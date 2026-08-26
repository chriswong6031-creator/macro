"""Byte-level pins for the HK Stock Dashboard V3.7 follower client composer.

site/hk-stock-v36.js is the HK follower of the Canada V3.7 composer
(site/canada-stock-v36.js), built per Sol's frozen follower architecture
(research/SOL_HK_V37_FOLLOWER_ARCHITECTURE.md, merges with records PR #6429).
Shared UX grammar, market-native semantics — never a Canada clone. These pins
hold the HK-specific constitution in place:

  - Top Picks is the owner's pv-featured cohort, never a position slice
    (Canada V3.6 shipped `state.cards.slice(0, 5)`; HK must never repeat it).
  - No LIVE plane exists for HK (site/live/quotes.json carries zero .HK
    symbols; the card's own nb-chg node is a server-baked "—"), so no LIVE
    text, no live-quote table enhancement, and zero fetch() calls anywhere.
  - Evidence & Record moves the HK trd wrapper via appendChild, never
    recomputed.
  - Leadership filtering never silently switches the Top Picks / All
    Candidates population (same Sol adversarial gate as Canada V3.7).
  - The Grid/Table XOR relies on explicit [hidden] overrides, same UA-vs-
    author display trap as Canada.
  - The loader (templates/dashboard-icons.js + its site/ pair) retries a
    transient entitled-fetch failure with the same bounded backoff shape as
    the Canada loader, gated on the composer's own idempotency flag.
"""

import re
from pathlib import Path

import pytest

COMPOSER = Path(__file__).resolve().parents[1] / "site" / "hk-stock-v36.js"


def _composer_text() -> str:
    if not COMPOSER.exists():
        pytest.skip("sparse checkout omits site/ (needs_full_checkout)")
    return COMPOSER.read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# Lane selector<->label binding (owner-native Act-Now vocabulary)
# ---------------------------------------------------------------------------

# (sel, en, zh) — the exact LANE_DEFS binding. Order matches the file so a
# swapped-lane mutation (e.g. "Buy Now" moved onto #anv2-red) is visible in a
# diff against this table too. Identical wording to Canada's LANE_BINDINGS
# because both markets share the Act-Now UX grammar (templates/hk.html.j2
# 3416-3419, `_hk_anlane(...)` title_en/title_zh) — the underlying sector
# population and every other HK read is independently harvested.
LANE_BINDINGS = [
    ("#anv2-buy", "Buy Now", "立即买入"),
    ("#anv2-pull", "In Favour", "看好"),
    ("#anv2-bot", "Bottoming Watch", "洗盘观察"),
    ("#anv2-red", "Reduce / Avoid", "减仓 / 回避"),
]


def test_lane_labels_bind_selector_to_owner_native_titles():
    """Each lane label must be bound to its OWN selector in LANE_DEFS — not
    merely present somewhere in the file. The regex requires sel/en/zh to
    appear together in one LANE_DEFS entry, so a mutation that swaps a label
    onto the wrong lane still fails this test even though the bare label
    text remains present elsewhere in the file."""
    text = _composer_text()
    for sel, en, zh in LANE_BINDINGS:
        pattern = (
            r'sel:\s*"' + re.escape(sel) + r'",\s*'
            r'en:\s*"' + re.escape(en) + r'",\s*'
            r'zh:\s*"' + re.escape(zh) + r'"'
        )
        assert re.search(pattern, text), (
            f"LANE_DEFS no longer binds {sel!r} to en={en!r} zh={zh!r} as one "
            "entry; either the label was swapped onto the wrong lane, or it "
            "was moved into a second, independently-invented lane vocabulary"
        )


# ---------------------------------------------------------------------------
# Featured-cohort pin — Top Picks is never a position slice
# ---------------------------------------------------------------------------

def test_source_set_is_built_from_pv_featured_never_a_position_slice():
    """sourceSet() must build the Top Picks cohort from the owner's
    `pv-featured` class (the literal selector, asserted below) — never from
    array position. Canada V3.6 shipped `state.cards.slice(0, 5)` for exactly
    this population; that defect is the one this pin exists to keep out of
    the HK follower. The file-wide ban on `slice(0` also catches a
    "leaders top 3" or "top N sectors" helper reintroducing position-based
    selection anywhere else — the composer uses a small `firstN()` helper
    instead everywhere it needs a bounded prefix."""
    text = _composer_text()
    assert '"pv-featured"' in text or "'pv-featured'" in text, (
        "composer never references the owner's pv-featured class literally; "
        "sourceSet() must be built from it"
    )
    m = re.search(r"function sourceSet\b.*?(?=\n  function )", text, re.S)
    assert m, "could not locate sourceSet() function body via regex"
    body = m.group(0)
    assert "pv-featured" in body, (
        "sourceSet() body does not reference pv-featured — the Top Picks "
        "cohort must be built inside this function from the owner's own "
        "featured flag"
    )
    assert "slice(" not in body, (
        "sourceSet() calls .slice(...) — Top Picks must never be a position "
        "slice of state.cards (the Canada V3.6 defect this composer must "
        "not repeat)"
    )
    assert "slice(0" not in text, (
        "composer contains a 'slice(0' call somewhere in the file; every "
        "bounded-prefix read (leaders, at-rest leadership rows) must use the "
        "firstN() helper instead so position-based Top Picks selection can "
        "never be quietly reintroduced anywhere"
    )


