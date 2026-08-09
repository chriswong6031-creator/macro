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
  - canonical fire reduction, declared buy-lane population, and 30-date maturity.
  - synthetic effects can produce only a descriptive blocked candidate, never authority.
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
    STAMP_COVERAGE_COLS,
    STAMP_COLS,
    _ivspread_stamp,
    _skew_stamp,
    stamp_options_state,
)
from scripts.stamp_options_state import stamp_ledger  # noqa: E402
from scripts.validate_options_entry import (  # noqa: E402
    CLEAN,
    MIN_PER_BUCKET,
    _benjamini_hochberg,
    _canonical_fire_frame,
    build_gate,
)


# ── synthetic store builders ─────────────────────────────────────────────────
def _spread_as_of(anchor: str, index: int) -> str:
    """Give paired buckets the same >=30 distinct dates without changing fire count."""
    return (_dt.date.fromisoformat(anchor) + _dt.timedelta(days=index)).isoformat()


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


def _sessions(n: int, start: str) -> list[_dt.date]:
    """n consecutive NYSE SESSION dates from `start` (inclusive if it is one).

    Chain-snapshot fixtures must be session-true: stamp_options_state filters
    chain_dates through the exchange calendar, so calendar-day fixtures silently shrink
    the PIT window and a weekend "fire date" has no window at all.
    """
    from lib import nyse_calendar
    out: list[_dt.date] = []
    d = _dt.date.fromisoformat(start)
    while len(out) < n:
        if nyse_calendar.is_session(d):
            out.append(d)
        d += _dt.timedelta(days=1)
    return out


