import io
import zipfile

import pymupdf
import pytest
from fastapi.testclient import TestClient

from pdfatolye import engines
from pdfatolye.api import app as app_module
from pdfatolye.settings import Settings
from tests.fixtures import make_fixtures as fx

BROWSER = engines.detect_browser(Settings()).path


@pytest.fixture
def calls(monkeypatch: pytest.MonkeyPatch) -> list[int]:
    """Gerçek motor taramasını sahtesiyle değiştirir ve kaç kez çağrıldığını sayar."""
    counter: list[int] = []
    real_browser = engines.EngineStatus(key="browser", name="Edge", available=True,
                                        needed_for="x", path=BROWSER)

    def fake_detect_all(_settings):
        counter.append(1)
        return [real_browser]

    monkeypatch.setattr(engines, "detect_all", fake_detect_all)
    return counter


@pytest.fixture
def anon(settings: Settings, calls):
    with TestClient(app_module.create_app(settings, start_background=False)) as c:
        yield c


@pytest.fixture
def client(anon: TestClient) -> TestClient:
    assert anon.get("/api/session").status_code == 200  # oturum çerezi
    return anon


def upload(client: TestClient, *paths, names=None) -> list[dict]:
    files = [("files", ((names or {}).get(p, p.name), p.read_bytes())) for p in paths]
    r = client.post("/api/files", files=files)
    assert r.status_code == 200, r.text
    return r.json()


def run_job(client: TestClient, payload: dict) -> dict:
    r = client.post("/api/jobs", json=payload)
    assert r.status_code == 200, r.text
    job = client.app.state.jobs.wait(r.json()["id"], timeout=120)
    return client.get(f"/api/jobs/{job.id}").json()


# --- temel ve güvenlik ------------------------------------------------------------------


def test_health_needs_no_session(anon):
    assert anon.get("/api/health").json()["status"] == "ok"


def test_api_requires_session_cookie(anon):
    r = anon.get("/api/files")
    assert r.status_code == 403
    assert "Oturum" in r.json()["detail"]


def test_index_page_sets_cookie(anon):
    assert anon.get("/").status_code == 200
    assert anon.get("/api/files").status_code == 200


def test_foreign_host_is_rejected(client):
    # DNS rebinding: kötü niyetli alan adı 127.0.0.1'e yönlendirilse bile reddedilmeli.
    r = client.get("/api/health", headers={"host": "kotu-site.example"})
    assert r.status_code == 400


def test_cross_origin_post_is_rejected(client, tmp_path):
    r = client.post("/api/jobs", json={}, headers={"origin": "https://kotu-site.example"})
    assert r.status_code == 403


def test_engines_are_cached_until_refresh(client, calls):
    first = client.get("/api/engines").json()
    assert first["engines"][0]["ok"] is True
    assert "pymupdf" in first["libraries"]
    client.get("/api/engines")
    assert len(calls) == 1
    client.get("/api/engines?refresh=true")
    assert len(calls) == 2


def test_unknown_api_path_is_404(client):
    assert client.get("/api/yok").status_code == 404


def test_spa_does_not_serve_files_outside_dist(client):
    r = client.get("/..%2F..%2Fpyproject.toml")
    assert "pdfatolye" not in r.text


# --- dosyalar ---------------------------------------------------------------------------


def test_upload_list_download_turkish_name(client, tmp_path):
    pdf = fx.numbered(tmp_path / "a.pdf", 2, with_toc=False)
    [meta] = upload(client, pdf, names={pdf: "Çağrı ödev.pdf"})
    assert meta["page_count"] == 2 and meta["name"] == "Çağrı ödev.pdf"
    assert [m["id"] for m in client.get("/api/files").json()] == [meta["id"]]
    r = client.get(f"/api/files/{meta['id']}/download")
    assert r.content == pdf.read_bytes()
    assert "filename*=utf-8''%C3%87a%C4%9Fr%C4%B1" in r.headers["content-disposition"]
    assert client.get(f"/api/files/{meta['id']}/raw").headers["content-type"] == "application/pdf"


def test_missing_file_is_404(client):
    assert client.get(f"/api/files/{'a' * 32}").status_code == 404


def test_password_check(client, tmp_path):
    [meta] = upload(client, fx.numbered(tmp_path / "s.pdf", 2, password="gizli"))
    assert meta["encrypted"] is True
    bad = client.post(f"/api/files/{meta['id']}/password", json={"password": "x"})
    assert bad.status_code == 400
    assert bad.json()["detail"] == "'s.pdf' için girilen şifre yanlış."  # iç ad (v1.pdf) değil
    ok = client.post(f"/api/files/{meta['id']}/password", json={"password": "gizli"})
    assert ok.json() == {"ok": True, "page_count": 2}


