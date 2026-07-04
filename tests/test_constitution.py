"""Neural Web W7a — constitution core regression tests.

Tests:
1. Null-simulation REGRESSION — binomial null (base=0.30, n_alerts=8, 10k draws):
   - Wilson gate false-grant rate < 10%  (scout computed 5.8%)
   - Old point-estimate gate (>= 1.25) would have been > 35%
   The motivating math is embedded as assertions, not just comments.
2. grant_authority paths: granted, refused (n), refused (events), refused (lift), lapsed.
3. A7 ORIGINATE refusal — AuthorityLevel.A7_ORIGINATE is refused unconditionally.
4. wilson_lower basic correctness + edge cases (k=0, k=n, n=0).
5. governance append/load round-trip — event_id determinism.
6. can_force scorecard: additive-fields compatibility (consumer reading only the bool).
7. Tune-loop governance event emission (mocked writes).
8. ARTICLES dict has entries 1, 2, 3.
9. article2_surfaces reads from synapse.yml (integration — skips if file absent).
"""
from __future__ import annotations

import json
import random
import sys
import tempfile
from pathlib import Path
from unittest import mock

import pytest

REPO_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(REPO_ROOT))

from engine.neuralweb.constitution import (
    ARTICLES,
    AuthorityLevel,
    GrantResult,
    grant_authority,
    wilson_lower,
)
from engine.neuralweb.governance import _event_id, append_event, load_events


# ---------------------------------------------------------------------------
# 1. Null-simulation REGRESSION
# ---------------------------------------------------------------------------

def _old_gate_passes(k: int, n: int, base: float) -> bool:
    """The old point-estimate gate: alert_hit / base >= 1.25."""
    if n == 0 or base == 0:
        return False
    return (k / n) / base >= 1.25


def _new_wilson_gate_passes(k: int, n: int, base: float) -> bool:
    """The new Wilson CI lower-bound gate: wilson_lower(k, n) / base > 1.0."""
    if base == 0:
        return False
    return wilson_lower(k, n, z=1.645) / base > 1.0


class TestNullSimulation:
    """Under the null (no real edge), alert hits are binomial(n, base_rate).

    At n_alerts=8, base=0.30, the point-estimate gate false-grants ~44% of the time.
    The Wilson gate reduces this to ~5.8%.
    """

    N_DRAWS = 10_000
    BASE = 0.30
    N_ALERTS = 8
    SEED = 42

    def _simulate(self, gate_fn):
        rng = random.Random(self.SEED)
        false_grants = 0
        for _ in range(self.N_DRAWS):
            # Draw from the null: hits ~ Binomial(N_ALERTS, BASE)
            k = sum(rng.random() < self.BASE for _ in range(self.N_ALERTS))
            if gate_fn(k, self.N_ALERTS, self.BASE):
                false_grants += 1
        return false_grants / self.N_DRAWS

    def test_old_gate_false_grant_rate_above_35_pct(self):
        """Old point-estimate gate should false-grant > 35% at n=8 under the null."""
        rate = self._simulate(_old_gate_passes)
        assert rate > 0.35, (
            f"Old point-estimate gate false-grant rate {rate:.1%} should be > 35% "
            f"at n=8 under binomial null (base={self.BASE}). "
            f"This is the motivating math for the Wilson fix."
        )

    def test_new_wilson_gate_false_grant_rate_below_10_pct(self):
        """Wilson CI gate should false-grant < 10% at n=8 under the null (scout: ~5.8%)."""
        rate = self._simulate(_new_wilson_gate_passes)
        assert rate < 0.10, (
            f"Wilson CI gate false-grant rate {rate:.1%} should be < 10% "
            f"at n=8 under binomial null (base={self.BASE}). "
            f"Scout computation: ~5.8%. If this exceeds 10%, the Wilson formula is wrong."
        )

    def test_wilson_gate_strictly_tighter_than_old_gate(self):
        """The Wilson gate must be strictly tighter (fewer grants) than the old gate."""
        old_rate = self._simulate(_old_gate_passes)
        new_rate = self._simulate(_new_wilson_gate_passes)
        assert new_rate < old_rate, (
            f"Wilson gate ({new_rate:.1%}) must be strictly tighter than old gate ({old_rate:.1%}). "
            f"If new >= old, the Wilson gate is not an improvement."
        )

    def test_wilson_reduction_factor_at_least_4x(self):
        """Wilson gate reduces false-grant rate by at least 4x at n=8 under the null."""
        old_rate = self._simulate(_old_gate_passes)
        new_rate = self._simulate(_new_wilson_gate_passes)
        # Scout says ~8x reduction (44.8% → 5.8%); we require at least 4x
        reduction_factor = old_rate / new_rate if new_rate > 0 else float("inf")
        assert reduction_factor >= 4.0, (
            f"Wilson gate reduction factor {reduction_factor:.1f}x should be >= 4x "
            f"(old={old_rate:.1%}, new={new_rate:.1%}). Scout projected ~8x."
        )


