"""Focused adversarial tests for dark ClinicalTrials.gov discovery control."""
from __future__ import annotations

import copy
from pathlib import Path

import pytest

from engine.biocatalyst.discovery import (
    DiscoveryError,
    build_discovery_coverage_epoch,
    build_discovery_scope,
    reconcile_discovery_run,
    validate_discovery_coverage_epoch,
    validate_discovery_run,
    validate_discovery_scope,
)
from engine.sector_intelligence import canonical_json_sha256, validate_contract
from engine.sector_intelligence.contracts import ContractValidationError


ROOT = Path(__file__).resolve().parents[1]
HASH_A = "a" * 64
HASH_B = "b" * 64
HASH_C = "c" * 64
TOKEN_A = "d" * 64
_MISSING = object()


def _scope(start: str = "2026-08-01", end: str = "2026-08-02") -> dict:
    return build_discovery_scope(selection_start_date=start, selection_end_date=end)


def _page(
    *,
    ordinal: int = 0,
    request: str | None = None,
    next_token: str | None = None,
    total: int | None = 1,
    nct_id: str = "NCT00000001",
    content: str = HASH_B,
    updated: str = "2026-08-01",
    received_at: str = "2026-08-03T00:01:00Z",
) -> dict:
    return {
        "page_ordinal": ordinal,
        "response_sha256": HASH_A if ordinal == 0 else HASH_C,
        "byte_count": 100,
        "received_at": received_at,
        "request_page_token_sha256": request,
        "next_page_token_sha256": next_token,
        "total_count": total,
        "records": [
            {
                "nct_id": nct_id,
                "canonical_content_sha256": content,
                "last_update_posted_date": updated,
            }
        ],
    }


def _version(*, timestamp: str = "2026-08-03T00:00:00Z", retrieved_at: str = "2026-08-03T00:00:00Z") -> dict:
    return {"data_timestamp_raw": timestamp, "api_version": "2.0", "retrieved_at": retrieved_at}


def _run(
    *,
    scope: dict | None = None,
    run_id: str = "ctgov_discovery_run_one",
    pages: list[dict] | None = None,
    before: dict | None | object = _MISSING,
    after: dict | None | object = _MISSING,
    started_at: str = "2026-08-03T00:00:00Z",
    finished_at: str = "2026-08-03T00:03:00Z",
    transaction_from: str = "2026-08-03T00:03:00Z",
) -> dict:
    return reconcile_discovery_run(
        scope=scope or _scope(),
        run_id=run_id,
        pages=pages if pages is not None else [_page()],
        source_version_before=_version() if before is _MISSING else before,
        source_version_after=_version(retrieved_at="2026-08-03T00:02:00Z") if after is _MISSING else after,
        started_at=started_at,
        finished_at=finished_at,
        transaction_from=transaction_from,
    )


def _rehash_scope(document: dict) -> None:
    identity = {key: value for key, value in document.items() if key not in {"scope_id", "scope_payload_sha256"}}
    document["scope_id"] = f"ctgov_discovery_scope_{canonical_json_sha256(identity)[:24]}"
    document["scope_payload_sha256"] = canonical_json_sha256(
        {key: value for key, value in document.items() if key != "scope_payload_sha256"}
    )


def _rehash(document: dict, field: str) -> None:
    document[field] = canonical_json_sha256({key: value for key, value in document.items() if key != field})


def _bind_scope_and_rehash_run(document: dict, scope: dict) -> dict:
    forged = copy.deepcopy(document)
    forged["scope"] = scope
    forged["scope_ref"] = scope["scope_id"]
    forged["scope_payload_sha256"] = scope["scope_payload_sha256"]
    _rehash(forged, "run_payload_sha256")
    return forged


def _time_shift(timestamp: str, seconds: int) -> str:
    return f"2026-08-03T00:{seconds:02d}:00Z"


