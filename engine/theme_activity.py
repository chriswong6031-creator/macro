"""Multi-source REAL-ACTIVITY observable — the v2 engine behind the Divergence Radar.

Fuses several INDEPENDENT non-price observables of "is real activity actually happening
on this theme" into one per-basket signal, laid against price (in engine/radar.py):

  * usaspending      — federal contract obligations  (collectors/usaspending.py)   [strong]
  * quiver_govcontract — Quiver new-award $          (collectors/quiver.py event tbl)[strong]
  * congress_netbuy  — congressional net-buy $         (Quiver event tbl, signed)   [medium]
  * lobbying_ramp    — lobbying spend ramp             (Quiver event tbl)           [medium]
  * news_velocity    — modeled macro-news flow         (engine/news_flow.py)        [weak/context]

TWO SOURCE KINDS, two metrics:
  * "wide"  (usaspending): a deep date-indexed [month x ticker] store series read YoY
    (recent 3 months vs the same 3 months a year ago) — kills federal seasonality.
  * "quiver": one of MAIN's append-only Quiver EVENT tables (collectors/quiver.py ->
    data/quiver/<dataset>.parquet, read via engine.altdata). These are forward-accumulating
    (no year of history yet), so the metric is recent-60d vs prior-60d, aggregated over the
    basket's members. Reuses altdata's _read/_usd/_side/_dt parsers — does NOT add a parallel
    collector.
Each source → a metric → a cross-sectional robust-z leg; legs are weight-fused into
`fused_obs_z` (the divergence/salience input) and `fused_accel` (the up/down direction).
Absent sources (no key, no table, thin coverage) are skipped and down-weighted to zero — the
radar degrades gracefully and sharpens as sources fill in. Raw ratios are winsorised
(ACCEL_CLAMP) against small-denominator blow-ups on thin windows.

CROWDING sources (off-exchange short ratio, WSB) are deliberately NOT fused here (the
asymmetry invariant: independent real-activity divergence UPGRADES ahead of price; crowding
only ever trims).

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
ACCEL_CLAMP = (0.05, 20.0)  # winsorise the raw ratio (small-denominator blow-ups on thin windows)
Z_CLAMP = 3.5            # winsorise robust-z (tight cross-section -> tiny MAD -> blow-ups)
NEWS_WEIGHT = 0.5        # the modeled-news leg carries a deliberately low fusion weight
QUIVER_RECENT_D = 60     # Quiver event tables are forward-accumulating -> recent vs prior window
QUIVER_PRIOR_D = 60      # (NOT YoY: those tables don't have a year of history yet)

# fusable spend/activity sources (crowding sources are handled separately, down-size only).
# Two kinds: "wide" = a date-indexed [month x ticker] store series read YoY (usaspending);
# "quiver" = one of main's append-only Quiver EVENT tables (collectors/quiver.py ->
# data/quiver/<dataset>.parquet), read via engine.altdata on a recent-vs-prior window and
# aggregated to the basket. label_* are the bilingual source-fusion-bar strings.
SOURCES: list[dict] = [
    {"name": "usaspending", "kind": "wide", "group": "usaspending", "series": "obligations",
     "weight": 1.0, "signed": False, "min_base": 10e6, "label_en": "Federal contracts", "label_zh": "联邦合同"},
    {"name": "quiver_govcontract", "kind": "quiver", "dataset": "govcontracts",
     "date": ["Date", "action_date"], "value": ["Amount"], "signed": False, "min_prior": 5e5,
     "weight": 1.0, "label_en": "Gov contracts (Quiver)", "label_zh": "政府合同"},
    {"name": "congress_netbuy", "kind": "quiver", "dataset": "congress",
     "date": ["TransactionDate", "ReportDate", "Date"], "value": ["Range", "Amount"], "signed": True,
     "txn_col": "Transaction", "min_prior": 0.0, "weight": 0.6, "label_en": "Congress net-buy", "label_zh": "国会净买入"},
    {"name": "lobbying_ramp", "kind": "quiver", "dataset": "lobbying",
     "date": ["Date"], "value": ["Amount"], "signed": False, "min_prior": 5e4,
     "weight": 0.7, "label_en": "Lobbying ramp", "label_zh": "游说支出"},
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
        accel = float(np.clip(recent / prior, *ACCEL_CLAMP))
        metric = float(np.log(accel))
    return {"accel": None if accel is None else round(accel, 3),
            "recent_3m_usd": round(recent, 0), "base_3m_usd": round(prior, 0),
            "metric": float(metric), "n_covered": len(cols), "covered": cols}


def _live_members(b: dict) -> list[str]:
    return [m.get("symbol") for m in b.get("members", []) if m.get("symbol")]


def _ok(df) -> pd.DataFrame | None:
    return df if df is not None and not df.empty else None


def _load_source(src: dict, sources_data: dict | None) -> pd.DataFrame | None:
    """Load a 'wide' source: a date-indexed [month x ticker] store series (usaspending).
    When sources_data is injected (test mode) it is authoritative — never fall through to disk."""
    if sources_data is not None:
        return _ok(sources_data.get(src["name"]))
    try:
        return _ok(store.read(src["group"], src["series"]))
    except Exception:  # noqa: BLE001
        return None


def _load_quiver(src: dict, sources_data: dict | None) -> pd.DataFrame | None:
    """Load a Quiver EVENT table (main's collectors/quiver.py). Injectable by dataset name;
    injection is authoritative (hermetic) — never read the real disk tables under injection."""
    if sources_data is not None:
        return _ok(sources_data.get(src["dataset"]))
    try:
        from engine import altdata
        return _ok(altdata._read(src["dataset"]))
    except Exception:  # noqa: BLE001
        return None


def _quiver_basket_metric(src: dict, members: list[str], *, today=None,
                          event_df: pd.DataFrame | None = None) -> dict | None:
    """Per-basket recent-vs-prior activity from one Quiver event table. Filters the event
    stream to the basket's members, then compares the last QUIVER_RECENT_D days to the prior
    window. Unsigned (gov-contract / lobbying $): accel = recent/prior. Signed (congress
    net-buy: purchase +, sale −): metric = (recent − prior)/scale. Reuses engine.altdata
    parsers (_s / _usd / _side / _dt)."""
    df = event_df
    if df is None or df.empty or "Ticker" not in df.columns:
        return None
    from engine import altdata
    tk = df["Ticker"].map(altdata._s)
    mask = tk.isin(set(members))
    if not mask.any():
        return None
    sub = df[mask]
    covered = sorted({t for t in tk[mask].dropna()})
    if len(covered) < MIN_COVERED:
        return None
    dcol = next((c for c in src["date"] if c in sub.columns), None)
    vcol = next((c for c in src["value"] if c in sub.columns), None)
    if not dcol or not vcol:
        return None
    dt = altdata._dt(sub[dcol])
    t0 = pd.Timestamp(today) if today is not None else dt.max()
    if pd.isna(t0):
        return None
    rec = (dt > t0 - pd.Timedelta(days=QUIVER_RECENT_D)) & (dt <= t0)
    pri = (dt > t0 - pd.Timedelta(days=QUIVER_RECENT_D + QUIVER_PRIOR_D)) & (dt <= t0 - pd.Timedelta(days=QUIVER_RECENT_D))
    val = sub[vcol].map(altdata._usd)
    if src["signed"]:
        tcol = src.get("txn_col", "Transaction")
        if tcol in sub.columns:
            sgn = sub[tcol].map(lambda t: -1.0 if altdata._side(t) == "sell" else (1.0 if altdata._side(t) == "buy" else 0.0))
            val = val * sgn
    recent = float(np.nansum(val[rec].to_numpy(dtype=float)))
    prior = float(np.nansum(val[pri].to_numpy(dtype=float)))
    if src["signed"]:
        scale = max(abs(prior), abs(recent), 1.0)
        metric, accel = (recent - prior) / scale, None
    else:
        if prior < src.get("min_prior", 5e5) or prior <= 0:
            return None
        accel = float(np.clip(recent / prior, *ACCEL_CLAMP))
        metric = float(np.log(accel))
    return {"accel": None if accel is None else round(accel, 3),
            "recent_3m_usd": round(recent, 0), "base_3m_usd": round(prior, 0),
            "metric": float(metric), "n_covered": len(covered), "covered": covered}


def compute_real_activity(baskets_payload: dict, *, sources_data: dict | None = None,
                          root=None, news: bool = True, today=None) -> dict:
    """Per-basket fused real-activity observable. Returns {basket_id: {...}} for every
    basket with >=1 usable source. Two-pass: per-source raw metrics, then cross-sectional
    robust-z + weight fusion. Pure-ish: inject sources_data for hermetic tests."""
    baskets = (baskets_payload or {}).get("baskets") or []
    if not baskets:
        return {}

    # pass 1 — per-basket, per-source raw metrics. Preload each source once: 'wide' sources
    # are date-indexed store frames (YoY); 'quiver' sources are main's event tables (recent window).
    loaded = {src["name"]: (_load_source(src, sources_data) if src["kind"] == "wide"
                            else _load_quiver(src, sources_data)) for src in SOURCES}
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
            data = loaded.get(src["name"])
            if data is None:
                continue
            if src["kind"] == "wide":
                acc = source_accel(data, members, signed=src["signed"], min_base=src["min_base"])
            else:
                acc = _quiver_basket_metric(src, members, today=today, event_df=data)
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
