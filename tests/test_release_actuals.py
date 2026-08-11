from __future__ import annotations

import json
from pathlib import Path

import pytest

from engine.release_actuals import (
    canonical_actual,
    is_scoring_truth_eligible,
    load_actual_ledger,
    normalize_publication,
    receipt_integrity_errors,
    receipts_from_payload,
    reconcile_receipts,
)
from scripts.reconcile_release_actuals import reconcile

_CASES = {
    "CPI": {
        "date": "2026-07-14",
        "reference_period": "June 2026",
        "publisher": "U.S. Bureau of Labor Statistics",
        "source_id": "bls_cpi",
        "source_url": "https://www.bls.gov/news.release/archives/cpi_07142026.htm",
        "parser": "cpi",
        "actual": {
            "headline_mom": -0.4,
            "core_mom": 0.0,
            "unit": "percent",
        },
    },
    "PPI": {
        "date": "2026-07-15",
        "reference_period": "June 2026",
        "publisher": "U.S. Bureau of Labor Statistics",
        "source_id": "bls_ppi",
        "source_url": "https://www.bls.gov/news.release/archives/ppi_07152026.htm",
        "parser": "ppi",
        "actual": {"headline_mom": 0.2, "unit": "percent"},
    },
    "NFP": {
        "date": "2026-08-07",
        "reference_period": "July 2026",
        "publisher": "U.S. Bureau of Labor Statistics",
        "source_id": "bls_employment",
        "source_url": "https://www.bls.gov/news.release/archives/empsit_08072026.htm",
        "parser": "nfp",
        "actual": {"payroll_change": 57_000, "unit": "persons"},
    },
    "PCE": {
        "date": "2026-07-30",
        "reference_period": "June 2026",
        "publisher": "U.S. Bureau of Economic Analysis",
        "source_id": "bea_pce",
        "source_url": "https://www.bea.gov/news/2026/personal-income-and-outlays-june-2026",
        "parser": "pce",
        "actual": {"headline_mom": -0.1, "core_mom": 0.1, "unit": "percent"},
    },
    "CLAIMS": {
        "date": "2026-08-06",
        "reference_period": "August 1, 2026",
        "publisher": "U.S. Department of Labor",
        "source_id": "dol_claims",
        "source_url": "https://www.dol.gov/newsroom/releases/eta/eta20260806",
        "parser": "claims",
        "actual": {"initial_claims": 199_000, "unit": "persons"},
    },
}


def _publication(event_type: str = "CPI") -> dict:
    case = _CASES[event_type]
    day = case["date"]
    actual = {**case["actual"], "reference_period": case["reference_period"]}
    return {
        "event_id": f"{event_type.lower()}:{day}",
        "type": event_type,
        "date": day,
        "reference_period": case["reference_period"],
        "data_ready": True,
        "publisher": case["publisher"],
        "source_id": case["source_id"],
        "source_url": case["source_url"],
        "source_sha256": "a" * 64,
        "first_seen_at": f"{day}T12:30:01+00:00",
        "observed_at": f"{day}T12:30:01+00:00",
        "source_released_at": f"{day}T12:30:00+00:00",
        "verified_at": f"{day}T12:31:00+00:00",
        "parser": {"name": case["parser"], "version": 1},
        "actual": actual,
    }


@pytest.mark.parametrize(
    ("event_type", "expected"),
    [
        ("CPI", [("cpi_headline", "2026-06", -0.4), ("cpi_core", "2026-06", 0.0)]),
        ("PPI", [("ppi_finaldemand", "2026-06", 0.2)]),
        ("NFP", [("nfp", "2026-07", 57.0)]),
        ("PCE", [("pce_headline", "2026-06", -0.1), ("pce_core", "2026-06", 0.1)]),
        ("CLAIMS", [("claims", "2026-08-06", 199.0)]),
    ],
)
def test_each_target_normalizes_only_from_compatible_official_source(
    event_type: str,
    expected: list[tuple[str, str, float]],
) -> None:
    rows = normalize_publication(_publication(event_type))
    assert [(row["release"], row["period"], row["actual"]) for row in rows] == expected
    assert all(row["actual_basis"] == "official_published_metric" for row in rows)
    assert all(row["automatic_scoring_eligible"] is True for row in rows)
    assert all(receipt_integrity_errors(row) == [] for row in rows)


