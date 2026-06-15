"""Phase-0 gate for the contrarian "fragility" tag (research/DATA_SIGNAL_EXPANSION_2026.md #6).

QUESTION: does a CONTRARIAN crowding/fragility conjunction predict WORSE forward
outcomes cross-sectionally — i.e. earn a place as a subtract-only TEMPER in the
per-stock conviction score — or is it display-only context?

The proposed live tag is:  fragile = high RS-crowding pctile AND high short-interest
pctile AND extended.  But our FINRA short-interest store holds only the LATEST
snapshot (data/finra/short_interest.parquet, one settlement date) — there is NO
point-in-time SI history to backtest, so the full 3-way conjunction CANNOT be
PIT-validated.  This script therefore tests the only legs we DO have history for:

    FRAGILE = crowded (trailing RS percentile >= 80) AND extended (cross-sectional
              stretch above the 50dma in the top quintile that day).

If even this price-only fragility core does not robustly predict worse forward
drawdown / lower forward excess return, the tag is display-only (and the SI leg —
which we cannot validate at all — certainly stays out of sizing).

Mirrors the team's "no unvalidated scoring leg" bar (cf. validate_stress_gate.py):
weekly rebalances, PIT features, by-date bucket means (no pseudo-replication),
Newey-West t-stats over the overlap, and a sign-consistent split-half check.

Decision rule (conservative): WIRE a subtract-only temper only if FRAGILE shows
BOTH (a) lower forward excess return than the rest AND (b) worse forward drawdown,
each with |t| >= 2 on the full sample AND the SAME sign in both halves.  Else
DISPLAY-ONLY.
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from engine.equity_factors import _closes  # noqa: E402
from lib import config, store  # noqa: E402

HORIZONS = [21, 63]        # ~1m, ~3m forward
CROWD_PCTILE = 0.80        # crowded = trailing 252d RS percentile >= this
EXT_QUINTILE = 0.80        # extended = cross-sectional stretch-above-50dma >= this pctile
RS_WIN = 252               # trailing window for the RS percentile rank
STEP = 5                   # weekly rebalances


def _spy() -> pd.Series:
    df = store.read("yahoo", "SPY")
    s = (df["close"] if df is not None and "close" in df else df.iloc[:, 0]).copy()
    s.index = pd.to_datetime(s.index)
    return s.sort_index()


def _fwd_maxdd(close: pd.DataFrame, h: int) -> pd.DataFrame:
    """Forward max drawdown over the next h days: min(close[t+1..t+h]) / close[t] - 1.
    Reverse-rolling so a backward window acts forward; values aligned at t."""
    rev = close.iloc[::-1]
    fmin = rev.rolling(h, min_periods=max(2, h // 3)).min().iloc[::-1]
    fmin = fmin.shift(-1)                      # exclude today, look t+1..t+h
    return fmin / close - 1.0


def _nw_tstat(x: pd.Series, lag: int) -> float:
    """Newey-West t-stat for the mean of an overlap-autocorrelated series."""
    x = x.dropna().astype(float)
    n = len(x)
    if n < 10:
        return float("nan")
    mu = x.mean()
    e = (x - mu).values
    gamma0 = (e @ e) / n
    var = gamma0
    for k in range(1, min(lag, n - 1) + 1):
        w = 1.0 - k / (lag + 1.0)
        cov = (e[k:] @ e[:-k]) / n
        var += 2.0 * w * cov
    se = np.sqrt(max(var, 1e-12) / n)
    return float(mu / se)


def _bucket_diff_series(value: pd.DataFrame, fragile: pd.DataFrame,
                        rest: pd.DataFrame, dates) -> pd.Series:
    """For each rebalance date, cross-sectional mean(value | fragile) - mean(value | rest)."""
    out = {}
    for d in dates:
        v = value.loc[d]
        fmask = fragile.loc[d].reindex(v.index).fillna(False)
        rmask = rest.loc[d].reindex(v.index).fillna(False)
        vf, vr = v[fmask].dropna(), v[rmask].dropna()
        if len(vf) >= 3 and len(vr) >= 20:
            out[d] = vf.mean() - vr.mean()
    return pd.Series(out).sort_index()


def main() -> int:
    closes = _closes()
    if closes.empty:
        raise SystemExit("no closes panel")
    spy = _spy().reindex(closes.index).ffill()

    rs = closes.div(spy, axis=0)
    rs_pct = rs.rolling(RS_WIN, min_periods=200).rank(pct=True)          # PIT trailing
    sma50 = closes.rolling(50).mean()
    stretch = closes / sma50 - 1.0
    ext_pct = stretch.rank(axis=1, pct=True)                            # PIT cross-sectional
    above50 = closes > sma50

    crowded = rs_pct >= CROWD_PCTILE
    extended = (ext_pct >= EXT_QUINTILE) & above50
    fragile = crowded & extended
    crowded_only = crowded & ~extended
    valid = rs_pct.notna() & ext_pct.notna()
    rest = valid & ~fragile

    spy_ret = {h: spy.pct_change(h).shift(-h) for h in HORIZONS}

    # rebalance dates: weekly, with enough trailing history and forward room
    rebal = closes.index[(np.arange(len(closes)) % STEP == 0)]
    rebal = rebal[(rebal >= closes.index[RS_WIN]) & (rebal <= closes.index[-max(HORIZONS) - 1])]

    print("Fund-crowding fragility Phase-0 — contrarian crowding/extension -> forward drawdown")
    print(f"sample {closes.index[0].date()} -> {closes.index[-1].date()}  "
          f"tickers={closes.shape[1]}  rebal dates={len(rebal)}")
    print(f"FRAGILE = RS pctile>={CROWD_PCTILE:.2f} AND stretch pctile>={EXT_QUINTILE:.2f} & >50dma")
    avg_frag = int(fragile.loc[rebal].sum(axis=1).mean())
    avg_rest = int(rest.loc[rebal].sum(axis=1).mean())
    print(f"avg names/day  fragile={avg_frag}  rest={avg_rest}\n")

    half = len(rebal) // 2
    halves = {"FULL": rebal, "H1": rebal[:half], "H2": rebal[half:]}
    wire_votes = []

    for h in HORIZONS:
        fwd_ret = closes.pct_change(h).shift(-h)
        fwd_ex = fwd_ret.sub(spy_ret[h], axis=0)        # excess vs SPY
        fwd_dd = _fwd_maxdd(closes, h)

        print(f"=== horizon {h}d ===")
        print(f"{'metric':22s}" + "".join(f"{k:>10s}" for k in halves) +
              "".join(f"{k+'·t':>10s}" for k in halves))

        for label, value, worse in (("fwd excess ret (pp)", fwd_ex, "lower"),
                                     ("fwd max drawdown (pp)", fwd_dd, "worse")):
            row_mean, row_t = [], []
            for hk, ds in halves.items():
                diff = _bucket_diff_series(value, fragile, rest, ds)
                row_mean.append(100 * diff.mean() if len(diff) else float("nan"))
                row_t.append(_nw_tstat(diff, lag=h // STEP + 1))
            print(f"{label:22s}" + "".join(f"{m:10.2f}" for m in row_mean) +
                  "".join(f"{t:10.2f}" for t in row_t))
            # contrarian fragility => diff (fragile - rest) should be NEGATIVE
            full_t = row_t[0]
            sign_ok = (row_mean[1] < 0 and row_mean[2] < 0)
            wire_votes.append(full_t <= -2.0 and sign_ok)
        print()

    wire = all(wire_votes)
    print("VERDICT:", "WIRE subtract-only fragility temper" if wire else
          "DISPLAY-ONLY — fragility core does not robustly predict worse forward outcomes")
    print("(rule: fragile underperforms on BOTH excess-return AND drawdown, |t|>=2 full + same-sign halves)")
    print("NOTE: the live tag also requires high short-interest, which has NO PIT history "
          "in our store (single FINRA snapshot) — so the SI leg is un-backtestable and "
          "stays display-only regardless of this verdict.")

    # current cross-section: how the (un-backtestable) SI leg overlaps fragility TODAY
    try:
        si = pd.read_parquet(config.data_dir() / "finra" / "short_interest.parquet")
        last = closes.index[-1]
        frag_today = fragile.loc[last]
        frag_names = frag_today[frag_today].index
        dtc = si["days_to_cover"].reindex(frag_names).dropna()
        hi_si = dtc[dtc >= si["days_to_cover"].quantile(0.80)]
        print(f"\nTODAY ({last.date()}): {len(frag_names)} fragile names; "
              f"{len(hi_si)} also high days-to-cover (top SI quintile) -> the display flag set.")
    except Exception as e:  # noqa: BLE001
        print("\n(SI cross-section skipped:", e, ")")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
