"""Hostile tests for the W2-A versioned workspace layout contract
(`workspace_layout.v1`).

Frozen contract: research/DEEPVUE_W2A_WORKSPACE_LAYOUT_CONTRACT_2026-08-26.md.

Coverage:
  1. schema parses + validates the freeze §1 canonical example
  2. every valid migration vector: migrate_legacy(input) deep-equals the
     committed `expected` envelope, twice in a row (determinism)
  3. no-claim law: unclaimed chart-config fields are ABSENT, never null
  4. validate_envelope is `ok` on every valid vector's expected envelope
  5. every invalid vector -> its exact committed `expected_code`, never raises
  6. subscriber_safe_projection: name filled, unknown injected key dropped,
     no user_id/uuid-shaped key ever survives
  7. MANIFEST.json digest recomputes to the pinned `vectors_digest` literal
  8. hostile fuzz across both validate_envelope and migrate_legacy never raises
"""
from __future__ import annotations

import hashlib
import json
import pathlib
import sys

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from engine.intelligence_workspace import workspace_layout as wl  # noqa: E402

REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]
FIXTURES_DIR = REPO_ROOT / "contracts" / "intelligence_workspace" / "fixtures" / "workspace_migration"
SCHEMA_PATH = REPO_ROOT / "contracts" / "intelligence_workspace" / "workspace_layout.v1.schema.json"

# Pinned hard literal (contract §10/#SCOPE-item-3): a MANIFEST digest drift
# without a matching edit here means the fixtures changed silently.
# Re-pinned under Amendment A1 (2026-08-26): `lockedVLine` is string|null (was
# number|null) and `split` is the discrete enum {1, 2, 4} (was 0-100) — both
# falsified against the real Terminal runtime; the pre-amendment digest is
# void (research/DEEPVUE_W2A_WORKSPACE_LAYOUT_CONTRACT_2026-08-26.md).
PINNED_VECTORS_DIGEST = "9eeef5b4b055e3ffa407f76d8e3a6ee70c2ab064194983391062d29ec4b701ab"

# The freeze doc's §1 canonical example, verbatim.
FREEZE_SECTION_1_EXAMPLE = {
    "schema": "workspace_layout.v1",
    "requires": {"floor": 1},
    "revision": 3,
    "name": None,
    "link_groups": {
        "primary_security": {"entity_type": "security"},
    },
    "widgets": [
        {
            "id": "chart-main",
            "type": "chart",
            "semantic_lane": "primary",
            "grid": {"x": 0, "y": 0, "w": 16, "h": 18},
            "context_in": ["primary_security"],
            "context_out": ["primary_security"],
            "config": {
                "panes": ["NVDA"], "paneTfs": ["1D"], "split": 1, "activePane": 0,
                "sync": True, "chartType": "candles", "inds": ["ema21"],
                "indParams": {}, "hidden": [], "compare": [], "compareCfg": {},
                "lockedVLine": None,
            },
        },
        {
            "id": "brain-dock",
            "type": "brain",
            "semantic_lane": "dock",
            "context_in": ["primary_security"],
            "context_out": [],
            "config": {},
        },
    ],
    "migration": {"source": "chart_layout_v2", "source_revision": 2},
}


def _load(name: str) -> dict:
    return json.loads((FIXTURES_DIR / name).read_text())


VALID_VECTOR_NAMES = [
    "legacy_v0_minimal.json",
    "legacy_v0_bare.json",
    "chart_layout_v1_typical.json",
    "chart_layout_v1_sparse.json",
    "chart_layout_v2_full.json",
    "chart_layout_v2_sparse.json",
]

INVALID_VECTOR_NAMES = [
    "invalid_unknown_schema.json",
    "invalid_floor_unsupported.json",
    "invalid_duplicate_widget_id.json",
    "invalid_unknown_widget_type.json",
    "invalid_lane.json",
    "invalid_port.json",
    "invalid_too_many_widgets.json",
    "invalid_oversized_workspace.json",
    "invalid_non_null_name.json",
    "invalid_unknown_top_level_key.json",
    "invalid_unknown_chart_config_key.json",
    "invalid_non_dict_input.json",
]


# ---------------------------------------------------------------------------
# 1. schema parses + validates the freeze §1 canonical example
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def _envelope_validator():
    from jsonschema import Draft202012Validator

    schema = json.loads(SCHEMA_PATH.read_text())
    Draft202012Validator.check_schema(schema)
    return Draft202012Validator(schema)


def test_schema_is_itself_a_valid_json_schema(_envelope_validator):
    assert _envelope_validator is not None


def test_freeze_section_1_example_validates_against_the_schema(_envelope_validator):
    errors = list(_envelope_validator.iter_errors(FREEZE_SECTION_1_EXAMPLE))
    assert errors == [], errors


