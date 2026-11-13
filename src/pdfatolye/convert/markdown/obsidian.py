"""Obsidian sözdizimi: callout, [[wiki bağlantısı]], ![[gömme]], ==vurgu==, %%yorum%%, #etiket.

Ayrıca sayfa sonu işaretleri (`\\newpage`, `<!-- pagebreak -->`).
"""

from __future__ import annotations

import html
import re
from collections.abc import Callable

from markdown_it import MarkdownIt
from markdown_it.rules_core import StateCore
from markdown_it.rules_inline import StateInline
from markdown_it.token import Token

# --- Ön işleme (kod blokları hariç) ------------------------------------------------------

_FENCE = re.compile(r"^ {0,3}(`{3,}|~{3,})")
_COMMENT = re.compile(r"%%.*?%%", re.DOTALL)
_PAGEBREAK = re.compile(r"^[ \t]*(?:\\newpage|\\pagebreak|<!--\s*pagebreak\s*-->)[ \t]*$",
                        re.MULTILINE | re.IGNORECASE)
PAGEBREAK_HTML = '<div class="page-break"></div>'


def _split_code_fences(text: str) -> list[tuple[bool, str]]:
    """Metni (kod_mu, parça) listesine böler. Satır sayısı korunur."""
    parts: list[tuple[bool, str]] = []
    buf: list[str] = []
    fence: str | None = None
    for line in text.splitlines(keepends=True):
        m = _FENCE.match(line)
        if fence is None and m:
            if buf:
                parts.append((False, "".join(buf)))
            buf, fence = [line], m.group(1)
        elif fence is not None and m and m.group(1)[0] == fence[0] and len(m.group(1)) >= len(
            fence
        ) and not line.strip()[len(m.group(1)):].strip():
            buf.append(line)
            parts.append((True, "".join(buf)))
            buf, fence = [], None
        else:
            buf.append(line)
    if buf:
        parts.append((fence is not None, "".join(buf)))
    return parts


def _has_blank_line_at(text: str, pos: int) -> bool:
    """`pos` konumundaki satır sonundan sonra boş satır varsa True."""
    q = pos + 1
    n = len(text)
    while q < n and text[q] in " \t":
        q += 1
    return q < n and text[q] == "\n"


def _find_closing_backticks(text: str, start: int, tick_len: int) -> int:
    """`start` konumundan itibaren `tick_len` uzunluğunda kapanış ters tırnağı arar."""
    n = len(text)
    p = start
    while p < n:
        ch = text[p]
        if ch == "\n" and _has_blank_line_at(text, p):
            return -1
        if ch == "`":
            q = p
            while q < n and text[q] == "`":
                q += 1
            if q - p == tick_len:
                return p
            p = q
            continue
        p += 1
    return -1


def _find_closing_math(text: str, start: int, close_char: str) -> int:
    """`start` konumundan itibaren kaçışsız `\\<close_char>` kapanışını bulur."""
    n = len(text)
    p = start
    while p < n:
        ch = text[p]
        if ch == "\n" and _has_blank_line_at(text, p):
            return -1
        if ch == "\\" and p + 1 < n:
            if text[p + 1] == close_char:
                return p
            p += 2
            continue
        p += 1
    return -1


def _normalize_latex_delimiters(text: str) -> str:
    """AI tarzı `\\(...\\)` → `$...$` ve `\\[...\\]` → `$$...$$` dönüşümü (kod içi hariç)."""
    if "\\(" not in text and "\\[" not in text:
        return text
    out: list[str] = []
    n = len(text)
    i = 0
    while i < n:
        ch = text[i]
        if ch == "`":
            j = i
            while j < n and text[j] == "`":
                j += 1
            end = _find_closing_backticks(text, j, j - i)
            if end != -1:
                stop = end + (j - i)
                out.append(text[i:stop])
                i = stop
            else:
                out.append(text[i:j])
                i = j
            continue
        if ch == "\\" and i + 1 < n:
            nxt = text[i + 1]
            if nxt in ("(", "["):
                close_char = ")" if nxt == "(" else "]"
                end = _find_closing_math(text, i + 2, close_char)
                if end != -1:
                    inner = text[i + 2 : end]
                    if inner.strip():
                        if nxt == "(":
                            core = inner.strip()
                            lead_nl = "\n" * inner[: len(inner) - len(inner.lstrip())].count("\n")
                            trail_nl = "\n" * inner[len(inner.rstrip()) :].count("\n")
                            out.append(f"{lead_nl}${core}${trail_nl}")
                        else:
                            out.append(f"$${inner}$$")
                        i = end + 2
                        continue
            out.append(text[i : i + 2])
            i += 2
            continue
        out.append(ch)
        i += 1
    return "".join(out)


