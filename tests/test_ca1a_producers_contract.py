"""CA1A producer near-miss contracts, pinned at the source level.

Macro CI has no browser, so the browser-visible behavior (events really landing,
product state surviving a dead beacon) belongs to the §16 production canary. What CI
CAN pin is the source structure that makes the near-miss laws true — the guards whose
REMOVAL is the mutation each of these tests exists to catch (CA1A handoff §15.13-21,
§15.25, §15.30):

  * a duplicate symbol cannot emit (the add() early-return precedes every emit);
  * a storage-blocked add cannot emit (storageOK gates the emit);
  * `watchlist.saved` fires only inside the localStorage ACK branch, threshold-armed;
  * bulk/merge paths (mergeInto) never emit;
  * intelligence.viewed emits only with baked rows > 0, latched once per session;
  * every emission rides mmTrackGrowth (stable eid + schema envelope), never a bare
    hand-built payload;
  * the shipping pairs actually ship what the templates say.
"""
from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

WL_T = (ROOT / "templates" / "watchlist.js").read_text(encoding="utf-8")
WL_S = (ROOT / "site" / "watchlist.js").read_text(encoding="utf-8")
TH_T = (ROOT / "templates" / "theme.js").read_text(encoding="utf-8")
TH_S = (ROOT / "site" / "theme.js").read_text(encoding="utf-8")
FV_T = (ROOT / "templates" / "flow_velocity.html.j2").read_text(encoding="utf-8")
FV_S = (ROOT / "site" / "flow_velocity.html").read_text(encoding="utf-8")


# ── shipping pairs (§15.25) ──────────────────────────────────────────────────────

def test_watchlist_js_pair_is_byte_identical():
    assert WL_T == WL_S, "templates/watchlist.js and site/watchlist.js must ship as one"


def test_theme_js_growth_helper_ships_in_both_pair_files():
    """site/theme.js is build-composed (not a byte copy), so the pair contract is
    that the CA1A helper block is present and identical in both."""
    block = re.search(r"window\.mmTrackGrowth = function[\s\S]*?\n      \};", TH_T)
    assert block, "mmTrackGrowth helper missing from templates/theme.js"
    assert block.group(0) in TH_S, "mmTrackGrowth helper differs between theme.js pair"


def test_flow_velocity_producer_ships_in_both_pair_files():
    block = re.search(r"\(function ivEmit\(\) \{[\s\S]*?\}\)\(\);", FV_T)
    assert block, "ivEmit producer missing from templates/flow_velocity.html.j2"
    assert block.group(0) in FV_S, "ivEmit producer differs between flow_velocity pair"


# ── envelope discipline ──────────────────────────────────────────────────────────

def test_every_producer_emission_rides_the_growth_envelope():
    """No producer hand-builds an envelope: watchlist.js emits only via growthEmit →
    mmTrackGrowth, and flow_velocity emits only via mmTrackGrowth. A bare mmTrack(
    'watchlist.saved' …) would ship an eid-less event the collector must drop."""
    for wire in ("watchlist.symbol_added", "watchlist.saved", "personal.act"):
        assert f"growthEmit('{wire}'" in WL_T, f"{wire} lost its growthEmit call"
        assert f"mmTrack('{wire}'" not in WL_T, f"{wire} bypasses the growth envelope"
    assert "mmTrackGrowth('intelligence.viewed'" in FV_T
    assert re.search(r"mmTrack\('intelligence\.viewed'", FV_T) is None
    assert "crypto.randomUUID" in TH_T and "schema: 'growth_events.v1'" in TH_T


# ── add() near-misses (§15.17-18, §15.30 shape) ─────────────────────────────────

def _fn(src: str, name: str) -> str:
    """The body of `function name(...) {...}` up to the next top-level function."""
    m = re.search(rf"function {name}\([^)]*\) \{{([\s\S]*?)\n  function ", src)
    assert m, f"could not isolate function {name}"
    return m.group(1)


def test_duplicate_symbol_cannot_emit():
    body = _fn(WL_T, "add")
    guard = body.index("if (!t || has(t)) return false;")
    emit = body.index("growthEmit('watchlist.symbol_added'")
    assert guard < emit, "the duplicate-symbol early-return must precede the emit"