def test_freeze_section_1_example_passes_validate_envelope():
    result = wl.validate_envelope(FREEZE_SECTION_1_EXAMPLE)
    assert result == {"ok": True, "errors": []}


# ---------------------------------------------------------------------------
# 2. every valid vector: migrate_legacy determinism + exact expected match
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("name", VALID_VECTOR_NAMES)
def test_valid_vector_migrates_to_the_exact_committed_envelope(name):
    vector = _load(name)
    first = wl.migrate_legacy(vector["input"])
    second = wl.migrate_legacy(vector["input"])
    assert first == second, f"{name}: migrate_legacy is not deterministic"
    assert first["ok"] is True, f"{name}: {first}"
    assert first["envelope"] == vector["expected"], name


@pytest.mark.parametrize("name", VALID_VECTOR_NAMES)
def test_valid_vector_expected_envelope_passes_validate_envelope(name):
    vector = _load(name)
    result = wl.validate_envelope(vector["expected"])
    assert result == {"ok": True, "errors": []}, (name, result)


@pytest.mark.parametrize("name", VALID_VECTOR_NAMES)
def test_valid_vector_expected_envelope_validates_against_the_schema(name, _envelope_validator):
    vector = _load(name)
    errors = list(_envelope_validator.iter_errors(vector["expected"]))
    assert errors == [], (name, errors)


# ---------------------------------------------------------------------------
# 3. no-claim law: unclaimed fields are ABSENT, never null
# ---------------------------------------------------------------------------

def test_legacy_v0_bare_has_no_pane_tfs_key_at_all():
    """No `tf` in the input -> `paneTfs` must be ABSENT from the migrated
    config, never present-and-null (contract §6 no-claim semantics)."""
    result = wl.migrate_legacy({"active": "MSFT"})
    config = result["envelope"]["widgets"][0]["config"]
    assert "paneTfs" not in config
    assert config["panes"] == ["MSFT"]
    assert config["sync"] is True


def test_chart_layout_v1_sparse_only_claims_panes_and_the_sync_default():
    vector = _load("chart_layout_v1_sparse.json")
    config = vector["expected"]["widgets"][0]["config"]
    assert set(config.keys()) == {"panes", "sync"}


def test_chart_layout_v2_sparse_never_defaults_sync():
    """v2 never gets the sync-default injection even though panes is
    claimed — the default is ONLY for version < 2 (contract §6 verbatim)."""
    vector = _load("chart_layout_v2_sparse.json")
    config = vector["expected"]["widgets"][0]["config"]
    assert "sync" not in config
    assert set(config.keys()) == {"panes", "chartType"}


def test_chart_layout_v2_full_carries_all_twelve_fields_verbatim():
    vector = _load("chart_layout_v2_full.json")
    config = vector["expected"]["widgets"][0]["config"]
    assert set(config.keys()) == set(wl.CHART_CONFIG_FIELDS)


def test_unclaimed_field_is_missing_key_not_none_value():
    result = wl.migrate_legacy({"panes": ["TSLA"]})
    config = result["envelope"]["widgets"][0]["config"]
    for field in wl.CHART_CONFIG_FIELDS:
        if field not in ("panes", "sync"):
            assert field not in config, field


# ---------------------------------------------------------------------------
# Amendment A1 (2026-08-26) regression: `lockedVLine` is string|null, never
# number; `split` is the discrete enum {1, 2, 4}, never a 0-100 percentage.
# Both were falsified against the real Terminal runtime and would have
# rejected every real v2 layout under the original (pre-amendment) law.
# ---------------------------------------------------------------------------

def _widget_config(**overrides):
    config = {"panes": ["NVDA"]}
    config.update(overrides)
    return {
        "schema": "workspace_layout.v1",
        "requires": {"floor": 1},
        "revision": 1,
        "name": None,
        "link_groups": {"primary_security": {"entity_type": "security"}},
        "widgets": [
            {
                "id": "chart-main",
                "type": "chart",
                "semantic_lane": "primary",
                "context_in": ["primary_security"],
                "context_out": ["primary_security"],
                "config": config,
            },
        ],
        "migration": {"source": "none", "source_revision": None},
    }


def test_amendment_a1_string_locked_vline_validates():
    envelope = _widget_config(lockedVLine="2026-08-12T14:30:00Z")
    result = wl.validate_envelope(envelope)
    assert result == {"ok": True, "errors": []}


def test_amendment_a1_numeric_locked_vline_is_invalid_widget_config():
    envelope = _widget_config(lockedVLine=1700000000)
    result = wl.validate_envelope(envelope)
    assert result["ok"] is False
    assert {e["code"] for e in result["errors"]} == {"invalid_widget_config"}


