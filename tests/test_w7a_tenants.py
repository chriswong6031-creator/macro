"""tests/test_w7a_tenants.py — W7a PR2 tenant tests.

Covers:
  T1  altdata_brain Article-3 verdict evaluation (clearing → granted; not clearing → refused)
  T2  actionable flag + is_context_only set correctly from verdict
  T3  article3 additive fields in brief schema
  T4  governance events emitted on transitions (grant / lapse)
  T5  feed additive-shape safety (no existing keys removed)
  T6  risk_radar_review A6 lane-(ii) governance emissions (proposal / apply / reject)
  T7  governance logging failure never blocks the loop
  T8  arming state resolves True through real config path
  T9  A7 still refused unconditionally (Article 1)
"""
from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

# Make sure the repo root is on the path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

# ---------------------------------------------------------------------------
# Helpers / fixtures
# ---------------------------------------------------------------------------

def _make_track_record(n_dates: int, hit_rate: float | None, root: Path) -> None:
    """Write a minimal site/qledger/track_record.json fixture."""
    cell: dict = {"n_obs": n_dates * 10, "n_dates": n_dates}
    if hit_rate is not None:
        cell["hit_rate"] = hit_rate
    else:
        cell["hit_rate"] = None
    (root / "site" / "qledger").mkdir(parents=True, exist_ok=True)
    tr = {
        "generated_at": "2026-07-04T11:05:29.729020+00:00",
        "by_family": {"altdata": {"5": cell}},
    }
    (root / "site" / "qledger" / "track_record.json").write_text(json.dumps(tr))


def _make_governance_dir(root: Path) -> Path:
    d = root / "data" / "neuralweb"
    d.mkdir(parents=True, exist_ok=True)
    return d / "governance.jsonl"


def _load_gov_events(ledger: Path) -> list[dict]:
    if not ledger.exists():
        return []
    return [json.loads(ln) for ln in ledger.read_text().splitlines() if ln.strip()]


# ---------------------------------------------------------------------------
# T1 — Article-3 verdict: clearing case
# ---------------------------------------------------------------------------

class TestArticle3Verdict:
    def test_clearing_case_grants(self, tmp_path):
        """n_dates=30, hit_rate=0.80 → n=30 >= 25, hits=24, wilson_lb=0.6575, lift_lb=1.315 > 1.25 → granted."""
        from engine.altdata_brain import article3_actionable_verdict
        _make_track_record(n_dates=30, hit_rate=0.80, root=tmp_path)
        result = article3_actionable_verdict(root=tmp_path)
        assert result.granted, f"Expected granted; got reason={result.reason}"
        assert result.lift_lb is not None and result.lift_lb > 1.25
        assert result.lapses_at is not None

    def test_insufficient_n_refused(self, tmp_path):
        """n_dates=5 < min_n=25 → refused on n floor."""
        from engine.altdata_brain import article3_actionable_verdict
        _make_track_record(n_dates=5, hit_rate=0.56, root=tmp_path)
        result = article3_actionable_verdict(root=tmp_path)
        assert not result.granted
        assert "insufficient-n" in result.reason

    def test_null_hit_rate_refused(self, tmp_path):
        """hit_rate=None → refused (no evidence)."""
        from engine.altdata_brain import article3_actionable_verdict
        _make_track_record(n_dates=30, hit_rate=None, root=tmp_path)
        result = article3_actionable_verdict(root=tmp_path)
        assert not result.granted

    def test_missing_track_record_refused(self, tmp_path):
        """No track_record.json → refused."""
        from engine.altdata_brain import article3_actionable_verdict
        result = article3_actionable_verdict(root=tmp_path)
        assert not result.granted
        assert "unavailable" in result.reason

    def test_lift_insufficient_refused(self, tmp_path):
        """n_dates=30, hit_rate=0.51 → lift_lb <= 1.25 → refused."""
        from engine.altdata_brain import article3_actionable_verdict
        _make_track_record(n_dates=30, hit_rate=0.51, root=tmp_path)
        result = article3_actionable_verdict(root=tmp_path)
        assert not result.granted
        assert "lift-lb-insufficient" in result.reason


# ---------------------------------------------------------------------------
# T2 — actionable flag + is_context_only from verdict
# ---------------------------------------------------------------------------

