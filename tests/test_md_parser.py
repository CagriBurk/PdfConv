import re
from pathlib import Path

import pytest

from pdfatolye.convert.markdown.document import (
    MdOptions,
    build_html,
    resolve_options,
    toc_html,
)
from pdfatolye.convert.markdown.obsidian import preprocess
from pdfatolye.convert.markdown.parser import Heading, parse_markdown, slugify
from pdfatolye.convert.markdown.render import match_heading_pages
from tests.fixtures import make_fixtures as fx


def body(text: str, base: Path = Path("."), **kw) -> str:
    return parse_markdown(text, base_dir=base, **kw).body_html


# --- formüller ---------------------------------------------------------------------------


def test_math_is_protected_from_markdown():
    html = body("Formül $a_1*b_2*c_3$ burada.")
    assert '<span class="math-inline" data-line="1">a_1*b_2*c_3</span>' in html
    assert "<em>" not in html


def test_money_is_not_math():
    html = body("Fiyat 100$ ile 200$ arası, $ 5 $ de değil.")
    assert "math-inline" not in html


def test_display_math_labels_and_align():
    html = body("$$\nE=mc^2\n$$ (3)\n\n\\begin{align}\na&=b\n\\end{align}\n")
    assert '<span class="eqno">(3)</span>' in html
    assert "\\begin{align}" in html
    assert "a &amp;= b" not in html and "a&amp;=b" in html


def test_double_dollar_inline_is_display():
    assert 'class="math-display"' in body("Satırda $$x^2$$ var.")


def test_math_line_numbers():
    html = body("ilk\n\nikinci $x$\n\n$$\ny\n$$\n")
    assert 'data-line="3">x<' in html
    assert 'data-line="5">' in html


# --- Obsidian ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("src", "cls", "title"),
    [
        ("> [!note]\n> içerik", "callout-blue", "Not"),
        ("> [!WARNING] Dikkat\n> içerik", "callout-orange", "Dikkat"),
        ("> [!tip]- Katlanır\n> içerik", "callout-teal", "Katlanır"),
        ("> [!ozel] Benim\n> içerik", "callout-blue", "Benim"),
    ],
)
def test_callouts(src, cls, title):
    html = body(src)
    assert f'class="callout {cls}"' in html
    assert f'<div class="callout-title">{title}</div>' in html
    assert "<p>içerik</p>" in html


def test_callout_title_with_markdown_and_no_body():
    html = body("> [!info] **Kalın** ve $x$")
    assert '<div class="callout-title"><strong>Kalın</strong> ve <span class="math-inline"' in html
    assert "<p></p>" not in html


def test_nested_callout():
    html = body("> [!note] Dış\n> > [!tip] İç\n> > metin")
    assert html.count('class="callout callout-') == 2


def test_plain_blockquote_untouched():
    html = body("> sadece alıntı")
    assert "callout" not in html and "<blockquote>" in html


@pytest.mark.parametrize(
    ("src", "text"),
    [("[[Not]]", "Not"), ("[[Not|Takma]]", "Takma"), ("[[Not#Başlık]]", "Not › Başlık")],
)
def test_wikilinks(src, text):
    assert f'<span class="wikilink">{text}</span>' in body(src)


def test_heading_wikilinks_render_as_anchor_links():
    src = (
        "# Ödev 2: Işık\n\n"
        "## Ödev 2: Işık\n\n"
        "[[#Ödev 2: Işık]] ve [[#Ödev 2: Işık|Ödeve git]] ve [[#Ödev 2: Işık-2|İkinci]]"
    )
    html = body(src)
    assert '<a class="wikilink" href="#odev-2-isik">Ödev 2: Işık</a>' in html
    assert '<a class="wikilink" href="#odev-2-isik">Ödeve git</a>' in html
    assert '<a class="wikilink" href="#odev-2-isik-2">İkinci</a>' in html


