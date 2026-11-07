"""PDF → Excel, PDF → Word ve A0'a kadar kağıt boyutları."""

from __future__ import annotations

import re
from pathlib import Path

import pymupdf
import pytest
from fastapi.testclient import TestClient
from openpyxl import load_workbook

from pdfatolye import engines
from pdfatolye.api import app as app_module
from pdfatolye.convert.to_excel import parse_number, pdf_to_excel
from pdfatolye.core import images, info
from pdfatolye.core.paper import PAPERS, size_pt
from pdfatolye.errors import EncryptedPdfError, PageRangeError, PdfAtolyeError
from pdfatolye.settings import PROJECT_ROOT
from tests.fixtures import make_fixtures as fx

HEADER = ["Tarih", "Açıklama", "Tutar"]
PAGE1 = [HEADER, ["01.11.2026", "Market alışverişi", "1.250,50"],
         ["02.11.2026", "Kira", "15.000,00"]]
PAGE2 = [HEADER, ["03.11.2026", "Elektrik faturası", "842,75"],
         ["04.11.2026", "Çay ocağı", "-35,00"]]


@pytest.fixture
def client(settings, monkeypatch):
    monkeypatch.setattr(engines, "detect_all", lambda _s: [])
    with TestClient(app_module.create_app(settings, start_background=False)) as c:
        assert c.get("/api/session").status_code == 200
        yield c


def upload(client: TestClient, *paths: Path) -> list[dict]:
    r = client.post("/api/files", files=[("files", (p.name, p.read_bytes())) for p in paths])
    assert r.status_code == 200, r.text
    return r.json()


def run_job(client: TestClient, payload: dict) -> dict:
    r = client.post("/api/jobs", json=payload)
    assert r.status_code == 200, r.text
    client.app.state.jobs.wait(r.json()["id"], timeout=120)
    return client.get(f"/api/jobs/{r.json()['id']}").json()


def values(ws) -> list[list]:
    return [[c.value for c in row] for row in ws.iter_rows()]


# --- sayılar -----------------------------------------------------------------------------------


@pytest.mark.parametrize(("text", "expected"), [
    ("1.250,50", 1250.5), ("1,250.50", 1250.5), ("15.000,00", 15000.0), ("12,5", 12.5),
    ("1.234.567", 1234567), ("-35,00", -35.0), ("₺1.250,00", 1250.0), ("1.250,00 TL", 1250.0),
    ("2026", 2026), ("0,750", 0.75), ("­35,00", -35.0), ("−12,5", -12.5),
    ("–1.000", -1000), ("35,00-", -35.0),
])
def test_numbers_are_parsed(text, expected):
    assert parse_number(text)[0] == expected


@pytest.mark.parametrize("text", [
    "05321234567", "0532 123 45 67", "007", "01.11.2026", "TR12 0006 4000 0011 2345 6789 01",
    "1234567890123456", "12:30", "abc", "1..2", "%12",
])
def test_ids_dates_and_text_stay_text(text):
    assert parse_number(text)[0] is None


def test_ambiguous_thousands_follow_document_style():
    assert parse_number("1.234", "tr")[0] == 1234 and parse_number("1.234", "en")[0] == 1.234
    assert parse_number("1,234", "tr")[0] == 1.234 and parse_number("1,234", "en")[0] == 1234


# --- PDF → Excel -------------------------------------------------------------------------------


def test_lined_table_to_excel(tmp_path):
    pdf = fx.table_pdf(tmp_path / "dokum.pdf", [PAGE1])
    r = pdf_to_excel(pdf, tmp_path / "o.xlsx")
    assert (r.table_count, r.pages_with_tables) == (1, 1)
    ws = load_workbook(r.output).active
    assert values(ws) == [HEADER, ["01.11.2026", "Market alışverişi", 1250.5],
                          ["02.11.2026", "Kira", 15000.0]]
    assert ws["A1"].font.bold and not ws["A2"].font.bold


def test_table_split_over_pages_is_joined(tmp_path):
    """Sayfadan sayfaya süren tablo: ikinci sayfadaki tekrar eden başlık atlanır."""
    pdf = fx.table_pdf(tmp_path / "dokum.pdf", [PAGE1, PAGE2])
    ws = load_workbook(pdf_to_excel(pdf, tmp_path / "o.xlsx").output).active
    rows = values(ws)
    assert rows[0] == HEADER and len(rows) == 5
    assert [r[2] for r in rows[1:]] == [1250.5, 15000.0, 842.75, -35.0]


def test_separate_sheets_layout(tmp_path):
    pdf = fx.table_pdf(tmp_path / "dokum.pdf", [PAGE1, PAGE2])
    wb = load_workbook(pdf_to_excel(pdf, tmp_path / "o.xlsx", layout="ayri").output)
    assert wb.sheetnames == ["S1-T1", "S2-T2"]
    assert values(wb["S2-T2"])[0] == HEADER


