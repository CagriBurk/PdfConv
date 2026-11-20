"""Uygulamanın kendi dosyalarının yerleri. Kod proje klasörüne bağlı değildir.

İki çalışma biçimi:
- **Geliştirme** (`uv run`): paket `src/toolia`; derlenmiş arayüz `web/dist`, ayar dosyası
  proje kökündeki `config.toml` olabilir.
- **Kurulu** (masaüstü paketi): python.org'un gömülü Python'u + `site-packages/toolia`.
  Derlenmiş arayüz paketin içinde (`toolia/web`), gömülü motorlar (Tesseract, Ghostscript)
  kurulum kökündeki `motorlar/` altında. Kurulum kökü `toolia-kurulum.json` işaret
  dosyasıyla bulunur (ya da `TOOLIA_HOME`).

Kullanıcı verisi her iki biçimde de `%LOCALAPPDATA%\\Toolia` (bkz. `settings.py`).
"""

from __future__ import annotations

import json
import os
import sys
from functools import cache
from pathlib import Path

PACKAGE_DIR = Path(__file__).resolve().parent
# Yalnızca geliştirmede anlamlı: src/toolia → depo kökü.
SOURCE_ROOT = PACKAGE_DIR.parents[1]
INSTALL_MARKER = "toolia-kurulum.json"


def is_dev_checkout() -> bool:
    """Kod bir git/proje klasöründen mi çalışıyor (uv run)?"""
    return (SOURCE_ROOT / "pyproject.toml").is_file() and \
        (SOURCE_ROOT / "src" / "toolia").resolve() == PACKAGE_DIR


@cache
def install_root() -> Path | None:
    """Masaüstü kurulumunun kökü; geliştirmede None."""
    if env := os.environ.get("TOOLIA_HOME"):
        return Path(env)
    for parent in Path(sys.executable).resolve().parents[:3]:
        if (parent / INSTALL_MARKER).is_file():
            return parent
    return None


def install_info() -> dict:
    """Kurulum işaret dosyasındaki bilgiler (sürüm, kurulum zamanı...); yoksa boş."""
    root = install_root()
    if root is None:
        return {}
    try:
        return json.loads((root / INSTALL_MARKER).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def web_dist() -> Path:
    """Derlenmiş arayüz: pakette `toolia/web`, geliştirmede `web/dist`."""
    packaged = PACKAGE_DIR / "web"
    if (packaged / "index.html").is_file():
        return packaged
    return SOURCE_ROOT / "web" / "dist"


def fonts_dir() -> Path:
    """Gömülü fontlar (Noto, OFL): paketin içinde, her iki biçimde de aynı yer."""
    return PACKAGE_DIR / "assets" / "fonts"


def engines_dir() -> Path | None:
    """Kurulumla gelen motorlar (Tesseract, Ghostscript); geliştirmede None."""
    root = install_root()
    return root / "motorlar" if root else None
