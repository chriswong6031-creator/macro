"""Tests for the sector-ETF accumulation engine (engine/holdings_signals.py).

The math core `decompose` is pure and tested directly with engineered Series; the
store-backed readers and the alert rule are tested by swapping in a fake
`store.read` / a fake `all_accumulation_signals` (save-and-restore so the module
stays runnable as a plain script, matching tests/test_alerts.py style)."""
from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from engine import holdings_signals as hs  # noqa: E402
from engine.alerts import sector_holdings_accumulation  # noqa: E402
from lib import store  # noqa: E402


# --- pure decompose -------------------------------------------------------------

def _decomp_one(w0v, w1v, r_stock, r_fund):
    w0 = pd.Series({"AAA": w0v})
    w1 = pd.Series({"AAA": w1v})
    rs = pd.Series({"AAA": r_stock})
    return hs.decompose(w0, w1, rs, r_fund).loc["AAA"]


def test_decompose_price_only_zero_residual() -> None:
    # weight that rose EXACTLY in line with price -> residual ~ 0
    w_price = 10.0 * (1 + 0.20) / (1 + 0.05)
    row = _decomp_one(10.0, w_price, 0.20, 0.05)
    assert abs(row["active_change"]) < 1e-6, row["active_change"]
    assert abs(row["raw_change"] - (w_price - 10.0)) < 1e-3  # raw still reflects the move (4dp rounding)


def test_decompose_accumulation_positive_residual() -> None:
    w_price = 10.0 * (1 + 0.20) / (1 + 0.05)
    row = _decomp_one(10.0, w_price + 0.5, 0.20, 0.05)  # 0.5pp ON TOP of price drift
    assert row["active_change"] > 0
    assert abs(row["active_change"] - 0.5) < 1e-6


def test_decompose_distribution_negative_residual() -> None:
    w_price = 10.0 * (1 + 0.20) / (1 + 0.05)
    row = _decomp_one(10.0, w_price - 0.5, 0.20, 0.05)
    assert row["active_change"] < 0


def test_decompose_no_common_tickers_empty() -> None:
    out = hs.decompose(pd.Series({"AAA": 10.0}), pd.Series({"BBB": 5.0}),
                       pd.Series({"AAA": 0.1}), 0.0)
    assert out.empty and list(out.columns) == hs.DECOMP_COLS


# --- store-backed readers (fake store.read) -------------------------------------

def _two_snapshot_holdings() -> pd.DataFrame:
    idx = pd.to_datetime(["2026-06-06", "2026-06-06", "2026-06-11", "2026-06-11"])
    return pd.DataFrame({
        "ticker": ["AAA", "BBB", "AAA", "BBB"],
        "name": ["Alpha", "Beta", "Alpha", "Beta"],
        "weight_pct": [10.0, 8.0, 12.0, 7.5],   # AAA accumulated, BBB trimmed
        "rank": [1, 2, 1, 2],
    }, index=idx)


def _flat_close() -> pd.Series:
    # both fund and stocks return +1% over the window -> all drift is "price"
    return pd.Series([100.0, 101.0], index=pd.to_datetime(["2026-06-06", "2026-06-11"]))


def _install_fake_store(holdings: pd.DataFrame):
    orig = store.read

    def fake(group: str, name: str):
        if group == "sector_holdings":
            return holdings.copy()
        if group in ("yahoo", "stocks"):
            return pd.DataFrame({"close": _flat_close(), "high": _flat_close()})
        if group == "flows":
            return pd.DataFrame({"aum_mn": [1000.0]}, index=pd.to_datetime(["2026-06-10"]))
        return None

    store.read = fake
    return orig


def test_weight_decomposition_none_on_single_snapshot() -> None:
    one = _two_snapshot_holdings().iloc[2:]  # only the 2026-06-11 rows
    orig = _install_fake_store(one)
    try:
        assert hs.weight_decomposition("XLK") is None
    finally:
        store.read = orig


def test_weight_decomposition_isolates_accumulation() -> None:
    orig = _install_fake_store(_two_snapshot_holdings())
    try:
        dec = hs.weight_decomposition("XLK")
        assert dec is not None
        # AAA gained 2pp while moving exactly with the fund -> ~all of it is active
        assert abs(dec.loc["AAA", "active_change"] - 2.0) < 1e-6
        assert dec.loc["BBB", "active_change"] < 0           # trimmed
        sigs = hs.accumulation_signals("XLK")
        by_t = {s["ticker"]: s for s in sigs}
        assert by_t["AAA"]["direction"] == "accumulating"
        assert by_t["BBB"]["direction"] == "distributing"
        assert by_t["AAA"]["ladder"] is None                 # 2-row series < min history
    finally:
        store.read = orig


