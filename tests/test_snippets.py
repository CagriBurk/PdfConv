"""Markdown → PDF kullanıcı şablonları: veri klasöründe `sablonlar/<ad>.md`."""

from __future__ import annotations

import os

import pytest
from fastapi.testclient import TestClient

from pdfatolye import snippets
from pdfatolye.api import app as app_module
from pdfatolye.settings import Settings

URL = "/api/md/snippets"


@pytest.fixture
def client(settings: Settings):
    with TestClient(app_module.create_app(settings, start_background=False)) as c:
        assert c.get("/api/session").status_code == 200
        yield c


def folder(settings: Settings):
    return settings.data_dir / snippets.DIR_NAME


def names(client: TestClient) -> list[str]:
    r = client.get(URL)
    assert r.status_code == 200, r.text
    return [s["name"] for s in r.json()["items"]]


def test_add_list_rename_overwrite_delete(client, settings):
    body = "> [!definition] Tanım\n> Süreklilik: $\\lim_{x\\to a} f(x) = f(a)$\n"
    r = client.post(URL, json={"name": "  Tanım   kutusu (ödev) ", "body": body})
    assert r.status_code == 200, r.text
    assert r.json()["name"] == "Tanım kutusu (ödev)"  # boşluklar sadeleşir, Türkçe harf serbest
    path = folder(settings) / "Tanım kutusu (ödev).md"
    assert path.read_text(encoding="utf-8") == body  # düz metin, elle de açılabilir

    listing = client.get(URL).json()
    assert listing["folder"] == str(folder(settings))
    assert listing["items"][0]["body"] == body

    r = client.put(f"{URL}/Tanım kutusu (ödev)", json={"new_name": "Tanım"})
    assert r.status_code == 200, r.text
    assert names(client) == ["Tanım"] and not path.exists()

    r = client.put(f"{URL}/Tanım", json={"body": "Yeni içerik\r\nikinci satır"})
    assert r.json()["body"] == "Yeni içerik\nikinci satır"
    assert (folder(settings) / "Tanım.md").read_bytes() == "Yeni içerik\nikinci satır".encode()

    r = client.delete(f"{URL}/Tanım")
    assert r.status_code == 200 and names(client) == []
    assert client.delete(f"{URL}/Tanım").status_code == 400  # zaten yok


def test_list_is_sorted_and_includes_files_dropped_by_hand(client, settings):
    d = folder(settings)
    d.mkdir(parents=True, exist_ok=True)
    (d / "Çizelge.md").write_bytes("| a |\n| --- |\n".encode("utf-8-sig"))  # BOM'lu
    (d / "eski not.md").write_bytes("Şöyle böyle: ığ".encode("cp1254"))  # Not Defteri ANSI
    (d / "resim.png").write_bytes(b"\x89PNG")  # .md değil
    (d / ".gizli.md").write_text("x", encoding="utf-8")
    client.post(URL, json={"name": "Ana", "body": "x"})
    items = client.get(URL).json()["items"]
    assert [s["name"] for s in items] == ["Ana", "Çizelge", "eski not"]
    assert items[1]["body"] == "| a |\n| --- |\n"
    assert items[2]["body"] == "Şöyle böyle: ığ"


@pytest.mark.parametrize(("name", "fragment"), [
    ("", "ad ver"),
    ("   ", "ad ver"),
    ("a" * 61, "en fazla 60"),
    ("../config", "kullanılamaz"),
    ("..\\..\\x", "kullanılamaz"),
    ("klasör/ad", "kullanılamaz"),
    ("C:ad", "kullanılamaz"),
    ("ne?", "kullanılamaz"),
    ("..", "nokta"),
    (".gizli", "nokta"),
    ("son.", "nokta"),
    ("CON", "ayrılmış"),
    ("nul.txt", "ayrılmış"),
    ("sekme\x01", "kullanılamaz"),
])
def test_bad_names_are_rejected(client, settings, name, fragment):
    r = client.post(URL, json={"name": name, "body": "x"})
    assert r.status_code == 400, r.text
    assert fragment in r.json()["detail"]
    # Klasörün dışında (veri klasöründe) hiçbir şey oluşmadı.
    assert not (settings.data_dir / "config.md").exists()
    assert [p.name for p in folder(settings).iterdir()] == []


