"""OIP W1 §1 — the nav front-door regroup (research/options_estate/W1_DESIGN_SPEC.md).

options.html was linked from NO navigation before this wave; the flyout trigger
was gex.html. This pins the corrected shape:
  * the Options & Flow flyout's trigger AND first inner row both point at
    options.html (mirroring the existing Sector Central / China Research
    trigger-duplicated-as-first-row pattern);
  * gex.html stays IN the flyout (a regular row now, not the trigger) — OIP's
    revision of OEU's original plan, because gex.html is the instrument bench,
    a genuinely different job from a reading surface;
  * options_screener.html / flow_desk.html / flow_leaders.html LEAVE the
    flyout — but their URLs, and the ribbon banner naming their replacement,
    stay live forever (house law: no page kills, no redirects);
  * Daily Movers relocates from the flyout into the United States group.

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


def _flyout() -> str:
    """The Options & Flow nav-dd nav-sub block only.

    Anchored on the trigger <a>'s literal href, NOT the "Options & Flow flyout"
    comment text — that phrase ALSO appears in the Daily Movers relocation
    comment ("relocates here from the Options & Flow flyout"), which sits
    earlier in the file and would otherwise capture Sector Central's block too.
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


# ─────────────────────────────────────────────────────────────────────────────
# The flyout trigger + first row both resolve to the workspace
# ─────────────────────────────────────────────────────────────────────────────
def test_flyout_trigger_points_at_the_workspace():
    fly = _flyout()
    trig = re.search(r'<a class="nav-sub-trig" href="\{\{ NP \}\}([^"]+)"', fly)
    assert trig, "flyout trigger <a> not found"
    assert trig.group(1) == "options.html", (
        f"OIP W1: the flyout trigger must be options.html (the workspace), got {trig.group(1)!r}"
    )


def test_workspace_is_also_the_flyouts_first_inner_row():
    fly = _flyout()
    rows = re.findall(r'<a href="\{\{ NP \}\}([^"]+)"', fly)
    assert rows, "no inner flyout rows found"
    assert rows[0] == "options.html", (
        "options.html must be the flyout's first inner row too — the trigger-"
        f"duplicated-as-first-row pattern Sector Central/China Research already use; got {rows}"
    )


def test_workspace_row_names_all_four_modes():
    fly = _flyout()
    # the FIRST options.html href is the trigger itself; the inner row (the one
    # carrying the mode list) is the second occurrence.
    after_trigger = fly.index('href="{{ NP }}options.html"') + 1
    row = fly[fly.index('href="{{ NP }}options.html"', after_trigger):]
    row = row[: row.index("</a>")]
    assert "Daily Brief" in row and "Scanner" in row and "Ticker" in row and "Leaders" in row
    assert "每日简报" in row and "筛选" in row and "个股" in row and "领头股" in row


# ─────────────────────────────────────────────────────────────────────────────
# gex.html stays IN the flyout — a regular row, not the trigger — OIP's revision
# ─────────────────────────────────────────────────────────────────────────────
def test_gex_desk_stays_in_the_flyout_as_a_regular_row():
    fly = _flyout()
    assert 'href="{{ NP }}gex.html"' in fly
    assert fly.index('href="{{ NP }}gex.html"') > fly.index('class="nav-sub-trig"'), (
        "gex.html must appear AFTER the trigger row, as a regular item — it is no "
        "longer the flyout's own trigger (OIP §4 revises OEU: gex.html is the "
        "instrument bench, a different job from the reading surfaces)"
    )
    # the freed submenu-icon-dashboard (options_screener's old icon) is reused
    # here, not a new icon class.
    row = fly[fly.index('href="{{ NP }}gex.html"'):]
    row = row[: row.index("</a>")]
    assert "submenu-icon-dashboard" in row


# ─────────────────────────────────────────────────────────────────────────────
# Three pages leave the flyout — but their URLs + banner stay live forever
# ─────────────────────────────────────────────────────────────────────────────
@pytest.mark.parametrize("legacy_url", ["options_screener.html", "flow_desk.html", "flow_leaders.html"])
def test_absorbed_pages_no_longer_appear_in_the_flyout(legacy_url):
    assert f'href="{{{{ NP }}}}{legacy_url}"' not in _flyout(), (
        f"{legacy_url} must leave the Options & Flow flyout (OIP W1 §1.1)"
    )


@pytest.mark.parametrize(("legacy_template", "banner_mode"), [
    ("options_screener.html.j2", "scanner"),
    ("flow_desk.html.j2", "brief"),
    ("flow_leaders.html.j2", "leaders"),
])
def test_absorbed_pages_still_carry_the_workspace_banner(legacy_template, banner_mode):
    """House law: no page kills, no redirects. Each leaving page must still
    include the ribbon that points a visitor at its replacement mode."""
    src = (ROOT / "templates" / legacy_template).read_text(encoding="utf-8")
    assert '{% include "_options_workspace_banner.html.j2" %}' in src
    assert f"oew_mode = '{banner_mode}'" in src


