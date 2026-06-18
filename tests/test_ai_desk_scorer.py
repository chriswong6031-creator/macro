"""AI Desk scorer (engine/ai_desk_scorer.py) — the durability engine, DETERMINISTIC.

Verifies the falsifier predicates score correctly against controlled closes (a `check`
is the FALSIFICATION condition → miss when it fires, else hit), that soft theses are
never fudged into a hit/miss, that not-yet-elapsed windows stay open, that scoring is
idempotent + append-only, and that the rolling track record aggregates by conviction —
the numbers the briefing reads back to calibrate conviction."""
from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from engine import ai_desk_scorer as sc  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
ASOF = "2026-01-05"
CHECK_BY = "2026-02-02"          # ~20 business days later
LATER = "2026-02-10"            # cache extends past check_by → window elapsed


def _mk_parquet(root, ticker, points):
    """points: list of (date, close)."""
    d = root / "data" / "yahoo"
    d.mkdir(parents=True, exist_ok=True)
    idx = pd.to_datetime([p[0] for p in points])
    pd.DataFrame({"close": [p[1] for p in points], "volume": [1] * len(points)},
                 index=idx).to_parquet(d / f"{ticker}.parquet")


def _thesis(tid, subject, lean, conv, check, entry, check_by=CHECK_BY):
    return {"id": tid, "logged_at": "x", "state_asof": ASOF, "subject": subject,
            "lean": lean, "conviction": conv, "horizon_d": 20,
            "falsifier": {"text": "t", "check": check}, "check_by": check_by,
            "entry_levels": entry, "status": "open"}


def _write_ledger(root, rows):
    d = root / "data" / "ai_desk"
    d.mkdir(parents=True, exist_ok=True)
    with open(d / "theses.jsonl", "a") as fh:
        for r in rows:
            fh.write(json.dumps(r) + "\n")


def _rel_check(ticker, op, thr):
    return {"kind": "rel_return", "subject_ticker": ticker, "vs": "SPY",
            "op": op, "threshold": thr, "horizon_d": 20}


def _new_root():
    return Path(tempfile.mkdtemp())


# --- rel_return: hit vs miss --------------------------------------------- #
def test_rel_return_overweight_hit_when_it_outperforms():
    root = _new_root()
    _mk_parquet(root, "XLE", [(ASOF, 100.0), (CHECK_BY, 110.0)])  # +10%
    _mk_parquet(root, "SPY", [(ASOF, 100.0), (CHECK_BY, 102.0)])  # +2%  → rel +8%
    _write_ledger(root, [_thesis("t1", "Energy", "overweight", "high",
                                 _rel_check("XLE", "<", -0.05), {"XLE": 100.0, "SPY": 100.0})])
    track = sc.run(root=root, today=pd.Timestamp(LATER))
    row = sc._load_scored(root)["t1"]
    assert row["outcome"] == "hit" and row["realized"] > 0.07
    assert row["directionally_correct"] is True
    assert track["overall"]["hits"] == 1 and track["by_conviction"]["high"]["n"] == 1


def test_rel_return_overweight_miss_when_it_underperforms():
    root = _new_root()
    _mk_parquet(root, "XLE", [(ASOF, 100.0), (CHECK_BY, 90.0)])   # -10%
    _mk_parquet(root, "SPY", [(ASOF, 100.0), (CHECK_BY, 105.0)])  # +5%  → rel -15%
    _write_ledger(root, [_thesis("t1", "Energy", "overweight", "medium",
                                 _rel_check("XLE", "<", -0.05), {"XLE": 100.0, "SPY": 100.0})])
    sc.run(root=root, today=pd.Timestamp(LATER))
    row = sc._load_scored(root)["t1"]
    assert row["outcome"] == "miss" and row["realized"] < -0.05
    assert row["directionally_correct"] is False


def test_rel_return_underweight_uses_opposite_sign():
    root = _new_root()
    _mk_parquet(root, "XLU", [(ASOF, 100.0), (CHECK_BY, 120.0)])  # +20% (bad for a short lean)
    _mk_parquet(root, "SPY", [(ASOF, 100.0), (CHECK_BY, 100.0)])  # flat → rel +20% > +0.05 → miss
    _write_ledger(root, [_thesis("t1", "Utilities", "underweight", "low",
                                 _rel_check("XLU", ">", 0.05), {"XLU": 100.0, "SPY": 100.0})])
    sc.run(root=root, today=pd.Timestamp(LATER))
    assert sc._load_scored(root)["t1"]["outcome"] == "miss"


# --- level: fade-fear VIX ------------------------------------------------ #
def _level_check():
    return {"kind": "level", "subject_ticker": "_VIX", "vs": None, "op": ">",
            "ref": "entry", "horizon_d": 20}


def test_fade_fear_hit_when_vix_stays_below_entry():
    root = _new_root()
    _mk_parquet(root, "_VIX", [(ASOF, 20.0), ("2026-01-20", 18.0), (LATER, 16.0)])
    _write_ledger(root, [_thesis("t1", "VIX", "fade-fear", "low", _level_check(), {"_VIX": 20.0})])
    sc.run(root=root, today=pd.Timestamp(LATER))
    row = sc._load_scored(root)["t1"]
    assert row["outcome"] == "hit" and row["directionally_correct"] is True


