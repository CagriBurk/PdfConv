"""HTML ve düz metin → PDF (kurulu Edge/Chrome ile, çevrimdışı).

Ağ erişimi kapalıdır: yalnızca file: ve data: adresleri yüklenir; uzak kaynaklar uyarı olur.
"""

from __future__ import annotations

import html as html_lib
import tempfile
from dataclasses import dataclass, field
from pathlib import Path

import pymupdf

from pdfatolye.convert.markdown.render import BrowserNotFoundError
from pdfatolye.core.pdfio import atomic_output

TIMEOUT_MS = 60_000
FOOTER = (
    '<div style="width:100%;font-size:8pt;color:#78716c;text-align:center;'
    "font-family:'Segoe UI',Arial,sans-serif;\">"
    '<span class="pageNumber"></span> / <span class="totalPages"></span></div>'
)

TEXT_TEMPLATE = """<!doctype html><html lang="tr"><head><meta charset="utf-8">
<title>{title}</title><style>
body {{ margin: 0; font: 10.5pt/1.45 "Segoe UI", Arial, sans-serif; color: #1c1917; }}
pre {{ margin: 0; font: inherit; white-space: pre-wrap; overflow-wrap: anywhere; }}
</style></head><body><pre>{body}</pre></body></html>"""


@dataclass
class HtmlResult:
    output: Path
    page_count: int
    warnings: list[str] = field(default_factory=list)


def read_text(path: Path, warnings: list[str], name: str) -> str:
    raw = path.read_bytes()
    try:
        return raw.decode("utf-8-sig")
    except UnicodeDecodeError:
        warnings.append(f"'{name}' UTF-8 değil; Windows-1254 (Türkçe) olarak okundu.")
        return raw.decode("cp1254", errors="replace")


def print_html(
    source: Path,
    output: Path,
    *,
    browser_path: str | None,
    paper: str = "A4",
    landscape: bool = False,
    margin_mm: float = 15,
    page_numbers: bool = True,
    display_name: str | None = None,
) -> HtmlResult:
    """HTML dosyasını basar. Göreli resim/CSS yolları dosyanın klasörüne göre çözülür."""
    if not browser_path or not Path(browser_path).is_file():
        raise BrowserNotFoundError()
    from playwright.sync_api import sync_playwright

    name = display_name or Path(source).name
    warnings: list[str] = []
    blocked: list[str] = []
    with sync_playwright() as pw:
        browser = pw.chromium.launch(executable_path=browser_path, headless=True)
        try:
            page = browser.new_page()

            def route(r):
                url = r.request.url
                if url.startswith(("file:", "data:", "about:")):
                    r.continue_()
                else:
                    blocked.append(url)
                    r.abort()

            page.route("**/*", route)
            page.goto(Path(source).resolve().as_uri(), wait_until="load", timeout=TIMEOUT_MS)
            page.evaluate("document.fonts.ready.then(() => true)")
            pdf_bytes = page.pdf(
                format=paper, landscape=landscape, print_background=True, outline=True,
                tagged=True, display_header_footer=page_numbers,
                header_template="<span></span>", footer_template=FOOTER,
                margin={s: f"{margin_mm}mm" for s in ("top", "right", "left")}
                | {"bottom": f"{max(margin_mm, 14 if page_numbers else 0)}mm"},
            )
        finally:
            browser.close()

    for url in dict.fromkeys(blocked):
        warnings.append(f"'{name}': uzak kaynak çevrimdışı olduğu için yüklenmedi: {url}")
    with pymupdf.open(stream=pdf_bytes, filetype="pdf") as doc:
        pages = doc.page_count
        doc.set_metadata({"title": Path(name).stem, "creator": "PDF Atölyesi"})
        with atomic_output(Path(output)) as tmp:
            doc.save(tmp, garbage=3, deflate=True)
    return HtmlResult(Path(output), pages, warnings)


def print_text(source: Path, output: Path, *, browser_path: str | None,
               display_name: str | None = None, **kwargs) -> HtmlResult:
    """Düz metni satır sonlarını koruyarak basar (Markdown olarak yorumlamaz)."""
    name = display_name or Path(source).name
    warnings: list[str] = []
    text = read_text(Path(source), warnings, name).replace("\r\n", "\n")
    with tempfile.TemporaryDirectory(prefix="pa-txt-") as tmp:
        page = Path(tmp) / "metin.html"
        page.write_text(TEXT_TEMPLATE.format(title=html_lib.escape(Path(name).stem),
                                             body=html_lib.escape(text)), encoding="utf-8")
        result = print_html(page, output, browser_path=browser_path, display_name=name, **kwargs)
    result.warnings[:0] = warnings
    return result