# --- alert rule (fake all_accumulation_signals) ---------------------------------

def _sig(active_change: float, confirmed: bool = False) -> dict:
    return {"fund": "XLK", "ticker": "AAA", "name": "Alpha",
            "active_change": active_change, "direction":
            "accumulating" if active_change > 0 else "distributing",
            "est_flow_mn": 400.0, "t0": "2026-06-06", "t1": "2026-06-11",
            "ladder": {"label": "BUY ZONE", "action": "BUY"}, "confirmed": confirmed}


def _patch_signals(sigs: list[dict]):
    orig = hs.all_accumulation_signals
    hs.all_accumulation_signals = lambda: sigs
    return orig


def test_alert_fires_above_threshold() -> None:
    orig = _patch_signals([_sig(0.40, confirmed=True)])
    try:
        out = sector_holdings_accumulation(None, pd.DataFrame())
        assert len(out) == 1
        a = out[0]
        assert a.severity == "warn" and "+0.40pp" in a.message and "XLK" in a.message
        assert "BUY ZONE" in a.message
    finally:
        hs.all_accumulation_signals = orig


def test_alert_silent_below_threshold() -> None:
    orig = _patch_signals([_sig(0.10)])   # below default alert_pp (0.25)
    try:
        assert sector_holdings_accumulation(None, pd.DataFrame()) == []
    finally:
        hs.all_accumulation_signals = orig


# --- Phase 2: ETF universe (share-based active decisions) -----------------------

def test_etf_normalize_drops_cash_and_parses() -> None:
    from collectors.etf_holdings import EtfHoldingsAdapter
    df = pd.DataFrame({"ticker": ["NVDA", "-", "AAPL"],
                       "name": ["NVIDIA", "CASH", "APPLE"],
                       "weight": ["10.5", "2.0", "8.0"],
                       "shares_held": ["1,000", "5", "2,000"]})
    out = EtfHoldingsAdapter._normalize(df, "XYZ", "2026-06-11",
                                        wcol="weight", scol="shares_held")
    assert list(out["ticker"]) == ["NVDA", "AAPL"]                 # '-' cash row dropped
    assert out.loc[out.ticker == "NVDA", "shares"].iloc[0] == 1000
    assert out.loc[out.ticker == "NVDA", "weight_pct"].iloc[0] == 10.5
    assert (out["as_of"] == "2026-06-11").all()


def test_etf_active_decision_flags_accumulation() -> None:
    import tempfile
    parent = Path(tempfile.mkdtemp())
    d = parent / "FAKE"
    d.mkdir()
    base = pd.DataFrame({"ticker": ["AAA", "BBB", "CCC"], "name": ["A", "B", "C"],
                         "weight_pct": [5.0, 4.0, 3.0], "shares": [100, 100, 100]})
    t0 = base.copy(); t0["as_of"] = "2026-06-06"
    t1 = base.copy(); t1["shares"] = [140, 100, 100]; t1["as_of"] = "2026-06-11"
    t0.to_parquet(d / "2026-06-06.parquet")
    t1.to_parquet(d / "2026-06-11.parquet")
    sigs = hs.etf_signals("FAKE", base_dir=parent, is_active=True, meta={"name": "Fake"})
    by = {s["ticker"]: s for s in sigs}
    # AAA grew far beyond the fund's SO drift -> flagged accumulation; BBB/CCC below thresh
    assert "AAA" in by and by["AAA"]["direction"] == "accumulating"
    assert by["AAA"]["active_chg_pct"] > 15
    assert "BBB" not in by and "CCC" not in by


def test_volume_surge_detects_and_degrades() -> None:
    idx = pd.bdate_range("2026-01-01", periods=30)
    vol = pd.Series([1e6] * 25 + [3e6] * 5, index=idx)
    frame = pd.DataFrame({"close": 1.0, "volume": vol}, index=idx)
    orig = store.read
    store.read = lambda g, n: frame if g == "stocks" else orig(g, n)
    try:
        vs = hs.volume_surge("ZZZ")
        assert vs is not None and vs["surging"] is True and vs["ratio"] >= 1.5
    finally:
        store.read = orig
    store.read = lambda g, n: pd.DataFrame({"close": [1, 2, 3]})   # no volume column
    try:
        assert hs.volume_surge("ZZZ") is None
    finally:
        store.read = orig


