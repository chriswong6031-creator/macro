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
    _build_identity_value,
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


def test_consensus_clock_uses_support_and_unfiltered_reference_index(
    tmp_path: Path,
    monkeypatch,
):
    import scripts.backfill_china_limit_tape as backfill_module

    raw_dir = tmp_path / "raw"
    raw_dir.mkdir()
    dates = pd.to_datetime(["2020-01-02", "2020-01-03", "2020-01-06"])
    reference = pd.DataFrame({"volume": [1.0, 0.0, 1.0]}, index=dates)
    reference.to_parquet(raw_dir / "600519.SS.parquet")
    for number in range(50):
        ticker_dates = list(dates)
        volumes = [1.0, 1.0, 1.0]
        if number == 0:
            ticker_dates.append(pd.Timestamp("2020-01-04"))  # unsupported vendor print
            volumes.append(1.0)
        pd.DataFrame({"volume": volumes}, index=ticker_dates).to_parquet(
            raw_dir / f"{number:06d}.SZ.parquet"
        )
    monkeypatch.setattr(backfill_module, "RAW_DIR", raw_dir)
    positions, receipt = backfill_module._observed_market_session_clock(
        sorted(raw_dir.glob("*.parquet")),
        floor=pd.Timestamp("2011-01-01"),
    )
    assert list(positions) == list(dates)
    assert receipt["sessions"] == 3
    assert receipt["reference_volume_filter_applied"] is False
    assert receipt["consensus_reference_exact_set_match"] is True
    assert pd.Timestamp("2020-01-04") not in positions


