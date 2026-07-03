"""Tests for the Options Alpha W1.3 entry-quality harness.

Covers (per the wave spec):
* Stamp module (engine/options_stamp.py):
  - PIT no-lookahead: a fire on date D never receives store data with as-of > D.
  - doi_slope / voi_flag null when fewer than the required prior chain days exist.
  - opt_iv_rank_252 is ALWAYS null (ruling A9).
  - adjusted roots (AAPL1) → all-null stamp.
* Stamping pass (scripts/stamp_options_state.py):
  - schema-union: legacy rows without stamp columns get them added as null.
  - backfill-does-not-overwrite: an already-stamped row is never re-stamped.
* Gate (scripts/validate_options_entry.py):
  - building_history path: scored=False, no verdict when buckets are under n≥30.
  - synthetic n≥30 with a real conditioned effect produces a "signal" verdict.
"""
import datetime as _dt
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from engine.options_stamp import (  # noqa: E402
    STAMP_COLS,
    stamp_options_state,
)
from scripts.stamp_options_state import stamp_ledger  # noqa: E402
from scripts.validate_options_entry import (  # noqa: E402
    build_gate,
    MIN_PER_BUCKET,
    CLEAN,
)


# ── synthetic store builders ─────────────────────────────────────────────────
def _summary_frame(dates, *, iv30=0.25, regime="long"):
    """A polygon_gex summary frame: DatetimeIndex, the columns the stamp reads."""
    idx = pd.to_datetime(list(dates))
    n = len(idx)
    return pd.DataFrame(
        {
            "gamma_regime": [regime] * n,
            "dist_to_flip_pct": np.linspace(5.0, 10.0, n),
            "magnet_up": [110.0] * n,
            "magnet_down": [95.0] * n,
            "iv30": [iv30] * n,
        },
        index=idx,
    )


def _chain_frame(ticker, *, spot=100.0, call_oi=1000.0, put_oi=800.0, volume=50.0):
    """One chain snapshot for a single name with a few near-money strikes."""
    strikes = [95.0, 100.0, 105.0]
    rows = []
    for k in strikes:
        rows.append({"underlying": ticker, "K": k, "is_call": True,
                     "oi": call_oi, "volume": volume, "spot": spot})
        rows.append({"underlying": ticker, "K": k, "is_call": False,
                     "oi": put_oi, "volume": volume, "spot": spot})
    return pd.DataFrame(rows)


# ── PIT no-lookahead ─────────────────────────────────────────────────────────
def test_pit_no_lookahead_summary():
    """A fire on D must use the summary row on/before D, NEVER a future row."""
    dates = ["2026-06-15", "2026-06-16", "2026-06-17", "2026-06-18"]
    # make each day's iv30 distinguishable so we can prove which row was used
    idx = pd.to_datetime(dates)
    sdf = pd.DataFrame(
        {
            "gamma_regime": ["long"] * 4,
            "dist_to_flip_pct": [1.0, 2.0, 3.0, 4.0],
            "magnet_up": [110.0] * 4, "magnet_down": [95.0] * 4,
            "iv30": [0.10, 0.20, 0.30, 0.40],
        },
        index=idx,
    )

    def read_summary(_t):
        return sdf

    # fire on 06-16 must see iv30=0.20 (that day) and dist=2.0 — never the 0.30/0.40 future rows
    s = stamp_options_state("2026-06-16", "FOO", read_summary=read_summary,
                            chain_dates=[], read_chain=lambda d: None)
    assert s["opt_iv30"] == pytest.approx(0.20)
    assert s["opt_dist_to_flip_pct"] == pytest.approx(2.0)


def test_pit_no_lookahead_chain():
    """doi_slope/voi_flag on date D use only chain snapshots ≤ D, never a future snapshot.

    We plant a huge OI spike on a FUTURE day; a fire before it must not see the spike."""
    dates = [_dt.date(2026, 6, d) for d in range(15, 25)]  # 10 days
    future_spike_day = _dt.date(2026, 6, 24)

    def read_chain(d):
        # normal small OI, but the future day has a 100x spike — if PIT leaks, slope explodes
        oi = 100000.0 if d == future_spike_day else 1000.0
        return _chain_frame("FOO", call_oi=oi)

    # fire on 06-20 (has 6 prior snapshots 15..20) — must NOT include the 06-24 spike
    s = stamp_options_state("2026-06-20", "FOO", read_summary=lambda t: None,
                            chain_dates=dates, read_chain=read_chain)
    # all six window days have identical OI (1000) → slope ≈ 0, definitely not spiked
    assert s["opt_doi_slope_5d"] is not None
    assert abs(s["opt_doi_slope_5d"]) < 0.01  # flat series, no future leak


