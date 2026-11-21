"""Güvenlik adım 5: telefon modu (GUVENLIK_PLANI.md, karar A).

Bağlantı HTTP'dir; aynı Wi-Fi'yi dinleyen biri cihazın çerezini görebilir. Önlemler bu çerezin
değerini sınırlar:
- cihaz oturumu eşleştiği IP'ye bağlı ve 8 saat sonra düşer; QR 10 dakika geçerli;
- bu bilgisayarın oturumu telefon modunda yalnızca loopback'ten geçerli;
- cihaz yalnızca kendi dosyalarını, imzalarını ve işlerini görür; Obsidian kasası ona kapalı.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from PIL import Image

from tests.fixtures import make_fixtures as fx
from toolia import access, engines, lan
from toolia.api import app as app_module
from toolia.api import security
from toolia.settings import Settings

PC = ("127.0.0.1", 5000)
PHONE = ("192.168.1.50", 5000)
PHONE2 = ("192.168.1.51", 5000)
SNIFFER = ("192.168.1.66", 5000)


@pytest.fixture
def lan_app(settings: Settings, monkeypatch: pytest.MonkeyPatch, tmp_path):
    monkeypatch.setattr(lan, "lan_ips", lambda: ["192.168.1.10"])
    monkeypatch.setattr(engines, "detect_all", lambda _s: [])
    settings.lan = True
    vault = tmp_path / "kasa"
    vault.mkdir()
    Image.new("RGB", (8, 8), "blue").save(vault / "gizli-kasa-resmi.png")
    settings.vault_path = vault
    return app_module.create_app(settings, start_background=False)


def _pc(app) -> TestClient:
    c = TestClient(app, client=PC)
    assert c.get("/api/session").status_code == 200
    return c


def _phone(app, addr=PHONE) -> TestClient:
    c = TestClient(app, client=addr, follow_redirects=False)
    assert c.get(f"/?t={app.state.sessions.pair_token}").status_code == 303
    return c


def _upload(c: TestClient, path) -> dict:
    r = c.post("/api/files", files=[("files", (path.name, path.read_bytes()))])
    assert r.status_code == 200, r.text
    return r.json()[0]


# --- oturum ------------------------------------------------------------------------------------

def test_stolen_device_cookie_fails_from_another_address(lan_app):
    phone = _phone(lan_app)
    cookie = phone.cookies["pa_oturum"]
    assert phone.get("/api/files").status_code == 200
    with TestClient(lan_app, client=SNIFFER, follow_redirects=False) as thief:
        thief.cookies.set("pa_oturum", cookie)
        assert thief.get("/api/files").status_code == 403
        assert thief.get("/").status_code == 403


def test_computer_session_is_loopback_only_in_lan_mode(lan_app):
    local_token = lan_app.state.sessions.local
    with TestClient(lan_app, client=PHONE, follow_redirects=False) as phone:
        phone.cookies.set("pa_oturum", local_token)
        assert phone.get("/api/files").status_code == 403
        assert phone.get("/api/settings").status_code == 403


def test_device_session_and_pair_token_expire():
    now = [1000.0]
    s = security.Sessions(lan=True, clock=lambda: now[0])
    first = s.pair_token
    now[0] += security.PAIR_TTL_S + 1
    assert s.pair(first, "192.168.1.50") is None  # süresi doldu
    token = s.pair(s.pair_token, "192.168.1.50")
    assert s.identify(token, "192.168.1.50")[0]
    now[0] += security.DEVICE_TTL_S - 1
    assert s.identify(token, "192.168.1.50")[0]
    now[0] += 2
    assert s.identify(token, "192.168.1.50") == (False, None)
    assert s.devices() == []


def test_pair_token_is_refreshed_for_the_qr_screen(lan_app):
    pc = _pc(lan_app)
    sessions = lan_app.state.sessions
    old = sessions.pair_token
    sessions._pair_created -= security.PAIR_TTL_S + 1
    url = pc.get("/api/lan").json()["urls"][0]
    assert old not in url and sessions.pair_token in url


# --- dosya ve iş yalıtımı ------------------------------------------------------------------------

def test_device_sees_only_its_own_files(lan_app, tmp_path):
    pc = _pc(lan_app)
    phone = _phone(lan_app)
    secret = _upload(pc, fx.numbered(tmp_path / "pc-gizli.pdf", 2))
    mine = _upload(phone, fx.numbered(tmp_path / "telefon.pdf", 2))

    assert [f["id"] for f in phone.get("/api/files").json()] == [mine["id"]]
    assert {f["id"] for f in pc.get("/api/files").json()} == {secret["id"], mine["id"]}
    assert "owner" not in mine  # sahiplik istemciye gösterilmez

    sid = secret["id"]
    for method, url, kw in [
        ("get", f"/api/files/{sid}", {}),
        ("get", f"/api/files/{sid}/raw", {}),
        ("get", f"/api/files/{sid}/download", {}),
        ("get", f"/api/files/{sid}/info", {}),
        ("get", f"/api/files/{sid}/thumb/0", {}),
        ("get", f"/api/zip?ids={sid}", {}),
        ("post", f"/api/files/{sid}/rename", {"json": {"name": "x"}}),
        ("post", f"/api/files/{sid}/pin", {"json": {"pinned": True}}),
        ("post", f"/api/files/{sid}/undo", {}),
        ("delete", f"/api/files/{sid}", {}),
    ]:
        r = getattr(phone, method)(url, **kw)
        assert r.status_code == 404, (method, url, r.status_code)
    assert pc.get(f"/api/files/{sid}").status_code == 200  # hâlâ yerinde


def test_device_cannot_use_others_files_in_jobs(lan_app, tmp_path):
    pc = _pc(lan_app)
    phone = _phone(lan_app)
    secret = _upload(pc, fx.numbered(tmp_path / "pc.pdf", 2))
    mine = _upload(phone, fx.numbered(tmp_path / "tel.pdf", 2))
    r = phone.post("/api/jobs", json={"type": "merge", "files": [mine["id"], secret["id"]]})
    assert r.status_code == 404
    pc_job = pc.post("/api/jobs", json={"type": "merge", "files": [secret["id"], secret["id"]]})
    assert pc_job.status_code == 200

    r = phone.post("/api/jobs", json={"type": "merge", "files": [mine["id"], mine["id"]]})
    assert r.status_code == 200, r.text
    job = lan_app.state.jobs.wait(r.json()["id"])
    assert job.status == "bitti", job.error
    out = job.outputs[0]
    assert out in {f["id"] for f in phone.get("/api/files").json()}  # çıktı cihazın
    assert "owner" not in phone.get(f"/api/jobs/{job.id}").json()

    phone_jobs = {j["id"] for j in phone.get("/api/jobs").json()}
    assert phone_jobs == {job.id}
    assert phone.get(f"/api/jobs/{pc_job.json()['id']}").status_code == 400  # "İş bulunamadı"
    assert {j["id"] for j in pc.get("/api/jobs").json()} >= {job.id, pc_job.json()["id"]}

    other = _phone(lan_app, PHONE2)
    assert other.get("/api/files").json() == []
    assert other.get(f"/api/files/{out}").status_code == 404


def test_device_does_not_see_computer_signatures(lan_app, tmp_path):
    pc = _pc(lan_app)
    phone = _phone(lan_app)
    sig = fx.signature_jpeg(tmp_path / "imza.jpg")
    r = pc.post("/api/signatures", files=[("file", ("imza.jpg", sig.read_bytes()))])
    assert r.status_code == 200, r.text
    assert len(pc.get("/api/signatures").json()) == 1
    assert phone.get("/api/signatures").json() == []


def test_device_markdown_preview_cannot_read_the_vault(lan_app):
    pc = _pc(lan_app)
    phone = _phone(lan_app)
    body = {"text": "![[gizli-kasa-resmi.png]]\n"}
    pc_html = pc.post("/api/md/preview", json=body).json()["html"]
    assert "/api/md/asset/" in pc_html  # bu bilgisayar kasayı kullanır
    phone_html = phone.post("/api/md/preview", json=body).json()["html"]
    assert "/api/md/asset/" not in phone_html
    assert "bulunamadı" in phone_html


def test_no_request_context_means_full_access():
    assert access.current() is None and access.can_see("herhangi")
    with access.acting_as("cihaz"):
        assert access.is_device() and not access.can_see(None) and access.can_see("cihaz")
    assert access.current() is None
