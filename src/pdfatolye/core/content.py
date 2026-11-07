"""İçerik ekleme: yazı, resim/imza, vurgu, şekil, karartma, beyazla kapatma, filigran,
sayfa numarası.

Editör her şeyi tarayıcıda nesne olarak tutar; "Uygula" denince bu işlem listesi gelir.
Koordinatlar **görünüm** uzayında (bkz. `geometry.py`): kullanıcının gördüğü sayfa, sol üst
(0, 0), y aşağı, PDF noktası. Döndürülmüş sayfa ve kaydırılmış CropBox burada değil,
`geometry.py`'de çözülür.

Uygulama sırası (her sayfa için): önce karartma ve beyazla kapatma (alttaki içerik silinir),
sonra sayfa işlemleri listedeki sırayla, en son filigran ve sayfa numarası. Böylece karartma
aynı uygulamada eklenen yazıyı silmez.
"""

from __future__ import annotations

import io
import math
from collections import defaultdict
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Annotated, Literal

import pymupdf
from PIL import Image, ImageOps, UnidentifiedImageError
from pydantic import BaseModel, Field, field_validator, model_validator

from pdfatolye.core import fonts as fontlib
from pdfatolye.core import geometry as geo
from pdfatolye.core import images as _images  # noqa: F401  (HEIC açıcısını kaydeder)
from pdfatolye.core.pdfio import atomic_output, opened, save_pdf
from pdfatolye.core.ranges import parse_ranges
from pdfatolye.errors import (
    ImageTooLargeError,
    PageRangeError,
    PdfAtolyeError,
    UnsupportedFileError,
)

Color = Annotated[str, Field(pattern=r"^#[0-9a-fA-F]{6}$")]
FontKey = Literal["segoe", "arial", "calibri", "times", "georgia", "consolas"]
Coord = Annotated[float, Field(ge=-20_000, le=20_000)]
Opacity = Annotated[float, Field(ge=0, le=1)]

# Resim, kutusunda bu çözünürlükten fazlasıyla gömülmez (4000 px fotoğraf → küçük imza).
IMAGE_DPI = 300
MAX_OPS = 5000


def _rgb(color: str) -> tuple[float, float, float]:
    return tuple(int(color[i:i + 2], 16) / 255 for i in (1, 3, 5))  # type: ignore[return-value]


# --- işlem şemaları -------------------------------------------------------------------------


class _Op(BaseModel):
    model_config = {"extra": "forbid"}


class _PageOp(_Op):
    page: int = Field(ge=0, description="0 tabanlı sayfa")


class _BoxOp(_PageOp):
    rect: list[Coord] = Field(min_length=4, max_length=4, description="[x0, y0, x1, y1]")

    @field_validator("rect")
    @classmethod
    def _rect(cls, v: list[float]) -> list[float]:
        x0, y0, x1, y1 = min(v[0], v[2]), min(v[1], v[3]), max(v[0], v[2]), max(v[1], v[3])
        if x1 - x0 < 0.5 or y1 - y0 < 0.5:
            raise ValueError("Kutu çok küçük.")
        return [x0, y0, x1, y1]


class TextOp(_BoxOp):
    type: Literal["text"]
    text: str = Field(min_length=1, max_length=20_000)
    font: FontKey = "segoe"
    bold: bool = False
    size: float = Field(default=12, ge=4, le=400)
    color: Color = "#1a1a1a"
    align: Literal["left", "center", "right", "justify"] = "left"
    line_height: float = Field(default=1.2, ge=0.8, le=3)
    opacity: Opacity = 1
    rotation: float = Field(default=0, description="saat yönünde, kutu merkezi etrafında")


class ImageOp(_BoxOp):
    """Resim ya da imza. `asset`: resmin anahtarı (depoda dosya kimliği)."""

    type: Literal["image"]
    asset: str = Field(min_length=1, max_length=260)
    keep_aspect: bool = True
    opacity: Opacity = 1
    rotation: float = 0


