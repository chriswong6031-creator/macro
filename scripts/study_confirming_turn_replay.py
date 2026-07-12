#!/usr/bin/env python3
"""STUDY A — Confirming-Turn predicate replay (Lane A gate, HK Index-Hybrid-Momentum).

READ-ONLY. Reconstructs the Lane-A "Confirming Turn" predicate historically over the
~74-name HK board universe from RAW prices (data/hk_stocks OHLCV) + RAW southbound
holdings (data/hk_southbound/holdings.parquet). Does NOT read the washout ledger jsonl
(one day locally) and does NOT import/modify any engine file.

PREDICATE (pre-registered — NOT tuned to make BABA fire):
  - RSI(14) <= 32 within the prior 15 sessions (an oversold washout printed recently)
  - close now above a RISING 10-session MA (MA10 today > MA10 5d ago AND close > MA10)
  - RSI(14) reclaimed into [40, 60] today
  - southbound accumulation positive for >= 3 consecutive sessions
        (net-share flow > 0 for 3 consecutive disclosures) OR accum_z > 0.5 today
        accum_z = cross-sectional z (over the board universe) of 5-session net-share flow.

For each firing name-day: forward 20d & 40d return, ABSOLUTE and HSI-excess; did the
swing low (min low over the washout lookback) hold over the next 40d?

NULL MODEL (time-preserving):
  1. Episode-collapse: consecutive firings of ONE name = ONE episode, keep FIRST.
  2. Compare hold-rate / fwd returns of firing episodes vs
       (a) ALL name-days (base rate over the same universe & window)
       (b) MATCHED RSI-reclaim-only episodes WITHOUT the flow leg (isolates flow's add).
  3. Era split: 2016 (southbound start) — MOOT, all SB data is >= 2024-07 (reported).
     Split-half of the firing window (first vs second half) for sign-stability.
  4. Significance via episode-label PERMUTATION over the flow leg (shuffle which
     RSI-reclaim episodes carry the flow tag, preserving the count & time distribution),
     NOT an iid name-day bootstrap. Effective N = episodes (months), not name-days.

Usage: python -m scripts.study_confirming_turn_replay   (or run the file directly)
"""
from __future__ import annotations

import glob
import json
import os
import sys
from pathlib import Path

import numpy as np
import pandas as pd

# ---------------------------------------------------------------- config
HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
DATA = ROOT / "data"

RSI_LEN = 14
OVERSOLD = 32.0            # RSI washout threshold
WASHOUT_LOOKBACK = 15      # oversold must have printed within prior N sessions
RECLAIM_LO, RECLAIM_HI = 40.0, 60.0
MA_LEN = 10
MA_RISE_LOOKBACK = 5       # MA10 today vs MA10 5d ago -> "rising"
ACCUM_CONSEC = 3           # >= 3 consecutive net-buy disclosures
ACCUM_Z_GATE = 0.5
SB_FLOW_WIN = 5            # net-share flow window for accum_z
FWD = (20, 40)
N_PERM = 5000
RNG = np.random.default_rng(20260710)


def rsi(close: pd.Series, n: int = RSI_LEN) -> pd.Series:
    d = close.diff()
    up = d.clip(lower=0.0)
    dn = (-d).clip(lower=0.0)
    # Wilder smoothing
    ru = up.ewm(alpha=1.0 / n, adjust=False, min_periods=n).mean()
    rd = dn.ewm(alpha=1.0 / n, adjust=False, min_periods=n).mean()
    rs = ru / rd.replace(0.0, np.nan)
    out = 100.0 - 100.0 / (1.0 + rs)
    out[rd == 0.0] = 100.0
    return out


# ---------------------------------------------------------------- load universe
def load_board_universe() -> dict[str, str]:
    """{ticker: name} for the board constituents that we have OHLCV for."""
    cons = pd.read_parquet(DATA / "hk_breadth" / "constituents.parquet")
    have = {os.path.basename(f).replace(".parquet", "")
            for f in glob.glob(str(DATA / "hk_stocks" / "*.parquet"))}
    uni = {t: str(cons.loc[t, "name"]) for t in cons.index if t in have}
    return uni


def load_prices(uni: dict[str, str]) -> dict[str, pd.DataFrame]:
    px = {}
    for t in uni:
        df = pd.read_parquet(DATA / "hk_stocks" / f"{t}.parquet")
        df = df.sort_index()
        df.index = pd.to_datetime(df.index)
        px[t] = df[["close", "high", "low"]]
    return px


def load_hsi() -> pd.Series:
    h = pd.read_parquet(DATA / "hk" / "_HSI.parquet").sort_index()
    h.index = pd.to_datetime(h.index)
    return h["close"]


def load_southbound() -> pd.DataFrame:
    """MultiIndex (date,ticker) -> hold_shares. Pivot to date x ticker share levels."""
    sb = pd.read_parquet(DATA / "hk_southbound" / "holdings.parquet")
    sh = sb["hold_shares"].unstack("ticker").sort_index()
    sh.index = pd.to_datetime(sh.index)
    return sh


