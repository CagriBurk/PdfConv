from typer.testing import CliRunner

from pdfatolye.cli import app
from tests.fixtures import make_fixtures as fx

runner = CliRunner()


def test_merge_with_default_output_name(tmp_path):
    a = fx.numbered(tmp_path / "a.pdf", 2, with_toc=False)
    b = fx.numbered(tmp_path / "b.pdf", 1, label="Ek", with_toc=False)
    r = runner.invoke(app, ["birlestir", str(a), str(b)])
    assert r.exit_code == 0, r.output
    assert fx.labels(tmp_path / "a_birlesik.pdf") == ["Sayfa 1", "Sayfa 2", "Ek 1"]
    # İkinci çalıştırma öncekinin üstüne yazmaz
    r = runner.invoke(app, ["birlestir", str(a), str(b)])
    assert (tmp_path / "a_birlesik (2).pdf").exists()


def test_select_and_rotate(tmp_path):
    a = fx.numbered(tmp_path / "a.pdf", 5, with_toc=False)
    out = tmp_path / "s.pdf"
    assert runner.invoke(app, ["sec", str(a), "5,1", "-o", str(out)]).exit_code == 0
    assert fx.labels(out) == ["Sayfa 5", "Sayfa 1"]
    assert runner.invoke(app, ["dondur", str(out), "90", "-o", str(out)]).exit_code == 0


def test_split_reports_count(tmp_path):
    a = fx.numbered(tmp_path / "a.pdf", 6)
    r = runner.invoke(app, ["bol", str(a), "--mod", "n", "--n", "3"])
    assert r.exit_code == 0, r.output
    assert "2 dosya" in r.output
    assert len(list((tmp_path / "a_parcalar").glob("*.pdf"))) == 2


def test_friendly_error_for_encrypted_pdf(tmp_path):
    a = fx.numbered(tmp_path / "a.pdf", 2, password="gizli")
    r = runner.invoke(app, ["sil", str(a), "1"])
    assert r.exit_code == 2
    assert "şifreli" in r.output
    assert "Traceback" not in r.output


def test_friendly_error_for_bad_range(tmp_path):
    a = fx.numbered(tmp_path / "a.pdf", 2, with_toc=False)
    r = runner.invoke(app, ["sec", str(a), "7"])
    assert r.exit_code == 2
    assert "7. sayfa yok" in r.output


def test_info_json(tmp_path):
    a = fx.numbered(tmp_path / "a.pdf", 3, with_toc=False)
    r = runner.invoke(app, ["bilgi", str(a), "--json"])
    assert r.exit_code == 0
    assert '"page_count": 3' in r.output


def test_images_roundtrip(tmp_path):
    jpg = fx.photo_jpeg(tmp_path / "foto.jpg")
    assert runner.invoke(app, ["resimden", str(jpg)]).exit_code == 0
    pdf = tmp_path / "foto_resimler.pdf"
    assert pdf.exists()
    r = runner.invoke(app, ["resme", str(pdf), "--dpi", "72"])
    assert r.exit_code == 0, r.output
    assert (tmp_path / "foto_resimler_resimler" / "foto_resimler_1.png").exists()


def test_watermark_and_page_numbers(tmp_path):
    import pymupdf

    a = fx.numbered(tmp_path / "a.pdf", 3, with_toc=False)
    r = runner.invoke(app, ["filigran", str(a), "--yazi", "GİZLİ", "--sayfalar", "2"])
    assert r.exit_code == 0, r.output
    r = runner.invoke(app, ["sayfa-no", str(tmp_path / "a_filigranli.pdf"), "--bicim",
                            "Sayfa {n} / {N}", "--kapak", "-o", str(tmp_path / "s.pdf")])
    assert r.exit_code == 0, r.output
    with pymupdf.open(tmp_path / "s.pdf") as doc:
        assert "GİZLİ" in doc[1].get_text() and "GİZLİ" not in doc[0].get_text()
        assert "Sayfa 2 / 2" in doc[2].get_text()
    r = runner.invoke(app, ["sayfa-no", str(a), "--bicim", "numara"])
    assert r.exit_code == 2 and "{n}" in r.output
