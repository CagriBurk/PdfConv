"""Office ↔ Office biçim dönüştürme. Gerçek LibreOffice yoksa dönüşüm testleri atlanır.

Her LibreOffice çağrısı ~7 sn sürdüğü için dönüşümler toplu çağrılarda birleştirildi."""

import re
import zipfile
from pathlib import Path

import openpyxl
import pytest

from tests.fixtures import make_fixtures as fx
from toolia import engines
from toolia.convert import office
from toolia.convert.office import OfficeItem, convert_office_format
from toolia.settings import Settings

SOFFICE = engines.detect_libreoffice(Settings()).path
needs_lo = pytest.mark.skipif(not SOFFICE, reason="LibreOffice yok")

_ODP_CONTENT = """<?xml version="1.0" encoding="UTF-8"?>
<office:document-content xmlns:office="urn:oasis:names:tc:opendocument:xmlns:office:1.0"
 xmlns:draw="urn:oasis:names:tc:opendocument:xmlns:drawing:1.0"
 xmlns:text="urn:oasis:names:tc:opendocument:xmlns:text:1.0"
 xmlns:svg="urn:oasis:names:tc:opendocument:xmlns:svg-compatible:1.0" office:version="1.3">
<office:body><office:presentation>{pages}</office:presentation></office:body>
</office:document-content>"""
_ODP_PAGE = ('<draw:page draw:name="s{n}"><draw:frame svg:x="2cm" svg:y="2cm" svg:width="20cm" '
             'svg:height="3cm"><draw:text-box><text:p>{text}</text:p></draw:text-box>'
             '</draw:frame></draw:page>')
_ODF_MANIFEST = """<?xml version="1.0" encoding="UTF-8"?>
<manifest:manifest xmlns:manifest="urn:oasis:names:tc:opendocument:xmlns:manifest:1.0"
 manifest:version="1.3">
<manifest:file-entry manifest:full-path="/" manifest:media-type="{mime}"/>
<manifest:file-entry manifest:full-path="content.xml" manifest:media-type="text/xml">{extra}
</manifest:file-entry></manifest:manifest>"""
_ENCRYPTION = ('<manifest:encryption-data manifest:checksum-type="SHA1/1K" '
               'manifest:checksum="x"/>')


def odp(path: Path, slides: list[str]) -> Path:
    """Elle yazılmış en küçük sunum (python-pptx kurulu değil)."""
    pages = "".join(_ODP_PAGE.format(n=i, text=t) for i, t in enumerate(slides, 1))
    mime = "application/vnd.oasis.opendocument.presentation"
    with zipfile.ZipFile(path, "w") as zf:
        zf.writestr("mimetype", mime, compress_type=zipfile.ZIP_STORED)
        zf.writestr("content.xml", _ODP_CONTENT.format(pages=pages))
        zf.writestr("META-INF/manifest.xml", _ODF_MANIFEST.format(mime=mime, extra=""))
    return path


def encrypted_ooxml(path: Path) -> Path:
    """Parolalı OOXML'in kabuğu: OLE imzası + 'EncryptedPackage' akış adı."""
    path.write_bytes(office._OLE_MAGIC + bytes(504) + "EncryptedPackage".encode("utf-16-le")
                     + bytes(512))
    return path


def encrypted_odf(path: Path) -> Path:
    mime = "application/vnd.oasis.opendocument.text"
    with zipfile.ZipFile(path, "w") as zf:
        zf.writestr("mimetype", mime)
        zf.writestr("content.xml", b"\x00sifreli")
        zf.writestr("META-INF/manifest.xml", _ODF_MANIFEST.format(mime=mime, extra=_ENCRYPTION))
    return path


def workbook(path: Path, sheets: dict[str, list[list]]) -> Path:
    wb = openpyxl.Workbook()
    wb.remove(wb.active)
    for title, rows in sheets.items():
        ws = wb.create_sheet(title)
        for row in rows:
            ws.append(row)
    wb.active = len(sheets) - 1  # etkin sayfa son sayfa olsa da CSV'ye ilk sayfa gitmeli
    wb.save(path)
    return path


def zip_text(path: Path, member: str) -> str:
    with zipfile.ZipFile(path) as zf:
        return zf.read(member).decode("utf-8")


def rtf_text(path: Path) -> str:
    raw = path.read_text(encoding="ascii")
    return re.sub(r"\\u(-?\d+)(?:\\'[0-9a-fA-F]{2}|\?)", lambda m: chr(int(m.group(1)) % 65536),
                  raw)


def items_for(paths: list[Path], target: str, outdir: Path) -> list[OfficeItem]:
    outdir.mkdir(exist_ok=True)
    return [OfficeItem(p, outdir / f"{p.stem}{target}", p.name) for p in paths]


# --- LibreOffice gerekmeyenler -----------------------------------------------------------


def test_missing_libreoffice_stops_whole_job(tmp_path):
    src = fx.docx(tmp_path / "a.docx", ["x"])
    with pytest.raises(office.LibreOfficeNotFoundError, match="winget"):
        convert_office_format(items_for([src], ".odt", tmp_path / "o"), soffice=None,
                              target=".odt")


