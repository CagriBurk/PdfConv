"""Office belgeleri → PDF ve Office ↔ Office biçim dönüştürme (LibreOffice başsız mod).

Sağlamlık önlemleri (PLAN.md §5.2, tuzaklar #6, #17, #26):
- Her LibreOffice çağrısı TAZE bir profil klasörüyle başlar. Bu sürüm (26.8) bir kez kullanılmış
  profille — kopyası bile olsa — ikinci çağrıda takılıyor; taze profil her seferinde çalışıyor.
  Açık bir LibreOffice penceresi de dönüşümü kilitlemez.
- Profil ilk açılışta ~4 sn sürer; toplu dönüşümde bütün dosyalar TEK çağrıda çevrilir, çıkmayan
  dosya tek başına yeniden denenip gerçek hatası raporlanır.
- Girdiler kısa yollu iş klasörüne ASCII adla kopyalanır (uzun yol LibreOffice'i çökertiyor).
- Zaman aşımında, komut satırında bizim profil yolumuzu taşıyan bütün süreçler öldürülür
  (soffice.com'un açtığı soffice.bin onun alt süreci olarak görünmeyebiliyor).
- Çıkış kodu 0 olsa bile çıktı PDF'i açılıp sayfası olduğu doğrulanır.
- Belgede istenen ama bu bilgisayarda olmayan fontlar uyarı olarak bildirilir.

Biçim dönüştürme (`convert_office_format`) aynı çağrı düzenini kullanır; ayrıntılar o bölümde.
"""

from __future__ import annotations

import contextlib
import re
import shutil
import tempfile
import zipfile
from dataclasses import dataclass, field
from pathlib import Path

import pymupdf

from toolia import proc
from toolia.errors import TooliaError
from toolia.formats import OFFICE_CONVERT_FAMILIES, OFFICE_EXTS

__all__ = ["OFFICE_EXTS", "convert_office", "convert_office_format", "convert_office_many"]

_CALC = {".xlsx", ".xls", ".ods", ".csv", ".xlsm"}
_IMPRESS = {".pptx", ".ppt", ".odp", ".pptm"}
DEFAULT_TIMEOUT_S = 120
BATCH_TIMEOUT_PER_FILE_S = 60


class LibreOfficeNotFoundError(TooliaError):
    def __init__(self, purpose: str = "Office → PDF") -> None:
        super().__init__(f"LibreOffice bulunamadı; {purpose} için gerekli. Kurmak için: "
                         "winget install TheDocumentFoundation.LibreOffice")


class OfficeConversionError(TooliaError):
    pass


class _Timeout(Exception):
    pass


@dataclass
class OfficeResult:
    output: Path
    page_count: int
    warnings: list[str] = field(default_factory=list)


@dataclass
class OfficeItem:
    source: Path
    output: Path
    name: str


def _export_filter(ext: str, pdfa: bool) -> str:
    """'pdf' ya da PDF/A-2b için seçenekli filtre (LibreOffice 7.4+ JSON sözdizimi)."""
    if not pdfa:
        return "pdf"
    name = ("calc_pdf_Export" if ext in _CALC else
            "impress_pdf_Export" if ext in _IMPRESS else "writer_pdf_Export")
    return f'pdf:{name}:{{"SelectPdfVersion":{{"type":"long","value":"2"}}}}'


def _filter_group(ext: str) -> str:
    return "calc" if ext in _CALC else "impress" if ext in _IMPRESS else "writer"


def _run_soffice(soffice: str, inputs: list[Path], outdir: Path, export: str,
                 timeout: float, *, infilter: str | None = None) -> str:
    """Girdileri tek çağrıda çevirir (taze profil). LibreOffice'in çıktı metnini döndürür.
    `infilter` verilirse bütün girdiler o içe aktarma filtresiyle açılır (CSV okuma ayarları)."""
    with tempfile.TemporaryDirectory(prefix="pa-lo-profil-", ignore_cleanup_errors=True) as profile:
        uri = Path(profile).resolve().as_uri()
        args = [soffice, f"-env:UserInstallation={uri}", "--headless", "--norestore",
                "--nolockcheck", "--nodefault", "--nologo",
                *([f"--infilter={infilter}"] if infilter else []), "--convert-to", export,
                "--outdir", str(outdir), *map(str, inputs)]
        # İptal (kullanıcı ya da sunucu kapanışı) ve zaman aşımında süreç ağacı ve profil
        # yolumuzu taşıyan bütün soffice süreçleri öldürülür; iptal `proc.Cancelled` yükseltir.
        # Çıkışta da öldürülür: arkada kalan soffice.bin profili kilitlemesin.
        try:
            done = proc.run(args, timeout=timeout, marker=Path(profile).name,
                            marker_name="soffice")
        except proc.TimedOut:
            raise _Timeout() from None
        return (done.stderr or done.stdout or b"").decode("utf-8", errors="replace")


