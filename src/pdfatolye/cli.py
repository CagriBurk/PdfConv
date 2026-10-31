"""Komut satırı: `pdfatolye serve`, `pdfatolye motorlar`."""

from __future__ import annotations

import json
import socket
import threading
import urllib.request
import webbrowser
from pathlib import Path
from typing import Annotated

import typer

from pdfatolye import engines
from pdfatolye.settings import load_settings

app = typer.Typer(help="PDF Atölyesi — yerel PDF araç seti", no_args_is_help=True)

ConfigOpt = Annotated[Path | None, typer.Option("--config", help="config.toml yolu")]


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
