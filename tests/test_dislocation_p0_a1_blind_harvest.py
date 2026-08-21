"""Deterministic tests for Dislocation P0-A1 price-blind harvest primitives."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts.research.dislocation_p0_a1_lib import (
    A1_DECLARED_LEDGER_SHA256,
    AUTHORITY_FALSE,
    LEXICON,
    PRIMARY_FAMILIES,
    QUOTAS,
    SEED,
    TURN5_LEXICON_SHA256,
    AccessLog,
    BlindWorkspaceError,
    assert_allowed_url,
    assert_blind_workspace,
    base_form,
    build_query_ledger,
    client_side_form_ok,
    clock_quality,
    extract_pass,
    forbidden_market_fields,
    is_amendment,
    is_design_excluded,
    lexicon_sha256,
    query_ledger_sha256,
    select_quota_rows,
    selection_key,
    split_date_range,
)


def test_lexicon_matches_turn5_capacity_census_hash() -> None:
    assert lexicon_sha256() == TURN5_LEXICON_SHA256
    assert "MACRO_OR_INDUSTRY_WIDE" not in LEXICON


def test_query_ledger_hash_is_stable_and_does_not_silently_claim_a1_file() -> None:
    ledger = build_query_ledger()
    digest = query_ledger_sha256(ledger)
    assert len(digest) == 64
    assert digest == query_ledger_sha256(build_query_ledger())
    assert ledger["a1_declared_ledger_sha256"] == A1_DECLARED_LEDGER_SHA256
    assert ledger["a1_declared_ledger_status"] == "UNVERIFIED_ABSENT_SOURCE_FILE"
    assert digest != A1_DECLARED_LEDGER_SHA256
    assert ledger["seed"] == SEED
    assert ledger["authority"] == AUTHORITY_FALSE
    assert all(not flag for flag in ledger["authority"].values())


def test_selection_key_is_deterministic() -> None:
    first = selection_key(
        family="CYBER_OR_IT_INTERRUPTION",
        era="modern",
        base="8-K",
        cik="0000320193",
        accession="0000320193-23-000077",
    )
    second = selection_key(
        family="CYBER_OR_IT_INTERRUPTION",
        era="modern",
        base="8-K",
        cik="0000320193",
        accession="0000320193-23-000077",
    )
    assert first == second
    assert first != selection_key(
        family="CYBER_OR_IT_INTERRUPTION",
        era="development",
        base="8-K",
        cik="0000320193",
        accession="0000320193-23-000077",
    )


def test_form_filter_keeps_amendments_visible_but_not_as_base_match_for_10k() -> None:
    assert client_side_form_ok("8-K", "8-K")
    assert client_side_form_ok("8-K/A", "8-K")
    assert not client_side_form_ok("10-K", "8-K")
    assert not client_side_form_ok("6-K", "8-K")
    assert is_amendment("8-K/A")
    assert not is_amendment("8-K")
    assert base_form("8-K/A") == "8-K"


def test_firewall_refuses_price_paths_and_banned_hosts(tmp_path: Path) -> None:
    assert_blind_workspace(tmp_path)
    (tmp_path / "data" / "ohlc").mkdir(parents=True)
    with pytest.raises(BlindWorkspaceError):
        assert_blind_workspace(tmp_path)
    assert_allowed_url("https://efts.sec.gov/LATEST/search-index")
    with pytest.raises(BlindWorkspaceError):
        assert_allowed_url("https://query1.finance.yahoo.com/v8/finance/chart/EXK")
    log = AccessLog()
    with pytest.raises(BlindWorkspaceError):
        log.read_path(tmp_path / "data" / "ohlc" / "EXK.parquet", tmp_path)
    assert log.banned_reads()


def test_date_split_and_clock_quality() -> None:
    left, right = split_date_range("2016-01-01", "2025-12-31")
    assert left[0] == "2016-01-01"
    assert right[1] == "2025-12-31"
    assert left[1] < right[0]
    assert clock_quality("2017-09-07T20:16:33Z", "2017-09-07") == "EXACT_SEC_ACCEPTANCE"
    assert clock_quality(None, "2017-09-07") == "DATE_ONLY_REFUSED"
    assert clock_quality(None, None) == "UNAVAILABLE"


def test_design_exclusion_is_endeavour_silver_not_us_edr() -> None:
    assert is_design_excluded(ticker="EXK", cik=None, display_name=None)
    assert is_design_excluded(
        ticker="EDR",
        cik="0001015647",
        display_name="Endeavour Silver Corp (EDR) (CIK 0001015647)",
    )
    assert not is_design_excluded(
        ticker="EDR",
        cik="0001959348",
        display_name="Endeavor Group Holdings, Inc. (EDR) (CIK 0001959348)",
    )


def test_quota_walk_caps_issuer_and_family_target() -> None:
    rows = []
    for idx in range(12):
        cik = "0000320193" if idx < 8 else f"{idx:010d}"
        accession = f"{cik}-23-{idx:06d}"
        rows.append(
            {
                "cik": cik,
                "accession": accession,
                "form": "8-K",
                "era": "modern",
                "selection_key": selection_key(
                    family="CYBER_OR_IT_INTERRUPTION",
                    era="modern",
                    base="8-K",
                    cik=cik,
                    accession=accession,
                ),
                "display_name": "TEST (AAPL) (CIK 0000320193)" if idx < 8 else f"OTHER{idx}",
            }
        )
    accepted, refused = select_quota_rows(rows, family="CYBER_OR_IT_INTERRUPTION")
    assert len(accepted) <= QUOTAS["CYBER_OR_IT_INTERRUPTION"]["source_target"]
    issuer_rows = [row for row in accepted if row["cik"] == "0000320193"]
    assert len(issuer_rows) <= 5
    assert any(row.get("refusal_reason") == "ISSUER_CAP" for row in refused)


def test_two_extraction_passes_can_disagree_on_structural_evidence() -> None:
    text = (
        "The Company experienced a ransomware cybersecurity incident on March 1. "
        "Operations were temporarily suspended. A material weakness in internal "
        "control was also identified."
    )
    pass1 = extract_pass(
        text,
        query_phrase="ransomware",
        family_candidate="CYBER_OR_IT_INTERRUPTION",
        pass_id="pass1",
    )
    pass2 = extract_pass(
        text,
        query_phrase="ransomware",
        family_candidate="CYBER_OR_IT_INTERRUPTION",
        pass_id="pass2",
    )
    assert pass1["intent_orchestration"] == "UNKNOWN"
    assert pass1["structural_impairment_at_t0"] == "EVIDENCE_PRESENT"
    assert pass2["structural_impairment_at_t0"] == "UNKNOWN"
    assert pass1["spans"]
    assert pass1["new_adverse_information_at_t0"] is True


def test_forbidden_market_fields_are_detected() -> None:
    clean = {"authority": dict(AUTHORITY_FALSE), "filing_receipt": {"accepted_at": "2017-01-01T00:00:00Z"}}
    assert forbidden_market_fields(clean) == []
    dirty = {"selection": {"price": 12.5}}
    assert "selection.price" in forbidden_market_fields(dirty)


def test_every_primary_family_has_frozen_phrases_and_quota() -> None:
    for family in PRIMARY_FAMILIES:
        assert LEXICON[family]
        assert QUOTAS[family]["source_target"] == 48
        assert json.dumps(LEXICON[family])
