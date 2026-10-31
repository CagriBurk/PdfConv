"""Kullanıcıya gösterilecek hatalar. Mesajlar Türkçe ve ne yapılacağını söyler."""

from __future__ import annotations

from pathlib import Path


class PdfAtolyeError(Exception):
    """Tüm beklenen hataların tabanı. `str(e)` doğrudan kullanıcıya gösterilebilir."""


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
