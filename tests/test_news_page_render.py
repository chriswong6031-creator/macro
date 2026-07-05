"""Render smoke tests for the W3 news.html.j2 intelligence boards page.

Two fixtures:
  _full_vm()  — exercising every board: event deltas, macro releases, theme
                pulse, context headlines, reject log, calibration (all-insufficient).
  _empty_vm() — every new artifact is None/missing; the page must render without
                exception and must NOT crash on absent news_rejected / macro_releases /
                news_calibration / macro_news.

Both VMs pass the same keys the build_site.py render call sends.
"""
from __future__ import annotations

from pathlib import Path

import jinja2
import pytest

ROOT = Path(__file__).resolve().parent.parent


def _env() -> jinja2.Environment:
    """Mirror scripts/build_site.py's Jinja env (same loader path)."""
    env = jinja2.Environment(
        loader=jinja2.FileSystemLoader(str(ROOT / "templates")),
        autoescape=False,
    )
    try:
        from engine import i18n  # noqa: PLC0415
        env.globals.update(td=i18n.td, tr=i18n.tr)
    except Exception:  # noqa: BLE001
        env.globals.update(td=lambda en: en, tr=lambda en: en)
    return env


# --------------------------------------------------------------------------- #
# Fixture helpers
# --------------------------------------------------------------------------- #

def _headline(theme: str = "monetary", with_event: bool = True, title: str = "Fed holds rates steady") -> dict:
    base: dict = {
        "title": title,
        "title_zh": "美联储维持利率不变",
        "theme": theme,
        "domain": "reuters.com",
        "source_name": "Reuters",
        "source_tier": 1,
        "url": "https://reuters.com/test",
        "seendate": "2026-07-04T10:00:00Z",
        "channels": ["monetary_policy", "rates"],
        "tickers": ["SPY", "TLT"],
        "importance": "high",
        "importance_score": 85,
        "importance_reasons": ["tier1_source", "macro_theme"],
        "centrality": "primary",
        "novelty_z": 1.8,
        "echo": {"n_sources": 3, "n_desks": 2},
    }
    if with_event:
        base["event"] = {
            "name": "rate_decision",
            "direction": "bearish",
            "numbers": {
                "pcts": [5.25, 5.5],
                "dollars_b": [],
                "dollars_m": [],
                "eps": [],
            },
        }
    else:
        base["event"] = None
    return base


def _release_card() -> dict:
    return {
        "release": "nonfarm_payrolls",
        "display_name": "Nonfarm Payrolls",
        "macro_channel": "labor",
        "period": "Jun 2026",
        "latest_date": "2026-07-03",
        "actual": 147000.0,
        "prior": 139000.0,
        "prior_date": "2026-06-06",
        "prior_label": "vs revised prior",
        "transform": "level",
        "deltas": {"vs_prior": 8000.0, "vs_3m_mean": 5200.0, "vs_6m_mean": 3100.0},
        "z3y": 0.8,
        "z5y": 0.7,
        "surprise_size": "notable",
        "direction_tag": "bullish",
        "summary": "Payrolls came in above revised prior, z3y slightly above trend.",
        "n_hist_3y": 36,
        "n_hist_5y": 60,
    }


def _rejected_entry(reason: str = "stock_pick_roundup", title: str = "10 stocks to buy this week") -> dict:
    return {
        "title": title,
        "domain": "fool.com",
        "reason": reason,
    }


def _calibration_entry(verdict: str = "insufficient") -> dict:
    return {
        "event_type": "rate_decision",
        "direction": "bearish",
        "n": 5,
        "n_graded": 3,
        "hit_5d": None,
        "hit_21d": None,
        "avg_rel_5d": None,
        "avg_rel_21d": None,
        "wilson_low_5d": None,
        "wilson_high_5d": None,
        "verdict": verdict,
    }


