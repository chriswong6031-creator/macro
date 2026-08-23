#!/usr/bin/env python3
"""Offline completion and exact-20 freeze for Dislocation P0-A1R.

This module deliberately has no HTTP client.  A caller that has separately been
authorized to retry SEC leaves supplies ``fetch_leaf``; the retry machinery can
only invoke that callback for the five historically failed leaves and always
returns a *new* cache object plus a content-addressed receipt.
"""
from __future__ import annotations

import itertools
import json
import sys
from pathlib import Path
from typing import Any, Callable, Iterable, Mapping

_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_ROOT))

from scripts.research.dislocation_p0_a1_lib import (
    PRIMARY_FAMILIES,
    base_form,
    canonical_accession,
    canonical_cik,
    canonical_json,
    era_for_filed_on,
    is_amendment,
    is_design_excluded,
    selection_key,
    sha256_text,
)  # noqa: E402


STRUCTURAL_CONTROL = "STRUCTURAL_IMPAIRMENT_CONTROL"
RESOLVED_CONTROL = "RESOLVED_BEFORE_DISCLOSURE_CONTROL"
FAMILIES = tuple(PRIMARY_FAMILIES) + (STRUCTURAL_CONTROL, RESOLVED_CONTROL)

# These are the only leaves a separately authorized retry executor may request.
FAILED_LEAVES = (
    {"phrase": "bankruptcy", "form": "8-K", "start": "2025-07-03", "end": "2025-12-31"},
    {"phrase": "liquidation", "form": "6-K", "start": "2025-01-01", "end": "2025-12-31"},
    {"phrase": "default under", "form": "8-K", "start": "2017-07-03", "end": "2017-12-31"},
    {"phrase": "default under", "form": "8-K", "start": "2023-01-01", "end": "2023-07-02"},
    {"phrase": "default under", "form": "8-K", "start": "2025-01-01", "end": "2025-07-02"},
)

# Aggregate records are local derivations, never network targets.  The left/right
# keys are supplied by the caller/cache and merged by ``aggregate_from_children``.
DERIVED_AGGREGATES = (
    {"phrase": "bankruptcy", "form": "8-K", "start": "2025-01-01", "end": "2025-12-31"},
    {"phrase": "default under", "form": "8-K", "start": "2017-01-01", "end": "2017-12-31"},
    {"phrase": "default under", "form": "8-K", "start": "2023-01-01", "end": "2023-12-31"},
    {"phrase": "default under", "form": "8-K", "start": "2025-01-01", "end": "2025-12-31"},
)


class CompletionBlocked(RuntimeError):
    """Raised before selection when source completion evidence is insufficient."""


class AllocationInfeasible(RuntimeError):
    """Raised when the fixed source-only allocation cannot be filled."""


def cache_key(spec: Mapping[str, str]) -> str:
    return canonical_json({key: spec[key] for key in ("phrase", "form", "start", "end")})


def sha256_json(value: Any) -> str:
    return sha256_text(canonical_json(value))


def retry_targets(cache: Mapping[str, Any]) -> list[dict[str, str]]:
    """Return only named failed leaves that remain incomplete in ``cache``."""
    targets: list[dict[str, str]] = []
    for leaf in FAILED_LEAVES:
        record = cache.get(cache_key(leaf))
        if not isinstance(record, Mapping) or record.get("complete") is not False:
            continue
        targets.append(dict(leaf))
    return targets


def aggregate_from_children(left: Mapping[str, Any], right: Mapping[str, Any]) -> dict[str, Any]:
    """Recompute a parent receipt without fetching it."""
    rows: dict[str, dict[str, Any]] = {}
    for row in list(left.get("rows") or []) + list(right.get("rows") or []):
        hit_id = str(row.get("hit_id") or "")
        if hit_id:
            rows[hit_id] = dict(row)
    complete = bool(left.get("complete") and right.get("complete"))
    return {
        "start": left.get("start"),
        "end": right.get("end"),
        "complete": complete,
        "refusal_reason": None if complete else "INCOMPLETE_QUERY_CELL",
        "error": None if complete else "CHILD_INCOMPLETE",
        "total_hits": int(left.get("total_hits") or 0) + int(right.get("total_hits") or 0),
        "rows": [rows[key] for key in sorted(rows)],
        "children": [dict(left), dict(right)],
        "response_sha256": sha256_json([
            left.get("response_sha256") or "", right.get("response_sha256") or "",
        ]),
    }


