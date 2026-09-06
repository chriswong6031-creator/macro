"""Static-shell and enhancement pins for the HK Stock Dashboard V3.8.

site/hk-stock-v36.js is the HK composer, corrected to V3.8 per
research/STOCK_DASHBOARD_V38_ACTION_LEADERSHIP_ARCHITECTURE.md and
DEC:V38-ACTION-IS-NOT-LEADERSHIP (carrier
stock-dashboard-v38-hk-ca-fable-20260826-sol-001). Canonical V3.8 law:
ACTION TIMING ≠ TREND LEADERSHIP. These pins hold the constitution in place:

  Laws still controlling:
  - Top Picks is the owner's pv-featured cohort, never a position slice.
  - No LIVE plane exists for HK — no LIVE text, no live-quote enhancement,
    zero fetch() calls anywhere.
  - Evidence & Record and the HK track-record owner render in place; the
    composer never moves or recomputes them.
  - Leadership/action-group filtering never silently switches the Top
    Picks / All Candidates population.
  - Grid/Table and card filters preserve owner show-more state.
  - The Southbound flow cue is gated on the owner's own materiality marker
    (.sbah-sig sig-in/sig-out/sig-neu), never on mere node existence.
  - The loader (templates/dashboard-icons.js + site/ pair) retry pins.

  V3.8 corrections (new pins below):
  - What to Act On Now renders AT REST above Prophet — never only inside
    the Expand-leadership modal — with the exact owner-native lanes, at
    most 3 group rows per lane before View all, and name-first rows with
    no performance/score/percentile towers.
  - The visible sector rank is the OWNER's Sector Rotation rank rendered
    as `RS #N` under a visible "Relative strength vs HSI" basis label; a
    sector the owner did not rank shows "—" — lane traversal order is
    never minted into a rank number.
  - Action stance stays a separate axis/field from rank (RS #1 can be
    Reduce / Avoid; that is information, not a contradiction).
  - The ambiguous BOARD count label is gone: the count column is labelled
    Prophet/候选 and renders only when canonical membership is known —
    unknown membership must never render as zero.
  - Mobile (§5.5): one segmented lane selector, one lane body at a time;
    lane switching never mutates the Prophet selection.
"""

import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
COMPOSER = ROOT / "site" / "hk-stock-v36.js"
STOCK_CSS = ROOT / "templates" / "stock-dashboard.css"


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


HK_TEMPLATE = Path(__file__).resolve().parents[1] / "templates" / "hk.html.j2"

# Matches `_hk_anlane('buy', 'buy', 'Buy Now', '立即买入', ..., _hk_buy, 'anv2-buy')`
# — group 1/2 are the owner's title_en/title_zh, group 3 is the lane_id arg
# (the last positional arg, e.g. 'anv2-buy') that binds directly to our
# LANE_DEFS `sel`. templates/hk.html.j2 is out of OWNED FILES scope, so this
# only ever reads it.
_HK_ANLANE_CALL_RE = re.compile(
    r"_hk_anlane\('\w+',\s*'[\w-]+',\s*'([^']*)',\s*'([^']*)',.*?,\s*'(anv2-[a-z]+)'\)"
)


def _owner_lane_titles():
    text = HK_TEMPLATE.read_text(encoding="utf-8")
    out = {}
    for title_en, title_zh, lane_id in _HK_ANLANE_CALL_RE.findall(text):
        out["#" + lane_id] = (title_en, title_zh)
    return out


