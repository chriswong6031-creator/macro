"""Forward ledger for the CN Reversal Sleeve — the REAL track record (the backcast is only
reconstruction-on-the-current-plane). Every monthly rebalance's membership is registered to
an own, append-only, point-in-time parquet; once a rebalance matures, grade() scores it
CSI300-relative + fill-realistic, so the sleeve accrues its own graded record from day 1.

CONVENTIONS — CN-1-compatible (engine.china_standout_track, macro#820), so this ledger and
the board ledger speak the same grammar and a later coherence pass can pool them:
  * CSI300-RELATIVE excess (benchmark 510300.SS) — never absolute; the honest question is
    "did the sleeve beat the index it was picked from", not "did A-shares go up".
  * FILL-REALISTIC entry: the rebalance reference is the month-end CLOSE, untradeable by a
    retail user; the earliest legal fill is T+1. Entry = T+1 open when collected, else the
    (H+L)/2 proxy (the measured dominant fill uncertainty — CN-1 ENTRY_BASIS).
  * EXCLUDE locked-limit-all-day T+1 rows (high==low==close): genuinely unfillable; grading
    them fabricates a fill that never existed.
  * NEVER anchored on a §7 marker date — the anchor is the rebalance-date close, the return
    starts at the T+1 fill.
  * data_through stamped distinct from as_of (§W6-CN cross-repo contract): the freshest CN
    session the membership was computed against.

Sleeve-level grade (this is a PORTFOLIO, not stock tips): the graded number is the EW MEMBER
mean excess per rebalance — the sleeve's realized CSI300-relative return — with a Wilson-CI
hit rate over rebalances. Append-only, keep-first per (rebalance_date, ticker). RESEARCH /
display telemetry — never a trade trigger. Best-effort: every path degrades, never raises."""
from __future__ import annotations

import logging

import numpy as np
import pandas as pd

from lib import config, store

log = logging.getLogger(__name__)

_STORE = "cn_reversal_sleeve_track"
_BENCH = "510300.SS"                              # CSI300 ETF (data/china) — the excess benchmark
_PRICE_GROUPS = ("china_stocks", "china")        # names resolve in china_stocks, ETFs in china
_HORIZON_D = 21                                   # ~1 month hold to the next rebalance
_MIN_GRADED = 4                                   # rebalances required before a number publishes
ENTRY_BASIS = "t1_hl2"                            # matches CN-1; upgrades to true T+1 open

# Row schema — a stable contract the tests assert. One row per (rebalance_date, ticker).
LEDGER_COLUMNS = ("rebalance_date", "ticker", "sector", "rev_z", "weight",
                  "level", "data_through")


def _store_path():
    return config.data_dir() / _STORE / "sleeve.parquet"


def append_rebalance(membership: dict, *, data_through: str | None = None,
                     lane: str | None = None) -> int:
    """Register a rebalance's membership (from cn_reversal_sleeve.current_membership) to the
    append-only ledger. Keep-FIRST per (rebalance_date, ticker) so a logged row is never
    overwritten/leaked. Returns the ledger row count after the merge.

    LEDGER-INTEGRITY GATE (CN-1 parity): appends only from the asia collection lane
    (``lane in {None, 'asia'}``); the nightly render lanes must not persist (they discard
    data/ writes). Best-effort — never raises."""
    if not membership or not membership.get("members"):
        return 0
    if lane is not None and lane != "asia":
        log.info("cn_reversal_sleeve ledger: append gated (lane=%s, not asia)", lane)
        return 0
    asof = membership.get("as_of")
    if not asof:
        return 0
    dt = str(data_through or asof)
    out = []
    for m in membership["members"]:
        tk = m.get("ticker")
        if not tk:
            continue
        out.append({
            "rebalance_date": str(asof), "ticker": str(tk),
            "sector": m.get("sector"), "rev_z": m.get("rev_z"),
            "weight": m.get("weight"), "level": None, "data_through": dt,
        })
    if not out:
        return 0
    # stamp the rebalance-date reference close (the anchor; the fill is T+1 in grade())
    for row in out:
        df = _price_frame(row["ticker"])
        if df is not None:
            close = pd.to_numeric(df.get("close"), errors="coerce")
            d0 = pd.Timestamp(asof)
            if d0 in close.index and pd.notna(close.loc[d0]):
                row["level"] = round(float(close.loc[d0]), 3)
    try:
        new = pd.DataFrame(out, columns=list(LEDGER_COLUMNS))
        p = _store_path()
        p.parent.mkdir(parents=True, exist_ok=True)
        if p.exists():
            prior = pd.read_parquet(p)
            combined = pd.concat([prior, new], ignore_index=True).drop_duplicates(
                subset=["rebalance_date", "ticker"], keep="first")
        else:
            combined = new
        combined.to_parquet(p, index=False)
        return int(len(combined))
    except Exception as e:  # noqa: BLE001 — grading is additive, never fatal
        log.warning("cn_reversal_sleeve ledger append failed: %s", e)
        return 0


def _price_frame(ticker: str) -> pd.DataFrame | None:
    for g in _PRICE_GROUPS:
        df = store.read(g, str(ticker))
        if df is not None and "close" in df:
            return df
    return None


def _bench_close() -> pd.Series | None:
    df = store.read("china", _BENCH)
    if df is None or "close" not in df:
        return None
    return pd.to_numeric(df["close"], errors="coerce").dropna()


