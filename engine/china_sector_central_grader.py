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


def _mhash_stable_cn(basket_id: str, d0: pd.Timestamp, h: int, frozen_df) -> bool:
    """Return True iff the China/THS basket's membership hash is stable over [d0, d0+h].

    Checks both 'china' and 'china_ths' domains (whichever has the basket).
    Returns False when uncertain (no frozen data) — grade is dropped rather than silently
    scored across a composition change.
    """
    if frozen_df is None:
        return False
    col = f"{basket_id}__mhash"
    if col not in frozen_df.columns:
        return False
    window = frozen_df.loc[
        (frozen_df.index >= d0) & (frozen_df.index <= d0 + pd.Timedelta(days=h * 2))
    ][col].dropna()
    if window.empty:
        return False
    return window.nunique() == 1


def _basket_levels_cn() -> tuple[dict, object]:
    """Basket level series from the FROZEN store for China + THS domains.

    W3.8: replaces the live compute_china_baskets() path.  Returns (basket_lvl_dict,
    merged_frozen_df).  Before the first freeze both are empty/None and the grader
    reports 'accruing from <freeze_start>'.
    """
    out: dict = {}
    merged_frozen = None
    try:
        from engine.basket_freeze import read_frozen
        for domain in ("china", "china_ths"):
            df = read_frozen(domain)
            if df is None or df.empty:
                continue
            # Merge for mhash checks (union of both domain columns)
            if merged_frozen is None:
                merged_frozen = df
            else:
                merged_frozen = pd.concat([merged_frozen, df], axis=1)
            for col in df.columns:
                if col.endswith("__level_tr"):
                    bid = col[: -len("__level_tr")]
                    s = df[col].dropna()
                    if not s.empty:
                        out[bid] = s
    except Exception as e:  # noqa: BLE001
        log.warning("basket_levels_cn: frozen read failed: %s", e)
    return out, merged_frozen


def _fwd_return(row: pd.Series, h: int, basket_lvl: dict,
                frozen_df=None) -> tuple[float | None, str | None]:
    """Realized return from the call date to call_date + h trading days (sector = Shenwan;
    basket = EW level), or (None, None) if the horizon hasn't elapsed / series missing.

    W3.8: basket calls additionally check membership-hash stability over the forward
    window.  Returns (return_float | None, invalidation_reason | None).
    """
    try:
        from engine import china_sector_index as csi
        d0 = pd.Timestamp(row["date"])
        if row.get("kind") == "sector" and pd.notna(row.get("shenwan_code")):
            s = csi.sw_close(row["shenwan_code"])
            if s is None or s.empty:
                return None, None
            s = s[s.index >= d0]
            if len(s) <= h:
                return None, None
            return float(s.iloc[h] / s.iloc[0] - 1.0), None
        else:
            bid = row.get("basket_id")
            s = basket_lvl.get(bid)
            if s is None or s.empty:
                return None, None
            # W3.8: membership-hash stability check
            if not _mhash_stable_cn(bid, d0, h, frozen_df):
                return None, "membership_changed"
            s = s[s.index >= d0]
            if len(s) <= h:
                return None, None
            return float(s.iloc[h] / s.iloc[0] - 1.0), None
    except Exception:  # noqa: BLE001
        return None, None


def grade() -> dict | None:
    """Score every matured call. Returns a scorecard {n_calls, n_graded, dates, by_horizon}.

    W3.8 changes:
    - Basket forward returns read from the FROZEN store (data/basket_levels/{china,china_ths}
      .parquet) only.  The live compute_china_baskets() path is gone.
    - Grades whose forward window spans a membership-hash change are INVALIDATED
      (dropped with reason 'membership_changed'; counted in invalidated_membership).
    - Pre-freeze basket calls are NOT graded: the scorecard reports
      'accruing from <freeze_start>' — the permanent survivorship hole (D4-N3 / R1).
    """
    p = config.data_dir() / _STORE[0] / _STORE[1]
    if not p.exists():
        return {"available": False, "note": "no calls logged yet"}
    try:
        df = pd.read_parquet(p)
    except Exception as e:  # noqa: BLE001
        return {"available": False, "note": f"unreadable: {e}"}
    if df.empty:
        return {"available": False, "note": "empty"}

    # W3.8: basket level series from FROZEN store only (no live recompute)
    basket_lvl, frozen_df = _basket_levels_cn()

    # Freeze-start for transparency reporting (earliest frozen date across china + china_ths)
    freeze_start = None
    try:
        from engine.basket_freeze import freeze_start_date
        starts = [freeze_start_date(d) for d in ("china", "china_ths")]
        valid_starts = [s for s in starts if s]
        freeze_start = min(valid_starts) if valid_starts else None
    except Exception:  # noqa: BLE001
        pass

    bench = None
    try:
        from engine import china_sector_index as csi
        # W0.3 / D4 benchmark basis-match: use price-basis benchmark so that
        # excess = sector_price − bench_price (same basis). benchmark_close_price()
        # prefers 'close_price' (D4-W1 dual-basis) with a logged fallback to 'close'
        # (TR) — for 000001.SS these are empirically identical (no dividend adjustment
        # on equity indices), so the fallback is safe while D4-W1 is pending.
        bench = csi.benchmark_close_price()
    except Exception:  # noqa: BLE001
        pass

    out = {
        "available": True, "n_calls": int(len(df)),
        "dates": sorted(df["date"].dropna().unique().tolist()),
        "horizons_d": list(_HORIZONS_D), "by_horizon": {},
        # W3.8 transparency fields
        "freeze_start": freeze_start,
        "pre_freeze_note": (
            f"Basket grading accruing from {freeze_start} (W3.8 freeze date). "
            "Pre-freeze basket calls are not graded: the series before this date is "
            "permanently survivorship-contaminated (D4-N3)."
            if freeze_start else
            "Basket grading not yet started (no frozen store). "
            "Basket calls will accrue once the first freeze runs."
        ),
    }
    for h in _HORIZONS_D:
        recs = []
        n_invalidated_membership = 0
        for _i, row in df.iterrows():
            fr, inv_reason = _fwd_return(row, h, basket_lvl, frozen_df=frozen_df)
            if inv_reason == "membership_changed":
                n_invalidated_membership += 1
                continue
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
            out["by_horizon"][f"{h}d"] = {
                "n": len(recs), "note": "accruing",
                "invalidated_membership": n_invalidated_membership,
            }
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
            "invalidated_membership": n_invalidated_membership,
        }
    out["n_graded"] = max((v.get("n", 0) for v in out["by_horizon"].values()), default=0)
    return out
