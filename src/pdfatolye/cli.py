"""Komut satırı. Sunucu: `serve`, `motorlar`. PDF işleri: `birlestir`, `bol`, `sec`, ...

Çıktı yolu verilmezse girdinin yanına, var olan dosyanın üstüne yazmayan bir ad seçilir.
"""

from __future__ import annotations

import functools
import json
import socket
import threading
import urllib.request
import webbrowser
from collections.abc import Callable
from pathlib import Path
from typing import Annotated, TypeVar

import typer

from pdfatolye import engines
from pdfatolye.errors import PdfAtolyeError
from pdfatolye.settings import load_settings

app = typer.Typer(help="PDF Atölyesi — yerel PDF araç seti", no_args_is_help=True)

ConfigOpt = Annotated[Path | None, typer.Option("--config", help="config.toml yolu")]
OutOpt = Annotated[
    Path | None, typer.Option("-o", "--cikti", help="Çıktı dosyası (yoksa otomatik ad)")
]
DirOpt = Annotated[
    Path | None, typer.Option("-d", "--klasor", help="Çıktı klasörü (yoksa otomatik)")
]
PwOpt = Annotated[str | None, typer.Option("--sifre", help="Şifreli PDF'in şifresi")]
InPdf = Annotated[Path, typer.Argument(help="PDF dosyası", exists=True, dir_okay=False)]

F = TypeVar("F", bound=Callable)


def friendly_errors(fn: F) -> F:
    """Beklenen hataları yığın izi yerine tek satır Türkçe mesajla gösterir (çıkış kodu 2)."""

    @functools.wraps(fn)
    def wrapper(*args, **kwargs):
        try:
            return fn(*args, **kwargs)
        except (PdfAtolyeError, FileNotFoundError, ValueError) as e:
            typer.secho(f"Hata: {e}", fg="red", err=True)
            raise typer.Exit(2) from None

    return wrapper  # type: ignore[return-value]


def _default_output(input: Path, suffix: str, ext: str = ".pdf") -> Path:
    from pdfatolye.core.pdfio import unique_path

    return unique_path(input.with_name(f"{input.stem}_{suffix}{ext}"))


def _default_dir(input: Path, suffix: str) -> Path:
    from pdfatolye.core.pdfio import unique_path

    return unique_path(input.with_name(f"{input.stem}_{suffix}"))


def _done(path: Path) -> None:
    typer.echo(f"Yazıldı: {path}")


@app.command()
def serve(
    port: Annotated[int | None, typer.Option(help="Sunucu portu")] = None,
    no_browser: Annotated[bool, typer.Option("--no-browser", help="Tarayıcıyı açma")] = False,
    config: ConfigOpt = None,
) -> None:
    """Web arayüzünü başlatır."""
    import uvicorn

    from pdfatolye.api.app import create_app

    settings = load_settings(config)
    if port is not None:
        settings.port = port
    url = f"http://{settings.host}:{settings.port}"
    browser = settings.open_browser and not no_browser

    if _port_in_use(settings.host, settings.port):
        if _is_our_server(url):
            typer.echo(f"PDF Atölyesi zaten çalışıyor: {url}")
            if browser:
                webbrowser.open(url)
            return
        typer.echo(
            f"{settings.port} portu başka bir program tarafından kullanılıyor. "
            "config.toml'da başka bir port seç veya --port ver.",
            err=True,
        )
        raise typer.Exit(1)

    typer.echo(f"PDF Atölyesi çalışıyor: {url}  (kapatmak için Ctrl+C)")
    if browser:
        threading.Timer(1.0, webbrowser.open, args=[url]).start()
    uvicorn.run(create_app(settings), host=settings.host, port=settings.port, log_level="warning")


