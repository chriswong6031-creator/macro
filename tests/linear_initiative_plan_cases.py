from __future__ import annotations

from collections import Counter
from copy import deepcopy
import importlib
import importlib.util
import json
from pathlib import Path

import pytest


REPO = Path(__file__).resolve().parents[1]
STRATEGY_PATH = REPO / "config" / "linear_initiative_portfolio.v1.json"

EXPECTED_INITIATIVES = {
    "canonical-intelligence-substrate-learning": ("Canonical Intelligence Substrate & Learning", 2),
    "legendary-alpha-discovery-timing": ("Legendary Alpha Discovery & Timing", 1),
    "institutional-company-event-intelligence": ("Institutional Company & Event Intelligence", 2),
    "global-markets-regimes-risk-command": ("Global Markets, Regimes & Risk Command", 2),
    "personal-institutional-desk": ("Personal Institutional Desk", 1),
    "trusted-production-customer-platform": ("Trusted Production & Customer Platform", 2),
    "autonomous-ai-organization": ("Autonomous AI Organization", 1),
}

EXPECTED_MEMBERSHIPS = {
    "WS:ALPHA-INTELLIGENCE-INTEGRATION": "canonical-intelligence-substrate-learning",
    "WS:GMI-THEME-GRAPH": "canonical-intelligence-substrate-learning",
    "WS:STOCK-IDENTITY": "canonical-intelligence-substrate-learning",
    "WS:MARKET-MEMORY-W2C": "canonical-intelligence-substrate-learning",
    "WS:MASSIVE-STOCK-DAY-R2-COHERENCE": "canonical-intelligence-substrate-learning",
    "WS:EVAL-OS-MEASUREMENT-LAW": "canonical-intelligence-substrate-learning",
    "WS:EVAL-OS-EVIDENCE-VIEW": "canonical-intelligence-substrate-learning",
    "WS:EVAL-OS-T1-ENGINE-REGISTRY": "canonical-intelligence-substrate-learning",
    "WS:EVAL-OS-OUTPUT-HEALTH": "canonical-intelligence-substrate-learning",
    "WS:ADVANCED-DATA-OPTIONS": "legendary-alpha-discovery-timing",
    "WS:OPTIONS-ALPHA-INTELLIGENCE-RECOVERY": "legendary-alpha-discovery-timing",
    "WS:INTRADAY-FLOW-P0-RECOVERY": "legendary-alpha-discovery-timing",
    "WS:OPTIONS-CONTEXT-AUDIT-PREREG-V2": "legendary-alpha-discovery-timing",
    "WS:CHINA-ALPHA-INTELLIGENCE": "legendary-alpha-discovery-timing",
    "WS:CN-LIMIT-ALPHA": "legendary-alpha-discovery-timing",
    "WS:PROPHET-CONDITIONAL-FUSION": "legendary-alpha-discovery-timing",
    "WS:PROPHET-HK-CA-REVAMP": "legendary-alpha-discovery-timing",
    "WS:PROPHET-US-AVAILABILITY": "legendary-alpha-discovery-timing",
    "WS:PROPHET-US-ENTRY-TIMING": "legendary-alpha-discovery-timing",
    "WS:PROPHET-US-V4-RECOVERY": "legendary-alpha-discovery-timing",
    "WS:LIVE-ENTRY-RADAR": "legendary-alpha-discovery-timing",
    "WS:BREATHING-PLATFORM": "legendary-alpha-discovery-timing",
    "WS:TOP-ANATOMY": "legendary-alpha-discovery-timing",
    "WS:EARNINGS-EVENT-INTELLIGENCE-COMPILER": "institutional-company-event-intelligence",
    "WS:FINANCIAL-INTELLIGENCE-FABRIC": "institutional-company-event-intelligence",
    "WS:CALCBENCH-FILING-FORENSICS-PARITY": "institutional-company-event-intelligence",
    "WS:CAPITAL-STRUCTURE-INTELLIGENCE-V2": "institutional-company-event-intelligence",
    "WS:DEFENSE-PROCUREMENT-V3": "institutional-company-event-intelligence",
    "WS:BPC-JV-RECON": "institutional-company-event-intelligence",
    "WS:CN-SOE-DEMAND": "institutional-company-event-intelligence",
    "WS:BIOCATALYST-CORE-PRODUCT": "institutional-company-event-intelligence",
    "WS:BIOCATALYST-RECOVERY-V2": "institutional-company-event-intelligence",
    "WS:EARNINGS-INTELLIGENCE-OS": "institutional-company-event-intelligence",
    "WS:FUNDAMENTAL-FORENSICS": "institutional-company-event-intelligence",
    "WS:RATES-INFLATION-COMMAND": "global-markets-regimes-risk-command",
    "WS:MACRO-CONTEXT-INDEX": "global-markets-regimes-risk-command",
    "WS:GREY-DEER-RISK-INTELLIGENCE": "global-markets-regimes-risk-command",
    "WS:CRYPTO-INTELLIGENCE": "global-markets-regimes-risk-command",
    "WS:CYCLE-PATTERN-ISSUER-MECHANISM": "global-markets-regimes-risk-command",
    "WS:MARKET-OS": "personal-institutional-desk",
    "WS:STOCK-DOSSIER-LIVE-QUOTE": "personal-institutional-desk",
    "WS:INSTITUTIONAL-PRODUCT-EXPERIENCE-V2": "personal-institutional-desk",
    "WS:ACCOUNT-IDENTITY-HARDENING": "trusted-production-customer-platform",
    "WS:CUSTOMER-DATA-BACKUP": "trusted-production-customer-platform",
    "WS:COMMERCIAL-PATH-ALERTING": "trusted-production-customer-platform",
    "WS:CI-MERGE-CONTROL-PLANE": "trusted-production-customer-platform",
    "WS:RUNNER-FLEET-RESILIENCE": "trusted-production-customer-platform",
    "WS:AGENT-OS": "autonomous-ai-organization",
    "WS:CHAIRMAN-CONTROL-ROOM": "autonomous-ai-organization",
    "WS:EXECUTIVE-CAPACITY-FABRIC": "autonomous-ai-organization",
}

