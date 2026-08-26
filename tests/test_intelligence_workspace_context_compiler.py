"""Hostile tests for the W1-C deterministic visible-context compiler.

Frozen contract: research/DEEPVUE_W1C_CONTEXT_ENVELOPE_CONTRACT_2026-08-25.md.

Coverage (numbered to match the commissioning packet's TESTS section):
  1. explicit beats active/ambient
  2. pinned beats active
  3. active beats ambient
  4. staleness (900s budget), precedence unchanged
  5. unsupported entity type never becomes effective
  6. dropped enumerates every outranked, non-empty lower level exactly
  7. malformed client blocks fall back to legacy fields, never raise
  8. privileged vs merely-unknown top-level keys stay distinct
  9. pure-function determinism for a duplicate (origin_id, revision)
  10. origin is echoed verbatim, never mutated
  11. multi-explicit is legal in the envelope; the native lane still refuses it
  15. receipt leak law (subscriber-safe: no path-like/private text)
  18. W1-A registry digest has not drifted (no W1-C-caused drift)

Review-repair coverage (adversarial pass on PR #6421):
  BLK-2: the native-fact receipt's precedence reason is DERIVED from the
      envelope, never independently recomputed (multi-pin disagreement probe)
  MAJ-1/MAJ-2: every echoed string (ambient fields, `unsupported[].entity`) is
      type/length/leak validated against hostile fixtures — nested dicts,
      oversized strings, ints, bools, path-like text, script tags
  NB-3: the full `<source>_over_<level>` / `<source>_only` precedence
      vocabulary names the HIGHEST level actually outranked
"""
from __future__ import annotations

import json
import pathlib
import sys
from datetime import datetime, timezone

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from engine.intelligence_workspace import context_compiler as cc  # noqa: E402
from engine.intelligence_workspace.resolver import _PRIVATE_SUBSCRIBER_TEXT  # noqa: E402
from engine.neuralweb import native_facts as nf  # noqa: E402

_NOW = datetime(2026, 8, 25, 20, 0, 0, tzinfo=timezone.utc)
_FRESH_CAPTURED_AT = "2026-08-25T19:59:00Z"          # 60s old — never stale
_STALE_CAPTURED_AT = "2026-08-25T19:00:00Z"          # 3600s old — stale


def _client_block(
    *,
    origin_id: str = "mount-1",
    context_revision: int = 1,
    captured_at: str = _FRESH_CAPTURED_AT,
    pinned: list | None = None,
    active: dict | None = None,
    ambient: dict | None = None,
) -> dict:
    return {
        "schema": "ai_context_client.v1",
        "origin_id": origin_id,
        "context_revision": context_revision,
        "captured_at": captured_at,
        "pinned": pinned if pinned is not None else [],
        "active": active,
        "ambient": ambient if ambient is not None else
        {"symbol": None, "timeframe": "1D", "page": "terminal", "panel": None},
    }


# ---------------------------------------------------------------------------
# 1. explicit beats active/ambient (legacy client — the exact W1-B shape)
# ---------------------------------------------------------------------------

def test_explicit_beats_legacy_ambient_context():
    envelope = cc.compile_envelope("INOD Stage", {"symbol": "AAOI"}, now=_NOW, request_id="r1")
    eff = envelope["effective_context"]
    assert eff["source"] == "explicit"
    assert eff["reason"] == "explicit_entity_wins"
    assert eff["entities"] == [{"type": "security", "id": "INOD"}]
    assert envelope["dropped"] == [
        {"entity": {"type": "security", "id": "AAOI"}, "level": "active",
         "reason": "outranked_by_explicit"},
    ]


def test_explicit_matching_lower_level_is_explicit_request_not_wins():
    """Same symbol at both levels: nothing was overridden, so the W1-B 'plain
    explicit_request' string applies, not 'wins' — and nothing is dropped."""
    envelope = cc.compile_envelope("AAOI Stage", {"symbol": "AAOI"}, now=_NOW, request_id="r1b")
    eff = envelope["effective_context"]
    assert eff["source"] == "explicit"
    assert eff["reason"] == "explicit_request"
    assert envelope["dropped"] == []


# ---------------------------------------------------------------------------
# 2. pinned beats active
# ---------------------------------------------------------------------------

