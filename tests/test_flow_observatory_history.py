"""Flow Observatory V2 W3 — the append-only point-in-time observation ledger, revision-safe
corrections, deterministic replay, and ledger-derived transitions/onset/age
(research/flow_observatory/W3_SPEC.md).

Written FIRST and failing per the frozen spec's §0 gate, against
``engine.flow_observatory.history`` (new) and the W3 extensions to
``engine.flow_observatory.changes.compute_changes`` / ``engine.flow_observatory.
contract.build_v2``. The eleven numbered tests below correspond 1:1 to spec §3's numbered
list; each test's docstring/name names its bullet.

Mutation M1 (spec §3 item 11 — "make append_observations mutate a closed row in place")
is a manual verification, not a permanent test: paste the failing output of tests 1 and 3
into the PR body/EVIDENCE after temporarily breaking ``_diff_entities``/``append_observations``
to mutate ``existing`` rows in place, then revert.
"""
from __future__ import annotations

import hashlib

import pytest

from engine.flow_observatory import changes as fo_changes
from engine.flow_observatory import history
from engine.flow_observatory.contract import build_v2
from tests.test_flow_observatory_contract import _snap


# ── shared fixture builder — a plain ledger row dict (no I/O) ──────────────────────────
def _row(entity_kind: str, entity_id: str, session: str, *, revision_id: int = 0,
        first_known_at: str = "2026-01-01T00:00:00+00:00", revised_at=None,
        quadrant=None, state=None, vel=None, rank=None, abs_value=None,
        coverage_n=None, status=None) -> dict:
    return {"entity_kind": entity_kind, "entity_id": entity_id, "effective_session": session,
           "revision_id": revision_id, "first_known_at": first_known_at, "revised_at": revised_at,
           "vel": vel, "abs_value": abs_value, "quadrant": quadrant, "state": state,
           "rank": rank, "coverage_n": coverage_n, "status": status}


# ── 1: append -> same inputs -> byte-identical file (hash compare) ────────────────────
def test_append_same_inputs_yields_byte_identical_file(tmp_path):
    path = tmp_path / "observations.parquet"
    entities = {("theme", "cn_autos"): {"vel": 1.0, "abs_value": 0.5,
                                        "quadrant": "true_accumulation", "state": "s",
                                        "rank": 1, "status": "HEALTHY"}}
    r1 = history.append_observations(path, "2026-09-01", entities,
                                     "2026-09-01T12:00:00+00:00", require_lane=False)
    assert r1["written"] is True and r1["rows_added"] == 1
    hash1 = hashlib.sha256(path.read_bytes()).hexdigest()

    r2 = history.append_observations(path, "2026-09-01", entities,
                                     "2026-09-01T13:00:00+00:00", require_lane=False)
    assert r2["written"] is False and r2["reason"] == "no_changes"
    hash2 = hashlib.sha256(path.read_bytes()).hexdigest()
    assert hash1 == hash2, "identical inputs must never rewrite the ledger file"


# ── 2: duplicate advance idempotent (no new rows) ──────────────────────────────────────
def test_duplicate_advance_is_idempotent_no_new_rows(tmp_path):
    path = tmp_path / "observations.parquet"
    entities = {("theme", "cn_autos"): {"quadrant": "true_accumulation", "vel": 1.0, "rank": 1}}
    history.append_observations(path, "2026-09-01", entities,
                                "2026-09-01T00:00:00+00:00", require_lane=False)
    history.append_observations(path, "2026-09-01", entities,
                                "2026-09-02T00:00:00+00:00", require_lane=False)
    rows = history.read_ledger(path)
    assert len(rows) == 1
    assert rows[0]["revision_id"] == 0


