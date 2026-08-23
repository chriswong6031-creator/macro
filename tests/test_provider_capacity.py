"""Discriminating contract and source tests for Capacity Fabric CF1."""
from __future__ import annotations

import ast
import copy
import hashlib
import inspect
import json
import os
import shutil
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace

import pytest

from engine import codex_provider as cp
from engine import provider_capacity as pc
from engine import provider_health as ph
from engine.neuralweb import key_pool

ROOT = Path(__file__).resolve().parent.parent
NOW = datetime(2026, 8, 23, 12, 0, tzinfo=timezone.utc)
GROUND = pc.MaterialSourceReceipt("1" * 64, "2" * 40, True)


def _cooling_false() -> dict:
    return {
        "active": False,
        "kind": None,
        "reset_at": None,
        "evidence": "exact",
        "observed_at": None,
    }


def _unknown_observation(
    definition: pc.SlotDefinition,
    *,
    present: bool | None = False,
    enabled: bool | None = True,
) -> dict:
    codes = [
        "PROVIDER_HEALTH_UNKNOWN",
        "PROVIDER_BUDGET_UNKNOWN",
        "PROVIDER_OUTCOME_UNKNOWN",
    ]
    if present is None:
        codes.append("PROVIDER_PRESENCE_UNKNOWN")
    if enabled is None:
        codes.append("PROVIDER_ENABLEMENT_UNKNOWN")
    return {
        "capability_id": definition.capability_id,
        "present": present,
        "enabled": enabled,
        "health": pc._unknown_health(),
        "cooling": _cooling_false(),
        "quota_horizons": [] if definition.provider == "deepseek" else [
            pc._unknown_quota("five_hour", 5 * 3600),
            pc._unknown_quota("weekly", 7 * 24 * 3600),
        ],
        "last_outcome": {"class": "unknown", "observed_at": None},
        "degraded_codes": sorted(codes),
    }


def _observations() -> list[dict]:
    return [_unknown_observation(definition) for definition in pc.SUPPORTED_SLOTS]


@pytest.fixture
def grounded(monkeypatch):
    monkeypatch.setattr(pc, "material_source_receipt", lambda _root: GROUND)


def _snapshot(monkeypatch, observations: list[dict] | None = None, **kwargs) -> dict:
    monkeypatch.setattr(pc, "material_source_receipt", lambda _root: GROUND)
    return pc._build_snapshot_from_observations(
        repo_root=ROOT,
        generated_at=kwargs.pop("generated_at", NOW),
        observations=observations or _observations(),
        **kwargs,
    )


def _slot(document: dict, capability_id: str) -> dict:
    return next(row for row in document["slots"] if row["capability_id"] == capability_id)


def _rehash(document: dict) -> dict:
    document["snapshot_hash"] = pc.snapshot_hash(document)
    pc.validate_snapshot(document)
    return document


def test_strict_closed_contract_and_reviewed_inventory(monkeypatch):
    document = _snapshot(monkeypatch)
    assert set(document) == {
        "schema", "generated_at", "producer", "audit", "snapshot_hash",
        "slots", "degraded",
    }
    assert [row["capability_id"] for row in document["slots"]] == [
        "claude_code_oauth",
        "claude_code_oauth_1",
        "claude_code_oauth_2",
        "claude_code_oauth_3",
        "claude_code_oauth_4",
        "claude_code_oauth_5",
        "claude_code_oauth_6",
        "claude_code_oauth_7",
        "codex_account",
        "codex_account_2",
        "codex_account_3",
        "deepseek_api_key",
    ]
    assert {(row["host_ref"], row["capability_id"]) for row in document["slots"]} == {
        (pc.HOST_REF, definition.capability_id)
        for definition in pc.SUPPORTED_SLOTS
    }
    assert all(row["host_ref"] == "local-unbound" for row in document["slots"])
    extra = copy.deepcopy(document)
    extra["extra"] = True
    with pytest.raises(pc.ProviderCapacityError, match="TOP_LEVEL_SCHEMA_INVALID"):
        pc.validate_snapshot(extra)


