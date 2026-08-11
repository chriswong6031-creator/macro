#!/usr/bin/env python3
"""Emit a pinned-generation options/Market Memory context coverage receipt."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import stat
import sys
from datetime import datetime, timezone
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT))

from engine import options_market_memory_context as context_bridge
from engine import options_signal_episode
from engine.neuralweb import market_memory_pit, market_memory_trusted

_MAX_LEDGER_BYTES = 48 * 1024 * 1024
_MAX_CONFIG_BYTES = 32 * 1024


class AuditInputError(RuntimeError):
    """An exact source artifact could not be read or authenticated."""


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
    if len(rows) > 25_000:
        raise AuditInputError(f"owner ledger exceeds the row boundary: {path}")
    return body, rows


def build_live_audit(
    *,
    repository_root: Path,
    w1a_store_root: Path,
    trusted_store_root: Path,
    config_path: Path,
) -> dict:
    root = repository_root.expanduser().resolve()
    if root.is_symlink() or not root.is_dir():
        raise AuditInputError("repository root must be an existing directory")
    data_root = root / "data" / "options_signal_episode"
    episode_path = data_root / "episodes.jsonl"
    campaign_path = data_root / "campaigns.jsonl"
    h60_path = data_root / "outcomes_h60.jsonl"

    episode_body, episodes = _ledger(episode_path)
    campaign_body, campaigns = _ledger(campaign_path)
    h60_body, h60_outcomes = _ledger(h60_path)
    config_body = _stable_read(config_path, maximum=_MAX_CONFIG_BYTES)

    try:
        for row in episodes:
            options_signal_episode.validate_episode(row)
        expected_campaigns, _pending = options_signal_episode.derive_campaigns(
            episodes, h60_outcomes
        )
    except options_signal_episode.ContractError as exc:
        raise AuditInputError(
            "options owner ledgers fail their frozen contracts"
        ) from exc
    if campaigns != expected_campaigns:
        raise AuditInputError("campaign ledger differs from exact owner replay")

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
    references.extend(
        context_bridge.resolve_campaign_context_reference(
            row,
            episodes=episodes,
            h60_outcomes=h60_outcomes,
            reader=pinned,
            canary_identity=canary_identity,
        )
        for row in campaigns
    )
    references.sort(key=lambda row: (row["owner"]["schema"], row["owner"]["id"]))

    sources = [
        _artifact(campaign_path, campaign_body, root=root, rows=len(campaigns)),
        _artifact(episode_path, episode_body, root=root, rows=len(episodes)),
        _artifact(h60_path, h60_body, root=root, rows=len(h60_outcomes)),
        _artifact(config_path, config_body, root=root, rows=1),
    ]
    sources.sort(key=lambda row: str(row["path"]))
    audited_at = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    return context_bridge.build_audit_receipt(
        references=references,
        source_artifacts=sources,
        context_generations=pinned.generation_receipts(),
        audited_at=audited_at,
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
        audit = build_live_audit(
            repository_root=repository_root,
            w1a_store_root=w1a_root,
            trusted_store_root=trusted_root,
            config_path=config_path,
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
            audit,
            allow_nan=False,
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
