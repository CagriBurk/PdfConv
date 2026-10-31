"""Office / HTML / metin → PDF. Gerçek LibreOffice ve tarayıcı yoksa ilgili testler atlanır."""

import zipfile
from pathlib import Path

import psutil
import pymupdf
import pytest

from pdfatolye import engines
from pdfatolye.convert import office
from pdfatolye.convert.html import print_html, print_text
from pdfatolye.settings import Settings
from tests.fixtures import make_fixtures as fx

SOFFICE = engines.detect_libreoffice(Settings()).path
BROWSER = engines.detect_browser(Settings()).path
needs_lo = pytest.mark.skipif(not SOFFICE, reason="LibreOffice yok")
needs_browser = pytest.mark.skipif(not BROWSER, reason="Edge/Chrome yok")



def text_of(pdf: Path) -> str:
    with pymupdf.open(pdf) as doc:
        return "\n".join(p.get_text() for p in doc).replace("\xa0", " ")


def soffice_processes() -> int:
    return sum(1 for p in psutil.process_iter(["name"])
               if (p.info["name"] or "").lower().startswith("soffice"))


# --- font çıkarma (LibreOffice gerekmez) -------------------------------------------------


def test_requested_fonts_from_docx(tmp_path):
    path = fx.docx(tmp_path / "a.docx", ["metin"], font="Yokfont Sans")
    assert office.requested_fonts(path) == {"Yokfont Sans"}


def test_requested_fonts_theme_and_pptx(tmp_path):
    path = tmp_path / "s.pptx"
    with zipfile.ZipFile(path, "w") as zf:
        zf.writestr("ppt/slides/slide1.xml",
                    '<a:latin typeface="Aptos"/><a:latin typeface="+mn-lt"/>')
        zf.writestr("ppt/theme/theme1.xml",
                    "<a:majorFont><a:latin typeface=\"Aptos Display\"/></a:majorFont>"
                    "<a:minorFont><a:latin typeface=\"Aptos\"/></a:minorFont>")
    assert office.requested_fonts(path) == {"Aptos", "Aptos Display"}


def test_font_warning_only_for_unavailable(tmp_path, monkeypatch):
    path = fx.docx(tmp_path / "a.docx", ["x"], font="Calibri")
    monkeypatch.setattr(office, "installed_fonts", lambda: {"calibri", "arial"})
    assert office.font_warnings(path, set(), "a.docx") == []
    path = fx.docx(tmp_path / "b.docx", ["x"], font="Yokfont Sans")
    [w] = office.font_warnings(path, {"liberationsans"}, "b.docx")
    assert "Yokfont Sans" in w and "'b.docx'" in w


def test_requested_fonts_on_non_zip(tmp_path):
    p = tmp_path / "x.docx"
    p.write_bytes(b"bozuk")
    assert office.requested_fonts(p) == set()


def test_missing_libreoffice_is_clear(tmp_path):
    src = fx.docx(tmp_path / "a.docx", ["x"])
    with pytest.raises(office.LibreOfficeNotFoundError, match="winget"):
        office.convert_office(src, tmp_path / "a.pdf", soffice=None)


def test_unsupported_extension(tmp_path):
    src = tmp_path / "a.xyz"
    src.write_text("x")
    with pytest.raises(office.OfficeConversionError, match="desteklenen"):
        office.convert_office(src, tmp_path / "a.pdf", soffice=__file__)


# --- gerçek dönüşüm ----------------------------------------------------------------------


@needs_lo
def test_docx_turkish_unicode_path_and_pages(tmp_path):
    folder = tmp_path / "Çağrı'nın ödevleri"
    folder.mkdir()
    src = fx.docx(folder / "Ödev 1 — Işık.docx", [fx.TURKISH, "İkinci sayfa"], page_breaks=True)
    r = office.convert_office(src, folder / "Ödev 1.pdf", soffice=SOFFICE)
    assert r.page_count == 2
    assert fx.TURKISH in text_of(r.output)
    assert r.warnings == []