def test_nightly_passes_attested_clock_to_detector_and_name_packet(
    tmp_path: Path,
    monkeypatch,
):
    import engine.china_microstructure as microstructure_module
    import scripts.backfill_china_limit_tape as backfill_module
    import scripts.build_china_microstructure as nightly_module

    raw_dir = tmp_path / "raw"
    site_dir = tmp_path / "site" / "chinastatedata"
    standouts_dir = tmp_path / "site" / "factordata"
    out_dir = tmp_path / "out"
    raw_dir.mkdir()
    standouts_dir.mkdir(parents=True)
    dates = pd.bdate_range("2020-01-02", periods=3)
    frame = pd.DataFrame({
        "open": [10.0, 11.0, 12.1],
        "high": [10.0, 11.0, 12.1],
        "low": [10.0, 11.0, 12.1],
        "close": [10.0, 11.0, 12.1],
        "volume": [1.0, 1.0, 1.0],
    }, index=dates)
    frame.to_parquet(raw_dir / "600519.SS.parquet")
    (standouts_dir / "china_standouts.json").write_text(
        json.dumps({"buy": [{"ticker": "600519.SS"}], "watch": [], "laggards": []}),
        encoding="utf-8",
    )

    monkeypatch.setattr(nightly_module, "ROOT", tmp_path)
    monkeypatch.setattr(nightly_module, "RAW_DIR", raw_dir)
    monkeypatch.setattr(nightly_module, "OUT_DIR", out_dir)
    monkeypatch.setattr(nightly_module, "TAPE_PATH", out_dir / "limit_tape.parquet")
    monkeypatch.setattr(nightly_module, "EVENTS_PATH", out_dir / "limit_events.parquet")
    monkeypatch.setattr(nightly_module, "SITE_DIR", site_dir)
    monkeypatch.setattr(nightly_module, "JSON_PATH", site_dir / "microstructure.json")

    clock = {date.normalize(): position for position, date in enumerate(dates)}
    receipt = {"status": "attested", "sessions": len(clock)}
    monkeypatch.setattr(backfill_module, "validate_completeness_manifest", lambda: [])
    monkeypatch.setattr(
        backfill_module,
        "_observed_market_session_clock",
        lambda raw_files, floor: (clock, receipt.copy()),
    )
    monkeypatch.setattr(microstructure_module, "_load_st_set", lambda data_dir: frozenset())

    detector_clocks = []
    packet_clocks = []

    def fake_detect_limit_events(**kwargs):
        detector_clocks.append(kwargs["market_session_positions"])
        return [], (), 0

    def fake_name_packet(**kwargs):
        packet_clocks.append(kwargs["market_session_positions"])
        return {"ticker": kwargs["ticker"]}

    monkeypatch.setattr(microstructure_module, "_detect_limit_events", fake_detect_limit_events)
    monkeypatch.setattr(microstructure_module, "name_packet", fake_name_packet)

    result = nightly_module.build_increment(target_date=dates[-1].strftime("%Y-%m-%d"))
    assert result["status"] == "ok"
    assert detector_clocks and all(value is clock for value in detector_clocks)
    assert packet_clocks == [clock]
    output = json.loads((site_dir / "microstructure.json").read_text(encoding="utf-8"))
    assert output["metadata"]["market_session_clock"]["status"] == "attested"


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
    _, inventory = raw_universe_inventory(raw_dir, include_content_hash=True)
    events_path = tmp_path / "events.parquet"
    tape_path = tmp_path / "tape.parquet"
    source_path = tmp_path / "producer.py"
    events_path.write_bytes(b"events")
    tape_path.write_bytes(b"tape")
    source_path.write_text("# producer\n", encoding="utf-8")
    manifest_path = tmp_path / "manifest.json"
    manifest = {
        "schema_version": MANIFEST_SCHEMA_VERSION,
        "implementation_version": "test",
        "complete": True,
        "raw_universe": inventory,
        "scan": {"files_scanned": 1, "unreadable_count": 0, "unreadable_files": []},
        "producer": {"source_sha256": {str(source_path): _sha256_file(source_path)}},
        "rule_era": {},
        "market_session_clock": {},
        "st_membership": {},
        "prior_vs_rebuilt_reconciliation": {},
        "rule_fix_vs_registration_only_generation": {},
        "artifacts": {
            "limit_events": {"path": str(events_path), "sha256": _sha256_file(events_path)},
            "limit_tape": {"path": str(tape_path), "sha256": _sha256_file(tape_path)},
        },
    }
    manifest["build_identity"] = {"value": _build_identity_value(manifest)}
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    assert validate_completeness_manifest(manifest_path, raw_dir) == []

    events_path.write_bytes(b"corrupt")
    defects = validate_completeness_manifest(manifest_path, raw_dir)
    assert any("artifact sha256 drift" in defect for defect in defects)
    events_path.write_bytes(b"events")

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
        "current_1842_file_positive_volume_nominal_OHLCV_scan_and_"
        "observed_session_calendar_only"
    )
    assert "historical PIT ST/risk-warning membership" in manifest["not_complete_for"]
    assert "official all-A-share listing-universe or breadth denominator coverage" in (
        manifest["not_complete_for"]
    )
    assert any("listing dates" in caveat for caveat in manifest["not_complete_for"])
    assert manifest["raw_universe"]["file_count"] == 1_842
    assert manifest["raw_universe"]["original_baseline_file_count"] == 1_587
    assert manifest["raw_universe"]["later_additions_since_baseline"] == 255
    assert manifest["scan"]["files_scanned"] == 1_842
    assert manifest["scan"]["unreadable_count"] == 0
    assert manifest["raw_universe"]["content_sha256"]
    assert manifest["artifacts"]["limit_events"]["rows"] == 71_692
    assert manifest["artifacts"]["limit_tape"]["rows"] == 3_786
    assert manifest["event_counts"] == {
        "failed_down_seal": 9_867,
        "failed_up_seal": 16_362,
        "sealed_down": 13_281,
        "sealed_up": 32_182,
    }
    clock = manifest["market_session_clock"]
    assert clock["sessions"] == 3_786
    assert clock["sha256"] == "8e8803fcbec6c8e8eccd67351a732695baa891ceb56616ffa7cd4e71f90a1ac6"
    assert clock["consensus_reference_exact_set_match"] is True
    assert clock["reference_volume_filter_applied"] is False
    assert clock["generation_pin"]["support_names"] == 894


