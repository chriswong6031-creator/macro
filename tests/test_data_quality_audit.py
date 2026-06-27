"""Tests for the end-of-collection data-quality audit suite.

Covers scripts/audit_prices, audit_macro, audit_universe and the collect.py governance gate.
Each test builds a tiny SYNTHETIC store in a tmp dir and asserts the deterministic rules catch
the planted defect while staying silent on clean data. The three headline scenarios the spec
calls out — a synthetic NaN, an 8% backwards revision, a missing ticker — plus the regression
cases the build review surfaced (deep-history gaps must NOT false-fail; near-zero revisions must
NOT false-fail; the >5% abort gate) and the read-only/idempotency contract.
"""
from __future__ import annotations

import hashlib
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from scripts import audit_common, audit_macro, audit_prices, audit_universe, collect

CFG = audit_common.quality_cfg()


# --- builders ---------------------------------------------------------------

def _ohlcv(n=400, end="2026-06-18", freq="B") -> pd.DataFrame:
    """A clean OHLCV frame of n bars ending on `end` (business-day index by default)."""
    idx = pd.bdate_range(end=end, periods=n) if freq == "B" else pd.date_range(end=end, periods=n, freq=freq)
    base = np.linspace(100.0, 130.0, n)
    df = pd.DataFrame(
        {"open": base, "high": base + 1.0, "low": base - 1.0, "close": base,
         "volume": np.full(n, 1_000_000.0)},
        index=idx,
    )
    df.index.name = "Date"
    return df


def _monthly(values, start="2015-01-01", col="val") -> pd.DataFrame:
    idx = pd.date_range(start=start, periods=len(values), freq="MS")
    df = pd.DataFrame({col: np.asarray(values, dtype="float64")}, index=idx)
    df.index.name = "date"
    return df


