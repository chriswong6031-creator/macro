"""Tests for scripts/heal_subsector_rotation_ledgers.py — calendar-asof audit 2026-08-05.

The heal re-keys the three data/subsector_rotation/ ledgers off the NYSE CALENDAR: a
row whose ``date`` is not a session cannot describe a tape, so it was stamped from
the clock by a nightly that runs seven nights a week against an end-of-day board.

Two policies, because the two row shapes are not the same kind of claim:
  * snapshots.jsonl — a re-description of a BOARD. Restamped onto the session it
    describes ONLY when that session was never built (the weekend run is the sole
    record of its tape); a session the engine actually built owns its roster and
    never gains a row. Quarantine therefore splits into two honest classes:
    DUPLICATE (the slot is taken — carries a kept-row pointer) and ROSTER (the
    session was built but never carried this key — carries no pointer, because
    none exists).
  * turns.jsonl / universe_nominations.jsonl — state-machine OUTPUT evolved on fake
    sessions. Always quarantined; restamping would mint events no real build made.

Covers:
  (1) pure-dupe weekend quarantine — reason, kept-row pointer, meta block, nothing lost
  (2) first-record Saturday restamp + its Sunday duplicate quarantined
  (3) genesis-Sunday restamp (nothing precedes it in the ledger)
  (4) turns/noms quarantine-all, including a novel weekend-only claim
  (5) meta contents including the DERIVED known_gaps
  (6) idempotent re-run — byte-identical files, no meta churn
  (7) --dry-run writes nothing
  (8) quarantine append-preservation across runs
  (9) fail-closed — missing ledger, unreadable date, torn JSON line
 (10) the restamp boundary — a BUILT session owns its roster; both branches in one run

Every fixture date is a pinned weekday; nothing here reads the wall clock.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scripts import heal_subsector_rotation_ledgers as HEAL

# ── pinned fixture dates (2026) ───────────────────────────────────────────────
_FRI = "2026-07-10"      # Friday — a session
_SAT = "2026-07-11"      # Saturday — resolves to _FRI
_SUN = "2026-07-12"      # Sunday   — resolves to _FRI
_MON = "2026-07-13"      # Monday   — a session
_TUE = "2026-07-14"
_WED = "2026-07-15"
_THU = "2026-07-16"      # Thursday — a session
_FRI2 = "2026-07-17"     # Friday   — a session
_SAT2 = "2026-07-18"     # Saturday — resolves to _FRI2


# ── fixture helpers ───────────────────────────────────────────────────────────

def _snap_row(date_str: str, key: str, score: float = 1.5) -> dict:
    return {"date": date_str, "key": key, "name": key.upper(), "theme": "T",
            "score": score, "rs_mom": 0.5, "accel": 1.0, "quadrant": "leading",
            "stage": "neutral", "lean": 0, "members": ["AAA", "BBB", "CCC"]}


def _turn_row(date_str: str, key: str, state: str = "turn_up") -> dict:
    return {"date": date_str, "key": key, "name": key.upper(), "theme": "T",
            "state": state, "since": date_str, "score": 0.7, "n_members": 5,
            "breadth": 0.6, "dd_from_peak": -0.03, "up_from_trough": 0.08}


def _nom_row(date_str: str, donor: str, receiver: str) -> dict:
    return {"date": date_str, "theme": "T", "donor": donor, "receiver": receiver,
            "confidence": 0.5, "both_confirmed": True}


def _write_all(root: Path, snapshots=(), turns=(), noms=()) -> Path:
    """Write all three ledgers (the heal fails closed unless every file exists)."""
    d = root / "data" / "subsector_rotation"
    d.mkdir(parents=True, exist_ok=True)
    for name, rows in (("snapshots.jsonl", snapshots), ("turns.jsonl", turns),
                       ("universe_nominations.jsonl", noms)):
        (d / name).write_text("".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8")
    return d


def _read_jsonl(p: Path) -> list[dict]:
    return [json.loads(x) for x in p.read_text(encoding="utf-8").splitlines() if x.strip()]


def _default_turns_noms() -> tuple[list, list]:
    """One honest row each — enough to satisfy the every-file-exists precondition."""
    return [_turn_row(_FRI, "k1")], [_nom_row(_FRI, "d1", "r1")]


# ── (1) pure-dupe weekend quarantine ──────────────────────────────────────────

def test_pure_duplicate_weekend_row_is_quarantined(tmp_path):
    """A Saturday re-description of a Friday already on file is a duplicate."""
    t, n = _default_turns_noms()
    d = _write_all(tmp_path, snapshots=[_snap_row(_FRI, "a"), _snap_row(_SAT, "a", 9.9)],
                   turns=t, noms=n)

    summary = HEAL.heal(tmp_path)
    snap = summary["files"]["snapshots.jsonl"]

    assert snap["n_quarantined_now"] == 1
    assert snap["n_restamped"] == 0
    assert snap["n_survivors"] == 1
    # never-delete law: every input row is still on disk somewhere
    assert snap["n_survivors"] + snap["n_quarantined_now"] == snap["n_rows_in"]

    survivors = _read_jsonl(d / "snapshots.jsonl")
    assert len(survivors) == 1
    assert survivors[0]["date"] == _FRI and survivors[0]["score"] == 1.5, "honest row kept"
    assert "session_inferred" not in survivors[0]

    quar = _read_jsonl(d / "snapshots_quarantine.jsonl")
    assert len(quar) == 1
    assert quar[0]["date"] == _SAT, "the quarantined row keeps its original stamp"
    assert "duplicate weekend re-description" in quar[0]["quarantine_reason"]
    assert quar[0]["quarantined_kept_row"] == {"date": _FRI, "key": "a"}
    assert quar[0]["quarantined_at"]


# ── (2) first-record Saturday restamp, Sunday duplicate quarantined ───────────

def test_saturday_recovery_restamped_and_its_sunday_dupe_quarantined(tmp_path):
    """Friday's fetch failed; Saturday's rows are the only record of that board.

    They are restamped onto Friday — normalization, not refusal — and the Sunday
    re-fetch of the SAME board then collides with them and is quarantined.
    """
    t, n = _default_turns_noms()
    d = _write_all(tmp_path, snapshots=[_snap_row(_SAT, "a"), _snap_row(_SUN, "a", 9.9)],
                   turns=t, noms=n)

    summary = HEAL.heal(tmp_path)
    snap = summary["files"]["snapshots.jsonl"]

    assert snap["n_restamped"] == 1
    assert snap["n_quarantined_now"] == 1
    assert snap["n_survivors"] == 1

    survivors = _read_jsonl(d / "snapshots.jsonl")
    assert len(survivors) == 1
    assert survivors[0]["date"] == _FRI
    assert survivors[0]["session_inferred"] is True
    assert survivors[0]["score"] == 1.5, "the Saturday row is the one that survived"

    quar = _read_jsonl(d / "snapshots_quarantine.jsonl")
    assert [q["date"] for q in quar] == [_SUN]
    assert quar[0]["quarantined_kept_row"] == {"date": _FRI, "key": "a"}


# ── (3) genesis Sunday ────────────────────────────────────────────────────────

def test_genesis_sunday_row_is_restamped_not_dropped(tmp_path):
    """The ledger's very first row being a Sunday must not cost us that board."""
    t, n = _default_turns_noms()
    d = _write_all(tmp_path, snapshots=[_snap_row(_SUN, "a")], turns=t, noms=n)

    summary = HEAL.heal(tmp_path)
    snap = summary["files"]["snapshots.jsonl"]

    assert snap["n_restamped"] == 1 and snap["n_quarantined_now"] == 0
    rows = _read_jsonl(d / "snapshots.jsonl")
    assert [r["date"] for r in rows] == [_FRI]
    assert rows[0]["session_inferred"] is True
    assert not (d / "snapshots_quarantine.jsonl").exists()


