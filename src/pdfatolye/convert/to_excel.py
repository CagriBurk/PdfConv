"""PDF → Excel: sayfalardaki tablolar (PyMuPDF `find_tables`) bir .xlsx dosyasına yazılır.

- Önce çizgili tablolar aranır; çizgisi olmayan sayfada yazıların hizasına göre aranır (banka
  dökümü, fatura gibi çizgisiz tablolar).
- "tek" düzende bütün tablolar bir çalışma sayfasında alt alta durur; sayfadan sayfaya süren bir
  tablonun (aynı başlık satırı) tekrarlanan başlığı atlanır, satırlar kesintisiz devam eder.
  "ayri" düzende her tablo kendi çalışma sayfasındadır.
- Sayılar Excel'de toplanabilsin diye sayıya çevrilir. "1.234,56" (Türkçe) ve "1,234.56"
  (İngilizce) ayırt edilir; belirsiz olanlar ("1.234") belgede çoğunlukta olan biçime göre okunur.
  Baştaki sıfırlı değerler (telefon, hesap no) ve 15 haneden uzunlar yazı kalır.
- "=" ile başlayan hücre yazı olarak yazılır: PDF'teki bir metin Excel'de formül olarak çalışmasın.
"""

from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

from pdfatolye.core.pdfio import atomic_output, opened
from pdfatolye.core.ranges import parse_ranges
from pdfatolye.errors import PageRangeError, PdfAtolyeError

Progress = Callable[[float, str], None]

LAYOUTS = ("tek", "ayri")
MAX_CELL_CHARS = 32_767  # Excel'in hücre sınırı
MAX_COL_WIDTH = 60
MAX_SHEETS = 1000  # "ayri" düzende; sonrası son sayfaya eklenir

# Sayı biçimleri: TR = binlik nokta, ondalık virgül (1.234,56); EN = tersi (1,234.56).
_NUMBER = re.compile(r"^(?P<sign>[-+]?)(?P<body>\d[\d.,]*)$")
_CURRENCY = re.compile(r"^(?:₺|TL|TRY|\$|€|£|USD|EUR)\s*|\s*(?:₺|TL|TRY|\$|€|£|USD|EUR)$")
_ILLEGAL = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f]")
# PDF'lerde eksi işareti çoğu zaman başka bir karakterle gelir: yumuşak tire (yazı tipinin "-"
# kodu), gerçek eksi, kısa çizgi, bölünmez tire.
_MINUS = str.maketrans({"­": "-", "−": "-", "‐": "-", "‑": "-",
                        "–": "-"})
_DECIMAL_SEP = {"tr": ",", "en": "."}


@dataclass
class ExcelResult:
    output: Path
    table_count: int
    pages_with_tables: int
    warnings: list[str] = field(default_factory=list)


def _clean(value: str | None) -> str:
    if value is None:
        return ""
    # Yumuşak tire Excel'de görünmez: PDF'te "-" olarak görünüyordu, öyle kalsın.
    text = _ILLEGAL.sub("", str(value)).replace("­", "-").strip()
    return text[:MAX_CELL_CHARS]


def _grouped(digits: str, sep: str) -> bool:
    """'1.234.567' gibi geçerli binlik gruplaması mı (ilk grup 1–3, sonrakiler 3 hane)?"""
    head, *rest = digits.split(sep)
    return 1 <= len(head) <= 3 and bool(rest) and all(len(g) == 3 and g.isdigit() for g in rest)


