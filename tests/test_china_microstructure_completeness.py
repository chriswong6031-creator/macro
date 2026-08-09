"""Completeness and provenance pins for the full China limit-tape reconstruction."""
from __future__ import annotations

import ast
import hashlib
import json
import sys
from pathlib import Path

import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from scripts.backfill_china_limit_tape import (  # noqa: E402
    MANIFEST_PATH,
    MANIFEST_SCHEMA_VERSION,
    RAW_DIR,
    REFERENCE_TICKER,
    TAPE_PATH,
    _sha256_file,
    raw_universe_inventory,
    run_backfill,
    validate_completeness_manifest,
)


def _membership_hash(names: list[str]) -> str:
    payload = "".join(f"{name}\n" for name in sorted(names)).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _aggregate_backfill_literals(path: Path) -> list[bool]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    values: list[bool] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        if not isinstance(node.func, ast.Name) or node.func.id != "aggregate_daily":
            continue
        keyword = next((kw for kw in node.keywords if kw.arg == "backfill"), None)
        assert keyword is not None, f"aggregate_daily caller omitted provenance in {path}"
        assert isinstance(keyword.value, ast.Constant) and isinstance(keyword.value.value, bool)
        values.append(keyword.value.value)
    return values


def test_backfill_and_nightly_callers_stamp_opposite_provenance():
    assert _aggregate_backfill_literals(
        ROOT / "scripts" / "backfill_china_limit_tape.py"
    ) == [True]
    assert _aggregate_backfill_literals(
        ROOT / "scripts" / "build_china_microstructure.py"
    ) == [False]


def test_raw_universe_inventory_detects_a_later_added_file(tmp_path: Path):
    (tmp_path / "000001.SZ.parquet").touch()
    (tmp_path / "600519.SS.parquet").touch()
    _, before = raw_universe_inventory(tmp_path)
    assert before == {
        "file_count": 2,
        "membership_sha256": _membership_hash(
            ["000001.SZ.parquet", "600519.SS.parquet"]
        ),
    }

    (tmp_path / "688981.SS.parquet").touch()
    _, after = raw_universe_inventory(tmp_path)
    assert after["file_count"] == 3
    assert after["membership_sha256"] != before["membership_sha256"]


def test_manifest_validator_fails_closed_on_membership_drift(tmp_path: Path):
    raw_dir = tmp_path / "raw"
    raw_dir.mkdir()
    (raw_dir / "000001.SZ.parquet").touch()
    _, inventory = raw_universe_inventory(raw_dir)
    manifest_path = tmp_path / "manifest.json"
    manifest_path.write_text(
        json.dumps({
            "schema_version": MANIFEST_SCHEMA_VERSION,
            "complete": True,
            "raw_universe": inventory,
            "scan": {
                "files_scanned": 1,
                "unreadable_count": 0,
                "unreadable_files": [],
            },
        }),
        encoding="utf-8",
    )
    assert validate_completeness_manifest(manifest_path, raw_dir) == []

    (raw_dir / "000002.SZ.parquet").touch()
    defects = validate_completeness_manifest(manifest_path, raw_dir)
    assert any("file_count drift" in defect for defect in defects)
    assert any("membership_sha256 drift" in defect for defect in defects)


def test_partial_rebuild_cannot_publish_complete_artifacts():
    with pytest.raises(ValueError, match="partial --start runs are dry-run only"):
        run_backfill(start_date=pd.Timestamp("2015-01-01"), dry_run=False)


def test_committed_manifest_matches_current_1842_file_universe():
    assert validate_completeness_manifest() == []
    manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    assert manifest["complete"] is True
    assert manifest["completeness_scope"] == (
        "current_1842_file_nominal_OHLCV_scan_and_session_calendar_only"
    )
    assert "historical PIT ST/risk-warning membership" in manifest["not_complete_for"]
    assert "official all-A-share listing-universe or breadth denominator coverage" in (
        manifest["not_complete_for"]
    )
    assert manifest["raw_universe"]["file_count"] == 1_842
    assert manifest["raw_universe"]["original_baseline_file_count"] == 1_587
    assert manifest["raw_universe"]["later_additions_since_baseline"] == 255
    assert manifest["scan"]["files_scanned"] == 1_842
    assert manifest["scan"]["unreadable_count"] == 0
    assert manifest["raw_universe"]["content_sha256"]


