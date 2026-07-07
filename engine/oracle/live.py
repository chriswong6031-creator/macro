"""Oracle O4 — Live state bus: build_oracle_state() → site/basketdata/oracle_state.json.

Reads the already-built oracle artifacts (panel, episodes, rotation_groups) and
emits a structured JSON payload on the sector_pulse bus pattern.  Pure assembler —
no heavy compute here; that lives in the build_oracle_* scripts.  Degrade-never-raise
on every optional input.

OUTPUT SCHEMA (oracle_state.json)
----------------------------------
{
  "schema": "oracle_state.v1",
  "asof": "YYYY-MM-DD",
  "regime": {
    "n_active_complexes": int,          # complexes with ≥1 active (non-exhausted) episode
    "breadth": float,                   # mean breadth_50 across panel nodes (latest row)
    "vix_regime": float | null,         # latest vix_pctile
    "rotation_tag": {                   # A3 — ROTATION / LIQUIDATION / ACCUMULATION / quiet
      "tag": str,                       # "rotation" | "liquidation" | "accumulation" | "quiet"
      "tag_zh": str,                    # bilingual tag
      "n_sources": int,                 # complexes with active OUT episodes at confirmed+ tier
      "n_sinks": int,                   # complexes with active IN episodes at confirmed+ tier
      "source_names": [str, ...],       # names of source complexes
      "sink_names": [str, ...],         # names of sink complexes
      "description_en": str,            # descriptive language only — NEVER forecast
      "description_zh": str
    }
  },
  "complexes": [
    {
      "id": str,
      "name": str,
      "name_zh": str,
      "state": str,                     # "active_in" | "active_out" | "quiet"
      "tier": str | null,               # detection tier of most-advanced episode
      "direction": str | null,          # "in" | "out" | null
      "n_members_active": int,
      "personality": str | null         # B1 personality class if available
    }, ...
  ],
  "active_episodes": [
    {
      "node": str,
      "direction": str,
      "tier": str,                      # "onset" | "confirmed" | "undeniable"
      "onset_date": str,
      "confirmed_date": str | null,
      "two_sided": bool,
      "pair": str | null,               # paired episode_id if two_sided
      "survivorship_flagged": bool,
      "base_rate_context": dict | null, # from memory_base_rates.json if present
      "analogues": list | null,         # from memory_active_analogues.json if present
      "personality": str | null         # B1 personality class for this node if available
    }, ...
  ],
  "onset_watchlist": [str, ...],        # nodes with accel_z > WATCH_THRESHOLD but no active episode
  "disclaimers": {
    "display_only": true,
    "error_rates": {
      "onset_to_confirmed_conversion": float | null,
      "false_start_rate": float | null
    }
  }
}

R4 BINDING CONSTRAINTS (ORACLE_GAUNTLET_P3_ADJUDICATION.md)
-------------------------------------------------------------
* Nothing here ships a predictive claim.
* onset_tier alerts MUST embed the false-start rate.
* Banner remains gated on confirmed + breadth floor (D7).
* Tilt stays config-gated OFF.
* rotation_tag is DESCRIPTIVE/DISPLAY tier — all language describes what is observed
  on the tape, never what will happen.

A3 REGIME TAG CONFIG
---------------------
REGIME_CONFIRMED_FRACTION  — fraction of complex members that must have active
  confirmed+ OUT/IN episodes for that complex to count as a source/sink.
  Default 0.0 (any confirmed+ episode in the complex qualifies).
REGIME_MIN_SOURCES / REGIME_MIN_SINKS — minimums for liquidation / accumulation.
"""
from __future__ import annotations

import json
import logging
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd

from lib import config as _cfg

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Thresholds
# ---------------------------------------------------------------------------
WATCH_ACCEL_Z = 0.8          # accel_z above this → onset_watchlist (no active episode)
SCHEMA = "oracle_state.v1"