# ── (4) turns / noms: quarantine ALL, including novel weekend-only claims ─────

def test_turns_quarantine_all_never_restamp_including_novel_claim(tmp_path):
    """Turn rows are state-machine output; a weekend row may carry a claim Friday
    never made, so restamping would MINT an event. Both shapes are quarantined."""
    d = _write_all(
        tmp_path,
        snapshots=[_snap_row(_FRI, "a")],
        turns=[_turn_row(_FRI, "k1", "turn_up"),          # honest
               _turn_row(_SAT, "k1", "turn_up"),          # dupe of the honest row
               _turn_row(_SAT, "novelkey", "turn_down")], # exists ONLY on the fake day
        noms=[_nom_row(_FRI, "d1", "r1"),
              _nom_row(_SAT, "d1", "r1"),
              _nom_row(_SAT, "dnew", "rnew")],
    )

    summary = HEAL.heal(tmp_path)

    for fname, novel_field, want_novel in (
            ("turns.jsonl", "key", {"k1": False, "novelkey": True}),
            ("universe_nominations.jsonl", "donor", {"d1": False, "dnew": True})):
        f = summary["files"][fname]
        assert f["n_restamped"] == 0, f"{fname} must never restamp"
        assert f["n_quarantined_now"] == 2
        assert f["n_survivors"] == 1

        survivors = _read_jsonl(d / fname)
        assert [r["date"] for r in survivors] == [_FRI]

        quar = _read_jsonl(d / fname.replace(".jsonl", "_quarantine.jsonl"))
        assert {q["date"] for q in quar} == {_SAT}
        assert all("mint" in q["quarantine_reason"] for q in quar)
        assert all(q["quarantined_true_session"] == _FRI for q in quar)
        assert all("quarantined_kept_row" not in q for q in quar), \
            "a quarantine-all row is not necessarily a duplicate of anything"
        assert {q[novel_field]: q["quarantined_novel_claim"] for q in quar} == want_novel


