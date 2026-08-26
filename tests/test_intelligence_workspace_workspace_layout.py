"""Hostile tests for the W2-A versioned workspace layout contract
(`workspace_layout.v1`).

Frozen contract: research/DEEPVUE_W2A_WORKSPACE_LAYOUT_CONTRACT_2026-08-26.md,
as amended by Amendment A1 (`lockedVLine`/`split` real-runtime types) and
Amendment A2 (Phase 6 adversarial review of head 8b4d326514f6: real-runtime
grammar, lossless-or-refuse migration, canonicalization, wire mode,
fail-closed projection, key deny-list, optional `requires`, honest
provenance).

Coverage:
  1. schema parses + validates the freeze §1 canonical example
  2. every valid migration vector (incl. the real-Terminal-shaped
     `chart_layout_v2_real_capture`): migrate_legacy(input) deep-equals the
     committed `expected` envelope, twice in a row (determinism)
  3. no-claim law: unclaimed chart-config fields are ABSENT, never null
  4. validate_envelope is `ok` on every valid vector's expected envelope
  5. every invalid vector -> its exact committed `expected_code`, never raises
  6. subscriber_safe_projection: fail-closed result shape, wire-mode output,
     normalized name, no injected key/value ever survives
  7. MANIFEST.json digest recomputes to the pinned `vectors_digest` literal
  8. hostile fuzz across validate_envelope/migrate_legacy/
     subscriber_safe_projection never raises
  A1. `lockedVLine` string|null, `split` enum {1,2,4}
  A2. real-runtime grammar (ruling 1), lossless-or-refuse (ruling 2),
      canonicalization/NaN/surrogates (ruling 4), wire mode (ruling 5),
      fail-closed projection (rulings 6/14), key deny-list (ruling 10),
      optional `requires` (ruling 11), source_revision >=1 + honest
      provenance (rulings 12/13)
"""
from __future__ import annotations

import copy
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
# Re-pinned under Amendment A3 (2026-08-26, reviewer re-verification of
# afe87f98750e): the six new `tolerant_v2_*` probe-C vectors (direction-scoped
# lossless law, ruling 1). No existing vector's bytes changed — the number
# law (ruling 2) and error precedence (ruling 3) touch no committed value.
# Prior (A2) digest d8bc519a3e2f9591... is void.
PINNED_VECTORS_DIGEST = "593e6ad7eccd666c1507e237f3dead3bd2f5aadb6446d2be57bf3af00e4c98f3"

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
    "chart_layout_v2_real_capture.json",
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

# Amendment A3 ruling 1: the reviewer's probe-C family, one committed
# tolerant-read (strict=False) vector per corrupted field.
TOLERANT_VECTOR_NAMES = [
    "tolerant_v2_split3.json",
    "tolerant_v2_activepane7.json",
    "tolerant_v2_panes_empty.json",
    "tolerant_v2_inds_mixed.json",
    "tolerant_v2_charttype_empty.json",
    "tolerant_v2_comparecfg_junk.json",
]


def _widget_config(**overrides):
    """Minimal valid envelope wrapper around one `chart` widget's config,
    used by field-level regression tests (Amendment A1/A2)."""
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
# 6. subscriber-safe projection — Amendment A2 rulings 6/14: FAIL-CLOSED
# result shape ({"ok": True, "envelope": ...} | {"ok": False, "code": ...}).
# The function validates the input in STORED mode first; any failure at all
# refuses outright — never rewrites, downgrades, or partially projects.
# ---------------------------------------------------------------------------

def test_projection_fills_name_and_is_otherwise_1to1():
    envelope = dict(FREEZE_SECTION_1_EXAMPLE)
    result = wl.subscriber_safe_projection(envelope, "My Chart Workspace")
    assert result["ok"] is True
    projected = result["envelope"]
    assert projected["name"] == "My Chart Workspace"
    without_name = {**projected, "name": None}
    assert without_name == envelope


def test_projection_output_validates_in_wire_mode():
    envelope = dict(FREEZE_SECTION_1_EXAMPLE)
    result = wl.subscriber_safe_projection(envelope, "My Chart Workspace")
    assert result["ok"] is True
    assert wl.validate_envelope(result["envelope"], wire=True) == {"ok": True, "errors": []}


def test_stored_non_null_name_still_refuses_in_stored_mode():
    """Amendment A2 ruling 5: wire mode is an ADDITIONAL allowance, never a
    relaxation of the stored-row law. The exact envelope a hostile/buggy
    caller might pass to projection — one whose STORED `name` is already
    non-null — is refused by validate_envelope in (default) stored mode."""
    hostile_stored = {**FREEZE_SECTION_1_EXAMPLE, "name": "should-be-null"}
    assert wl.validate_envelope(hostile_stored)["ok"] is False
    assert wl.validate_envelope(hostile_stored, wire=False)["ok"] is False
    result = wl.subscriber_safe_projection(hostile_stored, "row-name")
    assert result == {"ok": False, "code": "malformed_workspace"}


