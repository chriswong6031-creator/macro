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


# ---------------------------------------------------------------------------
# Radar fixtures (§data contracts — authored here, no Lane A dep)
# ---------------------------------------------------------------------------

MINIMAL_RADAR_REPORT = {
    "schema": "marketing.radar_report/v1",
    "as_of": "2026-07-18",
    "produced_at": "2026-07-18T06:00:00Z",
    "feeds": [
        {"name": "prophet",    "ok": True,  "n_assets": 42, "as_of": "2026-07-18"},
        {"name": "confluence", "ok": True,  "n_assets": 18, "as_of": "2026-07-18"},
        {"name": "movers",     "ok": True,  "n_assets": 25, "as_of": "2026-07-18"},
        {"name": "earnings",   "ok": False, "n_assets": 0,  "as_of": None},
        {"name": "stage",      "ok": True,  "n_assets": 2710, "as_of": "2026-07-17"},
    ],
    "posted_recent": {"n_tickers": 6, "window_plans": 7},
    "surplus": [
        {"ticker": "TNDM", "feed": "prophet", "why": "Momentum turned up after a catalyst; not yet posted this week.",
         "as_of": "2026-07-18", "staleness_days": 0, "opportunity_id": "opp-tndm-001"},
        {"ticker": "AMKR", "feed": "movers", "why": "Big down day on volume — a name readers will ask about.",
         "as_of": "2026-07-15", "staleness_days": 3, "opportunity_id": "opp-amkr-002"},
        {"ticker": "CRDO", "feed": "confluence", "why": "Two feeds agree; a similar name went out yesterday, so it's held.",
         "as_of": "2026-07-10", "staleness_days": 8, "opportunity_id": "opp-crdo-003"},
    ],
    "queue": {"added": 4, "expired": 1, "total": 12, "open": 9},
    "tiers_summary": {"as_of": "2026-07-18", "t1": 3, "t2": 4, "t3": 2},
    "cadence": {"available": True, "source": "public timelines", "competitors": ["@deskA", "@deskB"], "posts_per_day": 5.5},
}

MINIMAL_CASHTAG_TIERS = {
    "schema": "marketing.cashtag_tiers/v1",
    "as_of": "2026-07-18",
    "universe_n": 9,
    "tiers": {
        "T1": ["NVDA", "TSLA", "AAPL"],
        "T2": ["TNDM", "AMKR", "CRDO", "BG"],
        "T3": ["UNIT", "GIII"],
    },
    "tickers": {
        "NVDA": {"tier": "T1", "reasons": ["mega-cap", "high retail attention"],
                 "proxies": {"mcap_weight": 0.07, "pct_1d": 1.2, "pct_1w": 3.4, "earnings_in_days": 21, "dollar_vol_musd": 32000}},
        "TNDM": {"tier": "T2", "reasons": ["mid-cap", "catalyst pending"],
                 "proxies": {"mcap_weight": 0.001, "pct_1d": -0.4, "pct_1w": 5.1, "earnings_in_days": 8, "dollar_vol_musd": 120}},
        "UNIT": {"tier": "T3", "reasons": ["thin volume", "low attention"],
                 "proxies": {"mcap_weight": 0.0001, "pct_1d": 0.1, "pct_1w": -1.2, "earnings_in_days": 40, "dollar_vol_musd": 6}},
    },
}


@pytest.fixture()
def seeded_radar_root(tmp_path):
    """Fixture root with marketing_state.json + radar_report.json + cashtag_tiers.json."""
    nw_dir = tmp_path / "data" / "neuralweb"
    nw_dir.mkdir(parents=True)
    (nw_dir / "marketing_state.json").write_text(
        json.dumps(MINIMAL_STATE, ensure_ascii=False, indent=2), encoding="utf-8",
    )
    mkt_dir = tmp_path / "data" / "marketing"
    mkt_dir.mkdir(parents=True)
    (mkt_dir / "radar_report.json").write_text(
        json.dumps(MINIMAL_RADAR_REPORT, ensure_ascii=False, indent=2), encoding="utf-8",
    )
    (mkt_dir / "cashtag_tiers.json").write_text(
        json.dumps(MINIMAL_CASHTAG_TIERS, ensure_ascii=False, indent=2), encoding="utf-8",
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
                        "experiments", "lobes", "settings", "content", "radar"):
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

    # ── F7: payload timestamps for the admin (display_time / produced_at / stale) ──

    def test_content_posts_carry_display_time(self, seeded_content_root):
        """Each post gets display_time = slot_datetime(as_of, slot). The fixture
        as_of is 2026-07-18, so D1 slots are that day and D2 is the next."""
        r = marketing.content(seeded_content_root)
        by_slot = {p["slot"]: p
                   for a in r["accounts"] for p in a["queue"] if p.get("slot")}
        assert by_slot["D1-AM"]["display_time"] == "2026-07-18T14:00:00Z"
        assert by_slot["D1-PM"]["display_time"] == "2026-07-18T17:30:00Z"
        assert by_slot["D2-AM"]["display_time"] == "2026-07-19T14:00:00Z"  # +1 day

    def test_content_top_level_produced_and_stale(self, seeded_content_root):
        r = marketing.content(seeded_content_root)
        # Fixture as_of 2026-07-18 is well over a day old → stale.
        assert r["as_of"] == "2026-07-18"
        assert r["produced_at"] == "2026-07-18T00:00:00Z"
        assert r["stale"] is True

    def test_content_fresh_plan_not_stale(self, tmp_path):
        """A plan whose as_of is today (UTC) is NOT stale."""
        from datetime import datetime, timezone
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        plan = {**MINIMAL_CONTENT_PLAN, "as_of": today}
        cdir = tmp_path / "data" / "marketing"
        cdir.mkdir(parents=True)
        (cdir / "content_plan.json").write_text(json.dumps(plan), encoding="utf-8")
        r = marketing.content(tmp_path)
        assert r["stale"] is False

    # ── Usage fold (staleness fix, 2026-07-27): plan posts show real outbox
    #    status instead of a forever-"drafted" badge. ─────────────────────────

    def _find_post(self, r, post_id):
        for a in r["accounts"]:
            for p in a.get("queue", []):
                if p.get("id") == post_id:
                    return p
        return None

    def test_content_usage_fold_posted_via_plan_post_id(self, seeded_content_root):
        """An outbox item stamped source.plan_post_id and walked to 'posted' folds
        usage=posted onto the matching plan post (exact join)."""
        from datetime import datetime, timezone
        from engine.marketing.outbox import make_item, enqueue, transition
        _now = datetime(2026, 7, 18, 12, 0, tzinfo=timezone.utc)
        it = make_item(account="flagship", kind="signal",
                       text="Some emitted copy that need not match the plan text.",
                       as_of="2026-07-18", provenance="content_studio",
                       source={"plan_post_id": "post-flagship-001"}, now=_now)
        assert enqueue(it, root=seeded_content_root, max_per_account_day=99) == "queued"
        for to in ("approved", "posting", "posted"):
            assert transition(it["id"], to, actor="t", root=seeded_content_root, now=_now)

        r = marketing.content(seeded_content_root)
        post = self._find_post(r, "post-flagship-001")
        assert post is not None
        assert post["usage"] == "posted"
        assert post.get("usage_at")  # ISO timestamp present
        assert r.get("posted_7d", 0) >= 1

    def test_content_usage_fold_text_fallback(self, seeded_content_root):
        """A historical outbox item WITHOUT plan_post_id folds via the (account,
        normalized text) join built from the plan post's headline+body."""
        from datetime import datetime, timezone
        from engine.marketing.outbox import make_item, enqueue, transition
        _now = datetime(2026, 7, 18, 12, 0, tzinfo=timezone.utc)
        # Reconstruct the plan post's text exactly as emit_from_content_plan does.
        headline = "Fed pivot window: what the bond market is telling you"
        body = ("Rates moved; here is what it means for equity risk appetite and "
                "where to watch for confirmation.")
        text = f"{headline}\n\n{body}"
        it = make_item(account="flagship", kind="macro", text=text,
                       as_of="2026-07-18", provenance="content_studio", now=_now)
        assert enqueue(it, root=seeded_content_root, max_per_account_day=99) == "queued"
        assert transition(it["id"], "approved", actor="t", root=seeded_content_root, now=_now)

        r = marketing.content(seeded_content_root)
        post = self._find_post(r, "post-flagship-002")
        assert post is not None
        assert post["usage"] == "approved"

    def test_content_usage_absent_when_never_emitted(self, seeded_content_root):
        """A plan post with no matching outbox item carries NO usage field."""
        r = marketing.content(seeded_content_root)
        post = self._find_post(r, "post-flagship-001")
        assert post is not None
        assert "usage" not in post

    def test_content_usage_fold_failure_serves_plan(self, seeded_content_root, monkeypatch):
        """Any exception in the fold → the plan is served with no usage fields,
        never a broken panel."""
        import engine.marketing.outbox as _ob

        def _boom(*a, **k):
            raise RuntimeError("fold blew up")
        monkeypatch.setattr(_ob, "fold_state", _boom)

        r = marketing.content(seeded_content_root)
        assert r["ok"] is True
        for a in r["accounts"]:
            for p in a.get("queue", []):
                assert "usage" not in p


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


# ---------------------------------------------------------------------------
# Lab roll-up fixtures (§D03 lab_rollup.json shape, authored here — no engine dep)
# ---------------------------------------------------------------------------

# Populated: one clearly above-floor cell (n=46), several below-floor (n<20),
# and a spread of hypothesis states so the N-floor and state-mapping are tested.
POPULATED_LAB_ROLLUP = {
    "schema_version": 1,
    "produced_by": "test-fixture",
    "tier": "display",
    "schema": "marketing.lab_rollup/v1",
    "as_of": "2026-07-19",
    "n_posts": 214,
    "n_rows": 631,
    "n_orphans": 4,
    "cells": [
        {"dims": {"kind": "signal",    "account": "flagship",  "persona": "desk",    "slot": "am", "mode": "det", "cashtag_tier": "high"}, "n": 46, "med_impressions": 3120, "med_likes": 41, "med_replies": 6, "med_reposts": 9},
        {"dims": {"kind": "chart",     "account": "flagship",  "persona": "desk",    "slot": "pm", "mode": "det", "cashtag_tier": "mid"},  "n": 29, "med_impressions": 1980, "med_likes": 22, "med_replies": 2, "med_reposts": 4},
        {"dims": {"kind": "education", "account": "research_a", "persona": "teacher", "slot": "pm", "mode": "llm", "cashtag_tier": "none"}, "n": 24, "med_impressions": 1210, "med_likes": 18, "med_replies": 3, "med_reposts": 2},
        {"dims": {"kind": "receipt",   "account": "flagship",  "persona": "desk",    "slot": "pm", "mode": "det", "cashtag_tier": "mid"},  "n": 14, "med_impressions": 2200, "med_likes": 27, "med_replies": 3, "med_reposts": 6},
        {"dims": {"kind": "event",     "account": "research_a", "persona": "teacher", "slot": "am", "mode": "llm", "cashtag_tier": "mid"},  "n": 9,  "med_impressions": 890,  "med_likes": 11, "med_replies": 1, "med_reposts": 1},
        {"dims": {"kind": "watchlist", "account": "flagship",  "persona": "desk",    "slot": "pm", "mode": "det", "cashtag_tier": "low"},  "n": 5,  "med_impressions": 640,  "med_likes": 7,  "med_replies": 0, "med_reposts": 1},
    ],
    "top_posts": [
        {"post_id": "flagship-000817",   "dims": {"kind": "signal",  "account": "flagship",  "cashtag_tier": "high", "slot": "am"}, "impressions": 8420, "likes": 112, "replies": 19},
        {"post_id": "research_a-000642", "dims": {"kind": "signal",  "account": "research_a", "cashtag_tier": "high", "slot": "am"}, "impressions": 5330, "likes": 61,  "replies": 8},
    ],
    "hypotheses": [
        {"id": "H1", "title": "Multi-cashtag theme lists reach further than single-name posts", "state": "confirmed", "n_evidence": 46, "note": "Cashtag posts land ~2.6x the impressions."},
        {"id": "H2", "title": "Instant earnings reactions beat next-morning recaps",             "state": "seeding",   "n_evidence": 9,  "note": "Too few event posts to call."},
        {"id": "H3", "title": "The educational voice needs a cashtag to travel",                 "state": "refuted",   "n_evidence": 24, "note": "Cashtag added no measurable lift."},
        {"id": "H4", "title": "Odd state defaults to seeding",                                    "state": "bogus",     "n_evidence": 3,  "note": "Unknown state must not read as confirmed."},
    ],
}

# Zero-posts variant: file present, but nothing posted yet (the day-0 reality).
# Seeded hypotheses are carried so the operator still sees the bench.
ZERO_POSTS_LAB_ROLLUP = {
    "schema": "marketing.lab_rollup/v1",
    "as_of": "2026-07-19",
    "n_posts": 0,
    "n_rows": 0,
    "n_orphans": 0,
    "cells": [],
    "top_posts": [],
    "hypotheses": [
        {"id": "H01", "title": "Multi-cashtag theme list outperforms single-ticker posts", "state": "seeding", "n_evidence": 0, "note": "Playbook §2."},
        {"id": "H02", "title": "Instant earnings reaction posts capture the hot window",    "state": "seeding", "n_evidence": 0, "note": "Playbook §3."},
    ],
}


def _write_lab(root, rollup):
    d = root / "data" / "marketing"
    d.mkdir(parents=True, exist_ok=True)
    (d / "lab_rollup.json").write_text(
        json.dumps(rollup, ensure_ascii=False, indent=2), encoding="utf-8",
    )


@pytest.fixture()
def populated_lab_root(tmp_path):
    """Fixture root with a populated lab_rollup.json (n_posts > 0)."""
    _write_lab(tmp_path, POPULATED_LAB_ROLLUP)
    return tmp_path


@pytest.fixture()
def zero_posts_lab_root(tmp_path):
    """Fixture root with lab_rollup.json present but n_posts == 0 (waiting)."""
    _write_lab(tmp_path, ZERO_POSTS_LAB_ROLLUP)
    return tmp_path


