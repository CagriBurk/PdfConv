"""Güvenlik adım 9: dağıtım bütünlüğü (GUVENLIK_PLANI.md).

Paket imzasız; indiren, zip'in değiştirilmediğini Release'teki `<zip>.sha256` ile doğrular.
"""

from __future__ import annotations

import hashlib
import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _derle():
    spec = importlib.util.spec_from_file_location("derle", ROOT / "paket" / "derle.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_package_checksum_file(tmp_path):
    archive = tmp_path / "Toolia-9.9.9.zip"
    archive.write_bytes(b"PK\x05\x06" + bytes(range(256)) * 5000)
    out = _derle().write_checksum(archive)
    assert out.name == "Toolia-9.9.9.zip.sha256"
    raw = out.read_bytes()
    assert b"\r" not in raw
    digest, name = raw.decode("ascii").strip().split(" *")
    assert name == archive.name
    assert digest == hashlib.sha256(archive.read_bytes()).hexdigest()


def test_readme_explains_verification():
    text = (ROOT / "README.md").read_text(encoding="utf-8")
    assert "Get-FileHash" in text and ".zip.sha256" in text
