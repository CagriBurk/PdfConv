"""Gerçek tarayıcıyla baskı testleri. Edge/Chrome yoksa atlanır."""

from pathlib import Path

import pymupdf
import pytest

from pdfatolye import engines
from pdfatolye.convert.markdown import MarkdownPrinter, MdOptions
from pdfatolye.convert.markdown.render import BrowserNotFoundError
from pdfatolye.settings import Settings
from tests.fixtures import make_fixtures as fx

BROWSER = engines.detect_browser(Settings()).path
pytestmark = pytest.mark.skipif(not BROWSER, reason="Edge/Chrome yok")


@pytest.fixture(scope="module")
def printer(tmp_path_factory):
    vault = tmp_path_factory.mktemp("kasa")
    (vault / "ekler").mkdir()
    fx.photo_jpeg(vault / "ekler" / "devre.jpg", (600, 300))
    with MarkdownPrinter(BROWSER, vault) as p:
        p.vault_dir = vault
        yield p


def write(path: Path, text: str) -> Path:
    path.write_text(text, encoding="utf-8")
    return path


def text_of(pdf: Path) -> list[str]:
    with pymupdf.open(pdf) as doc:
        return [p.get_text().replace("\xa0", " ") for p in doc]


def test_basic_note(printer, tmp_path):
    src = write(tmp_path / "not.md",
                "# Başlık\n\nÇağrı ığdır şöyle: ĞÜŞİÖÇ $E=mc^2$\n\n> [!note]\n> kutu")
    r = printer.convert(src, tmp_path / "not.pdf")
    assert r.warnings == []
    assert r.page_count == 1
    pages = text_of(r.output)
    assert "Çağrı ığdır şöyle: ĞÜŞİÖÇ" in pages[0]
    assert "1 / 1" in pages[0]  # sayfa numarası
    with pymupdf.open(r.output) as doc:
        assert doc.metadata["title"] == "Başlık"
        assert doc.metadata["creator"] == "PDF Atölyesi"
        fonts = {f[3] for f in doc[0].get_fonts()}
    assert any("KaTeX" in f for f in fonts)  # formül KaTeX fontuyla çizildi


def test_math_error_reported_with_line(printer, tmp_path):
    src = write(tmp_path / "hata.md", "doğru $x$\n\nyanlış $\\frac{1}{$ burada")
    r = printer.convert(src, tmp_path / "hata.pdf")
    assert len(r.warnings) == 1
    assert r.warnings[0].startswith("Satır 3: formül çizilemedi")
    assert "\\frac{1}{" in text_of(r.output)[0]  # ham TeX görünür kalır


def test_toc_page_numbers_and_bookmarks(printer, tmp_path):
    src = write(tmp_path / "toc.md",
                "# Bir\n\nmetin\n\n\\newpage\n\n## İki $x^2$\n\n\\newpage\n\n# Üç\n")
    r = printer.convert(src, tmp_path / "toc.pdf", MdOptions(toc=True))
    pages = text_of(r.output)
    assert r.page_count == 4  # içindekiler + 3 sayfa
    assert "İçindekiler" in pages[0]
    toc_lines = [line.strip() for line in pages[0].splitlines()]
    assert toc_lines[toc_lines.index("Bir") + 1] == "2"
    assert toc_lines[toc_lines.index("Üç") + 1] == "4"
    with pymupdf.open(r.output) as doc:
        assert doc.get_toc(simple=True) == [[1, "Bir", 2], [2, "İki x^2", 3], [1, "Üç", 4]]


def test_cover_and_front_matter(printer, tmp_path):
    src = write(tmp_path / "kapak.md",
                "---\ntitle: Ders Notu\nauthor: Ç. B.\ndate: 2026-10-31\npdf:\n  kapak: true\n"
                "  kagit: A5\n  sayfa_no: false\n---\n# Giriş\n")
    r = printer.convert(src, tmp_path / "kapak.pdf")
    pages = text_of(r.output)
    assert "Ders Notu" in pages[0] and "31 Ekim 2026" in pages[0]
    assert "1 / 2" not in pages[0]
    with pymupdf.open(r.output) as doc:
        w, h = doc[0].rect.width, doc[0].rect.height
    assert abs(w - 420) < 2 and abs(h - 595) < 2  # A5 (Chromium 1 pt yuvarlayabiliyor)


def test_landscape_and_theme(printer, tmp_path):
    src = write(tmp_path / "y.md", "metin")
    r = printer.convert(src, tmp_path / "y.pdf", MdOptions(landscape=True, theme="rapor"))
    with pymupdf.open(r.output) as doc:
        assert doc[0].rect.width > doc[0].rect.height


def test_vault_image_embedded(printer, tmp_path):
    src = write(tmp_path / "resim.md", "![[devre.jpg|200]]")
    r = printer.convert(src, tmp_path / "resim.pdf")
    assert r.warnings == []
    with pymupdf.open(r.output) as doc:
        assert len(doc[0].get_images()) == 1


def test_remote_resources_are_blocked(printer, tmp_path):
    src = write(tmp_path / "uzak.md", "![](https://example.invalid/a.png)\n\nmetin")
    r = printer.convert(src, tmp_path / "uzak.pdf")
    assert any("Uzak kaynak" in w and "example.invalid" in w for w in r.warnings)


def test_cp1254_file_is_read(printer, tmp_path):
    src = tmp_path / "eski.md"
    src.write_bytes("Şirin ığdır".encode("cp1254"))
    r = printer.convert(src, tmp_path / "eski.pdf")
    assert any("Windows-1254" in w for w in r.warnings)
    assert "Şirin ığdır" in text_of(r.output)[0]


def test_overwrites_previous_export(printer, tmp_path):
    src = write(tmp_path / "a.md", "bir")
    out = tmp_path / "a.pdf"
    printer.convert(src, out)
    write(src, "iki")
    printer.convert(src, out)
    assert "iki" in text_of(out)[0]


def test_missing_browser_is_a_clear_error():
    with pytest.raises(BrowserNotFoundError, match="Edge veya Chrome"):
        MarkdownPrinter("C:/yok/msedge.exe")
