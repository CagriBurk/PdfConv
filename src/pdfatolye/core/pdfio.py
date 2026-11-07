"""PDF açma / kaydetme yardımcıları: şifre, bozuk dosya ve güvenli yazma tek yerde."""

from __future__ import annotations

import contextlib
import os
import tempfile
from collections.abc import Iterator
from pathlib import Path, PureWindowsPath

import pymupdf

from pdfatolye.errors import BrokenPdfError, EncryptedPdfError, UnsupportedFileError

# MuPDF onarılabilir hatalar için konsola uyarı basar; bunları kullanıcıya biz anlatıyoruz.
pymupdf.TOOLS.mupdf_display_errors(False)
pymupdf.TOOLS.mupdf_display_warnings(False)


def open_pdf(path: Path, password: str | None = None) -> pymupdf.Document:
    """PDF'i açar; şifreliyse şifreyle çözer. Hatalar Türkçe istisnalara çevrilir."""
    path = Path(path)
    if not path.is_file():
        raise FileNotFoundError(f"'{path}' bulunamadı.")
    try:
        doc = pymupdf.open(path, filetype="pdf")
    except (pymupdf.FileDataError, RuntimeError, ValueError) as e:
        raise BrokenPdfError(path, str(e)) from e
    if not doc.is_pdf:
        doc.close()
        raise UnsupportedFileError(path, "PDF")
    if doc.needs_pass:
        if not password:
            doc.close()
            raise EncryptedPdfError(path)
        if not doc.authenticate(password):
            doc.close()
            raise EncryptedPdfError(path, wrong_password=True)
    if doc.page_count == 0:
        doc.close()
        raise BrokenPdfError(path, "hiç sayfa yok")
    return doc


@contextlib.contextmanager
def opened(path: Path, password: str | None = None) -> Iterator[pymupdf.Document]:
    doc = open_pdf(path, password)
    try:
        yield doc
    finally:
        doc.close()


@contextlib.contextmanager
def atomic_output(output: Path) -> Iterator[Path]:
    """Önce aynı klasörde geçici dosyaya yazdırır, başarılıysa hedefin üstüne taşır.

    Böylece yarım dosya kalmaz ve çıktı girdiyle aynı dosya olabilir (yerinde düzenleme).
    """
    output = Path(output)
    output.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(prefix=".tmp-", suffix=output.suffix, dir=output.parent)
    os.close(fd)
    tmp = Path(tmp_name)
    try:
        yield tmp
        os.replace(tmp, output)
    finally:
        tmp.unlink(missing_ok=True)


def save_pdf(doc: pymupdf.Document, output: Path) -> Path:
    """Belgeyi sıkıştırılmış ve kullanılmayan nesnelerden arındırılmış hâlde kaydeder."""
    with atomic_output(output) as tmp:
        doc.save(tmp, garbage=3, deflate=True)
    return Path(output)


def unique_path(path: Path) -> Path:
    """Dosya varsa 'ad (2).pdf', 'ad (3).pdf' ... şeklinde boş bir ad bulur."""
    path = Path(path)
    if not path.exists():
        return path
    for i in range(2, 10_000):
        candidate = path.with_name(f"{path.stem} ({i}){path.suffix}")
        if not candidate.exists():
            return candidate
    raise FileExistsError(f"'{path}' için boş bir dosya adı bulunamadı.")


_FORBIDDEN = set('<>:"/\\|?*') | {chr(i) for i in range(32)}
_RESERVED = {"CON", "PRN", "AUX", "NUL", *(f"COM{i}" for i in range(1, 10)),
             *(f"LPT{i}" for i in range(1, 10))}


def base_name(name: str) -> str:
    """Kullanıcıdan gelen adın son parçası: eğik ve ters eğik çizgi her işletim sisteminde
    ayırıcıdır (Linux'ta `Path` ters eğik çizgiyi adın parçası sayardı)."""
    return PureWindowsPath(name).name


def safe_filename(name: str, fallback: str = "dosya", max_len: int = 80) -> str:
    """Windows'ta geçerli bir dosya adı KÖKÜ üretir (uzantısız ad için). Türkçe harfler korunur.
    Uzantılı ad için `safe_name_with_ext` kullan: bu fonksiyon uzun adda uzantıyı da keser."""
    cleaned = "".join("_" if c in _FORBIDDEN else c for c in name).strip(" .")
    cleaned = " ".join(cleaned.split())[:max_len].rstrip(" .")
    if not cleaned or cleaned.upper() in _RESERVED:
        return fallback
    return cleaned


MAX_EXT_LEN = 10


def split_ext(name: str) -> tuple[str, str]:
    """('rapor v1.2', '.pdf'). Uzantı yalnızca kısa, harf/rakamdan oluşan son parçadır:
    'Sürüm 1.2 son' adında '.2 son' uzantı sayılmaz (Path.suffix sayardı)."""
    name = name.strip().rstrip(" .")
    stem, dot, ext = name.rpartition(".")
    if dot and stem.strip(" .") and 0 < len(ext) <= MAX_EXT_LEN and ext.isascii() \
            and ext.isalnum():
        return stem, "." + ext
    return name, ""


def safe_name_with_ext(name: str, fallback: str = "dosya", max_len: int = 80) -> str:
    """Uzantılı güvenli dosya adı: kök kısaltılır, uzantı her zaman korunur
    ('çok uzun ... ad.pdf' → '<80 karakter>.pdf'). Ayrılmış adlar ('CON.pdf') yedek adı alır."""
    stem, ext = split_ext(name)
    return safe_filename(stem, fallback, max_len) + ext


def strip_ext(name: str, ext: str) -> str:
    """Ad `ext` ile bitiyorsa (büyük/küçük harf fark etmez) onu atar; başka noktalara dokunmaz."""
    name = name.strip()
    return name[: -len(ext)] if ext and name.lower().endswith(ext.lower()) else name