EXPECTED_EXCEPTIONS = {
    ("workstream_key", "WS:WATCHLIST-PORTFOLIO-CEO", "compatibility_redirect"),
    ("linear_project_id", "9aef6461-306a-4a3c-911b-c6a4b6635a78", "canonical_parent_unresolved"),
}

HISTORICAL_KEYS = {
    "WS:EVAL-OS-T1-ENGINE-REGISTRY",
    "WS:EVAL-OS-OUTPUT-HEALTH",
    "WS:BIOCATALYST-CORE-PRODUCT",
    "WS:BIOCATALYST-RECOVERY-V2",
    "WS:EARNINGS-INTELLIGENCE-OS",
    "WS:FUNDAMENTAL-FORENSICS",
    "WS:INSTITUTIONAL-PRODUCT-EXPERIENCE-V2",
}


def _lip():
    spec = importlib.util.find_spec("scripts.linear_initiative_plan")
    assert spec is not None, "Task 1 RED: scripts.linear_initiative_plan is not implemented yet"
    return importlib.import_module("scripts.linear_initiative_plan")


def _project_plan(*, active_keys=(), excluded_keys=()):
    return {
        "schema": "linear_portfolio_plan.v1",
        "active_projects": [{"workstream_key": key} for key in active_keys],
        "review_candidates": [],
        "excluded_projects": [{"workstream_key": key} for key in excluded_keys],
    }


def _full_project_plan():
    active = sorted((set(EXPECTED_MEMBERSHIPS) - HISTORICAL_KEYS) | {"WS:WATCHLIST-PORTFOLIO-CEO"})
    excluded = sorted(HISTORICAL_KEYS)

    def row(key, status_class):
        return {
            "workstream_key": key,
            "desired_project_name": f"{key} — fixture",
            "desired_project_summary": f"fixture summary for {key}",
            "desired_project_status_class": status_class,
            "canonical_status": "active" if status_class == "started" else "done",
        }

    return {
        "schema": "linear_portfolio_plan.v1",
        "semantic_hash": "project-plan-fixture-hash",
        "active_projects": [row(key, "started") for key in active],
        "review_candidates": [],
        "excluded_projects": [row(key, "completed") for key in excluded],
        "warnings": [],
    }


def _initiative_id(key):
    return "initiative-" + key


