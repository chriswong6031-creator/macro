"""Composer tests for the US capital_structure workspace (F01 / R4).

RED-first: each degraded condition must produce the correct TYPED state and
never a zero / neutral / calm default. Covers: the COMPUTATION_REFUSED
headline shape (architecture 10.3 DOES define a refinancing-pressure x
balance-sheet-resilience/market-access blueprint, but the scoped owner
artifact -- an event/filing classification projection -- explicitly types the
instrument-level substance both axes would need as unavailable, at both the
whole-projection level and every issuer record; see
capital_structure.py's module docstring for why this differs from
monetary_policy's / liquidity_central_banks' NOT_APPLICABLE precedent), the
nightly-cadence freshness law (CURRENT/LATE_WITHIN_TOLERANCE/STALE_SOURCE
boundaries), the owner source_status no-look-ahead downgrade law, the single-
pass record census (hand-computable aggregation correctness), the owner's own
per-record contradiction_ids as the composer's only contradiction signal, the
data-driven typed NOT_COVERED passthrough of the owner's own `unavailable`
list, digest determinism with a genuinely-consumed-field mutation and an
unconsumed-field negative control, a prose scan for raw enum-token leaks,
zh-narrative integrity, schema validation, the "never republish the record
set" law, and a real-owner-artifact build.

    python3 -m pytest tests/test_macro_workspace_capital_structure.py -x -q
"""
from __future__ import annotations

import copy
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from engine.market_os.macro_workspaces import capital_structure, contract  # noqa: E402

BUILT_AT = "2026-09-04T12:00:00Z"
GENERATED_AT = "2026-09-04T06:19:48.233321Z"
AS_OF = "2026-09-04T06:14:34.409360Z"
REAL_PROJECTION_PATH = ROOT / "data" / "capital_structure" / "projection.json"

_UNAVAILABLE = [
    "active_instrument_overhang", "cash_runway", "financing_probability",
    "fully_diluted_shares", "instruments", "normalized_terms",
    "offering_ability", "remaining_capacity",
]


# --------------------------------------------------------------------------- #
# fixtures (trimmed, representative subsets of the real owner artifact)
# --------------------------------------------------------------------------- #
def _base_authority() -> dict:
    return {
        "entry_authority": False, "is_context_only": True, "prophet_authority": False,
        "rank_authority": False, "sizing_authority": False,
    }


def _base_coverage() -> dict:
    return {
        "age_hours": None,
        "classified_event_count": 2717,
        "coverage_claim": "registration_allowlist_plus_issuer_scoped_reconciliation",
        "deferred_event_count": 3584,
        "edge_count": 581,
        "event_count": 6996,
        "freshness": "stale",
        "freshness_sla_hours": 6.0,
        "generation_age_hours": 0.087173,
        "generation_freshness": "fresh",
        "generation_freshness_sla_hours": 30,
        "horizon_reason_codes": [
            "latest_expected_index_not_observed", "latest_filings_observation_missing",
        ],
        "horizon_state": "degraded_discovery",
        "issuer_count": 2374,
        "reason": "event_state_only_terms_and_issuer_state_unavailable",
        "review_count": 4772,
        "source_status": "ok",
        "state": "partial",
    }


def _record(issuer_id, cik, ticker, *, classification_state, family, review_state,
            relationships=None, correction_of=None, contradiction_ids=None,
            coverage_state="partial") -> dict:
    relationships = relationships if relationships is not None else []
    contradiction_ids = contradiction_ids if contradiction_ids is not None else []
    return {
        "as_of": AS_OF,
        "authority": _base_authority(),
        "coverage": {
            "classified_event_count": 1 if classification_state == "classified" else 0,
            "contradiction_ids": contradiction_ids,
            "deferred_event_count": 0 if classification_state == "classified" else 1,
            "event_count": 1,
            "review_count": 1 if review_state == "pending" else 0,
            "review_queue_semantics": "current_rebuild_not_historical_ledger",
            "state": coverage_state,
        },
        "generated_at": GENERATED_AT,
        "identity": {"aliases": [], "cik": cik, "observed_tickers": [ticker], "ticker": ticker},
        "issuer_id": issuer_id,
        "latest_observed_event": {
            "accession": "0001104659-26-000001",
            "classification_state": classification_state,
            "clocks": {
                "mastermind_observed_at": "2026-08-28T03:50:45.203698Z",
                "projection_generated_at": GENERATED_AT,
                "sec_accepted_at": "2026-08-01T20:47:52Z",
            },
            "correction_of": correction_of,
            "correction_version": 1,
            "defer_reason": None if classification_state == "classified" else "current_report_requires_document_content",
            "event_id": f"event:cs:{issuer_id}",
            "family": family,
            "filing_date": "2026-08-01",
            "form": "8-K",
            "lifecycle_state": "filed",
            "relationships": relationships,
            "review": {"items": [], "queue_ids": [], "state": review_state},
            "source": {"filing_url": "https://www.sec.gov/x", "source_id": "0001104659-26-000001",
                       "source_system": "sec_edgar"},
            "subtype": "current_report_candidate",
        },
        "schema": "capital_structure.projection.v1",
        "timeline": [],
        "unavailable": list(_UNAVAILABLE),
        "what_changed": [],
    }


