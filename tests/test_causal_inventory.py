"""tests/test_causal_inventory.py — CHF-R4 causal constitution + feature inventory tests.

All correctness tests are hermetic (tmp_path roots, no network, no real repo
data required).  The non-hermetic smoke test is marked to skip gracefully
when real repo data is absent.

Test coverage:
1. priors_schema_valid          — valid priors passes validate_priors with no errors
2. priors_missing_section       — priors without 'tiers' fails validate_priors
3. priors_missing_lag_key       — priors without daily_engine key fails
4. priors_missing_kill_mask     — priors without kill_mask.compiled fails
5. forbidden_role_candidate_cause — fwd_* feature cannot carry candidate_cause
6. forbidden_future_only_target — forbidden_future feature → only target allowed
7. min_lag_weekly               — weekly-cadence feature gets min_lag_days=5
8. min_lag_daily                — daily-cadence feature gets min_lag_days=1
9. absent_file_honest           — present=False when file absent; builder exits 0
10. kill_mask_deterministic     — compile_kill_mask sorts deterministically
11. kill_mask_sync_true         — compiled section matching regeneration → True
12. kill_mask_sync_false        — mismatched compiled section → False
13. authority_block_frozen      — all authority booleans are False
14. smoke_test_real_repo        — (non-hermetic) builder runs on real repo data
"""
from __future__ import annotations

import json
import textwrap
from pathlib import Path

import pytest
import yaml

# ---------------------------------------------------------------------------
# Module under test
# ---------------------------------------------------------------------------