def _snapshot(*, include_initiatives=True):
    strategy = json.loads(STRATEGY_PATH.read_text(encoding="utf-8"))
    initiatives = []
    if include_initiatives:
        for key, row in sorted(strategy["initiatives"].items()):
            initiatives.append(
                {
                    "initiative_id": _initiative_id(key),
                    "name": row["name"],
                    "status": row["status"],
                    "priority": row["priority"],
                    "health": row["health"],
                    "owner_id": row["owner"],
                    "lead_team": row["lead_team"],
                    "target_date": row["target_date"],
                    "labels": list(row["labels"]),
                    "parent_initiative_ids": [],
                }
            )

    projects = []
    for index, (key, initiative_key) in enumerate(sorted(EXPECTED_MEMBERSHIPS.items()), start=1):
        projects.append(
            {
                "project_id": f"project-{index:02d}",
                "workstream_key": key,
                "name": f"{key} — fixture",
                "status_class": "completed" if key in HISTORICAL_KEYS else "started",
                "initiative_ids": [_initiative_id(initiative_key)] if include_initiatives else [],
                "initiative_names": [EXPECTED_INITIATIVES[initiative_key][0]] if include_initiatives else [],
            }
        )

    projects.extend(
        [
            {
                "project_id": "watchlist-project",
                "workstream_key": "WS:WATCHLIST-PORTFOLIO-CEO",
                "name": "WS:WATCHLIST-PORTFOLIO-CEO — compatibility redirect",
                "status_class": "started",
                "initiative_ids": [],
                "initiative_names": [],
            },
            {
                "project_id": "9aef6461-306a-4a3c-911b-c6a4b6635a78",
                "workstream_key": None,
                "name": "Mastermind-X Linear OS",
                "status_class": "started",
                "initiative_ids": [],
                "initiative_names": [],
            },
        ]
    )
    return {
        "schema": "linear_initiative_snapshot.v1",
        "source": {"authority": "witness_only_not_canonical"},
        "initiatives": initiatives,
        "projects": projects,
    }


def _write_snapshot(tmp_path, snapshot):
    path = tmp_path / "linear_snapshot.json"
    path.write_text(json.dumps(snapshot, sort_keys=True), encoding="utf-8")
    return path


def _codes(plan):
    return {row["code"] for row in plan["drift"]}


def test_strategy_file_has_frozen_v1_shape():
    lip = _lip()
    strategy = lip.load_strategy(STRATEGY_PATH)
    assert strategy["schema"] == lip.STRATEGY_SCHEMA
    assert set(strategy["initiatives"]) == set(EXPECTED_INITIATIVES)
    for key, (name, priority) in EXPECTED_INITIATIVES.items():
        row = strategy["initiatives"][key]
        assert row["name"] == name
        assert row["priority"] == priority
        assert row["status"] == "Active"
        assert row["lead_team"] == "MastermindX"
        assert row["owner"] is None
        assert row["target_date"] is None
        assert row["health"] is None
        assert row["labels"] == []
        assert row["parent_initiatives"] == []
        assert row["summary"]
        assert row["outcome"]
        assert row["moat"]
        assert row["completion_ruler"]
        assert row["scope_law"]

    assert strategy["memberships"] == EXPECTED_MEMBERSHIPS
    exceptions = {
        (row["identity_kind"], row["identity"], row["reason"])
        for row in strategy["unassigned_exceptions"]
    }
    assert exceptions == EXPECTED_EXCEPTIONS

    counts = Counter(strategy["memberships"].values())
    assert counts == {
        "canonical-intelligence-substrate-learning": 9,
        "legendary-alpha-discovery-timing": 14,
        "institutional-company-event-intelligence": 11,
        "global-markets-regimes-risk-command": 5,
        "personal-institutional-desk": 3,
        "trusted-production-customer-platform": 5,
        "autonomous-ai-organization": 3,
    }
    assert len(strategy["memberships"]) == 50
    assert "WS:WATCHLIST-PORTFOLIO-CEO" not in strategy["memberships"]


def test_validate_strategy_accepts_exact_current_universe_shape():
    lip = _lip()
    strategy = lip.load_strategy(STRATEGY_PATH)
    active = sorted((set(EXPECTED_MEMBERSHIPS) - HISTORICAL_KEYS) | {"WS:WATCHLIST-PORTFOLIO-CEO"})
    excluded = sorted(set(EXPECTED_MEMBERSHIPS) - set(active))
    lip.validate_strategy(strategy, _project_plan(active_keys=active, excluded_keys=excluded))


def test_validate_strategy_refuses_unmapped_active_workstream():
    lip = _lip()
    strategy = lip.load_strategy(STRATEGY_PATH)
    with pytest.raises(lip.InitiativePlanError) as exc:
        lip.validate_strategy(strategy, _project_plan(active_keys=["WS:NEW-ACTIVE"]))
    assert "strategy_unmapped_active_workstream" in {row["code"] for row in exc.value.failures}


