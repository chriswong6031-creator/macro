"""Immutable SEC raw-source collector for Fundamental Forensics.

The public SEC Company Facts and Submissions endpoints are the source plane.
Responses are stored content-addressed and gzip-compressed; a repeated response
reuses the same object and a changed response creates a new immutable object.
Nothing in this module normalizes or interprets facts.

The local default is intentionally gitignored.  Set ``--raw-root`` to a mounted
R2/B2/e2 sync directory today; an S3-compatible object adapter can be added once
bucket credentials are provisioned without changing the receipt format.
"""
from __future__ import annotations

import argparse
import gzip
import hashlib
import io
import json
import logging
import os
import time
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping

import pandas as pd
import requests
import yaml

from lib import config

log = logging.getLogger("edgar_forensics")
SEC_DATA = "https://data.sec.gov"


class SecResponseTooLarge(RuntimeError):
    """A SEC response exceeded the caller's explicit bounded-ingest budget."""


@dataclass(frozen=True)
class RetrievalReceipt:
    schema: str
    cik: str
    endpoint: str
    url: str
    retrieved_at: str
    sha256: str
    bytes: int
    object_path: str
    http_etag: str | None
    http_last_modified: str | None


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _canonical_cik(cik: int | str) -> str:
    digits = "".join(ch for ch in str(cik) if ch.isdigit())
    if not digits:
        raise ValueError(f"invalid CIK: {cik!r}")
    return f"{int(digits):010d}"


def endpoint_url(cik: int | str, endpoint: str) -> str:
    cik10 = _canonical_cik(cik)
    if endpoint == "companyfacts":
        return f"{SEC_DATA}/api/xbrl/companyfacts/CIK{cik10}.json"
    if endpoint == "submissions":
        return f"{SEC_DATA}/submissions/CIK{cik10}.json"
    raise ValueError(f"unsupported endpoint: {endpoint}")


def _temp_sibling(path: Path) -> Path:
    return path.with_name(f".{path.name}.{os.getpid()}.{time.time_ns()}.tmp")


def _sync_parent(path: Path) -> None:
    """Best-effort directory fsync after rename; unsupported filesystems degrade."""
    try:
        fd = os.open(path.parent, os.O_RDONLY)
        try:
            os.fsync(fd)
        finally:
            os.close(fd)
    except OSError:
        pass