def _check_pdf(produced: Path, item: OfficeItem) -> OfficeResult:
    try:
        with pymupdf.open(produced) as doc:
            pages = doc.page_count
            pdf_fonts = {_base_font(f[3]) for p in doc for f in p.get_fonts()}
    except Exception as e:
        raise OfficeConversionError(f"'{item.name}' için üretilen PDF okunamadı.") from e
    if pages == 0:
        raise OfficeConversionError(f"'{item.name}' boş bir PDF üretti.")
    warnings = font_warnings(item.source, pdf_fonts, item.name)
    item.output.parent.mkdir(parents=True, exist_ok=True)
    try:
        shutil.move(str(produced), item.output)
    except (OSError, PermissionError) as e:
        raise OfficeConversionError(f"'{item.name}' çıktısı kaydedilemedi: {e}") from e
    return OfficeResult(item.output, pages, warnings)


def _validate(soffice: str | None, item: OfficeItem) -> str:
    if not soffice or not Path(soffice).is_file():
        raise LibreOfficeNotFoundError()
    ext = item.source.suffix.lower()
    if ext not in OFFICE_EXTS:
        raise OfficeConversionError(f"'{item.name}' desteklenen bir Office biçimi değil.")
    return ext


def convert_office(
    source: Path,
    output: Path,
    *,
    soffice: str | None,
    pdfa: bool = False,
    timeout: float = DEFAULT_TIMEOUT_S,
    display_name: str | None = None,
) -> OfficeResult:
    """Tek bir belgeyi PDF'e çevirir."""
    item = OfficeItem(Path(source), Path(output), display_name or Path(source).name)
    ext = _validate(soffice, item)
    with tempfile.TemporaryDirectory(prefix="pa-lo-") as tmp:
        work = Path(tmp)
        src = work / f"girdi{ext}"
        try:
            shutil.copyfile(item.source, src)
        except (OSError, PermissionError) as e:
            raise OfficeConversionError(f"'{item.name}' okunamadı: {e}") from e
        try:
            log = _run_soffice(soffice, [src], work, _export_filter(ext, pdfa), timeout)
        except _Timeout:
            raise _timeout_error(item, timeout) from None
        produced = work / "girdi.pdf"
        if not produced.is_file():
            raise _not_produced_error(item, log)
        return _check_pdf(produced, item)


def _timeout_error(item: OfficeItem, timeout: float) -> OfficeConversionError:
    return OfficeConversionError(
        f"'{item.name}' {int(timeout)} saniyede dönüştürülemedi (zaman aşımı). Dosya "
        "çok büyük ya da LibreOffice takıldı olabilir.")


def _not_produced_error(item: OfficeItem, log: str) -> OfficeConversionError:
    detail = re.sub(r"\s+", " ", log).strip()[:200]
    return OfficeConversionError(
        f"'{item.name}' dönüştürülemedi; dosya bozuk ya da parola korumalı olabilir."
        + (f" (LibreOffice: {detail})" if detail else ""))


