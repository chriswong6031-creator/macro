"""Guards for `config/growth_events.yml`, the canonical growth-event vocabulary.

The registry's job is to stop six implementation waves from inventing six vocabularies
(research/MASTERMIND_GROWTH_INSTRUMENTATION_SPEC.md). A registry nothing checks would
drift from the running beacon on day one, so this file pins three properties:

1. **It cannot drift from production — in either direction (W2-1, landed by
   WS:COMMERCIAL-ACTIVATION CA1A).** The whitelist `app/main.py::_MM_EVENT_TYPES` is
   now DERIVED from this file via lib/growth_registry: the beacon accepts a wire IFF
   the registry marks it `status: live`. Both directions are asserted below, plus an
   AST guard that no hardcoded set literal creeps back in.
2. **It is well-formed.** Unique names, unique wire values, closed enums, a declared
   funnel stage, typed properties, and a stated purpose — because "no transition, no
   event" is only enforceable if `purpose` is mandatory.
3. **`insider` never becomes a telemetry value.** lib/tiers.py documents that the legacy
   tier string keeps arriving indefinitely and must be normalized at every boundary. If
   it reaches an event property, every tier-segmented number splits in two, invisibly.
"""
from __future__ import annotations

import re
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
REGISTRY = ROOT / "config" / "growth_events.yml"

_SCALAR_TYPES = {"string", "int", "bool", "float"}
_NAME_RE = re.compile(r"^[a-z][a-z0-9_]*(\.[a-z][a-z0-9_]*)*$")


def _registry() -> dict:
    return yaml.safe_load(REGISTRY.read_text(encoding="utf-8"))


def _live_beacon_types() -> set[str]:
    """The whitelist, read from the SAME derivation the beacon uses (W2-1, CA1A).

    Before CA1A this parsed app/main.py's hardcoded set literal with `ast` (importing
    app.main would pull FastAPI into a config test). W2-1 removed the literal: the
    whitelist is now derived from the registry via lib/growth_registry — yaml + stdlib
    only, so importing it here keeps this a config test while reading production's
    actual derivation rather than a re-typed copy.
    `test_whitelist_is_derived_from_the_registry_not_hardcoded` guards the other half:
    that app/main.py really binds _MM_EVENT_TYPES to this derivation and no set literal
    has crept back in.
    """
    from lib import growth_registry

    value = growth_registry.accepted_wires()
    assert isinstance(value, frozenset) and value
    return set(value)


def _mm_event_types_assignment() -> "object":
    """The ast node assigned to _MM_EVENT_TYPES in app/main.py (source-level, no import)."""
    import ast

    tree = ast.parse((ROOT / "app" / "main.py").read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign) and any(
            isinstance(t, ast.Name) and t.id == "_MM_EVENT_TYPES" for t in node.targets
        ):
            return node.value
    raise AssertionError("could not locate _MM_EVENT_TYPES in app/main.py — was it renamed?")


def test_whitelist_is_derived_from_the_registry_not_hardcoded():
    """W2-1 mutation guard (CA1A acceptance test 28): reintroducing a hardcoded-only
    whitelist — `_MM_EVENT_TYPES = {...}` — turns this red. The assignment must be a
    call into lib/growth_registry, because a hand-typed set is exactly the second
    vocabulary this registry exists to forbid.
    """
    import ast

    value = _mm_event_types_assignment()
    assert not isinstance(value, (ast.Set, ast.SetComp, ast.List, ast.Tuple)), (
        "_MM_EVENT_TYPES is a literal again — the whitelist must be derived from "
        "config/growth_events.yml via lib/growth_registry (W2-1)"
    )
    assert isinstance(value, ast.Call), "_MM_EVENT_TYPES must be bound to a derivation call"
    func = value.func
    assert isinstance(func, ast.Attribute) and func.attr == "accepted_wires" and (
        isinstance(func.value, ast.Name) and func.value.id == "growth_registry"
    ), "_MM_EVENT_TYPES must come from growth_registry.accepted_wires()"


