"""Faz 7: telefon (LAN) modu güvenliği ve beklenmeyen hatalarda hata kimliği."""

import re

import pytest
from fastapi.testclient import TestClient

from pdfatolye import engines, lan
from pdfatolye.api import app as app_module
from pdfatolye.jobs import workers
from pdfatolye.settings import Settings
from tests.fixtures import make_fixtures as fx


@pytest.fixture
def lan_app(settings: Settings, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(lan, "lan_ips", lambda: ["192.168.1.10"])
    monkeypatch.setattr(engines, "detect_all", lambda _s: [])
    settings.lan = True
    return app_module.create_app(settings, start_background=False)


def test_lan_ips_are_private():
    for ip in lan.lan_ips():
        assert re.match(r"^(10|172|192)\.", ip)


def test_qr_svg():
    assert lan.qr_svg("http://192.168.1.10:8790/?t=x").startswith("<svg")


def test_local_computer_gets_session_and_qr(lan_app):
    with TestClient(lan_app, client=("127.0.0.1", 5000)) as local:
        assert local.get("/api/session").status_code == 200
        info = local.get("/api/lan").json()
        assert info["enabled"] and info["urls"][0].startswith("http://192.168.1.10:8790/?t=")
        assert info["qr_svg"].startswith("<svg")
        assert "192.168.1.10" in lan_app.state.settings.allowed_hosts


def test_phone_needs_pair_token(lan_app):
    pair = lan_app.state.pair_token
    with TestClient(lan_app, client=("192.168.1.50", 5000), follow_redirects=False) as phone:
        assert phone.get("/api/session").status_code == 403
        assert phone.get("/").status_code == 403
        assert phone.get("/?t=yanlis").status_code == 403
        assert phone.get("/api/files").status_code == 403
        r = phone.get(f"/?t={pair}")
        assert r.status_code == 303 and r.headers["location"] == "/"
        # Eşleşti: çerezle artık her şey açık, belirteç adreste kalmadı.
        assert phone.get("/").status_code == 200
        assert phone.get("/api/session").status_code == 200
        assert phone.get("/api/files").status_code == 200
        # QR (eşleştirme belirteci) telefona verilmez.
        assert phone.get("/api/lan").status_code == 400


def test_without_lan_mode_qr_is_off(settings, monkeypatch):
    monkeypatch.setattr(engines, "detect_all", lambda _s: [])
    with TestClient(app_module.create_app(settings, start_background=False)) as c:
        c.get("/api/session")
        assert c.get("/api/lan").json() == {"enabled": False}


def test_unexpected_job_error_has_id(settings, monkeypatch, tmp_path):
    monkeypatch.setattr(engines, "detect_all", lambda _s: [])

    def boom(*args, **kwargs):
        raise RuntimeError("iç ayrıntı")

    monkeypatch.setattr(workers, "split", boom)
    with TestClient(app_module.create_app(settings, start_background=False)) as c:
        c.get("/api/session")
        pdf = fx.numbered(tmp_path / "a.pdf", 2, with_toc=False)
        [meta] = c.post("/api/files", files=[("files", ("a.pdf", pdf.read_bytes()))]).json()
        job_id = c.post("/api/jobs", json={"type": "split", "file": meta["id"]}).json()["id"]
        job = c.app.state.jobs.wait(job_id)
        m = re.search(r"Hata kimliği: ([0-9a-f]{8})", job.error or "")
        assert m, job.error
        assert "iç ayrıntı" not in job.error  # ayrıntı kullanıcıya değil, günlüğe
        log = (settings.logs_dir / "pdfatolye.log").read_text(encoding="utf-8")
        assert m.group(1) in log and "iç ayrıntı" in log
