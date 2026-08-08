"""Hermetic contract tests for the append-only SBIR.gov award observation rail.

Every test here pins one of the Wave 10 rail acceptance gates: source-native
identity, immutable receipts, an explicit collection universe with honest
omissions, four separate clocks, a first baseline that cannot synthesize
history, no semantic-similarity issuer joins, source failure that cannot erase
last-good evidence, and candidate impact that stays off until the family is
preregistered.
"""
from __future__ import annotations

import json
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import pandas as pd
import pytest
import requests
import yaml

import collectors.sbir_awards as sbir
from collectors.sbir_awards import (
    AUTHORITY,
    MAX_CELLS_PER_RUN,
    MAX_PAGES_PER_CELL,
    MAX_REQUESTS_PER_RUN,
    MIN_REQUEST_PACING_SECONDS,
    PII_SOURCE_FIELDS_NEVER_PERSISTED,
    PROBED_VALID_AGENCY_QUERY_CODES,
    PUBLISHED_RATE_LIMIT_REQUESTS,
    PUBLISHED_RATE_LIMIT_WINDOW_SECONDS,
    SBIR_AWARDS_URL,
    SBIR_COLLECTION_RECEIPTS_FILENAME,
    SBIR_COLLECTOR_HEARTBEAT_FILENAME,
    SBIR_INGEST_STATUS_FILENAME,
    SBIR_OBSERVATION_COLUMNS,
    SBIR_OBSERVATIONS_FILENAME,
    SBIR_PROJECTION_STATE_FILENAME,
    SbirAwardsAdapter,
    SbirAwardsCollector,
    SbirRateLimitError,
    append_sbir_award_observations,
    default_query_cells,
    heartbeat_frame,
    normalize_phase,
    normalize_sbir_award_observation,
    sbir_coverage_manifest,
    sbir_projection_generation,
    sbir_projection_generation_matches,
    write_heartbeat,
)
from engine.government_revenue.sbir_progression import (
    EXACT_ISSUER_JOIN_RULE,
    build_mapping_backlog,
    build_progression_evidence,
    build_sbir_progression_payload,
    is_valid_sbir_progression_payload,
    latest_visible_observations,
    progression_key,
    sbir_progression_content_id,
)

REPO = Path(__file__).parents[1]
OBSERVED = "2026-08-08T12:00:00+00:00"
OBSERVED_2 = "2026-08-09T12:00:00+00:00"
OBSERVED_3 = "2026-08-10T12:00:00+00:00"
UEI_MAPPED = "ABCDEFGHJK12"
UEI_UNMAPPED = "ZZZZZZZZZZ99"


# --------------------------------------------------------------------- helpers


class _Response:
    def __init__(self, payload, status_code: int = 200, *, text: str | None = None):
        self._payload = payload
        self.status_code = status_code
        self.text = text

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.HTTPError(f"HTTP {self.status_code}", response=self)

    def json(self):
        if self._payload is _NOT_JSON:
            raise ValueError("Expecting value: line 1 column 1 (char 0)")
        return self._payload


_NOT_JSON = object()


def _award(
    tracking: str,
    *,
    phase: str = "Phase I",
    uei: str = UEI_MAPPED,
    firm: str = "Acme Defense Labs, Inc.",
    award_date: str = "2024-03-01",
    amount: str = "150000",
    topic: str = "AF241-D001",
    agency: str = "DOW",
    branch: str = "USAF",
    program: str = "SBIR",
) -> dict:
    """One raw source row, including the PII fields the API really returns."""
    return {
        "firm": firm,
        "award_title": "Autonomous ISR payload maturation",
        "agency": agency,
        "branch": branch,
        "phase": phase,
        "program": program,
        "agency_tracking_number": tracking,
        "contract": f"FA8650-{tracking}",
        "proposal_award_date": award_date,
        "contract_end_date": "2025-03-01",
        "solicitation_number": "SBIR-24-1",
        "solicitation_year": "2024",
        "topic_code": topic,
        "award_year": "2024",
        "award_amount": amount,
        "duns": "123456789",
        "uei": uei,
        "hubzone_owned": "N",
        "number_employees": "42",
        "company_url": "https://example.invalid",
        "ri_name": "State University Research Institute",
        "state": "OH",
        "research_area_keywords": "autonomy, sensors",
        "award_link": f"https://www.sbir.gov/awards/{tracking}",
        # Fields that must never be persisted anywhere.
        "address1": "1 Secret Lane",
        "address2": "Suite 9",
        "city": "Dayton",
        "zip": "45402",
        "poc_name": "Dana Doe",
        "poc_title": "CEO",
        "poc_phone": "555-0100",
        "poc_email": "dana@example.invalid",
        "pi_name": "Ravi Patel",
        "pi_phone": "555-0101",
        "pi_email": "ravi@example.invalid",
        "ri_poc_name": "Sam Roe",
        "ri_poc_phone": "555-0102",
        "abstract": "A very long abstract " * 200,
    }


class _FixtureSession:
    """Serve declared offset pages from a per-cell row table."""

    def __init__(self, rows_by_cell: dict[tuple[str, str | None], list[dict]], *, fail_after: int | None = None):
        self.rows_by_cell = rows_by_cell
        self.fail_after = fail_after
        self.calls: list[dict] = []

    def get(self, url, **kwargs):
        parsed = urlparse(url)
        query = {key: value[0] for key, value in parse_qs(parsed.query).items()}
        self.calls.append(query)
        if self.fail_after is not None and len(self.calls) > self.fail_after:
            raise requests.ConnectionError("upstream unavailable token=do-not-persist")
        cell = (query["agency"], query.get("year"))
        rows = self.rows_by_cell.get(cell, [])
        start = int(query["start"])
        limit = int(query["rows"])
        return _Response(rows[start : start + limit])


def _collector(tmp_path: Path, session, **kwargs) -> SbirAwardsCollector:
    return SbirAwardsCollector(
        root=tmp_path,
        session=session,
        request_pacing_seconds=0,
        allow_rate_limit_override=True,
        **kwargs,
    )


