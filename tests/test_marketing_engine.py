"""tests/test_marketing_engine.py — Marketing lobe engine tests.

Spec §1 test list:
- state builds without error
- 10 departments chartered with required charter fields
- authority ladder has G0..G7
- opportunity scoring monotonic in expected_value
- campaign distinctness flags identical variants and passes distinct ones
- economics formula subtracts all cost terms
- self-deception checks all present
- growth-event taxonomy non-empty
- governor build_and_write writes both artifacts with envelope keys
- seed ledgers round-trip
"""
from __future__ import annotations

import json
import math
import tempfile
from datetime import datetime, timezone
from pathlib import Path

import pytest

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _worktree_root() -> Path:
    """Return the repo root (the directory containing engine/)."""
    p = Path(__file__).resolve()
    # Walk up until we find engine/
    for candidate in [p.parent, p.parent.parent, p.parent.parent.parent]:
        if (candidate / "engine").is_dir():
            return candidate
    raise RuntimeError(f"Could not locate repo root from {p}")


ROOT = _worktree_root()


# ---------------------------------------------------------------------------
# 1. State builds without error
# ---------------------------------------------------------------------------

def test_build_state_returns_dict():
    from engine.marketing.state import build_state
    state = build_state(root=ROOT)
    assert isinstance(state, dict)
    assert state.get("schema") == "marketing.state/v1"
    assert "lobe" in state
    assert "departments" in state
    assert "waves" in state
    assert "authority_ladder" in state


def test_build_state_no_error_key():
    from engine.marketing.state import build_state
    state = build_state(root=ROOT)
    # Must not be an error state
    assert state.get("state") != "error", f"build_state returned error: {state.get('error')}"


# ---------------------------------------------------------------------------
# 2. 10 departments chartered with required charter fields
# ---------------------------------------------------------------------------

def test_ten_departments():
    from engine.marketing.departments import DEPARTMENT_CHARTERS
    assert len(DEPARTMENT_CHARTERS) == 10


def test_department_required_fields():
    from engine.marketing.departments import DEPARTMENT_CHARTERS
    required_keys = {
        "id", "name", "formal_name", "tagline", "icon",
        "director_model", "primary_outcome", "non_goals",
        "engines", "authority_level", "lifecycle_state", "budget",
        "model_mix", "clock", "retirement_test", "scorecard", "wave",
    }
    for dept in DEPARTMENT_CHARTERS:
        d = dept.as_dict()
        missing = required_keys - set(d.keys())
        assert not missing, f"dept {dept.id} missing fields: {missing}"
        # Scorecard sub-fields
        sc = d["scorecard"]
        sc_keys = {"primary_metric", "leading", "trust_health",
                   "experiment_velocity", "learning_quality", "authority_level"}
        assert sc_keys.issubset(set(sc.keys())), f"dept {dept.id} scorecard missing: {sc_keys - set(sc.keys())}"


def test_department_short_names():
    """Departments must have the spec §1.1 short names."""
    from engine.marketing.departments import _DEPT_BY_ID
    expected = {
        "office_cmo": "Command",
        "growth_os": "Engine Room",
        "intelligence": "Radar",
        "products": "Workshop",
        "studio": "Studio",
        "distribution": "Broadcast",
        "lifecycle": "Funnel",
        "ecosystem": "Allies",
        "growth_science": "Lab",
        "trust_office": "Sentinel",
    }
    for dept_id, expected_name in expected.items():
        dept = _DEPT_BY_ID[dept_id]
        assert dept.name == expected_name, (
            f"dept {dept_id}: expected name {expected_name!r}, got {dept.name!r}"
        )


def test_department_icons():
    """Departments must have the spec §1.1 icon slugs."""
    from engine.marketing.departments import _DEPT_BY_ID
    expected_icons = {
        "office_cmo": "command",
        "growth_os": "engine_room",
        "intelligence": "radar",
        "products": "workshop",
        "studio": "studio",
        "distribution": "broadcast",
        "lifecycle": "funnel",
        "ecosystem": "allies",
        "growth_science": "lab",
        "trust_office": "sentinel",
    }
    for dept_id, expected_icon in expected_icons.items():
        dept = _DEPT_BY_ID[dept_id]
        assert dept.icon == expected_icon, (
            f"dept {dept_id}: expected icon {expected_icon!r}, got {dept.icon!r}"
        )


