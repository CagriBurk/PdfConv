"""Şifreleme, şifre kaldırma, meta veri temizliği ve onarım (pikepdf / qpdf).

Şifre kırma yok: şifre kaldırmak için açılış şifresi bilinmeli. Yalnızca sahip şifresiyle
kısıtlanmış (açılış şifresi olmayan) dosyalarda kısıtlar kaldırılabilir — kendi dosyaların için.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import pikepdf

from pdfatolye.core.pdfio import atomic_output
from pdfatolye.errors import BrokenPdfError, EncryptedPdfError, PdfAtolyeError

MIN_PASSWORD = 4


@dataclass
class SecurityResult:
    output: Path
    notes: list[str] = field(default_factory=list)


def _open(src: Path, password: str | None) -> pikepdf.Pdf:
    src = Path(src)
    try:
        return pikepdf.open(src, password=password or "")
    except pikepdf.PasswordError as e:
        raise EncryptedPdfError(src, wrong_password=bool(password)) from e
    except (pikepdf.PdfError, OSError, ValueError) as e:
        raise BrokenPdfError(src, "onarmayı dene") from e


def encrypt(src: Path, output: Path, user_password: str, *, owner_password: str | None = None,
            allow_print: bool = True, allow_copy: bool = True, allow_modify: bool = True,
            password: str | None = None) -> SecurityResult:
    """AES-256 ile şifreler. Sahip şifresi verilmezse rastgele değil, açılış şifresiyle aynı
    olur (kullanıcı kendi dosyasının izinlerini sonra değiştirebilsin)."""
    if len(user_password) < MIN_PASSWORD:
        raise PdfAtolyeError(f"Şifre en az {MIN_PASSWORD} karakter olmalı.")
    owner = owner_password or user_password
    perms = pikepdf.Permissions(
        print_lowres=allow_print, print_highres=allow_print,
        extract=allow_copy, accessibility=True,
        modify_annotation=allow_modify, modify_form=allow_modify, modify_other=allow_modify,
        modify_assembly=allow_modify,
    )
    with _open(src, password) as pdf, atomic_output(output) as tmp:
        pdf.save(tmp, encryption=pikepdf.Encryption(user=user_password, owner=owner, R=6,
                                                    aes=True, allow=perms))
    notes = ["AES-256 ile şifrelendi."]
    if not (allow_print and allow_copy and allow_modify):
        notes.append("İzin kısıtları her PDF okuyucusunda uygulanmayabilir; asıl koruma "
                     "açılış şifresidir.")
    return SecurityResult(Path(output), notes)


def decrypt(src: Path, output: Path, password: str | None = None) -> SecurityResult:
    with _open(src, password) as pdf:
        if not pdf.is_encrypted:
            raise PdfAtolyeError(f"'{Path(src).name}' zaten şifresiz.")
        with atomic_output(output) as tmp:
            pdf.save(tmp, encryption=False)
    note = "Şifre kaldırıldı." if password else "Kısıtlar kaldırıldı (açılış şifresi yoktu)."
    return SecurityResult(Path(output), [note])


def clean_metadata(src: Path, output: Path, password: str | None = None) -> SecurityResult:
    """Yazar, oluşturan program, XMP, gömülü dosyalar, belge JavaScript'i ve sayfa düzeyi
    özel veriler (PieceInfo) silinir. Görünen içerik değişmez."""
    removed: list[str] = []
    with _open(src, password) as pdf:
        info_keys = [str(k).lstrip("/") for k in pdf.docinfo.keys()]  # noqa: SIM118
        if info_keys:
            removed.append("belge bilgileri (" + ", ".join(info_keys) + ")")
            del pdf.trailer.Info
        root = pdf.Root
        if "/Metadata" in root:
            del root.Metadata
            removed.append("XMP meta verisi")
        names = root.get("/Names")
        if names is not None:
            for key, label in (("/EmbeddedFiles", "gömülü dosyalar"),
                               ("/JavaScript", "belge JavaScript'i")):
                if key in names:
                    del names[key]
                    removed.append(label)
        if "/OpenAction" in root and root.OpenAction.get("/S") == "/JavaScript":
            del root.OpenAction
            removed.append("açılış JavaScript'i")
        for key in ("/PieceInfo", "/AA"):
            if key in root:
                del root[key]
        pieces = 0
        for page in pdf.pages:
            for key in ("/PieceInfo", "/Metadata"):
                if key in page.obj:
                    del page.obj[key]
                    pieces += 1
        if pieces:
            removed.append(f"sayfa düzeyi özel veri ({pieces})")
        with atomic_output(output) as tmp:
            pdf.save(tmp, fix_metadata_version=False, deterministic_id=True)
    notes = ["Silinenler: " + "; ".join(removed)] if removed else ["Temizlenecek meta veri yoktu."]
    return SecurityResult(Path(output), notes)


def repair(src: Path, output: Path, password: str | None = None) -> SecurityResult:
    """qpdf'in onarımıyla açıp yeniden yazar; olmazsa MuPDF'in onarımını dener."""
    src = Path(src)
    notes: list[str] = []
    try:
        with pikepdf.open(src, password=password or "",
                          attempt_recovery=True) as pdf, atomic_output(output) as tmp:
            pdf.save(tmp, object_stream_mode=pikepdf.ObjectStreamMode.generate)
            if pdf.get_warnings():
                notes.append(f"{len(pdf.get_warnings())} sorun düzeltildi.")
        notes.insert(0, "qpdf ile yeniden yazıldı.")
        return SecurityResult(Path(output), notes)
    except pikepdf.PasswordError as e:
        raise EncryptedPdfError(src, wrong_password=bool(password)) from e
    except (pikepdf.PdfError, OSError) as first:
        import pymupdf

        try:
            doc = pymupdf.open(src, filetype="pdf")
        except Exception as e:
            raise BrokenPdfError(src, "onarılamadı") from e
        with doc:
            if doc.needs_pass and not doc.authenticate(password or ""):
                raise EncryptedPdfError(src, wrong_password=bool(password)) from first
            if doc.page_count == 0:
                raise BrokenPdfError(src, "hiç sayfa kurtarılamadı") from first
            with atomic_output(output) as tmp:
                doc.save(tmp, garbage=4, clean=True, deflate=True)
            notes = [f"MuPDF ile kurtarıldı ({doc.page_count} sayfa)."]
    return SecurityResult(Path(output), notes)
