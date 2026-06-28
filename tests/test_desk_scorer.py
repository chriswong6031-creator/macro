"""Shared falsifiable-thesis scorer (engine/desk_scorer.py).

engine.ai_desk_scorer is now a thin binding over this module; test_ai_desk_scorer.py
proves the ai_desk behaviour is byte-identical post-extraction. These tests prove the
EXTRACTED engine is genuinely reusable by an ARBITRARY desk: custom ledger paths +
schema + calibration note, an independent track record, and that two desks pointed at
different paths don't collide.
"""
from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from engine import desk_scorer as ds  # noqa: E402

ASOF = "2026-01-05"
CHECK_BY = "2026-02-02"
LATER = "2026-02-10"

LEDGER = ("data", "mydesk", "theses.jsonl")
SCORED = ("data", "mydesk", "scored.jsonl")
TRACK = ("data", "mydesk", "track_record.json")
SCHEMA = "mydesk_track_record.v1"


def _mk_parquet(root, ticker, points):
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


def _rel_check(ticker, op, thr):
    return {"kind": "rel_return", "subject_ticker": ticker, "vs": "SPY",
            "op": op, "threshold": thr, "horizon_d": 20}


def _write_ledger(root, ledger_path, rows):
    out = root.joinpath(*ledger_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    with open(out, "a") as fh:
        for r in rows:
            fh.write(json.dumps(r) + "\n")


def _note(overall, by_conv):
    return f"{overall['n']} scored on a custom desk."


def _new_root():
    return Path(tempfile.mkdtemp())


def test_run_with_custom_paths_and_schema_scores_and_persists():
    root = _new_root()
    _mk_parquet(root, "XLE", [(ASOF, 100.0), (CHECK_BY, 110.0)])     # +10%
    _mk_parquet(root, "SPY", [(ASOF, 100.0), (CHECK_BY, 102.0)])     # +2%  → rel +8% → HIT
    _write_ledger(root, LEDGER, [_thesis("m1", "Energy", "overweight", "high",
                                         _rel_check("XLE", "<", -0.05), {"XLE": 100.0, "SPY": 100.0})])
    track = ds.run(root=root, today=pd.Timestamp(LATER), ledger_path=LEDGER, scored_path=SCORED,
                   track_path=TRACK, schema=SCHEMA, calibration_note_fn=_note, log_label="mydesk")
    assert track["schema"] == SCHEMA                                  # custom schema honoured
    assert track["overall"]["hits"] == 1
    assert track["by_conviction"]["high"]["n"] == 1
    assert track["calibration_note"] == "1 scored on a custom desk."  # injected note
    # persisted to the custom paths, not ai_desk's
    assert root.joinpath(*SCORED).exists()
    assert root.joinpath(*TRACK).exists()
    assert not (root / "data" / "ai_desk").exists()
    assert ds.load_scored(root, SCORED)["m1"]["outcome"] == "hit"


def test_soft_thesis_is_unscored():
    root = _new_root()
    _write_ledger(root, LEDGER, [_thesis("s1", "Cash", "neutral", "low",
                                         {"kind": "soft"}, {})])
    track = ds.run(root=root, today=pd.Timestamp(LATER), ledger_path=LEDGER, scored_path=SCORED,
                   track_path=TRACK, schema=SCHEMA, calibration_note_fn=_note)
    assert track["unscored_soft"] == 1
    assert track["overall"]["n"] == 0                                # never fudged into hit/miss


def test_custom_evaluator_kind_is_dispatched():
    """A desk can register its own predicate kind (e.g. thematic's theme_rel_return)."""
    root = _new_root()
    seen = {}

    def _theme_eval(check, entry, root_, asof, check_by):
        seen["called"] = True
        return {"outcome": "hit", "realized": 0.1, "directionally_correct": True}

    chk = {"kind": "theme_rel_return", "subject_ticker": "XLE", "vs": "SPY",
           "op": "<", "threshold": -0.05, "horizon_d": 20}
    _mk_parquet(root, "XLE", [(ASOF, 100.0), (CHECK_BY, 110.0)])
    _mk_parquet(root, "SPY", [(ASOF, 100.0), (CHECK_BY, 102.0)])
    _write_ledger(root, LEDGER, [_thesis("t1", "Energy", "overweight", "high", chk,
                                         {"XLE": 100.0, "SPY": 100.0})])
    track = ds.run(root=root, today=pd.Timestamp(LATER), ledger_path=LEDGER, scored_path=SCORED,
                   track_path=TRACK, schema=SCHEMA,
                   evaluators={**ds.EVALUATORS, "theme_rel_return": _theme_eval},
                   by_kind_keys=("rel_return", "theme_rel_return"), calibration_note_fn=_note)
    assert seen.get("called") is True
    assert track["overall"]["hits"] == 1
    assert track["by_kind"]["theme_rel_return"]["n"] == 1


def test_by_regime_breakdown_buckets_by_stamp():
    """A regime-stamped thesis is bucketed in by_regime (Minimum-Regime-Performance)."""
    root = _new_root()
    _mk_parquet(root, "XLE", [(ASOF, 100.0), (CHECK_BY, 110.0)])     # +10%
    _mk_parquet(root, "SPY", [(ASOF, 100.0), (CHECK_BY, 102.0)])     # +2%  → rel +8% → HIT
    th = _thesis("g1", "Energy", "overweight", "high",
                 _rel_check("XLE", "<", -0.05), {"XLE": 100.0, "SPY": 100.0})
    th["regime"] = "Goldilocks"                                       # stamped at log time
    _write_ledger(root, LEDGER, [th])
    track = ds.run(root=root, today=pd.Timestamp(LATER), ledger_path=LEDGER, scored_path=SCORED,
                   track_path=TRACK, schema=SCHEMA, calibration_note_fn=_note)
    assert track["by_regime"]["Goldilocks"]["n"] == 1
    assert track["by_regime"]["Goldilocks"]["hits"] == 1
    assert ds.load_scored(root, SCORED)["g1"]["regime"] == "Goldilocks"   # carried onto scored row


def test_by_regime_is_empty_without_stamps():
    """Unstamped theses leave by_regime empty — additive, no noise for desks not yet stamping."""
    root = _new_root()
    _mk_parquet(root, "XLE", [(ASOF, 100.0), (CHECK_BY, 110.0)])
    _mk_parquet(root, "SPY", [(ASOF, 100.0), (CHECK_BY, 102.0)])
    _write_ledger(root, LEDGER, [_thesis("u1", "Energy", "overweight", "high",
                                         _rel_check("XLE", "<", -0.05), {"XLE": 100.0, "SPY": 100.0})])
    track = ds.run(root=root, today=pd.Timestamp(LATER), ledger_path=LEDGER, scored_path=SCORED,
                   track_path=TRACK, schema=SCHEMA, calibration_note_fn=_note)
    assert track["by_regime"] == {}
    assert track["overall"]["n"] == 1


def test_two_desks_do_not_collide():
    root = _new_root()
    _mk_parquet(root, "XLE", [(ASOF, 100.0), (CHECK_BY, 110.0)])
    _mk_parquet(root, "SPY", [(ASOF, 100.0), (CHECK_BY, 102.0)])
    a_ledger = ("data", "deskA", "theses.jsonl")
    b_ledger = ("data", "deskB", "theses.jsonl")
    _write_ledger(root, a_ledger, [_thesis("a1", "Energy", "overweight", "high",
                                           _rel_check("XLE", "<", -0.05), {"XLE": 100.0, "SPY": 100.0})])
    ta = ds.run(root=root, today=pd.Timestamp(LATER), ledger_path=a_ledger,
                scored_path=("data", "deskA", "scored.jsonl"),
                track_path=("data", "deskA", "track_record.json"), schema="a.v1")
    tb = ds.run(root=root, today=pd.Timestamp(LATER), ledger_path=b_ledger,
                scored_path=("data", "deskB", "scored.jsonl"),
                track_path=("data", "deskB", "track_record.json"), schema="b.v1")
    assert ta["overall"]["n"] == 1 and ta["schema"] == "a.v1"
    assert tb["overall"]["n"] == 0 and tb["schema"] == "b.v1"         # B has no theses → independent