def convert_office_many(
    items: list[OfficeItem],
    *,
    soffice: str | None,
    pdfa: bool = False,
    on_progress=None,
) -> list[OfficeResult | TooliaError]:
    """Çok belgeyi olabildiğince tek LibreOffice çağrısında çevirir. Sonuç listesi girdilerle
    aynı sıradadır; her eleman ya OfficeResult ya da o dosyanın hatasıdır."""
    results: list[OfficeResult | TooliaError | None] = [None] * len(items)
    groups: dict[str, list[int]] = {}
    for i, item in enumerate(items):
        try:
            ext = _validate(soffice, item)
        except LibreOfficeNotFoundError:
            raise
        except TooliaError as e:
            results[i] = e
            continue
        groups.setdefault(_filter_group(ext) if pdfa else "hepsi", []).append(i)

    done = 0
    for indices in groups.values():
        with tempfile.TemporaryDirectory(prefix="pa-lo-") as tmp:
            work = Path(tmp)
            inputs = []
            for i in indices:
                src = work / f"{i:04d}{items[i].source.suffix.lower()}"
                try:
                    shutil.copyfile(items[i].source, src)
                    inputs.append(src)
                except (OSError, PermissionError) as e:
                    results[i] = OfficeConversionError(f"'{items[i].name}' kopyalanamadı: {e}")
            if inputs:
                ext = items[indices[0]].source.suffix.lower()
                timeout = 30 + BATCH_TIMEOUT_PER_FILE_S * len(inputs)
                # Zaman aşımında çıkanlar alınır, kalanlar aşağıda tek tek denenir.
                with contextlib.suppress(_Timeout):
                    _run_soffice(soffice, inputs, work, _export_filter(ext, pdfa), timeout)
            for i in indices:
                if results[i] is not None:
                    done += 1
                    if on_progress:
                        on_progress(done, len(items))
                    continue
                produced = work / f"{i:04d}.pdf"
                try:
                    if produced.is_file():
                        results[i] = _check_pdf(produced, items[i])
                    else:  # tek başına yeniden dene: ya çıkar ya da gerçek hata mesajı gelir
                        results[i] = convert_office(items[i].source, items[i].output,
                                                    soffice=soffice, pdfa=pdfa,
                                                    display_name=items[i].name)
                except TooliaError as e:
                    results[i] = e
                done += 1
                if on_progress:
                    on_progress(done, len(items))
    return results  # type: ignore[return-value]


# --- Office ↔ Office biçim dönüştürme -----------------------------------------------------
#
# Aile içinde çevrilir (Word / tablo / sunum; `formats.OFFICE_CONVERT_FAMILIES`). Filtreler
# LibreOffice 26.8 ile tek tek denendi. CSV çıktısı Türkçe Excel'de çift tıkla açılmak üzere:
# - Ayraç ';': Türkçe Windows'ta liste ayırıcısı ';' (ondalık ayırıcı ','); Excel çift tıkla
#   açarken bunu kullanır. ',' ile her satır tek sütuna düşer, ondalıklar da bölünürdü.
# - UTF-8 + BOM: Excel BOM'u görünce UTF-8 okur; BOM'suz dosyayı Windows-1254 sanıp ğ/ş/ı'yı
#   bozar. LibreOffice BOM'u 14. seçenekle yazıyor; yazmadıysa sonradan eklenir.
# - Hücreler göründüğü gibi yazılır (Excel'in "CSV olarak kaydet"i gibi); sayı ve tarihler
#   LibreOffice'in yerel ayarıyla (Türkçe Windows'ta 1,5 ve 20.11.2026) yazılır.
# - Yalnız ilk sayfa yazılır (12. seçenek 0); kitapta başka sayfa varsa uyarılır.
# CSV girdisi ise LibreOffice'in varsayılanıyla (',' ve sistem kodlaması) bozuk okunur; ayraç
# ve kodlama (UTF-8 / Windows-1254) dosyadan sezilip içe aktarma filtresine verilir.

_CSV_FILTER = "Text - txt - csv (StarCalc)"
# Seçenekler sırayla: alan ayracı ; | metin ayracı " | UTF-8 | 1. satırdan | hücre biçimi yok |
# dil: sistem | metni hep tırnaklama: hayır | (içe aktarma) | göründüğü gibi: evet |
# formül yerine sonuç | (içe aktarma) | ilk sayfa | (içe aktarma) | BOM: evet
_CSV_EXPORT = f"csv:{_CSV_FILTER}:59,34,76,1,,0,false,true,true,false,false,0,false,true"
_FORMAT_EXPORT = {
    ".docx": "docx:MS Word 2007 XML",
    ".odt": "odt:writer8",
    ".rtf": "rtf:Rich Text Format",
    ".txt": "txt:Text (encoded):UTF8",
    ".xlsx": "xlsx:Calc MS Excel 2007 XML",
    ".ods": "ods:calc8",
    ".csv": _CSV_EXPORT,
    ".pptx": "pptx:Impress MS PowerPoint 2007 XML",
    ".odp": "odp:impress8",
}
_ZIP_TARGETS = {".docx", ".odt", ".xlsx", ".ods", ".pptx", ".odp"}
_ODF_EXTS = {".odt", ".ods", ".odp"}
_OOXML_EXTS = {".docx", ".docm", ".xlsx", ".xlsm", ".pptx", ".pptm"}
_MACRO_EXTS = {".docm", ".xlsm", ".pptm"}
_OLE_MAGIC = b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1"
_ENCRYPTED_STREAM = "EncryptedPackage".encode("utf-16-le")
_UTF8_BOM = b"\xef\xbb\xbf"
_CP1254, _UTF8 = 36, 76  # LibreOffice karakter kümesi numaraları (rtl_TextEncoding)