# A3 regime-tag config (provenance-commented)
# Fraction of complex members that must have a confirmed+ OUT/IN episode for
# that complex to count as source/sink.  0.0 means ANY confirmed+ episode
# in the complex qualifies (conservative: avoids missing a real rotation).
# Source: spec A3 "confirmed+ tier covering ≥ a config fraction of members".
# 0.0 DISABLES the fraction gate: required = max(1, int(n*0.0)) = 1, i.e. any
# single confirmed member qualifies its complex as source/sink (intended v1
# behavior — the tag is display-only and never gates). NOTE: a complex with
# both confirmed-out and confirmed-in members counts as BOTH source and sink,
# so intra-complex two-sided flow alone can yield the global "rotation" tag.
REGIME_CONFIRMED_FRACTION: float = 0.0
# Minimum number of source complexes to call "liquidation" (≥2 sources, 0 sinks)
REGIME_LIQUIDATION_MIN_SOURCES: int = 2  # spec: "≥2 sources, 0 sinks"
# Minimum number of sink complexes to call "accumulation" (≥2 sinks, 0 sources)
REGIME_ACCUMULATION_MIN_SINKS: int = 2   # spec: "≥2 sinks, 0 sources"

# Error-rate keys from gauntlet p3_results.json
_ER_ONSET_TO_CONFIRMED = "onset_to_confirmed_rate_out"   # representative (out episodes)
_ER_FALSE_START = "false_start_rate_out_5d"              # representative (out episodes)


# ---------------------------------------------------------------------------
# Internal helpers — all degrade-never-raise
# ---------------------------------------------------------------------------

def _read_json(p: Path) -> dict | list | None:
    try:
        return json.loads(p.read_text()) if p.exists() else None
    except Exception:  # noqa: BLE001
        return None


def _episodes_path(data_dir: Path, tier: str) -> Path:
    return data_dir / "oracle" / f"episodes_{tier}.parquet"


def _panel_path(data_dir: Path, tier: str) -> Path:
    return data_dir / "oracle" / f"panel_{tier}.parquet"


def _load_panel_latest(data_dir: Path) -> pd.DataFrame | None:
    """Load the latest panel row for each node (Tier S — survivorship-clean)."""
    p = _panel_path(data_dir, "s")
    if not p.exists():
        return None
    try:
        panel = pd.read_parquet(p)
        dates = panel.index.get_level_values("date")
        last = dates.max()
        return panel.xs(last, level="date")
    except Exception:  # noqa: BLE001
        log.warning("oracle_live: could not load panel_s", exc_info=True)
        return None


def _load_episodes(data_dir: Path) -> pd.DataFrame | None:
    """Load episodes (Tier S + M merged) for active-episode detection."""
    frames = []
    for tier in ("s", "m"):
        p = _episodes_path(data_dir, tier)
        if not p.exists():
            continue
        try:
            df = pd.read_parquet(p)
            df["tier_src"] = tier
            frames.append(df)
        except Exception:  # noqa: BLE001
            log.warning("oracle_live: could not load episodes_%s", tier, exc_info=True)
    if not frames:
        return None
    ep = pd.concat(frames, ignore_index=True)
    ep["onset_date"] = pd.to_datetime(ep["onset_date"], errors="coerce")
    ep["confirmed_date"] = pd.to_datetime(ep["confirmed_date"], errors="coerce")
    ep["undeniable_date"] = pd.to_datetime(ep["undeniable_date"], errors="coerce")
    ep["exhausted_date"] = pd.to_datetime(ep["exhausted_date"], errors="coerce")
    return ep


def _active_episodes(ep: pd.DataFrame, as_of: pd.Timestamp) -> pd.DataFrame:
    """Rows with no exhausted_date or exhausted_date > as_of."""
    not_exhausted = ep["exhausted_date"].isna() | (ep["exhausted_date"] > as_of)
    return ep[not_exhausted].copy()


def _tier_of(row: pd.Series) -> str:
    """Detects the current tier for an active episode row."""
    if pd.notna(row.get("undeniable_date")):
        return "undeniable"
    if pd.notna(row.get("confirmed_date")):
        return "confirmed"
    return "onset"


def _load_rotation_groups(data_dir: Path) -> list[dict]:
    rg = _read_json(data_dir / "oracle" / "rotation_groups.json")
    if isinstance(rg, dict):
        return rg.get("complexes") or []
    return []


def _load_base_rates(data_dir: Path) -> dict | None:
    """memory_base_rates.json — degrade to None if absent."""
    p = data_dir / "oracle" / "memory_base_rates.json"
    d = _read_json(p)
    return d if isinstance(d, dict) else None