def test_validate_strategy_refuses_exception_that_is_also_mapped():
    lip = _lip()
    strategy = lip.load_strategy(STRATEGY_PATH)
    mutated = {**strategy, "memberships": {**strategy["memberships"], "WS:WATCHLIST-PORTFOLIO-CEO": "personal-institutional-desk"}}
    with pytest.raises(lip.InitiativePlanError) as exc:
        lip.validate_strategy(mutated, _project_plan(active_keys=["WS:WATCHLIST-PORTFOLIO-CEO"]))
    assert "strategy_exception_also_mapped" in {row["code"] for row in exc.value.failures}


def test_validate_strategy_refuses_unknown_initiative_key():
    lip = _lip()
    strategy = lip.load_strategy(STRATEGY_PATH)
    mutated = {**strategy, "memberships": {**strategy["memberships"], "WS:MARKET-OS": "not-a-real-initiative"}}
    with pytest.raises(lip.InitiativePlanError) as exc:
        lip.validate_strategy(mutated, _project_plan(active_keys=["WS:MARKET-OS"]))
    assert "strategy_unknown_initiative_key" in {row["code"] for row in exc.value.failures}


# Task 2 — desired-state and drift compilation. These tests must go RED before
# production implementation exists; they deliberately exercise no network or writes.


def test_task2_compile_is_deterministic_and_complete(tmp_path):
    lip = _lip()
    project_plan = _full_project_plan()
    snapshot_path = _write_snapshot(tmp_path, _snapshot())
    before = deepcopy(project_plan)

    plan, receipt = lip.compile_initiative_plan(
        project_plan=project_plan,
        strategy_path=STRATEGY_PATH,
        snapshot_path=snapshot_path,
    )
    repeat, _ = lip.compile_initiative_plan(
        project_plan=project_plan,
        strategy_path=STRATEGY_PATH,
        snapshot_path=snapshot_path,
    )

    assert plan["schema"] == "linear_initiative_plan.v1"
    assert len(plan["desired_initiatives"]) == 7
    assert len(plan["desired_memberships"]) == 50
    assert len(plan["unassigned_exceptions"]) == 2
    assert plan["semantic_hash"] == repeat["semantic_hash"]
    assert plan["drift"] == []
    assert plan["hard_blockers"] == []
    assert receipt["initiative_plan_semantic_hash"] == plan["semantic_hash"]
    assert project_plan == before, "Initiative compilation mutated the Project plan"

    counts = Counter(row["initiative_key"] for row in plan["desired_memberships"])
    assert sorted(counts.values()) == [3, 5, 5, 9, 11, 14, 3] or counts == Counter(EXPECTED_MEMBERSHIPS.values())


def test_task2_render_description_is_exact():
    lip = _lip()
    strategy = lip.load_strategy(STRATEGY_PATH)
    row = strategy["initiatives"]["personal-institutional-desk"]
    assert lip.render_description(row) == (
        f"Outcome: {row['outcome']}\n\n"
        f"Moat: {row['moat']}\n\n"
        f"Completion ruler: {row['completion_ruler']}\n\n"
        f"Scope law: {row['scope_law']}"
    )


def test_task2_missing_active_requires_create_but_missing_historical_does_not(tmp_path):
    lip = _lip()
    snapshot = _snapshot()
    snapshot["projects"] = [
        row for row in snapshot["projects"]
        if row["workstream_key"] not in {"WS:TOP-ANATOMY", "WS:EVAL-OS-OUTPUT-HEALTH"}
    ]
    plan, _ = lip.compile_initiative_plan(
        project_plan=_full_project_plan(),
        strategy_path=STRATEGY_PATH,
        snapshot_path=_write_snapshot(tmp_path, snapshot),
    )
    create_keys = {
        row["workstream_key"]
        for row in plan["drift"]
        if row["code"] == "project_create_required"
    }
    assert "WS:TOP-ANATOMY" in create_keys
    assert "WS:EVAL-OS-OUTPUT-HEALTH" not in create_keys


