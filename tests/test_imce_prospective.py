"""Tests for engine/cycle_pattern/imce_prospective.py (IMCE A5B) and its
nightly builder scripts/build_cycle_pattern_imce_prospective.py.

All fixtures are labelled RECONSTRUCTION — every write in this file targets
an explicit temp path via ``reconstruction=True``; the word "prospective"
appears here only as the dataset's own name, never as a claim about a real
event.

No network. Price-leg tests read the REAL committed
data/baskets/ohlcv/{DHI,PHM,KBH,TOL}.parquet files (already on disk, no
network) so the PIT-bound logic is exercised against real bars rather than a
synthetic series. Fetch-disposition tests inject a stub fetch function
(never real HTTP).

Coverage (frozen spec TESTS a-j, plus the red-team B1/B2/B3/M4/M5/M6/M7/
MIN8/MIN9/MIN10 fixes applied on top of the same branch):
  a. activation record idempotence
  b. first-observation-wins + exact-duplicate rerun no-op
  c. correction append + original packet immutability (byte-compare)
  d. activation-law fencing + reconstruction/production path law
  e. M_t verbatim conformance (>=2 floor, tie=>MIXED, missing-never-zero,
     no state carry-forward past a source failure) — UNCHANGED arithmetic
  f. R_t PIT admissibility + construction pins + typed absence, INCLUDING
     the B1 biweekly-period-end truncation fix
  g. label truth table (4/4 cohort, 2-3 named_subset, <2 NOT_RECONSTRUCTABLE)
  h. schema outcome-field blacklist, INCLUDING the B2 substring/stem fix
  i. measurement projection rebuilds from the ledger alone
  j. cycle-pattern authority guard passes with the new reader/writer
  B3. network failure vs not-published disposition
  M4. correction-path routing (re-extraction + 8-K/A shapes)
  M5. contributor staleness / calendar-quarter pooling-key alignment
  M6. observation_id determinism (wall-clock timestamps excluded from hash)
  M7. module-level activation-law enforcement + production-flag law +
      activation-stamped-only-after-manifest-success
  MIN8. TOL sensitivity self-healing fact lookup
  MIN9. denominator-convention conformance guard
  MIN10. full C_t leg shape for every context leg
  A5C. fail-closed correction detection pending source-revision history
      (Sol A5C review 2026-08-23 item 1) — corrected/unknown-state workspace
      with no prior observation is refused, log-only, activation/other
      candidates unaffected, idempotent, no schema/row-kind change
"""
from __future__ import annotations

import inspect
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from engine.cycle_pattern import imce_prospective as m  # noqa: E402

ACTIVATION_TS = "2026-01-01T00:00:00Z"
CIKS = {"DHI": "0000882184", "PHM": "0000822416", "KBH": "0000795266", "TOL": "0000794170"}

# Calendar-aligned default quarter-end (matches PHM/KBH's real FYE) so most
# tests get a trivial pooling key of (year, quarter) without having to think
# about the majority-month rule; M5 tests override this explicitly to
# exercise DHI/TOL's genuinely offset fiscal calendars.
_CALENDAR_ALIGNED_QUARTER_END = {1: "03-31", 2: "06-30", 3: "09-30", 4: "12-31"}


def _default_calendar_end(year: int, quarter: int) -> str:
    return f"{year}-{_CALENDAR_ALIGNED_QUARTER_END[quarter]}"


# Ticker-aware default denominator text so a fixture that doesn't care about
# MIN9 conformance still passes it by default (construction doc §1 frozen
# per-issuer convention keywords).
_DEFAULT_DENOMINATOR_TEXT = {
    "DHI": "gross orders in period",
    "PHM": "gross new orders in period",
    "KBH": "cancellation rate as a percentage of gross orders",
    "TOL": "quarterly cancellations as a percentage of signed contracts in quarter",
}


# ---------------------------------------------------------------------------
# Fixture builders — RECONSTRUCTION only, synthetic event_workspace subsets
# (only the keys this module actually reads).
# ---------------------------------------------------------------------------

def _fact_present(fact_id: str, value, *, basis: str | None = None) -> dict:
    return {"schema": "event_fact.v1", "fact_id": fact_id, "value": value, "basis": basis}


def _fact_absent(fact_id: str, *, reason: str = "no_span_addressable_evidence") -> dict:
    return {"schema": "event_fact.v1", "fact_id": fact_id, "typed_absence": {"reason": reason}}


def _workspace(
    *,
    ticker: str,
    cik: str,
    year: int,
    quarter: int,
    source_available_at: str,
    net_orders_current=None,
    net_orders_prior=None,
    cancel_current=None,
    cancel_prior=None,
    denominator: str | None = None,
    calendar_end: str | None = None,
    generation_id: str = "a" * 24,
    accession: str = "0000000000-26-000001",
    sha256hex: str = "d" * 64,
    facts_override: list[dict] | None = None,
    lifecycle_state: str = "complete",
    source_form: str | None = "8-K",
) -> dict:
    if facts_override is not None:
        facts = facts_override
    else:
        denom_text = denominator if denominator is not None else _DEFAULT_DENOMINATOR_TEXT.get(ticker, "gross orders in period")
        facts = [
            _fact_present("fact_net_orders_current", net_orders_current) if net_orders_current is not None
            else _fact_absent("fact_net_orders_current"),
            _fact_present("fact_net_orders_prior_year", net_orders_prior) if net_orders_prior is not None
            else _fact_absent("fact_net_orders_prior_year"),
            _fact_present("fact_cancellation_rate_current", cancel_current) if cancel_current is not None
            else _fact_absent("fact_cancellation_rate_current"),
            _fact_present("fact_cancellation_rate_prior_year", cancel_prior) if cancel_prior is not None
            else _fact_absent("fact_cancellation_rate_prior_year"),
            _fact_present("fact_cancellation_rate_denominator", denom_text, basis=denom_text),
        ]
        if ticker == "TOL":
            facts.append(_fact_present(
                "fact_cancellation_rate_beginning_backlog_sensitivity", 4.2,
                basis="quarterly cancellations as a percentage of beginning-quarter backlog",
            ))
    return {
        "event_id": f"evt_cik{cik}_{year}q{quarter}_results",
        "issuer": {
            "company_id": f"cik:{cik}",
            "listings": [{"security_id": f"xnys:{ticker}", "ticker": ticker, "mic": "XNYS", "is_primary": True}],
        },
        "fiscal_period": {"year": year, "quarter": quarter,
                           "calendar_end": calendar_end or _default_calendar_end(year, quarter)},
        "lifecycle": {"state": lifecycle_state, "source_available_at": source_available_at},
        "facts": facts,
        "sources": [{
            "kind": "issuer_release", "source_sha256": sha256hex,
            "filing_key": {"cik": cik, "accession": accession},
            "form": source_form,
        }],
        "generation_id": generation_id,
    }


def _mk_ws(ticker, *, cutoff, **kwargs):
    return _workspace(ticker=ticker, cik=CIKS[ticker], year=2026, quarter=2, source_available_at=cutoff, **kwargs)


def _trigger_pooling_key(ws: dict) -> tuple[int, int]:
    return m.calendar_quarter_key(ws["fiscal_period"]["calendar_end"])


# ---------------------------------------------------------------------------
# IMCE A5C: builder-level tests that inject content into
# ``_fetch_all_candidates``'s ``found`` map must ALSO stub
# ``harvest_event_revisions`` — scripts.build_cycle_pattern_
# imce_prospective.run() now walks each found candidate's OWN chain
# (frozen spec D2(d)) via the shared reader BEFORE it can be observed/
# corrected. Without an explicit stub, the real default
# (engine.neuralweb.company_intelligence_reader.read_all_event_source_revisions)
# would make a genuine network call against production R2 — this file's own
# "No network." law. Every synthetic single-snapshot fixture here represents
# an event whose chain has never accumulated a real correction, so a
# single-revision history derived from that ONE workspace is the faithful
# stub.
#
# Production incident addendum (2026-08-23): run() now performs ONE shared
# chain walk across every candidate this run (harvest_event_revisions,
# event_ids -> {event_id: history}), replacing a PER-CANDIDATE walk
# (_load_event_revision_history, event_id -> history) that independently
# re-walked the SAME marker->predecessor chain once per candidate — a
# post-incident ~170-generation chain measured 153s for ONE event, and the
# nightly builder was paying that ~8 times. The stub helpers below build the
# SAME fixture data, just shaped as a batch-callable now.
# ---------------------------------------------------------------------------

def _revision_entry(ws: dict) -> dict:
    """One synthetic chain revision matching
    engine.neuralweb.company_intelligence_reader.read_all_event_source_revisions's
    own receipt shape, derived from a single already-built test workspace."""
    lifecycle = ws.get("lifecycle") or {}
    source = next((s for s in ws.get("sources") or [] if s.get("kind") == "issuer_release"), {})
    return {
        "generation_id": ws.get("generation_id"),
        "source_sha256": source.get("source_sha256"),
        "source_available_at": lifecycle.get("source_available_at"),
        "observed_at": lifecycle.get("observed_at") or lifecycle.get("source_available_at"),
        "lifecycle_state": lifecycle.get("state"),
        "form": source.get("form"),
        "workspace": ws,
    }


def _stub_revision_history(*workspaces: dict):
    """A ``harvest_event_revisions`` stub mapping each workspace's own
    event_id to a single-revision history, for every requested event_id."""
    by_event = {ws["event_id"]: [_revision_entry(ws)] for ws in workspaces}

    def harvester(event_ids) -> dict[str, list[dict]]:
        return {str(eid): by_event.get(str(eid), []) for eid in event_ids}

    return harvester


def _stub_revision_history_ordered(event_id: str, *ordered_workspaces: dict):
    """A ``harvest_event_revisions`` stub for ONE event_id carrying MULTIPLE
    ordered revisions (oldest first, as the caller supplies them) — for
    eligibility/replay tests that need more than one source revision of the
    same event. Every OTHER requested event_id maps to an empty history."""
    history = [_revision_entry(ws) for ws in ordered_workspaces]

    def harvester(event_ids) -> dict[str, list[dict]]:
        return {str(eid): (history if str(eid) == event_id else []) for eid in event_ids}

    return harvester


# ---------------------------------------------------------------------------
# (a) activation record idempotence
# ---------------------------------------------------------------------------

def test_activation_idempotent(tmp_path):
    p = tmp_path / "recon_activation.jsonl"
    r1 = m.ensure_activation(path=p, reconstruction=True, now=datetime(2026, 1, 1, tzinfo=timezone.utc))
    r2 = m.ensure_activation(path=p, reconstruction=True, now=datetime(2026, 6, 1, tzinfo=timezone.utc))
    assert r1 == r2
    assert r1["activation_started_at"] == "2026-01-01T00:00:00Z"
    rows = m.load_rows(p)
    assert sum(1 for r in rows if r["row_kind"] == "activation") == 1


# ---------------------------------------------------------------------------
# (b) first-observation-wins + exact-duplicate rerun no-op
# ---------------------------------------------------------------------------

def test_first_observation_wins_and_duplicate_is_noop(tmp_path):
    p = tmp_path / "recon_obs.jsonl"
    trig = _mk_ws("DHI", cutoff="2026-05-01T20:00:00Z", net_orders_current=100, net_orders_prior=90,
                  cancel_current=10.0, cancel_prior=12.0)
    packet = m.build_observation_packet(
        trigger_ticker="DHI", trigger_workspace=trig,
        issuer_workspaces={"DHI": trig, "PHM": None, "KBH": None, "TOL": None},
        activation_started_at=ACTIVATION_TS,
    )
    row1, appended1 = m.append_observation(
        packet, path=p, reconstruction=True, trigger_lifecycle_state="complete", trigger_source_form="8-K",
    )
    assert appended1 is True
    row2, appended2 = m.append_observation(packet, path=p, reconstruction=True)
    assert appended2 is False
    assert row2["observation_id"] == row1["observation_id"]
    rows = m.load_rows(p)
    assert sum(1 for r in rows if r["row_kind"] == "observation") == 1


# ---------------------------------------------------------------------------
# (c) correction append + original packet immutability (byte-compare)
# ---------------------------------------------------------------------------

