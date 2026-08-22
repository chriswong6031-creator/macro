"""Contract tests for the paid Catalyst Radar API (BioCatalyst P1-1).

``GET /api/biocatalyst/v1/catalyst-radar`` is the serving plane over the
frozen, pure projection in ``engine.biocatalyst.catalyst_events``.  These
tests exercise the route's own responsibilities only: authentication,
entitlement, query validation, generation-anchored pagination, the
sponsor-map serve-time hazard (must degrade, never 503), and the public
safety boundary (no score/rank vocabulary, no private path/receipt/object-key
leakage).  The projection's own semantics -- timing classification,
precision honesty, evidence shape -- are frozen and unit-tested in
``tests/test_biocatalyst_catalyst_radar.py``; this file does not re-test them.

Harness modeled on ``tests/test_biocatalyst_api.py``'s ``promoted_config`` /
``entitled_client`` fixtures (a genuine B2 generation published through the
worker's normal seam) and its ``_milestone_snapshot`` / ``_milestone_projection``
/ ``_milestone_operational`` fixtures (a monkeypatched ``_read_bundle`` for
scenario control), reused here rather than re-implemented.
"""
from __future__ import annotations

import json
import re
from datetime import date, timedelta
from pathlib import Path
from typing import Any, Iterator
from unittest import mock

import pytest

pytest.importorskip("fastapi", reason="BioCatalyst API tests need fastapi")
pytest.importorskip("httpx", reason="FastAPI TestClient needs httpx")

from fastapi import FastAPI, HTTPException  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

import app.biocatalyst as biocatalyst_api  # noqa: E402
from engine.biocatalyst.catalyst_events import (  # noqa: E402
    RADAR_EVENT_KINDS,
    RADAR_HORIZONS,
    project_trial_milestones,
)
from tests.test_biocatalyst_api import (  # noqa: E402
    _assert_private_headers,
    _classified_change_tape,
    _classified_change_tape_projection,
    _milestone_operational,
    _milestone_projection,
    _milestone_snapshot,
    _walk_keys,
    entitled_client,  # noqa: F401  (fixture)
    promoted_config,  # noqa: F401  (fixture)
)

# Mirrors test_biocatalyst_api.py's own evidence-safety fragment list -- the
# private-shaped keys this public route must never expose regardless of what
# the underlying worker state carries.
_FORBIDDEN_KEY_FRAGMENTS = (
    "canonical_study",
    "canonical_content",
    "source_snapshot",
    "source_record_ref",
    "raw_object",
    "receipt",
    "object_key",
    "source_pointer",
    "source_json_path",
    "manifest_sha",
    "generation_id",
    "snapshot_id",
    "query_sha",
)
_FORBIDDEN_VALUE_PATTERN = re.compile(r"score|probability|materiality|rank|composite|confidence|weight", re.IGNORECASE)
_ABSOLUTE_PATH_PATTERN = re.compile(r"^(?:/[A-Za-z0-9_.\-]+){2,}$")
_R2_OBJECT_KEY_PATTERN = re.compile(r"^biocatalyst/[a-z_]+/")
_HEX_HASH_PATTERN = re.compile(r"^[0-9a-f]{40,64}$")


def _walk_values(value: Any) -> Iterator[Any]:
    if isinstance(value, dict):
        for nested in value.values():
            yield from _walk_values(nested)
    elif isinstance(value, list):
        for nested in value:
            yield from _walk_values(nested)
    else:
        yield value


# ---------------------------------------------------------------------------
# 1-3: envelope shape, authority, headers -- against a REAL published cut.
# ---------------------------------------------------------------------------


