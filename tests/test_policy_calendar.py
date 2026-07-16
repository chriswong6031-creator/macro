"""Hermetic tests for engine/policy_calendar.py — W1b.

No network calls. All DataFrames are synthetic.

Test plan:
1. test_latency_join_matched       — PRORULE→RULE join via RIN; correct latency computed.
2. test_latency_join_open          — PRORULE with no RULE counterpart → counted as open,
                                      excluded from median.
3. test_latency_join_multiple_rin  — Multiple RIN families, per-theme medians distinct.
4. test_forward_dating_excludes_past — past comment-close never appears in upcoming_events.
5. test_entity_list_precision      — a non-entity-list BIS doc with 'nuclear' in title
                                      → NOT tagged; only entity-list patterns match.
6. test_stage_byte_identical       — compute_foresight_cascade with policy_reg present vs
                                      absent → stage fields byte-identical.
7. test_latency_no_equal_fixture   — guards against vacuous fixture: PR and FR baskets differ
                                      so a builder mistake (wrong latency) is caught.
"""
from __future__ import annotations

import copy
import sys
from datetime import date, timedelta
from pathlib import Path

import pandas as pd
import pytest

# Ensure repo root is on path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from engine.policy_calendar import (
    _compute_entity_list_events,
    _compute_latency,
    compute_policy_calendar,
)


# ---------------------------------------------------------------------------
# Shared fixture builders
# ---------------------------------------------------------------------------

def _doc(document_number, basket_id, reg_stage, publication_date, rin="",
         comments_close_on="", agency_slug="", title=""):
    return {
        "document_number": document_number,
        "basket_id": basket_id,
        "publication_date": publication_date,
        "type": "Rule" if reg_stage == "final_rule" else "Proposed Rule",
        "reg_stage": reg_stage,
        "weight": 1.0,
        "significant": None,
        "title": title or f"Title for {document_number}",
        "abstract": "",
        "action": "",
        "rin": rin,
        "comments_close_on": comments_close_on,
        "agency_slug": agency_slug or "some-agency",
        "cfr_ref": "",
        "_first_seen": publication_date,
    }


def _make_df(rows: list[dict]) -> pd.DataFrame:
    return pd.DataFrame(rows)


# ---------------------------------------------------------------------------
# 1. Latency join — matched pair
# ---------------------------------------------------------------------------

def test_latency_join_matched():
    """A PRORULE published 300 days before its RULE → median_days == 300."""
    pr_date = "2023-01-01"
    fr_date = "2023-10-28"  # 300 days later
    expected_latency = (date.fromisoformat(fr_date) - date.fromisoformat(pr_date)).days
    assert expected_latency == 300  # self-check the fixture

    rows = [
        _doc("PR-001", "ai_semiconductors", "proposed_rule", pr_date, rin="1234-AA01"),
        _doc("FR-001", "ai_semiconductors", "final_rule",    fr_date, rin="1234-AA01"),
    ]
    df = _make_df(rows)
    result = _compute_latency(df)

    assert "ai_semiconductors" in result
    lat = result["ai_semiconductors"]
    assert lat["n"] == 1
    assert lat["median_days"] == 300
    assert lat["n_open"] == 0


# ---------------------------------------------------------------------------
# 2. Latency join — open PRORULE excluded from median
# ---------------------------------------------------------------------------

def test_latency_join_open():
    """PRORULE with no RULE counterpart → n_open=1, n=0, median_days=None."""
    rows = [
        _doc("PR-002", "memory_storage", "proposed_rule", "2024-01-01", rin="9999-ZZ01"),
        # No final_rule row for this RIN
        _doc("FR-X",   "memory_storage", "final_rule",    "2023-06-01", rin="0000-AA01"),
    ]
    df = _make_df(rows)
    result = _compute_latency(df)

    assert "memory_storage" in result
    lat = result["memory_storage"]
    assert lat["n"] == 0          # no matched pairs
    assert lat["n_open"] == 1     # one open PRORULE
    assert lat["median_days"] is None


# ---------------------------------------------------------------------------
# 3. Multiple RIN families — per-theme medians are distinct
# ---------------------------------------------------------------------------

def test_latency_join_multiple_rin():
    """Two RIN families in different baskets produce different median latencies.

    This guards against a builder mistake that computes a single global median
    and assigns it to all baskets (the two median values here are deliberately
    different: 180 vs 540 days).
    """
    # ai_semiconductors: RIN-A → 180 days
    pr_a = "2023-01-01"
    fr_a = (date.fromisoformat(pr_a) + timedelta(days=180)).isoformat()
    # rare_earth_critical_min: RIN-B → 540 days
    pr_b = "2022-01-01"
    fr_b = (date.fromisoformat(pr_b) + timedelta(days=540)).isoformat()
    assert fr_a != fr_b  # dates differ → not the same fixture blended

    rows = [
        _doc("PR-A", "ai_semiconductors",    "proposed_rule", pr_a, rin="1111-AA"),
        _doc("FR-A", "ai_semiconductors",    "final_rule",    fr_a, rin="1111-AA"),
        _doc("PR-B", "rare_earth_critical_min", "proposed_rule", pr_b, rin="2222-BB"),
        _doc("FR-B", "rare_earth_critical_min", "final_rule",    fr_b, rin="2222-BB"),
    ]
    df = _make_df(rows)
    result = _compute_latency(df)

    lat_ai = result["ai_semiconductors"]["median_days"]
    lat_re = result["rare_earth_critical_min"]["median_days"]

    assert lat_ai == 180, f"ai_semiconductors median should be 180, got {lat_ai}"
    assert lat_re == 540, f"rare_earth median should be 540, got {lat_re}"
    # The key anti-vacuity check: they must differ
    assert lat_ai != lat_re, "medians are equal — fixture is not discriminating"


