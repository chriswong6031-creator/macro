"""tests/test_admin_marketing.py — Fail-soft panel tests for admin/marketing.py.

Uses a fixture root with a minimal marketing_state.json matching the frozen
§3 contract shape (authored here, not depending on the engine lane).

Assertions:
  - Each panel returns ok:True with expected top-level sections when data is present.
  - Each panel returns ok:True with empty/honest state (never raises) when the
    state file is missing (empty fixture root).
"""
from __future__ import annotations

import json
import pathlib

import pytest

from admin import marketing


# ---------------------------------------------------------------------------
# Minimal frozen-contract fixture
# ---------------------------------------------------------------------------

MINIMAL_STATE = {
    "schema_version": 1,
    "produced_by": "test-fixture",
    "produced_at": "2026-07-18T00:00:00Z",
    "inputs_hash": "sha256:0000000000000000000000000000000000000000000000000000000000000000",
    "tier": "display",
    "schema": "marketing.state/v1",
    "as_of": "2026-07-18",
    "lobe": {
        "id": "marketing",
        "name": "Marketing",
        "lifecycle_state": "chartered",
        "authority_level": "G2",
        "mandate": {
            "category": "Accountable AI market intelligence",
            "promise": "Know what changed, why it matters, and what to watch next.",
            "proof": "Every important conclusion carries evidence, invalidation, timestamp, and outcome history.",
            "icp": "Self-directed, research-intensive swing/position investors following 10-100 names.",
            "first_paid_job": "Continuously monitor what matters to my holdings/watchlist and tell me when the causal picture changes.",
        },
    },
    "north_star": {
        "metric": "retained_users_90d",
        "value": None,
        "state": "accruing",
        "note": "Shadow mode — no real users enrolled yet.",
    },
    "cmo": {
        "director": "Fable",
        "portfolio": {
            "allocations": [
                {"department": "growth_os", "weight": 0.25, "rank": 1},
                {"department": "intelligence", "weight": 0.2, "rank": 2},
            ],
            "total_envelope_usd": 0,
        },
        "opportunity_queue_depth": 1,
        "self_improvement": {
            "loop_state": "observing",
            "open_hypotheses": [
                {"id": "h001", "text": "Content resonance drives trial conversion", "status": "open"},
            ],
            "last_review": None,
            "next_review": "2026-08-18",
        },
        "guardrails": {
            "self_deception_checks": [
                {"name": "vanity_metric_firewall", "status": "enforced", "note": "Vanity metrics excluded from scorecard."},
                {"name": "correction_bus_open", "status": "enforced", "note": "All corrections propagate to derivatives."},
            ],
        },
    },
    "departments": [
        {
            "id": "office_cmo",
            "name": "Office of the CMO",
            "director_model": "fable",
            "primary_outcome": "Coherent growth strategy and authority ladder.",
            "non_goals": ["Paid media buying"],
            "engines": [],
            "authority_level": "G2",
            "lifecycle_state": "chartered",
            "budget": {"envelope_usd": 0, "spent_usd": 0},
            "model_mix": {},
            "clock": {"cadence": "weekly", "last_review": None, "next_review": "2026-07-25"},
            "retirement_test": "North-star flat for 3 consecutive quarters after G4.",
            "scorecard": {
                "primary_metric": "authority_level",
                "leading": [],
                "trust_health": "clean",
                "experiment_velocity": 0,
                "learning_quality": "seeding",
                "authority_level": "G2",
            },
            "wave": 0,
        },
        {
            "id": "growth_os",
            "name": "Growth OS",
            "director_model": "opus",
            "primary_outcome": "Scalable, repeatable growth infrastructure.",
            "non_goals": [],
            "engines": ["campaign_compiler", "opportunity_bus"],
            "authority_level": "G2",
            "lifecycle_state": "building",
            "budget": {"envelope_usd": 0, "spent_usd": 0},
            "model_mix": {},
            "clock": {"cadence": "weekly", "last_review": None, "next_review": "2026-07-25"},
            "retirement_test": "Infrastructure fully automated; maintenance only.",
            "scorecard": {
                "primary_metric": "campaigns_compiled_per_week",
                "leading": [],
                "trust_health": "clean",
                "experiment_velocity": 0,
                "learning_quality": "seeding",
                "authority_level": "G2",
            },
            "wave": 0,
        },
    ],
    "authority_ladder": [
        {"level": "G0", "name": "Observe", "desc": "Gather data; no outbound action."},
        {"level": "G1", "name": "Draft", "desc": "Produce content; human approves before publish."},
        {"level": "G2", "name": "Scheduled", "desc": "Publish on a pre-approved schedule."},
        {"level": "G3", "name": "Responsive", "desc": "Publish in response to events; human reviews."},
        {"level": "G4", "name": "Autonomous", "desc": "Full publish autonomy within policy."},
        {"level": "G5", "name": "Budgeted", "desc": "Allocate within approved budget envelope."},
        {"level": "G6", "name": "Commercial", "desc": "Transact; paid partnerships within policy."},
        {"level": "G7", "name": "Strategic", "desc": "Multi-year partnerships and M&A recommendations."},
    ],
    "desk_network": {
        "stage": "A",
        "actuation": {"path": "human_in_loop", "api_eligible": False, "control_loop": "drafted"},
        "distinctness": {"max_similarity": 0.0, "flags": 0},
        "accounts": [
            {
                "id": "flagship",
                "handle": None,
                "kind": "branded",
                "beat": "What changed and why it matters",
                "voice": "authoritative desk",
                "corpus": "full",
                "stage": "A",
                "status": "warming",
                "authority": "G1",
                "health": {"warnings": 0, "followers": None, "engagement": None},
            },
            {
                "id": "research_a",
                "handle": None,
                "kind": "generic",
                "beat": "Macro/rates/liquidity explainers",
                "voice": "educational",
                "corpus": "macro",
                "stage": "A",
                "status": "warming",
                "authority": "G1",
                "health": {"warnings": 0, "followers": None, "engagement": None},
            },
        ],
    },
    "pipeline": {
        "opportunities": {
            "open": 1,
            "scored": 1,
            "newest": [
                {
                    "id": "seed-opp-001",
                    "problem_or_desire": "Investors need to track what the smart money is buying.",
                    "expected_value": 0.8,
                    "score": 0.72,
                    "half_life_class": "evergreen",
                    "status": "scored",
                },
            ],
        },
        "campaigns": {
            "active": 0,
            "shadow": 1,
            "newest": [
                {
                    "id": "seed-cmpgn-001",
                    "objective": "Drive trial signups from market-intelligence audience.",
                    "audience": "self-directed investors",
                    "promise": "Know what changed, why it matters.",
                    "channels": ["flagship"],
                    "authority_level": "G1",
                    "status": "shadow",
                },
            ],
        },
        "publications": {
            "total": 0,
            "receipts": 0,
            "corrections": 0,
            "newest": [],
        },
        "experiments": {
            "running": 0,
            "newest": [],
        },
        "growth_events": {
            "instrumented": [
                "trial_start", "trial_convert", "churn", "referral",
                "content_share", "dashboard_open", "alert_engaged",
            ],
            "observed": 0,
        },
    },
    "provenance": {
        "modes": ["neural_web", "marketing_original", "hybrid"],
        "claims": {"total": 0, "open": 0, "resolved": 0},
    },
    "economics": {
        "formula": "retained contribution = recognized revenue - fees - refunds - payouts - paid media - inference - data/delivery - support",
        "cohorts": [],
        "budget_allocator": {"method": "scorecard-weighted", "total_envelope_usd": 0, "allocations": []},
    },
    "channels_priority": {"tier1": ["flagship"], "tier2": ["research_a"], "tier3": [], "tier4": []},
    "waves": [
        {"id": "wave0", "title": "Root charter & inventory", "status": "active", "goal": "Establish lobe charter and seed all 10 departments."},
        {"id": "wave1", "title": "Shadow distribution", "status": "planned", "goal": "Produce shadow-mode content from neural web signals."},
    ],
    "notes": ["deterministic v1 substrate; agent actuation staged", "shadow mode: no real accounts live yet"],
}


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture()
def seeded_root(tmp_path):
    """Fixture root with a minimal marketing_state.json committed."""
    nw_dir = tmp_path / "data" / "neuralweb"
    nw_dir.mkdir(parents=True)
    (nw_dir / "marketing_state.json").write_text(
        json.dumps(MINIMAL_STATE, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return tmp_path


@pytest.fixture()
def empty_root(tmp_path):
    """Fixture root with NO marketing_state.json (simulates day-0 / missing)."""
    return tmp_path


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _assert_fail_soft(result: dict, panel_name: str) -> None:
    """Panel must return a dict with ok:True (not raise, not ok:False on absence)."""
    assert isinstance(result, dict), f"{panel_name}: expected dict, got {type(result)}"
    assert result.get("ok") is True, f"{panel_name} on empty root must return ok:True, got: {result}"


# ---------------------------------------------------------------------------
# Tests — seeded root (data present)
# ---------------------------------------------------------------------------

class TestSeededRoot:
    def test_overview_ok(self, seeded_root):
        r = marketing.overview(seeded_root)
        assert r["ok"] is True
        assert r["lobe"] is not None
        assert r["lobe"]["id"] == "marketing"
        assert r["north_star"]["state"] == "accruing"
        assert r["cmo"]["director"] == "Fable"
        assert r["mandate"]["category"] == "Accountable AI market intelligence"
        assert r["as_of"] == "2026-07-18"

    def test_departments_ok(self, seeded_root):
        r = marketing.departments(seeded_root)
        assert r["ok"] is True
        assert len(r["departments"]) == 2
        assert len(r["authority_ladder"]) == 8
        ids = {d["id"] for d in r["departments"]}
        assert "office_cmo" in ids
        assert "growth_os" in ids
        # Authority ladder covers G0..G7
        levels = [rung["level"] for rung in r["authority_ladder"]]
        assert "G0" in levels and "G7" in levels

    def test_channels_ok(self, seeded_root):
        r = marketing.channels(seeded_root)
        assert r["ok"] is True
        assert r["desk_network"] is not None
        assert len(r["desk_network"]["accounts"]) == 2
        assert r["desk_network"]["stage"] == "A"
        assert r["publications"] is not None

    def test_campaigns_ok(self, seeded_root):
        r = marketing.campaigns(seeded_root)
        assert r["ok"] is True
        assert r["opportunities"] is not None
        assert r["opportunities"]["open"] == 1
        assert r["campaigns"] is not None
        assert r["pipeline"] is not None

    def test_experiments_ok(self, seeded_root):
        r = marketing.experiments(seeded_root)
        assert r["ok"] is True
        assert r["experiments"] is not None
        assert isinstance(r["trial_variants"], list)
        assert "7_trading_days" in r["trial_variants"]
        assert r["north_star"] is not None

    def test_lobes_ok(self, seeded_root):
        r = marketing.lobes(seeded_root)
        assert r["ok"] is True
        assert isinstance(r["engines_by_department"], list)
        assert len(r["engines_by_department"]) == 2
        assert r["provenance"] is not None
        assert r["provenance"]["modes"] == ["neural_web", "marketing_original", "hybrid"]
        assert r["growth_events"] is not None
        assert "trial_start" in r["growth_events"]["instrumented"]

    def test_settings_ok(self, seeded_root):
        # Settings echoes config/marketing.yml — absent here → defaults returned
        r = marketing.settings(seeded_root)
        assert r["ok"] is True
        assert "settings" in r
        s = r["settings"]
        assert s["trial_variant"] in ("7_trading_days", "14_calendar_days", "value_moment_limited")
        assert isinstance(s["paid_enabled"], bool)
        assert isinstance(s["auditor_strict"], bool)


# ---------------------------------------------------------------------------
# Tests — empty root (fail-soft / accruing)
# ---------------------------------------------------------------------------

class TestEmptyRoot:
    """All panels must return ok:True (not raise) when state file is absent."""

    def test_overview_fail_soft(self, empty_root):
        r = marketing.overview(empty_root)
        _assert_fail_soft(r, "overview")
        # Must include an honest note
        assert r.get("note") is not None
        assert r.get("lobe") is None

    def test_departments_fail_soft(self, empty_root):
        r = marketing.departments(empty_root)
        _assert_fail_soft(r, "departments")
        assert r["departments"] == []
        assert r["authority_ladder"] == []

    def test_channels_fail_soft(self, empty_root):
        r = marketing.channels(empty_root)
        _assert_fail_soft(r, "channels")
        assert r["desk_network"] is None

    def test_campaigns_fail_soft(self, empty_root):
        r = marketing.campaigns(empty_root)
        _assert_fail_soft(r, "campaigns")
        assert r["opportunities"] is None

    def test_experiments_fail_soft(self, empty_root):
        r = marketing.experiments(empty_root)
        _assert_fail_soft(r, "experiments")
        assert r["experiments"] is None
        # Trial variants always returned even when state absent
        assert "7_trading_days" in r["trial_variants"]

    def test_lobes_fail_soft(self, empty_root):
        r = marketing.lobes(empty_root)
        _assert_fail_soft(r, "lobes")
        assert r["engines_by_department"] == []
        assert r["provenance"] is None

    def test_settings_fail_soft(self, empty_root):
        # settings reads config/marketing.yml; absent → returns defaults
        r = marketing.settings(empty_root)
        _assert_fail_soft(r, "settings")
        assert "settings" in r

    def test_no_panel_raises(self, empty_root):
        """Belt-and-suspenders: none of the 7 panels may raise on empty root."""
        for fn_name in ("overview", "departments", "channels", "campaigns",
                        "experiments", "lobes", "settings"):
            fn = getattr(marketing, fn_name)
            try:
                result = fn(empty_root)
                assert isinstance(result, dict), f"{fn_name} returned non-dict: {result!r}"
            except Exception as exc:  # noqa: BLE001
                pytest.fail(f"marketing.{fn_name}() raised on empty root: {exc}")
