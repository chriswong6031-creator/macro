"""Incrementally discover bounded Terminal transcript revisions for evidence.

The Terminal index remains the commit marker.  A durable cursor retains one
explicit, bounded cohort (the bootstrap window plus later new/corrected
revisions). A root marker is promoted only after that cohort is cached and
fully rebuilt. Intermediate slices never write ``--out-dir``, so they cannot
replace a last-good public marker. This is a data-only deterministic worker;
it has no model/provider path.
"""
from __future__ import annotations

import argparse
from dataclasses import asdict
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
    TranscriptRef,
)
from scripts.publish_earnings_evidence_graph_r2 import PUBLISH_CONFLICT, load_remote_root_marker, publish


DEFAULT_TX_BASE_URL = "https://app.mastermind-x.com/data/tx"


class RefreshError(RuntimeError):
    """The last good marker must remain authoritative when refresh refuses."""


def _cohort_refs(state: dict[str, Any]) -> dict[str, TranscriptRef]:
    raw = state.get("evidence_cohort") or {}
    if not isinstance(raw, dict):
        raise RefreshError("evidence cohort state is invalid")
    cohort: dict[str, TranscriptRef] = {}
    for key, value in raw.items():
        if not isinstance(key, str) or not isinstance(value, dict):
            raise RefreshError("evidence cohort state is invalid")
        try:
            ref = TranscriptRef(**value)
        except TypeError as exc:
            raise RefreshError("evidence cohort state is invalid") from exc
        if ref.pair != key:
            raise RefreshError("evidence cohort key mismatch")
        cohort[key] = ref
    return cohort


def _oldest_completed_cohort_ref(cohort: dict[str, TranscriptRef], queued: dict[str, TranscriptRef]) -> TranscriptRef | None:
    completed = [ref for pair, ref in cohort.items() if pair not in queued]
    if not completed:
        return None
    return min(completed, key=lambda ref: (ref.call_date or "0000-00-00", ref.transcript_id, ref.ticker))


def _reconcile_cohort(
    state: dict[str, Any],
    pending: list[TranscriptRef],
    *,
    cohort_limit: int,
) -> tuple[dict[str, Any], list[TranscriptRef], dict[str, TranscriptRef], list[TranscriptRef]]:
    """Keep a rolling, bounded evidence cohort independent of old index rows."""
    if not 1 <= cohort_limit <= 2_000:
        raise RefreshError("cohort_limit must be between 1 and 2000")
    out = dict(state)
    evicted: list[TranscriptRef] = []
    if not bool(out.get("evidence_cohort_initialized")):
        cohort = {ref.pair: ref for ref in pending[:cohort_limit]}
        # The intake adapter tracks all first-run refs above the date floor.
        # Explicitly acknowledge the older tail as out-of-cohort; otherwise it
        # would make a bounded promotion non-terminating.
        for ref in pending[cohort_limit:]:
            out = mark_completed(out, ref)
        out["evidence_cohort_initialized"] = True
        out["evidence_cohort_truncated"] = len(pending) > cohort_limit
        out["evidence_cohort_scope_limited"] = len(pending) < len(out.get("known") or {})
        out["evidence_cohort"] = {pair: asdict(ref) for pair, ref in sorted(cohort.items())}
        return out, pending[:cohort_limit], cohort, evicted

    cohort = _cohort_refs(out)
    queued = {ref.pair: ref for ref in pending}
    for ref in pending:
        existing = cohort.get(ref.pair)
        if existing is not None:
            # A corrected revision of a retained event stays in the cohort.
            cohort[ref.pair] = ref
            continue
        if len(cohort) >= cohort_limit:
            victim = _oldest_completed_cohort_ref(cohort, queued)
            if victim is None:
                # Do not drop an arriving revision. It remains queued until a
                # completed cohort member can roll off without shrinking coverage.
                continue
            cohort.pop(victim.pair)
            evicted.append(victim)
            out["evidence_cohort_rolled_over"] = True
        cohort[ref.pair] = ref
    active: list[TranscriptRef] = []
    for ref in pending:
        current = cohort.get(ref.pair)
        if current is not None and current.revision_key == ref.revision_key:
            active.append(ref)
        elif current is not None:
            # An old queued revision lost to a correction; it must not block
            # the current cohort drain.
            out = mark_completed(out, ref)
    out["evidence_cohort"] = {pair: asdict(ref) for pair, ref in sorted(cohort.items())}
    return out, active, cohort, evicted


