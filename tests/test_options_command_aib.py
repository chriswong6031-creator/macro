"""tests/test_options_command_aib.py — A-F03-W2-2 AD-1 glance-tier lede.

Contract (BINDING): packet A-F03-W2-2 (frozen design spec, ledger row
MO-PAID-010) — the AD-1 Daily Brief panel gets a glance-tier "lede" block
(headline, stance, freshness) promoted above the existing evidence tier.

House rule this suite exists to prove: `build_aib()` stays a PASS-THROUGH
adapter — every lede/freshness string is a closed-vocabulary lookup keyed on
the payload's OWN `board_state` and `len(cards)`, never a score, rank or
generated sentence. Each test builds the REAL context from a fixture payload
and renders the REAL `options.html.j2` template, then asserts on the
rendered HTML — asserting on the dict alone would prove the adapter, not the
surface this packet ships.

Run: python3 -m pytest tests/test_options_command_aib.py -q
"""
from __future__ import annotations

import re
import sys
from datetime import datetime, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from scripts.build_options_command import build_aib, render  # noqa: E402

from tests.test_build_options_command import EMPTY_STORES  # noqa: E402

# Fixed render clock — Friday 2026-09-04, 22:00 UTC (18:00 ET, after the
# close+settle cutoff) -> nyse_calendar.expected_last_session(NOW) ==
# 2026-09-04, so an as_of of that same Friday close is genuinely CURRENT
# (0 sessions behind). A brief carrying the PRIOR session (Thursday
# 2026-09-03) is then correctly "1 day behind" — trading-session math, not
# calendar-day math (Major finding, review of PR #6932: calendar-day math
# mislabelled the freshest possible close as "behind"). No wall-clock read
# anywhere in this file.
NOW = datetime(2026, 9, 4, 22, 0, tzinfo=timezone.utc)


def _brief(*, board_state="OK", board_reason=None, opportunities=None,
           eligible=10, present=20, as_of="2026-09-03", oi_counted="2026-09-03",
           receipt_id="e5bd3f474eabff7904574b8c8abccd1d45f1bb57210eac2d4073e61915ad51",
           built_at_utc="2026-09-06T05:12:44Z") -> dict:
    return {
        "schema": "options.intel_brief/v1", "model_version": "intel_brief_heuristic/v1.2",
        "as_of_session": as_of, "oi_counted_date": oi_counted,
        "pending_session": None,
        "eligibility": {"present": present, "eligible": eligible,
                        "insufficient_history": 0, "insufficient_coverage": 0},
        "board_state": board_state, "board_reason": board_reason,
        "receipt_id": receipt_id,
        "built_at_utc": built_at_utc,
        "opportunities": opportunities or [],
        "opportunities_overflow": 0,
        "event_board": [], "risk_warnings": [], "no_signal_exemplar": None,
    }


def _card(symbol: str, *, direction: str = "LONG", r: int = 1) -> dict:
    return {
        "signal_id": f"adib:v1.2:2026-09-05:{symbol}",
        "symbol": symbol, "canonical_instrument_id": f"US:{symbol}",
        "direction": direction,
        "display_state_en": "Upside evidence", "display_state_zh": "上行证据",
        "horizon": "next_5_sessions",
        "evidence_strength": 0.7, "evidence_confidence": 0.5, "evidence_confidence_band": "moderate",
        "research_priority_score": r,
        "why_now": [{"en": f"why-now for {symbol}", "zh": f"{symbol} 事实"}],
        "evidence": [
            {"name": "Q_oi", "value": 0.7, "history_n": 45, "observed_or_inferred": "inferred"},
            {"name": "Q_skew", "value": 0.5, "history_n": 18, "observed_or_inferred": "inferred"},
        ],
        "contradictions": [],
        "mechanics_context": {"gex_confirm_verdict": None, "gamma_regime": None, "flip_proximity": None},
        "crowding": None,
        "event": None,
        "market_implied_move_pct": 0.03,
        "trigger_watch": {"en": f"trigger {symbol}", "zh": f"{symbol} 触发"},
        "invalidation_watch": {"en": f"invalidation {symbol}", "zh": f"{symbol} 失效"},
        "fresh_until": "2026-09-08",
        "source_state": "ok",
        "prophet_state": "READY",
        "prophet_asof": "2026-09-05",
        "asymmetry_score": None, "asymmetry_state": "UNCALIBRATED",
        "probability_up": None, "probability_down": None, "expected_edge_bps": None,
        "board_rank": r,
    }


def _aib_panel(page: str) -> str:
    start = page.index('<div class="oew-panel oew-aib" id="aib"')
    # The next sibling top-level panel opens with '<div class="oew-panel">'
    end = page.index('<div class="oew-panel">', start)
    return page[start:end]


