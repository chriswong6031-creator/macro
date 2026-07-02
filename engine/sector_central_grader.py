"""Self-grader for the US Sector Central engine — the piece that makes the conviction calls
MEASURED, not asserted (the same discipline the China central uses).

Two halves:
  • append_central_log(data) — append today's per-sector/basket central CALL (conviction score +
    direction + the as-of price level) to an append-only, point-in-time store
    (data/sector_central/calls.parquet), keep-FIRST per (date, id) so a past day's stamped call
    is never rewritten.
  • grade(horizons) — for every logged call old enough to have a realized outcome, join the
    forward return (sector = SPDR ETF close; basket = equal-weight level), and score the engine:
    directional hit-rate (overall + by conviction tier), cross-sectional rank-IC of the
    conviction score vs forward return, and forward return vs SPY. Returns a scorecard the
    dashboard renders honestly (sparse until it accrues).

Display/research-only — the log is NEVER read back into a live score. Additive / fail-soft.
"""
from __future__ import annotations

import logging

import numpy as np
import pandas as pd

from engine import grading  # W1c: shared next-bar-fill grader
from lib import config

log = logging.getLogger(__name__)

_HORIZONS_D = (21, 63, 126)        # ~1/3/6 months — the horizons that matter
_STORE = ("sector_central", "calls.parquet")


def _yahoo_panel():
    try:
        from engine.inputs import yahoo_closes
        return yahoo_closes()
    except Exception:  # noqa: BLE001
        return None


def _basket_levels() -> dict:
    """Equal-weight basket level series keyed by basket id — reads the FROZEN store only.

    W3.8: The live-recompute path (compute_baskets()) is REPLACED by the frozen
    basket-level parquet (data/basket_levels/us.parquet).  This kills the look-ahead /
    survivorship leak: grades are computed on PIT-frozen series, not on today's
    membership projected backward.

    Before the first freeze (data/basket_levels/us.parquet absent or empty) this
    returns an empty dict — the grader will report 'accruing from <freeze_start>'
    for all basket calls, which is the honest behaviour (see grade()).
    """
    out = {}
    try:
        from engine.basket_freeze import read_frozen
        df = read_frozen("us")
        if df is None or df.empty:
            log.info("basket_levels[us]: no frozen store yet — basket grading accruing")
            return out
        for col in df.columns:
            if col.endswith("__level_tr"):
                bid = col[: -len("__level_tr")]
                s = df[col].dropna()
                if not s.empty:
                    out[bid] = s
    except Exception as e:  # noqa: BLE001
        log.warning("basket_levels[us]: frozen read failed: %s", e)
    return out


def _level_for(row: dict, panel) -> float | None:
    """The as-of price level for a call (sector = SPDR close; basket left None — grade()
    recomputes forward returns from the dated series, so the stamp is informational)."""
    try:
        if row.get("kind") == "sector" and row.get("ticker") and panel is not None \
                and row["ticker"] in panel.columns:
            s = panel[row["ticker"]].dropna()
            return float(s.iloc[-1]) if not s.empty else None
    except Exception:  # noqa: BLE001
        pass
    return None


