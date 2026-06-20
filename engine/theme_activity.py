"""Multi-source REAL-ACTIVITY observable — the v2 engine behind the Divergence Radar.

Fuses several INDEPENDENT non-price observables of "is real activity actually happening
on this theme" into one per-basket signal, laid against price (in engine/radar.py):

  * usaspending      — federal contract obligations  (collectors/usaspending.py)   [strong]
  * quiver_govcontract — Quiver new-award $          (collectors/quiver.py)         [strong]
  * congress_netbuy  — congressional net-buy $         (Quiver, signed)             [medium]
  * lobbying_ramp    — lobbying spend ramp             (Quiver)                      [medium]
  * news_velocity    — modeled macro-news flow         (engine/news_flow.py)        [weak/context]

Each source → a self-referential YoY acceleration + a cross-sectional robust-z leg; the
legs are weight-fused into `fused_obs_z` (the divergence/salience input) and `fused_accel`
(the up/down direction). Sources that are absent (no key, no parquet, thin coverage) are
simply skipped and down-weighted to zero — so the radar degrades gracefully and improves
monotonically as data sources are added.

CROWDING sources (off-exchange short ratio, WSB) are deliberately NOT fused here — they
feed a separate down-size-only `crowd_context` (the asymmetry invariant: independent
real-activity divergence UPGRADES ahead of price; crowding only ever trims).

This module owns the shared primitives (robust_z + source_accel + the YoY constants);
engine/radar.py imports them. It does NOT import radar (no cycle). Display/context only.
"""
from __future__ import annotations

import logging

import numpy as np
import pandas as pd

from lib import config, store

log = logging.getLogger(__name__)

# --- shared primitives (radar.py re-exports these) ---------------------------
LAG_MONTHS = 3            # most-recent award months are incomplete -> drop them
RECENT_MONTHS = 3        # "recent" window
YOY_LAG = 12             # compare recent window to the SAME months a year ago (kills seasonality)
MIN_COVERED = 2          # a basket needs >=2 covered members in a source to use that source
MIN_BASE_USD = 10e6      # ignore trivially small footprints (year-ago 3-month spend)
ACCEL_UP = 1.25          # recent / year-ago >= this -> accelerating
ACCEL_DOWN = 0.80        # <= this -> cooling
Z_CLAMP = 3.5            # winsorise robust-z (tight cross-section -> tiny MAD -> blow-ups)
NEWS_WEIGHT = 0.5        # the modeled-news leg carries a deliberately low fusion weight

# fusable spend/activity sources (crowding sources are handled separately, down-size only).
# label_* are bilingual display strings for the source-fusion bar.
SOURCES: list[dict] = [
    {"name": "usaspending", "group": "usaspending", "series": "obligations",
     "weight": 1.0, "signed": False, "min_base": 10e6, "label_en": "Federal contracts", "label_zh": "联邦合同"},
    {"name": "quiver_govcontract", "group": "quiver", "series": "govcontracts",
     "weight": 1.0, "signed": False, "min_base": 1e6, "label_en": "Gov contracts (Quiver)", "label_zh": "政府合同"},
    {"name": "congress_netbuy", "group": "quiver", "series": "congress",
     "weight": 0.6, "signed": True, "min_base": 0.0, "label_en": "Congress net-buy", "label_zh": "国会净买入"},
    {"name": "lobbying_ramp", "group": "quiver", "series": "lobbying",
     "weight": 0.7, "signed": False, "min_base": 1e5, "label_en": "Lobbying ramp", "label_zh": "游说支出"},
]


def robust_z(values: list[float]) -> list[float]:
    """Median/MAD z (robust to the small, lumpy cross-section), winsorised to +/-Z_CLAMP."""
    arr = np.asarray([v if v is not None and np.isfinite(v) else np.nan for v in values], float)
    good = arr[~np.isnan(arr)]
    if len(good) < 2:
        return [0.0] * len(values)
    med = float(np.median(good))
    mad = float(np.median(np.abs(good - med))) * 1.4826
    scale = mad if mad > 1e-9 else float(np.std(good))
    if not scale or scale < 1e-9:
        return [0.0] * len(values)
    return [0.0 if np.isnan(v) else float(np.clip((v - med) / scale, -Z_CLAMP, Z_CLAMP)) for v in arr]


def source_accel(wide: pd.DataFrame, covered: list[str], *, signed: bool = False,
                 min_base: float = MIN_BASE_USD) -> dict | None:
    """Self-referential YoY change for one source over a basket's covered members.
    Unsigned (spend): accel = recent3m / same-3m-a-year-ago, metric = log(accel).
    Signed (net flows that can be negative): metric = (recent - prior) / scale, accel = None."""
    cols = [c for c in covered if c in wide.columns]
    if len(cols) < MIN_COVERED:
        return None
    monthly = wide[cols].sum(axis=1, min_count=1).dropna().sort_index()
    if LAG_MONTHS:
        monthly = monthly.iloc[:-LAG_MONTHS] if len(monthly) > LAG_MONTHS else monthly.iloc[:0]
    if len(monthly) < RECENT_MONTHS + YOY_LAG:
        return None
    recent = float(monthly.iloc[-RECENT_MONTHS:].sum())
    prior = float(monthly.iloc[-(RECENT_MONTHS + YOY_LAG):-YOY_LAG].sum())
    if signed:
        scale = max(abs(prior), abs(recent), min_base, 1.0)
        metric = (recent - prior) / scale
        accel = None
    else:
        if prior < min_base or prior <= 0:
            return None
        accel = recent / prior
        metric = float(np.log(max(accel, 1e-6)))
    return {"accel": None if accel is None else round(accel, 3),
            "recent_3m_usd": round(recent, 0), "base_3m_usd": round(prior, 0),
            "metric": float(metric), "n_covered": len(cols), "covered": cols}