def test_ai_latex_delimiters_normalized_outside_code():
    src = (
        "Satır içi \\( a_1 * b_2 \\) ve \\(x^2\\).\n\n"
        "\\[\nE = mc^2\n\\]\n\n"
        "Blok içi \\[y = mx + b\\] burada.\n\n"
        "Kod içi `\\(koru\\)` ve ``\\[koru2\\]``.\n\n"
        "```tex\n\\(kod_blok\\)\n\\[\nkod_blok_display\n\\]\n```\n\n"
        "~~~markdown\n\\[tilde_blok\\]\n~~~\n"
    )
    html = body(src)
    assert '<span class="math-inline" data-line="1">a_1 * b_2</span>' in html
    assert '<span class="math-inline" data-line="1">x^2</span>' in html
    assert "<em>" not in html
    assert '<div class="math-display" data-line="3">\nE = mc^2\n</div>' in html
    assert '<span class="math-display" data-line="7">y = mx + b</span>' in html
    assert "<code>\\(koru\\)</code>" in html
    assert "<code>\\[koru2\\]</code>" in html
    assert html.count('class="math-inline"') == 2
    assert html.count('class="math-display"') == 2
    plain = re.sub(r"<[^>]+>", "", html)
    assert "\\(kod_blok\\)" in plain
    assert "\\[\nkod_blok_display\n\\]" in plain
    assert "\\[tilde_blok\\]" in plain


def test_ai_latex_escaped_backslashes_and_unclosed():
    out = preprocess(
        "Kaçışlı \\\\(degil\\\\) ve \\\\\\(evet\\) ve \\[a \\\\[6pt] b\\] ve \\(acik"
    )
    assert "\\\\(degil\\\\)" in out
    assert "\\\\$evet$" in out
    assert "$$a \\\\[6pt] b$$" in out
    assert out.endswith("\\(acik")


def test_embedded_image_resolution_and_size(tmp_path):
    (tmp_path / "ekler").mkdir()
    img = fx.transparent_png(tmp_path / "ekler" / "devre şeması.png")
    note_dir = tmp_path / "notlar"
    note_dir.mkdir()
    r = parse_markdown("![[devre şeması.png|300]]", base_dir=note_dir, vault=tmp_path)
    assert img.resolve().as_uri() in r.body_html
    assert 'style="width:300px"' in r.body_html
    assert r.warnings == []


def test_standard_image_relative_path(tmp_path):
    fx.transparent_png(tmp_path / "a b.png")
    html = body("![alt metin](a%20b.png)", base=tmp_path)
    assert (tmp_path / "a b.png").resolve().as_uri() in html
    assert 'alt="alt metin"' in html


def test_missing_image_and_note_embed_warn(tmp_path):
    r = parse_markdown("![[yok.png]]\n\n![[Başka not]]\n\n![x](yok2.jpg)", base_dir=tmp_path)
    assert r.warnings == [
        "Resim bulunamadı: yok.png",
        "Not/dosya gömme henüz desteklenmiyor: ![[Başka not]]",
        "Resim bulunamadı: yok2.jpg",
    ]


def test_remote_image_left_for_printer():
    html = body("![](https://example.com/a.png)")
    assert 'src="https://example.com/a.png"' in html


def test_mark_and_tags():
    html = body("==vurgulu **kalın**== #etiket #iç/içe 3#değil #123 C#")
    assert "<mark>vurgulu <strong>kalın</strong></mark>" in html
    assert '<span class="tag">#etiket</span>' in html
    assert '<span class="tag">#iç/içe</span>' in html
    assert html.count('class="tag"') == 2


def test_heading_is_not_a_tag():
    html = body("# Başlık\n## İkinci")
    assert "tag" not in html


def test_comments_removed_except_in_code():
    src = "a %%gizli%% b\n\n%%\nçok\nsatır\n%%\n\n```\n%%kalsın%%\n```\n`%%x%%`"
    out = preprocess(src)
    assert "gizli" not in out and "çok" not in out
    assert "%%kalsın%%" in out
    assert out.count("\n") == src.count("\n")  # satır numaraları kaymadı


@pytest.mark.parametrize("eol", ["\n", "\r\n"])
def test_pagebreak_markers(eol):
    src = "a\n\n\\newpage\n\nb\n\n<!-- pagebreak -->\n\nc\n\n```\n\\newpage\n```".replace("\n", eol)
    html = body(src)
    assert html.count('class="page-break"') == 2


def test_crlf_comments_and_callouts():
    html = body("> [!tip] Başlık\r\n> metin %%gizli%%\r\n")
    assert '<div class="callout-title">Başlık</div>' in html
    assert "gizli" not in html and "\r" not in html


def test_breaks_follow_obsidian_default():
    assert "<br />" in body("bir\niki")
    assert "<br />" not in body("bir\niki", breaks=False)