def test_lane_defs_match_the_owner_template_verbatim():
    """Cross-file consistency: LANE_DEFS is hand-copied from the owner's own
    `_hk_anlane(...)` macro calls (templates/hk.html.j2:3476-3479) rather than
    read from them at build time, so nothing forces the two to stay in sync.
    Parse the owner's title_en/title_zh straight out of the template and
    assert LANE_DEFS equals them exactly, selector for selector — an owner
    rewording (or a typo introduced copying LANE_DEFS by hand) now turns this
    test red instead of leaving stale/invented vocabulary in the composer
    silently green."""
    owner = _owner_lane_titles()
    assert len(owner) == 4, (
        f"expected exactly 4 _hk_anlane(...) calls in {HK_TEMPLATE}, "
        f"parsed {len(owner)}: {sorted(owner)} — the regex may no longer "
        "match the macro call shape"
    )
    for sel, en, zh in LANE_BINDINGS:
        assert sel in owner, f"{sel!r} not found among the owner's _hk_anlane(...) calls"
        assert owner[sel] == (en, zh), (
            f"LANE_DEFS[{sel!r}] = (en={en!r}, zh={zh!r}) no longer matches the "
            f"owner template's own title, which is now {owner[sel]!r} — "
            "reword LANE_DEFS to match, never the other way around"
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
# Southbound flow cue — materiality-gated, lives in the Leadership header
# ---------------------------------------------------------------------------

def test_southbound_flow_cue_gated_on_materiality_not_existence():
    """The architecture forbids the Southbound flow cue when the read is
    non-material — "cue absent when stale, unavailable, or non-material".
    The owner computes a deterministic directional marker for this exact
    card: .sbah-sig carries sig-in (inflow) / sig-out (outflow) / sig-neu
    (templates/hk.html.j2, `_sbsig`). southboundFirstRead() must gate on
    that marker — sig-neu (or a missing .sbah-sig node) returns null; only
    sig-in/sig-out surface the cue. This is a read of an owner-published
    class, never a composer-invented threshold. V3.8 moved the cue's home
    from the deleted Leading Now strip into the Leadership & Rotation
    header (§4); the materiality gate travels with it unchanged."""
    text = _composer_text()
    m = re.search(r"function southboundFirstRead\b.*?(?=\n  function )", text, re.S)
    assert m, "could not locate southboundFirstRead() function body via regex"
    body = m.group(0)
    assert "sbah-sig" in body, (
        "southboundFirstRead() no longer reads .sbah-sig — the cue would go "
        "back to gating on mere .sbah-read node existence, pinning even a "
        "neutral/non-material read to the Leadership header"
    )
    assert "sig-neu" in body, (
        "southboundFirstRead() no longer checks for the owner's sig-neu "
        "marker — a neutral 'no strong tilt' Southbound read would surface, "
        "which the architecture forbids (cue absent when non-material)"
    )
    # Not a composer-invented numeric threshold: no comparison operators
    # against sb.* fields (net_z, cum_20d, etc.) — the owner already
    # computed the directional verdict server-side into the sig-* class.
    assert not re.search(r"[<>]=?\s*0(\.\d+)?\b", body), (
        "southboundFirstRead() appears to compare a numeric value against a "
        "threshold — materiality must be read from the owner's own sig-* "
        "class, never recomputed from raw flow numbers client-side"
    )
    # The cue's one consumer is renderFlowCue(), which fills the
    # #hk-v37-flow slot in the Leadership & Rotation header.
    m2 = re.search(r"function renderFlowCue\b.*?(?=\n\n)", text, re.S)
    assert m2, "could not locate renderFlowCue() function body via regex"
    cue_body = m2.group(0)
    assert "southboundFirstRead()" in cue_body, (
        "renderFlowCue() no longer consumes southboundFirstRead() — the "
        "materiality-gated cue has lost its renderer"
    )
    assert '"#hk-v37-flow"' in cue_body, (
        "renderFlowCue() no longer targets the #hk-v37-flow header slot"
    )
    assert 'id="hk-v37-flow"' in HK_TEMPLATE.read_text(encoding="utf-8"), (
        "the server-owned Leadership header lost the #hk-v37-flow slot; "
        "header — the cue has nowhere to render"
    )


def test_leadership_rows_keep_action_stance_as_separate_axis():
    """V3.8 axis law: every leadership row carries the sector's own
    owner-native action stance chip as a SEPARATE field beside the RS rank —
    `RS #1 · Reduce / Avoid` is a legitimate combination and must render
    honestly (the V3.7 Leading Now strip that used to carry this duty is
    gone, so the rows themselves are now the only guard). leadRow() must
    interpolate x.tone into an .hk-v37-stance chip and x.stance.en/zh as its
    text — a bare ranked name would silently imply 'strong = buy'."""
    text = _composer_text()
    m = re.search(r"function leadRow\b.*?(?=\n  function )", text, re.S)
    assert m, "could not locate leadRow() function body via regex"
    body = m.group(0)
    assert "hk-v37-stance " in body and "x.tone" in body, (
        "leadRow() no longer renders an .hk-v37-stance chip keyed off x.tone "
        "— action stance must stay a separate visible axis beside RS rank"
    )
    assert "x.stance.en" in body and "x.stance.zh" in body, (
        "leadRow() no longer interpolates the sector's own stance text"
    )


# ---------------------------------------------------------------------------
# Evidence & Record — moves the HK trd wrapper(s), never recomputes
# ---------------------------------------------------------------------------

def test_evidence_and_record_renders_owner_track_record_in_place():
    """Static HTML owns the evidence section and the complete dialog wrappers."""
    text = _composer_text()
    template = HK_TEMPLATE.read_text(encoding="utf-8")
    start = template.index('<section class="hk-v37-panel span12" id="hk-v37-evidence">')
    end = template.index("</section>", start)
    section = template[start:end]
    assert "Evidence & Record" in section and "证据与往绩" in section
    assert "measurement.html" in section
    assert 'id="track-record"' in section
    assert "_track_record_dlg.html.j2" in section
    assert "evidenceWraps" not in text and "evidenceSectionHtml" not in text
    assert "appendChild" not in text and "insertBefore" not in text
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
    in bind() is the only place that call is allowed.

    Hardened against comment-satisfiable false-passes: the three empty-state
    strings/markers are scoped to emptyStateHtml()'s OWN function body (a
    bare `"literal" in text` check would still pass if the emitting branch
    were deleted but a comment elsewhere kept mentioning the same words);
    the deliberate switch is pinned as a live `.hk-v37-empty-switch` click
    handler that calls `setSource("all")`, not just the class name appearing
    somewhere in the file."""
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

    m3 = re.search(r"function emptyStateHtml\b.*?(?=\n  function )", text, re.S)
    assert m3, "could not locate emptyStateHtml() function body via regex"
    empty_body = m3.group(0)
    assert "No Top Picks in this group." in empty_body, (
        "EN zero-state invitation missing from emptyStateHtml()'s own body"
    )
    assert "该组别中暂无首选。" in empty_body, (
        "ZH zero-state invitation missing from emptyStateHtml()'s own body"
    )
    assert "hk-v37-empty-switch" in empty_body, (
        "deliberate switch-to-All button markup missing from "
        "emptyStateHtml()'s own body"
    )
    # The distinct zero-featured-cards empty state (never present in Canada,
    # since Canada always had a position-based Top Picks population).
    assert "No featured names right now." in empty_body, (
        "EN zero-featured-cards empty state missing from emptyStateHtml()'s "
        "own body — when this build has no pv-featured cards at all, Top "
        "Picks must show this explicit state rather than silently behaving "
        "like All Candidates"
    )
    assert "当前暂无精选个股。" in empty_body, (
        "ZH zero-featured-cards empty state missing from emptyStateHtml()'s own body"
    )

    # The deliberate switch itself: a live click delegation that calls
    # setSource("all") when .hk-v37-empty-switch is clicked — not merely the
    # class name appearing as markup with no wired behavior.
    assert re.search(
        r'closest\("\.hk-v37-empty-switch"\)\)\s*return setSource\("all"\)', text
    ), (
        "bind() no longer wires .hk-v37-empty-switch to a live "
        'setSource("all") call — the deliberate switch-to-All control '
        "would render but do nothing"
    )


# ---------------------------------------------------------------------------
# Grid/Table XOR — explicit [hidden] overrides (same UA-vs-author trap)
# ---------------------------------------------------------------------------

REQUIRED_HIDDEN_OVERRIDE = (
    ".mx-stockdash--hk .hk-v37-card-grid .pvcard[hidden] { display: none !important; }"
)


def test_hidden_attribute_override_ships_in_governed_stylesheet():
    """Card filters retain an author-level hidden override without runtime CSS."""
    text = _composer_text()
    css = STOCK_CSS.read_text(encoding="utf-8")
    assert REQUIRED_HIDDEN_OVERRIDE in css
    assert "card.hidden = !show" in text.replace("  ", " "), (
        "composer no longer hides filtered cards via the hidden attribute"
    )
    assert "createElement(\"style\")" not in text and "style.textContent" not in text


def test_owner_show_more_state_survives_in_place():
    """No card move or global rescue may override the owner's show-more state."""
    text = _composer_text()
    css = STOCK_CSS.read_text(encoding="utf-8")
    assert 'classList.remove("sm-hidden")' not in text
    assert ".hk-v37-card-grid .sm-hidden" not in css
    assert "appendChild" not in text and "insertBefore" not in text


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