def _t1_fill(df: pd.DataFrame, d0: pd.Timestamp) -> tuple[float | None, bool]:
    """Fill-realistic entry: the first session strictly AFTER the rebalance close (T+1).
    Returns (fill, locked_limit). fill = true Open if collected else (H+L)/2 proxy."""
    idx = df.index
    after = idx[idx > d0]
    if len(after) == 0:
        return None, False
    row = df.loc[after[0]]
    hi, lo, close = row.get("high"), row.get("low"), row.get("close")
    op = row.get("open") if "open" in df.columns else None
    locked = (hi is not None and lo is not None and close is not None
              and pd.notna(hi) and pd.notna(lo) and pd.notna(close)
              and float(hi) == float(lo) == float(close))
    if op is not None and pd.notna(op):
        return float(op), bool(locked)
    if hi is not None and lo is not None and pd.notna(hi) and pd.notna(lo):
        return (float(hi) + float(lo)) / 2.0, bool(locked)
    if close is not None and pd.notna(close):
        return float(close), bool(locked)
    return None, bool(locked)


def _fwd_excess(ticker: str, d0: pd.Timestamp, h: int,
                bench: pd.Series | None) -> float | None:
    """Fill-realistic, CSI300-relative forward excess over `h` sessions from a T+1 entry.
    None when the name doesn't resolve, T+1 is locked (unfillable), or the horizon can't
    mature. Never anchored on a §7 marker date."""
    df = _price_frame(ticker)
    if df is None:
        return None
    fill, locked = _t1_fill(df, d0)
    if fill is None or locked:
        return None
    close = pd.to_numeric(df["close"], errors="coerce").dropna()
    fwd = close[close.index > d0]
    if len(fwd) <= h:
        return None
    name_ret = float(fwd.iloc[h] / fill - 1.0)
    if bench is None:
        return name_ret
    bslice = bench[bench.index > d0]
    if len(bslice) <= h:
        return None
    bench_ret = float(bslice.iloc[h] / bslice.iloc[0] - 1.0)
    return name_ret - bench_ret


def grade() -> dict:
    """Score every matured rebalance, CSI300-relative + fill-realistic. Sleeve-level: the
    graded number is the EW member-mean excess per rebalance (the sleeve's realized return),
    with a Wilson-CI hit rate over rebalances. "accruing" until enough rebalances mature."""
    p = _store_path()
    if not p.exists():
        return {"available": False, "note": "no rebalances logged yet"}
    try:
        df = pd.read_parquet(p)
    except Exception as e:  # noqa: BLE001
        return {"available": False, "note": f"unreadable: {e}"}
    if df.empty:
        return {"available": False, "note": "empty"}

    bench = _bench_close()
    rebal_excess = []            # one EW-member-mean excess per matured rebalance
    per_rebal = []
    for d0s, sub in df.groupby("rebalance_date"):
        d0 = pd.Timestamp(d0s)
        exs = [ex for ex in
               (_fwd_excess(t, d0, _HORIZON_D, bench) for t in sub["ticker"])
               if ex is not None]
        if len(exs) < 3:                          # too few fillable members to grade the leg
            continue
        leg_ex = float(np.mean(exs))
        rebal_excess.append(leg_ex)
        per_rebal.append({"rebalance_date": str(d0s), "n_filled": len(exs),
                          "sleeve_excess": round(leg_ex, 4)})

    out = {
        "available": True, "n_rows": int(len(df)),
        "rebalances": sorted(df["rebalance_date"].dropna().unique().tolist()),
        "horizon_d": _HORIZON_D,
        "grading": {"benchmark": _BENCH, "relative": True, "entry_basis": ENTRY_BASIS,
                    "excludes_locked_limit": True, "anchor": "rebalance_close_then_t1_fill",
                    "marker_dates": "forbidden", "level": "sleeve_ew_member_mean",
                    "bench_available": bench is not None},
        "per_rebalance": per_rebal,
    }
    if len(rebal_excess) < _MIN_GRADED:
        out["graded"] = {"n_rebalances": len(rebal_excess), "note": "accruing"}
        out["n_graded"] = len(rebal_excess)
        return out
    arr = np.array(rebal_excess, dtype=float)
    hit = float((arr > 0).mean())
    lo, hi = _wilson_ci(int((arr > 0).sum()), int(len(arr)))
    sd = float(arr.std(ddof=1)) if len(arr) > 1 else 0.0
    out["graded"] = {
        "n_rebalances": len(arr),
        "mean_excess_per_rebalance": round(float(arr.mean()), 4),
        "median_excess": round(float(np.median(arr)), 4),
        "sharpe_ann": round(float(arr.mean()) / sd * np.sqrt(12), 2) if sd > 0 else None,
        "hit_vs_csi300": round(hit, 4), "hit_ci": [round(lo, 4), round(hi, 4)],
    }
    out["n_graded"] = len(arr)
    return out


def _wilson_ci(k: int, n: int, z: float = 1.96) -> tuple[float, float]:
    if n <= 0:
        return 0.0, 0.0
    phat = k / n
    denom = 1 + z * z / n
    centre = (phat + z * z / (2 * n)) / denom
    half = z * ((phat * (1 - phat) / n + z * z / (4 * n * n)) ** 0.5) / denom
    return max(0.0, centre - half), min(1.0, centre + half)