def test_fade_fear_miss_when_vix_makes_new_high():
    root = _new_root()
    _mk_parquet(root, "_VIX", [(ASOF, 20.0), ("2026-01-20", 28.0), (LATER, 17.0)])  # spike above entry
    _write_ledger(root, [_thesis("t1", "VIX", "fade-fear", "high", _level_check(), {"_VIX": 20.0})])
    sc.run(root=root, today=pd.Timestamp(LATER))
    assert sc._load_scored(root)["t1"]["outcome"] == "miss"


# --- soft is never fudged; not-ready stays open -------------------------- #
def test_soft_thesis_is_unscored_not_a_hit_or_miss():
    root = _new_root()
    _write_ledger(root, [_thesis("t1", "retail", "overweight", "low",
                                 {"kind": "soft", "reason": "basket"}, {})])
    track = sc.run(root=root, today=pd.Timestamp(LATER))
    assert sc._load_scored(root)["t1"]["outcome"] == "unscored"
    assert track["scored_total"] == 0 and track["unscored_soft"] == 1


def test_not_ready_window_stays_open():
    root = _new_root()
    _mk_parquet(root, "XLE", [(ASOF, 100.0), ("2026-01-12", 101.0)])   # cache stops BEFORE check_by
    _mk_parquet(root, "SPY", [(ASOF, 100.0), ("2026-01-12", 100.0)])
    _write_ledger(root, [_thesis("t1", "Energy", "overweight", "low",
                                 _rel_check("XLE", "<", -0.05), {"XLE": 100.0, "SPY": 100.0})])
    track = sc.run(root=root, today=pd.Timestamp("2026-01-13"))       # before check_by → not expired
    assert "t1" not in sc._load_scored(root)                          # not scored yet
    assert track["open"] == 1 and track["scored_total"] == 0


# --- idempotent + append-only ------------------------------------------- #
def test_scoring_is_idempotent():
    root = _new_root()
    _mk_parquet(root, "XLE", [(ASOF, 100.0), (CHECK_BY, 110.0)])
    _mk_parquet(root, "SPY", [(ASOF, 100.0), (CHECK_BY, 102.0)])
    _write_ledger(root, [_thesis("t1", "Energy", "overweight", "high",
                                 _rel_check("XLE", "<", -0.05), {"XLE": 100.0, "SPY": 100.0})])
    sc.run(root=root, today=pd.Timestamp(LATER))
    sc.run(root=root, today=pd.Timestamp(LATER))                      # second pass
    lines = (root / "data" / "ai_desk" / "scored.jsonl").read_text().splitlines()
    assert len(lines) == 1                                            # scored exactly once


def test_track_record_aggregates_by_conviction():
    root = _new_root()
    _mk_parquet(root, "XLE", [(ASOF, 100.0), (CHECK_BY, 120.0)])     # rel big + → high HIT
    _mk_parquet(root, "XLU", [(ASOF, 100.0), (CHECK_BY, 80.0)])      # rel big - → low MISS (overweight)
    _mk_parquet(root, "SPY", [(ASOF, 100.0), (CHECK_BY, 100.0)])
    _write_ledger(root, [
        _thesis("h", "Energy", "overweight", "high", _rel_check("XLE", "<", -0.05), {"XLE": 100.0, "SPY": 100.0}),
        _thesis("l", "Utilities", "overweight", "low", _rel_check("XLU", "<", -0.05), {"XLU": 100.0, "SPY": 100.0}),
    ])
    track = sc.run(root=root, today=pd.Timestamp(LATER))
    assert track["overall"]["n"] == 2 and track["overall"]["hits"] == 1
    assert track["by_conviction"]["high"]["hit_rate"] == 1.0
    assert track["by_conviction"]["low"]["hit_rate"] == 0.0
    assert "scored" in track["calibration_note"].lower()
    assert "已评分" in track["calibration_note_zh"]                     # bilingual note (display)


# --- the feedback loop closes: ai_desk reads track_record back ------------ #
def test_gather_desk_state_reads_track_record_back():
    from engine import ai_desk as d
    root = _new_root()
    (root / "site" / "basketdata").mkdir(parents=True)
    (root / "site" / "basketdata" / "flow.json").write_text(json.dumps(
        {"as_of": ASOF, "verdict": "display_only", "sectors": [], "baskets": [],
         "ai_handoff": {"overall_verdict": "display_only"}}))
    (root / "data" / "ai_desk").mkdir(parents=True)
    (root / "data" / "ai_desk" / "track_record.json").write_text(json.dumps(
        {"schema": sc.SCHEMA, "overall": {"hit_rate": 0.4}, "calibration_note": "lean low"}))
    state = d.gather_desk_state(root)
    assert state["track_record"]["calibration_note"] == "lean low"   # the loop is wired
