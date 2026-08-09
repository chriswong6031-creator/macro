from __future__ import annotations

import json

import pytest

from engine.prophet_integrity import (
    PlanCorrectionError,
    apply_ledger_corrections,
    apply_plan_corrections,
    load_effective_ledger,
    load_ledger_corrections,
    load_ledger_quarantined_ids,
    effective_public_plan_date,
    load_plan_corrections,
)


@pytest.mark.parametrize(
    ("plan", "expected"),
    [
        ({
            "signal_date_basis": "tier_event_date",
            "signal_date": "2026-08-06",
            "observed_date": "2026-08-05",
        }, "2026-08-06"),
        ({
            "signal_date_basis": "tier_observation",
            "signal_date": "2026-07-01",
            "observed_date": "2026-08-05",
        }, "2026-08-05"),
        ({
            "signal_date_basis": "legacy_formation_alias",
            "signal_date": "2026-06-01",
            "price_basis_date": "2026-08-07",
            "entry_date": "2026-08-06",
        }, "2026-08-07"),
        ({"signal_date": "2026-08-06"}, None),
    ],
)
def test_effective_public_plan_date_is_strictly_family_native(plan, expected):
    assert effective_public_plan_date(plan) == expected


def _row(**overrides):
    row = {
        "schema": "prophet.plan_correction/v1",
        "id": "P1:price_basis_date:20260808",
        "corrects_id": "P1",
        "field": "price_basis_date",
        "old_value": None,
        "new_value": "2026-08-07",
        "basis": "entry price equals the 2026-08-07 close",
        "corrected_at": "2026-08-08",
        "evidence": {"price_source": "fixture", "published_entry": 100.0},
    }
    row.update(overrides)
    return row


def test_projection_never_mutates_the_published_plan():
    raw = {"P1": {"id": "P1", "signal_date": "2026-08-05", "entry_date": "2026-08-08"}}
    projection = apply_plan_corrections(raw, [
        _row(),
        _row(
            id="P1:entry_date:20260808",
            field="entry_date",
            old_value="2026-08-08",
            new_value="2026-08-07",
        ),
    ])

    assert raw["P1"].get("price_basis_date") is None
    assert projection.plans["P1"]["price_basis_date"] == "2026-08-07"
    assert projection.applied_by_plan["P1"] == (
        "P1:price_basis_date:20260808",
        "P1:entry_date:20260808",
    )


def test_entry_date_is_a_correctable_clock_not_trade_geometry():
    raw = {"P1": {"id": "P1", "entry_date": "2026-08-08"}}
    projection = apply_plan_corrections(
        raw,
        [_row(
            id="P1:entry_date:20260808",
            field="entry_date",
            old_value="2026-08-08",
            new_value="2026-08-07",
        )],
    )
    assert projection.plans["P1"]["entry_date"] == "2026-08-07"
    assert raw["P1"]["entry_date"] == "2026-08-08"


def test_identity_and_geometry_fields_cannot_be_corrected():
    with pytest.raises(PlanCorrectionError, match="not correctable"):
        apply_plan_corrections(
            {"P1": {"id": "P1"}},
            [_row(field="id", old_value="P1", new_value="P2")],
        )


def test_old_value_must_match_the_raw_publication_record():
    with pytest.raises(PlanCorrectionError, match="old_value mismatch"):
        apply_plan_corrections(
            {"P1": {"id": "P1", "signal_date": "2026-08-05"}},
            [_row(field="signal_date", old_value="2026-08-03", new_value="2026-08-07")],
        )


def test_quarantine_is_an_effective_disposition_not_a_plan_rewrite():
    status = _row(
        id="P1:integrity_status:20260808",
        field="integrity_status",
        new_value="quarantined",
        basis="mixed-vintage outage plan",
    )
    reason = _row(
        id="P1:integrity_reason:20260808",
        field="integrity_reason",
        new_value="mixed-vintage outage plan lacks exact price evidence",
        basis="mixed-vintage outage plan",
    )
    raw = {"P1": {"id": "P1"}}
    projection = apply_plan_corrections(raw, [status, reason])

    assert projection.quarantined_ids == frozenset({"P1"})
    assert "integrity_status" not in raw["P1"]


