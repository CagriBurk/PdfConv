"""Ağ çıkışı ölçümü: "dosyalar internete çıkmaz" vaadi (GUVENLIK_PLANI.md, adım 4).

Bütün dönüşüm türlerini sırayla çalıştırır; bu sırada bu sürecin ve bütün alt süreçlerinin
(soffice, gswin64c, tesseract, Edge, Playwright) bağlantılarını izler. 127.0.0.1 / ::1 dışındaki
her bağlantı raporlanır. Ayrıca System (PID 4) altında ölçüm sırasında YENİ açılan bağlantılar
da raporlanır (SMB istemcisi çekirdektedir; bkz. adım 3).

Elle çalıştırılır (pytest toplamaz):
    uv run python tests/guvenlik/ag_cikisi.py
Gerçek veri klasörüne dokunmaz: her şey geçici bir klasörde. Çıkış kodu: 0 temiz, 1 sızıntı.
"""

from __future__ import annotations

import contextlib
import ipaddress
import sys
import tempfile
import threading
import time
import traceback
import zipfile
from collections.abc import Callable
from pathlib import Path

import psutil
import pymupdf
from PIL import Image, ImageDraw, ImageFont

from toolia import engines
from toolia.settings import load_settings

TEST_NET = "192.0.2.1"  # RFC 5737 belgeleme adresi: internette yönlendirilmez


class Watch:
    def __init__(self) -> None:
        self.me = psutil.Process()
        self.found: list[tuple[str, str, str]] = []  # (adım, süreç, adres)
        self.step = "-"
        self._stop = threading.Event()
        self._base_system = self._system_conns()

    @staticmethod
    def _system_conns() -> set:
        out = set()
        for c in psutil.net_connections(kind="inet"):
            if c.pid == 4 and c.raddr:
                out.add((c.raddr.ip, c.raddr.port))
        return out

    def _tree(self) -> dict[int, str]:
        procs = {self.me.pid: self.me.name()}
        try:
            for p in self.me.children(recursive=True):
                with contextlib.suppress(psutil.Error):
                    procs[p.pid] = p.name()
        except psutil.Error:
            pass
        return procs

    def _poll(self) -> None:
        tree = self._tree()
        for c in psutil.net_connections(kind="inet"):
            if not c.raddr:
                continue
            ip = ipaddress.ip_address(c.raddr.ip.split("%")[0])
            if ip.is_loopback or ip.is_unspecified:
                continue
            if c.pid in tree:
                who = tree[c.pid]
            elif c.pid == 4 and (c.raddr.ip, c.raddr.port) not in self._base_system:
                who = "System (yeni)"
            else:
                continue
            entry = (self.step, who, f"{c.raddr.ip}:{c.raddr.port} {c.status}")
            if entry not in self.found:
                self.found.append(entry)

    def run(self) -> None:
        while not self._stop.is_set():
            with contextlib.suppress(psutil.Error):
                self._poll()
            time.sleep(0.1)

    def __enter__(self):
        self._t = threading.Thread(target=self.run, daemon=True)
        self._t.start()
        return self

    def __exit__(self, *exc):
        time.sleep(2)
        self._stop.set()
        self._t.join()


# --- girdiler ------------------------------------------------------------------------------

def make_inputs(d: Path) -> dict[str, Path]:
    f: dict[str, Path] = {}
    doc = pymupdf.open()
    for i in range(3):
        doc.new_page().insert_text((72, 72 + i * 20), f"Toolia ağ ölçümü sayfa {i + 1} — 1.234,56")
    f["pdf"] = d / "metin.pdf"
    doc.save(f["pdf"])

    # PDF → Excel için çizgili 3×3 tablo
    table = pymupdf.open()
    page = table.new_page()
    x0, y0, w, h = 72, 100, 120, 24
    for r in range(4):
        page.draw_line((x0, y0 + r * h), (x0 + 3 * w, y0 + r * h))
    for c in range(4):
        page.draw_line((x0 + c * w, y0), (x0 + c * w, y0 + 3 * h))
    for r, row in enumerate([["Ürün", "Adet", "Tutar"], ["Kalem", "3", "12,50"],
                             ["Defter", "2", "40,00"]]):
        for c, cell in enumerate(row):
            page.insert_text((x0 + c * w + 6, y0 + r * h + 16), cell)
    f["table"] = d / "tablo.pdf"
    table.save(f["table"])

    img = Image.new("RGB", (1240, 400), "white")
    draw = ImageDraw.Draw(img)
    try:
        font = ImageFont.truetype("arial.ttf", 48)
    except OSError:
        font = ImageFont.load_default()
    draw.text((40, 150), "Taranmis belge OCR denemesi 2026", fill="black", font=font)
    f["png"] = d / "tarama.png"
    img.save(f["png"])
    scan = pymupdf.open()
    page = scan.new_page(width=620, height=200)
    page.insert_image(page.rect, filename=str(f["png"]))
    f["scan"] = d / "tarama.pdf"
    scan.save(f["scan"])

    f["odt"] = d / "belge.odt"
    with zipfile.ZipFile(f["odt"], "w") as z:
        z.writestr(zipfile.ZipInfo("mimetype"), "application/vnd.oasis.opendocument.text")
        z.writestr("META-INF/manifest.xml", """<?xml version="1.0" encoding="UTF-8"?>
<manifest:manifest xmlns:manifest="urn:oasis:names:tc:opendocument:xmlns:manifest:1.0"
 manifest:version="1.3"><manifest:file-entry manifest:full-path="/"
 manifest:media-type="application/vnd.oasis.opendocument.text"/><manifest:file-entry
 manifest:full-path="content.xml" manifest:media-type="text/xml"/></manifest:manifest>""")
        z.writestr("content.xml", """<?xml version="1.0" encoding="UTF-8"?>
<office:document-content xmlns:office="urn:oasis:names:tc:opendocument:xmlns:office:1.0"
 xmlns:text="urn:oasis:names:tc:opendocument:xmlns:text:1.0" office:version="1.3">
<office:body><office:text><text:p>Toolia ağ ölçümü</text:p></office:text></office:body>
</office:document-content>""")

    f["html"] = d / "sayfa.html"
    f["html"].write_text(f"""<!doctype html><meta charset="utf-8"><body><h1>Ağ denemesi</h1>
<img src="http://{TEST_NET}/a.png"><img src="https://{TEST_NET}/b.png">
<link rel="stylesheet" href="https://{TEST_NET}/c.css">
<script>
  fetch('https://{TEST_NET}/d').catch(() => {{}});
  try {{ new WebSocket('ws://{TEST_NET}/e'); }} catch (e) {{}}
  try {{ navigator.sendBeacon('http://{TEST_NET}/f', 'x'); }} catch (e) {{}}
  const i = new Image(); i.src = 'file://{TEST_NET}' + location.pathname;
</script></body>""", encoding="utf-8")

    f["md"] = d / "not.md"
    f["md"].write_text(f"""---
title: Ağ denemesi
---
# Başlık

Formül: $e^{{i\\pi}} + 1 = 0$

$$\\int_0^1 x^2\\,dx = \\tfrac13$$

![uzak](http://{TEST_NET}/g.png)

<img src="https://{TEST_NET}/h.png">
""", encoding="utf-8")
    f["txt"] = d / "metin.txt"
    f["txt"].write_text("Düz metin ağ denemesi\nikinci satır\n", encoding="utf-8")
    return f


