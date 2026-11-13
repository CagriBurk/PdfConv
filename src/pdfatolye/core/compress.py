"""PDF küçültme: kayıpsız, dengeli, güçlü.

- kayıpsız: kullanılmayan nesneler atılır, akışlar yeniden sıkıştırılır, nesne akışları; gömülü
  yazı tipleri yalnızca kullanılan karakterlere indirilir (metin ağırlıklı PDF'te asıl kazanç
  budur). Görüntü ve metin değişmez.
- dengeli: + eşikten yüksek çözünürlüklü resimler 150 DPI'a, JPEG kalitesi 75.
- güçlü: + 100 DPI, kalite 60. PyMuPDF sonucu hâlâ büyükse (orijinalin %40'ından fazla)
  Ghostscript `/ebook` da denenir, hangisi küçükse o alınır. Resim ağırlıklı dosyada PyMuPDF
  zaten çok küçültür; Ghostscript orada dakikalar sürüp birkaç yüzde kazandırıyordu (ölçüldü:
  248 MB taranmış pafta → PyMuPDF 27 sn'de 37 MB, Ghostscript ek 130 sn'de 35,7 MB).

Sonuç orijinalden küçük değilse orijinal korunur (çıktı orijinalin kopyasıdır) ve söylenir.
"""

from __future__ import annotations

import logging
import re
import shutil
import tempfile
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

import pymupdf

from pdfatolye import proc
from pdfatolye.core.pdfio import atomic_output, opened
from pdfatolye.errors import PdfAtolyeError

log = logging.getLogger("pdfatolye.compress")

Level = Literal["kayipsiz", "dengeli", "guclu"]
LEVELS: dict[str, tuple[int, int] | None] = {  # (hedef DPI, JPEG kalitesi)
    "kayipsiz": None,
    "dengeli": (150, 75),
    "guclu": (100, 60),
}
GS_TIMEOUT_S = 1800
# PyMuPDF sonucu orijinalin bu oranının altındaysa Ghostscript denenmez (bkz. modül açıklaması).
GS_WORTH_RATIO = 0.4
Progress = Callable[[float, str], None]


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


def _subset_fonts(doc: pymupdf.Document) -> None:
    """Gömülü yazı tiplerini kullanılan karakterlere indirir. Bazı yazı tipleri (Type3, bozuk)
    indirilemez: o zaman olduğu gibi kalır, sıkıştırma durmaz."""
    try:
        doc.subset_fonts()
    except Exception as e:  # PyMuPDF/fontTools çeşitli hatalar verebilir
        log.info("Yazı tipleri alt kümeye indirilemedi: %s", e)


def _pymupdf(src: Path, out: Path, level: Level, password: str | None,
             report: Progress | None = None) -> None:
    say = report or (lambda f, m: None)
    with opened(src, password) as doc:
        target = LEVELS[level]
        if target:
            dpi, quality = target
            say(0.05, "Resimler küçültülüyor (büyük dosyada birkaç dakika sürebilir)")
            # Eşik hedefin biraz üstünde: 160 DPI'lık resmi 150'ye indirmek kazandırmaz, bozar.
            doc.rewrite_images(dpi_threshold=round(dpi * 1.3), dpi_target=dpi, quality=quality,
                               lossy=True, lossless=True, bitonal=False)
        proc.raise_if_cancelled()
        say(0.6, "Yazı tipleri küçültülüyor")
        _subset_fonts(doc)
        proc.raise_if_cancelled()
        say(0.7, "Kaydediliyor")
        doc.save(out, garbage=4, clean=True, deflate=True, deflate_images=True,
                 deflate_fonts=True, use_objstms=1)


