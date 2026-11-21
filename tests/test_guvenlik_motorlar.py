"""Güvenlik adım 6: motor bulma ve eski sürüm uyarısı (GUVENLIK_PLANI.md).

Kanıt: Python 3.11'de Windows'ta `shutil.which` önce çalışma klasörüne bakar; oraya bırakılmış
sahte `soffice.com` / `gswin64c.exe`, Program Files'taki gerçek LibreOffice / Ghostscript'in
önüne geçti. Motorlar artık yalnızca PATH'teki mutlak klasörlerde aranır.
"""

from __future__ import annotations

import os

import pytest

from toolia import engines
from toolia.settings import Settings


@pytest.fixture
def isolated(tmp_path, monkeypatch):
    """Boş PATH ve boş "Program Files": yalnızca testin koyduğu dosyalar bulunabilir."""
    empty = tmp_path / "bos"
    empty.mkdir()
    for var in ("ProgramFiles", "ProgramFiles(x86)", "LOCALAPPDATA"):
        monkeypatch.setenv(var, str(empty))
    monkeypatch.setenv("PATH", str(empty))
    monkeypatch.setattr(engines.paths, "engines_dir", lambda: None)
    return tmp_path


def _exe(path):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"MZ")
    path.chmod(0o755)
    return path


@pytest.mark.skipif(os.name != "nt", reason="çalışma klasörü önceliği Windows'a özgü")
def test_planted_engine_in_working_directory_is_ignored(isolated, monkeypatch):
    work = isolated / "indirilenler"
    _exe(work / "soffice.com")
    _exe(work / "gswin64c.exe")
    _exe(work / "winget.exe")
    monkeypatch.chdir(work)
    assert engines.detect_libreoffice(Settings()).path is None
    assert engines.detect_ghostscript(Settings()).path is None
    assert engines.find_on_path("winget") is None


def test_relative_path_entries_are_skipped(isolated, monkeypatch):
    work = isolated / "calisma"
    name = "soffice.com" if os.name == "nt" else "soffice"
    _exe(work / name)
    monkeypatch.chdir(work)
    monkeypatch.setenv("PATH", os.pathsep.join([".", "", "calisma"]))
    assert engines.find_on_path(name) is None


def test_engine_on_path_is_still_found(isolated, monkeypatch):
    bin_dir = isolated / "LibreOffice" / "program"
    name = "soffice.com" if os.name == "nt" else "soffice"
    exe = _exe(bin_dir / name)
    monkeypatch.setenv("PATH", str(bin_dir))
    assert engines.find_on_path(name) == exe
    if os.name == "nt":
        assert engines.find_on_path("soffice") == exe  # PATHEXT ile uzantısız ad


@pytest.mark.parametrize(("version", "warns"), [("24.8.7.2", True), ("25.8.4.2", True),
                                                ("26.2.0.3", False), ("26.8.2.2", False),
                                                (None, False)])
def test_old_libreoffice_warns_but_stays_usable(isolated, monkeypatch, version, warns):
    exe = _exe(isolated / "lo" / "soffice.com")
    monkeypatch.setattr(engines, "_file_version", lambda p: version)
    s = Settings()
    s.engines.libreoffice = str(exe)
    st = engines.detect_libreoffice(s)
    assert st.available and st.ok  # uyarı motoru "eksik" yapmaz
    assert bool(st.warnings) is warns
    d = st.to_dict()
    assert d["ok"] is True and "warnings" not in d
    assert (any("güvenlik güncellemesi" in p for p in d["problems"])) is warns


@pytest.mark.parametrize(("out", "warns"), [("10.05.1\n", True), ("9.56.1\n", True),
                                            ("10.06.0\n", False), ("10.08.0\n", False)])
def test_old_ghostscript_warns(isolated, monkeypatch, out, warns):
    exe = _exe(isolated / "gs" / "gswin64c.exe")
    monkeypatch.setattr(engines, "_run", lambda args: out)
    s = Settings()
    s.engines.ghostscript = str(exe)
    st = engines.detect_ghostscript(s)
    assert st.ok and bool(st.warnings) is warns