# ── (5) meta: per-file quarantine blocks + DERIVED known_gaps ─────────────────

def test_meta_blocks_and_derived_known_gaps(tmp_path):
    """known_gaps is derived from the healed span, never hardcoded."""
    t, n = _default_turns_noms()
    d = _write_all(
        tmp_path,
        # after the heal the span is _FRI.._THU; _MON/_TUE/_WED carry no rows
        snapshots=[_snap_row(_SAT, "a"), _snap_row(_SUN, "a"), _snap_row(_THU, "a")],
        turns=t, noms=n,
    )

    summary = HEAL.heal(tmp_path)

    assert summary["known_gaps"] == [_MON, _TUE, _WED]
    meta = json.loads((d / "ledgers_meta.json").read_text())
    block = meta["quarantine"]["snapshots.jsonl"]
    assert block["file"] == "snapshots_quarantine.jsonl"
    assert block["n_rows"] == 1
    assert block["healed_by"] == "scripts/heal_subsector_rotation_ledgers.py"
    assert block["last_heal"]
    assert "duplicate weekend re-description" in block["reason"]
    # turns/noms had nothing to quarantine here, so they get no block
    assert "turns.jsonl" not in meta["quarantine"]

    gaps = {g["session"]: g["reason"] for g in meta["known_gaps"]}
    assert set(gaps) == {_MON, _TUE, _WED}
    assert "unknowable from this ledger" in gaps[_MON]
    # the weekend dates themselves are NOT gaps — they are not sessions at all
    assert _SAT not in gaps and _SUN not in gaps


def test_known_gaps_merge_does_not_clobber_prior_entries(tmp_path):
    t, n = _default_turns_noms()
    d = _write_all(tmp_path, snapshots=[_snap_row(_SAT, "a"), _snap_row(_THU, "a")],
                   turns=t, noms=n)
    (d / "ledgers_meta.json").write_text(json.dumps({
        "known_gaps": [{"session": "2026-06-01", "reason": "an earlier audit"}],
        "unrelated_key": "must survive",
    }), encoding="utf-8")

    HEAL.heal(tmp_path)

    meta = json.loads((d / "ledgers_meta.json").read_text())
    assert meta["unrelated_key"] == "must survive"
    sessions = [g["session"] for g in meta["known_gaps"]]
    assert sessions == sorted(sessions), "gap entries stay sorted by session"
    assert "2026-06-01" in sessions and _MON in sessions


# ── (6) idempotency ───────────────────────────────────────────────────────────

def test_second_run_is_a_no_op(tmp_path):
    """A healed tree changes nothing on a re-run — byte-identical, meta untouched."""
    d = _write_all(
        tmp_path,
        snapshots=[_snap_row(_FRI, "a"), _snap_row(_SAT, "a"), _snap_row(_SUN, "a")],
        turns=[_turn_row(_FRI, "k1"), _turn_row(_SAT, "k1")],
        noms=[_nom_row(_FRI, "d1", "r1"), _nom_row(_SAT, "d1", "r1")],
    )

    HEAL.heal(tmp_path)
    before = {p.name: p.read_bytes() for p in sorted(d.iterdir())}

    summary2 = HEAL.heal(tmp_path)

    assert summary2["note"] == "already healed — nothing to do"
    assert all(f["n_restamped"] == 0 and f["n_quarantined_now"] == 0
               for f in summary2["files"].values())
    after = {p.name: p.read_bytes() for p in sorted(d.iterdir())}
    assert after == before, "a no-op run must not rewrite a single byte"


def test_untouched_rows_keep_their_exact_original_bytes(tmp_path):
    """Only restamped rows are re-serialised — the git diff stays minimal."""
    t, n = _default_turns_noms()
    d = _write_all(tmp_path, snapshots=[_snap_row(_FRI, "a"), _snap_row(_SAT, "a")],
                   turns=t, noms=n)
    original_first_line = (d / "snapshots.jsonl").read_text().splitlines()[0]

    HEAL.heal(tmp_path)

    assert (d / "snapshots.jsonl").read_text().splitlines()[0] == original_first_line