def test_correction_append_never_rewrites_original(tmp_path):
    p = tmp_path / "recon_corr.jsonl"
    trig = _mk_ws("PHM", cutoff="2026-05-01T20:00:00Z", net_orders_current=100, net_orders_prior=90,
                  cancel_current=10.0, cancel_prior=12.0, sha256hex="a" * 64)
    packet = m.build_observation_packet(
        trigger_ticker="PHM", trigger_workspace=trig,
        issuer_workspaces={"DHI": None, "PHM": trig, "KBH": None, "TOL": None},
        activation_started_at=ACTIVATION_TS,
    )
    row1, _ = m.append_observation(
        packet, path=p, reconstruction=True, trigger_lifecycle_state="complete", trigger_source_form="8-K",
    )

    original_bytes = p.read_bytes()
    original_lines = original_bytes.splitlines()

    revised_trig = _mk_ws("PHM", cutoff="2026-05-01T20:00:00Z", net_orders_current=101, net_orders_prior=90,
                           cancel_current=10.0, cancel_prior=12.0, sha256hex="b" * 64,
                           generation_id="b" * 24)
    revised_packet = m.build_observation_packet(
        trigger_ticker="PHM", trigger_workspace=revised_trig,
        issuer_workspaces={"DHI": None, "PHM": revised_trig, "KBH": None, "TOL": None},
        activation_started_at=ACTIVATION_TS,
    )
    corr_row = m.append_correction(
        superseded_observation_id=row1["observation_id"],
        corrected_packet=revised_packet,
        reason="source revision test",
        path=p, reconstruction=True,
    )
    assert corr_row["row_kind"] == "correction"
    assert corr_row["supersedes_observation_id"] == row1["observation_id"]

    new_bytes = p.read_bytes()
    new_lines = new_bytes.splitlines()
    # The original line(s) are byte-identical and untouched; only a new line was appended.
    assert new_lines[:len(original_lines)] == original_lines
    assert len(new_lines) == len(original_lines) + 1

    with pytest.raises(m.ProspectiveLedgerError):
        m.append_correction(
            superseded_observation_id="obs_doesnotexist", corrected_packet=revised_packet,
            reason="x", path=p, reconstruction=True,
        )


# ---------------------------------------------------------------------------
# (d) activation-law fencing + reconstruction/production path law
# ---------------------------------------------------------------------------

def test_pre_activation_event_excluded_from_cohort():
    activation = "2026-06-01T00:00:00Z"
    pre_activation_ws = _mk_ws("DHI", cutoff="2026-01-01T00:00:00Z", net_orders_current=100,
                                net_orders_prior=90, cancel_current=10.0, cancel_prior=12.0)
    key = _trigger_pooling_key(pre_activation_ws)
    state = m.per_issuer_state("DHI", pre_activation_ws, activation_started_at=activation,
                                as_of_cutoff="2026-07-01T00:00:00Z", trigger_pooling_key=key)
    assert state["contributor_eligible"] is False
    assert state["activation_law"] == "pre_activation_excluded"
    assert state["order_softness"] == "NOT_RECONSTRUCTABLE"

    post_activation_ws = _mk_ws("DHI", cutoff="2026-07-01T00:00:00Z", net_orders_current=100,
                                 net_orders_prior=90, cancel_current=10.0, cancel_prior=12.0)
    key2 = _trigger_pooling_key(post_activation_ws)
    state2 = m.per_issuer_state("DHI", post_activation_ws, activation_started_at=activation,
                                 as_of_cutoff="2026-07-01T00:00:00Z", trigger_pooling_key=key2)
    assert state2["contributor_eligible"] is True
    assert state2["activation_law"] == "post_activation"


def test_reconstruction_mode_cannot_touch_production_path():
    with pytest.raises(m.ProspectiveLedgerError):
        m.ensure_activation(path=m.PRODUCTION_PATH, reconstruction=True)


def test_production_write_without_flag_is_refused(tmp_path):
    stray = tmp_path / "not_production.jsonl"
    # Wrong path AND missing production flag — either alone would raise;
    # this proves the path check fires first (unchanged behavior).
    with pytest.raises(m.ProspectiveLedgerError):
        m.ensure_activation(path=stray, reconstruction=False)


def test_production_path_requires_explicit_production_flag(monkeypatch, tmp_path):
    """M7(b): even targeting the real production PATH, a bare
    reconstruction=False call without production=True is refused."""
    fake_prod = tmp_path / "fake_production.jsonl"
    monkeypatch.setattr(m, "PRODUCTION_PATH", fake_prod)
    with pytest.raises(m.ProspectiveLedgerError, match="production=True"):
        m.ensure_activation(reconstruction=False)  # production defaults False
    assert not fake_prod.exists()
    # With production=True it succeeds.
    row = m.ensure_activation(reconstruction=False, production=True,
                               now=datetime(2026, 1, 1, tzinfo=timezone.utc))
    assert row["activation_started_at"] == "2026-01-01T00:00:00Z"
    assert fake_prod.exists()


# ---------------------------------------------------------------------------
# M7(a): module-level activation-law enforcement in append_observation
# ---------------------------------------------------------------------------

def test_append_observation_rejects_pre_activation_decision_cutoff(tmp_path):
    p = tmp_path / "recon_activation_gate.jsonl"
    m.ensure_activation(path=p, reconstruction=True, now=datetime(2026, 6, 1, tzinfo=timezone.utc))
    pre_ws = _mk_ws("KBH", cutoff="2026-01-01T00:00:00Z", net_orders_current=100, net_orders_prior=90,
                     cancel_current=10.0, cancel_prior=12.0)
    packet = m.build_observation_packet(
        trigger_ticker="KBH", trigger_workspace=pre_ws,
        issuer_workspaces={"DHI": None, "PHM": None, "KBH": pre_ws, "TOL": None},
        activation_started_at="2026-01-01T00:00:00Z",  # packet claims an (incorrect) earlier activation
    )
    with pytest.raises(m.ProspectiveLedgerError, match="activation law"):
        m.append_observation(packet, path=p, reconstruction=True)
    assert m.load_rows(p) == [m.activation_row(p)]  # nothing else was written


# ---------------------------------------------------------------------------
# (e) M_t verbatim conformance — UNCHANGED arithmetic, red-team constant-exact
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("d_orders,d_cancel,expected", [
    ("+", "-", "TIGHTENING"), ("+", "0", "TIGHTENING"),
    ("-", "+", "SOFTENING"), ("-", "0", "SOFTENING"),
    ("+", "+", "MIXED"), ("-", "-", "MIXED"),
    ("0", "+", "MIXED"), ("0", "-", "MIXED"), ("0", "0", "MIXED"),
    (None, "+", "NOT_RECONSTRUCTABLE"), ("+", None, "NOT_RECONSTRUCTABLE"),
    (None, None, "NOT_RECONSTRUCTABLE"),
])
def test_order_softness_lookup_table_verbatim(d_orders, d_cancel, expected):
    assert m.order_softness_state(d_orders, d_cancel) == expected


def test_yoy_sign_missing_never_becomes_zero():
    assert m.yoy_sign(100, 100) == "0"
    assert m.yoy_sign(None, 100) is None
    assert m.yoy_sign(100, None) is None
    assert m.yoy_sign(None, None) is None


def test_pooling_two_contributor_floor_and_below():
    per_issuer = {
        "DHI": {"order_softness": "TIGHTENING"},
        "PHM": {"order_softness": "NOT_RECONSTRUCTABLE"},
        "KBH": {"order_softness": "NOT_RECONSTRUCTABLE"},
        "TOL": {"order_softness": "NOT_RECONSTRUCTABLE"},
    }
    result = m.pool_cohort_state(per_issuer)
    assert result["n_contributors"] == 1
    assert result["label"] == "NOT_RECONSTRUCTABLE"
    assert result["pooled_state"] == "NOT_RECONSTRUCTABLE"


def test_pooling_tie_is_mixed_two_way_and_three_way():
    two_way = {
        "DHI": {"order_softness": "TIGHTENING"}, "PHM": {"order_softness": "TIGHTENING"},
        "KBH": {"order_softness": "SOFTENING"}, "TOL": {"order_softness": "SOFTENING"},
    }
    r = m.pool_cohort_state(two_way)
    assert r["pooled_state"] == "MIXED"
    assert r["label"] == "cohort"

    three_way = {
        "DHI": {"order_softness": "TIGHTENING"}, "PHM": {"order_softness": "SOFTENING"},
        "KBH": {"order_softness": "MIXED"}, "TOL": {"order_softness": "NOT_RECONSTRUCTABLE"},
    }
    r2 = m.pool_cohort_state(three_way)
    assert r2["n_contributors"] == 3
    assert r2["pooled_state"] == "MIXED"
    assert r2["label"] == "named_subset"


def test_no_state_carry_forward_past_a_source_failure():
    good_ws = _mk_ws("KBH", cutoff="2026-05-01T00:00:00Z", net_orders_current=100, net_orders_prior=90,
                      cancel_current=10.0, cancel_prior=12.0)
    good_key = _trigger_pooling_key(good_ws)
    good_state = m.per_issuer_state("KBH", good_ws, activation_started_at=ACTIVATION_TS,
                                     as_of_cutoff="2026-06-01T00:00:00Z", trigger_pooling_key=good_key)
    assert good_state["order_softness"] != "NOT_RECONSTRUCTABLE"

    failed_ws = _mk_ws("KBH", cutoff="2026-08-01T00:00:00Z", net_orders_current=None, net_orders_prior=None,
                        cancel_current=10.0, cancel_prior=12.0)
    failed_key = _trigger_pooling_key(failed_ws)
    failed_state = m.per_issuer_state("KBH", failed_ws, activation_started_at=ACTIVATION_TS,
                                       as_of_cutoff="2026-09-01T00:00:00Z", trigger_pooling_key=failed_key)
    assert failed_state["order_softness"] == "NOT_RECONSTRUCTABLE"
    assert failed_state["d_orders"] is None


# ---------------------------------------------------------------------------
# M5 — contributor staleness / calendar-quarter pooling-key alignment
# ---------------------------------------------------------------------------

def test_calendar_quarter_key_matches_frozen_majority_month_table():
    # Frozen table (research/imce/IMCE_HB0_SOURCE_DEFINITION_CENSUS_V1.md §4b):
    # DHI FQ1 ends Dec 31 -> CQ4 of THAT SAME year (Oct/Nov/Dec all in it).
    assert m.calendar_quarter_key("2025-12-31") == (2025, 4)
    # TOL FQ1 ends Jan 31 -> CQ4 of the PRIOR year (Nov+Dec majority).
    assert m.calendar_quarter_key("2026-01-31") == (2025, 4)
    # PHM/KBH-style calendar-aligned quarter ends map onto themselves.
    assert m.calendar_quarter_key("2026-06-30") == (2026, 2)
    assert m.calendar_quarter_key("2026-05-31") == (2026, 2)
    assert m.calendar_quarter_key(None) is None
    assert m.calendar_quarter_key("not-a-date") is None


def test_m5_stale_snapshot_outside_aligned_quarter_excluded():
    """The reviewer's reproduction case: a multi-year-stale KBH snapshot
    (published well AFTER activation, so the activation-law gate alone would
    let it through) must never be pooled into a live trigger's read — the
    pooling-key alignment gate must catch what the activation-law gate
    cannot."""
    trigger_ws = _mk_ws("DHI", cutoff="2026-05-01T00:00:00Z", net_orders_current=100, net_orders_prior=90,
                         cancel_current=10.0, cancel_prior=12.0)
    trigger_key = _trigger_pooling_key(trigger_ws)
    assert trigger_key == (2026, 2)

    # KBH's fiscal Q4 2020 (calendar-aligned -> pooling key (2020, 4)),
    # but published/republished LATE — well after activation, so PIT and
    # activation-law alone would both pass it.
    stale_kbh = _workspace(
        ticker="KBH", cik=CIKS["KBH"], year=2020, quarter=4,
        source_available_at="2026-02-01T00:00:00Z", calendar_end="2020-11-30",
        net_orders_current=50, net_orders_prior=45, cancel_current=8.0, cancel_prior=9.0,
    )
    assert m.calendar_quarter_key(stale_kbh["fiscal_period"]["calendar_end"]) != trigger_key
    state = m.per_issuer_state("KBH", stale_kbh, activation_started_at=ACTIVATION_TS,
                                as_of_cutoff="2026-05-01T00:00:00Z", trigger_pooling_key=trigger_key)
    assert state["contributor_eligible"] is False
    assert state["activation_law"] == "stale_snapshot_outside_aligned_quarter"
    assert state["order_softness"] == "NOT_RECONSTRUCTABLE"