# --- başlıklar / ön bilgi / seçenekler -------------------------------------------------


def test_headings_ids_and_title():
    r = parse_markdown("# Ödev 2: Işık\n## Ödev 2: Işık\n### $x^2$ hesabı", base_dir=Path("."))
    # Kimlikte formül yer almaz (başlık kimliği yalnızca düz metni kullanır).
    assert [h.id for h in r.headings] == ["odev-2-isik", "odev-2-isik-2", "hesabi"]
    assert r.title == "Ödev 2: Işık"
    assert r.headings[2].text == "x^2 hesabı"


def test_heading_slug_deduplication():
    r = parse_markdown("# Giriş\n## Giriş\n### Giriş", base_dir=Path("."))
    assert [h.id for h in r.headings] == ["giris", "giris-2", "giris-3"]

    r2 = parse_markdown("# Giriş\n## Giriş 2\n### Giriş\n### Giriş", base_dir=Path("."))
    assert [h.id for h in r2.headings] == ["giris", "giris-2", "giris-3", "giris-4"]


def test_front_matter_title_wins():
    r = parse_markdown("---\ntitle: Ön Bilgi\n---\n# Başlık", base_dir=Path("."))
    assert r.title == "Ön Bilgi"
    assert r.headings[0].line == 4


def test_bad_front_matter_warns():
    r = parse_markdown("---\ntitle: [kapanmamış\n---\nmetin", base_dir=Path("."))
    assert any("YAML" in w for w in r.warnings)


def test_slugify():
    assert slugify("Çağrı'nın Ödevi — İş & Güç") == "cagri-nin-odevi-is-guc"


def test_option_precedence():
    warnings: list[str] = []
    front = {"pdf": {"tema": "rapor", "kagit": "letter", "icindekiler": True, "foo": 1,
                     "makrolar": {"\\R": "\\mathbb{R}"}}}
    opts = resolve_options(MdOptions(theme="sade"), front, warnings)
    assert opts.theme == "sade"  # komut satırı ön bilgiyi ezer
    assert opts.paper == "Letter"
    assert opts.toc is True
    assert opts.macros == {"\\R": "\\mathbb{R}"}
    assert warnings == ["Ön bilgide bilinmeyen pdf ayarı: foo"]


def test_invalid_options_fall_back():
    warnings: list[str] = []
    opts = resolve_options(MdOptions(theme="yok", paper="B5"), {}, warnings)
    assert (opts.theme, opts.paper) == ("ders", "A4")
    assert len(warnings) == 2


def test_toc_nesting_is_valid_html():
    hs = [Heading(1, "a", "A", "A", 1), Heading(3, "b", "B", "B", 2),
          Heading(2, "c", "C", "C", 3), Heading(1, "d", "D", "D", 4)]
    html = toc_html(hs, 3)
    assert html.count("<ol>") == html.count("</ol>")
    assert html.count("<li") == html.count("</li>") == 4
    assert 'class="toc-l2"' in html and 'class="toc-l3"' not in html  # h1→h3 atlaması düzeldi


def test_build_html_contains_assets_and_escapes_title():
    r = parse_markdown("# a < b & c", base_dir=Path("."))
    out = build_html(r, resolve_options(MdOptions(), {}, []))
    assert "katex/katex.min.js" in out
    assert "<title>a &lt; b &amp; c</title>" in out


def test_match_heading_pages_by_order_and_text():
    hs = [Heading(1, "a", "", "Giriş", 1), Heading(2, "b", "", "$x$", 2)]
    assert match_heading_pages(hs, [[1, "Giriş", 1], [2, "x", 3]]) == [1, 3]
    # Sayılar tutmuyorsa metinle eşleştir
    outline = [[1, "Kapak", 1], [1, "Giriş", 2], [2, "y", 3]]
    assert match_heading_pages(hs, outline) == [2, None]


def test_heading_with_inline_math_matches_wikilink():
    r = parse_markdown("# Bölüm $x$ Başlık\n\nBak: [[#Bölüm $x$ Başlık]]", base_dir=Path("."))
    assert len(r.headings) == 1
    hid = r.headings[0].id
    assert f'<h1 id="{hid}">' in r.body_html
    assert f'<a class="wikilink" href="#{hid}">Bölüm $x$ Başlık</a>' in r.body_html
