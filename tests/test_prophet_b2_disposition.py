"""B2-0 disposition matrix + mutation law — contract tests.

Two surfaces under test:

1. ``engine.prophet_b2_disposition`` — the frozen B-15..B-19 disposition matrix with
   deterministic classification, append-only correction/supersession lineage,
   point-in-time replay (FUTURE_KNOWLEDGE exclusion), and fail-closed mutation guards.

2. The five #6805 red-conditions as DISCRIMINATORS against the B1 event core
   (``engine.us_candidate_episode``, imported read-only): corrected-after-cut,
   retracted-trigger, and identity-supersession replays, each paired with the naive
   "current-state as history" answer so the test goes red if anyone swaps in a
   current-only reader.

Authority boundary: only tests may import ``engine.prophet_b2_disposition`` — the
tree-scan test at the bottom pins that no engine/scripts/app/lib module does.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

import engine.us_candidate_episode as b1
from engine.prophet_b2_disposition import (
    DISPOSITION_CLASSES,
    DISPOSITION_MATRIX,
    DISPOSITION_RULE_VERSION,
    DispositionContractError,
    FINDING_IDS,
    build_matrix,
    disposition,
    supersede,
)


# ────────────────────────────────────────────────────────── shared fixtures ──

#: The date every baked v1 record became knowable (the packet's verification date).
BAKED_KNOWN_AT = "2026-09-04"

#: The classes the v1 matrix actually assigns — pinned so a silent rebake is loud.
BAKED_CLASSES = {
    "B-15": "PROVEN_CLOSED",
    "B-16": "PROVEN_CLOSED",
    "B-17": "STILL_LIVE",
    "B-18": "PROVEN_CLOSED",
    "B-19": "PROVEN_CLOSED",
}


def _record(finding_id: str = "B-16", *, seq: int = 1, supersedes=None,
            known_at: str = "2026-09-01", clazz: str = "BUILT_NOT_PROVEN",
            **overrides) -> dict:
    """A minimal lawful disposition record for mutation-control tests."""
    record = {
        "finding_id": finding_id,
        "owner": "WS:PROPHET-US-V4-RECOVERY.b2",
        "disposition": clazz,
        "reason": "test record — stable string",
        "rule_version": DISPOSITION_RULE_VERSION,
        "evidence": [{"cite": "tests/test_prophet_b2_disposition.py fixture", "pin": "f" * 40}],
        "known_at": known_at,
        # recorded on the day the evidence became knowable (keeps known_at <= recorded_at)
        "recorded_at": known_at if isinstance(known_at, str) else "2026-09-04",
        "seq": seq,
        "supersedes": supersedes,
    }
    record.update(overrides)
    return record


# ── B1 fixtures (mirroring tests/test_us_candidate_episode.py conventions) ──

SECURITY_ID = "SEC:US-XNAS-XYZ"
COMPANY_ID = "ISS:US-XNAS-XYZ"
ERA = b1.DEFAULT_DEFINITION_ERA
RECORDED_AT = "2026-08-30T00:00:00Z"
T0, T1, T2 = "2026-08-24T20:00:00Z", "2026-08-25T20:00:00Z", "2026-08-27T20:00:00Z"
ANCHOR = {
    "kind": "turn_watch_reset_low",
    "time": "2026-08-24T20:00:00Z",
    "price": 42.1,
    "basis": "adjusted_close",
}


def _event(event_type: str, episode: str, *, payload: dict, source_event_id: str,
           known_at: str, correction_of=None) -> dict:
    return b1.make_event(
        event_type=event_type,
        episode_id=episode,
        source_system="b2_disposition_test",
        source_schema="test.source/v1",
        source_event_id=source_event_id,
        occurred_at=known_at,
        known_at=known_at,
        recorded_at=RECORDED_AT,
        source_receipt="sha256:test-source",
        definition_era=ERA,
        correction_of=correction_of,
        payload=payload,
    )


def _opened(episode: str, *, epoch: str = "epoch_0", state: str = "provisional",
            known_at: str = T0) -> dict:
    payload = {
        "security_id": SECURITY_ID,
        "company_id": COMPANY_ID,
        "identity_epoch": epoch,
        "identity_epoch_state": state,
        "identity_spec_schema": b1.STOCK_IDENTITY_SCHEMA,
        "identity_spec_hash": b1.STOCK_IDENTITY_SPEC_HASH,
        "structural_anchor": ANCHOR,
        "ticker_at_observation": "XYZ",
        "intake_class": "technical_emergence",
        "opened_at": known_at,
    }
    return _event("OPENED", episode, payload=payload,
                  source_event_id=f"open-{epoch}", known_at=known_at)


def _replay_at(events: list[dict], cut: str) -> list[dict]:
    """Point-in-time replay: only events knowable at the cut participate."""
    return b1.project_events([e for e in events if str(e["known_at"]) <= cut])


# ─────────────────────────────────────────── a. totality over FINDING_IDS ──

def test_disposition_is_total_over_the_five_findings():
    assert FINDING_IDS == ("B-15", "B-16", "B-17", "B-18", "B-19")
    for finding_id in FINDING_IDS:
        outcome = disposition(finding_id, as_of=BAKED_KNOWN_AT)
        assert outcome["finding_id"] == finding_id
        assert outcome["disposition"] in DISPOSITION_CLASSES
        assert outcome["reason"]
        assert outcome["evidence"], "a baked record must carry citations"
        pins = {entry["pin"] for entry in outcome["evidence"]}
        assert "edaf501ae7e4e1547e6124d50dd1b59e3cb17954" in pins, "audit-pin citation missing"
        assert "fdaf40910809de8da38e91c4696abfa22d2199e0" in pins, "HEAD citation missing"


def test_an_unknown_finding_id_fails_closed_not_defaulted():
    for bogus in ("B-14", "B-20", "", "b-15"):
        with pytest.raises(DispositionContractError, match="DISPOSITION_UNTOTAL"):
            disposition(bogus, as_of=BAKED_KNOWN_AT)


def test_the_baked_v1_classes_are_the_evidence_verified_ones():
    """The classes this packet actually verified (readiness doc vs HEAD fdaf4091).

    B-17 is the one finding that stays open: its measurement leg (J-16 re-measurement
    of the shipped union ∩ select_candidates roster) has never been run — §8.1 claim 1
    remains SUSPENDED. A rebake that silently closes it must fail here.
    """
    for finding_id, expected in BAKED_CLASSES.items():
        assert disposition(finding_id, as_of=BAKED_KNOWN_AT)["disposition"] == expected
    assert disposition("B-17", as_of=BAKED_KNOWN_AT)["disposition"] == "STILL_LIVE"
    legs = disposition("B-17", as_of=BAKED_KNOWN_AT)["evidence"]
    assert len(legs) >= 3, "B-17 must carry BOTH legs (measurement open + disclosure closed) plus the audit pin"


# ───────────────────────────── b. determinism + rule-version stamping ──────

def test_every_outcome_is_deterministic_and_rule_version_stamped():
    for finding_id in FINDING_IDS:
        first = disposition(finding_id, as_of=BAKED_KNOWN_AT)
        second = disposition(finding_id, as_of=BAKED_KNOWN_AT)
        assert first == second
        assert first["rule_version"] == DISPOSITION_RULE_VERSION
    # the synthesized pre-evidence outcome is stamped too — no unversioned answer exists
    early = disposition("B-15", as_of="2020-01-01")
    assert early["disposition"] == "UNKNOWN_EVIDENCE_REQUIRED"
    assert early["rule_version"] == DISPOSITION_RULE_VERSION


# ───────────────────────────────────────────── c. point-in-time replay ─────

def test_replay_reproduces_the_earlier_answer_after_a_supersession():
    t1, t2 = "2026-09-01", "2026-09-04"
    matrix = build_matrix([_record("B-16", seq=1, known_at=t1, clazz="BUILT_NOT_PROVEN")])
    assert disposition("B-16", as_of=t1, matrix=matrix)["disposition"] == "BUILT_NOT_PROVEN"

    superseding = _record(
        "B-16", seq=2, supersedes=1, known_at=t2, clazz="PROVEN_CLOSED",
        reason="drift gate + regeneration diff run green at HEAD")
    corrected = supersede(matrix, superseding)

    # the earlier answer is reproduced AT its own as_of even after the supersession
    assert disposition("B-16", as_of=t1, matrix=corrected)["disposition"] == "BUILT_NOT_PROVEN"
    # at and after t2 the superseding record wins
    assert disposition("B-16", as_of=t2, matrix=corrected)["disposition"] == "PROVEN_CLOSED"
    assert disposition("B-16", as_of="2026-12-31", matrix=corrected)["disposition"] == "PROVEN_CLOSED"
    # FUTURE_KNOWLEDGE: a record known only later can never leak backward
    before = disposition("B-16", as_of="2026-08-31", matrix=corrected)
    assert before["disposition"] == "UNKNOWN_EVIDENCE_REQUIRED"
    assert "FUTURE_KNOWLEDGE" in before["reason"]


def test_no_record_knowable_at_as_of_is_never_read_as_closed():
    for finding_id in FINDING_IDS:
        outcome = disposition(finding_id, as_of="2026-09-03")  # eve of the baked known_at
        assert outcome["disposition"] == "UNKNOWN_EVIDENCE_REQUIRED"
        assert outcome["evidence"] == ()


# ──────────────────────────────────────────────── d. append-only law ───────

def test_supersede_appends_and_refuses_in_place_mutation():
    superseding = _record("B-16", seq=2, supersedes=1, known_at="2026-09-05",
                          clazz="STILL_LIVE", reason="seeded demotion — test only")
    corrected = supersede(DISPOSITION_MATRIX, superseding)
    assert len(corrected) == len(DISPOSITION_MATRIX) + 1
    # the base matrix object is untouched (append-only, no in-place growth)
    assert len(DISPOSITION_MATRIX) == 5

    # a frozen prior record refuses field assignment outright
    prior = corrected[0]
    with pytest.raises((TypeError, DispositionContractError)):
        prior["disposition"] = "PROVEN_CLOSED"  # type: ignore[index]
    with pytest.raises((TypeError, DispositionContractError)):
        prior["evidence"][0]["cite"] = "rewritten"  # type: ignore[index]

    # the original superseded record is still retrievable at its own as_of
    original = disposition("B-16", as_of=BAKED_KNOWN_AT, matrix=corrected)
    assert original["disposition"] == "PROVEN_CLOSED"
    assert original["seq"] == 1


# ──────────────────────────────── e. fail-closed mutation controls ─────────

def test_a_record_with_no_owner_fails_closed():
    orphan = _record("B-15", seq=2, supersedes=1, known_at="2026-09-05")
    del orphan["owner"]
    with pytest.raises(DispositionContractError, match="OWNER_UNKNOWN"):
        supersede(DISPOSITION_MATRIX, orphan)
    with pytest.raises(DispositionContractError, match="OWNER_UNKNOWN"):
        supersede(DISPOSITION_MATRIX,
                  _record("B-15", seq=2, supersedes=1, known_at="2026-09-05", owner=None))


def test_a_record_with_no_known_at_fails_closed():
    unsourced = _record("B-15", seq=2, supersedes=1)
    del unsourced["known_at"]
    with pytest.raises(DispositionContractError, match="SOURCE_UNKNOWN"):
        supersede(DISPOSITION_MATRIX, unsourced)
    with pytest.raises(DispositionContractError, match="SOURCE_UNKNOWN"):
        supersede(DISPOSITION_MATRIX,
                  _record("B-15", seq=2, supersedes=1, known_at=None))


def test_a_foreign_rule_version_fails_closed():
    with pytest.raises(DispositionContractError, match="RULE_VERSION_UNKNOWN"):
        supersede(DISPOSITION_MATRIX,
                  _record("B-15", seq=2, supersedes=1, known_at="2026-09-05",
                          rule_version="b2-disposition-v0-2026-08-11"))


def test_a_correction_chain_gap_fails_closed():
    # skipping a link: seq 3 claiming to supersede a seq 2 that never existed
    with pytest.raises(DispositionContractError, match="CORRECTION_CHAIN_BROKEN"):
        supersede(DISPOSITION_MATRIX,
                  _record("B-15", seq=3, supersedes=2, known_at="2026-09-05"))
    # a second root beside an existing chain is a fork, not a correction
    with pytest.raises(DispositionContractError, match="CORRECTION_CHAIN_BROKEN"):
        supersede(DISPOSITION_MATRIX,
                  _record("B-15", seq=1, supersedes=None, known_at="2026-09-05"))
    # a correction backdated before its predecessor rewrites history
    with pytest.raises(DispositionContractError, match="CORRECTION_CHAIN_BROKEN"):
        supersede(DISPOSITION_MATRIX,
                  _record("B-15", seq=2, supersedes=1, known_at="2026-09-01"))


def test_a_tampered_base_matrix_fails_closed_before_any_append():
    thawed = [dict(record, evidence=[dict(entry) for entry in record["evidence"]])
              for record in DISPOSITION_MATRIX]
    thawed[0]["rule_version"] = "b2-disposition-v9-rogue"
    with pytest.raises(DispositionContractError, match="RULE_VERSION_UNKNOWN"):
        supersede(thawed, _record("B-16", seq=2, supersedes=1, known_at="2026-09-05"))


# ── f. the five #6805 red-conditions, as discriminators against the B1 core ──

def test_red_condition_corrected_after_cut_does_not_alter_replay_at_the_cut():
    """#6805 red-condition: a CORRECTED event known after a decision cut must not
    rewrite what was decided at that cut — and a current-only reader provably would."""
    episode = b1.episode_id(SECURITY_ID, "epoch_0", ANCHOR, 1)
    opened = _opened(episode, known_at=T0)
    correction = _event(
        "CORRECTED", episode,
        payload={"patch": {"ticker_at_observation": "XYZQ"}},
        source_event_id="correction-1", known_at=T2,
        correction_of=opened["event_id"])
    tape = [opened, correction]

    pit = _replay_at(tape, T1)
    assert pit[0]["ticker_at_observation"] == "XYZ"
    assert pit[0]["correction_state"] == "current"
    # the cut replay is byte-identical to a world where the correction never happened
    assert b1.canonical_json(pit) == b1.canonical_json(b1.project_events([opened]))

    naive = b1.project_events(tape)  # "current state as history"
    assert naive[0]["ticker_at_observation"] == "XYZQ"
    assert naive[0]["correction_state"] == "corrected"
    assert naive[0]["ticker_at_observation"] != pit[0]["ticker_at_observation"], (
        "a current-only reader would silently rewrite the decision-time tape")


def test_red_condition_a_retracted_trigger_does_not_remain_active():
    """#6805 red-condition: a retracted trigger must vanish from the projection —
    and a reader that drops RETRACTED events provably resurrects it."""
    episode = b1.episode_id(SECURITY_ID, "epoch_0", ANCHOR, 1)
    opened = _opened(episode, known_at=T0)
    retraction = _event(
        "RETRACTED", episode,
        payload={"reason": "source retraction — trigger withdrawn"},
        source_event_id="retract-1", known_at=T2,
        correction_of=opened["event_id"])

    assert b1.project_events([opened, retraction]) == []

    naive = b1.project_events([opened])  # ignores the retraction
    assert len(naive) == 1 and naive[0]["episode_state"] == "ACTIVE", (
        "the discriminator itself must be non-vacuous: without the retraction the "
        "trigger IS active, so dropping RETRACTED events flips the answer")


def test_red_condition_identity_supersession_fails_closed_for_stale_identity_reads():
    """#6805 red-condition: an identity-epoch change marks the old episode superseded
    point-in-time, and a NON-provisional identity refuses supersession outright."""
    episode = b1.episode_id(SECURITY_ID, "epoch_0", ANCHOR, 1)
    successor = b1.episode_id(SECURITY_ID, "epoch_1", ANCHOR, 1)
    opened = _opened(episode, known_at=T0)
    superseded = _event(
        "IDENTITY_SUPERSEDED", episode,
        payload={"successor_episode_id": successor, "reason": "identity epoch rolled"},
        source_event_id="supersede-1", known_at=T2,
        correction_of=None)
    tape = [opened, superseded]

    pit = _replay_at(tape, T1)
    assert pit[0]["superseded_by"] is None, "supersession must not leak before its known_at"
    current = b1.project_events(tape)
    assert current[0]["superseded_by"] == successor
    assert pit[0]["superseded_by"] != current[0]["superseded_by"], (
        "a current-only reader stamps the stale identity as already superseded at the cut")

    # fail-closed: a ratified (non-provisional) identity cannot be superseded at all
    ratified_episode = b1.episode_id(SECURITY_ID, "epoch_1", ANCHOR, 1)
    ratified = _opened(ratified_episode, epoch="epoch_1", state="ratified", known_at=T0)
    stale_write = _event(
        "IDENTITY_SUPERSEDED", ratified_episode,
        payload={"successor_episode_id": episode, "reason": "stale write"},
        source_event_id="supersede-2", known_at=T2,
        correction_of=None)
    with pytest.raises(b1.EpisodeContractError, match="provisional"):
        b1.project_events([ratified, stale_write])


# ──────────────────────────────────────── g. authority-negative boundary ───

def test_no_engine_scripts_app_or_lib_module_imports_the_disposition_matrix():
    """B2-0 carries NO authority: nothing outside tests/ may import the module."""
    root = Path(__file__).resolve().parents[1]
    own_module = root / "engine" / "prophet_b2_disposition.py"
    needle = re.compile(r"prophet_b2_disposition")
    offenders = []
    for tree in ("engine", "scripts", "app", "lib"):
        base = root / tree
        if not base.is_dir():
            continue
        for path in sorted(base.rglob("*.py")):
            if path == own_module:
                continue
            if needle.search(path.read_text(encoding="utf-8", errors="replace")):
                offenders.append(str(path.relative_to(root)))
    assert offenders == [], f"authority leak: {offenders} import the disposition matrix"
    assert own_module.exists(), "the module this boundary protects must exist"