def test_catalyst_radar_returns_expected_envelope_against_a_real_published_generation(
    entitled_client,
) -> None:
    response = entitled_client.get("/api/biocatalyst/v1/catalyst-radar")
    assert response.status_code == 200
    _assert_private_headers(response)
    payload = response.json()
    for key in (
        "schema_version",
        "as_of",
        "source",
        "health",
        "coverage",
        "authority",
        "query",
        "effective_horizon",
        "pagination",
        "catalyst_radar",
    ):
        assert key in payload, key
    assert payload["authority"]["decision_authority"] is False

    # Nonzero rows against the real single-trial worker fixture generation
    # (NCT00000001, primary_completion 2026-12 ESTIMATED, no sponsor on file,
    # RECRUITING, no revision history collected on this seam).
    rows = payload["catalyst_radar"]
    assert len(rows) == 1, rows
    row = rows[0]
    assert row["nct_id"] == "NCT00000001"
    assert row["kind"] == "primary_completion"
    assert row["milestone"]["date"] == "2026-12"
    assert row["timing"]["state"] == "upcoming"
    assert row["trial_status"] == {"value": "RECRUITING", "activity": "active", "reason_code": None}
    assert row["issuer"]["state"] == "sponsor_name_absent"
    assert row["revision"] == {
        "state": "history_not_collected",
        "count": 0,
        "latest": None,
        "lineage": [],
    }
    assert payload["pagination"]["total"] == 1
    assert payload["coverage"]["radar"]["trials_in_cohort"] == 1
    # _meta's own generation coverage block must survive being merged with the
    # radar denominators, not be clobbered by them.
    assert payload["coverage"]["class"] == "current_only"
    assert "configured" in payload["coverage"] and "observed" in payload["coverage"]


def test_catalyst_radar_authority_block_never_grants_decision_authority(entitled_client) -> None:
    response = entitled_client.get("/api/biocatalyst/v1/catalyst-radar")
    assert response.status_code == 200
    authority = response.json()["authority"]
    assert authority["decision_authority"] is False
    assert authority["classification"] == "source_fact"
    assert "originate_signal" in authority["forbidden_uses"]
    assert "raise_authority" in authority["forbidden_uses"]


def test_catalyst_radar_headers_are_exactly_the_private_set(entitled_client) -> None:
    response = entitled_client.get("/api/biocatalyst/v1/catalyst-radar")
    assert response.status_code == 200
    _assert_private_headers(response)
    assert response.headers["cache-control"] == "private, no-store"
    assert response.headers["vary"] == "Authorization"
    assert response.headers["x-content-type-options"] == "nosniff"
    assert response.headers["x-robots-tag"] == "noindex, noarchive"


# ---------------------------------------------------------------------------
# 4: unauthenticated -> 401 (entitlement dependency NOT overridden).
# ---------------------------------------------------------------------------


def test_catalyst_radar_requires_authentication_before_any_public_read() -> None:
    def must_not_read() -> tuple[object, dict[str, Any]]:
        raise AssertionError("anonymous catalyst-radar request reached the public reader")

    def deny() -> dict[str, Any]:
        raise HTTPException(
            401,
            "missing credentials",
            headers={
                **biocatalyst_api._PRIVATE_HEADERS,
                "WWW-Authenticate": "Bearer realm=mastermind",
            },
        )

    app = FastAPI()
    app.include_router(biocatalyst_api.router)
    app.dependency_overrides[biocatalyst_api.require_site_full_user] = deny
    with TestClient(app) as client:
        with mock.patch.object(biocatalyst_api, "_read_bundle", must_not_read):
            response = client.get("/api/biocatalyst/v1/catalyst-radar")

    assert response.status_code == 401
    _assert_private_headers(response)
    assert response.headers["www-authenticate"] == "Bearer realm=mastermind"
    assert response.json() == {"detail": "missing credentials"}


# ---------------------------------------------------------------------------
# 5: invalid horizon / milestone_kind / cursor -> 400.
# ---------------------------------------------------------------------------


def test_catalyst_radar_invalid_horizon_milestone_kind_and_cursor_fail_before_any_read(
    entitled_client, monkeypatch
) -> None:
    def must_not_read() -> tuple[object, dict[str, Any]]:
        raise AssertionError("invalid query must be rejected before the public read")

    monkeypatch.setattr(biocatalyst_api, "_read_bundle", must_not_read)

    bad_horizon = entitled_client.get("/api/biocatalyst/v1/catalyst-radar?horizon=bogus")
    assert bad_horizon.status_code == 400
    assert bad_horizon.json() == {"detail": "invalid horizon"}
    _assert_private_headers(bad_horizon)

    bad_kind = entitled_client.get("/api/biocatalyst/v1/catalyst-radar?milestone_kind=bogus")
    assert bad_kind.status_code == 400
    assert bad_kind.json() == {"detail": "invalid milestone_kind"}
    _assert_private_headers(bad_kind)

    bad_cursor = entitled_client.get("/api/biocatalyst/v1/catalyst-radar?cursor=not-a-real-cursor!!")
    assert bad_cursor.status_code == 400
    assert bad_cursor.json() == {"detail": "invalid cursor"}
    _assert_private_headers(bad_cursor)


