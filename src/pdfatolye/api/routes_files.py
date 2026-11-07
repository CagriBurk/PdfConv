"""Dosya uçları: yükle, listele, indir, sürüm geri al, sabitle, sil, ZIP."""

from __future__ import annotations

import os
import tempfile
import zipfile
from pathlib import Path

from fastapi import APIRouter, Query, Request, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
from starlette.background import BackgroundTask

from pdfatolye.api.security import SANDBOX_CSP
from pdfatolye.core.info import inspect_pdf
from pdfatolye.core.pdfio import safe_filename
from pdfatolye.errors import PdfAtolyeError
from pdfatolye.jobs.workers import with_display_name

router = APIRouter(prefix="/api")


def store(request: Request):
    return request.app.state.store


@router.post("/files")
def upload(request: Request, files: list[UploadFile]) -> list[dict]:
    out = []
    for f in files:
        out.append(store(request).add_stream(f.file, f.filename or "dosya").to_dict())
    return out


@router.get("/files")
def list_files(request: Request) -> list[dict]:
    return [m.to_dict() for m in store(request).list()]


@router.get("/files/{file_id}")
def get_file(request: Request, file_id: str) -> dict:
    return store(request).get(file_id).to_dict()


def _file_response(request: Request, file_id: str, version: int | None, disposition: str):
    s = store(request)
    meta = s.get(file_id)
    path = s.path(file_id, version)
    headers = {"Cache-Control": "no-store"}
    media = "application/pdf" if meta.kind == "pdf" else None
    if meta.kind != "pdf":
        # Yüklenen HTML/SVG uygulamanın kökeninde betik çalıştıramasın: kum havuzu, ve resim
        # olmayan her şey sayfa olarak değil indirme olarak sunulur.
        headers["Content-Security-Policy"] = SANDBOX_CSP
        if meta.kind != "image":
            disposition = "attachment"
    return FileResponse(path, media_type=media, filename=meta.name,
                        content_disposition_type=disposition, headers=headers)


@router.get("/files/{file_id}/raw")
def raw(request: Request, file_id: str, v: int | None = None):
    return _file_response(request, file_id, v, "inline")


@router.get("/files/{file_id}/download")
def download(request: Request, file_id: str, v: int | None = None):
    return _file_response(request, file_id, v, "attachment")


class PasswordBody(BaseModel):
    password: str = Field(max_length=1000)


@router.post("/files/{file_id}/password")
def check_password(request: Request, file_id: str, body: PasswordBody) -> dict:
    """Şifreyi doğrular. Şifre sunucuda saklanmaz; arayüz bellekte tutar ve işlere ekler."""
    try:
        info = inspect_pdf(store(request).path(file_id), body.password)
    except PdfAtolyeError as e:
        raise with_display_name(e, store(request)) from e
    return {"ok": True, "page_count": info.page_count}


@router.get("/files/{file_id}/info")
def info(request: Request, file_id: str) -> dict:
    """PDF incelemesi (metin var mı, sayfa boyutları...). Arayüz "metin yok → OCR?" önerir."""
    s = store(request)
    meta = s.get(file_id)
    if meta.kind != "pdf":
        raise PdfAtolyeError(f"'{meta.name}' bir PDF değil.")
    try:
        result = inspect_pdf(s.path(file_id)).to_dict()
    except PdfAtolyeError as e:
        raise with_display_name(e, s) from e
    result.pop("path", None)  # arayüz yol görmez
    return result


@router.post("/files/{file_id}/undo")
def undo(request: Request, file_id: str) -> dict:
    return store(request).undo(file_id).to_dict()


class PinBody(BaseModel):
    pinned: bool


@router.post("/files/{file_id}/pin")
def pin(request: Request, file_id: str, body: PinBody) -> dict:
    return store(request).set_pinned(file_id, body.pinned).to_dict()


class RenameBody(BaseModel):
    name: str = Field(min_length=1, max_length=200)


@router.post("/files/{file_id}/rename")
def rename(request: Request, file_id: str, body: RenameBody) -> dict:
    return store(request).rename(file_id, body.name).to_dict()


@router.delete("/files/{file_id}")
def delete(request: Request, file_id: str) -> dict:
    store(request).get(file_id)  # yoksa 404
    store(request).delete(file_id)
    return {"ok": True}


@router.get("/zip")
def zip_files(request: Request, ids: str = Query(max_length=40_000),
              name: str = "dosyalar.zip"):
    """Birden çok çıktıyı tek ZIP'te indirir (aynı adlar numaralanır)."""
    s = store(request)
    file_ids = [i for i in ids.split(",") if i]
    if not file_ids:
        raise PdfAtolyeError("ZIP için dosya seçilmedi.")
    fd, tmp_name = tempfile.mkstemp(prefix="pa-zip-", suffix=".zip")
    os.close(fd)
    used: set[str] = set()
    with zipfile.ZipFile(tmp_name, "w", zipfile.ZIP_DEFLATED) as zf:
        for fid in file_ids:
            meta = s.get(fid)
            arc, stem, ext, i = meta.name, Path(meta.name).stem, Path(meta.name).suffix, 2
            while arc.lower() in used:
                arc, i = f"{stem} ({i}){ext}", i + 1
            used.add(arc.lower())
            zf.write(s.path(fid), arc)
    zip_name = safe_filename(Path(name).stem, fallback="dosyalar") + ".zip"
    return FileResponse(tmp_name, media_type="application/zip", filename=zip_name,
                        background=BackgroundTask(Path(tmp_name).unlink, missing_ok=True))
