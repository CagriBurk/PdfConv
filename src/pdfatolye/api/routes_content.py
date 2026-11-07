"""Editör uçları: kullanılabilir fontlar ve "İmzalarım"."""

from __future__ import annotations

import shutil
import tempfile
from pathlib import Path

from fastapi import APIRouter, Request, UploadFile
from fastapi.responses import FileResponse

from pdfatolye.core import fonts
from pdfatolye.core.content import prepare_signature
from pdfatolye.errors import PdfAtolyeError
from pdfatolye.storage import UploadTooLargeError

router = APIRouter(prefix="/api")

SIGNATURE_TAG = "signature"
MAX_SIGNATURE_MB = 20


@router.get("/fonts")
def list_fonts() -> list[dict]:
    return fonts.available()


@router.get("/fonts/{key}/file")
def font_file(key: str, bold: bool = False):
    """Uygulamayla gelen fontun TTF'i: editör önizlemesi PDF'e gömülen fontla aynı çizilsin
    (Windows fontları tarayıcıda zaten var, yalnızca gömülü olanlar sunulur)."""
    if key not in fonts.BUNDLED:
        raise PdfAtolyeError(f"Bilinmeyen font: {key}")
    return FileResponse(fonts.font_path(key, bold), media_type="font/ttf",
                        headers={"Cache-Control": "max-age=86400"})


@router.get("/signatures")
def list_signatures(request: Request) -> list[dict]:
    store = request.app.state.store
    return [m.to_dict() for m in store.list() if m.tag == SIGNATURE_TAG]


@router.post("/signatures")
def add_signature(request: Request, file: UploadFile) -> dict:
    """Çizilen ya da yüklenen imzayı hazırlar (saydam arka plan, kırpma) ve sabitlenmiş PNG
    olarak saklar; otomatik temizlik silmez."""
    store = request.app.state.store
    with tempfile.TemporaryDirectory(prefix="pa-imza-") as tmp:
        raw = Path(tmp) / ("girdi" + Path(file.filename or "imza.png").suffix.lower())
        with raw.open("wb") as out:
            shutil.copyfileobj(file.file, out)
        if raw.stat().st_size > MAX_SIGNATURE_MB * 1024 * 1024:
            raise UploadTooLargeError(MAX_SIGNATURE_MB)
        png = prepare_signature(raw, Path(tmp) / "imza.png")
        count = sum(1 for m in store.list() if m.tag == SIGNATURE_TAG)
        meta = store.add_file(png, f"İmza {count + 1}.png", source="upload",
                              note="İmza", pinned=True, tag=SIGNATURE_TAG)
    return meta.to_dict()
