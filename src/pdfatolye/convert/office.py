"""Office belgeleri → PDF (LibreOffice başsız mod).

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

from pdfatolye import proc
from pdfatolye.errors import PdfAtolyeError
from pdfatolye.formats import OFFICE_EXTS

__all__ = ["OFFICE_EXTS", "convert_office", "convert_office_many"]

_CALC = {".xlsx", ".xls", ".ods", ".csv", ".xlsm"}
_IMPRESS = {".pptx", ".ppt", ".odp", ".pptm"}
DEFAULT_TIMEOUT_S = 120
BATCH_TIMEOUT_PER_FILE_S = 60


class LibreOfficeNotFoundError(PdfAtolyeError):
    def __init__(self) -> None:
        super().__init__("LibreOffice bulunamadı; Office → PDF için gerekli. Kurmak için: "
                         "winget install TheDocumentFoundation.LibreOffice")


class OfficeConversionError(PdfAtolyeError):
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
                 timeout: float) -> str:
    """Girdileri tek çağrıda çevirir (taze profil). LibreOffice'in çıktı metnini döndürür."""
    with tempfile.TemporaryDirectory(prefix="pa-lo-profil-", ignore_cleanup_errors=True) as profile:
        uri = Path(profile).resolve().as_uri()
        args = [soffice, f"-env:UserInstallation={uri}", "--headless", "--norestore",
                "--nolockcheck", "--nodefault", "--nologo", "--convert-to", export,
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
            raise OfficeConversionError(
                f"'{item.name}' {int(timeout)} saniyede dönüştürülemedi (zaman aşımı). Dosya "
                "çok büyük ya da LibreOffice takıldı olabilir.") from None
        produced = work / "girdi.pdf"
        if not produced.is_file():
            detail = re.sub(r"\s+", " ", log).strip()[:200]
            raise OfficeConversionError(
                f"'{item.name}' dönüştürülemedi; dosya bozuk ya da parola korumalı olabilir."
                + (f" (LibreOffice: {detail})" if detail else ""))
        return _check_pdf(produced, item)


def convert_office_many(
    items: list[OfficeItem],
    *,
    soffice: str | None,
    pdfa: bool = False,
    on_progress=None,
) -> list[OfficeResult | PdfAtolyeError]:
    """Çok belgeyi olabildiğince tek LibreOffice çağrısında çevirir. Sonuç listesi girdilerle
    aynı sıradadır; her eleman ya OfficeResult ya da o dosyanın hatasıdır."""
    results: list[OfficeResult | PdfAtolyeError | None] = [None] * len(items)
    groups: dict[str, list[int]] = {}
    for i, item in enumerate(items):
        try:
            ext = _validate(soffice, item)
        except LibreOfficeNotFoundError:
            raise
        except PdfAtolyeError as e:
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
                except PdfAtolyeError as e:
                    results[i] = e
                done += 1
                if on_progress:
                    on_progress(done, len(items))
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