def test_department_formal_names_non_empty():
    """All departments must have non-empty formal_name and tagline."""
    from engine.marketing.departments import DEPARTMENT_CHARTERS
    for dept in DEPARTMENT_CHARTERS:
        assert dept.formal_name, f"dept {dept.id} has empty formal_name"
        assert dept.tagline, f"dept {dept.id} has empty tagline"


def test_engines_are_dicts_with_id_name_does():
    """All engines must be dicts with id, name, does keys."""
    from engine.marketing.departments import DEPARTMENT_CHARTERS
    for dept in DEPARTMENT_CHARTERS:
        for engine in dept.engines:
            assert isinstance(engine, dict), (
                f"dept {dept.id}: engine is not a dict: {engine!r}"
            )
            for key in ("id", "name", "does"):
                assert key in engine, (
                    f"dept {dept.id} engine {engine.get('id', '?')} missing key: {key}"
                )
            # ≤3 meaningful words (& connector words excluded, per spec §1.2 naming)
            meaningful = [w for w in engine["name"].split()
                          if w.lower() not in ("&", "the", "of", "a", "an")]
            assert len(meaningful) <= 3, (
                f"dept {dept.id} engine {engine['id']} name too long: {engine['name']!r}"
            )
            assert len(engine["does"]) > 10, (
                f"dept {dept.id} engine {engine['id']} does too short: {engine['does']!r}"
            )


def test_content_studio_engine_in_distribution():
    """content_studio engine must exist in the distribution department."""
    from engine.marketing.departments import _DEPT_BY_ID
    dist = _DEPT_BY_ID["distribution"]
    engine_ids = [e["id"] for e in dist.engines]
    assert "content_studio" in engine_ids, (
        f"content_studio engine missing from distribution; found: {engine_ids}"
    )


def test_office_cmo_director_model_is_fable():
    from engine.marketing.departments import _DEPT_BY_ID
    cmo = _DEPT_BY_ID["office_cmo"]
    assert cmo.director_model == "fable"


def test_other_depts_director_model_is_opus():
    from engine.marketing.departments import DEPARTMENT_CHARTERS
    for dept in DEPARTMENT_CHARTERS:
        if dept.id != "office_cmo":
            assert dept.director_model == "opus", (
                f"dept {dept.id} expected opus, got {dept.director_model}"
            )


def test_growth_os_lifecycle_building():
    from engine.marketing.departments import _DEPT_BY_ID
    gos = _DEPT_BY_ID["growth_os"]
    assert gos.lifecycle_state == "building"


def test_other_depts_lifecycle_chartered():
    from engine.marketing.departments import DEPARTMENT_CHARTERS
    for dept in DEPARTMENT_CHARTERS:
        if dept.id != "growth_os":
            assert dept.lifecycle_state == "chartered", (
                f"dept {dept.id} expected chartered, got {dept.lifecycle_state}"
            )


def test_dept_registry_config_override(tmp_path):
    """Config override changes lifecycle_state."""
    cfg = {"departments": {"growth_os": {"lifecycle_state": "chartered"}}}
    from engine.marketing.departments import registry
    depts = registry(cfg=cfg)
    gos = next(d for d in depts if d.id == "growth_os")
    assert gos.lifecycle_state == "chartered"


# ---------------------------------------------------------------------------
# 3. Authority ladder G0..G7
# ---------------------------------------------------------------------------

def test_authority_ladder_g0_to_g7():
    from engine.marketing.authority import LADDER, GrowthAuthority
    assert len(LADDER) == 8
    levels = [e["level"] for e in LADDER]
    for ga in GrowthAuthority:
        assert ga.name in levels, f"{ga.name} missing from LADDER"


