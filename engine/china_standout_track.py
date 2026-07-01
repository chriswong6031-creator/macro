"""Board-ORDER forward track-record for the China standout strip — the keystone the review called
for. The per-name POTENTIAL grader ([[china-name-potential-score]] → engine/name_score_grader)
scores potential_score rank-IC; it does NOT observe the ``signal_gate.blend_sorted`` BOARD ORDER
(cascade tier × setup percentile × washout/extension bonus) that actually decides which names sit
at the TOP of china_stocks.html. So nothing today measures the user's exact worry — "the top pick
already ran / underperforms". This ledger closes that gap:

  • append_board(rows, asof) — append today's ranked top-N standout rows (board_rank, ticker, tier,
    setup, extended, washout, and the as-of close `level`) to an append-only, point-in-time store,
    keep-FIRST per (date, ticker) so a logged rank is never overwritten / leaked.
  • grade() — for every matured row join the name's forward return (data/china close store) and
    report, per horizon: TOP-decile vs rest mean forward return, the board RANK-IC (rank vs forward
    — a well-ordered board has a NEGATIVE rank-IC: rank #1 should outperform), and EXTENDED-vs-not
    forward (does the anti-chase demote actually flag underperformers?). "accruing" until enough.

This is the honest prerequisite for promoting the anti-chase extension DEMOTE to a HARD veto: only
once grade() shows extended top-of-board names underperform should the veto go live. Append-only,
point-in-time, keep-first (leak-free). RESEARCH / display telemetry — never a trade trigger.
Mirrors engine/name_score_grader. See [[signal-track-record-logger]]."""
from __future__ import annotations

import logging

import numpy as np
import pandas as pd

from lib import config, store

log = logging.getLogger(__name__)

_HORIZONS_D = (21, 63)                    # ~1 / 3 months
_TOP_DECILE = 0.10
_STORE = "china_standout_track"


def _store_path():
    return config.data_dir() / _STORE / "board.parquet"


def append_board(rows: list[dict], asof: str | None = None, top_n: int = 60) -> int:
    """Append today's ranked top-N standout rows. Each row is a china_standouts `buy` entry (already
    in board order); we stamp its 1-based board_rank + the fields the grade needs. Keep-FIRST per
    (date, ticker). Returns the ledger row count after the merge. Best-effort — never raises."""
    if not rows or not asof:
        return 0
    out = []
    for i, r in enumerate(rows[:top_n]):
        tk = r.get("ticker")
        if not tk:
            continue
        ext = r.get("extension") or {}
        sig = r.get("signal") or {}
        out.append({
            "date": str(asof), "ticker": str(tk), "board_rank": i + 1,
            "tier": sig.get("tier_cascade"),
            "setup": r.get("setup"),
            "extended": bool(ext.get("extended")),
            "washout": bool(r.get("washout_2w")),
            "level": r.get("price"),
        })
    if not out:
        return 0
    try:
        new = pd.DataFrame(out)
        p = _store_path()
        p.parent.mkdir(parents=True, exist_ok=True)
        if p.exists():
            prior = pd.read_parquet(p)
            combined = pd.concat([prior, new], ignore_index=True).drop_duplicates(
                subset=["date", "ticker"], keep="first")
        else:
            combined = new
        combined.to_parquet(p, index=False)
        return int(len(combined))
    except Exception as e:  # noqa: BLE001 — grading is additive, never fatal
        log.warning("china standout board-track append failed: %s", e)
        return 0


def _fwd_return(ticker: str, d0: pd.Timestamp, h: int) -> float | None:
    try:
        df = store.read("china", str(ticker))
        if df is None or "close" not in df:
            return None
        s = pd.to_numeric(df["close"], errors="coerce").dropna()
        s = s[s.index >= d0]
        if len(s) <= h:
            return None
        return float(s.iloc[h] / s.iloc[0] - 1.0)
    except Exception:  # noqa: BLE001
        return None


def grade() -> dict:
    """Score every matured board row. {available, n_rows, dates, by_horizon} where each horizon
    carries top-decile vs rest mean forward return, the board rank-IC, and extended-vs-not forward."""
    p = _store_path()
    if not p.exists():
        return {"available": False, "note": "no board rows logged yet"}
    try:
        df = pd.read_parquet(p)
    except Exception as e:  # noqa: BLE001
        return {"available": False, "note": f"unreadable: {e}"}
    if df.empty:
        return {"available": False, "note": "empty"}

    out = {"available": True, "n_rows": int(len(df)),
           "dates": sorted(df["date"].dropna().unique().tolist()),
           "horizons_d": list(_HORIZONS_D), "by_horizon": {}}
    for h in _HORIZONS_D:
        recs = []
        for _i, row in df.iterrows():
            fr = _fwd_return(row["ticker"], pd.Timestamp(row["date"]), h)
            if fr is None:
                continue
            recs.append({"date": row["date"], "rank": row.get("board_rank"),
                         "extended": bool(row.get("extended")), "fwd": fr})
        if len(recs) < 8:
            out["by_horizon"][f"{h}d"] = {"n": len(recs), "note": "accruing"}
            continue
        g = pd.DataFrame(recs)
        # board rank-IC per date (rank vs forward; NEGATIVE = a well-ordered board)
        ics = []
        for _d, sub in g.groupby("date"):
            if sub["rank"].nunique() >= 5:
                ics.append(float(sub["rank"].rank().corr(sub["fwd"].rank())))
        # top-decile (by best rank) vs the rest
        g = g.sort_values("rank")
        k = max(1, int(round(len(g) * _TOP_DECILE)))
        top_fwd = float(g.head(k)["fwd"].mean())
        rest_fwd = float(g.tail(len(g) - k)["fwd"].mean()) if len(g) > k else None
        ext = g[g["extended"]]
        non = g[~g["extended"]]
        out["by_horizon"][f"{h}d"] = {
            "n": int(len(g)),
            "top_decile_fwd": round(top_fwd, 4),
            "rest_fwd": round(rest_fwd, 4) if rest_fwd is not None else None,
            "board_rank_ic": round(float(np.mean(ics)), 4) if ics else None, "n_ic_dates": len(ics),
            "extended_fwd": round(float(ext["fwd"].mean()), 4) if len(ext) >= 5 else None,
            "not_extended_fwd": round(float(non["fwd"].mean()), 4) if len(non) >= 5 else None,
            "n_extended": int(len(ext)),
        }
    out["n_graded"] = max((v.get("n", 0) for v in out["by_horizon"].values()), default=0)
    return out
