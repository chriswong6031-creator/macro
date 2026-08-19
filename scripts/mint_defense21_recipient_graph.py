"""Mint the ``defense21-v1`` reviewed recipient graph — the D2 graph delta.

This is a ONE-TIME, bounded construction script, not a general proposer.  It
adds exactly the five Ex.21-proven BWX Technologies (BWXT) ownership chains
frozen in ``research/defense_intelligence/D2_IDENTITY_ATLAS_EXECUTION_SPEC.md``
§2 on top of the live ``defense19-v1`` graph, and nothing else:

* every ``defense19-v1`` row is carried forward byte-identical (this script
  self-verifies that before it ever calls the curator);
* the three refused BWXT identifiers named in the spec (Ordnance Tennessee,
  NOG Technologies, Enrichment Operations) are never admitted — they stay
  Atlas-unresolved;
* every evidence receipt is produced from REAL fetched bytes through the same
  seam ``scripts/propose_government_revenue_recipient_graph.py`` uses
  (:class:`HttpFetcher` + :func:`_evidence_row`), never hand-typed digests.

Publication reuses the existing curator
(``scripts/curate_government_revenue_recipient_graph.py::curate_graph``) so
the single write path to the canonical graph, and its strict admission gate,
are exercised exactly as they are for any other reviewed graph.

Usage::

    python3 -m scripts.mint_defense21_recipient_graph \\
      --user-agent "MastermindX Government Revenue research (contact: you@example.com)"
"""
from __future__ import annotations

import argparse
import json
import sys
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT))

from engine.government_revenue.entity_resolution import (  # noqa: E402
    RECIPIENT_GRAPH_CONTRACT,
    RECIPIENT_GRAPH_SCHEMA_VERSION,
    load_recipient_entity_graph,
)
from scripts.curate_government_revenue_recipient_graph import curate_graph  # noqa: E402
from scripts.propose_government_revenue_recipient_graph import (  # noqa: E402
    Fetch,
    HttpFetcher,
    _evidence_row,
    _temporal,
    normalize_legal_name,
)

CANONICAL_GRAPH_PATH = _ROOT / "data" / "government_revenue" / "recipient_entity_graph.json"
NEW_GRAPH_ID = "recipient-graph:reviewed:2026-08-19:defense21-v1"

# Ex.21-as-of clock for every new BWXT row (FY2025 10-K, filed 2026-02-23).
BWXT_VALID_FROM = "2025-12-31T00:00:00+00:00"

BWXT_CIK = "1486957"
BWXT_ACCESSION_DASHED = "0001486957-26-000007"
BWXT_ACCESSION_DASHLESS = "000148695726000007"
BWXT_10K_DOC = "bwxt-20251231.htm"
BWXT_EX21_DOC = "exhibit211_123125x10k.htm"
BWXT_10K_URL = (
    f"https://www.sec.gov/Archives/edgar/data/{BWXT_CIK}/{BWXT_ACCESSION_DASHLESS}/{BWXT_10K_DOC}"
)
BWXT_EX21_URL = (
    f"https://www.sec.gov/Archives/edgar/data/{BWXT_CIK}/{BWXT_ACCESSION_DASHLESS}/{BWXT_EX21_DOC}"
)
BWXT_10K_RECORD_ID = f"sec:{BWXT_CIK}:{BWXT_ACCESSION_DASHED}:{BWXT_10K_DOC}"
BWXT_EX21_RECORD_ID = f"sec:{BWXT_CIK}:{BWXT_ACCESSION_DASHED}:{BWXT_EX21_DOC}"

#: Parent-plane corroboration (review finding B4).  Every award receipt's
#: ``parent_recipient_uei`` field is null; on four of five awards
#: ``parent_recipient_name`` reads "BWX TECHNOLOGIES, INC." but UMBKD2WKD8N5
#: self-parents on its only award, so this exact-UEI children listing is the
#: load-bearing corroboration for that chain.  UEI CMT4S6G76QB5 is BWX
#: Technologies, Inc.'s own parent-recipient UEI (verified against the award
#: receipts above at mint time).
BWXT_PARENT_UEI = "CMT4S6G76QB5"
BWXT_CHILDREN_URL = f"https://api.usaspending.gov/api/v2/recipient/children/{BWXT_PARENT_UEI}/"

