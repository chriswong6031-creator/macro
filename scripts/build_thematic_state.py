"""scripts/build_thematic_state.py — TIL W0 Thematic State builder.

Mirrors scripts/build_mechanism_pathways.py conventions.

Writes:
    data/neuralweb/theme_state.json          (primary; git-committed)
    site/neuralwebdata/theme_state.json      (site mirror)
    data/neuralweb/theme_phase_history.jsonl (append-only PIT tape; nightly sole advancer)

Display/context tier only. Authority block: is_context_only=True, all promotion flags False.
Fail-open: missing source → stale_legs entry + null block; always exits 0.
Composition is adapter-cheap (reads existing committed artifacts only — no network calls).

Runs AFTER build_foresight and build_baskets steps in the engine lane.

Usage:
    python -m scripts.build_thematic_state [--root /path/to/repo]
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
import tempfile
import time
from pathlib import Path

_HERE = Path(__file__).resolve().parent
_REPO_ROOT = _HERE.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from engine.neuralweb.thematic_state import compose, append_phase_history
from engine.neuralweb.envelope import stamp

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
log = logging.getLogger("build_thematic_state")

_ARTIFACT_ID = "theme-state"
_DATA_PATH = "data/neuralweb/theme_state.json"
_SITE_PATH = "site/neuralwebdata/theme_state.json"
_HISTORY_PATH = "data/neuralweb/theme_phase_history.jsonl"


def _atomic_write_json(path: Path, payload: dict) -> None:
    """Write JSON atomically via temp-file + rename."""
    path.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(payload, ensure_ascii=False, indent=2, default=str)
    with tempfile.NamedTemporaryFile(
        mode="w",
        encoding="utf-8",
        dir=path.parent,
        prefix=f".tmp_{path.name}_",
        suffix=".json",
        delete=False,
    ) as tf:
        tf.write(text)
        tmp_path = Path(tf.name)
    tmp_path.replace(path)


def build(root: Path) -> int:
    """Build thematic state artifacts.  Returns exit code (always 0)."""
    t0 = time.perf_counter()

    # ── Compose ───────────────────────────────────────────────────────────
    try:
        artifact = compose(root=root)
    except Exception as exc:  # noqa: BLE001
        log.error("compose() failed unexpectedly: %s", exc)
        # Minimal null artifact — keeps the file present and parseable
        from datetime import datetime, timezone
        artifact = {
            "schema": "neuralweb.theme_state.v1",
            "as_of": datetime.now(tz=timezone.utc).strftime("%Y-%m-%d"),
            "generated_at": datetime.now(tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "authority": {
                "is_context_only": True, "may_rank": False, "may_gate": False,
                "may_size": False, "may_escalate": False,
            },
            "themes": [],
            "stale_legs": [f"compose exception: {exc}"],
        }

    elapsed_compose = time.perf_counter() - t0
    n_themes = len(artifact.get("themes", []))
    n_stale = len(artifact.get("stale_legs", []))
    log.info("compose done in %.2fs — %d themes, %d stale_legs", elapsed_compose, n_themes, n_stale)
    print(f"[thematic_state] compose {elapsed_compose:.2f}s — themes={n_themes} stale_legs={n_stale}", flush=True)

    # ── Stamp with envelope ───────────────────────────────────────────────
    try:
        artifact = stamp(artifact, artifact_id=_ARTIFACT_ID)
    except Exception as exc:  # noqa: BLE001
        log.warning("envelope stamp failed (non-fatal): %s", exc)

    # ── Write data artifact (atomic) ──────────────────────────────────────
    data_path = root / _DATA_PATH
    try:
        _atomic_write_json(data_path, artifact)
        log.info("wrote %s", data_path)
    except Exception as exc:  # noqa: BLE001
        log.error("data write failed: %s", exc)

    # ── Write site mirror (atomic) ─────────────────────────────────────────
    site_path = root / _SITE_PATH
    try:
        _atomic_write_json(site_path, artifact)
        log.info("wrote %s", site_path)
    except Exception as exc:  # noqa: BLE001
        log.error("site write failed: %s", exc)

    # ── Append PIT tape ───────────────────────────────────────────────────
    try:
        n_rows = append_phase_history(root, artifact)
        log.info("phase_history +%d rows", n_rows)
        print(f"[thematic_state] phase_history +{n_rows} rows", flush=True)
    except Exception as exc:  # noqa: BLE001
        log.warning("phase_history append failed (non-fatal): %s", exc)

    total = time.perf_counter() - t0
    print(f"[thematic_state] total {total:.2f}s", flush=True)
    return 0


def main() -> None:
    parser = argparse.ArgumentParser(description="Build thematic state artifacts (TIL W0)")
    parser.add_argument(
        "--root", default=None,
        help="Repo root path (default: inferred from script location)",
    )
    args = parser.parse_args()
    root = Path(args.root).resolve() if args.root else _REPO_ROOT
    code = build(root)
    sys.exit(code)


if __name__ == "__main__":
    main()