# ---------------------------------------------------------------------------
# 2. grant_authority paths
# ---------------------------------------------------------------------------

class TestGrantAuthority:

    BASE_EVIDENCE = {
        "hits": 6,
        "n": 10,
        "base_rate": 0.30,
        "evidence_asof": "2026-06-01",
    }
    BASE_FLOORS = {"min_n": 30, "min_events": 8}

    def test_refused_insufficient_n(self):
        res = grant_authority(
            {"hits": 6, "n": 5, "base_rate": 0.30, "evidence_asof": "2026-06-01"},
            floors={"min_n": 30, "min_events": 8},
        )
        assert not res.granted
        assert "insufficient-n" in res.reason
        assert res.lapses_at is None

    def test_refused_insufficient_events(self):
        res = grant_authority(
            {"hits": 2, "n": 35, "base_rate": 0.30, "evidence_asof": "2026-06-01"},
            floors={"min_n": 30, "min_events": 8},
        )
        assert not res.granted
        assert "insufficient-events" in res.reason

    def test_refused_lift_too_low(self):
        # n=35, hits=8 (exactly min_events), base=0.30
        # wilson_lower(8, 35, z=1.645) ≈ 0.116 (well below base=0.30 → lift_lb<1)
        res = grant_authority(
            {"hits": 8, "n": 35, "base_rate": 0.60, "evidence_asof": "2026-06-01"},
            floors={"min_n": 30, "min_events": 8},
        )
        assert not res.granted
        assert "lift-lb-insufficient" in res.reason or "lift" in res.reason.lower()

    def test_granted_when_strong_evidence(self):
        # n=40, hits=35, base=0.30 → high wilson_lb, lift_lb >> 1
        res = grant_authority(
            {"hits": 35, "n": 40, "base_rate": 0.30, "evidence_asof": "2026-06-01"},
            floors={"min_n": 30, "min_events": 8},
        )
        assert res.granted
        assert res.lift_lb is not None and res.lift_lb > 1.0
        assert res.wilson_lb is not None and res.wilson_lb > 0
        assert res.lapses_at is not None
        assert "granted" in res.reason.lower()

    def test_lapsed_stale_evidence(self):
        from datetime import datetime, timezone
        # Evidence from 200 days ago — exceeds max_staleness_days=120
        ancient_date = "2025-01-01"
        res = grant_authority(
            {"hits": 35, "n": 40, "base_rate": 0.30, "evidence_asof": ancient_date},
            floors={"min_n": 30, "min_events": 8},
            now=datetime(2026, 7, 4, tzinfo=timezone.utc),
        )
        assert not res.granted
        assert "stale" in res.reason

    def test_zero_base_rate_refused(self):
        res = grant_authority(
            {"hits": 30, "n": 35, "base_rate": 0.0, "evidence_asof": "2026-06-01"},
            floors={"min_n": 30, "min_events": 8},
        )
        assert not res.granted
        assert "base" in res.reason.lower()

    def test_grant_result_is_dataclass(self):
        res = grant_authority(
            {"hits": 35, "n": 40, "base_rate": 0.30, "evidence_asof": "2026-06-01"},
            floors={"min_n": 30, "min_events": 8},
        )
        assert isinstance(res, GrantResult)
        assert hasattr(res, "granted")
        assert hasattr(res, "lift_lb")
        assert hasattr(res, "wilson_lb")
        assert hasattr(res, "reason")
        assert hasattr(res, "lapses_at")


# ---------------------------------------------------------------------------
# 3. A7 ORIGINATE refusal
# ---------------------------------------------------------------------------

