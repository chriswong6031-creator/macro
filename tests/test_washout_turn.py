"""Tests for engine/washout_turn.py — washout_turn.v1 (WTN-W1).

Covers:
- a washout-depth weekly cross fires WASHOUT_TURN with the right since/depth receipts
- a MID-RANGE-depth terminal cross does NOT fire (the depth-read mutation pin)
- PIT: a cross living only on the CURRENT PARTIAL week does not fire; extending the
  same series through that Friday's close does (the completed-bars mutation pin)
- graduation (the line reclaims 0) and failure (2 consecutive negative hist bars),
  with the built-in 1-bar hysteresis
- TURN_WATCH on depth + a strictly rising histogram with no cross yet
- ledger lane gate (COLLECT_LANE) + keep-first idempotency
- compute() artifact shape, authority, disclosure, cohort/ticker agreement,
  skipped counting for a short-history symbol
- base rates: n < 8 → reason "insufficient_events" with null stats
- W2 history-deepening splice: prepend-only (an overlapping-date disagreement
  never changes the evaluated series; the recent end is never extended),
  boundary ratio-alignment, gap refusal, store-chain order (stocks then
  yahoo), no-deeper-store byte-identity, and the deep/signal leg split
  (depth + base rates read the deepened grid; state/since/indicator receipts
  read the preferred store only)

SYNTHETIC ONLY — no committed-data pins.  Every series is built from a weekly
close path anchored to a FIXED constant date and expanded onto business days, so
`resample("W-FRI").last()` reproduces the designed path exactly and nothing here
reads the wall clock (no date-bombs).
"""
from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import numpy as np
import pandas as pd
import pytest

from engine import canon
from engine.washout_turn import (
    AUTHORITY,
    DEPTH_PCTILE_MAX,
    DISCLOSURE,
    MAX_SPLICE_GAP_DAYS,
    MIN_HISTORY_EVENTS,
    MIN_WEEKLY_BARS,
    SCHEMA,
    STATE_TURN,
    STATE_WATCH,
    _base_rates,
    _completed_weekly,
    _deepen_close,
    _evaluate,
    _has_consecutive_negative,
    _load_ledger,
    _splice_prepend,
    _stamp_ledger,
    compute,
    compute_symbol_washout,
    write_site_artifact,
)

# ---------------------------------------------------------------------------
# Synthetic tape construction
# ---------------------------------------------------------------------------

_ANCHOR_FRIDAY = "1990-01-05"   # a real Friday; the tape defines its own "today"


def _weekly_to_daily(weekly_vals, start: str = _ANCHOR_FRIDAY) -> pd.Series:
    """Expand a WEEKLY close path onto business days.

    Every Friday carries its designed weekly close and the intra-week days
    interpolate, so ``resample("W-FRI").last()`` reproduces the path exactly —
    which lets a test design an indicator shape instead of guessing at one.
    """
    vals = np.asarray(list(weekly_vals), dtype=float)
    span = pd.bdate_range(start, periods=len(vals) * 7 + 10, freq="B")
    fridays = pd.DatetimeIndex([d for d in span if d.weekday() == 4])[: len(vals)]
    assert len(fridays) == len(vals)
    idx = pd.bdate_range(fridays[0] - pd.Timedelta(days=4), fridays[-1], freq="B")
    s = pd.Series(np.nan, index=idx, dtype=float)
    s.loc[fridays] = vals
    s.iloc[0] = float(vals[0])
    return s.interpolate().ffill().bfill().rename("close")


def _oscillating_head(n: int = 620) -> np.ndarray:
    """A long, ordinary weekly history — mild uptrend with two cycle lengths."""
    t = np.arange(n, dtype=float)
    return 100.0 * np.exp(0.0008 * t) * (
        1.0 + 0.11 * np.sin(2 * np.pi * t / 45.0) + 0.06 * np.sin(2 * np.pi * t / 13.0)
    )


