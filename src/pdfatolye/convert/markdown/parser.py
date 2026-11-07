"""Markdown → HTML gövdesi. Formüller burada çizilmez; tarayıcıda KaTeX çizer.

Formüller markdown işlenmeden önce `dollarmath` ile korunur: `$a_1*b_2$` içindeki `_` ve `*`
vurgu sanılmaz. `100$ ile 200$` gibi ifadeler formül sayılmaz (açılıştan sonra / kapanıştan
önce boşluk ya da kapanıştan hemen sonra rakam olamaz).
"""

from __future__ import annotations

import html
import os
import re
import unicodedata
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import unquote, urlparse

import yaml
from markdown_it import MarkdownIt
from markdown_it.rules_core import StateCore
from mdit_py_plugins.amsmath import amsmath_plugin
from mdit_py_plugins.anchors import anchors_plugin
from mdit_py_plugins.dollarmath import dollarmath_plugin
from mdit_py_plugins.footnote import footnote_plugin
from mdit_py_plugins.front_matter import front_matter_plugin
from mdit_py_plugins.tasklists import tasklists_plugin
from pygments import highlight as pygments_highlight
from pygments.formatters import HtmlFormatter
from pygments.lexers import get_lexer_by_name
from pygments.util import ClassNotFound

from pdfatolye.convert.markdown.obsidian import IMAGE_EXTS, obsidian_plugin, preprocess

_TR_ASCII = str.maketrans("çğıöşüÇĞİÖŞÜâîûÂÎÛ", "cgiosuCGIOSUaiuAIU")
_IGNORED_DIRS = {".obsidian", ".trash", ".git", "node_modules"}


def slugify(text: str) -> str:
    """Başlık kimliği: 'Ödev 2: Işık' → 'odev-2-isik'."""
    text = unicodedata.normalize("NFC", text).translate(_TR_ASCII).lower()
    text = re.sub(r"[^a-z0-9]+", "-", text).strip("-")
    return text or "baslik"


@dataclass
class Heading:
    level: int
    id: str
    html: str  # satır içi biçimlendirme dahil (formül, kalın...)
    text: str  # düz metin (PDF yer imi / eşleştirme için)
    line: int


@dataclass
class ParsedMarkdown:
    body_html: str
    front_matter: dict
    headings: list[Heading]
    warnings: list[str] = field(default_factory=list)
    title: str | None = None


class AssetResolver:
    """Resim yollarını çözer: önce not klasörüne göre, sonra Obsidian kasasında dosya adıyla.

    Yalnızca resim uzantıları çözülür. `confine=True` iken (arayüzden gelen, güvenilmeyen not)
    not klasörü ve kasa dışına çıkılamaz: `C:/...`, `../..`, kasadan dışarı sembolik bağlar.
    """

    def __init__(self, base_dir: Path, vault: Path | None = None,
                 attachments: dict[str, Path] | None = None, *, confine: bool = False) -> None:
        self.base_dir = base_dir
        self.vault = vault
        self.confine = confine
        # Arayüzden notla birlikte yüklenen dosyalar: ad (küçük harf) → yol
        self.attachments = {k.lower(): v for k, v in (attachments or {}).items()}
        self._index: dict[str, Path] | None = None

    def _allowed(self, path: Path) -> bool:
        if not self.confine:
            return True
        roots = [self.base_dir, *([self.vault] if self.vault else [])]
        return any(path.is_relative_to(root.resolve()) for root in roots)

    def _vault_index(self) -> dict[str, Path]:
        if self._index is None:
            self._index = {}
            if self.vault and self.vault.is_dir():
                for root, dirs, files in os.walk(self.vault):
                    dirs[:] = [d for d in dirs if d not in _IGNORED_DIRS]
                    for f in files:
                        self._index.setdefault(f.lower(), Path(root) / f)
        return self._index

    def resolve(self, name: str) -> Path | None:
        name = unquote(name.strip())
        if not name or Path(name).suffix.lower() not in IMAGE_EXTS:
            return None
        if attached := self.attachments.get(Path(name).name.lower()):
            return attached
        candidates = [self.base_dir / name]
        if self.vault:
            candidates.append(self.vault / name)
        for c in candidates:
            if c.is_file() and self._allowed(c.resolve()):
                return c.resolve()
        found = self._vault_index().get(Path(name).name.lower())
        if found and self._allowed(found.resolve()):
            return found.resolve()
        return None


