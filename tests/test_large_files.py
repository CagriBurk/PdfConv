"""Arkadaş denemesinden gelenler: büyük dosya sınırı, sıkıştırmada ilerleme ve süre, metin
ağırlıklı PDF'te az kazanç."""

from __future__ import annotations

import sys
import threading
import time
from pathlib import Path

import psutil
import pymupdf
import pytest
from fastapi.testclient import TestClient

from pdfatolye import engines, proc
from pdfatolye.api import app as app_module
from pdfatolye.core import compress
from pdfatolye.settings import Settings
from pdfatolye.storage import FileStore, UploadTooLargeError
from tests.fixtures import make_fixtures as fx

GHOSTSCRIPT = engines.detect_ghostscript(Settings())


def test_default_limits_allow_8_gb_files():
    s = Settings()
    assert s.max_upload_mb == 8192 and s.max_request_mb >= 2 * 8192
    assert "8 GB" in str(UploadTooLargeError(8192))


def test_text_pdf_fonts_are_subset_losslessly(tmp_path: Path):
    """Yazı tipi tam gömülü metin PDF'i kayıpsızda yalnızca ~%20 küçülüyordu."""
    src = fx.text_full_font(tmp_path / "metin.pdf")
    r = compress.compress(src, tmp_path / "o.pdf", "kayipsiz")
    assert r.after < r.before * 0.5, (r.before, r.after)
    with pymupdf.open(src) as a, pymupdf.open(r.output) as b:
        assert [p.get_text() for p in a] == [p.get_text() for p in b]


def test_ghostscript_skipped_when_images_already_shrunk(tmp_path: Path, monkeypatch):
    """Resim ağırlıklı dosyada Ghostscript dakikalar sürüp birkaç yüzde kazandırıyordu."""
    calls = []
    monkeypatch.setattr(compress, "_ghostscript", lambda *a, **k: calls.append(a) or False)
    src = fx.scanned_turkish(tmp_path / "s.pdf", pages=2, dpi=300, noise=True)
    r = compress.compress(src, tmp_path / "o.pdf", "guclu", ghostscript="gs.exe")
    assert r.after < r.before * compress.GS_WORTH_RATIO and calls == []
    # PyMuPDF'in küçültemediği dosyada Ghostscript yine denenir: düşük çözünürlüklü (eşiğin
    # altında, dokunulmaz) sıkıştırılamayan resimler.
    vec = fx.noisy_pages(tmp_path / "dusuk.pdf", pages=3, size=(300, 200), label=False)
    compress.compress(vec, tmp_path / "o2.pdf", "guclu", ghostscript="gs.exe")
    assert len(calls) == 1


def test_compress_reports_progress(tmp_path: Path):
    src = fx.scanned_turkish(tmp_path / "s.pdf", pages=1, dpi=200)
    seen: list[tuple[float, str]] = []
    compress.compress(src, tmp_path / "o.pdf", "dengeli", report=lambda f, m: seen.append((f, m)))
    assert any("Resimler" in m for _, m in seen) and any("Kaydediliyor" in m for _, m in seen)
    fractions = [f for f, _ in seen]
    assert fractions == sorted(fractions) and all(0 <= f <= 1 for f in fractions)


@pytest.mark.skipif(not GHOSTSCRIPT.available, reason="Ghostscript yok")
def test_ghostscript_progress_per_page(tmp_path: Path):
    src = fx.numbered(tmp_path / "n.pdf", 4, with_toc=False)
    seen: list[str] = []
    assert compress._ghostscript(GHOSTSCRIPT.path, src, tmp_path / "gs.pdf",
                                 lambda f, m: seen.append(m))
    assert seen[-1] == "Ghostscript ile ek deneme: sayfa 4/4", seen


def test_run_lines_streams_output_and_can_be_cancelled():
    code = ("import sys, time\n"
            "for i in range(3): print(f'Page {i + 1}', flush=True); time.sleep(0.05)\n"
            "time.sleep(60)\n")
    lines: list[str] = []
    cancel = threading.Event()
    started = time.monotonic()

    def on_line(line: str) -> None:
        lines.append(line)
        if line == "Page 3":
            cancel.set()

    with pytest.raises(proc.Cancelled):
        proc.run_lines([sys.executable, "-c", code], timeout=30, on_line=on_line,
                       should_cancel=cancel.is_set)
    assert lines == ["Page 1", "Page 2", "Page 3"] and time.monotonic() - started < 10
    for p in psutil.process_iter(["cmdline"]):  # süreç öksüz kalmadı
        assert "time.sleep(60)" not in " ".join(p.info["cmdline"] or [])


def test_run_lines_returns_code_and_tail():
    script = "print('a'); print('b'); raise SystemExit(3)"
    code, tail = proc.run_lines([sys.executable, "-c", script], timeout=30,
                                on_line=lambda _l: None)
    assert code == 3 and tail.splitlines() == ["a", "b"]


def _client(tmp_path: Path) -> TestClient:
    s = Settings(data_dir=tmp_path / "veri", allowed_hosts=["127.0.0.1", "localhost", "testserver"])
    c = TestClient(app_module.create_app(s, start_background=False), client=("127.0.0.1", 5000))
    c.get("/api/session")
    return c


def test_compress_job_explains_small_gain_on_text_pdfs(tmp_path: Path):
    """"%10 küçüldü" sonucu neden az olduğunu söylemeli (arkadaş denemesi, madde 4)."""
    src = tmp_path / "zaten-kucuk.pdf"
    doc = pymupdf.open()
    for i in range(3):
        doc.new_page().insert_text((72, 72), f"Sayfa {i + 1} rapor metni", fontsize=12)
    doc.save(src, garbage=4, deflate=True, use_objstms=1)
    with _client(tmp_path) as c:
        meta = c.app.state.store.add_file(src, "rapor.pdf", source="upload")
        r = c.post("/api/jobs", json={"type": "compress", "files": [meta.id], "level": "guclu"})
        job = c.app.state.jobs.wait(r.json()["id"], 60)
    assert job.status == "bitti", job.error
    assert any("%0'i resim" in w and "büyük kazanç beklenmez" in w for w in job.warnings), \
        job.warnings


def test_store_streams_big_upload_without_memory(tmp_path: Path):
    """Sınır akışla denetlenir: yükleme belleğe alınmaz, sınırı aşan yarım dosya silinir."""
    import io

    class Endless(io.RawIOBase):
        def __init__(self, n: int) -> None:
            self.left = n

        def readable(self) -> bool:
            return True

        def readinto(self, b) -> int:
            k = min(len(b), self.left)
            b[:k] = b"\0" * k
            self.left -= k
            return k

    store = FileStore(tmp_path / "files", max_upload_mb=3)
    with pytest.raises(UploadTooLargeError):
        store.add_stream(io.BufferedReader(Endless(50 * 1024 * 1024)), "buyuk.pdf")
    assert not any((tmp_path / "files").iterdir())