def test_manifest_pins_corrected_gap_and_zero_event_session_heal():
    manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    gap = manifest["historical_gap_census"]
    assert gap["later_added_files"] == 255
    assert gap["tickers"] == 241
    assert gap["rows"] == 11_043
    assert gap["rows_already_present_in_prior"] == 1
    assert gap["event_bearing_later_tickers_absent_from_prior"] == 204

    coverage = manifest["aggregate_session_coverage"]
    assert coverage["reference_ticker"] == REFERENCE_TICKER
    assert coverage["previous_tape_missing_reference_session_count"] == 35
    assert coverage["rebuilt_tape_missing_reference_session_count"] == 0
    # Of the 35 restored sessions, later-added names introduce events on 16; the other
    # 19 prove that the aggregate no longer drops genuine zero-event sessions.
    assert coverage["newly_restored_zero_event_session_count"] == 19
    assert coverage["zero_event_session_count"] >= 19


def test_manifest_reconciles_all_eight_rows_without_duplicates_or_residuals():
    manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    receipt = manifest["prior_vs_rebuilt_reconciliation"]
    assert receipt["prior_rows"] == 60_428
    assert receipt["rebuilt_rows"] == 71_463
    assert receipt["added_event_keys"] == 11_133
    assert receipt["removed_event_keys"] == 98
    assert receipt["net_event_keys"] == 11_035
    assert receipt["prior_duplicate_event_keys"] == 0
    assert receipt["rebuilt_duplicate_event_keys"] == 0
    assert receipt["naive_prior_plus_broad_gap_rows"] == 71_471
    assert receipt["rebuilt_minus_naive_rows"] == -8
    components = receipt["arithmetic_components"]
    assert components == {
        "broad_gap_overlap_already_in_prior": -1,
        "later_file_events_after_2026_06_30": 32,
        "current_raw_refresh_added": 52,
        "classifier_302_chinext_added": 7,
        "stale_prior_rows_removed_after_raw_refresh": -69,
        "old_main_width_rows_removed_by_302_chinext_classifier": -29,
        "unexplained_added": 0,
        "unexplained_removed": 0,
    }
    assert sum(components.values()) == -8
    reasons = receipt["reason_detail"]
    assert reasons["classifier_302_shared_keys_relabelled_main_to_chinext"] == 51
    assert reasons["current_raw_refresh_removed"]["by_ticker"] == {
        "000990.SZ": 19,
        "002827.SZ": 1,
        "300806.SZ": 10,
        "603663.SS": 39,
    }


def test_manifest_discloses_st_snapshot_proxy_hash_asof_and_staleness():
    manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    membership = manifest["st_membership"]
    assert membership["mode"] == "current_snapshot_proxy_exact_attested_date_only"
    assert membership["pit_history_available"] is False
    assert membership["unknown_membership_uses_ordinary_width_with_alarm"] is True
    assert membership["snapshot"]["attested_asof"] == "2026-07-06"
    assert membership["snapshot"]["sha256"]
    assert membership["snapshot_stale_for_source_max"] is True
    assert membership["snapshot_stale_days_at_source_max"] == 32


def test_committed_artifact_hashes_and_backfill_provenance_match_manifest():
    manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    artifacts = manifest["artifacts"]
    assert artifacts["limit_tape"]["sha256"] == _sha256_file(TAPE_PATH)
    assert artifacts["limit_events"]["sha256"] == _sha256_file(
        ROOT / artifacts["limit_events"]["path"]
    )

    tape = pd.read_parquet(TAPE_PATH)
    assert len(tape) == artifacts["limit_tape"]["rows"]
    assert tape["backfill"].eq(True).all()  # noqa: E712
    reference = pd.read_parquet(RAW_DIR / f"{REFERENCE_TICKER}.parquet", columns=["close"])
    reference_dates = {
        pd.Timestamp(ts).normalize()
        for ts in pd.to_datetime(reference.index)
        if pd.Timestamp(ts) >= pd.Timestamp("2011-01-01")
    }
    assert reference_dates.issubset(set(pd.to_datetime(tape["date"]).dt.normalize()))