def _esc(s: str) -> str:
    """The template renders through an autoescape=True Jinja env — a literal
    apostrophe comes back as the numeric entity, exactly like every other
    apostrophe-bearing string already shipped on this page (e.g. the footer's
    "don't chase"). Assertions compare against the escaped form."""
    return s.replace("'", "&#39;")


def _strip_attrs(html: str) -> str:
    """Strip tag attributes so 'user-visible text' assertions never match a
    data-* attribute value (data-aib-state legitimately carries the slug)."""
    return re.sub(r"<([a-zA-Z0-9]+)\s[^>]*>", r"<\1>", html)


# ─────────────────────────────────────────────────────────────────────────────
def test_populated_lede_renders_headline_stance_and_freshness():
    brief = _brief(board_state="OK", as_of="2026-09-03",
                    opportunities=[_card("AAA", r=1), _card("BBB", r=2), _card("CCC", r=3)])
    page = render(REPO, stores=dict(EMPTY_STORES), intel_brief=brief, now=NOW)
    panel = _aib_panel(page)
    assert _esc("3 names are worth a look after today's close.") in panel
    assert "今日收盘后有 3 个名称值得关注。" in panel
    assert "1 day behind" in panel
    assert "落后 1 天" in panel
    lede_start = panel.index('class="oew-aib-lede')
    lede_end = panel.index("</div>", panel.index('class="oew-aib-fresh"'))
    lede = panel[lede_start:lede_end]
    assert 'class="oew-stance st-watch"' in lede


def test_populated_carries_readback_markers():
    brief = _brief(board_state="OK", as_of="2026-09-03",
                    opportunities=[_card("AAA", r=1)])
    page = render(REPO, stores=dict(EMPTY_STORES), intel_brief=brief, now=NOW)
    panel = _aib_panel(page)
    assert 'data-aib-state="OK"' in panel
    assert 'data-aib-asof="2026-09-03"' in panel
    m = re.search(r'data-aib-receipt="([0-9a-f]{12})"', panel)
    assert m is not None, panel
    assert 'data-aib-fresh="lagging"' in panel


def test_quiet_is_not_degraded():
    brief = _brief(board_state="NO_SIGNAL", opportunities=[])
    page = render(REPO, stores=dict(EMPTY_STORES), intel_brief=brief, now=NOW)
    panel = _aib_panel(page)
    assert "The options tape is quiet — nothing meets the bar today." in panel
    assert "oew-aib-degraded" not in panel
    assert "oew-aib-elig" in panel


def test_degraded_prints_plain_null_and_hides_eligibility():
    brief = _brief(board_state="STALE_SOURCE", opportunities=[])
    page = render(REPO, stores=dict(EMPTY_STORES), intel_brief=brief, now=NOW)
    panel = _aib_panel(page)
    assert _esc("Today's brief isn't ready yet.") in panel
    assert "oew-aib-elig" not in panel
    assert "oew-aib-degraded-why" in panel
    stamps_start = panel.index('class="oew-aib-stamps"')
    stamps_end = panel.index("</div>", stamps_start)
    assert "0/" not in panel[stamps_start:stamps_end]


def test_degraded_why_is_true_for_each_board_reason_not_one_hardcoded_line():
    """Major finding, review of PR #6932: templates/options.html.j2 used to
    render ONE hardcoded 'not counted yet' why-sentence under every degraded
    state, contradicting the state-specific headline directly above it on
    ELIGIBILITY_COLLAPSE / MIXED_VINTAGE / NO_SETTLED_OI_PAIR. The why line
    must vary with board_state/board_reason exactly like the headline does,
    and must never assert a counting delay when the true cause differs."""
    cases = [
        ("STALE_SOURCE", None, "holding the last good session"),
        ("DEGRADED", "ELIGIBILITY_COLLAPSE", "too few names cleared today's coverage bar"),
        ("DEGRADED", "MIXED_VINTAGE", "evidence dates on file disagree"),
        ("DEGRADED", "NO_SETTLED_OI_PAIR", "next position count has not settled"),
    ]
    seen = set()
    for board_state, board_reason, must_contain in cases:
        brief = _brief(board_state=board_state, board_reason=board_reason, opportunities=[])
        page = render(REPO, stores=dict(EMPTY_STORES), intel_brief=brief, now=NOW)
        panel = _aib_panel(page)
        assert _esc(must_contain) in panel, (board_state, board_reason, panel)
        assert "This is a data gap, not a quiet market" in panel
        why_start = panel.index('class="oew-aib-degraded-why"')
        why_end = panel.index("</p>", why_start)
        seen.add(panel[why_start:why_end])
    assert len(seen) == len(cases), "each board_reason must render a DISTINCT why sentence"