# ---------------------------------------------------------------------------
# closeModal() is a no-op when the modal was never open
# ---------------------------------------------------------------------------

def test_close_modal_guards_on_is_open_before_clearing_overflow():
    """NONBLOCKING repair (adversarial review, 2026-08-25): activate() calls
    closeModal() unconditionally on every leadership-row click (rows are
    clickable both on the page and inside the modal), so closeModal() must
    be a no-op when the modal was never open — otherwise every plain
    leadership click (never having opened the modal) clears
    document.documentElement.style.overflow regardless of whether anything
    set it. Pinned as a guard clause scoped inside closeModal()'s own
    function body: `if (!modal || !modal.classList.contains("is-open"))
    return;` before the style mutation, not merely the string
    "is-open" appearing somewhere in the file."""
    text = _composer_text()
    m = re.search(r"function closeModal\b.*?\n  \}", text, re.S)
    assert m, "could not locate closeModal() function body via regex"
    body = m.group(0)
    assert re.search(r'!modal\.classList\.contains\("is-open"\)', body), (
        "closeModal() no longer guards on modal.classList.contains(\"is-open\") "
        "— it will clear document.documentElement.style.overflow even when "
        "the modal was never opened"
    )
    # The guard must come BEFORE the overflow mutation, not after (an
    # after-the-fact check would already have cleared the style).
    guard_idx = body.find('classList.contains("is-open")')
    overflow_idx = body.find("style.overflow")
    assert 0 <= guard_idx < overflow_idx, (
        "the is-open guard must appear before the "
        "document.documentElement.style.overflow mutation in closeModal(), "
        "not after it"
    )


