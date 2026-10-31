from pathlib import Path

import pymupdf
import pytest
from PIL import Image

from pdfatolye.core import images, info
from pdfatolye.core.pdfio import safe_filename, unique_path
from pdfatolye.errors import BrokenPdfError, EncryptedPdfError, UnsupportedFileError
from tests.fixtures import make_fixtures as fx


def page_sizes(path: Path) -> list[tuple[int, int]]:
    with pymupdf.open(path) as doc:
        return [(round(p.rect.width), round(p.rect.height)) for p in doc]


# --- resim → PDF ------------------------------------------------------------------------


def test_landscape_image_gets_landscape_a4(tmp_path):
    jpg = fx.photo_jpeg(tmp_path / "a.jpg", (400, 200))
    out = images.images_to_pdf([jpg], tmp_path / "o.pdf")
    assert page_sizes(out) == [(842, 595)]


def test_exif_rotation_is_applied(tmp_path):
    # Orientation 6: kamera 90° döndürülmüş; gerçek görüntü 200x400 dikey olmalı.
    jpg = fx.photo_jpeg(tmp_path / "a.jpg", (400, 200), exif_orientation=6)
    out = images.images_to_pdf([jpg], tmp_path / "o.pdf", page_size="resim")
    w, h = page_sizes(out)[0]
    assert h > w
    with pymupdf.open(out) as doc:
        pix = doc[0].get_pixmap(dpi=36)
        top = pix.pixel(pix.width // 2, 2)
        bottom = pix.pixel(pix.width // 2, pix.height - 3)
    # Sol (mavi) yarı, saat yönünde döndürülünce üste geçer.
    assert top[2] > 200 and top[0] < 60
    assert bottom[0] > 200 and bottom[2] < 60


def test_upright_jpeg_is_embedded_without_recompression(tmp_path):
    jpg = fx.photo_jpeg(tmp_path / "a.jpg")
    out = images.images_to_pdf([jpg], tmp_path / "o.pdf")
    with pymupdf.open(out) as doc:
        xref = doc.get_page_images(0)[0][0]
        assert doc.extract_image(xref)["image"] == jpg.read_bytes()


def test_png_alpha_tiff_frames_and_margins(tmp_path):
    png = fx.transparent_png(tmp_path / "a.png")
    tif = fx.multipage_tiff(tmp_path / "b.tif", frames=3)
    out = images.images_to_pdf([png, tif], tmp_path / "o.pdf", page_size="Letter",
                               orientation="dikey", margin_mm=10)
    assert page_sizes(out) == [(612, 792)] * 4
    with pymupdf.open(out) as doc:
        x0, y0, _, _ = doc[0].get_image_bbox(doc.get_page_images(0, full=True)[0])
        assert x0 >= 28  # 10 mm ≈ 28,3 pt


def test_not_an_image(tmp_path):
    bad = tmp_path / "x.jpg"
    bad.write_text("resim değil")
    with pytest.raises(UnsupportedFileError, match="resim"):
        images.images_to_pdf([bad], tmp_path / "o.pdf")


# --- PDF → resim ------------------------------------------------------------------------


def test_pdf_to_png(tmp_path):
    src = fx.numbered(tmp_path / "on.pdf", 10)
    outs = images.pdf_to_images(src, tmp_path / "img", dpi=72, spec="1, 10")
    assert [o.name for o in outs] == ["on_01.png", "on_10.png"]
    with Image.open(outs[0]) as im:
        assert im.size == (595, 842)


def test_pdf_to_jpg_respects_rotation(tmp_path):
    src = fx.rotated(tmp_path / "r.pdf")
    outs = images.pdf_to_images(src, tmp_path / "img", dpi=36, fmt="jpg", spec="2")
    with Image.open(outs[0]) as im:
        assert im.format == "JPEG"
        assert im.width > im.height  # 90° döndürülmüş A4


def test_pdf_to_images_rejects_extreme_dpi(tmp_path):
    src = fx.numbered(tmp_path / "a.pdf", 1, with_toc=False)
    with pytest.raises(ValueError):
        images.pdf_to_images(src, tmp_path / "img", dpi=2000)


def test_extract_embedded_images(tmp_path):
    jpg = fx.photo_jpeg(tmp_path / "a.jpg")
    png = fx.transparent_png(tmp_path / "b.png")
    pdf = images.images_to_pdf([jpg, png, jpg], tmp_path / "o.pdf")
    outs = images.extract_images(pdf, tmp_path / "ex")
    exts = sorted(o.suffix for o in outs)
    assert exts == [".jpeg", ".png"]  # aynı JPEG iki kez gömülmüş olsa da bir kez çıkar


# --- bilgi ------------------------------------------------------------------------------


def test_inspect_numbered(tmp_path):
    src = fx.mixed_sizes(tmp_path / "m.pdf")
    i = info.inspect_pdf(src)
    assert i.page_count == 3
    assert [p.paper for p in i.pages] == ["A4", "A4", "Letter"]
    assert i.has_text is True
    assert i.encrypted is False


def test_inspect_encrypted_without_password(tmp_path):
    src = fx.numbered(tmp_path / "s.pdf", 2, password="gizli")
    i = info.inspect_pdf(src)
    assert i.needs_password and i.encrypted and i.page_count == 0
    with pytest.raises(EncryptedPdfError):
        info.inspect_pdf(src, "yanlis")
    unlocked = info.inspect_pdf(src, "gizli")
    assert unlocked.encrypted and unlocked.page_count == 2


def test_inspect_scanned_has_no_text(tmp_path):
    assert info.inspect_pdf(fx.scanned(tmp_path / "t.pdf")).has_text is False


def test_broken_and_non_pdf_files(tmp_path):
    broken = tmp_path / "bozuk.pdf"
    broken.write_bytes(b"%PDF-1.7\n bu bir pdf degil")
    with pytest.raises(BrokenPdfError):
        info.inspect_pdf(broken)
    png = fx.transparent_png(tmp_path / "resim.pdf")  # uzantısı yanıltıcı
    with pytest.raises((BrokenPdfError, UnsupportedFileError)):
        info.inspect_pdf(png)


# --- dosya adı yardımcıları -------------------------------------------------------------


@pytest.mark.parametrize(
    ("name", "expected"),
    [("Bölüm 1: Giriş", "Bölüm 1_ Giriş"), ("a/b\\c", "a_b_c"), ("CON", "dosya"),
     ("  ..  ", "dosya"), ("Çok   boşluk", "Çok boşluk")],
)
def test_safe_filename(name, expected):
    assert safe_filename(name) == expected


def test_unique_path(tmp_path):
    p = tmp_path / "a.pdf"
    assert unique_path(p) == p
    p.write_bytes(b"")
    assert unique_path(p).name == "a (2).pdf"