def _base_records() -> list:
    # Hand-computable fixture (4 issuers):
    #   classified:            #1, #3  -> 2
    #   pending_review:        #2, #4  -> 2
    #   shelf family:          #1      -> 1
    #   with_relationships:    #2      -> 1
    #   correction_present:    #3      -> 1
    #   contradiction_flagged: #3      -> 1
    return [
        _record("sec:cik:0000001750", "1750", "AIR",
                classification_state="classified", family="shelf", review_state="none"),
        _record("sec:cik:0000002000", "2000", "BBB",
                classification_state="deferred_ambiguous_content", family="other", review_state="pending",
                relationships=[{"kind": "guarantor", "issuer_id": "sec:cik:0000002001"}]),
        _record("sec:cik:0000003000", "3000", "CCC",
                classification_state="classified", family="other", review_state="none",
                correction_of="event:cs:priorevent123", contradiction_ids=["contradiction:cs:abc123"]),
        _record("sec:cik:0000004000", "4000", "DDD",
                classification_state="not_applicable", family="corporate_action", review_state="pending"),
    ]


def _base_projection() -> dict:
    return {
        "as_of": AS_OF,
        "authority": _base_authority(),
        "coverage": _base_coverage(),
        "generated_at": GENERATED_AT,
        "generation_id": "projection:cs:a9c84d0f7bf3619559cf4eb4",
        "projection_version": "capital-structure-event-projection/1.0.0",
        "records": _base_records(),
        "schema": "capital_structure.projection_bundle.v1",
        "source_receipt": {
            "artifact_hashes": {
                "event_edges": "ad32940ed852297ecf21900bd691e09cfe537ff97b42c9b6b70f5752eefee6bc",
                "event_versions": "b61c16452fbd95abe158b7b02e9221857a5331b51a4ab4f7a534fd9b57be39b3",
                "review_queue": "bb139ff39dbc740bfa4fe5febb1feace627465528b921d1037b70ba1ad0938c8",
            },
            "as_of": AS_OF,
            "generation_id": "generation:cs:cb2f24b4fd95e25c02de5409",
            "source_ledger_receipt": {
                "form_policy_version": "capital-structure-sec-form-policy/1.2.0",
                "immutable_prefix": True,
                "prefix_sha256": "e0fc1cbcf1dbbe52501310c2bfb1df38a13222eaa37b2f8543ddf41a7a122383",
                "record_count": 22838,
                "schema": "capital_structure.source_ledger_receipt.v1",
            },
        },
        "unavailable": list(_UNAVAILABLE),
    }


def _compose(projection=None, **kw) -> dict:
    return capital_structure.compose(
        projection if projection is not None else _base_projection(),
        built_at=BUILT_AT, **kw,
    )


def _metric(snapshot: dict, metric_id: str) -> dict:
    return next(m for m in snapshot["metrics"]["items"] if m["metric_id"] == metric_id)


def _required(snapshot: dict, cid: str) -> dict:
    return next(c for c in snapshot["availability"]["required"] if c["component_id"] == cid)


# --------------------------------------------------------------------------- #
# healthy baseline
# --------------------------------------------------------------------------- #
def test_baseline_workspace_and_region() -> None:
    snap = _compose()
    assert snap["workspace"]["id"] == "capital_structure"
    assert snap["region"]["code"] == "US"
    assert snap["generation"]["producer"] == "engine.market_os.macro_workspaces.capital_structure"


def test_baseline_required_sources_current() -> None:
    snap = _compose()
    for cid in ("event_coverage_census", "issuer_records"):
        r = _required(snap, cid)
        assert r["freshness"] == "CURRENT", (cid, r)
        assert r["status"] == "PRESENT"
    assert snap["availability"]["state"] == "CURRENT"
    assert snap["availability"]["coverage_ratio"] == 1.0


