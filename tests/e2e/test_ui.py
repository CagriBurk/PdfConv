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
    # İlk açılış tanıtımı ayrı testte; diğer testler doğrudan ana sayfayla başlar.
    settings = Settings(data_dir=tmp_path_factory.mktemp("veri"), port=port, welcome_done=True)
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
    """Tarayıcı konsolu ve sayfa hataları toplanır; test başarısız olursa pytest bunları
    ("Captured stdout teardown") gösterir. CI'da tarayıcı sürümü farklı olabilir, nedeni
    görmeden tahmin etmeyelim."""
    ctx = browser.new_context(viewport={"width": 1400, "height": 1000}, locale="tr-TR")
    p = ctx.new_page()
    p.set_default_timeout(TIMEOUT_MS)
    log: list[str] = []
    p.on("console", lambda m: log.append(f"konsol {m.type}: {m.text}")
         if m.type in ("error", "warning") else None)
    p.on("pageerror", lambda e: log.append(f"sayfa hatası: {e}"))
    p.on("requestfailed", lambda r: log.append(f"istek başarısız: {r.url} {r.failure}"))
    yield p
    print(f"tarayıcı: {BROWSER} sürüm {browser.version}")
    for line in log:
        print(line)
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


def _tile_images(page, n: int) -> list[str]:
    from playwright.sync_api import expect

    tiles = page.locator(".page-tile")
    expect(tiles).to_have_count(n)  # wait_for_function dize değerlendirir: CSP engeller
    for i in range(n):
        tiles.nth(i).locator("img").wait_for()
    return [tiles.nth(i).locator("img").get_attribute("src") for i in range(n)]


def test_thumbnails_follow_version_after_undo_and_resave(server, page, tmp_path):
    """Kaydet (v2) → Önceki sürüme dön → başka değişiklik → Kaydet (yeni v2): küçük resimler
    eski v2'ninkiler olmamalı (sürüm numarası yeniden kullanılıyor)."""
    base, app = server
    meta = app.state.store.add_file(fx.numbered(tmp_path / "s.pdf", 3, with_toc=False),
                                    "sürümler.pdf", source="upload")
    page.goto(f"{base}/#/duzenle/{meta.id}")
    original = _tile_images(page, 3)
    assert len(set(original)) == 3
    page.locator(".page-tile").first.click()
    page.keyboard.press("Delete")
    page.get_by_role("button", name="Kaydet", exact=True).click()
    from playwright.sync_api import expect

    _wait_version(app, meta.id, 2)
    expect(page.get_by_role("button", name="Önceki sürüme dön")).to_be_visible()
    assert _tile_images(page, 2) == original[1:]  # v2: 2, 3
    undo = page.get_by_role("button", name="Önceki sürüme dön")
    undo.click()
    expect(undo).to_be_hidden()
    assert _tile_images(page, 3) == original
    page.locator(".page-tile").nth(2).click()
    page.keyboard.press("Delete")
    page.get_by_role("button", name="Kaydet", exact=True).click()
    out = _wait_version(app, meta.id, 2)
    assert fx.labels(out) == ["Sayfa 1", "Sayfa 2"]
    # Düzenleyici yeni sürümü yükleyene kadar bekle (öncesinde ekranda hâlâ v1'in resimleri
    # durur ve test yanlışlıkla geçer): geri alma düğmesi yalnızca sürüm > 1 iken görünür.
    expect(undo).to_be_visible()
    page.wait_for_timeout(500)
    assert _tile_images(page, 2) == original[:2]  # yeni v2: 1, 2 (eski v2'nin 2, 3'ü değil)


def test_unsaved_changes_ask_before_in_app_navigation(server, page, tmp_path):
    base, app = server
    meta = app.state.store.add_file(fx.numbered(tmp_path / "k.pdf", 3, with_toc=False),
                                    "kayıt.pdf", source="upload")
    page.goto(f"{base}/#/duzenle/{meta.id}")
    _tile_images(page, 3)
    page.locator(".page-tile").first.click()
    page.keyboard.press("Delete")
    asked: list[str] = []

    def dismiss(d):
        asked.append(d.message)
        d.dismiss()

    page.once("dialog", dismiss)
    page.get_by_role("link", name="Araçlar", exact=True).click()
    page.wait_for_timeout(300)
    assert asked and "Kaydedilmemiş" in asked[0]
    assert "#/duzenle/" in page.url and page.locator(".page-tile").count() == 2  # iş duruyor
    page.go_back()  # geri düğmesi de sorar
    page.wait_for_timeout(300)
    assert len(asked) == 1 or "Kaydedilmemiş" in asked[-1]
    page.once("dialog", lambda d: d.accept())
    page.get_by_role("link", name="Araçlar", exact=True).click()
    page.wait_for_url("**/#/araclar")


