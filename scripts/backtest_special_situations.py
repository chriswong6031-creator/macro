"""Near-term backtest of digest special situations (proof of concept).

Tests the digest as a tradeable signal: enter each US situation at the first close
on/after its issue (digest) date, measure forward returns at 5/20/60 trading days,
both raw and excess vs SPY, aggregated by category. This answers "do these
situations carry forward drift, and which categories?" — the question behind
building our own detector.

Honest scope: prices are limited to the US equity close caches currently on disk
(~1,100 tickers back to 2023), so only the situations whose tickers we can price
are included (count reported per cell). Full coverage needs a broad yahoo price
backfill for the off-cache small-caps. Entry at the *digest* date deliberately
includes their weekly lag — our own EDGAR pipeline would enter at the filing date.

Run: python -m scripts.backtest_special_situations
"""
from __future__ import annotations

import json
from datetime import datetime, timezone

import numpy as np
import pandas as pd

from lib import config

HORIZONS = [5, 20, 60]


_BT_PRICES = "special_situations/bt_prices.parquet"


def _us_closes() -> pd.DataFrame:
    frames = []
    for g in ("breadth", "midcap_breadth", "smallcap_breadth"):
        p = config.data_dir() / g / "_closes_cache.parquet"
        if p.exists():
            frames.append(pd.read_parquet(p))
    btp = config.data_dir() / _BT_PRICES        # backfilled off-cache US digest tickers
    if btp.exists():
        frames.append(pd.read_parquet(btp))
    if not frames:
        return pd.DataFrame()
    df = pd.concat(frames, axis=1, sort=False)
    df.index = pd.to_datetime(df.index)
    return df.loc[:, ~df.columns.duplicated()].sort_index()


def fetch_bt_prices(start: str = "2025-09-01") -> int:
    """Backfill adjusted closes (via yfinance) for US digest tickers not already in
    our breadth caches — widens the backtest from the S&P-ish universe to the full
    digest US set. Cached to data/special_situations/bt_prices.parquet."""
    import yfinance as yf
    digest = pd.read_parquet(config.data_dir() / "special_situations" / "digest_db.parquet")
    us = sorted({str(t).strip().upper() for t in digest[digest.country == "US"].ticker.dropna()
                 if "." not in str(t)})
    have = set()
    for g in ("breadth", "midcap_breadth", "smallcap_breadth"):
        p = config.data_dir() / g / "_closes_cache.parquet"
        if p.exists():
            have |= set(pd.read_parquet(p).columns)
    need = [t for t in us if t not in have]
    if not need:
        return 0
    frames = []
    for i in range(0, len(need), 60):
        batch = need[i:i + 60]
        try:
            df = yf.download(batch, start=start, auto_adjust=True, progress=False, threads=True)
            close = df["Close"] if "Close" in df else df
            if isinstance(close, pd.Series):
                close = close.to_frame(batch[0])
            frames.append(close)
        except Exception as e:  # noqa: BLE001
            print(f"  batch {i} failed: {e}")
    if not frames:
        return 0
    panel = pd.concat(frames, axis=1)
    panel = panel.loc[:, ~panel.columns.duplicated()].dropna(how="all")
    out = config.data_dir() / _BT_PRICES
    out.parent.mkdir(parents=True, exist_ok=True)
    panel.to_parquet(out)
    print(f"  backfilled {panel.shape[1]} tickers x {panel.shape[0]} days -> {out}")
    return panel.shape[1]


def _spy(closes: pd.DataFrame) -> pd.Series | None:
    if "SPY" in closes.columns:
        return closes["SPY"]
    try:
        from lib import store
        s = store.read("yahoo", "SPY")
        return s["close"] if s is not None and "close" in s else None
    except Exception:  # noqa: BLE001
        return None


def _fwd(series: pd.Series, entry_pos: int, h: int) -> float | None:
    if entry_pos < 0 or entry_pos + h >= len(series):
        return None
    p0, p1 = series.iloc[entry_pos], series.iloc[entry_pos + h]
    if p0 and p1 and p0 > 0:
        return float(p1 / p0 - 1.0)
    return None


