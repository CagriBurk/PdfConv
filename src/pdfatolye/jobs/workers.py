"""İş türlerinin gerçek işi. Çekirdek fonksiyonları depo dosyalarıyla çağırır.

Her çalışan: geçici klasöre (kısa yol) yazar, sonuçları depoya ekler, `WorkResult` döndürür.
"""

from __future__ import annotations

import re
import shutil
import tempfile
from collections.abc import Callable
from dataclasses import dataclass, field
from functools import partial
from pathlib import Path

from pdfatolye import engines
from pdfatolye.convert.markdown.render import BrowserNotFoundError
from pdfatolye.core import compress as compresslib
from pdfatolye.core import content, images, pages, security
from pdfatolye.core.pdfio import base_name, safe_filename, split_ext, strip_ext
from pdfatolye.errors import EncryptedPdfError, PdfAtolyeError, UnsupportedFileError
from pdfatolye.storage import FileMeta

Report = Callable[[float, str], None]


@dataclass
class WorkResult:
    outputs: list[FileMeta]
    warnings: list[str] = field(default_factory=list)


STEM_MAX = 56  # çıktı adındaki kaynak adı: "_duzenlenmis", "_01-05" gibi ekler kesilmesin


def _title(meta: FileMeta) -> str:
    """Yer imi başlığı: kısaltılmamış ad (uzantısız)."""
    return split_ext(meta.name)[0]


def _stem(meta: FileMeta) -> str:
    return safe_filename(split_ext(meta.name)[0], fallback="belge", max_len=STEM_MAX)


def _out_name(requested: str | None, default: str, ext: str = ".pdf") -> str:
    """Çıktı adı. İstenen addan yalnızca kendi uzantısı atılır ("Rapor v1.2" kısalmaz)."""
    stem = strip_ext(Path(requested).name, ext) if requested else default
    return safe_filename(stem, fallback="cikti") + ext


def _require(store, file_id: str, kind: str) -> tuple[FileMeta, Path]:
    meta = store.get(file_id)
    if meta.kind != kind:
        raise UnsupportedFileError(Path(meta.name), {"pdf": "PDF", "image": "resim",
                                                     "markdown": "Markdown"}.get(kind, kind))
    return meta, store.path(file_id)


def _protect(store, req, file_id: str, out: Path) -> list[str]:
    """Şifreli kaynaktan tek çıktı üretilince şifresi çıktıda da korunur; düzenleme bir dosyanın
    şifresini sessizce kaldırmamalı. Şifreyi yalnızca açıkça "Şifre kaldır" kaldırır."""
    password = req.passwords.get(file_id)
    if not store.get(file_id).encrypted and not password:
        return []
    return security.keep_encryption(store.path(file_id), out, password)


def _unprotected_warning(metas: list[FileMeta], protected_id: str | None = None) -> list[str]:
    """Birden çok kaynaklı çıktıda tek bir şifre seçilemez: şifresiz kaldığı açıkça söylenir."""
    names = [m.name for m in metas if m.encrypted and m.id != protected_id]
    if not names:
        return []
    return [f"Şifreli kaynak ({', '.join(names)}) kullanıldı; bu kaynağın şifresi çıktıya "
            "taşınmadı. Gerekirse Güvenlik ve Bakım → Şifrele ile şifrele."]


def run(manager, req, report: Report, job_id: str) -> WorkResult:
    fn = {
        "compose": compose,
        "merge": merge,
        "split": split,
        "images_to_pdf": images_to_pdf,
        "pdf_to_images": pdf_to_images,
        "md_to_pdf": md_to_pdf,
        "office_to_pdf": office_to_pdf,
        "apply": apply,
        "compress": compress,
        "ocr": ocr,
        "encrypt": encrypt,
        "decrypt": decrypt,
        "clean_metadata": clean_metadata,
        "repair": repair,
        "install_engine": install_engine,
    }[req.type]
    with tempfile.TemporaryDirectory(prefix="pa-is-") as tmp:
        try:
            return fn(manager.store, manager.settings, req, report, Path(tmp), job_id)
        except PdfAtolyeError as e:
            raise with_display_name(e, manager.store) from e