# ---------------------------------------------------------------------------
# 6: anchor is the generation clock, never wall clock.
# ---------------------------------------------------------------------------


def test_catalyst_radar_anchor_is_the_generation_clock_not_wall_clock(
    entitled_client, monkeypatch
) -> None:
    projection = _milestone_projection(
        [_milestone_snapshot("NCT00000001", primary_completion=("2026-05-01", "ESTIMATED"))],
        as_of="2026-02-28T23:30:00Z",
    )
    monkeypatch.setattr(biocatalyst_api, "_read_bundle", lambda: (projection, _milestone_operational()))

    response = entitled_client.get("/api/biocatalyst/v1/catalyst-radar?horizon=all")
    assert response.status_code == 200
    payload = response.json()
    # The generation's committed as-of civil date, not whatever "today" is
    # when the test happens to run.
    assert payload["effective_horizon"]["anchor_date"] == "2026-02-28"
    assert payload["as_of"] == "2026-02-28T23:30:00Z"


def test_catalyst_radar_prioritizes_current_and_upcoming_before_paginating_history(
    entitled_client, monkeypatch
) -> None:
    anchor = date(2026, 8, 20)
    snapshots = [
        _milestone_snapshot("NCT70000000", primary_completion=("2026-08", "ESTIMATED")),
        _milestone_snapshot("NCT70000001", primary_completion=("2026-08-21", "ESTIMATED")),
        _milestone_snapshot("NCT70000002", primary_completion=("2026-09-01", "ESTIMATED")),
        _milestone_snapshot("NCT70000003", primary_completion=("2026-10-01", "ESTIMATED")),
    ]
    snapshots.extend(
        _milestone_snapshot(
            f"NCT71{index:06d}",
            primary_completion=((anchor - timedelta(days=index)).isoformat(), "ACTUAL"),
        )
        for index in range(1, 61)
    )
    projection = _milestone_projection(
        snapshots,
        as_of="2026-08-20T12:00:00Z",
    )
    monkeypatch.setattr(
        biocatalyst_api,
        "_read_bundle",
        lambda: (projection, _milestone_operational()),
    )

    first_response = entitled_client.get(
        "/api/biocatalyst/v1/catalyst-radar?horizon=all&limit=50"
    )
    assert first_response.status_code == 200
    first_payload = first_response.json()
    first_rows = first_payload["catalyst_radar"]
    assert len(first_rows) == 50
    assert [row["timing"]["state"] for row in first_rows[:4]] == [
        "current",
        "upcoming",
        "upcoming",
        "upcoming",
    ]
    assert [row["milestone"]["interval_start"] for row in first_rows[1:4]] == [
        "2026-08-21",
        "2026-09-01",
        "2026-10-01",
    ]
    assert all(row["timing"]["state"] == "occurred" for row in first_rows[4:])
    first_occurred_dates = [row["milestone"]["interval_end"] for row in first_rows[4:]]
    assert first_occurred_dates == sorted(first_occurred_dates, reverse=True)

    cursor = first_payload["pagination"]["next_cursor"]
    assert isinstance(cursor, str) and cursor
    second_response = entitled_client.get(
        f"/api/biocatalyst/v1/catalyst-radar?horizon=all&limit=50&cursor={cursor}"
    )
    assert second_response.status_code == 200
    second_payload = second_response.json()
    second_rows = second_payload["catalyst_radar"]
    assert len(second_rows) == 14
    assert all(row["timing"]["state"] == "occurred" for row in second_rows)
    second_occurred_dates = [row["milestone"]["interval_end"] for row in second_rows]
    assert second_occurred_dates == sorted(second_occurred_dates, reverse=True)
    first_ids = {row["event_id"] for row in first_rows}
    second_ids = {row["event_id"] for row in second_rows}
    assert first_ids.isdisjoint(second_ids)
    assert len(first_ids | second_ids) == 64
    assert second_payload["pagination"]["next_cursor"] is None