def test_public_builder_owns_time_and_source_observations():
    assert tuple(inspect.signature(pc.build_snapshot).parameters) == ("repo_root",)
    with pytest.raises(TypeError):
        pc.build_snapshot(repo_root=ROOT, generated_at=NOW)  # type: ignore[call-arg]
    with pytest.raises(TypeError):
        pc.build_snapshot(repo_root=ROOT, observations=_observations())  # type: ignore[call-arg]


def test_known_absent_and_disabled_slots_remain_distinct(monkeypatch):
    observations = _observations()
    observations[0]["present"] = True
    observations[0]["enabled"] = False
    document = _snapshot(monkeypatch, observations)
    legacy = _slot(document, "claude_code_oauth")
    absent = _slot(document, "claude_code_oauth_1")
    assert (legacy["present"], legacy["enabled"]) == (True, False)
    assert (absent["present"], absent["enabled"]) == (False, True)


def test_unreadable_presence_stays_null_and_requires_degradation(monkeypatch):
    observations = _observations()
    observations[1] = _unknown_observation(
        pc.SUPPORTED_SLOTS[1], present=None, enabled=True,
    )
    document = _snapshot(monkeypatch, observations)
    assert _slot(document, "claude_code_oauth_1")["present"] is None
    assert {
        (row["code"], row["scope"]) for row in document["degraded"]
    } >= {("PROVIDER_PRESENCE_UNKNOWN", "claude_code_oauth_1")}

    broken = copy.deepcopy(document)
    broken["degraded"] = [
        row for row in broken["degraded"]
        if (row["code"], row["scope"]) != (
            "PROVIDER_PRESENCE_UNKNOWN", "claude_code_oauth_1",
        )
    ]
    broken["snapshot_hash"] = "0" * 64
    with pytest.raises(pc.ProviderCapacityError, match="REQUIRED_DEGRADATION_MISSING"):
        pc.validate_snapshot(broken, check_hash=False)


def test_dynamic_results_cannot_add_or_remove_reviewed_slots(monkeypatch):
    observations = _observations()
    observations.append({"capability_id": "undeclared_provider"})
    document = _snapshot(monkeypatch, observations)
    assert len(document["slots"]) == len(pc.SUPPORTED_SLOTS)
    assert not any(row["capability_id"] == "undeclared_provider" for row in document["slots"])
    assert {
        (row["code"], row["scope"]) for row in document["degraded"]
    } >= {("PROVIDER_INVENTORY_UNKNOWN", "producer")}

    missing = _snapshot(monkeypatch, _observations()[1:])
    legacy = _slot(missing, "claude_code_oauth")
    assert legacy["present"] is None and legacy["enabled"] is None


def test_duplicate_observation_refuses(monkeypatch):
    observations = _observations()
    observations.append(copy.deepcopy(observations[0]))
    with pytest.raises(pc.ProviderCapacityError, match="DUPLICATE_SLOT_IDENTITY"):
        _snapshot(monkeypatch, observations)


def test_slot_deletion_is_not_false_presence(monkeypatch):
    document = _snapshot(monkeypatch)
    false_hash = document["snapshot_hash"]
    deleted = copy.deepcopy(document)
    deleted["slots"] = deleted["slots"][1:]
    with pytest.raises(pc.ProviderCapacityError, match="SLOT_INVENTORY_INCOMPLETE"):
        pc.snapshot_hash(deleted)
    assert false_hash == document["snapshot_hash"]


def test_hash_excludes_exactly_projection_time_and_audit(monkeypatch):
    first = _snapshot(monkeypatch, generated_at=NOW)
    second = _snapshot(monkeypatch, generated_at=NOW + timedelta(minutes=3))
    assert first["generated_at"] != second["generated_at"]
    assert first["snapshot_hash"] == second["snapshot_hash"]

    audit_only = copy.deepcopy(first)
    audit_only["audit"]["repository_commit"] = "3" * 40
    assert pc.snapshot_hash(audit_only) == first["snapshot_hash"]