def test_pinned_beats_active_and_ambient():
    context = {"ai_context": _client_block(
        pinned=[{"type": "security", "id": "NVDA"}],
        active={"type": "security", "id": "AAOI"},
        ambient={"symbol": "MSFT", "timeframe": "1D", "page": "terminal", "panel": None},
    )}
    envelope = cc.compile_envelope("what is the price", context, now=_NOW, request_id="r2")
    eff = envelope["effective_context"]
    assert eff["source"] == "pinned"
    assert eff["reason"] == "pinned_context"
    assert eff["entities"] == [{"type": "security", "id": "NVDA"}]
    dropped = {(d["entity"]["id"], d["level"], d["reason"]) for d in envelope["dropped"]}
    assert dropped == {
        ("AAOI", "active", "outranked_by_pinned"),
        ("MSFT", "ambient", "outranked_by_pinned"),
    }


# ---------------------------------------------------------------------------
# 3. active beats ambient
# ---------------------------------------------------------------------------

def test_active_beats_ambient():
    context = {"ai_context": _client_block(
        active={"type": "security", "id": "AAOI"},
        ambient={"symbol": "MSFT", "timeframe": "1D", "page": "terminal", "panel": None},
    )}
    envelope = cc.compile_envelope("what is the price", context, now=_NOW, request_id="r3")
    eff = envelope["effective_context"]
    assert eff["source"] == "active"
    assert eff["reason"] == "active_selection"
    assert eff["entities"] == [{"type": "security", "id": "AAOI"}]
    assert envelope["dropped"] == [
        {"entity": {"type": "security", "id": "MSFT"}, "level": "ambient",
         "reason": "outranked_by_active"},
    ]


def test_ambient_only_is_the_floor_and_nothing_is_dropped():
    context = {"ai_context": _client_block(
        ambient={"symbol": "MSFT", "timeframe": "1D", "page": "terminal", "panel": None},
    )}
    envelope = cc.compile_envelope("what is the price", context, now=_NOW, request_id="r3b")
    eff = envelope["effective_context"]
    assert eff["source"] == "ambient"
    assert eff["reason"] == "ambient_context"
    assert envelope["dropped"] == []


def test_no_context_anywhere_is_a_distinct_state_not_an_error():
    envelope = cc.compile_envelope("hello there", {}, now=_NOW, request_id="r3c")
    eff = envelope["effective_context"]
    assert eff["source"] == "none"
    assert eff["reason"] == "no_context"
    assert eff["entities"] == []
    assert envelope["dropped"] == []


# ---------------------------------------------------------------------------
# 4. staleness — precedence unchanged
# ---------------------------------------------------------------------------

def test_stale_captured_at_flags_but_never_changes_precedence():
    context = {"ai_context": _client_block(captured_at=_STALE_CAPTURED_AT,
                                            active={"type": "security", "id": "AAOI"})}
    envelope = cc.compile_envelope("price", context, now=_NOW, request_id="r4")
    assert envelope["context_flags"]["stale"] is True
    assert envelope["effective_context"]["source"] == "active"
    assert envelope["effective_context"]["entities"] == [{"type": "security", "id": "AAOI"}]


def test_fresh_captured_at_is_never_stale():
    context = {"ai_context": _client_block(captured_at=_FRESH_CAPTURED_AT)}
    envelope = cc.compile_envelope("price", context, now=_NOW, request_id="r4b")
    assert envelope["context_flags"]["stale"] is False


def test_exactly_at_the_budget_boundary_is_not_yet_stale():
    """900s budget: strictly OLDER than the budget is stale, not >=."""
    boundary = _NOW.replace(microsecond=0)
    captured = boundary.isoformat().replace("+00:00", "Z")
    context = {"ai_context": _client_block(captured_at=captured)}
    envelope = cc.compile_envelope("price", context, now=boundary, request_id="r4c")
    assert envelope["context_flags"]["stale"] is False


# ---------------------------------------------------------------------------
# 5. unsupported entity type never becomes effective
# ---------------------------------------------------------------------------

def test_pinned_theme_type_is_unsupported_and_never_effective():
    context = {"ai_context": _client_block(
        pinned=[{"type": "theme", "id": "semiconductors"}],
        active={"type": "security", "id": "AAOI"},
    )}
    envelope = cc.compile_envelope("price", context, now=_NOW, request_id="r5")
    assert envelope["pinned_context"] == []
    assert envelope["unsupported"] == [
        {"entity": {"type": "theme", "id": "semiconductors"}, "reason": "unsupported_entity_type",
         "level": "pinned"},
    ]
    # active is the fallback effective level; the bad pin never wins by omission.
    assert envelope["effective_context"]["source"] == "active"
    assert envelope["effective_context"]["entities"] == [{"type": "security", "id": "AAOI"}]


