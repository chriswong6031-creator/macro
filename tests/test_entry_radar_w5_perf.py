"""W5 replay attach/match hot-path invariants.

The optimisations these pin are PURE PERFORMANCE: the frozen §6/§7 prereg laws,
the outcome set and the control selection are untouched, and the runner must
emit byte-identical results.  So every test here is an EQUIVALENCE test written
against the formulation it replaced — the legacy expression is spelled out in
the test body as the reference, so a regression has to disagree with the old
code, not merely with a hard-coded expectation.

Background (measured 2026-08-15, synthetic 1,200-name x 2,600-session panel):
``_attach_and_match`` ran at 467.8 ms/episode, of which ~92% was
``copy.deepcopy`` under pandas' ``NDFrame.__finalize__`` — pandas deep-copies
``DataFrame.attrs`` on every metadata-propagating operation, and the feature
panel carries the whole session-position map in ``attrs``.  After the three
fixes below it runs at 8.0 ms/episode (58x) with identical output.
"""
from __future__ import annotations

import copy
import pickle

import numpy as np
import pandas as pd
import pytest

from engine.entry_radar.replay import controls, feature_panel, panels


# --------------------------------------------------------------------------- #
# SessionPositions — the attrs payload that must never be deep-copied
# --------------------------------------------------------------------------- #
def _positions(n: int = 40) -> panels.SessionPositions:
    return panels.session_positions(pd.bdate_range("2020-01-02", periods=n))


def test_session_positions_reads_exactly_like_the_plain_dict_it_replaced():
    pos = _positions()
    plain = {pd.Timestamp(ts): i
             for i, ts in enumerate(pd.bdate_range("2020-01-02", periods=40))}
    assert pos == plain and plain == pos
    assert dict(pos) == plain
    assert len(pos) == len(plain)
    assert list(pos.keys()) == list(plain.keys())
    assert list(pos.values()) == list(plain.values())
    for key in plain:
        assert pos[key] == plain[key]
        assert pos.get(key) == plain.get(key)
        assert key in pos
    assert pos.get(pd.Timestamp("1999-01-04")) is None
    # the isinstance(..., dict) check tests/test_entry_radar_w5_data.py relies on
    assert isinstance(pos, dict)


@pytest.mark.parametrize("mutate", [
    lambda p: p.__setitem__(pd.Timestamp("2020-01-02"), 99),
    lambda p: p.__delitem__(pd.Timestamp("2020-01-02")),
    lambda p: p.update({pd.Timestamp("2020-01-02"): 99}),
    lambda p: p.setdefault(pd.Timestamp("2031-01-01"), 5),
    lambda p: p.pop(pd.Timestamp("2020-01-02")),
    lambda p: p.popitem(),
    lambda p: p.clear(),
])
def test_session_positions_refuses_mutation(mutate):
    """Read-only is what makes sharing (below) SAFE rather than merely fast."""
    pos = _positions()
    before = dict(pos)
    with pytest.raises(TypeError):
        mutate(pos)
    assert dict(pos) == before


def test_session_positions_is_shared_not_copied():
    pos = _positions()
    assert copy.copy(pos) is pos
    assert copy.deepcopy(pos) is pos
    # nested, the way pandas reaches it: attrs is deep-copied as a whole
    assert copy.deepcopy({"session_pos_by_date": pos})["session_pos_by_date"] is pos


def test_session_positions_survives_pickle():
    """Blocking ``__setitem__``/``update`` breaks the default dict-subclass
    unpickle path — ``__reduce__`` must rebuild through the constructor."""
    pos = _positions()
    back = pickle.loads(pickle.dumps(pos))
    assert isinstance(back, panels.SessionPositions)
    assert back == pos
    with pytest.raises(TypeError):
        back[pd.Timestamp("2020-01-02")] = 0


