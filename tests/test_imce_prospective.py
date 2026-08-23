"""Tests for engine/cycle_pattern/imce_prospective.py (IMCE A5B).

All fixtures are labelled RECONSTRUCTION — every write in this file targets an
explicit temp path via ``reconstruction=True``; the word "prospective" appears
here only as the dataset's own name, never as a claim about a real event.

No network. Price-leg tests read the REAL committed
data/baskets/ohlcv/{DHI,PHM,KBH,TOL}.parquet files (already on disk, no
network) so the PIT-bound logic is exercised against real bars rather than a
synthetic series.

Coverage (frozen spec TESTS a-j):
  a. activation record idempotence
  b. first-observation-wins + exact-duplicate rerun no-op
  c. correction append + original packet immutability (byte-compare)
  d. activation-law fencing + reconstruction/production path law
  e. M_t verbatim conformance (>=2 floor, tie=>MIXED, missing-never-zero,
     no state carry-forward past a source failure)
  f. R_t PIT admissibility + construction pins + typed absence
  g. label truth table (4/4 cohort, 2-3 named_subset, <2 NOT_RECONSTRUCTABLE)
  h. schema outcome-field blacklist
  i. measurement projection rebuilds from the ledger alone
  j. cycle-pattern authority guard passes with the new reader/writer
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
    denominator="stated denominator",
    generation_id: str = "a" * 24,
    accession: str = "0000000000-26-000001",
    sha256hex: str = "d" * 64,
    facts_override: list[dict] | None = None,
) -> dict:
    if facts_override is not None:
        facts = facts_override
    else:
        facts = [
            _fact_present("fact_net_orders_current", net_orders_current) if net_orders_current is not None
            else _fact_absent("fact_net_orders_current"),
            _fact_present("fact_net_orders_prior_year", net_orders_prior) if net_orders_prior is not None
            else _fact_absent("fact_net_orders_prior_year"),
            _fact_present("fact_cancellation_rate_current", cancel_current) if cancel_current is not None
            else _fact_absent("fact_cancellation_rate_current"),
            _fact_present("fact_cancellation_rate_prior_year", cancel_prior) if cancel_prior is not None
            else _fact_absent("fact_cancellation_rate_prior_year"),
            _fact_present("fact_cancellation_rate_denominator", denominator, basis=denominator),
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
        "fiscal_period": {"year": year, "quarter": quarter, "calendar_end": None},
        "lifecycle": {"state": "results_released", "source_available_at": source_available_at},
        "facts": facts,
        "sources": [{
            "kind": "issuer_release", "source_sha256": sha256hex,
            "filing_key": {"cik": cik, "accession": accession},
        }],
        "generation_id": generation_id,
    }


CIKS = {"DHI": "0000882184", "PHM": "0000822416", "KBH": "0000795266", "TOL": "0000794170"}


def _mk_ws(ticker, *, cutoff, **kwargs):
    return _workspace(ticker=ticker, cik=CIKS[ticker], year=2026, quarter=2, source_available_at=cutoff, **kwargs)


ACTIVATION_TS = "2026-01-01T00:00:00Z"


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
    row1, appended1 = m.append_observation(packet, path=p, reconstruction=True)
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
    row1, _ = m.append_observation(packet, path=p, reconstruction=True)

    original_bytes = p.read_bytes()
    original_lines = original_bytes.splitlines()

    revised_trig = _mk_ws("PHM", cutoff="2026-05-01T20:00:00Z", net_orders_current=101, net_orders_prior=90,
                           cancel_current=10.0, cancel_prior=12.0, sha256hex="b" * 64)
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
    state = m.per_issuer_state("DHI", pre_activation_ws, activation_started_at=activation,
                                as_of_cutoff="2026-07-01T00:00:00Z")
    assert state["contributor_eligible"] is False
    assert state["activation_law"] == "pre_activation_excluded"
    assert state["order_softness"] == "NOT_RECONSTRUCTABLE"

    post_activation_ws = _mk_ws("DHI", cutoff="2026-07-01T00:00:00Z", net_orders_current=100,
                                 net_orders_prior=90, cancel_current=10.0, cancel_prior=12.0)
    state2 = m.per_issuer_state("DHI", post_activation_ws, activation_started_at=activation,
                                 as_of_cutoff="2026-07-01T00:00:00Z")
    assert state2["contributor_eligible"] is True
    assert state2["activation_law"] == "post_activation"


def test_reconstruction_mode_cannot_touch_production_path():
    with pytest.raises(m.ProspectiveLedgerError):
        m.ensure_activation(path=m.PRODUCTION_PATH, reconstruction=True)


def test_production_write_must_target_production_path(tmp_path):
    stray = tmp_path / "not_production.jsonl"
    with pytest.raises(m.ProspectiveLedgerError):
        m.ensure_activation(path=stray, reconstruction=False)


# ---------------------------------------------------------------------------
# (e) M_t verbatim conformance
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
    # A genuine zero-change reading IS "0" (a real, present observation).
    assert m.yoy_sign(100, 100) == "0"
    # A missing input is None, never coerced to "0".
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
    """Statelessness: a workspace with a present fact followed by one with a
    typed absence must NEVER reuse the earlier non-missing state — each call
    is pure over its own input only."""
    good_ws = _mk_ws("KBH", cutoff="2026-05-01T00:00:00Z", net_orders_current=100, net_orders_prior=90,
                      cancel_current=10.0, cancel_prior=12.0)
    good_state = m.per_issuer_state("KBH", good_ws, activation_started_at=ACTIVATION_TS,
                                     as_of_cutoff="2026-06-01T00:00:00Z")
    assert good_state["order_softness"] != "NOT_RECONSTRUCTABLE"

    failed_ws = _mk_ws("KBH", cutoff="2026-08-01T00:00:00Z", net_orders_current=None, net_orders_prior=None,
                        cancel_current=10.0, cancel_prior=12.0)
    failed_state = m.per_issuer_state("KBH", failed_ws, activation_started_at=ACTIVATION_TS,
                                       as_of_cutoff="2026-09-01T00:00:00Z")
    # Independent of the earlier good_state — never "sticky".
    assert failed_state["order_softness"] == "NOT_RECONSTRUCTABLE"
    assert failed_state["d_orders"] is None


def test_tol_sensitivity_diagnostic_present_but_honestly_not_reconstructable():
    ws = _mk_ws("TOL", cutoff="2026-05-01T00:00:00Z", net_orders_current=100, net_orders_prior=90,
                cancel_current=5.0, cancel_prior=6.0)
    state = m.per_issuer_state("TOL", ws, activation_started_at=ACTIVATION_TS, as_of_cutoff="2026-06-01T00:00:00Z")
    assert "sensitivity" in state
    sens = state["sensitivity"]
    assert sens["current_value"] == 4.2
    assert sens["prior_year_value"] is None
    assert sens["d_cancel_sensitivity"] is None
    assert sens["order_softness_sensitivity_basis"] == "NOT_RECONSTRUCTABLE"


# ---------------------------------------------------------------------------
# (f) R_t PIT admissibility + construction pins + typed absence
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
    # The reported last admissible bar's calendar date must be STRICTLY before
    # the cutoff's own calendar date (cutoff is pre-market-close same day).
    assert last_bar[:10] < "2026-06-01"

    # A cutoff comfortably after that day's close DOES admit the same-day bar.
    late_cutoff = datetime(2026, 6, 1, 23, 0, tzinfo=timezone.utc)
    leg2 = m.price_leg_for_ticker("DHI", late_cutoff)
    assert leg2["last_admissible_bar"][:10] <= "2026-06-01"


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
# (h) schema outcome-field blacklist
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("token", sorted(m.FORBIDDEN_OUTCOME_TOKENS))
def test_outcome_blacklist_catches_every_token(token):
    with pytest.raises(m.ProspectiveLedgerError):
        m.assert_no_outcome_fields({"nested": {token: 1.23}})


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
    m.append_observation(packet, path=p, reconstruction=True)

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
