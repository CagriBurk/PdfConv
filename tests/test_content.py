"""İçerik ekleme ve koordinatlar: döndürülmüş / CropBox'ı kaydırılmış sayfalar, Türkçe yazı,
gerçek karartma."""

from pathlib import Path

import pymupdf
import pytest
from PIL import Image
from pydantic import TypeAdapter, ValidationError

from pdfatolye.core import content, fonts, geometry
from pdfatolye.errors import PageRangeError
from tests.fixtures import make_fixtures as fx

# Bazı testler bilerek bir Windows yazı tipini (Arial) kullanır; Linux'ta yoktur.
needs_arial = pytest.mark.skipif(not Path("C:/Windows/Fonts/arial.ttf").is_file(),
                                 reason="Windows yazı tipi (Arial) yok")

OPS = TypeAdapter(list[content.Op])
TR = "Onaylandı – Çağrı İşçi ğüşıöç İĞÜŞÖÇ"


def ops(*items: dict) -> list:
    return OPS.validate_python(list(items))


def view_words(page: pymupdf.Page) -> list[tuple[pymupdf.Rect, str]]:
    """Sayfadaki kelimeler, görünüm koordinatlarında."""
    return [(geometry.page_to_view_rect(page, w[:4]), w[4]) for w in page.get_text("words")]


def text_in(page: pymupdf.Page, view_rect) -> str:
    r = pymupdf.Rect(view_rect)
    words = [t for box, t in view_words(page) if (box.tl + box.br) / 2 in r]
    return " ".join(words)


def view_chars(page: pymupdf.Page, view_rect) -> list[tuple[pymupdf.Point, str]]:
    """Kutudaki karakterlerin taban noktaları (görünümde), yazıldıkları sırayla."""
    r = pymupdf.Rect(view_rect)
    out = []
    for b in page.get_text("rawdict")["blocks"]:
        for line in b.get("lines", []):
            for span in line["spans"]:
                for ch in span["chars"]:
                    o = geometry.page_to_view_point(page, *ch["origin"])
                    if o in r:
                        out.append((o, ch["c"]))
    return out


# --- geometri -------------------------------------------------------------------------------


@pytest.mark.parametrize("angle", [0, 90, 180, 270])
def test_view_page_roundtrip_with_cropbox(angle):
    doc = pymupdf.open()
    page = doc.new_page(width=600, height=800)
    page.set_cropbox(pymupdf.Rect(50, 100, 550, 700))
    page.set_rotation(angle)
    view = pymupdf.Rect(30, 40, 130, 90)
    back = geometry.page_to_view_rect(page, geometry.view_to_page_rect(page, view))
    assert tuple(back) == pytest.approx(tuple(view))
    w, h = geometry.view_size(page)
    assert (w, h) == ((500, 600) if angle in (0, 180) else (600, 500))


def test_view_origin_is_visible_top_left():
    doc = pymupdf.open()
    page = doc.new_page(width=600, height=800)
    page.set_rotation(90)
    # 90° saat yönünde: görünümün sol üstü, döndürülmemiş sayfanın sol altıdır.
    assert geometry.view_to_page_point(page, 0, 0) == pymupdf.Point(0, 800)


def test_fit_inside_and_rotated_bbox():
    r = geometry.fit_inside([0, 0, 200, 100], 50, 50)
    assert tuple(r) == (50, 0, 150, 100)
    bb = geometry.rotated_bbox([0, 0, 100, 50], 90)
    assert tuple(bb) == pytest.approx((25, -25, 75, 75))


# --- yazı -----------------------------------------------------------------------------------


@pytest.mark.parametrize("page_no", [0, 1, 2, 3])  # döndürmeler 0, 90, 180, 270
def test_turkish_text_on_rotated_pages(tmp_path: Path, page_no):
    src = fx.rotated(tmp_path / "r.pdf")
    out = tmp_path / "o.pdf"
    box = [150, 450, 500, 490]  # fixture'ın kendi yazılarından uzak (her döndürmede)
    content.apply_ops(src, out, ops({"type": "text", "page": page_no, "rect": box, "text": TR,
                                     "size": 14}))
    with pymupdf.open(out) as doc:
        page = doc[page_no]
        assert text_in(page, box) == TR
        chars = view_chars(page, box)
        assert chars[0][1] == "O"
        # Okuyana dik: soldan sağa ve aynı taban çizgisinde.
        assert chars[-1][0].x > chars[0][0].x + 100
        assert chars[-1][0].y == pytest.approx(chars[0][0].y, abs=0.5)
        fonts_used = [f for f in page.get_fonts() if f[4].startswith("pa")]
        assert fonts_used and fonts_used[0][1] == "ttf"  # gömülü TTF