def test_markdown_unsaved_text_and_cp1254_note(server, page, tmp_path):
    base, app = server
    note = tmp_path / "eski.md"
    note.write_bytes("# Çalışma\n\nığdır şöyle: ĞÜŞİÖÇ\n".encode("cp1254"))
    meta = app.state.store.add_file(note, "eski.md", source="upload")
    page.goto(f"{base}/#/md?dosya={meta.id}")
    editor = page.get_by_label("Markdown metni")
    editor.wait_for()
    assert "ığdır şöyle: ĞÜŞİÖÇ" in editor.input_value()  # sunucu cp1254'ü çözdü
    page.get_by_text("Windows-1254").first.wait_for()
    editor.press("End")
    editor.type("\n\nYeni satır: çok önemli")
    page.get_by_text("Kaydedilmemiş değişiklik var").wait_for()
    asked: list[str] = []
    page.once("dialog", lambda d: (asked.append(d.message), d.dismiss()))
    page.get_by_role("link", name="İşler ve dosyalar").click()
    page.wait_for_timeout(300)
    assert asked and "#/md" in page.url
    # Sekme kapanmış gibi: aynı tarayıcı profilinde yeni sekme taslağı önerir.
    page.wait_for_timeout(800)  # taslak yazımı (gecikmeli)
    other = page.context.new_page()
    other.goto(f"{base}/#/md?dosya={meta.id}")
    other.get_by_text("kaydedilmemiş bir taslak var").wait_for()
    other.get_by_role("button", name="Taslağı aç").click()
    assert "Yeni satır: çok önemli" in other.get_by_label("Markdown metni").input_value()
    other.close()


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



# --- Faz D: ürün deneyimi ----------------------------------------------------------------------

def _no_horizontal_overflow(page) -> bool:
    return page.evaluate("() => document.documentElement.scrollWidth <= "
                         "document.documentElement.clientWidth + 1")


def test_first_run_welcome_then_home(server, page):
    from playwright.sync_api import expect

    base, app = server
    app.state.settings.welcome_done = False
    try:
        page.goto(base)
        expect(page.get_by_role("heading", name="PDF Atölyesi'ne hoş geldin")).to_be_focused()
        page.get_by_role("heading", name="Hazırlık").wait_for()
        assert page.locator(".dropzone").count() == 0  # önce tanıtım
        page.get_by_role("button", name="Başla").click()
        page.get_by_text("Dosyayı buraya bırak").wait_for()
        assert app.state.settings.welcome_done is True
        cfg = app.state.settings.data_dir / "config.toml"
        assert "welcome_done = true" in cfg.read_text(encoding="utf-8")
        page.reload()
        page.get_by_text("Dosyayı buraya bırak").wait_for()  # bir daha gösterilmez
    finally:
        app.state.settings.welcome_done = True


def test_settings_are_editable_and_developer_info_is_advanced(server, page, tmp_path):
    from playwright.sync_api import expect

    base, app = server
    s = app.state.settings
    vault = tmp_path / "Obsidian Kasası"
    vault.mkdir()
    try:
        page.goto(f"{base}/#/ayarlar")
        page.get_by_label("Dosyaları sakla").fill("72")
        page.get_by_label("Obsidian kasası").fill(str(vault))
        page.get_by_label("Varsayılan tema").select_option("rapor")
        page.get_by_label("Varsayılan kağıt").select_option("A5")
        page.get_by_role("button", name="Kaydet", exact=True).first.click()
        page.get_by_text("Ayarlar kaydedildi.").wait_for()
        assert (s.retention_hours, s.vault_path, s.default_theme, s.default_paper) == (
            72, vault.resolve(), "rapor", "A5")
        assert "retention_hours = 72" in (s.data_dir / "config.toml").read_text(encoding="utf-8")
        # Telefon modu artık ayardan açılır (eski metin "baslat.bat --lan" diyordu).
        phone = page.get_by_label("Aynı Wi-Fi'deki telefon ve tabletler", exact=False)
        expect(phone).not_to_be_checked()
        assert page.get_by_text("baslat.bat --lan").count() == 0
        # Kütüphane sürümleri ve yollar "Gelişmiş" altında, kapalı.
        libs = page.get_by_role("heading", name="Kütüphaneler")
        expect(libs).to_be_hidden()
        page.get_by_text("Gelişmiş", exact=True).click()
        expect(libs).to_be_visible()
        # Geçersiz yol anlaşılır hata verir, kaydetmez.
        page.get_by_label("Obsidian kasası").fill(str(tmp_path / "yok"))
        page.get_by_role("button", name="Kaydet", exact=True).first.click()
        page.get_by_text("Klasör bulunamadı").wait_for()
        assert s.vault_path == vault.resolve()
    finally:
        from pdfatolye.settings import save_settings

        save_settings(s, {"retention_hours": None, "vault_path": None, "default_theme": None,
                          "default_paper": None})


