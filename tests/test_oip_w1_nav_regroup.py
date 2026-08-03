"""OIP W1.6-B — the nav after One Door (research/options_estate/ONE_DOOR_RULING_AND_SPEC.md §3).

W1 gave options.html a front door and left gex.html beside it as "the instrument
bench". W1.6 retired that distinction: the workspace absorbed all four legacy
options pages, which are now redirect stubs, so the flyout carries ONE options
door plus the two neighbours that do a genuinely different job.

  Nav · United States
  ├── … Daily Movers
  ├── Intraday Flow Tracker        ← moved OUT of the options flyout: it is a
  │                                  live session board, not an options page
  └── Options & Market Structure ▸
      ├── Options — the workspace  options.html   Brief · Flow · Scanner · Ticker · Leaders
      ├── Dark Pool Desk           darkpool.html
      └── Market Structure         market_structure.html

Both header families are checked SEPARATELY and neither is allowed to stand in
for the other: `_navlinks.html.j2` is the server-rendered inventory, and
`nav_market.js` is a hand-maintained JS copy that REPLACES the whole US menu for
a JS-enabled user. Before W1's B1 fix the two disagreed and the regroup reached
nobody — `grep -c "'options.html'" templates/nav_market.js` was 0 while every
template assertion passed.

templates/chat.html carries a THIRD copy, but it is generated: it is spliced from
`_site_nav.html.j2` by scripts/sync_chat_nav.py and guarded by
tests/test_chat_nav_sync.py, so it needs no pins here — only a `--fix` run
whenever this file's partial changes.

Run: python -m pytest tests/test_oip_w1_nav_regroup.py -q
"""
from __future__ import annotations

import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

NAV = (ROOT / "templates" / "_navlinks.html.j2").read_text(encoding="utf-8")

# The three rows the flyout is allowed to carry, in order.
FLYOUT_ROWS = ["options.html", "darkpool.html", "market_structure.html"]
# The four URLs the workspace absorbed. All four are still LIVE (as redirect
# stubs — tests/test_options_estate_redirect_stubs.py owns their shape); what
# they must no longer be is NAVIGATION destinations.
RETIRED_URLS = ["gex.html", "options_screener.html", "flow_desk.html", "flow_leaders.html"]


def _flyout() -> str:
    """The Options & Market Structure `nav-dd nav-sub` block only.

    Anchored on the trigger <a>'s literal href, NOT on the comment text above it
    — a prose phrase would also match the Daily Movers relocation comment
    earlier in the file and would capture Sector Central's block too.
    """
    block_start = NAV.rindex(
        '<div class="nav-dd nav-sub">',
        0, NAV.index('<a class="nav-sub-trig" href="{{ NP }}options.html"'),
    )
    end = NAV.index("leader_radar.html", block_start)
    return NAV[block_start:end]


def _united_states_menu() -> str:
    start = NAV.index('href="{{ NP }}macro.html"')
    end = NAV.index("</div>\n    <div class=\"nav-dd\">\n      <a class=\"nav-link\" href=\"{{ NP }}china.html\"")
    return NAV[start:end]


def _us_group_outside_the_flyout() -> str:
    """The United States group with the options flyout cut out of it, so "moved
    OUT of the flyout" can be asserted positively rather than by absence."""
    us, fly = _united_states_menu(), _flyout()
    assert fly in us, "the flyout is not inside the US group — slicing helpers drifted"
    return us.replace(fly, "\n<<<FLYOUT>>>\n")


# ─────────────────────────────────────────────────────────────────────────────
# One options door
# ─────────────────────────────────────────────────────────────────────────────
def test_flyout_carries_exactly_the_three_rows_in_order():
    rows = re.findall(r'<a href="\{\{ NP \}\}([^"]+)"', _flyout())
    assert rows == FLYOUT_ROWS, (
        f"the One Door flyout must be exactly {FLYOUT_ROWS} in that order, got {rows}"
    )


def test_flyout_trigger_is_the_workspace():
    trig = re.search(r'<a class="nav-sub-trig" href="\{\{ NP \}\}([^"]+)"', _flyout())
    assert trig and trig.group(1) == "options.html", (
        f"the flyout trigger must be options.html, got {trig and trig.group(1)!r}"
    )


