"""HK stock-conviction engine tests — the unique system (engine/hk_stock_signals.py)
and the southbound smart-money feed (engine/hk_southbound_stocks.py).

All synthetic (no network / disk): HK has NO selection alpha, so these verify the
HONEST mechanics — southbound accumulation z-scores cleanly, the A/H value tilt rewards
a cheap-and-widening H line, beta-neutral RS strips the beta the HK cross-section is
dominated by, and the regime master switch re-weights the fused edge."""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from engine import hk_southbound_stocks as sb  # noqa: E402
from engine import hk_stock_signals as hs  # noqa: E402


# ── southbound smart-money feed ──────────────────────────────────────────────
def _snap(n: int = 12):
    """Synthetic southbound cross-section: name i accumulates monotonically more (higher
    add_amp + 5/10d holding-value growth) so the accumulation z is monotonic in i."""
    idx = [f"{1000 + i:04d}.HK" for i in range(n)]
    hold = np.linspace(2e9, 2e10, n)
    chg5 = np.linspace(-0.15, 0.20, n) * hold        # abs HKD change, monotonic
    df = pd.DataFrame({
        "name": [f"N{i}" for i in range(n)],
        "hold_mktcap": hold,
        "hold_shares": np.linspace(1e8, 1e9, n),
        "own_pct": np.linspace(2.0, 30.0, n),
        "free_pct": np.linspace(3.0, 40.0, n),
        "chg5_v": chg5,
        "chg10_v": chg5 * 1.5,
        "add_amp": np.linspace(-2.0, 4.0, n),
        "close": np.linspace(5, 50, n),
    }, index=idx)
    df.index.name = "ticker"
    df["date"] = pd.Timestamp("2026-06-18")
    return df


def test_normalize_ticker():
    assert sb._normalize("00700.HK") == "0700.HK"
    assert sb._normalize("01347.HK") == "1347.HK"
    assert sb._normalize("09988.HK") == "9988.HK"
    assert sb._normalize("BADCODE") is None
    assert sb._normalize("") is None


def test_value_pct_normalizes():
    hold = pd.Series([1.1e9, 2.2e9])
    chg = pd.Series([1e8, -2e8])
    pct = sb._value_pct(chg, hold)
    # +1e8 on a (1.1e9-1e8)=1.0e9 base => +10%
    assert abs(pct.iloc[0] - 10.0) < 0.5
    assert pct.iloc[1] < 0


def test_southbound_signal_monotone_and_labels():
    snap = _snap(12)
    sig = sb.signal(tickers=list(snap.index), snap=snap)
    assert len(sig) == 12
    zs = [sig[t]["accum_z"] for t in snap.index]
    # accumulation z rises monotonically with the synthetic (allowing tiny float wobble)
    assert zs[-1] > zs[0] + 1.0
    assert sig[snap.index[-1]]["label"] == "accumulating"
    assert sig[snap.index[0]]["label"] == "distributing"
    # own_pct passes through
    assert sig[snap.index[-1]]["own_pct"] == 30.0


def test_southbound_signal_needs_min_names():
    assert sb.signal(tickers=["0001.HK"], snap=_snap(4)) == {}   # <8 after filter


def test_market_summary_ranks_and_sizes():
    snap = _snap(14)
    ms = sb.market_summary(snap=snap, min_hold_b=0.5)
    assert ms is not None
    # the most-accumulating name leads "buying"; the most-distributing leads "selling"
    assert ms["buying"][0]["chg5_pct"] > 0
    assert ms["selling"][0]["chg5_pct"] < 0
    assert ms["buying"][0]["chg5_pct"] >= ms["buying"][-1]["chg5_pct"]


# ── beta-neutral relative strength ───────────────────────────────────────────
def test_beta_neutral_rs_strips_beta():
    """A high-beta name in a market rip must NOT out-rank a true idiosyncratic leader
    once beta is stripped — the whole point (it de-thrones the raw-RS outlier). Needs
    >=8 names for a cross-sectional z."""
    n = 120
    dates = pd.bdate_range("2025-01-01", periods=n)
    f = pd.Series(np.full(n, 0.004), index=dates)          # steady up-market
    cols, betas = {}, {}
    # 8 filler names: pure beta spread 0.6..1.6, no idiosyncratic drift
    for i, b in enumerate(np.linspace(0.6, 1.6, 8)):
        t = f"F{i}"
        betas[t] = float(b)
        cols[t] = 100 * np.cumprod(1 + b * f.values)
    betas["HIBETA"] = 2.0
    cols["HIBETA"] = 100 * np.cumprod(1 + 2.0 * f.values)            # pure beta, no idio
    betas["LEADER"] = 0.5
    cols["LEADER"] = 100 * np.cumprod(1 + 0.5 * f.values + 0.004)    # real idio drift
    closes = pd.DataFrame(cols, index=dates)
    z = hs.beta_neutral_rs(closes, f, betas, win=63)
    assert z  # non-empty
    # LEADER (idio drift) beats HIBETA (pure beta) AFTER stripping beta — and HIBETA,
    # despite the biggest raw return, is NOT the top residual leader.
    assert z["LEADER"] > z["HIBETA"]
    assert z["LEADER"] == max(z.values())


