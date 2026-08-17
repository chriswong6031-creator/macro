"""Refresh and publish the sibling AAPL FY2026 Q3 event_workspace nest.

This is the production bridge from the merged E1 builder onto the existing
Company Intelligence publication lane.  It acquires the real SEC Exhibit 99.1
and the held Terminal transcript, builds ``event_workspace.v1`` with a
source-stable clock, writes the sibling nest, and publishes it under the
existing ``company_intelligence/`` R2 prefix.

It never writes the closed v1 teaser marker.  Source failure retains last-good
by refusing to move ``event_workspaces/manifest.json``.  Wall-clock of the
three-hour scheduler is not a data revision.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
from html import unescape as html_unescape
import json
import logging
import re
import sys
import time
from pathlib import Path
from typing import Any, Callable, Mapping
from urllib.parse import urljoin

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from engine.company_intelligence.event_workspace import (
    AAPL_ACCESSION,
    AAPL_CALL_DATE,
    AAPL_CIK,
    FLAGSHIP_EVENT_ID,
    LIVE_NARRATIVE_ALIAS,
    apple_registry,
    flagship_fiscal_period,
    write_workspace_generation,
)
from engine.company_intelligence.event_workspace_build import build_event_workspace
from engine.earnings_transcript_intake import (
    TranscriptRef,
    fetch_body,
    fetch_global_index,
    parse_global_index,
)
# Import closure reaches engine.earnings_narrative via event_id_adapter / public_wire.
from scripts.publish_company_intelligence_r2 import PUBLISH_CONFLICT, publish_event_workspaces

DEFAULT_TX_INDEX_URL = "https://app.mastermind-x.com/data/tx/index.json"

_DEFAULT_PUBLIC_ORIGIN = (
    "https://pub-f7ffb4441c5f4ad983ca56ec7c651c61.r2.dev/company_intelligence"
)


log = logging.getLogger("refresh_event_workspaces")

# Same fair-access User-Agent the EDGAR collectors already declare.
_SEC_UA = "macro-dashboard admin@macro-dashboard.example.com"
_SUBMISSIONS_URL = "https://data.sec.gov/submissions/CIK{cik:010d}.json"
_ARCHIVES = "https://www.sec.gov/Archives/edgar/data"
_PACE_S = 0.12
_RETRIES = 3
_TIMEOUT = 30
_EX99_TYPE = re.compile(r"^EX-99\.1(?:\b|$)", re.I)
_EX99_NAME = re.compile(r"ex[-_]?99[-_.]?1", re.I)


class RefreshError(RuntimeError):
    """A required source is unavailable; the sibling marker must not move."""


HttpGet = Callable[[str], tuple[int, bytes]]
FetchIndex = Callable[[str], object]
FetchBody = Callable[[str, TranscriptRef], dict[str, Any]]
PriorLoader = Callable[[], Mapping[str, Any] | None]
PublishFn = Callable[..., int]


def _iso_z(raw: object) -> str:
    text = str(raw or "").strip()
    if not text:
        raise RefreshError("filing acceptance_datetime is required as the source clock")
    parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def _http_get(url: str) -> tuple[int, bytes]:
    import requests  # local import keeps unit tests dependency-light

    last: Exception | None = None
    headers = {"User-Agent": _SEC_UA, "Accept-Encoding": "gzip, deflate"}
    for attempt in range(_RETRIES):
        try:
            response = requests.get(url, headers=headers, timeout=_TIMEOUT)
            if response.status_code in {429, 500, 502, 503, 504} and attempt < _RETRIES - 1:
                time.sleep(1.5 * (attempt + 1))
                continue
            return response.status_code, response.content
        except Exception as exc:  # noqa: BLE001
            last = exc
            if attempt < _RETRIES - 1:
                time.sleep(1.5 * (attempt + 1))
    raise RefreshError(f"SEC request failed: {url}: {last}")


def _parse_sgml_manifest(text: str) -> list[tuple[str, str]]:
    """[(TYPE, FILENAME)] from a filing's SGML ``-index-headers.html``.

    Same seam as ``collectors.edgar_8k._parse_sgml_manifest``: unescape first,
    then split on ``<DOCUMENT>``. The live EDGAR page is HTML-escaped SGML
    (``&lt;DOCUMENT&gt;``); splitting the raw bytes reports every exhibit as
    absent. ``index.json`` ``type`` is the directory-listing icon name and is
    not a document map.
    """
    out: list[tuple[str, str]] = []
    for block in html_unescape(text or "").split("<DOCUMENT>")[1:]:
        kind = re.search(r"<TYPE>([^<\r\n]+)", block)
        name = re.search(r"<FILENAME>([^<\r\n]+)", block)
        if kind and name:
            out.append((kind.group(1).strip().upper(), name.group(1).strip()))
    return out


def _select_exhibit_99_1(manifest: list[tuple[str, str]]) -> str | None:
    textish = [
        (kind, name)
        for kind, name in manifest
        if name.lower().endswith((".htm", ".html", ".txt"))
    ]
    exact = [name for kind, name in textish if kind == "EX-99.1"]
    if exact:
        return exact[0]
    prefixed = [name for kind, name in textish if _EX99_TYPE.match(kind)]
    if prefixed:
        return prefixed[0]
    hinted = [name for _, name in textish if _EX99_NAME.search(name)]
    return hinted[0] if hinted else None


def _parallel_row(block: Mapping[str, Any], accession: str) -> dict[str, Any] | None:
    accessions = block.get("accessionNumber") or []
    if not isinstance(accessions, list):
        return None
    for index, raw in enumerate(accessions):
        if str(raw or "") != accession:
            continue

        def at(field: str) -> str:
            values = block.get(field) or []
            if not isinstance(values, list) or index >= len(values):
                return ""
            return str(values[index] or "")

        return {
            "cik": AAPL_CIK,
            "accession": accession,
            "form": at("form") or "8-K",
            "filing_date": at("filingDate"),
            "acceptance_datetime": at("acceptanceDateTime"),
            "report_date": at("reportDate"),
            "primary_document": at("primaryDocument"),
            "items": at("items"),
        }
    return None


def acquire_flagship_filing(*, http_get: HttpGet = _http_get) -> dict[str, Any]:
    """Resolve the frozen AAPL accession through the submissions + SGML TYPE seam."""
    cik_int = int(AAPL_CIK)
    status, body = http_get(_SUBMISSIONS_URL.format(cik=cik_int))
    if status != 200:
        raise RefreshError(f"SEC submissions unavailable for CIK {AAPL_CIK}: HTTP {status}")
    try:
        submissions = json.loads(body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise RefreshError(f"SEC submissions JSON invalid: {exc}") from exc
    if not isinstance(submissions, dict):
        raise RefreshError("SEC submissions JSON must be an object")
    filings = submissions.get("filings") or {}
    if not isinstance(filings, dict):
        raise RefreshError("SEC submissions filings block invalid")
    row = _parallel_row(filings.get("recent") or {}, AAPL_ACCESSION)
    older = filings.get("files") or []
    if row is None and isinstance(older, list):
        for shard in older:
            fname = shard.get("name") if isinstance(shard, dict) else str(shard or "")
            if not fname:
                continue
            time.sleep(_PACE_S)
            shard_status, shard_body = http_get(
                urljoin("https://data.sec.gov/submissions/", str(fname))
            )
            if shard_status != 200:
                continue
            try:
                shard_payload = json.loads(shard_body.decode("utf-8"))
            except (UnicodeDecodeError, json.JSONDecodeError):
                continue
            if isinstance(shard_payload, dict):
                row = _parallel_row(shard_payload, AAPL_ACCESSION)
            if row is not None:
                break
    if row is None:
        raise RefreshError(
            f"accession {AAPL_ACCESSION} is not present in SEC submissions for CIK {AAPL_CIK}"
        )
    acc_nodash = AAPL_ACCESSION.replace("-", "")
    archive_base = f"{_ARCHIVES}/{cik_int}/{acc_nodash}"
    time.sleep(_PACE_S)
    header_status, header_body = http_get(f"{archive_base}/{AAPL_ACCESSION}-index-headers.html")
    if header_status != 200:
        raise RefreshError(
            f"SEC filing document map unavailable for {AAPL_ACCESSION}: HTTP {header_status}"
        )
    filename = _select_exhibit_99_1(_parse_sgml_manifest(header_body.decode("utf-8", errors="replace")))
    if not filename:
        raise RefreshError(f"EX-99.1 is absent from the SGML document map for {AAPL_ACCESSION}")
    exhibit_url = f"{archive_base}/{filename}"
    time.sleep(_PACE_S)
    exhibit_status, exhibit_body = http_get(exhibit_url)
    if exhibit_status != 200 or not exhibit_body.strip():
        raise RefreshError(f"Exhibit 99.1 unavailable at {exhibit_url}: HTTP {exhibit_status}")
    try:
        exhibit_text = exhibit_body.decode("utf-8")
    except UnicodeDecodeError:
        exhibit_text = exhibit_body.decode("latin-1")
    if not exhibit_text.strip():
        raise RefreshError(f"Exhibit 99.1 at {exhibit_url} is empty")
    acceptance = _iso_z(row["acceptance_datetime"])
    return {
        "cik": AAPL_CIK,
        "accession": AAPL_ACCESSION,
        "form": row["form"] or "8-K",
        "filing_date": row["filing_date"],
        "acceptance_datetime": acceptance,
        "report_date": row["report_date"],
        "exhibit_url": exhibit_url,
        "exhibit_body": exhibit_text,
        "items": row["items"],
    }


def acquire_flagship_transcript(
    index_url: str,
    *,
    fetch_index: FetchIndex = fetch_global_index,
    fetch_body_fn: FetchBody = fetch_body,
) -> tuple[dict[str, Any], str]:
    """Fetch AAPL/2026Q3 from the existing Terminal archive and verify its hash."""
    if index_url.endswith("/index.json"):
        base_url = index_url[: -len("/index.json")]
        raw_index = fetch_index(base_url)
    else:
        base_url = index_url.rstrip("/")
        raw_index = fetch_index(base_url)
    try:
        refs, _metadata = parse_global_index(raw_index)
    except Exception as exc:  # noqa: BLE001
        raise RefreshError(f"terminal transcript index invalid: {exc}") from exc
    ref = next((item for item in refs if item.pair == LIVE_NARRATIVE_ALIAS), None)
    if ref is None:
        raise RefreshError(f"terminal transcript {LIVE_NARRATIVE_ALIAS} is not in the public index")
    if not ref.body_sha256:
        raise RefreshError(
            f"terminal transcript {LIVE_NARRATIVE_ALIAS} has no advertised body hash"
        )
    try:
        payload = fetch_body_fn(base_url, ref)
    except Exception as exc:  # noqa: BLE001
        raise RefreshError(f"terminal transcript {LIVE_NARRATIVE_ALIAS} unavailable: {exc}") from exc
    return payload, ref.body_sha256


def exhibit_source_sha256(workspace: Mapping[str, Any] | None) -> str | None:
    if not isinstance(workspace, Mapping):
        return None
    for source in workspace.get("sources") or []:
        if isinstance(source, Mapping) and source.get("kind") == "issuer_release":
            sha = str(source.get("source_sha256") or "").strip().lower()
            return sha or None
    return None


def load_prior_flagship_workspace() -> dict[str, Any] | None:
    """Read the last published flagship workspace from the public origin.

    A missing nest is first-publish, not a failure.  Network errors are also
    fail-soft so a stale CDN cannot block a source-identical no-op rebuild.
    """
    import os

    import requests

    base = os.environ.get("COMPANY_INTELLIGENCE_R2_BASE_URL", _DEFAULT_PUBLIC_ORIGIN).strip().rstrip("/")
    headers = {"Accept": "application/json", "User-Agent": "mastermind-event-workspaces/1"}
    try:
        marker_resp = requests.get(f"{base}/event_workspaces/manifest.json", headers=headers, timeout=20)
        if marker_resp.status_code == 404:
            return None
        marker_resp.raise_for_status()
        marker = marker_resp.json()
        generation_id = str((marker or {}).get("generation_id") or "")
        if not generation_id:
            return None
        workspace_resp = requests.get(
            f"{base}/event_workspaces/generations/{generation_id}/workspaces/{FLAGSHIP_EVENT_ID}.json",
            headers=headers,
            timeout=20,
        )
        if workspace_resp.status_code == 404:
            return None
        workspace_resp.raise_for_status()
        payload = workspace_resp.json()
        return payload if isinstance(payload, dict) else None
    except Exception as exc:  # noqa: BLE001
        log.info("prior event workspace unread (%s); treating as first generation", exc)
        return None


def refresh(
    work_dir: Path,
    *,
    tx_index_url: str = DEFAULT_TX_INDEX_URL,
    out_dir: Path | None = None,
    dry_run: bool = False,
    http_get: HttpGet = _http_get,
    fetch_index: FetchIndex = fetch_global_index,
    fetch_body_fn: FetchBody = fetch_body,
    prior_workspace: PriorLoader | Mapping[str, Any] | None = None,
    publish_generation: PublishFn = publish_event_workspaces,
) -> int:
    """Acquire sources → build → write sibling nest → publish marker-last."""
    del work_dir  # reserved so the job shares the v1 scratch parent without writing it
    filing = acquire_flagship_filing(http_get=http_get)
    transcript, transcript_sha256 = acquire_flagship_transcript(
        tx_index_url,
        fetch_index=fetch_index,
        fetch_body_fn=fetch_body_fn,
    )
    prior: Mapping[str, Any] | None
    if callable(prior_workspace):
        try:
            prior = prior_workspace()
        except Exception as exc:  # noqa: BLE001 - missing last-good is first publish
            log.info("prior event workspace unavailable (%s); treating as first generation", exc)
            prior = None
    else:
        prior = prior_workspace
    source_clock = filing["acceptance_datetime"]
    payload = build_event_workspace(
        registry=apple_registry(),
        ticker="AAPL",
        asof=AAPL_CALL_DATE,
        fiscal_period=flagship_fiscal_period(),
        exhibit_body=str(filing["exhibit_body"]),
        filing={key: value for key, value in filing.items() if key != "exhibit_body"},
        transcript=transcript,
        transcript_sha256=transcript_sha256,
        observed_at=source_clock,
        source_available_at=source_clock,
        collector_rows=None,
        wire_record_found=False,
        prior_source_sha256=exhibit_source_sha256(prior),
    )
    if payload.get("event_id") != FLAGSHIP_EVENT_ID:
        raise RefreshError(f"flagship event_id drifted: {payload.get('event_id')}")
    target = Path(out_dir) if out_dir is not None else Path("data/company_intelligence")
    generation_dir = write_workspace_generation(
        target,
        {FLAGSHIP_EVENT_ID: payload},
        generated_at=source_clock,
    )
    print(
        "event workspaces: validated "
        f"event={FLAGSHIP_EVENT_ID} generation={generation_dir.name} "
        f"source_clock={source_clock}"
    )
    publish_rc = publish_generation(target, dry_run=dry_run)
    if publish_rc == PUBLISH_CONFLICT:
        print("event workspaces: sibling-marker promotion lost a safe compare-and-swap race")
    elif publish_rc != 0:
        raise RefreshError(f"event workspace publish failed with exit code {publish_rc}")
    elif dry_run:
        print("event workspaces: dry-run validated; sibling marker not promoted")
    else:
        print("event workspaces: immutable generation published and sibling marker promoted")
    return publish_rc


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--work-dir", type=Path, required=True, help="Unused scratch parent; kept for lane parity")
    parser.add_argument("--out-dir", type=Path, required=True, help="Company Intelligence product prefix")
    parser.add_argument("--terminal-tx-index-url", default=DEFAULT_TX_INDEX_URL)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    try:
        return refresh(
            args.work_dir,
            tx_index_url=args.terminal_tx_index_url,
            out_dir=args.out_dir,
            dry_run=args.dry_run,
            prior_workspace=load_prior_flagship_workspace,
        )
    except RefreshError as exc:
        print(f"::error title=event-workspaces::{exc}", flush=True)
        print(f"event workspaces: refresh refused: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