def test_scope_binds_canonical_filter_and_every_harness_limit() -> None:
    scope = _scope()

    validate_contract(scope, repo_root=ROOT)
    assert scope["contract_id"] == "ctgov_discovery_scope.v1"
    assert scope["selection_window"]["query_expression"] == "AREA[LastUpdatePostDate]RANGE[2026-08-01,2026-08-02]"
    assert scope["source_query"]["minimal_fields"] == [
        "protocolSection.identificationModule.nctId",
        "protocolSection.statusModule.lastUpdatePostDateStruct.date",
    ]
    assert scope["source_query"]["record_cap"] == scope["source_query"]["page_size"] * scope["source_query"]["page_cap"]
    assert scope["source_query"]["page_record_cap"] == scope["source_query"]["page_size"]
    assert scope["scope_semantics"]["global_coverage"] == "not_all_clinicaltrials_gov"


def test_scope_rejects_malformed_ranges_and_inconsistent_capacity() -> None:
    with pytest.raises(DiscoveryError, match="DISCOVERY_SELECTION_WINDOW_INVALID"):
        build_discovery_scope(selection_start_date="2026-08-02", selection_end_date="2026-08-01")
    with pytest.raises(DiscoveryError, match="DISCOVERY_CAPACITY_INCONSISTENT"):
        build_discovery_scope(selection_start_date="2026-08-01", selection_end_date="2026-08-02", page_size=10, page_cap=10, record_cap=99)

    forged = _scope()
    forged["selection_window"]["start_date"] = "2026-08-03"
    _rehash_scope(forged)
    with pytest.raises(ContractValidationError, match="discovery.window_order"):
        validate_discovery_scope(forged)


def test_run_is_deterministic_and_reconciles_terminal_total_count() -> None:
    scope = _scope()
    first = _page(next_token=TOKEN_A, total=2, received_at="2026-08-03T00:01:00Z")
    second = _page(
        ordinal=1,
        request=TOKEN_A,
        total=2,
        nct_id="NCT00000002",
        content=HASH_C,
        updated="2026-08-02",
        received_at="2026-08-03T00:01:30Z",
    )
    first_run = _run(scope=scope, pages=[second, first], run_id="ctgov_discovery_run_order")
    second_run = _run(scope=dict(reversed(list(scope.items()))), pages=[first, second], run_id="ctgov_discovery_run_order")

    assert first_run == second_run
    assert first_run["run_state"] == "complete"
    assert first_run["counts"] == {
        "pages": 2,
        "records_returned": 2,
        "records_unique": 2,
        "records_duplicates": 0,
        "declared_total_count": 2,
    }
    assert [row["nct_id"] for row in first_run["deduplicated_records"]] == ["NCT00000001", "NCT00000002"]


def test_run_quarantines_when_any_later_page_omits_required_total_count() -> None:
    first = _page(next_token=TOKEN_A, total=2)
    second = _page(
        ordinal=1,
        request=TOKEN_A,
        total=None,
        nct_id="NCT00000002",
        content=HASH_C,
        updated="2026-08-02",
        received_at="2026-08-03T00:01:30Z",
    )

    run = _run(pages=[first, second], run_id="ctgov_discovery_run_missing_later_total")

    assert run["run_state"] == "quarantined"
    assert "DISCOVERY_TOTAL_COUNT_MISMATCH" in run["quarantine_codes"]
    assert run["deduplicated_records"] == []


@pytest.mark.parametrize(
    ("pages", "code"),
    [
        ([_page(next_token=TOKEN_A), _page(ordinal=1, request=TOKEN_A, next_token=TOKEN_A, total=2, nct_id="NCT00000002")], "DISCOVERY_PAGE_CHAIN_INVALID"),
        ([_page(total=2)], "DISCOVERY_TOTAL_COUNT_MISMATCH"),
        ([_page(next_token=TOKEN_A)], "DISCOVERY_PAGE_CHAIN_INVALID"),
        ([_page(next_token=None), _page(ordinal=1, request=None, total=2, nct_id="NCT00000002")], "DISCOVERY_PAGE_CHAIN_INVALID"),
    ],
)
def test_run_quarantines_token_cycles_terminal_failures_and_count_mismatch(pages: list[dict], code: str) -> None:
    run = _run(pages=pages, run_id=f"ctgov_discovery_run_{code.lower()}")
    assert run["run_state"] == "quarantined"
    assert code in run["quarantine_codes"]
    assert run["deduplicated_records"] == []


