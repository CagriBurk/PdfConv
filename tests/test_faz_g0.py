"""Faz G0 regresyon testleri: küçük resim ucu, 409 kilidi, yerinde yazma, hızlı yollar."""

from __future__ import annotations

import contextlib
import io
import json
import shutil
from pathlib import Path

import pymupdf
import pytest
from fastapi.testclient import TestClient
from PIL import Image
from pydantic import TypeAdapter

from pdfatolye import engines
from pdfatolye.api import app as app_module
from pdfatolye.convert import to_excel, to_word
from pdfatolye.core import compress, content, ocr, security
from pdfatolye.errors import PageRangeError
from pdfatolye.settings import Settings
from tests.fixtures import make_fixtures as fx

OPS = TypeAdapter(list[content.Op])


@pytest.fixture
def client(settings: Settings, monkeypatch: pytest.MonkeyPatch) -> TestClient:
    monkeypatch.setattr(engines, "detect_all", lambda _s: [])
    with TestClient(app_module.create_app(settings, start_background=False)) as c:
        assert c.get("/api/session").status_code == 200
        yield c


def _upload(client: TestClient, path: Path) -> dict:
    with path.open("rb") as f:
        r = client.post("/api/files", files=[("files", (path.name, f))])
    assert r.status_code == 200, r.text
    return r.json()[0]


def test_thumb_returns_valid_jpeg_and_clamps_width(client: TestClient, tmp_path: Path):
    meta = _upload(client, fx.numbered(tmp_path / "n.pdf", 2, with_toc=False))

    r = client.get(f"/api/files/{meta['id']}/thumb/0?w=200")
    assert r.status_code == 200
    assert r.headers["content-type"] == "image/jpeg"
    assert r.content.startswith(b"\xff\xd8\xff")
    with Image.open(io.BytesIO(r.content)) as im:
        assert im.format == "JPEG"
        assert im.width == 200

    r_small = client.get(f"/api/files/{meta['id']}/thumb/1?w=10")
    assert r_small.status_code == 200
    with Image.open(io.BytesIO(r_small.content)) as im:
        assert im.width == 100

    r_large = client.get(f"/api/files/{meta['id']}/thumb/0?w=2000")
    assert r_large.status_code == 200
    with Image.open(io.BytesIO(r_large.content)) as im:
        assert im.width == 600


def test_thumb_bounds_non_pdf_and_missing(client: TestClient, tmp_path: Path):
    pdf_meta = _upload(client, fx.numbered(tmp_path / "n.pdf", 2, with_toc=False))
    img_meta = _upload(client, fx.photo_jpeg(tmp_path / "foto.jpg"))

    assert client.get(f"/api/files/{pdf_meta['id']}/thumb/-1").status_code == 404
    assert client.get(f"/api/files/{pdf_meta['id']}/thumb/2").status_code == 404
    assert client.get(f"/api/files/{'0' * 32}/thumb/0").status_code == 404
    assert client.get(f"/api/files/{img_meta['id']}/thumb/0").status_code == 400


def test_thumb_encrypted_pdf_headers(client: TestClient, tmp_path: Path):
    plain = fx.numbered(tmp_path / "plain.pdf", 1, with_toc=False)
    enc = tmp_path / "enc.pdf"
    security.encrypt(plain, enc, user_password="gizli")
    meta = _upload(client, enc)

    assert client.get(f"/api/files/{meta['id']}/thumb/0").status_code == 401
    assert client.get(
        f"/api/files/{meta['id']}/thumb/0", headers={"x-pdf-password": "yanlis"}
    ).status_code == 403

    r = client.get(f"/api/files/{meta['id']}/thumb/0", headers={"x-pdf-password": "gizli"})
    assert r.status_code == 200
    assert r.content.startswith(b"\xff\xd8\xff")


def test_delete_returns_409_when_in_use(client: TestClient, tmp_path: Path):
    meta = _upload(client, fx.numbered(tmp_path / "busy.pdf", 1, with_toc=False))
    fid = meta["id"]
    store = client.app.state.store

    store.hold([fid])
    try:
        r_busy = client.delete(f"/api/files/{fid}")
        assert r_busy.status_code == 409
        assert client.get(f"/api/files/{fid}").status_code == 200
    finally:
        store.release([fid])

    r_ok = client.delete(f"/api/files/{fid}")
    assert r_ok.status_code == 200
    assert client.get(f"/api/files/{fid}").status_code == 404


def test_apply_ops_in_place_overwrite(tmp_path: Path):
    src = fx.numbered(tmp_path / "inplace.pdf", 1, with_toc=False)
    ops = OPS.validate_python(
        [{"type": "text", "page": 0, "rect": [50, 120, 350, 160], "text": "Yerinde yazim"}]
    )

    res = content.apply_ops(src, src, ops)
    assert res.output == src
    assert not list(tmp_path.glob(".tmp-content-*"))
    with pymupdf.open(src) as doc:
        text = doc[0].get_text()
        assert "Sayfa 1" in text
        assert "Yerinde yazim" in text


