"""Build one deterministic earnings digest/story packet from evidence objects.

This is the operational seam between the append-only evidence plane and the
existing Press lane.  It performs no network or model call.
"""
from __future__ import annotations

import argparse
from hashlib import sha256
import json
from pathlib import Path
import re
import sys
import tempfile
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from engine.earnings_narrative.contracts import ContractError, canonical_json_bytes
from engine.earnings_narrative.digest import build_event_digest
from engine.earnings_narrative.digest import validate_event_digest
from engine.earnings_narrative.story import (
    build_canonical_story,
    validate_canonical_story,
    validate_correction_against_prior,
    validate_story_against_digest,
)
from engine.press.earnings_adapter import story_to_press_slot


_PACKET_POINTER_KEYS = frozenset({
    "schema", "packet_generation_id", "story_id", "story_revision_id",
    "digest_id", "tier", "article_eligible", "correction_status",
    "generation_path", "files",
})
_FILE_RECEIPT_KEYS = frozenset({"sha256", "bytes"})
_PACKET_GENERATION = re.compile(r"^packet_[0-9a-f]{32}$")


def _load(path: Path) -> object:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ContractError(f"cannot read canonical JSON from {path}: {exc}") from exc


def _atomic_write(path: Path, payload: object) -> None:
    body = canonical_json_bytes(payload)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="wb", prefix=f".{path.name}.", dir=path.parent, delete=False,
        ) as handle:
            handle.write(body)
            temporary = Path(handle.name)
        temporary.replace(path)
    finally:
        if temporary is not None and temporary.exists():
            temporary.unlink()


