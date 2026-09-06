"""Deterministic policy lifecycle state machine — MO-DELTA-032.

Pure fixtures only: no network, no dependency on data/ (sparse-tree safe).
"""
from __future__ import annotations

import inspect
import json
import random
from pathlib import Path

from engine.policy_intent_desk import (
    LIFECYCLE_EVENT_TYPES,
    LIFECYCLE_STAGES,
    STALL_DAYS,
    fold_lifecycle,
    ingest_lifecycle,
    lifecycle_events,
    lifecycle_view,
)

REG = [{"id": "L1", "title_en": "Lever One", "title_zh": "杠杆一",
        "jurisdiction": "US-FED", "jurisdiction_en": "United States — federal", "jurisdiction_zh": "美国联邦"}]


def _ev(item_id, typ, event_date, known_at, url="https://www.federalregister.gov/x", event_id=None):
    return {
        "event_id": event_id or f"{item_id}-{typ}-{event_date}",
        "item_id": item_id, "jurisdiction": "US-FED", "type": typ,
        "event_date": event_date, "known_at": known_at,
        "source": {"url": url, "title": "doc", "doc_id": "1"},
        "corrects": None, "reason": None, "logged_at": known_at,
        "schema": "policy_lifecycle.v1",
    }


def test_every_forward_transition_folds_to_its_state():
    events = [
        _ev("L1", "proposed", "2026-01-01", "2026-01-02T00:00:00Z"),
        _ev("L1", "passed", "2026-02-01", "2026-02-02T00:00:00Z"),
        _ev("L1", "in_force", "2026-03-01", "2026-03-02T00:00:00Z"),
        _ev("L1", "enforced", "2026-04-01", "2026-04-02T00:00:00Z"),
    ]
    row = fold_lifecycle(events, REG)[0]
    assert row["state"] == "enforced"
    assert row["stage_rank"] == LIFECYCLE_STAGES.index("enforced")
    assert row["reached"] == list(LIFECYCLE_STAGES)
    assert row["gaps"] == []


def test_skipped_stage_reports_gap_and_never_promotes():
    events = [
        _ev("L1", "proposed", "2026-01-01", "2026-01-02T00:00:00Z"),
        _ev("L1", "in_force", "2026-03-01", "2026-03-02T00:00:00Z"),
    ]
    row = fold_lifecycle(events, REG)[0]
    assert row["state"] == "in_force"
    assert row["gaps"] == ["passed"]
    # MAJOR-1: meter fills only observed stages — never conflates undocumented ones.
    assert "passed" not in row["reached"]
    assert row["reached"] == ["proposed", "in_force"]


def test_backward_event_sets_conflict_and_preserves_prior_state():
    events = [
        _ev("L1", "enforced", "2026-04-01", "2026-04-02T00:00:00Z"),
        _ev("L1", "proposed", "2026-01-01", "2026-05-01T00:00:00Z"),  # known later, rank lower
    ]
    row = fold_lifecycle(events, REG)[0]
    assert row["conflict"] is True
    assert row["state"] == "enforced"


def test_terminal_states_are_terminal_until_reinstated():
    for terminal in ("withdrawn", "struck_down", "superseded"):
        events = [
            _ev("L1", "in_force", "2026-03-01", "2026-03-02T00:00:00Z"),
            _ev("L1", terminal, "2026-04-01", "2026-04-02T00:00:00Z"),
            _ev("L1", "in_force", "2026-05-01", "2026-05-02T00:00:00Z"),  # must not resurrect
        ]
        row = fold_lifecycle(events, REG)[0]
        assert row["state"] == terminal, terminal

        events.append(_ev("L1", "reinstated", "2026-06-01", "2026-06-02T00:00:00Z"))
        row2 = fold_lifecycle(events, REG)[0]
        assert row2["state"] == "in_force", terminal


def test_correction_is_a_typed_state_and_appends():
    events = [
        _ev("L1", "passed", "2026-02-01", "2026-02-02T00:00:00Z"),
        {**_ev("L1", "correction", "2026-02-05", "2026-02-06T00:00:00Z"),
         "corrects": "L1-passed-2026-02-01", "reason": "date fixed",
         "corrected_type": "passed", "corrected_event_date": "2026-02-03"},
    ]
    row = fold_lifecycle(events, REG)[0]
    assert row["corrected"] is True
    assert row["state"] == "passed"
    assert row["state_asof"] == "2026-02-03"
    assert row["conflict"] is False


