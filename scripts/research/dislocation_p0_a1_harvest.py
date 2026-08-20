#!/usr/bin/env python3
"""Price-blind Dislocation P0-A1 harvest: FTS enumeration, receipts, extraction.

Network allowlist: efts.sec.gov, data.sec.gov, www.sec.gov only.
Does not classify from query phrase. Does not read prices or outcomes.
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping
from urllib.parse import urlparse

import requests

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from scripts.research.dislocation_p0_a1_lib import (  # noqa: E402
    ALLOWED_HOSTS,
    AMENDMENT_FORMS,
    BLOCKED_FAMILIES,
    CONTROL_FAMILIES,
    FORMS,
    FTS_CAP,
    LEXICON,
    PAGE_SIZE,
    PRIMARY_FAMILIES,
    QUOTAS,
    RAW_CANDIDATE_FLOOR,
    SEED,
    WINDOWS,
    AccessLog,
    BlindWorkspaceError,
    annual_shards,
    assert_allowed_url,
    assert_blind_workspace,
    authority_flags,
    base_form,
    build_query_ledger,
    canonical_accession,
    canonical_cik,
    canonical_json,
    client_side_form_ok,
    clock_quality,
    decode_document,
    era_for_filed_on,
    extract_pass,
    forbidden_market_fields,
    is_amendment,
    is_design_excluded,
    lexicon_sha256,
    normalize_form,
    parse_html_acceptance,
    parse_iso_acceptance,
    parse_sgml_acceptance,
    query_cell_id,
    query_ledger_sha256,
    select_quota_rows,
    selection_key,
    sha256_bytes,
    sha256_text,
    split_date_range,
    ticker_from_display_name,
)

ENDPOINT = "https://efts.sec.gov/LATEST/search-index"
ARCHIVE_ORIGIN = "https://www.sec.gov/Archives/edgar/data"
USER_AGENT = "MastermindX dislocation-p0-a1 research@mastermind-x.com"
PACE_SECONDS = 0.30
TIMEOUT_SECONDS = 45
MAX_RETRIES = 3
HEADER_BYTES = 65536


def utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def session() -> requests.Session:
    sess = requests.Session()
    sess.headers.update(
        {
            "User-Agent": USER_AGENT,
            "Accept": "application/json,text/html,application/xhtml+xml,*/*",
        }
    )
    return sess


def request(
    sess: requests.Session,
    access: AccessLog,
    url: str,
    *,
    params: dict[str, Any] | None = None,
    headers: dict[str, str] | None = None,
    raw: bool = False,
) -> Any:
    assert_allowed_url(url)
    access.fetch_url(url if not params else f"{url}?{sorted(params.items())}")
    last: Exception | None = None
    for attempt in range(MAX_RETRIES):
        try:
            response = sess.get(
                url,
                params=params,
                timeout=TIMEOUT_SECONDS,
                headers=headers,
            )
            if response.status_code in (429, 500, 502, 503, 504):
                raise requests.HTTPError(
                    f"HTTP {response.status_code}", response=response
                )
            response.raise_for_status()
            if raw:
                return response.content
            ctype = (response.headers.get("Content-Type") or "").lower()
            text = response.text
            if "json" in ctype or text.lstrip().startswith(("{", "[")):
                try:
                    payload = response.json()
                except ValueError:
                    payload = json.loads(text)
                if not isinstance(payload, dict) and not isinstance(payload, list):
                    raise RuntimeError("SEC returned non-object JSON")
                return payload
            return text
        except Exception as exc:  # noqa: BLE001 — bounded retry then typed fail
            last = exc
            if attempt + 1 < MAX_RETRIES:
                time.sleep(1.5 * (attempt + 1))
    raise RuntimeError(f"SEC request failed for {url}: {last}")


def total_hits(payload: dict) -> int:
    total = ((payload.get("hits") or {}).get("total"))
    if isinstance(total, dict):
        total = total.get("value")
    try:
        value = int(total or 0)
    except (TypeError, ValueError):
        return 0
    if payload.get("took") is not None and value > FTS_CAP:
        return FTS_CAP
    # SEC reports capped totals as 10000.
    return value


def parse_hit(hit: dict) -> dict[str, Any] | None:
    source = hit.get("_source") or {}
    hit_id = str(hit.get("_id") or "").strip()
    if not hit_id or not isinstance(source, dict):
        return None
    accession_from_id, _, filename = hit_id.partition(":")
    display_names = source.get("display_names") or []
    ciks = source.get("ciks") or []
    items = source.get("items") or []
    display_name = display_names[0] if display_names else None
    cik = canonical_cik(ciks[0] if ciks else None)
    accession = canonical_accession(source.get("adsh") or accession_from_id)
    form = normalize_form(source.get("form") or source.get("file_type"))
    filed_on = source.get("file_date")
    if filed_on is not None:
        filed_on = str(filed_on)[:10]
    return {
        "hit_id": hit_id,
        "accession": accession,
        "filename": filename or None,
        "form": form,
        "file_type": source.get("file_type"),
        "filed_on": filed_on,
        "display_name": display_name,
        "ticker": ticker_from_display_name(display_name),
        "cik": cik,
        "items": sorted(map(str, items)),
    }


def fts_page(
    sess: requests.Session,
    access: AccessLog,
    *,
    phrase: str,
    form: str,
    start: str,
    end: str,
    offset: int,
) -> dict[str, Any]:
    parsed = urlparse(ENDPOINT)
    if (
        parsed.scheme != "https"
        or parsed.netloc != "efts.sec.gov"
        or parsed.path != "/LATEST/search-index"
    ):
        raise BlindWorkspaceError("SEC FTS endpoint binding changed")
    payload = request(
        sess,
        access,
        ENDPOINT,
        params={
            "q": f'"{phrase}"',
            "startdt": start,
            "enddt": end,
            "forms": form,
            "from": offset,
            "size": PAGE_SIZE,
        },
    )
    if not isinstance(payload, dict):
        raise RuntimeError("SEC FTS returned non-object JSON")
    raw_hits = ((payload.get("hits") or {}).get("hits")) or []
    rows = [row for row in (parse_hit(hit) for hit in raw_hits) if row is not None]
    return {
        "total_hits": total_hits(payload),
        "rows": rows,
        "response_sha256": sha256_text(canonical_json(payload)),
    }


def enumerate_leaf(
    sess: requests.Session,
    access: AccessLog,
    *,
    phrase: str,
    form: str,
    start: str,
    end: str,
    cache: dict[str, Any],
) -> dict[str, Any]:
    key = canonical_json(
        {"phrase": phrase, "form": form, "start": start, "end": end}
    )
    if key in cache:
        return cache[key]
    try:
        first = fts_page(
            sess, access, phrase=phrase, form=form, start=start, end=end, offset=0
        )
    except Exception as exc:  # noqa: BLE001 — incomplete cell, not a crash
        result = {
            "start": start,
            "end": end,
            "complete": False,
            "refusal_reason": "INCOMPLETE_QUERY_CELL",
            "error": str(exc),
            "total_hits": 0,
            "rows": [],
            "response_sha256": sha256_text(str(exc)),
        }
        cache[key] = result
        return result
    time.sleep(PACE_SECONDS)
    total = int(first["total_hits"])
    if total >= FTS_CAP:
        split = split_date_range(start, end)
        if split is None:
            result = {
                "start": start,
                "end": end,
                "complete": False,
                "refusal_reason": "INCOMPLETE_QUERY_CELL",
                "total_hits": total,
                "rows": first["rows"],
                "response_sha256": first["response_sha256"],
            }
            cache[key] = result
            return result
        (ls, le), (rs, re) = split
        left = enumerate_leaf(
            sess, access, phrase=phrase, form=form, start=ls, end=le, cache=cache
        )
        right = enumerate_leaf(
            sess, access, phrase=phrase, form=form, start=rs, end=re, cache=cache
        )
        merged: dict[str, dict[str, Any]] = {}
        for row in left.get("rows", []) + right.get("rows", []):
            merged[row["hit_id"]] = row
        result = {
            "start": start,
            "end": end,
            "complete": bool(left.get("complete") and right.get("complete")),
            "refusal_reason": None
            if left.get("complete") and right.get("complete")
            else "INCOMPLETE_QUERY_CELL",
            "total_hits": int(left.get("total_hits") or 0) + int(right.get("total_hits") or 0),
            "rows": [merged[hit_id] for hit_id in sorted(merged)],
            "children": [left, right],
            "response_sha256": sha256_text(
                canonical_json([left.get("response_sha256"), right.get("response_sha256")])
            ),
        }
        cache[key] = result
        return result

    rows_by_id = {row["hit_id"]: row for row in first["rows"]}
    offset = PAGE_SIZE
    page_hashes = [first["response_sha256"]]
    complete = True
    page_error = None
    while offset < total:
        try:
            page = fts_page(
                sess, access, phrase=phrase, form=form, start=start, end=end, offset=offset
            )
        except Exception as exc:  # noqa: BLE001 — keep retrieved pages, mark incomplete
            complete = False
            page_error = str(exc)
            break
        time.sleep(PACE_SECONDS)
        page_hashes.append(page["response_sha256"])
        for row in page["rows"]:
            rows_by_id[row["hit_id"]] = row
        if not page["rows"]:
            break
        offset += PAGE_SIZE
    result = {
        "start": start,
        "end": end,
        "complete": complete,
        "refusal_reason": None if complete else "INCOMPLETE_QUERY_CELL",
        "error": page_error,
        "total_hits": total,
        "rows": [rows_by_id[hit_id] for hit_id in sorted(rows_by_id)],
        "response_sha256": sha256_text(canonical_json(page_hashes)),
    }
    cache[key] = result
    return result


def harvest_family(
    sess: requests.Session,
    access: AccessLog,
    family: str,
    work: Path,
    cache: dict[str, Any],
    cache_path: Path,
) -> dict[str, Any]:
    start, end = WINDOWS["full_2016_2025"]
    phrases = LEXICON[family]
    cells: list[dict[str, Any]] = []
    pool: dict[str, dict[str, Any]] = {}
    incomplete = 0
    for phrase in phrases:
        for form in FORMS:
            parent_id = query_cell_id(family, phrase, form, start, end)
            parent_rows: dict[str, dict[str, Any]] = {}
            parent_complete = True
            parent_hashes: list[str] = []
            parent_hits = 0
            for shard_start, shard_end in annual_shards(start, end):
                leaf = enumerate_leaf(
                    sess,
                    access,
                    phrase=phrase,
                    form=form,
                    start=shard_start,
                    end=shard_end,
                    cache=cache,
                )
                parent_hits += int(leaf.get("total_hits") or 0)
                parent_hashes.append(str(leaf.get("response_sha256") or ""))
                if not leaf.get("complete"):
                    parent_complete = False
                    incomplete += 1
                for row in leaf.get("rows") or []:
                    parent_rows[row["hit_id"]] = row
            cell = {
                "query_cell_id": parent_id,
                "family": family,
                "phrase": phrase,
                "base_form": form,
                "date_shard": {"start": start, "end": end},
                "complete": parent_complete,
                "refusal_reason": None if parent_complete else "INCOMPLETE_QUERY_CELL",
                "total_hits": parent_hits,
                "unique_hits": len(parent_rows),
                "query_receipt_sha256": sha256_text(canonical_json(parent_hashes)),
            }
            cells.append(cell)
            for row in parent_rows.values():
                form_norm = normalize_form(row.get("form"))
                if not client_side_form_ok(form_norm, form):
                    continue
                accession = canonical_accession(row.get("accession"))
                cik = canonical_cik(row.get("cik"))
                if not accession or not cik:
                    continue
                key = f"{cik}|{accession}"
                existing = pool.get(key)
                edge = {
                    "phrase": phrase,
                    "family_candidate": family,
                    "query_cell_id": cell["query_cell_id"],
                    "query_receipt_sha256": cell["query_receipt_sha256"],
                    "hit_id": row["hit_id"],
                }
                if existing is None:
                    pool[key] = {
                        **row,
                        "form": form_norm,
                        "cik": cik,
                        "accession": accession,
                        "family_candidate": family,
                        "query_edges": [edge],
                    }
                else:
                    existing["query_edges"].append(edge)
    cache_path.write_text(json.dumps(cache), encoding="utf-8")
    return {
        "family": family,
        "cells": cells,
        "incomplete_cells": incomplete,
        "pool": list(pool.values()),
    }


def attach_selection(row: dict[str, Any], family: str) -> dict[str, Any] | None:
    filed_on = row.get("filed_on")
    era = era_for_filed_on(filed_on)
    if era is None:
        return None
    cik = canonical_cik(row.get("cik"))
    accession = canonical_accession(row.get("accession"))
    form_family = base_form(row.get("form"))
    if not cik or not accession or not form_family:
        return None
    row = dict(row)
    row["era"] = era
    row["selection_key"] = selection_key(
        family=family,
        era=era,
        base=form_family,
        cik=cik,
        accession=accession,
    )
    row["is_amendment"] = is_amendment(row.get("form"))
    return row


def archive_urls(cik: str, accession: str) -> dict[str, str]:
    directory = f"{ARCHIVE_ORIGIN}/{int(cik)}/{accession.replace('-', '')}"
    return {
        "directory": directory,
        "index_json": f"{directory}/index.json",
        "index_htm": f"{directory}/{accession}-index.htm",
        "submission_txt": f"{directory}/{accession}.txt",
    }


def filing_receipt(
    sess: requests.Session,
    access: AccessLog,
    row: dict[str, Any],
) -> dict[str, Any]:
    cik = row["cik"]
    accession = row["accession"]
    urls = archive_urls(cik, accession)
    accepted_at = None
    primary_name = row.get("filename")
    source_bytes = b""
    index_json = None
    try:
        index_json = request(sess, access, urls["index_json"])
        time.sleep(PACE_SECONDS)
    except Exception as exc:  # noqa: BLE001 — typed receipt failure
        index_error = str(exc)
    else:
        index_error = None
        if not isinstance(index_json, dict):
            index_error = f"index.json was {type(index_json).__name__}"
            directory = {}
            items = []
        else:
            directory = index_json.get("directory") or {}
            items = directory.get("item") or []
        if isinstance(items, dict):
            items = [items]
        for item in items:
            if not isinstance(item, dict):
                continue
            name = str(item.get("name") or "")
            if name.lower().endswith((".htm", ".html", ".txt")) and not primary_name:
                if "index" not in name.lower() and name.lower() != f"{accession}.txt":
                    primary_name = name
    try:
        html = request(sess, access, urls["index_htm"])
        time.sleep(PACE_SECONDS)
        if isinstance(html, str):
            accepted_at = parse_html_acceptance(html)
    except Exception:
        html = None
    if not accepted_at:
        try:
            header = request(
                sess,
                access,
                urls["submission_txt"],
                headers={"Range": f"bytes=0-{HEADER_BYTES - 1}"},
                raw=True,
            )
            time.sleep(PACE_SECONDS)
            if isinstance(header, bytes):
                source_bytes = header
                accepted_at = parse_sgml_acceptance(header)
        except Exception:
            pass
    document_raw = b""
    archive_url = None
    if not primary_name:
        primary_name = f"{accession}.txt"
    archive_url = f"{urls['directory']}/{primary_name}"
    try:
        document_raw = request(sess, access, archive_url, raw=True)
        time.sleep(PACE_SECONDS)
    except Exception:
        document_raw = source_bytes
        archive_url = urls["submission_txt"]
    if not accepted_at and document_raw:
        accepted_at = parse_sgml_acceptance(document_raw)
    quality = clock_quality(accepted_at, row.get("filed_on"))
    receipt = {
        "cik": cik,
        "accession": accession,
        "form": row.get("form"),
        "accepted_at": accepted_at,
        "filed_on": row.get("filed_on"),
        "manifest_id": sha256_text(
            canonical_json({"cik": cik, "accession": accession, "accepted_at": accepted_at})
        ),
        "source_bytes_sha256": sha256_bytes(source_bytes or document_raw or b""),
        "amends_accession": None,
        "clock_quality": quality,
        "primary_document": primary_name,
        "archive_url": archive_url,
        "index_error": index_error,
    }
    return {
        "receipt": receipt,
        "document_raw": document_raw,
        "document_sha256": sha256_bytes(document_raw) if document_raw else None,
        "byte_length": len(document_raw) if document_raw else 0,
    }


def candidate_record(
    row: dict[str, Any],
    *,
    family: str,
    pool_sha: str,
    rank: int,
    receipt_pack: dict[str, Any],
    pass1: dict[str, Any] | None,
    pass2: dict[str, Any] | None,
) -> dict[str, Any]:
    edges = row.get("query_edges") or []
    first_edge = edges[0] if edges else {}
    receipt = receipt_pack["receipt"]
    documents = []
    if receipt_pack.get("document_raw"):
        spans = []
        for proposal in (pass1, pass2):
            if not proposal:
                continue
            for span in proposal.get("spans") or []:
                spans.append(
                    {
                        "span_id": span["span_id"],
                        "start": span["start"],
                        "end": span["end"],
                        "claim_field": span["claim_field"],
                        "excerpt": span["excerpt"],
                        "receipt_sha256": receipt_pack["document_sha256"],
                    }
                )
        documents.append(
            {
                "document_id": f"secdoc_{receipt_pack['document_sha256']}",
                "role": "primary",
                "archive_url": receipt.get("archive_url") or archive_urls(row["cik"], row["accession"])["submission_txt"],
                "content_sha256": receipt_pack["document_sha256"],
                "byte_length": receipt_pack["byte_length"],
                "retrieval_state": "STORED" if receipt_pack["document_raw"] else "MISSING",
                "evidence_spans": spans,
            }
        )
    classification = {
        "state": "UNCLASSIFIED",
        "event_family": None,
        "new_adverse_information_at_t0": "UNKNOWN",
        "adverse_uncertainty_at_t0": "UNKNOWN",
        "recoverability_evidence_at_t0": "UNKNOWN",
        "structural_impairment_at_t0": "UNKNOWN",
        "intent_orchestration": "UNKNOWN",
        "proposed_by": None,
    }
    if pass1:
        classification = {
            "state": pass1["state"],
            "event_family": pass1["event_family"],
            "new_adverse_information_at_t0": pass1["new_adverse_information_at_t0"],
            "adverse_uncertainty_at_t0": pass1["adverse_uncertainty_at_t0"],
            "recoverability_evidence_at_t0": pass1["recoverability_evidence_at_t0"],
            "structural_impairment_at_t0": pass1["structural_impairment_at_t0"],
            "intent_orchestration": "UNKNOWN",
            "proposed_by": pass1["proposed_by"],
        }
    record = {
        "schema": "mastermind.dislocation_p0.source_candidate.v1",
        "candidate_id": f"p0cand_{row['selection_key']}",
        "query_provenance": {
            "query_cell_id": first_edge.get("query_cell_id") or "",
            "family_candidate": family,
            "phrase": first_edge.get("phrase") or "",
            "base_form": base_form(row.get("form")) or "8-K",
            "date_shard": {
                "start": WINDOWS["full_2016_2025"][0],
                "end": WINDOWS["full_2016_2025"][1],
            },
            "query_receipt_sha256": first_edge.get("query_receipt_sha256") or ("0" * 64),
            "sec_hit_ids": [edge.get("hit_id") for edge in edges if edge.get("hit_id")] or [row.get("hit_id") or accession_fallback(row)],
        },
        "selection": {
            "seed": SEED,
            "partition": f"{family}|{row.get('era')}|{base_form(row.get('form'))}",
            "selection_key": row["selection_key"],
            "rank": rank,
            "candidate_pool_sha256": pool_sha,
            "review_state": "SOURCE_ACCEPTED",
            "refusal_reason": None,
        },
        "filing_receipt": {
            "cik": row["cik"],
            "accession": row["accession"],
            "form": row.get("form"),
            "accepted_at": receipt.get("accepted_at"),
            "filed_on": receipt.get("filed_on") or row.get("filed_on"),
            "report_date": None,
            "manifest_id": receipt.get("manifest_id"),
            "source_bytes_sha256": receipt.get("source_bytes_sha256") or ("0" * 64),
            "amends_accession": None,
            "clock_quality": receipt.get("clock_quality"),
        },
        "documents": documents,
        "classification": classification,
        "audit": {
            "state": "PENDING",
            "auditor": None,
            "verdict": "PENDING",
            "audited_at": None,
            "corrections": [],
        },
        "authority": {
            "can_rank": False,
            "can_gate": False,
            "can_size": False,
            "can_originate_signal": False,
            "can_escalate": False,
        },
    }
    return record


def accession_fallback(row: Mapping[str, Any]) -> str:
    return str(row.get("accession") or row.get("hit_id") or "unknown")


def write_json(path: Path, payload: Any) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False) + "\n"
    path.write_text(text, encoding="utf-8")
    return sha256_text(canonical_json(payload))


def cmd_inventory(root: Path, out: Path) -> int:
    access = AccessLog()
    present = assert_blind_workspace(root)
    ledger = build_query_ledger()
    report = {
        "schema": "mastermind.dislocation_p0.a1a_inventory.v1",
        "generated_at": utc_now(),
        "workspace_root": str(root),
        "price_firewall": "PASS",
        "present_forbidden_paths": present,
        "allowed_hosts": sorted(ALLOWED_HOSTS),
        "lexicon_sha256": lexicon_sha256(),
        "query_ledger_sha256": query_ledger_sha256(ledger),
        "a1_declared_ledger_sha256": ledger["a1_declared_ledger_sha256"],
        "a1_declared_ledger_status": ledger["a1_declared_ledger_status"],
        "query_cells": len(ledger["query_cells"]),
        "blocked_families": BLOCKED_FAMILIES,
        "authority": ledger["authority"],
        "access_log_sha256": access.digest(),
    }
    write_json(out, report)
    write_json(out.parent / "DISLOCATION_P0_SOURCE_QUERY_LEDGER_V1.json", ledger)
    print(canonical_json({
        "price_firewall": "PASS",
        "query_ledger_sha256": report["query_ledger_sha256"],
        "lexicon_sha256": report["lexicon_sha256"],
        "access_log_sha256": report["access_log_sha256"],
    }))
    return 0


def cmd_harvest(root: Path, out_dir: Path, families: list[str] | None) -> int:
    access = AccessLog()
    assert_blind_workspace(root)
    sess = session()
    work = out_dir / "work"
    work.mkdir(parents=True, exist_ok=True)
    cache_path = work / "fts_cache.json"
    cache: dict[str, Any] = {}
    if cache_path.exists():
        cache = json.loads(cache_path.read_text(encoding="utf-8"))
    chosen = families or list(PRIMARY_FAMILIES) + list(CONTROL_FAMILIES)
    family_outputs: dict[str, Any] = {}
    all_raw: list[dict[str, Any]] = []
    refusals: list[dict[str, Any]] = []
    for family in chosen:
        print(f"harvest {family}", flush=True)
        result = harvest_family(sess, access, family, work, cache, cache_path)
        prepared: list[dict[str, Any]] = []
        for row in result["pool"]:
            if is_design_excluded(
                ticker=row.get("ticker"),
                cik=row.get("cik"),
                display_name=row.get("display_name"),
            ):
                refusals.append(row | {"refusal_reason": "DESIGN_TOUCHED", "family": family})
                continue
            if row.get("is_amendment") or is_amendment(row.get("form")):
                tagged = attach_selection(row, family)
                if tagged:
                    refusals.append(tagged | {"refusal_reason": "AMENDMENT_NOT_ORIGIN", "family": family})
                else:
                    refusals.append(row | {"refusal_reason": "AMENDMENT_NOT_ORIGIN", "family": family})
                continue
            tagged = attach_selection(row, family)
            if tagged is None:
                refusals.append(row | {"refusal_reason": "DATE_ONLY_REFUSED", "family": family})
                continue
            prepared.append(tagged)
        pool_sha = sha256_text(canonical_json(
            [row["selection_key"] for row in sorted(prepared, key=lambda item: item["selection_key"])]
        ))
        selected, quota_refused = select_quota_rows(prepared, family=family)
        for row in quota_refused:
            refusals.append(row | {"family": family})
        family_outputs[family] = {
            "cells": result["cells"],
            "incomplete_cells": result["incomplete_cells"],
            "raw_unique_filings": len(prepared),
            "selected": len(selected),
            "pool_sha256": pool_sha,
            "quota": QUOTAS[family],
        }
        ranked = []
        for rank, row in enumerate(selected, start=1):
            ranked.append(row | {"family": family, "rank": rank, "pool_sha256": pool_sha})
            all_raw.append(ranked[-1])
        write_json(work / f"family_{family}.json", family_outputs[family])
        write_json(work / f"selected_{family}.json", ranked)
    persisted: dict[str, dict[str, Any]] = {}
    for path in sorted(work.glob("selected_*.json")):
        for row in json.loads(path.read_text(encoding="utf-8")):
            persisted[f"{row.get('family')}|{row.get('selection_key')}"] = row
    for row in all_raw:
        persisted[f"{row.get('family')}|{row.get('selection_key')}"] = row
    all_raw = list(persisted.values())
    write_json(out_dir / "A1B_FAMILY_COVERAGE.json", family_outputs)
    write_json(out_dir / "A1B_RAW_CANDIDATES.json", all_raw)
    write_json(out_dir / "A1F_REFUSAL_LEDGER.json", {
        "count": len(refusals),
        "by_reason": _count_reason(refusals),
        "sample_rows": [
            {
                "family": row.get("family"),
                "cik": row.get("cik"),
                "accession": row.get("accession"),
                "refusal_reason": row.get("refusal_reason"),
            }
            for row in refusals
            if row.get("refusal_reason") in {"DESIGN_TOUCHED", "AMENDMENT_NOT_ORIGIN", "INCOMPLETE_QUERY_CELL"}
        ][:200],
    })
    write_json(out_dir / "A1A_ACCESS_LOG.json", {
        "sha256": access.digest(),
        "banned_reads": access.banned_reads(),
        "hosts": sorted({urlparse(str(ev["target"])).hostname or "" for ev in access.events if ev["kind"] == "url"}),
        "event_count": len(access.events),
    })
    print(canonical_json({
        "raw_selected": len(all_raw),
        "refusals": len(refusals),
        "families": {key: value["selected"] for key, value in family_outputs.items()},
        "access_log_sha256": access.digest(),
    }))
    if len(all_raw) < RAW_CANDIDATE_FLOOR:
        print(f"BLOCKED: raw candidates {len(all_raw)} < {RAW_CANDIDATE_FLOOR}", flush=True)
        return 2
    return 0


def _count_reason(rows: list[dict[str, Any]]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for row in rows:
        reason = str(row.get("refusal_reason") or "UNKNOWN")
        counts[reason] = counts.get(reason, 0) + 1
    return counts


def cmd_extract(root: Path, out_dir: Path, limit: int | None) -> int:
    access = AccessLog()
    assert_blind_workspace(root)
    sess = session()
    raw_path = out_dir / "A1B_RAW_CANDIDATES.json"
    rows = json.loads(raw_path.read_text(encoding="utf-8"))
    if limit is not None:
        rows = rows[:limit]
    work = out_dir / "work"
    work.mkdir(parents=True, exist_ok=True)
    accepted_path = work / "extract_accepted.jsonl"
    refusal_path = work / "extract_refusals.jsonl"
    disagree_path = work / "extract_disagreements.jsonl"
    done_ids: set[str] = set()
    accepted: list[dict[str, Any]] = []
    refusals: list[dict[str, Any]] = []
    disagreements: list[dict[str, Any]] = []
    episodes: list[dict[str, Any]] = []
    if accepted_path.exists():
        for line in accepted_path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            record = json.loads(line)
            accepted.append(record)
            done_ids.add(record["candidate_id"])
            episodes.append({
                "episode_id": f"p0ep_{record['filing_receipt']['cik']}_{record['filing_receipt']['accession']}",
                "origin_candidate_id": record["candidate_id"],
                "cik": record["filing_receipt"]["cik"],
                "accession": record["filing_receipt"]["accession"],
                "family_candidate": record["query_provenance"]["family_candidate"],
                "accepted_at": record["filing_receipt"]["accepted_at"],
                "linked_transitions": [],
            })
    if refusal_path.exists():
        for line in refusal_path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            row = json.loads(line)
            refusals.append(row)
            done_ids.add(str(row.get("candidate_id") or f"p0cand_{row.get('selection_key')}"))
    if disagree_path.exists():
        for line in disagree_path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                disagreements.append(json.loads(line))
    for row in rows:
        candidate_id = f"p0cand_{row['selection_key']}"
        if candidate_id in done_ids:
            continue
        family = row["family"]
        try:
            pack = filing_receipt(sess, access, row)
        except Exception as exc:  # noqa: BLE001 — typed per-row refusal
            refused = row | {
                "candidate_id": candidate_id,
                "refusal_reason": "FILING_RECEIPT_UNAVAILABLE",
                "error": str(exc),
            }
            refusals.append(refused)
            with refusal_path.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(refused, sort_keys=True) + "\n")
            continue
        receipt = pack["receipt"]
        if receipt["clock_quality"] != "EXACT_SEC_ACCEPTANCE":
            refused = row | {
                "candidate_id": candidate_id,
                "refusal_reason": "ACCEPTED_AT_UNAVAILABLE"
                if receipt["clock_quality"] == "UNAVAILABLE"
                else "DATE_ONLY_REFUSED",
                "filing_receipt": receipt,
            }
            refusals.append(refused)
            with refusal_path.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(refused, sort_keys=True) + "\n")
            continue
        if not pack.get("document_raw"):
            refused = row | {
                "candidate_id": candidate_id,
                "refusal_reason": "DOCUMENT_UNAVAILABLE",
                "filing_receipt": receipt,
            }
            refusals.append(refused)
            with refusal_path.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(refused, sort_keys=True) + "\n")
            continue
        text = decode_document(pack["document_raw"])
        phrase = (row.get("query_edges") or [{}])[0].get("phrase") or ""
        pass1 = extract_pass(text, query_phrase=phrase, family_candidate=family, pass_id="pass1")
        pass2 = extract_pass(text, query_phrase=phrase, family_candidate=family, pass_id="pass2")
        if pass1["structural_impairment_at_t0"] != pass2["structural_impairment_at_t0"]:
            disagreement = {
                "candidate_id": candidate_id,
                "field": "structural_impairment_at_t0",
                "pass1": pass1["structural_impairment_at_t0"],
                "pass2": pass2["structural_impairment_at_t0"],
            }
            disagreements.append(disagreement)
            with disagree_path.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(disagreement, sort_keys=True) + "\n")
        if pass1["state"] == "REFUSED" and pass2["state"] == "REFUSED":
            refused = row | {
                "candidate_id": candidate_id,
                "refusal_reason": pass1.get("refusal_reason") or "NOT_AN_ADVERSE_EVENT",
                "filing_receipt": receipt,
            }
            refusals.append(refused)
            with refusal_path.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(refused, sort_keys=True) + "\n")
            continue
        record = candidate_record(
            row,
            family=family,
            pool_sha=row.get("pool_sha256") or ("0" * 64),
            rank=int(row.get("rank") or 0),
            receipt_pack=pack,
            pass1=pass1,
            pass2=pass2,
        )
        leaks = forbidden_market_fields(record)
        if leaks:
            raise BlindWorkspaceError(f"forbidden market fields: {leaks}")
        flags = authority_flags(record)
        if any(flags.values()):
            raise BlindWorkspaceError(f"authority flag true: {flags}")
        accepted.append(record)
        with accepted_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(record, sort_keys=True) + "\n")
        episodes.append({
            "episode_id": f"p0ep_{row['cik']}_{row['accession']}",
            "origin_candidate_id": record["candidate_id"],
            "cik": row["cik"],
            "accession": row["accession"],
            "family_candidate": family,
            "accepted_at": receipt["accepted_at"],
            "linked_transitions": [],
        })
        if len(accepted) % 10 == 0:
            print(f"extracted {len(accepted)} accepted / {len(refusals)} refused", flush=True)
    draft = {
        "schema": "mastermind.dislocation_p0.accepted_manifest_draft.v1",
        "generated_at": utc_now(),
        "seed": SEED,
        "n_accepted": len(accepted),
        "n_episodes": len(episodes),
        "authority": {
            "can_rank": False,
            "can_gate": False,
            "can_size": False,
            "can_originate_signal": False,
            "can_escalate": False,
        },
        "candidates": accepted,
        "episodes": episodes,
    }
    accepted_sha = write_json(out_dir / "A1_ACCEPTED_MANIFEST_DRAFT.json", draft)
    queue = {
        "schema": "mastermind.dislocation_p0.candidate_queue.v1",
        "generated_at": utc_now(),
        "n": len(accepted),
        "candidate_ids": [row["candidate_id"] for row in accepted],
        "candidates": accepted,
        "authority": draft["authority"],
    }
    queue_sha = write_json(out_dir / "A1_CANDIDATE_QUEUE.json", queue)
    write_json(out_dir / "A1F_DISAGREEMENT_LEDGER.json", {
        "count": len(disagreements),
        "rows": disagreements,
    })
    extract_refusals_path = out_dir / "A1F_EXTRACT_REFUSALS.json"
    write_json(extract_refusals_path, {"count": len(refusals), "rows": refusals})
    write_json(out_dir / "A1A_ACCESS_LOG_EXTRACT.json", {
        "sha256": access.digest(),
        "banned_reads": access.banned_reads(),
        "event_count": len(access.events),
    })
    print(canonical_json({
        "accepted": len(accepted),
        "episodes": len(episodes),
        "extract_refusals": len(refusals),
        "disagreements": len(disagreements),
        "queue_sha256": queue_sha,
        "draft_sha256": accepted_sha,
        "access_log_sha256": access.digest(),
    }))
    return 0


def cmd_report(out_dir: Path) -> int:
    coverage = json.loads((out_dir / "A1B_FAMILY_COVERAGE.json").read_text(encoding="utf-8")) if (out_dir / "A1B_FAMILY_COVERAGE.json").exists() else {}
    queue = json.loads((out_dir / "A1_CANDIDATE_QUEUE.json").read_text(encoding="utf-8")) if (out_dir / "A1_CANDIDATE_QUEUE.json").exists() else {}
    draft = json.loads((out_dir / "A1_ACCEPTED_MANIFEST_DRAFT.json").read_text(encoding="utf-8")) if (out_dir / "A1_ACCEPTED_MANIFEST_DRAFT.json").exists() else {}
    refusals = json.loads((out_dir / "A1F_REFUSAL_LEDGER.json").read_text(encoding="utf-8")) if (out_dir / "A1F_REFUSAL_LEDGER.json").exists() else {}
    extract_refusals = json.loads((out_dir / "A1F_EXTRACT_REFUSALS.json").read_text(encoding="utf-8")) if (out_dir / "A1F_EXTRACT_REFUSALS.json").exists() else {}
    disagreements = json.loads((out_dir / "A1F_DISAGREEMENT_LEDGER.json").read_text(encoding="utf-8")) if (out_dir / "A1F_DISAGREEMENT_LEDGER.json").exists() else {}
    access_path = out_dir / "A1A_ACCESS_LOG_EXTRACT.json"
    if not access_path.exists():
        access_path = out_dir / "A1A_ACCESS_LOG.json"
    access = json.loads(access_path.read_text(encoding="utf-8")) if access_path.exists() else {}
    accepted = draft.get("candidates") or queue.get("candidates") or []
    modern = sum(
        1
        for row in accepted
        if str((row.get("filing_receipt") or {}).get("accepted_at") or "")[:4] >= "2022"
    )
    by_family: dict[str, int] = {}
    by_form: dict[str, int] = {}
    for row in accepted:
        family = ((row.get("query_provenance") or {}).get("family_candidate")) or "UNKNOWN"
        by_family[family] = by_family.get(family, 0) + 1
        form = (row.get("filing_receipt") or {}).get("form") or "UNKNOWN"
        by_form[str(form)] = by_form.get(str(form), 0) + 1
    shortfalls: list[dict[str, Any]] = []
    for family in list(PRIMARY_FAMILIES) + list(CONTROL_FAMILIES):
        have = by_family.get(family, 0)
        need = int(QUOTAS[family]["source_target"])
        if have < need:
            shortfalls.append({"family": family, "have": have, "need": need})
    for family, reason in BLOCKED_FAMILIES.items():
        shortfalls.append({"family": family, "have": 0, "need": int(QUOTAS[family]["source_target"]), "blocked": reason})
    report = {
        "schema": "mastermind.dislocation_p0.a1g_coverage.v1",
        "generated_at": utc_now(),
        "raw_selected": sum(int(row.get("selected") or 0) for row in coverage.values()) if isinstance(coverage, dict) else 0,
        "accepted": len(accepted),
        "episodes": len(draft.get("episodes") or []),
        "modern_accepted": modern,
        "by_family": by_family,
        "by_form": by_form,
        "quota_shortfalls": shortfalls,
        "refusals": refusals.get("count"),
        "extract_refusals": extract_refusals.get("count"),
        "disagreements": disagreements.get("count"),
        "access_log_sha256": access.get("sha256"),
        "banned_reads": access.get("banned_reads") or [],
        "blocked_families": BLOCKED_FAMILIES,
        "authority": {
            "can_rank": False,
            "can_gate": False,
            "can_size": False,
            "can_originate_signal": False,
            "can_escalate": False,
        },
        "fable_audit_command": (
            "python3 scripts/research/dislocation_p0_a1_harvest.py report "
            "--out research/dislocation_intelligence/p0_a1"
        ),
    }
    write_json(out_dir / "A1G_COVERAGE_REPORT.json", report)
    print(canonical_json(report))
    return 0


def phrase_family_map() -> dict[str, str]:
    mapping: dict[str, str] = {}
    for family, phrases in LEXICON.items():
        for phrase in phrases:
            mapping[phrase] = family
    return mapping


def pool_from_cache(cache: dict[str, Any], family: str) -> tuple[list[dict[str, Any]], int]:
    start, end = WINDOWS["full_2016_2025"]
    phrases = set(LEXICON[family])
    cells: dict[str, dict[str, Any]] = {}
    pool: dict[str, dict[str, Any]] = {}
    incomplete = 0
    for key, leaf in cache.items():
        try:
            meta = json.loads(key) if key.startswith("{") else None
        except json.JSONDecodeError:
            meta = None
        if not isinstance(meta, dict):
            continue
        phrase = meta.get("phrase")
        form = meta.get("form")
        if phrase not in phrases or form not in FORMS:
            continue
        if not leaf.get("complete"):
            incomplete += 1
        parent_id = query_cell_id(family, phrase, form, start, end)
        cell = cells.setdefault(
            parent_id,
            {
                "query_cell_id": parent_id,
                "family": family,
                "phrase": phrase,
                "base_form": form,
                "date_shard": {"start": start, "end": end},
                "complete": True,
                "refusal_reason": None,
                "total_hits": 0,
                "unique_hits": 0,
                "query_receipt_sha256": "0" * 64,
                "_hashes": [],
            },
        )
        cell["total_hits"] += int(leaf.get("total_hits") or 0)
        cell["_hashes"].append(str(leaf.get("response_sha256") or ""))
        if not leaf.get("complete"):
            cell["complete"] = False
            cell["refusal_reason"] = "INCOMPLETE_QUERY_CELL"
        for row in leaf.get("rows") or []:
            form_norm = normalize_form(row.get("form"))
            if not client_side_form_ok(form_norm, form):
                continue
            accession = canonical_accession(row.get("accession"))
            cik = canonical_cik(row.get("cik"))
            if not accession or not cik:
                continue
            edge = {
                "phrase": phrase,
                "family_candidate": family,
                "query_cell_id": parent_id,
                "query_receipt_sha256": leaf.get("response_sha256") or ("0" * 64),
                "hit_id": row.get("hit_id"),
            }
            key_id = f"{cik}|{accession}"
            existing = pool.get(key_id)
            if existing is None:
                pool[key_id] = {
                    **row,
                    "form": form_norm,
                    "cik": cik,
                    "accession": accession,
                    "family_candidate": family,
                    "query_edges": [edge],
                }
            else:
                existing["query_edges"].append(edge)
    cell_list = []
    for cell in cells.values():
        hashes = cell.pop("_hashes", [])
        cell["query_receipt_sha256"] = sha256_text(canonical_json(hashes))
        cell_list.append(cell)
    return list(pool.values()), incomplete


def select_family_pool(pool: list[dict[str, Any]], family: str) -> tuple[list[dict[str, Any]], list[dict[str, Any]], str, int]:
    prepared: list[dict[str, Any]] = []
    refusals: list[dict[str, Any]] = []
    for row in pool:
        if is_design_excluded(
            ticker=row.get("ticker"),
            cik=row.get("cik"),
            display_name=row.get("display_name"),
        ):
            refusals.append(row | {"refusal_reason": "DESIGN_TOUCHED", "family": family})
            continue
        if row.get("is_amendment") or is_amendment(row.get("form")):
            tagged = attach_selection(row, family)
            refusals.append((tagged or row) | {"refusal_reason": "AMENDMENT_NOT_ORIGIN", "family": family})
            continue
        tagged = attach_selection(row, family)
        if tagged is None:
            refusals.append(row | {"refusal_reason": "DATE_ONLY_REFUSED", "family": family})
            continue
        prepared.append(tagged)
    pool_sha = sha256_text(canonical_json(
        [row["selection_key"] for row in sorted(prepared, key=lambda item: item["selection_key"])]
    ))
    selected, quota_refused = select_quota_rows(prepared, family=family)
    for row in quota_refused:
        refusals.append(row | {"family": family})
    ranked = [
        row | {"family": family, "rank": rank, "pool_sha256": pool_sha}
        for rank, row in enumerate(selected, start=1)
    ]
    return ranked, refusals, pool_sha, len(prepared)


def cmd_rebuild(root: Path, out_dir: Path) -> int:
    access = AccessLog()
    assert_blind_workspace(root)
    work = out_dir / "work"
    cache_path = work / "fts_cache.json"
    cache = json.loads(cache_path.read_text(encoding="utf-8"))
    family_outputs: dict[str, Any] = {}
    all_raw: list[dict[str, Any]] = []
    refusal_counts: dict[str, int] = {}
    leftover: list[dict[str, Any]] = []
    for family in list(PRIMARY_FAMILIES) + list(CONTROL_FAMILIES):
        pool, incomplete = pool_from_cache(cache, family)
        ranked, refusals, pool_sha, prepared_n = select_family_pool(pool, family)
        for row in refusals:
            reason = str(row.get("refusal_reason") or "UNKNOWN")
            refusal_counts[reason] = refusal_counts.get(reason, 0) + 1
        selected_keys = {row["selection_key"] for row in ranked}
        for row in pool:
            if is_design_excluded(
                ticker=row.get("ticker"),
                cik=row.get("cik"),
                display_name=row.get("display_name"),
            ) or is_amendment(row.get("form")):
                continue
            tagged = attach_selection(row, family)
            if tagged and tagged["selection_key"] not in selected_keys:
                leftover.append(tagged | {"family": family, "pool_sha256": pool_sha})
        family_outputs[family] = {
            "incomplete_cells": incomplete,
            "raw_unique_filings": prepared_n,
            "selected": len(ranked),
            "pool_sha256": pool_sha,
            "quota": QUOTAS[family],
        }
        write_json(work / f"selected_{family}.json", ranked)
        existing = work / f"family_{family}.json"
        if existing.exists():
            prior = json.loads(existing.read_text(encoding="utf-8"))
            prior.update(family_outputs[family])
            write_json(existing, prior)
        else:
            write_json(existing, family_outputs[family])
        all_raw.extend(ranked)
        print(canonical_json({"family": family, **family_outputs[family]}), flush=True)
    leftover_sorted = sorted(leftover, key=lambda row: row["selection_key"])
    issuer_counts: dict[str, int] = {}
    for row in all_raw:
        ident = f"cik:{row.get('cik')}"
        issuer_counts[ident] = issuer_counts.get(ident, 0) + 1
    extra_needed = max(0, RAW_CANDIDATE_FLOOR - len(all_raw))
    extras: list[dict[str, Any]] = []
    for row in leftover_sorted:
        if len(extras) >= extra_needed:
            break
        ident = f"cik:{row.get('cik')}"
        if issuer_counts.get(ident, 0) >= 5:
            continue
        extras.append(row | {"rank": 0, "overbuild": True})
        issuer_counts[ident] = issuer_counts.get(ident, 0) + 1
        all_raw.append(extras[-1])
    write_json(out_dir / "A1B_FAMILY_COVERAGE.json", family_outputs)
    write_json(out_dir / "A1B_RAW_CANDIDATES.json", all_raw)
    write_json(out_dir / "A1F_REFUSAL_LEDGER.json", {
        "count": sum(refusal_counts.values()),
        "by_reason": refusal_counts,
        "overbuild_added": len(extras),
    })
    write_json(out_dir / "A1A_ACCESS_LOG.json", {
        "sha256": access.digest(),
        "banned_reads": access.banned_reads(),
        "event_count": len(access.events),
        "note": "rebuild-from-cache; no new network",
    })
    print(canonical_json({
        "raw_selected": len(all_raw),
        "overbuild_added": len(extras),
        "families": {key: value["selected"] for key, value in family_outputs.items()},
        "refusal_counts": refusal_counts,
        "access_log_sha256": access.digest(),
    }))
    if len(all_raw) < RAW_CANDIDATE_FLOOR:
        print(f"BLOCKED: raw candidates {len(all_raw)} < {RAW_CANDIDATE_FLOOR}", flush=True)
        return 2
    return 0


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=("inventory", "harvest", "rebuild", "extract", "report"))
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument(
        "--out",
        type=Path,
        default=ROOT / "research" / "dislocation_intelligence" / "p0_a1",
    )
    parser.add_argument("--family", action="append")
    parser.add_argument("--limit", type=int, default=None)
    args = parser.parse_args()
    root = args.root.resolve()
    out = args.out if args.out.is_absolute() else (root / args.out)
    if args.command == "inventory":
        return cmd_inventory(root, out / "A1A_INVENTORY.json")
    if args.command == "harvest":
        return cmd_harvest(root, out, args.family)
    if args.command == "rebuild":
        return cmd_rebuild(root, out)
    if args.command == "extract":
        return cmd_extract(root, out, args.limit)
    return cmd_report(out)


if __name__ == "__main__":
    raise SystemExit(main())
