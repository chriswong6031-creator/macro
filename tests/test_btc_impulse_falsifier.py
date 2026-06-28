"""P3 falsifier: backtest gate + forward-outcome ledger + radar auto-demote.

Run: .venv/bin/python -m tests.test_btc_impulse_falsifier
"""
from __future__ import annotations

import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

from engine import btc_impulse_radar_backtest as BT  # noqa: E402
from engine import btc_impulse_ledger as LED  # noqa: E402
from engine import btc_impulse_radar as R  # noqa: E402


def _sig_with_drops(n=480, seed=3):
    """Synthetic daily close with single-bar ~-8% drops at RANDOM (seeded)
    intervals. Single-bar (not 3-bar) so each crosses the label's -5% floor; and
    NON-periodic so a circular-shift permutation gives a clean p (a periodic
    schedule would re-align under shift and inflate the null)."""
    rng = np.random.default_rng(seed)
    idx = pd.date_range("2024-01-01", periods=n, freq="D")
    px = [60000.0]
    cooldown = 0
    while len(px) < n:
        if cooldown == 0 and rng.random() < 0.05:     # a single -8% shock bar
            px.append(px[-1] * 0.92); cooldown = 4
        else:
            px.append(px[-1] * 1.001); cooldown = max(0, cooldown - 1)
    return pd.DataFrame({"close": pd.Series(px[:n], index=idx)}, index=idx)


def _patch_fire_series(frame):
    """Patch the backtest's view of radar.fire_series to return `frame`."""
    orig = BT.radar.fire_series
    BT.radar.fire_series = lambda s=None: frame
    return orig


def test_validate_passes_when_leg_leads():
    sig = _sig_with_drops()
    close = sig["close"]
    down, _ = BT._labels(close)
    # d2 fires exactly on the pre-drop down-event bars (a perfect leader)
    d2 = down.fillna(False).copy()
    fires = pd.DataFrame({"d2": d2}, index=sig.index)
    orig = _patch_fire_series(fires)
    try:
        v = BT.validate(sig)
    finally:
        BT.radar.fire_series = orig
    assert v["ok"] and v["legs"]["d2"]["status"] == "leading"
    assert v["legs"]["d2"]["lift_holdout"] >= 1.5
    assert v["legs"]["d2"]["perm_p"] <= 0.05


def test_validate_fails_when_leg_stops_leading():
    sig = _sig_with_drops()
    rng = np.random.default_rng(7)
    # fires RANDOM / independent of the drops -> lift ~1 < floor -> demoted
    d2 = pd.Series(rng.random(len(sig)) < 0.12, index=sig.index)
    fires = pd.DataFrame({"d2": d2}, index=sig.index)
    orig = _patch_fire_series(fires)
    try:
        v = BT.validate(sig)
    finally:
        BT.radar.fire_series = orig
    assert v["ok"] and v["all_pass"] is False
    assert v["legs"]["d2"]["status"] == "demoted"


def test_main_exit_code_reflects_pass(monkeypatch_free=True):
    """main() returns 1 when an act leg fails, 0 when all lead (smoke)."""
    sig = _sig_with_drops()
    rng = np.random.default_rng(1)
    fires = pd.DataFrame({"d2": pd.Series(rng.random(len(sig)) < 0.12, index=sig.index)})
    orig_fs = _patch_fire_series(fires)
    orig_read = BT.store.read
    BT.store.read = lambda ns, nm: sig if (ns, nm) == ("vector", "signals") else orig_read(ns, nm)
    tmp = Path(tempfile.mkdtemp()) / "gate.json"
    orig_path = BT.gate_path
    BT.gate_path = lambda: tmp
    try:
        rc = BT.main()
    finally:
        BT.radar.fire_series = orig_fs
        BT.store.read = orig_read
        BT.gate_path = orig_path
    assert rc == 1                      # a random (non-leading) leg fails the gate


def test_radar_auto_demotes_on_gate():
    """The radar zeroes an act leg's points when the gate marks it demoted."""
    import engine.btc_impulse_radar_backtest as bt
    orig = bt.load_gate
    bt.load_gate = lambda: {"legs": {"d2": {"status": "demoted"},
                                     "d3": {"status": "leading"},
                                     "u1": {"status": "leading"}}}
    try:
        out = R.compute()              # real data
    finally:
        bt.load_gate = orig
    if not out.get("ok"):
        return                          # stores absent -> skip
    d2 = next(l for l in out["down"]["legs"] if l["key"] == "d2_dvol")
    assert d2["demoted"] is True and d2["points"] == 0.0
    assert "DEMOTED" in d2["honesty"]


def test_ledger_stamp_and_grade_roundtrip():
    tmp = Path(tempfile.mkdtemp()) / "ledger.jsonl"
    orig = LED._path
    LED._path = lambda: tmp
    try:
        idx = pd.date_range("2024-01-01", periods=10, freq="D")
        # a fired DOWN leg followed by a real -6% move -> should grade down_hit=True
        close = pd.Series([100, 100, 100, 100, 100, 94, 93, 93, 93, 93.0], index=idx)
        sig = pd.DataFrame({"close": close}, index=idx)
        radar = {"ok": True, "asof": "2024-01-05",
                 "down": {"score": 70, "ladder": "trigger", "act_live": True,
                          "legs": [{"key": "d2_dvol", "fired_today": True}]},
                 "up": {"score": 0, "ladder": "quiet", "act_live": False, "legs": []}}
        LED.stamp(radar, sig.loc[:"2024-01-05"])
        assert len(LED.load()) == 1
        LED.stamp(radar, sig.loc[:"2024-01-05"])      # idempotent on asof
        assert len(LED.load()) == 1
        summ = LED.grade(sig)                          # now the row matures (3d fwd)
        rows = LED.load()
        assert rows[0]["outcome"]["matured"] is True
        assert rows[0]["outcome"]["down_hit"] is True  # -6% within 3d after a down fire
        assert summ["down"]["hit_rate"] == 1.0
    finally:
        LED._path = orig


def test_ledger_grade_skips_a_bad_row():
    """Audit MEDIUM: one corrupt/hand-edited asof must NOT abort grading of every
    other matured row (the live hit-rate display must keep filling)."""
    tmp = Path(tempfile.mkdtemp()) / "ledger.jsonl"
    orig = LED._path
    LED._path = lambda: tmp
    try:
        idx = pd.date_range("2024-01-01", periods=12, freq="D")
        close = pd.Series(100.0, index=idx)
        sig = pd.DataFrame({"close": close}, index=idx)
        LED._write([
            {"asof": "2024-01-02", "fires": {"d2": True, "d3": False, "u1": False}, "outcome": None},
            {"asof": "not-a-date", "fires": {"d2": True, "d3": False, "u1": False}, "outcome": None},
            {"asof": "2024-01-03", "fires": {"d2": True, "d3": False, "u1": False}, "outcome": None},
        ])
        summ = LED.grade(sig)
        rows = LED.load()
        assert summ["ok"] is True
        assert rows[0]["outcome"] is not None and rows[2]["outcome"] is not None   # valid rows graded
        assert rows[1]["outcome"] is None                                          # bad row skipped, not fatal
    finally:
        LED._path = orig


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    for fn in fns:
        fn(); print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} tests passed")
