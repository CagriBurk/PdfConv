"""Bu bilgisayarın masaüstüyle tümleşme: klasör seçme penceresi, Gezgin'de gösterme.

Arayüz tarayıcıda çalıştığı için dosya yolu göremez/seçemez; bu işler sunucuda, yalnızca sunucunun
çalıştığı bilgisayardan gelen isteklerle (telefon modundaki cihazlar değil) yapılır. Her şey
Windows'un kendi imzalı araçlarıyla (powershell.exe, explorer.exe): Akıllı Uygulama Denetimi
engellemez, yeni bir .exe gerekmez.
"""

from __future__ import annotations

import base64
import logging
import os
import shutil
import subprocess
from pathlib import Path

from pdfatolye.errors import PdfAtolyeError

log = logging.getLogger("pdfatolye.native")
PICK_TIMEOUT_S = 600  # kullanıcı pencereyi açık bırakabilir; sonsuza dek beklenmez
REVEAL_DIR = "Dışa aktarılanlar"

# Seçim penceresi her zaman en üstte açılsın: uygulama penceresinin arkasında kalmasın.
_PICK_SCRIPT = r"""
$ErrorActionPreference = 'Stop'
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
Add-Type -AssemblyName System.Windows.Forms
$owner = New-Object System.Windows.Forms.Form
$owner.TopMost = $true
$owner.ShowInTaskbar = $false
$d = New-Object System.Windows.Forms.FolderBrowserDialog
$d.Description = '__ACIKLAMA__'
$d.ShowNewFolderButton = $false
$start = '__BASLANGIC__'
if ($start -and (Test-Path -LiteralPath $start -PathType Container)) { $d.SelectedPath = $start }
if ($d.ShowDialog($owner) -eq [System.Windows.Forms.DialogResult]::OK) { $d.SelectedPath }
"""


class NativeUnavailableError(PdfAtolyeError):
    def __init__(self) -> None:
        super().__init__("Bu özellik yalnızca Windows'ta, uygulamanın çalıştığı bilgisayarda var.")


def _ps_literal(text: str) -> str:
    return text.replace("'", "''")


def _clean_env() -> dict:
    # pwsh içinden çağrılan powershell.exe devraldığı PSModulePath ile modül yükleyemez (#57).
    env = dict(os.environ)
    env.pop("PSModulePath", None)
    return env


def pick_folder(initial: str | None = None, description: str = "Klasör seç") -> str | None:
    """Windows'un klasör seçme penceresini açar; seçilen yol ya da vazgeçilirse None."""
    if os.name != "nt":
        raise NativeUnavailableError()
    script = (_PICK_SCRIPT.replace("__ACIKLAMA__", _ps_literal(description))
              .replace("__BASLANGIC__", _ps_literal(initial or "")))
    encoded = base64.b64encode(script.encode("utf-16-le")).decode("ascii")
    try:
        out = subprocess.run(
            ["powershell.exe", "-NoProfile", "-NonInteractive", "-STA", "-ExecutionPolicy",
             "Bypass", "-EncodedCommand", encoded],
            capture_output=True, timeout=PICK_TIMEOUT_S, env=_clean_env(),
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0), check=False)
    except subprocess.TimeoutExpired:
        return None
    if out.returncode != 0:
        log.warning("Klasör seçme penceresi açılamadı: %s",
                    out.stderr.decode("utf-8", "replace")[-500:])
        raise PdfAtolyeError("Klasör seçme penceresi açılamadı; yolu elle yaz.")
    path = out.stdout.decode("utf-8-sig", "replace").strip()
    return path or None


def reveal(path: Path) -> None:
    """Dosyayı Gezgin'de seçili gösterir."""
    if os.name != "nt":
        raise NativeUnavailableError()
    # explorer.exe hemen döner (işi çalışan Gezgin'e devreder); çıkış kodu anlamsızdır.
    subprocess.Popen(["explorer.exe", f"/select,{path}"],
                     creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))


def export_copy(store, data_dir: Path, file_id: str) -> Path:
    """Depodaki dosyanın güncel sürümünü kullanıcının gördüğü adıyla dışa aktarma klasörüne
    kopyalar (depodaki `v3.pdf` gibi iç dosyalar gösterilmez, kullanıcı onlara dokunamaz).
    Depodan silinmiş dosyaların kopyaları her çağrıda temizlenir."""
    meta = store.get(file_id)
    root = data_dir / REVEAL_DIR
    root.mkdir(parents=True, exist_ok=True)
    known = {m.id for m in store.list()}
    for d in root.iterdir():
        if d.is_dir() and d.name not in known:
            shutil.rmtree(d, ignore_errors=True)
    target_dir = root / file_id
    if target_dir.exists():
        shutil.rmtree(target_dir, ignore_errors=True)
    target_dir.mkdir(parents=True, exist_ok=True)
    target = target_dir / meta.name
    shutil.copyfile(store.path(file_id), target)
    return target
