import os
import sys
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


def _annotate(nodeid: str, text: str) -> None:
    """CI'da başarısızlık GitHub "annotation" olarak da yazılır: iş günlükleri kimlik ister,
    açıklamalar kimliksiz okunabilir (check-runs/{id}/annotations). Özellik değerinde `:` ve `,`
    kaçırılmalı (test kimliğindeki `::` komutu bölerdi)."""

    def esc(v: str, prop: bool = False) -> str:
        v = v.replace("%", "%25").replace("\r", "").replace("\n", "%0A")
        return v.replace(":", "%3A").replace(",", "%2C") if prop else v

    # Başta satır sonu: pytest ilerleme satırı ("....F") satır sonu olmadan biter; komut satır
    # başında olmalı, yoksa GitHub tanımaz.
    sys.__stdout__.write(f"\n::error title={esc(nodeid, True)}::{esc(text[-1500:])}\n")
    sys.__stdout__.flush()


def pytest_runtest_logreport(report):
    if os.environ.get("GITHUB_ACTIONS") and report.failed:
        _annotate(report.nodeid, str(report.longrepr))


def pytest_collectreport(report):
    if os.environ.get("GITHUB_ACTIONS") and report.failed:
        _annotate(report.nodeid or "toplama", str(report.longrepr))