def test_wire_mode_accepts_a_normalized_non_null_name():
    wire_envelope = {**FREEZE_SECTION_1_EXAMPLE, "name": "My Workspace"}
    assert wl.validate_envelope(wire_envelope, wire=True) == {"ok": True, "errors": []}
    # ...but the SAME object is still refused in stored (default) mode.
    assert wl.validate_envelope(wire_envelope)["ok"] is False


def test_wire_mode_still_refuses_an_unnormalized_name():
    """Wire mode accepts a non-null name, but only an already-normalized
    one — it is not a laxer parser, just a different allowed value."""
    for bad_name in ("  leading space", "trailing space  ", "double  space", "", "x" * 61):
        wire_envelope = {**FREEZE_SECTION_1_EXAMPLE, "name": bad_name}
        result = wl.validate_envelope(wire_envelope, wire=True)
        assert result["ok"] is False, bad_name


def test_projection_refuses_injected_unknown_top_level_key():
    hostile = {**FREEZE_SECTION_1_EXAMPLE, "user_id": "11111111-1111-1111-1111-111111111111"}
    result = wl.subscriber_safe_projection(hostile, "row-name")
    assert result == {"ok": False, "code": "malformed_workspace"}


def test_projection_refuses_injected_unknown_widget_key():
    hostile = copy.deepcopy(FREEZE_SECTION_1_EXAMPLE)
    hostile["widgets"][0]["owner_uuid"] = "22222222-2222-2222-2222-222222222222"
    result = wl.subscriber_safe_projection(hostile, "row-name")
    assert result["ok"] is False
    assert result["code"] in wl.FAILURE_CODES


def test_projection_refuses_injected_path_leak_in_config():
    hostile = copy.deepcopy(FREEZE_SECTION_1_EXAMPLE)
    hostile["widgets"][0]["config"]["path_leak"] = "/Users/attacker/.ssh/id_rsa"
    result = wl.subscriber_safe_projection(hostile, "row-name")
    assert result == {"ok": False, "code": "invalid_widget_config"}


def test_projection_p7_refuses_a_future_unknown_schema():
    hostile = {**FREEZE_SECTION_1_EXAMPLE, "schema": "workspace_layout.v2"}
    result = wl.subscriber_safe_projection(hostile, "row-name")
    assert result == {"ok": False, "code": "unsupported_schema"}


def test_projection_p8_refuses_an_invalid_port_envelope():
    hostile = copy.deepcopy(FREEZE_SECTION_1_EXAMPLE)
    hostile["widgets"][0]["context_in"] = ["no_such_group"]
    result = wl.subscriber_safe_projection(hostile, "row-name")
    assert result == {"ok": False, "code": "invalid_port"}


def test_projection_p10_normalizes_a_whitespace_padded_row_name():
    envelope = dict(FREEZE_SECTION_1_EXAMPLE)
    result = wl.subscriber_safe_projection(envelope, "  My   Workspace   Name  ")
    assert result["ok"] is True
    assert result["envelope"]["name"] == "My Workspace Name"


def test_projection_p10_refuses_an_oversized_row_name_even_after_normalization():
    envelope = dict(FREEZE_SECTION_1_EXAMPLE)
    oversized = "/Users/attacker/" + ("x" * 80)
    result = wl.subscriber_safe_projection(envelope, oversized)
    assert result == {"ok": False, "code": "malformed_workspace"}


def test_projection_refuses_a_non_string_row_name():
    envelope = dict(FREEZE_SECTION_1_EXAMPLE)
    for bad_name in (None, 123, ["a"], {"n": "x"}, ""):
        result = wl.subscriber_safe_projection(envelope, bad_name)
        assert result == {"ok": False, "code": "malformed_workspace"}, bad_name


def test_projection_on_hostile_non_mapping_envelope_refuses_rather_than_raising():
    for hostile in (None, [], 1, "garbage"):
        result = wl.subscriber_safe_projection(hostile, "row-name")
        assert result == {"ok": False, "code": "malformed_workspace"}