class TestLabPanelPopulated:
    def test_lab_ok_with_data(self, populated_lab_root):
        r = marketing.lab(populated_lab_root)
        assert r["ok"] is True
        assert r["waiting"] is False
        assert r["as_of"] == "2026-07-19"
        assert r["n_posts"] == 214
        assert r["n_orphans"] == 4
        assert r["n_floor"] == 20
        assert len(r["hypotheses"]) == 4
        assert len(r["cells"]) == 6
        assert len(r["top_posts"]) == 2

    def test_lab_hypothesis_states_normalised(self, populated_lab_root):
        r = marketing.lab(populated_lab_root)
        by_id = {h["id"]: h for h in r["hypotheses"]}
        assert by_id["H1"]["state"] == "confirmed"
        assert by_id["H2"]["state"] == "seeding"
        assert by_id["H3"]["state"] == "refuted"
        # An unknown state must fall to the cautious seeding bucket, never confirmed.
        assert by_id["H4"]["state"] == "seeding"

    def test_lab_n_floor_tagging(self, populated_lab_root):
        """Cells with n < 20 are tagged below_floor (kept, not dropped);
        cells at/above 20 are not — so the page can never crown a small cell."""
        r = marketing.lab(populated_lab_root)
        by_n = {c["n"]: c for c in r["cells"]}
        assert by_n[46]["below_floor"] is False
        assert by_n[29]["below_floor"] is False
        assert by_n[24]["below_floor"] is False
        assert by_n[14]["below_floor"] is True
        assert by_n[9]["below_floor"] is True
        assert by_n[5]["below_floor"] is True
        # No cell is dropped — small samples stay visible for honesty.
        assert len(r["cells"]) == 6

    def test_lab_floor_boundary_is_inclusive_at_20(self, tmp_path):
        """n == 20 is exactly at the floor and must NOT be suppressed."""
        rollup = dict(POPULATED_LAB_ROLLUP)
        rollup = json.loads(json.dumps(rollup))  # deep copy
        rollup["cells"] = [
            {"dims": {"kind": "signal", "account": "flagship"}, "n": 20, "med_impressions": 1000, "med_likes": 10, "med_replies": 1, "med_reposts": 1},
            {"dims": {"kind": "chart",  "account": "flagship"}, "n": 19, "med_impressions": 900,  "med_likes": 9,  "med_replies": 1, "med_reposts": 1},
        ]
        _write_lab(tmp_path, rollup)
        r = marketing.lab(tmp_path)
        by_n = {c["n"]: c for c in r["cells"]}
        assert by_n[20]["below_floor"] is False
        assert by_n[19]["below_floor"] is True

    def test_lab_cells_carry_medians(self, populated_lab_root):
        r = marketing.lab(populated_lab_root)
        top = next(c for c in r["cells"] if c["n"] == 46)
        assert top["med_impressions"] == 3120
        assert top["med_likes"] == 41
        assert top["dims"]["kind"] == "signal"


class TestLabPanelWaiting:
    """The empty state is a first-class design requirement, not an error page."""

    def test_lab_waiting_when_file_absent(self, empty_root):
        r = marketing.lab(empty_root)
        _assert_fail_soft(r, "lab")
        assert r["waiting"] is True
        assert r.get("note")
        assert r["n_posts"] == 0
        assert r["cells"] == []
        assert r["top_posts"] == []
        # Absent file → no seeded hypotheses to show yet.
        assert r["hypotheses"] == []

    def test_lab_waiting_with_zero_posts_keeps_seeded_hypotheses(self, zero_posts_lab_root):
        """n_posts == 0 → waiting, but seeded hypotheses ARE surfaced so the
        operator sees what will be measured."""
        r = marketing.lab(zero_posts_lab_root)
        assert r["ok"] is True
        assert r["waiting"] is True
        assert r["n_posts"] == 0
        assert len(r["hypotheses"]) == 2
        assert all(h["state"] == "seeding" for h in r["hypotheses"])
        # No reach data is invented while waiting.
        assert r["cells"] == []
        assert r["top_posts"] == []

    def test_lab_never_invents_numbers_while_waiting(self, zero_posts_lab_root):
        r = marketing.lab(zero_posts_lab_root)
        assert r["n_rows"] == 0
        assert r["n_orphans"] == 0

    def test_lab_does_not_raise_on_empty_root(self, empty_root):
        try:
            result = marketing.lab(empty_root)
            assert isinstance(result, dict)
        except Exception as exc:  # noqa: BLE001
            pytest.fail(f"marketing.lab() raised on empty root: {exc}")


# ---------------------------------------------------------------------------
# Tests — outbox() panel (D02 W0, Lane B)
# ---------------------------------------------------------------------------

_FIXED_NOW_OB = __import__("datetime").datetime(2026, 7, 19, 12, 0, 0,
                                                  tzinfo=__import__("datetime").timezone.utc)
_AS_OF_OB = "2026-07-19"


def _make_ob_item(
    tmp_path,
    *,
    account: str = "flagship",
    kind: str = "signal",
    text: str = "Test post for outbox panel.",
    as_of: str = _AS_OF_OB,
    provenance: str = "content_studio",
):
    from engine.marketing.outbox import make_item
    return make_item(
        account=account,
        kind=kind,
        text=text,
        as_of=as_of,
        provenance=provenance,
        now=_FIXED_NOW_OB,
    )


class TestOutboxPanel:
    # ------------------------------------------------------------------
    # Test 1: empty/temp root
    # ------------------------------------------------------------------

    def test_empty_root_ok_true(self, tmp_path):
        r = marketing.outbox(tmp_path)
        assert r["ok"] is True

    def test_empty_root_has_note(self, tmp_path):
        r = marketing.outbox(tmp_path)
        assert r.get("note") is not None
        assert "outbox empty" in r["note"].lower() or "accrue" in r["note"].lower()

    def test_empty_root_summary_all_zeros(self, tmp_path):
        r = marketing.outbox(tmp_path)
        s = r["summary"]
        assert s["total"] == 0
        for k in ("queued", "approved", "held", "posted", "failed", "quarantined"):
            assert s[k] == 0, f"summary[{k!r}] should be 0"

    def test_empty_root_accounts_empty(self, tmp_path):
        r = marketing.outbox(tmp_path)
        assert r["accounts"] == []

    def test_empty_root_history_empty(self, tmp_path):
        r = marketing.outbox(tmp_path)
        assert r["history"] == []

    def test_empty_root_cap_is_sentinel_floor(self, tmp_path):
        # No config in the tmp root → Sentinel in-code weeks_1_2 default (2).
        r = marketing.outbox(tmp_path)
        assert r["cap"] == 2
        assert r["sentinel"]["source"] == "sentinel_defaults"

    def test_empty_root_as_of_null(self, tmp_path):
        r = marketing.outbox(tmp_path)
        assert r["as_of"] is None

    # ------------------------------------------------------------------
    # Test 2: seeded outbox — 3 items, 2 accounts, hold + posted
    # ------------------------------------------------------------------

    def _seed_outbox(self, tmp_path):
        """Seed 3 items across 2 accounts; hold item2; approve+post item3 with receipt."""
        from engine.marketing.outbox import enqueue, record_decision, transition

        # item1: flagship, queued (no decision)
        item1 = _make_ob_item(
            tmp_path,
            account="flagship",
            text="Flagship queued item — no decision yet.",
        )
        enqueue(item1, root=tmp_path)

        # item2: flagship, hold decision → counts as held
        item2 = _make_ob_item(
            tmp_path,
            account="flagship",
            text="Flagship held item — operator issued hold.",
        )
        enqueue(item2, root=tmp_path)
        record_decision(item2["id"], "hold", actor="operator", root=tmp_path)

        # item3: research_a, queued → approved → posted with a receipt
        item3 = _make_ob_item(
            tmp_path,
            account="research_a",
            kind="education",
            text="Research post that was approved and posted.",
        )
        enqueue(item3, root=tmp_path)
        record_decision(item3["id"], "approve", actor="operator", root=tmp_path)
        transition(item3["id"], "approved", actor="actuator", root=tmp_path)
        receipt = {"tweet_id": "1234567890", "url": "https://x.com/i/web/status/1234567890"}
        transition(
            item3["id"], "posted", actor="actuator", root=tmp_path,
            receipt=receipt,
        )

        return item1["id"], item2["id"], item3["id"]

    def test_seeded_summary_counts(self, tmp_path):
        id1, id2, id3 = self._seed_outbox(tmp_path)
        r = marketing.outbox(tmp_path)
        assert r["ok"] is True
        s = r["summary"]
        assert s["total"] == 3
        assert s["queued"] == 1, f"Expected 1 queued, got {s['queued']}"
        assert s["held"] == 1, f"Expected 1 held, got {s['held']}"
        assert s["posted"] == 1, f"Expected 1 posted, got {s['posted']}"
        assert s["approved"] == 0
        assert s["failed"] == 0
        assert s["quarantined"] == 0

    def test_seeded_held_item_counts_as_held_not_queued(self, tmp_path):
        id1, id2, id3 = self._seed_outbox(tmp_path)
        r = marketing.outbox(tmp_path)
        s = r["summary"]
        # held item must increment held, NOT queued
        assert s["held"] == 1
        assert s["queued"] == 1  # only item1 is truly queued

    def test_seeded_held_item_decision_field(self, tmp_path):
        id1, id2, id3 = self._seed_outbox(tmp_path)
        r = marketing.outbox(tmp_path)
        flagship = next(a for a in r["accounts"] if a["id"] == "flagship")
        held_item = next(i for i in flagship["items"] if i["id"] == id2)
        assert held_item["decision"] == "hold"
        assert held_item["decided_at"] is not None

    def test_seeded_held_item_status_field_is_queued(self, tmp_path):
        """status field on item stays ledger-folded (queued), NOT the overlay held."""
        id1, id2, id3 = self._seed_outbox(tmp_path)
        r = marketing.outbox(tmp_path)
        flagship = next(a for a in r["accounts"] if a["id"] == "flagship")
        held_item = next(i for i in flagship["items"] if i["id"] == id2)
        assert held_item["status"] == "queued"

    def test_seeded_posted_item_in_history(self, tmp_path):
        id1, id2, id3 = self._seed_outbox(tmp_path)
        r = marketing.outbox(tmp_path)
        history_ids = {h["id"] for h in r["history"]}
        assert id3 in history_ids

    def test_seeded_posted_item_receipt_in_history(self, tmp_path):
        id1, id2, id3 = self._seed_outbox(tmp_path)
        r = marketing.outbox(tmp_path)
        posted_h = next(h for h in r["history"] if h["id"] == id3)
        assert posted_h["receipt"] is not None
        assert posted_h["receipt"].get("tweet_id") == "1234567890"

    def test_seeded_accounts_grouped_and_ordered(self, tmp_path):
        id1, id2, id3 = self._seed_outbox(tmp_path)
        r = marketing.outbox(tmp_path)
        acct_ids = [a["id"] for a in r["accounts"]]
        # Both accounts present
        assert "flagship" in acct_ids
        assert "research_a" in acct_ids
        # Sorted alphabetically (flagship < research_a)
        assert acct_ids == sorted(acct_ids)

    def test_seeded_flagship_account_counts(self, tmp_path):
        id1, id2, id3 = self._seed_outbox(tmp_path)
        r = marketing.outbox(tmp_path)
        flagship = next(a for a in r["accounts"] if a["id"] == "flagship")
        c = flagship["counts"]
        assert c["queued"] == 1
        assert c["held"] == 1
        assert c["posted"] == 0

    def test_seeded_cap_is_sentinel_floor(self, tmp_path):
        self._seed_outbox(tmp_path)
        r = marketing.outbox(tmp_path)
        assert r["cap"] == 2

    def test_seeded_as_of_set(self, tmp_path):
        self._seed_outbox(tmp_path)
        r = marketing.outbox(tmp_path)
        assert r["as_of"] == _AS_OF_OB

    # ------------------------------------------------------------------
    # Test 3: decide_outbox wrapper validation
    # ------------------------------------------------------------------

    def test_decide_outbox_approve_success(self, tmp_path):
        from engine.marketing.outbox import enqueue, read_decisions
        item = _make_ob_item(tmp_path, text="Decision wrapper approve test.")
        enqueue(item, root=tmp_path)

        before = len(read_decisions(root=tmp_path))
        result = marketing.decide_outbox(item["id"], "approve", root=tmp_path)
        after = len(read_decisions(root=tmp_path))

        assert result is True
        assert after == before + 1

    def test_decide_outbox_hold_success(self, tmp_path):
        from engine.marketing.outbox import enqueue, read_decisions
        item = _make_ob_item(tmp_path, text="Decision wrapper hold test.")
        enqueue(item, root=tmp_path)

        result = marketing.decide_outbox(item["id"], "hold", root=tmp_path)
        assert result is True

    def test_decide_outbox_unknown_id_returns_false(self, tmp_path):
        result = marketing.decide_outbox("ob-2026-07-19-nonexistent", "approve", root=tmp_path)
        assert result is False

    def test_decide_outbox_bogus_decision_returns_false(self, tmp_path):
        from engine.marketing.outbox import enqueue
        item = _make_ob_item(tmp_path, text="Bogus decision string test.")
        enqueue(item, root=tmp_path)

        result = marketing.decide_outbox(item["id"], "publish", root=tmp_path)
        assert result is False

    # ------------------------------------------------------------------
    # Decision log (per-item audit trail) — complements pipeline activity
    # ------------------------------------------------------------------

    def test_empty_root_decision_log_empty(self, tmp_path):
        r = marketing.outbox(tmp_path)
        assert r["decision_log"] == []

    def test_seeded_decision_log_present_newest_first(self, tmp_path):
        id1, id2, id3 = self._seed_outbox(tmp_path)
        r = marketing.outbox(tmp_path)
        dl = r["decision_log"]
        assert isinstance(dl, list) and len(dl) > 0
        stamps = [e["at"] for e in dl if e.get("at")]
        assert stamps == sorted(stamps, reverse=True)
        for e in dl:
            assert {"type", "id", "account", "kind", "at", "actor"} <= set(e.keys())
        types = {e["type"] for e in dl}
        # both operator decisions and the actuator posted transition are present
        assert "posted" in types and "hold" in types and "approve" in types

    def test_seeded_decision_log_carries_account_and_kind(self, tmp_path):
        id1, id2, id3 = self._seed_outbox(tmp_path)
        r = marketing.outbox(tmp_path)
        posted = next(e for e in r["decision_log"] if e["type"] == "posted")
        assert posted["id"] == id3
        assert posted["account"] == "research_a"
        assert posted["kind"] == "education"


# Tests — radar() panel (MKT-D06 · intelligence department view)
# ---------------------------------------------------------------------------

