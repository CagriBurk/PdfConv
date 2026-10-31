"""Koordinat dönüşümleri tek yerde.

İki uzay var:
- **görünüm** (view): kullanıcının ekranda gördüğü sayfa. Sol üst köşe (0, 0), y aşağı,
  birim PDF noktası (1/72 inç). Döndürme (/Rotate) uygulanmış, CropBox'a göre kırpılmış.
  Arayüz (pdf.js, ölçek 1) ve iş istekleri bu uzayı kullanır.
- **sayfa** (page): PyMuPDF'in çizim/yazı/açıklama fonksiyonlarının beklediği uzay.
  Döndürülmemiş sayfa, sol üst köşe CropBox'ın sol üstü, y aşağı.

Görünüm ↔ sayfa dönüşümü `page.rotation_matrix` / `derotation_matrix` ile yapılır;
CropBox ofsetini (dosyadaki gerçek, MediaBox tabanlı ve y'si yukarı koordinata geçişi)
PyMuPDF yazarken kendisi uygular. Not: `page.transformation_matrix` döndürülmüş ve CropBox'ı
kaydırılmış sayfada ofseti kaybediyor (PyMuPDF 2.0); bu yüzden hiçbir yerde kullanılmaz.

Açılar görünümde **saat yönünde** derecedir (ekran / Konva alışkanlığı, y aşağı).
"""

from __future__ import annotations

from collections.abc import Sequence

import pymupdf

RectLike = Sequence[float]


def view_size(page: pymupdf.Page) -> tuple[float, float]:
    """Görünür sayfanın genişlik ve yüksekliği (döndürme uygulanmış)."""
    return page.rect.width, page.rect.height


def view_to_page_point(page: pymupdf.Page, x: float, y: float) -> pymupdf.Point:
    return pymupdf.Point(x, y) * page.derotation_matrix


def page_to_view_point(page: pymupdf.Page, x: float, y: float) -> pymupdf.Point:
    return pymupdf.Point(x, y) * page.rotation_matrix


def view_to_page_rect(page: pymupdf.Page, rect: RectLike) -> pymupdf.Rect:
    """Görünümdeki eksen hizalı dikdörtgeni sayfa uzayına çevirir (90'ın katlarında yine
    eksen hizalıdır; köşeler yer değiştirebilir, bu yüzden normalleştirilir)."""
    r = pymupdf.Rect(rect) * page.derotation_matrix
    r.normalize()
    return r


def page_to_view_rect(page: pymupdf.Page, rect: RectLike) -> pymupdf.Rect:
    r = pymupdf.Rect(rect) * page.rotation_matrix
    r.normalize()
    return r


def screen_to_view(x: float, y: float, scale: float) -> tuple[float, float]:
    """Ekran pikseli → görünüm noktası (arayüz `scale` ile büyütüp çiziyorsa)."""
    return x / scale, y / scale


def text_rotate(page: pymupdf.Page) -> int:
    """Sayfa döndürülmüşse yazı/resim, okuyana dik görünsün diye bu açıyla yazılır
    (PyMuPDF'in `rotate` parametresi)."""
    return page.rotation % 360


def morph_matrix(angle_cw: float) -> pymupdf.Matrix:
    """PyMuPDF `morph` parametresi için: görünümde saat yönünde `angle_cw` derece.

    `morph` matrisi PDF'in y'si yukarı uzayında uygulanır; orada pozitif açı saat yönünün
    tersidir, bu yüzden işaret çevrilir. Döndürme katı bir hareket olduğundan sayfa
    döndürülmüş olsa da yön aynıdır; yalnızca dönme merkezi sayfa uzayına çevrilmelidir.
    """
    return pymupdf.Matrix(-angle_cw)


def rotated_bbox(rect: RectLike, angle_cw: float) -> pymupdf.Rect:
    """Merkezi etrafında döndürülen dikdörtgeni saran eksen hizalı dikdörtgen."""
    r = pymupdf.Rect(rect)
    if not angle_cw % 360:
        return r
    c = (r.tl + r.br) / 2
    m = pymupdf.Matrix(1, 0, 0, 1, -c.x, -c.y) * pymupdf.Matrix(angle_cw) \
        * pymupdf.Matrix(1, 0, 0, 1, c.x, c.y)
    return (r.quad * m).rect


def fit_inside(box: RectLike, width: float, height: float) -> pymupdf.Rect:
    """`width × height` oranındaki içeriği kutuya sığdırır, ortalar (oran korunur)."""
    b = pymupdf.Rect(box)
    if width <= 0 or height <= 0 or b.is_empty:
        return b
    s = min(b.width / width, b.height / height)
    w, h = width * s, height * s
    x0 = b.x0 + (b.width - w) / 2
    y0 = b.y0 + (b.height - h) / 2
    return pymupdf.Rect(x0, y0, x0 + w, y0 + h)