def test_projection_on_a_mapping_with_a_bad_schema_reports_unsupported_schema():
    """Amendment A3 ruling 3: the schema-literal gate runs before ANYTHING
    else, so a Mapping whose `schema` disagrees reports `unsupported_schema`
    alone — never `malformed_workspace` from unrelated missing keys."""
    result = wl.subscriber_safe_projection({"schema": {}}, "row-name")
    assert result == {"ok": False, "code": "unsupported_schema"}


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
def test_validate_envelope_wire_mode_never_raises_on_hostile_input(hostile):
    result = wl.validate_envelope(hostile, wire=True)
    assert isinstance(result, dict)
    assert isinstance(result["ok"], bool)


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
    result = wl.subscriber_safe_projection(hostile, "row-name")
    assert isinstance(result, dict)
    assert isinstance(result["ok"], bool)
    if result["ok"]:
        assert result["envelope"]["schema"] == wl.SCHEMA
    else:
        assert result["code"] in wl.FAILURE_CODES


def test_envelope_digest_is_deterministic_and_order_independent():
    a = {"b": 2, "a": 1}
    b = {"a": 1, "b": 2}
    assert wl.envelope_digest(a) == wl.envelope_digest(b)
    assert wl.envelope_digest(a) == wl.envelope_digest(a)


def test_envelope_digest_never_raises_on_hostile_input():
    for hostile in (None, [], "x", {"a": float("nan")}, {"a": float("inf")}, {"\ud800": "x"}):
        digest = wl.envelope_digest(hostile)
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


# ---------------------------------------------------------------------------
# Amendment A2 ruling 1: real-runtime grammar (Phase 6 review B1/M3).
# ---------------------------------------------------------------------------

def test_composite_and_caret_pane_symbols_are_valid():
    envelope = _widget_config(panes=["NVDA+AMD", "^NDX"])
    assert wl.validate_envelope(envelope) == {"ok": True, "errors": []}


def test_venue_qualified_symbol_is_valid():
    envelope = _widget_config(compare=["BINANCE:BTCUSDT"])
    assert wl.validate_envelope(envelope) == {"ok": True, "errors": []}


def test_hyphenated_chart_type_is_valid():
    envelope = _widget_config(chartType="line-markers")
    assert wl.validate_envelope(envelope) == {"ok": True, "errors": []}


def test_underscore_prefixed_indicator_id_is_valid():
    envelope = _widget_config(inds=["_lab"])
    assert wl.validate_envelope(envelope) == {"ok": True, "errors": []}


def test_dotted_suite_param_key_is_valid():
    envelope = _widget_config(indParams={"structure": {"ob.on": True, "ob.showLast": 6}})
    assert wl.validate_envelope(envelope) == {"ok": True, "errors": []}


def test_nested_vis_shape_at_depth_2_is_valid():
    envelope = _widget_config(indParams={
        "ema": {"_vis": {"days": {"on": True, "min": 1, "max": 366}}},
    })
    assert wl.validate_envelope(envelope) == {"ok": True, "errors": []}


def test_param_nesting_at_the_depth_3_boundary_is_valid():
    """depth 1 = `_vis`, depth 2 = `days`, depth 3 = one more wrapper whose
    OWN values must then be leaves — exactly at the allowed boundary."""
    envelope = _widget_config(indParams={
        "ema": {"_vis": {"days": {"extra": {"leaf": 1}}}},
    })
    assert wl.validate_envelope(envelope) == {"ok": True, "errors": []}


def test_param_nesting_beyond_depth_3_is_invalid():
    envelope = _widget_config(indParams={
        "ema": {"_vis": {"days": {"extra": {"deeper": {"leaf": 1}}}}},
    })
    result = wl.validate_envelope(envelope)
    assert result["ok"] is False
    assert {e["code"] for e in result["errors"]} == {"invalid_widget_config"}


def test_too_many_keys_at_a_param_level_is_invalid():
    envelope = _widget_config(indParams={
        "ema": {f"k{i}": i for i in range(65)},
    })
    result = wl.validate_envelope(envelope)
    assert result["ok"] is False
    assert {e["code"] for e in result["errors"]} == {"invalid_widget_config"}


def test_real_capture_vector_preserves_the_non_integral_float():
    vector = _load("chart_layout_v2_real_capture.json")
    assert vector["expected"]["widgets"][0]["config"]["indParams"]["bb"]["mult"] == 1.5


def test_real_capture_vector_preserves_the_real_cmp_cfg_shape():
    vector = _load("chart_layout_v2_real_capture.json")
    cmp_cfg = vector["expected"]["widgets"][0]["config"]["compareCfg"]["QQQ"]
    assert set(cmp_cfg.keys()) == {"color", "lineStyle", "lineWidth", "mode"}


def test_real_capture_vector_includes_lab_indicator_and_line_markers():
    vector = _load("chart_layout_v2_real_capture.json")
    config = vector["expected"]["widgets"][0]["config"]
    assert "_lab" in config["inds"]
    assert config["chartType"] == "line-markers"
    assert config["panes"] == ["NVDA+AMD", "^NDX"]


