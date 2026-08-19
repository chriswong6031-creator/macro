"""tests/test_options_intel_brief_ui.py — AD-1 board CONSUMER/parity suite.

Contract (BINDING): ``contracts/options/OPTIONS_INTEL_BRIEF_V1.md`` §5 (artifact
schema) and §6 (authority table).  Design (FROZEN, implement-don't-redesign): the
AD-1 board design spec commissioned alongside this suite.

Scope: ``scripts/build_options_command.py``'s AD-1 seam (``load_intel_brief``,
``build_aib``, ``_aib_card`` and friends) plus the board markup this seam feeds in
``templates/options.html.j2``.  Test numbers 34-40 continue the commission's own
numbering (tests 1-33 live in ``tests/test_options_intel_brief.py`` and cover the
PRODUCER; this file is the CONSUMER/parity half).

House rule this suite exists to prove: the command builder is a PASS-THROUGH
ADAPTER, never a second scorer.  Every assertion below either (a) feeds a fixture
artifact and checks the rendered HTML reproduces its values/order VERBATIM, or
(b) proves an absent/corrupt artifact degrades to an honest empty state without
touching the rest of the page.

AD-1 B5 (product exposure, Sol REQUEST_CHANGES on #5872) extends this file below
tests 34-40 with the three added bands inside #aib — directional watch, evidence
rail, control (contract §5a) — using a separate ``_b5_*`` fixture family (the
pre-B5 ``_card()``/``_brief()`` above never set ``board_rank`` or populate the
new top-level arrays). Same house rule: pass-through only, verbatim order.

Run: python3 -m pytest tests/test_options_intel_brief_ui.py -q
"""
from __future__ import annotations

import hashlib
import json
import re
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from scripts.build_options_command import (  # noqa: E402
    build_aib,
    build_context,
    load_intel_brief,
    render,
)

# Reuse the house's own legacy-Workspace fixtures rather than inventing a second
# synthetic-store shape — test 36 needs a REAL legacy render to prove against.
# Importing (never modifying) tests/test_build_options_command.py, which is out
# of scope for this packet's edits.
from tests.test_build_options_command import EMPTY_STORES, MODES, _stores  # noqa: E402


# ─────────────────────────────────────────────────────────────────────────────
# Fixture cards — deterministic, hand-built (never derived from the adapter
# itself, or a bug in the adapter could pass by construction).
# ─────────────────────────────────────────────────────────────────────────────
def _card(symbol: str, *, direction: str, r: int, band: str = "moderate",
          oi: float = 0.71, skew: float = 0.55, es: float = 0.82,
          prophet: str = "READY", crowding=None) -> dict:
    return {
        "signal_id": f"adib:v1.2:2026-08-12:{symbol}",
        "symbol": symbol, "canonical_instrument_id": f"US:{symbol}",
        "direction": direction,
        "display_state_en": {"LONG": "Upside evidence", "SHORT": "Downside evidence",
                              "VOLATILITY": "Volatility", "RISK_ONLY": "Risk / crowding"}[direction],
        "display_state_zh": {"LONG": "上行证据", "SHORT": "下行证据",
                              "VOLATILITY": "波动性", "RISK_ONLY": "风险/拥挤"}[direction],
        "horizon": "next_5_sessions",
        "evidence_strength": es, "evidence_confidence": 0.42, "evidence_confidence_band": band,
        "research_priority_score": r,
        "why_now": [{"en": f"why-now fact for {symbol}", "zh": f"{symbol} 的证据事实"}],
        "evidence": [
            {"name": "Q_oi", "value": oi, "history_n": 45, "observed_or_inferred": "inferred"},
            {"name": "Q_skew", "value": skew, "history_n": 18, "observed_or_inferred": "inferred"},
        ],
        "contradictions": [],
        "mechanics_context": {"gex_confirm_verdict": None, "gamma_regime": None, "flip_proximity": None},
        "crowding": crowding,
        "event": None,
        "market_implied_move_pct": 0.041,
        "trigger_watch": {"en": f"trigger for {symbol}", "zh": f"{symbol} 触发条件"},
        "invalidation_watch": {"en": f"invalidation for {symbol}", "zh": f"{symbol} 失效条件"},
        "fresh_until": "2026-08-17",
        "source_state": "ok",
        "prophet_state": prophet,
        "prophet_asof": "2026-08-12",
        "asymmetry_score": None, "asymmetry_state": "UNCALIBRATED",
        "probability_up": None, "probability_down": None, "expected_edge_bps": None,
        "supersedes_signal_id": None, "corrected_at": None,
    }


def _brief(*, board_state="OK", board_reason=None, opportunities=None,
           pending_session=None, eligible=210, present=300, overflow=0,
           as_of="2026-08-12", oi_counted="2026-08-13") -> dict:
    return {
        "schema": "options.intel_brief/v1", "model_version": "intel_brief_heuristic/v1.2",
        "as_of_session": as_of, "oi_counted_date": oi_counted,
        "pending_session": pending_session,
        "eligibility": {"present": present, "eligible": eligible,
                        "insufficient_history": 0, "insufficient_coverage": 0},
        "board_state": board_state, "board_reason": board_reason,
        "receipt_id": "e5bd3f474eabff7904574b8c8abccd1d45f1bb57210eac2d4073e61915ad5153",
        "opportunities": opportunities or [],
        "opportunities_overflow": overflow,
        "event_board": [], "risk_warnings": [], "no_signal_exemplar": None,
    }


