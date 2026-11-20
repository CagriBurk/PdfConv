"""Dosya türleri: tek kaynak. Depo (`storage.KINDS`), Office dönüşümü, komut satırı ve arayüzün
kabul listeleri (`web/src/tools.ts` ACCEPT; test tutarlılığı denetler) buradan türer."""

from __future__ import annotations

OFFICE_EXTS = frozenset({
    ".docx", ".doc", ".docm", ".odt", ".rtf", ".wpd",
    ".xlsx", ".xls", ".xlsm", ".ods", ".csv",
    ".pptx", ".ppt", ".pptm", ".odp",
})
# Resim → PDF'in (Pillow) açabildikleri.
RASTER_IMAGE_EXTS = frozenset({".png", ".jpg", ".jpeg", ".webp", ".gif", ".bmp", ".tif",
                               ".tiff", ".heic", ".heif"})
# Markdown notlarında resim olarak kullanılabilenler (tarayıcı çizer).
IMAGE_EXTS = RASTER_IMAGE_EXTS | {".svg"}
MARKDOWN_EXTS = frozenset({".md", ".markdown"})
TEXT_EXTS = frozenset({".txt"})
HTML_EXTS = frozenset({".html", ".htm"})

# --- Biçim dönüştürme (PDF dışı) -------------------------------------------------------------
# Yalnız sık kullanılan hedefler (bilinçli olarak dar tutuldu). Resimler Pillow ile, Office
# belgeleri LibreOffice ile aynı aile içinde çevrilir. Arayüzdeki kopya: `web/src/tools.ts`
# CONVERT_TARGETS (tests/test_robustness.py tutarlılığı denetler).
IMAGE_CONVERT_TARGETS: tuple[str, ...] = (".jpg", ".png", ".webp", ".tiff")
OFFICE_CONVERT_FAMILIES: dict[str, tuple[frozenset[str], tuple[str, ...]]] = {
    # aile: (kaynak uzantılar, hedef uzantılar)
    "word": (frozenset({".docx", ".doc", ".docm", ".odt", ".rtf", ".wpd"}),
             (".docx", ".odt", ".rtf", ".txt")),
    "sheet": (frozenset({".xlsx", ".xls", ".xlsm", ".ods", ".csv"}),
              (".xlsx", ".ods", ".csv")),
    "slides": (frozenset({".pptx", ".ppt", ".pptm", ".odp"}),
               (".pptx", ".odp")),
}
ALL_CONVERT_TARGETS = frozenset(IMAGE_CONVERT_TARGETS).union(
    *(targets for _, targets in OFFICE_CONVERT_FAMILIES.values()))
# Aynı biçime "dönüştürme" anlamsız; JPEG'in iki yazılışı da aynı biçimdir.
_SAME = {".jpeg": ".jpg", ".tif": ".tiff", ".heif": ".heic"}


def same_format(ext: str) -> str:
    """Uzantının biçim adı: '.jpeg' → '.jpg', '.tif' → '.tiff'."""
    ext = ext.lower()
    return _SAME.get(ext, ext)


def family_targets(ext: str) -> tuple[str, ...]:
    """Kaynağın ailesindeki bütün hedefler, kendi biçimi dahil (karışık seçimde ortak hedef
    için: JPG + PNG → JPG seçilebilsin; zaten JPG olan dosya olduğu gibi alınır)."""
    ext = ext.lower()
    if ext in RASTER_IMAGE_EXTS:
        return IMAGE_CONVERT_TARGETS
    for sources, targets in OFFICE_CONVERT_FAMILIES.values():
        if ext in sources:
            return targets
    return ()


def convert_targets(ext: str) -> tuple[str, ...]:
    """Kaynak uzantının çevrilebileceği hedefler (kendisi hariç). Desteklenmiyorsa boş."""
    return tuple(t for t in family_targets(ext) if t != same_format(ext))


KINDS: dict[str, str] = {
    ".pdf": "pdf",
    **dict.fromkeys(MARKDOWN_EXTS, "markdown"),
    **dict.fromkeys(TEXT_EXTS, "text"),
    **dict.fromkeys(IMAGE_EXTS, "image"),
    **dict.fromkeys(OFFICE_EXTS, "office"),
    **dict.fromkeys(HTML_EXTS, "html"),
}