def test_doi_null_when_insufficient_history():
    """< 5 prior chain days ⇒ opt_doi_slope_5d is null (PIT-honest, no fabrication)."""
    dates = [_dt.date(2026, 6, 15), _dt.date(2026, 6, 16)]  # only 2 days

    def read_chain(d):
        return _chain_frame("FOO")

    s = stamp_options_state("2026-06-16", "FOO", read_summary=lambda t: None,
                            chain_dates=dates, read_chain=read_chain)
    assert s["opt_doi_slope_5d"] is None
    # voi_flag needs only 2 days → it CAN be computed
    assert s["opt_voi_flag"] in (True, False)


def test_iv_rank_252_always_null():
    """Ruling A9: opt_iv_rank_252 is never computed in this module."""
    dates = [_dt.date(2026, 6, d) for d in range(15, 25)]
    s = stamp_options_state(
        "2026-06-24", "FOO",
        read_summary=lambda t: _summary_frame([f"2026-06-{d}" for d in range(15, 25)]),
        chain_dates=dates, read_chain=lambda d: _chain_frame("FOO"),
    )
    assert s["opt_iv_rank_252"] is None


def test_adjusted_root_all_null():
    """Corporate-action-adjusted roots (numeric suffix) → all-null stamp, never mis-parsed."""
    dates = [_dt.date(2026, 6, d) for d in range(15, 25)]
    s = stamp_options_state("2026-06-24", "AAPL1",
                            read_summary=lambda t: _summary_frame(["2026-06-24"]),
                            chain_dates=dates, read_chain=lambda d: _chain_frame("AAPL1"))
    assert all(s[c] is None for c in STAMP_COLS)


def test_stamp_always_has_all_columns():
    """A name with zero coverage still yields a stamp with every column present (as None)."""
    s = stamp_options_state("2026-06-24", "NOCOV", read_summary=lambda t: None,
                            chain_dates=[], read_chain=lambda d: None)
    assert set(s.keys()) == set(STAMP_COLS)
    assert all(v is None for v in s.values())


# ── stamping pass: schema-union + backfill-does-not-overwrite ────────────────
def _legacy_ledger():
    """A pre-stamp ledger with NONE of the opt_* columns (the schema-union input)."""
    return pd.DataFrame({
        "as_of": ["2026-06-20", "2026-06-20", "2026-06-21"],
        "ticker": ["FOO", "BAR", "FOO"],
        "lane": ["buy", "buy", "buy"],
        "horizon": [5, 5, 5],
        "fwd_ret_5": [0.01, -0.02, 0.03],
    })


def test_schema_union_adds_columns(monkeypatch):
    """Legacy rows with no stamp columns get them added; a covered name is stamped."""
    df = _legacy_ledger()
    # give FOO coverage; BAR none
    monkeypatch.setattr("engine.options_stamp._default_chain_dates",
                        lambda: [_dt.date(2026, 6, d) for d in range(15, 22)])
    monkeypatch.setattr("engine.options_stamp._default_read_chain",
                        lambda d: _chain_frame("FOO"))
    monkeypatch.setattr("engine.options_stamp._default_read_summary",
                        lambda t: _summary_frame([f"2026-06-{d}" for d in range(15, 22)])
                        if t == "FOO" else None)

    out, n = stamp_ledger(df)
    # every stamp column now present
    for c in STAMP_COLS:
        assert c in out.columns
    # FOO rows stamped (regime present), BAR row all-null
    foo = out[out["ticker"] == "FOO"]
    bar = out[out["ticker"] == "BAR"]
    assert foo["opt_gamma_regime"].notna().all()
    assert bar[STAMP_COLS].isna().all(axis=1).all()
    assert n == 2  # two FOO rows stamped