def with_display_name(e: PdfAtolyeError, store) -> PdfAtolyeError:
    """Hata mesajındaki depo içi adı ('v2.pdf') kullanıcının gördüğü adla değiştirir."""
    path = getattr(e, "path", None)
    if not isinstance(path, Path) or path.parent.parent != store.root:
        return e
    try:
        name = store.get(path.parent.name).name
    except PdfAtolyeError:
        return e
    if isinstance(e, EncryptedPdfError):
        return EncryptedPdfError(Path(name), e.wrong_password)
    return PdfAtolyeError(str(e).replace(f"'{path.name}'", f"'{name}'"))


def compose(store, settings, req, report, tmp: Path, job_id) -> WorkResult:
    order: list[str] = []
    for item in req.items:
        if item.file and item.file not in order:
            order.append(item.file)
    metas, paths = [], []
    for fid in order:
        meta, path = _require(store, fid, "pdf")
        metas.append(meta)
        paths.append(path)
    index = {fid: i for i, fid in enumerate(order)}
    manifest = [
        pages.BlankPage(item.width, item.height) if item.blank
        else pages.PageRef(index[item.file], item.page, item.rotate)
        for item in req.items
    ]
    report(0.2, "Sayfalar diziliyor")
    out = tmp / "cikti.pdf"
    # Her parçadan sonra ilerleme: iptal büyük belgede de beklemeden etkili olur.
    pages.compose(paths, manifest, out, passwords=[req.passwords.get(f) for f in order],
                  keep_bookmarks=req.keep_bookmarks, bookmark_titles=[_title(m) for m in metas],
                  on_progress=lambda f: report(0.2 + 0.65 * f, "Sayfalar diziliyor"))
    report(0.9, "Kaydediliyor")
    if req.target == "version":
        notes = _protect(store, req, req.base_file, out)
        notes += _unprotected_warning(metas, req.base_file)
        return WorkResult([store.new_version(req.base_file, out, "Sayfa düzenleme")], notes)
    if len(metas) == 1:
        notes = _protect(store, req, metas[0].id, out)
    else:
        notes = _unprotected_warning(metas)
    base = _stem(metas[0]) if metas else "belge"
    name = _out_name(req.name, f"{base}_duzenlenmis")
    return WorkResult([store.add_file(out, name, job_id=job_id)], notes)


def merge(store, settings, req, report, tmp: Path, job_id) -> WorkResult:
    metas, paths = zip(*(_require(store, f, "pdf") for f in req.files), strict=True)
    report(0.2, "Birleştiriliyor")
    out = tmp / "birlesik.pdf"
    pages.merge(list(paths), out, passwords=[req.passwords.get(f) for f in req.files],
                bookmark_per_file=req.bookmark_per_file,
                bookmark_titles=[_title(m) for m in metas])
    name = _out_name(req.name, f"{_stem(metas[0])}_birlesik")
    return WorkResult([store.add_file(out, name, job_id=job_id)],
                      _unprotected_warning(list(metas)))


def split(store, settings, req, report, tmp: Path, job_id) -> WorkResult:
    meta, path = _require(store, req.file, "pdf")
    report(0.1, "Bölünüyor")
    parts = pages.split(path, tmp / "parcalar", mode=req.mode, every=req.every, spec=req.spec,
                        password=req.passwords.get(req.file), name_stem=_stem(meta))
    outputs, notes = [], []
    for i, part in enumerate(parts, start=1):
        notes += _protect(store, req, req.file, part)
        outputs.append(store.add_file(part, part.name, job_id=job_id))
        report(0.1 + 0.9 * i / len(parts), f"{i}/{len(parts)} parça")
    return WorkResult(outputs, list(dict.fromkeys(notes)))