def test_accepted_wires_are_exactly_the_live_registry_wires(tmp_path):
    """W2-1 both directions (supersedes the pre-CA1A 'deliberately not asserted yet'):
    the beacon accepts a wire IFF the registry marks it live — proven against the real
    registry AND against a fixture flip, so the derivation is live, not a frozen copy.
    """
    from lib import growth_registry

    reg = _registry()
    live = {e["wire"] for e in reg["events"] if e["status"] == "live"}
    assert set(growth_registry.accepted_wires()) == live

    fixture = tmp_path / "growth_events.yml"
    fixture.write_text(
        "schema: growth_events.v1\nenums: {}\nfunnel: [{id: none}]\n"
        "events:\n"
        "  - {name: a.live, wire: a_live, status: live, source: client, funnel: none, purpose: p, properties: {}}\n"
        "  - {name: b.planned, wire: b_planned, status: planned, source: client, funnel: none, purpose: p, properties: {}}\n",
        encoding="utf-8",
    )
    assert set(growth_registry.accepted_wires(fixture)) == {"a_live"}
    assert set(growth_registry.envelope_v1_wires(fixture)) == set()


def test_schema_and_shape():
    reg = _registry()
    assert reg["schema"] == "growth_events.v1"
    for section in ("enums", "funnel", "events"):
        assert reg.get(section), f"missing section: {section}"
    assert isinstance(reg["events"], list) and reg["events"]


def test_every_live_beacon_type_is_registered_as_live():
    """Property 1 — the registry cannot be born out of step with production."""
    reg = _registry()
    live_wires = {e["wire"] for e in reg["events"] if e["status"] == "live"}
    missing = _live_beacon_types() - live_wires
    assert not missing, (
        f"event types accepted by app/main.py but absent from {REGISTRY.name}: "
        f"{sorted(missing)} — add them with status: live and their existing wire value"
    )


def test_live_wire_values_are_frozen_to_the_beacon():
    """A live wire value that is NOT in the whitelist would be dropped at /api/collect.

    It would also orphan its own history: rows already in `analytics_events` carry the
    old string, so renaming a live wire value silently splits a metric in two.
    """
    reg = _registry()
    beacon = _live_beacon_types()
    for event in reg["events"]:
        if event["status"] == "live":
            assert event["wire"] in beacon, (
                f"{event['name']}: wire '{event['wire']}' is marked live but the beacon "
                "does not accept it"
            )


def test_names_and_wires_are_unique_and_well_formed():
    reg = _registry()
    names = [e["name"] for e in reg["events"]]
    wires = [e["wire"] for e in reg["events"]]
    assert len(names) == len(set(names)), "duplicate event name"
    assert len(wires) == len(set(wires)), "duplicate wire value"
    for name in names:
        assert _NAME_RE.match(name), f"malformed event name: {name}"
    # `wire` was previously checked only for uniqueness (and, for live entries, beacon
    # membership), so `wire: 42`, `wire:` (null — `{None}` stays unique) or a value with
    # spaces all passed. The wire value is what lands in `analytics_events.event_type`
    # and what every downstream query joins on.
    for wire in wires:
        assert isinstance(wire, str) and _NAME_RE.match(wire), f"malformed wire: {wire!r}"


#: The live name↔wire pairs, pinned explicitly. Set equality alone cannot catch a SWAP
#: (exchanging two live entries' wires keeps the set identical while silently re-pointing
#: two metrics at each other's history). These are frozen: the rows already in
#: `analytics_events` carry these strings. Adding a genuinely NEW live pair (a new wire
#: type app/main.py starts accepting) is fine — append it here in the SAME commit; what
#: this pins is that none of the EXISTING pairs silently swaps to a different wire.
#: Flow Observatory V2 W7 (research/flow_observatory/W7_SPEC.md) added
#: flow_observatory.interacted/flowobs 2026-09.
_LIVE_PAIRS = {
    "session.start": "session_start",
    "page.viewed": "pageview",
    "route.changed": "route",
    "ad.exposed": "ad_exposure",
    "ticker.viewed": "ticker_view",
    "search.performed": "search",
    "terminal.jumped": "terminal_jump",
    "element.clicked": "click",
    "page.scrolled": "scroll",
    "session.heartbeat": "heartbeat",
    "session.exit": "exit",
    "flow_observatory.interacted": "flowobs",
    # WS:COMMERCIAL-ACTIVATION CA1A (2026-09): the four early-funnel envelope-v1
    # events. Planned wires had no history to orphan, so name == wire by design.
    "intelligence.viewed": "intelligence.viewed",
    "personal.act": "personal.act",
    "watchlist.symbol_added": "watchlist.symbol_added",
    "watchlist.saved": "watchlist.saved",
}