def _label(ext: str) -> str:
    return ext.lstrip(".").upper()


def _family_sources(target: str) -> frozenset[str]:
    """Hedefin ailesindeki kaynak uzantılar; hedef bir Office hedefi değilse hata."""
    for sources, targets in OFFICE_CONVERT_FAMILIES.values():
        if target in targets and target in _FORMAT_EXPORT:
            return sources
    raise OfficeConversionError(f"Office belgeleri {_label(target) or '?'} biçimine çevrilemez.")


def _file_contains(path: Path, needle: bytes, chunk: int = 1 << 20) -> bool:
    with path.open("rb") as f:
        tail = b""
        while block := f.read(chunk):
            if needle in tail + block:
                return True
            tail = block[-(len(needle) - 1):]
    return False


def is_password_protected(path: Path) -> bool:
    """Ucuz denetim: parolalı OOXML bir OLE kabıdır ('EncryptedPackage' akışı); parolalı ODF'nin
    manifest'inde şifreleme bilgisi bulunur. Eski .doc/.xls/.ppt için bilinmez (False);
    LibreOffice onları açamayınca 'bozuk ya da parola korumalı' hatası çabucak gelir."""
    ext = path.suffix.lower()
    try:
        if ext in _OOXML_EXTS:
            with path.open("rb") as f:
                if f.read(len(_OLE_MAGIC)) != _OLE_MAGIC:
                    return False
            return _file_contains(path, _ENCRYPTED_STREAM)
        if ext in _ODF_EXTS:
            with zipfile.ZipFile(path) as zf:
                return b"encryption-data" in zf.read("META-INF/manifest.xml")
    except (OSError, zipfile.BadZipFile, KeyError):
        return False
    return False


def _csv_infilter(path: Path) -> str:
    """CSV girdisinin ayracını ve kodlamasını sezip LibreOffice içe aktarma filtresini kurar."""
    try:
        with path.open("rb") as f:
            raw = f.read(64 * 1024)
    except OSError:
        raw = b""
    charset = _UTF8
    try:
        text = raw.removeprefix(_UTF8_BOM).decode("utf-8")
    except UnicodeDecodeError as e:
        if e.start >= len(raw) - 3 and len(raw) == 64 * 1024:  # örnek çok baytlı harfte kesildi
            text = raw[:e.start].removeprefix(_UTF8_BOM).decode("utf-8")
        else:
            charset, text = _CP1254, raw.decode("cp1254", errors="replace")
    sep = _sniff_separator(text)
    # alan ayracı | metin ayracı " | kodlama | 1. satırdan | hücre biçimi yok | dil: sistem |
    # tırnaklı alan metin olsun: hayır | özel sayıları (tarih vb.) tanı: evet
    return f"{_CSV_FILTER}:{ord(sep)},34,{charset},1,,0,false,true"


def _sniff_separator(text: str) -> str:
    """';', ',' ya da sekme: ilk satırlarda her satırda aynı sayıda geçen ve en çok geçen."""
    lines = [ln for ln in text.splitlines()[:20] if ln.strip()]
    if len(lines) > 1 and len(text) >= 64 * 1024:
        lines = lines[:-1]  # örneğin son satırı yarım olabilir
    best, best_score = ";", 0
    for sep in (";", "\t", ","):  # eşitlikte Türkçe Excel'in ayracı öne geçer
        counts = [len(re.sub(r'"[^"]*"', "", ln).split(sep)) - 1 for ln in lines]
        if not counts or min(counts) == 0:
            continue
        score = min(counts) + (1000 if len(set(counts)) == 1 else 0)
        if score > best_score:
            best, best_score = sep, score
    return best


