"""Güvenlik adım 1: Gönder menüsünde dosya adıyla komut çalıştırma (GUVENLIK_PLANI.md).

Gezgin, Gönder menüsündeki kısayola seçili dosyaların yollarını boşluk yoksa TIRNAKSIZ verir.
Eski kısayol bir .cmd çalıştırıyordu; cmd.exe `deneme&calc&.pdf` adındaki `&`'den sonrasını ayrı
komut olarak çalıştırdı (kullanıcının denemesinde hesap makinesi açıldı). Yeni kısayol doğrudan
python.exe'yi çalıştırır: yollar cmd'den geçmez.

Testler Gezgin'in davranışını taklit eder: komut satırı tırnaksız yolla, kabuk OLMADAN
(CreateProcess) verilir. Zararsız yük: `mkdir,isaret` (virgül cmd'de boşluk yerine geçer).
`isaret` klasörü oluşursa komut çalışmış demektir.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest
from PIL import Image

from toolia import gonder_menu

pytestmark = pytest.mark.skipif(os.name != "nt", reason="cmd.exe / Gezgin davranışı Windows'a özgü")

PAYLOAD_NAME = "resim&mkdir,isaret&.png"


def _png(path: Path) -> Path:
    Image.new("RGB", (8, 8), "red").save(path)
    return path


def _no_spaces(path: Path) -> Path:
    if " " in str(path):
        pytest.skip("geçici klasör yolu boşluk içeriyor: Gezgin tırnaklardı, deneme anlamsız")
    return path


def _env() -> dict[str, str]:
    env = {k: v for k, v in os.environ.items() if not k.upper().startswith("PYTHON")}
    env["TOOLIA_GONDER_BEKLEME"] = "0"
    return env


def test_old_cmd_launcher_pattern_was_injectable(tmp_path):
    """Kontrol: eski .cmd düzeni bu yükle gerçekten komut çalıştırır. Böylece aşağıdaki test
    "komut çalışmadı" dediğinde bunun düzeltmeden olduğu bilinir, yükün bozukluğundan değil."""
    work = _no_spaces(tmp_path)
    src = _png(work / PAYLOAD_NAME)
    launcher = work / "eski-cevir.cmd"
    launcher.write_bytes(b'@echo off\r\n"' + sys.executable.encode("mbcs")
                         + b'" -c "import sys" %*\r\n')
    # ShellExecute bir .cmd'yi `cmd /c ""betik" argümanlar"` ile çalıştırır
    subprocess.run(f'cmd /d /c ""{launcher}" {src}"', cwd=work, env=_env(),
                   stdin=subprocess.DEVNULL, capture_output=True, timeout=60)
    assert (work / "isaret").is_dir()


def test_sendto_command_line_does_not_run_commands(tmp_path):
    """Gönder → JPG'ye çevir: kısayolun komut satırı + Gezgin'in tırnaksız yolu."""
    work = _no_spaces(tmp_path)
    src = _png(work / PAYLOAD_NAME)
    cmdline = f'"{sys.executable}" -I -m toolia.gonder_menu jpg {src}'  # tırnaksız, Gezgin gibi
    done = subprocess.run(cmdline, cwd=work, env=_env(), stdin=subprocess.DEVNULL,
                          capture_output=True, timeout=120)
    assert not (work / "isaret").exists(), "dosya adındaki komut çalıştı"
    assert done.returncode == 0, done.stderr.decode("utf-8", "replace")
    outputs = list(work.glob("*.jpg"))
    assert len(outputs) == 1 and "&mkdir,isaret&" in outputs[0].name  # dosya adı bozulmadan


@pytest.mark.parametrize("name", ["a%PATH%.png", "a^b.png", "a!x!.png", "a,b;c.png",
                                  "a&b.png"])
def test_sendto_keeps_special_characters_in_names(tmp_path, name):
    work = _no_spaces(tmp_path)
    src = _png(work / name)
    done = subprocess.run(f'"{sys.executable}" -I -m toolia.gonder_menu jpg {src}', cwd=work,
                          env=_env(), stdin=subprocess.DEVNULL, capture_output=True,
                          timeout=120)
    assert done.returncode == 0, done.stderr.decode("utf-8", "replace")
    assert [p.stem for p in work.glob("*.jpg")] == [Path(name).stem]


def test_dash_file_name_is_not_an_option(tmp_path, monkeypatch):
    """Dosyalardan önce `--`: `-` ile başlayan dosya adı seçenek olarak okunmaz."""
    monkeypatch.chdir(tmp_path)
    _png(tmp_path / "--hedef=png.png")
    assert gonder_menu.cli_args("jpg", ["--hedef=png.png"]) == [
        "donustur", "--hedef", "jpg", "--", "--hedef=png.png"]
    assert gonder_menu.run(["jpg", "--hedef=png.png"]) == 0
    assert (tmp_path / "--hedef=png.jpg").is_file()


def test_usage_error_returns_nonzero_without_crashing(tmp_path):
    assert gonder_menu.run([]) == 2
    assert gonder_menu.run(["exe", "x"]) == 2
    assert gonder_menu.run(["jpg", str(tmp_path / "yok.png")]) != 0
