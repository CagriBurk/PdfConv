"""İş kuyruğu: iş parçacığı havuzları, tür başına eşzamanlılık sınırı, ilerleme, iptal, kayıt.

Redis/Celery gibi dış bir kuyruk yok; tek kullanıcılı yerel uygulama için gereksiz.

- Sınırlı türlerin (tarayıcı, LibreOffice, OCR) her birinin kendi tek iş parçacıklı sırası var:
  sırada bekleyen dört OCR işi genel havuzu tutmaz, basit bir birleştirme beklemeden çalışır.
- İptal bir bayraktır (`threading.Event`). Çekirdek ilerleme bildirirken (`report`), alt süreç
  beklerken (`proc.run`/`spawn`) ve tarayıcı baskısında (`OfflineBrowser.guard`) görülür;
  alt süreç ağacı hemen öldürülür.
- İşin kullandığı dosyalar, iş sıraya girdiği andan bitene kadar temizlikten korunur.
- İş kayıtları diskte JSON; dosya saklama süresiyle aynı sürede silinir.
"""

from __future__ import annotations

import json
import logging
import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict, dataclass, field, fields
from pathlib import Path

from pdfatolye import proc
from pdfatolye.errors import PdfAtolyeError, error_id, is_disk_full, unexpected_message
from pdfatolye.jobs import workers
from pdfatolye.storage import file_ids_in

log = logging.getLogger("pdfatolye.jobs")

# Aynı anda en fazla kaç tane: tarayıcı/LibreOffice/OCR bellek ve işlemci yer.
LIMITS = {"md_to_pdf": 1, "office_to_pdf": 1, "ocr": 1}
GENERAL_WORKERS = 4
KEEP_JOBS = 200  # bellekte ve diskte tutulan en fazla kayıt
# Yanıtlarda `request`in yalnızca küçük alanları gider (arayüz `file` vb. kullanır); sayfa
# listesi ya da işlem listesi gibi büyük alanlar her yoklamada gönderilmez.
SUMMARY_MAX_STR = 300
SUMMARY_MAX_LIST = 50

# Eski ad: iptal artık bütün katmanlarda ortak.
JobCancelled = proc.Cancelled


@dataclass
class Job:
    id: str
    type: str
    status: str  # bekliyor | calisiyor | bitti | hata | iptal
    created: float
    request: dict
    progress: float = 0.0
    message: str = ""
    started: float | None = None
    finished: float | None = None
    outputs: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    error: str | None = None
    rev: int = 0  # her değişiklikte artar; canlı izleme (SSE) farkı buradan anlar

    @property
    def done(self) -> bool:
        return self.status in ("bitti", "hata", "iptal")

    def to_dict(self) -> dict:
        return asdict(self)

    def view(self) -> dict:
        """API yanıtı: büyük istek alanları çıkarılmış."""
        return self.to_dict() | {"request": request_summary(self.request)}


_JOB_FIELDS = {f.name for f in fields(Job)}


def request_summary(request: dict) -> dict:
    out = {}
    for key, value in request.items():
        if isinstance(value, str) and len(value) > SUMMARY_MAX_STR:
            continue
        if isinstance(value, list) and (len(value) > SUMMARY_MAX_LIST or not all(
                isinstance(v, (str, int, float, bool)) for v in value)):
            continue
        if isinstance(value, dict) and len(json.dumps(value)) > SUMMARY_MAX_STR * 4:
            continue
        out[key] = value
    return out