def _sheet_count(path: Path) -> int | None:
    """Çalışma kitabındaki sayfa sayısı (xlsx/xlsm/ods'de zip içinden); bilinemiyorsa None."""
    ext = path.suffix.lower()
    if ext == ".csv":
        return 1
    try:
        with zipfile.ZipFile(path) as zf:
            if ext in (".xlsx", ".xlsm"):
                return len(re.findall(rb"<(?:\w+:)?sheet[\s/>]", zf.read("xl/workbook.xml")))
            if ext == ".ods":
                return len(re.findall(rb"<table:table[\s>]", zf.read("content.xml")))
    except (OSError, zipfile.BadZipFile, KeyError):
        return None
    return None


def _has_basic(odf: Path) -> bool:
    try:
        with zipfile.ZipFile(odf) as zf:
            return any(n.startswith("Basic/") for n in zf.namelist())
    except (OSError, zipfile.BadZipFile):
        return False


def _format_check(item: OfficeItem, sources: frozenset[str], target: str) -> str:
    ext = item.source.suffix.lower()
    if ext not in sources:
        raise OfficeConversionError(f"'{item.name}' {_label(target)} biçimine çevrilemez.")
    if is_password_protected(item.source):
        raise OfficeConversionError(
            f"'{item.name}' parola korumalı; LibreOffice parolalı belgeyi açamaz. Belgeyi "
            "Office'te açıp parolasını kaldır, sonra yeniden dene.")
    return ext


def _finish_format(produced: Path, item: OfficeItem, target: str) -> list[str]:
    """Çıktıyı doğrular, gerekirse düzeltir (CSV BOM), yerine taşır; uyarıları döndürür."""
    try:
        data_ok = produced.stat().st_size > 0
        if data_ok and target in _ZIP_TARGETS:
            with zipfile.ZipFile(produced) as zf:
                data_ok = bool(zf.namelist())
        elif data_ok:
            raw = produced.read_bytes()
            data_ok = bool(raw.removeprefix(_UTF8_BOM).strip())
            if target == ".csv" and not raw.startswith(_UTF8_BOM):
                produced.write_bytes(_UTF8_BOM + raw)
    except (OSError, zipfile.BadZipFile) as e:
        raise OfficeConversionError(f"'{item.name}' için üretilen dosya okunamadı.") from e
    if not data_ok:
        raise OfficeConversionError(
            f"'{item.name}' boş bir {_label(target)} dosyası üretti; belgede aktarılacak içerik "
            "yok ya da dönüşüm eksik kaldı.")

    warnings = []
    src_ext = item.source.suffix.lower()
    if target == ".csv":
        sheets = _sheet_count(item.source)
        if sheets is None:
            warnings.append(f"'{item.name}': CSV'ye yalnız ilk sayfa aktarıldı; kitapta başka "
                            "sayfalar varsa onlar alınmadı.")
        elif sheets > 1:
            warnings.append(f"'{item.name}': kitapta {sheets} sayfa var; CSV tek sayfa "
                            "tutabildiği için yalnız ilk sayfa aktarıldı.")
    if src_ext in _MACRO_EXTS:
        if target in _ODF_EXTS and _has_basic(produced):
            warnings.append(f"'{item.name}': makrolar LibreOffice Basic olarak taşındı; "
                            "Microsoft Office'te çalışmaz, LibreOffice'te de denetlemeden "
                            "çalıştırma.")
        else:
            warnings.append(f"'{item.name}': makrolar {_label(target)} dosyasına aktarılmadı "
                            "(atıldı).")
    item.output.parent.mkdir(parents=True, exist_ok=True)
    try:
        shutil.move(str(produced), item.output)
    except (OSError, PermissionError) as e:
        raise OfficeConversionError(f"'{item.name}' çıktısı kaydedilemedi: {e}") from e
    return warnings


def _format_one(item: OfficeItem, *, soffice: str, target: str,
                timeout: float = DEFAULT_TIMEOUT_S) -> list[str]:
    """Tek belgeyi tek başına çevirir; çıkmazsa LibreOffice'in mesajıyla hata verir."""
    ext = item.source.suffix.lower()
    with tempfile.TemporaryDirectory(prefix="pa-lo-") as tmp:
        work = Path(tmp)
        src = work / f"girdi{ext}"
        outdir = work / "cikti"  # aynı uzantıya kaydetme girdinin üzerine yazmasın
        outdir.mkdir()
        try:
            shutil.copyfile(item.source, src)
        except (OSError, PermissionError) as e:
            raise OfficeConversionError(f"'{item.name}' okunamadı: {e}") from e
        infilter = _csv_infilter(item.source) if ext == ".csv" else None
        try:
            log = _run_soffice(soffice, [src], outdir, _FORMAT_EXPORT[target], timeout,
                               infilter=infilter)
        except _Timeout:
            raise _timeout_error(item, timeout) from None
        produced = outdir / f"girdi{target}"
        if not produced.is_file():
            raise _not_produced_error(item, log)
        return _finish_format(produced, item, target)