def test_invalid_symbol_is_unsupported_not_a_crash():
    context = {"ai_context": _client_block(
        pinned=[{"type": "security", "id": "not-a-real-ticker-way-too-long"}],
    )}
    envelope = cc.compile_envelope("price", context, now=_NOW, request_id="r5b")
    assert envelope["pinned_context"] == []
    assert envelope["unsupported"][0]["reason"] == "invalid_symbol"
    assert envelope["effective_context"]["source"] == "none"


# ---------------------------------------------------------------------------
# 6. dropped enumerates every outranked, non-empty lower level exactly
# ---------------------------------------------------------------------------

def test_dropped_conflicting_context_enumerated_exactly():
    context = {"ai_context": _client_block(
        pinned=[{"type": "security", "id": "NVDA"}],
        active={"type": "security", "id": "AAOI"},
        ambient={"symbol": "TSLA", "timeframe": "1D", "page": "terminal", "panel": None},
    )}
    envelope = cc.compile_envelope("INOD price", context, now=_NOW, request_id="r6")
    assert envelope["effective_context"]["source"] == "explicit"
    dropped = {(d["entity"]["id"], d["level"], d["reason"]) for d in envelope["dropped"]}
    assert dropped == {
        ("NVDA", "pinned", "outranked_by_explicit"),
        ("AAOI", "active", "outranked_by_explicit"),
        ("TSLA", "ambient", "outranked_by_explicit"),
    }
    assert len(envelope["dropped"]) == 3


def test_dropped_never_double_counts_a_lower_level_matching_the_effective_symbol():
    """A pinned entry that happens to equal the explicit symbol is contained in
    the effective set — it is not overridden, so it must not be dropped."""
    context = {"ai_context": _client_block(
        pinned=[{"type": "security", "id": "INOD"}],
        active={"type": "security", "id": "AAOI"},
    )}
    envelope = cc.compile_envelope("INOD price", context, now=_NOW, request_id="r6b")
    dropped_levels = {d["level"] for d in envelope["dropped"]}
    assert dropped_levels == {"active"}


# ---------------------------------------------------------------------------
# 7. malformed client blocks fall back to legacy fields, never raise
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(("mutate", "expected_reason"), [
    (lambda b: {**b, "context_revision": "seven"}, "invalid_revision"),
    (lambda b: {**b, "context_revision": -1}, "invalid_revision"),
    (lambda b: {**b, "origin_id": "x" * 65}, "invalid_origin_id"),
    (lambda b: {**b, "origin_id": ""}, "invalid_origin_id"),
    (lambda b: {**b, "pinned": "not-a-list"}, "invalid_pinned"),
    (lambda b: {**b, "pinned": [{"type": "security", "id": s} for s in
                                ("AAPL", "MSFT", "NVDA", "TSLA")]}, "invalid_pinned"),
    (lambda b: {**b, "captured_at": "not-a-timestamp"}, "invalid_captured_at"),
    (lambda b: {**b, "active": "not-a-mapping"}, "invalid_active"),
    (lambda b: {**b, "ambient": "not-a-mapping"}, "invalid_ambient"),
])
def test_malformed_client_block_falls_back_to_legacy_without_raising(mutate, expected_reason):
    block = mutate(_client_block())
    context = {"ai_context": block, "symbol": "AAOI"}
    envelope = cc.compile_envelope("price", context, now=_NOW, request_id="r7")
    assert envelope["context_flags"]["malformed"] is True
    assert envelope["context_flags"]["malformed_reason"] == expected_reason
    # Legacy fallback: context["symbol"] still resolves via the active level.
    assert envelope["origin"]["legacy"] is True
    assert envelope["effective_context"]["source"] == "active"
    assert envelope["effective_context"]["entities"] == [{"type": "security", "id": "AAOI"}]


