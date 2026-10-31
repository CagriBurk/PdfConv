"""FastAPI uygulaması: API + derlenmiş arayüzün (web/dist) sunulması."""

from __future__ import annotations

import threading
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.trustedhost import TrustedHostMiddleware

from pdfatolye import __version__, engines
from pdfatolye.settings import PROJECT_ROOT, Settings

WEB_DIST = PROJECT_ROOT / "web" / "dist"

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


def create_app(settings: Settings) -> FastAPI:
    settings.ensure_dirs()
    app = FastAPI(title="PDF Atölyesi", version=__version__, docs_url="/api/docs")
    # Yalnızca localhost adlarıyla gelen isteklere izin ver: DNS rebinding saldırısını keser.
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=settings.allowed_hosts)
    app.state.settings = settings
    engine_cache = EngineCache(settings)

    @app.get("/api/health")
    def health() -> dict:
        return {"status": "ok", "version": __version__}

    @app.get("/api/engines")
    def get_engines(refresh: bool = False) -> dict:
        return {
            "engines": [e.to_dict() for e in engine_cache.get(refresh)],
            "libraries": engines.python_libraries(),
            "data_dir": str(settings.data_dir),
            "config_file": str(settings.config_file) if settings.config_file else None,
        }

    _mount_ui(app, WEB_DIST)
    return app


def _mount_ui(app: FastAPI, dist: Path) -> None:
    index = dist / "index.html"
    if (dist / "assets").is_dir():
        app.mount("/assets", StaticFiles(directory=dist / "assets"), name="assets")

    # Tek sayfalık uygulama: /api dışındaki her yol index.html'e düşer.
    @app.get("/{path:path}", include_in_schema=False)
    def spa(path: str):
        if path.startswith("api/"):
            return HTMLResponse("Bulunamadı", status_code=404)
        candidate = (dist / path).resolve()
        if path and candidate.is_file() and candidate.is_relative_to(dist.resolve()):
            return FileResponse(candidate)
        if index.is_file():
            return FileResponse(index)
        return HTMLResponse(NO_UI_PAGE)
