"""engine.metabolism.generic_fitness — Generic fitness card builder (R-V6-4).

For every charter in config/lobe_charters.yml with:
  - lifecycle_state in ("probation", "active")
  - fitness_sensors declared as a list of dicts with 'id' and 'store' keys
    (structured sensors — loop-manageable lobes)
  - AND no bespoke builder (skips lobe_id == "til")

...writes data/metabolism/fitness/<lobe_id>.json in the SAME shape that
organism_state._discover_fitness_cards() reads (filename-stem discovery).

Card shape mirrors til_fitness.v1:
  {
    "schema":   "metabolism.generic_fitness.v1",
    "as_of":    "YYYY-MM-DD",
    "lobe":     "<lobe_id>",
    "maturity": "accruing" | "partial" | "ready",
    "sensors":  {
      "<sensor_id>": {
        "value":         null (honest: never fabricated),
        "maturity":      "accruing" | "ready",
        "store_present": bool,
        "store_asof":    str | null,
        "rows_accrued":  int | null,
        "note":          str | null,
      },
      ...
    },
    "composite": null (null while any sensor is accruing — honesty law),
    "authority": { is_context_only: true, ... },
    "notes":     str,
  }

AUTHORITY BLOCK: is_context_only=True, all promotion flags False.
No LLM calls.  Tolerant reader (missing/corrupt charter → skip + log).
NEVER raises.  Per-lobe failures isolate.

History append: fitness cards do NOT embed history; the separate
data/metabolism/fitness_history/<lobe_id>.jsonl JSONL file is the
history path.  This module does NOT append to history — organism_state
reads fitness_history/ directly via _load_fitness_history().  On each
run this module overwrites the card (like til_fitness does), and the
nightly agenda step appends to fitness_history/ separately if present.
"""
from __future__ import annotations

import json
import logging
import os
import stat as stat_mod
from datetime import datetime, date, timezone
from pathlib import Path
from typing import Any

log = logging.getLogger(__name__)

SCHEMA = "metabolism.generic_fitness.v1"

# Lobes with bespoke builders — skip here.
# F3 fix: site-us-standouts and site-china-standouts have bespoke builders
# (engine/standout_audit.py and engine/china_standout_audit.py) that write the
# real sensor content to data/metabolism/fitness/standouts_us.json and
# data/metabolism/fitness/standouts_cn.json.  The charter store paths point at
# those same files.  If generic_fitness runs on these lobes it overwrites the
# bespoke card with an empty sensor-probe-only card, stranding the real sensors.
# Mirror the "til" exemption: bespoke producer owns the card; generic builder skips.
_BESPOKE_LOBE_IDS = frozenset({"til", "site-us-standouts", "site-china-standouts"})

# Lifecycle states that are loop-managed (get a fitness card)
_LOOP_MANAGED_STATES = frozenset({"probation", "active"})

AUTHORITY_BLOCK: dict[str, Any] = {
    "is_context_only": True,
    "may_rank": False,
    "may_gate": False,
    "may_size": False,
    "may_escalate": False,
    "display_only": True,
    "not_a_signal": True,
    "tier": "shadow",
    "forbidden_uses": [
        "ranking", "sizing", "alert_escalation", "board_ordering",
        "mastermind_arming", "scored_path",
    ],
}


# ── Config reader ──────────────────────────────────────────────────────────────

def _repo_root(root: Path | None = None) -> Path:
    if root is not None:
        return Path(root)
    return Path(__file__).resolve().parent.parent.parent


def _load_charters(root: Path) -> dict[str, dict]:
    """Load config/lobe_charters.yml.  Returns {} on any error.  NEVER raises."""
    try:
        import yaml  # noqa: PLC0415
        p = root / "config" / "lobe_charters.yml"
        if not p.exists():
            log.info("generic_fitness: lobe_charters.yml absent at %s", p)
            return {}
        data = yaml.safe_load(p.read_text(encoding="utf-8"))
        return (data or {}).get("charters") or {}
    except Exception as exc:  # noqa: BLE001
        log.warning("generic_fitness: cannot load lobe_charters.yml: %s", exc)
        return {}