def images_to_pdf(store, settings, req, report, tmp: Path, job_id) -> WorkResult:
    metas, paths = zip(*(_require(store, f, "image") for f in req.files), strict=True)
    report(0.2, "Resimler yerleştiriliyor")
    out = tmp / "resimler.pdf"
    images.images_to_pdf(list(paths), out, page_size=req.page_size,
                         orientation=req.orientation, margin_mm=req.margin_mm)
    name = _out_name(req.name, _stem(metas[0]) if len(metas) == 1 else "resimler")
    return WorkResult([store.add_file(out, name, job_id=job_id)])


def pdf_to_images(store, settings, req, report, tmp: Path, job_id) -> WorkResult:
    meta, path = _require(store, req.file, "pdf")
    report(0.1, "Sayfalar çiziliyor")
    files = images.pdf_to_images(path, tmp / "resimler", dpi=req.dpi, fmt=req.fmt,
                                 spec=req.spec, password=req.passwords.get(req.file),
                                 name_stem=_stem(meta))
    outputs = []
    for i, f in enumerate(files, start=1):
        outputs.append(store.add_file(f, f.name, job_id=job_id))
        report(0.1 + 0.9 * i / len(files), f"{i}/{len(files)} sayfa")
    notes = ["Kaynak PDF şifreli ama resim dosyaları şifre taşımaz."] if meta.encrypted else []
    return WorkResult(outputs, notes)


def md_to_pdf(store, settings, req, report, tmp: Path, job_id) -> WorkResult:
    from pdfatolye.convert.markdown import MarkdownPrinter, MdOptions
    from pdfatolye.core.textio import decode_text

    work = tmp / "md"
    work.mkdir()
    notes: list[str] = []
    if req.file:
        meta = store.get(req.file)
        if meta.kind not in ("markdown", "text"):  # arayüz .txt notu da kabul ediyor
            raise UnsupportedFileError(Path(meta.name), "Markdown")
        name = meta.name
        if req.text is not None:
            text = req.text
        else:
            text, note = decode_text(store.path(req.file).read_bytes(), meta.name)
            notes += [note] if note else []
    else:
        name, text = req.name, req.text or ""
    md_name = safe_filename(split_ext(base_name(name))[0], fallback="belge") + ".md"
    source = work / md_name
    # newline="": Windows'ta \n → \r\n çevrilmesin; metin zaten \r\n içeriyorsa \r\r\n olur ve
    # satır numaraları iki katına çıkar (uyarılardaki "Satır N" yanlış gösterilir).
    source.write_text(text.replace("\r\n", "\n"), encoding="utf-8", newline="")
    # Ekler notun yanına özgün adlarıyla konur: ![[resim.png]] ve ![](resim.png) bulunsun.
    for fid in req.attachments:
        att = store.get(fid)
        shutil.copyfile(store.path(fid), work / att.name)

    browser = engines.detect_browser(settings).path
    report(0.15, "Tarayıcı başlatılıyor")
    defaults = MdOptions(theme=settings.default_theme, paper=settings.default_paper)
    with MarkdownPrinter(browser, settings.vault_path, confine=True,
                         user_defaults=defaults) as printer:
        report(0.4, "Basılıyor")
        result = printer.convert(source, tmp / "cikti.pdf",
                                 MdOptions(**req.options.model_dump()))
    meta = store.add_file(result.output, Path(md_name).stem + ".pdf", job_id=job_id)
    return WorkResult([meta], notes + result.warnings)