CELL = ("DOW", "2024")
CELLS = [{"agency": "DOW", "year": "2024"}]


def _reviewed_graph() -> dict:
    """A minimal reviewed graph mapping exactly one UEI to one listed issuer."""
    return {
        "entities": [{"entity_id": "le:acme-sub", "canonical_name": "Acme Defense Labs, Inc."}],
        "companies": [{
            "company_id": "central:TST",
            "ticker": "TST",
            "verification_state": "confirmed",
            "known_at": "2025-01-01T00:00:00+00:00",
            "valid_from": "2020-01-01",
            "evidence_refs": ["evidence:company"],
        }],
        "identifiers": [{
            "identifier_id": "id-acme-uei",
            "entity_id": "le:acme-sub",
            "namespace": "sam_uei",
            "value": UEI_MAPPED,
            "verification_state": "confirmed",
            "known_at": "2025-01-01T00:00:00+00:00",
            "valid_from": "2020-01-01",
            "evidence_refs": ["evidence:uei"],
        }],
        "ownership_edges": [{
            "edge_id": "edge-acme",
            "child_entity_id": "le:acme-sub",
            "parent_company_id": "central:TST",
            "relationship": "wholly_owned",
            "confidence_state": "confirmed",
            "known_at": "2025-01-01T00:00:00+00:00",
            "valid_from": "2020-01-01",
            "evidence_refs": ["evidence:own"],
        }],
    }


def _receipt(observed_at: str = OBSERVED, *, response=None) -> dict:
    return SbirAwardsCollector._receipt(
        query={"agency": "DOW", "rows": 100, "start": 0, "year": "2024"},
        response_payload=response if response is not None else [],
        cell={"agency": "DOW", "year": "2024"},
        observed_at=observed_at,
        page=1,
        record_count=0,
        short_page=True,
    )


def _frame(rows: list[dict]) -> pd.DataFrame:
    return pd.DataFrame(rows, columns=SBIR_OBSERVATION_COLUMNS)


# ------------------------------------------------------- probed source contract


def test_probed_endpoint_and_query_shape_match_the_published_api():
    """The endpoint, params, and offset paging are the ones probed 2026-08-08."""
    session = _FixtureSession({CELL: [_award("T1")]})
    collector = _collector(Path("/tmp"), session, page_size=100)
    rows, receipt = collector.fetch_cell_page({"agency": "DOW", "year": "2024"}, 1, observed_at=OBSERVED)

    assert SBIR_AWARDS_URL == "https://api.www.sbir.gov/public/api/awards"
    assert len(rows) == 1
    assert session.calls == [{"agency": "DOW", "rows": "100", "start": "0", "year": "2024"}]
    # The API exposes no phase filter, so phase can never be a query constraint.
    assert "phase" not in session.calls[0]
    assert receipt["rail"] == "sbir_awards"
    assert receipt["endpoint"] == SBIR_AWARDS_URL
    assert receipt["offset"] == 0
    assert receipt["short_page"] is True
    assert "DOW" in PROBED_VALID_AGENCY_QUERY_CODES
    with pytest.raises(ValueError, match="not in the probed valid set"):
        collector.fetch_cell_page({"agency": "NOTANAGENCY"}, 1, observed_at=OBSERVED)


def test_offset_paging_walks_start_and_stops_on_a_short_page(tmp_path):
    rows = [_award(f"T{idx}") for idx in range(3)]
    session = _FixtureSession({CELL: rows})
    collector = _collector(tmp_path, session, page_size=2, max_pages_per_cell=2)
    status = collector.collect(observed_at=OBSERVED, cells=CELLS)

    assert [call["start"] for call in session.calls] == ["0", "2"]
    assert status["rows_seen"] == 3
    assert status["cells_source_exhausted"] == 1
    assert status["cells_truncated_by_page_cap"] == 0


@pytest.mark.parametrize(
    "response",
    [
        _Response(None, 403, text="You've exceeded the rate limit for API usage."),
        _Response({"Code": "TooManyRequestsError"}, 429),
    ],
)
def test_rate_limit_refusal_raises_and_never_reads_as_an_empty_page(tmp_path, response):
    """A refusal body is not award data.

    Both live refusal shapes were observed on 2026-08-08: a plain-text 403 from
    the application and a JSON 429 from the fronting API gateway.  Letting either
    fall through as "zero results" would silently retract every observation the
    ledger holds for that cell.
    """

    class Session:
        def get(self, url, **kwargs):
            return response

    collector = _collector(tmp_path, Session())
    with pytest.raises(SbirRateLimitError):
        collector.collect(observed_at=OBSERVED, cells=CELLS)
    assert not (tmp_path / "data" / "government_revenue" / SBIR_OBSERVATIONS_FILENAME).exists()


def test_non_json_and_non_array_bodies_fail_closed(tmp_path):
    class NotJson:
        def get(self, url, **kwargs):
            return _Response(_NOT_JSON, 200, text="<html>maintenance</html>")

    class NotArray:
        def get(self, url, **kwargs):
            return _Response({"results": []})

    with pytest.raises(ValueError, match="was not JSON"):
        _collector(tmp_path, NotJson()).collect(observed_at=OBSERVED, cells=CELLS)
    with pytest.raises(ValueError, match="must be a JSON array"):
        _collector(tmp_path, NotArray()).collect(observed_at=OBSERVED, cells=CELLS)


