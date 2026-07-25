"""PSS-W2 — Personality Timing Codex: builder structure measurement + world-state
lobe (honest-null + composed aggregate).

Mirrors tests/test_mag7_washout.py conventions: synthetic tapes written to
tmp_path, root override on the lobe. The builder's structure block is exercised
via build_row on synthetic OHLCV parquets (no SPY needed → beta_spy NaN, which
is the honest result when the market series is absent).

Copy law R-W1T-3 is a live constraint on this store: the derived-rung tool
CONFIRMS RESETS — it does not identify lows in advance. These tests assert the
measured structure (rho signs, derived rung, no_reversion flag) and the lobe's
always-on context flags — never a low-identification claim.
"""
from __future__ import annotations

from pathlib import Path
import sys

import numpy as np
import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import scripts.build_personality_codex as bc  # noqa: E402
from engine.neuralweb.world_state import _compose_personality_codex  # noqa: E402


# ── synthetic tapes ──────────────────────────────────────────────────────────

def _bdays(n: int, start: str = "2010-01-04") -> pd.DatetimeIndex:
    return pd.bdate_range(start, periods=n)


def _mean_reverting(n: int = 2960) -> pd.Series:
    """Stationary log-level (AR(1) pull to a drifting mean) → bar returns
    mean-revert HARD at every rung: all rho < 0, no_reversion False."""
    rng = np.random.default_rng(42)
    eps = rng.normal(0.0, 0.012, n)
    lvl = np.zeros(n)
    for i in range(1, n):
        lvl[i] = 0.85 * lvl[i - 1] + eps[i]
    return pd.Series(100 * np.exp(lvl), index=_bdays(n))


def _trending(n: int = 2960) -> pd.Series:
    """Persistent drift + momentum (positively autocorrelated returns) → bar
    returns do NOT revert: all rho > 0, no_reversion True.

    Seed 17 is PINNED and probed: it yields ρ 3D +0.137 / 1W +0.048 / 2W +0.138
    — all clearly positive with margin above the ~0.085 se of a lag-1 autocorr
    on ~140 coarse 2W bars (a random daily-momentum seed can dip a coarse-rung ρ
    slightly negative purely from sampling noise; the pinned seed avoids that
    knife-edge, same discipline as the mag7_washout probe comment)."""
    rng = np.random.default_rng(17)
    rets = 0.0006 + rng.normal(0.0, 0.004, n)
    for i in range(1, n):
        rets[i] += 0.15 * rets[i - 1]
    return pd.Series(100 * np.cumprod(1 + rets), index=_bdays(n))


def _write_ohlcv(root: Path, sym: str, close: pd.Series) -> Path:
    d = root / "baskets" / "ohlcv"
    d.mkdir(parents=True, exist_ok=True)
    df = pd.DataFrame({
        "open": close, "high": close * 1.01, "low": close * 0.99,
        "close": close, "volume": 1e6,
    })
    p = d / f"{sym}.parquet"
    df.to_parquet(p)
    return p


# ── (a) builder structure measurement ───────────────────────────────────────

def test_build_row_mean_reverting_all_rho_negative(tmp_path):
    """A hard mean-reverting tape → every rung's lag-1 autocorr is negative,
    so no_reversion is False and the derived rung is a real measurement."""
    f = _write_ohlcv(tmp_path, "MRTAPE", _mean_reverting())
    row = bc.build_row(f, "2026-07-25", spy_ret=None)
    assert row is not None, "mean-reverting tape must pass the mwr_phase1 filter"
    assert row["p_measured"] is True
    assert row["rho_3d"] < 0 and row["rho_1w"] < 0 and row["rho_2w"] < 0
    # all rho < 0 ⇒ NOT the 'washouts continue' class
    assert row["no_reversion"] is False
    # derived rung = argmin rho, and it is one of the three ladder rungs
    assert row["rung_derived"] in ("3D", "1W", "2W")
    # beta_spy is honestly NaN when no market series is supplied
    assert pd.isna(row["beta_spy"])
    # reset profile fired at least some signals and produced a base-rate
    assert row["n_signals"] >= 0
    assert np.isfinite(row["base_mae_med"])


def test_build_row_trending_sets_no_reversion(tmp_path):
    """A persistent-momentum tape → every rung's autocorr is positive, so the
    no_reversion ('washouts continue') flag fires."""
    f = _write_ohlcv(tmp_path, "TRTAPE", _trending())
    row = bc.build_row(f, "2026-07-25", spy_ret=None)
    assert row is not None
    assert row["p_measured"] is True
    assert row["rho_3d"] > 0 and row["rho_1w"] > 0 and row["rho_2w"] > 0
    assert row["no_reversion"] is True
    assert row["rung_derived"] in ("3D", "1W", "2W")