@pytest.mark.parametrize("event_type", list(_CASES))
def test_agency_source_id_and_parser_contracts_fail_closed(event_type: str) -> None:
    bad = _publication(event_type)
    bad["source_url"] = "https://www.federalreserve.gov/not-the-publisher"
    assert normalize_publication(bad) == []

    bad = _publication(event_type)
    bad["publisher"] = "Wrong agency"
    assert normalize_publication(bad) == []

    bad = _publication(event_type)
    bad["source_id"] = "wrong_source"
    assert normalize_publication(bad) == []

    bad = _publication(event_type)
    bad["parser"]["name"] = "wrong_parser"
    assert normalize_publication(bad) == []

    bad = _publication(event_type)
    bad["parser"]["version"] = 2
    assert normalize_publication(bad) == []


def test_unofficial_domain_or_missing_hash_fails_closed() -> None:
    bad = _publication("CPI")
    bad["source_url"] = "https://example.com/cpi"
    assert normalize_publication(bad) == []
    bad = _publication("CPI")
    bad["source_sha256"] = None
    assert normalize_publication(bad) == []


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("first_seen_at", "2026-08-07 12:30:01"),
        ("observed_at", "2026-08-07"),
        ("source_released_at", "not-a-time"),
        ("verified_at", "2026-08-07T12:31:00"),
    ],
)
def test_timestamps_require_full_timezone_aware_iso(field: str, value: str) -> None:
    bad = _publication("NFP")
    bad[field] = value
    assert normalize_publication(bad) == []


def test_observation_cannot_precede_source_release() -> None:
    bad = _publication("NFP")
    bad["source_released_at"] = "2026-08-07T14:30:46+00:00"
    assert normalize_publication(bad) == []

    bad = _publication("NFP")
    bad["verified_at"] = "2026-08-07T12:29:59+00:00"
    assert normalize_publication(bad) == []


def test_malformed_or_mismatched_nfp_reference_period_fails_closed() -> None:
    malformed = _publication("NFP")
    malformed["actual"]["reference_period"] = "The"
    assert normalize_publication(malformed) == []

    mismatched = _publication("NFP")
    mismatched["actual"]["reference_period"] = "June 2026"
    assert normalize_publication(mismatched) == []


def test_explicit_source_period_avoids_mechanical_month_minus_one() -> None:
    delayed = _publication("PCE")
    delayed["date"] = "2026-08-31"
    delayed["event_id"] = "pce:2026-08-31"
    delayed["first_seen_at"] = "2026-08-31T12:30:01+00:00"
    delayed["observed_at"] = "2026-08-31T12:30:01+00:00"
    delayed["source_released_at"] = "2026-08-31T12:30:00+00:00"
    delayed["verified_at"] = "2026-08-31T12:31:00+00:00"
    rows = normalize_publication(delayed)
    assert {row["period"] for row in rows} == {"2026-06"}
    assert all(
        row["period_resolution"] == "validated_parser_and_source_reference_period"
        for row in rows
    )


def test_claims_reference_week_must_match_source_and_schedule() -> None:
    bad = _publication("CLAIMS")
    bad["actual"]["reference_period"] = "August 8, 2026"
    bad["reference_period"] = "August 8, 2026"
    assert normalize_publication(bad) == []


def test_canonical_actual_revalidates_persisted_truth() -> None:
    valid = normalize_publication(_publication("NFP"))[0]
    assert canonical_actual([valid], "nfp", "2026-07") == valid

    malformed_period = {**valid, "official_reference_period": "The"}
    assert "reference_period_invalid" in receipt_integrity_errors(malformed_period)
    assert canonical_actual([malformed_period], "nfp", "2026-07") is None

    early = {
        **valid,
        "source_released_at": "2026-08-07T14:30:46+00:00",
    }
    assert "observed_before_source_release" in receipt_integrity_errors(early)
    assert canonical_actual([early], "nfp", "2026-07") is None

    wrong_agency = {**valid, "source_id": "bea_pce"}
    assert "source_id_mismatch" in receipt_integrity_errors(wrong_agency)
    assert canonical_actual([wrong_agency], "nfp", "2026-07") is None