def test_pin_rename_delete(client, tmp_path):
    [meta] = upload(client, fx.numbered(tmp_path / "a.pdf", 1, with_toc=False))
    fid = meta["id"]
    assert client.post(f"/api/files/{fid}/pin", json={"pinned": True}).json()["pinned"]
    assert client.post(f"/api/files/{fid}/rename", json={"name": "yeni"}).json()["name"] == \
        "yeni.pdf"
    assert client.delete(f"/api/files/{fid}").json() == {"ok": True}
    assert client.get(f"/api/files/{fid}").status_code == 404


# --- işler ------------------------------------------------------------------------------


def test_compose_as_new_version_then_undo(client, tmp_path):
    [a] = upload(client, fx.numbered(tmp_path / "a.pdf", 3, with_toc=False))
    [b] = upload(client, fx.numbered(tmp_path / "b.pdf", 1, label="Ek", with_toc=False))
    job = run_job(client, {
        "type": "compose", "target": "version", "base_file": a["id"],
        "items": [{"file": a["id"], "page": 2, "rotate": 90}, {"file": b["id"], "page": 0},
                  {"blank": True}],
    })
    assert job["status"] == "bitti", job
    assert job["outputs"] == [a["id"]]
    path = client.app.state.store.path(a["id"])
    assert fx.labels(path) == ["Sayfa 3", "Ek 1", ""]
    meta = client.post(f"/api/files/{a['id']}/undo").json()
    assert meta["version"] == 1 and meta["page_count"] == 3


def test_merge_uses_display_names_for_bookmarks(client, tmp_path):
    a = fx.numbered(tmp_path / "a.pdf", 1, with_toc=False)
    b = fx.numbered(tmp_path / "b.pdf", 1, label="Ek", with_toc=False)
    files = upload(client, a, b, names={a: "Birinci Ünite.pdf", b: "İkinci.pdf"})
    job = run_job(client, {"type": "merge", "files": [f["id"] for f in files],
                           "bookmark_per_file": True})
    out = job["files"][0]
    assert out["name"] == "Birinci Ünite_birlesik.pdf"
    with pymupdf.open(client.app.state.store.path(out["id"])) as doc:
        assert doc.get_toc() == [[1, "Birinci Ünite", 1], [1, "İkinci", 2]]


def test_split_then_zip(client, tmp_path):
    [a] = upload(client, fx.numbered(tmp_path / "x.pdf", 4, with_toc=False),
                 names={})
    job = run_job(client, {"type": "split", "file": a["id"], "mode": "n", "every": 2})
    names = [f["name"] for f in job["files"]]
    assert names == ["x_1-2.pdf", "x_3-4.pdf"]
    ids = ",".join(job["outputs"])
    r = client.get(f"/api/zip?ids={ids}&name=parcalar")
    assert r.headers["content-type"] == "application/zip"
    with zipfile.ZipFile(io.BytesIO(r.content)) as zf:
        assert sorted(zf.namelist()) == names


def test_encrypted_job_uses_password(client, tmp_path):
    [s] = upload(client, fx.numbered(tmp_path / "s.pdf", 2, password="gizli"))
    failed = run_job(client, {"type": "split", "file": s["id"]})
    assert failed["status"] == "hata"
    assert failed["error"] == "'s.pdf' şifreli. Açmak için şifresini gir."
    ok = run_job(client, {"type": "split", "file": s["id"], "passwords": {s["id"]: "gizli"}})
    assert ok["status"] == "bitti" and len(ok["outputs"]) == 2
    assert "gizli" not in str(ok["request"])  # şifre kayda geçmez


def test_images_roundtrip(client, tmp_path):
    files = upload(client, fx.photo_jpeg(tmp_path / "f.jpg", (400, 200)),
                   fx.transparent_png(tmp_path / "p.png"))
    job = run_job(client, {"type": "images_to_pdf", "files": [f["id"] for f in files],
                           "margin_mm": 5})
    pdf = job["files"][0]
    assert pdf["page_count"] == 2 and pdf["name"] == "resimler.pdf"
    job = run_job(client, {"type": "pdf_to_images", "file": pdf["id"], "dpi": 50, "fmt": "jpg"})
    assert [f["name"] for f in job["files"]] == ["resimler_1.jpg", "resimler_2.jpg"]


def test_wrong_kind_is_reported(client, tmp_path):
    [img] = upload(client, fx.transparent_png(tmp_path / "p.png"))
    job = run_job(client, {"type": "split", "file": img["id"]})
    assert job["status"] == "hata" and "PDF" in job["error"]