def test_m5_natural_staggered_cadence_all_eligible():
    """The genuine natural staggered cadence, verified mechanically against
    the frozen majority-month table (POOLING_KEY_DOC §4b) rather than
    assumed: TOL's Oct-31 FYE means its own CQ2-2026-aligned quarter (fiscal
    Q3, ending Jul 31) is the LAST of the four issuers to close and report
    for that calendar quarter — DHI (Jun 30), KBH (May 31), and PHM (Jun 30)
    are all already published by the time TOL itself reports in mid-August,
    which is exactly what makes a genuine 4/4 cohort pooling read possible:
    triggered by TOL's OWN report, with all three others already available
    and pooling-key-aligned.

    (Note: a DHI/PHM/KBH-triggered read for the SAME calendar quarter,
    published in July, structurally CANNOT include TOL — TOL's aligned
    quarter has not even closed yet at that point. That is not a defect;
    it is what the frozen majority-month rule + PIT correctly implies for
    TOL's specific fiscal offset.)"""
    dhi = _workspace(ticker="DHI", cik=CIKS["DHI"], year=2026, quarter=3,
                      source_available_at="2026-07-15T20:00:00Z", calendar_end="2026-06-30",
                      net_orders_current=100, net_orders_prior=90, cancel_current=10.0, cancel_prior=12.0)
    kbh = _workspace(ticker="KBH", cik=CIKS["KBH"], year=2026, quarter=2,
                      source_available_at="2026-06-20T20:00:00Z", calendar_end="2026-05-31",
                      net_orders_current=50, net_orders_prior=45, cancel_current=8.0, cancel_prior=9.0)
    phm = _workspace(ticker="PHM", cik=CIKS["PHM"], year=2026, quarter=2,
                      source_available_at="2026-07-25T20:00:00Z", calendar_end="2026-06-30",
                      net_orders_current=200, net_orders_prior=180, cancel_current=11.0, cancel_prior=10.0)
    tol = _workspace(ticker="TOL", cik=CIKS["TOL"], year=2026, quarter=3,
                      source_available_at="2026-08-15T20:00:00Z", calendar_end="2026-07-31",
                      net_orders_current=30, net_orders_prior=28, cancel_current=5.0, cancel_prior=6.0)

    trigger_key = _trigger_pooling_key(tol)
    assert trigger_key == (2026, 2)
    for ticker, ws in (("DHI", dhi), ("KBH", kbh), ("PHM", phm)):
        assert m.calendar_quarter_key(ws["fiscal_period"]["calendar_end"]) == (2026, 2), ticker

    for ticker, ws in (("DHI", dhi), ("KBH", kbh), ("PHM", phm), ("TOL", tol)):
        state = m.per_issuer_state(ticker, ws, activation_started_at=ACTIVATION_TS,
                                    as_of_cutoff="2026-08-15T20:00:00Z", trigger_pooling_key=trigger_key)
        assert state["contributor_eligible"] is True, (ticker, state)
        assert state["activation_law"] == "post_activation"


# ---------------------------------------------------------------------------
# MIN9 — denominator-convention conformance guard
# ---------------------------------------------------------------------------

def test_denominator_conformance_mismatch_excludes_contributor():
    ws = _mk_ws("DHI", cutoff="2026-05-01T00:00:00Z", net_orders_current=100, net_orders_prior=90,
                cancel_current=10.0, cancel_prior=12.0, denominator="some unrelated convention text")
    key = _trigger_pooling_key(ws)
    state = m.per_issuer_state("DHI", ws, activation_started_at=ACTIVATION_TS,
                                as_of_cutoff="2026-06-01T00:00:00Z", trigger_pooling_key=key)
    assert state["contributor_eligible"] is False
    assert state["activation_law"] == "denominator_convention_mismatch"
    assert state["denominator_conforms"] is False


def test_denominator_conformance_matching_keyword_passes():
    ws = _mk_ws("TOL", cutoff="2026-05-01T00:00:00Z", net_orders_current=100, net_orders_prior=90,
                cancel_current=5.0, cancel_prior=6.0,
                denominator="Quarterly Cancellations as a Percentage of Signed Contracts in Quarter")
    key = _trigger_pooling_key(ws)
    state = m.per_issuer_state("TOL", ws, activation_started_at=ACTIVATION_TS,
                                as_of_cutoff="2026-06-01T00:00:00Z", trigger_pooling_key=key)
    assert state["denominator_conforms"] is True
    assert state["contributor_eligible"] is True


# ---------------------------------------------------------------------------
# MIN8 — TOL sensitivity self-healing fact lookup
# ---------------------------------------------------------------------------

def test_tol_sensitivity_diagnostic_self_heals_when_fact_absent():
    ws = _mk_ws("TOL", cutoff="2026-05-01T00:00:00Z", net_orders_current=100, net_orders_prior=90,
                cancel_current=5.0, cancel_prior=6.0)
    key = _trigger_pooling_key(ws)
    state = m.per_issuer_state("TOL", ws, activation_started_at=ACTIVATION_TS,
                                as_of_cutoff="2026-06-01T00:00:00Z", trigger_pooling_key=key)
    sens = state["sensitivity"]
    assert sens["current_value"] == 4.2
    assert sens["prior_year_value"] is None
    assert sens["prior_year_absence_reason"] == "fact_absent_from_workspace"
    assert sens["d_cancel_sensitivity"] is None
    assert sens["order_softness_sensitivity_basis"] == "NOT_RECONSTRUCTABLE"


def test_tol_sensitivity_diagnostic_computes_when_prior_year_fact_present():
    facts = [
        _fact_present("fact_net_orders_current", 100), _fact_present("fact_net_orders_prior_year", 90),
        _fact_present("fact_cancellation_rate_current", 5.0), _fact_present("fact_cancellation_rate_prior_year", 6.0),
        _fact_present("fact_cancellation_rate_denominator", "signed contracts in quarter"),
        _fact_present("fact_cancellation_rate_beginning_backlog_sensitivity", 4.2),
        _fact_present("fact_cancellation_rate_beginning_backlog_sensitivity_prior_year", 3.0),
    ]
    ws = _mk_ws("TOL", cutoff="2026-05-01T00:00:00Z", facts_override=facts)
    key = _trigger_pooling_key(ws)
    state = m.per_issuer_state("TOL", ws, activation_started_at=ACTIVATION_TS,
                                as_of_cutoff="2026-06-01T00:00:00Z", trigger_pooling_key=key)
    sens = state["sensitivity"]
    assert sens["prior_year_value"] == 3.0
    assert sens["d_cancel_sensitivity"] == "+"  # 4.2 > 3.0
    assert sens["order_softness_sensitivity_basis"] != "NOT_RECONSTRUCTABLE"
    assert sens["agreement_with_primary_basis"] is not None


# ---------------------------------------------------------------------------
# (f) R_t PIT admissibility + construction pins + typed absence + B1 fix
# ---------------------------------------------------------------------------

def test_construction_pins_forbidden_strings_absent():
    src_imce = inspect.getsource(m)
    import scripts.build_cycle_pattern_imce_prospective as builder_mod
    src_builder = inspect.getsource(builder_mod)
    for forbidden in ("2W-FRI", "_resample_weekly"):
        assert forbidden not in src_imce, f"{forbidden!r} must never appear in imce_prospective.py"
        assert forbidden not in src_builder, f"{forbidden!r} must never appear in the nightly builder"
    assert "_biweekly_close" in src_imce


def test_price_leg_typed_absence_for_unknown_ticker():
    leg = m.price_leg_for_ticker("ZZZZNOPE", datetime(2026, 6, 1, tzinfo=timezone.utc))
    assert leg["typed_absence"] is not None
    assert leg["sign"] is None
    assert leg["price_plane_id"] is None


@pytest.mark.needs_full_checkout("data")
def test_price_leg_pit_bound_never_uses_a_future_bar():
    cutoff = datetime(2026, 6, 1, 12, 0, tzinfo=timezone.utc)  # mid-session, before that day's close
    leg = m.price_leg_for_ticker("DHI", cutoff)
    assert leg["typed_absence"] is None
    last_bar = leg["last_admissible_bar"]
    assert last_bar is not None
    assert last_bar[:10] < "2026-06-01"

    late_cutoff = datetime(2026, 6, 1, 23, 0, tzinfo=timezone.utc)
    leg2 = m.price_leg_for_ticker("DHI", late_cutoff)
    assert leg2["last_admissible_bar"][:10] <= "2026-06-01"


@pytest.mark.needs_full_checkout("data")
def test_b1_biweekly_period_end_truncation_mid_week_cutoff():
    """A bar whose PERIOD contains the cutoff must not participate — the
    stamped biweekly period-end must always be <= the cutoff date. Reproduces
    the reviewer's exact scenario: a Wed 2026-08-19 cutoff must not admit the
    2026-08-21 (Friday) period."""
    mid_week_cutoff = datetime(2026, 8, 19, 20, 0, tzinfo=timezone.utc)
    leg = m.price_leg_for_ticker("DHI", mid_week_cutoff)
    assert leg["typed_absence"] is None
    assert leg["last_biweekly_period_end"] is not None
    assert leg["last_biweekly_period_end"][:10] <= "2026-08-19"
    assert leg["last_biweekly_period_end"][:10] != "2026-08-21"

    # Once the period has genuinely closed, the SAME period-end is admitted
    # and the sign is free to differ from the mid-week read.
    closed_cutoff = datetime(2026, 8, 22, 20, 0, tzinfo=timezone.utc)
    leg2 = m.price_leg_for_ticker("DHI", closed_cutoff)
    assert leg2["last_biweekly_period_end"][:10] == "2026-08-21"


def test_r_t_leg_vintage_and_adjustment_basis_are_honest():
    leg = m.price_leg_for_ticker("ZZZZNOPE", datetime(2026, 6, 1, tzinfo=timezone.utc),
                                  now=datetime(2026, 6, 2, tzinfo=timezone.utc))
    assert leg["vintage"] == "2026-06-02T00:00:00Z"
    # No plane -> no adjustment_basis claim at all.
    assert leg["adjustment_basis"] is None


# ---------------------------------------------------------------------------
# (g) label truth table
# ---------------------------------------------------------------------------

def test_label_truth_table_four_of_four_is_cohort():
    per_issuer = {t: {"order_softness": "TIGHTENING"} for t in m.ROSTER}
    r = m.pool_cohort_state(per_issuer)
    assert r["label"] == "cohort"
    assert r["n_contributors"] == 4
    assert r["named_subset_basis"] is None


def test_label_truth_table_two_or_three_is_named_subset_with_exact_names():
    per_issuer = {
        "DHI": {"order_softness": "TIGHTENING"}, "PHM": {"order_softness": "TIGHTENING"},
        "KBH": {"order_softness": "NOT_RECONSTRUCTABLE"}, "TOL": {"order_softness": "NOT_RECONSTRUCTABLE"},
    }
    r = m.pool_cohort_state(per_issuer)
    assert r["label"] == "named_subset"
    assert r["named_subset_basis"] == ["DHI", "PHM"]


def test_label_truth_table_below_two_is_not_reconstructable():
    per_issuer = {t: {"order_softness": "NOT_RECONSTRUCTABLE"} for t in m.ROSTER}
    r = m.pool_cohort_state(per_issuer)
    assert r["label"] == "NOT_RECONSTRUCTABLE"


# ---------------------------------------------------------------------------
# (h) schema outcome-field blacklist — including the B2 substring/stem fix
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("token", sorted(m.FORBIDDEN_OUTCOME_TOKENS))
def test_outcome_blacklist_catches_every_bare_token(token):
    with pytest.raises(m.ProspectiveLedgerError):
        m.assert_no_outcome_fields({"nested": {token: 1.23}})


@pytest.mark.parametrize("key", [
    "forward_return_63d", "fwd_ret_21d", "brier_score_90d", "hit_rate_pct",
    "p_value_two_sided", "sharpe_1y", "forwardReturn", "outcome", "return_63d",
])
def test_outcome_blacklist_b2_substring_stem_fix(key):
    """B2: the blacklist must catch decorated/camelCase variants, not just
    exact tokens."""
    with pytest.raises(m.ProspectiveLedgerError):
        m.assert_no_outcome_fields({key: 1.0})


@pytest.mark.parametrize("key", [
    "company_id", "security_id", "event_id", "decision_cutoff", "activation_started_at",
    "pooled_state", "contributor_eligible", "prior_year_value", "current_value",
    "source_timestamp", "as_of_decision_cutoff", "denominator_conforms", "pooling_key",
])
def test_outcome_blacklist_no_false_positives_on_real_schema_keys(key):
    m.assert_no_outcome_fields({key: 1.0})  # must not raise


def test_real_observation_packet_carries_zero_outcome_fields():
    trig = _mk_ws("DHI", cutoff="2026-05-01T20:00:00Z", net_orders_current=100, net_orders_prior=90,
                  cancel_current=10.0, cancel_prior=12.0)
    packet = m.build_observation_packet(
        trigger_ticker="DHI", trigger_workspace=trig,
        issuer_workspaces={"DHI": trig, "PHM": None, "KBH": None, "TOL": None},
        activation_started_at=ACTIVATION_TS,
    )
    m.assert_no_outcome_fields(packet)  # must not raise
    flat = json.dumps(packet).lower()
    for token in m.FORBIDDEN_OUTCOME_TOKENS:
        assert f'"{token}"' not in flat


def test_schema_version_string():
    assert m.SCHEMA == "imce.prospective_observation.v1"


# ---------------------------------------------------------------------------
# N1 — frozen-schema WHITELIST (stronger than the blacklist: an unexpected
# key of ANY kind, outcome-shaped or not, must fail loudly and be added
# deliberately). The blacklist above stays as defence-in-depth, unchanged.
# ---------------------------------------------------------------------------

