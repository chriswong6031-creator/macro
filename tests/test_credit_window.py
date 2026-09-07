"""RED-first tests for engine/credit_window.py — the HY/IG bond issuance
window gate (packet B-F09-2). Fixtures build tiny parquet files under
tmp_path/{fred,archive,yahoo}/; every test passes root=tmp_path.

Fixture series end TODAY (not a fixed historical date) so their `as_of` is
fresh under the module's staleness gate (MAJOR 6) — a hardcoded 2024 anchor
would silently trip staleness in 2026+ and mask the behaviour under test.
"""
from __future__ import annotations

import pandas as pd
import pytest

from engine import credit_window as cw


def _end_bdate_range(periods, end=None):
    end = end or pd.Timestamp.now().normalize()
    return pd.bdate_range(end=end, periods=periods)


def _write_series(path, values, end=None):
    path.parent.mkdir(parents=True, exist_ok=True)
    idx = _end_bdate_range(len(values), end=end)
    df = pd.DataFrame({"value": values}, index=idx)
    df.to_parquet(path)


def _write_close(path, values, end=None):
    path.parent.mkdir(parents=True, exist_ok=True)
    idx = _end_bdate_range(len(values), end=end)
    df = pd.DataFrame({"close": values}, index=idx)
    df.to_parquet(path)


def test_scored_flag_is_false():
    assert cw.SCORED is False


def test_input_state_spread_range_thresholds():
    assert cw.input_state("spread_range", 0) == "open"
    assert cw.input_state("spread_range", 33.0) == "open"
    assert cw.input_state("spread_range", 33.1) == "neutral"
    assert cw.input_state("spread_range", 66.0) == "neutral"
    assert cw.input_state("spread_range", 66.1) == "shut"
    assert cw.input_state("spread_range", 100) == "shut"


def test_input_state_spread_drift_thresholds():
    assert cw.input_state("spread_drift", -20) == "open"
    assert cw.input_state("spread_drift", -15) == "open"
    assert cw.input_state("spread_drift", -14.9) == "neutral"
    assert cw.input_state("spread_drift", 24.9) == "neutral"
    assert cw.input_state("spread_drift", 25) == "shut"
    assert cw.input_state("spread_drift", 60) == "shut"


def test_input_state_rates_vol_thresholds():
    assert cw.input_state("rates_vol", 0) == "open"
    assert cw.input_state("rates_vol", 40) == "open"
    assert cw.input_state("rates_vol", 40.1) == "neutral"
    assert cw.input_state("rates_vol", 75) == "neutral"
    assert cw.input_state("rates_vol", 75.1) == "shut"
    assert cw.input_state("rates_vol", 100) == "shut"


def test_input_state_none_is_unknown():
    for key in ("spread_range", "spread_drift", "rates_vol", "anything"):
        assert cw.input_state(key, None) == "unknown"


def test_segment_open_requires_two_open_inputs():
    state, n, low = cw.segment_state(["open", "neutral", "neutral"])
    assert state == "neutral"
    assert state != "open"


def test_segment_two_open_inputs_flips_open():
    # MAJOR 7 — the primary "open" behaviour was never exercised.
    state, n, low = cw.segment_state(["open", "open", "neutral"])
    assert state == "open"
    assert n == 3
    assert low is False


def test_segment_two_shut_inputs_flips_shut():
    state, n, low = cw.segment_state(["shut", "shut", "neutral"])
    assert state == "shut"


def test_segment_two_open_one_unknown_is_still_open_but_low_confidence():
    # Precisely the "never open by default" guard acceptance line 3 names:
    # two open inputs with the third genuinely missing must not silently
    # become a full, undisclosed "open" verdict — it renders open, but with
    # low_confidence True so the gap is visible.
    state, n, low = cw.segment_state(["open", "open", "unknown"])
    assert state == "open"
    assert n == 2
    assert low is True


def test_segment_not_evaluable_below_min_inputs():
    assert cw.segment_state(["open", "unknown", "unknown"]) == ("not_evaluable", 1, True)
    state, n, low = cw.segment_state(["unknown", "unknown", "unknown"])
    assert state == "not_evaluable"
    assert n == 0
    assert low is True
    assert state != "open"


def test_window_state_null_path_when_hy_series_missing(tmp_path):
    _write_series(tmp_path / "fred" / f"{cw.FRED_IG}.parquet", [1.0] * 260)
    _write_close(tmp_path / "yahoo" / f"{cw.MOVE_TICKER}.parquet", [80.0] * 260)
    out = cw.window_state(root=tmp_path)
    segs = {s["key"]: s for s in out["segments"]}
    assert segs["hy"]["state"] == "not_evaluable"
    assert segs["hy"]["rail"] is None
    assert segs["ig"]["state"] != "not_evaluable"


