"""engine.neuralweb.marketing_governor — Marketing NW lobe governor.

Produces TWO committed artifacts (single writer, never-raise):

  A. data/neuralweb/marketing_state.json   (schema marketing.state/v1)
  B. site/neuralwebdata/marketing_lobe.json (schema marketing.lobe/v1, public-safe)

Never-raise contract: all exceptions are caught; best-effort written.

Entry point:
    build_and_write(root=None) -> {"state_path": ..., "lobe_path": ...}

Run as module: python -m engine.neuralweb.marketing_governor
"""
from __future__ import annotations

import json
import logging
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

log = logging.getLogger(__name__)

# Artifact ids (must match config/synapse.yml entries)
_ARTIFACT_STATE = "marketing-state"
_ARTIFACT_LOBE = "marketing-lobe"

# Paths relative to repo root
_STATE_PATH = Path("data") / "neuralweb" / "marketing_state.json"
_LOBE_PATH = Path("site") / "neuralwebdata" / "marketing_lobe.json"


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def _repo_root(root: Path | str | None = None) -> Path:
    if root is not None:
        return Path(root)
    return Path(__file__).resolve().parent.parent.parent


def _write_json_atomic(path: Path, obj: dict) -> None:
    """Atomic write via temp file in the same directory."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_fd, tmp_path = tempfile.mkstemp(
        dir=path.parent, prefix=".tmp_", suffix=".json"
    )
    try:
        with os.fdopen(tmp_fd, "w", encoding="utf-8") as f:
            json.dump(obj, f, indent=2, ensure_ascii=False)
            f.write("\n")
        os.replace(tmp_path, path)
    except Exception:
        try:
            os.unlink(tmp_path)
        except Exception:  # noqa: BLE001
            pass
        raise


def _public_safe_subset(state: dict) -> dict:
    """Extract the public-safe subset for marketing_lobe.json (spec §4).

    Included: schema, as_of, lobe (id/name/lifecycle_state/mandate),
              north_star (state only, no dollar value),
              departments (id/name/lifecycle_state/wave only),
              waves (id/title/status), channels_priority.

    Excluded: budgets, internal scorecards, desk-account handles, credentials.
    """
    return {
        "schema": "marketing.lobe/v1",
        "as_of": state.get("as_of", ""),
        "lobe": {
            "id": state.get("lobe", {}).get("id", "marketing"),
            "name": state.get("lobe", {}).get("name", "Marketing"),
            "lifecycle_state": state.get("lobe", {}).get("lifecycle_state", "chartered"),
            "mandate": state.get("lobe", {}).get("mandate", {}),
        },
        "north_star": {
            "state": state.get("north_star", {}).get("state", "accruing"),
        },
        "departments": [
            {
                "id": d.get("id", ""),
                "name": d.get("name", ""),
                "lifecycle_state": d.get("lifecycle_state", "chartered"),
                "wave": d.get("wave", 0),
            }
            for d in state.get("departments", [])
        ],
        "waves": [
            {
                "id": w.get("id", ""),
                "title": w.get("title", ""),
                "status": w.get("status", "planned"),
            }
            for w in state.get("waves", [])
        ],
        "channels_priority": state.get("channels_priority", {}),
    }


# ─────────────────────────────────────────────────────────────────────────────
# Governor
# ─────────────────────────────────────────────────────────────────────────────

def build_and_write(root: Path | str | None = None) -> dict[str, Any]:
    """Build marketing state and write both artifacts.

    Returns {"state_path": str, "lobe_path": str} on success.
    Never raises — returns {"state_path": None, "lobe_path": None, "error": ...}
    on failure.
    """
    result: dict[str, Any] = {"state_path": None, "lobe_path": None}
    try:
        r = _repo_root(root)

        # Build state
        from engine.marketing.state import build_state
        state = build_state(root=r)

        # Stamp with envelope
        try:
            from engine.neuralweb.envelope import stamp
            state = stamp(state, artifact_id=_ARTIFACT_STATE)
        except Exception as exc:  # noqa: BLE001
            log.warning("marketing_governor: envelope stamp failed: %s", exc)
            # Add minimal envelope keys manually so artifact is still valid
            now_str = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
            state.setdefault("schema_version", 1)
            state.setdefault("produced_by", "engine/neuralweb/marketing_governor.py")
            state.setdefault("produced_at", now_str)
            state.setdefault("inputs_hash", "sha256:unstamped")
            state.setdefault("tier", "display")

        # Write state artifact
        state_path = r / _STATE_PATH
        _write_json_atomic(state_path, state)
        result["state_path"] = str(state_path)
        log.info("marketing_governor: wrote %s", state_path)

        # Build public-safe subset
        lobe = _public_safe_subset(state)

        # Stamp lobe artifact
        try:
            from engine.neuralweb.envelope import stamp
            lobe = stamp(lobe, artifact_id=_ARTIFACT_LOBE)
        except Exception as exc:  # noqa: BLE001
            log.warning("marketing_governor: lobe stamp failed: %s", exc)
            now_str = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
            lobe.setdefault("schema_version", 1)
            lobe.setdefault("produced_by", "engine/neuralweb/marketing_governor.py")
            lobe.setdefault("produced_at", now_str)
            lobe.setdefault("inputs_hash", "sha256:unstamped")
            lobe.setdefault("tier", "display")

        # Write lobe artifact
        lobe_path = r / _LOBE_PATH
        _write_json_atomic(lobe_path, lobe)
        result["lobe_path"] = str(lobe_path)
        log.info("marketing_governor: wrote %s", lobe_path)

    except Exception as exc:  # noqa: BLE001
        log.warning("marketing_governor: build_and_write failed: %s", exc, exc_info=True)
        result["error"] = str(exc)

    return result


# ─────────────────────────────────────────────────────────────────────────────
# Module entry point
# ─────────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import sys
    logging.basicConfig(
        level=logging.INFO,
        format="%(levelname)s %(name)s %(message)s",
        stream=sys.stderr,
    )
    res = build_and_write()
    if res.get("error"):
        print(f"marketing_governor: ERROR — {res['error']}", file=sys.stderr)
        sys.exit(1)
    print(
        f"marketing_governor: ok — "
        f"state={res.get('state_path')} "
        f"lobe={res.get('lobe_path')}"
    )
