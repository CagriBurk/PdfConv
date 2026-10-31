"""Dosya deposu: yüklenen ve üretilen dosyalar, sürümler, otomatik temizlik.

Düzen: files/<id>/meta.json + v1.<uzantı>, v2.<uzantı>, ... Sürümler değişmez; geri al bir
önceki sürüme döner (son sürüm silinir). Sabitlenmemiş dosyalar `retention_hours` sonra silinir.
"""

from __future__ import annotations

import json
import shutil
import threading
import time
import uuid
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import BinaryIO

from pdfatolye.core.pdfio import safe_filename
from pdfatolye.errors import PdfAtolyeError

CHUNK = 1024 * 1024
KINDS = {
    ".pdf": "pdf",
    ".md": "markdown", ".markdown": "markdown", ".txt": "text",
    ".png": "image", ".jpg": "image", ".jpeg": "image", ".webp": "image", ".gif": "image",
    ".bmp": "image", ".tif": "image", ".tiff": "image", ".heic": "image", ".heif": "image",
    ".svg": "image",
    ".docx": "office", ".doc": "office", ".odt": "office", ".rtf": "office",
    ".xlsx": "office", ".xls": "office", ".ods": "office",
    ".pptx": "office", ".ppt": "office", ".odp": "office",
    ".html": "html", ".htm": "html",
}


class FileNotInStoreError(PdfAtolyeError):
    def __init__(self, file_id: str) -> None:
        super().__init__(f"Dosya bulunamadı (silinmiş olabilir): {file_id}")


class UploadTooLargeError(PdfAtolyeError):
    def __init__(self, limit_mb: int) -> None:
        super().__init__(f"Dosya çok büyük; üst sınır {limit_mb} MB (config.toml: max_upload_mb).")


@dataclass
class Version:
    n: int
    note: str
    created: float
    size: int
    page_count: int | None = None


@dataclass
class FileMeta:
    id: str
    name: str  # kullanıcının gördüğü dosya adı (uzantılı)
    kind: str
    created: float
    source: str  # "upload" | "job"
    versions: list[Version] = field(default_factory=list)
    pinned: bool = False
    encrypted: bool = False
    job_id: str | None = None

    @property
    def current(self) -> Version:
        return self.versions[-1]

    @property
    def ext(self) -> str:
        return Path(self.name).suffix.lower()

    def to_dict(self) -> dict:
        d = asdict(self)
        d["version"] = self.current.n
        d["size"] = self.current.size
        d["page_count"] = self.current.page_count
        d["updated"] = self.current.created
        return d


def kind_of(name: str) -> str:
    return KINDS.get(Path(name).suffix.lower(), "other")


def _pdf_facts(path: Path) -> tuple[int | None, bool]:
    """(sayfa sayısı, şifreli mi). Bozuk dosyada (None, False)."""
    import pymupdf

    try:
        with pymupdf.open(path, filetype="pdf") as doc:
            if doc.needs_pass:
                return None, True
            return doc.page_count, bool((doc.metadata or {}).get("encryption"))
    except Exception:
        return None, False


