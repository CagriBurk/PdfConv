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


def pytest_runtest_logreport(report):
    """CI'da başarısız test GitHub "annotation" olarak da yazılır: iş günlükleri kimlik ister,
    açıklamalar kimliksiz okunabilir (check-runs/{id}/annotations)."""
    import os
    import sys

    if not os.environ.get("GITHUB_ACTIONS") or not report.failed:
        return
    text = str(report.longrepr)[-1500:].replace("%", "%25").replace("\r", "").replace("\n", "%0A")
    sys.__stdout__.write(f"::error title={report.nodeid}::{text}\n")
    sys.__stdout__.flush()