# --- adımlar --------------------------------------------------------------------------------

def steps(f: dict[str, Path], out: Path) -> list[tuple[str, Callable[[], object]]]:
    s = load_settings()
    eng = {e.key: e.path for e in engines.detect_all(s)}
    so, br, tess, gs = eng.get("libreoffice"), eng.get("browser"), eng.get("tesseract"), \
        eng.get("ghostscript")

    from toolia.convert.html import print_html, print_text
    from toolia.convert.image_format import convert_image
    from toolia.convert.markdown.render import MarkdownPrinter
    from toolia.convert.office import OfficeItem, convert_office, convert_office_format
    from toolia.convert.to_excel import pdf_to_excel
    from toolia.convert.to_word import pdf_to_word
    from toolia.core.compress import compress
    from toolia.core.ocr import ocr

    def md():
        with MarkdownPrinter(br, confine=True) as p:
            return p.convert(f["md"], out / "not.pdf")

    return [
        ("PDF bilgisi / küçük resim (PyMuPDF)",
         lambda: pymupdf.open(f["pdf"])[0].get_pixmap().tobytes("png")),
        ("Sıkıştırma: dengeli (PyMuPDF)",
         lambda: compress(f["pdf"], out / "sik1.pdf", "dengeli")),
        ("Sıkıştırma: güçlü (Ghostscript)",
         lambda: compress(f["scan"], out / "sik2.pdf", "guclu", ghostscript=gs)),
        ("OCR (ocrmypdf + Tesseract + Ghostscript)",
         lambda: ocr(f["scan"], out / "ocr.pdf", tesseract=tess, ghostscript=gs)),
        ("PDF → Word (pdf2docx)", lambda: pdf_to_word(f["pdf"], out / "w.docx")),
        ("PDF → Excel (openpyxl)", lambda: pdf_to_excel(f["table"], out / "x.xlsx")),
        ("Resim → JPG (Pillow)",
         lambda: convert_image(f["png"], out / "r.jpg", target=".jpg", quality=90,
                               background="#ffffff")),
        ("Office → PDF (LibreOffice)",
         lambda: convert_office(f["odt"], out / "o.pdf", soffice=so)),
        ("Office → DOCX (LibreOffice)",
         lambda: convert_office_format([OfficeItem(f["odt"], out / "o.docx", "belge.odt")],
                                       soffice=so, target=".docx")),
        ("HTML → PDF (Edge; ağa çıkmaya çalışan betik)",
         lambda: print_html(f["html"], out / "h.pdf", browser_path=br, confine=True)),
        ("Metin → PDF (Edge)", lambda: print_text(f["txt"], out / "t.pdf", browser_path=br)),
        ("Markdown → PDF (Edge + KaTeX; uzak resimler)", md),
    ]


def main() -> int:
    with tempfile.TemporaryDirectory(prefix="toolia-ag-") as tmp:
        d = Path(tmp)
        out = d / "cikti"
        out.mkdir()
        f = make_inputs(d)
        watch = Watch()
        failed = []
        with watch:
            for name, fn in steps(f, out):
                watch.step = name
                t0 = time.time()
                try:
                    fn()
                    print(f"  tamam  {time.time() - t0:5.1f} sn  {name}")
                except Exception:  # noqa: BLE001 — ölçüm sürsün
                    failed.append(name)
                    print(f"  HATA          {name}\n{traceback.format_exc(limit=2)}")
                time.sleep(0.5)
        print()
        if watch.found:
            print("DIŞARI BAĞLANTI GÖRÜLDÜ:")
            for step, who, addr in watch.found:
                print(f"  [{step}] {who}: {addr}")
        else:
            print("Dışarı bağlantı yok: bütün bağlantılar 127.0.0.1 / ::1.")
        if failed:
            print("Çalışmayan adımlar:", ", ".join(failed))
        return 1 if watch.found else 0


if __name__ == "__main__":
    sys.exit(main())