def test_baseline_owner_coverage_state_and_horizon_state_surface_in_reasons() -> None:
    # the real owner artifact discloses coverage.state="partial" and
    # horizon_state="degraded_discovery" -- both neither block is "complete"/
    # "nominal", so both must surface as diagnostic reasons even though the
    # required components themselves read CURRENT.
    snap = _compose()
    reasons = snap["availability"]["reasons"]
    assert any(r.startswith("owner_coverage_state=partial") for r in reasons)
    assert any(r.startswith("owner_horizon_state=degraded_discovery") for r in reasons)


# --------------------------------------------------------------------------- #
# COMPUTATION_REFUSED headline / empty axes / empty drivers
# --------------------------------------------------------------------------- #
def test_headline_is_computation_refused_by_design() -> None:
    snap = _compose()
    h = snap["headline"]
    assert h["state_id"] is None
    assert h["status"] == "ABSENT"
    assert h["null_reason"] == "COMPUTATION_REFUSED"
    assert h["quadrant"] == {"x": None, "y": None, "x_status": "ABSENT", "y_status": "ABSENT"}
    assert h["nearest_boundary"]["null_reason"] == "COMPUTATION_REFUSED"
    assert h["one_month_vector"]["null_reason"] == "COMPUTATION_REFUSED"
    assert h["hysteresis"]["applied"] is False
    assert "quadrant" in h["hysteresis"]["note"]


def test_axes_items_is_empty_by_design() -> None:
    snap = _compose()
    assert snap["axes"]["items"] == []


def test_drivers_are_empty_by_design() -> None:
    snap = _compose()
    assert snap["drivers"] == {"rate_side": [], "balance_sheet": []}


# --------------------------------------------------------------------------- #
# owner top-level coverage census: pass-through, no computation
# --------------------------------------------------------------------------- #
def test_owner_coverage_passthrough_metrics() -> None:
    snap = _compose()
    assert _metric(snap, "cs_issuer_count")["value"] == 2374
    assert _metric(snap, "cs_event_count")["value"] == 6996
    assert _metric(snap, "cs_classified_event_count")["value"] == 2717
    assert _metric(snap, "cs_deferred_event_count")["value"] == 3584
    assert _metric(snap, "cs_review_count")["value"] == 4772
    assert _metric(snap, "cs_edge_count")["value"] == 581
    assert _metric(snap, "cs_owner_generation_age_hours")["value"] == pytest.approx(0.087173)
    assert _metric(snap, "cs_coverage_state")["value"] == "partial"
    assert _metric(snap, "cs_event_detection_freshness_state")["value"] == "stale"
    assert _metric(snap, "cs_generation_freshness_state")["value"] == "fresh"
    assert _metric(snap, "cs_source_status")["value"] == "ok"
    assert _metric(snap, "cs_horizon_state")["value"] == "degraded_discovery"


def test_event_classification_rate_and_review_backlog_ratio() -> None:
    snap = _compose()
    rate = _metric(snap, "cs_event_classification_rate")
    assert rate["value"] == pytest.approx(2717 / 6996)
    assert rate["status"] == "PRESENT"
    backlog = _metric(snap, "cs_review_backlog_ratio")
    assert backlog["value"] == pytest.approx(4772 / 6996)


def test_ratio_refused_when_event_count_zero() -> None:
    p = _base_projection()
    p["coverage"]["event_count"] = 0
    snap = _compose(p)
    rate = _metric(snap, "cs_event_classification_rate")
    assert rate["value"] is None
    assert rate["status"] == "ABSENT"
    assert rate["null_reason"] == "COMPUTATION_REFUSED"


# --------------------------------------------------------------------------- #
# single-pass record census: hand-computable aggregation correctness
# --------------------------------------------------------------------------- #
def test_aggregate_counts_match_hand_computed_fixture() -> None:
    snap = _compose()
    assert _metric(snap, "cs_issuer_records_count")["value"] == 4
    assert _metric(snap, "cs_issuer_latest_event_classified_count")["value"] == 2
    assert _metric(snap, "cs_issuer_pending_review_count")["value"] == 2
    assert _metric(snap, "cs_issuer_shelf_registration_count")["value"] == 1
    assert _metric(snap, "cs_issuer_with_relationships_count")["value"] == 1
    assert _metric(snap, "cs_issuer_correction_present_count")["value"] == 1
    assert _metric(snap, "cs_issuer_contradiction_flagged_count")["value"] == 1


def test_issuer_latest_event_classified_share() -> None:
    snap = _compose()
    m = _metric(snap, "cs_issuer_latest_event_classified_share")
    assert m["value"] == pytest.approx(0.5)
    m2 = _metric(snap, "cs_issuer_shelf_registration_share")
    assert m2["value"] == pytest.approx(0.25)