def _deep_washout_weekly(
    n_head: int = 620, n_dec: int = 55, drift: float = -0.015,
    amp: float = 0.030, period: float = 6.0, seed: int = 23,
) -> np.ndarray:
    """Ordinary history, then a NOISY grinding decline into the deepest weekly
    RSI-MACD line of the whole series.

    The noise is deliberate: a perfectly monotone decline pins RSI at ~0 and
    leaves the histogram no room to flip back negative, which would make the
    hysteresis pin below untestable.  Seeded RandomState → deterministic.
    """
    head = _oscillating_head(n_head)
    rs = np.random.RandomState(seed)
    i = np.arange(n_dec, dtype=float)
    rets = drift + amp * np.sin(2 * np.pi * i / period) + rs.normal(0, 0.012, n_dec)
    v = [float(head[-1])]
    for r in rets:
        v.append(v[-1] * (1.0 + r))
    return np.concatenate([head, np.asarray(v[1:], dtype=float)])


def _weekly_line(close: pd.Series):
    """The organ's own view: completed weekly bars → canon line/sig (warm-up dropped)."""
    wk = _completed_weekly(close)
    line, sig = canon.rsi_macd(wk)
    ok = line.notna() & sig.notna()
    return wk, line[ok], sig[ok]


def _qualifying_crosses(close: pd.Series) -> tuple[pd.Series, pd.Series, list[int]]:
    """Bar indices of every bullish cross at or below the depth gate."""
    _wk, line, sig = _weekly_line(close)
    n = len(line)
    lv = line.to_numpy(dtype=float)
    cx = canon.crossover(line, sig)
    qual = [
        i for i in range(n)
        if bool(cx.iloc[i]) and 100.0 * float((lv < lv[i]).sum()) / n <= DEPTH_PCTILE_MAX
    ]
    return line, sig, qual


def _all_cross_depths(close: pd.Series) -> list[tuple[int, float]]:
    _wk, line, sig = _weekly_line(close)
    n = len(line)
    lv = line.to_numpy(dtype=float)
    cx = canon.crossover(line, sig)
    return [
        (i, 100.0 * float((lv < lv[i]).sum()) / n)
        for i in range(n) if bool(cx.iloc[i])
    ]


def _deep_washout_then_turn() -> pd.Series:
    """Deep-washout tape TRUNCATED so the qualifying cross is the LAST completed bar."""
    raw = _weekly_to_daily(_deep_washout_weekly())
    line, _sig, qual = _qualifying_crosses(raw)
    assert qual, "generator must produce a washout-depth cross"
    return raw[raw.index <= line.index[qual[-1]]]


def _extend_weeks(close: pd.Series, weekly_rets) -> pd.Series:
    """Append whole weeks with the given weekly returns (weekly grid, exact)."""
    vals = _completed_weekly(close).to_numpy(dtype=float).tolist()
    last = vals[-1]
    for r in weekly_rets:
        last = last * (1.0 + float(r))
        vals.append(last)
    return _weekly_to_daily(vals)


def _midrange_cross(seed: int = 13, n: int = 760,
                    crash_at: int = 180, crash_n: int = 55) -> pd.Series:
    """A tape whose DEEP crosses are all in the distant past and whose TERMINAL
    cross sits at mid-range depth — truncated so that cross is the last bar.

    A mutant that drops (or widens) the depth gate fires on this series; the
    real organ must not.
    """
    rs = np.random.RandomState(seed)
    t = np.arange(n, dtype=float)
    base = 100.0 * np.exp(0.0006 * t) * (
        1.0 + 0.09 * np.sin(2 * np.pi * t / 41.0) + 0.05 * np.sin(2 * np.pi * t / 13.0)
    )
    rets = np.concatenate([[0.0], np.diff(np.log(base))])
    rets[crash_at:crash_at + crash_n] = -0.022 + rs.normal(0, 0.010, crash_n)
    rets[crash_at + crash_n:crash_at + crash_n + 45] = 0.020 + rs.normal(0, 0.010, 45)
    raw = _weekly_to_daily(100.0 * np.exp(np.cumsum(rets)))
    depths = _all_cross_depths(raw)
    assert depths, "generator must produce crosses"
    _wk, line, _sig = _weekly_line(raw)
    return raw[raw.index <= line.index[depths[-1][0]]]


def _short_history(n_weeks: int = 80) -> pd.Series:
    """Fewer than MIN_WEEKLY_BARS completed weeks — must be counted SKIPPED."""
    return _weekly_to_daily(_oscillating_head(n_weeks))


