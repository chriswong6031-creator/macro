"""Tests for the filing-text covenant extraction producer (packet B-F09-5).

Real-filing evidence: Corsair Gaming, Inc. Amended and Restated Credit
Agreement, filed as Exhibit 10.1 to an 8-K, accession 0001564590-22-038930,
CIK 0001743759 (2022-12-02), pulled from public EDGAR
(https://www.sec.gov/Archives/edgar/data/1743759/000156459022038930/crsr-ex101_7.htm)
2026-09-06 to satisfy the packet's Step-0 premise check. Section 7.11
"Financial Covenants" states both a Minimum Consolidated Interest Coverage
Ratio and a Maximum Consolidated Total Net Leverage Ratio as explicit
numbers ("3.00 to 1.00" / "3.50 to 1.00" etc.) -- the two closed-enum terms
this fixture exercises end to end.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from engine.capital_structure import covenant_terms as ct
from engine.capital_structure.ingestion_health import covenant_extraction_coverage

FIXTURES = Path(__file__).parent / "fixtures" / "capital_structure"


def _manifest() -> dict:
    return json.loads((FIXTURES / "covenant_manifest_ledger.json").read_text())


def _amended_manifest() -> dict:
    return json.loads((FIXTURES / "covenant_amended_manifest_ledger.json").read_text())


def _text() -> str:
    return (FIXTURES / "covenant_credit_agreement_submission.txt").read_text(encoding="utf-8")


def test_covenant_enum_is_closed_and_unknown_term_names_are_refused():
    assert set(ct.COVENANT_TERM_NAMES) == {
        "maximum_total_net_leverage_ratio",
        "maximum_secured_net_leverage_ratio",
        "minimum_interest_coverage_ratio",
        "minimum_fixed_charge_coverage_ratio",
        "minimum_liquidity_amount",
        "restricted_payments_basket_amount",
    }
    with pytest.raises(ValueError):
        ct.covenant_term_type("made_up_term_not_in_enum")
    assert set(ct.COVENANT_TERM_SCOPES) == {
        "credit_agreement_financial_covenant_clause",
        "credit_agreement_negative_covenant_basket_clause",
    }


def test_extraction_without_an_exact_byte_locator_is_refused_not_stored():
    bad_locator = "complete_submission:doc=EX-10.1#1:section=section_7_11_financial_covenants:role=x"
    with pytest.raises(ct.CovenantSpanUnbound):
        ct.validate_locator(bad_locator, retained_byte_length=1000)


def test_locator_out_of_bounds_fails_closed_against_retained_bytes():
    locator = ct.build_locator("EX-10.1", 1, "section_7_11_financial_covenants",
                               "maximum_total_net_leverage_ratio", 10, 999999)
    with pytest.raises(ct.CovenantSpanUnbound):
        ct.validate_locator(locator, retained_byte_length=1250)


def test_absent_covenant_term_is_explicitly_unavailable_not_zero_and_not_inferred():
    manifest = _manifest()
    text = _text()
    observations = ct.compile_observations(manifest, text, generated_at="2026-09-06T00:00:00Z")
    absent = [o for o in observations if o["term"]["name"] == "minimum_liquidity_amount"]
    assert len(absent) == 1
    obs = absent[0]
    assert obs["state"]["disposition"] == "unavailable"
    assert obs["state"]["reason"] == "clause_absent_in_source"
    assert obs["reported"] == {"raw": None, "unit": None, "value": None}
    assert obs["normalized"] == {"raw": None, "unit": None, "value": None}


def test_reported_value_is_a_unit_preserving_transcription_of_the_stated_clause():
    manifest = _manifest()
    text = _text()
    observations = ct.compile_observations(manifest, text, generated_at="2026-09-06T00:00:00Z")
    direct = {o["term"]["name"]: o for o in observations if o["state"]["disposition"] == "direct"}
    assert "maximum_total_net_leverage_ratio" in direct
    assert "minimum_interest_coverage_ratio" in direct
    encoded = text.encode("utf-8")
    for obs in direct.values():
        locator = obs["evidence"]["spans"][0]["locator"]
        start, end = ct._locator_bounds(locator)
        substring = encoded[start:end].decode("utf-8")
        assert substring == obs["reported"]["raw"]
        assert obs["reported"] == obs["normalized"]  # no rounding, no derived value


def test_re_extraction_of_the_same_accession_appends_a_correction_and_keeps_the_prior_row():
    manifest = _manifest()
    text = _text()
    v1 = ct.compile_observations(manifest, text, generated_at="2026-09-06T00:00:00Z")
    text_v2 = text.replace("3.00 to 1.00", "3.10 to 1.00", 1)
    v2 = ct.compile_observations(manifest, text_v2, generated_at="2026-09-07T00:00:00Z",
                                  prior_observations=v1)
    changed = [o for o in v2 if o["version"]["correction_version"] == 2]
    assert len(changed) >= 1
    corrected = changed[0]
    prior = next(o for o in v1 if o["logical_observation_id"] == corrected["logical_observation_id"])
    assert corrected["version"]["correction_of"] == prior["observation_id"]
    assert corrected["relationships"]["supersedes"] == [prior["observation_id"]]
    # both rows persist (the caller keeps v1 + v2 in the parquet; simulate that here)
    combined = v1 + v2
    assert prior["observation_id"] in {o["observation_id"] for o in combined}
    assert corrected["observation_id"] in {o["observation_id"] for o in combined}


def test_identical_re_extraction_cannot_mint_a_phantom_correction():
    manifest = _manifest()
    text = _text()
    v1 = ct.compile_observations(manifest, text, generated_at="2026-09-06T00:00:00Z")
    v2 = ct.compile_observations(manifest, text, generated_at="2026-09-08T00:00:00Z",
                                  prior_observations=v1)
    for obs in v2:
        assert obs["version"]["correction_version"] == 1


def test_amended_filing_creates_a_new_logical_observation_that_amends_and_never_overwrites_the_prior():
    manifest = _manifest()
    amended = _amended_manifest()
    text = _text()
    prior_obs = ct.compile_observations(manifest, text, generated_at="2026-09-06T00:00:00Z")
    prior_direct = next(o for o in prior_obs if o["state"]["disposition"] == "direct")
    prior_snapshot = json.loads(json.dumps(prior_direct))

    new_candidates = ct.extract_candidates(amended, text)
    new_candidate = next(c for c in new_candidates if c["term"]["name"] == prior_direct["term"]["name"])
    amended_obs = ct.link_amendment(new_candidate, prior_direct["observation_id"],
                                     generated_at="2026-12-09T16:30:00Z")

    assert amended_obs["logical_observation_id"] != prior_direct["logical_observation_id"]
    assert amended_obs["relationships"]["amends"] == [prior_direct["observation_id"]]
    # the prior observation is left byte-identical
    assert prior_direct == prior_snapshot


def test_correction_available_at_must_advance():
    manifest = _manifest()
    text = _text()
    v1 = ct.compile_observations(manifest, text, generated_at="2026-09-06T00:00:00Z")
    text_v2 = text.replace("3.00 to 1.00", "3.10 to 1.00", 1)
    with pytest.raises(ValueError):
        ct.compile_observations(manifest, text_v2, generated_at="2026-09-05T00:00:00Z",
                                 prior_observations=v1)


def test_real_issuer_covenant_terms_extract_end_to_end_from_the_committed_fixture():
    manifest = _manifest()
    text = _text()
    observations = ct.compile_observations(manifest, text, generated_at="2026-09-06T00:00:00Z")
    direct = [o for o in observations if o["state"]["disposition"] == "direct"]
    assert len(direct) >= 1
    for obs in direct:
        assert obs["filing"]["accession"] == "0001564590-22-038930"
        assert obs["document"]["content_sha256"] == manifest["document"]["content_sha256"]
        locator = obs["evidence"]["spans"][0]["locator"]
        start, end = ct._locator_bounds(locator)
        assert 0 <= start < end <= len(text.encode("utf-8"))


def test_observation_carries_zero_authority_keys():
    manifest = _manifest()
    text = _text()
    observations = ct.compile_observations(manifest, text, generated_at="2026-09-06T00:00:00Z")
    for obs in observations:
        ct._assert_zero_authority(obs)  # must not raise


def test_producer_writes_no_second_store_and_only_the_known_artifact():
    assert ct.__file__.endswith("covenant_terms.py")
    import inspect
    source = inspect.getsource(ct)
    assert "sqlite3" not in source
    assert "CREATE TABLE" not in source
    from engine.capital_structure.ingestion_health import COVENANT_OBSERVATION_FILENAME
    assert COVENANT_OBSERVATION_FILENAME == "covenant_term_observations.parquet"


def test_no_headroom_or_derived_capacity_field_exists_in_the_contract():
    manifest = _manifest()
    text = _text()
    observations = ct.compile_observations(manifest, text, generated_at="2026-09-06T00:00:00Z")
    for obs in observations:
        ct.assert_no_derived_capacity_field(obs)  # must not raise
    import inspect
    source = inspect.getsource(ct)
    assert "def headroom" not in source
    assert "def capacity" not in source


def test_ingestion_health_reports_covenant_coverage_state_including_uncovered():
    manifest = _manifest()
    uncovered = covenant_extraction_coverage([], [manifest])
    assert uncovered["state"] == "uncovered"
    assert uncovered["eligible_exhibits"] == 1
    assert uncovered["observations"] == 0

    text = _text()
    observations = ct.compile_observations(manifest, text, generated_at="2026-09-06T00:00:00Z")
    covered = covenant_extraction_coverage(observations, [manifest])
    assert covered["state"] == "covered"
    assert covered["observations"] == len(observations)
    assert covered["issuers_covered"] == 1
    assert covered["unavailable_terms"] >= 1