def test_window_state_null_path_when_move_missing(tmp_path):
    _write_series(tmp_path / "fred" / f"{cw.FRED_HY}.parquet", [3.0] * 260)
    _write_series(tmp_path / "fred" / f"{cw.FRED_IG}.parquet", [1.0] * 260)
    out = cw.window_state(root=tmp_path)
    for seg in out["segments"]:
        assert seg["low_confidence"] is True
        # MOVE missing entirely must never silently degrade into "open by
        # default" — this exercises the exact fixture acceptance line 3 guards.
        assert seg["state"] != "open" or seg["low_confidence"] is True


def test_as_of_propagates_per_input_and_to_top_level(tmp_path):
    _write_series(tmp_path / "fred" / f"{cw.FRED_HY}.parquet", [3.0] * 260)
    _write_series(tmp_path / "fred" / f"{cw.FRED_IG}.parquet", [1.0] * 260)
    _write_close(tmp_path / "yahoo" / f"{cw.MOVE_TICKER}.parquet", [80.0] * 260)
    out = cw.window_state(root=tmp_path)
    for seg in out["segments"]:
        for inp in seg["inputs"]:
            assert inp["as_of"] is not None
    assert out["as_of"] == max(
        i["as_of"] for seg in out["segments"] for i in seg["inputs"] if i["as_of"]
    )


def test_calendar_null_is_declared(tmp_path):
    out = cw.window_state(root=tmp_path)
    assert out["calendar"] == {"available": False, "reason": "no_upcoming_deal_calendar_source"}
    assert out["research_only"] is True


def test_no_issuer_identity_or_par_fields(tmp_path):
    _write_series(tmp_path / "fred" / f"{cw.FRED_HY}.parquet", [3.0] * 260)
    _write_series(tmp_path / "fred" / f"{cw.FRED_IG}.parquet", [1.0] * 260)
    _write_close(tmp_path / "yahoo" / f"{cw.MOVE_TICKER}.parquet", [80.0] * 260)
    out = cw.window_state(root=tmp_path)
    banned = {"issuer", "issuer_name", "isin", "cusip", "ticker", "par", "notional",
              "holdings", "name_match"}

    def walk(node):
        if isinstance(node, dict):
            for k, v in node.items():
                assert k not in banned
                walk(v)
        elif isinstance(node, list):
            for v in node:
                walk(v)

    walk(out)


def test_module_is_pure_and_writes_nothing(tmp_path):
    _write_series(tmp_path / "fred" / f"{cw.FRED_HY}.parquet", [3.0] * 260)
    before = sorted(p.relative_to(tmp_path).as_posix() for p in tmp_path.rglob("*") if p.is_file())
    cw.window_state(root=tmp_path)
    after = sorted(p.relative_to(tmp_path).as_posix() for p in tmp_path.rglob("*") if p.is_file())
    assert before == after


def test_not_imported_by_any_scoring_module():
    import ast
    import pathlib

    root = pathlib.Path(__file__).resolve().parent.parent
    scoring_dirs = [root / "engine"]
    hits = []
    for d in scoring_dirs:
        for f in d.glob("*.py"):
            if f.name in ("credit_window.py",):
                continue
            if "score" not in f.name and "regime" not in f.name and "axis" not in f.name:
                continue
            try:
                tree = ast.parse(f.read_text())
            except Exception:  # noqa: BLE001
                continue
            for node in ast.walk(tree):
                if isinstance(node, ast.ImportFrom) and node.module and "credit_window" in node.module:
                    hits.append(f.name)
                if isinstance(node, ast.Import):
                    for alias in node.names:
                        if "credit_window" in alias.name:
                            hits.append(f.name)
    assert hits == []


def test_rail_absent_when_spread_range_unknown(tmp_path):
    _write_close(tmp_path / "yahoo" / f"{cw.MOVE_TICKER}.parquet", [80.0] * 260)
    out = cw.window_state(root=tmp_path)
    for seg in out["segments"]:
        assert seg["rail"] is None