def test_group_label_and_trigger_description_are_the_pinned_copy():
    """§3 + §5 pinned copy, both languages. The label stopped saying "Flow"
    because Flow is now a MODE of the workspace, not a sibling page."""
    fly = _flyout()
    assert "t('Options & Market Structure', '期权与市场结构')" in fly, (
        "flyout group label is not the pinned EN/ZH pair"
    )
    assert "t('Workspace · dark pool · index regime', '工作台 · 暗池 · 指数结构')" in fly, (
        "flyout trigger description is not the pinned EN/ZH pair"
    )
    assert "Options & Flow" not in fly, "the retired 'Options & Flow' label is still here"


def test_workspace_row_names_all_five_modes():
    """Flow joined the mode list in W1.6-A — the row has to say so, or the one
    remaining door under-sells what it absorbed."""
    fly = _flyout()
    after_trigger = fly.index('href="{{ NP }}options.html"') + 1
    row = fly[fly.index('href="{{ NP }}options.html"', after_trigger):]
    row = row[: row.index("</a>")]
    for word in ("Daily Brief", "Flow", "Scanner", "Ticker", "Leaders"):
        assert word in row, f"workspace row does not name the {word} mode"
    for word in ("每日简报", "资金流", "筛选", "个股", "领头股"):
        assert word in row, f"workspace row's ZH copy does not name {word}"


@pytest.mark.parametrize("retired_url", RETIRED_URLS)
def test_retired_options_urls_are_no_longer_navigation_destinations(retired_url):
    """All four are redirect stubs now. Linking one from the menu would send a
    reader through a bounce to reach a page the menu could have named directly."""
    assert f'href="{{{{ NP }}}}{retired_url}"' not in NAV, (
        f"{retired_url} is a redirect stub — it must not be linked from navigation"
    )


def test_flyout_has_exactly_four_submenu_icon_spans():
    """trigger + options.html + darkpool + market_structure = 4, down from 6
    (W1) after gex.html was deleted and intraday_flow moved out."""
    found = _flyout().count('class="submenu-icon ')
    assert found == 4, f"expected 4 submenu-icon spans in the One Door flyout, found {found}"


# ─────────────────────────────────────────────────────────────────────────────
# The two neighbours keep their rows verbatim, guards included
# ─────────────────────────────────────────────────────────────────────────────
def test_darkpool_row_keeps_its_enable_guard_and_copy():
    fly = _flyout()
    assert "{% if darkpool_enabled is not defined or darkpool_enabled %}" in fly
    assert "t('Dark Pool Desk', '场外暗池台')" in fly
    assert "t('Off-exchange volume · short ratio · ATS venues', '场外成交量 · 融券比率 · ATS场所')" in fly


def test_market_structure_row_stays_unguarded_and_verbatim():
    fly = _flyout()
    assert 'href="{{ NP }}market_structure.html"' in fly
    assert "t('Market Structure', '市场结构')" in fly
    assert "t('GEX regime · machine flows · dispersion · weekly range', '做市商制度 · 机器资金 · 离散度 · 周度区间')" in fly


def test_no_new_enable_guards_were_invented_for_the_absorbed_pages():
    for flag in ("options_screener_enabled", "flow_desk_enabled", "flow_leaders_enabled"):
        assert flag not in NAV, f"{flag} must not appear in this partial"


# ─────────────────────────────────────────────────────────────────────────────
# Intraday Flow Tracker leaves the options flyout for the US group
# ─────────────────────────────────────────────────────────────────────────────
def test_intraday_flow_left_the_options_flyout():
    assert 'href="{{ NP }}intraday_flow.html"' not in _flyout(), (
        "Intraday Flow Tracker is a live session board, not an options page — "
        "it must not sit in the options flyout"
    )


