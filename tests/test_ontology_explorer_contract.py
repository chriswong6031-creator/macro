"""tests/test_ontology_explorer_contract.py — F04-X1 snapshot semantics (RED first).

`engine.ontology_explorer.compose_snapshot()` projects the owner-observed
transmission artifacts into the tenant-neutral `ontology_explorer_snapshot.v1`.
These tests lock the semantics the operation's acceptance clause names, and they
are deliberately hostile: each one is a way the surface could look correct while
telling the researcher something the owners never said.

  - the path order comes from the ORDERED hop list, never from any score, and
    the first blocking leg is the first FALSE node in that order
  - a confirmed downstream node can never activate a false upstream one; the
    contradiction is reported as a contradiction, not as partial activation
  - a cycle in the hop graph cannot inflate state
  - a missing node / right / clock / invalidator DEGRADES with a named gap
    instead of being silently dropped or invented
  - "what changed" is `comparison_unavailable` when no owner transition is
    recorded — an absent baseline is not evidence that nothing moved
  - the response carries no scenario, user, holding or forecast field
  - composing never writes to the owner artifacts
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import ontology_explorer_fixtures as fx  # noqa: E402

SCHEMA_ID = "ontology_explorer_snapshot.v1"

# Vocabulary that must never appear anywhere in a tenant-neutral snapshot. The
# four-layer separation puts scenario assumption, scenario evaluation and private
# user state OUTSIDE this object; a key like "position_size" appearing here would
# mean the layers had merged.
FORBIDDEN_KEY_SUBSTRINGS = (
    "scenario", "user", "account", "holding", "position", "portfolio",
    "exposure_value", "pnl", "trade", "order", "size", "rank", "gate",
    "forecast", "prediction", "target_price", "confidence", "probability_of",
    "recommend", "conviction", "session", "tenant", "email", "subscriber",
)


def _compose(root: Path, **kwargs):
    from engine.ontology_explorer import compose_snapshot
    return compose_snapshot(root, chain=kwargs.pop("chain", fx.SLUG), **kwargs)


def _walk_keys(obj, prefix=""):
    if isinstance(obj, dict):
        for k, v in obj.items():
            yield f"{prefix}.{k}" if prefix else str(k)
            yield from _walk_keys(v, f"{prefix}.{k}" if prefix else str(k))
    elif isinstance(obj, list):
        for i, v in enumerate(obj):
            yield from _walk_keys(v, f"{prefix}[{i}]")


# --------------------------------------------------------------------------
# shape
# --------------------------------------------------------------------------
def test_snapshot_declares_the_closed_schema_id(tmp_path):
    snap = _compose(fx.build_root(tmp_path))
    assert snap["schema"] == SCHEMA_ID


def test_path_order_follows_the_hop_list_not_the_node_mapping(tmp_path):
    """The knowledge file stores nodes in an UNORDERED mapping; only the hop
    list carries the path. Sorting node ids would happen to look right for
    n1..n4, so the fixture is re-keyed to prove order is really taken from hops.

    The payload calls this `path.sequence`, not `path.order`, and the blocking
    leg carries an `index`, not a `position` — both deliberately, so that the
    tenant-neutrality denylist below can keep banning "order" and "position"
    outright instead of carving out exceptions that a future trade-authority
    field could hide behind."""
    doc = fx.chain_yaml()
    doc["nodes"] = {k: doc["nodes"][k] for k in ("n4", "n2", "n1", "n3")}
    snap = _compose(fx.build_root(tmp_path, yaml_doc=doc))
    assert snap["path"]["sequence"] == ["n1", "n2", "n3", "n4"]


def test_first_blocking_leg_is_the_first_false_node_in_path_order(tmp_path):
    """n1 and n3 are both false. Path order — not receipt magnitude, not a
    score, not the largest shortfall — decides which one blocks."""
    state = fx.chain_state(confirmed=(False, True, False, True))
    snap = _compose(fx.build_root(tmp_path, state_doc=state))
    assert snap["first_blocking_leg"]["node_id"] == "n1"
    assert snap["first_blocking_leg"]["index"] == 1
    assert snap["first_blocking_leg"]["basis"] == "path_order"


def test_a_fully_confirmed_path_has_no_blocking_leg(tmp_path):
    state = fx.chain_state(confirmed=(True, True, True, True), state="expressed")
    snap = _compose(fx.build_root(tmp_path, state_doc=state))
    assert snap["first_blocking_leg"] is None


# --------------------------------------------------------------------------
# downstream true without upstream — the operation's frozen reference state
# --------------------------------------------------------------------------
def test_downstream_true_cannot_activate_a_false_upstream(tmp_path):
    state = fx.chain_state(confirmed=(False, False, False, True))
    snap = _compose(fx.build_root(tmp_path, state_doc=state))
    assert snap["state"]["code"] == "dormant"
    assert snap["state"]["activation"] is False
    contradiction = snap["contradiction"]
    assert contradiction["code"] == "downstream_true_without_upstream"
    assert contradiction["confirmed_downstream"] == ["n4"]
    assert contradiction["blocking_upstream"] == "n1"


def test_downstream_truth_is_not_reported_as_partial_activation(tmp_path):
    """One true terminal leg out of four must never read as "1 of 4 active"."""
    state = fx.chain_state(confirmed=(False, False, False, True))
    snap = _compose(fx.build_root(tmp_path, state_doc=state))
    assert snap["state"]["confirmed_hop_count"] == 0
    assert snap["state"]["code"] != "active"
    blob = json.dumps(snap, ensure_ascii=False).lower()
    assert "partially active" not in blob
    assert "partial activation" not in blob


# --------------------------------------------------------------------------
# cycles
# --------------------------------------------------------------------------
def test_a_cycle_is_detected_and_cannot_inflate_state(tmp_path):
    root = fx.build_root(
        tmp_path,
        yaml_doc=fx.chain_yaml(cycle=True),
        state_doc=fx.chain_state(confirmed=(False, True, True, True), cycle=True),
    )
    snap = _compose(root)
    assert snap["path"]["cycle"]["detected"] is True
    assert snap["path"]["cycle"]["nodes"]
    assert snap["state"]["code"] == "unknown"
    assert snap["state"]["activation"] is False


def test_a_cycle_does_not_repeat_a_node_in_the_path_order(tmp_path):
    root = fx.build_root(
        tmp_path,
        yaml_doc=fx.chain_yaml(cycle=True),
        state_doc=fx.chain_state(cycle=True),
    )
    order = _compose(root)["path"]["sequence"]
    assert len(order) == len(set(order))


# --------------------------------------------------------------------------
# degradation: absent owner facts are NAMED, never invented
# --------------------------------------------------------------------------
def test_a_node_missing_from_owner_state_degrades_with_a_named_gap(tmp_path):
    root = fx.build_root(tmp_path, state_doc=fx.chain_state(omit_nodes=("n3",)))
    snap = _compose(root)
    leg = next(x for x in snap["path"]["legs"] if x["node_id"] == "n3")
    assert leg["observation"] == "unobserved"
    assert leg["confirmed"] is None
    assert {"kind": "node_unobserved", "node_id": "n3"} in snap["gaps"]
    assert snap["state"]["code"] == "unknown"


def test_a_chain_without_invalidators_reports_the_absence(tmp_path):
    doc = fx.chain_yaml()
    doc.pop("falsifiers")
    snap = _compose(fx.build_root(tmp_path, yaml_doc=doc))
    assert snap["invalidators"] == []
    assert {"kind": "invalidators_absent"} in snap["gaps"]


def test_a_chain_without_exposure_screens_reports_the_absence(tmp_path):
    doc = fx.chain_yaml()
    doc.pop("exposure_screens")
    snap = _compose(fx.build_root(tmp_path, yaml_doc=doc))
    assert snap["rights"] == []
    assert {"kind": "rights_absent"} in snap["gaps"]


def test_a_hop_without_a_lag_window_reports_a_clock_gap(tmp_path):
    doc = fx.chain_yaml()
    doc["hops"][1].pop("lag_d")
    state = fx.chain_state()
    state["chains"][0]["hops"][1].pop("lag_d")
    snap = _compose(fx.build_root(tmp_path, yaml_doc=doc, state_doc=state))
    assert {"kind": "clock_absent", "hop_id": "n2->n3"} in snap["gaps"]


# --------------------------------------------------------------------------
# what changed — an absent baseline is NOT "nothing changed"
# --------------------------------------------------------------------------
def test_what_changed_is_comparison_unavailable_without_a_recorded_transition(tmp_path):
    snap = _compose(fx.build_root(tmp_path))
    changed = snap["what_changed"]
    assert changed["status"] == "comparison_unavailable"
    assert changed["reason"] == "no_recorded_transition"
    assert changed["items"] == []


def test_no_recorded_transition_never_renders_as_nothing_changed(tmp_path):
    """The regression this test exists for: zero rows in the episode ledger was
    read as proof that the underlying conditions had not moved. It is not."""
    snap = _compose(fx.build_root(tmp_path))
    blob = json.dumps(snap, ensure_ascii=False).lower()
    for phrase in ("nothing changed", "no change", "unchanged", "no changes"):
        assert phrase not in blob


# --------------------------------------------------------------------------
# tenant neutrality and authority limits
# --------------------------------------------------------------------------
def test_snapshot_carries_no_scenario_user_or_holding_field(tmp_path):
    snap = _compose(fx.build_root(tmp_path))
    offenders = [
        key for key in _walk_keys(snap)
        if any(bad in key.rsplit(".", 1)[-1].lower() for bad in FORBIDDEN_KEY_SUBSTRINGS)
    ]
    assert offenders == []


def test_frequencies_are_labelled_historical_context_not_confidence(tmp_path):
    snap = _compose(fx.build_root(tmp_path))
    for leg in snap["path"]["hops"]:
        base = leg.get("base_rate")
        if base is None:
            continue
        assert base["interpretation"] == "historical_context"
        assert "confidence" not in base


def test_the_word_validated_never_appears(tmp_path):
    snap = _compose(fx.build_root(tmp_path))
    assert "validated" not in json.dumps(snap, ensure_ascii=False).lower()


# --------------------------------------------------------------------------
# bounds fail closed
# --------------------------------------------------------------------------
def test_a_path_longer_than_the_bound_fails_closed(tmp_path):
    from engine.ontology_explorer import MAX_PATH_LEGS, SourceIncoherent
    doc = fx.chain_yaml()
    nodes = dict(doc["nodes"])
    hops = list(doc["hops"])
    prev = "n4"
    for i in range(MAX_PATH_LEGS + 2):
        node_id = f"x{i}"
        nodes[node_id] = {"title": {"en": node_id, "zh": node_id}, "src": "synthetic",
                          "test": {"all": []}}
        hops.append({"from": prev, "to": node_id, "sign": "+", "lag_d": [1, 2],
                     "label": {"en": "l", "zh": "l"},
                     "condition": {"en": "c", "zh": "c"},
                     "mechanism": {"en": "m", "zh": "m"}})
        prev = node_id
    doc["nodes"], doc["hops"] = nodes, hops
    with pytest.raises(SourceIncoherent):
        _compose(fx.build_root(tmp_path, yaml_doc=doc))


def test_bounds_are_reported_on_a_normal_response(tmp_path):
    from engine.ontology_explorer import MAX_PATH_LEGS
    snap = _compose(fx.build_root(tmp_path))
    assert snap["bounds"]["legs"] == 4
    assert snap["bounds"]["max_legs"] == MAX_PATH_LEGS
    assert snap["bounds"]["truncated"] is False


# --------------------------------------------------------------------------
# composing is read-only
# --------------------------------------------------------------------------
def test_composing_writes_nothing(tmp_path):
    root = fx.build_root(tmp_path)
    before = {p: (p.stat().st_mtime_ns, p.stat().st_size)
              for p in sorted(root.rglob("*")) if p.is_file()}
    _compose(root)
    after = {p: (p.stat().st_mtime_ns, p.stat().st_size)
             for p in sorted(root.rglob("*")) if p.is_file()}
    assert before == after


def test_composing_never_calls_the_episode_ledger_writer(tmp_path, monkeypatch):
    """`transmission_chains.run()` defaults to write=True and appends the episode
    ledger. A request-time composer that reached for it would mutate an owner
    artifact on a GET."""
    import engine.transmission_chains as tc

    def _boom(*a, **k):  # pragma: no cover - only runs on regression
        raise AssertionError("compose_snapshot must never call transmission_chains.run")

    monkeypatch.setattr(tc, "run", _boom)
    _compose(fx.build_root(tmp_path))