def test_request_pacing_and_budget_respect_the_published_rate_limit(tmp_path):
    """10 requests / 10 minutes is the published public ceiling.

    The default pacing must sit above one request per window slot, and the run's
    own hard request cap must stay under the published allowance, or a nightly
    run would earn the 403 that looks exactly like an unavailable source.
    """
    assert MIN_REQUEST_PACING_SECONDS >= (
        PUBLISHED_RATE_LIMIT_WINDOW_SECONDS / PUBLISHED_RATE_LIMIT_REQUESTS
    )
    assert MAX_REQUESTS_PER_RUN < PUBLISHED_RATE_LIMIT_REQUESTS
    assert MAX_CELLS_PER_RUN * MAX_PAGES_PER_CELL <= MAX_REQUESTS_PER_RUN

    with pytest.raises(ValueError, match="request pacing must be at least"):
        SbirAwardsCollector(root=tmp_path, request_pacing_seconds=1.0)
    # The override exists only for hermetic tests and is explicit at the call site.
    assert SbirAwardsCollector(
        root=tmp_path, request_pacing_seconds=0, allow_rate_limit_override=True
    ).request_pacing_seconds == 0


def test_run_request_budget_is_hard_capped(tmp_path):
    session = _FixtureSession({CELL: [_award(f"T{idx}") for idx in range(400)]})
    collector = _collector(tmp_path, session, page_size=1, max_pages_per_cell=2)
    collector._requests_this_run = MAX_REQUESTS_PER_RUN
    with pytest.raises(RuntimeError, match="request hard cap"):
        collector.fetch_cell_page({"agency": "DOW", "year": "2024"}, 1, observed_at=OBSERVED)


# ------------------------------------------------------------- exact identity


def test_identity_is_the_exact_agency_tracking_number_and_missing_keys_are_refused():
    row = normalize_sbir_award_observation(_award("AF24-1234"), _receipt(), OBSERVED)
    assert row["sbir_award_key"] == "AF24-1234"
    assert row["source_award_identity_kind"] == "agency_tracking_number"

    with pytest.raises(ValueError, match="agency_tracking_number"):
        normalize_sbir_award_observation(
            {**_award("X"), "agency_tracking_number": "  "}, _receipt(), OBSERVED
        )


def test_rows_without_exact_identity_are_counted_never_keyed_by_a_substitute(tmp_path):
    keyed = _award("T1")
    unkeyed = {**_award("T2"), "agency_tracking_number": None}
    session = _FixtureSession({CELL: [keyed, unkeyed]})
    status = _collector(tmp_path, session, page_size=100).collect(observed_at=OBSERVED, cells=CELLS)

    assert status["rows_seen"] == 2
    assert status["rows_accepted"] == 1
    assert status["rows_rejected_without_identity"] == 1
    ledger = pd.read_parquet(tmp_path / "data" / "government_revenue" / SBIR_OBSERVATIONS_FILENAME)
    assert list(ledger["sbir_award_key"]) == ["T1"]


def test_malformed_identifiers_are_dropped_rather_than_half_stored():
    # The official UEI alphabet omits I and O; a value that could never join the
    # reviewed graph must not be stored as though it were coverage.
    row = normalize_sbir_award_observation(
        {**_award("T1"), "uei": "ABCDEFGHIJKL", "duns": "12-345"}, _receipt(), OBSERVED
    )
    assert row["uei"] is None
    assert row["duns"] is None
    good = normalize_sbir_award_observation(
        {**_award("T2"), "uei": "abcdefghjk12", "duns": "123-456-789"}, _receipt(), OBSERVED
    )
    assert good["uei"] == UEI_MAPPED
    assert good["duns"] == "123456789"


def test_phase_spellings_normalize_and_unknown_phases_never_become_phase_ii():
    assert normalize_phase("Phase I") == normalize_phase("1") == normalize_phase("phase-i") == "I"
    assert normalize_phase("Phase II") == normalize_phase("2") == "II"
    # A Phase III or a future label must not be silently read as Phase II.
    assert normalize_phase("Phase III") is None
    assert normalize_phase("III") is None
    row = normalize_sbir_award_observation({**_award("T1"), "phase": "Phase III"}, _receipt(), OBSERVED)
    assert row["phase"] is None
    assert row["phase_source_value"] == "Phase III"


# -------------------------------------------------------------------- privacy


def test_pii_source_fields_are_never_persisted_in_a_row_or_a_receipt():
    raw = _award("T1")
    row = normalize_sbir_award_observation(raw, _receipt(), OBSERVED)

    for field in PII_SOURCE_FIELDS_NEVER_PERSISTED:
        assert field in raw, "the fixture must carry the field the source really returns"
        assert field not in row
    serialized = json.dumps(row)
    for value in ("dana@example.invalid", "Dana Doe", "Ravi Patel", "555-0100", "1 Secret Lane", "45402"):
        assert value not in serialized
    # The abstract is deliberately not persisted at all.
    assert "abstract" not in row
    assert sbir._contains_forbidden_receipt_key({"poc_email": "x"}) is True
    assert sbir._contains_forbidden_receipt_key({"nested": [{"pi_phone": "x"}]}) is True
    assert sbir._contains_forbidden_receipt_key(_receipt()) is False


def test_the_canonical_column_list_is_the_defended_privacy_seam(monkeypatch):
    """The row is filtered to the canonical columns, so that list is the gate.

    Adding a contact-shaped field to the intermediate row dict is harmless — it
    is dropped by the projection onto ``SBIR_OBSERVATION_COLUMNS``.  The real
    regression is a PII-named column joining that list, so pin it there: the
    census below fails on such an addition, and the in-normalizer guard refuses
    to emit the row at all rather than trusting the census to have caught it.
    """
    assert [column for column in SBIR_OBSERVATION_COLUMNS if sbir._PII_KEY.search(column)] == []

    monkeypatch.setattr(
        sbir, "SBIR_OBSERVATION_COLUMNS", [*SBIR_OBSERVATION_COLUMNS, "poc_email"]
    )
    with pytest.raises(ValueError, match="would persist PII columns"):
        normalize_sbir_award_observation(_award("T1"), _receipt(), OBSERVED)


