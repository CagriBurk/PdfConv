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

KINDS: dict[str, str] = {
    ".pdf": "pdf",
    **dict.fromkeys(MARKDOWN_EXTS, "markdown"),
    **dict.fromkeys(TEXT_EXTS, "text"),
    **dict.fromkeys(IMAGE_EXTS, "image"),
    **dict.fromkeys(OFFICE_EXTS, "office"),
    **dict.fromkeys(HTML_EXTS, "html"),
}