def parse_number(text: str, style: str = "tr") -> tuple[int | float | None, str | None]:
    """Hücre metnini sayıya çevirir: (değer ya da None, biçimden kesin çıkan stil ya da None).

    Kurallar: iki ayırıcı birlikteyse sondaki ondalıktır. Aynı ayırıcı birden çok kez geçiyorsa
    binliktir. Tek ayırıcının ardında tam 3 hane varsa ("1.234") belirsizdir: `style` karar
    verir. Baştaki sıfırlı tamsayılar ve 15 haneden uzunlar sayı sayılmaz.
    """
    t = _CURRENCY.sub("", text.replace(" ", " ").strip()).replace(" ", "").translate(_MINUS)
    if len(t) > 1 and t.endswith("-") and t[0].isdigit():  # muhasebe: "35,00-"
        t = "-" + t[:-1]
    m = _NUMBER.match(t)
    if not m:
        return None, None
    sign, body = m["sign"], m["body"]
    if len(re.sub(r"\D", "", body)) > 15:  # Excel 15 haneden sonrasını yuvarlar (hesap/kart no)
        return None, None
    dots, commas = body.count("."), body.count(",")
    if not dots and not commas:
        if len(body) > 1 and body.startswith("0"):  # 0532…, 00123: kimlik gibi, yazı kalsın
            return None, None
        return int(sign + body), None
    if dots and commas:
        dec = "," if body.rfind(",") > body.rfind(".") else "."
        thou = "." if dec == "," else ","
        whole, _, frac = body.rpartition(dec)
        if not frac.isdigit() or frac == "" or not (_grouped(whole, thou) or whole.isdigit()):
            return None, None
        return _float(sign, whole.replace(thou, ""), frac), "tr" if dec == "," else "en"
    sep = "." if dots else ","
    if dots + commas > 1:  # 1.234.567 → binlik
        if not _grouped(body, sep):
            return None, None
        return int(sign + body.replace(sep, "")), "tr" if sep == "." else "en"
    whole, frac = body.split(sep)
    if not whole or not frac:
        return None, None
    if len(frac) == 3 and 1 <= len(whole) <= 3 and whole != "0":
        dec = _DECIMAL_SEP[style]
        if sep == dec:
            return _float(sign, whole, frac), None
        return int(sign + whole + frac), None
    return _float(sign, whole, frac), "tr" if sep == "," else "en"


def _float(sign: str, whole: str, frac: str) -> float:
    return float(f"{sign}{whole}.{frac}")


def to_number(text: str, style: str = "tr") -> int | float | None:
    return parse_number(text, style)[0]


def _cell_text(rect, words: list) -> str:
    """Hücrenin metni: merkezi hücrede olan kelimeler, satır satır.

    `Table.extract()` kullanılmaz: harf kutularını kesin (glyph) ölçüyle alır, nokta ve virgülün
    kutusu satır çizgisinde kaldığı için ayrı satır sayılır ("1.250,50" → "125050\\n. ,") ve
    kelime arası boşluklar kaybolur (tuzak #77). Kelimeler normal kutularla gelir."""
    x0, y0, x1, y1 = rect
    inside = [w for w in words
              if x0 <= (w[0] + w[2]) / 2 <= x1 and y0 <= (w[1] + w[3]) / 2 <= y1]
    lines: list[tuple[float, list]] = []
    for w in sorted(inside, key=lambda w: (w[1] + w[3]) / 2):
        cy, half = (w[1] + w[3]) / 2, (w[3] - w[1]) / 2
        if lines and abs(cy - lines[-1][0]) <= half:
            lines[-1][1].append(w)
        else:
            lines.append((cy, [w]))
    return "\n".join(" ".join(w[4] for w in sorted(ws, key=lambda w: w[0])) for _, ws in lines)


def _rows(table, words: list) -> list[list[str]]:
    return [[_cell_text(c, words) if c else "" for c in row.cells] for row in table.rows]


def _real(found) -> list:
    """En az 2 × 2 hücre: tek hücreli çerçeve (kenarlıklı kutu) ya da hizaya göre aramada düz
    paragrafın "tek sütunlu tablo" görünümü tablo sayılmaz."""
    return [t for t in found.tables if t.col_count >= 2 and t.row_count >= 2]


def _find_tables(page, has_text: bool) -> list[list[list[str]]]:
    """Sayfanın tabloları (satır × sütun metin). Çizgili bulunamazsa hizaya göre aranır.

    `use_layout=False`: PyMuPDF 2'de varsayılan, her sayfada bir sayfa düzeni modeli (onnx)
    çalıştırır: sayfa başına ~0,7 sn yerine ~0,05 sn (100 sayfalık döküm 70 sn → 5 sn)."""
    words = page.get_text("words") if has_text else []
    tables = [_rows(t, words) for t in _real(page.find_tables(use_layout=False))]
    if not tables and has_text:
        found = page.find_tables(vertical_strategy="text", horizontal_strategy="text",
                                 use_layout=False)
        tables = [_rows(t, words) for t in _real(found)]
    result = []
    for rows in tables:
        cleaned = [[_clean(c) for c in row] for row in rows]
        cleaned = [row for row in cleaned if any(row)]
        if cleaned:
            # Tamamen boş sütunları at (hizaya göre aramada sık görülür).
            keep = [i for i in range(len(cleaned[0])) if any(r[i] for r in cleaned if i < len(r))]
            result.append([[r[i] if i < len(r) else "" for i in keep] for r in cleaned])
    return result


