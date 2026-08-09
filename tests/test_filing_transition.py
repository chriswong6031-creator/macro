"""Rolling 13F filing-transition contracts."""
from __future__ import annotations

import pandas as pd

from engine.filing_transition import (
    build_filing_transition, quarter_label, transition_counts,
)


def _clock(n_filed: int, n_active: int = 50) -> dict:
    rows = []
    for i in range(n_active):
        filed = i < n_filed
        rows.append({
            "slug": f"fund{i}",
            "name": f"Fund {i}",
            "period_end": "2026-06-30" if filed else "2026-03-31",
            "filing_date": f"2026-08-{i + 1:02d}" if filed else "2026-05-15",
            "status": "filed" if filed else "pending",
        })
    # Closed managers remain visible in the dot grid but never enter the denominator.
    rows.append({"slug": "closed", "name": "Closed", "period_end": "2026-03-31",
                 "filing_date": "2026-05-15", "status": "closed"})
    return {
        "quarter_end": "2026-06-30",
        "next_deadline": "2026-08-14",
        "days_to_deadline": 6,
        "quarter_state": "window_open",
        "filed_pending": rows,
    }


def test_quarter_label_is_dynamic():
    assert quarter_label("2026-06-30") == "Q2 2026"
    assert quarter_label("2027-12-31") == "Q4 2027"


def test_early_radar_appears_for_three_of_fifty():
    state = transition_counts(_clock(3))
    assert state["state"] == "early_roll"
    assert state["show_early_radar"] is True
    assert state["filed_count"] == 3
    assert state["active_count"] == 50
    assert state["majority_at"] == 26
    assert state["display_period"] == "2026-03-31"
    assert state["is_mixed"] is True


def test_radar_retires_at_strict_majority_handoff():
    before = transition_counts(_clock(25))
    handoff = transition_counts(_clock(26))
    complete = transition_counts(_clock(50))
    assert before["show_early_radar"] is True
    assert before["canonical_period"] == "2026-03-31"
    assert before["canonical_count"] == 50
    assert handoff["state"] == "bulk_roll"
    assert handoff["show_early_radar"] is False
    assert handoff["canonical_period"] == "2026-06-30"
    assert handoff["canonical_count"] == 26
    assert handoff["cohort_basis"] == "paired_reporters"
    assert complete["state"] == "complete"


def test_notice_is_visible_but_never_treated_as_holdings_or_an_exit():
    clock = _clock(3)
    notice = clock["filed_pending"][3]
    notice.update({
        "status": "notice",
        "notice_period_end": "2026-06-30",
        "notice_filing_date": "2026-08-05",
        "notice_form": "13F-NT",
        "notice_accession": "0000000000-26-000001",
    })
    state = transition_counts(clock)
    assert state["filed_count"] == 3
    assert state["notice_count"] == 1
    assert state["pending_count"] == 46
    assert state["canonical_period"] == "2026-03-31"
    assert "fund3" in state["canonical_slugs"]

    notice_clock = _clock(0)
    notice_clock["filed_pending"][3].update(notice)
    funds = {f"fund{i}": {"name": f"Fund {i}"} for i in range(50)}
    result = build_filing_transition(funds, notice_clock)
    assert result["notices"] == [{
        "slug": "fund3", "name": "Fund 3", "filing_date": "2026-08-05",
        "period_end": "2026-06-30", "form": "13F-NT",
        "accession": "0000000000-26-000001",
    }]
    assert "never counted as a zero-position" in result["notice_note"]


def test_build_transition_ranks_resolved_changes(monkeypatch):
    import engine.smart_money as sm

    prev = pd.DataFrame([
        {"cusip": "OLD", "issuer": "Old Co", "shares": 100.0,
         "value_usd": 40.0, "sh_type": "SH", "period_end": "2026-03-31",
         "filing_date": "2026-05-15"},
        {"cusip": "KEEP", "issuer": "Keep Co", "shares": 100.0,
         "value_usd": 60.0, "sh_type": "SH", "period_end": "2026-03-31",
         "filing_date": "2026-05-15"},
    ])
    latest = pd.DataFrame([
        {"cusip": "NEW", "issuer": "New Co", "shares": 100.0,
         "value_usd": 70.0, "sh_type": "SH", "period_end": "2026-06-30",
         "filing_date": "2026-08-01"},
        {"cusip": "KEEP", "issuer": "Keep Co", "shares": 150.0,
         "value_usd": 30.0, "sh_type": "SH", "period_end": "2026-06-30",
         "filing_date": "2026-08-01"},
    ])

    monkeypatch.setattr(sm, "_read_period_pair", lambda slug, period: (prev, latest))
    monkeypatch.setattr(sm, "name_ticker_map", lambda: {})
    monkeypatch.setattr(sm, "full_cusip_map", lambda: ({}, {}))

    def _resolve(df, _name, _cusip):
        out = df.copy()
        out["ticker"] = out["cusip"].map({"NEW": "NEW", "KEEP": "KEEP", "OLD": "OLD"})
        return out

    monkeypatch.setattr(sm, "resolve_tickers", _resolve)
    clock = _clock(1, n_active=4)
    funds = {f"fund{i}": {"name": f"Fund {i}"} for i in range(4)}
    tracker = {"leaderboard": [{"slug": "fund0", "grade": "A"}]}

    result = build_filing_transition(funds, clock, tracker)
    assert result["show_early_radar"] is True
    assert result["automation_mode"] == "rolling_filing_season"
    assert result["filers"][0]["action_counts"] == {
        "new": 1, "add": 1, "trim": 0, "exit": 1}
    assert {r["ticker"] for r in result["ranked_changes"]} == {"NEW", "KEEP", "OLD"}
    assert result["ranked_changes"][0]["ticker"] == "NEW"
    old = next(r for r in result["ranked_changes"] if r["ticker"] == "OLD")
    assert old["book_pct"] == 40.0  # prior-quarter weight, not the diff's synthetic zero
    assert "not an expected-return" in result["importance_note"]