def _sym_order(page: str) -> list[str]:
    return re.findall(r'class="oew-aib-sym mono">([^<]+)<', page)


def _workspace(page: str) -> str:
    start = page.index('<div class="oew">')
    end = page.index("<!-- /oew -->")
    return page[start:end]


# ─────────────────────────────────────────────────────────────────────────────
# Test 34 — fail-soft loader: missing/corrupt file -> None -> honest unavailable
# state, never an exception.
# ─────────────────────────────────────────────────────────────────────────────
def test_34_loader_is_fail_soft_on_a_missing_file(tmp_path):
    assert load_intel_brief(tmp_path) is None  # tmp_path has no site/ at all


def test_34_loader_is_fail_soft_on_a_corrupt_file(tmp_path):
    (tmp_path / "site").mkdir()
    (tmp_path / "site" / "options_intel_brief.json").write_text("{not json", encoding="utf-8")
    assert load_intel_brief(tmp_path) is None


def test_34_loader_reads_a_valid_file_verbatim(tmp_path):
    (tmp_path / "site").mkdir()
    payload = _brief(opportunities=[_card("AAPL", direction="LONG", r=344)])
    (tmp_path / "site" / "options_intel_brief.json").write_text(json.dumps(payload), encoding="utf-8")
    loaded = load_intel_brief(tmp_path)
    assert loaded == payload


def test_34_missing_artifact_renders_the_unavailable_state_with_no_exception():
    page = render(REPO, stores=dict(EMPTY_STORES), intel_brief=None)  # must not raise
    ws = _workspace(page)
    assert 'id="aib"' in ws
    assert "No options intelligence brief is available for this close." in ws
    assert "本次收盘暂无期权情报简报。" in ws
    assert "oew-aib-card" not in ws  # no cards fabricated for a missing artifact


# ─────────────────────────────────────────────────────────────────────────────
# Test 35 — pass-through: cards render in the artifact's own order with their
# own values, never re-ranked or re-labelled.
# ─────────────────────────────────────────────────────────────────────────────
def test_35_adapter_passes_cards_through_unmodified():
    cards = [
        _card("AAPL", direction="LONG", r=610, band="firm", oi=0.9, skew=0.8, es=0.95),
        _card("MSFT", direction="SHORT", r=410, band="moderate", oi=-0.6, skew=-0.55, es=0.6),
        _card("NVDA", direction="VOLATILITY", r=260, band="tentative", oi=0.1, skew=-0.05, es=0.3),
    ]
    brief = _brief(opportunities=cards, overflow=2)
    page = render(REPO, stores=dict(EMPTY_STORES), intel_brief=brief)
    ws = _workspace(page)

    # order is EXACTLY the artifact's own opportunities[] order
    assert _sym_order(ws) == ["AAPL", "MSFT", "NVDA"]

    # state labels come verbatim from display_state_en/zh — never re-derived
    assert "Upside evidence" in ws and "上行证据" in ws
    assert "Downside evidence" in ws and "下行证据" in ws

    # overflow count is verbatim
    # AD-1 B5 footer amendment (contract §5a/§3c) added a data-tip-en/zh pair to
    # this same span (disambiguates the two overflow counts) — match the class
    # regardless of what other attributes now sit between it and the `>`.
    assert re.search(r'class="oew-aib-more"[^>]*>\s*2\b', ws), "opportunities_overflow=2 not rendered verbatim"


def test_35_glyph_signs_are_read_not_recomputed():
    """AAPL's Q_oi/Q_skew are both positive -> both legs up-arrow, aligned.
    MSFT's are both negative -> both legs down-arrow, aligned. Sign is read
    straight off the artifact's own evidence[] value, nothing thresholded."""
    cards = [
        _card("AAPL", direction="LONG", r=610, oi=0.9, skew=0.8),
        _card("MSFT", direction="SHORT", r=410, oi=-0.6, skew=-0.55),
    ]
    page = render(REPO, stores=dict(EMPTY_STORES), intel_brief=_brief(opportunities=cards))
    ws = _workspace(page)
    aapl_card = ws[ws.index('>AAPL<'):ws.index('>MSFT<')]
    msft_card = ws[ws.index('>MSFT<'):]
    assert 'leg leg-oi up' in aapl_card and 'leg leg-skew up' in aapl_card
    assert 'leg leg-oi down' in msft_card and 'leg leg-skew down' in msft_card
    assert "aligned" in aapl_card and "一致" in aapl_card


# ─────────────────────────────────────────────────────────────────────────────
# Test 36 — an absent brief must not break the legacy Workspace: every
# pre-existing mode container still renders when intel_brief=None.
# ─────────────────────────────────────────────────────────────────────────────
def test_36_missing_brief_does_not_break_the_legacy_workspace():
    page = render(REPO, stores=_stores(), intel_brief=None)
    for mode in MODES:
        assert f'id="mode-{mode}"' in page, f"missing legacy mode container: {mode}"
        assert f'data-mode="{mode}"' in page
    assert 'class="oew-mode active" id="mode-brief"' in page
    ctx = build_context(REPO, _stores(), None)
    assert ctx["aib"]["available"] is False
    # the legacy session/posture/etc context is untouched
    assert ctx["session"]["date"] == "2026-07-24" or ctx["session"]["date"] is not None