def test_missing_artifact_why_never_claims_a_counting_delay():
    """The None-artifact path cannot have counted anything — its why must
    not assert 'not counted yet' the way the old hardcoded line did."""
    page = render(REPO, stores=dict(EMPTY_STORES), intel_brief=None, now=NOW)
    panel = _aib_panel(page)
    assert "This is a data gap, not a quiet market" in panel
    assert "not been counted yet" not in panel
    assert "hasn&#39;t arrived yet" in panel or "hasn't arrived yet" in panel


def test_missing_artifact_renders_unavailable_not_empty():
    page = render(REPO, stores=dict(EMPTY_STORES), intel_brief=None, now=NOW)
    panel = _aib_panel(page)
    assert _esc("Today's brief isn't ready yet.") in panel
    assert 'data-aib-state="unavailable"' in panel
    assert "oew-aib-grid" not in panel


def test_friday_close_read_on_sunday_is_current_not_behind():
    """Major finding, review of PR #6932: calendar-day math labelled the
    freshest possible board 'behind'. Friday 2026-09-04's close, read on
    Sunday 2026-09-06, must be CURRENT — 0 completed sessions are missing."""
    brief = _brief(board_state="OK", as_of="2026-09-04", opportunities=[_card("AAA")])
    sunday = datetime(2026, 9, 6, 12, 0, tzinfo=timezone.utc)
    out = build_aib(brief, now=sunday)
    assert out["freshness"]["days_behind"] == 0
    assert out["freshness"]["level"] == "current"
    page = render(REPO, stores=dict(EMPTY_STORES), intel_brief=brief, now=sunday)
    panel = _aib_panel(page)
    assert "Current" in panel
    assert "最新" in panel
    assert "behind" not in panel


def test_post_labor_day_tuesday_reads_the_newest_close_as_lagging_not_stale():
    """Major finding, review of PR #6932: after Labor Day (Mon 2026-09-07),
    reading Friday 2026-09-04's close on Tuesday 2026-09-08 evening is 4
    CALENDAR days but only 1 completed SESSION behind — 'lagging', never the
    warn-tinted 'stale' level calendar-day math produced on a holiday week."""
    brief = _brief(board_state="OK", as_of="2026-09-04", opportunities=[_card("AAA")])
    tuesday_eve = datetime(2026, 9, 8, 22, 0, tzinfo=timezone.utc)
    out = build_aib(brief, now=tuesday_eve)
    assert out["freshness"]["days_behind"] == 1
    assert out["freshness"]["level"] == "lagging"
    page = render(REPO, stores=dict(EMPTY_STORES), intel_brief=brief, now=tuesday_eve)
    panel = _aib_panel(page)
    assert "1 day behind" in panel
    assert "lvl-stale" not in panel


def test_unknown_asof_is_not_zero_days():
    brief = _brief(board_state="OK", as_of=None, opportunities=[_card("AAA")])
    out = build_aib(brief, now=NOW)
    assert out["freshness"]["days_behind"] is None
    assert out["freshness"]["level"] == "unknown"
    page = render(REPO, stores=dict(EMPTY_STORES), intel_brief=brief, now=NOW)
    panel = _aib_panel(page)
    assert "As-of date not recorded" in panel
    assert "Current" not in panel
    assert "最新" not in panel


def test_unparseable_built_at_renders_not_recorded():
    brief = _brief(board_state="OK", opportunities=[_card("AAA")], built_at_utc="garbage")
    page = render(REPO, stores=dict(EMPTY_STORES), intel_brief=brief, now=NOW)  # must not raise
    panel = _aib_panel(page)
    assert "Update time not recorded" in panel
    assert "未记录更新时间" in panel


def test_no_forbidden_vocabulary_in_brief_section():
    brief = _brief(board_state="STALE_SOURCE", opportunities=[])
    page = render(REPO, stores=dict(EMPTY_STORES), intel_brief=brief, now=NOW)
    panel = _strip_attrs(_aib_panel(page))
    for banned in ("falsifier", "refuted", "invalidated", "证伪",
                   "board_state", "NO_SIGNAL", "intel_brief_heuristic"):
        assert banned not in panel, banned


def test_every_new_string_is_bilingual_and_no_title_attribute():
    brief = _brief(board_state="OK", as_of="2026-09-03",
                    opportunities=[_card("AAA", r=1), _card("BBB", r=2)])
    page = render(REPO, stores=dict(EMPTY_STORES), intel_brief=brief, now=NOW)
    panel = _aib_panel(page)
    pairs = [
        (_esc("2 names are worth a look after today's close."), "今日收盘后有 2 个名称值得关注。"),
        ("What to do", "该怎么做"),
        ("Read these first — none is a trade on its own.", "建议优先阅读——均非独立交易信号。"),
        ("As of", "数据截至"),
        ("1 day behind", "落后 1 天"),
    ]
    for en, zh in pairs:
        assert en in panel, en
        assert zh in panel, zh
    assert "title=" not in panel
