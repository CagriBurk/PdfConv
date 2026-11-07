"""Faz D: düzenlenebilir ayarlar, yeniden başlatma, bu bilgisayara özgü işler, arayüz
hata günlüğü."""

from __future__ import annotations

import re
import threading
import typing
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from pdfatolye import native
from pdfatolye.api import app as app_module
from pdfatolye.jobs import models
from pdfatolye.settings import Settings, load_settings, save_settings, settings_file
from tests.fixtures import make_fixtures as fx

REPO = Path(__file__).resolve().parents[1]


def _settings(tmp_path: Path) -> Settings:
    return Settings(data_dir=tmp_path / "veri", allowed_hosts=["127.0.0.1", "localhost",
                                                               "testserver"])


def _client(settings: Settings, host: str = "127.0.0.1") -> TestClient:
    c = TestClient(app_module.create_app(settings, start_background=False), client=(host, 5000))
    c.get("/api/session")
    return c


# --- ayar dosyası ------------------------------------------------------------------------------

def test_save_writes_data_dir_config_and_reloads(tmp_path):
    s = _settings(tmp_path)
    vault = tmp_path / "Kasam Ödev's" / "ders notları"  # yolda \ ve ' (TOML'da kaçış ister)
    vault.mkdir(parents=True)
    path = save_settings(s, {"retention_hours": 72, "vault_path": vault, "default_theme": "rapor",
                             "default_paper": "Letter", "welcome_done": True})
    assert path == tmp_path / "veri" / "config.toml"  # kurulu pakette proje kökü yok
    assert s.retention_hours == 72 and s.vault_path == vault and s.default_theme == "rapor"
    again = load_settings(path)
    assert again.vault_path == vault  # ters eğik çizgi, tırnak ve Türkçe karakter bozulmaz
    assert (again.retention_hours, again.default_paper, again.welcome_done) == (72, "Letter", True)


def test_save_keeps_other_settings_and_reads_bom(tmp_path):
    cfg = tmp_path / "config.toml"
    cfg.write_bytes('\ufeffmax_upload_mb = 50\nport = 9100\n[engines]\ntesseract = "C:\\\\t.exe"\n'
                    .encode())
    s = load_settings(cfg)
    save_settings(s, {"retention_hours": 5})
    again = load_settings(cfg)
    assert again.max_upload_mb == 50 and again.port == 9100
    assert again.engines.tesseract == "C:\\t.exe" and again.retention_hours == 5
    assert settings_file(s) == cfg  # okunan dosyaya yazılır, başka yere değil


def test_empty_value_returns_to_default(tmp_path):
    s = _settings(tmp_path)
    vault = tmp_path / "k"
    vault.mkdir()
    save_settings(s, {"vault_path": vault, "default_theme": "sade"})
    save_settings(s, {"vault_path": "", "default_theme": None})
    assert s.vault_path is None and s.default_theme == "ders"
    text = settings_file(s).read_text(encoding="utf-8")
    assert "vault_path" not in text and "default_theme" not in text


def test_restart_settings_wait_for_restart_and_unknown_rejected(tmp_path):
    s = _settings(tmp_path)
    save_settings(s, {"port": 9300, "lan": True})
    assert (s.port, s.lan) == (8790, False)  # çalışan sunucu değişmez
    saved = load_settings(settings_file(s))
    assert (saved.port, saved.lan) == (9300, True)
    with pytest.raises(ValueError, match="data_dir"):
        save_settings(s, {"data_dir": "C:/"})


# --- API ---------------------------------------------------------------------------------------

def test_settings_api_round_trip(tmp_path):
    s = _settings(tmp_path)
    vault = tmp_path / "Obsidian Kasası"
    vault.mkdir()
    with _client(s) as c:
        view = c.get("/api/settings").json()
        assert view["values"]["retention_hours"] == 24 and view["local"] is True
        assert view["values"]["welcome_done"] is False and view["restart_available"] is False
        r = c.put("/api/settings", json={"retention_hours": 48, "vault_path": f'"{vault}"',
                                         "default_theme": "rapor"})
        assert r.status_code == 200, r.text
        assert r.json()["values"]["vault_path"] == str(vault.resolve())  # tırnaklar atılır
        assert s.retention_hours == 48 and s.vault_path == vault.resolve()
        assert load_settings(settings_file(s)).default_theme == "rapor"