_FROZEN_TOP_LEVEL_KEYS = frozenset({
    "trigger", "activation_started_at", "m_t", "r_t", "c_t", "authority", "prophet_flags",
})
_FROZEN_TRIGGER_KEYS = frozenset({
    "ticker", "company_id", "security_id", "event_id", "fiscal_period",
    "event_workspace_generation_id", "source_document_sha256", "source_accession", "decision_cutoff",
})
_FROZEN_MT_KEYS = frozenset({
    "construction_doc", "pooling_key_doc", "trigger_pooling_key", "roster", "per_issuer",
    "label", "pooled_state", "named_subset_basis", "contributors", "n_contributors",
})
_FROZEN_PER_ISSUER_KEYS = frozenset({
    "ticker", "contributor_eligible", "activation_law", "as_of_event_id", "as_of_decision_cutoff",
    "pooling_key", "denominator_conforms", "facts", "d_orders", "d_cancel", "order_softness",
})
_FROZEN_TOL_SENSITIVITY_KEYS = frozenset({
    "fact_id", "prior_year_fact_id", "current_value", "current_absence_reason", "basis",
    "prior_year_value", "prior_year_absence_reason", "d_cancel_sensitivity",
    "order_softness_sensitivity_basis", "agreement_with_primary_basis",
})
_FROZEN_RT_KEYS = frozenset({"construction_version", "legs"})
_FROZEN_RT_LEG_KEYS = frozenset({
    "ticker", "price_plane_id", "adjustment_basis", "vintage", "last_admissible_bar",
    "last_biweekly_period_end", "construction_version", "sign", "macd_hist_value", "typed_absence",
})
_FROZEN_CT_TOP_KEYS = frozenset({"treasury_cmt", "pmms", "fred_alfred", "nar_series"})
_FROZEN_CT_LEG_BASE_KEYS = frozenset({
    "source", "value", "typed_absence", "pit_class", "source_timestamp", "observation_timestamp", "context_only",
})
_FROZEN_CT_LEG_EXTRA_KEYS = {
    "treasury_cmt": frozenset({"rights_disposition"}),
    "pmms": frozenset({"persisted", "status"}),
    "fred_alfred": frozenset({"fetched", "status"}),
    "nar_series": frozenset({"may_be_stored"}),
}
_FROZEN_PROPHET_FLAGS_KEYS = frozenset({"may_rank", "may_size", "may_gate", "prophet_authority"})


def _whitelist_packet(with_tol_contributor: bool = True) -> dict:
    dhi = _mk_ws("DHI", cutoff="2026-05-01T20:00:00Z", net_orders_current=100, net_orders_prior=90,
                 cancel_current=10.0, cancel_prior=12.0, calendar_end="2026-06-30")
    tol = _workspace(ticker="TOL", cik=CIKS["TOL"], year=2026, quarter=3,
                      source_available_at="2026-04-25T20:00:00Z", calendar_end="2026-06-30",
                      net_orders_current=30, net_orders_prior=28, cancel_current=5.0, cancel_prior=6.0)
    return m.build_observation_packet(
        trigger_ticker="DHI", trigger_workspace=dhi,
        issuer_workspaces={"DHI": dhi, "PHM": None, "KBH": None, "TOL": tol if with_tol_contributor else None},
        activation_started_at=ACTIVATION_TS,
    )


def test_n1_frozen_schema_whitelist_top_level_and_trigger_and_mt():
    packet = _whitelist_packet()
    assert set(packet.keys()) == _FROZEN_TOP_LEVEL_KEYS
    assert set(packet["trigger"].keys()) == _FROZEN_TRIGGER_KEYS
    assert set(packet["m_t"].keys()) == _FROZEN_MT_KEYS
    assert set(packet["prophet_flags"].keys()) == _FROZEN_PROPHET_FLAGS_KEYS


def test_n1_frozen_schema_whitelist_per_issuer_and_sensitivity():
    packet = _whitelist_packet(with_tol_contributor=True)
    per_issuer = packet["m_t"]["per_issuer"]
    for ticker in m.ROSTER:
        keys = set(per_issuer[ticker].keys())
        if ticker == "TOL":
            assert keys == _FROZEN_PER_ISSUER_KEYS | {"sensitivity"}, (ticker, keys)
            assert set(per_issuer["TOL"]["sensitivity"].keys()) == _FROZEN_TOL_SENSITIVITY_KEYS
        else:
            assert keys == _FROZEN_PER_ISSUER_KEYS, (ticker, keys)


def test_n1_frozen_schema_whitelist_rt_legs():
    packet = _whitelist_packet()
    assert set(packet["r_t"].keys()) == _FROZEN_RT_KEYS
    for ticker in m.ROSTER:
        leg = packet["r_t"]["legs"][ticker]
        assert set(leg.keys()) == _FROZEN_RT_LEG_KEYS, (ticker, set(leg.keys()))


def test_n1_frozen_schema_whitelist_ct_legs():
    packet = _whitelist_packet()
    assert set(packet["c_t"].keys()) == _FROZEN_CT_TOP_KEYS
    for name, leg in packet["c_t"].items():
        expected = _FROZEN_CT_LEG_BASE_KEYS | _FROZEN_CT_LEG_EXTRA_KEYS[name]
        assert set(leg.keys()) == expected, (name, set(leg.keys()))


def test_n1_frozen_schema_whitelist_facts_shape():
    packet = _whitelist_packet()
    for fact in packet["m_t"]["per_issuer"]["DHI"]["facts"].values():
        assert set(fact.keys()) == {"value", "absence_reason"}


def test_n1_frozen_schema_whitelist_catches_an_injected_outcome_key():
    """Proves the whitelist actually fires — not just a green rubber stamp."""
    packet = _whitelist_packet()
    packet["r_t"]["legs"]["DHI"]["sneaky_forward_metric"] = 1.23
    assert set(packet["r_t"]["legs"]["DHI"].keys()) != _FROZEN_RT_LEG_KEYS


# ---------------------------------------------------------------------------
# M6 — observation_id determinism (wall-clock timestamps excluded from hash)
# ---------------------------------------------------------------------------

def test_observation_id_is_deterministic_across_wall_clock_times():
    trig = _mk_ws("KBH", cutoff="2026-05-01T20:00:00Z", net_orders_current=100, net_orders_prior=90,
                  cancel_current=10.0, cancel_prior=12.0)
    packet1 = m.build_observation_packet(
        trigger_ticker="KBH", trigger_workspace=trig,
        issuer_workspaces={"DHI": None, "PHM": None, "KBH": trig, "TOL": None},
        activation_started_at=ACTIVATION_TS, now=datetime(2026, 1, 1, tzinfo=timezone.utc),
    )
    packet2 = m.build_observation_packet(
        trigger_ticker="KBH", trigger_workspace=trig,
        issuer_workspaces={"DHI": None, "PHM": None, "KBH": trig, "TOL": None},
        activation_started_at=ACTIVATION_TS, now=datetime(2026, 3, 15, 12, 30, tzinfo=timezone.utc),
    )
    # The two builds' c_t observation_timestamp fields genuinely differ...
    assert packet1["c_t"]["treasury_cmt"]["observation_timestamp"] != packet2["c_t"]["treasury_cmt"]["observation_timestamp"]
    # ...but the content-address must be identical.
    id1 = m.compute_observation_id(packet1)
    id2 = m.compute_observation_id(packet2)
    assert id1 == id2


def test_observation_timestamp_survives_in_the_stored_row(tmp_path):
    p = tmp_path / "recon_m6.jsonl"
    trig = _mk_ws("PHM", cutoff="2026-05-01T20:00:00Z", net_orders_current=100, net_orders_prior=90,
                  cancel_current=10.0, cancel_prior=12.0)
    packet = m.build_observation_packet(
        trigger_ticker="PHM", trigger_workspace=trig,
        issuer_workspaces={"DHI": None, "PHM": trig, "KBH": None, "TOL": None},
        activation_started_at=ACTIVATION_TS, now=datetime(2026, 4, 1, tzinfo=timezone.utc),
    )
    row, _ = m.append_observation(
        packet, path=p, reconstruction=True, trigger_lifecycle_state="complete", trigger_source_form="8-K",
    )
    assert row["c_t"]["treasury_cmt"]["observation_timestamp"] == "2026-04-01T00:00:00Z"


# ---------------------------------------------------------------------------
# MIN10 — full C_t leg shape for every context leg
# ---------------------------------------------------------------------------

def test_context_legs_all_carry_the_full_shape():
    legs = m.context_legs(now=datetime(2026, 1, 1, tzinfo=timezone.utc))
    required = {"source", "value", "typed_absence", "pit_class", "source_timestamp",
                "observation_timestamp", "context_only"}
    for name, leg in legs.items():
        assert required <= set(leg.keys()), f"{name} missing fields: {required - set(leg.keys())}"
        assert leg["context_only"] is True
        assert leg["value"] is None
        assert leg["typed_absence"] is not None


# ---------------------------------------------------------------------------
# M4 — correction-path routing (identity law: at most one observation per event_id)
# ---------------------------------------------------------------------------

def test_m4_append_observation_refuses_second_observation_same_event_id(tmp_path):
    p = tmp_path / "recon_m4a.jsonl"
    trig = _mk_ws("TOL", cutoff="2026-05-01T20:00:00Z", net_orders_current=30, net_orders_prior=28,
                  cancel_current=5.0, cancel_prior=6.0)
    packet1 = m.build_observation_packet(
        trigger_ticker="TOL", trigger_workspace=trig,
        issuer_workspaces={"DHI": None, "PHM": None, "KBH": None, "TOL": trig},
        activation_started_at=ACTIVATION_TS,
    )
    row1, appended1 = m.append_observation(
        packet1, path=p, reconstruction=True, trigger_lifecycle_state="complete", trigger_source_form="8-K",
    )
    assert appended1 is True

    # 8-K/A shape: SAME event_id, a NEW decision_cutoff.
    revised_trig = dict(trig)
    revised_trig["lifecycle"] = {"state": "results_released", "source_available_at": "2026-05-03T20:00:00Z"}
    packet2 = m.build_observation_packet(
        trigger_ticker="TOL", trigger_workspace=revised_trig,
        issuer_workspaces={"DHI": None, "PHM": None, "KBH": None, "TOL": revised_trig},
        activation_started_at=ACTIVATION_TS,
    )
    assert packet2["trigger"]["event_id"] == packet1["trigger"]["event_id"]
    assert packet2["trigger"]["decision_cutoff"] != packet1["trigger"]["decision_cutoff"]
    with pytest.raises(m.ProspectiveLedgerError, match="already has an observation"):
        m.append_observation(packet2, path=p, reconstruction=True)
    # Still exactly one observation row.
    assert sum(1 for r in m.load_rows(p) if r["row_kind"] == "observation") == 1


def test_m4_find_observation_by_event_id(tmp_path):
    p = tmp_path / "recon_m4_find.jsonl"
    assert m.find_observation_by_event_id("evt_cik0000794170_2026q2_results", p) is None

    trig = _mk_ws("TOL", cutoff="2026-05-01T20:00:00Z", net_orders_current=30, net_orders_prior=28,
                  cancel_current=5.0, cancel_prior=6.0)
    packet = m.build_observation_packet(
        trigger_ticker="TOL", trigger_workspace=trig,
        issuer_workspaces={"DHI": None, "PHM": None, "KBH": None, "TOL": trig},
        activation_started_at=ACTIVATION_TS,
    )
    row, _ = m.append_observation(
        packet, path=p, reconstruction=True, trigger_lifecycle_state="complete", trigger_source_form="8-K",
    )

    # find_observation_by_event_id ignores decision_cutoff entirely — even a
    # WRONG cutoff still finds the row, unlike find_observation (exact-key).
    found = m.find_observation_by_event_id(packet["trigger"]["event_id"], p)
    assert found is not None
    assert found["observation_id"] == row["observation_id"]
    assert m.find_observation(packet["trigger"]["event_id"], "1999-01-01T00:00:00Z", p) is None
    assert m.find_observation_by_event_id("evt_cik0000000000_2026q1_results", p) is None


# ---------------------------------------------------------------------------
# N3 — append_observation on a SAME-(event_id, decision_cutoff) collision:
# a genuinely identical rebuild stays a no-op; a materially different one
# must RAISE, never silently trust the key over the content.
# ---------------------------------------------------------------------------

def test_n3_exact_key_identical_rebuild_stays_a_noop(tmp_path):
    p = tmp_path / "recon_n3_noop.jsonl"
    trig = _mk_ws("KBH", cutoff="2026-05-01T20:00:00Z", net_orders_current=100, net_orders_prior=90,
                  cancel_current=10.0, cancel_prior=12.0, generation_id="a" * 24)
    packet = m.build_observation_packet(
        trigger_ticker="KBH", trigger_workspace=trig,
        issuer_workspaces={"DHI": None, "PHM": None, "KBH": trig, "TOL": None},
        activation_started_at=ACTIVATION_TS,
    )
    row1, appended1 = m.append_observation(
        packet, path=p, reconstruction=True, trigger_lifecycle_state="complete", trigger_source_form="8-K",
    )
    assert appended1 is True

    # A second call with the byte-identical inputs (same trigger workspace,
    # hence same event_id AND same decision_cutoff) — genuinely nothing
    # changed, must stay a silent no-op.
    row2, appended2 = m.append_observation(packet, path=p, reconstruction=True)
    assert appended2 is False
    assert row2["observation_id"] == row1["observation_id"]
    assert sum(1 for r in m.load_rows(p) if r["row_kind"] == "observation") == 1