# --- data hygiene: non-equity predicate + denominator guard ---------------------

def test_is_non_equity_holding() -> None:
    from collectors.holdings import is_non_equity_holding
    # cash / FX / equivalents / blank => non-equity
    assert is_non_equity_holding("USD", "CASH & EQUIVALENTS")
    assert is_non_equity_holding("EUR", "EURO")
    assert is_non_equity_holding("-", "")
    assert is_non_equity_holding("XYZ", "Cash&Other")
    assert is_non_equity_holding("", "")
    # real equities (incl. foreign-listed) => kept
    assert not is_non_equity_holding("NVDA", "NVIDIA CORP")
    assert not is_non_equity_holding("000720 KS", "HYUNDAI ENGINEERING & CONST")
    assert not is_non_equity_holding("FF", "FutureFuel Corp")   # 'future' substring not flagged


def test_active_changes_dir_weeds_cash_and_tiny_base() -> None:
    import tempfile
    from collectors.holdings import active_changes_dir
    d = Path(tempfile.mkdtemp()) / "FUND"
    d.mkdir()
    # BALLAST keeps the SO ratio ~1 so AAPL's real add stands out; USD is a cash
    # line (dropped by predicate); ZZZZ is a tiny placeholder contra-line whose
    # near-zero base would otherwise explode the %.
    cols = {"name": ["Ballast", "Apple", "Cash & Equivalents", "Contra"]}
    t0 = pd.DataFrame({"ticker": ["BALLAST", "AAPL", "USD", "ZZZZ"],
                       "shares": [10_000_000, 10_000, 5, 1], **cols})
    t1 = pd.DataFrame({"ticker": ["BALLAST", "AAPL", "USD", "ZZZZ"],
                       "shares": [10_000_000, 15_000, 9_999_999, 80], **cols})
    t0.to_parquet(d / "2026-06-06.parquet")
    t1.to_parquet(d / "2026-06-11.parquet")
    out = active_changes_dir(d, 5)
    assert out is not None
    assert "USD" not in out.index            # cash line dropped by the predicate
    assert "ZZZZ" not in out.index           # tiny base dropped by min_base_frac
    assert "AAPL" in out.index               # real accumulation survives
    assert 40 < out.loc["AAPL", "active_chg_pct"] < 60   # ~+49%, NOT an explosion
    assert out["active_chg_pct"].abs().max() < 1000       # nothing blows up


def test_etf_signals_conviction_ranks_weight_over_pct() -> None:
    import tempfile
    parent = Path(tempfile.mkdtemp())
    d = parent / "FAKE2"
    d.mkdir()
    # BIG: 5%-weight name, manager adds ~20%; TINY: 0.2%-weight name that DOUBLES.
    # TINY's share % is far bigger, but conviction (pp of fund weight committed)
    # must rank BIG first — the user's "0.1%->0.2% double isn't significant".
    base_cols = {"name": ["Ballast", "Big Co", "Tiny Co"]}
    t0 = pd.DataFrame({"ticker": ["BALLAST", "BIG", "TINY"],
                       "weight_pct": [50.0, 5.0, 0.20],
                       "shares": [1_000_000, 1000, 100], **base_cols})
    t1 = pd.DataFrame({"ticker": ["BALLAST", "BIG", "TINY"],
                       "weight_pct": [50.0, 5.0, 0.20],
                       "shares": [1_000_000, 1200, 200], **base_cols})
    t0.to_parquet(d / "2026-06-06.parquet")
    t1.to_parquet(d / "2026-06-11.parquet")
    sigs = hs.etf_signals("FAKE2", base_dir=parent, is_active=True,
                          meta={"name": "Fake", "category": "Test"})
    by = {s["ticker"]: s for s in sigs}
    assert "BIG" in by and "TINY" in by
    assert by["TINY"]["active_chg_pct"] > by["BIG"]["active_chg_pct"]   # raw % bigger for TINY
    assert by["BIG"]["conviction_pp"] > by["TINY"]["conviction_pp"]      # but conviction bigger for BIG
    acc = hs.split_by_conviction(sigs)["accumulation"]
    assert acc[0]["ticker"] == "BIG"                                     # ranked first


