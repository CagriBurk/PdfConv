"""Kağıt boyutları: tek kaynak. Resim → PDF, Markdown → PDF, ayarlar, sayfa bilgisi ve arayüzün
listesi (`web/src/tools.ts` PAPERS; test tutarlılığı denetler) buradan türer."""

from __future__ import annotations

PT_PER_MM = 72 / 25.4

# Seçim listelerindeki sıra: en sık kullanılan önce, sonra büyüyen A serisi.
PAPER_SIZES_MM: dict[str, tuple[float, float]] = {
    "A4": (210, 297),
    "A5": (148, 210),
    "A3": (297, 420),
    "A2": (420, 594),
    "A1": (594, 841),
    "A0": (841, 1189),
    "Letter": (215.9, 279.4),
    "Legal": (215.9, 355.6),
}
PAPERS: tuple[str, ...] = tuple(PAPER_SIZES_MM)


def size_pt(name: str) -> tuple[float, float]:
    """Dikey (genişlik, yükseklik), nokta cinsinden. A4 → (595, 842)."""
    w, h = PAPER_SIZES_MM[name]
    return round(w * PT_PER_MM), round(h * PT_PER_MM)
