"""Güvenlik adım 8: yerel sunucu (GUVENLIK_PLANI.md).

1. Origin denetimi yalnızca sunucu adına bakıyordu: aynı bilgisayardaki başka bir yerel sitenin
   (`http://127.0.0.1:3000`) sayfası değiştirici istek atabilirdi (çerez SameSite açısından aynı
   site; port sayılmaz). Artık Origin, Host başlığıyla birebir (şema + sunucu + port) aynı olmalı.
2. Paylaşılan Windows bilgisayarında başka bir kullanıcı 127.0.0.1:8790'dan oturum çerezini
   alabilirdi. Artık bağlantının istemci ucundaki sürecin sahibi denetlenir.
"""

from __future__ import annotations

import os
import socket

import psutil
import pytest
from fastapi.testclient import TestClient

from toolia import native
from toolia.api import app as app_module
from toolia.settings import Settings

URL = "/api/md/snippets"


@pytest.fixture
def local(settings: Settings):
    app = app_module.create_app(settings, start_background=False)
    with TestClient(app, base_url="http://127.0.0.1:8790", client=("127.0.0.1", 5000)) as c:
        assert c.get("/api/session").status_code == 200
        yield c


@pytest.mark.parametrize(("origin", "ok"), [
    ("http://127.0.0.1:8790", True),
    ("http://127.0.0.1:3000", False),  # aynı bilgisayardaki başka yerel site
    ("http://localhost:8790", False),  # başka köken (Host 127.0.0.1:8790)
    ("https://127.0.0.1:8790", False),
    ("http://127.0.0.1", False),
    ("null", False),
    ("http://kotu-site.example", False),
])
def test_origin_must_match_exactly(local, origin, ok):
    r = local.post(URL, json={"name": f"ad {origin[-4:]}", "body": "x"},
                   headers={"Origin": origin})
    assert (r.status_code != 403) is ok, (origin, r.status_code, r.text)


def test_no_origin_header_still_works(local):
    """Origin göndermeyen istemciler (komut satırı, eski tarayıcı) çerezle çalışmaya devam eder."""
    assert local.post(URL, json={"name": "kökensiz", "body": "x"}).status_code == 200


def test_other_windows_user_gets_no_session(settings, monkeypatch):
    calls = []

    def other_user(ip, port):
        calls.append((ip, port))
        return False

    monkeypatch.setattr(native, "loopback_peer_is_same_user", other_user)
    app = app_module.create_app(settings, start_background=False)
    with TestClient(app, client=("127.0.0.1", 5000)) as c:
        r = c.get("/api/session")
        assert r.status_code == 403 and "başka bir Windows kullanıcısı" in r.json()["detail"]
        assert c.get("/").status_code == 403
        assert "pa_oturum" not in c.cookies
        assert c.get("/api/files").status_code == 403
    assert calls and calls[0] == ("127.0.0.1", 5000)


def test_lan_device_is_not_subject_to_the_windows_user_check(settings, monkeypatch):
    monkeypatch.setattr(native, "loopback_peer_is_same_user",
                        lambda ip, port: pytest.fail("yerel ağ isteğinde çağrılmamalı"))
    app = app_module.create_app(settings, start_background=False)
    with TestClient(app, client=("192.168.1.50", 5000)) as c:
        c.get("/api/session")


@pytest.mark.skipif(os.name != "nt", reason="süreç sahibi denetimi yalnız Windows'ta")
def test_real_loopback_peer_owner(monkeypatch):
    srv = socket.socket()
    srv.bind(("127.0.0.1", 0))
    srv.listen()
    cli = socket.create_connection(srv.getsockname())
    conn, (ip, port) = srv.accept()
    try:
        assert native.loopback_peer_is_same_user(ip, port) is True  # bu süreç: aynı kullanıcı
        # Başka kullanıcının sürecinin sahibi okunamaz (erişim reddedilir) → reddedilir
        real = psutil.Process

        class Other(real):
            def username(self):
                if self.pid != os.getpid():
                    return super().username()
                raise psutil.AccessDenied(self.pid)

        monkeypatch.setattr(psutil, "Process", Other)
        assert native.loopback_peer_is_same_user(ip, port) is False
        monkeypatch.setattr(psutil, "Process", real)
        assert native.loopback_peer_is_same_user(ip, 1) is True  # tabloda yok (gerçek soket değil)
    finally:
        conn.close()
        cli.close()
        srv.close()


def test_id_version_and_zip_name_tampering(local, tmp_path):
    from tests.fixtures import make_fixtures as fx

    pdf = fx.numbered(tmp_path / "a.pdf", 2)
    meta = local.post("/api/files", files=[("files", ("a.pdf", pdf.read_bytes()))]).json()[0]
    fid = meta["id"]
    for bad in ["..", "..%2F..%2Fsettings", "%2e%2e", "A" * 32, fid.upper(), fid + "0",
                "../" + fid, "x" * 200]:
        r = local.get(f"/api/files/{bad}/download")
        assert r.status_code in (400, 404, 422), (bad, r.status_code)
    for v in ("-1", "2", "999999999999"):
        assert local.get(f"/api/files/{fid}/raw?v={v}").status_code in (400, 422), v
    r = local.get(f"/api/zip?ids={fid}&name=..%5C..%5Ckotu.bat")  # ..\..\kotu.bat
    assert r.status_code == 200
    disposition = r.headers["content-disposition"]
    # Yol bileşenleri atılır, ad her zaman .zip ile biter ("kotu.bat.zip" çalıştırılabilir değil)
    assert disposition.endswith('.zip"') and ".." not in disposition and "\\" not in disposition