# ─────────────────────────────────────────────────────────────────────────────
# Test 37 — server-render parity: card count/order/state labels/R values in
# the detail tier exactly match the fixture artifact.
# ─────────────────────────────────────────────────────────────────────────────
def test_37_card_count_order_state_and_priority_score_match_the_artifact():
    cards = [
        _card("TSLA", direction="LONG", r=555, band="firm"),
        _card("META", direction="RISK_ONLY", r=280, band="tentative", crowding={"fired": ["c1"], "severity": 0.9}),
    ]
    brief = _brief(opportunities=cards)
    page = render(REPO, stores=dict(EMPTY_STORES), intel_brief=brief)
    ws = _workspace(page)

    assert ws.count('class="oew-aib-card') == 2
    assert _sym_order(ws) == ["TSLA", "META"]

    # research_priority_score (R) appears verbatim in the detail tier for each card
    assert re.search(r'Priority score.*?<span class="v mono">\s*555\s*</span>', ws, re.S)
    assert re.search(r'Priority score.*?<span class="v mono">\s*280\s*</span>', ws, re.S)

    # state labels are the artifact's own display_state_en/zh, verbatim
    tsla = ws[ws.index('>TSLA<'):ws.index('>META<')]
    meta = ws[ws.index('>META<'):]
    assert "Upside evidence" in tsla
    assert "Risk / crowding" in meta and "风险/拥挤" in meta
    assert "Crowded tape" in meta  # crowding chip present because card.crowding is truthy


def test_37_band_word_is_the_artifacts_own_confidence_band_verbatim():
    cards = [_card("AMD", direction="LONG", r=300, band="tentative")]
    page = render(REPO, stores=dict(EMPTY_STORES), intel_brief=_brief(opportunities=cards))
    ws = _workspace(page)
    assert 'oew-aib-band band-tentative' in ws
    assert "Tentative" in ws and "初步" in ws


# ─────────────────────────────────────────────────────────────────────────────
# Test 38 — the generated site/options.html places the Brief board BEFORE the
# What-changed panel (design spec: FIRST child of #mode-brief).
# ─────────────────────────────────────────────────────────────────────────────
def test_38_generated_site_page_orders_the_board_before_what_changed():
    site_page = (REPO / "site" / "options.html")
    if not site_page.exists():
        pytest.skip("site/options.html not generated in this checkout")
    html = site_page.read_text(encoding="utf-8")
    assert 'id="aib"' in html, "AD-1 board id=\"aib\" missing from the generated page"
    assert "What changed" in html
    assert html.index('id="aib"') < html.index("What changed"), (
        "AD-1 board must render BEFORE the What-changed panel"
    )


def test_38_board_is_the_first_child_of_mode_brief():
    page = render(REPO, stores=dict(EMPTY_STORES), intel_brief=_brief())
    marker = '<section class="oew-mode active" id="mode-brief" role="tabpanel" aria-labelledby="tab-brief">'
    idx = page.index(marker) + len(marker)
    tail = page[idx:idx + 1200]
    # the very next non-whitespace, non-comment content is the AD-1 panel
    stripped = re.sub(r"<!--.*?-->", "", tail, flags=re.S).strip()
    assert stripped.startswith('<div class="oew-panel oew-aib" id="aib">')


# ─────────────────────────────────────────────────────────────────────────────
# Test 39 — Scanner/Ticker/Leaders markup is BYTE-IDENTICAL to a pre-change
# snapshot: this packet's OWNED FILES are scoped to #mode-brief only.
# ─────────────────────────────────────────────────────────────────────────────
_SNAPSHOT_HASHES = {
    "mode-scanner": "11b87776c8bee03ac18c5a01cd1ea995510986dc557a479fed229e48a9bd90cf",
    "mode-ticker": "d18066a721fb6f0ecbf17936f9104b5b1c6ce5a11bb608c635414d1762fe3dc5",
    "mode-leaders": "5e09876f830fc2e201237f53eddf6afa6e94aec2f13e36113a3fe3acb84506c1",
}


def _extract_section(page: str, mode_id: str) -> str:
    marker = f'<section class="oew-mode" id="{mode_id}"'
    start = page.index(marker)
    end = page.index("</section>", start) + len("</section>")
    return page[start:end]


@pytest.mark.parametrize("mode_id", sorted(_SNAPSHOT_HASHES))
def test_39_scanner_ticker_leaders_markup_is_byte_identical_to_snapshot(mode_id):
    page = render(REPO, stores=dict(EMPTY_STORES), intel_brief=None)
    block = _extract_section(page, mode_id)
    digest = hashlib.sha256(block.encode("utf-8")).hexdigest()
    assert digest == _SNAPSHOT_HASHES[mode_id], (
        f"{mode_id} markup changed — this packet's scope is #mode-brief only; "
        f"got {digest}"
    )