# ---------------------------------------------------------------------------
# V3.8 — What to Act On Now at rest above Prophet (never modal-only)
# ---------------------------------------------------------------------------

def _build_shell_markup(_text: str = "") -> str:
    template = HK_TEMPLATE.read_text(encoding="utf-8")
    start = template.index('<main class="hk-v37 mx-stockdash mx-stockdash--hk" id="hk-v37">')
    end = template.index("</main>", start)
    return template[start:end]


def test_act_now_renders_at_rest_above_prophet_never_modal_only():
    """V3.8 §13.1: without opening any modal, the user sees the owner-native
    action lanes — group action must not be recoverable only through Expand
    Leadership. Pins the server-owned #hk-v37-actnow markup before Prophet,
    forbids client reconstruction/movement, and keeps the old modal action
    band absent so there is exactly one action-surface owner."""
    text = _composer_text()
    shell = _build_shell_markup(text)
    actnow_idx = shell.find('id="hk-v37-actnow"')
    prophet_idx = shell.find('id="hk-v37-prophet"')
    assert actnow_idx != -1, (
        "the template no longer renders the #hk-v37-actnow section at rest "
        "— the What to Act On Now job is buried again"
    )
    assert prophet_idx != -1, "the template lost the #hk-v37-prophet section"
    assert actnow_idx < prophet_idx, (
        "the What to Act On Now section must render ABOVE Prophet (§4 page "
        "grammar), not below it"
    )
    owner = shell[actnow_idx:prophet_idx]
    assert 'id="act-now"' in owner
    assert "main.innerHTML" not in text
    assert "appendChild" not in text and "insertBefore" not in text
    assert "hk-v37-modal-lanes" not in text, (
        "the V3.7 modal group-action band (hk-v37-modal-lanes) is back — "
        "the at-rest panel is the one home for group action; a second home "
        "inside the modal is duplication, not compression"
    )
    m = re.search(r"function openModal\b.*?(?=\n  /\*|\n  function )", text, re.S)
    assert m, "could not locate openModal() function body via regex"
    assert "groupActionBandHtml" not in m.group(0), (
        "openModal() composes a group-action band again — What to Act On "
        "Now must not live (only) inside Expand Leadership"
    )


