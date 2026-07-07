"""Build the Mechanism Pathway Compiler v1 artifact.

W1, feat/nw-mechanism-pathways.  Writes:
  - data/neuralweb/mechanism_pathways.json
  - data/neuralweb/mechanism_pathways_history.jsonl  (append-only, keep-first per as_of)
  - site/neuralwebdata/mechanism_pathways.json

All three paths are git-tracked.  Nightly engine job is the sole advancer
of the data/ writes; intraday lanes discard data/ writes per house law.

Trigger precedence and stale-trigger guard implemented in
engine/neuralweb/mechanism_pathways.py per RUL-CC-11..13.

Usage:
    python -m scripts.build_mechanism_pathways [--root /path/to/repo]
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
import time
from pathlib import Path

_HERE = Path(__file__).resolve().parent
_REPO_ROOT = _HERE.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from engine.neuralweb.mechanism_pathways import compile as compile_pathways  # noqa: A004

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
log = logging.getLogger("build_mechanism_pathways")

_DATA_PATH = "data/neuralweb/mechanism_pathways.json"
_HISTORY_PATH = "data/neuralweb/mechanism_pathways_history.jsonl"
_SITE_PATH = "site/neuralwebdata/mechanism_pathways.json"


def _append_history(history_path: Path, artifact: dict) -> int:
    """Append artifact as one JSONL line; keep-first per as_of.  Returns rows appended."""
    as_of = artifact.get("as_of", "")
    history_path.parent.mkdir(parents=True, exist_ok=True)

    existing_lines: list[str] = []
    if history_path.exists():
        existing_lines = history_path.read_text(encoding="utf-8").splitlines()

    # Check if this as_of already present
    for line in existing_lines:
        try:
            rec = json.loads(line)
            if rec.get("as_of") == as_of:
                log.info("history: as_of=%s already present — skipping (keep-first)", as_of)
                return 0
        except Exception:  # noqa: BLE001
            pass

    # Compact history row — exclude bulky nodes/edges lists
    compact = {
        "as_of": artifact.get("as_of"),
        "schema": artifact.get("schema"),
        "pathways_count": len(artifact.get("pathways", [])),
        "primary_family": None,
        "no_pathway_reason": None,
    }
    paths = artifact.get("pathways", [])
    if paths:
        compact["primary_family"] = paths[0].get("family")
    np_rec = artifact.get("no_pathway")
    if np_rec:
        compact["no_pathway_reason"] = np_rec.get("reason")

    new_line = json.dumps(compact, ensure_ascii=False, separators=(",", ":"))
    with history_path.open("a", encoding="utf-8") as f:
        f.write(new_line + "\n")
    return 1


def build(root: Path) -> int:
    """Build mechanism pathways artifacts.  Returns exit code (0=ok, 1=error)."""
    t0 = time.perf_counter()

    artifact = compile_pathways(root=root)

    elapsed = time.perf_counter() - t0
    as_of = artifact.get("as_of", "")
    paths_count = len(artifact.get("pathways", []))
    no_pathway = artifact.get("no_pathway")

    log.info(
        "compile done in %.2fs — as_of=%s pathways=%d no_pathway=%s",
        elapsed, as_of, paths_count,
        no_pathway.get("reason") if no_pathway else None,
    )
    print(
        f"[mechanism_pathways] {elapsed:.2f}s — as_of={as_of} "
        f"pathways={paths_count} "
        f"no_pathway={no_pathway.get('reason') if no_pathway else None}",
        flush=True,
    )

    # ── Write data artifact ──────────────────────────────────────────────
    data_path = root / _DATA_PATH
    data_path.parent.mkdir(parents=True, exist_ok=True)
    data_path.write_text(
        json.dumps(artifact, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    log.info("wrote %s", data_path)

    # ── Append history ───────────────────────────────────────────────────
    history_path = root / _HISTORY_PATH
    try:
        appended = _append_history(history_path, artifact)
        log.info("history: +%d rows @ %s", appended, as_of)
        print(f"[mechanism_pathways history] +{appended} rows @ {as_of}", flush=True)
    except Exception as exc:  # noqa: BLE001
        log.warning("history append failed (non-fatal): %s", exc)

    # ── Write site mirror ────────────────────────────────────────────────
    site_path = root / _SITE_PATH
    site_path.parent.mkdir(parents=True, exist_ok=True)
    site_path.write_text(
        json.dumps(artifact, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    log.info("wrote %s", site_path)

    total = time.perf_counter() - t0
    print(f"[mechanism_pathways total] {total:.2f}s including I/O", flush=True)
    return 0


def main() -> None:
    parser = argparse.ArgumentParser(description="Build mechanism_pathways artifacts")
    parser.add_argument(
        "--root", default=None,
        help="Repo root path (default: inferred from script location)",
    )
    args = parser.parse_args()

    root = Path(args.root) if args.root else _REPO_ROOT
    code = build(root)
    sys.exit(code)


if __name__ == "__main__":
    main()