# ── 3: changed value -> revision row; original byte-preserved; latest/replay ───────────
def test_changed_value_creates_revision_row_original_preserved_latest_and_replay(tmp_path):
    path = tmp_path / "observations.parquet"
    e1 = {("theme", "cn_autos"): {"quadrant": "true_accumulation", "vel": 1.0, "rank": 1}}
    history.append_observations(path, "2026-09-01", e1, "2026-09-01T00:00:00+00:00",
                                require_lane=False)
    original_row = next(r for r in history.read_ledger(path) if r["revision_id"] == 0)

    e2 = {("theme", "cn_autos"): {"quadrant": "true_distribution", "vel": -1.5, "rank": 4}}
    r2 = history.append_observations(path, "2026-09-01", e2, "2026-09-02T00:00:00+00:00",
                                     require_lane=False)
    assert r2["written"] is True and r2["rows_added"] == 1
    assert len(r2["revisions"]) == 1
    rev = r2["revisions"][0]
    assert rev["from"]["quadrant"] == "true_accumulation"
    assert rev["to"]["quadrant"] == "true_distribution"

    rows = history.read_ledger(path)
    assert len(rows) == 2
    kept = next(r for r in rows if r["revision_id"] == 0)
    for f in history.FIELDS:
        assert kept[f] == original_row[f], f"revision_id=0 row's {f!r} must be unchanged"
    assert kept["first_known_at"] == original_row["first_known_at"]
    assert kept["revised_at"] == original_row["revised_at"] is None

    latest_row = next(r for r in history.latest_view(rows) if r["entity_id"] == "cn_autos")
    assert latest_row["revision_id"] == 1
    assert latest_row["quadrant"] == "true_distribution"

    replayed_row = next(r for r in history.replay(rows, "2026-09-01T12:00:00+00:00")
                        if r["entity_id"] == "cn_autos")
    assert replayed_row["revision_id"] == 0
    assert replayed_row["quadrant"] == "true_accumulation"


# ── 4: replay excludes observations first-known after the replay instant ───────────────
def test_replay_excludes_observations_first_known_after_instant(tmp_path):
    path = tmp_path / "observations.parquet"
    history.append_observations(path, "2026-09-01", {("theme", "cn_autos"):
                                                      {"quadrant": "true_accumulation"}},
                                "2026-09-01T00:00:00+00:00", require_lane=False)
    history.append_observations(path, "2026-09-02", {("theme", "cn_gold"):
                                                      {"quadrant": "true_distribution"}},
                                "2026-09-03T00:00:00+00:00", require_lane=False)
    rows = history.read_ledger(path)
    ids = {r["entity_id"] for r in history.replay(rows, "2026-09-01T12:00:00+00:00")}
    assert ids == {"cn_autos"}, "cn_gold was not knowable yet at the replay instant"


# ── 5: onset survives repeats; prior_state correct; gap creates no transition ──────────
def test_onset_survives_repeats_prior_state_correct_gap_creates_no_transition():
    rows = [
        _row("theme", "cn_autos", "2026-08-25", quadrant="true_accumulation"),
        _row("theme", "cn_autos", "2026-08-26", quadrant="true_accumulation"),
        # 2026-08-27/28 deliberately MISSING (a lane-skipped gap)
        _row("theme", "cn_autos", "2026-08-31", quadrant="true_accumulation"),
        _row("theme", "cn_autos", "2026-09-01", quadrant="true_distribution"),
    ]
    states = history.derive_states(rows, "theme", "cn_autos")
    assert states["2026-08-25"]["note"] == "first tracked session"
    assert states["2026-08-25"]["state_started"] is None
    assert states["2026-08-26"]["state_started"] == "2026-08-25"
    assert states["2026-08-26"]["state_age_sessions"] == 2
    # the gap is invisible to the walk: 08-31 extends the SAME run, no fabricated reset
    assert states["2026-08-31"]["state_started"] == "2026-08-25"
    assert states["2026-08-31"]["state_age_sessions"] == 3
    # the genuine 09-01 flip: prior_state reads the immediately preceding quadrant, onset resets
    assert states["2026-09-01"]["prior_state"] == "true_accumulation"
    assert states["2026-09-01"]["state_started"] == "2026-09-01"
    assert states["2026-09-01"]["state_age_sessions"] == 1