#: (uei, entity slug, canonical name exactly as Ex.21 prints it, award id) —
#: five admitted chains, frozen order per spec §2/§4.
BWXT_SUBSIDIARIES = (
    (
        "WJYVCPD5HKK7",
        "bwxt-nuclear-operations-group-inc",
        "BWXT Nuclear Operations Group, Inc.",
        "CONT_AWD_89233123FNA400535_8900_89233120DNA000025_8900",
    ),
    (
        "C4L1VT236AA1",
        "bwxt-nuclear-energy-inc",
        "BWXT Nuclear Energy, Inc.",
        "CONT_AWD_80MSFC17C0006_8000_-NONE-_-NONE-",
    ),
    (
        "SMJQJGD5JEJ3",
        "nuclear-fuel-services-inc",
        "Nuclear Fuel Services, Inc.",
        "CONT_AWD_89233124CNA000371_8900_-NONE-_-NONE-",
    ),
    (
        "UMBKD2WKD8N5",
        "bwxt-advanced-technologies-llc",
        "BWXT Advanced Technologies LLC",
        "CONT_AWD_N0017325C2403_9700_-NONE-_-NONE-",
    ),
    (
        "PZDQCRZW7GJ3",
        "bwxt-technical-services-group-inc",
        "BWXT Technical Services Group, Inc.",
        "CONT_AWD_HQ085926FF258_9700_HQ085926DF017_9700",
    ),
)

#: Identifiers the frozen spec explicitly REFUSES from the graph.  They must
#: never appear in any row this script writes; the Atlas surfaces them as
#: unresolved via the curated file instead.
REFUSED_IDENTIFIERS = ("MMACD85DT5D5", "PM7HBL2KDX46", "URJ3CAC3MSH8")

_TABLES = ("evidence", "companies", "legal_entities", "identifiers", "ownership_edges")
_ROW_ID_FIELD = {
    "evidence": "evidence_id",
    "companies": "company_id",
    "legal_entities": "entity_id",
    "identifiers": "identifier_id",
    "ownership_edges": "edge_id",
}


def _award_url(award_id: str) -> str:
    return f"https://api.usaspending.gov/api/v2/awards/{award_id}/"


def _assert_award_body_names_its_uei(*, uei: str, body: bytes, award_id: str) -> None:
    """Refuse to admit an award receipt that does not actually name its UEI.

    A wrong award ID pasted into :data:`BWXT_SUBSIDIARIES` would otherwise
    mint a receipt that loads cleanly but proves nothing about the identifier
    it claims to corroborate.
    """
    if uei.upper().encode("ascii") not in body.upper():
        raise ValueError(
            f"award receipt {award_id!r} does not contain its own UEI {uei!r}; "
            "refusing to admit a mismatched receipt"
        )


def _assert_ex21_names_every_admitted_entity(*, body: bytes) -> None:
    """Refuse to admit Ex.21 evidence that does not actually list every
    canonical name this script is about to write, case/punctuation-insensitive
    (the same join rule ``normalize_legal_name`` uses for a real proposer
    walk)."""
    haystack = f" {normalize_legal_name(body.decode('utf-8', 'ignore'))} "
    missing = [
        canonical_name
        for _uei, _slug, canonical_name, _award_id in BWXT_SUBSIDIARIES
        if f" {normalize_legal_name(canonical_name)} " not in haystack
    ]
    if missing:
        raise ValueError(
            f"Ex.21 evidence does not name every admitted entity; missing: {missing}"
        )


def _assert_children_receipt_lists_every_admitted_uei(*, body: bytes) -> None:
    """Fail closed unless the parent-plane children listing corroborates all
    five admitted UEIs (review finding B4) BEFORE anything is published."""
    admitted = {uei for uei, _slug, _name, _award_id in BWXT_SUBSIDIARIES}
    try:
        rows = json.loads(body)
    except (ValueError, TypeError) as exc:
        raise ValueError("BWXT parent-plane children receipt is not valid JSON") from exc
    if not isinstance(rows, list):
        raise ValueError("BWXT parent-plane children receipt is not a JSON list")
    listed = {
        str(row.get("uei")).upper()
        for row in rows
        if isinstance(row, dict) and row.get("uei")
    }
    missing = sorted(admitted - listed)
    if missing:
        raise ValueError(
            f"BWXT parent-plane children receipt does not list every admitted UEI; missing: {missing}"
        )