def test_n3_exact_key_materially_different_rebuild_raises(tmp_path, monkeypatch):
    p = tmp_path / "recon_n3_raise.jsonl"
    trig = _mk_ws("KBH", cutoff="2026-05-01T20:00:00Z", net_orders_current=100, net_orders_prior=90,
                  cancel_current=10.0, cancel_prior=12.0, generation_id="a" * 24)
    packet1 = m.build_observation_packet(
        trigger_ticker="KBH", trigger_workspace=trig,
        issuer_workspaces={"DHI": None, "PHM": None, "KBH": trig, "TOL": None},
        activation_started_at=ACTIVATION_TS,
    )
    row1, appended1 = m.append_observation(
        packet1, path=p, reconstruction=True, trigger_lifecycle_state="complete", trigger_source_form="8-K",
    )
    assert appended1 is True

    # Force a SAME (event_id, decision_cutoff) key but a materially
    # different derived per-issuer state, by monkeypatching
    # packet_materially_differs to report True for this call — this is the
    # anomalous shape (same key, different content) that should never arise
    # from a genuine rebuild but must never be silently trusted if it does.
    monkeypatch.setattr(m, "packet_materially_differs", lambda *a, **k: True)
    with pytest.raises(m.ProspectiveLedgerError, match="MATERIALLY DIFFERS"):
        m.append_observation(packet1, path=p, reconstruction=True)
    # The original row is untouched — still exactly one observation.
    assert sum(1 for r in m.load_rows(p) if r["row_kind"] == "observation") == 1


def test_m4_packet_materially_differs_generation_gate():
    trig = _mk_ws("KBH", cutoff="2026-05-01T20:00:00Z", net_orders_current=100, net_orders_prior=90,
                  cancel_current=10.0, cancel_prior=12.0, generation_id="a" * 24)
    packet_orig = m.build_observation_packet(
        trigger_ticker="KBH", trigger_workspace=trig,
        issuer_workspaces={"DHI": None, "PHM": None, "KBH": trig, "TOL": None},
        activation_started_at=ACTIVATION_TS,
    )
    original_row = dict(packet_orig)
    original_row["observation_id"] = "obs_fake"

    # Same generation_id, everything else identical -> NOT material.
    same_gen_packet = m.build_observation_packet(
        trigger_ticker="KBH", trigger_workspace=trig,
        issuer_workspaces={"DHI": None, "PHM": None, "KBH": trig, "TOL": None},
        activation_started_at=ACTIVATION_TS,
    )
    assert m.packet_materially_differs(original_row, same_gen_packet, "KBH") is False

    # New generation_id but IDENTICAL derived facts -> NOT material (cosmetic republish).
    cosmetic_trig = _mk_ws("KBH", cutoff="2026-05-01T20:00:00Z", net_orders_current=100, net_orders_prior=90,
                            cancel_current=10.0, cancel_prior=12.0, generation_id="b" * 24)
    cosmetic_packet = m.build_observation_packet(
        trigger_ticker="KBH", trigger_workspace=cosmetic_trig,
        issuer_workspaces={"DHI": None, "PHM": None, "KBH": cosmetic_trig, "TOL": None},
        activation_started_at=ACTIVATION_TS,
    )
    assert m.packet_materially_differs(original_row, cosmetic_packet, "KBH") is False

    # New generation_id AND a genuinely different derived fact -> MATERIAL.
    changed_trig = _mk_ws("KBH", cutoff="2026-05-01T20:00:00Z", net_orders_current=999, net_orders_prior=90,
                           cancel_current=10.0, cancel_prior=12.0, generation_id="c" * 24)
    changed_packet = m.build_observation_packet(
        trigger_ticker="KBH", trigger_workspace=changed_trig,
        issuer_workspaces={"DHI": None, "PHM": None, "KBH": changed_trig, "TOL": None},
        activation_started_at=ACTIVATION_TS,
    )
    assert m.packet_materially_differs(original_row, changed_packet, "KBH") is True


# ---------------------------------------------------------------------------
# B3 — network failure vs not-published disposition (builder-level)
# ---------------------------------------------------------------------------

def test_b3_disposition_found_not_published_fetch_failed():
    import scripts.build_cycle_pattern_imce_prospective as b

    def stub_found(event_id):
        return {"event_id": event_id, "lifecycle": {"source_available_at": "2026-01-01T00:00:00Z"}}

    def stub_not_published(event_id):
        raise b._NotPublished("clean 404")

    def stub_network_error(event_id):
        raise TimeoutError("connection timed out")

    ws, disp = b._load_workspace_with_disposition("e1", fetch=stub_found)
    assert disp == "found" and ws is not None

    ws, disp = b._load_workspace_with_disposition("e1", fetch=stub_not_published)
    assert disp == "not_published" and ws is None

    ws, disp = b._load_workspace_with_disposition("e1", fetch=stub_network_error)
    assert disp == "fetch_failed" and ws is None


def test_b3_bare_invocation_refuses_and_writes_nothing(tmp_path, monkeypatch):
    """A stub network-error fetch -> zero rows appended, production never
    touched (also proves the production-flag law end to end)."""
    import scripts.build_cycle_pattern_imce_prospective as b

    fake_prod = tmp_path / "fake_prod_b3.jsonl"
    monkeypatch.setattr(m, "PRODUCTION_PATH", fake_prod)
    monkeypatch.setattr("engine.cycle_pattern.imce_prospective.PRODUCTION_PATH", fake_prod)

    summary = b.run()  # production=False by default
    assert summary["production"] is False
    assert summary["activated"] is False
    assert not fake_prod.exists()


def test_b3_fetch_failed_defers_entire_run(monkeypatch, tmp_path):
    import scripts.build_cycle_pattern_imce_prospective as b

    fake_prod = tmp_path / "fake_prod_b3b.jsonl"
    monkeypatch.setattr(m, "PRODUCTION_PATH", fake_prod)
    monkeypatch.setattr("engine.cycle_pattern.imce_prospective.PRODUCTION_PATH", fake_prod)

    def fake_fetch_all_candidates(today):
        # One genuine not_published, one genuine fetch_failed.
        dispositions = {
            "DHI": {"evt_1": "not_published"},
            "PHM": {"evt_2": "fetch_failed"},
            "KBH": {}, "TOL": {},
        }
        found = {"DHI": [], "PHM": [], "KBH": [], "TOL": []}
        return found, dispositions

    monkeypatch.setattr(b, "_fetch_all_candidates", fake_fetch_all_candidates)
    summary = b.run(production=True)
    assert summary["deferred_fetch_failed"] == ["evt_2"]
    assert summary["activated"] is False  # activation never stamped this run
    assert not fake_prod.exists()


def test_b3_not_published_only_proceeds_normally(monkeypatch, tmp_path):
    """A genuine not_published (no fetch_failed anywhere) must NOT defer —
    activation proceeds and the run completes with zero candidates found."""
    import scripts.build_cycle_pattern_imce_prospective as b

    fake_prod = tmp_path / "fake_prod_b3c.jsonl"
    monkeypatch.setattr(m, "PRODUCTION_PATH", fake_prod)
    monkeypatch.setattr("engine.cycle_pattern.imce_prospective.PRODUCTION_PATH", fake_prod)

    def fake_fetch_all_candidates(today):
        dispositions = {"DHI": {"evt_1": "not_published"}, "PHM": {}, "KBH": {}, "TOL": {}}
        found = {"DHI": [], "PHM": [], "KBH": [], "TOL": []}
        return found, dispositions

    monkeypatch.setattr(b, "_fetch_all_candidates", fake_fetch_all_candidates)
    summary = b.run(production=True)
    assert summary["deferred_fetch_failed"] == []
    assert summary["activated"] is True
    assert fake_prod.exists()


# ---------------------------------------------------------------------------
# (i) measurement projection rebuilds from the ledger alone
# ---------------------------------------------------------------------------

def test_measurement_projection_rebuilds_from_ledger(tmp_path, monkeypatch):
    sys.path.insert(0, str(REPO_ROOT))
    import scripts.build_measurement as bm

    p = tmp_path / "recon_measurement.jsonl"
    m.ensure_activation(path=p, reconstruction=True, now=datetime(2026, 1, 1, tzinfo=timezone.utc))
    trig = _mk_ws("KBH", cutoff="2026-05-01T20:00:00Z", net_orders_current=100, net_orders_prior=90,
                  cancel_current=10.0, cancel_prior=12.0)
    packet = m.build_observation_packet(
        trigger_ticker="KBH", trigger_workspace=trig,
        issuer_workspaces={"DHI": None, "PHM": None, "KBH": trig, "TOL": None},
        activation_started_at="2026-01-01T00:00:00Z",
    )
    m.append_observation(
        packet, path=p, reconstruction=True,
        trigger_lifecycle_state="complete", trigger_source_form="8-K",
    )

    monkeypatch.setattr(m, "PRODUCTION_PATH", p)
    monkeypatch.setattr("engine.cycle_pattern.imce_prospective.PRODUCTION_PATH", p)

    proj = bm.build_imce_prospective_projection()
    assert proj["available"] is True
    assert proj["activation_started_at"] == "2026-01-01T00:00:00Z"
    assert proj["n_observations"] == 1
    assert proj["per_issuer_counts"]["KBH"] == 1
    assert proj["n_outcomes"] == 0


def test_measurement_projection_self_defaults_with_no_ledger(tmp_path, monkeypatch):
    p = tmp_path / "does_not_exist.jsonl"
    import scripts.build_measurement as bm
    monkeypatch.setattr("engine.cycle_pattern.imce_prospective.PRODUCTION_PATH", p)
    proj = bm.build_imce_prospective_projection()
    assert proj["available"] is True
    assert proj["activation_started_at"] is None
    assert proj["n_observations"] == 0


# ---------------------------------------------------------------------------
# (j) cycle-pattern authority guard passes with the new reader/writer
# ---------------------------------------------------------------------------

def test_authority_guard_selftest_passes():
    import scripts.check_cycle_pattern_authority as guard

    assert guard._run_selftest(REPO_ROOT) == 0


def test_authority_guard_no_hard_findings_on_new_files():
    import scripts.check_cycle_pattern_authority as guard

    for rel in (
        "engine/cycle_pattern/imce_prospective.py",
        "scripts/build_cycle_pattern_imce_prospective.py",
    ):
        text = (REPO_ROOT / rel).read_text(encoding="utf-8")
        findings = guard.scan(REPO_ROOT, extra_files={rel: text})
        hard = [f for f in findings if f["severity"] == "HARD"]
        assert hard == [], f"{rel}: unexpected HARD authority findings: {hard}"


# ---------------------------------------------------------------------------
# A5C — fail-closed correction detection pending source-revision history
# (Sol A5C review, 2026-08-23, item 1): "Until canonical source-revision
# history is available, A5B must fail closed rather than mint an observation
# from a corrected workspace when no prior observation exists. Activation
# may exist; unsafe observation creation may not."
# ---------------------------------------------------------------------------

def test_a5c_safe_state_constant_is_exactly_complete():
    """Pins the enumerated safe set itself — a future edit widening it must
    do so deliberately, never accidentally."""
    assert m.SAFE_ORIGINAL_LIFECYCLE_STATES == frozenset({"complete"})
    assert m.is_safe_original_lifecycle_state("complete") is True
    assert m.is_safe_original_lifecycle_state("corrected") is False
    assert m.is_safe_original_lifecycle_state(None) is False


def test_a5c_corrected_workspace_with_empty_ledger_is_refused_not_appended(tmp_path, capsys):
    """(a): corrected workspace + empty ledger for that event -> NO
    observation row appended, refusal logged. MAJOR-2/MINOR-4 (Opus
    red-team, 2026-08-23): the warning line is pinned to start-of-line
    (never buried mid-line) and must report the OBSERVED signals verbatim
    (via !r), never an asserted diagnosis — here lifecycle_state="corrected"
    and no source_form was passed (defaults to None, also unsafe)."""
    p = tmp_path / "recon_a5c_refuse.jsonl"
    trig = _mk_ws("DHI", cutoff="2026-05-01T20:00:00Z", net_orders_current=100, net_orders_prior=90,
                  cancel_current=10.0, cancel_prior=12.0, lifecycle_state="corrected")
    packet = m.build_observation_packet(
        trigger_ticker="DHI", trigger_workspace=trig,
        issuer_workspaces={"DHI": trig, "PHM": None, "KBH": None, "TOL": None},
        activation_started_at=ACTIVATION_TS,
    )
    row, appended = m.append_observation(
        packet, path=p, reconstruction=True, trigger_lifecycle_state="corrected",
    )
    assert row is None
    assert appended is False
    assert m.load_rows(p) == []

    out = capsys.readouterr().out
    lines = out.splitlines()
    assert any(line.startswith("::warning title=imce-prospective-unsafe-correction::") for line in lines), out
    warning_line = next(line for line in lines if line.startswith("::warning title=imce-prospective-unsafe-correction::"))
    assert packet["trigger"]["event_id"] in warning_line
    assert "lifecycle_state='corrected'" in warning_line
    assert "source_form=None" in warning_line
    assert "fail-closed pending source-revision history" in warning_line