def test_live_name_to_wire_mapping_is_frozen():
    reg = _registry()
    live = {e["name"]: e["wire"] for e in reg["events"] if e["status"] == "live"}
    assert live == _LIVE_PAIRS, (
        "a live event's wire value moved. Rows already in analytics_events carry the old "
        "string, so re-pointing one silently splits (or merges) a metric's history."
    )


def test_every_event_declares_source_status_funnel_and_purpose():
    reg = _registry()
    stages = {stage["id"] for stage in reg["funnel"]}
    for event in reg["events"]:
        n = event["name"]
        assert event["source"] in {"client", "server"}, f"{n}: bad source"
        assert event["status"] in {"live", "planned"}, f"{n}: bad status"
        assert event["funnel"] in stages, f"{n}: funnel '{event['funnel']}' not declared"
        # "No transition, no event" is only enforceable if purpose is mandatory.
        assert str(event.get("purpose", "")).strip(), f"{n}: empty purpose"
        assert isinstance(event.get("properties"), dict), f"{n}: properties must be a mapping"


def _enum_key_and_nullable(decl: str) -> tuple[str, bool]:
    """`enum:<name>` or `enum:<name>|null` — the `|null` suffix (PR #6815 repair B3)
    marks a property whose frozen spec explicitly allows a null value (e.g.
    flow_observatory.interacted's `lens`, per research/flow_observatory/W7_SPEC.md §1:
    `theme|sector|aggregate|null`)."""
    key = decl.split(":", 1)[1]
    if key.endswith("|null"):
        return key[: -len("|null")], True
    return key, False


def test_property_types_are_scalars_or_declared_enums():
    reg = _registry()
    enums = reg["enums"]
    for event in reg["events"]:
        for prop, decl in event["properties"].items():
            if str(decl).startswith("enum:"):
                key, _nullable = _enum_key_and_nullable(str(decl))
                assert key in enums, f"{event['name']}.{prop}: unknown enum '{key}'"
            else:
                assert decl in _SCALAR_TYPES, (
                    f"{event['name']}.{prop}: type '{decl}' is neither a scalar "
                    f"{sorted(_SCALAR_TYPES)} nor enum:<declared>"
                )


def test_flowobs_lens_property_is_declared_nullable():
    """B3 (PR #6815 review): W7_SPEC.md §1 freezes `lens` as
    `theme|sector|aggregate|null` — five of the nine flowobs events carry no group
    (trust_open, changed_expand, compare_run, terminal_out, watch_note_view). Before
    this, `enum:flow_lens` had no way to say "or null", so those five live null
    payloads were technically out of contract with the registry."""
    reg = _registry()
    event = next(e for e in reg["events"] if e["name"] == "flow_observatory.interacted")
    decl = str(event["properties"]["lens"])
    assert decl.startswith("enum:"), f"lens declaration {decl!r} is not an enum"
    key, nullable = _enum_key_and_nullable(decl)
    assert key == "flow_lens"
    assert nullable, f"lens declaration {decl!r} does not mark null allowed"


def test_flowobs_sample_payloads_conform_to_the_registry():
    """B3: a trust_open payload with lens:null passes (the frozen null allowance); the
    __all__ aggregate row's group_drill payload carries lens:'aggregate' — a real
    flow_lens member, not null, because the row is mapped to it directly in the
    template rather than falling back to the registry's null allowance."""
    reg = _registry()
    enums = reg["enums"]
    event = next(e for e in reg["events"] if e["name"] == "flow_observatory.interacted")
    samples = [
        {"ev": "trust_open", "lens": None, "id": "cn_large_order_proxy", "sess": "2026-09-03"},
        {"ev": "group_drill", "lens": "aggregate", "id": "__all__", "sess": "2026-09-03"},
    ]
    for payload in samples:
        for prop, value in payload.items():
            decl = str(event["properties"][prop])
            if decl.startswith("enum:"):
                key, nullable = _enum_key_and_nullable(decl)
                if value is None:
                    assert nullable, f"{prop} received None but {decl!r} is not nullable"
                else:
                    assert value in enums[key], f"{prop}={value!r} not in enum {key}"
            else:
                assert value is None or isinstance(value, str), f"{prop}={value!r} not a string"


