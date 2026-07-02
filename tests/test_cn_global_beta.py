"""C1 — China per-name global-beta size-dampener tests (engine/cn_global_beta.py +
the harness verdict + the not-wired guarantee).

The C1 channel was MEASURED and graded CONTEXT (weaker than HK; the RORO-conditional
dampener mechanism is refuted). These tests lock in:

  1. causality — the beta uses PRIOR-window data only (lag/shift; no look-ahead);
  2. shrinkage — Vasicek-lite pulls toward the cross-sectional mean, bounded by w;
  3. structure/recovery — the engine recovers each name's true beta and ranks roles;
  4. guards — empty / too-few-names / short-factor degrade to None, never raise;
  5. NOT-WIRED guarantee — the C1 ledger row is CONTEXT with weight_cap 0, so
     engine/intl_feed.features() returns weight 0 for it: any future consumer that
     honours the weight field applies ZERO dampening → the China build is unaffected;
  6. de-risk-only + stale-zeroing — the intl_feed weight policy the (unwired) dampener
     would depend on zeroes a DIRECTIONAL add-tilt and a stale source, proving the
     dampener path can only ever de-risk and self-zeroes on staleness.

Run: python -m pytest tests/test_cn_global_beta.py -v
"""
from __future__ import annotations

import json
import sys
from datetime import date, timedelta
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from engine import cn_global_beta as gb  # noqa: E402
from engine import intl_feed as feed  # noqa: E402


# ---------------------------------------------------------------------------
# synthetic universe: known per-name betas to a global-risk factor
# ---------------------------------------------------------------------------
def _synthetic(seed: int = 0, n: int = 400):
    rng = np.random.default_rng(seed)
    dates = pd.bdate_range("2021-06-15", periods=n)
    f = rng.normal(0.0003, 0.011, n)                       # global-risk factor returns
    true = {f"T{i:02d}": b for i, b in enumerate(np.linspace(0.0, 1.3, 14))}
    closes = pd.DataFrame(
        {t: pd.Series(100 * np.cumprod(1 + (b * f + rng.normal(0, 0.005, n))), index=dates)
         for t, b in true.items()})
    factor = pd.Series(f, index=dates)
    names = {t: t for t in true}
    sectors = {t: "Tech" for t in true}
    return closes, factor, names, sectors, true


# ---------------------------------------------------------------------------
# 1. causality — the beta must not see future factor bars
# ---------------------------------------------------------------------------
def test_causality_no_lookahead():
    """A spike appended to the LAST factor bar must not change the as-of beta, because
    _causal_beta shifts by one day (prior-window only). If future data leaked, the last
    beta would move when we perturb the final factor observation."""
    closes, factor, names, sectors, _ = _synthetic()
    base = gb.compute_global_betas(closes, factor, "unknown", names, sectors,
                                   win=120, shrink=1.0, min_names=8)
    assert base is not None
    # perturb ONLY the final factor bar (the one shift(1) drops from the last beta)
    fac2 = factor.copy()
    fac2.iloc[-1] = fac2.iloc[-1] + 5.0                    # absurd spike on the last day
    pert = gb.compute_global_betas(closes, fac2, "unknown", names, sectors,
                                   win=120, shrink=1.0, min_names=8)
    b0 = {t: base["per_ticker"][t]["beta"] for t in base["per_ticker"]}
    b1 = {t: pert["per_ticker"][t]["beta"] for t in pert["per_ticker"]}
    # identical → the last-day factor value did NOT enter the as-of beta (no look-ahead)
    assert b0 == b1


def test_causal_beta_is_shifted():
    """_causal_beta returns a series whose last row is NaN-or-prior (shift(1) applied):
    the beta ROW at date D is computed from data through D-1."""
    closes, factor, _, _, _ = _synthetic()
    R = closes.pct_change(fill_method=None)
    raw = (R.rolling(120, min_periods=60).cov(factor.reindex(R.index))
           .div(factor.reindex(R.index).rolling(120, min_periods=60).var(), axis=0))
    shifted = gb._causal_beta(R, factor.reindex(R.index), 120, 60)
    # the shifted engine value at date D equals the UNSHIFTED value at D-1
    col = closes.columns[7]
    assert np.isclose(shifted[col].iloc[-1], raw[col].iloc[-2], equal_nan=True) or (
        np.isnan(shifted[col].iloc[-1]) and np.isnan(raw[col].iloc[-2]))


# ---------------------------------------------------------------------------
# 2. shrinkage — Vasicek-lite bounds
# ---------------------------------------------------------------------------
def test_shrinkage_pulls_to_mean():
    b = pd.Series({"a": 0.0, "b": 1.0, "c": 2.0})          # mean = 1.0
    full = gb._shrink(b, 1.0)                              # w=1 → no shrink
    assert full.equals(b)
    half = gb._shrink(b, 0.5)                              # w=0.5 → halfway to the mean
    assert np.isclose(half["a"], 0.5) and np.isclose(half["c"], 1.5)
    # every shrunk beta sits strictly BETWEEN its raw value and the cross-sectional mean
    for k in b.index:
        lo, hi = sorted((b[k], b.mean()))
        assert lo <= half[k] <= hi
    # dispersion strictly shrinks
    assert half.std() < b.std()


