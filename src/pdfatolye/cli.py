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
            return json.load(resp).get("status") == "ok"
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
