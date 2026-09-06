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


def _has_gap(gaps, **fields):
    """A gap is present when it carries the fields under test.

    Not whole-dict equality: the composer also stamps every gap with a
    reader-facing `where_label`/`reason_label`, and pinning the entire dict here
    would make these tests fail on a labelling change that is not the defect any
    of them is about.
    """
    return any(all(gap.get(k) == v for k, v in fields.items()) for gap in gaps)


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
    # The state now reports the OWNER's episode, which stays knowable even when
    # this surface cannot read every current condition. What these tests have
    # always been about is that an unreadable input must never INFLATE the
    # state, so they now pin that directly rather than through a proxy code.
    assert snap["state"]["activation"] is False
    assert snap["state"]["conditions"]["all_current_met"] is None
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
    assert _has_gap(snap["gaps"], kind="node_unobserved", node_id="n3")
    # The state now reports the OWNER's episode, which stays knowable even when
    # this surface cannot read every current condition. What these tests have
    # always been about is that an unreadable input must never INFLATE the
    # state, so they now pin that directly rather than through a proxy code.
    assert snap["state"]["activation"] is False
    assert snap["state"]["conditions"]["all_current_met"] is None


def test_a_chain_without_invalidators_reports_the_absence(tmp_path):
    doc = fx.chain_yaml()
    doc.pop("falsifiers")
    snap = _compose(fx.build_root(tmp_path, yaml_doc=doc))
    assert snap["invalidators"] == []
    assert _has_gap(snap["gaps"], kind="invalidators_absent")


def test_a_chain_without_exposure_screens_reports_the_absence(tmp_path):
    doc = fx.chain_yaml()
    doc.pop("exposure_screens")
    snap = _compose(fx.build_root(tmp_path, yaml_doc=doc))
    assert snap["exposure_screens"] == []
    assert _has_gap(snap["gaps"], kind="exposure_screens_absent")


def test_a_hop_without_a_lag_window_reports_a_clock_gap(tmp_path):
    doc = fx.chain_yaml()
    doc["hops"][1].pop("lag_d")
    state = fx.chain_state()
    state["chains"][0]["hops"][1].pop("lag_d")
    snap = _compose(fx.build_root(tmp_path, yaml_doc=doc, state_doc=state))
    assert _has_gap(snap["gaps"], kind="clock_absent", hop_id="n2->n3")


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


# --------------------------------------------------------------------------
# front-facing vocabulary: tripwires are shown as what is watched, never as a
# thesis being refuted
# --------------------------------------------------------------------------
def _with_note(note):
    doc = fx.chain_yaml()
    doc["falsifiers"][0]["note"] = note
    return doc


@pytest.mark.parametrize(("note", "reason"), [
    ({"en": "the derating leg is falsified", "zh": "该环节已被否定"}, "refutation_vocabulary"),
    ({"en": "refuted by the 120d reading", "zh": "已被 120 日读数推翻"}, "refutation_vocabulary"),
    ({"en": "yield_rise with the cohort flat", "zh": "yield_rise 与该组合持平"}, "raw_identifier"),
    ("an English-only note with no translation", "untranslated"),
])
def test_an_owner_note_that_breaks_front_facing_law_is_withheld(tmp_path, note, reason):
    """Measured on the live WTI chain: one falsifier note carried refutation
    wording, a raw node id and no Chinese at all. Owner prose is not a user
    surface, so it is screened rather than trusted."""
    snap = _compose(fx.build_root(tmp_path, yaml_doc=_with_note(note)))
    invalidator = snap["invalidators"][0]
    assert invalidator["note"] is None
    assert invalidator["note_status"] == "withheld"
    assert invalidator["note_withheld_reason"] == reason


def test_a_clean_bilingual_owner_note_is_published(tmp_path):
    note = {"en": "oil up sharply with breakevens flat", "zh": "油价大涨而盈亏平衡持平"}
    snap = _compose(fx.build_root(tmp_path, yaml_doc=_with_note(note)))
    invalidator = snap["invalidators"][0]
    assert invalidator["note"] == note
    assert invalidator["note_status"] == "published"


def test_a_withheld_note_still_shows_the_condition_being_watched(tmp_path):
    """Withholding the prose must not withhold the substance."""
    snap = _compose(fx.build_root(tmp_path, yaml_doc=_with_note("English only")))
    watched = snap["invalidators"][0]["watched"]
    assert watched["series"] == "SYN-B"
    assert watched["op"] == "lt"
    assert watched["value"] == 1


def test_no_refutation_vocabulary_reaches_reader_facing_text(tmp_path):
    """Scoped to what a reader can see.

    `note_withheld_reason: "refutation_vocabulary"` is a machine reason code
    naming the rule that fired, and it is useful precisely because it says why.
    The ban is on reader-facing text, so the assertion reads reader-facing text.
    """
    snap = _compose(fx.build_root(tmp_path, yaml_doc=_with_note(
        {"en": "the thesis is falsified", "zh": "该论点已被证伪"})))
    shown = json.dumps({
        "state": snap["state"], "path": snap["path"],
        "what_changed": snap["what_changed"], "why_it_matters": snap["why_it_matters"],
        "next_action": snap["next_action"], "contradiction": snap["contradiction"],
        "invalidators": [{"note": i["note"], "watched": i["watched"]}
                         for i in snap["invalidators"]],
        "exposure_screens": snap["exposure_screens"],
    }, ensure_ascii=False).lower()
    for banned in ("falsif", "refut", "证伪", "disprov"):
        assert banned not in shown


