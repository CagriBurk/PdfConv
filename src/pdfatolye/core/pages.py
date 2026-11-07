"""Sayfa işlemleri. Hepsi tek bir fikre dayanır: sayfa manifestosu (PLAN.md §4.3).

Manifest, çıktının sayfalarını sırayla listeler: "şu kaynağın şu sayfası, şu kadar döndürülmüş"
ya da "boş sayfa". Birleştirme, sıralama, silme, döndürme, sayfa ekleme bunun özel hâlleridir.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path

import pymupdf

from pdfatolye.core.pdfio import open_pdf, opened, safe_filename, save_pdf
from pdfatolye.core.ranges import parse_range_groups, parse_ranges
from pdfatolye.errors import PageRangeError

A4 = (595.0, 842.0)  # nokta


@dataclass(frozen=True)
class PageRef:
    source: int  # `sources` listesindeki sıra
    page: int  # 0 tabanlı
    rotate: int = 0  # kaynaktaki döndürmeye EK olarak, 90'ın katı


@dataclass(frozen=True)
class BlankPage:
    width: float | None = None  # None: bir önceki sayfanın boyutu (yoksa A4)
    height: float | None = None


ManifestItem = PageRef | BlankPage


def _check_rotation(angle: int) -> int:
    if angle % 90:
        raise PageRangeError(f"Döndürme açısı 90'ın katı olmalı ({angle} verildi).")
    return angle % 360


def _runs(items: Sequence[ManifestItem]) -> list[tuple[ManifestItem, int]]:
    """Aynı kaynaktan ardışık, aynı açıyla gelen sayfaları tek parçada toplar.

    Tek `insert_pdf` çağrısı hem hızlıdır hem de parça içi bağlantıları (link) korur.
    Dönen her öğe: (ilk öğe, parçadaki sayfa sayısı).
    """
    runs: list[tuple[ManifestItem, int]] = []
    for item in items:
        if runs and isinstance(item, PageRef):
            first, length = runs[-1]
            if (
                isinstance(first, PageRef)
                and first.source == item.source
                and first.rotate == item.rotate
                and first.page + length == item.page
            ):
                runs[-1] = (first, length + 1)
                continue
        runs.append((item, 1))
    return runs


def _fix_toc_levels(toc: list[list]) -> list[list]:
    """Silinen yer imleri yüzünden seviye atlamalarını düzeltir (1 → 3 geçersizdir)."""
    fixed: list[list] = []
    prev = 0
    for level, title, page in toc:
        level = max(1, min(level, prev + 1))
        fixed.append([level, title, page])
        prev = level
    return fixed


def compose(
    sources: Sequence[Path],
    items: Sequence[ManifestItem],
    output: Path,
    *,
    passwords: Sequence[str | None] | None = None,
    keep_bookmarks: bool = True,
    bookmark_per_file: bool = False,
    bookmark_titles: Sequence[str] | None = None,
    on_progress: Callable[[float], None] | None = None,
) -> Path:
    """Manifestteki sayfalardan yeni bir PDF yazar.

    - Kaynaktaki döndürme korunur, `rotate` üstüne eklenir.
    - Belge bilgileri (başlık, yazar, XMP) çıktıda ilk görünen kaynaktan alınır; sayfa
      etiketleri (i, ii, 1, 2...) sayfalarla birlikte taşınır; gömülü dosyalar korunur.
    - Yer imleri sayfa kaymasına göre yeniden hesaplanır; sayfası çıkarılanlar düşer.
      (Hedef, sayfanın başı olur; sayfa içi konum korunmaz.)
    - Şifreli kaynaklar çözülmüş olarak yazılır.
    - `output` kaynaklardan biri olabilir; yazım geçici dosya üzerinden yapılır.
    """
    if not items:
        raise PageRangeError("Çıktıda hiç sayfa kalmıyor.")
    passwords = list(passwords or [None] * len(sources))
    docs: list[pymupdf.Document] = []
    out = pymupdf.open()
    try:
        for src, pw in zip(sources, passwords, strict=True):
            docs.append(open_pdf(Path(src), pw))

        for item in items:
            if isinstance(item, PageRef):
                if not 0 <= item.source < len(docs):
                    raise PageRangeError(f"Geçersiz kaynak numarası: {item.source}")
                if not 0 <= item.page < docs[item.source].page_count:
                    name = Path(sources[item.source]).name
                    raise PageRangeError(f"'{name}' içinde {item.page + 1}. sayfa yok.")
                _check_rotation(item.rotate)

        runs = _runs(items)
        # insert_pdf'te final=False, aynı kaynaktan sonraki çağrılar için ortak nesneleri
        # (font, resim) hatırlar; böylece çıktı şişmez. Kaynağın son parçasında True olmalı.
        last_run_of_source = {}
        for i, (first, _) in enumerate(runs):
            if isinstance(first, PageRef):
                last_run_of_source[first.source] = i

        # kaynak → {kaynak sayfası: çıktıdaki ilk konumu}
        placement: dict[int, dict[int, int]] = {}
        first_out_page: dict[int, int] = {}
        for i, (first, length) in enumerate(runs):
            if isinstance(first, BlankPage):
                prev = out[-1].rect if out.page_count else None
                width = first.width or (prev.width if prev else A4[0])
                height = first.height or (prev.height if prev else A4[1])
                out.new_page(width=width, height=height)
                continue
            src = docs[first.source]
            start_at = out.page_count
            out.insert_pdf(
                src,
                from_page=first.page,
                to_page=first.page + length - 1,
                final=i == last_run_of_source[first.source],
            )
            for k in range(length):
                src_page = first.page + k
                placement.setdefault(first.source, {}).setdefault(src_page, start_at + k)
                first_out_page.setdefault(first.source, start_at + k)
                if first.rotate:
                    page = out[start_at + k]
                    page.set_rotation((src[src_page].rotation + first.rotate) % 360)
            if on_progress:  # iptal edilen iş burada durur (JobCancelled)
                on_progress((i + 1) / len(runs))

        if keep_bookmarks or bookmark_per_file:
            toc = _build_toc(
                docs, sources, placement, first_out_page,
                keep_bookmarks, bookmark_per_file, bookmark_titles,
            )
            out.set_toc(toc)
        _carry_document_info(docs, items, out)

        # Kaynaklar kaydetmeden önce kapanmalı: Windows açık dosyanın üstüne yazdırmaz
        # (çıktı = girdi olduğunda). insert_pdf nesneleri kopyaladığı için `out` bağımsızdır.
        _close_all(docs)
        return save_pdf(out, Path(output))
    finally:
        out.close()
        _close_all(docs)


_INFO_KEYS = ("title", "author", "subject", "keywords", "creator", "producer", "creationDate")


def _carry_document_info(docs: list[pymupdf.Document], items: Sequence[ManifestItem],
                         out: pymupdf.Document) -> None:
    """`pymupdf.open()` boş belgeyle başlar: başlık, yazar, sayfa etiketleri ve gömülü dosyalar
    düşerdi. Belge bilgisi çıktıda ilk görünen kaynaktan (birleştirmede ilk dosya) alınır."""
    used = list(dict.fromkeys(i.source for i in items if isinstance(i, PageRef)))
    if not used:
        return
    first = docs[used[0]]
    info = first.metadata or {}
    out.set_metadata({k: info.get(k) or "" for k in _INFO_KEYS}
                     | {"modDate": pymupdf.get_pdf_now()})
    xml = first.get_xml_metadata()
    if xml:
        out.set_xml_metadata(xml)
    labels = _carried_labels(docs, items)
    if labels:
        out.set_page_labels(labels)
    taken = set(out.embfile_names())
    for s in used:
        src = docs[s]
        for name in src.embfile_names():
            meta = src.embfile_info(name)
            new, n = name, 2
            while new in taken:  # iki kaynakta aynı adlı ek
                new, n = f"{name} ({n})", n + 1
            taken.add(new)
            out.embfile_add(new, src.embfile_get(name), filename=meta.get("filename"),
                            ufilename=meta.get("ufilename"), desc=meta.get("description"))


def _carried_labels(docs: list[pymupdf.Document], items: Sequence[ManifestItem]) -> list[dict]:
    """Her çıktı sayfası kaynaktaki etiketini taşır. Ardışık sayfalar aynı kuralla devam ettikçe
    tek kural yazılır ("i, ii" ve "1, 2, 3" sıralandıktan sonra da doğru). Etiketsiz kaynakta
    ya da boş sayfada etiket sayfanın kendi numarasıdır (birleştirmede de anlamlı kalsın)."""
    rules_of = {s: docs[s].get_page_labels() for s in {i.source for i in items
                                                      if isinstance(i, PageRef)}}
    if not any(rules_of.values()):
        return []
    out: list[dict] = []
    prev: tuple | None = None  # (kaynak, kural no, kaynak sayfası)
    for idx, item in enumerate(items):
        rules = rules_of.get(item.source) if isinstance(item, PageRef) else None
        if not rules:
            out.append({"startpage": idx, "prefix": "", "style": "D", "firstpagenum": idx + 1})
            prev = None
            continue
        page = item.page
        r = max((k for k, rule in enumerate(rules) if rule["startpage"] <= page), default=None)
        if r is None:  # ilk kuraldan önceki sayfalar: düz numara
            rule = {"prefix": "", "style": "D", "startpage": 0, "firstpagenum": 1}
        else:
            rule = rules[r]
        if prev and prev == (item.source, r, page - 1):
            prev = (item.source, r, page)
            continue
        out.append({"startpage": idx, "prefix": rule.get("prefix", ""),
                    "style": rule.get("style", ""),
                    "firstpagenum": rule.get("firstpagenum", 1) + page - rule["startpage"]})
        prev = (item.source, r, page)
    # Aynı biçimde ardışık devam eden kuralları birleştir (etiketsiz sayfalar 1, 2, 3...).
    merged: list[dict] = []
    for rule in out:
        last = merged[-1] if merged else None
        if (last and last["style"] == rule["style"] == "D" and last["prefix"] == rule["prefix"]
                and last["firstpagenum"] + rule["startpage"] - last["startpage"]
                == rule["firstpagenum"]):
            continue
        merged.append(rule)
    return merged


def _close_all(docs: list[pymupdf.Document]) -> None:
    for d in docs:
        if not d.is_closed:
            d.close()


def _build_toc(
    docs: list[pymupdf.Document],
    sources: Sequence[Path],
    placement: dict[int, dict[int, int]],
    first_out_page: dict[int, int],
    keep_bookmarks: bool,
    bookmark_per_file: bool,
    bookmark_titles: Sequence[str] | None,
) -> list[list]:
    toc: list[list] = []
    # Kaynaklar çıktıda ilk göründükleri sırayla.
    for s in sorted(first_out_page, key=first_out_page.__getitem__):
        shift = 0
        if bookmark_per_file:
            title = bookmark_titles[s] if bookmark_titles else Path(sources[s]).stem
            toc.append([1, title, first_out_page[s] + 1])
            shift = 1
        if not keep_bookmarks:
            continue
        for level, title, page in docs[s].get_toc(simple=True):
            out_page = placement[s].get(page - 1)
            if out_page is not None:
                toc.append([level + shift, title, out_page + 1])
    return _fix_toc_levels(toc)


# --- Kolay kullanım fonksiyonları -------------------------------------------------------


def merge(
    inputs: Sequence[Path],
    output: Path,
    *,
    passwords: Sequence[str | None] | None = None,
    bookmark_per_file: bool = False,
    bookmark_titles: Sequence[str] | None = None,
) -> Path:
    """PDF'leri verilen sırayla arka arkaya ekler. Dosya başına yer iminin adı
    `bookmark_titles`'tan, yoksa dosya adından gelir."""
    items: list[ManifestItem] = []
    passwords = list(passwords or [None] * len(inputs))
    for s, (path, pw) in enumerate(zip(inputs, passwords, strict=True)):
        with opened(Path(path), pw) as doc:
            items.extend(PageRef(s, p) for p in range(doc.page_count))
    return compose(inputs, items, output, passwords=passwords,
                   bookmark_per_file=bookmark_per_file, bookmark_titles=bookmark_titles)