def build_bwxt_rows(
    *, fetch: Fetch
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]], str]:
    """Fetch real evidence bytes and construct the five BWXT chains.

    ``known_at`` cannot be chosen before the fetches run: the loader requires
    every evidence receipt's real ``retrieved_at`` to sit at or before its own
    ``known_at``, and a walk across seven documents takes real wall-clock time.
    So every row here is built with a placeholder, and the true ``known_at`` —
    computed strictly AFTER the last byte lands — is stamped on afterward.

    Returns ``(evidence, companies, legal_entities, identifiers,
    ownership_edges, known_at)`` — new rows only, never a merge with the base
    graph.
    """
    known_at = "PENDING"  # replaced below once every fetch has completed
    evidence_rows: list[dict[str, Any]] = []
    company_rows: list[dict[str, Any]] = []
    entity_rows: list[dict[str, Any]] = []
    identifier_rows: list[dict[str, Any]] = []
    edge_rows: list[dict[str, Any]] = []

    # --- Top of the chain: the public issuer and its registrant legal entity.
    tenk_body = fetch(BWXT_10K_URL)
    tenk_retrieved_at = datetime.now(timezone.utc).isoformat()
    evidence_10k = _evidence_row(
        evidence_id="evidence:bwxt-sec-10k",
        publisher="SEC",
        evidence_class="official_filing",
        record_id=BWXT_10K_RECORD_ID,
        url=BWXT_10K_URL,
        body=tenk_body,
        claim_scopes=("legal_entity", "ownership", "public_company"),
        known_at=known_at,
        valid_from=BWXT_VALID_FROM,
        retrieved_at=tenk_retrieved_at,
    )
    evidence_rows.append(evidence_10k)

    company_rows.append(
        {
            "company_id": "central:BWXT",
            "ticker": "BWXT",
            "verification_state": "reviewed",
            **_temporal(known_at, BWXT_VALID_FROM, [evidence_10k["evidence_id"]]),
        }
    )
    entity_rows.append(
        {
            "entity_id": "legal:bwxt:bwx-technologies-inc",
            "canonical_name": "BWX Technologies, Inc.",
            "verification_state": "reviewed",
            **_temporal(known_at, BWXT_VALID_FROM, [evidence_10k["evidence_id"]]),
        }
    )
    edge_rows.append(
        {
            "edge_id": "issuer-identity:bwxt:bwx-technologies-inc",
            "child_entity_id": "legal:bwxt:bwx-technologies-inc",
            "parent_company_id": "central:BWXT",
            "relationship": "issuer_legal_entity",
            "economic_share": 1.0,
            "verification_state": "reviewed",
            **_temporal(known_at, BWXT_VALID_FROM, [evidence_10k["evidence_id"]]),
        }
    )

    # --- Ex.21 exhibit: names and jurisdictions of the five admitted subsidiaries.
    ex21_body = fetch(BWXT_EX21_URL)
    ex21_retrieved_at = datetime.now(timezone.utc).isoformat()
    evidence_ex21 = _evidence_row(
        evidence_id="evidence:bwxt-sec-ex21",
        publisher="SEC",
        evidence_class="official_filing",
        record_id=BWXT_EX21_RECORD_ID,
        url=BWXT_EX21_URL,
        body=ex21_body,
        claim_scopes=("legal_entity", "ownership"),
        known_at=known_at,
        valid_from=BWXT_VALID_FROM,
        retrieved_at=ex21_retrieved_at,
    )
    _assert_ex21_names_every_admitted_entity(body=ex21_body)
    evidence_rows.append(evidence_ex21)

    # --- Parent-plane corroboration (review finding B4): the exact-UEI
    # children listing under BWX Technologies' own parent recipient UEI.
    # Per-award ``parent_recipient_uei`` is null on all five award receipts,
    # so this receipt is the one that actually ties every admitted UEI back
    # to the same parent recipient by exact identifier, not by name match.
    children_body = fetch(BWXT_CHILDREN_URL)
    children_retrieved_at = datetime.now(timezone.utc).isoformat()
    _assert_children_receipt_lists_every_admitted_uei(body=children_body)
    evidence_children = _evidence_row(
        evidence_id="evidence:bwxt-usaspending-children-cmt4s6g76qb5",
        publisher="USAspending.gov",
        evidence_class="official_award",
        record_id=f"recipient-children:{BWXT_PARENT_UEI}",
        url=BWXT_CHILDREN_URL,
        body=children_body,
        claim_scopes=("exact_identifier", "ownership"),
        known_at=known_at,
        valid_from=BWXT_VALID_FROM,
        retrieved_at=children_retrieved_at,
    )
    evidence_rows.append(evidence_children)

    for uei, slug, canonical_name, award_id in BWXT_SUBSIDIARIES:
        if uei in REFUSED_IDENTIFIERS:  # pragma: no cover - defensive; never true
            raise ValueError(f"refused identifier {uei} must never be admitted")
        award_url = _award_url(award_id)
        award_body = fetch(award_url)
        award_retrieved_at = datetime.now(timezone.utc).isoformat()
        _assert_award_body_names_its_uei(uei=uei, body=award_body, award_id=award_id)
        evidence_award = _evidence_row(
            evidence_id=f"evidence:bwxt-usaspending-{uei.lower()}",
            publisher="USAspending.gov",
            evidence_class="official_award",
            record_id=award_id,
            url=award_url,
            body=award_body,
            claim_scopes=("exact_identifier", "legal_entity", "ownership"),
            known_at=known_at,
            valid_from=BWXT_VALID_FROM,
            retrieved_at=award_retrieved_at,
        )
        evidence_rows.append(evidence_award)

        entity_id = f"legal:bwxt:{slug}"
        entity_refs = [
            evidence_ex21["evidence_id"],
            evidence_award["evidence_id"],
            evidence_children["evidence_id"],
        ]
        entity_rows.append(
            {
                "entity_id": entity_id,
                "canonical_name": canonical_name,
                "verification_state": "reviewed",
                **_temporal(known_at, BWXT_VALID_FROM, entity_refs),
            }
        )
        identifier_rows.append(
            {
                "identifier_id": f"identifier:bwxt:{uei.lower()}",
                "entity_id": entity_id,
                "namespace": "sam_uei",
                "value": uei,
                "verification_state": "reviewed",
                **_temporal(
                    known_at,
                    BWXT_VALID_FROM,
                    [evidence_award["evidence_id"], evidence_children["evidence_id"]],
                ),
            }
        )
        edge_rows.append(
            {
                "edge_id": f"ownership:bwxt:{slug}",
                "child_entity_id": entity_id,
                "parent_entity_id": "legal:bwxt:bwx-technologies-inc",
                "relationship": "wholly_owned",
                "economic_share": 1.0,
                "verification_state": "reviewed",
                **_temporal(known_at, BWXT_VALID_FROM, entity_refs),
            }
        )

    # Every fetch is done; the true known_at is now knowable and guaranteed to
    # sit at or after every retrieved_at captured above.
    known_at = datetime.now(timezone.utc).isoformat()
    for row in (*evidence_rows, *company_rows, *entity_rows, *identifier_rows, *edge_rows):
        row["known_at"] = known_at

    return evidence_rows, company_rows, entity_rows, identifier_rows, edge_rows, known_at


