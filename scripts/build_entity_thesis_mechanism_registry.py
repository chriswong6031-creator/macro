"""scripts/build_entity_thesis_mechanism_registry — CLI for ETM crosswalk.

Builds data/neuralweb/entity_thesis_mechanism_registry.json from existing
local artifacts:
  - data/species/registry.json
  - data/research_factory/candidates.jsonl + transitions.jsonl
  - data/trial_ledger.jsonl
  - data/neuralweb/governance.jsonl
  - data/governance/claim_accountability.json
  - site/factordata/reflexivity_overlay.json
  - data/research/thesis_funnel_states.parquet
  - data/experiments/registry_seed.json
  - config/entity_thesis_mechanism_registry.yml

HARD LAWS (encoded in engine module ETM-R1..R8):
    Display-only crosswalk.  No authority to gate, rank, score, size, originate,
    or promote.  Every link carries source provenance.  No invented links.

Usage:
    python -m scripts.build_entity_thesis_mechanism_registry
    python -m scripts.build_entity_thesis_mechanism_registry --root /path/to/repo
    python -m scripts.build_entity_thesis_mechanism_registry --check-only
    python -m scripts.build_entity_thesis_mechanism_registry --query "washout"

Exit codes:
    0 — success
    1 — hard failure (write error or unexpected exception)
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from engine.neuralweb.entity_thesis_mechanism_registry import (  # noqa: E402
    build,
    build_and_write,
    lookup,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    stream=sys.stderr,
)
log = logging.getLogger("build_entity_thesis_mechanism_registry")


def _summary_line(artifact: dict) -> str:
    counts = artifact.get("counts", {})
    rbt = counts.get("rows_by_type", {})
    ebk = counts.get("edges_by_kind", {})
    n_conflicts = len(artifact.get("conflicts", []))
    n_dups = len(artifact.get("possible_duplicates", []))
    n_families = len(artifact.get("trial_families", {}))
    return (
        f"entity_thesis_mechanism_registry OK — "
        f"rows_by_type={rbt} "
        f"edges_by_kind={ebk} "
        f"trial_families={n_families} "
        f"conflicts={n_conflicts} "
        f"possible_duplicates={n_dups} "
        f"as_of={artifact.get('as_of', '?')}"
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Build data/neuralweb/entity_thesis_mechanism_registry.json — "
            "Entity/Thesis/Mechanism crosswalk (display-only)."
        )
    )
    parser.add_argument(
        "--root",
        type=Path,
        default=None,
        help="Repo root (default: auto-detected from script location).",
    )
    parser.add_argument(
        "--check-only",
        action="store_true",
        help="Build in-memory, print counts, write nothing.",
    )
    parser.add_argument(
        "--query",
        type=str,
        default=None,
        help="Tokenized lookup query; build artifact first if needed, then pretty-print result.",
    )
    args = parser.parse_args(argv)

    try:
        if args.query:
            # Build in-memory (or load committed artifact if present and no --check-only)
            root = args.root
            if root is None:
                root = Path(__file__).resolve().parent.parent
            artifact_path = root / "data" / "neuralweb" / "entity_thesis_mechanism_registry.json"
            if artifact_path.exists():
                artifact = json.loads(artifact_path.read_text(encoding="utf-8"))
            else:
                artifact = build(root=root)
            result = lookup(artifact, args.query)
            print(json.dumps(result, indent=2, ensure_ascii=False), flush=True)
            return 0

        if args.check_only:
            artifact = build(root=args.root)
            print(_summary_line(artifact), flush=True)
            return 0

        artifact = build_and_write(root=args.root)
        # build_and_write returns a Path; reload to get the dict for summary
        artifact_dict = json.loads(artifact.read_text(encoding="utf-8"))
        print(_summary_line(artifact_dict), flush=True)
        print(f"written: {artifact}", flush=True)
        return 0

    except OSError as exc:
        log.error("entity_thesis_mechanism_registry: FAILED to write artifact — %s", exc)
        return 1
    except Exception as exc:  # noqa: BLE001
        log.error("entity_thesis_mechanism_registry: unexpected error — %s", exc)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
