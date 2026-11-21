"""Güvenlik adım 2: LibreOffice dönüşümünde belge dışarı uzanamaz, makro çalıştıramaz
(GUVENLIK_PLANI.md).

Kanıt denemesinde (LibreOffice 26.8) uzak resim, bağlı bölüm, dış ilişkili DOCX resmi ve
WEBSERVICE hiçbir istek üretmedi; makro da çalışmadı. Yine de bu, kurulu sürümün varsayılanlarına
dayanıyordu. Taze profile güvenlik ayarları açıkça yazılır (`office.harden_profile`). Bu testler:
1. ayar dosyasının her çağrıda LibreOffice açılmadan önce yazıldığını,
2. LibreOffice'in dosyayı kabul ettiğini (bozuk olsaydı değerleri atıp kendi dosyasını yazardı),
3. dış kaynaklı belgelerin 127.0.0.1'deki dinleyiciye istek göndermediğini ve yerel bir
   "kanarya" dosyasının içeriğinin PDF'e girmediğini denetler.
"""

from __future__ import annotations

import http.server
import subprocess
import threading
import xml.etree.ElementTree as ET
import zipfile
from pathlib import Path

import pymupdf
import pytest

from toolia import engines
from toolia.convert import office
from toolia.settings import Settings

SOFFICE = engines.detect_libreoffice(Settings()).path
needs_lo = pytest.mark.skipif(not SOFFICE, reason="LibreOffice yok")
MARKER = "TOOLIA-KANARYA-7731"
OOR = "{http://openoffice.org/2001/registry}"


def _values(xcu: Path) -> dict[tuple[str, str], str]:
    root = ET.parse(xcu).getroot()
    out = {}
    for item in root.iter("item"):
        for prop in item.iter("prop"):
            value = prop.find("value")
            out[(item.get(f"{OOR}path"), prop.get(f"{OOR}name"))] = (
                value.text if value is not None else None)
    return out


EXPECTED = {(p, n): v for p, n, _t, v in office.HARDENING}


def test_hardening_covers_macros_links_and_recalc():
    keys = {n for _p, n, _t, _v in office.HARDENING}
    assert {"DisableMacrosExecution", "MacroSecurityLevel", "BlockUntrustedRefererLinks",
            "Link", "OOXMLRecalcMode", "ODFRecalcMode"} <= keys
    assert EXPECTED[("/org.openoffice.Office.Common/Security/Scripting",
                     "DisableMacrosExecution")] == "true"


def test_harden_profile_writes_valid_registry(tmp_path):
    xcu = office.harden_profile(tmp_path)
    assert xcu == tmp_path / "user" / "registrymodifications.xcu"
    assert _values(xcu) == EXPECTED


def test_every_soffice_call_gets_hardened_profile(tmp_path, monkeypatch):
    seen = []

    def fake_run(args, **kw):
        env = next(a for a in args if a.startswith("-env:UserInstallation="))
        from urllib.parse import urlparse
        from urllib.request import url2pathname

        profile = Path(url2pathname(urlparse(env.split("=", 1)[1]).path))
        seen.append(_values(profile / "user" / "registrymodifications.xcu"))
        return subprocess.CompletedProcess(args, 0, b"", b"")

    monkeypatch.setattr(office.proc, "run", fake_run)
    office._run_soffice("soffice", [tmp_path / "a.docx"], tmp_path, "pdf", 10)
    assert seen == [EXPECTED]


# --- gerçek LibreOffice ile ---------------------------------------------------------------------

class _Listener:
    def __init__(self) -> None:
        hits = self.hits = []

        class H(http.server.BaseHTTPRequestHandler):
            def do_GET(self):  # noqa: N802
                hits.append(self.path)
                self.send_response(404)
                self.end_headers()

            do_HEAD = do_GET

            def log_message(self, *a):
                pass

        self.srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), H)
        self.base = f"http://127.0.0.1:{self.srv.server_address[1]}"
        threading.Thread(target=self.srv.serve_forever, daemon=True).start()

    def close(self) -> None:
        self.srv.shutdown()
        self.srv.server_close()


@pytest.fixture
def listener():
    lst = _Listener()
    yield lst
    lst.close()


ODT = "application/vnd.oasis.opendocument.text"
ODS = "application/vnd.oasis.opendocument.spreadsheet"


