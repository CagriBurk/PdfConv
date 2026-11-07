"""Yerel sunucuyu tarayıcıdaki başka sitelerden ve yerel ağdaki başka cihazlardan korur.

1. Host başlığı (app.py, TrustedHostMiddleware): DNS rebinding'i keser.
2. Oturum çerezi (SameSite=Strict): başka bir sitenin sayfası API'ye istek atsa bile tarayıcı
   çerezi göndermez → 403.
3. Origin kontrolü: değiştiren isteklerde (POST/DELETE...) Origin başka bir siteyse → 403.
4. Güvenlik başlıkları: uygulama yalnızca kendi betiklerini çalıştırır (CSP), türü tahmin edilmez.
5. Telefon modu: her cihazın kendi oturumu var; QR kod tek kullanımlıktır, oturumlar kesilebilir.
"""

from __future__ import annotations

import secrets
import threading
import time
from dataclasses import dataclass
from urllib.parse import urlparse

from starlette.datastructures import MutableHeaders
from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Message, Receive, Scope, Send

COOKIE = "pa_oturum"
EXEMPT_PATHS = {"/api/health", "/api/session"}
# Önizleme çerçevesindeki KaTeX'in statik dosyaları; gizli bir şey içermez.
EXEMPT_PREFIXES = ("/api/md/katex/",)
SAFE_METHODS = {"GET", "HEAD", "OPTIONS"}
# Yüklenen dosyalar doğrudan açılsa bile betik çalıştıramaz, uygulamanın kökenini paylaşamaz.
SANDBOX_CSP = "sandbox; default-src 'none'; img-src data:; style-src 'unsafe-inline'"


def new_token() -> str:
    return secrets.token_urlsafe(32)


def tokens_match(given: str, expected: str) -> bool:
    """Sabit süreli karşılaştırma. Dışarıdan ASCII olmayan değer de gelebilir; `compare_digest`
    str'de buna hata verir, bu yüzden bayt olarak karşılaştırılır."""
    return secrets.compare_digest(given.encode("utf-8", "replace"),
                                  expected.encode("utf-8", "replace"))


def app_csp(inline_script_hash: str) -> str:
    """Uygulama sayfasının politikası. Markdown önizlemesi srcdoc çerçevesidir, bu politikayı da
    devralır: tek izinli satır içi betik KaTeX başlatıcısıdır (özetiyle). `wasm-unsafe-eval`
    pdf.js'in görüntü çözücüleri için. Satır içi stil React/Konva için gerekli.
    `connect-src` bu bilgisayarın diğer portları: masaüstü uygulaması yeni portta yeniden
    başlayınca arayüz yeni sunucuyu yoklar (bkz. restart.ts; içerik okunamaz, yalnızca açık mı)."""
    return (
        "default-src 'self'; "
        f"script-src 'self' 'wasm-unsafe-eval' '{inline_script_hash}'; "
        "style-src 'self' 'unsafe-inline'; img-src 'self' data: blob:; font-src 'self' data:; "
        "worker-src 'self' blob:; connect-src 'self' http://127.0.0.1:*; frame-src 'self'; "
        "object-src 'none'; "
        "base-uri 'self'; form-action 'self'; frame-ancestors 'self'"
    )


@dataclass
class Device:
    ip: str
    paired_at: float


class Sessions:
    """Oturum belirteçleri: `local` bu bilgisayarın, `devices` QR ile eşleşen cihazların.

    QR'daki eşleştirme belirteci tek kullanımlıktır: kullanılınca yenisi üretilir. Böylece
    adres çubuğunda, geçmişte ya da ağda görülen eski değer işe yaramaz.
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self.local = new_token()
        self.pair_token = secrets.token_urlsafe(16)
        self._devices: dict[str, Device] = {}

    def is_valid(self, token: str | None) -> bool:
        if not token:
            return False
        with self._lock:
            known = [self.local, *self._devices]
        # Erken çıkmadan hepsi denenir: süre, hangi belirteçle ne kadar eşleştiğini söylemesin.
        return any([tokens_match(token, k) for k in known])

    def pair(self, given: str, ip: str) -> str | None:
        """Belirteç doğruysa cihaza yeni oturum açar ve belirteci yeniler; değilse None."""
        with self._lock:
            if not tokens_match(given, self.pair_token):
                return None
            self.pair_token = secrets.token_urlsafe(16)
            token = new_token()
            self._devices[token] = Device(ip, time.time())
            return token

    def devices(self) -> list[Device]:
        with self._lock:
            return sorted(self._devices.values(), key=lambda d: d.paired_at)

    def revoke_devices(self) -> int:
        """Bütün cihazların oturumunu keser; eski QR da geçersiz olur."""
        with self._lock:
            count = len(self._devices)
            self._devices.clear()
            self.pair_token = secrets.token_urlsafe(16)
            return count


def _cookie(scope: Scope, name: str) -> str | None:
    for key, value in scope.get("headers", []):
        if key == b"cookie":
            for part in value.decode("latin-1").split(";"):
                k, _, v = part.strip().partition("=")
                if k == name:
                    return v
    return None


def _header(scope: Scope, name: bytes) -> str | None:
    for key, value in scope.get("headers", []):
        if key == name:
            return value.decode("latin-1")
    return None


class SessionGuard:
    def __init__(self, app: ASGIApp, sessions: Sessions, allowed_hosts: list[str]) -> None:
        self.app = app
        self.sessions = sessions
        self.allowed_hosts = set(allowed_hosts)

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        path = scope.get("path", "")
        if (
            scope["type"] == "http"
            and path.startswith("/api/")
            and path not in EXEMPT_PATHS
            and not path.startswith(EXEMPT_PREFIXES)
        ):
            if scope["method"] not in SAFE_METHODS:
                origin = _header(scope, b"origin")
                if origin and urlparse(origin).hostname not in self.allowed_hosts:
                    await _deny("Başka bir siteden gelen istek reddedildi.")(scope, receive, send)
                    return
            if not self.sessions.is_valid(_cookie(scope, COOKIE)):
                await _deny("Oturum geçersiz; sayfayı yenile.")(scope, receive, send)
                return
        await self.app(scope, receive, send)


class SecurityHeaders:
    """Her yanıta güvenlik başlıkları ekler. Yanıt kendi CSP'sini koyduysa ona dokunmaz."""

    def __init__(self, app: ASGIApp, csp: str) -> None:
        self.app = app
        self.csp = csp

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        async def with_headers(message: Message) -> None:
            if message["type"] == "http.response.start":
                headers = MutableHeaders(scope=message)
                headers.setdefault("Content-Security-Policy", self.csp)
                headers.setdefault("X-Content-Type-Options", "nosniff")
                headers.setdefault("Referrer-Policy", "no-referrer")
                headers.setdefault("X-Frame-Options", "SAMEORIGIN")
                headers.setdefault("Cross-Origin-Resource-Policy", "same-origin")
            await send(message)

        await self.app(scope, receive, with_headers)


def _deny(message: str) -> JSONResponse:
    return JSONResponse({"detail": message}, status_code=403)
