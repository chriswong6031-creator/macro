import hashlib
import json
import subprocess
from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest

from engine.prophet_integrity import (
    PlanCorrectionError,
    load_plan_corrections,
    validate_plan_correction,
)
from scripts.audit_prophet_plan_chronology import (
    OriginationReceiptError,
    _append_correction_rows,
    _integrity_disposition,
    audit_plan,
    build_plan_corrections,
    decimal_tolerance,
    match_latest_price_basis,
    match_price_basis,
    session_lag,
)


def _git(repo: Path, *args: str) -> str:
    return subprocess.run(
        ["git", *args], cwd=repo, check=True, capture_output=True, text=True,
    ).stdout.strip()


def _commit_all(repo: Path, message: str) -> str:
    _git(repo, "add", ".")
    _git(repo, "commit", "-m", message)
    return _git(repo, "rev-parse", "HEAD")


def _chronology_repo(
    tmp_path: Path,
    *,
    receipt_mutator=None,
    ambiguous: bool = False,
    legacy: bool = False,
) -> tuple[Path, Path, bytes | None]:
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init")
    _git(repo, "config", "user.email", "fixture@example.com")
    _git(repo, "config", "user.name", "Chronology Fixture")
    _git(repo, "config", "commit.gpgsign", "false")

    plan_path = repo / "site/prophet/plans/NVDA-BULL-20260805.json"
    plan_path.parent.mkdir(parents=True)
    plan = {
        "id": "NVDA-BULL-20260805",
        "asset": "NVDA",
        "asof": "2026-08-08",
        "formation_date": "2026-08-05",
        "signal_date": "2026-08-05",
        "entry": 100.0,
    }
    plan_path.write_text(
        json.dumps(plan, indent=2, sort_keys=True) + "\n", encoding="utf-8",
    )
    receipt_row = {
        "ticker": "NVDA",
        "entry_signal": {"spot": 100.0},
        "signal": {
            "tier_cascade": "T2",
            "last": {"date": "2026-08-05", "type": "buy"},
        },
    }
    source_staleness = {
        "price_through": "2026-08-07",
        "basis": "panel_majority",
        "delayed": False,
        "unknown": False,
        "inputs": {"panel": {"mixed_vintage": False}},
    }
    first_add_board = {
        "as_of": "2026-08-01",
        "staleness": {
            **source_staleness,
            "price_through": "2026-08-01",
        },
        "buy": [{
            "ticker": "NVDA",
            "entry_signal": {"spot": 1.0},
            "signal": {"tier_cascade": "T4"},
        }],
    }
    if legacy:
        # No receipt directory means the exact first-add standouts blob remains the
        # compatibility authority. Its wrapper date intentionally differs from its
        # Friday ranked-price watermark.
        first_add_board = {
            "as_of": "2026-08-08",
            "staleness": source_staleness,
            "buy": [receipt_row],
        }
    board_path = repo / "site/factordata/us_standouts.json"
    board_path.parent.mkdir(parents=True)
    board_path.write_text(
        json.dumps(first_add_board, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    receipt_bytes: bytes | None = None
    if not legacy:
        frozen_source = b"exact pre-build board bytes need not equal the selective commit"
        canonical_row = json.dumps(
            receipt_row, sort_keys=True, separators=(",", ":"), allow_nan=False,
        ).encode("utf-8")
        receipt = {
            "schema": "prophet.origination_receipt/v1",
            "receipt_id": "fixture",
            "recorded_utc": "2026-08-08T08:00:00+00:00",
            "run": {"id": "fixture", "attempt": "1"},
            "source": {
                "path": "site/factordata/us_standouts.json",
                "sha256": hashlib.sha256(frozen_source).hexdigest(),
                "size_bytes": len(frozen_source),
                "board_asof": "2026-08-08",
                "source_asof": "2026-08-07",
                "price_through": "2026-08-07",
                "source_basis": "panel_majority",
                "basis": "panel_majority",
                "delayed": False,
                "unknown": False,
                "staleness": source_staleness,
                "gate_go": True,
            },
            "selection": {
                "rule": "engine.prophet_bridge.select_candidates(n=None)",
                "admitted_count": 1,
                "originated_count": 1,
            },
            "originated_plan_ids": [plan["id"]],
            "originations": [{
                "plan_id": plan["id"],
                "asset": plan["asset"],
                "formation_date": plan["formation_date"],
                "plan_path": plan_path.relative_to(repo).as_posix(),
                "plan_sha256": hashlib.sha256(plan_path.read_bytes()).hexdigest(),
                "admission_rank": 1,
                "board_row_sha256": hashlib.sha256(canonical_row).hexdigest(),
                "board_row": receipt_row,
            }],
        }
        if receipt_mutator is not None:
            receipt_mutator(receipt)
        receipt_dir = repo / "data/prophet/origination_receipts"
        receipt_dir.mkdir(parents=True)
        receipt_path = receipt_dir / "fixture.json"
        receipt_path.write_text(
            json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8",
        )
        receipt_bytes = receipt_path.read_bytes()
        if ambiguous:
            duplicate = json.loads(json.dumps(receipt))
            duplicate["receipt_id"] = "fixture-copy"
            (receipt_dir / "fixture-copy.json").write_text(
                json.dumps(duplicate, indent=2, sort_keys=True) + "\n",
                encoding="utf-8",
            )

    _commit_all(repo, "first add plan")
    # HEAD has advanced twice: neither its board nor the potentially older board in the
    # selective first-add commit may override an atomic receipt.
    board_path.write_text(
        json.dumps({
            "as_of": "2026-08-09",
            "staleness": {
                **source_staleness,
                "price_through": "2026-08-08",
            },
            "buy": [{
                "ticker": "NVDA",
                "entry_signal": {"spot": 999.0},
                "signal": {"tier_cascade": "T1"},
            }],
        }, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    _commit_all(repo, "advance head board")
    return repo, plan_path, receipt_bytes


def test_decimal_tolerance_follows_the_published_precision():
    assert decimal_tolerance(Decimal("381.2")) > Decimal("0.05")
    assert decimal_tolerance(Decimal("18.03")) < Decimal("0.006")


def test_same_recorded_session_match_wins_over_an_old_repeated_price():
    read = match_price_basis(
        Decimal("3.67"),
        [(date(2026, 7, 31), 3.67), (date(2026, 8, 3), 3.67)],
        date(2026, 8, 3),
    )
    assert read["status"] == "matched"
    assert read["match"]["date"] == "2026-08-03"


def test_two_prior_matches_are_ambiguous_not_latest_wins():
    read = match_price_basis(
        Decimal("3.67"),
        [(date(2026, 7, 30), 3.67), (date(2026, 7, 31), 3.67)],
        date(2026, 8, 3),
    )
    assert read["status"] == "ambiguous"
    assert read["match"] is None


def test_creation_blob_rule_reads_only_the_latest_available_close():
    read = match_latest_price_basis(
        Decimal("172.2"),
        [(date(2026, 7, 1), 172.22), (date(2026, 8, 5), 172.24)],
        date(2026, 8, 6),
    )
    assert read["status"] == "matched"
    assert read["match"]["date"] == "2026-08-05"


def test_weekend_publication_has_zero_session_lag_from_friday_close():
    assert session_lag(date(2026, 8, 7), date(2026, 8, 8)) == 0


def test_one_missing_market_session_is_a_lag_even_if_calendar_gap_is_one_day():
    assert session_lag(date(2026, 8, 4), date(2026, 8, 5)) == 1


def test_atomic_receipt_beats_first_add_and_head_board_drift(tmp_path):
    repo, plan_path, receipt_bytes = _chronology_repo(tmp_path)

    audited = audit_plan(repo, plan_path)

    assert audited["board_as_of"] == "2026-08-08"
    assert audited["board_price_basis"] == "2026-08-07"
    assert audited["board_mixed_vintage"] is False
    assert audited["board_row_signal_tier"] == "T2"
    assert audited["board_row_spot"] == 100.0
    assert audited["price_basis_date"] == "2026-08-07"
    assert audited["price_match_status"] == "matched_origination_receipt"
    assert audited["price_source_scope"] == "origination_receipt_board_contract"
    assert audited["origination_receipt_path"] == (
        "data/prophet/origination_receipts/fixture.json"
    )
    assert audited["origination_receipt_sha256"] == hashlib.sha256(
        receipt_bytes
    ).hexdigest()


def test_commit_without_receipt_directory_keeps_legacy_creation_board_fallback(tmp_path):
    repo, plan_path, _ = _chronology_repo(tmp_path, legacy=True)

    audited = audit_plan(repo, plan_path)

    assert audited["board_as_of"] == "2026-08-08"
    assert audited["board_price_basis"] == "2026-08-07"
    assert audited["price_basis_date"] == "2026-08-07"
    assert audited["price_source_scope"] == "creation_board_contract"
    assert "origination_receipt_path" not in audited
    assert "origination_receipt_sha256" not in audited


def test_receipt_with_noncanonical_board_row_hash_fails_closed(tmp_path):
    def corrupt_row_hash(receipt):
        receipt["originations"][0]["board_row_sha256"] = "0" * 64

    repo, plan_path, _ = _chronology_repo(
        tmp_path, receipt_mutator=corrupt_row_hash,
    )

    with pytest.raises(OriginationReceiptError, match="board_row hash mismatch"):
        audit_plan(repo, plan_path)


def test_receipt_with_wrong_source_path_fails_closed(tmp_path):
    def corrupt_source_path(receipt):
        receipt["source"]["path"] = "site/factordata/other_board.json"

    repo, plan_path, _ = _chronology_repo(
        tmp_path, receipt_mutator=corrupt_source_path,
    )

    with pytest.raises(OriginationReceiptError, match="canonical US board"):
        audit_plan(repo, plan_path)


def test_receipt_with_wrong_plan_blob_hash_fails_closed(tmp_path):
    def corrupt_plan_hash(receipt):
        receipt["originations"][0]["plan_sha256"] = "0" * 64

    repo, plan_path, _ = _chronology_repo(
        tmp_path, receipt_mutator=corrupt_plan_hash,
    )

    with pytest.raises(OriginationReceiptError, match="plan blob hash mismatch"):
        audit_plan(repo, plan_path)


def test_receipt_with_wrong_plan_path_fails_closed(tmp_path):
    def corrupt_plan_path(receipt):
        receipt["originations"][0]["plan_path"] = (
            "site/prophet/plans/NVDA-BULL-WRONG.json"
        )

    repo, plan_path, _ = _chronology_repo(
        tmp_path, receipt_mutator=corrupt_plan_path,
    )

    with pytest.raises(OriginationReceiptError, match="does not match first-added path"):
        audit_plan(repo, plan_path)


def test_two_matching_receipts_are_ambiguous_and_fail_closed(tmp_path):
    repo, plan_path, _ = _chronology_repo(tmp_path, ambiguous=True)

    with pytest.raises(OriginationReceiptError, match="expected exactly one.*found 2"):
        audit_plan(repo, plan_path)


def test_legacy_correction_discloses_tier_basis_without_rewriting_signal_date(tmp_path):
    plans = tmp_path / "site" / "prophet" / "plans"
    plans.mkdir(parents=True)
    (plans / "P1.json").write_text(
        '{"id":"P1","signal_date":"2026-08-05","asof":"2026-08-08"}',
        encoding="utf-8",
    )
    audited = {
        "plan_id": "P1",
        "first_commit": "a" * 40,
        "first_committed_at": "2026-08-08T08:00:00Z",
        "board_as_of": "2026-08-07",
        "board_mixed_vintage": False,
        "board_row_signal_tier": "T2",
        "board_row_source_marker_date": "2026-08-05",
        "board_row_source_marker_type": "buy",
        "price_source": "data/stocks/P1.parquet",
        "price_source_scope": "creation_commit",
        "price_source_sha256": "b" * 64,
        "price_match_status": "matched",
        "market_session_lag": 0,
        "price_basis_date": "2026-08-07",
        "integrity_status": "price_current",
        "admission_integrity": "actionable_tier_proven",
    }

    rows = build_plan_corrections(
        tmp_path,
        {"rows": [audited]},
        corrected_at=date(2026, 8, 8),
        audit_receipt="research/audit.json",
    )
    by_field = {row["field"]: row for row in rows}

    assert "signal_date" not in by_field
    assert by_field["formation_date"]["new_value"] == "2026-08-05"
    assert by_field["signal_date_basis"]["new_value"] == "legacy_formation_alias"
    assert by_field["signal_tier"]["new_value"] == "T2"
    assert by_field["source_marker_date"]["new_value"] == "2026-08-05"
    assert "origination_receipt_path" not in by_field["entry_date"]["evidence"]
    assert "origination_receipt_sha256" not in by_field["entry_date"]["evidence"]

    receipt_backed = {
        **audited,
        "origination_receipt_path": (
            "data/prophet/origination_receipts/fixture.json"
        ),
        "origination_receipt_sha256": "c" * 64,
    }
    receipt_rows = build_plan_corrections(
        tmp_path,
        {"rows": [receipt_backed]},
        corrected_at=date(2026, 8, 8),
        audit_receipt="research/audit.json",
    )
    receipt_evidence = receipt_rows[0]["evidence"]
    assert receipt_evidence["origination_receipt_path"].endswith("fixture.json")
    assert receipt_evidence["origination_receipt_sha256"] == "c" * 64


def test_projected_t4_and_unknown_legacy_admission_are_quarantined():
    t4_status, t4_reason = _integrity_disposition({
        "admission_integrity": "non_actionable_t4",
        "integrity_status": "price_current",
    })
    unknown_status, unknown_reason = _integrity_disposition({
        "admission_integrity": "admission_tier_unknown",
        "integrity_status": "price_current",
    })

    assert t4_status == unknown_status == "quarantined"
    assert "T4" in t4_reason
    assert "lacks a persisted causal admission tier" in unknown_reason


def _plan_correction(plan_id, field, value):
    return {
        "schema": "prophet.plan_correction/v1",
        "id": f"{plan_id}:{field}:20260808",
        "corrects_id": plan_id,
        "field": field,
        "old_value": None,
        "new_value": value,
        "basis": "fixture",
        "corrected_at": "2026-08-08",
        "evidence": {"audit": "fixture"},
    }


def test_correction_writer_appends_and_exact_rerun_is_byte_idempotent(tmp_path):
    path = tmp_path / "plan_corrections.jsonl"
    existing = _plan_correction("OLD", "recorded_at", "2026-08-07")
    new = _plan_correction("NEW", "recorded_at", "2026-08-08")
    original = json.dumps(existing) + "\n"
    path.write_text(original, encoding="utf-8")

    appended = _append_correction_rows(
        path, [new], loader=load_plan_corrections,
        validator=validate_plan_correction,
    )
    first_pass = path.read_bytes()
    repeated = _append_correction_rows(
        path, [new], loader=load_plan_corrections,
        validator=validate_plan_correction,
    )

    assert appended == 1
    assert repeated == 0
    assert first_pass == path.read_bytes()
    assert path.read_text(encoding="utf-8").startswith(original)
    assert [row["corrects_id"] for row in load_plan_corrections(path)] == [
        "OLD", "NEW",
    ]


def test_correction_writer_refuses_hidden_target_revision(tmp_path):
    path = tmp_path / "plan_corrections.jsonl"
    existing = _plan_correction("P1", "recorded_at", "2026-08-07")
    path.write_text(json.dumps(existing) + "\n", encoding="utf-8")
    conflicting = {
        **_plan_correction("P1", "recorded_at", "2026-08-08"),
        "id": "P1:recorded_at:20260809",
        "corrected_at": "2026-08-09",
    }

    with pytest.raises(PlanCorrectionError, match="target"):
        _append_correction_rows(
            path, [conflicting], loader=load_plan_corrections,
            validator=validate_plan_correction,
        )
