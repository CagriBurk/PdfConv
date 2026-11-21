"""Sağ tık → Gönder menüsünün girişi: `python -I -m toolia.gonder_menu pdf|jpg <dosyalar>`.

Gönder kısayolları bir .cmd/.bat dosyasını değil, doğrudan python.exe'yi çalıştırır. Gezgin
boşluk içermeyen yolları tırnaklamaz; cmd.exe de `&` işaretinden sonrasını ayrı bir komut sayar.
.cmd başlatıcısıyla `fatura&calc&.pdf` adlı bir dosya, Gönder → PDF'e çevir denince komut
çalıştırıyordu (GUVENLIK_PLANI.md, adım 1). Burada yollar cmd'den hiç geçmez: Windows onları
doğrudan Python'un argümanları olarak verir; `&`, `%`, `^`, `!` sıradan karakterdir.

Dosyalardan önce `--` konur: `-` ile başlayan bir dosya adı seçenek olarak okunamaz.
"""

from __future__ import annotations

import contextlib
import os
import sys

COMMANDS = {
    "pdf": ["gonder"],
    "jpg": ["donustur", "--hedef", "jpg"],
}
USAGE = "Kullanım: python -m toolia.gonder_menu pdf|jpg <dosyalar>"


def cli_args(kind: str, files: list[str]) -> list[str]:
    return [*COMMANDS[kind], "--", *files]


def run(argv: list[str]) -> int:
    """Komutu çalıştırır, çıkış kodunu döndürür (pencereyi kapatmaz)."""
    if not argv or argv[0] not in COMMANDS:
        print(USAGE, file=sys.stderr)
        return 2
    from toolia.cli import app

    try:
        app(args=cli_args(argv[0], argv[1:]), prog_name="toolia", standalone_mode=True)
    except SystemExit as e:
        if e.code is None:
            return 0
        return e.code if isinstance(e.code, int) else 1
    return 0


def main() -> None:
    # Çıktı bir boruya/dosyaya giderse Windows kod sayfası "ç", "→" yazamaz.
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")
    code = run(sys.argv[1:])
    # Eski .cmd'deki "if errorlevel 1 pause": hata olursa pencere açık kalır, okunabilsin.
    if code and os.environ.get("TOOLIA_GONDER_BEKLEME") != "0":
        with contextlib.suppress(EOFError, KeyboardInterrupt):
            input("\nBazı dosyalar çevrilemedi. Kapatmak için Enter'a bas...")
    sys.exit(code)


if __name__ == "__main__":
    main()