def test_a5c_sibling_events_unaffected_by_a_refusal(tmp_path):
    """(a, continued): a refusal on one event_id does not taint another."""
    p = tmp_path / "recon_a5c_sibling.jsonl"
    corrected_trig = _mk_ws("DHI", cutoff="2026-05-01T20:00:00Z", net_orders_current=100, net_orders_prior=90,
                             cancel_current=10.0, cancel_prior=12.0, lifecycle_state="corrected")
    corrected_packet = m.build_observation_packet(
        trigger_ticker="DHI", trigger_workspace=corrected_trig,
        issuer_workspaces={"DHI": corrected_trig, "PHM": None, "KBH": None, "TOL": None},
        activation_started_at=ACTIVATION_TS,
    )
    m.append_observation(corrected_packet, path=p, reconstruction=True, trigger_lifecycle_state="corrected")

    safe_trig = _mk_ws("PHM", cutoff="2026-05-01T20:00:00Z", net_orders_current=50, net_orders_prior=45,
                        cancel_current=8.0, cancel_prior=9.0)  # default lifecycle_state="complete"
    safe_packet = m.build_observation_packet(
        trigger_ticker="PHM", trigger_workspace=safe_trig,
        issuer_workspaces={"DHI": None, "PHM": safe_trig, "KBH": None, "TOL": None},
        activation_started_at=ACTIVATION_TS,
    )
    row, appended = m.append_observation(
        safe_packet, path=p, reconstruction=True, trigger_lifecycle_state="complete", trigger_source_form="8-K",
    )
    assert appended is True
    assert row is not None
    assert sum(1 for r in m.load_rows(p) if r["row_kind"] == "observation") == 1


def test_a5c_corrected_workspace_with_existing_prior_observation_still_corrects(tmp_path):
    """(b): when a prior observation DOES exist, a corrected revision
    behaves exactly as before — routes to append_correction, never
    refused."""
    p = tmp_path / "recon_a5c_existing.jsonl"
    trig = _mk_ws("KBH", cutoff="2026-05-01T20:00:00Z", net_orders_current=100, net_orders_prior=90,
                  cancel_current=10.0, cancel_prior=12.0, generation_id="a" * 24)
    packet = m.build_observation_packet(
        trigger_ticker="KBH", trigger_workspace=trig,
        issuer_workspaces={"DHI": None, "PHM": None, "KBH": trig, "TOL": None},
        activation_started_at=ACTIVATION_TS,
    )
    row1, appended1 = m.append_observation(
        packet, path=p, reconstruction=True, trigger_lifecycle_state="complete", trigger_source_form="8-K",
    )
    assert appended1 is True

    revised_trig = _mk_ws("KBH", cutoff="2026-05-01T20:00:00Z", net_orders_current=105, net_orders_prior=90,
                           cancel_current=10.0, cancel_prior=12.0, generation_id="b" * 24,
                           lifecycle_state="corrected")
    revised_packet = m.build_observation_packet(
        trigger_ticker="KBH", trigger_workspace=revised_trig,
        issuer_workspaces={"DHI": None, "PHM": None, "KBH": revised_trig, "TOL": None},
        activation_started_at=ACTIVATION_TS,
    )
    corr = m.append_correction(
        superseded_observation_id=row1["observation_id"],
        corrected_packet=revised_packet,
        reason="source revision test",
        path=p, reconstruction=True,
    )
    assert corr["row_kind"] == "correction"
    assert corr["supersedes_observation_id"] == row1["observation_id"]
    assert sum(1 for r in m.load_rows(p) if r["row_kind"] == "correction") == 1
    assert sum(1 for r in m.load_rows(p) if r["row_kind"] == "observation") == 1


def test_a5c_safe_original_state_mints_observation_as_before(tmp_path):
    """(c): a NON-corrected (safe-original) state behaves exactly as
    today — regression."""
    p = tmp_path / "recon_a5c_safe.jsonl"
    trig = _mk_ws("TOL", cutoff="2026-05-01T20:00:00Z", net_orders_current=30, net_orders_prior=28,
                  cancel_current=5.0, cancel_prior=6.0)  # default lifecycle_state="complete"
    packet = m.build_observation_packet(
        trigger_ticker="TOL", trigger_workspace=trig,
        issuer_workspaces={"DHI": None, "PHM": None, "KBH": None, "TOL": trig},
        activation_started_at=ACTIVATION_TS,
    )
    row, appended = m.append_observation(
        packet, path=p, reconstruction=True, trigger_lifecycle_state="complete", trigger_source_form="8-K",
    )
    assert appended is True
    assert row is not None
    assert sum(1 for r in m.load_rows(p) if r["row_kind"] == "observation") == 1


def test_a5c_builder_happy_path_appends_a_real_observation(monkeypatch, tmp_path):
    """MAJOR-3 (Opus red-team, 2026-08-23): the whole A5C test surface
    previously only ever asserted n_observations_appended == 0 — a builder
    bug that silently refused EVERY candidate forever (e.g. reading the
    lifecycle/form off the wrong key) would leave the suite green. This
    proves the SAFE path through the real builder: a production-mode run
    against a workspace with lifecycle_state="complete" and
    source_form="8-K" appends exactly one observation row to the temp
    production path."""
    import scripts.build_cycle_pattern_imce_prospective as b

    fake_prod = tmp_path / "fake_prod_a5c_happy.jsonl"
    monkeypatch.setattr(m, "PRODUCTION_PATH", fake_prod)
    monkeypatch.setattr("engine.cycle_pattern.imce_prospective.PRODUCTION_PATH", fake_prod)

    m.ensure_activation(path=fake_prod, reconstruction=False, production=True,
                         now=datetime(2020, 1, 1, tzinfo=timezone.utc))

    safe_ws = _mk_ws("TOL", cutoff="2026-05-01T20:00:00Z", net_orders_current=30, net_orders_prior=28,
                      cancel_current=5.0, cancel_prior=6.0)  # default lifecycle_state="complete", form="8-K"

    def fake_fetch_all_candidates(today):
        dispositions = {"TOL": {safe_ws["event_id"]: "found"}, "DHI": {}, "PHM": {}, "KBH": {}}
        found = {"DHI": [], "PHM": [], "KBH": [], "TOL": [safe_ws]}
        return found, dispositions

    monkeypatch.setattr(b, "_fetch_all_candidates", fake_fetch_all_candidates)
    monkeypatch.setattr(b, "harvest_event_revisions", _stub_revision_history(safe_ws))
    summary = b.run(production=True)
    assert summary["errors"] == []
    assert summary["n_observations_appended"] == 1
    assert summary["n_observations_refused_unsafe_correction"] == 0
    rows = m.load_rows(fake_prod)
    assert sum(1 for r in rows if r["row_kind"] == "observation") == 1


def test_a5c_builder_harvests_all_candidates_in_exactly_one_walk(monkeypatch, tmp_path):
    """Production incident addendum (2026-08-23): run() must call
    harvest_event_revisions EXACTLY ONCE per run, covering EVERY candidate
    across every ticker in that ONE call — never once per candidate. A
    live measurement found a single-event chain walk cost 153 SECONDS
    against the post-incident ~170-generation backfilled chain; calling it
    once per candidate (the former shape this replaces) would multiply
    that by the candidate count every night (~8 candidates => ~20 min)."""
    import scripts.build_cycle_pattern_imce_prospective as b

    fake_prod = tmp_path / "fake_prod_a5c_one_walk.jsonl"
    monkeypatch.setattr(m, "PRODUCTION_PATH", fake_prod)
    monkeypatch.setattr("engine.cycle_pattern.imce_prospective.PRODUCTION_PATH", fake_prod)
    m.ensure_activation(path=fake_prod, reconstruction=False, production=True,
                         now=datetime(2020, 1, 1, tzinfo=timezone.utc))

    tol_ws = _mk_ws("TOL", cutoff="2026-05-01T20:00:00Z", net_orders_current=30, net_orders_prior=28,
                     cancel_current=5.0, cancel_prior=6.0)  # default lifecycle_state="complete", form="8-K"
    dhi_ws = _mk_ws("DHI", cutoff="2026-05-01T20:00:00Z", net_orders_current=100, net_orders_prior=90,
                     cancel_current=10.0, cancel_prior=12.0)

    def fake_fetch_all_candidates(today):
        dispositions = {
            "TOL": {tol_ws["event_id"]: "found"}, "DHI": {dhi_ws["event_id"]: "found"},
            "PHM": {}, "KBH": {},
        }
        found = {"DHI": [dhi_ws], "PHM": [], "KBH": [], "TOL": [tol_ws]}
        return found, dispositions

    monkeypatch.setattr(b, "_fetch_all_candidates", fake_fetch_all_candidates)

    real_harvester = _stub_revision_history(tol_ws, dhi_ws)
    calls: list[set] = []

    def counting_harvester(event_ids):
        calls.append({str(e) for e in event_ids})
        return real_harvester(event_ids)

    monkeypatch.setattr(b, "harvest_event_revisions", counting_harvester)
    summary = b.run(production=True)
    assert summary["errors"] == []
    assert summary["n_observations_appended"] == 2
    assert len(calls) == 1  # exactly ONE walk this run
    assert calls[0] == {tol_ws["event_id"], dhi_ws["event_id"]}  # covering EVERY candidate in that one call


def test_a5c_safe_state_and_form_constants_stay_inside_the_real_event_vocabulary():
    """MINOR-6 (Opus red-team, 2026-08-23): pins SAFE_ORIGINAL_LIFECYCLE_STATES
    against the REAL production state vocabulary
    (engine.company_intelligence.events.EVENT_STATES) so a fictional fixture
    state (like the pre-fix "results_released" placeholder) can never
    recur as the safe set's basis."""
    from engine.company_intelligence.events import EVENT_STATES

    assert "complete" in EVENT_STATES
    assert m.SAFE_ORIGINAL_LIFECYCLE_STATES <= EVENT_STATES


def test_a5c_refusal_does_not_defer_the_run_or_block_activation(monkeypatch, tmp_path):
    """(d): a refusal must NOT join failed_ids / trigger the fetch_failed
    all-or-nothing deferral, and must NOT block ensure_activation. Exercised
    at the builder level."""
    import scripts.build_cycle_pattern_imce_prospective as b

    fake_prod = tmp_path / "fake_prod_a5c.jsonl"
    monkeypatch.setattr(m, "PRODUCTION_PATH", fake_prod)
    monkeypatch.setattr("engine.cycle_pattern.imce_prospective.PRODUCTION_PATH", fake_prod)

    # Pre-stamp activation well BEFORE the candidate's decision_cutoff (real
    # wall-clock "now" would otherwise postdate a 2026-05-01 cutoff and the
    # builder's own pre-activation trigger fence would skip the candidate
    # before ever reaching append_observation — unrelated to this law).
    m.ensure_activation(path=fake_prod, reconstruction=False, production=True,
                         now=datetime(2020, 1, 1, tzinfo=timezone.utc))

    corrected_ws = _mk_ws("DHI", cutoff="2026-05-01T20:00:00Z", net_orders_current=100, net_orders_prior=90,
                           cancel_current=10.0, cancel_prior=12.0, lifecycle_state="corrected")

    def fake_fetch_all_candidates(today):
        dispositions = {"DHI": {corrected_ws["event_id"]: "found"}, "PHM": {}, "KBH": {}, "TOL": {}}
        found = {"DHI": [corrected_ws], "PHM": [], "KBH": [], "TOL": []}
        return found, dispositions

    monkeypatch.setattr(b, "_fetch_all_candidates", fake_fetch_all_candidates)
    monkeypatch.setattr(b, "harvest_event_revisions", _stub_revision_history(corrected_ws))
    summary = b.run(production=True)
    assert summary["deferred_fetch_failed"] == []
    assert summary["activated"] is True
    assert summary["n_observations_appended"] == 0
    assert summary["n_observations_refused_unsafe_correction"] == 1
    assert summary["errors"] == []
    assert fake_prod.exists()  # activation WAS written
    assert m.load_rows(fake_prod) == [m.activation_row(fake_prod)]  # only the activation row