def _write(df: pd.DataFrame, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(path)


def _reasons(universe: dict) -> str:
    return " | ".join(r for f in universe["failed"] for r in f["reasons"])


def _u(doc: dict, name: str) -> dict:
    return next(x for x in doc["universes"] if x["name"] == name)


# --- audit_prices: synthetic NaN + structural integrity ---------------------

def test_prices_catches_interior_nan(tmp_path):
    data = tmp_path / "data"
    _write(_ohlcv(), data / "stocks" / "GOOD.parquet")
    bad = _ohlcv()
    bad.iloc[200, bad.columns.get_loc("close")] = np.nan  # interior NaN in a price column
    _write(bad, data / "stocks" / "BADNAN.parquet")

    doc = audit_prices.run(stores=[{"group": "stocks"}], data_dir=data, out_dir=tmp_path / "q")
    u = _u(doc, "stocks")
    failed = {f["name"] for f in u["failed"]}
    assert failed == {"BADNAN"}
    assert "interior NaN in close" in _reasons(u)


def test_prices_tolerates_volume_nan(tmp_path):
    """Older rows legitimately lack volume — a NaN there must NOT fail (documented in LIMITATIONS)."""
    data = tmp_path / "data"
    df = _ohlcv()
    df.iloc[10, df.columns.get_loc("volume")] = np.nan
    _write(df, data / "stocks" / "VOLNAN.parquet")
    doc = audit_prices.run(stores=[{"group": "stocks"}], data_dir=data, out_dir=tmp_path / "q")
    assert _u(doc, "stocks")["n_failed"] == 0


def test_prices_catches_ohlc_negvol_and_inf(tmp_path):
    data = tmp_path / "data"
    bad = _ohlcv()
    bad.iloc[10, bad.columns.get_loc("high")] = bad.iloc[10]["close"] - 5.0   # high below close
    bad.iloc[20, bad.columns.get_loc("volume")] = -1.0                        # negative volume
    bad.iloc[30, bad.columns.get_loc("low")] = np.inf                        # inf
    _write(bad, data / "stocks" / "BAD.parquet")
    doc = audit_prices.run(stores=[{"group": "stocks"}], data_dir=data, out_dir=tmp_path / "q")
    r = _reasons(_u(doc, "stocks"))
    assert "OHLC invalid" in r and "negative volume" in r and "inf in low" in r


def test_prices_recent_gap_fails_but_deep_history_closure_does_not(tmp_path):
    """A recent hole is an actionable collection miss (fail); an immutable deep-history exchange
    closure (the 9/11 pattern) must be ignored so the gate doesn't false-abort forever."""
    data = tmp_path / "data"
    asof = date(2026, 6, 27)

    deep = _ohlcv(n=1500, end="2026-06-18")                  # long clean series
    deep = deep.drop(deep.index[200:205])                    # a 1-week hole ~2020 (deep history)
    _write(deep, data / "stocks" / "DEEPGAP.parquet")

    recent = _ohlcv(n=1500, end="2026-06-18")
    # drop ~2 weeks inside the recent window (last ~120d) -> a real recent hole
    mask = (recent.index >= "2026-05-04") & (recent.index <= "2026-05-15")
    recent = recent[~mask]
    _write(recent, data / "stocks" / "RECENTGAP.parquet")

    doc = audit_prices.run(stores=[{"group": "stocks"}], data_dir=data, out_dir=tmp_path / "q", asof=asof)
    failed = {f["name"] for f in _u(doc, "stocks")["failed"]}
    assert "RECENTGAP" in failed and "DEEPGAP" not in failed
    assert "recent gap" in _reasons(_u(doc, "stocks"))


def test_prices_skips_snapshot_only_store(tmp_path):
    """A dir with no per-ticker parquet (china_stocks/hk_stocks hold only latest.json) is SKIPPED,
    never an abort for a missing backing store."""
    data = tmp_path / "data"
    (data / "china_stocks").mkdir(parents=True)
    (data / "china_stocks" / "latest.json").write_text("{}")
    doc = audit_prices.run(stores=[{"group": "china_stocks"}], data_dir=data, out_dir=tmp_path / "q")
    u = _u(doc, "china_stocks")
    assert u["skipped"] and u["n"] == 0
    assert doc["n"] == 0  # skipped cohort excluded from the gate totals


# --- audit_macro: 8% backwards revision + integrity -------------------------

def test_macro_catches_8pct_backwards_revision(tmp_path):
    data, base = tmp_path / "data", tmp_path / "baselines"
    _write(_monthly(np.linspace(100.0, 200.0, 120)), data / "fred" / "TEST.parquet")
    asof = date(2025, 3, 1)

    seed = audit_macro.run(groups=["fred"], data_dir=data, baseline_dir=base,
                           out_dir=tmp_path / "q", asof=asof)
    assert seed["n_failed"] == 0  # first run only seeds the baseline

    df = _monthly(np.linspace(100.0, 200.0, 120))
    df.iloc[10, 0] *= 1.08        # revise a SETTLED historical value by 8%
    _write(df, data / "fred" / "TEST.parquet")
    doc = audit_macro.run(groups=["fred"], data_dir=data, baseline_dir=base,
                          out_dir=tmp_path / "q", asof=asof)
    assert doc["n_failed"] == 1
    assert "backwards revision" in _reasons(_u(doc, "fred"))


def test_macro_near_zero_revision_not_false_flagged(tmp_path):
    """A sub-noise nudge on a near-zero settled value is a huge RELATIVE % but a tiny ABSOLUTE
    move — the dual relative-AND-absolute test must not flag it (the build-review regression)."""
    data, base = tmp_path / "data", tmp_path / "baselines"
    vals = np.linspace(-2.0, 3.0, 120)            # a spread series that crosses zero
    _write(_monthly(vals, col="spread"), data / "fred" / "SPREAD.parquet")
    asof = date(2025, 3, 1)
    audit_macro.run(groups=["fred"], data_dir=data, baseline_dir=base, out_dir=tmp_path / "q", asof=asof)

    df = _monthly(vals, col="spread")
    near_zero = int(np.argmin(np.abs(vals[:90])))  # a settled point closest to zero
    df.iloc[near_zero, 0] = vals[near_zero] + 0.0005   # tiny absolute nudge (well below the floor)
    _write(df, data / "fred" / "SPREAD.parquet")
    doc = audit_macro.run(groups=["fred"], data_dir=data, baseline_dir=base, out_dir=tmp_path / "q", asof=asof)
    assert doc["n_failed"] == 0


def test_macro_catches_inf(tmp_path):
    data, base = tmp_path / "data", tmp_path / "baselines"
    vals = np.linspace(100.0, 200.0, 120)
    vals[-3] = np.inf
    _write(_monthly(vals), data / "fred" / "INFSER.parquet")
    doc = audit_macro.run(groups=["fred"], data_dir=data, baseline_dir=base,
                          out_dir=tmp_path / "q", asof=date(2025, 3, 1))
    assert "inf in val" in _reasons(_u(doc, "fred"))


def test_macro_idempotent_second_run_clean(tmp_path):
    data, base = tmp_path / "data", tmp_path / "baselines"
    _write(_monthly(np.linspace(100.0, 200.0, 120)), data / "fred" / "TEST.parquet")
    a = audit_macro.run(groups=["fred"], data_dir=data, baseline_dir=base, out_dir=tmp_path / "q", asof=date(2025, 3, 1))
    b = audit_macro.run(groups=["fred"], data_dir=data, baseline_dir=base, out_dir=tmp_path / "q", asof=date(2025, 3, 1))
    assert a["n_failed"] == b["n_failed"] == 0


# --- audit_universe: missing ticker -----------------------------------------

def test_universe_catches_missing_and_short_ticker(tmp_path):
    data = tmp_path / "data"
    _write(_ohlcv(n=400), data / "yahoo" / "PRESENT.parquet")   # deep -> ok
    _write(_ohlcv(n=100), data / "yahoo" / "SHORTY.parquet")    # present but < 250 bars
    conf = {"yahoo": {"tickers": {"sectors": ["PRESENT", "SHORTY", "ABSENT"]}}}

    doc = audit_universe.run(conf=conf, data_dir=data, out_dir=tmp_path / "q")
    u = _u(doc, "us_sectors")
    failed = {f["name"]: f["reasons"][0] for f in u["failed"]}
    assert "ABSENT" in failed and "missing from" in failed["ABSENT"]
    assert "SHORTY" in failed and "short" in failed["SHORTY"]
    assert "PRESENT" not in failed


def test_universe_coverage_limited_missing_is_flag_not_fail(tmp_path):
    """A name outside a coverage-limited search matrix (china/canada) is a FLAG, not a fail;
    a present-but-truncated series there is still a fail."""
    data = tmp_path / "data"
    idx = pd.bdate_range(end="2026-06-18", periods=400)
    wide = pd.DataFrame({"600000.SS": np.linspace(1, 2, 400),          # deep -> ok
                         "600001.SS": [np.nan] * 300 + list(np.linspace(1, 2, 100))},  # 100 valid -> short fail
                        index=idx)
    wide.index.name = "Date"
    _write(wide, data / "china_search" / "closes.parquet")
    conf = {"china": {"constituents": {"X": ["600000.SS", "600001.SS", "999999.SZ"]}}}

    doc = audit_universe.run(conf=conf, data_dir=data, out_dir=tmp_path / "q")
    u = _u(doc, "china_constituents")
    failed = {f["name"] for f in u["failed"]}
    flagged = {f["name"] for f in u["flags"]}
    assert "600001.SS" in failed                # truncated -> fail
    assert "999999.SZ" in flagged and "999999.SZ" not in failed  # off-coverage -> flag only


def test_universe_theme_in_membership_without_price_is_nobars(tmp_path):
    """A theme name present in membership but without a committed price parquet (price lives in the
    git-excluded breadth cache) is informational (nobars flag), never a fail."""
    data = tmp_path / "data"
    _write(pd.DataFrame({"ticker": ["INUNIV", "WITHPRICE"]}), data / "universe" / "membership.parquet")
    _write(_ohlcv(n=400), data / "stocks" / "WITHPRICE.parquet")
    conf = {"themes": {"t": {"tickers": ["INUNIV", "WITHPRICE", "TYPO123"]}}}

    doc = audit_universe.run(conf=conf, data_dir=data, out_dir=tmp_path / "q")
    u = _u(doc, "us_themes")
    failed = {f["name"] for f in u["failed"]}
    flagged = {f["name"] for f in u["flags"]}
    assert "TYPO123" in failed                  # not even in membership -> real config error
    assert "INUNIV" in flagged and "INUNIV" not in failed   # in universe, price in cache -> ok
    assert "WITHPRICE" not in failed


# --- collect.py governance gate ---------------------------------------------

def test_gate_aborts_when_universe_exceeds_5pct(tmp_path):
    """End-to-end: a real audit over a store with >5% corrupt tickers must RuntimeError."""
    data = tmp_path / "data"
    for i in range(18):
        _write(_ohlcv(), data / "stocks" / f"OK{i}.parquet")
    for i in range(2):                          # 2/20 = 10% > abort_fail_pct(5%)
        bad = _ohlcv()
        bad.iloc[100, bad.columns.get_loc("close")] = np.nan
        _write(bad, data / "stocks" / f"BAD{i}.parquet")

    audit_fns = [("prices", lambda: audit_prices.run(
        stores=[{"group": "stocks"}], cfg=CFG, data_dir=data, out_dir=tmp_path / "q"))]
    with pytest.raises(RuntimeError, match="DATA-QUALITY GATE FAILED"):
        collect.run_quality_audits(cfg=CFG, audit_fns=audit_fns)


def test_gate_warns_but_does_not_abort_in_1_to_5pct_band(caplog):
    doc = {"n_flags": 0, "universes": [
        {"name": "stocks", "n": 100, "n_failed": 3, "fail_pct": 3.0, "skipped": False}]}
    with caplog.at_level("WARNING"):
        s = collect.run_quality_audits(cfg=CFG, audit_fns=[("prices", lambda: doc)])
    assert s["aborts"] == [] and s["warns"]
    assert any("elevated failure rate" in r.message for r in caplog.records)


def test_gate_passes_clean_and_skipped_never_aborts(caplog):
    doc = {"n_flags": 5, "universes": [
        {"name": "ok", "n": 100, "n_failed": 0, "fail_pct": 0.0, "skipped": False},
        {"name": "hk", "n": 0, "n_failed": 0, "fail_pct": 0.0, "skipped": True}]}
    s = collect.run_quality_audits(cfg=CFG, audit_fns=[("u", lambda: doc)])
    assert s["aborts"] == [] and s["warns"] == []


def test_gate_never_emails_and_logs_when_flag_set(caplog):
    cfg = dict(CFG, email_alerts=True)
    doc = {"n_flags": 0, "universes": []}
    with caplog.at_level("WARNING"):
        collect.run_quality_audits(cfg=cfg, audit_fns=[("u", lambda: doc)])
    assert any("no email sent" in r.message.lower() for r in caplog.records)


# --- read-only / idempotency contract ---------------------------------------

def _digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_audits_never_mutate_source_stores(tmp_path):
    data = tmp_path / "data"
    p_price = data / "stocks" / "AAA.parquet"
    p_macro = data / "fred" / "M.parquet"
    _write(_ohlcv(), p_price)
    _write(_monthly(np.linspace(100.0, 200.0, 120)), p_macro)
    before = {p_price: _digest(p_price), p_macro: _digest(p_macro)}

    audit_prices.run(stores=[{"group": "stocks"}], data_dir=data, out_dir=tmp_path / "q")
    audit_macro.run(groups=["fred"], data_dir=data, baseline_dir=tmp_path / "bl",
                    out_dir=tmp_path / "q", asof=date(2025, 3, 1))
    for p, h in before.items():
        assert _digest(p) == h, f"audit mutated source store {p}"