# ── (7) --dry-run ─────────────────────────────────────────────────────────────

def test_dry_run_writes_nothing(tmp_path):
    t, n = _default_turns_noms()
    d = _write_all(tmp_path, snapshots=[_snap_row(_FRI, "a"), _snap_row(_SAT, "a")],
                   turns=t, noms=n)
    before = {p.name: p.read_bytes() for p in sorted(d.iterdir())}

    summary = HEAL.heal(tmp_path, dry_run=True)

    assert summary["dry_run"] is True
    assert summary["files"]["snapshots.jsonl"]["n_quarantined_now"] == 1
    assert {p.name: p.read_bytes() for p in sorted(d.iterdir())} == before
    assert not (d / "snapshots_quarantine.jsonl").exists()
    assert not (d / "ledgers_meta.json").exists()


# ── (8) quarantine append-preservation ────────────────────────────────────────

def test_quarantine_file_appends_and_never_drops_prior_rows(tmp_path):
    """A pre-existing quarantine row from an earlier heal survives the next one."""
    t, n = _default_turns_noms()
    d = _write_all(tmp_path, snapshots=[_snap_row(_FRI, "a"), _snap_row(_SAT, "a")],
                   turns=t, noms=n)
    prior = {"date": "2026-06-27", "key": "older", "quarantine_reason": "an earlier heal"}
    (d / "snapshots_quarantine.jsonl").write_text(json.dumps(prior) + "\n", encoding="utf-8")

    HEAL.heal(tmp_path)

    quar = _read_jsonl(d / "snapshots_quarantine.jsonl")
    assert [(q["date"], q["key"]) for q in quar] == [("2026-06-27", "older"), (_SAT, "a")]
    assert json.loads((d / "ledgers_meta.json").read_text())[
        "quarantine"]["snapshots.jsonl"]["n_rows"] == 2

    # a NEW mislabeled row on a later run appends without re-adding the old ones
    (d / "snapshots.jsonl").write_text(
        (d / "snapshots.jsonl").read_text() + json.dumps(_snap_row(_FRI2, "a")) + "\n"
        + json.dumps(_snap_row(_SAT2, "a")) + "\n", encoding="utf-8")
    HEAL.heal(tmp_path)

    quar2 = _read_jsonl(d / "snapshots_quarantine.jsonl")
    assert [(q["date"], q["key"]) for q in quar2] == [
        ("2026-06-27", "older"), (_SAT, "a"), (_SAT2, "a")]


# ── (9) fail-closed ───────────────────────────────────────────────────────────

def test_missing_ledger_reports_error_and_writes_nothing(tmp_path):
    d = tmp_path / "data" / "subsector_rotation"
    d.mkdir(parents=True)
    (d / "snapshots.jsonl").write_text(json.dumps(_snap_row(_SAT, "a")) + "\n")
    before = (d / "snapshots.jsonl").read_bytes()

    summary = HEAL.heal(tmp_path)

    assert "error" in summary and "turns.jsonl" in summary["error"]
    assert (d / "snapshots.jsonl").read_bytes() == before, \
        "one missing ledger must not leave another half-healed"
    assert HEAL.main(["--root", str(tmp_path)]) == 1


def test_unreadable_date_aborts_every_write(tmp_path):
    t, n = _default_turns_noms()
    bad = _snap_row(_SAT, "a")
    bad["date"] = "not-a-date"
    d = _write_all(tmp_path, snapshots=[_snap_row(_FRI, "a"), bad], turns=t, noms=n)
    before = {p.name: p.read_bytes() for p in sorted(d.iterdir())}

    with pytest.raises(SystemExit) as exc:
        HEAL.heal(tmp_path)

    assert "FAIL-CLOSED" in str(exc.value)
    assert {p.name: p.read_bytes() for p in sorted(d.iterdir())} == before
    assert not (d / "snapshots_quarantine.jsonl").exists()


def test_torn_json_line_aborts_every_write(tmp_path):
    t, n = _default_turns_noms()
    d = _write_all(tmp_path, snapshots=[_snap_row(_FRI, "a")], turns=t, noms=n)
    with (d / "snapshots.jsonl").open("a", encoding="utf-8") as fh:
        fh.write('{"date": "2026-07-11", "key": "tor\n')
    before = {p.name: p.read_bytes() for p in sorted(d.iterdir())}

    with pytest.raises(SystemExit) as exc:
        HEAL.heal(tmp_path)

    assert "FAIL-CLOSED" in str(exc.value)
    assert {p.name: p.read_bytes() for p in sorted(d.iterdir())} == before