@pytest.mark.parametrize("target", [".pdf", ".jpg", ".docm", ""])
def test_non_office_target_is_clear_error(tmp_path, target):
    src = fx.docx(tmp_path / "a.docx", ["x"])
    with pytest.raises(office.OfficeConversionError, match="çevrilemez"):
        convert_office_format(items_for([src], target, tmp_path / "o"), soffice=__file__,
                              target=target)


def test_per_file_errors_without_calling_libreoffice(tmp_path):
    # Aile dışı ve parolalı dosyalar LibreOffice'e hiç gitmez (soffice burada sahte bir yol).
    paths = [workbook(tmp_path / "tablo.xlsx", {"S": [["x"]]}),
             encrypted_ooxml(tmp_path / "parolalı.docx"),
             encrypted_odf(tmp_path / "gizli.odt")]
    progress: list[tuple[int, int]] = []
    results = convert_office_format(
        items_for(paths, ".docx", tmp_path / "o"), soffice=__file__, target=".docx",
        on_progress=lambda n, t: progress.append((n, t)))
    assert all(isinstance(r, office.OfficeConversionError) for r in results)
    assert "'tablo.xlsx' DOCX biçimine çevrilemez" in str(results[0])
    assert "'parolalı.docx' parola korumalı" in str(results[1])
    assert "'gizli.odt' parola korumalı" in str(results[2])
    assert progress == [(1, 3), (2, 3), (3, 3)]


def test_password_detection_is_not_fooled(tmp_path):
    assert not office.is_password_protected(fx.docx(tmp_path / "a.docx", ["x"]))
    ole = tmp_path / "eski.docx"  # adı yanlış konmuş .doc: OLE ama şifreli paket yok
    ole.write_bytes(office._OLE_MAGIC + bytes(2048))
    assert not office.is_password_protected(ole)
    assert not office.is_password_protected(odp(tmp_path / "s.odp", ["x"]))
    broken = tmp_path / "b.odt"
    broken.write_bytes(b"bozuk")
    assert not office.is_password_protected(broken)


def test_csv_input_separator_and_encoding_are_sniffed(tmp_path):
    p = tmp_path / "a.csv"
    p.write_bytes("Ad;Şehir;Sayı\r\nÇağrı;\"Iğdır, merkez\";1,5\r\n".encode("cp1254"))
    assert office._csv_infilter(p).endswith(":59,34,36,1,,0,false,true")
    p.write_bytes(office._UTF8_BOM + "ad,şehir\nçağrı,\"a;b;c\"\n".encode())
    assert ":44,34,76," in office._csv_infilter(p)
    p.write_text("a\tb\tc\n1\t2\t3\n", encoding="utf-8")
    assert ":9,34,76," in office._csv_infilter(p)
    p.write_text("tek sütun\n", encoding="utf-8")
    assert ":59,34,76," in office._csv_infilter(p)


def test_sheet_count(tmp_path):
    assert office._sheet_count(workbook(tmp_path / "a.xlsx", {"Bir": [[1]], "İki": [[2]]})) == 2
    assert office._sheet_count(workbook(tmp_path / "b.xlsx", {"Bir": [[1]]})) == 1
    assert office._sheet_count(tmp_path / "c.csv") == 1
    assert office._sheet_count(tmp_path / "yok.xls") is None


# --- gerçek dönüşüm ----------------------------------------------------------------------


@needs_lo
def test_word_batch_to_odt_broken_file_does_not_stop_others(tmp_path):
    folder = tmp_path / "Çağrı'nın ödevleri"
    folder.mkdir()
    good = fx.docx(folder / "Ödev 1 — Işık.docx", [fx.TURKISH, "İkinci paragraf"])
    macro = fx.docx(tmp_path / "makrolu.docm", ["Makrolu ş"])
    bad = tmp_path / "bozuk.docx"
    bad.write_bytes(b"PK\x03\x04 bu bir docx degil")
    locked = encrypted_ooxml(tmp_path / "kilitli.docx")
    sheet = workbook(tmp_path / "tablo.xlsx", {"S": [["x"]]})
    items = items_for([good, macro, bad, locked, sheet], ".odt", tmp_path / "çıktı klasörü")
    progress: list[int] = []
    results = convert_office_format(items, soffice=SOFFICE, target=".odt",
                                    on_progress=lambda n, t: progress.append(n))

    assert results[0] == []
    assert fx.TURKISH in zip_text(items[0].output, "content.xml")
    assert isinstance(results[1], list) and "Makrolu ş" in zip_text(items[1].output,
                                                                      "content.xml")
    assert len(results[1]) == 1 and "makrolar" in results[1][0]
    assert "'makrolu.docm'" in results[1][0]
    assert isinstance(results[2], office.OfficeConversionError)
    assert "'bozuk.docx' dönüştürülemedi" in str(results[2])
    assert "parola korumalı" in str(results[3])
    assert "çevrilemez" in str(results[4])
    assert not items[2].output.exists() and not items[3].output.exists()
    assert progress == [1, 2, 3, 4, 5]