def preprocess(text: str) -> str:
    """%%yorum%% sil, sayfa sonu işaretlerini HTML'e ve AI LaTeX ayraçlarını `$` biçimine çevir."""
    out = []
    for is_code, part in _split_code_fences(text):
        if not is_code:
            part = _COMMENT.sub(lambda m: "\n" * m.group(0).count("\n"), part)
            part = _PAGEBREAK.sub(PAGEBREAK_HTML, part)
            part = _normalize_latex_delimiters(part)
        out.append(part)
    return "".join(out)


# --- Callout -----------------------------------------------------------------------------

CALLOUT_TITLES = {
    "note": "Not", "abstract": "Özet", "summary": "Özet", "tldr": "Özet", "info": "Bilgi",
    "todo": "Yapılacak", "tip": "İpucu", "hint": "İpucu", "important": "Önemli",
    "success": "Başarılı", "check": "Başarılı", "done": "Tamam", "question": "Soru",
    "help": "Yardım", "faq": "SSS", "warning": "Uyarı", "caution": "Dikkat",
    "attention": "Dikkat", "failure": "Başarısız", "fail": "Başarısız", "missing": "Eksik",
    "danger": "Tehlike", "error": "Hata", "bug": "Hata", "example": "Örnek", "quote": "Alıntı",
    "cite": "Alıntı", "definition": "Tanım", "theorem": "Teorem", "proof": "İspat",
    "formula": "Formül",
}
# Renk grubu (CSS sınıfı): aynı anlamdaki türler aynı renkte.
CALLOUT_GROUPS = {
    "note": "blue", "info": "blue", "todo": "blue", "definition": "blue",
    "abstract": "cyan", "summary": "cyan", "tldr": "cyan", "formula": "cyan",
    "tip": "teal", "hint": "teal", "important": "teal", "theorem": "teal",
    "success": "green", "check": "green", "done": "green",
    "question": "yellow", "help": "yellow", "faq": "yellow",
    "warning": "orange", "caution": "orange", "attention": "orange",
    "failure": "red", "fail": "red", "missing": "red", "danger": "red", "error": "red",
    "bug": "red",
    "example": "purple", "proof": "purple",
    "quote": "gray", "cite": "gray",
}
_CALLOUT_HEAD = re.compile(r"^\[!([A-Za-z][\w-]*)\]([+-]?)[ \t]*(.*)$")


def _callout_rule(state: StateCore) -> None:
    """Blok ayrıştırmadan sonra, satır içi ayrıştırmadan önce çalışır."""
    tokens = state.tokens
    i = 0
    while i < len(tokens):
        tok = tokens[i]
        if (
            tok.type == "blockquote_open"
            and i + 2 < len(tokens)
            and tokens[i + 1].type == "paragraph_open"
            and tokens[i + 2].type == "inline"
        ):
            inline = tokens[i + 2]
            first, _, rest = inline.content.partition("\n")
            m = _CALLOUT_HEAD.match(first.strip())
            if m:
                kind = m.group(1).lower()
                title = m.group(3).strip() or CALLOUT_TITLES.get(kind, kind.capitalize())
                tok.attrSet("class", f"callout callout-{CALLOUT_GROUPS.get(kind, 'blue')}")
                tok.attrSet("data-callout", kind)
                if m.group(2):
                    tok.attrSet("data-fold", m.group(2))

                title_open = Token("html_block", "", 0)
                title_open.content = '<div class="callout-title">'
                title_inline = Token("inline", "", 0)
                title_inline.content = title
                title_inline.map = inline.map
                title_inline.children = []
                title_close = Token("html_block", "", 0)
                title_close.content = "</div>\n"
                new = [title_open, title_inline, title_close]

                if rest.strip():
                    inline.content = rest
                    tokens[i + 1:i + 1] = new
                else:  # başlıktan sonra paragraf boş kaldı: paragrafı kaldır
                    tokens[i + 1:i + 4] = new
                i += len(new)
        i += 1


