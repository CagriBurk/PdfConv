"""Seçenekler ve tam HTML belgesi (tema, kapak, içindekiler, KaTeX betiği)."""

from __future__ import annotations

import base64
import datetime as dt
import hashlib
import html
import json
from dataclasses import dataclass, field, fields, replace
from pathlib import Path

from pdfatolye.convert.markdown.parser import Heading, ParsedMarkdown, pygments_css

ASSETS = Path(__file__).parent / "assets"
THEMES = ("ders", "rapor", "sade")
PAPERS = ("A4", "A5", "A3", "Letter", "Legal")
TR_MONTHS = ("Ocak", "Şubat", "Mart", "Nisan", "Mayıs", "Haziran", "Temmuz", "Ağustos",
             "Eylül", "Ekim", "Kasım", "Aralık")


@dataclass
class MdOptions:
    """None olan alanlar ön bilgideki (front matter `pdf:`) değerden, o da yoksa varsayılandan
    gelir. Öncelik: komut/arayüz > ön bilgi > varsayılan."""

    theme: str | None = None
    paper: str | None = None
    landscape: bool | None = None
    margin_mm: float | None = None
    toc: bool | None = None
    toc_depth: int | None = None
    cover: bool | None = None
    page_numbers: bool | None = None
    font_size_pt: float | None = None
    breaks: bool | None = None
    macros: dict[str, str] = field(default_factory=dict)


DEFAULTS = MdOptions(theme="ders", paper="A4", landscape=False, margin_mm=18, toc=False,
                     toc_depth=3, cover=False, page_numbers=True, font_size_pt=None,
                     breaks=True)

# Ön bilgideki `pdf:` anahtarları (Türkçe ve İngilizce) → MdOptions alanı
FRONT_MATTER_KEYS = {
    "tema": "theme", "theme": "theme",
    "kagit": "paper", "kağıt": "paper", "paper": "paper",
    "yatay": "landscape", "landscape": "landscape",
    "kenar": "margin_mm", "margin": "margin_mm",
    "icindekiler": "toc", "içindekiler": "toc", "toc": "toc",
    "icindekiler_derinlik": "toc_depth", "toc_depth": "toc_depth",
    "kapak": "cover", "cover": "cover",
    "sayfa_no": "page_numbers", "page_numbers": "page_numbers",
    "yazi_boyutu": "font_size_pt", "font_size": "font_size_pt",
    "satir_sonu": "breaks", "breaks": "breaks",
    "makrolar": "macros", "macros": "macros",
}


def options_from_front_matter(front: dict, warnings: list[str]) -> MdOptions:
    raw = front.get("pdf")
    if raw is None:
        return MdOptions()
    if not isinstance(raw, dict):
        warnings.append("Ön bilgideki 'pdf:' bir sözlük olmalı; yok sayıldı.")
        return MdOptions()
    opts = MdOptions()
    for key, value in raw.items():
        name = FRONT_MATTER_KEYS.get(str(key).lower())
        if name is None:
            warnings.append(f"Ön bilgide bilinmeyen pdf ayarı: {key}")
            continue
        if name == "macros":
            if isinstance(value, dict):
                opts.macros = {str(k): str(v) for k, v in value.items()}
            continue
        setattr(opts, name, value)
    return opts


def resolve_options(explicit: MdOptions, front: dict, warnings: list[str],
                    user_defaults: MdOptions | None = None) -> MdOptions:
    """Katmanları birleştirir ve değerleri doğrular: yerleşik varsayılan < kullanıcının
    Ayarlar'daki varsayılanı (tema, kağıt) < notun ön bilgisi < komut / arayüz seçimi."""
    from_front = options_from_front_matter(front, warnings)
    merged = replace(DEFAULTS)
    for f in fields(MdOptions):
        if f.name == "macros":
            continue
        for layer in (user_defaults or MdOptions(), from_front, explicit):
            value = getattr(layer, f.name)
            if value is not None:
                setattr(merged, f.name, value)
    merged.macros = {**from_front.macros, **explicit.macros}

    if merged.theme not in THEMES:
        warnings.append(f"Bilinmeyen tema '{merged.theme}'; 'ders' kullanıldı.")
        merged.theme = "ders"
    paper = next((p for p in PAPERS if p.lower() == str(merged.paper).lower()), None)
    if paper is None:
        warnings.append(f"Bilinmeyen kağıt '{merged.paper}'; A4 kullanıldı.")
        paper = "A4"
    merged.paper = paper
    try:
        merged.margin_mm = min(max(float(merged.margin_mm), 0), 60)
        merged.toc_depth = min(max(int(merged.toc_depth), 1), 6)
        if merged.font_size_pt is not None:
            merged.font_size_pt = min(max(float(merged.font_size_pt), 6), 24)
    except (TypeError, ValueError):
        warnings.append("Kenar / derinlik / yazı boyutu sayı olmalı; varsayılan kullanıldı.")
        merged.margin_mm, merged.toc_depth, merged.font_size_pt = 18, 3, None
    return merged


