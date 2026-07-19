"""tests/test_admin_marketing.py — Fail-soft panel tests for admin/marketing.py.

Uses a fixture root with a minimal marketing_state.json matching the frozen
§3 contract shape (authored here, not depending on the engine lane).

Also tests the NEW content() and department() panels added in round 2 of the
Marketing Cockpit build.  The content_plan.json fixture is authored here and
does NOT depend on Lane A (engine lane).

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
# Minimal content_plan.json fixture (§2.3 shape, authored here — no Lane A dep)
# ---------------------------------------------------------------------------

MINIMAL_CONTENT_PLAN = {
    "schema_version": 1,
    "produced_by": "test-fixture",
    "produced_at": "2026-07-18T00:00:00Z",
    "tier": "display",
    "schema": "marketing.content/v1",
    "as_of": "2026-07-18",
    "source": {
        "prophet_plans": 3,
        "plans_with_charts": 2,
        "note": "test fixture — no real Prophet data",
    },
    "content_types": [
        {"id": "signal",    "name": "Signal Alert",          "desc": "A Prophet plan as a cashtag post + chart.", "color": "#38e0d4"},
        {"id": "chart",     "name": "Chart of the Day",      "desc": "A notable price chart.",                   "color": "#6a8dff"},
        {"id": "education", "name": "Plain-English Explainer","desc": "Simple concept explainers.",              "color": "#b18cff"},
        {"id": "macro",     "name": "Macro Note",            "desc": "Big-picture macro context.",               "color": "#ffb84d"},
        {"id": "receipt",   "name": "Report Card",           "desc": "Outcome reopen / call review.",            "color": "#4ad6a0"},
        {"id": "watchlist", "name": "On Our Radar",          "desc": "Names we are watching.",                   "color": "#93a0b4"},
        {"id": "event",     "name": "Event Reaction",        "desc": "Reaction to a market event.",              "color": "#ff6b6b"},
    ],
    "accounts": [
        {
            "id": "flagship",
            "name": "Flagship",
            "kind": "branded",
            "voice": "authoritative desk",
            "tilt": {
                "signal": 0.38, "chart": 0.14, "education": 0.10,
                "macro": 0.14, "receipt": 0.10, "watchlist": 0.07, "event": 0.07,
            },
            "mix_observed": {
                "signal": 8, "chart": 3, "education": 2, "macro": 3,
                "receipt": 2, "watchlist": 1, "event": 2,
            },
            "queue": [
                {
                    "id": "post-flagship-001",
                    "type": "signal",
                    "account": "flagship",
                    "cashtag": "$TNDM",
                    "ticker": "TNDM",
                    "headline": "Tandem Diabetes — momentum building after catalyst",
                    "body": "Watch $TNDM. The technical picture shifted this week; what to watch: FDA label update timeline. What would change this: broad medtech selloff.",
                    "provenance": "neural_web",
                    "chart_id": "chart-001",
                    "slot": "D1-AM",
                    "status": "drafted",
                },
                {
                    "id": "post-flagship-002",
                    "type": "macro",
                    "account": "flagship",
                    "cashtag": None,
                    "ticker": None,
                    "headline": "Fed pivot window: what the bond market is telling you",
                    "body": "Rates moved; here is what it means for equity risk appetite and where to watch for confirmation.",
                    "provenance": "neural_web",
                    "chart_id": None,
                    "slot": "D1-PM",
                    "status": "drafted",
                },
            ],
        },
        {
            "id": "research_a",
            "name": "Research A",
            "kind": "generic",
            "voice": "educational",
            "tilt": {
                "signal": 0.28, "chart": 0.12, "education": 0.22,
                "macro": 0.18, "receipt": 0.08, "watchlist": 0.07, "event": 0.05,
            },
            "mix_observed": {
                "signal": 6, "chart": 2, "education": 5, "macro": 4,
                "receipt": 2, "watchlist": 2, "event": 0,
            },
            "queue": [
                {
                    "id": "post-research_a-001",
                    "type": "education",
                    "account": "research_a",
                    "cashtag": None,
                    "ticker": None,
                    "headline": "What is MACD telling us — without the jargon",
                    "body": "A buy marker on our charts means the price momentum shifted. Here is what that means in plain English.",
                    "provenance": "neural_web",
                    "chart_id": None,
                    "slot": "D2-AM",
                    "status": "drafted",
                },
            ],
        },
    ],
    "featured_charts": [
        {
            "id": "chart-001",
            "ticker": "TNDM",
            "account": "flagship",
            "cashtag": "$TNDM",
            "marker_source": "macd_cross",
            "marker_date": "2026-06-24",
            "marker_price": 15.28,
            "svg": "<svg viewBox='0 0 560 300' xmlns='http://www.w3.org/2000/svg'><rect width='560' height='300' fill='#0d1117'/><text x='10' y='20' fill='#38e0d4' font-size='12'>$TNDM</text><polyline points='0,250 100,220 200,180 300,150 400,120 500,90' stroke='#38e0d4' stroke-width='2' fill='none'/><polygon points='300,130 295,145 305,145' fill='#3ddc84'/><text x='295' y='125' fill='#3ddc84' font-size='10'>BUY</text></svg>",
            "headline": "TNDM buy marker — price momentum shifted",
            "body": "Watch $TNDM at current levels. The price line crossed into new territory.",
        },
    ],
    "distinctness": {
        "max_similarity": 0.12,
        "flags": 0,
        "note": "same signal rendered per-desk; variants checked",
    },
    "summary": {
        "total_posts": 3,
        "signal_posts": 1,
        "charts": 1,
        "accounts": 2,
    },
}


# ---------------------------------------------------------------------------
# State fixture extended with new dept fields (name short, formal_name, tagline, icon, engines as dicts)
# ---------------------------------------------------------------------------

MINIMAL_STATE_V2 = dict(MINIMAL_STATE)  # shallow copy; override departments below
MINIMAL_STATE_V2["departments"] = [
    {
        "id": "office_cmo",
        "name": "Command",
        "formal_name": "Office of the Autonomous CMO",
        "tagline": "Sets strategy, allocates budget, hires and retires teams.",
        "icon": "command",
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
        "name": "Engine Room",
        "formal_name": "Growth Operating System & Finance",
        "tagline": "Keeps everything running — scheduling, budgets, credentials, recovery.",
        "icon": "engine_room",
        "director_model": "opus",
        "primary_outcome": "Scalable, repeatable growth infrastructure.",
        "non_goals": [],
        "engines": [
            {"id": "campaign_compiler", "name": "Campaign Compiler", "does": "Turns opportunity data into a structured campaign brief."},
            {"id": "opportunity_bus", "name": "Opportunity Bus", "does": "Scores and queues incoming opportunities from the intelligence layer."},
        ],
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
]


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
def seeded_root_v2(tmp_path):
    """Fixture root with v2 state (short name / formal_name / tagline / engines-as-dicts)."""
    nw_dir = tmp_path / "data" / "neuralweb"
    nw_dir.mkdir(parents=True)
    (nw_dir / "marketing_state.json").write_text(
        json.dumps(MINIMAL_STATE_V2, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return tmp_path


@pytest.fixture()
def seeded_content_root(tmp_path):
    """Fixture root with both marketing_state.json and content_plan.json."""
    nw_dir = tmp_path / "data" / "neuralweb"
    nw_dir.mkdir(parents=True)
    (nw_dir / "marketing_state.json").write_text(
        json.dumps(MINIMAL_STATE_V2, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    content_dir = tmp_path / "data" / "marketing"
    content_dir.mkdir(parents=True)
    (content_dir / "content_plan.json").write_text(
        json.dumps(MINIMAL_CONTENT_PLAN, ensure_ascii=False, indent=2),
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
        """Belt-and-suspenders: none of the panels may raise on empty root."""
        for fn_name in ("overview", "departments", "channels", "campaigns",
                        "experiments", "lobes", "settings", "content"):
            fn = getattr(marketing, fn_name)
            try:
                result = fn(empty_root)
                assert isinstance(result, dict), f"{fn_name} returned non-dict: {result!r}"
            except Exception as exc:  # noqa: BLE001
                pytest.fail(f"marketing.{fn_name}() raised on empty root: {exc}")

    def test_department_fail_soft(self, empty_root):
        r = marketing.department(empty_root, dept_id="office_cmo")
        _assert_fail_soft(r, "department")
        assert r["department"] is None

    def test_content_fail_soft(self, empty_root):
        r = marketing.content(empty_root)
        _assert_fail_soft(r, "content")
        assert r["content_types"] == []
        assert r["accounts"] == []
        assert r["featured_charts"] == []


# ---------------------------------------------------------------------------
# Tests — departments now have name (short), formal_name, tagline, icon
# ---------------------------------------------------------------------------

class TestDepartmentShape:
    """Verify departments in the live engine have the new spec §1.1 shape."""

    def test_departments_have_short_names(self):
        from engine.marketing.departments import DEPARTMENT_CHARTERS
        short_names = {d.name for d in DEPARTMENT_CHARTERS}
        expected_short = {
            "Command", "Engine Room", "Radar", "Workshop", "Studio",
            "Broadcast", "Funnel", "Allies", "Lab", "Sentinel",
            "Beacon",  # Organic Search & Public Pages — added by the MNZ program
        }
        assert expected_short == short_names, (
            f"Short names mismatch. Got: {short_names}"
        )

    def test_departments_have_formal_name(self):
        from engine.marketing.departments import DEPARTMENT_CHARTERS
        for dept in DEPARTMENT_CHARTERS:
            d = dept.as_dict()
            assert d.get("formal_name"), f"dept {dept.id} missing formal_name"

    def test_departments_have_tagline(self):
        from engine.marketing.departments import DEPARTMENT_CHARTERS
        for dept in DEPARTMENT_CHARTERS:
            d = dept.as_dict()
            assert d.get("tagline"), f"dept {dept.id} missing tagline"

    def test_departments_have_icon(self):
        from engine.marketing.departments import DEPARTMENT_CHARTERS
        for dept in DEPARTMENT_CHARTERS:
            d = dept.as_dict()
            assert d.get("icon"), f"dept {dept.id} missing icon"

    def test_engines_are_dicts(self):
        from engine.marketing.departments import DEPARTMENT_CHARTERS
        for dept in DEPARTMENT_CHARTERS:
            d = dept.as_dict()
            for engine in d["engines"]:
                assert isinstance(engine, dict), (
                    f"dept {dept.id}: engine is not dict: {engine!r}"
                )
                assert "id" in engine and "name" in engine and "does" in engine, (
                    f"dept {dept.id}: engine missing keys: {engine}"
                )


# ---------------------------------------------------------------------------
# Tests — content() panel (round 2)
# ---------------------------------------------------------------------------

class TestContentPanel:
    def test_content_ok_with_data(self, seeded_content_root):
        r = marketing.content(seeded_content_root)
        assert r["ok"] is True
        assert isinstance(r["content_types"], list)
        assert len(r["content_types"]) == 7
        assert isinstance(r["accounts"], list)
        assert len(r["accounts"]) == 2
        assert isinstance(r["featured_charts"], list)
        assert len(r["featured_charts"]) == 1
        assert r["summary"]["total_posts"] == 3
        assert r["summary"]["signal_posts"] == 1
        assert r["summary"]["charts"] == 1
        assert r["summary"]["accounts"] == 2
        assert r["distinctness"]["flags"] == 0

    def test_content_type_fields(self, seeded_content_root):
        r = marketing.content(seeded_content_root)
        ct = r["content_types"][0]
        assert "id" in ct
        assert "name" in ct
        assert "color" in ct

    def test_content_account_tilt(self, seeded_content_root):
        r = marketing.content(seeded_content_root)
        acct = r["accounts"][0]
        assert acct["id"] == "flagship"
        tilt = acct["tilt"]
        assert "signal" in tilt
        # signal must be the largest weight for flagship
        assert tilt["signal"] >= max(v for k, v in tilt.items() if k != "signal")

    def test_content_featured_chart_has_svg(self, seeded_content_root):
        r = marketing.content(seeded_content_root)
        fc = r["featured_charts"][0]
        assert fc["ticker"] == "TNDM"
        assert fc["svg"].startswith("<svg")
        assert "BUY" in fc["svg"]

    def test_content_queue_posts(self, seeded_content_root):
        r = marketing.content(seeded_content_root)
        flagship = next(a for a in r["accounts"] if a["id"] == "flagship")
        queue = flagship["queue"]
        assert len(queue) == 2
        signal_post = next(p for p in queue if p["type"] == "signal")
        assert signal_post["cashtag"] == "$TNDM"
        assert signal_post["chart_id"] == "chart-001"
        assert signal_post["status"] == "drafted"

    def test_content_fail_soft_absent(self, seeded_root):
        """content_plan.json absent → ok:True with honest note, empty lists."""
        r = marketing.content(seeded_root)
        assert r["ok"] is True
        assert r.get("note") is not None
        assert "accruing" in r["note"].lower() or "not yet" in r["note"].lower()
        assert r["content_types"] == []
        assert r["accounts"] == []
        assert r["featured_charts"] == []

    def test_content_fail_soft_empty_root(self, empty_root):
        r = marketing.content(empty_root)
        _assert_fail_soft(r, "content")
        assert r["content_types"] == []
        assert r["accounts"] == []


# ---------------------------------------------------------------------------
# Tests — department() panel (round 2)
# ---------------------------------------------------------------------------

class TestDepartmentPanel:
    def test_department_ok_known_id(self, seeded_root_v2):
        r = marketing.department(seeded_root_v2, dept_id="growth_os")
        assert r["ok"] is True
        dept = r["department"]
        assert dept is not None
        assert dept["id"] == "growth_os"
        assert dept["name"] == "Engine Room"
        assert dept["formal_name"] == "Growth Operating System & Finance"
        assert dept["tagline"] is not None
        assert dept["icon"] == "engine_room"

    def test_department_engines_as_dicts(self, seeded_root_v2):
        r = marketing.department(seeded_root_v2, dept_id="growth_os")
        engines = r["department"]["engines"]
        assert len(engines) == 2
        eng = engines[0]
        assert "id" in eng
        assert "name" in eng
        assert "does" in eng

    def test_department_known_id_cmo(self, seeded_root_v2):
        r = marketing.department(seeded_root_v2, dept_id="office_cmo")
        assert r["ok"] is True
        dept = r["department"]
        assert dept["name"] == "Command"
        assert dept["formal_name"] == "Office of the Autonomous CMO"
        assert dept["engines"] == []

    def test_department_unknown_id_fail_soft(self, seeded_root_v2):
        r = marketing.department(seeded_root_v2, dept_id="does_not_exist")
        assert r["ok"] is True
        assert r["department"] is None
        assert r.get("note") is not None

    def test_department_none_id_fail_soft(self, seeded_root_v2):
        r = marketing.department(seeded_root_v2, dept_id=None)
        assert r["ok"] is True
        assert r["department"] is None

    def test_department_fail_soft_absent_state(self, empty_root):
        r = marketing.department(empty_root, dept_id="office_cmo")
        _assert_fail_soft(r, "department")
        assert r["department"] is None

    def test_no_new_panel_raises_empty_root(self, empty_root):
        """content() and department() must not raise on empty root."""
        for fn_name, kwargs in [("content", {}), ("department", {"dept_id": "office_cmo"})]:
            fn = getattr(marketing, fn_name)
            try:
                result = fn(empty_root, **kwargs)
                assert isinstance(result, dict), f"{fn_name} returned non-dict: {result!r}"
            except Exception as exc:  # noqa: BLE001
                pytest.fail(f"marketing.{fn_name}() raised on empty root: {exc}")
