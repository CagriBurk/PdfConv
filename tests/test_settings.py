import os
from pathlib import Path

import pytest

from toolia.settings import Settings, load_settings


def write(path: Path, text: str) -> Path:
    path.write_text(text, encoding="utf-8")
    return path


def test_defaults_are_local_only():
    s = Settings()
    assert s.host == "127.0.0.1"
    assert s.port == 8790
    assert "0.0.0.0" not in s.allowed_hosts


def test_load_overrides_and_engines(tmp_path: Path):
    cfg = write(
        tmp_path / "config.toml",
        'port = 9000\nretention_hours = 6\ndata_dir = "D:\\\\veri"\n'
        '[engines]\ntesseract = "C:\\\\tess\\\\tesseract.exe"\n',
    )
    s = load_settings(cfg)
    assert s.port == 9000
    assert s.retention_hours == 6
    assert s.data_dir == Path("D:\\veri")
    assert s.engines.tesseract == "C:\\tess\\tesseract.exe"
    assert s.engines.libreoffice == ""
    assert s.config_file == cfg


def test_data_dir_expands_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("PDFTEST_ROOT", str(tmp_path))
    # Ortam değişkeni işletim sisteminin sözdizimiyle: Windows %AD%, Linux $AD.
    ref = "%PDFTEST_ROOT%\\\\x" if os.name == "nt" else "$PDFTEST_ROOT/x"
    cfg = write(tmp_path / "c.toml", f'data_dir = "{ref}"\n')
    assert load_settings(cfg).data_dir == tmp_path / "x"


def test_unknown_key_is_an_error(tmp_path: Path):
    cfg = write(tmp_path / "c.toml", "prot = 9000\n")
    with pytest.raises(ValueError, match="prot"):
        load_settings(cfg)


def test_unknown_engine_key_is_an_error(tmp_path: Path):
    cfg = write(tmp_path / "c.toml", '[engines]\nword = "x"\n')
    with pytest.raises(ValueError, match="word"):
        load_settings(cfg)


def test_ensure_dirs(settings: Settings):
    settings.ensure_dirs()
    assert settings.files_dir.is_dir()
    assert settings.jobs_dir.is_dir()
    assert settings.logs_dir.is_dir()


def test_config_with_bom_is_read(tmp_path):
    """Not Defteri / PowerShell BOM'lu UTF-8 yazar; uygulama yine açılmalı (kurulum denemesinde
    BOM'lu config.toml uygulamayı açtırmadı)."""
    from toolia.settings import load_settings

    cfg = tmp_path / "config.toml"
    cfg.write_bytes("\ufeffport = 8800\nvault_path = 'C:/Kasa/Ödev'\n".encode())
    s = load_settings(cfg)
    assert s.port == 8800 and str(s.vault_path).endswith("Ödev")


# --- 0.12.0: veri klasörü PdfAtolye → Toolia ------------------------------------------------


def test_legacy_data_dir_is_used_until_moved_then_migrated(tmp_path, monkeypatch):
    from toolia import settings as s

    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    monkeypatch.delenv("TOOLIA_CONFIG", raising=False)
    old = tmp_path / "PdfAtolye"
    (old / "imzalar").mkdir(parents=True)
    (old / "imzalar" / "imza.png").write_bytes(b"x")
    assert s.default_data_dir() == old  # taşınmadan önce eski klasör: belgeler görünür
    assert s.migrate_on_startup(tmp_path / "config.toml") is False  # açık ayar: dokunma
    assert old.exists()
    assert s.migrate_on_startup(None) is True
    assert not old.exists()
    assert (tmp_path / "Toolia" / "imzalar" / "imza.png").read_bytes() == b"x"
    assert s.default_data_dir() == tmp_path / "Toolia"
    assert s.migrate_on_startup(None) is False  # ikinci kez: yapacak iş yok


def test_legacy_data_dir_kept_when_move_fails_or_new_exists(tmp_path, monkeypatch):
    from toolia import settings as s

    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    old = tmp_path / "PdfAtolye"
    old.mkdir()

    def locked(self, target):
        raise PermissionError("kilitli")

    monkeypatch.setattr(Path, "rename", locked)
    assert s.migrate_legacy_data_dir() is False
    assert s.default_data_dir() == old  # eski sürüm açıkken: eski klasörle devam
    monkeypatch.undo()
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    (tmp_path / "Toolia").mkdir()
    assert s.migrate_legacy_data_dir() is False  # iki klasör de varsa hiçbirine dokunma
    assert old.exists() and s.default_data_dir() == tmp_path / "Toolia"