def _long_note(tmp_path: Path) -> Path:
    note = tmp_path / "uzun.md"
    parts = ["# Uzun not\n"]
    for i in range(1, 121):
        parts.append(f"## Bölüm {i}\n\nParagraf {i}: $x_{{{i}}}^2 + y = {i}$ ve biraz metin.\n")
    note.write_text("\n".join(parts), encoding="utf-8")
    return note


def test_markdown_preview_keeps_scroll_position_while_typing(server, page, tmp_path):
    """Önizleme her güncellemede yeniden yüklenip başa atlıyordu (srcdoc)."""
    base, app = server
    meta = app.state.store.add_file(_long_note(tmp_path), "uzun.md", source="upload")
    page.goto(f"{base}/#/md?dosya={meta.id}")
    frame = page.frame_locator("iframe[title='Önizleme']")
    frame.get_by_text("Paragraf 120:").wait_for()
    frame.locator(".katex").first.wait_for()
    root = frame.locator("html")
    root.evaluate("e => { e.scrollTop = (e.scrollHeight - e.clientHeight) * 0.6; }")
    page.wait_for_timeout(200)
    before = root.evaluate("e => e.scrollTop")
    assert before > 500
    editor = page.get_by_label("Markdown metni")
    editor.press("Control+End")
    editor.type("\n\nSON İŞARET $z$")
    frame.get_by_text("SON İŞARET").wait_for()
    page.wait_for_timeout(300)
    after = root.evaluate("e => e.scrollTop")
    assert abs(after - before) < 50, (before, after)
    # Yerinde güncellenen içerikte formül de çizildi.
    assert frame.locator("p", has_text="SON İŞARET").locator(".katex").count() == 1


def test_markdown_preview_ignores_late_stale_response(server, page, tmp_path):
    """Yavaş gelen eski önizleme yanıtı yenisinin üstüne yazılmamalı."""
    base, app = server
    note = tmp_path / "s.md"
    note.write_text("# Not\n\nİLK\n", encoding="utf-8")
    meta = app.state.store.add_file(note, "s.md", source="upload")
    held: list = []

    def handler(route):
        if not held and "ESKI" in (route.request.post_data or ""):
            held.append((route, route.fetch()))  # yanıt alınır ama sayfaya hemen verilmez
            return
        route.continue_()

    page.route("**/api/md/preview", handler)
    page.goto(f"{base}/#/md?dosya={meta.id}")
    frame = page.frame_locator("iframe[title='Önizleme']")
    frame.get_by_text("İLK").wait_for()
    editor = page.get_by_label("Markdown metni")
    editor.fill("# Not\n\nESKI\n")
    for _ in range(50):
        if held:
            break
        page.wait_for_timeout(100)
    assert held, "eski istek yakalanamadı"
    editor.fill("# Not\n\nYENİ\n")
    frame.get_by_text("YENİ").wait_for()
    route, response = held[0]
    route.fulfill(response=response)  # eski yanıt şimdi geliyor
    page.wait_for_timeout(1000)
    assert frame.get_by_text("YENİ").count() == 1
    assert frame.get_by_text("ESKI").count() == 0