def test_receipts_are_canonical_hash_only_and_binding_is_checked(tmp_path):
    response = [_award("T1")]
    first = _receipt(response=response)
    second = _receipt(response=list(response))
    assert first["request_sha256"] == second["request_sha256"]
    assert first["response_sha256"] == second["response_sha256"]
    assert "response_body" not in first and "request_body" not in first

    with pytest.raises(ValueError, match="invalid source page receipt binding"):
        normalize_sbir_award_observation(_award("T1"), {**first, "rail": "other"}, OBSERVED)
    with pytest.raises(ValueError, match="missing its source page receipt"):
        normalize_sbir_award_observation(_award("T1"), None, OBSERVED)


# --------------------------------------------------------------------- clocks


def test_the_four_clocks_stay_separate_and_knowledge_is_observation_bound():
    """Source, effective, observed, and known-at are distinct fields.

    SBIR.gov publishes no record-publication timestamp, so knowledge is bound to
    our own retrieval and is never backdated to the award date — otherwise a
    first baseline would claim to have known a 2024 award in 2024.
    """
    row = normalize_sbir_award_observation(
        _award("T1", award_date="2024-03-01"), _receipt(), OBSERVED
    )
    assert row["source_at"] == "2024-03-01"
    assert row["source_at_field"] == "proposal_award_date"
    assert row["effective_at"] == "2024-03-01"
    assert row["observed_at"] == OBSERVED
    assert row["known_at"] == OBSERVED
    assert row["first_seen_at"] == OBSERVED
    assert row["source_at"] < row["known_at"]
    assert row["source_fiscal_year"] == "2024"
    assert row["contract_end_date"] == "2025-03-01"
    # An unparseable source date stays null instead of being guessed into order.
    ambiguous = normalize_sbir_award_observation(
        {**_award("T2"), "proposal_award_date": "03/01/2024"}, _receipt(), OBSERVED
    )
    assert ambiguous["source_at"] is None
    assert ambiguous["effective_at"] is None
    assert ambiguous["known_at"] == OBSERVED


# ---------------------------------------------------------------- append-only


def test_rerun_appends_and_never_rewrites_or_deletes_accrued_history(tmp_path):
    """G-append-only. A re-run may add observations; it may never edit history."""
    data_dir = tmp_path / "data" / "government_revenue"
    ledger_path = data_dir / SBIR_OBSERVATIONS_FILENAME

    first = _FixtureSession({CELL: [_award("T1", amount="150000"), _award("T2", phase="Phase II")]})
    _collector(tmp_path, first).collect(observed_at=OBSERVED, cells=CELLS)
    run_one = pd.read_parquet(ledger_path)
    assert len(run_one) == 2

    # An identical re-run adds nothing: same semantic state is not a new version.
    _collector(tmp_path, _FixtureSession({CELL: [_award("T1", amount="150000"), _award("T2", phase="Phase II")]})).collect(
        observed_at=OBSERVED_2, cells=CELLS
    )
    assert len(pd.read_parquet(ledger_path)) == 2

    # A changed cell appends a version and preserves every prior row verbatim.
    changed = _FixtureSession({CELL: [_award("T1", amount="900000"), _award("T2", phase="Phase II")]})
    status = _collector(tmp_path, changed).collect(observed_at=OBSERVED_3, cells=CELLS)
    run_three = pd.read_parquet(ledger_path)
    assert len(run_three) == 3
    assert status["observations_new_this_run"] == 1
    pd.testing.assert_frame_equal(run_three.iloc[:2].reset_index(drop=True), run_one)
    versions = run_three[run_three["sbir_award_key"] == "T1"]
    assert list(versions["award_amount"]) == [150000.0, 900000.0]
    assert list(versions["known_at"]) == [OBSERVED, OBSERVED_3]
    # first_seen_at is immutable across versions.
    assert set(versions["first_seen_at"]) == {OBSERVED}


def test_a_reverted_state_is_retained_as_its_own_version():
    base = _award("T1", amount="100000")
    high = _award("T1", amount="200000")
    frames = _frame([])
    for observed, raw in ((OBSERVED, base), (OBSERVED_2, high), (OBSERVED_3, base)):
        incoming = _frame([normalize_sbir_award_observation(raw, _receipt(observed), observed)])
        frames = append_sbir_award_observations(frames, incoming)
    # A-B-A is three versions: collapsing it would delete the excursion.
    assert list(frames["award_amount"]) == [100000.0, 200000.0, 100000.0]
    assert list(frames["known_at"]) == [OBSERVED, OBSERVED_2, OBSERVED_3]


def test_a_non_increasing_evidence_clock_is_refused():
    row_a = normalize_sbir_award_observation(_award("T1", amount="1"), _receipt(OBSERVED_2), OBSERVED_2)
    row_b = normalize_sbir_award_observation(_award("T1", amount="2"), _receipt(OBSERVED), OBSERVED)
    existing = append_sbir_award_observations(_frame([]), _frame([row_a]))
    with pytest.raises(ValueError, match="strictly increasing evidence clock"):
        append_sbir_award_observations(existing, _frame([row_b]))


def test_a_merge_that_would_shrink_the_ledger_is_refused(tmp_path, monkeypatch):
    session = _FixtureSession({CELL: [_award("T1")]})
    collector = _collector(tmp_path, session)
    collector.collect(observed_at=OBSERVED, cells=CELLS)

    monkeypatch.setattr(
        sbir, "append_sbir_award_observations", lambda existing, incoming: _frame([])
    )
    with pytest.raises(RuntimeError, match="would drop accrued observations"):
        _collector(tmp_path, _FixtureSession({CELL: [_award("T1")]})).collect(
            observed_at=OBSERVED_2, cells=CELLS
        )


# ------------------------------------------------------------ bounded sample


