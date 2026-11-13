"""Dış süreçler: zaman aşımı, iptal, süreç ağacını öldürme ve kapanışta temizlik.

LibreOffice, Ghostscript, OCR ve başsız tarayıcı uzun sürebilir ya da takılabilir. Buradaki
yardımcılar:
- `run` / `spawn`: süreci başlatır, iptal ve zaman aşımında süreç AĞACINI öldürür.
- `Watchdog`: kesilemeyen bir çağrıyı (Playwright `page.pdf`, `evaluate`) bekleyen iş parçacığı
  için bekçi: süre dolunca ya da iş iptal edilince verilen süreçleri öldürür; çağrı hatayla döner.
- `cancel_scope`: iş yöneticisi her işi bir iptal bayrağıyla çalıştırır; alt katmanlar bayrağı
  parametre taşımadan `cancelled()` ile görür.
- `kill_all`: sunucu kapanırken yaşayan bütün alt süreçler öldürülür (öksüz LibreOffice kalmasın).
"""

from __future__ import annotations

import contextlib
import itertools
import logging
import subprocess
import threading
import time
from collections.abc import Callable, Iterator, Sequence

import psutil

log = logging.getLogger("pdfatolye.proc")
NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)
POLL_S = 0.2


class Cancelled(Exception):
    """İş kullanıcı tarafından iptal edildi (ya da sunucu kapanıyor)."""


class TimedOut(Exception):
    pass


# --- iptal bayrağı (iş başına, iş parçacığına bağlı) -------------------------------------------

_local = threading.local()


@contextlib.contextmanager
def cancel_scope(is_cancelled: Callable[[], bool]) -> Iterator[None]:
    prev = getattr(_local, "check", None)
    _local.check = is_cancelled
    try:
        yield
    finally:
        _local.check = prev


def cancel_check() -> Callable[[], bool]:
    """Bu iş parçacığındaki işin iptal denetimi (iş dışında: hiç iptal edilmez)."""
    return getattr(_local, "check", None) or (lambda: False)


def cancelled() -> bool:
    return cancel_check()()


def raise_if_cancelled() -> None:
    if cancelled():
        raise Cancelled()


# --- öldürme ----------------------------------------------------------------------------------

def kill_tree(pid: int) -> None:
    """Süreci ve bütün alt süreçlerini öldürür (önce çocuklar: ana süreç ölünce yetim kalmasın)."""
    try:
        parent = psutil.Process(pid)
        children = parent.children(recursive=True)
    except psutil.NoSuchProcess:
        return
    for p in [*children, parent]:
        with contextlib.suppress(psutil.NoSuchProcess, psutil.AccessDenied):
            p.kill()
    psutil.wait_procs([*children, parent], timeout=5)


def kill_marked(marker: str, name_prefix: str | None = None) -> int:
    """Komut satırında `marker` geçen süreçleri (ve ağaçlarını) öldürür. Bir süreç başka bir
    süreci açıp çıkıyorsa (soffice.com → soffice.bin, Edge) ağacı izlemek yetmez; işaret izlenir.
    Öldürülen süreç sayısını döndürür."""
    killed = 0
    for p in psutil.process_iter(["name", "cmdline"]):
        try:
            if name_prefix and not (p.info["name"] or "").lower().startswith(name_prefix):
                continue
            if marker in " ".join(p.info["cmdline"] or []):
                kill_tree(p.pid)
                killed += 1
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue
    return killed


# --- kapanışta temizlik için kayıt -------------------------------------------------------------

_killers: dict[int, Callable[[], None]] = {}
_ids = itertools.count(1)
_reg_lock = threading.Lock()


def register(killer: Callable[[], None]) -> int:
    with _reg_lock:
        key = next(_ids)
        _killers[key] = killer
        return key


def unregister(key: int) -> None:
    with _reg_lock:
        _killers.pop(key, None)


def kill_all() -> int:
    """Kayıtlı bütün alt süreçleri öldürür (sunucu kapanırken). Sayısını döndürür."""
    with _reg_lock:
        killers = list(_killers.values())
        _killers.clear()
    for k in killers:
        try:
            k()
        except Exception:  # kapanışta tek bir hata diğerlerini durdurmasın
            log.exception("Alt süreç kapatılamadı")
    return len(killers)


# --- çalıştırma -------------------------------------------------------------------------------