def test_share_metrics_refused_when_zero_records() -> None:
    p = _base_projection()
    p["records"] = []
    snap = _compose(p)
    m = _metric(snap, "cs_issuer_latest_event_classified_share")
    assert m["value"] is None
    assert m["null_reason"] == "COMPUTATION_REFUSED"
    # but the raw count itself is an honest zero, not a fabricated absence
    count = _metric(snap, "cs_issuer_records_count")
    assert count["value"] == 0
    assert count["status"] == "PRESENT"
    assert count["null_reason"] is None


# --------------------------------------------------------------------------- #
# owner-native contradiction: coverage.contradiction_ids only
# --------------------------------------------------------------------------- #
def test_contradiction_fires_when_owner_flags_contradiction_ids() -> None:
    snap = _compose()
    c = snap["availability"]["contradiction"]
    assert c["present"] is True
    assert c["kind"] == "issuer_event_contradiction"
    assert c["components"] == ["cs_issuer_contradiction_flagged_count"]
    assert any("contradiction=issuer_event_contradiction" in r for r in snap["availability"]["reasons"])
    m = _metric(snap, "cs_issuer_contradiction_flagged_count")
    assert m["status"] == "DISAGREEMENT"
    assert m["value"] == 1  # typed disagreement, not censored
    assert any(i["implication_id"] == "contradiction_issuer_event_contradiction"
               for i in snap["implications"]["items"])


def test_contradiction_silent_when_no_contradiction_ids() -> None:
    records = _base_records()
    records[2]["coverage"]["contradiction_ids"] = []
    p = _base_projection()
    p["records"] = records
    snap = _compose(p)
    assert snap["availability"]["contradiction"]["present"] is False
    m = _metric(snap, "cs_issuer_contradiction_flagged_count")
    assert m["value"] == 0
    assert m["status"] == "PRESENT"


# --------------------------------------------------------------------------- #
# owner honesty passthrough: the `unavailable` list is data-driven, typed
# NOT_COVERED, never masked
# --------------------------------------------------------------------------- #
def test_unavailable_passthrough_emits_typed_not_covered_metric_per_name() -> None:
    snap = _compose()
    for name in _UNAVAILABLE:
        m = _metric(snap, f"cs_{name}")
        assert m["value"] is None
        assert m["status"] == "ABSENT"
        assert m["null_reason"] == "NOT_COVERED"
        assert m["freshness"] == "NOT_COVERED"
        assert name in m["transformation"]
    assert any(i["implication_id"] == "unavailable_capacities_disclosure"
               for i in snap["implications"]["items"])


def test_unavailable_empty_list_emits_no_not_covered_metrics() -> None:
    p = _base_projection()
    p["unavailable"] = []
    snap = _compose(p)
    ids = {m["metric_id"] for m in snap["metrics"]["items"]}
    assert not any(mid.startswith(f"cs_{name}") for name in _UNAVAILABLE for mid in ids)
    assert not any(i["implication_id"] == "unavailable_capacities_disclosure"
                   for i in snap["implications"]["items"])


def test_unavailable_list_is_data_driven_not_hardcoded() -> None:
    p = _base_projection()
    p["unavailable"] = ["some_future_capacity_name"]
    snap = _compose(p)
    m = _metric(snap, "cs_some_future_capacity_name")
    assert m["null_reason"] == "NOT_COVERED"


# --------------------------------------------------------------------------- #
# typed degraded states (never zero / neutral / calm)
# --------------------------------------------------------------------------- #
def test_missing_coverage_block_is_typed_source_failed() -> None:
    p = _base_projection()
    del p["coverage"]
    snap = _compose(p)
    r = _required(snap, "event_coverage_census")
    assert r["freshness"] == "SOURCE_FAILED"
    assert r["status"] == "ABSENT"
    assert r["null_reason"] == "SOURCE_FAILED"
    m = _metric(snap, "cs_issuer_count")
    assert m["value"] is None and m["status"] == "ABSENT" and m["null_reason"] == "SOURCE_FAILED"
    # the issuer_records component and record census are unaffected -- freshness
    # must reflect THIS component's own presence only.
    r2 = _required(snap, "issuer_records")
    assert r2["status"] == "PRESENT"


def test_missing_records_block_is_typed_source_failed() -> None:
    p = _base_projection()
    del p["records"]
    snap = _compose(p)
    r = _required(snap, "issuer_records")
    assert r["freshness"] == "SOURCE_FAILED"
    assert r["status"] == "ABSENT"
    m = _metric(snap, "cs_issuer_records_count")
    assert m["value"] is None
    assert m["null_reason"] == "SOURCE_FAILED"
    # sibling required component (coverage) is unaffected
    r2 = _required(snap, "event_coverage_census")
    assert r2["status"] == "PRESENT"


