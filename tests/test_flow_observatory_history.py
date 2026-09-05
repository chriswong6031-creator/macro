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


# ── S7: narrowed suppression — an UNRELATED revision must not black out a real flip ─────
def test_corrected_session_and_a_real_flip_both_emit(tmp_path):
    """A revision to an OLDER already-recorded session must not swallow a genuinely NEW,
    unrelated transition the SAME entity has TONIGHT — the old entity-id-only suppression
    blacked this out; S7 narrows the match to (entity, from_quadrant, to_quadrant)."""
    path = tmp_path / "observations.parquet"
    history.append_observations(path, "2026-08-29",
                                {("theme", "cn_autos"): {"quadrant": "true_accumulation", "rank": 1}},
                                "2026-08-29T00:00:00+00:00", require_lane=False)
    history.append_observations(path, "2026-08-30",
                                {("theme", "cn_autos"): {"quadrant": "true_accumulation", "rank": 1}},
                                "2026-08-30T00:00:00+00:00", require_lane=False)
    ledger_rows = history.read_ledger(path)
    assert history.ledger_session_count(ledger_rows, "theme") == 2

    # tonight's build corrects 2026-08-30's PAST belief acc -> dist (unrelated to today).
    corrected = {("theme", "cn_autos"): {"quadrant": "true_distribution", "rank": 4}}
    now = "2026-08-31T00:00:00+00:00"
    revisions = history.preview_revisions(ledger_rows, "2026-08-30", corrected, now)
    assert len(revisions) == 1 and revisions[0]["to"]["quadrant"] == "true_distribution"

    # tonight's ACTUAL new session (08-31) reports a DIFFERENT flip: acc -> improving —
    # a real transition the revision's own (acc, dist) does not restate.
    current = {"session": "2026-08-31",
              "themes": {"cn_autos": {"quadrant": "improving_but_still_selling", "rank": 2}}}
    cs = fo_changes.compute_changes(current, [], ledger_rows=ledger_rows, revisions=revisions)
    assert cs["source_revisions"] == revisions, "the correction must still be reported"
    flip = next((t for t in cs["transitions"] if t["id"] == "cn_autos"), None)
    assert flip is not None, (
        "an unrelated revision must never black out cn_autos's genuine NEW transition — "
        f"both rows must emit; got transitions={cs['transitions']}")
    assert flip == {"id": "cn_autos", "from_quadrant": "true_accumulation",
                    "to_quadrant": "improving_but_still_selling"}


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


# ═══════════════════════════════════════════════════════════════════════════════════════
# W3 REPAIR ROUND (research/flow_observatory/W3_SPEC.md repair packet) — B1/B2/B3/S4/S5/
# M9/M10 failing-first tests, each named for its own repair item.
# ═══════════════════════════════════════════════════════════════════════════════════════

# ── B1: atomic durability — a corrupt file is never silently treated as empty ──────────
def test_truncated_file_raises_ledger_corrupt(tmp_path):
    path = tmp_path / "observations.parquet"
    path.write_bytes(b"not a parquet file at all")
    with pytest.raises(history.LedgerCorrupt):
        history.read_ledger(path)


def test_append_refuses_over_corrupt_ledger_never_rewrites(tmp_path):
    path = tmp_path / "observations.parquet"
    path.write_bytes(b"not a parquet file at all")
    before = path.read_bytes()
    with pytest.raises(history.LedgerCorrupt):
        history.append_observations(path, "2026-09-01",
                                    {("theme", "cn_autos"): {"quadrant": "true_accumulation"}},
                                    "2026-09-01T00:00:00+00:00", require_lane=False)
    assert path.read_bytes() == before, "a corrupt ledger must never be silently rewritten"


def test_write_ledger_atomic_original_intact_when_replace_fails(tmp_path, monkeypatch):
    path = tmp_path / "observations.parquet"
    history.append_observations(path, "2026-09-01",
                                {("theme", "cn_autos"): {"quadrant": "true_accumulation"}},
                                "2026-09-01T00:00:00+00:00", require_lane=False)
    original_bytes = path.read_bytes()

    def _boom(src, dst):
        raise OSError("simulated crash between write and os.replace")

    monkeypatch.setattr(history.os, "replace", _boom)
    with pytest.raises(OSError):
        history.append_observations(path, "2026-09-02",
                                    {("theme", "cn_gold"): {"quadrant": "true_distribution"}},
                                    "2026-09-02T00:00:00+00:00", require_lane=False)
    assert path.read_bytes() == original_bytes, (
        "a failed os.replace must leave the ORIGINAL file byte-for-byte untouched")
    leftovers = [p for p in tmp_path.iterdir() if ".tmp-" in p.name]
    assert leftovers == [], "the partial temp file must be cleaned up, not left behind"