def test_authority_ladder_names():
    from engine.marketing.authority import LADDER
    names = {e["name"] for e in LADDER}
    expected = {"Observe", "Create", "Shadow", "Publish", "Engage", "Allocate", "Organize", "Root"}
    assert names == expected


def test_can_earn_all_true():
    from engine.marketing.authority import can_earn
    record = {
        "passed_shadow": True,
        "clean_receipts": True,
        "within_cost_cap": True,
        "positive_incremental_impact": True,
        "no_unresolved_corrections": True,
        "survived_red_team": True,
        "reliable_rollback": True,
    }
    assert can_earn(record) is True


def test_can_earn_missing_key_is_false():
    from engine.marketing.authority import can_earn
    assert can_earn({}) is False


def test_should_narrow_with_warning():
    from engine.marketing.authority import should_narrow
    assert should_narrow({"platform_warnings_increased": True}) is True
    assert should_narrow({}) is False


# ---------------------------------------------------------------------------
# 4. Opportunity scoring monotonic in expected_value
# ---------------------------------------------------------------------------

def test_opportunity_scoring_monotonic_in_expected_value():
    from engine.marketing.opportunity_bus import score_dict
    now = datetime.now(timezone.utc)
    base = {
        "opportunity_id": "t1",
        "detected_at": now.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "source_type": "evergreen",
        "originality": 1.0,
    }
    scores = []
    for ev in [0.0, 0.25, 0.5, 0.75, 1.0]:
        d = dict(base)
        d["expected_value"] = ev
        scores.append(score_dict(d, now=now))
    assert scores == sorted(scores), f"Scores not monotonically increasing: {scores}"


def test_opportunity_score_clamped():
    from engine.marketing.opportunity_bus import score_dict
    now = datetime.now(timezone.utc)
    d = {
        "opportunity_id": "t2",
        "detected_at": now.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "source_type": "evergreen",
        "expected_value": 2.0,  # clamped to 1.0
        "originality": 1.0,
    }
    s = score_dict(d, now=now)
    assert 0.0 <= s <= 1.0


def test_opportunity_score_decays_with_age():
    from engine.marketing.opportunity_bus import score_dict
    import datetime as dt
    now = datetime.now(timezone.utc)
    old = now - dt.timedelta(hours=48)
    base_ev = 0.8
    fresh = {
        "opportunity_id": "tf",
        "detected_at": now.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "source_type": "breaking_event",
        "expected_value": base_ev,
        "originality": 1.0,
    }
    stale = {
        "opportunity_id": "ts",
        "detected_at": old.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "source_type": "breaking_event",
        "expected_value": base_ev,
        "originality": 1.0,
    }
    assert score_dict(fresh, now=now) > score_dict(stale, now=now)


# ---------------------------------------------------------------------------
# 5. Campaign distinctness
# ---------------------------------------------------------------------------

def test_distinctness_flags_identical_variants():
    from engine.marketing.campaign_compiler import distinctness
    result = distinctness(["hello world this is a test", "hello world this is a test"])
    assert result["flags"] >= 1
    assert result["max_similarity"] == 1.0


def test_distinctness_passes_distinct_variants():
    from engine.marketing.campaign_compiler import distinctness
    v1 = "macro rates liquidity explainer educational"
    v2 = "single stock why moving fast reactive desk chart"
    v3 = "charts historical analogues pattern history"
    result = distinctness([v1, v2, v3])
    assert result["flags"] == 0
    assert result["max_similarity"] < 0.7


def test_distinctness_empty_list():
    from engine.marketing.campaign_compiler import distinctness
    result = distinctness([])
    assert result["max_similarity"] == 0.0
    assert result["flags"] == 0


