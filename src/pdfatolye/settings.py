"""Ayarlar: varsayılanlar + config.toml.

Arama sırası: PDFATOLYE_CONFIG ortam değişkeni → (yalnızca geliştirmede) proje kökündeki
config.toml → %LOCALAPPDATA%\\PdfAtolye\\config.toml. Bulunamazsa varsayılanlar kullanılır.

Arayüzden değiştirilen ayarlar (`save_settings`) okunan dosyaya, dosya yoksa veri klasöründeki
`config.toml`'a yazılır: masaüstü kullanıcısı dosya düzenlemez, kurulu pakette proje kökü yoktur.
"""

from __future__ import annotations

import json
import os
import threading
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
    # Şehir planlama paftaları gibi GB'larca PDF'ler için (arkadaş denemesi: 2 GB'lık dosya 1 GB
    # sınırına takıldı). Yükleme akışla yazılır, bellek kullanmaz; disk alanı önceden denetlenir.
    max_upload_mb: int = 8192  # dosya başına
    max_request_mb: int = 16384  # tek yüklemede (çok dosya) toplam
    vault_path: Path | None = None
    default_theme: str = "ders"  # Markdown → PDF: notta ve ekranda seçilmemişse
    default_paper: str = "A4"
    welcome_done: bool = False  # ilk açılış tanıtımı görüldü
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


def _read_toml(path: Path) -> dict:
    # utf-8-sig: Not Defteri ve PowerShell (Set-Content -Encoding utf8) başa BOM koyar; tomllib
    # BOM'lu dosyayı "Invalid statement" ile reddederdi ve uygulama açılmazdı.
    return tomllib.loads(path.read_bytes().decode("utf-8-sig"))


def load_settings(config_file: Path | None = None) -> Settings:
    path = config_file
    if path is None:
        path = next((p for p in _candidate_config_files() if p.is_file()), None)

    settings = Settings()
    if path is None:
        return settings

    raw = _read_toml(path)

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


# --- arayüzden düzenleme ----------------------------------------------------------------------

# Arayüzden değiştirilebilen ayarlar. Geri kalanı (veri klasörü, motor yolları, sınırlar) dosyadan.
EDITABLE = ("retention_hours", "vault_path", "default_theme", "default_paper", "port", "lan",
            "welcome_done")
# Çalışan sunucuda hemen geçerli olmayanlar: yeniden başlatma gerekir.
NEEDS_RESTART = ("port", "lan")


def settings_file(settings: Settings) -> Path:
    """Arayüzün yazdığı dosya: okunan ayar dosyası, yoksa veri klasöründeki config.toml."""
    return settings.config_file or settings.data_dir / "config.toml"


def _toml_value(value) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, int | float):
        return repr(value)
    if isinstance(value, Path):
        value = str(value)
    if isinstance(value, str):
        # JSON'un kaçış biçimleri (\\, \", \n, \uXXXX) TOML temel dizgesinde de geçerli.
        return json.dumps(value, ensure_ascii=False)
    if isinstance(value, list):
        return "[" + ", ".join(_toml_value(v) for v in value) + "]"
    raise TypeError(f"TOML'a yazılamayan değer: {value!r}")


def dump_toml(raw: dict) -> str:
    """Bu uygulamanın ayar dosyası için yeterli TOML yazıcısı: düz değerler + tek düzey tablolar."""
    lines = ["# PDF Atölyesi ayarları. Uygulamanın Ayarlar ekranı bu dosyayı günceller;",
             "# elle de düzenlenebilir (açıklamalı örnek: config.example.toml).", ""]
    tables = {k: v for k, v in raw.items() if isinstance(v, dict)}
    lines += [f"{k} = {_toml_value(v)}" for k, v in raw.items() if k not in tables]
    for name, table in tables.items():
        lines += ["", f"[{name}]", *(f"{k} = {_toml_value(v)}" for k, v in table.items())]
    return "\n".join(lines) + "\n"


_SETTINGS_LOCK = threading.Lock()


def save_settings(settings: Settings, changes: dict) -> Path:
    """Değişiklikleri ayar dosyasına yazar (dosyadaki diğer ayarlar korunur) ve yeniden
    başlatma gerektirmeyenleri çalışan `settings` nesnesine uygular. `None` ya da boş dizge:
    ayar dosyadan kaldırılır (varsayılana döner)."""
    if bad := set(changes) - set(EDITABLE):
        raise ValueError(f"Arayüzden değiştirilemeyen ayar(lar): {', '.join(sorted(bad))}")
    with _SETTINGS_LOCK:
        path = settings_file(settings)
        raw = _read_toml(path) if path.is_file() else {}
        for key, value in changes.items():
            if value is None or value == "":
                raw.pop(key, None)
            else:
                raw[key] = str(value) if isinstance(value, Path) else value
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_name(path.name + ".tmp")
        tmp.write_text(dump_toml(raw), encoding="utf-8", newline="\n")
        tmp.replace(path)
        settings.config_file = path
        defaults = Settings()
        for key, value in changes.items():
            if key in NEEDS_RESTART:
                continue
            if key == "vault_path":
                value = Path(value) if value else None
            elif value is None or value == "":
                value = getattr(defaults, key)
            setattr(settings, key, value)
        return path