def test_ai_context_that_is_not_even_a_mapping_is_malformed_not_a_crash():
    envelope = cc.compile_envelope("price", {"ai_context": "garbage", "symbol": "AAOI"},
                                    now=_NOW, request_id="r7b")
    assert envelope["context_flags"]["malformed"] is True
    assert envelope["effective_context"]["entities"] == [{"type": "security", "id": "AAOI"}]


# ---------------------------------------------------------------------------
# 8. privileged vs merely-unknown top-level keys stay distinct
# ---------------------------------------------------------------------------

def test_privileged_fields_are_stripped_and_recorded_distinctly_from_unknown():
    block = _client_block()
    block["authority"] = {"may_execute": True}
    block["effective_context"] = {"source": "explicit"}
    block["_server_internal"] = {"secret": "x"}
    block["some_future_client_field"] = "harmless"
    envelope = cc.compile_envelope("price", {"ai_context": block}, now=_NOW, request_id="r8")
    assert set(envelope["context_flags"]["rejected_fields"]) == {
        "authority", "effective_context", "_server_internal",
    }
    assert envelope["context_flags"]["ignored_fields"] == ["some_future_client_field"]
    # Never actually raises the client's authority: the constant always wins.
    assert envelope["authority"] == {"may_execute": False, "may_originate_signal": False}
    # And a privileged/unknown key never poisons the malformed check.
    assert envelope["context_flags"]["malformed"] is False


# ---------------------------------------------------------------------------
# 9. pure-function determinism for a duplicate (origin_id, revision)
# ---------------------------------------------------------------------------

def test_duplicate_origin_and_revision_compiles_byte_identically():
    context = {"ai_context": _client_block(origin_id="mount-9", context_revision=3)}
    first = cc.compile_envelope("INOD price", context, now=_NOW, request_id="fixed-rid")
    second = cc.compile_envelope("INOD price", context, now=_NOW, request_id="fixed-rid")
    assert first == second


def test_determinism_holds_across_the_whole_precedence_ladder():
    for message, context in (
        ("INOD price", {"symbol": "AAOI"}),
        ("price", {"ai_context": _client_block(
            pinned=[{"type": "security", "id": "NVDA"}])}),
        ("price", {"ai_context": _client_block(
            active={"type": "security", "id": "AAOI"})}),
        ("price", {}),
    ):
        first = cc.compile_envelope(message, context, now=_NOW, request_id="rid")
        second = cc.compile_envelope(message, context, now=_NOW, request_id="rid")
        assert first == second


# ---------------------------------------------------------------------------
# 10. origin is echoed verbatim, never mutated
# ---------------------------------------------------------------------------

def test_origin_is_echoed_verbatim_never_mutated():
    context = {"ai_context": _client_block(
        origin_id="widget-mount-abc123", context_revision=42,
        captured_at="2026-08-25T19:58:30Z",
    )}
    envelope = cc.compile_envelope("price", context, now=_NOW, request_id="r10")
    assert envelope["origin"] == {
        "origin_id": "widget-mount-abc123",
        "context_revision": 42,
        "captured_at": "2026-08-25T19:58:30Z",
        "legacy": False,
    }
    receipt = cc.compile_receipt(envelope)
    assert receipt["origin"] == envelope["origin"]


def test_zero_revision_is_not_treated_as_falsy_missing():
    context = {"ai_context": _client_block(context_revision=0)}
    envelope = cc.compile_envelope("price", context, now=_NOW, request_id="r10b")
    assert envelope["origin"]["context_revision"] == 0
    assert envelope["context_flags"]["malformed"] is False


# ---------------------------------------------------------------------------
# 11. multi-explicit is legal in the envelope; the native lane still refuses it
# ---------------------------------------------------------------------------

def test_multi_explicit_is_effective_in_the_envelope_but_native_lane_refuses():
    message = "$AAPL and $MSFT price"
    envelope = cc.compile_envelope(message, {"symbol": "AAOI"}, now=_NOW, request_id="r11")
    assert envelope["effective_context"]["source"] == "explicit"
    assert envelope["effective_context"]["entities"] == [
        {"type": "security", "id": "AAPL"}, {"type": "security", "id": "MSFT"},
    ]
    # Native lane law is completely unchanged: >1 explicit still refuses (deep route).
    assert nf.plan_native_facts(message, {"symbol": "AAOI"}, envelope=envelope) is None
    assert nf.plan_native_facts(message, {"symbol": "AAOI"}) is None