def test_bounded_sample_manifest_states_its_omissions_honestly(tmp_path):
    """A fully retrieved page cap is a complete bounded sample, not completion.

    The source publishes no pagination metadata and no total, so exhaustion is
    provable only by a short page.  Any other claim would be invented.
    """
    rows = [_award(f"T{idx}") for idx in range(4)]
    session = _FixtureSession({CELL: rows})
    status = _collector(tmp_path, session, page_size=2, max_pages_per_cell=2).collect(
        observed_at=OBSERVED, cells=CELLS
    )

    completeness = status["completeness"]
    assert completeness["bounded_sample_complete"] is True
    assert completeness["source_exhausted"] is False
    assert completeness["truncated_by_page_cap"] is True
    assert completeness["full_sbir_corpus"] is False
    assert completeness["pagination_metadata_available"] is False
    assert "bounded sample, not corpus completion" in completeness["claim"]

    manifest = status["coverage_manifest"]
    assert manifest["paging"]["source_exhaustion_signal"] == "short_page_only"
    assert manifest["paging"]["total_record_count_available"] is False
    assert manifest["paging"]["sort_is_configurable"] is False
    assert manifest["omissions"]["full_sbir_corpus"] is False
    assert manifest["omissions"]["abstract_persisted"] is False
    assert manifest["omissions"]["pii_source_fields_never_persisted"] == list(
        PII_SOURCE_FIELDS_NEVER_PERSISTED
    )
    assert manifest["clocks"]["source_publication_clock_available"] is False
    assert manifest["identity"]["name_association_is_attribution"] is False
    assert manifest["safety_caps"]["published_rate_limit_requests"] == PUBLISHED_RATE_LIMIT_REQUESTS


def test_the_coverage_manifest_is_a_configuration_not_a_run_log():
    """Two runs of the same contract share one manifest ID.

    A manifest that embedded today's clock would force a rebaseline every night
    even when the declared universe never changed.
    """
    kwargs = dict(
        page_size=100,
        max_pages_per_cell=2,
        max_cells_per_run=4,
        max_rows_per_run=800,
        request_pacing_seconds=63.0,
    )
    first = sbir_coverage_manifest(CELLS, **kwargs)
    second = sbir_coverage_manifest(list(CELLS), **kwargs)
    assert first == second
    assert sbir.sbir_coverage_manifest_id(first) == sbir.sbir_coverage_manifest_id(second)
    assert first != sbir_coverage_manifest([{"agency": "NSF", "year": "2024"}], **kwargs)


def test_declared_universe_is_small_enough_to_actually_collect():
    cells = default_query_cells(as_of="2026-11-02T00:00:00+00:00")
    assert len(cells) <= MAX_CELLS_PER_RUN
    # Federal fiscal year rolls on 1 October, so November 2026 is FY2027.
    assert [cell["year"] for cell in cells] == ["2027", "2026"]
    assert all(cell["agency"] in PROBED_VALID_AGENCY_QUERY_CODES for cell in cells)


# ------------------------------------------------------------- atomic persist


def test_a_staged_verification_failure_leaves_every_live_artifact_last_good(tmp_path, monkeypatch):
    """G-atomic. Nothing commits until the staged ledger has round-tripped."""
    data_dir = tmp_path / "data" / "government_revenue"
    _collector(tmp_path, _FixtureSession({CELL: [_award("T1")]})).collect(
        observed_at=OBSERVED, cells=CELLS
    )
    protected = [
        data_dir / SBIR_OBSERVATIONS_FILENAME,
        data_dir / SBIR_PROJECTION_STATE_FILENAME,
        data_dir / SBIR_INGEST_STATUS_FILENAME,
    ]
    before = {path: path.read_bytes() for path in protected}

    monkeypatch.setattr(
        sbir,
        "_verify_staged_parquet",
        lambda tmp, frame: (_ for _ in ()).throw(RuntimeError("injected round-trip failure")),
    )
    with pytest.raises(RuntimeError, match="injected round-trip failure"):
        _collector(tmp_path, _FixtureSession({CELL: [_award("T1", amount="7")]})).collect(
            observed_at=OBSERVED_2, cells=CELLS
        )
    assert {path: path.read_bytes() for path in protected} == before
    assert not list(data_dir.glob(".*tmp"))


def test_a_state_write_failure_commits_no_half_bundle(tmp_path, monkeypatch):
    data_dir = tmp_path / "data" / "government_revenue"
    _collector(tmp_path, _FixtureSession({CELL: [_award("T1")]})).collect(
        observed_at=OBSERVED, cells=CELLS
    )
    protected = [
        data_dir / SBIR_OBSERVATIONS_FILENAME,
        data_dir / SBIR_PROJECTION_STATE_FILENAME,
        data_dir / SBIR_INGEST_STATUS_FILENAME,
    ]
    before = {path: path.read_bytes() for path in protected}

    real_stage_json = sbir._stage_json

    def fail_state(payload, path):
        if path.name == SBIR_PROJECTION_STATE_FILENAME:
            raise OSError("injected activation failure")
        return real_stage_json(payload, path)

    monkeypatch.setattr(sbir, "_stage_json", fail_state)
    with pytest.raises(OSError, match="injected activation failure"):
        _collector(tmp_path, _FixtureSession({CELL: [_award("T1", amount="7")]})).collect(
            observed_at=OBSERVED_2, cells=CELLS
        )
    assert {path: path.read_bytes() for path in protected} == before


def test_source_failure_preserves_last_good_and_still_keeps_successful_receipts(tmp_path):
    """G-last-good. A source outage cannot erase evidence we already hold."""
    data_dir = tmp_path / "data" / "government_revenue"
    rows = [_award(f"T{idx}") for idx in range(4)]
    _collector(tmp_path, _FixtureSession({CELL: rows}), page_size=2).collect(
        observed_at=OBSERVED, cells=CELLS
    )
    protected = [
        data_dir / SBIR_OBSERVATIONS_FILENAME,
        data_dir / SBIR_PROJECTION_STATE_FILENAME,
        data_dir / SBIR_INGEST_STATUS_FILENAME,
    ]
    before = {path: path.read_bytes() for path in protected}
    receipts_before = (data_dir / SBIR_COLLECTION_RECEIPTS_FILENAME).read_text().count("\n")

    failing = _FixtureSession({CELL: rows}, fail_after=1)
    with pytest.raises(requests.ConnectionError) as excinfo:
        _collector(tmp_path, failing, page_size=2, max_pages_per_cell=2).collect(
            observed_at=OBSERVED_2, cells=CELLS
        )
    assert {path: path.read_bytes() for path in protected} == before
    # The one page that did succeed remains immutable evidence.
    assert (data_dir / SBIR_COLLECTION_RECEIPTS_FILENAME).read_text().count("\n") > receipts_before
    assert "do-not-persist" in str(excinfo.value)
    assert "do-not-persist" not in (data_dir / SBIR_COLLECTION_RECEIPTS_FILENAME).read_text()