def _has_structured_sensors(sensors: Any) -> bool:
    """Return True iff sensors is a non-empty list where EVERY item is a dict
    with 'id' and 'store' keys.  Bare-string lists (e.g., ['liveness']) return False.
    """
    if not isinstance(sensors, list) or not sensors:
        return False
    return all(isinstance(s, dict) and "id" in s and "store" in s for s in sensors)


# ── Per-sensor store probing ──────────────────────────────────────────────────

def _store_content_asof(store_path: Path, last_line: str | None) -> str | None:
    """Content as-of date for a sensor store: the last JSONL row's timestamp,
    or a JSON store's top-level as_of/asof/produced_at. None when no stamp is
    readable (caller falls back to mtime)."""
    try:
        doc = None
        if last_line is not None:
            doc = json.loads(last_line)
        elif store_path.suffix.lower() == ".json":
            doc = json.loads(store_path.read_text(encoding="utf-8", errors="replace"))
        if isinstance(doc, dict):
            stamp = (doc.get("ts") or doc.get("as_of") or doc.get("asof")
                     or doc.get("produced_at"))
            if stamp:
                return str(stamp)[:10]
    except Exception:  # noqa: BLE001
        pass
    return None


def _probe_store(sensor: dict, root: Path) -> dict[str, Any]:
    """Probe a sensor's store file for presence, content as-of, and row count.

    Returns a partial sensor card dict (no 'value' — callers add that).
    NEVER raises.
    """
    store_path_rel = sensor.get("store") or ""
    store_present = False
    store_asof: str | None = None
    rows_accrued: int | None = None
    note: str | None = None
    maturity_date_str: str | None = str(sensor.get("maturity_date") or "")
    today_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    # Determine maturity: accruing until maturity_date
    if maturity_date_str and maturity_date_str >= today_str:
        # maturity_date is in the future → accruing
        sensor_maturity = "accruing"
    elif maturity_date_str and maturity_date_str < today_str:
        # maturity_date is past → potentially ready (store check decides)
        sensor_maturity = "ready"
    else:
        # No maturity_date → check accruing flag
        accruing_flag = sensor.get("accruing", True)
        sensor_maturity = "accruing" if accruing_flag else "ready"

    try:
        if store_path_rel:
            store_path = root / store_path_rel
            if store_path.exists():
                store_present = True

                # Count rows: JSONL → line count; JSON → 1 (presence).
                # store_asof prefers a content stamp (last JSONL row's ts /
                # JSON as_of) over mtime — committed stores get
                # mtime = checkout time on CI/fresh worktrees (#2690 class);
                # mtime stays as the fallback for stamp-less stores.
                last_line: str | None = None
                try:
                    suffix = store_path.suffix.lower()
                    if suffix == ".jsonl":
                        content = store_path.read_text(encoding="utf-8", errors="replace")
                        lines = [ln for ln in content.splitlines() if ln.strip()]
                        rows_accrued = len(lines)
                        last_line = lines[-1] if lines else None
                    elif suffix == ".json":
                        rows_accrued = 1
                    else:
                        # Unknown format — just note present
                        rows_accrued = None
                except Exception:  # noqa: BLE001
                    rows_accrued = None

                store_asof = _store_content_asof(store_path, last_line)
                if store_asof is None:
                    try:
                        mtime = store_path.stat().st_mtime
                        store_asof = datetime.fromtimestamp(
                            mtime, tz=timezone.utc).strftime("%Y-%m-%d")
                    except Exception:  # noqa: BLE001
                        pass
            else:
                store_present = False
                note = f"store absent: {store_path_rel}"
    except Exception as exc:  # noqa: BLE001
        log.warning("generic_fitness._probe_store(%s): %s", store_path_rel, exc)
        store_present = False
        note = f"probe error: {exc}"

    return {
        "value": None,  # HONEST: no LLM-originated values
        "maturity": sensor_maturity,
        "store_present": store_present,
        "store_asof": store_asof,
        "rows_accrued": rows_accrued,
        "note": note,
    }


# ── Card builder for a single lobe ───────────────────────────────────────────