def test_at_rest_lane_rows_capped_at_three_with_view_all():
    """V3.8 §5.2 density law: no more than 3 group rows per lane at rest;
    additional content only through the explicit View all expansion. The
    server renders every owner row once, while the shared stylesheet caps a
    collapsed lane at three and the template emits View all only above that
    threshold."""
    template = HK_TEMPLATE.read_text(encoding="utf-8")
    css = STOCK_CSS.read_text(encoding="utf-8")
    assert 'class="anv2-lst hk-v37-an-list is-collapsed"' in template
    assert "{% if items|length > 3 %}" in template and "data-hk-an-view" in template
    assert re.search(
        r"\.hk-v37-an-list\.is-collapsed\s*>\s*:nth-child\(n\+4\)\s*\{\s*display:\s*none",
        css,
    )


# ---------------------------------------------------------------------------
# V3.8 — rank is the owner's rank; lane traversal is never rank
# ---------------------------------------------------------------------------

def test_rank_is_owner_rank_never_lane_traversal():
    """DEC:V38-ACTION-IS-NOT-LEADERSHIP: every visible numeric rank needs a
    canonical rank owner; lane traversal order is never a rank. The only
    .rank assignments collectSectors() may make are the owner-rank copy
    (`x.rank = r.rank`) and the explicit null (`x.rank = null`) for a
    sector the owner did not rank. The V3.7 synthesis
    (`x.rank = ranked.length + i + 1`) — and the Canada idiom
    (`out.length + 1`) — must never reappear anywhere in the file."""
    text = _composer_text()
    m = re.search(r"function collectSectors\b.*?(?=\n  function )", text, re.S)
    assert m, "could not locate collectSectors() function body via regex"
    body = m.group(0)
    assert "x.rank = r.rank" in body, (
        "collectSectors() no longer copies the owner's rotation rank"
    )
    # Catch both member-access and subscript assignment shapes — a mutation
    # writing x["rank"] = ... must not slip past a dot-only scan
    # (adversarial review 2026-08-27, finding 8).
    assignments = re.findall(r"(?:\.rank|\[[\"']rank[\"']\])\s*=\s*([^;]+);", body)
    for rhs in assignments:
        assert rhs.strip() in {"r.rank", "null"}, (
            f"collectSectors() assigns rank = {rhs.strip()!r} — the only "
            "lawful assignments are the owner-rank copy (r.rank) and the "
            "explicit null; anything else is a presentation-minted rank"
        )
    assert '["rank"]' not in text and "['rank']" not in text, (
        "the composer assigns rank via subscript somewhere — every rank "
        "write must be visible to this test's assignment scan"
    )
    assert "ranked.length + i" not in text, (
        "the V3.7 rank synthesis (ranked.length + i + 1) is back — a sector "
        "without an owner rank must render '—', never a minted number"
    )
    assert "out.length + 1" not in text, (
        "the Canada traversal-rank idiom (out.length + 1) appeared in the "
        "HK composer — lane traversal is never rank"
    )


def test_rank_basis_label_and_rs_prefix():
    """V3.8 §6.2: never display a bare rank number without a visible basis.
    Pins (a) the 'Relative strength vs HSI' basis label in buildShell()'s
    Leadership & Rotation header (and its ZH twin, the owner's own
    相对恒生指数); (b) leadRow()/modalRows() render `RS #` + the owner rank
    and fall back to '—' on null via the exact conditional — removing the
    label, the prefix, or the null guard turns this red."""
    text = _composer_text()
    # The basis label must be visible in BOTH rank homes: the at-rest
    # Leadership & Rotation header (buildShell markup) and the expanded
    # modal pane (modalPaneHtml) — losing either leaves a bare RS number
    # somewhere.
    shell = _build_shell_markup(text)
    leadership = re.search(r"function renderLeadership\b.*?(?=\n  /\*)", text, re.S)
    assert leadership, "could not locate renderLeadership()"
    assert 'qs("#hk-v37-lead-basis")' in leadership.group(0)
    assert "basis.hidden = !state.hasRankOwner" in leadership.group(0)
    mp = re.search(r"function modalPaneHtml\b.*?(?=\n  function )", text, re.S)
    assert mp, "could not locate modalPaneHtml() function body via regex"
    for where, markup in [("Leadership & Rotation header", shell),
                          ("expanded modal pane", mp.group(0))]:
        assert "Relative strength vs HSI" in markup, (
            f"the visible rank-basis label (Relative strength vs HSI) is "
            f"gone from the {where} — a bare RS number without its basis is "
            "exactly the V3.7 confusion V3.8 corrects"
        )
        assert "相对恒生指数" in markup, (
            f"the ZH rank-basis label (相对恒生指数, the owner's own "
            f"wording) is gone from the {where}"
        )
    for fn in ("leadRow", "modalRows"):
        m = re.search(r"function " + fn + r"\b.*?(?=\n  function )", text, re.S)
        assert m, f"could not locate {fn}() function body via regex"
        body = m.group(0)
        assert re.search(r'x\.rank != null \? "RS #" \+ x\.rank : "—"', body), (
            f"{fn}() no longer renders the owner rank as 'RS #N' with the "
            "explicit null → '—' guard — either the basis-bearing prefix or "
            "the no-synthesized-rank fallback was dropped"
        )
    assert "Sector Leadership" not in text, (
        "the old ambiguous 'Sector Leadership' heading is back — V3.8 names "
        "this surface Leadership & Rotation"
    )