class FileStore:
    def __init__(self, root: Path, max_upload_mb: int = 1024) -> None:
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        self.max_bytes = max_upload_mb * 1024 * 1024
        self.max_upload_mb = max_upload_mb
        self._lock = threading.RLock()

    # --- iç yardımcılar ---

    def _dir(self, file_id: str) -> Path:
        # Kimlik dışarıdan gelir: yalnızca onaltılık karakterler (yol saldırısı olmasın).
        if not file_id or not all(c in "0123456789abcdef" for c in file_id):
            raise FileNotInStoreError(file_id)
        return self.root / file_id

    def _save_meta(self, meta: FileMeta) -> None:
        d = self._dir(meta.id)
        tmp = d / "meta.json.tmp"
        tmp.write_text(json.dumps(asdict(meta), ensure_ascii=False, indent=1), encoding="utf-8")
        tmp.replace(d / "meta.json")

    def _version_path(self, meta: FileMeta, n: int) -> Path:
        return self._dir(meta.id) / f"v{n}{meta.ext or '.bin'}"

    def _new(self, name: str, source: str, job_id: str | None) -> tuple[FileMeta, Path]:
        name = safe_filename(Path(name).name, fallback="dosya")
        meta = FileMeta(id=uuid.uuid4().hex, name=name, kind=kind_of(name),
                        created=time.time(), source=source, job_id=job_id)
        d = self._dir(meta.id)
        d.mkdir(parents=True)
        return meta, self._version_path(meta, 1)

    def _finish_version(self, meta: FileMeta, path: Path, n: int, note: str) -> None:
        pages, encrypted = (None, False)
        if meta.kind == "pdf":
            pages, encrypted = _pdf_facts(path)
            meta.encrypted = encrypted
        meta.versions.append(Version(n, note, time.time(), path.stat().st_size, pages))
        self._save_meta(meta)

    # --- dışa açık ---

    def add_stream(self, stream: BinaryIO, name: str) -> FileMeta:
        """Yüklemeyi parça parça diske yazar; sınırı aşarsa yarım dosyayı siler."""
        meta, path = self._new(name, "upload", None)
        written = 0
        try:
            with path.open("wb") as out:
                while chunk := stream.read(CHUNK):
                    written += len(chunk)
                    if written > self.max_bytes:
                        raise UploadTooLargeError(self.max_upload_mb)
                    out.write(chunk)
            self._finish_version(meta, path, 1, "Yüklendi")
        except BaseException:
            shutil.rmtree(self._dir(meta.id), ignore_errors=True)
            raise
        return meta

    def add_file(self, src: Path, name: str, *, source: str = "job", job_id: str | None = None,
                 note: str = "Oluşturuldu") -> FileMeta:
        meta, path = self._new(name, source, job_id)
        shutil.copyfile(src, path)
        self._finish_version(meta, path, 1, note)
        return meta

    def new_version(self, file_id: str, src: Path, note: str) -> FileMeta:
        with self._lock:
            meta = self.get(file_id)
            n = meta.current.n + 1
            path = self._version_path(meta, n)
            shutil.copyfile(src, path)
            self._finish_version(meta, path, n, note)
            return meta

    def undo(self, file_id: str) -> FileMeta:
        with self._lock:
            meta = self.get(file_id)
            if len(meta.versions) < 2:
                raise PdfAtolyeError("Geri alınacak bir değişiklik yok.")
            last = meta.versions.pop()
            self._version_path(meta, last.n).unlink(missing_ok=True)
            if meta.kind == "pdf":
                meta.encrypted = _pdf_facts(self._version_path(meta, meta.current.n))[1]
            self._save_meta(meta)
            return meta

    def get(self, file_id: str) -> FileMeta:
        path = self._dir(file_id) / "meta.json"
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError) as e:
            raise FileNotInStoreError(file_id) from e
        raw["versions"] = [Version(**v) for v in raw["versions"]]
        return FileMeta(**raw)

    def path(self, file_id: str, version: int | None = None) -> Path:
        meta = self.get(file_id)
        n = version or meta.current.n
        if not any(v.n == n for v in meta.versions):
            raise PdfAtolyeError(f"'{meta.name}' için {n}. sürüm yok.")
        return self._version_path(meta, n)

    def list(self) -> list[FileMeta]:
        out = []
        for d in self.root.iterdir():
            if (d / "meta.json").is_file():
                try:
                    out.append(self.get(d.name))
                except PdfAtolyeError:
                    continue
        return sorted(out, key=lambda m: m.current.created, reverse=True)

    def set_pinned(self, file_id: str, pinned: bool) -> FileMeta:
        with self._lock:
            meta = self.get(file_id)
            meta.pinned = pinned
            self._save_meta(meta)
            return meta

    def rename(self, file_id: str, name: str) -> FileMeta:
        """Görünen adı değiştirir; uzantı korunur."""
        with self._lock:
            meta = self.get(file_id)
            stem = safe_filename(Path(name).stem, fallback=Path(meta.name).stem)
            meta.name = stem + meta.ext
            self._save_meta(meta)
            return meta

    def delete(self, file_id: str) -> None:
        shutil.rmtree(self._dir(file_id), ignore_errors=True)

    def cleanup(self, retention_hours: float) -> int:
        """Süresi dolmuş, sabitlenmemiş dosyaları siler. Silinen dosya sayısını döndürür."""
        limit = time.time() - retention_hours * 3600
        removed = 0
        for d in list(self.root.iterdir()):
            if not d.is_dir():
                continue
            try:
                meta = self.get(d.name)
            except PdfAtolyeError:
                # meta'sız yarım klasör (çökme artığı): bir günden eskiyse sil
                if d.stat().st_mtime < time.time() - 86400:
                    shutil.rmtree(d, ignore_errors=True)
                continue
            if not meta.pinned and meta.current.created < limit:
                shutil.rmtree(d, ignore_errors=True)
                removed += 1
        return removed
