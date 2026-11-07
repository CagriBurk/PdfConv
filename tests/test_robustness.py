"""Faz B: sağlamlık. Her test, denetimde çalıştırılarak bulunmuş bir hatanın geri gelmemesi
içindir: uzun ad, bozuk kayıt, iş kayıtları, sayfa düzenlemede bilgi kaybı, dosya türleri,
iptal ve kuyruk, temizlik yarışı, Windows-1254 notlar, takılan HTML, istek boyutu."""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import threading
import time
from pathlib import Path

import psutil
import pymupdf
import pytest
from fastapi.testclient import TestClient
from PIL import Image

from pdfatolye import engines, proc
from pdfatolye.api import app as app_module
from pdfatolye.api import limits
from pdfatolye.core import images, pages
from pdfatolye.core.pdfio import safe_name_with_ext, split_ext
from pdfatolye.core.textio import decode_text
from pdfatolye.errors import ImageTooLargeError, PdfAtolyeError
from pdfatolye.formats import KINDS
from pdfatolye.jobs import manager as manager_module
from pdfatolye.jobs import workers
from pdfatolye.settings import PROJECT_ROOT, Settings
from pdfatolye.storage import FileStore
from tests.fixtures import make_fixtures as fx

BROWSER = engines.detect_browser(Settings()).path
needs_browser = pytest.mark.skipif(not BROWSER, reason="Edge/Chrome yok")
TURKISH_NOTE = "# Çalışma notu\n\nığdır şöyle: ĞÜŞİÖÇ ğüşiöç\n"


