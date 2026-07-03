"""Tests for scripts/validate_gex.py — W0.3 extension.

Covers both the existing cboe store evaluation AND the new polygon_gex per-name
store evaluation. Gate schema (gex.gate.v1) must remain unchanged; evidence lines
must carry [cboe] or [polygon_gex] store labels; scored flips only on CI-clean pass
in either store.
"""
from __future__ import annotations

import json
import math
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from scripts.validate_gex import (
    MIN_PER_BUCKET,
    N_BOOT,
    _boot,
    _evaluate_cboe_store,
    _evaluate_polygon_store,
    _fwd_rv,
    _regime,
    evaluate,
)


# ── helpers ──────────────────────────────────────────────────────────────────


def _spot_series(n: int, drift: float = 0.0, seed: int = 42) -> pd.Series:
    rng = np.random.default_rng(seed)
    log_ret = rng.normal(drift, 0.012, n)
    prices = 100.0 * np.exp(np.cumsum(log_ret))
    return pd.Series(prices)


def _gex_frame(n: int, regime_col: str = "gamma_regime",
               long_frac: float = 0.6, seed: int = 0) -> pd.DataFrame:
    """Minimal DataFrame mirroring polygon_gex/summary_*.parquet schema."""
    rng = np.random.default_rng(seed)
    spot = _spot_series(n, seed=seed + 1).values
    regimes = np.where(rng.random(n) < long_frac, "long", "short")
    return pd.DataFrame({"spot": spot, regime_col: regimes})


# ── _fwd_rv ───────────────────────────────────────────────────────────────────


def test_fwd_rv_annualised():
    s = _spot_series(30)
    rv = _fwd_rv(s, 5)
    assert rv.notna().any()
    assert (rv.dropna() > 0).all()


def test_fwd_rv_shift_alignment():
    """Day-t forward RV uses days t+1..t+h (shift(-h) on the h-day rolling window)."""
    s = _spot_series(20)
    rv = _fwd_rv(s, 5)
    # the last h positions must be NaN (no lookahead data)
    assert rv.iloc[-5:].isna().all()


# ── _regime ───────────────────────────────────────────────────────────────────


def test_regime_gamma_regime_column():
    df = pd.DataFrame({"gamma_regime": ["long", "short", "long", None]})
    r = _regime(df)
    assert list(r.dropna()) == [1.0, -1.0, 1.0]


def test_regime_fallback_net_gex():
    df = pd.DataFrame({"net_gex_bn": [1.5, -0.3, 0.0]})
    r = _regime(df)
    assert list(r) == [1.0, -1.0, 0.0]


def test_regime_none_when_no_column():
    df = pd.DataFrame({"spot": [100.0, 101.0]})
    assert _regime(df) is None


# ── _boot ────────────────────────────────────────────────────────────────────


def test_boot_positive_when_short_higher():
    rng = np.random.default_rng(7)
    longg = rng.uniform(0.10, 0.20, 50)
    shortg = rng.uniform(0.25, 0.35, 50)   # clearly higher
    diff, lo, hi = _boot(longg, shortg)
    assert diff > 0
    assert lo > 0   # 95% CI should exclude 0 with this separation


def test_boot_includes_zero_when_no_difference():
    rng = np.random.default_rng(13)
    vals = rng.uniform(0.15, 0.25, 50)
    diff, lo, hi = _boot(vals[:25], vals[25:])
    assert lo < 0 < hi   # CI should include 0


# ── evaluate ─────────────────────────────────────────────────────────────────


def test_evaluate_building_history_short_series():
    df = _gex_frame(10)
    lines = evaluate("TEST", df, store_label="polygon_gex")
    assert all("building history" in ln for ln in lines)
    assert all("[polygon_gex]" in ln for ln in lines)


def test_evaluate_building_history_label():
    df = _gex_frame(10)
    lines = evaluate("SPY", df, store_label="cboe")
    assert all("[cboe]" in ln for ln in lines)


def test_evaluate_no_spot_column():
    df = pd.DataFrame({"gamma_regime": ["long"] * 5})
    lines = evaluate("X", df)
    assert any("building history" in ln for ln in lines)


def test_evaluate_no_regime_column():
    df = pd.DataFrame({"spot": [100.0] * 20})
    lines = evaluate("X", df)
    assert any("no regime column" in ln for ln in lines)


def test_evaluate_empty_store_label():
    df = _gex_frame(5)
    lines = evaluate("A", df)   # no label → no prefix
    assert not any("[" in ln for ln in lines)


def test_evaluate_passes_when_boot_returns_positive_ci(monkeypatch):
    """When _boot returns a CI that excludes 0, evaluate() emits a PASS line."""
    import scripts.validate_gex as vgex
    rng = np.random.default_rng(99)
    # Use n large enough that both buckets clear MIN_PER_BUCKET after forward-RV dropna
    n = MIN_PER_BUCKET * 5
    spot = 100 * np.exp(np.cumsum(rng.normal(0, 0.012, n)))
    # Alternate long/short so both buckets are populated
    regimes = np.array(["long" if i % 2 == 0 else "short" for i in range(n)])
    df = pd.DataFrame({"spot": spot, "gamma_regime": regimes})
    # Patch _boot at module level; evaluate uses module globals, so this is picked up
    monkeypatch.setattr(vgex, "_boot", lambda l, s: (0.05, 0.01, 0.09))
    lines = vgex.evaluate("SYN", df, store_label="polygon_gex")
    assert any("PASS —" in ln for ln in lines)