def test_an_unreadable_accrued_ledger_is_never_overwritten(tmp_path):
    data_dir = tmp_path / "data" / "government_revenue"
    data_dir.mkdir(parents=True)
    corrupt = data_dir / SBIR_OBSERVATIONS_FILENAME
    corrupt.write_bytes(b"not a parquet file")
    with pytest.raises(RuntimeError, match="refusing to overwrite unreadable"):
        _collector(tmp_path, _FixtureSession({CELL: [_award("T1")]})).collect(
            observed_at=OBSERVED, cells=CELLS
        )
    assert corrupt.read_bytes() == b"not a parquet file"


def test_a_torn_generation_is_refused_rather_than_rebound(tmp_path):
    """A live state whose binding no longer describes the ledger fails closed."""
    data_dir = tmp_path / "data" / "government_revenue"
    _collector(tmp_path, _FixtureSession({CELL: [_award("T1")]})).collect(
        observed_at=OBSERVED, cells=CELLS
    )
    ledger_path = data_dir / SBIR_OBSERVATIONS_FILENAME
    tampered = pd.read_parquet(ledger_path)
    tampered.loc[0, "award_amount"] = 1.0
    tampered.to_parquet(ledger_path, index=False)

    with pytest.raises(RuntimeError, match="does not match its observation ledger"):
        _collector(tmp_path, _FixtureSession({CELL: [_award("T1")]})).collect(
            observed_at=OBSERVED_2, cells=CELLS
        )


def test_generation_binding_is_order_independent_and_tamper_evident(tmp_path):
    rows = [
        normalize_sbir_award_observation(_award(f"T{idx}"), _receipt(), OBSERVED)
        for idx in range(3)
    ]
    forward = sbir_projection_generation(_frame(rows))
    reversed_generation = sbir_projection_generation(_frame(list(reversed(rows))))
    assert forward == reversed_generation

    state = {
        "schema_version": sbir.SCHEMA_VERSION,
        "contract": sbir.SBIR_PROJECTION_STATE_SCHEMA,
        "activation_state": "live",
        "projection_eligible": True,
        **forward,
    }
    assert sbir_projection_generation_matches(state, _frame(rows)) is True
    assert sbir_projection_generation_matches(state, _frame(rows[:2])) is False
    assert sbir_projection_generation_matches({**state, "activation_state": "draft"}, _frame(rows)) is False


# ----------------------------------------------------------- pandas-3 legacy


def test_a_legacy_ledger_missing_a_column_can_still_be_appended_to(tmp_path):
    """Pandas 3 refuses a string write into an all-NaN float64 column.

    A ledger written before a canonical column existed reindexes that column to
    float64; without the object coercion the very next append raises instead of
    accruing.
    """
    legacy_columns = [c for c in SBIR_OBSERVATION_COLUMNS if c != "research_institution"]
    legacy = normalize_sbir_award_observation(_award("T0"), _receipt(), OBSERVED)
    legacy_frame = pd.DataFrame([{k: legacy[k] for k in legacy_columns}], columns=legacy_columns)
    data_dir = tmp_path / "data" / "government_revenue"
    data_dir.mkdir(parents=True)
    legacy_frame.to_parquet(data_dir / SBIR_OBSERVATIONS_FILENAME, index=False)

    merged = append_sbir_award_observations(
        sbir._read_existing(data_dir / SBIR_OBSERVATIONS_FILENAME),
        _frame([normalize_sbir_award_observation(_award("T1"), _receipt(), OBSERVED)]),
    )
    assert len(merged) == 2
    assert merged.loc[0, "research_institution"] is None
    assert merged.loc[1, "research_institution"] == "State University Research Institute"


# ------------------------------------------------------------ progression rail


def _bundle(tmp_path: Path, rows: list[dict], *, observed: str = OBSERVED) -> dict:
    session = _FixtureSession({CELL: rows})
    return _collector(tmp_path, session, page_size=100).collect(observed_at=observed, cells=CELLS)


def _phase_pair(**kwargs) -> list[dict]:
    return [
        _award("PH1-001", phase="Phase I", award_date="2023-04-01", amount="180000", **kwargs),
        _award("PH2-001", phase="Phase II", award_date="2024-09-15", amount="1200000", **kwargs),
    ]


def test_progression_is_labeled_evidence_and_never_production_conversion(tmp_path):
    """G-progression. Phase movement is evidence; conversion needs a chain."""
    _bundle(tmp_path, _phase_pair())
    payload = build_sbir_progression_payload(root=tmp_path, as_of=OBSERVED)

    assert is_valid_sbir_progression_payload(payload)
    assert len(payload["progression_evidence"]) == 1
    row = payload["progression_evidence"][0]
    assert row["evidence_kind"] == "phase_i_to_phase_ii_observed"
    assert row["is_production_conversion"] is False
    assert row["production_award_chain"] == "absent"
    assert row["source_publishes_phase_lineage"] is False
    assert row["phase_i"]["sbir_award_key"] == "PH1-001"
    assert row["phase_ii"]["sbir_award_key"] == "PH2-001"
    assert row["days_between_award_starts"] == 533
    serialized = json.dumps(payload).lower()
    for forbidden in ("production conversion is", "converted to production", "revenue recognized"):
        assert forbidden not in serialized
    assert any("never production conversion" in item for item in payload["limitations"])


