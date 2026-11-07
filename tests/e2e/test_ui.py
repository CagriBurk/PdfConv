"""Uçtan uca: gerçek sunucu (ayrı iş parçacığında) + gerçek tarayıcı (Edge, başsız).

Derlenmiş arayüz (web/dist) ya da tarayıcı yoksa atlanır.
"""

from __future__ import annotations

import socket
import threading
import time
import urllib.request
from pathlib import Path

import pymupdf
import pytest

from pdfatolye import engines
from pdfatolye.api.app import WEB_DIST, create_app
from pdfatolye.settings import Settings
from tests.fixtures import make_fixtures as fx

BROWSER = engines.detect_browser(Settings()).path
pytestmark = pytest.mark.skipif(
    not BROWSER or not (WEB_DIST / "index.html").is_file(),
    reason="Tarayıcı ya da derlenmiş arayüz (npm --prefix web run build) yok",
)
TIMEOUT_MS = 20_000


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.fixture(scope="module")
def server(tmp_path_factory):
    import uvicorn

    port = _free_port()
    settings = Settings(data_dir=tmp_path_factory.mktemp("veri"), port=port)
    app = create_app(settings, start_background=False)
    srv = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=port, log_level="warning"))
    thread = threading.Thread(target=srv.run, daemon=True)
    thread.start()
    base = f"http://127.0.0.1:{port}"
    for _ in range(100):
        try:
            urllib.request.urlopen(f"{base}/api/health", timeout=1)
            break
        except OSError:
            time.sleep(0.1)
    yield base, app
    srv.should_exit = True
    thread.join(timeout=10)


@pytest.fixture(scope="module")
def browser():
    from playwright.sync_api import sync_playwright

    with sync_playwright() as pw:
        b = pw.chromium.launch(executable_path=BROWSER, headless=True)
        yield b
        b.close()


@pytest.fixture
def page(browser):
    ctx = browser.new_context(viewport={"width": 1400, "height": 1000}, locale="tr-TR")
    p = ctx.new_page()
    p.set_default_timeout(TIMEOUT_MS)
    yield p
    ctx.close()


def _wait_version(app, file_id: str, version: int) -> Path:
    store = app.state.store
    for _ in range(200):
        if store.get(file_id).current.n == version:
            return store.path(file_id)
        time.sleep(0.1)
    raise AssertionError(f"{version}. sürüm oluşmadı")


def test_upload_reorder_delete_save(server, page, tmp_path):
    base, app = server
    pdf = fx.numbered(tmp_path / "ders.pdf", 3, with_toc=False)
    page.goto(base)
    page.locator("input[type=file]").first.set_input_files(str(pdf))
    page.wait_for_url("**/#/duzenle/*")
    tiles = page.locator(".page-tile")
    tiles.nth(2).wait_for()
    assert tiles.count() == 3
    tiles.first.click()
    page.keyboard.press("Delete")
    page.get_by_role("button", name="Kaydet", exact=True).click()
    file_id = page.url.rsplit("/", 1)[-1]
    out = _wait_version(app, file_id, 2)
    assert fx.labels(out) == ["Sayfa 2", "Sayfa 3"]


def test_editor_adds_turkish_text_on_rotated_page(server, page, tmp_path):
    base, app = server
    meta = app.state.store.add_file(fx.rotated(tmp_path / "r.pdf"), "döndürülmüş.pdf",
                                    source="upload")
    page.goto(f"{base}/#/editor/{meta.id}")
    page.locator(".editor-page canvas").first.wait_for()
    page.locator(".editor-thumb").nth(1).click()  # 90° döndürülmüş sayfa
    page.wait_for_timeout(500)
    page.get_by_role("button", name="Yazı", exact=True).click()
    stage = page.locator(".editor-stage canvas").first
    box = stage.bounding_box()
    page.mouse.click(box["x"] + box["width"] * 0.3, box["y"] + box["height"] * 0.5)
    text = page.get_by_label("Metin")
    text.fill("Onaylandı – Çağrı İşçi")
    page.get_by_role("button", name="Uygula (1)").click()
    out = _wait_version(app, meta.id, 2)
    with pymupdf.open(out) as doc:
        assert "Onaylandı – Çağrı İşçi" in doc[1].get_text()
        line = doc[1].get_text("dict")["blocks"][-1]["lines"][0]
        # 90° döndürülmüş sayfada yazı okuyana dik: sayfa uzayında yukarı akar.
        assert line["dir"] == pytest.approx((0, -1), abs=1e-3)


def test_csp_allows_the_real_app(server, page, tmp_path):
    """Güvenlik başlıkları uygulamayı bozmasın: pdf.js, küçük resimler, editör tuvali, Markdown
    önizlemesindeki KaTeX ve resim. Tek bir CSP ihlali bile burada yakalanır."""
    base, app = server
    problems: list[str] = []
    page.on("console", lambda m: problems.append(m.text)
            if m.type == "error" and "Content Security Policy" in m.text else None)
    page.on("pageerror", lambda e: problems.append(str(e)))
    meta = app.state.store.add_file(fx.numbered(tmp_path / "a.pdf", 2, with_toc=False), "a.pdf",
                                    source="upload")
    page.goto(f"{base}/#/duzenle/{meta.id}")
    page.locator(".page-tile img").first.wait_for()
    page.goto(f"{base}/#/editor/{meta.id}")
    page.locator(".editor-page canvas").first.wait_for()
    img = app.state.store.add_file(fx.transparent_png(tmp_path / "res.png"), "res.png",
                                   source="upload")
    note = app.state.store.add_file(_note(tmp_path), "n.md", source="upload")
    page.goto(f"{base}/#/md?dosya={note.id}&ek={img.id}")
    frame = page.frame_locator("iframe[title='Önizleme']")
    frame.locator(".katex").first.wait_for()
    assert frame.locator("img").first.evaluate("i => i.complete && i.naturalWidth > 0")
    assert problems == []


def test_preview_blocks_note_scripts(server, page, tmp_path):
    base, app = server
    note = tmp_path / "kotu.md"
    note.write_text("# Not\n\n$x$\n\n<script>window.parent.document.title='ELEGECIRILDI'</script>"
                    "\n", encoding="utf-8")
    meta = app.state.store.add_file(note, "kotu.md", source="upload")
    page.goto(f"{base}/#/md?dosya={meta.id}")
    frame = page.frame_locator("iframe[title='Önizleme']")
    frame.locator(".katex").first.wait_for()
    assert page.title() != "ELEGECIRILDI"


def _note(tmp_path: Path) -> Path:
    note = tmp_path / "n.md"
    note.write_text("# Başlık\n\n$E = mc^2$\n\n![[res.png]]\n", encoding="utf-8")
    return note


def test_settings_lists_engines_and_tools_are_live(server, page):
    base, _ = server
    page.goto(f"{base}/#/ayarlar")
    page.get_by_role("heading", name="Motorlar").wait_for()
    page.get_by_text("Telefon modu").first.wait_for()
    page.goto(f"{base}/#/araclar")
    # Bütün araç kartları artık açık (Faz etiketi kalmadı).
    page.locator(".tool-card.active").first.wait_for()
    assert page.locator(".tool-card:not(.active)").count() == 0
