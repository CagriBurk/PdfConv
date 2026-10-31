"""Testler için kodla üretilen PDF ve resimler. Depoya ikili dosya koymamak için.

Her sayfaya "Sayfa N" yazılır; testler sayfa sırasını metni okuyarak doğrular.
"""

from __future__ import annotations

import re
from pathlib import Path

import pymupdf
from PIL import Image

TURKISH = "Çağrı ığdır şöyle: ĞÜŞİÖÇ ğüşiöç ı İ"
_WIN_FONT = Path("C:/Windows/Fonts/arial.ttf")
_LABEL = re.compile(r"(?:Sayfa|Ek) \d+")


def _write_label(page: pymupdf.Page, label: str) -> None:
    page.insert_text((72, 72), label, fontsize=20)
    if _WIN_FONT.is_file():
        page.insert_text((72, 110), TURKISH, fontsize=12, fontname="arial",
                         fontfile=str(_WIN_FONT))


def numbered(path: Path, n: int = 10, *, label: str = "Sayfa", with_toc: bool = True,
             password: str | None = None, size: tuple[float, float] = (595, 842)) -> Path:
    doc = pymupdf.open()
    for i in range(1, n + 1):
        _write_label(doc.new_page(width=size[0], height=size[1]), f"{label} {i}")
    if with_toc and n >= 6:
        doc.set_toc([
            [1, "Bölüm 1", 1],
            [2, "Kısım 1.1", 2],
            [2, "Kısım 1.2", 4],
            [1, "Bölüm 2", 6],
        ])
    kwargs = {}
    if password:
        kwargs = dict(encryption=pymupdf.PDF_ENCRYPT_AES_256, user_pw=password,
                      owner_pw=password + "-sahip")
    doc.save(path, **kwargs)
    doc.close()
    return path


def rotated(path: Path) -> Path:
    """4 sayfa; döndürmeleri 0, 90, 180, 270."""
    doc = pymupdf.open()
    for i, angle in enumerate((0, 90, 180, 270), start=1):
        page = doc.new_page()
        _write_label(page, f"Sayfa {i}")
        page.set_rotation(angle)
    doc.save(path)
    doc.close()
    return path


def mixed_sizes(path: Path) -> Path:
    """A4 dikey, A4 yatay, Letter."""
    doc = pymupdf.open()
    for i, (w, h) in enumerate([(595, 842), (842, 595), (612, 792)], start=1):
        _write_label(doc.new_page(width=w, height=h), f"Sayfa {i}")
    doc.save(path)
    doc.close()
    return path


def with_link(path: Path) -> Path:
    """5 sayfa; 1. sayfada 3. sayfaya giden iç bağlantı."""
    doc = pymupdf.open()
    for i in range(1, 6):
        _write_label(doc.new_page(), f"Sayfa {i}")
    doc[0].insert_link({"kind": pymupdf.LINK_GOTO, "from": pymupdf.Rect(72, 200, 300, 230),
                        "page": 2, "to": pymupdf.Point(0, 0)})
    doc.save(path)
    doc.close()
    return path


def scanned(path: Path) -> Path:
    """Metin katmanı olmayan, yalnızca resimden oluşan 1 sayfa."""
    img = path.with_suffix(".png")
    Image.new("RGB", (400, 560), "white").save(img)
    doc = pymupdf.open()
    doc.new_page().insert_image(pymupdf.Rect(0, 0, 595, 842), filename=str(img))
    doc.save(path)
    doc.close()
    img.unlink()
    return path


def photo_jpeg(path: Path, size: tuple[int, int] = (400, 200), exif_orientation: int = 1
               ) -> Path:
    """Sol yarısı mavi, sağ yarısı kırmızı JPEG; isteğe bağlı EXIF yönlendirmesi."""
    img = Image.new("RGB", size, "red")
    img.paste("blue", (0, 0, size[0] // 2, size[1]))
    exif = Image.Exif()
    if exif_orientation != 1:
        exif[0x0112] = exif_orientation
    img.save(path, "JPEG", quality=90, exif=exif.tobytes())
    return path


def transparent_png(path: Path) -> Path:
    img = Image.new("RGBA", (300, 300), (0, 0, 0, 0))
    img.paste((0, 128, 0, 255), (50, 50, 250, 250))
    img.save(path, "PNG")  # biçim açık: uzantı yanıltıcı olabilir (testte "resim.pdf")
    return path


def multipage_tiff(path: Path, frames: int = 3) -> Path:
    images = [Image.new("RGB", (200, 280), c) for c in ("white", "gray", "black")[:frames]]
    images[0].save(path, save_all=True, append_images=images[1:])
    return path


def labels(path: Path, password: str | None = None) -> list[str]:
    """Her sayfadaki 'Sayfa N' etiketini sırayla döndürür (boş sayfa için '')."""
    with pymupdf.open(path) as doc:
        if password:
            doc.authenticate(password)
        out = []
        for page in doc:
            m = _LABEL.search(page.get_text())
            out.append(m.group(0) if m else "")
        return out


# --- Office belgeleri (elle kurulan en küçük geçerli dosyalar) ---------------------------

_DOCX_TYPES = (
    '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
    '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
    '<Default Extension="rels" '
    'ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
    '<Default Extension="xml" ContentType="application/xml"/>'
    '<Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-'
    'officedocument.wordprocessingml.document.main+xml"/></Types>'
)
_DOCX_RELS = (
    '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
    '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
    '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/'
    'relationships/officeDocument" Target="word/document.xml"/></Relationships>'
)


def docx(path: Path, paragraphs: list[str], *, font: str | None = None,
         page_breaks: bool = False) -> Path:
    """Paragrafları (isteğe bağlı fontla) içeren .docx; page_breaks=True her paragraf ayrı sayfa."""
    from xml.sax.saxutils import escape

    rpr = f'<w:rPr><w:rFonts w:ascii="{font}" w:hAnsi="{font}"/></w:rPr>' if font else ""
    body = []
    for i, text in enumerate(paragraphs):
        if page_breaks and i:
            body.append('<w:p><w:r><w:br w:type="page"/></w:r></w:p>')
        body.append(f'<w:p><w:r>{rpr}<w:t xml:space="preserve">{escape(text)}</w:t></w:r></w:p>')
    document = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
        f'<w:body>{"".join(body)}<w:sectPr/></w:body></w:document>'
    )
    import zipfile

    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("[Content_Types].xml", _DOCX_TYPES)
        zf.writestr("_rels/.rels", _DOCX_RELS)
        zf.writestr("word/document.xml", document)
    return path


def rtf(path: Path, text: str) -> Path:
    """Türkçe karakterleri \\uN? kaçışlarıyla yazılmış RTF."""
    body = "".join(c if ord(c) < 128 else f"\\u{ord(c)}?" for c in text)
    path.write_text("{\\rtf1\\ansi\\deff0{\\fonttbl{\\f0 Arial;}}\\f0\\fs24 " + body + "\\par}",
                    encoding="ascii")
    return path
