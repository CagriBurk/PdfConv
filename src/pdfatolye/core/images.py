"""Resim → PDF ve PDF → resim."""

from __future__ import annotations

import io
from collections.abc import Iterator, Sequence
from dataclasses import dataclass
from pathlib import Path

import pymupdf
from PIL import Image, ImageOps, UnidentifiedImageError

from pdfatolye.core.pdfio import opened, save_pdf
from pdfatolye.core.ranges import parse_ranges
from pdfatolye.errors import PageRangeError, UnsupportedFileError

try:  # iPhone fotoğrafları (HEIC/HEIF)
    from pillow_heif import register_heif_opener

    register_heif_opener()
except ImportError:  # pragma: no cover - isteğe bağlı
    pass

PT_PER_MM = 72 / 25.4
PAGE_SIZES_PT = {
    "A4": (595.0, 842.0),
    "A3": (842.0, 1191.0),
    "A5": (420.0, 595.0),
    "Letter": (612.0, 792.0),
    "Legal": (612.0, 1008.0),
}
# "resim" sayfa boyutunda DPI bilgisi olmayan/saçma olan resimler için varsayım.
DEFAULT_DPI = 150
# Tek sayfa için üretilecek en büyük resim (piksel). 300 DPI'da A3 ≈ 17,4 MP.
MAX_RENDER_PIXELS = 60_000_000


@dataclass
class _Frame:
    data: bytes  # PDF'e gömülecek bayt (JPEG veya PNG)
    width: int  # piksel, yönlendirme uygulanmış
    height: int
    dpi: float | None


def _frames(path: Path) -> Iterator[_Frame]:
    """Resmi (çok sayfalı TIFF dahil) PDF'e gömülmeye hazır karelere çevirir.

    Yönlendirmesi doğru bir JPEG baytları olduğu gibi kullanılır (yeniden sıkıştırma = kalite
    kaybı olmasın). Diğerleri EXIF'e göre döndürülüp PNG (saydamlık/çizim) ya da JPEG
    (fotoğraf) olarak yeniden kodlanır.
    """
    try:
        img = Image.open(path)
    except (UnidentifiedImageError, OSError) as e:
        raise UnsupportedFileError(path, "resim") from e

    with img:
        fmt = (img.format or "").upper()
        n_frames = getattr(img, "n_frames", 1)
        for index in range(n_frames):
            img.seek(index)
            dpi_info = img.info.get("dpi")
            dpi = float(dpi_info[0]) if dpi_info and dpi_info[0] else None
            orientation = img.getexif().get(0x0112, 1)

            if fmt == "JPEG" and n_frames == 1 and orientation == 1 and img.mode in ("RGB", "L"):
                yield _Frame(path.read_bytes(), img.width, img.height, dpi)
                continue

            frame = ImageOps.exif_transpose(img)
            has_alpha = frame.mode in ("RGBA", "LA", "PA") or (
                frame.mode == "P" and "transparency" in frame.info
            )
            buf = io.BytesIO()
            if has_alpha or fmt in ("PNG", "GIF", "BMP", "TIFF"):
                frame.convert("RGBA" if has_alpha else "RGB").save(buf, "PNG", optimize=True)
            else:
                frame.convert("RGB").save(buf, "JPEG", quality=92, subsampling=0)
            yield _Frame(buf.getvalue(), frame.width, frame.height, dpi)


def _page_size(frame: _Frame, page_size: str, orientation: str) -> tuple[float, float]:
    if page_size == "resim":
        dpi = frame.dpi if frame.dpi and 50 <= frame.dpi <= 1200 else DEFAULT_DPI
        return frame.width * 72 / dpi, frame.height * 72 / dpi
    if page_size not in PAGE_SIZES_PT:
        raise ValueError(f"Bilinmeyen sayfa boyutu: {page_size}")
    w, h = PAGE_SIZES_PT[page_size]
    landscape = (
        orientation == "yatay"
        or (orientation == "otomatik" and frame.width > frame.height)
    )
    return (h, w) if landscape else (w, h)


