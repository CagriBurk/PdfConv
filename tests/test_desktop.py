"""Faz C: masaüstü paketi. Kod proje klasörüne bağlı değil; tek örnek; pencere kapanınca sunucu
kapanır; öksüz alt süreç kalmaz; kurulum "internetten geldi" işaretini taşımaz; sürüm tek kaynak;
LibreOffice kurulumu yalnızca bu bilgisayardan; güncelleme denetimi."""

from __future__ import annotations

import io
import json
import os
import socket
import subprocess
import sys
import threading
import time
import tomllib
from pathlib import Path

import psutil
import pytest
from fastapi.testclient import TestClient

import pdfatolye
from pdfatolye import desktop, engines, kurulum, paths, settings, update
from pdfatolye.api import app as app_module
from pdfatolye.core import fonts
from pdfatolye.jobs import workers

ROOT = Path(__file__).resolve().parents[1]


def wait_until(cond, timeout=15.0, step=0.05) -> bool:
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        if cond():
            return True
        time.sleep(step)
    return cond()


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


# --- proje klasörüne bağlılık ------------------------------------------------------------------


def test_version_has_single_source():
    pyproject = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    version = pyproject["project"]["version"]
    package = json.loads((ROOT / "web" / "package.json").read_text(encoding="utf-8"))
    lock = json.loads((ROOT / "web" / "package-lock.json").read_text(encoding="utf-8"))
    assert pdfatolye.__version__ == version
    assert package["version"] == version
    assert lock["version"] == lock["packages"][""]["version"] == version


def test_install_root_and_engine_dirs(tmp_path, monkeypatch):
    paths.install_root.cache_clear()
    monkeypatch.setenv("PDFATOLYE_HOME", str(tmp_path))
    try:
        assert paths.install_root() == tmp_path
        assert paths.engines_dir() == tmp_path / "motorlar"
        exe = tmp_path / "motorlar" / "tesseract" / "tesseract.exe"
        exe.parent.mkdir(parents=True)
        exe.write_bytes(b"MZ")
        # Kurulumla gelen motor PATH ve Program Files'tan önce bulunur.
        assert engines._find_executable("", ["tesseract"], [],
                                        engines._bundled("tesseract/tesseract.exe")) == exe
    finally:
        paths.install_root.cache_clear()


def test_install_root_from_marker_next_to_python(tmp_path, monkeypatch):
    (tmp_path / "python").mkdir()
    (tmp_path / paths.INSTALL_MARKER).write_text('{"version": "9.9.9"}', encoding="utf-8")
    monkeypatch.delenv("PDFATOLYE_HOME", raising=False)
    monkeypatch.setattr(sys, "executable", str(tmp_path / "python" / "pythonw.exe"))
    paths.install_root.cache_clear()
    try:
        assert paths.install_root() == tmp_path
        assert paths.install_info()["version"] == "9.9.9"
    finally:
        paths.install_root.cache_clear()


def test_installed_package_ignores_project_config(monkeypatch, tmp_path):
    """Kurulu pakette (proje klasörü yok) depo kökündeki config.toml aranmaz."""
    monkeypatch.delenv("PDFATOLYE_CONFIG", raising=False)
    monkeypatch.setattr(paths, "is_dev_checkout", lambda: False)
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    candidates = settings._candidate_config_files()
    assert candidates == [tmp_path / "PdfAtolye" / "config.toml"]


def test_packaged_web_dist_wins(tmp_path, monkeypatch):
    monkeypatch.setattr(paths, "PACKAGE_DIR", tmp_path)
    assert paths.web_dist() == paths.SOURCE_ROOT / "web" / "dist"
    (tmp_path / "web").mkdir()
    (tmp_path / "web" / "index.html").write_text("<!doctype html>", encoding="utf-8")
    assert paths.web_dist() == tmp_path / "web"