def test_39_scanner_ticker_leaders_tabs_and_ids_still_present():
    page = render(REPO, stores=dict(EMPTY_STORES), intel_brief=_brief(opportunities=[_card("AAPL", direction="LONG", r=300)]))
    for mode in ("scanner", "ticker", "leaders"):
        assert f'id="mode-{mode}"' in page
        assert f'data-mode="{mode}"' in page


# ─────────────────────────────────────────────────────────────────────────────
# Test 40 — no client-side recomputation: the board ships no new JS, and
# numeric fields render VERBATIM from the artifact (pip count / move %).
# ─────────────────────────────────────────────────────────────────────────────
def test_40_board_adds_no_script_content():
    page = render(REPO, stores=dict(EMPTY_STORES), intel_brief=_brief(opportunities=[_card("AAPL", direction="LONG", r=300)]))
    for m in re.finditer(r"<script\b.*?</script>", page, re.S | re.I):
        body = m.group(0)
        for needle in ("oew-aib", "evidence_strength", "Q_oi", "Q_skew", "research_priority_score"):
            assert needle not in body, f"AD-1 board leaked scoring identifier '{needle}' into client JS"


def test_40_pip_count_is_the_verbatim_linear_encoding_of_evidence_strength():
    """The contract's own formula (design spec): pips = round(evidence_strength*5).
    Recomputed independently here (not via the adapter's _pips) so a drift in the
    adapter's own encoding would be caught, not rubber-stamped."""
    card = _card("AAPL", direction="LONG", r=300, es=0.82)
    page = render(REPO, stores=dict(EMPTY_STORES), intel_brief=_brief(opportunities=[card]))
    ws = _workspace(page)
    expected_on = round(0.82 * 5)
    meter = ws[ws.index('oew-aib-meter'):ws.index('oew-aib-band')]
    assert meter.count('class="oew-pip on"') == expected_on


def test_40_move_pct_is_the_verbatim_unit_conversion_of_the_artifact_fraction():
    card = _card("AAPL", direction="LONG", r=300)
    card["market_implied_move_pct"] = 0.0413
    page = render(REPO, stores=dict(EMPTY_STORES), intel_brief=_brief(opportunities=[card]))
    ws = _workspace(page)
    assert "±4.1%" in ws  # 0.0413 * 100, rounded to 1dp — a unit conversion, not a score


def test_40_null_move_pct_renders_no_implied_move_chip():
    """A null market_implied_move_pct must render NO ± chip — never a fabricated
    0% (contract: null | float, no synthetic default)."""
    card = _card("AAPL", direction="LONG", r=300)
    card["market_implied_move_pct"] = None
    page = render(REPO, stores=dict(EMPTY_STORES), intel_brief=_brief(opportunities=[card]))
    ws = _workspace(page)
    facts = ws[ws.index('oew-aib-facts'):ws.index('oew-aib-chips')]
    assert "±" not in facts
    assert "implied" not in facts


# ═════════════════════════════════════════════════════════════════════════════
# AD-1 B5 (product exposure) — the accepted design packet's three added bands
# inside #aib: directional watch (2), evidence rail (3), control (4).
# contracts/options/OPTIONS_INTEL_BRIEF_V1.md §5a.
#
# Reuses this file's own `_card()`/`_brief()`/`EMPTY_STORES`/`render` — a
# SEPARATE `_b5_*` fixture family only where the B5 bands need fields `_card()`
# doesn't carry (board_rank, event, crowding shaped for the rail, the
# directional_watch/event_board/risk_warnings/no_signal_exemplar top-level
# arrays `_brief()` always leaves empty).
# ═════════════════════════════════════════════════════════════════════════════

_B5_DISPLAY_STATE = {
    "LONG": ("Upside evidence", "上行证据"), "SHORT": ("Downside evidence", "下行证据"),
    "VOLATILITY": ("Volatility", "波动率"), "RISK_ONLY": ("Risk / crowding", "风险/拥挤"),
}


def _b5_opp_card(symbol: str, rank: int, *, direction: str = "VOLATILITY",
                  crowding: dict | None = None, event: dict | None = None) -> dict:
    """A Band-1 grid card carrying `board_rank` (contract §5a) — `_card()` above
    predates B5 and never sets it; the B5 bands need it wired through."""
    c = _card(symbol, direction=direction, r=900 - rank * 10, crowding=crowding)
    c["board_rank"] = rank
    c["event"] = event
    en, zh = _B5_DISPLAY_STATE[direction]
    c["display_state_en"], c["display_state_zh"] = en, zh
    return c


def _b5_brief(*, opportunities=None, watch=None, watch_overflow=0, qualified_count=None,
              events=None, events_overflow=0, risks=None, risks_overflow=0,
              control_exemplar=None, board_state="OK", **kwargs) -> dict:
    opportunities = opportunities or []
    brief = _brief(opportunities=opportunities, board_state=board_state, **kwargs)
    brief["directional_watch"] = watch or []
    brief["directional_watch_overflow"] = watch_overflow
    brief["directional_qualified_count"] = (
        qualified_count if qualified_count is not None else len(brief["directional_watch"])
    )
    brief["event_board"] = events or []
    brief["event_board_overflow"] = events_overflow
    brief["risk_warnings"] = risks or []
    brief["risk_board_overflow"] = risks_overflow
    brief["no_signal_exemplar"] = control_exemplar
    return brief