def test_correction_repairs_overstated_ladder_without_conflict():
    events = [
        _ev("L1", "proposed", "2026-01-01", "2026-01-02T00:00:00Z"),
        _ev("L1", "in_force", "2026-03-01", "2026-03-02T00:00:00Z"),
        {**_ev("L1", "correction", "2026-03-05", "2026-03-06T00:00:00Z"),
         "corrected_type": "passed", "corrected_event_date": "2026-02-01",
         "reason": "we recorded enforcement; it had only passed"},
    ]
    row = fold_lifecycle(events, REG)[0]
    assert row["corrected"] is True
    assert row["state"] == "passed"
    assert row["state_asof"] == "2026-02-01"
    assert row["conflict"] is False
    assert "in_force" not in row["reached"]


def test_correction_repairs_post_terminal_misrecord():
    events = [
        _ev("L1", "in_force", "2026-03-01", "2026-03-02T00:00:00Z"),
        _ev("L1", "withdrawn", "2026-04-01", "2026-04-02T00:00:00Z"),
        {**_ev("L1", "correction", "2026-04-05", "2026-04-06T00:00:00Z"),
         "corrected_type": "enforced", "corrected_event_date": "2026-04-03",
         "reason": "withdrawn was a mis-tag; rule was enforced"},
    ]
    row = fold_lifecycle(events, REG)[0]
    assert row["corrected"] is True
    assert row["state"] == "enforced"
    assert row["state_asof"] == "2026-04-03"


def test_stalled_when_no_forward_motion_past_threshold():
    events = [
        _ev("L1", "proposed", "2026-01-01", "2026-01-02T00:00:00Z"),
        _ev("L1", "passed", "2026-02-01", "2026-02-02T00:00:00Z"),
    ]
    row = fold_lifecycle(events, REG, as_of_date="2026-04-15")[0]
    assert STALL_DAYS == 45
    assert row["stalled"] is True
    row2 = fold_lifecycle(events, REG, as_of_date="2026-02-20")[0]
    assert row2["stalled"] is False


def test_registered_item_with_no_events_is_unknown_not_zero():
    row = fold_lifecycle([], REG)[0]
    assert row["state"] == "unknown"
    assert row["why"] == "no_document"
    assert row["stage_rank"] is None


def test_absent_jurisdiction_is_not_fabricated():
    reg = [{"id": "L1", "title_en": "Lever One", "title_zh": "杠杆一"}]
    row = fold_lifecycle([_ev("L1", "proposed", "2026-01-01", "2026-01-02T00:00:00Z")], reg)[0]
    assert row["jurisdiction_en"] is None
    assert row["jurisdiction_zh"] is None


def test_absent_store_yields_typed_no_coverage_and_still_renders_items(tmp_path):
    (tmp_path / "data" / "policy").mkdir(parents=True)
    (tmp_path / "data" / "policy" / "intel.json").write_text(
        '{"as_of":"2026-09-01","administration":{"verified_levers":'
        '[{"id":"L1","title_en":"Lever One","title_zh":"杠杆一","jurisdiction":"US-FED"}]}}'
    )
    view = lifecycle_view(tmp_path)
    assert view["null_reason"] == "no_coverage"
    assert len(view["items"]) == 1


def test_rights_suppressed_outranks_empty_store(tmp_path):
    (tmp_path / "data" / "policy").mkdir(parents=True)
    (tmp_path / "data" / "policy" / "intel.json").write_text(
        '{"as_of":"2026-09-01","policy_lifecycle_suppressed":true,'
        '"administration":{"verified_levers":'
        '[{"id":"L1","title_en":"Lever One","title_zh":"杠杆一"}]}}'
    )
    view = lifecycle_view(tmp_path)
    assert view["null_reason"] == "rights_suppressed"
    assert view["items"] == []