# ---------------------------------------------------------------------------
# V3.8 — Prophet count label; unknown membership is never zero
# ---------------------------------------------------------------------------

def test_count_is_labelled_prophet_and_unknown_membership_never_renders_zero():
    """V3.8 §6.3 + failure law: the ambiguous BOARD count label is gone —
    the count column is labelled Prophet/候选 — and a Prophet count renders
    only where canonical membership is known. collectSectors() derives
    membershipKnown from the board rows actually carrying a sector field;
    when unknown it must set members/count to null (NOT an empty set /
    zero), and every renderer must branch on `count != null` rather than
    defaulting to 0."""
    text = _composer_text()
    m = re.search(r"function renderLeadership\b.*?(?=\n  /\*|\n  function )", text, re.S)
    assert m, "could not locate renderLeadership() function body via regex"
    body = m.group(0)
    assert 'bi("Prophet", "候选")' in body, (
        "the leadership list count column is no longer labelled "
        "Prophet/候选 — an unlabelled or BOARD-labelled count is the "
        "ambiguity V3.8 removes"
    )
    assert 'bi("Board", "榜单")' not in body, (
        "the ambiguous Board/榜单 count label is back in renderLeadership()"
    )
    m2 = re.search(r"function collectSectors\b.*?(?=\n  function )", text, re.S)
    assert m2, "could not locate collectSectors() function body via regex"
    sec_body = m2.group(0)
    assert "state.membershipKnown" in sec_body and "r.sector" in sec_body, (
        "collectSectors() no longer derives membershipKnown from the board "
        "rows' own sector field"
    )
    assert re.search(r"x\.members = null; x\.leaders = \[\]; x\.count = null;", sec_body), (
        "collectSectors() no longer nulls members/count when membership is "
        "unknown — an empty set would render as a false 0"
    )
    for fn, snippet in [
        ("leadRow", 'x.count != null ? x.count : "—"'),
        ("modalRows", 'x.count != null ? x.count : "—"'),
    ]:
        m3 = re.search(r"function " + fn + r"\b.*?(?=\n  function )", text, re.S)
        assert m3, f"could not locate {fn}() function body via regex"
        assert snippet in m3.group(0), (
            f"{fn}() no longer branches on count != null — an unknown "
            "membership would render as zero, and missing ≠ zero"
        )
    template = HK_TEMPLATE.read_text(encoding="utf-8")
    assert "{% if _hk_members.known %}<span class=\"hk-v37-an-n\">" in template


# ---------------------------------------------------------------------------
# V3.8 — mobile lane grammar; presentation controls never touch population
# ---------------------------------------------------------------------------

def test_static_owner_action_board_has_mobile_single_column_grammar():
    """The first-frame owner lanes collapse to one bounded column on phones."""
    template = HK_TEMPLATE.read_text(encoding="utf-8")
    stock_css = STOCK_CSS.read_text(encoding="utf-8")
    shell = _build_shell_markup()
    assert re.search(r'class="anv2-grid\s+hk-v37-an-lanes"', shell)
    assert re.search(
        r"@media\s*\(max-width:\s*680px\).*?"
        r"\.hk-v37-an-lanes\s*\{[^}]*grid-template-columns:\s*1fr",
        stock_css,
        re.S,
    )
    assert re.search(
        r"\.hk-v37-an-body:not\(\.is-enhanced\).*?\.hk-v37-an-lane:target\s*\{[^}]*display:\s*block",
        stock_css,
        re.S,
    )
    assert ".hk-v37-an-body.is-enhanced .hk-v37-an-lane.is-current" in stock_css
    assert 'id="act-now"' in template