# ---------------------------------------------------------------------------
# 1 — a deep cross fires WASHOUT_TURN with correct since / depth_pctile_at_cross
# ---------------------------------------------------------------------------

def test_deep_cross_fires_washout_turn():
    close = _deep_washout_then_turn()
    r = compute_symbol_washout(close)
    assert r is not None, "a washout-depth weekly cross must produce a state"
    assert r["state"] == STATE_TURN

    line, _sig, qual = _qualifying_crosses(close)
    c = qual[-1]
    n = len(line)
    lv = line.to_numpy(dtype=float)

    assert c == n - 1, "fixture: the qualifying cross is the last completed weekly bar"
    assert r["since"] == str(line.index[c].date())
    assert r["since"] == str(close.index[-1].date())
    assert r["weeks_since_cross"] == 0

    expected_depth = round(100.0 * float((lv < lv[c]).sum()) / n, 1)
    assert r["depth_pctile_at_cross"] == expected_depth
    assert r["depth_pctile_at_cross"] <= DEPTH_PCTILE_MAX
    assert r["depth_pctile"] == r["depth_pctile_at_cross"]  # cross IS the current bar

    # receipts are populated, not placeholders
    assert isinstance(r["weekly_cb"], bool)
    assert r["line"] is not None and r["sig"] is not None and r["hist"] is not None
    assert r["stoch_k"] is not None and r["stoch_d"] is not None
    assert r["drawdown_pct"] is not None and r["drawdown_pct"] <= 0
    assert r["data_through"] == str(close.index[-1].date())
    assert r["history_weeks"] == n
    assert r["history_start"] == str(line.index[0].date())
    assert r["history"]["n"] == len(qual)


# ---------------------------------------------------------------------------
# 2 — MUTATION PIN: a terminal cross at mid-range depth must NOT fire
# ---------------------------------------------------------------------------

def test_midrange_depth_cross_does_not_fire():
    """Kills a mutant that drops the depth gate (or widens it toward 100)."""
    close = _midrange_cross()
    depths = _all_cross_depths(close)
    _wk, line, _sig = _weekly_line(close)

    last_i, last_depth = depths[-1]
    assert last_i == len(line) - 1, "fixture: the terminal cross is the last bar"
    assert last_depth > DEPTH_PCTILE_MAX, (
        f"fixture is mis-built: terminal cross depth {last_depth:.2f} is inside the gate"
    )
    assert min(d for _i, d in depths) <= DEPTH_PCTILE_MAX, (
        "fixture must still CONTAIN deep crosses, so only the DEPTH READ can explain "
        "the null (not an absence of crosses)"
    )

    r = compute_symbol_washout(close)
    assert r is None or r["state"] != STATE_TURN, (
        "a mid-range-depth cross must never read as a washout turn"
    )


# ---------------------------------------------------------------------------
# 3 — MUTATION PIN (PIT): the partial trailing week is not a bar
# ---------------------------------------------------------------------------

def test_partial_week_cross_is_not_counted_until_friday_closes():
    """Kills a mutant that resamples W-FRI without dropping the partial bar."""
    fri = _deep_washout_then_turn()                 # ends ON the cross Friday
    assert fri.index[-1].weekday() == 4
    wed = fri.iloc[:-2]                             # same tape, ends that Wednesday
    assert wed.index[-1].weekday() == 2
    assert (fri.index[-1] - wed.index[-1]).days == 2

    wk_fri, _l, _s = _weekly_line(fri)
    wk_wed = _completed_weekly(wed)
    assert wk_fri.index[-1].date() == fri.index[-1].date(), (
        "a series ending ON a Friday keeps that COMPLETED weekly bar"
    )
    assert wk_wed.index[-1].date() <= wed.index[-1].date(), (
        "no weekly bar may be dated after the last traded session"
    )
    assert len(wk_fri) == len(wk_wed) + 1

    r_fri = compute_symbol_washout(fri)
    r_wed = compute_symbol_washout(wed)
    assert r_fri is not None and r_fri["state"] == STATE_TURN
    assert r_fri["since"] == str(fri.index[-1].date())
    # the SAME cross is invisible while its week is still open
    assert r_wed is None or r_wed.get("state") != STATE_TURN
    assert r_wed is None or r_wed.get("since") != r_fri["since"]