# --------------------------------------------------------------------------- #
# MAJOR 4 — _band_width must read `state` and use the right constants per key
# --------------------------------------------------------------------------- #
def test_band_width_reads_state_not_just_key():
    # A neutral rates_vol band is 35.0 wide (MOVE_SHUT_PCT - MOVE_OPEN_PCT),
    # not 33.0 (spread_range's neutral band) — the pre-fix bug returned the
    # RANGE_* constant for both keys regardless of state.
    assert cw._band_width("rates_vol", "neutral") == pytest.approx(35.0)
    assert cw._band_width("spread_range", "neutral") == pytest.approx(33.0)
    assert cw._band_width("spread_drift", "neutral") == pytest.approx(40.0)
    # open/shut bands are the unbounded sentinel, and must differ from the
    # neutral band width — the pre-fix bug made them identical.
    assert cw._band_width("spread_range", "open") != cw._band_width("spread_range", "neutral")
    assert cw._band_width("rates_vol", "shut") == cw._band_width("rates_vol", "open")


def test_choose_change_prefers_bounded_neutral_candidate_over_sentinel_open_shut_candidate(monkeypatch):
    # MINOR-1 (review repair round 4): `_band_width`'s docstring says a value
    # deep in an open/shut band "is never chosen as the input closest to
    # flipping", but the pre-fix `_choose_change` computed
    # `dist = raw_diff / width` — dividing by the 1.0e6 sentinel makes an
    # open/shut-origin candidate's distance TINY, the exact opposite of
    # "never chosen". Verified by exhaustive enumeration that today's 64
    # reachable (key, state) combinations never actually produce a candidate
    # SET that mixes a bounded (genuine neutral-band) candidate with a
    # sentinel (open/shut-origin) one, so the inversion is currently inert —
    # this test stubs `_next_threshold` / `segment_state` to construct that
    # mixed set directly, so the ranking contract is pinned even though no
    # real input shape exercises it today.
    inputs = [
        {"key": "spread_range", "value": 50.0, "state": "neutral"},  # bounded: raw 16, width 33 -> dist ~0.48
        {"key": "rates_vol", "value": 20.0, "state": "open"},        # sentinel: raw 1 (tiny!)
    ]

    def fake_next_threshold(key, state):
        if key == "spread_range":
            return [(66.0, "shut", "up")]
        if key == "rates_vol":
            return [(21.0, "neutral", "up")]
        return []

    def fake_segment_state(states):
        return ("changed", 2, False)  # always "different from original" -> both candidates valid

    monkeypatch.setattr(cw, "_next_threshold", fake_next_threshold)
    monkeypatch.setattr(cw, "segment_state", fake_segment_state)
    change = cw._choose_change(inputs, "orig")
    assert change is not None
    # the bounded candidate (spread_range) must win despite its larger RAW
    # distance (16 vs 1) — the sentinel candidate's tiny raw gap must never
    # let it jump the queue ahead of a genuine bounded-band candidate.
    assert change["input"] == "spread_range"


def test_next_threshold_open_and_shut_directions():
    # open/shut states have exactly ONE adjacent boundary (back into neutral) —
    # there is nothing beyond the extreme, so these are unchanged by the
    # round-3 fix below; the return type is now a list, never a bare tuple.
    assert cw._next_threshold("spread_range", "open") == [(cw.RANGE_OPEN_PCT, "neutral", "up")]
    assert cw._next_threshold("rates_vol", "shut") == [(cw.MOVE_SHUT_PCT, "neutral", "down")]
    assert cw._next_threshold("unknown_key", "open") == []
    assert cw._next_threshold("spread_range", "unknown") == []


# --------------------------------------------------------------------------- #
# BLOCKER (review repair round 3) — a "neutral" input has TWO adjacent
# boundaries (up into "shut", down into "open"), not one. The pre-fix
# `_next_threshold` returned only the shut-side crossing for a neutral input,
# so `_choose_change` could never name an open-side flip even when it would
# actually move the segment majority — see test_choose_change_finds_open_side_
# candidate_for_live_hy_shape below for the exact live counterexample.
# --------------------------------------------------------------------------- #
def test_next_threshold_neutral_returns_both_the_shut_side_and_open_side_boundary():
    assert cw._next_threshold("spread_range", "neutral") == [
        (cw.RANGE_SHUT_PCT, "shut", "up"), (cw.RANGE_OPEN_PCT, "open", "down"),
    ]
    assert cw._next_threshold("rates_vol", "neutral") == [
        (cw.MOVE_SHUT_PCT, "shut", "up"), (cw.MOVE_OPEN_PCT, "open", "down"),
    ]
    assert cw._next_threshold("spread_drift", "neutral") == [
        (cw.DRIFT_SHUT_BP, "shut", "up"), (cw.DRIFT_OPEN_BP, "open", "down"),
    ]


