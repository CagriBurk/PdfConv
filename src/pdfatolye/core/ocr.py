"""OCR: taranmış PDF'e aranabilir metin katmanı (OCRmyPDF + Tesseract, `tur+eng`).

Varsayılan `skip`: zaten metni olan sayfalar atlanır (bozulmasın), eğiklik düzeltilir, yan
taranmış sayfalar döndürülür. `redo`: eski OCR katmanını yenisiyle değiştirir. `force`: her
sayfayı resme çevirip yeniden tanır (metin seçilemeyen ama "metni var" görünen dosyalar için).

OCRmyPDF ayrı süreçte çalışır: iptal ve zaman aşımında süreç ağacı öldürülür.
"""

from __future__ import annotations

import json
import os
import queue
import subprocess
import sys
import tempfile
import threading
import time
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

import psutil

from pdfatolye.core._ocr_run import PREFIX
from pdfatolye.core.pdfio import atomic_output, opened
from pdfatolye.errors import BrokenPdfError, EncryptedPdfError, PdfAtolyeError

Mode = Literal["skip", "redo", "force"]
PAGE_TIMEOUT_S = 30  # Tesseract'ın tek sayfaya ayırabileceği süre
BASE_TIMEOUT_S = 120


class OcrCancelled(Exception):
    pass


class OcrError(PdfAtolyeError):
    pass


@dataclass
class OcrResult:
    output: Path
    page_count: int
    pages_with_text: int
    warnings: list[str] = field(default_factory=list)


Progress = Callable[[float, str], None]

_ERRORS = {
    1: "OCR seçenekleri geçersiz.",
    3: "OCR için gereken bir program bulunamadı (Tesseract / Ghostscript). Ayarlar sayfasındaki "
       "motor durumuna bak.",
    6: "Bu PDF'te zaten metin var. Yeniden tanımak için 'Eski OCR'ı yenile' ya da 'Zorla' seç.",
    7: "Tesseract bir sayfada hata verdi ya da zaman aşımına uğradı.",
    10: "PDF/A dönüşümü başarısız.",
}


_STEPS = {"Checking output": "Çıktı denetleniyor", "Linearizing": "Dosya düzenleniyor",
          "Grafting hOCR to PDF": "Metin katmanı ekleniyor"}


def _kill_tree(proc: subprocess.Popen) -> None:
    try:
        parent = psutil.Process(proc.pid)
        for child in parent.children(recursive=True):
            child.kill()
        parent.kill()
    except psutil.NoSuchProcess:
        pass


def _env(tools: Sequence[str | None]) -> dict[str, str]:
    """Tesseract ve Ghostscript'in klasörleri PATH'in başına: OCRmyPDF onları bulsun."""
    env = dict(os.environ)
    dirs = [str(Path(t).parent) for t in tools if t]
    env["PATH"] = os.pathsep.join([*dirs, env.get("PATH", "")])
    env["PYTHONIOENCODING"] = "utf-8"
    return env


def ocr(src: Path, output: Path, *, mode: Mode = "skip", langs: Sequence[str] = ("tur", "eng"),
        password: str | None = None, tesseract: str | None = None,
        ghostscript: str | None = None, on_progress: Progress | None = None,
        should_cancel: Callable[[], bool] | None = None) -> OcrResult:
    src = Path(src)
    report = on_progress or (lambda f, m: None)
    with opened(src, password) as doc:  # şifre/bozukluk burada Türkçe hatayla yakalanır
        page_count = doc.page_count
        encrypted = doc.is_encrypted or bool(password)

    with tempfile.TemporaryDirectory(prefix="pa-ocr-") as tmp:
        work = src
        if encrypted:  # OCRmyPDF şifreli dosyayı açmaz: önce şifresiz kopya
            import pikepdf

            work = Path(tmp) / "girdi.pdf"
            with pikepdf.open(src, password=password or "") as pdf:
                pdf.save(work, encryption=False)
        result_pdf = Path(tmp) / "cikti.pdf"
        args = {"input": str(work), "output": str(result_pdf), "mode": mode,
                "langs": list(langs), "page_timeout": PAGE_TIMEOUT_S}
        proc = subprocess.Popen(
            [sys.executable, "-m", "pdfatolye.core._ocr_run", json.dumps(args)],
            stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, env=_env([tesseract, ghostscript]),
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        lines: queue.Queue[str | None] = queue.Queue()

        def pump() -> None:
            assert proc.stderr is not None
            for raw in proc.stderr:
                lines.put(raw.decode("utf-8", errors="replace").rstrip())
            lines.put(None)

        threading.Thread(target=pump, daemon=True).start()
        deadline = time.monotonic() + BASE_TIMEOUT_S + page_count * PAGE_TIMEOUT_S * 2
        log: list[str] = []
        error: dict | None = None
        skipped = 0
        report(0.02, "OCR başlıyor")
        try:
            while True:
                if should_cancel and should_cancel():
                    raise OcrCancelled()
                if time.monotonic() > deadline:
                    raise OcrError("OCR zaman aşımına uğradı. Daha az sayfayla dene.")
                try:
                    line = lines.get(timeout=0.3)
                except queue.Empty:
                    continue
                if line is None:
                    break
                if not line.startswith(PREFIX):
                    log.append(line)
                    if "skipping all processing" in line or "already has text" in line:
                        skipped += 1
                    continue
                data = json.loads(line[len(PREFIX):])
                if "error" in data:
                    error = data
                elif "step" in data and data.get("total"):
                    step, total = data["step"], data["total"]
                    frac = min(1.0, float(data["done"]) / float(total))
                    if step == "OCR":
                        report(0.05 + 0.85 * frac,
                               f"Metin tanınıyor: {int(data['done'])}/{int(total)} sayfa")
                    elif step == "Scanning contents":
                        report(0.02 + 0.03 * frac, "Sayfalar inceleniyor")
                    else:
                        report(0.9 + 0.08 * frac, _STEPS.get(step, "Son işlemler"))
        except BaseException:
            _kill_tree(proc)
            raise
        code = proc.wait(timeout=30)
        if code != 0 or not result_pdf.is_file():
            code = (error or {}).get("error", code)
            if code == 8:
                raise EncryptedPdfError(src)
            if code == 2:
                raise BrokenPdfError(src, "OCR girdiyi okuyamadı; önce Onar aracını dene")
            detail = (error or {}).get("message") or (log[-1] if log else "")
            msg = _ERRORS.get(code, "OCR başarısız oldu.")
            raise OcrError(f"{msg} ({detail})" if detail and code not in _ERRORS else msg)

        with opened(result_pdf) as doc:
            with_text = sum(1 for p in doc if p.get_text("text").strip())
        with atomic_output(output) as out:
            out.write_bytes(result_pdf.read_bytes())

    warnings = []
    if skipped:
        warnings.append(f"{skipped} sayfada zaten metin vardı, atlandı.")
    if with_text < page_count:
        warnings.append(f"{page_count - with_text} sayfada metin bulunamadı (boş ya da çok "
                        "silik olabilir).")
    return OcrResult(Path(output), page_count, with_text, warnings)