def _atomic_write(path: Path, content: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = _temp_sibling(path)
    try:
        with temp.open("xb") as fh:
            fh.write(content)
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(temp, path)
        _sync_parent(path)
    finally:
        temp.unlink(missing_ok=True)


def _gzip_bytes(content: bytes) -> bytes:
    buffer = io.BytesIO()
    with gzip.GzipFile(filename="", fileobj=buffer, mode="wb", compresslevel=9, mtime=0) as fh:
        fh.write(content)
    return buffer.getvalue()


def _object_matches(path: Path, content: bytes) -> bool:
    try:
        with gzip.open(path, "rb") as fh:
            decoded = fh.read(len(content) + 1)
        return decoded == content
    except (OSError, EOFError):
        return False


def _receipt_matches(path: Path, receipt: RetrievalReceipt) -> bool:
    """Validate immutable identity fields while preserving first-seen metadata."""
    try:
        doc = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        return False
    return isinstance(doc, dict) and all(
        doc.get(field) == getattr(receipt, field)
        for field in ("schema", "cik", "endpoint", "url", "sha256", "bytes", "object_path")
    )


def persist_response(
    raw_root: Path,
    *,
    cik: int | str,
    endpoint: str,
    url: str,
    content: bytes,
    retrieved_at: str,
    etag: str | None = None,
    last_modified: str | None = None,
) -> RetrievalReceipt:
    """Write one content-addressed immutable object plus its canonical receipt."""
    cik10 = _canonical_cik(cik)
    digest = hashlib.sha256(content).hexdigest()
    rel = Path(cik10) / endpoint / f"{digest}.json.gz"
    target = raw_root / rel
    target.parent.mkdir(parents=True, exist_ok=True)
    # An interrupted prior write can leave a hash-named file that merely exists.
    # Validate its decompressed bytes before reuse and atomically repair it when
    # corrupt; existence alone is never proof of immutability.
    if not _object_matches(target, content):
        _atomic_write(target, _gzip_bytes(content))
        if not _object_matches(target, content):  # pragma: no cover - storage corruption
            raise OSError(f"failed to verify immutable SEC object: {target}")
    receipt = RetrievalReceipt(
        schema="fundamental_forensics_retrieval.v1",
        cik=cik10,
        endpoint=endpoint,
        url=url,
        retrieved_at=retrieved_at,
        sha256=digest,
        bytes=len(content),
        object_path=rel.as_posix(),
        http_etag=etag,
        http_last_modified=last_modified,
    )
    receipt_path = target.with_suffix(".receipt.json")
    encoded_receipt = (
        json.dumps(asdict(receipt), sort_keys=True, separators=(",", ":")) + "\n"
    ).encode("utf-8")
    if not _receipt_matches(receipt_path, receipt):
        _atomic_write(receipt_path, encoded_receipt)
    latest = target.parent / "latest.json"
    # Pointer commits last: a reader can observe the previous complete receipt or
    # the new complete receipt, never a pointer to a partial object/sidecar.
    _atomic_write(latest, encoded_receipt)
    return receipt


class SecForensicsCollector:
    """Polite SEC client with bounded retries and immutable persistence."""

    def __init__(
        self,
        raw_root: Path,
        *,
        user_agent: str,
        min_interval_seconds: float = 0.12,
        timeout_seconds: float = 30.0,
        max_response_bytes: int | None = None,
        session: requests.Session | None = None,
    ) -> None:
        if "@" not in user_agent:
            raise ValueError("SEC user agent must identify an application and contact email")
        self.raw_root = raw_root
        self.user_agent = user_agent
        self.min_interval_seconds = max(0.1, min_interval_seconds)
        self.timeout_seconds = timeout_seconds
        self.max_response_bytes = _byte_limit(max_response_bytes, field="max_response_bytes")
        self.session = session or requests.Session()
        self._last_request_at = 0.0

    def _pace(self) -> None:
        wait = self.min_interval_seconds - (time.monotonic() - self._last_request_at)
        if wait > 0:
            time.sleep(wait)

    def fetch(
        self,
        cik: int | str,
        endpoint: str,
        *,
        retrieved_at: str | None = None,
        max_response_bytes: int | None = None,
    ) -> RetrievalReceipt:
        url = endpoint_url(cik, endpoint)
        limit = self.max_response_bytes
        if max_response_bytes is not None:
            limit = _byte_limit(max_response_bytes, field="max_response_bytes")
        last_error: Exception | None = None
        for attempt in range(4):
            self._pace()
            try:
                response = self.session.get(
                    url,
                    headers={"User-Agent": self.user_agent, "Accept-Encoding": "gzip, deflate"},
                    timeout=self.timeout_seconds,
                )
                self._last_request_at = time.monotonic()
                if response.status_code in (429, 500, 502, 503, 504):
                    raise requests.HTTPError(f"SEC transient HTTP {response.status_code}")
                response.raise_for_status()
                _reject_declared_oversize(response.headers, limit, url=url)
                content = response.content
                if not isinstance(content, bytes):
                    raise RuntimeError(f"SEC response body is not bytes for {url}")
                if limit is not None and len(content) > limit:
                    raise SecResponseTooLarge(
                        f"SEC response exceeds bounded ingest limit ({len(content)} > {limit}) for {url}"
                    )
                # Reject non-JSON bodies before they enter the immutable source plane.
                json.loads(content)
                return persist_response(
                    self.raw_root,
                    cik=cik,
                    endpoint=endpoint,
                    url=url,
                    content=content,
                    retrieved_at=retrieved_at or _utc_now(),
                    etag=response.headers.get("ETag"),
                    last_modified=response.headers.get("Last-Modified"),
                )
            except SecResponseTooLarge:
                raise
            except (requests.RequestException, json.JSONDecodeError) as exc:
                last_error = exc
                if attempt < 3:
                    time.sleep(min(2 ** attempt, 4))
        raise RuntimeError(f"SEC fetch failed after retries for {url}: {last_error}")

    def fetch_company(self, cik: int | str, *, retrieved_at: str | None = None) -> list[RetrievalReceipt]:
        return [self.fetch(cik, endpoint, retrieved_at=retrieved_at) for endpoint in ("companyfacts", "submissions")]


def _byte_limit(value: int | None, *, field: str) -> int | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise ValueError(f"{field} must be a positive integer or None")
    return value


def _reject_declared_oversize(headers: Any, limit: int | None, *, url: str) -> None:
    """Fail before persistence when SEC provides an honest oversized length header."""
    if limit is None or not isinstance(headers, Mapping):
        return
    raw = headers.get("Content-Length") or headers.get("content-length")
    if raw is None:
        return
    try:
        declared = int(str(raw).strip())
    except (TypeError, ValueError):
        return
    if declared < 0:
        raise SecResponseTooLarge(f"SEC response has invalid Content-Length for {url}")
    if declared > limit:
        raise SecResponseTooLarge(
            f"SEC response exceeds bounded ingest limit ({declared} > {limit}) for {url}"
        )


def _user_agent(root: Path) -> str:
    cfg = yaml.safe_load((root / "config.yml").read_text(encoding="utf-8")) or {}
    user_agent = str(((cfg.get("edgar") or {}).get("user_agent") or "")).strip()
    if not user_agent:
        raise ValueError("config.yml edgar.user_agent is required")
    return user_agent


def _cik_map(root: Path) -> dict[str, int]:
    path = root / "data" / "edgar" / "fundamentals.parquet"
    frame = pd.read_parquet(path, columns=["cik"])
    return {
        str(ticker).upper(): int(row["cik"])
        for ticker, row in frame.iterrows()
        if pd.notna(row.get("cik"))
    }


def collect_tickers(
    root: Path,
    tickers: Iterable[str],
    *,
    raw_root: Path | None = None,
    retrieved_at: str | None = None,
) -> list[RetrievalReceipt]:
    mapping = _cik_map(root)
    collector = SecForensicsCollector(
        raw_root or root / "data" / "fundamental_forensics" / "raw",
        user_agent=_user_agent(root),
    )
    receipts: list[RetrievalReceipt] = []
    for ticker in dict.fromkeys(str(t).upper() for t in tickers):
        if ticker not in mapping:
            log.warning("no CIK for %s; skipped", ticker)
            continue
        receipts.extend(collector.fetch_company(mapping[ticker], retrieved_at=retrieved_at))
        log.info("stored immutable SEC sources for %s", ticker)
    return receipts


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("tickers", nargs="+", help="US ticker symbols")
    parser.add_argument("--root", type=Path, default=config.ROOT)
    parser.add_argument("--raw-root", type=Path, default=None)
    args = parser.parse_args(argv)
    receipts = collect_tickers(args.root.resolve(), args.tickers, raw_root=args.raw_root)
    print(json.dumps([asdict(item) for item in receipts], indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
