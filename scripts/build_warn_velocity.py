"""scripts/build_warn_velocity.py — Nightly WARN Act velocity build (collect lane).

Off the render critical path.  Produces:
    data/warn/theme_warn_velocity.json

This script is a COLLECT-LANE job: it runs alongside (or just after) the
theme_activity / radar compute step, but writes to data/ not site/.  The radar
consumer (engine/radar.py) reads theme_warn.compute_warn_activity() at build
time; this script is the CLI to do the same write for persistence / auditing.

Do NOT add this to scripts/collect.py (still in accrual phase; per the
warn_notices.py WIRING NOTE pattern).  Invoke standalone:
    python -m scripts.build_warn_velocity

The output carries the engine.neuralweb.envelope sidecar for provenance.

Exit 0 always (tolerant; absent store -> honest null JSON written).
"""
from __future__ import annotations

import json
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from engine.theme_warn import compute_warn_activity  # noqa: E402
from lib import config  # noqa: E402

log = logging.getLogger(__name__)

_OUT = ROOT / "data" / "warn" / "theme_warn_velocity.json"

_AUTHORITY = {
    "may_rank": False,
    "may_gate": False,
    "may_size": False,
    "may_escalate": False,
    "is_context_only": True,
}


def build(baskets_payload: dict | None = None, write: bool = True) -> dict:
    """Build the WARN velocity artifact and (optionally) write to disk."""
    # Load baskets payload from site if not injected
    if baskets_payload is None:
        try:
            site = config.ROOT / config.load()["storage"]["site_dir"]
            bp = site / "basketdata" / "baskets.json"
            if bp.exists():
                raw = json.loads(bp.read_text())
                baskets_payload = raw if "baskets" in raw else None
        except Exception as exc:  # noqa: BLE001
            log.warning("baskets.json load failed: %s", exc)

    if not baskets_payload:
        log.warning("build_warn_velocity: no baskets payload — writing empty artifact")
        baskets_payload = {"baskets": []}

    result = compute_warn_activity(baskets_payload)

    artifact = {
        "schema": "warn_velocity.v1",
        "is_context_only": True,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "authority": _AUTHORITY,
        "baskets": result,
    }

    if write:
        out = _OUT
        out.parent.mkdir(parents=True, exist_ok=True)
        tmp = out.with_suffix(".tmp.json")
        tmp.write_text(json.dumps(artifact, default=str), encoding="utf-8")
        tmp.rename(out)
        log.info("build_warn_velocity: wrote %s (%d baskets)", out, len(result))

        # Write sidecar for provenance
        try:
            from engine.neuralweb.envelope import write_sidecar
            from engine.neuralweb.synapse import load_registry
            try:
                # Only write sidecar if artifact is registered in synapse.yml
                reg = load_registry()
                if "warn-velocity" in reg.get("artifacts", {}):
                    write_sidecar(out, artifact_id="warn-velocity")
            except KeyError:
                pass  # Not registered yet — skip sidecar (avoid import error)
        except Exception as exc:  # noqa: BLE001
            log.debug("sidecar write skipped: %s", exc)

    n_matched = sum(
        1 for v in result.values()
        if v.get("n_matched", 0) > 0
    )
    log.info("build_warn_velocity: %d/%d baskets with WARN matches", n_matched, len(result))
    return artifact


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    try:
        build()
    except Exception as exc:  # noqa: BLE001
        log.error("build_warn_velocity failed: %s", exc)
    return 0  # always exit 0


if __name__ == "__main__":
    raise SystemExit(main())
