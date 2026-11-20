"""`toolia serve` (baslat.bat) da kendini yeniden başlatır: Ayarlar'da telefon modu ya da port
değişince sunucu aynı süreçte yeni ayarlarla yeniden açılır (masaüstü uygulamasıyla aynı yol)."""

from __future__ import annotations

import json
import socket
import threading
import time
import urllib.request
from pathlib import Path

import httpx
import psutil
import pytest

from toolia import cli, desktop, lan
from toolia.settings import load_settings


def wait_until(cond, timeout=20.0, step=0.05) -> bool:
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


def _config(tmp_path: Path, port: int, extra: str = "") -> Path:
    cfg = tmp_path / "config.toml"
    data = str(tmp_path / "veri").replace("\\", "/")
    cfg.write_text(f'data_dir = "{data}"\nport = {port}\n{extra}', encoding="utf-8")
    return cfg


def _health(url: str) -> dict | None:
    try:
        with urllib.request.urlopen(f"{url}/api/health", timeout=1) as resp:
            return json.load(resp)
    except OSError:
        return None


def _listening(port: int) -> set[str]:
    """Bu sürecin `port`'ta dinlediği adresler."""
    conns = psutil.Process().net_connections(kind="tcp")
    return {c.laddr.ip for c in conns if c.status == psutil.CONN_LISTEN and c.laddr.port == port}


def _cleanup_threads() -> int:
    return sum(t.name == "temizlik" and t.is_alive() for t in threading.enumerate())


class Serving:
    """`serve`'ün döngüsü ayrı iş parçacığında; `stop` Ctrl+C'nin yerine."""

    def __init__(self, cfg: Path, settings=None) -> None:
        self.stop = threading.Event()
        self.result: list[int] = []
        settings = settings or load_settings(cfg)
        self.thread = threading.Thread(
            target=lambda: self.result.append(
                cli._serve_until_closed(cfg, settings, stop=self.stop)), daemon=True)
        self.thread.start()

    def close(self) -> int:
        self.stop.set()
        self.thread.join(30)
        assert not self.thread.is_alive(), "sunucu kapanmadı"
        return self.result[0]


def _restart(url: str, change: dict | None = None) -> dict:
    """Arayüzün yaptığı gibi: ayarı kaydet, yeniden başlat, yeni örneği bekle."""
    before = _health(url)["instance"]
    with httpx.Client(base_url=url, timeout=10) as c:
        c.get("/api/session")
        if change:
            assert c.put("/api/settings", json=change).status_code == 200
        r = c.post("/api/restart")
        assert r.status_code == 200, r.text
    new_url = r.json()["url"]
    assert wait_until(lambda: (_health(new_url) or {}).get("instance") not in (None, before)), \
        "yeni sunucu açılmadı"
    return r.json()