@pytest.mark.needs_full_checkout("data")
def test_the_live_default_chain_composes_without_front_facing_violations():
    """The guard that matters: run it against the real knowledge file, not a
    fixture. This is the test that would have caught the defect at review time
    instead of in a browser."""
    from engine.ontology_explorer import DEFAULT_CHAIN, compose_snapshot
    repo = Path(__file__).resolve().parents[1]
    if not (repo / "data" / "transmission" / "chain_state.json").exists():
        pytest.skip("needs the full checkout (data/ is omitted in a sparse tree)")
    snap = compose_snapshot(repo, chain=DEFAULT_CHAIN)
    shown = json.dumps({
        "state": snap["state"], "path": snap["path"], "invalidators": [
            {"note": i["note"], "watched": i["watched"]} for i in snap["invalidators"]],
        "what_changed": snap["what_changed"], "next_action": snap["next_action"],
    }, ensure_ascii=False).lower()
    for banned in ("falsif", "refut", "证伪", "disprov", "validated"):
        assert banned not in shown, f"{banned!r} reaches a user surface on the live chain"


# --------------------------------------------------------------------------
# the screen must cover EVERY owner-authored string, not just the one that
# happened to be caught first
# --------------------------------------------------------------------------
READER_FACING_KEYS = ("state", "path", "what_changed", "why_it_matters",
                      "next_action", "contradiction", "exposure_screens")


def _reader_facing(snap) -> str:
    payload = {key: snap[key] for key in READER_FACING_KEYS}
    payload["invalidators"] = [{"note": i["note"], "watched": i["watched"]}
                               for i in snap["invalidators"]]
    return json.dumps(payload, ensure_ascii=False)


def _plant(field: str, text: dict):
    """Put `text` into one owner-authored field of the knowledge document."""
    doc = fx.chain_yaml()
    if field == "chain_title":
        doc["title"] = text
    elif field == "node_title":
        doc["nodes"]["n1"]["title"] = text
    elif field == "hop_label":
        doc["hops"][0]["label"] = text
    elif field == "hop_condition":
        doc["hops"][0]["condition"] = text
    elif field == "hop_mechanism":
        doc["hops"][0]["mechanism"] = text
    elif field == "screen_label":
        doc["exposure_screens"]["synthetic_screen"]["label"] = text
    elif field == "screen_note":
        doc["exposure_screens"]["synthetic_screen"]["note"] = text
    elif field == "falsifier_note":
        doc["falsifiers"][0]["note"] = text
    else:  # pragma: no cover - guards a typo in the parametrize list
        raise AssertionError(f"unknown field {field}")
    return doc


OWNER_TEXT_FIELDS = ("chain_title", "node_title", "hop_label", "hop_condition",
                     "hop_mechanism", "screen_label", "screen_note", "falsifier_note")


@pytest.mark.parametrize("field", OWNER_TEXT_FIELDS)
def test_refutation_vocabulary_cannot_reach_the_reader_through_any_owner_field(
        tmp_path, field):
    """The regression this test exists for.

    The first version of the screen guarded the falsifier note alone, because
    that is where the defect was found. An adversarial pass put the same words
    into the chain title, a node title, a hop label, a hop mechanism and an
    exposure-screen note — and every one reached the reader. The live chain is
    clean in those fields TODAY, so testing against real data gave false
    comfort; the leak fires the first time somebody edits a knowledge file.
    """
    doc = _plant(field, {"en": "the thesis is falsified", "zh": "该论点已被证伪"})
    shown = _reader_facing(_compose(fx.build_root(tmp_path, yaml_doc=doc)))
    for banned in ("falsif", "证伪"):
        assert banned not in shown.lower(), f"{banned!r} leaks through {field}"


@pytest.mark.parametrize("field", OWNER_TEXT_FIELDS)
def test_a_raw_identifier_cannot_reach_the_reader_through_any_owner_field(
        tmp_path, field):
    doc = _plant(field, {"en": "watch yield_rise closely", "zh": "密切关注 yield_rise"})
    shown = _reader_facing(_compose(fx.build_root(tmp_path, yaml_doc=doc)))
    assert "yield_rise" not in shown, f"raw node id leaks through {field}"


@pytest.mark.parametrize("field", OWNER_TEXT_FIELDS)
def test_a_withheld_string_is_always_named_in_gaps(tmp_path, field):
    """Withholding must never be silent — a reader who sees a positional label
    instead of a name is entitled to know the name was refused."""
    doc = _plant(field, {"en": "the thesis is falsified", "zh": "该论点已被证伪"})
    snap = _compose(fx.build_root(tmp_path, yaml_doc=doc))
    withheld = [g for g in snap["gaps"] if g.get("kind") == "text_withheld"]
    assert withheld, f"{field} was withheld silently"
    assert all(g.get("reason") for g in withheld)
    assert all(g.get("where") for g in withheld)


def test_a_withheld_identity_string_falls_back_to_a_positional_label(tmp_path):
    """Blanking a step's name would leave an unlabelled step. The honest
    substitute is its position, not an invented name and not nothing."""
    doc = _plant("node_title", {"en": "step one is falsified", "zh": "环节一已证伪"})
    snap = _compose(fx.build_root(tmp_path, yaml_doc=doc))
    assert snap["path"]["legs"][0]["title"] == {"en": "Step 1", "zh": "第 1 环节"}
    assert snap["path"]["legs"][1]["title"]["en"] == "Node two"


def test_an_untranslated_identity_label_is_kept_but_reported(tmp_path):
    """Proportionality: an untranslated short label is a content-quality defect,
    not a law violation. Blanking the chain title over it would make the page
    unusable, so it is kept and the gap is named."""
    doc = _plant("chain_title", {"en": "Probe", "zh": "Probe"})
    snap = _compose(fx.build_root(tmp_path, yaml_doc=doc))
    assert snap["path"]["title"] == {"en": "Probe", "zh": "Probe"}
    assert _has_gap(snap["gaps"], kind="text_untranslated", where="title")


def test_untranslated_prose_is_withheld_rather_than_served_as_english(tmp_path):
    doc = _plant("hop_mechanism", "English-only mechanism prose")
    snap = _compose(fx.build_root(tmp_path, yaml_doc=doc))
    assert snap["path"]["hops"][0]["mechanism"] is None
    assert _has_gap(snap["gaps"], kind="text_withheld", where="hops.n1->n2.mechanism",             reason= "untranslated")