@contextlib.contextmanager
def spawn(args: Sequence[str], *, marker: str | None = None, marker_name: str | None = None,
          **popen) -> Iterator[subprocess.Popen]:
    """Süreci başlatır ve kaydeder; bloktan nasıl çıkılırsa çıkılsın hâlâ yaşıyorsa ağacıyla
    öldürülür. `marker`: süreç kendi kopyasını açıp çıkıyorsa onu da bulmak için."""
    proc = subprocess.Popen(list(args), creationflags=NO_WINDOW, **popen)

    def kill() -> None:
        if proc.poll() is None:
            kill_tree(proc.pid)
        if marker:
            kill_marked(marker, marker_name)

    key = register(kill)
    try:
        yield proc
    finally:
        unregister(key)
        kill()


def run(args: Sequence[str], *, timeout: float, marker: str | None = None,
        marker_name: str | None = None, should_cancel: Callable[[], bool] | None = None,
        **popen) -> subprocess.CompletedProcess:
    """`subprocess.run` gibi (çıktılar yakalanır) ama iptal edilebilir: iptalde `Cancelled`,
    süre dolunca `TimedOut` yükselir; ikisinde de süreç ağacı öldürülür."""
    check = should_cancel or cancel_check()
    popen.setdefault("stdout", subprocess.PIPE)
    popen.setdefault("stderr", subprocess.PIPE)
    deadline = time.monotonic() + timeout
    with spawn(args, marker=marker, marker_name=marker_name, **popen) as proc:
        while True:
            try:
                out, err = proc.communicate(timeout=POLL_S)
                break
            except subprocess.TimeoutExpired:
                if check():
                    raise Cancelled() from None
                if time.monotonic() > deadline:
                    raise TimedOut() from None
        return subprocess.CompletedProcess(list(args), proc.returncode, out, err)


def run_lines(args: Sequence[str], *, timeout: float, on_line: Callable[[str], None],
              should_cancel: Callable[[], bool] | None = None, tail: int = 40) -> tuple[int, str]:
    """`run` gibi iptal edilebilir, ama çıktıyı (stdout + stderr) satır satır `on_line`'a verir:
    uzun süren aracın ilerlemesi (Ghostscript "Page 12") arayüze taşınır. Dönüş: (çıkış kodu,
    son `tail` satır)."""
    import queue

    check = should_cancel or cancel_check()
    lines: queue.Queue[str | None] = queue.Queue()
    last: list[str] = []
    deadline = time.monotonic() + timeout
    with spawn(args, stdout=subprocess.PIPE, stderr=subprocess.STDOUT) as proc:
        def pump() -> None:
            assert proc.stdout is not None
            try:
                for raw in iter(proc.stdout.readline, b""):
                    lines.put(raw.decode("utf-8", "replace").rstrip())
            finally:
                lines.put(None)

        threading.Thread(target=pump, daemon=True, name="cikti").start()
        while True:
            try:
                line = lines.get(timeout=POLL_S)
            except queue.Empty:
                if proc.poll() is not None and lines.empty():
                    break
                line = ""
            if line is None:
                break
            if line:
                last = [*last[-(tail - 1):], line]
                on_line(line)
            if check():
                raise Cancelled()
            if time.monotonic() > deadline:
                raise TimedOut()
        return proc.wait(), "\n".join(last)


class Watchdog:
    """Kesilemeyen bir çağrının bekçisi. `kill` süre dolunca ya da iş iptal edilince çağrılır;
    çağrı hatayla döner, hemen ardından `check()` doğru nedeni (Cancelled / TimedOut) yükseltir.

        with Watchdog(kill_browser, timeout=120) as dog:
            try:
                page.pdf(...)
            except Exception:
                dog.check()
                raise
        """

    def __init__(self, kill: Callable[[], None], timeout: float,
                 should_cancel: Callable[[], bool] | None = None) -> None:
        self._kill = kill
        self._timeout = timeout
        self._check = should_cancel or cancel_check()
        self._stop = threading.Event()
        self.fired: str | None = None  # "cancel" | "timeout"

    def __enter__(self) -> Watchdog:
        deadline = time.monotonic() + self._timeout

        def watch() -> None:
            while not self._stop.wait(POLL_S):
                reason = ("cancel" if self._check() else
                          "timeout" if time.monotonic() > deadline else None)
                if reason:
                    self.fired = reason
                    try:
                        self._kill()
                    except Exception:
                        log.exception("Bekçi süreci öldüremedi")
                    return

        self._thread = threading.Thread(target=watch, daemon=True, name="bekci")
        self._thread.start()
        return self

    def check(self) -> None:
        if self.fired == "cancel":
            raise Cancelled()
        if self.fired == "timeout":
            raise TimedOut()

    def __exit__(self, *exc) -> None:
        self._stop.set()
        self._thread.join(timeout=5)