def _build_card(lobe_id: str, charter: dict, root: Path) -> dict[str, Any]:
    """Build the fitness card dict for one lobe.  NEVER raises (returns error card)."""
    try:
        sensors_cfg = charter.get("fitness_sensors") or []
        sensors: dict[str, Any] = {}

        for sensor in sensors_cfg:
            sensor_id = sensor.get("id") or ""
            if not sensor_id:
                continue
            probe = _probe_store(sensor, root)
            sensors[sensor_id] = probe

        # Roll-up maturity
        maturities = {s["maturity"] for s in sensors.values()}
        if not maturities:
            overall_maturity = "accruing"
        elif maturities == {"ready"}:
            overall_maturity = "ready"
        elif "accruing" in maturities and "ready" not in maturities:
            overall_maturity = "accruing"
        else:
            overall_maturity = "partial"

        # Composite is null while ANY sensor is still accruing (honesty law)
        composite = None  # NEVER fabricate

        card: dict[str, Any] = {
            "schema": SCHEMA,
            "as_of": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
            "lobe": lobe_id,
            "maturity": overall_maturity,
            "sensors": sensors,
            "composite": composite,
            "authority": AUTHORITY_BLOCK,
            "notes": (
                f"Generic fitness card for lobe '{lobe_id}'. "
                "Sensors are accruing until their maturity_date. "
                "Values are display-context only; no signal-path authority. "
                "composite=null while any sensor is accruing — honesty law (R-V6-4). "
                "No LLM-originated values anywhere in this card."
            ),
        }
        return card

    except Exception as exc:  # noqa: BLE001
        log.warning("generic_fitness._build_card(%s): %s", lobe_id, exc)
        return {
            "schema": SCHEMA,
            "as_of": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
            "lobe": lobe_id,
            "maturity": "accruing",
            "sensors": {},
            "composite": None,
            "authority": AUTHORITY_BLOCK,
            "notes": f"Error building fitness card for '{lobe_id}': {exc}",
        }


# ── Public API ────────────────────────────────────────────────────────────────

def build_generic_fitness_cards(root: Path | str | None = None) -> list[str]:
    """Build fitness cards for all loop-managed lobes without bespoke builders.

    For every charter in config/lobe_charters.yml where:
      - lifecycle_state in ("probation", "active")
      - fitness_sensors are structured (list of dicts with id+store)
      - lobe_id not in _BESPOKE_LOBE_IDS (skip "til" etc.)

    Writes data/metabolism/fitness/<lobe_id>.json and returns list of
    written paths.

    Per-lobe failures isolate (continue loop).
    NEVER raises.
    """
    r = _repo_root(root)
    written: list[str] = []

    try:
        charters = _load_charters(r)
        if not charters:
            log.info("generic_fitness: no charters loaded — nothing to build")
            return written

        fitness_dir = r / "data" / "metabolism" / "fitness"

        for lobe_id, charter in charters.items():
            try:
                # Skip bespoke builders
                if lobe_id in _BESPOKE_LOBE_IDS:
                    log.debug("generic_fitness: skipping bespoke lobe %r", lobe_id)
                    continue

                # Only loop-managed lifecycle states
                lc_state = charter.get("lifecycle_state") or ""
                if lc_state not in _LOOP_MANAGED_STATES:
                    continue

                # Only structured sensors (dicts with id+store)
                sensors_cfg = charter.get("fitness_sensors") or []
                if not _has_structured_sensors(sensors_cfg):
                    log.debug(
                        "generic_fitness: skipping %r — no structured sensors", lobe_id
                    )
                    continue

                # Build and write card
                card = _build_card(lobe_id, charter, r)

                fitness_dir.mkdir(parents=True, exist_ok=True)
                out_path = fitness_dir / f"{lobe_id}.json"
                out_path.write_text(
                    json.dumps(card, indent=2, ensure_ascii=False), encoding="utf-8"
                )
                written.append(str(out_path))
                log.info("generic_fitness: wrote %s (maturity=%s)", out_path, card.get("maturity"))

            except Exception as exc:  # noqa: BLE001
                log.warning("generic_fitness: lobe %r failed: %s", lobe_id, exc)
                # Per-lobe failures isolate — continue

    except Exception as exc:  # noqa: BLE001
        log.warning("generic_fitness.build_generic_fitness_cards: outer error: %s", exc)

    return written