class HighlightOp(_BoxOp):
    """Kutunun altındaki satırlar vurgulanır; altında yazı yoksa kutunun kendisi."""

    type: Literal["highlight"]
    color: Color = "#ffe066"
    opacity: Opacity = 1


class ShapeOp(_BoxOp):
    type: Literal["rect", "ellipse"]
    stroke: Color | None = "#d00000"
    fill: Color | None = None
    width: float = Field(default=1.5, ge=0, le=50)
    opacity: Opacity = 1
    rotation: float = 0

    @model_validator(mode="after")
    def _visible(self) -> ShapeOp:
        if self.fill is None and (self.stroke is None or self.width == 0):
            raise ValueError("Şeklin ne çizgisi ne dolgusu var.")
        return self


class LineOp(_PageOp):
    type: Literal["line", "arrow"]
    points: list[Coord] = Field(min_length=4, max_length=4, description="[x1, y1, x2, y2]")
    stroke: Color = "#d00000"
    width: float = Field(default=2, gt=0, le=50)
    opacity: Opacity = 1


class RedactOp(_BoxOp):
    """Gerçek karartma: altındaki yazı, resim pikselleri ve çizimler dosyadan silinir."""

    type: Literal["redact"]
    fill: Color = "#000000"


class WhiteoutOp(_BoxOp):
    """Beyazla kapat: alttaki yazı silinir, kutu renge boyanır; üstüne yeni yazı eklenebilir.
    Karartmadan farkı: resimlere ve çizgilere dokunmaz (yalnızca üstü örtülür)."""

    type: Literal["whiteout"]
    color: Color = "#ffffff"


class WatermarkOp(_Op):
    type: Literal["watermark"]
    pages: str = Field(default="", max_length=2000, description="1 tabanlı aralık; boş = tümü")
    text: str | None = Field(default=None, max_length=200)
    asset: str | None = Field(default=None, max_length=260)
    font: FontKey = "segoe"
    bold: bool = True
    size: float = Field(default=72, ge=6, le=400)
    color: Color = "#888888"
    opacity: Opacity = 0.2
    angle: float = Field(default=45, description="saat yönünün tersine (yükselen çapraz)")
    layer: Literal["front", "back"] = "front"
    scale: float = Field(default=0.5, gt=0, le=1, description="resim genişliği / sayfa")

    @model_validator(mode="after")
    def _one(self) -> WatermarkOp:
        if self.text is not None:
            self.text = " ".join(self.text.split())
        if bool(self.text) == bool(self.asset):
            raise ValueError("Filigran için ya yazı ya da resim ver.")
        return self


Position = Literal["top-left", "top-center", "top-right",
                   "bottom-left", "bottom-center", "bottom-right"]


class PageNumbersOp(_Op):
    type: Literal["page_numbers"]
    format: str = Field(default="{n}", min_length=3, max_length=100)
    position: Position = "bottom-center"
    start: int = Field(default=1, ge=0, le=1_000_000)
    skip_first: bool = False
    pages: str = Field(default="", max_length=2000)
    font: FontKey = "segoe"
    bold: bool = False
    size: float = Field(default=11, ge=4, le=72)
    color: Color = "#333333"
    margin: float = Field(default=28, ge=0, le=300, description="kenardan uzaklık (pt)")

    @field_validator("format")
    @classmethod
    def _format(cls, v: str) -> str:
        if "{n}" not in v:
            raise ValueError("Biçimde {n} olmalı. Örnek: Sayfa {n} / {N}")
        return v


Op = Annotated[
    TextOp | ImageOp | HighlightOp | ShapeOp | LineOp | RedactOp | WhiteoutOp | WatermarkOp
    | PageNumbersOp,
    Field(discriminator="type"),
]
PAGE_OPS = (TextOp, ImageOp, HighlightOp, ShapeOp, LineOp, RedactOp, WhiteoutOp)


@dataclass
class ApplyResult:
    output: Path
    warnings: list[str] = field(default_factory=list)


# --- yardımcılar ----------------------------------------------------------------------------


def _clean_text(text: str) -> str:
    return text.replace("\r\n", "\n").replace("\r", "\n").replace("\xa0", " ") \
        .replace("\t", "    ")