# ---------------------------------------------------------------------------
# 7: sponsor-map failure degrades every row -- 200, never 503.
# ---------------------------------------------------------------------------


def test_catalyst_radar_sponsor_map_failure_degrades_to_200_never_503(
    entitled_client, monkeypatch
) -> None:
    def raising_loader(_repo_root: Any) -> dict[str, Any]:
        raise RuntimeError("sponsor ticker map unavailable in this deployment")

    monkeypatch.setattr(
        biocatalyst_api,
        "_catalyst_radar_runtime",
        lambda: (RADAR_HORIZONS, RADAR_EVENT_KINDS, project_trial_milestones, raising_loader),
    )
    projection = _milestone_projection(
        [
            _milestone_snapshot("NCT00000001", primary_completion=("2026-03-01", "ACTUAL")),
            _milestone_snapshot("NCT00000002", primary_completion=("2026-03-15", "ACTUAL")),
        ]
    )
    monkeypatch.setattr(biocatalyst_api, "_read_bundle", lambda: (projection, _milestone_operational()))

    response = entitled_client.get("/api/biocatalyst/v1/catalyst-radar?horizon=all")
    assert response.status_code == 200
    payload = response.json()
    rows = payload["catalyst_radar"]
    assert len(rows) == 2, rows
    assert all(row["issuer"]["state"] == "sponsor_map_unavailable" for row in rows)
    assert all(row["issuer"]["ticker"] is None for row in rows)


def test_catalyst_radar_loads_sponsor_map_at_most_once_per_request(
    entitled_client, monkeypatch
) -> None:
    calls: list[Any] = []

    def counting_loader(repo_root: Any) -> dict[str, Any]:
        calls.append(repo_root)
        return {"rows": []}

    monkeypatch.setattr(
        biocatalyst_api,
        "_catalyst_radar_runtime",
        lambda: (RADAR_HORIZONS, RADAR_EVENT_KINDS, project_trial_milestones, counting_loader),
    )
    projection = _milestone_projection(
        [
            _milestone_snapshot("NCT00000001", primary_completion=("2026-03-01", "ACTUAL")),
            _milestone_snapshot("NCT00000002", primary_completion=("2026-03-15", "ACTUAL")),
            _milestone_snapshot("NCT00000003", primary_completion=("2026-04-01", "ACTUAL")),
        ]
    )
    monkeypatch.setattr(biocatalyst_api, "_read_bundle", lambda: (projection, _milestone_operational()))

    response = entitled_client.get("/api/biocatalyst/v1/catalyst-radar?horizon=all")
    assert response.status_code == 200
    assert len(response.json()["catalyst_radar"]) == 3
    assert len(calls) == 1, "sponsor map loader must be called at most once per request"


# ---------------------------------------------------------------------------
# 8: no-score invariant across the full response.
# ---------------------------------------------------------------------------


def test_catalyst_radar_never_emits_a_score_rank_or_confidence_key(entitled_client) -> None:
    response = entitled_client.get("/api/biocatalyst/v1/catalyst-radar")
    assert response.status_code == 200
    payload = response.json()
    for key in _walk_keys(payload):
        assert not _FORBIDDEN_VALUE_PATTERN.search(key), key


# ---------------------------------------------------------------------------
# 9: evidence safety -- no absolute path, R2 object key, or private hash.
# ---------------------------------------------------------------------------


def test_catalyst_radar_never_leaks_a_path_object_key_or_private_hash(entitled_client) -> None:
    response = entitled_client.get("/api/biocatalyst/v1/catalyst-radar")
    assert response.status_code == 200
    payload = response.json()

    for key in _walk_keys(payload):
        lowered = key.lower()
        for fragment in _FORBIDDEN_KEY_FRAGMENTS:
            assert fragment not in lowered, key

    for value in _walk_values(payload):
        if not isinstance(value, str):
            continue
        assert not _ABSOLUTE_PATH_PATTERN.match(value), value
        assert not _R2_OBJECT_KEY_PATTERN.match(value), value
        assert not _HEX_HASH_PATTERN.match(value), value