# ---------------------------------------------------------------------------
# Amendment A2 ruling 2: lossless-or-refuse — migrate_legacy MUST NOT
# silently drop a present-but-invalid owned field.
# ---------------------------------------------------------------------------

def test_realistic_capture_migrates_successfully_under_the_amended_grammar():
    real_capture_input = _load("chart_layout_v2_real_capture.json")["input"]
    result = wl.migrate_legacy(real_capture_input)
    assert result["ok"] is True, result


def test_realistic_capture_with_one_hostile_field_refuses_rather_than_drops():
    """Same real-Terminal-shaped input, but ONE owned field (`bb.mult`) is
    corrupted (a NaN, non-finite float). The old (pre-ruling-2) behavior
    would have silently produced an envelope missing `indParams.bb` (or
    the whole `bb` entry); the amended law refuses outright instead."""
    real_capture_input = copy.deepcopy(_load("chart_layout_v2_real_capture.json")["input"])
    real_capture_input["indParams"]["bb"]["mult"] = float("nan")
    result = wl.migrate_legacy(real_capture_input)
    assert result == {"ok": False, "code": "invalid_widget_config"}


def test_realistic_capture_with_hostile_pane_symbol_refuses():
    real_capture_input = copy.deepcopy(_load("chart_layout_v2_real_capture.json")["input"])
    real_capture_input["panes"] = ["this-is-way-too-long-to-be-a-real-symbol-string"]
    result = wl.migrate_legacy(real_capture_input)
    assert result == {"ok": False, "code": "invalid_widget_config"}


def test_legacy_active_present_but_wrong_type_refuses_rather_than_drops():
    result = wl.migrate_legacy({"active": 12345, "tf": "1D"})
    assert result == {"ok": False, "code": "invalid_widget_config"}


def test_legacy_tf_present_but_wrong_type_refuses_rather_than_drops():
    result = wl.migrate_legacy({"active": "AAPL", "tf": 999})
    assert result == {"ok": False, "code": "invalid_widget_config"}


# ---------------------------------------------------------------------------
# Amendment A2 ruling 4: canonicalization — ensure_ascii=False/allow_nan=False,
# integral-float normalization, lone-surrogate/NaN/Inf handling.
# ---------------------------------------------------------------------------

def test_cjk_string_digest_is_stable_and_does_not_raise():
    envelope = {"widgets": [{"config": {"chartType": "蜡烛图"}}]}
    first = wl.envelope_digest(envelope)
    second = wl.envelope_digest(envelope)
    assert first == second
    assert len(first) == 64


def test_integral_valued_float_digests_identically_to_the_equivalent_int():
    """Closes the Python `20.0` vs JS `20` split (JS has one number type)."""
    with_float = {"widgets": [{"config": {"split": 2.0}}]}
    with_int = {"widgets": [{"config": {"split": 2}}]}
    assert wl.envelope_digest(with_float) == wl.envelope_digest(with_int)


def test_non_integral_float_is_preserved_and_digests_distinctly():
    one_point_five = wl.envelope_digest({"a": 1.5})
    one = wl.envelope_digest({"a": 1})
    two = wl.envelope_digest({"a": 2})
    assert one_point_five not in (one, two)


def test_lone_surrogate_in_an_otherwise_valid_field_is_malformed_workspace():
    """A lone UTF-16 surrogate passes every per-field regex/length check
    (Python `str` can hold one), but can never round-trip through UTF-8 —
    caught only at the whole-envelope canonicalization step."""
    envelope = _widget_config(lockedVLine="\ud800")
    result = wl.validate_envelope(envelope)
    assert result["ok"] is False
    assert "malformed_workspace" in {e["code"] for e in result["errors"]}


def test_nan_indicator_param_is_refused_via_migrate_legacy():
    config = {"panes": ["AAPL"], "indParams": {"ema21": {"period": float("nan")}}}
    result = wl.migrate_legacy(config)
    assert result == {"ok": False, "code": "invalid_widget_config"}


def test_infinite_indicator_param_is_refused_via_migrate_legacy():
    config = {"panes": ["AAPL"], "indParams": {"ema21": {"period": float("inf")}}}
    result = wl.migrate_legacy(config)
    assert result == {"ok": False, "code": "invalid_widget_config"}


def test_nan_indicator_param_is_refused_via_validate_envelope():
    envelope = _widget_config(indParams={"ema21": {"period": float("nan")}})
    result = wl.validate_envelope(envelope)
    assert result["ok"] is False
    assert "invalid_widget_config" in {e["code"] for e in result["errors"]}


# ---------------------------------------------------------------------------
# Amendment A2 ruling 10: key deny-list — __proto__/constructor/prototype
# are never valid identifiers anywhere a key/id is accepted.
# ---------------------------------------------------------------------------