# --------------------------------------------------------------------------- #
# BLOCKER 3 — the "what would change this read" line must only name an input
# whose flip would actually flip the SEGMENT, never just the input.
# --------------------------------------------------------------------------- #
def test_choose_change_never_names_a_flip_that_does_not_move_the_segment():
    # Exact counterexample from the review: spread_range=10 (open),
    # spread_drift=-30 (open), rates_vol=74 (neutral, 1pt from shut at 75).
    # segment_state(['open','open','neutral']) is 'open' with n_open=2, and
    # flipping rates_vol alone to 'shut' gives ['open','open','shut'] which
    # is STILL 'open' (n_open=2 > n_shut=1) — so rates_vol must never be
    # offered as "what would change this read".
    inputs = [
        {"key": "spread_range", "value": 10.0, "state": "open"},
        {"key": "spread_drift", "value": -30.0, "state": "open"},
        {"key": "rates_vol", "value": 74.0, "state": "neutral"},
    ]
    change = cw._choose_change(inputs, "open")
    assert change is None or change["input"] != "rates_vol"


def test_choose_change_names_an_input_whose_flip_moves_the_segment():
    # One open, one neutral-near-shut, one shut: flipping the neutral input
    # to shut DOES flip the segment (neutral -> shut), so it is a legitimate
    # candidate.
    inputs = [
        {"key": "spread_range", "value": 10.0, "state": "open"},
        {"key": "spread_drift", "value": 24.0, "state": "neutral"},
        {"key": "rates_vol", "value": 76.0, "state": "shut"},
    ]
    change = cw._choose_change(inputs, "neutral")
    assert change is not None
    assert change["input"] == "spread_drift"
    assert change["to_state"] == "shut"
    assert change["segment_to"] == "shut"


def test_choose_change_returns_none_when_no_flip_moves_the_segment():
    inputs = [
        {"key": "spread_range", "value": None, "state": "unknown"},
        {"key": "spread_drift", "value": None, "state": "unknown"},
        {"key": "rates_vol", "value": None, "state": "unknown"},
    ]
    assert cw._choose_change(inputs, "not_evaluable") is None


def test_choose_change_finds_open_side_candidate_for_live_hy_shape():
    # BLOCKER (round 3): exact live shape read off the committed dark/en/desktop
    # PNG. HY today = [spread_range=open, spread_drift=neutral, rates_vol=neutral].
    # segment_state(['open','neutral','neutral']) is 'neutral' (n_open=1, not >=2).
    # Flipping EITHER spread_drift OR rates_vol from neutral to open gives
    # ['open','open','neutral'] -> n_open=2 > n_shut=0 -> segment 'open': two of
    # the three inputs are one threshold-crossing from flipping the headline in
    # the open direction. The pre-fix _next_threshold only ever returned the
    # shut-side boundary for a neutral input, so this candidate could never be
    # found and change=None rendered the false "nothing is close to flipping"
    # copy on a read where two-thirds of the inputs were, in fact, close.
    inputs = [
        {"key": "spread_range", "value": 10.0, "state": "open"},
        {"key": "spread_drift", "value": 10.0, "state": "neutral"},
        {"key": "rates_vol", "value": 70.0, "state": "neutral"},
    ]
    change = cw._choose_change(inputs, "neutral")
    assert change is not None
    assert change["to_state"] == "open"
    assert change["segment_to"] == "open"
    assert change["input"] == "spread_drift"  # nearer of the two valid open-side candidates


# --------------------------------------------------------------------------- #
# MAJOR-1 (review repair round 4) — the exact live counterexample measured by
# the round-4 review: HY = [spread_range=open(10.0), spread_drift=neutral(5.0),
# rates_vol=open(20.0)]. segment_state(['open','neutral','open']) is 'open'
# (n_open=2 > n_shut=0). Flipping rates_vol from 'open' to 'neutral' gives
# ['open','neutral','neutral'] -> n_open=1 -> segment 'neutral', which differs
# from 'open', so rates_vol is a valid candidate — and it is the nearest one
# (20 units from the 40 threshold vs. spread_range's 23 units from its 33
# threshold). The crossing direction is "up" (rates_vol RISING to 40), not
# "down" — this pins the engine side of the MAJOR-1 fix so the render-side
# tests in tests/test_ipo.py have a correctly-signed `direction` to render.
# --------------------------------------------------------------------------- #
def test_choose_change_rates_vol_up_direction_candidate_for_live_hy_open_shape():
    inputs = [
        {"key": "spread_range", "value": 10.0, "state": "open"},
        {"key": "spread_drift", "value": 5.0, "state": "neutral"},
        {"key": "rates_vol", "value": 20.0, "state": "open"},
    ]
    change = cw._choose_change(inputs, "open")
    assert change is not None
    assert change["input"] == "rates_vol"
    assert change["to_state"] == "neutral"
    assert change["direction"] == "up"
    assert change["threshold"] == pytest.approx(40.0)
    assert change["current"] == pytest.approx(20.0)
    assert change["segment_to"] == "neutral"