def pdf_to_excel(
    input: Path,
    output: Path,
    *,
    spec: str = "",
    layout: str = "tek",
    numbers: bool = True,
    password: str | None = None,
    on_progress: Progress | None = None,
) -> ExcelResult:
    from openpyxl import Workbook
    from openpyxl.styles import Alignment, Font

    if layout not in LAYOUTS:
        raise ValueError(f"Bilinmeyen düzen: {layout}")
    report = on_progress or (lambda f, m: None)
    input, output = Path(input), Path(output)

    collected: list[tuple[int, list[list[str]]]] = []  # (sayfa, tablo)
    has_text = False
    with opened(input, password) as doc:
        pages = list(dict.fromkeys(parse_ranges(spec, doc.page_count)))
        if not pages:
            raise PageRangeError("Seçilen aralıkta sayfa bulunamadı.")
        for i, p in enumerate(pages):
            report(0.05 + 0.75 * i / len(pages), f"Tablolar aranıyor: {i + 1}/{len(pages)} sayfa")
            page = doc[p]
            page_text = bool(page.get_text("text").strip())
            has_text = has_text or page_text
            collected += [(p, t) for t in _find_tables(page, page_text)]

    if not collected:
        if not has_text:
            raise PdfAtolyeError("Bu PDF'te metin yok (taranmış olabilir). Önce OCR ile metin "
                                 "tanıt, sonra Excel'e çevir.")
        raise PdfAtolyeError("Bu PDF'te tablo bulunamadı. Tablo sayfasını seçtiğinden emin ol; "
                             "düz yazı için PDF → Word'ü dene.")

    style = "tr"
    if numbers:
        votes = [parse_number(c)[1] for _, t in collected for row in t for c in row if c]
        if votes.count("en") > votes.count("tr"):
            style = "en"

    report(0.85, "Excel dosyası yazılıyor")
    wb = Workbook()
    ws = wb.active
    ws.title = "Tablolar"
    bold = Font(bold=True)
    wrap = Alignment(wrap_text=True, vertical="top")
    widths: dict[int, dict[int, float]] = {}

    def write(ws, row_no: int, row: list[str], header: bool) -> None:
        col_widths = widths.setdefault(id(ws), {})
        for col, text in enumerate(row, start=1):
            if not text:
                continue
            value = None if header or not numbers else to_number(text, style)
            cell = ws.cell(row=row_no, column=col)
            if value is not None:
                cell.value = value
            else:
                cell.value = text
                cell.data_type = "s"  # "=..." formül olmasın
                if "\n" in text:
                    cell.alignment = wrap
            if header:
                cell.font = bold
            longest = max(len(line) for line in text.split("\n"))
            col_widths[col] = min(MAX_COL_WIDTH, max(col_widths.get(col, 8), longest + 2))

    sheets = 0
    row_no = 0
    prev_header: list[str] | None = None
    for n, (p, table) in enumerate(collected, start=1):
        if layout == "ayri":
            if sheets < MAX_SHEETS:
                ws = wb.active if sheets == 0 else wb.create_sheet()
                ws.title = f"S{p + 1}-T{n}"[:31]
                sheets += 1
                row_no = 0
                ws.freeze_panes = "A2"
            elif row_no:
                row_no += 1
            for r, row in enumerate(table):
                row_no += 1
                write(ws, row_no, row, header=r == 0)
            continue
        header = table[0]
        continues = prev_header is not None and header == prev_header
        body = table[1:] if continues else table
        if not continues and row_no:
            row_no += 1  # tablolar arasında bir boş satır
        for r, row in enumerate(body):
            row_no += 1
            write(ws, row_no, row, header=not continues and r == 0)
        prev_header = header

    from openpyxl.utils import get_column_letter

    for sheet in wb.worksheets:
        for col, width in widths.get(id(sheet), {}).items():
            sheet.column_dimensions[get_column_letter(col)].width = width

    warnings = []
    if layout == "ayri" and len(collected) > MAX_SHEETS:
        warnings.append(f"{len(collected)} tablo var; ilk {MAX_SHEETS - 1} tanesi ayrı sayfada, "
                        "kalanlar son sayfada alt alta.")
    with atomic_output(output) as tmp:
        wb.save(tmp)
    pages_with = len({p for p, _ in collected})
    return ExcelResult(output, len(collected), pages_with, warnings)