# ── B2: belief-identity split — PRODUCT fields only mint revisions ─────────────────────
def test_context_only_status_flap_across_three_runs_mints_one_row(tmp_path):
    path = tmp_path / "observations.parquet"
    healthy = {("market", "cn_large_order_proxy"): {"status": "HEALTHY", "coverage_n": 100}}
    stale = {("market", "cn_large_order_proxy"): {"status": "STALE", "coverage_n": 100}}
    history.append_observations(path, "2026-09-01", healthy, "2026-09-01T00:00:00+00:00",
                                require_lane=False)
    history.append_observations(path, "2026-09-01", stale, "2026-09-01T01:00:00+00:00",
                                require_lane=False)
    r3 = history.append_observations(path, "2026-09-01", healthy, "2026-09-01T02:00:00+00:00",
                                     require_lane=False)
    assert r3["written"] is False and r3["reason"] == "no_changes"
    rows = history.read_ledger(path)
    assert len(rows) == 1, "a routine status flap with no product change must mint ONE row"
    assert rows[0]["revision_id"] == 0


def test_nan_vel_stable_across_runs_no_revision(tmp_path):
    path = tmp_path / "observations.parquet"
    nan = float("nan")
    entities = {("theme", "cn_autos"): {"vel": nan, "quadrant": "neutral_or_unknown", "rank": 10}}
    history.append_observations(path, "2026-09-01", entities, "2026-09-01T00:00:00+00:00",
                                require_lane=False)
    r2 = history.append_observations(path, "2026-09-01", entities, "2026-09-01T01:00:00+00:00",
                                     require_lane=False)
    assert r2["written"] is False and r2["reason"] == "no_changes", (
        "a stable NaN metric must compare equal to itself, never manufacture a revision")


def test_float_jitter_below_tolerance_no_revision(tmp_path):
    path = tmp_path / "observations.parquet"
    e1 = {("theme", "cn_autos"): {"vel": 1.20000000001, "quadrant": "true_accumulation", "rank": 3}}
    e2 = {("theme", "cn_autos"): {"vel": 1.20000000001 + 1e-17, "quadrant": "true_accumulation",
                                 "rank": 3}}
    history.append_observations(path, "2026-09-01", e1, "2026-09-01T00:00:00+00:00",
                                require_lane=False)
    r2 = history.append_observations(path, "2026-09-01", e2, "2026-09-01T01:00:00+00:00",
                                     require_lane=False)
    assert r2["written"] is False and r2["reason"] == "no_changes"


def test_real_product_change_still_revises_despite_b2_split(tmp_path):
    path = tmp_path / "observations.parquet"
    e1 = {("theme", "cn_autos"): {"vel": 1.0, "quadrant": "true_accumulation", "rank": 3,
                                 "status": "HEALTHY"}}
    e2 = {("theme", "cn_autos"): {"vel": 1.5, "quadrant": "true_accumulation", "rank": 3,
                                 "status": "HEALTHY"}}
    history.append_observations(path, "2026-09-01", e1, "2026-09-01T00:00:00+00:00",
                                require_lane=False)
    r2 = history.append_observations(path, "2026-09-01", e2, "2026-09-01T01:00:00+00:00",
                                     require_lane=False)
    assert r2["written"] is True and r2["rows_added"] == 1, (
        "the B2 split must never mask a GENUINE product change")


# ── B3: pinned age semantics — an all-stale baseline must never freeze at None forever ──
def test_all_stale_baseline_age_renders_as_one():
    rows = [_row("theme", "cn_autos", f"2026-08-2{i}", quadrant="true_accumulation",
                status="STALE") for i in range(5)]
    states = history.derive_states(rows, "theme", "cn_autos")
    assert states["2026-08-20"]["note"] == "first tracked session"
    for session in ("2026-08-21", "2026-08-22", "2026-08-23", "2026-08-24"):
        s = states[session]
        assert s["state_age_sessions"] == 1, (session, s)
        assert s["note"] == "age frozen (stale source)"
        assert s["state_started"] == "2026-08-20"


def test_flip_on_stale_day_chip_and_lens_agree():
    rows = [
        _row("theme", "cn_autos", "2026-08-28", quadrant="true_accumulation"),
        _row("theme", "cn_autos", "2026-08-29", quadrant="true_distribution", status="STALE"),
    ]
    states = history.derive_states(rows, "theme", "cn_autos")
    flip = states["2026-08-29"]
    assert flip["state_started"] == "2026-08-29", "onset is the flip session, even stale-stamped"
    assert flip["state_age_sessions"] == 1
    assert flip["prior_state"] == "true_accumulation"
    assert flip["note"] == "age frozen (stale source)"


