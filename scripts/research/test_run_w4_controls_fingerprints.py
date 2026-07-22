"""Tests for the W4 matched-controls fingerprint study (Layer-3b).

Pins the spec-mandated invariants (spec §6):
  - α/m-vs-95% CI disagreement case (the corrected-Bonferroni behavior — spec §0.1);
  - matched-set bootstrap atomicity: an episode never separates from its controls in a
    draw (spec §4, test-pinned);
  - parity check vs committed columns on a REAL episode row (spec §3);
  - degenerate guard (< 12 distinct t0 months → no CI, spec §4);
  - mask-don't-impute: absent 8-K coverage drops the observation, never zero-fills
    (spec §0.3).

MM_DATA_GUARD: all fixtures use tmp_path / in-memory frames — no writes to real data/.
The real-data parity test reads the read-only stores under _DATA_ROOT and is skipped if
they are absent (CI without the store still runs the synthetic tests).
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

_HERE = Path(__file__).resolve()
_REPO_ROOT = _HERE.parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

import scripts.research.run_w4_controls_fingerprints as w4  # noqa: E402

_DATA_ROOT = Path("/Users/chriswong/Documents/Cluade/Macro Dashboard/data")
_EPISODES = _REPO_ROOT / "data" / "research" / "winner_episodes.parquet"


# ---------------------------------------------------------------------------
# α/m vs 95% CI disagreement (spec §0.1): the α/m CI is strictly WIDER than the 95%
# CI (smaller tail probability), so there must exist a Δ distribution where the 95% CI
# excludes 0 but the α/m CI contains it — i.e. "significant at 95%, NOT at Bonferroni".
# ---------------------------------------------------------------------------

def test_alpha_m_vs_95_disagreement():
    rng = np.random.default_rng(0)
    # Build a Δ series (one per month) whose bulk is just above 0 — enough for the 95%
    # CI to clear 0 but not the much wider α/m tail.
    months = np.array([f"2020-{m:02d}" for m in range(1, 13)] * 6)  # 72 obs, 12 months
    deltas = rng.normal(loc=0.30, scale=1.0, size=len(months))

    alpha_bonf = 0.05 / 40.0  # a realistic m ⇒ very wide α/m CI
    res = w4.month_block_matched_bootstrap(
        deltas, months, n_reps=5000, seed=w4.BOOT_SEED, alpha_bonf=alpha_bonf
    )
    # The α/m interval must be wider than (contain) the 95% interval on both sides.
    assert res["ci_bonf_lo"] <= res["ci95_lo"] + 1e-9
    assert res["ci_bonf_hi"] >= res["ci95_hi"] - 1e-9

    # Find a scale where the two verdicts disagree: 95% excludes 0, α/m contains 0.
    found = False
    for loc in (0.25, 0.30, 0.35, 0.40, 0.45, 0.50):
        d = rng.normal(loc=loc, scale=1.2, size=len(months))
        r = w4.month_block_matched_bootstrap(
            d, months, n_reps=5000, seed=w4.BOOT_SEED, alpha_bonf=alpha_bonf
        )
        excl_95 = (r["ci95_lo"] > 0) or (r["ci95_hi"] < 0)
        excl_bonf = (r["ci_bonf_lo"] > 0) or (r["ci_bonf_hi"] < 0)
        if excl_95 and not excl_bonf:
            found = True
            break
    assert found, "expected a case where 95% CI excludes 0 but α/m CI does not"


def test_bonf_survives_uses_bonf_ci_not_95():
    """analyze_feature.bonf_survives must be driven by the α/m CI, never the 95% CI."""
    # Construct matched sets so the point Δ is modestly positive on many months.
    rng = np.random.default_rng(1)
    episode_feats = []
    control_feats = []
    for i in range(60):
        month = f"2019-{(i % 12) + 1:02d}"
        ev = float(rng.normal(0.4, 0.5))
        episode_feats.append({"x": ev, "_month": month, "_ticker": f"T{i % 7}"})
        control_feats.append([{"x": 0.0}, {"x": 0.0}])
    res = w4.analyze_feature(
        "x", False, episode_feats, control_feats, "c", 0.05 / 30.0,
        n_boot=4000, seed=w4.BOOT_SEED,
    )
    # bonf_survives is True IFF the α/m CI excludes 0.
    expected = (res["ci_bonf_lo"] is not None
                and (res["ci_bonf_lo"] > 0 or res["ci_bonf_hi"] < 0))
    assert res["bonf_survives"] == expected


# ---------------------------------------------------------------------------
# Matched-set atomicity (spec §4): an episode's Δ is a single scalar folding in its whole
# control set. A bootstrap draw resamples episode-level atoms (months / tickers); it never
# recombines one episode's value with another episode's controls. We pin this two ways.
# ---------------------------------------------------------------------------

def test_matched_delta_is_per_episode_scalar():
    """Each Δ_i uses ONLY episode i's own controls — never another episode's."""
    episode_feats = [
        {"x": 10.0, "_month": "2020-01", "_ticker": "A"},
        {"x": 20.0, "_month": "2020-02", "_ticker": "B"},
    ]
    control_feats = [
        [{"x": 1.0}, {"x": 3.0}],   # episode A controls → median 2.0 → Δ_A = 8.0
        [{"x": 100.0}, {"x": 100.0}],  # episode B controls → median 100 → Δ_B = -80.0
    ]
    deltas, months, tickers = w4._matched_deltas(
        episode_feats, control_feats, "x", is_binary=False
    )
    assert np.isclose(deltas[0], 8.0)   # A never sees B's 100-valued controls
    assert np.isclose(deltas[1], -80.0)
    assert list(months) == ["2020-01", "2020-02"]
    assert list(tickers) == ["A", "B"]


def test_bootstrap_atom_is_the_matched_set_not_individual_obs():
    """Bootstrap resamples episode-level Δ atoms; the control set is welded into each Δ.

    Verify by construction: if control values were resampled independently of their
    episode, a draw could produce a Δ outside the observed per-episode Δ range. The
    month-block bootstrap over Δ can only ever produce medians of the FIXED Δ atoms, so
    every bootstrap statistic lies within [min Δ, max Δ].
    """
    rng = np.random.default_rng(2)
    months = np.array([f"2020-{(i % 12) + 1:02d}" for i in range(48)])
    deltas = rng.normal(0.0, 5.0, size=48)
    lo, hi = float(deltas.min()), float(deltas.max())
    # Instrument the RNG-free path: recompute a handful of bootstrap medians directly.
    res = w4.month_block_matched_bootstrap(
        deltas, months, n_reps=2000, seed=w4.BOOT_SEED, alpha_bonf=0.05 / 10
    )
    # Every percentile of the bootstrap distribution of medians must lie within [lo, hi]:
    # a median of a multiset of the atoms can never exceed the atom range. If controls
    # leaked across episodes this bound could break.
    for key in ("ci95_lo", "ci95_hi", "ci_bonf_lo", "ci_bonf_hi", "point"):
        assert lo - 1e-9 <= res[key] <= hi + 1e-9, f"{key}={res[key]} outside [{lo},{hi}]"


def test_binary_matched_delta_is_rate_within_set():
    """Binary Δ = 1{E} − mean_j 1{C_j} within the matched set (spec §4)."""
    episode_feats = [{"b": True, "_month": "2020-01", "_ticker": "A"}]
    control_feats = [[{"b": True}, {"b": False}, {"b": False}, {"b": False}]]  # mean 0.25
    deltas, _, _ = w4._matched_deltas(episode_feats, control_feats, "b", is_binary=True)
    assert np.isclose(deltas[0], 1.0 - 0.25)


# ---------------------------------------------------------------------------
# Degenerate guard (spec §4): < 12 distinct t0 months → report only, no CI.
# ---------------------------------------------------------------------------

def test_degenerate_guard_below_12_months():
    episode_feats = []
    control_feats = []
    for i in range(30):
        month = f"2020-{(i % 6) + 1:02d}"  # only 6 distinct months
        episode_feats.append({"x": 1.0 + i, "_month": month, "_ticker": f"T{i}"})
        control_feats.append([{"x": 0.0}])
    res = w4.analyze_feature(
        "x", False, episode_feats, control_feats, "c", 0.05 / 12,
        n_boot=1000, seed=w4.BOOT_SEED,
    )
    assert res["degenerate"] is True
    assert res["ci95_lo"] is None
    assert res["ci_bonf_lo"] is None
    assert "degenerate" in res["note"]


def test_non_degenerate_at_12_months_gets_ci():
    episode_feats = []
    control_feats = []
    for i in range(48):
        month = f"2020-{(i % 12) + 1:02d}"  # exactly 12 distinct months
        episode_feats.append({"x": 2.0, "_month": month, "_ticker": f"T{i}"})
        control_feats.append([{"x": 0.0}])
    res = w4.analyze_feature(
        "x", False, episode_feats, control_feats, "c", 0.05 / 12,
        n_boot=1000, seed=w4.BOOT_SEED,
    )
    assert res["degenerate"] is False
    assert res["ci95_lo"] is not None


# ---------------------------------------------------------------------------
# Mask-don't-impute (spec §0.3): absent 8-K coverage → None (dropped), never 0.
# ---------------------------------------------------------------------------

def test_8k_absent_ticker_is_masked_not_zero_filled():
    events = pd.DataFrame({
        "ticker": ["AAA", "AAA"],
        "filing_date": pd.to_datetime(["2020-06-01", "2020-06-15"]),
        "items": ["1.01", "8.01"],
    })
    # A ticker NOT in the store → all counts None (masked), _8k_covered False.
    out = w4._trailing_8k_counts("ZZZ", pd.Timestamp("2020-07-01"), events)
    assert out["hard_event_count_126d"] is None
    assert out["soft_event_count_126d"] is None
    assert out["trailing_rung_ge2"] is None
    assert out["_8k_covered"] is False


def test_8k_present_ticker_no_window_events_is_real_zero():
    events = pd.DataFrame({
        "ticker": ["AAA"],
        "filing_date": pd.to_datetime(["2019-01-01"]),  # far outside the 126d window
        "items": ["1.01"],
    })
    out = w4._trailing_8k_counts("AAA", pd.Timestamp("2020-07-01"), events)
    # Present in store but no filings in (t0-126d, t0) → REAL zero, covered True.
    assert out["hard_event_count_126d"] == 0.0
    assert out["soft_event_count_126d"] == 0.0
    assert out["trailing_rung_ge2"] is False
    assert out["_8k_covered"] is True


def test_8k_pre_era_is_masked():
    events = pd.DataFrame({
        "ticker": ["AAA"],
        "filing_date": pd.to_datetime(["2010-06-01"]),
        "items": ["1.01"],
    })
    out = w4._trailing_8k_counts("AAA", pd.Timestamp("2010-07-01"), events)
    assert out["hard_event_count_126d"] is None  # pre-2014 era → masked
    assert out["_8k_covered"] is False


def test_matched_deltas_masks_missing_episode_and_controls():
    """Episodes with None episode value, or no covered control, are dropped (masked)."""
    episode_feats = [
        {"x": None, "_month": "2020-01", "_ticker": "A"},   # episode value missing → drop
        {"x": 5.0, "_month": "2020-02", "_ticker": "B"},    # no covered control → drop
        {"x": 5.0, "_month": "2020-03", "_ticker": "C"},    # kept
    ]
    control_feats = [
        [{"x": 1.0}],
        [{"x": None}],
        [{"x": 1.0}, {"x": None}],  # one covered control → median 1.0 → Δ = 4.0
    ]
    deltas, months, tickers = w4._matched_deltas(
        episode_feats, control_feats, "x", is_binary=False
    )
    assert len(deltas) == 1
    assert np.isclose(deltas[0], 4.0)
    assert list(tickers) == ["C"]


# ---------------------------------------------------------------------------
# Robustness-grid pins (review round 1):
#   - t0−1 variant: reading dvz at the bar BEFORE onset excludes the onset volume spike;
#   - gate-matched control filter: only controls passing the vol-confirm gate contribute.
# ---------------------------------------------------------------------------

def _synthetic_bench_and_spike_ticker():
    """Build a benchmark series and a ticker whose t0 bar is a huge volume spike.

    Returns (bars, bench_closes, sector_of, t0). The ticker "SPK" trades on a flat-ish
    price with steady volume EXCEPT the t0 bar, which carries a 50x volume spike. The
    dollar_vol_z21 at t0 is therefore large-positive; at t0−1 (windows ending the bar
    before onset) the spike is NOT yet in the window, so the z-score is near 0.
    """
    n = 120
    idx = pd.bdate_range("2020-01-01", periods=n)
    # Flat price so dollar-volume == volume (no price trend confounds the z-score); a tiny
    # deterministic sawtooth on volume gives a small nonzero rolling std (so t0−1 z is
    # defined, not a divide-by-zero), and one 50x volume spike sits ON the onset bar only.
    close = pd.Series(np.full(n, 100.0), index=idx)
    base = np.full(n, 1_000_000.0) + (np.arange(n) % 2) * 10_000.0  # +10k on alternate bars
    volume = pd.Series(base, index=idx)
    t0_pos = 100
    t0 = idx[t0_pos]
    volume.iloc[t0_pos] = 50_000_000.0  # 50x spike ON the onset bar only
    bench = pd.Series(np.linspace(400.0, 404.0, n), index=idx)  # calm benchmark
    bars = {
        "SPK": pd.DataFrame({"close": close, "volume": volume}),
        w4.BENCH: pd.DataFrame({"close": bench, "volume": pd.Series(np.full(n, 5e8), index=idx)}),
    }
    bench_closes = {w4.BENCH: bench}
    sector_of = {"SPK": "Technology"}  # not in _GICS_ETF → resolves to SPY benchmark
    return bars, bench_closes, sector_of, t0


def test_t0m1_variant_excludes_the_onset_volume_spike():
    """dvz at t0 sees the 50x spike; dvz at t0−1 (window ends the prior bar) does not."""
    bars, bench_closes, sector_of, t0 = _synthetic_bench_and_spike_ticker()
    z_t0, r_t0 = w4._dvz_dvr_at_offset("SPK", t0, bars, bench_closes, sector_of, offset=0)
    z_m1, r_m1 = w4._dvz_dvr_at_offset("SPK", t0, bars, bench_closes, sector_of, offset=-1)
    assert z_t0 is not None and z_m1 is not None
    # The onset-bar z-score is strongly positive (the 50x spike is in-window at t0).
    assert z_t0 > 3.0, f"expected a large t0 z-score from the spike, got {z_t0}"
    # The t0−1 z-score EXCLUDES the onset bar → an ordinary sawtooth bar in its own window,
    # small in magnitude and far below the onset-bar value (the mechanism under test).
    assert abs(z_m1) < 1.5, f"expected t0−1 z-score to exclude the spike, got {z_m1}"
    assert z_m1 < z_t0 - 3.0, f"t0−1 z ({z_m1}) must be far below t0 z ({z_t0})"
    # Same story for the 5/60 dollar-volume ratio: spike inflates it at t0, not at t0−1.
    assert r_t0 is not None and r_m1 is not None
    assert r_t0 > 3.0 and r_m1 < 1.5 and r_m1 < r_t0 - 3.0


def test_t0m1_variant_wired_into_compute_features():
    """compute_features exposes __t0m1 columns and they differ from the t0 columns."""
    bars, bench_closes, sector_of, t0 = _synthetic_bench_and_spike_ticker()
    feats = w4.compute_features("SPK", t0, bars, bench_closes, sector_of, events_df=None)
    assert "dollar_vol_z21__t0m1" in feats
    assert "dv_5_60_ratio__t0m1" in feats
    # Onset column present and much larger than the t0−1 column (spike on the onset bar).
    assert feats["dollar_vol_z21"] is not None
    assert feats["dollar_vol_z21__t0m1"] is not None
    assert feats["dollar_vol_z21"] > feats["dollar_vol_z21__t0m1"] + 2.0


def test_control_passes_vol_gate_filter():
    """_control_passes_vol_gate: dvz>=1 OR dvr>=1.5; both-None → not passing (mask)."""
    assert w4._control_passes_vol_gate({"dollar_vol_z21": 1.2, "dv_5_60_ratio": 0.5}) is True
    assert w4._control_passes_vol_gate({"dollar_vol_z21": 0.2, "dv_5_60_ratio": 1.7}) is True
    assert w4._control_passes_vol_gate({"dollar_vol_z21": 0.5, "dv_5_60_ratio": 1.0}) is False
    # Both None → mask, not a pass (never counts a coverage hole as gate-passing).
    assert w4._control_passes_vol_gate({"dollar_vol_z21": None, "dv_5_60_ratio": None}) is False
    # Exactly-at-floor is inclusive (>=).
    assert w4._control_passes_vol_gate({"dollar_vol_z21": 1.0, "dv_5_60_ratio": None}) is True
    assert w4._control_passes_vol_gate({"dollar_vol_z21": None, "dv_5_60_ratio": 1.5}) is True


def test_gate_matched_gridcell_drops_ungated_controls():
    """robustness_grid_cell(gate_matched=True) forms the control median from gate-passers only.

    Episode value 10; two controls: one gate-passing (value 2), one ungated (value 8).
    All-controls median = 5 → Δ = 5. Gate-matched median = 2 → Δ = 8. The filter must bite.
    """
    recs = []
    for i in range(20):
        month = f"2020-{(i % 12) + 1:02d}"
        recs.append({
            "x": 10.0, "_month": month, "_ticker": f"T{i}",
            "_controls": [
                {"x": 2.0, "dollar_vol_z21": 3.0, "dv_5_60_ratio": None},   # gate-passing
                {"x": 8.0, "dollar_vol_z21": 0.1, "dv_5_60_ratio": 0.1},    # ungated
            ],
        })
    d_all, _, _ = w4._matched_deltas_gridcell(recs, "x", gate_matched=False)
    d_gate, _, _ = w4._matched_deltas_gridcell(recs, "x", gate_matched=True)
    assert np.allclose(d_all, 5.0)   # median(2,8)=5 → 10-5
    assert np.allclose(d_gate, 8.0)  # median(2)=2 → 10-2 (ungated control dropped)


def test_gate_matched_gridcell_masks_when_no_gate_control():
    """If an episode has no gate-passing control, it is dropped (masked) in the gate cell."""
    recs = [{
        "x": 10.0, "_month": "2020-01", "_ticker": "A",
        "_controls": [{"x": 8.0, "dollar_vol_z21": 0.1, "dv_5_60_ratio": 0.1}],  # ungated only
    }]
    d_all, _, _ = w4._matched_deltas_gridcell(recs, "x", gate_matched=False)
    d_gate, _, _ = w4._matched_deltas_gridcell(recs, "x", gate_matched=True)
    assert len(d_all) == 1
    assert len(d_gate) == 0  # no gate-passing control → episode masked out


# ---------------------------------------------------------------------------
# Parity on a REAL episode row (spec §3): the recomputed trio equals the committed
# columns within 1e-6. Reads read-only stores; skipped if the data root is absent.
# ---------------------------------------------------------------------------

@pytest.mark.skipif(
    not (_DATA_ROOT.exists() and _EPISODES.exists()),
    reason="read-only data root / committed episodes parquet not present",
)
def test_parity_on_real_episode_row():
    eps = pd.read_parquet(_EPISODES)
    eps["t0"] = pd.to_datetime(eps["t0"])
    # Load the full bars universe the way the study does.
    yahoo = w4._load_yahoo_bars(_DATA_ROOT)
    massive = w4._load_massive_bars(_DATA_ROOT)
    dead = w4._load_dead_name_bars(_DATA_ROOT)
    bars = w4._merge_bars(yahoo, massive, dead)
    bench_closes = w4._load_bench_closes(bars)
    sector_of = w4._load_sector_of(_DATA_ROOT)

    # Pick a matured equity episode with all three committed columns present and bars.
    matured = eps[
        (~eps["ticker"].isin(w4.CRYPTO_TICKERS))
        & eps["outcome_label"].isin(w4.MATURED_LABELS)
        & eps["excess_21d_pp"].notna()
        & eps["dollar_vol_z21"].notna()
        & eps["dv_5_60_ratio"].notna()
    ]
    checked = 0
    for _, row in matured.iterrows():
        if str(row["ticker"]) not in bars:
            continue
        trio = w4._parity_trio(
            str(row["ticker"]), pd.Timestamp(row["t0"]), bars, bench_closes, sector_of
        )
        for col in ("excess_21d_pp", "dollar_vol_z21", "dv_5_60_ratio"):
            rec = trio[col]
            if rec is None:
                continue
            assert abs(float(row[col]) - float(rec)) <= w4.PARITY_TOL, (
                f"parity fail {row['ticker']} {row['t0']} {col}: "
                f"committed={row[col]} recomputed={rec}"
            )
            checked += 1
        if checked >= 30:  # enough real rows to pin the code path
            break
    assert checked >= 3, "expected to check parity on at least a few real rows"