# --- Satır içi kurallar -----------------------------------------------------------------

IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".svg", ".bmp", ".avif"}
_WIKI = re.compile(r"(!?)\[\[([^\[\]\n|]+?)(?:\|([^\[\]\n]*))?\]\]")


def _wikilink_rule(state: StateInline, silent: bool) -> bool:
    if state.src[state.pos] not in "![":
        return False
    m = _WIKI.match(state.src, state.pos)
    if not m:
        return False
    if not silent:
        embed, target, alias = m.group(1) == "!", m.group(2).strip(), m.group(3)
        tok = state.push("obsidian_embed" if embed else "obsidian_link", "", 0)
        tok.meta = {"target": target, "alias": alias.strip() if alias is not None else None}
    state.pos = m.end()
    return True


def _mark_rule(state: StateInline, silent: bool) -> bool:
    src, pos = state.src, state.pos
    if not src.startswith("==", pos) or src.startswith("===", pos):
        return False
    end = src.find("==", pos + 2)
    if end == -1 or end == pos + 2 or src[pos + 2].isspace() or src[end - 1].isspace():
        return False
    if not silent:
        state.push("mark_open", "mark", 1)
        # İçerideki biçimlendirme (kalın, formül...) de işlensin.
        old_max = state.posMax
        state.pos, state.posMax = pos + 2, end
        state.md.inline.tokenize(state)
        state.posMax = old_max
        state.push("mark_close", "mark", -1)
    state.pos = end + 2
    return True


_TAG = re.compile(r"#([\w/-]*[^\W\d_][\w/-]*)", re.UNICODE)


def _tag_rule(state: StateInline, silent: bool) -> bool:
    pos = state.pos
    if state.src[pos] != "#":
        return False
    if pos > 0 and not state.src[pos - 1].isspace() and state.src[pos - 1] not in "([":
        return False
    m = _TAG.match(state.src, pos)
    if not m:
        return False
    if not silent:
        tok = state.push("obsidian_tag", "", 0)
        tok.content = m.group(1)
    state.pos = m.end()
    return True


# --- HTML çıktısı ------------------------------------------------------------------------


# Not: add_render_rule fonksiyonları renderer'a bağlar; ilk parametre `self` olur.


def _render_link(tokens, idx, slug_func: Callable[[str], str] | None = None) -> str:
    meta = tokens[idx].meta
    target: str = meta["target"]
    note, sep, heading = target.partition("#")
    if meta["alias"]:
        text = meta["alias"]
    elif note and heading:
        text = f"{note} › {heading.lstrip('^')}"
    else:
        text = note or heading
    if sep and not note:
        heading_name = heading.strip()
        if heading_name and not heading_name.startswith("^") and slug_func is not None:
            slug = slug_func(heading_name)
            return f'<a class="wikilink" href="#{html.escape(slug)}">{html.escape(text)}</a>'
    return f'<span class="wikilink">{html.escape(text)}</span>'


def _render_tag(self, tokens, idx, options, env) -> str:
    return f'<span class="tag">#{html.escape(tokens[idx].content)}</span>'


def obsidian_plugin(
    md: MarkdownIt,
    embed_renderer: Callable,
    slug_func: Callable[[str], str] | None = None,
) -> None:
    """`embed_renderer(target, alias, env) -> html` resim/not gömmelerini çizer."""
    md.core.ruler.after("block", "obsidian_callout", _callout_rule)
    md.inline.ruler.before("link", "obsidian_wikilink", _wikilink_rule)
    md.inline.ruler.before("emphasis", "obsidian_mark", _mark_rule)
    md.inline.ruler.push("obsidian_tag", _tag_rule)

    def render_link(self, tokens, idx, options, env) -> str:
        return _render_link(tokens, idx, slug_func=slug_func)

    md.add_render_rule("obsidian_link", render_link)
    md.add_render_rule("obsidian_tag", _render_tag)

    def render_embed(self, tokens, idx, options, env) -> str:
        return embed_renderer(tokens[idx].meta["target"], tokens[idx].meta["alias"], env)

    md.add_render_rule("obsidian_embed", render_embed)
