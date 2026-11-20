"""Resim biçimi dönüştürme (convert/image_format.py). Resimler testte Pillow ile üretilir."""

from pathlib import Path

import pytest
from PIL import Image, ImageCms

from toolia.convert.image_format import convert_image
from toolia.errors import ImageTooLargeError, TooliaError, UnsupportedFileError

FORMATS = {".jpg": "JPEG", ".png": "PNG", ".webp": "WEBP", ".tiff": "TIFF"}


def run(src: Path, target: str, *, quality: int = 90, background: str = "#ffffff",
        out: Path | None = None) -> tuple[Path, list[str]]:
    out = out or src.with_name(src.stem + "_cikti" + target)
    return out, convert_image(src, out, target=target, quality=quality, background=background)


def two_tone(size=(40, 20), left=(0, 0, 255), right=(255, 0, 0)) -> Image.Image:
    """Sol yarısı `left`, sağ yarısı `right` renkli RGB resim."""
    img = Image.new("RGB", size, right)
    img.paste(left, (0, 0, size[0] // 2, size[1]))
    return img


def transparent_png(path: Path) -> Path:
    """Sol yarısı tamamen saydam, sağ yarısı opak yeşil RGBA PNG."""
    img = Image.new("RGBA", (40, 20), (0, 200, 0, 255))
    img.paste((0, 0, 0, 0), (0, 0, 20, 20))
    img.save(path)
    return path


def close(a, b, tol=12) -> bool:
    return all(abs(x - y) <= tol for x, y in zip(a, b, strict=True))


def no_leftovers(folder: Path, *expected: str) -> bool:
    return sorted(p.name for p in folder.iterdir()) == sorted(expected)


# --- her hedef -------------------------------------------------------------------------------


@pytest.mark.parametrize("target", [".jpg", ".png", ".webp", ".tiff"])
def test_each_target_writes_real_format(tmp_path, target):
    src = tmp_path / "kaynak.png"
    two_tone().save(src)
    out, warnings = run(src, target)
    assert warnings == []
    with Image.open(out) as img:
        assert img.format == FORMATS[target]
        assert img.size == (40, 20)
        assert close(img.convert("RGB").getpixel((5, 10)), (0, 0, 255))
    assert no_leftovers(tmp_path, "kaynak.png", out.name)  # geçici dosya kalmadı


def test_turkish_name_with_spaces(tmp_path):
    src = tmp_path / "Fotoğraf Şubat.png"
    two_tone().save(src)
    out, _ = run(src, ".jpg", out=tmp_path / "Fotoğraf Şubat.jpg")
    with Image.open(out) as img:
        assert img.format == "JPEG"


def test_quality_changes_jpeg_size(tmp_path):
    src = tmp_path / "a.png"
    Image.effect_noise((200, 200), 64).convert("RGB").save(src)
    low, _ = run(src, ".jpg", quality=10, out=tmp_path / "dusuk.jpg")
    high, _ = run(src, ".jpg", quality=95, out=tmp_path / "yuksek.jpg")
    assert low.stat().st_size < high.stat().st_size


# --- saydamlık -------------------------------------------------------------------------------


def test_transparent_png_to_jpg_uses_background(tmp_path):
    src = transparent_png(tmp_path / "a.png")
    out, warnings = run(src, ".jpg", background="#ff0000")
    with Image.open(out) as img:
        assert img.mode == "RGB"
        assert close(img.getpixel((5, 10)), (255, 0, 0))  # saydam yer → arka plan
        assert close(img.getpixel((35, 10)), (0, 200, 0))  # opak yer olduğu gibi
    assert len(warnings) == 1 and "#ff0000" in warnings[0]


def test_default_white_background_is_named(tmp_path):
    src = transparent_png(tmp_path / "a.png")
    out, warnings = run(src, ".jpg")
    with Image.open(out) as img:
        assert close(img.getpixel((5, 10)), (255, 255, 255))
    assert warnings == ["JPG saydamlık taşımaz: saydam alanlar beyaz ile dolduruldu."]


def test_opaque_alpha_to_jpg_has_no_warning(tmp_path):
    src = tmp_path / "a.png"
    Image.new("RGBA", (10, 10), (10, 20, 30, 255)).save(src)
    _, warnings = run(src, ".jpg")
    assert warnings == []


def test_palette_transparency_to_jpg(tmp_path):
    src = tmp_path / "a.gif"
    img = Image.new("P", (10, 10), 1)
    img.putpalette([0, 0, 0, 255, 0, 0] + [0] * 762)
    img.paste(0, (0, 0, 5, 10))
    img.save(src, transparency=0)
    out, warnings = run(src, ".jpg", background="#0000ff")
    with Image.open(out) as res:
        assert close(res.getpixel((1, 5)), (0, 0, 255))
        assert close(res.getpixel((8, 5)), (255, 0, 0))
    assert len(warnings) == 1


@pytest.mark.parametrize("target", [".png", ".webp", ".tiff"])
def test_alpha_is_kept_where_supported(tmp_path, target):
    src = transparent_png(tmp_path / "a.png")
    out, warnings = run(src, target)
    assert warnings == []
    with Image.open(out) as img:
        rgba = img.convert("RGBA")
        assert rgba.getpixel((5, 10))[3] == 0
        assert rgba.getpixel((35, 10))[3] == 255


# --- yönlendirme, kipler, kareler --------------------------------------------------------------


def exif_rotated_jpeg(path: Path) -> Path:
    """Piksel olarak 40x20 yatay; EXIF yönlendirmesi 6 (90° saat yönünde göster)."""
    exif = Image.Exif()
    exif[0x0112] = 6
    exif[0x0132] = "2026:02:14 10:00:00"  # DateTime: geri kalan EXIF taşınıyor mu
    two_tone().save(path, quality=95, exif=exif.tobytes())
    return path


@pytest.mark.parametrize("target", [".png", ".jpg"])
def test_exif_orientation_is_applied(tmp_path, target):
    src = exif_rotated_jpeg(tmp_path / "a.jpg")
    out, _ = run(src, target)
    with Image.open(out) as img:
        assert img.size == (20, 40)
        rgb = img.convert("RGB")
        assert close(rgb.getpixel((10, 3)), (0, 0, 255), tol=40)  # sol (mavi) yarı üste geçti
        assert close(rgb.getpixel((10, 36)), (255, 0, 0), tol=40)
        exif = img.getexif()
        # Yönlendirme piksellere uygulandı; etiket kalsa görüntüleyici ikinci kez döndürürdü.
        assert exif.get(0x0112, 1) == 1
        assert exif.get(0x0132) == "2026:02:14 10:00:00"


def test_cmyk_jpeg_to_png(tmp_path):
    src = tmp_path / "baski.jpg"
    Image.new("CMYK", (16, 16), (0, 255, 255, 0)).save(src, quality=95)
    out, warnings = run(src, ".png")
    assert warnings == []
    with Image.open(out) as img:
        assert img.format == "PNG" and img.mode == "RGB"
        assert close(img.getpixel((8, 8)), (255, 0, 0), tol=20)


def test_cmyk_stays_cmyk_in_tiff(tmp_path):
    src = tmp_path / "baski.jpg"
    Image.new("CMYK", (16, 16), (0, 255, 255, 0)).save(src, quality=95)
    out, _ = run(src, ".tiff")
    with Image.open(out) as img:
        assert img.mode == "CMYK"


def test_16bit_gray_is_scaled_not_clipped(tmp_path):
    src = tmp_path / "derin.png"
    Image.new("I;16", (8, 8), 40000).save(src)  # 40000/65535 ≈ %61 gri
    out, _ = run(src, ".jpg")
    with Image.open(out) as img:
        assert img.mode == "L"
        assert 150 <= img.getpixel((4, 4)) <= 162  # kırpılsaydı 255 (beyaz) olurdu


def test_bilevel_and_gray_to_webp(tmp_path):
    src = tmp_path / "tarama.png"
    Image.new("1", (8, 8), 1).save(src)
    out, _ = run(src, ".webp")
    with Image.open(out) as img:
        assert img.format == "WEBP"
        assert close(img.convert("RGB").getpixel((4, 4)), (255, 255, 255))


def test_animated_gif_takes_first_frame(tmp_path):
    src = tmp_path / "hareketli.gif"
    frames = [Image.new("RGB", (10, 10), c) for c in ((255, 0, 0), (0, 255, 0), (0, 0, 255))]
    frames[0].save(src, save_all=True, append_images=frames[1:], duration=100, loop=0)
    out, warnings = run(src, ".png")
    with Image.open(out) as img:
        assert getattr(img, "n_frames", 1) == 1
        assert close(img.convert("RGB").getpixel((5, 5)), (255, 0, 0))
    assert len(warnings) == 1 and "3 karenin yalnız ilki" in warnings[0]


def test_multipage_tiff_to_jpg(tmp_path):
    src = tmp_path / "cok.tiff"
    pages = [Image.new("RGB", (10, 10), c) for c in ((0, 0, 255), (255, 0, 0))]
    pages[0].save(src, save_all=True, append_images=pages[1:])
    out, warnings = run(src, ".jpg")
    with Image.open(out) as img:
        assert close(img.getpixel((5, 5)), (0, 0, 255))
    assert len(warnings) == 1 and "2 karenin" in warnings[0]


# --- üstveri ---------------------------------------------------------------------------------


@pytest.mark.parametrize("target", [".jpg", ".png", ".webp", ".tiff"])
def test_icc_profile_is_kept(tmp_path, target):
    icc = ImageCms.ImageCmsProfile(ImageCms.createProfile("sRGB")).tobytes()
    src = tmp_path / "a.png"
    two_tone().save(src, icc_profile=icc)
    out, _ = run(src, target)
    with Image.open(out) as img:
        assert img.info.get("icc_profile") == icc


@pytest.mark.parametrize("target", [".jpg", ".png", ".tiff"])
def test_dpi_is_kept(tmp_path, target):
    src = tmp_path / "a.png"
    two_tone().save(src, dpi=(300, 300))
    out, _ = run(src, target)
    with Image.open(out) as img:
        assert [round(v) for v in img.info["dpi"]] == [300, 300]


# --- HEIC ------------------------------------------------------------------------------------


def test_heic_source(tmp_path):
    src = tmp_path / "iphone.heic"
    try:
        two_tone().save(src, format="HEIF", quality=95)
    except (KeyError, OSError, ValueError) as e:  # pillow-heif yok ya da kodlayıcısı yok
        pytest.skip(f"HEIF yazılamıyor: {e}")
    out, warnings = run(src, ".jpg")
    assert warnings == []
    with Image.open(out) as img:
        assert img.format == "JPEG" and img.size == (40, 20)
        assert close(img.getpixel((5, 10)), (0, 0, 255), tol=40)


# --- hatalar ---------------------------------------------------------------------------------


def test_garbage_file_is_unsupported_and_leaves_nothing(tmp_path):
    src = tmp_path / "sahte.png"
    src.write_bytes(b"bu bir resim degil" * 10)
    out = tmp_path / "cikti.jpg"
    with pytest.raises(UnsupportedFileError, match="sahte.png"):
        convert_image(src, out, target=".jpg", quality=90, background="#ffffff")
    assert no_leftovers(tmp_path, "sahte.png")


def test_truncated_file_is_clear_error_and_leaves_nothing(tmp_path):
    src = tmp_path / "yarim.png"
    Image.effect_noise((200, 200), 64).convert("RGB").save(src)
    src.write_bytes(src.read_bytes()[:2000])
    with pytest.raises(TooliaError, match="bozuk ya da yarım"):
        run(src, ".jpg")
    assert no_leftovers(tmp_path, "yarim.png")


def test_too_wide_for_webp(tmp_path):
    src = tmp_path / "panorama.png"
    Image.new("L", (16_384, 2)).save(src)
    with pytest.raises(TooliaError, match="en fazla 16383"):
        run(src, ".webp")
    assert no_leftovers(tmp_path, "panorama.png")


def test_decompression_bomb(tmp_path, monkeypatch):
    src = tmp_path / "dev.png"
    Image.new("L", (100, 100)).save(src)
    monkeypatch.setattr(Image, "MAX_IMAGE_PIXELS", 1000)  # 2 katını aşan: bomba sayılır
    with pytest.raises(ImageTooLargeError):
        run(src, ".jpg")
    assert no_leftovers(tmp_path, "dev.png")


@pytest.mark.parametrize("kwargs", [{"target": ".bmp"}, {"background": "kırmızı"},
                                    {"background": "#gggggg"}, {"quality": 0}])
def test_bad_arguments(tmp_path, kwargs):
    src = tmp_path / "a.png"
    two_tone().save(src)
    args = {"target": ".jpg", "quality": 90, "background": "#ffffff", **kwargs}
    with pytest.raises(TooliaError):
        convert_image(src, tmp_path / "o.jpg", **args)
