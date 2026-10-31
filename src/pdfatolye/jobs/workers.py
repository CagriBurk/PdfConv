"""İş türlerinin gerçek işi. Çekirdek fonksiyonları depo dosyalarıyla çağırır.

Her çalışan: geçici klasöre (kısa yol) yazar, sonuçları depoya ekler, `WorkResult` döndürür.
"""

from __future__ import annotations

import shutil
import tempfile
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

from pdfatolye import engines
from pdfatolye.convert.markdown.render import BrowserNotFoundError
from pdfatolye.core import content, images, pages
from pdfatolye.core.pdfio import safe_filename
from pdfatolye.errors import EncryptedPdfError, PdfAtolyeError, UnsupportedFileError
from pdfatolye.storage import FileMeta

Report = Callable[[float, str], None]


@dataclass
class WorkResult:
    outputs: list[FileMeta]
    warnings: list[str] = field(default_factory=list)


def _stem(meta: FileMeta) -> str:
    return Path(meta.name).stem


def _out_name(requested: str | None, default: str, ext: str = ".pdf") -> str:
    name = safe_filename(Path(requested).stem if requested else default, fallback="cikti")
    return name + ext


def _require(store, file_id: str, kind: str) -> tuple[FileMeta, Path]:
    meta = store.get(file_id)
    if meta.kind != kind:
        raise UnsupportedFileError(Path(meta.name), {"pdf": "PDF", "image": "resim",
                                                     "markdown": "Markdown"}.get(kind, kind))
    return meta, store.path(file_id)


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
    pages.compose(paths, manifest, out, passwords=[req.passwords.get(f) for f in order],
                  keep_bookmarks=req.keep_bookmarks, bookmark_titles=[_stem(m) for m in metas])
    report(0.9, "Kaydediliyor")
    if req.target == "version":
        return WorkResult([store.new_version(req.base_file, out, "Sayfa düzenleme")])
    base = _stem(metas[0]) if metas else "belge"
    name = _out_name(req.name, f"{base}_duzenlenmis")
    return WorkResult([store.add_file(out, name, job_id=job_id)])


def merge(store, settings, req, report, tmp: Path, job_id) -> WorkResult:
    metas, paths = zip(*(_require(store, f, "pdf") for f in req.files), strict=True)
    report(0.2, "Birleştiriliyor")
    out = tmp / "birlesik.pdf"
    pages.merge(list(paths), out, passwords=[req.passwords.get(f) for f in req.files],
                bookmark_per_file=req.bookmark_per_file,
                bookmark_titles=[_stem(m) for m in metas])
    name = _out_name(req.name, f"{_stem(metas[0])}_birlesik")
    return WorkResult([store.add_file(out, name, job_id=job_id)])


def split(store, settings, req, report, tmp: Path, job_id) -> WorkResult:
    meta, path = _require(store, req.file, "pdf")
    report(0.1, "Bölünüyor")
    parts = pages.split(path, tmp / "parcalar", mode=req.mode, every=req.every, spec=req.spec,
                        password=req.passwords.get(req.file), name_stem=_stem(meta))
    outputs = []
    for i, part in enumerate(parts, start=1):
        outputs.append(store.add_file(part, part.name, job_id=job_id))
        report(0.1 + 0.9 * i / len(parts), f"{i}/{len(parts)} parça")
    return WorkResult(outputs)


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
    return WorkResult(outputs)


def md_to_pdf(store, settings, req, report, tmp: Path, job_id) -> WorkResult:
    from pdfatolye.convert.markdown import MarkdownPrinter, MdOptions

    work = tmp / "md"
    work.mkdir()
    if req.file:
        meta, path = _require(store, req.file, "markdown")
        name = meta.name
        text = req.text if req.text is not None else path.read_text(encoding="utf-8-sig",
                                                                     errors="replace")
    else:
        name, text = req.name, req.text or ""
    md_name = safe_filename(Path(name).stem, fallback="belge") + ".md"
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
    with MarkdownPrinter(browser, settings.vault_path) as printer:
        report(0.4, "Basılıyor")
        result = printer.convert(source, tmp / "cikti.pdf",
                                 MdOptions(**req.options.model_dump()))
    meta = store.add_file(result.output, Path(md_name).stem + ".pdf", job_id=job_id)
    return WorkResult([meta], result.warnings)


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
        printer = print_html if m.kind == "html" else print_text
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
                    bookmark_titles=[_stem(m) for m, _ in converted])
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
    kinds = {op.type for op in req.ops}
    note = _APPLY_NOTES.get(next(iter(kinds)), "") if len(kinds) == 1 else ""
    if req.target == "version":
        return WorkResult([store.new_version(req.file, out, note or "İçerik düzenleme")],
                          result.warnings)
    name = _out_name(req.name, f"{_stem(meta)}_duzenlenmis")
    return WorkResult([store.add_file(out, name, job_id=job_id)], result.warnings)
