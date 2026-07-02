"""Tests for scripts/backfill_qledger_us.py — W1 US adapters.

Hermetic: all source data is written to tmp_path fixtures; no live data/network.
Covers:
  * ALTDATA adapter — field mapping, direction, idempotency, entry_levels.
  * RADAR adapter  — direction from state, scope_type, legacy horizon_d default,
                     honest-n: each snapshot date becomes its own claim asof.
  * POLICY adapter — rel_return + priceable → gradeable; soft/unpriceable → direction=0.
  * End-to-end idempotency: re-running produces no duplicate claims.
  * D4 dark fraction: direction=0 policy claims are registered (not rejected).
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from engine import qledger as q
from scripts.backfill_qledger_us import (
    _altdata_direction,
    _altdata_entry_levels,
    _policy_direction,
    _radar_direction,
    _radar_scope_type,
    backfill_altdata,
    backfill_policy,
    backfill_radar,
)


# ---------------------------------------------------------------------------
# fixtures — tiny synthetic source files
# ---------------------------------------------------------------------------

def _write_jsonl(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as fh:
        for r in rows:
            fh.write(json.dumps(r) + "\n")


@pytest.fixture
def src_root(tmp_path):
    """Returns a tmp_path already wired with tiny source ledgers."""
    # -- altdata/theses.jsonl --
    altdata_theses = [
        {
            "id": "2026-06-19-CARR-altconv",
            "ticker": "CARR",
            "logged_at": "2026-06-20T01:58:20+00:00",
            "state_asof": "2026-06-19",
            "subject": "CARR alt-data convergence",
            "lean": "overweight",
            "conviction": "low",
            "horizon_d": 63,
            "channels": ["congress_buy"],
            "falsifier": {
                "text": "CARR fails to beat SPY.",
                "check": {"kind": "rel_return", "subject_ticker": "CARR",
                           "vs": "SPY", "op": "<", "threshold": -0.05, "horizon_d": 63},
            },
            "check_by": "2026-09-18",
            "entry_levels": {"CARR": 71.81, "SPY": 746.74},
            "status": "open",
        },
        {
            "id": "2026-06-19-EFX-altconv",
            "ticker": "EFX",
            "logged_at": "2026-06-20T01:58:20+00:00",
            "state_asof": "2026-06-19",
            "lean": "underweight",   # test direction=-1
            "conviction": "low",
            "horizon_d": 21,
            "channels": [],
            "falsifier": {
                "text": "EFX beats SPY.",
                "check": {"kind": "rel_return", "subject_ticker": "EFX",
                           "vs": "SPY", "op": ">", "threshold": 0.0, "horizon_d": 21},
            },
            "check_by": "2026-07-17",
            "entry_levels": {"EFX": 200.0, "SPY": 746.74},
            "status": "open",
        },
    ]
    _write_jsonl(tmp_path / "data" / "altdata" / "theses.jsonl", altdata_theses)

    # -- radar/edge_snapshots.jsonl --
    radar_rows = [
        # two basket rows on same date
        {"date": "2026-06-20", "kind": "basket", "subject": "housing",
         "ticker": "XHB", "edge_score": 76, "state": "POSITIVE_DIVERGENCE"},
        {"date": "2026-06-20", "kind": "basket", "subject": "defense",
         "ticker": "ITA", "edge_score": 52, "state": "NEGATIVE_DIVERGENCE"},
        # ticker row on different date (tests honest-n)
        {"date": "2026-06-21", "kind": "ticker", "subject": "MSFT",
         "ticker": "MSFT", "edge_score": 75, "state": "CONFIRMED_UP"},
        # row with explicit horizon_d
        {"date": "2026-06-22", "kind": "basket", "subject": "ai_agents",
         "ticker": "IGV", "edge_score": 28, "state": "CONFIRMED_DOWN",
         "horizon_d": 21},
    ]
    _write_jsonl(tmp_path / "data" / "radar" / "edge_snapshots.jsonl", radar_rows)

    # -- policy_intent/theses.jsonl --
    policy_theses = [
        # rel_return — will be priceable (monkeypatched below)
        {
            "id": "2026-06-18-065043-3",
            "logged_at": "2026-06-18T07:00:00+00:00",
            "state_asof": "2026-06-18",
            "actor": "admin",
            "subject": "SMH",
            "lean": "overweight",
            "conviction": "low",
            "horizon_d": 90,
            "falsifier": {
                "text": "SMH underperforms SPY.",
                "check": {"kind": "rel_return", "subject_ticker": "SMH",
                           "vs": "SPY", "op": "<", "threshold": -0.05, "horizon_d": 90},
            },
            "check_by": "2026-10-22",
            "entry_levels": {"SMH": 623.97, "SPY": 740.96},
            "status": "open",
        },
        # soft falsifier → direction=0 regardless of priceable
        {
            "id": "2026-06-18-065043-1",
            "logged_at": "2026-06-18T07:00:00+00:00",
            "state_asof": "2026-06-18",
            "actor": "admin",
            "subject": "BIL",
            "lean": "overweight",
            "conviction": "low",
            "horizon_d": 126,
            "falsifier": {
                "text": "Treasury announces coupon increase.",
                "check": {"kind": "soft", "reason": "BIL not scorable"},
            },
            "check_by": "2026-12-11",
            "entry_levels": {},
            "status": "open",
        },
        # underweight → direction=-1 when priceable
        {
            "id": "2026-07-02-092100-4",
            "logged_at": "2026-07-02T09:21:00+00:00",
            "state_asof": "2026-07-02",
            "actor": "admin",
            "subject": "GLD",
            "lean": "underweight",
            "conviction": "low",
            "horizon_d": 63,
            "falsifier": {
                "text": "Gold outperforms.",
                "check": {"kind": "rel_return", "subject_ticker": "GLD",
                           "vs": "SPY", "op": ">", "threshold": 0.0, "horizon_d": 63},
            },
            "check_by": "2026-09-26",
            "entry_levels": {"GLD": 3350.0, "SPY": 750.0},
            "status": "open",
        },
    ]
    _write_jsonl(tmp_path / "data" / "policy_intent" / "theses.jsonl", policy_theses)

    return tmp_path


# ---------------------------------------------------------------------------
# mock price layer
# ---------------------------------------------------------------------------

@pytest.fixture
def priceable_only_smh(monkeypatch, src_root):
    """SMH is priceable; BIL and GLD are not.
    Patches scripts.backfill_qledger_us._close_series (the imported binding
    inside the script module) which is what _ticker_priceable calls.
    """
    import pandas as pd

    def _series(ticker, root):
        if ticker == "SMH":
            idx = pd.bdate_range("2026-01-01", periods=120)
            return pd.Series([600.0 + i for i in range(120)], index=idx)
        return None

    monkeypatch.setattr("scripts.backfill_qledger_us._close_series", _series)
    return src_root


# ---------------------------------------------------------------------------
# unit tests: helpers
# ---------------------------------------------------------------------------

class TestAltdataHelpers:
    def test_direction_overweight(self):
        assert _altdata_direction({"lean": "overweight"}) == 1

    def test_direction_underweight(self):
        assert _altdata_direction({"lean": "underweight"}) == -1

    def test_direction_neutral(self):
        assert _altdata_direction({"lean": "neutral"}) == 0
        assert _altdata_direction({}) == 0

    def test_entry_levels_extracted(self):
        thesis = {"ticker": "CARR", "entry_levels": {"CARR": 71.81, "SPY": 746.74}}
        subj, bench = _altdata_entry_levels(thesis)
        assert subj == pytest.approx(71.81)
        assert bench == pytest.approx(746.74)

    def test_entry_levels_missing(self):
        subj, bench = _altdata_entry_levels({"ticker": "X", "entry_levels": {}})
        assert subj is None
        assert bench is None


class TestRadarHelpers:
    def test_direction_bullish_states(self):
        assert _radar_direction("POSITIVE_DIVERGENCE") == 1
        assert _radar_direction("CONFIRMED_UP") == 1

    def test_direction_bearish_states(self):
        assert _radar_direction("NEGATIVE_DIVERGENCE") == -1
        assert _radar_direction("CONFIRMED_DOWN") == -1

    def test_direction_unknown(self):
        assert _radar_direction("QUIET") == 0
        assert _radar_direction("") == 0

    def test_scope_type_mapping(self):
        assert _radar_scope_type("ticker") == "entity"
        assert _radar_scope_type("basket") == "basket"
        assert _radar_scope_type("other") == "basket"  # default to basket


class TestPolicyHelpers:
    def test_soft_falsifier_is_dark(self):
        thesis = {"lean": "overweight",
                  "falsifier": {"check": {"kind": "soft"}}}
        assert _policy_direction(thesis, priceable=True) == 0

    def test_rel_return_unpriceable_is_dark(self):
        thesis = {"lean": "overweight",
                  "falsifier": {"check": {"kind": "rel_return"}}}
        assert _policy_direction(thesis, priceable=False) == 0

    def test_rel_return_priceable_overweight(self):
        thesis = {"lean": "overweight",
                  "falsifier": {"check": {"kind": "rel_return"}}}
        assert _policy_direction(thesis, priceable=True) == 1

    def test_rel_return_priceable_underweight(self):
        thesis = {"lean": "underweight",
                  "falsifier": {"check": {"kind": "rel_return"}}}
        assert _policy_direction(thesis, priceable=True) == -1


# ---------------------------------------------------------------------------
# integration: ALTDATA backfill
# ---------------------------------------------------------------------------

class TestAltdataBackfill:
    def test_registers_all_theses(self, src_root):
        n = backfill_altdata(src_root)
        assert n == 2
        claims = q.load_claims(src_root)
        assert len(claims) == 2

    def test_desk_is_altdata(self, src_root):
        backfill_altdata(src_root)
        claims = q.load_claims(src_root)
        assert all(c["desk"] == "altdata" for c in claims)

    def test_direction_from_lean(self, src_root):
        backfill_altdata(src_root)
        claims = {c["scope"]["key"]: c for c in q.load_claims(src_root)}
        assert claims["CARR"]["direction"] == 1    # overweight
        assert claims["EFX"]["direction"] == -1   # underweight

    def test_entry_levels_preserved(self, src_root):
        backfill_altdata(src_root)
        claims = {c["scope"]["key"]: c for c in q.load_claims(src_root)}
        carr = claims["CARR"]
        assert carr["entry_levels"]["subject"] == pytest.approx(71.81)
        assert carr["entry_levels"]["bench"] == pytest.approx(746.74)

    def test_timestamp_quality_is_disclosure(self, src_root):
        backfill_altdata(src_root)
        claims = q.load_claims(src_root)
        assert all(c["timestamp_quality"] == "DISCLOSURE_DATE" for c in claims)

    def test_bench_is_spy(self, src_root):
        backfill_altdata(src_root)
        claims = q.load_claims(src_root)
        assert all(c["bench"] == "SPY" for c in claims)

    def test_idempotent_on_rerun(self, src_root):
        backfill_altdata(src_root)
        backfill_altdata(src_root)  # second run
        claims = q.load_claims(src_root)
        assert len(claims) == 2   # no duplicates

    def test_source_id_stored(self, src_root):
        backfill_altdata(src_root)
        claims = q.load_claims(src_root)
        source_ids = {c.get("source_id") for c in claims}
        assert "2026-06-19-CARR-altconv" in source_ids

    def test_all_claims_open_status(self, src_root):
        backfill_altdata(src_root)
        claims = q.load_claims(src_root)
        assert all(c["status"] == "open" for c in claims)


# ---------------------------------------------------------------------------
# integration: RADAR backfill
# ---------------------------------------------------------------------------

class TestRadarBackfill:
    def test_registers_all_snapshots(self, src_root):
        n = backfill_radar(src_root)
        assert n == 4
        claims = q.load_claims(src_root)
        assert len(claims) == 4

    def test_desk_is_radar(self, src_root):
        backfill_radar(src_root)
        claims = q.load_claims(src_root)
        assert all(c["desk"] == "radar" for c in claims)

    def test_direction_from_state(self, src_root):
        backfill_radar(src_root)
        claims = q.load_claims(src_root)
        by_subj = {}
        for c in claims:
            subj = c.get("source_subject") or c["scope"]["key"]
            by_subj[subj] = c["direction"]
        assert by_subj["housing"] == 1    # POSITIVE_DIVERGENCE
        assert by_subj["defense"] == -1   # NEGATIVE_DIVERGENCE
        assert by_subj["MSFT"] == 1       # CONFIRMED_UP
        assert by_subj["ai_agents"] == -1 # CONFIRMED_DOWN

    def test_scope_type_mapping(self, src_root):
        backfill_radar(src_root)
        claims = q.load_claims(src_root)
        by_subj = {c.get("source_subject") or c["scope"]["key"]: c for c in claims}
        assert by_subj["housing"]["scope"]["type"] == "basket"
        assert by_subj["MSFT"]["scope"]["type"] == "entity"

    def test_legacy_horizon_d_default(self, src_root):
        """Rows without horizon_d field should default to RADAR_DEFAULT_HORIZON_D=63."""
        backfill_radar(src_root)
        claims = q.load_claims(src_root)
        by_subj = {c.get("source_subject") or c["scope"]["key"]: c for c in claims}
        assert by_subj["housing"]["horizon_d"] == 63   # legacy, no horizon_d in row
        assert by_subj["ai_agents"]["horizon_d"] == 21  # explicit horizon_d=21

    def test_asof_is_snapshot_date(self, src_root):
        """Each claim's asof must equal its source snapshot date (honest-n dedup)."""
        backfill_radar(src_root)
        claims = q.load_claims(src_root)
        by_subj = {c.get("source_subject") or c["scope"]["key"]: c for c in claims}
        assert by_subj["housing"]["asof"] == "2026-06-20"
        assert by_subj["MSFT"]["asof"] == "2026-06-21"
        assert by_subj["ai_agents"]["asof"] == "2026-06-22"

    def test_three_dates_give_three_n_dates(self, src_root):
        """n_dates should count 3 distinct asof clusters (not 4 obs)."""
        backfill_radar(src_root)
        claims = q.load_claims(src_root)
        dates = {c["asof"] for c in claims}
        assert len(dates) == 3   # 2026-06-20, 2026-06-21, 2026-06-22

    def test_idempotent_on_rerun(self, src_root):
        backfill_radar(src_root)
        backfill_radar(src_root)
        claims = q.load_claims(src_root)
        assert len(claims) == 4

    def test_edge_score_preserved(self, src_root):
        backfill_radar(src_root)
        claims = q.load_claims(src_root)
        by_subj = {c.get("source_subject") or c["scope"]["key"]: c for c in claims}
        assert by_subj["housing"]["edge_score"] == 76

    def test_ticker_is_scope_key(self, src_root):
        """scope.key is the proxy ticker, not the basket_id (so grader can price it)."""
        backfill_radar(src_root)
        claims = q.load_claims(src_root)
        by_subj = {c.get("source_subject"): c for c in claims if c.get("source_subject")}
        assert by_subj["housing"]["scope"]["key"] == "XHB"


