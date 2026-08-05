"""Pins for the LSR-P0 phase-0 study's pure functions.

The study reports a NULL, and a null is only worth anything if the machinery that
produced it can see a real effect. These tests pin the three properties whose
silent failure would manufacture that null:

  * ``sector_ex_self_peer`` must EXCLUDE the subject from its own benchmark. If it
    did not, an extreme name would be pulled into its own peer mean, its residual
    would shrink toward zero exactly on the days the 3-sigma trigger fires, and the
    study would measure a muted, biased event population while looking healthy.
  * ``date_block_ci`` must resample DATES, not name-days, and must widen when the
    series is short. A per-name-day interval would be far too tight on a tape whose
    events arrive in market-wide bunches, turning noise into a finding.
  * ``corwin_schultz`` must recover a spread it is given and must not emit negatives.

Run: .venv/bin/python -m pytest tests/test_liquidity_shock_reversal.py -q
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from scripts.research_liquidity_shock_reversal import (
    break_even_bps,
    corwin_schultz,
    date_block_ci,
    sector_ex_self_peer,
)


# ── sector_ex_self_peer ──────────────────────────────────────────────────────
def test_peer_benchmark_excludes_the_subject() -> None:
    """The whole point of ex-self: a name must not appear in its own benchmark.

    Four names in one sector on one day: A crashes -50%, B/C/D are flat at +1%.
    A's peer return must be exactly +1% (the mean of B, C, D). An INCLUSIVE mean
    would be -11.75%, which would shrink A's residual from -51pp to -38.25pp.
    """
    idx = pd.date_range("2024-01-01", periods=1, freq="D")
    ret = pd.DataFrame({"A": [-0.50], "B": [0.01], "C": [0.01], "D": [0.01]}, index=idx)
    sector = pd.Series({"A": "Tech", "B": "Tech", "C": "Tech", "D": "Tech"})

    peer = sector_ex_self_peer(ret, sector, min_peers=4)

    assert peer.loc[idx[0], "A"] == pytest.approx(0.01)
    inclusive = ret.loc[idx[0]].mean()
    assert peer.loc[idx[0], "A"] != pytest.approx(inclusive)
    # and the residual keeps the full shock
    assert (ret - peer).loc[idx[0], "A"] == pytest.approx(-0.51)
    # each flat name sees a peer mean dragged down by A — also ex-self
    assert peer.loc[idx[0], "B"] == pytest.approx((-0.50 + 0.01 + 0.01) / 3)


def test_thin_sector_falls_back_to_the_universe_mean() -> None:
    """Below min_peers the sector mean is noise, so the benchmark must fall back —
    not silently emit a two-name 'sector' average."""
    idx = pd.date_range("2024-01-01", periods=1, freq="D")
    ret = pd.DataFrame({"A": [-0.10], "B": [0.02], "X": [0.06], "Y": [0.06]}, index=idx)
    sector = pd.Series({"A": "Thin", "B": "Thin", "X": "Wide", "Y": "Wide"})

    peer = sector_ex_self_peer(ret, sector, min_peers=4)

    assert peer.loc[idx[0], "A"] == pytest.approx(ret.loc[idx[0]].mean())


def test_unlabelled_names_are_benchmarked_not_dropped() -> None:
    idx = pd.date_range("2024-01-01", periods=1, freq="D")
    ret = pd.DataFrame({"A": [0.10], "B": [0.02], "C": [0.02], "D": [0.02], "Z": [-0.30]}, index=idx)
    sector = pd.Series({"A": "Tech", "B": "Tech", "C": "Tech", "D": "Tech"})  # Z unlabelled

    peer = sector_ex_self_peer(ret, sector, min_peers=4)

    assert np.isfinite(peer.loc[idx[0], "Z"])
    assert peer.loc[idx[0], "Z"] == pytest.approx(ret.loc[idx[0]].mean())


# ── date_block_ci ────────────────────────────────────────────────────────────
def test_date_block_ci_recovers_the_mean_and_brackets_it() -> None:
    rng = np.random.default_rng(3)
    s = pd.Series(rng.normal(0.004, 0.01, 600))
    ci = date_block_ci(s)
    assert ci["mean"] == pytest.approx(s.mean())
    assert ci["lo"] < ci["mean"] < ci["hi"]
    assert ci["lo"] > 0, "a 0.4% mean on 600 obs of 1% noise must exclude zero"


def test_date_block_ci_widens_on_a_short_series() -> None:
    """A shorter tape must produce a WIDER interval — the guard against a study
    reporting confident nulls off a handful of dates."""
    rng = np.random.default_rng(5)
    draws = rng.normal(0.0, 0.02, 800)
    wide = date_block_ci(pd.Series(draws[:40]))
    tight = date_block_ci(pd.Series(draws))
    assert (wide["hi"] - wide["lo"]) > (tight["hi"] - tight["lo"])


def test_date_block_ci_refuses_a_series_too_short_to_bootstrap() -> None:
    ci = date_block_ci(pd.Series([0.01, 0.02, 0.03]))
    assert np.isnan(ci["mean"]) and np.isnan(ci["lo"]) and np.isnan(ci["hi"])
    assert ci["n"] == 3


def test_date_block_ci_ignores_nan_dates() -> None:
    s = pd.Series([np.nan] * 50 + [0.01] * 100)
    ci = date_block_ci(s)
    assert ci["n"] == 100
    assert ci["mean"] == pytest.approx(0.01)


# ── corwin_schultz ───────────────────────────────────────────────────────────
def _simulate(n: int, ticks: int, sigma_day: float, spread: float, seed: int):
    """Daily bars from an intraday price PATH, then bracketed by a known spread —
    the high is a buy at the ask, the low a sell at the bid."""
    rng = np.random.default_rng(seed)
    path = 100 * np.exp(np.cumsum(rng.normal(0, sigma_day / np.sqrt(ticks), (n, ticks)), axis=1))
    base = np.concatenate([[100.0], 100 * np.exp(np.cumsum(rng.normal(0, sigma_day, n - 1)))])
    px = path * (base / path[:, 0])[:, None]
    high = pd.DataFrame({"X": px.max(axis=1) * (1 + spread / 2)})
    low = pd.DataFrame({"X": px.min(axis=1) * (1 - spread / 2)})
    return corwin_schultz(high, low)["X"].dropna()


def test_corwin_schultz_rises_with_the_true_spread() -> None:
    """The estimator must at least ORDER spreads correctly at fixed volatility —
    that is the only property this study leans on."""
    tight = _simulate(3000, 80, 0.015, 0.0005, seed=7).mean()
    wide = _simulate(3000, 80, 0.015, 0.0100, seed=7).mean()
    assert wide > tight * 1.5


def test_corwin_schultz_is_dominated_by_volatility_not_spread() -> None:
    """THE PIN THAT MATTERS: this estimator is NOT a cost estimate and must never be
    subtracted from a return as one.

    Two measured facts, both pinned here. (a) A near-zero true spread reads an order
    of magnitude too high — 5bp planted comes back as ~38bp, so the reading has a
    large volatility-driven FLOOR that exists whatever the spread is. (b) Holding the
    true spread fixed at that 5bp and merely doubling volatility roughly doubles the
    reading again, so the level is a property of the day's range as much as of the
    spread — and a shock-day population is selected for exactly that range.

    A future session that grabs `spread_shock` as a trading cost would manufacture a
    catastrophic-looking net return out of nothing but volatility, which is why the
    study's cost gate is a break-even and never a subtraction.
    """
    lo_vol_tight = _simulate(3000, 80, 0.015, 0.0005, seed=7).mean()
    hi_vol_tight = _simulate(3000, 80, 0.030, 0.0005, seed=7).mean()

    assert lo_vol_tight > 0.0020, "a 5bp true spread already reads >20bp — contamination floor"
    assert hi_vol_tight > 1.5 * lo_vol_tight, (
        "doubling volatility at a FIXED 5bp spread must move the reading materially"
    )


def test_corwin_schultz_never_returns_a_negative_spread() -> None:
    rng = np.random.default_rng(13)
    px = pd.Series(50 * np.exp(np.cumsum(rng.normal(0, 0.02, 300))))
    high = pd.DataFrame({"X": px * (1 + rng.uniform(0, 0.03, 300))})
    low = pd.DataFrame({"X": px * (1 - rng.uniform(0, 0.03, 300))})

    est = corwin_schultz(high, low)

    assert (est.dropna() >= 0).all().all()


def test_corwin_schultz_reads_zero_when_high_equals_low() -> None:
    flat = pd.DataFrame({"X": [10.0] * 50})
    est = corwin_schultz(flat, flat)["X"].dropna()
    assert (est == 0).all()


# ── break_even_bps ───────────────────────────────────────────────────────────
def test_break_even_splits_the_edge_across_both_legs() -> None:
    """A long/short spread pays a round trip on BOTH legs, so a 0.28% gross edge
    dies at 14bp per leg — not 28bp. Halving is the whole point of the function."""
    assert break_even_bps(0.281) == pytest.approx(14.05)
    assert break_even_bps(0.281, n_legs=1) == pytest.approx(28.1)


def test_break_even_takes_percent_and_returns_basis_points() -> None:
    """UNIT PIN. The input is a spread in PERCENT and the output is BASIS POINTS, so
    the function multiplies by 100 as well as halving. Re-deriving this inline in the
    reopener script once produced a break-even 100x too small — which would have read
    as 'dies at 0.2bp' (absurdly fragile) instead of '19.6bp' (a real bar). Anything
    that needs a break-even calls THIS, never its own arithmetic.
    """
    assert break_even_bps(1.0) == pytest.approx(50.0)      # 1% gross -> 50bp per leg
    assert break_even_bps(0.3922) == pytest.approx(19.61)  # the illiquid-tail number
    assert break_even_bps(0.3922) > 1.0, "a sub-1bp break-even means the units slipped"