def _b5_healthy_with_cards_brief() -> dict:
    """Scene A — grid + watch + populated rails + control (design packet §2A)."""
    cards = [_b5_opp_card(sym, i + 1) for i, sym in enumerate(["COST", "CSCO", "SPY", "QQQ", "TSLA", "IBM"])]
    cards[3]["event"] = {"event_date": "2026-08-21", "event_premium_state": "HIGH"}       # QQQ, rank 4
    cards[4]["crowding"] = {"fired": ["c1", "c2"], "severity": 0.9}                        # TSLA, rank 5
    watch = [   # deliberately NOT ascending — proves array order is preserved, never re-sorted
        {"board_rank": 12, "symbol": "MU", "direction": "LONG"},
        {"board_rank": 7, "symbol": "AMD", "direction": "LONG"},
        {"board_rank": 9, "symbol": "XOM", "direction": "SHORT"},
    ]
    events = [
        # F6 (2026-08-18): the event rail's OWN move figure lives inside `event.
        # event_implied_move_pct` — a card-level `market_implied_move_pct` (0.041,
        # the unchanged 5-session read every _b5_opp_card carries) is ALSO present
        # here to prove the two are read from genuinely different fields, never
        # conflated.
        {"symbol": "QQQ", "event": {"event_date": "2026-08-21", "event_premium_state": "HIGH",
                                     "event_implied_move_pct": 0.08},
         "market_implied_move_pct": 0.041, "board_rank": 4, "null_reason": None},
        {"symbol": "LLY", "event": {"event_date": "2026-08-25", "event_premium_state": "NORMAL",
                                     "event_implied_move_pct": 0.05},
         "market_implied_move_pct": 0.041, "board_rank": None, "null_reason": None},
        {"symbol": "ORCL", "event": {"event_date": "2026-09-02", "event_premium_state": "LOW",
                                      "event_implied_move_pct": 0.04},
         "market_implied_move_pct": 0.041, "board_rank": None, "null_reason": None},
    ]
    risks = [
        {"symbol": "TSLA", "crowding": {"fired": ["c1", "c2"], "severity": 0.9}, "board_rank": 5, "null_reason": None},
        {"symbol": "NFLX", "crowding": {"fired": ["c2"], "severity": 0.6}, "board_rank": None, "null_reason": None},
        {"symbol": "SMCI", "crowding": {"fired": ["c3"], "severity": 0.5}, "board_rank": None, "null_reason": None},
        {"symbol": "COIN", "crowding": {"fired": ["c1"], "severity": 0.7}, "board_rank": None, "null_reason": None},
    ]
    return _b5_brief(
        opportunities=cards, overflow=5,
        watch=watch, watch_overflow=2, qualified_count=5,
        events=events, events_overflow=1,
        risks=risks, risks_overflow=0,
        control_exemplar={"symbol": "NVDA", "no_signal_reason": {
            "en": "both readings are inside their normal range", "zh": "两项读数均在正常区间内"}},
    )


def _b5_healthy_quiet_brief(*, events: list | None = None, unknown_calendar: bool = False) -> dict:
    """Scene B — no cards, no directional watch, but the rails may still speak."""
    exemplar = {
        "symbol": "NVDA",
        "no_signal_reason": {"en": "both readings are inside their normal range", "zh": "两项读数均在正常区间内"},
        "null_reason": ("EVENT_STATE_UNKNOWN" if unknown_calendar else None),
    }
    return _b5_brief(
        opportunities=[], watch=[], watch_overflow=0, qualified_count=0,
        events=(events or []), events_overflow=0, risks=[], risks_overflow=0,
        control_exemplar=exemplar, board_state="NO_SIGNAL", eligible=368, present=372,
    )


def _b5_degraded_brief() -> dict:
    """Scene C — STALE_SOURCE; byte-silhouette must match the pre-B5 shape."""
    return _b5_brief(opportunities=[], watch=[], qualified_count=0, board_state="STALE_SOURCE",
                      eligible=0, present=0)


def _aib_section(page: str) -> str:
    """Slice out just the `#aib` panel's markup (up to the next sibling panel
    start) — narrower than this file's own `_workspace()`, which returns the
    whole `.oew` shell — so band-order/vocabulary assertions can't accidentally
    match unrelated page furniture."""
    start = page.index('id="aib"')
    end = page.index('oew-panel', start + 20)
    return page[start:end]


def _order_ok(haystack: str, *needles: str) -> bool:
    positions = [haystack.index(n) for n in needles]
    return positions == sorted(positions)


# ─────────────────────────────────────────────────────────────────────────────
# Band ordering.
# ─────────────────────────────────────────────────────────────────────────────


def test_b5_band_order_healthy_with_cards():
    page = render(REPO, stores=dict(EMPTY_STORES), intel_brief=_b5_healthy_with_cards_brief())
    sec = _aib_section(page)
    assert _order_ok(sec, "oew-aib-grid", "oew-aib-watch", "oew-aib-rail", "oew-aib-control", "oew-pfoot")