def select(input: Path, spec: str, output: Path, *, password: str | None = None) -> Path:
    """Aralıktaki sayfaları yazıldığı sırayla alır. Sıralama ve çıkarma için."""
    with opened(Path(input), password) as doc:
        pages = parse_ranges(spec, doc.page_count)
    return compose([input], [PageRef(0, p) for p in pages], output, passwords=[password])


def delete(input: Path, spec: str, output: Path, *, password: str | None = None) -> Path:
    with opened(Path(input), password) as doc:
        total = doc.page_count
        drop = set(parse_ranges(spec, total))
    keep = [p for p in range(total) if p not in drop]
    if not keep:
        raise PageRangeError("Bütün sayfalar silinemez; en az bir sayfa kalmalı.")
    return compose([input], [PageRef(0, p) for p in keep], output, passwords=[password])


def rotate(
    input: Path, angle: int, output: Path, *, spec: str = "", password: str | None = None
) -> Path:
    """Aralıktaki sayfaları (boşsa hepsini) saat yönünde `angle` derece döndürür."""
    angle = _check_rotation(angle)
    with opened(Path(input), password) as doc:
        total = doc.page_count
        targets = set(parse_ranges(spec, total))
    items = [PageRef(0, p, angle if p in targets else 0) for p in range(total)]
    return compose([input], items, output, passwords=[password])