def format_date(value) -> str:
    if isinstance(value, dt.datetime):
        value = value.date()
    if isinstance(value, dt.date):
        return f"{value.day} {TR_MONTHS[value.month - 1]} {value.year}"
    return str(value)


def _meta_line(front: dict) -> str:
    author = front.get("author") or front.get("yazar")
    date = front.get("date") or front.get("tarih")
    if isinstance(author, list):
        author = ", ".join(map(str, author))
    parts = [html.escape(str(author))] if author else []
    if date:
        parts.append(html.escape(format_date(date)))
    return " · ".join(parts)


def _title_block(parsed: ParsedMarkdown, opts: MdOptions) -> str:
    front = parsed.front_matter
    explicit_title = front.get("title") or front.get("baslik") or front.get("başlık")
    meta = _meta_line(front)
    if opts.cover:
        title = explicit_title or parsed.title or ""
        subtitle = front.get("subtitle") or front.get("altbaslik") or front.get("alt_baslik")
        sub = f'<div class="subtitle">{html.escape(str(subtitle))}</div>' if subtitle else ""
        meta_html = f'<div class="meta">{meta}</div>' if meta else ""
        return (f'<section class="cover"><div class="title">{html.escape(str(title))}</div>'
                f"{sub}{meta_html}</section>")
    if explicit_title:
        meta_html = f'<div class="meta">{meta}</div>' if meta else ""
        return (f'<header class="doc-title"><div class="title">'
                f"{html.escape(str(explicit_title))}</div>{meta_html}</header>")
    return ""


def toc_html(headings: list[Heading], depth: int) -> str:
    """İç içe liste. Sayfa numaraları ilk baskıdan sonra doldurulur ('000' yer tutucu,
    aynı genişlikte olduğu için yerleşim değişmez)."""
    items = [h for h in headings if h.level <= depth and h.id]
    if not items:
        return ""
    # Seviye atlamalarını (h1 → h3) düzelt: her başlığın derinliği en fazla bir artar.
    ancestors: list[int] = []
    depths = []
    for h in items:
        while ancestors and ancestors[-1] >= h.level:
            ancestors.pop()
        ancestors.append(h.level)
        depths.append(len(ancestors))

    out = ['<nav class="toc"><div class="toc-heading">İçindekiler</div>']
    current = 0
    for i, (h, d) in enumerate(zip(items, depths, strict=True)):
        if d > current:
            out.append("<ol>")
        else:
            out.append("</li>" + "</ol></li>" * (current - d))
        current = d
        out.append(
            f'<li class="toc-l{d}"><a href="#{html.escape(h.id)}">'
            f'<span class="toc-text">{h.html}</span><span class="toc-dots"></span>'
            f'<span class="toc-page" data-toc-index="{i}">000</span></a>'
        )
    out.append("</li>" + "</ol></li>" * (current - 1) + "</ol></nav>")
    return "".join(out)


def toc_headings(headings: list[Heading], depth: int) -> list[Heading]:
    """İçindekilerde gösterilen başlıklar (data-toc-index sırasıyla)."""
    return [h for h in headings if h.level <= depth and h.id]


# Obsidian (MathJax) ortamları otomatik numaralamaz; KaTeX numaralar. Aynı görünsün diye
# numarasız (*) sürümlerine çevrilir. Elle etiket gerekiyorsa `$$ ... $$ (1)` kullanılır.
#
# `window.__paRender(kök)`: arayüzün canlı önizlemesi içeriği yerinde güncellerken (sayfa yeniden
# yüklenmeden, kaydırma konumu korunarak) yeni formülleri de bununla çizer.
KATEX_SCRIPT = r"""
(async () => {
  const macros = JSON.parse(document.getElementById('katex-macros').textContent);
  if (typeof katex === 'undefined') {
    window.__sonuc = {fatal: 'KaTeX yüklenemedi'};
    return;
  }
  const unnumbered = /\\(begin|end)\{(equation|align|alignat|gather|multline|flalign)\}/g;
  window.__paRender = (root) => {
    const errors = [];
    for (const el of root.querySelectorAll('.math-inline, .math-display')) {
      const tex = el.textContent;
      try {
        katex.render(tex.replace(unnumbered, '\\$1{$2*}'), el, {
          displayMode: el.classList.contains('math-display'),
          throwOnError: true, macros, strict: 'ignore', trust: false, output: 'html',
        });
      } catch (e) {
        errors.push({line: el.dataset.line || '', message: String(e && e.message || e)});
        el.classList.add('math-error');
        el.textContent = tex;
      }
    }
    return errors;
  };
  const errors = window.__paRender(document);
  await Promise.all([...document.images].map(img => img.complete ? null :
    new Promise(r => { img.onload = img.onerror = r; })));
  await document.fonts.ready;
  const broken = [...document.images].filter(i => !i.naturalWidth)
    .map(i => decodeURI(i.getAttribute('src') || ''));
  window.__sonuc = {errors, broken};
})();
"""


