"""Unit tests for engine.subsector_track_record — the forward outcome ledger."""
from __future__ import annotations

import json
from datetime import date, timedelta

import pandas as pd

from engine import subsector_track_record as S


def _payload(subs, emerging, fading):
    return {"subsectors": subs, "highlights": {"emerging": emerging, "fading": fading}}


def test_snapshot_idempotent(tmp_path):
    pay = _payload([{"key": "a", "name": "A", "theme": "T", "emerging_score": 2.0,
                     "rs_mom": 1.0, "accel": 3.0, "quadrant": "improving"}],
                   ["a"], [])
    mm = {"a": ["NVDA", "AAPL", "MSFT"]}
    assert S.snapshot(pay, mm, today="2026-06-28", root=tmp_path) == 1
    assert S.snapshot(pay, mm, today="2026-06-28", root=tmp_path) == 0   # same day → no dupes
    rows = [json.loads(x) for x in (tmp_path / "data/subsector_rotation/snapshots.jsonl").read_text().splitlines()]
    assert rows[0]["stage"] == "emerging" and rows[0]["lean"] == 1 and rows[0]["members"] == ["NVDA", "AAPL", "MSFT"]


def test_accruing_when_empty(tmp_path):
    tr = S.compute(today="2026-06-28", root=tmp_path)
    assert tr["verdict"] == "accruing" and tr["any_matured"] is False and tr["n_snapshots"] == 0
    assert tr["is_context_only"] is True


def _fake_prices(monkeypatch):
    # entry = 100 for everyone; exit encodes the move via a per-ticker table.
    exit_px = {"W": 110.0, "L": 90.0, "SPY": 100.0}   # W up 10%, L down 10%, SPY flat
    monkeypatch.setattr(S, "_covers", lambda t, root, end: True)
    monkeypatch.setattr(S, "_level_asof", lambda t, root, start: 100.0)
    monkeypatch.setattr(S, "_close_at", lambda t, root, end: exit_px.get(t[0] if t != "SPY" else "SPY", 100.0))


def _write_rows(tmp_path, rows):
    p = tmp_path / "data/subsector_rotation/snapshots.jsonl"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text("\n".join(json.dumps(r) for r in rows) + "\n")


def test_maturation_grades_calls(tmp_path, monkeypatch):
    _fake_prices(monkeypatch)
    d0 = (date(2026, 6, 28) - timedelta(days=30)).isoformat()
    rows = [
        # emerging with WINNER members → fwd>0 → HIT
        {"date": d0, "key": "e_hit", "name": "Ehit", "theme": "T", "score": 2.5, "lean": 1,
         "stage": "emerging", "members": ["W1", "W2", "W3"]},
        # emerging with LOSER members → fwd<0 → MISS (false judgement → error ledger)
        {"date": d0, "key": "e_miss", "name": "Emiss", "theme": "T", "score": 2.0, "lean": 1,
         "stage": "emerging", "members": ["L1", "L2", "L3"]},
        # fading with LOSER members → fwd<0 → HIT (correctly called the roll-over)
        {"date": d0, "key": "f_hit", "name": "Fhit", "theme": "T", "score": -1.0, "lean": -1,
         "stage": "fading", "members": ["L4", "L5", "L6"]},
        # too few priceable members → unscored (members table prices all, but only 2 → < _MIN_PRICED)
        {"date": d0, "key": "thin", "name": "Thin", "theme": "T", "score": 0.1, "lean": 0,
         "stage": "neutral", "members": ["W9", "W8"]},
    ]
    _write_rows(tmp_path, rows)
    tr = S.compute(today="2026-06-28", root=tmp_path)
    h21 = tr["horizons"]["21"]
    assert h21["n_matured"] == 3                                  # the 2-member 'thin' is dropped
    bs = h21["by_stage"]
    assert bs["emerging"]["n"] == 2 and bs["emerging"]["hit_rate"] == 0.5   # 1 hit / 1 miss
    assert bs["fading"]["n"] == 1 and bs["fading"]["hit_rate"] == 1.0
    # the falsified emerging call is logged in the error ledger
    misses = {m["key"] for m in tr["recent_misses"]}
    assert "e_miss" in misses and "e_hit" not in misses
    # still no significance on a tiny sample → not 'validated'
    assert tr["verdict"] in ("measuring", "accruing")


def test_horizon_gating(tmp_path, monkeypatch):
    _fake_prices(monkeypatch)
    # a call only 7 days old: matures at 5d, not at 21d.
    d0 = (date(2026, 6, 28) - timedelta(days=7)).isoformat()
    _write_rows(tmp_path, [{"date": d0, "key": "e", "name": "E", "theme": "T", "score": 1.0,
                            "lean": 1, "stage": "emerging", "members": ["W1", "W2", "W3"]}])
    tr = S.compute(today="2026-06-28", root=tmp_path)
    assert tr["horizons"]["5"]["n_matured"] == 1
    assert tr["horizons"]["21"]["n_matured"] == 0