def _load_active_analogues(data_dir: Path) -> dict | None:
    """memory_active_analogues.json — degrade to None if absent."""
    p = data_dir / "oracle" / "memory_active_analogues.json"
    d = _read_json(p)
    return d if isinstance(d, dict) else None


def _error_rates_from_gauntlet(data_dir: Path) -> dict:
    """Read S3 error rates from gauntlet/p3_results.json.  Never hardcode."""
    p = data_dir / "oracle" / "gauntlet" / "p3_results.json"
    d = _read_json(p)
    if not isinstance(d, dict):
        return {"onset_to_confirmed_conversion": None, "false_start_rate": None}
    er = d.get("s3_error_rates") or {}
    otc = er.get(_ER_ONSET_TO_CONFIRMED)
    fsr = er.get(_ER_FALSE_START)
    return {
        "onset_to_confirmed_conversion": float(otc) if otc is not None else None,
        "false_start_rate": float(fsr) if fsr is not None else None,
    }


def _load_personality(data_dir: Path) -> dict:
    """Load personality.json for B1 per-node personality classes.

    Degrades to empty dict if not yet built (first run before personality step).
    personality.json has schema oracle_personality.v1 with a "nodes" dict mapping
    node_id → {personality, stats, ...}.  We extract just the class string.
    """
    p = data_dir / "oracle" / "personality.json"
    d = _read_json(p)
    if not isinstance(d, dict):
        return {}
    # Full payload format: {schema, nodes: {node: {personality: str, ...}}}
    nodes = d.get("nodes")
    if isinstance(nodes, dict):
        return {str(k): v.get("personality") for k, v in nodes.items()
                if isinstance(v, dict) and v.get("personality")}
    # Flat fallback (legacy): node → personality string directly
    return {str(k): v for k, v in d.items() if isinstance(v, str)}


def _compute_regime_tag(
    complexes_def: list[dict],
    active_ep_map: dict[str, list[dict]],
    confirmed_fraction: float = REGIME_CONFIRMED_FRACTION,
    liquidation_min_sources: int = REGIME_LIQUIDATION_MIN_SOURCES,
    accumulation_min_sinks: int = REGIME_ACCUMULATION_MIN_SINKS,
) -> dict:
    """A3 — Compute the ROTATION / LIQUIDATION / ACCUMULATION / quiet regime tag.

    A complex is a SOURCE if it has ≥1 active confirmed+ OUT episode covering
    ≥ confirmed_fraction of its members (default 0.0 → any confirmed+ OUT episode).
    A complex is a SINK if it has ≥1 active confirmed+ IN episode (same rule).

    Tags (mutually exclusive, evaluated in order):
      "rotation"     — ≥1 source AND ≥1 sink
      "liquidation"  — ≥2 sources, 0 sinks
      "accumulation" — ≥2 sinks, 0 sources
      "quiet"        — else

    All language is DESCRIPTIVE only — no forecast claim.
    Data source: active_ep_map (confirmed+ tier only per spec A3).
    """
    _confirmed_tiers = {"confirmed", "undeniable"}

    source_complexes: list[str] = []
    sink_complexes: list[str] = []
    source_names: list[str] = []
    sink_names: list[str] = []

    for c in complexes_def:
        cid = c.get("id", "")
        cname = c.get("name", cid)
        members = set(c.get("members") or [])
        if not members:
            continue

        # Confirmed+ OUT episodes for members of this complex
        out_members_with_confirmed = sum(
            1 for m in members
            if any(
                e.get("direction") == "out" and e.get("tier") in _confirmed_tiers
                for e in active_ep_map.get(m, [])
            )
        )
        # Confirmed+ IN episodes for members of this complex
        in_members_with_confirmed = sum(
            1 for m in members
            if any(
                e.get("direction") == "in" and e.get("tier") in _confirmed_tiers
                for e in active_ep_map.get(m, [])
            )
        )

        required = max(1, int(len(members) * confirmed_fraction))
        if out_members_with_confirmed >= required:
            source_complexes.append(cid)
            source_names.append(cname)
        if in_members_with_confirmed >= required:
            sink_complexes.append(cid)
            sink_names.append(cname)

    n_sources = len(source_complexes)
    n_sinks = len(sink_complexes)

    # Tag assignment — order matters (rotation > liquidation > accumulation > quiet)
    if n_sources >= 1 and n_sinks >= 1:
        tag = "rotation"
        tag_zh = "轮动"
        description_en = (
            "Broad de-risking is visible in some sectors while re-risking is "
            "observed simultaneously in others — a cross-sector rotation is "
            "underway on the tape. Descriptive read from confirmed-tier episodes."
        )
        description_zh = (
            "部分行业的相对强度正在下降，同时其他行业的相对强度正在上升——"
            "行情面上正在发生跨行业轮动。基于确认层级事件的描述性读数。"
        )
    elif n_sources >= liquidation_min_sources and n_sinks == 0:
        tag = "liquidation"
        tag_zh = "流动性收缩"
        description_en = (
            f"Broad de-risking in progress: {n_sources} sector complexes are "
            "showing confirmed outflow episodes with no offsetting inflow. "
            "This describes what is observed on the tape — not a forecast."
        )
        description_zh = (
            f"广泛去风险化正在进行：{n_sources} 个行业复合体出现确认流出信号，"
            "且无对应的流入信号。描述行情面所观察到的情况，非预测。"
        )
    elif n_sinks >= accumulation_min_sinks and n_sources == 0:
        tag = "accumulation"
        tag_zh = "资金积累"
        description_en = (
            f"Broad re-risking observed: {n_sinks} sector complexes are "
            "showing confirmed inflow episodes with no offsetting outflow. "
            "This describes what is observed on the tape — not a forecast."
        )
        description_zh = (
            f"广泛承险化正在进行：{n_sinks} 个行业复合体出现确认流入信号，"
            "且无对应的流出信号。描述行情面所观察到的情况，非预测。"
        )
    else:
        tag = "quiet"
        tag_zh = "平静"
        description_en = (
            "No broad rotation pattern is currently detected at confirmed tier. "
            "Descriptive read — confirmed-tier episode breadth is below the "
            "rotation/liquidation/accumulation thresholds."
        )
        description_zh = (
            "当前未在确认层级检测到广泛轮动形态。描述性读数——"
            "确认层级事件宽度低于轮动/流动性收缩/资金积累阈值。"
        )

    return {
        "tag": tag,
        "tag_zh": tag_zh,
        "n_sources": n_sources,
        "n_sinks": n_sinks,
        "source_names": source_names,
        "sink_names": sink_names,
        "description_en": description_en,
        "description_zh": description_zh,
    }