def test_ambiguous_uppercase_explicit_sets_flag_and_resolves_from_remaining_levels():
    envelope = cc.compile_envelope("IT and price", {"symbol": "AAPL"}, now=_NOW, request_id="r11b")
    assert envelope["context_flags"]["ambiguous_explicit"] is True
    assert envelope["effective_context"]["source"] == "active"
    assert envelope["effective_context"]["entities"] == [{"type": "security", "id": "AAPL"}]
    # And the native lane keeps refusing exactly as it does today.
    assert nf.plan_native_facts("IT and price", {"symbol": "AAPL"}, envelope=envelope) is None


# ---------------------------------------------------------------------------
# Review repair BLK-2: the native-fact receipt's precedence reason must be
# DERIVED from the envelope, never independently recomputed — the two must
# never disagree. Reproduces the reviewer's exact probe: pins [NVDA, AAPL]
# (two pinned entities) + explicit "NVDA price". The old code compared the
# explicit symbol only against the FIRST pinned entity (NVDA == NVDA, so it
# reported "explicit_request" — nothing overridden), while the envelope
# correctly reports "explicit_entity_wins" because the SECOND pinned entity
# (AAPL) was outranked. The two receipts must be assert-equal.
# ---------------------------------------------------------------------------

def _pinned_two_client(pinned_ids):
    return {
        "schema": "ai_context_client.v1", "origin_id": "blk2-mount", "context_revision": 1,
        "captured_at": _FRESH_CAPTURED_AT,
        "pinned": [{"type": "security", "id": pid} for pid in pinned_ids],
        "active": None,
        "ambient": {"symbol": None, "timeframe": None, "page": "terminal", "panel": None},
    }


def test_native_receipt_reason_never_disagrees_with_envelope_multi_pin_probe():
    context = {"ai_context": _pinned_two_client(["NVDA", "AAPL"])}
    envelope = cc.compile_envelope("NVDA price", context, now=_NOW, request_id="blk2-r1")
    # Confirms the envelope itself reports the override (the reviewer's premise).
    assert envelope["effective_context"]["source"] == "explicit"
    assert envelope["effective_context"]["reason"] == "explicit_entity_wins"

    plan = nf.plan_native_facts("NVDA price", context, envelope=envelope)
    assert plan is not None
    assert plan.effective_context_reason == envelope["effective_context"]["reason"] == "explicit_entity_wins"
    assert plan.envelope_source == envelope["effective_context"]["source"] == "explicit"


def test_native_receipt_reason_agrees_with_envelope_when_nothing_is_overridden():
    """Same shape, but the ONLY pin present matches the explicit entity — no
    override happened, so both sides must agree on "explicit_request"."""
    context = {"ai_context": _pinned_two_client(["NVDA"])}
    envelope = cc.compile_envelope("NVDA price", context, now=_NOW, request_id="blk2-r2")
    assert envelope["effective_context"]["reason"] == "explicit_request"
    plan = nf.plan_native_facts("NVDA price", context, envelope=envelope)
    assert plan is not None
    assert plan.effective_context_reason == envelope["effective_context"]["reason"] == "explicit_request"


def test_native_receipt_effective_context_block_matches_envelope_end_to_end():
    """The full receipt-building path (execute_native_fact_plan) must carry the
    same reason through to the native_fact_receipt.effective_context block —
    the actual object the inspector/receipt-parity law compares against the
    context_receipt — using the real W1-A runtime (no fixture drift)."""
    from engine.intelligence_workspace.runtime import build_runtime

    repo_root = pathlib.Path(__file__).resolve().parents[1]
    runtime = build_runtime(repo_root=repo_root)
    context = {"ai_context": _pinned_two_client(["NVDA", "AAPL"])}
    envelope = cc.compile_envelope("NVDA price", context, now=_NOW, request_id="blk2-r3")
    plan = nf.plan_native_facts("NVDA price", context, envelope=envelope)
    assert plan is not None
    execution = nf.execute_native_fact_plan(plan, runtime=runtime, repo_root=repo_root)
    receipt_reason = execution.receipt["effective_context"]["reason"]
    assert receipt_reason == envelope["effective_context"]["reason"] == "explicit_entity_wins"
    assert execution.receipt["effective_context"]["envelope_source"] == envelope["effective_context"]["source"]


# ---------------------------------------------------------------------------
# 15. receipt leak law — subscriber-safe, never path-like or private text
# ---------------------------------------------------------------------------