def test_manifest_pins_corrected_gap_and_zero_event_session_heal():
    manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    gap = manifest["historical_gap_census"]
    assert gap["later_added_files"] == 255
    # Rule-era restoration adds 32 genuine pre-reform ChiNext rows; positive-volume eligibility
    # removes one false later-file event from the prior 11,040-row registration-only census.
    assert gap["tickers"] == 239
    assert gap["rows"] == 11_071
    assert gap["rows_already_present_in_prior"] == 1
    assert gap["event_bearing_later_tickers_absent_from_prior"] == 203

    coverage = manifest["aggregate_session_coverage"]
    assert coverage["reference_ticker"] == REFERENCE_TICKER
    assert coverage["previous_tape_missing_reference_session_count"] == 35
    assert coverage["rebuilt_tape_missing_reference_session_count"] == 0
    # Of the 35 restored sessions, later-added names introduce events on 17; the other
    # 18 prove that the aggregate no longer drops genuine zero-event sessions.
    assert coverage["newly_restored_zero_event_session_count"] == 18
    assert coverage["zero_event_session_count"] == 23


def test_manifest_reconciles_full_rebuild_and_ipo_correction_without_residuals():
    manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    receipt = manifest["prior_vs_rebuilt_reconciliation"]
    assert receipt["prior_rows"] == 60_428
    assert receipt["rebuilt_rows"] == 71_692
    assert receipt["added_event_keys"] == 11_432
    assert receipt["removed_event_keys"] == 168
    assert receipt["net_event_keys"] == 11_264
    assert receipt["prior_duplicate_event_keys"] == 0
    assert receipt["rebuilt_duplicate_event_keys"] == 0
    assert receipt["naive_prior_plus_broad_gap_rows"] == 71_499
    assert receipt["rebuilt_minus_naive_rows"] == 193
    components = receipt["arithmetic_components"]
    assert components == {
        "broad_gap_overlap_already_in_prior": -1,
        "later_file_events_after_2026_06_30": 32,
        "current_raw_refresh_added": 53,
        "classifier_302_chinext_added": 7,
        "stale_prior_rows_removed_after_raw_refresh": -69,
        "old_main_width_rows_removed_by_302_chinext_classifier": -29,
        "registration_era_main_ipo_no_limit_rows_removed": -55,
        "pre_reform_chinext_false_ipo_exclusions_restored_original_universe": 252,
        "positive_volume_previous_close_rows_added_original_universe": 9,
        "positive_volume_ineligible_rows_removed_original_universe": -15,
        "start_floor_previous_close_context_rows_restored": 9,
        "unexplained_added": 0,
        "unexplained_removed": 0,
    }
    assert sum(components.values()) == 193
    reasons = receipt["reason_detail"]
    assert reasons["classifier_302_shared_keys_relabelled_main_to_chinext"] == 51
    assert reasons["current_raw_refresh_removed"]["by_ticker"] == {
        "000990.SZ": 19,
        "002827.SZ": 1,
        "300806.SZ": 10,
        "603663.SS": 39,
    }
    ipo = reasons["registration_era_main_ipo_no_limit_removed"]
    assert ipo["rows"] == 55
    assert ipo["tickers"] == 31
    assert ipo["by_event"] == {
        "failed_down_seal": 12,
        "failed_up_seal": 11,
        "sealed_down": 26,
        "sealed_up": 6,
    }
    chinext = reasons["pre_reform_chinext_false_ipo_exclusions_restored"]
    assert chinext["rows"] == 285
    assert chinext["tickers"] == 136
    assert chinext["by_event"] == {
        "failed_down_seal": 2,
        "failed_up_seal": 2,
        "sealed_down": 4,
        "sealed_up": 277,
    }
    nontrades = reasons["positive_volume_ineligible_rows_removed"]
    assert nontrades["rows"] == 15
    assert nontrades["by_ticker"] == {
        "000519.SZ": 1,
        "000703.SZ": 1,
        "000783.SZ": 1,
        "002340.SZ": 1,
        "600061.SS": 1,
        "600389.SS": 1,
        "600446.SS": 1,
        "600461.SS": 1,
        "600478.SS": 1,
        "600733.SS": 1,
        "600850.SS": 1,
        "600900.SS": 1,
        "601018.SS": 1,
        "601877.SS": 1,
        "603083.SS": 1,
    }
    assert reasons["positive_volume_previous_close_rows_added"]["rows"] == 9
    assert reasons["start_floor_previous_close_context_rows_restored"]["rows"] == 12
    overlap = receipt["reason_overlap_receipt"]
    assert overlap["added"]["duplicate_reason_memberships"] == 1
    floor = overlap["floor_context_cross_reason_deduplication"]
    assert floor["raw_floor_context_event_keys"] == 12
    assert floor["overlap_with_broad_gap_baseline_event_keys"] == 3
    assert floor["terminal_floor_context_event_keys"] == 9
    rule = manifest["rule_era"]["main_normal"]["registration_era_ipo_no_limit"]
    assert rule["effective_first_listing_date"] == "2023-04-10"
    assert rule["excluded_sessions_from_listing"] == 5
    assert rule["sse_rule_source"] and rule["szse_rule_source"]
    legacy = manifest["rule_era"]["main_normal"]["legacy_ipo_listing_day_special"]
    assert legacy["applies_to_listings_before"] == "2023-04-10"
    assert legacy["excluded_sessions_from_listing"] == 1
    assert legacy["sse_2014_rule_source"] and legacy["szse_2014_rule_source"]
    assert manifest["producer"]["python"] == "3.12.4"
    assert manifest["producer"]["pandas"] == "3.0.3"
    assert manifest["producer"]["pyarrow"] == "24.0.0"


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


