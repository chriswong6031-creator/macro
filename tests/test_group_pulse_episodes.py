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