def test_image_share_uses_length_key_before_stream_raw(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    scan = fx.scanned(tmp_path / "scan.pdf")
    text_only = fx.numbered(tmp_path / "text.pdf", 2, with_toc=False)

    assert compress.image_share(text_only) == 0.0
    baseline = compress.image_share(scan)
    assert baseline is not None and 0.0 < baseline <= 1.0

    raw_calls = 0
    real_opened = compress.opened

    class _DocProxy:
        def __init__(self, doc, force_missing_length: bool):
            self._doc = doc
            self._force_missing_length = force_missing_length

        def xref_length(self):
            return self._doc.xref_length()

        def xref_get_key(self, xref: int, key: str):
            if self._force_missing_length and key == "Length":
                return ("null", "")
            return self._doc.xref_get_key(xref, key)

        def xref_stream_raw(self, xref: int):
            nonlocal raw_calls
            raw_calls += 1
            return self._doc.xref_stream_raw(xref)

    @contextlib.contextmanager
    def _proxy_opened(path: Path, password: str | None = None, *, force_missing: bool = False):
        with real_opened(path, password) as doc:
            yield _DocProxy(doc, force_missing)

    monkeypatch.setattr(
        compress, "opened", lambda p, pw=None: _proxy_opened(p, pw, force_missing=False)
    )
    fast_val = compress.image_share(scan)
    assert fast_val == baseline
    assert raw_calls == 0

    monkeypatch.setattr(
        compress, "opened", lambda p, pw=None: _proxy_opened(p, pw, force_missing=True)
    )
    fallback_val = compress.image_share(scan)
    assert fallback_val == baseline
    assert raw_calls > 0


def test_ocr_copies_result_with_copyfile(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    src = fx.numbered(tmp_path / "ocr_src.pdf", 1, with_toc=False)
    out = tmp_path / "ocr_out.pdf"
    copy_calls: list[tuple[Path, Path]] = []
    real_copyfile = shutil.copyfile

    class _FakeProc:
        def __init__(self):
            self.stderr = io.BytesIO(b"")

        def wait(self, timeout=None):
            return 0

    @contextlib.contextmanager
    def _fake_spawn(cmd, **_kwargs):
        args = json.loads(cmd[-1])
        real_copyfile(args["input"], args["output"])
        yield _FakeProc()

    def _spy_copyfile(s, d, *args, **kwargs):
        copy_calls.append((Path(s), Path(d)))
        return real_copyfile(s, d, *args, **kwargs)

    monkeypatch.setattr(ocr.proc, "spawn", _fake_spawn)
    monkeypatch.setattr(ocr.shutil, "copyfile", _spy_copyfile)

    res = ocr.ocr(src, out)
    assert res.output == out and out.is_file()
    assert res.page_count == 1 and res.pages_with_text == 1
    assert len(copy_calls) == 1
    with pymupdf.open(out) as doc:
        assert doc.page_count == 1


def test_to_word_and_to_excel_empty_range_guards(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    src = fx.numbered(tmp_path / "empty_range.pdf", 2, with_toc=False)

    with pytest.raises(PageRangeError):
        to_excel.pdf_to_excel(src, tmp_path / "out1.xlsx", spec=";")
    with pytest.raises(PageRangeError):
        to_word.pdf_to_word(src, tmp_path / "out1.docx", spec=";")

    monkeypatch.setattr(to_excel, "parse_ranges", lambda _spec, _n: [])
    with pytest.raises(PageRangeError):
        to_excel.pdf_to_excel(src, tmp_path / "out2.xlsx", spec="1")

    real_import = to_word._import_pdf2docx

    def _empty_pages_import():
        Converter, Document, Fonts, RawPageFactory = real_import()

        class _EmptyConverter(Converter):
            def load_pages(self, pages=None, start=0, end=None):
                self.pages.reset()

        return _EmptyConverter, Document, Fonts, RawPageFactory

    monkeypatch.setattr(to_word, "_import_pdf2docx", _empty_pages_import)
    with pytest.raises(PageRangeError):
        to_word.pdf_to_word(src, tmp_path / "out2.docx", spec="1")


def test_repair_in_place_overwrite(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    doc_path = fx.numbered(tmp_path / "onar.pdf", 2, with_toc=False)
    res_qpdf = security.repair(doc_path, doc_path)
    assert res_qpdf.output == doc_path

    # qpdf hata verirse MuPDF yedek yolu da yerinde yazarken WinError 5 vermemeli
    def _fail_pikepdf(*_args, **_kwargs):
        raise OSError("simule qpdf hatasi")

    monkeypatch.setattr(security.pikepdf, "open", _fail_pikepdf)
    res_mupdf = security.repair(doc_path, doc_path)
    assert res_mupdf.output == doc_path
    with pymupdf.open(doc_path) as pdf:
        assert pdf.page_count == 2