class TestRadarPanel:
    def test_radar_ok_with_data(self, seeded_radar_root):
        r = marketing.radar(seeded_radar_root)
        assert r["ok"] is True
        assert r["available"] is True
        assert r["as_of"] == "2026-07-18"
        assert r["produced_at"] == "2026-07-18T06:00:00Z"

    def test_radar_feeds(self, seeded_radar_root):
        r = marketing.radar(seeded_radar_root)
        feeds = r["feeds"]
        assert len(feeds) == 5
        names = {f["name"] for f in feeds}
        assert names == {"prophet", "confluence", "movers", "earnings", "stage"}
        # The earnings feed is down in the fixture — carried through faithfully.
        earnings = next(f for f in feeds if f["name"] == "earnings")
        assert earnings["ok"] is False

    def test_radar_surplus_is_the_hero(self, seeded_radar_root):
        r = marketing.radar(seeded_radar_root)
        surplus = r["surplus"]
        assert len(surplus) == 3
        first = surplus[0]
        assert first["ticker"] == "TNDM"
        assert "why" in first and first["why"]
        assert first["feed"] == "prophet"
        assert first["staleness_days"] == 0
        # Order preserved as delivered (sorted upstream).
        assert [s["ticker"] for s in surplus] == ["TNDM", "AMKR", "CRDO"]

    def test_radar_queue(self, seeded_radar_root):
        r = marketing.radar(seeded_radar_root)
        q = r["queue"]
        assert q["open"] == 9
        assert q["total"] == 12
        assert q["added"] == 4
        assert q["expired"] == 1

    def test_radar_tiers(self, seeded_radar_root):
        r = marketing.radar(seeded_radar_root)
        assert r["tiers_summary"]["t1"] == 3
        assert r["tiers_summary"]["t3"] == 2
        assert r["universe_n"] == 9
        assert r["tiers"]["T1"] == ["NVDA", "TSLA", "AAPL"]
        # Per-ticker proxies present for hover/detail (never the glance line).
        assert r["tickers"]["NVDA"]["proxies"]["mcap_weight"] == 0.07

    def test_radar_cadence(self, seeded_radar_root):
        r = marketing.radar(seeded_radar_root)
        cad = r["cadence"]
        assert cad["available"] is True
        assert cad["posts_per_day"] == 5.5
        assert cad["competitors"] == ["@deskA", "@deskB"]

    def test_radar_joins_opportunity_queue_from_state(self, seeded_radar_root):
        """radar() surfaces the scored opportunity pipeline from marketing_state.json."""
        r = marketing.radar(seeded_radar_root)
        assert r["opportunities"] is not None
        assert r["opportunities"]["open"] == 1
        newest = r["opportunities"]["newest"]
        assert newest and newest[0]["half_life_class"] == "evergreen"

    def test_radar_fail_soft_report_absent(self, seeded_root):
        """radar_report.json absent (but state present) → available:False + honest note,
        and the opportunity queue still surfaces from state."""
        r = marketing.radar(seeded_root)
        assert r["ok"] is True
        assert r["available"] is False
        assert r.get("note") is not None
        assert "nightly" in r["note"].lower() or "hasn't" in r["note"].lower()
        assert r["feeds"] == []
        assert r["surplus"] == []
        assert r["queue"] is None
        # Even without the report, the live opportunity queue is exposed.
        assert r["opportunities"] is not None
        assert r["opportunities"]["open"] == 1

    def test_radar_fail_soft_empty_root(self, empty_root):
        """No files at all → available:False, everything empty, never raises."""
        r = marketing.radar(empty_root)
        _assert_fail_soft(r, "radar")
        assert r["available"] is False
        assert r["surplus"] == []
        assert r["feeds"] == []
        assert r["opportunities"] is None
        assert r["universe_n"] is None

    def test_radar_tiers_without_report(self, tmp_path):
        """cashtag_tiers present but radar_report absent → available:False but the
        tier universe still comes through (fail-soft per-file)."""
        mkt_dir = tmp_path / "data" / "marketing"
        mkt_dir.mkdir(parents=True)
        (mkt_dir / "cashtag_tiers.json").write_text(
            json.dumps(MINIMAL_CASHTAG_TIERS, ensure_ascii=False, indent=2), encoding="utf-8",
        )
        r = marketing.radar(tmp_path)
        assert r["ok"] is True
        assert r["available"] is False
        assert r["universe_n"] == 9
        assert r["tiers"]["T1"] == ["NVDA", "TSLA", "AAPL"]


class TestOutboxBatchDecide:
    """decide_outbox_batch — bulk approve/hold from the admin."""

    def _seed(self, tmp_path, n=3):
        from engine.marketing.outbox import enqueue, make_item
        ids = []
        for i in range(n):
            item = make_item(
                account="flagship", kind="signal",
                text=f"Batch decide post number {i}.",
                as_of=_AS_OF_OB, provenance="content_studio", now=_FIXED_NOW_OB,
            )
            enqueue(item, root=tmp_path, max_per_account_day=8)
            ids.append(item["id"])
        return ids

    def test_batch_approve_all(self, tmp_path):
        ids = self._seed(tmp_path)
        res = marketing.decide_outbox_batch(ids, "approve", root=tmp_path)
        assert res["decided"] == 3
        assert all(res["results"][i] for i in ids)
        from engine.marketing.outbox import latest_decisions
        decs = latest_decisions(tmp_path)
        assert all(decs[i]["decision"] == "approve" for i in ids)

    def test_batch_unknown_id_does_not_block_rest(self, tmp_path):
        ids = self._seed(tmp_path, n=2)
        res = marketing.decide_outbox_batch(
            [ids[0], "ob-2026-07-19-nonexist00", ids[1]], "hold", root=tmp_path)
        assert res["decided"] == 2
        assert res["results"][ids[0]] is True
        assert res["results"]["ob-2026-07-19-nonexist00"] is False
        assert res["results"][ids[1]] is True

    def test_batch_invalid_decision_all_false(self, tmp_path):
        ids = self._seed(tmp_path, n=2)
        res = marketing.decide_outbox_batch(ids, "publish", root=tmp_path)
        assert res["decided"] == 0


class TestOutboxActivityPayload:
    """The panel surfaces pipeline activity + per-item attempts."""

    def test_activity_surfaced_newest_first(self, tmp_path):
        from engine.marketing.outbox import _append_activity
        _append_activity(tmp_path, {"at": "2026-07-19T01:00:00Z", "lane": "emit"})
        _append_activity(tmp_path, {"at": "2026-07-19T02:00:00Z", "lane": "actuator_dry_run"})
        r = marketing.outbox(tmp_path)
        assert [a["lane"] for a in r["activity"]] == ["actuator_dry_run", "emit"]

    def test_items_carry_attempts(self, tmp_path):
        from engine.marketing.outbox import enqueue, make_item, transition
        item = make_item(
            account="flagship", kind="signal", text="Attempts surfaced post.",
            as_of=_AS_OF_OB, provenance="content_studio", now=_FIXED_NOW_OB,
        )
        enqueue(item, root=tmp_path)
        transition(item["id"], "approved", actor="t", root=tmp_path)
        transition(item["id"], "failed", actor="t", root=tmp_path)
        r = marketing.outbox(tmp_path)
        it = r["accounts"][0]["items"][0]
        assert it["attempts"] == 1
        assert it["status"] == "failed"


# ---------------------------------------------------------------------------
# Operator console additions (PR 2/3) — pipeline block, sentinel/allow,
# accounts/toggle, sentinel `passed` pass-through
# ---------------------------------------------------------------------------

class TestPipelineBlock:
    def test_overview_pipeline_present_on_empty_root(self, empty_root):
        r = marketing.overview(empty_root)
        assert r["ok"] is True
        assert "pipeline" in r, "overview must always carry a pipeline block"
        pl = r["pipeline"]
        # every stage present as a dict, fail-soft (not None) on a bare root
        for stage in ("plan", "gate", "outbox", "publisher", "receipts"):
            assert stage in pl, f"pipeline missing {stage}"
        assert pl["plan"]["present"] is False
        assert pl["gate"]["present"] is False
        assert pl["outbox"]["present"] is False
        # publisher stage is computable from config/env even with no files
        assert pl["publisher"]["armed"] is False
        assert isinstance(pl["publisher"]["slots_utc"], list)

    def test_overview_pipeline_reads_content_plan(self, seeded_content_root):
        r = marketing.overview(seeded_content_root)
        pl = r["pipeline"]
        assert pl["plan"]["present"] is True
        assert pl["plan"]["items"] == 3          # summary.total_posts in fixture
        # 2026-07-18 as_of is before "today" → stale by the date-compare fallback
        assert pl["plan"]["stale"] is True

    def test_pipeline_next_slot_is_iso_or_none(self, empty_root):
        pl = marketing.overview(empty_root)["pipeline"]
        nxt = pl["publisher"]["next_slot_utc"]
        # either a Z-suffixed ISO string or None — never a bare magic string
        assert nxt is None or (isinstance(nxt, str) and nxt.endswith("Z"))


class TestSentinelAllow:
    def test_appends_valid_exception_row(self, tmp_path):
        r = marketing.sentinel_allow("ob-2026-07-24-abc123", "dup was my own post", root=tmp_path)
        assert r["ok"] is True
        p = tmp_path / "data" / "marketing" / "sentinel_exceptions.jsonl"
        assert p.exists()
        rows = [json.loads(ln) for ln in p.read_text().splitlines() if ln.strip()]
        assert len(rows) == 1
        row = rows[0]
        assert row["item_id"] == "ob-2026-07-24-abc123"
        assert row["allow"] is True
        assert row["reason"] == "dup was my own post"
        assert row["actor"] == "operator"
        assert "at" in row and row["at"].endswith("Z")

    def test_appends_are_additive(self, tmp_path):
        marketing.sentinel_allow("ob-1", "reason one", root=tmp_path)
        marketing.sentinel_allow("ob-2", "reason two", root=tmp_path)
        p = tmp_path / "data" / "marketing" / "sentinel_exceptions.jsonl"
        rows = [json.loads(ln) for ln in p.read_text().splitlines() if ln.strip()]
        assert [r["item_id"] for r in rows] == ["ob-1", "ob-2"]

    def test_rejects_empty_reason(self, tmp_path):
        r = marketing.sentinel_allow("ob-x", "   ", root=tmp_path)
        assert r["ok"] is False
        assert "reason" in r["error"].lower()
        # nothing written
        assert not (tmp_path / "data" / "marketing" / "sentinel_exceptions.jsonl").exists()

    def test_rejects_empty_item_id(self, tmp_path):
        r = marketing.sentinel_allow("", "a reason", root=tmp_path)
        assert r["ok"] is False
        assert "item_id" in r["error"].lower()


class TestAccountsToggle:
    def test_merge_writes_overrides_atomically(self, tmp_path):
        r1 = marketing.accounts_toggle("flagship", False, note="pausing", root=tmp_path, push=False)
        assert r1["ok"] is True
        assert r1["pushed"] is False
        p = tmp_path / "data" / "marketing" / "account_overrides.json"
        obj = json.loads(p.read_text())
        assert obj["flagship"]["enabled"] is False
        assert obj["flagship"]["note"] == "pausing"
        assert obj["flagship"]["at"].endswith("Z")
        # a second toggle MERGES (does not clobber the first)
        marketing.accounts_toggle("research_a", True, root=tmp_path, push=False)
        obj2 = json.loads(p.read_text())
        assert set(obj2.keys()) == {"flagship", "research_a"}
        assert obj2["research_a"]["enabled"] is True
        # no stray temp file left behind
        assert not (p.with_suffix(p.suffix + ".tmp")).exists()

    def test_toggle_flip_updates_same_key(self, tmp_path):
        marketing.accounts_toggle("flagship", False, root=tmp_path, push=False)
        marketing.accounts_toggle("flagship", True, root=tmp_path, push=False)
        obj = json.loads((tmp_path / "data" / "marketing" / "account_overrides.json").read_text())
        assert obj["flagship"]["enabled"] is True

    def test_rejects_empty_account_id(self, tmp_path):
        r = marketing.accounts_toggle("  ", True, root=tmp_path, push=False)
        assert r["ok"] is False
        assert "account_id" in r["error"].lower()

    def test_rejects_unknown_account_when_config_present(self, tmp_path):
        cfg = tmp_path / "config"
        cfg.mkdir(parents=True)
        (cfg / "marketing.yml").write_text(
            "desk_network:\n  accounts:\n    - id: flagship\n    - id: research_a\n",
            encoding="utf-8")
        r = marketing.accounts_toggle("not_a_desk", True, root=tmp_path, push=False)
        assert r["ok"] is False
        assert "unknown account" in r["error"]
        # known id still accepted against the same config
        r2 = marketing.accounts_toggle("flagship", False, root=tmp_path, push=False)
        assert r2["ok"] is True

    def test_deployed_mode_commits_override_via_github_api(self, tmp_path, monkeypatch):
        # Deployed VPS admin has no git auth: the toggle must PERSIST via the
        # GitHub Contents API rather than refuse (the old dead-end behaviour).
        monkeypatch.setenv("ADMIN_DEPLOYED", "1")
        from admin import github_api
        captured: dict = {}
        monkeypatch.setattr(github_api, "get_file", lambda rel, ref="main": {
            "ok": True, "content": '{"receipts": {"enabled": false}}', "sha": "s0"})

        def fake_put(rel, content, msg, sha=None, branch="main"):
            captured.update(rel=rel, content=content, sha=sha, msg=msg)
            return {"ok": True, "commit_sha": "c0ffee"}
        monkeypatch.setattr(github_api, "put_file", fake_put)

        r = marketing.accounts_toggle("theme_desk", False, root=tmp_path)
        assert r["ok"] is True
        assert r["via"] == "github_api" and r["pushed"] is True
        assert r["commit_sha"] == "c0ffee"
        # read-modify-write on the ON-MAIN copy: preserves receipts, adds theme_desk
        merged = json.loads(captured["content"])
        assert merged["receipts"] == {"enabled": False}
        assert merged["theme_desk"]["enabled"] is False
        assert captured["sha"] == "s0"                    # updates existing file
        assert "data/marketing/account_overrides.json" in captured["rel"]
        # nothing written to the local (VPS) checkout
        assert not (tmp_path / "data" / "marketing" / "account_overrides.json").exists()

    def test_deployed_mode_surfaces_api_commit_error(self, tmp_path, monkeypatch):
        monkeypatch.setenv("ADMIN_DEPLOYED", "1")
        from admin import github_api
        monkeypatch.setattr(github_api, "get_file",
                            lambda rel, ref="main": {"ok": True, "content": None, "sha": None})
        monkeypatch.setattr(github_api, "put_file",
                            lambda *a, **k: {"ok": False, "error": "HTTP 403 — needs Contents: write"})
        r = marketing.accounts_toggle("flagship", False, root=tmp_path)
        assert r["ok"] is False
        assert "commit failed" in r["error"].lower() and "403" in r["error"]

    def test_note_and_reason_length_capped(self, tmp_path):
        marketing.accounts_toggle("flagship", True, note="n" * 2000,
                                  root=tmp_path, push=False)
        obj = json.loads((tmp_path / "data" / "marketing"
                          / "account_overrides.json").read_text())
        assert len(obj["flagship"]["note"]) == 500
        r = marketing.sentinel_allow("post-x-001", "r" * 2000, root=tmp_path)
        assert r["ok"] is True
        row = json.loads((tmp_path / "data" / "marketing"
                          / "sentinel_exceptions.jsonl").read_text().splitlines()[-1])
        assert len(row["reason"]) == 500

    def test_honest_pushed_false_when_git_push_refused(self, tmp_path, monkeypatch):
        """When the git commit+push step reports pushed:false (e.g. off a main
        tracking branch), the override is still saved and the result is honest."""
        from admin import gitops

        def fake_commit_paths(paths, message="", push=False, confirm=False):
            # mimic gitops refusing to push from a feature branch
            return {"ok": True, "committed": True, "pushed": False,
                    "warning": "committed locally; refused to push (not on a main tracking branch)"}

        monkeypatch.setattr(gitops, "commit_paths", fake_commit_paths)
        r = marketing.accounts_toggle("flagship", False, root=tmp_path, push=True)
        assert r["ok"] is True
        assert r["pushed"] is False
        assert "not yet" in r["note"].lower() or "will not reach" in r["note"].lower()
        # the local write still happened
        p = tmp_path / "data" / "marketing" / "account_overrides.json"
        assert json.loads(p.read_text())["flagship"]["enabled"] is False

    def test_channels_passes_through_overrides(self, tmp_path):
        """channels() surfaces the override file so the UI toggle reflects state."""
        # seed state so channels() reaches the populated branch
        nw = tmp_path / "data" / "neuralweb"
        nw.mkdir(parents=True)
        (nw / "marketing_state.json").write_text(
            json.dumps(MINIMAL_STATE, ensure_ascii=False), encoding="utf-8")
        marketing.accounts_toggle("flagship", False, root=tmp_path, push=False)
        ch = marketing.channels(tmp_path)
        assert ch["ok"] is True
        assert "overrides" in ch
        assert ch["overrides"]["flagship"]["enabled"] is False
        assert "channels_set" in ch