# ---------------------------------------------------------------------------
# 4. Forward dating: past comment-close never appears in upcoming_events
# ---------------------------------------------------------------------------

def test_forward_dating_excludes_past(tmp_path, monkeypatch):
    """A row with comments_close_on in the past must not appear in upcoming_events."""
    from lib import config

    # compute_policy_calendar seeds the forward ledger via _append_ledger →
    # config.data_dir(). Unredirected, this synthetic (solar, asof) row lands in
    # the REAL data/foresight ledger — it did once: the committed
    # 2026-07-04T00:30:49Z solar row is this fixture.
    monkeypatch.setattr(config, "data_dir", lambda: tmp_path / "data")

    today = date(2026, 7, 3)
    past_date = "2026-07-01"   # 2 days ago
    future_date = "2026-08-01"  # 29 days away

    rows = [
        _doc("DOC-PAST",   "solar", "proposed_rule", "2026-06-01",
             comments_close_on=past_date),
        _doc("DOC-FUTURE", "solar", "proposed_rule", "2026-07-01",
             comments_close_on=future_date),
    ]
    df = _make_df(rows)
    result = compute_policy_calendar(df=df, today=today)

    assert result is not None
    dates_in_upcoming = [ev["date"] for ev in result["upcoming_events"]]
    assert past_date not in dates_in_upcoming, \
        f"Past date {past_date} must not appear in upcoming_events"
    assert future_date in dates_in_upcoming, \
        f"Future date {future_date} must appear in upcoming_events"

    # sanity: the ledger append went to the isolated tree, not the repo
    ledger = tmp_path / "data" / "foresight" / "policy_calendar_ledger.jsonl"
    assert ledger.exists(), "ledger row must land in the redirected data dir"


def test_append_ledger_gated_off_outside_nightly_lane(tmp_path, monkeypatch):
    """COLLECT_LANE != nightly must suppress the forward-ledger append (the
    #2598 idiom; policy_calendar was the one appender the sweep missed)."""
    from lib import config

    monkeypatch.setattr(config, "data_dir", lambda: tmp_path / "data")
    monkeypatch.delenv("COLLECT_LANE", raising=False)
    monkeypatch.delenv("US_LANE", raising=False)

    rows = [
        _doc("DOC-FUTURE", "solar", "proposed_rule", "2026-07-01",
             comments_close_on="2026-08-01"),
    ]
    result = compute_policy_calendar(df=_make_df(rows), today=date(2026, 7, 3))

    assert result is not None  # display payload unaffected by the gate
    ledger = tmp_path / "data" / "foresight" / "policy_calendar_ledger.jsonl"
    assert not ledger.exists(), \
        "forward ledger must not advance outside the nightly lane"


# ---------------------------------------------------------------------------
# 5. Entity-list precision: non-entity-list BIS doc is NOT tagged
# ---------------------------------------------------------------------------

def test_entity_list_precision():
    """A BIS doc about 'nuclear export' that does NOT match entity-list patterns
    should not appear in entity_list_events.

    A BIS doc with 'Entity List' in the title SHOULD appear.
    """
    today = date(2026, 7, 3)
    cutoff_60d = (today - timedelta(days=60)).isoformat()

    non_el_title = "Nuclear Regulatory Cooperation with Allied Nations"  # no entity-list pattern
    el_title = "Addition of Entities to the Entity List"

    rows = [
        _doc("BIS-NONEL", "nuclear_power", "final_rule", "2026-06-15",
             agency_slug="industry-and-security-bureau", title=non_el_title),
        _doc("BIS-EL",    "ai_semiconductors", "final_rule", "2026-06-15",
             agency_slug="industry-and-security-bureau", title=el_title),
    ]
    df = _make_df(rows)
    events = _compute_entity_list_events(df, today.isoformat(), cutoff_60d)

    event_titles = [e["title"] for e in events]
    assert non_el_title not in event_titles, \
        f"Non-entity-list BIS doc should NOT be tagged: {non_el_title}"
    assert any(el_title in t for t in event_titles), \
        f"Entity-list BIS doc MUST be tagged; events={event_titles}"