def _number_label(op: PageNumbersOp, n: int, total: int) -> str:
    # str.format değil: kullanıcı metnindeki başka {} ifadeleri hata/sızıntı olmasın.
    return op.format.replace("{n}", str(n)).replace("{N}", str(total))


def _morph(page: pymupdf.Page, view_rect: pymupdf.Rect, angle_cw: float):
    if not angle_cw % 360:
        return None
    c = (view_rect.tl + view_rect.br) / 2
    return geo.view_to_page_point(page, c.x, c.y), geo.morph_matrix(angle_cw)


class _Images:
    """Resimleri bir kez açar; aynı resim aynı ayarlarla tekrar kullanılınca PDF'e bir kez
    gömülür (her sayfadaki imza aynı nesne)."""

    def __init__(self, assets: Mapping[str, Path]) -> None:
        self.assets = assets
        self._img: dict[str, Image.Image] = {}
        self._xref: dict[tuple, int] = {}

    def image(self, key: str) -> Image.Image:
        if key not in self._img:
            path = self.assets.get(key)
            if path is None:
                raise PdfAtolyeError(f"Resim bulunamadı: {key}. Resmi yeniden ekle.")
            try:
                with Image.open(path) as im:
                    im = ImageOps.exif_transpose(im)
                    im.load()
                    alpha = im.mode in ("RGBA", "LA", "PA") or "transparency" in im.info
                    self._img[key] = im.convert("RGBA" if alpha else "RGB")
            except Image.DecompressionBombError as e:
                raise ImageTooLargeError(Path(path)) from e
            except (UnidentifiedImageError, OSError) as e:
                raise UnsupportedFileError(Path(path), "resim") from e
        return self._img[key]

    def insert(self, page: pymupdf.Page, key: str, view_box: pymupdf.Rect, *,
               opacity: float = 1, angle_cw: float = 0, overlay: bool = True,
               keep_aspect: bool = True) -> None:
        img = self.image(key)
        box = geo.fit_inside(view_box, img.width, img.height) if keep_aspect else view_box
        # Kutunun gerektirdiğinden büyük resmi küçült (IMAGE_DPI), ölçüyü sabitle ki aynı
        # imza farklı boyda da olsa önbellek birkaç değerde toplansın.
        target = max(box.width, box.height) * IMAGE_DPI / 72
        longest = max(img.width, img.height)
        limit = 2 ** math.ceil(math.log2(max(target, 64)))
        size = min(longest, limit)
        stretch = None if keep_aspect else round(box.width / box.height, 3)
        cache = (key, size, round(opacity, 3), round(angle_cw % 360, 2), stretch)
        bbox = geo.rotated_bbox(box, angle_cw)
        rect = geo.view_to_page_rect(page, bbox)
        xref = self._xref.get(cache, 0)
        if xref:
            page.insert_image(rect, xref=xref, keep_proportion=False,
                              rotate=geo.text_rotate(page), overlay=overlay)
            return
        work = img
        if size < longest:
            work = img.copy()
            work.thumbnail((size, size), Image.Resampling.LANCZOS)
        if stretch:  # oran korunmuyor: önce kutuya gerilir, sonra döner
            ratio = box.width / box.height
            w = max(work.width, round(work.height * ratio))
            work = work.resize((w, max(1, round(w / ratio))), Image.Resampling.LANCZOS)
        if opacity < 1:
            work = work.convert("RGBA")
            alpha = work.getchannel("A").point(lambda a: round(a * opacity))
            work.putalpha(alpha)
        if angle_cw % 360:
            work = work.convert("RGBA").rotate(-angle_cw, expand=True,
                                               resample=Image.Resampling.BICUBIC)
        buf = io.BytesIO()
        if work.mode == "RGBA":
            work.save(buf, "PNG", optimize=True)
        else:
            work.convert("RGB").save(buf, "JPEG", quality=90)
        xref = page.insert_image(rect, stream=buf.getvalue(), keep_proportion=False,
                                 rotate=geo.text_rotate(page), overlay=overlay)
        self._xref[cache] = xref