# ---------------------------------------------------------------------------
# 4 — graduation: the line reclaims zero after the cross → no entry
# ---------------------------------------------------------------------------

def test_graduated_turn_leaves_the_cohort():
    close = _deep_washout_then_turn()
    assert compute_symbol_washout(close)["state"] == STATE_TURN

    grown = _extend_weeks(close, [0.06] * 30)
    _wk, gline, _gsig = _weekly_line(grown)
    assert float(gline.iloc[-1]) >= 0.0, "fixture must actually reclaim zero"

    res = _evaluate(grown)
    assert res["state"] != STATE_TURN, (
        "once the line reclaims zero the trend lenses own it — not this watch lane"
    )
    assert res["state"] is None and res["none_reason"] == "graduated"
    assert compute_symbol_washout(grown) is None


# ---------------------------------------------------------------------------
# 5 — failure + the built-in 1-bar hysteresis
# ---------------------------------------------------------------------------

def _neg_run_after_last_qualifying_cross(close: pd.Series) -> int:
    line, sig, qual = _qualifying_crosses(close)
    h = (line - sig).to_numpy(dtype=float)[qual[-1] + 1:]
    run = best = 0
    for v in h:
        run = run + 1 if (np.isfinite(v) and v < 0) else 0
        best = max(best, run)
    return best


def test_one_negative_hist_bar_holds_two_consecutive_drops():
    # unit-level pin on the run detector the state machine uses
    assert _has_consecutive_negative(np.array([0.1, -0.2, 0.3, -0.1]), 2) is False
    assert _has_consecutive_negative(np.array([0.1, -0.2, -0.3, 0.4]), 2) is True
    assert _has_consecutive_negative(np.array([np.nan, -0.2, np.nan, -0.3]), 2) is False

    close = _deep_washout_then_turn()
    assert compute_symbol_washout(close)["state"] == STATE_TURN

    one_bad = _extend_weeks(close, [-0.20])
    two_bad = _extend_weeks(close, [-0.20, -0.20])

    assert _neg_run_after_last_qualifying_cross(one_bad) == 1, (
        "fixture: exactly ONE negative histogram bar after the cross"
    )
    assert _neg_run_after_last_qualifying_cross(two_bad) >= 2, (
        "fixture: TWO consecutive negative histogram bars after the cross"
    )

    r1 = compute_symbol_washout(one_bad)
    assert r1 is not None and r1["state"] == STATE_TURN, (
        "a single negative histogram bar must be absorbed (1-bar hysteresis)"
    )
    r2 = _evaluate(two_bad)
    assert r2["state"] != STATE_TURN, (
        "two consecutive negative histogram bars must fail the attempt"
    )
    assert r2["none_reason"] == "failed"


# ---------------------------------------------------------------------------
# 6 — TURN_WATCH: depth + strictly rising histogram, no cross yet
# ---------------------------------------------------------------------------

def test_turn_watch_fires_on_depth_and_rising_hist_without_a_cross():
    """The week BEFORE the qualifying cross: still below signal, already curling up."""
    full = _deep_washout_then_turn()
    weekly = _completed_weekly(full)
    pre = full[full.index <= weekly.index[-2]]      # drop the cross week entirely

    res = _evaluate(pre)
    assert res["state"] == STATE_WATCH, (
        "a deep base with a strictly rising histogram is the watch state"
    )
    r = res["receipts"]
    assert r["state"] == STATE_WATCH
    assert r["since"] is None and r["weeks_since_cross"] is None
    assert r["depth_pctile_at_cross"] is None
    assert r["weekly_cb"] is False
    assert r["depth_pctile"] <= DEPTH_PCTILE_MAX

    _wk, line, sig = _weekly_line(pre)
    h = (line - sig).to_numpy(dtype=float)
    assert h[-1] < 0, "TURN_WATCH requires the histogram to still be NEGATIVE"
    assert h[-1] > h[-2] > h[-3], "TURN_WATCH requires a STRICTLY rising histogram"


# ---------------------------------------------------------------------------
# 7 — ledger gate + keep-first idempotency
# ---------------------------------------------------------------------------

