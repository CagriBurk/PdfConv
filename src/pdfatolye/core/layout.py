"""Sayfa düzeni ve yazdırma: N-up dizilim, kenar kırpma, poster bölme ve yeniden boyutlandırma."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

import pymupdf

from pdfatolye import proc
from pdfatolye.core import geometry as geo
from pdfatolye.core.paper import PAPER_SIZES_MM, PT_PER_MM, size_pt
from pdfatolye.core.pdfio import opened, save_pdf
from pdfatolye.core.ranges import parse_ranges
from pdfatolye.errors import PdfAtolyeError

_VALID_ORIENTATIONS = ("otomatik", "dikey", "yatay")
_VALID_PER_SHEET = (1, 2, 4, 6, 9, 16)
_MIN_BOX_PT = 1.0
_NOTE_LINE_STEP_PT = 18.0
_NOTE_TOP_PAD_PT = 14.0
_NOTE_BOTTOM_PAD_PT = 4.0
_NOTE_LINE_COLOR = (0.78, 0.80, 0.84)
_BORDER_COLOR = (0.72, 0.72, 0.72)


def _sheet_size(paper: str, orientation: str, *, auto_landscape: bool) -> tuple[float, float]:
    """Kağıt adı ve yönlendirmeye göre (genişlik, yükseklik) nokta boyutunu döndürür."""
    if paper not in PAPER_SIZES_MM:
        raise PdfAtolyeError(f"Bilinmeyen kağıt boyutu: {paper}")
    if orientation not in _VALID_ORIENTATIONS:
        raise PdfAtolyeError(f"Bilinmeyen sayfa yönü: {orientation}")
    base_w, base_h = size_pt(paper)
    landscape = orientation == "yatay" or (orientation == "otomatik" and auto_landscape)
    return (base_h, base_w) if landscape else (base_w, base_h)


def _show_page(
    out_page: pymupdf.Page,
    target: pymupdf.Rect,
    src_doc: pymupdf.Document,
    pno: int,
    src_page: pymupdf.Page,
    *,
    clip_visual: pymupdf.Rect | None = None,
) -> None:
    """`src_page`'i (isteğe bağlı görsel kırpmayla) `target` içine çizer.

    PyMuPDF 2.0'da `cropbox != mediabox` ve `rotation != 0` birlikteyken `show_pdf_page`
    kaynak XObject BBox'unu kaydırıp içeriği kesebiliyor; bu durumda geçici 1 sayfalık
    döndürmesiz kopya üzerinden `rotate=-rot` ile çizilir.
    """
    clip: pymupdf.Rect | None = None
    if clip_visual is not None:
        clip = clip_visual * src_page.derotation_matrix
        clip.normalize()

    if src_page.rotation and src_page.cropbox != src_page.mediabox:
        scratch = pymupdf.open()
        try:
            scratch.insert_pdf(src_doc, from_page=pno, to_page=pno)
            rot = scratch[0].rotation
            scratch[0].set_rotation(0)
            out_page.show_pdf_page(target, scratch, 0, clip=clip, rotate=-rot)
        finally:
            scratch.close()
        return

    out_page.show_pdf_page(target, src_doc, pno, clip=clip)


def _draw_note_lines(page: pymupdf.Page, x0: float, x1: float, y0: float, y1: float) -> None:
    """Not alanı içine ince, açık gri yazım çizgileri çizer."""
    if x1 - x0 <= 2 or y1 - y0 <= _NOTE_TOP_PAD_PT:
        return
    shape = page.new_shape()
    y = y0 + _NOTE_TOP_PAD_PT
    drawn = False
    while y <= y1 - _NOTE_BOTTOM_PAD_PT:
        shape.draw_line(pymupdf.Point(x0, y), pymupdf.Point(x1, y))
        drawn = True
        y += _NOTE_LINE_STEP_PT
    if drawn:
        shape.finish(color=_NOTE_LINE_COLOR, width=0.5)
        shape.commit()


def _nup_grid(per_sheet: int, landscape: bool, notes_side: bool) -> tuple[int, int]:
    if notes_side:
        return 1, per_sheet
    if per_sheet == 1:
        return 1, 1
    if per_sheet == 2:
        return (2, 1) if landscape else (1, 2)
    if per_sheet == 4:
        return 2, 2
    if per_sheet == 6:
        return (3, 2) if landscape else (2, 3)
    if per_sheet == 9:
        return 3, 3
    if per_sheet == 16:
        return 4, 4
    raise PdfAtolyeError(f"Desteklenmeyen sayfa sayısı: {per_sheet}")


def nup_pdf(
    input: Path,
    output: Path,
    *,
    spec: str = "",
    paper: str = "A4",
    orientation: str = "otomatik",
    per_sheet: int = 2,
    notes_side: bool = False,
    margin_mm: float = 6,
    gap_mm: float = 4,
    border: bool = True,
    password: str | None = None,
    on_progress: Callable[[float], None] | None = None,
) -> Path:
    """Seçilen sayfaları `paper` üzerine `per_sheet` ızgarada (N-up) yerleştirir.

    `notes_side=True` ise sol ~%55 alana slaytlar (1 sütun × `per_sheet` satır), sağ ~%45
    alana çizgili not satırları çizilir.
    """
    if per_sheet not in _VALID_PER_SHEET:
        raise PdfAtolyeError(f"Yaprak başına sayfa sayısı { _VALID_PER_SHEET } içinden seçilmeli.")
    if margin_mm < 0 or gap_mm < 0:
        raise PdfAtolyeError("Kenar boşluğu ve aralık negatif olamaz.")

    margin = margin_mm * PT_PER_MM
    gap = gap_mm * PT_PER_MM

    with opened(Path(input), password) as src:
        indices = parse_ranges(spec, src.page_count)
        first_rect = src[indices[0]].rect
        src_landscape = first_rect.width > first_rect.height

        if notes_side:
            auto_landscape = src_landscape if per_sheet == 1 else False
        elif per_sheet in (2, 6):
            auto_landscape = not src_landscape
        else:
            auto_landscape = src_landscape

        sheet_w, sheet_h = _sheet_size(paper, orientation, auto_landscape=auto_landscape)
        cols, rows = _nup_grid(per_sheet, sheet_w > sheet_h, notes_side)

        usable_w = sheet_w - 2 * margin
        usable_h = sheet_h - 2 * margin
        if notes_side:
            slides_w = (usable_w - gap) * 0.55
            notes_x0 = margin + slides_w + gap
            notes_x1 = sheet_w - margin
            cell_w = slides_w
            cell_h = (usable_h - (rows - 1) * gap) / rows
            if notes_x1 - notes_x0 < _MIN_BOX_PT:
                raise PdfAtolyeError("Kenar boşluğu veya aralık seçili kağıt için çok büyük.")
        else:
            notes_x0 = notes_x1 = 0.0
            cell_w = (usable_w - (cols - 1) * gap) / cols
            cell_h = (usable_h - (rows - 1) * gap) / rows

        if cell_w < _MIN_BOX_PT or cell_h < _MIN_BOX_PT:
            raise PdfAtolyeError("Kenar boşluğu veya aralık seçili kağıt için çok büyük.")

        chunks = [indices[i:i + per_sheet] for i in range(0, len(indices), per_sheet)]
        out = pymupdf.open()
        try:
            for chunk_idx, chunk in enumerate(chunks):
                proc.raise_if_cancelled()
                out_page = out.new_page(width=sheet_w, height=sheet_h)
                for slot, pno in enumerate(chunk):
                    r, c = divmod(slot, cols)
                    x0 = margin + c * (cell_w + gap)
                    y0 = margin + r * (cell_h + gap)
                    cell = pymupdf.Rect(x0, y0, x0 + cell_w, y0 + cell_h)
                    src_page = src[pno]
                    target = geo.fit_inside(cell, src_page.rect.width, src_page.rect.height)
                    _show_page(out_page, target, src, pno, src_page)
                    if border:
                        out_page.draw_rect(target, color=_BORDER_COLOR, width=0.5)
                    if notes_side:
                        _draw_note_lines(out_page, notes_x0, notes_x1, y0, y0 + cell_h)
                if on_progress:
                    on_progress((chunk_idx + 1) / len(chunks))
            return save_pdf(out, Path(output))
        finally:
            out.close()


def _content_bbox_in_mediabox(page: pymupdf.Page) -> pymupdf.Rect | None:
    """Sayfadaki metin, çizim ve resimlerin mediabox uzayındaki ortak sınır kutusunu döndürür.

    Sayfa boşsa `None` döner. `get_text("blocks")`, `get_drawings()` ve `get_image_info()`
    döndürülmemiş, CropBox sol-üstüne göreli koordinat verir; burada `cropbox.tl` eklenip
    `mediabox`'a kırpılır (sıfır kalınlıklı yatay/dikey çizgiler korunur).
    """
    mediabox = page.mediabox
    offset = page.cropbox.tl
    boxes: list[tuple[float, float, float, float]] = []

    def _collect(rect_like: pymupdf.Rect | tuple[float, float, float, float]) -> None:
        r = pymupdf.Rect(rect_like)
        if r.is_infinite:
            return
        r.normalize()
        x0 = max(mediabox.x0, r.x0 + offset.x)
        y0 = max(mediabox.y0, r.y0 + offset.y)
        x1 = min(mediabox.x1, r.x1 + offset.x)
        y1 = min(mediabox.y1, r.y1 + offset.y)
        if x1 >= x0 and y1 >= y0 and (x1 > x0 or y1 > y0):
            boxes.append((x0, y0, x1, y1))

    for block in page.get_text("blocks"):
        if len(block) >= 7 and block[6] == 0 and not str(block[4]).strip():
            continue
        _collect(block[:4])

    for drawing in page.get_drawings():
        if drawing.get("type") == "clip":
            continue
        if drawing.get("color") is None and drawing.get("fill") is None:
            continue
        rect = drawing.get("rect")
        if rect is not None:
            _collect(rect)

    for info in page.get_image_info():
        bbox = info.get("bbox")
        if bbox is not None:
            _collect(bbox)

    if not boxes:
        return None
    return pymupdf.Rect(
        min(b[0] for b in boxes),
        min(b[1] for b in boxes),
        max(b[2] for b in boxes),
        max(b[3] for b in boxes),
    )


def _clamp_nonempty(rect: pymupdf.Rect, bounds: pymupdf.Rect) -> pymupdf.Rect:
    """Dikdörtgeni `bounds` içine sıkıştırır ve CropBox'ın en az 1 pt kalmasını sağlar."""
    x0 = max(bounds.x0, rect.x0)
    y0 = max(bounds.y0, rect.y0)
    x1 = min(bounds.x1, rect.x1)
    y1 = min(bounds.y1, rect.y1)
    if x1 - x0 < _MIN_BOX_PT:
        cx = (x0 + x1) / 2
        x0 = max(bounds.x0, cx - _MIN_BOX_PT / 2)
        x1 = min(bounds.x1, x0 + _MIN_BOX_PT)
        x0 = max(bounds.x0, x1 - _MIN_BOX_PT)
    if y1 - y0 < _MIN_BOX_PT:
        cy = (y0 + y1) / 2
        y0 = max(bounds.y0, cy - _MIN_BOX_PT / 2)
        y1 = min(bounds.y1, y0 + _MIN_BOX_PT)
        y0 = max(bounds.y0, y1 - _MIN_BOX_PT)
    return pymupdf.Rect(x0, y0, x1, y1)