# --- tek tek işlemler -----------------------------------------------------------------------


def _text(page: pymupdf.Page, op: TextOp, fonts: fontlib.FontSet, warnings: list[str]) -> None:
    name, _ = fonts.use(page, op.font, op.bold)
    text = _clean_text(op.text)
    box = pymupdf.Rect(op.rect)
    align = {"left": 0, "center": 1, "right": 2, "justify": 3}[op.align]
    for _attempt in range(4):
        rc = page.insert_textbox(
            geo.view_to_page_rect(page, box), text, fontname=name, fontsize=op.size,
            color=_rgb(op.color), align=align, lineheight=op.line_height,
            rotate=geo.text_rotate(page), fill_opacity=op.opacity,
            morph=_morph(page, box, op.rotation),
        )
        if rc >= 0:
            return
        # Sığmadı (hiçbir şey yazılmadı): kutuyu eksik kadar aşağı uzat, yeniden dene.
        box.y1 += -rc + 1
    warnings.append(f"{op.page + 1}. sayfadaki yazı kutuya sığmadı: “{text[:30]}…”")


def _highlight(page: pymupdf.Page, op: HighlightOp) -> None:
    area = geo.view_to_page_rect(page, op.rect)
    lines: dict[tuple[int, int], pymupdf.Rect] = {}
    for x0, y0, x1, y1, _w, block, line, _n in page.get_text("words"):
        word = pymupdf.Rect(x0, y0, x1, y1)
        center = (word.tl + word.br) / 2
        if center in area:
            key = (block, line)
            lines[key] = lines[key] | word if key in lines else word
    quads = [r.quad for r in lines.values()] or [area.quad]
    annot = page.add_highlight_annot(quads=quads)
    annot.set_colors(stroke=_rgb(op.color))
    annot.set_opacity(op.opacity)
    annot.update()


def _shape(page: pymupdf.Page, op: ShapeOp) -> None:
    shape = page.new_shape()
    rect = geo.view_to_page_rect(page, op.rect)
    if op.type == "rect":
        shape.draw_rect(rect)
    else:
        shape.draw_oval(rect)
    stroke = op.stroke if op.width > 0 else None
    shape.finish(color=_rgb(stroke) if stroke else None, fill=_rgb(op.fill) if op.fill else None,
                 width=op.width if stroke else 0, stroke_opacity=op.opacity,
                 fill_opacity=op.opacity, morph=_morph(page, pymupdf.Rect(op.rect), op.rotation))
    shape.commit()


def _line(page: pymupdf.Page, op: LineOp) -> None:
    p1 = geo.view_to_page_point(page, op.points[0], op.points[1])
    p2 = geo.view_to_page_point(page, op.points[2], op.points[3])
    color = _rgb(op.stroke)
    shape = page.new_shape()
    length = abs(p2 - p1)
    if op.type == "arrow" and length > 0:
        d = (p2 - p1) / length
        n = pymupdf.Point(-d.y, d.x)
        head = min(max(8, op.width * 4), length)
        base = p2 - d * head
        shape.draw_line(p1, p2 - d * head * 0.8)
        shape.finish(color=color, width=op.width, stroke_opacity=op.opacity, closePath=False)
        shape.draw_polyline([p2, base + n * head * 0.5, base - n * head * 0.5])
        shape.finish(color=color, fill=color, width=0, fill_opacity=op.opacity,
                     stroke_opacity=op.opacity, closePath=True)
    else:
        shape.draw_line(p1, p2)
        shape.finish(color=color, width=op.width, stroke_opacity=op.opacity, lineCap=1,
                     closePath=False)
    shape.commit()