def test_build_row_rung_is_argmin_rho(tmp_path):
    """The derived rung is the scale whose bars mean-revert hardest (argmin rho)
    — the mechanism a washout/reset-confirmer tool monetizes."""
    f = _write_ohlcv(tmp_path, "MRTAPE", _mean_reverting())
    row = bc.build_row(f, "2026-07-25", spy_ret=None)
    rhos = {"3D": row["rho_3d"], "1W": row["rho_1w"], "2W": row["rho_2w"]}
    expected = min(rhos, key=rhos.get)
    assert row["rung_derived"] == expected


def test_build_row_filters_short_tape(tmp_path):
    """A tape with < 2900 closes fails the mwr_phase1 filter (returns None) —
    the codex universe gate is byte-identical to the study filter."""
    f = _write_ohlcv(tmp_path, "SHORT", _mean_reverting(n=1500))
    assert bc.build_row(f, "2026-07-25", spy_ret=None) is None


def test_beta_vs_spy_recovers_known_slope():
    """beta_vs_spy is the OLS slope of the name on SPY: a tape built as
    2x SPY returns + idiosyncratic noise recovers a beta near 2."""
    rng = np.random.default_rng(1)
    n = 1500
    idx = _bdays(n)
    spy_ret = pd.Series(rng.normal(0.0004, 0.01, n), index=idx)
    name_ret = 2.0 * spy_ret + pd.Series(rng.normal(0.0, 0.002, n), index=idx)
    name_close = pd.Series(100 * np.cumprod(1 + name_ret), index=idx)
    beta = bc.beta_vs_spy(name_close, spy_ret)
    assert 1.7 < beta < 2.3, f"expected beta≈2, got {beta:.3f}"


# ── (b) lobe honest-null when the parquet is absent ─────────────────────────

def test_lobe_honest_null_when_absent(tmp_path):
    """No codex.parquet → honest-null block, but display_only AND
    is_context_only are True even in the null fallback (darkpool discipline)."""
    out = _compose_personality_codex(root=tmp_path)
    assert out["display_only"] is True
    assert out["is_context_only"] is True
    assert out["n_names"] is None
    assert out["as_of"] is None
    assert out["rung_distribution"] is None
    assert out["median_lateness_tdt"] is None


# ── (c) lobe composed aggregate from a tiny parquet ─────────────────────────

def _write_codex(root: Path, rows: list[dict]) -> None:
    # The lobe reads repo/data/personality_timing/codex.parquet (it prepends
    # 'data/' to the root, matching production), so the tmp layout must too.
    d = root / "data" / "personality_timing"
    d.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(rows).to_parquet(d / "codex.parquet", index=False)


def test_lobe_composed_aggregate(tmp_path):
    """A tiny parquet → the lobe reports AGGREGATE counts (no per-name payload),
    with the always-on context flags. Verifies rung_distribution, no_reversion
    count, median lateness, and slow_defensive count."""
    rows = [
        {"sym": "A", "as_of": "2026-07-25", "rung_derived": "1W",
         "no_reversion": False, "med_tdt": -5.0, "slow_defensive": True},
        {"sym": "B", "as_of": "2026-07-25", "rung_derived": "1W",
         "no_reversion": True, "med_tdt": -1.0, "slow_defensive": False},
        {"sym": "C", "as_of": "2026-07-25", "rung_derived": "3D",
         "no_reversion": False, "med_tdt": 3.0, "slow_defensive": False},
    ]
    _write_codex(tmp_path, rows)
    out = _compose_personality_codex(root=tmp_path)
    assert out["display_only"] is True and out["is_context_only"] is True
    assert out["as_of"] == "2026-07-25"
    assert out["n_names"] == 3
    assert out["rung_distribution"] == {"1W": 2, "3D": 1}
    assert out["n_no_reversion"] == 1
    assert out["n_slow_defensive"] == 1
    # median of [-5, -1, 3] = -1 (reset-confirmation lateness; negative = the
    # trough is in before entry — a confirmed reset, not a low identified early)
    assert out["median_lateness_tdt"] == -1.0
    # aggregate-only: no per-name field leaks into the lobe
    assert "sym" not in out and "rows" not in out


def test_lobe_composed_has_no_per_name_payload(tmp_path):
    """Guard: the lobe is an aggregate view — the per-name store is the parquet.
    Only the documented aggregate keys may appear."""
    rows = [{"sym": "A", "as_of": "2026-07-25", "rung_derived": "2W",
             "no_reversion": True, "med_tdt": -8.0, "slow_defensive": True}]
    _write_codex(tmp_path, rows)
    out = _compose_personality_codex(root=tmp_path)
    assert set(out.keys()) == {
        "as_of", "n_names", "rung_distribution", "n_no_reversion",
        "median_lateness_tdt", "n_slow_defensive",
        "display_only", "is_context_only",
    }