def test_b5_band_order_healthy_quiet_with_rails_speaking():
    page = render(REPO, stores=dict(EMPTY_STORES), intel_brief=_b5_healthy_quiet_brief())
    sec = _aib_section(page)
    # Band 1 empty -> .oew-aib-empty; Band 2 empty+qualified==0 -> null line;
    # Band 3/4 still speak; order must still hold.
    assert _order_ok(sec, "oew-aib-empty", "oew-aib-wnull", "oew-aib-rail", "oew-aib-control", "oew-pfoot")


def test_b5_degraded_scene_never_shows_bands_2_3_4():
    page = render(REPO, stores=dict(EMPTY_STORES), intel_brief=_b5_degraded_brief())
    sec = _aib_section(page)
    assert "oew-aib-degraded" in sec
    for marker in ("oew-aib-grid", "oew-aib-watch", "oew-aib-wnull", "oew-aib-rail", "oew-aib-control"):
        assert marker not in sec, f"{marker} must never render on a degraded scene"
    assert _order_ok(sec, "oew-aib-stamps", "oew-aib-degraded", "oew-pfoot")


# ─────────────────────────────────────────────────────────────────────────────
# Band 1 — machine board_rank, never loop.index.
# ─────────────────────────────────────────────────────────────────────────────


def test_b5_band1_grid_uses_machine_board_rank_not_loop_index():
    """Feed opportunities in the array's natural order but with board_rank
    values that DISAGREE with loop position — the strongest proof the template
    reads `c.board_rank`, never `loop.index` (the exact hole this closes)."""
    brief = _b5_healthy_with_cards_brief()
    for i, c in enumerate(brief["opportunities"]):
        c["board_rank"] = 100 + i   # loop.index would print 1..6; assert it does NOT
    page = render(REPO, stores=dict(EMPTY_STORES), intel_brief=brief)
    sec = _aib_section(page)
    for i in range(6):
        assert f"№{100 + i}" in sec
    assert "№1<" not in sec and "№2<" not in sec


# ─────────────────────────────────────────────────────────────────────────────
# Band 2 — directional watch: real gapped ordinals, array order preserved.
# ─────────────────────────────────────────────────────────────────────────────


def test_b5_band2_watch_prints_real_gapped_ordinals_in_array_order():
    page = render(REPO, stores=dict(EMPTY_STORES), intel_brief=_b5_healthy_with_cards_brief())
    sec = _aib_section(page)
    assert "№12" in sec and "№7" in sec and "№9" in sec
    assert "Qualified below the cut" in sec
    assert _order_ok(sec, "MU", "AMD", "XOM")   # array order [12,7,9] — not sorted ascending
    assert "Upside" in sec and "Downside" in sec
    assert "+2" in sec   # directional_watch_overflow


def test_f10_watch_row_refuses_unexpected_direction_never_fabricates_upside(capsys):
    """F10 (2026-08-18): a directional_watch row carrying a direction other than
    LONG/SHORT (a producer/adapter contract mismatch — this array is supposed to
    carry LONG/SHORT exclusively) must be OMITTED, never rendered as a fabricated
    "Upside" (the pre-fix `.get(direction, ...LONG...)` fallback). One
    ::warning-style annotation is emitted for the omitted row; the lawful rows
    around it still render, array order preserved."""
    brief_payload = _b5_healthy_with_cards_brief()
    brief_payload["directional_watch"] = [
        {"board_rank": 7, "symbol": "AMD", "direction": "LONG"},
        {"board_rank": 8, "symbol": "GLITCH", "direction": "VOLATILITY"},   # unexpected
        {"board_rank": 9, "symbol": "XOM", "direction": "SHORT"},
    ]
    page = render(REPO, stores=dict(EMPTY_STORES), intel_brief=brief_payload)
    sec = _aib_section(page)
    assert "AMD" in sec and "XOM" in sec
    assert "GLITCH" not in sec, "unexpected-direction row rendered instead of being omitted"
    assert _order_ok(sec, "AMD", "XOM")

    out = capsys.readouterr().out
    lines = [ln for ln in out.splitlines() if "GLITCH" in ln]
    assert lines, "no annotation emitted for the omitted row"
    assert lines[0].startswith("::warning"), \
        "annotation must START the line for GitHub to surface it (house law) — " \
        f"got: {lines[0]!r}"
    assert "VOLATILITY" in lines[0]


def test_b5_band2_omitted_when_watch_empty_but_qualified_positive():
    """§6: empty strip AND directional_qualified_count>0 -> band OMITTED
    entirely (not even the null line) — the six cards above already contain
    directional names."""
    brief = _b5_healthy_with_cards_brief()
    brief["directional_watch"] = []
    brief["directional_watch_overflow"] = 0
    brief["directional_qualified_count"] = 3   # positive, but nothing below the cut
    page = render(REPO, stores=dict(EMPTY_STORES), intel_brief=brief)
    sec = _aib_section(page)
    assert "oew-aib-watch" not in sec
    assert "Qualified below the cut" not in sec
    assert "No upside or downside hypothesis qualified today." not in sec