def _strip_overlapping(page: pymupdf.Page, areas: Sequence[pymupdf.Rect]) -> None:
    """Kutulara değen açıklama (not, serbest metin...) ve form alanlarını siler. Bunlar sayfa
    içeriğinin üstünde ayrı nesnelerdir: `apply_redactions` onlara dokunmaz, karartılan yerde
    görünmeye ve dosyada okunmaya devam ederlerdi. Bağlantıları `apply_redactions` kaldırır."""
    def overlaps(rect: pymupdf.Rect) -> bool:
        return any(rect.intersects(area) for area in areas)

    for xref in [a.xref for a in page.annots() if overlaps(a.rect)]:
        page.delete_annot(page.load_annot(xref))
    for xref in [w.xref for w in page.widgets() if overlaps(w.rect)]:
        page.delete_widget(page.load_widget(xref))


def _remove_under(page: pymupdf.Page, ops: Sequence[RedactOp | WhiteoutOp]) -> None:
    whiteouts = [o for o in ops if isinstance(o, WhiteoutOp)]
    redacts = [o for o in ops if isinstance(o, RedactOp)]
    _strip_overlapping(page, [geo.view_to_page_rect(page, o.rect) for o in ops])
    if redacts:
        # Sayfanın küçük resmi ve üreten programın özel verisi karartılmamış içeriği taşıyabilir.
        for key in ("Thumb", "PieceInfo"):
            page.parent.xref_set_key(page.xref, key, "null")
    if whiteouts:
        for o in whiteouts:
            page.add_redact_annot(geo.view_to_page_rect(page, o.rect), fill=_rgb(o.color))
        page.apply_redactions(images=pymupdf.PDF_REDACT_IMAGE_NONE,
                              graphics=pymupdf.PDF_REDACT_LINE_ART_NONE)
    if redacts:
        for o in redacts:
            page.add_redact_annot(geo.view_to_page_rect(page, o.rect), fill=_rgb(o.fill))
        # Resimlerin yalnızca kutudaki pikselleri, çizimlerin tamamen kutuda kalanları silinir;
        # sayfa boyu bir arka plan çizgisi kutuya değdi diye kaybolmasın.
        page.apply_redactions(images=pymupdf.PDF_REDACT_IMAGE_PIXELS,
                              graphics=pymupdf.PDF_REDACT_LINE_ART_REMOVE_IF_COVERED)


def _normalized(text: str) -> str:
    return " ".join(text.split()).casefold()


def _redaction_warnings(doc: pymupdf.Document, redacted: dict[int, list[str]]) -> list[str]:
    """Karartma yalnızca işaretlenen kutuyu temizler. Aynı metin belgenin başka yerinde geçiyorsa
    kullanıcı bilmeli: yer imleri, belge bilgileri, öteki sayfalar, gömülü dosyalar."""
    phrases = {p for texts in redacted.values() for p in map(_normalized, texts) if len(p) >= 3}
    words = {w for p in phrases for w in p.split() if len(w) >= 4}
    warnings: list[str] = []

    def mentions(text: str) -> bool:
        text = _normalized(text)
        return any(w in text for w in words)

    if any(mentions(str(entry[1])) for entry in doc.get_toc(simple=True)):
        warnings.append("Karartılan metin yer imlerinde de geçiyor; yer imleri değişmedi.")
    meta_text = " ".join(str(v) for v in (doc.metadata or {}).values() if v)
    if mentions(meta_text) or mentions(doc.get_xml_metadata() or ""):
        warnings.append("Karartılan metin belge bilgilerinde de geçiyor. Güvenlik ve Bakım → "
                        "Meta veri temizle ile silebilirsin.")
    others = []
    for i, page in enumerate(doc):
        text = _normalized(page.get_text())
        extras = [str(a.info.get("content", "")) for a in page.annots()]
        extras += [str(w.field_value or "") for w in page.widgets()]
        if any(p in text for p in phrases) or any(mentions(x) for x in extras):
            others.append(i + 1)
    if others:
        pages = ", ".join(map(str, others[:10])) + ("…" if len(others) > 10 else "")
        warnings.append(f"Karartılan metin başka yerlerde de geçiyor (sayfa {pages}); o yerler "
                        "karartılmadı.")
    if doc.embfile_count():
        warnings.append("Bu PDF'te gömülü dosya var; karartma onlara dokunmaz. Güvenlik ve Bakım → "
                        "Meta veri temizle ile silebilirsin.")
    return warnings


