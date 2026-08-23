"""Offline proofs for the Dislocation P0-A1R exact-20 source freeze."""
from __future__ import annotations

from copy import deepcopy

import pytest

from scripts.research.dislocation_p0_a1r import (
    AllocationInfeasible,
    CompletionBlocked,
    DERIVED_AGGREGATES,
    FAILED_LEAVES,
    FAMILIES,
    aggregate_from_children,
    annual_top_level_specs,
    cache_key,
    compile_annual_source_plane,
    complete_pool_hashes,
    eligible_candidates,
    exact20_manifest,
    merge_candidates,
    logical_cell_census,
    manifest_bytes,
    recompute_derived_aggregates,
    retry_only_completion,
    retry_targets,
    solve_exact20,
)
from scripts.research.dislocation_p0_a1_lib import build_query_ledger, selection_key


def _ledger() -> dict:
    return {"query_cells": [{"query_cell_id": f"cell-{idx:03d}"} for idx in range(146)]}


def _census() -> dict:
    ledger = _ledger()
    receipts = [{"query_cell_id": row["query_cell_id"], "complete": True} for row in ledger["query_cells"]]
    return logical_cell_census(ledger, receipts)


def _row(family: str, era: str, form: str, key: str, *, cik: str | None = None, accession: str | None = None, edges: list[dict] | None = None, semantic: object = None) -> dict:
    serial = int(key[-4:], 16) if all(ch in "0123456789abcdef" for ch in key[-4:]) else len(key)
    real_cik = cik or f"{serial + 1:010d}"
    real_accession = accession or f"{serial + 1:010d}-24-{serial:06d}"
    filed_on = "2024-01-02" if era == "modern" else "2020-01-02"
    return {
        "family": family,
        "era": era,
        "form": form,
        "selection_key": selection_key(family=family, era=era, base=form, cik=real_cik, accession=real_accession),
        "cik": real_cik, "accession": real_accession,
        "filed_on": filed_on, "filename": f"{key}.htm", "display_name": f"Issuer {key}",
        "ticker": f"T{serial}", "hit_id": f"hit-{key}", "items": ["1.01"], "base_form": form,
        "query_edges": edges or [{"query_cell_id": "cell-000", "phrase": "frozen", "hit_id": key, "query_receipt_sha256": "r"}],
        "classification": semantic,
        "audit": {"verdict": semantic},
    }


def _feasible_rows() -> list[dict]:
    rows: list[dict] = []
    counter = 1
    for family in FAMILIES:
        # Pattern A for every family: 2 modern 8-K plus 1 development 6-K.
        pattern = [("modern", "8-K"), ("development", "6-K")] if family.endswith("RESOLVED_BEFORE_DISCLOSURE_CONTROL") else [("modern", "8-K"), ("modern", "8-K"), ("development", "6-K")]
        for era, form in pattern:
            rows.append(_row(family, era, form, f"{counter:064x}"))
            counter += 1
    return rows


def test_census_requires_exactly_146_complete_logical_cells() -> None:
    ledger = _ledger()
    receipts = [{"query_cell_id": row["query_cell_id"], "complete": True} for row in ledger["query_cells"][:-1]]
    with pytest.raises(CompletionBlocked):
        logical_cell_census(ledger, receipts)
    census = _census()
    assert census["expected"] == census["complete"] == 146
    assert len(census["cell_ids"]) == 146


def test_exact20_allocation_margins_and_byte_identical_serialization() -> None:
    rows, census = _feasible_rows(), _census()
    manifest = exact20_manifest(rows, census)
    assert manifest["n"] == 20
    packets = manifest["candidates"]
    assert [row["selection_key"] for row in packets] == sorted(row["selection_key"] for row in packets)
    assert len({(row["cik"], row["accession"]) for row in packets}) == 20
    assert manifest["selection_identity"] == ["cik", "accession"]
    for family in FAMILIES:
        family_rows = [row for row in packets if row["family"] == family]
        if family.endswith("RESOLVED_BEFORE_DISCLOSURE_CONTROL"):
            assert len(family_rows) == 2
            assert {row["era"] for row in family_rows} == {"modern", "development"}
            assert {row["form"] for row in family_rows} == {"8-K", "6-K"}
        else:
            assert len(family_rows) == 3
            assert sum(row["era"] == "modern" for row in family_rows) == 2
            assert sum(row["form"] == "8-K" for row in family_rows) == 2
    assert manifest_bytes(manifest) == manifest_bytes(exact20_manifest(deepcopy(rows), census))