def test_denied_widget_id_is_invalid():
    envelope = copy.deepcopy(FREEZE_SECTION_1_EXAMPLE)
    envelope["widgets"][0]["id"] = "__proto__"
    result = wl.validate_envelope(envelope)
    assert result["ok"] is False
    assert "invalid_widget_config" in {e["code"] for e in result["errors"]}


def test_denied_link_group_name_is_invalid():
    envelope = copy.deepcopy(FREEZE_SECTION_1_EXAMPLE)
    # Added alongside the real group (not referenced by any port), so the
    # ONLY issue this envelope has is the denied group name itself.
    envelope["link_groups"]["constructor"] = {"entity_type": "security"}
    result = wl.validate_envelope(envelope)
    assert result["ok"] is False
    assert "malformed_workspace" in {e["code"] for e in result["errors"]}


def test_denied_indparams_indicator_key_is_invalid():
    envelope = _widget_config(indParams={"prototype": {"length": 20}})
    result = wl.validate_envelope(envelope)
    assert result["ok"] is False
    assert {e["code"] for e in result["errors"]} == {"invalid_widget_config"}


def test_denied_nested_param_key_is_invalid():
    envelope = _widget_config(indParams={"ema21": {"__proto__": {"x": 1}}})
    result = wl.validate_envelope(envelope)
    assert result["ok"] is False
    assert {e["code"] for e in result["errors"]} == {"invalid_widget_config"}


def test_denied_compare_cfg_nested_param_key_is_invalid():
    """compareCfg's OUTER key must already look like a symbol (uppercase),
    so a lowercase `constructor` there is caught by the ordinary pattern
    mismatch, not meaningfully by the deny-list. Exercise the deny-list on
    the nested per-symbol param key instead, where a real field name could
    plausibly collide with it."""
    envelope = _widget_config(compareCfg={"QQQ": {"constructor": "x"}})
    result = wl.validate_envelope(envelope)
    assert result["ok"] is False
    assert {e["code"] for e in result["errors"]} == {"invalid_widget_config"}


# ---------------------------------------------------------------------------
# Amendment A2 ruling 11: `requires` is optional — absent (or empty)
# defaults to floor 1.
# ---------------------------------------------------------------------------

def test_missing_requires_key_entirely_defaults_to_floor_1():
    envelope = copy.deepcopy(FREEZE_SECTION_1_EXAMPLE)
    del envelope["requires"]
    assert wl.validate_envelope(envelope) == {"ok": True, "errors": []}


def test_empty_requires_object_defaults_to_floor_1():
    envelope = copy.deepcopy(FREEZE_SECTION_1_EXAMPLE)
    envelope["requires"] = {}
    assert wl.validate_envelope(envelope) == {"ok": True, "errors": []}


def test_requires_with_unknown_key_is_still_malformed():
    envelope = copy.deepcopy(FREEZE_SECTION_1_EXAMPLE)
    envelope["requires"] = {"floor": 1, "ceiling": 9}
    result = wl.validate_envelope(envelope)
    assert result["ok"] is False
    assert "malformed_workspace" in {e["code"] for e in result["errors"]}


# ---------------------------------------------------------------------------
# Amendment A2 rulings 12/13: source_revision >= 1, and honest provenance
# (null unless the payload actually carried a valid integer schemaVersion;
# a bool is never treated as a version number).
# ---------------------------------------------------------------------------

def test_source_revision_zero_is_malformed():
    envelope = copy.deepcopy(FREEZE_SECTION_1_EXAMPLE)
    envelope["migration"]["source_revision"] = 0
    result = wl.validate_envelope(envelope)
    assert result["ok"] is False
    assert "malformed_workspace" in {e["code"] for e in result["errors"]}


def test_source_revision_negative_is_malformed():
    envelope = copy.deepcopy(FREEZE_SECTION_1_EXAMPLE)
    envelope["migration"]["source_revision"] = -1
    result = wl.validate_envelope(envelope)
    assert result["ok"] is False
    assert "malformed_workspace" in {e["code"] for e in result["errors"]}


def test_v1_without_schema_version_key_gets_null_source_revision():
    result = wl.migrate_legacy({"panes": ["AAPL"]})
    assert result["ok"] is True
    assert result["envelope"]["migration"] == {"source": "chart_layout_v1", "source_revision": None}


def test_v1_with_explicit_schema_version_one_gets_honest_source_revision_one():
    result = wl.migrate_legacy({"panes": ["AAPL"], "schemaVersion": 1})
    assert result["ok"] is True
    assert result["envelope"]["migration"] == {"source": "chart_layout_v1", "source_revision": 1}