# ---------------------------------------------------------------------------
# 11 (MINOR 9): revision lineage wiring THROUGH THE ENDPOINT.
#
# projection.change_tapes_by_nct hangs off the SAME `_read_bundle()` call
# this route already makes (the change-tape endpoint reads the identical
# attribute), so populating revisions_by_nct costs zero new I/O. This proves
# the wiring end to end: a real milestone-date change tape row renders
# has_revisions with correct from/to/from_version/to_version, and a
# same-shaped enrollment-only change never counts as a milestone revision.
# ---------------------------------------------------------------------------


def _exact_value_entry(value: str) -> dict[str, Any]:
    encoded = json.dumps(value)
    return {
        "state": "present",
        "value_json": encoded,
        "value_byte_length": len(encoded.encode("utf-8")),
        "value_truncated": False,
        "unavailable_reason": None,
    }


def _milestone_date_constraint_row(
    *,
    source_pointer: str = "/protocolSection/statusModule/primaryCompletionDateStruct/date",
    before_value: str = "2027-01",
    after_value: str = "2027-06",
    before_version: int = 1,
    exact_operation_index: int = 0,
    observed_at: str = "2026-08-02T12:00:00.000000Z",
    predecessor_basis: str = "before_version_record",
    predecessor_exact_operation_index: int | None = None,
) -> dict[str, Any]:
    """A milestone_date_constraint change row disclosing exact before/after values."""

    return {
        "field_class": "milestone_date_constraint",
        "exact_operation_index": exact_operation_index,
        "review_state": "not_required",
        "semantic_resolution": "registry_field_class_only",
        "op": "replace",
        "before_state": "present",
        "after_state": "present",
        "source_versions": {"before": before_version, "after": before_version + 1},
        "observed_at": observed_at,
        "protocol_change_asserted": False,
        "materiality_assessed": False,
        "correction_assessed": False,
        "exact_values": {
            "source_pointer": source_pointer,
            "before": _exact_value_entry(before_value),
            "after": _exact_value_entry(after_value),
        },
        "correction_lineage": {
            "relation": "supersedes_prior_recorded_value",
            "predecessor_basis": predecessor_basis,
            "predecessor_source_version": before_version,
            "predecessor_exact_operation_index": predecessor_exact_operation_index,
            "correction_assessed": False,
        },
    }


def _with_exact_value_disclosure(tape: dict[str, Any]) -> dict[str, Any]:
    rows = tape["history"]["rows"]
    tape["history"]["classification_count"] = len(
        {
            (
                row["source_versions"]["before"],
                row["source_versions"]["after"],
            )
            for row in rows
        }
    )
    tape["value_disclosure"] = {
        "encoding": "canonical_json_utf8",
        "locator_grammar": "rfc6901_json_pointer_into_source_record",
        "max_value_bytes": biocatalyst_api._CHANGE_TAPE_MAX_VALUE_JSON_BYTES,
        "max_tape_value_bytes": biocatalyst_api._CHANGE_TAPE_MAX_TAPE_VALUE_JSON_BYTES,
        "truncation_behavior": "declared_prefix_with_original_byte_length",
        "unavailable_behavior": "explicit_row_marker_never_empty_and_never_guessed",
        "correction_assessed": False,
        "state": "exact_values_present",
    }
    return tape