@pytest.mark.parametrize(("body", "message"), [
    ({"vault_path": "göreli/klasör"}, "tam bir klasör"),
    ({"vault_path": "C:/kesinlikle/olmayan/klasör"}, "bulunamadı"),
    ({"vault_path": "C:\\"}, "sürücünün tamamı"),
    ({"default_theme": "koyu"}, "default_theme"),
    ({"retention_hours": 0}, "retention_hours"),
    ({"port": 80}, "port"),
    ({"data_dir": "C:/"}, "data_dir"),
])
def test_settings_api_rejects_bad_values(tmp_path, body, message):
    s = _settings(tmp_path)
    with _client(s) as c:
        r = c.put("/api/settings", json=body)
        assert r.status_code == 422 and message in r.json()["detail"], r.text
    assert not settings_file(s).exists()


def test_settings_change_only_from_this_computer(tmp_path, monkeypatch):
    monkeypatch.setattr(native, "pick_folder", lambda *a: pytest.fail("açılmamalı"))
    monkeypatch.setattr(native, "reveal", lambda *a: pytest.fail("açılmamalı"))
    s = _settings(tmp_path)
    meta_holder = {}
    with _client(s, host="192.168.1.50") as phone:
        meta_holder["id"] = phone.app.state.store.add_file(
            fx.numbered(tmp_path / "a.pdf", 1, with_toc=False), "a.pdf", source="upload").id
        assert phone.get("/api/settings").json()["local"] is False
        for method, url, body in [("put", "/api/settings", {"retention_hours": 1}),
                                  ("post", "/api/restart", None),
                                  ("post", "/api/pick-folder", {}),
                                  ("post", f"/api/files/{meta_holder['id']}/reveal", None)]:
            r = getattr(phone, method)(url, json=body) if body is not None else \
                getattr(phone, method)(url)
            assert r.status_code == 400 and "bilgisayardan" in r.json()["detail"], (url, r.text)
    assert s.retention_hours == 24 and not settings_file(s).exists()


def test_restart_pending_and_hook(tmp_path):
    s = _settings(tmp_path)
    with _client(s) as c:
        r = c.put("/api/settings", json={"port": 9400})
        assert r.json()["restart_pending"] is True and r.json()["running"]["port"] == 8790
        r = c.post("/api/restart")
        assert r.status_code == 400 and "baslat.bat" in r.json()["detail"]  # `serve`'de kanca yok
        called = threading.Event()
        c.app.state.restart = called.set
        assert c.get("/api/settings").json()["restart_available"] is True
        assert c.post("/api/restart").json() == {"url": "http://127.0.0.1:9400"}
        assert called.is_set()
        # Eski değere dönülürse yeniden başlatma gerekmez.
        assert c.put("/api/settings", json={"port": 8790}).json()["restart_pending"] is False


def test_markdown_defaults_from_settings(tmp_path):
    s = _settings(tmp_path)
    with _client(s) as c:
        c.put("/api/settings", json={"default_theme": "sade", "default_paper": "A5"})
        opts = c.post("/api/md/preview", json={"text": "# Not\n"}).json()["options"]
        assert (opts["theme"], opts["paper"]) == ("sade", "A5")
        front = "---\npdf:\n  tema: rapor\n---\n# Not\n"  # notun ön bilgisi önce gelir
        assert c.post("/api/md/preview", json={"text": front}).json()["options"]["theme"] == "rapor"
        chosen = c.post("/api/md/preview", json={"text": front, "options": {"theme": "ders"}})
        assert chosen.json()["options"]["theme"] == "ders"  # ekrandaki seçim en önce