def test_mobile_lane_election_only_when_no_lane_chosen():
    """Adversarial review 2026-08-27, finding 1 (MAJOR): the default-lane
    election belongs to the static owner and must be adopted once. The
    enhancer must not re-elect from client data after a user chooses an empty
    lane; all-empty deterministically falls back to Buy."""
    text = _composer_text()
    template = HK_TEMPLATE.read_text(encoding="utf-8")
    assert "renderActNow" not in text
    adopt = re.search(r"function adoptActNow\b.*?(?=\n  function )", text, re.S)
    assert adopt and 'getAttribute("data-hk-an-default") === "true"' in adopt.group(0)
    assert 'host.classList.add("is-enhanced")' in adopt.group(0)
    assert "('avoid' if _hk_red else 'buy')" in template


def test_act_now_enhancement_reconciles_fragments_without_replacing_owner_nodes():
    """The static owner is an anchor fallback; only the loaded composer may
    upgrade those same nodes to tabs and bind action-local history."""
    text = _composer_text()
    template = HK_TEMPLATE.read_text(encoding="utf-8")
    assert '<div class="hk-v37-an-seg">' in template
    assert '<a href="#anv2-buy" data-hk-an-lane="buy"' in template
    assert 'role="tablist"' not in template[template.index('<div class="hk-v37-an-seg">'):template.index('<div class="anv2-grid hk-v37-an-lanes">')]
    assert "function toneFromActionHash" in text
    assert 'seg.setAttribute("role", "tablist")' in text
    assert 'tab.setAttribute("role", "tab")' in text
    assert 'tab.setAttribute("aria-controls", laneId)' in text
    assert 'window.addEventListener("hashchange", reconcileActionLocation)' in text
    assert 'window.addEventListener("popstate", reconcileActionLocation)' in text
    assert "history.pushState" in text
    assert "cloneNode(" not in re.search(
        r"function adoptActNow\b.*?(?=\n  function )", text, re.S
    ).group(0)


def test_act_now_rows_carry_group_research_route_and_known_zero_state():
    """Adversarial review 2026-08-27, finding 2 (MAJOR): §5.4/§10 — a
    known-zero group must stay useful as a group-research destination.
    Pins (a) the server row renders the harvested owner href as a live
    .hk-v37-an-go route link; (b) emptyStateHtml() has a distinct known-zero
    branch (members known, size 0) with quiet §10 copy — never the
    filter-miss language — that keeps the research route usable."""
    text = _composer_text()
    template = HK_TEMPLATE.read_text(encoding="utf-8")
    assert 'class="anv2-name-link hk-v37-an-go" href="sectors/{{ it.ticker }}.html"' in template
    m2 = re.search(r"function emptyStateHtml\b.*?(?=\n  function )", text, re.S)
    assert m2, "could not locate emptyStateHtml() function body via regex"
    empty_body = m2.group(0)
    assert "item.members.size === 0" in empty_body, (
        "emptyStateHtml() lost its known-zero branch — a canonically empty "
        "group falls through to filter-miss language, which §10 forbids"
    )
    assert "No current Prophet names in this group." in empty_body, (
        "the quiet §10 known-zero copy is gone from emptyStateHtml()"
    )
    assert "该组别暂无 Prophet 候选。" in empty_body, (
        "the ZH known-zero copy is gone from emptyStateHtml()"
    )
    assert "item.href" in empty_body and "hk-v37-empty-go" in empty_body, (
        "the known-zero state no longer offers the group-research route"
    )


