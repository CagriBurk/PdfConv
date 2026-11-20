"""Kelebek simgesi: tek kaynak paket/simge.py; arayüzdeki kopyalar onunla aynı olmalı."""

import importlib.util
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
_spec = importlib.util.spec_from_file_location("simge", ROOT / "paket" / "simge.py")
simge = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(simge)


def test_wings_are_mirror_symmetric():
    w = simge.wings()
    for (left, _), (right, _) in ((w[0], w[1]), (w[2], w[3])):
        assert right == [(round(simge.CANVAS - x, 1), y) for x, y in left]
    xs = [x for pts, _ in w for x, _ in pts]
    ys = [y for pts, _ in w for _, y in pts]
    assert abs((min(xs) + max(xs)) / 2 - simge.CANVAS / 2) < 0.1  # yatayda tam ortada
    assert abs((min(ys) + max(ys)) / 2 - simge.CANVAS / 2) < 3


def test_ico_has_every_size(tmp_path):
    out = tmp_path / "toolia.ico"
    simge.write_ico(out)
    with Image.open(out) as im:
        assert sorted(im.info["sizes"]) == [(s, s) for s in simge.ICO_SIZES]
    big = simge.render(1024)
    assert big.getpixel((5, 5))[3] == 0  # karonun dışı saydam (koyu çerçeve yok)
    assert big.getpixel((512, 80))[:3] == (255, 255, 255)  # karo beyaz


def test_ui_copies_match_source():
    svg = simge.svg()
    mark = (ROOT / "web" / "src" / "components" / "BrandMark.tsx").read_text(encoding="utf-8")
    for pts, color in simge.wings():
        coords = " ".join(f"{x:g},{y:g}" for x, y in pts)
        assert f'points="{coords}" fill="{color}"' in mark
        assert f'points="{coords}" fill="{color}"' in svg
    index = (ROOT / "web" / "index.html").read_text(encoding="utf-8")
    uri = "data:image/svg+xml," + svg.replace('"', "'").replace("#", "%23")
    assert f'<link rel="icon" href="{uri}" />' in index
