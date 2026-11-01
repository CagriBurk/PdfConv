"""Faz 6: sıkıştırma, şifreleme, meta temizliği, onarım, OCR."""

from pathlib import Path

import pikepdf
import pymupdf
import pytest

from pdfatolye import engines
from pdfatolye.core import compress, ocr, security
from pdfatolye.errors import EncryptedPdfError, PdfAtolyeError
from pdfatolye.settings import Settings
from tests.fixtures import make_fixtures as fx

TESSERACT = engines.detect_tesseract(Settings())
GHOSTSCRIPT = engines.detect_ghostscript(Settings())
needs_ocr = pytest.mark.skipif(not TESSERACT.ok, reason="Tesseract (tur+eng) yok")


# --- sıkıştırma -----------------------------------------------------------------------------


def test_balanced_shrinks_scans(tmp_path: Path):
    src = fx.scanned_turkish(tmp_path / "s.pdf", pages=2, dpi=300, noise=True)
    r = compress.compress(src, tmp_path / "o.pdf", "dengeli")
    assert not r.kept_original
    assert r.after < r.before * 0.6, (r.before, r.after)
    with pymupdf.open(r.output) as doc:
        assert doc.page_count == 2


def test_lossless_keeps_text_and_never_grows(tmp_path: Path):
    src = fx.numbered(tmp_path / "n.pdf", 3)
    r = compress.compress(src, tmp_path / "o.pdf", "kayipsiz")
    assert r.after <= r.before
    assert fx.labels(r.output) == ["Sayfa 1", "Sayfa 2", "Sayfa 3"]


def test_original_kept_when_not_smaller(tmp_path: Path):
    src = tmp_path / "k.pdf"
    doc = pymupdf.open()
    doc.new_page()
    doc.save(src, garbage=4, deflate=True, use_objstms=1)
    r = compress.compress(src, tmp_path / "o.pdf", "guclu")
    assert r.kept_original and r.output.read_bytes() == src.read_bytes()
    assert "orijinal korundu" in r.warnings[-1]


@pytest.mark.skipif(not GHOSTSCRIPT.available, reason="Ghostscript yok")
def test_strong_with_ghostscript(tmp_path: Path):
    src = fx.scanned_turkish(tmp_path / "s.pdf", dpi=300, noise=True)
    r = compress.compress(src, tmp_path / "o.pdf", "guclu", ghostscript=GHOSTSCRIPT.path)
    assert r.after < r.before * 0.5


# --- şifreleme ------------------------------------------------------------------------------


def test_encrypt_is_aes256_with_permissions(tmp_path: Path):
    src = fx.numbered(tmp_path / "n.pdf", 2)
    out = tmp_path / "s.pdf"
    r = security.encrypt(src, out, "açılış1", owner_password="sahip-ş", allow_copy=False)
    assert any("kısıt" in n for n in r.notes)
    with pytest.raises(pikepdf.PasswordError):
        pikepdf.open(out)
    with pikepdf.open(out, password="açılış1") as pdf:
        assert pdf.encryption.R == 6 and pdf.encryption.bits == 256
        assert not pdf.allow.extract and pdf.allow.print_highres
    assert fx.labels(out, password="açılış1") == ["Sayfa 1", "Sayfa 2"]


def test_encrypt_short_password(tmp_path: Path):
    with pytest.raises(PdfAtolyeError, match="en az 4"):
        security.encrypt(fx.numbered(tmp_path / "n.pdf", 1), tmp_path / "o.pdf", "abc")


def test_decrypt_needs_correct_password(tmp_path: Path):
    src = fx.numbered(tmp_path / "s.pdf", 2, password="gizli")
    with pytest.raises(EncryptedPdfError, match="yanlış"):
        security.decrypt(src, tmp_path / "o.pdf", "yanlis")
    security.decrypt(src, tmp_path / "o.pdf", "gizli")
    with pikepdf.open(tmp_path / "o.pdf") as pdf:
        assert not pdf.is_encrypted


