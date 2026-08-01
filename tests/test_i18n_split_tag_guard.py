"""Split-tag guard for the bilingual `t()` macro — the i18n-breaks-HTML class.

`templates/seo_base.html.j2`'s t() macro wraps EACH language in its OWN span:

    {%- macro t(en, zh='') -%}
    <span class="l-en">{{ en|safe }}</span><span class="l-zh">{{ zh|safe }}</span>

so a tag that opens inside one argument and closes outside it does not survive
the render. The shipped instance passed an OPENING anchor through t():

    {{ t('… with the <a href="', '用 <a href="') }}{{ rel }}tools/…/compounding.html">…

which rendered as

    <a href="</span><span class="l-zh">用 <a href="</span>../../tools/…">

— the anchor's href was literally `</span>`, so BOTH language copies of the link
were dead and the markup was malformed. 48 t() calls across the 26 calculator
pages carried it (96 dead href attributes, two per call).

Nothing caught it. `scripts/check_inline_js.py` only parses `<script>` bodies and
`on*=` handlers. `scripts/check_site_asset_refs.py` deliberately SKIPS refs
containing `<` — it proves file existence, not markup validity. And
`build_free_content --check` only pins committed bytes to a fresh render, so it
happily froze the broken output.

Two checks, one at each stage:

  1. RENDERED — no URL-valued attribute in committed site HTML may contain `<`.
     A `<` in an href/src is never legitimate; this is the shape a user hits.
  2. SOURCE — no t() argument may leave a tag open. This fires at PR time, one
     stage before a render, on the construction rather than its symptom.

Deliberately NOT a blanket "no attribute value contains `<`": `data-zh` carries
bilingual HTML fragments for the JS language swap on 261 committed pages, and
that is legitimate. The URL family is where `<` is unambiguously a defect.

Bare `<`/`>` as comparison operators in prose (`Calm <16`, `P(Sharpe>0)`,
`% > 50d MA`) are also legitimate and stay legal — check 2 keys on an UNCLOSED
tag open (`<` followed by a letter, `/` or `!` with no `>` after it), which is
the split-tag signature and nothing else.

Stdlib only: the free-content-estate job installs pytest/pyyaml/jinja2.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

_REPO = Path(__file__).resolve().parent.parent
_SITE = _REPO / "site"
_TEMPLATES = _REPO / "templates"

# ── detectors ────────────────────────────────────────────────────────────────

# an HTML attribute in `name="value"` form
_ATTR = re.compile(r'\s([a-zA-Z_:][-a-zA-Z0-9_:.]*)\s*=\s*"([^"]*)"')

# attribute names whose value is a URL. Matched on the last dash-separated
# segment so the `data-`/`xlink:` prefixed variants are covered too — here that
# breadth is wanted, unlike the `\b(href|src)=` footgun where `data-src=` was an
# accidental hit.
_URL_ATTR_TAILS = frozenset(
    {"href", "src", "srcset", "action", "poster", "formaction", "cite"}
)

# a t() call's argument list: one or more single-quoted Jinja literals
_T_CALL = re.compile(r"\{\{-?\s*t\(\s*((?:'(?:[^'\\]|\\.)*'\s*,?\s*)+)\)", re.S)
_LITERAL = re.compile(r"'((?:[^'\\]|\\.)*)'")
_COMPLETE_TAG = re.compile(r"<[^<>]*>")
_TAG_OPEN = re.compile(r"<[a-zA-Z/!]")


def _is_url_attr(name: str) -> bool:
    return name.lower().rsplit("-", 1)[-1] in _URL_ATTR_TAILS


def url_attrs_holding_a_tag(html: str) -> list[tuple[str, str]]:
    """(name, value) for every URL-valued attribute whose value contains `<`."""
    return [
        (m.group(1), m.group(2))
        for m in _ATTR.finditer(html)
        if "<" in m.group(2) and _is_url_attr(m.group(1))
    ]


def t_args_leaving_a_tag_open(source: str) -> list[str]:
    """Every t() argument in `source` that opens a tag it never closes."""
    out: list[str] = []
    for call in _T_CALL.finditer(source):
        for literal in _LITERAL.finditer(call.group(1)):
            body = literal.group(1)
            if _TAG_OPEN.search(_COMPLETE_TAG.sub("", body)):
                out.append(body)
    return out


# ── sentinels: the detectors must FIRE on the exact shipped defect ───────────
# Without these an edit that quietly narrows either regex turns both scans below
# into vacuous passes — a guard that cannot fail is not a guard.

_SHIPPED_TEMPLATE_LINE = (
    """{{ t('See how a balance grows deposit by deposit with the <a href="', """
    """'用 <a href="') }}{{ rel }}tools/calculators/compounding.html">"""
)
_SHIPPED_RENDERED_LINE = (
    '<span class="l-en">See how a balance grows deposit by deposit with the '
    '<a href="</span><span class="l-zh">用 <a href="</span>'
    '../../tools/calculators/compounding.html">'
)


