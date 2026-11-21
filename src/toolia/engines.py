"""Dış araçları (LibreOffice, Tesseract, Ghostscript, Edge/Chrome) bulur ve raporlar.

Her motor için: ayardaki yol → uygulamayla gelen motor (kurulumun `motorlar/` klasörü) → PATH →
bilinen Windows kurulum klasörleri sırasıyla aranır.
Sürüm bilgisi mümkünse .exe'nin sürüm kaynağından okunur; LibreOffice'i sırf sürüm için
başlatmak birkaç saniye sürdüğü için onu çalıştırmayız.
"""

from __future__ import annotations

import glob
import os
import re
import subprocess
from dataclasses import asdict, dataclass, field
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path

from toolia import paths
from toolia.settings import Settings

# İlk çalıştırmada Windows Defender taraması birkaç saniye sürebiliyor.
SUBPROCESS_TIMEOUT = 20
REQUIRED_OCR_LANGS = ("tur", "eng")

# Bunlardan eski sürümler güvenlik güncellemesi almıyor ya da bilinen açıklar içeriyor; motor
# çalışır ama Ayarlar'da uyarı çıkar (GUVENLIK_PLANI.md, adım 6). Ghostscript 10.06.0 Eylül
# 2025'te birkaç bellek bozulması açığını (CVE-2025-59798…59801) kapattı. LibreOffice'in her
# sürüm dalı ~9 ay güncellenir; 2026 sonunda desteklenen en eski dal 26.2.
MIN_GHOSTSCRIPT = (10, 6, 0)
MIN_LIBREOFFICE = (26, 2)


@dataclass
class EngineStatus:
    key: str
    name: str
    available: bool
    needed_for: str
    path: str | None = None
    version: str | None = None
    problems: list[str] = field(default_factory=list)  # motor kullanılamaz ("hazır değil")
    install_hint: str | None = None
    warnings: list[str] = field(default_factory=list)  # çalışır ama dikkat (ör. eski sürüm)

    @property
    def ok(self) -> bool:
        return self.available and not self.problems

    def to_dict(self) -> dict:
        d = asdict(self)
        # Arayüz sorunları ve uyarıları aynı satırlarda gösterir; uyarı motoru "eksik" yapmaz.
        d["problems"] = d["problems"] + d.pop("warnings")
        return d | {"ok": self.ok}


def _program_files() -> list[Path]:
    dirs = []
    for var in ("ProgramFiles", "ProgramFiles(x86)", "LOCALAPPDATA"):
        if value := os.environ.get(var):
            dirs.append(Path(value))
    return dirs


def on_windows() -> bool:
    return os.name == "nt"


def _hint(windows: str, linux: str) -> str:
    """Eksik motor için kurulum ipucu (Linux'ta Debian/Ubuntu paket adları)."""
    return windows if on_windows() else linux


def _bundled(*rel: str) -> list[Path]:
    """Kurulumla gelen motorun olası yerleri (geliştirmede boş)."""
    root = paths.engines_dir()
    return [root / r for r in rel] if root else []


def find_on_path(name: str) -> Path | None:
    """PATH'te arar ama `shutil.which`'ten farklı olarak ÇALIŞMA KLASÖRÜNE BAKMAZ. Windows'ta
    `shutil.which` (Python 3.11) önce o anki klasörü dener: komut satırı İndirilenler'de
    çalışırken oraya bırakılmış sahte bir `soffice.com` gerçek LibreOffice'in önüne geçiyordu
    (GUVENLIK_PLANI.md, adım 6). Göreli PATH girdileri de (`.`) atlanır."""
    exts = [""]
    if os.name == "nt" and not Path(name).suffix:
        exts = [e.lower() for e in os.environ.get("PATHEXT", ".COM;.EXE;.BAT;.CMD").split(";")
                if e]
    for entry in os.environ.get("PATH", "").split(os.pathsep):
        entry = entry.strip().strip('"')
        if not entry or not os.path.isabs(entry):
            continue
        for ext in exts:
            candidate = Path(entry) / (name + ext)
            if candidate.is_file() and (os.name == "nt" or os.access(candidate, os.X_OK)):
                return candidate
    return None