def _row(sym: str, session: str, state: str) -> dict:
    return {"session": session, "symbol": sym, "state": state,
            "prior_state": "NONE", "since": session, "depth_pctile": 4.2,
            "line": -8.0, "hist": 0.02, "data_through": session, "reason": None}


def test_ledger_is_dark_without_the_nightly_lane(tmp_path, monkeypatch):
    monkeypatch.delenv("COLLECT_LANE", raising=False)
    monkeypatch.delenv("US_LANE", raising=False)
    assert _stamp_ledger([_row("AAA", "2026-07-31", STATE_TURN)], tmp_path) == 0
    assert not (tmp_path / "washout_turn" / "ledger.jsonl").exists()
    assert _load_ledger(tmp_path) == []


def test_ledger_appends_transitions_and_is_idempotent(tmp_path, monkeypatch):
    monkeypatch.setenv("COLLECT_LANE", "nightly")

    rows = [_row("AAA", "2026-07-31", STATE_TURN), _row("BBB", "2026-07-31", STATE_WATCH)]
    assert _stamp_ledger(rows, tmp_path) == 2
    p = tmp_path / "washout_turn" / "ledger.jsonl"
    assert p.exists()
    assert len(_load_ledger(tmp_path)) == 2

    # keep-FIRST: re-running the same session appends nothing and rewrites nothing
    mutated = [dict(rows[0], depth_pctile=99.9), dict(rows[1], depth_pctile=99.9)]
    assert _stamp_ledger(mutated, tmp_path) == 0
    stored = _load_ledger(tmp_path)
    assert len(stored) == 2
    assert {r["depth_pctile"] for r in stored} == {4.2}

    # a LATER session for the same symbol is a new row (X → NONE carries its reason)
    drop = dict(_row("AAA", "2026-08-07", "NONE"),
                prior_state=STATE_TURN, reason="graduated")
    assert _stamp_ledger([drop], tmp_path) == 1
    stored = _load_ledger(tmp_path)
    assert len(stored) == 3
    assert stored[-1]["state"] == "NONE"
    assert stored[-1]["prior_state"] == STATE_TURN
    assert stored[-1]["reason"] == "graduated"
    # the file is valid JSONL end to end
    for line in p.read_text().splitlines():
        if line.strip():
            json.loads(line)


def test_compute_writes_transition_rows_under_the_nightly_lane(tmp_path, monkeypatch):
    monkeypatch.setenv("COLLECT_LANE", "nightly")
    universe = {"DEEP": ["b1"]}
    closes = {"DEEP": _deep_washout_then_turn()}
    with patch("engine.washout_turn._build_universe", return_value=universe), \
         patch("engine.washout_turn._load_close", side_effect=lambda s, r=None: closes.get(s)):
        out = compute(data_root=tmp_path)
        rows = _load_ledger(tmp_path)
        assert len(rows) == 1
        assert rows[0]["symbol"] == "DEEP"
        assert rows[0]["state"] == STATE_TURN
        assert rows[0]["prior_state"] == "NONE"
        assert rows[0]["since"] == out["tickers"]["DEEP"]["since"]

        # a second pass in the SAME session is a no-op: state now matches the ledger
        compute(data_root=tmp_path)
        assert len(_load_ledger(tmp_path)) == 1


# ---------------------------------------------------------------------------
# 8 — compute() artifact shape
# ---------------------------------------------------------------------------

