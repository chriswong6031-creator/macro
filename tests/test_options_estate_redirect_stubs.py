"""OIP W1.6-B — the four retired options pages are redirect stubs.

Replaces tests/test_flow_leaders_render_markers.py, which pinned the RENDERED
Flow Leaders board (dot ladder, plain-word leg copy, per-tier banned-vocabulary
sweeps).  That page no longer exists: `templates/flow_leaders.html.j2` is now a
stub and the board it used to describe lives inside the Options workspace, where
`tests/test_build_options_command.py` owns the same sweeps against
`templates/options.html.j2`.  Keeping the old file would have pinned a template
whose body was deleted — a test that passes because it is asking about nothing.

What this pins instead, for ALL FOUR stubs at once (research/options_estate/
ONE_DOOR_RULING_AND_SPEC.md §3):

  * the `<meta http-equiv="refresh">` target is the workspace + the RIGHT mode
    hash — the no-JS path, and the only one a crawler follows;
  * `location.replace()` is EXECUTED (node) and lands on the same URL — a grep
    could not tell the gex stub's computed destination from a string literal,
    which is the whole point of that stub;
  * the gex hash mapping itself: `#NVDA` → `options.html?t=NVDA#ticker`, a
    legacy mode word (`#flow`) → the bare `options.html#ticker`;
  * `noindex,follow` — the pages must leave the index while still passing their
    link equity to the workspace;
  * bilingual fallback copy in both languages, for the reader whose JS never
    runs and whose meta-refresh is disabled;
  * zero shared-asset loads — a stub that pulled theme.css/theme.js would make
    a redirect cost a full page's assets.

Run: python -m pytest tests/test_options_estate_redirect_stubs.py -q
"""
from __future__ import annotations

import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

import pytest
from jinja2 import Environment, FileSystemLoader

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

# (template, mode hash, EN mode word, ZH mode word, the builder's own autoescape)
#
# `autoescape` is carried per row rather than fixed, because the four builders
# genuinely differ (build_gex_board/build_options_screener render with
# autoescape=True, build_flow_desk/build_flow_leaders with False) and a stub is
# only proven safe under the setting it actually ships with.
STUBS = [
    ("gex.html.j2", "ticker", "Ticker", "个股", True),
    ("options_screener.html.j2", "scanner", "Scanner", "筛选", True),
    ("flow_desk.html.j2", "flow", "Flow", "资金流", False),
    ("flow_leaders.html.j2", "leaders", "Leaders", "领头股", False),
]
IDS = [s[0] for s in STUBS]

_needs_node = pytest.mark.skipif(shutil.which("node") is None, reason="node not on PATH")


def _render(template: str, autoescape: bool) -> str:
    env = Environment(loader=FileSystemLoader(str(ROOT / "templates")), autoescape=autoescape)
    return env.get_template(template).render()


def _script_body(rendered: str) -> str:
    m = re.search(r"<script>(.*?)</script>", rendered, re.S)
    assert m, "stub carries no inline <script> — the JS redirect path is missing"
    return m.group(1)


def _drive(rendered: str, hash_: str = "") -> dict:
    """Execute the stub's own script under a recording `location` stub.

    The gex stub COMPUTES its destination from location.hash, so a source grep
    reads the fallback literal and calls it the answer. Running the real script
    is the only check that can see the mapping.
    """
    harness = (
        "var __calls = [];\n"
        "var __anchor = { href: null };\n"
        "var __meta = { content: null, setAttribute: function (k, v) { if (k === 'content') this.content = v; } };\n"
        f"var location = {{ hash: {json.dumps(hash_)}, replace: function (u) {{ __calls.push(u); }} }};\n"
        "var document = { getElementById: function (id) { return id === 'go' ? __anchor : null; },\n"
        "                 querySelector: function (sel) { return /meta/.test(sel) ? __meta : null; } };\n"
        + _script_body(rendered)
        + "\nprocess.stdout.write(JSON.stringify({ calls: __calls, anchorHref: __anchor.href, metaContent: __meta.content }));\n"
    )
    res = subprocess.run(["node", "-e", harness], capture_output=True, text=True, timeout=30)
    assert res.returncode == 0, f"node failed:\nSTDERR:\n{res.stderr}\nSTDOUT:\n{res.stdout}"
    return json.loads(res.stdout)