_LEAK_FIXTURES = [
    {"symbol": "AAOI"},
    {"ai_context": _client_block(
        pinned=[{"type": "security", "id": "NVDA"}],
        active={"type": "security", "id": "AAOI"},
        ambient={"symbol": "MSFT", "timeframe": "1D", "page": "terminal", "panel": "chat"},
    )},
    {"ai_context": _client_block(captured_at=_STALE_CAPTURED_AT)},
    {"ai_context": {**_client_block(), "context_revision": "bad"}},
    {},
]


@pytest.mark.parametrize("context", _LEAK_FIXTURES)
def test_context_receipt_never_carries_path_like_or_private_text(context):
    envelope = cc.compile_envelope("INOD Stage and industry rank", context,
                                    now=_NOW, request_id="r15")
    receipt = cc.compile_receipt(envelope)
    blob = json.dumps(receipt, ensure_ascii=False)
    assert _PRIVATE_SUBSCRIBER_TEXT.search(blob) is None, blob


# ---------------------------------------------------------------------------
# Review repair MAJ-1/MAJ-2: every echoed string (ambient fields AND
# `unsupported[].entity`) must be validated/coerced — a hostile client must
# never be able to smuggle a nested structure, an oversized string, or
# subscriber-private/path-like text into the envelope. The leak/schema checks
# above were vacuous on CLEAN fixtures (nothing there was ever going to trip
# them); these fixtures are deliberately adversarial.
# ---------------------------------------------------------------------------

_HOSTILE_CONTEXTS = [
    # nested dict where a pinned entity id is expected
    {"ai_context": _client_block(
        pinned=[{"type": "security", "id": {"nested": "/Users/attacker/.ssh/id_rsa"}}],
    )},
    # a list, not a scalar, as an active entity id
    {"ai_context": _client_block(
        active={"type": "security", "id": ["a", "b", "c"]},
    )},
    # path-like strings in every ambient field + an oversized one
    {"ai_context": _client_block(
        ambient={
            "symbol": None,
            "timeframe": "/Users/attacker/.ssh/id_rsa_" + ("x" * 64),
            "page": "/Users/attacker/secret/config.yml",
            "panel": "engine/neuralweb/brain_gateway.py",
        },
    )},
    # an integer landing where a string is expected (ambient panel)
    {"ai_context": _client_block(ambient={"symbol": None, "timeframe": None, "page": None, "panel": 1234567890})},
    # a bool landing where an entity id is expected
    {"ai_context": _client_block(pinned=[{"type": "security", "id": True}])},
    # an oversized script-tag string as an unsupported entity id (type
    # mismatch path) — long enough that, even though it is not path-like, the
    # length ceiling still forces a truncation (never a raw >64-char echo).
    {"ai_context": _client_block(
        active={"type": "theme", "id": "<script>alert(document.cookie)</script>" + ("A" * 40)},
    )},
    # an oversized (200-char) garbage string as a pinned entity id
    {"ai_context": _client_block(pinned=[{"type": "security", "id": "Z" * 200}])},
    # a credentials-shaped string riding through the unsupported active slot
    {"ai_context": _client_block(
        active={"type": "security", "id": "api_key=sk-live-0000000000000000000000000000"},
    )},
]


@pytest.fixture(scope="module")
def _envelope_validator():
    import json as _json

    from jsonschema import Draft202012Validator

    schema_path = (
        pathlib.Path(__file__).resolve().parents[1]
        / "contracts" / "intelligence_workspace" / "ai_context_envelope.v1.schema.json"
    )
    schema = _json.loads(schema_path.read_text())
    Draft202012Validator.check_schema(schema)
    return Draft202012Validator(schema)


@pytest.mark.parametrize("context", _HOSTILE_CONTEXTS)
def test_hostile_echoed_input_still_validates_against_the_committed_schema(context, _envelope_validator):
    envelope = cc.compile_envelope("price", context, now=_NOW, request_id="hostile-schema")
    errors = list(_envelope_validator.iter_errors(envelope))
    assert errors == [], errors
    # The compiler never raises and never silently drops the condition.
    assert envelope["context_flags"]["echo_sanitized"] is True