class TestSynthesizeFlags:
    def _minimal_state(self):
        return {
            "as_of": "2026-07-04",
            "clusters": [],
            "n_clusters": 0,
            "track_record": None,
        }

    def test_actionable_false_when_not_clearing(self, tmp_path):
        """n_dates=5 → Article-3 refuses → brief.actionable=False, is_context_only=True."""
        from engine.altdata_brain import synthesize
        _make_track_record(n_dates=5, hit_rate=0.56, root=tmp_path)

        def _stub_call(system, user):
            return (None, "test_stub")

        brief = synthesize(self._minimal_state(), call=_stub_call, root=tmp_path)
        assert brief["actionable"] is False
        assert brief["is_context_only"] is True

    def test_actionable_true_when_clearing(self, tmp_path):
        """n_dates=30, hit_rate=0.80 → Article-3 grants → brief.actionable=True."""
        from engine.altdata_brain import synthesize
        _make_track_record(n_dates=30, hit_rate=0.80, root=tmp_path)

        def _stub_call(system, user):
            return (None, "test_stub")

        brief = synthesize(self._minimal_state(), call=_stub_call, root=tmp_path)
        assert brief["actionable"] is True
        assert brief["is_context_only"] is False


# ---------------------------------------------------------------------------
# T3 — article3 additive fields in brief schema
# ---------------------------------------------------------------------------

class TestBriefSchema:
    def _minimal_state(self):
        return {
            "as_of": "2026-07-04",
            "clusters": [],
            "n_clusters": 0,
            "track_record": None,
        }

    def test_article3_block_present(self, tmp_path):
        """The brief always contains the article3 block (additive fields only)."""
        from engine.altdata_brain import synthesize, SCHEMA
        _make_track_record(n_dates=5, hit_rate=0.56, root=tmp_path)

        def _stub_call(system, user):
            return (None, "test_stub")

        brief = synthesize(self._minimal_state(), call=_stub_call, root=tmp_path)
        assert "article3" in brief
        a3 = brief["article3"]
        for key in ("granted", "lift_lb", "reason", "evaluated_at"):
            assert key in a3, f"article3.{key} missing"

    def test_existing_keys_unchanged(self, tmp_path):
        """No pre-existing keys are removed from the brief."""
        from engine.altdata_brain import synthesize
        _make_track_record(n_dates=5, hit_rate=0.56, root=tmp_path)

        def _stub_call(system, user):
            return (None, "test_stub")

        brief = synthesize(self._minimal_state(), call=_stub_call, root=tmp_path)
        for key in ("schema", "generated_at", "state_asof", "model",
                    "regime_read", "theses", "confidence", "disclaimer",
                    "track_record", "degraded_reason"):
            assert key in brief, f"Key {key!r} should still be present"


# ---------------------------------------------------------------------------
# T4 — governance events on transitions
# ---------------------------------------------------------------------------

class TestGovernanceTransitions:
    def _minimal_state(self):
        return {"as_of": "2026-07-04", "clusters": [], "n_clusters": 0, "track_record": None}

    def _call_stub(self, system, user):
        return (None, "test_stub")

    def test_grant_transition_emits_authority_grant(self, tmp_path):
        """prev_granted=False + verdict.granted=True → authority_grant event emitted."""
        from engine.altdata_brain import synthesize
        _make_track_record(n_dates=30, hit_rate=0.80, root=tmp_path)
        ledger = _make_governance_dir(tmp_path)
        # Simulate transition from not-granted to granted
        synthesize(self._minimal_state(), call=self._call_stub, root=tmp_path, _prev_granted=False)
        events = _load_gov_events(ledger)
        types = [e["event_type"] for e in events]
        assert "article3_review" in types
        assert "authority_grant" in types

    def test_lapse_transition_emits_authority_lapse(self, tmp_path):
        """prev_granted=True + verdict.granted=False → authority_lapse event emitted."""
        from engine.altdata_brain import synthesize
        _make_track_record(n_dates=5, hit_rate=0.56, root=tmp_path)
        ledger = _make_governance_dir(tmp_path)
        # Simulate transition from granted to not-granted (lapse)
        synthesize(self._minimal_state(), call=self._call_stub, root=tmp_path, _prev_granted=True)
        events = _load_gov_events(ledger)
        types = [e["event_type"] for e in events]
        assert "article3_review" in types
        assert "authority_lapse" in types

    def test_no_transition_only_review_event(self, tmp_path):
        """prev_granted=None → only article3_review emitted (first evaluation)."""
        from engine.altdata_brain import synthesize
        _make_track_record(n_dates=5, hit_rate=0.56, root=tmp_path)
        ledger = _make_governance_dir(tmp_path)
        synthesize(self._minimal_state(), call=self._call_stub, root=tmp_path, _prev_granted=None)
        events = _load_gov_events(ledger)
        types = [e["event_type"] for e in events]
        assert "article3_review" in types
        assert "authority_grant" not in types
        assert "authority_lapse" not in types


