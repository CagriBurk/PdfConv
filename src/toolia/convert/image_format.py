"""Resim biçimi dönüştürme (Pillow): JPG, PNG, WEBP, TIFF.

Yalnız ilk kare çevrilir; EXIF yönlendirmesi uygulanır; ICC profili, DPI ve (JPG/PNG/WEBP'de)
EXIF korunur. Hedefin desteklemediği kipler güvenle çevrilir, saydamlık JPG'de arka plan
rengine birleştirilir.
"""

from __future__ import annotations

import contextlib
import io
import os
import uuid
from pathlib import Path

from PIL import Image, ImageOps, UnidentifiedImageError

from toolia.errors import (
    ImageTooLargeError,
    TooliaError,
    UnsupportedFileError,
    disk_full_error,
    is_disk_full,
)

try:  # iPhone fotoğrafları (HEIC/HEIF)
    from pillow_heif import register_heif_opener

    register_heif_opener()
except ImportError:  # pragma: no cover - isteğe bağlı
    pass

_FORMATS = {".jpg": "JPEG", ".png": "PNG", ".webp": "WEBP", ".tiff": "TIFF"}
# Hedefin olduğu gibi yazdığı kipler; diğerleri bunlardan birine çevrilir.
_MODES = {
    ".jpg": frozenset({"RGB", "L"}),
    ".png": frozenset({"RGB", "RGBA", "L", "LA"}),
    ".webp": frozenset({"RGB", "RGBA"}),
    ".tiff": frozenset({"RGB", "RGBA", "L", "LA", "CMYK", "1"}),
}
# Biçimin kenar sınırı (piksel); aşılırsa kodlayıcı anlaşılmaz bir hata verir.
_MAX_SIDE = {".jpg": 65_500, ".webp": 16_383}
_JPEG_MAX_EXIF = 65_000  # JPEG'de EXIF tek bir 64 KB işaretçiye sığmalı
_COLOR_NAMES = {"#ffffff": "beyaz", "#000000": "siyah"}
_ORIENTATION = 0x0112


class ImageConvertError(TooliaError):
    """Mesajında dosya adı geçen hata; işçi `path` sayesinde adı kullanıcınınkiyle değiştirir."""

    def __init__(self, path: Path, message: str) -> None:
        self.path = path
        super().__init__(message)


def convert_image(src: Path, out: Path, *, target: str, quality: int,
                  background: str) -> list[str]:
    """`src` resmini `target` biçiminde `out`'a yazar; kullanıcıya gösterilecek uyarıları döner.

    target: '.jpg', '.png', '.webp', '.tiff'. quality: JPG/WEBP için 1–100.
    background: '#rrggbb'; saydam resim JPG'e çevrilirken saydam alanlar bu renkle doldurulur.
    """
    src, out = Path(src), Path(out)
    target = target.lower()
    if target not in _FORMATS:
        raise TooliaError(f"Bilinmeyen hedef biçim: {target}")
    if not 1 <= quality <= 100:
        raise TooliaError("Kalite 1 ile 100 arasında olmalı.")
    bg = _parse_color(background)
    warnings: list[str] = []

    try:
        img = Image.open(src)
    except Image.DecompressionBombError as e:
        raise ImageTooLargeError(src) from e
    except (UnidentifiedImageError, OSError) as e:
        raise UnsupportedFileError(src, "resim") from e

    with img:
        n_frames = getattr(img, "n_frames", 1)
        icc = img.info.get("icc_profile") or None
        dpi = _dpi(img.info.get("dpi"))
        src_mode = img.mode
        try:
            # Kopya üretir ve ilk kareyi çözer; bozuk/yarım dosya burada yakalanır.
            frame = ImageOps.exif_transpose(img)
            exif = _exif_bytes(img, frame)
        except Image.DecompressionBombError as e:
            raise ImageTooLargeError(src) from e
        except MemoryError as e:
            raise ImageTooLargeError(src) from e
        except (OSError, ValueError, SyntaxError) as e:
            raise ImageConvertError(
                src, f"'{src.name}' okunamadı; resim bozuk ya da yarım olabilir.") from e

    if n_frames > 1:
        warnings.append(f"Hareketli ya da çok sayfalı resim: {n_frames} karenin yalnız ilki "
                        "alındı.")

    limit = _MAX_SIDE.get(target)
    if limit and max(frame.size) > limit:
        name = target.lstrip(".").upper()
        raise ImageConvertError(
            src, f"'{src.name}' {name} için çok büyük (en fazla {limit} piksel kenar). PNG ya "
            "da TIFF seç.")

    try:
        frame, icc = _to_target_mode(frame, src_mode, icc, target, bg, warnings)
    except MemoryError as e:
        raise ImageTooLargeError(src) from e

    _save(frame, src, out, target, quality=quality, icc=icc, dpi=dpi, exif=exif)
    return warnings