@pytest.fixture(scope="module")
def rendered() -> dict:
    return {t: _render(t, ae) for t, _m, _e, _z, ae in STUBS}


# ─────────────────────────────────────────────────────────────────────────────
# The no-JS path — what a crawler and a scripting-disabled reader follow
# ─────────────────────────────────────────────────────────────────────────────
@pytest.mark.parametrize("template,mode,_en,_zh,_ae", STUBS, ids=IDS)
def test_meta_refresh_targets_the_right_workspace_mode(rendered, template, mode, _en, _zh, _ae):
    html = rendered[template]
    m = re.search(r'<meta http-equiv="refresh" content="0;url=([^"]+)">', html)
    assert m, f"{template}: no meta-refresh — a no-JS reader lands on a dead end"
    assert m.group(1) == f"options.html#{mode}", (
        f"{template}: meta-refresh points at {m.group(1)!r}, expected options.html#{mode}"
    )


@pytest.mark.parametrize("template,mode,_en,_zh,_ae", STUBS, ids=IDS)
def test_stub_is_noindex_follow(rendered, template, mode, _en, _zh, _ae):
    """`follow`, not `nofollow`: the stub must leave the index while still
    passing its accumulated link equity through to the workspace."""
    assert '<meta name="robots" content="noindex,follow">' in rendered[template], (
        f"{template}: missing the noindex,follow robots directive"
    )


@pytest.mark.parametrize("template,mode,_en,_zh,_ae", STUBS, ids=IDS)
def test_canonical_points_at_the_workspace(rendered, template, mode, _en, _zh, _ae):
    assert '<link rel="canonical" href="https://www.mastermind-x.com/options.html">' in rendered[template], (
        f"{template}: canonical must name the workspace, not the retired page"
    )


# ─────────────────────────────────────────────────────────────────────────────
# The JS path — EXECUTED, never grepped
# ─────────────────────────────────────────────────────────────────────────────
@_needs_node
@pytest.mark.parametrize("template,mode,_en,_zh,_ae", STUBS, ids=IDS)
def test_location_replace_lands_on_the_meta_refresh_target(rendered, template, mode, _en, _zh, _ae):
    """The two redirect paths must agree. They are written independently in the
    markup, so nothing but this stops one being edited without the other."""
    out = _drive(rendered[template])
    assert out["calls"] == [f"options.html#{mode}"], (
        f"{template}: location.replace() called with {out['calls']!r}, "
        f"expected exactly ['options.html#{mode}']"
    )


@_needs_node
@pytest.mark.parametrize("hash_,expect_symbol", [
    ("#NVDA", "NVDA"),
    ("#nvda", "NVDA"),        # normalised to upper case
    ("#BRK.B", "BRK.B"),      # dots are legal in the symbol charset
    ("#SPY", "SPY"),
])
def test_gex_stub_carries_a_legacy_symbol_hash_into_the_workspace(rendered, hash_, expect_symbol):
    """gex.html's deep links were hash-based (`gex.html#NVDA`). The workspace's
    contract is `?t=SYM#ticker`, so the symbol has to be MOVED across the two
    syntaxes — the one thing in these four stubs that is real logic."""
    out = _drive(rendered["gex.html.j2"], hash_)
    assert out["calls"] == [f"options.html?t={expect_symbol}#ticker"], (
        f"gex stub dropped the symbol from {hash_!r}: {out['calls']!r}"
    )
    assert out["anchorHref"] == f"options.html?t={expect_symbol}#ticker", (
        "the visible fallback link must carry the symbol too — it is what a "
        f"reader whose redirect was blocked actually clicks; got {out['anchorHref']!r}"
    )
    assert out["metaContent"] == f"0;url=options.html?t={expect_symbol}#ticker", (
        "the declarative meta-refresh must be rewritten onto the SAME "
        f"destination — the two redirect paths may never diverge; got {out['metaContent']!r}"
    )


@_needs_node
@pytest.mark.parametrize("hash_", ["", "#", "#brief", "#flow", "#scanner", "#ticker", "#leaders",
                                   "#LEADERS", "#not_a_symbol", "#waytoolongforasymbol"])