def convert_office_format(
    items: list[OfficeItem],
    *,
    soffice: str | None,
    target: str,
    on_progress=None,
) -> list[list[str] | TooliaError]:
    """Office belgelerini aynı ailede başka bir biçime çevirir (ör. .doc → .docx, .xlsx → .csv).
    Belgeler olabildiğince tek LibreOffice çağrısında çevrilir, çıkmayan tek başına yeniden
    denenir. Sonuç girdilerle aynı sıradadır; her eleman ya o dosyanın uyarı listesi (çıktı
    `item.output`'a yazıldı) ya da o dosyanın hatasıdır. LibreOffice yoksa işin tamamı durur."""
    target = target.lower()
    sources = _family_sources(target)
    if not soffice or not Path(soffice).is_file():
        raise LibreOfficeNotFoundError("Office biçim dönüştürme")
    total = len(items)
    results: list[list[str] | TooliaError | None] = [None] * total
    done = 0

    def finished() -> None:
        nonlocal done
        done += 1
        if on_progress:
            on_progress(done, total)

    # CSV girdileri kendi içe aktarma ayarlarıyla ayrı çağrıda açılır; diğerleri tek çağrıda.
    groups: dict[str | None, list[int]] = {}
    for i, item in enumerate(items):
        try:
            ext = _format_check(item, sources, target)
        except TooliaError as e:
            results[i] = e
            finished()
            continue
        infilter = _csv_infilter(item.source) if ext == ".csv" else None
        groups.setdefault(infilter, []).append(i)

    for infilter, indices in groups.items():
        with tempfile.TemporaryDirectory(prefix="pa-lo-") as tmp:
            work = Path(tmp)
            outdir = work / "cikti"
            outdir.mkdir()
            inputs = []
            for i in indices:
                src = work / f"{i:04d}{items[i].source.suffix.lower()}"
                try:
                    shutil.copyfile(items[i].source, src)
                    inputs.append(src)
                except (OSError, PermissionError) as e:
                    results[i] = OfficeConversionError(f"'{items[i].name}' kopyalanamadı: {e}")
            if inputs:
                timeout = 30 + BATCH_TIMEOUT_PER_FILE_S * len(inputs)
                # Zaman aşımında çıkanlar alınır, kalanlar aşağıda tek tek denenir.
                with contextlib.suppress(_Timeout):
                    _run_soffice(soffice, inputs, outdir, _FORMAT_EXPORT[target], timeout,
                                 infilter=infilter)
            for i in indices:
                if results[i] is None:
                    produced = outdir / f"{i:04d}{target}"
                    try:
                        if produced.is_file():
                            results[i] = _finish_format(produced, items[i], target)
                        else:  # tek başına yeniden dene: ya çıkar ya da gerçek hata mesajı gelir
                            results[i] = _format_one(items[i], soffice=soffice, target=target)
                    except TooliaError as e:
                        results[i] = e
                finished()
    return results  # type: ignore[return-value]


# --- Font kontrolü -----------------------------------------------------------------------

_ATTR = r'="([^"]+)"'


def _base_font(pdf_name: str) -> str:
    """'ABCDEF+Calibri-Bold' → 'calibri'."""
    name = pdf_name.split("+", 1)[-1]
    name = re.split(r"[-,]", name, maxsplit=1)[0]
    return _norm(name)


def _norm(name: str) -> str:
    name = re.sub(r"(?i)(bold|italic|oblique|regular|light|semibold|medium|mt|ps)$", "", name)
    return re.sub(r"[^a-z0-9]", "", name.lower())


def _read(zf: zipfile.ZipFile, pattern: str) -> str:
    return "\n".join(zf.read(n).decode("utf-8", "ignore") for n in zf.namelist()
                     if re.fullmatch(pattern, n))