@pytest.mark.parametrize("legacy_site_page", [
    "options_screener.html", "flow_desk.html", "flow_leaders.html",
])
def test_legacy_pages_still_exist_as_built_files(legacy_site_page):
    """Old URLs keep working (masterplan §0 gate #13) — the file itself, not
    just the template, must still be a real, reachable artifact."""
    p = ROOT / "site" / legacy_site_page
    if not p.exists():
        pytest.skip(f"{legacy_site_page} not built in this checkout")
    assert p.stat().st_size > 0


def test_screener_enabled_guard_variables_untouched():
    """§1.2's own note: do not touch the *_enabled guard variables anywhere else
    — the pages still render, they are simply no longer linked from this menu."""
    assert "options_screener_enabled" not in NAV, (
        "options_screener_enabled must not reappear as a NEW guard in this file — "
        "the page left the flyout unconditionally, it was never guarded here before either"
    )
    assert "flow_desk_enabled" not in NAV
    assert "flow_leaders_enabled" not in NAV


# ─────────────────────────────────────────────────────────────────────────────
# The two rows that DO stay guarded keep their guards
# ─────────────────────────────────────────────────────────────────────────────
def test_intraday_flow_and_darkpool_keep_their_enable_guards():
    fly = _flyout()
    assert "{% if intraday_flow_enabled is not defined or intraday_flow_enabled %}" in fly
    assert "{% if darkpool_enabled is not defined or darkpool_enabled %}" in fly


def test_market_structure_stays_unguarded_in_the_flyout():
    fly = _flyout()
    assert 'href="{{ NP }}market_structure.html"' in fly


def test_flyout_has_exactly_six_submenu_icon_spans():
    """trigger + options.html + gex.html + intraday_flow + darkpool +
    market_structure = 6, down from 9 before this wave (§1.2's own diff)."""
    fly = _flyout()
    assert fly.count('class="submenu-icon ') == 6, (
        f"expected 6 submenu-icon spans in the regrouped flyout, found "
        f"{fly.count('class=\"submenu-icon ')}"
    )


# ─────────────────────────────────────────────────────────────────────────────
# Daily Movers relocates to the United States group
# ─────────────────────────────────────────────────────────────────────────────
def test_movers_no_longer_in_the_options_flyout():
    assert 'href="{{ NP }}movers.html"' not in _flyout()


def test_movers_relocated_into_united_states_beside_the_stock_dashboard():
    us = _united_states_menu()
    assert 'href="{{ NP }}movers.html"' in us, "movers.html must land in the United States group"
    assert us.index('href="{{ NP }}us_stocks.html"') < us.index('href="{{ NP }}movers.html"'), (
        "movers.html must sit immediately after us_stocks.html (beside the Stock "
        "Dashboard — stock-level content, not deep in the menu)"
    )
    assert us.index('href="{{ NP }}movers.html"') < us.index('href="{{ NP }}stage_analysis.html"'), (
        "movers.html must land BEFORE stage_analysis.html"
    )


def test_movers_copy_is_verbatim_unchanged_by_the_relocation():
    us = _united_states_menu()
    row = us[us.index('href="{{ NP }}movers.html"'):]
    row = row[: row.index("</a>")]
    assert "submenu-icon-stocks" in row
    assert "Daily Movers" in row and "每日异动" in row
    assert "biggest gainers &amp; losers today" in row or "biggest gainers & losers today" in row


def test_movers_appears_exactly_once_sitewide_in_this_partial():
    assert NAV.count('href="{{ NP }}movers.html"') == 1


# ─────────────────────────────────────────────────────────────────────────────
# B1 (adversarial review, binding ruling): the regroup above never reached a
# JS-enabled user. templates/nav_market.js's enhanceMarketMenus() replaces the
# ENTIRE United States .nav-dd-menu — including the Options & Flow flyout the
# tests above pin — via marketMarkup('us', ...), a SEPARATE, hand-maintained
# copy of the nav's destinations. Before this fix: `grep -c "'options.html'"
# templates/nav_market.js` -> 0. These tests read the SHIPPED JS source (never
# templates/_navlinks.html.j2 — the two are intentionally checked separately
# so neither one going stale hides behind the other staying green), plus one
# end-to-end run of the real marketMarkup() function so the assertion is about
# rendered output, not just source text containing the right words.
# ─────────────────────────────────────────────────────────────────────────────
NAV_JS = (ROOT / "templates" / "nav_market.js").read_text(encoding="utf-8")


def _us_market_menu_js() -> str:
    """The nav_market.js MARKET_MENU.us entry, sliced to the next top-level
    market key so a China/HK/Canada row can never leak into a "US menu" check."""
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


def test_js_menu_market_structure_leads_with_the_options_workspace():
    sec = _us_market_structure_section_js()
    assert "'options.html'" in sec, (
        "B1: templates/nav_market.js's US 'Market structure' section must "
        "link options.html — this is the exact gap that let the regroup ship "
        "without reaching a JS-enabled user"
    )
    assert sec.index("'options.html'") < sec.index("'gex.html'"), (
        "options.html (the workspace) must lead the section, ahead of gex.html"
    )