def insert(
    target: Path,
    source: Path,
    after: int,
    output: Path,
    *,
    spec: str = "",
    passwords: tuple[str | None, str | None] = (None, None),
) -> Path:
    """`source`'un (aralıktaki) sayfalarını `target`'ın `after`. sayfasından sonra ekler.

    after=0 en başa ekler; after=sayfa sayısı en sona.
    """
    with opened(Path(target), passwords[0]) as t, opened(Path(source), passwords[1]) as s:
        t_count = t.page_count
        s_pages = parse_ranges(spec, s.page_count)
    if not 0 <= after <= t_count:
        raise PageRangeError(f"Ekleme yeri 0 ile {t_count} arasında olmalı ({after} verildi).")
    items: list[ManifestItem] = [PageRef(0, p) for p in range(after)]
    items += [PageRef(1, p) for p in s_pages]
    items += [PageRef(0, p) for p in range(after, t_count)]
    return compose([target, source], items, output, passwords=list(passwords))


def insert_blank(
    input: Path,
    after: int,
    output: Path,
    *,
    count: int = 1,
    size: tuple[float, float] | None = None,
    password: str | None = None,
) -> Path:
    with opened(Path(input), password) as doc:
        total = doc.page_count
    if not 0 <= after <= total:
        raise PageRangeError(f"Ekleme yeri 0 ile {total} arasında olmalı ({after} verildi).")
    blank = BlankPage(*size) if size else BlankPage()
    items: list[ManifestItem] = [PageRef(0, p) for p in range(after)]
    items += [blank] * count
    items += [PageRef(0, p) for p in range(after, total)]
    return compose([input], items, output, passwords=[password])


