"""Kullanıcı şablonları (Markdown → PDF ekranındaki "Şablon ekle" menüsü).

Düzen: veri klasöründe `sablonlar/<ad>.md`, şablon başına bir düz metin dosyası. Şablonun adı
dosya adıdır: kullanıcı klasöre elle .md dosyası atarsa o da listede görünür. Saklama süresi
temizliği yalnızca `files/` ve `jobs/` klasörlerine bakar; bu klasöre hiç dokunmaz.
"""

from __future__ import annotations

import logging
import threading
import unicodedata
import uuid
from dataclasses import dataclass
from pathlib import Path

from pdfatolye.core.textio import decode_text
from pdfatolye.errors import PdfAtolyeError, disk_full_error, is_disk_full

DIR_NAME = "sablonlar"
MAX_NAME = 60
MAX_BODY_CHARS = 100_000
MAX_COUNT = 100
# Elle atılan dosyalar için: karakter sınırının UTF-8 karşılığından büyükse okunmaz.
MAX_FILE_BYTES = MAX_BODY_CHARS * 4
BAD_CHARS = '<>:"/\\|?*'
# Windows bu adlarla (uzantılı da olsa) dosya oluşturmaz.
RESERVED = {"con", "prn", "aux", "nul", *(f"com{i}" for i in range(1, 10)),
            *(f"lpt{i}" for i in range(1, 10))}

# Türkçe alfabe sırası: "~" harflerden sonra gelir, Ç → C'lerin sonunda, D'den önce.
_TR_ORDER = str.maketrans({"ç": "c~", "ğ": "g~", "ı": "h~", "ö": "o~", "ş": "s~", "ü": "u~"})

# Ad çakışması: "TAKTİĞİ" ile "taktiği", "Lab" ile "lab" aynı şablon (I, İ, ı, i tek harf).
_FOLD_I = str.maketrans({"İ": "i", "I": "i", "ı": "i"})

log = logging.getLogger("pdfatolye.sablonlar")
# Her istek kendi deposunu kurar; yazma işlemleri (sayı sınırı, ad çakışması) tek kilitle sıralanır.
_LOCK = threading.Lock()


@dataclass
class Snippet:
    name: str
    body: str
    updated: float

    def to_dict(self) -> dict:
        return {"name": self.name, "body": self.body, "updated": self.updated}


def clean_name(name: str) -> str:
    """Yeni şablon adı: boşluklar sadeleşir; Türkçe harf serbest, Windows'un dosya adında kabul
    etmediği karakterler ve ayrılmış adlar reddedilir (ad dosya adı olur)."""
    name = unicodedata.normalize("NFC", " ".join(name.split()))
    if not name:
        raise PdfAtolyeError("Şablona bir ad ver.")
    if len(name) > MAX_NAME:
        raise PdfAtolyeError(f"Şablon adı en fazla {MAX_NAME} karakter olabilir.")
    if any(c in BAD_CHARS or ord(c) < 32 or ord(c) == 127 for c in name):
        raise PdfAtolyeError('Şablon adında < > : " / \\ | ? * karakterleri kullanılamaz.')
    if name.startswith(".") or name.endswith("."):
        raise PdfAtolyeError("Şablon adı nokta ile başlayamaz ve bitemez.")
    if name.split(".")[0].strip().casefold() in RESERVED:
        raise PdfAtolyeError(f"'{name}' Windows'ta ayrılmış bir ad; başka bir ad seç.")
    return name


def clean_body(body: str) -> str:
    body = body.replace("\r\n", "\n").replace("\r", "\n")
    if not body.strip():
        raise PdfAtolyeError("Şablon boş olamaz; önce düzenleyicide bir metin yaz ya da seç.")
    if len(body) > MAX_BODY_CHARS:
        limit = f"{MAX_BODY_CHARS:,}".replace(",", ".")
        raise PdfAtolyeError(f"Şablon çok uzun: en fazla {limit} karakter olabilir. Notun yalnızca "
                             "gereken kısmını seçip kaydet.")
    return body