def crop_margins_pdf(
    input: Path,
    output: Path,
    *,
    spec: str = "",
    crop_mode: str = "auto",
    margin_mm: float = 6,
    crop_top_mm: float = 0,
    crop_right_mm: float = 0,
    crop_bottom_mm: float = 0,
    crop_left_mm: float = 0,
    password: str | None = None,
    on_progress: Callable[[float], None] | None = None,
) -> Path:
    """Seçilen sayfaların kenar boşluklarını kırpar (`auto` içerikten algılar, `manual` keser)."""
    if crop_mode not in ("auto", "manual"):
        raise PdfAtolyeError(f"Bilinmeyen kırpma modu: {crop_mode}")
    if margin_mm < 0 or min(crop_top_mm, crop_right_mm, crop_bottom_mm, crop_left_mm) < 0:
        raise PdfAtolyeError("Kırpma değerleri negatif olamaz.")

    pad = margin_mm * PT_PER_MM
    top_pt = crop_top_mm * PT_PER_MM
    right_pt = crop_right_mm * PT_PER_MM
    bottom_pt = crop_bottom_mm * PT_PER_MM
    left_pt = crop_left_mm * PT_PER_MM

    with opened(Path(input), password) as doc:
        targets = sorted(set(parse_ranges(spec, doc.page_count)))
        for idx, pno in enumerate(targets):
            proc.raise_if_cancelled()
            page = doc[pno]
            if crop_mode == "auto":
                bbox = _content_bbox_in_mediabox(page)
                if bbox is not None:
                    expanded = pymupdf.Rect(
                        bbox.x0 - pad, bbox.y0 - pad, bbox.x1 + pad, bbox.y1 + pad
                    )
                    new_cb = _clamp_nonempty(expanded, page.mediabox)
                    if new_cb.width >= _MIN_BOX_PT and new_cb.height >= _MIN_BOX_PT:
                        page.set_cropbox(new_cb)
            else:
                vis_w, vis_h = page.rect.width, page.rect.height
                vis_trimmed = pymupdf.Rect(left_pt, top_pt, vis_w - right_pt, vis_h - bottom_pt)
                if vis_trimmed.width < _MIN_BOX_PT or vis_trimmed.height < _MIN_BOX_PT:
                    raise PdfAtolyeError(
                        f"{pno + 1}. sayfada kırpma boşlukları sayfa boyutunu aşıyor."
                    )
                unrot = vis_trimmed * page.derotation_matrix
                unrot.normalize()
                offset = page.cropbox.tl
                new_cb = pymupdf.Rect(unrot.tl + offset, unrot.br + offset)
                new_cb = _clamp_nonempty(new_cb, page.mediabox)
                page.set_cropbox(new_cb)
            if on_progress:
                on_progress((idx + 1) / len(targets))
        return save_pdf(doc, Path(output))


