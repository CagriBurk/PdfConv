"""Masaüstü kurulumu ve kaldırma. Paketteki `Kur.cmd` / kurulu klasördeki `Kaldir.cmd` çağırır:

    <paket>\\python\\python.exe -I -m toolia.kurulum kur
    <kurulum>\\python\\python.exe -I -m toolia.kurulum kaldir

Neden bir kurulum programı (.exe) değil: Windows Akıllı Uygulama Denetimi (Smart App Control)
internetten indirilmiş, imzasız .exe dosyalarını engelliyor (PLAN.md tuzak #52). Paket yalnızca
imzalı python.org Python'unu çalıştırır; geri kalan her şey Python kodu.

Kurulum yönetici izni istemez: `%LOCALAPPDATA%\\Programs\\Toolia`, masaüstü ve Başlat menüsü
kısayolu, Gönder menüsünde "PDF'e çevir" ve "JPG'ye çevir", "Uygulamalar"da kaldırma kaydı.
Kısayollar her kurulumda yeniden yazılır (eski sürümün üzerine kurunca yenileri de gelir); kaldırma
`shortcut_paths()`'teki hepsini siler. Kopyalama `shutil` ile
yapılır: indirilen dosyalardaki "internetten geldi" işareti (Zone.Identifier akışı) kopyaya
taşınmaz. Kullanıcı verisi (`%LOCALAPPDATA%\\Toolia`) kuruluma dokunulmadan kalır; kaldırırken
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

APP_NAME = "Toolia"
OLD_APP_NAME = "PDF Atölyesi"  # 0.12.0'dan önceki görünen ad (eski kısayolları silmek için)
DIR_NAME = "Toolia"
UNINSTALL_KEY = r"Software\Microsoft\Windows\CurrentVersion\Uninstall\Toolia"
MARKER = "toolia-kurulum.json"
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
    # PowerShell 7'den devralınan PSModulePath Windows PowerShell'in modüllerini bozar.
    env = {k: v for k, v in os.environ.items() if k.upper() != "PSMODULEPATH"}
    subprocess.run(["powershell", "-NoProfile", "-NonInteractive", "-EncodedCommand", encoded],
                   check=True, creationflags=NO_WINDOW, capture_output=True, env=env)


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
    desktop, start, sendto = known(0x10), known(0x02), known(0x09)
    return {"masaustu": desktop / f"{APP_NAME}.lnk",
            "baslat": start / f"{APP_NAME}.lnk",
            "gonder": sendto / "PDF'e çevir.lnk",
            "gonder_jpg": sendto / "JPG'ye çevir.lnk",
            # 0.12.0'a kadarki ad: güncellemede ve kaldırmada silinir (iki simge kalmasın).
            "eski_masaustu": desktop / f"{OLD_APP_NAME}.lnk",
            "eski_baslat": start / f"{OLD_APP_NAME}.lnk"}


# Gönder menüsü kısayolları: anahtar → (paketteki başlatıcı, açıklama)
SENDTO_LAUNCHERS = {
    "gonder": ("pdfe-cevir.cmd", "Seçili dosyaları Toolia ile PDF'e çevirir"),
    "gonder_jpg": ("jpge-cevir.cmd", "Seçili resimleri JPG'ye çevirir"),
}


def create_shortcuts(target: Path) -> None:
    """Her kurulumda (güncelleme dahil) baştan yazılır: eski sürümün üzerine kurulunca yeni
    eklenen kısayollar da oluşur, eski addaki kısayollar silinir."""
    pyw = target / "python" / "pythonw.exe"
    icon = target / "simgeler" / "toolia.ico"
    links = shortcut_paths()
    for key, path in links.items():
        if key.startswith("eski_"):
            path.unlink(missing_ok=True)
    lines = ["$s = New-Object -ComObject WScript.Shell"]
    for key in ("masaustu", "baslat"):
        lines += [f"$l = $s.CreateShortcut({_ps_str(links[key])})",
                  f"$l.TargetPath = {_ps_str(pyw)}",
                  "$l.Arguments = '-I -m toolia uygulama'",
                  f"$l.WorkingDirectory = {_ps_str(target)}",
                  f"$l.IconLocation = {_ps_str(str(icon) + ',0')}",
                  "$l.Description = 'Toolia: çevrimdışı PDF ve dosya araçları'",
                  "$l.Save()"]
    for key, (launcher, description) in SENDTO_LAUNCHERS.items():
        lines += [f"$l = $s.CreateShortcut({_ps_str(links[key])})",
                  f"$l.TargetPath = {_ps_str(target / launcher)}",
                  f"$l.WorkingDirectory = {_ps_str(target)}",
                  f"$l.IconLocation = {_ps_str(str(icon) + ',0')}",
                  "$l.WindowStyle = 7",
                  f"$l.Description = {_ps_str(description)}",
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
            "Publisher": "Toolia",
            "InstallLocation": str(target),
            "DisplayIcon": str(target / "simgeler" / "toolia.ico"),
            "UninstallString": f'"{target / "Kaldir.cmd"}"',
            "URLInfoAbout": "https://github.com/CagriBurk/PdfConv",
        }
        for name, value in values.items():
            winreg.SetValueEx(key, name, 0, winreg.REG_SZ, value)
        for name, value in {"NoModify": 1, "NoRepair": 1, "EstimatedSize": size_kb}.items():
            winreg.SetValueEx(key, name, 0, winreg.REG_DWORD, value)


def unregister_uninstall(key: str = UNINSTALL_KEY) -> None:
    import winreg

    with contextlib.suppress(FileNotFoundError):
        winreg.DeleteKey(winreg.HKEY_CURRENT_USER, key)


# --- 0.12.0 öncesi kurulum (PDF Atölyesi) ----------------------------------------------------

LEGACY_DIR_NAME = "PdfAtolyesi"
LEGACY_MARKER = "pdfatolye-kurulum.json"
LEGACY_UNINSTALL_KEY = r"Software\Microsoft\Windows\CurrentVersion\Uninstall\PdfAtolyesi"


def legacy_install(target: Path) -> Path | None:
    """Yeni kurulumun yanındaki eski "PDF Atölyesi" kurulumu. Yalnız kendi işaret dosyasını
    taşıyan klasör sayılır: başka bir klasör asla silinmez."""
    old = target.parent / LEGACY_DIR_NAME
    return old if (old / LEGACY_MARKER).is_file() else None


def remove_legacy_install(old: Path) -> None:
    """Eski kurulum klasörünü ve "Uygulamalar" kaydını kaldırır. Kullanıcı verisine
    (veri klasörü) dokunmaz; o, uygulama ilk açıldığında yeni ada taşınır."""
    shutil.rmtree(old, ignore_errors=True)
    if old.exists():
        _say(f"Eski kurulum klasörü tamamen silinemedi, elle silebilirsin: {old}")
    unregister_uninstall(LEGACY_UNINSTALL_KEY)


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
    old = legacy_install(target)
    if old is not None and _running_app(old):
        _say("Eski sürüm (PDF Atölyesi) açık. Pencereyi kapatıp kurulumu yeniden çalıştır.")
        return 1
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
        if old is not None:
            _say("Eski sürüm (PDF Atölyesi) kaldırılıyor (belgelerin korunur)...")
            remove_legacy_install(old)
    _say("Kurulum tamam. Masaüstündeki \"Toolia\" simgesiyle açabilirsin.")
    if launch:
        spawn_detached([str(target / "python" / "pythonw.exe"), "-I", "-m", "toolia",
                        "uygulama"], cwd=target)
    return 0


def uninstall(target: Path, *, assume_yes: bool = False, remove_data: bool | None = None,
              data_dir: Path | None = None) -> int:
    """`data_dir` verilmezse ayarlardaki veri klasörü (kullanıcıya sorulur)."""
    from toolia.settings import load_settings

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
    script = Path(tempfile.gettempdir()) / "toolia-kaldir.cmd"
    script.write_text(
        "@echo off\r\n"
        f"timeout /t 2 /nobreak >nul\r\nrmdir /s /q \"{target}\"\r\n"
        "del \"%~f0\"\r\n", encoding="mbcs")
    spawn_detached(["cmd", "/c", str(script)])
    _say(f"{APP_NAME} kaldırıldı.")
    return 0


def main(argv: list[str]) -> int:
    if not argv or argv[0] not in ("kur", "kaldir"):
        _say("Kullanım: python -m toolia.kurulum kur [hedef] | kaldir")
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
    # Çıktı bir boruya/dosyaya giderse Windows kod sayfası (cp1252/cp857) "→", "ğ" yazamaz.
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")
    code = main(sys.argv[1:])
    if os.environ.get("TOOLIA_KURULUM_BEKLEME") != "0":
        input("\nKapatmak için Enter'a bas...")
    sys.exit(code)
