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
# 18. W1-A registry digest has not drifted
# ---------------------------------------------------------------------------

def test_w1a_registry_digest_has_not_drifted():
    from engine.intelligence_workspace.runtime import build_runtime

    repo_root = pathlib.Path(__file__).resolve().parents[1]
    runtime = build_runtime(repo_root=repo_root)
    assert str(runtime.registry.digest) == (
        "7dff09b790f9f789dfeed80781a7fb62bc138ad4bf801d81664d471c4508d4cf"
    )