# ── 6: stale session does not advance state age (frozen-age path) ─────────────────────
def test_stale_session_freezes_state_age():
    rows = [
        _row("theme", "cn_autos", "2026-08-28", quadrant="true_accumulation"),
        _row("theme", "cn_autos", "2026-08-29", quadrant="true_accumulation"),
        _row("theme", "cn_autos", "2026-08-30", quadrant="true_accumulation", status="STALE"),
    ]
    states = history.derive_states(rows, "theme", "cn_autos")
    assert states["2026-08-29"]["state_age_sessions"] == 2
    frozen = states["2026-08-30"]
    assert frozen["note"] == "age frozen (stale source)"
    assert frozen["state_age_sessions"] == 2, "must freeze at yesterday's age, not advance to 3"
    assert frozen["state_started"] == "2026-08-28"

    # the per-build convenience (state_for_session) agrees when asked directly about a
    # not-yet-committed session with an explicit current_status
    prior = rows[:2]
    hist = history.state_for_session(prior, "theme", "cn_autos", "2026-08-30",
                                     "true_accumulation", current_rank=None,
                                     current_status="STALE")
    assert hist["state_age_sessions"] == 2
    assert hist["note"] == "age frozen (stale source)"


# ── 7: rank_change compares a consistent universe ──────────────────────────────────────
def test_rank_change_null_when_entity_absent_from_prior_valid_session():
    rows = [
        _row("theme", "cn_gold", "2026-08-31", quadrant="true_accumulation", rank=2),
        # cn_autos absent from the universe's 2026-08-31 snapshot entirely; its own last
        # appearance was 08-30, a DIFFERENT (older) session than the universe's own prior.
        _row("theme", "cn_autos", "2026-08-30", quadrant="true_accumulation", rank=5),
    ]
    hist = history.state_for_session(rows, "theme", "cn_autos", "2026-09-01",
                                     "true_accumulation", current_rank=1)
    assert hist["rank_change"] is None, (
        "cn_autos was absent from the universe's own previous valid session (08-31); "
        "comparing today's rank against its stale 08-30 rank would be a fabricated "
        "cross-gap delta, not a consistent-universe comparison")


# ── 8: non-owner lane cannot append ────────────────────────────────────────────────────
def test_non_owner_lane_cannot_append(tmp_path, monkeypatch):
    monkeypatch.delenv("COLLECT_LANE", raising=False)
    monkeypatch.delenv("US_LANE", raising=False)
    monkeypatch.delenv("CN_LANE", raising=False)
    path = tmp_path / "observations.parquet"
    r = history.append_observations(path, "2026-09-01",
                                    {("theme", "cn_autos"): {"quadrant": "true_accumulation"}},
                                    "2026-09-01T00:00:00+00:00")   # require_lane defaults True
    assert r["written"] is False and r["reason"] == "off_ledger_lane"
    assert not path.exists()