def test_catalyst_radar_attributes_both_dates_and_returns_full_public_lineage(
    entitled_client, monkeypatch
) -> None:
    revised_nct = "NCT60000001"
    enrollment_only_nct = "NCT60000002"
    snapshots = [
        _milestone_snapshot(
            revised_nct,
            primary_completion=("2027-06", "ESTIMATED"),
            completion=("2028-02", "ESTIMATED"),
        ),
        _milestone_snapshot(enrollment_only_nct, primary_completion=("2027-06", "ESTIMATED")),
    ]
    revised_tape = _classified_change_tape(
        revised_nct,
        rows=[
            _milestone_date_constraint_row(
                before_value="2026-12",
                after_value="2027-01",
                observed_at="2026-06-01T12:00:00.000000Z",
            ),
            _milestone_date_constraint_row(
                source_pointer="/protocolSection/statusModule/completionDateStruct/date",
                before_value="2028-01",
                after_value="2028-02",
                exact_operation_index=1,
                observed_at="2026-06-01T12:00:00.000000Z",
            ),
            _milestone_date_constraint_row(
                before_value="2027-01",
                after_value="2027-03",
                before_version=2,
                observed_at="2026-07-01T12:00:00.000000Z",
                predecessor_basis="prior_tape_row",
                predecessor_exact_operation_index=0,
            ),
            _milestone_date_constraint_row(
                before_value="2027-03",
                after_value="2027-06",
                before_version=3,
                observed_at="2026-08-02T12:00:00.000000Z",
                predecessor_basis="prior_tape_row",
                predecessor_exact_operation_index=0,
            ),
        ],
    )
    _with_exact_value_disclosure(revised_tape)
    enrollment_tape = _classified_change_tape(
        enrollment_only_nct,
        rows=[
            {
                "field_class": "enrollment",
                "exact_operation_index": 0,
                "review_state": "not_required",
                "semantic_resolution": "registry_field_class_only",
                "op": "replace",
                "before_state": "present",
                "after_state": "present",
                "source_versions": {"before": 1, "after": 2},
                "observed_at": "2026-08-02T12:00:00.000000Z",
                "protocol_change_asserted": False,
                "materiality_assessed": False,
                "correction_assessed": False,
            }
        ],
    )
    projection = _classified_change_tape_projection(
        snapshots, {revised_nct: revised_tape, enrollment_only_nct: enrollment_tape}
    )
    monkeypatch.setattr(biocatalyst_api, "_read_bundle", lambda: (projection, _milestone_operational()))

    response = entitled_client.get("/api/biocatalyst/v1/catalyst-radar?horizon=all")
    assert response.status_code == 200
    payload = response.json()
    rows = {(row["nct_id"], row["kind"]): row for row in payload["catalyst_radar"]}
    assert set(rows) == {
        (revised_nct, "primary_completion"),
        (revised_nct, "completion"),
        (enrollment_only_nct, "primary_completion"),
    }

    primary_revision = rows[(revised_nct, "primary_completion")]["revision"]
    assert primary_revision["state"] == "has_revisions"
    assert primary_revision["count"] == 3
    assert [(item["from"], item["to"]) for item in primary_revision["lineage"]] == [
        ("2026-12", "2027-01"),
        ("2027-01", "2027-03"),
        ("2027-03", "2027-06"),
    ]
    assert [(item["from_version"], item["to_version"]) for item in primary_revision["lineage"]] == [
        (1, 2),
        (2, 3),
        (3, 4),
    ]
    assert primary_revision["latest"] == primary_revision["lineage"][-1]

    completion_revision = rows[(revised_nct, "completion")]["revision"]
    assert completion_revision["state"] == "has_revisions"
    assert completion_revision["count"] == 1
    assert completion_revision["lineage"][0]["from"] == "2028-01"
    assert completion_revision["lineage"][0]["to"] == "2028-02"

    # An enrollment-only change on a covered NCT is real change-tape history,
    # but it is not a milestone-date revision -- it must never be misread as
    # one, and it must not fabricate a "no revisions collected" state either.
    enrollment_revision = rows[(enrollment_only_nct, "primary_completion")]["revision"]
    assert enrollment_revision["state"] == "no_revisions_recorded"
    assert enrollment_revision["count"] == 0
    assert enrollment_revision["lineage"] == []

    # The source locator is consumed for attribution and discarded.  No
    # revision-bearing response may expose it at any depth.
    assert "source_pointer" not in set(_walk_keys(payload))


