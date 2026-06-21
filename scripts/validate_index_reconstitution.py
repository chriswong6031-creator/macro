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
from engine.index_changes import classify_cohort, pit_history  # noqa: E402
from lib import config  # noqa: E402

log = logging.getLogger("validate_index_recon")

_START = "2019-01-01"          # modern (post-decay) regime; balances sample vs relevance
_RECENT = "2023-01-01"         # recent subsample for a robustness check
_POST_H = [5, 10, 21]
_ANNOUNCE_WINDOW = (-5, 0)     # announcement→effective capture window (S&P announces ~5 td prior)
_MIN_EVENTS = 40
_T_BAR = 2.0
# realistic round-trip transaction cost by index tier (bid-ask + impact over a ~5d small-cap hold)
_NET_COST = {"sp500": 0.002, "sp400": 0.006, "sp600": 0.012}


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


# cohort classification (pure/migration/readd) lives in engine/index_changes — imported above.


def fetch_prices(tickers: list[str]) -> pd.DataFrame:
    cache = _dir() / "prices.parquet"
    att_path = _dir() / "prices_attempted.json"
    have = pd.read_parquet(cache) if cache.exists() else pd.DataFrame()
    # remember tickers we've already TRIED (incl. delisted ones that never resolve) so each
    # run doesn't re-hammer yfinance for hundreds of dead symbols. Tied to the price cache:
    # if prices.parquet is gone, ignore a stale attempted-list (re-fetch from scratch).
    attempted = (set(json.loads(att_path.read_text()))
                 if (cache.exists() and att_path.exists()) else set())
    need = sorted(set(tickers + ["SPY"]) - set(have.columns) - attempted)
    if not need:
        return have
    import yfinance as yf
    got, B = {}, 150
    newly_tried = set()                          # mark attempted ONLY for batches that RESPONDED —
    for i in range(0, len(need), B):             # an errored batch must retry next run, not stick
        chunk = need[i:i + B]
        try:
            raw = yf.download(chunk, start="2018-10-01", interval="1d",
                              progress=False, threads=False, auto_adjust=True)
        except Exception as e:  # noqa: BLE001
            log.warning("yf batch %d failed: %s — will retry next run", i, e)
            continue                             # NOT marked attempted (network error, not dead)
        newly_tried |= set(chunk)                # batch responded → these names are now "tried"
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
    if newly_tried:                              # persist only names whose batch actually responded
        att_path.write_text(json.dumps(sorted(attempted | newly_tried)))
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


