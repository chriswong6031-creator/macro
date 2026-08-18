"""Run bounded rolling SEC 13F discovery and append-only catalog publication."""

from __future__ import annotations

import argparse
import os
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import requests

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from engine.institutional_census.models import (
    canonical_json_bytes,
    normalize_utc,
)
from engine.institutional_census.rolling import (
    MAX_ACCESSIONS,
    MAX_REQUESTS_PER_SECOND,
    MAX_SEC_RESPONSE_BYTES,
    PRODUCER_VERSION,
    ROLLING_CHECKPOINT_KEY,
    ROLLING_RECEIPT_SCHEMA,
    run_rolling_ingestion,
    safe_exception_fields,
)
from engine.institutional_census.storage import build_institutional_13f_store

DEFAULT_RECEIPT = Path("data/institutional_13f/receipts/rolling_latest.json")
DEFAULT_USER_AGENT = "MastermindX institutional census research longr2512@gmail.com"
HTTP_CHUNK_BYTES = 1024 * 1024


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _user_agent(explicit: str | None) -> str:
    value = (explicit or os.environ.get("SEC_USER_AGENT") or DEFAULT_USER_AGENT).strip()
    if not value or len(value) > 512:
        raise ValueError("SEC user agent must be a bounded non-empty value")
    return value


class _RequestsSecFetch:
    """Bounded streaming SEC fetch; request pacing is owned by ``PacedFetch``."""

    def __init__(self, *, user_agent: str) -> None:
        self._session = requests.Session()
        self._headers = {
            "User-Agent": user_agent,
            "Accept-Encoding": "gzip, deflate",
        }

    def __call__(self, url: str) -> bytes:
        parsed = urlparse(url)
        host = (parsed.hostname or "").lower()
        if (
            parsed.scheme != "https"
            or parsed.username is not None
            or parsed.password is not None
            or not (host == "sec.gov" or host.endswith(".sec.gov"))
        ):
            raise ValueError("rolling fetch is restricted to HTTPS SEC URLs")
        chunks: list[bytes] = []
        observed = 0
        announced_size: int | None = None
        with self._session.get(
            url,
            headers=self._headers,
            stream=True,
            timeout=(20, 180),
        ) as response:
            response.raise_for_status()
            announced = response.headers.get("Content-Length")
            if announced:
                try:
                    announced_size = int(announced)
                except ValueError as exc:
                    raise RuntimeError(
                        "SEC response Content-Length is invalid"
                    ) from exc
                if announced_size < 0 or announced_size > MAX_SEC_RESPONSE_BYTES:
                    raise RuntimeError(
                        "SEC response exceeds the SEC response byte ceiling"
                    )
            for chunk in response.iter_content(HTTP_CHUNK_BYTES):
                if not chunk:
                    continue
                if type(chunk) is not bytes:
                    raise RuntimeError("SEC response stream returned non-bytes")
                observed += len(chunk)
                if observed > MAX_SEC_RESPONSE_BYTES:
                    raise RuntimeError(
                        "SEC response exceeds the SEC response byte ceiling"
                    )
                chunks.append(chunk)
            # Content-Length describes the ENCODED (on-the-wire) body, so
            # comparing it to `observed` (the bytes iter_content yields,
            # already transparently decompressed by urllib3/requests) is only
            # valid for identity-encoded responses. A content-coded response
            # (e.g. gzip) is instead covered by the codec's own framing: a
            # truncated gzip stream fails to decode and iter_content raises.
            if (
                announced_size is not None
                and not response.headers.get("Content-Encoding")
                and observed != announced_size
            ):
                raise RuntimeError(
                    "SEC response truncated: "
                    f"Content-Length={announced_size}, received={observed}"
                )
        return b"".join(chunks)

    def close(self) -> None:
        self._session.close()


