"""Sayfa düzeni ve yazdırma testleri: N-up, kenar kırpma, poster bölme, yeniden boyutlandırma."""

from __future__ import annotations

import io
from pathlib import Path

import pikepdf
import pymupdf
import pytest
from fastapi.testclient import TestClient
from PIL import Image
from pydantic import ValidationError

from pdfatolye import engines, proc
from pdfatolye.api import app as app_module
from pdfatolye.core import layout
from pdfatolye.core.paper import PT_PER_MM, size_pt
from pdfatolye.errors import EncryptedPdfError, PageRangeError, PdfAtolyeError
from pdfatolye.jobs.models import LayoutRequest
from pdfatolye.settings import Settings
from tests.fixtures import make_fixtures as fx


@pytest.fixture
def client(settings: Settings, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(engines, "detect_all", lambda _s: [])
    with TestClient(app_module.create_app(settings, start_background=False)) as c:
        assert c.get("/api/session").status_code == 200
        yield c


def _upload(client: TestClient, path: Path, name: str | None = None) -> dict:
    r = client.post("/api/files", files=[("files", (name or path.name, path.read_bytes()))])
    assert r.status_code == 200, r.text
    return r.json()[0]


def _run_job(client: TestClient, payload: dict) -> dict:
    r = client.post("/api/jobs", json=payload)
    assert r.status_code == 200, r.text
    client.app.state.jobs.wait(r.json()["id"], timeout=120)
    return client.get(f"/api/jobs/{r.json()['id']}").json()


def _page_sizes(path: Path) -> list[tuple[int, int]]:
    with pymupdf.open(path) as doc:
        return [(round(p.rect.width), round(p.rect.height)) for p in doc]


# --- N-up -----------------------------------------------------------------------------------


@pytest.mark.parametrize(("per_sheet", "expected_pages"), [
    (1, 5), (2, 3), (4, 2), (6, 1), (9, 1), (16, 1),
])
def test_nup_page_counts_and_text(tmp_path, per_sheet, expected_pages):
    src = fx.numbered(tmp_path / "bes.pdf", 5, with_toc=False)
    out = layout.nup_pdf(src, tmp_path / "nup.pdf", per_sheet=per_sheet)
    with pymupdf.open(out) as doc:
        assert doc.page_count == expected_pages
        all_text = "\n".join(p.get_text() for p in doc)
    for i in range(1, 6):
        assert f"Sayfa {i}" in all_text


def test_nup_orientation_and_paper(tmp_path):
    src = fx.numbered(tmp_path / "dort.pdf", 4, with_toc=False)
    a5_w, a5_h = size_pt("A5")
    out_p = layout.nup_pdf(src, tmp_path / "p.pdf", paper="A5", orientation="dikey", per_sheet=4)
    assert _page_sizes(out_p) == [(a5_w, a5_h)]

    out_l = layout.nup_pdf(src, tmp_path / "l.pdf", paper="A5", orientation="yatay", per_sheet=4)
    assert _page_sizes(out_l) == [(a5_h, a5_w)]


def test_nup_spec_and_border(tmp_path):
    src = fx.numbered(tmp_path / "on.pdf", 6, with_toc=False)
    seen_progress: list[float] = []
    out_border = layout.nup_pdf(
        src, tmp_path / "b.pdf", spec="1, 4-5", per_sheet=4, border=True,
        on_progress=seen_progress.append,
    )
    out_plain = layout.nup_pdf(
        src, tmp_path / "p.pdf", spec="1, 4-5", per_sheet=4, border=False,
    )
    assert seen_progress == [1.0]
    with pymupdf.open(out_border) as doc_b, pymupdf.open(out_plain) as doc_p:
        assert doc_b.page_count == 1
        text = doc_b[0].get_text()
        assert "Sayfa 1" in text and "Sayfa 4" in text and "Sayfa 5" in text
        assert "Sayfa 2" not in text
        assert len(doc_b[0].get_drawings()) > len(doc_p[0].get_drawings())


@pytest.mark.parametrize("per_sheet", [1, 2, 4])
def test_nup_notes_side_places_slides_left_and_lines_right(tmp_path, per_sheet):
    src = fx.numbered(tmp_path / "slayt.pdf", 4, with_toc=False, size=(842, 595))
    out = layout.nup_pdf(
        src, tmp_path / f"not_{per_sheet}.pdf",
        per_sheet=per_sheet, notes_side=True, border=False,
    )
    with pymupdf.open(out) as doc:
        page = doc[0]
        mid_x = page.rect.width * 0.55
        # Metin blokları sol ~%55 sütunda kalmalı
        text_blocks = [b for b in page.get_text("blocks") if str(b[4]).strip()]
        assert text_blocks
        assert all(b[2] <= mid_x + 2 for b in text_blocks)
        # Sağ ~%45 alanda çizgili not satırları bulunmalı
        note_drawings = [
            d for d in page.get_drawings()
            if d["rect"].x0 >= mid_x - 2 and d["rect"].width > page.rect.width * 0.25
        ]
        line_count = sum(1 for d in note_drawings for item in d["items"] if item[0] == "l")
        assert line_count >= 4


def test_nup_handles_rotated_and_cropped_pages(tmp_path):
    src = fx.cropped(tmp_path / "kirpik.pdf")
    out = layout.nup_pdf(src, tmp_path / "nup.pdf", per_sheet=2)
    with pymupdf.open(out) as doc:
        assert doc.page_count == 1
        txt = doc[0].get_text()
        assert "Sayfa 1" in txt and "Sayfa 2" in txt


def test_nup_cancellation(tmp_path):
    src = fx.numbered(tmp_path / "a.pdf", 4, with_toc=False)
    with proc.cancel_scope(lambda: True), pytest.raises(proc.Cancelled):
        layout.nup_pdf(src, tmp_path / "o.pdf", per_sheet=2)


# --- Kenar kırpma ---------------------------------------------------------------------------


@pytest.mark.parametrize("rot", [0, 90, 180, 270])
def test_crop_auto_rotated_pages(tmp_path, rot):
    src = tmp_path / f"rot_{rot}.pdf"
    doc = pymupdf.open()
    page = doc.new_page(width=600, height=800)
    page.insert_text((200, 300), "ORTA-METIN", fontsize=18)
    page.draw_line((190, 320), (340, 320), color=(0, 0, 0))
    page.set_rotation(rot)
    doc.save(src)
    doc.close()

    out = layout.crop_margins_pdf(src, tmp_path / "out.pdf", crop_mode="auto", margin_mm=5)
    with pymupdf.open(out) as res:
        rp = res[0]
        assert rp.rect.width < 300 and rp.rect.height < 300
        assert "ORTA-METIN" in rp.get_text()


def test_crop_auto_includes_images_and_guards_empty_page(tmp_path):
    src = tmp_path / "karma.pdf"
    img_buf = io.BytesIO()
    Image.new("RGB", (80, 60), "navy").save(img_buf, "PNG")

    doc = pymupdf.open()
    p_img = doc.new_page(width=600, height=800)
    p_img.insert_image(pymupdf.Rect(150, 250, 350, 400), stream=img_buf.getvalue())
    doc.new_page(width=600, height=800)  # tamamen boş sayfa
    doc.save(src)
    doc.close()

    out = layout.crop_margins_pdf(src, tmp_path / "out.pdf", crop_mode="auto", margin_mm=5)
    with pymupdf.open(out) as res:
        assert res[0].rect.width < 260 and res[0].rect.height < 210
        assert res[1].rect == pymupdf.Rect(0, 0, 600, 800)


def test_crop_auto_respects_spec_leaving_unselected_pages(tmp_path):
    src = fx.numbered(tmp_path / "iki.pdf", 2, with_toc=False)
    out = layout.crop_margins_pdf(
        src, tmp_path / "out.pdf", spec="1", crop_mode="auto", margin_mm=5
    )
    with pymupdf.open(out) as res:
        assert res.page_count == 2
        assert res[0].rect.width < 595
        assert (round(res[1].rect.width), round(res[1].rect.height)) == (595, 842)


@pytest.mark.parametrize("rot", [0, 90, 180, 270])
def test_crop_manual_rotated_pages(tmp_path, rot):
    src = tmp_path / f"m_{rot}.pdf"
    doc = pymupdf.open()
    page = doc.new_page(width=600, height=800)
    page.insert_text((280, 380), "MERKEZ", fontsize=16)
    page.set_rotation(rot)
    doc.save(src)
    doc.close()

    with pymupdf.open(src) as orig:
        orig_w, orig_h = orig[0].rect.width, orig[0].rect.height

    out = layout.crop_margins_pdf(
        src, tmp_path / "out.pdf", crop_mode="manual",
        crop_top_mm=10, crop_right_mm=20, crop_bottom_mm=15, crop_left_mm=5,
    )
    expected_w = orig_w - (20 + 5) * PT_PER_MM
    expected_h = orig_h - (10 + 15) * PT_PER_MM
    with pymupdf.open(out) as res:
        assert abs(res[0].rect.width - expected_w) < 0.5
        assert abs(res[0].rect.height - expected_h) < 0.5
        assert "MERKEZ" in res[0].get_text()


def test_crop_manual_rejects_excessive_margins(tmp_path):
    src = fx.numbered(tmp_path / "a.pdf", 1, with_toc=False)
    with pytest.raises(PdfAtolyeError, match="sayfa boyutunu aşıyor"):
        layout.crop_margins_pdf(
            src, tmp_path / "out.pdf", crop_mode="manual",
            crop_left_mm=120, crop_right_mm=120,
        )


# --- Poster bölme ---------------------------------------------------------------------------


def test_poster_split_quadrants_and_overlap(tmp_path):
    src = tmp_path / "poster_src.pdf"
    doc = pymupdf.open()
    p = doc.new_page(width=600, height=800)
    p.insert_text((80, 100), "SOL-UST", fontsize=16)
    p.insert_text((420, 100), "SAG-UST", fontsize=16)
    p.insert_text((80, 700), "SOL-ALT", fontsize=16)
    p.insert_text((420, 700), "SAG-ALT", fontsize=16)
    p.insert_text((295, 400), "ORTA-SINIR", fontsize=12)
    doc.save(src)
    doc.close()

    out = layout.poster_split_pdf(
        src, tmp_path / "poster.pdf",
        paper="A4", poster_cols=2, poster_rows=2, overlap_mm=12, margin_mm=5,
    )
    with pymupdf.open(out) as res:
        assert res.page_count == 4
        texts = [pg.get_text() for pg in res]
        assert "SOL-UST" in texts[0] and "SAG-ALT" not in texts[0]
        assert "SAG-UST" in texts[1] and "SOL-ALT" not in texts[1]
        assert "SOL-ALT" in texts[2] and "SAG-UST" not in texts[2]
        assert "SAG-ALT" in texts[3] and "SOL-UST" not in texts[3]


def test_poster_split_handles_rotated_cropped_page(tmp_path):
    src = fx.cropped(tmp_path / "kirpik.pdf")
    out = layout.poster_split_pdf(
        src, tmp_path / "poster.pdf", spec="2", poster_cols=2, poster_rows=1, overlap_mm=5,
    )
    with pymupdf.open(out) as res:
        assert res.page_count == 2
        combined = res[0].get_text() + res[1].get_text()
        assert "Sayfa 2" in combined


# --- Yeniden boyutlandırma ------------------------------------------------------------------


def test_resize_pages_mixed_sizes(tmp_path):
    src = fx.mixed_sizes(tmp_path / "karisik.pdf")
    a5_w, a5_h = size_pt("A5")
    out_auto = layout.resize_pages_pdf(src, tmp_path / "auto.pdf", paper="A5", margin_mm=5)
    assert _page_sizes(out_auto) == [(a5_w, a5_h), (a5_h, a5_w), (a5_w, a5_h)]

    out_sel = layout.resize_pages_pdf(
        src, tmp_path / "sel.pdf", spec="2", paper="A5", orientation="dikey", margin_mm=5,
    )
    assert _page_sizes(out_sel) == [(a5_w, a5_h)]
    with pymupdf.open(out_sel) as doc:
        assert "Sayfa 2" in doc[0].get_text()


# --- Hata ve şifre koruması -----------------------------------------------------------------


def test_invalid_range_and_passwords(tmp_path):
    plain = fx.numbered(tmp_path / "duz.pdf", 2, with_toc=False)
    with pytest.raises(PageRangeError):
        layout.nup_pdf(plain, tmp_path / "x.pdf", spec="99")

    enc = fx.numbered(tmp_path / "gizli.pdf", 2, with_toc=False, password="sifre")
    with pytest.raises(EncryptedPdfError, match="şifreli"):
        layout.resize_pages_pdf(enc, tmp_path / "x.pdf")
    with pytest.raises(EncryptedPdfError, match="yanlış"):
        layout.crop_margins_pdf(enc, tmp_path / "x.pdf", password="yanlis")


def test_layout_request_validation():
    req = LayoutRequest(type="layout", file="a" * 32)
    assert req.mode == "nup" and req.paper == "A4" and req.per_sheet == 2

    with pytest.raises(ValidationError):
        LayoutRequest(type="layout", file="a" * 32, per_sheet=5)
    with pytest.raises(ValidationError):
        LayoutRequest(type="layout", file="a" * 32, poster_cols=7)
    with pytest.raises(ValidationError):
        LayoutRequest(type="layout", file="a" * 32, margin_mm=-1)


# --- İş / API tümleştirme testleri ----------------------------------------------------------


@pytest.mark.parametrize(("mode", "suffix", "extra"), [
    ("nup", "_nup.pdf", {"per_sheet": 2, "notes_side": True}),
    ("crop", "_kirpilmis.pdf", {"crop_mode": "auto", "margin_mm": 5}),
    ("poster", "_poster.pdf", {"poster_cols": 2, "poster_rows": 2}),
    ("resize", "_boyut.pdf", {"paper": "A5"}),
])
def test_layout_jobs_preserve_encryption_and_suffix(client, tmp_path, mode, suffix, extra):
    src = fx.numbered(tmp_path / "ders.pdf", 2, with_toc=False, password="parola")
    meta = _upload(client, src)
    assert meta["encrypted"]

    job = _run_job(client, {
        "type": "layout",
        "file": meta["id"],
        "mode": mode,
        "passwords": {meta["id"]: "parola"},
        **extra,
    })
    assert job["status"] == "bitti", job
    out_meta = job["files"][0]
    assert out_meta["name"].endswith(suffix)
    assert out_meta["encrypted"]

    out_path = client.app.state.store.path(out_meta["id"])
    with pytest.raises(pikepdf.PasswordError):
        pikepdf.open(out_path)
    with pikepdf.open(out_path, password="parola") as pdf:
        assert pdf.encryption.R == 6 and pdf.encryption.bits == 256