def test_bundled_noto_fonts_cover_turkish():
    import pymupdf

    for key in fonts.BUNDLED:
        for bold in (False, True):
            path = fonts.font_path(key, bold)
            assert path.parent == paths.fonts_dir()
            font = pymupdf.Font(fontfile=str(path))
            assert all(font.has_glyph(ord(c)) for c in "ğüşıöçĞÜŞİÖÇ")
    assert fonts.DEFAULT_FAMILY == "noto-sans"
    assert (paths.fonts_dir() / "OFL.txt").is_file()


# --- masaüstü başlatıcı ------------------------------------------------------------------------


def test_window_command_is_isolated_app_window(tmp_path):
    cmd = desktop.window_command("msedge.exe", "http://127.0.0.1:1", tmp_path / "p")
    assert cmd[1] == "--app=http://127.0.0.1:1"
    assert f"--user-data-dir={tmp_path / 'p'}" in cmd
    assert "--disable-background-mode" in cmd  # pencere kapanınca süreç kalmasın


def test_pick_port_falls_back_when_busy():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        s.listen()
        busy = s.getsockname()[1]
        assert desktop.pick_port(busy) != busy
    free = _free_port()
    assert desktop.pick_port(free) == free


class FakeWindow:
    """Edge penceresi yerine: `close()` çağrılınca "kullanıcı pencereyi kapattı"."""

    def __init__(self):
        self.closed = threading.Event()

    def wait(self):
        self.closed.wait(30)
        return 0

    def poll(self):
        return 0 if self.closed.is_set() else None


def _config(tmp_path: Path, port: int) -> Path:
    cfg = tmp_path / "config.toml"
    data = str(tmp_path / "veri").replace("\\", "/")
    cfg.write_text(f'data_dir = "{data}"\nport = {port}\n', encoding="utf-8")
    return cfg


def test_app_runs_until_window_closes_and_is_single_instance(tmp_path, monkeypatch):
    monkeypatch.setattr(desktop, "kill_children_on_exit", lambda: False)  # test sürecini değil
    port = _free_port()
    cfg = _config(tmp_path, port)
    windows: list[tuple[str, FakeWindow]] = []

    def fake_open(s, url):
        w = FakeWindow()
        windows.append((url, w))
        return w

    monkeypatch.setattr(desktop, "open_window", fake_open)
    result: list[int] = []
    t = threading.Thread(target=lambda: result.append(desktop.run(cfg)), daemon=True)
    t.start()
    assert wait_until(lambda: windows, 30), "pencere açılmadı"
    url = windows[0][0]
    assert url == f"http://127.0.0.1:{port}" and desktop.is_our_server(url)
    lock = tmp_path / "veri" / desktop.LOCK_NAME
    assert json.loads(lock.read_text(encoding="utf-8"))["port"] == port
    # İkinci açılış: yeni sunucu değil, aynı sunucuya yeni pencere.
    assert desktop.run(cfg) == 0
    assert len(windows) == 2 and windows[1][0] == url
    windows[0][1].closed.set()  # kullanıcı pencereyi kapattı
    t.join(20)
    assert result == [0]
    assert not desktop.is_our_server(url, timeout=1)
    assert not lock.exists()


