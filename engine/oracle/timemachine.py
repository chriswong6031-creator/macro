"""Oracle P6 — Time Machine feed helpers.

Pure functions consumed by scripts/build_oracle_timemachine.py.
No side effects; no network; numpy + pandas only.

Granularity:
  Tier S — quarterly chunks, DAILY data (11 nodes × ~63 dates ≈ 9 KB/chunk).
  Tier M — monthly chunks, WEEKLY data (Friday-only; 354 nodes × ~12 dates ≈ 35 KB/chunk).
  Total uncompressed budget: ~1 MB (S) + ~1 MB (M) + ~1 MB episodes ≈ 3 MB, well within the
  6 MB ceiling.  Months where accel_z is 100 % null (2021-07 → 2022-01) are skipped for Tier M
  (the RRG visualization needs both axes).

Chunk format (per tier per period):
  {
    "dates": ["YYYY-MM-DD", ...],          # sorted ascending
    "data": {                              # keyed by node_id (int str)
        "0": [[rs, accel_z], ...],         # parallel to dates; null where missing
        ...
    }
  }

Manifest format:
  {
    "schema_version": 2,
    "built_at": "ISO UTC",
    "tiers": {
      "s": {"label": "Sectors", "granularity": "daily", "period_type": "Q",
             "date_from": "1998-12-22", "date_to": "...",
             "chunks": [{"key": "1999Q1", "file": "tm_s_1999Q1.json", ...}]},
      "m": {"label": "Subsectors + Themes", "granularity": "weekly",
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
    """Build Tier-M chunks, one per calendar month, WEEKLY granularity (Fridays only).

    Months where ``accel_z`` is 100% null are skipped — the RRG scatter requires
    both axes.  Period format: "YYYYMmm" e.g. "2022M02".
    """
    nodes = [r["name"] for r in registry]
    id_by_name = {r["name"]: str(r["id"]) for r in registry}

    dates_idx = panel_m.index.get_level_values("date")
    all_dates = dates_idx.unique().sort_values()

    # Keep only Fridays (weekday == 4); fall back to Thursday if a Friday is missing
    friday_dates: set = set()
    for d in all_dates:
        if d.weekday() == 4:  # Friday
            friday_dates.add(d)
    # For weeks where Friday is absent, include Thursday as fallback
    thursdays = {d for d in all_dates if d.weekday() == 3}
    for th in thursdays:
        # Check if the Friday of the same week is present
        try:
            fri = th + pd.Timedelta(days=1)
        except Exception:
            continue
        if fri not in friday_dates:
            friday_dates.add(th)

    friday_dates_sorted = sorted(friday_dates)

    periods = dates_idx.to_period("M").unique().sort_values()

    chunks = []
    for period in periods:
        # Only use Friday dates that fall in this period
        period_fridays = [
            d for d in friday_dates_sorted
            if d.to_period("M") == period
        ]
        if not period_fridays:
            continue

        # Skip months where accel_z is 100% null (early Tier-M warm-up period)
        mask = dates_idx.to_period("M") == period
        sub = panel_m[mask]
        if sub["accel_z"].isna().all():
            log.debug("Skipping %s: accel_z 100%% null", period)
            continue

        data: dict[str, list] = {}
        valid_dates = []
        for date in period_fridays:
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

    # Build presets from the catalog itself
    presets = _build_presets(ep_m, ep_s)

    return {"episodes": records, "presets": presets}


def _is_null(v: Any) -> bool:
    if v is None:
        return True
    try:
        return bool(pd.isna(v))
    except (TypeError, ValueError):
        return False


def _build_presets(ep_m: pd.DataFrame, ep_s: pd.DataFrame) -> list[dict]:
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

    return presets


# ── manifest writer ───────────────────────────────────────────────────────────

def build_manifest(
    registry_s: list[dict],
    registry_m: list[dict],
    chunks_s: list[dict],
    chunks_m: list[dict],
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

    return {
        "schema_version": 2,
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
                "granularity": "weekly",
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
        },
        "registry": {
            "s": registry_s,
            "m": registry_m,
        },
    }
