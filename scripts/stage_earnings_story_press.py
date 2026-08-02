"""Admit and stage one exact current earnings story packet.

This is a deliberately closed bridge between the deterministic earnings story
projection and the existing Press writer/validator rail.  Its CLI accepts three
immutable identities and nothing else.  It never ranks candidates, accepts a
packet path or caller-built slot, changes promotion tier, emits an article,
writes R2, or writes the repository.

The transport audit and packet replay happen before the first possible model
call.  The current R2 marker is checked again immediately before that call and
after the staging artifact is written.  A post-call root race quarantines the
artifact and fails the run; it never leaves a stale draft marked as passing.
"""
from __future__ import annotations

import argparse
import json
import logging
import os
from pathlib import Path
import re
import sys
from typing import Any, Mapping


_REPO = Path(__file__).resolve().parent.parent
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

from engine.earnings_narrative.admission import (  # noqa: E402
    build_press_admission,
    validate_press_admission,
)
from engine.earnings_narrative.contracts import (  # noqa: E402
    canonical_json_bytes,
    canonical_json_sha256,
)
from engine.press import desk_planner  # noqa: E402
from engine.press.earnings_adapter import story_to_press_slot  # noqa: E402
from scripts import publish_earnings_story_packets_r2 as story_r2  # noqa: E402
from scripts.run_press import run_admitted_earnings_staging  # noqa: E402


log = logging.getLogger("stage_earnings_story_press")
_STAGING_NAME = "earnings-story-press-stage"
_GENERATION_ID = re.compile(r"^[0-9a-f]{32}$")
_PACKET_ID = re.compile(r"^storypacket_[0-9a-f]{32}$")
_STORY_REVISION_ID = re.compile(r"^storyrev_[0-9a-f]{32}$")


class EarningsStoryIngressError(RuntimeError):
    """The exact packet cannot safely cross into one-call Press staging."""


def _derive_slot(packet: Mapping[str, Any]) -> dict[str, Any]:
    prior = packet.get("prior")
    prior_story = prior.get("story") if isinstance(prior, Mapping) else None
    slot = story_to_press_slot(
        packet["story"],
        packet["digest"],
        prior_story=prior_story,
    )
    if canonical_json_bytes(slot) != canonical_json_bytes(packet.get("press_slot")):
        raise EarningsStoryIngressError("current packet Press slot differs from canonical adapter replay")
    return slot


def _validate_requested_ids(generation_id: str, packet_id: str, story_revision_id: str) -> None:
    if not isinstance(generation_id, str) or not _GENERATION_ID.fullmatch(generation_id):
        raise EarningsStoryIngressError("generation_id is invalid")
    if not isinstance(packet_id, str) or not _PACKET_ID.fullmatch(packet_id):
        raise EarningsStoryIngressError("packet_id is invalid")
    if not isinstance(story_revision_id, str) or not _STORY_REVISION_ID.fullmatch(story_revision_id):
        raise EarningsStoryIngressError("story_revision_id is invalid")