def test_recovery_resumes_counting_after_stale_gap():
    rows = [
        _row("theme", "cn_autos", "2026-08-25", quadrant="true_accumulation"),
        _row("theme", "cn_autos", "2026-08-26", quadrant="true_accumulation", status="STALE"),
        _row("theme", "cn_autos", "2026-08-27", quadrant="true_accumulation", status="STALE"),
        _row("theme", "cn_autos", "2026-08-28", quadrant="true_accumulation"),
        _row("theme", "cn_autos", "2026-08-31", quadrant="true_accumulation"),
    ]
    states = history.derive_states(rows, "theme", "cn_autos")
    recovery = states["2026-08-28"]
    assert recovery["note"] is None
    assert recovery["state_started"] == "2026-08-25"
    assert recovery["state_age_sessions"] == 2, "onset day + recovery day, stale days transparent"
    later = states["2026-08-31"]
    assert later["state_age_sessions"] == 3


def test_prior_state_correct_across_null_quadrant_stale_day():
    rows = [
        _row("theme", "cn_autos", "2026-08-25", quadrant="true_accumulation"),
        _row("theme", "cn_autos", "2026-08-26", quadrant=None, status="STALE"),
        _row("theme", "cn_autos", "2026-08-27", quadrant="true_distribution"),
    ]
    states = history.derive_states(rows, "theme", "cn_autos")
    flip = states["2026-08-27"]
    assert flip["prior_state"] == "true_accumulation", (
        "the null-quadrant stale day must be transparently skipped, not reported as prior")
    assert flip["state_started"] == "2026-08-27"
    assert flip["state_age_sessions"] == 1


# ── S4: prospective first_known_at — never regresses to None across healthy builds ─────
def test_prospective_first_known_at_advances_across_consecutive_healthy_builds(tmp_path):
    path = tmp_path / "observations.parquet"
    days_and_stamps = [
        ("2026-08-25", "2026-08-25T00:00:00+00:00"),
        ("2026-08-26", "2026-08-26T00:00:00+00:00"),
        ("2026-08-27", "2026-08-27T00:00:00+00:00"),
    ]
    for day, now in days_and_stamps:
        entities = {("market", "cn_large_order_proxy"): {"status": "HEALTHY", "coverage_n": 100}}
        res = history.append_observations(path, day, entities, now, require_lane=False)
        assert res["written"] is True, (day, res)
    rows = history.read_ledger(path)
    stamps = [history.first_known_at(rows, "market", "cn_large_order_proxy", day)
             for day, _ in days_and_stamps]
    assert all(s is not None for s in stamps), stamps
    assert stamps == sorted(stamps), "first_known_at must advance, never regress, per session"
    assert stamps == [now for _, now in days_and_stamps]


# ── S5: monotonicity — a clock stepback is refused, not silently accepted ──────────────
def test_append_refuses_clock_stepback_and_preserves_replay_ordering(tmp_path):
    path = tmp_path / "observations.parquet"
    history.append_observations(path, "2026-09-01",
                                {("theme", "cn_autos"): {"quadrant": "true_accumulation"}},
                                "2026-09-01T00:00:00+00:00", require_lane=False)
    before_rows = history.read_ledger(path)
    before_bytes = path.read_bytes()

    with pytest.raises(history.ClockStepback):
        history.append_observations(path, "2026-08-30",
                                    {("theme", "cn_gold"): {"quadrant": "true_distribution"}},
                                    "2026-08-30T00:00:00+00:00", require_lane=False)

    assert path.read_bytes() == before_bytes, "a stepback refusal must write nothing"
    after_rows = history.read_ledger(path)
    assert after_rows == before_rows
    replayed = history.replay(after_rows, "2026-09-01T12:00:00+00:00")
    assert len(replayed) == 1 and replayed[0]["entity_id"] == "cn_autos"