class TestGitopsCommitPaths:
    def test_refuses_non_allowlisted_path(self):
        from admin import gitops
        r = gitops.commit_paths(["site/evil.html"], confirm=True)
        assert r["ok"] is False
        assert "allowlist" in r["error"].lower()

    def test_requires_confirm(self):
        from admin import gitops
        r = gitops.commit_paths(["config.yml"])
        assert r["ok"] is False
        assert "confirm" in r["error"].lower()

    def test_allowlisted_path_accepted(self, monkeypatch):
        """An allowlisted path passes the guard (no real git side-effect: the
        _git call is stubbed to report a clean tree → no-op)."""
        from admin import gitops
        monkeypatch.setattr(gitops, "_git", lambda *a, **k: (0, "", ""))
        r = gitops.commit_paths(["config.yml"], confirm=True)
        assert r["ok"] is True
        # clean tree → nothing to commit, but the path was accepted (not refused)
        assert "allowlist" not in str(r.get("error", "")).lower()
        assert r.get("committed") in (False, None)


class _FakeGit:
    """A scripted stand-in for ``gitops._git``: records argv, answers by verb.

    Real git is never invoked. The whole point of commit_paths_synced is the
    CHOREOGRAPHY around a refused push (push -> fetch -> rebase -> push, abort on
    a conflict, and never a force), and choreography is asserted from the
    recorded call list — a temp repo would test git, not this function.

    ``pushes`` is the rc sequence; the LAST value repeats, so ``(1,)`` is "always
    refused" and ``(1, 0)`` is "refused once, then lands".
    """

    def __init__(self, *, branch="main", upstream="origin/main", dirty=True,
                 pushes=(0,), fetch_rc=0, rebase_rc=0, abort_rc=0):
        self.branch, self.upstream, self.dirty = branch, upstream, dirty
        self.pushes = list(pushes)
        self.fetch_rc, self.rebase_rc, self.abort_rc = fetch_rc, rebase_rc, abort_rc
        self.calls: list[tuple] = []

    def __call__(self, *args, timeout=20):
        self.calls.append(args)
        verb = args[0]
        if verb == "rev-parse":
            if "@{u}" in args:
                return (0, self.upstream, "") if self.upstream else (1, "", "no upstream")
            return 0, self.branch, ""
        if verb == "rev-list":
            return 0, "0\t1", ""
        if verb == "status":
            return (0, f" M {args[-1]}", "") if self.dirty else (0, "", "")
        if verb == "add":
            return 0, "", ""
        if verb == "commit":
            return 0, "[main 1a2b3c4] 3 files changed", ""
        if verb == "fetch":
            return ((0, "", "") if self.fetch_rc == 0
                    else (self.fetch_rc, "", "could not read from remote repository"))
        if verb == "rebase":
            if args[1:2] == ("--abort",):
                return (self.abort_rc, "",
                        "" if self.abort_rc == 0 else "no rebase in progress")
            if self.rebase_rc == 0:
                return 0, f"Successfully rebased onto {self.upstream}", ""
            return (self.rebase_rc, "",
                    "CONFLICT (content): Merge conflict in "
                    "data/marketing/outbox/items.jsonl")
        if verb == "push":
            rc = self.pushes.pop(0) if len(self.pushes) > 1 else self.pushes[0]
            return ((0, "", "abc..def  main -> main") if rc == 0
                    else (rc, "", "! [rejected] main -> main (fetch first)"))
        raise AssertionError(f"unscripted git call: {args}")

    @property
    def verbs(self) -> list[str]:
        """Compact call trace; a rebase keeps its first argument so the retry
        rebase and the abort do not read as the same step."""
        return [" ".join(c[:2]) if c[0] == "rebase" else c[0] for c in self.calls]

    @property
    def tokens(self) -> list[str]:
        return [t for c in self.calls for t in c]


class TestGitopsCommitPathsSynced:
    """The delivery primitive behind the Intelligence Desk approve click.

    ``commit_paths`` fires ONE push, and on this repo that is not enough: the
    press wire commits every few minutes, so a push racing it is refused about as
    often as it lands, and a refused push strands the operator's queued item on
    the VPS disk where no publisher will ever read it.
    """

    OUTBOX = ["data/marketing/outbox/items.jsonl",
              "data/marketing/outbox/status_ledger.jsonl",
              "data/marketing/outbox/activity.jsonl"]

    def test_the_three_outbox_ledgers_are_allowlisted(self):
        from admin import gitops
        assert set(self.OUTBOX) <= set(gitops._ALLOWED_PATHS)
        # Review N6: the approve path commits ONLY the file its enqueue wrote.
        # `outbox.enqueue` appends items.jsonl alone, and a wider scoped commit
        # would sweep other lanes' dirt on the status/activity ledgers of a
        # shared checkout onto main. The allowlist keeps all three (harmless);
        # the delivery tuple must not.
        assert set(marketing._INTEL_OUTBOX_LEDGERS) == {
            "data/marketing/outbox/items.jsonl"}

    def test_requires_confirm_and_shells_out_to_nothing_without_it(self, monkeypatch):
        from admin import gitops
        fake = _FakeGit()
        monkeypatch.setattr(gitops, "_git", fake)
        r = gitops.commit_paths_synced(self.OUTBOX)
        assert r["ok"] is False and "confirm" in r["error"].lower()
        assert fake.calls == []

    def test_refuses_a_non_allowlisted_path_before_touching_git(self, monkeypatch):
        from admin import gitops
        fake = _FakeGit()
        monkeypatch.setattr(gitops, "_git", fake)
        r = gitops.commit_paths_synced(["site/evil.html"], confirm=True)
        assert r["ok"] is False and "allowlist" in r["error"].lower()
        # One bad path poisons the whole set: committing "the good ones anyway"
        # would let an unreviewed file ride a live-main push.
        r = gitops.commit_paths_synced([*self.OUTBOX, "site/evil.html"],
                                       confirm=True)
        assert r["ok"] is False and "allowlist" in r["error"].lower()
        assert fake.calls == []

    def test_a_refused_push_is_rebased_and_retried_until_it_lands(self, monkeypatch):
        from admin import gitops
        fake = _FakeGit(pushes=(1, 0))
        monkeypatch.setattr(gitops, "_git", fake)
        r = gitops.commit_paths_synced(
            self.OUTBOX, message="admin: intelligence desk approve post-x-1",
            confirm=True)
        assert r["ok"] is True and r["committed"] is True and r["pushed"] is True
        assert r["attempts"] == 2
        # the choreography, in order
        assert ["push", "fetch", "rebase origin/main", "push"] == [
            v for v in fake.verbs if v.split()[0] in ("push", "fetch", "rebase")]
        # the commit is SCOPED to the three ledgers and carries the caller's message
        assert ("commit", "-m", "admin: intelligence desk approve post-x-1",
                "--", *self.OUTBOX) in fake.calls

    def test_a_conflicted_rebase_aborts_and_says_so(self, monkeypatch):
        """A conflict is not a race to retry through. Leaving the checkout
        mid-rebase would wedge every later admin write AND the VPS's own pull."""
        from admin import gitops
        fake = _FakeGit(pushes=(1,), rebase_rc=1)
        monkeypatch.setattr(gitops, "_git", fake)
        r = gitops.commit_paths_synced(self.OUTBOX, confirm=True, attempts=3)
        assert r["ok"] is False
        assert r["committed"] is True and r["pushed"] is False
        assert "conflicted" in r["error"] and "aborted" in r["error"]
        assert ("rebase", "--abort") in fake.calls
        # and it stops: no blind re-push into a conflict it could not resolve
        assert fake.verbs.count("push") == 1

    def test_a_rebase_that_never_started_is_not_called_a_conflict(self, monkeypatch):
        """A failing abort means there was no rebase to abort — git REFUSED to
        start one, and on the VPS a dirty working tree is the everyday cause.
        Reporting that as a conflict sends the operator hunting for a merge
        conflict that never existed, and claiming a clean rollback is worse."""
        from admin import gitops
        fake = _FakeGit(pushes=(1,), rebase_rc=1, abort_rc=1)
        monkeypatch.setattr(gitops, "_git", fake)
        r = gitops.commit_paths_synced(self.OUTBOX, confirm=True)
        assert r["ok"] is False and r["committed"] is True
        assert "abort did not succeed" in r["error"], r["error"]
        assert "never started" in r["error"]
        assert "back as it was" not in r["error"]

    def test_exhausted_attempts_is_committed_only_not_a_failure(self, monkeypatch):
        """The commit is real. Union-merge ledgers mean it rides the next
        successful sync cleanly, so this reports ok:True with a warning rather
        than an error the caller would surface as 'your click did nothing'."""
        from admin import gitops
        fake = _FakeGit(pushes=(1,))
        monkeypatch.setattr(gitops, "_git", fake)
        r = gitops.commit_paths_synced(self.OUTBOX, confirm=True, attempts=3)
        assert r["ok"] is True
        assert r["committed"] is True and r["pushed"] is False
        assert r["attempts"] == 3
        assert "committed locally" in r["warning"]
        assert "3 push attempt" in r["warning"]
        assert fake.verbs.count("push") == 3
        # no pointless catch-up after the final push
        assert fake.verbs.count("fetch") == 2
        assert fake.verbs.count("rebase origin/main") == 2

    def test_a_failed_fetch_stops_the_loop_and_keeps_the_commit(self, monkeypatch):
        """It must blame the step that actually failed. Reporting an unreachable
        remote as 'push did not land in 3 attempts' names the wrong command and
        claims two retries that never ran."""
        from admin import gitops
        fake = _FakeGit(pushes=(1,), fetch_rc=1)
        monkeypatch.setattr(gitops, "_git", fake)
        r = gitops.commit_paths_synced(self.OUTBOX, confirm=True, attempts=3)
        assert r["ok"] is True and r["committed"] is True and r["pushed"] is False
        assert "fetch" in r["warning"]
        assert "1 push attempt" in r["warning"]
        assert r["attempts"] == 1
        assert fake.verbs.count("push") == 1
        assert "rebase origin/main" not in fake.verbs

    def test_a_dev_checkout_commits_and_never_pushes(self, monkeypatch):
        """can_push_live stays the outer guard: a feature branch (this worktree,
        for one) must never push admin state at main."""
        from admin import gitops
        fake = _FakeGit(branch="claude/news-intelligence-upgrade",
                        upstream="origin/claude/news-intelligence-upgrade")
        monkeypatch.setattr(gitops, "_git", fake)
        r = gitops.commit_paths_synced(self.OUTBOX, confirm=True)
        assert r["ok"] is True and r["committed"] is True and r["pushed"] is False
        assert "not on a main tracking branch" in r["warning"]
        assert "push" not in fake.verbs and "fetch" not in fake.verbs

    def test_a_clean_tree_commits_nothing(self, monkeypatch):
        from admin import gitops
        fake = _FakeGit(dirty=False)
        monkeypatch.setattr(gitops, "_git", fake)
        r = gitops.commit_paths_synced(self.OUTBOX, confirm=True)
        assert r["ok"] is True and r["committed"] is False and r["pushed"] is False
        assert "commit" not in fake.verbs and "push" not in fake.verbs

    def test_it_never_force_pushes_and_never_resets(self, monkeypatch):
        """The standing law this function must not break: it may lose no one
        else's commit. Every branch of the retry loop is checked, not just the
        happy one."""
        from admin import gitops
        for kw in ({"pushes": (1, 0)}, {"pushes": (1,)},
                   {"pushes": (1,), "rebase_rc": 1}, {"pushes": (1,), "fetch_rc": 1}):
            fake = _FakeGit(**kw)
            monkeypatch.setattr(gitops, "_git", fake)
            gitops.commit_paths_synced(self.OUTBOX, confirm=True, attempts=3)
            assert "reset" not in fake.tokens, kw
            assert "--force" not in fake.tokens, kw
            assert "-f" not in fake.tokens, kw
            assert "--force-with-lease" not in fake.tokens, kw


class TestSentinelPassedPassthrough:
    _SENTINEL_WITH_PASSED = {
        "schema_version": 1,
        "as_of": "2026-07-24",
        "produced_at": "2026-07-24T04:00:00Z",
        "plan_status": "pass",
        "publish_enabled": False,
        "auditor_strict": True,
        "counts": {"items": 21, "passed": 12, "quarantined_policy": 2,
                   "quarantined_overflow": 7},
        "reasons_histogram": {"cadence_cap_daily": 7, "near_dup": 2},
        "passed": [
            {"id": "ob-2026-07-24-a", "account": "flagship", "type": "signal",
             "cashtag": "$TNDM", "headline": "Tandem momentum", "slot": "D1-AM",
             "display_time": "9:30 AM ET"},
            {"id": "ob-2026-07-24-b", "account": "research_a", "type": "education",
             "cashtag": None, "headline": "MACD without jargon", "slot": "D1-PM"},
        ],
        "quarantined": [
            {"id": "ob-q1", "class": "overflow", "account": "flagship"},
            {"id": "ob-q2", "account": "flagship", "reasons": ["near_dup:ob-x"]},
        ],
        "checks": {},
        "notes": [],
    }

    def _seed(self, tmp_path):
        d = tmp_path / "data" / "marketing"
        d.mkdir(parents=True)
        (d / "sentinel_report.json").write_text(
            json.dumps(self._SENTINEL_WITH_PASSED, ensure_ascii=False), encoding="utf-8")
        return tmp_path

    def test_passes_through_passed_list_when_present(self, tmp_path):
        self._seed(tmp_path)
        r = marketing.sentinel(tmp_path)
        assert r["ok"] is True
        assert isinstance(r["passed"], list)
        assert len(r["passed"]) == 2
        assert r["passed"][0]["cashtag"] == "$TNDM"
        assert r["passed"][0]["display_time"] == "9:30 AM ET"

    def test_passed_is_none_when_absent(self, tmp_path):
        # the older MINIMAL fixture has no `passed` — must not raise, must be None
        d = tmp_path / "data" / "marketing"
        d.mkdir(parents=True)
        (d / "sentinel_report.json").write_text(
            json.dumps({"plan_status": "pass", "publish_enabled": False,
                        "counts": {"items": 5}, "reasons_histogram": {},
                        "quarantined": []}, ensure_ascii=False), encoding="utf-8")
        r = marketing.sentinel(tmp_path)
        assert r["ok"] is True
        assert r["passed"] is None


# ---------------------------------------------------------------------------
# Publisher ARM toggle + Buffer token paste-box (kill-switch → repo VARIABLE).
# The kill-switch moved from a repo SECRET to a repo VARIABLE; arming/disarming
# writes MARKETING_PUBLISH_ENABLED = "1"/"0" via github_api; the Buffer token is
# set via `gh secret set BUFFER_TOKEN` on stdin and is NEVER echoed back.
# github_api + subprocess are stubbed — no network, no real `gh`.
# ---------------------------------------------------------------------------

