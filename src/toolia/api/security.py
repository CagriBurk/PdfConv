"""Yerel sunucuyu tarayıcıdaki başka sitelerden ve yerel ağdaki başka cihazlardan korur.

1. Host başlığı (app.py, TrustedHostMiddleware): DNS rebinding'i keser.
2. Oturum çerezi (SameSite=Strict): başka bir sitenin sayfası API'ye istek atsa bile tarayıcı
   çerezi göndermez → 403.
3. Origin kontrolü: değiştiren isteklerde (POST/DELETE...) Origin, isteğin kendi kökeni (şema +
   sunucu + PORT, Host başlığıyla aynı) değilse → 403. Yalnızca sunucu adına bakılsaydı aynı
   bilgisayardaki başka bir yerel sitenin (`127.0.0.1:3000`) sayfası istek atabilirdi: çerez
   SameSite açısından "aynı site"dir, port farkı sayılmaz (GUVENLIK_PLANI.md, adım 8).
4. Güvenlik başlıkları: uygulama yalnızca kendi betiklerini çalıştırır (CSP), türü tahmin edilmez.
5. Telefon modu: her cihazın kendi oturumu var; QR kod tek kullanımlıktır ve 10 dakika geçerlidir,
   oturumlar kesilebilir. Cihaz oturumu eşleştiği IP adresine bağlıdır ve 8 saat sonra düşer; bu
   bilgisayarın oturumu telefon modunda yalnızca loopback'ten geçerlidir. Cihaz yalnızca kendi
   dosyalarını ve işlerini görür (`toolia.access`). Bağlantı HTTP'dir (şifresiz): bunlar, Wi-Fi'de
   ele geçirilen bir çerezin değerini sınırlar (GUVENLIK_PLANI.md, adım 5).
"""

from __future__ import annotations

import secrets
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass
from urllib.parse import urlparse

from starlette.datastructures import MutableHeaders
from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from toolia import access
from toolia.lan import LOOPBACK_HOSTS

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


PAIR_TTL_S = 10 * 60  # QR kodun geçerlilik süresi (arayüz kodu birkaç saniyede bir yeniler)
DEVICE_TTL_S = 8 * 3600  # eşleşmiş cihaz oturumunun ömrü; sonra QR yeniden okutulur


@dataclass
class Device:
    id: str  # dosya sahipliği için (belirteç değil; gizli değildir)
    ip: str
    paired_at: float
    expires: float


class Sessions:
    """Oturum belirteçleri: `local` bu bilgisayarın, `_devices` QR ile eşleşen cihazların.

    QR'daki eşleştirme belirteci tek kullanımlıktır ve `PAIR_TTL_S` sonra kendiliğinden yenilenir:
    adres çubuğunda, geçmişte ya da ağda görülen eski değer işe yaramaz.
    """

    def __init__(self, *, lan: bool = False, clock: Callable[[], float] = time.time) -> None:
        self._lock = threading.Lock()
        self._clock = clock
        self.lan = lan
        self.local = new_token()
        self._devices: dict[str, Device] = {}
        self._rotate_pair()

    def _rotate_pair(self) -> None:
        self._pair_token = secrets.token_urlsafe(16)
        self._pair_created = self._clock()

    def _expire(self) -> None:
        now = self._clock()
        if now - self._pair_created > PAIR_TTL_S:
            self._rotate_pair()
        for token in [k for k, d in self._devices.items() if d.expires <= now]:
            del self._devices[token]

    @property
    def pair_token(self) -> str:
        """Geçerli eşleştirme belirteci (süresi dolduysa yenisi)."""
        with self._lock:
            self._expire()
            return self._pair_token

    def identify(self, token: str | None, ip: str) -> tuple[bool, str | None]:
        """(geçerli mi, sahip). Sahip None: bu bilgisayar; metin: eşleşmiş cihazın kimliği.

        Cihaz belirteci yalnızca eşleştiği IP'den, bu bilgisayarınki telefon modunda yalnızca
        loopback'ten geçerlidir."""
        if not token:
            return False, None
        with self._lock:
            self._expire()
            local = self.local
            devices = list(self._devices.items())
        # Erken çıkmadan hepsi denenir: süre, hangi belirteçle eşleştiğini söylemesin.
        local_ok = tokens_match(token, local)
        matched = [d for k, d in devices if tokens_match(token, k)]
        if local_ok:
            return (not self.lan or ip in LOOPBACK_HOSTS), None
        if matched and matched[0].ip == ip:
            return True, matched[0].id
        return False, None

    def is_valid(self, token: str | None, ip: str) -> bool:
        return self.identify(token, ip)[0]

    def pair(self, given: str, ip: str) -> str | None:
        """Belirteç doğru ve süresi dolmamışsa cihaza yeni oturum açar ve belirteci yeniler;
        değilse None."""
        with self._lock:
            self._expire()
            if not tokens_match(given, self._pair_token):
                return None
            self._rotate_pair()
            token = new_token()
            now = self._clock()
            self._devices[token] = Device(secrets.token_hex(8), ip, now, now + DEVICE_TTL_S)
            return token

    def devices(self) -> list[Device]:
        with self._lock:
            self._expire()
            return sorted(self._devices.values(), key=lambda d: d.paired_at)

    def revoke_devices(self) -> int:
        """Bütün cihazların oturumunu keser; eski QR da geçersiz olur."""
        with self._lock:
            count = len(self._devices)
            self._devices.clear()
            self._rotate_pair()
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
                if origin and not self._same_origin(origin, _header(scope, b"host")):
                    await _deny("Başka bir siteden gelen istek reddedildi.")(scope, receive, send)
                    return
            client = scope.get("client")
            valid, owner = self.sessions.identify(_cookie(scope, COOKIE),
                                                  client[0] if client else "")
            if not valid:
                await _deny("Oturum geçersiz; sayfayı yenile.")(scope, receive, send)
                return
            # İsteğin sahibi: depo ve işler buna göre süzer (eşzamanlı uçlara da taşınır).
            with access.acting_as(owner):
                await self.app(scope, receive, send)
            return
        await self.app(scope, receive, send)


    def _same_origin(self, origin: str, host: str | None) -> bool:
        try:
            parsed = urlparse(origin)
        except ValueError:
            return False
        return (parsed.scheme == "http" and bool(host)
                and parsed.netloc.lower() == (host or "").lower()
                and parsed.hostname in self.allowed_hosts)


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
