"""Masaüstü uygulaması: sunucu + uygulama penceresi (`pythonw -m pdfatolye uygulama`).

- **Pencere**: kurulu Edge `--app` kipinde, ayrı bir profil klasörüyle açılır (adres çubuğu yok,
  kullanıcının kendi Edge oturumuna karışmaz). Başlattığımız Edge süreci, uygulamanın son penceresi
  kapanınca çıkar; o zaman sunucu da kapanır.
- **Tek örnek**: çalışan bir uygulama varsa (`calisiyor.json` + `/api/health`), yeni sunucu
  açılmaz; aynı profille yeni bir pencere açılır (Edge onu çalışan örneğe devreder).
- **Öksüz süreç yok**: süreç bir Windows iş nesnesine (Job Object, "kapanınca öldür") alınır;
  uygulama Görev Yöneticisi'nden zorla kapatılsa bile LibreOffice / OCR / Edge alt süreçleri
  onunla birlikte kapanır.
- Konsol yok (`pythonw`): çıktılar günlük dosyasına; açılış hatası ileti kutusuyla gösterilir.
- **Telefon modu** Ayarlar'dan açılır (`lan = true`): sunucu yerel ağdan da dinler, pencere
  127.0.0.1'e bağlı kalır. Port ya da telefon modu değişince sunucu pencere kapanmadan yeniden
  başlar.
"""

from __future__ import annotations

import contextlib
import json
import logging
import os
import socket
import subprocess
import sys
import threading
import time
import urllib.request
from pathlib import Path

from pdfatolye.settings import Settings, load_settings

log = logging.getLogger("pdfatolye.desktop")
LOCK_NAME = "calisiyor.json"
WINDOW_PROFILE = "pencere-profili"


# --- yardımcılar ------------------------------------------------------------------------------

def message_box(text: str, title: str = "PDF Atölyesi", error: bool = True) -> None:
    """Konsolsuz çalışırken kullanıcıya görünür ileti."""
    if os.name != "nt":
        print(text, file=sys.stderr)
        return
    import ctypes

    ctypes.windll.user32.MessageBoxW(None, text, title, 0x10 if error else 0x40)


def is_our_server(url: str, timeout: float = 2) -> bool:
    try:
        with urllib.request.urlopen(f"{url}/api/health", timeout=timeout) as resp:
            return json.load(resp).get("app") == "pdfatolye"
    except (OSError, ValueError):
        return False