def test_restart_moves_to_new_port_and_keeps_window(tmp_path, monkeypatch):
    """Ayarlar'da port değişip "Şimdi yeniden başlat" denince: eski sunucu kapanır, yenisi yeni
    portta açılır, pencere açık kalır (yeni pencere açılmaz), ayar dosyaya yazılmıştır."""
    import httpx

    from pdfatolye.settings import load_settings

    monkeypatch.setattr(desktop, "kill_children_on_exit", lambda: False)
    port, new_port = _free_port(), _free_port()
    cfg = _config(tmp_path, port)
    windows: list[tuple[str, FakeWindow]] = []

    def fake_open(s, url):
        w = FakeWindow()
        windows.append((url, w))
        return w

    monkeypatch.setattr(desktop, "open_window", fake_open)
    result: list[int] = []
    t = threading.Thread(target=lambda: result.append(desktop.run(cfg)), daemon=True)
    t.start()
    assert wait_until(lambda: windows, 30), "pencere açılmadı"
    old_url = windows[0][0]
    with httpx.Client(base_url=old_url, timeout=10) as c:
        c.get("/api/session")
        assert c.get("/api/settings").json()["restart_available"] is True
        assert c.put("/api/settings", json={"port": new_port}).status_code == 200
        assert c.post("/api/restart").json() == {"url": f"http://127.0.0.1:{new_port}"}
    new_url = f"http://127.0.0.1:{new_port}"
    assert wait_until(lambda: desktop.is_our_server(new_url, timeout=1), 30), "yeni sunucu yok"
    assert not desktop.is_our_server(old_url, timeout=1)
    assert len(windows) == 1, "yeniden başlatma yeni pencere açmamalı"
    lock = tmp_path / "veri" / desktop.LOCK_NAME
    # Kilit, sunucu yanıt vermeye başladıktan hemen sonra yazılır: kısa bir bekleme.
    assert wait_until(lambda: lock.is_file()
                      and json.loads(lock.read_text(encoding="utf-8"))["port"] == new_port, 10)
    assert load_settings(cfg).port == new_port
    windows[0][1].closed.set()
    t.join(20)
    assert result == [0]
    assert not desktop.is_our_server(new_url, timeout=1) and not lock.exists()


def test_phone_mode_listens_on_local_network(tmp_path):
    from pdfatolye.settings import Settings

    server = desktop._Server(Settings(data_dir=tmp_path / "veri", lan=True, port=_free_port()))
    assert server.server.config.host == "0.0.0.0"
    local = desktop._Server(Settings(data_dir=tmp_path / "veri2", port=_free_port()))
    assert local.server.config.host == "127.0.0.1"


def test_stale_lock_does_not_block_start(tmp_path, monkeypatch):
    monkeypatch.setattr(desktop, "kill_children_on_exit", lambda: False)
    port = _free_port()
    cfg = _config(tmp_path, port)
    (tmp_path / "veri").mkdir()
    (tmp_path / "veri" / desktop.LOCK_NAME).write_text('{"pid": 1, "port": 9}', "utf-8")
    opened = []

    def fake_open(s, url):
        opened.append(url)
        w = FakeWindow()
        w.closed.set()
        return w

    monkeypatch.setattr(desktop, "open_window", fake_open)
    assert desktop.run(cfg) == 0
    assert opened == [f"http://127.0.0.1:{port}"]


@pytest.mark.skipif(os.name != "nt", reason="Windows iş nesnesi")
def test_children_die_when_app_is_killed(tmp_path):
    """Uygulama Görev Yöneticisi'nden zorla kapatılsa da alt süreçler (LibreOffice, OCR, Edge)
    öksüz kalmaz: iş nesnesi onları da kapatır."""
    code = (
        "import subprocess, sys, time\n"
        "from pdfatolye import desktop\n"
        "assert desktop.kill_children_on_exit()\n"
        "p = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(120)'])\n"
        "print(p.pid, flush=True)\n"
        "time.sleep(120)\n"
    )
    parent = subprocess.Popen([sys.executable, "-c", code], stdout=subprocess.PIPE, text=True)
    child_pid = int(parent.stdout.readline())
    assert psutil.pid_exists(child_pid)
    parent.kill()  # zorla kapatma: Python'un hiçbir temizlik kodu çalışmaz
    parent.wait(10)
    assert wait_until(lambda: not psutil.pid_exists(child_pid), 10), "alt süreç öksüz kaldı"


# --- kurulum -----------------------------------------------------------------------------------


def _fake_package(root: Path) -> Path:
    pkg = root / "paket"
    (pkg / "python").mkdir(parents=True)
    (pkg / "python" / "pythonw.exe").write_bytes(b"MZ")
    (pkg / "motorlar").mkdir()
    (pkg / "Kaldir.cmd").write_text("@echo off", encoding="ascii")
    (pkg / kurulum.MARKER).write_text('{"version": "0.9.0"}', encoding="utf-8")
    return pkg


