"""Index dealer-gamma HISTORY reconstruction (roadmap P1.1b / scripts.build_index_gex_history)
+ the engine.market_gamma context upgrade.

Pins the four things the roadmap requires:
  1. greeks ⋈ oi join correctness on a synthetic fixture (keys, oi>0, T formula, iv units);
  2. the dealer-sign / net-GEX / regime convention is IDENTICAL to engine.gex_engine on a
     synthetic chain — a call-heavy chain is +GEX/long, a put-heavy one is -GEX, and the
     reconstruction summary equals compute_gex fed the same chain (no divergent basis);
  3. the overlap-audit helper runs and returns correlation + regime sign-agreement;
  4. engine.market_gamma.snapshot() falls back to the pre-upgrade current-day-only verdict
     when the reconstructed history store is absent, and attaches a context block when present.
"""
import numpy as np
import pandas as pd
import pytest

from engine.gex_engine import compute_gex
import scripts.build_index_gex_history as B
from scripts.build_index_gex_history import audit_overlap


# ---------------------------------------------------------------- fixtures --

def _greeks_oi_fixture(tmp_path, root="TST", year=2020):
    """Write a minimal greeks + oi parquet pair mirroring the ThetaData store schema,
    then point the builder at tmp_path. One trading date, a small call/put chain."""
    date = pd.Timestamp(f"{year}-03-16")
    exp = pd.Timestamp(f"{year}-04-17")
    spot = 100.0
    strikes = [90.0, 95.0, 100.0, 105.0, 110.0]
    rows = []
    for k in strikes:
        for right in ("C", "P"):
            rows.append(dict(root=root, expiration=exp, strike=k, right=right,
                             date=date, underlying_price=spot, implied_vol=0.20))
    greeks = pd.DataFrame(rows)
    # oi: call-heavy (calls carry more OI than puts) + one zero-OI row that must drop.
    oi_rows = []
    for k in strikes:
        oi_rows.append(dict(root=root, expiration=exp, strike=k, right="C",
                            date=date, open_interest=1000))
        oi_rows.append(dict(root=root, expiration=exp, strike=k, right="P",
                            date=date, open_interest=200))
    oi_rows.append(dict(root=root, expiration=exp, strike=999.0, right="C",
                        date=date, open_interest=0))  # zero-OI -> dropped
    oi = pd.DataFrame(oi_rows)

    (tmp_path / "greeks" / root).mkdir(parents=True)
    (tmp_path / "oi" / root).mkdir(parents=True)
    greeks.to_parquet(tmp_path / "greeks" / root / f"{year}.parquet")
    oi.to_parquet(tmp_path / "oi" / root / f"{year}.parquet")
    return date, exp, spot, strikes


# ------------------------------------------------------------ join + parse --

def test_read_year_chain_join_correctness(tmp_path, monkeypatch):
    date, exp, spot, strikes = _greeks_oi_fixture(tmp_path)
    monkeypatch.setattr(B, "THETA_ROOT", tmp_path)
    ch = B._read_year_chain("TST", 2020)
    assert ch is not None
    # 5 strikes x 2 rights = 10 joined rows; the zero-OI row is dropped.
    assert len(ch) == 10
    assert set(ch.columns) >= {"date", "expiry", "K", "T", "iv", "oi", "is_call", "underlying_price"}
    # T = calendar days / 365 (matches collectors/polygon_options.parse_chain exactly).
    assert ch["T"].round(6).eq(round((exp - date).days / 365.0, 6)).all()
    assert ch["iv"].eq(0.20).all()                       # decimal iv preserved
    assert ch["is_call"].sum() == 5 and (~ch["is_call"]).sum() == 5
    assert ch["oi"].min() > 0                            # zero-OI purged


# --------------------------------------------- dealer-sign / regime parity --