def test_storage_blocked_add_cannot_emit():
    body = _fn(WL_T, "add")
    m = re.search(r"if \(storageOK\) \{([\s\S]*?)\n    \}", body)
    assert m, "the storageOK gate disappeared from add()"
    assert "growthEmit('watchlist.symbol_added'" in m.group(1)
    assert "growthEmit('personal.act'" in m.group(1)


def test_personal_act_is_latched_once_per_session():
    body = _fn(WL_T, "add")
    assert "sessionStorage.getItem('mm.pact.watchlist_add')" in body
    assert body.index("sessionStorage.setItem('mm.pact.watchlist_add'") < \
        body.index("growthEmit('personal.act'")


# ── saved = acknowledged threshold crossing (§15.19-20) ──────────────────────────

def test_saved_fires_only_inside_the_persist_ack_branch():
    """growthSavedCheck() is called exactly once, and that call sits INSIDE persist's
    try, AFTER the localStorage write — the acknowledgement — and before the catch."""
    calls = [m.start() for m in re.finditer(r"growthSavedCheck\(\);", WL_T)]
    assert len(calls) == 1, "growthSavedCheck must have exactly one call site (persist ack)"
    persist = re.search(
        r"var persist = debounce\(function \(\) \{\s*try \{([\s\S]*?)\} catch", WL_T)
    assert persist, "persist() shape changed"
    ack_block = persist.group(1)
    assert "localStorage.setItem(storageKey(), JSON.stringify(blob));" in ack_block
    assert "growthSavedCheck();" in ack_block
    assert ack_block.index("localStorage.setItem") < ack_block.index("growthSavedCheck()")


def test_saved_threshold_is_three_and_rearms_below_three():
    m = re.search(r"function growthSavedCheck\(\) \{([\s\S]*?)\n  \}", WL_T)
    assert m
    body = m.group(1)
    assert "n >= 3 && growthSavedArmed" in body
    assert "growthSavedArmed = false;" in body
    assert re.search(r"else if \(n < 3\) \{ growthSavedArmed = true; \}", body)
    assert "growthEmit('watchlist.saved'" in body


def test_boot_and_rebind_rearm_from_the_loaded_list():
    """A returning >=3 list must not re-emit on load; a rebind is a new list state.
    Both blob-load sites call growthSavedRebase()."""
    assert WL_T.count("growthSavedRebase();") == 2
    for site in re.finditer(r"blob = readStorage\(\);\n(.*)", WL_T):
        assert "growthSavedRebase" in site.group(1), (
            "a blob-load site is missing its growthSavedRebase() re-arm")


def test_bulk_merge_paths_never_emit():
    m = re.search(r"function mergeInto\(other\) \{([\s\S]*?)\n  \}", WL_T)
    assert m, "mergeInto shape changed"
    assert "growthEmit" not in m.group(1), (
        "mergeInto (import/cross-tab/cloud sync) must never emit a deliberate-act event")


# ── intelligence.viewed near-misses (§15.13-16) ─────────────────────────────────

def test_intelligence_viewed_requires_baked_rows_and_a_session_latch():
    m = re.search(r"\(function ivEmit\(\) \{([\s\S]*?)\}\)\(\);", FV_T)
    assert m
    body = m.group(1)
    assert "document.querySelectorAll('tr.sector-row').length" in body
    assert "if (!(ivRows > 0)) return;" in body, (
        "removing the rows>0 guard would emit on locked/empty builds — the exact "
        "mutation of handoff test 30")
    assert "sessionStorage.getItem('mm.iv.flow_velocity')" in body
    assert body.index("sessionStorage.setItem('mm.iv.flow_velocity'") < \
        body.index("mmTrackGrowth('intelligence.viewed'")
    assert "rows_visible: ivRows" in body


def test_intelligence_viewed_meta_is_the_registry_contract():
    assert "surface: 'flow_velocity', surface_group: 'read', tier_seen: 'anon'" in FV_T


# ── analytics can never break the product (§15.21, client half) ──────────────────

def test_all_producer_emissions_are_exception_isolated():
    m = re.search(r"function growthEmit\(wire, meta\) \{([\s\S]*?)\n  \}", WL_T)
    assert m and "try {" in m.group(1) and "catch" in m.group(1)
    helper = re.search(r"window\.mmTrackGrowth = function \(wire, meta\) \{([\s\S]*?)\n      \};", TH_T)
    assert helper and "try {" in helper.group(1) and "catch" in helper.group(1)
