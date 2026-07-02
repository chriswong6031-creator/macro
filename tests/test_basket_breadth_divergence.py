"""Intra-basket breadth-DIVERGENCE texture (engine.basket_breadth_divergence).

Pins the four load-bearing contracts. (1) The signature fires: a level PINNED by two
mega-winners while 8/10 members roll over must read elevated/high. (2) No signal on a
healthy basket. (3) NO FALSE TOP: a visible decline (basket well off its high) returns
risk 0 exactly — every leg is pinned-gated. (4) NO LEAK: the forward-log grader anchors
on the stamp-date close with the outcome window STRICTLY after (the T+1-fill convention,
= calibrate_baskets._fwd_dd i+1..i+h); a marker-date variant that lets the stamp-day move
into the "forward" window must overstate the drawdown (the repo's measured +5.7pp/10d
trap, engine.signal_quality §W6-CN / tests/test_signal_quality_no_leak.py). Plus the
keep-first forward log and the additive theme_textures wiring. Synthetic only; no network.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from engine import basket_breadth_divergence as bd
from engine import basket_score as bs


def _matrix(n_days=320, n_up=180, decliners=8, winners=2,
            up=0.002, fade=-0.0025, win=0.010):
    """Member close matrix: everyone rises for n_up days, then `decliners` fade at `fade`/d
    while `winners` melt up at `win`/d — sized so the EW mean daily return stays ~0 and the
    LEVEL sits pinned at its high while the membership rolls over underneath."""
    idx = pd.date_range("2024-01-02", periods=n_days, freq="B")
    cols = {}
    for j in range(decliners + winners):
        r = np.full(n_days, up)
        r[n_up:] = fade if j < decliners else win
        cols[f"M{j}"] = 100.0 * np.cumprod(1 + r)
    C = pd.DataFrame(cols, index=idx)
    lvl = (1.0 + C.pct_change(fill_method=None).mean(axis=1).fillna(0.0)).cumprod()
    return C, lvl


def test_pinned_level_with_rolling_members_fires():
    C, lvl = _matrix()          # 2 winners mask 8 decliners; EW level ~flat at the high
    snap = bd.breadth_divergence(C, lvl)
    assert snap["directional"] is False
    assert snap["pinned"] is True
    assert snap["risk"] is not None and snap["risk"] >= 0.6
    assert snap["band"] in ("elevated", "high")
    assert 1 <= len(snap["reasons"]) <= 4
    # the raw stamped fields are populated (the forward log consumes them)
    assert snap["basket_off_high"] is not None and snap["basket_off_high"] >= -0.06
    assert snap["member_dd_med"] is not None and snap["member_dd_med"] < -0.10
    assert snap["pct_above_50"] is not None and snap["pct_above_50"] <= 0.5


def test_all_healthy_reads_zero():
    C, lvl = _matrix(decliners=0, winners=10, win=0.002)   # everyone trending, no divergence
    snap = bd.breadth_divergence(C, lvl)
    assert snap["risk"] == 0.0 and snap["band"] == "low" and snap["reasons"] == []


def test_not_pinned_decline_is_not_a_false_top():
    # ALL members (and the basket) visibly -25%+ off the high: a bear is not a HIDDEN top.
    C, lvl = _matrix(decliners=10, winners=0, fade=-0.003)
    snap = bd.breadth_divergence(C, lvl)
    assert snap["pinned"] is False
    assert snap["risk"] == 0.0 and snap["band"] == "low" and snap["reasons"] == []


def test_never_raises_and_degrades_to_none():
    for args in ((None, None), (pd.DataFrame(), pd.Series(dtype=float)),
                 (pd.DataFrame({"A": [1.0, 2.0]}), pd.Series([1.0, 2.0]))):
        snap = bd.breadth_divergence(*args)
        assert snap["risk"] is None and snap["directional"] is False
    assert bd.series(None, None) is None


def test_theme_textures_wiring_is_additive():
    C, lvl = _matrix()
    base = bs.theme_textures(lvl, {}, {}, None, {}, {})            # legacy call: byte-identical
    assert "breadth_divergence" not in base
    withm = bs.theme_textures(lvl, {}, {}, None, {}, {}, mc_closes=C)
    tx = withm["breadth_divergence"]
    assert isinstance(tx, dict) and tx["directional"] is False and tx["band"] in (
        "low", "elevated", "high")


def test_forward_log_keep_first(tmp_path):
    p = tmp_path / "forward_log.parquet"
    tex = {"band": "elevated", "risk": 0.5, "basket_off_high": -0.02, "pct_above_50": 0.4}
    assert bd.log_stamp("cn_ai_compute", "china", tex, "dominant", "2026-06-30", path=p) is True
    # keep-first: the same (date, basket, region) key never restamps — even a HIGHER risk
    assert bd.log_stamp("cn_ai_compute", "china", {**tex, "risk": 0.9}, "fading",
                        "2026-06-30", path=p) is False
    assert bd.log_stamp("cn_ai_compute", "china", tex, "dominant", "2026-07-01", path=p) is True
    df = pd.read_parquet(p)
    assert len(df) == 2 and float(df[df["date"] == "2026-06-30"]["risk"].iloc[0]) == 0.5
    # a low band never stamps
    assert bd.log_stamp("x", "us", {**tex, "band": "low"}, "neutral", "2026-07-01", path=p) is False
    assert len(pd.read_parquet(p)) == 2


def _stamped_level():
    """60 flat closes at 100, then the STAMP-DAY close drops to 90 (the move that fired the
    detector), then 21 closes at 88. Stamp date = the 90-close bar."""
    idx = pd.date_range("2026-01-02", periods=90, freq="B")
    v = np.concatenate([np.full(60, 100.0), [90.0], np.full(29, 88.0)])
    return pd.Series(v, index=idx), idx[60]


def test_grade_anchors_on_stamp_close_equals_t_plus_1_fill():
    lvl, stamp = _stamped_level()
    got = bd.realized_fwd_dd(lvl, stamp, h=21)
    # the T+1-fill convention, computed independently: anchor = the stamp-date close (the
    # bar at which the band was knowable), outcome = min of the 21 closes STRICTLY after.
    s = lvl.dropna()
    anchor = float(s.loc[stamp])
    fwd = s.loc[s.index > stamp].iloc[:21]
    expect = float(fwd.min() / anchor - 1.0)
    assert got is not None and abs(got - expect) < 1e-12
    assert abs(got - (88.0 / 90.0 - 1.0)) < 1e-12


def test_marker_date_variant_fails_the_no_leak_guard():
    """The FORBIDDEN variant: anchoring the outcome window so the stamp-day move counts as
    'forward' (anchor = the close BEFORE the stamp, window from the stamp bar). On a fixture
    where the stamp-day drop is what fired the detector, that variant must overstate the
    achieved drawdown — the +5.7pp/10d marker-date trap. It must NOT equal the honest grade."""
    lvl, stamp = _stamped_level()
    honest = bd.realized_fwd_dd(lvl, stamp, h=21)
    s = lvl.dropna()
    pos = s.index.get_loc(stamp)
    leak_anchor = float(s.iloc[pos - 1])                    # pre-stamp close
    leak_window = s.iloc[pos:pos + 21]                      # includes the stamp-day drop
    leak = float(leak_window.min() / leak_anchor - 1.0)
    assert leak != honest
    assert leak < honest, "marker-date grading must overstate the drawdown on this fixture"


def test_grade_forward_log_lead_time_and_base_rate():
    lvl, stamp = _stamped_level()
    log_df = pd.DataFrame([{"date": str(stamp.date()), "basket_id": "b1", "region": "us",
                            "risk": 0.7, "band": "high"}])
    labels = pd.Series("dominant", index=lvl.index, dtype=object)
    flip_at = lvl.index[lvl.index.get_loc(stamp) + 7]       # guard flips 7 sessions later
    labels.loc[labels.index >= flip_at] = "deteriorating"
    out = bd.grade_forward_log(log_df, {"b1": lvl}, {"b1": labels}, h=21)
    assert out["n"] == 1
    row = out["rows"][0]
    assert row["lead_vs_guard_days"] == 7
    assert abs(row["fwd_dd"] - (88.0 / 90.0 - 1.0)) < 1e-12
    assert out["base_rate"] is not None and 0.0 <= out["base_rate"] <= 1.0