def refresh(
    work_dir: Path,
    *,
    tx_base_url: str = DEFAULT_TX_BASE_URL,
    bootstrap_since: str | None = None,
    max_bodies: int = 100,
    cohort_limit: int = 500,
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
    state, pending, cohort, evicted = _reconcile_cohort(state, pending, cohort_limit=cohort_limit)
    for ref in evicted:
        (root / "bodies" / ref.ticker / f"{ref.transcript_id}.json.gz").unlink(missing_ok=True)
    selected = pending[:max_bodies]
    for ref in selected:
        try:
            body = fetch_body(tx_base_url, ref)
            # Validate the complete closed evidence pair before acknowledging
            # the revision in the cursor. A bad body remains pending for a
            # later corrected Terminal index/body rather than poisoning cache.
            build_evidence_pair(
                body,
                index_payload=index,
                indexed_body_sha256=ref.body_sha256 or None,
                index_generated_at=index_generated_at,
            )
            cache_path = root / "bodies" / ref.ticker / f"{ref.transcript_id}.json.gz"
            cache_path.parent.mkdir(parents=True, exist_ok=True)
            cache_path.write_bytes(gzip.compress(canonical_transcript_body_bytes(body), mtime=0))
            state = mark_completed(state, ref)
        except Exception as exc:  # noqa: BLE001
            state = mark_failed(state, ref, error=str(exc))
    save_state(state_path, state)
    remaining = len(state["pending"])
    print(
        "earnings evidence: "
        f"discovered={len(refs)} cohort={len(cohort)} selected={len(selected)} remaining={remaining}"
    )
    if not promote or remaining:
        if not promote:
            print("earnings evidence: discovery complete; public root marker not promoted")
        else:
            print("earnings evidence: public promotion deferred until bounded cohort cursor drains")
        return 0
    # Only the complete retained cohort touches --out-dir.  This preserves the
    # prior public root and its correction ancestry through every work slice.
    pairs: list[EvidencePair] = []
    for ref in sorted(cohort.values(), key=lambda item: (item.call_date, item.transcript_id, item.ticker), reverse=True):
        try:
            body = read_local_body(root / "bodies", ref)
            pack, graph = build_evidence_pair(
                body,
                index_payload=index,
                indexed_body_sha256=ref.body_sha256 or None,
                index_generated_at=index_generated_at,
            )
            pairs.append(EvidencePair(fact_pack=pack, claim_graph=graph, transcript=body))
        except Exception as exc:  # noqa: BLE001
            raise RefreshError(f"complete cached cohort unavailable for {ref.pair}: {exc}") from exc
    destination = Path(out_dir) if out_dir is not None else root / "output"
    warnings = ["selection_bounded"] if any(
        bool(state.get(key))
        for key in ("evidence_cohort_truncated", "evidence_cohort_scope_limited", "evidence_cohort_rolled_over")
    ) else []
    # A cache loss must not erase correction lineage. Prefer the public R2
    # marker whenever credentials are available; otherwise the local marker is
    # a read-only fallback for explicit/offline runs.
    prior_manifest = load_remote_root_marker()
    _generation, manifest = write_generation(
        destination,
        pairs,
        warnings=warnings,
        coverage={
            "selection_policy": "bootstrap_since_then_new_or_corrected",
            "cohort_limit": cohort_limit,
            "historical_completeness": (
                len(cohort) == int(metadata["body_count"])
                and not any(bool(state.get(key)) for key in ("evidence_cohort_truncated", "evidence_cohort_scope_limited", "evidence_cohort_rolled_over"))
            ),
            "index_body_count": int(metadata["body_count"]),
            "index_generated_at": index_generated_at,
        },
        prior_manifest=prior_manifest,
    )
    health = validate_generation(destination, manifest)
    if health["status"] == "invalid":
        raise RefreshError("output health invalid: " + ", ".join(health["warnings"]))
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
    parser.add_argument("--cohort-limit", type=int, default=500, help="Maximum retained current cohort (1..2000)")
    parser.add_argument("--out-dir", type=Path, default=None)
    parser.add_argument("--promote", action="store_true", help="Promote only after the bounded cursor has drained")
    args = parser.parse_args(argv)
    try:
        return refresh(
            args.work_dir,
            tx_base_url=args.terminal_tx_base_url,
            bootstrap_since=args.bootstrap_since,
            max_bodies=args.max_bodies,
            cohort_limit=args.cohort_limit,
            out_dir=args.out_dir,
            promote=args.promote,
        )
    except RefreshError as exc:
        print(f"earnings evidence: refresh refused: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