# --------------------------------------------------------------------------- #
# MAJOR 5 — a handful of observations must not render a full "past year" read
# --------------------------------------------------------------------------- #
def test_pct_rank_last_requires_minimum_history():
    short = pd.Series([1.0, 2.0, 3.0, 4.0])
    assert cw._pct_rank_last(short, cw.RANGE_WINDOW) is None
    long = pd.Series(range(cw.MIN_HISTORY + 5), dtype=float)
    assert cw._pct_rank_last(long, cw.RANGE_WINDOW) is not None


def test_window_state_four_observations_is_not_evaluable(tmp_path):
    _write_series(tmp_path / "fred" / f"{cw.FRED_HY}.parquet", [3.0, 3.1, 3.0, 2.9])
    out = cw.window_state(root=tmp_path)
    hy = [s for s in out["segments"] if s["key"] == "hy"][0]
    # spread_range needs MIN_HISTORY obs; spread_drift needs DRIFT_WINDOW+1 (22);
    # with only 4 rows neither is readable, so the segment must not render a
    # confident state off 4 observations.
    assert hy["state"] == "not_evaluable"


# --------------------------------------------------------------------------- #
# MAJOR 6 — a stale underlying series must not back a confident verdict
# --------------------------------------------------------------------------- #
def test_stale_series_is_unreadable_not_confident(tmp_path):
    stale_end = pd.Timestamp.now().normalize() - pd.Timedelta(days=400)
    _write_series(tmp_path / "fred" / f"{cw.FRED_HY}.parquet", [3.0] * 260, end=stale_end)
    _write_series(tmp_path / "fred" / f"{cw.FRED_IG}.parquet", [1.0] * 260)  # fresh
    _write_close(tmp_path / "yahoo" / f"{cw.MOVE_TICKER}.parquet", [80.0] * 260)  # fresh
    out = cw.window_state(root=tmp_path)
    hy = [s for s in out["segments"] if s["key"] == "hy"][0]
    hy_spread_inputs = [i for i in hy["inputs"] if i["key"] in ("spread_range", "spread_drift")]
    for inp in hy_spread_inputs:
        assert inp["state"] == "unknown"
    # the stale as_of is still surfaced (never hidden), just not trusted for a verdict
    assert hy["inputs"][0]["as_of"] is not None
    assert cw._is_stale(hy["inputs"][0]["as_of"])


def test_is_stale_threshold():
    fresh = pd.Timestamp.now(tz="UTC").strftime("%Y-%m-%d")
    old = (pd.Timestamp.now(tz="UTC") - pd.Timedelta(days=400)).strftime("%Y-%m-%d")
    assert cw._is_stale(fresh) is False
    assert cw._is_stale(old) is True
    assert cw._is_stale(None) is False


# --------------------------------------------------------------------------- #
# BLOCKER 1 — the MOVE path must be the file the repo actually tracks and
# actively maintains (data/yahoo/_MOVE.parquet), not a hand-built guess that
# happens to also exist as a stale, unmaintained file (data/yahoo/MOVE.parquet,
# no underscore). A hand-built path that resolves to SOME file on disk is a
# silent wrong-file bug, not a crash — this test pins the real tracked path so
# it cannot regress back to the stale file without a red test.
# --------------------------------------------------------------------------- #
def test_move_path_is_tracked_in_repo():
    import subprocess
    import pathlib

    root = pathlib.Path(__file__).resolve().parent.parent
    tracked = subprocess.check_output(
        ["git", "ls-files", "--", "data/yahoo", "data/fred", "data/archive"],
        cwd=root,
    ).decode().splitlines()
    assert f"data/yahoo/{cw.MOVE_TICKER}.parquet" in tracked
    assert f"data/fred/{cw.FRED_HY}.parquet" in tracked or f"data/archive/{cw.FRED_HY}.parquet" in tracked
    assert f"data/fred/{cw.FRED_IG}.parquet" in tracked or f"data/archive/{cw.FRED_IG}.parquet" in tracked
    # the pre-fix bug: an unprefixed "MOVE.parquet" also exists on disk (a
    # stale, unmaintained snapshot) — reading it instead of "_MOVE.parquet"
    # would not crash, it would silently read the wrong series.
    assert cw.MOVE_TICKER != "MOVE"