def test_compute_artifact_shape_and_skipped_counting(tmp_path, monkeypatch):
    monkeypatch.delenv("COLLECT_LANE", raising=False)
    monkeypatch.delenv("US_LANE", raising=False)

    universe = {"DEEP": ["b1"], "MIDR": ["b2"], "TINY": []}
    closes = {
        "DEEP": _deep_washout_then_turn(),
        "MIDR": _midrange_cross(),
        "TINY": _short_history(),          # < MIN_WEEKLY_BARS → skipped
    }

    with patch("engine.washout_turn._build_universe", return_value=universe), \
         patch("engine.washout_turn._load_close", side_effect=lambda s, r=None: closes.get(s)):
        out = compute(data_root=tmp_path)

    assert out["schema"] == SCHEMA
    assert out["tier"] == "display"
    assert out["authority"] == AUTHORITY
    assert out["disclosure"] == DISCLOSURE
    assert "ranks nothing" in out["disclosure"]
    assert isinstance(out["elapsed_s"], float)
    assert "error" not in out

    assert out["skipped_n"] == 1, "the short-history symbol must be counted skipped"
    assert out["universe_n"] == len(universe) - out["skipped_n"]
    assert "TINY" not in out["tickers"]

    cohort = out["cohort"]
    assert set(cohort) == {"turn", "watch"}
    assert cohort["turn"] == sorted(cohort["turn"])
    assert cohort["watch"] == sorted(cohort["watch"])
    # cohort lists and the tickers map are the same population — no drift
    assert sorted(cohort["turn"] + cohort["watch"]) == sorted(out["tickers"])
    for sym, row in out["tickers"].items():
        assert row["state"] in (STATE_TURN, STATE_WATCH)
        assert row["basket_ids"] == universe[sym]
    assert "DEEP" in cohort["turn"]

    # ledger stays dark outside the nightly lane
    assert not (tmp_path / "washout_turn" / "ledger.jsonl").exists()

    # the artifact round-trips as JSON to the expected path
    site_root = tmp_path / "site"
    written = write_site_artifact(out, site_root)
    assert written == site_root / "stockdata" / "washout_turn.json"
    reread = json.loads(written.read_text())
    assert reread["schema"] == SCHEMA
    assert reread["cohort"] == out["cohort"]
    assert reread["authority"] == AUTHORITY


def test_compute_never_raises_on_a_broken_universe(tmp_path):
    with patch("engine.washout_turn._build_universe", side_effect=RuntimeError("boom")):
        out = compute(data_root=tmp_path)
    assert out["schema"] == SCHEMA
    assert out["error"] == "boom"
    assert out["authority"] == AUTHORITY
    assert out["cohort"] == {"turn": [], "watch": []}


# ---------------------------------------------------------------------------
# 9 — base rates: the low-n null is PRINTED, never hidden
# ---------------------------------------------------------------------------

def test_base_rates_low_n_prints_the_null():
    # The threshold is pinned to the LITERAL 8 the surface copy promises — reading
    # it from the module would make this test move with the mutant it must catch.
    assert MIN_HISTORY_EVENTS == 8
    closes = np.linspace(100.0, 200.0, 200)
    out = _base_rates(closes, list(range(7)))
    assert out["n"] == 7
    assert out["reason"] == "insufficient_events"
    assert out["med_13w"] is None and out["med_26w"] is None
    assert out["win_13w"] is None and out["win_26w"] is None


def test_base_rates_summarise_once_there_are_enough_events():
    closes = np.linspace(100.0, 300.0, 400)      # strictly rising → every window a gain
    events = list(range(0, 8 * 20, 20))
    out = _base_rates(closes, events)
    assert out["n"] == len(events) == 8
    assert "reason" not in out
    assert out["win_13w"] == 100.0 and out["win_26w"] == 100.0
    assert out["med_13w"] > 0 and out["med_26w"] > out["med_13w"]


def test_base_rates_drop_immature_events_without_imputing():
    """Right-censored events are DROPPED from the medians — never filled with 0."""
    closes = np.linspace(100.0, 200.0, 60)
    events = list(range(0, 40, 5)) + [50, 58]    # the last two have no 26w window
    out = _base_rates(closes, events)
    assert out["n"] == len(events)
    assert out["med_26w"] is not None and out["med_26w"] > 0


# ---------------------------------------------------------------------------
# 10 — W2 history-deepening splice (prepend-only; depth/base-rate legs only)
# ---------------------------------------------------------------------------

def _bdate_series(start: str, periods: int, lo: float, hi: float) -> pd.Series:
    idx = pd.bdate_range(start, periods=periods, freq="B")
    return pd.Series(np.linspace(lo, hi, periods), index=idx, dtype=float)


def _deep_store_for(tape: pd.Series) -> pd.Series:
    """A deep-store double for the 1990-anchored tapes: ~7 years of ordinary
    history ending 1989-12-29 (3 calendar days before the tape starts), then
    the tape's own dates at a DIFFERENT adjustment level (×1.3) — a store that
    both deepens the history and disagrees on every overlapping date.
    """
    prefix = _weekly_to_daily(_oscillating_head(365) * 3.0, start="1983-01-07")
    assert (tape.index[0] - prefix.index[-1]).days <= MAX_SPLICE_GAP_DAYS
    return pd.concat([prefix, tape * 1.3])