def poster_split_pdf(
    input: Path,
    output: Path,
    *,
    spec: str = "",
    paper: str = "A4",
    orientation: str = "otomatik",
    poster_cols: int = 2,
    poster_rows: int = 2,
    overlap_mm: float = 5,
    margin_mm: float = 6,
    password: str | None = None,
    on_progress: Callable[[float], None] | None = None,
) -> Path:
    """Seçilen her sayfayı `poster_cols × poster_rows` parçaya bölüp `paper` üzerine yayar."""
    if poster_cols < 1 or poster_rows < 1:
        raise PdfAtolyeError("Poster sütun ve satır sayısı en az 1 olmalı.")
    if overlap_mm < 0 or margin_mm < 0:
        raise PdfAtolyeError("Bindirme ve kenar boşluğu negatif olamaz.")

    margin = margin_mm * PT_PER_MM
    overlap_pt = overlap_mm * PT_PER_MM

    with opened(Path(input), password) as src:
        indices = parse_ranges(spec, src.page_count)
        out = pymupdf.open()
        try:
            for idx, pno in enumerate(indices):
                proc.raise_if_cancelled()
                src_page = src[pno]
                src_w, src_h = src_page.rect.width, src_page.rect.height
                step_x = src_w / poster_cols
                step_y = src_h / poster_rows
                ov_x = min(overlap_pt / 2, step_x * 0.45) if poster_cols > 1 else 0.0
                ov_y = min(overlap_pt / 2, step_y * 0.45) if poster_rows > 1 else 0.0

                max_tile_w = step_x + (ov_x if poster_cols == 2 else 2 * ov_x)
                max_tile_h = step_y + (ov_y if poster_rows == 2 else 2 * ov_y)

                sheet_w, sheet_h = _sheet_size(
                    paper, orientation, auto_landscape=max_tile_w > max_tile_h
                )
                usable_w = sheet_w - 2 * margin
                usable_h = sheet_h - 2 * margin
                if usable_w < _MIN_BOX_PT or usable_h < _MIN_BOX_PT:
                    raise PdfAtolyeError("Kenar boşluğu seçili kağıt için çok büyük.")

                # Tüm parçalar aynı ölçekle basılmalı ki yan yana yapıştırıldığında birebir otursun.
                scale = min(usable_w / max_tile_w, usable_h / max_tile_h)

                for r in range(poster_rows):
                    for c in range(poster_cols):
                        tx0 = 0.0 if c == 0 else max(0.0, c * step_x - ov_x)
                        tx1 = src_w if c == poster_cols - 1 else min(src_w, (c + 1) * step_x + ov_x)
                        ty0 = 0.0 if r == 0 else max(0.0, r * step_y - ov_y)
                        ty1 = src_h if r == poster_rows - 1 else min(src_h, (r + 1) * step_y + ov_y)
                        vis_tile = pymupdf.Rect(tx0, ty0, tx1, ty1)
                        tw = vis_tile.width * scale
                        th = vis_tile.height * scale
                        px0 = margin + (usable_w - tw) / 2
                        py0 = margin + (usable_h - th) / 2
                        target = pymupdf.Rect(px0, py0, px0 + tw, py0 + th)

                        out_page = out.new_page(width=sheet_w, height=sheet_h)
                        _show_page(out_page, target, src, pno, src_page, clip_visual=vis_tile)
                if on_progress:
                    on_progress((idx + 1) / len(indices))
            return save_pdf(out, Path(output))
        finally:
            out.close()