class JobManager:
    def __init__(self, store, settings, max_workers: int = GENERAL_WORKERS) -> None:
        self.store = store
        self.settings = settings
        self.dir = Path(settings.jobs_dir)
        self.dir.mkdir(parents=True, exist_ok=True)
        self._pool = ThreadPoolExecutor(max_workers=max_workers, thread_name_prefix="is")
        self._limited = {t: ThreadPoolExecutor(max_workers=n, thread_name_prefix=f"is-{t}")
                         for t, n in LIMITS.items()}
        self._lock = threading.Lock()
        self._jobs: dict[str, Job] = {}
        self._cancel: dict[str, threading.Event] = {}
        self._closing = False
        self._load()

    # --- kayıt ---

    def _load(self) -> None:
        files = sorted(self.dir.glob("*.json"), key=lambda p: p.stat().st_mtime)
        for f in files[:-KEEP_JOBS]:
            f.unlink(missing_ok=True)
        for f in files[-KEEP_JOBS:]:
            try:
                raw = json.loads(f.read_text(encoding="utf-8"))
                job = Job(**{k: v for k, v in raw.items() if k in _JOB_FIELDS})
            except (OSError, ValueError, TypeError) as e:
                log.warning("Bozuk iş kaydı atlandı: %s (%s)", f.name, e)
                continue
            if not job.done:  # önceki çalıştırmada yarım kalmış
                job.status, job.error = "hata", "Sunucu iş bitmeden kapandı."
                job.finished = job.finished or time.time()
                self._persist(job)
            self._jobs[job.id] = job

    def _persist(self, job: Job) -> None:
        path = self.dir / f"{job.id}.json"
        tmp = path.with_suffix(".tmp")
        try:
            tmp.write_text(json.dumps(job.to_dict(), ensure_ascii=False), encoding="utf-8")
            tmp.replace(path)
        except OSError:  # kayıt yazılamadı (disk dolu?): iş yine de bellekte doğru durumda
            log.exception("İş kaydı yazılamadı: %s", job.id)

    def _update(self, job: Job, persist: bool = False, **changes) -> None:
        with self._lock:
            for k, v in changes.items():
                setattr(job, k, v)
            job.rev += 1
        if persist:
            self._persist(job)

    def cleanup(self, retention_hours: float) -> int:
        """Bitmiş ve saklama süresi dolmuş iş kayıtlarını (bellek + disk) siler."""
        limit = time.time() - retention_hours * 3600
        with self._lock:
            old = [j for j in self._jobs.values()
                   if j.done and (j.finished or j.created) < limit]
            done = sorted((j for j in self._jobs.values() if j.done), key=lambda j: j.created)
            old += done[:max(0, len(self._jobs) - KEEP_JOBS)]
            for j in old:
                self._jobs.pop(j.id, None)
        for j in old:
            (self.dir / f"{j.id}.json").unlink(missing_ok=True)
        return len({j.id for j in old})

    # --- dışa açık ---

    def submit(self, req) -> Job:
        if self._closing:
            raise PdfAtolyeError("Sunucu kapanıyor; iş başlatılamadı.")
        dumped = req.model_dump(mode="json")  # şifreler ve not metni `exclude` ile dışarıda
        job = Job(id=uuid.uuid4().hex, type=req.type, status="bekliyor", created=time.time(),
                  request=dumped)
        held = file_ids_in(dumped)  # sıraya girdiği andan itibaren temizlikten korunur
        self.store.hold(held)
        with self._lock:
            self._jobs[job.id] = job
            self._cancel[job.id] = threading.Event()
        self._persist(job)
        pool = self._limited.get(req.type, self._pool)
        try:
            pool.submit(self._run, job, req, held)
        except RuntimeError:  # havuz kapandı (sunucu kapanıyor)
            self.store.release(held)
            self._update(job, True, status="hata", finished=time.time(),
                         error="Sunucu kapanıyor; iş başlatılamadı.", message="Hata")
        return job

    def get(self, job_id: str) -> Job:
        job = self._jobs.get(job_id)
        if job is None:
            raise PdfAtolyeError("İş bulunamadı.")
        return job

    def list(self, limit: int = 50) -> list[Job]:
        jobs = sorted(self._jobs.values(), key=lambda j: j.created, reverse=True)
        return jobs[:limit]

    def cancel(self, job_id: str) -> Job:
        job = self.get(job_id)
        event = self._cancel.get(job_id)
        if not job.done and event is not None:
            event.set()
            with self._lock:
                pending = job.status == "bekliyor"
            if pending:
                self._update(job, True, status="iptal", finished=time.time(),
                             message="İptal edildi")
        return job

    def wait(self, job_id: str, timeout: float = 120) -> Job:
        """Testler ve komut satırı için: iş bitene kadar bekler."""
        end = time.time() + timeout
        job = self.get(job_id)
        while not job.done and time.time() < end:
            time.sleep(0.05)
        return job

    def shutdown(self) -> None:
        """Sunucu kapanıyor: bekleyenler iptal, çalışanların alt süreçleri (LibreOffice, OCR,
        tarayıcı) öldürülür; öksüz süreç kalmaz."""
        self._closing = True
        for event in list(self._cancel.values()):
            event.set()
        for pool in [self._pool, *self._limited.values()]:
            pool.shutdown(wait=False, cancel_futures=True)
        killed = proc.kill_all()
        if killed:
            log.info("Kapanış: %d alt süreç durduruldu", killed)

    # --- çalıştırma ---

    def _run(self, job: Job, req, held: set[str]) -> None:
        event = self._cancel.get(job.id) or threading.Event()
        try:
            with self._lock:
                if job.status == "iptal" or event.is_set():
                    if not job.done:
                        job.status, job.finished = "iptal", time.time()
                        job.message = "İptal edildi"
                        job.rev += 1
                    return
                job.status, job.started, job.message = "calisiyor", time.time(), "Çalışıyor"
                job.rev += 1
            self._persist(job)

            def report(progress: float, message: str = "") -> None:
                if event.is_set():
                    raise JobCancelled()
                self._update(job, progress=max(0.0, min(progress, 1.0)),
                             message=message or job.message)

            with proc.cancel_scope(event.is_set):
                result = workers.run(self, req, report, job.id)
            self._update(job, True, status="bitti", progress=1.0, finished=time.time(),
                         outputs=[m.id for m in result.outputs], warnings=result.warnings,
                         message="Tamamlandı")
        except BaseException as e:
            self._fail(job, e, event)
            if not isinstance(e, Exception):
                raise
        finally:
            self.store.release(held)
            self._cancel.pop(job.id, None)

    def _fail(self, job: Job, e: BaseException, event: threading.Event) -> None:
        now = time.time()
        if event.is_set() or isinstance(e, JobCancelled):
            # Tarayıcı/LibreOffice öldürülünce çağrı başka bir hatayla da dönebilir: bayrak
            # kalktıysa sonuç "iptal"dir.
            self._update(job, True, status="iptal", finished=now, message="İptal edildi")
        elif isinstance(e, (PdfAtolyeError, FileNotFoundError, ValueError)):
            self._update(job, True, status="hata", finished=now, error=str(e), message="Hata")
        elif is_disk_full(e):
            self._update(job, True, status="hata", finished=now, message="Hata",
                         error="Diskte yer kalmadı. Biraz yer aç ve yeniden dene.")
        else:  # beklenmeyen: kullanıcıya kısa, loga ayrıntılı
            eid = error_id()
            log.error("[%s] İş %s (%s) beklenmedik hata", eid, job.id, job.type, exc_info=e)
            self._update(job, True, status="hata", finished=now,
                         error=unexpected_message(e, eid), message="Hata")