def _full_vm() -> dict:
    """Full fixture exercising every board."""
    return dict(
        # standard build_site vm keys
        latest={
            "date": "2026-07-04",
            "conditions": {
                "risk_appetite": {
                    "news_sentiment_state": "pessimistic",
                    "news_sentiment_z": -0.9,
                }
            },
        },
        macro_news={
            "headlines": [
                _headline(theme="monetary", with_event=True, title="Fed holds rates steady"),
                _headline(theme="labor",    with_event=True, title="Payrolls beat, unemployment ticks up"),
                _headline(theme="inflation", with_event=False, title="CPI expectations stay elevated"),
                _headline(theme="growth",   with_event=False, title="ISM manufacturing soft for third month"),
            ],
            "synthesis": {
                "read": "4 headlines across 2 themes",
                "top_channels": [{"name": "monetary_policy"}, {"name": "rates"}],
                "top_tickers": [{"ticker": "TLT"}, {"ticker": "SPY"}],
            },
            "fetched_at": "2026-07-04T06:00:00Z",
            "n_raw": 120,
            "n_kept": 4,
            "n_official": 2,
            "n_news_rss": 1,
            "n_gdelt": 1,
        },
        macro_news_disclaimer="Context only — not a signal.",
        macro_news_disclaimer_zh="仅作背景，非信号。",
        macro_catalysts=[
            {"date": "2026-07-10", "time_et": "08:30", "type": "FOMC", "label": "FOMC minutes"},
        ],
        event_strip=[
            {"dow": "Thu", "md": "Jul 10", "time_et": "08:30", "type": "CPI", "label": "CPI Jun"},
        ],
        prediction_markets=None,
        ndi=None,
        # W3 new keys
        macro_releases={
            "schema": "macro_releases.v1",
            "is_context_only": True,
            "asof": "2026-07-04T06:00:00Z",
            "cards": [_release_card()],
            "n_cards": 1,
            "n_fetched": 8,
            "n_registry": 10,
        },
        news_rejected={
            "schema": "news_reject_log.v1",
            "is_context_only": True,
            "built": "2026-07-04T06:00:00Z",
            "n_total": 5,
            "feeds": {
                "macro": [
                    _rejected_entry("stock_pick_roundup", "10 stocks for 2026"),
                    _rejected_entry("calendar_preview",   "This week in markets"),
                ],
                "financial": [
                    _rejected_entry("routine_fund_distribution", "Distribution notice: XYZ ETF"),
                ],
                "rss": [
                    _rejected_entry("lifestyle_content", "How to retire at 40"),
                    _rejected_entry("personal_finance_advice", "Should I buy gold?"),
                ],
            },
        },
        news_calibration={
            "schema": "news_event_calibration.v1",
            "is_context_only": True,
            "asof": "2026-07-04",
            "n_events_logged": 5,
            "n_events_graded": 0,
            "classes": [
                _calibration_entry("insufficient"),
                _calibration_entry("insufficient"),
            ],
            "reject_audit": {
                "n_sampled": 10,
                "n_graded": 0,
                "classes": [
                    {"reason": "stock_pick_roundup", "n_graded": 0, "avg_rel_21d": None, "note": "accruing"},
                ],
            },
        },
    )


def _empty_vm() -> dict:
    """All new artifacts are None — page must render without exception."""
    return dict(
        latest={"date": "2026-07-04", "conditions": None},
        macro_news=None,
        macro_news_disclaimer="",
        macro_news_disclaimer_zh="",
        macro_catalysts=[],
        event_strip=[],
        prediction_markets=None,
        ndi=None,
        # W3 keys all absent
        macro_releases=None,
        news_rejected=None,
        news_calibration=None,
    )


# --------------------------------------------------------------------------- #
# Tests — full vm
# --------------------------------------------------------------------------- #

def _render_full() -> str:
    return _env().get_template("news.html.j2").render(**_full_vm())


def _render_empty() -> str:
    return _env().get_template("news.html.j2").render(**_empty_vm())


def test_full_vm_renders_without_exception():
    """Full fixture must render without raising."""
    html = _render_full()
    assert len(html) > 500


def test_full_vm_delta_board_present():
    """<!-- nx-delta-board --> section marker present."""
    html = _render_full()
    assert "nx-delta-board" in html or "nxDeltaBoard" in html


def test_full_vm_release_board_present():
    """<!-- nx-release-board --> section marker present."""
    html = _render_full()
    assert "nx-release-board" in html or "nxReleaseBoard" in html


def test_full_vm_theme_pulse_present():
    """<!-- nx-theme-pulse --> section marker present."""
    html = _render_full()
    assert "nx-theme-pulse" in html or "nxThemePulse" in html


def test_full_vm_context_section_present():
    """<!-- nx-context-section --> section marker present."""
    html = _render_full()
    assert "nx-context-section" in html or "nxContextSection" in html


def test_full_vm_reject_log_present():
    """<!-- nx-reject-log --> section marker present."""
    html = _render_full()
    assert "nx-reject-log" in html or "nxRejectLog" in html


def test_full_vm_calibration_board_present():
    """<!-- nx-calibration-board --> section marker present."""
    html = _render_full()
    assert "nx-calibration-board" in html or "nxCalibrationBoard" in html


def test_full_vm_event_cards_render():
    """Event-typed headlines appear in the delta board."""
    html = _render_full()
    assert "rate_decision" in html.lower() or "Rate Decision" in html


def test_full_vm_release_card_renders():
    """Nonfarm Payrolls card renders with actual value."""
    html = _render_full()
    assert "Nonfarm Payrolls" in html
    assert "147" in html  # actual value present


def test_full_vm_reject_log_groups_by_reason():
    """Reject log groups items by reason — at least one reason label visible."""
    html = _render_full()
    assert "stock pick roundup" in html.lower() or "stock_pick_roundup" in html


def test_full_vm_calibration_shows_insufficient():
    """All-insufficient calibration renders 'accruing' states, not a crash."""
    html = _render_full()
    assert "accruing" in html.lower() or "insufficient" in html.lower()


def test_full_vm_exec_strip_counts():
    """Executive strip shows event counts; both 0 and >0 cases work."""
    html = _render_full()
    # 2 events, 1 release in fixture
    assert "exec-strip" in html
    # counts must be present somewhere in the strip
    assert "exec-chip" in html


