"""Incrementally discover bounded Terminal transcript revisions for evidence.

The Terminal index remains the commit marker.  A durable intake cursor controls
which advertised revisions are fetched, and a root marker is promoted only when
the cursor is drained: a bounded work slice can never replace a broader
last-good public tree.  This is a data-only deterministic worker; it has no
model/provider path.
"""
from __future__ import annotations

import argparse
import gzip
from pathlib import Path
import sys
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from engine.earnings_narrative.contracts import canonical_transcript_body_bytes
from engine.earnings_narrative.extract import build_evidence_pair
from engine.earnings_narrative.generation import EvidencePair, write_generation
from engine.earnings_narrative.health import validate_generation
from engine.earnings_transcript_intake import (
    fetch_body,
    fetch_global_index,
    load_state,
    mark_completed,
    mark_failed,
    parse_global_index,
    plan_index,
    read_local_body,
    save_state,
)
from scripts.publish_earnings_evidence_graph_r2 import PUBLISH_CONFLICT, publish


DEFAULT_TX_BASE_URL = "https://app.mastermind-x.com/data/tx"


class RefreshError(RuntimeError):
    """The last good marker must remain authoritative when refresh refuses."""


def refresh(
    work_dir: Path,
    *,
    tx_base_url: str = DEFAULT_TX_BASE_URL,
    bootstrap_since: str | None = None,
    max_bodies: int = 100,
    out_dir: Path | None = None,
    promote: bool = False,
) -> int:
    if not 1 <= max_bodies <= 500:
        raise RefreshError("max_bodies must be between 1 and 500")
    root = Path(work_dir)
    root.mkdir(parents=True, exist_ok=True)
    state_path = root / "intake-state.json"
    try:
        index = fetch_global_index(tx_base_url)
        refs, metadata = parse_global_index(index)
        index_generated_at = str(metadata.get("generated_at") or "")
        if not index_generated_at:
            raise RefreshError("Terminal index lacks required generated_at receipt")
        state = load_state(state_path, source=tx_base_url)
        state, pending = plan_index(
            refs,
            state,
            metadata=metadata,
            bootstrap_since=bootstrap_since,
        )
    except RefreshError:
        raise
    except Exception as exc:  # noqa: BLE001
        raise RefreshError(f"Terminal discovery refused: {exc}") from exc
    selected = pending[:max_bodies]
    pairs: list[EvidencePair] = []
    omissions: list[dict[str, Any]] = []
    for ref in selected:
        try:
            body = fetch_body(tx_base_url, ref)
            cache_path = root / "bodies" / ref.ticker / f"{ref.transcript_id}.json.gz"
            cache_path.parent.mkdir(parents=True, exist_ok=True)
            cache_path.write_bytes(gzip.compress(canonical_transcript_body_bytes(body), mtime=0))
            pack, graph = build_evidence_pair(
                body,
                index_payload=index,
                indexed_body_sha256=ref.body_sha256 or None,
                index_generated_at=index_generated_at,
            )
            pairs.append(EvidencePair(fact_pack=pack, claim_graph=graph))
            state = mark_completed(state, ref)
        except Exception as exc:  # noqa: BLE001
            state = mark_failed(state, ref, error=str(exc))
            omissions.append({
                "event_key": ref.pair,
                "reason": "body_revision_mismatch" if "hash mismatch" in str(exc) else "body_contract_invalid",
                "expected_source_sha256": ref.body_sha256 or None,
            })
    save_state(state_path, state)
    remaining = len(state["pending"])
    # The final cursor slice rebuilds the full current index from the durable
    # cache. Earlier slices may be inspected locally but cannot be promoted.
    if promote and not remaining:
        pairs = []
        omissions = []
        for ref in refs:
            try:
                body = read_local_body(root / "bodies", ref)
                pack, graph = build_evidence_pair(
                    body,
                    index_payload=index,
                    indexed_body_sha256=ref.body_sha256 or None,
                    index_generated_at=index_generated_at,
                )
                pairs.append(EvidencePair(fact_pack=pack, claim_graph=graph))
            except Exception as exc:  # noqa: BLE001
                raise RefreshError(f"complete cached corpus unavailable for {ref.pair}: {exc}") from exc
    destination = Path(out_dir) if out_dir is not None else root / "output"
    warnings = ["selection_bounded"] if remaining else []
    _generation, manifest = write_generation(destination, pairs, warnings=warnings, omissions=omissions)
    health = validate_generation(destination, manifest)
    if health["status"] == "invalid":
        raise RefreshError("output health invalid: " + ", ".join(health["warnings"]))
    print(
        "earnings evidence: "
        f"discovered={len(refs)} selected={len(selected)} built={len(pairs)} "
        f"remaining={remaining} generation={manifest['generation_id']}"
    )
    if not promote:
        print("earnings evidence: dry discovery/build complete; public root marker not promoted")
        return 0
    if remaining:
        print("earnings evidence: public promotion deferred until bounded intake cursor drains")
        return 0
    result = publish(destination)
    if result == PUBLISH_CONFLICT:
        print("earnings evidence: root marker promotion lost safe compare-and-swap race")
        return result
    if result != 0:
        raise RefreshError(f"R2 publication failed with exit code {result}")
    print("earnings evidence: immutable tree published and root marker promoted")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--work-dir", type=Path, required=True, help="Durable worker scratch containing the intake cursor")
    parser.add_argument("--terminal-tx-base-url", default=DEFAULT_TX_BASE_URL)
    parser.add_argument("--bootstrap-since", default=None, help="Required only on first cursor use; YYYY-MM-DD")
    parser.add_argument("--max-bodies", type=int, default=100)
    parser.add_argument("--out-dir", type=Path, default=None)
    parser.add_argument("--promote", action="store_true", help="Promote only after the bounded cursor has drained")
    args = parser.parse_args(argv)
    try:
        return refresh(
            args.work_dir,
            tx_base_url=args.terminal_tx_base_url,
            bootstrap_since=args.bootstrap_since,
            max_bodies=args.max_bodies,
            out_dir=args.out_dir,
            promote=args.promote,
        )
    except RefreshError as exc:
        print(f"earnings evidence: refresh refused: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