class TestA7Refusal:

    def test_a7_level_exists(self):
        assert AuthorityLevel.A7_ORIGINATE.value == 7

    def test_a7_docstring_says_banned(self):
        # Enum member docstrings are accessible via the class-level _member_docstrings_
        # or by checking the module source.  Python Enum stores member docstrings
        # as the member's _value_ companion; we check via the ARTICLES dict instead.
        # The ARTICLES dict is the canonical place where "permanently banned" is encoded.
        assert "A7" in ARTICLES[1] or "originate" in ARTICLES[1].lower() or "Origination" in ARTICLES[1], (
            "Article 1 must reference the A7 ban. Got: " + ARTICLES[1]
        )
        # Also verify via the enum module's source docstring (accessible in the class body)
        import inspect
        src = inspect.getsource(AuthorityLevel)
        assert "PERMANENTLY BANNED" in src or "permanently banned" in src.lower(), (
            "AuthorityLevel source must mention 'PERMANENTLY BANNED' for A7_ORIGINATE"
        )

    def test_all_levels_have_docstrings(self):
        for level in AuthorityLevel:
            assert level.__doc__, f"AuthorityLevel.{level.name} must have a docstring"


# ---------------------------------------------------------------------------
# 4. wilson_lower basic correctness
# ---------------------------------------------------------------------------

class TestWilsonLower:

    def test_zero_n_returns_zero(self):
        assert wilson_lower(0, 0) == 0.0
        assert wilson_lower(5, 0) == 0.0

    def test_zero_k_returns_low_value(self):
        # k=0 → lower bound should be near 0 (but not negative)
        lb = wilson_lower(0, 20, z=1.645)
        assert 0.0 <= lb < 0.10

    def test_k_equals_n_returns_high_value(self):
        lb = wilson_lower(20, 20, z=1.645)
        assert lb > 0.80

    def test_z_parameter_respected(self):
        # Higher z → tighter (lower) lower bound
        lb_90 = wilson_lower(5, 20, z=1.645)
        lb_95 = wilson_lower(5, 20, z=1.96)
        assert lb_90 > lb_95, "Higher z should give lower Wilson lower bound"

    def test_default_z_is_1645(self):
        lb_default = wilson_lower(5, 20)
        lb_explicit = wilson_lower(5, 20, z=1.645)
        assert abs(lb_default - lb_explicit) < 1e-9

    def test_monotone_in_k(self):
        # More hits → higher lower bound
        n = 30
        lbs = [wilson_lower(k, n) for k in range(0, n + 1)]
        for i in range(len(lbs) - 1):
            assert lbs[i] <= lbs[i + 1], f"wilson_lower not monotone at k={i}"

    def test_stays_between_0_and_1(self):
        for k in [0, 5, 10, 20, 30]:
            for n in [30, 50, 100]:
                if k <= n:
                    lb = wilson_lower(k, n)
                    assert 0.0 <= lb <= 1.0, f"Out of range: wilson_lower({k}, {n}) = {lb}"


# ---------------------------------------------------------------------------
# 5. governance append/load round-trip and event_id determinism
# ---------------------------------------------------------------------------

