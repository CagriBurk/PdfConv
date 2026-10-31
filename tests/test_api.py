import pytest
from fastapi.testclient import TestClient

from pdfatolye import engines
from pdfatolye.api import app as app_module
from pdfatolye.settings import Settings


@pytest.fixture
def calls(monkeypatch: pytest.MonkeyPatch) -> list[int]:
    """Gerçek motor taramasını sahtesiyle değiştirir ve kaç kez çağrıldığını sayar."""
    counter: list[int] = []

    def fake_detect_all(_settings):
        counter.append(1)
        return [engines.EngineStatus(key="browser", name="Edge", available=True, needed_for="x")]

    monkeypatch.setattr(engines, "detect_all", fake_detect_all)
    return counter


@pytest.fixture
def client(settings: Settings, calls) -> TestClient:
    return TestClient(app_module.create_app(settings))


def test_health(client: TestClient):
    r = client.get("/api/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"


def test_engines_are_cached_until_refresh(client: TestClient, calls: list[int]):
    first = client.get("/api/engines").json()
    assert first["engines"][0]["ok"] is True
    assert "pymupdf" in first["libraries"]
    client.get("/api/engines")
    assert len(calls) == 1
    client.get("/api/engines?refresh=true")
    assert len(calls) == 2


def test_foreign_host_is_rejected(client: TestClient):
    # DNS rebinding: kötü niyetli bir alan adı 127.0.0.1'e yönlendirilse bile reddedilmeli.
    r = client.get("/api/health", headers={"host": "kotu-site.example"})
    assert r.status_code == 400


def test_unknown_api_path_is_404(client: TestClient):
    assert client.get("/api/yok").status_code == 404


def test_spa_fallback_serves_html(client: TestClient):
    r = client.get("/ayarlar")
    assert r.status_code == 200
    assert "text/html" in r.headers["content-type"]


def test_spa_does_not_serve_files_outside_dist(client: TestClient):
    r = client.get("/..%2F..%2Fpyproject.toml")
    assert "pdfatolye" not in r.text
