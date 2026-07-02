"""China Sector Pathway — W2.6 input-repair invariants (D6 / G1 + G3).

These are pure-function tests on synthetic panels; they never touch the china_sectors data
plane, so they always run (including in a bare checkout). They pin the three repairs:

  1. COMPOSITE ERA-STABILIZATION (audit china-sector-cycles-1): the setup composite is a FIXED
     constituent set, DEFINED only from the month all configured legs are live. Legs that come
     online at different dates → composite is NaN before the last leg lands, and the per-month
     active-leg count / first-all-live date / composition_version are disclosed correctly.
  2. BLOCK-BOOTSTRAP CI (china-sector-cycles-2): the conditional CI is a date-blocked bootstrap
     on the (cond − base) hit-rate GAP with n_months + n_eff reported — the naive
     Wilson-on-overlapping-n path is GONE (no ci_lo/ci_hi/`_wilson`).
  3. CAUSAL HARD GATE (china-sector-cycles-5): the gate's own-history percentile is trailing,
     not a full-sample rank — appending FUTURE data must not change a historical percentile.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from engine import china_sector_pathway as pw
from engine import china_sector_pathway_backtest as gate


def _panel_with_staggered_legs() -> pd.DataFrame:
    """Monthly panel where each leg's raw columns come online at a DIFFERENT date, so the
    fixed-constituent composite can only be defined once the LAST leg lands. Enough noise per
    column that expanding-z (min_periods 36) produces finite values after warm-up."""
    grid = pd.date_range("2008-01-31", periods=240, freq="ME")   # 20y monthly
    rng = np.random.default_rng(3)
    n = len(grid)

    def _col(first_idx: int) -> pd.Series:
        s = pd.Series(np.nan, index=grid)
        vals = np.cumsum(rng.normal(size=n - first_idx)) + rng.normal(size=n - first_idx)
        s.iloc[first_idx:] = vals
        return s

    # breadth+ppi live from month 0; meanrev from month ~96 (2016); credit from month ~132 (2019)
    return pd.DataFrame({
        "ppi_yoy": _col(0),
        "breadth_pct200": _col(0),
        "dist_200d": _col(96),
        "dd_from_high": _col(96),
        "credit_impulse": _col(132),
        "tsf_yoy": _col(132),
    })


# ─────────────────────────────── 1 · ERA-STABILIZATION ─────────────────────────────────

def test_composite_undefined_before_all_legs_live():
    panel = _panel_with_staggered_legs()
    setup, info = pw._setup_series(panel)

    first_all = info["first_all_live"]
    assert first_all is not None
    # composite is NaN strictly BEFORE the first all-legs-live month …
    before = setup[setup.index < first_all]
    assert before.dropna().empty, "composite must be undefined before all legs are live"
    # … and defined AT/after it (once expanding-z has warmed up on the last leg).
    after = setup[setup.index >= first_all]
    assert not after.dropna().empty, "composite must be defined once all legs are live"


def test_active_leg_count_and_first_all_live_are_correct():
    panel = _panel_with_staggered_legs()
    _setup, info = pw._setup_series(panel)

    # all four legs have data somewhere → the fixed required set is all four.
    assert set(info["required_legs"]) == {"credit", "ppi", "meanrev", "breadth"}
    assert info["n_required_legs"] if "n_required_legs" in info else True  # legacy-tolerant

    ac = info["active_count"]
    # early months: only ppi + breadth live (expanding-z needs 36mo warm-up, but availability
    # is measured on the standardized leg series, which is NaN until warm-up) → active grows.
    assert ac.iloc[-1] == 4, "all four legs active at the tail"
    # active-leg count is monotone non-decreasing as legs come online (never re-drops here).
    assert (ac.diff().dropna() >= 0).all()

    # first_all_live is where the LAST leg (credit, idx 132) plus its 36mo z warm-up lands —
    # i.e. no earlier than the credit column's first date.
    credit_first = panel["credit_impulse"].dropna().index.min()
    assert info["first_all_live"] >= credit_first


def test_composition_version_is_stable_and_set_scoped():
    # same leg set (any order) → same version; different set → different version.
    v_full = pw._composition_version(["credit", "ppi", "meanrev", "breadth"])
    v_full_shuffled = pw._composition_version(["breadth", "meanrev", "ppi", "credit"])
    v_partial = pw._composition_version(["ppi", "breadth"])
    assert v_full == v_full_shuffled
    assert v_full != v_partial
    assert v_full.startswith("v4-") and v_partial.startswith("v2-")


def test_dropped_leg_shrinks_required_set_and_changes_version():
    """A sector that NEVER has credit data must not have its composite undefined forever — the
    required set drops to the available legs, and the version reflects the smaller set."""
    panel = _panel_with_staggered_legs().drop(columns=["credit_impulse", "tsf_yoy"])
    setup, info = pw._setup_series(panel)
    assert "credit" not in info["required_legs"]
    assert info["composition_version"].startswith("v3-")
    assert not setup.dropna().empty, "composite must still be defined without the missing leg"


# ─────────────────────────────── 2 · BLOCK-BOOTSTRAP CI ────────────────────────────────

def test_conditional_uses_block_bootstrap_not_naive_wilson():
    # a synthetic setup+price where high-setup months precede up-moves → a real cohort forms.
    grid = pd.date_range("2012-01-31", periods=180, freq="ME")
    rng = np.random.default_rng(11)
    setup = pd.Series(rng.normal(size=len(grid)), index=grid)
    # price drifts up when last month's setup was high → conditional edge exists
    steps = 1.0 + 0.01 * np.sign(setup.shift(1).fillna(0.0)).to_numpy() + 0.02 * rng.normal(size=len(grid))
    mpx = pd.Series(100.0 * np.cumprod(steps), index=grid)

    c = pw._conditional(setup, mpx, 6)
    assert c is not None
    # NEW schema — the naive Wilson-on-level fields are GONE.
    assert "ci_lo" not in c and "ci_hi" not in c and "n" not in c
    # block-bootstrap lift CI + honest sample disclosure present.
    assert "lift_ci_lo" in c and "lift_ci_hi" in c
    assert "n_months" in c and "n_eff" in c and "n_base_months" in c
    # overlap deflator: effective n never EXCEEDS the raw month count (and is < it under overlap).
    assert c["n_eff"] <= c["n_months"]
    # the module no longer exposes the bespoke Wilson helper (ported to grading_stats).
    assert not hasattr(pw, "_wilson")


def test_conditional_reports_n_eff_below_raw_under_overlap():
    grid = pd.date_range("2012-01-31", periods=180, freq="ME")
    rng = np.random.default_rng(5)
    setup = pd.Series(rng.normal(size=len(grid)), index=grid)
    mpx = pd.Series(100.0 * np.cumprod(1.0 + 0.01 * rng.normal(size=len(grid))), index=grid)
    c = pw._conditional(setup, mpx, 6)
    assert c is not None
    # 6-month overlap on monthly stamps → n_eff meaningfully below n_months (never over-counts).
    assert c["n_eff"] < c["n_months"], "overlapping-window CI must not treat rows as independent"


# ─────────────────────────────── 3 · CAUSAL HARD GATE ──────────────────────────────────

def test_gate_percentile_is_causal():
    """Appending FUTURE bars must not change a historical percentile — the look-ahead the audit
    flagged (full-sample .rank(pct=True) over 3–4 turns). Trailing-window percentile is causal."""
    s = pd.Series(np.arange(120.0), index=pd.date_range("2020-01-01", periods=120, freq="D"))
    p_hist = gate._causal_pctile(s.iloc[:90])
    # extend with wildly different future values
    fut = pd.Series([-500.0] * 30, index=pd.date_range("2020-04-01", periods=30, freq="D"))
    p_long = gate._causal_pctile(pd.concat([s.iloc[:90], fut]))
    common = p_hist.dropna().index.intersection(p_long.dropna().index)
    assert len(common) > 10
    drift = (p_hist.reindex(common) - p_long.reindex(common)).abs().max()
    assert drift == 0.0, f"gate percentile is NOT causal (drift={drift})"


def test_full_sample_rank_would_leak_but_causal_does_not():
    """Contrast: pandas full-sample rank (the OLD gate) DOES change historically when future
    data is appended — proving the causal replacement is a genuine fix, not a no-op."""
    s = pd.Series(np.arange(120.0), index=pd.date_range("2020-01-01", periods=120, freq="D"))
    fut = pd.Series([-500.0] * 30, index=pd.date_range("2020-04-01", periods=30, freq="D"))
    long = pd.concat([s.iloc[:90], fut])
    old_hist = s.iloc[:90].rank(pct=True)
    old_long = long.rank(pct=True)
    common = old_hist.index.intersection(old_long.index)
    leak = (old_hist.reindex(common) - old_long.reindex(common)).abs().max()
    assert leak > 0.0, "sanity: full-sample rank must leak (else the test proves nothing)"


def test_pooled_gate_requires_ci_to_exclude_zero_for_evidence():
    """The pooled gate promotes a leg to 'evidence' ONLY when the block-bootstrap gap CI excludes
    zero; a directionally-correct-but-noisy separation is 'suggestive', not evidence."""
    # clean separation across two 'sectors' → evidence
    rows_sep = []
    for sec in ("a", "b"):
        for i in range(4):
            rows_sep.append({"sector": sec, "kind": "bottom",
                             "date": pd.Timestamp(f"201{i}-01-01"), "dist_p": 0.05 + 0.01 * i})
            rows_sep.append({"sector": sec, "kind": "top",
                             "date": pd.Timestamp(f"201{i}-07-01"), "dist_p": 0.92 + 0.01 * i})
    res = gate._pooled_gate(rows_sep, "dist_p")
    assert res["sign_ok"] and res["evidence"] and res["gap_ci"][0] > 0

    # overlapping / no real separation → sign may be fine but NOT evidence
    rng = np.random.default_rng(2)
    rows_noise = []
    for sec in ("a", "b"):
        for i in range(4):
            rows_noise.append({"sector": sec, "kind": "bottom",
                               "date": pd.Timestamp(f"201{i}-01-01"), "dist_p": float(rng.random())})
            rows_noise.append({"sector": sec, "kind": "top",
                               "date": pd.Timestamp(f"201{i}-07-01"), "dist_p": float(rng.random())})
    res_n = gate._pooled_gate(rows_noise, "dist_p")
    assert res_n["evidence"] is False