@pytest.mark.parametrize(
    "mutation",
    [
        "presence",
        "health_freshness",
        "implementation_version",
        "material_source_digest",
        "required_degradation",
    ],
)
def test_semantic_mutations_change_hash(monkeypatch, mutation):
    document = _snapshot(monkeypatch)
    original = document["snapshot_hash"]
    changed = copy.deepcopy(document)
    if mutation == "presence":
        changed["slots"][0]["present"] = True
    elif mutation == "health_freshness":
        changed["slots"][0]["health"] = {
            "state": "available",
            "error_class": None,
            "observed_at": "2026-08-23T11:00:00Z",
            "stale_after": "2026-08-23T11:10:00Z",
            "evidence": "provider_reported",
            "source_kind": "provider_attempt",
            "freshness": "stale",
        }
    elif mutation == "implementation_version":
        changed["producer"]["implementation_version"] += 1
    elif mutation == "material_source_digest":
        changed["producer"]["material_source_digest"] = "4" * 64
    else:
        changed["degraded"].append({
            "code": "SOURCE_CORRUPT",
            "scope": "producer",
            "observed_at": None,
        })
        changed["degraded"] = pc._dedupe_degraded(changed["degraded"])
    assert pc.snapshot_hash(changed) != original


def test_hash_function_refuses_invalid_snapshot(monkeypatch):
    document = _snapshot(monkeypatch)
    document["slots"][0]["surprise"] = "not-v1"
    with pytest.raises(pc.ProviderCapacityError, match="SLOT_SCHEMA_INVALID"):
        pc.snapshot_hash(document)


def test_no_observation_quota_is_null_not_zero(monkeypatch):
    document = _snapshot(monkeypatch)
    horizon = _slot(document, "claude_code_oauth")["quota_horizons"][0]
    assert all(
        horizon[key] is None
        for key in (
            "limit", "used", "remaining", "used_percent", "reset_at",
            "observed_at", "stale_after",
        )
    )
    assert (horizon["evidence"], horizon["source_kind"], horizon["freshness"]) == (
        "unknown", "unknown", "unknown",
    )


def test_reported_percentage_outranks_estimate_without_inventing_remaining():
    definition = next(row for row in pc.SUPPORTED_SLOTS if row.capability_id == "claude_code_oauth_1")
    source = {
        "budget": {
            "headers": {
                "anthropic-ratelimit-5h-used-percent": "57",
                "anthropic-ratelimit-5h-reset": "2026-08-23T13:00:00Z",
            },
            "headers_ts": "2026-08-23T11:59:00Z",
            "est_5h_tokens": 20,
            "est_weekly_tokens": 30,
        },
        "cooling": _cooling_false(),
        "last_outcome": {"class": "ok", "observed_at": "2026-08-23T11:59:00Z"},
    }
    rows, _codes = pc._quota_from_sources(
        definition,
        source,
        {"quality": "ok", "est_budget_5h_tokens": 100, "est_budget_weekly_tokens": 100},
        NOW,
    )
    five, weekly = rows
    assert five["evidence"] == "provider_reported"
    assert five["used_percent"] == 57.0
    assert five["limit"] is None and five["remaining"] is None
    assert weekly["evidence"] == "estimated"


def test_429_affects_only_evidenced_horizon():
    definition = pc.SUPPORTED_SLOTS[1]
    source = {
        "budget": {"headers": {}, "headers_ts": None},
        "cooling": {
            "active": True,
            "kind": "window",
            "reset_at": "2026-08-23T13:00:00Z",
            "evidence": "provider_reported",
            "observed_at": "2026-08-23T11:59:00Z",
        },
        "last_outcome": {"class": "rate_limited", "observed_at": "2026-08-23T11:59:00Z"},
    }
    rows, _codes = pc._quota_from_sources(
        definition,
        source,
        {"quality": "ok", "est_budget_5h_tokens": None, "est_budget_weekly_tokens": None},
        NOW,
    )
    assert rows[0]["used_percent"] == 100.0
    assert rows[0]["source_kind"] == "error_signal"
    assert rows[1]["evidence"] == "unknown"