def test_panel_attrs_ride_pandas_operations_without_being_copied():
    """The whole point: a derived frame SHARES the map instead of deep-copying it.

    Mutation control — with a plain dict, pandas hands back a copy, so the
    ``is`` assertion below is not vacuous.
    """
    pos = _positions()
    frame = pd.DataFrame({"ticker": ["A", "B"], "session": [pd.Timestamp("2020-01-02")] * 2})
    frame.attrs["session_pos_by_date"] = pos
    derived = frame[frame["ticker"] == "A"]
    assert derived.attrs["session_pos_by_date"] is pos

    plain = pd.DataFrame({"ticker": ["A", "B"]})
    plain.attrs["session_pos_by_date"] = dict(pos)
    assert plain[plain["ticker"] == "A"].attrs["session_pos_by_date"] is not \
        plain.attrs["session_pos_by_date"], (
        "a plain dict is deep-copied by pandas — if this ever stops being true "
        "the SessionPositions optimisation is moot, not wrong")


def test_control_session_offset_is_unchanged_through_the_shared_map():
    cal = pd.bdate_range("2020-01-02", periods=40)
    shared, plain = panels.session_positions(cal), {pd.Timestamp(t): i
                                                    for i, t in enumerate(cal)}
    a = pd.DataFrame({"ticker": ["A"]})
    b = pd.DataFrame({"ticker": ["A"]})
    a.attrs["session_pos_by_date"] = shared
    b.attrs["session_pos_by_date"] = plain
    for other in list(cal) + [pd.Timestamp("1999-01-04")]:
        for base in (cal[0], cal[10], cal[-1]):
            assert (controls._session_offset(a, other.date(), base.date())
                    == controls._session_offset(b, other.date(), base.date()))


def test_cross_sectionalize_attaches_the_shared_map_not_a_plain_dict():
    """Regression pin: reverting either producer to ``{}``/``dict`` silently
    restores the CPU-hours."""
    empty = feature_panel.cross_sectionalize(pd.DataFrame())
    assert isinstance(empty.attrs["session_pos_by_date"], panels.SessionPositions)
    frame = pd.DataFrame({"session": pd.bdate_range("2020-01-02", periods=3)})
    assert isinstance(feature_panel.attach_session_positions(frame),
                      panels.SessionPositions)
    assert isinstance(
        feature_panel.attach_session_positions(frame, pd.bdate_range("2020-01-02", periods=9)),
        panels.SessionPositions)


# --------------------------------------------------------------------------- #
# _ctx_session_rows — indexed lookup must equal the full-frame boolean mask
# --------------------------------------------------------------------------- #
def _panel(n_names: int = 25, n_sessions: int = 30, *,
           session_dtype: str = "datetime64") -> pd.DataFrame:
    """A feature-panel-shaped frame.

    ``session_dtype`` matters and is not a detail: ``cross_sectionalize`` emits
    ``session`` as an OBJECT column of ``datetime.date`` (``feature_panel._as_dates``
    returns dates and ``build_feature_rows`` writes them straight through), so a
    fixture built from ``pd.bdate_range`` tests a dtype the production panel never
    has.  Both shapes are exercised below.
    """
    rng = np.random.default_rng(4242)
    sessions = pd.bdate_range("2021-03-01", periods=n_sessions)
    col = (np.repeat(sessions, n_names) if session_dtype == "datetime64"
           else np.repeat(np.asarray([s.date() for s in sessions], dtype=object), n_names))
    names = [f"N{i:03d}" for i in range(n_names)]
    frame = pd.DataFrame({
        "ticker": np.tile(np.asarray(names, dtype=object), n_sessions),
        "session": col,
        "proximity_decile": rng.integers(0, 10, n_names * n_sessions),
    })
    # shuffle so "grouped order" and "row order" cannot coincide by accident
    return frame.sample(frac=1.0, random_state=7).reset_index(drop=True)


def _legacy_or_raise(frame, session):
    """The expression `_ctx_session_rows` replaced, incl. its empty->KeyError leg."""
    rows = frame[frame["session"] == pd.Timestamp(session)]
    if rows.empty:
        raise KeyError(f"no feature rows for session {session}")
    return rows