def test_rank_language_degrades_when_rank_owner_missing():
    """Adversarial review 2026-08-27, finding 3 (MAJOR): §10 — when the
    rank owner is absent (no sector carries an owner rank), hide numeric
    rank AND rank language. Pins (a) collectSectors() derives
    state.hasRankOwner from the merged rank values; (b) the at-rest
    Leadership header renders its basis chip only under state.hasRankOwner;
    (c) modalPaneHtml() guards both its basis chip and its Rank column on
    the same flag, and modalRows() takes the flag rather than always
    emitting a rank cell."""
    text = _composer_text()
    m = re.search(r"function collectSectors\b.*?(?=\n  function )", text, re.S)
    assert m, "could not locate collectSectors() function body via regex"
    assert re.search(r"state\.hasRankOwner = merged\.some\(function \(x\) \{ return x\.rank != null; \}\)", m.group(0)), (
        "collectSectors() no longer derives state.hasRankOwner from the "
        "merged owner ranks"
    )
    shell = _build_shell_markup(text)
    assert 'id="hk-v37-lead-basis" hidden' in shell
    rl = re.search(r"function renderLeadership\b.*?(?=\n  /\*)", text, re.S)
    assert rl and "basis.hidden = !state.hasRankOwner" in rl.group(0), (
        "the static rank-basis slot is no longer hidden when no owner rank exists"
    )
    mp = re.search(r"function modalPaneHtml\b.*?(?=\n  function )", text, re.S)
    assert mp, "could not locate modalPaneHtml() function body via regex"
    mp_body = mp.group(0)
    assert "state.hasRankOwner" in mp_body, (
        "modalPaneHtml() no longer consults state.hasRankOwner"
    )
    assert re.search(r"rk \? '<th>' \+ bi\(\"Rank\", \"排名\"\)", mp_body), (
        "the modal Rank column header is unconditional again"
    )
    mr = re.search(r"function modalRows\b.*?(?=\n  function )", text, re.S)
    assert mr, "could not locate modalRows() function body via regex"
    assert re.search(r"rk \? '<td class=\"num\">'", mr.group(0)), (
        "modalRows() emits its rank cell unconditionally again"
    )


def test_at_rest_action_rows_carry_no_metric_towers():
    """§5.2/§13.5: at-rest action rows carry only the group name, optional
    type cue, optional Prophet count, and a route/filter affordance — never
    performance stacks, score towers, percentile or diagnostic fields. Pins
    the server row summary and the scoped CSS that keeps supplemental card
    chips and stats out of the at-rest lane."""
    text = _composer_text()
    template = HK_TEMPLATE.read_text(encoding="utf-8")
    assert "renderActNow" not in text
    assert '<div class="anv2-row-top">' in template
    assert '<button class="anv2-name hk-v37-an-row"' in template
    css = STOCK_CSS.read_text(encoding="utf-8")
    assert ".hk-v37-an-body :is(.anv2-chips, .anv2-stat) { display: none; }" in css


def test_act_now_lane_order_is_the_action_owners_order():
    """DEC:V38-ACTION-IS-NOT-LEADERSHIP: the rank axis must not order (or
    via the 3-row cap, gate the at-rest visibility of) the action surface.
    collectLaneSectors() records the owner's lane order for Leadership, while
    the static action surface preserves the owner's template iteration order
    independently of that client-side presentation model."""
    text = _composer_text()
    m = re.search(r"function collectLaneSectors\b.*?(?=\n  /\*|\n  function )", text, re.S)
    assert m, "could not locate collectLaneSectors() function body via regex"
    assert "laneIdx: out.length" in m.group(0), (
        "collectLaneSectors() no longer stamps the action owner's row order"
    )
    template = HK_TEMPLATE.read_text(encoding="utf-8")
    assert "{% for it in items %}{{ _hk_anrow(it, lane) }}{% endfor %}" in template
    assert "renderActNow" not in text


def test_act_now_presentation_controls_never_touch_population_or_filter():
    """V3.8 §5.5: switching the visible mobile lane (or expanding View all)
    is presentation-only — it must not mutate the Prophet selection until a
    group is actually chosen. setAnLane()/toggleAnLane() must not call
    setSource()/activate()/applyFilter() or assign state.source /
    state.filter."""
    text = _composer_text()
    for fn in ("setAnLane", "toggleAnLane"):
        m = re.search(r"function " + fn + r"\b.*?\n  \}", text, re.S)
        assert m, f"could not locate {fn}() function body via regex"
        body = m.group(0)
        for forbidden in ("setSource(", "activate(", "applyFilter(",
                          "state.source", "state.filter"):
            assert forbidden not in body, (
                f"{fn}() references {forbidden!r} — Act-Now lane "
                "presentation controls must never mutate the Prophet "
                "population or filter"
            )
