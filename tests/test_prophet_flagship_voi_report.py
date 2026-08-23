from __future__ import annotations

import json

import pytest

from scripts import prophet_flagship_voi_report as report_cli
from engine.prophet_voi import (
    DESCRIPTIVE_ONLY,
    HOLD_INTEGRITY,
    MEASURED,
    PROTECTED_OUTCOME,
    UNAVAILABLE_FIELD,
)


def _clock() -> dict:
    return {
        "claim_family": "demand_chain",
        "declared_horizon_d": 126,
        "first_prospective_registration_utc": "2026-08-19T08:10:37.995754+00:00",
        "git_sha": "34899ec5235884e183be86088ab01f81e34a693f",
        "horizon_unit": "trading_days",
    }


def _w3() -> dict:
    return {
        "schema": "us.prophet_w3_status/v1",
        "authority": "measurement only / none",
        "comparison_surface": "forbidden",
        "first_lawful_comparison_read": "PENDING until 20 matured H=10 sessions",
        "honest_n_floor": 20,
        "matured_h10_sessions": 0,
        "paired_sessions_accrued": 5,
        "unmatured_sessions": 5,
        "n_degraded_or_unpaired": 6,
        "n_missing": 0,
        "structural": {"outcome_blind": True},
    }


def test_qledger_clock_inventory_reads_only_clock_metadata(tmp_path, monkeypatch) -> None:
    (tmp_path / "demand_chain.json").write_text(json.dumps(_clock()), encoding="utf-8")
    monkeypatch.setattr(report_cli, "DEFAULT_QLEDGER_CLOCK_DIR", tmp_path)
    got = report_cli._qledger_clock_inventory()
    assert got["state"] == MEASURED
    assert got["registration_count"] == 1
    assert got["registrations"][0]["claim_family"] == "demand_chain"
    assert got["registrations"][0]["declared_horizon_d"] == 126
    assert got["outcome_files_opened"] is False
    assert got["promotion_authority"] is False


def test_qledger_clock_inventory_holds_on_filename_family_mismatch(tmp_path, monkeypatch) -> None:
    (tmp_path / "stock_desk.json").write_text(json.dumps(_clock()), encoding="utf-8")
    monkeypatch.setattr(report_cli, "DEFAULT_QLEDGER_CLOCK_DIR", tmp_path)
    got = report_cli._qledger_clock_inventory()
    assert got["state"] == HOLD_INTEGRITY
    assert got["registration_count"] == 0
    assert len(got["invalid_records"]) == 1
    assert got["outcome_files_opened"] is False


def test_cli_rejects_arbitrary_w3_and_board_source_paths() -> None:
    with pytest.raises(SystemExit):
        report_cli._args(["--w3-status", "some/outcome.json"])
    with pytest.raises(SystemExit):
        report_cli._args(["--board-ledger", "some/protected.parquet"])


def test_metadata_only_cli_proves_protected_w3_and_clock_without_board(
    tmp_path, monkeypatch, capsys
) -> None:
    w3_path = tmp_path / "status.json"
    w3_path.write_text(json.dumps(_w3()), encoding="utf-8")
    clock_dir = tmp_path / "clock"
    clock_dir.mkdir()
    (clock_dir / "demand_chain.json").write_text(json.dumps(_clock()), encoding="utf-8")
    monkeypatch.setattr(report_cli, "DEFAULT_W3_STATUS", w3_path)
    monkeypatch.setattr(report_cli, "DEFAULT_QLEDGER_CLOCK_DIR", clock_dir)

    rc = report_cli.main(["--no-board"])
    assert rc == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["promotion_authority"] is False
    assert payload["writes_evaluation_store"] is False
    assert payload["w3"]["state"] == PROTECTED_OUTCOME
    assert payload["w3"]["outcome_files_opened"] is False
    assert payload["qledger_evidence_clocks"]["state"] == MEASURED
    assert payload["qledger_evidence_clocks"]["outcome_files_opened"] is False
    assert payload["promotion"]["authorized"] is False


def test_current_committed_metadata_path_is_safe_and_zero_authority(capsys) -> None:
    assert report_cli.DEFAULT_W3_STATUS.is_file()
    assert report_cli.DEFAULT_QLEDGER_CLOCK_DIR.is_dir()
    rc = report_cli.main(["--no-board"])
    assert rc == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["promotion_authority"] is False
    assert payload["writes_evaluation_store"] is False
    assert payload["w3"]["outcome_files_opened"] is False
    assert payload["qledger_evidence_clocks"]["outcome_files_opened"] is False
    assert payload["qledger_evidence_clocks"]["registration_count"] >= 1
    assert payload["promotion"]["authorized"] is False


def test_current_committed_board_report_executes_without_upgrading_truth(capsys) -> None:
    assert report_cli.DEFAULT_BOARD_LEDGER.is_file()
    rc = report_cli.main([])
    assert rc == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["promotion_authority"] is False
    assert payload["writes_evaluation_store"] is False
    assert payload["promotion"]["authorized"] is False
    board = payload["us_board"]
    assert board["promotion_authority"] is False
    if board["state"] == DESCRIPTIVE_ONLY:
        assert board["source_grain"] == "(as_of,lane,ticker,horizon)"
        assert board["first_eligible_surface"]["state"] == UNAVAILABLE_FIELD
        assert board["first_presented_surface"]["state"] == UNAVAILABLE_FIELD
        assert board["actionable_at_first_surface"]["state"] == UNAVAILABLE_FIELD
        assert board["lead_vs_champion"]["state"] == UNAVAILABLE_FIELD