def _watermark(doc: pymupdf.Document, op: WatermarkOp, fonts: fontlib.FontSet,
               images: _Images) -> None:
    overlay = op.layer == "front"
    for idx in dict.fromkeys(parse_ranges(op.pages, doc.page_count)):
        page = doc[idx]
        vw, vh = geo.view_size(page)
        center = pymupdf.Point(vw / 2, vh / 2)
        if op.text:
            name, font = fonts.use(page, op.font, op.bold)
            width = font.text_length(op.text, op.size)
            # Yazı ortası sayfa ortasına gelsin: taban çizgisi yüksekliğin yarısı kadar aşağıda.
            base = pymupdf.Point(center.x - width / 2,
                                 center.y + op.size * (font.ascender + font.descender) / 2)
            pivot = geo.view_to_page_point(page, center.x, center.y)
            page.insert_text(geo.view_to_page_point(page, base.x, base.y), op.text,
                             fontname=name, fontsize=op.size, color=_rgb(op.color),
                             rotate=geo.text_rotate(page), fill_opacity=op.opacity,
                             morph=(pivot, geo.morph_matrix(-op.angle)),
                             overlay=overlay)
        else:
            img = images.image(op.asset or "")
            w = vw * op.scale
            h = w * img.height / img.width
            box = pymupdf.Rect(center.x - w / 2, center.y - h / 2, center.x + w / 2,
                               center.y + h / 2)
            images.insert(page, op.asset or "", box, opacity=op.opacity, angle_cw=-op.angle,
                          overlay=overlay)


def _page_numbers(doc: pymupdf.Document, op: PageNumbersOp, fonts: fontlib.FontSet) -> None:
    targets = [p for p in dict.fromkeys(parse_ranges(op.pages, doc.page_count))
               if not (op.skip_first and p == 0)]
    total = op.start + len(targets) - 1
    vertical, horizontal = op.position.split("-")
    for i, idx in enumerate(targets):
        page = doc[idx]
        name, font = fonts.use(page, op.font, op.bold)
        label = _number_label(op, op.start + i, total)
        vw, vh = geo.view_size(page)
        width = font.text_length(label, op.size)
        x = {"left": op.margin, "center": (vw - width) / 2,
             "right": vw - op.margin - width}[horizontal]
        if vertical == "top":
            y = op.margin + op.size * font.ascender
        else:
            y = vh - op.margin + op.size * font.descender  # descender < 0
        page.insert_text(geo.view_to_page_point(page, x, y), label, fontname=name,
                         fontsize=op.size, color=_rgb(op.color), rotate=geo.text_rotate(page))


def _declare_fonts(ops: Sequence, fonts: fontlib.FontSet, warnings: list[str]) -> None:
    """Alt küme üretilmeden önce yazılacak her metin bilinmeli."""
    for op in ops:
        if isinstance(op, TextOp):
            text = _clean_text(op.text)
        elif isinstance(op, WatermarkOp) and op.text:
            text = op.text
        elif isinstance(op, PageNumbersOp):
            text = op.format + "0123456789"
        else:
            continue
        fonts.need(op.font, op.bold, text)
        missing = fonts.missing_chars(op.font, op.bold, text)
        if missing:
            name = fontlib.FAMILIES[op.font][0]
            warnings.append(f"{name} fontunda şu karakterler yok, kutucuk olarak çıkabilir: "
                            + " ".join(missing))


