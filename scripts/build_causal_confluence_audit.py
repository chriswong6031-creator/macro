"""Build causal confluence audit artifact (CHF-R10, W6).

Nightly step: reads committed artifacts only, applies deterministic rules,
writes data/neuralweb/causal_confluence_audit.json.

Non-fatal pattern (exits 0 on any error, logs a warning).

Usage:
    python -m scripts.build_causal_confluence_audit
    python scripts/build_causal_confluence_audit.py

Synapse artifact: causal-confluence-audit
Schema: neuralweb.causal_confluence_audit.v1
Consumers declared:
  - engine/neuralweb/confluence.py (stamp_confluence_edges)
  - admin/causal_lab.py (audit counts in panel)
"""
from __future__ import annotations

import json
import logging
import sys
from pathlib import Path

# Allow running as script or module
_SCRIPT_DIR = Path(__file__).resolve().parent
_REPO_ROOT = _SCRIPT_DIR.parent
sys.path.insert(0, str(_REPO_ROOT))

from engine.neuralweb.causal_audit import build_audit  # noqa: E402

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s — %(message)s",
)
log = logging.getLogger("build_causal_confluence_audit")

_OUT_PATH = _REPO_ROOT / "data" / "neuralweb" / "causal_confluence_audit.json"


def main() -> int:
    """Build and write the audit artifact.  Returns 0 always (non-fatal)."""
    try:
        log.info("build_causal_confluence_audit: starting audit build")
        artifact = build_audit(root=_REPO_ROOT)

        counts = artifact.get("counts") or {}
        gap_notes = artifact.get("gap_notes") or []
        log.info(
            "audit: duplicate_exposure=%d  shared_parent_suspect=%d  collider_risk=%d  total=%d",
            counts.get("duplicate_exposure", 0),
            counts.get("shared_parent_suspect", 0),
            counts.get("collider_risk", 0),
            counts.get("total", 0),
        )
        if gap_notes:
            for note in gap_notes:
                log.warning("gap: %s", note)

        _OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
        _OUT_PATH.write_text(
            json.dumps(artifact, indent=2, ensure_ascii=False, default=str),
            encoding="utf-8",
        )
        log.info("build_causal_confluence_audit: wrote %s", _OUT_PATH)
        return 0

    except Exception as exc:  # noqa: BLE001
        log.warning(
            "build_causal_confluence_audit: unhandled error (non-fatal) — %s", exc
        )
        return 0


if __name__ == "__main__":
    sys.exit(main())