def requested_fonts(path: Path) -> set[str]:
    """Belgenin metinde kullandığı font adları (bilinen biçimler için; diğerlerinde boş)."""
    ext = path.suffix.lower()
    try:
        zf = zipfile.ZipFile(path)
    except (zipfile.BadZipFile, OSError):
        return set()
    with zf:
        fonts: set[str] = set()
        if ext in (".docx", ".docm"):
            xml = _read(zf, r"word/(document|styles|header\d*|footer\d*)\.xml")
            fonts |= set(re.findall(r"<w:rFonts[^>]*?w:(?:ascii|hAnsi)" + _ATTR, xml))
            if re.search(r"w:(?:ascii|hAnsi)Theme=", xml):
                fonts |= _theme_fonts(_read(zf, r"word/theme/theme\d*\.xml"))
        elif ext in (".pptx", ".pptm"):
            xml = _read(zf, r"ppt/(slides/slide\d+|slideMasters/slideMaster\d+)\.xml")
            fonts |= {f for f in re.findall(r"<a:latin[^>]*?typeface" + _ATTR, xml)
                      if not f.startswith("+")}
            fonts |= _theme_fonts(_read(zf, r"ppt/theme/theme\d*\.xml"))
        elif ext in (".xlsx", ".xlsm"):
            xml = _read(zf, r"xl/styles\.xml")
            fonts |= set(re.findall(r"<name val" + _ATTR, xml))
        elif ext in (".odt", ".ods", ".odp"):
            xml = _read(zf, r"(content|styles)\.xml")
            fonts |= set(re.findall(r'svg:font-family="\'?([^"\']+)', xml))
            fonts |= set(re.findall(r'fo:font-family="\'?([^"\']+)', xml))
    return {f.strip() for f in fonts if f.strip()}


def _theme_fonts(theme_xml: str) -> set[str]:
    out = set()
    for kind in ("majorFont", "minorFont"):
        m = re.search(rf"<a:{kind}>.*?<a:latin typeface{_ATTR}", theme_xml, re.DOTALL)
        if m:
            out.add(m.group(1))
    return out


_STYLE_WORDS = re.compile(
    r"(?i)\b(bold|italic|oblique|regular|light|semilight|semibold|demibold|extrabold|black|"
    r"medium|thin|extralight|condensed|narrow)\b")


def _family(name: str) -> str:
    return _norm(_STYLE_WORDS.sub("", name))


_installed_cache: set[str] | None = None


def installed_fonts() -> set[str] | None:
    """Windows'ta kurulu font aileleri (kayıt defterinden). Bilinmiyorsa None."""
    global _installed_cache
    if _installed_cache is not None:
        return _installed_cache
    try:
        import winreg
    except ImportError:
        return None
    key_path = r"SOFTWARE\Microsoft\Windows NT\CurrentVersion\Fonts"
    names: set[str] = set()
    for hive in (winreg.HKEY_LOCAL_MACHINE, winreg.HKEY_CURRENT_USER):
        try:
            with winreg.OpenKey(hive, key_path) as key:
                for i in range(winreg.QueryInfoKey(key)[1]):
                    value = winreg.EnumValue(key, i)[0]
                    for part in re.sub(r"\(.*?\)", "", value).split("&"):
                        if part.strip():
                            names.add(_family(part))
        except OSError:
            continue
    _installed_cache = names
    return names


def _is_available(font: str, pdf_fonts: set[str], installed: set[str] | None) -> bool:
    fam = _family(font)
    if fam in pdf_fonts or _norm(font) in pdf_fonts:
        return True
    if installed is None:  # kurulu fontları bilemiyoruz: yalnızca gömülü fontlara güven
        return False
    return fam in installed or any(i.startswith(fam) for i in installed if len(fam) >= 4)


def font_warnings(source: Path, pdf_fonts: set[str], name: str) -> list[str]:
    """Hem PDF'e gömülmemiş hem de bilgisayarda kurulu olmayan fontları bildirir (stil
    tanımında geçip metinde hiç kullanılmayan fontlar için gereksiz uyarı vermesin diye)."""
    installed = installed_fonts()
    missing = sorted(f for f in requested_fonts(source)
                     if not _is_available(f, pdf_fonts, installed))
    if not missing:
        return []
    return [f"'{name}': {', '.join(missing)} fontu bu bilgisayarda yok; yerine benzer bir font "
            "kullanıldı, yerleşim biraz farklı olabilir."]
