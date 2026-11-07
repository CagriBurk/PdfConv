"""Masaüstü kurulumu ve kaldırma. Paketteki `Kur.cmd` / kurulu klasördeki `Kaldir.cmd` çağırır:

    <paket>\\python\\python.exe -I -m pdfatolye.kurulum kur
    <kurulum>\\python\\python.exe -I -m pdfatolye.kurulum kaldir

Neden bir kurulum programı (.exe) değil: Windows Akıllı Uygulama Denetimi (Smart App Control)
internetten indirilmiş, imzasız .exe dosyalarını engelliyor (PLAN.md tuzak #52). Paket yalnızca
imzalı python.org Python'unu çalıştırır; geri kalan her şey Python kodu.

Kurulum yönetici izni istemez: `%LOCALAPPDATA%\\Programs\\PdfAtolyesi`, masaüstü ve Başlat menüsü
kısayolu, Gönder menüsünde "PDF'e çevir", "Uygulamalar"da kaldırma kaydı. Kopyalama `shutil` ile
yapılır: indirilen dosyalardaki "internetten geldi" işareti (Zone.Identifier akışı) kopyaya
taşınmaz. Kullanıcı verisi (`%LOCALAPPDATA%\\PdfAtolye`) kuruluma dokunulmadan kalır; kaldırırken
silinip silinmeyeceği sorulur.
"""

from __future__ import annotations

import base64
import contextlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

APP_NAME = "PDF Atölyesi"
DIR_NAME = "PdfAtolyesi"
UNINSTALL_KEY = r"Software\Microsoft\Windows\CurrentVersion\Uninstall\PdfAtolyesi"
MARKER = "pdfatolye-kurulum.json"
NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)
DETACHED = 0x00000008 | 0x00000200  # DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP
BREAKAWAY = 0x01000000


def default_target() -> Path:
    return Path(os.environ["LOCALAPPDATA"]) / "Programs" / DIR_NAME


def package_root() -> Path:
    """Çalışan Python'un ait olduğu paket/kurulum kökü (python\\python.exe → kök)."""
    return Path(sys.executable).resolve().parent.parent


def spawn_detached(args: list[str], **kw) -> None:
    """Bağımsız süreç: bizim süreç (ve varsa iş nesnemiz) kapanınca kapanmasın. Üst süreç
    ayrılmaya izin vermeyen bir iş nesnesindeyse (bazı terminaller) bayraksız yeniden dener."""
    try:
        subprocess.Popen(args, creationflags=DETACHED | BREAKAWAY | NO_WINDOW, **kw)
    except OSError:
        subprocess.Popen(args, creationflags=DETACHED | NO_WINDOW, **kw)


def _say(text: str = "") -> None:
    print(text, flush=True)


def _ask(question: str) -> bool:
    try:
        answer = input(f"{question} (E/H): ").strip().casefold()
    except EOFError:
        return False
    return answer in ("e", "evet", "y", "yes")


# --- kısayollar (WScript.Shell; PowerShell betiği base64 ile, tırnak sorunu olmasın) ---------

def _powershell(script: str) -> None:
    encoded = base64.b64encode(script.encode("utf-16-le")).decode("ascii")
    subprocess.run(["powershell", "-NoProfile", "-NonInteractive", "-EncodedCommand", encoded],
                   check=True, creationflags=NO_WINDOW, capture_output=True)


def _ps_str(value: str | Path) -> str:
    return "'" + str(value).replace("'", "''") + "'"


def shortcut_paths() -> dict[str, Path]:
    import ctypes
    from ctypes import wintypes

    def known(csidl: int) -> Path:
        buf = ctypes.create_unicode_buffer(wintypes.MAX_PATH)
        ctypes.windll.shell32.SHGetFolderPathW(None, csidl, None, 0, buf)
        return Path(buf.value)

    # 0x10 masaüstü, 0x02 Başlat menüsü\Programlar, 0x09 Gönder (SendTo)
    return {"masaustu": known(0x10) / f"{APP_NAME}.lnk",
            "baslat": known(0x02) / f"{APP_NAME}.lnk",
            "gonder": known(0x09) / "PDF'e çevir.lnk"}


def create_shortcuts(target: Path) -> None:
    pyw = target / "python" / "pythonw.exe"
    icon = target / "simgeler" / "pdfatolye.ico"
    links = shortcut_paths()
    lines = ["$s = New-Object -ComObject WScript.Shell"]
    for key in ("masaustu", "baslat"):
        lines += [f"$l = $s.CreateShortcut({_ps_str(links[key])})",
                  f"$l.TargetPath = {_ps_str(pyw)}",
                  "$l.Arguments = '-I -m pdfatolye uygulama'",
                  f"$l.WorkingDirectory = {_ps_str(target)}",
                  f"$l.IconLocation = {_ps_str(str(icon) + ',0')}",
                  "$l.Description = 'PDF Atölyesi: çevrimdışı PDF araç seti'",
                  "$l.Save()"]
    lines += [f"$l = $s.CreateShortcut({_ps_str(links['gonder'])})",
              f"$l.TargetPath = {_ps_str(target / 'pdfe-cevir.cmd')}",
              f"$l.WorkingDirectory = {_ps_str(target)}",
              f"$l.IconLocation = {_ps_str(str(icon) + ',0')}",
              "$l.WindowStyle = 7",
              "$l.Description = 'Seçili dosyaları PDF Atölyesi ile PDF''e çevirir'",
              "$l.Save()"]
    _powershell("\n".join(lines))


def remove_shortcuts() -> None:
    for path in shortcut_paths().values():
        path.unlink(missing_ok=True)


# --- kaldırma kaydı ---------------------------------------------------------------------------

