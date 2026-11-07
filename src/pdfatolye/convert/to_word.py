"""PDF → Word (.docx), pdf2docx ile.

pdf2docx'in `Converter.convert` çağrısı tek parça çalışır: ilerleme bildirmez, iptal edilemez ve
sayfa hatalarını yalnızca günlüğe yazıp geçer. Burada aynı dört aşama (aç → belgeyi çözümle →
sayfaları çözümle → docx yaz) sayfa sayfa yürütülür; her sayfadan önce `on_progress` çağrılır
(iş iptal edildiyse oradan `Cancelled` yükselir) ve atlanan sayfalar uyarı olarak döner.
Bu, pdf2docx'in iç yapısına bağlıdır: sürüm `pyproject.toml`'da 0.5.x'e sabitlenmiştir.
"""

from __future__ import annotations

import logging
import warnings
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

from pdfatolye.core.pdfio import atomic_output, opened
from pdfatolye.core.ranges import format_pages, parse_ranges
from pdfatolye.errors import PdfAtolyeError

Progress = Callable[[float, str], None]
log = logging.getLogger("pdfatolye.word")

# Aşamaların toplam süredeki yaklaşık payları (ölçüm: metin + tablo ağırlıklı belgeler).
_ANALYZE, _PARSE, _WRITE = 0.35, 0.45, 0.15


@dataclass
class WordResult:
    output: Path
    page_count: int
    warnings: list[str] = field(default_factory=list)


def _import_pdf2docx():
    """pdf2docx içe aktarılırken kök günlükleyiciye `basicConfig` uygular (stderr'e INFO). Bu,
    uygulamanın günlük düzenini değiştirmesin diye kök günlükleyici eski hâline döndürülür.
    Eski `fitz` adını kullandığı için PyMuPDF'in verdiği uyarı da bastırılır."""
    root = logging.getLogger()
    handlers, level = list(root.handlers), root.level
    try:
        with warnings.catch_warnings():
            warnings.filterwarnings("ignore", message=".*fitz.*", category=FutureWarning)
            from docx import Document
            from pdf2docx import Converter
            from pdf2docx.font.Fonts import Fonts
            from pdf2docx.page.RawPageFactory import RawPageFactory
    finally:
        for h in root.handlers[:]:
            if h not in handlers:
                root.removeHandler(h)
        root.setLevel(level)
        if _quiet_pdf2docx not in root.filters:
            root.addFilter(_quiet_pdf2docx)
    return Converter, Document, Fonts, RawPageFactory


def _quiet_pdf2docx(record: logging.LogRecord) -> bool:
    """pdf2docx her sayfa için kök günlükleyiciye yazar ("Ignore Line ... due to overlap"); bunlar
    terminale ve günlüğe dökülmesin. Sayfa hataları burada ayrıca yakalanıp uyarı olarak döner."""
    return "pdf2docx" not in record.pathname.replace("\\", "/").split("/")


def pdf_to_word(
    input: Path,
    output: Path,
    *,
    spec: str = "",
    password: str | None = None,
    on_progress: Progress | None = None,
) -> WordResult:
    Converter, Document, Fonts, RawPageFactory = _import_pdf2docx()
    report = on_progress or (lambda f, m: None)
    input, output = Path(input), Path(output)

    # Şifre ve bozuk dosya hataları uygulamanın Türkçe mesajlarıyla çıksın.
    with opened(input, password) as doc:
        indexes = list(dict.fromkeys(parse_ranges(spec, doc.page_count)))
        has_text = any(doc[i].get_text("text").strip() for i in indexes[:50])

    report(0.02, "Belge açılıyor")
    cv = Converter(str(input), password=password)
    try:
        settings = cv.default_settings
        cv.load_pages(pages=indexes)
        pages = [p for p in cv.pages if not p.skip_parsing]
        total = len(pages)
        failed: list[int] = []

        # 2. aşama (pdf2docx `Pages.parse`): ham sayfa, yazı tipleri, kenar boşluğu, bölümler.
        fonts = Fonts.extract(cv.fitz_doc)
        for n, page in enumerate(pages):
            report(0.05 + _ANALYZE * n / total, f"Sayfa yapısı çözümleniyor: {n + 1}/{total}")
            raw = RawPageFactory.create(page_engine=cv.fitz_doc[page.id], backend="PyMuPDF")
            raw.restore(**settings)
            raw.clean_up(**settings)
            raw.process_font(fonts)
            page.width, page.height = raw.width, raw.height
            page.float_images.reset().extend(raw.blocks.floating_image_blocks)
            raw.margin = page.margin = raw.calculate_margin(**settings)
            page.sections.extend(raw.parse_section(**settings))

        # 3. aşama: paragraf, tablo, resim.
        start = 0.05 + _ANALYZE
        for n, page in enumerate(pages):
            report(start + _PARSE * n / total, f"Sayfa dönüştürülüyor: {n + 1}/{total}")
            try:
                page.parse(**settings)
            except Exception:  # pdf2docx'in kendi davranışı: sayfayı atla, devam et
                log.exception("PDF → Word: %d. sayfa çözümlenemedi", page.id + 1)
                failed.append(page.id)

        # 4. aşama: Word belgesi.
        start += _PARSE
        docx = Document()
        done = [p for p in pages if p.finalized]
        if not done:
            raise PdfAtolyeError("Hiçbir sayfa Word'e dönüştürülemedi.")
        for n, page in enumerate(done):
            report(start + _WRITE * n / len(done), f"Word belgesi yazılıyor: {n + 1}/{len(done)}")
            try:
                page.make_docx(docx)
            except Exception:
                log.exception("PDF → Word: %d. sayfa yazılamadı", page.id + 1)
                failed.append(page.id)
        report(0.97, "Kaydediliyor")
        with atomic_output(output) as tmp:
            docx.save(str(tmp))
    finally:
        cv.close()

    warnings = []
    if failed:
        warnings.append(f"Şu sayfalar dönüştürülemedi ve atlandı: {format_pages(sorted(failed))}.")
    if not has_text:
        warnings.append("Bu PDF'te metin yok (taranmış olabilir): sayfalar Word'e resim olarak "
                        "aktarıldı. Düzenlenebilir yazı için önce OCR yap, sonra yeniden çevir.")
    return WordResult(output, total, warnings)
