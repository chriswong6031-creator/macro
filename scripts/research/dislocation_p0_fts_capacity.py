#!/usr/bin/env python3
"""Price-blind SEC full-text-search capacity census for Dislocation P0.

This one-time research executable tests whether a frozen, semantics-first phrase
lexicon can retrieve enough official SEC filing candidates to justify the blind
extraction program. It does NOT classify events, read prices/volume/outcomes, or
claim that a search hit is an economic episode.

Network boundary: HTTPS GET requests to exactly efts.sec.gov/LATEST/search-index.
Forms: 8-K and 6-K, queried separately. Windows: 2016-2025 and 2022-2025.
Every count is a query-hit count and can contain duplicates or false positives.
If SEC FTS rejects an overloaded multi-year cell, the exact same phrase/form cell
is split into calendar-year shards; unresolved shards are typed errors, not zeroes.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import time
from collections import defaultdict
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import requests

ENDPOINT = "https://efts.sec.gov/LATEST/search-index"
ALLOWED_HOST = "efts.sec.gov"
FORMS = ("8-K", "6-K")
WINDOWS = {
    "full_2016_2025": ("2016-01-01", "2025-12-31"),
    "modern_2022_2025": ("2022-01-01", "2025-12-31"),
}
PACE_SECONDS = 0.27
TIMEOUT_SECONDS = 45
MAX_RETRIES = 3
PAGE_SIZE = 100
USER_AGENT = "MastermindX research-source-census research@mastermind-x.com"

# Frozen before querying. These phrases are candidate-retrieval hooks, not
# classifications and not evidence of temporary impairment.
LEXICON = {
    "PHYSICAL_MECHANICAL_INTERRUPTION": [
        "equipment failure", "mechanical failure", "unplanned outage",
        "temporary shutdown", "temporarily shut down",
        "temporarily suspended operations", "operations were suspended",
        "production interruption", "manufacturing interruption", "plant outage",
        "facility outage", "equipment malfunction", "power outage",
    ],
    "EXTERNAL_HUMAN_INTERRUPTION": [
        "labor strike", "work stoppage", "labor action", "union strike",
        "blockade", "community protest", "civil unrest", "picket line",
        "access restriction", "workforce walkout",
    ],
    "CYBER_OR_IT_INTERRUPTION": [
        "cybersecurity incident", "cyber incident", "ransomware",
        "network outage", "systems outage", "system outage",
        "information technology outage", "data breach", "unauthorized access",
        "cyber-related business interruption",
    ],
    "WEATHER_OR_PHYSICAL_DISASTER": [
        "severe weather", "hurricane damage", "winter storm", "wildfire",
        "flooding", "earthquake", "tornado", "facility fire", "plant fire",
        "natural disaster", "storm damage",
    ],
    "TEMPORARY_EXPECTATION_RESET": [
        "temporary headwinds", "temporary margin pressure",
        "temporary cost pressure", "temporary demand weakness",
        "temporary slowdown", "one-time impact", "one-time charge",
        "transitory impact", "guidance withdrawn", "lowered guidance",
        "temporary disruption", "temporary factors",
    ],
    "STRUCTURAL_IMPAIRMENT_CONTROL": [
        "going concern", "bankruptcy", "permanent closure", "permanently close",
        "non-reliance on previously issued financial statements",
        "material weakness", "ceased operations", "liquidation", "insolvency",
        "default under",
    ],
    "RESOLVED_BEFORE_DISCLOSURE_CONTROL": [
        "operations have resumed", "resumed normal operations",
        "service has been restored", "fully restored operations",
        "returned to normal operations", "operations resumed",
        "issue has been resolved",
    ],
}

FORBIDDEN_PATHS = (
    "data/yahoo", "data/stocks", "data/ohlc", "data/stockdata",
    "data/intraday", "data/chinaohlc", "data/hkohlc", "data/canadaohlc",
    "data/intlohlc", "data/price_pressure", "data/washout_turn",
)


def canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def lexicon_sha256() -> str:
    return hashlib.sha256(canonical_json(LEXICON).encode("utf-8")).hexdigest()


def request_json(
    session: requests.Session, *, phrase: str, form: str, start: str, end: str
) -> dict:
    parsed = urlparse(ENDPOINT)
    if (
        parsed.scheme != "https"
        or parsed.netloc != ALLOWED_HOST
        or parsed.path != "/LATEST/search-index"
    ):
        raise RuntimeError("SEC FTS endpoint binding changed")
    params = {
        "q": f'"{phrase}"', "startdt": start, "enddt": end,
        "forms": form, "from": 0, "size": PAGE_SIZE,
    }
    last: Exception | None = None
    for attempt in range(MAX_RETRIES):
        try:
            response = session.get(
                ENDPOINT,
                params=params,
                timeout=TIMEOUT_SECONDS,
                headers={"User-Agent": USER_AGENT, "Accept": "application/json"},
            )
            if response.status_code in (429, 500, 502, 503, 504):
                raise requests.HTTPError(f"HTTP {response.status_code}", response=response)
            response.raise_for_status()
            payload = response.json()
            if not isinstance(payload, dict):
                raise RuntimeError("SEC FTS returned non-object JSON")
            return payload
        except Exception as exc:  # noqa: BLE001 — typed below after bounded retries
            last = exc
            if attempt + 1 < MAX_RETRIES:
                time.sleep(1.5 * (attempt + 1))
    raise RuntimeError(f"SEC FTS failed for {phrase!r}/{form}/{start}..{end}: {last}")


def total_hits(payload: dict) -> int:
    total = ((payload.get("hits") or {}).get("total"))
    if isinstance(total, dict):
        total = total.get("value")
    try:
        return int(total or 0)
    except (TypeError, ValueError):
        return 0


def parse_hit(hit: dict) -> dict[str, Any] | None:
    source = hit.get("_source") or {}
    hit_id = str(hit.get("_id") or "").strip()
    if not hit_id or not isinstance(source, dict):
        return None
    accession_from_id, _, filename = hit_id.partition(":")
    display_names = source.get("display_names") or []
    ciks = source.get("ciks") or []
    items = source.get("items") or []
    return {
        "hit_id": hit_id,
        "accession": source.get("adsh") or accession_from_id or None,
        "filename": filename or None,
        "form": source.get("form"),
        "file_type": source.get("file_type"),
        "file_date": source.get("file_date"),
        "display_name": display_names[0] if display_names else None,
        "cik": str(ciks[0]) if ciks else None,
        "items": sorted(map(str, items)),
    }


def parse_payload(payload: dict, expected_form: str) -> dict[str, Any]:
    raw_hits = ((payload.get("hits") or {}).get("hits")) or []
    rows = [row for row in (parse_hit(hit) for hit in raw_hits) if row is not None]
    return {
        "total_hits": total_hits(payload),
        "rows": rows,
        "form_filter_mismatches": sorted(
            {str(row.get("form")) for row in rows if row.get("form") != expected_form}
        ),
    }


def annual_shards(start: str, end: str) -> list[tuple[str, str]]:
    start_year = int(start[:4])
    end_year = int(end[:4])
    return [(f"{year}-01-01", f"{year}-12-31") for year in range(start_year, end_year + 1)]


def search_one(
    session: requests.Session, *, phrase: str, form: str, start: str, end: str
) -> dict[str, Any]:
    errors: list[str] = []
    shards: list[dict[str, Any]] = []
    try:
        parsed = parse_payload(
            request_json(session, phrase=phrase, form=form, start=start, end=end), form
        )
        shards.append({"start": start, "end": end, **parsed})
        query_mode = "whole_window"
    except Exception as exc:  # noqa: BLE001 — overload fallback is the point
        errors.append(str(exc))
        query_mode = "annual_fallback"
        for shard_start, shard_end in annual_shards(start, end):
            try:
                parsed = parse_payload(
                    request_json(
                        session,
                        phrase=phrase,
                        form=form,
                        start=shard_start,
                        end=shard_end,
                    ),
                    form,
                )
                shards.append({"start": shard_start, "end": shard_end, **parsed})
            except Exception as shard_exc:  # noqa: BLE001 — typed unresolved shard
                errors.append(str(shard_exc))
            time.sleep(PACE_SECONDS)

    all_rows: dict[str, dict[str, Any]] = {}
    mismatch_forms: set[str] = set()
    total = 0
    for shard in shards:
        total += int(shard["total_hits"])
        mismatch_forms.update(shard["form_filter_mismatches"])
        for row in shard["rows"]:
            all_rows[row["hit_id"]] = row
    rows = [all_rows[key] for key in sorted(all_rows)]
    return {
        "phrase": phrase,
        "form": form,
        "query_mode": query_mode,
        "resolved_shards": len(shards),
        "errors": errors,
        "complete": bool(shards) and not errors[1:] if query_mode == "annual_fallback" else not errors,
        "total_hits": total,
        "returned_unique_hits": len(rows),
        "form_filter_mismatches": sorted(mismatch_forms),
        "unique_accessions_in_pages": len(
            {row.get("accession") for row in rows if row.get("accession")}
        ),
        "unique_ciks_in_pages": len({row.get("cik") for row in rows if row.get("cik")}),
        "sample": rows[:10],
        "page_hit_ids": [row["hit_id"] for row in rows],
    }


def aggregate(results: list[dict]) -> dict[str, Any]:
    grouped: dict[str, dict[str, list[dict]]] = defaultdict(lambda: defaultdict(list))
    for row in results:
        grouped[row["window"]][row["family"]].append(row)

    output: dict[str, Any] = {}
    for window, family_map in sorted(grouped.items()):
        output[window] = {}
        for family, rows in sorted(family_map.items()):
            hit_ids = {
                hit_id for row in rows for hit_id in row.get("page_hit_ids", [])
            }
            ciks = {
                sample.get("cik")
                for row in rows
                for sample in row.get("sample", [])
                if sample.get("cik")
            }
            output[window][family] = {
                "query_form_cells": len(rows),
                "raw_total_hit_sum_not_deduped": sum(row["total_hits"] for row in rows),
                "page_unique_hit_ids": len(hit_ids),
                "sample_unique_ciks": len(ciks),
                "cells_with_at_least_15_hits": sum(row["total_hits"] >= 15 for row in rows),
                "zero_hit_cells": sum(row["total_hits"] == 0 and row["complete"] for row in rows),
                "incomplete_cells": sum(not row["complete"] for row in rows),
                "annual_fallback_cells": sum(row["query_mode"] == "annual_fallback" for row in rows),
                "form_filter_mismatch_cells": sum(bool(row["form_filter_mismatches"]) for row in rows),
                "capacity_read": (
                    "CANDIDATE_CAPACITY_PRESENT"
                    if len(hit_ids) >= 15
                    else "INSUFFICIENT_PAGE_SAMPLE_CAPACITY"
                ),
            }
    return output


def run(root: Path) -> dict[str, Any]:
    present_forbidden = [path for path in FORBIDDEN_PATHS if (root / path).exists()]
    if present_forbidden:
        raise RuntimeError(f"price/outcome paths present in blind workspace: {present_forbidden}")

    session = requests.Session()
    results: list[dict[str, Any]] = []
    for window, (start, end) in WINDOWS.items():
        for family, phrases in LEXICON.items():
            for phrase in phrases:
                for form in FORMS:
                    row = search_one(
                        session, phrase=phrase, form=form, start=start, end=end
                    )
                    row.update(
                        {"window": window, "family": family, "start": start, "end": end}
                    )
                    results.append(row)
                    time.sleep(PACE_SECONDS)

    return {
        "schema": "mastermind.dislocation_p0_fts_capacity.v1_1",
        "authority": {
            "can_rank": False, "can_gate": False, "can_size": False,
            "can_originate_signal": False, "can_escalate": False,
        },
        "query_contract": {
            "endpoint": ENDPOINT,
            "allowed_host": ALLOWED_HOST,
            "forms": list(FORMS),
            "windows": {
                key: {"start": value[0], "end": value[1]}
                for key, value in WINDOWS.items()
            },
            "page_size": PAGE_SIZE,
            "phrase_matching": "quoted_exact_phrase_candidate_retrieval",
            "overload_fallback": "same phrase/form split into calendar-year shards",
            "lexicon": LEXICON,
            "lexicon_sha256": lexicon_sha256(),
            "warning": "hit counts are not events; duplicates and false positives are expected",
        },
        "blind_boundary": {
            "forbidden_paths": list(FORBIDDEN_PATHS),
            "present_forbidden_paths": present_forbidden,
            "network_hosts_used": [ALLOWED_HOST],
            "price_or_outcome_read": False,
        },
        "results": results,
        "aggregate": aggregate(results),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=Path("."))
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    payload = run(args.root.resolve())
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    print(f"wrote {args.out} ({len(payload['results'])} query/form/window cells)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
