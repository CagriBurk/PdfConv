from pathlib import Path

import pytest

from pdfatolye.settings import Settings


@pytest.fixture
def settings(tmp_path: Path) -> Settings:
    # TestClient "testserver" Host başlığıyla istek atar.
    return Settings(
        data_dir=tmp_path / "data",
        allowed_hosts=["127.0.0.1", "localhost", "testserver"],
    )