def _synth_chain(call_oi, put_oi, spot=100.0):
    exp = pd.Timestamp("2020-04-17")
    rows = []
    for k in [90.0, 95.0, 100.0, 105.0, 110.0]:
        rows.append(dict(K=k, T=32 / 365.0, iv=0.20, oi=float(call_oi), is_call=True, expiry=exp))
        rows.append(dict(K=k, T=32 / 365.0, iv=0.20, oi=float(put_oi), is_call=False, expiry=exp))
    return pd.DataFrame(rows)


def test_summary_equals_compute_gex_exactly(tmp_path, monkeypatch):
    """The reconstruction summary for a day MUST equal engine.gex_engine.compute_gex fed
    the same chain — same dealer sign (call +1 / put -1), same net-GEX $, same flip/regime.
    This is the anti-divergence guarantee: no independent GEX math in the reconstructor."""
    _greeks_oi_fixture(tmp_path)
    monkeypatch.setattr(B, "THETA_ROOT", tmp_path)
    ch = B._read_year_chain("TST", 2020)
    day = ch[ch["date"] == ch["date"].max()]
    got = B._summarise_day(day, "TST")

    spot = float(day["underlying_price"].iloc[0])
    ref = compute_gex(day[["K", "T", "iv", "oi", "is_call", "expiry"]].copy(), spot, symbol="TST")
    for key in ("net_gex_bn", "gamma_flip", "gamma_regime", "n_strikes", "spot", "max_pain"):
        assert got[key] == ref[key] or (
            isinstance(got[key], float) and np.isclose(got[key], ref[key])), key
    assert got["reconstructed"] is True


def test_dealer_sign_call_heavy_positive_put_heavy_negative():
    """Pin the dealer long-call/short-put convention: call-dominated OI -> net GEX > 0
    (dealers net long gamma); put-dominated OI -> net GEX < 0 — same as gex_engine."""
    call_heavy = compute_gex(_synth_chain(call_oi=5000, put_oi=100), 100.0, symbol="TST")
    put_heavy = compute_gex(_synth_chain(call_oi=100, put_oi=5000), 100.0, symbol="TST")
    assert call_heavy["net_gex_bn"] > 0
    assert put_heavy["net_gex_bn"] < 0


# ------------------------------------------------------------ overlap audit --

def test_overlap_audit_runs_and_reports_agreement():
    """The blocking overlap audit (reconstructed vs live polygon summary) computes a
    net-GEX correlation and a regime sign-agreement rate. Feed two aligned frames."""
    idx = pd.to_datetime(["2026-06-15", "2026-06-16", "2026-06-17", "2026-06-18"])
    recon = pd.DataFrame({"net_gex_bn": [1.0, -0.5, -0.2, 0.8],
                          "gamma_regime": ["long", "short", "short", "long"]}, index=idx)
    live = pd.DataFrame({"net_gex_bn": [0.9, -0.6, -0.1, 0.7],
                         "gamma_regime": ["long", "short", "long", "long"]}, index=idx)
    rep = audit_overlap(recon, live)
    assert rep["n_overlap"] == 4
    assert -1.0 <= rep["net_gex_corr_raw"] <= 1.0
    assert rep["regime_agreement_raw"] == pytest.approx(0.75)  # 3/4 regimes agree


def test_same_spot_filter_isolates_timing_matched_rows():
    """Same-spot filter: rows where reconstructed and live spot differ >= 0.5% are
    excluded from net_gex_corr_same_spot.  This separates T-1-lag mismatch from
    model mismatch.  Synthetic: two timing-matched rows (high corr) + one mismatched
    row (spot shifts by >0.5%) that would drag the raw corr down."""
    idx = pd.to_datetime(["2026-06-15", "2026-06-16", "2026-06-17"])
    # Reconstructed (T+0 same-session spot)
    recon = pd.DataFrame({
        "net_gex_bn": [5.0, -3.0, 8.0],
        "spot":        [100.0, 101.0, 102.0],  # spot_r
        "gamma_regime": ["long", "short", "long"],
    }, index=idx)
    # Live (T-1 settlement): first two rows match spot; third shifts by >1% (timing lag)
    live = pd.DataFrame({
        "net_gex_bn": [4.8, -2.9, 2.0],   # last row is divergent (timing lag)
        "spot":        [100.05, 101.02, 99.5],  # third spot differs >0.5% from 102.0
        "gamma_regime": ["long", "short", "short"],
    }, index=idx)
    rep = audit_overlap(recon, live)
    assert rep["n_overlap"] == 3
    # Same-spot filter: only first two rows pass (|102-99.5|/102 ~2.45% > 0.5%)
    assert rep["n_same_spot"] == 2
    # Same-spot corr should be near-perfect on the two matched rows
    assert rep["net_gex_corr_same_spot"] is not None
    assert rep["net_gex_corr_same_spot"] > 0.99
    # Regime agreement on same-spot rows: both are "long"/"short" matching -> 1.0
    assert rep["regime_agreement_same_spot"] == pytest.approx(1.0)
    # Raw corr includes the bad row and is lower
    assert rep["net_gex_corr_raw"] < rep["net_gex_corr_same_spot"]