def test_stale_health_is_not_restamped_fresh():
    definition = pc.SUPPORTED_SLOTS[0]
    health, codes = pc._health_from_sources(
        definition,
        {
            "quality": "ok",
            "rows": [{
                "ts": "2026-08-23T10:00:00Z",
                "rung": "oauth",
                "cap_id": None,
                "ok": True,
                "error_class": "",
            }],
        },
        NOW,
    )
    assert codes == []
    assert health["state"] == "available"
    assert health["observed_at"] == "2026-08-23T10:00:00Z"
    assert health["freshness"] == "stale"


def test_no_health_source_is_fully_unknown():
    health, codes = pc._health_from_sources(
        pc.SUPPORTED_SLOTS[0], {"quality": "missing", "rows": []}, NOW,
    )
    assert health == pc._unknown_health()
    assert "PROVIDER_HEALTH_UNKNOWN" in codes


def test_legacy_claude_health_identifier_is_canonicalized_and_consumed(tmp_path):
    ledger = tmp_path / "data" / "ai_costs" / "provider_health.jsonl"
    ledger.parent.mkdir(parents=True)
    ledger.write_text(
        json.dumps({
            "event": "attempt",
            "ts": "2026-08-23T11:59:00Z",
            "rung": "oauth",
            "cap_id": "CLAUDE_CODE_OAUTH_TOKEN",
            "ok": True,
            "error_class": "",
        }) + "\n",
        encoding="utf-8",
    )
    source = ph.capacity_health_observations(root=tmp_path)
    assert source["rows"][0]["cap_id"] == "claude_code_oauth"

    health, codes = pc._health_from_sources(pc.SUPPORTED_SLOTS[0], source, NOW)
    assert codes == []
    assert health["state"] == "available"
    assert health["evidence"] == "provider_reported"


def test_invalid_numbers_and_impossible_absolute_quota_refuse(monkeypatch):
    document = _snapshot(monkeypatch)
    row = document["slots"][0]["quota_horizons"][0]
    row.update({
        "limit": 100,
        "used": 80,
        "remaining": 30,
        "used_percent": 80,
        "observed_at": "2026-08-23T11:59:00Z",
        "stale_after": "2026-08-23T12:09:00Z",
        "evidence": "estimated",
        "source_kind": "local_ledger",
        "freshness": "fresh",
    })
    with pytest.raises(pc.ProviderCapacityError, match="IMPOSSIBLE_QUOTA_RELATION"):
        pc.validate_snapshot(document, check_hash=False)
    row["remaining"] = 20
    row["used"] = float("nan")
    with pytest.raises(pc.ProviderCapacityError, match="INVALID_NUMBER"):
        pc.validate_snapshot(document, check_hash=False)


def test_secret_shaped_header_value_never_enters_projection():
    sentinel = "sk-live-never-serialize-this"
    definition = pc.SUPPORTED_SLOTS[1]
    rows, codes = pc._quota_from_sources(
        definition,
        {
            "budget": {
                "headers": {"anthropic-ratelimit-5h-used-percent": sentinel},
                "headers_ts": "2026-08-23T11:59:00Z",
            },
            "cooling": _cooling_false(),
            "last_outcome": {"class": "unknown", "observed_at": None},
        },
        {"quality": "ok", "est_budget_5h_tokens": None, "est_budget_weekly_tokens": None},
        NOW,
    )
    assert sentinel not in json.dumps(rows)
    assert "SOURCE_CORRUPT" in codes