def test_body_validation(client):
    r = client.post(URL, json={"name": "Boş", "body": " \n\t "})
    assert r.status_code == 400 and "boş olamaz" in r.json()["detail"]
    r = client.post(URL, json={"name": "Uzun", "body": "x" * (snippets.MAX_BODY_CHARS + 1)})
    assert r.status_code == 400 and "100.000 karakter" in r.json()["detail"]
    assert client.post(URL, json={"name": "Sınırda", "body": "ş" * snippets.MAX_BODY_CHARS}
                       ).status_code == 200


def test_name_conflicts_ignore_case(client):
    assert client.post(URL, json={"name": "Lab Raporu", "body": "x"}).status_code == 200
    r = client.post(URL, json={"name": "lab raporu", "body": "y"})
    assert r.status_code == 400 and "zaten var" in r.json()["detail"]
    client.post(URL, json={"name": "Sınav taktiği", "body": "y"})
    r = client.post(URL, json={"name": "SINAV TAKTİĞİ", "body": "y"})  # Türkçe büyük harf
    assert r.status_code == 400 and "'Sınav taktiği' adında" in r.json()["detail"]
    client.post(URL, json={"name": "Ödev", "body": "z"})
    r = client.put(f"{URL}/Ödev", json={"new_name": "LAB RAPORU"})
    assert r.status_code == 400 and "zaten var" in r.json()["detail"]
    # Yalnızca harf büyüklüğünü değiştirmek serbest (Windows'ta aynı dosya).
    r = client.put(f"{URL}/lab raporu", json={"new_name": "LAB raporu"})
    assert r.status_code == 200, r.text
    assert names(client) == ["LAB raporu", "Ödev", "Sınav taktiği"]


def test_count_limit(client, monkeypatch):
    monkeypatch.setattr(snippets, "MAX_COUNT", 2)
    for n in ("bir", "iki"):
        assert client.post(URL, json={"name": n, "body": "x"}).status_code == 200
    r = client.post(URL, json={"name": "üç", "body": "x"})
    assert r.status_code == 400 and "En fazla 2 şablon" in r.json()["detail"]


def test_path_params_cannot_escape_folder(client, settings):
    secret = settings.data_dir / "gizli.md"
    secret.write_text("gizli", encoding="utf-8")
    for bad in ("..%2Fgizli", "..%5Cgizli", "%2E%2E%2Fgizli", "..", "gizli"):
        assert client.delete(f"{URL}/{bad}").status_code >= 400
        assert client.put(f"{URL}/{bad}", json={"body": "ele geçirildi"}).status_code >= 400
    assert secret.read_text(encoding="utf-8") == "gizli"


def test_snippets_survive_retention_cleanup(client, settings):
    client.post(URL, json={"name": "Kalıcı", "body": "x"})
    path = folder(settings) / "Kalıcı.md"
    old = 1_000_000_000  # 2001: saklama süresinden çok eski
    os.utime(path, (old, old))
    app = client.app
    app.state.store.cleanup(0)
    app.state.jobs.cleanup(0)
    assert path.is_file() and names(client) == ["Kalıcı"]


def test_session_and_origin_are_required(settings):
    with TestClient(app_module.create_app(settings, start_background=False)) as anon:
        assert anon.get(URL).status_code == 403
        assert anon.post(URL, json={"name": "a", "body": "b"}).status_code == 403
        anon.get("/api/session")
        r = anon.post(URL, json={"name": "a", "body": "b"},
                      headers={"Origin": "http://kotu-site.example"})
        assert r.status_code == 403
    assert not folder(settings).exists() or not any(folder(settings).iterdir())


def test_paired_device_can_manage_snippets(settings):
    """Telefon modunda eşleşmiş cihaz (loopback dışı, geçerli çerezli) imzalar gibi şablonları da
    kaydedebilir: kullanıcının kendi içeriği, bilgisayarın ayarı değil."""
    app = app_module.create_app(settings, start_background=False)
    with TestClient(app, client=("192.168.1.50", 5000)) as phone:
        phone.cookies.set("pa_oturum", app.state.sessions.local)
        assert phone.post(URL, json={"name": "Telefondan", "body": "x"}).status_code == 200
        assert [s["name"] for s in phone.get(URL).json()["items"]] == ["Telefondan"]