def test_organizer_works_with_keyboard_only(server, page, tmp_path):
    from playwright.sync_api import expect

    base, app = server
    meta = app.state.store.add_file(fx.numbered(tmp_path / "k.pdf", 4, with_toc=False),
                                    "klavye.pdf", source="upload")
    page.goto(f"{base}/#/duzenle/{meta.id}")
    tiles = page.locator(".page-tile")
    _tile_images(page, 4)
    expect(page.get_by_role("listbox", name="Sayfalar")).to_be_visible()
    tiles.first.focus()
    page.keyboard.press("ArrowRight")  # 2. sayfa odakta ve seçili
    expect(tiles.nth(1)).to_be_focused()
    expect(tiles.nth(1)).to_have_attribute("aria-selected", "true")
    expect(tiles.nth(0)).to_have_attribute("aria-selected", "false")
    page.keyboard.press("Control+r")  # yenile kısayolu döndürme sayılmamalı (#66)
    expect(page.get_by_role("button", name="Kaydet", exact=True)).to_be_disabled()
    url = page.url
    page.keyboard.press("Alt+ArrowRight")  # 2. sayfa bir sağa: 1, 3, 2, 4
    page.wait_for_timeout(200)
    assert page.url == url  # Alt+← / → tarayıcıda gezinme yapmadı
    expect(tiles.nth(2)).to_be_focused()  # odak taşınan sayfayla gitti
    page.keyboard.press("Enter")  # büyük önizleme
    dialog = page.get_by_role("dialog")
    expect(dialog).to_be_visible()
    page.keyboard.press("Escape")
    expect(dialog).to_be_hidden()
    expect(tiles.nth(2)).to_be_focused()  # odak açan sayfaya döndü
    page.keyboard.press("ArrowLeft")  # orijinal 3. sayfa
    page.keyboard.press("Shift+ArrowLeft")  # + orijinal 1. sayfa
    for _ in range(3):  # yalnızca odak taşınır, seçim değişmez
        page.keyboard.press("Control+ArrowRight")
    page.keyboard.press("Space")  # orijinal 4. sayfayı da seçime ekle
    page.get_by_text("3 sayfa seçili").wait_for()
    page.keyboard.press("Delete")
    expect(tiles).to_have_count(1)
    expect(tiles.first).to_be_focused()
    page.get_by_role("button", name="Kaydet", exact=True).click()
    out = _wait_version(app, meta.id, 2)
    assert fx.labels(out) == ["Sayfa 2"]


def test_jobs_have_turkish_names_and_files_can_be_renamed(server, page, tmp_path):
    base, app = server
    meta = app.state.store.add_file(fx.numbered(tmp_path / "j.pdf", 2, with_toc=False),
                                    "eski ad.pdf", source="upload")
    page.goto(base)
    r = page.request.post(f"{base}/api/jobs", data={"type": "compress", "files": [meta.id],
                                                     "level": "kayipsiz"})
    assert r.ok, r.text()
    app.state.jobs.wait(r.json()["id"], 60)
    page.goto(f"{base}/#/isler")
    page.locator(".job-list").get_by_text("Sıkıştırma").first.wait_for()
    assert page.locator(".job-list").get_by_text("compress", exact=True).count() == 0
    page.get_by_role("button", name="eski ad.pdf yeniden adlandır").click()
    field = page.get_by_label("'eski ad.pdf' için yeni ad")
    field.fill("Yeni ad ğüş")
    field.press("Enter")
    page.get_by_text("Yeni ad: Yeni ad ğüş.pdf").wait_for()
    assert app.state.store.get(meta.id).name == "Yeni ad ğüş.pdf"
    # Bu bilgisayardan açıldığı için "Klasörde göster" var (tıklamıyoruz: Gezgin açılır).
    assert page.get_by_role("button", name="Klasörde göster").count() >= 1


def test_render_error_shows_message_not_white_page(server, page):
    """Bir ekranın çizimindeki hata bütün uygulamayı (beyaz sayfa) götürüyordu."""
    from playwright.sync_api import expect

    base, app = server
    bad_job = {"id": "x" * 32, "type": "compress", "status": "bitti", "created": 0,
               "warnings": [], "files": None, "outputs": [], "request": {}, "error": None}
    page.route("**/api/jobs?limit=30", lambda r: r.fulfill(json=[bad_job]))
    page.goto(f"{base}/#/isler")
    page.get_by_role("heading", name="Bu ekranda bir şeyler ters gitti").wait_for()
    expect(page.get_by_role("link", name="Araçlar", exact=True)).to_be_visible()  # uygulama ayakta
    page.get_by_text("Hata kimliği").wait_for()
    eid = page.locator(".crash strong.mono").inner_text()
    log = (app.state.settings.logs_dir / "pdfatolye.log").read_text(encoding="utf-8")
    assert f"[{eid}] arayüz hatası" in log
    page.unroute("**/api/jobs?limit=30")
    page.get_by_role("link", name="Araçlar", exact=True).click()
    page.get_by_text("Dosyayı buraya bırak").wait_for()  # başka ekran sıfırdan kurulur