class TestArmPublisher:
    def test_arm_sets_variable_to_1(self, monkeypatch):
        from admin import github_api
        calls = {}
        monkeypatch.setattr(github_api, "token", lambda: "gh_faketoken")

        def fake_set(name, value):
            calls["name"] = name
            calls["value"] = value
            return True

        monkeypatch.setattr(github_api, "set_repo_variable", fake_set)
        r = marketing.arm_publisher(True)
        assert r["ok"] is True
        assert r["enabled"] is True
        assert calls == {"name": "MARKETING_PUBLISH_ENABLED", "value": "1"}
        assert r["variable_value"] == "1"

    def test_disarm_sets_variable_to_0(self, monkeypatch):
        from admin import github_api
        calls = {}
        monkeypatch.setattr(github_api, "token", lambda: "gh_faketoken")
        monkeypatch.setattr(github_api, "set_repo_variable",
                            lambda n, v: calls.update(name=n, value=v) or True)
        r = marketing.arm_publisher(False)
        assert r["ok"] is True
        assert r["enabled"] is False
        assert calls["value"] == "0"

    def test_arm_fail_soft_without_token(self, monkeypatch):
        from admin import github_api
        monkeypatch.setattr(github_api, "token", lambda: None)
        # set_repo_variable must not even be reached; make it explode if it is
        monkeypatch.setattr(github_api, "set_repo_variable",
                            lambda *a, **k: (_ for _ in ()).throw(AssertionError("must not write")))
        r = marketing.arm_publisher(True)
        assert r["ok"] is False
        assert r["enabled"] is None
        assert "token" in r["error"].lower()

    def test_arm_fail_soft_when_write_fails(self, monkeypatch):
        from admin import github_api
        monkeypatch.setattr(github_api, "token", lambda: "gh_faketoken")
        monkeypatch.setattr(github_api, "set_repo_variable", lambda n, v: False)
        monkeypatch.setattr(github_api, "_last_set_variable_error",
                            "HTTP 403 — no Variables write", raising=False)
        r = marketing.arm_publisher(True)
        assert r["ok"] is False
        assert "403" in r["error"] or "Variables" in r["error"]


class TestArmState:
    def test_reads_variable_true_as_armed(self, monkeypatch):
        from admin import github_api
        monkeypatch.setattr(github_api, "available",
                            lambda: {"ok": True, "has_token": True})
        monkeypatch.setattr(github_api, "get_repo_variable", lambda n: "1")
        s = marketing.arm_state()
        assert s["enabled"] is True
        assert s["source"] == "github_variable"
        assert s["error"] is None

    def test_reads_variable_zero_as_disarmed(self, monkeypatch):
        from admin import github_api
        monkeypatch.setattr(github_api, "available",
                            lambda: {"ok": True, "has_token": True})
        monkeypatch.setattr(github_api, "get_repo_variable", lambda n: "0")
        s = marketing.arm_state()
        assert s["enabled"] is False
        assert s["source"] == "github_variable"

    def test_variable_not_set_404_is_null_dark(self, monkeypatch):
        from admin import github_api
        monkeypatch.setattr(github_api, "available",
                            lambda: {"ok": True, "has_token": True})
        # get_repo_variable returns None for a 404 (variable never created)
        monkeypatch.setattr(github_api, "get_repo_variable", lambda n: None)
        s = marketing.arm_state()
        assert s["enabled"] is None
        assert s["error"] is None
        assert "not set" in s["note"].lower()

    def test_api_unreachable_falls_back_to_env(self, monkeypatch):
        from admin import github_api
        monkeypatch.setattr(github_api, "available",
                            lambda: {"ok": False, "has_token": False})
        # env armed → fallback reports enabled True, but flags the source + error
        monkeypatch.setenv("MARKETING_PUBLISH_ENABLED", "1")
        s = marketing.arm_state()
        assert s["source"].startswith("local_env")
        assert s["error"] is not None
        assert s["enabled"] is True

    def test_never_raises_on_api_exception(self, monkeypatch):
        from admin import github_api

        def boom():
            raise RuntimeError("network down")

        monkeypatch.setattr(github_api, "available", boom)
        s = marketing.arm_state()
        assert s["enabled"] is None
        assert s["error"] is not None   # honest, not a crash


class TestSetBufferToken:
    def _stub_gh_ok(self, monkeypatch, captured):
        """Stub subprocess.run so `gh secret set` succeeds and the token is
        captured from STDIN (never argv)."""
        import subprocess

        class _Res:
            def __init__(self, rc=0, stdout="", stderr=""):
                self.returncode = rc
                self.stdout = stdout
                self.stderr = stderr

        def fake_run(argv, **kw):
            captured.setdefault("argv", []).append(list(argv))
            if argv[:3] == ["gh", "secret", "set"]:
                # the token MUST arrive on stdin (`input=`), NEVER in argv
                captured["stdin"] = kw.get("input")
                return _Res(0)
            if argv[:3] == ["gh", "secret", "list"]:
                return _Res(0, stdout="BUFFER_TOKEN\tUpdated 2026-07-23\n")
            return _Res(0)

        monkeypatch.setattr(subprocess, "run", fake_run)

    def test_sets_secret_via_stdin_not_argv(self, monkeypatch):
        from admin import settings
        monkeypatch.setattr(settings, "deployed", lambda: False)
        captured = {}
        self._stub_gh_ok(monkeypatch, captured)
        secret = "buffer_tok_ABC123_secret"
        r = marketing.set_buffer_token(secret)
        assert r["ok"] is True
        # token arrived on stdin
        assert captured["stdin"] == secret
        # token NEVER in any argv
        for argv in captured["argv"]:
            assert secret not in argv
            assert not any(secret in str(a) for a in argv)
        # token NEVER in the response
        assert secret not in json.dumps(r)
        # present-check reported truthfully
        assert r.get("token_present") is True

    def test_refuses_empty_token(self, monkeypatch):
        from admin import settings
        monkeypatch.setattr(settings, "deployed", lambda: False)
        import subprocess
        # subprocess must not be called at all for an empty token
        monkeypatch.setattr(subprocess, "run",
                            lambda *a, **k: (_ for _ in ()).throw(AssertionError("must not shell out")))
        r = marketing.set_buffer_token("   ")
        assert r["ok"] is False
        assert "empty" in r["error"].lower()

    def test_refused_in_deployed_mode(self, monkeypatch):
        from admin import settings
        monkeypatch.setattr(settings, "deployed", lambda: True)
        import subprocess
        monkeypatch.setattr(subprocess, "run",
                            lambda *a, **k: (_ for _ in ()).throw(AssertionError("no gh in deployed mode")))
        r = marketing.set_buffer_token("buffer_tok_XYZ")
        assert r["ok"] is False
        assert "deployed" in r["error"].lower()
        # honest fallback instruction present, token absent
        assert "Secrets" in r["error"]
        assert "buffer_tok_XYZ" not in json.dumps(r)

    def test_gh_missing_returns_honest_fallback(self, monkeypatch):
        from admin import settings
        monkeypatch.setattr(settings, "deployed", lambda: False)
        import subprocess

        def raise_fnf(*a, **k):
            raise FileNotFoundError("gh not found")

        monkeypatch.setattr(subprocess, "run", raise_fnf)
        r = marketing.set_buffer_token("buffer_tok_QQQ")
        assert r["ok"] is False
        assert "gh" in r["error"].lower()
        assert "buffer_tok_QQQ" not in json.dumps(r)

    def test_gh_nonzero_surfaces_stderr_without_token(self, monkeypatch):
        from admin import settings
        monkeypatch.setattr(settings, "deployed", lambda: False)
        import subprocess

        class _Res:
            returncode = 1
            stdout = ""
            stderr = "error: not authenticated; run gh auth login"

        monkeypatch.setattr(subprocess, "run", lambda *a, **k: _Res())
        r = marketing.set_buffer_token("buffer_tok_SEKRIT")
        assert r["ok"] is False
        assert "auth" in r["error"].lower()
        assert "buffer_tok_SEKRIT" not in json.dumps(r)


class TestPublisherArmStatePayload:
    def test_publisher_payload_carries_arm_state(self, monkeypatch, tmp_path):
        # API stubbed unreachable → arm_state falls back but publisher() still
        # returns ok:True with an arm_state block (fail-soft).
        from admin import github_api
        monkeypatch.setattr(github_api, "available",
                            lambda: {"ok": False, "has_token": False})
        r = marketing.publisher(root=tmp_path)
        assert r["ok"] is True
        assert "arm_state" in r
        assert r["arm_state"]["enabled"] in (True, False, None)
        assert "source" in r["arm_state"]

    def test_publisher_arm_state_survives_api_error(self, monkeypatch, tmp_path):
        from admin import github_api

        def boom():
            raise RuntimeError("api exploded")

        monkeypatch.setattr(github_api, "available", boom)
        r = marketing.publisher(root=tmp_path)
        assert r["ok"] is True
        assert r["arm_state"]["enabled"] is None
        assert r["arm_state"]["error"] is not None

    def test_pipeline_publisher_armed_uses_api_truth(self, monkeypatch, tmp_path):
        # variable "1" → pipeline publisher.kill_switch True and arm_state present
        from admin import github_api
        monkeypatch.setattr(github_api, "available",
                            lambda: {"ok": True, "has_token": True})
        monkeypatch.setattr(github_api, "get_repo_variable", lambda n: "1")
        pl = marketing.overview(tmp_path)["pipeline"]
        assert pl["publisher"]["kill_switch"] is True
        assert pl["publisher"]["arm_state"]["enabled"] is True


class TestPostNow:
    """BREAKING DISPATCH — admin.marketing.post_now(): the "Post now" button's
    server side. Dispatches marketing-publish.yml scoped to one outbox item.
    Every assertion here is about the GUARDS; the actual posting decisions live
    in the runner (tests/test_marketing_publisher_autoapprove.py)."""

    @staticmethod
    def _wire(monkeypatch, *, armed=True, dispatch=None):
        from admin import github_api
        monkeypatch.setattr(github_api, "token", lambda: "tkn")
        monkeypatch.setattr(marketing, "arm_state",
                            lambda: {"enabled": armed, "source": "github_variable",
                                     "error": None, "note": ""})
        calls: list[dict] = []

        def fake_dispatch(workflow="daily.yml", ref="main", inputs=None):
            calls.append({"workflow": workflow, "ref": ref, "inputs": inputs})
            return dispatch if dispatch is not None else {"ok": True}

        monkeypatch.setattr(github_api, "dispatch", fake_dispatch)
        return calls

    def test_dispatches_the_publisher_with_the_item_id(self, monkeypatch):
        calls = self._wire(monkeypatch)
        r = marketing.post_now("ob-2026-07-25-15098c35f1")
        assert r["ok"] is True and r["dispatched"] is True
        assert calls == [{
            "workflow": "marketing-publish.yml", "ref": "main",
            "inputs": {"post_now_item": "ob-2026-07-25-15098c35f1"},
        }]

    def test_accepts_a_short_comma_list(self, monkeypatch):
        calls = self._wire(monkeypatch)
        r = marketing.post_now(" ob-a , ob-b ")
        assert r["ok"] is True
        assert calls[0]["inputs"]["post_now_item"] == "ob-a,ob-b"

    def test_rejects_an_argparse_flag_shaped_id(self, monkeypatch):
        """The runner passes this value to argparse — a leading dash would be
        read as a FLAG, not an item id."""
        calls = self._wire(monkeypatch)
        r = marketing.post_now("--live")
        assert r["ok"] is False and "valid outbox item id" in r["error"]
        assert calls == []

    def test_rejects_empty_and_oversized_batches(self, monkeypatch):
        calls = self._wire(monkeypatch)
        assert marketing.post_now("")["ok"] is False
        assert marketing.post_now("a,b,c,d,e,f")["ok"] is False
        assert calls == []

    def test_refuses_while_the_publisher_is_disarmed(self, monkeypatch):
        """A dispatch with the kill-switch off dry-runs and posts nothing — say
        so instead of letting the operator watch an empty green run."""
        calls = self._wire(monkeypatch, armed=False)
        r = marketing.post_now("ob-x")
        assert r["ok"] is False and "DISARMED" in r["error"]
        assert calls == []

    def test_requires_a_github_token(self, monkeypatch):
        from admin import github_api
        self._wire(monkeypatch)
        monkeypatch.setattr(github_api, "token", lambda: "")
        r = marketing.post_now("ob-x")
        assert r["ok"] is False and "GH_TOKEN" in r["error"]

    def test_surfaces_a_dispatch_failure(self, monkeypatch):
        self._wire(monkeypatch, dispatch={"ok": False, "error": "HTTP 403 — Actions: write"})
        r = marketing.post_now("ob-x")
        assert r["ok"] is False and "403" in r["error"]


# ---------------------------------------------------------------------------
# Intelligence Desk approve flow (V2 wave B) — admin.marketing.intelligence_approve
#
# The operator click is the review gate, so these tests are about the GATES: what
# gets refused, what the refusal is called, and that a success writes exactly one
# canonical outbox item. Everything is tmp-rooted and monkeypatched; nothing here
# reaches the network, the live plane, or the real repo.
# ---------------------------------------------------------------------------

_INTEL_WIRE_TEXT = (
    "Regulators cleared the Aldon Systems takeover this morning after a nine "
    "month review, and the buyer now has until October to close. Reuters."
)

INTEL_SNAPSHOT = {
    "schema": "intelligence.desk/v1",
    "updated_at": "2026-07-29T14:05:00Z",
    "health": {"active_stories": 3, "draft_ready": 2},
    "stories": [
        {
            # Builder A's machine field present. Carries tickers, so the success
            # note must be honest about shipping without a chart.
            "id": "story-alpha",
            "stage": "confirmed",
            "lane": "wire",
            "event_class": "policy",
            "headline": "Regulator clears the Aldon Systems takeover",
            "tickers": ["ALD"],
            "content_routes": ["breaking"],
            "evidence": [
                {"event_id": "ev-1", "name": "Reuters",
                 "url": "https://example.com/reuters/aldon",
                 "published_at": "2026-07-29T13:50:00Z"},
                {"event_id": "ev-2", "name": "AP",
                 "url": "https://example.com/ap/aldon",
                 "published_at": "2026-07-29T13:58:00Z"},
            ],
            "drafts": [
                {"id": "draft-wire-1", "shape": "wire", "status": "review",
                 "text": _INTEL_WIRE_TEXT, "characters": len(_INTEL_WIRE_TEXT),
                 "requires_review": True,
                 "source_url": "https://example.com/reuters/aldon"},
                {"id": "draft-analysis-1", "shape": "analysis",
                 "status": "needs_edit",
                 "text": "Second look at the clearance and what it changes.",
                 "characters": 49, "requires_review": True,
                 "source_url": "https://example.com/reuters/aldon"},
            ],
        },
        {
            # event_class ABSENT (pre-Builder-A snapshot, or a story the
            # classifier could not label) and no tickers.
            "id": "story-beta",
            "stage": "developing",
            "lane": "wire",
            "headline": "Port strike talks resume in Rotterdam",
            "tickers": [],
            "drafts": [
                {"id": "draft-beta-1", "shape": "wire", "status": "review",
                 "text": ("Talks to end the Rotterdam port strike resumed on "
                          "Tuesday with a mediator in the room for the first "
                          "time since June. AP."),
                 "characters": 148, "requires_review": True,
                 "source_url": "https://example.com/ap/rotterdam"},
                {"id": "draft-beta-cheese", "shape": "wire", "status": "review",
                 # "guaranteed" is in copywriter._BANNED_VOCAB.
                 "text": ("Rotterdam talks resumed Tuesday and a deal is "
                          "guaranteed before the weekend, say the mediators "
                          "who have been in the room since June."),
                 "characters": 141, "requires_review": True,
                 "source_url": "https://example.com/ap/rotterdam"},
            ],
        },
        {
            # Too thin for the value gate's gift test (< 6 body words).
            "id": "story-thin",
            "stage": "developing",
            "lane": "wire",
            "headline": "Aldon cleared",
            "tickers": [],
            "drafts": [
                {"id": "draft-thin-1", "shape": "wire", "status": "review",
                 "text": "Aldon cleared.", "characters": 14,
                 "requires_review": True, "source_url": ""},
            ],
        },
    ],
}