def test_task2_linear_os_exception_is_exact_id_not_fuzzy_name(tmp_path):
    lip = _lip()
    snapshot = _snapshot()
    snapshot["projects"].append(
        {
            "project_id": "wrong-linear-os-id",
            "workstream_key": None,
            "name": "Mastermind-X Linear OS",
            "status_class": "started",
            "initiative_ids": [],
            "initiative_names": [],
        }
    )
    plan, _ = lip.compile_initiative_plan(
        project_plan=_full_project_plan(),
        strategy_path=STRATEGY_PATH,
        snapshot_path=_write_snapshot(tmp_path, snapshot),
    )
    assert any(
        row["code"] == "unmapped_visible_project" and row.get("project_id") == "wrong-linear-os-id"
        for row in plan["drift"]
    )


def test_task2_watchlist_redirect_remains_unassigned(tmp_path):
    lip = _lip()
    plan, _ = lip.compile_initiative_plan(
        project_plan=_full_project_plan(),
        strategy_path=STRATEGY_PATH,
        snapshot_path=_write_snapshot(tmp_path, _snapshot()),
    )
    assert "WS:WATCHLIST-PORTFOLIO-CEO" not in {
        row["workstream_key"] for row in plan["desired_memberships"]
    }
    assert not any(
        row["code"] == "unmapped_visible_project"
        and row.get("workstream_key") == "WS:WATCHLIST-PORTFOLIO-CEO"
        for row in plan["drift"]
    )


@pytest.mark.parametrize(
    ("mutation", "expected_code"),
    [
        ("initiative_missing", "initiative_missing"),
        ("unexpected_initiative", "unexpected_initiative"),
        ("initiative_field_drift", "initiative_field_drift"),
        ("initiative_name_ambiguous", "initiative_name_ambiguous"),
        ("project_binding_missing", "project_binding_missing"),
        ("project_binding_ambiguous", "project_binding_ambiguous"),
        ("membership_missing", "membership_missing"),
        ("membership_wrong", "membership_wrong"),
        ("membership_multi_parent", "membership_multi_parent"),
        ("exception_has_forbidden_membership", "exception_has_forbidden_membership"),
        ("unmapped_visible_project", "unmapped_visible_project"),
    ],
)
def test_task2_drift_vocabulary_is_load_bearing(tmp_path, mutation, expected_code):
    lip = _lip()
    snapshot = _snapshot()
    desired_key = "canonical-intelligence-substrate-learning"
    desired_name = EXPECTED_INITIATIVES[desired_key][0]
    desired_project = next(
        row for row in snapshot["projects"]
        if row["workstream_key"] == "WS:ALPHA-INTELLIGENCE-INTEGRATION"
    )

    if mutation == "initiative_missing":
        snapshot["initiatives"] = [row for row in snapshot["initiatives"] if row["name"] != desired_name]
    elif mutation == "unexpected_initiative":
        snapshot["initiatives"].append(
            {
                "initiative_id": "unexpected-id",
                "name": "Unexpected Initiative",
                "status": "Active",
                "priority": 2,
                "health": None,
                "owner_id": None,
                "lead_team": "MastermindX",
                "target_date": None,
                "labels": [],
                "parent_initiative_ids": [],
            }
        )
    elif mutation == "initiative_field_drift":
        next(row for row in snapshot["initiatives"] if row["name"] == desired_name)["priority"] = 4
    elif mutation == "initiative_name_ambiguous":
        duplicate = deepcopy(next(row for row in snapshot["initiatives"] if row["name"] == desired_name))
        duplicate["initiative_id"] = "duplicate-initiative-id"
        snapshot["initiatives"].append(duplicate)
    elif mutation == "project_binding_missing":
        desired_project["project_id"] = None
    elif mutation == "project_binding_ambiguous":
        duplicate = deepcopy(desired_project)
        duplicate["project_id"] = "duplicate-project-id"
        snapshot["projects"].append(duplicate)
    elif mutation == "membership_missing":
        desired_project["initiative_ids"] = []
        desired_project["initiative_names"] = []
    elif mutation == "membership_wrong":
        desired_project["initiative_ids"] = [_initiative_id("legendary-alpha-discovery-timing")]
        desired_project["initiative_names"] = [EXPECTED_INITIATIVES["legendary-alpha-discovery-timing"][0]]
    elif mutation == "membership_multi_parent":
        desired_project["initiative_ids"] = [
            _initiative_id(desired_key),
            _initiative_id("legendary-alpha-discovery-timing"),
        ]
        desired_project["initiative_names"] = [
            desired_name,
            EXPECTED_INITIATIVES["legendary-alpha-discovery-timing"][0],
        ]
    elif mutation == "exception_has_forbidden_membership":
        watchlist = next(row for row in snapshot["projects"] if row["workstream_key"] == "WS:WATCHLIST-PORTFOLIO-CEO")
        watchlist["initiative_ids"] = [_initiative_id("personal-institutional-desk")]
        watchlist["initiative_names"] = [EXPECTED_INITIATIVES["personal-institutional-desk"][0]]
    elif mutation == "unmapped_visible_project":
        snapshot["projects"].append(
            {
                "project_id": "unmapped-project-id",
                "workstream_key": "WS:UNMAPPED-VISIBLE",
                "name": "WS:UNMAPPED-VISIBLE — visible",
                "status_class": "started",
                "initiative_ids": [],
                "initiative_names": [],
            }
        )

    plan, _ = lip.compile_initiative_plan(
        project_plan=_full_project_plan(),
        strategy_path=STRATEGY_PATH,
        snapshot_path=_write_snapshot(tmp_path, snapshot),
    )
    assert expected_code in _codes(plan)


