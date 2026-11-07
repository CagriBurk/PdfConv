"""Markdown canlı önizleme. Önizleme kullanıcının kendi tarayıcısında çizilir (KaTeX dahil);
PDF baskısıyla aynı HTML ve CSS kullanılır, yalnızca kağıt görünümü eklenir."""

from __future__ import annotations

import hashlib
import hmac
import secrets
from collections import OrderedDict
from pathlib import Path

from fastapi import APIRouter, Request
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from pdfatolye.api.security import SANDBOX_CSP
from pdfatolye.convert.markdown.document import (
    MdOptions,
    build_html,
    preview_csp,
    resolve_options,
)
from pdfatolye.convert.markdown.parser import parse_markdown
from pdfatolye.errors import PdfAtolyeError
from pdfatolye.jobs.models import FileId, MdOptionsModel

router = APIRouter(prefix="/api/md")
MAX_ASSETS = 2000


class PreviewAssets:
    """Önizlemedeki yerel resimler için tahmin edilemez belirteç → dosya yolu eşlemesi.

    Böylece istemci hiçbir zaman dosya yolu göndermez/görmez (yol geçişi saldırısı olmaz).
    """

    def __init__(self, secret: str) -> None:
        self._secret = secret.encode()
        self._map: OrderedDict[str, Path] = OrderedDict()

    def url_for(self, path: Path) -> str:
        token = hmac.new(self._secret, str(path).encode(), hashlib.sha256).hexdigest()[:40]
        self._map[token] = path
        self._map.move_to_end(token)
        while len(self._map) > MAX_ASSETS:
            self._map.popitem(last=False)
        return f"/api/md/asset/{token}"

    def get(self, token: str) -> Path | None:
        return self._map.get(token)


class PreviewBody(BaseModel):
    text: str = Field(max_length=5_000_000)
    attachments: list[FileId] = Field(default_factory=list, max_length=2000)
    options: MdOptionsModel = Field(default_factory=MdOptionsModel)


@router.post("/preview")
def preview(request: Request, body: PreviewBody) -> dict:
    state = request.app.state
    attachments = {}
    for fid in body.attachments:
        meta = state.store.get(fid)
        attachments[meta.name] = state.store.path(fid)
    vault = state.settings.vault_path
    # Not bir klasörde değil: göreli resimler yalnızca eklerden ve (varsa) kasadan çözülür.
    empty = state.settings.data_dir / "bos"
    parsed = parse_markdown(body.text, base_dir=vault or empty, vault=vault,
                            url_for=state.preview_assets.url_for, attachments=attachments,
                            confine=True)
    warnings = list(parsed.warnings)
    opts = resolve_options(MdOptions(**body.options.model_dump()), parsed.front_matter, warnings)
    origin = str(request.base_url).rstrip("/")
    nonce = secrets.token_urlsafe(16)
    html = build_html(parsed, opts, katex_dir=f"{origin}/api/md/katex", preview=True,
                      csp=preview_csp(nonce, f"{origin}/api/md/katex/"), nonce=nonce)
    return {"html": html, "warnings": warnings, "title": parsed.title,
            "options": {"theme": opts.theme, "paper": opts.paper, "toc": opts.toc,
                        "cover": opts.cover, "landscape": opts.landscape}}


@router.get("/asset/{token}")
def asset(request: Request, token: str):
    path = request.app.state.preview_assets.get(token)
    if path is None or not path.is_file():
        raise PdfAtolyeError("Önizleme resmi bulunamadı.")
    return FileResponse(path, headers={"Cache-Control": "no-store",
                                       "Content-Security-Policy": SANDBOX_CSP})
