"""Toolia simgesi (kelebek): tek kaynak.

Beyaz karo üzerinde dört geometrik kanat, uygulamanın dört araç grubu renginde. Geometri
referans tasarımdan ölçüldü; yalnız sol kanatlar tanımlıdır, sağdakiler tam aynasıdır (simetri
milimetrik). Buradan üretilenler:
- masaüstü / kısayol simgesi `toolia.ico` (16–256 px; `derle.make_icon`)
- arayüzün sekme simgesi (`web/index.html`) ve üst çubuk logosu (`TopBar.tsx` BrandMark)
  için SVG; `tests/test_simge.py` ikisinin buradakiyle aynı olduğunu denetler.

    uv run python paket/simge.py   → SVG'yi ve 1024 px PNG önizlemeyi yazdırır
"""

from __future__ import annotations

from pathlib import Path

BLUE, VIOLET, GREEN, AMBER = "#2E5BE6", "#7C4DDB", "#22A06B", "#F5A524"
EDGE = "#E3E6EC"
CANVAS = 1024
TILE = (40, 40, 984, 984)
RADIUS = 176
EDGE_WIDTH = 6
ICO_SIZES = (16, 24, 32, 48, 64, 128, 256)

# Referans tasarımdaki sol kanatlar (1024 px; simetri ekseni x = 511.5, orta y = 511)
_AXIS, _MID_Y, _SCALE = 511.5, 511.0, 1.31
_UPPER_LEFT = [(244, 290), (398, 332), (499, 437), (499, 498), (320, 498), (279, 455)]
_LOWER_LEFT = [(308, 577), (360, 523), (499, 523), (499, 604), (413, 736), (328, 655)]


def wings() -> list[tuple[list[tuple[float, float]], str]]:
    """Dört kanat: (köşeler, renk). Koordinatlar 1024'lük tuvalde, 0,1 px'e yuvarlanmış."""
    def tr(p: tuple[int, int]) -> tuple[float, float]:
        return (round((p[0] - _AXIS) * _SCALE + CANVAS / 2, 1),
                round((p[1] - _MID_Y) * _SCALE + CANVAS / 2, 1))

    out = []
    for poly, (left_color, right_color) in ((_UPPER_LEFT, (BLUE, VIOLET)),
                                            (_LOWER_LEFT, (GREEN, AMBER))):
        left = [tr(p) for p in poly]
        right = [(round(CANVAS - x, 1), y) for x, y in left]
        out += [(left, left_color), (right, right_color)]
    return out


def svg() -> str:
    """Tek satır SVG (viewBox 1024): karo + kanatlar."""
    x0, y0, x1, y1 = TILE
    half = EDGE_WIDTH / 2
    parts = [f'<rect x="{x0 + half:g}" y="{y0 + half:g}" width="{x1 - x0 - EDGE_WIDTH:g}" '
             f'height="{y1 - y0 - EDGE_WIDTH:g}" rx="{RADIUS - half:g}" fill="#fff" '
             f'stroke="{EDGE}" stroke-width="{EDGE_WIDTH}"/>']
    for pts, color in wings():
        coords = " ".join(f"{x:g},{y:g}" for x, y in pts)
        parts.append(f'<polygon points="{coords}" fill="{color}"/>')
    return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {CANVAS} {CANVAS}">'
            + "".join(parts) + "</svg>")


def render(size: int):
    """Simgeyi `size` px RGBA olarak çizer (4× büyük çizip küçültür: yumuşak kenar)."""
    from PIL import Image, ImageDraw

    n = max(size, 256) * 4
    k = n / CANVAS
    img = Image.new("RGBA", (n, n), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.rounded_rectangle([v * k for v in TILE], radius=RADIUS * k, fill="white",
                        outline=EDGE, width=max(1, round(EDGE_WIDTH * k)))
    for pts, color in wings():
        d.polygon([(x * k, y * k) for x, y in pts], fill=color)
    return img.resize((size, size), Image.LANCZOS)


def write_ico(path: Path) -> None:
    """Her boyut ayrı çizilir (büyük resmi küçültmekten daha keskin)."""
    images = [render(s) for s in ICO_SIZES]
    path.parent.mkdir(parents=True, exist_ok=True)
    images[-1].save(path, format="ICO", sizes=[(s, s) for s in ICO_SIZES],
                    append_images=images[:-1])


if __name__ == "__main__":
    print(svg())
    out = Path("build") / "toolia-simge-1024.png"
    out.parent.mkdir(exist_ok=True)
    render(1024).save(out)
    print("önizleme:", out)