def test_serve_restarts_into_phone_mode_and_back(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(lan, "lan_ips", lambda: ["192.168.1.10"])
    port = _free_port()
    cfg = _config(tmp_path, port)
    url = f"http://127.0.0.1:{port}"
    srv = Serving(cfg)
    try:
        assert wait_until(lambda: _health(url)), "sunucu açılmadı"
        assert _listening(port) == {"127.0.0.1"}
        with httpx.Client(base_url=url, timeout=10) as c:
            c.get("/api/session")
            view = c.get("/api/settings").json()
            assert view["restart_available"] is True  # artık `serve`'de de kanca var

        assert _restart(url, {"lan": True}) == {"url": url}  # port aynı
        assert wait_until(lambda: _listening(port) == {"0.0.0.0"})
        with httpx.Client(base_url=url, timeout=10) as c:
            c.get("/api/session")
            view = c.get("/api/settings").json()
            assert view["running"]["lan"] is True and view["restart_pending"] is False
            assert c.get("/api/lan").json()["enabled"] is True
        # Sunucu dinlemeye başladıktan hemen sonra yazar: çıktı gelene kadar beklenir.
        out = [""]

        def printed() -> bool:
            out[0] += capsys.readouterr().out
            return "Yeniden başlatıldı" in out[0] and "http://192.168.1.10:" in out[0]

        assert wait_until(printed, 10), out[0]  # konsola QR/adres

        _restart(url, {"lan": False})
        assert wait_until(lambda: _listening(port) == {"127.0.0.1"})
        # Eski sunucuların temizlik iş parçacıkları kapanır; yalnızca çalışanınki kalır.
        assert wait_until(lambda: _cleanup_threads() == 1, 10), _cleanup_threads()
    finally:
        code = srv.close()
    assert code == 0
    assert _health(url) is None
    assert load_settings(cfg).lan is False


def test_serve_restart_moves_to_new_port(tmp_path):
    port, new_port = _free_port(), _free_port()
    cfg = _config(tmp_path, port)
    url = f"http://127.0.0.1:{port}"
    srv = Serving(cfg)
    try:
        assert wait_until(lambda: _health(url))
        assert _restart(url, {"port": new_port}) == {"url": f"http://127.0.0.1:{new_port}"}
        assert _health(url) is None
    finally:
        assert srv.close() == 0
    assert not (tmp_path / "veri" / desktop.LOCK_NAME).exists()  # tek örnek kilidi yalnız masaüstü


def test_serve_restart_keeps_old_port_when_new_one_is_busy(tmp_path, monkeypatch):
    port = _free_port()
    cfg = _config(tmp_path, port)
    url = f"http://127.0.0.1:{port}"
    srv = Serving(cfg)
    with socket.socket() as busy:
        busy.bind(("127.0.0.1", 0))
        busy.listen()
        taken = busy.getsockname()[1]
        try:
            assert wait_until(lambda: _health(url))
            before = _health(url)["instance"]
            with httpx.Client(base_url=url, timeout=10) as c:
                c.get("/api/session")
                c.put("/api/settings", json={"port": taken})
                c.post("/api/restart")
            # Yeni port dolu: süreç çökmez, eski portta yeniden açılır (arayüz oradan bulur).
            assert wait_until(lambda: (_health(url) or {}).get("instance") not in (None, before),
                              30)
        finally:
            assert srv.close() == 0


def test_lan_flag_applies_only_to_first_start(tmp_path, monkeypatch):
    """`--lan` ile açılıp Ayarlar'dan yeniden başlatılınca ayar dosyası geçerli olur."""
    monkeypatch.setattr(lan, "lan_ips", lambda: ["192.168.1.10"])
    port = _free_port()
    cfg = _config(tmp_path, port)
    settings = load_settings(cfg)
    settings.lan, settings.host = True, "0.0.0.0"  # serve --lan
    url = f"http://127.0.0.1:{port}"
    srv = Serving(cfg, settings)
    try:
        assert wait_until(lambda: _health(url))
        assert _listening(port) == {"0.0.0.0"}
        _restart(url, {"lan": False})
        assert wait_until(lambda: _listening(port) == {"127.0.0.1"})
    finally:
        assert srv.close() == 0


_SIGINT_SCRIPT = r"""
import _thread, signal, sys, threading, time, json, urllib.request
import httpx
from toolia import cli
from pathlib import Path
from toolia.settings import load_settings
cfg, url = Path(sys.argv[1]), sys.argv[2]

def health():
    try:
        with urllib.request.urlopen(url + "/api/health", timeout=1) as r:
            return json.load(r)["instance"]
    except OSError:
        return None

def drive():
    while not health():
        time.sleep(0.1)
    first = health()
    with httpx.Client(base_url=url, timeout=10) as c:
        c.get("/api/session")
        c.post("/api/restart")
    while health() in (None, first):
        time.sleep(0.1)
    print("YENIDEN", flush=True)
    time.sleep(float(sys.argv[3]))  # 0: yeni sunucu açılırken; 1: beklerken
    _thread.interrupt_main(signal.SIGINT)  # Ctrl+C: Python'un işleyicisi ana iş parçacığında

threading.Thread(target=drive, daemon=True).start()
code = cli._serve_until_closed(cfg, load_settings(cfg))
print("KOD", code, "SUNUCU", health(), flush=True)
"""


@pytest.mark.parametrize("delay", ["0", "1"])
def test_real_ctrl_c_in_main_thread_closes_after_restart(tmp_path, delay):
    """Gerçek akış: sunucu ayrı iş parçacığında, ana iş parçacığı bekler; Ctrl+C (SIGINT) orada
    KeyboardInterrupt olur ve yeniden başlatmadan sonra da süreç düzgün kapanır."""
    import subprocess
    import sys

    port = _free_port()
    cfg = _config(tmp_path, port)
    start = time.monotonic()
    r = subprocess.run([sys.executable, "-c", _SIGINT_SCRIPT, str(cfg), f"http://127.0.0.1:{port}",
                        delay],
                       capture_output=True, text=True, encoding="utf-8", timeout=90,
                       env={**__import__("os").environ, "PYTHONIOENCODING": "utf-8"})
    out = r.stdout + r.stderr
    assert "YENIDEN" in out and "Kapatılıyor" in out, out
    assert "KOD 0 SUNUCU None" in out, out
    assert r.returncode == 0 and time.monotonic() - start < 60, out


@pytest.mark.parametrize(("event", "code"), [(KeyboardInterrupt, 0), ("crashed", 1)])
def test_ctrl_c_closes_cleanly_and_crash_is_reported(tmp_path, monkeypatch, event, code):
    port = _free_port()
    cfg = _config(tmp_path, port)
    url = f"http://127.0.0.1:{port}"
    seen = []

    def fake_wait(self, window, stop=None):
        seen.append(_health(url))
        if event is KeyboardInterrupt:
            raise KeyboardInterrupt
        return event

    monkeypatch.setattr(desktop._Server, "wait", fake_wait)
    assert cli._serve_until_closed(cfg, load_settings(cfg)) == code
    assert seen and seen[0]["app"] == "toolia"  # sunucu açıktı
    assert _health(url) is None  # ve kapandı