def _version_tuple(text: str | None) -> tuple[int, ...] | None:
    m = re.match(r"\s*(\d+(?:\.\d+)*)", text or "")
    return tuple(int(x) for x in m.group(1).split(".")) if m else None


def _find_executable(override: str, names: list[str], relative_paths: list[str],
                     bundled: list[Path] | None = None) -> Path | None:
    if override:
        p = Path(override)
        return p if p.is_file() else None
    for p in bundled or []:
        if p.is_file():
            return p
    for name in names:
        if found := find_on_path(name):
            return found
    # Önce yol sırası: listede önde olan (ör. Edge) hangi klasörde olursa olsun kazanır.
    for rel in relative_paths:
        for base in _program_files():
            # Sürüm numaralı klasörler (gs\gs10.04.0\bin) için glob; en yeni sürüm önce.
            matches = sorted(glob.glob(str(base / rel)), reverse=True)
            for m in matches:
                if Path(m).is_file():
                    return Path(m)
    return None


def _run(args: list[str]) -> str | None:
    try:
        result = subprocess.run(
            args,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=SUBPROCESS_TIMEOUT,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    return (result.stdout or "") + (result.stderr or "")


def _file_version(path: Path) -> str | None:
    """Windows .exe dosyasının sürüm kaynağını okur (Dosya Özellikleri → Ayrıntılar)."""
    if os.name != "nt" or not path.is_file():
        return None
    import ctypes
    from ctypes import wintypes

    api = ctypes.windll.version
    size = api.GetFileVersionInfoSizeW(str(path), None)
    if not size:
        return None
    buf = ctypes.create_string_buffer(size)
    if not api.GetFileVersionInfoW(str(path), 0, size, buf):
        return None
    ptr, length = ctypes.c_void_p(), wintypes.UINT()
    if not api.VerQueryValueW(buf, "\\", ctypes.byref(ptr), ctypes.byref(length)):
        return None
    # VS_FIXEDFILEINFO: imza, yapı sürümü, dosya sürümü (yüksek), dosya sürümü (düşük), ...
    info = ctypes.cast(ptr, ctypes.POINTER(wintypes.DWORD * 4)).contents
    ms, ls = info[2], info[3]
    return f"{ms >> 16}.{ms & 0xFFFF}.{ls >> 16}.{ls & 0xFFFF}"


def detect_libreoffice(settings: Settings) -> EngineStatus:
    status = EngineStatus(
        key="libreoffice",
        name="LibreOffice",
        available=False,
        needed_for="Word / Excel / PowerPoint → PDF",
        install_hint=_hint("winget install TheDocumentFoundation.LibreOffice",
                           "sudo apt install libreoffice-writer libreoffice-calc "
                           "libreoffice-impress"),
    )
    exe = _find_executable(
        settings.engines.libreoffice,
        ["soffice.com", "soffice"],
        ["LibreOffice/program/soffice.com", "LibreOffice/program/soffice.exe"],
    )
    if exe is None:
        return status
    status.available = True
    status.path = str(exe)
    # soffice.com'un sürüm kaynağı yok; aynı klasördeki soffice.exe'ninkini oku.
    status.version = _file_version(exe.with_name("soffice.exe"))
    v = _version_tuple(status.version)
    if v and v[:2] < MIN_LIBREOFFICE:
        status.warnings.append(
            f"Bu LibreOffice sürümü ({status.version}) artık güvenlik güncellemesi almıyor; "
            "başkasından gelen belgeleri çevirmeden önce güncelle"
            + (": winget upgrade TheDocumentFoundation.LibreOffice" if on_windows() else "."))
    return status


def detect_tesseract(settings: Settings) -> EngineStatus:
    status = EngineStatus(
        key="tesseract",
        name="Tesseract OCR",
        available=False,
        needed_for="Taranmış PDF'i aranabilir yapma (OCR)",
        install_hint=_hint("winget install UB-Mannheim.TesseractOCR",
                           "sudo apt install tesseract-ocr tesseract-ocr-tur tesseract-ocr-eng"),
    )
    exe = _find_executable(
        settings.engines.tesseract, ["tesseract"], ["Tesseract-OCR/tesseract.exe"],
        _bundled("tesseract/tesseract.exe"),
    )
    if exe is None:
        return status
    status.available = True
    status.path = str(exe)
    out = _run([str(exe), "--version"]) or ""
    if m := re.search(r"tesseract\s+v?([\d.]+)", out, re.IGNORECASE):
        status.version = m.group(1)
    langs_out = _run([str(exe), "--list-langs"]) or ""
    # İlk satır "List of available languages in ...:" başlığıdır.
    langs = {line.strip() for line in langs_out.splitlines()[1:] if line.strip()}
    missing = [lang for lang in REQUIRED_OCR_LANGS if lang not in langs]
    if missing:
        status.problems.append(f"Eksik dil paketi: {', '.join(missing)}")
    return status


def detect_ghostscript(settings: Settings) -> EngineStatus:
    status = EngineStatus(
        key="ghostscript",
        name="Ghostscript",
        available=False,
        needed_for="OCR ve güçlü sıkıştırma",
        install_hint=_hint("ghostscript.com/releases adresinden Windows 64-bit kurulum dosyası",
                           "sudo apt install ghostscript"),
    )
    exe = _find_executable(
        settings.engines.ghostscript,
        ["gswin64c", "gswin32c", "gs"],
        ["gs/gs*/bin/gswin64c.exe"],
        _bundled("ghostscript/bin/gswin64c.exe"),
    )
    if exe is None:
        return status
    status.available = True
    status.path = str(exe)
    if out := _run([str(exe), "--version"]):
        status.version = out.strip().splitlines()[0] if out.strip() else None
    v = _version_tuple(status.version)
    if v and v < MIN_GHOSTSCRIPT:
        status.warnings.append(
            f"Ghostscript {status.version} bilinen güvenlik açıkları içeren eski bir sürüm "
            f"({'.'.join(map(str, MIN_GHOSTSCRIPT))} ya da yenisini kur).")
    return status


def detect_browser(settings: Settings) -> EngineStatus:
    status = EngineStatus(
        key="browser",
        name="Edge / Chrome",
        available=False,
        needed_for="Markdown / HTML → PDF baskısı",
        install_hint=_hint("Microsoft Edge Windows ile birlikte gelir; kaldırıldıysa yeniden kur",
                           "Chromium, Google Chrome ya da Microsoft Edge kur (ör. sudo apt install "
                           "chromium)"),
    )
    exe = _find_executable(
        settings.engines.browser,
        # Linux / macOS: PATH'teki adlar. Windows'ta bunlar PATH'te olmaz, aşağıdaki yollar aranır.
        [] if os.name == "nt" else ["microsoft-edge", "microsoft-edge-stable", "google-chrome",
                                    "google-chrome-stable", "chromium", "chromium-browser"],
        [
            "Microsoft/Edge/Application/msedge.exe",
            "Google/Chrome/Application/chrome.exe",
        ],
    )
    if exe is None:
        return status
    status.available = True
    status.path = str(exe)
    low = exe.name.lower()
    status.name = ("Microsoft Edge" if "edge" in low else "Chromium" if "chromium" in low
                   else "Google Chrome")
    status.version = _file_version(exe)
    if status.version is None and os.name != "nt" and (
            m := re.search(r"(\d+\.[\d.]+)", _run([str(exe), "--version"]) or "")):
        status.version = m.group(1)
    return status


def python_libraries() -> dict[str, str | None]:
    out = {}
    for pkg in ("pymupdf", "pikepdf", "fastapi"):
        try:
            out[pkg] = version(pkg)
        except PackageNotFoundError:
            out[pkg] = None
    return out


def detect_all(settings: Settings) -> list[EngineStatus]:
    return [
        detect_libreoffice(settings),
        detect_browser(settings),
        detect_tesseract(settings),
        detect_ghostscript(settings),
    ]