def is_remote(src: str) -> bool:
    return urlparse(src).scheme in ("http", "https", "ftp")


def _size_style(alias: str | None) -> tuple[str, str]:
    """Obsidian `|300` veya `|300x200` boyutu; aksi hâlde alias alt metindir."""
    if alias and (m := re.fullmatch(r"\s*(\d+)(?:x(\d+))?\s*", alias)):
        style = f"width:{m.group(1)}px"
        if m.group(2):
            style += f";height:{m.group(2)}px;object-fit:contain"
        return style, ""
    return "", alias or ""


def _render_embed(target: str, alias: str | None, env: dict) -> str:
    resolver: AssetResolver = env["resolver"]
    name = target.split("#", 1)[0]
    ext = Path(name).suffix.lower()
    if ext in IMAGE_EXTS:
        path = resolver.resolve(name)
        if path is None:
            env["warnings"].append(f"Resim bulunamadı: {name}")
            return f'<span class="missing">Resim bulunamadı: {html.escape(name)}</span>'
        style, alt = _size_style(alias)
        style_attr = f' style="{style}"' if style else ""
        src = html.escape(env["url_for"](path))
        return (f'<img src="{src}" alt="{html.escape(alt or Path(name).stem)}"'
                f"{style_attr}>")
    env["warnings"].append(f"Not/dosya gömme henüz desteklenmiyor: ![[{target}]]")
    return f'<span class="embed-note">Gömülü: {html.escape(alias or target)}</span>'


def _render_image(self, tokens, idx, options, env) -> str:
    tok = tokens[idx]
    src = tok.attrGet("src") or ""
    if src and not is_remote(src) and not src.startswith("data:"):
        path = env["resolver"].resolve(src)
        if path is None:
            env["warnings"].append(f"Resim bulunamadı: {src}")
            return f'<span class="missing">Resim bulunamadı: {html.escape(src)}</span>'
        tok.attrSet("src", env["url_for"](path))
    tok.attrs["alt"] = self.renderInlineAsText(tok.children or [], options, env)
    return self.renderToken(tokens, idx, options, env)


def _highlight(code: str, lang: str, _attrs) -> str:
    lang = (lang or "").strip().lower()
    try:
        lexer = get_lexer_by_name(lang) if lang else None
    except ClassNotFound:
        lexer = None
    body = (pygments_highlight(code, lexer, HtmlFormatter(nowrap=True)) if lexer
            else html.escape(code))
    cls = f' class="language-{html.escape(lang)}"' if lang else ""
    return f'<pre class="code highlight"><code{cls}>{body}</code></pre>\n'


def _math_line_rule(state: StateCore) -> None:
    """Satır içi formüllere bulundukları paragrafın satır numarasını yaz (hata raporu için)."""
    for tok in state.tokens:
        if tok.type == "inline" and tok.map and tok.children:
            for child in tok.children:
                if child.type.startswith("math_inline"):
                    child.meta["line"] = tok.map[0] + 1


# Render kuralları renderer'a bağlanır (add_render_rule); ilk parametre `self`.


def _math_inline(self, tokens, idx, options, env) -> str:
    tok = tokens[idx]
    display = tok.type == "math_inline_double"
    cls = "math-display" if display else "math-inline"
    line = tok.meta.get("line", "")
    return f'<span class="{cls}" data-line="{line}">{html.escape(tok.content)}</span>'


def _math_block(self, tokens, idx, options, env) -> str:
    tok = tokens[idx]
    line = tok.map[0] + 1 if tok.map else ""
    eqno = ""
    if tok.type == "math_block_label" and tok.info:
        eqno = f'<span class="eqno">({html.escape(tok.info)})</span>'
    return (f'<div class="math-display" data-line="{line}">{html.escape(tok.content)}</div>'
            f"{eqno}\n")