def test_codex_observation_keeps_presence_enablement_and_binary_orthogonal(
    monkeypatch, tmp_path,
):
    homes = [tmp_path / f"codex-{index}" for index in range(3)]
    for home in homes:
        home.mkdir()
    (homes[0] / "auth.json").write_text("credential-bytes-not-read", encoding="utf-8")
    monkeypatch.setenv("CODEX_ACCOUNT_HOMES", os.pathsep.join(map(str, homes)))
    monkeypatch.setenv("CODEX_PROVIDER_ENABLED", "0")
    monkeypatch.delenv("CODEX_ACCESS_TOKEN", raising=False)
    monkeypatch.delenv("CODEX_API_KEY", raising=False)
    monkeypatch.setattr(cp, "resolve_codex_bin", lambda: "/definitely/missing/codex")

    result = cp.capacity_account_observations()
    assert result["enabled"] is False
    assert result["executable_present"] is False
    assert [row["present"] for row in result["slots"]] == [True, False, False]


def test_codex_unreadable_presence_is_null(monkeypatch):
    class UnreadableMarker:
        def stat(self):
            raise PermissionError("not readable")

    monkeypatch.setattr(cp, "account_homes", lambda: [Path("/opaque")])
    monkeypatch.setattr(cp, "auth_file_path", lambda _home: UnreadableMarker())
    monkeypatch.setattr(cp, "resolve_codex_bin", lambda: "/definitely/missing/codex")
    monkeypatch.delenv("CODEX_ACCESS_TOKEN", raising=False)
    monkeypatch.delenv("CODEX_API_KEY", raising=False)
    result = cp.capacity_account_observations()
    assert result["slots"][0]["present"] is None
    assert "SOURCE_UNREADABLE" in result["slots"][0]["codes"]


def _write_manifest(root: Path) -> None:
    rows = "\n".join(
        "  - capability_id: {0}\n    secret_ref: TEST_SECRET_{1}\n"
        "    kill_state: active".format(capability_id, index)
        for index, capability_id in enumerate(key_pool._CAPACITY_KEY_IDS)
    )
    path = root / "config" / "capability_manifest.yml"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("capabilities:\n" + rows + "\n", encoding="utf-8")


def test_key_owner_preserves_disabled_presence_and_complete_negative_cooling(
    monkeypatch, tmp_path,
):
    repo = tmp_path / "repo"
    state = tmp_path / "state"
    _write_manifest(repo)
    ledger = state / "data" / "metabolism" / "key_ledger.jsonl"
    ledger.parent.mkdir(parents=True)
    ledger.write_text("", encoding="utf-8")
    usage = state / "data" / "metabolism" / "key_usage.jsonl"
    usage.write_text("", encoding="utf-8")
    monkeypatch.setenv("TEST_SECRET_1", "present-but-never-returned")
    monkeypatch.setenv("METAB_KEYS_ENABLED", "2")

    result = key_pool.capacity_key_observations(
        repo, state_root=state, observed_at=NOW,
    )
    slot = next(row for row in result["slots"] if row["capability_id"] == "claude_code_oauth_1")
    assert slot["present"] is True
    assert slot["enabled"] is False
    assert {
        key: slot["cooling"][key] for key in _cooling_false()
    } == _cooling_false()
    assert "present-but-never-returned" not in json.dumps(result)


@pytest.mark.parametrize("source_state", ["missing", "corrupt"])
def test_key_owner_never_turns_ambiguous_cooling_into_false(
    monkeypatch, tmp_path, source_state,
):
    repo = tmp_path / "repo"
    state = tmp_path / "state"
    _write_manifest(repo)
    if source_state == "corrupt":
        ledger = state / "data" / "metabolism" / "key_ledger.jsonl"
        ledger.parent.mkdir(parents=True)
        ledger.write_text("not-json\n", encoding="utf-8")
    result = key_pool.capacity_key_observations(
        repo, state_root=state, observed_at=NOW,
    )
    assert all(row["cooling"]["active"] is None for row in result["slots"])
    expected = "SOURCE_CORRUPT" if source_state == "corrupt" else "PROVIDER_COOLING_UNKNOWN"
    assert all(expected in row["codes"] for row in result["slots"])


def _git(root: Path, *args: str) -> str:
    return subprocess.run(
        ["git", "-C", str(root), *args],
        check=True,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    ).stdout.strip()