def office_to_pdf(store, settings, req, report, tmp: Path, job_id) -> WorkResult:
    """Office dosyaları tek LibreOffice çağrısında, HTML/metin tarayıcıyla çevrilir. Tek dosyanın
    hatası işi durdurmaz; motor eksikse durdurur (devam etmenin anlamı yok)."""
    from pdfatolye.convert.html import print_html, print_text
    from pdfatolye.convert.office import OfficeItem, convert_office_many

    metas = [store.get(fid) for fid in req.files]
    for m in metas:
        if m.kind not in ("office", "html", "text", "markdown"):
            raise UnsupportedFileError(Path(m.name), "Office, HTML ya da metin")
    outs = [tmp / f"{i:04d}.pdf" for i in range(len(metas))]
    results: dict[int, list[str] | PdfAtolyeError] = {}
    total = len(metas)

    office_idx = [i for i, m in enumerate(metas) if m.kind == "office"]
    if office_idx:
        report(0.05, f"LibreOffice: {len(office_idx)} belge")
        items = [OfficeItem(store.path(metas[i].id), outs[i], metas[i].name) for i in office_idx]
        soffice = engines.detect_libreoffice(settings).path
        done = convert_office_many(
            items, soffice=soffice, pdfa=req.pdfa,
            on_progress=lambda n, t: report(0.05 + 0.8 * n / total, f"{n}/{total} belge"),
        )
        for i, r in zip(office_idx, done, strict=True):
            results[i] = r if isinstance(r, PdfAtolyeError) else r.warnings

    browser = engines.detect_browser(settings).path
    for i, m in enumerate(metas):
        if m.kind == "office":
            continue
        report(len(results) / total, f"{len(results) + 1}/{total}: {m.name}")
        printer = partial(print_html, confine=True) if m.kind == "html" else print_text
        try:
            results[i] = printer(store.path(m.id), outs[i], browser_path=browser,
                                 display_name=m.name).warnings
        except BrowserNotFoundError:
            raise
        except PdfAtolyeError as e:
            results[i] = e

    converted = [(metas[i], outs[i]) for i in range(total) if isinstance(results[i], list)]
    errors = [str(with_display_name(r, store)) for r in results.values()
              if isinstance(r, PdfAtolyeError)]
    warnings = [w for i in range(total) if isinstance(results[i], list) for w in results[i]]
    if not converted:
        raise PdfAtolyeError(errors[0] if len(errors) == 1 else
                             "Hiçbir dosya dönüştürülemedi:\n" + "\n".join(errors))
    if req.merge and len(converted) > 1:
        report(0.95, "Birleştiriliyor")
        merged = tmp / "birlesik.pdf"
        pages.merge([p for _, p in converted], merged, bookmark_per_file=True,
                    bookmark_titles=[_title(m) for m, _ in converted])
        name = _out_name(req.name, f"{_stem(converted[0][0])}_birlesik")
        outputs = [store.add_file(merged, name, job_id=job_id)]
    else:
        outputs = [store.add_file(p, _stem(m) + ".pdf", job_id=job_id) for m, p in converted]
    return WorkResult(outputs, errors + warnings)

_APPLY_NOTES = {"watermark": "Filigran", "page_numbers": "Sayfa numarası"}


def apply(store, settings, req, report, tmp: Path, job_id) -> WorkResult:
    meta, path = _require(store, req.file, "pdf")
    assets = {}
    for key in dict.fromkeys(op.asset for op in req.ops if getattr(op, "asset", None)):
        assets[key] = _require(store, key, "image")[1]
    report(0.2, "Değişiklikler uygulanıyor")
    out = tmp / "cikti.pdf"
    result = content.apply_ops(path, out, req.ops, password=req.passwords.get(req.file),
                               assets=assets)
    report(0.9, "Kaydediliyor")
    warnings = result.warnings + _protect(store, req, req.file, out)
    kinds = {op.type for op in req.ops}
    note = _APPLY_NOTES.get(next(iter(kinds)), "") if len(kinds) == 1 else ""
    if req.target == "version":
        if "redact" in kinds:
            warnings.append("Karartılmamış önceki sürüm, sen silene ya da otomatik temizliğe kadar "
                            "bu bilgisayarda durur. İndirdiğin dosyada karartılan içerik yoktur.")
        return WorkResult([store.new_version(req.file, out, note or "İçerik düzenleme")], warnings)
    name = _out_name(req.name, f"{_stem(meta)}_duzenlenmis")
    return WorkResult([store.add_file(out, name, job_id=job_id)], warnings)


def _size(n: int) -> str:
    return f"{n / 1024 / 1024:.1f} MB" if n >= 1024 * 1024 else f"{n / 1024:.0f} KB"


