import io
import os
import time

import pytest

from pdfatolye.errors import PdfAtolyeError
from pdfatolye.storage import FileNotInStoreError, FileStore, UploadTooLargeError
from tests.fixtures import make_fixtures as fx


@pytest.fixture
def store(tmp_path):
    # Fixture PDF'leri Arial'ı tam gömdüğü için ~1 MB; sınır bunun üstünde olmalı.
    return FileStore(tmp_path / "files", max_upload_mb=5)


def test_upload_detects_pdf_facts(store, tmp_path):
    pdf = fx.numbered(tmp_path / "a.pdf", 3)
    meta = store.add_stream(pdf.open("rb"), "Ödev 1.pdf")
    assert (meta.name, meta.kind, meta.source) == ("Ödev 1.pdf", "pdf", "upload")
    assert meta.current.page_count == 3 and not meta.encrypted
    assert store.path(meta.id).read_bytes() == pdf.read_bytes()


def test_encrypted_upload(store, tmp_path):
    pdf = fx.numbered(tmp_path / "s.pdf", 2, password="x")
    meta = store.add_stream(pdf.open("rb"), "s.pdf")
    assert meta.encrypted and meta.current.page_count is None


def test_versions_and_undo(store, tmp_path):
    a = fx.numbered(tmp_path / "a.pdf", 3)
    b = fx.numbered(tmp_path / "b.pdf", 1)
    meta = store.add_stream(a.open("rb"), "a.pdf")
    meta = store.new_version(meta.id, b, "Sayfa düzenleme")
    assert [v.n for v in meta.versions] == [1, 2]
    assert meta.current.page_count == 1
    assert store.path(meta.id, 1).read_bytes() == a.read_bytes()
    meta = store.undo(meta.id)
    assert meta.current.n == 1 and meta.current.page_count == 3
    with pytest.raises(PdfAtolyeError, match="Geri alınacak"):
        store.undo(meta.id)


def test_upload_limit_removes_partial_file(store):
    with pytest.raises(UploadTooLargeError, match="5 MB"):
        store.add_stream(io.BytesIO(b"x" * (6 * 1024 * 1024)), "buyuk.pdf")
    assert store.list() == []
    assert list(store.root.iterdir()) == []


def test_bad_ids_are_rejected(store):
    for bad in ("../x", "", "ABC", "a" * 31 + "/"):
        with pytest.raises(FileNotInStoreError):
            store.get(bad)


def test_names_are_sanitized_and_kind_detected(store):
    meta = store.add_stream(io.BytesIO(b"# x"), "..\\..\\kötü:ad?.md")
    assert meta.name == "kötü_ad_.md" and meta.kind == "markdown"
    meta = store.rename(meta.id, "yeni ad.txt")
    assert meta.name == "yeni ad.md"  # uzantı korunur


def test_cleanup_respects_pin(store, tmp_path):
    old = store.add_stream(io.BytesIO(b"a"), "eski.txt")
    pinned = store.add_stream(io.BytesIO(b"b"), "sabit.txt")
    new = store.add_stream(io.BytesIO(b"c"), "yeni.txt")
    store.set_pinned(pinned.id, True)
    for m in (old, pinned):
        meta = store.get(m.id)
        meta.versions[-1].created = time.time() - 48 * 3600
        store._save_meta(meta)
    (store.root / ("0" * 32)).mkdir()  # meta'sız artık klasör
    os.utime(store.root / ("0" * 32), (0, 0))
    assert store.cleanup(24) == 1
    assert {m.id for m in store.list()} == {pinned.id, new.id}
    assert not (store.root / ("0" * 32)).exists()