def run() -> pd.DataFrame:
    df = pd.read_parquet(config.data_dir() / "special_situations" / "digest_db.parquet")
    us = df[(df.country == "US") & df.ticker.notna() & df.issue_date.notna()].copy()
    closes = _us_closes()
    if closes.empty:
        print("no US close caches on disk — cannot backtest")
        return pd.DataFrame()
    spy = _spy(closes)
    idx = closes.index

    recs = []
    for _, r in us.iterrows():
        tkr = r.ticker
        if tkr not in closes.columns:
            continue
        s = closes[tkr].dropna()
        if s.empty:
            continue
        entry_dt = pd.Timestamp(r.issue_date)
        pos_all = idx.searchsorted(entry_dt)            # first close >= issue date
        if pos_all >= len(idx):
            continue
        entry_dt_actual = idx[pos_all]
        epos = s.index.searchsorted(entry_dt_actual)
        if epos >= len(s) or s.index[epos] < entry_dt_actual:
            continue
        spos = spy.index.searchsorted(entry_dt_actual) if spy is not None else -1
        rec = {"category": r.category, "ticker": tkr}
        for h in HORIZONS:
            fr = _fwd(s, epos, h)
            rec[f"r{h}"] = fr
            if fr is not None and spy is not None and 0 <= spos < len(spy):
                sr = _fwd(spy, spos, h)
                rec[f"x{h}"] = (fr - sr) if sr is not None else None
            else:
                rec[f"x{h}"] = None
        recs.append(rec)

    bt = pd.DataFrame(recs)
    return bt


def _agg(bt: pd.DataFrame) -> pd.DataFrame:
    out = []
    for cat, g in bt.groupby("category"):
        row = {"category": cat, "n": len(g)}
        for h in HORIZONS:
            col, xcol = f"r{h}", f"x{h}"
            v = g[col].dropna()
            x = g[xcol].dropna()
            row[f"n{h}"] = len(v)
            row[f"med_r{h}"] = round(v.median() * 100, 1) if len(v) else np.nan
            row[f"win{h}"] = round((v > 0).mean() * 100, 0) if len(v) else np.nan
            row[f"med_x{h}"] = round(x.median() * 100, 1) if len(x) else np.nan
        out.append(row)
    res = pd.DataFrame(out).sort_values("n", ascending=False)
    return res


def main() -> int:
    bt = run()
    if bt.empty:
        return 1
    res = _agg(bt)
    pd.set_option("display.width", 200)
    print(f"Backtested {len(bt)} US situations we can price "
          f"(entry = first close after the digest date).\n")
    show = ["category", "n", "med_r20", "win20", "med_x20", "n20", "med_r60", "med_x60", "n60"]
    print(res[show].to_string(index=False))
    print("\nALL situations pooled:")
    for h in HORIZONS:
        v = bt[f"r{h}"].dropna(); x = bt[f"x{h}"].dropna()
        if len(v):
            print(f"  +{h:>2}d: median {v.median()*100:+.1f}% · win {(v>0).mean()*100:.0f}% · "
                  f"median excess vs SPY {x.median()*100:+.1f}% (n={len(v)})")
    print("\n[honest] entry includes the digest's weekly lag; forward windows are capped "
          "by the present, so late-issue n is small. Our EDGAR pipeline (filing-date entry) "
          "is the cleaner go-forward signal.")

    # persist per-category forward-return priors for the signal system / trading brain
    def _num(v):
        return None if v is None or (isinstance(v, float) and np.isnan(v)) else float(v)
    priors = {r["category"]: {"n": int(r["n"]), "med_ret_20d_pct": _num(r["med_r20"]),
                              "win_20d_pct": _num(r["win20"]), "med_excess_20d_pct": _num(r["med_x20"]),
                              "med_ret_60d_pct": _num(r["med_r60"])}
              for _, r in res.iterrows()}
    out = {"schema": "ss_backtest_priors.v1", "is_context_only": True,
           "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
           "n_situations": int(len(bt)), "entry": "first close after digest date",
           "by_category": priors,
           "note": "Forward returns of digest US situations by category. Context/priors only, not a signal."}
    p = config.data_dir() / "special_situations" / "backtest_priors.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(out, indent=2))
    print(f"\n[priors] wrote {p}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