def test_loader_refuses_two_rows_that_compete_for_one_fact(tmp_path):
    path = tmp_path / "corrections.jsonl"
    first = _row()
    second = _row(id="P1:price_basis_date:again", new_value="2026-08-06")
    path.write_text(json.dumps(first) + "\n" + json.dumps(second) + "\n", encoding="utf-8")

    with pytest.raises(PlanCorrectionError, match="duplicate correction target"):
        load_plan_corrections(path)


def test_loader_requires_canonical_dates_and_evidence(tmp_path):
    path = tmp_path / "corrections.jsonl"
    path.write_text(json.dumps(_row(new_value="2026-8-7")) + "\n", encoding="utf-8")
    with pytest.raises(PlanCorrectionError, match="not an ISO date"):
        load_plan_corrections(path)

    path.write_text(json.dumps(_row(evidence={})) + "\n", encoding="utf-8")
    with pytest.raises(PlanCorrectionError, match="evidence"):
        load_plan_corrections(path)


def test_ledger_corrections_project_dates_without_rewriting_source(tmp_path):
    raw = [{
        "schema": "prophet.ledger/v1",
        "id": "P1",
        "signal_date": "2026-07-31",
    }]
    row = {
        "schema": "prophet.ledger_correction/v1",
        "id": "P1:ledger:price_basis_date:20260808",
        "corrects_id": "P1",
        "field": "price_basis_date",
        "old_value": None,
        "new_value": "2026-07-31",
        "basis": "creation-commit entry-price match",
        "corrected_at": "2026-08-08",
        "evidence": {"audit": "fixture"},
    }
    path = tmp_path / "ledger_corrections.jsonl"
    path.write_text(json.dumps(row) + "\n", encoding="utf-8")

    projection = apply_ledger_corrections(raw, load_ledger_corrections(path))

    assert projection.rows[0]["price_basis_date"] == "2026-07-31"
    assert "price_basis_date" not in raw[0]
    assert projection.applied_by_id["P1"] == (
        "P1:ledger:price_basis_date:20260808",
    )


def test_ledger_correction_refuses_ambiguous_duplicate_terminal_ids():
    rows = [{"id": "P1"}, {"id": "P1"}]
    with pytest.raises(PlanCorrectionError, match="duplicate terminal id"):
        apply_ledger_corrections(rows, [])


def test_direct_projection_rejects_duplicate_targets_without_loader():
    raw = {"P1": {"id": "P1"}}
    with pytest.raises(PlanCorrectionError, match="duplicate correction target"):
        apply_plan_corrections(raw, [_row(), _row(id="P1:price:again")])


def test_projection_rejects_unknown_disposition_and_impossible_chronology():
    raw = {"P1": {"id": "P1", "recorded_at": "2026-08-08"}}
    with pytest.raises(PlanCorrectionError, match="unknown integrity_status"):
        apply_plan_corrections(raw, [_row(
            field="integrity_status", new_value="looks_fine"
        )])
    with pytest.raises(PlanCorrectionError, match="unknown integrity_status"):
        apply_plan_corrections(raw, [_row(
            field="integrity_status", new_value=["audited_current"]
        )])

    with pytest.raises(PlanCorrectionError, match="postdates recorded_at"):
        apply_plan_corrections(raw, [_row(new_value="2026-08-10")])


@pytest.mark.parametrize(
    ("field", "new_value", "message"),
    [
        ("signal_tier", "T9", "unknown signal_tier"),
        ("signal_tier", ["T2"], "unknown signal_tier"),
        ("signal_date_basis", "close_enough", "unknown signal_date_basis"),
        (
            "signal_date_basis",
            ["legacy_formation_alias"],
            "unknown signal_date_basis",
        ),
    ],
)
def test_projection_rejects_unregistered_signal_provenance(
    field, new_value, message
):
    with pytest.raises(PlanCorrectionError, match=message):
        apply_plan_corrections(
            {"P1": {"id": "P1"}},
            [_row(field=field, new_value=new_value)],
        )