def test_run_quarantines_any_duplicate_nct_and_source_version_race() -> None:
    duplicate = _run(
        pages=[
            _page(next_token=TOKEN_A, total=1),
            _page(ordinal=1, request=TOKEN_A, total=1, content=HASH_C, received_at="2026-08-03T00:01:30Z"),
        ],
        run_id="ctgov_discovery_run_duplicate",
    )
    assert duplicate["run_state"] == "quarantined"
    assert "DISCOVERY_DUPLICATE_CONTENT_AMBIGUITY" in duplicate["quarantine_codes"]
    assert duplicate["deduplicated_records"] == []

    raced = _run(
        after=_version(timestamp="2026-08-03T00:00:01Z", retrieved_at="2026-08-03T00:02:00Z"),
        run_id="ctgov_discovery_run_race",
    )
    assert raced["run_state"] == "quarantined"
    assert "DISCOVERY_SOURCE_VERSION_RACE" in raced["quarantine_codes"]
    assert raced["deduplicated_records"] == []


def test_run_quarantines_duplicate_page_content_even_with_distinct_records() -> None:
    first = _page(next_token=TOKEN_A, total=2)
    second = _page(
        ordinal=1,
        request=TOKEN_A,
        total=2,
        nct_id="NCT00000002",
        content=HASH_C,
        received_at="2026-08-03T00:01:30Z",
    )
    second["response_sha256"] = first["response_sha256"]

    run = _run(pages=[first, second], run_id="ctgov_discovery_run_duplicate_page")

    assert run["run_state"] == "quarantined"
    assert "DISCOVERY_DUPLICATE_CONTENT_AMBIGUITY" in run["quarantine_codes"]
    assert run["deduplicated_records"] == []


def test_preterminal_quarantine_has_empty_output_and_time_chain_is_fail_closed() -> None:
    preterminal = _run(
        pages=[],
        after=None,
        run_id="ctgov_discovery_run_preterminal",
    )
    assert preterminal["run_state"] == "quarantined"
    assert preterminal["counts"]["pages"] == 0
    assert preterminal["deduplicated_records"] == []
    assert "DISCOVERY_PAGE_CHAIN_INVALID" in preterminal["quarantine_codes"]
    assert "DISCOVERY_SOURCE_VERSION_INCOMPLETE" in preterminal["quarantine_codes"]

    bad_time = _run(
        pages=[_page(received_at="2026-08-03T00:03:30Z")],
        run_id="ctgov_discovery_run_bad_time",
    )
    assert "DISCOVERY_TIME_CHAIN_INVALID" in bad_time["quarantine_codes"]


def test_scope_and_run_capacity_limits_reject_before_unbounded_output() -> None:
    with pytest.raises(DiscoveryError, match="DISCOVERY_CAPACITY_INCONSISTENT"):
        build_discovery_scope(selection_start_date="2026-08-01", selection_end_date="2026-08-01", page_size=1000, page_cap=201, record_cap=200_000)
    scoped = build_discovery_scope(selection_start_date="2026-08-01", selection_end_date="2026-08-01", page_size=1, page_cap=2, record_cap=2, per_page_byte_cap=65536, total_byte_cap=100000)
    with pytest.raises(DiscoveryError, match="DISCOVERY_TOTAL_BYTES_EXCEEDED"):
        _run(scope=scoped, pages=[
            _page(next_token=TOKEN_A, total=2) | {"byte_count": 60000},
            _page(ordinal=1, request=TOKEN_A, total=2, nct_id="NCT00000002", received_at="2026-08-03T00:01:30Z") | {"byte_count": 60000},
        ])
    with pytest.raises(DiscoveryError, match="DISCOVERY_PAGE_SIZE_EXCEEDED"):
        _run(scope=scoped, pages=[_page() | {"records": [_page()["records"][0], _page(nct_id="NCT00000002")["records"][0]]}])