def _assert_no_refused_identifiers(identifier_rows: list[dict[str, Any]]) -> None:
    values = {row.get("value") for row in identifier_rows}
    leaked = values & set(REFUSED_IDENTIFIERS)
    if leaked:
        raise ValueError(f"refused identifiers must never be admitted: {sorted(leaked)}")


def _assert_base_rows_untouched(
    base_graph: dict[str, Any], merged_graph: dict[str, Any]
) -> None:
    """Every defense19 row must survive byte-identical, keyed by its own id."""
    for table in _TABLES:
        id_field = _ROW_ID_FIELD[table]
        base_rows = {row[id_field]: row for row in base_graph.get(table, [])}
        merged_rows = {row[id_field]: row for row in merged_graph.get(table, [])}
        missing = set(base_rows) - set(merged_rows)
        if missing:
            raise ValueError(f"defense19 {table} rows dropped from defense21: {sorted(missing)}")
        for row_id, base_row in base_rows.items():
            if merged_rows[row_id] != base_row:
                raise ValueError(
                    f"defense19 {table} row {row_id!r} was mutated in defense21 — refusing"
                )


def build_defense21_graph(
    *, base_graph: dict[str, Any], fetch: Fetch
) -> dict[str, Any]:
    """Return the complete defense21-v1 candidate: defense19 plus BWXT.

    The construction stamp is derived from the fetches themselves (see
    :func:`build_bwxt_rows`) — never chosen ahead of time — so this can never
    mint a graph whose own clock sits ahead of the moment its evidence
    actually arrived.
    """
    evidence_rows, company_rows, entity_rows, identifier_rows, edge_rows, known_at = (
        build_bwxt_rows(fetch=fetch)
    )
    _assert_no_refused_identifiers(identifier_rows)

    merged = deepcopy(base_graph)
    merged["graph_id"] = NEW_GRAPH_ID
    merged["graph_known_at"] = known_at
    merged["graph_effective_at"] = known_at
    merged["contract"] = RECIPIENT_GRAPH_CONTRACT
    merged["schema_version"] = RECIPIENT_GRAPH_SCHEMA_VERSION
    merged["evidence"] = list(base_graph.get("evidence", [])) + evidence_rows
    merged["companies"] = list(base_graph.get("companies", [])) + company_rows
    merged["legal_entities"] = list(base_graph.get("legal_entities", [])) + entity_rows
    merged["identifiers"] = list(base_graph.get("identifiers", [])) + identifier_rows
    merged["ownership_edges"] = list(base_graph.get("ownership_edges", [])) + edge_rows

    _assert_base_rows_untouched(base_graph, merged)
    return merged