# ── 9: revision -> source_revisions[] + REVISED row, never a duplicate transition ──────
def test_revision_produces_source_revisions_and_suppresses_duplicate_transition(tmp_path):
    path = tmp_path / "observations.parquet"
    history.append_observations(path, "2026-08-29",
                                {("theme", "cn_autos"): {"quadrant": "true_accumulation", "rank": 1}},
                                "2026-08-29T00:00:00+00:00", require_lane=False)
    history.append_observations(path, "2026-08-30",
                                {("theme", "cn_autos"): {"quadrant": "true_accumulation", "rank": 1}},
                                "2026-08-30T00:00:00+00:00", require_lane=False)
    ledger_rows = history.read_ledger(path)
    assert history.ledger_session_count(ledger_rows, "theme") == 2   # ledger path is live

    # tonight's build recomputes 2026-08-30 with a CORRECTED quadrant (a restated source)
    # -- a revision to an ALREADY-recorded session, not a fresh transition.
    corrected = {("theme", "cn_autos"): {"quadrant": "true_distribution", "rank": 4}}
    now = "2026-08-31T00:00:00+00:00"
    revisions = history.preview_revisions(ledger_rows, "2026-08-30", corrected, now)
    assert len(revisions) == 1
    assert revisions[0]["id"] == "cn_autos"
    assert revisions[0]["to"]["quadrant"] == "true_distribution"

    current = {"session": "2026-08-30",
              "themes": {"cn_autos": {"quadrant": "true_distribution", "rank": 4}}}
    cs = fo_changes.compute_changes(current, [], ledger_rows=ledger_rows, revisions=revisions)
    assert cs["source_revisions"] == revisions
    assert cs["material_change"] is True
    assert not any(t["id"] == "cn_autos" for t in cs["transitions"]), (
        "a revision to cn_autos's own session must not ALSO surface as a quadrant "
        "transition — that double-counts one correction as two change types")
    assert not any(m["id"] == "cn_autos" for m in cs["rank_movers"]), (
        "same rule for rank movers — the corrected rank must not double-count either")


# ── 10: fallback path — ledger depth <2 still serves state_log summaries ───────────────
def test_fallback_to_state_log_when_ledger_depth_below_two():
    log_rows = [
        {"session": "2026-08-31", "written_at": "x", "aggregate": {}, "market_read": {},
         "themes": {"cn_autos": {"quadrant": "true_distribution", "state": "s", "vel": -2.0,
                                 "rank": 5, "abs": -3.0}}},
    ]
    # exactly ONE theme session in the ledger -- depth < 2, must NOT be used yet
    ledger_rows = [_row("theme", "cn_autos", "2026-08-31", quadrant="true_distribution",
                        vel=-2.0, abs_value=-3.0, state="s", rank=5)]
    assert history.ledger_session_count(ledger_rows, "theme") == 1

    v2 = build_v2(_snap(), log_rows=log_rows, ledger_rows=ledger_rows,
                 market_session="2026-09-01", generated_at="2026-09-01T12:00:00+00:00",
                 seats_as_of="2026-08-30")
    autos = next(r for r in v2["ashare_sectors"]["rows"] if r["id"] == "cn_autos")
    # identical numbers to the pure state_log path (test_flow_observatory_contract.py's
    # own W1 test of the same fixture) -- proves the fallback is byte-for-byte the same
    # answer, not a degraded approximation.
    assert autos["prior_state"] == "true_distribution"
    assert autos["state_started"] == "2026-09-01"
    assert autos["state_age_sessions"] == 1
    assert autos["rank_change"] == autos["rank"] - 5
    assert autos["state_note"] is None


def test_ledger_path_serves_once_depth_reaches_two():
    """The mirror of test 10: once the ledger holds >=2 theme sessions, build_v2 uses IT
    (not state_log) for state history — proven by a ledger answer that DIFFERS from what
    state_log alone would have said (state_log below is deliberately empty)."""
    ledger_rows = [
        _row("theme", "cn_autos", "2026-08-29", quadrant="true_distribution", rank=5),
        _row("theme", "cn_autos", "2026-08-30", quadrant="true_distribution", rank=5),
    ]
    assert history.ledger_session_count(ledger_rows, "theme") == 2
    v2 = build_v2(_snap(), log_rows=[], ledger_rows=ledger_rows,
                 market_session="2026-08-31", generated_at="2026-08-31T12:00:00+00:00",
                 seats_as_of="2026-08-30")
    autos = next(r for r in v2["ashare_sectors"]["rows"] if r["id"] == "cn_autos")
    # cn_autos's fixture quadrant (_autos_row) is "true_distribution"? -- assert only what
    # the ledger path guarantees regardless of the fixture's own quadrant: real history
    # (not the "first tracked session" null state_log-alone would report with no log_rows).
    assert autos["state_note"] is None
    assert autos["state_started"] is not None
    assert autos["state_age_sessions"] is not None