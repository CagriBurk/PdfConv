"""İş uçları: başlat, durum, canlı ilerleme (SSE), iptal."""

from __future__ import annotations

import asyncio
import json
from typing import Annotated

from fastapi import APIRouter, Body, Query, Request
from fastapi.responses import StreamingResponse
from pydantic import TypeAdapter

from pdfatolye.errors import PdfAtolyeError
from pdfatolye.jobs import JobRequest
from pdfatolye.lan import LOOPBACK_HOSTS
from pdfatolye.storage import FileNotInStoreError

router = APIRouter(prefix="/api")
_adapter = TypeAdapter(JobRequest)


def _is_local(request: Request) -> bool:
    return (request.client.host if request.client else "") in LOOPBACK_HOSTS


def job_view(request: Request, job) -> dict:
    """İş + çıktı dosyalarının meta verisi (silinmiş çıktılar atlanır)."""
    files = []
    for fid in job.outputs:
        try:
            files.append(request.app.state.store.get(fid).to_dict())
        except FileNotInStoreError:
            continue
    return job.view() | {"files": files}


@router.post("/jobs")
def submit(request: Request, payload: Annotated[dict, Body()]) -> dict:
    req = _adapter.validate_python(payload)
    if req.type == "install_engine" and not _is_local(request):
        # Telefon modunda eşleşmiş bir cihaz bu bilgisayara program kurduramaz.
        raise PdfAtolyeError("Program kurulumu yalnızca bu bilgisayardan başlatılabilir.")
    return job_view(request, request.app.state.jobs.submit(req))


@router.get("/jobs")
def list_jobs(request: Request, limit: int = Query(default=50, ge=1, le=500)) -> list[dict]:
    return [job_view(request, j) for j in request.app.state.jobs.list(limit)]


@router.get("/jobs/{job_id}")
def get_job(request: Request, job_id: str) -> dict:
    return job_view(request, request.app.state.jobs.get(job_id))


@router.post("/jobs/{job_id}/cancel")
def cancel(request: Request, job_id: str) -> dict:
    return job_view(request, request.app.state.jobs.cancel(job_id))


@router.get("/jobs/{job_id}/events")
async def events(request: Request, job_id: str):
    manager = request.app.state.jobs
    job = manager.get(job_id)

    async def stream():
        last = -1
        while True:
            if await request.is_disconnected():
                return
            if job.rev != last:
                last = job.rev
                yield f"data: {json.dumps(job_view(request, job), ensure_ascii=False)}\n\n"
            if job.done:
                return
            await asyncio.sleep(0.25)

    return StreamingResponse(stream(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-store", "X-Accel-Buffering": "no"})
