import sys
from pathlib import Path

import pytest

from pdfatolye import engines
from pdfatolye.settings import EnginePaths, Settings


def test_detect_all_reports_every_engine(settings: Settings):
    keys = [e.key for e in engines.detect_all(settings)]
    assert keys == ["libreoffice", "browser", "tesseract", "ghostscript"]


def test_missing_override_path_means_unavailable(tmp_path: Path):
    s = Settings(engines=EnginePaths(libreoffice=str(tmp_path / "yok.exe")))
    status = engines.detect_libreoffice(s)
    assert not status.available
    assert not status.ok
    assert status.install_hint


def test_tesseract_missing_language_is_a_problem(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    exe = tmp_path / "tesseract.exe"
    exe.write_bytes(b"")
    outputs = {
        "--version": "tesseract v5.4.0.20240606\n leptonica-1.84.1\n",
        "--list-langs": 'List of available languages in "C:\\tessdata/" (2):\neng\nosd\n',
    }
    monkeypatch.setattr(engines, "_run", lambda args: outputs[args[1]])

    status = engines.detect_tesseract(Settings(engines=EnginePaths(tesseract=str(exe))))
    assert status.available
    assert status.version == "5.4.0.20240606"
    assert status.problems == ["Eksik dil paketi: tur"]
    assert not status.ok
    assert status.to_dict()["ok"] is False


def test_tesseract_with_all_languages_is_ok(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    exe = tmp_path / "tesseract.exe"
    exe.write_bytes(b"")
    outputs = {
        "--version": "tesseract 5.5.0\n",
        "--list-langs": "List of available languages (3):\neng\nosd\ntur\n",
    }
    monkeypatch.setattr(engines, "_run", lambda args: outputs[args[1]])
    status = engines.detect_tesseract(Settings(engines=EnginePaths(tesseract=str(exe))))
    assert status.ok


@pytest.mark.skipif(sys.platform != "win32", reason="Windows sürüm kaynağı")
def test_file_version_reads_windows_exe():
    version = engines._file_version(Path(sys.executable))
    assert version is not None
    assert version.count(".") == 3


def test_python_libraries_are_installed():
    libs = engines.python_libraries()
    assert libs["pymupdf"]
    assert libs["pikepdf"]