@pytest.fixture
def client(settings: Settings, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(engines, "detect_all", lambda _s: [])
    with TestClient(app_module.create_app(settings, start_background=False)) as c:
        assert c.get("/api/session").status_code == 200
        yield c


def upload(client: TestClient, path: Path | bytes, name: str) -> dict:
    data = path if isinstance(path, bytes) else path.read_bytes()
    r = client.post("/api/files", files=[("files", (name, data))])
    assert r.status_code == 200, r.text
    return r.json()[0]


def run_job(client: TestClient, payload: dict, timeout: float = 120) -> dict:
    r = client.post("/api/jobs", json=payload)
    assert r.status_code == 200, r.text
    client.app.state.jobs.wait(r.json()["id"], timeout=timeout)
    return client.get(f"/api/jobs/{r.json()['id']}").json()


def wait_until(cond, timeout: float = 10, step: float = 0.05) -> bool:
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        if cond():
            return True
        time.sleep(step)
    return cond()


# --- 1. uzun dosya adı -------------------------------------------------------------------------


def test_long_upload_name_keeps_extension(client, tmp_path):
    name = "Çok uzun bir ders notu adı " * 5 + ".pdf"  # ~135 karakter
    meta = upload(client, fx.numbered(tmp_path / "a.pdf", 2, with_toc=False), name)
    assert meta["kind"] == "pdf"
    assert meta["name"].endswith(".pdf") and len(meta["name"]) <= 84
    job = run_job(client, {"type": "compose", "items": [{"file": meta["id"], "page": 1}]})
    assert job["status"] == "bitti", job["error"]
    assert job["files"][0]["name"].endswith("_duzenlenmis.pdf")


@pytest.mark.parametrize(("name", "expected"), [
    ("a" * 100 + ".PDF", "a" * 80 + ".PDF"),
    ("CON.pdf", "dosya.pdf"),
    ("Sürüm 1.2 son", "Sürüm 1.2 son"),  # ".2 son" uzantı değil
    ("rapor.pdf. ", "rapor.pdf"),
    ("..pdf", "pdf"),
])
def test_safe_name_with_ext(name, expected):
    assert safe_name_with_ext(name) == expected


def test_split_ext():
    assert split_ext("not.tar.gz") == ("not.tar", ".gz")
    assert split_ext("v1.2 final") == ("v1.2 final", "")


def test_rename_and_output_names_keep_dots(client, tmp_path):
    meta = upload(client, fx.numbered(tmp_path / "a.pdf", 1, with_toc=False), "a.pdf")
    r = client.post(f"/api/files/{meta['id']}/rename", json={"name": "Sürüm 1.2 son"})
    assert r.json()["name"] == "Sürüm 1.2 son.pdf"
    r = client.post(f"/api/files/{meta['id']}/rename", json={"name": "Yeni.PDF"})
    assert r.json()["name"] == "Yeni.pdf"
    other = upload(client, fx.numbered(tmp_path / "b.pdf", 1, with_toc=False), "b.pdf")
    job = run_job(client, {"type": "merge", "files": [meta["id"], other["id"]],
                           "name": "Rapor v1.2"})
    assert job["files"][0]["name"] == "Rapor v1.2.pdf"


# --- 4. bozuk meta.json ------------------------------------------------------------------------


@pytest.mark.parametrize("garbage", ["{yarım", '{"id": "x"}', '{"versions": []}', "[]"])
def test_corrupt_meta_is_skipped_and_logged(client, tmp_path, garbage):
    good = upload(client, fx.numbered(tmp_path / "a.pdf", 1, with_toc=False), "iyi.pdf")
    bad = upload(client, fx.numbered(tmp_path / "b.pdf", 1, with_toc=False), "bozuk.pdf")
    store = client.app.state.store
    (store.root / bad["id"] / "meta.json").write_text(garbage, encoding="utf-8")
    r = client.get("/api/files")
    assert r.status_code == 200
    assert [f["id"] for f in r.json()] == [good["id"]]
    assert client.get(f"/api/files/{bad['id']}").status_code == 404
    assert store.cleanup(0) == 1  # iyi dosya silinir, bozuk kayıt patlatmaz ve kalır
    assert (store.root / bad["id"]).is_dir()
    log = (client.app.state.settings.logs_dir / "pdfatolye.log").read_text(encoding="utf-8")
    assert "Bozuk dosya kaydı atlandı" in log and bad["id"] in log


def test_meta_has_schema_and_ignores_unknown_fields(tmp_path):
    store = FileStore(tmp_path / "files")
    meta = store.add_file(fx.numbered(tmp_path / "a.pdf", 1, with_toc=False), "a.pdf")
    path = store.root / meta.id / "meta.json"
    raw = json.loads(path.read_text(encoding="utf-8"))
    assert raw["schema"] == 1
    raw["gelecekte_eklenen_alan"] = True  # daha yeni bir sürüm yazmış olabilir
    raw["versions"][0]["yeni"] = 1
    path.write_text(json.dumps(raw), encoding="utf-8")
    assert store.get(meta.id).name == "a.pdf"


# --- 5. iş kayıtları ---------------------------------------------------------------------------


def test_md_text_not_in_job_record_or_responses(client, monkeypatch):
    seen = {}

    def fake_md(store, settings, req, report, tmp, job_id):
        seen["text"] = req.text  # çalışan metni yine alır
        return workers.WorkResult([])

    monkeypatch.setattr(workers, "md_to_pdf", fake_md)
    secret = "GIZLINOTMETNI " * 2000
    job = run_job(client, {"type": "md_to_pdf", "text": secret, "name": "n.md"})
    assert job["status"] == "bitti" and seen["text"] == secret
    record = (client.app.state.settings.jobs_dir / f"{job['id']}.json").read_text("utf-8")
    assert "GIZLINOTMETNI" not in record
    assert "GIZLINOTMETNI" not in client.get("/api/jobs").text
    assert "GIZLINOTMETNI" not in json.dumps(job)


def test_job_responses_drop_large_request_fields(client, tmp_path):
    meta = upload(client, fx.numbered(tmp_path / "a.pdf", 3, with_toc=False), "a.pdf")
    items = [{"file": meta["id"], "page": p % 3} for p in range(300)]
    job = run_job(client, {"type": "compose", "items": items})
    assert job["status"] == "bitti"
    assert "items" not in job["request"] and job["request"]["type"] == "compose"
    single = run_job(client, {"type": "repair", "file": meta["id"]})
    assert single["request"]["file"] == meta["id"]  # arayüz "Onarmayı dene" için kullanır


def test_old_job_records_are_deleted(client):
    jobs = client.app.state.jobs
    old = manager_module.Job(id="a" * 32, type="merge", status="bitti", created=1.0,
                             request={}, finished=2.0)
    jobs._jobs[old.id] = old
    jobs._persist(old)
    assert (jobs.dir / f"{old.id}.json").is_file()
    assert jobs.cleanup(24) == 1
    assert not (jobs.dir / f"{old.id}.json").exists()
    assert old.id not in {j.id for j in jobs.list(500)}


def test_job_records_on_disk_are_bounded(settings, tmp_path, monkeypatch):
    monkeypatch.setattr(manager_module, "KEEP_JOBS", 5)
    settings.jobs_dir.mkdir(parents=True)
    for i in range(12):
        job = manager_module.Job(id=f"{i:032x}", type="merge", status="bitti", created=i,
                                 request={}, finished=time.time())
        (settings.jobs_dir / f"{job.id}.json").write_text(json.dumps(job.to_dict()), "utf-8")
        os.utime(settings.jobs_dir / f"{job.id}.json", (i + 1, i + 1))
    m = manager_module.JobManager(FileStore(settings.files_dir), settings)
    try:
        assert len(list(settings.jobs_dir.glob("*.json"))) == 5
        assert len(m.list(500)) == 5
    finally:
        m.shutdown()


def test_jobs_limit_is_bounded(client):
    for bad in (-1, 0, 100_000):
        assert client.get(f"/api/jobs?limit={bad}").status_code == 422
    assert client.get("/api/jobs?limit=5").status_code == 200


# --- 6. sayfa düzenleme belge bilgisini korur --------------------------------------------------


def _rich_pdf(path: Path, title: str = "Tez Taslağı", n: int = 5) -> Path:
    doc = pymupdf.open()
    for i in range(n):
        doc.new_page().insert_text((72, 72), f"Sayfa {i + 1}")
    doc.set_metadata({"title": title, "author": "Çağrı Yazar", "subject": "Konu",
                      "keywords": "anahtar"})
    doc.set_page_labels([{"startpage": 0, "prefix": "", "style": "r", "firstpagenum": 1},
                         {"startpage": 2, "prefix": "", "style": "D", "firstpagenum": 1}])
    doc.embfile_add("veri.csv", b"a;b\n1;2\n", filename="veri.csv", desc="ek tablo")
    doc.save(path)
    doc.close()
    return path


def test_compose_keeps_info_labels_and_attachments(tmp_path):
    src = _rich_pdf(tmp_path / "t.pdf")  # etiketler: i ii 1 2 3
    out = tmp_path / "o.pdf"
    # 3. sayfa (etiket "1") silindi, son iki sayfa yer değiştirdi, araya boş sayfa
    pages.compose([src], [pages.PageRef(0, 0), pages.PageRef(0, 1), pages.PageRef(0, 4),
                          pages.BlankPage(), pages.PageRef(0, 3)], out)
    with pymupdf.open(out) as doc:
        assert doc.metadata["title"] == "Tez Taslağı"
        assert doc.metadata["author"] == "Çağrı Yazar"
        assert doc.metadata["keywords"] == "anahtar"
        assert [p.get_label() for p in doc] == ["i", "ii", "3", "4", "2"]
        assert doc.embfile_names() == ["veri.csv"]
        assert doc.embfile_get("veri.csv") == b"a;b\n1;2\n"


def test_identity_compose_keeps_labels_exactly(tmp_path):
    src = _rich_pdf(tmp_path / "t.pdf")
    out = pages.rotate(src, 90, tmp_path / "r.pdf", spec="1")
    with pymupdf.open(out) as doc:
        assert [p.get_label() for p in doc] == ["i", "ii", "1", "2", "3"]


def test_merge_takes_first_files_info_and_all_attachments(tmp_path):
    a = _rich_pdf(tmp_path / "a.pdf", "Birinci", n=3)
    b = _rich_pdf(tmp_path / "b.pdf", "İkinci", n=2)
    out = pages.merge([a, b], tmp_path / "m.pdf")
    with pymupdf.open(out) as doc:
        assert doc.metadata["title"] == "Birinci"
        assert sorted(doc.embfile_names()) == ["veri.csv", "veri.csv (2)"]
        assert [p.get_label() for p in doc] == ["i", "ii", "1", "i", "ii"]


def test_compose_without_labels_adds_none(tmp_path):
    src = fx.numbered(tmp_path / "n.pdf", 3, with_toc=False)
    out = pages.compose([src], [pages.PageRef(0, 2), pages.PageRef(0, 0)], tmp_path / "o.pdf")
    with pymupdf.open(out) as doc:
        assert doc.get_page_labels() == []


# --- 7. dosya türleri tek kaynaktan ------------------------------------------------------------


def _accept_lists() -> dict[str, list[str]]:
    src = (PROJECT_ROOT / "web" / "src" / "tools.ts").read_text(encoding="utf-8")
    block = src[src.index("export const ACCEPT"):]
    block = block[:block.index("};")]
    return {k: [e for e in v.split(",") if e.startswith(".")]
            for k, v in re.findall(r"(\w+): \"([^\"]+)\"", block)}


def test_ui_accept_lists_match_store_kinds():
    expected = {"pdf": {"pdf"}, "images": {"image"}, "markdown": {"markdown", "text"},
                "office": {"office", "html", "text"}}
    lists = _accept_lists()
    assert set(lists) == set(expected)
    for key, exts in lists.items():
        for ext in exts:
            assert KINDS.get(ext) in expected[key], f"ACCEPT.{key}: {ext} → {KINDS.get(ext)}"
    from pdfatolye.formats import OFFICE_EXTS
    assert set(lists["office"]) >= OFFICE_EXTS, "arayüz bir Office türünü kabul etmiyor"


@pytest.mark.parametrize("name", ["tablo.csv", "makro.docm", "hesap.xlsm", "sunum.pptm"])
def test_csv_and_macro_office_files_are_office(client, monkeypatch, name):
    monkeypatch.setattr(engines, "detect_libreoffice", lambda _s: engines.EngineStatus(
        key="libreoffice", name="LibreOffice", available=False, needed_for=""))
    meta = upload(client, b"a;b\n1;2\n", name)
    assert meta["kind"] == "office"
    # İş türü denetiminden geçer; LibreOffice yoksa motor hatası gelir, tür hatası değil.
    job = run_job(client, {"type": "office_to_pdf", "files": [meta["id"]]})
    assert "dosyası değil" not in (job["error"] or "")


# --- 8. iptal ve kuyruk ------------------------------------------------------------------------

SLEEPER = [sys.executable, "-c", "import time; time.sleep(60)"]


def _sleepers() -> list[int]:
    """Bu testlerin açtığı `time.sleep(60)` süreçleri (başka alt süreçler karışmasın)."""
    out = []
    for p in psutil.Process().children(recursive=True):
        try:
            if "time.sleep(60)" in " ".join(p.cmdline()):
                out.append(p.pid)
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue
    return out


def _alive(pid: int) -> bool:
    try:
        return psutil.Process(pid).status() != psutil.STATUS_ZOMBIE
    except psutil.NoSuchProcess:
        return False


def test_proc_run_cancel_kills_tree():
    flag = threading.Event()
    pids: list[int] = []
    # Çocuk süreç bir torun açar: ağaç öldürülmeli.
    code = ("import subprocess, sys, time; "
            "p = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(60)']); "
            "print(p.pid, flush=True); time.sleep(60)")

    def cancel_soon():
        time.sleep(1.5)
        pids.extend(_sleepers())
        flag.set()

    threading.Thread(target=cancel_soon, daemon=True).start()
    start = time.monotonic()
    with pytest.raises(proc.Cancelled):
        proc.run([sys.executable, "-c", code], timeout=60, should_cancel=flag.is_set)
    assert time.monotonic() - start < 10
    assert pids and wait_until(lambda: not any(_alive(p) for p in pids), 5)


def test_proc_run_timeout():
    with pytest.raises(proc.TimedOut):
        proc.run(SLEEPER, timeout=0.5)


def test_running_subprocess_job_is_really_cancelled(client, tmp_path, monkeypatch):
    started = {}

    def slow_compress(store, settings, req, report, tmp, job_id):
        def remember():  # proc.run içindeki süreci yakala
            for pid in _sleepers():
                started.setdefault("pid", pid)
        threading.Timer(0.5, remember).start()
        proc.run(SLEEPER, timeout=120)
        return workers.WorkResult([])

    monkeypatch.setattr(workers, "compress", slow_compress)
    meta = upload(client, fx.numbered(tmp_path / "a.pdf", 1, with_toc=False), "a.pdf")
    r = client.post("/api/jobs", json={"type": "compress", "files": [meta["id"]]})
    job_id = r.json()["id"]
    assert wait_until(lambda: "pid" in started, 10)
    t0 = time.monotonic()
    client.post(f"/api/jobs/{job_id}/cancel")
    job = client.app.state.jobs.wait(job_id, timeout=15)
    assert job.status == "iptal" and time.monotonic() - t0 < 5
    assert wait_until(lambda: not _alive(started["pid"]), 5)


def test_compose_is_cancelled_mid_way(client, tmp_path, monkeypatch):
    """Sayfa düzenleme de iptal edilebilir: her parçadan sonra bayrak denetlenir."""
    meta = upload(client, fx.numbered(tmp_path / "a.pdf", 3, with_toc=False), "a.pdf")
    real = pages.compose
    gate, inside = threading.Event(), threading.Event()
    finished = []

    def slow_compose(*a, on_progress=None, **kw):
        def progress(f):
            inside.set()  # compose ilk parçayı yazdı, ilerleme bildiriyor
            gate.wait(10)
            on_progress(f)
        out = real(*a, on_progress=progress, **kw)
        finished.append(True)  # iptal ortada etkili olduysa buraya gelinmez
        return out

    monkeypatch.setattr(pages, "compose", slow_compose)
    items = [{"file": meta["id"], "page": p % 3, "rotate": 90 * (p % 2)} for p in range(6)]
    r = client.post("/api/jobs", json={"type": "compose", "items": items})
    job_id = r.json()["id"]
    # İptal compose'un İÇİNDEyken gelmeli (öncesindeki `report` zaten iptal ederdi).
    assert inside.wait(10), "compose ilerleme bildirmiyor: iptal ortada denetlenemez"
    client.post(f"/api/jobs/{job_id}/cancel")
    gate.set()
    job = client.app.state.jobs.wait(job_id, timeout=15)
    assert job.status == "iptal" and job.outputs == [] and not finished


def test_limited_types_do_not_block_simple_jobs(client, tmp_path, monkeypatch):
    gate = threading.Event()

    def blocked_ocr(store, settings, req, report, tmp, job_id):
        gate.wait(30)
        return workers.WorkResult([])

    monkeypatch.setattr(workers, "ocr", blocked_ocr)
    meta = upload(client, fx.numbered(tmp_path / "a.pdf", 2, with_toc=False), "a.pdf")
    try:
        ocr_jobs = [client.post("/api/jobs", json={"type": "ocr", "file": meta["id"]}).json()
                    for _ in range(5)]
        t0 = time.monotonic()
        job = run_job(client, {"type": "merge", "files": [meta["id"], meta["id"]]}, timeout=20)
        assert job["status"] == "bitti" and time.monotonic() - t0 < 10
        # Sırada bekleyen OCR işi iptal edilince hemen "iptal" olur.
        last = ocr_jobs[-1]["id"]
        assert client.post(f"/api/jobs/{last}/cancel").json()["status"] == "iptal"
    finally:
        gate.set()


def test_shutdown_kills_child_processes(settings):
    m = manager_module.JobManager(FileStore(settings.files_dir), settings)
    pids: list[int] = []

    def worker():
        with proc.spawn(SLEEPER) as child:
            pids.append(child.pid)
            child.wait()

    t = threading.Thread(target=worker, daemon=True)
    t.start()
    assert wait_until(lambda: pids and _alive(pids[0]))
    m.shutdown()
    assert wait_until(lambda: not _alive(pids[0]), 10)


def test_ocr_exit_wait_timeout_is_friendly(monkeypatch):
    from pdfatolye.core import ocr

    class Stuck:
        stderr = iter([])  # çıktı bitti ama süreç kapanmıyor

        def wait(self, timeout=None):
            raise subprocess.TimeoutExpired("ocr", timeout)

    with pytest.raises(ocr.OcrError, match="kapanmadı"):
        ocr._follow(Stuck(), 1, lambda f, m: None, lambda: False)


# --- 9. temizlik yarışı ------------------------------------------------------------------------


def _age(store: FileStore, file_id: str, hours: float) -> None:
    path = store.root / file_id / "meta.json"
    raw = json.loads(path.read_text(encoding="utf-8"))
    for v in raw["versions"]:
        v["created"] -= hours * 3600
    raw["created"] -= hours * 3600
    path.write_text(json.dumps(raw), encoding="utf-8")


def test_cleanup_spares_files_in_use_and_recently_opened(client, tmp_path, monkeypatch):
    store = client.app.state.store
    ids = [upload(client, fx.numbered(tmp_path / f"{i}.pdf", 1, with_toc=False),
                  f"{i}.pdf")["id"] for i in range(3)]
    for i in ids:
        _age(store, i, 48)
    busy, opened, stale = ids
    gate = threading.Event()

    def blocked(store_, settings, req, report, tmp, job_id):
        gate.wait(30)
        return workers.WorkResult([])

    monkeypatch.setattr(workers, "repair", blocked)
    job = client.post("/api/jobs", json={"type": "repair", "file": busy}).json()
    client.get(f"/api/files/{opened}")  # arayüzde açık (editör yoklar)
    try:
        assert store.cleanup(24) == 1
        assert {m.id for m in store.list()} == {busy, opened}
    finally:
        gate.set()
    client.app.state.jobs.wait(job["id"], 10)
    assert not store.in_use(busy)


def test_cleanup_spares_queued_job_inputs(client, tmp_path, monkeypatch):
    store = client.app.state.store
    gate = threading.Event()
    monkeypatch.setattr(workers, "ocr", lambda *a: (gate.wait(30), workers.WorkResult([]))[1])
    a = upload(client, fx.numbered(tmp_path / "a.pdf", 1, with_toc=False), "a.pdf")["id"]
    b = upload(client, fx.numbered(tmp_path / "b.pdf", 1, with_toc=False), "b.pdf")["id"]
    try:
        client.post("/api/jobs", json={"type": "ocr", "file": a})
        client.post("/api/jobs", json={"type": "ocr", "file": b})  # sırada bekliyor
        _age(store, a, 48)
        _age(store, b, 48)
        store._accessed.clear()
        assert store.cleanup(24) == 0
    finally:
        gate.set()


# --- 10. Windows-1254 notlar -------------------------------------------------------------------


def test_decode_text_variants():
    assert decode_text(TURKISH_NOTE.encode("utf-8")) == (TURKISH_NOTE, None)
    assert decode_text(TURKISH_NOTE.encode("utf-8-sig"))[0] == TURKISH_NOTE
    assert decode_text(TURKISH_NOTE.encode("utf-16"))[0] == TURKISH_NOTE
    text, note = decode_text(TURKISH_NOTE.encode("cp1254"), "eski.md")
    assert text == TURKISH_NOTE and "Windows-1254" in note


def test_text_endpoint_decodes_cp1254(client):
    meta = upload(client, TURKISH_NOTE.replace("\n", "\r\n").encode("cp1254"), "eski.md")
    body = client.get(f"/api/files/{meta['id']}/text").json()
    assert body["text"] == TURKISH_NOTE
    assert "Windows-1254" in body["note"]
    pdf = upload(client, b"%PDF-1.4", "x.pdf")
    assert client.get(f"/api/files/{pdf['id']}/text").status_code == 400


@needs_browser
def test_md_job_from_cp1254_file(client):
    meta = upload(client, TURKISH_NOTE.encode("cp1254"), "eski.md")
    job = run_job(client, {"type": "md_to_pdf", "file": meta["id"]})
    assert job["status"] == "bitti", job["error"]
    assert any("Windows-1254" in w for w in job["warnings"])
    with pymupdf.open(client.app.state.store.path(job["outputs"][0])) as doc:
        assert "ğüşiöç" in doc[0].get_text()


# --- 11. takılan HTML --------------------------------------------------------------------------

LOOP_HTML = ("<!doctype html><meta charset=utf-8><p>Döngü</p>"
             "<script>addEventListener('load', () => setTimeout(() => { for (;;) {} }, 0));"
             "</script>")


def _marked_browsers() -> list[int]:
    from pdfatolye.convert.browser import MARKER_FLAG

    out = []
    for p in psutil.process_iter(["cmdline"]):
        try:
            if MARKER_FLAG in " ".join(p.info["cmdline"] or []):
                out.append(p.pid)
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue
    return out


@needs_browser
def test_infinite_loop_html_times_out(tmp_path, monkeypatch):
    from pdfatolye.convert import html

    monkeypatch.setattr(html, "PRINT_TIMEOUT_S", 6)
    src = tmp_path / "dongu.html"
    src.write_text(LOOP_HTML, encoding="utf-8")
    t0 = time.monotonic()
    with pytest.raises(PdfAtolyeError, match="basılamadı"):
        html.print_html(src, tmp_path / "o.pdf", browser_path=BROWSER, confine=True)
    assert time.monotonic() - t0 < 40
    assert wait_until(lambda: not _marked_browsers(), 10), "başsız tarayıcı arkada kaldı"


@needs_browser
def test_html_print_job_cancel_kills_browser(client, monkeypatch):
    from pdfatolye.convert import html

    monkeypatch.setattr(html, "PRINT_TIMEOUT_S", 120)
    meta = upload(client, LOOP_HTML.encode("utf-8"), "dongu.html")
    r = client.post("/api/jobs", json={"type": "office_to_pdf", "files": [meta["id"]]})
    job_id = r.json()["id"]
    assert wait_until(lambda: bool(_marked_browsers()), 30)
    time.sleep(1)
    client.post(f"/api/jobs/{job_id}/cancel")
    job = client.app.state.jobs.wait(job_id, timeout=20)
    assert job.status == "iptal"
    assert wait_until(lambda: not _marked_browsers(), 10)


# --- 12. istek boyutu ve disk alanı ------------------------------------------------------------


def test_request_size_limit(settings, monkeypatch):
    settings.max_request_mb = 1
    monkeypatch.setattr(engines, "detect_all", lambda _s: [])
    with TestClient(app_module.create_app(settings, start_background=False)) as c:
        c.get("/api/session")
        r = c.post("/api/files", files=[("files", ("b.pdf", b"x" * (2 * 1024 * 1024)))])
        assert r.status_code == 413 and "en fazla 1 MB" in r.json()["detail"]

        def chunks():  # uzunluk bildirmeyen gövde
            for _ in range(40):
                yield b"y" * 65536

        r = c.post("/api/files", content=chunks(),
                   headers={"content-type": "multipart/form-data; boundary=sinir"})
        assert r.status_code == 413
        assert c.get("/api/files").json() == []


def test_upload_rejected_when_disk_is_full(client, monkeypatch):
    monkeypatch.setattr(limits, "free_bytes", lambda _p: 10 * 1024 * 1024)
    r = client.post("/api/files", files=[("files", ("a.pdf", b"%PDF" + b"0" * 1000))])
    assert r.status_code == 507 and "Diskte yer yok" in r.json()["detail"]


def test_disk_full_during_store_write_is_friendly(client, monkeypatch, tmp_path):
    import shutil as shutil_module

    def full(*a, **k):
        raise OSError(28, "No space left on device")

    store = client.app.state.store
    monkeypatch.setattr(shutil_module, "copyfile", full)
    with pytest.raises(PdfAtolyeError, match="Diskte yer kalmadı"):
        store.add_file(fx.numbered(tmp_path / "a.pdf", 1, with_toc=False), "a.pdf")
    assert store.list() == []


# --- 13. küçükler ------------------------------------------------------------------------------


def test_decompression_bomb_is_friendly(tmp_path, monkeypatch):
    png = tmp_path / "dev.png"
    Image.new("RGB", (400, 400), "white").save(png)
    monkeypatch.setattr(Image, "MAX_IMAGE_PIXELS", 1000)  # 2×'i aşan resim hata verir
    with pytest.raises(ImageTooLargeError, match="çok büyük bir resim"):
        images.images_to_pdf([png], tmp_path / "o.pdf")


def test_decompression_bomb_job_message(client, tmp_path, monkeypatch):
    png = tmp_path / "dev.png"
    Image.new("RGB", (400, 400), "white").save(png)
    meta = upload(client, png, "dev.png")
    monkeypatch.setattr(Image, "MAX_IMAGE_PIXELS", 1000)
    job = run_job(client, {"type": "images_to_pdf", "files": [meta["id"]]})
    assert job["status"] == "hata" and "çok büyük bir resim" in job["error"]
    assert "Hata kimliği" not in job["error"]