def test_same_cik_with_different_accession_is_allowed() -> None:
    rows = _feasible_rows()
    physical = rows[0]
    external_dev = next(row for row in rows if row["family"] == "EXTERNAL_HUMAN_INTERRUPTION" and row["era"] == "development")
    physical["cik"] = external_dev["cik"]
    physical["selection_key"] = selection_key(
        family=physical["family"], era=physical["era"], base=physical["form"],
        cik=physical["cik"], accession=physical["accession"],
    )
    selected = solve_exact20(rows, _census())
    identities = {(row["cik"], row["accession"]) for row in selected}
    assert (physical["cik"], physical["accession"]) in identities
    assert (external_dev["cik"], external_dev["accession"]) in identities
    assert physical["cik"] == external_dev["cik"]
    assert physical["accession"] != external_dev["accession"]


def test_query_edges_are_merged_sorted_and_incomplete_edge_is_excluded() -> None:
    rows = _feasible_rows()
    original = rows[0]
    duplicate = deepcopy(original)
    duplicate["query_edges"] = [
        {"query_cell_id": "cell-001", "phrase": "b", "hit_id": "z", "query_receipt_sha256": "2"},
        {"query_cell_id": "cell-000", "phrase": "a", "hit_id": "a", "query_receipt_sha256": "1"},
    ]
    rows.append(duplicate)
    manifest = exact20_manifest(rows, _census())
    packet = next(row for row in manifest["candidates"] if row["selection_key"] == original["selection_key"])
    assert [edge["query_cell_id"] for edge in packet["query_edges"]] == sorted(edge["query_cell_id"] for edge in packet["query_edges"])
    assert {edge["query_cell_id"] for edge in packet["query_edges"]} == {"cell-000", "cell-001"}
    bad = deepcopy(rows)
    bad[0]["query_edges"].append({"query_cell_id": "unknown", "phrase": "bad", "hit_id": "bad", "query_receipt_sha256": "bad"})
    # A replacement exists, so completion remains possible without deleting the
    # bad edge; the contaminated row itself cannot enter the manifest.
    bad.append(_row("PHYSICAL_MECHANICAL_INTERRUPTION", "modern", "8-K", "e" * 64))
    selected = solve_exact20(bad, _census())
    assert bad[0]["selection_key"] not in {row["selection_key"] for row in selected}


def test_semantic_fields_do_not_affect_admission_or_manifest() -> None:
    rows = _feasible_rows()
    before = exact20_manifest(rows, _census())
    changed = deepcopy(rows)
    for row in changed:
        row["classification"] = {"outcome": 999, "event_family": "INVENTED"}
        row["audit"] = {"verdict": "PASS", "price": 123}
    assert manifest_bytes(before) == manifest_bytes(exact20_manifest(changed, _census()))


def test_incomplete_census_blocks_before_any_selection() -> None:
    census = _census() | {"complete": 145}
    with pytest.raises(CompletionBlocked):
        solve_exact20(_feasible_rows(), census)


def test_retry_only_calls_five_named_failed_leaves_and_preserves_original_cache() -> None:
    cache = {cache_key(leaf): {"complete": False, "response_sha256": f"old-{idx}"} for idx, leaf in enumerate(FAILED_LEAVES)}
    cache[cache_key(DERIVED_AGGREGATES[0])] = {"complete": False, "response_sha256": "aggregate"}
    called: list[dict] = []
    def fetch(leaf: dict) -> dict:
        called.append(dict(leaf))
        return {"complete": True, "response_sha256": f"new-{len(called)}", "rows": []}
    updated, receipt = retry_only_completion(cache, fetch)
    assert called == list(FAILED_LEAVES)
    assert retry_targets(updated) == []
    assert cache[cache_key(FAILED_LEAVES[0])]["complete"] is False
    assert receipt["derived_aggregates"] == list(DERIVED_AGGREGATES)


def test_aggregate_receipt_is_local_and_deduplicates_sorted_hits() -> None:
    left = {"start": "a", "end": "b", "complete": True, "total_hits": 2, "response_sha256": "left", "rows": [{"hit_id": "b"}, {"hit_id": "a"}]}
    right = {"start": "c", "end": "d", "complete": True, "total_hits": 2, "response_sha256": "right", "rows": [{"hit_id": "b"}, {"hit_id": "c"}]}
    aggregate = aggregate_from_children(left, right)
    assert aggregate["complete"] is True
    assert [row["hit_id"] for row in aggregate["rows"]] == ["a", "b", "c"]
    assert aggregate["response_sha256"] == aggregate_from_children(left, right)["response_sha256"]
    parent_key = cache_key(DERIVED_AGGREGATES[0])
    copied, receipt = recompute_derived_aggregates(
        {"left": left, "right": right}, {parent_key: ("left", "right")}
    )
    assert copied[parent_key] == aggregate
    assert receipt["aggregates"][0]["aggregate_key"] == parent_key