def test_cleanup_reads_retention_each_round(tmp_path, monkeypatch):
    s = _settings(tmp_path)
    seen: list[float] = []

    class Store:
        def cleanup(self, hours):
            seen.append(hours)
            return 0

    class Jobs:
        def cleanup(self, hours):
            return 0

    stop = threading.Event()
    stop.set()
    s.retention_hours = 3
    app_module._cleanup_loop(Store(), Jobs(), s, stop)
    s.retention_hours = 100  # Ayarlar'dan değişti
    app_module._cleanup_loop(Store(), Jobs(), s, stop)
    assert seen == [3, 100]


def test_client_error_goes_to_log_with_id(tmp_path):
    s = _settings(tmp_path)
    with _client(s) as c:
        r = c.post("/api/client-error", json={"message": "TypeError: x is undefined",
                                              "stack": "at Jobs (index.js:1)", "where": "isler/"})
        eid = r.json()["id"]
    log = (s.logs_dir / "pdfatolye.log").read_text(encoding="utf-8")
    assert re.fullmatch(r"[0-9a-f]{8}", eid)
    assert f"[{eid}] arayüz hatası (isler/): TypeError: x is undefined" in log
    assert "at Jobs (index.js:1)" in log


def test_health_has_instance_and_is_probeable_cross_port(tmp_path):
    s = _settings(tmp_path)
    with _client(s) as c:
        r = c.get("/api/health")
        other = TestClient(app_module.create_app(_settings(tmp_path / "2"),
                                                 start_background=False)).get("/api/health")
    assert r.json()["app"] == "pdfatolye" and r.json()["instance"] != other.json()["instance"]
    assert r.headers["cross-origin-resource-policy"] == "cross-origin"
    assert r.headers["cache-control"] == "no-store"


def test_reveal_exports_copy_with_real_name(tmp_path, monkeypatch):
    shown: list[Path] = []
    monkeypatch.setattr(native, "reveal", shown.append)
    s = _settings(tmp_path)
    with _client(s) as c:
        store = c.app.state.store
        a = store.add_file(fx.numbered(tmp_path / "a.pdf", 2, with_toc=False), "Ödev — son.pdf",
                           source="upload")
        b = store.add_file(fx.numbered(tmp_path / "b.pdf", 1, with_toc=False), "b.pdf",
                           source="upload")
        assert c.post(f"/api/files/{b.id}/reveal").status_code == 200
        r = c.post(f"/api/files/{a.id}/reveal")
        assert r.status_code == 200, r.text
        target = Path(r.json()["path"])
        assert target.name == "Ödev — son.pdf"
        assert target.read_bytes() == store.path(a.id).read_bytes()
        assert target.is_relative_to(tmp_path)
        assert shown == [s.data_dir / native.REVEAL_DIR / b.id / "b.pdf", target]
        # Kullanıcı kopyayı değiştirse de depodaki sürüm değişmez.
        target.write_bytes(b"degisti")
        assert store.path(a.id).read_bytes() != b"degisti"
        store.delete(b.id)
        c.post(f"/api/files/{a.id}/reveal")
        assert not (s.data_dir / native.REVEAL_DIR / b.id).exists()  # silinen dosyanın kopyası


def test_pick_folder_returns_choice(tmp_path, monkeypatch):
    asked = []
    monkeypatch.setattr(native, "pick_folder",
                        lambda initial, desc: asked.append(initial) or "C:\\Kasa")
    with _client(_settings(tmp_path)) as c:
        r = c.post("/api/pick-folder", json={"initial": "C:\\Eski"})
        assert r.json() == {"path": "C:\\Kasa"}
    assert asked == ["C:\\Eski"]


def test_every_job_type_has_a_turkish_label():
    """İşler ekranında ham tür adı (`office_to_pdf`) görünmesin: her iş türünün adı labels.ts'te."""
    union = typing.get_args(typing.get_args(models.JobRequest)[0])
    types = {typing.get_args(m.model_fields["type"].annotation)[0] for m in union}
    labels = (REPO / "web" / "src" / "labels.ts").read_text(encoding="utf-8")
    block = labels.split("JOB_TYPE_LABEL")[1].split("};")[0]
    keys = set(re.findall(r"^\s*(\w+):", block, re.M))
    assert len(types) >= 15 and types <= keys, types - keys
