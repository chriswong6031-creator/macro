"""Build a bounded, deterministic earnings evidence generation from Terminal data.

Input is intentionally narrow: a committed ``mastermind.tx-index/v1`` marker
plus the corresponding gzip bodies.  This script does not read Company
Intelligence summaries/highlights, call a provider, or produce an article.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from engine.earnings_narrative.extract import build_evidence_pair
from engine.earnings_narrative.generation import EvidencePair, write_generation
from engine.earnings_narrative.health import validate_generation
from engine.earnings_transcript_intake import parse_global_index, read_local_body


def _read_index(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("Terminal transcript index must be an object")
    return payload


def build(
    tx_index: Path,
    transcripts_dir: Path,
    out_dir: Path,
    *,
    max_bodies: int,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Build at most ``max_bodies`` newest index-advertised revisions."""
    if not 1 <= max_bodies <= 500:
        raise ValueError("max_bodies must be between 1 and 500")
    index = _read_index(Path(tx_index))
    refs, metadata = parse_global_index(index)
    index_generated_at = str(metadata.get("generated_at") or "")
    if not index_generated_at:
        raise ValueError("Terminal index generated_at is required for receipt chronology")
    selected = refs[:max_bodies]
    pairs: list[EvidencePair] = []
    omissions: list[dict[str, Any]] = []
    for ref in selected:
        try:
            if not (Path(transcripts_dir) / ref.ticker / f"{ref.transcript_id}.json.gz").is_file():
                raise FileNotFoundError(ref.pair)
            body = read_local_body(Path(transcripts_dir), ref)
            pack, graph = build_evidence_pair(
                body,
                index_payload=index,
                indexed_body_sha256=ref.body_sha256 or None,
                index_generated_at=index_generated_at,
            )
            pairs.append(EvidencePair(fact_pack=pack, claim_graph=graph, transcript=body))
        except FileNotFoundError:
            omissions.append({
                "event_key": ref.pair,
                "reason": "missing_body",
                "expected_source_sha256": ref.body_sha256 or None,
            })
        except Exception as exc:  # noqa: BLE001 - keep every selected omission explicit.
            reason = "body_revision_mismatch" if "hash mismatch" in str(exc) or "revision mismatch" in str(exc) else "body_contract_invalid"
            omissions.append({
                "event_key": ref.pair,
                "reason": reason,
                "expected_source_sha256": ref.body_sha256 or None,
            })
    warnings = ["selection_bounded"] if len(refs) > len(selected) else []
    generation, manifest = write_generation(
        Path(out_dir),
        pairs,
        warnings=warnings,
        omissions=omissions,
        coverage={
            "selection_policy": "explicit_input",
            "batch_limit": max_bodies,
            "historical_completeness": len(selected) == len(refs) and not omissions,
            "index_body_count": int(metadata["body_count"]),
            "index_generated_at": index_generated_at,
        },
    )
    health = validate_generation(Path(out_dir), manifest)
    if health["status"] == "invalid":
        raise ValueError("written evidence generation failed health: " + ", ".join(health["warnings"]))
    return manifest, {
        "generation_dir": generation,
        "selected": len(selected),
        "discovered": len(refs),
        "built": len(pairs),
        "omitted": len(omissions),
        "health": health,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tx-index", type=Path, required=True, help="Committed Terminal index.json")
    parser.add_argument("--transcripts-dir", type=Path, required=True, help="Directory containing <TICKER>/<YYYYQn>.json.gz")
    parser.add_argument("--out-dir", type=Path, required=True)
    parser.add_argument("--max-bodies", type=int, default=100, help="Newest index refs to read (1..500; default 100)")
    args = parser.parse_args(argv)
    try:
        manifest, report = build(args.tx_index, args.transcripts_dir, args.out_dir, max_bodies=args.max_bodies)
    except Exception as exc:  # noqa: BLE001
        print(f"earnings evidence: build refused: {exc}", file=sys.stderr)
        return 1
    print(
        "earnings evidence: "
        f"generation={manifest['generation_id']} status={manifest['status']} "
        f"discovered={report['discovered']} selected={report['selected']} "
        f"built={report['built']} omitted={report['omitted']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