def test_a_phase_ii_that_starts_before_the_phase_i_is_not_progression(tmp_path):
    rows = [
        _award("PH1-001", phase="Phase I", award_date="2024-09-15"),
        _award("PH2-001", phase="Phase II", award_date="2023-04-01"),
    ]
    _bundle(tmp_path, rows)
    payload = build_sbir_progression_payload(root=tmp_path, as_of=OBSERVED)
    assert payload["progression_evidence"] == []
    assert payload["phase_observations"] == {"phase_i": 1, "phase_ii": 1, "unrecognized_phase": 0}


def test_progression_key_requires_an_exact_identifier_not_a_firm_name():
    keyed = progression_key({"uei": UEI_MAPPED, "agency": "DOW", "program": "SBIR", "topic_code": "T1"})
    assert keyed is not None
    assert keyed[1] == "uei_agency_program_topic"
    # No UEI means no exact identity to group on; a firm name is not a key.
    assert progression_key({"firm": "Acme Defense Labs, Inc.", "agency": "DOW", "program": "SBIR"}) is None
    coarse = progression_key({"uei": UEI_MAPPED, "agency": "DOW", "program": "SBIR"})
    assert coarse is not None and coarse[1] == "uei_agency_program"
    # A coarser grouping must never share the sharper grouping's key.
    assert coarse[0] != keyed[0]


def test_exact_uei_join_only_a_matching_name_with_a_different_uei_is_not_attribution(tmp_path):
    """G-identity. The join reads the UEI and nothing else.

    Both firms carry the byte-identical reviewed name; only one carries the
    reviewed UEI.  A name-shaped join would attribute both.
    """
    rows = [
        *_phase_pair(uei=UEI_MAPPED, firm="Acme Defense Labs, Inc."),
        _award("PH1-002", phase="Phase I", award_date="2023-04-01", uei=UEI_UNMAPPED,
               firm="Acme Defense Labs, Inc.", topic="AF241-D002"),
        _award("PH2-002", phase="Phase II", award_date="2024-09-15", uei=UEI_UNMAPPED,
               firm="Acme Defense Labs, Inc.", topic="AF241-D002"),
    ]
    _bundle(tmp_path, rows)
    observations = latest_visible_observations(
        pd.read_parquet(tmp_path / "data" / "government_revenue" / SBIR_OBSERVATIONS_FILENAME),
        as_of=OBSERVED,
    )
    evidence = build_progression_evidence(observations, _reviewed_graph(), as_of=OBSERVED)
    assert len(evidence) == 2

    by_uei = {row["key_fields"]["uei"]: row for row in evidence}
    mapped = by_uei[UEI_MAPPED]["issuer_link"]
    unmapped = by_uei[UEI_UNMAPPED]["issuer_link"]

    assert mapped["issuer_attribution"] == "exact_identifier"
    assert mapped["issuer_join_rule"] == EXACT_ISSUER_JOIN_RULE
    assert mapped["ticker"] == "TST"

    assert unmapped["issuer_attribution"] == "not_asserted"
    assert unmapped["issuer_join_rule"] == "none"
    assert unmapped["ticker"] is None
    assert "exact_identifier_not_mapped" in unmapped["resolution_reason_codes"]
    # Both rows carry the same firm name, so the name cannot be what separated them.
    assert by_uei[UEI_MAPPED]["firm_name_context"] == by_uei[UEI_UNMAPPED]["firm_name_context"]


def test_a_name_only_row_appears_as_mapping_backlog_never_as_attribution(tmp_path):
    _bundle(tmp_path, [_award("PH1-003", uei="BADUEI")])
    payload = build_sbir_progression_payload(root=tmp_path, as_of=OBSERVED)

    assert payload["exact_identity"]["exact_linked"] == 0
    assert payload["exact_identity"]["name_association_is_attribution"] is False
    assert len(payload["mapping_backlog"]) == 1
    backlog = payload["mapping_backlog"][0]
    assert backlog["issuer_attribution"] == "not_asserted"
    assert backlog["mapping_state"] == "mapping_needed"
    assert backlog["uei"] is None
    assert backlog["company_name"] == "Acme Defense Labs, Inc."
    assert is_valid_sbir_progression_payload(payload)


def test_the_projection_is_point_in_time_and_a_later_version_cannot_leak_backwards(tmp_path):
    _bundle(tmp_path, [_award("T1", amount="100000")])
    _bundle(tmp_path, [_award("T1", amount="900000")], observed=OBSERVED_2)
    ledger = pd.read_parquet(tmp_path / "data" / "government_revenue" / SBIR_OBSERVATIONS_FILENAME)
    assert len(ledger) == 2

    early = latest_visible_observations(ledger, as_of=OBSERVED)
    late = latest_visible_observations(ledger, as_of=OBSERVED_2)
    assert list(early["award_amount"]) == [100000.0]
    assert list(late["award_amount"]) == [900000.0]


def test_first_baseline_is_zero_history_and_emits_no_forward_events(tmp_path):
    """G-baseline. One knowledge generation is not a graded forward record."""
    status = _bundle(tmp_path, _phase_pair())
    assert status["first_baseline"] is True
    assert status["history_synthesized"] is False

    payload = build_sbir_progression_payload(root=tmp_path, as_of=OBSERVED)
    assert payload["baseline"]["state"] == "first_baseline"
    assert payload["baseline"]["history_synthesized"] is False
    assert payload["baseline"]["emits_forward_events"] is False
    assert payload["forward_events"] == []
    assert payload["forward_events_emitted"] == 0
    # No evidence row may claim to have been knowable before the first observation.
    assert payload["first_observed_at"] == OBSERVED
    assert all(row["known_at"] >= OBSERVED for row in payload["progression_evidence"])
    assert "never backfilled as prior knowledge" in payload["baseline"]["disclosure"]

    _bundle(tmp_path, [_award("PH1-001", phase="Phase I", award_date="2023-04-01", amount="7")], observed=OBSERVED_2)
    accrued = build_sbir_progression_payload(root=tmp_path, as_of=OBSERVED_2)
    assert accrued["baseline"]["state"] == "accrued"
    assert accrued["forward_events"] == []


