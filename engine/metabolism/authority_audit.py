"""engine.metabolism.authority_audit — Quarterly authority audit (V2-C, R-V2-3 §6.2).

Scans the synapse registry for the "promotion-launder gap": display-tier lobes
whose outputs are read by scored/authority consumers.  The tier fence in
lifecycle.py catches structural tier-raises, but a display lobe that feeds a
scored consumer via its consumers list is a launder the fence cannot see.

This is a DISPLAY-TIER, READ-ONLY report.  It does NOT take action.
Output: data/metabolism/authority_audit/<quarter>.json.

Design:
  - Reads synapse.yml (artifacts dict).
  - For every artifact A whose tier is in {confirmer, scored}:
      for every artifact B that A's consumers list mentions:
          if B's tier is in {display, shadow} → flag as potential launder.
  - Also scans scored_path_surfaces: any display lobe that appears in a
    scored artifact's scored_path_surfaces is flagged.
  - Surfaced in the operator digest (V2-D tap card).

NEVER-RAISE CONTRACT: all functions return safe defaults on any error.
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

log = logging.getLogger(__name__)

SCHEMA = "metabolism.authority_audit.v1"
OUTPUT_DIR = ("data", "metabolism", "authority_audit")

# Tiers that represent authority / scored consumers
_SCORED_TIERS = frozenset({"confirmer", "scored"})

# Tiers that are display-level (should not feed scored consumers)
_DISPLAY_TIERS = frozenset({"display", "shadow"})


def _resolve_root(root: str | Path | None) -> Path:
    if root is not None:
        return Path(root)
    return Path(__file__).resolve().parent.parent.parent


def _load_yaml(path: Path) -> dict | None:
    """Load a YAML file; return None on any error (NEVER-RAISE)."""
    try:
        import yaml  # noqa: PLC0415
        return yaml.safe_load(path.read_text(encoding="utf-8"))
    except Exception as exc:  # noqa: BLE001
        log.warning("authority_audit: failed to load %s: %s", path, exc)
        return None


def _quarter(ts: str) -> str:
    """Convert ISO timestamp to quarter string like '2026Q3'."""
    try:
        dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
        q = (dt.month - 1) // 3 + 1
        return f"{dt.year}Q{q}"
    except Exception:  # noqa: BLE001
        return "unknown"


def run_audit(root: str | Path | None = None) -> dict[str, Any]:
    """Run the quarterly authority audit and return the report dict.

    The report lists:
      - display_to_scored_consumers: display lobes whose outputs appear in
        the consumers list of a scored/confirmer artifact.
      - scored_path_surface_launders: display lobes that appear in a
        scored artifact's scored_path_surfaces list.

    Returns the report dict (display-tier, no action).  NEVER raises.
    """
    result: dict[str, Any] = {
        "schema": SCHEMA,
        "ts": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "ok": False,
        "errors": [],
        "display_to_scored_consumers": [],
        "scored_path_surface_launders": [],
        "summary": {},
        "authority": {
            "is_context_only": True,
            "display_only": True,
            "not_a_signal": True,
            "note": (
                "Quarterly authority audit — display-tier report only. "
                "No action taken. Surfaced in operator digest for human review."
            ),
        },
    }
    try:
        r = _resolve_root(root)
        synapse_raw = _load_yaml(r / "config" / "synapse.yml")
        if synapse_raw is None:
            result["errors"].append("config/synapse.yml missing or unreadable")
            return result

        artifacts = synapse_raw.get("artifacts") or {}

        # Build a map: artifact_id → tier
        tier_map: dict[str, str] = {
            art_id: art.get("tier", "display")
            for art_id, art in artifacts.items()
        }

        # Build a map: path → artifact_id (for consumer-path resolution)
        path_to_id: dict[str, str] = {
            art.get("path", ""): art_id
            for art_id, art in artifacts.items()
            if art.get("path")
        }

        launders_consumer: list[dict] = []
        launders_surface: list[dict] = []

        for art_id, art in artifacts.items():
            art_tier = art.get("tier", "display")
            if art_tier not in _SCORED_TIERS:
                continue

            # Check consumers list for display-tier artifacts
            consumers = art.get("consumers") or []
            external_consumers = art.get("external_consumers") or []
            all_consumers = list(consumers) + [str(c) for c in external_consumers]
            for consumer_ref in all_consumers:
                consumer_ref_str = str(consumer_ref)
                # consumer_ref may be a file path like 'engine/foo.py' or artifact id
                # Check if any display artifact's path matches
                for b_id, b_art in artifacts.items():
                    b_tier = b_art.get("tier", "display")
                    if b_tier not in _DISPLAY_TIERS:
                        continue
                    b_path = b_art.get("path", "")
                    if b_path and b_path in consumer_ref_str:
                        launders_consumer.append({
                            "scored_artifact": art_id,
                            "scored_tier": art_tier,
                            "display_artifact": b_id,
                            "display_tier": b_tier,
                            "via": "consumers_list",
                            "consumer_ref": consumer_ref_str,
                        })

            # Check scored_path_surfaces for display lobe paths
            sps = art.get("scored_path_surfaces") or []
            for surface in sps:
                surface_str = str(surface)
                # See if any display artifact path appears in this surface
                for b_id, b_art in artifacts.items():
                    b_tier = b_art.get("tier", "display")
                    if b_tier not in _DISPLAY_TIERS:
                        continue
                    b_path = b_art.get("path", "")
                    if b_path and b_path in surface_str:
                        launders_surface.append({
                            "scored_artifact": art_id,
                            "scored_tier": art_tier,
                            "display_artifact": b_id,
                            "display_tier": b_tier,
                            "via": "scored_path_surfaces",
                            "surface": surface_str,
                        })

        result["display_to_scored_consumers"] = launders_consumer
        result["scored_path_surface_launders"] = launders_surface
        result["summary"] = {
            "total_artifacts": len(artifacts),
            "scored_artifacts": sum(1 for t in tier_map.values() if t in _SCORED_TIERS),
            "display_artifacts": sum(1 for t in tier_map.values() if t in _DISPLAY_TIERS),
            "potential_launders_via_consumers": len(launders_consumer),
            "potential_launders_via_surfaces": len(launders_surface),
        }
        result["ok"] = True

    except Exception as exc:  # noqa: BLE001
        log.warning("authority_audit.run_audit: unexpected error: %s", exc)
        result["errors"].append(f"unexpected error: {exc}")

    return result


def write_audit(
    report: dict[str, Any],
    root: str | Path | None = None,
    quarter: str | None = None,
) -> Path | None:
    """Write the audit report to data/metabolism/authority_audit/<quarter>.json.

    Returns the path written, or None on error.  NEVER raises.
    """
    try:
        r = _resolve_root(root)
        q = quarter or _quarter(report.get("ts", ""))
        out_dir = r.joinpath(*OUTPUT_DIR)
        out_dir.mkdir(parents=True, exist_ok=True)
        out_path = out_dir / f"{q}.json"
        tmp = out_path.with_suffix(".tmp")
        tmp.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
        tmp.replace(out_path)
        return out_path
    except Exception as exc:  # noqa: BLE001
        log.warning("authority_audit.write_audit: %s", exc)
        return None


def run_and_write(root: str | Path | None = None) -> dict[str, Any]:
    """Run the audit and write the output file.

    Returns the report dict with an additional 'output_path' key.
    NEVER raises.
    """
    report = run_audit(root)
    path = write_audit(report, root)
    report["output_path"] = str(path) if path else None
    return report
