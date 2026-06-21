"""master_brain_scorer — grades the brain's own cross-asset leans (Phase C, deterministic).

Mirrors test_ai_desk_scorer: a `check` is the FALSIFICATION condition (miss when it fires,
else hit); soft is never fudged; not-ready stays open; expired after the grace window; scoring
is idempotent; degrades on a missing ledger. Closes the flagship loop's write side.
"""
from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from engine import master_brain_scorer as mbs  # noqa: E402
from engine import desk_scorer as ds  # noqa: E402

ASOF = "2026-01-05"
CHECK_BY = "2026-02-02"
LATER = "2026-02-10"


def _mk_parquet(root, ticker, points):
    d = root / "data" / "yahoo"
    d.mkdir(parents=True, exist_ok=True)
    idx = pd.to_datetime([p[0] for p in points])
    pd.DataFrame({"close": [p[1] for p in points], "volume": [1] * len(points)},
                 index=idx).to_parquet(d / f"{ticker}.parquet")


def _rel_check(ticker, op, thr):
    return {"kind": "rel_return", "subject_ticker": ticker, "vs": "SPY",
            "op": op, "threshold": thr, "horizon_d": 20}


def _thesis(tid, subject, lean, conv, check, entry, check_by=CHECK_BY):
    return {"id": tid, "logged_at": "x", "state_asof": ASOF, "subject": subject,
            "lean": lean, "conviction": conv, "horizon_d": 20,
            "falsifier": {"text": "t", "check": check}, "check_by": check_by,
            "entry_levels": entry, "regime": "Goldilocks", "status": "open"}


def _write_ledger(root, rows):
    d = root / "data" / "master_brain"
    d.mkdir(parents=True, exist_ok=True)
    with open(d / "theses.jsonl", "a") as fh:
        for r in rows:
            fh.write(json.dumps(r) + "\n")


def _new_root():
    return Path(tempfile.mkdtemp())


def test_underweight_miss_when_subject_outperforms():
    root = _new_root()
    _mk_parquet(root, "HYG", [(ASOF, 100.0), (CHECK_BY, 110.0)])   # +10%
    _mk_parquet(root, "SPY", [(ASOF, 100.0), (CHECK_BY, 102.0)])   # +2%  → rel +8% > 0.05 → MISS
    _write_ledger(root, [_thesis("mb-1", "High-yield credit", "underweight", "high",
                                 _rel_check("HYG", ">", 0.05), {"HYG": 100.0, "SPY": 100.0})])
    track = mbs.run(root=root, today=pd.Timestamp(LATER))
    row = ds.load_scored(root, mbs._SCORED)["mb-1"]
    assert row["outcome"] == "miss"
    assert track["schema"] == "master_brain_track_record.v1"
    assert track["overall"]["misses"] == 1
    assert track["by_regime"]["Goldilocks"]["n"] == 1          # regime stamp → by_regime for free


def test_underweight_hit_when_subject_lags():
    root = _new_root()
    _mk_parquet(root, "HYG", [(ASOF, 100.0), (CHECK_BY, 101.0)])   # +1%
    _mk_parquet(root, "SPY", [(ASOF, 100.0), (CHECK_BY, 105.0)])   # +5%  → rel -4% < 0.05 → HIT
    _write_ledger(root, [_thesis("mb-1", "High-yield credit", "underweight", "high",
                                 _rel_check("HYG", ">", 0.05), {"HYG": 100.0, "SPY": 100.0})])
    track = mbs.run(root=root, today=pd.Timestamp(LATER))
    assert ds.load_scored(root, mbs._SCORED)["mb-1"]["outcome"] == "hit"
    assert track["overall"]["hits"] == 1


def test_soft_thesis_unscored():
    root = _new_root()
    _write_ledger(root, [_thesis("mb-s", "US dollar", "overweight", "low",
                                 {"kind": "soft", "reason": "uncached"}, {})])
    track = mbs.run(root=root, today=pd.Timestamp(LATER))
    assert track["unscored_soft"] == 1 and track["overall"]["n"] == 0


def test_idempotent_no_duplicate_scored():
    root = _new_root()
    _mk_parquet(root, "HYG", [(ASOF, 100.0), (CHECK_BY, 110.0)])
    _mk_parquet(root, "SPY", [(ASOF, 100.0), (CHECK_BY, 102.0)])
    _write_ledger(root, [_thesis("mb-1", "High-yield credit", "underweight", "high",
                                 _rel_check("HYG", ">", 0.05), {"HYG": 100.0, "SPY": 100.0})])
    mbs.run(root=root, today=pd.Timestamp(LATER))
    mbs.run(root=root, today=pd.Timestamp(LATER))
    n = len((root / "data" / "master_brain" / "scored.jsonl").read_text().splitlines())
    assert n == 1


def test_not_ready_stays_open():
    root = _new_root()
    _write_ledger(root, [_thesis("mb-1", "Small caps", "overweight", "low",
                                 _rel_check("IWM", "<", -0.05), {"IWM": 100.0, "SPY": 100.0})])
    track = mbs.run(root=root, today=pd.Timestamp(ASOF))    # before check_by, no data
    assert track["open"] == 1 and track["overall"]["n"] == 0


def test_degrades_on_missing_ledger():
    track = mbs.run(root=_new_root(), today=pd.Timestamp(LATER))
    assert track["overall"]["n"] == 0                       # never raises, empty track record