# --------------------------------------------------------------------------
# path SHAPE — a partial read must never be presented as the whole path
#
# `_walk_path` follows one successor chain. That is the right reading of a
# simple path and a silently wrong reading of anything else. An independent
# review measured a hop list of `n1->n2` and `n3->n4`, with n3 and n4 observed
# FALSE, composing as `state: active` over a two-leg path — the surface
# answering "active" about a path it had not read.
# --------------------------------------------------------------------------
def test_a_discontinuous_hop_list_fails_closed_instead_of_truncating(tmp_path):
    doc = fx.chain_yaml()
    doc["hops"] = [doc["hops"][0], doc["hops"][2]]          # n1->n2 , n3->n4
    state = fx.chain_state(confirmed=(True, True, False, False))
    from engine.ontology_explorer import SourceIncoherent
    with pytest.raises(SourceIncoherent) as excinfo:
        _compose(fx.build_root(tmp_path, yaml_doc=doc, state_doc=state))
    assert "path_disconnected" in str(excinfo.value)


def test_a_branching_hop_list_fails_closed(tmp_path):
    """The second out-edge was dropped when the successor map was built, so a
    false branch simply vanished and the path read as active."""
    from engine.ontology_explorer import SourceIncoherent
    doc = fx.chain_yaml()
    doc["hops"][2] = {**doc["hops"][2], "from": "n2", "to": "n4"}
    with pytest.raises(SourceIncoherent) as excinfo:
        _compose(fx.build_root(tmp_path, yaml_doc=doc,
                               state_doc=fx.chain_state(confirmed=(True, True, True, False))))
    assert "path_branches" in str(excinfo.value)


def test_a_hop_to_an_undeclared_node_is_incoherent_not_an_unread_leg(tmp_path):
    """Reported as an unpublished reading it invented a positional title for the
    phantom and told the researcher to wait for a reading that cannot arrive."""
    from engine.ontology_explorer import SourceIncoherent
    doc = fx.chain_yaml()
    doc["hops"].append({"from": "n4", "to": "ghost", "sign": "+", "lag_d": [1, 2],
                        "label": {"en": "l", "zh": "l2"},
                        "condition": {"en": "c", "zh": "c2"},
                        "mechanism": {"en": "m", "zh": "m2"}})
    with pytest.raises(SourceIncoherent) as excinfo:
        _compose(fx.build_root(tmp_path, yaml_doc=doc))
    assert "undeclared_node:ghost" in str(excinfo.value)


def test_a_chain_with_no_hops_is_incoherent_not_unavailable(tmp_path):
    """The file was present, readable and parsed. Calling that "absent" tells the
    operator to look for a missing artifact that is sitting right there."""
    from engine.ontology_explorer import SourceIncoherent
    doc = fx.chain_yaml()
    doc["hops"] = []
    with pytest.raises(SourceIncoherent):
        _compose(fx.build_root(tmp_path, yaml_doc=doc))


def test_duplicate_chain_rows_fail_closed(tmp_path):
    """Taking matches[0] made every later row invisible — including one at a
    different rev with a different state, which also walked past the rev check,
    because that check only ever saw row 0."""
    from engine.ontology_explorer import SourceIncoherent
    state = fx.chain_state()
    duplicate = json.loads(json.dumps(state["chains"][0]))
    duplicate["rev"], duplicate["state"] = 99, "expressed"
    state["chains"].append(duplicate)
    with pytest.raises(SourceIncoherent) as excinfo:
        _compose(fx.build_root(tmp_path, state_doc=state))
    assert "duplicate_chain_rows" in str(excinfo.value)


def test_the_bound_is_measured_against_the_file_not_the_walk(tmp_path):
    """Measuring the walk let a large file compose as "2 of 12 legs" while
    returning every one of its hop rows."""
    from engine.ontology_explorer import MAX_PATH_LEGS, SourceIncoherent
    doc = fx.chain_yaml()
    nodes, hops, previous = dict(doc["nodes"]), list(doc["hops"]), "n4"
    for i in range(MAX_PATH_LEGS + 2):
        node_id = f"x{i}"
        nodes[node_id] = {"title": {"en": node_id, "zh": f"{node_id}zh"},
                          "src": "synthetic", "test": {"all": []}}
        hops.append({"from": previous, "to": node_id, "sign": "+", "lag_d": [1, 2],
                     "label": {"en": "l", "zh": "l2"},
                     "condition": {"en": "c", "zh": "c2"},
                     "mechanism": {"en": "m", "zh": "m2"}})
        previous = node_id
    doc["nodes"], doc["hops"] = nodes, hops
    state = fx.chain_state()
    state["chains"][0]["nodes"] = []          # nothing observed; the FILE is the problem
    with pytest.raises(SourceIncoherent) as excinfo:
        _compose(fx.build_root(tmp_path, yaml_doc=doc, state_doc=state))
    assert "path_exceeds_bound" in str(excinfo.value)


# --------------------------------------------------------------------------
# a missing reading is not a contradiction, and an unresolved leg is not observed
# --------------------------------------------------------------------------
def _state_with_unresolved_second_leg():
    state = fx.chain_state(confirmed=(True, True, True, True))
    state["chains"][0]["nodes"][1]["resolved"] = False
    state["chains"][0]["nodes"][1]["confirmed"] = None
    return state


def test_an_unresolved_leg_is_not_counted_as_observed(tmp_path):
    """The snapshot said all four legs were observed while its own blocking-leg
    block said that very leg had no reading."""
    snap = _compose(fx.build_root(tmp_path, state_doc=_state_with_unresolved_second_leg()))
    assert snap["state"]["coverage"]["legs_observed"] == 3
    assert snap["state"]["coverage"]["legs_unobserved"] == ["n2"]
    # The state now reports the OWNER's episode, which stays knowable even when
    # this surface cannot read every current condition. What these tests have
    # always been about is that an unreadable input must never INFLATE the
    # state, so they now pin that directly rather than through a proxy code.
    assert snap["state"]["activation"] is False
    assert snap["state"]["conditions"]["all_current_met"] is None