def test_gex_stub_falls_back_to_bare_ticker_mode_for_non_symbols(rendered, hash_):
    """A legacy MODE word must not be mistaken for a ticker — `gex.html#flow`
    would otherwise resolve to `?t=FLOW`, a lookup for a stock that does not
    exist. Same for anything outside the symbol charset or length."""
    out = _drive(rendered["gex.html.j2"], hash_)
    assert out["calls"] == ["options.html#ticker"], (
        f"gex stub treated {hash_!r} as a symbol: {out['calls']!r}"
    )


@_needs_node
def test_gex_symbol_branch_is_reachable_and_distinct(rendered):
    """Non-vacuity control for the two tests above: they only mean something if
    the symbol branch and the fallback branch produce DIFFERENT output. A stub
    that always emitted `options.html#ticker` would pass the fallback test for
    free."""
    sym = _drive(rendered["gex.html.j2"], "#NVDA")["calls"]
    bare = _drive(rendered["gex.html.j2"], "#flow")["calls"]
    assert sym != bare, "gex stub's symbol mapping is dead code — both branches agree"


# ─────────────────────────────────────────────────────────────────────────────
# What the reader sees while the redirect happens
# ─────────────────────────────────────────────────────────────────────────────
@pytest.mark.parametrize("template,mode,mode_en,mode_zh,_ae", STUBS, ids=IDS)
def test_fallback_copy_is_bilingual(rendered, template, mode, mode_en, mode_zh, _ae):
    """Both languages, and the mode named in each — a ZH reader must not be
    handed an English-only explanation of where their page went."""
    html = rendered[template]
    assert "This desk moved into the Options workspace" in html, f"{template}: EN heading missing"
    assert "本面板已并入期权工作台" in html, f"{template}: ZH sentence missing"
    assert f"「{mode_zh}」" in html, f"{template}: ZH copy does not name the {mode_zh} mode"
    assert mode_en in html, f"{template}: EN copy does not name the {mode_en} mode"
    assert "Open the workspace →" in html and "打开期权工作台 →" in html, (
        f"{template}: the manual fallback link is not bilingual"
    )


@pytest.mark.parametrize("template,mode,_en,_zh,_ae", STUBS, ids=IDS)
def test_visible_link_matches_the_redirect_target(rendered, template, mode, _en, _zh, _ae):
    """The clickable escape hatch and the automatic redirect must agree — this
    link is what a reader uses when both redirects are blocked."""
    assert f'href="options.html#{mode}"' in rendered[template], (
        f"{template}: no visible fallback link to options.html#{mode}"
    )


@pytest.mark.parametrize("template,mode,_en,_zh,_ae", STUBS, ids=IDS)
def test_stub_loads_no_shared_assets(rendered, template, mode, _en, _zh, _ae):
    """§3: "zero shared-asset loads". A stub exists to get out of the way in one
    paint; pulling theme.css/theme.js would make a redirect cost a full page's
    assets. (lib.pages.write_page adds the data-base shim at WRITE time — that
    is the build's, not the template's, and this reads the template's render.)"""
    html = rendered[template]
    assert 'rel="stylesheet"' not in html, f"{template}: stub pulls a stylesheet"
    assert "<script src=" not in html, f"{template}: stub pulls an external script"
    assert "_site_nav" not in html and 'class="site-nav"' not in html, (
        f"{template}: stub renders the site nav — it must be a bare interstitial"
    )


@pytest.mark.parametrize("template,mode,_en,_zh,_ae", STUBS, ids=IDS)
def test_stub_is_actually_a_stub(rendered, template, mode, _en, _zh, _ae):
    """Size control. Every one of these templates was a 38-60KB page; if a
    future edit reinstates any of that body, the pins above would still pass
    while the "redirect" quietly became a page again."""
    html = rendered[template]
    assert len(html) < 4000, f"{template}: rendered {len(html)} bytes — this is not a stub"
    assert "<html" in html and "</html>" in html, f"{template}: not a complete document"


def test_all_four_modes_are_distinct():
    """The mapping table itself: four pages, four different workspace modes. A
    copy-paste that pointed two stubs at the same mode would leave one legacy
    URL landing on the wrong view, and every per-stub test above would pass."""
    modes = [m for _t, m, _e, _z, _ae in STUBS]
    assert len(set(modes)) == len(modes), f"duplicate mode targets: {modes}"
    assert set(modes) == {"ticker", "scanner", "flow", "leaders"}