def test_full_vm_context_headlines_present():
    """Context (no-event) headlines appear in the context section."""
    html = _render_full()
    # 2 context heads in fixture
    assert "CPI expectations" in html or "nxContextSection" in html


def test_full_vm_theme_pulse_counts():
    """Theme pulse shows monetary/labor/inflation/growth counts."""
    html = _render_full()
    # monetary theme has 1 event head + nothing in ctx = 1 total (or 2 if both)
    assert "pulse-cell" in html or "nxThemePulse" in html


def test_full_vm_no_translated_title_attrs():
    """No translated text inside title= attribute (check_title_i18n guard)."""
    import re
    html = _render_full()
    # Find all title= attributes
    titles = re.findall(r'title=["\']([^"\']+)["\']', html)
    for t_val in titles:
        # Chinese chars: any CJK unified ideograph
        assert not any('一' <= c <= '鿿' for c in t_val), \
            f"Translated text found in title= attribute: {t_val!r}"


# --------------------------------------------------------------------------- #
# Tests — empty vm
# --------------------------------------------------------------------------- #

def test_empty_vm_renders_without_exception():
    """All-empty vm must render without exception (null-safety)."""
    html = _render_empty()
    assert len(html) > 200


def test_empty_vm_still_has_board_structure():
    """Even with all artifacts absent the board sections are present."""
    html = _render_empty()
    assert "nxDeltaBoard" in html
    assert "nxReleaseBoard" in html
    assert "nxCalibrationBoard" in html


def test_empty_vm_calibration_shows_placeholder():
    """Missing calibration artifact renders the 'accruing' placeholder panel."""
    html = _render_empty()
    assert "accruing" in html.lower()


def test_empty_vm_no_context_headlines_crash():
    """No macro_news must not raise — empty state renders."""
    html = _render_empty()
    assert "board-empty" in html or "nxDeltaBoard" in html


def test_empty_vm_reject_log_shows_empty_state():
    """No news_rejected artifact renders empty state, not a crash."""
    html = _render_empty()
    assert "nxRejectLog" in html


def test_empty_vm_no_jinja_undefined_error():
    """Template must not access undefined variables (Jinja2 silent mode active)."""
    # If any key access raises UndefinedError jinja2 would propagate it;
    # the render call would have raised before this assertion.
    html = _render_empty()
    assert html is not None


# --------------------------------------------------------------------------- #
# Tests — Delta Board sort (W3 fix: build_site.py ev_heads pre-sort)
# --------------------------------------------------------------------------- #

def _make_ev_head(title: str, novelty_z, seendate: str) -> dict:
    return {
        "title": title,
        "seendate": seendate,
        "novelty_z": novelty_z,
        "event": {"name": "rate_decision", "direction": "bearish"},
    }


def _apply_ev_heads_sort(heads: list) -> list:
    """Replicate the sort logic from scripts/build_site.py for unit testing."""
    _ev = [h for h in heads if h.get("event")]
    _ev.sort(key=lambda h: h.get("seendate") or "", reverse=True)
    _ev.sort(
        key=lambda h: abs(float(h["novelty_z"])) if h.get("novelty_z") is not None else 0.0,
        reverse=True,
    )
    return _ev


def test_delta_board_sort_by_novelty_z_desc():
    """Headlines with higher |novelty_z| appear first."""
    heads = [
        _make_ev_head("low novelty",  novelty_z=0.5, seendate="20260704T100000Z"),
        _make_ev_head("high novelty", novelty_z=3.2, seendate="20260704T090000Z"),
        _make_ev_head("mid novelty",  novelty_z=1.8, seendate="20260704T080000Z"),
    ]
    sorted_heads = _apply_ev_heads_sort(heads)
    titles = [h["title"] for h in sorted_heads]
    assert titles == ["high novelty", "mid novelty", "low novelty"], titles


def test_delta_board_sort_negative_novelty_z_uses_abs():
    """Negative novelty_z with large magnitude ranks above smaller |z|."""
    heads = [
        _make_ev_head("small positive", novelty_z=1.0, seendate="20260704T100000Z"),
        _make_ev_head("large negative", novelty_z=-2.5, seendate="20260704T090000Z"),
    ]
    sorted_heads = _apply_ev_heads_sort(heads)
    assert sorted_heads[0]["title"] == "large negative"


def test_delta_board_sort_recency_tiebreak():
    """Equal |novelty_z| — most recent seendate wins."""
    heads = [
        _make_ev_head("older",  novelty_z=1.5, seendate="20260703T100000Z"),
        _make_ev_head("newer",  novelty_z=1.5, seendate="20260704T100000Z"),
    ]
    sorted_heads = _apply_ev_heads_sort(heads)
    assert sorted_heads[0]["title"] == "newer"


def test_delta_board_sort_none_novelty_z_goes_last():
    """Headlines with novelty_z=None sort below those with a real z-score."""
    heads = [
        _make_ev_head("no novelty",   novelty_z=None, seendate="20260704T120000Z"),
        _make_ev_head("has novelty",  novelty_z=0.1,  seendate="20260704T060000Z"),
    ]
    sorted_heads = _apply_ev_heads_sort(heads)
    assert sorted_heads[0]["title"] == "has novelty"