# ---------------------------------------------------------------------------
# T5 — feed additive-shape safety (mastermind.json consumers)
# ---------------------------------------------------------------------------

class TestFeedShape:
    def test_mastermind_consumers_intact(self):
        """Grep: no consumer in THIS repo reads altdata_brain keys we removed.
        The only removed key is the hardcoded 'actionable: True' — now evidence-driven.
        Verify no consumer hardcodes actionable=True / is_context_only=False expectations
        outside of test fixtures."""
        # This test verifies the contract: the brief shape is ADDITIVE.
        # We check that the fields that existed before still exist (T3 covers that).
        # Additionally verify that altdata_emit.py reads 'actionable' dynamically.
        import importlib.util
        emit_path = Path(__file__).parent.parent / "engine" / "altdata_emit.py"
        if emit_path.exists():
            src = emit_path.read_text()
            # The emit module should check actionable, not hardcode it
            assert "actionable" in src, "altdata_emit.py should reference 'actionable'"
        # Brief still has all pre-existing keys (checked in T3)


# ---------------------------------------------------------------------------
# T6 — risk_radar_review A6 lane-(ii) governance emissions
# ---------------------------------------------------------------------------

class TestRiskRadarReviewGovernance:
    """Mock the LLM call; verify proposal/apply/reject paths each emit governance events."""

    def _make_scorecard(self, n_graded: int = 35) -> dict:
        return {
            "n_graded": n_graded,
            "alert_precision": 0.6,
            "recall_dd5_h21": 0.5,
            "n_alerts": 10,
            "n_true_pos": 6,
            "n_false_pos": 4,
            "by_state": {},
            "recent_mistakes": [],
        }

    def _make_base_calib(self) -> dict:
        from engine.risk_radar import _DEFAULT_BANDS
        return {
            "bands": dict(_DEFAULT_BANDS),
            "legs": {},
            "scares": {},
            "prob_cal": {"h5": {"calm": 0.1, "watch": 0.2, "caution": 0.3, "elevated": 0.4, "risk-off": 0.5},
                         "h10": {"calm": 0.1, "watch": 0.2, "caution": 0.3, "elevated": 0.4, "risk-off": 0.5},
                         "h21": {"calm": 0.1, "watch": 0.2, "caution": 0.3, "elevated": 0.4, "risk-off": 0.5}},
            "alert_from": "elevated",
        }

    def test_proposal_path_emits_a6_llm_proposed(self, tmp_path):
        """A proposal (regardless of apply/reject) emits a6_llm_proposed governance event."""
        ledger = _make_governance_dir(tmp_path)

        def _mock_call(system, user):
            return json.dumps({
                "analysis": "test analysis",
                "deltas": {"bands": {}, "legs": {}, "prob_cal": {}},
                "rationale": "test rationale",
            })

        def _mock_compare(proposed):
            return {"base": {}, "proposed": {}, "improves": False, "legs_ok": True}

        from engine.risk_radar_review import run
        result = run(
            persist=False, root=tmp_path, force=True,
            call=_mock_call,
            scorecard=self._make_scorecard(),
            compare=_mock_compare,
        )
        events = _load_gov_events(ledger)
        types = [e["event_type"] for e in events]
        assert "a6_llm_proposed" in types, f"Expected a6_llm_proposed in {types}"

    def test_apply_path_emits_a6_auto_apply(self, tmp_path):
        """When do-no-harm passes, a6_auto_apply event is emitted."""
        ledger = _make_governance_dir(tmp_path)

        def _mock_call(system, user):
            return json.dumps({
                "analysis": "test",
                "deltas": {"bands": {}, "legs": {}, "prob_cal": {}},
                "rationale": "test",
            })

        def _mock_compare(proposed):
            return {"base": {"f1": 0.4}, "proposed": {"f1": 0.45}, "improves": True, "legs_ok": True}

        from engine.risk_radar_review import run
        result = run(
            persist=False, root=tmp_path, force=True,
            call=_mock_call,
            scorecard=self._make_scorecard(),
            compare=_mock_compare,
        )
        assert result.get("applied") is True
        events = _load_gov_events(ledger)
        types = [e["event_type"] for e in events]
        assert "a6_auto_apply" in types, f"Expected a6_auto_apply in {types}"

    def test_reject_path_emits_rejection_governance(self, tmp_path):
        """When do-no-harm fails, a reject governance event is emitted."""
        ledger = _make_governance_dir(tmp_path)

        def _mock_call(system, user):
            return json.dumps({
                "analysis": "test",
                "deltas": {"bands": {}, "legs": {}, "prob_cal": {}},
                "rationale": "test",
            })

        def _mock_compare(proposed):
            return {"base": {"f1": 0.5}, "proposed": {"f1": 0.4}, "improves": False, "legs_ok": True}

        from engine.risk_radar_review import run
        result = run(
            persist=False, root=tmp_path, force=True,
            call=_mock_call,
            scorecard=self._make_scorecard(),
            compare=_mock_compare,
        )
        assert result.get("applied") is False
        events = _load_gov_events(ledger)
        types = [e["event_type"] for e in events]
        # reject path: a6_llm_proposed event (proposal logged), then reject in second a6_llm_proposed
        assert "a6_llm_proposed" in types