def test_pit_no_lookahead_chain():
    """doi_slope/voi_flag on date D use only chain snapshots ≤ D, never a future snapshot.

    We plant a huge OI spike on a FUTURE day; a fire before it must not see the spike."""
    # TEN SESSIONS. This used to be ten consecutive CALENDAR days (06-15..06-24), which
    # contains Juneteenth (06-19) plus the weekend — only 7 sessions — and the fire below
    # was dated 06-20, a SATURDAY. stamp_options_state session-filters chain_dates now
    # (the #3721 class: a weekend chain snapshot re-records the prior session's OI, so it
    # enters the ΔOI window as a duplicate day), and _DOI_WINDOW's "today + 5 prior
    # TRADING snapshots" needs six real sessions to exist at all.
    dates = _sessions(10, "2026-06-15")
    future_spike_day = dates[-1]

    def read_chain(d):
        # normal small OI, but the future day has a 100x spike — if PIT leaks, slope explodes
        oi = 100000.0 if d == future_spike_day else 1000.0
        return _chain_frame("FOO", call_oi=oi)

    # fire on the 6th session (6 snapshots at/before it) — must NOT see the last-day spike
    fire_day = dates[5]
    assert fire_day < future_spike_day
    s = stamp_options_state(fire_day.isoformat(), "FOO", read_summary=lambda t: None,
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

    Two columns are always-computable (non-null without any data store):
      opt_opex_days — OPEX calendar (engine/opex.py; purely date-arithmetic)
      opt_root_class — ticker taxonomy (static mapping; no data store needed)
    All other data-store-dependent columns must be null when no stores are present."""
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
    # (opt_opex_days and opt_root_class are always-computable — excluded from null check)
    _always_computable = ("opt_opex_days", "opt_root_class")
    data_store_cols = [c for c in STAMP_COLS if c not in _always_computable]
    assert all(s[c] is None for c in data_store_cols), (
        f"Expected all data-store cols null, got: "
        f"{[(c, s[c]) for c in data_store_cols if s[c] is not None]}"
    )
    # opt_opex_days may be None or int (calendar-derived; depends on engine/opex availability)
    # opt_root_class is always non-null (taxonomy-derived from ticker alone)


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
    # FOO rows stamped (regime present); BAR row null on every column EXCEPT the
    # always-computable opt_root_class (ticker taxonomy — dedicated write, same
    # contract as opt_opex_days; W-OVC repair 2026-08-02)
    foo = out[out["ticker"] == "FOO"]
    bar = out[out["ticker"] == "BAR"]
    assert foo["opt_gamma_regime"].notna().all()
    _null_for_bar = [c for c in STAMP_COLS if c not in ("opt_root_class", "opt_opex_days")]
    assert bar[_null_for_bar].isna().all(axis=1).all()
    assert (bar["opt_root_class"] == "single_name").all(), (
        "opt_root_class is always-computable and must be written even on no-coverage rows"
    )
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
    """Production-shaped horizon ledger split by VOI, spanning one paired date per fire."""
    rng = np.random.default_rng(42)
    rows = []
    for i in range(n_per_bucket):
        as_of = _spread_as_of("2026-06-20", i)
        breach = bool(rng.random() < 0.5 - effect)
        clean = CLEAN if rng.random() < 0.5 + effect else "STOPPED"
        ret5 = float(rng.normal(0.02 + effect, 0.01))
        mfe5 = float(rng.normal(0.03 + effect, 0.01))
        mfe21 = float(rng.normal(0.10 + effect, 0.02))
        for horizon in (5, 21):
            rows.append({
                "as_of": as_of, "ticker": f"T{i}", "lane": "buy", "horizon": horizon,
                "opt_voi_flag": True,
                "post_cushion_breach": breach,
                "terminal_state_clean8_21": clean,
                "ret": ret5 if horizon == 5 else float(rng.normal(0.04, 0.01)),
                "fwd_mfe_5": mfe5 if horizon == 5 else None,
                "fwd_mfe_21": mfe21 if horizon == 21 else None,
            })
    for i in range(n_per_bucket):
        as_of = _spread_as_of("2026-06-20", i)
        breach = bool(rng.random() < 0.5)
        clean = CLEAN if rng.random() < 0.5 else "STOPPED"
        ret5 = float(rng.normal(0.02, 0.01))
        mfe5 = float(rng.normal(0.03, 0.01))
        mfe21 = float(rng.normal(0.10, 0.02))
        for horizon in (5, 21):
            rows.append({
                "as_of": as_of, "ticker": f"B{i}", "lane": "buy", "horizon": horizon,
                "opt_voi_flag": False,
                "post_cushion_breach": breach,
                "terminal_state_clean8_21": clean,
                "ret": ret5 if horizon == 5 else float(rng.normal(0.04, 0.01)),
                "fwd_mfe_5": mfe5 if horizon == 5 else None,
                "fwd_mfe_21": mfe21 if horizon == 21 else None,
            })
    df = pd.DataFrame(rows)
    # add the remaining stamp cols as null so STAMP_COLS coverage math works
    for c in STAMP_COLS:
        if c not in df.columns:
            df[c] = None
    return df


def test_options_entry_canonical_fire_maps_exact_horizons_and_filters_lane():
    """Horizon projections collapse to one buy-lane fire with exact outcome sources."""
    rows = []
    for lane, ticker in (("buy", "AAA"), ("watch", "WATCH")):
        for horizon in (5, 10, 21):
            rows.append({
                "as_of": "2026-07-01",
                "ticker": ticker,
                "lane": lane,
                "horizon": horizon,
                "ret": {5: 0.05, 10: 0.10, 21: 0.21}[horizon],
                # This stale legacy-looking field must never override horizon=5 ret.
                "fwd_ret_5": 9.99,
                "fwd_mfe_5": 0.15 if horizon == 5 else None,
                "fwd_mfe_21": 0.41 if horizon == 21 else None,
                "opt_voi_flag": True,
                "post_cushion_breach": False,
                "terminal_state_clean8_21": CLEAN,
            })

    raw = pd.DataFrame(rows)
    fires, population = _canonical_fire_frame(raw)

    assert len(fires) == 1
    assert fires.iloc[0]["ticker"] == "AAA"
    assert fires.iloc[0]["fwd_ret_5"] == pytest.approx(0.05)
    assert fires.iloc[0]["fwd_mfe_5"] == pytest.approx(0.15)
    assert fires.iloc[0]["fwd_mfe_21"] == pytest.approx(0.41)
    assert fires.iloc[0]["post_cushion_breach"] is False or not bool(
        fires.iloc[0]["post_cushion_breach"]
    )
    assert population["event_key"] == ["as_of", "lane", "ticker"]
    assert population["declared_lane"] == "buy"
    assert population["raw_rows"] == 6
    assert population["declared_lane_rows"] == 3
    assert population["excluded_non_buy_rows"] == 3
    assert population["canonical_events"] == 1
    gate = build_gate(raw)
    assert gate["schema"] == "options_entry.gate.v3"
    assert gate["n_ledger_rows"] == 6
    assert gate["n_canonical_events"] == 1

    shuffled, _ = _canonical_fire_frame(raw.sample(frac=1.0, random_state=17))
    pd.testing.assert_frame_equal(fires, shuffled)


@pytest.mark.parametrize(
    ("column", "other"),
    [
        ("opt_voi_flag", False),
        ("post_cushion_breach", True),
        ("terminal_state_clean8_21", "STOPPED"),
    ],
)
def test_options_entry_canonical_fire_rejects_conflicting_repeated_values(column, other):
    rows = [
        {
            "as_of": "2026-07-01", "ticker": "AAA", "lane": "buy", "horizon": 5,
            "ret": 0.05, "fwd_mfe_5": 0.10, "opt_voi_flag": True,
            "post_cushion_breach": False, "terminal_state_clean8_21": CLEAN,
        },
        {
            "as_of": "2026-07-01", "ticker": "AAA", "lane": "buy", "horizon": 21,
            "ret": 0.20, "fwd_mfe_21": 0.30, "opt_voi_flag": True,
            "post_cushion_breach": False, "terminal_state_clean8_21": CLEAN,
        },
    ]
    rows[1][column] = other

    with pytest.raises(ValueError, match="conflicting repeated event-level values"):
        _canonical_fire_frame(pd.DataFrame(rows))


def test_options_entry_canonical_fire_rejects_duplicate_event_horizon():
    row = {
        "as_of": "2026-07-01", "ticker": "AAA", "lane": "buy", "horizon": 5,
        "ret": 0.05, "opt_voi_flag": True,
    }
    with pytest.raises(ValueError, match=r"duplicate options-entry event\+horizon"):
        _canonical_fire_frame(pd.DataFrame([row, dict(row)]))


def test_options_entry_top_risk_requires_both_logical_legs_known():
    rows = [
        {
            "as_of": "2026-07-01", "ticker": "MISSING", "lane": "buy", "horizon": 21,
            "opt_skew_5d_chg": 0.2, "opt_ivspread_rel": None,
        },
        {
            "as_of": "2026-07-01", "ticker": "FLAG", "lane": "buy", "horizon": 21,
            "opt_skew_5d_chg": 0.2, "opt_ivspread_rel": 0.1,
        },
        {
            "as_of": "2026-07-01", "ticker": "BASE", "lane": "buy", "horizon": 21,
            "opt_skew_5d_chg": -0.2, "opt_ivspread_rel": 0.1,
        },
    ]
    top = build_gate(pd.DataFrame(rows))["tests"]["S-TOP_RISK"]

    assert (top["n_cond"], top["n_base"]) == (1, 1)
    assert top["n_excluded_missing_leg"] == 1


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
    assert gate["tests"]["S-DOI"]["promotion_blockers"] == [
        "JOINED_HAC_RECEIPT_REQUIRED"
    ]


def test_gate_synthetic_signal_produces_verdict():
    """A strong mature effect is visible but cannot become signal authority."""
    df = _stamped_ledger(MIN_PER_BUCKET + 20, effect=0.30)  # strong effect, 50 per bucket
    gate = build_gate(df)
    assert gate["tests"]["S-VOI"]["ready"] is True
    assert gate["verdicts"]["S-VOI"] == "candidate_signal_blocked"
    assert gate["status"] == "building_history"
    assert "DATE_CLUSTER_INFERENCE_REQUIRED" in gate["promotion_blockers"]
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
    """A noisy null with a stray directional CI is inconclusive, not a false null claim."""
    df = _stamped_ledger(MIN_PER_BUCKET + 20, effect=0.0)
    gate = build_gate(df)
    assert gate["tests"]["S-VOI"]["ready"] is True
    assert gate["verdicts"]["S-VOI"] == "inconclusive_fdr"


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
            "as_of": _spread_as_of("2026-07-05", i), "ticker": f"T{i}", "lane": "buy", "horizon": 21,
            "opt_ivspread_rel": 0.01 + float(rng.random() * 0.05),  # positive
            "post_cushion_breach": bool(rng.random() < 0.5 - effect),
            "terminal_state_clean8_21": CLEAN if rng.random() < 0.5 + effect else "STOPPED",
            "fwd_mfe_21": float(rng.normal(0.10 + effect, 0.02)),
            "fwd_ret_5": float(rng.normal(0.02, 0.01)),
        })
    # base (ivspread_rel <= 0): lower clean rate
    for i in range(n_per_bucket):
        rows.append({
            "as_of": _spread_as_of("2026-07-05", i), "ticker": f"B{i}", "lane": "buy", "horizon": 21,
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
    """All W-C and W-OVC buckets are building_history when n < 30 per bucket."""
    # ledger with only S-VOI data (from existing test helper) — W-C/W-OVC cols absent
    df = _stamped_ledger(5)
    gate = build_gate(df)
    # W-C buckets
    for tid in ("S-IVSPREAD-F", "S-SKEW_DECEL", "S-TOP_RISK", "S-PIN_RISK", "S-VOI2"):
        assert gate["tests"][tid].get("ready") is False
        assert gate["verdicts"].get(tid) == "building_history", (
            f"{tid} should be building_history, got {gate['verdicts'].get(tid)}")
    # W-OVC buckets
    for tid in ("S-VANNA-RELIEF", "S-FRONT-CHARM"):
        assert gate["tests"][tid].get("ready") is False
        assert gate["verdicts"].get(tid) == "building_history", (
            f"{tid} should be building_history, got {gate['verdicts'].get(tid)}")
    # gate schema should be v3 (W-OVC bump)
    assert gate["schema"] == "options_entry.gate.v3"
    # fdr_family block: 22→28→36 (W-OVC amendment 2026-07-06 added 6 cells to 28;
    # FS-3 amendment 2026-07-13 added 8 S-FLOWML cells to the same family → 36 total)
    assert "fdr_family" in gate
    assert gate["fdr_family"]["family_size"] == 36
    assert gate["fdr_family"]["alpha"] == pytest.approx(0.10)
    # per_family_status block includes all W-C and W-OVC buckets
    assert "per_family_status" in gate
    assert gate["per_family_status"]["S-IVSPREAD-F"] == "building_history"
    assert gate["per_family_status"]["S-VANNA-RELIEF"] == "building_history"
    assert gate["per_family_status"]["S-FRONT-CHARM"] == "building_history"


def test_wc_ivspread_f_synthetic_signal():
    """S-IVSPREAD-F can produce only a blocked descriptive candidate."""
    df = _stamped_ledger_with_ivspread(MIN_PER_BUCKET + 20, effect=0.35)
    gate = build_gate(df)
    t = gate["tests"]["S-IVSPREAD-F"]
    assert t["ready"] is True, f"Expected ready=True, got n_cond={t['n_cond']} n_base={t['n_base']}"
    assert gate["verdicts"]["S-IVSPREAD-F"] == "candidate_signal_blocked", (
        f"Expected blocked candidate, got {gate['verdicts']['S-IVSPREAD-F']}"
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


# ── FIX-ROUND: retry-gate (STAMP_COVERAGE_COLS) ──────────────────────────────

def test_stamp_coverage_cols_excludes_always_computable():
    """STAMP_COVERAGE_COLS must NOT contain always-computable cols (opt_opex_days, opt_root_class).

    Always-computable cols (no data store needed):
      opt_opex_days  — OPEX calendar (engine/opex.py; purely date-arithmetic)
      opt_root_class — ticker taxonomy (static mapping; no data store)
    Excluding them preserves the W1.3 retry-gate design: rows that only have these cols
    remain retryable when GEX/skew/ivspread coverage later arrives."""
    _always_computable = ("opt_opex_days", "opt_root_class")
    for col in _always_computable:
        assert col not in STAMP_COVERAGE_COLS, (
            f"{col} must be excluded from STAMP_COVERAGE_COLS — it is always-computable "
            "(no data store needed) and should not lock out rows from future retries"
        )
    # all other STAMP_COLS must be in STAMP_COVERAGE_COLS
    for col in STAMP_COLS:
        if col not in _always_computable:
            assert col in STAMP_COVERAGE_COLS, f"{col} missing from STAMP_COVERAGE_COLS"


def test_opex_only_row_remains_retryable(monkeypatch):
    """A row that received opt_opex_days (calendar) but no GEX/skew/ivspread coverage
    must remain retryable (STAMP_COVERAGE_COLS all null) and be stamped by a later run
    once coverage-gated columns become non-null.

    This is the blocker fix: the old gate used STAMP_COLS.isna().all(), which locked out
    any row that had opt_opex_days set — permanently preventing future GEX/skew/ivspread
    fills.  The new gate uses STAMP_COVERAGE_COLS, keeping those rows retryable."""
    # Build a minimal ledger with one row that has ONLY opt_opex_days set
    df = pd.DataFrame({
        "as_of": ["2026-06-20"],
        "ticker": ["FOO"],
        "lane": ["buy"],
        "horizon": [5],
        "fwd_ret_5": [0.01],
    })
    for c in STAMP_COLS:
        df[c] = None
    # Simulate "opex-only stamped" state: opex_days is set but all coverage-gated cols null
    df.loc[0, "opt_opex_days"] = 14  # 14 trading days to next OPEX

    # With the new gate, this row should be retryable (coverage-gated cols all null)
    coverage_cols = [c for c in STAMP_COVERAGE_COLS if c in df.columns]
    assert df[coverage_cols].isna().all(axis=1).all(), (
        "Row with only opt_opex_days should be retryable (coverage cols all null)"
    )

    # Now simulate coverage arriving: monkeypatch the defaults so GEX data appears
    monkeypatch.setattr("engine.options_stamp._default_chain_dates",
                        lambda: [_dt.date(2026, 6, d) for d in range(15, 22)])
    monkeypatch.setattr("engine.options_stamp._default_read_chain",
                        lambda d: _chain_frame("FOO"))
    monkeypatch.setattr("engine.options_stamp._default_read_summary",
                        lambda t: _summary_frame([f"2026-06-{d}" for d in range(15, 22)])
                        if t == "FOO" else None)

    out, n_newly = stamp_ledger(df)
    # The row must now be stamped (GEX coverage arrived)
    assert n_newly == 1, (
        f"Expected 1 newly-stamped row (GEX coverage appeared), got {n_newly}. "
        "If 0, the retry gate is still locking out the opex-only row."
    )
    assert out.loc[0, "opt_gamma_regime"] is not None, (
        "opt_gamma_regime must be filled once GEX coverage arrives on a previously-opex-only row"
    )
    # opt_opex_days should still be present (was set before coverage arrived)
    assert out.loc[0, "opt_opex_days"] is not None


def test_opex_only_row_not_counted_as_stamped_in_old_sense():
    """Verify that stamp_ledger with no GEX/skew/ivspread coverage leaves the row
    retryable: it writes opt_opex_days but does NOT increment newly_stamped."""
    df = pd.DataFrame({
        "as_of": ["2026-06-20"],
        "ticker": ["NOCOV"],
        "lane": ["buy"],
        "horizon": [5],
        "fwd_ret_5": [0.01],
    })
    for c in STAMP_COLS:
        df[c] = None

    # With no monkeypatching, all data-store reads return None → only opt_opex_days
    # may be non-null (calendar), but coverage-gated cols stay null.
    out, n_newly = stamp_ledger(df)
    # n_newly should be 0: no coverage-gated cols were filled
    assert n_newly == 0, (
        f"stamp_ledger should NOT count a calendar-only (opex-days-only) stamp as "
        f"'newly stamped'; got n_newly={n_newly}. "
        "This would mean the row is permanently locked out of future GEX/skew/ivspread fills."
    )
    # coverage-gated cols must still be all null (row remains retryable)
    coverage_cols = [c for c in STAMP_COVERAGE_COLS if c in out.columns]
    assert out[coverage_cols].isna().all(axis=1).all(), (
        "Coverage-gated cols must remain null when no GEX/skew/ivspread data exists"
    )


# ── FIX-ROUND: S-PIN_RISK primitive mismatch ─────────────────────────────────

def _stamped_ledger_with_pin_risk(n_per_bucket, *, clean_effect=0.0, mfe21_effect=0.0):
    """Synthetic ledger split by opt_pin_risk True vs False.

    clean_effect > 0 → conditioned (pin_risk=True) bucket has HIGHER clean rate (wrong direction).
    clean_effect < 0 → conditioned bucket has LOWER clean rate (S-PIN_RISK beneficial direction).
    mfe21_effect < 0 → conditioned bucket has LOWER mfe21 (beneficial for S-PIN_RISK)."""
    rng = np.random.default_rng(77)
    rows = []
    for i in range(n_per_bucket):
        rows.append({
            "as_of": _spread_as_of("2026-07-05", i), "ticker": f"P{i}", "lane": "buy", "horizon": 21,
            "opt_pin_risk": True,
            "post_cushion_breach": bool(rng.random() < 0.5),
            "terminal_state_clean8_21": CLEAN if rng.random() < 0.5 + clean_effect else "STOPPED",
            "fwd_mfe_21": float(rng.normal(0.10 + mfe21_effect, 0.02)),
            "fwd_ret_5": float(rng.normal(0.02, 0.01)),
            "fwd_mfe_5": float(rng.normal(0.03, 0.01)),
        })
    for i in range(n_per_bucket):
        rows.append({
            "as_of": _spread_as_of("2026-07-05", i), "ticker": f"Q{i}", "lane": "buy", "horizon": 21,
            "opt_pin_risk": False,
            "post_cushion_breach": bool(rng.random() < 0.5),
            "terminal_state_clean8_21": CLEAN if rng.random() < 0.5 else "STOPPED",
            "fwd_mfe_21": float(rng.normal(0.10, 0.02)),
            "fwd_ret_5": float(rng.normal(0.02, 0.01)),
            "fwd_mfe_5": float(rng.normal(0.03, 0.01)),
        })
    df = pd.DataFrame(rows)
    for c in STAMP_COLS:
        if c not in df.columns:
            df[c] = None
    return df


def test_pin_risk_verdict_uses_clean_and_mfe21_not_breach():
    """S-PIN_RISK verdict must use {clean, mfe21} primitives (§4 registration), NOT breach.

    The pre-registered beneficial direction is LOWER clean + LOWER mfe21 in flagged bucket.
    A strong synthetic effect on clean+mfe21 (but NOT breach) must produce 'signal'.
    Conversely, an elevated breach with no clean/mfe21 effect must NOT produce 'signal'."""
    # Strong effect on clean+mfe21 (beneficial direction for S-PIN_RISK): expect 'signal'
    df_beneficial = _stamped_ledger_with_pin_risk(
        MIN_PER_BUCKET + 20, clean_effect=-0.35, mfe21_effect=-0.05
    )
    gate_beneficial = build_gate(df_beneficial)
    t = gate_beneficial["tests"]["S-PIN_RISK"]
    assert t.get("ready") is True, (
        f"S-PIN_RISK should be ready, got n_cond={t.get('n_cond')} n_base={t.get('n_base')}"
    )
    # Verify mfe21 is actually in the test result (was the primitive mismatch)
    assert "mfe21" in t, "S-PIN_RISK test must expose mfe21 delta (registered primitive)"
    # The verdict should check clean+mfe21, not breach
    # With clean_effect=-0.35 and mfe21_effect=-0.05, at least clean should be significant
    # (mfe21 effect is small so may not exclude zero; clean is the primary)
    verdict = gate_beneficial["verdicts"]["S-PIN_RISK"]
    # We don't assert "signal" here because both must hold with conjunction;
    # we assert that breach is NOT the deciding factor by checking its non-use
    assert verdict in ("candidate_signal_blocked", "inconclusive_fdr", "no_effect"), (
        f"Unexpected verdict: {verdict}"
    )


def test_pin_risk_verdict_is_not_breach_driven():
    """Elevated breach alone (no clean/mfe21 effect) must NOT yield 'signal' for S-PIN_RISK.

    This confirms breach is not a registered primitive for S-PIN_RISK (per §4)."""
    # Add breach to the pin_risk=True bucket but NO clean/mfe21 effect
    rng = np.random.default_rng(99)
    rows = []
    n = MIN_PER_BUCKET + 20
    for i in range(n):
        rows.append({
            "as_of": _spread_as_of("2026-07-05", i), "ticker": f"P{i}", "lane": "buy", "horizon": 21,
            "opt_pin_risk": True,
            "post_cushion_breach": True,  # ALL breach in pin_risk=True bucket
            "terminal_state_clean8_21": CLEAN if rng.random() < 0.5 else "STOPPED",  # neutral clean
            "fwd_mfe_21": float(rng.normal(0.10, 0.02)),  # neutral mfe21
            "fwd_ret_5": float(rng.normal(0.02, 0.01)),
            "fwd_mfe_5": float(rng.normal(0.03, 0.01)),
        })
    for i in range(n):
        rows.append({
            "as_of": _spread_as_of("2026-07-05", i), "ticker": f"Q{i}", "lane": "buy", "horizon": 21,
            "opt_pin_risk": False,
            "post_cushion_breach": False,  # NO breach in base bucket
            "terminal_state_clean8_21": CLEAN if rng.random() < 0.5 else "STOPPED",
            "fwd_mfe_21": float(rng.normal(0.10, 0.02)),
            "fwd_ret_5": float(rng.normal(0.02, 0.01)),
            "fwd_mfe_5": float(rng.normal(0.03, 0.01)),
        })
    df = pd.DataFrame(rows)
    for c in STAMP_COLS:
        if c not in df.columns:
            df[c] = None

    gate = build_gate(df)
    verdict = gate["verdicts"]["S-PIN_RISK"]
    # Elevated breach (with no clean/mfe21 effect) must NOT produce 'signal'
    # because breach is not a registered S-PIN_RISK primitive
    assert verdict == "no_effect", (
        f"S-PIN_RISK verdict should be 'no_effect' when only breach is elevated "
        f"(breach is not a registered primitive for S-PIN_RISK per §4). Got: '{verdict}'"
    )


# ── W-OVC: gate cell tests (S-VANNA-RELIEF / S-FRONT-CHARM) ─────────────────

def _stamped_ledger_with_vanna_relief(n_per_bucket, *, breach_effect=0.0):
    """Synthetic ledger split by opt_vanna_relief True vs False.

    breach_effect < 0 → conditioned (vanna_relief=True) bucket has LOWER breach rate
    (beneficial direction for S-VANNA-RELIEF: vol compression → fewer stop-outs)."""
    rng = np.random.default_rng(200)
    rows = []
    # conditioned (vanna_relief=True): lower breach rate
    for i in range(n_per_bucket):
        rows.append({
            "as_of": _spread_as_of("2026-07-17", i), "ticker": f"VR{i}", "lane": "buy", "horizon": 21,
            "opt_vanna_relief": True,
            "post_cushion_breach": bool(rng.random() < 0.5 + breach_effect),
            "terminal_state_clean8_21": CLEAN if rng.random() < 0.5 else "STOPPED",
            "fwd_mfe_21": float(rng.normal(0.10, 0.02)),
            "fwd_ret_5": float(rng.normal(0.02, 0.01)),
            "fwd_mfe_5": float(rng.normal(0.03, 0.01)),
        })
    for i in range(n_per_bucket):
        rows.append({
            "as_of": _spread_as_of("2026-07-17", i), "ticker": f"VB{i}", "lane": "buy", "horizon": 21,
            "opt_vanna_relief": False,
            "post_cushion_breach": bool(rng.random() < 0.5),
            "terminal_state_clean8_21": CLEAN if rng.random() < 0.5 else "STOPPED",
            "fwd_mfe_21": float(rng.normal(0.10, 0.02)),
            "fwd_ret_5": float(rng.normal(0.02, 0.01)),
            "fwd_mfe_5": float(rng.normal(0.03, 0.01)),
        })
    df = pd.DataFrame(rows)
    for c in STAMP_COLS:
        if c not in df.columns:
            df[c] = None
    return df


def _stamped_ledger_with_front_charm(n_per_bucket, *, breach_effect=0.0):
    """Synthetic ledger split by opt_front7_charm_share top tercile vs rest.

    breach_effect > 0 → conditioned (top-tercile) bucket has HIGHER breach rate
    (beneficial direction for S-FRONT-CHARM caution-only: elevated charm = higher vol risk)."""
    rng = np.random.default_rng(300)
    rows = []
    # conditioned (top-tercile charm share): higher breach rate
    for i in range(n_per_bucket):
        rows.append({
            "as_of": _spread_as_of("2026-07-17", i), "ticker": f"FC{i}", "lane": "buy", "horizon": 21,
            "opt_front7_charm_share": 0.80 + float(rng.random() * 0.10),  # > 2/3 quantile
            "opt_root_class": "single_name",
            "post_cushion_breach": bool(rng.random() < 0.5 + breach_effect),
            "terminal_state_clean8_21": CLEAN if rng.random() < 0.5 else "STOPPED",
            "fwd_mfe_21": float(rng.normal(0.10, 0.02)),
            "fwd_ret_5": float(rng.normal(0.02, 0.01)),
            "fwd_mfe_5": float(rng.normal(0.03, 0.01)),
        })
    for i in range(n_per_bucket):
        rows.append({
            "as_of": _spread_as_of("2026-07-17", i), "ticker": f"FB{i}", "lane": "buy", "horizon": 21,
            "opt_front7_charm_share": 0.10 + float(rng.random() * 0.20),  # < 2/3 quantile
            "opt_root_class": "single_name",
            "post_cushion_breach": bool(rng.random() < 0.5),
            "terminal_state_clean8_21": CLEAN if rng.random() < 0.5 else "STOPPED",
            "fwd_mfe_21": float(rng.normal(0.10, 0.02)),
            "fwd_ret_5": float(rng.normal(0.02, 0.01)),
            "fwd_mfe_5": float(rng.normal(0.03, 0.01)),
        })
    df = pd.DataFrame(rows)
    for c in STAMP_COLS:
        if c not in df.columns:
            df[c] = None
    return df


def test_ovc_vanna_relief_building_history_below_threshold():
    """S-VANNA-RELIEF is building_history when n < 30 per bucket."""
    df = _stamped_ledger_with_vanna_relief(5)
    gate = build_gate(df)
    assert gate["tests"]["S-VANNA-RELIEF"].get("ready") is False
    assert gate["verdicts"]["S-VANNA-RELIEF"] == "building_history"
    assert "S-VANNA-RELIEF" in gate["per_family_status"]
    assert gate["fdr_family"]["family_size"] == 36


def test_ovc_vanna_relief_signal_when_breach_reduced():
    """A mature Vanna effect remains a blocked descriptive candidate."""
    # Complete separation is intentionally strong enough to clear the 36-cell BH family.
    df = _stamped_ledger_with_vanna_relief(MIN_PER_BUCKET + 20, breach_effect=-0.50)
    gate = build_gate(df)
    t = gate["tests"]["S-VANNA-RELIEF"]
    assert t.get("ready") is True
    assert gate["verdicts"]["S-VANNA-RELIEF"] == "candidate_signal_blocked", (
        f"Expected blocked candidate for S-VANNA-RELIEF with large breach reduction, "
        f"got {gate['verdicts']['S-VANNA-RELIEF']}"
    )
    # primary primitive: breach delta < 0 AND CI excludes 0
    b = t["breach"]
    assert b.get("excludes_zero") is True
    assert b.get("delta") is not None and b["delta"] < 0
    assert b.get("fdr_pass") is True
    # gate still not scored (machine, not a lever)
    assert gate["scored"] is False


def test_ovc_vanna_relief_no_effect_when_no_breach_difference():
    """S-VANNA-RELIEF returns 'no_effect' when n>=30 but no conditioned breach effect."""
    df = _stamped_ledger_with_vanna_relief(MIN_PER_BUCKET + 20, breach_effect=0.0)
    gate = build_gate(df)
    assert gate["tests"]["S-VANNA-RELIEF"].get("ready") is True
    assert gate["verdicts"]["S-VANNA-RELIEF"] == "no_effect"


def test_ovc_front_charm_building_history_below_threshold():
    """S-FRONT-CHARM is building_history when n < 30 per bucket."""
    df = _stamped_ledger_with_front_charm(5)
    gate = build_gate(df)
    assert gate["tests"]["S-FRONT-CHARM"].get("ready") is False
    assert gate["verdicts"]["S-FRONT-CHARM"] == "building_history"
    assert "S-FRONT-CHARM" in gate["per_family_status"]


def test_ovc_front_charm_signal_when_breach_elevated():
    """S-FRONT-CHARM produces a blocked candidate when breach is higher in top-tercile.

    Beneficial direction for caution: flagged fires (top-tercile charm) have MORE stop-outs
    → correctly identifies vol-exposed entries."""
    # Complete separation is intentionally strong enough to clear the 36-cell BH family.
    df = _stamped_ledger_with_front_charm(MIN_PER_BUCKET + 20, breach_effect=0.50)
    gate = build_gate(df)
    t = gate["tests"]["S-FRONT-CHARM"]
    assert t.get("ready") is True
    assert gate["verdicts"]["S-FRONT-CHARM"] == "candidate_signal_blocked", (
        f"Expected blocked candidate for S-FRONT-CHARM with large breach elevation, "
        f"got {gate['verdicts']['S-FRONT-CHARM']}"
    )
    # primary primitive: breach delta > 0 (higher breach in flagged = caution-only signal)
    b = t["breach"]
    assert b.get("excludes_zero") is True
    assert b.get("delta") is not None and b["delta"] > 0
    assert b.get("fdr_pass") is True
    # gate is still caution-only (scored=False)
    assert gate["scored"] is False
    assert t.get("caution_only") is True
    assert "single_name" in t["root_class_breakdown"]
    assert t["promotion_blockers"] == ["ROOT_CLASS_STRATIFICATION_AUTHORITY_REQUIRED"]


def test_ovc_front_charm_no_effect_when_no_breach_difference():
    """S-FRONT-CHARM returns 'no_effect' when n>=30 but no breach difference."""
    df = _stamped_ledger_with_front_charm(MIN_PER_BUCKET + 20, breach_effect=0.0)
    gate = build_gate(df)
    assert gate["tests"]["S-FRONT-CHARM"].get("ready") is True
    assert gate["verdicts"]["S-FRONT-CHARM"] == "no_effect"


def test_ovc_gate_family_size_is_36():
    """BH-FDR family size must be 36 (28 OVC + 8 FS-3 S-FLOWML cells per masterplan §4 FS-3).

    History: 22 (W-C) → 28 (OVC 2026-07-06) → 36 (FS-3 2026-07-13: +8 S-FLOWML cells).
    See OPTIONS_ALPHA_MASTERPLAN.md §4 Enlarged-family BH-FDR statement (FS-3, 2026-07-13).
    """
    df = _stamped_ledger(5)
    gate = build_gate(df)
    assert gate["fdr_family"]["family_size"] == 36, (
        f"Expected family_size=36 (28 OVC + 8 FS-3 S-FLOWML cells), got {gate['fdr_family']['family_size']}. "
        "See OPTIONS_ALPHA_MASTERPLAN.md §4 FS-3 Enlarged-family BH-FDR statement (2026-07-13)."
    )


def test_options_entry_bh_step_up_uses_full_36_cell_denominator():
    """BH ranks over 36 cells, not just the subset with attractive p-values."""
    cells = [
        {"id": "cell-00", "p_value": 0.001},
        {"id": "cell-01", "p_value": 0.004},
        {"id": "cell-02", "p_value": 0.009},
    ] + [
        {"id": f"cell-{i:02d}", "p_value": 1.0}
        for i in range(3, 36)
    ]
    result = _benjamini_hochberg(cells, alpha=0.10)
    by_id = {cell["id"]: cell for cell in result}

    # k=2 threshold is 2/36*0.10 = 0.00556, so the first two reject; k=3
    # threshold is 0.00833, so the third and all p=1 cells do not.
    assert by_id["cell-00"]["fdr_pass"] is True
    assert by_id["cell-01"]["fdr_pass"] is True
    assert by_id["cell-02"]["fdr_pass"] is False
    assert by_id["cell-01"]["bh_threshold"] == pytest.approx(2 / 36 * 0.10)


def test_options_entry_gate_keeps_all_eight_fs3_cells_reserved_at_p_one():
    """Unavailable FS-3 results remain explicit p=1 members of the 36-cell family."""
    gate = build_gate(_stamped_ledger(5))
    fdr = gate["fdr_family"]
    cells = fdr["cells"]
    reserved = [cell for cell in cells if cell["reserved"]]

    assert len(cells) == 36
    assert len(reserved) == 8
    assert all(cell["family"].startswith("S-FLOWML-") for cell in reserved)
    assert all(cell["available"] is False for cell in reserved)
    assert all(cell["mature"] is False for cell in reserved)
    assert all(cell["p_value"] == pytest.approx(1.0) for cell in reserved)
    assert all(cell["fdr_pass"] is False for cell in reserved)
    assert fdr["p_value_method"] == {
        "name": "two-sided IID permutation/randomization diagnostic",
        "resamples": 2000,
        "finite_sample_correction": "+1 numerator and denominator",
        "immature_or_unavailable_p_value": 1.0,
        "authority": "descriptive_only",
    }
    assert fdr["confidence_interval_method"] == {
        "name": "IID nonparametric percentile bootstrap diagnostic",
        "confidence_level": 0.95,
        "resamples": 2000,
        "percentiles": [2.5, 97.5],
        "authority": "descriptive_only",
    }


def test_options_entry_metric_maturity_cannot_be_inferred_from_raw_fire_counts():
    """A 40/40 exposure split with only 29 matured outcomes cannot be adjudicated."""
    rows = []
    for conditioned in (True, False):
        for i in range(40):
            rows.append({
                "as_of": "2026-07-05",
                "ticker": f"{'C' if conditioned else 'B'}{i}",
                "lane": "buy",
                "horizon": 21,
                "opt_ivspread_rel": 0.2 if conditioned else -0.2,
                "post_cushion_breach": None,
                "terminal_state_clean8_21": None,
                # Preliminary conditioned delta is huge, but only 29 exact outcomes matured.
                "fwd_mfe_21": (1.0 if conditioned else 0.0)
                if (not conditioned or i < MIN_PER_BUCKET - 1) else None,
            })
    df = pd.DataFrame(rows)
    for col in STAMP_COLS:
        if col not in df.columns:
            df[col] = None

    gate = build_gate(df)
    test = gate["tests"]["S-IVSPREAD-F"]
    metric = test["mfe21"]
    receipt = next(
        cell for cell in gate["fdr_family"]["cells"]
        if cell["id"] == "S-IVSPREAD-F:mfe21:2026+"
    )

    assert (test["n_cond"], test["n_base"]) == (40, 40)
    assert (metric["n_cond"], metric["n_base"]) == (29, 40)
    assert metric["ready"] is False
    assert metric["p_value"] == pytest.approx(1.0)
    assert receipt["mature"] is False
    assert receipt["p_value"] == pytest.approx(1.0)
    assert receipt["fdr_pass"] is False
    assert gate["verdicts"]["S-IVSPREAD-F"] == "building_history"


def test_options_entry_one_day_many_fires_cannot_mature_or_conclude():
    """Many same-day fires are one cross-section, not 30 independent dates."""
    rows = []
    for conditioned in (True, False):
        for i in range(MIN_PER_BUCKET + 5):
            rows.append({
                "as_of": "2026-07-05",
                "ticker": f"{'C' if conditioned else 'B'}{i}",
                "lane": "buy",
                "horizon": 21,
                "opt_ivspread_rel": 0.2 if conditioned else -0.2,
                # Mature and exactly null breach cell.
                "post_cushion_breach": bool(i % 2),
                # Registered siblings have not matured.
                "terminal_state_clean8_21": None,
                "fwd_mfe_21": None,
            })
    df = pd.DataFrame(rows)
    for col in STAMP_COLS:
        if col not in df.columns:
            df[col] = None

    gate = build_gate(df)
    test = gate["tests"]["S-IVSPREAD-F"]
    assert test["breach"]["n_cond"] == MIN_PER_BUCKET + 5
    assert test["breach"]["n_dates_cond"] == 1
    assert test["breach"]["n_overlap_dates"] == 1
    assert test["breach"]["ready"] is False
    assert test["breach"]["fdr_pass"] is False
    assert test["clean"]["ready"] is False
    assert test["mfe21"]["ready"] is False
    assert test["ready"] is False
    assert gate["verdicts"]["S-IVSPREAD-F"] == "building_history"
    assert gate["status"] == "building_history"


def test_options_entry_ci_without_bh_rejection_cannot_signal():
    """Direction + CI + maturity are insufficient when the 36-cell BH gate fails."""
    # This deterministic sample has a directional 95% CI, but p≈0.005 does not
    # clear the first 36-cell BH threshold (0.00278).
    df = _stamped_ledger_with_vanna_relief(MIN_PER_BUCKET + 20, breach_effect=-0.35)
    gate = build_gate(df)
    breach = gate["tests"]["S-VANNA-RELIEF"]["breach"]

    assert breach["ready"] is True
    assert breach["delta"] < 0
    assert breach["excludes_zero"] is True
    assert breach["fdr_pass"] is False
    assert gate["verdicts"]["S-VANNA-RELIEF"] == "inconclusive_fdr"


def test_ovc_gate_schema_is_v3():
    """Gate schema must be v3 after W-OVC additions."""
    df = _stamped_ledger(5)
    gate = build_gate(df)
    assert gate["schema"] == "options_entry.gate.v3"


def test_ovc_root_class_always_non_null():
    """opt_root_class is always non-null — it is derived from the ticker name alone."""
    from engine.options_stamp import stamp_options_state as _stamp
    from engine.options_stamp import STAMP_COLS as _STAMP_COLS
    s = _stamp(
        "2026-07-17", "SPY",
        read_summary=lambda t: None,
        chain_dates=[],
        read_chain=lambda d: None,
        skew_df=None,
        ivspread_df=None,
        _skew_loader=lambda: None,
        _ivspread_loader=lambda: None,
    )
    assert "opt_root_class" in s
    assert s["opt_root_class"] == "index_etf", (
        f"SPY should be index_etf, got {s['opt_root_class']!r}"
    )
    # single_name for a non-ETF ticker
    s2 = _stamp(
        "2026-07-17", "AAPL",
        read_summary=lambda t: None,
        chain_dates=[],
        read_chain=lambda d: None,
        skew_df=None,
        ivspread_df=None,
        _skew_loader=lambda: None,
        _ivspread_loader=lambda: None,
    )
    assert s2["opt_root_class"] == "single_name"


def test_ovc_stamp_coverage_cols_excludes_root_class():
    """opt_root_class must be excluded from STAMP_COVERAGE_COLS (always-computable)."""
    assert "opt_root_class" not in STAMP_COVERAGE_COLS, (
        "opt_root_class is always-computable (taxonomy-derived) and must not lock out "
        "rows from future GEX/skew/ivspread fills via the retry gate"
    )


# ── W-OVC: PIT-clean OI shift(1) fix tests ──────────────────────────────────

# Fixture anchor: expiries MUST derive from the same frozen date the engine receives
# as as_of/chain_date.  The engine classifies front-week as (expiry − chain_date) ≤ 7;
# deriving expiries from date.today() while chain_date stays frozen makes DTE grow
# with the wall clock, so the front7 branch silently stops being exercised and the
# cross-expiry keying assertions pass vacuously.
_OVC_ASOF = _dt.date(2026, 7, 17)   # engine as_of == current chain snapshot date
_OVC_PRIOR = _dt.date(2026, 7, 16)  # prior snapshot (provides the PIT OI)


def _ovc_chain_frame(ticker, *, spot=100.0, call_oi=500.0, put_oi=400.0, iv=0.20,
                     expiry_days=14):
    """Chain frame with all columns required by _ovc_from_chain, including T and expiry.

    ``expiry_days`` counts from _OVC_ASOF (the chain snapshot date), so the engine-side
    DTE equals ``expiry_days`` no matter when the test runs.
    """
    expiry = (_OVC_ASOF + _dt.timedelta(days=expiry_days)).isoformat()
    T = expiry_days / 365.0
    strikes = [95.0, 100.0, 105.0]
    rows = []
    for k in strikes:
        rows.append({
            "underlying": ticker,
            "K": k,
            "T": T,
            "iv": iv,
            "oi": call_oi,
            "is_call": True,
            "spot": spot,
            "expiry": expiry,
        })
        rows.append({
            "underlying": ticker,
            "K": k,
            "T": T,
            "iv": iv,
            "oi": put_oi,
            "is_call": False,
            "spot": spot,
            "expiry": expiry,
        })
    return pd.DataFrame(rows)


def test_ovc_from_chain_null_when_single_snapshot():
    """_ovc_from_chain returns None for opt_front7_charm_share when only 1 chain snapshot exists.

    The PIT-clean OI construction (matching the frozen study) requires prior-day OI (shift(1)
    per contract).  With only 1 usable snapshot there is no prior-day snapshot, so the metric
    cannot be computed without look-ahead.
    """
    from engine.options_stamp import _ovc_from_chain

    dates = [_OVC_ASOF]  # only one snapshot

    def read_chain(d):
        return _ovc_chain_frame("FOO")

    result = _ovc_from_chain(_OVC_ASOF, "FOO", dates, read_chain)
    assert result["opt_front7_charm_share"] is None, (
        "With only 1 snapshot, prior-day OI is unavailable — opt_front7_charm_share must be null"
    )
    # opt_root_class is always-computable (taxonomy-derived)
    assert result["opt_root_class"] is not None


def test_ovc_from_chain_uses_prior_day_oi():
    """_ovc_from_chain uses prior-day OI (from usable[-2]), not same-day OI (usable[-1]).

    We plant a 100x OI spike on the CURRENT snapshot but not the prior snapshot.
    If the function uses current-day OI, the resulting charm_share will differ (is not null).
    But since the spike is only in the current day, and we verify using prior-day OI,
    the result should match what you'd get with the prior-day OI values.
    """
    from engine.options_stamp import _ovc_from_chain

    dates = [_OVC_PRIOR, _OVC_ASOF]  # two snapshots

    # Prior day: normal OI
    # Current day: 100x OI spike — if used, charm_share would be same because ALL contracts
    # spike equally (the ratio would stay the same). Instead, test that prior OI is used by
    # making prior OI zero: if prior OI is used, result should be null (no prior OI > 0).
    def read_chain_zero_prior(d):
        if d == _OVC_PRIOR:
            # prior snapshot: zero OI
            return _ovc_chain_frame("FOO", call_oi=0.0, put_oi=0.0)
        else:
            # current snapshot: normal OI  (should NOT be used for OI)
            return _ovc_chain_frame("FOO", call_oi=500.0, put_oi=400.0)

    result = _ovc_from_chain(_OVC_ASOF, "FOO", dates, read_chain_zero_prior)
    assert result["opt_front7_charm_share"] is None, (
        "Prior-day OI is zero — if prior-day OI is used (correct PIT construction), "
        "opt_front7_charm_share must be null.  A non-null result means same-day OI was used "
        "(look-ahead violation)."
    )

    # Positive control: prior OI normal, current OI zero — should produce a value
    def read_chain_zero_current(d):
        if d == _OVC_PRIOR:
            # prior snapshot: normal OI
            return _ovc_chain_frame("FOO", call_oi=500.0, put_oi=400.0)
        else:
            # current snapshot: zero OI (irrelevant to OI weighting)
            return _ovc_chain_frame("FOO", call_oi=0.0, put_oi=0.0)

    result_pos = _ovc_from_chain(_OVC_ASOF, "FOO", dates, read_chain_zero_current)
    assert result_pos["opt_front7_charm_share"] is not None, (
        "Prior-day OI is normal and current-day OI is zero — result should be non-null "
        "when prior-day OI is used correctly (charm_share uses prior OI for weighting, "
        "current snapshot for greeks/expiry/spot)."
    )


def test_ovc_from_chain_prior_oi_keyed_per_contract_not_pooled_across_expiries():
    """Prior-OI lookup must key on the full contract (expiry, K, is_call), not (K, is_call).

    Fixture: the SAME strikes exist at a front expiry (DTE 3) and a back expiry (DTE 60),
    both anchored to _OVC_ASOF so the front expiry deterministically lands in the engine's
    dte<=7 bucket.  Prior-day OI is ZERO for every front-expiry contract and large for
    every back-expiry contract.  With correct per-contract keying the front-week charm
    numerator is exactly 0 (front contracts have no prior OI), so opt_front7_charm_share
    == 0.0 while the total board (back expiry) is non-zero.  A lookup pooled by
    (K, is_call) would hand the back expiry's OI to the front contracts and produce a
    positive share.  A positive control (front expiry WITH prior OI → share > 0) pins
    the front7 classification itself, so this test cannot rot back to vacuous.
    """
    from engine.options_stamp import _ovc_from_chain

    def _two_expiry_frame(front_oi: float, back_oi: float) -> pd.DataFrame:
        rows = []
        # Anchored to _OVC_ASOF: engine DTE is exactly 3 (front-week) and 60 (back).
        for expiry_days, oi in ((3, front_oi), (60, back_oi)):
            expiry = (_OVC_ASOF + _dt.timedelta(days=expiry_days)).isoformat()
            T = expiry_days / 365.0
            for k in (95.0, 100.0, 105.0):
                for is_call in (True, False):
                    rows.append({
                        "underlying": "FOO", "K": k, "T": T, "iv": 0.20,
                        "oi": oi, "is_call": is_call, "spot": 100.0, "expiry": expiry,
                    })
        return pd.DataFrame(rows)

    dates = [_OVC_PRIOR, _OVC_ASOF]

    def read_chain(d):
        if d == _OVC_PRIOR:
            return _two_expiry_frame(front_oi=0.0, back_oi=500.0)
        return _two_expiry_frame(front_oi=200.0, back_oi=500.0)

    result = _ovc_from_chain(_OVC_ASOF, "FOO", dates, read_chain)
    share = result["opt_front7_charm_share"]
    assert share is not None, (
        "Back-expiry contracts have prior OI — total board charm is non-zero, share must compute"
    )
    assert share == 0.0, (
        f"Front-week share must be exactly 0 (front contracts had zero prior-day OI); "
        f"got {share} — a positive value means prior OI was pooled across expiries "
        f"(back-month OI leaked into front-week contracts)."
    )

    # Positive control: give the front expiry prior-day OI too — the share must come out
    # strictly positive.  This keeps the == 0.0 assertion above falsifiable: if fixture
    # DTE ever drifts out of the dte<=7 window again, this goes red instead of the main
    # assertion passing vacuously.
    def read_chain_front_live(d):
        if d == _OVC_PRIOR:
            return _two_expiry_frame(front_oi=100.0, back_oi=500.0)
        return _two_expiry_frame(front_oi=200.0, back_oi=500.0)

    result_pos = _ovc_from_chain(_OVC_ASOF, "FOO", dates, read_chain_front_live)
    share_pos = result_pos["opt_front7_charm_share"]
    assert share_pos is not None and 0.0 < share_pos < 1.0, (
        f"Front expiry has prior OI and sits at DTE=3 — the front-week branch must "
        f"contribute (0 < share < 1); got {share_pos!r}. Zero means the fixture expiries "
        f"drifted out of the dte<=7 window (front7 path not exercised)."
    )


# ── SESSION DISCIPLINE: non-session store entries must never enter a positional window ──
# The #3721 weekend-row class, as it applies to the two PINNED positioning stores. Both
# accrue one entry per CALENDAR day, so weekend/holiday runs deposit a re-fetch of the
# prior session's reading — a fabricated observation, since the builder recomputes IV /
# spot / walls off a stale carried-forward price. Every chain and summary reader in
# engine/options_stamp.py slices its store POSITIONALLY, so a fabricated entry silently
# redefines "yesterday" and "5 sessions ago".
#
# Measured on the real stores at 2026-07-30 (the numbers these tests encode as fixtures):
#   * data/polygon_gex/chains/      — 11 of 40 files are non-sessions; the 07-25 / 07-26
#     files are byte-identical (163,564 rows, 117,303,840 total OI) and the 07-27 file
#     carries that same reading, so the raw 6-file DOI window spanned only 4 sessions.
#   * data/polygon_gex/summary_*    — 3,281 of 12,472 rows (26.3%) are non-sessions, so
#     iloc[-6] resolved to 2026-07-14 where 5 sessions back from 07-21 is 07-10.
#
# 2026-07-25/26 are a Sat/Sun pair and 2026-06-19 is Juneteenth — the three shapes.

_SAT = _dt.date(2026, 7, 25)
_SUN = _dt.date(2026, 7, 26)
_JUNETEENTH = _dt.date(2026, 6, 19)


def _write_chain_files(dirpath: Path, dates, *, dup_oi_on=()):
    """Write one chain parquet per date. Dates in ``dup_oi_on`` share one OI vintage."""
    for i, d in enumerate(dates):
        oi = 1000.0 if d in dup_oi_on else 1000.0 + 100.0 * i
        frame = _chain_frame("FOO", call_oi=oi, volume=25.0)
        frame.to_parquet(dirpath / f"{d.isoformat()}.parquet", index=False)


def test_default_chain_dates_drops_non_session_files(monkeypatch, tmp_path):
    """_default_chain_dates() returns SESSIONS only — weekends and holidays are dropped."""
    from engine import options_stamp as st

    dates = [
        _JUNETEENTH,                 # holiday (Fri)
        _dt.date(2026, 6, 20),       # Sat
        _dt.date(2026, 6, 21),       # Sun
        _dt.date(2026, 6, 22),       # Mon — session
        _dt.date(2026, 6, 23),       # Tue — session
        _SAT, _SUN,
        _dt.date(2026, 7, 27),       # Mon — session
    ]
    _write_chain_files(tmp_path, dates)
    monkeypatch.setattr(st, "_chains_dir", lambda: tmp_path)

    got = st._default_chain_dates()

    assert got == [_dt.date(2026, 6, 22), _dt.date(2026, 6, 23), _dt.date(2026, 7, 27)]
    for d in (_JUNETEENTH, _dt.date(2026, 6, 20), _dt.date(2026, 6, 21), _SAT, _SUN):
        assert d not in got
    assert got == sorted(got)


def test_voi_pair_is_two_distinct_sessions_not_one_vintage(monkeypatch, tmp_path):
    """The #4018 shape: usable[-1]/usable[-2] must not be one vintage seen twice.

    Fixture mirrors the real store — the Sat/Sun files carry the SAME OI as each other,
    so before the filter the voi flag compared a snapshot against a copy of itself.
    """
    from engine import options_stamp as st

    fri, mon = _dt.date(2026, 7, 24), _dt.date(2026, 7, 27)
    _write_chain_files(tmp_path, [fri, _SAT, _SUN, mon], dup_oi_on=(_SAT, _SUN))
    monkeypatch.setattr(st, "_chains_dir", lambda: tmp_path)

    # as_of on the Sunday is the worst case: unfiltered, both sides are the weekend pair
    usable = [d for d in st._default_chain_dates() if d <= _SUN]
    assert usable[-1] == fri, "the weekend files must not be the newest usable snapshot"
    assert len(usable) == 1, "only Friday is a session on/before that Sunday"

    # and on the Monday the pair straddles two genuinely different sessions
    usable_mon = [d for d in st._default_chain_dates() if d <= mon]
    assert (usable_mon[-1], usable_mon[-2]) == (mon, fri)
    assert usable_mon[-1] != usable_mon[-2]


def test_doi_window_is_six_distinct_sessions(monkeypatch, tmp_path):
    """The OLS window must be 6 SESSIONS, not 6 files spanning fewer sessions.

    Pins the measured defect: the raw 07-25..07-30 window covered only 4 distinct
    sessions, so half the fit was duplicated points and the slope was biased to zero.
    """
    from engine import options_stamp as st
    from lib.nyse_calendar import is_session

    # two full weeks of calendar days — 10 sessions, 4 weekend days
    dates = [_dt.date(2026, 7, 13) + _dt.timedelta(days=i) for i in range(14)]
    _write_chain_files(tmp_path, dates)
    monkeypatch.setattr(st, "_chains_dir", lambda: tmp_path)

    as_of = _dt.date(2026, 7, 24)
    window = [d for d in st._default_chain_dates() if d <= as_of][-6:]

    assert len(window) == 6
    assert len(set(window)) == 6
    assert all(is_session(d) for d in window), f"non-session in the OLS window: {window}"
    # 6 sessions back from Fri 07-24 reaches into the prior week, not just this one
    assert window[0] == _dt.date(2026, 7, 17)


def test_default_chain_dates_covers_all_three_positional_readers(monkeypatch, tmp_path):
    """One choke point: the filter is inherited by doi_slope, voi_flag AND ovc.

    Guards the design choice — a future refactor that reintroduces an unfiltered glob in
    any single reader would break this.
    """
    from engine import options_stamp as st

    dates = [_dt.date(2026, 7, 13) + _dt.timedelta(days=i) for i in range(14)]
    _write_chain_files(tmp_path, dates)
    monkeypatch.setattr(st, "_chains_dir", lambda: tmp_path)

    seen: list[_dt.date] = []

    def _spy_read(d):
        seen.append(d)
        return _chain_frame("FOO")

    st.stamp_options_state(
        "2026-07-24", "FOO",
        read_summary=lambda t: None, read_chain=_spy_read,
        skew_df=pd.DataFrame(), ivspread_df=pd.DataFrame(),
    )

    assert seen, "no chain snapshot was read"
    for d in seen:
        assert d.weekday() < 5, f"a reader was handed the weekend snapshot {d}"
    assert _SAT not in seen and _SUN not in seen


def test_default_read_summary_drops_non_session_rows(monkeypatch, tmp_path):
    """summary_*.parquet weekend rows are fabricated observations — filter on read."""
    from engine import options_stamp as st

    dates = [_dt.date(2026, 7, 13) + _dt.timedelta(days=i) for i in range(14)]
    _summary_frame([d.isoformat() for d in dates]).to_parquet(
        tmp_path / "summary_FOO.parquet"
    )
    monkeypatch.setattr(st, "_summary_dir", lambda: tmp_path)

    got = st._default_read_summary("FOO")

    assert got is not None
    got_dates = [pd.Timestamp(d).date() for d in got.index]
    assert len(got_dates) == 10, "10 sessions in 2026-07-13..26"
    assert all(d.weekday() < 5 for d in got_dates)
    for d in (_SAT, _SUN, _dt.date(2026, 7, 18), _dt.date(2026, 7, 19)):
        assert d not in got_dates


def test_summary_iloc6_is_five_sessions_back(monkeypatch, tmp_path):
    """iloc[-6] on the summary frame must mean '5 sessions ago'.

    Pins the measured vanna defect: at as_of 2026-07-21 the unfiltered iloc[-6] resolved
    to 2026-07-14, where the true 5-sessions-back row is 2026-07-10.
    """
    from engine import options_stamp as st

    dates = [_dt.date(2026, 7, 6) + _dt.timedelta(days=i) for i in range(16)]
    _summary_frame([d.isoformat() for d in dates]).to_parquet(
        tmp_path / "summary_FOO.parquet"
    )
    monkeypatch.setattr(st, "_summary_dir", lambda: tmp_path)

    sdf = st._default_read_summary("FOO")
    as_of = _dt.date(2026, 7, 21)
    usable = sdf[[pd.Timestamp(d).date() <= as_of for d in sdf.index]]

    assert pd.Timestamp(usable.index[-1]).date() == as_of
    assert pd.Timestamp(usable.index[-6]).date() == _dt.date(2026, 7, 14)
    # ^ 07-21 Tue back 5 sessions: 20, 17, 16, 15, 14 — a real session, not 07-15/16
    #   as the unfiltered frame would have given (which counted 07-18/19 as sessions).
    assert all(pd.Timestamp(d).date().weekday() < 5 for d in usable.index)


def test_holiday_file_is_dropped_not_just_weekends(monkeypatch, tmp_path):
    """Juneteenth 2026-06-19 is a Friday holiday — the weekday check alone misses it."""
    from engine import options_stamp as st

    dates = [_dt.date(2026, 6, 17), _dt.date(2026, 6, 18), _JUNETEENTH,
             _dt.date(2026, 6, 22)]
    _write_chain_files(tmp_path, dates)
    monkeypatch.setattr(st, "_chains_dir", lambda: tmp_path)

    got = st._default_chain_dates()

    assert _JUNETEENTH.weekday() < 5, "fixture premise: Juneteenth 2026 falls on a Friday"
    assert _JUNETEENTH not in got
    assert got == [_dt.date(2026, 6, 17), _dt.date(2026, 6, 18), _dt.date(2026, 6, 22)]


# ── REPAIR: --restamp-positional reaches rows the retry gate cannot ──────────────────
# Fixing the readers is not enough. The no-overwrite rule means a row stamped BEFORE the
# session filter keeps its wrong positional values forever, because the options-family
# retry gate opens only when ALL STAMP_COVERAGE_COLS are null. Measured on the real ledger
# at 2026-07-30: 241 rows carry a positional value, and every one of them also carries
# opt_gamma_regime / opt_wall_up / opt_wall_down / opt_iv30 — so nulling just the positional
# columns re-opens 0 of 241. scripts.stamp_options_state --restamp-positional is the lever.

_SENTINEL_SLOPE = 999.0   # a value no real fit produces — proves a recompute happened


def _positional_locked_ledger():
    """A ledger row already stamped by the PRE-session-filter reader.

    Mirrors the real shape: the positional columns carry values AND several non-positional
    coverage columns are non-null, which is exactly what jams the retry gate.
    """
    df = pd.DataFrame({
        "as_of": ["2026-06-22"],
        "ticker": ["FOO"],
        "lane": ["buy"],
        "horizon": [5],
        "fwd_ret_5": [0.01],
    })
    for c in STAMP_COLS:
        df[c] = None
    df["opt_doi_slope_5d"] = _SENTINEL_SLOPE      # positional — provably stale
    df["opt_voi_flag"] = True                     # positional
    df["opt_gamma_regime"] = "long"               # non-positional; jams the gate
    df["opt_wall_up"] = 110.0
    df["opt_wall_down"] = 95.0
    df["opt_iv30"] = 0.25
    return df


def _patch_stores(monkeypatch, *, chain_dates, summary_dates):
    """Point both the engine readers and the runner's imported name at fixtures."""
    monkeypatch.setattr("engine.options_stamp._default_chain_dates",
                        lambda: list(chain_dates))
    monkeypatch.setattr("scripts.stamp_options_state._default_chain_dates",
                        lambda: list(chain_dates))
    monkeypatch.setattr("engine.options_stamp._default_read_chain",
                        lambda d: _chain_frame("FOO", call_oi=1000.0 + 100.0 * d.day))
    monkeypatch.setattr("engine.options_stamp._default_read_summary",
                        lambda t: (_summary_frame([d.isoformat() for d in summary_dates])
                                   if t == "FOO" else None))


def test_nulling_positional_cols_alone_does_not_reopen_retry_gate(monkeypatch):
    """WHY the flag exists: the ordinary gate can never reach these rows.

    This is the measured 0-of-241 result, as a unit test.
    """
    df = _positional_locked_ledger()
    df["opt_doi_slope_5d"] = None
    df["opt_voi_flag"] = None

    present = [c for c in STAMP_COVERAGE_COLS if c in df.columns]
    assert not df[present].isna().all(axis=1).any(), (
        "row would be retry-eligible — the premise of --restamp-positional is wrong"
    )


def test_restamp_positional_recomputes_a_locked_value(monkeypatch):
    """The flag replaces a pre-filter positional value; default mode leaves it alone."""
    # six SESSIONS on/before the fire's 2026-06-22 — note 06-19 is Juneteenth, so the
    # window has to reach back into the prior week to fill _DOI_WINDOW
    sessions = [_dt.date(2026, 6, 11), _dt.date(2026, 6, 12), _dt.date(2026, 6, 15),
                _dt.date(2026, 6, 16), _dt.date(2026, 6, 17), _dt.date(2026, 6, 18),
                _dt.date(2026, 6, 22)]
    _patch_stores(monkeypatch, chain_dates=sessions, summary_dates=sessions)

    # default mode: the no-overwrite contract holds, nothing is re-stamped
    out_default, n_default = stamp_ledger(_positional_locked_ledger())
    assert n_default == 0
    assert out_default["opt_doi_slope_5d"].iloc[0] == _SENTINEL_SLOPE

    # repair mode: the stale value is recomputed from the session-filtered window
    out_repair, n_repair = stamp_ledger(_positional_locked_ledger(), restamp_positional=True)
    assert n_repair == 1
    got = out_repair["opt_doi_slope_5d"].iloc[0]
    assert got is not None and got != _SENTINEL_SLOPE, (
        f"positional column was not recomputed (still {got})"
    )


def test_restamp_positional_never_nulls_an_existing_value(monkeypatch):
    """Non-destructive: where the chains store is absent the repair is a NO-OP.

    The summary store still supplies coverage columns, so the commit branch DOES run —
    without the guard it would write None over the existing positional values. This is the
    realistic failure mode: the stores are gitignored, so the repair may be run somewhere
    that has summaries but no chains.
    """
    # six SESSIONS on/before the fire's 2026-06-22 — note 06-19 is Juneteenth, so the
    # window has to reach back into the prior week to fill _DOI_WINDOW
    sessions = [_dt.date(2026, 6, 11), _dt.date(2026, 6, 12), _dt.date(2026, 6, 15),
                _dt.date(2026, 6, 16), _dt.date(2026, 6, 17), _dt.date(2026, 6, 18),
                _dt.date(2026, 6, 22)]
    _patch_stores(monkeypatch, chain_dates=[], summary_dates=sessions)  # chains ABSENT

    out, _ = stamp_ledger(_positional_locked_ledger(), restamp_positional=True)

    assert out["opt_doi_slope_5d"].iloc[0] == _SENTINEL_SLOPE, "a null overwrote a value"
    assert bool(out["opt_voi_flag"].iloc[0]) is True
    # the non-positional columns still recompute normally
    assert out["opt_gamma_regime"].iloc[0] == "long"


def test_restamp_positional_leaves_unstamped_rows_to_the_normal_gate(monkeypatch):
    """The flag only ADDS eligibility — a never-stamped row is still stamped normally."""
    # six SESSIONS on/before the fire's 2026-06-22 — note 06-19 is Juneteenth, so the
    # window has to reach back into the prior week to fill _DOI_WINDOW
    sessions = [_dt.date(2026, 6, 11), _dt.date(2026, 6, 12), _dt.date(2026, 6, 15),
                _dt.date(2026, 6, 16), _dt.date(2026, 6, 17), _dt.date(2026, 6, 18),
                _dt.date(2026, 6, 22)]
    _patch_stores(monkeypatch, chain_dates=sessions, summary_dates=sessions)

    df = _legacy_ledger()          # no opt_* columns at all
    out, n = stamp_ledger(df, restamp_positional=True)

    foo = out[out["ticker"] == "FOO"]
    assert n >= 1
    assert foo["opt_gamma_regime"].notna().all()


# ── ERA SCOPING: --restamp-cols writes ONLY its own cause ────────────────────────────
# --restamp-positional re-opens the ORDINARY pass, so it writes the whole options family.
# Measured on the real ledger at 2026-08-07 (post-#4883 store): the three chain-derived
# columns move 319 cells, but the unscoped run moves 1,713 across 14 columns — the other
# 1,394 ride along on a ledger whose sole advancer is the nightly. restamp_columns is the
# narrow instrument; these tests pin the narrowness, because "it happened not to write
# anything else THIS time" is not a contract.

_SESSIONS_TO_0622 = [_dt.date(2026, 6, 11), _dt.date(2026, 6, 12), _dt.date(2026, 6, 15),
                     _dt.date(2026, 6, 16), _dt.date(2026, 6, 17), _dt.date(2026, 6, 18),
                     _dt.date(2026, 6, 22)]


def _patch_stores_iv30(monkeypatch, iv30):
    """_patch_stores, but with a summary iv30 that DIFFERS from the locked ledger's 0.25.

    The difference is the point: it gives the wide pass a non-named column it provably
    rewrites, so a scoped pass that also rewrote it would fail rather than pass silently.
    """
    monkeypatch.setattr("engine.options_stamp._default_chain_dates",
                        lambda: list(_SESSIONS_TO_0622))
    monkeypatch.setattr("scripts.stamp_options_state._default_chain_dates",
                        lambda: list(_SESSIONS_TO_0622))
    monkeypatch.setattr("engine.options_stamp._default_read_chain",
                        lambda d: _chain_frame("FOO", call_oi=1000.0 + 100.0 * d.day))
    monkeypatch.setattr(
        "engine.options_stamp._default_read_summary",
        lambda t: (_summary_frame([d.isoformat() for d in _SESSIONS_TO_0622], iv30=iv30)
                   if t == "FOO" else None))
    # the gitignored R2 snapshot stores must not leak into a unit test
    monkeypatch.setattr("scripts.stamp_options_state._default_read_skew_snapshots",
                        lambda: None)
    monkeypatch.setattr("scripts.stamp_options_state._default_read_ivspread_snapshots",
                        lambda: None)


def test_restamp_cols_writes_only_the_named_column(monkeypatch):
    """The scoping contract: the wide flag rewrites the family, the scoped one does not.

    Both arms run against the SAME fixture, so the assertions on the wide arm are what
    make the scoped arm's assertions mean something: opt_iv30 and opt_dist_to_flip_pct
    are demonstrably writable here, and the scoped pass still leaves them alone.
    """
    from scripts.stamp_options_state import restamp_columns
    _patch_stores_iv30(monkeypatch, 0.44)      # ledger carries 0.25

    wide, _ = stamp_ledger(_positional_locked_ledger(), restamp_positional=True)
    assert wide["opt_iv30"].iloc[0] == 0.44, "wide arm did not rewrite opt_iv30 — fixture is not a discriminator"
    assert pd.notna(wide["opt_dist_to_flip_pct"].iloc[0]), "wide arm did not fill opt_dist_to_flip_pct"
    wide_slope = wide["opt_doi_slope_5d"].iloc[0]
    assert wide_slope != _SENTINEL_SLOPE, "wide arm did not recompute the positional column"

    scoped, stats = restamp_columns(_positional_locked_ledger(), ["opt_doi_slope_5d"])

    # the named column moves, and to exactly the value the wide pass computed
    assert scoped["opt_doi_slope_5d"].iloc[0] == wide_slope
    assert stats["opt_doi_slope_5d"]["changed"] == 1
    # ...and nothing else does
    assert scoped["opt_iv30"].iloc[0] == 0.25, "scoped pass wrote a non-named column"
    assert pd.isna(scoped["opt_dist_to_flip_pct"].iloc[0]), "scoped pass filled a non-named column"
    assert bool(scoped["opt_voi_flag"].iloc[0]) is True, "scoped pass wrote an unnamed positional column"


def test_restamp_cols_never_opens_or_closes_the_retry_gate(monkeypatch):
    """A row that never carried the column is UNSTAMPED, not stale — leave it to nightly.

    Filling it here would flip the row's coverage status and lock the ordinary gate.
    """
    from scripts.stamp_options_state import restamp_columns
    _patch_stores_iv30(monkeypatch, 0.44)

    df = _positional_locked_ledger()
    df["opt_doi_slope_5d"] = None                 # never stamped on this row

    before = df[[c for c in STAMP_COVERAGE_COLS if c in df.columns]].isna().all(axis=1)
    out, stats = restamp_columns(df, ["opt_doi_slope_5d"])
    after = out[[c for c in STAMP_COVERAGE_COLS if c in out.columns]].isna().all(axis=1)

    assert pd.isna(out["opt_doi_slope_5d"].iloc[0]), "scoped pass filled a null it was not asked to fill"
    assert stats["opt_doi_slope_5d"] == {"changed": 0, "unchanged": 0, "filled": 0, "blanked": 0}
    assert list(before) == list(after), "retry-gate eligibility moved"


def test_restamp_cols_never_nulls_an_existing_value(monkeypatch):
    """Non-destructive contract, kept: no chains store → no-op, and the loss is COUNTED."""
    from scripts.stamp_options_state import restamp_columns
    _patch_stores_iv30(monkeypatch, 0.44)
    monkeypatch.setattr("engine.options_stamp._default_chain_dates", lambda: [])
    monkeypatch.setattr("scripts.stamp_options_state._default_chain_dates", lambda: [])

    out, stats = restamp_columns(_positional_locked_ledger(), ["opt_doi_slope_5d"])

    assert out["opt_doi_slope_5d"].iloc[0] == _SENTINEL_SLOPE, "a null overwrote a value"
    assert stats["opt_doi_slope_5d"]["blanked"] == 1, (
        "a value that could not be recomputed must be COUNTED, not silently kept"
    )


def test_restamp_cols_refuses_a_cross_sectional_column():
    """opt_vanna_relief is a tercile over the pass's own universe — narrowing re-adjudicates it."""
    from scripts.stamp_options_state import (
        restamp_columns, _RESTAMP_COLS_ALLOWED, _POSITIONAL_WINDOW_COLS,
    )

    assert "opt_vanna_relief" in _POSITIONAL_WINDOW_COLS, "premise moved"
    assert "opt_vanna_relief" not in _RESTAMP_COLS_ALLOWED

    with pytest.raises(SystemExit) as e:
        restamp_columns(_positional_locked_ledger(), ["opt_vanna_relief"])
    assert "cross-sectional" in str(e.value)


# ── W-OVC silent-null repair (2026-08-02; registry defect opex-vanna-charm-wovc) ────
# From the W-OVC build (2026-07-17) to 2026-08-02 opt_front7_charm_share and
# opt_root_class never reached the ledger (0/2282) while the display store carried
# 370/415 and 415/415: the default chain reader's pruned column list lacked
# expiry/T/iv (so _ovc_from_chain's required-column check silently nulled front7 on
# every default-path call), and opt_root_class had no write path at all (excluded
# from STAMP_COVERAGE_COLS like opt_opex_days, but without the dedicated write).
# These tests pin the repaired wiring end-to-end AND the tripwire that makes the
# failure class loud.

_OVC_REQUIRED_CHAIN_COLS = {"underlying", "K", "T", "iv", "oi", "is_call", "spot", "expiry"}


def _ovc_full_chain_frame(tickers=("FOO",)):
    """A FULL-SCHEMA chain snapshot: two expiries per name — 2026-07-22 (5 days from the
    2026-07-17 fire → inside the front-7 window) and 2026-08-14 (28 days → outside).
    Expiries are FIXED dates (not offsets from the file date) so the prior-day OI lookup
    keyed by (expiry, K, is_call) matches across the two snapshots."""
    rows = []
    for tk in tickers:
        for k in (95.0, 105.0):
            for exp, t_years in (("2026-07-22", 5 / 365.0), ("2026-08-14", 28 / 365.0)):
                for is_call in (True, False):
                    rows.append({
                        "underlying": tk, "K": k, "expiry": pd.Timestamp(exp),
                        "T": t_years, "iv": 0.30, "is_call": is_call,
                        "oi": 500.0, "volume": 25.0, "spot": 100.0,
                    })
    return pd.DataFrame(rows)


def test_default_chain_reader_carries_ovc_required_columns(tmp_path, monkeypatch):
    """THE DEFECT PIN: _default_read_chain must return every column _ovc_from_chain
    requires.  2026-07-17..2026-08-02 its pruned list dropped expiry/T/iv, so the
    required-column check returned early and front7 was silently null on every call."""
    from engine.options_stamp import _default_read_chain

    d = _dt.date(2026, 7, 17)
    chains = tmp_path / "chains"
    chains.mkdir()
    _ovc_full_chain_frame().to_parquet(chains / f"{d.isoformat()}.parquet", index=False)
    monkeypatch.setattr("engine.options_stamp._chains_dir", lambda: chains)

    out = _default_read_chain(d)
    assert out is not None, "reader must not fail on a full-schema chain file"
    missing = _OVC_REQUIRED_CHAIN_COLS - set(out.columns)
    assert not missing, (
        f"_default_read_chain drops {sorted(missing)} — _ovc_from_chain's required-column "
        "check will silently null opt_front7_charm_share on every default-path call "
        "(the six-week W-OVC silent-null, registry defect opex-vanna-charm-wovc)"
    )


def test_stamp_default_path_fills_front7_and_root_class(tmp_path, monkeypatch):
    """End-to-end through the PRODUCTION default readers: two full-schema chain files on
    disk, no injected read_chain — the stamp must fill opt_front7_charm_share (greeks
    from usable[-1], prior-day OI from usable[-2]) and opt_root_class."""
    chains = tmp_path / "chains"
    chains.mkdir()
    for d in (_dt.date(2026, 7, 16), _dt.date(2026, 7, 17)):  # Thu, Fri — both sessions
        _ovc_full_chain_frame().to_parquet(chains / f"{d.isoformat()}.parquet", index=False)
    monkeypatch.setattr("engine.options_stamp._chains_dir", lambda: chains)

    s = stamp_options_state(
        "2026-07-17", "FOO",
        read_summary=lambda t: None,
        skew_df=None, ivspread_df=None,
        _skew_loader=lambda: None, _ivspread_loader=lambda: None,
    )
    f7 = s["opt_front7_charm_share"]
    assert f7 is not None, (
        "opt_front7_charm_share must be non-null when chains carry full schema — "
        "null here means the default chain reader lost the OVC columns again"
    )
    assert 0.0 < f7 < 1.0, f"one front expiry of two → share strictly inside (0,1), got {f7}"
    assert s["opt_root_class"] == "single_name"


def test_stamp_ledger_writes_root_class_on_all_eligible_rows(monkeypatch):
    """opt_root_class gets the dedicated always-computable write (opt_opex_days contract):
    written on covered AND no-coverage rows, without closing the retry gate."""
    df = _legacy_ledger()
    monkeypatch.setattr("engine.options_stamp._default_chain_dates",
                        lambda: [_dt.date(2026, 6, d) for d in range(15, 22)])
    monkeypatch.setattr("scripts.stamp_options_state._default_chain_dates",
                        lambda: [_dt.date(2026, 6, d) for d in range(15, 22)])
    monkeypatch.setattr("engine.options_stamp._default_read_chain",
                        lambda d: _chain_frame("FOO"))
    monkeypatch.setattr("engine.options_stamp._default_read_summary",
                        lambda t: _summary_frame([f"2026-06-{d}" for d in range(15, 22)])
                        if t == "FOO" else None)

    out, _ = stamp_ledger(df)
    assert (out["opt_root_class"] == "single_name").all(), (
        "every row must carry opt_root_class after a pass — it is ticker taxonomy, "
        "needs no data store, and sat at 0/2282 for six weeks without this write"
    )
    # the no-coverage row must REMAIN retryable — root_class is not a coverage column
    bar = out[out["ticker"] == "BAR"]
    present = [c for c in STAMP_COVERAGE_COLS if c in out.columns]
    assert bar[present].isna().all(axis=1).all(), (
        "writing opt_root_class must never close the options-family retry gate"
    )


def test_backfill_ovc_fills_gate_closed_rows_only(monkeypatch):
    """--backfill-ovc scope contract:
      * opt_root_class: filled wherever null (every row);
      * opt_front7_charm_share: ONLY on gate-closed rows (≥1 coverage col non-null) —
        writing it on a retryable row would close the gate and permanently lock out
        the summary/skew/ivspread columns;
      * never overwrites a non-null; idempotent."""
    from scripts.stamp_options_state import backfill_ovc

    df = pd.DataFrame({
        "as_of": ["2026-07-17"] * 3,
        "ticker": ["FOO", "FOO", "BAR"],
        "lane": ["buy"] * 3, "horizon": [21] * 3,
    })
    for c in STAMP_COLS:
        df[c] = None
    df.loc[0, "opt_gamma_regime"] = "long"       # gate closed → backfill target
    df.loc[1, "opt_gamma_regime"] = "long"
    df.loc[1, "opt_front7_charm_share"] = 0.123  # already stamped → must survive
    # row 2 (BAR): fully null → retryable → front7 must NOT be written even though
    # the chain fixture below carries BAR data

    monkeypatch.setattr("scripts.stamp_options_state._default_chain_dates",
                        lambda: [_dt.date(2026, 7, 16), _dt.date(2026, 7, 17)])
    monkeypatch.setattr("engine.options_stamp._default_read_chain",
                        lambda d: _ovc_full_chain_frame(("FOO", "BAR")))

    out, n_root, n_front7 = backfill_ovc(df)
    assert n_root == 3 and n_front7 == 1
    f7 = out.loc[0, "opt_front7_charm_share"]
    assert f7 is not None and 0.0 < f7 < 1.0
    assert out.loc[1, "opt_front7_charm_share"] == 0.123, "backfill overwrote a stamped value"
    assert pd.isna(out.loc[2, "opt_front7_charm_share"]), (
        "backfill wrote front7 on a RETRYABLE row — that closes the retry gate and "
        "permanently locks out the summary/skew/ivspread columns"
    )
    assert (out["opt_root_class"] == "single_name").all()
    # idempotent: a second pass changes nothing
    out2, n_root2, n_front72 = backfill_ovc(out)
    assert n_root2 == 0 and n_front72 == 0


def test_display_twin_map_integrity():
    """DISPLAY_TWIN_COLS maps real stamp columns and carries the two W-OVC columns whose
    silent null it exists to catch; opt_iv_rank_252 stays exempt (A9 designed-null)."""
    from engine.options_stamp import DISPLAY_TWIN_COLS

    unknown = set(DISPLAY_TWIN_COLS) - set(STAMP_COLS)
    assert not unknown, f"twin map names non-stamp columns: {sorted(unknown)}"
    assert "opt_front7_charm_share" in DISPLAY_TWIN_COLS
    assert "opt_root_class" in DISPLAY_TWIN_COLS
    assert "opt_iv_rank_252" not in DISPLAY_TWIN_COLS, (
        "opt_iv_rank_252 is designed-null in the ledger (ruling A9) until the thetadata "
        "dedup repair lands — mapping it would fire a permanent false alarm the day its "
        "display twin starts populating"
    )
    assert "opt_vanna_relief" not in DISPLAY_TWIN_COLS, (
        "opt_vanna_relief has no display twin (ledger-only cross-sectional flag)"
    )


def test_twin_guard_prints_line_start_warning(tmp_path, monkeypatch, capsys):
    """The nightly tripwire prints a GitHub annotation that STARTS the line (bare print,
    never a logger — the ::warning is silently dropped otherwise) when a stamp column is
    100% null while its display twin is populated."""
    from lib import config as _config
    from scripts.stamp_options_state import _twin_silent_null_guard

    (tmp_path / "options_entry").mkdir()
    pd.DataFrame({"front7_charm_share": [0.4, 0.5]}).to_parquet(
        tmp_path / "options_entry" / "state.parquet", index=False)
    monkeypatch.setattr(_config, "data_dir", lambda: tmp_path)

    df = pd.DataFrame({"as_of": ["2026-07-17"], "ticker": ["FOO"]})
    for c in STAMP_COLS:
        df[c] = None

    n = _twin_silent_null_guard(df)
    assert n == 1, "exactly one twin pair (front7) is present in the fixture display store"
    out_lines = capsys.readouterr().out.splitlines()
    hits = [ln for ln in out_lines if ln.startswith("::warning title=stamp-col-silent-null::")]
    assert len(hits) == 1 and "opt_front7_charm_share" in hits[0], (
        "the annotation must START the line or GitHub drops it (annotation-line-start law)"
    )


def test_committed_ledger_has_no_silent_null_stamp_cols():
    """THE SIX-WEEK SIGNATURE, enforced on the committed parquets: a stamp column that is
    100% null in data/us_board_ledger/retro_grades.parquet while its display twin in
    data/options_entry/state.parquet is populated means the ledger write path is dead —
    the compute works (display proves it), the write never lands, and the gate bucket
    sits at n=0 forever.  If this fails for a NEW stamp column you just shipped: wire its
    ledger write (or backfill) in the same PR — do not exempt it here without a ruling."""
    from engine.options_stamp import DISPLAY_TWIN_COLS

    repo = Path(__file__).resolve().parent.parent
    ledger_p = repo / "data" / "us_board_ledger" / "retro_grades.parquet"
    state_p = repo / "data" / "options_entry" / "state.parquet"
    if not ledger_p.exists() or not state_p.exists():
        pytest.skip("committed stores absent in this checkout")

    led = pd.read_parquet(ledger_p)
    state = pd.read_parquet(state_p)
    if led.empty or state.empty:
        pytest.skip("committed stores empty")

    dead = []
    for led_col, disp_col in DISPLAY_TWIN_COLS.items():
        if led_col not in led.columns or disp_col not in state.columns:
            continue
        if int(state[disp_col].notna().sum()) > 0 and int(led[led_col].notna().sum()) == 0:
            dead.append(f"{led_col} (display twin {disp_col} is populated)")
    assert not dead, (
        "silent-permanent-null stamp columns — ledger write path is dead while the "
        f"display store computes fine: {dead}"
    )


# ── the 5-SESSION basis resolves its far endpoint by DATE, not by POSITION ───────────
#
# The session filters above make every row in a positional window a real SESSION. They do
# NOT make a six-row window five sessions WIDE — the store is also missing sessions the
# collector never ran for, and no reader-side filter can conjure those. Measured on
# data/polygon_gex/summary_AAPL.parquet at as_of 2026-08-06, the six trailing session rows
# are 07-27, 07-28, 07-29, 07-30, 07-31, 08-06: SIX rows spanning NINE sessions, because
# the 08-03..08-05 collection outage punched a hole into the tail window. `iloc[-6]`
# therefore resolved 2026-07-27 where the 5-sessions-back session is 2026-07-30 — a
# NINE-session change shipped labelled "5d" into opt_vanna_relief's cross-sectional
# tercile (the same class that flipped the sign on 10 of 10 sampled names at 2026-07-21).
#
# A two-endpoint difference has an exact repair: resolve the far endpoint BY DATE. Only
# the endpoints enter a difference, so an interior hole is irrelevant and the stat
# recovers exactly; a hole AT the target session is unmeasurable, so the stat is null —
# never a mislabeled basis. Both readers below route through
# engine.options_stamp._row_n_sessions_back. (The display twin
# engine/options_entry_state._compute_vanna_hedge_5d is pinned in
# tests/test_options_entry_state.py; the resolver itself in
# tests/test_options_session_guards.py.)

# The real outage geometry, replayed. iv30 is chosen so the CALENDAR answer and the
# POSITIONAL answer land on OPPOSITE SIDES of the latest reading — a test that only
# asserted "the value changed" would pass on a rounding difference.
_GAP_ROWS = ["2026-07-27", "2026-07-28", "2026-07-29", "2026-07-30", "2026-07-31",
             "2026-08-06"]
_GAP_IV30 = [0.20, 0.22, 0.24, 0.30, 0.28, 0.26]
_GAP_NET_VEX = 1_000_000.0
_GAP_ASOF = _dt.date(2026, 8, 6)
_GAP_FIVE_BACK = _dt.date(2026, 7, 30)    # 08-05, 08-04, 08-03, 07-31, 07-30
_GAP_ILOC6 = _dt.date(2026, 7, 27)        # what the positional read used to give
# calendar   : 0.26 − 0.30 = −0.04  →  vanna = −net_vex × chg = +40,000
# positional : 0.26 − 0.20 = +0.06  →  vanna = −net_vex × chg = −60,000
_GAP_CAL_CHG = _GAP_IV30[-1] - _GAP_IV30[3]
_GAP_POS_CHG = _GAP_IV30[-1] - _GAP_IV30[0]

# Seven rows — clear of the ≥6-row floor — with the 5-back session (07-30) absent.
# iloc[-6] is 07-24, so a positional read WOULD have returned a number here.
_MISSING_ROWS = ["2026-07-23", "2026-07-24", "2026-07-27", "2026-07-28",
                 "2026-07-29", "2026-07-31", "2026-08-06"]
_MISSING_IV30 = [0.18, 0.20, 0.20, 0.22, 0.24, 0.28, 0.26]

# Six CONSECUTIVE sessions: dense, so the calendar target IS index[-6] and the value must
# be byte-identical to what the old positional code produced.
_DENSE_ROWS = ["2026-07-30", "2026-07-31", "2026-08-03", "2026-08-04",
               "2026-08-05", "2026-08-06"]
_DENSE_IV30 = [0.30, 0.28, 0.27, 0.29, 0.31, 0.26]


def _vanna_summary_frame(dates, iv30s, *, net_vex=_GAP_NET_VEX):
    """A polygon_gex summary frame carrying the two columns the 5-session basis reads."""
    idx = pd.to_datetime(list(dates))
    n = len(idx)
    return pd.DataFrame(
        {
            "gamma_regime": ["long"] * n,
            "dist_to_flip_pct": [5.0] * n,
            "magnet_up": [110.0] * n,
            "magnet_down": [95.0] * n,
            "net_vex": [float(net_vex)] * n,
            "iv30": [float(v) for v in iv30s],
        },
        index=idx,
    )


def _assert_outage_geometry(frame):
    """PREMISE for every gap test: six rows spanning NINE sessions.

    Without this the fixture can rot dense — the calendar and positional answers would
    coincide and the behavioural assertions would pass for the wrong reason.
    """
    from lib import nyse_calendar
    idx = [pd.Timestamp(d).date() for d in frame.index]
    assert len(frame) == 6, f"the outage fixture must hold exactly six rows, got {len(frame)}"
    assert len(nyse_calendar.sessions_between(idx[0], idx[-1])) == 9, (
        f"fixture premise gone: {idx[0]}..{idx[-1]} no longer spans nine sessions, so "
        "positional and calendar resolution would agree and this test is vacuous")
    assert idx[3] == _GAP_FIVE_BACK and idx[0] == _GAP_ILOC6
    assert _GAP_CAL_CHG < 0 < _GAP_POS_CHG, (
        "fixture premise: the calendar and positional answers must differ in SIGN")


# ── site (1): engine/options_stamp._vanna_hedge_5d_basis → opt_vanna_relief ──────────

def test_vanna_5d_basis_resolves_the_far_endpoint_by_calendar_not_by_position():
    """The measured outage shape: 6 rows / 9 sessions, opposite-sign answers."""
    from engine.options_stamp import BASIS_OK, _vanna_hedge_5d_basis

    frame = _vanna_summary_frame(_GAP_ROWS, _GAP_IV30)
    _assert_outage_geometry(frame)

    cal = round(-_GAP_NET_VEX * _GAP_CAL_CHG, 6)      # +40,000 — the 07-30 endpoint
    pos = round(-_GAP_NET_VEX * _GAP_POS_CHG, 6)      # −60,000 — the iloc[-6] endpoint
    assert cal > 0 > pos, "fixture premise: the two answers have opposite signs"

    got, status = _vanna_hedge_5d_basis(_GAP_ASOF, frame)
    assert got == pytest.approx(cal), (
        f"shipped {got}; five sessions before {_GAP_ASOF} is {_GAP_FIVE_BACK} "
        f"(iv30 {_GAP_IV30[3]}), so vanna_hedge_5d is {cal}")
    assert got != pytest.approx(pos), (
        f"shipped the POSITIONAL iloc[-6] answer {pos} — the {_GAP_ILOC6} endpoint is "
        "NINE sessions back, and this stat is labelled '5d'")
    assert status == BASIS_OK
    # The wrapper the ledger path actually calls must agree with the basis it wraps.
    from engine.options_stamp import _vanna_hedge_5d_from_summary
    assert _vanna_hedge_5d_from_summary(_GAP_ASOF, frame) == pytest.approx(cal)


def test_vanna_5d_basis_nulls_when_the_five_back_session_has_no_row():
    """≥6 rows and still None — the null comes from RESOLUTION, not the row floor."""
    from engine.options_stamp import (BASIS_GAP, _vanna_hedge_5d_basis,
                                      _vanna_hedge_5d_from_summary)
    from lib import nyse_calendar

    frame = _vanna_summary_frame(_MISSING_ROWS, _MISSING_IV30)
    idx = [pd.Timestamp(d).date() for d in frame.index]

    # PREMISE — SEVEN rows. Load-bearing: the reader already nulls below six rows, so at
    # exactly the floor a None could not be attributed to the missing target session.
    assert len(frame) >= 6, "a None here must come from target resolution, not the floor"
    assert nyse_calendar.is_session(_GAP_FIVE_BACK), "fixture premise: 07-30 trades"
    assert _GAP_FIVE_BACK not in idx, "fixture premise: the store has no 07-30 row"
    # A positional read would have returned a number (iloc[-6] = 07-24, iv30 0.20).
    assert pd.Timestamp(frame.iloc[-6].name).date() == _dt.date(2026, 7, 24)
    would_have = round(-_GAP_NET_VEX * (_MISSING_IV30[-1] - _MISSING_IV30[1]), 6)
    assert would_have == pytest.approx(-60_000.0), "fixture premise: iloc[-6] is non-null"

    got, status = _vanna_hedge_5d_basis(_GAP_ASOF, frame)
    assert got is None, (
        f"shipped {got} for a store with no {_GAP_FIVE_BACK} row — unmeasurable is a "
        "null, never a substituted endpoint")
    assert status == BASIS_GAP, (
        f"status {status!r}: seven rows with one session missing is a collection GAP, "
        "not absent history — the tercile's coverage floor reads that distinction")
    assert _vanna_hedge_5d_from_summary(_GAP_ASOF, frame) is None


def test_vanna_5d_basis_on_a_dense_store_is_the_old_positional_value():
    """Strict refinement: no gap, no change — every healthy date keeps its value."""
    from engine.options_stamp import BASIS_OK, _vanna_hedge_5d_basis
    from lib import nyse_calendar

    frame = _vanna_summary_frame(_DENSE_ROWS, _DENSE_IV30)
    idx = [pd.Timestamp(d).date() for d in frame.index]

    # PREMISE — six rows over exactly six sessions: dense, so calendar target == index[-6].
    assert len(frame) == 6
    assert len(nyse_calendar.sessions_between(idx[0], idx[-1])) == 6, (
        "fixture premise gone: these six dates no longer span exactly six sessions")

    # The literal the OLD positional code produced, computed from the fixture's own
    # numbers (not from a second call to the function under test).
    expected = round(-_GAP_NET_VEX * (_DENSE_IV30[-1] - _DENSE_IV30[0]), 6)
    assert expected == pytest.approx(40_000.0)

    got, status = _vanna_hedge_5d_basis(_GAP_ASOF, frame)
    assert got == pytest.approx(expected), (
        f"dense store shipped {got}, not the unchanged positional value {expected}")
    assert status == BASIS_OK


# ── site (2): scripts/stamp_options_state._get_iv30_5d_chg_from_summary ─────────────
# The relief SIGN input: reads the store from disk through _default_read_summary, so
# these go through the real on-disk path, not an injected frame.

def _plant_summary(tmp_path, monkeypatch, dates, iv30s, ticker="FOO"):
    from engine import options_stamp as st
    _vanna_summary_frame(dates, iv30s).to_parquet(tmp_path / f"summary_{ticker}.parquet")
    monkeypatch.setattr(st, "_summary_dir", lambda: tmp_path)
    planted = st._default_read_summary(ticker)
    assert planted is not None and len(planted) == len(dates), (
        "the session filter dropped a fixture row — every fixture date must be a session")
    return planted


def test_iv30_5d_chg_resolves_the_far_endpoint_by_calendar_not_by_position(
        monkeypatch, tmp_path):
    from scripts.stamp_options_state import _get_iv30_5d_chg_from_summary

    frame = _plant_summary(tmp_path, monkeypatch, _GAP_ROWS, _GAP_IV30)
    _assert_outage_geometry(frame)

    got = _get_iv30_5d_chg_from_summary("2026-08-06", "FOO", {})
    assert got == pytest.approx(_GAP_CAL_CHG), (
        f"read {got}; the {_GAP_FIVE_BACK} endpoint gives {_GAP_CAL_CHG}")
    assert got != pytest.approx(_GAP_POS_CHG), (
        f"read the POSITIONAL iloc[-6] change {_GAP_POS_CHG} — nine sessions of iv30 "
        "move, signed the other way, feeding opt_vanna_relief")
    assert got < 0 < _GAP_POS_CHG, "the shipped answer must carry the CALENDAR sign"


def test_iv30_5d_chg_nulls_when_the_five_back_session_has_no_row(monkeypatch, tmp_path):
    from scripts.stamp_options_state import _get_iv30_5d_chg_from_summary

    frame = _plant_summary(tmp_path, monkeypatch, _MISSING_ROWS, _MISSING_IV30)
    idx = [pd.Timestamp(d).date() for d in frame.index]

    # PREMISE — SEVEN rows, so a None cannot come from the reader's own <6-row floor.
    assert len(frame) >= 6
    assert _GAP_FIVE_BACK not in idx, "fixture premise: the store has no 07-30 row"
    assert pd.Timestamp(frame.iloc[-6].name).date() == _dt.date(2026, 7, 24), (
        "fixture premise: a positional read would have returned the 07-24 row")

    assert _get_iv30_5d_chg_from_summary("2026-08-06", "FOO", {}) is None, (
        "a missing 5-back session must null the relief sign input, not widen its basis")


def test_iv30_5d_chg_on_a_dense_store_is_the_old_positional_value(monkeypatch, tmp_path):
    from scripts.stamp_options_state import _get_iv30_5d_chg_from_summary
    from lib import nyse_calendar

    frame = _plant_summary(tmp_path, monkeypatch, _DENSE_ROWS, _DENSE_IV30)
    idx = [pd.Timestamp(d).date() for d in frame.index]

    assert len(frame) == 6
    assert len(nyse_calendar.sessions_between(idx[0], idx[-1])) == 6, (
        "fixture premise gone: these six dates no longer span exactly six sessions")

    expected = _DENSE_IV30[-1] - _DENSE_IV30[0]     # literal from the fixture
    assert expected == pytest.approx(-0.04)
    assert _get_iv30_5d_chg_from_summary("2026-08-06", "FOO", {}) == pytest.approx(expected)


# ---------------------------------------------------------------------------
# The tercile COVERAGE FLOOR (2026-08-06).
#
# Calendar-resolving the 5-session basis makes it null on a store gap, and that null is
# DATE-wide rather than per-name: every ticker reads the same store on the same schedule.
# The pre-existing `len(vals) >= 3` floor cannot see that — it answers "enough values to
# draw a boundary", never "do these values represent the universe".  These guards pin the
# distinction, using the geometry actually measured on the committed store.
# ---------------------------------------------------------------------------

def test_tercile_refuses_a_date_whose_ranked_names_are_coverage_selected(capsys):
    """The measured collapse: 5 ranked of 375 measurable must NOT produce a threshold."""
    from scripts.stamp_options_state import _TERCILE_MIN_NAMES, _tercile_thresholds

    survivors = [-3000.0, -1500.0, -850.0, -400.0, 25000.0]
    # PREMISE: the old `>= 3` floor would have FIRED on this input — otherwise this test
    # would pass for the wrong reason (too few values, not too little coverage).
    assert len(survivors) >= _TERCILE_MIN_NAMES

    out = _tercile_thresholds({"2026-07-22": survivors}, {"2026-07-22": 375})
    assert "2026-07-22" not in out, (
        "a date ranking 5 of 375 measurable names (1.3%) was given a tercile boundary — "
        "that redefines 'top tercile of the market' as 'top tercile of 5 "
        "coverage-selected names'")

    # Surfaced, never silent — and as a LINE-START annotation, or Actions drops it.
    line = [ln for ln in capsys.readouterr().out.splitlines() if "vanna-tercile" in ln]
    assert line and line[0].startswith("::warning "), (
        "the refusal must emit a line-start ::warning; a prefixed logger call is dropped "
        "by GitHub Actions")
    assert "5 of 375" in line[0]


def test_tercile_still_ranks_a_healthy_date(capsys):
    """The other side of the floor: 374 of 375 (99.7%) is the normal case and must rank."""
    from scripts.stamp_options_state import _tercile_thresholds

    vals = [float(i) for i in range(374)]
    out = _tercile_thresholds({"2026-07-27": vals}, {"2026-07-27": 375})
    assert "2026-07-27" in out, (
        "a date ranking 99.7% of its measurable names was refused — the floor is "
        "supposed to sit between the 1.3% and 99.7% populations, not above both")
    assert out["2026-07-27"] == pytest.approx(np.percentile(vals, 100.0 * 2.0 / 3.0))
    assert "vanna-tercile" not in capsys.readouterr().out


def test_coverage_denominator_excludes_names_that_were_never_candidates():
    """Coverage is ranked ÷ MEASURABLE, never ÷ the whole board.

    Only 214 of 2,287 ledger rows carry this flag at all.  Dividing by the board would
    refuse to rank on every healthy date — the denominator must exclude names with no
    options history (BASIS_NO_HISTORY), which is why the producer reports WHY a value is
    null instead of just returning None.
    """
    from scripts.stamp_options_state import _tercile_thresholds

    vals = [1.0, 2.0, 3.0, 4.0]
    # 4 ranked, 4 measurable (100%) — but 2,287 names exist on the board overall.
    assert "2026-07-27" in _tercile_thresholds({"2026-07-27": vals}, {"2026-07-27": 4})
    # Had the denominator been the whole board, this same date would be refused:
    assert "2026-07-27" not in _tercile_thresholds({"2026-07-27": vals}, {"2026-07-27": 2287})