def test_a_ledger_of_only_session_rows_is_left_alone(tmp_path):
    """Clean pass: nothing is touched when every row is already session-dated."""
    d = _write_all(tmp_path,
                   snapshots=[_snap_row(_FRI, "a"), _snap_row(_MON, "a")],
                   turns=[_turn_row(_FRI, "k1")], noms=[_nom_row(_FRI, "d1", "r1")])
    before = {p.name: p.read_bytes() for p in sorted(d.iterdir())}

    summary = HEAL.heal(tmp_path)

    assert summary["note"] == "already healed — nothing to do"
    assert {p.name: p.read_bytes() for p in sorted(d.iterdir())} == before


# ── (10) the restamp boundary: a BUILT session owns its roster ───────────────

def test_key_absent_from_a_built_sessions_roster_is_quarantined_not_restamped(tmp_path):
    """A session the engine actually BUILT may never gain a row from a weekend re-run.

    This is the boundary the committed data exercises: on Sunday 2026-07-12 the build
    had just gained the synthetic ``megacapgenerals`` node, so that one key has no
    2026-07-10 row while the other 268 do. Backdating it would insert a call the real
    Friday build provably did not make — the feature shipped after that build, and a
    coverage cliff dates the FEATURE, not the data. It is quarantined under its OWN
    reason class, with no kept-row pointer (none exists to point at).
    """
    t, n = _default_turns_noms()
    d = _write_all(tmp_path,
                   snapshots=[_snap_row(_FRI, "a"),         # 2026-07-10 was BUILT
                              _snap_row(_SUN, "a"),         # plain duplicate
                              _snap_row(_SUN, "newnode")],  # key absent from the roster
                   turns=t, noms=n)

    summary = HEAL.heal(tmp_path)
    snap = summary["files"]["snapshots.jsonl"]

    assert snap["n_restamped"] == 0, "a built session's roster is never added to"
    assert snap["n_quarantined_now"] == 2
    assert snap["n_survivors"] == 1
    assert snap["quarantined_by_class"] == {"duplicate": 1, "roster": 1}

    rows = _read_jsonl(d / "snapshots.jsonl")
    assert [(r["date"], r["key"]) for r in rows] == [(_FRI, "a")]
    assert all("session_inferred" not in r for r in rows)

    quar = {q["key"]: q for q in _read_jsonl(d / "snapshots_quarantine.jsonl")}
    assert set(quar) == {"a", "newnode"}

    # the ROSTER class — an honest shape: no pointer to a row that does not exist
    roster = quar["newnode"]
    assert "first observation of a key absent from the built true-session's roster" \
        in roster["quarantine_reason"]
    assert roster["quarantined_true_session"] == _FRI
    assert roster["roster_built_without_key"] is True
    assert "quarantined_kept_row" not in roster, \
        "no kept row exists for (2026-07-10, newnode) — claiming one would be a lie"

    # the DUPLICATE class keeps its resolvable pointer, and the two reasons differ
    dupe = quar["a"]
    assert dupe["quarantined_kept_row"] == {"date": _FRI, "key": "a"}
    assert "roster_built_without_key" not in dupe
    assert dupe["quarantine_reason"] != roster["quarantine_reason"]


def test_recovery_restamp_survives_only_when_the_session_was_never_built(tmp_path):
    """The two branches side by side in one run, so the predicate cannot silently widen.

    _FRI was built (roster closed → its weekend rows quarantine); _FRI2 was never built
    (no roster → its Saturday rows are the sole record and restamp).
    """
    t, n = _default_turns_noms()
    d = _write_all(tmp_path,
                   snapshots=[_snap_row(_FRI, "a"),        # built session
                              _snap_row(_SUN, "brandnew"), # roster-class quarantine
                              _snap_row(_SAT2, "a"),       # 2026-07-17 never built
                              _snap_row(_SAT2, "brandnew")],
                   turns=t, noms=n)

    summary = HEAL.heal(tmp_path)
    snap = summary["files"]["snapshots.jsonl"]

    assert snap["n_restamped"] == 2, "both _SAT2 rows recover onto the unbuilt _FRI2"
    assert snap["n_quarantined_now"] == 1
    assert snap["quarantined_by_class"] == {"roster": 1}

    rows = sorted((r["date"], r["key"]) for r in _read_jsonl(d / "snapshots.jsonl"))
    assert rows == [(_FRI, "a"), (_FRI2, "a"), (_FRI2, "brandnew")]