# ---------------------------------------------------------------------------
# integration: POLICY backfill
# ---------------------------------------------------------------------------

class TestPolicyBackfill:
    def test_registers_all_theses(self, priceable_only_smh):
        root = priceable_only_smh
        n = backfill_policy(root)
        assert n == 3
        claims = q.load_claims(root)
        assert len(claims) == 3

    def test_desk_is_policy(self, priceable_only_smh):
        root = priceable_only_smh
        backfill_policy(root)
        claims = q.load_claims(root)
        assert all(c["desk"] == "policy" for c in claims)

    def test_gradeable_rel_return_priceable(self, priceable_only_smh):
        """SMH: rel_return + priceable → direction=+1, ungradeable_soft=False."""
        root = priceable_only_smh
        backfill_policy(root)
        claims = {c["scope"]["key"]: c for c in q.load_claims(root)}
        smh = claims["SMH"]
        assert smh["direction"] == 1
        assert not smh.get("ungradeable_soft")

    def test_soft_falsifier_is_salience_only(self, priceable_only_smh):
        """BIL: soft falsifier → direction=0, ungradeable_soft=True."""
        root = priceable_only_smh
        backfill_policy(root)
        claims = {c["scope"]["key"]: c for c in q.load_claims(root)}
        bil = claims["BIL"]
        assert bil["direction"] == 0
        assert bil.get("ungradeable_soft") is True

    def test_unpriceable_is_salience_only(self, priceable_only_smh):
        """GLD: rel_return but not priceable → direction=0 (dark fraction)."""
        root = priceable_only_smh
        backfill_policy(root)
        claims = {c["scope"]["key"]: c for c in q.load_claims(root)}
        gld = claims["GLD"]
        assert gld["direction"] == 0
        assert gld.get("ungradeable_soft") is True

    def test_underweight_direction(self, priceable_only_smh, monkeypatch):
        """When underweight subject is priceable → direction=-1."""
        import pandas as pd
        def _series_all(ticker, root):
            idx = pd.bdate_range("2026-01-01", periods=120)
            return pd.Series([100.0 + i for i in range(120)], index=idx)
        monkeypatch.setattr("scripts.backfill_qledger_us._close_series", _series_all)
        root = priceable_only_smh
        backfill_policy(root)
        claims = {c["scope"]["key"]: c for c in q.load_claims(root)}
        gld = claims["GLD"]
        assert gld["direction"] == -1   # underweight + priceable

    def test_all_claims_open_status(self, priceable_only_smh):
        """Even direction=0 claims are open (not rejected) — D4 display-only."""
        root = priceable_only_smh
        backfill_policy(root)
        claims = q.load_claims(root)
        assert all(c["status"] == "open" for c in claims)

    def test_idempotent_on_rerun(self, priceable_only_smh):
        root = priceable_only_smh
        backfill_policy(root)
        backfill_policy(root)
        claims = q.load_claims(root)
        assert len(claims) == 3

    def test_timestamp_quality_is_disclosure(self, priceable_only_smh):
        root = priceable_only_smh
        backfill_policy(root)
        claims = q.load_claims(root)
        assert all(c["timestamp_quality"] == "DISCLOSURE_DATE" for c in claims)