# ---------------------------------------------------------------------------
# No-LIVE invariant — HK has no canonical live quote/change plane
# ---------------------------------------------------------------------------

def test_no_live_plane_invariant():
    """HK has no per-ticker live quote plane (site/live/quotes.json carries
    zero .HK symbols; the card's own nb-chg node is a server-baked "—" with
    no dynamic up/down class). The composer must never claim otherwise: no
    user-visible LIVE chip markup, no live-quote table enhancement keyed off
    live/quotes.json, and no styling that reacts to a populated nb-chg.up/
    nb-chg.down class (which would silently start rendering the moment a
    live plane is ever wired up without this file being revisited)."""
    text = _composer_text()
    assert "LIVE" not in text, (
        "composer contains the literal string LIVE; HK has no canonical "
        "live quote plane and must not display a LIVE chip/clock"
    )
    assert "live/quotes.json" not in text, (
        "composer references live/quotes.json; HK has no live quote plane "
        "to read from"
    )
    assert "nb-chg.up" not in text and "nb-chg.down" not in text, (
        "composer styles/reacts to nb-chg.up or nb-chg.down; those classes "
        "are only ever added by a live quote plane HK does not have"
    )


def test_zero_fetch_calls():
    """Constitution: the composer harvests every input from DOM the server
    already rendered. Unlike Canada (which fetches two basket/pulse JSON
    endpoints), HK must make zero fetch() calls anywhere in the file."""
    text = _composer_text()
    assert "fetch(" not in text, (
        "composer calls fetch(); every HK input must be harvested from "
        "already-served DOM, never fetched independently"
    )


# ---------------------------------------------------------------------------
# Evidence & Record — moves the HK trd wrapper(s), never recomputes
# ---------------------------------------------------------------------------

def test_evidence_and_record_moves_trd_wrap_via_appendchild():
    """HK ships _track_record_dlg.html.j2 WITHOUT Canada's wrapping `.trk`
    div: #track-record directly holds two sibling `.trd-wrap` elements (the
    #trd-btn chip and the #trd-dlg dialog — verified site/hk_stocks.html:3765).
    evidenceWraps() must move ALL `.trd-wrap` matches, not just the first —
    moving only the button and stranding the dialog inside the hidden legacy
    panel would silently break the "Track record" click (display:none on an
    ancestor suppresses a position:fixed descendant too)."""
    text = _composer_text()
    assert 'id="hk-v37-evidence"' in text, (
        "Evidence & Record section markup missing its exact "
        'id="hk-v37-evidence"'
    )
    assert "Evidence &amp; Record" in text or "Evidence & Record" in text, (
        "Evidence & Record EN heading missing"
    )
    assert "证据与往绩" in text, "Evidence & Record ZH heading missing"
    assert "measurement.html" in text, "Methodology link to measurement.html missing"
    assert "qsa(\".trd-wrap\", host)" in text, (
        "evidenceWraps() no longer collects every .trd-wrap match via qsa() — "
        "moving only the first .trd-wrap (querySelector) would strand the "
        "#trd-dlg dialog inside the hidden legacy panel"
    )
    assert "evBody.appendChild(w)" in text or "appendChild(w)" in text, (
        "composer no longer moves the trd-wrap elements via appendChild; "
        "Track Record must be MOVED into the Evidence body, never "
        "recomputed or left unattached"
    )
    assert "hk_track_ledger" not in text, (
        "composer must never fetch factordata/hk_track_ledger.json itself; "
        "the trd dialog owns that fetch via its own data-url"
    )


# ---------------------------------------------------------------------------
# Population law — leadership filter never force-switches Top Picks/All
# ---------------------------------------------------------------------------