def test_empty_records_list_reads_present_with_honest_zero_counts() -> None:
    # A published-but-empty records array is a real, legitimate owner state
    # (zero issuers this cycle) -- distinct from a MISSING records key, which
    # is a hard failure. "Missing never becomes zero" cuts both ways: an
    # honestly-published zero must not be censored into ABSENT either.
    p = _base_projection()
    p["records"] = []
    snap = _compose(p)
    r = _required(snap, "issuer_records")
    assert r["status"] == "PRESENT"
    assert r["freshness"] == "CURRENT"
    m = _metric(snap, "cs_issuer_records_count")
    assert m["value"] == 0
    assert m["status"] == "PRESENT"
    assert m["null_reason"] is None


def test_snapshot_with_projection_missing_entirely_still_validates() -> None:
    snap = contract.finalize(capital_structure.compose({}, built_at=BUILT_AT))
    contract.validate(snap)
    assert snap["availability"]["state"] == "SOURCE_FAILED"
    assert snap["availability"]["coverage_ratio"] == 0.0


def test_malformed_unavailable_entries_are_skipped_not_crashed() -> None:
    p = _base_projection()
    p["unavailable"] = ["real_name", 123, None, "", {"nested": True}]
    snap = _compose(p)
    m = _metric(snap, "cs_real_name")
    assert m["null_reason"] == "NOT_COVERED"
    # non-string / empty entries never produce a metric
    ids = {m2["metric_id"] for m2 in snap["metrics"]["items"]}
    assert "cs_123" not in ids
    assert "cs_None" not in ids


# --------------------------------------------------------------------------- #
# nightly-cadence freshness law: CURRENT / LATE_WITHIN_TOLERANCE / STALE.
# BUILT_AT is held fixed (never overridden -- the composer never reads a wall
# clock) and generated_at is varied instead.
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("generated_at,expected", [
    ("2026-09-04T12:00:00Z", "CURRENT"),               # age 0h
    ("2026-09-03T00:00:00Z", "CURRENT"),                # age 36h (boundary)
    ("2026-09-02T23:00:00Z", "LATE_WITHIN_TOLERANCE"),  # age 37h
    ("2026-09-02T12:00:00Z", "LATE_WITHIN_TOLERANCE"),  # age 48h (boundary)
    ("2026-09-02T11:00:00Z", "STALE_SOURCE"),           # age 49h
])
def test_nightly_freshness_tiers(generated_at: str, expected: str) -> None:
    p = _base_projection()
    p["generated_at"] = generated_at
    snap = _compose(p)
    r = _required(snap, "event_coverage_census")
    assert r["freshness"] == expected


def test_generated_at_after_built_at_is_source_failed() -> None:
    p = _base_projection()
    p["generated_at"] = "2026-09-05T00:00:00Z"  # AFTER BUILT_AT (2026-09-04T12:00:00Z)
    snap = _compose(p)
    r = _required(snap, "event_coverage_census")
    assert r["freshness"] == "SOURCE_FAILED"


def test_owner_source_status_downgrades_freshness_never_upgrades() -> None:
    p = _base_projection()
    p["coverage"]["source_status"] = "degraded"  # not "ok"
    snap = _compose(p)
    r = _required(snap, "event_coverage_census")
    assert r["freshness"] == "STALE_SOURCE"
    assert snap["availability"]["state"] != "CURRENT"
    assert any(rz.startswith("owner_source_status=degraded") for rz in snap["availability"]["reasons"])


def test_owner_source_status_ok_never_upgrades_a_genuinely_stale_read() -> None:
    p = _base_projection()
    p["generated_at"] = "2026-09-02T11:00:00Z"  # already STALE_SOURCE on date math
    p["coverage"]["source_status"] = "ok"
    snap = _compose(p)
    r = _required(snap, "event_coverage_census")
    assert r["freshness"] == "STALE_SOURCE"


# --------------------------------------------------------------------------- #
# metric identity
# --------------------------------------------------------------------------- #
def test_metric_ids_are_unique_and_exact_count() -> None:
    snap = _compose()
    ids = [m["metric_id"] for m in snap["metrics"]["items"]]
    assert len(ids) == len(set(ids))
    assert len(ids) == 23 + len(_UNAVAILABLE)


