"""Self-grader for the China Sector Central engine — the piece that makes Phase 2's predictive
power MEASURED, not asserted (the gap the allocation_china audit exposed: nothing in the
rotation stack grades its own calls).

Two halves:
  • append_central_log(data) — append today's per-sector/basket central CALL (conviction score +
    direction + the as-of price level) to an append-only, point-in-time store
    (data/china_sector_central/calls.parquet), keep-FIRST per (date, id) so a past day's stamped
    call is never rewritten.
  • grade(horizons) — for every logged call old enough to have a realized outcome, join the
    forward return (sector = Shenwan close; basket = equal-weight level), and score the engine:
    directional hit-rate (overall + by conviction tier), cross-sectional rank-IC of the
    conviction score vs forward return, and forward return vs the Shanghai Composite. Returns a
    scorecard the dashboard renders honestly (sparse until it accrues).

Display/research-only — the log is NEVER read back into a live score. Additive / fail-soft.
"""
from __future__ import annotations

import logging

import numpy as np
import pandas as pd

from lib import config

log = logging.getLogger(__name__)

_HORIZONS_D = (21, 63, 126)        # ~1/3/6 months — the horizons the audit showed matter
_STORE = ("china_sector_central", "calls.parquet")


def _level_for(row: dict) -> float | None:
    """The as-of price level for a call (sector = Shenwan close; basket = EW level)."""
    try:
        from engine import china_sector_index as csi
        if row.get("kind") == "sector" and row.get("shenwan_code"):
            s = csi.sw_close(row["shenwan_code"])
            return float(s.iloc[-1]) if s is not None and not s.empty else None
    except Exception:  # noqa: BLE001
        pass
    return None


def append_central_log(data: dict) -> int:
    asof = (data or {}).get("as_of")
    if not asof:
        return 0
    rows = []
    for rec in (data.get("sectors", []) + data.get("baskets", [])):
        conv = rec.get("conviction") or {}
        fwd = rec.get("forward") or {}
        rows.append({
            "date": asof, "id": rec.get("id"), "kind": rec.get("kind"),
            "shenwan_code": rec.get("shenwan_code"), "basket_id": rec.get("basket_id"),
            "name": rec.get("name"),
            "score": conv.get("score"), "label": conv.get("label_en"), "dir": conv.get("dir"),
            "confluence": (conv.get("confluence") or {}).get("agree"),
            "fwd_cond_rate": fwd.get("cond_rate"), "fwd_lift": fwd.get("lift"),
            "gate_factor": (rec.get("components") or {}).get("gate_factor"),
            "level": _level_for(rec),
        })
    if not rows:
        return 0
    try:
        new = pd.DataFrame(rows)
        p = config.data_dir() / _STORE[0] / _STORE[1]
        p.parent.mkdir(parents=True, exist_ok=True)
        if p.exists():
            prior = pd.read_parquet(p)
            combined = pd.concat([prior, new], ignore_index=True).drop_duplicates(
                subset=["date", "id"], keep="first")
        else:
            combined = new
        combined.to_parquet(p, index=False)
        return len(new)
    except Exception as e:  # noqa: BLE001
        log.warning("central grader: append failed: %s", e)
        return 0


def _fwd_return(row: pd.Series, h: int, basket_lvl: dict) -> float | None:
    """Realized return from the call date to call_date + h trading days (sector = Shenwan;
    basket = EW level), or None if the horizon hasn't elapsed / series missing."""
    try:
        from engine import china_sector_index as csi
        d0 = pd.Timestamp(row["date"])
        if row.get("kind") == "sector" and pd.notna(row.get("shenwan_code")):
            s = csi.sw_close(row["shenwan_code"])
        else:
            s = basket_lvl.get(row.get("basket_id"))
        if s is None or s.empty:
            return None
        s = s[s.index >= d0]
        if len(s) <= h:
            return None
        return float(s.iloc[h] / s.iloc[0] - 1.0)
    except Exception:  # noqa: BLE001
        return None


def grade() -> dict | None:
    """Score every matured call. Returns a scorecard {n_calls, n_graded, dates, by_horizon}."""
    p = config.data_dir() / _STORE[0] / _STORE[1]
    if not p.exists():
        return {"available": False, "note": "no calls logged yet"}
    try:
        df = pd.read_parquet(p)
    except Exception as e:  # noqa: BLE001
        return {"available": False, "note": f"unreadable: {e}"}
    if df.empty:
        return {"available": False, "note": "empty"}

    # basket level series (for grading basket calls)
    basket_lvl = {}
    try:
        from engine.baskets_china import compute_china_baskets
        bd = compute_china_baskets()
        if bd and bd.get("chart"):
            ch = bd["chart"]; idx = pd.to_datetime(ch["dates"])
            for bid, lv in (ch.get("baskets") or {}).items():
                basket_lvl[bid] = pd.Series(lv, index=idx, dtype="float64").dropna()
    except Exception:  # noqa: BLE001
        pass

    bench = None
    try:
        from engine import china_sector_index as csi
        bench = csi.benchmark_close()
    except Exception:  # noqa: BLE001
        pass

    out = {"available": True, "n_calls": int(len(df)),
           "dates": sorted(df["date"].dropna().unique().tolist()),
           "horizons_d": list(_HORIZONS_D), "by_horizon": {}}
    for h in _HORIZONS_D:
        recs = []
        for _i, row in df.iterrows():
            fr = _fwd_return(row, h, basket_lvl)
            if fr is None:
                continue
            br = None
            if bench is not None:
                d0 = pd.Timestamp(row["date"]); bb = bench[bench.index >= d0]
                if len(bb) > h:
                    br = float(bb.iloc[h] / bb.iloc[0] - 1.0)
            recs.append({"date": row["date"], "score": row.get("score"), "dir": row.get("dir"),
                         "label": row.get("label"), "fwd": fr,
                         "excess": (fr - br) if br is not None else None})
        if len(recs) < 3:
            out["by_horizon"][f"{h}d"] = {"n": len(recs), "note": "accruing"}
            continue
        g = pd.DataFrame(recs)
        # directional hit-rate (up call → positive fwd; down call → negative)
        up = g[g["dir"] == "up"]; dn = g[g["dir"] == "down"]
        hit = float(((up["fwd"] > 0).sum() + (dn["fwd"] < 0).sum()) / len(g)) if len(g) else None
        # cross-sectional rank-IC per date (score vs fwd), averaged
        ics = []
        for d, sub in g.groupby("date"):
            if sub["score"].nunique() >= 3:
                ics.append(float(sub["score"].rank().corr(sub["fwd"].rank())))
        # by tier
        by_tier = {}
        for lab, sub in g.groupby("label"):
            if len(sub) >= 3:
                by_tier[lab] = {"n": int(len(sub)), "mean_fwd": round(float(sub["fwd"].mean()), 4),
                                "mean_excess": (round(float(sub["excess"].dropna().mean()), 4)
                                                if sub["excess"].notna().any() else None),
                                "pos_rate": round(float((sub["fwd"] > 0).mean()), 3)}
        out["by_horizon"][f"{h}d"] = {
            "n": int(len(g)), "dir_hit_rate": round(hit, 3) if hit is not None else None,
            "rank_ic": round(float(np.mean(ics)), 4) if ics else None, "n_ic_dates": len(ics),
            "mean_excess_vs_bench": (round(float(g["excess"].dropna().mean()), 4)
                                     if g["excess"].notna().any() else None),
            "by_tier": by_tier,
        }
    out["n_graded"] = max((v.get("n", 0) for v in out["by_horizon"].values()), default=0)
    return out