def _load_canonical(path: Path) -> object:
    try:
        raw = path.read_bytes()
        payload = json.loads(raw.decode("utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ContractError(f"cannot read canonical packet JSON from {path}: {exc}") from exc
    if raw != canonical_json_bytes(payload):
        raise ContractError(f"story packet JSON is not canonical: {path}")
    return payload


def load_published_packet(out_dir: Path) -> dict[str, Any]:
    """Verify the atomic pointer, immutable receipts, and all packet contracts."""
    pointer = _load_canonical(out_dir / "latest.json")
    if not isinstance(pointer, dict) or set(pointer) != _PACKET_POINTER_KEYS:
        raise ContractError("story packet pointer fields mismatch")
    if pointer.get("schema") != "earnings.story_packet_pointer/v1":
        raise ContractError("story packet pointer schema mismatch")
    generation_id = pointer.get("packet_generation_id")
    if not isinstance(generation_id, str) or not _PACKET_GENERATION.fullmatch(generation_id):
        raise ContractError("story packet generation id invalid")
    expected_path = f"generations/{generation_id}"
    if pointer.get("generation_path") != expected_path:
        raise ContractError("story packet generation path mismatch")
    generation_dir = out_dir / expected_path
    if not generation_dir.is_dir():
        raise ContractError("story packet generation directory is absent")
    expected_files = {"event_digest.json", "canonical_story.json"}
    if pointer.get("article_eligible") is True:
        expected_files.add("press_slot.json")
    elif pointer.get("article_eligible") is not False:
        raise ContractError("story packet article_eligible must be boolean")
    correction_status = pointer.get("correction_status")
    if correction_status == "corrected":
        expected_files.add("prior_story.json")
    elif correction_status != "current":
        raise ContractError("story packet correction_status invalid")
    receipts = pointer.get("files")
    if not isinstance(receipts, dict) or set(receipts) != expected_files:
        raise ContractError("story packet file receipt set mismatch")
    if {path.name for path in generation_dir.iterdir()} != expected_files:
        raise ContractError("story packet immutable generation file set mismatch")

    payloads: dict[str, Any] = {}
    serialized: dict[str, bytes] = {}
    for name in sorted(expected_files):
        receipt = receipts.get(name)
        if not isinstance(receipt, dict) or set(receipt) != _FILE_RECEIPT_KEYS:
            raise ContractError(f"story packet file receipt invalid: {name}")
        path = generation_dir / name
        raw = path.read_bytes()
        if (
            isinstance(receipt.get("bytes"), bool)
            or not isinstance(receipt.get("bytes"), int)
            or receipt["bytes"] != len(raw)
            or receipt.get("sha256") != sha256(raw).hexdigest()
        ):
            raise ContractError(f"story packet file receipt mismatch: {name}")
        payload = _load_canonical(path)
        payloads[name] = payload
        serialized[name] = raw

    generation_material = b"".join(
        name.encode("utf-8") + b"\0" + body
        for name, body in sorted(serialized.items())
    )
    if generation_id != "packet_" + sha256(generation_material).hexdigest()[:32]:
        raise ContractError("story packet generation id does not bind immutable files")
    digest = payloads["event_digest.json"]
    story = payloads["canonical_story.json"]
    validate_event_digest(digest)
    validate_canonical_story(story)
    validate_story_against_digest(story, digest)
    if (
        pointer.get("story_id") != story["story_id"]
        or pointer.get("story_revision_id") != story["story_revision_id"]
        or pointer.get("digest_id") != digest["digest_id"]
        or pointer.get("tier") != story["promotion"]["tier"]
        or pointer.get("article_eligible") is not story["promotion"]["article_eligible"]
        or pointer.get("correction_status") != story["correction"]["status"]
    ):
        raise ContractError("story packet pointer differs from canonical story")
    prior_story = payloads.get("prior_story.json")
    if story["correction"]["status"] == "corrected":
        if prior_story is None:
            raise ContractError("corrected story packet is missing its prior manifest")
        validate_correction_against_prior(story, prior_story)
    if story["promotion"]["article_eligible"]:
        expected_slot = story_to_press_slot(story, digest, prior_story=prior_story)
        if payloads.get("press_slot.json") != expected_slot:
            raise ContractError("story packet Press slot does not replay")
    return {
        "packet_pointer": pointer,
        "event_digest": digest,
        "canonical_story": story,
        "press_slot": payloads.get("press_slot.json"),
        "prior_story": prior_story,
    }


def _publish_packet(out_dir: Path, payloads: dict[str, object], story: dict[str, Any]) -> dict[str, Any]:
    """Publish one immutable generation, then atomically move its root pointer."""
    serialized = {
        name: canonical_json_bytes(payload)
        for name, payload in sorted(payloads.items())
    }
    generation_material = b"".join(
        name.encode("utf-8") + b"\0" + body
        for name, body in sorted(serialized.items())
    )
    generation_name = "packet_" + sha256(generation_material).hexdigest()[:32]
    generations = out_dir / "generations"
    generations.mkdir(parents=True, exist_ok=True)
    generation_dir = generations / generation_name
    if generation_dir.exists():
        for name, body in serialized.items():
            path = generation_dir / name
            if not path.is_file() or path.read_bytes() != body:
                raise ContractError(f"immutable story packet generation collision: {generation_name}/{name}")
        if sorted(path.name for path in generation_dir.iterdir()) != sorted(serialized):
            raise ContractError(f"immutable story packet generation file set differs: {generation_name}")
    else:
        with tempfile.TemporaryDirectory(prefix=".packet-", dir=generations) as temporary:
            temporary_dir = Path(temporary)
            for name, body in serialized.items():
                (temporary_dir / name).write_bytes(body)
            try:
                temporary_dir.rename(generation_dir)
            except OSError:
                if not generation_dir.is_dir():
                    raise
                for name, body in serialized.items():
                    path = generation_dir / name
                    if not path.is_file() or path.read_bytes() != body:
                        raise ContractError(
                            f"concurrent immutable story packet collision: {generation_name}/{name}"
                        )

    pointer = {
        "schema": "earnings.story_packet_pointer/v1",
        "packet_generation_id": generation_name,
        "story_id": story["story_id"],
        "story_revision_id": story["story_revision_id"],
        "digest_id": story["digest"]["digest_id"],
        "tier": story["promotion"]["tier"],
        "article_eligible": story["promotion"]["article_eligible"],
        "correction_status": story["correction"]["status"],
        "generation_path": f"generations/{generation_name}",
        "files": {
            name: {"sha256": sha256(body).hexdigest(), "bytes": len(body)}
            for name, body in sorted(serialized.items())
        },
    }
    _atomic_write(out_dir / "latest.json", pointer)
    return pointer


def build_packet(
    fact_pack_path: Path,
    claim_graph_path: Path,
    source_body_path: Path,
    out_dir: Path,
    *,
    tier: str = "C",
    reasons: list[str] | None = None,
    decision_source: str = "default_hold",
    prior_story_path: Path | None = None,
    max_facts: int = 12,
    per_category_cap: int = 3,
) -> dict[str, Any]:
    fact_pack = _load(fact_pack_path)
    claim_graph = _load(claim_graph_path)
    source_body = _load(source_body_path)
    digest = build_event_digest(
        fact_pack,
        claim_graph,
        source_body,
        max_facts=max_facts,
        per_category_cap=per_category_cap,
    )
    prior_story = _load(prior_story_path) if prior_story_path is not None else None
    story = build_canonical_story(
        digest,
        tier=tier,
        reasons=reasons or ["awaiting_governed_promotion"],
        decision_source=decision_source,
        prior_story=prior_story,
    )
    press_slot = None
    if story["promotion"]["article_eligible"]:
        press_slot = story_to_press_slot(story, digest, prior_story=prior_story)

    # Compile and validate every derivative before moving any file.  Immutable
    # generations land first; latest.json is the sole atomic commit marker.
    packet_payloads: dict[str, object] = {
        "event_digest.json": digest,
        "canonical_story.json": story,
    }
    if press_slot is not None:
        packet_payloads["press_slot.json"] = press_slot
    if prior_story is not None:
        packet_payloads["prior_story.json"] = prior_story
    pointer = _publish_packet(out_dir, packet_payloads, story)
    return {
        "event_digest": digest,
        "canonical_story": story,
        "press_slot": press_slot,
        "packet_pointer": pointer,
        "prior_story": prior_story,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--fact-pack", type=Path, required=True)
    parser.add_argument("--claim-graph", type=Path, required=True)
    parser.add_argument("--source-body", type=Path, required=True)
    parser.add_argument("--out-dir", type=Path, required=True)
    parser.add_argument("--tier", choices=("A", "B", "C"), default="C")
    parser.add_argument("--reason", action="append", default=[])
    parser.add_argument(
        "--decision-source",
        choices=("default_hold", "governed_triage", "operator"),
        default="default_hold",
    )
    parser.add_argument("--prior-story", type=Path)
    parser.add_argument("--max-facts", type=int, default=12)
    parser.add_argument("--per-category-cap", type=int, default=3)
    args = parser.parse_args(argv)
    result = build_packet(
        args.fact_pack,
        args.claim_graph,
        args.source_body,
        args.out_dir,
        tier=args.tier,
        reasons=args.reason or None,
        decision_source=args.decision_source,
        prior_story_path=args.prior_story,
        max_facts=args.max_facts,
        per_category_cap=args.per_category_cap,
    )
    story = result["canonical_story"]
    print(json.dumps({
        "story_id": story["story_id"],
        "story_revision_id": story["story_revision_id"],
        "digest_id": result["event_digest"]["digest_id"],
        "tier": story["promotion"]["tier"],
        "article_eligible": story["promotion"]["article_eligible"],
        "press_slot_written": result["press_slot"] is not None,
        "generation_path": result["packet_pointer"]["generation_path"],
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
