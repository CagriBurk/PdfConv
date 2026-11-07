"""Ayarlar ve bu bilgisayara özgü işler: ayarları okuma/yazma, yeniden başlatma, klasör seçme,
Gezgin'de gösterme, arayüz hatalarının günlüğe yazılması.

Ayar değiştirme, yeniden başlatma ve masaüstü işleri yalnızca sunucunun çalıştığı bilgisayardan
(loopback) istenebilir: telefon modunda eşleşmiş bir cihaz kasa yolunu ya da portu değiştiremez.
"""

from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Literal

from fastapi import APIRouter, Request
from pydantic import BaseModel, Field, field_validator

from pdfatolye import lan, native
from pdfatolye.convert.markdown.document import PAPERS, THEMES
from pdfatolye.errors import PdfAtolyeError, error_id
from pdfatolye.settings import NEEDS_RESTART, _read_toml, save_settings, settings_file

router = APIRouter(prefix="/api")
log = logging.getLogger("pdfatolye")
client_log = logging.getLogger("pdfatolye.arayuz")


def is_local(request: Request) -> bool:
    host = request.client.host if request.client else ""
    return host in lan.LOOPBACK_HOSTS


def require_local(request: Request, what: str) -> None:
    if not is_local(request):
        raise PdfAtolyeError(f"{what} yalnızca uygulamanın çalıştığı bilgisayardan yapılabilir.")


def _file_values(settings) -> dict:
    """Ayar dosyasındaki (kaydedilmiş) değerler: port ve telefon modu çalışan sunucudan farklı
    olabilir (yeniden başlatılınca geçerli olur)."""
    path = settings_file(settings)
    try:
        raw = _read_toml(path) if path.is_file() else {}
    except (OSError, ValueError):
        raw = {}
    return raw


def settings_view(request: Request) -> dict:
    state = request.app.state
    s = state.settings
    raw = _file_values(s)
    return {
        "values": {
            "retention_hours": s.retention_hours,
            "vault_path": str(s.vault_path) if s.vault_path else "",
            "default_theme": s.default_theme,
            "default_paper": s.default_paper,
            "port": int(raw.get("port", 8790)),
            "lan": bool(raw.get("lan", False)),
            "welcome_done": s.welcome_done,
        },
        "running": {"port": s.port, "lan": s.lan},
        "restart_pending": bool(state.restart_pending),
        "restart_available": state.restart is not None,
        "config_file": str(settings_file(s)),
        "local": is_local(request),
        # Klasör seç / Gezgin'de göster yalnızca Windows'ta (native.py).
        "desktop": is_local(request) and os.name == "nt",
        "themes": list(THEMES),
        "papers": list(PAPERS),
    }


class SettingsBody(BaseModel):
    """Yalnızca gönderilen alanlar değişir. `vault_path: ""` kasayı kaldırır."""

    model_config = {"extra": "forbid"}
    retention_hours: int | None = Field(default=None, ge=1, le=24 * 365)
    vault_path: str | None = Field(default=None, max_length=1000)
    default_theme: Literal[THEMES] | None = None  # type: ignore[valid-type]
    default_paper: Literal[PAPERS] | None = None  # type: ignore[valid-type]
    port: int | None = Field(default=None, ge=1024, le=65535)
    lan: bool | None = None
    welcome_done: bool | None = None

    @field_validator("vault_path")
    @classmethod
    def _vault(cls, v: str | None) -> str | None:
        if v is None:
            return None
        v = v.strip().strip('"')
        if not v:
            return ""
        p = Path(v).expanduser()
        if not p.is_absolute():
            raise ValueError("Kasa yolu tam bir klasör yolu olmalı (ör. C:\\Users\\...\\Kasam).")
        if not p.is_dir():
            raise ValueError(f"Klasör bulunamadı: {p}")
        if p.resolve() == Path(p.resolve().anchor):
            raise ValueError("Bir sürücünün tamamı kasa olarak seçilemez; kasa klasörünü seç.")
        return str(p.resolve())


@router.get("/settings")
def get_settings(request: Request) -> dict:
    return settings_view(request)


@router.put("/settings")
def put_settings(request: Request, body: SettingsBody) -> dict:
    require_local(request, "Ayarları değiştirmek")
    state = request.app.state
    changes = {k: getattr(body, k) for k in body.model_fields_set}
    if not changes:
        return settings_view(request)
    save_settings(state.settings, changes)
    for key in NEEDS_RESTART:
        if key in changes:
            if changes[key] == getattr(state.settings, key):
                state.restart_pending.discard(key)
            else:
                state.restart_pending.add(key)
    log.info("Ayarlar değişti: %s", ", ".join(sorted(changes)))
    return settings_view(request)


@router.post("/restart")
def restart(request: Request) -> dict:
    """Masaüstü uygulamasında sunucuyu yeni ayarlarla yeniden başlatır (pencere açık kalır)."""
    require_local(request, "Yeniden başlatmak")
    state = request.app.state
    if state.restart is None:
        raise PdfAtolyeError("Bu çalışma biçiminde uygulama kendini yeniden başlatamaz: sunucuyu "
                             "kapatıp yeniden aç (baslat.bat).")
    port = settings_view(request)["values"]["port"]
    state.restart()
    return {"url": f"http://127.0.0.1:{port}"}


class PickFolderBody(BaseModel):
    initial: str | None = Field(default=None, max_length=1000)


@router.post("/pick-folder")
def pick_folder(request: Request, body: PickFolderBody) -> dict:
    require_local(request, "Klasör seçmek")
    return {"path": native.pick_folder(body.initial, "Obsidian kasasının klasörünü seç")}


@router.post("/files/{file_id}/reveal")
def reveal(request: Request, file_id: str) -> dict:
    """Dosyanın bir kopyasını gerçek adıyla dışa aktarma klasörüne koyar ve Gezgin'de gösterir."""
    require_local(request, "Klasörde göstermek")
    state = request.app.state
    target = native.export_copy(state.store, state.settings.data_dir, file_id)
    native.reveal(target)
    return {"path": str(target)}


class ClientErrorBody(BaseModel):
    message: str = Field(max_length=2000)
    stack: str = Field(default="", max_length=20_000)
    where: str = Field(default="", max_length=500)


@router.post("/client-error")
def client_error(body: ClientErrorBody) -> dict:
    """Arayüzde yakalanan beklenmeyen hata: kullanıcıya kısa kimlik, günlüğe ayrıntı."""
    eid = error_id()
    client_log.error("[%s] arayüz hatası (%s): %s\n%s", eid, body.where or "?", body.message,
                     body.stack)
    return {"id": eid}
