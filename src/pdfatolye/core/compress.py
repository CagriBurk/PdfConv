"""PDF küçültme: kayıpsız, dengeli, güçlü.

- kayıpsız: kullanılmayan nesneler atılır, akışlar yeniden sıkıştırılır, nesne akışları.
  Görüntü kalitesi değişmez.
- dengeli: + eşikten yüksek çözünürlüklü resimler 150 DPI'a, JPEG kalitesi 75.
- güçlü: + 100 DPI, kalite 60. Ghostscript varsa onun `/ebook` çıktısı da denenir,
  hangisi küçükse o alınır.

Sonuç orijinalden küçük değilse orijinal korunur (çıktı orijinalin kopyasıdır) ve söylenir.
"""

from __future__ import annotations

import shutil
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

import pymupdf

from pdfatolye import proc
from pdfatolye.core.pdfio import atomic_output, opened
from pdfatolye.errors import PdfAtolyeError

Level = Literal["kayipsiz", "dengeli", "guclu"]
LEVELS: dict[str, tuple[int, int] | None] = {  # (hedef DPI, JPEG kalitesi)
    "kayipsiz": None,
    "dengeli": (150, 75),
    "guclu": (100, 60),
}
GS_TIMEOUT_S = 600


@dataclass
class CompressResult:
    output: Path
    before: int
    after: int
    kept_original: bool
    method: str
    warnings: list[str] = field(default_factory=list)

    @property
    def saved_ratio(self) -> float:
        return 1 - self.after / self.before if self.before else 0.0


def _pymupdf(src: Path, out: Path, level: Level, password: str | None) -> None:
    with opened(src, password) as doc:
        target = LEVELS[level]
        if target:
            dpi, quality = target
            # Eşik hedefin biraz üstünde: 160 DPI'lık resmi 150'ye indirmek kazandırmaz, bozar.
            doc.rewrite_images(dpi_threshold=round(dpi * 1.3), dpi_target=dpi, quality=quality,
                               lossy=True, lossless=True, bitonal=False)
        doc.save(out, garbage=4, clean=True, deflate=True, deflate_images=True,
                 deflate_fonts=True, use_objstms=1)


def _ghostscript(gs: str, src: Path, out: Path) -> bool:
    args = [gs, "-sDEVICE=pdfwrite", "-dCompatibilityLevel=1.6", "-dPDFSETTINGS=/ebook",
            "-dNOPAUSE", "-dBATCH", "-dQUIET", "-dSAFER", f"-sOutputFile={out}", str(src)]
    try:  # iptal (proc.Cancelled) yukarı geçer; süreç ağacı öldürülür
        result = proc.run(args, timeout=GS_TIMEOUT_S)
    except (OSError, proc.TimedOut):
        return False
    if result.returncode != 0 or not out.is_file():
        return False
    try:
        with pymupdf.open(out) as doc:  # gs bazen bozuk/boş dosya bırakır
            return doc.page_count > 0
    except Exception:
        return False


def compress(src: Path, output: Path, level: Level = "dengeli", *, password: str | None = None,
             ghostscript: str | None = None) -> CompressResult:
    if level not in LEVELS:
        raise PdfAtolyeError(f"Bilinmeyen sıkıştırma seviyesi: {level}")
    src = Path(src)
    before = src.stat().st_size
    warnings: list[str] = []
    with tempfile.TemporaryDirectory(prefix="pa-sik-") as tmp:
        candidates: list[tuple[Path, str]] = []
        mu = Path(tmp) / "mu.pdf"
        _pymupdf(src, mu, level, password)
        candidates.append((mu, "PyMuPDF"))
        if level == "guclu" and ghostscript:
            if password:
                warnings.append("Şifreli dosyada Ghostscript denenmedi.")
            else:
                gs_out = Path(tmp) / "gs.pdf"
                if _ghostscript(ghostscript, src, gs_out):
                    candidates.append((gs_out, "Ghostscript /ebook"))
        best, method = min(candidates, key=lambda c: c[0].stat().st_size)
        after = best.stat().st_size
        kept = after >= before
        with atomic_output(output) as out:
            shutil.copyfile(src if kept else best, out)
    if kept:
        warnings.append("Dosya bu seviyede daha fazla küçülmedi; orijinal korundu.")
        after, method = before, "orijinal"
    return CompressResult(Path(output), before, after, kept, method, warnings)