def _write_receipt(path: Path, receipt: dict[str, Any]) -> None:
    destination = path.expanduser().resolve()
    destination.parent.mkdir(parents=True, exist_ok=True)
    payload = canonical_json_bytes(receipt)
    temporary: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="wb",
            dir=destination.parent,
            prefix=f".{destination.name}.",
            suffix=".tmp",
            delete=False,
        ) as handle:
            temporary = Path(handle.name)
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, destination)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def _fatal_receipt(error: BaseException) -> dict[str, Any]:
    stamp = normalize_utc(_utc_now(), field="run clock")
    return {
        "schema": ROLLING_RECEIPT_SCHEMA,
        "status": "failed",
        "producer_version": PRODUCER_VERSION,
        "run_started_at": stamp,
        "source_cutoff_at": stamp,
        "run_completed_at": stamp,
        "discovery": {
            "atom": {
                "pages_fetched": 0,
                "entries": 0,
                "complete": False,
                "stop_reason": "fatal_error",
            },
            "master_index": {
                "supplied": False,
                "source": None,
                "sha256": None,
                "byte_length": 0,
                "entries": 0,
            },
            "merged_accessions": 0,
            "checkpoint_filtered_accessions": 0,
            "selected_accessions": 0,
            "backlog_accessions": 0,
        },
        "checkpoint": {
            "object_key": ROLLING_CHECKPOINT_KEY,
            "authority": "operational_discovery_only",
            "entries_before": 0,
            "entries_after": 0,
            "updated": False,
            "updated_at": None,
        },
        "counts": {
            "requests": 0,
            "sec_response_bytes": 0,
            "raw_receipts_published": 0,
            "new_filings_staged": 0,
            "new_filings_published": 0,
            "checkpoint_accessions_skipped": 0,
            "existing_accessions_skipped": 0,
            "periods_published": 0,
            "failures": 1,
        },
        "catalog_periods": [],
        "backlog": {"count": 0, "details": [], "details_truncated": False},
        "failures": {
            "count": 1,
            "details": [
                {
                    "stage": "runner",
                    **safe_exception_fields(error),
                }
            ],
            "details_truncated": False,
        },
    }


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Discover live SEC Form 13F filings, retain exact evidence, and append "
            "one catalog generation per report period."
        )
    )
    parser.add_argument(
        "--local-store",
        help=(
            "Explicit local object-store directory. If omitted, all dedicated "
            "INSTITUTIONAL_13F_R2_* variables are required; no generic fallback exists."
        ),
    )
    parser.add_argument(
        "--master-index",
        help="Optional supplied SEC daily/full master-index file or HTTPS sec.gov URL.",
    )
    parser.add_argument(
        "--max-accessions",
        type=int,
        default=MAX_ACCESSIONS,
        help=f"Hard processing cap, 1-{MAX_ACCESSIONS} (default: {MAX_ACCESSIONS}).",
    )
    parser.add_argument(
        "--requests-per-second",
        type=float,
        default=MAX_REQUESTS_PER_SECOND,
        help=(
            f"SEC request-start rate, above 0 and at most {MAX_REQUESTS_PER_SECOND:g}."
        ),
    )
    parser.add_argument(
        "--receipt",
        default=str(DEFAULT_RECEIPT),
        help=f"Atomic run-receipt destination (default: {DEFAULT_RECEIPT}).",
    )
    parser.add_argument(
        "--user-agent",
        help="SEC identity string; defaults to SEC_USER_AGENT then the project identity.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    receipt_path = Path(args.receipt)
    fetcher: _RequestsSecFetch | None = None
    try:
        store = build_institutional_13f_store(local_dir=args.local_store)
        fetcher = _RequestsSecFetch(user_agent=_user_agent(args.user_agent))
        receipt = run_rolling_ingestion(
            store=store,
            fetch=fetcher,
            master_index_source=args.master_index,
            max_accessions=args.max_accessions,
            requests_per_second=args.requests_per_second,
        )
    except Exception as exc:  # noqa: BLE001 - fatal receipt is an operator contract.
        receipt = _fatal_receipt(exc)
    finally:
        if fetcher is not None:
            fetcher.close()

    try:
        _write_receipt(receipt_path, receipt)
    except Exception as exc:  # noqa: BLE001 - receipt loss must be terminal and visible.
        safe = safe_exception_fields(exc)
        sys.stderr.write(f"rolling receipt write failed: {safe['error']}\n")
        return 1
    sys.stdout.buffer.write(canonical_json_bytes(receipt))
    return 0 if receipt.get("status") in {"ok", "no_changes", "bounded_backlog"} else 1


if __name__ == "__main__":
    raise SystemExit(main())