_INTEL_CFG = """\
sentinel:
  max_posts_per_account_per_day: -1
wire_routing:
  default: flagship
  classes:
    policy: mastermind_news
"""


def _write_intel_root(tmp_path, snapshot=None, cfg: str = _INTEL_CFG):
    """A repo root carrying the desk snapshot + a minimal marketing config.

    The cap is set unlimited on purpose: these tests are about the approve
    gates, and a Sentinel default of 2/account/day would otherwise turn a later
    assertion into a cap refusal that looks like a bug in this lane.
    """
    p = tmp_path / "data" / "marketing" / "press"
    p.mkdir(parents=True, exist_ok=True)
    (p / "intelligence.json").write_text(
        json.dumps(snapshot if snapshot is not None else INTEL_SNAPSHOT),
        encoding="utf-8")
    (tmp_path / "config").mkdir(parents=True, exist_ok=True)
    (tmp_path / "config" / "marketing.yml").write_text(cfg, encoding="utf-8")
    return tmp_path


def _intel_items(root) -> list[dict]:
    p = pathlib.Path(root) / "data" / "marketing" / "outbox" / "items.jsonl"
    if not p.exists():
        return []
    return [json.loads(ln) for ln in p.read_text(encoding="utf-8").splitlines()
            if ln.strip()]


@pytest.fixture()
def intel_root(tmp_path):
    return _write_intel_root(tmp_path)


@pytest.fixture(autouse=True)
def _isolate_dark_route_warnings(monkeypatch):
    """Give every test in this file its OWN dark-route warning set.

    ``wire_routing._WARNED_DARK`` is a once-per-PROCESS set: the first route onto
    a dark desk prints the ``::warning wire-routing-dark`` annotation and every
    later one is silent, so the Actions summary is not buried. The approve tests
    below route ``policy`` onto the (deliberately dark) ``mastermind_news`` desk,
    which SPENDS that one warning — and
    ``tests/test_marketing_cadence_spine.py::test_routing_to_a_dark_account_falls_back_and_says_so``
    then finds nothing on stdout and fails, but only when the two files share a
    process (they do: the pack runs them together). The bug is cross-suite state,
    not either test, so it is fixed by isolation rather than by ordering.

    Module-wide rather than per-class on purpose: any future admin test that
    routes would re-open the same hole. ImportError is a no-op (packs that
    install minimal deps have no engine to isolate); a RENAMED attribute is not —
    monkeypatch raises, loudly, instead of quietly creating a decoy set that
    isolates nothing.
    """
    try:
        from engine.marketing import wire_routing
    except ImportError:
        return
    monkeypatch.setattr(wire_routing, "_WARNED_DARK", set())


class TestIntelligenceApproveSuccess:
    def test_enqueues_exactly_one_canonical_item(self, intel_root):
        r = marketing.intelligence_approve("story-alpha", "draft-wire-1",
                                           root=intel_root)
        assert r["ok"] is True, r
        items = _intel_items(intel_root)
        assert len(items) == 1
        it = items[0]
        assert it["schema"] == "marketing.outbox/v1"
        assert it["kind"] == "breaking"
        assert it["provenance"] == "intelligence_desk"
        assert it["status"] == "queued"
        assert it["scheduled_at"] == "immediate"
        assert it["priority"] == 1
        assert it["media"] == []
        assert it["id"] == r["item_id"]
        assert it["account"] == r["account"]
        # The text is the DESK's, not anything a browser could have sent.
        assert it["text"] == _INTEL_WIRE_TEXT

    def test_source_carries_the_backlink_and_the_lock_key(self, intel_root):
        marketing.intelligence_approve("story-alpha", "draft-wire-1",
                                       root=intel_root)
        src = _intel_items(intel_root)[0]["source"]
        assert src["lane"] == "intelligence_desk"
        assert src["story_id"] == "story-alpha"
        assert src["draft_id"] == "draft-wire-1"
        assert src["url"] == "https://example.com/reuters/aldon"
        # Without a story_key on the item the one-owner lock has nothing to read
        # back, and the next desk to draw this story would be waved through.
        assert src["story_key"]
        # Every emission carries its Gift-Grip-Proof verdict (charter §0).
        assert "value_gate" in src

    def test_success_note_is_honest_about_the_missing_chart(self, intel_root):
        """`breaking` sits outside the publisher's _CHART_BEARING_KINDS, so a
        ticker-bearing item on this lane ships bare instead of deferring. The
        operator is told, not left to assume the every-ticker-post-is-charted
        law covers this queue."""
        r = marketing.intelligence_approve("story-alpha", "draft-wire-1",
                                           root=intel_root)
        assert "text only" in r["note"]
        assert "nothing posts now" in r["note"].lower()
        # A story with no tickers gets the plain note, no chart sentence.
        r2 = marketing.intelligence_approve("story-beta", "draft-beta-1",
                                            root=intel_root)
        assert r2["ok"] is True
        assert "text only" not in r2["note"]

    def test_event_class_is_routed_through_wire_routing(self, intel_root,
                                                        monkeypatch):
        from engine.marketing import wire_routing as wr
        seen: dict = {}

        def fake_route(event_class, *, cfg, root=None):
            seen["event_class"] = event_class
            return "mastermind_news"

        monkeypatch.setattr(wr, "route", fake_route)
        r = marketing.intelligence_approve("story-alpha", "draft-wire-1",
                                           root=intel_root)
        assert r["ok"] is True
        assert seen["event_class"] == "policy"
        assert r["account"] == "mastermind_news"
        assert _intel_items(intel_root)[0]["account"] == "mastermind_news"

    def test_story_without_event_class_uses_the_fallback_account(self, intel_root):
        """Builder A's machine field may be absent. An unlabelled story routes
        to wire_routing's own default, never to the literal class "none"."""
        r = marketing.intelligence_approve("story-beta", "draft-beta-1",
                                           root=intel_root)
        assert r["ok"] is True
        assert r["account"] == "flagship"


class TestIntelligenceApproveRefusals:
    def test_needs_edit_draft_is_refused(self, intel_root):
        r = marketing.intelligence_approve("story-alpha", "draft-analysis-1",
                                           root=intel_root)
        assert r["ok"] is False
        assert r["reason"] == "not_reviewable"
        assert "needs_edit" in r["detail"]
        assert _intel_items(intel_root) == []

    def test_banned_language_is_refused_with_the_violation_list(self, intel_root):
        r = marketing.intelligence_approve("story-beta", "draft-beta-cheese",
                                           root=intel_root)
        assert r["ok"] is False
        assert r["reason"] == "banned_language"
        assert any("guaranteed" in v for v in r["violations"])
        assert _intel_items(intel_root) == []

    def test_unknown_story_is_refused(self, intel_root):
        r = marketing.intelligence_approve("story-nope", "draft-wire-1",
                                           root=intel_root)
        assert r["ok"] is False and r["reason"] == "story_not_found"
        assert _intel_items(intel_root) == []

    def test_unknown_draft_is_refused(self, intel_root):
        r = marketing.intelligence_approve("story-alpha", "draft-nope",
                                           root=intel_root)
        assert r["ok"] is False and r["reason"] == "draft_not_found"
        assert _intel_items(intel_root) == []

    def test_missing_ids_are_refused(self, intel_root):
        assert marketing.intelligence_approve("", "draft-wire-1",
                                              root=intel_root)["reason"] == "bad_request"
        assert marketing.intelligence_approve("story-alpha", None,
                                              root=intel_root)["reason"] == "bad_request"
        assert _intel_items(intel_root) == []

    def test_absent_snapshot_is_refused(self, tmp_path):
        r = marketing.intelligence_approve("story-alpha", "draft-wire-1",
                                           root=tmp_path)
        assert r["ok"] is False and r["reason"] == "no_snapshot"

    def test_second_click_is_a_duplicate_not_a_second_post(self, intel_root):
        """Outbox id-dedup makes a double-click safe. It must SAY so — and it
        must not be a dead end (review N5): the row exists, so ok stays True
        with reason "duplicate", nothing is queued twice, and on a deployed
        host delivery would be re-attempted (root-pinned calls attempt none)."""
        first = marketing.intelligence_approve("story-alpha", "draft-wire-1",
                                               root=intel_root)
        assert first["ok"] is True
        second = marketing.intelligence_approve("story-alpha", "draft-wire-1",
                                                root=intel_root)
        assert second["ok"] is True
        assert second["reason"] == "duplicate"
        assert "queued nothing twice" in second["note"]
        assert "delivered" not in second  # root-pinned: no delivery attempted
        assert len(_intel_items(intel_root)) == 1

    def test_story_owned_by_another_desk_is_refused(self, intel_root):
        """One conversation, one owner. The refusal names the holder so the
        operator knows which desk to look at rather than just being blocked."""
        from datetime import datetime, timedelta, timezone

        from engine.marketing import story_lock as sl

        now = datetime(2026, 7, 29, 14, 30, tzinfo=timezone.utc)
        key = sl.story_key(cluster_key="story-alpha", event_id="draft-wire-1",
                           headline="Regulator clears the Aldon Systems takeover")
        prior = {
            "schema": "marketing.outbox/v1",
            "id": "ob-2026-07-29-priorabc1",
            "as_of": "2026-07-29",
            "account": "mastermind_news",
            "kind": "breaking",
            "text": "Rotterdam mediators return to the table on Tuesday.",
            "media": [], "scheduled_at": "immediate", "slot": None,
            "priority": 1, "provenance": "press_lane",
            "source": {"lane": "press", "story_key": key},
            "status": "queued",
            "created_at": (now - timedelta(hours=1)).strftime("%Y-%m-%dT%H:%M:%SZ"),
        }
        out = intel_root / "data" / "marketing" / "outbox"
        out.mkdir(parents=True, exist_ok=True)
        (out / "items.jsonl").write_text(json.dumps(prior) + "\n", encoding="utf-8")

        r = marketing.intelligence_approve("story-alpha", "draft-wire-1",
                                           root=intel_root, now=now)
        assert r["ok"] is False
        assert r["reason"] == "story_locked"
        assert r["owner"] == "mastermind_news"
        assert len(_intel_items(intel_root)) == 1  # nothing appended

    def test_armed_value_gate_refuses_a_thin_draft(self, tmp_path):
        """value_gate.enforce ships false (record-only). When an operator arms
        it, an abstention must STOP this lane, not just be stamped."""
        root = _write_intel_root(
            tmp_path,
            cfg=_INTEL_CFG + "value_gate:\n  enforce: true\n")
        r = marketing.intelligence_approve("story-thin", "draft-thin-1", root=root)
        assert r["ok"] is False
        assert r["reason"] == "value_gate"
        assert r["violations"]
        assert _intel_items(root) == []
        # Record-only (the shipped default) lets the same draft through.
        root2 = _write_intel_root(tmp_path / "recordonly")
        r2 = marketing.intelligence_approve("story-thin", "draft-thin-1", root=root2)
        assert r2["ok"] is True

    def test_a_gate_that_cannot_run_refuses(self, intel_root, monkeypatch):
        """Publish-adjacent polarity: the display panels above fail OPEN, this
        path fails CLOSED. A language screen that raises must not be read as a
        clean screen."""
        from engine.marketing import copywriter

        def boom(_text):
            raise RuntimeError("lexicon unreadable")

        monkeypatch.setattr(copywriter, "banned_language", boom)
        r = marketing.intelligence_approve("story-alpha", "draft-wire-1",
                                           root=intel_root)
        assert r["ok"] is False
        assert r["reason"] == "gate_unavailable"
        assert "lexicon unreadable" in r["detail"]
        assert _intel_items(intel_root) == []


class TestIntelligenceApproveReadsTheServerSideSnapshot:
    def test_a_pinned_root_never_reads_the_host_live_plane(self, intel_root,
                                                           tmp_path, monkeypatch):
        """content() and this path share _intelligence_snapshot. A seeded/test
        root must resolve the fixture tree only, or an approval on a dev box
        could act on the production desk."""
        live = tmp_path / "live-intelligence.json"
        live.write_text(json.dumps({
            "schema": "intelligence.desk/v1",
            "updated_at": "2026-07-29T14:00:00Z",
            "health": {},
            "stories": [{"id": "live-only-story", "headline": "Live plane story",
                         "drafts": [{"id": "live-draft", "status": "review",
                                     "text": "Live plane copy that must not post.",
                                     "source_url": ""}]}],
        }), encoding="utf-8")
        monkeypatch.setattr(marketing, "_INTELLIGENCE_LIVE", live)
        r = marketing.intelligence_approve("live-only-story", "live-draft",
                                           root=intel_root)
        assert r["ok"] is False and r["reason"] == "story_not_found"
        assert _intel_items(intel_root) == []

    def test_content_panel_still_serves_the_desk(self, intel_root):
        """Regression on the shared reader: content() kept its payload shape
        when the snapshot read was lifted into _intelligence_snapshot."""
        r = marketing.content(intel_root)
        assert r["ok"] is True
        intel = r["intelligence"]
        assert intel["schema"] == "intelligence.desk/v1"
        assert [s["id"] for s in intel["stories"]] == [
            "story-alpha", "story-beta", "story-thin"]
        assert intel["health"]["draft_ready"] == 2