def _material_repo(tmp_path: Path) -> Path:
    root = tmp_path / "material-repo"
    for relative in pc.MATERIAL_SOURCE_PATHS:
        target = root / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(ROOT / relative, target)
    unrelated = root / "notes" / "unrelated.txt"
    unrelated.parent.mkdir(parents=True)
    unrelated.write_text("unchanged\n", encoding="utf-8")
    _git(root, "init")
    _git(root, "config", "user.email", "capacity@example.invalid")
    _git(root, "config", "user.name", "Capacity Test")
    _git(root, "add", ".")
    _git(root, "commit", "-m", "fixture")
    return root


def test_material_digest_and_grounding_are_file_granular(tmp_path):
    root = _material_repo(tmp_path)
    initial = pc.material_source_receipt(root)
    assert initial.material_sources_match_commit is True

    (root / "notes" / "unrelated.txt").write_text("dirty unrelated\n", encoding="utf-8")
    unrelated = pc.material_source_receipt(root)
    assert unrelated.material_source_digest == initial.material_source_digest
    assert unrelated.material_sources_match_commit is True

    material = root / "config" / "metabolism_budget.yml"
    material.write_bytes(material.read_bytes() + b"\n")
    dirty = pc.material_source_receipt(root)
    assert dirty.material_source_digest != initial.material_source_digest
    assert dirty.material_sources_match_commit is False

    _git(root, "add", "config/metabolism_budget.yml")
    _git(root, "commit", "-m", "material change")
    restored = pc.material_source_receipt(root)
    assert restored.material_sources_match_commit is True
    assert restored.material_source_digest == dirty.material_source_digest


def test_unrelated_commit_changes_audit_not_semantic_producer(monkeypatch, tmp_path):
    root = _material_repo(tmp_path)
    first = pc.material_source_receipt(root)
    (root / "notes" / "unrelated.txt").write_text("committed unrelated\n", encoding="utf-8")
    _git(root, "add", "notes/unrelated.txt")
    _git(root, "commit", "-m", "unrelated")
    second = pc.material_source_receipt(root)
    assert first.repository_commit != second.repository_commit
    assert first.material_source_digest == second.material_source_digest
    assert second.material_sources_match_commit is True

    observations = _observations()
    monkeypatch.setattr(pc, "material_source_receipt", lambda _root: first)
    one = pc._build_snapshot_from_observations(
        repo_root=root, generated_at=NOW, observations=observations,
    )
    monkeypatch.setattr(pc, "material_source_receipt", lambda _root: second)
    two = pc._build_snapshot_from_observations(
        repo_root=root, generated_at=NOW, observations=observations,
    )
    assert one["snapshot_hash"] == two["snapshot_hash"]


def test_material_grounding_uses_one_bounded_tree_query(monkeypatch, tmp_path):
    root = _material_repo(tmp_path)
    real_run = pc.subprocess.run
    git_calls: list[tuple[str, ...]] = []

    def recording_run(args, **kwargs):
        git_calls.append(tuple(str(value) for value in args))
        return real_run(args, **kwargs)

    monkeypatch.setattr(pc.subprocess, "run", recording_run)
    receipt = pc.material_source_receipt(root)
    assert receipt.material_sources_match_commit is True
    assert sum("ls-tree" in call for call in git_calls) == 1
    assert not any("show" in call for call in git_calls)
    assert len(git_calls) == 2


def test_allowlist_change_changes_digest_without_caller_override(monkeypatch, tmp_path):
    root = _material_repo(tmp_path)
    initial = pc.material_source_receipt(root)
    changed_paths = tuple(sorted((*pc.MATERIAL_SOURCE_PATHS, "notes/unrelated.txt")))
    monkeypatch.setattr(pc, "MATERIAL_SOURCE_PATHS", changed_paths)
    changed = pc.material_source_receipt(root)
    assert changed.material_source_digest != initial.material_source_digest


