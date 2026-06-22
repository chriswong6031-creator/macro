"""scripts/basket_coherence_audit.py — does each member's PRICE ACTION belong in its basket?

For every US thematic basket (data/baskets/membership.json), measure how well each LIVE
member co-moves with the basket it sits in, using a LEAVE-ONE-OUT equal-weight index so a
member is never correlated against itself. Emits a rich per-member metric table + cohort-
relative outlier flags so miscategorised names (whose tape diverges from the theme and so
SKEW the equal-weight index) can be weeded out and the basket reads as a faithful theme proxy.

Pure measurement — no thresholds are acted on here; it prints distributions + candidate flags
so the criteria can be calibrated against the real cross-section. Reuses the canonical deep
OHLCV loader (engine.basket_index._load_member_ohlcv) so the prices match the live index.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from engine.basket_index import _load_member_ohlcv  # noqa: E402
from lib import config  # noqa: E402

WINDOWS = {"full": None, "y3": 756, "y1": 252, "m6": 126, "m3": 63}
CLIP = 0.50            # winsorise daily returns at +/-50% (kill split/print artefacts)
MIN_OBS = {"full": 120, "y3": 250, "y1": 200, "m6": 100, "m3": 50}


def _closes(ticker: str) -> pd.Series | None:
    df = _load_member_ohlcv(ticker)
    if df is None or df.empty or "close" not in df.columns:
        return None
    s = df["close"].copy()
    s.index = pd.DatetimeIndex(s.index)
    s = s[~s.index.duplicated(keep="last")].sort_index()
    return s


def _rets(s: pd.Series) -> pd.Series:
    r = s.pct_change()
    return r.clip(-CLIP, CLIP)


def _live_members(b: dict, last: pd.Timestamp) -> list[dict]:
    out = []
    for m in b.get("members", []):
        t = m.get("ticker")
        if not t:
            continue
        added = m.get("added")
        removed = m.get("removed")
        if added and pd.Timestamp(added) > last:
            continue
        if removed and pd.Timestamp(removed) <= last:
            continue
        out.append(m)
    return out


def _metrics(r_m: pd.Series, r_loo: pd.Series, win: int | None, key: str) -> dict | None:
    """Co-movement of member returns r_m vs leave-one-out basket returns r_loo over a window."""
    df = pd.concat([r_m, r_loo], axis=1, keys=["m", "b"]).dropna()
    if win:
        df = df.iloc[-win:]
    n = len(df)
    if n < MIN_OBS[key]:
        return {"n": n, "insufficient": True}
    rm, rb = df["m"], df["b"]
    corr = float(rm.corr(rb))
    # weekly (5d) returns — less microstructure noise, the cleaner "trend together" read
    wk = pd.concat([(1 + rm).resample("W").prod() - 1, (1 + rb).resample("W").prod() - 1],
                   axis=1, keys=["m", "b"]).dropna()
    corr_w = float(wk["m"].corr(wk["b"])) if len(wk) >= 12 else None
    sign_w = float((np.sign(wk["m"]) == np.sign(wk["b"])).mean()) if len(wk) >= 12 else None
    # downside co-movement: corr on the basket's down days (does it fall WITH the theme?)
    dn = df[df["b"] < 0]
    corr_dn = float(dn["m"].corr(dn["b"])) if len(dn) >= max(20, MIN_OBS[key] // 3) else None
    beta = float(np.cov(rm, rb)[0, 1] / np.var(rb)) if np.var(rb) > 0 else None
    # trajectory divergence: total compounded return gap vs the cohort over the window
    tot_m = float((1 + rm).prod() - 1)
    tot_b = float((1 + rb).prod() - 1)
    return {
        "n": n, "corr": round(corr, 3),
        "corr_w": None if corr_w is None else round(corr_w, 3),
        "corr_dn": None if corr_dn is None else round(corr_dn, 3),
        "sign_w": None if sign_w is None else round(sign_w, 3),
        "r2": round(corr * corr, 3),
        "beta": None if beta is None else round(beta, 2),
        "ret": round(tot_m, 3), "ret_basket": round(tot_b, 3),
        "ret_gap": round(tot_m - tot_b, 3),
        "insufficient": False,
    }


def audit() -> dict:
    mem = json.loads((config.data_dir() / "baskets" / "membership.json").read_text())
    baskets = mem["baskets"]
    # last common date across the store
    last = max((s.index.max() for s in (_closes(m["ticker"])
               for b in baskets.values() for m in b["members"]) if s is not None))
    out = {"as_of": str(last.date()), "baskets": {}}
    for bid, b in baskets.items():
        live = _live_members(b, last)
        series = {m["ticker"]: _rets(s) for m in live
                  if (s := _closes(m["ticker"])) is not None}
        tickers = list(series.keys())
        if len(tickers) < 4:
            out["baskets"][bid] = {"name": b.get("name"), "n": len(tickers), "thin": True}
            continue
        panel = pd.DataFrame(series)
        members = {}
        for t in tickers:
            others = [x for x in tickers if x != t]
            # leave-one-out equal-weight basket return; need >=3 others present each day
            loo = panel[others]
            loo = loo.where(loo.notna().sum(axis=1) >= 3)
            r_loo = loo.mean(axis=1)
            mrow = {w: _metrics(panel[t], r_loo, win, w) for w, win in WINDOWS.items()}
            members[t] = mrow
        # cohort-relative outlier read: rank each member's 1y (fallback full) daily corr
        ref = {}
        for t in tickers:
            m1 = members[t].get("y1") or {}
            mf = members[t].get("full") or {}
            c = m1.get("corr") if not m1.get("insufficient") else mf.get("corr")
            if c is not None:
                ref[t] = c
        if ref:
            vals = np.array(list(ref.values()))
            med = float(np.median(vals))
            mad = float(np.median(np.abs(vals - med))) or 1e-9
            for t, c in ref.items():
                members[t]["cohort"] = {
                    "corr_ref": round(c, 3), "cohort_med": round(med, 3),
                    "dev_mad": round((c - med) / (1.4826 * mad), 2),
                    "rank": round(float((vals <= c).mean()), 3),
                    "is_min": bool(c == vals.min()),
                }
        out["baskets"][bid] = {
            "name": b.get("name"), "category": b.get("category"),
            "n": len(tickers), "thesis": b.get("thesis", "")[:200],
            "members": members,
        }
    return out


if __name__ == "__main__":
    rep = audit()
    p = config.ROOT / "reports" / "basket_coherence.json"
    p.parent.mkdir(exist_ok=True)
    p.write_text(json.dumps(rep, indent=1, default=str))
    print(f"wrote {p}  ({len(rep['baskets'])} baskets, as_of {rep['as_of']})")
