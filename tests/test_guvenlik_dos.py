"""Güvenlik adım 7: sıkıştırma bombası (GUVENLIK_PLANI.md).

Kanıt: 398 KB'lık bir docx'in belgeye bağlı olmayan bir parçası (`word/header9.xml`, 400 MB boşluk)
font denetiminde Toolia'nın kendi sürecinde belleğe açıldı (+401 MB); LibreOffice dönüşümü
sorunsuz bittiği için patlama dönüşümden SONRA oluyordu. Aynısı xlsx sayfa sayımında. Oran ~1000:1
olduğundan birkaç MB'lık dosya bilgisayarı kilitlerdi.

Testler sınırları küçülterek çalışır (gerçek boyutta dosya üretmek yavaş olurdu).
"""

from __future__ import annotations

import sys
import zipfile

import pytest

from toolia.convert import office

MB = 1024 * 1024


def _zip(path, members: dict[str, bytes], *, big: tuple[str, int] | None = None,
         compression=zipfile.ZIP_DEFLATED):
    with zipfile.ZipFile(path, "w", compression) as z:
        for name, data in members.items():
            z.writestr(name, data)
        if big:
            name, size = big
            with z.open(name, "w", force_zip64=True) as f:
                chunk = b" " * MB
                for _ in range(size // MB):
                    f.write(chunk)
    return path


@pytest.fixture
def small_limits(monkeypatch):
    monkeypatch.setattr(office, "MAX_XML_MEMBER", 1 * MB)
    monkeypatch.setattr(office, "MAX_UNPACKED", 8 * MB)


def test_font_check_skips_oversized_parts(tmp_path, small_limits):
    font = b'<w:rFonts w:ascii="GizliFont"/>'
    ok = _zip(tmp_path / "ok.docx", {"word/document.xml": font})
    assert office.requested_fonts(ok) == {"GizliFont"}
    # Aynı font, sınırı aşan bir parçanın içinde: parça belleğe açılmaz, atlanır
    big = _zip(tmp_path / "buyuk.docx", {"word/document.xml": b"<w:document/>",
                                         "word/header9.xml": font + b" " * (2 * MB)})
    assert office.requested_fonts(big) == set()


def test_sheet_count_and_password_check_are_bounded(tmp_path, small_limits):
    xlsx = _zip(tmp_path / "a.xlsx", {}, big=("xl/workbook.xml", 3 * MB))
    assert office._sheet_count(xlsx) is None
    odt = _zip(tmp_path / "a.odt", {"mimetype": b"application/vnd.oasis.opendocument.text"},
               big=("META-INF/manifest.xml", 2 * MB))
    assert office.is_password_protected(odt) is False


def test_zip_bomb_is_rejected_before_libreoffice(tmp_path, small_limits, monkeypatch):
    bomb = _zip(tmp_path / "bomba.docx", {"word/document.xml": b"<w:document/>"},
                big=("word/header9.xml", 20 * MB))
    assert bomb.stat().st_size < 200 * 1024
    with pytest.raises(office.OfficeConversionError, match="sıkıştırma bombası"):
        office.check_not_zip_bomb(bomb, "bomba.docx")

    def no_libreoffice(*a, **kw):
        raise AssertionError("LibreOffice çalıştırılmamalıydı")

    monkeypatch.setattr(office.proc, "run", no_libreoffice)
    # soffice yolu yalnızca var olan bir dosya olmalı; çağrılmadan önce reddedilir
    with pytest.raises(office.OfficeConversionError, match="sıkıştırma bombası"):
        office.convert_office(bomb, tmp_path / "b.pdf", soffice=sys.executable)
    item = office.OfficeItem(bomb, tmp_path / "b.odt", "bomba.docx")
    results = office.convert_office_format([item], soffice=sys.executable, target=".odt")
    assert isinstance(results[0], office.OfficeConversionError)
    assert "sıkıştırma bombası" in str(results[0])


def test_large_but_honest_files_are_not_rejected(tmp_path, small_limits):
    # Açılmış hâli büyük ama sıkışmamış (resimler gibi): oran 1, bomba değil
    stored = _zip(tmp_path / "resimli.docx", {"word/document.xml": b"<w:document/>"},
                  big=("word/media/video.bin", 10 * MB), compression=zipfile.ZIP_STORED)
    office.check_not_zip_bomb(stored, "resimli.docx")
    # Çok sıkışan ama küçük (olağan XML): sınırın altında
    xml = _zip(tmp_path / "metin.docx", {"word/document.xml": b"<w:t>a</w:t>" * 200_000})
    office.check_not_zip_bomb(xml, "metin.docx")
    # Zip olmayan eski biçim (.doc) ve bozuk dosya: denetim karışmaz
    (tmp_path / "eski.doc").write_bytes(b"\xd0\xcf\x11\xe0" + b"\0" * 100)
    office.check_not_zip_bomb(tmp_path / "eski.doc", "eski.doc")