def register_uninstall(target: Path, version: str) -> None:
    import winreg

    size_kb = sum(f.stat().st_size for f in target.rglob("*") if f.is_file()) // 1024
    with winreg.CreateKey(winreg.HKEY_CURRENT_USER, UNINSTALL_KEY) as key:
        values = {
            "DisplayName": APP_NAME,
            "DisplayVersion": version,
            "Publisher": "PDF Atölyesi",
            "InstallLocation": str(target),
            "DisplayIcon": str(target / "simgeler" / "pdfatolye.ico"),
            "UninstallString": f'"{target / "Kaldir.cmd"}"',
            "URLInfoAbout": "https://github.com/CagriBurk/PdfConv",
        }
        for name, value in values.items():
            winreg.SetValueEx(key, name, 0, winreg.REG_SZ, value)
        for name, value in {"NoModify": 1, "NoRepair": 1, "EstimatedSize": size_kb}.items():
            winreg.SetValueEx(key, name, 0, winreg.REG_DWORD, value)


def unregister_uninstall() -> None:
    import winreg

    with contextlib.suppress(FileNotFoundError):
        winreg.DeleteKey(winreg.HKEY_CURRENT_USER, UNINSTALL_KEY)


# --- çalışan uygulama -------------------------------------------------------------------------

def _running_app(target: Path) -> bool:
    """Kurulu klasörden çalışan bir uygulama var mı (dosyalar kilitli olur)?"""
    import psutil

    for p in psutil.process_iter(["exe"]):
        try:
            exe = p.info["exe"]
            inside = exe and Path(exe).resolve().is_relative_to(target.resolve())
            if inside and p.pid != os.getpid():
                return True
        except (psutil.Error, OSError, ValueError):
            continue
    return False


# --- kur / kaldır -----------------------------------------------------------------------------

def install(source: Path, target: Path, *, launch: bool = True, shortcuts: bool = True) -> int:
    info = json.loads((source / MARKER).read_text(encoding="utf-8"))
    version = info.get("version", "?")
    _say(f"{APP_NAME} {version} kuruluyor → {target}")
    if source.resolve() == target.resolve():
        _say("Paket zaten kurulu klasörde; yalnızca kısayollar yenileniyor.")
    else:
        if target.exists():
            if _running_app(target):
                _say("Uygulama açık. Pencereyi kapatıp kurulumu yeniden çalıştır.")
                return 1
            _say("Önceki sürüm kaldırılıyor (belgelerin ve ayarların korunur)...")
            shutil.rmtree(target)
        _say("Dosyalar kopyalanıyor (bir iki dakika sürebilir)...")
        shutil.copytree(source, target, copy_function=shutil.copyfile)
    marker = info | {"installed": time.time(), "source": str(source)}
    (target / MARKER).write_text(json.dumps(marker, ensure_ascii=False, indent=1),
                                 encoding="utf-8")
    if shortcuts:
        _say("Kısayollar oluşturuluyor...")
        create_shortcuts(target)
        register_uninstall(target, version)
    _say("Kurulum tamam. Masaüstündeki \"PDF Atölyesi\" simgesiyle açabilirsin.")
    if launch:
        spawn_detached([str(target / "python" / "pythonw.exe"), "-I", "-m", "pdfatolye",
                        "uygulama"], cwd=target)
    return 0


def uninstall(target: Path, *, assume_yes: bool = False, remove_data: bool | None = None,
              data_dir: Path | None = None) -> int:
    """`data_dir` verilmezse ayarlardaki veri klasörü (kullanıcıya sorulur)."""
    from pdfatolye.settings import load_settings

    if not assume_yes and not _ask(f"{APP_NAME} kaldırılsın mı?"):
        _say("Vazgeçildi.")
        return 1
    if _running_app(target):
        _say("Uygulama açık. Pencereyi kapatıp yeniden dene.")
        return 1
    data_dir = Path(data_dir) if data_dir is not None else load_settings().data_dir
    if remove_data is None:
        remove_data = _ask(f"Belgelerin, imzaların ve ayarların da silinsin mi? ({data_dir})")
    remove_shortcuts()
    unregister_uninstall()
    if remove_data:
        shutil.rmtree(data_dir, ignore_errors=True)
        _say("Veriler silindi.")
    else:
        _say(f"Veriler korundu: {data_dir}")
    # Çalışan python.exe kurulum klasöründe: klasörü, bu süreç çıktıktan sonra ayrı bir
    # komut penceresi siler.
    script = Path(tempfile.gettempdir()) / "pdfatolye-kaldir.cmd"
    script.write_text(
        "@echo off\r\n"
        f"timeout /t 2 /nobreak >nul\r\nrmdir /s /q \"{target}\"\r\n"
        "del \"%~f0\"\r\n", encoding="mbcs")
    spawn_detached(["cmd", "/c", str(script)])
    _say(f"{APP_NAME} kaldırıldı.")
    return 0


def main(argv: list[str]) -> int:
    if not argv or argv[0] not in ("kur", "kaldir"):
        _say("Kullanım: python -m pdfatolye.kurulum kur [hedef] | kaldir")
        return 2
    try:
        if argv[0] == "kur":
            target = Path(argv[1]) if len(argv) > 1 else default_target()
            return install(package_root(), target)
        return uninstall(package_root())
    except Exception as e:  # kullanıcı konsolda okusun; yığın izi değil
        _say(f"Hata: {type(e).__name__}: {e}")
        return 1


if __name__ == "__main__":
    code = main(sys.argv[1:])
    if os.environ.get("PDFATOLYE_KURULUM_BEKLEME") != "0":
        input("\nKapatmak için Enter'a bas...")
    sys.exit(code)