def test_text_on_cropped_and_rotated_page(tmp_path: Path):
    src = fx.cropped(tmp_path / "c.pdf")
    out = tmp_path / "o.pdf"
    box = [20, 20, 300, 50]
    content.apply_ops(src, out, ops(
        {"type": "text", "page": 0, "rect": box, "text": "Kırpılmış ğ"},
        {"type": "text", "page": 1, "rect": box, "text": "Döndürülmüş ş"},
    ))
    with pymupdf.open(out) as doc:
        assert text_in(doc[0], box) == "Kırpılmış ğ"
        assert text_in(doc[1], box) == "Döndürülmüş ş"
        # Görünür alanın içinde çizildi mi (CropBox dışında kalsa görünmezdi)?
        pix = doc[1].get_pixmap(dpi=72)
        dark = [pix.pixel(x, y) for x in range(20, 120, 2) for y in range(20, 50)]
        assert min(sum(p) for p in dark) < 300


@needs_arial
def test_text_spaces_and_subset_size(tmp_path: Path):
    src = fx.numbered(tmp_path / "n.pdf", 2)
    out = tmp_path / "o.pdf"
    content.apply_ops(src, out, ops(
        {"type": "text", "page": 0, "rect": [72, 400, 400, 440], "text": "a b c",
         "font": "arial"},
        {"type": "text", "page": 1, "rect": [72, 400, 400, 440], "text": "İkinci sayfa",
         "font": "arial"},
    ))
    with pymupdf.open(out) as doc:
        assert "a b c" in doc[0].get_text()  # NBSP değil, gerçek boşluk
        xrefs = {f[0] for p in doc for f in p.get_fonts() if f[4].startswith("pa")}
        assert len(xrefs) == 1  # aynı font tüm sayfalarda tek nesne
    assert out.stat().st_size < src.stat().st_size + 60_000  # alt küme, tam font değil


def test_text_box_grows_when_too_small(tmp_path: Path):
    src = fx.numbered(tmp_path / "n.pdf", 1)
    out = tmp_path / "o.pdf"
    long = "Uzun bir paragraf " * 12
    result = content.apply_ops(src, out, ops(
        {"type": "text", "page": 0, "rect": [72, 400, 250, 410], "text": long}))
    assert not result.warnings
    with pymupdf.open(out) as doc:
        assert doc[0].get_text().count("paragraf") == 12


def test_rotated_text_box(tmp_path: Path):
    src = fx.numbered(tmp_path / "n.pdf", 1)
    out = tmp_path / "o.pdf"
    content.apply_ops(src, out, ops({"type": "text", "page": 0, "rect": [200, 400, 400, 430],
                                     "text": "Eğik yazı", "rotation": 90}))
    with pymupdf.open(out) as doc:
        line = doc[0].get_text("dict")["blocks"][-1]["lines"][0]
        assert line["dir"] == pytest.approx((0, 1), abs=1e-3)  # saat yönünde 90°: aşağı akar
        # Kutu merkezi etrafında döndü: yazı x≈300 dikey çizgisinde.
        assert 280 < line["bbox"][0] < 320


@needs_arial
def test_missing_glyph_warning(tmp_path: Path):
    src = fx.numbered(tmp_path / "n.pdf", 1)
    result = content.apply_ops(src, tmp_path / "o.pdf", ops(
        {"type": "text", "page": 0, "rect": [72, 400, 300, 430], "text": "Merhaba 世",
         "font": "arial"}))
    assert any("世" in w for w in result.warnings)


# --- resim / imza ---------------------------------------------------------------------------


@pytest.mark.parametrize("page_no", [0, 1, 2, 3])
def test_image_upright_on_rotated_pages(tmp_path: Path, page_no):
    src = fx.rotated(tmp_path / "r.pdf")
    img = fx.photo_jpeg(tmp_path / "foto.jpg")  # sol mavi, sağ kırmızı, 2:1
    out = tmp_path / "o.pdf"
    box = [100, 400, 300, 500]
    content.apply_ops(src, out, ops({"type": "image", "page": page_no, "rect": box,
                                     "asset": "foto"}), assets={"foto": img})
    with pymupdf.open(out) as doc:
        pix = doc[page_no].get_pixmap(dpi=72)  # görünüm yönünde çizilir
        left, right = pix.pixel(130, 450), pix.pixel(270, 450)
        assert left[2] > 200 and left[0] < 80, left  # mavi
        assert right[0] > 200 and right[2] < 80, right  # kırmızı