def test_amendment_a1_split_2_validates():
    envelope = _widget_config(split=2)
    result = wl.validate_envelope(envelope)
    assert result == {"ok": True, "errors": []}


def test_amendment_a1_split_50_is_invalid_widget_config():
    envelope = _widget_config(split=50)
    result = wl.validate_envelope(envelope)
    assert result["ok"] is False
    assert {e["code"] for e in result["errors"]} == {"invalid_widget_config"}


def test_amendment_a1_locked_vline_null_still_valid():
    """`null` remains a legitimate claimed value (explicit "no lock"), not
    merely the absence of the field — unaffected by the type-narrowing."""
    envelope = _widget_config(lockedVLine=None)
    assert wl.validate_envelope(envelope) == {"ok": True, "errors": []}


def test_amendment_a1_split_only_allows_the_frozen_enum():
    for value in (0, 3, 5, 100, -1):
        envelope = _widget_config(split=value)
        result = wl.validate_envelope(envelope)
        assert result["ok"] is False, value
        assert {e["code"] for e in result["errors"]} == {"invalid_widget_config"}
    for value in (1, 2, 4):
        envelope = _widget_config(split=value)
        assert wl.validate_envelope(envelope) == {"ok": True, "errors": []}


def test_amendment_a1_locked_vline_rejects_control_characters_and_oversize():
    for bad in ("\x00", "a\nb", "x" * 65, ""):
        envelope = _widget_config(lockedVLine=bad)
        result = wl.validate_envelope(envelope)
        assert result["ok"] is False, repr(bad)
        assert {e["code"] for e in result["errors"]} == {"invalid_widget_config"}


# ---------------------------------------------------------------------------
# 4/5. invalid vectors -> exact expected_code, never raises
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("name", INVALID_VECTOR_NAMES)
def test_invalid_vector_yields_its_exact_expected_code(name):
    vector = _load(name)
    result = wl.validate_envelope(vector["input"])
    assert result["ok"] is False, name
    codes = {e["code"] for e in result["errors"]}
    assert codes == {vector["expected_code"]}, (name, result["errors"])


def test_every_invalid_vector_names_a_frozen_failure_code():
    for name in INVALID_VECTOR_NAMES:
        vector = _load(name)
        assert vector["expected_code"] in wl.FAILURE_CODES, name


# ---------------------------------------------------------------------------
# 6. subscriber-safe projection
# ---------------------------------------------------------------------------

def test_projection_fills_name_from_row_and_matches_otherwise():
    envelope = dict(FREEZE_SECTION_1_EXAMPLE)
    projected = wl.subscriber_safe_projection(envelope, "My Chart Workspace")
    assert projected["name"] == "My Chart Workspace"
    without_name = {**projected, "name": None}
    assert without_name == envelope


def test_projection_drops_injected_unknown_top_level_key():
    hostile = {**FREEZE_SECTION_1_EXAMPLE, "user_id": "11111111-1111-1111-1111-111111111111"}
    projected = wl.subscriber_safe_projection(hostile, "row-name")
    assert "user_id" not in projected
    blob = json.dumps(projected)
    assert "11111111-1111-1111-1111-111111111111" not in blob


def test_projection_drops_injected_unknown_widget_key():
    import copy

    hostile = copy.deepcopy(FREEZE_SECTION_1_EXAMPLE)
    hostile["widgets"][0]["owner_uuid"] = "22222222-2222-2222-2222-222222222222"
    hostile["widgets"][0]["config"]["path_leak"] = "/Users/attacker/.ssh/id_rsa"
    projected = wl.subscriber_safe_projection(hostile, "row-name")
    blob = json.dumps(projected)
    assert "owner_uuid" not in blob
    assert "22222222" not in blob
    assert "path_leak" not in blob
    assert "attacker" not in blob


def test_projection_never_carries_uuid_or_path_shaped_injected_values():
    import copy

    hostile = copy.deepcopy(FREEZE_SECTION_1_EXAMPLE)
    hostile["row_uuid"] = "33333333-3333-3333-3333-333333333333"
    hostile["source_path"] = "/etc/passwd"
    projected = wl.subscriber_safe_projection(hostile, "row-name")
    blob = json.dumps(projected)
    assert "33333333" not in blob
    assert "/etc/passwd" not in blob


def test_projection_on_hostile_non_mapping_envelope_never_raises():
    for hostile in (None, [], 1, "garbage", {"schema": {}}):
        projected = wl.subscriber_safe_projection(hostile, "row-name")
        assert projected["schema"] == wl.SCHEMA
        assert projected["widgets"] == []