# ── M9: baseline unification — quality_transitions never mix two different "yesterday"s ─
def test_quality_transitions_use_ledger_baseline_when_ledger_drives():
    log_rows = [
        {"session": "2026-08-29", "themes": {}, "health": {"legs": {"leg_a": {"status": "HEALTHY"}}}},
        {"session": "2026-08-30", "themes": {}, "health": {"legs": {"leg_a": {"status": "DEGRADED"}}}},
    ]
    ledger_rows = [
        _row("theme", "cn_autos", "2026-08-25", quadrant="true_accumulation", rank=1),
        _row("theme", "cn_autos", "2026-08-29", quadrant="true_accumulation", rank=1),
    ]
    assert history.ledger_session_count(ledger_rows, "theme") == 2
    current = {"session": "2026-08-31",
              "themes": {"cn_autos": {"quadrant": "true_accumulation", "rank": 1}},
              "legs": {"leg_a": "DEGRADED"}}
    cs = fo_changes.compute_changes(current, log_rows, ledger_rows=ledger_rows)
    assert cs["previous_valid_session"] == "2026-08-29"
    qt = {(q["id"], q["from_status"], q["to_status"]) for q in cs["quality_transitions"]}
    assert ("leg_a", "HEALTHY", "DEGRADED") in qt, (
        "the quality baseline must be the LEDGER's own previous session (08-29, HEALTHY), "
        f"never state_log's more-recent, ledger-invisible 08-30 entry: got "
        f"{cs['quality_transitions']}")


def test_quality_transitions_use_state_log_baseline_in_fallback_path():
    log_rows = [
        {"session": "2026-08-29", "themes": {}, "health": {"legs": {"leg_a": {"status": "HEALTHY"}}}},
        {"session": "2026-08-30", "themes": {}, "health": {"legs": {"leg_a": {"status": "DEGRADED"}}}},
    ]
    current = {"session": "2026-08-31", "themes": {}, "legs": {"leg_a": "DEGRADED"}}
    cs = fo_changes.compute_changes(current, log_rows, ledger_rows=[])
    assert cs["previous_valid_session"] == "2026-08-30"
    assert cs["quality_transitions"] == [], (
        "the fallback path's OWN baseline (08-30, already DEGRADED) shows no new transition")


# ── NIT12: ISO stamps keep milliseconds; a naive datetime raises ──────────────────────
def test_iso_keeps_milliseconds_for_a_real_datetime(tmp_path):
    from datetime import datetime, timezone

    path = tmp_path / "observations.parquet"
    now = datetime(2026, 9, 1, 12, 30, 45, 123000, tzinfo=timezone.utc)
    res = history.append_observations(path, "2026-09-01",
                                      {("theme", "cn_autos"): {"quadrant": "true_accumulation"}},
                                      now, require_lane=False)
    assert res["written"] is True
    rows = history.read_ledger(path)
    assert rows[0]["first_known_at"].endswith(".123+00:00"), rows[0]["first_known_at"]


def test_iso_raises_on_naive_datetime():
    from datetime import datetime

    with pytest.raises(ValueError):
        history._iso(datetime(2026, 9, 1, 12, 0, 0))


# ── NIT13: revision_receipts keyed on identity, never a revised_at TIMESTAMP match ─────
def test_revision_receipts_keyed_on_identity_not_timestamp_collision():
    rows = [
        _row("theme", "cn_autos", "2026-08-29", revision_id=0, quadrant="true_accumulation"),
        _row("theme", "cn_autos", "2026-08-29", revision_id=1, quadrant="true_distribution",
            revised_at="2026-08-30T00:00:00.000+00:00"),
        _row("theme", "cn_gold", "2026-08-29", revision_id=0, quadrant="true_accumulation"),
        # a DIFFERENT, unrelated revision that happens to share the exact same revised_at
        # stamp — the old timestamp-matching revision_receipts would have pulled this in too.
        _row("theme", "cn_gold", "2026-08-29", revision_id=1, quadrant="true_distribution",
            revised_at="2026-08-30T00:00:00.000+00:00"),
    ]
    keys = {("theme", "cn_autos", "2026-08-29", 1)}
    receipts = history.revision_receipts(rows, keys)
    assert len(receipts) == 1, receipts
    assert receipts[0]["id"] == "cn_autos"


# ── M10: preview_revisions gains the SAME lane gate as append ──────────────────────────
def test_preview_revisions_off_lane_returns_no_revised_markers(tmp_path, monkeypatch):
    monkeypatch.delenv("COLLECT_LANE", raising=False)
    monkeypatch.delenv("US_LANE", raising=False)
    monkeypatch.delenv("CN_LANE", raising=False)
    path = tmp_path / "observations.parquet"
    history.append_observations(path, "2026-08-29",
                                {("theme", "cn_autos"): {"quadrant": "true_accumulation", "rank": 1}},
                                "2026-08-29T00:00:00+00:00", require_lane=False)
    ledger_rows = history.read_ledger(path)
    corrected = {("theme", "cn_autos"): {"quadrant": "true_distribution", "rank": 4}}
    revisions = history.preview_revisions(ledger_rows, "2026-08-29", corrected,
                                          "2026-08-30T00:00:00+00:00")
    assert revisions == [], "an off-lane preview must never show a REVISED marker it will never persist"