def test_splice_is_prepend_only_and_never_extends_the_recent_end():
    preferred = _bdate_series("2014-01-06", 500, 50.0, 80.0)
    # Disagrees on EVERY overlapping date and runs PAST the preferred end —
    # the data/yahoo/ shape (it trades a few sessions ahead of the ohlcv store).
    deeper = _bdate_series("2010-01-04", 1700, 200.0, 260.0)
    assert deeper.index[-1] > preferred.index[-1]

    spliced = _splice_prepend(preferred, deeper)
    d0 = preferred.index[0]

    # Overlap: preferred values, byte-unchanged — the disagreement never leaks in.
    assert spliced.loc[spliced.index >= d0].equals(preferred)
    # Recent end: never extended.
    assert spliced.index[-1] == preferred.index[-1]
    # Old bars: present, ratio-aligned at the boundary.
    assert spliced.index[0] == deeper.index[0]
    factor = float(preferred.iloc[0]) / float(deeper.loc[d0])
    old_mask = spliced.index < d0
    assert np.allclose(spliced.loc[old_mask].to_numpy(),
                       (deeper.loc[deeper.index < d0] * factor).to_numpy())
    # The join preserves the deep store's own return into d0 (no fabricated jump).
    last_old = spliced.index[spliced.index < d0][-1]
    assert np.isclose(float(spliced.loc[d0]) / float(spliced.loc[last_old]),
                      float(deeper.loc[d0]) / float(deeper.loc[last_old]))
    # Idempotent: a second pass has nothing strictly before the spliced start.
    assert _splice_prepend(spliced, deeper) is spliced
    # A store that starts on the same date deepens nothing.
    assert _splice_prepend(preferred, preferred.copy()) is preferred


def test_splice_refuses_a_deep_store_that_never_reaches_the_boundary():
    preferred = _bdate_series("2014-01-06", 500, 50.0, 80.0)
    gapped = _bdate_series("2010-01-04", 900, 90.0, 120.0)   # ends mid-2013
    assert (preferred.index[0] - gapped.index[-1]).days > MAX_SPLICE_GAP_DAYS
    assert _splice_prepend(preferred, gapped) is preferred


def test_deep_legs_read_the_deepened_series_and_signal_legs_do_not():
    tape = _deep_washout_then_turn()
    deep = _splice_prepend(tape, _deep_store_for(tape))
    assert deep is not tape and deep.index[0].year == 1983

    rp = _evaluate(tape)
    rd = _evaluate(tape, deep)
    assert rp["deepened"] is False and rd["deepened"] is True
    p, q = rp["receipts"], rd["receipts"]

    # SIGNAL legs — state machine and every last-bar indicator receipt — are
    # byte-identical: the deepened series never touches the preferred store's
    # recent values (which the ×1.3 overlap disagreement would have moved).
    for key in ("state", "since", "weeks_since_cross", "line", "sig", "hist",
                "stoch_k", "stoch_d", "weekly_cb", "drawdown_pct", "data_through"):
        assert q[key] == p[key], key
    assert q["state"] == STATE_TURN

    # DEPTH + HISTORY legs read the deepened grid.
    _wk_d, line_d, _sig_d = _weekly_line(deep)
    assert q["history_weeks"] == len(line_d) > p["history_weeks"]
    assert q["history_start"] == str(line_d.index[0].date())
    # More history above the washout ⇒ the same cross sits DEEPER in its own
    # distribution (the MCD 8.6→6.3 direction).
    assert q["depth_pctile_at_cross"] < p["depth_pctile_at_cross"]
    assert q["depth_pctile_at_cross"] <= DEPTH_PCTILE_MAX

    # BASE RATES are the deep grid's qualifying-cross events, not the
    # preferred grid's (the two event sets genuinely differ on this fixture).
    _l0, _s0, qual_plain = _qualifying_crosses(tape)
    _l1, _s1, qual_deep = _qualifying_crosses(deep)
    assert len(qual_deep) != len(qual_plain)
    assert p["history"]["n"] == len(qual_plain)
    assert q["history"]["n"] == len(qual_deep)


