"""Telefon / LAN modu yardımcıları: yerel ağ adresleri ve QR kod.

LAN modunda sunucu 0.0.0.0'a bağlanır. Oturum çerezi yalnızca bu bilgisayara (loopback) ya da
QR koddaki eşleştirme belirteciyle (`?t=...`) gelen cihaza verilir; belirteçsiz istek reddedilir.
"""

from __future__ import annotations

import io
import ipaddress
import socket

import psutil

LOOPBACK_HOSTS = {"127.0.0.1", "::1", "localhost"}


def lan_ips() -> list[str]:
    """Bu bilgisayarın yerel ağdaki IPv4 adresleri; varsayılan çıkış arayüzü önce."""
    found: list[str] = []
    try:  # UDP "bağlantısı" paket göndermez; yalnızca hangi arayüzün kullanılacağını sorar.
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.connect(("10.255.255.255", 1))
            found.append(s.getsockname()[0])
    except OSError:
        pass
    for addrs in psutil.net_if_addrs().values():
        for a in addrs:
            if a.family == socket.AF_INET:
                found.append(a.address)
    out: list[str] = []
    for ip in found:
        addr = ipaddress.ip_address(ip)
        if addr.is_private and not addr.is_loopback and not addr.is_link_local and ip not in out:
            out.append(ip)
    return out


def qr_svg(text: str) -> str:
    import qrcode
    import qrcode.image.svg

    img = qrcode.make(text, image_factory=qrcode.image.svg.SvgPathImage, border=2)
    return img.to_string(encoding="unicode")


def qr_text(text: str) -> str:
    """Terminale basılacak QR (blok karakterleriyle)."""
    import qrcode

    qr = qrcode.QRCode(border=1)
    qr.add_data(text)
    buf = io.StringIO()
    qr.print_ascii(out=buf, invert=True)
    return buf.getvalue()
