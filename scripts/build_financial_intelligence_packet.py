#!/usr/bin/env python3
"""Build a hermetic financial_intelligence_packet.v1 from local fixtures.

Cutoffs have no default of \"now\". The filing-package ledger is the query
input. Company Facts / submissions files, when supplied, are hashed as
occurrence-inventory witnesses and are never converted into the query ledger.
"""
from __future__ import annotations

import argparse
import os
import sys
import tempfile
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from engine.fundamental_forensics.financial_intelligence_packet import (
    PACKET_SCHEMA,
    PacketQueryRequest,
    build_financial_intelligence_packet,
    canonical_packet_bytes,
    default_packet_periods,
    load_core_registry,
    load_filing_package_fixture,
    sha256_file,
)
from engine.fundamental_forensics.query import QueryPolicy


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--ledger",
        required=True,
        type=Path,
        help="Canonical synthetic filing-package raw-ledger fixture",
    )
    parser.add_argument(
        "--companyfacts-witness",
        type=Path,
        default=None,
        help="Optional Company Facts occurrence-inventory witness (hashed only)",
    )
    parser.add_argument(
        "--submissions-witness",
        type=Path,
        default=None,
        help="Optional submissions occurrence-inventory witness (hashed only)",
    )
    parser.add_argument(
        "--policy",
        required=True,
        choices=("as_reported", "latest_known_as_of", "latest_restated"),
    )
    parser.add_argument("--source-event-cutoff", required=True)
    parser.add_argument("--system-recorded-cutoff", required=True)
    parser.add_argument(
        "--metrics",
        default="revenue,accounts_receivable_net,gross_margin,CustomerCount",
        help="Comma-separated metric IDs",
    )
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--built-at", default=None)
    parser.add_argument("--repo-root", type=Path, default=_ROOT)
    return parser.parse_args(argv)


def _write_atomic(path: Path, payload: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=".fip_packet_")
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(payload)
        os.replace(tmp, path)
    except Exception:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    fixture = load_filing_package_fixture(args.ledger)
    metrics = tuple(item.strip() for item in args.metrics.split(",") if item.strip())
    packet = build_financial_intelligence_packet(
        entity=fixture.entity,
        ledger=fixture.ledger,
        filing_metadata=fixture.filing_metadata,
        query_request=PacketQueryRequest(
            policy=QueryPolicy(
                source_snapshot_at=args.source_event_cutoff,
                recorded_at=args.system_recorded_cutoff,
                selection=args.policy,
            ),
            metrics=metrics,
            periods=default_packet_periods(),
        ),
        metric_registry=load_core_registry(args.repo_root),
        built_at=args.built_at,
        input_digests={
            "filing_package_fixture_sha256": sha256_file(args.ledger),
            "companyfacts_witness_sha256": (
                sha256_file(args.companyfacts_witness)
                if args.companyfacts_witness is not None
                else None
            ),
            "submissions_witness_sha256": (
                sha256_file(args.submissions_witness)
                if args.submissions_witness is not None
                else None
            ),
        },
    )
    _write_atomic(args.output, canonical_packet_bytes(packet))
    coverage = packet["coverage"]
    print(
        " ".join(
            [
                f"schema={PACKET_SCHEMA}",
                f"packet_id={packet['packet_id']}",
                f"digest={packet['content_sha256']}",
                f"cells={len(packet['cells'])}",
                f"revisions={len(packet['revisions'])}",
                f"valued_metrics={len(coverage['valued_metrics'])}",
                f"unsupported_metrics={len(coverage['unsupported_metrics'])}",
            ]
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
