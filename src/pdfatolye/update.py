"""Yeni sürüm denetimi (yalnızca kullanıcı "Güncellemeleri denetle" derse).

GitHub Releases API'ye tek bir GET gider; hiçbir dosya ya da kişisel bilgi gönderilmez. Güncelleme
kendiliğinden indirilmez: kullanıcı sürüm sayfasından yeni paketi indirip "Kur"u çalıştırır
(belgeler ve ayarlar korunur).
"""

from __future__ import annotations

import json
import re
import urllib.error
import urllib.request

REPO = "CagriBurk/PdfConv"
LATEST_URL = f"https://api.github.com/repos/{REPO}/releases/latest"
RELEASES_PAGE = f"https://github.com/{REPO}/releases"
TIMEOUT_S = 8


def parse_version(text: str) -> tuple[int, ...] | None:
    m = re.match(r"^v?(\d+)\.(\d+)\.(\d+)", (text or "").strip())
    return tuple(int(x) for x in m.groups()) if m else None


def check(current: str) -> dict:
    out = {"current": current, "latest": None, "newer": False, "url": RELEASES_PAGE,
           "message": ""}
    req = urllib.request.Request(LATEST_URL, headers={
        "User-Agent": "pdfatolye-guncelleme", "Accept": "application/vnd.github+json"})
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT_S) as resp:
            data = json.load(resp)
    except urllib.error.HTTPError as e:
        out["message"] = ("Henüz yayımlanmış bir sürüm yok." if e.code == 404 else
                          f"GitHub yanıt vermedi ({e.code}); sonra yeniden dene.")
        return out
    except (OSError, ValueError):
        out["message"] = "İnternete ulaşılamadı; bağlantını denetleyip yeniden dene."
        return out
    tag = str(data.get("tag_name") or "")
    latest, mine = parse_version(tag), parse_version(current)
    out["latest"] = tag.lstrip("v") or None
    out["url"] = data.get("html_url") or RELEASES_PAGE
    out["newer"] = bool(latest and mine and latest > mine)
    out["message"] = (f"Yeni sürüm var: {out['latest']}." if out["newer"] else
                      "En güncel sürümü kullanıyorsun.")
    return out