def test_candidate_impact_is_off_and_mirrors_the_shipped_candidate_queue_authority(tmp_path):
    """G-candidates. No candidate family exists until it is preregistered."""
    live_authority = json.loads(
        (REPO / "data" / "government_revenue" / "candidate_queue.json").read_text()
    )["authority"]
    assert AUTHORITY == live_authority

    status = _bundle(tmp_path, _phase_pair())
    assert status["authority"] == live_authority
    payload = build_sbir_progression_payload(root=tmp_path, as_of=OBSERVED)
    assert payload["authority"] == live_authority
    assert payload["candidate_impact"] == {
        "emits_candidates": False,
        "candidate_family_preregistered": False,
        "authority": live_authority,
    }
    # The rail writes nothing into the candidate lane.
    assert "candidates" not in payload
    assert not (tmp_path / "data" / "government_revenue" / "candidate_queue.json").exists()


def test_an_absent_bundle_is_a_designed_unavailable_state_not_a_synthesized_empty(tmp_path):
    payload = build_sbir_progression_payload(root=tmp_path, as_of=OBSERVED)
    assert payload["availability"] == {
        "state": "unavailable",
        "reason": "sbir_observation_bundle_absent",
    }
    assert payload["baseline"]["state"] == "no_bundle"
    assert is_valid_sbir_progression_payload(payload)
    assert "not an absence of awards" in payload["baseline"]["disclosure"]


def test_a_partial_bundle_is_a_hard_failure(tmp_path):
    data_dir = tmp_path / "data" / "government_revenue"
    data_dir.mkdir(parents=True)
    (data_dir / SBIR_INGEST_STATUS_FILENAME).write_text("{}")
    with pytest.raises(ValueError, match="bundle is partial"):
        build_sbir_progression_payload(root=tmp_path, as_of=OBSERVED)


def test_a_tampered_ledger_is_not_projected(tmp_path):
    _bundle(tmp_path, _phase_pair())
    ledger_path = tmp_path / "data" / "government_revenue" / SBIR_OBSERVATIONS_FILENAME
    tampered = pd.read_parquet(ledger_path)
    tampered.loc[0, "award_amount"] = 42.0
    tampered.to_parquet(ledger_path, index=False)
    with pytest.raises(ValueError, match="refusing to project a torn generation"):
        build_sbir_progression_payload(root=tmp_path, as_of=OBSERVED)


def test_content_id_is_deterministic_and_tamper_evident(tmp_path):
    _bundle(tmp_path, _phase_pair())
    payload = build_sbir_progression_payload(root=tmp_path, as_of=OBSERVED)
    assert payload["content_id"] == sbir_progression_content_id(payload)
    assert is_valid_sbir_progression_payload({**payload, "content_id": "grsp1-tampered"}) is False
    assert is_valid_sbir_progression_payload(
        {**payload, "forward_events_emitted": 1}
    ) is False


def test_mapping_backlog_excludes_exactly_linked_firms():
    rows = [
        normalize_sbir_award_observation(_award("T1", uei=UEI_MAPPED), _receipt(), OBSERVED),
        normalize_sbir_award_observation(_award("T2", uei=UEI_UNMAPPED), _receipt(), OBSERVED),
    ]
    backlog = build_mapping_backlog(_frame(rows), _reviewed_graph(), as_of=OBSERVED)
    assert [row["uei"] for row in backlog] == [UEI_UNMAPPED]


# ------------------------------------------------------------ runner wiring


def test_adapter_returns_a_dated_heartbeat_only_after_success(monkeypatch, tmp_path):
    ok = {
        "status": "ok",
        "observed_at": OBSERVED,
        "cells_declared": 1,
        "cells_collected": 1,
        "cells_source_exhausted": 1,
        "cells_truncated_by_page_cap": 0,
        "requests_this_run": 1,
        "rows_seen": 2,
        "rows_accepted": 2,
        "rows_rejected_without_identity": 0,
        "observations_total": 2,
        "errors": [],
    }
    monkeypatch.setattr(SbirAwardsCollector, "collect", lambda self: ok)
    frames = SbirAwardsAdapter().fetch()
    assert list(frames) == ["sbir_collector_heartbeat"]
    assert frames["sbir_collector_heartbeat"].index[0] == pd.Timestamp("2026-08-08")

    path = write_heartbeat(ok, tmp_path)
    assert path.name == SBIR_COLLECTOR_HEARTBEAT_FILENAME
    assert path.exists()
    with pytest.raises(ValueError, match="successful"):
        heartbeat_frame({**ok, "status": "failed"})


def test_collect_registration_and_slow_lane():
    from scripts.collect import _SLOW, all_adapters

    assert "sbir_awards" in _SLOW
    assert all_adapters()["sbir_awards"] is SbirAwardsAdapter


def test_dag_declares_every_path_the_collector_actually_touches():
    """The nightly contract must name the real artifacts, not a subset."""
    dag = yaml.safe_load((REPO / "config" / "dag.yml").read_text())
    steps = [
        step
        for step in dag["modules"]
        if step.get("module") == "collectors.sbir_awards"
    ]
    assert len(steps) == 1
    step = steps[0]
    written = {
        SBIR_OBSERVATIONS_FILENAME,
        SBIR_COLLECTION_RECEIPTS_FILENAME,
        SBIR_PROJECTION_STATE_FILENAME,
        SBIR_INGEST_STATUS_FILENAME,
        SBIR_COLLECTOR_HEARTBEAT_FILENAME,
    }
    declared_writes = {Path(path).name for path in step["writes"]}
    declared_reads = {Path(path).name for path in step["reads"]}
    assert written <= declared_writes
    # Every accrued artifact the collector reads back before appending must be
    # declared as a read, or the DAG would claim this step invents its history.
    assert written - {SBIR_COLLECTOR_HEARTBEAT_FILENAME} <= declared_reads
    assert step["impure"] is True
    assert step["needs_secrets"] is False
