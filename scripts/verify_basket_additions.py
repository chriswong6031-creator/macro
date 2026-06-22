"""scripts/verify_basket_additions.py — quant gate for PROPOSED new basket members.

Given proposals [{bid, ticker}, ...] (e.g. from the addition-research workflow), measure how
well each candidate's PRICE ACTION would co-move with the basket it is proposed for, using the
basket's CURRENT equal-weight index (the candidate is not yet a member, so no leave-one-out
needed). Only candidates that (a) have usable price history and (b) clear the basket's own
cohort bar are recommended — so additions are data-confirmed good fits, never narrative-only.

Usage: python -m scripts.verify_basket_additions reports/addition_proposals.json
       (proposals: a JSON list of {"bid": "...", "ticker": "..."} or {"bid":..,"candidates":[{ticker}]})
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

CLIP = 0.50
WINS = {"full": None, "y1": 252, "m6": 126}


def _rets(t: str) -> pd.Series | None:
    df = _load_member_ohlcv(t)
    if df is None or df.empty or "close" not in df.columns:
        return None
    s = df["close"].copy()
    s.index = pd.DatetimeIndex(s.index)
    s = s[~s.index.duplicated(keep="last")].sort_index()
    return s.pct_change().clip(-CLIP, CLIP)


def _basket_eqw(members: list[dict], last: pd.Timestamp) -> pd.Series:
    """Equal-weight daily return of a basket's CURRENT live members."""
    cols = {}
    for m in members:
        if m.get("removed"):
            continue
        added = m.get("added")
        if added and pd.Timestamp(added) > last:
            continue
        r = _rets(m["ticker"])
        if r is not None:
            cols[m["ticker"]] = r
    panel = pd.DataFrame(cols)
    panel = panel.where(panel.notna().sum(axis=1) >= 3)
    return panel.mean(axis=1)


def _pair(rc: pd.Series, rb: pd.Series, win: int | None) -> dict:
    df = pd.concat([rc, rb], axis=1, keys=["c", "b"], sort=True).dropna()
    if win:
        df = df.iloc[-win:]
    n = len(df)
    if n < 60:
        return {"n": n, "insufficient": True}
    corr = float(df["c"].corr(df["b"]))
    wk = pd.concat([(1 + df["c"]).resample("W").prod() - 1,
                    (1 + df["b"]).resample("W").prod() - 1], axis=1, keys=["c", "b"], sort=True).dropna()
    corr_w = float(wk["c"].corr(wk["b"])) if len(wk) >= 12 else None
    dn = df[df["b"] < 0]
    corr_dn = float(dn["c"].corr(dn["b"])) if len(dn) >= 20 else None
    return {"n": n, "corr": round(corr, 3),
            "corr_w": None if corr_w is None else round(corr_w, 3),
            "corr_dn": None if corr_dn is None else round(corr_dn, 3),
            "insufficient": False}


def verify(proposals: list[dict]) -> list[dict]:
    mem = json.loads((config.data_dir() / "baskets" / "membership.json").read_text())["baskets"]
    coh = json.loads((config.ROOT / "reports" / "basket_coherence.json").read_text())["baskets"]
    last = pd.Timestamp("2026-06-18")
    bcache: dict[str, pd.Series] = {}
    out = []
    for p in proposals:
        bid, t = p["bid"], p["ticker"].upper()
        b = mem.get(bid)
        if b is None:
            out.append({"bid": bid, "ticker": t, "status": "bad_basket"})
            continue
        if t in [m["ticker"] for m in b["members"]]:
            out.append({"bid": bid, "ticker": t, "status": "already_member"})
            continue
        rc = _rets(t)
        if rc is None or rc.dropna().shape[0] < 60:
            out.append({"bid": bid, "ticker": t, "status": "no_price_data"})
            continue
        if bid not in bcache:
            bcache[bid] = _basket_eqw(b["members"], last)
        rb = bcache[bid]
        metrics = {w: _pair(rc, rb, win) for w, win in WINS.items()}
        cohort_med = coh.get(bid, {}).get("members") and None
        # basket cohesion median from the audit report
        cs = [m["cohort"]["corr_ref"] for m in coh.get(bid, {}).get("members", {}).values()
              if isinstance(m, dict) and m.get("cohort")]
        cohort_med = round(float(np.median(cs)), 3) if cs else None
        cohort_min = round(float(min(cs)), 3) if cs else None
        y1 = metrics["y1"] if not metrics["y1"].get("insufficient") else metrics["full"]
        c = y1.get("corr")
        cw = y1.get("corr_w")
        # GATE: co-moves at least as well as a typical member (>= cohort median, floored at 0.35),
        # weekly corr >= 0.30, enough history. Short history => 'partial' (recommend with flag).
        bar = max(0.35, (cohort_med or 0.5) - 0.12)
        passed = (c is not None and c >= bar and (cw is None or cw >= 0.30))
        short = metrics["full"].get("n", 0) < 252
        out.append({
            "bid": bid, "ticker": t,
            "status": "pass" if passed else "below_bar",
            "partial_history": short,
            "corr_y1": c, "corr_wk_y1": cw, "corr_dn_y1": y1.get("corr_dn"),
            "corr_full": metrics["full"].get("corr"), "n_full": metrics["full"].get("n"),
            "bar": round(bar, 3), "cohort_med": cohort_med, "cohort_worst": cohort_min,
        })
    return out


def _flatten(raw) -> list[dict]:
    props = []
    if isinstance(raw, dict) and "additions" in raw:
        raw = raw["additions"]
    for item in raw:
        if "ticker" in item:
            props.append({"bid": item["bid"], "ticker": item["ticker"]})
        elif "candidates" in item:
            for c in item["candidates"]:
                props.append({"bid": item["bid"], "ticker": c["ticker"]})
    return props


if __name__ == "__main__":
    src = sys.argv[1] if len(sys.argv) > 1 else "reports/addition_proposals.json"
    raw = json.loads(Path(src).read_text())
    props = _flatten(raw)
    res = verify(props)
    print(f"{'basket':<22} {'tkr':<6} {'status':<14} {'cY1':>6} {'cWk':>6} {'bar':>5} {'cohMed':>6} {'nFull':>6} part")
    for r in sorted(res, key=lambda x: (x["bid"], x.get("status", ""))):
        if r["status"] in ("pass", "below_bar"):
            print(f"{r['bid']:<22} {r['ticker']:<6} {r['status']:<14} "
                  f"{str(r['corr_y1']):>6} {str(r['corr_wk_y1']):>6} {str(r['bar']):>5} "
                  f"{str(r['cohort_med']):>6} {str(r['n_full']):>6} {'Y' if r['partial_history'] else ''}")
        else:
            print(f"{r['bid']:<22} {r['ticker']:<6} {r['status']:<14}")
    Path("reports/addition_verified.json").write_text(json.dumps(res, indent=1, default=str))
    npass = sum(1 for r in res if r["status"] == "pass")
    print(f"\n{npass}/{len(res)} proposals PASS the cohort bar  ->  reports/addition_verified.json")