def test_catalyst_radar_never_guesses_kind_without_one_exact_valid_pointer(
    entitled_client, monkeypatch
) -> None:
    absent_nct = "NCT60000011"
    unrecognized_nct = "NCT60000012"
    malformed_nct = "NCT60000013"
    snapshots = [
        _milestone_snapshot(
            nct_id,
            primary_completion=("2027-06", "ESTIMATED"),
            completion=("2028-02", "ESTIMATED"),
        )
        for nct_id in (absent_nct, unrecognized_nct, malformed_nct)
    ]

    absent_row = _milestone_date_constraint_row()
    absent_row.pop("exact_values")
    absent_row.pop("correction_lineage")
    absent_tape = _classified_change_tape(absent_nct, rows=[absent_row])
    unrecognized_tape = _with_exact_value_disclosure(
        _classified_change_tape(
            unrecognized_nct,
            rows=[
                _milestone_date_constraint_row(
                    source_pointer="/protocolSection/statusModule/startDateStruct/date"
                )
            ],
        )
    )
    malformed_tape = _with_exact_value_disclosure(
        _classified_change_tape(
            malformed_nct,
            rows=[
                _milestone_date_constraint_row(
                    source_pointer=(
                        "/protocolSection/statusModule/primaryCompletionDateStruct~2/date"
                    )
                )
            ],
        )
    )
    projection = _classified_change_tape_projection(
        snapshots,
        {
            absent_nct: absent_tape,
            unrecognized_nct: unrecognized_tape,
            malformed_nct: malformed_tape,
        },
    )
    monkeypatch.setattr(
        biocatalyst_api,
        "_read_bundle",
        lambda: (projection, _milestone_operational()),
    )

    response = entitled_client.get("/api/biocatalyst/v1/catalyst-radar?horizon=all")
    assert response.status_code == 200
    rows = response.json()["catalyst_radar"]
    assert len(rows) == 6
    assert all(row["revision"]["state"] == "no_revisions_recorded" for row in rows)
    assert all(row["revision"]["count"] == 0 for row in rows)
    assert all(row["revision"]["lineage"] == [] for row in rows)


# ---------------------------------------------------------------------------
# 12 (MAJOR 14): a parent-company ticker is never rendered as the sponsor's
# own listing.
# ---------------------------------------------------------------------------


def test_catalyst_radar_surfaces_issuer_relationship_for_parent_and_direct_issuers(
    entitled_client, monkeypatch
) -> None:
    sponsor_document = {
        "rows": [
            {
                "sponsor_name": "Acme Subsidiary Trials",
                "valid_from": "2020-01-01",
                "valid_to": None,
                "review_state": "reviewed_admitted",
                "ticker": "PARENTCO",
                "issuer_relationship": "parent_of_subsidiary_sponsor",
            },
            {
                "sponsor_name": "Beta Direct Pharma",
                "valid_from": "2020-01-01",
                "valid_to": None,
                "review_state": "reviewed_admitted",
                "ticker": "BETA",
                "issuer_relationship": "direct_issuer",
            },
        ]
    }
    parent_snapshot = _milestone_snapshot("NCT61000001", primary_completion=("2027-06-01", "ESTIMATED"))
    parent_snapshot["facts"]["sponsor"] = {"state": "observed", "value": {"name": "Acme Subsidiary Trials"}}
    direct_snapshot = _milestone_snapshot("NCT61000002", primary_completion=("2027-06-01", "ESTIMATED"))
    direct_snapshot["facts"]["sponsor"] = {"state": "observed", "value": {"name": "Beta Direct Pharma"}}
    projection = _milestone_projection([parent_snapshot, direct_snapshot])
    monkeypatch.setattr(
        biocatalyst_api,
        "_catalyst_radar_runtime",
        lambda: (
            RADAR_HORIZONS,
            RADAR_EVENT_KINDS,
            project_trial_milestones,
            lambda _repo_root: sponsor_document,
        ),
    )
    monkeypatch.setattr(biocatalyst_api, "_read_bundle", lambda: (projection, _milestone_operational()))

    response = entitled_client.get("/api/biocatalyst/v1/catalyst-radar?horizon=all")
    assert response.status_code == 200
    rows = {row["nct_id"]: row["issuer"] for row in response.json()["catalyst_radar"]}

    parent_issuer = rows["NCT61000001"]
    assert parent_issuer["state"] == "ticker_only"
    assert parent_issuer["ticker"] == "PARENTCO"
    assert parent_issuer["issuer_relationship"] == "parent_of_subsidiary_sponsor"

    direct_issuer = rows["NCT61000002"]
    assert direct_issuer["state"] == "ticker_only"
    assert direct_issuer["ticker"] == "BETA"
    assert direct_issuer["issuer_relationship"] == "direct_issuer"

    # The UI-side qualifier: the row renderer must brand a parent-company
    # ticker differently from a direct issuer's -- never a bare ticker chip
    # implying the trial belongs to the parent's own listed security.
    js = (_TEMPLATES / "biocatalyst.js").read_text(encoding="utf-8")
    assert "parent_of_subsidiary_sponsor" in js
    assert "isParentIssuer" in js
    parent_chip_body = js[js.index("function issuerChip(") : js.index("function trialStatusChip(")]
    assert "isParentIssuer" in parent_chip_body
    assert "is-parent" in parent_chip_body