def compress(store, settings, req, report, tmp: Path, job_id) -> WorkResult:
    gs = engines.detect_ghostscript(settings).path if req.level == "guclu" else None
    outputs, warnings = [], []
    total = len(req.files)
    for i, fid in enumerate(req.files):
        meta, path = _require(store, fid, "pdf")
        prefix = f"{i + 1}/{total} {meta.name}: " if total > 1 else ""
        report(i / total, f"{prefix}başlıyor")
        out = tmp / f"{i:04d}.pdf"
        r = compresslib.compress(
            path, out, req.level, password=req.passwords.get(fid), ghostscript=gs,
            report=lambda f, m, i=i, prefix=prefix: report((i + f) / total, prefix + m))
        kept, after = r.kept_original, r.after
        if not kept:
            warnings += _protect(store, req, fid, out)  # şifre biraz yer tutar: boyut yeniden
            after = out.stat().st_size
            if after >= r.before:
                shutil.copyfile(path, out)
                kept = True
        if kept:
            warnings.append(f"{meta.name}: daha fazla küçülmedi, orijinal korundu "
                            f"({_size(r.before)}).")
        else:
            warnings.append(f"{meta.name}: {_size(r.before)} → {_size(after)} "
                            f"(%{round((1 - after / r.before) * 100)} küçüldü)")
        if after > r.before * 0.8 and (why := _little_gain_reason(path, req, fid)):
            warnings.append(f"{meta.name}: {why}")
        outputs.append(store.add_file(out, _out_name(None, f"{_stem(meta)}_kucuk"),
                                      job_id=job_id))
    return WorkResult(outputs, warnings)


def _little_gain_reason(path: Path, req, fid: str) -> str | None:
    """Az küçüldüyse nedenini söyler (kullanıcı "neden yalnızca %10?" diye sormasın)."""
    share = compresslib.image_share(path, req.passwords.get(fid))
    if share is None:
        return None
    if share < 0.3:
        return (f"dosyanın yalnızca %{round(share * 100)}'i resim; gerisi yazı, yazı tipi ve "
                "çizim. Bu tür PDF'ler zaten sıkıştırılmış olur, büyük kazanç beklenmez.")
    if req.level == "kayipsiz":
        return ("dosyanın çoğu resim; kayıpsız seviye resimlere dokunmaz. Daha küçük dosya için "
                "Dengeli ya da Güçlü seç.")
    return "resimler zaten bu seviyenin çözünürlüğünde ya da altında sıkıştırılmış."


def _single_output(store, req, meta, out: Path, note: str, suffix: str, job_id) -> FileMeta:
    if req.target == "version":
        return store.new_version(req.file, out, note)
    return store.add_file(out, _out_name(None, f"{_stem(meta)}_{suffix}"), job_id=job_id)


def ocr(store, settings, req, report, tmp: Path, job_id) -> WorkResult:
    from pdfatolye.core import ocr as ocrlib

    meta, path = _require(store, req.file, "pdf")
    tess = engines.detect_tesseract(settings)
    if not tess.available:
        raise PdfAtolyeError("OCR için Tesseract bulunamadı. Ayarlar sayfasındaki kurulum "
                             "komutunu çalıştır.")
    out = tmp / "ocr.pdf"
    # İptal: `report` JobCancelled yükseltir ya da süreç izlenirken bayrak görülür; ikisinde de
    # OCR süreç ağacı öldürülür (`proc.spawn`).
    r = ocrlib.ocr(path, out, mode=req.mode, langs=req.langs,
                   password=req.passwords.get(req.file), tesseract=tess.path,
                   ghostscript=engines.detect_ghostscript(settings).path, on_progress=report)
    summary = f"{r.page_count} sayfanın {r.pages_with_text} tanesinde metin var."
    notes = _protect(store, req, req.file, out)
    return WorkResult([_single_output(store, req, meta, out, "OCR", "ocr", job_id)],
                      [summary, *r.warnings, *notes])