def test_no_single_issuer_metric_is_republished() -> None:
    # composer law: aggregate, never republish the record set -- no per-issuer
    # identity (ticker/cik/issuer_id) may leak into the published snapshot.
    snap = _compose()
    blob = json.dumps(snap)
    for needle in ("AIR", "0000001750", "sec:cik:0000003000", "BBB", "CCC", "DDD"):
        assert needle not in blob, needle


# --------------------------------------------------------------------------- #
# changes / method-version comparability
# --------------------------------------------------------------------------- #
def _prior(method=capital_structure.METHOD_VERSION, issuer_count=2300,
           gen="capital_structure-US-deadbeefdeadbeef") -> dict:
    prior = _compose()
    prior["headline"]["method_version"] = method
    prior["headline"]["effective_date"] = "2026-08-28T00:00:00Z"
    prior["generation"]["generation_id"] = gen
    for m in prior["metrics"]["items"]:
        if m["metric_id"] == "cs_issuer_count":
            m["value"] = issuer_count
    return prior


def test_changes_no_prior_yields_warmup() -> None:
    snap = _compose()
    assert snap["changes"]["comparability"] == "NO_PRIOR"
    assert snap["changes"]["null_reason"] == "WARMUP"


def test_changes_method_mismatch_refuses_numeric_comparison() -> None:
    snap = _compose(prior_snapshot=_prior(method="capital_structure.compose.v0"))
    assert snap["changes"]["comparability"] == "METHOD_CHANGED"
    assert snap["changes"]["deltas"] == []
    assert snap["changes"]["null_reason"] == "COMPUTATION_REFUSED"


def test_changes_comparable_prior_produces_deltas() -> None:
    snap = _compose(prior_snapshot=_prior(issuer_count=2300))
    assert snap["changes"]["comparability"] == "COMPARABLE"
    ids = {d["metric_id"] for d in snap["changes"]["deltas"]}
    assert ids == set(capital_structure._TRACKED_CHANGE_METRICS)
    d = next(x for x in snap["changes"]["deltas"] if x["metric_id"] == "cs_issuer_count")
    assert d["prior_value"] == 2300
    assert d["current_value"] == 2374
    assert d["delta"] == pytest.approx(74)


# --------------------------------------------------------------------------- #
# corrections / supersession honesty
# --------------------------------------------------------------------------- #
def test_corrections_none_for_first_print() -> None:
    snap = _compose()
    assert snap["corrections"]["correction_state"] == "none"
    assert snap["corrections"]["predecessor_generation_id"] is None


def test_corrections_superseded_when_same_period_value_changes() -> None:
    p = _base_projection()
    prior_snap = contract.finalize(capital_structure.compose(p, built_at=BUILT_AT))
    p2 = copy.deepcopy(p)
    p2["coverage"]["issuer_count"] = 9999  # same as_of, revised value
    snap2 = capital_structure.compose(p2, built_at=BUILT_AT, prior_snapshot=prior_snap)
    assert snap2["corrections"]["correction_state"] == "superseded"
    assert snap2["corrections"]["changed_fingerprints"]
    assert snap2["corrections"]["predecessor_generation_id"] == prior_snap["generation"]["generation_id"]


def test_corrections_none_when_reference_period_advances() -> None:
    p = _base_projection()
    prior_snap = contract.finalize(capital_structure.compose(p, built_at=BUILT_AT))
    p2 = copy.deepcopy(p)
    p2["as_of"] = "2026-09-05T06:14:34.409360Z"  # new observation, not a revision
    p2["coverage"]["issuer_count"] = 9999
    snap2 = capital_structure.compose(p2, built_at=BUILT_AT, prior_snapshot=prior_snap)
    assert snap2["corrections"]["correction_state"] == "none"


# --------------------------------------------------------------------------- #
# digest determinism (contract.py's content_digest excludes generation/build
# provenance; identical owner input -> identical digest). Includes a
# genuinely-consumed-field mutation AND unconsumed-field negative controls.
# --------------------------------------------------------------------------- #
def test_digest_is_deterministic_across_identical_input() -> None:
    snap1 = contract.finalize(_compose())
    snap2 = contract.finalize(_compose())
    assert snap1["generation"]["content_sha256"] == snap2["generation"]["content_sha256"]
    assert snap1["generation"]["generation_id"] == snap2["generation"]["generation_id"]


def test_digest_unaffected_by_code_version() -> None:
    snap1 = contract.finalize(_compose(code_version="abc123"))
    snap2 = contract.finalize(_compose(code_version="def456"))
    assert snap1["generation"]["content_sha256"] == snap2["generation"]["content_sha256"]


