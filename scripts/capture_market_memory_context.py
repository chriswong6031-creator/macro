#!/usr/bin/env python3
"""Capture one exact Market Memory operational packet into the W1A store."""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT))

from engine.neuralweb import market_memory_options_episode_capture as options_capture
from engine.neuralweb.market_memory_pit import (
    MarketMemoryPITError,
    capture_context,
    default_store_root,
    load_packet_file,
)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Validate and create-once capture one contemporaneous "
            "market_memory.as_known_at.v1 operational packet."
        )
    )
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument(
        "--packet",
        type=Path,
        help="bounded strict-JSON packet file",
    )
    source.add_argument(
        "--options-request-jsonl",
        action="store_true",
        help=(
            "read a bounded prospective option-context request batch from stdin; "
            "reserved for the forced-command owner transport"
        ),
    )
    parser.add_argument(
        "--store",
        type=Path,
        default=None,
        help=(
            "dedicated immutable store root; defaults to the private local "
            "data path in development or /var/lib/macro-market-memory/public "
            "for the /opt/macro production checkout"
        ),
    )
    return parser


def _read_options_batch_stdin() -> bytes:
    body = b""
    while len(body) <= options_capture.MAX_BATCH_BYTES:
        chunk = os.read(
            sys.stdin.fileno(),
            min(65_536, options_capture.MAX_BATCH_BYTES + 1 - len(body)),
        )
        if not chunk:
            break
        body += chunk
    if not body or len(body) > options_capture.MAX_BATCH_BYTES:
        raise options_capture.OptionsEpisodeContextCaptureError(
            "capture request batch is empty or exceeds its byte bound"
        )
    if not body.endswith(b"\n"):
        raise options_capture.OptionsEpisodeContextCaptureError(
            "capture request batch has a torn final line"
        )
    return body


def capture_options_request_batch(
    body: bytes, *, store: Path
) -> tuple[list[dict], int]:
    """Validate and capture at most eight exact requests through the sole writer."""

    if (
        not body
        or len(body) > options_capture.MAX_BATCH_BYTES
        or not body.endswith(b"\n")
    ):
        raise options_capture.OptionsEpisodeContextCaptureError(
            "capture request batch shape is invalid"
        )
    lines = body.splitlines()
    if not lines or len(lines) > options_capture.MAX_BATCH_REQUESTS:
        raise options_capture.OptionsEpisodeContextCaptureError(
            "capture request batch count exceeds its bound"
        )
    responses: list[dict] = []
    rejected = 0
    for line in lines:
        request_id = "unknown"
        try:
            request = options_capture._strict_object(
                line,
                label="capture request",
                maximum=options_capture.MAX_REQUEST_BYTES,
            )
            candidate_id = request.get("request_id")
            if isinstance(candidate_id, str):
                request_id = candidate_id
            clean = options_capture.validate_capture_request(request)
            stored = capture_context(store, clean["packet"])
            responses.append(
                options_capture.response_from_stored_capture(
                    store, request=clean, stored=stored
                )
            )
        except (options_capture.OptionsEpisodeContextCaptureError, MarketMemoryPITError) as exc:
            rejected += 1
            print(
                f"options-context-capture rejected {request_id}: "
                f"{type(exc).__name__}: {exc}",
                file=sys.stderr,
            )
    return responses, rejected


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    store = args.store or default_store_root(_ROOT)
    if args.options_request_jsonl:
        try:
            responses, rejected = capture_options_request_batch(
                _read_options_batch_stdin(), store=store
            )
        except (options_capture.OptionsEpisodeContextCaptureError, MarketMemoryPITError) as exc:
            print(f"options-context-capture: {exc}", file=sys.stderr)
            return 2
        for response in responses:
            print(
                json.dumps(
                    response,
                    allow_nan=False,
                    ensure_ascii=False,
                    separators=(",", ":"),
                    sort_keys=True,
                )
            )
        return 2 if rejected else 0
    try:
        assert args.packet is not None
        packet = load_packet_file(args.packet)
        stored = capture_context(store, packet)
    except MarketMemoryPITError as exc:
        print(f"capture rejected: {exc}", file=sys.stderr)
        return 2
    receipt = stored.capture_receipt
    print(
        json.dumps(
            {
                "status": "captured",
                "capture_id": receipt["capture_id"],
                "query_id": receipt["query_id"],
                "context_id": receipt["context_id"],
                "packet_sha256": receipt["packet_sha256"],
            },
            allow_nan=False,
            separators=(",", ":"),
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