def test_borderless_table_is_found(tmp_path):
    rows = [HEADER, *PAGE1[1:], *PAGE2[1:]]
    pdf = fx.table_pdf(tmp_path / "cizgisiz.pdf", [rows], lines=False)
    ws = load_workbook(pdf_to_excel(pdf, tmp_path / "o.xlsx").output).active
    got = [r for r in values(ws) if any(v is not None for v in r)]
    assert got[0] == HEADER
    assert [r[2] for r in got[1:]] == [1250.5, 15000.0, 842.75, -35.0]


def test_numbers_option_off_keeps_text(tmp_path):
    pdf = fx.table_pdf(tmp_path / "dokum.pdf", [PAGE1])
    ws = load_workbook(pdf_to_excel(pdf, tmp_path / "o.xlsx", numbers=False).output).active
    assert ws["C2"].value == "1.250,50"


def test_formula_text_is_not_a_formula(tmp_path):
    """PDF'teki "=..." metni Excel'de formül olarak çalışmamalı (açınca dış bağlantı vb.)."""
    rows = [["Ad", "Not"], ["Ali", '=HYPERLINK("http://ornek.invalid","tikla")'], ["Ayşe", "=1+1"]]
    pdf = fx.table_pdf(tmp_path / "f.pdf", [rows])
    out = pdf_to_excel(pdf, tmp_path / "o.xlsx").output
    ws = load_workbook(out).active
    assert ws["B3"].value == "=1+1" and ws["B3"].data_type == "s"
    assert ws["B2"].data_type == "s"
    import zipfile
    sheet = zipfile.ZipFile(out).read("xl/worksheets/sheet1.xml").decode()
    assert "<f>" not in sheet


def no_text_pdf(path: Path) -> Path:
    doc = pymupdf.open()
    doc.new_page().draw_rect(pymupdf.Rect(50, 50, 200, 200), fill=(0, 0, 0))
    doc.save(path)
    return path


def test_no_text_suggests_ocr(tmp_path):
    with pytest.raises(PdfAtolyeError, match="OCR"):
        pdf_to_excel(no_text_pdf(tmp_path / "tarama.pdf"), tmp_path / "o.xlsx")


def test_prose_without_tables_is_explained(tmp_path):
    pdf = fx.numbered(tmp_path / "yazi.pdf", 2, with_toc=False)
    with pytest.raises(PdfAtolyeError, match="tablo bulunamadı"):
        pdf_to_excel(pdf, tmp_path / "o.xlsx")


def test_page_selection_and_password(tmp_path):
    pdf = fx.table_pdf(tmp_path / "s.pdf", [PAGE1, PAGE2], password="gizli1")
    with pytest.raises(EncryptedPdfError):
        pdf_to_excel(pdf, tmp_path / "o.xlsx")
    ws = load_workbook(pdf_to_excel(pdf, tmp_path / "o.xlsx", spec="2", password="gizli1")
                       .output).active
    assert values(ws)[1][1] == "Elektrik faturası"


def test_excel_job(client, tmp_path):
    pdf = fx.table_pdf(tmp_path / "Kasım dökümü.pdf", [PAGE1, PAGE2], password="gizli1")
    meta = upload(client, pdf)[0]
    job = run_job(client, {"type": "pdf_to_excel", "file": meta["id"],
                           "passwords": {meta["id"]: "gizli1"}})
    assert job["status"] == "bitti", job
    out = job["files"][0]
    assert out["name"] == "Kasım dökümü.xlsx" and out["kind"] == "office"
    assert "2 sayfada 2 tablo bulundu." in job["warnings"]
    assert any("şifre taşımaz" in w for w in job["warnings"])
    assert "gizli1" not in str(job["request"])


# --- PDF → Word --------------------------------------------------------------------------------


def docx_text(path: Path) -> str:
    from docx import Document

    d = Document(str(path))
    parts = [p.text for p in d.paragraphs]
    parts += [c.text for t in d.tables for row in t.rows for c in row.cells]
    return "\n".join(parts)


def test_word_keeps_turkish_text_and_tables(tmp_path):
    from pdfatolye.convert.to_word import pdf_to_word

    pdf = fx.table_pdf(tmp_path / "t.pdf", [PAGE1], prose="Sayın Çağrı, ödeme bilgileri ektedir.")
    r = pdf_to_word(pdf, tmp_path / "o.docx")
    text = docx_text(r.output)
    assert "Sayın Çağrı, ödeme bilgileri ektedir." in text
    assert "Market alışverişi" in text and "1.250,50" in text


def test_word_page_selection_and_progress(tmp_path):
    from pdfatolye.convert.to_word import pdf_to_word

    pdf = fx.numbered(tmp_path / "n.pdf", 5, with_toc=False)
    seen: list[float] = []
    r = pdf_to_word(pdf, tmp_path / "o.docx", spec="2, 4", on_progress=lambda f, m: seen.append(f))
    text = docx_text(r.output)
    assert "Sayfa 2" in text and "Sayfa 4" in text
    assert "Sayfa 1" not in text and "Sayfa 3" not in text and "Sayfa 5" not in text
    assert seen == sorted(seen) and len(seen) >= 3