def _live_members(b: dict) -> list[str]:
    return [m.get("symbol") for m in b.get("members", []) if m.get("symbol")]


def _load_source(src: dict, sources_data: dict | None) -> pd.DataFrame | None:
    if sources_data is not None and src["name"] in sources_data:
        df = sources_data[src["name"]]
        return df if df is not None and not df.empty else None
    try:
        df = store.read(src["group"], src["series"])
        return df if df is not None and not df.empty else None
    except Exception:  # noqa: BLE001
        return None


def compute_real_activity(baskets_payload: dict, *, sources_data: dict | None = None,
                          root=None, news: bool = True, today=None) -> dict:
    """Per-basket fused real-activity observable. Returns {basket_id: {...}} for every
    basket with >=1 usable source. Two-pass: per-source raw metrics, then cross-sectional
    robust-z + weight fusion. Pure-ish: inject sources_data for hermetic tests."""
    baskets = (baskets_payload or {}).get("baskets") or []
    if not baskets:
        return {}

    # pass 1 — per-basket, per-source raw metrics
    frames = {src["name"]: _load_source(src, sources_data) for src in SOURCES}
    events = None
    if news:
        try:
            from engine import news_flow
            events = news_flow.load_events(root=root)
        except Exception as e:  # noqa: BLE001
            log.debug("news events load failed: %s", e)
    raw: dict[str, dict] = {}
    for b in baskets:
        bid = b.get("id")
        members = _live_members(b)
        per_src = {}
        for src in SOURCES:
            wide = frames.get(src["name"])
            if wide is None:
                continue
            acc = source_accel(wide, members, signed=src["signed"], min_base=src["min_base"])
            if acc is not None:
                per_src[src["name"]] = acc
        news_leg = None
        if news and events is not None:
            try:
                from engine import news_flow
                news_leg = news_flow.theme_flow(bid, events, today=today)
            except Exception as e:  # noqa: BLE001
                log.debug("news leg failed for %s: %s", bid, e)
        # require >=1 HARD source (spend / alt-data); the coarse news leg only ENRICHES a
        # basket that already has hard activity data — it never qualifies one on its own.
        if per_src:
            raw[bid] = {"sources": per_src, "news": news_leg}

    if not raw:
        return {}

    # pass 2 — cross-sectional robust-z per source, then weight-fuse
    bids = list(raw)
    z_by_src: dict[str, dict[str, float]] = {}
    for src in SOURCES:
        metrics = [raw[bid]["sources"].get(src["name"], {}).get("metric") for bid in bids]
        zs = robust_z([m if m is not None else np.nan for m in metrics])
        z_by_src[src["name"]] = {bid: z for bid, z in zip(bids, zs)}
    news_metrics = [(raw[bid]["news"] or {}).get("metric") for bid in bids]
    news_z = {bid: z for bid, z in zip(bids, robust_z([m if m is not None else np.nan for m in news_metrics]))}

    weight = {src["name"]: src["weight"] for src in SOURCES}
    out: dict[str, dict] = {}
    for bid in bids:
        present = raw[bid]["sources"]
        leg_list, num, den = [], 0.0, 0.0
        ln_accel_num, ln_accel_den = 0.0, 0.0
        for src in SOURCES:
            nm = src["name"]
            if nm not in present:
                continue
            z = z_by_src[nm][bid]
            w = weight[nm]
            num += w * z
            den += w
            leg = {"name": nm, "label_en": src["label_en"], "label_zh": src["label_zh"],
                   "accel": present[nm]["accel"], "z": round(z, 3), "weight": w,
                   "n_covered": present[nm]["n_covered"], "covered": present[nm]["covered"]}
            leg_list.append(leg)
            if present[nm]["accel"] is not None and present[nm]["accel"] > 0:
                ln_accel_num += w * np.log(present[nm]["accel"])
                ln_accel_den += w
        news_leg = raw[bid]["news"]
        if news_leg is not None:
            z = news_z[bid]
            num += NEWS_WEIGHT * z
            den += NEWS_WEIGHT
            leg_list.append({"name": "news_velocity", "label_en": "News flow", "label_zh": "新闻流",
                             "velocity": news_leg["velocity"], "acceleration": news_leg["acceleration"],
                             "z": round(z, 3), "weight": NEWS_WEIGHT,
                             "unscheduled_share": news_leg["unscheduled_share"], "tier1_share": news_leg["tier1_share"]})
        if den <= 0:
            continue
        fused_obs_z = num / den
        fused_accel = float(np.exp(ln_accel_num / ln_accel_den)) if ln_accel_den > 0 else None
        if fused_accel is not None:
            obs_dir = 1 if fused_accel >= ACCEL_UP else (-1 if fused_accel <= ACCEL_DOWN else 0)
        else:
            obs_dir = 1 if fused_obs_z >= 0.75 else (-1 if fused_obs_z <= -0.75 else 0)
        primary = present.get("usaspending") or next(iter(present.values()), None)
        out[bid] = {
            "fused_obs_z": round(fused_obs_z, 3),
            "fused_accel": None if fused_accel is None else round(fused_accel, 3),
            "obs_dir": obs_dir,
            "n_sources": len(present) + (1 if news_leg is not None else 0),
            "sources": leg_list,
            "primary": None if primary is None else {
                "accel": primary["accel"], "recent_3m_usd": primary["recent_3m_usd"],
                "base_3m_usd": primary["base_3m_usd"], "n_covered": primary["n_covered"],
                "covered": primary["covered"]},
            "news": news_leg,
        }
    return out