def test_digest_changes_when_consumed_coverage_field_changes() -> None:
    snap1 = contract.finalize(_compose())
    p2 = _base_projection()
    p2["coverage"]["issuer_count"] = 1111  # genuinely consumed
    snap2 = contract.finalize(_compose(p2))
    assert snap1["generation"]["content_sha256"] != snap2["generation"]["content_sha256"]


def test_digest_changes_when_consumed_record_field_changes() -> None:
    snap1 = contract.finalize(_compose())
    p2 = _base_projection()
    p2["records"][0]["latest_observed_event"]["classification_state"] = "deferred_ambiguous_content"  # genuinely consumed
    snap2 = contract.finalize(_compose(p2))
    assert snap1["generation"]["content_sha256"] != snap2["generation"]["content_sha256"]


def test_digest_unaffected_by_unconsumed_source_receipt_artifact_hashes() -> None:
    snap1 = contract.finalize(_compose())
    p3 = _base_projection()
    p3["source_receipt"]["artifact_hashes"]["event_edges"] = "0" * 64  # never read by this composer
    snap3 = contract.finalize(_compose(p3))
    assert snap1["generation"]["content_sha256"] == snap3["generation"]["content_sha256"]


def test_digest_unaffected_by_unconsumed_record_identity_field() -> None:
    snap1 = contract.finalize(_compose())
    p3 = _base_projection()
    p3["records"][0]["identity"]["ticker"] = "ZZZZ"  # never read by this composer
    p3["records"][0]["latest_observed_event"]["accession"] = "9999999999-99-999999"
    snap3 = contract.finalize(_compose(p3))
    assert snap1["generation"]["content_sha256"] == snap3["generation"]["content_sha256"]


def test_digest_unaffected_by_unconsumed_timeline_content() -> None:
    snap1 = contract.finalize(_compose())
    p3 = _base_projection()
    p3["records"][0]["timeline"] = [{"anything": "this composer never reads timeline"}]
    snap3 = contract.finalize(_compose(p3))
    assert snap1["generation"]["content_sha256"] == snap3["generation"]["content_sha256"]


# --------------------------------------------------------------------------- #
# schema validation
# --------------------------------------------------------------------------- #
def test_baseline_snapshot_validates_against_the_closed_contract() -> None:
    snap = contract.finalize(_compose())
    contract.validate(snap)  # raises ContractError on any violation
    assert snap["authority"]["can_size"] is False
    assert snap["authority"]["can_execute"] is False
    assert snap["authority"]["can_originate_signal"] is False
    assert snap["authority"]["can_rank"] is False


def test_degraded_snapshot_still_validates() -> None:
    p = _base_projection()
    del p["coverage"]
    p["records"] = p["records"][:1]
    p["records"][0]["coverage"]["contradiction_ids"] = ["contradiction:cs:zzz"]
    snap = contract.finalize(capital_structure.compose(p, built_at=BUILT_AT))
    contract.validate(snap)


def test_owner_authority_claim_exceeds_composer_ceiling_disclosed() -> None:
    p = _base_projection()
    p["authority"]["rank_authority"] = True
    snap = contract.finalize(capital_structure.compose(p, built_at=BUILT_AT))
    contract.validate(snap)
    # the published contract authority stays fixed regardless of the owner's claim
    assert snap["authority"]["can_rank"] is False
    assert any(i["implication_id"] == "owner_authority_claim_exceeds_composer_ceiling"
               for i in snap["implications"]["items"])


def test_owner_authority_agrees_disclosure_when_all_false() -> None:
    snap = _compose()
    assert any(i["implication_id"] == "owner_authority_disclosure_agrees"
               for i in snap["implications"]["items"])


# --------------------------------------------------------------------------- #
# disclosure prose: reader language only -- never a raw closed-vocabulary
# enum token (PRESENT/SOURCE_FAILED/etc.) inside a human-readable field.
# --------------------------------------------------------------------------- #
_RAW_ENUM_TOKENS = frozenset({
    "CURRENT", "LATE_WITHIN_TOLERANCE", "STALE_SOURCE", "NOT_YET_RELEASED",
    "SOURCE_FAILED", "RIGHTS_BLOCKED", "NOT_COVERED", "HISTORICAL_AS_KNOWN", "SIMULATED",
    "UNKNOWN", "NOT_APPLICABLE", "INSUFFICIENT_HISTORY", "WARMUP",
    "REVISION_PENDING_REBUILD", "DISAGREEMENT", "COMPUTATION_REFUSED", "OUT_OF_REGION",
    "PRESENT", "PARTIAL", "ABSENT",
})
_PROSE_KEYS = ("en", "zh", "note", "transformation")