def test_intraday_flow_sits_directly_after_daily_movers():
    us = _us_group_outside_the_flyout()
    assert 'href="{{ NP }}intraday_flow.html"' in us, (
        "intraday_flow.html must land in the United States group itself"
    )
    assert us.index('href="{{ NP }}movers.html"') < us.index('href="{{ NP }}intraday_flow.html"'), (
        "intraday_flow.html must follow Daily Movers"
    )
    assert us.index('href="{{ NP }}intraday_flow.html"') < us.index('href="{{ NP }}stage_analysis.html"'), (
        "intraday_flow.html must sit DIRECTLY after Daily Movers — before Stage Analysis"
    )


def test_intraday_flow_keeps_its_enable_guard_through_the_move():
    us = _us_group_outside_the_flyout()
    row_start = us.index("{% if intraday_flow_enabled is not defined or intraday_flow_enabled %}")
    row = us[row_start: us.index("{% endif %}", row_start)]
    assert 'href="{{ NP }}intraday_flow.html"' in row, (
        "the relocated row lost its enable guard — a disabled page would be linked"
    )


def test_intraday_flow_description_is_the_pinned_plain_word_copy():
    """§5: the RVOL/VWAP/K-7 jargon desc retires with the move. The page itself
    is untouched — only how the menu describes it."""
    us = _us_group_outside_the_flyout()
    row = us[us.index('href="{{ NP }}intraday_flow.html"'):]
    row = row[: row.index("</a>")]
    assert ("t('Live session board — volume, tape and stance lanes · ≈15-min delayed', "
            "'盘中实时看板 — 量能、盘面与操作分级 · 约延迟15分钟')") in row, (
        "intraday_flow row is not carrying the pinned EN/ZH description"
    )
    for jargon in ("RVOL", "VWAP", "K/7"):
        assert jargon not in row, f"retired jargon {jargon!r} is still in the intraday row"


def test_intraday_flow_appears_exactly_once_in_this_partial():
    assert NAV.count('href="{{ NP }}intraday_flow.html"') == 1


def test_movers_stays_where_w1_put_it():
    us = _us_group_outside_the_flyout()
    assert NAV.count('href="{{ NP }}movers.html"') == 1
    assert us.index('href="{{ NP }}us_stocks.html"') < us.index('href="{{ NP }}movers.html"')


# ─────────────────────────────────────────────────────────────────────────────
# The JS mirror — a separate, hand-maintained copy of the same destinations
# ─────────────────────────────────────────────────────────────────────────────
NAV_JS = (ROOT / "templates" / "nav_market.js").read_text(encoding="utf-8")


def _us_market_menu_js() -> str:
    start = NAV_JS.index("us: {")
    end = NAV_JS.index("cn: {", start)
    return NAV_JS[start:end]


def _us_market_structure_section_js() -> str:
    us = _us_market_menu_js()
    start = us.index("['Market structure', [")
    end = us.index("]]", start) + len("]]")
    return us[start:end]


def _us_market_overview_section_js() -> str:
    us = _us_market_menu_js()
    start = us.index("['Market overview', [")
    end = us.index("]]", start) + len("]]")
    return us[start:end]


def test_js_market_structure_section_carries_the_same_three_rows_in_order():
    sec = _us_market_structure_section_js()
    hrefs = [h for h in re.findall(r"'([a-z_]+\.html)'", sec)]
    # darkpool.html appears twice: once as the destination, once as its gate arg.
    ordered = [h for i, h in enumerate(hrefs) if h not in hrefs[:i]]
    assert ordered == FLYOUT_ROWS, (
        f"nav_market.js's 'Market structure' section must mirror {FLYOUT_ROWS}, got {ordered}"
    )


def test_js_workspace_row_names_all_five_modes():
    sec = _us_market_structure_section_js()
    assert "Daily Brief · Flow · Scanner · Ticker · Leaders" in sec
    assert "每日简报 · 资金流 · 筛选 · 个股 · 领头股" in sec


@pytest.mark.parametrize("retired_url", RETIRED_URLS)
def test_js_menu_drops_the_retired_options_urls(retired_url):
    assert f"'{retired_url}'" not in _us_market_menu_js(), (
        f"{retired_url} is a redirect stub — nav_market.js must not link it either"
    )


def test_js_darkpool_keeps_its_conditional_gate():
    """The row is guarded server-side, so the JS mirror must not hardcode it as
    always-on. The 8th tuple element names the href hrefPresent() requires in
    the source DOM before the row renders."""
    sec = _us_market_structure_section_js()
    assert sec.count("'darkpool.html'") >= 2, "darkpool.html row must carry a gate"