class TestIntelligenceApproveDelivery:
    """Queued is not delivered.

    The publisher runs in GitHub Actions off the git-tracked outbox ON MAIN; the
    admin writes to the VPS checkout. Before this step the approve click wrote a
    row that looked queued in the panel forever and was read by nobody. Delivery
    is therefore attempted on every real approval, REPORTED honestly, and never
    allowed to un-queue the item it failed to deliver.
    """

    @pytest.fixture()
    def deployed_root(self, intel_root, monkeypatch):
        """The deployed shape — root=None — aimed at the fixture tree.

        root=None is what the HTTP route passes, and it is the ONLY shape that
        touches git, so it cannot be tested by passing a root. The live-plane
        snapshot path is stubbed to a nonexistent file so a host that happens to
        have one cannot leak into the fixture.
        """
        monkeypatch.setattr(marketing, "_default_root", lambda: intel_root)
        monkeypatch.setattr(marketing, "_INTELLIGENCE_LIVE",
                            intel_root / "no-live-plane" / "intelligence.json")
        return intel_root

    @staticmethod
    def _stub_delivery(monkeypatch, result):
        """Stub the N6 delivery primitive: plain ``commit_paths`` (ONE push, no
        rebase — this branch may run on a checkout other agents occupy)."""
        from admin import gitops
        seen: dict = {}

        def fake(paths, message="", push=False, confirm=False):
            seen.update(paths=list(paths), message=message, confirm=confirm,
                        push=push)
            if isinstance(result, Exception):
                raise result
            return result

        monkeypatch.setattr(gitops, "commit_paths", fake)
        return seen

    # ---- the dev/test shape: git is never in the picture --------------------

    def test_a_root_pinned_approve_never_reaches_git(self, intel_root, monkeypatch):
        """A pinned root is a scratch tree git knows nothing about. Committing
        from one would either fail noisily or, worse, commit the REAL repo's
        working tree from under whatever else is running in it."""
        from admin import gitops
        called: list = []
        for name in ("commit_paths_synced", "commit_paths", "commit", "_git"):
            monkeypatch.setattr(
                gitops, name,
                lambda *a, _n=name, **kw: called.append(_n) or {"ok": True})
        r = marketing.intelligence_approve("story-alpha", "draft-wire-1",
                                           root=intel_root)
        assert r["ok"] is True
        assert called == [], f"a root-pinned approve called git: {called}"
        # No `delivered` key at all: a delivery nobody attempted is not a failed
        # one, and reporting delivered:false here would read as a real refusal.
        assert "delivered" not in r

    # ---- the deployed shape --------------------------------------------------

    def test_a_landed_push_reports_delivered_true(self, deployed_root, monkeypatch):
        seen = self._stub_delivery(monkeypatch, {
            "ok": True, "committed": True, "pushed": True})
        r = marketing.intelligence_approve("story-alpha", "draft-wire-1")
        assert r["ok"] is True and r["delivered"] is True
        # ONLY items.jsonl (review N6 — enqueue writes nothing else), pushed,
        # confirmed, under the item's own message
        assert seen["paths"] == ["data/marketing/outbox/items.jsonl"]
        assert seen["message"] == f"admin: intelligence desk approve {r['item_id']}"
        assert seen["confirm"] is True and seen["push"] is True
        assert "publisher will see it" in r["note"]
        # the pre-existing note survives — delivery appends, it does not replace
        assert "nothing posts now" in r["note"].lower()

    def test_a_stranded_commit_is_delivered_false_and_keeps_the_item(
            self, deployed_root, monkeypatch):
        """A push refused by a racing press-wire commit is the routine outcome,
        and there is deliberately NO rebase retry (review N6: this branch can
        run on a checkout other agents occupy). The item is real, so ok stays
        True and only `delivered` goes false."""
        self._stub_delivery(monkeypatch, {
            "ok": False, "committed": True, "pushed": False,
            "error": "the push was refused (! [rejected] main -> main)"})
        r = marketing.intelligence_approve("story-alpha", "draft-wire-1")
        assert r["ok"] is True
        assert r["delivered"] is False
        assert "NOT reached the publisher" in r["note"]
        assert "will not post" in r["note"]
        assert "refused" in r["note"]
        # NEVER un-queued: the row the operator queued is still on disk
        items = _intel_items(deployed_root)
        assert len(items) == 1 and items[0]["id"] == r["item_id"]

    def test_a_gitops_refusal_is_named_not_swallowed(self, deployed_root,
                                                     monkeypatch):
        """The dev-checkout case: gitops refuses to push off a main-tracking
        branch. That is correct behaviour and a non-delivery, and the operator is
        told which it is."""
        self._stub_delivery(monkeypatch, {
            "ok": True, "committed": True, "pushed": False,
            "warning": ("committed locally; refused to push (not on a main "
                        "tracking branch)")})
        r = marketing.intelligence_approve("story-alpha", "draft-wire-1")
        assert r["ok"] is True and r["delivered"] is False
        assert "not on a main tracking branch" in r["note"]

    def test_a_named_push_error_is_folded_into_the_note(self, deployed_root,
                                                        monkeypatch):
        self._stub_delivery(monkeypatch, {
            "ok": False, "committed": True, "pushed": False,
            "error": "git push failed (network unreachable)"})
        r = marketing.intelligence_approve("story-alpha", "draft-wire-1")
        assert r["ok"] is True and r["delivered"] is False
        assert "network unreachable" in r["note"]

    def test_a_thrown_delivery_error_never_un_queues_the_item(
            self, deployed_root, monkeypatch):
        self._stub_delivery(monkeypatch, RuntimeError("git binary missing"))
        r = marketing.intelligence_approve("story-alpha", "draft-wire-1")
        assert r["ok"] is True and r["delivered"] is False
        assert "git binary missing" in r["note"]
        assert len(_intel_items(deployed_root)) == 1

    def test_a_refused_approval_never_attempts_delivery(self, deployed_root,
                                                        monkeypatch):
        """Nothing was enqueued, so there is nothing to deliver — and a commit
        here would sweep up whatever else is dirty in the checkout."""
        seen = self._stub_delivery(monkeypatch, {"ok": True, "pushed": True})
        r = marketing.intelligence_approve("story-beta", "draft-beta-cheese")
        assert r["ok"] is False and r["reason"] == "banned_language"
        assert seen == {}


class _FakeContents:
    """The file on main, behind a stand-in Contents API.

    Records every GET and PUT so a test can assert the read-append-write ORDER —
    a retry that does not re-read would overwrite whichever lane appended in
    between. ``conflicts`` scripts the first N PUTs to answer "stale sha" AND
    moves the file underneath us, which is what actually happens on this repo:
    the press wire appends to these ledgers every few minutes.
    """

    def __init__(self, content: str = "", sha: str = "sha-main-0",
                 conflicts: int = 0):
        self.content = content
        self.sha = sha
        self.conflicts = conflicts
        self.gets: list[str] = []
        self.puts: list[dict] = []

    def install(self, monkeypatch, *, has_token: bool = True):
        from admin import github_api
        monkeypatch.setattr(github_api, "available", lambda: {
            "ok": True, "has_token": has_token, "lib": True,
            "owner": "o", "repo": "r"})
        monkeypatch.setattr(github_api, "get_file", self._get)
        monkeypatch.setattr(github_api, "put_file", self._put)
        return self

    def _get(self, path, ref="main"):
        self.gets.append(path)
        return {"ok": True, "content": self.content, "sha": self.sha}

    def _put(self, path, content, message, *, sha=None, branch="main"):
        self.puts.append({"path": path, "content": content, "message": message,
                          "sha": sha, "branch": branch})
        if self.conflicts > 0:
            self.conflicts -= 1
            self.content += '{"id":"another-lane-got-there-first"}\n'
            self.sha = self.sha + "-moved"
            return {"ok": False,
                    "error": "HTTP 409 — sha conflict (file changed under us); retry"}
        self.content = content
        self.sha = "sha-main-after"
        return {"ok": True, "commit_sha": "c0ffee"}


class TestIntelligenceApproveDeliveryDeployed:
    """On the DEPLOYED admin, commit+push cannot deliver — at all.

    That checkout has no authenticated git remote, and app/deploy/update.sh
    resets it ``--hard`` to origin/main every ~3 minutes. A local commit there is
    not slow delivery, it is DELETED delivery: the reset discards the commit and
    takes the operator's queued row with it, while the panel showed "queued" the
    whole time. So the deployed host writes the item straight to main through the
    GitHub Contents API — the same tokened path the account toggle uses.
    """

    @pytest.fixture()
    def deployed_vps(self, intel_root, monkeypatch):
        """The real deployed shape: root=None AND ADMIN_DEPLOYED=1."""
        monkeypatch.setattr(marketing, "_default_root", lambda: intel_root)
        monkeypatch.setattr(marketing, "_INTELLIGENCE_LIVE",
                            intel_root / "no-live-plane" / "intelligence.json")
        monkeypatch.setenv("ADMIN_DEPLOYED", "1")
        return intel_root

    @staticmethod
    def _local_line(root) -> str:
        """The last line of the LOCAL items.jsonl, verbatim (no trailing \\n)."""
        p = pathlib.Path(root) / "data" / "marketing" / "outbox" / "items.jsonl"
        return p.read_text(encoding="utf-8").splitlines()[-1]

    @staticmethod
    def _no_git(monkeypatch) -> list:
        """Trip-wire on every gitops write: the deployed path must call none."""
        from admin import gitops
        called: list = []
        for name in ("commit_paths_synced", "commit_paths", "commit", "_git"):
            monkeypatch.setattr(
                gitops, name,
                lambda *a, _n=name, **kw: called.append(_n) or {"ok": True})
        return called

    # ---- (a) the happy path --------------------------------------------------

    def test_the_appended_line_is_byte_identical_to_the_local_row(
            self, deployed_vps, monkeypatch):
        """The row PUT to main must be the row ledgers.append_jsonl wrote here.

        main's copy and this checkout's copy are the same append-only file under
        a union merge driver. A re-serialized row (different key order, spaced
        separators, \\u-escaped CJK) is a different line for the same item — it
        would survive the fold as a second row and show up as a diff forever.
        Comparing against the file the engine actually wrote pins the format to
        its real writer, so a change in ledgers.append_jsonl fails HERE.
        """
        self._no_git(monkeypatch)
        gh = _FakeContents(content='{"id":"older-row"}\n').install(monkeypatch)
        r = marketing.intelligence_approve("story-alpha", "draft-wire-1")

        assert r["ok"] is True and r["delivered"] is True
        assert len(gh.puts) == 1
        put = gh.puts[0]
        assert put["path"] == "data/marketing/outbox/items.jsonl"
        assert put["branch"] == "main"
        assert put["sha"] == "sha-main-0"          # threaded from the GET
        assert put["message"] == (
            f"admin: intelligence desk approve {r['item_id']}")
        # append, not replace: the pre-existing row survives byte-for-byte
        assert put["content"] == (
            '{"id":"older-row"}\n' + self._local_line(deployed_vps) + "\n")
        assert "publisher will see it" in r["note"]
        assert "nothing posts now" in r["note"].lower()

    def test_the_idempotency_marker_matches_the_engines_own_serialization(
            self, deployed_vps, monkeypatch):
        """The guard looks for the compact ``"id":"…"`` field. If the writer's
        separators ever change, the marker stops matching and the guard silently
        stops guarding — so assert the marker against the real written line."""
        self._no_git(monkeypatch)
        _FakeContents().install(monkeypatch)
        r = marketing.intelligence_approve("story-alpha", "draft-wire-1")
        assert f'"id":"{r["item_id"]}"' in self._local_line(deployed_vps)

    # ---- (b) + (c) the file moves under us -----------------------------------

    def test_a_stale_sha_re_reads_and_retries_without_dropping_the_other_row(
            self, deployed_vps, monkeypatch):
        self._no_git(monkeypatch)
        gh = _FakeContents(conflicts=1).install(monkeypatch)
        r = marketing.intelligence_approve("story-alpha", "draft-wire-1")

        assert r["delivered"] is True
        # TWO reads: the retry re-read the file rather than re-PUT a body built
        # from the stale copy, which is the only reason the other lane's row is
        # still there afterwards.
        assert len(gh.gets) == 2 and len(gh.puts) == 2
        assert gh.puts[1]["sha"] == "sha-main-0-moved"
        assert '"id":"another-lane-got-there-first"' in gh.puts[1]["content"]
        assert gh.puts[1]["content"].endswith(
            self._local_line(deployed_vps) + "\n")

    def test_exhausted_retries_report_delivered_false_and_keep_the_item(
            self, deployed_vps, monkeypatch):
        self._no_git(monkeypatch)
        gh = _FakeContents(conflicts=99).install(monkeypatch)
        r = marketing.intelligence_approve("story-alpha", "draft-wire-1")

        assert r["ok"] is True and r["delivered"] is False
        assert len(gh.gets) == 3 and len(gh.puts) == 3   # bounded, not infinite
        assert "NOT reached the publisher" in r["note"]
        assert "will not post" in r["note"]
        assert "writes the row to main" in r["note"]     # the step is NAMED
        assert "approve it again later" in r["note"]
        # never un-queued: the row is real on this disk either way
        items = _intel_items(deployed_vps)
        assert len(items) == 1 and items[0]["id"] == r["item_id"]

    def test_a_retry_whose_re_read_finds_our_own_id_stops_without_a_second_put(
            self, deployed_vps, monkeypatch):
        """Review N12: the idempotency check must live INSIDE the retry loop.

        The race this pins: our PUT is rejected as a stale sha, and the write
        that beat us carried the SAME item row (a twin admin worker, or our own
        first PUT that half-landed). The re-read now contains our id — a loop
        whose marker check ran only on the FIRST read would append the row a
        second time. Hoisting the check above the loop passes every other test
        in this class; this one fails it.
        """
        self._no_git(monkeypatch)

        class _SelfRaced(_FakeContents):
            def _put(self, path, content, message, *, sha=None, branch="main"):
                self.puts.append({"path": path, "content": content,
                                  "message": message, "sha": sha,
                                  "branch": branch})
                if self.conflicts > 0:
                    self.conflicts -= 1
                    # The competing write carried OUR row: the body this PUT
                    # tried to write becomes main's content.
                    self.content = content
                    self.sha = self.sha + "-moved"
                    return {"ok": False,
                            "error": "HTTP 409 — sha conflict; retry"}
                return {"ok": True, "commit_sha": "c0ffee"}

        gh = _SelfRaced(conflicts=1).install(monkeypatch)
        r = marketing.intelligence_approve("story-alpha", "draft-wire-1")

        assert r["ok"] is True and r["delivered"] is True
        assert "already" in r["note"], "a found-on-main row must say so"
        # Two reads (the retry re-read), but only ONE put — the rejected one.
        # A second PUT here is the double-append this test exists to forbid.
        assert len(gh.gets) == 2
        assert len(gh.puts) == 1
        assert gh.content.count(f'"id":"{r["item_id"]}"') == 1

    # ---- (d) idempotency ------------------------------------------------------

    def test_an_id_already_on_main_is_never_appended_twice(
            self, deployed_vps, monkeypatch):
        """The dangerous re-click is the one AFTER the deploy pull.

        The 3-minute reset takes the local row with it, so the local duplicate
        guard has no memory of the first click — and the item id is a content
        hash, so the second click rebuilds the SAME id. Only main can answer
        "already delivered?" in a way that survives that reset.
        """
        self._no_git(monkeypatch)
        first = _FakeContents().install(monkeypatch)
        r1 = marketing.intelligence_approve("story-alpha", "draft-wire-1")
        assert r1["delivered"] is True and len(first.puts) == 1
        on_main = first.content

        (pathlib.Path(deployed_vps) / "data" / "marketing" / "outbox"
         / "items.jsonl").unlink()                       # the deploy pull
        second = _FakeContents(content=on_main, sha="sha-main-9").install(monkeypatch)
        r2 = marketing.intelligence_approve("story-alpha", "draft-wire-1")

        assert r2["item_id"] == r1["item_id"]            # deterministic id
        assert second.puts == [], "the row was appended to main twice"
        assert r2["delivered"] is True                   # it IS on main
        assert "already on the shared queue" in r2["note"]
        assert "queued nothing twice" in r2["note"]

    def test_another_items_row_on_main_does_not_look_like_this_one(
            self, deployed_vps, monkeypatch):
        """The guard must key on THIS id, not on anything an outbox row happens
        to carry.

        A marker keyed on a shared field ("status":"queued", the schema id, the
        account) matches on the first sweep and every sweep after it, so the
        append quietly no-ops and the click reports delivered — the exact silent
        non-delivery this whole path exists to end. The seeded row here is a byte
        copy of a real one with only the id changed, so nothing BUT the id can
        distinguish them.
        """
        self._no_git(monkeypatch)
        _FakeContents().install(monkeypatch)
        r1 = marketing.intelligence_approve("story-alpha", "draft-wire-1")
        mine = self._local_line(deployed_vps)
        someone_else = mine.replace(r1["item_id"], "post-a-different-item-0001")
        assert someone_else != mine

        (pathlib.Path(deployed_vps) / "data" / "marketing" / "outbox"
         / "items.jsonl").unlink()
        gh = _FakeContents(content=someone_else + "\n").install(monkeypatch)
        r2 = marketing.intelligence_approve("story-alpha", "draft-wire-1")

        assert r2["delivered"] is True
        assert len(gh.puts) == 1, "a different item's row was read as this one"
        assert gh.puts[0]["content"] == someone_else + "\n" + mine + "\n"
        assert "already" not in r2["note"]

    # ---- (e) the size ceiling -------------------------------------------------

    def test_a_ledger_near_the_api_ceiling_is_refused_honestly(
            self, deployed_vps, monkeypatch):
        """Over ~1 MB the Contents API rejects the whole write. Refuse early and
        say the fix is rotation — do NOT send the operator back to a button that
        cannot work."""
        from admin import github_api
        self._no_git(monkeypatch)
        big = "z" * (github_api.CONTENTS_APPEND_MAX_BYTES + 1)
        gh = _FakeContents(content=big).install(monkeypatch)
        r = marketing.intelligence_approve("story-alpha", "draft-wire-1")

        assert r["ok"] is True and r["delivered"] is False
        assert gh.puts == []                             # refused BEFORE the write
        assert "too big" in r["note"]
        assert "Rotating the shared queue" in r["note"]
        assert "approve it again later" not in r["note"]
        assert len(_intel_items(deployed_vps)) == 1

    # ---- (f) the switch -------------------------------------------------------

    def test_deployed_delivery_never_shells_out_to_git(self, deployed_vps,
                                                        monkeypatch):
        """A git commit on the VPS is worse than useless: it cannot push, and the
        next `reset --hard` deletes it. One mechanism per host, never both."""
        called = self._no_git(monkeypatch)
        gh = _FakeContents().install(monkeypatch)
        r = marketing.intelligence_approve("story-alpha", "draft-wire-1")
        assert r["delivered"] is True and len(gh.puts) == 1
        assert called == [], f"the deployed path called git: {called}"

    def test_a_local_checkout_never_calls_the_contents_api(self, intel_root,
                                                            monkeypatch):
        """And the mirror image: an authenticated local checkout keeps B2's
        commit+push. Writing to main through the API from a machine that can push
        would bypass the branch the operator is actually working on."""
        monkeypatch.setattr(marketing, "_default_root", lambda: intel_root)
        monkeypatch.setattr(marketing, "_INTELLIGENCE_LIVE",
                            intel_root / "no-live-plane" / "intelligence.json")
        monkeypatch.delenv("ADMIN_DEPLOYED", raising=False)
        gh = _FakeContents().install(monkeypatch)
        seen = TestIntelligenceApproveDelivery._stub_delivery(
            monkeypatch, {"ok": True, "committed": True, "pushed": True})
        r = marketing.intelligence_approve("story-alpha", "draft-wire-1")

        assert r["delivered"] is True
        assert seen["paths"] == list(marketing._INTEL_OUTBOX_LEDGERS)
        assert gh.gets == [] and gh.puts == []

    # ---- (g) no way to reach the API ------------------------------------------

    def test_a_missing_token_is_named_not_swallowed(self, deployed_vps,
                                                     monkeypatch):
        """No token = no delivery, and the operator is told which step is
        missing. Reporting delivered:true here would be the worst outcome: the
        row is on a disk that gets wiped in three minutes."""
        self._no_git(monkeypatch)
        gh = _FakeContents().install(monkeypatch, has_token=False)
        r = marketing.intelligence_approve("story-alpha", "draft-wire-1")

        assert r["ok"] is True and r["delivered"] is False
        assert gh.gets == [] and gh.puts == []           # refused before any call
        assert "NOT reached the publisher" in r["note"]
        assert "no working link to the shared queue" in r["note"]
        assert "GH_TOKEN" in r["note"]
        assert len(_intel_items(deployed_vps)) == 1

    def test_an_unreadable_ledger_on_main_names_the_read_step(
            self, deployed_vps, monkeypatch):
        from admin import github_api
        self._no_git(monkeypatch)
        monkeypatch.setattr(github_api, "available", lambda: {
            "ok": True, "has_token": True, "lib": True, "owner": "o", "repo": "r"})
        monkeypatch.setattr(github_api, "get_file", lambda *a, **k: {
            "ok": False, "error": "HTTP 404 — the token cannot see this repository"})
        puts: list = []
        monkeypatch.setattr(github_api, "put_file",
                            lambda *a, **k: puts.append(a) or {"ok": True})
        r = marketing.intelligence_approve("story-alpha", "draft-wire-1")
        assert r["delivered"] is False and puts == []
        assert "reads the shared queue on main" in r["note"]
        assert "404" in r["note"]

    def test_a_permission_error_on_the_write_does_not_retry(
            self, deployed_vps, monkeypatch):
        """403 is not a race. Re-reading and re-PUTting spends three round trips
        to be refused three times and tells the operator nothing new."""
        from admin import github_api
        self._no_git(monkeypatch)
        gets: list = []
        monkeypatch.setattr(github_api, "available", lambda: {
            "ok": True, "has_token": True, "lib": True, "owner": "o", "repo": "r"})
        monkeypatch.setattr(github_api, "get_file", lambda *a, **k: gets.append(a) or {
            "ok": True, "content": "", "sha": "s0"})
        monkeypatch.setattr(github_api, "put_file", lambda *a, **k: {
            "ok": False, "error": "HTTP 403 — the GitHub token can't write repo contents."})
        r = marketing.intelligence_approve("story-alpha", "draft-wire-1")
        assert r["delivered"] is False
        assert len(gets) == 1, "a 403 was retried as if it were a sha conflict"
        assert "403" in r["note"] and "writes the row to main" in r["note"]