def test_coverage_requires_complete_runs_exact_union_and_day_overlap() -> None:
    first_scope = _scope("2026-08-01", "2026-08-02")
    second_scope = _scope("2026-08-02", "2026-08-03")
    first = _run(scope=first_scope, run_id="ctgov_discovery_run_first")
    second = _run(
        scope=second_scope,
        pages=[_page(updated="2026-08-02")],
        run_id="ctgov_discovery_run_second",
    )
    epoch = build_discovery_coverage_epoch(
        coverage_epoch_id="ctgov_discovery_coverage_overlap",
        runs=[second, first],
        declared_start_date="2026-08-01",
        declared_end_date="2026-08-03",
        transaction_from="2026-08-03T00:04:00Z",
    )
    assert epoch["coverage_state"] == "complete"
    assert epoch["gap_windows"] == []
    assert epoch["overlap_windows"] == [{"start_date": "2026-08-02", "end_date": "2026-08-02"}]
    assert [row["run_transaction_from"] for row in epoch["included_runs"]] == [
        "2026-08-03T00:03:00Z",
        "2026-08-03T00:03:00Z",
    ]

    partial = copy.deepcopy(first)
    partial["run_state"] = "quarantined"
    partial["reconciliation_state"] = "source_version_race"
    partial["quarantine_codes"] = ["DISCOVERY_SOURCE_VERSION_RACE"]
    _rehash(partial, "run_payload_sha256")
    with pytest.raises((DiscoveryError, ContractValidationError)):
        build_discovery_coverage_epoch(
            coverage_epoch_id="ctgov_discovery_coverage_partial",
            runs=[partial],
            declared_start_date="2026-08-01",
            declared_end_date="2026-08-02",
            transaction_from="2026-08-03T00:04:00Z",
        )

    gap_scope = _scope("2026-08-04", "2026-08-04")
    gap_run = _run(scope=gap_scope, pages=[_page(updated="2026-08-04")], run_id="ctgov_discovery_run_gap")
    with pytest.raises(DiscoveryError, match="DISCOVERY_PARTIAL_COVERAGE_REFUSED"):
        build_discovery_coverage_epoch(
            coverage_epoch_id="ctgov_discovery_coverage_gap",
            runs=[first, gap_run],
            declared_start_date="2026-08-01",
            declared_end_date="2026-08-04",
            transaction_from="2026-08-03T00:04:00Z",
        )

    with pytest.raises(ContractValidationError, match="discovery_coverage.knowledge_time"):
        build_discovery_coverage_epoch(
            coverage_epoch_id="ctgov_discovery_coverage_backdated",
            runs=[first],
            declared_start_date="2026-08-01",
            declared_end_date="2026-08-02",
            transaction_from="2026-08-03T00:02:59Z",
        )


