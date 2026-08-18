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
    assert re.search(r'class="oew-aib-more">\s*2\b', ws), "opportunities_overflow=2 not rendered verbatim"


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