def test_leadership_activation_never_force_switches_population():
    """Same Sol adversarial gate as Canada V3.7: activate() must set
    state.filter and re-render via applyFilter() only — it must never call
    setSource(...) or set state.source = "all" as a side effect. The
    deliberate, user-initiated setSource("all") wired to .hk-v37-empty-switch
    in bind() is the only place that call is allowed."""
    text = _composer_text()
    m = re.search(r"function activate\b.*?(?=\n  function )", text, re.S)
    assert m, "could not locate activate() function body via regex"
    body = m.group(0)
    assert "setSource(" not in body, (
        "activate() calls setSource(...), which force-switches the Top "
        "Picks / All Candidates population as a side effect of leadership "
        "activation"
    )
    assert 'state.source = "all"' not in body, (
        'activate() directly sets state.source = "all"; leadership '
        "activation must leave the active population untouched"
    )
    assert "applyFilter()" in body, (
        "activate() must re-render via applyFilter() after setting "
        "state.filter"
    )
    assert "No Top Picks in this group." in text, "EN zero-state invitation missing"
    assert "该组别中暂无首选。" in text, "ZH zero-state invitation missing"
    assert "hk-v37-empty-switch" in text, "deliberate switch-to-All button missing"
    # The distinct zero-featured-cards empty state (never present in Canada,
    # since Canada always had a position-based Top Picks population).
    assert "No featured names right now." in text, (
        "EN zero-featured-cards empty state missing — when this build has no "
        "pv-featured cards at all, Top Picks must show this explicit state "
        "rather than silently behaving like All Candidates"
    )
    assert "当前暂无精选个股。" in text, "ZH zero-featured-cards empty state missing"


# ---------------------------------------------------------------------------
# Grid/Table XOR — explicit [hidden] overrides (same UA-vs-author trap)
# ---------------------------------------------------------------------------

REQUIRED_HIDDEN_OVERRIDES = [
    ".hk-v37-card-grid[hidden]{display:none!important}",
    ".hk-v37-card-grid .pvcard[hidden]{display:none!important}",
]


def test_hidden_attribute_overrides_ship_in_composer_style():
    """The UA sheet's [hidden]{display:none} loses to ANY author display
    rule, and both hidden targets carry one: the page stylesheet sets
    .pvcard{display:flex} and the composer's own style sets
    .hk-v37-card-grid{display:grid}. Without explicit overrides, the Top
    Picks segment, the leadership filter's grid hiding, and the grid/table
    view switch are all visually inert even though state/aria update."""
    text = _composer_text()
    for rule in REQUIRED_HIDDEN_OVERRIDES:
        assert rule in text, (
            f"composer style lost the {rule!r} override; the hidden "
            "attribute is defeated by author display rules and the Top "
            "Picks segment / leadership filter / grid-table switch go "
            "visually inert"
        )
    assert "card.hidden = !show" in text.replace("  ", " "), (
        "composer no longer hides grid cards via the hidden attribute; "
        "re-review REQUIRED_HIDDEN_OVERRIDES before deleting them"
    )


# ---------------------------------------------------------------------------
# Loader — bounded retry, both templates/ and site/ dashboard-icons.js
# ---------------------------------------------------------------------------

LOADER = Path(__file__).resolve().parents[1] / "templates" / "dashboard-icons.js"


def test_loader_retries_transient_entitled_fetch_failures():
    """Mirrors test_canada_v36_composer.py's
    test_loader_retries_transient_entitled_fetch_failures: the HK composer
    asset is entitled-only, and the gate consults the auth backend per
    request — a transient failure there must not strand an entitled visitor
    on the legacy page with no retry."""
    for path in [LOADER, LOADER.parents[1] / "site" / "dashboard-icons.js"]:
        if not path.exists():
            continue  # sparse checkout omits site/; templates/ always present
        text = path.read_text(encoding="utf-8")
        # Anchor on the distinguishing header comment, not the guard-flag
        # token itself — the IIFE checks the hk_stocks.html path regex
        # BEFORE it ever touches __mmHKStockV36Loader, so anchoring on the
        # flag would slice that path-gate check out of `block` entirely.
        start = text.find("HK Stock Dashboard V3.7 follower composer")
        assert start != -1, f"{path.name}: HK loader IIFE comment missing entirely"
        block = text[start:]
        assert "__mmHKStockV36Loader" in block, (
            f"{path.name}: __mmHKStockV36Loader block missing entirely"
        )
        assert "script.onerror" in block, f"{path.name}: loader lost its onerror retry"
        assert "attempt < 3" in block, f"{path.name}: loader retry is no longer bounded"
        assert "!window.__mmHKStockV36" in block, (
            f"{path.name}: retry must not re-inject after a successful mount"
        )
        assert '"hk-stock-v36.js?v=20260825"' in block, (
            f"{path.name}: loader no longer injects hk-stock-v36.js"
        )
        assert "hk_stocks\\.html" in block, (
            f"{path.name}: loader is no longer gated on hk_stocks.html"
        )


def test_loader_is_a_separate_iife_from_the_canada_loader():
    """The HK loader must never share its retry/idempotency state with the
    Canada loader — separate IIFE guard flag, separate injected script."""
    text = LOADER.read_text(encoding="utf-8")
    hk_idx = text.find("__mmHKStockV36Loader")
    ca_idx = text.find("__mmCanadaStockV36Loader")
    assert hk_idx != -1 and ca_idx != -1, "both loader guard flags must be present"
    hk_block = text[hk_idx:]
    assert "__mmCanadaStockV36" not in hk_block.split("}());", 1)[0], (
        "HK loader IIFE references a Canada composer flag; the two loaders "
        "must stay fully independent"
    )