def test_generic_validators_reject_rehashed_internal_forgeries() -> None:
    run = _run()
    forged_run = copy.deepcopy(run)
    forged_run["deduplicated_records"] = []
    _rehash(forged_run, "run_payload_sha256")
    with pytest.raises(ContractValidationError, match="discovery_run.dedupe"):
        validate_contract(forged_run, repo_root=ROOT)
    with pytest.raises(ContractValidationError, match="discovery_run.dedupe"):
        validate_discovery_run(forged_run)

    foreign_scope = _scope("2026-08-02", "2026-08-02")
    forged_scope_binding = copy.deepcopy(run)
    forged_scope_binding["scope"] = foreign_scope
    forged_scope_binding["scope_ref"] = foreign_scope["scope_id"]
    forged_scope_binding["scope_payload_sha256"] = foreign_scope["scope_payload_sha256"]
    _rehash(forged_scope_binding, "run_payload_sha256")
    with pytest.raises(ContractValidationError, match="discovery_run.scope_binding"):
        validate_contract(forged_scope_binding, repo_root=ROOT)
    with pytest.raises(ContractValidationError, match="discovery_run.scope_binding"):
        validate_discovery_run(forged_scope_binding)

    wide_scope = build_discovery_scope(
        selection_start_date="2026-08-01",
        selection_end_date="2026-08-02",
        page_size=1,
        page_cap=2,
        record_cap=2,
    )
    wide_run = _run(
        scope=wide_scope,
        run_id="ctgov_discovery_run_scope_capacity_forge",
        pages=[
            _page(next_token=TOKEN_A, total=2),
            _page(
                ordinal=1,
                request=TOKEN_A,
                total=2,
                nct_id="NCT00000002",
                content=HASH_C,
                updated="2026-08-02",
                received_at="2026-08-03T00:01:30Z",
            ),
        ],
    )
    narrow_scope = build_discovery_scope(
        selection_start_date="2026-08-01",
        selection_end_date="2026-08-02",
        page_size=1,
        page_cap=1,
        record_cap=1,
    )
    forged_scope_capacity = _bind_scope_and_rehash_run(wide_run, narrow_scope)
    with pytest.raises(ContractValidationError, match="discovery_run.scope_capacity"):
        validate_contract(forged_scope_capacity, repo_root=ROOT)
    with pytest.raises(ContractValidationError, match="discovery_run.scope_capacity"):
        validate_discovery_run(forged_scope_capacity)
    with pytest.raises(ContractValidationError, match="discovery_run.scope_capacity"):
        build_discovery_coverage_epoch(
            coverage_epoch_id="ctgov_discovery_coverage_scope_capacity_forge",
            runs=[forged_scope_capacity],
            declared_start_date="2026-08-01",
            declared_end_date="2026-08-02",
            transaction_from="2026-08-03T00:04:00Z",
        )

    valid_epoch = build_discovery_coverage_epoch(
        coverage_epoch_id="ctgov_discovery_coverage_valid_wide_scope",
        runs=[wide_run],
        declared_start_date="2026-08-01",
        declared_end_date="2026-08-02",
        transaction_from="2026-08-03T00:04:00Z",
    )
    with pytest.raises(ContractValidationError, match="discovery_run.scope_capacity"):
        validate_discovery_coverage_epoch(valid_epoch, runs=[forged_scope_capacity])

    first_scope = _scope("2026-08-01", "2026-08-02")
    second_scope = _scope("2026-08-02", "2026-08-03")
    first = _run(scope=first_scope, run_id="ctgov_discovery_run_forge_one")
    second = _run(scope=second_scope, pages=[_page(updated="2026-08-02")], run_id="ctgov_discovery_run_forge_two")
    epoch = build_discovery_coverage_epoch(
        coverage_epoch_id="ctgov_discovery_coverage_forge",
        runs=[first, second],
        declared_start_date="2026-08-01",
        declared_end_date="2026-08-03",
        transaction_from="2026-08-03T00:04:00Z",
    )
    forged_epoch = copy.deepcopy(epoch)
    forged_epoch["overlap_windows"] = []
    _rehash(forged_epoch, "coverage_payload_sha256")
    with pytest.raises(ContractValidationError, match="discovery_coverage.overlaps"):
        validate_discovery_coverage_epoch(forged_epoch, runs=[first, second])


