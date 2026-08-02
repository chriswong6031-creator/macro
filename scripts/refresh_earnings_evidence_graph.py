"""Append-only refresh of the verified Terminal transcript evidence catalog.

R2's verified root marker is the accumulated catalog of record.  The local
cursor/cache only avoids refetching bodies: every run diffs the current
Terminal index against that catalog, processes a bounded delta, unions it with
the prior event refs, and never rolls historical evidence off the root.
"""
from __future__ import annotations

import argparse
from dataclasses import asdict
import gzip
import json
import os
from pathlib import Path
import sys
from typing import Any, Mapping

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from engine.earnings_narrative.contracts import canonical_json_bytes, canonical_transcript_body_bytes, validate_manifest
from engine.earnings_narrative.extract import build_evidence_pair
from engine.earnings_narrative.generation import EvidencePair, write_generation
from engine.earnings_narrative.health import validate_generation
from engine.earnings_transcript_intake import (
    TranscriptRef,
    fetch_body,
    fetch_global_index,
    load_state,
    mark_completed,
    mark_failed,
    parse_global_index,
    read_local_body,
    save_state,
)
from scripts.publish_earnings_evidence_graph_r2 import PUBLISH_CONFLICT, load_remote_root_state, publish


DEFAULT_TX_BASE_URL = "https://app.mastermind-x.com/data/tx"


class RefreshError(RuntimeError):
    """The public catalog cannot be advanced safely."""


def _receipt_path(root: Path, ref: TranscriptRef) -> Path:
    return root / "bodies" / ref.ticker / f"{ref.transcript_id}.receipt.json"


def _write_source_receipt(root: Path, ref: TranscriptRef, receipt: Mapping[str, Any]) -> None:
    path = _receipt_path(root, ref)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp.{os.getpid()}")
    try:
        temporary.write_bytes(canonical_json_bytes(dict(receipt)))
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def _read_source_receipt(root: Path, ref: TranscriptRef) -> object:
    try:
        return json.loads(_receipt_path(root, ref).read_text(encoding="utf-8"))
    except Exception as exc:  # noqa: BLE001
        raise RefreshError(f"cannot read cached source receipt for {ref.pair}: {exc}") from exc


def _local_healthy_marker(destination: Path) -> dict[str, Any] | None:
    health = validate_generation(destination)
    if health["status"] != "ready":
        return None
    try:
        marker = json.loads((destination / "manifest.json").read_text(encoding="utf-8"))
        validate_manifest(marker)
        return marker
    except Exception:  # noqa: BLE001 - health is authoritative at this boundary.
        return None


def _catalog_pending(refs: list[TranscriptRef], marker: Mapping[str, Any] | None) -> list[TranscriptRef]:
    events = marker.get("events") if isinstance(marker, Mapping) else None
    events = events if isinstance(events, Mapping) else {}
    pending: list[TranscriptRef] = []
    for ref in refs:
        event = events.get(ref.pair)
        indexed_sha = ref.body_sha256
        if not isinstance(event, Mapping) or (indexed_sha and event.get("source_sha256") != indexed_sha):
            pending.append(ref)
    return pending


def _order_pending(pending: list[TranscriptRef], state: Mapping[str, Any]) -> list[TranscriptRef]:
    """Preserve failure rotation while adding new catalog deltas deterministically."""
    required = {ref.pair: ref for ref in pending}
    ordered: list[TranscriptRef] = []
    prior = state.get("pending") if isinstance(state, Mapping) else None
    if isinstance(prior, list):
        for item in prior:
            if not isinstance(item, Mapping):
                continue
            try:
                ref = TranscriptRef(**item)
            except TypeError:
                continue
            current = required.pop(ref.pair, None)
            if current is not None:
                ordered.append(current)
    ordered.extend(sorted(required.values(), key=lambda ref: (ref.call_date, ref.transcript_id, ref.ticker), reverse=True))
    return ordered


def _catalog_complete(refs: list[TranscriptRef], events: Mapping[str, Any]) -> bool:
    for ref in refs:
        event = events.get(ref.pair)
        if not isinstance(event, Mapping) or (ref.body_sha256 and event.get("source_sha256") != ref.body_sha256):
            return False
    return True


def _cached_or_fetched_pair(
    root: Path,
    ref: TranscriptRef,
    *,
    tx_base_url: str,
    index: object,
    index_generated_at: str,
) -> EvidencePair:
    """Return an exact cached receipt when possible, otherwise intake once."""
    try:
        body = read_local_body(root / "bodies", ref)
        receipt = _read_source_receipt(root, ref)
        pack, graph = build_evidence_pair(body, source_receipt=receipt)
        if not ref.body_sha256 or pack["source"]["body_sha256"] != ref.body_sha256:
            raise RefreshError(f"cached source receipt is not the current indexed revision for {ref.pair}")
        return EvidencePair(fact_pack=pack, claim_graph=graph, transcript=body)
    except Exception:  # noqa: BLE001 - refetch and revalidate the authoritative revision.
        body = fetch_body(tx_base_url, ref)
        pack, _graph = build_evidence_pair(
            body,
            index_payload=index,
            indexed_body_sha256=ref.body_sha256 or None,
            index_generated_at=index_generated_at,
        )
        cache_path = root / "bodies" / ref.ticker / f"{ref.transcript_id}.json.gz"
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        cache_path.write_bytes(gzip.compress(canonical_transcript_body_bytes(body), mtime=0))
        _write_source_receipt(root, ref, pack["source"])
        stable_pack, stable_graph = build_evidence_pair(body, source_receipt=pack["source"])
        return EvidencePair(fact_pack=stable_pack, claim_graph=stable_graph, transcript=body)