def test_compile_campaign_returns_campaign():
    from engine.marketing.campaign_compiler import compile as compile_campaign
    opp = {
        "opportunity_id": "opp-t1",
        "problem_or_desire": "Why did yields spike?",
        "audience_hypothesis": "macro traders",
        "evidence_available": True,
        "owner_department": "intelligence",
    }
    accounts = [
        {"id": "flagship", "kind": "branded", "beat": "What changed and why", "corpus": "full"},
        {"id": "research_a", "kind": "generic", "beat": "Macro explainer", "corpus": "macro"},
    ]
    c = compile_campaign(opp, accounts)
    assert c.campaign_id == "cmp-opp-t1"
    assert len(c.asset_plan) == 2
    # Variant texts must be distinct
    variants = [item["variant_promise"] for item in c.asset_plan]
    from engine.marketing.campaign_compiler import distinctness
    d = distinctness(variants)
    assert d["flags"] == 0


# ---------------------------------------------------------------------------
# 6. Economics formula subtracts all cost terms
# ---------------------------------------------------------------------------

def test_retained_contribution_formula():
    from engine.marketing.economics import retained_contribution
    cohort = {
        "recognized_revenue": 1000.0,
        "fees": 30.0,
        "refunds": 50.0,
        "chargebacks": 10.0,
        "creator_payout": 40.0,
        "referral_payout": 20.0,
        "paid_media_cost": 100.0,
        "model_inference_cost": 25.0,
        "data_delivery_cost": 15.0,
        "support_cost": 10.0,
    }
    expected = 1000 - 30 - 50 - 10 - 40 - 20 - 100 - 25 - 15 - 10
    assert retained_contribution(cohort) == pytest.approx(expected, abs=0.01)


def test_retained_contribution_negative_possible():
    """A cohort with costs > revenue should return negative."""
    from engine.marketing.economics import retained_contribution
    cohort = {
        "recognized_revenue": 10.0,
        "paid_media_cost": 500.0,
    }
    assert retained_contribution(cohort) < 0


def test_economics_formula_string():
    from engine.marketing.economics import FORMULA
    # Must mention all cost components
    for term in ["fees", "refunds", "payouts", "paid media", "inference", "data/delivery", "support"]:
        assert term in FORMULA, f"Formula missing term: {term!r}"


def test_cohort_summary():
    from engine.marketing.economics import cohort_summary, retained_contribution
    cohorts = [
        {"recognized_revenue": 100.0, "fees": 10.0},
        {"recognized_revenue": 200.0, "fees": 20.0},
    ]
    summary = cohort_summary(cohorts)
    expected_total = sum(retained_contribution(c) for c in cohorts)
    assert summary["count"] == 2
    assert summary["total_retained_contribution"] == pytest.approx(expected_total, abs=0.01)


# ---------------------------------------------------------------------------
# 7. Self-deception checks all present
# ---------------------------------------------------------------------------

def test_self_deception_checks_count():
    from engine.marketing.cmo import self_deception_checks
    checks = self_deception_checks()
    assert len(checks) == 8


def test_self_deception_checks_all_enforced():
    from engine.marketing.cmo import self_deception_checks
    checks = self_deception_checks()
    for c in checks:
        assert c.get("status") == "enforced", (
            f"Check {c.get('name')} has status {c.get('status')!r}, expected enforced"
        )


def test_self_deception_checks_required_names():
    from engine.marketing.cmo import self_deception_checks
    checks = self_deception_checks()
    names = {c["name"] for c in checks}
    required = {
        "no_training_on_unverified_attribution",
        "no_delete_losing_cells",
        "no_relabel_failed_metric_as_success",
        "no_self_grading_by_publishing_dept",
        "no_engagement_as_revenue_proxy",
        "no_creator_payout_ignoring_refunds",
        "no_marketing_response_changes_market_scores",
        "no_authority_widening_on_anomalous_win",
    }
    assert required.issubset(names), f"Missing checks: {required - names}"


# ---------------------------------------------------------------------------
# 8. Growth event taxonomy non-empty
# ---------------------------------------------------------------------------

def test_growth_events_non_empty():
    from engine.marketing.events import GROWTH_EVENTS
    assert len(GROWTH_EVENTS) >= 26  # docket lists 26 events


