"""Dosya deposu: yüklenen ve üretilen dosyalar, sürümler, otomatik temizlik.

Düzen: files/<id>/meta.json + v1.<uzantı>, v2.<uzantı>, ... Sürümler değişmez; geri al bir
önceki sürüme döner (son sürüm silinir). Sabitlenmemiş dosyalar `retention_hours` sonra silinir.
"""

from __future__ import annotations

import contextlib
import json
import logging
import re
import shutil
import threading
import time
import uuid
from collections import Counter
from collections.abc import Iterable, Iterator
from dataclasses import asdict, dataclass, field, fields
from pathlib import Path
from typing import BinaryIO

from pdfatolye.core.pdfio import safe_filename, safe_name_with_ext, split_ext, strip_ext
from pdfatolye.errors import PdfAtolyeError, disk_full_error, is_disk_full
from pdfatolye.formats import KINDS

__all__ = ["KINDS", "FileMeta", "FileStore", "FileNotInStoreError", "Version", "kind_of"]

CHUNK = 1024 * 1024
SCHEMA = 1  # meta.json biçim sürümü; yeni sürüm bilinmeyen alanları yok sayar
log = logging.getLogger("pdfatolye.storage")


class FileNotInStoreError(PdfAtolyeError):
    def __init__(self, file_id: str) -> None:
        super().__init__(f"Dosya bulunamadı (silinmiş olabilir): {file_id}")


class CorruptMetaError(FileNotInStoreError):
    """meta.json okunuyor ama içeriği bozuk (yarım yazılmış, elle değiştirilmiş...)."""


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
    tag: str | None = None  # "signature": İmzalarım listesinde
    schema: int = SCHEMA

    @property
    def current(self) -> Version:
        return self.versions[-1]

    @property
    def ext(self) -> str:
        return split_ext(self.name)[1].lower()

    def to_dict(self) -> dict:
        d = asdict(self)
        d["version"] = self.current.n
        d["size"] = self.current.size
        d["page_count"] = self.current.page_count
        d["updated"] = self.current.created
        return d


def kind_of(name: str) -> str:
    return KINDS.get(split_ext(Path(name).name)[1].lower(), "other")


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


_HEX32 = re.compile(r"^[0-9a-f]{32}$")
_META_FIELDS = {f.name for f in fields(FileMeta)}
_VERSION_FIELDS = {f.name for f in fields(Version)}


def file_ids_in(value) -> set[str]:
    """İş isteğinin içindeki bütün depo kimlikleri (iç içe listeler/sözlükler dahil)."""
    found: set[str] = set()
    stack = [value]
    while stack:
        v = stack.pop()
        if isinstance(v, str):
            if _HEX32.match(v):
                found.add(v)
        elif isinstance(v, dict):
            stack.extend(v.values())
        elif isinstance(v, (list, tuple, set)):
            stack.extend(v)
    return found


