"""Kullanıcıya gösterilecek hatalar. Mesajlar Türkçe ve ne yapılacağını söyler."""

from __future__ import annotations

from pathlib import Path


class PdfAtolyeError(Exception):
    """Tüm beklenen hataların tabanı. `str(e)` doğrudan kullanıcıya gösterilebilir."""


def error_id() -> str:
    """Beklenmeyen hatalar için kısa kimlik: kullanıcı mesajında ve günlükte aynısı geçer."""
    import uuid

    return uuid.uuid4().hex[:8]


def unexpected_message(exc: BaseException, eid: str) -> str:
    return (f"Beklenmeyen hata ({type(exc).__name__}). Hata kimliği: {eid}. Ayrıntı günlük "
            "dosyasında (Ayarlar sayfasında yolu yazar).")


_DISK_FULL_ERRNO = {28}  # ENOSPC
_DISK_FULL_WINERROR = {39, 112}  # ERROR_HANDLE_DISK_FULL, ERROR_DISK_FULL


def is_disk_full(exc: BaseException) -> bool:
    return isinstance(exc, OSError) and (
        exc.errno in _DISK_FULL_ERRNO or getattr(exc, "winerror", None) in _DISK_FULL_WINERROR)


class DiskFullError(PdfAtolyeError):
    def __init__(self, where: str = "") -> None:
        super().__init__("Diskte yer kalmadı" + (f" ({where})" if where else "") + ". Biraz yer "
                         "aç (İşler ve dosyalar sayfasından eski dosyaları silebilirsin) ve "
                         "yeniden dene.")


def disk_full_error(where: str = "") -> DiskFullError:
    return DiskFullError(where)


class PageRangeError(PdfAtolyeError, ValueError):
    pass


class EncryptedPdfError(PdfAtolyeError):
    def __init__(self, path: Path, wrong_password: bool = False) -> None:
        self.path = path
        self.wrong_password = wrong_password
        if wrong_password:
            msg = f"'{path.name}' için girilen şifre yanlış."
        else:
            msg = f"'{path.name}' şifreli. Açmak için şifresini gir."
        super().__init__(msg)


class BrokenPdfError(PdfAtolyeError):
    def __init__(self, path: Path, detail: str = "") -> None:
        self.path = path
        msg = f"'{path.name}' açılamadı; dosya bozuk olabilir."
        if detail:
            msg += f" ({detail})"
        super().__init__(msg)


class UnsupportedFileError(PdfAtolyeError):
    def __init__(self, path: Path, expected: str) -> None:
        self.path = path
        super().__init__(f"'{path.name}' bir {expected} dosyası değil.")


class ImageTooLargeError(PdfAtolyeError):
    """Pillow'un sıkıştırma bombası koruması (`DecompressionBombError`) ya da aşırı büyük resim."""

    def __init__(self, path: Path) -> None:
        self.path = path
        super().__init__(f"'{path.name}' çok büyük bir resim (yüz milyonlarca piksel); güvenlik "
                         "için açılmadı. Resmi küçültüp (ör. 8000 piksel kenara) yeniden dene.")