# ---------------------------------------------------------------------------
# cross-desk: mixed backfill + idempotency
# ---------------------------------------------------------------------------

class TestCrossDesk:
    def test_all_three_desks_combined(self, priceable_only_smh):
        """Running all three adapters in sequence produces correct total."""
        root = priceable_only_smh
        n_alt = backfill_altdata(root)
        n_rad = backfill_radar(root)
        n_pol = backfill_policy(root)
        claims = q.load_claims(root)
        assert len(claims) == n_alt + n_rad + n_pol
        desks = {c["desk"] for c in claims}
        assert desks == {"altdata", "radar", "policy"}

    def test_full_rerun_idempotent(self, priceable_only_smh):
        """Running all adapters twice produces no duplicate claims."""
        root = priceable_only_smh
        backfill_altdata(root)
        backfill_radar(root)
        backfill_policy(root)
        first_count = len(q.load_claims(root))

        backfill_altdata(root)
        backfill_radar(root)
        backfill_policy(root)
        assert len(q.load_claims(root)) == first_count

    def test_claim_ids_unique_across_desks(self, priceable_only_smh):
        root = priceable_only_smh
        backfill_altdata(root)
        backfill_radar(root)
        backfill_policy(root)
        claims = q.load_claims(root)
        ids = [c["claim_id"] for c in claims]
        assert len(ids) == len(set(ids))   # no collisions

    def test_dry_run_writes_nothing(self, priceable_only_smh):
        root = priceable_only_smh
        backfill_altdata(root, dry_run=True)
        backfill_radar(root, dry_run=True)
        backfill_policy(root, dry_run=True)
        claims_path = root / "data" / "qledger" / "claims.jsonl"
        assert not claims_path.exists()

    def test_radar_honest_n_dates(self, priceable_only_smh):
        """After radar backfill, the 4 rows span 3 distinct asof dates.
        qledger.compute_track_record should see n_dates=3, not n_obs=4.
        The test verifies the mechanism without grading (no grades exist yet).
        """
        root = priceable_only_smh
        backfill_radar(root)
        claims = q.load_claims(root)
        radar_claims = [c for c in claims if c["desk"] == "radar"]
        dates = {c["asof"] for c in radar_claims}
        # 3 distinct dates (2026-06-20, 2026-06-21, 2026-06-22)
        assert len(dates) == 3

    def test_policy_dark_fraction_registered_not_rejected(self, priceable_only_smh):
        """direction=0 claims (soft/unpriceable) must be status=open, not rejected.
        They represent the honest D4 dark fraction — logged but not graded by direction.
        """
        root = priceable_only_smh
        backfill_policy(root)
        claims = q.load_claims(root)
        dark = [c for c in claims if c["desk"] == "policy" and c.get("ungradeable_soft")]
        assert len(dark) >= 1
        assert all(c["status"] == "open" for c in dark)
        assert all(c["direction"] == 0 for c in dark)