def test_growth_events_has_full_taxonomy():
    from engine.marketing.events import GROWTH_EVENTS
    required = [
        "landing_view", "public_object_view", "account_created",
        "preview_started", "subscription_created", "invoice_paid",
        "cancellation", "refund", "referral_converted",
    ]
    for ev in required:
        assert ev in GROWTH_EVENTS, f"Missing event: {ev}"


def test_spine_returns_dict():
    from engine.marketing.events import spine
    s = spine()
    assert isinstance(s["instrumented"], list)
    assert len(s["instrumented"]) > 0
    assert s["observed"] == 0


# ---------------------------------------------------------------------------
# 9. Governor build_and_write writes both artifacts with envelope keys
# ---------------------------------------------------------------------------

def test_governor_writes_both_artifacts(tmp_path):
    """Run the governor with a temp root and verify both artifacts are written."""
    # Create minimal directory structure
    (tmp_path / "config").mkdir()
    (tmp_path / "data" / "marketing").mkdir(parents=True)
    (tmp_path / "data" / "neuralweb").mkdir(parents=True)
    (tmp_path / "site" / "neuralwebdata").mkdir(parents=True)

    # Copy config
    import shutil
    cfg_src = ROOT / "config" / "marketing.yml"
    shutil.copy(cfg_src, tmp_path / "config" / "marketing.yml")

    # Copy seed ledgers
    for name in [
        "opportunities.jsonl", "campaigns.jsonl", "publications.jsonl",
        "growth_events.jsonl", "experiments.jsonl", "department_changes.jsonl",
        "corrections.jsonl", "claims.jsonl",
    ]:
        src = ROOT / "data" / "marketing" / name
        if src.exists():
            shutil.copy(src, tmp_path / "data" / "marketing" / name)

    # Run governor (envelope stamp may fail on test root without synapse.yml)
    from engine.neuralweb.marketing_governor import build_and_write
    result = build_and_write(root=tmp_path)

    state_path = tmp_path / "data" / "neuralweb" / "marketing_state.json"
    lobe_path = tmp_path / "site" / "neuralwebdata" / "marketing_lobe.json"

    assert state_path.exists(), f"marketing_state.json not written: {result}"
    assert lobe_path.exists(), f"marketing_lobe.json not written: {result}"

    state = json.loads(state_path.read_text())
    lobe = json.loads(lobe_path.read_text())

    # Must have envelope keys
    envelope_keys = {"schema_version", "produced_by", "produced_at", "inputs_hash", "tier"}
    for k in envelope_keys:
        assert k in state, f"state missing envelope key: {k}"
        assert k in lobe, f"lobe missing envelope key: {k}"

    # Schema ids
    assert state.get("schema") == "marketing.state/v1"
    assert lobe.get("schema") == "marketing.lobe/v1"


def test_governor_public_safe_subset_excludes_budgets(tmp_path):
    """marketing_lobe.json must not contain budgets or internal scorecards."""
    import shutil
    (tmp_path / "config").mkdir()
    (tmp_path / "data" / "marketing").mkdir(parents=True)
    (tmp_path / "data" / "neuralweb").mkdir(parents=True)
    (tmp_path / "site" / "neuralwebdata").mkdir(parents=True)

    cfg_src = ROOT / "config" / "marketing.yml"
    shutil.copy(cfg_src, tmp_path / "config" / "marketing.yml")

    from engine.neuralweb.marketing_governor import build_and_write
    build_and_write(root=tmp_path)

    lobe_path = tmp_path / "site" / "neuralwebdata" / "marketing_lobe.json"
    lobe = json.loads(lobe_path.read_text())

    # Public-safe: no budget fields
    lobe_text = json.dumps(lobe)
    assert "envelope_usd" not in lobe_text, "lobe must not expose budget amounts"
    assert "scorecard" not in lobe_text, "lobe must not expose internal scorecards"
    assert "handle" not in lobe_text, "lobe must not expose desk handles"

    # Departments in lobe must be public-safe subset
    for d in lobe.get("departments", []):
        assert set(d.keys()) == {"id", "name", "lifecycle_state", "wave"}, (
            f"dept {d.get('id')} has unexpected keys in lobe: {set(d.keys())}"
        )