def test_boolean_schema_version_is_never_treated_as_a_version_number():
    """`True == 1` in Python, but a boolean is not a version — this must
    fall through to `unsupported_schema`, never be silently coerced."""
    result = wl.migrate_legacy({"panes": ["AAPL"], "schemaVersion": True})
    assert result == {"ok": False, "code": "unsupported_schema"}


def test_boolean_schema_version_two_is_never_treated_as_v2_either():
    # Python has no `bool` equal to 2, but guard the general principle:
    # a non-plain-int schemaVersion must never satisfy the v2 recognizer.
    result = wl.migrate_legacy({"schemaVersion": 2.0, "panes": ["AAPL"]})
    assert result == {"ok": False, "code": "unsupported_schema"}


# ---------------------------------------------------------------------------
# Amendment A3 ruling 1: direction-scoped lossless law. WRITE/IMPORT
# (`strict=True`, the default) keeps A2's lossless-or-refuse exactly.
# READ/RENDER (`strict=False`) is per-field tolerant: a present-but-invalid
# owned field becomes no-claim (absent) and is named in `unclaimed`; every
# OTHER field stays intact; determinism holds in both modes.
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("name", TOLERANT_VECTOR_NAMES)
def test_tolerant_vector_strict_mode_refuses(name):
    vector = _load(name)
    result = wl.migrate_legacy(vector["input"], strict=True)
    assert result == {"ok": False, "code": "invalid_widget_config"}, name


@pytest.mark.parametrize("name", TOLERANT_VECTOR_NAMES)
def test_tolerant_vector_tolerant_mode_matches_committed_envelope_and_unclaimed(name):
    vector = _load(name)
    first = wl.migrate_legacy(vector["input"], strict=False)
    second = wl.migrate_legacy(vector["input"], strict=False)
    assert first == second, f"{name}: tolerant migration is not deterministic"
    assert first["ok"] is True, (name, first)
    assert first["envelope"] == vector["expected"], name
    assert first["unclaimed"] == vector["expected_unclaimed"], name


@pytest.mark.parametrize("name", TOLERANT_VECTOR_NAMES)
def test_tolerant_vector_expected_envelope_passes_validate_envelope(name):
    vector = _load(name)
    result = wl.validate_envelope(vector["expected"])
    assert result == {"ok": True, "errors": []}, (name, result)


@pytest.mark.parametrize("name", TOLERANT_VECTOR_NAMES)
def test_tolerant_vector_names_exactly_one_field_and_keeps_the_rest(name):
    """Every probe-C vector corrupts exactly ONE owned field — the tolerant
    migration must drop that ONE field and keep every other originally
    valid field intact (never over-correct, never drop a second field)."""
    vector = _load(name)
    assert len(vector["expected_unclaimed"]) == 1, name
    dropped_field = vector["expected_unclaimed"][0]
    config = vector["expected"]["widgets"][0]["config"]
    assert dropped_field not in config, name
    # Every OTHER field present in the corrupted input (besides the source
    # recognition keys) that is not the dropped one is still claimed.
    base_fields = set(wl.CHART_CONFIG_FIELDS) & set(vector["input"].keys())
    for field in base_fields - {dropped_field}:
        assert field in config, (name, field)


def test_strict_is_the_default_and_matches_the_pre_a3_call_shape():
    """Existing callers (`migrate_legacy(config)`, one positional arg) must
    keep getting exactly the A2 lossless-or-refuse shape — no `unclaimed`
    key leaking into the strict/default return."""
    result = wl.migrate_legacy({"panes": ["AAPL"], "split": 3})
    assert result == {"ok": False, "code": "invalid_widget_config"}
    ok_result = wl.migrate_legacy({"panes": ["AAPL"]})
    assert set(ok_result.keys()) == {"ok", "envelope"}


def test_tolerant_mode_on_a_fully_clean_input_returns_an_empty_unclaimed_list():
    result = wl.migrate_legacy({"panes": ["AAPL"], "tf": "1D"}, strict=False)
    assert result["ok"] is True
    assert result["unclaimed"] == []


def test_tolerant_mode_legacy_active_scalar_present_but_invalid_is_unclaimed():
    """The legacy `active`->`panes` mapping is itself an owned field under
    the direction-scoped law — tolerant mode no-claims it too."""
    result = wl.migrate_legacy({"active": 12345, "tf": "1D"}, strict=False)
    assert result["ok"] is True
    assert result["unclaimed"] == ["panes"]
    assert "panes" not in result["envelope"]["widgets"][0]["config"]
    assert result["envelope"]["widgets"][0]["config"]["paneTfs"] == ["1D"]