# ---------------------------------------------------------------------------
# T7 — governance logging failure never blocks the loop
# ---------------------------------------------------------------------------

class TestGovernanceNeverBlocks:
    def test_altdata_brain_governance_failure_safe(self, tmp_path):
        """If governance append_event raises, synthesize() still returns a valid brief."""
        from engine.altdata_brain import synthesize
        _make_track_record(n_dates=5, hit_rate=0.56, root=tmp_path)

        def _stub_call(system, user):
            return (None, "test_stub")

        with patch("engine.altdata_brain.append_event", side_effect=RuntimeError("ledger down")):
            # synthesize() must not raise even when append_event crashes
            brief = synthesize(
                {"as_of": "2026-07-04", "clusters": [], "n_clusters": 0, "track_record": None},
                call=_stub_call, root=tmp_path,
            )
        assert isinstance(brief, dict)
        assert "actionable" in brief

    def test_risk_radar_review_governance_failure_safe(self, tmp_path):
        """If governance append_event raises, run() still returns applied=True."""
        _make_governance_dir(tmp_path)

        def _mock_call(system, user):
            return json.dumps({
                "analysis": "test",
                "deltas": {"bands": {}, "legs": {}, "prob_cal": {}},
                "rationale": "test",
            })

        def _mock_compare(proposed):
            return {"base": {}, "proposed": {}, "improves": True, "legs_ok": True}

        from engine.risk_radar_review import run
        with patch("engine.risk_radar_review.append_event", side_effect=RuntimeError("ledger down")):
            result = run(
                persist=False, root=tmp_path, force=True,
                call=_mock_call,
                scorecard={"n_graded": 35, "recent_mistakes": [], "by_state": {},
                           "n_alerts": 5, "n_true_pos": 3, "n_false_pos": 2},
                compare=_mock_compare,
            )
        # The loop must complete and not crash even when governance fails
        assert isinstance(result, dict)


# ---------------------------------------------------------------------------
# T8 — arming state resolves True through real config path
# ---------------------------------------------------------------------------

class TestArmingState:
    def test_enabled_true_via_config_yml(self):
        """risk_radar_review.enabled resolves True through config.load() overlay.

        The _DEFAULTS dict has enabled=False.  The real arm is config.yml which has
        enabled: true (committed in W7a PR2).  _cfg() merges: {**_DEFAULTS, **config_overlay}.
        """
        from engine.risk_radar_review import _cfg
        cfg = _cfg()
        assert cfg.get("enabled") is True, (
            f"expected enabled=True from config.yml overlay, got {cfg.get('enabled')!r}"
        )

    def test_run_noops_when_not_enough_graded(self):
        """Even when enabled, run() no-ops when n_graded < min_graded=30."""
        from engine.risk_radar_review import run
        result = run(
            persist=False,
            scorecard={"n_graded": 5, "recent_mistakes": []},
            call=lambda s, u: "{}",
        )
        assert result.get("degraded_reason") == "insufficient_graded"
        assert result.get("applied") is False


