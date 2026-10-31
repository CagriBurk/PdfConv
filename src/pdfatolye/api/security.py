"""Yerel sunucuyu tarayıcıdaki başka sitelerden korur.

1. Host başlığı (app.py, TrustedHostMiddleware): DNS rebinding'i keser.
2. Oturum çerezi (SameSite=Strict): başka bir sitenin sayfası API'ye istek atsa bile tarayıcı
   çerezi göndermez → 403.
3. Origin kontrolü: değiştiren isteklerde (POST/DELETE...) Origin başka bir siteyse → 403.
"""

from __future__ import annotations

import secrets
from urllib.parse import urlparse

from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Receive, Scope, Send

COOKIE = "pa_oturum"
EXEMPT_PATHS = {"/api/health", "/api/session"}
# Önizleme iframe'i kum havuzunda (sandbox) çalışır, çerez gönderemez. Bu adresler yalnızca
# KaTeX'in statik dosyalarını ve tahmin edilemez belirteçli önizleme resimlerini verir.
EXEMPT_PREFIXES = ("/api/md/katex/", "/api/md/asset/")
SAFE_METHODS = {"GET", "HEAD", "OPTIONS"}


def new_token() -> str:
    return secrets.token_urlsafe(32)


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
    def __init__(self, app: ASGIApp, token: str, allowed_hosts: list[str]) -> None:
        self.app = app
        self.token = token
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
            if not secrets.compare_digest(_cookie(scope, COOKIE) or "", self.token):
                await _deny("Oturum geçersiz; sayfayı yenile.")(scope, receive, send)
                return
        await self.app(scope, receive, send)


def _deny(message: str) -> JSONResponse:
    return JSONResponse({"detail": message}, status_code=403)