def append_central_log(data: dict) -> int:
    asof = (data or {}).get("as_of")
    if not asof:
        return 0
    panel = _yahoo_panel()
    rows = []
    for rec in (data.get("sectors", []) + data.get("baskets", [])):
        conv = rec.get("conviction") or {}
        fwd = rec.get("forward") or {}
        rid = rec.get("id") or ""
        bid = rid[2:] if rid.startswith("b-") else None
        rows.append({
            "date": asof, "id": rid, "kind": rec.get("kind"),
            "ticker": rec.get("ticker"), "basket_id": bid, "name": rec.get("name"),
            "score": conv.get("score"), "label": conv.get("label_en"), "dir": conv.get("dir"),
            "confluence": (conv.get("confluence") or {}).get("agree"),
            "trend_pass": fwd.get("trend_pass"), "ret_12m": fwd.get("ret_12m"),
            "gate_factor": (rec.get("components") or {}).get("gate_factor"),
            "level": _level_for(rec, panel),
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


def _mhash_stable(basket_id: str, d0: pd.Timestamp, h: int, frozen_df) -> bool:
    """Return True iff the membership hash is stable over the forward window [d0, d0+h].

    A grade is INVALIDATED (returns False) when the mhash changes within the forward
    window — this means the basket's composition changed mid-horizon and the return
    is not attributable to the same membership the call was made on.

    frozen_df may be None (no frozen store yet) — returns False so the grade is dropped.
    """
    if frozen_df is None or frozen_df.empty:
        return False
    col = f"{basket_id}__mhash"
    if col not in frozen_df.columns:
        return False
    # window: d0 through d0 + h trading-day equivalent (calendar)
    window = frozen_df.loc[
        (frozen_df.index >= d0) & (frozen_df.index <= d0 + pd.Timedelta(days=h * 2))
    ][col].dropna()
    if window.empty:
        return False   # no frozen data in window → can't grade
    return window.nunique() == 1   # stable iff exactly one unique hash


def _fwd_return(row: pd.Series, h: int, panel, basket_lvl: dict,
                frozen_df=None) -> tuple[float | None, str | None]:
    """Realized return from the call to call_date + h trading days, NEXT-BAR filled
    (W1c, audit #15): the call fires on d0's close but is entered on the next bar, so the
    same-bar ``iloc[0]`` denominator no longer flatters the read (sector = SPDR close;
    basket = EW level). None if the horizon hasn't elapsed / series missing.

    W3.8: basket calls additionally check membership-hash stability over the forward
    window.  Returns (return_float | None, invalidation_reason | None).  When a
    non-None invalidation_reason is returned the grade must be DROPPED (not scored).
    """
    try:
        d0 = pd.Timestamp(row["date"])
        if row.get("kind") == "sector" and pd.notna(row.get("ticker")):
            s = panel[row["ticker"]].dropna() if (panel is not None and row["ticker"] in panel.columns) else None
            fr = grading.grade_next_bar_return(s, str(d0.date()), h) if s is not None and not s.empty else None
            return fr, None
        else:
            bid = row.get("basket_id")
            s = basket_lvl.get(bid)
            if s is None or s.empty:
                return None, None
            # W3.8: membership-hash stability check before grading
            if not _mhash_stable(bid, d0, h, frozen_df):
                return None, "membership_changed"
            fr = grading.grade_next_bar_return(s, str(d0.date()), h)
            return fr, None
    except Exception:  # noqa: BLE001
        return None, None


def grade() -> dict | None:
    """Score every matured call. Returns a scorecard {n_calls, n_graded, dates, by_horizon}.

    W3.8 changes:
    - Basket forward returns read from the FROZEN store (data/basket_levels/us.parquet) only.
      The live compute_baskets() path is gone from _basket_levels().
    - Grades whose forward window spans a membership-hash change are INVALIDATED
      (dropped with reason 'membership_changed'; counted in invalidated_membership).
    - Pre-freeze basket calls are NOT graded: if the frozen store doesn't exist yet
      (or has no data for the basket's call date), the scorecard reports
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

    panel = _yahoo_panel()
    basket_lvl = _basket_levels()

    # Load frozen DataFrame for membership-hash checks (W3.8)
    frozen_df = None
    freeze_start = None
    try:
        from engine.basket_freeze import read_frozen, freeze_start_date
        frozen_df = read_frozen("us")
        freeze_start = freeze_start_date("us")
    except Exception:  # noqa: BLE001
        pass

    bench = None
    if panel is not None and "SPY" in panel.columns:
        bench = panel["SPY"].dropna()

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
            fr, inv_reason = _fwd_return(row, h, panel, basket_lvl, frozen_df=frozen_df)
            if inv_reason == "membership_changed":
                n_invalidated_membership += 1
                continue
            if fr is None:
                continue
            br = None
            if bench is not None:
                d0 = pd.Timestamp(row["date"])
                br = grading.grade_next_bar_return(bench, str(d0.date()), h)  # next-bar fill (W1c)
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
        up = g[g["dir"] == "up"]; dn = g[g["dir"] == "down"]
        hit = float(((up["fwd"] > 0).sum() + (dn["fwd"] < 0).sum()) / len(g)) if len(g) else None
        ics = []
        for d, sub in g.groupby("date"):
            if sub["score"].nunique() >= 3:
                ics.append(float(sub["score"].rank().corr(sub["fwd"].rank())))
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
