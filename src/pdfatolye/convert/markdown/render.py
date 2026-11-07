"""HTML → PDF: kurulu Edge/Chrome'u Playwright ile başsız çalıştırır.

Akış: md → HTML (geçici klasöre, KaTeX kopyasıyla) → tarayıcıda aç → formüller çizilsin,
resimler ve fontlar yüklensin → page.pdf(). İçindekiler istendiyse iki geçiş yapılır: ilk
baskının yer imlerinden başlıkların sayfaları okunur, numaralar yazılıp yeniden basılır.

Not güvenilir sayılmaz: içerik güvenlik politikası (nonce) notun içindeki betikleri ve gömülü
çerçeveleri durdurur; ağ kapalıdır, yalnızca KaTeX dosyaları ile çözülen resimler açılır (bkz.
`browser.py`). Engellenen kaynaklar uyarı olarak raporlanır.
"""

from __future__ import annotations

import re
import secrets
import shutil
import tempfile
import unicodedata
from dataclasses import dataclass, field
from pathlib import Path

import pymupdf

from pdfatolye import proc
from pdfatolye.convert.browser import (
    OfflineBrowser,
    blocked_warnings,
    file_url_path,
    new_offline_page,
)
from pdfatolye.convert.markdown.document import (
    ASSETS,
    MdOptions,
    build_html,
    print_csp,
    resolve_options,
    toc_headings,
)
from pdfatolye.convert.markdown.parser import Heading, parse_markdown
from pdfatolye.core.pdfio import atomic_output
from pdfatolye.core.textio import decode_text
from pdfatolye.errors import PdfAtolyeError

RENDER_TIMEOUT_MS = 90_000
# Tek notun bütün baskısının (iki geçişli içindekiler dahil) üst süresi; dolunca tarayıcı
# öldürülür, sonraki not için yeniden açılır.
PRINT_TIMEOUT_S = 300
FOOTER = (
    '<div style="width:100%;font-size:8pt;color:#78716c;text-align:center;'
    "font-family:'Segoe UI',Arial,sans-serif;\">"
    '<span class="pageNumber"></span> / <span class="totalPages"></span></div>'
)
EMPTY = "<span></span>"


class BrowserNotFoundError(PdfAtolyeError):
    def __init__(self) -> None:
        super().__init__("Edge veya Chrome bulunamadı; Markdown → PDF için biri gerekli. "
                         "Ayarlar sayfasındaki motor durumuna bak.")


@dataclass
class MdResult:
    output: Path
    page_count: int
    warnings: list[str] = field(default_factory=list)


def read_markdown(path: Path, warnings: list[str]) -> str:
    text, note = decode_text(Path(path).read_bytes(), Path(path).name)
    if note:
        warnings.append(note)
    return text


def _norm(text: str) -> str:
    text = unicodedata.normalize("NFKC", text).casefold()
    return re.sub(r"\s+", " ", text).strip()


def match_heading_pages(headings: list[Heading], outline: list[list]) -> list[int | None]:
    """Tarayıcının ürettiği yer imlerini (sırayla tüm h1–h6) başlıklarımızla eşleştirir.

    Sayılar tutuyorsa sırayla eşler (en güvenilir yol; formüllü başlıkların metni farklı
    görünebilir). Tutmuyorsa metin eşleştirmesine düşer.
    """
    if len(outline) == len(headings):
        return [entry[2] for entry in outline]
    pages: list[int | None] = []
    j = 0
    for h in headings:
        page = None
        for k in range(j, len(outline)):
            if _norm(outline[k][1]) == _norm(h.text):
                page, j = outline[k][2], k + 1
                break
        pages.append(page)
    return pages