class FileStore:
    def __init__(self, root: Path, max_upload_mb: int = 1024) -> None:
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        self.max_bytes = max_upload_mb * 1024 * 1024
        self.max_upload_mb = max_upload_mb
        self._lock = threading.RLock()
        # Temizlik bunlara dokunmaz: işlerin kullandığı (sırada bekleyenler dahil) dosyalar ve
        # arayüzün yakın zamanda açtığı dosyalar (açık sayfa düzenli aralıklarla "dokunur").
        # Bellekte tutulur: sunucu yeniden başlarsa açık sekme ilk istekte yeniden dokunur.
        self._busy: Counter[str] = Counter()
        self._accessed: dict[str, float] = {}
        self._corrupt_logged: set[str] = set()

    # --- iç yardımcılar ---

    def _dir(self, file_id: str) -> Path:
        # Kimlik dışarıdan gelir: yalnızca onaltılık karakterler (yol saldırısı olmasın).
        if not file_id or not all(c in "0123456789abcdef" for c in file_id):
            raise FileNotInStoreError(file_id)
        return self.root / file_id

    def _save_meta(self, meta: FileMeta) -> None:
        d = self._dir(meta.id)
        tmp = d / "meta.json.tmp"
        try:
            tmp.write_text(json.dumps(asdict(meta), ensure_ascii=False, indent=1),
                           encoding="utf-8")
            tmp.replace(d / "meta.json")
        except OSError as e:
            if is_disk_full(e):
                raise disk_full_error() from e
            raise

    def _version_path(self, meta: FileMeta, n: int) -> Path:
        return self._dir(meta.id) / f"v{n}{meta.ext or '.bin'}"

    def _new(self, name: str, source: str, job_id: str | None) -> tuple[FileMeta, Path]:
        # Uzantı ayrı korunur: uzun adda kök kısalır, ".pdf" asla kesilmez (tür ondan anlaşılır).
        name = safe_name_with_ext(Path(name).name, fallback="dosya")
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

    @staticmethod
    def _copy_in(src: Path, dest: Path) -> None:
        try:
            shutil.copyfile(src, dest)
        except OSError as e:
            if is_disk_full(e):
                dest.unlink(missing_ok=True)
                raise disk_full_error() from e
            raise

    # --- dışa açık ---

    def add_stream(self, stream: BinaryIO, name: str) -> FileMeta:
        """Yüklemeyi parça parça diske yazar; sınırı aşarsa ya da disk dolarsa yarım dosyayı
        siler."""
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
        except BaseException as e:
            shutil.rmtree(self._dir(meta.id), ignore_errors=True)
            if isinstance(e, OSError) and is_disk_full(e):
                raise disk_full_error() from e
            raise
        return meta

    def add_file(self, src: Path, name: str, *, source: str = "job", job_id: str | None = None,
                 note: str = "Oluşturuldu", pinned: bool = False,
                 tag: str | None = None) -> FileMeta:
        meta, path = self._new(name, source, job_id)
        meta.pinned, meta.tag = pinned, tag
        try:
            self._copy_in(src, path)
            self._finish_version(meta, path, 1, note)
        except BaseException:
            shutil.rmtree(self._dir(meta.id), ignore_errors=True)
            raise
        return meta

    def new_version(self, file_id: str, src: Path, note: str) -> FileMeta:
        with self._lock:
            meta = self.get(file_id)
            n = meta.current.n + 1
            path = self._version_path(meta, n)
            self._copy_in(src, path)
            try:
                self._finish_version(meta, path, n, note)
            except BaseException:
                path.unlink(missing_ok=True)
                raise
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
        except FileNotFoundError as e:
            raise FileNotInStoreError(file_id) from e
        except (OSError, ValueError) as e:  # yarım yazılmış ya da bozuk JSON
            raise self._corrupt(file_id, e) from e
        try:
            # Bilinmeyen alanlar (daha yeni bir sürümün yazdıkları) yok sayılır.
            versions = [Version(**{k: v[k] for k in v if k in _VERSION_FIELDS})
                        for v in raw["versions"]]
            meta = FileMeta(**{k: raw[k] for k in raw if k in _META_FIELDS}
                            | {"versions": versions})
            if not versions or meta.id != file_id:
                raise ValueError("sürüm listesi boş ya da kimlik klasörle tutmuyor")
        except (KeyError, TypeError, ValueError, AttributeError) as e:
            raise self._corrupt(file_id, e) from e
        return meta

    def _corrupt(self, file_id: str, exc: Exception) -> CorruptMetaError:
        if file_id not in self._corrupt_logged:  # her temizlikte aynı satırı yazmasın
            self._corrupt_logged.add(file_id)
            log.warning("Bozuk dosya kaydı atlandı: %s (%s: %s)", file_id, type(exc).__name__,
                        exc)
        return CorruptMetaError(file_id)

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
                except PdfAtolyeError:  # bozuk kayıt günlüğe yazıldı; diğerleri listelensin
                    continue
        return sorted(out, key=lambda m: m.current.created, reverse=True)

    def set_pinned(self, file_id: str, pinned: bool) -> FileMeta:
        with self._lock:
            meta = self.get(file_id)
            meta.pinned = pinned
            self._save_meta(meta)
            return meta

    def rename(self, file_id: str, name: str) -> FileMeta:
        """Görünen adı değiştirir; uzantı korunur. Yazılan ad bilinen bir türün uzantısıyla
        bitiyorsa ("yeni.txt") o atılır; "Sürüm 1.2 son" ya da "Rapor v1.2" olduğu gibi kalır."""
        with self._lock:
            meta = self.get(file_id)
            given = Path(name).name
            stem, ext = split_ext(given)
            if ext.lower() not in KINDS:
                stem = strip_ext(given, meta.ext)
            stem = safe_filename(stem, fallback=Path(meta.name).stem)
            meta.name = stem + meta.ext
            self._save_meta(meta)
            return meta

    def delete(self, file_id: str) -> None:
        shutil.rmtree(self._dir(file_id), ignore_errors=True)
        self._accessed.pop(file_id, None)

    # --- temizlikten koruma ---

    def touch(self, file_id: str) -> None:
        """Arayüz dosyayı açtı ya da hâlâ açık tutuyor: son erişim zamanı yenilenir."""
        self._accessed[file_id] = time.time()

    def hold(self, file_ids: Iterable[str]) -> None:
        """Bir iş bu dosyaları kullanacak (sırada beklerken de): temizlik silmesin."""
        with self._lock:
            self._busy.update(i for i in file_ids if _HEX32.match(i))

    def release(self, file_ids: Iterable[str]) -> None:
        with self._lock:
            self._busy.subtract(i for i in file_ids if _HEX32.match(i))
            self._busy = +self._busy  # sıfıra inenleri at

    @contextlib.contextmanager
    def using(self, file_ids: Iterable[str]) -> Iterator[None]:
        ids = list(set(file_ids))
        self.hold(ids)
        try:
            yield
        finally:
            self.release(ids)

    def in_use(self, file_id: str) -> bool:
        return self._busy.get(file_id, 0) > 0

    def cleanup(self, retention_hours: float) -> int:
        """Süresi dolmuş, sabitlenmemiş dosyaları siler. Silinen dosya sayısını döndürür.

        Yaş son sürümden ya da arayüzdeki son erişimden (hangisi yeniyse) sayılır; bir işin
        kullandığı dosya silinmez. Bozuk kayıtlı klasörler silinmez (içindeki dosya elle
        kurtarılabilir), günlüğe yazılır."""
        now = time.time()
        limit = now - retention_hours * 3600
        removed = 0
        for d in list(self.root.iterdir()):
            if not d.is_dir():
                continue
            try:
                meta = self.get(d.name)
            except CorruptMetaError:
                continue
            except PdfAtolyeError:
                # meta'sız yarım klasör (çökme artığı): bir günden eskiyse sil
                with contextlib.suppress(OSError):
                    if d.stat().st_mtime < now - 86400:
                        shutil.rmtree(d, ignore_errors=True)
                continue
            with self._lock:  # hold() ile yarışmasın: iş tam bu anda dosyayı almak üzere olabilir
                last = max(meta.current.created, self._accessed.get(meta.id, 0.0))
                if meta.pinned or last >= limit or self.in_use(meta.id):
                    continue
                shutil.rmtree(d, ignore_errors=True)
                self._accessed.pop(meta.id, None)
            removed += 1
        return removed
