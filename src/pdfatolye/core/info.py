"""PDF hakkında bilgi: sayfa sayısı, boyutlar, şifre, metin var mı, yer imleri."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from pathlib import Path

from pdfatolye.core.pdfio import open_pdf, opened
from pdfatolye.errors import EncryptedPdfError

# Metin katmanı kontrolü için bakılacak en fazla sayfa (büyük belgede hızlı kalsın).
TEXT_SAMPLE_PAGES = 10
MM_PER_PT = 25.4 / 72

PAPER_SIZES_MM = {"A3": (297, 420), "A4": (210, 297), "A5": (148, 210), "Letter": (216, 279),
                  "Legal": (216, 356)}


@dataclass
class PageInfo:
    width: float  # nokta (1/72 inç), döndürme uygulanmış görünür boyut
    height: float
    rotation: int
    paper: str | None


@dataclass
class PdfInfo:
    path: str
    file_size: int
    encrypted: bool
    needs_password: bool
    page_count: int = 0
    pages: list[PageInfo] = field(default_factory=list)
    has_text: bool | None = None
    bookmark_count: int = 0
    metadata: dict[str, str] = field(default_factory=dict)
    pdf_version: str | None = None

    def to_dict(self) -> dict:
        return asdict(self)


def paper_name(width_pt: float, height_pt: float, tolerance_mm: float = 3) -> str | None:
    w, h = sorted((width_pt * MM_PER_PT, height_pt * MM_PER_PT))
    for name, (pw, ph) in PAPER_SIZES_MM.items():
        if abs(w - pw) <= tolerance_mm and abs(h - ph) <= tolerance_mm:
            return name
    return None


def inspect_pdf(path: Path, password: str | None = None) -> PdfInfo:
    """Şifreli ve şifresi verilmemiş belgede bile temel bilgiyi döndürür (hata atmaz)."""
    path = Path(path)
    try:
        doc = open_pdf(path, password)
    except EncryptedPdfError as e:
        if e.wrong_password:
            raise
        return PdfInfo(str(path), path.stat().st_size, encrypted=True, needs_password=True)

    with doc:
        pages = []
        for page in doc:
            rect = page.rect
            pages.append(PageInfo(round(rect.width, 2), round(rect.height, 2), page.rotation,
                                  paper_name(rect.width, rect.height)))
        sample = min(doc.page_count, TEXT_SAMPLE_PAGES)
        has_text = any(doc[i].get_text("text").strip() for i in range(sample))
        meta = doc.metadata or {}
        return PdfInfo(
            path=str(path),
            file_size=path.stat().st_size,
            # Şifre çözüldükten sonra da metadata'daki "encryption" alanı dolu kalır.
            encrypted=bool(meta.get("encryption")),
            needs_password=False,
            page_count=doc.page_count,
            pages=pages,
            has_text=has_text,
            bookmark_count=len(doc.get_toc(simple=True)),
            metadata={k: v for k, v in meta.items() if v and k not in ("format", "encryption")},
            pdf_version=(meta.get("format") or "").removeprefix("PDF ") or None,
        )


def page_count(path: Path, password: str | None = None) -> int:
    with opened(path, password) as doc:
        return doc.page_count
