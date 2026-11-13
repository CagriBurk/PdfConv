"""Baskı için çevrimdışı ve yalıtılmış tarayıcı. Yazdırılan belge güvenilir değildir.

"Dosyalar internete çıkmaz" vaadi burada korunur. Katmanlar:
1. Tarayıcı ölü bir vekil sunucu (proxy) ile başlar: ağ yığınından çıkan her şey (http, WebSocket,
   DNS ön yükleme, tarayıcının kendi arka plan istekleri) oraya gider ve düşer. WebSocket
   `page.route`'a takılmadığı için asıl koruması budur. (`page.route_web_socket` kullanılmaz:
   Playwright'ın eşzamanlı API'sinde sayfa açılışını kilitliyor.)
2. `page.route` her isteği denetler: yalnızca `allow_file`'ın izin verdiği yerel dosyalar açılır.
   Bir belge `<iframe src="file:///...">` ile diskteki başka bir dosyayı PDF'e gömemez.
"""

from __future__ import annotations

import contextlib
from collections.abc import Callable
from pathlib import Path
from urllib.parse import urlparse
from urllib.request import url2pathname

# 9 numaralı port (discard) dinlenmez; bağlantı hemen reddedilir. Tarayıcı varsayılan olarak
# loopback'i vekilden muaf tutar; `<-loopback>` bu muafiyeti kaldırır.
OFFLINE_ARGS = [
    "--proxy-server=http://127.0.0.1:9",
    "--proxy-bypass-list=<-loopback>",
    "--disable-background-networking",
    "--disable-component-update",
    "--disable-sync",
    "--no-first-run",
    "--no-default-browser-check",
    "--force-webrtc-ip-handling-policy=disable_non_proxied_udp",
]
_LOCAL_SCHEMES = ("data:", "about:", "blob:")


MARKER_FLAG = "--pa-isaret"


def launch_offline(playwright, executable_path: str, marker: str | None = None):
    """Başsız, ağsız tarayıcı. `marker`: komut satırına eklenen (tarayıcının yok saydığı) işaret;
    takılan ya da iptal edilen baskıda süreç ağacı bununla bulunup öldürülür
    (`OfflineBrowser`)."""
    args = OFFLINE_ARGS + ([f"{MARKER_FLAG}={marker}"] if marker else [])
    return playwright.chromium.launch(executable_path=executable_path, headless=True,
                                      args=args)


class OfflineBrowser:
    """Playwright + işaretli tarayıcı. Kesilemeyen çağrıları (`page.pdf`, `evaluate`) `guard`
    ile korur: süre dolunca ya da iş iptal edilince tarayıcı süreç ağacı öldürülür, çağrı
    hatayla döner ve `TimedOut` / `Cancelled` yükselir. Sunucu kapanırken de öldürülür.

        with OfflineBrowser(path) as ob:
            with ob.guard(timeout=120):
                page = new_offline_page(ob.browser, ...)
                ...
    """

    def __init__(self, executable_path: str) -> None:
        self.executable_path = executable_path
        self.browser = None
        self._pw = None
        self._marker = ""
        self._key: int | None = None

    def _kill(self) -> None:
        from pdfatolye import proc

        if self._marker:
            proc.kill_marked(self._marker)

    def start(self) -> None:
        import uuid

        from playwright.sync_api import sync_playwright

        from pdfatolye import proc

        self._marker = uuid.uuid4().hex
        self._pw = sync_playwright().start()
        try:
            self.browser = launch_offline(self._pw, self.executable_path, self._marker)
        except Exception:
            self._pw.stop()
            self._pw = None
            raise
        self._key = proc.register(self._kill)

    def ensure(self) -> None:
        """Önceki baskıda öldürüldüyse yeniden başlatır (çok dosyalı baskı sürsün)."""
        if self.browser is not None and self.browser.is_connected():
            return
        self.stop()
        self.start()

    def stop(self) -> None:
        from pdfatolye import proc

        try:
            if self.browser is not None and self.browser.is_connected():
                self.browser.close()
        except Exception:
            self._kill()
        finally:
            self.browser = None
            if self._key is not None:
                proc.unregister(self._key)
                self._key = None
            if self._pw is not None:
                with contextlib.suppress(Exception):
                    self._pw.stop()
                self._pw = None

    @contextlib.contextmanager
    def guard(self, timeout: float):
        from pdfatolye import proc

        with proc.Watchdog(self._kill, timeout) as dog:
            try:
                yield
            except Exception:
                dog.check()  # tarayıcıyı bekçi öldürdüyse asıl neden: iptal / zaman aşımı
                raise
            dog.check()

    def __enter__(self) -> OfflineBrowser:
        self.start()
        return self

    def __exit__(self, *exc) -> None:
        self.stop()


def file_url_path(url: str) -> Path | None:
    """file: adresinin yerel yolu; çözülemezse None."""
    try:
        return Path(url2pathname(urlparse(url).path))
    except (ValueError, OSError):
        return None


def new_offline_page(browser, allow_file: Callable[[Path], bool], blocked: list[str]):
    """Kendi bağlamında sayfa açar. Engellenen adresler `blocked`'a eklenir. İşin bitince
    `page.context.close()` çağır."""
    context = browser.new_context(service_workers="block")
    page = context.new_page()

    def route(r) -> None:
        url = r.request.url
        if url.startswith(_LOCAL_SCHEMES):
            r.continue_()
            return
        if url.startswith("file:"):
            path = file_url_path(url)
            if path is not None:
                try:
                    allowed = allow_file(path.resolve())
                except (OSError, ValueError):
                    allowed = False
                if allowed:
                    r.continue_()
                    return
        blocked.append(url)
        r.abort()

    page.route("**/*", route)
    return page


def blocked_warnings(blocked: list[str], prefix: str = "") -> list[str]:
    """Engellenen adresler için kullanıcıya gösterilecek uyarılar."""
    out = []
    for url in dict.fromkeys(blocked):
        if url.startswith("file:"):
            path = file_url_path(url)
            name = path.name if path is not None else url
            out.append(f"{prefix}Belgenin dışındaki yerel dosya güvenlik için açılmadı: {name}")
        else:
            out.append(f"{prefix}Uzak kaynak çevrimdışı olduğu için yüklenmedi: {url}")
    return out