def test_signature_reused_on_many_pages(tmp_path: Path):
    src = fx.numbered(tmp_path / "n.pdf", 3)
    sig = content.prepare_signature(fx.signature_jpeg(tmp_path / "imza.jpg"),
                                    tmp_path / "imza.png")
    out = tmp_path / "o.pdf"
    content.apply_ops(src, out, ops(*[
        {"type": "image", "page": i, "rect": [400, 700, 520, 760], "asset": "imza"}
        for i in range(3)]), assets={"imza": sig})
    with pymupdf.open(out) as doc:
        xrefs = {img[0] for p in doc for img in p.get_images()}
        assert len(xrefs) == 1
        smask = doc[0].get_images()[0][1]
        assert smask  # saydamlık maskesi var


def test_prepare_signature_makes_paper_transparent(tmp_path: Path):
    out = content.prepare_signature(fx.signature_jpeg(tmp_path / "imza.jpg"), tmp_path / "s.png")
    with Image.open(out) as im:
        assert im.mode == "RGBA"
        assert im.getpixel((0, 0))[3] == 0  # köşe: kâğıt saydam
        assert im.width < 600 and im.height < 300  # boşluk kırpıldı
        assert im.getchannel("A").getextrema()[1] == 255  # mürekkep opak


def test_prepare_signature_rejects_blank(tmp_path: Path):
    blank = tmp_path / "bos.png"
    Image.new("RGB", (200, 100), "white").save(blank)
    with pytest.raises(Exception, match="imza bulunamadı"):
        content.prepare_signature(blank, tmp_path / "s.png")


# --- karartma / beyazla kapat ---------------------------------------------------------------


@pytest.mark.parametrize("page_no", [0, 1])
def test_redaction_removes_text(tmp_path: Path, page_no):
    src = fx.rotated(tmp_path / "r.pdf")
    label = f"Sayfa {page_no + 1}"
    with pymupdf.open(src) as doc:
        page = doc[page_no]
        hit = geometry.page_to_view_rect(page, page.search_for(label)[0])
    out = tmp_path / "o.pdf"
    box = [hit.x0 - 2, hit.y0 - 2, hit.x1 + 2, hit.y1 + 2]
    content.apply_ops(src, out, ops({"type": "redact", "page": page_no, "rect": box}))
    with pymupdf.open(out) as doc:
        page = doc[page_no]
        assert label not in page.get_text()
        assert "ığdır" in page.get_text()  # kutu dışındaki yazı duruyor
        assert not list(page.annots())  # karartma açıklaması kalmadı, uygulandı
        assert "Sayfa" in doc[(page_no + 1) % 4].get_text()