# ---------------------------------------------------------------------------
# 3. structure / recovery
# ---------------------------------------------------------------------------
def test_structure_and_recovery():
    pytest.importorskip("scipy")
    closes, factor, names, sectors, true = _synthetic()
    out = gb.compute_global_betas(closes, factor, "unknown", names, sectors,
                                  win=120, shrink=1.0, min_names=8)
    assert out is not None
    assert set(out) >= {"as_of", "n", "amplifiers", "cushions", "per_ticker"}
    assert out["n"] == 14
    est = pd.Series({t: out["per_ticker"][t]["beta"] for t in out["per_ticker"]})
    tru = pd.Series(true)[est.index]
    assert est.corr(tru, method="spearman") > 0.9         # recovers the beta ordering
    assert out["amplifiers"][0]["role"] == "amplifier"    # top-tercile = amplifier
    assert out["cushions"][0]["role"] == "cushion"
    # roles are the top/bottom tercile split (no per-state tilt in the CN port — it is
    # de-risk-direction-only, so there is no add-tilt "favored" role)
    assert set(out["per_ticker"][t]["role"] for t in out["per_ticker"]) <= {
        "amplifier", "neutral", "cushion"}


def test_guards():
    closes, factor, names, sectors, _ = _synthetic()
    assert gb.compute_global_betas(pd.DataFrame(), factor, "unknown") is None
    assert gb.compute_global_betas(closes.iloc[:, :3], factor, "unknown", names, sectors,
                                   win=120, min_names=8) is None          # too few names
    short = factor.iloc[:20]
    assert gb.compute_global_betas(closes, short, "unknown", names, sectors,
                                   win=120, min_names=8) is None          # factor too short


# ---------------------------------------------------------------------------
# 5/6. the NOT-WIRED guarantee via the intl_feed weight policy
# ---------------------------------------------------------------------------
def _write_ledger(tmp_path: Path, features: list[dict]) -> Path:
    d = tmp_path / "data" / "intl_bridge"
    d.mkdir(parents=True)
    (d / "ledger.json").write_text(json.dumps(
        {"asof": "2026-07-02", "family": "intl_bridge", "features": features}))
    return tmp_path


def _fresh_parquet(tmp_path: Path, group: str, name: str, age_days: int) -> None:
    d = tmp_path / "data" / group
    d.mkdir(parents=True, exist_ok=True)
    safe = name.replace("^", "_").replace("=", "_").replace("/", "_").replace(" ", "_")
    idx = pd.to_datetime([date.today() - timedelta(days=age_days)])
    pd.DataFrame({"close": [1.0]}, index=idx).to_parquet(d / f"{safe}.parquet")


def _c1_row(**over) -> dict:
    row = {
        "id": "c1_china_global_beta", "channel": "C1", "direction": "de-risk",
        "verdict": "CONTEXT", "weight_cap": 0.0,
        "source_series": ["yahoo/FXI", "yahoo/SPY"], "freshness_sla_days": 5,
        "kill": True, "notes": "measured CONTEXT",
    }
    row.update(over)
    return row


def test_c1_context_is_zero_weight(tmp_path):
    """The shipped C1 verdict (CONTEXT, kill=True) → weight 0 → the China build is
    UNAFFECTED: a consumer honouring the weight field applies zero dampening."""
    root = _write_ledger(tmp_path, [_c1_row()])
    _fresh_parquet(tmp_path, "yahoo", "FXI", 1)
    _fresh_parquet(tmp_path, "yahoo", "SPY", 1)
    st = feed.features(root=root)
    assert st["c1_china_global_beta"]["weight"] == 0.0     # nothing sizes off C1


def test_c1_dampener_would_zero_when_stale(tmp_path):
    """Stale-zeroing: even if C1 were ever promoted to DIRECTIONAL/CONFIRMED, a stale
    source series forces weight 0 (fail-closed). Proven on the SPY factor going stale."""
    root = _write_ledger(tmp_path, [_c1_row(verdict="DIRECTIONAL", weight_cap=0.10, kill=False)])
    _fresh_parquet(tmp_path, "yahoo", "FXI", 1)
    _fresh_parquet(tmp_path, "yahoo", "SPY", 40)           # 40d > SLA 5 → stale
    st = feed.features(root=root)["c1_china_global_beta"]
    assert st["stale"] is True and st["weight"] == 0.0


def test_c1_dampener_is_de_risk_only(tmp_path):
    """De-risk-only: a DIRECTIONAL leg with direction != 'de-risk' is a ledger bug and is
    forced to weight 0 with a warning — the dampener path can NEVER become an add-tilt."""
    root = _write_ledger(
        tmp_path, [_c1_row(verdict="DIRECTIONAL", direction="add-tilt",
                           weight_cap=0.10, kill=False)])
    _fresh_parquet(tmp_path, "yahoo", "FXI", 1)
    _fresh_parquet(tmp_path, "yahoo", "SPY", 1)
    st = feed.features(root=root)["c1_china_global_beta"]
    assert st["weight"] == 0.0
    assert "DIRECTIONAL" in st["notes"] and "de-risk" in st["notes"]


def test_c1_directional_de_risk_gets_half_cap(tmp_path):
    """Sanity that the policy IS live: a de-risk DIRECTIONAL leg with fresh data would
    get half the cap (the bounded dampener), so the CONTEXT-zero above is the verdict's
    doing, not a dead code path."""
    root = _write_ledger(
        tmp_path, [_c1_row(verdict="DIRECTIONAL", weight_cap=0.10, kill=False)])
    _fresh_parquet(tmp_path, "yahoo", "FXI", 1)
    _fresh_parquet(tmp_path, "yahoo", "SPY", 1)
    st = feed.features(root=root)["c1_china_global_beta"]
    assert st["weight"] == pytest.approx(0.05)             # half of 0.10, de-risk-only
