"""Tests for the forward PIT state accrual (engine/dislocation state_log).

The accrual is the validation clock for the mechanical-reversion fade edge: each
build appends today's dislocation + narrative state; forward returns are joined at
validation time. Invariants tested: the row maps every field, the merge is
keep-LAST per date (idempotent re-runs, forward dates accrue), and the IO wrapper
never raises / never writes on a missing snapshot. No network, no disk writes.

Run as a plain script:  python tests/test_dislocation_accrual.py
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from engine import dislocation as dz  # noqa: E402

_SNAP = {
    "asof": "2026-06-12", "verdict": "buyable_washout", "put_state": "put-present",
    "dislocation_active": True,
    "gate2": {"state": "awaiting_confirm"},
    "geo_reversibility": {"agreement": "diverges", "lean": "act"},
    "inputs": {"capitulation_active": True, "capitulation_strong": False,
               "vix": 34.2, "spy_drawdown_pct": -12.4, "vrp_pctile": 0.95},
}
_NDI = {"ndi": 81.5, "band": "high"}
_NEWS = {"events": {"unscheduled_share": 0.7}}
_GPR = {"pct": 95.1, "lean": "act"}


def test_state_row_maps_all_fields():
    r = dz.state_row(_SNAP, _NDI, _NEWS, gpr=_GPR)
    assert r["date"] == "2026-06-12" and r["verdict"] == "buyable_washout"
    assert r["put_state"] == "put-present" and r["dislocation_active"] is True
    assert r["cap_active"] is True and r["cap_strong"] is False
    assert r["vix"] == 34.2 and r["spy_dd_pct"] == -12.4 and r["vrp_pctile"] == 0.95
    assert r["gate2_state"] == "awaiting_confirm"
    assert r["gpr_pct"] == 95.1 and r["gpr_lean"] == "act" and r["geo_agreement"] == "diverges"
    assert r["ndi"] == 81.5 and r["ndi_band"] == "high"
    assert r["unscheduled_share"] == 0.7
    assert set(r) == set(dz._STATE_LOG_COLS)


def test_state_row_none_without_date():
    assert dz.state_row(None) is None
    assert dz.state_row({"verdict": "calm"}) is None         # no asof


def test_state_row_calm_minimal():
    r = dz.state_row({"asof": "2026-01-02", "verdict": "calm"})
    assert r["date"] == "2026-01-02" and r["verdict"] == "calm"
    assert r["vix"] is None and r["gpr_pct"] is None and r["ndi"] is None
    assert r["dislocation_active"] is False


def test_merge_keep_last_per_date_and_idempotent():
    r1 = dz.state_row(_SNAP, _NDI, _NEWS, gpr=_GPR)
    log1 = dz.merge_state_log(None, [r1])
    assert len(log1) == 1
    # same date, revised verdict -> keep LAST (state is deterministic; re-run overwrites)
    r1b = dict(r1, verdict="stand_aside")
    log2 = dz.merge_state_log(log1, [r1b])
    assert len(log2) == 1 and log2.iloc[0]["verdict"] == "stand_aside"
    # re-merging the identical row is a no-op
    assert len(dz.merge_state_log(log2, [r1b])) == 1


def test_merge_accrues_forward_dates_sorted():
    r1 = dz.state_row({"asof": "2026-06-12", "verdict": "calm"})
    r2 = dz.state_row({"asof": "2026-06-15", "verdict": "buyable_washout"})
    # insert out of order -> stored sorted by date
    log = dz.merge_state_log(dz.merge_state_log(None, [r2]), [r1])
    assert list(log["date"]) == ["2026-06-12", "2026-06-15"]
    assert list(log.columns) == list(dz._STATE_LOG_COLS)


def test_append_state_log_none_guard_does_not_write():
    # a missing snapshot must return None and never touch disk
    assert dz.append_state_log(None) is None
    assert dz.append_state_log({"verdict": "calm"}) is None   # no asof


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    for fn in fns:
        fn()
        print(f"ok  {fn.__name__}")
    print(f"\n{len(fns)} passed")