@pytest.mark.skipif(os.name != "nt", reason="NTFS akışı")
def test_install_copies_without_mark_of_the_web(tmp_path):
    pkg = _fake_package(tmp_path)
    exe = pkg / "python" / "pythonw.exe"
    with open(f"{exe}:Zone.Identifier", "w", encoding="ascii") as f:  # indirilmiş dosya
        f.write("[ZoneTransfer]\nZoneId=3\n")
    assert Path(f"{exe}:Zone.Identifier").exists()
    target = tmp_path / "Programs" / "PdfAtolyesi"
    old = target / "eski.txt"
    old.parent.mkdir(parents=True)
    old.write_text("önceki sürüm", encoding="utf-8")
    assert kurulum.install(pkg, target, launch=False, shortcuts=False) == 0
    copied = target / "python" / "pythonw.exe"
    assert copied.read_bytes() == b"MZ"
    assert not Path(f"{copied}:Zone.Identifier").exists(), "MOTW kopyaya taşındı"
    assert not old.exists()  # önceki sürüm tamamen değiştirildi
    marker = json.loads((target / kurulum.MARKER).read_text(encoding="utf-8"))
    assert marker["version"] == "0.9.0" and "installed" in marker


@pytest.mark.skipif(os.name != "nt", reason="kurulum yalnızca Windows")
def test_uninstall_keeps_or_removes_data(tmp_path, monkeypatch):
    target = tmp_path / "Programs" / "PdfAtolyesi"
    target.mkdir(parents=True)
    data = tmp_path / "veri"
    data.mkdir()
    (data / "imza.png").write_bytes(b"x")
    calls = []
    monkeypatch.setattr(kurulum, "remove_shortcuts", lambda: calls.append("kisayol"))
    monkeypatch.setattr(kurulum, "unregister_uninstall", lambda: calls.append("kayit"))
    monkeypatch.setattr(kurulum, "_running_app", lambda t: False)
    # Güvenlik: gerçek veri klasörüne asla ulaşılmasın (varsayılan da geçici klasöre düşer).
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "localappdata"))
    monkeypatch.delenv("PDFATOLYE_CONFIG", raising=False)
    spawned = []
    monkeypatch.setattr(kurulum, "spawn_detached", lambda args, **kw: spawned.append(args))
    monkeypatch.setattr(kurulum.tempfile, "gettempdir", lambda: str(tmp_path))
    assert data.is_relative_to(tmp_path)
    assert kurulum.uninstall(target, assume_yes=True, remove_data=False, data_dir=data) == 0
    assert data.exists() and calls == ["kisayol", "kayit"]
    script = Path(spawned[0][-1]).read_text(encoding="mbcs")
    assert f'rmdir /s /q "{target}"' in script
    assert kurulum.uninstall(target, assume_yes=True, remove_data=True, data_dir=data) == 0
    assert not data.exists()


def test_uninstall_refuses_while_app_runs(tmp_path, monkeypatch):
    monkeypatch.setattr(kurulum, "_running_app", lambda t: True)
    monkeypatch.setattr(kurulum, "remove_shortcuts", lambda: pytest.fail("silmemeli"))
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "localappdata"))
    assert kurulum.uninstall(tmp_path / "kurulum", assume_yes=True, remove_data=False,
                             data_dir=tmp_path / "veri") == 1


# --- LibreOffice kurulumu ve güncelleme ----------------------------------------------------------


@pytest.fixture
def app(settings_fixture=None):  # noqa: PT004
    return None


def _client(tmp_path, monkeypatch, host="127.0.0.1"):
    from pdfatolye.settings import Settings

    monkeypatch.setattr(engines, "detect_all", lambda _s: [])
    s = Settings(data_dir=tmp_path / "veri", allowed_hosts=["127.0.0.1", "localhost",
                                                           "testserver"])
    return TestClient(app_module.create_app(s, start_background=False), client=(host, 5000))