@pytest.mark.parametrize("failure", ["missing", "symlink", "escape"])
def test_invalid_material_source_refuses(monkeypatch, tmp_path, failure):
    root = _material_repo(tmp_path)
    if failure == "missing":
        monkeypatch.setattr(pc, "MATERIAL_SOURCE_PATHS", ("missing.py",))
        expected = "MATERIAL_SOURCE_MISSING"
    elif failure == "symlink":
        (root / "linked.py").symlink_to(root / "engine" / "provider_capacity.py")
        monkeypatch.setattr(pc, "MATERIAL_SOURCE_PATHS", ("linked.py",))
        expected = "MATERIAL_SOURCE_SYMLINK"
    else:
        monkeypatch.setattr(pc, "MATERIAL_SOURCE_PATHS", ("../escape.py",))
        expected = "MATERIAL_SOURCE_PATH_ESCAPE"
    with pytest.raises(pc.ProviderCapacityError, match=expected):
        pc.material_source_receipt(root)


def test_projection_normalizer_has_no_direct_secret_or_provider_call_path():
    source_path = ROOT / "engine" / "provider_capacity.py"
    source = source_path.read_text(encoding="utf-8")
    tree = ast.parse(source)
    imports = {
        node.names[0].name
        for node in ast.walk(tree)
        if isinstance(node, ast.Import) and node.names
    }
    assert "os" not in imports
    assert "requests" not in imports
    assert "httpx" not in imports
    forbidden = (
        "CODEX_ACCESS_TOKEN",
        "CODEX_API_KEY",
        "CLAUDE_CODE_OAUTH_TOKEN",
        "DEEPSEEK_API_KEY",
        "auth.json",
        "available_accounts(",
        "discover_present_keys(",
        "make_call(",
        "run_codex(",
    )
    assert all(token not in source for token in forbidden)


def test_real_cli_is_canonical_json_and_no_write():
    tracked_before = _git(ROOT, "status", "--porcelain=v1")
    proc = subprocess.run(
        [sys.executable, "scripts/build_provider_capacity.py"],
        cwd=ROOT,
        check=True,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=30,
    )
    tracked_after = _git(ROOT, "status", "--porcelain=v1")
    document = json.loads(proc.stdout)
    pc.validate_snapshot(document)
    assert proc.stdout == pc.canonical_json(document)
    assert tracked_after == tracked_before
    assert proc.stderr == ""
    assert document["schema"] == pc.SCHEMA
    assert document["producer"]["implementation_id"] == pc.IMPLEMENTATION_ID
    assert document["audit"]["repository_commit"] == _git(ROOT, "rev-parse", "HEAD")
    forbidden_values = (
        str(Path.home()),
        "@",
        "CODEX_ACCESS_TOKEN",
        "CLAUDE_CODE_OAUTH_TOKEN",
        "DEEPSEEK_API_KEY",
        "auth.json",
    )
    assert all(value not in proc.stdout for value in forbidden_values)


def test_material_source_allowlist_is_static_sorted_and_complete():
    assert pc.MATERIAL_SOURCE_PATHS == tuple(sorted(pc.MATERIAL_SOURCE_PATHS))
    assert len(pc.MATERIAL_SOURCE_PATHS) == len(set(pc.MATERIAL_SOURCE_PATHS))
    assert {
        "config/capability_manifest.yml",
        "config/metabolism_budget.yml",
        "engine/codex_lane/runner.py",
        "engine/codex_provider.py",
        "engine/llm_auth.py",
        "engine/metabolism/budget_gate.py",
        "engine/neuralweb/key_pool.py",
        "engine/provider_capacity.py",
        "engine/provider_health.py",
        "lib/ai_costs.py",
    } == set(pc.MATERIAL_SOURCE_PATHS)


def test_canonical_digest_vector_is_stable():
    value = {"z": "容量", "a": [2, 1]}
    expected_bytes = '{"a":[2,1],"z":"容量"}'.encode("utf-8")
    assert pc._canonical_bytes(value) == expected_bytes
    assert hashlib.sha256(pc._canonical_bytes(value)).hexdigest() == hashlib.sha256(expected_bytes).hexdigest()