def test_manifest_rule_fix_delta_and_lianban_clock_audit_are_exact():
    manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    delta = manifest["rule_fix_vs_registration_only_generation"]
    assert delta["before_rows"] == 71_406
    assert delta["after_rows"] == 71_692
    assert delta["added_event_keys"] == 308
    assert delta["removed_event_keys"] == 22
    assert delta["net_event_keys"] == 286
    assert delta["shared_event_attribute_changes"]["lianban_count"] == 63
    assert delta["tape_sessions_before"] == delta["tape_sessions_after"] == 3_786
    assert delta["aggregate_sums_after"] == {
        "failed_up_seal_count": 16_362,
        "lianban_2plus": 4_133,
        "limit_down_count": 13_281,
        "limit_up_count": 48_544,
        "sealed_up_close": 32_182,
    }
    assert delta["zero_event_session_count_before"] == 24
    assert delta["zero_event_session_count_after"] == 23

    clock = manifest["market_session_clock"]
    before = clock["registration_only_generation_audit"]
    after = clock["rebuilt_generation_audit"]
    assert before["reported_lianban_2plus"] == before["recomputed_lianban_2plus"] == 4_001
    assert after["reported_lianban_2plus"] == after["recomputed_lianban_2plus"] == 4_133
    assert before["attribute_mismatches"] == after["attribute_mismatches"] == 0
    assert before["false_gap_bridges"] == after["false_gap_bridges"] == 0


def test_committed_artifact_hashes_and_backfill_provenance_match_manifest():
    manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    artifacts = manifest["artifacts"]
    assert artifacts["limit_events"]["sha256"] == (
        "a9785b954ab9acc33696911e94d07c2ad5aa07cd0a8b753ae45d6dcc82484314"
    )
    assert artifacts["limit_tape"]["sha256"] == (
        "e17b426ed4fc107430038a08658e7a772c2da860f9ebd4302fb1ad6c44e49d17"
    )
    assert artifacts["limit_tape"]["sha256"] == _sha256_file(TAPE_PATH)
    assert artifacts["limit_events"]["sha256"] == _sha256_file(
        ROOT / artifacts["limit_events"]["path"]
    )

    tape = pd.read_parquet(TAPE_PATH)
    assert len(tape) == artifacts["limit_tape"]["rows"]
    assert tape["backfill"].eq(True).all()  # noqa: E712
    reference = pd.read_parquet(
        RAW_DIR / f"{REFERENCE_TICKER}.parquet", columns=["close", "volume"]
    )
    reference_dates = {
        pd.Timestamp(ts).normalize()
        for ts in pd.to_datetime(reference.index)
        if pd.Timestamp(ts) >= pd.Timestamp("2011-01-01")
    }
    assert reference_dates == set(pd.to_datetime(tape["date"]).dt.normalize())
    assert int(tape["st_excluded_counts"].sum()) == 2_636