def resize_pages_pdf(
    input: Path,
    output: Path,
    *,
    spec: str = "",
    paper: str = "A4",
    orientation: str = "otomatik",
    margin_mm: float = 0,
    password: str | None = None,
    on_progress: Callable[[float], None] | None = None,
) -> Path:
    """Seçilen her sayfayı oranını koruyarak `paper` ortasına sığdırır."""
    if margin_mm < 0:
        raise PdfAtolyeError("Kenar boşluğu negatif olamaz.")
    margin = margin_mm * PT_PER_MM

    with opened(Path(input), password) as src:
        indices = parse_ranges(spec, src.page_count)
        out = pymupdf.open()
        try:
            for idx, pno in enumerate(indices):
                proc.raise_if_cancelled()
                src_page = src[pno]
                src_w, src_h = src_page.rect.width, src_page.rect.height
                sheet_w, sheet_h = _sheet_size(
                    paper, orientation, auto_landscape=src_w > src_h
                )
                box = pymupdf.Rect(margin, margin, sheet_w - margin, sheet_h - margin)
                if box.width < _MIN_BOX_PT or box.height < _MIN_BOX_PT:
                    raise PdfAtolyeError("Kenar boşluğu seçili kağıt için çok büyük.")
                out_page = out.new_page(width=sheet_w, height=sheet_h)
                target = geo.fit_inside(box, src_w, src_h)
                _show_page(out_page, target, src, pno, src_page)
                if on_progress:
                    on_progress((idx + 1) / len(indices))
            return save_pdf(out, Path(output))
        finally:
            out.close()