def images_to_pdf(
    images: Sequence[Path],
    output: Path,
    *,
    page_size: str = "A4",
    orientation: str = "otomatik",
    margin_mm: float = 0,
) -> Path:
    """Resimleri sırayla PDF sayfası yapar.

    page_size: 'A4', 'A3', 'A5', 'Letter', 'Legal' veya 'resim' (sayfa = resim boyutu).
    orientation: 'otomatik' (resme göre), 'dikey', 'yatay'. 'resim' boyutunda yok sayılır.
    Resim sayfaya oranı korunarak sığdırılır ve ortalanır.
    """
    if not images:
        raise ValueError("En az bir resim gerekli.")
    if orientation not in ("otomatik", "dikey", "yatay"):
        raise ValueError(f"Bilinmeyen yön: {orientation}")
    doc = pymupdf.open()
    try:
        for path in images:
            for frame in _frames(Path(path)):
                width, height = _page_size(frame, page_size, orientation)
                page = doc.new_page(width=width, height=height)
                margin = 0 if page_size == "resim" else margin_mm * PT_PER_MM
                box = pymupdf.Rect(margin, margin, width - margin, height - margin)
                if box.is_empty:
                    raise ValueError("Kenar boşluğu sayfadan büyük.")
                page.insert_image(box, stream=frame.data, keep_proportion=True)
        return save_pdf(doc, Path(output))
    finally:
        doc.close()


def pdf_to_images(
    input: Path,
    output_dir: Path,
    *,
    dpi: int = 150,
    fmt: str = "png",
    spec: str = "",
    jpg_quality: int = 90,
    password: str | None = None,
) -> list[Path]:
    """Sayfaları resim dosyası olarak kaydeder: '<ad>_<sayfa>.png'."""
    fmt = fmt.lower().replace("jpeg", "jpg")
    if fmt not in ("png", "jpg"):
        raise ValueError("Biçim 'png' ya da 'jpg' olmalı.")
    if not 36 <= dpi <= 600:
        raise ValueError("Çözünürlük 36 ile 600 DPI arasında olmalı.")
    input, output_dir = Path(input), Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    outputs: list[Path] = []
    with opened(input, password) as doc:
        pages = parse_ranges(spec, doc.page_count)
        width = len(str(doc.page_count))
        for p in dict.fromkeys(pages):  # tekrarları at, sırayı koru
            page = doc[p]
            scale = dpi / 72
            pixels = page.rect.width * scale * page.rect.height * scale
            if pixels > MAX_RENDER_PIXELS:
                raise PageRangeError(
                    f"{p + 1}. sayfa {dpi} DPI'da çok büyük bir resim olur; daha düşük DPI seç."
                )
            pix = page.get_pixmap(dpi=dpi, alpha=False)
            target = output_dir / f"{input.stem}_{p + 1:0{width}d}.{fmt}"
            if fmt == "png":
                pix.save(target)
            else:
                pix.save(target, jpg_quality=jpg_quality)
            outputs.append(target)
    return outputs


def extract_images(
    input: Path, output_dir: Path, *, min_size: int = 16, password: str | None = None
) -> list[Path]:
    """PDF'e gömülü resimleri yeniden kodlamadan, özgün biçimleriyle çıkarır."""
    input, output_dir = Path(input), Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    outputs: list[Path] = []
    seen: set[int] = set()
    with opened(input, password) as doc:
        for p in range(doc.page_count):
            for info in doc.get_page_images(p):
                xref, smask = info[0], info[1]
                if xref in seen:
                    continue
                seen.add(xref)
                data = doc.extract_image(xref)
                if not data or min(data["width"], data["height"]) < min_size:
                    continue
                if smask:  # saydamlık maskesi ayrı saklanır; birleştirip PNG yap
                    try:
                        pix = pymupdf.Pixmap(pymupdf.Pixmap(doc, xref), pymupdf.Pixmap(doc, smask))
                        image_bytes, ext = pix.tobytes("png"), "png"
                    except (RuntimeError, ValueError):
                        image_bytes, ext = data["image"], data["ext"]
                else:
                    image_bytes, ext = data["image"], data["ext"]
                target = output_dir / f"{input.stem}_s{p + 1}_{len(outputs) + 1}.{ext}"
                target.write_bytes(image_bytes)
                outputs.append(target)
    return outputs