def test_a5c_refusal_is_idempotent_across_reruns(monkeypatch, tmp_path):
    """(e): two consecutive nightly runs over the same corrected/no-prior
    candidate append ZERO rows both times — refusals are log-only, never a
    new row kind."""
    import scripts.build_cycle_pattern_imce_prospective as b

    fake_prod = tmp_path / "fake_prod_a5c_idem.jsonl"
    monkeypatch.setattr(m, "PRODUCTION_PATH", fake_prod)
    monkeypatch.setattr("engine.cycle_pattern.imce_prospective.PRODUCTION_PATH", fake_prod)

    # See test_a5c_refusal_does_not_defer_the_run_or_block_activation for why
    # activation must be pre-stamped early relative to the candidate cutoff.
    m.ensure_activation(path=fake_prod, reconstruction=False, production=True,
                         now=datetime(2020, 1, 1, tzinfo=timezone.utc))

    corrected_ws = _mk_ws("PHM", cutoff="2026-05-01T20:00:00Z", net_orders_current=50, net_orders_prior=45,
                           cancel_current=8.0, cancel_prior=9.0, lifecycle_state="corrected")

    def fake_fetch_all_candidates(today):
        dispositions = {"PHM": {corrected_ws["event_id"]: "found"}, "DHI": {}, "KBH": {}, "TOL": {}}
        found = {"DHI": [], "PHM": [corrected_ws], "KBH": [], "TOL": []}
        return found, dispositions

    monkeypatch.setattr(b, "_fetch_all_candidates", fake_fetch_all_candidates)
    monkeypatch.setattr(b, "harvest_event_revisions", _stub_revision_history(corrected_ws))
    summary1 = b.run(production=True)
    rows_after_1 = m.load_rows(fake_prod)
    summary2 = b.run(production=True)
    rows_after_2 = m.load_rows(fake_prod)

    assert summary1["n_observations_refused_unsafe_correction"] == 1
    assert summary2["n_observations_refused_unsafe_correction"] == 1
    assert sum(1 for r in rows_after_1 if r["row_kind"] == "observation") == 0
    assert sum(1 for r in rows_after_2 if r["row_kind"] == "observation") == 0
    assert rows_after_1 == rows_after_2  # nothing new appended the second run


@pytest.mark.parametrize("unknown_state", [
    None, "", "results_released", "derived_ready", "distributed",
    "completed_partial", "discovered", "future_state_v2",
])
def test_a5c_unknown_or_future_lifecycle_state_is_treated_as_unsafe(tmp_path, unknown_state):
    """(f): fail-closed vocabulary — anything OTHER than the enumerated
    safe-original set is unsafe, including states this module has never
    seen a production writer emit. trigger_source_form is pinned SAFE
    ("8-K") so the refusal is attributable purely to the state signal, not
    incidentally to a second unsafe signal."""
    assert m.is_safe_original_lifecycle_state(unknown_state) is False

    p = tmp_path / "recon_a5c_unknown.jsonl"
    trig = _mk_ws("KBH", cutoff="2026-05-01T20:00:00Z", net_orders_current=100, net_orders_prior=90,
                  cancel_current=10.0, cancel_prior=12.0)
    packet = m.build_observation_packet(
        trigger_ticker="KBH", trigger_workspace=trig,
        issuer_workspaces={"DHI": None, "PHM": None, "KBH": trig, "TOL": None},
        activation_started_at=ACTIVATION_TS,
    )
    row, appended = m.append_observation(
        packet, path=p, reconstruction=True,
        trigger_lifecycle_state=unknown_state, trigger_source_form="8-K",
    )
    assert row is None
    assert appended is False
    assert m.load_rows(p) == []


@pytest.mark.parametrize("unsafe_form", [None, "", "8-K/A", "10-Q", "6-K", "8-k"])
def test_a5c_missing_or_wrong_source_form_is_treated_as_unsafe(tmp_path, unsafe_form):
    """A5C BLOCKER-1 (1c, Opus red-team 2026-08-23): trigger_source_form
    must be EXACTLY "8-K" — missing, blank, an actual amendment ("8-K/A"),
    an unrelated form, or even a case variant, are all unsafe. Pinned SAFE
    ("complete") lifecycle_state so the refusal is attributable purely to
    the form signal."""
    assert m.is_safe_original_source_form(unsafe_form) is False

    p = tmp_path / "recon_a5c_unsafe_form.jsonl"
    trig = _mk_ws("DHI", cutoff="2026-05-01T20:00:00Z", net_orders_current=100, net_orders_prior=90,
                  cancel_current=10.0, cancel_prior=12.0)
    packet = m.build_observation_packet(
        trigger_ticker="DHI", trigger_workspace=trig,
        issuer_workspaces={"DHI": trig, "PHM": None, "KBH": None, "TOL": None},
        activation_started_at=ACTIVATION_TS,
    )
    row, appended = m.append_observation(
        packet, path=p, reconstruction=True,
        trigger_lifecycle_state="complete", trigger_source_form=unsafe_form,
    )
    assert row is None
    assert appended is False
    assert m.load_rows(p) == []


def test_a5c_builder_end_to_end_refuses_a_workspace_missing_its_form(monkeypatch, tmp_path):
    """NEW-3 (Opus red-team round 2, 2026-08-23): pins the FAIL-REFUSE
    direction end to end through the real builder — before this test, a
    mutation making _issuer_release_source_form always return "8-K"
    (instead of reading the workspace's real source row) survived all 134
    tests, because nothing drove b.run(production=True) over a workspace
    whose issuer_release row genuinely lacks "form" and asserted the
    REFUSAL outcome specifically. lifecycle_state is pinned SAFE
    ("complete") so the refusal is attributable purely to the missing form."""
    import scripts.build_cycle_pattern_imce_prospective as b

    fake_prod = tmp_path / "fake_prod_a5c_missing_form.jsonl"
    monkeypatch.setattr(m, "PRODUCTION_PATH", fake_prod)
    monkeypatch.setattr("engine.cycle_pattern.imce_prospective.PRODUCTION_PATH", fake_prod)
    m.ensure_activation(path=fake_prod, reconstruction=False, production=True,
                         now=datetime(2020, 1, 1, tzinfo=timezone.utc))

    no_form_ws = _mk_ws("PHM", cutoff="2026-05-01T20:00:00Z", net_orders_current=50, net_orders_prior=45,
                         cancel_current=8.0, cancel_prior=9.0, source_form=None)
    assert b._issuer_release_source_form(no_form_ws) is None

    def fake_fetch_all_candidates(today):
        dispositions = {"PHM": {no_form_ws["event_id"]: "found"}, "DHI": {}, "KBH": {}, "TOL": {}}
        found = {"DHI": [], "PHM": [no_form_ws], "KBH": [], "TOL": []}
        return found, dispositions

    monkeypatch.setattr(b, "_fetch_all_candidates", fake_fetch_all_candidates)
    monkeypatch.setattr(b, "harvest_event_revisions", _stub_revision_history(no_form_ws))
    summary = b.run(production=True)
    assert summary["errors"] == []
    assert summary["n_observations_appended"] == 0
    assert summary["n_observations_refused_unsafe_correction"] == 1
    assert sum(1 for r in m.load_rows(fake_prod) if r["row_kind"] == "observation") == 0


def test_a5c_builder_end_to_end_refuses_a_workspace_missing_its_lifecycle_state(monkeypatch, tmp_path):
    """NEW-3 (Opus red-team round 2, 2026-08-23): sibling to the form test
    above — pins that a mutation defaulting the builder's lifecycle read to
    `or "complete"` would be caught. source_form is pinned SAFE ("8-K") so
    the refusal is attributable purely to the missing lifecycle state."""
    import scripts.build_cycle_pattern_imce_prospective as b

    fake_prod = tmp_path / "fake_prod_a5c_missing_state.jsonl"
    monkeypatch.setattr(m, "PRODUCTION_PATH", fake_prod)
    monkeypatch.setattr("engine.cycle_pattern.imce_prospective.PRODUCTION_PATH", fake_prod)
    m.ensure_activation(path=fake_prod, reconstruction=False, production=True,
                         now=datetime(2020, 1, 1, tzinfo=timezone.utc))

    no_state_ws = _mk_ws("KBH", cutoff="2026-05-01T20:00:00Z", net_orders_current=100, net_orders_prior=90,
                          cancel_current=10.0, cancel_prior=12.0, lifecycle_state=None)

    def fake_fetch_all_candidates(today):
        dispositions = {"KBH": {no_state_ws["event_id"]: "found"}, "DHI": {}, "PHM": {}, "TOL": {}}
        found = {"DHI": [], "PHM": [], "KBH": [no_state_ws], "TOL": []}
        return found, dispositions

    monkeypatch.setattr(b, "_fetch_all_candidates", fake_fetch_all_candidates)
    monkeypatch.setattr(b, "harvest_event_revisions", _stub_revision_history(no_state_ws))
    summary = b.run(production=True)
    assert summary["errors"] == []
    assert summary["n_observations_appended"] == 0
    assert summary["n_observations_refused_unsafe_correction"] == 1
    assert sum(1 for r in m.load_rows(fake_prod) if r["row_kind"] == "observation") == 0


def test_a5c_frozen_schema_whitelist_unaffected():
    """(g): the packet schema/whitelist is untouched by this law — the
    lifecycle state travels into append_observation as a function parameter,
    never as a new packet key."""
    packet = _whitelist_packet()
    assert set(packet.keys()) == _FROZEN_TOP_LEVEL_KEYS
    assert set(packet["trigger"].keys()) == _FROZEN_TRIGGER_KEYS
    assert set(packet["m_t"].keys()) == _FROZEN_MT_KEYS


# ---------------------------------------------------------------------------
# IMCE A5C — E: eligibility-by-earliest-revision; F: ordered replay;
# G: contributor selection walks the chain, never a future correction.
# ---------------------------------------------------------------------------

def test_e_post_activation_amendment_on_a_pre_activation_event_mints_nothing(monkeypatch, tmp_path):
    """Mutation-kill (1): a post-activation 8-K/A on a pre-activation event
    must NEVER mint an observation — the EARLIEST known revision decides
    eligibility, permanently (E1/E2/E3), even though the discovered
    "current" revision (the amendment) is itself post-activation."""
    import scripts.build_cycle_pattern_imce_prospective as b

    fake_prod = tmp_path / "fake_prod_e_eligibility.jsonl"
    monkeypatch.setattr(m, "PRODUCTION_PATH", fake_prod)
    monkeypatch.setattr("engine.cycle_pattern.imce_prospective.PRODUCTION_PATH", fake_prod)
    m.ensure_activation(path=fake_prod, reconstruction=False, production=True,
                         now=datetime(2020, 1, 1, tzinfo=timezone.utc))

    original_ws = _mk_ws("DHI", cutoff="2019-06-01T00:00:00Z", net_orders_current=100, net_orders_prior=90,
                          cancel_current=10.0, cancel_prior=12.0, generation_id="a" * 24)
    amendment_ws = _mk_ws("DHI", cutoff="2026-05-01T00:00:00Z", net_orders_current=105, net_orders_prior=90,
                           cancel_current=10.0, cancel_prior=12.0, generation_id="b" * 24, source_form="8-K/A")

    def fake_fetch_all_candidates(today):
        dispositions = {"DHI": {amendment_ws["event_id"]: "found"}, "PHM": {}, "KBH": {}, "TOL": {}}
        found = {"DHI": [amendment_ws], "PHM": [], "KBH": [], "TOL": []}
        return found, dispositions

    monkeypatch.setattr(b, "_fetch_all_candidates", fake_fetch_all_candidates)
    monkeypatch.setattr(
        b, "harvest_event_revisions",
        _stub_revision_history_ordered(original_ws["event_id"], original_ws, amendment_ws),
    )
    summary = b.run(production=True)
    assert summary["errors"] == []
    assert summary["n_observations_appended"] == 0
    assert summary["n_observations_refused_unsafe_correction"] == 0
    assert summary["n_corrections"] == 0
    assert sum(1 for r in m.load_rows(fake_prod) if r["row_kind"] in ("observation", "correction")) == 0