def port_free(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        try:
            s.bind(("127.0.0.1", port))
        except OSError:
            return False
    return True


def pick_port(preferred: int) -> int:
    """Tercih edilen port boşsa o; değilse işletim sisteminin verdiği boş bir port."""
    if port_free(preferred):
        return preferred
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def read_lock(settings: Settings) -> dict | None:
    try:
        return json.loads((settings.data_dir / LOCK_NAME).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def running_url(settings: Settings) -> str | None:
    """Çalışan bir uygulama örneğinin adresi (yoksa None)."""
    info = read_lock(settings)
    if not info or not isinstance(info.get("port"), int):
        return None
    url = f"http://127.0.0.1:{info['port']}"
    return url if is_our_server(url) else None


# --- iş nesnesi (Job Object) ------------------------------------------------------------------

def kill_children_on_exit() -> bool:
    """Bu süreci "kapanınca öldür" iş nesnesine alır: süreç ölünce (zorla kapatılsa da) bütün
    alt süreçleri ölür. İç içe iş nesnesi desteklenmiyorsa sessizce vazgeçer."""
    if os.name != "nt":
        return False
    import ctypes
    from ctypes import wintypes

    k32 = ctypes.WinDLL("kernel32", use_last_error=True)

    class BasicLimits(ctypes.Structure):
        _fields_ = [("PerProcessUserTimeLimit", ctypes.c_int64),
                    ("PerJobUserTimeLimit", ctypes.c_int64),
                    ("LimitFlags", wintypes.DWORD),
                    ("MinimumWorkingSetSize", ctypes.c_size_t),
                    ("MaximumWorkingSetSize", ctypes.c_size_t),
                    ("ActiveProcessLimit", wintypes.DWORD),
                    ("Affinity", ctypes.c_size_t),
                    ("PriorityClass", wintypes.DWORD),
                    ("SchedulingClass", wintypes.DWORD)]

    class IoCounters(ctypes.Structure):
        _fields_ = [(n, ctypes.c_uint64) for n in (
            "ReadOperationCount", "WriteOperationCount", "OtherOperationCount",
            "ReadTransferCount", "WriteTransferCount", "OtherTransferCount")]

    class ExtendedLimits(ctypes.Structure):
        _fields_ = [("BasicLimitInformation", BasicLimits),
                    ("IoInfo", IoCounters),
                    ("ProcessMemoryLimit", ctypes.c_size_t),
                    ("JobMemoryLimit", ctypes.c_size_t),
                    ("PeakProcessMemoryUsed", ctypes.c_size_t),
                    ("PeakJobMemoryUsed", ctypes.c_size_t)]

    # 64-bit tutamaklar int'e sığmaz: imzalar açıkça verilmeli.
    k32.CreateJobObjectW.restype = wintypes.HANDLE
    k32.CreateJobObjectW.argtypes = [ctypes.c_void_p, wintypes.LPCWSTR]
    k32.SetInformationJobObject.argtypes = [wintypes.HANDLE, ctypes.c_int, ctypes.c_void_p,
                                            wintypes.DWORD]
    k32.GetCurrentProcess.restype = wintypes.HANDLE
    k32.AssignProcessToJobObject.argtypes = [wintypes.HANDLE, wintypes.HANDLE]
    job = k32.CreateJobObjectW(None, None)
    if not job:
        return False
    info = ExtendedLimits()
    # KILL_ON_JOB_CLOSE | BREAKAWAY_OK (winget gibi uzun kurulumlar bilerek dışarıda başlatılır)
    info.BasicLimitInformation.LimitFlags = 0x2000 | 0x0800
    if not k32.SetInformationJobObject(job, 9, ctypes.byref(info), ctypes.sizeof(info)):
        return False
    k32.GetCurrentProcess.restype = wintypes.HANDLE
    if not k32.AssignProcessToJobObject(job, k32.GetCurrentProcess()):
        log.info("İş nesnesine alınamadı (hata %s); alt süreçler yine kapanışta durdurulur",
                 ctypes.get_last_error())
        return False
    # Tutamak bilerek kapatılmaz: süreç ölünce işletim sistemi kapatır, iş nesnesi tetiklenir.
    globals()["_JOB_HANDLE"] = job
    return True


# --- pencere ----------------------------------------------------------------------------------

def window_command(browser: str, url: str, profile: Path) -> list[str]:
    return [browser, f"--app={url}", f"--user-data-dir={profile}", "--no-first-run",
            "--no-default-browser-check", "--disable-background-mode",
            "--disable-features=msEdgeStartupBoost", "--window-size=1320,900"]


def open_window(settings: Settings, url: str) -> subprocess.Popen | None:
    """Uygulama penceresini açar. Edge/Chrome yoksa varsayılan tarayıcıda açar ve None döner."""
    from pdfatolye import engines

    browser = engines.detect_browser(settings).path
    if not browser:
        # Varsayılan tarayıcı iş nesnesinin dışında açılsın (uygulama kapanınca o kapanmasın).
        from pdfatolye.kurulum import spawn_detached

        spawn_detached(["cmd", "/c", "start", "", url])
        return None
    profile = settings.data_dir / WINDOW_PROFILE
    profile.mkdir(parents=True, exist_ok=True)
    return subprocess.Popen(window_command(browser, url, profile))


# --- ana akış ---------------------------------------------------------------------------------

def run(config: Path | None = None, *, wait_window: bool = True) -> int:
    """Uygulamayı açar; pencere kapanınca döner. Çıkış kodu.

    Ayarlar'da port ya da telefon modu değişince arayüz yeniden başlatma ister
    (`/api/restart`): sunucu kapanır, ayarlar yeniden okunur, yenisi açılır; pencere açık kalır
    ve arayüz yeni adrese geçer."""
    settings = load_settings(config)
    settings.ensure_dirs()
    _quiet_console(settings)
    url = running_url(settings)
    if url:
        log.info("Uygulama zaten çalışıyor (%s); yeni pencere açılıyor", url)
        open_window(settings, url)
        return 0

    kill_children_on_exit()
    window: subprocess.Popen | None = None
    previous_port: int | None = None
    while True:
        if previous_port is not None:  # yeniden başlatma: ayarları dosyadan yeniden oku
            settings = load_settings(config)
            settings.ensure_dirs()
        server = _start_server(settings, previous_port)
        if server is None:
            message_box("PDF Atölyesi başlatılamadı. Ayrıntı günlük dosyasında:\n"
                        f"{settings.logs_dir / 'pdfatolye.log'}")
            return 1
        try:
            if window is None:
                window = open_window(settings, server.url)
            reason = server.wait(window if wait_window else None)
        finally:
            server.stop()
        if reason != "restart":
            log.info("Masaüstü uygulaması kapandı")
            return 0
        previous_port = settings.port
        log.info("Yeni ayarlarla yeniden başlatılıyor")


class _Server:
    """Arka planda çalışan uvicorn sunucusu + yeniden başlatma isteği."""

    def __init__(self, settings: Settings) -> None:
        import uvicorn

        from pdfatolye.api.app import create_app

        self.settings = settings
        self.url = f"http://127.0.0.1:{settings.port}"
        self.restart = threading.Event()
        application = create_app(settings)
        application.state.restart = self.restart.set
        # Telefon modu: yerel ağdan da dinler. Pencere yine 127.0.0.1'e bağlanır.
        host = "0.0.0.0" if settings.lan else "127.0.0.1"
        self.server = uvicorn.Server(uvicorn.Config(application, host=host, port=settings.port,
                                                    log_level="warning", log_config=None))
        self.thread = threading.Thread(target=self.server.run, daemon=True, name="sunucu")

    def start(self, timeout: float = 60) -> bool:
        self.thread.start()
        deadline = time.monotonic() + timeout
        while not is_our_server(self.url, timeout=1):
            if not self.thread.is_alive() or time.monotonic() > deadline:
                return False
            time.sleep(0.1)
        lock = self.settings.data_dir / LOCK_NAME
        lock.write_text(json.dumps({"pid": os.getpid(), "port": self.settings.port}),
                        encoding="utf-8")
        log.info("Masaüstü uygulaması açıldı: %s%s", self.url,
                 " (telefon modu)" if self.settings.lan else "")
        return True

    def wait(self, window: subprocess.Popen | None) -> str:
        """Pencere kapanana ("closed") ya da yeniden başlatma istenene ("restart") kadar bekler.
        Pencere yoksa (Edge/Chrome bulunamadı) sunucu süreç sonlanana kadar açık kalır."""
        while True:
            if self.restart.wait(0.25):
                return "restart"
            if window is not None and window.poll() is not None:
                return "closed"
            if not self.thread.is_alive():
                return "closed"

    def stop(self) -> None:
        self.server.should_exit = True
        self.thread.join(timeout=15)
        with contextlib.suppress(OSError):
            if (read_lock(self.settings) or {}).get("pid") == os.getpid():
                (self.settings.data_dir / LOCK_NAME).unlink()


def _start_server(settings: Settings, previous_port: int | None) -> _Server | None:
    """Sunucuyu açar. Yeniden başlatmada istenen port bir süre beklenir (eski sunucu yeni
    kapandı); hâlâ doluysa eski port kullanılır (pencere onu biliyor), o da doluysa boş bir port."""
    wanted = settings.port
    if previous_port is not None:
        deadline = time.monotonic() + 5
        while not port_free(wanted) and time.monotonic() < deadline:
            time.sleep(0.2)
        if not port_free(wanted):
            log.warning("Port %s kullanımda; %s ile devam ediliyor", wanted, previous_port)
            wanted = previous_port
    settings.port = pick_port(wanted)
    server = _Server(settings)
    return server if server.start() else None


def _quiet_console(settings: Settings) -> None:
    """pythonw'da stdout/stderr yoktur (None): yazmaya çalışan kütüphane çöker. Günlüğe yönlenir."""
    if sys.stdout is None or sys.stderr is None:
        stream = open(settings.logs_dir / "konsol.log", "a", encoding="utf-8",  # noqa: SIM115
                      buffering=1)
        sys.stdout = sys.stdout or stream
        sys.stderr = sys.stderr or stream