def test_no_deeper_store_is_byte_identical(tmp_path):
    tape = _deep_washout_then_turn()
    # Empty data_root: no stocks/, no yahoo/ — the deepener returns the SAME
    # object, and the evaluation is exactly the pre-W2 evaluation.
    out = _deepen_close("NOSTORE", tape, tmp_path)
    assert out is tape
    assert _evaluate(tape, out) == _evaluate(tape)


def test_deepen_close_prefers_stocks_then_yahoo(tmp_path):
    close = _bdate_series("2014-01-06", 700, 50.0, 80.0)
    stocks = _bdate_series("2000-01-03", 4200, 30.0, 55.0)    # reaches past 2014
    yahoo = _bdate_series("1995-01-02", 5600, 20.0, 60.0)     # deeper than stocks
    for store, series in (("stocks", stocks), ("yahoo", yahoo)):
        (tmp_path / store).mkdir()
        pd.DataFrame({"close": series}).to_parquet(tmp_path / store / "SYM.parquet")

    both = _deepen_close("SYM", close, tmp_path)
    assert both.index[0] == stocks.index[0], "data/stocks wins even when yahoo is deeper"
    assert both.loc[both.index >= close.index[0]].equals(close)

    (tmp_path / "stocks" / "SYM.parquet").unlink()
    only_yahoo = _deepen_close("SYM", close, tmp_path)
    assert only_yahoo.index[0] == yahoo.index[0]


def test_compute_deepens_from_the_store_chain(tmp_path, monkeypatch):
    monkeypatch.delenv("COLLECT_LANE", raising=False)
    tape = _deep_washout_then_turn()
    universe = {"DEEP": ["b1"]}

    def _run(root: Path) -> dict:
        with patch("engine.washout_turn._build_universe", return_value=universe), \
             patch("engine.washout_turn._load_close",
                   side_effect=lambda s, r=None: tape):
            return compute(data_root=root)

    bare = tmp_path / "bare"
    bare.mkdir()
    out0 = _run(bare)
    assert out0["deepened_n"] == 0

    deep_root = tmp_path / "deep"
    (deep_root / "stocks").mkdir(parents=True)
    pd.DataFrame({"close": _deep_store_for(tape)}).to_parquet(
        deep_root / "stocks" / "DEEP.parquet")
    out1 = _run(deep_root)
    assert out1["deepened_n"] == 1

    r0, r1 = out0["tickers"]["DEEP"], out1["tickers"]["DEEP"]
    assert (r1["state"], r1["since"]) == (r0["state"], r0["since"])
    assert r1["history_weeks"] > r0["history_weeks"]
    assert r1["history_start"] < r0["history_start"]


# ---------------------------------------------------------------------------
# Guard rails — authority creep and the canon-only rule
# ---------------------------------------------------------------------------

def test_authority_block_is_all_false_display_tier():
    assert AUTHORITY["tier"] == "display"
    assert AUTHORITY["horizon_role"] == "context"
    for key in ("may_rank", "may_gate", "may_size", "may_escalate"):
        assert AUTHORITY[key] is False


def test_module_imports_canon_and_never_engine_technicals_rsi():
    """engine.technicals.rsi is a DIFFERENT rsi (bare ewm warm-up) — banned here."""
    src = Path(__file__).resolve().parents[1].joinpath("engine/washout_turn.py").read_text(
        encoding="utf-8"
    )
    assert "from engine.canon import" in src
    assert "from engine.technicals import" not in src
    assert "import engine.technicals" not in src
    # zero authority creep: no prophet/board/scoring imports
    for banned in ("engine.prophet", "us_board_rank", "engine.board", "name_score",
                   "stock_score", "entry_signal"):
        assert f"import {banned}" not in src


def test_short_history_is_insufficient_not_a_silent_none():
    short = _short_history()
    assert len(_completed_weekly(short)) < MIN_WEEKLY_BARS
    res = _evaluate(short)
    assert res["insufficient"] is True
    assert res["state"] is None
    assert compute_symbol_washout(short) is None


if __name__ == "__main__":  # pragma: no cover
    pytest.main([__file__, "-x", "-q"])