# Ekranda önizleme: kağıt görünümü, sayfa sonları kesik çizgi. Baskıda kullanılmaz.
PREVIEW_CSS = """
html { background: #e7e5e4; }
body { max-width: 210mm; margin: 16px auto; padding: 18mm; box-sizing: border-box;
       box-shadow: 0 1px 4px rgb(0 0 0 / 0.18); }
body.yatay { max-width: 297mm; }
.page-break, .cover, .toc { border-bottom: 2px dashed #a8a29e; padding-bottom: 1em;
       margin-bottom: 1.5em; }
.cover { padding-top: 6em; }
.toc .toc-page { visibility: hidden; }  /* numaralar yalnızca PDF'te hesaplanır */
@media (max-width: 700px) { body { padding: 16px; margin: 0; box-shadow: none; } }
"""


def preview_csp(nonce: str, katex_url: str) -> str:
    """Önizleme için içerik güvenlik politikası: yalnızca bizim betiklerimiz (nonce) ve KaTeX
    dosyaları çalışır. Notun içindeki <script>, onclick=... gibi şeyler çalışmaz, ağa çıkılmaz."""
    return (
        f"default-src 'none'; script-src 'nonce-{nonce}' {katex_url}; "
        f"style-src 'unsafe-inline' {katex_url}; font-src {katex_url}; img-src 'self' data:; "
        "base-uri 'none'; form-action 'none'; frame-src 'none'; connect-src 'none'"
    )


def print_csp(nonce: str) -> str:
    """PDF baskısı için aynı politika: belge file: adresinden açılır; resimler ve KaTeX fontları
    yereldir, ağ ve çerçeve yoktur. Hangi yerel dosyanın açılacağını `browser.py` denetler."""
    return (
        f"default-src 'none'; script-src 'nonce-{nonce}'; style-src 'unsafe-inline' file:; "
        "font-src file: data:; img-src file: data:; base-uri 'none'; form-action 'none'; "
        "frame-src 'none'; connect-src 'none'; object-src 'none'"
    )


def katex_script_hash() -> str:
    """Önizleme çerçevesindeki satır içi KaTeX betiğinin CSP özeti. srcdoc çerçevesi uygulamanın
    politikasını da devralır; uygulama politikası yalnızca bu betiğe izin verir."""
    digest = hashlib.sha256(KATEX_SCRIPT.encode("utf-8")).digest()
    return "sha256-" + base64.b64encode(digest).decode("ascii")


def build_html(parsed: ParsedMarkdown, opts: MdOptions, katex_dir: str = "katex",
               preview: bool = False, csp: str | None = None, nonce: str | None = None) -> str:
    """Tek dosyalık HTML. KaTeX dosyaları `katex_dir` göreli yolundan yüklenir.

    `csp` ve `nonce` verilirse sayfaya içerik güvenlik politikası eklenir (tarayıcı önizlemesi).
    """
    themes = ASSETS / "themes"
    css = "\n".join([
        (themes / "base.css").read_text(encoding="utf-8"),
        (themes / f"{opts.theme}.css").read_text(encoding="utf-8"),
        pygments_css(),
    ])
    if opts.font_size_pt:
        css += f"\n:root {{ --font-size: {opts.font_size_pt}pt; }}"
    if preview:
        css += PREVIEW_CSS
    title = html.escape(parsed.title or "Belge")
    toc = toc_html(parsed.headings, opts.toc_depth) if opts.toc else ""
    macros = json.dumps(opts.macros, ensure_ascii=False).replace("</", "<\\/")
    n = f' nonce="{html.escape(nonce)}"' if nonce else ""
    csp_meta = (f'<meta http-equiv="Content-Security-Policy" content="{html.escape(csp)}">'
                if csp else "")
    return f"""<!doctype html>
<html lang="tr">
<head>
<meta charset="utf-8">
{csp_meta}
<title>{title}</title>
<link rel="stylesheet" href="{katex_dir}/katex.min.css">
<style>{css}</style>
<script{n} src="{katex_dir}/katex.min.js"></script>
<script{n} src="{katex_dir}/contrib/mhchem.min.js"></script>
<script type="application/json" id="katex-macros">{macros}</script>
</head>
<body class="{'yatay' if opts.landscape else ''}">
{_title_block(parsed, opts)}
{toc}
<main class="content">
{parsed.body_html}
</main>
<script{n}>{KATEX_SCRIPT}</script>
</body>
</html>
"""