def test_defect_sidecar_is_absent_open_and_matching_malformed_closed(
    tmp_path: Path,
) -> None:
    missing = tmp_path / "absent.json"
    row = normalize_publication(
        _publication("PCE"),
        defects_path=missing,
    )[0]
    assert is_scoring_truth_eligible(row, defects_path=missing)

    unrelated = tmp_path / "unrelated.json"
    unrelated.write_text(
        json.dumps(
            {
                "schema": "official_actual_defects.v1",
                "defects_by_receipt": {"official_actual:unrelated": "malformed"},
            }
        ),
        encoding="utf-8",
    )
    assert is_scoring_truth_eligible(row, defects_path=unrelated)

    matching = tmp_path / "matching.json"
    matching.write_text(
        json.dumps(
            {
                "schema": "official_actual_defects.v1",
                "defects_by_receipt": {row["receipt_id"]: "malformed"},
            }
        ),
        encoding="utf-8",
    )
    assert receipt_integrity_errors(row, defects_path=matching)[-1] == (
        "known_source_binding_defect"
    )
    assert not is_scoring_truth_eligible(row, defects_path=matching)
    assert canonical_actual(
        [row],
        row["release"],
        row["period"],
        defects_path=matching,
    ) is None

    invalid_root = tmp_path / "invalid.json"
    invalid_root.write_text("{not-json", encoding="utf-8")
    assert "official_actual_defect_sidecar_invalid" in receipt_integrity_errors(
        row,
        defects_path=invalid_root,
    )
    assert not is_scoring_truth_eligible(row, defects_path=invalid_root)


def test_keep_first_and_correction_candidate() -> None:
    payload = {"schema": "release_publications.v2", "publications": [_publication("CPI")]}
    first = receipts_from_payload(payload)
    assert len(reconcile_receipts(payload, [])) == 2
    changed = _publication("CPI")
    changed["source_sha256"] = "b" * 64
    changed["actual"]["headline_mom"] = -0.3
    novel = reconcile_receipts(
        {"schema": "release_publications.v2", "publications": [changed]}, first
    )
    assert all(row["row_type"] == "correction_candidate" for row in novel)
    assert canonical_actual(first + novel, "cpi_headline", "2026-06")["actual"] == -0.4


def test_quarantined_pce_receipts_yield_to_fresh_bound_receipts() -> None:
    root = Path(__file__).resolve().parents[1]
    existing = load_actual_ledger(
        root / "data" / "release_forecast" / "official_actuals.jsonl"
    )
    defective_replay = _publication("PCE")
    defective_replay["source_sha256"] = (
        "29ae0bad7d568ca7ea59be2f74461b5dcf5da4393ff816544254cd47507f13e1"
    )
    assert reconcile_receipts(
        {
            "schema": "release_publications.v2",
            "publications": [defective_replay],
        },
        [],
    ) == []

    corrected = _publication("PCE")
    corrected["source_sha256"] = "b" * 64
    payload = {"schema": "release_publications.v2", "publications": [corrected]}

    novel = reconcile_receipts(payload, existing)

    assert len(novel) == 2
    assert all(row["row_type"] == "actual" for row in novel)
    assert all(row["automatic_scoring_eligible"] is True for row in novel)
    assert all(is_scoring_truth_eligible(row) for row in novel)
    for release in ("pce_headline", "pce_core"):
        winner = canonical_actual(existing + novel, release, "2026-06")
        assert winner is not None
        assert winner["source_sha256"] == "b" * 64
        assert winner["receipt_id"] in {row["receipt_id"] for row in novel}


def test_file_reconciliation_is_idempotent(tmp_path: Path) -> None:
    payload_path = tmp_path / "live.json"
    out = tmp_path / "actuals.jsonl"
    payload_path.write_text(
        json.dumps({"schema": "release_publications.v2", "publications": [_publication("CPI")]}),
        encoding="utf-8",
    )
    assert len(reconcile(str(payload_path), out)) == 2
    assert reconcile(str(payload_path), out) == []
    assert len(out.read_text(encoding="utf-8").splitlines()) == 2


def test_committed_official_actual_ledger_quarantines_known_pce_binding_defects(
    tmp_path: Path,
) -> None:
    root = Path(__file__).resolve().parents[1]
    rows = load_actual_ledger(root / "data" / "release_forecast" / "official_actuals.jsonl")
    assert rows
    missing_sidecar = tmp_path / "absent.json"
    assert all(
        receipt_integrity_errors(row, defects_path=missing_sidecar) == []
        for row in rows
    )
    quarantined = {
        row["receipt_id"]
        for row in rows
        if "known_source_binding_defect" in receipt_integrity_errors(row)
    }
    assert quarantined == {
        "official_actual:0492229833dc679fdb39494f",
        "official_actual:3af69117d78be4d9ea46b002",
    }
    assert all(
        is_scoring_truth_eligible(row) == (row["receipt_id"] not in quarantined)
        for row in rows
    )
    assert all(row.get("official_reference_period") != "The" for row in rows)