def test_no_enum_carries_the_legacy_insider_tier():
    """Property 3 — `insider` must be normalized before it reaches telemetry.

    See lib/tiers.py: the string has no expiry (pre-rename entitlement rows are never
    back-filled and `immutable`-cached JS keeps emitting it), so an emitter that passes
    it through would split every tier-segmented metric in two.
    """
    reg = _registry()
    for key, values in reg["enums"].items():
        # Type-check FIRST. `tier: "anon,free,essential,pro"` (a scalar — YAML accepts it)
        # would turn both assertions below into substring tests over a string, and the
        # positive one would still pass, so the guard would silently stop guarding.
        assert isinstance(values, list) and values, f"enums.{key} must be a non-empty list"
        assert all(isinstance(v, str) for v in values), f"enums.{key} must be strings"
        assert "insider" not in values, (
            f"enums.{key} lists 'insider' — normalize to 'essential' at the emitter "
            "(lib/tiers.normalize_tier / normTier) instead of widening the enum"
        )
    assert "essential" in reg["enums"]["tier"]


def test_marketing_aliases_resolve_to_the_existing_taxonomy():
    """The repo already had a declared growth vocabulary; two of them cannot be joined.

    `engine/marketing/events.py::GROWTH_EVENTS` is the marketing lobe's taxonomy, published
    into `marketing_state.json` as `{"instrumented": [...], "observed": 0}` — declarative,
    like this registry. Every `marketing_alias` here must name a real member of it, or the
    two vocabularies drift apart the moment either is edited.
    """
    from engine.marketing.events import GROWTH_EVENTS

    reg = _registry()
    aliased = {e["name"]: e["marketing_alias"] for e in reg["events"] if "marketing_alias" in e}
    assert aliased, "no marketing aliases declared — the reconciliation was removed"
    unknown = {n: a for n, a in aliased.items() if a not in GROWTH_EVENTS}
    assert not unknown, f"marketing_alias values absent from GROWTH_EVENTS: {unknown}"
    # An alias must be 1:1 — two of our events pointing at one of theirs would double-count.
    values = list(aliased.values())
    assert len(values) == len(set(values)), f"duplicate marketing_alias: {values}"


def test_tier_properties_must_use_the_enum_not_a_bare_string():
    """The `insider` guard scans `enums`, so retyping a tier property to `string` escapes it.

    One word — `enum:tier` -> `string` — would let an emitter publish the legacy tier value
    with every guard still green, splitting every tier-segmented metric in two invisibly.
    """
    reg = _registry()
    tierish = {"tier", "required_tier", "tier_seen", "from_tier", "to_tier"}
    for event in reg["events"]:
        for prop, decl in event["properties"].items():
            if prop in tierish:
                assert decl == "enum:tier", (
                    f"{event['name']}.{prop} is {decl!r}; tier-valued properties must use "
                    "enum:tier so the insider guard covers them"
                )


def test_the_funnel_stages_cover_the_documented_model():
    """The stages are the transitions in MASTERMIND_ACTIVATION_AND_FUNNEL.md §1."""
    reg = _registry()
    stages = {stage["id"] for stage in reg["funnel"]}
    expected = {
        "visit", "intelligence_experienced", "personal_act", "registration",
        "activation", "upgrade_intent", "paid", "paid_activation", "retained",
        "churn", "none",
    }
    assert stages == expected


def test_each_funnel_transition_has_at_least_one_event():
    """A stage nothing emits is a step we cannot measure — which is the whole failure
    this program exists to fix. `none` and `paid_activation` are exempt: the former is
    the explicit no-transition bucket, the latter is DERIVED from capability-group use
    across days rather than emitted directly."""
    reg = _registry()
    emitted = {e["funnel"] for e in reg["events"]}
    for stage in (s["id"] for s in reg["funnel"]):
        if stage in {"none", "paid_activation"}:
            continue
        assert stage in emitted, f"funnel stage '{stage}' has no event"