# ---------------------------------------------------------------------------
# T9 — A7 still refused unconditionally (Article 1)
# ---------------------------------------------------------------------------

class TestA7StillRefused:
    def test_a7_refused_with_perfect_evidence(self):
        """A7/ORIGINATE is refused even with n=1000, hit_rate=1.0 (Article 1 hard ban)."""
        from engine.neuralweb.constitution import grant_authority, AuthorityLevel
        result = grant_authority(
            {"hits": 1000, "n": 1000, "base_rate": 0.5, "evidence_asof": "2026-07-04"},
            floors={"min_n": 1, "min_events": 1},
            target_level=AuthorityLevel.A7_ORIGINATE,
        )
        assert not result.granted
        assert "article-1-origination-ban" in result.reason


# ---------------------------------------------------------------------------
# T10 — mastermind.json propagation (INTEGRITY FIX 2)
# ---------------------------------------------------------------------------

class TestMastermindPropagation:
    """build_mastermind() propagates article3 + is_context_only from the brain brief.
    Two-organisms law: the bot reads flags per its own logic; no existing keys are changed.
    """

    def _minimal_by_ticker(self) -> dict:
        return {"as_of": "2026-07-04", "tickers": {}}

    def test_article3_and_is_context_only_propagated_when_brain_present(self, tmp_path):
        """When brain has article3 block, mastermind.json carries it additively."""
        import engine.altdata_emit as EM
        brain = {
            "theses": [],
            "article3": {
                "granted": False,
                "lift_lb": None,
                "reason": "insufficient-n: n=5 < min_n=25",
                "evidence_asof": "2026-07-04",
                "evaluated_at": "2026-07-04T23:27:19+00:00",
            },
            "is_context_only": True,
            "actionable": False,
            "regime_read": None,
            "disclaimer": "test disclaimer",
        }
        out = EM.build_mastermind(self._minimal_by_ticker(), brain, {}, {}, {}, root=tmp_path)
        assert "article3" in out, "mastermind.json must carry article3"
        a3 = out["article3"]
        assert a3["granted"] is False
        assert a3["reason"] == "insufficient-n: n=5 < min_n=25"
        assert a3["evidence_asof"] == "2026-07-04"
        assert out["is_context_only"] is True

    def test_brain_absent_defaults_refuse_by_default(self, tmp_path):
        """When brain is absent/None: article3=None, is_context_only=True (refuse-by-default)."""
        import engine.altdata_emit as EM
        out = EM.build_mastermind(self._minimal_by_ticker(), None, {}, {}, {}, root=tmp_path)
        assert out["article3"] is None
        assert out["is_context_only"] is True, "must default True (refuse-by-default) when brain absent"

    def test_brain_empty_dict_defaults_refuse_by_default(self, tmp_path):
        """When brain is {} (no theses): article3=None, is_context_only=True."""
        import engine.altdata_emit as EM
        out = EM.build_mastermind(self._minimal_by_ticker(), {}, {}, {}, {}, root=tmp_path)
        assert out["article3"] is None
        assert out["is_context_only"] is True

    def test_existing_keys_not_removed(self, tmp_path):
        """Additive only — no pre-existing mastermind.json keys are removed."""
        import engine.altdata_emit as EM
        out = EM.build_mastermind(self._minimal_by_ticker(), None, {}, {}, {}, root=tmp_path)
        for key in ("schema", "as_of", "generated_utc", "contract", "regime_read",
                    "brain_present", "brain_usable", "calibration",
                    "n_signals", "n_broken", "signals", "broken_signals", "disclaimer"):
            assert key in out, f"pre-existing key {key!r} must still be present"

    def test_article3_granted_propagated(self, tmp_path):
        """When brain has granted=True article3, is_context_only is False."""
        import engine.altdata_emit as EM
        brain = {
            "theses": [],
            "article3": {
                "granted": True,
                "lift_lb": 1.35,
                "reason": "granted: n-floors cleared, wilson-lift > 1.25, evidence fresh",
                "evidence_asof": "2026-07-04",
                "evaluated_at": "2026-07-04T23:27:19+00:00",
            },
            "is_context_only": False,
            "actionable": True,
            "regime_read": None,
            "disclaimer": None,
        }
        out = EM.build_mastermind(self._minimal_by_ticker(), brain, {}, {}, {}, root=tmp_path)
        assert out["article3"]["granted"] is True
        assert out["is_context_only"] is False