def retry_only_completion(
    cache: Mapping[str, Any],
    fetch_leaf: Callable[[Mapping[str, str]], Mapping[str, Any]],
    *,
    historical_cache_sha256: str | None = None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Retry only failed leaves and return a copied cache plus durable receipt.

    The callback is intentionally injected: this module cannot make a network
    request by itself.  A failed or incomplete callback response leaves the
    caller's original cache untouched and raises ``CompletionBlocked``.
    """
    # The historical FTS cache is ~739 MB.  We replace only named top-level
    # leaves, so copying nested values would be both wasteful and a second
    # accidental full-cache traversal.  The caller owns the raw-file digest.
    original = dict(cache)
    updated = dict(cache)
    attempts: list[dict[str, Any]] = []
    for leaf in retry_targets(original):
        prior = original[cache_key(leaf)]
        result = dict(fetch_leaf(dict(leaf)))
        if result.get("complete") is not True:
            raise CompletionBlocked(f"retry leaf did not complete: {leaf}")
        updated[cache_key(leaf)] = result
        attempts.append({
            "leaf": leaf,
            "prior_response_sha256": prior.get("response_sha256"),
            "result_response_sha256": result.get("response_sha256"),
            "complete": True,
        })
    receipt = {
        "schema": "mastermind.dislocation_p0.a1r_retry_receipt.v1",
        "retry_targets": [row["leaf"] for row in attempts],
        "derived_aggregates": [dict(item) for item in DERIVED_AGGREGATES],
        "attempts": attempts,
        "historical_cache_sha256": historical_cache_sha256,
        "replacement_set_sha256": sha256_json({
            "historical_cache_sha256": historical_cache_sha256,
            "replacements": attempts,
        }),
    }
    receipt["receipt_sha256"] = sha256_json(receipt)
    return updated, receipt


def recompute_derived_aggregates(
    cache: Mapping[str, Any],
    children: Mapping[str, tuple[str, str]],
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Return a copied cache with only named derived aggregates recomputed.

    ``children`` maps an aggregate cache key to its two child cache keys.  It is
    intentionally explicit so a caller cannot accidentally derive an arbitrary
    query or turn a parent aggregate into a network target.
    """
    allowed = {cache_key(spec) for spec in DERIVED_AGGREGATES}
    if set(children) - allowed:
        raise CompletionBlocked("attempted recomputation of a non-derived aggregate")
    # Only up to four named top-level parent records are replaced.
    updated = dict(cache)
    receipts: list[dict[str, Any]] = []
    for parent_key in sorted(children):
        left_key, right_key = children[parent_key]
        if left_key not in updated or right_key not in updated:
            raise CompletionBlocked(f"missing aggregate child for {parent_key}")
        aggregate = aggregate_from_children(updated[left_key], updated[right_key])
        updated[parent_key] = aggregate
        receipts.append({
            "aggregate_key": parent_key,
            "children": [left_key, right_key],
            "response_sha256": aggregate["response_sha256"],
            "complete": aggregate["complete"],
        })
    receipt = {"schema": "mastermind.dislocation_p0.a1r_aggregate_receipt.v1", "aggregates": receipts}
    receipt["receipt_sha256"] = sha256_json(receipt)
    return updated, receipt


def write_retry_version(directory: Path, cache: Mapping[str, Any], receipt: Mapping[str, Any]) -> tuple[Path, Path]:
    """Persist a new cache/receipt pair; never overwrite the historical cache."""
    directory.mkdir(parents=True, exist_ok=True)
    digest = str(receipt["receipt_sha256"])
    cache_path = directory / f"fts_cache_retry_{digest[:16]}.json"
    receipt_path = directory / f"retry_receipt_{digest[:16]}.json"
    # json.dump emits the huge cache once without materialising a second giant
    # canonical-json string; separators/sort order remain canonical.
    with cache_path.open("w", encoding="utf-8") as handle:
        json.dump(cache, handle, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        handle.write("\n")
    with receipt_path.open("w", encoding="utf-8") as handle:
        json.dump(receipt, handle, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        handle.write("\n")
    return cache_path, receipt_path


def logical_cell_census(ledger: Mapping[str, Any], receipts: Iterable[Mapping[str, Any]]) -> dict[str, Any]:
    """Fail closed unless all 146 frozen logical query cells have receipts."""
    expected = {str(row["query_cell_id"]) for row in ledger.get("query_cells") or []}
    if len(expected) != 146:
        raise CompletionBlocked(f"frozen ledger must contain 146 logical cells, got {len(expected)}")
    receipt_rows = [dict(row) for row in receipts]
    ids = [str(row.get("query_cell_id") or "") for row in receipt_rows]
    duplicate_ids = sorted({cell_id for cell_id in ids if cell_id and ids.count(cell_id) > 1})
    seen = {str(row.get("query_cell_id")): bool(row.get("complete")) for row in receipt_rows}
    missing = sorted(expected - set(seen))
    incomplete = sorted(key for key in expected if seen.get(key) is False)
    unexpected = sorted(set(seen) - expected)
    result = {
        "schema": "mastermind.dislocation_p0.a1r_logical_cell_census.v1",
        "expected": len(expected),
        "complete": len(expected) - len(missing) - len(incomplete),
        "missing": missing,
        "incomplete": incomplete,
        "unexpected": unexpected,
        "duplicate_receipt_ids": duplicate_ids,
        "cell_ids": sorted(expected),
    }
    result["complete_sha256"] = sha256_json(sorted(key for key in expected if seen.get(key) is True))
    if missing or incomplete or unexpected or duplicate_ids:
        raise CompletionBlocked(canonical_json(result))
    return result


def _edge_key(edge: Mapping[str, Any]) -> tuple[str, str, str, str]:
    return (
        str(edge.get("query_cell_id") or ""), str(edge.get("phrase") or ""),
        str(edge.get("hit_id") or ""), str(edge.get("query_receipt_sha256") or ""),
    )


def merge_candidates(rows: Iterable[Mapping[str, Any]], complete_cells: set[str]) -> list[dict[str, Any]]:
    """Merge duplicate source identity while retaining every complete query edge."""
    merged: dict[tuple[str, str, str], dict[str, Any]] = {}
    global_edges: dict[tuple[str, str], list[dict[str, Any]]] = {}
    immutable: dict[tuple[str, str], dict[str, Any]] = {}
    for raw in rows:
        cik, accession = str(raw.get("cik") or ""), str(raw.get("accession") or "")
        if not cik or not accession:
            continue
        edges = [dict(edge) for edge in raw.get("query_edges") or []]
        if not edges:
            continue
        family = str(raw.get("family") or "")
        identity = (cik, accession)
        # SEC FTS may return multiple matching documents (primary/exhibits) for
        # one accession, so filename is edge provenance rather than a
        # filing-level immutable field.
        frozen = {field: raw.get(field) for field in ("form", "filed_on")}
        prior = immutable.setdefault(identity, frozen)
        if any(prior[field] != frozen[field] for field in frozen):
            raise CompletionBlocked("duplicate source identity has conflicting immutable metadata")
        for edge in edges:
            edge.setdefault("family_candidate", family)
            edge.setdefault("filename", raw.get("filename"))
        global_edges.setdefault(identity, []).extend(edges)
        key = (family, cik, accession)
        candidate = merged.setdefault(key, dict(raw) | {"query_edges": []})
        candidate["query_edges"].extend(edges)
    output: list[dict[str, Any]] = []
    for candidate in merged.values():
        identity = (str(candidate["cik"]), str(candidate["accession"]))
        edge_map = {_edge_key(edge): edge for edge in global_edges[identity]}
        candidate["query_edges"] = [edge_map[key] for key in sorted(edge_map)]
        candidate["filename"] = next((edge.get("filename") for edge in candidate["query_edges"] if edge.get("filename")), None)
        # Identity-level exclusion is intentional: a duplicate source record
        # cannot silently shed an incomplete provenance edge to become eligible.
        if any(str(edge.get("query_cell_id")) not in complete_cells for edge in candidate["query_edges"]):
            continue
        output.append(candidate)
    return sorted(output, key=lambda row: str(row.get("selection_key") or ""))


def complete_pool_hashes(rows: Iterable[Mapping[str, Any]]) -> dict[str, str]:
    """Hash the full eligible merged records, not merely their identities."""
    by_family: dict[str, list[dict[str, Any]]] = {family: [] for family in FAMILIES}
    for row in rows:
        family, key = str(row.get("family") or ""), str(row.get("selection_key") or "")
        if family in by_family and key:
            by_family[family].append({
                "selection_key": key, "era": row.get("era"), "form": row.get("form"),
                "base_form": row.get("base_form"), "cik": row.get("cik"), "accession": row.get("accession"),
                **{field: row.get(field) for field in SOURCE_PACKET_FIELDS if field != "base_form"},
                "query_edges": row.get("query_edges"),
            })
    return {family: sha256_json(sorted(items, key=canonical_json)) for family, items in sorted(by_family.items())}


def annual_top_level_specs(cell: Mapping[str, Any]) -> list[dict[str, str]]:
    """The only ten cache nodes the A1R compiler is allowed to read per cell."""
    phrase = str(cell["phrase"])
    form = base_form(str(cell.get("base_form") or cell.get("form") or ""))
    if form not in {"8-K", "6-K"}:
        raise CompletionBlocked("annual compiler ledger cell has no eligible base_form")
    return [
        {"phrase": phrase, "form": form, "start": f"{year}-01-01", "end": f"{year}-12-31"}
        for year in range(2016, 2026)
    ]


def compile_annual_source_plane(
    ledger: Mapping[str, Any], cache: Mapping[str, Any],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Compile logical-cell receipts and family candidates from annual roots only.

    No recursive/cache-wide walk occurs here: exactly ten annual top-level keys
    are looked up for every frozen ledger cell.  This makes a prior recursive
    split, stale cache orphan, or semantic sidecar incapable of admission.
    """
    cells = [dict(cell) for cell in ledger.get("query_cells") or []]
    cell_ids = [str(cell.get("query_cell_id") or "") for cell in cells]
    if len(cells) != 146 or len(set(cell_ids)) != 146 or not all(cell_ids):
        raise CompletionBlocked("annual compiler requires exactly 146 unique ledger cells")
    receipts: list[dict[str, Any]] = []
    raw_rows: list[dict[str, Any]] = []
    for cell in sorted(cells, key=lambda item: str(item["query_cell_id"])):
        annual = [(spec, cache.get(cache_key(spec))) for spec in annual_top_level_specs(cell)]
        missing = [spec for spec, record in annual if not isinstance(record, Mapping)]
        incomplete = [spec for spec, record in annual if isinstance(record, Mapping) and record.get("complete") is not True]
        response_hashes = [str(record.get("response_sha256") or "") for _, record in annual if isinstance(record, Mapping)]
        complete = not missing and not incomplete
        receipt = {
            "query_cell_id": cell["query_cell_id"], "complete": complete,
            "annual_keys": [cache_key(spec) for spec, _ in annual],
            "missing_annual_shards": missing, "incomplete_annual_shards": incomplete,
            "query_receipt_sha256": sha256_json(response_hashes),
        }
        receipts.append(receipt)
        if not complete:
            continue
        for _, record in annual:
            assert isinstance(record, Mapping)
            for hit in record.get("rows") or []:
                source = dict(hit)
                cik, accession = canonical_cik(source.get("cik")), canonical_accession(source.get("accession"))
                filed_on = source.get("filed_on")
                era = era_for_filed_on(str(filed_on) if filed_on is not None else None)
                ledger_base = base_form(str(cell.get("base_form") or cell.get("form") or ""))
                form = str(source.get("form") or ledger_base or "")
                frozen_base = base_form(form)
                if not cik or not accession or not era or not frozen_base or frozen_base != ledger_base:
                    continue
                family = str(cell.get("family") or source.get("family") or "")
                raw_rows.append({
                    **source, "family": family, "cik": cik, "accession": accession,
                    "filed_on": filed_on, "era": era, "form": form, "base_form": frozen_base,
                    "selection_key": selection_key(family=family, era=era, base=frozen_base, cik=cik, accession=accession),
                    "query_edges": [{
                        "query_cell_id": cell["query_cell_id"], "phrase": cell["phrase"],
                        "hit_id": source.get("hit_id"), "query_receipt_sha256": receipt["query_receipt_sha256"],
                        "family_candidate": family,
                    }],
                })
    complete_cells = {row["query_cell_id"] for row in receipts if row["complete"]}
    return receipts, merge_candidates(raw_rows, complete_cells)


SOURCE_PACKET_FIELDS = (
    "filed_on", "filename", "display_name", "ticker", "hit_id", "items", "base_form",
)


def eligible_candidates(rows: Iterable[Mapping[str, Any]], complete_cells: set[str]) -> list[dict[str, Any]]:
    """Return the exact complete, source-only candidate universe for selection.

    This is intentionally shared by the solver and manifest pool receipt: the
    pool hash cannot describe a broader pre-filter universe than the solver.
    """
    eligible: list[dict[str, Any]] = []
    for raw in merge_candidates(rows, complete_cells):
        family = str(raw.get("family") or "")
        cik = canonical_cik(raw.get("cik"))
        accession = canonical_accession(raw.get("accession"))
        raw_form = str(raw.get("form") or "")
        frozen_base = base_form(raw_form)
        filed_on = raw.get("filed_on")
        inferred_era = era_for_filed_on(str(filed_on) if filed_on is not None else None)
        if (family not in FAMILIES or not cik or not accession or not frozen_base
                or inferred_era not in {"modern", "development"}):
            continue
        # Amendments and fixed design exclusions are never source origins.
        if is_amendment(raw_form) or is_design_excluded(
            ticker=raw.get("ticker"), cik=cik, display_name=raw.get("display_name"),
        ):
            continue
        if raw.get("base_form") not in (None, frozen_base):
            raise CompletionBlocked("candidate base_form disagrees with frozen form")
        if raw.get("era") not in (None, inferred_era):
            raise CompletionBlocked("candidate era disagrees with frozen filed_on")
        expected_key = selection_key(family=family, era=inferred_era, base=frozen_base, cik=cik, accession=accession)
        if raw.get("selection_key") != expected_key:
            raise CompletionBlocked("candidate selection_key does not recompute from frozen fields")
        candidate = dict(raw)
        candidate.update({"cik": cik, "accession": accession, "era": inferred_era, "form": frozen_base, "base_form": frozen_base})
        eligible.append(candidate)
    return sorted(eligible, key=lambda row: str(row["selection_key"]))


def _plans() -> Iterable[dict[tuple[str, str, str], int]]:
    # For 3 packets, 2 modern/1 development and 2 8-K/1 6-K permit A or B.
    triples = (
        {("modern", "8-K"): 2, ("development", "6-K"): 1},
        {("modern", "8-K"): 1, ("modern", "6-K"): 1, ("development", "8-K"): 1},
    )
    pairs = (
        {("modern", "8-K"): 1, ("development", "6-K"): 1},
        {("modern", "6-K"): 1, ("development", "8-K"): 1},
    )
    for choices in itertools.product(triples, repeat=6):
        for pair in pairs:
            plan: dict[tuple[str, str, str], int] = {}
            for family, pattern in zip(FAMILIES[:6], choices):
                for (era, form), count in pattern.items():
                    plan[(family, era, form)] = count
            for (era, form), count in pair.items():
                plan[(RESOLVED_CONTROL, era, form)] = count
            yield plan


def _feasible(rows: list[dict[str, Any]], demand: Mapping[tuple[str, str, str], int], chosen: list[dict[str, Any]], index: Mapping[tuple[str, str, str], list[dict[str, Any]]] | None = None, rejected_keys: set[str] | None = None) -> bool:
    """Small deterministic DFS feasibility oracle (exactly twenty slots)."""
    used_identities = {
        (str(row["cik"]), str(row["accession"])) for row in chosen
    }
    remaining = dict(demand)
    for row in chosen:
        slot = (str(row["family"]), str(row["era"]), str(row["form"]))
        remaining[slot] = remaining.get(slot, 0) - 1
        if remaining[slot] < 0:
            return False
    slots = [slot for slot, count in remaining.items() for _ in range(count)]
    if not slots:
        return True
    options: dict[tuple[str, str, str], list[dict[str, Any]]] = {}
    rejected_keys = rejected_keys or set()
    for slot in set(slots):
        source = index.get(slot, []) if index is not None else rows
        options[slot] = [row for row in source if str(row["selection_key"]) not in rejected_keys]
    if any(len(options[slot]) < slots.count(slot) for slot in set(slots)):
        return False
    slots.sort(key=lambda slot: (len(options[slot]), slot))

    # Feasibility is a 20-slot bipartite matching problem: demanded margin
    # slots are on the left and canonical filing identities are on the right.
    # This avoids an exponential search across the 277k-row completed pool and
    # implements the frozen uniqueness law exactly.  A CIK may appear more than
    # once when the accessions differ; only the pair is an occupied identity.
    demanded_slots = list(enumerate(slots))
    matched_slot_by_identity: dict[tuple[str, str], int] = {}

    def augment(slot_index: int, visited: set[tuple[str, str]]) -> bool:
        slot = demanded_slots[slot_index][1]
        for row in options[slot]:
            identity = (str(row["cik"]), str(row["accession"]))
            if identity in used_identities or identity in visited:
                continue
            visited.add(identity)
            occupied = matched_slot_by_identity.get(identity)
            if occupied is None or augment(occupied, visited):
                matched_slot_by_identity[identity] = slot_index
                return True
        return False

    return all(augment(slot_index, set()) for slot_index, _slot in demanded_slots)


def _solve_plan(rows: list[dict[str, Any]], plan: Mapping[tuple[str, str, str], int]) -> list[dict[str, Any]] | None:
    selected: list[dict[str, Any]] = []
    rejected: set[str] = set()
    index: dict[tuple[str, str, str], list[dict[str, Any]]] = {}
    for row in rows:
        index.setdefault((str(row["family"]), str(row["era"]), str(row["form"])), []).append(row)
    used_identities: set[tuple[str, str]] = set()
    for row in rows:
        trial = selected + [row]
        key = str(row["selection_key"])
        identity = (str(row["cik"]), str(row["accession"]))
        if identity in used_identities:
            rejected.add(key)
            continue
        if _feasible(rows, plan, trial, index, rejected):
            selected.append(row)
            used_identities.add(identity)
        else:
            rejected.add(key)
        if len(selected) == 20:
            return sorted(selected, key=lambda item: str(item["selection_key"]))
    return None


def solve_exact20(rows: Iterable[Mapping[str, Any]], census: Mapping[str, Any]) -> list[dict[str, Any]]:
    """Return the lexicographically smallest source-only feasible packet set."""
    if census.get("expected") != 146 or census.get("complete") != 146:
        raise CompletionBlocked("exact-20 requires a complete 146-cell census")
    complete_cells = set(census.get("cell_ids") or [])
    if len(complete_cells) != 146:
        raise CompletionBlocked("exact-20 requires explicit complete cell identities")
    candidates = eligible_candidates(rows, complete_cells)
    solutions = [solution for plan in _plans() if (solution := _solve_plan(candidates, plan))]
    if not solutions:
        raise AllocationInfeasible("no exact-20 source-only allocation satisfies frozen margins")
    return min(solutions, key=lambda solution: tuple(str(row["selection_key"]) for row in solution))


def exact20_manifest(rows: Iterable[Mapping[str, Any]], census: Mapping[str, Any]) -> dict[str, Any]:
    materialized = [dict(row) for row in rows]
    complete_cells = set(census.get("cell_ids") or [])
    pool = eligible_candidates(materialized, complete_cells)
    selected = solve_exact20(pool, census)
    packets = [{
        "candidate_id": f"p0cand_{row['selection_key']}", "selection_key": row["selection_key"],
        "family": row["family"], "era": row["era"], "form": row["form"],
        "cik": row["cik"], "accession": row["accession"], "query_edges": row["query_edges"],
        **{field: row.get(field) for field in SOURCE_PACKET_FIELDS},
    } for row in selected]
    manifest = {
        "schema": "mastermind.dislocation_p0.a1r_exact20_source_manifest.v2",
        "n": 20,
        "selection_identity": ["cik", "accession"],
        "supersedes": {
            "reason": "GLOBAL_CIK_UNIQUENESS_WAS_STRICTER_THAN_FROZEN_SOURCE_LAW",
            "manifest_sha256": "f44f37d5f44b4c3eabb5098004afa4aed8c40a173404709084a82152741d36bf",
            "file_sha256": "2635a5c6787d5fd60be8f08177d699e65c9f83ab39bdfec4e616b11d4b3e45fa",
        },
        "candidates": packets,
        "pool_sha256_by_family": complete_pool_hashes(pool),
        "logical_cell_complete_sha256": census["complete_sha256"],
        "authority": {"can_rank": False, "can_gate": False, "can_size": False, "can_originate_signal": False, "can_escalate": False},
    }
    manifest["manifest_sha256"] = sha256_json(manifest)
    return manifest


def manifest_bytes(manifest: Mapping[str, Any]) -> bytes:
    return (canonical_json(manifest) + "\n").encode("utf-8")
