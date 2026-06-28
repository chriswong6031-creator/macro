"""Phase-2 sector-confluence backtest: the TWEAKS that make the theory work.

Phase-1 (_bt_sector_confluence) found: the signal has the right SIGN (fresh
3D turns-up precede positive excess, tops precede negative excess) but a naive
symmetric long/flat system only trades return for drawdown. This script tests
the levers:

  A) cross-sectional ROTATION spread (the real use-case: long fresh-turn sectors,
     avoid topping sectors) — the dashboard is a rotation tool, not a single-name
     timer.
  B) a 200-day TREND gate (only act on buys above the 200d, i.e. confirmed
     bottoming not falling-knife) — does it lift the edge?
  C) WEEKLY confirmation (3D buy AND weekly histogram not rolling over).
  D) a cleaner strategy: long on SETUP/BUY-up while the higher timeframe agrees,
     exit on SETUP-dn or confirmed top, with the trend gate.

Run:  python3 -m scripts._bt_sector_confluence2
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from engine.cycles import macd_parts, stoch_rsi
from engine.technicals import rsi
from scripts._bt_sector_confluence import _load, _to_3b, _signals_3b, SECTORS, BENCH, HORIZONS


def _weekly_hist_state(close: pd.Series) -> pd.Series:
    """Weekly MACD histogram rising? (reindexed to daily, ffill). Used as a
    higher-timeframe confirmer for 3D buys."""
    w = close.resample("W-FRI").last().dropna()
    h = macd_parts(w)["hist"]
    rising = (h > h.shift(1)).reindex(w.index)
    return rising.reindex(close.index, method="ffill").fillna(False)


def _enrich(t: str, spy: pd.Series) -> pd.DataFrame:
    daily = _load(t)
    s3 = _to_3b(daily)
    sigs = _signals_3b(s3["close"])
    # trend gate on the underlying daily, sampled at each 3B date
    sma200 = daily.rolling(200).mean()
    above200 = (daily > sma200).reindex(sigs.index, method="ffill")
    sma50 = daily.rolling(50).mean()
    above50 = (daily > sma50).reindex(sigs.index, method="ffill")
    wk_rising = _weekly_hist_state(daily).reindex(sigs.index, method="ffill")
    sigs = sigs.copy()
    sigs["above200"] = above200.fillna(False).values
    sigs["above50"] = above50.fillna(False).values
    sigs["wk_rising"] = wk_rising.fillna(False).values
    sigs["ticker"] = t
    # forward returns + excess
    didx = daily.index
    pos = didx.get_indexer(sigs.index)
    for h in HORIZONS:
        fwd = np.full(len(sigs), np.nan)
        exc = np.full(len(sigs), np.nan)
        for i, p in enumerate(pos):
            if p < 0 or p + h >= len(didx):
                continue
            d0, d1 = didx[p], didx[p + h]
            fwd[i] = daily.iloc[p + h] / daily.iloc[p] - 1
            if d0 in spy.index and d1 in spy.index:
                exc[i] = fwd[i] - (spy.loc[d1] / spy.loc[d0] - 1)
        sigs[f"fwd{h}"] = fwd
        sigs[f"exc{h}"] = exc
    return sigs


def _agg(label: str, sub: pd.DataFrame) -> dict:
    rec = {"signal": label, "n": int(len(sub))}
    for h in [10, 21, 63]:
        e = sub[f"exc{h}"].dropna()
        v = sub[f"fwd{h}"].dropna()
        rec[f"exc{h}"] = round(100 * e.mean(), 2) if len(e) else np.nan
        rec[f"hit{h}"] = round(100 * (v > 0).mean(), 0) if len(v) else np.nan
    return rec


def conditioned_study(R: pd.DataFrame) -> pd.DataFrame:
    buy_any = R["buy_full"] | R["buy_partial"]
    setup_up = R["setup_up"]
    recs = [
        _agg("baseline (all bars)", R),
        _agg("BUY any", R[buy_any]),
        _agg("BUY any + above200", R[buy_any & R["above200"]]),
        _agg("BUY any + below200 (knife)", R[buy_any & ~R["above200"]]),
        _agg("BUY any + wk_rising", R[buy_any & R["wk_rising"]]),
        _agg("BUY any + above200 + wk_rising", R[buy_any & R["above200"] & R["wk_rising"]]),
        _agg("BUY full + above200", R[R["buy_full"] & R["above200"]]),
        _agg("SETUP up", R[setup_up]),
        _agg("SETUP up + above200", R[setup_up & R["above200"]]),
        _agg("SETUP up + below200", R[setup_up & ~R["above200"]]),
        _agg("SETUP up + wk_rising", R[setup_up & R["wk_rising"]]),
        _agg("--- tops ---", R.iloc[:0]),
        _agg("SELL any", R[R["sell_full"] | R["sell_partial"]]),
        _agg("SELL partial", R[R["sell_partial"]]),
        _agg("top + extended (>70 rsi or stoch>80)",
             R[(R["sell_full"] | R["sell_partial"]) & ((R["rsi14"] > 70) | (R["stoch"] > 80))]),
        _agg("SETUP dn", R[R["setup_dn"]]),
        _agg("SETUP dn + below50", R[R["setup_dn"] & ~R["above50"]]),
    ]
    return pd.DataFrame(recs).set_index("signal")


def rotation_spread(R: pd.DataFrame) -> None:
    """Cross-sectional: on each 3B date, group sectors by signal bucket and
    measure the mean forward excess of the BUY-side vs the SELL-side bucket."""
    def bucket(row):
        if row["buy_full"] or (row.get("setup_up") and row["above200"]):
            return "buy_side"
        if row["sell_full"] or row["sell_partial"] or row["setup_dn"]:
            return "sell_side"
        return "neutral"
    R = R.copy()
    R["bucket"] = R.apply(bucket, axis=1)
    print("\nCross-sectional rotation buckets (forward EXCESS vs SPY, %):")
    g = R.groupby("bucket")[["exc10", "exc21", "exc63"]].mean().mul(100).round(2)
    g["n"] = R.groupby("bucket").size()
    print(g.to_string())
    buy = R[R["bucket"] == "buy_side"]["exc63"].dropna().mul(100)
    sell = R[R["bucket"] == "sell_side"]["exc63"].dropna().mul(100)
    print(f"\nBUY-side minus SELL-side spread @63d: {buy.mean() - sell.mean():.2f}% "
          f"(buy n={len(buy)}, sell n={len(sell)})")


def strategy_v2() -> pd.DataFrame:
    """Long when (BUY any OR setup_up) AND above200; exit to cash on (setup_dn OR
    sell confirmed) OR price loses the 200d. Trend-gated oscillator timing."""
    out = []
    spy = _load(BENCH)
    for t in SECTORS:
        daily = _load(t)
        if len(daily) < 400:
            continue
        s3 = _to_3b(daily)
        sigs = _signals_3b(s3["close"])
        sma200 = daily.rolling(200).mean()
        above200_3b = (daily > sma200).reindex(sigs.index, method="ffill").fillna(False)
        enter = (sigs["buy_full"] | sigs["buy_partial"] | sigs["setup_up"]) & above200_3b.values
        exit_ = (sigs["setup_dn"] | sigs["sell_full"] | sigs["sell_partial"]) | ~above200_3b.values
        state = pd.Series(np.nan, index=sigs.index)
        state[enter.values] = 1.0
        state[exit_.values & ~enter.values] = 0.0
        state = state.ffill().fillna(0.0)
        pos = state.reindex(daily.index, method="ffill").shift(1).fillna(0.0)
        ret = daily.pct_change().fillna(0.0)
        strat = pos * ret
        eq = (1 + strat).cumprod()
        bh = daily / daily.iloc[0]
        yrs = (daily.index[-1] - daily.index[0]).days / 365.25
        out.append({
            "ticker": t,
            "BH_CAGR%": round(100 * (bh.iloc[-1] ** (1 / yrs) - 1), 1),
            "strat_CAGR%": round(100 * (eq.iloc[-1] ** (1 / yrs) - 1), 1),
            "BH_maxDD%": round(100 * (bh / bh.cummax() - 1).min(), 1),
            "strat_maxDD%": round(100 * (eq / eq.cummax() - 1).min(), 1),
            "time%": round(100 * (pos > 0).mean(), 0),
            "BH_Shrp": round((bh.pct_change().mean() / bh.pct_change().std()) * np.sqrt(252), 2),
            "strat_Shrp": round((strat.mean() / strat.std()) * np.sqrt(252), 2) if strat.std() else np.nan,
        })
    return pd.DataFrame(out).set_index("ticker")


if __name__ == "__main__":
    pd.set_option("display.width", 200)
    pd.set_option("display.max_columns", 30)
    spy = _load(BENCH)
    R = pd.concat([_enrich(t, spy) for t in SECTORS])
    print("=" * 100)
    print("CONDITIONED EVENT STUDY — does a trend / weekly gate sharpen the edge? (excN = excess vs SPY %)")
    print("=" * 100)
    print(conditioned_study(R).to_string())
    rotation_spread(R)
    print("\n" + "=" * 100)
    print("STRATEGY v2 — trend-gated: long on BUY/SETUP-up above 200d, exit on top/setup-dn/lose-200d")
    print("=" * 100)
    st = strategy_v2()
    print(st.to_string())
    print("\nMEDIANS:", st.median(numeric_only=True).round(1).to_dict())
    wins = (st["strat_Shrp"] > st["BH_Shrp"]).sum()
    print(f"Sectors where strat Sharpe > buy-hold Sharpe: {wins}/{len(st)}")
