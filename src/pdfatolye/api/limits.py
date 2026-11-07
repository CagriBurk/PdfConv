"""İstek boyutu sınırı ve disk alanı denetimi (uç çalışmadan ÖNCE).

Çok parçalı (multipart) yükleme, FastAPI uca ulaşmadan önce gövdeyi geçici klasöre tamamen
yazar; dosya başına sınır (`max_upload_mb`) ancak bundan sonra denetlenebilir. Bu ara katman:
- `Content-Length` sınırı aşıyorsa ya da diskte yer yoksa gövdeyi hiç okumadan reddeder,
- uzunluk bildirmeyen (chunked) istekte okunan baytı sayar, sınırda keser.
"""

from __future__ import annotations

import json
import shutil
import tempfile
from pathlib import Path

from starlette.exceptions import HTTPException
from starlette.types import ASGIApp, Message, Receive, Scope, Send

MB = 1024 * 1024
JSON_LIMIT_MB = 64  # yükleme dışı istekler (not metni 5 MB, sayfa listesi...) için bol bir sınır
DISK_RESERVE_MB = 256  # yükleme sonrası diskte en az bu kadar yer kalsın


class _TooLarge(HTTPException):
    """Gövde okunurken sınır aşıldı. HTTPException: FastAPI gövde ayrıştırma hatalarını 400'e
    çevirir ama HTTPException'ı olduğu gibi geçirir (413 ve Türkçe mesaj kalsın)."""

    def __init__(self, detail: str) -> None:
        super().__init__(status_code=413, detail=detail)


def free_bytes(path: Path) -> int | None:
    try:
        return shutil.disk_usage(path).free
    except OSError:
        return None


def space_problem(length: int, data_dir: Path) -> str | None:
    """Gövde geçici klasöre, sonra depoya yazılır: aynı sürücüdeyse iki katı yer gerekir."""
    need: dict[str, int] = {}
    free: dict[str, int | None] = {}
    for path in (Path(tempfile.gettempdir()), Path(data_dir)):
        probe = path if path.exists() else path.anchor or path
        drive = Path(probe).resolve().anchor.lower() or str(probe)
        need[drive] = need.get(drive, DISK_RESERVE_MB * MB) + length
        free[drive] = free_bytes(Path(probe))
    for drive, n in need.items():
        f = free[drive]
        if f is not None and f < n:
            return (f"Diskte yer yok: yükleme için {n // MB} MB gerekli, {drive.upper()} "
                    f"sürücüsünde {f // MB} MB boş. Biraz yer aç (İşler ve dosyalar sayfasından "
                    "eski dosyaları silebilirsin) ve yeniden dene.")
    return None


class RequestLimits:
    def __init__(self, app: ASGIApp, *, request_mb: int, data_dir: Path) -> None:
        self.app = app
        self.upload_bytes = request_mb * MB
        self.upload_mb = request_mb
        self.data_dir = data_dir

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http" or scope["method"] in ("GET", "HEAD", "OPTIONS"):
            await self.app(scope, receive, send)
            return
        headers = {k.decode("latin-1").lower(): v.decode("latin-1")
                   for k, v in scope.get("headers", [])}
        multipart = headers.get("content-type", "").startswith("multipart/")
        limit = self.upload_bytes if multipart else JSON_LIMIT_MB * MB
        limit_mb = self.upload_mb if multipart else JSON_LIMIT_MB
        too_large = (f"İstek çok büyük; bir seferde en fazla {limit_mb} MB gönderilebilir "
                     "(config.toml: max_request_mb). Dosyaları birkaç parti hâlinde yükle.")
        try:
            length = int(headers.get("content-length", ""))
        except ValueError:
            length = None
        if length is not None:
            if length > limit:
                await _reply(send, 413, too_large)
                return
            if multipart and (problem := space_problem(length, self.data_dir)):
                await _reply(send, 507, problem)
                return

        received = 0
        started = False

        async def counted_receive() -> Message:
            nonlocal received
            message = await receive()
            if message["type"] == "http.request":
                received += len(message.get("body", b""))
                if received > limit:
                    raise _TooLarge(too_large)
            return message

        async def tracked_send(message: Message) -> None:
            nonlocal started
            if message["type"] == "http.response.start":
                started = True
            await send(message)

        try:
            await self.app(scope, counted_receive, tracked_send)
        except _TooLarge:
            if not started:
                await _reply(send, 413, too_large)


async def _reply(send: Send, status: int, detail: str) -> None:
    body = json.dumps({"detail": detail}, ensure_ascii=False).encode("utf-8")
    await send({"type": "http.response.start", "status": status,
                "headers": [(b"content-type", b"application/json; charset=utf-8"),
                            (b"content-length", str(len(body)).encode()),
                            (b"connection", b"close")]})
    await send({"type": "http.response.body", "body": body})
