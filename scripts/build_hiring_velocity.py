"""scripts/build_hiring_velocity.py — DOL hiring-intent velocity build (collect lane).

Off the render critical path.  Produces:
    data/dol_certs/hiring_velocity.json    (runner-local; gitignored; provenance artifact)
    site/basketdata/hiring_intent.json     (site projection; git-tracked)

This script is a COLLECT-LANE job: it runs after collect_dol_certs has ingested
at least one quarterly file.  It is cheap once the store exists (pure in-memory
aggregation).  The per-basket velocity computation reads the small normalized
store only — no network calls, no large file downloads on the render path.

Wiring (mirroring build_warn_velocity.py pattern):
  Do NOT add to scripts/collect.py (still in accrual phase).
  Invoke standalone:
      python -m scripts.build_hiring_velocity

  Or after the DOL cert collection step in a collect-lane script.

FENCE: hiring-intent leg is separate from fused_obs_z (per spec LAWS).

Exit 0 always (tolerant; absent store → honest null JSON written).
"""
from __future__ import annotations

import json
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from engine.theme_hiring import compute_hiring_velocity  # noqa: E402
from lib import config  # noqa: E402

log = logging.getLogger(__name__)

_DATA_OUT = ROOT / "data" / "dol_certs" / "hiring_velocity.json"
_SITE_OUT = ROOT / "site" / "basketdata" / "hiring_intent.json"

_AUTHORITY = {
    "may_rank": False,
    "may_gate": False,
    "may_size": False,
    "may_escalate": False,
    "is_context_only": True,
}


def _load_baskets(root: Path) -> dict:
    """Load baskets payload from site/basketdata/baskets.json."""
    try:
        cfg = config.load()
        site = root / cfg.get("storage", {}).get("site_dir", "site")
        bp = site / "basketdata" / "baskets.json"
        if bp.exists():
            raw = json.loads(bp.read_text(encoding="utf-8"))
            return raw if "baskets" in raw else {}
    except Exception as exc:  # noqa: BLE001
        log.warning("baskets.json load failed: %s", exc)
    return {}


def build(baskets_payload: dict | None = None, write: bool = True) -> dict:
    """Build the hiring-intent velocity artifact and (optionally) write to disk."""
    if baskets_payload is None:
        baskets_payload = _load_baskets(ROOT)

    if not baskets_payload:
        log.warning("build_hiring_velocity: no baskets payload — writing empty artifact")
        baskets_payload = {"baskets": []}

    result = compute_hiring_velocity(baskets_payload)

    # Coverage stats (aggregate across baskets)
    n_matched_emp = sum(v.get("n_matched_employers", 0) for v in result.values())
    total_baskets = len(result)
    baskets_with_data = sum(1 for v in result.values() if v.get("cert_count_recent"))

    coverage_stats = {
        "n_matched_employers": n_matched_emp,
        "baskets_with_data": baskets_with_data,
        "total_baskets": total_baskets,
        "match_rate": round(baskets_with_data / total_baskets, 4) if total_baskets > 0 else 0.0,
    }

    as_of = datetime.now(timezone.utc).isoformat()

    # Full data artifact (runner-local)
    data_artifact = {
        "schema": "hiring_velocity.v1",
        "is_context_only": True,
        "generated_at": as_of,
        "authority": _AUTHORITY,
        "coverage_stats": coverage_stats,
        "baskets": result,
    }

    # Compact site projection — per spec: {schema, as_of, authority, per-basket rows, coverage_stats}
    site_rows: list[dict] = []
    for bid, v in result.items():
        site_rows.append({
            "basket_id": bid,
            "cert_velocity_z": v.get("cert_velocity_z"),
            "cert_count_recent": v.get("cert_count_recent"),
            "ai_title_share": v.get("ai_title_share"),
            "median_wage_yoy": v.get("median_wage_yoy"),
            "n_matched_employers": v.get("n_matched_employers", 0),
            "coverage_note": v.get("coverage_note", ""),
            "coverage_note_zh": v.get("coverage_note_zh", ""),
        })

    site_artifact = {
        "schema": "theme_hiring.v1",
        "as_of": as_of,
        "authority": _AUTHORITY,
        "coverage_stats": coverage_stats,
        "baskets": site_rows,
    }

    if write:
        # Write data artifact (runner-local; gitignored)
        _DATA_OUT.parent.mkdir(parents=True, exist_ok=True)
        tmp = _DATA_OUT.with_suffix(".tmp.json")
        tmp.write_text(json.dumps(data_artifact, default=str), encoding="utf-8")
        tmp.rename(_DATA_OUT)
        log.info("build_hiring_velocity: wrote data artifact %s (%d baskets)", _DATA_OUT, len(result))

        # Write site projection
        _SITE_OUT.parent.mkdir(parents=True, exist_ok=True)
        site_tmp = _SITE_OUT.with_suffix(".tmp.json")
        site_tmp.write_text(json.dumps(site_artifact, default=str), encoding="utf-8")
        site_tmp.rename(_SITE_OUT)
        log.info("build_hiring_velocity: wrote site artifact %s", _SITE_OUT)

        # Write sidecar for provenance (mirroring build_warn_velocity.py pattern)
        try:
            from engine.neuralweb.envelope import write_sidecar
            from engine.neuralweb.synapse import load_registry
            try:
                reg = load_registry()
                if "hiring-velocity" in reg.get("artifacts", {}):
                    write_sidecar(_DATA_OUT, artifact_id="hiring-velocity")
            except KeyError:
                pass
        except Exception as exc:  # noqa: BLE001
            log.debug("sidecar write skipped: %s", exc)

    log.info(
        "build_hiring_velocity: %d/%d baskets with hiring-intent data",
        baskets_with_data,
        total_baskets,
    )
    return data_artifact


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    try:
        build()
    except Exception as exc:  # noqa: BLE001
        log.error("build_hiring_velocity failed: %s", exc)
    return 0  # always exit 0


if __name__ == "__main__":
    raise SystemExit(main())