def name_key(name: str) -> str:
    return unicodedata.normalize("NFC", " ".join(name.split())).translate(_FOLD_I).casefold()


class SnippetStore:
    def __init__(self, root: Path) -> None:
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)

    def _files(self) -> dict[str, Path]:
        """Ad anahtarı (`name_key`; Windows'ta da `Lab.md` ile `lab.md` aynı dosya) → yol."""
        out: dict[str, Path] = {}
        for p in self.root.iterdir():
            if p.suffix.lower() == ".md" and not p.name.startswith(".") and p.is_file():
                out[name_key(p.stem)] = p
        return out

    def _find(self, name: str) -> Path:
        path = self._files().get(name_key(name))
        if path is None:
            raise PdfAtolyeError(f"'{name}' şablonu bulunamadı; silinmiş ya da adı değişmiş "
                                 "olabilir. Menüyü kapatıp yeniden aç.")
        return path

    def _target(self, name: str) -> Path:
        path = self.root / f"{name}.md"
        # Ad zaten doğrulandı; yine de yol hiçbir koşulda klasörün dışına çıkmasın.
        if path.resolve().parent != self.root.resolve():
            raise PdfAtolyeError("Geçersiz şablon adı.")
        return path

    def _read(self, path: Path) -> Snippet | None:
        try:
            st = path.stat()
            if st.st_size > MAX_FILE_BYTES:
                log.warning("Şablon çok büyük, listelenmedi: %s", path.name)
                return None
            text, _ = decode_text(path.read_bytes(), path.name)
        except OSError as e:
            log.warning("Şablon okunamadı: %s (%s)", path.name, e)
            return None
        body = text.replace("\r\n", "\n").replace("\r", "\n")
        return Snippet(path.stem, body, st.st_mtime)

    def _write(self, path: Path, body: str) -> None:
        tmp = self.root / f".{uuid.uuid4().hex}.tmp"
        try:
            tmp.write_bytes(body.encode("utf-8"))
            tmp.replace(path)
        except OSError as e:
            tmp.unlink(missing_ok=True)
            if is_disk_full(e):
                raise disk_full_error() from e
            raise

    def list(self) -> list[Snippet]:
        items = [s for p in self._files().values() if (s := self._read(p))]
        return sorted(items, key=lambda s: s.name.casefold().translate(_TR_ORDER))

    def add(self, name: str, body: str) -> Snippet:
        name, body = clean_name(name), clean_body(body)
        with _LOCK:
            files = self._files()
            if name_key(name) in files:
                raise PdfAtolyeError(f"'{files[name_key(name)].stem}' adında bir şablon zaten "
                                     "var. Başka bir ad seç ya da menüden o şablonun üzerine yaz.")
            if len(files) >= MAX_COUNT:
                raise PdfAtolyeError(f"En fazla {MAX_COUNT} şablon saklanabilir; kullanmadıklarını "
                                     "menüden sil.")
            path = self._target(name)
            self._write(path, body)
            return self._read(path) or Snippet(name, body, 0)

    def update(self, name: str, *, new_name: str | None = None, body: str | None = None) -> Snippet:
        """Yeniden adlandırır ve/veya içeriği değiştirir ("üzerine yaz")."""
        new_name = clean_name(new_name) if new_name is not None else None
        body = clean_body(body) if body is not None else None
        with _LOCK:
            path = self._find(name)
            if new_name is not None and new_name != path.stem:
                other = self._files().get(name_key(new_name))
                if other is not None and other != path:
                    raise PdfAtolyeError(f"'{other.stem}' adında bir şablon zaten var; başka bir "
                                         "ad seç.")
                target = self._target(new_name)
                path.replace(target)  # yalnızca harf büyüklüğü değişse de çalışır
                path = target
            if body is not None:
                self._write(path, body)
            return self._read(path) or Snippet(path.stem, body or "", 0)

    def delete(self, name: str) -> None:
        with _LOCK:
            self._find(name).unlink(missing_ok=True)