# ---------------------------------------------------------------------------
# 10: static UI-contract checks (string-level, like test_biocatalyst_page.py).
# ---------------------------------------------------------------------------

_ROOT = Path(__file__).resolve().parents[1]
_TEMPLATES = _ROOT / "templates"


def test_ui_contract_wires_the_radar_api_and_365_day_window() -> None:
    js = (_TEMPLATES / "biocatalyst.js").read_text(encoding="utf-8")
    html = (_TEMPLATES / "biocatalyst.html.j2").read_text(encoding="utf-8")

    assert "RADAR_API" in js
    assert "/api/biocatalyst/v1/catalyst-radar" in js
    # The 180/365/730/All radar window options are painted at JS runtime onto
    # the shared window-control markup (tests/test_biocatalyst_page.py pins
    # that markup's SSR shape at 30/90/180/all, 90 active); "365" therefore
    # lives in the JS default/option table, not the static template.
    assert "365" in js
    assert "DEFAULT_RADAR_HORIZON = '365'" in js
    # Frozen ids/attributes (tests/test_biocatalyst_page.py:62-101) must survive
    # the upgrade in place.
    assert 'id="bci-mode-milestones"' in html
    assert 'data-mode="milestones"' in html


def test_ui_contract_never_speaks_forbidden_market_wording() -> None:
    js = (_TEMPLATES / "biocatalyst.js").read_text(encoding="utf-8")
    html = (_TEMPLATES / "biocatalyst.html.j2").read_text(encoding="utf-8")
    engine_src = (_ROOT / "engine" / "biocatalyst" / "catalyst_events.py").read_text(encoding="utf-8")
    # "readout" is checked as a standalone word: the pre-existing, unrelated
    # Temporal Braid feature owns the compound id/variable "braid-readout" /
    # "braidReadout" (bci-braid-readout), which is not the forbidden market
    # sense of the word and is out of this packet's scope.
    js_without_braid = re.sub(r"braid-?readout", "", js, flags=re.IGNORECASE)
    html_without_braid = re.sub(r"braid-?readout", "", html, flags=re.IGNORECASE)
    assert "readout" not in js_without_braid.lower()
    assert "readout" not in html_without_braid.lower()
    # WEAK TEST fix: the US spelling "canceled" is just as forbidden as
    # "cancelled", and the frozen projection engine (which never imports
    # app.* and could still smuggle market wording into its own
    # docstrings/comments) is in scope too, not only the two template files.
    for forbidden in ("catalyst date", "cancelled", "canceled"):
        assert forbidden not in js.lower(), forbidden
        assert forbidden not in html.lower(), forbidden
        assert forbidden not in engine_src.lower(), forbidden
    # The ZH side of the same prohibition: no Chinese "cancelled/withdrawn as
    # a market event" wording either -- only the frozen registry-status ZH
    # labels (already exercised elsewhere) may speak trial-status language.
    for forbidden_zh in ("取消",):
        assert forbidden_zh not in js, forbidden_zh
        assert forbidden_zh not in html, forbidden_zh
