"""FastAPI uygulaması: API + derlenmiş arayüzün (web/dist) sunulması."""

from __future__ import annotations

import logging
import threading
from contextlib import asynccontextmanager
from logging.handlers import RotatingFileHandler
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import ValidationError
from starlette.middleware.trustedhost import TrustedHostMiddleware

from pdfatolye import __version__, engines
from pdfatolye.api import routes_content, routes_files, routes_jobs, routes_md
from pdfatolye.api.security import COOKIE, SessionGuard, new_token
from pdfatolye.convert.markdown.document import ASSETS as MD_ASSETS
from pdfatolye.errors import PdfAtolyeError
from pdfatolye.jobs import JobManager
from pdfatolye.settings import PROJECT_ROOT, Settings
from pdfatolye.storage import FileNotInStoreError, FileStore

WEB_DIST = PROJECT_ROOT / "web" / "dist"
CLEANUP_INTERVAL_S = 3600
log = logging.getLogger("pdfatolye")

NO_UI_PAGE = """<!doctype html><html lang="tr"><meta charset="utf-8">
<title>PDF Atölyesi</title>
<body style="font-family:system-ui;max-width:40rem;margin:4rem auto;padding:0 1rem">
<h1>PDF Atölyesi</h1>
<p>Sunucu çalışıyor ama arayüz henüz derlenmemiş.</p>
<pre>npm --prefix web install
npm --prefix web run build</pre>
<p>API durumu: <a href="/api/engines">/api/engines</a></p>
</body></html>"""


class EngineCache:
    """Motor taraması birkaç alt süreç çalıştırır; sonucu saklayıp istendiğinde yeniler."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._lock = threading.Lock()
        self._value: list[engines.EngineStatus] | None = None

    def get(self, refresh: bool = False) -> list[engines.EngineStatus]:
        with self._lock:
            if refresh or self._value is None:
                self._value = engines.detect_all(self._settings)
            return self._value


def _setup_logging(settings: Settings) -> None:
    if any(isinstance(h, RotatingFileHandler) for h in log.handlers):
        return
    handler = RotatingFileHandler(settings.logs_dir / "pdfatolye.log", maxBytes=2_000_000,
                                  backupCount=3, encoding="utf-8")
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s"))
    log.addHandler(handler)
    log.setLevel(logging.INFO)


def _cleanup_loop(store: FileStore, hours: float, stop: threading.Event) -> None:
    while True:
        try:
            removed = store.cleanup(hours)
            if removed:
                log.info("Temizlik: %d eski dosya silindi", removed)
        except Exception:
            log.exception("Temizlik başarısız")
        if stop.wait(CLEANUP_INTERVAL_S):
            return


def create_app(settings: Settings, *, start_background: bool = True) -> FastAPI:
    settings.ensure_dirs()
    _setup_logging(settings)
    store = FileStore(settings.files_dir, settings.max_upload_mb)
    jobs = JobManager(store, settings)
    stop = threading.Event()
    token = new_token()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        if start_background:
            threading.Thread(target=_cleanup_loop, args=(store, settings.retention_hours, stop),
                             daemon=True, name="temizlik").start()
        yield
        stop.set()
        jobs.shutdown()

    app = FastAPI(title="PDF Atölyesi", version=__version__, docs_url="/api/docs",
                  openapi_url="/api/openapi.json", lifespan=lifespan)
    # Sıra önemli: dıştaki (son eklenen) önce çalışır. Önce Host, sonra oturum.
    app.add_middleware(SessionGuard, token=token, allowed_hosts=settings.allowed_hosts)
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=settings.allowed_hosts)
    app.state.settings = settings
    app.state.store = store
    app.state.jobs = jobs
    app.state.token = token
    app.state.preview_assets = routes_md.PreviewAssets(token)
    engine_cache = EngineCache(settings)

    @app.exception_handler(PdfAtolyeError)
    async def _app_error(request: Request, exc: PdfAtolyeError):
        status = 404 if isinstance(exc, FileNotInStoreError) else 400
        return JSONResponse({"detail": str(exc)}, status_code=status)

    @app.exception_handler(ValidationError)
    async def _validation_error(request: Request, exc: ValidationError):
        return JSONResponse({"detail": _first_error(exc.errors())}, status_code=422)

    @app.exception_handler(RequestValidationError)
    async def _request_validation_error(request: Request, exc: RequestValidationError):
        return JSONResponse({"detail": _first_error(exc.errors())}, status_code=422)

    @app.get("/api/health")
    def health() -> dict:
        # "app" alanı: aynı portta başka bir uygulama varsa onu bizimki sanmayalım.
        return {"status": "ok", "app": "pdfatolye", "version": __version__}

    @app.get("/api/session")
    def session() -> JSONResponse:
        resp = JSONResponse({"ok": True, "version": __version__})
        _set_cookie(resp, token)
        return resp

    @app.get("/api/engines")
    def get_engines(refresh: bool = False) -> dict:
        return {
            "engines": [e.to_dict() for e in engine_cache.get(refresh)],
            "libraries": engines.python_libraries(),
            "data_dir": str(settings.data_dir),
            "config_file": str(settings.config_file) if settings.config_file else None,
            "vault_path": str(settings.vault_path) if settings.vault_path else None,
            "retention_hours": settings.retention_hours,
        }

    app.include_router(routes_files.router)
    app.include_router(routes_jobs.router)
    app.include_router(routes_md.router)
    app.include_router(routes_content.router)
    app.mount("/api/md/katex", StaticFiles(directory=MD_ASSETS / "katex"), name="katex")
    _mount_ui(app, WEB_DIST, token)
    return app


def _first_error(errors: list) -> str:
    if not errors:
        return "Geçersiz istek."
    e = errors[0]
    where = ".".join(str(p) for p in e.get("loc", ()) if p not in ("body",))
    msg = str(e.get("msg", "geçersiz")).removeprefix("Value error, ")
    return f"{where}: {msg}" if where else msg


def _set_cookie(resp, token: str) -> None:
    resp.set_cookie(COOKIE, token, httponly=True, samesite="strict", path="/")


def _mount_ui(app: FastAPI, dist: Path, token: str) -> None:
    index = dist / "index.html"
    if (dist / "assets").is_dir():
        app.mount("/assets", StaticFiles(directory=dist / "assets"), name="assets")

    # Tek sayfalık uygulama: /api dışındaki her yol index.html'e düşer.
    @app.get("/{path:path}", include_in_schema=False)
    def spa(path: str):
        if path.startswith("api/"):
            return JSONResponse({"detail": "Bulunamadı"}, status_code=404)
        candidate = (dist / path).resolve()
        if path and candidate.is_file() and candidate.is_relative_to(dist.resolve()):
            return FileResponse(candidate)
        resp = FileResponse(index) if index.is_file() else HTMLResponse(NO_UI_PAGE)
        _set_cookie(resp, token)
        return resp