# ── A/H value ────────────────────────────────────────────────────────────────
def test_ah_value_rewards_cheap_widening_h():
    out = hs.ah_value_signal({
        "CHEAP.HK": {"pctile": 90, "chg_1y": 8.0, "premium_pct": 40.0, "a": "X.SS"},
        "RICH.HK": {"pctile": 8, "chg_1y": -10.0, "premium_pct": 2.0, "a": "Y.SS"},
    })
    assert out["CHEAP.HK"]["z"] > 0.4 and out["CHEAP.HK"]["cheap"] is True
    assert out["RICH.HK"]["z"] < 0 and out["RICH.HK"]["cheap"] is False


# ── the fused edge + regime master switch ────────────────────────────────────
def test_hk_edge_regime_reweights():
    """Risk-off must up-weight southbound + A/H value vs Risk-on (the master switch)."""
    tickers = ["A.HK"]
    southbound = {"A.HK": {"accum_z": 2.0}}
    ah_value = {"A.HK": {"z": 1.0}}
    bnrs = {"A.HK": -1.0}                       # RS drags
    betas_pt = {"A.HK": {"role": "cushion", "tilt": "favored"}}
    off = hs.hk_edge(tickers, southbound=southbound, ah_value=ah_value, bnrs=bnrs,
                     betas_pt=betas_pt, risk_state="Risk-off")
    on = hs.hk_edge(tickers, southbound=southbound, ah_value=ah_value, bnrs=bnrs,
                    betas_pt={"A.HK": {"role": "cushion", "tilt": "lag"}}, risk_state="Risk-on")
    # flow + value dominate in risk-off (cushion favored) -> higher fused edge than risk-on
    assert off["A.HK"]["z"] > on["A.HK"]["z"]
    assert any(b["leg"] == "southbound" for b in off["A.HK"]["basis"])


def test_hk_edge_renormalizes_and_handles_missing():
    # a name with ONLY southbound still scores positive (renormalized), lightly haircut by
    # the single-leg confidence floor (so it can't score like a multi-leg conviction name).
    out = hs.hk_edge(["A.HK"], southbound={"A.HK": {"accum_z": 1.5}}, ah_value={},
                     bnrs={}, betas_pt={}, risk_state="neutral")
    assert 1.0 < out["A.HK"]["z"] <= 1.5
    # a name with NO HK-native leg drops out (no fake zero)
    assert hs.hk_edge(["Z.HK"], southbound={}, ah_value={}, bnrs={}, betas_pt={},
                      risk_state="neutral") == {}


def test_regime_fit_and_calm_and_overlay():
    assert hs._regime_fit_z("amplifier", "favored") == 0.8
    assert hs._regime_fit_z("amplifier", "exposed") == -0.8
    assert hs._regime_fit_z(None, None) is None
    assert hs.hk_calm("Risk-on") > hs.hk_calm("Risk-off")
    off = hs.hk_risk_overlay("Risk-off")
    on = hs.hk_risk_overlay("Risk-on")
    assert off["stress"] > on["stress"]
    # a high drawdown band escalates stress + records a driver
    esc = hs.hk_risk_overlay("neutral", vhsi_pctile=10, drawdown_band="high")
    assert esc["stress"] >= 0.6 and any("drawdown" in d for d in (esc["drivers"] or []))


def test_lottery_map():
    dates = pd.bdate_range("2026-01-01", periods=30)
    s = np.full(30, 100.0)
    s[-3] = 130.0   # +30% one-day spike in the last 21 sessions
    closes = pd.DataFrame({"SPIKE.HK": s, "CALM.HK": np.linspace(100, 101, 30)}, index=dates)
    lm = hs.lottery_map(closes)
    assert lm["SPIKE.HK"] >= 25.0
    assert lm["CALM.HK"] < 5.0


