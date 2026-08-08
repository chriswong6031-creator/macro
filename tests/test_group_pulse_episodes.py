"""Episode machine + ledger tests for engine/group_pulse.py.

Covers:
  (1)  ENTER needs BOTH bars (activity_share >= 0.50 AND activity_n >= 3).
  (2)  HYSTERESIS: 0.35 sustains an OPEN episode and never opens a new one.
  (3)  Active days <= 2 inactive sessions apart are ONE episode.
  (4)  3 consecutive inactive sessions CLOSE it, at its LAST ACTIVE session — the
       trailing quiet days belong to no episode.
  (5)  Persistence math on a hand-built member fixture (every-session members vs
       one-session tourists).
  (6)  The trailing episode is PROVISIONAL (closed=False) and is recomputed on
       every advance.
  (7)  A closed row is IMMUTABLE: the stored row wins over its recomputed twin,
       so a later data revision cannot rewrite history.
  (8)  Replay determinism: advancing twice over the same inputs leaves the closed
       rows byte-identical.
  (9)  The lane gate — an off-nightly advance computes and DISCARDS (house law:
       nightly is the sole advancer of forward ledgers).
  (10) episode.state_change transitions.
  (11) Degradation: an unreadable ledger annotates at COLUMN 0 and starts empty
       rather than raising into the nightly.

Frozen-fixture law: the state machine is exercised on hand-built series. Nothing
here reads the live member store or the committed ledger.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from engine import group_pulse as GP


# ---------------------------------------------------------------------------
# Fixture builders
# ---------------------------------------------------------------------------

def _dates(n: int) -> list[pd.Timestamp]:
    return list(pd.bdate_range("2026-01-05", periods=n))


def _run(pattern: list[tuple[float, int]], basket_id: str = "b1",
         members: list[set] | None = None) -> list[dict]:
    """`pattern` is [(activity_share, activity_n), ...] one entry per session."""
    d = _dates(len(pattern))
    return GP.episodes_from_series(basket_id, d, [p[0] for p in pattern],
                                   [p[1] for p in pattern], members)


ON = (0.80, 6)     # comfortably above the enter bar
SOFT = (0.40, 5)   # inside the hysteresis band: sustains, never opens
OFF = (0.05, 0)    # inactive


# ---------------------------------------------------------------------------
# (1) enter conditions
# ---------------------------------------------------------------------------

def test_enter_needs_both_the_share_and_the_count():
    assert _run([(0.90, 2)] * 6) == []            # share is there, count is not
    assert _run([(0.30, 9)] * 6) == []            # count is there, share is not
    eps = _run([(0.50, 3)] * 6)                   # exactly on both bars -> enters
    assert len(eps) == 1 and eps[0]["sessions_active"] == 6


def test_a_quiet_series_produces_no_episode():
    assert _run([OFF] * 40) == []


# ---------------------------------------------------------------------------
# (2) hysteresis
# ---------------------------------------------------------------------------

def test_hysteresis_sustains_an_open_episode_below_the_enter_bar():
    """0.40 is below ENTER (0.50) and at/above EXIT (0.35): inside an episode it is
    still an ACTIVE session, so one soft day does not chop the episode in two."""
    eps = _run([ON, ON, SOFT, SOFT, ON])
    assert len(eps) == 1
    assert eps[0]["sessions_active"] == 5
    assert eps[0]["sessions_span"] == 5


def test_hysteresis_never_opens_an_episode():
    assert _run([SOFT] * 30) == []


def test_just_below_the_exit_bar_is_inactive_inside_an_episode():
    """0.34 < EXIT(0.35): the day is inactive even with an episode open."""
    eps = _run([ON, ON, (0.34, 5), (0.34, 5), (0.34, 5), OFF, OFF])
    assert len(eps) == 1 and eps[0]["closed"] is True
    assert eps[0]["sessions_active"] == 2


def test_the_min_active_floor_applies_to_the_hysteresis_bar_too():
    """A soft share with only 2 active members is NOT an active session — the count
    floor is not waived by the hysteresis band."""
    eps = _run([ON, ON, (0.40, 2), (0.40, 2), (0.40, 2), OFF])
    assert len(eps) == 1 and eps[0]["sessions_active"] == 2


# ---------------------------------------------------------------------------
# (3)/(4) gap joining and closure
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("gap", [1, 2])
def test_gaps_of_at_most_two_join_one_episode(gap):
    eps = _run([ON, ON] + [OFF] * gap + [ON, ON])
    assert len(eps) == 1
    assert eps[0]["sessions_active"] == 4
    assert eps[0]["sessions_span"] == 4 + gap


def test_a_three_session_gap_splits_into_two_episodes():
    eps = _run([ON, ON] + [OFF] * 3 + [ON, ON] + [OFF] * 4)
    assert len(eps) == 2
    assert [e["sessions_active"] for e in eps] == [2, 2]
    assert all(e["closed"] for e in eps)


def test_an_episode_closes_at_its_last_active_session():
    """The three quiet sessions that CLOSE an episode are not part of it."""
    d = _dates(6)
    eps = _run([ON, ON, ON, OFF, OFF, OFF])
    assert len(eps) == 1
    assert eps[0]["end_date"] == d[2].strftime("%Y-%m-%d")
    assert eps[0]["start_date"] == d[0].strftime("%Y-%m-%d")
    assert eps[0]["sessions_span"] == 3
    assert eps[0]["closed"] is True


def test_sessions_span_exceeds_sessions_active_when_a_gap_was_bridged():
    eps = _run([ON, OFF, OFF, ON])
    assert eps[0]["sessions_active"] == 2 and eps[0]["sessions_span"] == 4


# ---------------------------------------------------------------------------
# (5) persistence
# ---------------------------------------------------------------------------

def test_persistence_counts_members_active_in_every_active_session():
    members = [{"A", "B", "C"}, {"A", "B", "D"}, {"A", "B", "E"}]
    eps = _run([ON, ON, ON], members=members)
    assert len(eps) == 1
    assert eps[0]["members_ever_active"] == 5      # A B C D E
    assert eps[0]["members_persisted"] == 2        # A B
    assert eps[0]["persistence_share"] == pytest.approx(0.4)


def test_persistence_is_one_when_the_same_members_carry_every_session():
    eps = _run([ON, ON, ON], members=[{"A", "B", "C"}] * 3)
    assert eps[0]["members_persisted"] == 3
    assert eps[0]["persistence_share"] == 1.0


def test_persistence_ignores_the_inactive_sessions_a_gap_bridged():
    """The bridged quiet days are not active sessions, so they cannot empty the
    persisted set — otherwise every bridged episode would report 0."""
    members = [{"A", "B"}, set(), set(), {"A", "B"}]
    eps = _run([ON, OFF, OFF, ON], members=members)
    assert eps[0]["members_persisted"] == 2
    assert eps[0]["persistence_share"] == 1.0


def test_persistence_is_null_without_member_sets():
    eps = _run([ON, ON, ON])
    assert eps[0]["members_ever_active"] == 0
    assert eps[0]["persistence_share"] is None


# ---------------------------------------------------------------------------
# (6) the provisional row
# ---------------------------------------------------------------------------

def test_the_trailing_episode_is_provisional():
    eps = _run([ON, ON, ON])
    assert len(eps) == 1 and eps[0]["closed"] is False


def test_an_episode_inside_its_grace_period_is_still_open():
    eps = _run([ON, ON, OFF, OFF])
    assert len(eps) == 1 and eps[0]["closed"] is False
    assert eps[0]["sessions_active"] == 2


def test_episode_id_is_derivable_from_basket_and_start():
    d = _dates(3)
    eps = _run([ON, ON, ON], basket_id="ai_infra")
    assert eps[0]["episode_id"] == f"ai_infra:{d[0].strftime('%Y-%m-%d')}"


def test_ragged_inputs_raise_rather_than_silently_misalign():
    with pytest.raises(ValueError):
        GP.episodes_from_series("b", _dates(3), [0.9, 0.9], [5, 5, 5])


def test_the_machine_is_pure():
    """Same inputs -> identical output, twice, with no shared mutable state."""
    pattern = [ON, ON, OFF, ON, OFF, OFF, OFF, ON, ON]
    members = [{"A", "B", "C"} for _ in pattern]
    assert _run(pattern, members=[set(m) for m in members]) == \
        _run(pattern, members=[set(m) for m in members])


# ---------------------------------------------------------------------------
# (7)/(8) ledger immutability + replay determinism
# ---------------------------------------------------------------------------

def _closed_bytes(df: pd.DataFrame) -> bytes:
    """A literal byte image of the closed rows — a frame comparison can pass on
    values while a dtype or an order changed underneath it."""
    c = df[df["closed"]].sort_values("episode_id", kind="stable")
    return c.to_csv(index=False).encode()


def test_closed_rows_are_immutable(tmp_path):
    """The stored closed row WINS over its recomputed twin. This is the whole
    provisional-bucket law: the stored row is never asked to agree with a recompute,
    so a later data revision cannot silently rewrite a closed episode."""
    computed = {"b1": _run([ON, ON, ON] + [OFF] * 4)}
    GP.advance_episode_ledger(computed, tmp_path, require_nightly_lane=False,
                              advanced_at="T1")
    first = GP.read_ledger(tmp_path)
    assert len(first) == 1 and bool(first["closed"].iloc[0]) is True

    # a REVISED recompute of the same episode — different numbers, same id
    revised = [{**computed["b1"][0], "sessions_active": 999,
                "members_ever_active": 999, "persistence_share": 0.123}]
    GP.advance_episode_ledger({"b1": revised}, tmp_path,
                              require_nightly_lane=False, advanced_at="T2")
    second = GP.read_ledger(tmp_path)
    assert _closed_bytes(first) == _closed_bytes(second)
    assert int(second["sessions_active"].iloc[0]) == 3
    assert str(second["advanced_at"].iloc[0]) == "T1"


def test_replay_determinism_over_identical_inputs(tmp_path):
    computed = {"b1": _run([ON, ON] + [OFF] * 4 + [ON, ON, ON], basket_id="b1"),
                "b2": _run([ON] * 4 + [OFF] * 5, basket_id="b2")}
    GP.advance_episode_ledger(computed, tmp_path, require_nightly_lane=False,
                              advanced_at="T1")
    first = GP.read_ledger(tmp_path)
    GP.advance_episode_ledger(computed, tmp_path, require_nightly_lane=False,
                              advanced_at="T2")
    second = GP.read_ledger(tmp_path)
    assert _closed_bytes(first) == _closed_bytes(second)
    assert len(first) == len(second)


def test_the_provisional_row_is_recomputed_each_advance(tmp_path):
    """The OPEN row is the one thing an advance may rewrite — a growing episode must
    be allowed to grow, or the pulse artifact would print a frozen session count."""
    GP.advance_episode_ledger({"b1": _run([ON, ON])}, tmp_path,
                              require_nightly_lane=False, advanced_at="T1")
    GP.advance_episode_ledger({"b1": _run([ON, ON, ON, ON])}, tmp_path,
                              require_nightly_lane=False, advanced_at="T2")
    df = GP.read_ledger(tmp_path)
    assert len(df) == 1
    assert bool(df["closed"].iloc[0]) is False
    assert int(df["sessions_active"].iloc[0]) == 4
    assert str(df["advanced_at"].iloc[0]) == "T2"


def test_an_open_episode_that_later_closes_freezes_at_that_point(tmp_path):
    GP.advance_episode_ledger({"b1": _run([ON, ON])}, tmp_path,
                              require_nightly_lane=False, advanced_at="T1")
    GP.advance_episode_ledger({"b1": _run([ON, ON] + [OFF] * 4)}, tmp_path,
                              require_nightly_lane=False, advanced_at="T2")
    closed = GP.read_ledger(tmp_path)
    assert bool(closed["closed"].iloc[0]) is True and str(closed["advanced_at"].iloc[0]) == "T2"
    # a third advance must not touch it again
    GP.advance_episode_ledger({"b1": _run([ON, ON] + [OFF] * 4)}, tmp_path,
                              require_nightly_lane=False, advanced_at="T3")
    assert _closed_bytes(GP.read_ledger(tmp_path)) == _closed_bytes(closed)


def test_new_episodes_append_without_disturbing_the_old(tmp_path):
    GP.advance_episode_ledger({"b1": _run([ON, ON] + [OFF] * 4)}, tmp_path,
                              require_nightly_lane=False, advanced_at="T1")
    before = GP.read_ledger(tmp_path)
    GP.advance_episode_ledger(
        {"b1": _run([ON, ON] + [OFF] * 4 + [ON, ON] + [OFF] * 4)}, tmp_path,
        require_nightly_lane=False, advanced_at="T2")
    after = GP.read_ledger(tmp_path)
    assert len(after) == 2
    assert _closed_bytes(before[before["closed"]]) == _closed_bytes(
        after[after["episode_id"] == before["episode_id"].iloc[0]])


def test_ledger_columns_and_dtypes_are_frozen(tmp_path):
    GP.advance_episode_ledger({"b1": _run([ON, ON, ON] + [OFF] * 4)}, tmp_path,
                              require_nightly_lane=False, advanced_at="T1")
    df = pd.read_parquet(GP.ledger_path(tmp_path))
    assert tuple(df.columns) == GP.EPISODE_COLUMNS
    assert df["sessions_active"].dtype == np.dtype("int64")
    assert df["persistence_share"].dtype == np.dtype("float64")
    assert df["closed"].dtype == np.dtype("bool")


# ---------------------------------------------------------------------------
# (9) the lane gate
# ---------------------------------------------------------------------------

def test_off_lane_advance_computes_and_discards(tmp_path, monkeypatch):
    monkeypatch.delenv("COLLECT_LANE", raising=False)
    monkeypatch.delenv("US_LANE", raising=False)
    res = GP.advance_episode_ledger({"b1": _run([ON, ON, ON])}, tmp_path)
    assert res["written"] is False and res["reason"] == "off_nightly_lane"
    assert not GP.ledger_path(tmp_path).exists()


def test_nightly_lane_advance_writes(tmp_path, monkeypatch):
    monkeypatch.setenv("COLLECT_LANE", "nightly")
    res = GP.advance_episode_ledger({"b1": _run([ON, ON, ON])}, tmp_path)
    assert res["written"] is True and res["rows"] == 1
    assert GP.ledger_path(tmp_path).exists()


# ---------------------------------------------------------------------------
# (10) state_change
# ---------------------------------------------------------------------------

def _daily(shares: list[float]) -> pd.DataFrame:
    return pd.DataFrame({"activity_share": shares}, index=_dates(len(shares)))


def test_state_change_strengthening():
    assert GP.episode_state_change(_daily([0.40, 0.60]), True) == "strengthening"


def test_state_change_cooling_inside_an_episode():
    assert GP.episode_state_change(_daily([0.80, 0.60]), True) == "cooling"


def test_state_change_cooling_inside_the_exit_hysteresis_band():
    """Falling out of an episode into [0.35, 0.50) still reads COOLING — the drop is
    the news, and it is not yet quiet."""
    assert GP.episode_state_change(_daily([0.60, 0.40]), False) == "cooling"


def test_state_change_steady():
    assert GP.episode_state_change(_daily([0.60, 0.62]), True) == "steady"


def test_state_change_quiet():
    assert GP.episode_state_change(_daily([0.10, 0.12]), False) == "quiet"
    assert GP.episode_state_change(_daily([]), False) == "quiet"


def test_a_big_drop_to_nothing_is_quiet_not_cooling():
    """Below the hysteresis band with no open episode there is nothing to cool."""
    assert GP.episode_state_change(_daily([0.60, 0.05]), False) == "quiet"


# ---------------------------------------------------------------------------
# (11) degradation
# ---------------------------------------------------------------------------

def test_an_unreadable_ledger_annotates_at_column_zero_and_starts_empty(tmp_path, capsys):
    p = GP.ledger_path(tmp_path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_bytes(b"not a parquet file")
    df = GP.read_ledger(tmp_path)
    assert df.empty and tuple(df.columns) == GP.EPISODE_COLUMNS
    out = capsys.readouterr().out
    ann = [ln for ln in out.splitlines() if "episode ledger unreadable" in ln]
    assert ann, out
    # GitHub only parses a workflow command when "::" STARTS the line.
    assert ann[0].startswith("::"), ann[0]


def test_a_missing_ledger_reads_as_an_empty_typed_frame(tmp_path):
    df = GP.read_ledger(tmp_path)
    assert df.empty and tuple(df.columns) == GP.EPISODE_COLUMNS
    assert df["closed"].dtype == np.dtype("bool")


def test_merge_over_an_empty_ledger_writes_every_episode():
    computed = {"b1": _run([ON, ON, ON] + [OFF] * 4 + [ON, ON])}
    out = GP.merge_episodes(GP._empty_ledger(), computed, "T1")
    assert len(out) == 2
    assert list(out["advanced_at"]) == ["T1", "T1"]


# ---------------------------------------------------------------------------
# (12) site/basketdata/episodes.json — the web-readable CLOSED-episode history
# ---------------------------------------------------------------------------

def _seeded_ledger(tmp_path, computed: dict[str, list[dict]]):
    GP.advance_episode_ledger(computed, tmp_path, require_nightly_lane=False,
                              advanced_at="T1")
    return GP.read_ledger(tmp_path)


def test_episodes_json_matches_the_ledgers_closed_rows(tmp_path):
    """THE contract: every row the artifact publishes is a row the LEDGER froze —
    same episodes, same field values, same order — and nothing else.

    The ledger is the source of truth on purpose. A surface that re-derived this
    history instead could quietly disagree with the immutable store the moment an
    input was revised, and the disagreement would only ever show up to a user.
    """
    computed = {
        # three closed episodes + one still open
        "b1": _run([ON, ON] + [OFF] * 4 + [ON] + [OFF] * 4 + [ON, ON, ON] + [OFF] * 4
                   + [ON, ON], basket_id="b1"),
        "b2": _run([ON, ON, ON] + [OFF] * 5, basket_id="b2"),
    }
    ledger = _seeded_ledger(tmp_path, computed)
    history = GP.closed_episode_history(ledger, ["b1", "b2"])
    assert GP.validate_episode_history(history) == []

    for bid in ("b1", "b2"):
        stored = ledger[(ledger["basket_id"] == bid) & ledger["closed"]]
        expected = [
            {"start_date": str(r.start_date), "end_date": str(r.end_date),
             "sessions_active": int(r.sessions_active),
             "sessions_span": int(r.sessions_span),
             "members_ever_active": int(r.members_ever_active),
             "persistence_share": (None if pd.isna(r.persistence_share)
                                   else float(r.persistence_share))}
            for r in stored.sort_values("start_date", ascending=False).itertuples(index=False)
        ]
        assert history[bid] == expected, bid


def test_episodes_json_ignores_the_provisional_open_row(tmp_path):
    """An episode still running is not history — pulse.json's `episode` block already
    carries the current state, and publishing an open row here would double-count it
    AND publish a number that changes every night."""
    computed = {"b1": _run([ON, ON] + [OFF] * 4 + [ON, ON, ON], basket_id="b1")}
    ledger = _seeded_ledger(tmp_path, computed)
    assert int((~ledger["closed"]).sum()) == 1, "fixture must contain an OPEN row"
    open_start = str(ledger.loc[~ledger["closed"], "start_date"].iloc[0])

    history = GP.closed_episode_history(ledger, ["b1"])
    assert len(history["b1"]) == 1
    assert open_start not in [r["start_date"] for r in history["b1"]]
    assert int(ledger["closed"].sum()) == len(history["b1"])


def test_a_basket_with_no_closed_episode_keeps_its_key_with_an_empty_list(tmp_path):
    """A missing key would make the surface branch on presence; an empty list lets it
    render "no prior episodes" without a special case."""
    ledger = _seeded_ledger(tmp_path, {"b1": _run([ON, ON, ON])})   # open only
    history = GP.closed_episode_history(ledger, ["b1", "b2", "b3"])
    assert set(history) == {"b1", "b2", "b3"}
    assert history == {"b1": [], "b2": [], "b3": []}


def test_episodes_json_is_newest_first_and_capped(tmp_path):
    pattern: list[tuple[float, int]] = []
    for _ in range(14):                       # 14 closed episodes, oldest first
        pattern += [ON, ON] + [OFF] * 4
    ledger = _seeded_ledger(tmp_path, {"b1": _run(pattern, basket_id="b1")})
    assert int(ledger["closed"].sum()) == 14

    rows = GP.closed_episode_history(ledger, ["b1"])["b1"]
    assert len(rows) == GP.EPISODES_JSON_MAX == 10
    starts = [r["start_date"] for r in rows]
    assert starts == sorted(starts, reverse=True), "newest first"
    newest_stored = str(ledger[ledger["closed"]]["start_date"].max())
    assert starts[0] == newest_stored, "the cap must drop the OLDEST, not the newest"


def test_episodes_json_rows_carry_exactly_the_six_contract_keys(tmp_path):
    ledger = _seeded_ledger(tmp_path, {"b1": _run([ON, ON] + [OFF] * 4)})
    row = GP.closed_episode_history(ledger, ["b1"])["b1"][0]
    assert set(row) == set(GP.EPISODE_JSON_KEYS)
    # the ledger's bookkeeping columns stay in the ledger
    for leaked in ("episode_id", "basket_id", "closed", "advanced_at", "members_persisted"):
        assert leaked not in row


def test_a_ledger_basket_outside_the_key_set_is_not_published(tmp_path):
    """The key set is pulse.json's baskets. A basket that left membership still has
    frozen ledger rows — it must not reappear on a surface that has no pulse for it."""
    ledger = _seeded_ledger(tmp_path, {"b1": _run([ON, ON] + [OFF] * 4, basket_id="b1"),
                                       "retired": _run([ON, ON] + [OFF] * 4,
                                                       basket_id="retired")})
    history = GP.closed_episode_history(ledger, ["b1"])
    assert set(history) == {"b1"} and len(history["b1"]) == 1


def test_a_missing_or_empty_ledger_yields_empty_lists(tmp_path):
    assert GP.closed_episode_history(GP.read_ledger(tmp_path), ["b1", "b2"]) == \
        {"b1": [], "b2": []}
    assert GP.closed_episode_history(GP._empty_ledger(), []) == {}


def test_a_null_persistence_share_publishes_as_null(tmp_path):
    """No member sets -> members_ever_active 0 -> persistence is UNKNOWN. It must
    publish as null, not as 0.0, which would read as "nobody persisted"."""
    ledger = _seeded_ledger(tmp_path, {"b1": _run([ON, ON] + [OFF] * 4)})
    row = GP.closed_episode_history(ledger, ["b1"])["b1"][0]
    assert row["members_ever_active"] == 0
    assert row["persistence_share"] is None


def test_the_artifact_round_trips_as_json(tmp_path):
    import json
    ledger = _seeded_ledger(tmp_path, {"b1": _run([ON, ON] + [OFF] * 4 + [ON, ON, ON])})
    history = GP.closed_episode_history(ledger, ["b1", "b2"])
    p = GP.write_episodes_artifact(history, tmp_path)
    assert p == tmp_path / "basketdata" / "episodes.json"
    assert json.loads(p.read_text(encoding="utf-8")) == history


@pytest.mark.parametrize("mutant,needle", [
    ({"b1": [{"start_date": "2026-01-01", "end_date": "2026-01-02",
              "sessions_active": 2, "sessions_span": 2, "members_ever_active": 3,
              "persistence_share": 1.0, "rank": 1}]}, "keys must be"),
    ({"b1": [{"start_date": "2026-01-01"}]}, "keys must be"),
    ({"b1": "not a list"}, "must be a list"),
])
def test_the_history_validator_goes_red_on_mutants(mutant, needle):
    errs = GP.validate_episode_history(mutant)
    assert any(needle in e for e in errs), errs


def test_the_history_validator_catches_a_wrong_sort_order():
    rows = [{"start_date": "2026-01-01", "end_date": "2026-01-02", "sessions_active": 1,
             "sessions_span": 1, "members_ever_active": 3, "persistence_share": 1.0},
            {"start_date": "2026-05-01", "end_date": "2026-05-02", "sessions_active": 1,
             "sessions_span": 1, "members_ever_active": 3, "persistence_share": 1.0}]
    errs = GP.validate_episode_history({"b1": rows})
    assert any("newest-first" in e for e in errs), errs


def test_run_writes_BOTH_artifacts_and_degrades_without_data(tmp_path, capsys):
    """The emission is wired into run(), and an empty data plane still produces both
    files rather than raising into the nightly."""
    import json
    data_root, site_root = tmp_path / "data", tmp_path / "site"
    data_root.mkdir()
    res = GP.run(data_root=data_root, site_root=site_root, require_nightly_lane=False)
    pulse = site_root / "basketdata" / "pulse.json"
    episodes = site_root / "basketdata" / "episodes.json"
    assert pulse.exists() and episodes.exists()
    assert json.loads(pulse.read_text()) == {}
    assert json.loads(episodes.read_text()) == {}
    assert res["n_closed_episodes"] == 0
    assert res["episodes_artifact"] == str(episodes)