def test_tolerant_mode_legacy_tf_scalar_present_but_invalid_is_unclaimed():
    result = wl.migrate_legacy({"active": "AAPL", "tf": 999}, strict=False)
    assert result["ok"] is True
    assert result["unclaimed"] == ["paneTfs"]
    assert "paneTfs" not in result["envelope"]["widgets"][0]["config"]
    assert result["envelope"]["widgets"][0]["config"]["panes"] == ["AAPL"]


def test_tolerant_mode_never_raises_and_strict_mode_never_raises_either():
    hostile_configs = [
        {"panes": [1, 2, 3]},
        {"schemaVersion": 2, "panes": {"nested": True}},
        {"active": ["a", "b"]},
    ]
    for cfg in hostile_configs:
        strict_result = wl.migrate_legacy(cfg, strict=True)
        assert isinstance(strict_result, dict)
        tolerant_result = wl.migrate_legacy(cfg, strict=False)
        assert isinstance(tolerant_result, dict)


# ---------------------------------------------------------------------------
# Amendment A3 ruling 2: number law — integers bounded to the IEEE-754 safe
# range everywhere numbers occur; non-integral floats valid only within
# 1e-4 <= |x| < 1e12; integral floats still normalize to int.
# ---------------------------------------------------------------------------

def test_integer_beyond_the_safe_range_is_invalid_widget_config():
    envelope = _widget_config(indParams={"ema21": {"period": 9007199254740993}})
    result = wl.validate_envelope(envelope)
    assert result["ok"] is False
    assert "invalid_widget_config" in {e["code"] for e in result["errors"]}


def test_integer_at_the_safe_range_boundary_is_valid():
    envelope = _widget_config(indParams={"ema21": {"period": 9007199254740991}})
    assert wl.validate_envelope(envelope) == {"ok": True, "errors": []}


def test_revision_beyond_the_safe_range_is_malformed():
    envelope = copy.deepcopy(FREEZE_SECTION_1_EXAMPLE)
    envelope["revision"] = 2 ** 60
    result = wl.validate_envelope(envelope)
    assert result["ok"] is False
    assert "malformed_workspace" in {e["code"] for e in result["errors"]}


def test_source_revision_beyond_the_safe_range_is_malformed():
    envelope = copy.deepcopy(FREEZE_SECTION_1_EXAMPLE)
    envelope["migration"]["source_revision"] = 2 ** 60
    result = wl.validate_envelope(envelope)
    assert result["ok"] is False
    assert "malformed_workspace" in {e["code"] for e in result["errors"]}


def test_requires_floor_beyond_the_safe_range_is_malformed_not_unsupported():
    """A truly malformed (astronomically large) floor is a NUMBER-LAW
    violation (`malformed_workspace`), distinct from a well-formed floor
    this reader merely doesn't support yet (`unsupported_floor`). The
    field-level check fires at `$.requires.floor`; the same astronomical
    value also trips the whole-envelope canonicalization backstop at `$`
    (defense in depth — both report the same `malformed_workspace` code)."""
    envelope = copy.deepcopy(FREEZE_SECTION_1_EXAMPLE)
    envelope["requires"] = {"floor": 2 ** 60}
    result = wl.validate_envelope(envelope)
    assert result["ok"] is False
    codes = {e["code"] for e in result["errors"]}
    assert codes == {"malformed_workspace"}
    paths = {e["path"] for e in result["errors"]}
    assert "$.requires.floor" in paths


def test_non_integral_float_just_below_the_floor_is_invalid():
    envelope = _widget_config(indParams={"ema21": {"mult": 1e-5}})
    result = wl.validate_envelope(envelope)
    assert result["ok"] is False
    assert "invalid_widget_config" in {e["code"] for e in result["errors"]}


def test_non_integral_float_at_the_floor_boundary_is_valid():
    envelope = _widget_config(indParams={"ema21": {"mult": 1e-4}})
    assert wl.validate_envelope(envelope) == {"ok": True, "errors": []}


def test_non_integral_float_at_the_ceiling_is_invalid():
    """The ceiling is EXCLUSIVE (`< 1e12`), and applies only to NON-integral
    floats — `1e12` itself has no fractional part (it IS the integer
    1,000,000,000,000, safely within the integer bound), so the ceiling
    must be probed with a value that is both >= 1e12 AND non-integral."""
    envelope = _widget_config(indParams={"ema21": {"mult": 1_000_000_000_000.5}})
    result = wl.validate_envelope(envelope)
    assert result["ok"] is False
    assert "invalid_widget_config" in {e["code"] for e in result["errors"]}


def test_an_integral_valued_float_at_1e12_is_valid_as_an_integer():
    """1e12 has no fractional part — it normalizes to the plain integer
    1,000,000,000,000 and is judged against the (much wider) safe-integer
    bound, not the narrower non-integral-float window."""
    envelope = _widget_config(indParams={"ema21": {"mult": 1e12}})
    assert wl.validate_envelope(envelope) == {"ok": True, "errors": []}