def test_no_contradiction_is_claimed_when_the_blocking_leg_was_never_read(tmp_path):
    """The published note says a later leg reads true "while an earlier one does
    not". If the earlier leg was never read, that sentence is false."""
    snap = _compose(fx.build_root(tmp_path, state_doc=_state_with_unresolved_second_leg()))
    assert snap["first_blocking_leg"]["reason"] == "not_resolved"
    assert snap["contradiction"] is None


def test_no_contradiction_is_claimed_when_the_blocking_leg_is_absent(tmp_path):
    state = fx.chain_state(confirmed=(True, True, True, True), omit_nodes=("n1",))
    snap = _compose(fx.build_root(tmp_path, state_doc=state))
    assert snap["first_blocking_leg"]["reason"] == "not_observed"
    assert snap["contradiction"] is None


def test_a_contradiction_still_fires_when_the_blocker_is_genuinely_false(tmp_path):
    snap = _compose(fx.build_root(tmp_path, state_doc=fx.chain_state(
        confirmed=(False, False, False, True))))
    assert snap["first_blocking_leg"]["reason"] == "condition_false"
    assert snap["contradiction"]["code"] == "downstream_true_without_upstream"


# --------------------------------------------------------------------------
# clocks and revisions
# --------------------------------------------------------------------------
def test_a_build_stamp_in_the_future_is_not_an_age_of_zero(tmp_path):
    """`max(0, ...)` re-opened the very defect the parser was written to close:
    a stamp we cannot make sense of rendering as "built just now"."""
    state = fx.chain_state()
    state["built"] = "2099-01-01 00:00 UTC"
    snap = _compose(fx.build_root(tmp_path, state_doc=state))
    freshness = snap["source"]["freshness"]
    assert freshness["source_age_seconds"] is None
    assert freshness["source_age_basis"] == "build_stamp_in_future"
    assert _has_gap(snap["gaps"], kind="build_stamp_in_future", where="chain_state.built")


def test_a_transition_from_another_revision_is_not_this_revisions_change(tmp_path):
    """A row written under a different revision describes a different definition
    of the path; presenting it as the current change is a category error."""
    root = fx.build_root(tmp_path)
    (root / "data" / "transmission" / "chain_episodes.jsonl").write_text(
        json.dumps({"chain": fx.SLUG, "rev": 1, "episode_id": "ep-synthetic-1", "transition": "arming", "hop": 0,
                    "asof": "2026-01-01"}) + "\n"
        + json.dumps({"chain": fx.SLUG, "rev": 99, "episode_id": "ep-synthetic-1", "transition": "arming", "hop": 0,
                      "asof": "2026-01-01"}) + "\n", encoding="utf-8")
    snap = _compose(root)
    assert snap["what_changed"]["status"] == "comparison_unavailable"
    assert snap["evidence"]["k1"]["refs_count"] == 0
    assert _has_gap(snap["gaps"], kind="transitions_from_another_revision", count=2)


def test_a_transition_at_the_current_revision_is_reported(tmp_path):
    root = fx.build_root(tmp_path)
    (root / "data" / "transmission" / "chain_episodes.jsonl").write_text(
        json.dumps({"chain": fx.SLUG, "rev": 2, "episode_id": "ep-synthetic-1", "transition": "arming", "hop": 0,
                    "asof": "2026-01-01", "hop": 1}) + "\n", encoding="utf-8")
    snap = _compose(root)
    assert snap["what_changed"]["status"] == "recorded_transition"
    assert snap["what_changed"]["items"][0]["asof"] == "2026-01-01"


# ==========================================================================
# Sol REQUEST_REPAIR 1788598030.999859 — five truth blockers
# ==========================================================================

# B1 — a recorded transition is NOT an evidence reference
def _root_with_episodes(tmp_path, rows: list[dict]):
    root = fx.build_root(tmp_path)
    (root / "data" / "transmission" / "chain_episodes.jsonl").write_text(
        "\n".join(json.dumps(r) for r in rows) + "\n", encoding="utf-8")
    return root


def test_a_recorded_transition_alone_never_makes_k1_available(tmp_path):
    """`_evidence` counted any row with a matching chain and declared K1
    AVAILABLE — while creating and validating no EvidenceRef at all. The client
    then hid the binding limitation. A transition is a transition; a reference is
    a reference that resolved."""
    root = _root_with_episodes(tmp_path, [
        {"chain": fx.SLUG, "rev": 2, "episode_id": "ep-synthetic-1", "transition": "arming", "hop": 0, "asof": "2026-01-02"}])
    snap = _compose(root)
    assert snap["evidence"]["k1"]["status"] == "unavailable_for_object"
    assert snap["evidence"]["k1"]["refs"] == []
    assert snap["evidence"]["k1"]["refs_count"] == 0


def test_transition_count_is_reported_separately_from_reference_count(tmp_path):
    root = _root_with_episodes(tmp_path, [
        {"chain": fx.SLUG, "rev": 2, "episode_id": "ep-synthetic-1", "transition": "arming", "hop": 0, "asof": "2026-01-02"}])
    k1 = _compose(root)["evidence"]["k1"]
    assert k1["recorded_transitions"] == 1
    assert k1["refs_count"] == 0
    assert k1["reason_code"] == "eligible_transition_not_k1_resolved"


def test_an_arbitrary_json_object_cannot_manufacture_evidence(tmp_path):
    root = _root_with_episodes(tmp_path, [{"chain": fx.SLUG}])
    k1 = _compose(root)["evidence"]["k1"]
    assert k1["status"] == "unavailable_for_object"
    assert k1["refs_count"] == 0


# B2 — typed boolean / null semantics; never invent state from truthiness
def _state_with_node_field(field: str, value):
    state = fx.chain_state(confirmed=(True, True, True, True))
    state["chains"][0]["nodes"][0][field] = value
    return state