import sys
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from engine.neuralweb.causal_inventory import (  # noqa: E402
    build_inventory,
    compile_kill_mask,
    kill_mask_in_sync,
    load_priors,
    validate_priors,
    _matches_forbidden,
    _build_feature_entry,
    _validate_feature_roles,
    FEATURE_SOURCES,
    _AUTHORITY,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_MINIMAL_VALID_PRIORS: dict = {
    "schema": "causal_priors.v1",
    "tiers": [
        {"name": "macro_plumbing", "tier_rule": "top tier"},
        {"name": "fire_outcome", "tier_rule": "outcome only"},
    ],
    "min_lag_days_by_cadence": {
        "weekly_publication": 5,
        "daily_engine": 1,
        "monthly_grain": 21,
    },
    "forbidden_causes": [
        {"pattern": "fwd_", "reason": "forward outcome", "source_ruling": "RUL-CC-2"},
        {"pattern": "board_rank", "reason": "Article-2 surface", "source_ruling": "NW-ART2"},
    ],
    "kill_mask": {
        "curated": [],
        "compiled": [],
    },
}


def _write_priors(tmp_path: Path, priors: dict) -> Path:
    """Write a causal_priors.yml to tmp_path/config/ and return the config dir."""
    cfg_dir = tmp_path / "config"
    cfg_dir.mkdir(parents=True, exist_ok=True)
    priors_file = cfg_dir / "causal_priors.yml"
    priors_file.write_text(yaml.dump(priors), encoding="utf-8")
    return tmp_path


# ---------------------------------------------------------------------------
# 1. Valid priors passes
# ---------------------------------------------------------------------------

def test_priors_schema_valid():
    errors = validate_priors(_MINIMAL_VALID_PRIORS)
    assert errors == [], f"Expected no errors, got: {errors}"


# ---------------------------------------------------------------------------
# 2. Missing 'tiers' section caught
# ---------------------------------------------------------------------------

def test_priors_missing_section():
    bad = {k: v for k, v in _MINIMAL_VALID_PRIORS.items() if k != "tiers"}
    errors = validate_priors(bad)
    assert any("tiers" in e for e in errors), (
        f"Expected error about 'tiers', got: {errors}"
    )


# ---------------------------------------------------------------------------
# 3. Missing daily_engine lag key caught
# ---------------------------------------------------------------------------

def test_priors_missing_lag_key():
    import copy
    bad = copy.deepcopy(_MINIMAL_VALID_PRIORS)
    del bad["min_lag_days_by_cadence"]["daily_engine"]
    errors = validate_priors(bad)
    assert any("daily_engine" in e for e in errors), (
        f"Expected error about 'daily_engine', got: {errors}"
    )


# ---------------------------------------------------------------------------
# 4. Missing kill_mask.compiled caught
# ---------------------------------------------------------------------------

def test_priors_missing_kill_mask_compiled():
    import copy
    bad = copy.deepcopy(_MINIMAL_VALID_PRIORS)
    bad["kill_mask"] = {"curated": []}  # compiled missing
    errors = validate_priors(bad)
    assert any("compiled" in e for e in errors), (
        f"Expected error about 'compiled', got: {errors}"
    )


# ---------------------------------------------------------------------------
# 5. Forbidden-role law: fwd_* feature cannot carry candidate_cause
# ---------------------------------------------------------------------------

def test_forbidden_role_candidate_cause(tmp_path: Path):
    """A feature with fwd_ in feature_id or columns cannot have candidate_cause."""
    root = _write_priors(tmp_path, _MINIMAL_VALID_PRIORS)

    fwd_feature = {
        "feature_id": "fwd_ret_21",
        "family": "outcomes",
        "path": "data/fake/outcomes.parquet",
        "columns": ["fwd_ret_21", "fwd_mdd_21"],
        "producer": "test",
        "cadence": "daily-engine",
        "time_grain": "daily",
        "asof_field": "date",
        "declared_first": "2022-01-01",
        "pit_basis": "recomputed_history",
        "era_coverage": ["2022-07+"],
        "tier": "fire_outcome",
        "allowed_roles": ["candidate_cause", "target"],  # candidate_cause is illegal
        "forbidden_roles": [],
        "collider_risk": "low",
        "notes": "test only",
    }

    forbidden_causes = _MINIMAL_VALID_PRIORS["forbidden_causes"]

    # _matches_forbidden should find the fwd_ pattern
    matched = _matches_forbidden(
        fwd_feature["feature_id"],
        fwd_feature["columns"],
        forbidden_causes,
    )
    assert matched is not None, "Expected fwd_ pattern to match"

    # _validate_feature_roles should report an error
    errors = _validate_feature_roles(fwd_feature, forbidden_causes)
    assert any("candidate_cause" in e for e in errors), (
        f"Expected validation error about candidate_cause, got: {errors}"
    )


# ---------------------------------------------------------------------------
# 6. forbidden_future in allowed_roles → only target permitted
# ---------------------------------------------------------------------------

def test_forbidden_future_only_target():
    feature = {
        "feature_id": "test_fwd_outcome",
        "allowed_roles": ["forbidden_future", "conditioner"],  # conditioner is illegal
        "columns": [],
    }
    errors = _validate_feature_roles(feature, [])
    assert any("forbidden_future" in e and "target" in e for e in errors), (
        f"Expected error about forbidden_future allowing only target, got: {errors}"
    )


def test_forbidden_future_target_only_ok():
    feature = {
        "feature_id": "test_fwd_ok",
        "allowed_roles": ["target"],
        "columns": [],
    }
    errors = _validate_feature_roles(feature, [])
    assert errors == [], f"Expected no errors for target-only, got: {errors}"


# ---------------------------------------------------------------------------
# 7. Weekly-cadence feature gets min_lag_days=5
# ---------------------------------------------------------------------------

def test_min_lag_weekly(tmp_path: Path):
    root = _write_priors(tmp_path, _MINIMAL_VALID_PRIORS)
    # Create a dummy parquet-like path presence (non-parquet, just needs to exist or not)
    src = {
        "feature_id": "test_weekly_feature",
        "family": "test",
        "path": "data/nonexistent/weekly.parquet",
        "columns": ["some_col"],
        "producer": "test",
        "cadence": "weekly",
        "time_grain": "weekly",
        "asof_field": "date",
        "declared_first": "2020-01-01",
        "pit_basis": "pit_live",
        "era_coverage": ["2020-"],
        "tier": "macro_plumbing",
        "allowed_roles": ["candidate_cause"],
        "forbidden_roles": [],
        "collider_risk": "low",
        "notes": "",
    }
    min_lag_by_cadence = _MINIMAL_VALID_PRIORS["min_lag_days_by_cadence"]
    entry = _build_feature_entry(src, root, _MINIMAL_VALID_PRIORS, min_lag_by_cadence)
    assert entry["min_lag_days"] == 5, (
        f"Expected min_lag_days=5 for weekly cadence, got {entry['min_lag_days']}"
    )


# ---------------------------------------------------------------------------
# 8. Daily-cadence feature gets min_lag_days=1
# ---------------------------------------------------------------------------

def test_min_lag_daily(tmp_path: Path):
    root = _write_priors(tmp_path, _MINIMAL_VALID_PRIORS)
    src = {
        "feature_id": "test_daily_feature",
        "family": "test",
        "path": "data/nonexistent/daily.parquet",
        "columns": ["some_col"],
        "producer": "test",
        "cadence": "daily-engine",
        "time_grain": "daily",
        "asof_field": "date",
        "declared_first": "2020-01-01",
        "pit_basis": "pit_live",
        "era_coverage": ["2020-"],
        "tier": "asset_class",
        "allowed_roles": ["candidate_cause"],
        "forbidden_roles": [],
        "collider_risk": "low",
        "notes": "",
    }
    min_lag_by_cadence = _MINIMAL_VALID_PRIORS["min_lag_days_by_cadence"]
    entry = _build_feature_entry(src, root, _MINIMAL_VALID_PRIORS, min_lag_by_cadence)
    assert entry["min_lag_days"] == 1, (
        f"Expected min_lag_days=1 for daily cadence, got {entry['min_lag_days']}"
    )


# ---------------------------------------------------------------------------
# 8b. Monthly-grain feature gets min_lag_days=21 (M4 monthly_grain floor)
# ---------------------------------------------------------------------------

def test_min_lag_monthly(tmp_path: Path):
    """Monthly time_grain (on-demand cadence) routes to monthly_grain floor=21."""
    root = _write_priors(tmp_path, _MINIMAL_VALID_PRIORS)
    src = {
        "feature_id": "test_monthly_feature",
        "family": "test",
        "path": "data/nonexistent/monthly.parquet",
        "columns": ["phase"],
        "producer": "test",
        "cadence": "on-demand",
        "time_grain": "monthly",
        "asof_field": "date",
        "declared_first": "2010-01-01",
        "pit_basis": "recomputed_history",
        "era_coverage": ["2009-16"],
        "tier": "sector_complex",
        "allowed_roles": ["candidate_cause", "conditioner"],
        "forbidden_roles": [],
        "collider_risk": "medium",
        "notes": "",
    }
    min_lag_by_cadence = _MINIMAL_VALID_PRIORS["min_lag_days_by_cadence"]
    entry = _build_feature_entry(src, root, _MINIMAL_VALID_PRIORS, min_lag_by_cadence)
    assert entry["min_lag_days"] == 21, (
        f"Expected min_lag_days=21 for monthly time_grain, got {entry['min_lag_days']}"
    )


# ---------------------------------------------------------------------------
# 8c. cycle_pattern__state_monthly gets min_lag_days=21 via real FEATURE_SOURCES
# ---------------------------------------------------------------------------

def test_cycle_pattern_monthly_lag(tmp_path: Path):
    """cycle_pattern__state_monthly (time_grain=monthly) must have min_lag_days=21."""
    root = _write_priors(tmp_path, _MINIMAL_VALID_PRIORS)
    import engine.neuralweb.causal_inventory as inv_mod
    cycle_src = next(
        s for s in inv_mod.FEATURE_SOURCES
        if s["feature_id"] == "cycle_pattern__state_monthly"
    )
    min_lag_by_cadence = _MINIMAL_VALID_PRIORS["min_lag_days_by_cadence"]
    entry = _build_feature_entry(cycle_src, root, _MINIMAL_VALID_PRIORS, min_lag_by_cadence)
    assert entry["min_lag_days"] == 21, (
        f"cycle_pattern__state_monthly: expected min_lag_days=21, got {entry['min_lag_days']}"
    )


# ---------------------------------------------------------------------------
# 8d. Determinism test — build_inventory twice produces identical output
# ---------------------------------------------------------------------------

def test_build_inventory_deterministic(tmp_path: Path):
    """build_inventory is deterministic: two runs on identical state are equal.

    The 'asof' timestamp is excluded from comparison (it is expected to differ
    by wall-clock time between calls).
    """
    root = _write_priors(tmp_path, _MINIMAL_VALID_PRIORS)
    (tmp_path / "data" / "neuralweb").mkdir(parents=True, exist_ok=True)

    import engine.neuralweb.causal_inventory as inv_mod
    original_sources = inv_mod.FEATURE_SOURCES

    # Use a small deterministic source list for speed
    inv_mod.FEATURE_SOURCES = [
        {
            "feature_id": "test_det_feature",
            "family": "test",
            "path": "data/nonexistent/det.parquet",
            "columns": ["col_a", "col_b"],
            "producer": "test",
            "cadence": "daily-engine",
            "time_grain": "daily",
            "asof_field": "date",
            "declared_first": "2020-01-01",
            "pit_basis": "pit_live",
            "era_coverage": ["2020-"],
            "tier": "asset_class",
            "allowed_roles": ["candidate_cause"],
            "forbidden_roles": [],
            "collider_risk": "low",
            "notes": "determinism check",
        }
    ]

    try:
        run_a = build_inventory(root=root)
        run_b = build_inventory(root=root)
    finally:
        inv_mod.FEATURE_SOURCES = original_sources

    # Remove non-deterministic 'asof' timestamp before comparing
    run_a.pop("asof", None)
    run_b.pop("asof", None)

    assert run_a == run_b, (
        f"build_inventory not deterministic across two runs: "
        f"diff keys: {set(run_a) ^ set(run_b)}"
    )


# ---------------------------------------------------------------------------
# 9. Absent file → present=False; builder still exits 0
# ---------------------------------------------------------------------------

def test_absent_file_honest(tmp_path: Path):
    """build_inventory emits present=False for missing files and does not crash."""
    root = _write_priors(tmp_path, _MINIMAL_VALID_PRIORS)
    # Create the data/neuralweb directory so the output can be written
    (tmp_path / "data" / "neuralweb").mkdir(parents=True, exist_ok=True)

    # Patch FEATURE_SOURCES to use a single absent-file entry
    import engine.neuralweb.causal_inventory as inv_mod
    original_sources = inv_mod.FEATURE_SOURCES
    inv_mod.FEATURE_SOURCES = [
        {
            "feature_id": "test_absent",
            "family": "test",
            "path": "data/does_not_exist/missing.parquet",
            "columns": ["col_a"],
            "producer": "test",
            "cadence": "daily-engine",
            "time_grain": "daily",
            "asof_field": "date",
            "declared_first": "2020-01-01",
            "pit_basis": "pit_live",
            "era_coverage": ["2020-"],
            "tier": "asset_class",
            "allowed_roles": ["candidate_cause"],
            "forbidden_roles": [],
            "collider_risk": "low",
            "notes": "",
        }
    ]

    try:
        payload = build_inventory(root=root)
    finally:
        inv_mod.FEATURE_SOURCES = original_sources

    features = payload.get("features", [])
    assert len(features) == 1
    assert features[0]["present"] is False, (
        f"Expected present=False for absent file, got {features[0]['present']}"
    )
    # gap_notes should mention the absent file
    gap_notes = payload.get("gap_notes", [])
    assert any("absent" in g.lower() for g in gap_notes), (
        f"Expected gap note about absent file, got {gap_notes}"
    )


# ---------------------------------------------------------------------------
# 10. compile_kill_mask is deterministic across shuffled input
# ---------------------------------------------------------------------------

def test_kill_mask_deterministic(tmp_path: Path):
    """compile_kill_mask returns the same sorted list regardless of line order."""
    rows = [
        {"edge_id": "gex->ret", "scanned_at": "2026-07-09", "verdict": "null"},
        {"edge_id": "breadth->ret", "scanned_at": "2026-07-08", "verdict": "null"},
        {"edge_id": "gex->ret", "scanned_at": "2026-07-08", "verdict": "screened_candidate"},
    ]
    # Write in one order
    nulls_dir = tmp_path / "data" / "neuralweb"
    nulls_dir.mkdir(parents=True, exist_ok=True)
    nulls_path = nulls_dir / "causal_nulls.jsonl"
    nulls_path.write_text(
        "\n".join(json.dumps(r) for r in rows), encoding="utf-8"
    )

    result_a = compile_kill_mask(tmp_path)

    # Write in reversed order
    nulls_path.write_text(
        "\n".join(json.dumps(r) for r in reversed(rows)), encoding="utf-8"
    )
    result_b = compile_kill_mask(tmp_path)

    assert result_a == result_b, (
        f"compile_kill_mask not deterministic: {result_a} vs {result_b}"
    )


# ---------------------------------------------------------------------------
# 11. kill_mask_in_sync returns True when committed section matches
# ---------------------------------------------------------------------------

def test_kill_mask_sync_true(tmp_path: Path):
    """kill_mask_in_sync returns True when compiled section matches regeneration."""
    rows = [
        {"edge_id": "a->b", "scanned_at": "2026-07-09", "verdict": "null"},
    ]
    # Write causal_nulls.jsonl
    nulls_dir = tmp_path / "data" / "neuralweb"
    nulls_dir.mkdir(parents=True, exist_ok=True)
    (nulls_dir / "causal_nulls.jsonl").write_text(
        json.dumps(rows[0]), encoding="utf-8"
    )

    # Write priors with compiled section that matches
    import copy
    priors = copy.deepcopy(_MINIMAL_VALID_PRIORS)
    priors["kill_mask"]["compiled"] = rows  # matches what compile_kill_mask returns

    root = _write_priors(tmp_path, priors)
    assert kill_mask_in_sync(root) is True


# ---------------------------------------------------------------------------
# 12. kill_mask_in_sync returns False when committed section mismatches
# ---------------------------------------------------------------------------

def test_kill_mask_sync_false(tmp_path: Path):
    """kill_mask_in_sync returns False when compiled section does not match."""
    rows = [
        {"edge_id": "a->b", "scanned_at": "2026-07-09", "verdict": "null"},
    ]
    nulls_dir = tmp_path / "data" / "neuralweb"
    nulls_dir.mkdir(parents=True, exist_ok=True)
    (nulls_dir / "causal_nulls.jsonl").write_text(
        json.dumps(rows[0]), encoding="utf-8"
    )

    # Write priors with compiled section that does NOT match (stale/wrong)
    import copy
    priors = copy.deepcopy(_MINIMAL_VALID_PRIORS)
    priors["kill_mask"]["compiled"] = [{"edge_id": "stale", "scanned_at": "old"}]

    root = _write_priors(tmp_path, priors)
    assert kill_mask_in_sync(root) is False


# ---------------------------------------------------------------------------
# 13. Authority block: all booleans frozen False (CHF-R1)
# ---------------------------------------------------------------------------

def test_authority_block_frozen(tmp_path: Path):
    """Every may_* boolean in the authority block must be False."""
    root = _write_priors(tmp_path, _MINIMAL_VALID_PRIORS)
    (tmp_path / "data" / "neuralweb").mkdir(parents=True, exist_ok=True)

    payload = build_inventory(root=root)
    auth = payload.get("authority", {})

    for key in ("may_rank", "may_gate", "may_size", "may_escalate"):
        assert auth.get(key) is False, (
            f"authority.{key} must be False (CHF-R1), got {auth.get(key)!r}"
        )

    assert auth.get("display_only") is True, (
        f"authority.display_only must be True, got {auth.get('display_only')!r}"
    )
    assert auth.get("not_a_signal") is True, (
        f"authority.not_a_signal must be True, got {auth.get('not_a_signal')!r}"
    )
    assert auth.get("scored_path_surfaces") == [], (
        f"authority.scored_path_surfaces must be [], got {auth.get('scored_path_surfaces')!r}"
    )


# ---------------------------------------------------------------------------
# 14. Smoke test on real repo data (non-hermetic, skipped when data absent)
# ---------------------------------------------------------------------------

_REPO_ROOT = Path(__file__).resolve().parent.parent
_PRIORS_FILE = _REPO_ROOT / "config" / "causal_priors.yml"
_DATA_REGIME = _REPO_ROOT / "data" / "regime" / "regime_v2_pit.parquet"


@pytest.mark.skipif(
    not (_PRIORS_FILE.exists() and _DATA_REGIME.exists()),
    reason="Real repo data not available — skipping non-hermetic smoke test",
)
def test_smoke_real_repo():
    """Run build_inventory on real repo data and verify schema/structure."""
    payload = build_inventory(root=_REPO_ROOT)

    assert payload.get("schema") == "neuralweb.causal_feature_inventory.v1"
    assert isinstance(payload.get("features"), list)
    assert len(payload["features"]) > 0

    # Every feature must have required keys
    required_keys = {
        "feature_id", "family", "path", "producer", "cadence", "time_grain",
        "asof_field", "first_available_date", "pit_basis", "era_coverage",
        "tier", "allowed_roles", "forbidden_roles", "min_lag_days",
        "collider_risk", "present", "notes",
    }
    for feat in payload["features"]:
        missing = required_keys - feat.keys()
        assert not missing, (
            f"Feature {feat.get('feature_id', '?')} missing keys: {missing}"
        )

    # Authority block check
    auth = payload.get("authority", {})
    for key in ("may_rank", "may_gate", "may_size", "may_escalate"):
        assert auth.get(key) is False, f"authority.{key} must be False"

    # regime_v2_pit feature should be present=True
    pit_features = [
        f for f in payload["features"]
        if "regime_v2_pit" in f["path"]
    ]
    assert len(pit_features) > 0, "Expected at least one regime_v2_pit feature"
    assert pit_features[0]["present"] is True, (
        f"regime_v2_pit feature should be present on real repo, got "
        f"{pit_features[0]['present']}"
    )

    # No forbidden_future feature should have candidate_cause
    for feat in payload["features"]:
        if "forbidden_future" in feat.get("allowed_roles", []):
            assert "candidate_cause" not in feat["allowed_roles"], (
                f"Feature {feat['feature_id']} has forbidden_future but also "
                f"candidate_cause in allowed_roles"
            )
