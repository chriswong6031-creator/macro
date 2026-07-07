"""scripts/build_evidence_clock.py — CLI wrapper for engine.neuralweb.evidence_clock.

Builds the Global Evidence Clock display artifact (EC-R1..R8, display-only).

Writes:
  data/neuralweb/evidence_clock.json    (primary; git-committed; display-only)

The output path sits under already-git-tracked data/neuralweb/ so the engine
job's "git add data/" commit step stages it automatically — no explicit git-add
line in daily.yml is required (RUL-P10 commit-path declaration).

All writes are atomic (tempfile + rename).  Always exits 0 — any single-source
failure produces a row-level `gaps` note in the artifact rather than a crash.
This is a display-only aggregator: it reads source ledgers but never mutates
them.  No LLM in the loop.

Usage:
    python -m scripts.build_evidence_clock [--root PATH]
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
import tempfile
from pathlib import Path

_HERE = Path(__file__).resolve().parent
_REPO_ROOT = _HERE.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

# Declare reads of registered artifacts consumed by this builder.
# Surfaces covered: experiments registry, RF queue+candidates, qledger claims,
# trial ledger, health.json, mastermind context, governance, machine registry,
# rule experiments registry, cycle pattern truths, species registry.
# (check_synapse_reads.py literal-path scan will pick up the path literals
#  declared in engine/neuralweb/evidence_clock.py adapters.)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    stream=sys.stderr,
)
log = logging.getLogger("build_evidence_clock")


def _repo_root(given: Path | None) -> Path:
    if given is not None:
        return given.resolve()
    return _REPO_ROOT


def _atomic_write_json(path: Path, payload: dict) -> None:
    """Write JSON atomically via tempfile + rename."""
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
    log.info("wrote %s (%d rows)", path, len(payload.get("rows", [])))


def build(root: Path) -> int:
    """Run the evidence clock build. Returns exit code (always 0)."""
    from engine.neuralweb.evidence_clock import build as _build  # noqa: PLC0415

    out_path = root / "data" / "neuralweb" / "evidence_clock.json"

    try:
        payload = _build(root)
    except Exception as exc:
        # Last-resort: build returned a fatal exception — construct a minimal gap artifact
        log.error("evidence_clock.build() raised: %s", exc)
        import traceback
        from datetime import date, datetime, timezone
        payload = {
            "schema": "neuralweb.evidence_clock.v1",
            "as_of": date.today().isoformat(),
            "generated_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "authority": "display_only",
            "summary": {
                "n_rows": 0,
                "by_state": {},
                "n_acknowledged": 0,
                "top_due": None,
                "morning_line": "build error — see gaps.",
            },
            "rows": [],
            "gaps": [f"fatal: {exc}", traceback.format_exc()],
            "caveats": [],
        }

    n_rows = len(payload.get("rows", []))
    n_gaps = len(payload.get("gaps", []))
    ml = payload.get("summary", {}).get("morning_line", "")

    try:
        _atomic_write_json(out_path, payload)
    except Exception as exc:
        log.error("could not write %s: %s", out_path, exc)
        # Still exit 0

    log.info("evidence clock: %d rows, %d gaps", n_rows, n_gaps)
    log.info("morning_line: %s", ml)
    if n_gaps:
        log.warning("%d gap(s) in evidence clock build", n_gaps)
        for g in payload.get("gaps", []):
            log.warning("  gap: %s", g)

    return 0


def main() -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument(
        "--root",
        type=Path,
        default=None,
        help="Repo root (default: parent of scripts/)",
    )
    args = parser.parse_args()
    root = _repo_root(args.root)
    log.info("build_evidence_clock: root=%s", root)
    return build(root)


if __name__ == "__main__":
    sys.exit(main())