def apply_ops(src: Path, output: Path, ops: Sequence, *, password: str | None = None,
              assets: Mapping[str, Path] | None = None) -> ApplyResult:
    """İşlem listesini PDF'e uygular ve `output`'a yazar."""
    if not ops:
        raise PdfAtolyeError("Uygulanacak bir değişiklik yok.")
    if len(ops) > MAX_OPS:
        raise PdfAtolyeError(f"Tek seferde en fazla {MAX_OPS} değişiklik uygulanabilir.")
    warnings: list[str] = []
    images = _Images(assets or {})
    fonts = fontlib.FontSet()
    with opened(src, password) as doc:
        n = doc.page_count
        by_page: dict[int, list] = defaultdict(list)
        doc_ops = []
        for op in ops:
            if isinstance(op, PAGE_OPS):
                if op.page >= n:
                    raise PageRangeError(f"{op.page + 1}. sayfa yok; belgede {n} sayfa var.")
                by_page[op.page].append(op)
            else:
                doc_ops.append(op)
        _declare_fonts(ops, fonts, warnings)

        redacted: dict[int, list[str]] = {}
        for idx in sorted(by_page):
            page = doc[idx]
            page_ops = by_page[idx]
            removals = [o for o in page_ops if isinstance(o, (RedactOp, WhiteoutOp))]
            boxes = [geo.view_to_page_rect(page, o.rect) for o in page_ops
                     if isinstance(o, RedactOp)]
            if boxes:
                redacted[idx] = [page.get_textbox(box) for box in boxes]
            if removals:
                _remove_under(page, removals)
            for box in boxes:
                # Son denetim: kutuda hâlâ yazı varsa sessiz kalınmaz.
                if page.get_textbox(box).strip():
                    warnings.append(f"{idx + 1}. sayfada karartılan alanda yazı kaldı; dosyayı "
                                    "paylaşmadan önce kontrol et.")
            for op in page_ops:
                if isinstance(op, TextOp):
                    _text(page, op, fonts, warnings)
                elif isinstance(op, ImageOp):
                    images.insert(page, op.asset, pymupdf.Rect(op.rect), opacity=op.opacity,
                                  angle_cw=op.rotation, keep_aspect=op.keep_aspect)
                elif isinstance(op, HighlightOp):
                    _highlight(page, op)
                elif isinstance(op, ShapeOp):
                    _shape(page, op)
                elif isinstance(op, LineOp):
                    _line(page, op)

        if redacted:
            warnings.extend(_redaction_warnings(doc, redacted))
        for op in doc_ops:
            if isinstance(op, WatermarkOp):
                _watermark(doc, op, fonts, images)
            else:
                _page_numbers(doc, op, fonts)
        save_pdf(doc, output)
    return ApplyResult(Path(output), warnings)


# --- imza -----------------------------------------------------------------------------------

# Bu açıklıktan (0-255) parlak pikseller kâğıt sayılır ve saydamlaşır; arası yumuşak geçiş.
PAPER = 225
INK = 150


def prepare_signature(src: Path, output: Path, *, max_side: int = 1600) -> Path:
    """İmza resmini hazırlar: yönlendirme düzeltilir, saydamlığı yoksa beyaz kâğıt saydam
    yapılır, kenarlardaki boşluk kırpılır, PNG olarak yazılır."""
    try:
        with Image.open(src) as im:
            img = ImageOps.exif_transpose(im).convert("RGBA")
    except Image.DecompressionBombError as e:
        raise ImageTooLargeError(Path(src)) from e
    except (UnidentifiedImageError, OSError) as e:
        raise UnsupportedFileError(Path(src), "resim") from e

    if img.getchannel("A").getextrema()[0] == 255:  # tamamen opak: taranmış/fotoğraf imza
        gray = img.convert("L")
        span = PAPER - INK
        img.putalpha(gray.point(
            lambda v: 0 if v >= PAPER else 255 if v <= INK else round((PAPER - v) * 255 / span)))
    bbox = img.getchannel("A").point(lambda a: 255 if a > 16 else 0).getbbox()
    if not bbox:
        raise PdfAtolyeError("Resimde imza bulunamadı. Beyaz kâğıda koyu renkle atılmış bir "
                             "imza yükle ya da imzayı çiz.")
    pad = max(4, round(max(bbox[2] - bbox[0], bbox[3] - bbox[1]) * 0.03))
    img = img.crop((max(0, bbox[0] - pad), max(0, bbox[1] - pad),
                    min(img.width, bbox[2] + pad), min(img.height, bbox[3] + pad)))
    img.thumbnail((max_side, max_side), Image.Resampling.LANCZOS)
    with atomic_output(output) as tmp:
        img.save(tmp, "PNG", optimize=True)
    return Path(output)