@pytest.mark.parametrize("value", ["false", "true", 0, 1, "", "yes"])
def test_a_non_boolean_confirmed_is_unknown_not_coerced(tmp_path, value):
    """`bool("false")` is True. A string in the owner artifact could activate a
    leg that the owners had marked as not holding."""
    snap = _compose(fx.build_root(tmp_path, state_doc=_state_with_node_field("confirmed", value)))
    leg = snap["path"]["legs"][0]
    assert leg["confirmed"] is None
    assert leg["observation"] == "unreadable"
    # The state now reports the OWNER's episode, which stays knowable even when
    # this surface cannot read every current condition. What these tests have
    # always been about is that an unreadable input must never INFLATE the
    # state, so they now pin that directly rather than through a proxy code.
    assert snap["state"]["activation"] is False
    assert snap["state"]["conditions"]["all_current_met"] is None
    assert snap["state"]["activation"] is False


def test_a_missing_confirmed_is_unknown_not_false(tmp_path):
    state = fx.chain_state(confirmed=(True, True, True, True))
    del state["chains"][0]["nodes"][0]["confirmed"]
    snap = _compose(fx.build_root(tmp_path, state_doc=state))
    assert snap["path"]["legs"][0]["confirmed"] is None
    # The state now reports the OWNER's episode, which stays knowable even when
    # this surface cannot read every current condition. What these tests have
    # always been about is that an unreadable input must never INFLATE the
    # state, so they now pin that directly rather than through a proxy code.
    assert snap["state"]["activation"] is False
    assert snap["state"]["conditions"]["all_current_met"] is None


def test_a_missing_resolved_flag_is_not_assumed_resolved(tmp_path):
    """Defaulting `resolved` to True asserts the owners judged something they
    may simply not have written down."""
    state = fx.chain_state(confirmed=(True, True, True, True))
    del state["chains"][0]["nodes"][0]["resolved"]
    snap = _compose(fx.build_root(tmp_path, state_doc=state))
    assert snap["path"]["legs"][0]["observation"] == "incomplete"
    # The state now reports the OWNER's episode, which stays knowable even when
    # this surface cannot read every current condition. What these tests have
    # always been about is that an unreadable input must never INFLATE the
    # state, so they now pin that directly rather than through a proxy code.
    assert snap["state"]["activation"] is False
    assert snap["state"]["conditions"]["all_current_met"] is None
    assert _has_gap(snap["gaps"], kind="node_incomplete", node_id="n1")


def test_a_null_confirmed_on_a_resolved_node_stays_unknown(tmp_path):
    snap = _compose(fx.build_root(tmp_path, state_doc=_state_with_node_field("confirmed", None)))
    assert snap["path"]["legs"][0]["confirmed"] is None
    assert snap["state"]["activation"] is False


# B3 — topology completeness must also hold when a cycle is present
def test_a_disconnected_component_beside_a_cycle_is_not_invisible(tmp_path):
    doc = fx.chain_yaml(cycle=True)
    doc["nodes"]["z1"] = {"title": {"en": "Z one", "zh": "Z一"}, "src": "synthetic",
                          "test": {"all": []}}
    doc["nodes"]["z2"] = {"title": {"en": "Z two", "zh": "Z二"}, "src": "synthetic",
                          "test": {"all": []}}
    doc["hops"].append({"from": "z1", "to": "z2", "sign": "+", "lag_d": [1, 2],
                        "label": {"en": "l", "zh": "l2"},
                        "condition": {"en": "c", "zh": "c2"},
                        "mechanism": {"en": "m", "zh": "m2"}})
    snap = _compose(fx.build_root(tmp_path, yaml_doc=doc,
                                  state_doc=fx.chain_state(cycle=True)))
    # The state now reports the OWNER's episode, which stays knowable even when
    # this surface cannot read every current condition. What these tests have
    # always been about is that an unreadable input must never INFLATE the
    # state, so they now pin that directly rather than through a proxy code.
    assert snap["state"]["activation"] is False
    assert snap["state"]["conditions"]["all_current_met"] is None
    assert any(g["kind"] == "path_incomplete" for g in snap["gaps"])


def test_duplicate_node_rows_in_owner_state_fail_closed(tmp_path):
    from engine.ontology_explorer import SourceIncoherent
    state = fx.chain_state()
    state["chains"][0]["nodes"].append(json.loads(json.dumps(state["chains"][0]["nodes"][0])))
    with pytest.raises(SourceIncoherent) as excinfo:
        _compose(fx.build_root(tmp_path, state_doc=state))
    assert "duplicate_node_rows" in str(excinfo.value)


def test_an_oversized_source_fails_closed_on_bytes(tmp_path):
    """The bound must cover payload size, not only node count."""
    from engine.ontology_explorer import SourceIncoherent
    state = fx.chain_state()
    state["chains"][0]["padding"] = "x" * 3_000_000
    with pytest.raises(SourceIncoherent) as excinfo:
        _compose(fx.build_root(tmp_path, state_doc=state))
    assert "source_exceeds_bound" in str(excinfo.value)


# B4 — transition identity, and generation age vs observation age
def test_a_transition_row_missing_its_identity_is_not_a_change(tmp_path):
    root = _root_with_episodes(tmp_path, [{"chain": fx.SLUG, "rev": 2}])
    snap = _compose(root)
    assert snap["what_changed"]["status"] == "comparison_unavailable"
    assert any(g["kind"] == "transitions_malformed" for g in snap["gaps"])


def test_a_transition_dated_after_the_owner_cutoff_is_refused(tmp_path):
    """A row dated past the artifact's own `asof` cannot be a change this
    artifact observed."""
    root = _root_with_episodes(tmp_path, [
        {"chain": fx.SLUG, "rev": 2, "episode_id": "ep-synthetic-1", "transition": "arming", "hop": 0, "asof": "2099-01-01"}])
    snap = _compose(root)
    assert snap["what_changed"]["status"] == "comparison_unavailable"
    assert any(g["kind"] == "transitions_after_cutoff" for g in snap["gaps"])


def test_corrupt_ledger_lines_are_disclosed_not_silently_dropped(tmp_path):
    root = fx.build_root(tmp_path)
    (root / "data" / "transmission" / "chain_episodes.jsonl").write_text(
        "{not json\n" + json.dumps({"chain": fx.SLUG, "rev": 2, "episode_id": "ep-synthetic-1", "transition": "arming", "hop": 0,
                                    "asof": "2026-01-02"}) + "\n", encoding="utf-8")
    snap = _compose(root)
    assert any(g["kind"] == "transitions_unreadable" for g in snap["gaps"])


