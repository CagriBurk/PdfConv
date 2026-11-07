"""Eklenen yazılar için gömülü TTF fontlar.

PDF'in yerleşik Helvetica'sında ğ, ş, ı, İ yoktur; bu yüzden her yazı bir TTF gömülerek
yazılır. Font, belgede kullanılan karakterlere indirgenir (alt küme): tam Arial ~1 MB,
alt kümesi birkaç KB. Alt küme ayrıca boşluğun metin çıkarmada NBSP (U+00A0) olarak
okunmasını önler (çoğu fontta ikisi aynı glifi paylaşır).

Varsayılan fontlar Noto Sans / Serif / Sans Mono (OFL) ve paketin içinde gelir
(`pdfatolye/assets/fonts`): editör Windows fontlarına bağımlı değildir. Windows fontları (Segoe UI,
Arial...) bilgisayarda varsa ek seçenek olarak listelenir.
"""

from __future__ import annotations

import io
import logging
import os
import uuid
from dataclasses import dataclass, field
from pathlib import Path

import pymupdf

from pdfatolye import paths
from pdfatolye.errors import PdfAtolyeError

# anahtar: (görünen ad, normal dosya, kalın dosya). Görünen ad tarayıcıdaki CSS adıyla aynı;
# editör önizlemesi aynı fontla çizer.
FAMILIES: dict[str, tuple[str, str, str]] = {
    "noto-sans": ("Noto Sans", "NotoSans-Regular.ttf", "NotoSans-Bold.ttf"),
    "noto-serif": ("Noto Serif", "NotoSerif-Regular.ttf", "NotoSerif-Bold.ttf"),
    "noto-mono": ("Noto Sans Mono", "NotoSansMono-Regular.ttf", "NotoSansMono-Bold.ttf"),
    "segoe": ("Segoe UI", "segoeui.ttf", "segoeuib.ttf"),
    "arial": ("Arial", "arial.ttf", "arialbd.ttf"),
    "calibri": ("Calibri", "calibri.ttf", "calibrib.ttf"),
    "times": ("Times New Roman", "times.ttf", "timesbd.ttf"),
    "georgia": ("Georgia", "georgia.ttf", "georgiab.ttf"),
    "consolas": ("Consolas", "consola.ttf", "consolab.ttf"),
}
DEFAULT_FAMILY = "noto-sans"
BUNDLED = ("noto-sans", "noto-serif", "noto-mono")

logging.getLogger("fontTools").setLevel(logging.ERROR)


class FontNotFoundError(PdfAtolyeError):
    def __init__(self, family: str, filename: str) -> None:
        super().__init__(
            f"'{family}' fontu ({filename}) bu bilgisayarda yok. Noto Sans gibi uygulamayla "
            "gelen bir font seç."
        )


def _search_dirs() -> list[Path]:
    dirs = [paths.fonts_dir()]
    windir = os.environ.get("WINDIR", r"C:\Windows")
    dirs.append(Path(windir) / "Fonts")
    if local := os.environ.get("LOCALAPPDATA"):
        dirs.append(Path(local) / "Microsoft" / "Windows" / "Fonts")  # kullanıcıya kurulanlar
    return dirs


def font_path(family: str, bold: bool = False) -> Path:
    if family not in FAMILIES:
        raise PdfAtolyeError(f"Bilinmeyen font: {family}")
    name, regular, bold_file = FAMILIES[family]
    filename = bold_file if bold else regular
    for d in _search_dirs():
        if (d / filename).is_file():
            return d / filename
    raise FontNotFoundError(name + (" Kalın" if bold else ""), filename)


def available() -> list[dict]:
    """Arayüz için: hangi fontlar kullanılabilir, kalını var mı."""
    out = []
    for key, (name, _, _) in FAMILIES.items():
        try:
            font_path(key)
        except FontNotFoundError:
            continue
        try:
            font_path(key, bold=True)
            has_bold = True
        except FontNotFoundError:
            has_bold = False
        out.append({"key": key, "name": name, "bold": has_bold})
    return out


def subset_font(path: Path, text: str) -> bytes:
    """TTF'i yalnızca `text` içindeki karakterleri içerecek şekilde küçültür."""
    from fontTools import subset
    from fontTools.ttLib import TTFont

    options = subset.Options()
    options.notdef_outline = True
    options.name_IDs = ["*"]
    font = TTFont(path, lazy=False)
    subsetter = subset.Subsetter(options)
    subsetter.populate(text=text + " ")
    subsetter.subset(font)
    buf = io.BytesIO()
    font.save(buf)
    return buf.getvalue()


@dataclass
class _Entry:
    text: set[str] = field(default_factory=set)
    resource: str = ""
    buffer: bytes | None = None
    font: pymupdf.Font | None = None


class FontSet:
    """Bir belgeye yazılacak tüm metin önce `need` ile bildirilir; `use` ilk çağrıda alt
    kümeyi üretir ve sayfaya ekler. Aynı font tüm sayfalarda tek nesne olarak paylaşılır.

    Kaynak adları her uygulamada rastgele: aynı sayfaya ikinci kez yazarken eski alt kümeyle
    (yeni harfleri içermeyen) karışmasın.
    """

    def __init__(self) -> None:
        self._entries: dict[tuple[str, bool], _Entry] = {}
        self._token = uuid.uuid4().hex[:6]

    def need(self, family: str, bold: bool, text: str) -> None:
        font_path(family, bold)  # yoksa şimdi hata versin, yarım iş kalmasın
        self._entries.setdefault((family, bold), _Entry()).text.update(text)

    def _entry(self, family: str, bold: bool) -> _Entry:
        entry = self._entries.get((family, bold))
        if entry is None:
            raise PdfAtolyeError("İç hata: font önceden bildirilmedi.")
        if entry.buffer is None:
            entry.buffer = subset_font(font_path(family, bold), "".join(sorted(entry.text)))
            entry.font = pymupdf.Font(fontbuffer=entry.buffer)
            entry.resource = f"pa{self._token}{list(self._entries).index((family, bold))}"
        return entry

    def use(self, page: pymupdf.Page, family: str, bold: bool) -> tuple[str, pymupdf.Font]:
        """(sayfadaki kaynak adı, ölçüm için font)."""
        entry = self._entry(family, bold)
        page.insert_font(fontname=entry.resource, fontbuffer=entry.buffer)
        return entry.resource, entry.font

    def missing_chars(self, family: str, bold: bool, text: str) -> list[str]:
        """Fontta glifi olmayan karakterler (kutucuk olarak çıkarlar)."""
        font = pymupdf.Font(fontfile=str(font_path(family, bold)))
        seen: list[str] = []
        for ch in text:
            if ch in "\n\t " or ch in seen:
                continue
            if not font.has_glyph(ord(ch)):
                seen.append(ch)
        return seen
