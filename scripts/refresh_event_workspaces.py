"""Refresh and publish the sibling event_workspace nest: AAPL + A5A homebuilders.

This is the production bridge from the merged E1 builder onto the existing
Company Intelligence publication lane.  It acquires the real SEC Exhibit 99.1
(and, when held, the Terminal transcript), builds ``event_workspace.v1`` with a
source-stable clock, writes the sibling nest, and publishes it under the
existing ``company_intelligence/`` R2 prefix — for the AAPL flagship AND, as of
IMCE A5A, DHI/PHM/KBH/TOL results events through the SAME path.

It never writes the closed v1 teaser marker.  Source failure retains last-good
by refusing to move ``event_workspaces/manifest.json``.  Wall-clock of the
three-hour scheduler is not a data revision.

The AAPL flagship leg is a hard failure: any acquisition/build error there
refuses the whole refresh, exactly as before A5A.  Each homebuilder is
fail-soft (frozen spec item 8): one issuer's acquisition or extraction error
is logged and that issuer is skipped for this run; it never blocks the
flagship or the other homebuilders.  A5A stops at source truth — nothing here
writes to ``data/cycle_pattern/`` or computes an IMCE observation.

A GENUINE failure to read the PRIOR published workspace (network error,
timeout, non-2xx, malformed JSON — as opposed to a clean not-yet-published
404) is NOT fail-soft (NEW-1 fix, Opus red-team verification round 2,
2026-08-23): ``load_prior_workspace`` raises ``PriorWorkspaceFetchFailed``
rather than returning ``None``, which would otherwise be silently read as
"first generation" and could permanently erase a prior "corrected"
lifecycle state (see that exception's docstring). This still routes through
the SAME two failure disciplines above: a hard ``RefreshError`` for the
flagship, a per-ticker skip (no rebuild attempted this cycle) for a
homebuilder.
"""
from __future__ import annotations

import argparse
import calendar
from datetime import date, datetime, timezone
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
    production_registry,
    write_workspace_generation,
)
from engine.company_intelligence.event_workspace_build import build_event_workspace
from engine.company_intelligence.events import FiscalPeriod, canonical_event_id, parse_canonical_event_id
from engine.company_intelligence.issuer_profiles import (
    HOMEBUILDER_TICKERS,
    issuer_for_ticker,
    profile_for_ticker,
)
from engine.earnings_release.binding import submissions_rows
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


def _parallel_row(block: Mapping[str, Any], accession: str, *, cik: str) -> dict[str, Any] | None:
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
            "cik": cik,
            "accession": accession,
            # NEW-2 fix (Opus red-team round 2, 2026-08-23): never manufacture
            # "8-K" from a genuinely absent EDGAR form — at() already returns
            # "" when missing; publishing that truthfully lets the A5C
            # observation gate refuse rather than being handed an invented
            # safe value. Discovery pre-filters candidates to {8-K, 8-K/A},
            # so an empty form here should be unreachable on the real nightly
            # path; this is a defense-in-depth truthfulness fix, not a
            # behavior change for any real filing.
            "form": at("form"),
            "filing_date": at("filingDate"),
            "acceptance_datetime": at("acceptanceDateTime"),
            "report_date": at("reportDate"),
            "primary_document": at("primaryDocument"),
            "items": at("items"),
        }
    return None


def _select_newest_results_rows(rows: list[Mapping[str, Any]]) -> list[dict[str, Any]]:
    """Every 8-K or 8-K/A row whose declared items include Item 2.02, newest first.

    Admitting ``"8-K/A"`` (F5) matters: an amendment is a different FILING of
    the SAME event (``engine.earnings_release.binding`` module docstring),
    and ``form == "8-K"`` alone made the correction path unreachable in
    discovery mode — an amendment would never even be considered as a
    candidate, let alone matched to the original by ``report_date`` grouping
    downstream.  The check is an exact membership test, not a prefix match,
    so an unrelated "8-K12B"/"8-K12G3"/"8-K15D5" special-filing variant is
    never admitted.  Newest is by acceptance timestamp (falling back to
    filing date for a row that somehow lacks one) — the source's own clock,
    not feed order.
    """
    candidates = [
        dict(row)
        for row in rows
        if str(row.get("form") or "").strip().upper() in {"8-K", "8-K/A"} and "2.02" in str(row.get("items") or "")
    ]
    candidates.sort(
        key=lambda row: (str(row.get("acceptanceDateTime") or ""), str(row.get("filingDate") or "")),
        reverse=True,
    )
    return candidates


