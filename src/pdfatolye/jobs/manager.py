"""İş kuyruğu: iş parçacığı havuzu, tür başına eşzamanlılık sınırı, ilerleme, iptal, kayıt.

Redis/Celery gibi dış bir kuyruk yok; tek kullanıcılı yerel uygulama için gereksiz.
"""

from __future__ import annotations

import json
import logging
import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict, dataclass, field
from pathlib import Path

from pdfatolye.errors import PdfAtolyeError, error_id, unexpected_message
from pdfatolye.jobs import workers

log = logging.getLogger("pdfatolye.jobs")

# Aynı anda en fazla kaç tane: tarayıcı/LibreOffice/OCR bellek ve işlemci yer.
LIMITS = {"md_to_pdf": 1, "office_to_pdf": 1, "ocr": 1}
KEEP_JOBS = 200


class JobCancelled(Exception):
    pass


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


class JobManager:
    def __init__(self, store, settings, max_workers: int = 4) -> None:
        self.store = store
        self.settings = settings
        self.dir = Path(settings.jobs_dir)
        self.dir.mkdir(parents=True, exist_ok=True)
        self._pool = ThreadPoolExecutor(max_workers=max_workers, thread_name_prefix="is")
        self._lock = threading.Lock()
        self._jobs: dict[str, Job] = {}
        self._cancel: set[str] = set()
        self._limits = {k: threading.Semaphore(v) for k, v in LIMITS.items()}
        self._load()

    # --- kayıt ---

    def _load(self) -> None:
        for f in sorted(self.dir.glob("*.json"), key=lambda p: p.stat().st_mtime)[-KEEP_JOBS:]:
            try:
                job = Job(**json.loads(f.read_text(encoding="utf-8")))
            except (OSError, ValueError, TypeError):
                continue
            if not job.done:  # önceki çalıştırmada yarım kalmış
                job.status, job.error = "hata", "Sunucu iş bitmeden kapandı."
                job.finished = job.finished or time.time()
                self._persist(job)
            self._jobs[job.id] = job

    def _persist(self, job: Job) -> None:
        path = self.dir / f"{job.id}.json"
        tmp = path.with_suffix(".tmp")
        tmp.write_text(json.dumps(job.to_dict(), ensure_ascii=False), encoding="utf-8")
        tmp.replace(path)

    def _update(self, job: Job, persist: bool = False, **changes) -> None:
        with self._lock:
            for k, v in changes.items():
                setattr(job, k, v)
            job.rev += 1
        if persist:
            self._persist(job)

    # --- dışa açık ---

    def submit(self, req) -> Job:
        job = Job(
            id=uuid.uuid4().hex,
            type=req.type,
            status="bekliyor",
            created=time.time(),
            request=req.model_dump(mode="json"),  # şifreler `exclude` ile dışarıda
        )
        with self._lock:
            self._jobs[job.id] = job
        self._persist(job)
        self._pool.submit(self._run, job, req)
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
        if not job.done:
            self._cancel.add(job_id)
            if job.status == "bekliyor":
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
        self._pool.shutdown(wait=False, cancel_futures=True)

    # --- çalıştırma ---

    def _run(self, job: Job, req) -> None:
        if job.status == "iptal":
            return
        limit = self._limits.get(job.type)
        if limit:
            limit.acquire()
        try:
            if job.id in self._cancel:
                return
            self._update(job, True, status="calisiyor", started=time.time(),
                         message="Çalışıyor")

            def report(progress: float, message: str = "") -> None:
                if job.id in self._cancel:
                    raise JobCancelled()
                self._update(job, progress=max(0.0, min(progress, 1.0)),
                             message=message or job.message)

            result = workers.run(self, req, report, job.id)
            self._update(job, True, status="bitti", progress=1.0, finished=time.time(),
                         outputs=[m.id for m in result.outputs], warnings=result.warnings,
                         message="Tamamlandı")
        except JobCancelled:
            self._update(job, True, status="iptal", finished=time.time(), message="İptal edildi")
        except (PdfAtolyeError, FileNotFoundError, ValueError) as e:
            self._update(job, True, status="hata", finished=time.time(), error=str(e),
                         message="Hata")
        except Exception as e:  # beklenmeyen: kullanıcıya kısa, loga ayrıntılı
            eid = error_id()
            log.exception("[%s] İş %s (%s) beklenmedik hata", eid, job.id, job.type)
            self._update(job, True, status="hata", finished=time.time(),
                         error=unexpected_message(e, eid), message="Hata")
        finally:
            if limit:
                limit.release()
            self._cancel.discard(job.id)