def test_rehashed_runs_replay_every_observable_immutable_scope_limit() -> None:
    one_page = _run(run_id="ctgov_discovery_run_scope_limit_one_page")
    two_page_scope = build_discovery_scope(
        selection_start_date="2026-08-01",
        selection_end_date="2026-08-02",
        page_size=1,
        page_cap=2,
        record_cap=2,
    )
    two_pages = _run(
        scope=two_page_scope,
        run_id="ctgov_discovery_run_scope_limit_two_pages",
        pages=[
            _page(next_token=TOKEN_A, total=2),
            _page(
                ordinal=1,
                request=TOKEN_A,
                total=2,
                nct_id="NCT00000002",
                content=HASH_C,
                updated="2026-08-02",
                received_at="2026-08-03T00:01:30Z",
            ),
        ],
    )
    two_record_page = _page(total=2)
    two_record_page["records"].append(
        {
            "nct_id": "NCT00000002",
            "canonical_content_sha256": HASH_C,
            "last_update_posted_date": "2026-08-02",
        }
    )
    two_record_scope = build_discovery_scope(
        selection_start_date="2026-08-01",
        selection_end_date="2026-08-02",
        page_size=2,
        page_cap=1,
        record_cap=2,
    )
    two_records = _run(
        scope=two_record_scope,
        run_id="ctgov_discovery_run_scope_limit_two_records",
        pages=[two_record_page],
    )

    hostile_cases = (
        (
            "per-page bytes",
            one_page,
            build_discovery_scope(
                selection_start_date="2026-08-01",
                selection_end_date="2026-08-02",
                page_size=1,
                page_cap=1,
                record_cap=1,
                per_page_byte_cap=99,
                total_byte_cap=100,
            ),
        ),
        (
            "total bytes",
            two_pages,
            build_discovery_scope(
                selection_start_date="2026-08-01",
                selection_end_date="2026-08-02",
                page_size=1,
                page_cap=2,
                record_cap=2,
                per_page_byte_cap=100,
                total_byte_cap=199,
            ),
        ),
        (
            "page records",
            two_records,
            build_discovery_scope(
                selection_start_date="2026-08-01",
                selection_end_date="2026-08-02",
                page_size=2,
                page_record_cap=1,
                page_cap=1,
                record_cap=2,
            ),
        ),
        (
            "record bytes",
            one_page,
            build_discovery_scope(
                selection_start_date="2026-08-01",
                selection_end_date="2026-08-02",
                page_size=1,
                page_cap=1,
                record_cap=1,
                record_byte_cap=1,
            ),
        ),
        (
            "token bytes",
            two_pages,
            build_discovery_scope(
                selection_start_date="2026-08-01",
                selection_end_date="2026-08-02",
                page_size=1,
                page_cap=2,
                record_cap=2,
                token_byte_cap=63,
            ),
        ),
        (
            "string bytes",
            one_page,
            build_discovery_scope(
                selection_start_date="2026-08-01",
                selection_end_date="2026-08-02",
                page_size=1,
                page_cap=1,
                record_cap=1,
                string_byte_cap=10,
            ),
        ),
    )

    for _label, run, hostile_scope in hostile_cases:
        forged = _bind_scope_and_rehash_run(run, hostile_scope)
        with pytest.raises(ContractValidationError, match="discovery_run.scope_capacity"):
            validate_discovery_run(forged)


def test_dark_semantic_leak_scan() -> None:
    payload = "\n".join(
        path.read_text(encoding="utf-8").lower()
        for path in (
            ROOT / "engine" / "biocatalyst" / "discovery.py",
            ROOT / "contracts" / "biocatalyst" / "discovery_scope.v1.schema.json",
            ROOT / "contracts" / "biocatalyst" / "discovery_run.v1.schema.json",
            ROOT / "contracts" / "biocatalyst" / "discovery_coverage_epoch.v1.schema.json",
        )
    )
    for forbidden in ("ticker", "issuer", "signal", "prophet", "neural web", "rank_", "trade", "requests.", "fastapi"):
        assert forbidden not in payload


def test_dark_harness_is_absent_from_every_production_and_authority_entrypoint() -> None:
    exact_paths = (
        ROOT / "collectors" / "biocatalyst" / "__init__.py",
        ROOT / "scripts" / "biocatalyst_worker.py",
        ROOT / "app" / "biocatalyst.py",
        ROOT / "app" / "main.py",
        ROOT / "app" / "deploy" / "macro-biocatalyst.service",
        ROOT / "app" / "deploy" / "macro-biocatalyst.timer",
    )
    authority_roots = (ROOT / "engine" / "neuralweb", ROOT / "engine" / "prophet")
    paths = [path for path in exact_paths if path.is_file()]
    for authority_root in authority_roots:
        if authority_root.is_dir():
            paths.extend(sorted(authority_root.rglob("*.py")))
    production_text = "\n".join(path.read_text(encoding="utf-8") for path in paths)

    for forbidden in (
        "clinicaltrials_discovery",
        "ctgov_discovery_scope",
        "ctgov_discovery_run",
        "ctgov_discovery_coverage_epoch",
        "dark_discovery_harness",
    ):
        assert forbidden not in production_text