def _window(events, prices, a, b, cost=0.0) -> dict:
    recs = []
    for ev in events.itertuples(index=False):
        v = _abn(prices, ev.ticker, ev.d, a, b)
        if v is not None:
            recs.append((ev.d, v - cost))         # subtract round-trip cost for a net read
    if len(recs) < 10:
        return {"n": len(recs)}
    df = pd.DataFrame(recs, columns=["d", "abn"])
    df["mo"] = df["d"].dt.to_period("M").astype(str)
    monthly = df.groupby("mo")["abn"].mean()
    nw = V.newey_west_tstat(monthly.values, lags=min(4, max(1, len(monthly) // 4)))
    out = {"n": int(len(df)), "n_months": int(len(monthly)),
           "mean_abn": round(float(df["abn"].mean()), 4),
           "median_abn": round(float(df["abn"].median()), 4),
           "hit_rate": round(float((df["abn"] > 0).mean()), 3)}
    # newey_west_tstat returns t/p = None when <8 monthly obs — OMIT them (don't float(None));
    # the _ok/_net_tradeable consumers .get('hac_t', 0) → fail closed (not scored). Fail-safe.
    t, p = nw.get("t"), nw.get("p")
    if t is not None:
        out["hac_t"] = round(float(t), 2)
    if p is not None:
        out["p"] = round(float(p), 4)
    return out


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

    def _ok(w, sign):
        return (w.get("n", 0) >= _MIN_EVENTS and abs(w.get("hac_t", 0)) >= _T_BAR
                and np.sign(w.get("mean_abn", 0)) == sign)

    # ANNOUNCEMENT-CAPTURE window [-5,0]: what a trader earns buying an ADD at announcement
    # (~5 td before effective) and holding through the effective close — the only capturable
    # slice (post-effective has reversed). HONEST DECOMPOSITION (Vijh-Wang 2022): the edge is
    # ENTIRELY in PURE/net-new adds (no offsetting forced seller); MIGRATIONS (400→500 etc.) have
    # a forced seller and ~no edge. And it must survive NET of small-cap transaction cost.
    a0, a1 = _ANNOUNCE_WINDOW
    pit_by_t = pit_history()
    adds = ev[ev["kind"] == "add"].copy()
    adds["cohort"] = [classify_cohort(r.ticker, r.d, r.index, pit_by_t) for r in adds.itertuples(index=False)]
    pure = adds[adds["cohort"] == "pure"]
    pure_rec = pure[pure["d"] >= _RECENT]
    # gross pure by index + net-of-cost by index (cost per tier)
    pure_by_index = {ix: _window(pure[pure["index"] == ix], prices, a0, a1) for ix in ("sp500", "sp400", "sp600")}
    pure_net_by_index = {ix: _window(pure[pure["index"] == ix], prices, a0, a1, cost=_NET_COST[ix])
                         for ix in ("sp500", "sp400", "sp600")}
    announce = {
        "window": list(_ANNOUNCE_WINDOW),
        "all_cohorts": _window(adds, prices, a0, a1),
        "pure_gross": _window(pure, prices, a0, a1),
        "pure_gross_recent": _window(pure_rec, prices, a0, a1),
        "migration_gross": _window(adds[adds["cohort"] == "migration"], prices, a0, a1),  # the control: ~0
        "pure_by_index": pure_by_index,
        "pure_net_by_index": pure_net_by_index,
        "net_cost_assumed": _NET_COST,
        "cohort_counts": {k: int(v) for k, v in adds["cohort"].value_counts().items()},
    }

    # verdict: a TRADEABLE post-effective drift, right-signed, significant, n≥floor,
    # AND still present recently (not a pre-decay artifact).
    add_post = res["add"]["post"][21]
    del_post = res["delete"]["post"][21]
    add_scored = _ok(add_post, 1) and _ok(res["add"]["post_recent_21"], 1)
    del_scored = _ok(del_post, -1) and _ok(res["delete"]["post_recent_21"], -1)
    scored = bool(add_scored or del_scored)
    # ANNOUNCE GATES — two honest flags. GROSS: the pure-add [-5,0] run-up is real & recent.
    # NET: it survives small-cap costs AND the TYPICAL name wins (median>0, hit>0.5) — the bar
    # for a scored alpha. Our data: gross passes, NET FAILS (median net<0, hit<0.5 for sp600) →
    # the live leg is DISPLAY-ONLY context, never a scored sizer.
    def _net_tradeable(w):
        return (w.get("n", 0) >= _MIN_EVENTS and w.get("mean_abn", 0) > 0
                and abs(w.get("hac_t", 0)) >= _T_BAR
                and w.get("median_abn", -1) > 0 and w.get("hit_rate", 0) > 0.5)
    announce_gross_scored = bool(_ok(announce["pure_gross"], 1) and _ok(announce["pure_gross_recent"], 1))
    announce_net_scored = bool(any(_net_tradeable(w) for w in pure_net_by_index.values()))
    # per-index tiers where the PURE gross edge lives (informs which indices the context leg surfaces)
    announce_tiers = {ix: bool(_ok(w, 1)) for ix, w in pure_by_index.items()}
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
        # the announcement-capture leg: gross-vs-net verdict + per-index tiers. The LIVE leg
        # surfaces fresh PURE adds as CONTEXT; it scores ONLY if announce_net_scored (it doesn't).
        "announce": announce,
        "announce_gross_scored": announce_gross_scored,
        "announce_net_scored": announce_net_scored,
        "announce_tiers": announce_tiers,
        "min_events": _MIN_EVENTS, "t_bar": _T_BAR,
        "note": ((f"PURE/net-new ADD announcement→effective [-5,0] run-up is real & recent "
                  f"(+{announce['pure_gross'].get('mean_abn')}, t={announce['pure_gross'].get('hac_t')}; "
                  f"recent t={announce['pure_gross_recent'].get('hac_t')}); migrations are ~0 "
                  f"(t={announce['migration_gross'].get('hac_t')}) — so screen to PURE adds. "
                  + ("BUT net of small-cap cost the TYPICAL name loses "
                     f"(sp600 net median={announce['pure_net_by_index']['sp600'].get('median_abn')}, "
                     f"hit={announce['pure_net_by_index']['sp600'].get('hit_rate')}) → a NET-OF-COST "
                     "MIRAGE. Leg ships DISPLAY-ONLY context (fresh pure-add catalysts), scoring gate "
                     "CLOSED; the net edge lives only in the announcement-overnight gap, which needs "
                     "intraday opens to validate." if not announce_net_scored else
                     "AND it survives net of cost with the typical name winning → SCORED."))),
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
    def _row(label, w):
        return (f"| {label} | {w.get('n','—')} | {w.get('mean_abn','—')} | {w.get('median_abn','—')} | "
                f"{w.get('hit_rate','—')} | {w.get('hac_t','—')} |")
    L += ["", f"## ADD announcement-capture window {list(_ANNOUNCE_WINDOW)} — pure vs migration, gross vs net",
          "", f"_Buy at announcement (~5 td before effective), hold through the effective close. "
          f"Cohorts: {announce['cohort_counts']}. **announce_gross_scored={announce_gross_scored} · "
          f"announce_net_scored={announce_net_scored}** (net cost assumed {_NET_COST})._", "",
          "| Cohort / index | n | mean | median | hit | HAC-t |", "|--|--:|--:|--:|--:|--:|",
          _row("PURE gross", announce["pure_gross"]),
          _row(f"PURE gross recent ({_RECENT}+)", announce["pure_gross_recent"]),
          _row("MIGRATION gross (control)", announce["migration_gross"])]
    for ix in ("sp500", "sp400", "sp600"):
        L.append(_row(f"pure {ix} gross", announce["pure_by_index"][ix]))
    for ix in ("sp500", "sp400", "sp600"):
        L.append(_row(f"pure {ix} NET (−{_NET_COST[ix]:.1%})", announce["pure_net_by_index"][ix]))
    L += ["", f"_{gate['note']}._", ""]
    (rp / "index-reconstitution-validation.md").write_text("\n".join(L))
    log.info("report -> %s", rp / "index-reconstitution-validation.md")


if __name__ == "__main__":
    main()