def test_b5_band2_null_line_when_qualified_count_is_zero():
    page = render(REPO, stores=dict(EMPTY_STORES), intel_brief=_b5_healthy_quiet_brief())
    sec = _aib_section(page)
    assert "oew-aib-wnull" in sec
    assert "No upside or downside hypothesis qualified today." in sec
    assert "oew-aib-watch\"" not in sec   # the populated-strip container itself is absent


# ─────────────────────────────────────────────────────────────────────────────
# Band 3 — evidence rail (event + risk groups).
# ─────────────────────────────────────────────────────────────────────────────


def test_b5_band3_event_rail_populated_with_backref_and_without():
    page = render(REPO, stores=dict(EMPTY_STORES), intel_brief=_b5_healthy_with_cards_brief())
    sec = _aib_section(page)
    assert "Ahead of an event" in sec
    assert "Priced above event peers" in sec    # QQQ, HIGH
    assert "In line with event peers" in sec    # LLY, NORMAL
    assert "Priced below event peers" in sec    # ORCL, LOW
    assert "№4" in sec and "above" in sec       # QQQ's back-ref to Band 1
    assert "+1" in sec                          # events_overflow


def test_f6_event_rail_move_pct_reads_event_implied_move_never_card_level():
    """F6 (2026-08-18): the event rail's ± figure must come from
    `event.event_implied_move_pct` (QQQ's fixture value 0.08 -> "±8.0%"), never
    the card-level `market_implied_move_pct` (0.041 -> "±4.1%", which every
    _b5_opp_card ALSO carries, hence legitimately appears in the Band-1 grid) —
    the two coexist in the fixture specifically so a regression back to the old
    field would print the wrong number. Scoped to just the event-rail slice (not
    the whole #aib panel) since ±4.1% is EXPECTED to appear in the grid cards."""
    page = render(REPO, stores=dict(EMPTY_STORES), intel_brief=_b5_healthy_with_cards_brief())
    sec = _aib_section(page)
    assert "±4.1%" in sec, "sanity: the card-level move should still render in the grid"
    rail_start = sec.index("Ahead of an event")
    rail_end = sec.index("Crowded tape", rail_start)
    event_rail = sec[rail_start:rail_end]
    assert "±8.0%" in event_rail    # QQQ event_implied_move_pct
    assert "±5.0%" in event_rail    # LLY event_implied_move_pct
    assert "±4.0%" in event_rail    # ORCL event_implied_move_pct
    assert "±4.1%" not in event_rail, "event rail printed the card-level 5-session move, not its own event-horizon figure"


def test_f10_event_tooltip_claim_scoped_to_event_moves_not_the_crowding_copy():
    """F10 (2026-08-18): the event-rail tooltip's "never says X is cheap or
    expensive" claim must be scoped to an EVENT move specifically (EN "...an event
    move is cheap or expensive.") — the OLD unscoped wording ("...a move is cheap
    or expensive.") contradicted the crowding rail's own tooltip, which
    legitimately calls options "costly" (c2 leg, "Expensive options at a high") a
    few lines below on the SAME panel."""
    page = render(REPO, stores=dict(EMPTY_STORES), intel_brief=_b5_healthy_with_cards_brief())
    sec = _aib_section(page)
    assert "it never says an event move is cheap or expensive" in sec
    assert "绝不表示某次事件变动是便宜还是昂贵" in sec
    # the crowding rail's own "costly options" language coexists without contradiction
    assert "options costly while price sits at a high" in sec


def test_b5_band3_event_rail_empty_causes_never_collapse():
    none_page = render(REPO, stores=dict(EMPTY_STORES), intel_brief=_b5_healthy_quiet_brief())
    none_sec = _aib_section(none_page)
    assert "No name has an event inside the window." in none_sec

    unknown_page = render(REPO, stores=dict(EMPTY_STORES), intel_brief=_b5_healthy_quiet_brief(unknown_calendar=True))
    unknown_sec = _aib_section(unknown_page)
    assert "Event calendar not loaded" in unknown_sec
    assert "No name has an event inside the window." not in unknown_sec


def test_b5_band3_event_rail_shows_populated_rows_on_the_quiet_scene():
    """Design packet §2 Scene B / §6: the rails may still speak even though
    Band 1's grid and Band 2's strip are both empty."""
    events = [{"symbol": "LLY", "event": {"event_date": "2026-08-25", "event_premium_state": "NORMAL",
                                           "event_implied_move_pct": 0.05},
               "market_implied_move_pct": 0.041, "board_rank": None, "null_reason": None}]
    page = render(REPO, stores=dict(EMPTY_STORES), intel_brief=_b5_healthy_quiet_brief(events=events))
    sec = _aib_section(page)
    assert "oew-aib-empty" in sec
    assert "oew-aib-wnull" in sec
    assert "LLY" in sec and "In line with event peers" in sec


def test_b5_band3_risk_rail_populated_and_empty():
    page = render(REPO, stores=dict(EMPTY_STORES), intel_brief=_b5_healthy_with_cards_brief())
    sec = _aib_section(page)
    assert "Crowded tape" in sec
    assert "Same-day bets crowded" in sec
    assert "Expensive options at a high" in sec
    assert "Busy and expensive for days" in sec
    assert "№5" in sec   # TSLA back-ref

    quiet_page = render(REPO, stores=dict(EMPTY_STORES), intel_brief=_b5_healthy_quiet_brief())
    quiet_sec = _aib_section(quiet_page)
    assert "Nothing looks crowded today." in quiet_sec