def refresh(
    work_dir: Path,
    *,
    tx_base_url: str = DEFAULT_TX_BASE_URL,
    max_bodies: int = 100,
    out_dir: Path | None = None,
    promote: bool = False,
) -> int:
    """Append at most ``max_bodies`` index deltas; a no-change run writes nothing."""
    if not 1 <= max_bodies <= 500:
        raise RefreshError("max_bodies must be between 1 and 500")
    root = Path(work_dir)
    root.mkdir(parents=True, exist_ok=True)
    destination = Path(out_dir) if out_dir is not None else root / "output"
    state_path = root / "intake-state.json"
    try:
        index = fetch_global_index(tx_base_url)
        refs, metadata = parse_global_index(index)
        index_generated_at = str(metadata.get("generated_at") or "")
        if not index_generated_at:
            raise RefreshError("Terminal index lacks required generated_at receipt")
        remote_marker, _remote_etag, remote_digest = load_remote_root_state()
        prior_marker = remote_marker or _local_healthy_marker(destination)
        state = load_state(state_path, source=tx_base_url)
    except RefreshError:
        raise
    except Exception as exc:  # noqa: BLE001
        raise RefreshError(f"Terminal discovery refused: {exc}") from exc

    pending = _order_pending(_catalog_pending(refs, prior_marker), state)
    state = dict(state)
    state["known"] = {ref.pair: ref.body_sha256 for ref in refs}
    state["pending"] = [asdict(ref) for ref in pending]
    state["initialized"] = True
    state["last_index_generated_at"] = index_generated_at
    state["last_index_body_count"] = int(metadata["body_count"])
    state["last_index_symbol_count"] = int(metadata["symbol_count"])

    if not pending:
        save_state(state_path, state)
        if prior_marker is None:
            raise RefreshError("index has no pending rows but no healthy catalog marker exists")
        print("earnings evidence: index unchanged; healthy append-only catalog is a true no-op")
        return 0

    selected = pending[:max_bodies]
    pairs: list[EvidencePair] = []
    for ref in selected:
        try:
            pair = _cached_or_fetched_pair(root, ref, tx_base_url=tx_base_url, index=index, index_generated_at=index_generated_at)
            pairs.append(pair)
            state = mark_completed(state, ref)
        except Exception as exc:  # noqa: BLE001
            state = mark_failed(state, ref, error=str(exc))
    save_state(state_path, state)
    if not pairs:
        raise RefreshError("no selected transcript body passed closed-contract intake")
    if not promote:
        print(f"earnings evidence: validated {len(pairs)} append candidates; public root not promoted")
        return 0

    prior_events = prior_marker.get("events") if isinstance(prior_marker, Mapping) else {}
    prospective_events = dict(prior_events) if isinstance(prior_events, Mapping) else {}
    for pair in pairs:
        prospective_events[f"{pair.fact_pack['event']['ticker']}/{pair.fact_pack['event']['transcript_id']}"] = {
            "source_sha256": pair.fact_pack["source"]["body_sha256"],
        }
    complete = _catalog_complete(refs, prospective_events)
    warnings = [] if complete else ["backfill_pending"]
    _generation, manifest = write_generation(
        destination,
        pairs,
        warnings=warnings,
        coverage={
            "selection_policy": "append_only_full_index",
            "batch_limit": max_bodies,
            "historical_completeness": complete,
            "index_body_count": int(metadata["body_count"]),
            "index_generated_at": index_generated_at,
        },
        prior_manifest=prior_marker,
    )
    # A cache-restored catalog can receive full local health here. A fresh
    # runner stages only the delta and the publisher verifies those objects
    # against the authoritative root before its CAS promotion.
    result = publish(
        destination,
        expected_base_marker_sha256=remote_digest,
        require_absent_root=remote_marker is None,
    )
    if result == PUBLISH_CONFLICT:
        print("earnings evidence: root marker promotion lost safe compare-and-swap race")
        return result
    if result != 0:
        raise RefreshError(f"R2 publication failed with exit code {result}")
    print(
        "earnings evidence: append published "
        f"events={manifest['coverage']['event_count']} batch={len(pairs)} "
        f"complete={manifest['coverage']['historical_completeness']}"
    )
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--work-dir", type=Path, required=True, help="Cache/cursor only; R2 root is the catalog of record")
    parser.add_argument("--terminal-tx-base-url", default=DEFAULT_TX_BASE_URL)
    parser.add_argument("--max-bodies", type=int, default=100, help="Append batch size (1..500; full history drains over runs)")
    parser.add_argument("--out-dir", type=Path, default=None)
    parser.add_argument("--promote", action="store_true", help="Append this verified bounded batch to the public catalog")
    args = parser.parse_args(argv)
    try:
        return refresh(
            args.work_dir,
            tx_base_url=args.terminal_tx_base_url,
            max_bodies=args.max_bodies,
            out_dir=args.out_dir,
            promote=args.promote,
        )
    except RefreshError as exc:
        print(f"earnings evidence: refresh refused: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
