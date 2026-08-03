"""Publish staged member Earnings Wire payloads to the private Research Vault.

The staging directory must be outside the repository and is never committed.
Publication is fail-closed: missing private-store credentials, malformed staged
bytes, a read-back mismatch, or an invalid current-generation replay returns a
non-zero exit before the public workflow stages any HTML.
"""
from __future__ import annotations

import argparse
import json
import logging
from pathlib import Path

from engine.earnings_narrative.private_publication import (
    EarningsPrivatePublicationError,
    prepare_private_publication,
    publish_private_publication,
)
from engine.research_vault.r2_store import build_store


log = logging.getLogger("publish_earnings_private_store")


def publish(source_dir: Path, *, local_store: Path | None = None) -> dict:
    prepared = prepare_private_publication(source_dir)
    store = build_store(local_store)
    if store is None:
        raise EarningsPrivatePublicationError(
            "private Research Vault store is not configured; refusing a public-only publish"
        )
    pointer = publish_private_publication(store, prepared)
    return {
        "schema": "earnings.private_publish_result/v1",
        "status": "ready",
        "generation_id": pointer["generation_id"],
        "record_count": prepared.manifest["record_count"],
        "ticker_count": prepared.manifest["ticker_count"],
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Publish off-repo earnings member payloads to private R2.",
    )
    parser.add_argument("--source-dir", type=Path, required=True)
    parser.add_argument(
        "--local-store",
        type=Path,
        default=None,
        help="Hermetic local Research Vault root for tests/operator dry runs.",
    )
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    try:
        result = publish(args.source_dir, local_store=args.local_store)
    except (EarningsPrivatePublicationError, OSError, ValueError) as exc:
        log.error("earnings private publication failed: %s", exc)
        return 1
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