# --- kip dönüşümleri -------------------------------------------------------------------------


def _to_target_mode(img: Image.Image, src_mode: str, icc: bytes | None, target: str,
                    bg: tuple[int, int, int], warnings: list[str]
                    ) -> tuple[Image.Image, bytes | None]:
    """Resmi hedefin yazabildiği kipe getirir. ICC profili renk uzayı değişirse düşürülür."""
    allowed = _MODES[target]
    mode = img.mode

    # Önce az rastlanan kipleri 1/L/LA/RGB/RGBA/CMYK'ya indir.
    if mode.startswith("I") or mode == "F":
        img = _to_8bit(img)
    elif mode in ("RGBa", "PA"):
        img = img.convert("RGBA")
    elif mode == "La":
        img = img.convert("LA")
    elif mode == "P":
        img = img.convert("RGBA" if "transparency" in img.info else "RGB")
    elif mode in ("L", "RGB") and "transparency" in img.info:  # PNG tRNS: tek saydam renk
        img = img.convert(mode + "A")
    elif mode == "CMYK" and "CMYK" not in allowed:
        img, icc = _cmyk_to_rgb(img, icc), None
    elif mode not in ("1", "L", "LA", "RGB", "RGBA", "CMYK"):  # YCbCr, LAB, HSV, RGBX…
        img = img.convert("RGB")

    if img.mode in ("LA", "RGBA") and target == ".jpg":
        img = _flatten(img, bg, warnings)
    if img.mode not in allowed:
        img = img.convert({"1": "L", "L": "RGB", "LA": "RGBA"}.get(img.mode, "RGB"))

    if icc and _space(src_mode) != _space(img.mode):
        icc = None
    return img, icc


def _to_8bit(img: Image.Image) -> Image.Image:
    """16/32 bit gri resmi 8 bite indirir (16 bit değerler kırpılmadan ölçeklenir)."""
    if img.mode == "F":
        return img.convert("L")
    if img.mode != "I":
        img = img.convert("I")
    _, hi = img.getextrema()
    if hi > 255:
        img = img.point(lambda v: v / 256)
    return img.convert("L")


def _flatten(img: Image.Image, bg: tuple[int, int, int], warnings: list[str]) -> Image.Image:
    """Saydam resmi arka plan rengine birleştirir (JPG saydamlık taşımaz)."""
    rgba = img.convert("RGBA")
    if rgba.getchannel("A").getextrema()[0] == 255:  # saydam alan yok
        return img.convert("RGB" if img.mode == "RGBA" else "L")
    base = Image.new("RGBA", rgba.size, (*bg, 255))
    hex_color = "#{:02x}{:02x}{:02x}".format(*bg)
    color = _COLOR_NAMES.get(hex_color, hex_color)
    warnings.append(f"JPG saydamlık taşımaz: saydam alanlar {color} ile dolduruldu.")
    return Image.alpha_composite(base, rgba).convert("RGB")