def _record_root_status(staging_dir: Path, *, current: bool, reason: str = "") -> None:
    """Keep the uploaded artifact honest if the root moves during the model call."""
    for path in sorted(staging_dir.glob("*.json")):
        if path.name.startswith("_"):
            continue
        try:
            row = json.loads(path.read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001 - a corrupt output is already a failed run.
            continue
        if not isinstance(row, dict):
            continue
        row["story_root_current_after_stage"] = current
        if not current:
            row["status"] = "quarantined"
            row["quarantine_reason"] = reason
        path.write_text(json.dumps(row, ensure_ascii=False, indent=2, default=str) + "\n", encoding="utf-8")

    summary_path = staging_dir / "_run_summary.json"
    if not summary_path.exists():
        raise EarningsStoryIngressError("admitted staging produced no _run_summary.json")
    try:
        summary = json.loads(summary_path.read_text(encoding="utf-8"))
    except Exception as exc:  # noqa: BLE001
        raise EarningsStoryIngressError("admitted staging summary is unreadable") from exc
    if not isinstance(summary, dict):
        raise EarningsStoryIngressError("admitted staging summary is not an object")
    summary["story_root_current_after_stage"] = current
    if not current:
        summary["passed"] = 0
        summary["quarantined"] = max(1, int(summary.get("quarantined") or 0))
        summary["root_race_reason"] = reason
        for item in summary.get("items") or []:
            if isinstance(item, dict):
                item["status"] = "quarantined"
    summary_path.write_text(
        json.dumps(summary, ensure_ascii=False, indent=2, default=str) + "\n",
        encoding="utf-8",
    )


def stage_exact_current_story(
    *,
    generation_id: str,
    packet_id: str,
    story_revision_id: str,
    staging_dir: Path,
    root: Path = _REPO,
    s3: Any | None = None,
    bucket: str | None = None,
) -> dict[str, Any]:
    """Full-audit, derive, and stage exactly one current Tier-B packet."""
    _validate_requested_ids(generation_id, packet_id, story_revision_id)
    destination = Path(staging_dir)
    if destination.exists() and any(destination.iterdir()):
        raise EarningsStoryIngressError("dedicated earnings story staging directory is not empty")

    client = s3 if s3 is not None else story_r2._client()  # transport owns credential construction
    if client is None:
        raise EarningsStoryIngressError("read-only R2 credentials are required")
    target_bucket = bucket or os.environ.get("R2_BUCKET", "")
    if not target_bucket:
        raise EarningsStoryIngressError("R2_BUCKET is required")

    # JIT full replay: current + all ancestors + every bound evidence object.
    audit = story_r2.hydrate_and_verify_current_story_root(s3=client, bucket=target_bucket)
    packet = story_r2.load_exact_current_story_packet(
        audit,
        generation_id=generation_id,
        packet_id=packet_id,
        story_revision_id=story_revision_id,
        s3=client,
        bucket=target_bucket,
    )
    admission = build_press_admission(audit, packet)
    validate_press_admission(admission, audit_binding=audit, packet=packet)
    slot = _derive_slot(packet)
    if admission["press_slot"]["sha256"] != canonical_json_sha256(slot):
        raise EarningsStoryIngressError("admission does not bind the replayed Press slot")

    cfg = desk_planner.load_config(root)
    if not cfg:
        raise EarningsStoryIngressError("config/press.yml is missing or invalid")

    # Last zero-token boundary.  A stale ID, object, admission, or root race has
    # made no model request when execution reaches any failure above this line.
    story_r2.assert_story_root_binding_current(audit, s3=client, bucket=target_bucket)
    summary = run_admitted_earnings_staging(
        root,
        cfg,
        slot=slot,
        admission_receipt=admission,
        staging_dir=destination,
    )
    if not (destination / "_run_summary.json").exists():
        raise EarningsStoryIngressError("admitted staging produced no _run_summary.json")

    try:
        story_r2.assert_story_root_binding_current(audit, s3=client, bucket=target_bucket)
    except Exception as exc:
        reason = "earnings story root moved during the bounded staging call"
        _record_root_status(destination, current=False, reason=reason)
        raise EarningsStoryIngressError(reason) from exc
    _record_root_status(destination, current=True)
    summary = json.loads((destination / "_run_summary.json").read_text(encoding="utf-8"))

    result = {
        "schema": "earnings.press_stage_result/v1",
        "operation": "stage_only",
        "allow_emit": False,
        "generation_id": generation_id,
        "packet_id": packet_id,
        "story_revision_id": story_revision_id,
        "admission": admission,
        "staging": summary,
    }
    return result


def _runner_destination() -> Path:
    runner_temp = os.environ.get("RUNNER_TEMP", "").strip()
    if not runner_temp:
        raise EarningsStoryIngressError("RUNNER_TEMP is required for isolated staging")
    return Path(runner_temp).resolve() / _STAGING_NAME


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Stage one exact audited earnings story packet.")
    parser.add_argument("--generation-id", required=True)
    parser.add_argument("--packet-id", required=True)
    parser.add_argument("--story-revision-id", required=True)
    args = parser.parse_args(argv)

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    destination = _runner_destination()
    try:
        result = stage_exact_current_story(
            generation_id=args.generation_id,
            packet_id=args.packet_id,
            story_revision_id=args.story_revision_id,
            staging_dir=destination,
        )
    except Exception as exc:  # noqa: BLE001 - CLI is a fail-closed workflow boundary.
        destination.mkdir(parents=True, exist_ok=True)
        failure = {
            "schema": "earnings.press_stage_failure/v1",
            "status": "failed",
            "operation": "stage_only",
            "allow_emit": False,
            "generation_id": args.generation_id,
            "packet_id": args.packet_id,
            "story_revision_id": args.story_revision_id,
            "error_type": type(exc).__name__,
            "error": str(exc),
        }
        (destination / "_ingress_failure.json").write_text(
            json.dumps(failure, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n",
            encoding="utf-8",
        )
        print(f"::error title=earnings_story_press_stage::{type(exc).__name__}: {exc}", flush=True)
        return 1
    print(json.dumps(result, ensure_ascii=False, sort_keys=True, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
