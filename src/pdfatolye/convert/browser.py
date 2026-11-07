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


def launch_offline(playwright, executable_path: str):
    return playwright.chromium.launch(executable_path=executable_path, headless=True,
                                      args=OFFLINE_ARGS)


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
            if path is not None and allow_file(path.resolve()):
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