@needs_lo
def test_word_to_rtf_txt_and_back_to_docx(tmp_path):
    src = fx.docx(tmp_path / "metin.docx", [fx.TURKISH, "İkinci satır"])
    rtf_items = items_for([src], ".rtf", tmp_path / "rtf")
    assert convert_office_format(rtf_items, soffice=SOFFICE, target=".rtf") == [[]]
    assert fx.TURKISH in rtf_text(rtf_items[0].output)

    txt_items = items_for([src], ".txt", tmp_path / "txt")
    assert convert_office_format(txt_items, soffice=SOFFICE, target=".txt") == [[]]
    body = txt_items[0].output.read_bytes().decode("utf-8-sig")
    assert fx.TURKISH in body and "İkinci satır" in body

    docx_items = items_for([rtf_items[0].output], ".docx", tmp_path / "docx")
    assert convert_office_format(docx_items, soffice=SOFFICE, target=".DOCX") == [[]]
    assert fx.TURKISH in zip_text(docx_items[0].output, "word/document.xml")


@needs_lo
def test_sheets_to_csv_for_turkish_excel(tmp_path):
    two = workbook(tmp_path / "Satış Raporu.xlsx", {
        "Birinci": [["Ad", "Şehir", "Sayı"], ["Çağrı", "Iğdır; İzmir", 1.5],
                    ["ğüşıöç İ", 'tırnak "x"', 7]],
        "İkinci": [["ikinci sayfa"]],
    })
    one = workbook(tmp_path / "tek.xlsx", {"Tek": [["Işık", "ılık"]]})
    items = items_for([two, one], ".csv", tmp_path / "csv")
    results = convert_office_format(items, soffice=SOFFICE, target=".csv")

    assert len(results[0]) == 1 and "2 sayfa" in results[0][0]
    assert "'Satış Raporu.xlsx'" in results[0][0]
    assert results[1] == []
    raw = items[0].output.read_bytes()
    assert raw.startswith(office._UTF8_BOM)  # Excel UTF-8 olduğunu BOM'dan anlar
    lines = raw.decode("utf-8-sig").splitlines()
    assert lines[0] == "Ad;Şehir;Sayı"
    assert lines[1] in ('Çağrı;"Iğdır; İzmir";1,5', 'Çağrı;"Iğdır; İzmir";1.5')
    assert lines[2] == 'ğüşıöç İ;"tırnak ""x""";7'
    assert "ikinci sayfa" not in raw.decode("utf-8-sig")
    assert items[1].output.read_bytes().decode("utf-8-sig").strip() == "Işık;ılık"


@needs_lo
def test_sheets_xlsx_to_ods_and_csv_to_xlsx(tmp_path):
    book = workbook(tmp_path / "kitap.xlsx", {"Sayfa": [["Çağrı ığdır", "ĞÜŞİÖÇ"]],
                                              "İkinci": [["x"]]})
    items = items_for([book], ".ods", tmp_path / "ods")
    assert convert_office_format(items, soffice=SOFFICE, target=".ods") == [[]]
    content = zip_text(items[0].output, "content.xml")
    assert "Çağrı ığdır" in content and "ĞÜŞİÖÇ" in content
    assert office._sheet_count(items[0].output) == 2

    csv = tmp_path / "eski excel.csv"  # Türkçe Excel'in yazdığı gibi: ';' ve Windows-1254
    csv.write_bytes("Ad;Şehir;Sayı\r\nÇağrı;Iğdır;1,5\r\n".encode("cp1254"))
    items = items_for([csv], ".xlsx", tmp_path / "xlsx")
    assert convert_office_format(items, soffice=SOFFICE, target=".xlsx") == [[]]
    ws = openpyxl.load_workbook(items[0].output).active
    rows = [[c.value for c in r] for r in ws.iter_rows()]
    assert rows[0] == ["Ad", "Şehir", "Sayı"]
    assert rows[1][:2] == ["Çağrı", "Iğdır"]


@needs_lo
def test_slides_odp_to_pptx_and_back(tmp_path):
    src = odp(tmp_path / "sunum.odp", ["Sunum ğüşıöç İ", "İkinci slayt"])
    items = items_for([src], ".pptx", tmp_path / "pptx")
    assert convert_office_format(items, soffice=SOFFICE, target=".pptx") == [[]]
    with zipfile.ZipFile(items[0].output) as zf:
        slides = sorted(n for n in zf.namelist() if re.fullmatch(r"ppt/slides/slide\d+\.xml", n))
        assert len(slides) == 2
        assert "Sunum ğüşıöç İ" in zf.read("ppt/slides/slide1.xml").decode("utf-8")

    back = items_for([items[0].output], ".odp", tmp_path / "odp")
    assert convert_office_format(back, soffice=SOFFICE, target=".odp") == [[]]
    content = zip_text(back[0].output, "content.xml")
    assert "Sunum ğüşıöç İ" in content and "İkinci slayt" in content