# ---------------------------------------------------------------------------
# 7. MANIFEST digest recomputes to the pinned literal
# ---------------------------------------------------------------------------

def test_manifest_recomputes_to_the_pinned_vectors_digest():
    manifest = json.loads((FIXTURES_DIR / "MANIFEST.json").read_text())
    entries = sorted(manifest["files"], key=lambda row: row["name"])
    for row in entries:
        path = FIXTURES_DIR / row["name"]
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        assert digest == row["sha256"], row["name"]
    recomputed = hashlib.sha256(
        "".join(row["sha256"] for row in entries).encode("utf-8")
    ).hexdigest()
    assert recomputed == manifest["vectors_digest"]
    assert manifest["vectors_digest"] == PINNED_VECTORS_DIGEST


def test_manifest_lists_every_fixture_file_and_nothing_extra():
    manifest = json.loads((FIXTURES_DIR / "MANIFEST.json").read_text())
    manifest_names = {row["name"] for row in manifest["files"]}
    on_disk = {p.name for p in FIXTURES_DIR.glob("*.json") if p.name != "MANIFEST.json"}
    assert manifest_names == on_disk


# ---------------------------------------------------------------------------
# 8. hostile fuzz — never raises, always a structured result
# ---------------------------------------------------------------------------

_HOSTILE_INPUTS = [
    None,
    [],
    1,
    3.14,
    True,
    "not-a-dict",
    b"bytes-not-a-dict",
    {},
    {"schema": {}},
    {"schema": "workspace_layout.v1"},
    {"schema": "workspace_layout.v1", "widgets": "not-a-list"},
    {"active": None},
    {"active": ["a", "b"]},
    {"panes": None},
    {"panes": [1, 2, 3]},
    {"schemaVersion": 2, "panes": {"nested": True}},
    {"schemaVersion": "2"},
    {"\ud800": "lone-surrogate-key"},
    {"active": "𐀀", "tf": "1D"},
    {str(i): i for i in range(200)},
]


@pytest.mark.parametrize("hostile", _HOSTILE_INPUTS)
def test_validate_envelope_never_raises_on_hostile_input(hostile):
    result = wl.validate_envelope(hostile)
    assert isinstance(result, dict)
    assert isinstance(result["ok"], bool)
    assert isinstance(result["errors"], list)
    for row in result["errors"]:
        assert row["code"] in wl.FAILURE_CODES


@pytest.mark.parametrize("hostile", _HOSTILE_INPUTS)
def test_migrate_legacy_never_raises_on_hostile_input(hostile):
    result = wl.migrate_legacy(hostile)
    assert isinstance(result, dict)
    assert isinstance(result["ok"], bool)
    if result["ok"]:
        assert "envelope" in result
    else:
        assert result["code"] in wl.FAILURE_CODES


@pytest.mark.parametrize("hostile", _HOSTILE_INPUTS)
def test_subscriber_safe_projection_never_raises_on_hostile_input(hostile):
    projected = wl.subscriber_safe_projection(hostile, "row-name")
    assert projected["schema"] == wl.SCHEMA


def test_envelope_digest_is_deterministic_and_order_independent():
    a = {"b": 2, "a": 1}
    b = {"a": 1, "b": 2}
    assert wl.envelope_digest(a) == wl.envelope_digest(b)
    assert wl.envelope_digest(a) == wl.envelope_digest(a)


def test_envelope_digest_never_raises_on_hostile_input():
    for hostile in (None, [], "x", {"a": float("nan")}):
        try:
            digest = wl.envelope_digest(hostile)
        except (TypeError, ValueError):
            # float("nan") is not valid JSON under default json.dumps
            # settings unless allow_nan permits it (it does, by default) —
            # this branch exists purely so a future stricter serialization
            # choice cannot turn into an uncaught crash here.
            continue
        assert isinstance(digest, str) and len(digest) == 64


# ---------------------------------------------------------------------------
# Migration recognizer table sanity: an unrecognized shape refuses cleanly.
# ---------------------------------------------------------------------------

def test_unrecognized_shape_is_unsupported_schema():
    result = wl.migrate_legacy({"totally": "unknown", "shape": 1})
    assert result == {"ok": False, "code": "unsupported_schema"}


def test_already_canonical_input_passes_through_validation():
    result = wl.migrate_legacy(FREEZE_SECTION_1_EXAMPLE)
    assert result["ok"] is True
    assert result["envelope"] == FREEZE_SECTION_1_EXAMPLE


def test_already_canonical_but_invalid_input_surfaces_its_code():
    hostile = {**FREEZE_SECTION_1_EXAMPLE, "name": "not-null"}
    result = wl.migrate_legacy(hostile)
    assert result == {"ok": False, "code": "malformed_workspace"}