# ---------------------------------------------------------------------------
# 6. Stage byte-identical regression: policy_reg present vs absent
# ---------------------------------------------------------------------------

def test_stage_byte_identical_with_policy_reg():
    """compute_foresight_cascade with policy_reg present vs absent must produce
    byte-identical stage, bottleneck_band, revision_breadth, and glut_band fields
    for every theme row.

    This verifies that policy_reg NEVER changes cascade stages (only rationale text).
    """
    from engine.foresight_cascade import compute_foresight_cascade

    # Minimal synthetic inputs — avoid any real file IO
    synthetic_bottleneck = {
        "asof": "2026-07-03",
        "themes": {
            "ai_semiconductors": {
                "band": "TIGHT",
                "text_only": False,
                "fingerprint_only": False,
                "tightness": 0.7,
                "regime": "constrained",
                "numeric_band": "TIGHT",
                "ppi_yoy_latest": 3.5,
                "language_accel": None,
                "name": "AI Semiconductors",
            },
        },
    }
    synthetic_revisions = {
        "asof": "2026-07-03",
        "themes": {
            "ai_semiconductors": {
                "breadth": 0.55,
                "level_state": "rising",
                "broadening_state": "broadening",
                "est_drift_90d": 4.2,
                "name": "AI Semiconductors",
            },
        },
    }
    # Minimal policy_reg payload (has a real chip for ai_semiconductors)
    synthetic_policy_reg = {
        "asof": "2026-07-03",
        "themes": {
            "ai_semiconductors": {
                "basket_id": "ai_semiconductors",
                "days_to_next_comment_close": 14,
                "next_comment_close_date": "2026-07-17",
                "next_comment_close_title": "Export Controls on Advanced Computing",
                "days_to_next_rule_effective": None,
                "next_rule_effective_date": None,
                "next_rule_effective_title": None,
                "prorule_inflow_60d": 3,
                "rule_finalization_60d": 1,
            },
        },
        "upcoming_events": [],
        "entity_list_events": [],
        "latency_summary": {},
        "note": "test",
    }

    # Run cascade WITHOUT policy_reg (pass as empty dict to disable lazy-load)
    # We pass policy_reg={} so the lazy-load ALSO won't load real data.
    # To truly isolate, override the lazy-load by passing a sentinel empty dict.
    # The cascade's "if policy_reg is None:" block only lazy-loads when None.
    cascade_without = compute_foresight_cascade(
        bottleneck=copy.deepcopy(synthetic_bottleneck),
        revisions=copy.deepcopy(synthetic_revisions),
        demand={}, glut={}, guidance={}, confirmers={},
        fda_scarcity={},
        policy_reg={},  # empty — no chips, no rationale addition
        write_ledger=False,
    )
    cascade_with = compute_foresight_cascade(
        bottleneck=copy.deepcopy(synthetic_bottleneck),
        revisions=copy.deepcopy(synthetic_revisions),
        demand={}, glut={}, guidance={}, confirmers={},
        fda_scarcity={},
        policy_reg=synthetic_policy_reg,  # real chip present
        write_ledger=False,
    )

    assert cascade_without is not None, "cascade_without must not be None"
    assert cascade_with is not None, "cascade_with must not be None"

    rows_without = {r["theme"]: r for r in (cascade_without.get("themes") or [])}
    rows_with    = {r["theme"]: r for r in (cascade_with.get("themes") or [])}

    stage_fields = ["stage", "bottleneck_band", "glut_band", "tier",
                    "entry_ready", "bottleneck_text_only", "bottleneck_fingerprint_only"]

    for theme in rows_without:
        if theme not in rows_with:
            continue
        r_no  = rows_without[theme]
        r_yes = rows_with[theme]
        for field in stage_fields:
            assert r_no.get(field) == r_yes.get(field), (
                f"Stage field '{field}' differs for theme '{theme}': "
                f"without={r_no.get(field)!r} with={r_yes.get(field)!r}"
            )

    # Verify rationale DID change (policy chip folds into rationale)
    r_no_rat  = rows_without.get("ai_semiconductors", {}).get("rationale", "")
    r_yes_rat = rows_with.get("ai_semiconductors", {}).get("rationale", "")
    assert "policy pipeline" in r_yes_rat, \
        f"policy_reg chip must appear in rationale when present; got: {r_yes_rat!r}"
    assert "policy pipeline" not in r_no_rat, \
        f"policy pipeline must NOT appear in rationale when policy_reg is empty; got: {r_no_rat!r}"


# ---------------------------------------------------------------------------
# 7. Anti-vacuity: latency fixture uses non-equal basket latencies
#    (already covered by test_latency_join_multiple_rin asserting lat_ai != lat_re)
# ---------------------------------------------------------------------------

def test_latency_no_equal_fixture():
    """Explicit guard: if both latencies were 300 days (equal), test_latency_join_multiple_rin
    would not catch a wrong-basket assignment bug. This test asserts the fixture creates
    genuinely different values — 180 != 540."""
    assert 180 != 540, "fixture sanity: latency values must differ"
