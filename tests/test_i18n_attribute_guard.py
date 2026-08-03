"""No i18n dual-span markup inside HTML attributes — rendered-page guard.

``t()`` — the ``engine.i18n`` helper and the equivalent ``{% macro t() %}`` most
page templates define locally — returns a dual-language pair::

    <span class="l-en">Views</span><span class="l-zh">视图</span>

Placed inside an attribute, ``aria-label="{{ t('Views','视图') }}"``, the FIRST
inner ``class="`` closes the attribute, the tag breaks, and the rest of the copy
leaks onto the page as visible text. Jinja raises nothing and the HTML still
parses, so every structural pin passes — only the RENDERED page shows it.
sector_central shipped exactly this (the rail's aria-label sat as literal text
above the nav buttons); alerts/factors then shipped the same shape live, and
committee/watchlist carried the ``| striptags`` variant, which keeps the tag
intact but smuggles Chinese into aria-label — against the house law that
attribute copy is plain English (title= already has its own source guard in
scripts/check_title_i18n.py; aria-label/placeholder/alt get theirs here, on the
rendered output, which also catches indirect routes like ``{{ tr(...) }}``).

The guard therefore renders each page the way scripts/build_site.py does —
autoescape on, the real ``engine.i18n`` helpers as globals (a template-local
``t`` macro shadows the global with identical output; the global covers any
template that calls ``t`` without defining one) — and walks every attribute of
every tag. Deliberately-bilingual carriers (``data-tip-zh=…``) are data-*
attributes and stay out of the plain-English set.

Extend PAGES when another t()-macro page joins the estate; the context is the
minimum that page needs to render under Jinja's default permissive Undefined
(missing scalars print empty, missing sequences iterate empty).
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest
from jinja2 import Environment, FileSystemLoader

from engine import i18n

ROOT = Path(__file__).resolve().parent.parent

PAGES: dict[str, dict] = {
    "alerts.html.j2": {
        "summary": {}, "regime": {}, "cross_asset": {}, "events": {},
        "risk_backdrop": {},
    },
    "committee.html.j2": {},
    "factors.html.j2": {
        "fac": {"factors": [], "factor_labels": {}, "leadership": [], "leaders": {}},
        "momo": {},
    },
    "watchlist.html.j2": {},
    "sector_central.html.j2": {"basket_member_syms": ["SPY"]},
}

_TAG = re.compile(r"<[a-zA-Z][^>]*>")
_ATTR = re.compile(r'([a-zA-Z_:][-a-zA-Z0-9_:.]*)\s*=\s*"([^"]*)"')
_CJK = re.compile(r"[一-鿿]")
# Attribute copy the estate keeps plain-English (assistive tech / tooltips /
# input hints). data-* attributes are exempt by construction — the l-en/l-zh
# swap happens in JS for those.
_PLAIN_ENGLISH_ATTRS = {"aria-label", "placeholder", "alt", "title"}


def _render(name: str) -> str:
    env = Environment(loader=FileSystemLoader(str(ROOT / "templates")),
                      autoescape=True)
    env.filters["min"] = lambda seq: min(seq)  # build_site.py's override
    env.globals.update(t=i18n.t, td=i18n.td, tr=i18n.tr, zip=zip,
                       SITE_BASE="https://example.invalid")
    return env.get_template(name).render(**PAGES[name])


@pytest.mark.parametrize("name", sorted(PAGES))
def test_no_i18n_markup_inside_an_html_attribute(name: str) -> None:
    html = _render(name)
    assert "<body" in html, f"{name} rendered to something that is not a page"
    for tag in _TAG.findall(html):
        for attr, val in _ATTR.findall(tag):
            assert "<span" not in val, (
                f"{name}: an i18n dual-span was expanded inside {attr}= — the "
                f"first inner class=\" closes the attribute, the tag breaks and "
                f"the copy leaks onto the page as visible text. Use a plain "
                f"English attribute value instead:\n  {tag[:170]}"
            )
            if attr.lower() in _PLAIN_ENGLISH_ATTRS:
                assert not _CJK.search(val), (
                    f"{name}: translated text inside {attr}= — attribute copy "
                    f"is plain English on this estate (striptags on t() is not "
                    f"a fix, it concatenates both languages):\n  {tag[:170]}"
                )