def _port_in_use(host: str, port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(0.5)
        return s.connect_ex((host, port)) == 0


def _is_our_server(url: str) -> bool:
    try:
        with urllib.request.urlopen(f"{url}/api/health", timeout=2) as resp:
            return json.load(resp).get("app") == "pdfatolye"
    except (OSError, ValueError):
        return False


@app.command("motorlar")
def motorlar(config: ConfigOpt = None) -> None:
    """Dış araçların (LibreOffice, Tesseract, ...) durumunu gösterir."""
    settings = load_settings(config)
    any_missing = False
    for e in engines.detect_all(settings):
        # ASCII işaretler: çıktı bir dosyaya/borulara yönlendirildiğinde cp1254 bozulmasın.
        mark = "[OK]" if e.ok else ("[!!]" if e.available else "[--]")
        line = f" {mark} {e.name:<16} {e.version or '-':<16} {e.needed_for}"
        typer.echo(line)
        for p in e.problems:
            typer.echo(f"      -> {p}")
        if not e.available:
            any_missing = True
            typer.echo(f"      -> kurulum: {e.install_hint}")
    raise typer.Exit(1 if any_missing else 0)


# --- PDF işlemleri -----------------------------------------------------------------------


@app.command()
@friendly_errors
def bilgi(
    pdf: InPdf,
    sifre: PwOpt = None,
    json_: Annotated[bool, typer.Option("--json", help="JSON olarak yaz")] = False,
) -> None:
    """PDF hakkında bilgi: sayfa sayısı, boyutlar, şifre, metin, yer imleri."""
    from pdfatolye.core.info import inspect_pdf

    info = inspect_pdf(pdf, sifre)
    if json_:
        typer.echo(json.dumps(info.to_dict(), ensure_ascii=False, indent=2))
        return
    typer.echo(f"Dosya        : {pdf.name} ({info.file_size / 1024:.0f} KB)")
    if info.needs_password:
        typer.echo("Durum        : şifreli (bilgi için --sifre ver)")
        return
    typer.echo(f"Sayfa        : {info.page_count}")
    sizes: dict[str, int] = {}
    for p in info.pages:
        label = p.paper or f"{p.width:.0f}x{p.height:.0f} pt"
        label += " yatay" if p.width > p.height else ""
        sizes[label] = sizes.get(label, 0) + 1
    typer.echo("Boyutlar     : " + ", ".join(f"{k} ({v})" for k, v in sizes.items()))
    typer.echo(f"Şifreli      : {'evet' if info.encrypted else 'hayır'}")
    text_state = "var" if info.has_text else "yok (taranmış olabilir, OCR gerekir)"
    typer.echo(f"Metin katmanı: {text_state}")
    typer.echo(f"Yer imi      : {info.bookmark_count}")
    for key in ("title", "author", "creator", "producer"):
        if key in info.metadata:
            typer.echo(f"{key:<13}: {info.metadata[key]}")


@app.command()
@friendly_errors
def birlestir(
    pdfler: Annotated[list[Path], typer.Argument(help="Sırasıyla birleştirilecek PDF'ler",
                                                 exists=True, dir_okay=False)],
    cikti: OutOpt = None,
    yer_imi_dosya: Annotated[bool, typer.Option(
        "--yer-imi-dosya", help="Her dosya için adıyla bir yer imi ekle")] = False,
    sifre: PwOpt = None,
) -> None:
    """PDF'leri tek dosyada birleştirir. Yer imleri korunur."""
    from pdfatolye.core.pages import merge

    if len(pdfler) < 2:
        raise ValueError("Birleştirmek için en az iki PDF ver.")
    out = cikti or _default_output(pdfler[0], "birlesik")
    _done(merge(pdfler, out, passwords=[sifre] * len(pdfler), bookmark_per_file=yer_imi_dosya))


@app.command()
@friendly_errors
def sec(
    pdf: InPdf,
    aralik: Annotated[str, typer.Argument(help="Ör. '3,1,2' veya '1-5,8-'")],
    cikti: OutOpt = None,
    sifre: PwOpt = None,
) -> None:
    """Sayfaları verilen sırayla alır: sayfa çıkarma ve yeniden sıralama."""
    from pdfatolye.core.pages import select

    _done(select(pdf, aralik, cikti or _default_output(pdf, "secilen"), password=sifre))


@app.command()
@friendly_errors
def sil(
    pdf: InPdf,
    aralik: Annotated[str, typer.Argument(help="Silinecek sayfalar, ör. '2,5-7'")],
    cikti: OutOpt = None,
    sifre: PwOpt = None,
) -> None:
    """Sayfaları siler."""
    from pdfatolye.core.pages import delete

    _done(delete(pdf, aralik, cikti or _default_output(pdf, "silinmis"), password=sifre))


@app.command()
@friendly_errors
def dondur(
    pdf: InPdf,
    aci: Annotated[int, typer.Argument(help="Saat yönünde derece: 90, 180, 270 (-90 = sola)")],
    sayfalar: Annotated[str, typer.Option(help="Yalnızca bu sayfalar (boş = hepsi)")] = "",
    cikti: OutOpt = None,
    sifre: PwOpt = None,
) -> None:
    """Sayfaları döndürür."""
    from pdfatolye.core.pages import rotate

    out = cikti or _default_output(pdf, "dondurulmus")
    _done(rotate(pdf, aci, out, spec=sayfalar, password=sifre))


@app.command()
@friendly_errors
def ekle(
    hedef: InPdf,
    kaynak: Annotated[Path, typer.Argument(help="Sayfaları eklenecek PDF", exists=True,
                                           dir_okay=False)],
    sonra: Annotated[int, typer.Option(help="Hedefin kaçıncı sayfasından sonra (0 = en başa)")],
    sayfalar: Annotated[str, typer.Option(help="Kaynaktan alınacak sayfalar (boş = hepsi)")] = "",
    cikti: OutOpt = None,
) -> None:
    """Bir PDF'in sayfalarını diğerinin istenen yerine ekler."""
    from pdfatolye.core.pages import insert

    _done(insert(hedef, kaynak, sonra, cikti or _default_output(hedef, "eklenmis"),
                 spec=sayfalar))


@app.command()
@friendly_errors
def bos(
    pdf: InPdf,
    sonra: Annotated[int, typer.Option(help="Kaçıncı sayfadan sonra (0 = en başa)")],
    adet: Annotated[int, typer.Option(min=1, max=500)] = 1,
    cikti: OutOpt = None,
    sifre: PwOpt = None,
) -> None:
    """Boş sayfa ekler (bir önceki sayfanın boyutunda)."""
    from pdfatolye.core.pages import insert_blank

    _done(insert_blank(pdf, sonra, cikti or _default_output(pdf, "bos-sayfali"),
                       count=adet, password=sifre))


@app.command()
@friendly_errors
def bol(
    pdf: InPdf,
    mod: Annotated[str, typer.Option(help="her | n | aralik | yer-imi")] = "her",
    n: Annotated[int, typer.Option(help="'n' modunda kaç sayfada bir")] = 1,
    aralik: Annotated[str, typer.Option(help="'aralik' modunda, ör. '1-3, 4-10, 11-'")] = "",
    klasor: DirOpt = None,
    sifre: PwOpt = None,
) -> None:
    """PDF'i parçalara böler."""
    from pdfatolye.core.pages import SPLIT_MODES, split

    if mod not in SPLIT_MODES:
        raise ValueError(f"Mod şunlardan biri olmalı: {', '.join(SPLIT_MODES)}")
    outputs = split(pdf, klasor or _default_dir(pdf, "parcalar"), mode=mod, every=n,
                    spec=aralik, password=sifre)
    typer.echo(f"{len(outputs)} dosya yazıldı: {outputs[0].parent}")


@app.command()
@friendly_errors
def resimden(
    resimler: Annotated[list[Path], typer.Argument(help="Sırasıyla resimler", exists=True,
                                                   dir_okay=False)],
    cikti: OutOpt = None,
    boyut: Annotated[str, typer.Option(help="A4, A3, A5, Letter, Legal, resim")] = "A4",
    yon: Annotated[str, typer.Option(help="otomatik, dikey, yatay")] = "otomatik",
    kenar: Annotated[float, typer.Option(help="Kenar boşluğu (mm)")] = 0,
) -> None:
    """Resimlerden PDF yapar (JPG, PNG, HEIC, WEBP, TIFF)."""
    from pdfatolye.core.images import images_to_pdf

    out = cikti or _default_output(resimler[0], "resimler")
    _done(images_to_pdf(resimler, out, page_size=boyut, orientation=yon, margin_mm=kenar))


@app.command()
@friendly_errors
def resme(
    pdf: InPdf,
    klasor: DirOpt = None,
    dpi: Annotated[int, typer.Option(help="Çözünürlük (36-600)")] = 150,
    bicim: Annotated[str, typer.Option(help="png veya jpg")] = "png",
    sayfalar: Annotated[str, typer.Option(help="Boş = hepsi")] = "",
    sifre: PwOpt = None,
) -> None:
    """PDF sayfalarını resim olarak kaydeder."""
    from pdfatolye.core.images import pdf_to_images

    outputs = pdf_to_images(pdf, klasor or _default_dir(pdf, "resimler"), dpi=dpi, fmt=bicim,
                            spec=sayfalar, password=sifre)
    typer.echo(f"{len(outputs)} resim yazıldı: {outputs[0].parent}")


@app.command()
@friendly_errors
def md(
    dosyalar: Annotated[list[Path], typer.Argument(help="Markdown dosyaları", exists=True,
                                                   dir_okay=False)],
    cikti: Annotated[Path | None, typer.Option(
        "-o", "--cikti", help="Çıktı PDF (tek dosyada) veya klasör (çok dosyada)")] = None,
    tema: Annotated[str | None, typer.Option(help="ders | rapor | sade")] = None,
    kagit: Annotated[str | None, typer.Option(help="A4, A5, A3, Letter, Legal")] = None,
    yatay: Annotated[bool | None, typer.Option("--yatay/--dikey")] = None,
    kenar: Annotated[float | None, typer.Option(help="Kenar boşluğu (mm)")] = None,
    icindekiler: Annotated[bool | None, typer.Option(
        "--icindekiler/--icindekiler-yok", help="Sayfa numaralı içindekiler")] = None,
    derinlik: Annotated[int | None, typer.Option(help="İçindekiler başlık derinliği")] = None,
    kapak: Annotated[bool | None, typer.Option("--kapak/--kapak-yok")] = None,
    sayfa_no: Annotated[bool | None, typer.Option("--sayfa-no/--sayfa-no-yok")] = None,
    yazi_boyutu: Annotated[float | None, typer.Option(help="Gövde yazı boyutu (pt)")] = None,
    kasa: Annotated[Path | None, typer.Option(
        help="Obsidian kasası (![[resim]] aramak için); yoksa config.toml'daki vault_path")
    ] = None,
    html: Annotated[bool, typer.Option("--html", help="Hata ayıklama için HTML de kaydet")
                    ] = False,
    config: ConfigOpt = None,
) -> None:
    """Markdown'ı PDF yapar: LaTeX formüller, Obsidian callout/[[bağlantı]]/![[resim]], kod."""
    from pdfatolye.convert.markdown import MarkdownPrinter, MdOptions

    settings = load_settings(config)
    browser = engines.detect_browser(settings)
    options = MdOptions(theme=tema, paper=kagit, landscape=yatay, margin_mm=kenar,
                        toc=icindekiler, toc_depth=derinlik, cover=kapak, page_numbers=sayfa_no,
                        font_size_pt=yazi_boyutu)
    multi = len(dosyalar) > 1
    if multi and cikti and cikti.suffix.lower() == ".pdf":
        raise ValueError("Birden çok dosyada -o bir klasör olmalı.")

    failed = 0
    with MarkdownPrinter(browser.path, kasa or settings.vault_path) as printer:
        for src in dosyalar:
            # Not.md → Not.pdf: dışa aktarımı yenilemek için var olan PDF'in üstüne yazılır.
            if multi:
                out = cikti / f"{src.stem}.pdf" if cikti else src.with_suffix(".pdf")
            else:
                out = cikti or src.with_suffix(".pdf")
            try:
                result = printer.convert(src, out, options,
                                         html_out=out.with_suffix(".html") if html else None)
            except PdfAtolyeError as e:
                failed += 1
                typer.secho(f"Hata ({src.name}): {e}", fg="red", err=True)
                continue
            typer.echo(f"Yazıldı: {result.output} ({result.page_count} sayfa)")
            for w in result.warnings:
                typer.secho(f"  uyarı: {w}", fg="yellow")
    if failed:
        raise typer.Exit(2)


@app.command()
@friendly_errors
def cevir(
    dosyalar: Annotated[list[Path], typer.Argument(
        help="Word, Excel, PowerPoint, ODT, RTF, HTML veya TXT dosyaları", exists=True,
        dir_okay=False)],
    cikti: Annotated[Path | None, typer.Option(
        "-o", "--cikti", help="Çıktı PDF (tek dosya / --birlestir) veya klasör")] = None,
    pdfa: Annotated[bool, typer.Option("--pdfa", help="Arşiv için PDF/A-2b (Office)")] = False,
    birlestir: Annotated[bool, typer.Option(
        "--birlestir", help="Hepsini tek PDF'te birleştir")] = False,
    config: ConfigOpt = None,
) -> None:
    """Office / HTML / metin dosyalarını PDF'e çevirir. Bozuk dosya diğerlerini durdurmaz."""
    from pdfatolye.convert.html import print_html, print_text
    from pdfatolye.convert.office import OFFICE_EXTS, convert_office
    from pdfatolye.core.pages import merge
    from pdfatolye.core.pdfio import unique_path

    settings = load_settings(config)
    settings.ensure_dirs()
    soffice = engines.detect_libreoffice(settings).path
    browser = engines.detect_browser(settings).path
    produced: list[Path] = []
    failed = 0
    for src in dosyalar:
        ext = src.suffix.lower()
        if birlestir or len(dosyalar) > 1:
            folder = cikti if (cikti and not birlestir) else src.parent
            out = unique_path(folder / f"{src.stem}.pdf")
        else:
            out = cikti or unique_path(src.with_suffix(".pdf"))
        try:
            if ext in OFFICE_EXTS:
                result = convert_office(src, out, soffice=soffice, pdfa=pdfa)
            elif ext in (".html", ".htm"):
                result = print_html(src, out, browser_path=browser)
            elif ext in (".txt", ".text", ".log", ".md"):
                result = print_text(src, out, browser_path=browser)
            else:
                raise ValueError(f"'{src.name}' desteklenmeyen bir dosya türü.")
        except (PdfAtolyeError, ValueError) as e:
            failed += 1
            typer.secho(f"Hata: {e}", fg="red", err=True)
            continue
        produced.append(result.output)
        typer.echo(f"Yazıldı: {result.output} ({result.page_count} sayfa)")
        for w in result.warnings:
            typer.secho(f"  uyarı: {w}", fg="yellow")
    if birlestir and len(produced) > 1:
        target = cikti or unique_path(dosyalar[0].with_name(f"{dosyalar[0].stem}_birlesik.pdf"))
        merge(produced, target, bookmark_per_file=True,
              bookmark_titles=[p.stem for p in produced])
        for p in produced:
            p.unlink(missing_ok=True)
        typer.echo(f"Birleştirildi: {target}")
    if failed:
        raise typer.Exit(2)


@app.command("resimleri-cikar")
@friendly_errors
def resimleri_cikar(pdf: InPdf, klasor: DirOpt = None, sifre: PwOpt = None) -> None:
    """PDF'e gömülü resimleri özgün biçimleriyle çıkarır."""
    from pdfatolye.core.images import extract_images

    outputs = extract_images(pdf, klasor or _default_dir(pdf, "gomulu-resimler"),
                             password=sifre)
    if not outputs:
        typer.echo("Bu PDF'te çıkarılacak resim yok.")
        return
    typer.echo(f"{len(outputs)} resim çıkarıldı: {outputs[0].parent}")


@app.command()
@friendly_errors
def filigran(
    pdf: InPdf,
    yazi: Annotated[str | None, typer.Option(help="Filigran yazısı, ör. TASLAK")] = None,
    resim: Annotated[Path | None, typer.Option(help="Filigran resmi (PNG önerilir)",
                                               exists=True, dir_okay=False)] = None,
    aci: Annotated[float, typer.Option(help="Derece, saat yönünün tersine")] = 45,
    opaklik: Annotated[float, typer.Option(min=0, max=1)] = 0.2,
    boyut: Annotated[float, typer.Option(help="Yazı boyutu (pt)")] = 72,
    renk: Annotated[str, typer.Option(help="#rrggbb")] = "#888888",
    arkada: Annotated[bool, typer.Option("--arkada", help="İçeriğin arkasına koy")] = False,
    sayfalar: Annotated[str, typer.Option(help="Yalnızca bu sayfalar (boş = hepsi)")] = "",
    cikti: OutOpt = None,
    sifre: PwOpt = None,
) -> None:
    """Yazı ya da resim filigranı ekler."""
    from pdfatolye.core.content import WatermarkOp, apply_ops

    op = WatermarkOp(type="watermark", text=yazi, asset="resim" if resim else None, angle=aci,
                     opacity=opaklik, size=boyut, color=renk, pages=sayfalar,
                     layer="back" if arkada else "front")
    out = cikti or _default_output(pdf, "filigranli")
    result = apply_ops(pdf, out, [op], password=sifre, assets={"resim": resim} if resim else {})
    for w in result.warnings:
        typer.secho(f"Uyarı: {w}", fg="yellow")
    _done(result.output)


@app.command("sayfa-no")
@friendly_errors
def sayfa_no(
    pdf: InPdf,
    bicim: Annotated[str, typer.Option(help="{n} = sayfa, {N} = toplam")] = "{n}",
    konum: Annotated[str, typer.Option(
        help="top-left, top-center, top-right, bottom-left, bottom-center, bottom-right")]
    = "bottom-center",
    baslangic: Annotated[int, typer.Option(help="İlk numara")] = 1,
    kapak: Annotated[bool, typer.Option("--kapak",
                                        help="İlk sayfaya numara koyma (kapak)")] = False,
    sayfalar: Annotated[str, typer.Option(help="Yalnızca bu sayfalar (boş = hepsi)")] = "",
    boyut: Annotated[float, typer.Option(help="Yazı boyutu (pt)")] = 11,
    cikti: OutOpt = None,
    sifre: PwOpt = None,
) -> None:
    """Sayfa numarası ekler: --bicim "Sayfa {n} / {N}"."""
    from pdfatolye.core.content import PageNumbersOp, apply_ops

    op = PageNumbersOp(type="page_numbers", format=bicim, position=konum, start=baslangic,
                       skip_first=kapak, pages=sayfalar, size=boyut)
    out = cikti or _default_output(pdf, "numarali")
    _done(apply_ops(pdf, out, [op], password=sifre).output)
