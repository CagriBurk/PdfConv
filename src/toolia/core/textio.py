"""Metin dosyalarının (.md, .txt) kod çözümü: tek yer. Komut satırı, iş çalışanları, HTML/metin
baskısı ve arayüzün metin ucu (`/api/files/{id}/text`) bunu kullanır.

Sıra: BOM (UTF-8 / UTF-16) → katı UTF-8 → Windows-1254 (Türkçe Windows'un eski varsayılanı;
Not Defteri'nin "ANSI" kaydı). Son durumda kullanıcıya not düşülür.
"""

from __future__ import annotations

import codecs

_BOMS = ((codecs.BOM_UTF8, "utf-8-sig"), (codecs.BOM_UTF16_LE, "utf-16"),
         (codecs.BOM_UTF16_BE, "utf-16"))


def decode_text(raw: bytes, name: str = "dosya") -> tuple[str, str | None]:
    """(metin, not). Not yalnızca UTF-8 dışı bir kodlamayla okunduysa doludur."""
    for bom, encoding in _BOMS:
        if raw.startswith(bom):
            return raw.decode(encoding, errors="replace"), None
    try:
        return raw.decode("utf-8"), None
    except UnicodeDecodeError:
        return (raw.decode("cp1254", errors="replace"),
                f"'{name}' UTF-8 değil; Windows-1254 (Türkçe) olarak okundu.")