def test_word_cancel_stops_between_pages(tmp_path):
    from pdfatolye.convert.to_word import pdf_to_word

    class Stop(Exception):
        pass

    pdf = fx.numbered(tmp_path / "n.pdf", 6, with_toc=False)
    seen: list[str] = []

    def report(f, m):
        seen.append(m)
        if len(seen) == 3:
            raise Stop

    with pytest.raises(Stop):
        pdf_to_word(pdf, tmp_path / "o.docx", on_progress=report)
    assert not (tmp_path / "o.docx").exists()


def test_word_scanned_pdf_warns(tmp_path):
    from pdfatolye.convert.to_word import pdf_to_word

    r = pdf_to_word(no_text_pdf(tmp_path / "tarama.pdf"), tmp_path / "o.docx")
    assert any("OCR" in w for w in r.warnings)


def test_word_import_leaves_root_logger_alone(monkeypatch):
    """pdf2docx içe aktarılırken `logging.basicConfig` çağırır: uygulamanın günlüğü değişmemeli."""
    import logging
    import sys

    from pdfatolye.convert.to_word import _import_pdf2docx

    root = logging.getLogger()
    monkeypatch.setattr(root, "handlers", [])  # pytest'in işleyicisi varken basicConfig etkisiz
    monkeypatch.setattr(root, "level", logging.WARNING)
    for name in [m for m in sys.modules if m == "pdf2docx" or m.startswith("pdf2docx.")]:
        monkeypatch.delitem(sys.modules, name)
    _import_pdf2docx()
    assert root.handlers == [] and root.level == logging.WARNING


def test_word_job(client, tmp_path):
    pdf = fx.numbered(tmp_path / "Rapor v1.2.pdf", 2, with_toc=False)
    meta = upload(client, pdf)[0]
    job = run_job(client, {"type": "pdf_to_word", "file": meta["id"]})
    assert job["status"] == "bitti", job
    out = job["files"][0]
    assert out["name"] == "Rapor v1.2.docx" and out["kind"] == "office"
    path = client.app.state.store.path(out["id"])
    assert "Sayfa 2" in docx_text(path)


# --- A0'a kadar kağıt --------------------------------------------------------------------------


def test_paper_sizes_up_to_a0():
    assert size_pt("A0") == (2384, 3370) and size_pt("A4") == (595, 842)
    assert {"A0", "A1", "A2", "A3", "A4", "A5"} <= set(PAPERS)
    assert info.paper_name(2384, 3370) == "A0" and info.paper_name(1684, 1191) == "A2"


def test_ui_paper_list_matches_core():
    src = (PROJECT_ROOT / "web" / "src" / "tools.ts").read_text(encoding="utf-8")
    line = next(ln for ln in src.splitlines() if ln.startswith("export const PAPERS"))
    assert tuple(re.findall(r'"([^"]+)"', line)) == PAPERS


@pytest.mark.parametrize("paper", ["A0", "A1", "A2"])
def test_images_to_large_paper(tmp_path, paper):
    jpg = fx.photo_jpeg(tmp_path / "a.jpg", (300, 400))
    out = images.images_to_pdf([jpg], tmp_path / "o.pdf", page_size=paper)
    with pymupdf.open(out) as doc:
        assert (round(doc[0].rect.width), round(doc[0].rect.height)) == size_pt(paper)


def test_images_to_a0_job_accepts_paper(client, tmp_path):
    meta = upload(client, fx.photo_jpeg(tmp_path / "a.jpg", (400, 300)))[0]
    job = run_job(client, {"type": "images_to_pdf", "files": [meta["id"]], "page_size": "A0"})
    assert job["status"] == "bitti", job
    with pymupdf.open(client.app.state.store.path(job["files"][0]["id"])) as doc:
        assert (round(doc[0].rect.width), round(doc[0].rect.height)) == (3370, 2384)  # yatay


def test_a0_page_renders_at_300_dpi(tmp_path):
    """A0 pafta baskı kalitesinde (300 DPI) resme çevrilebilmeli; 600 DPI'da uygun DPI önerilir."""
    pdf = fx.numbered(tmp_path / "pafta.pdf", 1, with_toc=False, size=size_pt("A0"))
    [png] = images.pdf_to_images(pdf, tmp_path / "r", dpi=300)
    pix = pymupdf.Pixmap(str(png))
    assert abs(pix.width - 9933) <= 2 and abs(pix.height - 14043) <= 2  # 841 × 1189 mm
    with pytest.raises(PageRangeError, match=r"en fazla 3\d\d DPI"):
        images.pdf_to_images(pdf, tmp_path / "r2", dpi=600)