def test_legacy_signal_provenance_is_additive_and_explicit():
    raw = {"P1": {"id": "P1", "signal_date": "2026-08-05"}}
    projection = apply_plan_corrections(raw, [
        _row(
            id="P1:signal_date_basis:20260808",
            field="signal_date_basis",
            new_value="legacy_formation_alias",
        ),
        _row(
            id="P1:signal_tier:20260808",
            field="signal_tier",
            new_value="T2",
        ),
        _row(
            id="P1:source_marker_date:20260808",
            field="source_marker_date",
            new_value="2026-08-05",
        ),
    ])

    effective = projection.plans["P1"]
    assert effective["signal_date"] == "2026-08-05"
    assert effective["signal_date_basis"] == "legacy_formation_alias"
    assert effective["signal_tier"] == "T2"
    assert effective["source_marker_date"] == "2026-08-05"
    assert "signal_date_basis" not in raw["P1"]


def test_canonical_ledger_unions_legacy_and_correction_quarantines(tmp_path):
    store = tmp_path / "data" / "prophet"
    store.mkdir(parents=True)
    rows = [
        {"schema": "prophet.ledger/v1", "id": "LEGACY_BAD"},
        {"schema": "prophet.ledger/v1", "id": "CORRECTED_BAD"},
        {"schema": "prophet.ledger/v1", "id": "GOOD"},
    ]
    (store / "ledger.jsonl").write_text(
        "".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8"
    )
    corrections = [
        {
            "schema": "prophet.ledger_correction/v1",
            "id": f"CORRECTED_BAD:ledger:{field}:20260808",
            "corrects_id": "CORRECTED_BAD",
            "field": field,
            "old_value": None,
            "new_value": value,
            "basis": "fixture",
            "corrected_at": "2026-08-08",
            "evidence": {"audit": "fixture"},
        }
        for field, value in (
            ("integrity_status", "quarantined"),
            ("integrity_reason", "correction-only exclusion"),
        )
    ]
    (store / "ledger_corrections.jsonl").write_text(
        "".join(json.dumps(row) + "\n" for row in corrections), encoding="utf-8"
    )
    (store / "ledger_quarantine.json").write_text(json.dumps({
        "schema": "prophet.ledger_quarantine/v1",
        "count": 1,
        "quarantined": [{
            "id": "LEGACY_BAD",
            "reason": "graded_on_pre_origination_clock",
        }],
    }), encoding="utf-8")

    projection = load_effective_ledger(tmp_path)

    assert projection.quarantined_ids == frozenset({
        "LEGACY_BAD", "CORRECTED_BAD",
    })
    assert len(projection.rows) == 3


def test_legacy_quarantine_loader_fails_closed_on_receipt_drift(tmp_path):
    path = tmp_path / "ledger_quarantine.json"
    path.write_text(json.dumps({
        "schema": "prophet.ledger_quarantine/v1",
        "count": 2,
        "quarantined": [{"id": "P1", "reason": "fixture"}],
    }), encoding="utf-8")

    with pytest.raises(PlanCorrectionError, match="count"):
        load_ledger_quarantined_ids(path)


def test_legacy_quarantine_loader_rejects_whitespace_id(tmp_path):
    path = tmp_path / "ledger_quarantine.json"
    path.write_text(json.dumps({
        "schema": "prophet.ledger_quarantine/v1",
        "count": 1,
        "quarantined": [{"id": " P1", "reason": "fixture"}],
    }), encoding="utf-8")

    with pytest.raises(PlanCorrectionError, match="canonical id"):
        load_ledger_quarantined_ids(path)