def test_duplicate_logical_receipt_id_is_a_fail_closed_error() -> None:
    ledger = _ledger()
    receipts = [{"query_cell_id": row["query_cell_id"], "complete": True} for row in ledger["query_cells"]]
    receipts.append(dict(receipts[0]))
    with pytest.raises(CompletionBlocked, match="duplicate_receipt_ids"):
        logical_cell_census(ledger, receipts)


def test_cross_family_same_filing_remains_two_options_but_cannot_both_select() -> None:
    rows = _feasible_rows()
    original = rows[0]
    other_family = "EXTERNAL_HUMAN_INTERRUPTION"
    clone = _row(other_family, "modern", "8-K", "abcd", cik=original["cik"], accession=original["accession"])
    for field in ("filed_on", "filename", "display_name", "ticker", "hit_id", "items"):
        clone[field] = original[field]
    rows.append(clone)
    merged = merge_candidates(rows, set(_census()["cell_ids"]))
    assert sum(row["cik"] == original["cik"] and row["accession"] == original["accession"] for row in merged) == 2
    selected = solve_exact20(rows, _census())
    assert sum(row["cik"] == original["cik"] and row["accession"] == original["accession"] for row in selected) == 1


def test_amendments_and_design_exclusions_are_not_admitted() -> None:
    rows = _feasible_rows()
    amended = rows[0]
    amended["form"] = "8-K/A"
    amended["base_form"] = "8-K"
    # Its selection key remains a valid frozen base key, so only amendment law
    # is responsible for refusal.
    rows.append(_row(amended["family"], "modern", "8-K", "eeee"))
    excluded = rows[1]
    excluded["ticker"] = "EXK"
    rows.append(_row(excluded["family"], "modern", "8-K", "ffff"))
    selected = solve_exact20(rows, _census())
    assert amended["accession"] not in {row["accession"] for row in selected}
    assert excluded["accession"] not in {row["accession"] for row in selected}


def test_selection_key_and_source_packet_metadata_are_frozen() -> None:
    rows = _feasible_rows()
    manifest = exact20_manifest(rows, _census())
    packet = manifest["candidates"][0]
    for field in ("filed_on", "filename", "display_name", "ticker", "hit_id", "items", "base_form"):
        assert field in packet
    bad = deepcopy(rows)
    bad[0]["selection_key"] = "0" * 64
    with pytest.raises(CompletionBlocked, match="selection_key"):
        solve_exact20(bad, _census())
    assert manifest["pool_sha256_by_family"] == complete_pool_hashes(
        eligible_candidates(rows, set(_census()["cell_ids"]))
    )


def test_retry_shallow_copy_does_not_mutate_nested_historical_cache() -> None:
    nested = {"complete": False, "response_sha256": "old", "rows": [{"deep": ["preserved"]}]}
    cache = {cache_key(FAILED_LEAVES[0]): nested}
    updated, _ = retry_only_completion(cache, lambda _: {"complete": True, "response_sha256": "new", "rows": []})
    assert cache[cache_key(FAILED_LEAVES[0])] is nested
    assert cache[cache_key(FAILED_LEAVES[0])]["rows"][0]["deep"] == ["preserved"]
    assert updated[cache_key(FAILED_LEAVES[0])] is not nested


def test_annual_compiler_reads_only_ten_top_level_shards_per_ledger_cell() -> None:
    ledger = {"query_cells": [
        {"query_cell_id": f"annual-{idx:03d}", "family": FAMILIES[idx % len(FAMILIES)], "phrase": f"p{idx}", "form": "8-K"}
        for idx in range(146)
    ]}
    cache: dict[str, dict] = {}
    for cell in ledger["query_cells"]:
        for year in range(2016, 2026):
            spec = {"phrase": cell["phrase"], "form": "8-K", "start": f"{year}-01-01", "end": f"{year}-12-31"}
            cache[cache_key(spec)] = {"complete": True, "response_sha256": f"{cell['query_cell_id']}-{year}", "rows": []}
    first = ledger["query_cells"][0]
    cache[cache_key({"phrase": first["phrase"], "form": "8-K", "start": "2024-01-01", "end": "2024-12-31"})]["rows"] = [{
        "cik": "0000000001", "accession": "0000000001-24-000001", "filed_on": "2024-01-02",
        "form": "8-K", "hit_id": "annual-source", "filename": "annual.htm", "display_name": "Annual issuer",
    }]
    cache["recursive-orphan"] = {"complete": True, "rows": [{"cik": "0000000001", "accession": "0000000001-24-000001", "hit_id": "rogue"}]}
    receipts, candidates = compile_annual_source_plane(ledger, cache)
    assert len(receipts) == 146 and all(row["complete"] for row in receipts)
    assert [row["hit_id"] for row in candidates] == ["annual-source"]
    assert candidates[0]["family"] == first["family"]