class MarkdownPrinter:
    """Bir tarayıcıyı açık tutar; çok dosyayı art arda hızlıca basmak için yeniden kullanılır.

        with MarkdownPrinter(browser_path) as p:
            p.convert(Path("not.md"), Path("not.pdf"))
    """

    def __init__(self, browser_path: str | None, vault: Path | None = None,
                 *, confine: bool = False, user_defaults: MdOptions | None = None) -> None:
        """`confine=True`: notun resimleri yalnızca not klasöründen ve kasadan okunur (arayüzden
        gelen not). Komut satırında kullanıcı kendi notunu bastığı için göreli `../` serbesttir.
        `user_defaults`: Ayarlar'daki varsayılan tema / kağıt (ön bilgi ve seçim önce gelir)."""
        if not browser_path or not Path(browser_path).is_file():
            raise BrowserNotFoundError()
        self.browser_path = browser_path
        self.vault = vault
        self.confine = confine
        self.user_defaults = user_defaults
        self._ob = OfflineBrowser(browser_path)
        self._tmp: tempfile.TemporaryDirectory | None = None

    def __enter__(self) -> MarkdownPrinter:
        # Kısa yol: uzun klasör yolları Windows'ta sorun çıkarıyor (PLAN.md tuzak #17).
        self._tmp = tempfile.TemporaryDirectory(prefix="pa-md-")
        shutil.copytree(ASSETS / "katex", Path(self._tmp.name) / "katex")
        try:
            self._ob.start()
        except Exception:
            self._tmp.cleanup()
            raise
        return self

    def __exit__(self, *exc) -> None:
        try:
            self._ob.stop()
        finally:
            if self._tmp:
                self._tmp.cleanup()

    def convert(
        self, source: Path, output: Path, options: MdOptions | None = None, *, html_out=None
    ) -> MdResult:
        from playwright.sync_api import TimeoutError as PlaywrightTimeout

        self._ob.ensure()  # önceki not takılıp öldürüldüyse yeniden aç
        try:
            with self._ob.guard(PRINT_TIMEOUT_S):
                return self._convert(source, output, options, html_out=html_out)
        except (proc.TimedOut, PlaywrightTimeout):
            raise PdfAtolyeError(f"'{Path(source).name}' {PRINT_TIMEOUT_S} saniyede "
                                 "basılamadı (zaman aşımı). Not çok büyük ya da bir formül "
                                 "tarayıcıyı kilitlemiş olabilir.") from None

    def _convert(self, source: Path, output: Path, options: MdOptions | None, *, html_out
                 ) -> MdResult:
        source = Path(source)
        warnings: list[str] = []
        text = read_markdown(source, warnings)
        # Tarayıcı yalnızca buradan geçen resimleri ve geçici klasörü (KaTeX, belge) açabilir.
        images: set[Path] = set()

        def url_for(path: Path) -> str:
            images.add(path.resolve())
            return path.as_uri()

        parse = dict(base_dir=source.parent, vault=self.vault, url_for=url_for,
                     confine=self.confine)
        # Satır sonu ayarı ayrıştırmadan önce lazım: ön bilgi için hızlı bir ilk geçiş.
        first = parse_markdown(text, **parse)
        opts = resolve_options(options or MdOptions(), first.front_matter, warnings,
                               self.user_defaults)
        parsed = first if opts.breaks else parse_markdown(text, breaks=False, **parse)
        warnings.extend(parsed.warnings)

        tmp_root = Path(self._tmp.name).resolve()
        html_path = tmp_root / "belge.html"
        nonce = secrets.token_urlsafe(16)
        html_path.write_text(build_html(parsed, opts, csp=print_csp(nonce), nonce=nonce),
                             encoding="utf-8")
        if html_out:
            Path(html_out).write_text(build_html(parsed, opts, katex_dir=(
                ASSETS / "katex").as_uri()), encoding="utf-8")

        blocked: list[str] = []
        page = new_offline_page(self._ob.browser,
                                lambda p: p.is_relative_to(tmp_root) or p in images, blocked)
        try:
            page.goto(html_path.as_uri(), wait_until="load", timeout=RENDER_TIMEOUT_MS)
            page.wait_for_function("window.__sonuc !== undefined", timeout=RENDER_TIMEOUT_MS)
            result = page.evaluate("window.__sonuc")
            if result.get("fatal"):
                raise PdfAtolyeError(f"Formül motoru başlatılamadı: {result['fatal']}")
            for err in result["errors"]:
                where = f"Satır {err['line']}: " if err.get("line") else ""
                warnings.append(f"{where}formül çizilemedi — {err['message']}")
            for src in result["broken"]:
                if src.startswith(("http:", "https:")):
                    blocked.append(src)  # CSP istek çıkmadan durdurur, `route`'a hiç ulaşmaz
                    continue
                path = file_url_path(src) if src.startswith("file:") else None
                if path is None:
                    warnings.append(f"Resim açılamadı: {src}")
                elif path.resolve() in images:
                    warnings.append(f"Resim açılamadı: {path.name}")
            warnings.extend(blocked_warnings(blocked))

            pdf_kwargs = dict(
                format=opts.paper,
                landscape=bool(opts.landscape),
                print_background=True,
                outline=True,
                tagged=True,
                display_header_footer=bool(opts.page_numbers),
                header_template=EMPTY,
                footer_template=FOOTER,
                margin={side: f"{opts.margin_mm}mm" for side in ("left", "right")}
                | {"top": f"{opts.margin_mm}mm",
                   "bottom": f"{max(opts.margin_mm, 14 if opts.page_numbers else 0)}mm"},
            )
            pdf_bytes = page.pdf(**pdf_kwargs)
            headings = parsed.headings
            heading_pages = self._heading_pages(pdf_bytes, headings, warnings)

            if opts.toc and heading_pages is not None:
                shown = toc_headings(headings, opts.toc_depth)
                index = {id(h): p for h, p in zip(headings, heading_pages, strict=True)}
                numbers = [index.get(id(h)) for h in shown]
                page.evaluate(
                    """nums => document.querySelectorAll('.toc-page').forEach((el, i) => {
                         el.textContent = nums[i] == null ? '' : String(nums[i]); })""",
                    numbers,
                )
                pdf_bytes = page.pdf(**pdf_kwargs)
            elif opts.toc:
                page.evaluate("document.querySelectorAll('.toc-page')"
                              ".forEach(el => el.textContent = '')")
                pdf_bytes = page.pdf(**pdf_kwargs)
        finally:
            page.context.close()

        return MdResult(
            output=self._finish(pdf_bytes, output, parsed, headings, heading_pages),
            page_count=_page_count(pdf_bytes),
            warnings=list(dict.fromkeys(warnings)),
        )

    @staticmethod
    def _heading_pages(pdf_bytes: bytes, headings: list[Heading], warnings: list[str]
                       ) -> list[int | None] | None:
        if not headings:
            return []
        with pymupdf.open(stream=pdf_bytes, filetype="pdf") as doc:
            outline = doc.get_toc(simple=True)
        pages = match_heading_pages(headings, outline)
        if all(p is None for p in pages):
            warnings.append("Başlıkların sayfaları bulunamadı; içindekiler numarasız kaldı.")
            return None
        return pages

    @staticmethod
    def _finish(pdf_bytes, output, parsed, headings, heading_pages) -> Path:
        """Meta veriyi yaz; yer imlerini formüllerin TeX hâliyle temiz başlıklara çevir."""
        front = parsed.front_matter
        author = front.get("author") or front.get("yazar") or ""
        if isinstance(author, list):
            author = ", ".join(map(str, author))
        with pymupdf.open(stream=pdf_bytes, filetype="pdf") as doc:
            doc.set_metadata({
                "title": parsed.title or "",
                "author": str(author),
                "creator": "PDF Atölyesi",
                "producer": "PDF Atölyesi (Chromium + PyMuPDF)",
            })
            if heading_pages and all(p is not None for p in heading_pages):
                toc, prev = [], 0
                for h, p in zip(headings, heading_pages, strict=True):
                    level = max(1, min(h.level, prev + 1))
                    toc.append([level, h.text or "(başlık)", p])
                    prev = level
                doc.set_toc(toc)
            with atomic_output(Path(output)) as tmp:
                doc.save(tmp, garbage=3, deflate=True)
        return Path(output)


def _page_count(pdf_bytes: bytes) -> int:
    with pymupdf.open(stream=pdf_bytes, filetype="pdf") as doc:
        return doc.page_count


def convert_markdown(
    source: Path,
    output: Path,
    options: MdOptions | None = None,
    *,
    browser_path: str | None,
    vault: Path | None = None,
) -> MdResult:
    """Tek dosya için kısayol. Çok dosyada `MarkdownPrinter`'ı doğrudan kullan."""
    with MarkdownPrinter(browser_path, vault) as printer:
        return printer.convert(source, output, options)
