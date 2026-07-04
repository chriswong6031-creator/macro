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
    "vix_regime": float | null          # latest vix_pctile
  },
  "complexes": [
    {
      "id": str,
      "name": str,
      "name_zh": str,
      "state": str,                     # "active_in" | "active_out" | "quiet"
      "tier": str | null,               # detection tier of most-advanced episode
      "direction": str | null,          # "in" | "out" | null
      "n_members_active": int
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
      "analogues": list | null          # from memory_active_analogues.json if present
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


def _complex_state(complex_def: dict, active_ep_nodes: set[str],
                   active_ep_map: dict[str, list[dict]]) -> dict:
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

    return {
        "id": complex_def.get("id", ""),
        "name": complex_def.get("name", ""),
        "name_zh": complex_def.get("name_zh", ""),
        "state": state,
        "tier": best_tier,
        "direction": best_dir,
        "n_members_active": n_active,
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

    # --- 4. Complexes ---
    complexes_def = _load_rotation_groups(data_dir)
    complexes_out = [_complex_state(c, active_ep_nodes, active_ep_map) for c in complexes_def]

    n_active_complexes = sum(1 for c in complexes_out if c["state"] != "quiet")

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