def test_js_intraday_flow_moved_to_market_overview_after_movers():
    overview = _us_market_overview_section_js()
    assert "'intraday_flow.html'" in overview, (
        "intraday_flow.html must move into the JS 'Market overview' section too"
    )
    assert overview.index("'movers.html'") < overview.index("'intraday_flow.html'"), (
        "intraday_flow.html must follow Daily Movers, mirroring _navlinks.html.j2"
    )
    assert "'intraday_flow.html'" not in _us_market_structure_section_js(), (
        "intraday_flow.html must LEAVE the options section, not be duplicated"
    )
    assert overview.count("'intraday_flow.html'") >= 2, (
        "the relocated row must keep its href gate"
    )


def test_js_intraday_flow_description_is_the_pinned_plain_word_copy():
    overview = _us_market_overview_section_js()
    assert "Live session board — volume, tape and stance lanes · ≈15-min delayed" in overview
    assert "盘中实时看板 — 量能、盘面与操作分级 · 约延迟15分钟" in overview
    for jargon in ("RVOL", "VWAP", "K/7"):
        assert jargon not in overview, f"retired jargon {jargon!r} is still in the JS intraday row"


# ─────────────────────────────────────────────────────────────────────────────
# …and the JS mirror is checked as RENDERED OUTPUT, not as source text
# ─────────────────────────────────────────────────────────────────────────────
_HAS_NODE = shutil.which("node") is not None
needs_node = pytest.mark.skipif(not _HAS_NODE, reason="node not on PATH")


def _extract_nav_market_iife_body() -> str:
    start = NAV_JS.index("(function () {") + len("(function () {")
    end = NAV_JS.rindex("})();")
    return NAV_JS[start:end]


@needs_node
def test_js_rendered_us_menu_matches_the_one_door_shape():
    """Runs the REAL marketMarkup('us', …) — a source-text pin cannot tell a
    destination that RENDERS from one that was edited into a dead branch."""
    stub = """
    var document = { querySelector: function () { return null; }, addEventListener: function () {} };
    var window = {};
    var location = { hash: '' };
    var history = { replaceState: function () {} };
    """
    driver = stub + _extract_nav_market_iife_body() + """
    function fakeScope(hrefs) {
      return { querySelector: function (sel) {
        var m = /a\\[href\\$="([^"]+)"\\]/.exec(sel);
        return (m && hrefs.indexOf(m[1]) !== -1) ? {} : null;
      } };
    }

    var full = marketMarkup('us', '', fakeScope(['intraday_flow.html', 'darkpool.html']));
    var noIntraday = marketMarkup('us', '', fakeScope(['darkpool.html']));
    var noDarkpool = marketMarkup('us', '', fakeScope(['intraday_flow.html']));
    process.stdout.write(JSON.stringify({ full: full, noIntraday: noIntraday, noDarkpool: noDarkpool }));
    """
    res = subprocess.run(["node", "-e", driver], capture_output=True, text=True, timeout=30)
    assert res.returncode == 0, f"node failed:\nSTDERR:\n{res.stderr}\nSTDOUT:\n{res.stdout}"
    out = json.loads(res.stdout)

    full = out["full"]
    for href in ("options.html", "movers.html", "market_structure.html",
                 "intraday_flow.html", "darkpool.html"):
        assert f'href="{href}"' in full, f"the rendered US menu lost {href}"
    for retired in RETIRED_URLS:
        assert f'href="{retired}"' not in full, (
            f"the rendered US menu still links the retired {retired}"
        )

    # the gates actually gate, in both directions — an absent conditional must
    # hide its own row and nothing else.
    assert 'href="intraday_flow.html"' not in out["noIntraday"]
    assert 'href="darkpool.html"' in out["noIntraday"]
    assert 'href="darkpool.html"' not in out["noDarkpool"]
    assert 'href="intraday_flow.html"' in out["noDarkpool"]
    assert 'href="options.html"' in out["noIntraday"], (
        "an unrelated absent conditional must not hide the workspace row"
    )