def test_task2_hard_apply_blockers_are_explicit(tmp_path):
    lip = _lip()
    snapshot = _snapshot()
    snapshot["initiatives"].append(deepcopy(snapshot["initiatives"][0]))
    snapshot["initiatives"][-1]["initiative_id"] = "ambiguous-copy"
    snapshot["projects"].append(
        {
            "project_id": "unmapped-project-id",
            "workstream_key": "WS:UNMAPPED-VISIBLE",
            "name": "WS:UNMAPPED-VISIBLE — visible",
            "status_class": "started",
            "initiative_ids": [],
            "initiative_names": [],
        }
    )
    plan, _ = lip.compile_initiative_plan(
        project_plan=_full_project_plan(),
        strategy_path=STRATEGY_PATH,
        snapshot_path=_write_snapshot(tmp_path, snapshot),
    )
    blocker_codes = {row["code"] for row in plan["hard_blockers"]}
    assert "initiative_name_ambiguous" in blocker_codes
    assert "unmapped_visible_project" in blocker_codes


WATCHLIST_EXCEPTION_KEY = "WS:WATCHLIST-PORTFOLIO-CEO"
CI_MANIFEST_PATH = REPO / ".github" / "ci" / "legacy-jobs.yml"
AGENT_OS_OWNER_JOB = "self-mod-fence"
AGENT_OS_RECORD_STEP_PREFIX = "agent-os record contract"
INITIATIVE_OWNED_PATHS = (
    "scripts/linear_initiative_plan.py",
    "config/linear_initiative_portfolio.v1.json",
    "tests/linear_initiative_plan_cases.py",
    "tests/linear_initiative_plan_live_cases.py",
)


def _agent_os_owner_job():
    import yaml

    manifest = yaml.safe_load(CI_MANIFEST_PATH.read_text(encoding="utf-8"))
    return manifest, manifest["jobs"][AGENT_OS_OWNER_JOB]


@pytest.mark.parametrize("live_health", ["onTrack", "atRisk", "offTrack"])
def test_task2_lawful_later_health_update_is_not_structural_drift(tmp_path, live_health):
    """Health is unset at creation; a later formal Sol update may set it.

    Blocker 1: the compiler compared live `health` to the strategy's creation-time
    `null`, so any lawful later On track / At risk / Off track update surfaced as
    `initiative_field_drift`. Health is descriptive, not structural.
    """
    lip = _lip()
    snapshot = _snapshot()
    desired_key = "legendary-alpha-discovery-timing"
    desired_name = EXPECTED_INITIATIVES[desired_key][0]
    live = next(row for row in snapshot["initiatives"] if row["name"] == desired_name)
    assert live["health"] is None, "fixture must start from the creation-time null"
    live["health"] = live_health

    plan, _ = lip.compile_initiative_plan(
        project_plan=_full_project_plan(),
        strategy_path=STRATEGY_PATH,
        snapshot_path=_write_snapshot(tmp_path, snapshot),
    )

    desired = next(
        row for row in plan["desired_initiatives"]
        if row["initiative_key"] == desired_key
    )
    assert desired["health"] is None, "creation desired state must still emit health=null"

    assert not any(
        row["code"] == "initiative_field_drift" and row.get("initiative_key") == desired_key
        for row in plan["drift"]
    ), f"lawful later health={live_health!r} must not read as structural drift"


