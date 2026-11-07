"""FastAPI uygulaması: API + derlenmiş arayüzün (web/dist) sunulması."""

from __future__ import annotations

import logging
import mimetypes
import threading
from contextlib import asynccontextmanager
from logging.handlers import RotatingFileHandler
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from pydantic import ValidationError
from starlette.middleware.trustedhost import TrustedHostMiddleware

from pdfatolye import __version__, engines, lan
from pdfatolye.api import routes_content, routes_files, routes_jobs, routes_md
from pdfatolye.api.limits import RequestLimits
from pdfatolye.api.security import COOKIE, SecurityHeaders, SessionGuard, Sessions, app_csp
from pdfatolye.convert.markdown.document import ASSETS as MD_ASSETS
from pdfatolye.convert.markdown.document import katex_script_hash
from pdfatolye.errors import DiskFullError, PdfAtolyeError, error_id, unexpected_message
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

LAN_LOCKED_PAGE = """<!doctype html><html lang="tr"><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>PDF Atölyesi</title>
<body style="font-family:system-ui;max-width:30rem;margin:3rem auto;padding:0 1rem">
<h1>PDF Atölyesi</h1>
<p>Bu bilgisayar telefon modunda. Bağlanmak için bilgisayardaki <b>Ayarlar</b> sayfasındaki QR
kodu telefonun kamerasıyla okut. QR kod tek kullanımlıktır; önceden okutulmuşsa Ayarlar'daki yeni
kodu kullan.</p>
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
    target = settings.logs_dir / "pdfatolye.log"
    for h in [h for h in log.handlers if isinstance(h, RotatingFileHandler)]:
        if Path(h.baseFilename) == target.resolve():
            return
        log.removeHandler(h)  # başka veri klasörüyle yeniden oluşturuldu (testler)
        h.close()
    handler = RotatingFileHandler(target, maxBytes=2_000_000,
                                  backupCount=3, encoding="utf-8")
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s"))
    log.addHandler(handler)
    log.setLevel(logging.INFO)


def _cleanup_loop(store: FileStore, jobs: JobManager, hours: float, stop: threading.Event) -> None:
    while True:
        try:
            removed = store.cleanup(hours)
            if removed:
                log.info("Temizlik: %d eski dosya silindi", removed)
            old = jobs.cleanup(hours)
            if old:
                log.info("Temizlik: %d eski iş kaydı silindi", old)
        except Exception:
            log.exception("Temizlik başarısız")
        if stop.wait(CLEANUP_INTERVAL_S):
            return


WEB_MIME_TYPES = {
    ".js": "text/javascript", ".mjs": "text/javascript", ".css": "text/css",
    ".wasm": "application/wasm", ".json": "application/json", ".svg": "image/svg+xml",
    ".woff2": "font/woff2", ".woff": "font/woff", ".ttf": "font/ttf",
}


def register_mime_types() -> None:
    """Python dosya türünü Windows kayıt defterinden okur. Bazı makinelerde `.mjs` hiç yoktur ya da
    `.js` `text/plain` olarak kayıtlıdır (bazı programlar bunu bozar): tarayıcı modül betiğini
    reddeder, pdf.js yüklenmez, arayüzde hiçbir sayfa çizilmez. Kayıt defterine güvenilmez."""
    for ext, mime in WEB_MIME_TYPES.items():
        mimetypes.add_type(mime, ext)


def create_app(settings: Settings, *, start_background: bool = True) -> FastAPI:
    register_mime_types()
    if not settings.lan and settings.host not in lan.LOOPBACK_HOSTS:
        # Telefon modu dışında eşleştirme yok: bu bilgisayara özgü oturum herkese verilirdi.
        raise ValueError(f"host = \"{settings.host}\" güvenli değil: yerel ağdan bağlanmak için "
                         "host ayarını kaldırıp lan = true kullan.")
    settings.ensure_dirs()
    _setup_logging(settings)
    store = FileStore(settings.files_dir, settings.max_upload_mb)
    jobs = JobManager(store, settings)
    stop = threading.Event()
    sessions = Sessions()
    if settings.lan:
        settings.allowed_hosts = list(dict.fromkeys([*settings.allowed_hosts, *lan.lan_ips()]))

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        if start_background:
            threading.Thread(target=_cleanup_loop,
                             args=(store, jobs, settings.retention_hours, stop),
                             daemon=True, name="temizlik").start()
        yield
        stop.set()
        jobs.shutdown()

    # API belgeleri kapalı: CDN'den yüklenir (çevrimdışı açılmaz) ve kullanıcıya gerekmez.
    app = FastAPI(title="PDF Atölyesi", version=__version__, docs_url=None, redoc_url=None,
                  openapi_url=None, lifespan=lifespan)
    # Sıra önemli: dıştaki (son eklenen) önce çalışır. Başlıklar her yanıtta, önce Host, sonra
    # oturum.
    app.add_middleware(SessionGuard, sessions=sessions, allowed_hosts=settings.allowed_hosts)
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=settings.allowed_hosts)
    app.add_middleware(SecurityHeaders, csp=app_csp(katex_script_hash()))
    # En dışta: sınırı aşan ya da diske sığmayacak yükleme gövdesi hiç okunmadan reddedilir.
    app.add_middleware(RequestLimits, request_mb=settings.max_request_mb,
                       data_dir=settings.data_dir)
    app.state.settings = settings
    app.state.store = store
    app.state.jobs = jobs
    app.state.sessions = sessions
    app.state.preview_assets = routes_md.PreviewAssets(sessions.local)
    engine_cache = EngineCache(settings)

    @app.exception_handler(PdfAtolyeError)
    async def _app_error(request: Request, exc: PdfAtolyeError):
        status = (404 if isinstance(exc, FileNotInStoreError) else
              507 if isinstance(exc, DiskFullError) else 400)
        return JSONResponse({"detail": str(exc)}, status_code=status)

    @app.exception_handler(Exception)
    async def _unexpected(request: Request, exc: Exception):
        eid = error_id()
        log.error("[%s] %s %s beklenmedik hata", eid, request.method, request.url.path,
                  exc_info=exc)
        return JSONResponse({"detail": unexpected_message(exc, eid)}, status_code=500)

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
    def session(request: Request) -> JSONResponse:
        if settings.lan and not _trusted(request, sessions):
            return JSONResponse({"detail": "Telefon modunda bağlanmak için bilgisayardaki QR "
                                           "kodu okut."}, status_code=403)
        resp = JSONResponse({"ok": True, "version": __version__})
        # Eşleşmiş cihaz kendi çerezini korur; bu bilgisayarın oturumu ona verilmez.
        if not settings.lan or _is_local(request):
            _set_cookie(resp, sessions.local)
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
            "log_file": str(settings.logs_dir / "pdfatolye.log"),
        }

    @app.get("/api/lan")
    def lan_info(request: Request) -> dict:
        if not settings.lan:
            return {"enabled": False}
        if not _is_local(request):
            raise PdfAtolyeError("QR kod yalnızca sunucunun çalıştığı bilgisayarda gösterilir.")
        urls = [f"http://{ip}:{settings.port}/?t={sessions.pair_token}" for ip in lan.lan_ips()]
        return {"enabled": True, "urls": urls, "qr_svg": lan.qr_svg(urls[0]) if urls else None,
                "devices": [{"ip": d.ip, "paired_at": d.paired_at} for d in sessions.devices()]}

    @app.delete("/api/lan/devices")
    def revoke_devices(request: Request) -> dict:
        if not _is_local(request):
            raise PdfAtolyeError("Bağlantıları yalnızca sunucunun çalıştığı bilgisayar kesebilir.")
        return {"revoked": sessions.revoke_devices()}

    app.include_router(routes_files.router)
    app.include_router(routes_jobs.router)
    app.include_router(routes_md.router)
    app.include_router(routes_content.router)
    app.mount("/api/md/katex", StaticFiles(directory=MD_ASSETS / "katex"), name="katex")
    _mount_ui(app, WEB_DIST, sessions, lan_mode=settings.lan)
    return app


def _first_error(errors: list) -> str:
    if not errors:
        return "Geçersiz istek."
    e = errors[0]
    where = ".".join(str(p) for p in e.get("loc", ()) if p not in ("body",))
    msg = str(e.get("msg", "geçersiz")).removeprefix("Value error, ")
    return f"{where}: {msg}" if where else msg


def _is_local(request: Request) -> bool:
    host = request.client.host if request.client else ""
    return host in lan.LOOPBACK_HOSTS


def _trusted(request: Request, sessions: Sessions) -> bool:
    """Bu bilgisayardan mı, yoksa daha önce eşleşmiş (geçerli çerezli) bir cihazdan mı?"""
    return _is_local(request) or sessions.is_valid(request.cookies.get(COOKIE))


def _set_cookie(resp, token: str) -> None:
    resp.set_cookie(COOKIE, token, httponly=True, samesite="strict", path="/")


def _mount_ui(app: FastAPI, dist: Path, sessions: Sessions, *, lan_mode: bool) -> None:
    index = dist / "index.html"
    if (dist / "assets").is_dir():
        app.mount("/assets", StaticFiles(directory=dist / "assets"), name="assets")

    # Tek sayfalık uygulama: /api dışındaki her yol index.html'e düşer.
    @app.get("/{path:path}", include_in_schema=False)
    def spa(path: str, request: Request, t: str = ""):
        if path.startswith("api/"):
            return JSONResponse({"detail": "Bulunamadı"}, status_code=404)
        candidate = (dist / path).resolve()
        if path and candidate.is_file() and candidate.is_relative_to(dist.resolve()):
            return FileResponse(candidate)
        if lan_mode and not _trusted(request, sessions):
            host = request.client.host if request.client else "?"
            device_token = sessions.pair(t, host) if t else None
            if device_token is None:
                return HTMLResponse(LAN_LOCKED_PAGE, status_code=403)
            # Eşleşti: cihaza kendi çerezini ver, belirteci adres çubuğundan sil.
            log.info("Telefon modu: yeni cihaz eşleşti (%s)", host)
            resp = RedirectResponse("/", status_code=303)
            _set_cookie(resp, device_token)
            return resp
        resp = FileResponse(index) if index.is_file() else HTMLResponse(NO_UI_PAGE)
        if not lan_mode or _is_local(request):
            _set_cookie(resp, sessions.local)
        return resp
