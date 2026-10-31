from pathlib import Path

import pymupdf
import pytest

from pdfatolye.core import pages
from pdfatolye.core.pages import BlankPage, PageRef, compose
from pdfatolye.errors import EncryptedPdfError, PageRangeError
from tests.fixtures import make_fixtures as fx


@pytest.fixture
def ten(tmp_path: Path) -> Path:
    return fx.numbered(tmp_path / "on.pdf", 10)


@pytest.fixture
def three(tmp_path: Path) -> Path:
    return fx.numbered(tmp_path / "uc.pdf", 3, label="Ek")


def rotations(path: Path) -> list[int]:
    with pymupdf.open(path) as doc:
        return [p.rotation for p in doc]


def toc(path: Path) -> list[list]:
    with pymupdf.open(path) as doc:
        return doc.get_toc(simple=True)


# --- birleştirme -------------------------------------------------------------------------


def test_merge_order_and_bookmark_offsets(ten, three, tmp_path):
    out = pages.merge([three, ten], tmp_path / "m.pdf")
    assert fx.labels(out) == [f"Ek {i}" for i in (1, 2, 3)] + [f"Sayfa {i}" for i in range(1, 11)]
    # "on.pdf"nin yer imleri 3 sayfa kaymalı
    assert toc(out) == [[1, "Bölüm 1", 4], [2, "Kısım 1.1", 5], [2, "Kısım 1.2", 7],
                        [1, "Bölüm 2", 9]]


def test_merge_bookmark_per_file(ten, three, tmp_path):
    out = pages.merge([three, ten], tmp_path / "m.pdf", bookmark_per_file=True)
    assert toc(out) == [
        [1, "uc", 1],
        [1, "on", 4], [2, "Bölüm 1", 4], [3, "Kısım 1.1", 5], [3, "Kısım 1.2", 7],
        [2, "Bölüm 2", 9],
    ]


def test_merge_keeps_internal_links(tmp_path):
    linked = fx.with_link(tmp_path / "link.pdf")
    other = fx.numbered(tmp_path / "x.pdf", 2, label="Ek", with_toc=False)
    out = pages.merge([other, linked], tmp_path / "m.pdf")
    with pymupdf.open(out) as doc:
        links = doc[2].get_links()  # link.pdf'in 1. sayfası artık 3. sayfa
        assert len(links) == 1
        assert links[0]["page"] == 4  # 3. sayfası artık 5. sayfa (0 tabanlı 4)


def test_turkish_text_survives(ten, tmp_path):
    out = pages.select(ten, "2,1", tmp_path / "s.pdf")
    with pymupdf.open(out) as doc:
        # MuPDF boşlukları bölünmez boşluk (U+00A0) olarak okuyabiliyor.
        assert fx.TURKISH in doc[0].get_text().replace("\xa0", " ")


def test_encrypted_source(tmp_path):
    enc = fx.numbered(tmp_path / "sifreli.pdf", 3, password="gizli")
    with pytest.raises(EncryptedPdfError, match="şifreli"):
        pages.select(enc, "1", tmp_path / "x.pdf")
    with pytest.raises(EncryptedPdfError, match="yanlış"):
        pages.select(enc, "1", tmp_path / "x.pdf", password="yanlis")
    out = pages.select(enc, "3,1", tmp_path / "x.pdf", password="gizli")
    assert fx.labels(out) == ["Sayfa 3", "Sayfa 1"]
    with pymupdf.open(out) as doc:
        assert not doc.needs_pass


# --- seçme / silme / sıralama -----------------------------------------------------------


def test_select_reorders(ten, tmp_path):
    out = pages.select(ten, "10, 1-2", tmp_path / "s.pdf")
    assert fx.labels(out) == ["Sayfa 10", "Sayfa 1", "Sayfa 2"]


def test_select_drops_bookmarks_of_removed_pages(ten, tmp_path):
    out = pages.select(ten, "1, 6-7", tmp_path / "s.pdf")
    # Kısım 1.1 (s.2) ve 1.2 (s.4) düştü; Bölüm 2 (s.6) artık 2. sayfada
    assert toc(out) == [[1, "Bölüm 1", 1], [1, "Bölüm 2", 2]]


def test_toc_levels_are_repaired(ten, tmp_path):
    # Bölüm 1 (s.1) düşer, alt başlıklar kalır: 2. seviye yetim kalmamalı
    out = pages.select(ten, "2-10", tmp_path / "s.pdf")
    assert toc(out) == [[1, "Kısım 1.1", 1], [2, "Kısım 1.2", 3], [1, "Bölüm 2", 5]]


def test_delete(ten, tmp_path):
    out = pages.delete(ten, "2-9", tmp_path / "d.pdf")
    assert fx.labels(out) == ["Sayfa 1", "Sayfa 10"]


def test_delete_all_is_refused(ten, tmp_path):
    with pytest.raises(PageRangeError, match="en az bir sayfa"):
        pages.delete(ten, "1-10", tmp_path / "d.pdf")
    assert not (tmp_path / "d.pdf").exists()


def test_in_place_edit(ten):
    pages.delete(ten, "1", ten)
    assert fx.labels(ten)[0] == "Sayfa 2"
    assert len(list(ten.parent.glob(".tmp-*"))) == 0


# --- döndürme ---------------------------------------------------------------------------


def test_rotate_adds_to_existing_rotation(tmp_path):
    src = fx.rotated(tmp_path / "r.pdf")
    out = pages.rotate(src, 90, tmp_path / "o.pdf")
    assert rotations(out) == [90, 180, 270, 0]
    assert fx.labels(out) == ["Sayfa 1", "Sayfa 2", "Sayfa 3", "Sayfa 4"]