def image_share(path: Path, password: str | None = None) -> float | None:
    """Dosya baytlarının ne kadarı resim akışı (0–1)? Az kazancın nedenini açıklamak için:
    resmi az olan (yazı, çizim) PDF'ler zaten sıkıştırılmıştır. Okunamazsa None."""
    try:
        with opened(path, password) as doc:
            total = 0
            for xref in range(1, doc.xref_length()):
                if doc.xref_get_key(xref, "Subtype")[1] == "/Image":
                    stream_len: int | None = None
                    try:
                        kind, val = doc.xref_get_key(xref, "Length")
                        if kind == "int" or val:
                            stream_len = int(val.strip())
                    except Exception:
                        stream_len = None
                    if stream_len is None or stream_len < 0:
                        stream_len = len(doc.xref_stream_raw(xref) or b"")
                    total += stream_len
        size = Path(path).stat().st_size
        return min(1.0, total / size) if size else None
    except Exception:
        return None


_GS_PAGES = re.compile(r"Processing pages \d+ through (\d+)")
_GS_PAGE = re.compile(r"^Page (\d+)$")


def _ghostscript(gs: str, src: Path, out: Path, report: Progress | None = None) -> bool:
    """Ghostscript `/ebook`. `-dQUIET` yok: sayfa satırları ("Page 12") ilerleme olarak okunur."""
    args = [gs, "-sDEVICE=pdfwrite", "-dCompatibilityLevel=1.6", "-dPDFSETTINGS=/ebook",
            "-dNOPAUSE", "-dBATCH", "-dSAFER", f"-sOutputFile={out}", str(src)]
    total = [0]

    def on_line(line: str) -> None:
        if m := _GS_PAGES.search(line):
            total[0] = int(m.group(1))
        elif (m := _GS_PAGE.match(line)) and report and total[0]:
            n = int(m.group(1))
            report(n / total[0], f"Ghostscript ile ek deneme: sayfa {n}/{total[0]}")

    try:  # iptal (proc.Cancelled) yukarı geçer; süreç ağacı öldürülür
        code, tail = proc.run_lines(args, timeout=GS_TIMEOUT_S, on_line=on_line)
    except (OSError, proc.TimedOut):
        return False
    if code != 0 or not out.is_file():
        log.info("Ghostscript başarısız (%s): %s", code, tail[-500:])
        return False
    try:
        with pymupdf.open(out) as doc:  # gs bazen bozuk/boş dosya bırakır
            return doc.page_count > 0
    except Exception:
        return False


def compress(src: Path, output: Path, level: Level = "dengeli", *, password: str | None = None,
             ghostscript: str | None = None, report: Progress | None = None) -> CompressResult:
    """`report(oran, ileti)`: 0–1 arası ilerleme (bu dosya için)."""
    if level not in LEVELS:
        raise PdfAtolyeError(f"Bilinmeyen sıkıştırma seviyesi: {level}")
    say = report or (lambda f, m: None)
    src = Path(src)
    before = src.stat().st_size
    warnings: list[str] = []
    use_gs = level == "guclu" and ghostscript
    mu_share = 0.5 if use_gs else 1.0  # ilerleme çubuğunda PyMuPDF'in payı
    with tempfile.TemporaryDirectory(prefix="pa-sik-") as tmp:
        candidates: list[tuple[Path, str]] = []
        mu = Path(tmp) / "mu.pdf"
        _pymupdf(src, mu, level, password, lambda f, m: say(f * mu_share, m))
        candidates.append((mu, "PyMuPDF"))
        if use_gs:
            if password:
                warnings.append("Şifreli dosyada Ghostscript denenmedi.")
            elif mu.stat().st_size <= before * GS_WORTH_RATIO:
                log.info("Ghostscript atlandı: PyMuPDF %d → %d bayt", before, mu.stat().st_size)
            else:
                gs_out = Path(tmp) / "gs.pdf"
                say(mu_share, "Ghostscript ile ek deneme")
                if _ghostscript(ghostscript, src, gs_out,
                                lambda f, m: say(mu_share + f * (1 - mu_share), m)):
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