def mint(
    *,
    base_path: Path,
    out_path: Path,
    fetch: Fetch,
    dry_run: bool = False,
) -> dict[str, Any]:
    base_graph = json.loads(base_path.read_text(encoding="utf-8"))
    if base_graph.get("graph_id") != "recipient-graph:reviewed:2026-08-08:defense19-v1":
        raise ValueError(
            f"base graph at {base_path} is not defense19-v1 "
            f"(graph_id={base_graph.get('graph_id')!r}); refusing to mint on top of it"
        )
    candidate = build_defense21_graph(base_graph=base_graph, fetch=fetch)
    stamp = candidate["graph_known_at"]

    # Prove admission BEFORE writing anything, mirroring the proposer's own
    # "PROVE the candidate loads, then write it" discipline.
    loaded = load_recipient_entity_graph(candidate, as_of=stamp)
    if loaded.get("status") != "ready":
        codes = ",".join(loaded.get("error_codes") or ["unknown_graph_error"])
        raise ValueError(f"defense21 candidate failed admission: {codes}")

    if dry_run:
        return loaded

    import tempfile

    with tempfile.TemporaryDirectory() as tmp:
        candidate_path = Path(tmp) / "defense21_candidate.json"
        candidate_path.write_text(
            json.dumps(candidate, ensure_ascii=False, sort_keys=True, separators=(",", ":")),
            encoding="utf-8",
        )
        published = curate_graph(candidate_path, target_path=out_path, as_of=stamp)
    return published


def main(argv: list[str] | None = None, *, fetch: Fetch | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Mint the defense21-v1 reviewed recipient graph (defense19 + BWXT)."
    )
    parser.add_argument(
        "--user-agent",
        required=fetch is None,
        help=(
            "SEC fair-access User-Agent carrying a real contact, e.g. "
            "'MastermindX Government Revenue research (contact: you@example.com)'"
        ),
    )
    parser.add_argument("--base", type=Path, default=CANONICAL_GRAPH_PATH)
    parser.add_argument("--out", type=Path, default=CANONICAL_GRAPH_PATH)
    parser.add_argument("--pace-seconds", type=float, default=0.35)
    parser.add_argument("--dry-run", action="store_true", help="Validate without publishing.")
    args = parser.parse_args(argv)

    active_fetch: Fetch = fetch or HttpFetcher(args.user_agent, pace_seconds=args.pace_seconds)
    result = mint(
        base_path=args.base,
        out_path=args.out,
        fetch=active_fetch,
        dry_run=args.dry_run,
    )
    action = "validated" if args.dry_run else "published"
    print(
        f"defense21 recipient graph {action}: id={result.get('graph_id')} "
        f"digest={result.get('graph_digest')}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