def _find_raw_token_leaks(node, path: str = "$") -> list[tuple[str, str, str]]:
    leaks: list[tuple[str, str, str]] = []
    if isinstance(node, dict):
        for k, v in node.items():
            if k in _PROSE_KEYS and isinstance(v, str):
                for tok in _RAW_ENUM_TOKENS:
                    if tok in v:
                        leaks.append((f"{path}.{k}", tok, v))
            leaks.extend(_find_raw_token_leaks(v, f"{path}.{k}"))
    elif isinstance(node, list):
        for idx, v in enumerate(node):
            leaks.extend(_find_raw_token_leaks(v, f"{path}[{idx}]"))
    return leaks


def test_prose_fields_contain_no_raw_enum_tokens() -> None:
    # exercise every disclosure branch at once: contradiction fired, owner
    # horizon/coverage/source-status degraded, unavailable list disclosed,
    # owner authority claim disclosed.
    p = _base_projection()
    p["coverage"]["source_status"] = "degraded"
    p["authority"]["rank_authority"] = True
    snap = _compose(p)
    leaks = _find_raw_token_leaks(snap)
    assert leaks == [], f"raw enum tokens leaked into prose field(s): {leaks}"


# --------------------------------------------------------------------------- #
# zh-label integrity: composer-authored English phrasing must never leak into
# the composer-authored zh sibling
# --------------------------------------------------------------------------- #
_COMPOSER_ENGLISH_PHRASES = (
    "the owner's own", "This composer", "Rather than estimate", "a filing-classification census",
    "never republish", "read-only projection", "a coarse market-access census",
)


def _find_english_leaks(node, path: str = "$") -> list[tuple[str, str, str]]:
    leaks: list[tuple[str, str, str]] = []
    if isinstance(node, dict):
        zh = node.get("zh")
        if "en" in node and isinstance(zh, str):
            for phrase in _COMPOSER_ENGLISH_PHRASES:
                if phrase in zh:
                    leaks.append((path, phrase, zh))
        for k, v in node.items():
            leaks.extend(_find_english_leaks(v, f"{path}.{k}"))
    elif isinstance(node, list):
        for idx, v in enumerate(node):
            leaks.extend(_find_english_leaks(v, f"{path}[{idx}]"))
    return leaks


def test_zh_narrative_never_embeds_composer_english_phrasing() -> None:
    p = _base_projection()
    p["coverage"]["source_status"] = "degraded"
    p["authority"]["rank_authority"] = True
    snap = _compose(p)
    leaks = _find_english_leaks(snap)
    assert leaks == [], f"English phrasing leaked into zh field(s): {leaks}"


def test_zh_narrative_present_wherever_english_is_composer_authored() -> None:
    snap = _compose()
    for impl in snap["implications"]["items"]:
        assert impl["text"]["en"], impl
        assert impl["text"]["zh"], impl
    assert snap["workspace"]["title"]["zh"]
    assert snap["headline"]["subtitle"]["zh"]


# --------------------------------------------------------------------------- #
# real owner artifact (data/capital_structure/projection.json) -- skipped
# where the artifact is absent, never fabricated. This file is ~25MB; the
# composer itself only ever iterates `records` once, so this is a real (if
# slow) exercise of that law, not just the synthetic fixtures above.
# --------------------------------------------------------------------------- #
@pytest.mark.skipif(not REAL_PROJECTION_PATH.exists(), reason="real owner artifact is absent")
def test_builds_and_validates_from_real_owner_artifact() -> None:
    projection = json.loads(REAL_PROJECTION_PATH.read_text(encoding="utf-8"))
    snap = contract.finalize(capital_structure.compose(projection, built_at=BUILT_AT))
    contract.validate(snap)
    assert snap["headline"]["state_id"] is None
    assert snap["headline"]["null_reason"] == "COMPUTATION_REFUSED"
    assert snap["axes"]["items"] == []
    assert snap["authority"]["can_size"] is False
    assert snap["authority"]["can_execute"] is False
    # the real projection's own issuer_count should be reflected verbatim
    issuer_count_metric = next(m for m in snap["metrics"]["items"] if m["metric_id"] == "cs_issuer_count")
    assert issuer_count_metric["value"] == projection.get("coverage", {}).get("issuer_count")
    # every owner-disclosed unavailable capacity gets its own typed metric
    unavailable = projection.get("unavailable") or []
    ids = {m["metric_id"] for m in snap["metrics"]["items"]}
    for name in unavailable:
        if isinstance(name, str) and name:
            assert f"cs_{name}" in ids
