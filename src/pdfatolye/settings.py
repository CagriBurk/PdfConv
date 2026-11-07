"""Ayarlar: varsayılanlar + config.toml.

Arama sırası: PDFATOLYE_CONFIG ortam değişkeni → (yalnızca geliştirmede) proje kökündeki
config.toml →
%LOCALAPPDATA%\\PdfAtolye\\config.toml. Bulunamazsa varsayılanlar kullanılır.
"""

from __future__ import annotations

import os
import tomllib
from dataclasses import dataclass, field, fields
from pathlib import Path

from pdfatolye import paths

# Geliştirmede depo kökü. Kurulu pakette anlamsızdır; dosya yolları için `paths` kullan.
PROJECT_ROOT = paths.SOURCE_ROOT


def default_data_dir() -> Path:
    base = os.environ.get("LOCALAPPDATA") or str(Path.home() / ".local" / "share")
    return Path(base) / "PdfAtolye"


@dataclass
class EnginePaths:
    """Dış araçların elle verilmiş yolları. Boşsa otomatik aranır."""

    libreoffice: str = ""
    tesseract: str = ""
    ghostscript: str = ""
    browser: str = ""


@dataclass
class Settings:
    host: str = "127.0.0.1"
    port: int = 8790
    data_dir: Path = field(default_factory=default_data_dir)
    retention_hours: int = 24
    max_upload_mb: int = 1024  # dosya başına
    max_request_mb: int = 4096  # tek yüklemede (çok dosya) toplam
    vault_path: Path | None = None
    open_browser: bool = True
    lan: bool = False  # telefon modu: 0.0.0.0, QR koddaki belirteçle eşleşme
    allowed_hosts: list[str] = field(default_factory=lambda: ["127.0.0.1", "localhost"])
    engines: EnginePaths = field(default_factory=EnginePaths)
    config_file: Path | None = None

    @property
    def files_dir(self) -> Path:
        return self.data_dir / "files"

    @property
    def jobs_dir(self) -> Path:
        return self.data_dir / "jobs"

    @property
    def logs_dir(self) -> Path:
        return self.data_dir / "logs"
    def ensure_dirs(self) -> None:
        for d in (self.files_dir, self.jobs_dir, self.logs_dir):
            d.mkdir(parents=True, exist_ok=True)


def _candidate_config_files() -> list[Path]:
    out: list[Path] = []
    if env := os.environ.get("PDFATOLYE_CONFIG"):
        out.append(Path(env))
    if paths.is_dev_checkout():
        out.append(PROJECT_ROOT / "config.toml")
    out.append(default_data_dir() / "config.toml")
    return out


def load_settings(config_file: Path | None = None) -> Settings:
    path = config_file
    if path is None:
        path = next((p for p in _candidate_config_files() if p.is_file()), None)

    settings = Settings()
    if path is None:
        return settings

    with path.open("rb") as f:
        raw = tomllib.load(f)

    known = {f.name for f in fields(Settings)} - {"engines", "config_file"}
    unknown = set(raw) - known - {"engines"}
    if unknown:
        raise ValueError(f"{path}: bilinmeyen ayar(lar): {', '.join(sorted(unknown))}")

    for key, value in raw.items():
        if key == "engines":
            continue
        if key in ("data_dir", "vault_path"):
            value = Path(os.path.expandvars(value)) if value else None
            if key == "data_dir" and value is None:
                continue
        setattr(settings, key, value)

    engine_raw = raw.get("engines", {})
    engine_known = {f.name for f in fields(EnginePaths)}
    if bad := set(engine_raw) - engine_known:
        names = ", ".join(sorted(bad))
        raise ValueError(f"{path}: [engines] altında bilinmeyen ayar(lar): {names}")
    settings.engines = EnginePaths(**engine_raw)
    settings.config_file = path
    return settings