def test_e_eligibility_survives_an_inverted_chain_order(monkeypatch, tmp_path):
    """BLOCKER-1 (Opus red-team, 2026-08-23): the chain walk's own return
    order is a construction detail, not something eligibility may lean on.
    The revision-history STUB here deliberately returns [amendment,
    original] — newest first, inverted from the real chain-walk contract —
    and eligibility must STILL correctly identify the TRUE earliest
    (original, pre-activation) and refuse. A mutant that reads
    revisions[0] instead of the source_available_at-sorted list dies here
    (revisions[0] would be the POST-activation amendment, which would
    incorrectly mint)."""
    import scripts.build_cycle_pattern_imce_prospective as b

    fake_prod = tmp_path / "fake_prod_e_inverted.jsonl"
    monkeypatch.setattr(m, "PRODUCTION_PATH", fake_prod)
    monkeypatch.setattr("engine.cycle_pattern.imce_prospective.PRODUCTION_PATH", fake_prod)
    m.ensure_activation(path=fake_prod, reconstruction=False, production=True,
                         now=datetime(2020, 1, 1, tzinfo=timezone.utc))

    original_ws = _mk_ws("KBH", cutoff="2019-06-01T00:00:00Z", net_orders_current=100, net_orders_prior=90,
                          cancel_current=10.0, cancel_prior=12.0, generation_id="a" * 24)
    amendment_ws = _mk_ws("KBH", cutoff="2026-05-01T00:00:00Z", net_orders_current=105, net_orders_prior=90,
                           cancel_current=10.0, cancel_prior=12.0, generation_id="b" * 24, source_form="8-K/A")

    def fake_fetch_all_candidates(today):
        dispositions = {"KBH": {amendment_ws["event_id"]: "found"}, "DHI": {}, "PHM": {}, "TOL": {}}
        found = {"DHI": [], "PHM": [], "KBH": [amendment_ws], "TOL": []}
        return found, dispositions

    monkeypatch.setattr(b, "_fetch_all_candidates", fake_fetch_all_candidates)
    # Deliberately INVERTED order: newest (amendment) first, oldest
    # (original) second — the opposite of read_event_source_revisions's own
    # oldest-first contract.
    monkeypatch.setattr(
        b, "harvest_event_revisions",
        _stub_revision_history_ordered(original_ws["event_id"], amendment_ws, original_ws),
    )
    summary = b.run(production=True)
    assert summary["errors"] == []
    assert summary["n_observations_appended"] == 0
    assert summary["n_observations_refused_unsafe_correction"] == 0
    assert summary["n_corrections"] == 0
    assert sum(1 for r in m.load_rows(fake_prod) if r["row_kind"] in ("observation", "correction")) == 0


def test_f_packet_build_failure_on_the_anchor_revision_never_mints_from_a_later_one(monkeypatch, tmp_path):
    """BLOCKER-1 (2nd fix): if the EARLIEST eligible revision's own packet
    build fails, the loop must NEVER fall through and mint from a LATER
    revision instead — the whole event is abandoned for this run (recorded
    as an error), not silently re-anchored on a later cutoff."""
    import scripts.build_cycle_pattern_imce_prospective as b

    fake_prod = tmp_path / "fake_prod_f_anchor_failure.jsonl"
    monkeypatch.setattr(m, "PRODUCTION_PATH", fake_prod)
    monkeypatch.setattr("engine.cycle_pattern.imce_prospective.PRODUCTION_PATH", fake_prod)
    m.ensure_activation(path=fake_prod, reconstruction=False, production=True,
                         now=datetime(2020, 1, 1, tzinfo=timezone.utc))

    # rev1 (earliest) carries NO fiscal_period.calendar_end -- this makes
    # build_observation_packet raise (it requires calendar_end to compute
    # the pooling key) so the "would-be anchor" mint fails. rev2 (later) is
    # otherwise perfectly healthy and would happily mint if the loop
    # incorrectly fell through to it.
    rev1 = _mk_ws("PHM", cutoff="2026-03-01T00:00:00Z", net_orders_current=100, net_orders_prior=90,
                  cancel_current=10.0, cancel_prior=12.0, generation_id="a" * 24, sha256hex="a" * 64)
    rev1["fiscal_period"] = {**rev1["fiscal_period"], "calendar_end": None}
    rev2 = _mk_ws("PHM", cutoff="2026-03-05T00:00:00Z", net_orders_current=105, net_orders_prior=90,
                  cancel_current=10.0, cancel_prior=12.0, generation_id="b" * 24, sha256hex="b" * 64)

    def fake_fetch_all_candidates(today):
        dispositions = {"PHM": {rev2["event_id"]: "found"}, "DHI": {}, "KBH": {}, "TOL": {}}
        found = {"DHI": [], "PHM": [rev2], "KBH": [], "TOL": []}
        return found, dispositions

    monkeypatch.setattr(b, "_fetch_all_candidates", fake_fetch_all_candidates)
    monkeypatch.setattr(
        b, "harvest_event_revisions",
        _stub_revision_history_ordered(rev1["event_id"], rev1, rev2),
    )
    summary = b.run(production=True)
    assert summary["n_observations_appended"] == 0
    assert summary["n_corrections"] == 0
    assert any("packet_build" in err for err in summary["errors"])
    assert sum(1 for r in m.load_rows(fake_prod) if r["row_kind"] in ("observation", "correction")) == 0


def test_e_post_activation_original_is_eligible_and_mints(monkeypatch, tmp_path):
    """Regression pair to the test above: when the EARLIEST revision itself
    is post-activation, the event is eligible and observes normally."""
    import scripts.build_cycle_pattern_imce_prospective as b

    fake_prod = tmp_path / "fake_prod_e_eligible.jsonl"
    monkeypatch.setattr(m, "PRODUCTION_PATH", fake_prod)
    monkeypatch.setattr("engine.cycle_pattern.imce_prospective.PRODUCTION_PATH", fake_prod)
    m.ensure_activation(path=fake_prod, reconstruction=False, production=True,
                         now=datetime(2020, 1, 1, tzinfo=timezone.utc))

    safe_ws = _mk_ws("TOL", cutoff="2026-05-01T20:00:00Z", net_orders_current=30, net_orders_prior=28,
                      cancel_current=5.0, cancel_prior=6.0)

    def fake_fetch_all_candidates(today):
        dispositions = {"TOL": {safe_ws["event_id"]: "found"}, "DHI": {}, "PHM": {}, "KBH": {}}
        found = {"DHI": [], "PHM": [], "KBH": [], "TOL": [safe_ws]}
        return found, dispositions

    monkeypatch.setattr(b, "_fetch_all_candidates", fake_fetch_all_candidates)
    monkeypatch.setattr(b, "harvest_event_revisions", _stub_revision_history(safe_ws))
    summary = b.run(production=True)
    assert summary["n_observations_appended"] == 1


def test_g_contributor_never_uses_a_revision_whose_source_available_at_is_after_the_cutoff():
    """Mutation-kill (5): a contributor's state at a trigger cutoff must be
    the LATEST LAWFUL revision at-or-before that cutoff — never a later
    (future-relative) correction used retrospectively."""
    import scripts.build_cycle_pattern_imce_prospective as b

    early_ws = _mk_ws("PHM", cutoff="2026-04-01T00:00:00Z", net_orders_current=10, net_orders_prior=9,
                       cancel_current=5.0, cancel_prior=6.0)
    late_ws = _mk_ws("PHM", cutoff="2026-06-01T00:00:00Z", net_orders_current=20, net_orders_prior=9,
                      cancel_current=5.0, cancel_prior=6.0)
    found = {"PHM": [late_ws]}
    revision_histories = {late_ws["event_id"]: [_revision_entry(early_ws), _revision_entry(late_ws)]}

    # Cutoff strictly between early and late -- only "early" is lawful.
    selected = b._latest_contributor_revision_at_or_before(
        "PHM", found, revision_histories, "2026-05-01T00:00:00Z",
    )
    assert selected is not None
    assert selected["lifecycle"]["source_available_at"] == "2026-04-01T00:00:00Z"

    # Cutoff BEFORE both -- nothing lawful.
    assert b._latest_contributor_revision_at_or_before(
        "PHM", found, revision_histories, "2026-01-01T00:00:00Z",
    ) is None

    # Cutoff AFTER both -- "late" IS <= this cutoff, so it is legitimately
    # the latest LAWFUL revision (never used when it is AFTER the cutoff,
    # exactly as the first assertion above proves).
    selected2 = b._latest_contributor_revision_at_or_before(
        "PHM", found, revision_histories, "2026-07-01T00:00:00Z",
    )
    assert selected2["lifecycle"]["source_available_at"] == "2026-06-01T00:00:00Z"


def test_f_ordered_replay_mints_from_earliest_then_corrects_only_material_changes(monkeypatch, tmp_path):
    """F1/F2/F3/F4: three revisions accumulated between nightlies — the
    FIRST (earliest) mints THE observation with decision_cutoff pinned to
    its OWN source_available_at; the second (materially different) becomes
    an ordered correction; the third (cosmetic — same derived facts as the
    second) produces NO correction noise. The correction supersedes the
    ANCHOR observation, never a prior correction."""
    import scripts.build_cycle_pattern_imce_prospective as b

    fake_prod = tmp_path / "fake_prod_f_replay.jsonl"
    monkeypatch.setattr(m, "PRODUCTION_PATH", fake_prod)
    monkeypatch.setattr("engine.cycle_pattern.imce_prospective.PRODUCTION_PATH", fake_prod)
    m.ensure_activation(path=fake_prod, reconstruction=False, production=True,
                         now=datetime(2020, 1, 1, tzinfo=timezone.utc))

    rev1 = _mk_ws("KBH", cutoff="2026-03-01T00:00:00Z", net_orders_current=100, net_orders_prior=90,
                  cancel_current=10.0, cancel_prior=12.0, generation_id="a" * 24, sha256hex="a" * 64)
    rev2 = _mk_ws("KBH", cutoff="2026-03-05T00:00:00Z", net_orders_current=200, net_orders_prior=90,
                  cancel_current=10.0, cancel_prior=12.0, generation_id="b" * 24, sha256hex="b" * 64,
                  lifecycle_state="corrected")
    rev3 = _mk_ws("KBH", cutoff="2026-03-10T00:00:00Z", net_orders_current=200, net_orders_prior=90,
                  cancel_current=10.0, cancel_prior=12.0, generation_id="c" * 24, sha256hex="c" * 64,
                  lifecycle_state="corrected")  # cosmetic: SAME derived facts as rev2

    def fake_fetch_all_candidates(today):
        dispositions = {"KBH": {rev3["event_id"]: "found"}, "DHI": {}, "PHM": {}, "TOL": {}}
        found = {"DHI": [], "PHM": [], "KBH": [rev3], "TOL": []}
        return found, dispositions

    monkeypatch.setattr(b, "_fetch_all_candidates", fake_fetch_all_candidates)
    monkeypatch.setattr(
        b, "harvest_event_revisions",
        _stub_revision_history_ordered(rev1["event_id"], rev1, rev2, rev3),
    )
    summary = b.run(production=True)
    assert summary["errors"] == []
    assert summary["n_observations_appended"] == 1
    assert summary["n_corrections"] == 1
    rows = m.load_rows(fake_prod)
    obs = [r for r in rows if r["row_kind"] == "observation"]
    corr = [r for r in rows if r["row_kind"] == "correction"]
    assert len(obs) == 1 and len(corr) == 1
    assert obs[0]["trigger"]["decision_cutoff"] == "2026-03-01T00:00:00Z"
    assert corr[0]["trigger"]["decision_cutoff"] == "2026-03-05T00:00:00Z"
    assert corr[0]["supersedes_observation_id"] == obs[0]["observation_id"]

    # A SECOND nightly run over the SAME (unchanged) revision history is
    # fully idempotent — no new rows.
    summary2 = b.run(production=True)
    assert summary2["n_observations_appended"] == 0
    assert summary2["n_corrections"] == 0
    assert m.load_rows(fake_prod) == rows


def test_tol_sensitivity_flow_through_when_both_facts_present_reconstruction_mode():
    """WORLD STATE sweep item (i): the TOL PR #6307 extraction change means
    _tol_sensitivity's prior-year lookup is now a REAL, resolvable fact once
    the workspace carries the prior-year cell — this pins the CONSUMPTION
    side end to end (extraction itself is issuer_profiles' own PR, untouched
    here)."""
    facts = [
        _fact_present("fact_net_orders_current", 30),
        _fact_present("fact_net_orders_prior_year", 28),
        _fact_present("fact_cancellation_rate_current", 5.0),
        _fact_present("fact_cancellation_rate_prior_year", 6.0),
        _fact_present(
            "fact_cancellation_rate_denominator", _DEFAULT_DENOMINATOR_TEXT["TOL"],
            basis=_DEFAULT_DENOMINATOR_TEXT["TOL"],
        ),
        _fact_present(
            "fact_cancellation_rate_beginning_backlog_sensitivity", 4.2,
            basis="quarterly cancellations as a percentage of beginning-quarter backlog",
        ),
        _fact_present(
            "fact_cancellation_rate_beginning_backlog_sensitivity_prior_year", 3.1,
            basis="quarterly cancellations as a percentage of beginning-quarter backlog",
        ),
    ]
    ws = _mk_ws("TOL", cutoff="2026-05-01T20:00:00Z", facts_override=facts)
    state = m.per_issuer_state(
        "TOL", ws, activation_started_at=ACTIVATION_TS, as_of_cutoff="2026-05-01T20:00:00Z",
        trigger_pooling_key=_trigger_pooling_key(ws),
    )
    assert state["contributor_eligible"] is True
    sensitivity = state["sensitivity"]
    assert sensitivity["current_value"] == 4.2
    assert sensitivity["prior_year_value"] == 3.1
    assert sensitivity["prior_year_absence_reason"] is None
    assert sensitivity["d_cancel_sensitivity"] == "+"
    assert sensitivity["order_softness_sensitivity_basis"] == "MIXED"