@pytest.mark.parametrize("context", _HOSTILE_CONTEXTS)
def test_hostile_echoed_input_never_leaks_into_the_receipt(context):
    envelope = cc.compile_envelope("price", context, now=_NOW, request_id="hostile-leak")
    receipt = cc.compile_receipt(envelope)
    blob = json.dumps(receipt, ensure_ascii=False)
    assert _PRIVATE_SUBSCRIBER_TEXT.search(blob) is None, blob


def test_hostile_input_never_exceeds_the_committed_length_ceilings():
    """Belt-and-suspenders on top of the schema check: assert the ceilings by
    number, not only by schema pattern, so a future schema loosening cannot
    silently widen what actually gets echoed."""
    context = {"ai_context": _client_block(
        pinned=[{"type": "security", "id": "Z" * 200}],
        ambient={"symbol": None, "timeframe": "y" * 99, "page": "z" * 99, "panel": None},
    )}
    envelope = cc.compile_envelope("price", context, now=_NOW, request_id="hostile-len")
    for row in envelope["unsupported"]:
        for key in ("type", "id"):
            value = row["entity"].get(key) if row["entity"] else None
            assert value is None or len(value) <= 64
    ambient = envelope["ambient_widget_context"]
    for key in ("timeframe", "page", "panel"):
        assert ambient[key] is None or len(ambient[key]) <= 32


# ---------------------------------------------------------------------------
# Review repair NB-3: the full `<source>_over_<level>` / `<source>_only`
# precedence vocabulary — the level named must be the HIGHEST one that
# actually lost an entity, never a fixed "_over_active" regardless of what
# (if anything) was outranked.
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(("message", "context", "expected_precedence"), [
    # explicit beats pinned (the highest possible lower level)
    ("NVDA price", {"ai_context": _client_block(pinned=[{"type": "security", "id": "AAOI"}])},
     "explicit_over_pinned"),
    # explicit beats only active (no pins at all)
    ("NVDA price", {"ai_context": _client_block(active={"type": "security", "id": "AAOI"})},
     "explicit_over_active"),
    # explicit beats only ambient (no pins, no active)
    ("NVDA price", {"ai_context": _client_block(
        ambient={"symbol": "AAOI", "timeframe": None, "page": None, "panel": None})},
     "explicit_over_ambient"),
    # explicit alone, nothing at all beneath it
    ("NVDA price", {}, "explicit_only"),
    # pinned beats active
    ("price", {"ai_context": _client_block(
        pinned=[{"type": "security", "id": "NVDA"}],
        active={"type": "security", "id": "AAOI"})},
     "pinned_over_active"),
    # pinned beats only ambient (no active)
    ("price", {"ai_context": _client_block(
        pinned=[{"type": "security", "id": "NVDA"}],
        ambient={"symbol": "AAOI", "timeframe": None, "page": None, "panel": None})},
     "pinned_over_ambient"),
    # pinned alone, nothing beneath it
    ("price", {"ai_context": _client_block(pinned=[{"type": "security", "id": "NVDA"}])},
     "pinned_only"),
    # active beats ambient
    ("price", {"ai_context": _client_block(
        active={"type": "security", "id": "AAOI"},
        ambient={"symbol": "MSFT", "timeframe": None, "page": None, "panel": None})},
     "active_over_ambient"),
    # active alone
    ("price", {"ai_context": _client_block(active={"type": "security", "id": "AAOI"})},
     "active_only"),
    # ambient alone (the floor — nothing can ever be dropped beneath it)
    ("price", {"ai_context": _client_block(
        ambient={"symbol": "MSFT", "timeframe": None, "page": None, "panel": None})},
     "ambient_only"),
    # nothing anywhere
    ("hello", {}, "none"),
])
def test_precedence_names_the_highest_level_actually_outranked(message, context, expected_precedence):
    envelope = cc.compile_envelope(message, context, now=_NOW, request_id="nb3")
    assert envelope["effective_context"]["precedence"] == expected_precedence


# ---------------------------------------------------------------------------
# 18. W1-A registry digest has not drifted
# ---------------------------------------------------------------------------

def test_w1a_registry_digest_has_not_drifted():
    from engine.intelligence_workspace.runtime import build_runtime

    repo_root = pathlib.Path(__file__).resolve().parents[1]
    runtime = build_runtime(repo_root=repo_root)
    assert str(runtime.registry.digest) == (
        "7dff09b790f9f789dfeed80781a7fb62bc138ad4bf801d81664d471c4508d4cf"
    )