@needs_lo
def test_missing_font_is_reported(tmp_path):
    src = fx.docx(tmp_path / "f.docx", ["metin"], font="Yokfont Sans Pro")
    r = office.convert_office(src, tmp_path / "f.pdf", soffice=SOFFICE)
    assert len(r.warnings) == 1 and "Yokfont Sans Pro" in r.warnings[0]


@needs_lo
def test_rtf_and_pdfa(tmp_path):
    src = fx.rtf(tmp_path / "a.rtf", "Şeker ğüşıöç")
    r = office.convert_office(src, tmp_path / "a.pdf", soffice=SOFFICE,
                              pdfa=True)
    assert "Şeker ğüşıöç" in text_of(r.output)
    with pymupdf.open(r.output) as doc:
        assert "pdfaid" in (doc.get_xml_metadata() or "")


@needs_lo
def test_broken_document_gives_clear_error(tmp_path):
    src = tmp_path / "bozuk.docx"
    src.write_bytes(b"PK\x03\x04 bu bir docx degil")
    with pytest.raises(office.OfficeConversionError, match="'bozuk.docx' dönüştürülemedi"):
        office.convert_office(src, tmp_path / "b.pdf", soffice=SOFFICE)


@needs_lo
def test_timeout_kills_libreoffice(tmp_path):
    src = fx.docx(tmp_path / "t.docx", ["x"])
    before = soffice_processes()
    with pytest.raises(office.OfficeConversionError, match="zaman aşımı"):
        office.convert_office(src, tmp_path / "t.pdf", soffice=SOFFICE,
                              timeout=0.3)
    assert soffice_processes() <= before


@needs_browser
def test_html_offline_and_text(tmp_path):
    page = tmp_path / "s.html"
    page.write_text('<h1>Başlık ğüş</h1><img src="https://example.invalid/x.png">',
                    encoding="utf-8")
    r = print_html(page, tmp_path / "s.pdf", browser_path=BROWSER)
    assert "Başlık ğüş" in text_of(r.output)
    assert any("example.invalid" in w for w in r.warnings)

    txt = tmp_path / "not.txt"
    content = "satır 1\n    girintili *yıldız* # değil başlık\n<b>etiket</b>"
    txt.write_bytes(content.encode("cp1254"))
    r = print_text(txt, tmp_path / "not.pdf", browser_path=BROWSER)
    body = text_of(r.output)
    # Girinti korunur (metin çıkarma boşluk sayısını tam vermeyebilir); markdown yorumlanmaz.
    assert "   girintili *yıldız* # değil başlık" in body
    assert "<b>etiket</b>" in body
    assert any("Windows-1254" in w for w in r.warnings)


@needs_lo
def test_batch_one_call_and_broken_file_does_not_stop_others(tmp_path):
    good1 = fx.docx(tmp_path / "bir.docx", ["Birinci ğ"])
    bad = tmp_path / "bozuk.docx"
    bad.write_bytes(b"PK\x03\x04 bozuk")
    good2 = fx.rtf(tmp_path / "iki.rtf", "İkinci ş")
    items = [office.OfficeItem(p, tmp_path / f"{p.stem}.pdf", p.name) for p in (good1, bad, good2)]
    progress: list[int] = []
    results = office.convert_office_many(items, soffice=SOFFICE,
                                         on_progress=lambda n, t: progress.append(n))
    assert isinstance(results[0], office.OfficeResult)
    assert isinstance(results[1], office.OfficeConversionError)
    assert "'bozuk.docx'" in str(results[1])
    assert isinstance(results[2], office.OfficeResult)
    assert "İkinci ş" in text_of(results[2].output)
    assert progress == [1, 2, 3]
    assert soffice_processes() == 0  # arkada süreç kalmadı


@needs_lo
def test_repeated_conversions_do_not_hang(tmp_path):
    # LibreOffice 26.8'de aynı profil ikinci çağrıda takılıyordu (tuzak #26).
    for i in range(3):
        src = fx.docx(tmp_path / f"t{i}.docx", [f"Deneme {i}"])
        r = office.convert_office(src, tmp_path / f"t{i}.pdf", soffice=SOFFICE, timeout=60)
        assert r.page_count == 1