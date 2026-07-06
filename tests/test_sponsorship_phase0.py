"""Unit tests for research.entry_stack.sponsorship_phase0 — SRSS Phase 0
read-only join. Covers: no-future-leak, the 6-state classification rules
(with the rs_ratio->score/rs_mom substitution the ledger forces), thin-group
handling, and coverage-report robustness on empty input."""
from __future__ import annotations

import json

import pandas as pd

from research.entry_stack import sponsorship_phase0 as P


def _snap(date_, key, members, quadrant, rs_mom, accel, score):
    return {"date": date_, "key": key, "name": key, "theme": "T", "score": score,
            "rs_mom": rs_mom, "accel": accel, "quadrant": quadrant,
            "stage": "emerging", "lean": 1, "members": members}


def _write_snapshots(tmp_path, rows):
    p = tmp_path / "data/subsector_rotation/snapshots.jsonl"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text("\n".join(json.dumps(r) for r in rows) + "\n")


# --------------------------------------------------------------------------- #
# (a) no-future-leak
# --------------------------------------------------------------------------- #
def test_rotation_index_never_returns_future_row():
    snaps = [
        _snap("2026-06-28", "k1", ["AAA"], "leading", 1.0, 1.0, 2.0),
        _snap("2026-07-10", "k1", ["AAA"], "leading", 5.0, 5.0, 9.0),  # AFTER event date
    ]
    idx = P.RotationIndex(snaps)
    hit = idx.lookup("AAA", pd.Timestamp("2026-07-01"))
    assert hit is not None
    assert hit["date"] == "2026-06-28"          # must never pick the 07-10 row
    assert hit["score"] == 2.0

    # event strictly before the ONLY snapshot on record -> no match, not a
    # fallback to the future row.
    none_hit = idx.lookup("AAA", pd.Timestamp("2026-06-01"))
    assert none_hit is None


def test_build_end_to_end_respects_leak_rule(tmp_path):
    snaps = [
        _snap("2026-06-28", "k1", ["AAA", "BBB", "CCC"], "leading", 1.0, 1.0, 2.0),
        _snap("2026-07-10", "k1", ["AAA", "BBB", "CCC"], "lagging", -3.0, -3.0, -9.0),
    ]
    _write_snapshots(tmp_path, snaps)
    fires = pd.DataFrame([
        {"ticker": "AAA", "date": pd.Timestamp("2026-07-01"), "tier": "T1", "sub": "deep",
         "ticks": 0.0, "not_topped": True, "eligible": True, "panel": "deep"},
    ])
    fp = tmp_path / "data/research"
    fp.mkdir(parents=True, exist_ok=True)
    fires.to_parquet(fp / "gate_fires_deep.parquet", index=False)

    df = P.build(root=tmp_path)
    row = df.iloc[0]
    assert row["match_found"]
    assert str(row["rotation_asof"].date()) == "2026-06-28"
    assert row["rotation_quadrant"] == "leading"   # not the future 'lagging' row


# --------------------------------------------------------------------------- #
# (b) classification logic — one fixture per state
# --------------------------------------------------------------------------- #
def test_classify_tailwind():
    state = P.classify_sponsorship("leading", rs_mom=1.5, accel=0.5, score=1.5, n_members=8, stale=False)
    assert state == "TAILWIND"


def test_classify_early_repair_substitute():
    # rs_ratio unavailable -> substitute rs_mom>0 and score<0
    state = P.classify_sponsorship("improving", rs_mom=0.5, accel=0.0, score=-0.5, n_members=6, stale=False)
    assert state == "EARLY_REPAIR"


def test_classify_confirmed_leadership_substitute():
    # rs_ratio unavailable -> substitute score>0; keep score < 1.0 so TAILWIND doesn't pre-empt it
    state = P.classify_sponsorship("leading", rs_mom=0.8, accel=-0.1, score=0.5, n_members=6, stale=False)
    assert state == "CONFIRMED_LEADERSHIP"


