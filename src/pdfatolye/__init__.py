"""PDF Atölyesi: yerel, çevrimdışı PDF araç seti."""

from importlib.metadata import PackageNotFoundError, version


def _version() -> str:
    """Tek kaynak `pyproject.toml`: kurulu paketin meta verisinden okunur (uv run da paketi
    kurar). Meta veri yoksa (kaynaktan doğrudan çalıştırma) pyproject'ten okunur."""
    try:
        return version("pdfatolye")
    except PackageNotFoundError:
        import tomllib
        from pathlib import Path

        pyproject = Path(__file__).resolve().parents[2] / "pyproject.toml"
        try:
            return tomllib.loads(pyproject.read_text(encoding="utf-8"))["project"]["version"]
        except (OSError, KeyError, ValueError):
            return "0.0.0"


__version__ = _version()
