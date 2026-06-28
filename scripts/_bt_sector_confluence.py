"""Backtest the 3-day MACD + StochRSI crossover-confluence theory on sector ETFs.

The user's theory (verbatim, paraphrased):
  * Bottom CONFIRM on the 3-day chart = MACD bullish crossover OR StochRSI
    bullish crossover from below back up over the 20 line.
  * Top CONFIRM on the 3-day chart = MACD bearish crossover OR StochRSI bearish
    crossover (down out of overbought).
  * One indicator = PARTIAL confirmation; BOTH = a full BUY / SELL.
  * SETUP = the days leading up to a potential crossover.

This script measures whether those events have predictive power on the 11 SPDR
sector ETFs over their full Yahoo history, using the EXACT cross logic the live
engine (`engine.cycles._tf_state`) already computes, so the research and the
production signal share one definition. Point-in-time: every signal is read at
the close of a 3-business-day bar and forward returns start from that close.

Run:  python3 -m scripts._bt_sector_confluence
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from engine.cycles import macd_parts, stoch_rsi
from engine.technicals import rsi

SECTORS = ["XLB", "XLC", "XLE", "XLF", "XLI", "XLK", "XLP", "XLRE", "XLU", "XLV", "XLY"]
BENCH = "SPY"
HORIZONS = [5, 10, 21, 42, 63]


def _load(t: str) -> pd.Series:
    df = pd.read_parquet(f"data/yahoo/{t}.parquet")
    return df["close"].dropna()


def _to_3b(close: pd.Series) -> pd.DataFrame:
    """Resample to 3 business days, keeping the ACTUAL last trading date per bin
    (not the bin label) so forward returns align to the real decision date."""
    df = close.to_frame("close")
    df["date"] = df.index
    res = df.resample("3B").last().dropna()
    res = res.set_index("date")
    return res


def _signals_3b(close3b: pd.Series) -> pd.DataFrame:
    """Vectorised replica of engine.cycles._tf_state cross flags on a 3B series."""
    m = macd_parts(close3b)
    h = m["hist"]
    s = stoch_rsi(close3b)
    r14 = rsi(close3b, 14)

    prior_le0 = (h.shift(1) <= 0) | (h.shift(2) <= 0) | (h.shift(3) <= 0)
    prior_ge0 = (h.shift(1) >= 0) | (h.shift(2) >= 0) | (h.shift(3) >= 0)
    macd_up = (h > 0) & prior_le0
    macd_dn = (h < 0) & prior_ge0

    prior_s_lt20 = (s.shift(1) < 20) | (s.shift(2) < 20) | (s.shift(3) < 20)
    prior_s_gt80 = (s.shift(1) > 80) | (s.shift(2) > 80) | (s.shift(3) > 80)
    stoch_up = (s >= 20) & prior_s_lt20
    stoch_dn = (s <= 80) & prior_s_gt80

    # setup = histogram rising 3 bars while still negative (approaching up-cross)
    rising = (h > h.shift(1)) & (h.shift(1) > h.shift(2))
    falling = (h < h.shift(1)) & (h.shift(1) < h.shift(2))
    setup_up = (h < 0) & rising
    setup_dn = (h > 0) & falling

    out = pd.DataFrame({
        "close": close3b, "hist": h, "stoch": s, "rsi14": r14,
        "macd_up": macd_up.fillna(False), "macd_dn": macd_dn.fillna(False),
        "stoch_up": stoch_up.fillna(False), "stoch_dn": stoch_dn.fillna(False),
        "setup_up": setup_up.fillna(False), "setup_dn": setup_dn.fillna(False),
    })
    out["buy_full"] = out["macd_up"] & out["stoch_up"]
    out["buy_partial"] = (out["macd_up"] | out["stoch_up"]) & ~out["buy_full"]
    out["sell_full"] = out["macd_dn"] & out["stoch_dn"]
    out["sell_partial"] = (out["macd_dn"] | out["stoch_dn"]) & ~out["sell_full"]
    return out


def _fwd_table(sigs: pd.DataFrame, daily: pd.Series, spy: pd.Series) -> pd.DataFrame:
    """Attach forward absolute + excess-vs-SPY returns at each signal date."""
    didx = daily.index
    pos = didx.get_indexer(sigs.index)
    rows = sigs.copy()
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
        rows[f"fwd{h}"] = fwd
        rows[f"exc{h}"] = exc
    return rows


def _agg(label: str, mask: pd.Series, rows: pd.DataFrame) -> dict:
    sub = rows[mask]
    rec = {"signal": label, "n": int(mask.sum())}
    for h in HORIZONS:
        v = sub[f"fwd{h}"].dropna()
        e = sub[f"exc{h}"].dropna()
        rec[f"fwd{h}"] = round(100 * v.mean(), 2) if len(v) else np.nan
        rec[f"hit{h}"] = round(100 * (v > 0).mean(), 0) if len(v) else np.nan
        rec[f"exc{h}"] = round(100 * e.mean(), 2) if len(e) else np.nan
    return rec


def event_study() -> pd.DataFrame:
    spy = _load(BENCH)
    all_rows = []
    base_rows = []
    for t in SECTORS:
        daily = _load(t)
        if len(daily) < 400:
            continue
        s3 = _to_3b(daily)
        sigs = _signals_3b(s3["close"])
        rows = _fwd_table(sigs, daily, spy)
        rows["ticker"] = t
        all_rows.append(rows)
        base_rows.append(rows)
    R = pd.concat(all_rows)
    B = pd.concat(base_rows)
    recs = [_agg("ALL-3Bbars (baseline)", pd.Series(True, index=B.index), B)]
    for lbl, col in [("BUY full (MACD+Stoch up)", "buy_full"),
                     ("BUY partial (one up)", "buy_partial"),
                     ("  MACD up only", "macd_up"),
                     ("  Stoch up only", "stoch_up"),
                     ("SETUP up (approaching)", "setup_up"),
                     ("SELL full (MACD+Stoch dn)", "sell_full"),
                     ("SELL partial (one dn)", "sell_partial"),
                     ("  MACD dn only", "macd_dn"),
                     ("  Stoch dn only", "stoch_dn"),
                     ("SETUP dn (approaching)", "setup_dn")]:
        recs.append(_agg(lbl, R[col], R))
    return pd.DataFrame(recs).set_index("signal")


def strategy_test() -> pd.DataFrame:
    """Long/flat: go long on a BUY (full or partial), exit to cash on a SELL
    (full or partial). Compare CAGR + max drawdown vs buy-and-hold per sector."""
    out = []
    for t in SECTORS:
        daily = _load(t)
        if len(daily) < 400:
            continue
        s3 = _to_3b(daily)
        sigs = _signals_3b(s3["close"])
        # build a daily position series from 3B state transitions
        buy = (sigs["buy_full"] | sigs["buy_partial"])
        sell = (sigs["sell_full"] | sigs["sell_partial"])
        state = pd.Series(np.nan, index=sigs.index)
        state[buy] = 1.0
        state[sell] = 0.0
        state = state.ffill().fillna(0.0)
        # map to daily, hold next day (enter at next daily close = no lookahead)
        pos = state.reindex(daily.index, method="ffill").shift(1).fillna(0.0)
        ret = daily.pct_change().fillna(0.0)
        strat = (pos * ret)
        eq = (1 + strat).cumprod()
        bh = daily / daily.iloc[0]
        yrs = (daily.index[-1] - daily.index[0]).days / 365.25
        out.append({
            "ticker": t,
            "BH_CAGR%": round(100 * (bh.iloc[-1] ** (1 / yrs) - 1), 1),
            "strat_CAGR%": round(100 * (eq.iloc[-1] ** (1 / yrs) - 1), 1),
            "BH_maxDD%": round(100 * (bh / bh.cummax() - 1).min(), 1),
            "strat_maxDD%": round(100 * (eq / eq.cummax() - 1).min(), 1),
            "time_in_mkt%": round(100 * (pos > 0).mean(), 0),
            "BH_Sharpe": round((bh.pct_change().mean() / bh.pct_change().std()) * np.sqrt(252), 2),
            "strat_Sharpe": round((strat.mean() / strat.std()) * np.sqrt(252), 2) if strat.std() else np.nan,
        })
    df = pd.DataFrame(out).set_index("ticker")
    return df


if __name__ == "__main__":
    pd.set_option("display.width", 200)
    pd.set_option("display.max_columns", 30)
    print("=" * 100)
    print("EVENT STUDY — forward returns (%) after each signal, pooled across 11 sector ETFs")
    print("fwdN = mean abs fwd return; hitN = % positive; excN = mean excess vs SPY")
    print("=" * 100)
    es = event_study()
    print(es[["n", "fwd5", "fwd10", "fwd21", "fwd63", "hit10", "hit21", "exc21", "exc63"]].to_string())
    print()
    print("=" * 100)
    print("STRATEGY — long after BUY (full|partial), flat after SELL (full|partial), per sector")
    print("=" * 100)
    st = strategy_test()
    print(st.to_string())
    print()
    print("MEDIANS:", st.median(numeric_only=True).round(1).to_dict())