def test_classify_headwind_lagging():
    state = P.classify_sponsorship("lagging", rs_mom=0.1, accel=0.1, score=0.1, n_members=6, stale=False)
    assert state == "HEADWIND"


def test_classify_headwind_weakening_neg_rs_mom():
    # score<=0 here (not >0) so ROLLOVER's tighter condition doesn't apply.
    state = P.classify_sponsorship("weakening", rs_mom=-1.0, accel=0.1, score=-0.1, n_members=6, stale=False)
    assert state == "HEADWIND"


def test_classify_rollover_substitute():
    # ROLLOVER's condition (weakening, rs_mom<0, score>0) is a strict SUBSET
    # of HEADWIND's "weakening and rs_mom<0" clause, so the doc's literal
    # rule order would make ROLLOVER unreachable — sponsorship_phase0.py
    # documents this and checks ROLLOVER first as the more specific case.
    state = P.classify_sponsorship("weakening", rs_mom=-0.5, accel=0.5, score=0.5, n_members=6, stale=False)
    assert state == "ROLLOVER"


def test_classify_headwind_weakening_negative_score_not_rollover():
    # same quadrant/rs_mom as the ROLLOVER fixture but score<=0 -> falls
    # through to the generic HEADWIND weakening clause instead.
    state = P.classify_sponsorship("weakening", rs_mom=-0.5, accel=0.5, score=-0.2, n_members=6, stale=False)
    assert state == "HEADWIND"


def test_classify_neutral_fallback():
    state = P.classify_sponsorship(None, rs_mom=None, accel=None, score=None, n_members=None, stale=False)
    assert state == "NEUTRAL"


def test_classify_stale_forces_neutral():
    state = P.classify_sponsorship("leading", rs_mom=1.5, accel=0.5, score=1.5, n_members=8, stale=True)
    assert state == "NEUTRAL"


# --------------------------------------------------------------------------- #
# (c) thin-group handling
# --------------------------------------------------------------------------- #
def test_thin_group_forces_neutral_and_confidence_none():
    state = P.classify_sponsorship("leading", rs_mom=1.5, accel=0.5, score=1.5, n_members=2, stale=False)
    assert state == "NEUTRAL"
    assert P._confidence_tier(2) == "none"
    assert P._confidence_tier(None) == "none"


def test_confidence_tier_bands():
    assert P._confidence_tier(3) == "low"
    assert P._confidence_tier(5) == "low"
    assert P._confidence_tier(6) == "medium"
    assert P._confidence_tier(11) == "medium"
    assert P._confidence_tier(12) == "high"
    assert P._confidence_tier(200) == "high"


# --------------------------------------------------------------------------- #
# (d) coverage report never crashes on empty input
# --------------------------------------------------------------------------- #
def test_coverage_report_empty_input():
    empty = pd.DataFrame(columns=P._OUTPUT_COLS + ["_stale", "_rotation_key"])
    rep = P.coverage_report(empty)
    assert rep["total_events"] == 0
    assert rep["matched_pct"] == 0.0
    assert rep["missing_pct"] == 0.0


def test_build_no_snapshots_no_crash(tmp_path):
    fires = pd.DataFrame([
        {"ticker": "ZZZ", "date": pd.Timestamp("2026-07-01"), "tier": "T1", "sub": "deep",
         "ticks": 1.0, "not_topped": True, "eligible": True, "panel": "deep"},
    ])
    fp = tmp_path / "data/research"
    fp.mkdir(parents=True, exist_ok=True)
    fires.to_parquet(fp / "gate_fires_deep.parquet", index=False)
    # no snapshots.jsonl written at all
    df = P.build(root=tmp_path)
    assert len(df) == 1
    assert not df.iloc[0]["match_found"]
    rep = P.coverage_report(df)
    assert rep["missing_pct"] == 100.0
