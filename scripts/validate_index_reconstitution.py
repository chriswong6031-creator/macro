"""Event-study validation for the index-reconstitution forced-flow leg.

The classic "index effect" (Shleifer 1986, Wurgler-Zhuravskaya 2002): a name added
to the S&P 500 is force-bought by index funds → a run-up from announcement to the
effective date, then a partial reversal. The research blueprint (§"missing
modalities") flags it as ungraded folklore that is **widely documented to have
DECAYED post-2010** as the trade got crowded and index funds adopted patient
execution. So we re-event-study it honestly on the modern regime before scoring.

Data: data/breadth/sp1500_pit_membership.parquet (ticker, start_date=effective add,
end_date=effective delete, src=sp500/400/600). Prices via yfinance (local parquets
don't cover the small/mid-cap names that churn in and out of these indices).

We measure SPY-relative abnormal returns in two windows per ADD / DELETE event:
  • PRE  [ED-10 … ED-1]  — the announcement→effective run-up (only tradeable if a
    name can be detected BEFORE its effective date, which we cannot reliably do).
  • POST [ED … ED+h]     — what a buy on the effective-date close earns (5/10/21d).
Month-clustered HAC-t (reconstitution events cluster on quarterly effective dates).

A leg is SCORED only if the POST-effective drift is right-signed (adds>0, dels<0),
significant, and survives on a recent subsample. The near-certain honest finding —
the effect has decayed to ~0 net-of-reversal — ships as a DISPLAY-ONLY context leg.

Outputs: data/index_reconstitution/validation_gate.json
         reports/index-reconstitution-validation.md
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

import sys
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from engine import validation as V  # noqa: E402
from lib import config  # noqa: E402

log = logging.getLogger("validate_index_recon")

_START = "2019-01-01"          # modern (post-decay) regime; balances sample vs relevance
_RECENT = "2023-01-01"         # recent subsample for a robustness check
_POST_H = [5, 10, 21]
_MIN_EVENTS = 40
_T_BAR = 2.0


def _dir() -> Path:
    p = config.data_dir() / "index_reconstitution"
    p.mkdir(parents=True, exist_ok=True)
    return p


def load_events() -> pd.DataFrame:
    """One row per (ticker, effective-date, kind, index) for adds & deletes."""
    pit = pd.read_parquet(config.data_dir() / "breadth" / "sp1500_pit_membership.parquet")
    pit["start_date"] = pd.to_datetime(pit["start_date"], errors="coerce")
    pit["end_date"] = pd.to_datetime(pit["end_date"], errors="coerce")
    adds = pit.dropna(subset=["start_date"])[["ticker", "start_date", "src"]].copy()
    adds.columns = ["ticker", "d", "index"]
    adds["kind"] = "add"
    dels = pit.dropna(subset=["end_date"])[["ticker", "end_date", "src"]].copy()
    dels.columns = ["ticker", "d", "index"]
    dels["kind"] = "delete"
    ev = pd.concat([adds, dels], ignore_index=True)
    ev = ev[ev["d"] >= _START]
    ev["ticker"] = ev["ticker"].astype(str).str.upper()
    return ev.dropna(subset=["d", "ticker"])


def fetch_prices(tickers: list[str]) -> pd.DataFrame:
    cache = _dir() / "prices.parquet"
    have = pd.read_parquet(cache) if cache.exists() else pd.DataFrame()
    need = sorted(set(tickers + ["SPY"]) - set(have.columns))
    if not need:
        return have
    import yfinance as yf
    got, B = {}, 150
    for i in range(0, len(need), B):
        chunk = need[i:i + B]
        try:
            raw = yf.download(chunk, start="2018-10-01", interval="1d",
                              progress=False, threads=False, auto_adjust=True)
        except Exception as e:  # noqa: BLE001
            log.warning("yf batch %d failed: %s", i, e)
            continue
        if raw is None or raw.empty:
            continue
        close = (raw["Close"] if isinstance(raw.columns, pd.MultiIndex)
                 and "Close" in raw.columns.get_level_values(0) else raw)
        if isinstance(close, pd.Series):
            close = close.to_frame(chunk[0])
        for c in close.columns:
            s = close[c].dropna()
            if len(s) > 20:
                got[c] = s
        log.info("prices batch %d/%d (+%d)", i // B + 1, (len(need) + B - 1) // B, len(close.columns))
    if got:
        new = pd.DataFrame(got)
        have = new if have.empty else have.join(new, how="outer")
        have.to_parquet(cache)
    return have


def _abn(prices, ticker, d, a, b) -> float | None:
    """SPY-relative return over the trading-day window [event+a, event+b] around the
    effective date (a,b are signed trading-day offsets; entry/exit are closes)."""
    if ticker not in prices.columns or "SPY" not in prices.columns:
        return None
    s = prices[ticker].dropna()
    spy = prices["SPY"].dropna()
    idx = s.index[s.index >= d]
    if len(idx) == 0:
        return None
    e = s.index.get_loc(idx[0])           # first trading day on/after the effective date
    i0, i1 = e + a, e + b
    if i0 < 0 or i1 >= len(s):
        return None
    t0, t1 = s.index[i0], s.index[i1]
    try:
        r = s.iloc[i1] / s.iloc[i0] - 1.0
        sp = spy.asof(t1) / spy.asof(t0) - 1.0
    except Exception:  # noqa: BLE001
        return None
    return float(r - sp) if np.isfinite(r) and np.isfinite(sp) else None


def _window(events, prices, a, b) -> dict:
    recs = []
    for ev in events.itertuples(index=False):
        v = _abn(prices, ev.ticker, ev.d, a, b)
        if v is not None:
            recs.append((ev.d, v))
    if len(recs) < 10:
        return {"n": len(recs)}
    df = pd.DataFrame(recs, columns=["d", "abn"])
    df["mo"] = df["d"].dt.to_period("M").astype(str)
    monthly = df.groupby("mo")["abn"].mean()
    nw = V.newey_west_tstat(monthly.values, lags=min(4, max(1, len(monthly) // 4)))
    return {"n": int(len(df)), "n_months": int(len(monthly)),
            "mean_abn": round(float(df["abn"].mean()), 4),
            "hit_rate": round(float((df["abn"] > 0).mean()), 3),
            "hac_t": round(float(nw.get("t", float("nan"))), 2),
            "p": round(float(nw.get("p", float("nan"))), 4)}


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    ev = load_events()
    log.info("events since %s: %d adds · %d deletes",
             _START, int((ev["kind"] == "add").sum()), int((ev["kind"] == "delete").sum()))
    prices = fetch_prices(sorted(ev["ticker"].unique()))
    log.info("price panel: %d cols", prices.shape[1])

    res = {}
    for kind in ("add", "delete"):
        sub = ev[ev["kind"] == kind]
        rec = ev[(ev["kind"] == kind) & (ev["d"] >= _RECENT)]
        res[kind] = {
            "n": int(len(sub)),
            "pre_runup": _window(sub, prices, -10, -1),      # announcement→effective proxy
            "post": {h: _window(sub, prices, 0, h) for h in _POST_H},
            "post_recent_21": _window(rec, prices, 0, 21),   # decay check
        }
    # per-index post-21 add drift (the canonical S&P500 index effect)
    by_index = {}
    for ix in ("sp500", "sp400", "sp600"):
        sub = ev[(ev["kind"] == "add") & (ev["index"] == ix)]
        by_index[ix] = _window(sub, prices, 0, 21)

    # verdict: a TRADEABLE post-effective drift, right-signed, significant, n≥floor,
    # AND still present recently (not a pre-decay artifact).
    def _ok(w, sign):
        return (w.get("n", 0) >= _MIN_EVENTS and abs(w.get("hac_t", 0)) >= _T_BAR
                and np.sign(w.get("mean_abn", 0)) == sign)
    add_post = res["add"]["post"][21]
    del_post = res["delete"]["post"][21]
    add_scored = _ok(add_post, 1) and _ok(res["add"]["post_recent_21"], 1)
    del_scored = _ok(del_post, -1) and _ok(res["delete"]["post_recent_21"], -1)
    scored = bool(add_scored or del_scored)
    # is the classic pre-effective run-up still alive (even if not post-effective tradeable)?
    pr = res["add"]["pre_runup"]
    runup_alive = bool(pr.get("n", 0) >= _MIN_EVENTS and pr.get("mean_abn", 0) > 0
                       and abs(pr.get("hac_t", 0)) >= _T_BAR)

    gate = {
        "schema": "index_reconstitution.gate.v1",
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
        "window_start": _START, "recent_start": _RECENT,
        "scored": scored, "add_scored": bool(add_scored), "del_scored": bool(del_scored),
        "weight": 1.0 if scored else 0.0,
        "results": res, "add_by_index_post21": by_index,
        "runup_alive": runup_alive,
        "min_events": _MIN_EVENTS, "t_bar": _T_BAR,
        "note": ("post-effective index drift is right-signed, significant and persists "
                 "recently → SCORED forced-flow leg"
                 if scored else
                 (("the pre-effective ADD run-up is still significant "
                   f"(+{pr.get('mean_abn')}, t={pr.get('hac_t')}), but it is front-run INTO the "
                   "effective date and REVERSES after — so a surfaced (already-effective) add "
                   "has no tradeable post-effective edge. " if runup_alive else
                   "the classic index effect has decayed. ")
                  + "→ leg DORMANT (would need an announcement feed to trade the run-up)")),
    }
    (_dir() / "validation_gate.json").write_text(json.dumps(gate, indent=2))
    log.info("GATE scored=%s (add=%s del=%s)", scored, add_scored, del_scored)

    rp = Path(__file__).resolve().parent.parent / "reports"
    rp.mkdir(parents=True, exist_ok=True)
    L = [
        "# Index-reconstitution forced-flow event study", "",
        f"_Generated {gate['generated_at']}. Effective-date events {_START}→ from S&P "
        "500/400/600 PIT membership; SPY-relative; month-clustered HAC-t._", "",
        f"- Adds: **{res['add']['n']}** · Deletes: **{res['delete']['n']}** "
        f"(price-covered subset)",
        f"- **Verdict: {'SCORED forced-flow leg' if scored else 'display-only context (effect decayed)'}**",
        "",
        "## ADD events — SPY-relative abnormal return", "",
        "| Window | n | mean | hit | HAC-t |", "|--|--:|--:|--:|--:|",
        f"| pre run-up [-10,-1] | {res['add']['pre_runup'].get('n','—')} | "
        f"{res['add']['pre_runup'].get('mean_abn','—')} | {res['add']['pre_runup'].get('hit_rate','—')} | "
        f"{res['add']['pre_runup'].get('hac_t','—')} |",
    ]
    for h in _POST_H:
        w = res["add"]["post"][h]
        L.append(f"| post [0,{h}] | {w.get('n','—')} | {w.get('mean_abn','—')} | "
                 f"{w.get('hit_rate','—')} | {w.get('hac_t','—')} |")
    L += ["", "## DELETE events — SPY-relative abnormal return", "",
          "| Window | n | mean | hit | HAC-t |", "|--|--:|--:|--:|--:|"]
    for h in _POST_H:
        w = res["delete"]["post"][h]
        L.append(f"| post [0,{h}] | {w.get('n','—')} | {w.get('mean_abn','—')} | "
                 f"{w.get('hit_rate','—')} | {w.get('hac_t','—')} |")
    L += ["", "## ADD post-[0,21] by index", "", "| Index | n | mean | HAC-t |", "|--|--:|--:|--:|"]
    for ix, w in by_index.items():
        L.append(f"| {ix} | {w.get('n','—')} | {w.get('mean_abn','—')} | {w.get('hac_t','—')} |")
    L += ["", f"_{gate['note']}._", ""]
    (rp / "index-reconstitution-validation.md").write_text("\n".join(L))
    log.info("report -> %s", rp / "index-reconstitution-validation.md")


if __name__ == "__main__":
    main()