def test_task2_health_exemption_does_not_blind_real_field_drift(tmp_path):
    """Discriminating proof: exempting health must not exempt its neighbours."""
    lip = _lip()
    snapshot = _snapshot()
    desired_key = "legendary-alpha-discovery-timing"
    desired_name = EXPECTED_INITIATIVES[desired_key][0]
    live = next(row for row in snapshot["initiatives"] if row["name"] == desired_name)
    live["health"] = "atRisk"
    live["priority"] = 4

    plan, _ = lip.compile_initiative_plan(
        project_plan=_full_project_plan(),
        strategy_path=STRATEGY_PATH,
        snapshot_path=_write_snapshot(tmp_path, snapshot),
    )

    rows = [
        row for row in plan["drift"]
        if row["code"] == "initiative_field_drift" and row.get("initiative_key") == desired_key
    ]
    assert len(rows) == 1, "a real structural change must still be reported"
    assert rows[0]["fields"] == ["priority"], "health must not appear in structural fields"


def test_task2_duplicate_watchlist_exception_is_hard_binding_ambiguity(tmp_path):
    """Blocker 2: exact WS identity stays unique even for an unassigned exception.

    The exception loop consumed each visible project independently, so two Projects
    carrying the exact same exception workstream key both passed silently.
    """
    lip = _lip()

    clean_plan, _ = lip.compile_initiative_plan(
        project_plan=_full_project_plan(),
        strategy_path=STRATEGY_PATH,
        snapshot_path=_write_snapshot(tmp_path, _snapshot()),
    )
    assert not any(
        row["code"] == "project_binding_ambiguous"
        and row.get("workstream_key") == WATCHLIST_EXCEPTION_KEY
        for row in clean_plan["drift"]
    ), "a single lawful watchlist redirect must stay clean"

    snapshot = _snapshot()
    duplicate = deepcopy(
        next(
            row for row in snapshot["projects"]
            if row["workstream_key"] == WATCHLIST_EXCEPTION_KEY
        )
    )
    duplicate["project_id"] = "watchlist-project-duplicate"
    # Deliberately a different display name: identity is the exact workstream key,
    # never the title, so a rename must not launder the duplicate.
    duplicate["name"] = "Watchlist (CEO) — second copy"
    snapshot["projects"].append(duplicate)

    plan, _ = lip.compile_initiative_plan(
        project_plan=_full_project_plan(),
        strategy_path=STRATEGY_PATH,
        snapshot_path=_write_snapshot(tmp_path, snapshot),
    )

    rows = [
        row for row in plan["drift"]
        if row["code"] == "project_binding_ambiguous"
        and row.get("workstream_key") == WATCHLIST_EXCEPTION_KEY
    ]
    assert len(rows) == 1, "duplicate exact watchlist identity must refuse exactly once"
    assert rows[0]["count"] == 2
    assert rows[0] in plan["hard_blockers"], "exact-binding ambiguity must fail closed"


def test_task2_initiative_suites_are_owned_by_agent_os_record_contract_job():
    """Blocker 3: durable CI ownership, not incidental aggregate collection."""
    manifest, job = _agent_os_owner_job()

    owned = set(job["paths"])
    missing = [path for path in INITIATIVE_OWNED_PATHS if path not in owned]
    assert not missing, f"no durable CI path ownership for: {missing}"

    step = next(
        row for row in job["steps"]
        if isinstance(row.get("name"), str)
        and row["name"].startswith(AGENT_OS_RECORD_STEP_PREFIX)
    )
    run = step["run"]
    for suite in (
        "tests/linear_initiative_plan_cases.py",
        "tests/linear_initiative_plan_live_cases.py",
    ):
        assert suite in run, f"{suite} is not invoked by the Agent OS record-contract step"

    # The record-contract step is ordered last on purpose: it must never be able to
    # return nonzero ahead of a fence step and blind the self-mod fence.
    assert job["steps"][-1] is step, "record-contract step must remain ordered last"

    # One CI plane only — no Initiative-specific job may be introduced.
    assert not [key for key in manifest["jobs"] if "initiative" in key.lower()]

    portfolio_source = (REPO / "tests" / "linear_portfolio_plan_live_cases.py").read_text(
        encoding="utf-8"
    )
    for hack in (
        "linear_initiative_plan_cases import *",
        "linear_initiative_plan_live_cases import *",
    ):
        assert hack not in portfolio_source, "import aggregation hack must be removed"