# ── W4 screen-tier re-weight toward phase-0 evidence (reports/hkca-h3-phase0.md +
#    hk-southbound-h1-phase0.md) ────────────────────────────────────────────────
def test_edge_weights_tilted_toward_ah_value_away_from_southbound():
    """The W4 re-weight tilts every regime row toward ahv (H3 near-GO) and away from sb
    (H1 Δ-ranker NO-GO) vs the pre-W4 baseline, while keeping regime-conditionality
    (bnrs still leads risk-on) and the ~1.0 row sums."""
    base = {  # pre-W4 baseline, recorded in the _EDGE_W comment block
        "Risk-off": {"sb": 0.38, "ahv": 0.28, "bnrs": 0.10, "fit": 0.24},
        "Risk-on":  {"sb": 0.30, "ahv": 0.14, "bnrs": 0.36, "fit": 0.20},
        "neutral":  {"sb": 0.34, "ahv": 0.22, "bnrs": 0.22, "fit": 0.22},
    }
    for row, b in base.items():
        w = hs._EDGE_W[row]
        assert w["ahv"] > b["ahv"], f"{row}: ahv must be up-weighted (H3 near-GO)"
        assert w["sb"] < b["sb"], f"{row}: sb must be down-weighted (H1 Δ-ranker NO-GO)"
        assert abs(sum(w.values()) - 1.0) < 1e-9, f"{row}: weights must still sum to 1"
    # regime character preserved: risk-on still leads with beta-neutral RS; risk-off leads
    # with the two structural flow/value legs (sb+ahv) over RS.
    assert hs._EDGE_W["Risk-on"]["bnrs"] == max(hs._EDGE_W["Risk-on"].values())
    ro = hs._EDGE_W["Risk-off"]
    assert ro["sb"] + ro["ahv"] > ro["bnrs"] + ro["fit"]


def test_edge_ah_value_now_outweighs_sb_pressure_in_riskoff():
    """A concrete effect of the tilt: with equal-magnitude flow and value legs, the fused
    edge now leans on the A/H value leg more than the pre-W4 weights did."""
    tks = ["V.HK"]
    # value-strong, flow-weak name: the tilt should let value carry more of the edge.
    out = hs.hk_edge(tks, southbound={"V.HK": {"accum_z": 0.5}},
                     ah_value={"V.HK": {"z": 2.0}}, bnrs={}, betas_pt={},
                     risk_state="Risk-off")
    # ahv .32 * 2.0 + sb .34 * 0.5  over (.32+.34) => (0.64 + 0.17)/0.66 ~ 1.23, clipped ok
    z = out["V.HK"]["z"]
    assert z is not None and z > 1.0                       # value-led edge stays strong-positive
    assert any(b["leg"] == "ah_value" for b in out["V.HK"]["basis"])


# ── H2a SFC reportable short-position context (ACCRUE) ────────────────────────
def _short_panel(ticker: str, dtc_series: list[float], vol: float = 1_000_000.0):
    """Build a weekly SFC positions frame + a daily volume series such that days-to-cover
    (shorted_shares / mean(volume,63)) equals the requested ``dtc_series`` per week."""
    weeks = pd.bdate_range("2024-01-05", periods=len(dtc_series), freq="W-FRI")
    rows = [{"date": w, "ticker": ticker, "shorted_shares": d * vol}
            for w, d in zip(weeks, dtc_series)]
    pos = pd.DataFrame(rows)
    # flat daily volume so the 63d ADV == vol on every SFC date
    vidx = pd.bdate_range("2023-06-01", weeks[-1])
    volume = {ticker: pd.Series(vol, index=vidx)}
    return pos, volume, weeks[-1]


def test_sfc_short_pressure_percentile_and_freshness():
    # a rising short book: the latest week is the highest days-to-cover -> ~P100
    dtc = list(np.linspace(1.0, 6.0, 60))
    pos, vol, last_wk = _short_panel("0001.HK", dtc)
    out = hs.sfc_short_pressure(pos, vol, asof=last_wk)
    assert "0001.HK" in out
    r = out["0001.HK"]
    assert r["pctile"] >= 95                     # latest is the deepest short book
    assert abs(r["dtc"] - 6.0) < 0.2             # days-to-cover ~ latest ratio
    assert r["as_of"] == last_wk.strftime("%Y-%m-%d")


def test_sfc_short_pressure_freshness_guard_suppresses_stale():
    dtc = list(np.linspace(1.0, 6.0, 60))
    pos, vol, last_wk = _short_panel("0001.HK", dtc)
    # asof 40 calendar days after the last SFC week -> >12 trading days stale -> suppressed
    stale_asof = last_wk + pd.Timedelta(days=40)
    assert hs.sfc_short_pressure(pos, vol, asof=stale_asof) == {}


def test_sfc_short_pressure_needs_min_history_and_volume():
    # <52 weeks of history -> no percentile
    dtc = [2.0] * 20
    pos, vol, last_wk = _short_panel("0001.HK", dtc)
    assert hs.sfc_short_pressure(pos, vol, asof=last_wk) == {}
    # missing volume for the ticker -> dropped
    dtc = list(np.linspace(1.0, 6.0, 60))
    pos, _, last_wk = _short_panel("0001.HK", dtc)
    assert hs.sfc_short_pressure(pos, {}, asof=last_wk) == {}
    # missing/empty positions -> empty map
    assert hs.sfc_short_pressure(None, {"0001.HK": pd.Series([1, 2, 3])}) == {}
