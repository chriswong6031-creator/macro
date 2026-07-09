"""CLI wrapper: build the deterministic operator-attention artifact.

Usage
-----
    python -m scripts.build_attention_deterministic [--root REPO_ROOT]

Reads
-----
- data/neuralweb/world_state.json
- data/neuralweb/health.json
- data/neuralweb/daily_brief.json
- data/neuralweb/confluence_graph.json  (optional)

Writes
------
- data/neuralweb/attention_deterministic.json   (primary artifact)
- site/neuralwebdata/attention_deterministic.json  (site mirror)

Envelope-stamped via engine.neuralweb.envelope.stamp().
Registered in config/synapse.yml as 'attention-deterministic'.

Exit codes
----------
0 — artifact written successfully.
0 — any input missing → fail-open: writes empty-items artifact + exits 0 with warning.
1 — total failure to write the artifact.

Designed to be called as:
    python -m scripts.build_attention_deterministic || echo "::warning::non-fatal"
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from engine.neuralweb.attention_deterministic import build  # noqa: E402
from engine.neuralweb.envelope import stamp  # noqa: E402

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    stream=sys.stderr,
)
log = logging.getLogger("build_attention_deterministic")


def _repo_root(given: Path | None) -> Path:
    if given is not None:
        return given.resolve()
    return Path(__file__).resolve().parent.parent


def _load_json(path: Path, label: str) -> dict | None:
    """Load a JSON file, returning None on error (fail-open)."""
    if not path.exists():
        log.warning("build_attention_deterministic: %s not found at %s — skipping", label, path)
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:  # noqa: BLE001
        log.warning("build_attention_deterministic: failed to load %s (%s) — skipping", label, exc)
        return None


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Build data/neuralweb/attention_deterministic.json — deterministic attention items."
    )
    parser.add_argument(
        "--root",
        type=Path,
        default=None,
        help="Repo root (default: auto-detected from script location).",
    )
    args = parser.parse_args(argv)
    root = _repo_root(args.root)

    nw_data = root / "data" / "neuralweb"
    nw_site = root / "site" / "neuralwebdata"

    # Load inputs — all fail-open
    world_state = _load_json(nw_data / "world_state.json", "world_state") or {}
    health = _load_json(nw_data / "health.json", "health") or {}
    daily_brief = _load_json(nw_data / "daily_brief.json", "daily_brief") or {}
    confluence_graph = _load_json(nw_data / "confluence_graph.json", "confluence_graph")

    try:
        payload = build(
            world_state=world_state,
            health=health,
            daily_brief=daily_brief,
            confluence_graph=confluence_graph,
        )
    except Exception as exc:  # noqa: BLE001
        log.error("build_attention_deterministic: build() raised unexpectedly: %s", exc)
        # Fail-open: write an empty-items artifact so consumers always get a valid JSON
        payload = {
            "as_of": "",
            "item_count": 0,
            "counts_by_severity": {},
            "items": [],
            "caveats": ["build failed — empty placeholder"],
        }

    try:
        stamped = stamp(payload, artifact_id="attention-deterministic")
    except Exception as exc:  # noqa: BLE001
        log.error("build_attention_deterministic: stamp() failed: %s", exc)
        return 1

    out_text = json.dumps(stamped, indent=2, ensure_ascii=False) + "\n"

    # Write data/ artifact
    try:
        nw_data.mkdir(parents=True, exist_ok=True)
        data_path = nw_data / "attention_deterministic.json"
        data_path.write_text(out_text, encoding="utf-8")
        log.info("build_attention_deterministic: wrote %s (%d items)", data_path, stamped.get("item_count", 0))
    except Exception as exc:  # noqa: BLE001
        log.error("build_attention_deterministic: failed to write data artifact: %s", exc)
        return 1

    # Write site/ mirror (non-fatal)
    try:
        nw_site.mkdir(parents=True, exist_ok=True)
        site_path = nw_site / "attention_deterministic.json"
        site_path.write_text(out_text, encoding="utf-8")
        log.info("build_attention_deterministic: wrote site mirror %s", site_path)
    except Exception as exc:  # noqa: BLE001
        log.warning("build_attention_deterministic: site mirror write failed (non-fatal): %s", exc)

    return 0


if __name__ == "__main__":
    sys.exit(main())