def _wrap_labeled(self, tokens, idx, options, env) -> str:
    return f'<div class="equation">{_math_block(self, tokens, idx, options, env)}</div>\n'


def build_markdown(breaks: bool = True) -> MarkdownIt:
    md = MarkdownIt("commonmark", {"html": True, "breaks": breaks, "highlight": _highlight})
    md.enable(["table", "strikethrough"])
    md.use(front_matter_plugin)
    md.use(dollarmath_plugin, allow_space=False, allow_digits=False, double_inline=True,
           allow_labels=True)
    md.use(amsmath_plugin)
    md.use(footnote_plugin)
    md.use(tasklists_plugin)
    md.use(anchors_plugin, min_level=1, max_level=6, slug_func=slugify)
    md.use(obsidian_plugin, embed_renderer=_render_embed)
    md.core.ruler.after("inline", "math_line", _math_line_rule)

    md.add_render_rule("math_inline", _math_inline)
    md.add_render_rule("math_inline_double", _math_inline)
    md.add_render_rule("math_block", _math_block)
    md.add_render_rule("math_block_label", _wrap_labeled)
    md.add_render_rule("amsmath", _math_block)
    md.add_render_rule("image", _render_image)
    return md


def _plain_text(children) -> str:
    out = []
    for c in children or []:
        if c.type in ("text", "code_inline", "math_inline", "math_inline_double"):
            out.append(c.content)
        elif c.type == "obsidian_link":
            out.append(c.meta.get("alias") or c.meta["target"])
        elif c.children:
            out.append(_plain_text(c.children))
    return "".join(out).strip()


def parse_markdown(
    text: str,
    *,
    base_dir: Path,
    vault: Path | None = None,
    breaks: bool = True,
    url_for: Callable[[Path], str] | None = None,
    attachments: dict[str, Path] | None = None,
    confine: bool = False,
) -> ParsedMarkdown:
    """`breaks=True` Obsidian varsayılanıdır: tek satır sonu da satır kırar.

    `url_for` yerel resim yolunu HTML'de kullanılacak adrese çevirir. Baskıda file:// adresi,
    tarayıcı önizlemesinde sunucunun verdiği geçici adres kullanılır. `confine` için bkz.
    `AssetResolver`.
    """
    md = build_markdown(breaks)
    env: dict = {"warnings": [],
                 "resolver": AssetResolver(base_dir, vault, attachments, confine=confine),
                 "url_for": url_for or (lambda p: p.as_uri())}
    # Windows (CRLF) ve eski Mac (CR) satır sonları: satır sonu düzenli ifadeleri \n bekler.
    text = text.lstrip("﻿").replace("\r\n", "\n").replace("\r", "\n")
    tokens = md.parse(preprocess(text), env)

    front: dict = {}
    if tokens and tokens[0].type == "front_matter":
        try:
            loaded = yaml.safe_load(tokens[0].content) or {}
            front = loaded if isinstance(loaded, dict) else {}
        except yaml.YAMLError as e:
            env["warnings"].append(f"Ön bilgi (YAML) okunamadı: {e}")

    headings: list[Heading] = []
    for i, tok in enumerate(tokens):
        if tok.type == "heading_open":
            inline = tokens[i + 1]
            headings.append(Heading(
                level=int(tok.tag[1]),
                id=tok.attrGet("id") or "",
                html=md.renderer.renderInline(inline.children or [], md.options, env),
                text=_plain_text(inline.children),
                line=(tok.map[0] + 1) if tok.map else 0,
            ))

    body = md.renderer.render(tokens, md.options, env)
    title = front.get("title") or front.get("baslik") or front.get("başlık")
    if not title and headings and headings[0].level == 1:
        title = headings[0].text
    # Aynı uyarı birden çok kez çıkmasın, sıra korunsun.
    warnings = list(dict.fromkeys(env["warnings"]))
    return ParsedMarkdown(body, front, headings, warnings, str(title) if title else None)


def pygments_css() -> str:
    return HtmlFormatter(style="friendly").get_style_defs(".highlight")
