"""İş isteklerinin şemaları. Her tür ayrı doğrulanır (Pydantic, `type` alanına göre)."""

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import BaseModel, Field, model_validator

FileId = Annotated[str, Field(pattern=r"^[0-9a-f]{32}$")]
Passwords = dict[FileId, str]


class _Base(BaseModel):
    model_config = {"extra": "forbid"}
    # Şifreler yalnızca bellekte tutulur; iş kaydına yazılmaz.
    passwords: Passwords = Field(default_factory=dict, exclude=True)


class PageItem(BaseModel):
    model_config = {"extra": "forbid"}
    file: FileId | None = None
    page: int = Field(default=0, ge=0)
    rotate: int = 0
    blank: bool = False
    width: float | None = Field(default=None, gt=0, le=14400)
    height: float | None = Field(default=None, gt=0, le=14400)

    @model_validator(mode="after")
    def _check(self) -> PageItem:
        if not self.blank and self.file is None:
            raise ValueError("Sayfa için 'file' gerekli (boş sayfa değilse).")
        if self.rotate % 90:
            raise ValueError("Döndürme 90'ın katı olmalı.")
        return self


class ComposeRequest(_Base):
    type: Literal["compose"]
    items: list[PageItem] = Field(min_length=1, max_length=20_000)
    target: Literal["version", "new"] = "new"
    base_file: FileId | None = None  # target="version" ise sürümü eklenecek dosya
    name: str | None = None
    keep_bookmarks: bool = True

    @model_validator(mode="after")
    def _check(self) -> ComposeRequest:
        if self.target == "version" and not self.base_file:
            raise ValueError("Yeni sürüm için 'base_file' gerekli.")
        return self


class MergeRequest(_Base):
    type: Literal["merge"]
    files: list[FileId] = Field(min_length=2, max_length=500)
    bookmark_per_file: bool = False
    name: str | None = None


class SplitRequest(_Base):
    type: Literal["split"]
    file: FileId
    mode: Literal["her", "n", "aralik", "yer-imi"] = "her"
    every: int = Field(default=1, ge=1, le=10_000)
    spec: str = Field(default="", max_length=2000)


class ImagesToPdfRequest(_Base):
    type: Literal["images_to_pdf"]
    files: list[FileId] = Field(min_length=1, max_length=2000)
    page_size: Literal["A4", "A3", "A5", "Letter", "Legal", "resim"] = "A4"
    orientation: Literal["otomatik", "dikey", "yatay"] = "otomatik"
    margin_mm: float = Field(default=0, ge=0, le=50)
    name: str | None = None


class PdfToImagesRequest(_Base):
    type: Literal["pdf_to_images"]
    file: FileId
    dpi: int = Field(default=150, ge=36, le=600)
    fmt: Literal["png", "jpg"] = "png"
    spec: str = Field(default="", max_length=2000)


class MdOptionsModel(BaseModel):
    model_config = {"extra": "forbid"}
    theme: Literal["ders", "rapor", "sade"] | None = None
    paper: Literal["A4", "A5", "A3", "Letter", "Legal"] | None = None
    landscape: bool | None = None
    margin_mm: float | None = Field(default=None, ge=0, le=60)
    toc: bool | None = None
    toc_depth: int | None = Field(default=None, ge=1, le=6)
    cover: bool | None = None
    page_numbers: bool | None = None
    font_size_pt: float | None = Field(default=None, ge=6, le=24)


class MdToPdfRequest(_Base):
    type: Literal["md_to_pdf"]
    file: FileId | None = None  # ya yüklenmiş .md ...
    text: str | None = Field(default=None, max_length=5_000_000)  # ... ya da düzenlenmiş metin
    name: str = "belge.md"
    attachments: list[FileId] = Field(default_factory=list, max_length=2000)
    options: MdOptionsModel = Field(default_factory=MdOptionsModel)

    @model_validator(mode="after")
    def _check(self) -> MdToPdfRequest:
        if self.file is None and self.text is None:
            raise ValueError("'file' ya da 'text' gerekli.")
        return self


class OfficeToPdfRequest(_Base):
    """Office / HTML / düz metin dosyalarını PDF'e çevirir. Bozuk bir dosya diğerlerini
    durdurmaz; uyarı olarak bildirilir. `merge` ise başarılı çıktılar tek PDF'te birleştirilir."""

    type: Literal["office_to_pdf"]
    files: list[FileId] = Field(min_length=1, max_length=500)
    pdfa: bool = False
    merge: bool = False
    name: str | None = None


JobRequest = Annotated[
    ComposeRequest | MergeRequest | SplitRequest | ImagesToPdfRequest | PdfToImagesRequest
    | MdToPdfRequest | OfficeToPdfRequest,
    Field(discriminator="type"),
]