def _odf(path: Path, mime: str, body: str) -> Path:
    content = f"""<?xml version="1.0" encoding="UTF-8"?>
<office:document-content xmlns:office="urn:oasis:names:tc:opendocument:xmlns:office:1.0"
 xmlns:text="urn:oasis:names:tc:opendocument:xmlns:text:1.0"
 xmlns:table="urn:oasis:names:tc:opendocument:xmlns:table:1.0"
 xmlns:draw="urn:oasis:names:tc:opendocument:xmlns:drawing:1.0"
 xmlns:svg="urn:oasis:names:tc:opendocument:xmlns:svg-compatible:1.0"
 xmlns:xlink="http://www.w3.org/1999/xlink" office:version="1.3">
<office:body>{body}</office:body></office:document-content>"""
    manifest = f"""<?xml version="1.0" encoding="UTF-8"?>
<manifest:manifest xmlns:manifest="urn:oasis:names:tc:opendocument:xmlns:manifest:1.0"
 manifest:version="1.3">
 <manifest:file-entry manifest:full-path="/" manifest:media-type="{mime}"/>
 <manifest:file-entry manifest:full-path="content.xml" manifest:media-type="text/xml"/>
</manifest:manifest>"""
    with zipfile.ZipFile(path, "w") as z:
        z.writestr(zipfile.ZipInfo("mimetype"), mime)
        z.writestr("META-INF/manifest.xml", manifest, zipfile.ZIP_DEFLATED)
        z.writestr("content.xml", content, zipfile.ZIP_DEFLATED)
    return path


def _remote_image_odt(path: Path, url: str) -> Path:
    return _odf(path, ODT, f"""<office:text><text:p>
<draw:frame draw:name="r" svg:width="2cm" svg:height="2cm"><draw:image xlink:href="{url}"
 xlink:type="simple" xlink:show="embed" xlink:actuate="onLoad"/></draw:frame></text:p>
</office:text>""")


def _text(pdf: Path) -> str:
    with pymupdf.open(pdf) as doc:
        return "".join(p.get_text() for p in doc)


@needs_lo
def test_libreoffice_accepts_hardened_profile(tmp_path):
    """LibreOffice dosyayı okuyup kabul ederse çıkışta değerlerimizi korur."""
    profile = tmp_path / "profil"
    office.harden_profile(profile)
    src = _odf(tmp_path / "a.odt", ODT, "<office:text><text:p>merhaba</text:p></office:text>")
    subprocess.run([SOFFICE, f"-env:UserInstallation={profile.resolve().as_uri()}",
                    "--headless", "--norestore", "--nolockcheck", "--nodefault", "--nologo",
                    "--convert-to", "pdf", "--outdir", str(tmp_path), str(src)],
                   capture_output=True, timeout=180, check=True)
    assert (tmp_path / "a.pdf").is_file()
    assert _values(profile / "user" / "registrymodifications.xcu").items() >= EXPECTED.items()


@needs_lo
def test_office_documents_do_not_reach_out(tmp_path, listener):
    canary = tmp_path / "kanarya.txt"
    canary.write_text(f"{MARKER}\n", encoding="utf-8")
    docs = [
        _remote_image_odt(tmp_path / "uzak-resim.odt", f"{listener.base}/odt.png"),
        _odf(tmp_path / "bagli-bolum.odt", ODT, f"""<office:text><text:section text:name="S1">
<text:section-source xlink:href="{canary.as_uri()}" xlink:type="simple"
 text:filter-name="Text (encoded)"/><text:p>(bos)</text:p></text:section></office:text>"""),
        _odf(tmp_path / "webservice.ods", ODS, f"""<office:spreadsheet>
<table:table table:name="S"><table:table-row><table:table-cell
 table:formula="of:=WEBSERVICE(&quot;{listener.base}/ods&quot;)" office:value-type="string">
<text:p>x</text:p></table:table-cell></table:table-row></table:table></office:spreadsheet>"""),
    ]
    # DOCX'teki dış ilişkili resim (TargetMode="External"): LibreOffice'in kendisine ürettir
    seed = _remote_image_odt(tmp_path / "docx-kaynak.odt", f"{listener.base}/docx.png")
    office._run_soffice(SOFFICE, [seed], tmp_path, "docx:MS Word 2007 XML", 180)
    docx = tmp_path / "docx-kaynak.docx"
    with zipfile.ZipFile(docx) as z:
        assert b'TargetMode="External"' in z.read("word/_rels/document.xml.rels")
    docs.append(docx)
    listener.hits.clear()

    for src in docs:
        out = tmp_path / f"{src.stem}-{src.suffix[1:]}.pdf"
        office.convert_office(src, out, soffice=SOFFICE, timeout=180)
        assert MARKER not in _text(out), src.name
    assert listener.hits == []