def test_generation_age_and_observation_age_are_distinct(tmp_path):
    """`built` is when the artifact was generated; `asof` is what it observed.
    A freshly generated old observation is not a current one."""
    freshness = _compose(fx.build_root(tmp_path))["source"]["freshness"]
    assert freshness["generation_age_basis"] == "chain_state.built"
    assert freshness["observation_asof"] == "2026-01-02"
    assert "observation_age_days" in freshness


# B5 — exposure screens are not display rights
def test_exposure_screens_are_not_presented_as_rights(tmp_path):
    """The YAML's `exposure_screens` are valuation / refinancing / capex / FCF
    context. They are not permission to display anything, and labelling them
    `rights` invented a license status the owners never granted."""
    snap = _compose(fx.build_root(tmp_path))
    assert "rights" not in snap
    assert snap["exposure_screens"][0]["id"] == "synthetic_screen"


def test_display_permission_is_reported_as_not_determined_here(tmp_path):
    snap = _compose(fx.build_root(tmp_path))
    assert snap["display_permission"]["status"] == "not_determined_here"


# B6 — the manifest must bind the composer method, not only the bytes read
def test_the_manifest_hash_binds_the_composer_method_version(tmp_path):
    from engine.ontology_explorer import COMPOSER_METHOD, manifest_hash_for
    snap = _compose(fx.build_root(tmp_path))
    source = snap["source"]
    assert source["composer_method"] == COMPOSER_METHOD
    assert source["source_manifest_hash"] == manifest_hash_for(
        source["reads"], method=COMPOSER_METHOD)
    assert manifest_hash_for(source["reads"], method="something.else.v9") != \
        source["source_manifest_hash"]


def test_every_next_action_names_a_handler_the_client_implements():
    """A card that says 'open the evidence' with nothing behind it is a caption,
    not an action. Every branch must name a handler and, where the handler needs
    one, a target that resolves to a leg actually on the page."""
    from engine.ontology_explorer import _next_action
    legs = [
        {"node_id": "a", "index": 1, "title": {"en": "First step", "zh": "第一环节"}},
        {"node_id": "b", "index": 2, "title": {"en": "Second step", "zh": "第二环节"}},
    ]
    blocking = {"node_id": "a", "index": 1, "title": legs[0]["title"]}
    contradiction = {"confirmed_downstream": ["b"], "blocking_upstream": "a"}
    cases = [
        _next_action("unknown", None, None, ["b"], legs),
        _next_action("dormant", blocking, contradiction, [], legs),
        _next_action("dormant", blocking, None, [], legs),
        _next_action("active", None, None, [], legs),
    ]
    node_ids = {leg["node_id"] for leg in legs}
    for action in cases:
        assert action["handler"] in {"focus_leg", "open_transmission"}
        if action["handler"] == "focus_leg":
            assert action["target"] in node_ids
        else:
            assert action["target"] is None


def test_no_action_advertises_an_inverse_comparison_that_was_never_built():
    """An inverse-path switch needs a proven inverse path. None is defined for
    this chain, so no state may offer the comparison."""
    from engine.ontology_explorer import _next_action
    legs = [{"node_id": "a", "index": 1, "title": {"en": "First", "zh": "第一"}}]
    for state in ("active", "dormant", "unknown", "degraded"):
        for blocking in (None, {"node_id": "a", "index": 1, "title": legs[0]["title"]}):
            action = _next_action(state, blocking, None, [], legs)
            assert action["code"] != "compare_inverse_path"
            assert "inverse" not in json.dumps(action).lower()


def test_the_action_label_never_carries_a_raw_node_id():
    """`wait_for_named_condition` used to interpolate the slug straight into the
    sentence, putting an internal identifier on a customer surface in both
    languages."""
    from engine.ontology_explorer import _next_action
    legs = [{"node_id": "breakeven_rise", "index": 1,
             "title": {"en": "Breakevens rise", "zh": "盈亏平衡上行"}}]
    action = _next_action("unknown", None, None, ["breakeven_rise"], legs)
    assert "breakeven_rise" not in action["label"]["en"]
    assert "breakeven_rise" not in action["label"]["zh"]
    assert "Breakevens rise" in action["label"]["en"]


def test_an_action_for_an_unknown_node_degrades_instead_of_printing_the_slug():
    from engine.ontology_explorer import _next_action
    action = _next_action("unknown", None, None, ["ghost_node"], [])
    assert "ghost_node" not in action["label"]["en"]
    assert "ghost_node" not in action["label"]["zh"]


def test_a_ledger_too_long_to_read_is_not_reported_as_corrupt_rows(tmp_path):
    """The row cap used to increment `malformed` and break, so a ledger this
    page merely stopped reading was reported to the reader as the owners having
    written bad data. Truncation is our limitation and is disclosed as ours."""
    from engine.ontology_explorer import MAX_EPISODE_ROWS
    row = json.dumps({"chain": fx.SLUG, "rev": 2, "episode_id": "ep-synthetic-1", "transition": "arming", "hop": 0,
                      "asof": "2026-01-01"})
    root = fx.build_root(tmp_path)
    (root / "data" / "transmission" / "chain_episodes.jsonl").write_text(
        "\n".join([row] * (MAX_EPISODE_ROWS + 50)) + "\n", encoding="utf-8")
    snap = _compose(root)
    assert _has_gap(snap["gaps"], kind="episode_ledger_truncated",
                    read_rows=MAX_EPISODE_ROWS, reason="exceeds_read_bound")
    assert not _has_gap(snap["gaps"], kind="transitions_malformed")
    truncation = next(g for g in snap["gaps"]
                      if g["kind"] == "episode_ledger_truncated")
    assert truncation["reason_label"]["en"] and truncation["reason_label"]["zh"]