@pytest.mark.parametrize("width", [390, 1400])
def test_new_screens_fit_the_window(server, page, tmp_path, width):
    base, app = server
    page.set_viewport_size({"width": width, "height": 900})
    app.state.store.add_file(fx.numbered(tmp_path / "g.pdf", 1, with_toc=False),
                             "çok uzun bir dosya adı ki dar ekranda taşmasın diye denenir.pdf",
                             source="upload")
    page.goto(f"{base}/#/ayarlar")
    page.get_by_text("Gelişmiş", exact=True).click()
    page.get_by_role("heading", name="Kütüphaneler").wait_for()
    assert _no_horizontal_overflow(page), "Ayarlar taşıyor"
    page.goto(f"{base}/#/isler")
    page.locator(".file-table").wait_for()
    assert _no_horizontal_overflow(page), "İşler taşıyor"
    app.state.settings.welcome_done = False
    try:
        page.goto(f"{base}/#/araclar")
        page.reload()  # ayarlar açılışta okunur (yalnızca adres karması değişti)
        page.get_by_role("heading", name="PDF Atölyesi'ne hoş geldin").wait_for()
        assert _no_horizontal_overflow(page), "Tanıtım taşıyor"
    finally:
        app.state.settings.welcome_done = True


def test_in_place_preview_update_still_blocks_note_scripts(server, page, tmp_path):
    """Önizleme artık içeriği yerinde günceller (innerHTML): sonradan yazılan betik ve satır içi
    olay işleyicisi de çalışmamalı (çerçevenin içerik güvenlik politikası)."""
    base, app = server
    note = tmp_path / "temiz.md"
    note.write_text("# Not\n\n$x$\n", encoding="utf-8")
    meta = app.state.store.add_file(note, "temiz.md", source="upload")
    page.goto(f"{base}/#/md?dosya={meta.id}")
    frame = page.frame_locator("iframe[title='Önizleme']")
    frame.locator(".katex").first.wait_for()
    editor = page.get_by_label("Markdown metni")
    editor.press("Control+End")
    editor.type('\n\n<img src="yok.png" onerror="parent.document.title=\'ELEGECIRILDI\'">\n\n'
                "<script>parent.document.title='ELEGECIRILDI'</script>\n\nBETİK SONRASI\n")
    frame.get_by_text("BETİK SONRASI").wait_for()
    page.wait_for_timeout(500)
    assert page.title() != "ELEGECIRILDI"
    assert frame.locator("img[onerror]").count() == 1  # yerinde güncellendi, ama çalışmadı


def test_restart_button_moves_window_to_new_port(browser, tmp_path, monkeypatch):
    """Masaüstü uygulamasında port değişip "Şimdi yeniden başlat" denince pencere yeni adrese
    geçmeli. (Kurulu pakette denendi: sunucu yeni portta açılıyordu ama arayüz, uygulamanın
    `connect-src 'self'` politikası başka portu yoklamayı engellediği için eski adreste
    kalıyordu.)"""
    from playwright.sync_api import expect

    from pdfatolye import desktop

    monkeypatch.setattr(desktop, "kill_children_on_exit", lambda: False)
    port, new_port = _free_port(), _free_port()
    cfg = tmp_path / "config.toml"
    data = str(tmp_path / "veri").replace("\\", "/")
    cfg.write_text(f'data_dir = "{data}"\nport = {port}\nwelcome_done = true\n',
                   encoding="utf-8")
    closed = threading.Event()
    opened: list[str] = []

    class Window:
        def poll(self):
            return 0 if closed.is_set() else None

    def fake_open(s, url):
        opened.append(url)
        return Window()

    monkeypatch.setattr(desktop, "open_window", fake_open)
    result: list[int] = []
    t = threading.Thread(target=lambda: result.append(desktop.run(cfg)), daemon=True)
    t.start()
    for _ in range(300):
        if opened:
            break
        time.sleep(0.1)
    assert opened, "uygulama açılmadı"
    ctx = browser.new_context(viewport={"width": 1400, "height": 1000}, locale="tr-TR")
    page = ctx.new_page()
    page.set_default_timeout(TIMEOUT_MS)
    try:
        page.goto(f"{opened[0]}/#/ayarlar")
        page.get_by_text("Gelişmiş", exact=True).click()
        page.get_by_label("Port").fill(str(new_port))
        page.locator("form.setting-row").get_by_role("button", name="Kaydet").click()
        page.get_by_role("button", name="Şimdi yeniden başlat").click()
        page.wait_for_url(f"http://127.0.0.1:{new_port}/#/ayarlar", timeout=30_000)
        expect(page.get_by_text(f"Şu an {new_port} portunda çalışıyor")).to_be_attached()
        assert len(opened) == 1  # yeni pencere açılmadı
    finally:
        ctx.close()
        closed.set()
        t.join(20)
    assert result == [0]


