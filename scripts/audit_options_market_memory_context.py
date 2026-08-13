#!/usr/bin/env python3
"""Emit a pinned-generation options/Market Memory context coverage receipt."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import stat
import subprocess
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT))

from engine import options_market_memory_context as context_bridge  # noqa: E402
from engine import options_market_memory_receipt_store as receipt_store  # noqa: E402
from engine import options_signal_episode  # noqa: E402
from engine.neuralweb import market_memory_pit  # noqa: E402
from engine.neuralweb import market_memory_trusted  # noqa: E402

# These two bounds size the auditor's own READ of the owner ledgers, and nothing
# else.  `engine/neuralweb/market_memory_production_records.py:55,74-76` sizes this
# exact artifact -- `SOURCE_ARTIFACT_REL = "data/options_signal_episode/
# episodes.jsonl"` -- at `MAX_SOURCE_ROWS = 25_000` and `MAX_SOURCE_BYTES = 48 MiB`,
# so an 8 MiB / 4,096-row read bound here had the repository contradicting its own
# sizing of one file.  Worse, it was the boundary that would raise FIRST: at row
# 4,097 the audit would die on `owner ledger exceeds the row boundary`, taking the
# nightly `macro-market-memory-context` unit down while naming a limit that is not
# the real one and is trivially editable, sending the diagnosis to the wrong wall.
#
# The binding ceiling is NOT here and cannot be moved from here.  It is the pinned
# `_MAX_REFERENCES = 4_096` in `engine/options_market_memory_context.py`, which caps
# the emitted reference set, every source artifact's `record_count`, and the
# campaign-replay corpora, plus the matching `reference_count` bound on the receipt
# HEAD in `engine/options_market_memory_receipt_store.py`.  Both files are
# byte-pinned by `research/options_estate/
# sparse_selector_preregistration_receipt_v1.json`, so editing either one is a
# preregistration act, not a buffer change.  Crossing 4,096 owner rows therefore
# requires the preregistration v2 chartered in `research/options_estate/
# OPTIONS_CONTEXT_AUDIT_LEDGER_BOUND_ADJUDICATION_2026-08-13.md`.
#
# Raising these constants buys no headroom.  It only makes the eventual failure
# land on the wall that actually owns it, and it stops this file from failing
# early and misleadingly.  The early warning for the real ceiling lives in
# `tests/test_market_memory_trusted.py::
# test_options_owner_ledgers_stay_clear_of_the_pinned_reference_ceiling`.
_MAX_LEDGER_BYTES = 48 * 1024 * 1024
_MAX_LEDGER_ROWS = 25_000
_MAX_CONFIG_BYTES = 32 * 1024
_FROZEN_LEGACY_CAMPAIGN_ROWS = 8
_FROZEN_LEGACY_CAMPAIGN_BYTES = 10_492
_FROZEN_LEGACY_CAMPAIGN_SHA256 = (
    "db326f5c772ab417c43b8579ad50abb0434916922bda3a13c2da5b8303813910"
)
_COMMIT = re.compile(r"[a-f0-9]{40,64}\Z")


class AuditInputError(RuntimeError):
    """An exact source artifact could not be read or authenticated."""


@dataclass(frozen=True)
class LiveAuditBundle:
    """The complete reference set and its authenticated compact receipt."""

    deployed_commit: str | None
    references: tuple[dict, ...]
    audit: dict


def _repository_commit(root: Path) -> str:
    try:
        result = subprocess.run(
            ["git", "-C", str(root), "rev-parse", "HEAD"],
            check=True,
            capture_output=True,
            text=True,
            timeout=15,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        raise AuditInputError(
            "cannot bind the options receipt to the deployed checkout"
        ) from exc
    commit = result.stdout.strip()
    if not _COMMIT.fullmatch(commit):
        raise AuditInputError("deployed checkout commit is malformed")
    return commit


def _tracked_bytes(root: Path, commit: str, relative_path: str) -> bytes:
    try:
        result = subprocess.run(
            ["git", "-C", str(root), "show", f"{commit}:{relative_path}"],
            check=True,
            capture_output=True,
            timeout=15,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        raise AuditInputError(
            f"cannot bind {relative_path} to the deployed checkout"
        ) from exc
    return result.stdout


def _stable_read(path: Path, *, maximum: int) -> bytes:
    try:
        metadata = path.lstat()
    except OSError as exc:
        raise AuditInputError(
            f"required source artifact is unavailable: {path}"
        ) from exc
    if stat.S_ISLNK(metadata.st_mode) or not stat.S_ISREG(metadata.st_mode):
        raise AuditInputError(f"source artifact must be a regular non-symlink: {path}")
    if metadata.st_size <= 0 or metadata.st_size > maximum:
        raise AuditInputError(f"source artifact exceeds its byte boundary: {path}")
    flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(path, flags)
    except OSError as exc:
        raise AuditInputError(
            f"source artifact cannot be opened safely: {path}"
        ) from exc
    try:
        before = os.fstat(descriptor)
        body = bytearray()
        while len(body) <= maximum:
            chunk = os.read(descriptor, min(65_536, maximum + 1 - len(body)))
            if not chunk:
                break
            body.extend(chunk)
        after = os.fstat(descriptor)
    finally:
        os.close(descriptor)
    if (
        before.st_ino != after.st_ino
        or before.st_size != after.st_size
        or before.st_mtime_ns != after.st_mtime_ns
        or len(body) != after.st_size
        or len(body) > maximum
    ):
        raise AuditInputError(f"source artifact changed during stable read: {path}")
    return bytes(body)


def _artifact(path: Path, body: bytes, *, root: Path, rows: int) -> dict[str, object]:
    try:
        relative = path.resolve().relative_to(root).as_posix()
    except ValueError as exc:
        raise AuditInputError("source artifact escaped repository root") from exc
    return {
        "path": relative,
        "sha256": hashlib.sha256(body).hexdigest(),
        "bytes": len(body),
        "record_count": rows,
    }


def _ledger(path: Path) -> tuple[bytes, list[dict]]:
    body = _stable_read(path, maximum=_MAX_LEDGER_BYTES)
    try:
        rows = options_signal_episode._decode_jsonl(body, path)
    except options_signal_episode.ContractError as exc:
        raise AuditInputError(f"owner ledger is malformed: {path}") from exc
    if len(rows) > _MAX_LEDGER_ROWS:
        raise AuditInputError(f"owner ledger exceeds the row boundary: {path}")
    return body, rows


def _validate_frozen_legacy_campaign_ledger(
    *,
    body: bytes,
    campaigns: list[dict],
    episodes: list[dict],
    h60_outcomes: list[dict],
) -> None:
    """Authenticate the retired v1 bytes without treating future sources as v1 rows."""
    if (
        len(campaigns) != _FROZEN_LEGACY_CAMPAIGN_ROWS
        or len(body) != _FROZEN_LEGACY_CAMPAIGN_BYTES
        or hashlib.sha256(body).hexdigest() != _FROZEN_LEGACY_CAMPAIGN_SHA256
    ):
        raise AuditInputError(
            "legacy campaign ledger differs from the frozen eight-row corpus"
        )
    try:
        for campaign in campaigns:
            options_signal_episode.validate_campaign_against_sources(
                campaign, episodes, h60_outcomes
            )
    except options_signal_episode.ContractError as exc:
        raise AuditInputError(
            "frozen legacy campaign row differs from its historical source prefix"
        ) from exc


def _closed_campaign_era_sources(
    episodes: list[dict], h60_outcomes: list[dict]
) -> tuple[list[dict], list[dict]]:
    """The episode/outcome slice the RETIRED v1 campaign corpus was derived from.

    `data/options_signal_episode/campaigns.jsonl` is byte-frozen at its eight
    retrospective rows and no lane appends to it -- `tests/test_options_signal_
    campaign.py` pins the nightly episode builder out of `derive_campaigns` and
    `append_campaigns` entirely -- while `episodes.jsonl` grows every night.
    `resolve_campaign_context_references` requires the corpus to EQUAL its replay,
    so replaying a closed corpus against the whole live ledger was a scheduled
    failure rather than a contract: the 2026-08-13 durable checkpoint
    (e9738279704) appended 822 episodes and with them twelve newly qualifying
    groups the frozen corpus by construction cannot hold, and this auditor began
    exiting non-zero on a clean checkout with "campaign corpus differs from exact
    episode/outcome replay".

    A replay of a closed cohort is only closed if its INPUTS are, so cut the inputs
    at the same instant the cohort is: `CAMPAIGN_RULE_FROZEN_AT`, the boundary
    `derive_campaigns` itself uses to stamp `evidence_phase`, and therefore exactly
    the line between the corpus's `retrospective_discovery` rows and everything the
    ledger learned afterwards.  The equality that authenticates the corpus is
    untouched -- nothing omitted, nothing extra, same rows in the same order -- and
    the frozen-ledger authenticator above still replays every committed row against
    the FULL live sources, so a v1 row that stopped being reproducible from today's
    ledger still fails there.

    Truncation can only ever REMOVE groups: a qualifying prefix is the first one to
    cross the premium threshold, so dropping later episodes cannot promote an
    earlier prefix.  Outcomes are cut to the retained episodes because
    `derive_campaigns` refuses an outcome whose episode it cannot see.
    """

    frozen = options_signal_episode._as_utc(
        options_signal_episode.CAMPAIGN_RULE_FROZEN_AT, "campaign rule frozen_at"
    )
    closed_episodes = [
        row
        for row in episodes
        if options_signal_episode._as_utc(
            row.get("available_at"), "episode available_at"
        )
        < frozen
    ]
    retained = {row["episode_id"] for row in closed_episodes}
    closed_h60_outcomes = [
        row for row in h60_outcomes if row.get("episode_id") in retained
    ]
    return closed_episodes, closed_h60_outcomes


def build_live_audit_bundle(
    *,
    repository_root: Path,
    w1a_store_root: Path,
    trusted_store_root: Path,
    config_path: Path,
    expected_deployed_commit: str | None = None,
) -> LiveAuditBundle:
    root = repository_root.expanduser().resolve()
    if root.is_symlink() or not root.is_dir():
        raise AuditInputError("repository root must be an existing directory")
    if expected_deployed_commit is not None:
        if not _COMMIT.fullmatch(expected_deployed_commit):
            raise AuditInputError("expected deployed checkout commit is malformed")
        if _repository_commit(root) != expected_deployed_commit:
            raise AuditInputError("deployed checkout differs before options audit")
    data_root = root / "data" / "options_signal_episode"
    episode_path = data_root / "episodes.jsonl"
    campaign_path = data_root / "campaigns.jsonl"
    h60_path = data_root / "outcomes_h60.jsonl"

    episode_body, episodes = _ledger(episode_path)
    campaign_body, campaigns = _ledger(campaign_path)
    h60_body, h60_outcomes = _ledger(h60_path)
    config_body = _stable_read(config_path, maximum=_MAX_CONFIG_BYTES)

    bodies = {
        campaign_path: campaign_body,
        episode_path: episode_body,
        h60_path: h60_body,
        config_path: config_body,
    }
    if expected_deployed_commit is not None:
        for path, body in bodies.items():
            try:
                relative = path.resolve().relative_to(root).as_posix()
            except ValueError as exc:
                raise AuditInputError(
                    "options audit source escaped the deployed checkout"
                ) from exc
            if _tracked_bytes(root, expected_deployed_commit, relative) != body:
                raise AuditInputError(
                    f"{relative} bytes are not owned by the deployed checkout"
                )

    try:
        for row in episodes:
            options_signal_episode.validate_episode(row)
    except options_signal_episode.ContractError as exc:
        raise AuditInputError(
            "options owner ledgers fail their frozen contracts"
        ) from exc
    _validate_frozen_legacy_campaign_ledger(
        body=campaign_body,
        campaigns=campaigns,
        episodes=episodes,
        h60_outcomes=h60_outcomes,
    )

    canary_identity = context_bridge.load_canary_identity_snapshot(config_path)
    if canary_identity.config_sha256 != hashlib.sha256(config_body).hexdigest():
        raise AuditInputError(
            "canary config changed between stable read and validation"
        )

    composite = market_memory_trusted.CompositeAsKnownAtReader(
        w1a_store_root, trusted_store_root
    )
    pinned = context_bridge.PinnedCompositeAsKnownAtReader(composite)
    references = [
        context_bridge.resolve_episode_context_reference(
            row, reader=pinned, canary_identity=canary_identity
        )
        for row in episodes
    ]
    closed_episodes, closed_h60_outcomes = _closed_campaign_era_sources(
        episodes, h60_outcomes
    )
    references.extend(
        context_bridge.resolve_campaign_context_references(
            campaigns,
            episodes=closed_episodes,
            h60_outcomes=closed_h60_outcomes,
            reader=pinned,
            canary_identity=canary_identity,
        )
    )
    references.sort(key=lambda row: (row["owner"]["schema"], row["owner"]["id"]))

    sources = [
        _artifact(campaign_path, campaign_body, root=root, rows=len(campaigns)),
        _artifact(episode_path, episode_body, root=root, rows=len(episodes)),
        _artifact(h60_path, h60_body, root=root, rows=len(h60_outcomes)),
        _artifact(config_path, config_body, root=root, rows=1),
    ]
    sources.sort(key=lambda row: str(row["path"]))
    if (
        expected_deployed_commit is not None
        and _repository_commit(root) != expected_deployed_commit
    ):
        raise AuditInputError("deployed checkout changed during options audit")
    audited_at = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    audit = context_bridge.build_audit_receipt(
        references=references,
        source_artifacts=sources,
        context_generations=pinned.generation_receipts(),
        audited_at=audited_at,
    )
    return LiveAuditBundle(
        deployed_commit=expected_deployed_commit,
        references=tuple(references),
        audit=audit,
    )


def build_live_audit(
    *,
    repository_root: Path,
    w1a_store_root: Path,
    trusted_store_root: Path,
    config_path: Path,
) -> dict:
    """Build an in-memory audit for tests and read-only operator inspection."""

    return build_live_audit_bundle(
        repository_root=repository_root,
        w1a_store_root=w1a_store_root,
        trusted_store_root=trusted_store_root,
        config_path=config_path,
    ).audit


def publish_live_audit(
    *,
    repository_root: Path,
    w1a_store_root: Path,
    trusted_store_root: Path,
    config_path: Path,
    publication_root: Path,
    expected_deployed_commit: str | None = None,
) -> dict:
    """Publish a complete private receipt bound to exact deployed Git bytes."""

    root = repository_root.expanduser().resolve()
    deployed_commit = expected_deployed_commit or _repository_commit(root)
    bundle = build_live_audit_bundle(
        repository_root=root,
        w1a_store_root=w1a_store_root,
        trusted_store_root=trusted_store_root,
        config_path=config_path,
        expected_deployed_commit=deployed_commit,
    )
    if _repository_commit(root) != deployed_commit:
        raise AuditInputError("deployed checkout changed before receipt publication")
    return receipt_store.publish_receipt_set(
        publication_root,
        deployed_commit=deployed_commit,
        references=bundle.references,
        audit=bundle.audit,
        repository_root=root,
    )


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Audit exact requested-as-of Market Memory coverage for the options "
            "episode/campaign research ledgers."
        )
    )
    parser.add_argument("--repository-root", type=Path, default=Path.cwd())
    parser.add_argument("--w1a-store-root", type=Path)
    parser.add_argument("--trusted-store-root", type=Path)
    parser.add_argument("--config-path", type=Path)
    output = parser.add_mutually_exclusive_group(required=True)
    output.add_argument(
        "--publish-root",
        type=Path,
        help="private durable receipt root",
    )
    output.add_argument(
        "--stdout-only",
        action="store_true",
        help="explicitly inspect a compact receipt without durable publication",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    repository_root = args.repository_root.expanduser().resolve()
    w1a_root = args.w1a_store_root or market_memory_pit.default_store_root(
        repository_root
    )
    trusted_root = (
        args.trusted_store_root
        or market_memory_trusted.default_trusted_store_root(repository_root)
    )
    config_path = args.config_path or (
        repository_root / "config" / "market_memory_canary.v1.json"
    )
    try:
        if args.publish_root is None:
            result = build_live_audit(
                repository_root=repository_root,
                w1a_store_root=w1a_root,
                trusted_store_root=trusted_root,
                config_path=config_path,
            )
        else:
            result = publish_live_audit(
                repository_root=repository_root,
                w1a_store_root=w1a_root,
                trusted_store_root=trusted_root,
                config_path=config_path,
                publication_root=args.publish_root,
            )
    except (
        AuditInputError,
        options_signal_episode.ContractError,
        context_bridge.OptionsMarketMemoryContextError,
        market_memory_pit.MarketMemoryPITError,
    ) as exc:
        print(f"options-context-audit: {exc}", file=sys.stderr)
        return 2
    print(
        json.dumps(
            result,
            allow_nan=False,
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