# ---------------------------------------------------------------------------
# 10. Seed ledgers round-trip
# ---------------------------------------------------------------------------

def test_seed_opportunities_roundtrip():
    from engine.marketing.ledgers import read_jsonl
    opps = read_jsonl(ROOT / "data" / "marketing" / "opportunities.jsonl")
    assert len(opps) >= 1
    # All seed rows have mode=shadow and id prefix seed-
    for o in opps:
        assert o.get("mode") == "shadow", f"opportunity {o.get('opportunity_id')} not shadow"
        assert o.get("opportunity_id", "").startswith("seed-"), (
            f"non-seed id found: {o.get('opportunity_id')}"
        )


def test_seed_claims_roundtrip():
    from engine.marketing.ledgers import read_jsonl
    claims = read_jsonl(ROOT / "data" / "marketing" / "claims.jsonl")
    assert len(claims) >= 1
    for c in claims:
        assert "claim_id" in c
        assert "exact_claim" in c
        assert c.get("mode") == "shadow"


def test_ledger_append_and_tail(tmp_path):
    from engine.marketing.ledgers import append_jsonl, tail, read_jsonl
    p = tmp_path / "test.jsonl"
    for i in range(5):
        append_jsonl(p, {"idx": i, "v": f"row{i}"})
    rows = read_jsonl(p)
    assert len(rows) == 5
    last2 = tail(p, 2)
    assert len(last2) == 2
    assert last2[-1]["idx"] == 4


def test_ledger_read_missing_returns_empty(tmp_path):
    from engine.marketing.ledgers import read_jsonl
    rows = read_jsonl(tmp_path / "nonexistent.jsonl")
    assert rows == []


# ---------------------------------------------------------------------------
# Additional: provenance and claims
# ---------------------------------------------------------------------------

def test_provenance_modes():
    from engine.marketing.provenance import MODES
    assert set(MODES) == {"neural_web", "marketing_original", "hybrid"}


def test_source_packet_validation():
    from engine.marketing.provenance import SourcePacket, validate
    bad = SourcePacket(packet_id="", provenance_mode="unknown", created_by="x", created_at="2026-07-18T00:00:00Z")
    problems = validate(bad)
    assert any("provenance_mode" in p for p in problems)
    assert any("packet_id" in p for p in problems)


def test_claims_summarize():
    from engine.marketing.claims import summarize
    claims = [
        {"claim_id": "c1", "status": "open"},
        {"claim_id": "c2", "status": "resolved"},
        {"claim_id": "c3", "status": "open"},
    ]
    s = summarize(claims)
    assert s["total"] == 3
    assert s["open"] == 2
    assert s["resolved"] == 1


# ---------------------------------------------------------------------------
# Additional: department formation gate
# ---------------------------------------------------------------------------

def test_dept_formation_gate_approved():
    from engine.marketing.cmo import department_formation_gate
    item = {
        "id": "new_dept",
        "distinct_objective": True,
        "no_existing_dept_can_absorb": True,
        "positive_expected_option_value": True,
        "no_unresolved_conflict": True,
        "has_budget_assigned": True,
        "has_retirement_test": True,
    }
    result = department_formation_gate([item])
    assert "new_dept" in result["approved"]
    assert result["rejected"] == []


def test_dept_formation_gate_rejected():
    from engine.marketing.cmo import department_formation_gate
    item = {
        "id": "bad_dept",
        "distinct_objective": False,
        "no_existing_dept_can_absorb": True,
        "positive_expected_option_value": True,
        "no_unresolved_conflict": True,
        "has_budget_assigned": True,
        "has_retirement_test": True,
    }
    result = department_formation_gate([item])
    assert len(result["rejected"]) == 1
    assert result["rejected"][0]["id"] == "bad_dept"