# ---------------------------------------------------------------- predicate legs
def price_legs(close: pd.Series) -> pd.DataFrame:
    r = rsi(close)
    ma = close.rolling(MA_LEN).mean()
    ma_rising = ma > ma.shift(MA_RISE_LOOKBACK)
    above_ma = close > ma
    oversold_recent = (r <= OVERSOLD).rolling(WASHOUT_LOOKBACK).max().astype(bool)
    reclaim = r.between(RECLAIM_LO, RECLAIM_HI)
    swing_low = close.rolling(WASHOUT_LOOKBACK).min()  # proxy for washout low on close
    out = pd.DataFrame({
        "rsi": r, "ma_rising": ma_rising, "above_ma": above_ma,
        "oversold_recent": oversold_recent, "reclaim": reclaim,
        "swing_low": swing_low,
    })
    # price-turn (RSI-reclaim-only, no flow): oversold washout printed, reclaim now,
    # above a rising MA10
    out["price_turn"] = (out["oversold_recent"] & out["reclaim"]
                         & out["ma_rising"] & out["above_ma"]).fillna(False)
    return out


def build_flow(sh: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Return (consec_pos, accum_z) aligned on SB dates x tickers.
    consec_pos[t,d] True if net-share flow (diff of hold_shares) > 0 for >=3 consec
    disclosures ending d. accum_z = cross-sectional z of 5d net-share flow that day."""
    flow1 = sh.diff()                          # per-disclosure net-share flow
    pos = flow1 > 0
    # consecutive positive count (per column) ending each row
    consec = pos.copy().astype(float)
    for col in pos.columns:
        c = 0
        vals = []
        for v in pos[col].values:
            c = c + 1 if v else 0
            vals.append(c)
        consec[col] = vals
    consec_pos = consec >= ACCUM_CONSEC

    flow5 = sh.diff(SB_FLOW_WIN)
    mu = flow5.mean(axis=1)
    sd = flow5.std(axis=1).replace(0.0, np.nan)
    accum_z = flow5.sub(mu, axis=0).div(sd, axis=0)
    return consec_pos, accum_z


# ---------------------------------------------------------------- forward returns
def fwd_ret(close: pd.Series, idx_pos: int, h: int) -> float:
    if idx_pos + h >= len(close):
        return np.nan
    c0 = close.iloc[idx_pos]
    c1 = close.iloc[idx_pos + h]
    if c0 <= 0 or not np.isfinite(c0) or not np.isfinite(c1):
        return np.nan
    return c1 / c0 - 1.0


def swing_held(low: pd.Series, idx_pos: int, swing: float, h: int) -> float:
    """Did the min-low over next h sessions stay above the washout swing low?"""
    if not np.isfinite(swing):
        return np.nan
    end = min(idx_pos + h, len(low) - 1)
    if end <= idx_pos:
        return np.nan
    fwd_min = low.iloc[idx_pos + 1:end + 1].min()
    return float(fwd_min >= swing)


# ---------------------------------------------------------------- main
def main() -> None:
    uni = load_board_universe()
    px = load_prices(uni)
    hsi = load_hsi()
    sh = load_southbound()
    consec_pos, accum_z = build_flow(sh)
    sb_dates = sh.index
    sb_start = sb_dates.min()

    # HSI forward returns keyed by position for excess calc
    hsi_close = hsi

    firings = []      # full flow-confirmed firings (Lane A)
    price_only = []   # RSI-reclaim-only (matched null (b)) — every price_turn day
    all_rows = []     # base-rate universe of eval-able name-days in SB window

    for t, df in px.items():
        close = df["close"].dropna()
        low = df["low"].reindex(close.index).ffill()
        legs = price_legs(close)
        # restrict eval to SB window (flow leg only meaningful there)
        elig = close.index[close.index >= sb_start]
        # SB series for this ticker (may be absent -> no flow confirmation)
        has_sb = t in consec_pos.columns
        cp = consec_pos[t].reindex(close.index).fillna(False) if has_sb else pd.Series(False, index=close.index)
        az = accum_z[t].reindex(close.index) if t in accum_z.columns else pd.Series(np.nan, index=close.index)
        flow_ok = (cp | (az > ACCUM_Z_GATE)).fillna(False)

        pos_of = {d: i for i, d in enumerate(close.index)}
        for d in elig:
            i = pos_of[d]
            row = {"ticker": t, "name": uni[t], "date": d}
            for h in FWD:
                row[f"abs{h}"] = fwd_ret(close, i, h)
                # HSI excess
                if d in hsi_close.index:
                    hi = hsi_close.index.get_loc(d)
                    hpos = hi if isinstance(hi, int) else hsi_close.index.get_indexer([d])[0]
                    hr = fwd_ret(hsi_close, hpos, h) if hpos >= 0 else np.nan
                else:
                    hr = np.nan
                row[f"exc{h}"] = row[f"abs{h}"] - hr if np.isfinite(row[f"abs{h}"]) and np.isfinite(hr) else np.nan
            row["held40"] = swing_held(low, i, legs["swing_low"].iloc[i], 40)
            all_rows.append(row)

            if bool(legs["price_turn"].iloc[i]):
                pr = dict(row); pr["flow_ok"] = bool(flow_ok.iloc[i])
                price_only.append(pr)
                if bool(flow_ok.iloc[i]):
                    firings.append(dict(row))

    fdf = pd.DataFrame(firings)
    pdf = pd.DataFrame(price_only)
    adf = pd.DataFrame(all_rows)

    def episode_collapse(df: pd.DataFrame, gap_days: int = 20) -> pd.DataFrame:
        """Consecutive firings of one name = one episode; keep first. New episode when
        the same name re-fires after a > gap_days break."""
        if df.empty:
            return df
        df = df.sort_values(["ticker", "date"]).copy()
        keep = []
        last = {}
        for _, r in df.iterrows():
            t = r["ticker"]; d = r["date"]
            if t not in last or (d - last[t]).days > gap_days:
                keep.append(True)
            else:
                keep.append(False)
            last[t] = d
        return df[pd.Series(keep, index=df.index)]

    fe = episode_collapse(fdf)
    pe = episode_collapse(pdf)                       # all price-turn episodes
    pe_noflow = pe[~pe["flow_ok"]] if not pe.empty else pe

    def summ(df: pd.DataFrame, label: str) -> dict:
        d = {"label": label, "n": int(len(df))}
        if df.empty:
            return d
        for h in FWD:
            d[f"abs{h}_mean"] = float(df[f"abs{h}"].mean())
            d[f"abs{h}_med"] = float(df[f"abs{h}"].median())
            d[f"exc{h}_mean"] = float(df[f"exc{h}"].mean())
            d[f"exc{h}_med"] = float(df[f"exc{h}"].median())
            d[f"abs{h}_win"] = float((df[f"abs{h}"] > 0).mean())
        d["held40_rate"] = float(df["held40"].mean())
        return d

    res = {
        "sb_window": [str(sb_start.date()), str(sb_dates.max().date())],
        "sb_n_dates": int(len(sb_dates)),
        "universe_n": len(uni),
        "era_split_2016": "MOOT — all southbound data >= 2024-07; no pre-2016 rows exist",
        "summaries": {
            "firing_episodes": summ(fe, "Lane-A firing episodes (flow-confirmed)"),
            "price_turn_all_episodes": summ(pe, "RSI-reclaim episodes (all, price-only leg)"),
            "price_turn_noflow_episodes": summ(pe_noflow, "RSI-reclaim episodes WITHOUT flow (null b)"),
            "base_rate_all_namedays": summ(adf, "ALL name-days in SB window (null a)"),
        },
    }

    # split-half sign stability on firing episodes
    if not fe.empty:
        fe_s = fe.sort_values("date")
        mid = fe_s["date"].iloc[len(fe_s) // 2]
        h1 = fe_s[fe_s["date"] < mid]; h2 = fe_s[fe_s["date"] >= mid]
        res["split_half"] = {
            "cut": str(mid.date()),
            "first": summ(h1, "first half"),
            "second": summ(h2, "second half"),
        }

    # permutation test: does the flow leg ADD forward edge over price-turn-only?
    # Universe = all price-turn EPISODES (pe). Observed contrast = mean(fwd | flow)
    #  - mean(fwd | no-flow). Null: shuffle the flow_ok labels across episodes.
    perm = {}
    if not pe.empty and pe["flow_ok"].sum() >= 3 and (~pe["flow_ok"]).sum() >= 3:
        labels = pe["flow_ok"].values.astype(bool)
        k = labels.sum()
        for metric in ("abs20", "abs40", "exc20", "exc40", "held40"):
            vals = pe[metric].values.astype(float)
            m = np.isfinite(vals)
            v = vals[m]; lab = labels[m]
            if lab.sum() < 3 or (~lab).sum() < 3:
                continue
            obs = v[lab].mean() - v[~lab].mean()
            n = len(v); kk = int(lab.sum())
            null = np.empty(N_PERM)
            for b in range(N_PERM):
                idx = RNG.permutation(n)
                sel = idx[:kk]
                null[b] = v[sel].mean() - v[np.setdiff1d(np.arange(n), sel, assume_unique=False)].mean()
            p_two = float((np.abs(null) >= abs(obs)).mean())
            perm[metric] = {
                "flow_mean": float(v[lab].mean()), "noflow_mean": float(v[~lab].mean()),
                "delta": float(obs), "p_two_sided": p_two,
                "n_flow": int(lab.sum()), "n_noflow": int((~lab).sum()),
            }
    res["flow_leg_permutation"] = perm

    print(json.dumps(res, indent=2, default=str))
    out = ROOT / "data" / "_study_confirming_turn_replay.json"
    try:
        out.write_text(json.dumps(res, indent=2, default=str))
        print(f"\n[wrote {out}]", file=sys.stderr)
    except Exception as e:  # noqa: BLE001
        print(f"[no write: {e}]", file=sys.stderr)


if __name__ == "__main__":
    main()