# --- büyük dosyalar (arkadaş denemesi) ----------------------------------------------------------

def test_too_large_upload_in_organizer_is_reported(server, page, tmp_path):
    """Düzenleyiciye sınırdan büyük dosya bırakınca hiçbir şey olmuyordu (hata gösterilmiyordu)."""
    base, app = server
    store = app.state.store
    old = store.max_bytes, store.max_upload_mb
    store.max_bytes, store.max_upload_mb = 10_000, 1
    try:
        page.goto(f"{base}/#/duzenle")
        pdf = fx.numbered(tmp_path / "b.pdf", 30, with_toc=False)
        page.locator("input[type=file]").first.set_input_files(str(pdf))
        page.get_by_role("alert").filter(has_text="Dosya çok büyük").wait_for()
        assert "#/duzenle" in page.url and "/duzenle/" not in page.url
    finally:
        store.max_bytes, store.max_upload_mb = old


def test_organizer_fetches_only_visible_pages(server, page, tmp_path):
    """pdf.js bütün dosyayı arka planda tarayıcıya çekiyordu (2 GB'lık dosyada 15 sn'de 578 MB,
    sürüyordu). Artık yalnızca çizilen sayfaların baytları aralık isteğiyle gelir ve ekran
    durunca indirme de durur."""
    base, app = server
    pages = 400
    pdf = fx.noisy_pages(tmp_path / "buyuk.pdf", pages=pages, size=(600, 450), label=False)
    meta = app.state.store.add_file(pdf, "buyuk.pdf", source="upload")
    got = {"bytes": 0}
    raw_ids: set[str] = set()
    # Ağ katmanından sayılır: akışla gelen ya da yarıda kesilen (bitmeyen) istekler de dahil.
    cdp = page.context.new_cdp_session(page)
    cdp.send("Network.enable")
    cdp.on("Network.requestWillBeSent",
           lambda e: raw_ids.add(e["requestId"]) if "/raw" in e["request"]["url"] else None)
    cdp.on("Network.dataReceived",
           lambda e: got.__setitem__("bytes", got["bytes"] + e["dataLength"])
           if e["requestId"] in raw_ids else None)

    page.set_viewport_size({"width": 600, "height": 400})
    page.goto(f"{base}/#/duzenle/{meta.id}")
    page.locator(".page-tile img").first.wait_for()
    # Görünen küçük resimler çizilip ağ 2 sn susana kadar bekle (CI yavaş olabilir). Eski
    # davranışta arka plan indirmesi dosyanın tamamı gelene kadar sürerdi.
    settled, quiet_since = -1, time.monotonic()
    deadline = time.monotonic() + 60
    while time.monotonic() < deadline:
        page.wait_for_timeout(250)
        if got["bytes"] != settled:
            settled, quiet_since = got["bytes"], time.monotonic()
        elif time.monotonic() - quiet_since > 2:
            break
    size = pdf.stat().st_size
    assert 0 < settled < size * 0.6, (settled, size)
    # Aşağı kaydırınca sonraki sayfalar yine çizilir.
    page.locator(".page-tile").nth(pages - 1).scroll_into_view_if_needed()
    page.locator(".page-tile").nth(pages - 1).locator("img").wait_for()