def test_b5_band3_rail_slot_stability_both_groups_render_even_when_both_empty():
    brief = _b5_healthy_quiet_brief(unknown_calendar=True)
    brief["risk_warnings"] = []
    page = render(REPO, stores=dict(EMPTY_STORES), intel_brief=brief)
    sec = _aib_section(page)
    assert "oew-aib-rail" in sec
    assert "Ahead of an event" in sec and "Crowded tape" in sec


# ─────────────────────────────────────────────────────────────────────────────
# Band 4 — control.
# ─────────────────────────────────────────────────────────────────────────────


def test_b5_band4_control_populated_and_empty():
    page = render(REPO, stores=dict(EMPTY_STORES), intel_brief=_b5_healthy_with_cards_brief())
    sec = _aib_section(page)
    assert "oew-aib-control" in sec
    assert "NVDA" in sec
    assert "both readings are inside their normal range" in sec

    brief = _b5_healthy_quiet_brief()
    brief["no_signal_exemplar"] = None
    page2 = render(REPO, stores=dict(EMPTY_STORES), intel_brief=brief)
    sec2 = _aib_section(page2)
    assert "no fully covered quiet name today." in sec2


# ─────────────────────────────────────────────────────────────────────────────
# Panel-level amendments (§3c): subtitle, chip order, footer disambiguation tip.
# ─────────────────────────────────────────────────────────────────────────────


def test_b5_panel_subtitle_describes_the_new_composition():
    page = render(REPO, stores=dict(EMPTY_STORES), intel_brief=_b5_healthy_with_cards_brief())
    assert "ranked priorities, event and crowding reads, and one quiet control" in page
    assert "优先级排序、事件与拥挤读数，以及一个平静对照" in page


def test_b5_prophet_chip_sits_after_crowding_chip_in_the_card():
    page = render(REPO, stores=dict(EMPTY_STORES), intel_brief=_b5_healthy_with_cards_brief())
    sec = _aib_section(page)
    # TSLA (rank 5) is the only card carrying crowding=True — locate ITS OWN
    # chips row (nearest preceding "oew-aib-chips" opener) rather than the
    # first card's, which has no crowding chip at all.
    crowd_pos = sec.index("oew-aib-crowd")
    chips_start = sec.rfind("oew-aib-chips", 0, crowd_pos)
    assert chips_start != -1
    prophet_pos = sec.index("oew-aib-prophet", chips_start)
    assert chips_start < crowd_pos < prophet_pos


def test_b5_footer_overflow_disambiguation_tip_present():
    page = render(REPO, stores=dict(EMPTY_STORES), intel_brief=_b5_healthy_with_cards_brief())
    sec = _aib_section(page)
    assert "Counts every direction above the threshold, including volatility names." in sec
    assert "统计门槛之上的全部方向，含波动率名称。" in sec


# ─────────────────────────────────────────────────────────────────────────────
# Vocabulary / a11y hygiene on the NEW copy specifically (contract §5 banned list).
# ─────────────────────────────────────────────────────────────────────────────

_B5_BANNED_GLANCE_TOKENS = [
    "probability", "alpha", "edge", "asymmetry", "target", "buy-now", "sell-now",
    "validated", "NO_SIGNAL", "EVENT_STATE_UNKNOWN", "Q_oi", "Q_skew", "F_E",
]


def _b5_strip_tags(html_fragment: str) -> str:
    """Inner text only — attributes (incl. data-tip-*, the sanctioned Tier-2
    home for more technical language) are stripped along with their tags."""
    return re.sub(r"<[^>]+>", " ", html_fragment)


def test_b5_new_copy_carries_no_banned_glance_vocabulary():
    """Scoped to `oew-pbody` onward — the panel HEAD carries pre-existing,
    already-reviewed honesty copy ("not a probability or trade signal") that
    legitimately contains a banned token in a negation; that copy is outside
    this packet's scope. Bands 1-4 + the footer are the new/amended surface."""
    page = render(REPO, stores=dict(EMPTY_STORES), intel_brief=_b5_healthy_with_cards_brief())
    sec = _aib_section(page)
    body_start = sec.index("oew-pbody")
    glance_text = _b5_strip_tags(sec[body_start:])
    hits = {tok: glance_text.count(tok) for tok in _B5_BANNED_GLANCE_TOKENS if tok in glance_text}
    assert not hits, f"banned vocabulary leaked into glance-tier text: {hits}"
    for raw in ("c1", "c2", "c3"):
        assert raw not in glance_text


def test_b5_no_translated_text_in_a_title_attribute():
    page = render(REPO, stores=dict(EMPTY_STORES), intel_brief=_b5_healthy_with_cards_brief())
    sec = _aib_section(page)
    for m in re.finditer(r'title="([^"]*)"', sec):
        assert not re.search(r"[一-鿿]", m.group(1)), f"zh text in title=: {m.group(1)!r}"


# Zero horizontal overflow is verified visually (verify_shots/, scripted check
# in the shoot script) — not re-derived here; this suite is markup/copy-level.