def test_redaction_removes_image_pixels(tmp_path: Path):
    src = fx.numbered(tmp_path / "n.pdf", 1)
    img = fx.photo_jpeg(tmp_path / "foto.jpg")
    mid = tmp_path / "m.pdf"
    content.apply_ops(src, mid, ops({"type": "image", "page": 0, "rect": [100, 400, 300, 500],
                                     "asset": "f"}), assets={"f": img})
    out = tmp_path / "o.pdf"
    content.apply_ops(mid, out, ops({"type": "redact", "page": 0, "rect": [90, 390, 200, 510],
                                     "fill": "#000000"}))
    with pymupdf.open(out) as doc:
        pix = doc[0].get_pixmap(dpi=72)
        assert pix.pixel(130, 450) == (0, 0, 0)  # karartılan kısım
        assert pix.pixel(270, 450)[0] > 200  # kalan kısım (kırmızı)
        xref = doc[0].get_images()[0][0]
        data = pymupdf.Pixmap(doc, xref)
        # Resmin kendisinde de silinmiş: sol yarı artık mavi değil (boşaltılmış = beyaz).
        assert data.pixel(10, data.height // 2) == (255, 255, 255)
        assert data.pixel(data.width - 10, data.height // 2)[0] > 200


def test_whiteout_then_text(tmp_path: Path):
    src = fx.numbered(tmp_path / "n.pdf", 1)
    with pymupdf.open(src) as doc:
        hit = doc[0].search_for("Sayfa 1")[0]
    box = [hit.x0 - 2, hit.y0 - 2, hit.x1 + 40, hit.y1 + 2]
    out = tmp_path / "o.pdf"
    content.apply_ops(src, out, ops(
        {"type": "whiteout", "page": 0, "rect": box},
        {"type": "text", "page": 0, "rect": box, "text": "Düzeltildi", "size": 16},
    ))
    with pymupdf.open(out) as doc:
        text = doc[0].get_text()
        assert "Sayfa 1" not in text
        assert "Düzeltildi" in text


# --- vurgu ve şekiller ----------------------------------------------------------------------


def test_highlight_snaps_to_words(tmp_path: Path):
    src = fx.numbered(tmp_path / "n.pdf", 1)
    out = tmp_path / "o.pdf"
    content.apply_ops(src, out, ops({"type": "highlight", "page": 0,
                                     "rect": [60, 40, 300, 80]}))
    with pymupdf.open(out) as doc:
        page = doc[0]
        annot = next(page.annots())
        assert annot.type[1] == "Highlight"
        assert annot.rect.width < 120  # yalnızca "Sayfa 1" kelimeleri, kutunun tamamı değil


def test_shapes_and_lines(tmp_path: Path):
    src = fx.rotated(tmp_path / "r.pdf")
    out = tmp_path / "o.pdf"
    content.apply_ops(src, out, ops(
        {"type": "rect", "page": 1, "rect": [50, 50, 150, 100], "stroke": "#ff0000"},
        {"type": "ellipse", "page": 1, "rect": [200, 50, 300, 100], "stroke": None,
         "fill": "#00ff00"},
        {"type": "line", "page": 1, "points": [50, 200, 300, 200]},
        {"type": "arrow", "page": 1, "points": [50, 250, 300, 250], "width": 3},
    ))
    with pymupdf.open(out) as doc:
        page = doc[1]
        pix = page.get_pixmap(dpi=72)
        assert pix.pixel(50, 75)[0] > 200 and pix.pixel(50, 75)[1] < 80  # çerçevenin sol kenarı
        assert pix.pixel(250, 75)[1] > 200  # elips dolgusu
        assert pix.pixel(150, 200)[0] > 150 and pix.pixel(150, 200)[1] < 60  # çizgi
        assert pix.pixel(150, 210) == (255, 255, 255)
        assert pix.pixel(296, 250)[1] < 60  # ok ucu
        assert pix.pixel(290, 253)[1] < 60  # ucun genişliği (çizgiden kalın)
        assert pix.pixel(280, 253)[1] > 200
        assert len(page.get_drawings()) >= 4


def test_rotated_rect(tmp_path: Path):
    src = fx.numbered(tmp_path / "n.pdf", 1)
    out = tmp_path / "o.pdf"
    # 200×20'lik dolu kutu, merkezi (300, 500) etrafında 90°: 20×200 dikey şerit olur.
    content.apply_ops(src, out, ops({"type": "rect", "page": 0, "rect": [200, 490, 400, 510],
                                     "stroke": None, "fill": "#0000ff", "rotation": 90}))
    with pymupdf.open(out) as doc:
        pix = doc[0].get_pixmap(dpi=72)
        assert pix.pixel(300, 420)[2] > 200 and pix.pixel(300, 420)[0] < 60
        assert pix.pixel(220, 500) == (255, 255, 255)


def test_shape_needs_stroke_or_fill():
    with pytest.raises(ValidationError):
        ops({"type": "rect", "page": 0, "rect": [0, 0, 10, 10], "stroke": None})


# --- filigran ve sayfa numarası -------------------------------------------------------------


def test_text_watermark_on_range(tmp_path: Path):
    src = fx.rotated(tmp_path / "r.pdf")
    out = tmp_path / "o.pdf"
    content.apply_ops(src, out, ops({"type": "watermark", "text": "TASLAK ĞİŞ", "pages": "2-3",
                                     "opacity": 0.3, "layer": "back"}))
    with pymupdf.open(out) as doc:
        assert ["TASLAK" in p.get_text() for p in doc] == [False, True, True, False]
        page = doc[1]
        # Ortalanmış: kelimelerin merkezi görünür sayfanın ortasına yakın.
        boxes = [b for b, t in view_words(page) if t in ("TASLAK", "ĞİŞ")]
        union = boxes[0] | boxes[1]
        w, h = geometry.view_size(page)
        assert abs((union.x0 + union.x1) / 2 - w / 2) < 5
        assert abs((union.y0 + union.y1) / 2 - h / 2) < 5
        # 45°, yükselen çapraz: görünümde ilk harf sol altta, son harf sağ üstte.
        chars = view_chars(page, [0, 0, w, h])
        letters = [(o, c) for o, c in chars if c in "TK"]
        first, last = letters[0][0], letters[-1][0]
        assert last.x > first.x + 50 and last.y < first.y - 50


def test_image_watermark(tmp_path: Path):
    src = fx.numbered(tmp_path / "n.pdf", 2)
    logo = fx.transparent_png(tmp_path / "logo.png")
    out = tmp_path / "o.pdf"
    content.apply_ops(src, out, ops({"type": "watermark", "asset": "logo", "angle": 0,
                                     "opacity": 0.5, "scale": 0.4}), assets={"logo": logo})
    with pymupdf.open(out) as doc:
        assert all(p.get_images() for p in doc)
        pix = doc[0].get_pixmap(dpi=72)
        r, g, b = pix.pixel(297, 421)
        assert 100 < r < 200 and g > 150  # yarı saydam yeşil


def test_watermark_needs_text_or_image():
    with pytest.raises(ValidationError):
        ops({"type": "watermark"})
    with pytest.raises(ValidationError):
        ops({"type": "watermark", "text": "a", "asset": "b"})


def test_page_numbers_format_skip_first_and_position(tmp_path: Path):
    src = fx.rotated(tmp_path / "r.pdf")
    out = tmp_path / "o.pdf"
    content.apply_ops(src, out, ops({"type": "page_numbers", "format": "Sayfa {n} / {N}",
                                     "skip_first": True}))
    with pymupdf.open(out) as doc:
        assert "/ 3" not in doc[0].get_text()
        for i in (1, 2, 3):
            page = doc[i]
            w, h = geometry.view_size(page)
            words = [b for b, t in view_words(page) if t == "/"]
            assert words, f"{i + 1}. sayfada numara yok"
            slash = words[0]
            assert abs((slash.x0 + slash.x1) / 2 - w / 2) < 30  # ortada
            assert h - 60 < slash.y1 < h  # altta (döndürülmüş sayfada da görünür alt)
            assert f"Sayfa {i} / 3" in " ".join(t for _, t in view_words(page))


def test_page_numbers_start_and_range(tmp_path: Path):
    src = fx.numbered(tmp_path / "n.pdf", 5)
    out = tmp_path / "o.pdf"
    content.apply_ops(src, out, ops({"type": "page_numbers", "format": "- {n} -", "start": 10,
                                     "pages": "3-5", "position": "top-right"}))
    with pymupdf.open(out) as doc:
        assert "- 10 -" in doc[2].get_text()
        assert "- 12 -" in doc[4].get_text()
        assert "- " not in doc[1].get_text()


def test_page_number_format_needs_n():
    with pytest.raises(ValidationError):
        ops({"type": "page_numbers", "format": "Sayfa"})


# --- doğrulama ------------------------------------------------------------------------------


def test_page_out_of_range(tmp_path: Path):
    src = fx.numbered(tmp_path / "n.pdf", 2)
    with pytest.raises(PageRangeError, match="5. sayfa yok"):
        content.apply_ops(src, tmp_path / "o.pdf", ops(
            {"type": "text", "page": 4, "rect": [0, 0, 100, 20], "text": "x"}))


def test_unknown_asset(tmp_path: Path):
    src = fx.numbered(tmp_path / "n.pdf", 1)
    with pytest.raises(Exception, match="Resim bulunamadı"):
        content.apply_ops(src, tmp_path / "o.pdf", ops(
            {"type": "image", "page": 0, "rect": [0, 0, 100, 100], "asset": "yok"}))


def test_encrypted_source(tmp_path: Path):
    src = fx.numbered(tmp_path / "s.pdf", 2, password="gizli")
    out = tmp_path / "o.pdf"
    content.apply_ops(src, out, ops({"type": "text", "page": 0, "rect": [72, 400, 300, 430],
                                     "text": "Şifreli"}), password="gizli")
    with pymupdf.open(out) as doc:
        assert "Şifreli" in doc[0].get_text()


@needs_arial
def test_fonts_available():
    keys = {f["key"] for f in fonts.available()}
    assert "arial" in keys