def test_libreoffice_install_job(tmp_path, monkeypatch):
    calls = []

    def fake_run(args, *, timeout, **kw):
        calls.append(args)
        return subprocess.CompletedProcess(args, 0, b"Successfully installed", b"")

    monkeypatch.setattr(workers.shutil, "which", lambda name: r"C:\winget.exe")
    from pdfatolye import proc
    monkeypatch.setattr(proc, "run", fake_run)
    with _client(tmp_path, monkeypatch) as c:
        c.get("/api/session")
        r = c.post("/api/jobs", json={"type": "install_engine", "engine": "libreoffice"})
        assert r.status_code == 200, r.text
        job = c.app.state.jobs.wait(r.json()["id"], 10)
        assert job.status == "bitti", job.error
    assert calls and "TheDocumentFoundation.LibreOffice" in calls[0]
    assert "--silent" in calls[0] and "--accept-package-agreements" in calls[0]


def test_libreoffice_install_failure_is_reported(tmp_path, monkeypatch):
    from pdfatolye import proc
    monkeypatch.setattr(workers.shutil, "which", lambda name: r"C:\winget.exe")
    monkeypatch.setattr(proc, "run", lambda args, **kw: subprocess.CompletedProcess(
        args, 5, b"", b"Installer failed with exit code: 1603"))
    with _client(tmp_path, monkeypatch) as c:
        c.get("/api/session")
        job_id = c.post("/api/jobs", json={"type": "install_engine",
                                           "engine": "libreoffice"}).json()["id"]
        job = c.app.state.jobs.wait(job_id, 10)
    assert job.status == "hata" and "1603" in job.error


def test_install_job_rejected_from_other_devices(tmp_path, monkeypatch):
    with _client(tmp_path, monkeypatch, host="192.168.1.50") as c:
        r = c.post("/api/jobs", json={"type": "install_engine", "engine": "libreoffice"},
                   cookies={})
        assert r.status_code in (400, 403)


class _Resp(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


@pytest.mark.parametrize(("tag", "newer"), [("v1.0.0", True), ("v0.9.0", False),
                                            ("0.8.5", False)])
def test_update_check(monkeypatch, tag, newer):
    body = json.dumps({"tag_name": tag, "html_url": "https://example/r"}).encode()
    seen = []

    def fake_urlopen(req, timeout):
        seen.append(req.full_url)
        return _Resp(body)

    monkeypatch.setattr(update.urllib.request, "urlopen", fake_urlopen)
    r = update.check("0.9.0")
    assert r["newer"] is newer and r["latest"] == tag.lstrip("v")
    assert seen == [update.LATEST_URL]


@pytest.mark.parametrize(("current", "tag", "newer"), [("0.9.1", "v0.10.0", True),
                                                       ("0.10.0", "v0.9.1", False),
                                                       ("0.10.0", "v0.10.0", False)])
def test_update_check_compares_numbers_not_text(monkeypatch, current, tag, newer):
    """Metin olarak "0.10" < "0.9" olurdu: 0.9.1 kuranlar 0.10.0'ı göremezdi."""
    body = json.dumps({"tag_name": tag}).encode()
    monkeypatch.setattr(update.urllib.request, "urlopen", lambda req, timeout: _Resp(body))
    assert update.check(current)["newer"] is newer


def test_update_check_offline(monkeypatch):
    def offline(req, timeout):
        raise OSError("ağ yok")

    monkeypatch.setattr(update.urllib.request, "urlopen", offline)
    r = update.check("0.9.0")
    assert r["newer"] is False and "ulaşılamadı" in r["message"]


def test_installer_output_survives_cp1252_pipe():
    """Kurulum çıktısı boruya giderse (cp1252) "→", "ı" yazdırmak çöktürmemeli (denemede oldu)."""
    env = dict(os.environ, PYTHONIOENCODING="cp1252", PDFATOLYE_KURULUM_BEKLEME="0")
    r = subprocess.run([sys.executable, "-m", "pdfatolye.kurulum"], capture_output=True,
                       env=env, timeout=60)
    assert r.returncode == 2, r.stderr.decode("utf-8", "replace")
    assert "Kullanım" in r.stdout.decode("utf-8")