@pytest.mark.parametrize("session_dtype", ["datetime64", "object_date"])
def test_ctx_session_rows_returns_every_row_of_the_session(session_dtype):
    """The indexed lookup resolves the session on BOTH panel shapes.

    REVISITED BY #5780, on this test's own instruction — its previous revision
    ended "if a later change makes the object/date lookup start matching, this
    test must be revisited together with the control-matching refusal census it
    would change".  That change is #5780.

    What it used to assert was equivalence to the boolean mask this index
    replaced.  On the object/date shape production actually emits, that meant the
    two agreed on finding NOTHING — ``date == pd.Timestamp`` is False in Python,
    so both formulations missed every session, every episode fell into
    ``control_match_unavailable``, and the §7 control arm was structurally empty.
    Identity with a broken baseline can no longer be the contract.

    What survives unchanged is the part that licensed the groupby refactor: on
    the datetime64 shape the index must still reproduce the mask row for row and
    index label for index label, with ``attrs`` SHARED rather than deep-copied.
    """
    from scripts import entry_radar_replay as rr

    frame = _panel(session_dtype=session_dtype)
    frame.attrs["session_pos_by_date"] = _positions()
    ctx = {"features": frame}
    all_sessions = sorted({pd.Timestamp(s).date() for s in frame["session"]})
    seen = 0
    for session in all_sessions:
        got = rr._ctx_session_rows(ctx, session)
        assert len(got), f"{session_dtype}: session {session} must resolve"
        assert {pd.Timestamp(s).date() for s in got["session"]} == {session}
        assert got.attrs["session_pos_by_date"] is frame.attrs["session_pos_by_date"]
        if session_dtype == "datetime64":
            pd.testing.assert_frame_equal(got, _legacy_or_raise(frame, session),
                                          check_exact=True)
            assert list(got.index) == list(_legacy_or_raise(frame, session).index)
        seen += len(got)
    assert seen == len(frame), "every row must be reachable through its own session"

    if session_dtype == "object_date":
        # MUTATION CONTROL and provenance in one: the mask this index replaced
        # still finds nothing on the shape production emits.  That is precisely
        # the defect #5780 repaired, and the reason equivalence-to-legacy cannot
        # be the contract on this leg.  If this stops raising, the panel dtype
        # moved and both this file and the §7 lookup need re-reading.
        with pytest.raises(KeyError):
            _legacy_or_raise(frame, all_sessions[0])


def test_ctx_session_rows_still_raises_on_a_session_with_no_rows():
    from scripts import entry_radar_replay as rr

    import datetime as dt

    frame = _panel()
    ctx = {"features": frame}
    with pytest.raises(KeyError):
        rr._ctx_session_rows(ctx, dt.date(1999, 1, 4))


# --------------------------------------------------------------------------- #
# vendor daily-cache memo — same bytes in, same frame out; a rewrite invalidates
# --------------------------------------------------------------------------- #
def _write_daily(path, closes, start="2022-01-03"):
    idx = pd.bdate_range(start, periods=len(closes))
    frame = pd.DataFrame({"o": closes, "h": closes, "l": closes,
                          "c": closes, "v": [1e6] * len(closes)}, index=idx)
    frame.index.name = "session"
    frame.to_parquet(path)


def test_daily_cache_memo_returns_the_same_frame_and_invalidates_on_rewrite(tmp_path):
    from scripts import entry_radar_vendor as vendor

    path = tmp_path / "AAA.parquet"
    _write_daily(path, [10.0, 11.0, 12.0])
    first = vendor._read_daily_cache(path)
    second = vendor._read_daily_cache(path)
    assert first is not None
    pd.testing.assert_frame_equal(first, second, check_exact=True)

    # MUTATION CONTROL: rewriting the file must miss the memo, or the memo would
    # serve a stale plane forever.
    _write_daily(path, [99.0, 98.0, 97.0])
    third = vendor._read_daily_cache(path)
    assert list(third["c"]) == [99.0, 98.0, 97.0], "memo served a stale cache file"


def test_daily_cache_memo_is_bounded(tmp_path, monkeypatch):
    from scripts import entry_radar_vendor as vendor

    monkeypatch.setattr(vendor, "_DAILY_PARSE_CACHE_MAX", 3)
    vendor._DAILY_PARSE_CACHE.clear()
    for i in range(8):
        path = tmp_path / f"T{i}.parquet"
        _write_daily(path, [1.0 + i, 2.0 + i])
        assert vendor._read_daily_cache(path) is not None
    assert len(vendor._DAILY_PARSE_CACHE) <= 3