def test_source_detector_fires_on_the_shipped_defect() -> None:
    """The savings_goal line as it stood at 78073f0 must be flagged."""
    hits = t_args_leaving_a_tag_open(_SHIPPED_TEMPLATE_LINE)
    assert len(hits) == 2, f"expected both language args flagged, got {hits}"
    assert all(h.rstrip().endswith('<a href="') for h in hits)


def test_rendered_detector_fires_on_the_shipped_defect() -> None:
    """The rendered `href="</span>"` must be flagged as a URL attribute."""
    hits = url_attrs_holding_a_tag(_SHIPPED_RENDERED_LINE)
    assert [n for n, _ in hits] == ["href", "href"], hits
    assert all(v.startswith("</span>") for _, v in hits)


def test_prose_comparison_operators_stay_legal() -> None:
    """`Calm <16` / `P(Sharpe>0)` are copy, not markup — never flag them."""
    for legal in ("Calm <16", "P(Sharpe>0)", "% > 50d MA", "ER>0 vs SPY", "return < 0"):
        assert not t_args_leaving_a_tag_open(f"{{{{ t('{legal}') }}}}"), legal
    # a complete tag inside ONE argument is the correct construction
    assert not t_args_leaving_a_tag_open(
        """{{ t('read the <a href="/x.html">lesson</a>.', '阅读<a href="/x.html">课程</a>。') }}"""
    )


# ── the tree-wide scans ──────────────────────────────────────────────────────


def test_no_rendered_url_attribute_contains_a_tag() -> None:
    """No committed page may ship an href/src whose value contains `<`."""
    pages = sorted(_SITE.rglob("*.html"))
    # coverage floor: a checkout that lost site/ must fail loudly, not pass
    # vacuously (site/ carried 3,488 pages when this guard was written).
    assert len(pages) > 2000, f"site/ scan saw only {len(pages)} pages — bad checkout?"

    violations: list[str] = []
    for page in pages:
        html = page.read_text(encoding="utf-8", errors="replace")
        for name, value in url_attrs_holding_a_tag(html):
            rel = page.relative_to(_REPO)
            violations.append(f"{rel}: {name}=\"{value[:60]}\"")

    assert not violations, (
        "URL attribute values must never contain `<` — a tag was split across a "
        "translation or concatenation boundary:\n  " + "\n  ".join(violations[:20])
    )


def test_no_t_macro_argument_leaves_a_tag_open() -> None:
    """No t() argument may open a tag it does not close (see module docstring)."""
    templates = sorted(_TEMPLATES.rglob("*.j2"))
    assert len(templates) > 100, f"templates/ scan saw only {len(templates)} files"

    violations: list[str] = []
    for tmpl in templates:
        source = tmpl.read_text(encoding="utf-8", errors="replace")
        for arg in t_args_leaving_a_tag_open(source):
            rel = tmpl.relative_to(_REPO)
            violations.append(f"{rel}: …{arg[-70:]!r}")

    assert not violations, (
        "a t() argument opens a tag it never closes. The t() macro wraps EACH "
        "language in its own span, so the tag cannot survive the render — keep "
        "the WHOLE element inside each language branch:\n  "
        + "\n  ".join(violations[:20])
    )


def _calculator_slugs() -> list[str]:
    return sorted(p.stem for p in (_SITE / "tools" / "calculators").glob("*.html"))


@pytest.mark.parametrize("slug", _calculator_slugs())
def test_calculator_related_links_resolve(slug: str) -> None:
    """The repaired anchors point at files that exist, in BOTH language spans."""
    page = _SITE / "tools" / "calculators" / f"{slug}.html"
    html = page.read_text(encoding="utf-8")
    para = re.search(r'<p class="mut"[^>]*>(.*?)</p>', html, re.S)
    assert para, f"{slug}: related-links paragraph missing"

    spans = re.findall(r'<span class="l-(en|zh)">(.*?)</span>', para.group(1), re.S)
    assert {lang for lang, _ in spans} == {"en", "zh"}, f"{slug}: {spans}"
    for lang, body in spans:
        hrefs = re.findall(r'<a href="([^"]+)"', body)
        assert hrefs, f"{slug}/{lang}: no anchor in this language branch"
        for href in hrefs:
            target = (
                _SITE / href.lstrip("/")
                if href.startswith("/")
                else (page.parent / href).resolve()
            )
            assert Path(target).is_file(), f"{slug}/{lang}: dead link {href}"