def encrypt(store, settings, req, report, tmp: Path, job_id) -> WorkResult:
    meta, path = _require(store, req.file, "pdf")
    out = tmp / "sifreli.pdf"
    r = security.encrypt(path, out, req.user_password, owner_password=req.owner_password,
                         allow_print=req.allow_print, allow_copy=req.allow_copy,
                         allow_modify=req.allow_modify, password=req.passwords.get(req.file))
    name = _out_name(None, f"{_stem(meta)}_sifreli")
    return WorkResult([store.add_file(out, name, job_id=job_id)], r.notes)


def decrypt(store, settings, req, report, tmp: Path, job_id) -> WorkResult:
    meta, path = _require(store, req.file, "pdf")
    out = tmp / "sifresiz.pdf"
    r = security.decrypt(path, out, req.passwords.get(req.file))
    return WorkResult([_single_output(store, req, meta, out, "Şifre kaldırıldı", "sifresiz",
                                      job_id)], r.notes)


def clean_metadata(store, settings, req, report, tmp: Path, job_id) -> WorkResult:
    meta, path = _require(store, req.file, "pdf")
    out = tmp / "temiz.pdf"
    r = security.clean_metadata(path, out, req.passwords.get(req.file))
    notes = r.notes + _protect(store, req, req.file, out)
    return WorkResult([_single_output(store, req, meta, out, "Meta veri temizlendi", "temiz",
                                      job_id)], notes)


def repair(store, settings, req, report, tmp: Path, job_id) -> WorkResult:
    meta = store.get(req.file)
    if meta.kind != "pdf":
        raise UnsupportedFileError(Path(meta.name), "PDF")
    out = tmp / "onarilmis.pdf"
    r = security.repair(store.path(req.file), out, req.passwords.get(req.file))
    notes = r.notes + _protect(store, req, req.file, out)
    return WorkResult([_single_output(store, req, meta, out, "Onarıldı", "onarilmis", job_id)],
                      notes)


WINGET_IDS = {"libreoffice": "TheDocumentFoundation.LibreOffice"}
INSTALL_TIMEOUT_S = 45 * 60


def install_engine(store, settings, req, report, tmp: Path, job_id) -> WorkResult:
    """LibreOffice'i winget ile kurar (uygulamaya gömülmez: ~350 MB). Windows kurulum için izin
    (UAC) isteyebilir. Kurulum bitince motorlar yeniden taranır."""
    from pdfatolye import proc

    winget = shutil.which("winget")
    if not winget:
        raise PdfAtolyeError("winget bulunamadı. Microsoft Store'dan \"Uygulama Yükleyicisi\"ni "
                             "güncelle ya da LibreOffice'i libreoffice.org'dan indirip kur.")
    report(0.05, "LibreOffice indiriliyor ve kuruluyor (birkaç dakika; Windows izin "
                 "isteyebilir)")
    try:
        done = proc.run([winget, "install", "--id", WINGET_IDS[req.engine], "--exact",
                         "--silent", "--accept-package-agreements",
                         "--accept-source-agreements", "--disable-interactivity"],
                        timeout=INSTALL_TIMEOUT_S)
    except proc.TimedOut:
        raise PdfAtolyeError("LibreOffice kurulumu 45 dakikada bitmedi; yeniden dene.") from None
    text = (done.stdout or b"").decode("utf-8", "replace") + \
        (done.stderr or b"").decode("utf-8", "replace")
    lines = [ln.strip() for ln in re.split(r"[\r\n]+", text) if ln.strip()]
    if done.returncode != 0 and not any("already installed" in ln.lower() or
                                        "zaten yüklü" in ln.lower() for ln in lines):
        detail = lines[-1] if lines else ""
        raise PdfAtolyeError(f"LibreOffice kurulamadı (winget çıkış kodu {done.returncode})."
                             + (f" {detail}" if detail else ""))
    report(0.98, "Motorlar yeniden taranıyor")
    return WorkResult([], ["LibreOffice kuruldu. Word / Excel / PowerPoint → PDF artık "
                           "kullanılabilir."])