# ── _evaluate_polygon_store ───────────────────────────────────────────────────


def test_evaluate_polygon_store_empty_dir(tmp_path):
    (tmp_path / "polygon_gex").mkdir()
    verdicts = _evaluate_polygon_store(tmp_path)
    assert verdicts == []


def test_evaluate_polygon_store_reads_files(tmp_path):
    pg_dir = tmp_path / "polygon_gex"
    pg_dir.mkdir()
    # Write two minimal per-name summaries
    for sym, n in [("AAPL", 8), ("TSLA", 6)]:
        df = _gex_frame(n, seed=hash(sym) % 100)
        df.to_parquet(pg_dir / f"summary_{sym}.parquet")
    verdicts = _evaluate_polygon_store(tmp_path)
    syms_mentioned = {ln.split()[0].lstrip("[").rstrip("]").replace("polygon_gex] ", "")
                      for ln in verdicts}
    # evidence lines should cover both names
    assert any("AAPL" in ln for ln in verdicts)
    assert any("TSLA" in ln for ln in verdicts)
    # all lines carry the store label
    assert all("[polygon_gex]" in ln for ln in verdicts)


def test_evaluate_polygon_store_corrupt_file(tmp_path):
    pg_dir = tmp_path / "polygon_gex"
    pg_dir.mkdir()
    (pg_dir / "summary_BAD.parquet").write_bytes(b"not a parquet")
    verdicts = _evaluate_polygon_store(tmp_path)
    assert any("read error" in ln for ln in verdicts)


# ── _evaluate_cboe_store ─────────────────────────────────────────────────────


def test_evaluate_cboe_store_empty_dir(tmp_path):
    (tmp_path / "cboe").mkdir()
    verdicts = _evaluate_cboe_store(tmp_path)
    assert verdicts == []


def test_evaluate_cboe_store_reads_files(tmp_path):
    cboe_dir = tmp_path / "cboe"
    cboe_dir.mkdir()
    df = _gex_frame(10, seed=5)
    df.to_parquet(cboe_dir / "gex_SPY.parquet")
    verdicts = _evaluate_cboe_store(tmp_path)
    assert any("[cboe]" in ln for ln in verdicts)
    assert any("SPY" in ln for ln in verdicts)


# ── gate.json schema ─────────────────────────────────────────────────────────


def test_main_writes_gate_json(tmp_path, monkeypatch):
    """gate.json must carry schema gex.gate.v1 + stores_evaluated list."""
    import scripts.validate_gex as vgex

    # Minimal cboe + polygon_gex dirs with tiny frames
    (tmp_path / "cboe").mkdir()
    df_cboe = _gex_frame(5, seed=10)
    df_cboe.to_parquet(tmp_path / "cboe" / "gex_SPY.parquet")

    pg_dir = tmp_path / "polygon_gex"
    pg_dir.mkdir()
    df_pg = _gex_frame(7, seed=11)
    df_pg.to_parquet(pg_dir / "summary_AAPL.parquet")

    monkeypatch.setattr(vgex.config, "data_dir", lambda: tmp_path)
    monkeypatch.setattr(vgex.config, "ROOT", tmp_path)

    vgex.main()

    gate_path = tmp_path / "gex" / "gate.json"
    assert gate_path.exists()
    gate = json.loads(gate_path.read_text())
    assert gate["schema"] == "gex.gate.v1"
    assert isinstance(gate["scored"], bool)
    assert "stores_evaluated" in gate
    assert set(gate["stores_evaluated"]) == {"cboe", "polygon_gex"}
    # With only 5-7 rows, all verdicts are building_history → scored=False
    assert not gate["scored"]
    # Evidence lines carry store labels
    cboe_ev = [ln for ln in gate["evidence"] if "[cboe]" in ln]
    pg_ev = [ln for ln in gate["evidence"] if "[polygon_gex]" in ln]
    assert cboe_ev
    assert pg_ev


def test_main_scored_true_when_either_store_passes(tmp_path, monkeypatch):
    """scored=True if EITHER store has at least one PASS — evidence line."""
    import scripts.validate_gex as vgex

    (tmp_path / "cboe").mkdir()
    pg_dir = tmp_path / "polygon_gex"
    pg_dir.mkdir()

    # Patch _boot in the module so the polygon store returns a PASS
    monkeypatch.setattr(vgex, "_boot", lambda l, s: (0.05, 0.01, 0.09))

    # Frame large enough to clear MIN_PER_BUCKET
    n = MIN_PER_BUCKET * 4
    df = _gex_frame(n, long_frac=0.5, seed=3)
    df.to_parquet(pg_dir / "summary_SYN.parquet")

    monkeypatch.setattr(vgex.config, "data_dir", lambda: tmp_path)
    monkeypatch.setattr(vgex.config, "ROOT", tmp_path)

    vgex.main()

    gate = json.loads((tmp_path / "gex" / "gate.json").read_text())
    assert gate["scored"] is True
    assert gate["status"] == "passed"
    assert gate["weight"] == 0.10
