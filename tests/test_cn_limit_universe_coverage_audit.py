"""Contracts for the A-share universe-selection coverage receipt."""
from __future__ import annotations

import json

from scripts.research import cn_limit_universe_coverage_audit as audit


def test_shanghai_vendor_alias_is_one_economic_identity():
    assert audit.canonical_ticker("600000.SH") == "600000.SS"
    assert audit.canonical_ticker("600000.ss") == "600000.SS"
    assert audit.canonical_ticker("000001.SZ") == "000001.SZ"


def test_current_frozen_coverage_receipt_reconciles():
    receipt = audit.build_receipt()
    universe = receipt["universe"]
    pool = receipt["zt_pool"]
    assert universe["raw_names"] == 1842
    assert universe["valuation_names"] == 5526
    assert universe["shsz_names"] == 5197
    assert universe["bse_names"] == 329
    assert universe["raw_valuation_overlap"] == 1838
    assert universe["raw_shsz_overlap"] == 1838
    assert universe["raw_bse_overlap"] == 0
    assert universe["coverage_buckets"]["lt_50_yi"]["raw_names"] == 19
    assert universe["coverage_buckets"]["lt_50_yi"]["names"] == 2622
    assert universe["top_cap_decile"] == {
        "names": 553, "raw_names": 553, "raw_share": 1.0,
    }
    assert pool["rows"] == 3102
    assert pool["observed_pool_sessions"] == 36
    assert pool["official_calendar_sessions_in_window"] == 39
    assert pool["reference_ticker_sessions_in_window"] == 39
    assert pool["reference_ticker_set_equal_official_calendar"] is True
    assert pool["missing_official_sessions"] == ["2026-06-29", "2026-07-09", "2026-07-22"]
    assert pool["off_session_pool_dates"] == []
    assert pool["literal_ticker_values"] == 1770
    assert pool["economic_names"] == 1607
    assert pool["raw_name_overlap"] == 580
    assert pool["raw_event_rows"] == 1187
    assert pool["valuation_matched_rows"] == 3087
    assert pool["valuation_unmatched_rows"] == 15
    assert pool["below_200_yi_event_rows"] == 2470
    assert pool["below_200_yi_event_row_share_all_rows"] == 0.79626
    assert pool["below_200_yi_share_of_valuation_matched_rows"] == 0.80013
    assert receipt["receipt_hash"] == audit.canonical_hash({
        key: value for key, value in receipt.items() if key != "receipt_hash"
    })


def test_generated_artifact_matches_builder():
    on_disk = json.loads(audit.OUT_PATH.read_text())
    assert on_disk == audit.build_receipt()
