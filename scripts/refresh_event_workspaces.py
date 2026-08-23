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
from hashlib import sha256
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
    MANIFEST_SCHEMA_V2,
    apple_registry,
    flagship_fiscal_period,
    preview_generation_identity,
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
from engine.neuralweb import company_intelligence_reader as ci_reader
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


def prior_observed_at(workspace: Mapping[str, Any] | None) -> str | None:
    """The prior published workspace's OWN ``lifecycle.observed_at``, or
    ``None`` — IMCE A5C two-clock law, first-observation persistence (C3).
    Paired with ``exhibit_source_sha256`` above and passed through to
    ``build_event_workspace`` as ``prior_observed_at`` so an unchanged
    source revision keeps its ORIGINAL first-observation timestamp forever;
    ``build_event_workspace`` carries it forward only when the freshly
    bound exhibit's source_sha256 matches ``prior_source_sha256`` exactly."""
    if not isinstance(workspace, Mapping):
        return None
    observed = (workspace.get("lifecycle") or {}).get("observed_at")
    return str(observed) if observed else None


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


# IMCE A5C (frozen spec D1/D3): the marker/generation/workspace GET
# sequence now lives ONCE, in engine.neuralweb.company_intelligence_reader
# (load_current_workspace / WorkspaceChainNotPublished). This alias keeps
# the exact pre-A5C exception identity (name AND raise sites) importable
# from this module — every caller and test that constructs or catches
# ``_PriorWorkspaceNotPublished`` keeps working unchanged; it IS the shared
# reader's exception class, not a lookalike.
_PriorWorkspaceNotPublished = ci_reader.WorkspaceChainNotPublished


def _raw_load_prior_workspace(event_id: str, *, base_url: str | None = None) -> dict[str, Any]:
    """Fetch the last published workspace for *event_id* from the public
    origin — a thin delegator to the ONE shared reader implementation
    (``engine.neuralweb.company_intelligence_reader.load_current_workspace``,
    frozen spec D1/D3). Raises ``_PriorWorkspaceNotPublished`` on a clean 404
    (manifest or workspace) or an absent-generation manifest. Raises any
    OTHER exception (network error, timeout, non-2xx, malformed JSON) on a
    genuine fetch failure — never returns ``None`` on failure; disposition
    classification is ``load_prior_workspace``'s job.
    """
    return ci_reader.load_current_workspace(event_id, base_url=base_url)


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
    # IMCE A5C (frozen spec D1/D3): the marker/generation-manifest scan now
    # lives ONCE, in the shared reader
    # (``engine.neuralweb.company_intelligence_reader.
    # find_current_event_id_for_company``). This wrapper translates that
    # function's typed ``WorkspaceChainIntegrityError`` — and any other
    # genuine fetch failure — into this module's own
    # ``PriorWorkspaceFetchFailed`` with the same line-start ``::warning``,
    # preserving the exact NEW-6/NEW-7 anomaly discipline byte-for-byte.
    issuer = issuer_for_ticker(ticker)
    if issuer is None:
        return None

    def _anomaly(detail: str) -> PriorWorkspaceFetchFailed:
        print(
            "::warning title=event-workspace-prior-fetch-failed::"
            f"{ticker}: {detail} — refusing to treat this as no-prior-to-carry",
            flush=True,
        )
        return PriorWorkspaceFetchFailed(f"{ticker}: {detail}")

    try:
        matched_event_id = ci_reader.find_current_event_id_for_company(
            issuer.company_id, base_url=base_url,
        )
    except ci_reader.WorkspaceChainIntegrityError as exc:
        raise _anomaly(str(exc)) from exc
    except Exception as exc:  # noqa: BLE001 - every other failure is a genuine fetch failure, never silently absent
        raise _anomaly(f"current-generation read failed ({type(exc).__name__}: {exc})") from exc

    if matched_event_id is None:
        return None  # (i) no nest yet, or (ii) well-formed, no entry for this issuer
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


# NIT-21/MINOR-17 (Opus red-team verification round 2, 2026-08-23): the
# pre-A5C single-newest acquisition function (acquire_and_build_homebuilder_
# workspace) is DELETED. It had no production caller once discover_new_
# homebuilder_revisions became the sole per-ticker mechanism (BLOCKER-2),
# and it still carried the two-clock violation (observed_at=source_clock)
# fixed everywhere else — keeping it around, unused, would only mislead a
# future session into resurrecting it. Its own unit test at
# tests/test_issuer_profiles_a5a.py (which called this function directly)
# was retargeted to discover_new_homebuilder_revisions in the same commit.


# ---------------------------------------------------------------------------
# IMCE A5C discovery (frozen spec B) — ALL not-yet-represented qualifying
# revisions per issuer, ascending SEC acceptance order, chained through the
# manifest chain (frozen spec A). The AAPL flagship keeps its own frozen-
# accession replay path above UNCHANGED (B5) — this section is homebuilder-
# only. Scope note (interpretation, named in the PR body): the discovery
# WINDOW stays exactly what ``_select_newest_results_rows`` already reads
# (SEC submissions.json's ``recent`` block) — this PR widens "take the
# single newest" to "take every not-yet-represented row in that SAME
# existing window", never adds a new unbounded backfill surface (no
# ``files`` shard walk in discovery mode, unchanged from before this PR).
# ---------------------------------------------------------------------------