def test_annual_compiler_accepts_frozen_ledger_base_form_shape() -> None:
    ledger = build_query_ledger()
    cache: dict[str, dict] = {}
    for cell in ledger["query_cells"]:
        for spec in annual_top_level_specs(cell):
            cache[cache_key(spec)] = {"complete": True, "response_sha256": cache_key(spec), "rows": []}
    receipts, candidates = compile_annual_source_plane(ledger, cache)
    assert len(receipts) == 146 and all(receipt["complete"] for receipt in receipts)
    assert candidates == []


def test_family_options_share_global_edges_and_allow_multiple_fts_documents() -> None:
    rows = _feasible_rows()
    original = rows[0]
    other = _row("EXTERNAL_HUMAN_INTERRUPTION", "modern", "8-K", "beef", cik=original["cik"], accession=original["accession"])
    for field in ("filed_on", "filename", "display_name", "ticker", "hit_id", "items"):
        other[field] = original[field]
    other["query_edges"] = [{"query_cell_id": "cell-002", "phrase": "cyber", "hit_id": "other", "query_receipt_sha256": "q"}]
    merged = merge_candidates(rows + [other], set(_census()["cell_ids"]))
    options = [row for row in merged if row["cik"] == original["cik"] and row["accession"] == original["accession"]]
    assert len(options) == 2
    assert all({edge["query_cell_id"] for edge in row["query_edges"]} == {"cell-000", "cell-002"} for row in options)
    assert {edge["family_candidate"] for edge in options[0]["query_edges"]} == {original["family"], other["family"]}
    second_document = deepcopy(other)
    second_document["filename"] = "different.htm"
    second_document["query_edges"] = [{
        "query_cell_id": "cell-003", "phrase": "exhibit match",
        "hit_id": "other-exhibit", "query_receipt_sha256": "q2",
    }]
    with_exhibit = merge_candidates(
        rows + [other, second_document], set(_census()["cell_ids"])
    )
    exhibit_option = next(
        row for row in with_exhibit
        if row["family"] == other["family"]
        and row["cik"] == original["cik"]
        and row["accession"] == original["accession"]
    )
    assert {edge["filename"] for edge in exhibit_option["query_edges"]} == {
        original["filename"], "different.htm",
    }

    conflicted = deepcopy(other)
    conflicted["filed_on"] = "2023-01-01"
    with pytest.raises(CompletionBlocked, match="immutable metadata"):
        merge_candidates(rows + [other, conflicted], set(_census()["cell_ids"]))


def test_annual_compiler_excludes_hit_whose_form_disagrees_with_ledger_base_form() -> None:
    ledger = {"query_cells": [
        {"query_cell_id": f"shape-{idx}", "family": FAMILIES[0], "phrase": f"shape-{idx}", "base_form": "8-K"}
        for idx in range(146)
    ]}
    cache = {cache_key(spec): {"complete": True, "response_sha256": cache_key(spec), "rows": []}
             for cell in ledger["query_cells"] for spec in annual_top_level_specs(cell)}
    first = ledger["query_cells"][0]
    cache[cache_key(annual_top_level_specs(first)[0])]["rows"] = [{
        "cik": "0000000001", "accession": "0000000001-24-000001", "filed_on": "2024-01-02",
        "form": "6-K", "hit_id": "wrong-form",
    }]
    _, candidates = compile_annual_source_plane(ledger, cache)
    assert candidates == []


def test_solver_scale_keeps_small_manifest_lexicographically_identical() -> None:
    rows, census = _feasible_rows(), _census()
    expected = exact20_manifest(rows, census)
    ceiling = max(packet["selection_key"] for packet in expected["candidates"])
    scaled = list(rows)
    accepted = 0
    serial = 1000
    while accepted < 40:
        candidate = _row(
            "PHYSICAL_MECHANICAL_INTERRUPTION", "modern", "8-K", f"{serial:064x}",
            cik=f"{serial:010d}", accession=f"{serial:010d}-24-{serial:06d}",
            edges=[{"query_cell_id": f"cell-{edge:03d}", "phrase": "load", "hit_id": f"{serial}-{edge}", "query_receipt_sha256": "load"} for edge in range(100)],
        )
        serial += 1
        if candidate["selection_key"] <= ceiling:
            continue
        scaled.append(candidate)
        accepted += 1
    assert exact20_manifest(scaled, census)["candidates"] == expected["candidates"]