# ==========================================================================
# Sol analytical support F04-EXACT-MODULE-SUPPORT-56649 — class A:
# owner episode state is not instantaneous coincidence
# ==========================================================================

@pytest.mark.parametrize(
    "owner_state,extra,expected_code",
    [
        ("failed", {}, "ended"),
        ("expired", {}, "ended"),
        ("dormant", {"arm_veto": {"why": "synthetic"}}, "dormant"),
        ("arming", {"arm_veto": {"why": "synthetic"}}, "stopped"),
        ("arming", {"falsifier_fired": True}, "stopped"),
        ("propagating", {"falsifier_fired": True}, "stopped"),
        ("arming", {}, "active"),
        ("propagating", {}, "active"),
        ("expressed", {}, "completed"),
    ],
)
def test_all_conditions_true_does_not_override_the_owner_episode(
        tmp_path, owner_state, extra, expected_code):
    """Today's conditions all reading true is a description of TODAY, not an
    episode. The owner's chain is temporal: a chain whose conditions coincide may
    be merely arming, a fired watch condition stops it while those same
    conditions still read true, and failed/expired episodes end with their
    conditions unchanged. Deriving state from the node booleans emitted `active`
    against an owner reading `failed` with ZERO confirmed hops.

    Every case here holds the current node verdicts IDENTICAL (all true) and
    varies only the owner's episode, which is exactly the axis the old predicate
    could not see.
    """
    state = fx.chain_state(confirmed=(True, True, True, True))
    state["chains"][0]["state"] = owner_state
    state["chains"][0].update(extra)
    snap = _compose(fx.build_root(tmp_path, state_doc=state))

    # the coincidence is reported, as its own separate fact
    assert snap["state"]["conditions"]["all_current_met"] is True
    assert snap["state"]["conditions"]["describes"] == "current_readings_only"
    # ... and it does not decide the state
    assert snap["state"]["code"] == expected_code
    assert snap["state"]["activation"] is (expected_code == "active")
    assert snap["state"]["basis"] == "owner_episode"


def test_a_stopped_episode_is_not_reported_as_merely_dormant(tmp_path):
    """`dormant` reads as "never started". An episode a watch condition stopped
    did start, and saying otherwise loses the thing the reader most needs."""
    state = fx.chain_state(confirmed=(True, True, True, True))
    state["chains"][0]["state"] = "propagating"
    state["chains"][0]["falsifier_fired"] = True
    snap = _compose(fx.build_root(tmp_path, state_doc=state))
    assert snap["state"]["code"] == "stopped"
    assert snap["state"]["watch_condition_fired"] is True


def test_an_owner_state_outside_the_owner_vocabulary_is_unknown_not_guessed(tmp_path):
    """Defaulting an unrecognised owner state would put the whole surface back on
    instantaneous coincidence through the fallback branch."""
    state = fx.chain_state(confirmed=(True, True, True, True))
    state["chains"][0]["state"] = "synthetic_not_a_real_owner_state"
    snap = _compose(fx.build_root(tmp_path, state_doc=state))
    assert snap["state"]["code"] == "unknown"
    assert snap["state"]["activation"] is None
    assert _has_gap(snap["gaps"], kind="owner_state_unrecognised")


def test_a_missing_owner_state_is_unknown_and_named(tmp_path):
    state = fx.chain_state(confirmed=(True, True, True, True))
    state["chains"][0].pop("state", None)
    snap = _compose(fx.build_root(tmp_path, state_doc=state))
    assert snap["state"]["code"] == "unknown"
    assert snap["state"]["activation"] is None
    assert _has_gap(snap["gaps"], kind="owner_state_absent")


def test_the_payload_never_ships_the_owners_refutation_key_name(tmp_path):
    """The owner spells this `falsifier_fired`. The payload is a reader-facing
    surface and this product does not ship that family anywhere on one."""
    snap = _compose(fx.build_root(tmp_path))
    assert "watch_condition_fired" in snap["state"]
    assert "falsifier_fired" not in json.dumps(snap)


# class D — the future-time false zero, on the SECOND clock
def test_an_observation_dated_in_the_future_is_not_an_age_of_zero(tmp_path):
    """`max(0, ...)` on the new observation clock turned a reading dated in the
    future into "observed today" — the most confident possible answer to a
    question the data cannot answer. The build stamp already refused this."""
    state = fx.chain_state()
    state["asof"] = "2099-01-01"
    snap = _compose(fx.build_root(tmp_path, state_doc=state))
    freshness = snap["source"]["freshness"]
    assert freshness["observation_age_days"] is None
    assert freshness["observation_age_basis"] == "observation_date_in_future"
    assert _has_gap(snap["gaps"], kind="observation_date_in_future")


def test_an_unreadable_observation_date_is_distinguished_from_a_future_one(tmp_path):
    state = fx.chain_state()
    state["asof"] = "not-a-date"
    snap = _compose(fx.build_root(tmp_path, state_doc=state))
    freshness = snap["source"]["freshness"]
    assert freshness["observation_age_days"] is None
    assert freshness["observation_age_basis"] == "unparseable_observation_date"


# class B — the owner's whole native transition key
@pytest.mark.parametrize("bad_rev", [None, "2", "99", True])
def test_a_non_integer_revision_is_not_an_owner_transition(tmp_path, bad_rev):
    """`_episode_rows` excluded only a DIFFERENT INTEGER revision, so missing,
    null and string revisions survived — and `_what_changed` then filled the
    missing one in from the caller, manufacturing the identity the row failed."""
    row = {"chain": fx.SLUG, "episode_id": "ep-1", "transition": "arming",
           "hop": 0, "asof": "2026-01-02"}
    if bad_rev is not None:
        row["rev"] = bad_rev
    snap = _compose(_root_with_episodes(tmp_path, [row]))
    assert snap["what_changed"]["status"] != "recorded_transition"
    assert snap["evidence"]["k1"]["recorded_transitions"] == 0


