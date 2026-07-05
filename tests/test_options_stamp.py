"""Tests for the Options Alpha W1.3 / W-C entry-quality harness.

Covers (per the wave spec):
* Stamp module (engine/options_stamp.py):
  - PIT no-lookahead: a fire on date D never receives store data with as-of > D.
  - doi_slope / voi_flag null when fewer than the required prior chain days exist.
  - opt_iv_rank_252 is ALWAYS null (ruling A9).
  - adjusted roots (AAPL1) → all-null stamp.
* W-C stamp extensions:
  - PIT no-lookahead for skew snapshots: a fire on D never uses a future skew row.
  - PIT no-lookahead for ivspread snapshots: same pattern.
  - opt_skew_5d_chg is null when fewer than 2 qualifying snapshots exist.
  - skew/ivspread absent (None) → W-C cols remain null (never crash).
* Stamping pass (scripts/stamp_options_state.py):
  - schema-union: legacy rows without stamp columns get them added as null.
  - schema-union non-destructiveness: an existing-value row is never overwritten.
  - backfill-does-not-overwrite: an already-stamped row is never re-stamped.
* Gate (scripts/validate_options_entry.py):
  - building_history path: scored=False, no verdict when buckets are under n≥30.
  - synthetic n≥30 with a real conditioned effect produces a "signal" verdict.
  - W-C new-bucket building_history: all five new buckets report correctly.
  - synthetic n≥30 for S-IVSPREAD-F produces a signal verdict.
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
    _skew_stamp,
    _ivspread_stamp,
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
    """A name with zero data-store coverage yields a stamp with every column present.

    W-C note: opt_opex_days is computed from the OPEX calendar (not a data store) and may
    be non-null even for a name with no polygon_gex/skew/ivspread coverage. All other
    data-store-dependent columns must be null when no stores are present."""
    s = stamp_options_state(
        "2026-06-24", "NOCOV",
        read_summary=lambda t: None,
        chain_dates=[],
        read_chain=lambda d: None,
        skew_df=None,
        ivspread_df=None,
        _skew_loader=lambda: None,
        _ivspread_loader=lambda: None,
    )
    assert set(s.keys()) == set(STAMP_COLS)
    # data-store-dependent cols must all be null
    data_store_cols = [c for c in STAMP_COLS if c != "opt_opex_days"]
    assert all(s[c] is None for c in data_store_cols), (
        f"Expected all data-store cols null, got: "
        f"{[(c, s[c]) for c in data_store_cols if s[c] is not None]}"
    )
    # opt_opex_days may be None or int (calendar-derived; depends on engine/opex availability)


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


# ── W-C: PIT no-lookahead for skew/ivspread snapshots ───────────────────────

def _skew_frame(dates, *, ticker="FOO", skews=None):
    """Synthetic skew snapshots DataFrame (date str column, underlying str, skew float)."""
    rows = []
    for i, d in enumerate(dates):
        rows.append({
            "date": d if isinstance(d, str) else d.isoformat(),
            "underlying": ticker,
            "skew": (skews[i] if skews is not None else float(0.10 + i * 0.01)),
        })
    return pd.DataFrame(rows)


def _ivspread_frame(dates, *, ticker="FOO", vals=None):
    """Synthetic ivspread snapshots DataFrame (date str column, underlying str, ivspread_rel float)."""
    rows = []
    for i, d in enumerate(dates):
        rows.append({
            "date": d if isinstance(d, str) else d.isoformat(),
            "underlying": ticker,
            "ivspread_rel": (vals[i] if vals is not None else float(0.02 + i * 0.005)),
        })
    return pd.DataFrame(rows)


def test_pit_no_lookahead_skew():
    """A fire on date D must NOT see a skew snapshot with date > D (future-spike test).

    We plant a 100x spike on a future date; a fire before it must see a flat series."""
    dates = ["2026-06-21", "2026-06-22", "2026-06-23", "2026-06-24", "2026-06-25"]
    future_spike = "2026-06-25"  # spike date: future relative to fire on 06-23
    skews = [0.05, 0.06, 0.07, 0.08, 999.0]  # last is the future spike
    sdf = _skew_frame(dates, skews=skews)

    # fire on 06-23 (index 2): must NOT see the 06-25 spike
    result = _skew_stamp(_dt.date(2026, 6, 23), "FOO", sdf)
    # should see skew = 0.07 (the 06-23 row), NOT 999.0
    assert result["opt_skew"] is not None
    assert result["opt_skew"] == pytest.approx(0.07, abs=1e-6)

    # verify the spike date itself would be visible on 06-25
    result_future = _skew_stamp(_dt.date(2026, 6, 25), "FOO", sdf)
    assert result_future["opt_skew"] == pytest.approx(999.0, abs=1e-6)


def test_pit_no_lookahead_ivspread():
    """A fire on date D must NOT see an ivspread snapshot with date > D.

    Mirror of the future-OI-spike leak test in the W1.3 chain test."""
    dates = ["2026-06-28", "2026-06-29", "2026-06-30", "2026-07-01"]
    future_spike_date = "2026-07-01"
    vals = [0.01, 0.02, 0.03, 999.0]  # last is the future spike
    idf = _ivspread_frame(dates, vals=vals)

    # fire on 06-30: must see 0.03, NOT the 07-01 spike
    result = _ivspread_stamp(_dt.date(2026, 6, 30), "FOO", idf)
    assert result["opt_ivspread_rel"] is not None
    assert result["opt_ivspread_rel"] == pytest.approx(0.03, abs=1e-6)

    # on 07-01 the spike should be visible
    result_future = _ivspread_stamp(_dt.date(2026, 7, 1), "FOO", idf)
    assert result_future["opt_ivspread_rel"] == pytest.approx(999.0, abs=1e-6)


def test_skew_5d_chg_null_on_single_snapshot():
    """opt_skew_5d_chg is None when there is only one qualifying skew snapshot."""
    sdf = _skew_frame(["2026-06-21"], skews=[0.10])
    result = _skew_stamp(_dt.date(2026, 6, 21), "FOO", sdf)
    assert result["opt_skew"] == pytest.approx(0.10, abs=1e-6)
    # only one row → cannot compute 5d change
    assert result["opt_skew_5d_chg"] is None


def test_skew_5d_chg_computed_when_enough_history():
    """opt_skew_5d_chg = latest minus the snapshot >= 5 calendar days earlier."""
    # 10 days apart = satisfies the 5-calendar-day requirement
    dates = ["2026-06-15", "2026-06-20", "2026-06-25"]
    skews = [0.10, 0.12, 0.15]
    sdf = _skew_frame(dates, skews=skews)

    # fire on 06-25: latest=0.15, 5-day-or-more-back = 06-15 (0.10) or 06-20 (0.12)
    # _skew_stamp uses the LATEST of the rows that are >= 5 calendar days back
    # cutoff = 06-25 - 5d = 06-20; rows <= 06-20: 06-15 (0.10) and 06-20 (0.12)
    # latest of those = 06-20 with skew 0.12
    result = _skew_stamp(_dt.date(2026, 6, 25), "FOO", sdf)
    assert result["opt_skew"] == pytest.approx(0.15, abs=1e-6)
    assert result["opt_skew_5d_chg"] == pytest.approx(0.15 - 0.12, abs=1e-5)


def test_skew_ivspread_absent_yields_null():
    """When skew_df / ivspread_df are None, the W-C stamp cols are all None (never crash)."""
    s = stamp_options_state(
        "2026-06-24", "FOO",
        read_summary=lambda t: None,
        chain_dates=[],
        read_chain=lambda d: None,
        skew_df=None,
        ivspread_df=None,
        _skew_loader=lambda: None,
        _ivspread_loader=lambda: None,
    )
    assert s["opt_skew"] is None
    assert s["opt_skew_5d_chg"] is None
    assert s["opt_ivspread_rel"] is None
    # all STAMP_COLS present
    assert set(s.keys()) == set(STAMP_COLS)


def test_all_stamp_cols_present_with_wc_data():
    """A full stamp with W-C data returns all STAMP_COLS including the 7 new W-C cols."""
    dates = [_dt.date(2026, 6, d) for d in range(15, 26)]
    skew_dates = ["2026-06-15", "2026-06-20", "2026-06-25"]
    ivspread_dates = ["2026-06-25"]

    s = stamp_options_state(
        "2026-06-25", "FOO",
        read_summary=lambda t: _summary_frame([f"2026-06-{d}" for d in range(15, 26)]),
        chain_dates=dates,
        read_chain=lambda d: _chain_frame("FOO"),
        skew_df=_skew_frame(skew_dates, skews=[0.10, 0.12, 0.15]),
        ivspread_df=_ivspread_frame(ivspread_dates, vals=[0.02]),
        _skew_loader=None,
        _ivspread_loader=None,
    )
    # all STAMP_COLS present
    assert set(s.keys()) == set(STAMP_COLS)
    # W-C cols have values where data exists
    assert s["opt_skew"] is not None
    assert s["opt_ivspread_rel"] is not None
    # opt_iv_rank_252 still null (A9)
    assert s["opt_iv_rank_252"] is None


# ── W-C: schema-union non-destructiveness ───────────────────────────────────

def test_schema_union_non_destructiveness_on_ledger_copy():
    """schema-union on a copy must not destroy any existing column values.

    We create a ledger with some existing stamp values, run stamp_ledger on a copy,
    and verify that (a) previously-null W-C cols are added, (b) no existing non-null
    value is modified or destroyed."""
    base = _legacy_ledger()
    # simulate a row that already has W1.3 stamps from a prior run
    for c in STAMP_COLS:
        if c not in base.columns:
            base[c] = None
    # set sentinel on one specific cell
    base.loc[0, "opt_iv30"] = 42.0
    base.loc[0, "opt_gamma_regime"] = "long"

    # copy and run stamp_ledger (which will try to stamp unstamped rows)
    import copy
    df_copy = copy.deepcopy(base)
    out, _ = stamp_ledger(df_copy)

    # the sentinel must survive (schema-union must not overwrite)
    # row 0 has a non-null opt_iv30 → it should not be overwritten
    assert out.loc[0, "opt_iv30"] == 42.0
    assert out.loc[0, "opt_gamma_regime"] == "long"

    # all STAMP_COLS must be present after the union
    for col in STAMP_COLS:
        assert col in out.columns, f"W-C column {col} missing after schema-union"


# ── W-C: new bucket verdict machinery ───────────────────────────────────────

def _stamped_ledger_with_ivspread(n_per_bucket, *, effect=0.0):
    """Synthetic ledger for S-IVSPREAD-F: split by opt_ivspread_rel > 0 vs <= 0."""
    rng = np.random.default_rng(123)
    rows = []
    # conditioned (ivspread_rel > 0): higher clean rate
    for i in range(n_per_bucket):
        rows.append({
            "as_of": "2026-07-05", "ticker": f"T{i}", "lane": "buy", "horizon": 21,
            "opt_ivspread_rel": 0.01 + float(rng.random() * 0.05),  # positive
            "post_cushion_breach": bool(rng.random() < 0.5 - effect),
            "terminal_state_clean8_21": CLEAN if rng.random() < 0.5 + effect else "STOPPED",
            "fwd_mfe_21": float(rng.normal(0.10 + effect, 0.02)),
            "fwd_ret_5": float(rng.normal(0.02, 0.01)),
        })
    # base (ivspread_rel <= 0): lower clean rate
    for i in range(n_per_bucket):
        rows.append({
            "as_of": "2026-07-05", "ticker": f"B{i}", "lane": "buy", "horizon": 21,
            "opt_ivspread_rel": -0.01 - float(rng.random() * 0.05),  # negative
            "post_cushion_breach": bool(rng.random() < 0.5),
            "terminal_state_clean8_21": CLEAN if rng.random() < 0.5 else "STOPPED",
            "fwd_mfe_21": float(rng.normal(0.10, 0.02)),
            "fwd_ret_5": float(rng.normal(0.02, 0.01)),
        })
    df = pd.DataFrame(rows)
    for c in STAMP_COLS:
        if c not in df.columns:
            df[c] = None
    return df


def test_wc_buckets_building_history_below_threshold():
    """All five W-C buckets are building_history when n < 30 per bucket."""
    # ledger with only S-VOI data (from existing test helper) — W-C cols absent
    df = _stamped_ledger(5)
    gate = build_gate(df)
    for tid in ("S-IVSPREAD-F", "S-SKEW_DECEL", "S-TOP_RISK", "S-PIN_RISK", "S-VOI2"):
        assert gate["tests"][tid].get("ready") is False
        assert gate["verdicts"].get(tid) == "building_history", (
            f"{tid} should be building_history, got {gate['verdicts'].get(tid)}")
    # gate schema should be v2
    assert gate["schema"] == "options_entry.gate.v2"
    # fdr_family block present
    assert "fdr_family" in gate
    assert gate["fdr_family"]["family_size"] == 22
    assert gate["fdr_family"]["alpha"] == pytest.approx(0.10)
    # per_family_status block present
    assert "per_family_status" in gate
    assert gate["per_family_status"]["S-IVSPREAD-F"] == "building_history"


def test_wc_ivspread_f_synthetic_signal():
    """S-IVSPREAD-F produces a 'signal' verdict when n>=30 and a strong effect is present."""
    df = _stamped_ledger_with_ivspread(MIN_PER_BUCKET + 20, effect=0.35)
    gate = build_gate(df)
    t = gate["tests"]["S-IVSPREAD-F"]
    assert t["ready"] is True, f"Expected ready=True, got n_cond={t['n_cond']} n_base={t['n_base']}"
    assert gate["verdicts"]["S-IVSPREAD-F"] == "signal", (
        f"Expected 'signal', got {gate['verdicts']['S-IVSPREAD-F']}"
    )
    # gate is still NOT scored (machine, not a lever)
    assert gate["scored"] is False
    # at least one primitive CI excludes 0 in beneficial direction
    beneficial = (
        (t["clean"]["excludes_zero"] and t["clean"]["delta"] > 0)
        or (t["breach"]["excludes_zero"] and t["breach"]["delta"] < 0)
        or (t["mfe21"]["excludes_zero"] and t["mfe21"]["delta"] > 0)
    )
    assert beneficial, "No beneficial primitive CI found — effect may be too small for this seed"


def test_wc_ivspread_f_no_effect():
    """S-IVSPREAD-F returns 'no_effect' when n>=30 but no conditioned effect exists."""
    df = _stamped_ledger_with_ivspread(MIN_PER_BUCKET + 20, effect=0.0)
    gate = build_gate(df)
    t = gate["tests"]["S-IVSPREAD-F"]
    assert t["ready"] is True
    assert gate["verdicts"]["S-IVSPREAD-F"] == "no_effect"