def test_non_integral_float_just_below_the_ceiling_is_valid():
    just_under_ceiling = 999999999999.9  # < 1e12, non-integral
    assert just_under_ceiling < 1e12
    envelope = _widget_config(indParams={"ema21": {"mult": just_under_ceiling}})
    assert wl.validate_envelope(envelope) == {"ok": True, "errors": []}


@pytest.mark.parametrize("value", [1.5, 0.0001, 123456.789])
def test_representative_non_integral_floats_are_accepted(value):
    envelope = _widget_config(indParams={"ema21": {"mult": value}})
    assert wl.validate_envelope(envelope) == {"ok": True, "errors": []}


def test_integral_float_still_normalizes_for_digest_purposes_under_a3():
    with_float = {"a": 20.0}
    with_int = {"a": 20}
    assert wl.envelope_digest(with_float) == wl.envelope_digest(with_int)


def test_integer_out_of_range_via_migrate_legacy_refuses():
    result = wl.migrate_legacy({"panes": ["AAPL"], "indParams": {"ema21": {"period": 2 ** 60}}})
    assert result == {"ok": False, "code": "invalid_widget_config"}


def test_non_integral_float_out_of_range_via_migrate_legacy_tolerant_is_unclaimed():
    result = wl.migrate_legacy(
        {"panes": ["AAPL"], "indParams": {"ema21": {"mult": 1e-5}}}, strict=False,
    )
    assert result["ok"] is True
    assert result["unclaimed"] == ["indParams"]


# ---------------------------------------------------------------------------
# Amendment A3 ruling 3: error precedence — schema literal FIRST (alone),
# then `requires.floor` (alone), only then the general structural sweep. A
# future/incompatible payload is never reported as merely malformed.
# ---------------------------------------------------------------------------

def test_future_schema_with_unknown_key_reports_unsupported_schema_alone():
    envelope = {
        "schema": "workspace_layout.v2",
        "requires": {"floor": 1},
        "revision": 1,
        "name": None,
        "link_groups": {},
        "widgets": [],
        "migration": {"source": "none", "source_revision": None},
        "v2_new_field": 1,
    }
    result = wl.validate_envelope(envelope)
    assert result == {"ok": False, "errors": [{"code": "unsupported_schema", "path": "$.schema"}]}


def test_future_schema_with_unknown_key_reports_unsupported_schema_via_projection_too():
    envelope = {
        "schema": "workspace_layout.v2",
        "requires": {"floor": 1},
        "revision": 1,
        "name": None,
        "link_groups": {},
        "widgets": [],
        "migration": {"source": "none", "source_revision": None},
        "v2_new_field": 1,
    }
    result = wl.subscriber_safe_projection(envelope, "row-name")
    assert result == {"ok": False, "code": "unsupported_schema"}


def test_unsupported_floor_with_unknown_key_reports_unsupported_floor_alone():
    envelope = copy.deepcopy(FREEZE_SECTION_1_EXAMPLE)
    envelope["requires"] = {"floor": 2}
    envelope["some_future_top_level_field"] = 1
    result = wl.validate_envelope(envelope)
    assert result == {"ok": False, "errors": [{"code": "unsupported_floor", "path": "$.requires.floor"}]}


def test_unsupported_floor_via_projection_reports_unsupported_floor_alone():
    envelope = copy.deepcopy(FREEZE_SECTION_1_EXAMPLE)
    envelope["requires"] = {"floor": 2}
    result = wl.subscriber_safe_projection(envelope, "row-name")
    assert result == {"ok": False, "code": "unsupported_floor"}


def test_malformed_requires_shape_still_folds_into_the_general_sweep():
    """A STRUCTURALLY bad `requires` (not merely an unsupported floor) is
    NOT one of the two alone-gates — it reports through the general sweep,
    same as any other structural defect."""
    envelope = copy.deepcopy(FREEZE_SECTION_1_EXAMPLE)
    envelope["requires"] = {"floor": 1, "ceiling": 9}
    result = wl.validate_envelope(envelope)
    assert result["ok"] is False
    assert "malformed_workspace" in {e["code"] for e in result["errors"]}


def test_well_formed_floor_within_support_never_short_circuits_other_errors():
    """A floor of exactly 1 (supported) must NOT suppress genuine other
    errors elsewhere in the object — only an UNSUPPORTED floor gets the
    alone treatment."""
    envelope = copy.deepcopy(FREEZE_SECTION_1_EXAMPLE)
    envelope["widgets"][0]["semantic_lane"] = "bogus-lane"
    result = wl.validate_envelope(envelope)
    assert result["ok"] is False
    assert "invalid_lane" in {e["code"] for e in result["errors"]}