def test_an_arbitrary_transition_name_is_not_an_owner_event(tmp_path):
    """The owner's vocabulary is closed (`_mk_transition` call sites). A date
    plus any string was being accepted as an event."""
    snap = _compose(_root_with_episodes(tmp_path, [
        {"chain": fx.SLUG, "rev": 2, "episode_id": "ep-1", "hop": 0,
         "transition": "SYNTHETIC_NOT_AN_OWNER_TRANSITION", "asof": "2026-01-02"}]))
    assert snap["what_changed"]["status"] != "recorded_transition"


@pytest.mark.parametrize("missing", ["episode_id", "hop"])
def test_a_row_without_the_owners_whole_key_is_not_a_transition(tmp_path, missing):
    """The native key is (chain, rev, episode_id, transition, hop, asof). A row
    was being accepted with episode_id=None and hop=None."""
    row = {"chain": fx.SLUG, "rev": 2, "episode_id": "ep-1", "transition": "arming",
           "hop": 0, "asof": "2026-01-02"}
    row.pop(missing)
    snap = _compose(_root_with_episodes(tmp_path, [row]))
    assert snap["what_changed"]["status"] != "recorded_transition"


# class C — an unread history is not a history of nothing
def test_an_entirely_corrupt_ledger_is_not_reported_as_no_history(tmp_path):
    """The prose said the owners recorded no transition. They may have recorded
    many; this page could not read them."""
    root = fx.build_root(tmp_path)
    (root / "data" / "transmission" / "chain_episodes.jsonl").write_text(
        "{not json\n{also not json\n", encoding="utf-8")
    snap = _compose(root)
    changed = snap["what_changed"]
    assert changed["status"] == "comparison_incomplete"
    assert changed["reason"] == "ledger_read_incomplete"
    assert "recorded no transition" not in changed["note"]["en"]


def test_a_truncated_history_is_not_reported_as_the_latest_change(tmp_path):
    """A ledger longer than the read bound was answered from its OLDEST prefix:
    the reported change was the 5,000th row from the start, not the newest."""
    from engine.ontology_explorer import MAX_EPISODE_ROWS
    old = [{"chain": fx.SLUG, "rev": 2, "episode_id": "ep-1", "transition": "arming",
            "hop": 0, "asof": "1993-09-08"}] * (MAX_EPISODE_ROWS + 10)
    newest = {"chain": fx.SLUG, "rev": 2, "episode_id": "ep-2",
              "transition": "expressed", "hop": 2, "asof": "2026-01-02"}
    snap = _compose(_root_with_episodes(tmp_path, [*old, newest]))
    changed = snap["what_changed"]
    assert changed["status"] == "comparison_incomplete"
    assert changed["items"] == []
    assert _has_gap(snap["gaps"], kind="episode_ledger_truncated")


# ==========================================================================
# class E — the output and typed-failure boundary
# ==========================================================================

def test_a_nested_object_in_an_owner_receipt_does_not_ride_into_the_response(tmp_path):
    """A contract witness, not an observed incident: receipts were passed through
    whole, so this tenant-neutral response's shape was whatever the owner
    artifact happened to carry — including a nested object."""
    state = fx.chain_state()
    state["chains"][0]["nodes"][0]["receipts"][0]["user"] = {"id": "SYNTHETIC-SENTINEL"}
    snap = _compose(fx.build_root(tmp_path, state_doc=state))
    # An UNDECLARED field is outside this product's shape, so it is dropped as a
    # boundary rather than reported as a gap in the owner's data.
    assert "SYNTHETIC-SENTINEL" not in json.dumps(snap)
    assert "user" not in snap["path"]["legs"][0]["receipts"][0]
    # the legitimate fields still arrive
    assert snap["path"]["legs"][0]["receipts"][0]["series"]


def test_a_nested_value_inside_a_declared_receipt_field_is_dropped_and_named(tmp_path):
    """A DECLARED field that is not a reading is a different thing from a field
    outside the contract: this one the reader was promised, so its absence is
    disclosed rather than silently trimmed."""
    state = fx.chain_state()
    state["chains"][0]["nodes"][0]["receipts"][0]["value"] = {"id": "SYNTHETIC-SENTINEL"}
    snap = _compose(fx.build_root(tmp_path, state_doc=state))
    assert "SYNTHETIC-SENTINEL" not in json.dumps(snap)
    assert "value" not in snap["path"]["legs"][0]["receipts"][0]
    assert _has_gap(snap["gaps"], kind="receipt_field_not_scalar")


def test_a_non_finite_receipt_value_is_refused_before_serialisation(tmp_path):
    """A non-finite float survived composition and then broke strict JSON at the
    transport edge, turning an upstream data problem into a 500 of ours."""
    state = fx.chain_state()
    state["chains"][0]["nodes"][0]["receipts"][0]["value"] = float("inf")
    snap = _compose(fx.build_root(tmp_path, state_doc=state))
    json.dumps(snap, allow_nan=False)  # the assertion: this must not raise
    assert snap["path"]["legs"][0]["receipts"][0]["value"] is None
    assert _has_gap(snap["gaps"], kind="receipt_value_not_finite")


def test_legitimate_zero_false_and_null_survive_the_receipt_contract(tmp_path):
    """The projection must not confuse "cannot be serialised" with "falsy"."""
    state = fx.chain_state()
    receipt = state["chains"][0]["nodes"][0]["receipts"][0]
    receipt["value"] = 0
    receipt["passed"] = False
    receipt["window"] = None
    snap = _compose(fx.build_root(tmp_path, state_doc=state))
    got = snap["path"]["legs"][0]["receipts"][0]
    assert got["value"] == 0
    assert got["passed"] is False
    assert got["window"] is None


def test_a_malformed_node_collection_is_a_typed_source_failure(tmp_path):
    """`nodes: 7` went straight to iteration and escaped as a generic internal
    error. A malformed owner structure is a source problem and says so."""
    from engine.ontology_explorer import SourceIncoherent
    state = fx.chain_state()
    state["chains"][0]["nodes"] = 7
    with pytest.raises(SourceIncoherent) as excinfo:
        _compose(fx.build_root(tmp_path, state_doc=state))
    assert "malformed_nodes" in str(excinfo.value)