class TestAppendJsonlLine:
    """The Contents-API append primitive itself, at the seams the caller can't
    reach: a file that does not exist yet, and one whose last line has no
    newline. Both would corrupt an append-only ledger by fusing two rows into
    one — and a fused row is TWO items the publisher can no longer read."""

    @staticmethod
    def _api(monkeypatch, content, sha="s0"):
        from admin import github_api
        monkeypatch.setattr(github_api, "available", lambda: {
            "ok": True, "has_token": True, "lib": True, "owner": "o", "repo": "r"})
        monkeypatch.setattr(github_api, "get_file",
                            lambda *a, **k: {"ok": True, "content": content, "sha": sha})
        seen: dict = {}
        monkeypatch.setattr(github_api, "put_file",
                            lambda p, c, m, sha=None, branch="main":
                            seen.update(content=c, sha=sha) or {"ok": True, "commit_sha": "c1"})
        return seen

    def test_a_missing_file_is_created_with_just_the_row(self, monkeypatch):
        from admin import github_api
        seen = self._api(monkeypatch, None, sha=None)     # 404 shape from get_file
        r = github_api.append_jsonl_line("x.jsonl", '{"id":"a"}', "msg")
        assert r["ok"] is True and r["appended"] is True
        assert seen["content"] == '{"id":"a"}\n' and seen["sha"] is None

    def test_a_file_with_no_trailing_newline_does_not_fuse_two_rows(
            self, monkeypatch):
        from admin import github_api
        seen = self._api(monkeypatch, '{"id":"a"}')       # truncated last line
        github_api.append_jsonl_line("x.jsonl", '{"id":"b"}', "msg")
        assert seen["content"] == '{"id":"a"}\n{"id":"b"}\n'

    def test_the_marker_check_happens_before_any_write(self, monkeypatch):
        from admin import github_api
        seen = self._api(monkeypatch, '{"id":"a"}\n')
        r = github_api.append_jsonl_line("x.jsonl", '{"id":"a"}', "msg",
                                         if_absent='"id":"a"')
        assert r == {"ok": True, "appended": False, "reason": "already_present",
                     "attempts": 1}
        assert seen == {}


class TestIntelligenceApproveAuthWiring:
    """The approve endpoint carries NO auth of its own, by design: admin/server.py
    do_POST refuses every write with 401 (no session) / 403 (no double-submit
    CSRF token) BEFORE it dispatches on the path, so a per-route check would be a
    second source of truth that can drift. What must stay true is the ORDERING —
    a marketing POST route registered above that block would be reachable
    unauthenticated."""

    @staticmethod
    def _do_post_source() -> str:
        server = pathlib.Path(marketing.__file__).resolve().parent / "server.py"
        return server.read_text(encoding="utf-8").split("def do_POST", 1)[1]

    def test_marketing_post_routes_are_registered_after_the_auth_gate(self):
        body = self._do_post_source()
        assert body.index('"authentication required"') < body.index('"/api/marketing/')
        assert body.index("CSRF token missing/invalid") < body.index('"/api/marketing/')

    def test_the_approve_route_sits_behind_that_gate(self):
        """ARMED (the route landed). This used to skip while the handler existed
        and the route did not; a conditional skip that outlives its condition is
        a test that reports green on a route nobody registered, so the absence of
        the route is now a FAILURE, not a skip."""
        body = self._do_post_source()
        at = body.find("/api/marketing/intelligence/approve")
        assert at > 0, ("POST /api/marketing/intelligence/approve is not "
                        "registered in admin/server.py — the admin panel's "
                        "approve button posts into the void")
        assert at > body.index('"authentication required"')
        assert at > body.index("CSRF token missing/invalid")

    def test_the_handler_the_route_will_call_exists(self):
        assert callable(getattr(marketing, "intelligence_approve", None))


# ---------------------------------------------------------------------------
# POST /api/marketing/intelligence/approve — the live HTTP contract.
#
# The class above reads the source for ORDERING; these ride the real socket, so
# they see what a browser sees: status codes, and whether the refusal shape the
# panel keys its message off survives the trip.
# ---------------------------------------------------------------------------

def _admin_server():
    from http.server import ThreadingHTTPServer  # noqa: PLC0415
    import threading  # noqa: PLC0415

    from admin.server import Handler  # noqa: PLC0415
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    return httpd, httpd.server_address[1]


def _approve_post(port, body, cookies=None, headers=None):
    """POST the approve route. Returns (status, payload) for BOTH success and
    error responses — an HTTPError carries the JSON body the panel reads, so
    swallowing it would hide the very contract under test."""
    import urllib.error  # noqa: PLC0415
    import urllib.request  # noqa: PLC0415

    h = {"Content-Type": "application/json"}
    if cookies:
        h["Cookie"] = "; ".join(f"{k}={v}" for k, v in cookies.items())
    if headers:
        h.update(headers)
    req = urllib.request.Request(
        f"http://127.0.0.1:{port}/api/marketing/intelligence/approve",
        data=json.dumps(body).encode(), headers=h, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            return r.status, json.loads(r.read())
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read())


@pytest.fixture()
def approve_server(monkeypatch):
    """A live admin server whose approve handler is a recording stub.

    The handler itself is tested exhaustively above against a fixture root; what
    these tests own is the ROUTE, so the handler is replaced by a spy. That also
    keeps the socket tests from writing an outbox row anywhere.
    """
    calls: list[tuple] = []
    reply: dict = {"ok": True, "item_id": "post-x-1", "account": "flagship",
                   "note": "queued", "delivered": True}

    def spy(story_id, draft_id, *a, **kw):
        calls.append((story_id, draft_id))
        return reply

    monkeypatch.setattr(marketing, "intelligence_approve", spy)
    httpd, port = _admin_server()
    try:
        yield port, calls, reply
    finally:
        httpd.shutdown()
        httpd.server_close()


class TestIntelligenceApproveRoute:
    def test_missing_or_blank_ids_are_400_and_never_reach_the_handler(
            self, approve_server):
        """Shape is the ROUTE's job. A blank id must not become a handler call
        that refuses for some deeper-sounding reason — the operator would read
        'story not found' for a bug in the card's data attributes."""
        port, calls, _ = approve_server
        for body, want in (
            ({}, "story_id"),
            ({"draft_id": "d1"}, "story_id"),
            ({"story_id": "s1"}, "draft_id"),
            ({"story_id": "   ", "draft_id": "d1"}, "story_id"),
            ({"story_id": "s1", "draft_id": ""}, "draft_id"),
            ({"story_id": 7, "draft_id": "d1"}, "story_id"),
            ({"story_id": "s1", "draft_id": ["d1"]}, "draft_id"),
        ):
            code, payload = _approve_post(port, body)
            assert code == 400, (body, payload)
            assert payload["ok"] is False
            assert want in payload["error"], (body, payload)
        assert calls == [], "a malformed request reached the approve handler"

    def test_a_queued_approval_is_200_and_carries_the_item(self, approve_server):
        port, calls, _ = approve_server
        code, payload = _approve_post(port, {"story_id": "story-alpha",
                                             "draft_id": "draft-wire-1"})
        assert code == 200, payload
        assert payload["ok"] is True
        assert payload["item_id"] == "post-x-1"
        assert payload["account"] == "flagship"
        assert calls == [("story-alpha", "draft-wire-1")]

    def test_a_refusal_is_400_with_reason_and_detail_intact(self, approve_server):
        """The panel prints `reason`/`detail`; the shared route guards print
        `error`. Flattening one into the other is how a named gate turns into
        'Not queued: no detail given' in the UI."""
        port, _, reply = approve_server
        reply.clear()
        reply.update({"ok": False, "reason": "story_locked",
                      "detail": "flagship already has this story",
                      "owner": "flagship"})
        code, payload = _approve_post(port, {"story_id": "s1", "draft_id": "d1"})
        assert code == 400
        assert payload["reason"] == "story_locked"
        assert payload["detail"] == "flagship already has this story"
        assert payload["owner"] == "flagship"

    def test_auth_and_csrf_are_refused_before_the_handler_runs(self, monkeypatch):
        """401 (no session) and 403 (no double-submit CSRF) come from the shared
        do_POST gate ABOVE path dispatch. Asserted over the socket as well as in
        source order, because 'registered after the gate' is only protective if
        the gate actually fires for this path."""
        from admin import auth  # noqa: PLC0415

        calls: list[tuple] = []
        monkeypatch.setattr(marketing, "intelligence_approve",
                            lambda *a, **kw: calls.append(a) or {"ok": True})
        monkeypatch.setenv("ADMIN_PASSWORD", "s3cret")
        monkeypatch.setenv("ADMIN_SESSION_SECRET", "route-test-secret")
        httpd, port = _admin_server()
        try:
            body = {"story_id": "s1", "draft_id": "d1"}
            code, payload = _approve_post(port, body)
            assert code == 401 and "authentication" in payload["error"]

            # a valid session is not enough: the write still needs the CSRF header
            csrf = auth.new_csrf()
            jar = {auth.SESSION_COOKIE: auth.mint_session(),
                   auth.CSRF_COOKIE: csrf}
            code, payload = _approve_post(port, body, cookies=jar)
            assert code == 403 and "CSRF" in payload["error"]

            assert calls == [], "an unauthenticated request reached the handler"

            # with both, the route dispatches normally
            code, payload = _approve_post(port, body, cookies=jar,
                                          headers={auth.CSRF_HEADER: csrf})
            assert code == 200, payload
            assert calls == [("s1", "d1")]
        finally:
            httpd.shutdown()
            httpd.server_close()