def test_decrypt_plain_file_is_reported(tmp_path: Path):
    with pytest.raises(PdfAtolyeError, match="zaten şifresiz"):
        security.decrypt(fx.numbered(tmp_path / "n.pdf", 1), tmp_path / "o.pdf")


def test_owner_only_restrictions_removed(tmp_path: Path):
    src = fx.numbered(tmp_path / "n.pdf", 1)
    restricted = tmp_path / "k.pdf"
    with pikepdf.open(src) as pdf:
        pdf.save(restricted, encryption=pikepdf.Encryption(
            user="", owner="sahip", allow=pikepdf.Permissions(extract=False)))
    r = security.decrypt(restricted, tmp_path / "o.pdf")
    assert "Kısıtlar" in r.notes[0]


# --- meta veri ve onarım --------------------------------------------------------------------


def test_clean_metadata(tmp_path: Path):
    src = fx.with_metadata(tmp_path / "m.pdf")
    out = tmp_path / "o.pdf"
    r = security.clean_metadata(src, out)
    text = r.notes[0]
    for word in ("Author", "XMP", "gömülü dosyalar", "JavaScript"):
        assert word in text, text
    with pikepdf.open(out) as pdf:
        assert "/Author" not in pdf.docinfo
        assert "/Metadata" not in pdf.Root
        assert "/EmbeddedFiles" not in pdf.Root.get("/Names", {})
    assert fx.labels(out) == ["Sayfa 1", "Sayfa 2"]
    assert b"Gizli Yazar" not in out.read_bytes()


def test_repair_broken_xref(tmp_path: Path):
    src = fx.broken(tmp_path / "b.pdf")
    out = tmp_path / "o.pdf"
    r = security.repair(src, out)
    assert r.notes
    assert fx.labels(out) == ["Sayfa 1", "Sayfa 2", "Sayfa 3"]
    with pikepdf.open(out) as pdf:  # artık uyarısız açılır
        assert not pdf.get_warnings()


def test_repair_garbage_fails_clearly(tmp_path: Path):
    junk = tmp_path / "cop.pdf"
    junk.write_bytes(b"%PDF-1.7\nbu bir pdf degil")
    with pytest.raises(PdfAtolyeError, match="cop.pdf"):
        security.repair(junk, tmp_path / "o.pdf")


# --- OCR ------------------------------------------------------------------------------------


@needs_ocr
def test_ocr_turkish_scan(tmp_path: Path):
    src = fx.scanned_turkish(tmp_path / "s.pdf", pages=2)
    steps: list[str] = []
    r = ocr.ocr(src, tmp_path / "o.pdf", tesseract=TESSERACT.path,
                ghostscript=GHOSTSCRIPT.path, on_progress=lambda f, m: steps.append(m))
    assert r.page_count == 2 and r.pages_with_text == 2
    assert any(s.startswith("Metin tanınıyor") for s in steps)
    with pymupdf.open(r.output) as doc:
        # Ctrl+F ile ğ/ş/İ içeren kelimeler bulunur.
        assert doc[0].search_for("öğrenciler") and doc[0].search_for("yaşıyor")
        assert "Sayfa 2" in doc[1].get_text()


@needs_ocr
def test_ocr_skips_text_pages_and_handles_password(tmp_path: Path):
    src = fx.numbered(tmp_path / "n.pdf", 2, password="gizli")
    r = ocr.ocr(src, tmp_path / "o.pdf", password="gizli", tesseract=TESSERACT.path)
    assert r.pages_with_text == 2
    assert any("atlandı" in w for w in r.warnings)


@needs_ocr
def test_ocr_cancel(tmp_path: Path):
    src = fx.scanned_turkish(tmp_path / "s.pdf", pages=3)
    with pytest.raises(ocr.OcrCancelled):
        ocr.ocr(src, tmp_path / "o.pdf", tesseract=TESSERACT.path, should_cancel=lambda: True)
    assert not (tmp_path / "o.pdf").exists()