def test_backfill_does_not_overwrite(monkeypatch):
    """A row already carrying a stamp value is NEVER re-stamped (idempotent)."""
    df = _legacy_ledger()
    monkeypatch.setattr("engine.options_stamp._default_chain_dates",
                        lambda: [_dt.date(2026, 6, d) for d in range(15, 22)])
    monkeypatch.setattr("engine.options_stamp._default_read_chain",
                        lambda d: _chain_frame("FOO"))
    monkeypatch.setattr("engine.options_stamp._default_read_summary",
                        lambda t: _summary_frame([f"2026-06-{d}" for d in range(15, 22)])
                        if t == "FOO" else None)

    out1, n1 = stamp_ledger(df)
    assert n1 == 2
    # pin a sentinel on one already-stamped row, then re-run — it must survive
    out1.loc[out1["ticker"] == "FOO", "opt_iv30"] = 9.99
    out2, n2 = stamp_ledger(out1)
    assert n2 == 0  # nothing re-stamped
    assert (out2.loc[out2["ticker"] == "FOO", "opt_iv30"] == 9.99).all()


# ── gate: building_history + synthetic-signal ────────────────────────────────
def _stamped_ledger(n_per_bucket, *, effect=0.0, voi=True):
    """Synthetic stamped ledger with 2*n_per_bucket fires split by voi_flag, with an optional
    conditioned effect on the clean-liftoff rate (higher CLEAN incidence in the voi=True bucket)."""
    rng = np.random.default_rng(42)
    rows = []
    for i in range(n_per_bucket):
        # conditioned (voi True) bucket — CLEAN with prob 0.5+effect
        rows.append({
            "as_of": "2026-06-20", "ticker": f"T{i}", "lane": "buy", "horizon": 21,
            "opt_voi_flag": True,
            "post_cushion_breach": bool(rng.random() < 0.5 - effect),
            "terminal_state_clean8_21": CLEAN if rng.random() < 0.5 + effect else "STOPPED",
            "fwd_mfe_21": float(rng.normal(0.10 + effect, 0.02)),
            "fwd_ret_5": float(rng.normal(0.02 + effect, 0.01)),
            "fwd_mfe_5": float(rng.normal(0.03 + effect, 0.01)),
        })
    for i in range(n_per_bucket):
        rows.append({
            "as_of": "2026-06-20", "ticker": f"B{i}", "lane": "buy", "horizon": 21,
            "opt_voi_flag": False,
            "post_cushion_breach": bool(rng.random() < 0.5),
            "terminal_state_clean8_21": CLEAN if rng.random() < 0.5 else "STOPPED",
            "fwd_mfe_21": float(rng.normal(0.10, 0.02)),
            "fwd_ret_5": float(rng.normal(0.02, 0.01)),
            "fwd_mfe_5": float(rng.normal(0.03, 0.01)),
        })
    df = pd.DataFrame(rows)
    # add the remaining stamp cols as null so STAMP_COLS coverage math works
    for c in STAMP_COLS:
        if c not in df.columns:
            df[c] = None
    return df


def test_gate_building_history_below_threshold():
    """Under n≥30 per bucket, the gate is scored=False / building_history with NO verdict."""
    df = _stamped_ledger(5)  # 5 per bucket, well under 30
    gate = build_gate(df)
    assert gate["scored"] is False
    assert gate["status"] == "building_history"
    assert gate["weight"] == 0.0
    # S-VOI not ready
    assert gate["tests"]["S-VOI"]["ready"] is False
    assert gate["verdicts"]["S-VOI"] == "building_history"


def test_gate_synthetic_signal_produces_verdict():
    """Fed n≥30 per bucket WITH a real conditioned effect, the bucket math produces a
    'signal' verdict — proving the machine can decide once history accrues."""
    df = _stamped_ledger(MIN_PER_BUCKET + 20, effect=0.30)  # strong effect, 50 per bucket
    gate = build_gate(df)
    assert gate["tests"]["S-VOI"]["ready"] is True
    assert gate["verdicts"]["S-VOI"] == "signal"
    # at least one primitive delta CI excludes 0 in the beneficial direction
    t = gate["tests"]["S-VOI"]
    beneficial = (
        (t["clean"]["excludes_zero"] and t["clean"]["delta"] > 0)
        or (t["breach"]["excludes_zero"] and t["breach"]["delta"] < 0)
        or (t["mfe21"]["excludes_zero"] and t["mfe21"]["delta"] > 0)
    )
    assert beneficial
    # a scored gate with a signal is still NOT auto-scored in W1.3 (machine, not lever)
    assert gate["scored"] is False


def test_gate_null_effect_no_signal():
    """Fed n≥30 per bucket but NO conditioned effect, the ready bucket returns 'no_effect'."""
    df = _stamped_ledger(MIN_PER_BUCKET + 20, effect=0.0)
    gate = build_gate(df)
    assert gate["tests"]["S-VOI"]["ready"] is True
    assert gate["verdicts"]["S-VOI"] == "no_effect"