def acquire_results_filing(
    *, cik: str, http_get: HttpGet = _http_get, accession: str | None = None
) -> dict[str, Any]:
    """Resolve one issuer's results 8-K + EX-99.1 through the submissions + SGML seam.

    ``accession`` pins an exact filing — the AAPL flagship replay path, and
    byte-identical to the pre-A5A single-issuer behavior.  ``accession=None``
    is discovery mode: it walks ``filings.recent``'s 8-K rows whose declared
    ``items`` include Item 2.02 (Results of Operations), newest first, and
    returns the first one that ALSO carries an EX-99.1 results exhibit — a
    later 8-K with no Item 2.02, or one that has it but no results exhibit, is
    skipped rather than treated as a refusal.  SEC-only; no IR webpage
    scraping.
    """
    cik_int = int(cik)
    status, body = http_get(_SUBMISSIONS_URL.format(cik=cik_int))
    if status != 200:
        raise RefreshError(f"SEC submissions unavailable for CIK {cik}: HTTP {status}")
    try:
        submissions = json.loads(body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise RefreshError(f"SEC submissions JSON invalid: {exc}") from exc
    if not isinstance(submissions, dict):
        raise RefreshError("SEC submissions JSON must be an object")
    filings = submissions.get("filings") or {}
    if not isinstance(filings, dict):
        raise RefreshError("SEC submissions filings block invalid")

    candidate_rows: list[dict[str, Any]]
    if accession is not None:
        row = _parallel_row(filings.get("recent") or {}, accession, cik=cik)
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
                    row = _parallel_row(shard_payload, accession, cik=cik)
                if row is not None:
                    break
        if row is None:
            raise RefreshError(f"accession {accession} is not present in SEC submissions for CIK {cik}")
        candidate_rows = [row]
    else:
        ordered = _select_newest_results_rows(submissions_rows(submissions, block="recent"))
        candidate_rows = [
            {
                "cik": cik,
                "accession": str(entry.get("accessionNumber") or ""),
                # NEW-2 fix (Opus red-team round 2, 2026-08-23): never
                # manufacture "8-K" from a genuinely absent EDGAR form — see
                # the sibling comment on _parallel_row's "form" key above.
                "form": entry.get("form") or "",
                "filing_date": entry.get("filingDate") or "",
                "acceptance_datetime": entry.get("acceptanceDateTime") or "",
                "report_date": entry.get("reportDate") or "",
                "primary_document": entry.get("primaryDocument") or "",
                "items": entry.get("items") or "",
            }
            for entry in ordered
        ]
        if not candidate_rows:
            raise RefreshError(f"no Item 2.02 8-K is present in SEC submissions for CIK {cik}")

    last_error: str | None = None
    for row in candidate_rows:
        row_accession = str(row["accession"])
        acc_nodash = row_accession.replace("-", "")
        archive_base = f"{_ARCHIVES}/{cik_int}/{acc_nodash}"
        time.sleep(_PACE_S)
        header_status, header_body = http_get(f"{archive_base}/{row_accession}-index-headers.html")
        if header_status != 200:
            message = f"SEC filing document map unavailable for {row_accession}: HTTP {header_status}"
            if accession is not None:
                raise RefreshError(message)
            last_error = message
            continue
        filename = _select_exhibit_99_1(_parse_sgml_manifest(header_body.decode("utf-8", errors="replace")))
        if not filename:
            message = f"EX-99.1 is absent from the SGML document map for {row_accession}"
            if accession is not None:
                raise RefreshError(message)
            last_error = message
            continue
        exhibit_url = f"{archive_base}/{filename}"
        time.sleep(_PACE_S)
        exhibit_status, exhibit_body = http_get(exhibit_url)
        if exhibit_status != 200 or not exhibit_body.strip():
            message = f"Exhibit 99.1 unavailable at {exhibit_url}: HTTP {exhibit_status}"
            if accession is not None:
                raise RefreshError(message)
            last_error = message
            continue
        try:
            exhibit_text = exhibit_body.decode("utf-8")
        except UnicodeDecodeError:
            exhibit_text = exhibit_body.decode("latin-1")
        if not exhibit_text.strip():
            message = f"Exhibit 99.1 at {exhibit_url} is empty"
            if accession is not None:
                raise RefreshError(message)
            last_error = message
            continue
        acceptance = _iso_z(row["acceptance_datetime"])
        return {
            "cik": cik,
            "accession": row_accession,
            # NEW-2 fix (Opus red-team round 2, 2026-08-23): never
            # manufacture "8-K" from a genuinely absent EDGAR form — see
            # the sibling comments on the candidate_rows construction above.
            "form": row["form"] or "",
            "filing_date": row["filing_date"],
            "acceptance_datetime": acceptance,
            "report_date": row["report_date"],
            "exhibit_url": exhibit_url,
            "exhibit_body": exhibit_text,
            "items": row["items"],
        }
    raise RefreshError(last_error or f"no results filing with an EX-99.1 exhibit is available for CIK {cik}")


def acquire_flagship_filing(*, http_get: HttpGet = _http_get) -> dict[str, Any]:
    """Resolve the frozen AAPL accession — unchanged pre-A5A behavior."""
    return acquire_results_filing(cik=AAPL_CIK, http_get=http_get, accession=AAPL_ACCESSION)


def acquire_transcript_for(
    pair: str,
    index_url: str,
    *,
    fetch_index: FetchIndex = fetch_global_index,
    fetch_body_fn: FetchBody = fetch_body,
    required: bool = True,
) -> tuple[dict[str, Any] | None, str | None]:
    """Fetch *pair* (``"TICKER/YYYYQn"``) from the Terminal archive and verify its hash.

    ``required=True`` (the flagship's own behavior, unchanged) raises
    ``RefreshError`` on any absence.  ``required=False`` (homebuilders, which
    may have no held call — frozen spec item 5) returns ``(None, None)``
    instead, so a missing transcript is a typed absence at build time, not a
    refusal.
    """
    if index_url.endswith("/index.json"):
        base_url = index_url[: -len("/index.json")]
    else:
        base_url = index_url.rstrip("/")
    raw_index = fetch_index(base_url)
    try:
        refs, _metadata = parse_global_index(raw_index)
    except Exception as exc:  # noqa: BLE001
        raise RefreshError(f"terminal transcript index invalid: {exc}") from exc
    ref = next((item for item in refs if item.pair == pair), None)
    if ref is None:
        if required:
            raise RefreshError(f"terminal transcript {pair} is not in the public index")
        return None, None
    if not ref.body_sha256:
        if required:
            raise RefreshError(f"terminal transcript {pair} has no advertised body hash")
        return None, None
    try:
        payload = fetch_body_fn(base_url, ref)
    except Exception as exc:  # noqa: BLE001
        if required:
            raise RefreshError(f"terminal transcript {pair} unavailable: {exc}") from exc
        return None, None
    return payload, ref.body_sha256


def acquire_flagship_transcript(
    index_url: str,
    *,
    fetch_index: FetchIndex = fetch_global_index,
    fetch_body_fn: FetchBody = fetch_body,
) -> tuple[dict[str, Any], str]:
    """Fetch AAPL/2026Q3 from the existing Terminal archive and verify its hash."""
    payload, body_sha256 = acquire_transcript_for(
        LIVE_NARRATIVE_ALIAS, index_url, fetch_index=fetch_index, fetch_body_fn=fetch_body_fn, required=True,
    )
    assert payload is not None and body_sha256 is not None  # required=True never returns (None, None)
    return payload, body_sha256


def exhibit_source_sha256(workspace: Mapping[str, Any] | None) -> str | None:
    if not isinstance(workspace, Mapping):
        return None
    for source in workspace.get("sources") or []:
        if isinstance(source, Mapping) and source.get("kind") == "issuer_release":
            sha = str(source.get("source_sha256") or "").strip().lower()
            return sha or None
    return None


def prior_lifecycle_state(workspace: Mapping[str, Any] | None) -> str | None:
    """The prior published workspace's OWN ``lifecycle.state``, or ``None``.

    A5C BLOCKER-1 (Opus red-team, 2026-08-23): paired with
    ``exhibit_source_sha256`` above and passed through to
    ``build_event_workspace`` as ``prior_lifecycle_state`` so a
    ``"corrected"`` state STAYS corrected on every later generation whose
    source hash is unchanged — ``build_event_workspace`` re-applies the
    corrected transition rather than silently walking back to
    ``"complete"``, which is what let the exact mint the IMCE A5C safety
    law forbids proceed within one 3-hour republish cycle."""
    if not isinstance(workspace, Mapping):
        return None
    state = (workspace.get("lifecycle") or {}).get("state")
    return str(state) if state else None


class PriorWorkspaceFetchFailed(RuntimeError):
    """The prior-workspace read failed for a reason OTHER than a clean
    not-yet-published 404 (NEW-1, Opus red-team verification round 2,
    2026-08-23): a network error, timeout, non-2xx, or malformed JSON.

    Distinguishable on purpose from "genuinely not published yet": treating
    a transient fetch failure as first-publish is exactly the bug this
    exception exists to prevent. A missed prior read on an event whose last
    published generation was ``lifecycle.state == "corrected"`` would
    silently erase that correction (the rebuild walks started -> complete
    instead of re-applying corrected -> corrected), and because the
    de-corrected workspace becomes the new "prior" on the very next read,
    the erasure is PERMANENT, not merely delayed to the next successful
    fetch. A second (non-amendment, still form="8-K") correction minted
    after this erasure would then present as a first-ever "complete"/"8-K"
    revision — the A5C form gate (BLOCKER-1 1c) does not catch this shape,
    because nothing about it is actually an SEC amendment.
    """


class _PriorWorkspaceNotPublished(Exception):
    """A clean 404 (manifest or workspace) or an absent-generation
    manifest — the event genuinely has no prior publication yet. Distinct
    from ``PriorWorkspaceFetchFailed`` above; caught internally by
    ``load_prior_workspace`` and turned into a plain ``None`` return."""


def _raw_load_prior_workspace(event_id: str, *, base_url: str | None = None) -> dict[str, Any]:
    """Fetch the last published workspace for *event_id* from the public
    origin, mirroring
    ``scripts.build_cycle_pattern_imce_prospective._raw_fetch_workspace``'s
    own base-URL resolution and GET sequence (NEW-1, Opus red-team round 2,
    2026-08-23).

    Raises ``_PriorWorkspaceNotPublished`` on a clean 404 (manifest or
    workspace) or an absent-generation manifest. Raises any OTHER exception
    (network error, timeout, non-2xx, malformed JSON) on a genuine fetch
    failure — never returns ``None`` on failure; disposition classification
    is ``load_prior_workspace``'s job, exactly as the A5B builder's
    ``_load_workspace_with_disposition`` classifies its own fetcher.
    """
    import os

    import requests

    base = (base_url or os.environ.get("COMPANY_INTELLIGENCE_R2_BASE_URL", _DEFAULT_PUBLIC_ORIGIN)).strip().rstrip("/")
    headers = {"Accept": "application/json", "User-Agent": "mastermind-event-workspaces/1"}

    marker_resp = requests.get(f"{base}/event_workspaces/manifest.json", headers=headers, timeout=20)
    if marker_resp.status_code == 404:
        raise _PriorWorkspaceNotPublished(f"{event_id}: manifest 404")
    marker_resp.raise_for_status()
    marker = marker_resp.json()
    generation_id = str((marker or {}).get("generation_id") or "")
    if not generation_id:
        raise _PriorWorkspaceNotPublished(f"{event_id}: manifest carries no generation_id")

    workspace_resp = requests.get(
        f"{base}/event_workspaces/generations/{generation_id}/workspaces/{event_id}.json",
        headers=headers,
        timeout=20,
    )
    if workspace_resp.status_code == 404:
        raise _PriorWorkspaceNotPublished(f"{event_id}: workspace 404 in generation {generation_id}")
    workspace_resp.raise_for_status()
    payload = workspace_resp.json()
    if not isinstance(payload, dict):
        raise ValueError(f"{event_id}: workspace payload is not a dict")
    return payload


def load_prior_workspace(
    event_id: str, *, base_url: str | None = None,
    fetch: Callable[[str], dict[str, Any]] | None = None,
) -> dict[str, Any] | None:
    """Read the last published workspace for *event_id* from the public origin.

    A missing nest, or a nest published without this event, is first-publish,
    not a failure — returns ``None``.

    NEW-1 fix (Opus red-team verification round 2, 2026-08-23): this NO
    LONGER fail-softs a GENUINE fetch failure into "first generation". The
    prior behavior (catching every ``Exception`` and returning ``None``)
    meant one transient HTTP failure on the prior read was indistinguishable
    from "this event was never published" — see
    ``PriorWorkspaceFetchFailed``'s docstring for the exact silent-erasure
    consequence. Raises ``PriorWorkspaceFetchFailed`` on anything other than
    a clean not-published 404; only a genuinely absent prior publication
    returns ``None``. *fetch* is injectable for tests (a stub raising
    ``_PriorWorkspaceNotPublished`` for a clean 404, any other exception for
    a fetch failure, or returning a dict for a hit) — production callers
    never pass it, always exercising the real HTTP path via
    ``_raw_load_prior_workspace``.
    """
    fetcher = fetch or (lambda eid: _raw_load_prior_workspace(eid, base_url=base_url))
    try:
        return fetcher(event_id)
    except _PriorWorkspaceNotPublished as exc:
        log.debug("%s: prior workspace not published (%s)", event_id, exc)
        return None
    except Exception as exc:  # noqa: BLE001 - every other failure is a genuine fetch failure, never silently absent
        print(
            "::warning title=event-workspace-prior-fetch-failed::"
            f"{event_id}: prior workspace fetch failed ({type(exc).__name__}: {exc}) — "
            "refusing to treat this as first-generation; this event's rebuild is skipped this cycle",
            flush=True,
        )
        log.info("%s: prior workspace fetch failed, refusing first-generation fallback (%s)", event_id, exc)
        raise PriorWorkspaceFetchFailed(
            f"{event_id}: prior workspace fetch failed ({type(exc).__name__}: {exc})"
        ) from exc


def load_prior_flagship_workspace() -> dict[str, Any] | None:
    """Read the last published flagship workspace — unchanged pre-A5A behavior."""
    return load_prior_workspace(FLAGSHIP_EVENT_ID)


def load_prior_workspace_for_ticker(ticker: str, *, base_url: str | None = None) -> dict[str, Any] | None:
    """The most recently published workspace belonging to *ticker*'s STATIC
    issuer identity, read directly from the CURRENT generation's own
    manifest — independent of whether THIS CYCLE's fresh acquisition ever
    succeeds (NEW-4, Opus red-team verification round 3, 2026-08-23).

    ``load_prior_workspace(event_id)`` needs THIS cycle's freshly discovered
    event_id, which is only computable after a successful acquisition —
    exactly the thing that may have just failed. This function instead
    scans the current generation manifest's ``files`` map (event_ids only;
    no workspace body is fetched for anything but the one match) for an
    event_id whose ``parse_canonical_event_id`` company_id matches this
    ticker's registered issuer identity — a STATIC, acquisition-independent
    lookup.

    Returns ``None`` ONLY for: (i) the top-level marker is a clean 404 (no
    nest has ever been published); (ii) the current generation's own
    manifest is well-formed and simply carries no entry for this ticker's
    issuer (never published, or already superseded off the generation at a
    quarterly rollover — see the module docstring's monotonicity note).

    NEW-6 (Opus red-team verification round 4, 2026-08-23): EVERY other
    outcome is treated as an ANOMALY, not an absence, and raises
    ``PriorWorkspaceFetchFailed`` — a genuine network/timeout/non-2xx/
    malformed-JSON failure at any read here (unchanged from round 3), a
    top-level marker that parses but carries no ``generation_id``, the
    named generation's own ``manifest.json`` 404ing, that manifest's
    payload not being an object, or that object carrying no usable
    ``"files"`` map. ``write_workspace_generation`` uploads every workspace
    object, THEN that generation's own ``manifest.json``, and only THEN
    promotes the top-level marker to point at it — so once the top-level
    marker names a ``generation_id``, that generation's manifest existing,
    being an object, and carrying a ``"files"`` key are all GUARANTEED by
    the publish protocol unless something is genuinely broken. Reading any
    of those as "nothing to carry" would erase a corrected event exactly
    like a genuine fetch failure would.
    """
    issuer = issuer_for_ticker(ticker)
    if issuer is None:
        return None
    import os

    import requests

    base = (base_url or os.environ.get("COMPANY_INTELLIGENCE_R2_BASE_URL", _DEFAULT_PUBLIC_ORIGIN)).strip().rstrip("/")
    headers = {"Accept": "application/json", "User-Agent": "mastermind-event-workspaces/1"}

    def _anomaly(detail: str) -> PriorWorkspaceFetchFailed:
        print(
            "::warning title=event-workspace-prior-fetch-failed::"
            f"{ticker}: {detail} — refusing to treat this as no-prior-to-carry",
            flush=True,
        )
        return PriorWorkspaceFetchFailed(f"{ticker}: {detail}")

    try:
        marker_resp = requests.get(f"{base}/event_workspaces/manifest.json", headers=headers, timeout=20)
        if marker_resp.status_code == 404:
            return None  # (i): genuinely no nest published yet
        marker_resp.raise_for_status()
        marker = marker_resp.json()
        generation_id = str((marker or {}).get("generation_id") or "")
        if not generation_id:
            # NEW-6: a marker that parsed successfully but carries no
            # generation_id is anomalous — the publish protocol never
            # promotes a marker without one.
            raise _anomaly("top-level marker carries no generation_id")
        gen_resp = requests.get(
            f"{base}/event_workspaces/generations/{generation_id}/manifest.json",
            headers=headers, timeout=20,
        )
        if gen_resp.status_code == 404:
            # NEW-6 (a): the marker names a generation whose OWN manifest is
            # missing — anomalous (the publisher writes the generation
            # manifest BEFORE promoting the marker to point at it).
            raise _anomaly(f"generation {generation_id} manifest 404 despite a promoted marker")
        gen_resp.raise_for_status()
        gen_manifest = gen_resp.json()
    except PriorWorkspaceFetchFailed:
        raise
    except Exception as exc:  # noqa: BLE001 - every other failure is a genuine fetch failure, never silently absent
        raise _anomaly(f"current-generation read failed ({type(exc).__name__}: {exc})") from exc

    if not isinstance(gen_manifest, Mapping):
        # NEW-6 (b)
        raise _anomaly(f"generation {generation_id} manifest payload is not an object")
    files = gen_manifest.get("files")
    if not isinstance(files, Mapping):
        # NEW-6 (c)
        raise _anomaly(f"generation {generation_id} manifest carries no usable 'files' map")

    # NEW-7 (Opus red-team round 4, 2026-08-23): collect EVERY matching
    # event_id and select the NEWEST fiscal period, not the first one
    # encountered — `files` iterates in the manifest's own sorted-string
    # key order, so a plain first-match would pick the LEXICOGRAPHICALLY
    # SMALLEST (= OLDEST) event if the one-event-per-issuer invariant ever
    # broke (e.g. a transient double-publish). Correct selection costs
    # nothing here and removes a silent wrong-answer mode.
    matches: list[tuple[tuple[int, int], str]] = []
    for relative in files:
        relative_text = str(relative)
        if not relative_text.startswith("workspaces/") or not relative_text.endswith(".json"):
            continue
        candidate_event_id = relative_text[len("workspaces/"):-len(".json")]
        try:
            company_id, fiscal_period, _event_type = parse_canonical_event_id(candidate_event_id)
        except Exception:  # noqa: BLE001 - a non-canonical file name is simply not a match
            continue
        if company_id == issuer.company_id:
            matches.append(((fiscal_period.year, fiscal_period.quarter or 0), candidate_event_id))
    if not matches:
        return None  # (ii): well-formed files map, no entry for this issuer
    matches.sort(key=lambda item: item[0])
    matched_event_id = matches[-1][1]
    return load_prior_workspace(matched_event_id, base_url=base_url)


_STATED_PERIOD_END_RE = re.compile(
    r"(?:Three\s+Months\s+Ended|[Qq]uarter\s+ended)\s+([A-Za-z]+\s+\d{1,2},?\s*\d{4})"
)


def _fiscal_quarter_end_before(anchor: date, fiscal_year_end_month: int) -> date:
    """The most recent completed fiscal-quarter END strictly before *anchor*.

    F1: an earnings release is published WEEKS after the quarter it reports
    on closes.  EDGAR's own ``reportDate`` on an Item 2.02 8-K is the SAME as
    ``filingDate`` — the press-release date, never the period end (verified:
    DHI accession 0000882184-26-000092 carries ``reportDate == filingDate ==
    "2026-07-21"``, live SEC receipt, for a quarter that actually ended
    2026-06-30).  This walks backward from ``anchor`` to the nearest fiscal
    quarter-end date that precedes it, using the issuer's own
    ``fiscal_year_end_month``; the caller then cross-checks that computed
    date against the exhibit's own stated period before minting an event.
    """
    quarter_end_months = sorted({(fiscal_year_end_month - 3 * i - 1) % 12 + 1 for i in range(4)})
    candidates: list[date] = []
    for year in (anchor.year - 1, anchor.year, anchor.year + 1):
        for month in quarter_end_months:
            last_day = calendar.monthrange(year, month)[1]
            candidates.append(date(year, month, last_day))
    before = [candidate for candidate in candidates if candidate < anchor]
    if not before:
        raise RefreshError(f"no fiscal quarter end precedes anchor date {anchor.isoformat()}")
    return max(before)


def fiscal_period_for_report_date(report_date: str, fiscal_year_end_month: int) -> FiscalPeriod:
    """Derive the fiscal period from the quarter END nearest before *report_date*.

    ``report_date`` here is EDGAR's own value (== the press-release/filing
    date on every real Item-2.02 8-K observed — F1), used only as an ANCHOR
    to find "which quarter just closed", never as the period end itself.
    Standard US-GAAP fiscal-quarter convention: the fiscal year starts the
    calendar month after ``fiscal_year_end_month`` and runs 4 quarters of 3
    months each; the fiscal year label is the calendar year in which the
    fiscal year END falls.  Verified by hand against DHI (FYE Sept, real
    reportDate 2026-07-21 -> FY2026 Q3, period end 2026-06-30), PHM (FYE Dec,
    real reportDate 2026-07-22 -> FY2026 Q2, period end 2026-06-30), KBH (FYE
    Nov, real reportDate 2026-06-23 -> FY2026 Q2, period end 2026-05-31), and
    TOL (FYE Oct, real reportDate 2026-08-18 -> FY2026 Q3, period end
    2026-07-31) — see the PR body.  The caller cross-checks this against the
    exhibit's own stated period (:func:`_stated_period_end`) before trusting
    it; a mismatch refuses rather than minting a guessed identity.
    """
    anchor = date.fromisoformat(str(report_date))
    quarter_end = _fiscal_quarter_end_before(anchor, fiscal_year_end_month)
    fy_start_month = (fiscal_year_end_month % 12) + 1
    months_elapsed = (quarter_end.month - fy_start_month) % 12
    quarter = months_elapsed // 3 + 1
    fiscal_year = quarter_end.year if quarter_end.month <= fiscal_year_end_month else quarter_end.year + 1
    return FiscalPeriod(year=fiscal_year, quarter=quarter, calendar_end=quarter_end)


def _stated_period_end(exhibit_body: str) -> date | None:
    """The exhibit's own stated quarterly period end, or ``None`` if it
    cannot be located.

    Tries "Three Months Ended <date>" (DHI/KBH/PHM's table-header phrasing)
    then "quarter ended <date>" (PHM/TOL's narrative phrasing); first match
    wins.  This is the cross-check F1 requires: the discovery-derived
    quarter end (:func:`fiscal_period_for_report_date`) must agree with what
    the release itself says it covers, or the issuer is skipped rather than
    published under a guessed fiscal identity.
    """
    visible = html_unescape(re.sub(r"<[^>]+>", " ", exhibit_body))
    visible = re.sub(r"\s+", " ", visible)
    match = _STATED_PERIOD_END_RE.search(visible)
    if match is None:
        return None
    raw = match.group(1).replace(",", "")
    for fmt in ("%B %d %Y", "%b %d %Y"):
        try:
            return datetime.strptime(raw, fmt).date()
        except ValueError:
            continue
    return None


def acquire_and_build_homebuilder_workspace(
    ticker: str,
    *,
    http_get: HttpGet = _http_get,
    tx_index_url: str = DEFAULT_TX_INDEX_URL,
    fetch_index: FetchIndex = fetch_global_index,
    fetch_body_fn: FetchBody = fetch_body,
    prior_workspace_loader: Callable[[str], Mapping[str, Any] | None] = load_prior_workspace,
) -> tuple[str, dict[str, Any]]:
    """Acquire + build one homebuilder's workspace.  Raises on any failure.

    The caller (``refresh``) is responsible for the fail-soft wrapping this
    function deliberately does NOT do itself, so a direct call surfaces the
    real error for tests and diagnostics.
    """
    issuer = issuer_for_ticker(ticker)
    profile = profile_for_ticker(ticker)
    if issuer is None or profile is None:
        raise RefreshError(f"{ticker} has no registered A5A homebuilder identity/profile")
    filing = acquire_results_filing(cik=issuer.cik, http_get=http_get)
    fiscal_period = fiscal_period_for_report_date(filing["report_date"], issuer.fiscal_year_end_month)
    # F1 cross-check: never mint an event on the discovery-derived quarter
    # end alone.  The exhibit must state that SAME period itself, or this
    # issuer is skipped for the run (typed/logged absence) rather than
    # published under a guessed fiscal identity.
    stated_end = _stated_period_end(str(filing["exhibit_body"]))
    if stated_end != fiscal_period.calendar_end:
        raise RefreshError(
            f"{ticker}: computed fiscal quarter end {fiscal_period.calendar_end} does not match "
            f"the exhibit's own stated period end ({stated_end!r}); refusing to mint a guessed "
            "fiscal identity"
        )
    asof = date.fromisoformat(str(filing["filing_date"]))
    event_id = canonical_event_id(issuer.company_id, fiscal_period)
    pair = f"{ticker}/{fiscal_period.year}Q{fiscal_period.quarter}"
    transcript, transcript_sha256 = acquire_transcript_for(
        pair, tx_index_url, fetch_index=fetch_index, fetch_body_fn=fetch_body_fn, required=False,
    )
    prior = prior_workspace_loader(event_id)
    source_clock = filing["acceptance_datetime"]
    payload = build_event_workspace(
        registry=production_registry(),
        ticker=ticker,
        asof=asof,
        fiscal_period=fiscal_period,
        exhibit_body=str(filing["exhibit_body"]),
        filing={key: value for key, value in filing.items() if key != "exhibit_body"},
        transcript=transcript,
        transcript_sha256=transcript_sha256,
        observed_at=source_clock,
        source_available_at=source_clock,
        collector_rows=None,
        wire_record_found=False,
        prior_source_sha256=exhibit_source_sha256(prior),
        prior_lifecycle_state=prior_lifecycle_state(prior),
        profile=profile,
    )
    if payload.get("event_id") != event_id:
        raise RefreshError(f"{ticker} event_id drifted: {payload.get('event_id')}")
    return event_id, payload


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
    # NEW-4 fix (Opus red-team verification round 3, 2026-08-23): the
    # homebuilder prior loader was hardcoded to load_prior_workspace at the
    # per-ticker call site — unreachable by a test without monkeypatching
    # the module-level name. Now a real parameter, mirroring the flagship's
    # own prior_workspace injection point above.
    homebuilder_prior_workspace_loader: Callable[[str], Mapping[str, Any] | None] = load_prior_workspace,
    # NEW-4: the ticker-scoped carry-forward lookup (load_prior_workspace_for_ticker
    # by default) used ONLY when this cycle's acquisition/build fails and the
    # normal event_id-keyed prior read above was never reached.
    homebuilder_carry_forward_loader: Callable[[str], Mapping[str, Any] | None] = load_prior_workspace_for_ticker,
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
        except Exception as exc:  # noqa: BLE001
            # NEW-1 fix (round 2) + NEW-5 fix (round 3, Opus red-team
            # verification, 2026-08-23): NO exception of ANY type may be
            # silently read as "first generation" — only an EXPLICIT clean
            # `None` return from prior_workspace() may mean that. Round 2
            # fixed this specifically for PriorWorkspaceFetchFailed but left
            # a generic `except Exception: prior = None` fallback for every
            # OTHER exception type — a latent re-entry of the exact erasure
            # bug this law exists to prevent, the moment any future loader
            # raised something else. The flagship leg is ALREADY a hard,
            # all-or-nothing failure for every other acquisition/build
            # error (module docstring) — this raises RefreshError
            # uniformly for the same reason, refusing the WHOLE refresh
            # rather than guessing. Chosen over "skip semantics" because
            # the flagship has no per-issuer loop to skip within —
            # refresh() produces exactly one flagship record, not N
            # independent ones.
            raise RefreshError(f"flagship prior workspace fetch failed: {exc}") from exc
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
        prior_lifecycle_state=prior_lifecycle_state(prior),
    )
    if payload.get("event_id") != FLAGSHIP_EVENT_ID:
        raise RefreshError(f"flagship event_id drifted: {payload.get('event_id')}")

    # NEW-4 fix (Opus red-team verification round 3, 2026-08-23): generations
    # are WHOLE-NEST snapshots — write_workspace_generation has no carry
    # logic, so an event silently omitted from `workspaces` here is simply
    # ABSENT from this generation. The NEXT cycle's prior lookup for that
    # SAME event_id then 404s against the CURRENT (this) generation — a
    # legitimate, successful "not published in this generation" read, not a
    # fetch failure NEW-1 catches — so prior_source_sha256/prior_lifecycle_state
    # both resolve None and a "corrected" state silently erases one hop
    # later, with the only ::warning ever fired describing a skip, not an
    # erasure. NEW-8 (Opus red-team round 4, 2026-08-23 — the round-3
    # wording above overstated it as a blanket "membership must be
    # monotonic"): the true invariant is narrower — each ticker's MOST
    # RECENTLY PUBLISHED event is carried forward whenever THIS cycle
    # cannot rebuild it. A SUPERSEDED event (the prior quarter, once a
    # newer one publishes) legitimately drops out of the generation at
    # rollover and reads as not_published downstream from then on — that
    # is fail-closed and intentional, not a regression of this fix. Three
    # outcomes per ticker below implement the narrower invariant:
    #   (a) acquisition/build failed but a prior IS readable (via the
    #       ticker-scoped carry-forward lookup, independent of whether
    #       THIS cycle's fresh event_id was ever computed) -> CARRY FORWARD
    #       the prior payload unchanged into this generation.
    #   (b) the carry-forward lookup ITSELF fails for ANY reason -> ABORT
    #       the whole refresh (RefreshError, nothing published, marker
    #       frozen) — cannot rule out silently dropping a corrected event.
    #       Same discipline as the flagship's own prior-fetch-failure
    #       handling above; one issuer's CDN blip delaying ALL publication
    #       by one cycle is the accepted cost. The NORMAL-path
    #       event_id-keyed prior read inside
    #       acquire_and_build_homebuilder_workspace (after a SUCCESSFUL
    #       acquisition) already raises PriorWorkspaceFetchFailed uncaught
    #       (NEW-1) — caught here too, same abort.
    #   (c) genuinely never published (no prior found by either lookup)
    #       and acquisition failed -> true skip, nothing to carry, and its
    #       absence next cycle correctly reads as first-publish.
    #
    # Accepted-cost note (no code change, requested for the record): this
    # abort surface is now roughly 10 R2 GETs/cycle across ~8 cycles/day.
    # Each abort costs exactly one 3h cycle with the marker frozen on the
    # last good generation. At realistic GET success rates that is on the
    # order of one delayed cycle per days-to-weeks, not per night. A
    # bounded retry on the prior-read GETs is a possible future reduction
    # of that already-small residual — deliberately NOT added in this PR.
    workspaces: dict[str, dict[str, Any]] = {FLAGSHIP_EVENT_ID: payload}
    for ticker in HOMEBUILDER_TICKERS:
        try:
            event_id, hb_payload = acquire_and_build_homebuilder_workspace(
                ticker,
                http_get=http_get,
                tx_index_url=tx_index_url,
                fetch_index=fetch_index,
                fetch_body_fn=fetch_body_fn,
                prior_workspace_loader=homebuilder_prior_workspace_loader,
            )
        except PriorWorkspaceFetchFailed as exc:
            # (b): the NORMAL-path prior read (after a successful
            # acquisition) failed — cannot safely publish.
            raise RefreshError(
                f"{ticker}: prior workspace fetch failed — refusing to publish a nest that might "
                f"silently drop a corrected event: {exc}"
            ) from exc
        except Exception as exc:  # noqa: BLE001 - acquisition/build failed; try to carry the prior forward before giving up
            try:
                carried_prior = homebuilder_carry_forward_loader(ticker)
            except Exception as carry_exc:  # noqa: BLE001
                # (b), extended (NIT fix, round 4): ANY exception from the
                # carry-forward lookup — not only PriorWorkspaceFetchFailed
                # — means we cannot confirm nothing is lost. Uniform with
                # the flagship's own handler above (NEW-5): only an
                # explicit clean None return may mean "nothing to carry."
                raise RefreshError(
                    f"{ticker}: acquisition failed AND the carry-forward prior lookup also failed — "
                    f"refusing to publish a nest that might silently drop a corrected event: {carry_exc}"
                ) from carry_exc
            if carried_prior is not None:
                # (a): carry the prior payload forward unchanged. Its own
                # event_id field is authoritative for the workspaces key.
                carried_event_id = str(carried_prior.get("event_id") or "")
                if not carried_event_id:
                    raise RefreshError(f"{ticker}: carried-forward prior workspace has no event_id") from exc
                print(
                    "::warning title=event-workspaces::"
                    f"{ticker} acquisition failed, CARRIED FORWARD prior workspace unchanged "
                    f"(class={type(exc).__name__}): {exc}",
                    flush=True,
                )
                log.info("%s: acquisition failed, carried forward prior workspace unchanged (%s)", ticker, exc)
                workspaces[carried_event_id] = dict(carried_prior)
            else:
                # (c): genuinely never published — true skip.
                print(f"::warning title=event-workspaces::{ticker} skipped (no prior to carry): {exc}", flush=True)
                log.info("%s event workspace skipped, no prior to carry (%s)", ticker, exc)
            continue
        workspaces[event_id] = hb_payload

    target = Path(out_dir) if out_dir is not None else Path("data/company_intelligence")
    generation_dir = write_workspace_generation(
        target,
        workspaces,
        generated_at=source_clock,
    )
    print(
        "event workspaces: validated "
        f"events={sorted(workspaces)} generation={generation_dir.name} "
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