def test_rotate_only_selected_pages(tmp_path):
    src = fx.rotated(tmp_path / "r.pdf")
    out = pages.rotate(src, -90, tmp_path / "o.pdf", spec="1,3")
    assert rotations(out) == [270, 90, 90, 270]


def test_rotate_rejects_odd_angles(ten, tmp_path):
    with pytest.raises(PageRangeError, match="90'ın katı"):
        pages.rotate(ten, 45, tmp_path / "o.pdf")


# --- ekleme -----------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("after", "expected_first"),
    [(0, ["Ek 1", "Ek 2", "Ek 3", "Sayfa 1"]), (2, ["Sayfa 1", "Sayfa 2", "Ek 1", "Ek 2"])],
)
def test_insert(ten, three, tmp_path, after, expected_first):
    out = pages.insert(ten, three, after, tmp_path / "i.pdf")
    got = fx.labels(out)
    assert len(got) == 13
    assert got[:4] == expected_first


def test_insert_at_end_with_range(ten, three, tmp_path):
    out = pages.insert(ten, three, 10, tmp_path / "i.pdf", spec="3")
    assert fx.labels(out)[-2:] == ["Sayfa 10", "Ek 3"]


def test_insert_out_of_bounds(ten, three, tmp_path):
    with pytest.raises(PageRangeError):
        pages.insert(ten, three, 11, tmp_path / "i.pdf")


def test_blank_pages_take_previous_size(tmp_path):
    src = fx.mixed_sizes(tmp_path / "m.pdf")
    out = pages.insert_blank(src, 2, tmp_path / "b.pdf", count=2)
    with pymupdf.open(out) as doc:
        sizes = [(round(p.rect.width), round(p.rect.height)) for p in doc]
    assert sizes == [(595, 842), (842, 595), (842, 595), (842, 595), (612, 792)]
    assert fx.labels(out) == ["Sayfa 1", "Sayfa 2", "", "", "Sayfa 3"]


def test_blank_page_first_defaults_to_a4(tmp_path):
    src = fx.mixed_sizes(tmp_path / "m.pdf")
    out = compose([src], [BlankPage(), PageRef(0, 2)], tmp_path / "b.pdf")
    with pymupdf.open(out) as doc:
        assert (round(doc[0].rect.width), round(doc[0].rect.height)) == (595, 842)


# --- manifest (çok kaynak, karışık) ------------------------------------------------------


def test_compose_interleaved_sources(ten, three, tmp_path):
    items = [PageRef(1, 0), PageRef(0, 4, 180), PageRef(1, 2), PageRef(0, 0), PageRef(0, 1)]
    out = compose([ten, three], items, tmp_path / "c.pdf")
    assert fx.labels(out) == ["Ek 1", "Sayfa 5", "Ek 3", "Sayfa 1", "Sayfa 2"]
    assert rotations(out) == [0, 180, 0, 0, 0]


def test_compose_duplicate_page(ten, tmp_path):
    out = compose([ten], [PageRef(0, 0), PageRef(0, 0)], tmp_path / "c.pdf")
    assert fx.labels(out) == ["Sayfa 1", "Sayfa 1"]


def test_compose_rejects_bad_page(ten, tmp_path):
    with pytest.raises(PageRangeError, match="11. sayfa yok"):
        compose([ten], [PageRef(0, 10)], tmp_path / "c.pdf")


def test_compose_rejects_empty(ten, tmp_path):
    with pytest.raises(PageRangeError):
        compose([ten], [], tmp_path / "c.pdf")


def test_merged_output_does_not_bloat(ten, tmp_path):
    # Aynı fontu kullanan 10 sayfayı tek tek seçmek font kopyası üretmemeli.
    whole = pages.select(ten, "", tmp_path / "a.pdf")
    shuffled = pages.select(ten, "10,1,9,2,8,3,7,4,6,5", tmp_path / "b.pdf")
    assert shuffled.stat().st_size < whole.stat().st_size * 1.3


# --- bölme ------------------------------------------------------------------------------


def test_split_each_page(ten, tmp_path):
    outs = pages.split(ten, tmp_path / "p")
    assert [o.name for o in outs[:2]] == ["on_01.pdf", "on_02.pdf"]
    assert len(outs) == 10
    assert fx.labels(outs[9]) == ["Sayfa 10"]


def test_split_every_n(ten, tmp_path):
    outs = pages.split(ten, tmp_path / "p", mode="n", every=4)
    assert [o.name for o in outs] == ["on_1-4.pdf", "on_5-8.pdf", "on_9-10.pdf"]
    assert fx.labels(outs[2]) == ["Sayfa 9", "Sayfa 10"]


def test_split_ranges(ten, tmp_path):
    outs = pages.split(ten, tmp_path / "p", mode="aralik", spec="1-2, 5, 9-")
    assert [fx.labels(o) for o in outs] == [["Sayfa 1", "Sayfa 2"], ["Sayfa 5"],
                                           ["Sayfa 9", "Sayfa 10"]]


def test_split_by_bookmarks(ten, tmp_path):
    outs = pages.split(ten, tmp_path / "p", mode="yer-imi")
    assert [o.name for o in outs] == ["on_1 Bölüm 1.pdf", "on_2 Bölüm 2.pdf"]
    assert len(fx.labels(outs[0])) == 5
    assert fx.labels(outs[1])[0] == "Sayfa 6"


def test_split_by_bookmarks_without_any(tmp_path):
    src = fx.numbered(tmp_path / "a.pdf", 3, with_toc=False)
    with pytest.raises(PageRangeError, match="yer imi yok"):
        pages.split(src, tmp_path / "p", mode="yer-imi")
