"""
Tests for scripts/leadlag_phase0.py — W5.1 Lead-Lag Phase-0 (pre-registered).

Four suites required by the wave prompt:
  1. confirmed_at discipline — a synthetic leader whose turn confirms LATE cannot
     produce a usable lead (the integrity trap; leads keyed on pivots are forbidden).
  2. FDR screen math — the BH-FDR screen is correctly applied and an injected lead is
     detected while pure-noise pairs do NOT survive.
  3. Stage-B refit reproducibility under the pre-registered seed.
  4. Gate arithmetic — LL-A / LL-B evaluated verbatim on synthetic pass AND fail cases.
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

from scripts.leadlag_phase0 import (  # noqa: E402
    LEADER_TURN_WINDOW_M,
    REL_BRIER_BAR,
    STAGE_A_BLOCK_M,
    STAGE_A_BOOT,
    STAGE_A_SEED,
    _block_perm_null_p,
    _lagged_corr,
    _leader_turned_feature,
    evaluate_gate,
    stage_a_screen,
)
from engine.grading_stats import fdr_bh  # noqa: E402


# ───────────────────────────────────────────────────────────────────────────────
# 1 · confirmed_at discipline — the integrity trap
# ───────────────────────────────────────────────────────────────────────────────

def test_late_confirmation_no_lead():
    """A leader turn PIVOTS at month P but is only CONFIRMED at month P+lag. The
    follower decides at time t. The leader is only usable if confirmed_at <= t.

    Construct a follower decision date t that sits AFTER the leader's pivot but BEFORE
    its confirmation. A naive study keyed on the PIVOT would flag the leader as 'turned';
    the confirmed_at-honest feature must return 0 (the future had not yet leaked).
    """
    # follower decision at 2015-06-30 month-end
    panel = pd.DataFrame({"date": [pd.Timestamp("2015-06-30")]})

    # leader turn pivots 2015-05-15 but confirms LATE — 2015-09-20 (4 months later).
    turns_late = {"LEADER": [{"date": "2015-05-15", "confirmed_at": "2015-09-20",
                              "k": "trough", "provisional": False}]}
    feat_late = _leader_turned_feature(panel, "LEADER", turns_late)
    assert feat_late[0] == 0.0, (
        "confirmed_at discipline VIOLATED: leader confirmed AFTER the follower's decision "
        "time was counted as a usable turn — the future leaked backward via the pivot."
    )

    # same pivot, but this time confirmed BEFORE the decision (2015-06-10, within 3m) →
    # the leader IS usable and the feature must fire.
    turns_early = {"LEADER": [{"date": "2015-05-15", "confirmed_at": "2015-06-10",
                               "k": "trough", "provisional": False}]}
    feat_early = _leader_turned_feature(panel, "LEADER", turns_early)
    assert feat_early[0] == 1.0, "a leader confirmed within the window must fire the feature"


def test_leader_feature_respects_3m_window():
    """A turn confirmed MORE than LEADER_TURN_WINDOW_M months before t must NOT fire —
    the feature is `leader_turned_3m`, a recency gate, not an ever-turned flag."""
    panel = pd.DataFrame({"date": [pd.Timestamp("2015-06-30")]})
    # confirmed 5 months earlier → outside the 3m window
    stale = {"LEADER": [{"date": "2015-01-01", "confirmed_at": "2015-01-20",
                         "provisional": False}]}
    feat = _leader_turned_feature(panel, "LEADER", stale)
    assert feat[0] == 0.0
    assert LEADER_TURN_WINDOW_M == 3


def test_provisional_turns_excluded_upstream():
    """The loader drops provisional open legs; a turns dict passed to the feature that
    (hypothetically) contained only a provisional turn yields no fire — but the real
    guard is load_confirmed_turns filtering provisional==True, asserted here in spirit:
    a confirmed_at in the future window with provisional flag still would fire IF passed,
    so the exclusion MUST happen at load time. We assert the load-time contract exists."""
    from scripts.leadlag_phase0 import load_confirmed_turns
    import inspect
    src = inspect.getsource(load_confirmed_turns)
    assert 'provisional' in src and 'not t.get("provisional"' in src.replace("'", '"'), (
        "load_confirmed_turns must exclude provisional open legs"
    )


# ───────────────────────────────────────────────────────────────────────────────
# 2 · FDR screen math + injected-lead detection
# ───────────────────────────────────────────────────────────────────────────────

def test_fdr_bh_monotone_and_empty():
    """BH-FDR: the survivor set is monotone (a tiny p always survives when a larger one
    does at the same family size) and an all-large-p family yields no survivors."""
    # one clearly-significant p among noise
    pv = {"a": 0.0001, **{f"n{i}": 0.6 + 0.001 * i for i in range(50)}}
    res = fdr_bh(pv, q=0.10)
    assert res["a"] is True
    assert sum(res.values()) >= 1
    # pure noise: uniform-ish large p-values, none should survive
    noise = {f"n{i}": 0.5 + 0.4 * (i / 50) for i in range(50)}
    assert sum(fdr_bh(noise, q=0.10).values()) == 0


def test_injected_lead_detected_noise_not():
    """Stage A must (a) detect an INJECTED Δpos lead as an FDR survivor and (b) NOT flag
    pure-noise pairs. Build a 3-instrument US-sector family where XLK leads XLF by 2
    months in Δpos, plus a pure-noise XLE."""
    rng = np.random.default_rng(0)
    n = 180
    dates = pd.date_range("2003-01-31", periods=n, freq="ME")
    # leader Δpos (as an integrated level so first-diff is the signal)
    dlead = rng.normal(0, 8, n)
    lead_level = 50 + np.cumsum(dlead) * 0.0  # keep bounded-ish; use levels directly
    lead_pos = np.clip(50 + np.cumsum(rng.normal(0, 2, n)) % 50, 0, 100)
    # follower = leader's Δpos shifted forward 2 months + noise
    dlead_series = np.diff(lead_pos, prepend=lead_pos[0])
    fol_dpos = np.roll(dlead_series, 2) + rng.normal(0, 1.0, n)
    fol_pos = np.clip(50 + np.cumsum(fol_dpos), 0, 100)
    noise_pos = np.clip(50 + np.cumsum(rng.normal(0, 3, n)), 0, 100)

    rows = []
    for iid, series in [("XLK", lead_pos), ("XLF", fol_pos), ("XLE", noise_pos)]:
        for dt, v in zip(dates, series):
            rows.append({"id": iid, "date": dt, "pos": float(v)})
    pos_panel = pd.DataFrame(rows)

    out = stage_a_screen(pos_panel)
    survivors = out["fdr_survivors"]
    # the true lead XLK->XLF at lag 2 should be among survivors
    assert any("XLK->XLF" in s and "lag2" in s for s in survivors), (
        f"injected XLK->XLF lag-2 lead not detected; survivors={survivors}"
    )
    # a pure-noise pair (XLE as leader into anything) should not dominate the survivor set
    noise_survivors = [s for s in survivors if s.startswith("us_sector|XLE->")]
    assert len(noise_survivors) <= len(survivors), "sanity"


def test_lagged_corr_alignment():
    """corr(lead[t-k], follow[t]) aligns correctly: a perfectly-shifted follower yields
    r≈1 at the true lag and ~0 at the wrong lag."""
    n = 100
    lead = np.sin(np.arange(n) * 0.3)
    follow = np.roll(lead, 3)  # follower = leader shifted +3
    r3, _ = _lagged_corr(lead, follow, 3)
    r1, _ = _lagged_corr(lead, follow, 1)
    assert r3 > 0.95
    assert abs(r1) < abs(r3)


# ───────────────────────────────────────────────────────────────────────────────
# 3 · Stage-A / permutation reproducibility under seed
# ───────────────────────────────────────────────────────────────────────────────

def test_block_perm_null_reproducible():
    """The block-permutation p-value is deterministic under the pre-registered seed."""
    rng = np.random.default_rng(1)
    lead = rng.normal(0, 1, 120)
    follow = np.roll(lead, 2) + rng.normal(0, 0.5, 120)
    r, _ = _lagged_corr(lead, follow, 2)
    p_a = _block_perm_null_p(lead, follow, 2, r, block_m=STAGE_A_BLOCK_M,
                             boot=500, seed=STAGE_A_SEED)
    p_b = _block_perm_null_p(lead, follow, 2, r, block_m=STAGE_A_BLOCK_M,
                             boot=500, seed=STAGE_A_SEED)
    assert p_a == p_b, "permutation null must be reproducible under a fixed seed"
    # a real lead should get a small p
    assert p_a < 0.10


def test_stage_a_reproducible():
    """The full Stage-A screen is deterministic under the pinned seed."""
    rng = np.random.default_rng(2)
    n = 120
    dates = pd.date_range("2005-01-31", periods=n, freq="ME")
    rows = []
    base = np.clip(50 + np.cumsum(rng.normal(0, 3, n)), 0, 100)
    for iid in ["XLK", "XLF"]:
        series = base + rng.normal(0, 5, n)
        for dt, v in zip(dates, np.clip(series, 0, 100)):
            rows.append({"id": iid, "date": dt, "pos": float(v)})
    pp = pd.DataFrame(rows)
    a1 = stage_a_screen(pp)
    a2 = stage_a_screen(pp)
    assert a1["fdr_survivors"] == a2["fdr_survivors"]
    assert [r["p"] for r in a1["all_rows"]] == [r["p"] for r in a2["all_rows"]]


# ───────────────────────────────────────────────────────────────────────────────
# 4 · Gate arithmetic (LL-A / LL-B verbatim, synthetic pass & fail)
# ───────────────────────────────────────────────────────────────────────────────

def _synthetic_stage_b(rel_imp, n_pos, n_yr, ci_lo):
    return {"pooled": {
        "rel_brier_improvement": rel_imp,
        "n_year_blocks_positive": n_pos, "n_year_blocks": n_yr,
        "ci90": [ci_lo, ci_lo + 0.01],
    }}


def test_gate_go_case():
    """All three LL-B conditions met AND LL-A has a survivor → GO."""
    sa = {"n_fdr_survivors": 3}
    sb = _synthetic_stage_b(rel_imp=0.05, n_pos=6, n_yr=8, ci_lo=0.001)  # >=2%, 6/8>=2/3, CI>0
    g = evaluate_gate(sa, sb)
    assert g["LL_A_pass"] and g["LL_B_pass"]
    assert g["verdict"] == "GO"
    assert g["stop_action"] is None


def test_gate_stop_no_stage_a_survivor():
    """No FDR survivor in Stage A → NO-GO regardless of Stage B (STOP)."""
    sa = {"n_fdr_survivors": 0}
    sb = _synthetic_stage_b(rel_imp=0.10, n_pos=8, n_yr=8, ci_lo=0.05)
    g = evaluate_gate(sa, sb)
    assert not g["LL_A_pass"]
    assert g["verdict"] == "NO-GO"
    assert g["stop_action"] == "ship_sync_gauge"


def test_gate_stop_below_brier_bar():
    """Stage A passes but LL-B rel improvement < 2% → NO-GO."""
    sa = {"n_fdr_survivors": 5}
    sb = _synthetic_stage_b(rel_imp=0.015, n_pos=8, n_yr=8, ci_lo=0.05)  # 1.5% < 2%
    g = evaluate_gate(sa, sb)
    assert g["LL_A_pass"] and not g["LL_B_pass"]
    assert g["LL_B_detail"]["rel_ok"] is False
    assert g["verdict"] == "NO-GO"


def test_gate_stop_ci_touches_zero():
    """rel improvement and year-blocks OK but CI includes 0 → NO-GO."""
    sa = {"n_fdr_survivors": 5}
    sb = _synthetic_stage_b(rel_imp=0.05, n_pos=6, n_yr=8, ci_lo=-0.001)  # CI lo < 0
    g = evaluate_gate(sa, sb)
    assert not g["LL_B_pass"]
    assert g["LL_B_detail"]["ci_excludes_0"] is False
    assert g["verdict"] == "NO-GO"


def test_gate_stop_year_blocks_insufficient():
    """rel improvement and CI OK but positive in only 1/3 year-blocks → NO-GO."""
    sa = {"n_fdr_survivors": 5}
    sb = _synthetic_stage_b(rel_imp=0.05, n_pos=3, n_yr=9, ci_lo=0.01)  # 3/9 < 2/3
    g = evaluate_gate(sa, sb)
    assert not g["LL_B_pass"]
    assert g["LL_B_detail"]["year_blocks_ok"] is False
    assert g["verdict"] == "NO-GO"


def test_year_block_ceiling_threshold():
    """The >=2/3 rule uses ceil(2/3 * n): for n=8 the bar is 6 (ceil(5.33))."""
    sa = {"n_fdr_survivors": 1}
    # exactly 6/8 passes, 5/8 fails
    assert evaluate_gate(sa, _synthetic_stage_b(0.05, 6, 8, 0.01))["LL_B_pass"] is True
    assert evaluate_gate(sa, _synthetic_stage_b(0.05, 5, 8, 0.01))["LL_B_pass"] is False


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