def _fetch_submissions_candidates(cik: str, *, http_get: HttpGet) -> list[dict[str, Any]]:
    """Every qualifying Item-2.02 8-K/8-K/A row from SEC submissions.recent,
    ASCENDING by acceptance_datetime (oldest first) — B1. Raises
    ``RefreshError`` only on a hard SEC submissions access failure; an
    individual row is never filtered here beyond the existing admission
    test (``_select_newest_results_rows``)."""
    cik_int = int(cik)
    status, body = http_get(_SUBMISSIONS_URL.format(cik=cik_int))
    if status != 200:
        raise RefreshError(f"SEC submissions unavailable for CIK {cik}: HTTP {status}")
    try:
        submissions = json.loads(body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise RefreshError(f"SEC submissions JSON invalid: {exc}") from exc
    if not isinstance(submissions, dict):
        raise RefreshError("SEC submissions filings block invalid")
    descending = _select_newest_results_rows(submissions_rows(submissions, block="recent"))
    return list(reversed(descending))


def _resolve_exhibit_for_row(row: Mapping[str, Any], *, cik: str, http_get: HttpGet) -> dict[str, Any] | None:
    """Resolve one candidate row's EX-99.1 exhibit body, or ``None`` (skip,
    never fail — B4) if no usable exhibit is found for THIS row. A skip here
    must never orphan a LATER row for the same or another event; the caller
    simply continues to the next candidate."""
    row_accession = str(row.get("accessionNumber") or "")
    if not row_accession:
        return None
    cik_int = int(cik)
    acc_nodash = row_accession.replace("-", "")
    archive_base = f"{_ARCHIVES}/{cik_int}/{acc_nodash}"
    time.sleep(_PACE_S)
    header_status, header_body = http_get(f"{archive_base}/{row_accession}-index-headers.html")
    if header_status != 200:
        return None
    filename = _select_exhibit_99_1(_parse_sgml_manifest(header_body.decode("utf-8", errors="replace")))
    if not filename:
        return None
    exhibit_url = f"{archive_base}/{filename}"
    time.sleep(_PACE_S)
    exhibit_status, exhibit_body = http_get(exhibit_url)
    if exhibit_status != 200 or not exhibit_body.strip():
        return None
    try:
        exhibit_text = exhibit_body.decode("utf-8")
    except UnicodeDecodeError:
        exhibit_text = exhibit_body.decode("latin-1")
    if not exhibit_text.strip():
        return None
    try:
        acceptance = _iso_z(row.get("acceptanceDateTime"))
    except RefreshError:
        return None
    return {
        "cik": cik,
        "accession": row_accession,
        "form": row.get("form") or "",
        "filing_date": row.get("filingDate") or "",
        "acceptance_datetime": acceptance,
        "report_date": row.get("reportDate") or "",
        "exhibit_url": exhibit_url,
        "exhibit_body": exhibit_text,
        "items": row.get("items") or "",
    }


def _event_known_revisions(
    event_id: str, *, base_url: str | None = None,
) -> list[dict[str, Any]]:
    """ALL already-chain-represented revisions for *event_id*, OLDEST FIRST
    (ONE shared reader chain walk, D1/D3/B2). MINOR-9 (Opus red-team
    verification round 2, 2026-08-23): this deliberately returns the FULL
    ordered timeline, not merely "the newest" — a newly-discovered row can
    be a genuine BACKFILL (chronologically OLDER than what is already
    chain-represented, e.g. an original whose accession only became
    resolvable after its own amendment was already captured); finding that
    row's TRUE prior revision requires searching the whole timeline for the
    nearest entry strictly older than it, never assuming "the chain's
    overall newest" is always the right predecessor.

    A genuine chain-integrity failure or any other read failure is NEVER
    treated as "nothing represented" — it is re-raised as
    ``PriorWorkspaceFetchFailed`` so the caller's existing abort-the-whole-
    refresh discipline applies uniformly."""
    try:
        return list(ci_reader.read_event_source_revisions(event_id, base_url=base_url))
    except Exception as exc:  # noqa: BLE001 - chain-state ambiguity must never read as "nothing represented"
        print(
            "::warning title=event-workspace-chain-read-failed::"
            f"{event_id}: source-revision chain read failed ({type(exc).__name__}: {exc}) — "
            "refusing to treat this as no-prior-revision-represented",
            flush=True,
        )
        raise PriorWorkspaceFetchFailed(
            f"{event_id}: chain read failed ({type(exc).__name__}: {exc})"
        ) from exc


def _revision_accession(entry: Mapping[str, Any]) -> str | None:
    """The SEC accession recorded on one chain-revision receipt's own
    workspace body (the ``issuer_release`` source row), or None."""
    ws = entry.get("workspace") if isinstance(entry.get("workspace"), Mapping) else {}
    for source in ws.get("sources") or []:
        if isinstance(source, Mapping) and source.get("kind") == "issuer_release":
            accession = (source.get("filing_key") or {}).get("accession")
            return str(accession) if accession else None
    return None


def _nearest_older_revision(
    timeline: list[dict[str, Any]], *, before: str,
) -> Mapping[str, Any] | None:
    """MINOR-9: the entry in *timeline* with the LATEST ``source_available_at``
    that is STRICTLY older than *before* — never the timeline's overall
    newest entry, which may itself postdate *before* (a backfill scenario).
    Returns the entry's own workspace body, or None when nothing in the
    timeline precedes *before* at all (a genuine first-ever/backfilled-
    original revision, which correctly gets prior_*=None and publishes
    "complete")."""
    best_entry: Mapping[str, Any] | None = None
    best_avail: str | None = None
    for entry in timeline:
        avail = entry.get("source_available_at")
        if not avail or str(avail) >= before:
            continue
        if best_avail is None or str(avail) > best_avail:
            best_entry, best_avail = entry, str(avail)
    if best_entry is None:
        return None
    ws = best_entry.get("workspace")
    return ws if isinstance(ws, Mapping) else None


def discover_new_homebuilder_revisions(
    ticker: str,
    *,
    http_get: HttpGet = _http_get,
    tx_index_url: str = DEFAULT_TX_INDEX_URL,
    fetch_index: FetchIndex = fetch_global_index,
    fetch_body_fn: FetchBody = fetch_body,
    chain_state_loader: Callable[[str], list[dict[str, Any]]] | None = None,
    base_url: str | None = None,
    # PRODUCTION INCIDENT FIX (verification round 4, 2026-08-23 — FROZEN,
    # not open for redesign): Sol's law is "all newly observed qualifying
    # accessions SINCE THE CANONICAL PRIOR GENERATION" — the temporal
    # boundary this parameter implements was never wired before this fix,
    # so "not yet represented in the chain" alone admitted ALL of history
    # on first deploy. Production run 32652474368 (workflow_dispatch,
    # 2026-08-23) crawled each of the four homebuilders' ENTIRE SEC
    # "recent" submissions block back to 2010, resolving hundreds of
    # accessions' filing indexes (index-headers.html + exhibit, ~0.5s
    # each) before the job's 25-minute timeout killed it mid-step — it had
    # already published ~170 backfilled historical events as chained
    # generations (lawful, immutable history; never rewritten) by then.
    # *discovery_boundary* is the newest ``source_available_at`` already
    # represented across this ticker's issuer chain (the CALLER resolves
    # this via the SAME carry-forward read it already performs to seed
    # Phase 1's base snapshot — see refresh()'s Phase 1 loop — so this
    # costs ZERO additional R2 GETs). A row whose acceptance_datetime is
    # at-or-older than the boundary is OUTSIDE the discovery window BY LAW
    # — filtered on the raw submissions row alone, before ANY per-
    # accession HTTP fetch (index-headers/exhibit), and without a
    # ``::warning`` (it is not a "skipped candidate", B4's skip!=fail
    # discipline does not apply to it — it was never eligible to begin
    # with). ``None`` means genuinely no represented event yet for this
    # issuer (first-ever discovery) — see the current+prior-fiscal-year
    # bound applied below instead of an unbounded scan.
    discovery_boundary: str | None = None,
    # Test seam for the first-ever-discovery bound below; production
    # default is the real wall clock.
    today: date | None = None,
) -> list[tuple[str, dict[str, Any]]]:
    """Every not-yet-represented qualifying source revision for *ticker*,
    resolved and bound to its OWN ``event_workspace`` payload, ASCENDING by
    SEC acceptance order (B1). An original + its own 8-K/A amendment
    discovered in the SAME poll chain WITHIN this list itself, each
    revision's ``prior_*`` taken from the nearest STRICTLY OLDER entry in
    its OWN event's timeline (MINOR-9) — never a stale "chain's overall
    newest" read, which would be wrong for a genuine backfill.

    A row is admitted only if it is NEWER than *discovery_boundary* (the
    canonical prior generation's own knowledge) — or, when *discovery_
    boundary* is ``None`` (nothing represented yet for this issuer), only
    if its derived fiscal period falls within the current or immediately
    prior fiscal year (mirrors scripts/build_cycle_pattern_imce_
    prospective.py's own bounded candidate lookback convention on the A5B
    side — a mechanical/operational scan window, never a construction
    choice; a missed poll is covered on the NEXT one regardless, since
    events are content-addressed by (issuer, fiscal period), not by a
    "latest" pointer).

    Raises ``RefreshError`` on a hard SEC submissions access failure (fail-
    soft — the caller's existing per-ticker carry-forward handles this).
    Raises ``PriorWorkspaceFetchFailed`` straight through on a chain-read
    failure (hard abort — never silently treated as "nothing represented").
    A row lacking a usable EX-99.1, or whose exhibit disagrees with the
    discovery-derived fiscal period (F1 cross-check), is skipped (skip !=
    fail — B4) via a bare line-start ``::warning``, without orphaning any
    later row.
    """
    issuer = issuer_for_ticker(ticker)
    profile = profile_for_ticker(ticker)
    if issuer is None or profile is None:
        raise RefreshError(f"{ticker} has no registered A5A homebuilder identity/profile")

    loader = chain_state_loader or (lambda event_id: _event_known_revisions(event_id, base_url=base_url))
    candidates = _fetch_submissions_candidates(issuer.cik, http_get=http_get)

    resolved_today = today if today is not None else datetime.now(timezone.utc).date()
    # First-ever-discovery bound: current + immediately prior fiscal year,
    # ALL quarters — same shape as _CANDIDATE_YEARS_BACK=1/_CANDIDATE_
    # QUARTERS=(1,2,3,4) on the A5B side.
    first_publish_years = {resolved_today.year - 1, resolved_today.year}

    # event_id -> its own known+newly-built timeline this cycle (mutated as
    # new revisions are built, so a LATER row for the same event this cycle
    # correctly sees everything built so far as a candidate predecessor —
    # B3/MINOR-9).
    timelines: dict[str, list[dict[str, Any]]] = {}
    results: list[tuple[str, dict[str, Any]]] = []

    for row in candidates:
        row_accession = str(row.get("accessionNumber") or "")
        report_date = str(row.get("reportDate") or "")
        if not row_accession or not report_date:
            continue

        # PRODUCTION INCIDENT FIX: the temporal boundary, applied on the
        # RAW submissions row, before any per-accession HTTP fetch and
        # before even deriving the fiscal period. Out-of-window rows are
        # not "skipped candidates" (no warning) — they were never eligible.
        if discovery_boundary is not None:
            try:
                row_accepted_normalized = _iso_z(row.get("acceptanceDateTime"))
            except RefreshError as exc:
                print(
                    "::warning title=event-workspaces-discovery-skip::"
                    f"{ticker}: accession {row_accession} acceptanceDateTime unparseable ({exc}); skipped",
                    flush=True,
                )
                continue
            if row_accepted_normalized <= discovery_boundary:
                continue  # outside the discovery window BY LAW -- not a fail, no warning

        try:
            fiscal_period = fiscal_period_for_report_date(report_date, issuer.fiscal_year_end_month)
        except Exception as exc:  # noqa: BLE001 - an unresolvable period is a per-row skip, not a refusal
            print(
                "::warning title=event-workspaces-discovery-skip::"
                f"{ticker}: accession {row_accession} fiscal period unresolvable ({exc}); skipped",
                flush=True,
            )
            continue

        if discovery_boundary is None and fiscal_period.year not in first_publish_years:
            # First-ever discovery for this issuer: bounded to current +
            # prior fiscal year, never the whole recent block (the exact
            # incident this fix closes — unbounded admission on first
            # deploy). Not a "skip" either -- outside the bound by law.
            continue

        event_id = canonical_event_id(issuer.company_id, fiscal_period)

        if event_id not in timelines:
            timelines[event_id] = loader(event_id)
        timeline = timelines[event_id]

        represented_accessions = {
            accession for accession in (_revision_accession(entry) for entry in timeline)
            if accession
        }
        if row_accession in represented_accessions:
            continue  # B2: already represented in the chain

        resolved_row = _resolve_exhibit_for_row(row, cik=issuer.cik, http_get=http_get)
        if resolved_row is None:
            print(
                "::warning title=event-workspaces-discovery-skip::"
                f"{ticker}: accession {row_accession} skipped (no usable EX-99.1 exhibit)",
                flush=True,
            )
            continue

        stated_end = _stated_period_end(str(resolved_row["exhibit_body"]))
        if stated_end != fiscal_period.calendar_end:
            print(
                "::warning title=event-workspaces-discovery-skip::"
                f"{ticker}: accession {row_accession} computed fiscal quarter end "
                f"{fiscal_period.calendar_end} does not match the exhibit's own stated "
                f"period end ({stated_end!r}); skipped rather than minting a guessed identity",
                flush=True,
            )
            continue

        asof = date.fromisoformat(str(resolved_row["filing_date"]))
        pair = f"{ticker}/{fiscal_period.year}Q{fiscal_period.quarter}"
        transcript, transcript_sha256 = acquire_transcript_for(
            pair, tx_index_url, fetch_index=fetch_index, fetch_body_fn=fetch_body_fn, required=False,
        )
        # C2: a genuinely NEW/not-yet-represented revision is a first
        # observation — real wall-clock now, never the SEC acceptance clock.
        now = datetime.now(timezone.utc)
        row_accepted = resolved_row["acceptance_datetime"]
        # MINOR-9: the TRUE chronological predecessor — the newest entry
        # (known OR already built this cycle) STRICTLY OLDER than THIS
        # row's own source_available_at. A genuine backfill (nothing older
        # exists yet) correctly gets prior_*=None and publishes "complete".
        prior_ws = _nearest_older_revision(timeline, before=row_accepted)
        payload = build_event_workspace(
            registry=production_registry(),
            ticker=ticker,
            asof=asof,
            fiscal_period=fiscal_period,
            exhibit_body=str(resolved_row["exhibit_body"]),
            filing={key: value for key, value in resolved_row.items() if key != "exhibit_body"},
            transcript=transcript,
            transcript_sha256=transcript_sha256,
            observed_at=now,
            source_available_at=row_accepted,
            collector_rows=None,
            wire_record_found=False,
            prior_source_sha256=exhibit_source_sha256(prior_ws),
            prior_lifecycle_state=prior_lifecycle_state(prior_ws),
            prior_observed_at=prior_observed_at(prior_ws),
            profile=profile,
        )
        if payload.get("event_id") != event_id:
            raise RefreshError(f"{ticker} event_id drifted: {payload.get('event_id')}")
        results.append((event_id, payload))
        # B3/MINOR-9: insert the freshly-built revision into this event's
        # OWN timeline so a LATER row this cycle (its own later amendment,
        # or another backfill) correctly considers it as a candidate
        # predecessor too.
        timeline.append({"source_available_at": row_accepted, "workspace": payload})

    # MINOR-14: discovery must not lose revisions SILENTLY. This SEC
    # "recent" window is a ROLLING one (B1's own scope note) — if the
    # chain's newest already-represented revision predates the OLDEST row
    # still visible in this poll, a genuine intervening revision may have
    # rolled off the window between nightly polls and is no longer
    # discoverable through this mechanism at all. Log-only.
    #
    # NAMED LIMITATION (MINOR-14 residual (ii)): this is a PARTIAL-ROLLOVER
    # heuristic only. It can only compare the chain's newest known revision
    # against the oldest row STILL visible in the CURRENT poll — a TOTAL
    # rollover (every row that would have proven a gap has ALREADY scrolled
    # off the "recent" window, leaving nothing in `candidates` to compare
    # against) is undetectable BY CONSTRUCTION: there is no surviving
    # evidence in this poll to raise the flag from. This limitation is not
    # closed by this PR and must not be papered over with a false "covered"
    # claim.
    if candidates:
        # MINOR-14 residual (i): normalize BOTH sides through the SAME
        # _iso_z form before comparing — the raw SEC acceptanceDateTime
        # carries milliseconds ("...T16:30:00.000Z") while chain-published
        # source_available_at values are already millisecond-stripped
        # ("...T16:30:00Z"); comparing the two AS RAW STRINGS is unsound
        # (the "." sorts before "Z", so a raw-vs-normalized pair of the
        # SAME instant can compare unequal/out-of-order).
        try:
            oldest_visible_accepted = _iso_z(candidates[0].get("acceptanceDateTime"))
        except RefreshError:
            oldest_visible_accepted = ""
        # PRODUCTION INCIDENT FIX (round 4): the chain's newest known
        # revision IS discovery_boundary now — the caller already resolves
        # it from the SAME carry-forward read, so this heuristic "naturally
        # uses the same boundary" (frozen fix item 3) rather than
        # re-deriving it from a per-event_id timeline walk that the
        # boundary filter above may not even populate for a converged
        # ticker. Already normalized by the caller (lifecycle.source_
        # available_at is always stored via _iso()).
        newest_chain_known = discovery_boundary
        if oldest_visible_accepted and newest_chain_known and newest_chain_known < oldest_visible_accepted:
            print(
                "::warning title=event-workspace-discovery-window::"
                f"{ticker} chain gap may predate the submissions recent block "
                f"(chain's newest known revision {newest_chain_known} precedes the oldest row "
                f"still visible in this poll, {oldest_visible_accepted}) — an intervening "
                "revision may have rolled off the SEC recent-filings window and would not be "
                "discoverable through this mechanism (partial-rollover heuristic only; a total "
                "rollover leaves no evidence in this poll to detect)",
                flush=True,
            )

    return results


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
    # BLOCKER-2/MAJOR-6/MINOR-9 (Opus red-team, 2026-08-23): the homebuilder
    # acquisition call site is now SUBSUMED into discovery below —
    # homebuilder_prior_workspace_loader is no longer part of refresh()'s
    # own flow. NIT-25 (verification round 3, 2026-08-23): the OLD
    # single-newest acquire_and_build_homebuilder_workspace() this comment
    # used to describe as "still exists, independently testable" is now
    # DELETED entirely (NEW-NIT-21/MINOR-17, round 2) — its own direct unit
    # test at tests/test_issuer_profiles_a5a.py was retargeted to
    # discover_new_homebuilder_revisions in the same round. A SECOND,
    # clock-drifted rebuild of "the newest" row atop discovery's own
    # chained publish was exactly the architecture MINOR-9/MAJOR-6 named as
    # broken.
    #
    # NEW-4: the ticker-scoped carry-forward lookup (load_prior_workspace_for_ticker
    # by default), used whenever THIS cycle's discovery finds zero new
    # revisions (SEC reachable, nothing new) or fails to reach SEC at all —
    # either way the ticker's current published state must still be carried
    # into the running snapshot.
    homebuilder_carry_forward_loader: Callable[[str], Mapping[str, Any] | None] = load_prior_workspace_for_ticker,
    publish_generation: PublishFn = publish_event_workspaces,
    # IMCE A5C (frozen spec A2/B3): resolves the CURRENT top-level
    # event_workspaces marker (v1 or v2, or None on a genuinely fresh nest)
    # so this cycle's generation(s) can chain onto it. NEW-MINOR-18 (Opus
    # red-team verification round 2, 2026-08-23): returns the marker's own
    # RAW bytes alongside the parsed dict, so chain_previous_sha is computed
    # by hashing exactly what R2 actually stores — re-serializing the parsed
    # dict via canonical_json_bytes and hashing THAT is not guaranteed
    # byte-identical to the real object (key order, whitespace, a field this
    # reader does not round-trip) and would silently mint a wrong hash link.
    # Production default is the real R2 read; tests inject an explicit stub
    # (a fresh sandboxed nest has no real predecessor to fetch — see
    # tests/test_refresh_event_workspaces.py).
    current_marker_loader: Callable[[], tuple[bytes, Mapping[str, Any]] | None] = (
        ci_reader.fetch_current_workspace_marker_raw
    ),
    # IMCE A5C (frozen spec B): per-ticker discovery of ALL not-yet-
    # represented qualifying revisions, ascending — including whatever
    # would be "the newest" (MINOR-13: the real signature is keyword-heavy,
    # never a bare Callable[[str], ...]). Injectable for tests; production
    # default is discover_new_homebuilder_revisions.
    homebuilder_discovery: Callable[..., list[tuple[str, dict[str, Any]]]] | None = None,
) -> int:
    """Acquire sources → build → write sibling nest → publish marker-last.

    IMCE A5C (frozen spec B/C): the AAPL flagship keeps its own frozen-
    accession single-revision replay (B5) — unchanged shape, now stamped
    with a real wall-clock ``observed_at`` and first-observation persistence
    (C2/C3) like every other issuer. Each HOMEBUILDER ticker's discovery
    yields EVERY not-yet-represented qualifying revision this cycle
    (B1/B2) — including the newest, which is no longer separately
    reacquired (BLOCKER-2) — publishing ONE nest generation per discovered
    revision, chained in ascending SEC acceptance order (B3); each
    revision's ``prior_*`` continuity is the NEAREST entry in its OWN
    event's timeline that is strictly OLDER than it (never a stale "chain's
    overall newest" lookahead, and never simply "the previous item in this
    cycle's discovered list" either — a genuine BACKFILL can require
    pointing further back, or at nothing at all — MINOR-9's lineage fix
    lives inside ``discover_new_homebuilder_revisions`` itself). Resolution
    and publication are two separate passes (NEW-BLOCKER-16): Phase 1
    resolves EVERY ticker (discovery + carry-forward, zero writes) so the
    running snapshot is a COMPLETE nest before Phase 2 writes a single
    generation — no promoted marker can ever transiently omit a ticker
    that simply hadn't been visited yet. The common case (0 or 1 total new
    revision this cycle across every issuer) collapses Phase 2 to exactly
    one write+publish call, and the running snapshot always ends each
    ticker's slot at its OWN newest known revision (MAJOR-6). NIT-24
    (verification round 3, 2026-08-23): at a fiscal-quarter rollover, ONE
    cycle's discovery can legitimately publish TWO events for the same
    issuer at once (a late prior-quarter amendment alongside the fresh new
    quarter's original) — this is safe and self-clearing, never a special
    case here, because ``find_current_event_id_for_company``'s own double-
    match tie-break always resolves to the NEWEST fiscal period on every
    later carry-forward read.
    """
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
    # C2/C3: real wall-clock "now" for this build attempt; build_event_workspace
    # carries prior_observed_at forward instead whenever the source is unchanged.
    now = datetime.now(timezone.utc)
    payload = build_event_workspace(
        registry=apple_registry(),
        ticker="AAPL",
        asof=AAPL_CALL_DATE,
        fiscal_period=flagship_fiscal_period(),
        exhibit_body=str(filing["exhibit_body"]),
        filing={key: value for key, value in filing.items() if key != "exhibit_body"},
        transcript=transcript,
        transcript_sha256=transcript_sha256,
        observed_at=now,
        source_available_at=source_clock,
        collector_rows=None,
        wire_record_found=False,
        prior_source_sha256=exhibit_source_sha256(prior),
        prior_lifecycle_state=prior_lifecycle_state(prior),
        prior_observed_at=prior_observed_at(prior),
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
    #       by one cycle is the accepted cost. NIT-25 (verification round 3,
    #       2026-08-23): this used to also name the deleted
    #       acquire_and_build_homebuilder_workspace's own prior read as
    #       sharing this discipline — that function is gone (round 2). The
    #       real NORMAL-path event_id-keyed prior read today lives inside
    #       discover_new_homebuilder_revisions itself, via
    #       _event_known_revisions (which re-raises any genuine chain-read
    #       failure as PriorWorkspaceFetchFailed, never silently "nothing
    #       represented") — that path is caught by the PriorWorkspaceFetchFailed
    #       handler around the discover(...) call below, same abort
    #       discipline.
    #   (c) genuinely never published (no prior found by either lookup)
    #       and acquisition failed -> true skip, nothing to carry, and its
    #       absence next cycle correctly reads as first-publish.
    #
    # Accepted-cost note (MINOR-22, Opus red-team verification round 3,
    # 2026-08-23 — supersedes the round-2 note this replaces, which
    # undercounted the real R2 GET volume by roughly 4x): the two-phase
    # design pays ONE homebuilder_carry_forward_loader call per ticker
    # UNCONDITIONALLY in Phase 1 — whether or not that ticker's own
    # discovery found a new revision — to guarantee the base snapshot is
    # complete before Phase 2 writes anything (this is exactly what closes
    # NEW-BLOCKER-16: a triggering ticker's first write must never publish
    # a nest that is silently missing a ticker Phase 1 simply hadn't
    # reached yet). That ONE call is NOT one GET: load_prior_workspace_for_
    # ticker is find_current_event_id_for_company (marker + generation
    # manifest = 2 GETs) followed by load_prior_workspace (marker +
    # workspace object = 2 GETs) = 4 R2 GETs PER TICKER, 16/cycle across
    # HOMEBUILDER_TICKERS. Add the top-level marker read for chain bookkeeping
    # (current_marker_loader, 1 GET) and the flagship's own prior read
    # (load_prior_flagship_workspace = load_prior_workspace = marker +
    # workspace, 2 GETs): a QUIET cycle (zero new revisions anywhere) costs
    # roughly 19 R2 GETs on top of those, NOT ~4-10. On top of THAT, each
    # ticker's own discovery performs a FULL read_event_source_revisions
    # chain walk (1 marker + N generation manifests + M workspace objects,
    # growing with that event's own chain length) for every distinct
    # candidate event_id seen in the SEC "recent" window this cycle — the
    # chain-state loader call happens the FIRST time an event_id is seen
    # among candidates, BEFORE the already-represented check, so this walk
    # fires even when nothing about that ticker is new. On a quiet cycle
    # with one candidate event per ticker that is 4 additional chain walks,
    # each growing with how many generations that event has accumulated —
    # this is the real, dominant, and UNBOUNDED-with-chain-length cost, not
    # a fixed small constant. Both costs are paid once per cycle regardless
    # of how many revisions Phase 2 later replays (Phase 1 runs exactly
    # once). The abort-surface discipline is otherwise unchanged in shape:
    # any one ticker's failed carry-forward read still aborts the WHOLE
    # cycle (RefreshError, marker frozen on the last good generation)
    # rather than risk silently dropping a corrected event, and one
    # issuer's CDN blip delaying the whole cycle remains the accepted cost.
    # A bounded retry on these reads, and/or a chain-walk cache keyed by
    # event_id within one cycle, are possible future reductions —
    # deliberately NOT added in this PR.
    workspaces: dict[str, dict[str, Any]] = {FLAGSHIP_EVENT_ID: payload}
    target = Path(out_dir) if out_dir is not None else Path("data/company_intelligence")

    # IMCE A5C (frozen spec A2): resolve the predecessor generation this
    # cycle's writes chain onto — the currently-published marker (v1 or v2),
    # or None only for a genuine first-ever generation of the nest.
    try:
        current_marker_raw = current_marker_loader()
    except Exception as exc:  # noqa: BLE001 - a genuine failure to read the current marker must abort
        raise RefreshError(f"failed to read the current event workspace marker: {exc}") from exc
    if current_marker_raw is not None:
        current_marker_bytes, current_marker = current_marker_raw
    else:
        current_marker_bytes, current_marker = None, None
    original_current_generation_id = (
        str(current_marker.get("generation_id") or "") or None if current_marker is not None else None
    )
    chain_previous_id = original_current_generation_id
    # NEW-MINOR-18: hash the marker's own RAW bytes — never a re-serialization
    # of the parsed dict — so the chain link matches what R2 actually stores.
    chain_previous_sha = (
        sha256(current_marker_bytes).hexdigest()
        if current_marker_bytes is not None and original_current_generation_id else None
    )
    # MINOR-9/MAJOR-6 (Opus red-team, 2026-08-23): the LAST workspaces
    # snapshot actually published this cycle, if any — the closing write
    # below must semantic-no-op against THIS (the just-promoted generation),
    # never mint a redundant third generation for byte-identical content
    # that a per-ticker chained write already published.
    last_published_snapshot: dict[str, dict[str, Any]] | None = None

    # NEW-BLOCKER-16 (Opus red-team verification round 2, 2026-08-23 —
    # FROZEN FIX, not open for redesign): refresh() resolves EVERY
    # homebuilder ticker BEFORE writing anything, then publishes. The prior
    # single-pass per-ticker loop wrote a triggering ticker's first
    # generation before LATER tickers in HOMEBUILDER_TICKERS had been
    # carried forward into `workspaces` at all — a live verifier probe
    # caught exactly this: marker generation 0 (an earlier ticker's own
    # first chained write) carried a lower event_count with a LATER ticker
    # silently ABSENT, only reaching the full event_count once that later
    # ticker was visited in the same cycle. A whole-nest snapshot with a
    # member silently missing is indistinguishable downstream from "that
    # ticker was never published" — exactly the failure mode NEW-4/NEW-8
    # above exist to prevent, reintroduced here by loop ORDER rather than
    # by a missing carry-forward call.
    #
    # PHASE 1 (resolution only, zero writes): for every ticker, run
    # carry-forward THEN discovery, but instead of writing immediately:
    # (a) seed `workspaces[event_id]` with the ticker's CURRENT published
    # state via an UNCONDITIONAL carry-forward read (whether or not
    # discovery ALSO found new revisions — see the Accepted-cost note
    # above), and (b) collect each triggering ticker's own ascending
    # new-revision sequence into `sequences` for Phase 2 to replay. Every
    # abort surface (chain-read failure, carry-forward failure) fires
    # HERE, before any write — a Phase 1 abort leaves the marker
    # completely untouched, same as before.
    #
    # PRODUCTION INCIDENT FIX (verification round 4, 2026-08-23): carry-
    # forward now runs BEFORE discover() (was AFTER) — reordered, not
    # merely relabeled, because discover() needs the carry-forward read's
    # OWN result as its discovery_boundary (Sol's law: "since the
    # CANONICAL PRIOR GENERATION"). Computing the boundary from a SECOND,
    # separate read would double the per-ticker R2 GET cost this exact
    # ordering avoids; the carry-forward call itself is unchanged in
    # shape, just moved earlier, so its own abort discipline (below) is
    # unchanged.
    discover = homebuilder_discovery or discover_new_homebuilder_revisions
    sequences: dict[str, list[tuple[str, dict[str, Any]]]] = {}
    for ticker in HOMEBUILDER_TICKERS:
        try:
            current_prior = homebuilder_carry_forward_loader(ticker)
        except Exception as carry_exc:  # noqa: BLE001
            # ANY exception from the carry-forward lookup means we cannot
            # confirm nothing is lost — uniform with the flagship's own
            # handler above: only an explicit clean None return may mean
            # "nothing to carry."
            raise RefreshError(
                f"{ticker}: carry-forward lookup for the Phase 1 base snapshot failed — refusing to "
                f"publish a nest that might silently drop a corrected event: {carry_exc}"
            ) from carry_exc
        discovery_boundary: str | None = None
        if current_prior is not None:
            current_event_id = str(current_prior.get("event_id") or "")
            if not current_event_id:
                raise RefreshError(f"{ticker}: carried-forward prior workspace has no event_id")
            workspaces[current_event_id] = dict(current_prior)
            boundary_raw = (current_prior.get("lifecycle") or {}).get("source_available_at")
            discovery_boundary = str(boundary_raw) if boundary_raw else None

        try:
            new_revisions = discover(
                ticker,
                http_get=http_get,
                tx_index_url=tx_index_url,
                fetch_index=fetch_index,
                fetch_body_fn=fetch_body_fn,
                discovery_boundary=discovery_boundary,
            )
        except PriorWorkspaceFetchFailed as exc:
            # A genuine chain-integrity/network failure while discovering
            # history must hard-abort — never silently treated as "nothing
            # to discover" (mirrors the flagship's own prior-fetch-failure
            # discipline above).
            raise RefreshError(
                f"{ticker}: source-revision discovery failed — refusing to publish a nest that "
                f"might silently drop a corrected event: {exc}"
            ) from exc
        except Exception as exc:  # noqa: BLE001 - SEC access failure during discovery is fail-soft
            # The carry-forward read above ALREADY seeded workspaces[...]
            # (or correctly left this ticker's slot untouched when
            # genuinely nothing was ever published) — reordering means
            # there is nothing further to carry here, only to log.
            print(
                "::warning title=event-workspaces::"
                f"{ticker} discovery failed; carry-forward state (if any) already applied "
                f"(class={type(exc).__name__}): {exc}",
                flush=True,
            )
            log.info("%s: discovery failed; carry-forward already applied above (%s)", ticker, exc)
            continue

        if new_revisions:
            sequences[ticker] = new_revisions

    # PHASE 2 (writes only): `workspaces` is now COMPLETE — every ticker
    # already holds either its carried-forward current state (Phase 1
    # above) or is about to have its own new revisions applied below.
    # Publish each triggering ticker's ascending revisions as its own
    # chained generation, in HOMEBUILDER_TICKERS order (B3: promote once
    # PER generation, immediately after each write — every intermediate
    # immutable generation is therefore always fully uploaded before any
    # later marker references it). Because Phase 1 already seeded every
    # OTHER ticker's slot, the very FIRST write below already contains a
    # complete nest — no promoted marker can ever transiently omit a
    # ticker Phase 1 has already resolved (NEW-BLOCKER-16).
    for ticker in HOMEBUILDER_TICKERS:
        for event_id, hb_payload in sequences.get(ticker, []):
            workspaces[event_id] = hb_payload
            generation_dir = write_workspace_generation(
                target,
                dict(workspaces),
                generated_at=source_clock,
                previous_generation_id=chain_previous_id,
                previous_manifest_sha256=chain_previous_sha,
            )
            print(
                "event workspaces: validated "
                f"events={sorted(workspaces)} generation={generation_dir.name} "
                f"chained_revision={event_id}"
            )
            publish_rc = publish_generation(target, dry_run=dry_run)
            if publish_rc == PUBLISH_CONFLICT:
                print("event workspaces: sibling-marker promotion lost a safe compare-and-swap race")
                return publish_rc
            if publish_rc != 0:
                raise RefreshError(f"event workspace publish failed with exit code {publish_rc}")
            manifest_body = (target / "event_workspaces" / "manifest.json").read_bytes()
            chain_previous_id = generation_dir.name
            chain_previous_sha = sha256(manifest_body).hexdigest()
            last_published_snapshot = dict(workspaces)

    # MINOR-9/MAJOR-6: if the LAST thing published this cycle (a per-ticker
    # chained write) already reflects the CURRENT, fully-assembled
    # `workspaces` dict byte-for-byte, there is NOTHING left to write — a
    # closing write here would mint a REDUNDANT generation for content a
    # write above already published (same content, deeper chain link only).
    if last_published_snapshot is not None and last_published_snapshot == workspaces:
        print(
            "event workspaces: validated "
            f"events={sorted(workspaces)} generation={chain_previous_id} "
            "source_clock=" + source_clock + " (closing write skipped: no change since the last chained publish)"
        )
        return 0

    # Final combined write (IMCE A5C A4: preserve the semantic no-op). If NO
    # discovery step advanced the chain this cycle (chain_previous_id is
    # unchanged from the marker read above) AND the freshly-assembled
    # workspaces content, hashed atop the CURRENT generation's OWN
    # predecessor, reproduces that CURRENT generation_id exactly, this
    # cycle's content is byte-identical to what is already published — reuse
    # the SAME chain link (never advance) so the write/publish short-
    # circuits before minting or PUTting anything new.
    final_previous_id, final_previous_sha = chain_previous_id, chain_previous_sha
    if (
        chain_previous_id == original_current_generation_id
        and current_marker is not None
        and current_marker.get("schema") == MANIFEST_SCHEMA_V2
    ):
        candidate_previous_id = current_marker.get("previous_generation_id")
        candidate_previous_sha = current_marker.get("previous_manifest_sha256")
        candidate_id = preview_generation_identity(
            workspaces, source_clock, previous_generation_id=candidate_previous_id,
        )
        if candidate_id == original_current_generation_id:
            final_previous_id, final_previous_sha = candidate_previous_id, candidate_previous_sha

    generation_dir = write_workspace_generation(
        target,
        workspaces,
        generated_at=source_clock,
        previous_generation_id=final_previous_id,
        previous_manifest_sha256=final_previous_sha,
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
