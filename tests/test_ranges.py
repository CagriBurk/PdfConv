import pytest

from toolia.core.ranges import format_pages, parse_range_groups, parse_ranges
from toolia.errors import PageRangeError


@pytest.mark.parametrize(
    ("spec", "expected"),
    [
        ("", list(range(10))),
        ("tümü", list(range(10))),
        ("1", [0]),
        ("1-3", [0, 1, 2]),
        ("1-3,5", [0, 1, 2, 4]),
        ("8-", [7, 8, 9]),
        ("-3", [0, 1, 2]),
        ("5-3", [4, 3, 2]),
        ("son", [9]),
        ("3-son", [2, 3, 4, 5, 6, 7, 8, 9]),
        (" 1 - 2 ; 4 ", [0, 1, 3]),
        ("3,1,2", [2, 0, 1]),
        ("2,2", [1, 1]),
        ("1-3,,5,", [0, 1, 2, 4]),
        ("SON", [9]),
        ("HEPSİ", list(range(10))),
        ("1, HEPSİ", [0, *range(10)]),
        ("tümü", list(range(10))),  # ayrışık (NFD) yazılmış "tümü"
        ("3 - SON", [2, 3, 4, 5, 6, 7, 8, 9]),
        ("007", [6]),
    ],
)
def test_parse_ranges(spec, expected):
    assert parse_ranges(spec, 10) == expected


@pytest.mark.parametrize(
    ("spec", "message"),
    [
        ("0", "0. sayfa yok"),
        ("11", "11. sayfa yok"),
        ("3-12", "12. sayfa yok"),
        ("a", "anlaşılmadı"),
        ("1-2-3", "anlaşılmadı"),
        ("1.5", "anlaşılmadı"),
        (",", "boş"),
        # Rakam gibi görünen ama ASCII olmayan karakterler ValueError değil, PageRangeError verir.
        ("²", "anlaşılmadı"),
        ("1-³", "anlaşılmadı"),
        ("٣", "anlaşılmadı"),
        ("9" * 4301, "çok büyük"),
        ("1" + "0" * 9, "çok büyük"),
        # Parça içindeki boşluk sayıları birleştirmez: "1 3" on üçüncü sayfa değildir.
        ("1 3", "anlaşılmadı"),
        ("1 2-5", "anlaşılmadı"),
        # Tek başına tire ne başı ne sonu belirtir.
        ("-", "anlaşılmadı"),
        ("1, -, 3", "anlaşılmadı"),
    ],
)
def test_parse_ranges_errors(spec, message):
    with pytest.raises(PageRangeError, match=message):
        parse_ranges(spec, 10)


def test_empty_document_is_an_error():
    with pytest.raises(PageRangeError):
        parse_ranges("1", 0)


def test_groups_keep_parts_separate():
    assert parse_range_groups("1-3, 4-5, 9-", 10) == [[0, 1, 2], [3, 4], [8, 9]]


@pytest.mark.parametrize(
    ("pages", "text"),
    [
        ([], ""),
        ([0], "1"),
        ([0, 1, 2, 5], "1-3, 6"),
        ([4, 3], "5, 4"),
        ([0, 2, 3, 4, 9], "1, 3-5, 10"),
    ],
)
def test_format_pages(pages, text):
    assert format_pages(pages) == text


def test_format_roundtrip():
    pages = [0, 1, 2, 6, 8, 9]
    assert parse_ranges(format_pages(pages), 10) == pages
