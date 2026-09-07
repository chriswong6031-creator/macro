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


def _flat_rows(observations):
    """Mirror scripts/compile_capital_structure_covenant_terms.py's
    COVENANT_OBSERVATION_COLUMNS parquet flattening (Major 4): evaluate_health()
    feeds covenant_extraction_coverage() flat rows read back off disk, never
    the nested library shape compile_observations() returns in-process."""
    rows = []
    for o in observations:
        rows.append({
            "observation_id": o["observation_id"],
            "logical_observation_id": o["logical_observation_id"],
            "issuer_id": o["issuer_id"],
            "accession": o["filing"]["accession"],
            "form": o["filing"]["form"],
            "source_manifest_id": o["document"]["source_manifest_id"],
            "term_name": o["term"]["name"],
            "clause_id": o["clause"]["clause_id"],
            "state": o["state"]["disposition"],
            "available_at": o["point_in_time"]["available_at"],
            "correction_version": o["version"]["correction_version"],
            "observation_json": json.dumps(o, sort_keys=True),
        })
    return rows


def test_ingestion_health_reports_covenant_coverage_state_including_uncovered():
    manifest = _manifest()
    uncovered = covenant_extraction_coverage([], [manifest])
    assert uncovered["state"] == "uncovered"
    assert uncovered["eligible_exhibits"] == 1
    assert uncovered["observations"] == 0

    text = _text()
    observations = ct.compile_observations(manifest, text, generated_at="2026-09-06T00:00:00Z")
    flat = _flat_rows(observations)
    covered = covenant_extraction_coverage(flat, [manifest])
    assert covered["state"] == "covered"
    assert covered["observations"] == len(observations)
    assert covered["issuers_covered"] == 1
    assert covered["unavailable_terms"] + sum(
        1 for o in observations if o["state"]["disposition"] == "ambiguous"
    ) >= 1
    # the flat rows are what evaluate_health() actually passes -- assert the
    # coverage census reads the FLAT keys, not the nested library shape
    # (Blocker 1: the nested-shape read crashed on a real parquet row).
    assert covered["covered_manifests"] == 1


def test_stepped_schedule_does_not_raise_unboundlocalerror_on_the_real_fixture():
    """RED-first for BLOCKER-1 (review round 2): the unpatched code raised
    UnboundLocalError: cannot access local variable '_seq' at
    covenant_terms.py:302, because `_seq` was assigned only inside the final
    (single-value direct) branch but read unconditionally afterward -- so the
    very first stepped-schedule candidate (the elif branch) crashed before
    compile_observations() could return anything at all. Both real terms in
    this fixture ARE stepped schedules, so this exercises the crash directly."""
    manifest = _manifest()
    text = _text()
    observations = ct.compile_observations(manifest, text, generated_at="2026-09-06T00:00:00Z")
    assert len(observations) == len(ct.COVENANT_TERM_NAMES)


def test_stepped_schedule_is_a_direct_observation_with_the_current_step_and_full_grid():
    """BLOCKER-2 (DECIDED): stepped covenant schedules ARE what credit
    agreements state, so refusing them made the producer useless on real
    filings. Both terms in the committed Corsair fixture are stepped, closed-
    enum, real-filing evidence: assert each is 'direct' (never 'ambiguous'),
    carries the CURRENT step (selected against the filing's own as-of date,
    2022-12-02, per manifest.filing.filing_date) as the headline raw ratio,
    and retains the full measurement-period grid."""
    manifest = _manifest()
    text = _text()
    observations = ct.compile_observations(manifest, text, generated_at="2026-09-06T00:00:00Z")
    by_name = {o["term"]["name"]: o for o in observations}

    leverage = by_name["maximum_total_net_leverage_ratio"]
    assert leverage["state"]["disposition"] == "direct"
    assert leverage["state"]["reason"] is None
    # as of 2022-12-02 the most recently effective step is the row that starts
    # 2022-09-30 ("September 30, 2022  3.50 to 1.00"), not the very first row.
    assert leverage["reported"]["raw"] == "3.50 to 1.00"
    schedule = leverage["reported"]["schedule"]
    assert [row["ratio"] for row in schedule] == [
        "3.00 to 1.00", "3.50 to 1.00", "3.75 to 1.00",
        "3.50 to 1.00", "3.25 to 1.00", "3.00 to 1.00",
    ]
    assert schedule[-1]["period_end"] is None  # open-ended "and each fiscal quarter thereafter"
    assert schedule[0]["period_end"] == "2022-06-30"

    coverage = by_name["minimum_interest_coverage_ratio"]
    assert coverage["state"]["disposition"] == "direct"
    assert coverage["reported"]["raw"] == "3.00 to 1.00"
    assert len(coverage["reported"]["schedule"]) == 3

    # both stay a byte-exact transcription of their own locator span, and
    # reported == normalized still holds with the schedule field present.
    encoded = text.encode("utf-8")
    for obs in (leverage, coverage):
        locator = obs["evidence"]["spans"][0]["locator"]
        start, end = ct._locator_bounds(locator)
        assert encoded[start:end].decode("utf-8") == obs["reported"]["raw"]
        assert obs["reported"] == obs["normalized"]


def test_stepped_schedule_with_no_dates_at_all_is_still_ambiguous():
    """The ONLY remaining refusal case per the ruling: a grid whose header is
    found and which states more than one ratio value nearby, but no calendar
    date at all -- there is then no way to identify a "current" step, so it
    stays 'ambiguous' / stepped_schedule_no_measurement_period rather than
    guessing. A grid that DOES carry dates (real filings) is always resolved
    to a direct schedule -- this must never regress to blanket-refusing every
    stepped schedule again."""
    manifest = _manifest()
    text = (
        "7.11 Financial Covenants . (a) Consolidated Interest Coverage Ratio . "
        "Minimum Consolidated Interest Coverage Ratio shall not be less than "
        "3.00 to 1.00 or, if elected by the Borrower, 2.50 to 1.00."
    )
    observations = ct.compile_observations(manifest, text, generated_at="2026-09-06T00:00:00Z")
    coverage = next(o for o in observations if o["term"]["name"] == "minimum_interest_coverage_ratio")
    assert coverage["state"] == {"disposition": "ambiguous", "reason": "stepped_schedule_no_measurement_period"}
    assert coverage["reported"] == {"raw": None, "unit": None, "value": None}


def test_current_step_selection_is_a_step_function_of_the_row_start_dates():
    """Unit-level check of _select_current_step/_parse_schedule_rows against
    the exact Corsair leverage grid text, independent of the extraction-
    method plumbing above."""
    text = _text()
    rows = ct._parse_schedule_rows(text, ct._TERM_HEADERS["maximum_total_net_leverage_ratio"])
    assert len(rows) == 6
    import datetime as _dt
    current = ct._select_current_step(rows, _dt.date(2022, 12, 2))
    assert current["ratio"] == "3.50 to 1.00"
    # before the schedule starts: falls back to the earliest row, never crashes
    earliest = ct._select_current_step(rows, _dt.date(2000, 1, 1))
    assert earliest["ratio"] == "3.00 to 1.00"
    # unknown as-of date: same safe fallback
    unknown = ct._select_current_step(rows, None)
    assert unknown["ratio"] == "3.00 to 1.00"
