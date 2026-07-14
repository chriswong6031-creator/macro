"""Oracle P6 — Time Machine feed helpers.

Pure functions consumed by scripts/build_oracle_timemachine.py.
No side effects; no network; numpy + pandas only.

Granularity:
  Tier S — quarterly chunks, DAILY data (11 nodes × ~63 dates ≈ 9 KB/chunk).
  Tier M — monthly chunks, DAILY data (354 nodes × ~21 dates ≈ 145 KB/chunk).
  Chunks are lazy-loaded per year by the UI, so per-chunk size is what matters;
  total feed size scales to ~20 MB uncompressed across all years.
  Months where EITHER axis is 100 % null (warm-up) are skipped for Tier M
  (the RRG visualization needs both axes).

Chunk format (per tier per period):
  {
    "dates": ["YYYY-MM-DD", ...],          # sorted ascending
    "data": {                              # keyed by node_id (int str)
        "0": [[rs_ratio, rs_mom], ...],    # parallel to dates; null where missing (v3 desk-parity coords)
        ...
    }
  }

Manifest format:
  {
    "schema_version": 3,
    "built_at": "ISO UTC",
    "tiers": {
      "s": {"label": "Sectors", "granularity": "daily", "period_type": "Q",
             "date_from": "1998-12-22", "date_to": "...",
             "chunks": [{"key": "1999Q1", "file": "tm_s_1999Q1.json", ...}]},
      "m": {"label": "Subsectors + Themes", "granularity": "daily",
             "period_type": "M", "date_from": "2022-02-04", "date_to": "...",
             "chunks": [{"key": "2022M02", "file": "tm_m_2022M02.json", ...}]}
    },
    "registry": {
      "s": [{"id": 0, "name": "XLB", "name_zh": null, "theme": "Sectors", "tier": "s"}, ...],
      "m": [{"id": 0, "name": "...", "name_zh": "...", "theme": "...", "tier": "theme|subsector|basket"}, ...]
    }
  }
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

log = logging.getLogger(__name__)

# ── constants ────────────────────────────────────────────────────────────────

_SECTOR_ETF_ZH: dict[str, str] = {
    "XLB": "材料",
    "XLC": "通信",
    "XLE": "能源",
    "XLF": "金融",
    "XLI": "工业",
    "XLK": "科技",
    "XLP": "必需消费",
    "XLRE": "房地产",
    "XLU": "公用事业",
    "XLV": "医疗保健",
    "XLY": "可选消费",
}


# ── registry builders ────────────────────────────────────────────────────────

_FACTOR_ETF_ZH: dict[str, str] = {
    "IWF": "成长", "IWD": "价值", "MTUM": "动量",
    "QUAL": "质量", "USMV": "低波动", "IWM": "小盘",
}


def build_registry_s(panel_s: pd.DataFrame) -> list[dict]:
    """Build the Tier-S node registry: 11 sector ETFs."""
    nodes = sorted(panel_s.index.get_level_values("node").unique().tolist())
    registry = []
    for idx, name in enumerate(nodes):
        registry.append(
            {
                "id": idx,
                "name": name,
                "name_zh": _SECTOR_ETF_ZH.get(name),
                "theme": "Sectors",
                "tier": "s",
            }
        )
    return registry


def build_registry_f(panel_f: pd.DataFrame) -> list[dict]:
    """Build the Tier-F node registry: 6 style-factor ETFs (SPY-excess, context-only)."""
    nodes = sorted(panel_f.index.get_level_values("node").unique().tolist())
    return [
        {"id": i, "name": n, "name_zh": _FACTOR_ETF_ZH.get(n),
         "theme": "Factors", "tier": "f"}
        for i, n in enumerate(nodes)
    ]


def build_registry_m(
    panel_m: pd.DataFrame,
    themes_tree: list[dict],
    names_zh: dict[str, dict[str, str]],
    baskets_data: list[dict],
) -> list[dict]:
    """Build the Tier-M node registry: subsectors + themes + baskets.

    ``names_zh`` is the content of data/themes_heatmap/names_zh.json — a dict
    with keys "themes" and "subsectors", each mapping English name -> zh name.
    ``baskets_data`` is the ``baskets`` list from site/basketdata/baskets.json.
    """
    # Build lookup: node name -> info from the themes tree
    tree_info: dict[str, dict] = {}
    for t in themes_tree:
        theme_name = t["theme"]
        tree_info[theme_name] = {"tier": "theme", "theme": theme_name}
        for sub in t.get("subsectors", []):
            sub_name = sub.get("name", sub.get("key", ""))
            sub_key = sub.get("key", "")
            info = {"tier": "subsector", "theme": theme_name}
            if sub_name:
                tree_info[sub_name] = info
            # Also index by key (snake_case identifiers)
            if sub_key and sub_key != sub_name:
                tree_info[sub_key] = dict(info)

    # Basket name -> info
    basket_info: dict[str, dict] = {}
    for b in baskets_data:
        name = b.get("name", "")
        name_zh = b.get("name_zh", "")
        category = b.get("category", "basket")
        if name:
            basket_info[name] = {
                "tier": "basket",
                "theme": category or "basket",
                "name_zh": name_zh or None,
            }

    # Zh lookups from names_zh.json
    themes_zh: dict[str, str] = names_zh.get("themes", {})
    subsectors_zh: dict[str, str] = names_zh.get("subsectors", {})

    nodes = sorted(panel_m.index.get_level_values("node").unique().tolist())
    registry = []
    for idx, name in enumerate(nodes):
        info = tree_info.get(name) or basket_info.get(name) or {}
        tier = info.get("tier", "subsector")
        theme = info.get("theme", "")

        # Resolve zh name: names_zh has theme and subsector maps
        if info.get("name_zh"):
            name_zh: str | None = info["name_zh"]
        elif tier == "theme":
            name_zh = themes_zh.get(name)
        else:
            # Try subsector key, then full name
            name_zh = subsectors_zh.get(name)

        registry.append(
            {
                "id": idx,
                "name": name,
                "name_zh": name_zh,
                "theme": theme,
                "tier": tier,
            }
        )
    return registry


# ── chunk builders ────────────────────────────────────────────────────────────

def _quantize(v: float) -> float | None:
    """Round to 2dp; return None for NaN/inf."""
    if v is None:
        return None
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    import math

    if math.isnan(f) or math.isinf(f):
        return None
    return round(f, 2)


# ── RRG coordinate transform (desk parity, schema v3) ────────────────────────
#
# The tape originally plotted the oracle panel's raw features — ``rs`` (a
# ONE-DAY relative return, panel.py: ``ret - bench_ret``) and ``accel_z`` —
# which were built for episode detection, not as chart coordinates: the
# x-axis was daily noise and the dots jumped frame to frame. rrg_transform
# re-derives both axes with the SAME math the live rotation desk uses
# (engine/subsector_rotation.py::compute_rotation), evaluated at every date:
#
#   perf_h   = h-day return of the node level          h ∈ {1W,1M,3M,6M}
#   rel_h    = perf_h − cross-sectional MEDIAN(perf_h)          (per date)
#   z_h      = cross-sectional z-score of rel_h                 (per date)
#   x  rs_ratio = mean(z_1M, z_3M)
#   y  rs_mom   = mean(z_1W, z_1M) − mean(z_3M, z_6M)
#
# Desk-parity details copied exactly: population std with an sd≤1e-9 → 0.0
# guard; the momentum back-leg falls back to 0.0 while 3M/6M are warming up
# (compute_rotation's ``or 0.0``). Divergence (deliberate, tape-only): a node
# with no 1M history yet emits NaN → null → not plotted, instead of the
# desk's snapshot-only 0.0 — a warm-up node must not sit fake-centred.

_RRG_HORIZONS: dict[str, int] = {"1W": 5, "1M": 21, "3M": 63, "6M": 126}


def _to_long(wide: pd.DataFrame) -> pd.Series:
    """(date × node) frame → Series indexed by (node, date), no stack() dance."""
    idx = pd.MultiIndex.from_product(
        [wide.index, wide.columns], names=["date", "node"])
    return pd.Series(wide.to_numpy().ravel(), index=idx).reorder_levels(["node", "date"])


def _nanmean2(a: pd.DataFrame, b: pd.DataFrame) -> pd.DataFrame:
    """Element-wise nanmean of two aligned frames (NaN only where BOTH are NaN)."""
    av, bv = a.to_numpy(), b.to_numpy()
    an, bn = np.isnan(av), np.isnan(bv)
    s = np.where(an, 0.0, av) + np.where(bn, 0.0, bv)
    c = (~an).astype(int) + (~bn).astype(int)
    out = np.divide(s, c, out=np.full_like(s, np.nan), where=c > 0)
    return pd.DataFrame(out, index=a.index, columns=a.columns)


def rrg_transform(panel: pd.DataFrame) -> pd.DataFrame:
    """Overwrite ``rs``/``accel_z`` with desk-parity RRG coords (see block comment).

    Input: (node, date)-indexed panel with a daily ``ret`` column. Returns a
    COPY where ``rs`` ← rs_ratio and ``accel_z`` ← rs_mom, so the chunk
    builders (which read those column names) need no changes. Interior
    missing rets compound as 0% (rare; display-tape tolerance); dates before
    a node's first valid ret stay NaN and never plot.
    """
    ret_w = panel["ret"].unstack("node").sort_index()
    alive = ret_w.notna().cummax()
    lvl = (1.0 + ret_w.fillna(0.0)).cumprod().where(alive)

    z: dict[str, pd.DataFrame] = {}
    for name, h in _RRG_HORIZONS.items():
        perf = lvl / lvl.shift(h) - 1.0
        # require the node to have been alive a full window ago
        perf = perf.where(alive.shift(h, fill_value=False))
        rel = perf.sub(perf.median(axis=1), axis=0)
        sd = rel.std(axis=1, ddof=0)
        zz = rel.sub(rel.mean(axis=1), axis=0).div(sd.where(sd > 1e-9), axis=0)
        degen = ~(sd > 1e-9)
        if degen.any():  # desk guard: degenerate cross-section → 0.0 (NaNs stay NaN)
            zz.loc[degen] = rel.loc[degen].where(rel.loc[degen].isna(), 0.0)
        z[name] = zz

    rs_ratio = _nanmean2(z["1M"], z["3M"])
    back = _nanmean2(z["3M"], z["6M"]).fillna(0.0)   # desk `or 0.0` warm-up fallback
    rs_mom = _nanmean2(z["1W"], z["1M"]) - back

    out = panel.copy()
    out["rs"] = _to_long(rs_ratio).reindex(out.index)
    out["accel_z"] = _to_long(rs_mom).reindex(out.index)
    return out


def build_chunks_s(
    panel_s: pd.DataFrame,
    registry: list[dict],
    period_key: str = "Q",
) -> list[dict[str, Any]]:
    """Build Tier-S chunks, one per quarter.

    Returns list of {"period": "YYYY-Qn", "dates": [...], "data": {id: [[rs, accel_z],...]}}
    sorted by period ascending.
    """
    nodes = [r["name"] for r in registry]
    id_by_name = {r["name"]: str(r["id"]) for r in registry}

    dates_idx = panel_s.index.get_level_values("date")
    periods = dates_idx.to_period(period_key).unique().sort_values()

    chunks = []
    for period in periods:
        mask = dates_idx.to_period(period_key) == period
        sub = panel_s[mask]
        unique_dates = sub.index.get_level_values("date").unique().sort_values()

        data: dict[str, list] = {}
        for date in unique_dates:
            try:
                day_df = sub.xs(date, level="date")
            except KeyError:
                continue
            for n in nodes:
                nid = id_by_name[n]
                if nid not in data:
                    data[nid] = []
                if n in day_df.index:
                    rs = _quantize(day_df.loc[n, "rs"])
                    az = _quantize(day_df.loc[n, "accel_z"])
                    data[nid].append([rs, az])
                else:
                    data[nid].append(None)

        chunks.append(
            {
                "period": str(period),
                "dates": [str(d.date()) for d in unique_dates],
                "data": data,
            }
        )

    return chunks


def build_chunks_m(
    panel_m: pd.DataFrame,
    registry: list[dict],
    period_key: str = "M",
) -> list[dict[str, Any]]:
    """Build Tier-M chunks, one per calendar month, DAILY granularity.

    All trading days present in the panel are emitted — no day-of-week filter.
    Months where ``accel_z`` is 100% null are skipped — the RRG scatter requires
    both axes.  Period format: "YYYYMmm" e.g. "2022M02".
    """
    nodes = [r["name"] for r in registry]
    id_by_name = {r["name"]: str(r["id"]) for r in registry}

    dates_idx = panel_m.index.get_level_values("date")

    periods = dates_idx.to_period("M").unique().sort_values()

    chunks = []
    for period in periods:
        mask = dates_idx.to_period("M") == period
        sub = panel_m[mask]

        # Skip months where accel_z is 100% null (early Tier-M warm-up period)
        if sub["accel_z"].isna().all() or sub["rs"].isna().all():
            log.debug("Skipping %s: accel_z 100%% null", period)
            continue

        unique_dates = sub.index.get_level_values("date").unique().sort_values()

        data: dict[str, list] = {}
        valid_dates = []
        for date in unique_dates:
            try:
                day_df = sub.xs(date, level="date")
            except KeyError:
                continue
            valid_dates.append(str(date.date()))
            for n in nodes:
                nid = id_by_name[n]
                if nid not in data:
                    data[nid] = []
                if n in day_df.index:
                    rs = _quantize(day_df.loc[n, "rs"])
                    az = _quantize(day_df.loc[n, "accel_z"])
                    data[nid].append([rs, az])
                else:
                    data[nid].append(None)

        if not valid_dates:
            continue

        chunks.append(
            {
                "period": f"{period.year}M{period.month:02d}",
                "dates": valid_dates,
                "data": data,
            }
        )

    return chunks


# ── episode feed ─────────────────────────────────────────────────────────────

def build_chunks_f(
    panel_f: pd.DataFrame,
    registry: list[dict],
    period_key: str = "Q",
) -> list[dict[str, Any]]:
    """Build Tier-F chunks, one per quarter (mirrors build_chunks_s)."""
    nodes = [r["name"] for r in registry]
    id_by_name = {r["name"]: str(r["id"]) for r in registry}
    dates_idx = panel_f.index.get_level_values("date")
    periods = dates_idx.to_period(period_key).unique().sort_values()
    chunks = []
    for period in periods:
        mask = dates_idx.to_period(period_key) == period
        sub = panel_f[mask]
        unique_dates = sub.index.get_level_values("date").unique().sort_values()
        data: dict[str, list] = {}
        for date in unique_dates:
            try:
                day_df = sub.xs(date, level="date")
            except KeyError:
                continue
            for n in nodes:
                nid = id_by_name[n]
                if nid not in data:
                    data[nid] = []
                if n in day_df.index:
                    rs = _quantize(day_df.loc[n, "rs"])
                    az = _quantize(day_df.loc[n, "accel_z"])
                    data[nid].append([rs, az])
                else:
                    data[nid].append(None)
        chunks.append({
            "period": str(period),
            "dates": [str(d.date()) for d in unique_dates],
            "data": data,
        })
    return chunks


def _date_str(v: Any) -> str | None:
    """Convert a pandas Timestamp / NaT / str to ISO date string or None."""
    if v is None:
        return None
    if isinstance(v, str):
        return v[:10] if v else None
    try:
        if pd.isna(v):
            return None
    except (TypeError, ValueError):
        pass
    try:
        return str(pd.Timestamp(v).date())
    except Exception:
        return None


def build_episode_feed(
    ep_m: pd.DataFrame,
    ep_s: pd.DataFrame,
    ep_f: pd.DataFrame | None = None,
) -> dict:
    """Build the episode overlay feed (tm_episodes.json).

    The ``presets`` list is derived purely from the episode catalog — date
    ranges are the earliest onset among included nodes and the latest
    exhausted_date (or confirmed_date as fallback) — no invented dates.
    """
    records = []

    def _row_to_dict(row: pd.Series) -> dict:
        return {
            "episode_id": str(row["episode_id"]) if not _is_null(row["episode_id"]) else None,
            "node": str(row["node"]) if not _is_null(row["node"]) else None,
            "direction": str(row["direction"]) if not _is_null(row["direction"]) else None,
            "onset_date": _date_str(row["onset_date"]),
            "confirmed_date": _date_str(row["confirmed_date"]),
            "undeniable_date": _date_str(row.get("undeniable_date")),
            "exhausted_date": _date_str(row.get("exhausted_date")),
            "two_sided": bool(row["two_sided"]) if not _is_null(row.get("two_sided")) else False,
            "paired_episode_id": str(row["paired_episode_id"]) if not _is_null(row.get("paired_episode_id")) else None,
            "peak_accel_z": _quantize(row.get("peak_accel_z")),
            "survivorship_flagged": bool(row.get("survivorship_flagged", False)),
            "tier": "m",
        }

    for _, row in ep_m.iterrows():
        records.append(_row_to_dict(row))

    def _row_to_dict_s(row: pd.Series) -> dict:
        d = _row_to_dict(row)
        d["tier"] = "s"
        return d

    for _, row in ep_s.iterrows():
        records.append(_row_to_dict_s(row))

    def _row_to_dict_f(row: pd.Series) -> dict:
        d = _row_to_dict(row)
        d["tier"] = "f"
        d["context_unverified"] = True
        return d

    if ep_f is not None:
        for _, row in ep_f.iterrows():
            records.append(_row_to_dict_f(row))

    # Build presets from the catalog itself
    presets = _build_presets(ep_m, ep_s, ep_f)

    return {"episodes": records, "presets": presets}


def _is_null(v: Any) -> bool:
    if v is None:
        return True
    try:
        return bool(pd.isna(v))
    except (TypeError, ValueError):
        return False


def _build_presets(ep_m: pd.DataFrame, ep_s: pd.DataFrame, ep_f: pd.DataFrame | None = None) -> list[dict]:
    """Derive presets from the episode catalog (no invented dates).

    Four presets:
    1. 2021-11 growth top (Tier S): XLK/XLC/XLY rolling over
    2. 2022 energy leadership (Tier S): XLE multi-episode in
    3. 2023-01 AI ignition (Tier M): aimodels/aiagi/aiapplications onset
    4. 2025-26 semis->healthcare (Tier M): semis* in + healthcare* in
    """
    presets = []

    # --- Preset 1: 2021-11 growth top (Tier S) ---
    growth_top_nodes = {"XLK", "XLC", "XLY"}
    growth_top_ep = ep_s[
        (ep_s["node"].isin(growth_top_nodes))
        & (ep_s["direction"] == "out")
        & (ep_s["onset_date"] >= pd.Timestamp("2021-10-01"))
        & (ep_s["onset_date"] <= pd.Timestamp("2022-03-31"))
    ]
    if not growth_top_ep.empty:
        onset = str(growth_top_ep["onset_date"].min().date())
        ends = growth_top_ep["exhausted_date"].dropna()
        end = str(ends.max().date()) if not ends.empty else str(growth_top_ep["confirmed_date"].max().date())
        presets.append(
            {
                "id": "2021_growth_top",
                "label_en": "2021 Growth Top",
                "label_zh": "2021年成长股见顶",
                "tier": "s",
                "date_from": onset,
                "date_to": end,
                "node_ids": sorted(growth_top_ep["node"].unique().tolist()),
            }
        )

    # --- Preset 2: 2022 energy leadership (Tier S) ---
    energy_ep = ep_s[
        (ep_s["node"] == "XLE")
        & (ep_s["direction"] == "in")
        & (ep_s["onset_date"] >= pd.Timestamp("2021-09-01"))
        & (ep_s["onset_date"] <= pd.Timestamp("2022-12-31"))
    ]
    if not energy_ep.empty:
        onset = str(energy_ep["onset_date"].min().date())
        ends = energy_ep["exhausted_date"].dropna()
        end = str(ends.max().date()) if not ends.empty else str(energy_ep["confirmed_date"].max().date())
        presets.append(
            {
                "id": "2022_energy_leadership",
                "label_en": "2022 Energy Leadership",
                "label_zh": "2022年能源领涨",
                "tier": "s",
                "date_from": onset,
                "date_to": end,
                "node_ids": ["XLE"],
            }
        )

    # --- Preset 3: 2023-01 AI ignition (Tier M) ---
    ai_nodes_pattern = ["aimodels", "aiagi", "aiapplications", "aidata", "aiadssearch",
                        "bigdataaiplatforms", "ainetworking", "smarthomevoiceai"]
    ai_ignition_ep = ep_m[
        (ep_m["node"].isin(ai_nodes_pattern))
        & (ep_m["direction"] == "in")
        & (ep_m["onset_date"] >= pd.Timestamp("2022-11-01"))
        & (ep_m["onset_date"] <= pd.Timestamp("2023-06-30"))
    ]
    if not ai_ignition_ep.empty:
        onset = str(ai_ignition_ep["onset_date"].min().date())
        ends = ai_ignition_ep["exhausted_date"].dropna()
        end = str(ends.max().date()) if not ends.empty else str(ai_ignition_ep["confirmed_date"].max().date())
        presets.append(
            {
                "id": "2023_ai_ignition",
                "label_en": "2023 AI Ignition",
                "label_zh": "2023年AI爆发",
                "tier": "m",
                "date_from": onset,
                "date_to": end,
                "node_ids": sorted(ai_ignition_ep["node"].unique().tolist()),
            }
        )

    # --- Preset 4: 2025-26 semis -> healthcare ---
    semi_hc_ep = ep_m[
        (ep_m["node"].str.contains("semi|health|longevity", case=False, na=False))
        & (ep_m["direction"] == "in")
        & (ep_m["onset_date"] >= pd.Timestamp("2025-01-01"))
    ]
    # Also grab June 2026 cascade (from the data: healthcareitdata, softwareenterprise in)
    june26_ep = ep_m[
        (ep_m["onset_date"] >= pd.Timestamp("2026-06-01"))
        & (ep_m["direction"] == "in")
    ]
    combined = pd.concat([semi_hc_ep, june26_ep]).drop_duplicates(subset="episode_id")
    if not combined.empty:
        onset = str(combined["onset_date"].min().date())
        ends = combined["exhausted_date"].dropna()
        end = str(ends.max().date()) if not ends.empty else str(combined["confirmed_date"].max().date())
        presets.append(
            {
                "id": "2025_26_semis_healthcare",
                "label_en": "2025–26 Semis → Healthcare",
                "label_zh": "2025–26年半导体→医疗",
                "tier": "m",
                "date_from": onset,
                "date_to": end,
                "node_ids": sorted(combined["node"].unique().tolist()),
            }
        )

    # --- Preset 5: 2022 value rotation (Tier F) - self-guarding, no invented dates ---
    if ep_f is not None and not ep_f.empty:
        value_nodes = {"IWD", "USMV"}
        value_ep = ep_f[
            (ep_f["node"].isin(value_nodes))
            & (ep_f["direction"] == "in")
            & (ep_f["onset_date"] >= pd.Timestamp("2022-01-01"))
            & (ep_f["onset_date"] <= pd.Timestamp("2022-12-31"))
        ]
        if not value_ep.empty:
            onset = str(value_ep["onset_date"].min().date())
            ends = value_ep["exhausted_date"].dropna()
            end = (str(ends.max().date()) if not ends.empty
                   else str(value_ep["confirmed_date"].max().date()))
            presets.append(
                {
                    "id": "2022_value_rotation",
                    "label_en": "2022 Value Rotation",
                    "label_zh": "2022年价值轮动",
                    "tier": "f",
                    "date_from": onset,
                    "date_to": end,
                    "node_ids": sorted(value_ep["node"].unique().tolist()),
                }
            )

    return presets


# ── manifest writer ───────────────────────────────────────────────────────────

def build_manifest(
    registry_s: list[dict],
    registry_m: list[dict],
    chunks_s: list[dict],
    chunks_m: list[dict],
    registry_f: list[dict] | None = None,
    chunks_f: list[dict] | None = None,
    built_at: str | None = None,
) -> dict:
    """Build tm_manifest.json payload."""
    if built_at is None:
        built_at = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")

    def _chunk_meta(chunk: dict, tier: str) -> dict:
        return {
            "key": chunk["period"],
            "file": f"tm_{tier}_{chunk['period']}.json",
            "date_from": chunk["dates"][0] if chunk["dates"] else None,
            "date_to": chunk["dates"][-1] if chunk["dates"] else None,
            "n_dates": len(chunk["dates"]),
        }

    tier_s_dates = [d for c in chunks_s for d in c["dates"]]
    tier_m_dates = [d for c in chunks_m for d in c["dates"]]
    tier_f_dates = [d for c in (chunks_f or []) for d in c["dates"]]

    return {
        "schema_version": 3,
        "built_at": built_at,
        "tiers": {
            "s": {
                "label": "Sectors",
                "granularity": "daily",
                "period_type": "Q",
                "date_from": tier_s_dates[0] if tier_s_dates else None,
                "date_to": tier_s_dates[-1] if tier_s_dates else None,
                "n_nodes": len(registry_s),
                "n_chunks": len(chunks_s),
                "chunks": [_chunk_meta(c, "s") for c in chunks_s],
            },
            "m": {
                "label": "Subsectors + Themes",
                "granularity": "daily",
                "period_type": "M",
                "survivorship_note": (
                    "Membership as of 2026-06 — historical composition approximated"
                ),
                "date_from": tier_m_dates[0] if tier_m_dates else None,
                "date_to": tier_m_dates[-1] if tier_m_dates else None,
                "n_nodes": len(registry_m),
                "n_chunks": len(chunks_m),
                "chunks": [_chunk_meta(c, "m") for c in chunks_m],
            },
            "f": {
                "label": "Factors",
                "granularity": "daily",
                "period_type": "Q",
                "context_note": (
                    "6 style sleeves, ~0.9 collinear; SPY-excess replay, context only - not an edge."
                ),
                "date_from": tier_f_dates[0] if tier_f_dates else None,
                "date_to": tier_f_dates[-1] if tier_f_dates else None,
                "n_nodes": len(registry_f or []),
                "n_chunks": len(chunks_f or []),
                "chunks": [_chunk_meta(c, "f") for c in (chunks_f or [])],
            },
        },
        "registry": {
            "s": registry_s,
            "m": registry_m,
            "f": registry_f or [],
        },
    }