def _complex_state(complex_def: dict, active_ep_nodes: set[str],
                   active_ep_map: dict[str, list[dict]],
                   personality_map: dict[str, str] | None = None) -> dict:
    """Summarize one complex's rotation state from active episodes."""
    members = set(complex_def.get("members") or [])
    active_in = [n for n in members if n in active_ep_nodes
                 and any(e.get("direction") == "in" for e in active_ep_map.get(n, []))]
    active_out = [n for n in members if n in active_ep_nodes
                  and any(e.get("direction") == "out" for e in active_ep_map.get(n, []))]
    n_active = len(set(active_in) | set(active_out))

    # Best-available tier (undeniable > confirmed > onset)
    tier_order = {"undeniable": 3, "confirmed": 2, "onset": 1}
    best_tier = None
    best_dir = None
    best_score = 0
    for nodes_list, direction in ((active_out, "out"), (active_in, "in")):
        for n in nodes_list:
            for ep in active_ep_map.get(n, []):
                if ep.get("direction") != direction:
                    continue
                t = ep.get("tier", "onset")
                sc = tier_order.get(t, 0)
                if sc > best_score:
                    best_score, best_tier, best_dir = sc, t, direction

    if active_out and active_in:
        state = "active_two_sided"
    elif active_out:
        state = "active_out"
    elif active_in:
        state = "active_in"
    else:
        state = "quiet"

    # B1: personality of the complex's most active node (best-tier episode node)
    personality: str | None = None
    if personality_map:
        # Try to find personality for the best-tier node, then any active node
        all_active = list(active_out) + list(active_in)
        for n in all_active:
            p = personality_map.get(n)
            if p:
                personality = p
                break

    return {
        "id": complex_def.get("id", ""),
        "name": complex_def.get("name", ""),
        "name_zh": complex_def.get("name_zh", ""),
        "state": state,
        "tier": best_tier,
        "direction": best_dir,
        "n_members_active": n_active,
        "personality": personality,
    }


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def build_oracle_state(
    data_dir: Path | str | None = None,
    as_of: date | str | None = None,
) -> dict:
    """Assemble the oracle_state payload from committed oracle artifacts.

    All inputs are optional — the function degrades gracefully when any
    artifact is missing or malformed.

    Parameters
    ----------
    data_dir : Path | str | None
        Root data directory.  Defaults to config.data_dir().
    as_of : date | str | None
        Override the reference date.  Defaults to the latest panel date.
    """
    data_dir = Path(data_dir) if data_dir else _cfg.data_dir()

    # --- 1. Establish as_of ---
    panel_latest = _load_panel_latest(data_dir)
    if as_of is not None:
        as_of_ts = pd.Timestamp(as_of)
    elif panel_latest is not None:
        # panel_s index is (node, date) — _load_panel_latest returns the xs slice
        # (node-only index); we need the date from the panel itself
        p = _panel_path(data_dir, "s")
        try:
            raw = pd.read_parquet(p)
            as_of_ts = pd.Timestamp(raw.index.get_level_values("date").max())
        except Exception:  # noqa: BLE001
            as_of_ts = pd.Timestamp.now("UTC").normalize().tz_localize(None)
    else:
        as_of_ts = pd.Timestamp.now("UTC").normalize().tz_localize(None)

    asof_str = as_of_ts.strftime("%Y-%m-%d")

    # --- 2. Regime aggregate (from panel_s latest) ---
    breadth: float | None = None
    vix_regime: float | None = None
    if panel_latest is not None:
        try:
            b_col = panel_latest["breadth_50"].dropna()
            breadth = float(b_col.mean()) if len(b_col) else None
            v_col = panel_latest["vix_pctile"].dropna()
            vix_regime = float(v_col.iloc[0]) if len(v_col) else None
        except Exception:  # noqa: BLE001
            pass


    # --- 3. Episodes ---
    ep = _load_episodes(data_dir)
    active_ep_df = _active_episodes(ep, as_of_ts) if ep is not None else pd.DataFrame()

    # Build maps
    active_ep_map: dict[str, list[dict]] = {}  # node → [episode row dicts with tier]
    for _, row in active_ep_df.iterrows():
        node = str(row.get("node", ""))
        if not node:
            continue
        ep_item = {
            "episode_id": row.get("episode_id", ""),
            "direction": row.get("direction", ""),
            "tier": _tier_of(row),
            "onset_date": row["onset_date"].strftime("%Y-%m-%d") if pd.notna(row.get("onset_date")) else None,
            "confirmed_date": row["confirmed_date"].strftime("%Y-%m-%d") if pd.notna(row.get("confirmed_date")) else None,
            "two_sided": bool(row.get("two_sided", False)),
            "pair": (None if pd.isna(row.get("paired_episode_id"))
                     else row.get("paired_episode_id")),
            "survivorship_flagged": bool(row.get("survivorship_flagged", False)),
        }
        active_ep_map.setdefault(node, []).append(ep_item)

    active_ep_nodes = set(active_ep_map.keys())

    # --- 4. Complexes + B1 personality map ---
    complexes_def = _load_rotation_groups(data_dir)
    personality_map = _load_personality(data_dir)
    complexes_out = [
        _complex_state(c, active_ep_nodes, active_ep_map, personality_map)
        for c in complexes_def
    ]

    n_active_complexes = sum(1 for c in complexes_out if c["state"] != "quiet")

    # --- 4b. R-SP19 personality_context additive wave ---
    # Appends personality_context to each complex dict from the stock-personality
    # site aggregate.  Fail-open: absent aggregate ⇒ no field emitted.
    # This is ADDITIVE and does not rename or remove any existing field.
    try:
        from engine.oracle.personality_context import append_personality_context  # noqa: PLC0415
        # Resolve repo root: data_dir = <repo>/data
        _repo = data_dir.parent
        complexes_out = append_personality_context(
            complexes_out, complexes_def, repo=_repo
        )
    except Exception:  # noqa: BLE001
        log.warning("oracle_live: personality_context wave failed — skipping (fail-open)",
                    exc_info=True)

    # --- 4.5. A3 rotation tag (computed from active_ep_map + complexes_def) ---
    try:
        rotation_tag = _compute_regime_tag(complexes_def, active_ep_map)
    except Exception:  # noqa: BLE001
        log.warning("oracle_live: _compute_regime_tag failed — defaulting to quiet", exc_info=True)
        rotation_tag = {
            "tag": "quiet", "tag_zh": "平静", "n_sources": 0, "n_sinks": 0,
            "source_names": [], "sink_names": [],
            "description_en": "Regime tag unavailable (computation error).",
            "description_zh": "制度标签不可用（计算错误）。",
        }

    # --- 5. Active episodes (structured) ---
    base_rates_meta = _load_base_rates(data_dir)
    analogues_meta = _load_active_analogues(data_dir)

    active_episodes_out = []
    for node, eps in sorted(active_ep_map.items()):
        for ep_item in eps:
            br_ctx = None
            if base_rates_meta is not None:
                # Degrade gracefully — look for a matching direction/tier key
                br_ctx = (base_rates_meta.get(f"{ep_item['direction']}_{ep_item['tier']}") or
                          base_rates_meta.get(ep_item["direction"]))
            anl = None
            if analogues_meta is not None:
                anl = analogues_meta.get(ep_item.get("episode_id") or "")
            # B1: fold personality into active episode
            node_personality = personality_map.get(node) if personality_map else None
            active_episodes_out.append({
                "node": node,
                "direction": ep_item["direction"],
                "tier": ep_item["tier"],
                "onset_date": ep_item["onset_date"],
                "confirmed_date": ep_item["confirmed_date"],
                "two_sided": ep_item["two_sided"],
                "pair": ep_item["pair"],
                "survivorship_flagged": ep_item["survivorship_flagged"],
                "base_rate_context": br_ctx,
                "analogues": anl,
                "personality": node_personality,
            })

    # --- 6. Onset watchlist (panel accel_z > threshold, no active episode) ---
    onset_watchlist: list[str] = []
    if panel_latest is not None:
        try:
            az = panel_latest["accel_z"].dropna()
            for node_name, val in az.items():
                if float(val) >= WATCH_ACCEL_Z and node_name not in active_ep_nodes:
                    onset_watchlist.append(str(node_name))
        except Exception:  # noqa: BLE001
            pass

    # --- 7. Error rates from gauntlet (never hardcoded) ---
    error_rates = _error_rates_from_gauntlet(data_dir)

    payload = {
        "schema": SCHEMA,
        "asof": asof_str,
        "regime": {
            "n_active_complexes": n_active_complexes,
            "breadth": round(breadth, 4) if breadth is not None else None,
            "vix_regime": round(vix_regime, 4) if vix_regime is not None else None,
            "rotation_tag": rotation_tag,  # A3
        },
        "complexes": complexes_out,
        "active_episodes": active_episodes_out,
        "onset_watchlist": onset_watchlist,
        "disclaimers": {
            "display_only": True,
            "error_rates": error_rates,
        },
    }

    # Stamp payload_version + per-episode confidence_class / lineage (additive).
    # Parallel waves (A3 regime_tag, B1 personality) may have already added fields;
    # stamp_payload is tolerant and will not overwrite.
    try:
        from engine.oracle.contract import stamp_payload
        stamp_payload(payload)
    except Exception:  # noqa: BLE001
        log.warning("oracle_live: contract.stamp_payload failed — payload ships without stamps",
                    exc_info=True)

    return payload


def write_oracle_state(
    payload: dict,
    out_dir: Path | str | None = None,
) -> None:
    """Write oracle_state.json to site/basketdata/. Mirrors write_pulse idiom."""
    try:
        from lib import config as _cfg2
        root = _cfg2.ROOT if out_dir is None else Path(out_dir)
        p = Path(root) if out_dir else Path(_cfg2.ROOT) / "site" / "basketdata"
        if out_dir:
            p = Path(out_dir)
        p.mkdir(parents=True, exist_ok=True)
        out_path = p / "oracle_state.json"
        out_path.write_text(json.dumps(payload, separators=(",", ":"), default=str))
        log.info("oracle_live: wrote oracle_state.json (asof=%s, %d active_episodes, %d watchlist)",
                 payload.get("asof"), len(payload.get("active_episodes", [])),
                 len(payload.get("onset_watchlist", [])))
    except Exception:  # noqa: BLE001
        log.warning("oracle_live: write_oracle_state failed", exc_info=True)