# ---------------------------------------------- market_gamma context upgrade --

def _cboe_gex(net_gex_bn=17.7, flip=8100, spot=7394.3, svf=-8.71):
    return pd.DataFrame({"net_gex_bn": [net_gex_bn], "flip_strike": [flip],
                         "spot": [spot], "spot_vs_flip_pct": [svf]},
                        index=pd.to_datetime(["2026-06-13"]))


def test_snapshot_falls_back_when_history_absent(monkeypatch):
    """No reconstructed store -> context is None and the verdict is otherwise the
    pre-upgrade current-day-only object (regime/flip/net_gex intact)."""
    from engine import market_gamma

    def fake_read(group, name):
        if group == "cboe":
            return _cboe_gex()
        return None  # index_gex_history absent

    monkeypatch.setattr(market_gamma.store, "read", fake_read)
    mg = market_gamma.snapshot()
    assert mg is not None
    assert mg["regime"] == "short" and mg["flip"] == 8100
    assert mg["context"] is None


def test_snapshot_attaches_context_when_history_present(monkeypatch):
    """With a reconstructed SPY history, snapshot() attaches net-GEX percentile +
    standing-regime persistence WITHOUT changing the current-day regime source."""
    from engine import market_gamma

    # SIX SESSIONS. This fixture used to end on 2026-06-13, a SATURDAY, so
    # _history_context saw 6 rows where the exchange calendar has 5 — and market_gamma
    # now session-filters the history (the #3721 weekend-row class: `.iloc[-1]` is the
    # standing reading and the percentile below is an own-history distribution, so both
    # must be session-true). Mon 06-08 → Mon 06-15 gives six real sessions and keeps the
    # last three 'short' (persistence 3) the assertions below depend on.
    hist = pd.DataFrame(
        {"net_gex_bn": [50.0, 40.0, 30.0, -5.0, -8.0, -8.5],
         "gamma_regime": ["long", "long", "long", "short", "short", "short"]},
        index=pd.to_datetime(["2026-06-08", "2026-06-09", "2026-06-10",
                              "2026-06-11", "2026-06-12", "2026-06-15"]))

    def fake_read(group, name):
        if group == "cboe":
            return _cboe_gex(net_gex_bn=17.7, svf=-8.71)  # current: short
        if group == "index_gex_history":
            return hist
        return None

    monkeypatch.setattr(market_gamma.store, "read", fake_read)
    mg = market_gamma.snapshot()
    ctx = mg["context"]
    assert ctx is not None and ctx["reconstructed"] is True
    assert ctx["n_days"] == 6
    # own-history percentile of the reconstructed latest (-8.5, the minimum) -> ~16.7 pct
    assert ctx["net_gex_latest_bn"] == -8.5
    assert 0.0 <= ctx["net_gex_pctile"] <= 100.0
    # reconstructed last 3 days are 'short' -> persistence 3; current-day (SPX) is 'short' too
    assert ctx["recon_regime_last"] == "short"
    assert ctx["regime_persistence_days"] == 3
    assert ctx["regime_agrees_current"] is True
