#!/usr/bin/env python3
"""Publish the bounded SPY macro-regime Market Memory canary."""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from hashlib import sha256
from pathlib import Path
from typing import Any

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT))

from engine.neuralweb import (
    market_memory_identity,
    market_memory_projection,
    market_memory_trusted,
)

_COMMIT = re.compile(r"[a-f0-9]{40,64}\Z")


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
        raise market_memory_trusted.MarketMemoryTrustedCaptureError(
            "cannot bind the trusted capture to the deployed checkout"
        ) from exc
    commit = result.stdout.strip()
    if not _COMMIT.fullmatch(commit):
        raise market_memory_trusted.MarketMemoryTrustedCaptureError(
            "deployed checkout commit is malformed"
        )
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
        raise market_memory_trusted.MarketMemoryTrustedCaptureError(
            f"cannot bind {relative_path} to the deployed checkout"
        ) from exc
    return result.stdout


def project_current_context(
    repository_root: str | Path,
    *,
    public_store_root: str | Path | None = None,
    private_evidence_root: str | Path | None = None,
) -> dict[str, Any]:
    """Project and persist the sole current SPY canary from canonical paths."""

    root = Path(repository_root).expanduser().resolve()
    if not root.is_dir():
        raise market_memory_trusted.MarketMemoryTrustedCaptureError(
            "repository root is unavailable"
        )
    public = public_store_root or market_memory_trusted.default_trusted_store_root(root)
    private = (
        private_evidence_root
        or market_memory_trusted.default_private_evidence_root(root)
    )
    # Establish a complete authenticated empty generation first. Strict source
    # rejection can then fail closed without turning every unrelated W1A exact
    # lookup into an ambiguous missing-store error.
    market_memory_trusted.initialize_trusted_store(public)
    deployed_commit = _repository_commit(root)
    regime_path = root / "data" / "regime" / "latest.json"
    config_path = root / "config" / "market_memory_canary.v1.json"
    snapshot = market_memory_projection.build_macro_regime_snapshot(regime_path)
    # A second full stable read must match the exact projected source identity;
    # those bytes, not a later reopen, become the private immutable evidence.
    raw_body = market_memory_projection.read_verified_macro_regime_bytes(
        regime_path, snapshot
    )
    identity = market_memory_identity.build_current_spy_identity(
        config_path=config_path
    )
    if _repository_commit(root) != deployed_commit:
        raise market_memory_trusted.MarketMemoryTrustedCaptureError(
            "deployed checkout changed during trusted context projection"
        )
    if _tracked_bytes(root, deployed_commit, "data/regime/latest.json") != raw_body:
        raise market_memory_trusted.MarketMemoryTrustedCaptureError(
            "regime source bytes are not owned by the deployed checkout"
        )
    tracked_config = _tracked_bytes(
        root, deployed_commit, "config/market_memory_canary.v1.json"
    )
    if sha256(tracked_config).hexdigest() != identity.config_sha256:
        raise market_memory_trusted.MarketMemoryTrustedCaptureError(
            "canary identity config is not owned by the deployed checkout"
        )
    stored = market_memory_trusted.capture_trusted_regime_context(
        public,
        private,
        snapshot=snapshot,
        identity_evidence=identity,
        raw_source_body=raw_body,
        deployed_commit=deployed_commit,
    )
    receipt = stored.capture_receipt
    return {
        "schema": "market_memory.trusted_projection_result.v1",
        "context_id": stored.packet["context_id"],
        "capture_id": receipt["capture_id"],
        "query_id": receipt["query_id"],
        "packet_sha256": receipt["packet_sha256"],
        "snapshot_id": receipt["feature_snapshot"]["snapshot_id"],
        "event_time": stored.packet["clocks"]["event_time"],
        "as_known_at": stored.packet["clocks"]["as_known_at"],
        "observed_feature_ids": receipt["observed_feature_ids"],
        "missing_feature_count": len(receipt["missing_feature_ids"]),
        "authority": stored.packet["authority"],
    }


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Publish the current SPY macro-regime Market Memory canary"
    )
    parser.add_argument(
        "--repository-root",
        default=os.environ.get("MACRO_REPO", "/opt/macro"),
        help="reviewed Macro checkout containing the canonical source and config",
    )
    parser.add_argument(
        "--public-store-root",
        default=None,
        help="trusted public store override (tests/operators only)",
    )
    parser.add_argument(
        "--private-evidence-root",
        default=None,
        help="private evidence root override (tests/operators only)",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    result = project_current_context(
        args.repository_root,
        public_store_root=args.public_store_root,
        private_evidence_root=args.private_evidence_root,
    )
    print(json.dumps(result, sort_keys=True, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
