"""China Sector Intelligence consolidation invariants (2026-08 merge of
baskets_china + subsector_rotation_china into sector_central_china.html).

Sibling of tests/test_sector_intelligence_page.py, which pins the US merge; this
file pins the China one so a later template edit cannot silently undo it: the two
redirect stubs and their HASH FORWARDING, the merged page's section skeleton, the
payload externalization (no inline BASKETS/CHART embed), the inbound-hash contract,
the THS-survival fork, the collapsed nav, the ZH vocabulary ruling, and the
inverse guard that the US siblings were left alone.

Charter: research/CHINA_SECTOR_INTELLIGENCE_CONSOLIDATION_MASTERPLAN_BY_FABLE.md §0.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest
from jinja2 import Environment, FileSystemLoader

ROOT = Path(__file__).resolve().parent.parent
TPL = ROOT / "templates"

MERGED = "sector_central_china.html.j2"

# (template, deep-link anchor the bare URL falls back to)
STUBS = [
    ("baskets_china.html.j2", "#si-explore"),
    ("subsector_rotation_china.html.j2", "#si-movement"),
]


def _read(p: Path) -> str:
    assert p.exists(), f"{p} missing"
    return p.read_text(encoding="utf-8")


def _render(name: str) -> str:
    """Render a stub the way scripts/build_baskets_china.py does — contextless.

    Asserting on the RENDERED bytes rather than the source is deliberate: both
    stubs name openBasket/openTheme inside a ``{# ... #}`` Jinja comment that
    documents where those handlers went, and a source-level ban would trip on the
    documentation instead of on real resurrected code.
    """
    env = Environment(loader=FileSystemLoader(str(TPL)), autoescape=True)
    return env.get_template(name).render()


# ---------------------------------------------------------------- stubs

@pytest.mark.parametrize("name,anchor", STUBS, ids=lambda v: str(v).split(".")[0])
def test_redirect_stub(name: str, anchor: str) -> None:
    src = _read(TPL / name)
    target = f"sector_central_china.html{anchor}"
    assert f'content="0;url={target}"' in src, "meta refresh missing/retargeted"
    assert 'name="robots" content="noindex,follow"' in src
    assert f'{{% set seo_path = "sector_central_china.html" %}}' in src, \
        "canonical must point at the merged page"
    # A stub must never regrow page content.
    assert len(src) < 4000, f"{name} is {len(src)} chars — no longer a stub?"


@pytest.mark.parametrize("name,anchor", STUBS, ids=lambda v: str(v).split(".")[0])
def test_stub_forwards_the_inbound_hash(name: str, anchor: str) -> None:
    """A bare visit lands on the section anchor; a deep link keeps its own hash.

    Unlike the US stubs (which replace to a fixed anchor), the China pages carried
    live ``#b-<id>`` / ``#theme-<id>`` deep links from alerts, the dashboard chips
    and 22 basket detail pages. Dropping the inbound hash would land every one of
    them on the top of the merged page — the silent-no-op class this repo already
    ate once on the US page (tests/test_theme_hash_deeplink.py docstring).
    """
    src = _read(TPL / name)
    forward = (
        "location.replace('sector_central_china.html'"
        f"+(location.hash?location.hash:'{anchor}'))"
    )
    assert forward in src, f"{name} lost its hash-forwarding redirect"


@pytest.mark.parametrize("name,anchor", STUBS, ids=lambda v: str(v).split(".")[0])
def test_stub_ships_no_page_machinery(name: str, anchor: str) -> None:
    """The rendered stub carries no payload, no desk boot and no rotation config."""
    html = _render(name)
    for tok in ("BASKETS", "SR_CFG", "openTheme", "openBasket",
                "baskets_desk.js", "subsector_rotation.js"):
        assert tok not in html, f"{name} still ships {tok} — not a stub"
    assert len(html) < 4000, f"rendered {name} is {len(html)} chars — not a stub"


# ---------------------------------------------------- merged template skeleton

def test_merged_template_sections_in_order() -> None:
    """The four-section spine, top to bottom.

    Order is load-bearing, not decorative: the persistent rail's buttons are authored
    in this order, and the stubs' fallback anchors (#si-explore / #si-movement) assume
    MOVEMENT precedes EXPLORE.

    The V1 horizontal anchor rail (#si-rail) that used to head this spine was retired
    when the page adopted the US workspace shell — a sticky strip of jump links over a
    12,000px document is a table of contents, not navigation. `<nav class="si-side">`
    replaced it and heads the spine now; the shell contract itself is pinned in
    tests/test_china_si_workspace_shell.py.
    """
    s = _read(TPL / MERGED)
    spine = ['<nav class="si-side"', 'id="actnow-section"', 'id="si-map"',
             'id="si-movement"', 'id="si-explore"']
    seen = []
    for anchor in spine:
        i = s.find(anchor)
        assert i != -1, f"merged page lost {anchor}"
        seen.append(i)
    assert seen == sorted(seen), (
        "section skeleton reordered — the rail's button order and the stub fallback "
        f"anchors assume {' < '.join(spine)}"
    )


def test_merged_template_carries_every_transplanted_organ() -> None:
    """Nothing silently lost (masterplan §0 gate 7)."""
    s = _read(TPL / MERGED)
    for organ in ('id="theme-context-hero"',   # rotation state in plain words
                  'id="sc-board"', 'id="board"', 'id="grader"',   # gated layer
                  'id="sc-cyclemap"',                              # cycle map
                  'id="rc-events-cn"',                             # rotation events rail
                  'id="rotation-app"',                             # whole-market rotation
                  '_baskets_desk',                                 # theme desk include
                  'id="entry-radar"',
                  '_forming_narratives',
                  'id="table-section"', 'id="chart-section"', 'id="categories"',
                  'id="reversal-sleeve-card"',
                  'id="semis-chip"'):
        assert organ in s, f"merged page lost {organ}"


def test_merged_page_keeps_the_macro_desk_opt_in() -> None:
    s = _read(TPL / MERGED)
    assert '<body class="macro-desk page-sector-central">' in s, (
        "the merged page still declares page-sector-central — macro-desk.css scopes "
        "the scc-cycle/cyc-stage rules to exactly that variant "
        "(tests/test_macro_desk_surface.py roster)"
    )


# ------------------------------------------------------- payload externalized

def test_payload_externalized_not_embedded() -> None:
    """Gate 5: the 774KB inline BASKETS+CHART blobs are fetched, not inlined."""
    s = _read(TPL / MERGED)
    assert "baskets_json" not in s, "inline BASKETS embed came back"
    assert "chart_json" not in s, "inline CHART embed came back"
    assert "__csiInitPage" in s, "payload boot entry point missing"
    assert "chinabasketdata/baskets.json" in s, "payload fetch missing"


@pytest.mark.parametrize("name,anchor", STUBS, ids=lambda v: str(v).split(".")[0])
def test_stub_carries_no_payload(name: str, anchor: str) -> None:
    assert "baskets_json" not in _read(TPL / name)


def test_stub_builder_renders_contextless() -> None:
    """build_baskets_china.py renders the stub with no payload context.

    The #2886 double render is gone with the inline embed: the shell is rendered
    ONCE and the authoritative baskets.json write IS the delivery contract.
    """
    src = _read(ROOT / "scripts" / "build_baskets_china.py")
    assert 'env.get_template("baskets_china.html.j2").render()' in src, (
        "the stub render must stay contextless — a payload argument here means the "
        "inline embed is creeping back"
    )
    assert "_render_page(_bj2_render)" not in src, (
        "the post-organ RE-RENDER is back; externalization replaced it with the "
        "post-organ authoritative JSON write (masterplan §0 gate 5)"
    )


# ------------------------------------------------------------- hash contract

def test_merged_page_resolves_both_inbound_hash_families() -> None:
    """Both handlers the stubs forward to must exist on the receiving side.

    The stubs forward the hash unconditionally; if the merged page stopped
    handling it, every forwarded deep link would land and do nothing — with the
    stub in the way, nobody would ever see the old page fail.
    """
    s = _read(TPL / MERGED)
    assert "location.hash.startsWith('#b-')" in s, "#b-<id> basket deep link unhandled"
    assert "openBasket(" in s
    assert "location.hash.startsWith('#theme-')" in s, "#theme-<id> deep link unhandled"
    assert "openTheme(" in s


def test_merged_page_declares_its_own_rotation_pagehref() -> None:
    """SR_CFG.pageHref drives the rotation renderer's self-links."""
    s = _read(TPL / MERGED)
    assert "pageHref:'sector_central_china.html'" in s, (
        "rotation self-links still point at the absorbed page"
    )
    assert "marketdata/subsector_rotation_china.json" in s
    assert "detailDir:'rotation_china/'" in s


# --------------------------------------------------------- THS survival fork

def test_factorwatch_fork_keeps_the_inline_payload() -> None:
    """The THS browser is a BYTE-IDENTICAL fork of the pre-merge template.

    baskets_china_ths.html is a 3.5MB standalone page rendered lite=True from this
    fork (masterplan §4 W2). It is OUT OF SCOPE for the merge, so it keeps the
    inline embed the merged page shed — externalizing it would point it at a JSON
    describing the CURATED baskets, not the 同花顺 concept boards.
    """
    s = _read(TPL / "baskets_china_factorwatch.html.j2")
    assert "const BASKETS = {{ baskets_json|safe }};" in s, (
        "the THS fork lost its inline payload — it has no JSON to fetch"
    )
    assert "const CHART   = {{ chart_json|safe }};" in s
    assert "{% if lite %}" in s and "{% if not lite %}" in s, "lite branches gone"
    assert "openTheme" in s


def test_ths_builder_renders_the_fork_not_the_stub() -> None:
    src = _read(ROOT / "scripts" / "build_baskets_china_ths.py")
    assert 'get_template("baskets_china_factorwatch.html.j2")' in src, (
        "the THS builder must render its own fork; baskets_china.html.j2 is a stub "
        "and would ship a 3.5MB page as a redirect"
    )
    assert "lite=True" in src


# ------------------------------------------------------------------ nav

def test_china_nav_collapsed_to_the_merged_page() -> None:
    """Gate 6: the 5-entry China Sector Central flyout collapses to flat rows."""
    s = _read(TPL / "_navlinks.html.j2")
    assert 'href="{{ NP }}sector_central_china.html"' in s
    assert 'href="{{ NP }}baskets_china.html"' not in s, (
        "absorbed page still has a China nav entry"
    )
    assert 'href="{{ NP }}subsector_rotation_china.html"' not in s, (
        "absorbed page still has a China nav entry"
    )
    # the two survivors keep their rows
    assert 'href="{{ NP }}subsectors_china.html"' in s
    assert 'href="{{ NP }}china_heatmap.html"' in s
    assert "China Sector Intelligence consolidation" in s, (
        "the collapse must stay documented in the partial — the next nav editor "
        "has no other way to know these rows were merged, not dropped"
    )


# --------------------------------------------------------- ZH vocabulary

@pytest.mark.parametrize("name", [MERGED, "_navlinks.html.j2"])
def test_one_zh_term_for_subsector(name: str) -> None:
    """Gate 3: 子行业 is the house term; the 细分行业 synonym does not survive."""
    assert "细分行业" not in _read(TPL / name), (
        f"{name} reintroduces the 细分行业 synonym — the nav says 子行业 and gate 3 "
        "allows exactly one ZH term for 'subsector'"
    )


# ------------------------------------------------- US siblings left untouched

def test_us_sector_intelligence_page_untouched() -> None:
    """Inverse guard: this program is China-only (masterplan scope line)."""
    s = _read(TPL / "sector_central.html.j2")
    assert 'id="actnow-section"' in s
    assert "__siInitPage" in s, "the US page must keep its OWN boot entry point"
    assert "__csiInitPage" not in s, "China's boot leaked onto the US page"


def test_us_baskets_stays_the_us_stub() -> None:
    s = _read(TPL / "baskets.html.j2")
    assert 'http-equiv="refresh"' in s, "US baskets stub was un-stubbed"
    assert 'content="0;url=sector_central.html#actnow-section"' in s, (
        "US stub retargeted at the China page"
    )


# ------------------------------------------------------ donor style scoping

def test_donor_card_styles_are_scoped_not_bare() -> None:
    """The absorbed baskets page's `.card` rules must not restyle the whole page.

    sector_central_china already had its own `.card` (the conviction-board rows);
    the donor brought category cards that live under `.cards`. Two bare `.card {`
    blocks in one document is the cascade collision this merge had to avoid, and
    it is invisible in a diff — the second block simply wins.
    """
    s = _read(TPL / MERGED)
    assert ".cards .card" in s, "donor card rules lost their .cards scope"
    bare = re.findall(r"^[ \t]*\.card\s*\{", s, re.M)
    assert len(bare) == 1, (
        f"{len(bare)} bare `.card {{` blocks in the merged template — the donor's "
        "card rules must be scoped under `.cards`, not merged into the base rule"
    )
