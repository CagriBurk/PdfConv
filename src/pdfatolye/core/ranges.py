"""Sayfa aralığı ayrıştırıcı.

Kullanıcı 1'den sayar, çekirdek 0'dan. Dönüşüm yalnızca burada yapılır.

Sözdizimi (virgül veya noktalı virgülle ayrılmış parçalar):
    5        tek sayfa
    1-3      aralık (uçlar dahil)
    8-       8'den sona kadar
    -3       baştan 3'e kadar
    5-2      ters sıra: 5, 4, 3, 2
    son      son sayfa (ör. "son", "3-son")
    tümü     bütün sayfalar (boş metin de bütün sayfalar demektir)
"""

from __future__ import annotations

import re
import unicodedata

from pdfatolye.errors import PageRangeError

_LAST = {"son", "last", "n"}
_ALL = {"tümü", "tumu", "hepsi", "all", "*"}
_PART = re.compile(r"^(?P<a>[^-]*)(?P<dash>-)?(?P<b>[^-]*)$")
_DIGITS = re.compile(r"[0-9]+")  # yalnız ASCII rakam: "²" ya da "٣" sayfa numarası sayılmaz
_MAX_DIGITS = 9  # bundan uzun bir sayı hiçbir belgede sayfa olamaz; int() sınırına da takılmaz


def _key(text: str) -> str:
    """Anahtar sözcük karşılaştırması için: "HEPSİ" → "hepsi", ayrışık "tümü" → birleşik."""
    return unicodedata.normalize("NFC", text).strip().replace("İ", "i").lower()


def _unclear(part: str) -> PageRangeError:
    shown = part if len(part) <= 20 else part[:20] + "…"
    return PageRangeError(f"'{shown}' anlaşılmadı. Örnek: 1-3, 5, 8-")


def _number(token: str, page_count: int, part: str) -> int:
    token = _key(token)
    if token in _LAST:
        return page_count
    if not _DIGITS.fullmatch(token):
        raise _unclear(part)
    if len(token.lstrip("0")) > _MAX_DIGITS:
        raise PageRangeError(f"Sayfa numarası çok büyük; belgede {page_count} sayfa var.")
    n = int(token)
    if n < 1 or n > page_count:
        raise PageRangeError(f"{n}. sayfa yok; belgede {page_count} sayfa var.")
    return n


def parse_range_groups(spec: str, page_count: int) -> list[list[int]]:
    """Her parça ayrı bir grup olarak döner (bölme için). Sayfa numaraları 0 tabanlıdır."""
    if page_count < 1:
        raise PageRangeError("Belgede hiç sayfa yok.")
    text = (spec or "").strip()
    if not text or _key(text) in _ALL:
        return [list(range(page_count))]

    groups: list[list[int]] = []
    for raw in re.split(r"[,;]", text):
        part = raw.strip()
        if not part:
            continue
        if _key(part) in _ALL:
            groups.append(list(range(page_count)))
            continue
        # Boşluklar silinmez, yalnız uçlardan kırpılır: "1 3" on üçüncü sayfa değil, hatadır.
        m = _PART.match(part)
        if not m:
            raise _unclear(part)
        a, b = m["a"].strip(), m["b"].strip()
        if m["dash"] and not a and not b:
            raise _unclear(part)  # tek başına "-" ne başı ne sonu belirtir
        if not m["dash"]:
            n = _number(a, page_count, part)
            groups.append([n - 1])
            continue
        start = _number(a, page_count, part) if a else 1
        end = _number(b, page_count, part) if b else page_count
        step = 1 if end >= start else -1
        groups.append([p - 1 for p in range(start, end + step, step)])

    if not groups:
        raise PageRangeError("Sayfa aralığı boş.")
    return groups


def parse_ranges(spec: str, page_count: int) -> list[int]:
    """Aralığı yazıldığı sırayla düz bir listeye çevirir. Tekrarlar korunur."""
    return [p for group in parse_range_groups(spec, page_count) for p in group]


def format_pages(pages: list[int]) -> str:
    """0 tabanlı sayfa listesini kısa, 1 tabanlı metne çevirir: [0,1,2,5] → '1-3, 6'."""
    if not pages:
        return ""
    parts: list[str] = []
    start = prev = pages[0]
    for p in [*pages[1:], None]:
        if p is not None and p == prev + 1:
            prev = p
            continue
        parts.append(f"{start + 1}" if start == prev else f"{start + 1}-{prev + 1}")
        if p is not None:
            start = prev = p
    return ", ".join(parts)