@pytest.mark.parametrize(
    ("payload", "fragment"),
    [
        ({"type": "yok"}, "type"),
        ({"type": "merge", "files": ["a" * 32]}, "files"),
        ({"type": "compose", "items": [{"page": 0}]}, "file"),
        ({"type": "compose", "items": [{"blank": True}], "target": "version"}, "base_file"),
        ({"type": "split", "file": "../../etc"}, "file"),
    ],
)
def test_invalid_payloads(client, payload, fragment):
    r = client.post("/api/jobs", json=payload)
    assert r.status_code == 422
    assert fragment in r.json()["detail"]


# --- Markdown ---------------------------------------------------------------------------


def test_md_preview_with_attachment(client, tmp_path):
    [img] = upload(client, fx.transparent_png(tmp_path / "devre.png"))
    r = client.post("/api/md/preview", json={
        "text": "---\npdf:\n  tema: rapor\n---\n# Başlık $x$\n![[devre.png|200]]\n![[yok.png]]",
        "attachments": [img["id"]],
    })
    data = r.json()
    assert data["options"]["theme"] == "rapor"
    assert data["warnings"] == ["Resim bulunamadı: yok.png"]
    assert "/api/md/katex/katex.min.js" in data["html"]
    src = data["html"].split('<img src="')[1].split('"')[0]
    assert src.startswith("/api/md/asset/")
    assert client.get(src).content == (tmp_path / "devre.png").read_bytes()
    assert client.get("/api/md/katex/katex.min.css").status_code == 200


def test_md_preview_cannot_read_arbitrary_files(client):
    r = client.post("/api/md/preview", json={"text": "![](../../../../Windows/win.ini)"})
    assert "/api/md/asset/" not in r.json()["html"]
    assert client.get("/api/md/asset/deadbeef").status_code == 400


@pytest.mark.skipif(not BROWSER, reason="Edge/Chrome yok")
def test_md_to_pdf_job_with_edited_text(client, tmp_path):
    md = tmp_path / "not.md"
    md.write_text("# Eski", encoding="utf-8")
    [m] = upload(client, md)
    [img] = upload(client, fx.photo_jpeg(tmp_path / "f.jpg"))
    job = run_job(client, {"type": "md_to_pdf", "file": m["id"],
                           # CRLF: Windows'ta \r\r\n'e dönüşüp satır numaralarını bozmamalı
                           "text": "# Yeni ğüş\r\n\r\n![[f.jpg]]\r\n\r\n$\\frac{1}{$",
                           "attachments": [img["id"]], "options": {"paper": "A5"}})
    assert job["status"] == "bitti", job
    out = job["files"][0]
    assert out["name"] == "not.pdf"
    assert len(job["warnings"]) == 1
    assert job["warnings"][0].startswith("Satır 5: formül")
    with pymupdf.open(client.app.state.store.path(out["id"])) as doc:
        assert "Yeni ğüş" in doc[0].get_text()
        assert len(doc[0].get_images()) == 1
        assert abs(doc[0].rect.width - 420) < 2


@pytest.mark.skipif(not engines.detect_libreoffice(Settings()).path, reason="LibreOffice yok")
def test_office_job_merges_and_reports_broken(client, tmp_path):
    a = fx.docx(tmp_path / "a.docx", ["Birinci belge"])
    bad = tmp_path / "bozuk.docx"
    bad.write_bytes(b"PK\x03\x04 bozuk")
    txt = tmp_path / "not.txt"
    txt.write_text("düz metin satırı", encoding="utf-8")
    files = upload(client, a, bad, txt, names={a: "Rapor Ödevi.docx"})
    job = run_job(client, {"type": "office_to_pdf", "files": [f["id"] for f in files],
                           "merge": True})
    assert job["status"] == "bitti", job
    [out] = job["files"]
    assert out["name"] == "Rapor Ödevi_birlesik.pdf" and out["page_count"] == 2
    assert any("'bozuk.docx' dönüştürülemedi" in w for w in job["warnings"])
    with pymupdf.open(client.app.state.store.path(out["id"])) as doc:
        assert doc.get_toc() == [[1, "Rapor Ödevi", 1], [1, "not", 2]]


def test_job_events_stream(client, tmp_path):
    [a] = upload(client, fx.numbered(tmp_path / "a.pdf", 2, with_toc=False))
    r = client.post("/api/jobs", json={"type": "split", "file": a["id"]})
    job_id = r.json()["id"]
    client.app.state.jobs.wait(job_id)
    with client.stream("GET", f"/api/jobs/{job_id}/events") as s:
        body = "".join(s.iter_text())
    assert body.startswith("data: ") and '"status": "bitti"' in body
