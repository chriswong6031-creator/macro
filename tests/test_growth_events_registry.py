"""Guards for `config/growth_events.yml`, the canonical growth-event vocabulary.

The registry's job is to stop six implementation waves from inventing six vocabularies
(research/MASTERMIND_GROWTH_INSTRUMENTATION_SPEC.md). A registry nothing checks would
drift from the running beacon on day one, so this file pins three properties:

1. **It cannot start out of step with production.** Every event type
   `app/main.py::_MM_EVENT_TYPES` already accepts appears in the registry with
   `status: live`, keyed on the WIRE value that is actually in `analytics_events`.
   (The reverse direction — whitelist ⊇ registry — becomes true in wave W2-1, when the
   whitelist is generated from this file. Asserting it now would red on every planned
   event, so it is deliberately not asserted yet.)
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
    """The whitelist, read from source rather than re-typed or imported.

    Parsed with `ast` rather than a regex: importing app.main would pull FastAPI and the
    whole request stack into a config test, and a regex is not safe here — the set
    literal's own comment contains `{arena, creative}`, so a non-greedy `\\{(.*?)\\}`
    closes on the comment's brace and silently drops every member declared after it
    (measured: it lost `ad_exposure`). An absence produced by a broken instrument looks
    exactly like a real absence, so the instrument has to be exact.
    """
    import ast

    tree = ast.parse((ROOT / "app" / "main.py").read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign) and any(
            isinstance(t, ast.Name) and t.id == "_MM_EVENT_TYPES" for t in node.targets
        ):
            value = ast.literal_eval(node.value)
            assert isinstance(value, (set, frozenset)) and value
            return set(value)
    raise AssertionError("could not locate _MM_EVENT_TYPES in app/main.py — was it renamed?")


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
#: two metrics at each other's history). These eleven are frozen: the rows already in
#: `analytics_events` carry these strings.
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


def test_property_types_are_scalars_or_declared_enums():
    reg = _registry()
    enums = reg["enums"]
    for event in reg["events"]:
        for prop, decl in event["properties"].items():
            if str(decl).startswith("enum:"):
                key = str(decl).split(":", 1)[1]
                assert key in enums, f"{event['name']}.{prop}: unknown enum '{key}'"
            else:
                assert decl in _SCALAR_TYPES, (
                    f"{event['name']}.{prop}: type '{decl}' is neither a scalar "
                    f"{sorted(_SCALAR_TYPES)} nor enum:<declared>"
                )


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