def test_etf_signals_flags_new_position() -> None:
    import tempfile
    parent = Path(tempfile.mkdtemp())
    d = parent / "FAKE3"
    d.mkdir()
    # NEW initiated this window (absent before): undefined % but a real 1.2%-weight
    # stake => flagged is_new, conviction = full weight, ranked highly.
    cols0 = {"name": ["Ballast", "Held"], "weight_pct": [60.0, 4.0]}
    t0 = pd.DataFrame({"ticker": ["BALLAST", "HELD"], "shares": [1_000_000, 5000], **cols0})
    cols1 = {"name": ["Ballast", "Held", "Initiated Co"], "weight_pct": [60.0, 4.0, 1.2]}
    t1 = pd.DataFrame({"ticker": ["BALLAST", "HELD", "NEWPOS"],
                       "shares": [1_000_000, 5000, 8000], **cols1})
    t0.to_parquet(d / "2026-06-06.parquet")
    t1.to_parquet(d / "2026-06-11.parquet")
    sigs = hs.etf_signals("FAKE3", base_dir=parent, is_active=False,
                          meta={"name": "Fake", "category": "Test"})
    by = {s["ticker"]: s for s in sigs}
    assert "NEWPOS" in by
    n = by["NEWPOS"]
    assert n["is_new"] is True and n["direction"] == "accumulating"
    assert n["active_chg_pct"] is None            # % undefined for a new position
    assert n["conviction_pp"] == 1.2              # full current weight committed


def test_etf_signals_flags_full_exit() -> None:
    import tempfile
    parent = Path(tempfile.mkdtemp())
    d = parent / "FAKE4"
    d.mkdir()
    # GONE held a window ago (3% weight), fully sold by now => strongest negative
    # signal: is_exit, conviction = -prior weight, name recovered from the prior snap.
    t0 = pd.DataFrame({"ticker": ["BALLAST", "GONE"], "name": ["Ballast", "Gone Co"],
                       "weight_pct": [60.0, 3.0], "shares": [1_000_000, 5000]})
    t1 = pd.DataFrame({"ticker": ["BALLAST"], "name": ["Ballast"],
                       "weight_pct": [60.0], "shares": [1_000_000]})
    t0.to_parquet(d / "2026-06-06.parquet")
    t1.to_parquet(d / "2026-06-11.parquet")
    sigs = hs.etf_signals("FAKE4", base_dir=parent, is_active=False,
                          meta={"name": "Fake", "category": "Test"})
    by = {s["ticker"]: s for s in sigs}
    assert "GONE" in by
    g = by["GONE"]
    assert g["is_exit"] is True and g["direction"] == "trimming"
    assert g["conviction_pp"] == -3.0            # full prior weight sold out
    assert g["weight_pct"] == 3.0 and g["name"] == "Gone Co"   # prior-snap name
    assert hs.split_by_conviction(sigs)["trims"][0]["ticker"] == "GONE"


def test_active_changes_dir_no_lifecycle_rows_by_default() -> None:
    # the alert path uses the default (no lifecycle rows) so its semantics are
    # unchanged — only the radar opts into new/exit via include_lifecycle=True.
    import tempfile
    from collectors.holdings import active_changes_dir
    d = Path(tempfile.mkdtemp()) / "FUND"
    d.mkdir()
    pd.DataFrame({"ticker": ["A", "GONE"], "name": ["A", "G"],
                  "shares": [1000, 500]}).to_parquet(d / "2026-06-06.parquet")
    pd.DataFrame({"ticker": ["A", "NEWP"], "name": ["A", "N"],
                  "shares": [1000, 500]}).to_parquet(d / "2026-06-11.parquet")
    base = active_changes_dir(d, 5)
    assert "GONE" not in base.index and "NEWP" not in base.index   # no lifecycle
    life = active_changes_dir(d, 5, include_lifecycle=True)
    assert "NEWP" in life.index and "GONE" in life.index


if __name__ == "__main__":
    for fn in [test_decompose_price_only_zero_residual,
               test_decompose_accumulation_positive_residual,
               test_decompose_distribution_negative_residual,
               test_decompose_no_common_tickers_empty,
               test_weight_decomposition_none_on_single_snapshot,
               test_weight_decomposition_isolates_accumulation,
               test_alert_fires_above_threshold,
               test_alert_silent_below_threshold,
               test_etf_normalize_drops_cash_and_parses,
               test_etf_active_decision_flags_accumulation,
               test_volume_surge_detects_and_degrades,
               test_is_non_equity_holding,
               test_active_changes_dir_weeds_cash_and_tiny_base,
               test_etf_signals_conviction_ranks_weight_over_pct,
               test_etf_signals_flags_new_position,
               test_etf_signals_flags_full_exit,
               test_active_changes_dir_no_lifecycle_rows_by_default]:
        fn()
        print(f"PASS {fn.__name__}")
    print("all holdings-signal tests passed")