def _cmyk_to_rgb(img: Image.Image, icc: bytes | None) -> Image.Image:
    """CMYK → sRGB. Gömülü profil varsa renkler onunla çevrilir, yoksa yaklaşık çevrilir."""
    if icc:
        try:
            from PIL import ImageCms

            src_profile = ImageCms.ImageCmsProfile(io.BytesIO(icc))
            return ImageCms.profileToProfile(img, src_profile, ImageCms.createProfile("sRGB"),
                                             outputMode="RGB")
        except (ImportError, OSError, ValueError, TypeError):  # PyCMSError, OSError'dan türer
            pass
    return img.convert("RGB")


def _space(mode: str) -> str:
    if mode in ("1", "L", "LA", "La", "F") or mode.startswith("I"):
        return "gri"
    if mode == "CMYK":
        return "cmyk"
    if mode in ("RGB", "RGBA", "RGBa", "RGBX", "P", "PA"):
        return "rgb"
    return mode


# --- üstveri ---------------------------------------------------------------------------------


def _parse_color(value: str) -> tuple[int, int, int]:
    text = (value or "").strip().lstrip("#")
    if len(text) != 6:
        raise TooliaError(f"Arka plan rengi '#rrggbb' biçiminde olmalı: {value}")
    try:
        return int(text[0:2], 16), int(text[2:4], 16), int(text[4:6], 16)
    except ValueError as e:
        raise TooliaError(f"Arka plan rengi '#rrggbb' biçiminde olmalı: {value}") from e


def _dpi(value) -> tuple[float, float] | None:
    try:
        x, y = (float(v) for v in value)
    except (TypeError, ValueError):
        return None
    return (x, y) if x > 0 and y > 0 else None


def _exif_bytes(src: Image.Image, frame: Image.Image) -> bytes | None:
    """Kaynağın EXIF bloğu (yönlendirme etiketi atılmış). TIFF'in etiketleri EXIF sayılmaz."""
    if "exif" not in src.info:
        return None
    try:
        exif = frame.getexif()
        exif.pop(_ORIENTATION, None)  # yönlendirme piksellere uygulandı
        data = exif.tobytes()
    except Exception:  # bozuk EXIF dönüşümü durdurmasın, yalnız atılır
        return None
    return data if len(data) > 8 else None  # yalnız başlık kaldıysa yazma


# --- kaydetme --------------------------------------------------------------------------------


def _save(img: Image.Image, src: Path, out: Path, target: str, *, quality: int,
          icc: bytes | None, dpi: tuple[float, float] | None, exif: bytes | None) -> None:
    """Önce yanındaki geçici dosyaya yazar, sonra `out`'a taşır: yarım çıktı kalmaz."""
    params: dict = {}
    if icc:
        params["icc_profile"] = icc
    if dpi and target != ".webp":
        params["dpi"] = dpi
    if exif and target != ".tiff" and not (target == ".jpg" and len(exif) > _JPEG_MAX_EXIF):
        params["exif"] = exif
    if target == ".jpg":
        params.update(quality=quality, optimize=False)
    elif target == ".webp":
        params.update(quality=quality)
    elif target == ".png":
        params.update(optimize=False)
    else:
        params.update(compression="tiff_lzw")

    tmp = out.with_name(f".{out.stem}.{uuid.uuid4().hex[:8]}.part")
    try:
        img.save(tmp, format=_FORMATS[target], **params)
        os.replace(tmp, out)
    except MemoryError as e:
        raise ImageTooLargeError(src) from e
    except (OSError, ValueError) as e:
        if isinstance(e, OSError) and is_disk_full(e):
            raise disk_full_error() from e
        name = target.lstrip(".").upper()
        raise ImageConvertError(src, f"'{src.name}' {name} olarak kaydedilemedi ({e}).") from e
    finally:
        with contextlib.suppress(OSError):
            tmp.unlink(missing_ok=True)