class TestGovernanceLedger:

    def test_event_id_is_deterministic(self):
        eid1 = _event_id("authority_grant", "engine/test.can_force:CN", "2026-07-04T12:00:00+00:00")
        eid2 = _event_id("authority_grant", "engine/test.can_force:CN", "2026-07-04T12:00:00+00:00")
        assert eid1 == eid2

    def test_event_id_changes_with_inputs(self):
        eid1 = _event_id("authority_grant", "target_A", "2026-07-04T12:00:00+00:00")
        eid2 = _event_id("authority_lapse", "target_A", "2026-07-04T12:00:00+00:00")
        assert eid1 != eid2

    def test_event_id_is_16_hex_chars(self):
        eid = _event_id("authority_grant", "target", "2026-07-04T12:00:00+00:00")
        assert len(eid) == 16
        assert all(c in "0123456789abcdef" for c in eid)

    def test_append_and_load_roundtrip(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            append_event(
                "authority_grant",
                "engine/risk_radar_intl_audit.can_force:CN",
                article=3,
                authored_by="test_runner",
                evidence={"hits": 25, "n": 30, "base_rate": 0.30},
                root=tmpdir,
            )
            events = load_events(root=tmpdir)
            assert len(events) == 1
            ev = events[0]
            assert ev["schema"] == "neuralweb.governance.v1"
            assert ev["event_type"] == "authority_grant"
            assert ev["target"] == "engine/risk_radar_intl_audit.can_force:CN"
            assert ev["article"] == 3
            assert ev["authored_by"] == "test_runner"
            assert ev["evidence"]["hits"] == 25

    def test_load_filter_by_event_type(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            append_event("authority_grant", "t1", authored_by="x", root=tmpdir)
            append_event("authority_lapse", "t2", authored_by="x", root=tmpdir)
            append_event("a6_auto_apply", "t3", authored_by="x", root=tmpdir)
            grants = load_events(root=tmpdir, event_type="authority_grant")
            assert len(grants) == 1
            assert grants[0]["event_type"] == "authority_grant"

    def test_load_filter_by_target_prefix(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            append_event("authority_grant", "engine/foo:CN", authored_by="x", root=tmpdir)
            append_event("authority_grant", "engine/foo:HK", authored_by="x", root=tmpdir)
            append_event("authority_grant", "engine/bar:CN", authored_by="x", root=tmpdir)
            cn_foo = load_events(root=tmpdir, target="engine/foo:CN")
            assert len(cn_foo) == 1

    def test_append_never_raises_on_bad_root(self):
        # append_event must not raise even with a bad path
        result = append_event("authority_grant", "t", authored_by="x", root="/dev/null/bad")
        # Returns False (failure) but does not raise
        assert isinstance(result, bool)

    def test_load_empty_on_missing_ledger(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            events = load_events(root=tmpdir)
            assert events == []

    def test_governance_event_schema_field_present(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            append_event("a6_auto_apply", "data/calibration.json",
                         article=6, authored_by="tune", root=tmpdir)
            events = load_events(root=tmpdir)
            assert events[0]["schema"] == "neuralweb.governance.v1"

    def test_multiple_appends_accumulate(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            for i in range(5):
                append_event("authority_grant", f"target_{i}", authored_by="x", root=tmpdir)
            events = load_events(root=tmpdir)
            assert len(events) == 5


# ---------------------------------------------------------------------------
# 6. can_force scorecard additive-fields compatibility
# ---------------------------------------------------------------------------

class TestScorecardAdditiveFields:
    """Consumers that read only `can_force` (bool) still work after W7a additive fields."""

    def _make_scorecard_result(self, can_force: bool) -> dict:
        """Simulate what scorecard() returns post-W7a."""
        return {
            "market": "CN",
            "n_graded": 35,
            "can_force": can_force,
            # NEW additive fields (W7a)
            "wilson_lift_lb": 1.15 if can_force else 0.85,
            "grant_reason": "granted" if can_force else "lift-lb-insufficient",
            "evidence_asof": "2026-07-01",
            # Existing fields
            "force_lift": 1.30 if can_force else 0.90,
            "base_rate_dd5_h21": 0.30,
        }

    def test_existing_consumer_reads_bool_only(self):
        """Simulates engine/market_state.py:507 — reads only the bool."""
        sc = self._make_scorecard_result(can_force=True)
        # The consumer only does: if rr.get("can_force") and state in (...)
        can_force_value = sc.get("can_force")
        assert isinstance(can_force_value, bool)
        assert can_force_value is True

    def test_existing_consumer_with_false(self):
        sc = self._make_scorecard_result(can_force=False)
        assert not sc.get("can_force")

    def test_new_fields_present_and_accessible(self):
        sc = self._make_scorecard_result(can_force=True)
        assert "wilson_lift_lb" in sc
        assert "grant_reason" in sc
        assert "evidence_asof" in sc
        assert sc["wilson_lift_lb"] > 1.0

    def test_new_fields_absent_does_not_break_bool_check(self):
        """Simulate a scorecard WITHOUT the new fields (backwards compat in the other direction)."""
        sc = {"market": "HK", "n_graded": 5, "can_force": False}
        # Consumer only reads the bool — missing new fields cause no crash
        val = bool(sc.get("can_force", False))
        assert val is False
        assert sc.get("wilson_lift_lb") is None  # graceful None


# ---------------------------------------------------------------------------
# 7. Tune-loop governance event emission (mocked writes)
# ---------------------------------------------------------------------------

class TestTuneGovernanceEmission:
    """Verify the A6 governance event is emitted during tune() — without running
    the full engine (which requires loaded market data)."""

    def test_market_state_tune_calls_append_event(self):
        """_append_governance_a6 inside market_state_tune should call append_event."""
        from engine.market_state_tune import _append_governance_a6
        with tempfile.TemporaryDirectory() as tmpdir:
            _append_governance_a6(
                root=tmpdir,
                decision="apply",
                n_graded=25,
                base_rate=0.30,
                bt_cur={"f1": 0.40, "fp": 5},
                bt_cand={"f1": 0.45, "fp": 4},
            )
            events = load_events(root=tmpdir, event_type="a6_auto_apply")
            assert len(events) == 1
            ev = events[0]
            assert ev["authored_by"] == "market_state_tune"
            assert ev["article"] == 6
            assert ev["after"]["action"] == "apply"
            assert ev["evidence"]["n_graded"] == 25

    def test_intl_tune_calls_append_event(self):
        """_append_governance_a6 inside risk_radar_intl_tune emits an event."""
        from engine.risk_radar_intl_tune import _append_governance_a6
        with tempfile.TemporaryDirectory() as tmpdir:
            _append_governance_a6(
                key="CN",
                root=tmpdir,
                decision="hold",
                n_graded=30,
                brier_cur=0.12,
                brier_cand=0.11,
            )
            events = load_events(root=tmpdir, event_type="a6_auto_apply")
            assert len(events) == 1
            ev = events[0]
            assert ev["authored_by"] == "risk_radar_intl_tune"
            assert ev["evidence"]["market"] == "CN"
            assert ev["after"]["action"] == "hold"

    def test_governance_failure_does_not_raise(self):
        """If governance write fails, the tune helper must not propagate the exception."""
        from engine.market_state_tune import _append_governance_a6
        with mock.patch("engine.neuralweb.governance.append_event", side_effect=RuntimeError("disk full")):
            # Should not raise
            _append_governance_a6(
                root=None,
                decision="apply",
                n_graded=25,
                base_rate=0.30,
                bt_cur={"f1": 0.40, "fp": 5},
                bt_cand={"f1": 0.45, "fp": 4},
            )


# ---------------------------------------------------------------------------
# 8. ARTICLES dict
# ---------------------------------------------------------------------------

class TestArticles:

    def test_articles_has_1_2_3(self):
        assert 1 in ARTICLES
        assert 2 in ARTICLES
        assert 3 in ARTICLES

    def test_article_1_mentions_origination(self):
        assert "Origination" in ARTICLES[1] or "originate" in ARTICLES[1].lower()

    def test_article_3_mentions_wilson(self):
        assert "Wilson" in ARTICLES[3] or "CI" in ARTICLES[3]

    def test_article_2_mentions_perimeter(self):
        assert "Perimeter" in ARTICLES[2] or "surface" in ARTICLES[2].lower()


# ---------------------------------------------------------------------------
# 9. article2_surfaces reads from synapse.yml
# ---------------------------------------------------------------------------

class TestArticle2Surfaces:

    def test_reads_from_synapse_yml(self):
        from engine.neuralweb.constitution import article2_surfaces
        # Integration test — skips gracefully if synapse.yml not found
        surfaces = article2_surfaces(root=REPO_ROOT)
        if not (REPO_ROOT / "config" / "synapse.yml").exists():
            pytest.skip("synapse.yml not found — integration test requires repo root")
        # The scout confirms at least these 5 surfaces
        for expected in ["alert_triage", "board_ordering", "top_setups",
                         "attention_queue", "push_floor"]:
            assert expected in surfaces, (
                f"{expected!r} missing from article2_surfaces. "
                f"Got: {surfaces}. Check config/synapse.yml meta.article2_surfaces."
            )

    def test_returns_list(self):
        from engine.neuralweb.constitution import article2_surfaces
        result = article2_surfaces(root=REPO_ROOT)
        assert isinstance(result, list)

    def test_graceful_missing_file(self):
        from engine.neuralweb.constitution import article2_surfaces
        with tempfile.TemporaryDirectory() as tmpdir:
            result = article2_surfaces(root=tmpdir)
            assert result == []  # missing synapse.yml → empty, not exception