def test_seed_substrate_advances_real_shaped_levers(tmp_path):
    """BLOCKER-1: when intel lacks policy_lifecycle, the committed seed still advances."""
    (tmp_path / "data" / "policy").mkdir(parents=True)
    (tmp_path / "config").mkdir(parents=True)
    levers = [
        {"id": "lever_issuance", "title_en": "Bill-heavy issuance", "title_zh": "偏短端发债",
         "basis": "FACT", "detail_en": "Treasury bills.", "detail_zh": "国库券。"},
        {"id": "lever_chips", "title_en": "Chip tariff", "title_zh": "芯片关税",
         "basis": "FACT", "detail_en": "Tariff.", "detail_zh": "关税。"},
    ]
    (tmp_path / "data" / "policy" / "intel.json").write_text(json.dumps({
        "as_of": "2026-07-13",
        "administration": {"verified_levers": levers},
    }))
    seed = json.loads(Path("config/policy_lifecycle_seed.json").read_text())
    (tmp_path / "config" / "policy_lifecycle_seed.json").write_text(json.dumps(seed))
    view = lifecycle_view(tmp_path)
    assert view["null_reason"] is None
    by_id = {it["id"]: it for it in view["items"]}
    assert by_id["lever_issuance"]["state"] == "enforced"
    assert by_id["lever_issuance"]["state_asof"]
    assert by_id["lever_issuance"]["source"]["url"]
    assert by_id["lever_chips"]["state"] == "in_force"
    # Full ladder for issuance was observed — no undocumented fill.
    assert by_id["lever_issuance"]["reached"] == list(LIFECYCLE_STAGES)


def test_proposal_is_never_conflated_with_enactment():
    proposed_row = fold_lifecycle([_ev("L1", "proposed", "2026-01-01", "2026-01-02T00:00:00Z")], REG)[0]
    assert proposed_row["state"] != "in_force"
    assert proposed_row["state"] != "enforced"

    in_force_row = fold_lifecycle([_ev("L1", "in_force", "2026-03-01", "2026-03-02T00:00:00Z")], REG)[0]
    assert in_force_row["state"] == "in_force"
    assert in_force_row["reached"] == ["in_force"]
    assert in_force_row["gaps"] == ["proposed", "passed"]


def test_ingest_is_idempotent(tmp_path, monkeypatch):
    monkeypatch.setenv("COLLECT_LANE", "nightly")
    (tmp_path / "data" / "policy").mkdir(parents=True)
    (tmp_path / "data" / "policy" / "intel.json").write_text(
        '{"policy_lifecycle":[{"item_id":"L1","type":"proposed","event_date":"2026-01-01",'
        '"known_at":"2026-01-02T00:00:00Z","source":{"url":"https://www.federalregister.gov/x"}}]}'
    )
    n1 = ingest_lifecycle(tmp_path)
    n2 = ingest_lifecycle(tmp_path)
    assert n1 == 1
    assert n2 == 0
    assert len(lifecycle_events(tmp_path)) == 1


def test_ingest_is_gated_to_the_nightly_lane(tmp_path, monkeypatch):
    monkeypatch.delenv("COLLECT_LANE", raising=False)
    monkeypatch.delenv("US_LANE", raising=False)
    (tmp_path / "data" / "policy").mkdir(parents=True)
    (tmp_path / "data" / "policy" / "intel.json").write_text(
        '{"policy_lifecycle":[{"item_id":"L1","type":"proposed","event_date":"2026-01-01",'
        '"known_at":"2026-01-02T00:00:00Z","source":{"url":"https://www.federalregister.gov/x"}}]}'
    )
    n = ingest_lifecycle(tmp_path)
    assert n == 0
    assert not (tmp_path / "data" / "policy_lifecycle" / "events.jsonl").exists()


def test_fold_is_order_independent():
    events = [
        _ev("L1", "proposed", "2026-01-01", "2026-01-02T00:00:00Z"),
        _ev("L1", "passed", "2026-02-01", "2026-02-02T00:00:00Z"),
        _ev("L1", "in_force", "2026-03-01", "2026-03-02T00:00:00Z"),
    ]
    shuffled = list(events)
    random.Random(7).shuffle(shuffled)
    a = fold_lifecycle(events, REG)
    b = fold_lifecycle(shuffled, REG)
    assert a == b


def test_lifecycle_never_calls_the_llm():
    for fn in (fold_lifecycle, lifecycle_view, ingest_lifecycle):
        src = inspect.getsource(fn)
        for banned in ("synthesize", "call(", "_SYSTEM", "api_key"):
            assert banned not in src, f"{fn.__name__} references {banned!r}"


def test_all_event_types_are_declared():
    assert set(LIFECYCLE_EVENT_TYPES) >= {"proposed", "passed", "in_force", "enforced",
                                           "withdrawn", "struck_down", "superseded",
                                           "correction", "reinstated"}