def test_js_menu_gex_desk_stays_as_the_instrument_bench_row():
    sec = _us_market_structure_section_js()
    assert "'gex.html'" in sec
    assert "Options Desk" in sec


def test_js_menu_market_structure_page_present_unguarded():
    assert "'market_structure.html'" in _us_market_structure_section_js()


@pytest.mark.parametrize("legacy_url", ["options_screener.html", "flow_desk.html", "flow_leaders.html"])
def test_js_menu_absorbed_pages_leave_market_structure_too(legacy_url):
    sec = _us_market_structure_section_js()
    assert f"'{legacy_url}'" not in sec, (
        f"{legacy_url} must leave nav_market.js's US 'Market structure' section "
        "the same way it already left _navlinks.html.j2's flyout (§1.1)"
    )


def test_js_menu_intraday_flow_and_darkpool_keep_a_conditional_gate():
    """Both rows are guarded server-side ({% if intraday_flow_enabled/
    darkpool_enabled is not defined or ... %}) — the JS mirror must not
    hardcode them as always-on, or a page where the flag is false would show
    a link the template itself omits. The 8th tuple element names the href
    hrefPresent() requires in the source DOM before the row renders."""
    sec = _us_market_structure_section_js()
    assert "'intraday_flow.html'" in sec and "'darkpool.html'" in sec
    # each conditional row's href appears a SECOND time as its own gate arg
    assert sec.count("'intraday_flow.html'") >= 2, "intraday_flow.html row must carry a gate"
    assert sec.count("'darkpool.html'") >= 2, "darkpool.html row must carry a gate"


def test_js_menu_movers_relocated_beside_stock_dashboard():
    sec = _us_market_overview_section_js()
    assert "'movers.html'" in sec, "Daily Movers must land in the JS mega-menu too"
    assert sec.index("'us_stocks.html'") < sec.index("'movers.html'"), (
        "movers.html must sit after us_stocks.html, matching §1.3's placement"
    )


def test_js_menu_movers_not_duplicated_in_market_structure():
    assert "'movers.html'" not in _us_market_structure_section_js()


_HAS_NODE = shutil.which("node") is not None
needs_node = pytest.mark.skipif(not _HAS_NODE, reason="node not on PATH")


def _extract_nav_market_iife_body() -> str:
    """nav_market.js's whole IIFE body, minus the `(function () {` / `})();`
    wrapper — its var declarations (MARKET_MENU, marketMarkup, hrefPresent)
    become directly callable top-level statements in a bare node -e script,
    the same extraction idiom test_build_options_command.py already uses for
    options.html.j2's own inline <script>."""
    start = NAV_JS.index("(function () {") + len("(function () {")
    end = NAV_JS.rindex("})();")
    return NAV_JS[start:end]


@needs_node
def test_js_menu_end_to_end_marketmarkup_output_contains_options_html():
    """Runs the REAL marketMarkup('us', ...) — not a source-text pin — and
    asserts its rendered output contains options.html, matching the shipped
    template's flyout. This is the direct answer to B1's own instruction:
    'add a test that asserts the JS-rendered menu contains options.html.'"""
    # Minimal stub: MARKET_MENU is built EAGERLY as the IIFE body executes
    # (intl's rail calls intlCountryHref() inline while constructing the
    # object literal), and boot() auto-runs at the bottom of the same body —
    # both need document/window/location/history to already exist, so the
    # stub must precede the extracted body, not follow it (the same ordering
    # test_build_options_command.py's _DOM_STUB + extracted-script uses).
    # document.querySelector returns null for the nav-links lookup, so
    # boot()'s own enhanceMarketMenus() call is never reached (harmless
    # no-op) — marketMarkup is exercised directly below instead, against a
    # controllable fake source scope.
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
    process.stdout.write(JSON.stringify({ full: full, noIntraday: noIntraday }));
    """
    res = subprocess.run(["node", "-e", driver], capture_output=True, text=True, timeout=30)
    assert res.returncode == 0, f"node failed:\nSTDERR:\n{res.stderr}\nSTDOUT:\n{res.stdout}"
    out = json.loads(res.stdout)

    full = out["full"]
    assert 'href="options.html"' in full, "the rendered US menu must contain options.html"
    assert 'href="gex.html"' in full
    assert 'href="movers.html"' in full
    assert 'href="market_structure.html"' in full
    assert 'href="intraday_flow.html"' in full
    assert 'href="darkpool.html"' in full
    assert 'href="options_screener.html"' not in full
    assert 'href="flow_desk.html"' not in full

    # the conditional gate actually gates: with intraday_flow.html absent from
    # the fake source scope, its row must not render, while darkpool.html
    # (present in the scope) still does.
    no_intraday = out["noIntraday"]
    assert 'href="intraday_flow.html"' not in no_intraday
    assert 'href="darkpool.html"' in no_intraday
    assert 'href="options.html"' in no_intraday, "an unrelated absent conditional must not hide the workspace row"


if __name__ == "__main__":
    for _name, _fn in sorted(globals().items()):
        if _name.startswith("test_") and callable(_fn):
            try:
                _fn()
                print("PASS", _name)
            except TypeError:
                pass  # parametrized — skip in this bare runner