# --- Bölme -------------------------------------------------------------------------------


def _split_groups(doc: pymupdf.Document, mode: str, every: int, spec: str
                  ) -> list[tuple[str, list[int]]]:
    total = doc.page_count
    if mode == "her":
        width = len(str(total))
        return [(f"{p + 1:0{width}d}", [p]) for p in range(total)]
    if mode == "n":
        if every < 1:
            raise PageRangeError("Kaç sayfada bir bölüneceği en az 1 olmalı.")
        chunks = [list(range(i, min(i + every, total))) for i in range(0, total, every)]
        return [(f"{c[0] + 1}-{c[-1] + 1}", c) for c in chunks]
    if mode == "aralik":
        if not spec.strip():
            raise PageRangeError("Bölmek için aralık gir. Örnek: 1-3, 4-10, 11-")
        groups = parse_range_groups(spec, total)
        return [(f"{g[0] + 1}-{g[-1] + 1}" if len(g) > 1 else f"{g[0] + 1}", g) for g in groups]
    if mode == "yer-imi":
        top = [(title, page - 1) for level, title, page in doc.get_toc(simple=True)
               if level == 1 and page >= 1]
        if not top:
            raise PageRangeError("Bu PDF'te üst seviye yer imi yok; başka bir bölme yöntemi seç.")
        top.sort(key=lambda t: t[1])
        out: list[tuple[str, list[int]]] = []
        if top[0][1] > 0:  # ilk yer iminden önceki sayfalar (kapak vb.)
            out.append(("Başlangıç", list(range(0, top[0][1]))))
        for i, (title, start) in enumerate(top):
            end = top[i + 1][1] if i + 1 < len(top) else total
            if end > start:  # aynı sayfayı gösteren yer imleri boş parça üretmesin
                out.append((title, list(range(start, end))))
        return out
    raise PageRangeError(f"Bilinmeyen bölme yöntemi: {mode}")


SPLIT_MODES = ("her", "n", "aralik", "yer-imi")


def split(
    input: Path,
    output_dir: Path,
    *,
    mode: str = "her",
    every: int = 1,
    spec: str = "",
    password: str | None = None,
    name_stem: str | None = None,
) -> list[Path]:
    """PDF'i parçalara ayırır. Dosya adları: '<ad>_<parça>.pdf' (<ad> = `name_stem` ya da
    girdinin adı).

    mode: 'her' (her sayfa ayrı), 'n' (her `every` sayfada bir),
          'aralik' (`spec` içindeki her parça ayrı dosya), 'yer-imi' (üst seviye yer imleri).
    """
    input = Path(input)
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    with opened(input, password) as doc:
        groups = _split_groups(doc, mode, every, spec)

    stem = name_stem or input.stem
    outputs: list[Path] = []
    used: set[str] = set()
    width = len(str(len(groups)))
    for i, (label, pages) in enumerate(groups, start=1):
        name = safe_filename(label, fallback=f"parca-{i}")
        if mode == "yer-imi":
            name = f"{i:0{width}d} {name}"
        filename = f"{stem}_{name}.pdf"
        while filename.lower() in used:  # aynı adlı yer imleri
            filename = f"{stem}_{name}_{i}.pdf"
        used.add(filename.lower())
        outputs.append(
            compose([input], [PageRef(0, p) for p in pages], output_dir / filename,
                    passwords=[password])
        )
    return outputs
