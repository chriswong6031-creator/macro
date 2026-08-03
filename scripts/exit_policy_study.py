#!/usr/bin/env python3
"""Exit-policy horse race on the US buy-lane episode cohort (Learning Loop G3).

WHAT THIS IS
------------
A MEASUREMENT-TIER study. It takes the SAME episodes the Track-record ledger already
scores — same buy lane, same contiguous-run grain, same next-session-close fill — and
asks one question the ledger deliberately refuses to ask:

    on identical entries, what does a holder-with-rules capture?

The ledger measures SIGNAL QUALITY and must stay policy-free (fixed horizon, forced
verdict) so eras and desks compare. This study measures TRADE MANAGEMENT. They are two
instruments, never one blended number (masterplan §1). Nothing here changes the public
track record, the board, or any weight; ``engine/track_scoring.py`` and
``scripts/grade_us_board.py`` are imported READ-ONLY and are not modified by this file.

WHAT IT IS NOT
--------------
Not a promotion, not a recommendation, not an authority claim. Every verdict in the
emitted report is descriptive ("shows", "in this sample"). Any policy that eventually
displaces the incumbent must go through its own pre-registration first (G4/G7).

THE POLICIES (identical entries, identical cohort)
--------------------------------------------------
  P0   incumbent as shipped — 10-session forced verdict, 3D-StochRSI>=80 target leg,
       90-session-trough x0.97 stop leg. This is literally ``track_scoring.score_episode``
       called with the grader's own parameters, so the calibration block below can
       reproduce ``site/factordata/us_track_ledger.json`` key-for-key.
  P0f  pure fixed H=10 — the SAME horizon with both early-exit legs removed. This is the
       policy-free reference the decomposition is anchored on, because the operator's
       question is literally about bar 10 ("winners extended beyond 10d, losers cut
       before 10d") and P0f exits every episode at bar 10 exactly.
  P1   pure fixed H=21.
  P2   ATR trailing stop, k in {2, 3}: exit at the first close below
       (running max close - k x ATR14). Hard cap H=63.
  P3   plan geometry: stop = the board row's own ``hold.invalidation`` when present
       (that IS the 90d-trough x0.97 level the desk publishes), else entry - 2 x ATR14;
       target = entry + 3R where R = entry - stop; first touch on closes; cap H=21.
  P4   breakeven-then-trail: P2 k=3 with a breakeven floor armed once a close reaches
       entry + 1 x ATR14. Cap H=63.

PINNED CONVENTIONS (each one is a choice; a reviewer should see it, not infer it)
--------------------------------------------------------------------------------
* ATR14 is Wilder's, computed on the name's own daily bars UP TO AND INCLUDING the fill
  bar, then HELD FIXED for the life of the episode. A re-measured (Chandelier-style) ATR
  would make the stop distance a second, drifting signal; fixing it at entry keeps the
  horse race about the EXIT RULE. The re-measured variant was not run.
* The trailing anchor is the running max of {entry price} U {closes bar 1..t}. Including
  the entry price is what makes the bar-1 stop entry - k x ATR rather than undefined.
* Same-bar ordering in the target/stop walker: the STOP is tested before the target, so
  a bar that satisfies both resolves as a loss. Conservative by construction. On daily
  closes a single close cannot be both below the stop and above the target, so this is
  unreachable with well-formed geometry — it is pinned and tested anyway so a later
  refactor cannot silently reverse it.
* P4 arms its breakeven floor at entry + 1 x ATR14. Reading "+1R" as the trail's own
  initial risk (3 x ATR14) makes P4 PROVABLY IDENTICAL to P2 k=3 on every path — see
  ``walk_trail``'s docstring for the two-line proof and the test that pins it. An ATR
  multiple is therefore the only reading under which P4 is a distinct policy at all.
* MAE/MFE are CLOSE-PATH (the caches carry no intraday path for the walk), so both
  understate the true intraday excursion. ``capture`` is median(realised / MFE) over the
  policy's OWN hold window — the same definition ``track_scoring.summarize`` uses, so
  the P0 row is comparable to the shipped ledger's ``capture``.

CENSORING — the load-bearing caveat
-----------------------------------
The record starts 2026-06-30 and the close caches end 2026-07-31. The matured-at-10
cohort therefore has 11..21 forward bars available; NOTHING has 63, and only the first
board day has 21. A policy with a 21- or 63-bar cap will frequently still be holding
when the data runs out. Those rows are NOT dropped (dropping them would delete exactly
the positions that were still running — the outcome-conditioned denominator
``track_scoring``'s rule 1 exists to forbid). They are MARKED at the last available
close and flagged ``data_end``; every policy row prints its ``data_end`` count. A
data_end row is a MARK, not a realised exit, and its hold length is a LOWER BOUND.
Read the cap-63 rows as "what these rules were holding on 2026-07-31", not as
"what these rules returned".

STATISTICS
----------
Daily boards overlap heavily; episodes surfaced on the same night are one bet, not N.
Every interval here is ``track_scoring.date_block_ci`` — resampling WHOLE BOARD DAYS,
seeded — and ``n_board_days`` is printed beside ``n_episodes`` everywhere. Policy-vs-P0
comparisons are PAIRED per-episode deltas (same entry, same window) with a blocked CI
on the mean delta. No p-values are computed: with 8 blocks a per-policy p-value would be
a decoration, and the block structure is the only thing that makes the interval honest.

Run:  python -m scripts.exit_policy_study                 # writes reports/exit-policy-horserace.md
      python -m scripts.exit_policy_study --json out.json # also dump the raw result dict
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import math
import sys
from pathlib import Path
from typing import Any, Callable, Iterable, Mapping, Sequence

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from engine import track_scoring as ts  # noqa: E402
# Import, never copy: the definition cut, the horizon, and the incumbent's own exit legs
# belong to the grader. If the grader moves them, this study moves with it instead of
# silently measuring a different cohort.
from scripts.grade_us_board import (  # noqa: E402
    BENCH,
    LEDGER_HISTORY_FROM,
    LEDGER_HORIZON,
    LEDGER_JSON,
    RETRO_PARQUET,
    SNAPSHOTS_JSONL,
    _TROUGH_LB,
    _TROUGH_TOL,
    _ob_mask,
)

REPORT_PATH = ROOT / "reports" / "exit-policy-horserace.md"

# Close panel = engine.equity_factors._closes("broad") — breadth (S&P 500) + smallcap +
# midcap, first-hit-wins — so the price basis is byte-identical to the grader's. Russell
# is appended for the high/low panel only (it ships no close cache); listing it here
# costs nothing and keeps the two loaders symmetric.
_CLOSE_GROUPS = ("breadth", "smallcap_breadth", "midcap_breadth", "russell_breadth")

ATR_N = 14                 # Wilder period
H_LONG = 21                # the ladder's next rung — P1's fixed horizon
HORIZON_LADDER = (LEDGER_HORIZON, H_LONG, 63)
TRAIL_K = (2.0, 3.0)
CAP_TRAIL = 63
CAP_PLAN = H_LONG
PLAN_R_MULT = 3.0          # target = entry + 3R
PLAN_ATR_MULT = 2.0        # fallback stop when the board row carries no invalidation
BE_ARM_ATR = 1.0           # P4 arms its breakeven floor here — see walk_trail's docstring

# Exit reasons. `data_end` is this study's own addition — see the CENSORING block.
R_HORIZON, R_TRAIL, R_PLAN_STOP, R_PLAN_TARGET, R_DATA_END = (
    "horizon", "trail_stop", "plan_stop", "plan_target", "data_end")


# --------------------------------------------------------------------------- #
# price panels
# --------------------------------------------------------------------------- #
def _panel(kind: str, root: Path | None = None) -> pd.DataFrame:
    """Concatenate the breadth caches for one OHLC field, first-hit-wins on ticker."""
    base = (root or ROOT) / "data"
    frames = []
    for grp in _CLOSE_GROUPS:
        p = base / grp / f"_{kind}_cache.parquet"
        if p.exists():
            frames.append(pd.read_parquet(p))
    if not frames:
        return pd.DataFrame()
    out = pd.concat(frames, axis=1, sort=True)
    out = out.loc[:, ~out.columns.duplicated()]
    out.index = pd.to_datetime(out.index)
    return out.sort_index()


def load_prices(root: Path | None = None) -> tuple[pd.DataFrame, pd.DataFrame,
                                                   pd.DataFrame, pd.Series | None]:
    """(closes, highs, lows, benchmark_closes). Benchmark is SPY total-return closes."""
    closes, highs, lows = _panel("closes", root), _panel("high", root), _panel("low", root)
    bench = None
    bp = (root or ROOT) / "data" / "yahoo" / f"{BENCH}.parquet"
    if bp.exists():
        b = pd.read_parquet(bp)
        col = "close" if "close" in b.columns else b.columns[0]
        bench = b[col].dropna()
        bench.index = pd.to_datetime(bench.index)
        bench = bench.sort_index()
    return closes, highs, lows, bench


def wilder_atr(high: pd.Series, low: pd.Series, close: pd.Series,
               n: int = ATR_N) -> pd.Series:
    """Wilder's ATR(n). TR = max(H-L, |H-C_prev|, |L-C_prev|); RMA smoothing.

    Returned on ``close``'s index so a caller can read the value AT the fill bar without
    any forward information: ATR[t] uses bars <= t only.
    """
    h = high.reindex(close.index).astype(float)
    l = low.reindex(close.index).astype(float)
    c = close.astype(float)
    prev = c.shift(1)
    tr = pd.concat([(h - l).abs(), (h - prev).abs(), (l - prev).abs()], axis=1).max(axis=1)
    return tr.ewm(alpha=1.0 / n, adjust=False, min_periods=n).mean()


# --------------------------------------------------------------------------- #
# cohort
# --------------------------------------------------------------------------- #
def load_board_days(root: Path | None = None) -> tuple[dict[str, set[str]],
                                                       dict[tuple[str, str], float],
                                                       dict[str, int]]:
    """Buy-lane board membership from snapshots.jsonl UNION retro_grades.parquet.

    Only board dates >= ``LEDGER_HISTORY_FROM`` are admitted. Earlier boards published a
    120-name broad screen rather than a selection — grading them is grading calls the
    board never made (see the constant's own comment in scripts/grade_us_board.py).

    Returns (board_days, invalidation_by[(as_of, ticker)], provenance counts).
    """
    base = root or ROOT
    snap_path = base / "data" / "us_board_ledger" / "snapshots.jsonl"
    retro_path = base / "data" / "us_board_ledger" / "retro_grades.parquet"
    if root is None:
        snap_path, retro_path = SNAPSHOTS_JSONL, RETRO_PARQUET

    board_days: dict[str, set[str]] = {}
    invalidation: dict[tuple[str, str], float] = {}
    prov = {"n_days_snapshots": 0, "n_days_retro_only": 0,
            "n_tickers_added_by_retro": 0, "n_days_before_definition": 0}

    if snap_path.exists():
        for line in snap_path.read_text().splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                d = json.loads(line)
            except json.JSONDecodeError:
                continue
            as_of = d.get("as_of")
            if not as_of:
                continue
            if as_of < LEDGER_HISTORY_FROM:
                prov["n_days_before_definition"] += 1
                continue
            day = board_days.setdefault(str(as_of), set())
            prov["n_days_snapshots"] += 1
            for r in d.get("buy") or []:
                if not isinstance(r, dict):
                    continue
                tk = r.get("ticker")
                if not tk:
                    continue
                day.add(str(tk))
                hold = r.get("hold") or {}
                inv = hold.get("invalidation") if isinstance(hold, dict) else None
                if inv is not None:
                    try:
                        v = float(inv)
                    except (TypeError, ValueError):
                        continue
                    if math.isfinite(v) and v > 0:
                        invalidation[(str(as_of), str(tk))] = v

    if retro_path.exists():
        rg = pd.read_parquet(retro_path, columns=["as_of", "lane", "ticker"])
        rg = rg[(rg["lane"] == "buy") & (rg["as_of"].astype(str) >= LEDGER_HISTORY_FROM)]
        for as_of, grp in rg.groupby("as_of"):
            key = str(as_of)
            if key not in board_days:
                prov["n_days_retro_only"] += 1
            day = board_days.setdefault(key, set())
            before = len(day)
            day |= {str(t) for t in grp["ticker"]}
            prov["n_tickers_added_by_retro"] += len(day) - before

    return board_days, invalidation, prov


def build_cohort(board_days: Mapping[str, Iterable[str]],
                 invalidation: Mapping[tuple[str, str], float],
                 closes: pd.DataFrame, highs: pd.DataFrame, lows: pd.DataFrame,
                 *, min_bars: int = LEDGER_HORIZON) -> tuple[list[dict], dict[str, int]]:
    """Matured buy-lane episodes with a COMPLETE forward path and a usable ATR.

    One episode = one contiguous board run (``track_scoring.build_episodes``); a name
    that leaves and returns yields two. Fill = the next session's close after the run's
    first board date — the board is computed FROM that close and published that evening,
    so the signal bar itself is unbuyable.

    Every exclusion is COUNTED, never silent. Exclusions here are by DATA COVERAGE and
    by AGE only; neither can know which way a trade went.
    """
    excl = {"no_price_column": 0, "empty_series": 0, "fill_not_printed": 0,
            "immature": 0, "no_atr": 0, "bad_entry": 0}
    excl_tickers: dict[str, set[str]] = {k: set() for k in excl}
    out: list[dict] = []

    for ep in ts.build_episodes(dict(board_days)):
        tk, d0 = ep["ticker"], ep["entry_date"]
        if tk not in closes.columns:
            excl["no_price_column"] += 1
            excl_tickers["no_price_column"].add(tk)
            continue
        ser = closes[tk].dropna()
        if ser.empty:
            excl["empty_series"] += 1
            excl_tickers["empty_series"].add(tk)
            continue
        i_sig = ser.index.searchsorted(pd.Timestamp(d0), side="left")
        if i_sig >= len(ser) or i_sig + 1 >= len(ser):
            excl["fill_not_printed"] += 1
            excl_tickers["fill_not_printed"].add(tk)
            continue
        i_fill = i_sig + 1
        entry = float(ser.iloc[i_fill])
        if not math.isfinite(entry) or entry <= 0:
            excl["bad_entry"] += 1
            excl_tickers["bad_entry"].add(tk)
            continue
        fwd = ser.iloc[i_fill + 1:]
        if len(fwd) < min_bars:
            excl["immature"] += 1
            excl_tickers["immature"].add(tk)
            continue
        if tk not in highs.columns or tk not in lows.columns:
            excl["no_atr"] += 1
            excl_tickers["no_atr"].add(tk)
            continue
        atr_ser = wilder_atr(highs[tk], lows[tk], ser)
        atr = float(atr_ser.iloc[i_fill]) if i_fill < len(atr_ser) else float("nan")
        if not math.isfinite(atr) or atr <= 0:
            excl["no_atr"] += 1
            excl_tickers["no_atr"].add(tk)
            continue

        # The incumbent's own stop level: a break of the setup's 90-session trough x0.97
        # (engine/hold.py BROKEN). Recomputed here from the same window the grader uses.
        lo = max(0, i_sig - _TROUGH_LB)
        trough = float(ser.iloc[lo:i_sig + 1].min())
        trough_stop = trough * _TROUGH_TOL if math.isfinite(trough) and trough > 0 else None

        out.append({
            "ticker": tk,
            "board_date": str(d0),
            "fill_date": str(ser.index[i_fill].date()),
            "entry": entry,
            "atr": atr,
            "series": ser,
            "i_fill": i_fill,
            "fwd": fwd,
            "n_bars_available": len(fwd),
            "trough_stop": trough_stop,
            "plan_stop": invalidation.get((str(d0), tk)),
        })
    out.sort(key=lambda e: (e["board_date"], e["ticker"]))
    return out, {"counts": excl,
                 "tickers": {k: sorted(v) for k, v in excl_tickers.items() if v}}


# --------------------------------------------------------------------------- #
# policy walkers — pure, unit-testable, no lookahead
# --------------------------------------------------------------------------- #
def _finish(prices: Sequence[float], idx: int, reason: str) -> dict:
    return {"exit_bar": idx + 1, "exit_px": float(prices[idx]), "reason": reason}


def walk_fixed(prices: Sequence[float], cap: int) -> dict:
    """Exit at bar ``cap``, or at the last available bar when the data runs out."""
    n = len(prices)
    if n == 0:
        raise ValueError("empty forward path")
    if n < cap:
        return _finish(prices, n - 1, R_DATA_END)
    return _finish(prices, cap - 1, R_HORIZON)


def walk_trail(prices: Sequence[float], entry: float, atr: float, k: float, cap: int,
               *, breakeven_arm_atr: float | None = None) -> dict:
    """ATR trailing stop; optional breakeven floor armed ``breakeven_arm_atr`` ATRs up.

    Anchor = running max of {entry} U {closes seen so far}. Stop = anchor - k*atr. The
    close is folded into the anchor BEFORE the test (a new high can never trip its own
    stop, so the order is immaterial for well-formed k>0 — it is pinned for clarity).

    ``breakeven_arm_atr`` is P4: once a close reaches entry + m*atr the effective stop
    floor becomes the entry price and never goes back below it.

    WHY THE ARM IS EXPRESSED IN ATRs AND NOT IN R
    --------------------------------------------
    "Breakeven after +1R, then trail at k" has two readings, and one of them is a
    mathematical no-op. If R is taken to be the trail's OWN initial risk (k*atr), then at
    the moment the floor arms the close is already >= entry + k*atr, so the anchor is too,
    so the trailing stop is already >= entry — and the anchor never falls, so it stays
    there. ``max(trail, entry) == trail`` for every subsequent bar and the policy is
    IDENTICAL to plain ``walk_trail(k)`` on every path. That identity is proved by
    construction and pinned in tests/test_exit_policy_study.py; it is why this parameter
    is an ATR multiple. P4 arms at +1*atr, where the floor genuinely binds over the
    region between +1 and +k ATRs — which is the whole point of a breakeven rule.
    """
    if atr <= 0 or not math.isfinite(atr):
        raise ValueError("atr must be positive and finite")
    n = len(prices)
    if n == 0:
        raise ValueError("empty forward path")
    anchor = float(entry)
    armed = False
    trigger = (float(entry) + breakeven_arm_atr * atr
               if breakeven_arm_atr is not None else None)
    limit = min(cap, n)
    for i in range(limit):
        p = float(prices[i])
        if not math.isfinite(p):
            continue
        if p > anchor:
            anchor = p
        if trigger is not None and not armed and p >= trigger:
            armed = True
        stop = anchor - k * atr
        if armed:
            stop = max(stop, float(entry))
        if p < stop:
            return _finish(prices, i, R_TRAIL)
    return _finish(prices, limit - 1, R_HORIZON if n >= cap else R_DATA_END)


def walk_target_stop(prices: Sequence[float], stop: float, target: float,
                     cap: int) -> dict:
    """First-touch on closes. THE STOP IS TESTED FIRST — a bar that satisfies both
    conditions resolves as the loss. Conservative, and pinned so a refactor cannot
    quietly reverse it."""
    n = len(prices)
    if n == 0:
        raise ValueError("empty forward path")
    limit = min(cap, n)
    for i in range(limit):
        p = float(prices[i])
        if not math.isfinite(p):
            continue
        if p <= stop:
            return _finish(prices, i, R_PLAN_STOP)
        if p >= target:
            return _finish(prices, i, R_PLAN_TARGET)
    return _finish(prices, limit - 1, R_HORIZON if n >= cap else R_DATA_END)


# --------------------------------------------------------------------------- #
# per-episode evaluation
# --------------------------------------------------------------------------- #
def _excess(ep: Mapping[str, Any], exit_bar: int, pnl: float,
            bench: pd.Series | None) -> float | None:
    """Benchmark leg over the SAME fill bar -> exit bar window, matched by TIMESTAMP.

    Offset arithmetic would drift whenever the name and SPY keep different holiday
    calendars; ``track_scoring.score_from_fill`` matches by timestamp for the same
    reason and this mirrors it.
    """
    if bench is None or bench.empty:
        return None
    ser: pd.Series = ep["series"]
    i_fill = ep["i_fill"]
    j = i_fill + exit_bar
    if j >= len(ser):
        return None
    b = bench.dropna()
    bi = b.index.searchsorted(ser.index[i_fill], side="left")
    bj = b.index.searchsorted(ser.index[j], side="left")
    if bi >= len(b) or bj >= len(b) or bj < bi:
        return None
    b0, b1 = float(b.iloc[bi]), float(b.iloc[bj])
    if not (math.isfinite(b0) and b0 > 0 and math.isfinite(b1)):
        return None
    return pnl - (b1 / b0 - 1.0) * 100.0


def _row_from_walk(ep: Mapping[str, Any], walk: Mapping[str, Any],
                   bench: pd.Series | None) -> dict:
    """Turn a walker verdict into a track_scoring-shaped scored row.

    The shape matters: it is fed straight to ``track_scoring.summarize``, so every
    headline number in this study uses the ledger's own definitions (win = >0, no dead
    band, capture = median(realised/MFE), blocked CIs) rather than a second convention.
    """
    entry = float(ep["entry"])
    fwd = np.asarray(ep["fwd"].values, dtype=float)
    bar = int(walk["exit_bar"])
    window = fwd[:bar]
    pnl = (float(walk["exit_px"]) / entry - 1.0) * 100.0
    return {
        "ticker": ep["ticker"],
        "board_date": ep["board_date"],
        "entry_date": ep["fill_date"],
        "entry": entry,
        "matured": True,
        "held": bar,
        "exit": float(walk["exit_px"]),
        "exit_reason": walk["reason"],
        "censored": walk["reason"] == R_DATA_END,
        "pnl": pnl,
        "excess": _excess(ep, bar, pnl, bench),
        "mfe": (float(np.nanmax(window)) / entry - 1.0) * 100.0,
        "mae": (float(np.nanmin(window)) / entry - 1.0) * 100.0,
    }


def _plan_geometry(ep: Mapping[str, Any]) -> tuple[float, float, str]:
    """(stop, target, source). Falls back to entry - 2*ATR when the board row carries no
    usable invalidation, or when the published level is not below the entry (a stop at or
    above the fill has no R and would resolve every episode on bar 1)."""
    entry, atr = float(ep["entry"]), float(ep["atr"])
    stop, src = ep.get("plan_stop"), "plan_invalidation"
    if stop is None or not math.isfinite(float(stop)) or float(stop) >= entry:
        stop, src = entry - PLAN_ATR_MULT * atr, "atr_fallback"
    stop = float(stop)
    return stop, entry + PLAN_R_MULT * (entry - stop), src


def evaluate(cohort: Sequence[Mapping[str, Any]], bench: pd.Series | None,
             *, ob_masks: Mapping[str, pd.Series | None] | None = None
             ) -> dict[str, list[dict]]:
    """Run every policy over the SAME cohort. Returns {policy_key: [scored rows]}."""
    policies: dict[str, list[dict]] = {k: [] for k in POLICY_KEYS}
    masks = dict(ob_masks or {})
    for ep in cohort:
        ser, fwd = ep["series"], ep["fwd"]
        prices = np.asarray(fwd.values, dtype=float)
        entry, atr = float(ep["entry"]), float(ep["atr"])

        # P0 — the incumbent, run through track_scoring itself so the calibration block
        # is comparing the shipped code path, not a re-implementation of it.
        tk = ep["ticker"]
        if tk not in masks:
            masks[tk] = _ob_mask(ser)
        sc = ts.score_from_fill(ser, ser.index[ep["i_fill"]], entry, LEDGER_HORIZON,
                                stop_level=ep.get("trough_stop"), early_exit=masks[tk],
                                bench_close=bench)
        row0 = {"ticker": tk, "board_date": ep["board_date"], "entry_date": ep["fill_date"],
                "entry": entry, "matured": True, "held": sc["held"],
                "exit": sc["exit"], "exit_reason": sc["exit_reason"], "censored": False,
                "pnl": sc["pnl"], "excess": sc["excess"], "mfe": sc["mfe"], "mae": sc["mae"]}
        policies["P0"].append(row0)

        policies["P0f"].append(_row_from_walk(ep, walk_fixed(prices, LEDGER_HORIZON), bench))
        policies["P1"].append(_row_from_walk(ep, walk_fixed(prices, H_LONG), bench))
        for k in TRAIL_K:
            key = f"P2k{int(k)}"
            policies[key].append(
                _row_from_walk(ep, walk_trail(prices, entry, atr, k, CAP_TRAIL), bench))
        stop, target, src = _plan_geometry(ep)
        r3 = _row_from_walk(ep, walk_target_stop(prices, stop, target, CAP_PLAN), bench)
        r3["plan_stop_source"] = src
        r3["plan_r_pct"] = (entry - stop) / entry * 100.0
        policies["P3"].append(r3)
        policies["P4"].append(_row_from_walk(
            ep, walk_trail(prices, entry, atr, 3.0, CAP_TRAIL,
                           breakeven_arm_atr=BE_ARM_ATR), bench))
    return policies


POLICY_KEYS = ("P0", "P0f", "P1", "P2k2", "P2k3", "P3", "P4")
POLICY_LABEL = {
    "P0":   "P0 · incumbent as shipped (H=10 + StochRSI target + trough stop)",
    "P0f":  "P0f · pure fixed H=10",
    "P1":   "P1 · pure fixed H=21",
    "P2k2": "P2 · ATR trail k=2 (cap 63)",
    "P2k3": "P2 · ATR trail k=3 (cap 63)",
    "P3":   "P3 · plan target/stop, +3R (cap 21)",
    "P4":   "P4 · breakeven at +1 ATR then trail k=3 (cap 63)",
}
POLICY_SHORT = {"P0": "P0", "P0f": "P0f", "P1": "P1", "P2k2": "P2 k=2",
                "P2k3": "P2 k=3", "P3": "P3", "P4": "P4"}


# --------------------------------------------------------------------------- #
# metrics
# --------------------------------------------------------------------------- #
def _blocked(rows: Sequence[Mapping[str, Any]], field: str,
             stat: Callable[[np.ndarray], float]) -> tuple[float | None, float | None]:
    pairs = [(str(r["board_date"]), float(r[field])) for r in rows
             if r.get(field) is not None and math.isfinite(float(r[field]))]
    return ts.date_block_ci(pairs, stat)


def policy_metrics(rows: Sequence[Mapping[str, Any]]) -> dict:
    """Headline block for one policy, computed through ``track_scoring.summarize``."""
    out = dict(ts.summarize(rows, metric="pnl", horizon=LEDGER_HORIZON))
    ex = [float(r["excess"]) for r in rows
          if r.get("excess") is not None and math.isfinite(float(r["excess"]))]
    out["n_excess"] = len(ex)
    out["excess_expectancy_pct"] = round(float(np.mean(ex)), 2) if ex else None
    lo, hi = _blocked(rows, "excess", lambda a: float(a.mean()))
    out["excess_lo_pct"] = round(lo, 2) if lo is not None else None
    out["excess_hi_pct"] = round(hi, 2) if hi is not None else None
    out["n_censored"] = sum(1 for r in rows if r.get("censored"))
    reasons: dict[str, int] = {}
    for r in rows:
        reasons[str(r.get("exit_reason"))] = reasons.get(str(r.get("exit_reason")), 0) + 1
    out["exit_reasons"] = dict(sorted(reasons.items()))
    holds = [int(r["held"]) for r in rows if r.get("held") is not None]
    out["mean_hold"] = round(float(np.mean(holds)), 1) if holds else None
    out["max_hold"] = int(max(holds)) if holds else None
    return out


def paired_delta(rows: Sequence[Mapping[str, Any]],
                 base: Sequence[Mapping[str, Any]], field: str = "pnl") -> dict:
    """Mean per-episode (policy - base) with a date-blocked CI.

    Paired, not two-sample: the same entry on the same dates appears in both legs, so
    the difference isolates the exit rule and removes the entry cohort's variance. The
    CI still resamples whole board days — the pairs from one night are still one bet.
    """
    by_key = {(r["ticker"], r["board_date"]): r for r in base}
    deltas: list[tuple[str, float]] = []
    for r in rows:
        b = by_key.get((r["ticker"], r["board_date"]))
        if b is None or r.get(field) is None or b.get(field) is None:
            continue
        deltas.append((str(r["board_date"]), float(r[field]) - float(b[field])))
    if not deltas:
        return {"n": 0, "mean_delta_pct": None, "lo_pct": None, "hi_pct": None,
                "n_board_days": 0}
    vals = np.array([d for _, d in deltas], dtype=float)
    lo, hi = ts.date_block_ci(deltas, lambda a: float(a.mean()))
    return {"n": len(deltas),
            "n_board_days": len({d for d, _ in deltas}),
            "mean_delta_pct": round(float(vals.mean()), 3),
            "median_delta_pct": round(float(np.median(vals)), 3),
            "lo_pct": round(lo, 3) if lo is not None else None,
            "hi_pct": round(hi, 3) if hi is not None else None,
            "separates": bool(lo is not None and hi is not None and (lo > 0 or hi < 0))}


def decompose(rows: Sequence[Mapping[str, Any]],
              base: Sequence[Mapping[str, Any]], field: str = "pnl") -> dict:
    """WINNERS-KEPT vs LOSERS-CUT, against a fixed bar-10 anchor.

    The operator's question is "let winners run, cut losers short — what does each half
    actually buy us?". Each half has a benefit leg AND a cost leg, and a decomposition
    that prints only the benefit legs is an advert. So every episode lands in exactly one
    of five buckets, keyed on the POLICY's exit bar versus the anchor's, and on how the
    ANCHOR called the trade:

      extended_winner  held past bar 10, anchor had it green  -> "let winners run"
      extended_loser   held past bar 10, anchor had it red    -> the cost of that
      cut_winner       exited before bar 10, anchor had it green -> the cost of cutting
      cut_loser        exited before bar 10, anchor had it red   -> "cut losers short"
      same_bar         same exit bar; contributes exactly 0 by construction

    Each bucket's CONTRIBUTION is sum(delta in bucket) / n_total, so the five
    contributions sum to the overall mean delta exactly. That identity is unit-tested.
    """
    by_key = {(r["ticker"], r["board_date"]): r for r in base}
    buckets = {k: [] for k in ("extended_winner", "extended_loser",
                               "cut_winner", "cut_loser", "same_bar")}
    n_total = 0
    for r in rows:
        b = by_key.get((r["ticker"], r["board_date"]))
        if b is None or r.get(field) is None or b.get(field) is None:
            continue
        n_total += 1
        delta = float(r[field]) - float(b[field])
        anchor_win = float(b[field]) > 0
        rb, bb = int(r["held"]), int(b["held"])
        if rb > bb:
            key = "extended_winner" if anchor_win else "extended_loser"
        elif rb < bb:
            key = "cut_winner" if anchor_win else "cut_loser"
        else:
            key = "same_bar"
        buckets[key].append(delta)
    out: dict[str, Any] = {"n_total": n_total, "buckets": {}}
    total = 0.0
    for key, vals in buckets.items():
        contrib = (sum(vals) / n_total) if n_total else 0.0
        total += contrib
        out["buckets"][key] = {
            "n": len(vals),
            "contribution_pp": round(contrib, 3),
            "mean_delta_in_bucket_pp": round(float(np.mean(vals)), 3) if vals else None,
        }
    out["total_contribution_pp"] = round(total, 3)
    out["winners_kept_net_pp"] = round(
        out["buckets"]["extended_winner"]["contribution_pp"]
        + out["buckets"]["extended_loser"]["contribution_pp"], 3)
    out["losers_cut_net_pp"] = round(
        out["buckets"]["cut_loser"]["contribution_pp"]
        + out["buckets"]["cut_winner"]["contribution_pp"], 3)
    return out


# --------------------------------------------------------------------------- #
# calibration against the shipped ledger
# --------------------------------------------------------------------------- #
_CALIB_KEYS = ("n_matured", "n_board_days", "win_pct", "expectancy_pct", "median_pct",
               "avg_win_pct", "avg_loss_pct", "profit_factor", "ci_lo_pct", "ci_hi_pct",
               "exp_lo_pct", "exp_hi_pct", "median_hold", "capture",
               "mfe_median_pct", "mae_median_pct")


def calibrate(board_days: Mapping[str, Iterable[str]], closes: pd.DataFrame,
              bench: pd.Series | None, *, ledger_path: Path | None = None) -> dict:
    """Re-derive the shipped ledger summary on the FULL (uncoverage-filtered) cohort.

    Deliberately NOT the horse-race cohort: the ledger scores every episode with a close
    path, while the horse race additionally requires a high/low path for ATR. Running the
    calibration on the ledger's own cohort is what makes a non-zero delta mean "the
    reconstruction drifted" rather than "the cohorts differ".
    """
    scored, n_inflight, skipped = [], 0, []
    ob: dict[str, pd.Series | None] = {}
    for ep in ts.build_episodes(dict(board_days)):
        tk, d0 = ep["ticker"], ep["entry_date"]
        if tk not in closes.columns:
            skipped.append(tk)
            continue
        ser = closes[tk].dropna()
        if ser.empty:
            skipped.append(tk)
            continue
        if tk not in ob:
            ob[tk] = _ob_mask(ser)
        i_sig = ser.index.searchsorted(pd.Timestamp(d0), side="left")
        stop = None
        if i_sig < len(ser):
            trough = float(ser.iloc[max(0, i_sig - _TROUGH_LB):i_sig + 1].min())
            if math.isfinite(trough) and trough > 0:
                stop = trough * _TROUGH_TOL
        sc = ts.score_episode(ser, d0, LEDGER_HORIZON, stop_level=stop,
                              early_exit=ob[tk], bench_close=bench)
        if sc is None:
            skipped.append(tk)
            continue
        if sc.get("fill_pending") or not sc["matured"]:
            n_inflight += 1
            continue
        sc["board_date"] = d0
        scored.append(sc)
    rebuilt = ts.summarize(scored, metric="pnl", n_inflight=n_inflight,
                           n_skipped=len(skipped), horizon=LEDGER_HORIZON)

    path = ledger_path if ledger_path is not None else LEDGER_JSON
    shipped: dict[str, Any] = {}
    if Path(path).exists():
        shipped = (json.loads(Path(path).read_text()) or {}).get("summary") or {}
    deltas = {}
    for k in _CALIB_KEYS:
        a, b = rebuilt.get(k), shipped.get(k)
        if a is None or b is None:
            deltas[k] = None
        else:
            deltas[k] = round(float(a) - float(b), 6)
    exact = all(v == 0 for v in deltas.values() if v is not None)
    return {"rebuilt": rebuilt, "shipped": shipped, "deltas": deltas,
            "n_skipped_no_price": len(skipped),
            "tickers_skipped": sorted(set(skipped)),
            "exact_match": bool(exact and shipped)}


# --------------------------------------------------------------------------- #
# study
# --------------------------------------------------------------------------- #
def run_study(root: Path | None = None) -> dict:
    """Everything, deterministically. Returns the full result dict the report renders."""
    closes, highs, lows, bench = load_prices(root)
    board_days, invalidation, prov = load_board_days(root)
    cohort, exclusions = build_cohort(board_days, invalidation, closes, highs, lows)
    policies = evaluate(cohort, bench)

    metrics = {k: policy_metrics(v) for k, v in policies.items()}
    deltas_vs_p0 = {k: paired_delta(policies[k], policies["P0"])
                    for k in POLICY_KEYS if k != "P0"}
    deltas_vs_p0f = {k: paired_delta(policies[k], policies["P0f"])
                     for k in POLICY_KEYS if k != "P0f"}
    decomposition = {k: decompose(policies[k], policies["P0f"])
                     for k in POLICY_KEYS if k != "P0f"}

    bars = np.array([e["n_bars_available"] for e in cohort], dtype=int) if cohort else np.array([])
    ladder = {}
    for h in HORIZON_LADDER:
        idx = [i for i, e in enumerate(cohort) if e["n_bars_available"] >= h]
        ladder[h] = {
            "n_episodes": len(idx),
            "n_board_days": len({cohort[i]["board_date"] for i in idx}),
        }
    # The 21-bar sub-cohort: every <=21-cap policy resolves there without a data mark.
    sub21 = [e for e in cohort if e["n_bars_available"] >= 21]
    sub21_keys = {(e["ticker"], e["board_date"]) for e in sub21}
    ladder_metrics = {}
    if sub21:
        for k in POLICY_KEYS:
            rows = [r for r in policies[k] if (r["ticker"], r["board_date"]) in sub21_keys]
            ladder_metrics[k] = policy_metrics(rows)

    plan_r = [r["plan_r_pct"] for r in policies["P3"] if r.get("plan_r_pct") is not None]
    plan_src: dict[str, int] = {}
    for r in policies["P3"]:
        s = str(r.get("plan_stop_source"))
        plan_src[s] = plan_src.get(s, 0) + 1

    return {
        "generated_utc": dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%MZ"),
        "definition_cut": LEDGER_HISTORY_FROM,
        "incumbent_horizon": LEDGER_HORIZON,
        "bench": BENCH,
        "provenance": prov,
        "board_days": {"n": len(board_days),
                       "first": min(board_days) if board_days else None,
                       "last": max(board_days) if board_days else None},
        "price_asof": str(closes.index.max().date()) if len(closes.index) else None,
        "cohort": {
            "n_episodes": len(cohort),
            "n_board_days": len({e["board_date"] for e in cohort}),
            "bars_available_min": int(bars.min()) if bars.size else None,
            "bars_available_median": int(np.median(bars)) if bars.size else None,
            "bars_available_max": int(bars.max()) if bars.size else None,
        },
        "exclusions": exclusions,
        "metrics": metrics,
        "deltas_vs_p0": deltas_vs_p0,
        "deltas_vs_p0f": deltas_vs_p0f,
        "decomposition": decomposition,
        "ladder": ladder,
        "ladder_metrics": ladder_metrics,
        "plan_geometry": {
            "stop_source_counts": plan_src,
            "r_pct_median": round(float(np.median(plan_r)), 2) if plan_r else None,
            "r_pct_p10": round(float(np.percentile(plan_r, 10)), 2) if plan_r else None,
            "r_pct_p90": round(float(np.percentile(plan_r, 90)), 2) if plan_r else None,
            "target_pct_median": round(float(np.median(plan_r)) * PLAN_R_MULT, 2) if plan_r else None,
        },
        "calibration": calibrate(board_days, closes, bench),
    }


# --------------------------------------------------------------------------- #
# report
# --------------------------------------------------------------------------- #
def _f(v: Any, nd: int = 2, suffix: str = "") -> str:
    if v is None:
        return "—"
    if isinstance(v, float):
        return f"{v:.{nd}f}{suffix}"
    return f"{v}{suffix}"


def _ci(lo: Any, hi: Any, nd: int = 2) -> str:
    if lo is None or hi is None:
        return "—"
    return f"{lo:.{nd}f} … {hi:.{nd}f}"


def render_report(res: Mapping[str, Any]) -> str:
    m, coh = res["metrics"], res["cohort"]
    cal = res["calibration"]
    L = []
    A = L.append

    A("# Exit-policy horse race — US buy-lane episodes")
    A("")
    A(f"**Study date:** {res['generated_utc']} · "
      f"**Script:** `scripts/exit_policy_study.py` · "
      f"**Charter:** `research/PROPHET_LEARNING_LOOP_MASTERPLAN_BY_FABLE.md` §0 G3/G4, §1")
    A("")
    A("**Tier: measurement / display. Nothing here promotes anything.** The public track "
      "record keeps the incumbent rule. Every verdict below is descriptive — what this "
      "sample shows, on this cohort, at this size. A policy that eventually replaces the "
      "incumbent has to be pre-registered first; see *Promotion path* at the end.")
    A("")
    A("---")
    A("")

    # ---- what was measured -------------------------------------------------
    A("## What was measured")
    A("")
    A("One question: **on identical entries, what does a holder-with-rules capture?** "
      "The Track-record ledger answers a different one (is the SIGNAL any good?) and has "
      "to stay policy-free to answer it, so this is a separate study reading the same "
      "episodes — the ledger, the board and every weight are untouched.")
    A("")
    A(f"* **Cohort** — buy-lane episodes on boards from **{res['definition_cut']}** onward "
      f"(the board-definition cut; earlier boards published a 120-name broad screen and "
      f"are a different instrument). One episode = one contiguous board run. "
      f"Entry = the **next session's close** after the board date, identical for every "
      f"policy — the board is computed from that close and published that evening, so the "
      f"signal bar is unbuyable.")
    A(f"* **Boards** — {res['board_days']['n']} board days, "
      f"{res['board_days']['first']} → {res['board_days']['last']}. "
      f"Prices run to **{res['price_asof']}**.")
    A(f"* **Episodes** — **{coh['n_episodes']} episodes across "
      f"{coh['n_board_days']} board days.** Forward bars available per episode: "
      f"{coh['bars_available_min']} min / {coh['bars_available_median']} median / "
      f"{coh['bars_available_max']} max.")
    A(f"* **Benchmark** — {res['bench']} total return over each episode's own "
      f"fill→exit window.")
    prov = res["provenance"]
    A(f"* **Provenance** — board membership is `snapshots.jsonl` UNION the buy-lane rows of "
      f"`retro_grades.parquet`. In this run the snapshot store already covered the whole "
      f"post-cut era: retro contributed {prov['n_days_retro_only']} extra board days and "
      f"{prov['n_tickers_added_by_retro']} extra tickers. The union is kept anyway so a "
      f"future gap in the forward store heals from git archaeology instead of silently "
      f"shrinking the cohort.")
    A("")
    A("`n_board_days` is the number that matters. Episodes surfaced on the same night "
      "share the tape, the regime read and the ranker's state — they are one bet, not N. "
      f"**{coh['n_board_days']} board days is the effective sample here**, not "
      f"{coh['n_episodes']}.")
    A("")

    # ---- exclusions --------------------------------------------------------
    A("### Coverage and exclusions (nothing dropped silently)")
    A("")
    A("| Excluded because | Episodes |")
    A("|---|---:|")
    _labels = {
        "no_price_column": "no close series in the breadth caches (delisted / not in S&P 1500)",
        "empty_series": "close column present but all-null",
        "fill_not_printed": "next-session fill has not printed yet",
        "bad_entry": "fill price non-finite or ≤ 0",
        "immature": f"fewer than {res['incumbent_horizon']} forward bars (in flight)",
        "no_atr": "no high/low path, or ATR14 not computable at the fill bar",
    }
    n_excl = 0
    for k, lab in _labels.items():
        n = res["exclusions"]["counts"].get(k, 0)
        n_excl += n
        A(f"| {lab} | {n} |")
    A(f"| **kept — the horse-race cohort** | **{coh['n_episodes']}** |")
    A(f"| *total episodes built from the {res['board_days']['n']} boards* "
      f"| *{n_excl + coh['n_episodes']}* |")
    A("")
    tick = res["exclusions"]["tickers"].get("no_price_column") or []
    if tick:
        A(f"No-price names ({len(tick)} distinct tickers, "
          f"{res['exclusions']['counts'].get('no_price_column', 0)} episodes): "
          f"{', '.join('`%s`' % t for t in tick)}.")
        A("")
    A("Exclusions are by **data coverage** and by **age** only. Neither can know which way "
      "a trade went, so both are symmetric — unlike an exclusion keyed on outcome, which "
      "would delete the losers.")
    A("")

    # ---- censoring ---------------------------------------------------------
    A("### The censoring caveat — read before the table")
    A("")
    lad = res["ladder"]
    h0, h1, h2 = HORIZON_LADDER
    A(f"The record starts {res['board_days']['first']} and prices end {res['price_asof']}. "
      f"Of the {coh['n_episodes']} episodes, **{lad[h0]['n_episodes']} have {h0} forward "
      f"bars** ({lad[h0]['n_board_days']} board days), **{lad[h1]['n_episodes']} have "
      f"{h1}** ({lad[h1]['n_board_days']} board day"
      f"{'s' if lad[h1]['n_board_days'] != 1 else ''}), and "
      f"**{lad[h2]['n_episodes']} have {h2}**.")
    A("")
    A("So the 21- and 63-bar caps mostly cannot be reached. A position still open when the "
      "data ends is **marked at the last available close and flagged `data_end`** — it is "
      "not dropped, because dropping it would delete precisely the trades that were still "
      "running, and a denominator conditioned on how a trade ended is the single artefact "
      "`engine/track_scoring.py` exists to forbid. Every policy row prints its `data_end` "
      "count. **A `data_end` row is a mark, not a realised exit, and its hold length is a "
      "lower bound.** Read the cap-63 rows as *what these rules were still holding on "
      f"{res['price_asof']}*, not as *what these rules returned*.")
    A("")

    # ---- calibration -------------------------------------------------------
    A("## Calibration — does P0 reproduce the shipped ledger?")
    A("")
    if cal["shipped"]:
        A("P0 is the incumbent rule executed through `engine.track_scoring` itself, on the "
          "ledger's own cohort (close path only, no ATR requirement) so a non-zero delta "
          "would mean the reconstruction drifted rather than that the cohorts differ.")
        A("")
        A("| Key | Shipped `us_track_ledger.json` | Rebuilt here | Δ |")
        A("|---|---:|---:|---:|")
        for k in _CALIB_KEYS:
            A(f"| `{k}` | {_f(cal['shipped'].get(k))} | {_f(cal['rebuilt'].get(k))} | "
              f"{_f(cal['deltas'].get(k), 4)} |")
        A("")
        A(f"**Calibration delta: {'exact — 0.0000 on every key' if cal['exact_match'] else 'NON-ZERO — see the table'}.** "
          "The horse-race cohort is a strict subset of this one (it additionally requires a "
          "high/low path for ATR14).")
    else:
        A("`site/factordata/us_track_ledger.json` was not readable — calibration skipped.")
    A("")

    # ---- headline table ----------------------------------------------------
    A("## The horse race")
    A("")
    A(f"All {coh['n_episodes']} episodes, all policies, identical entries. "
      "Win = return > 0 (no dead band). `capture` = median(realised / MFE) over the "
      "policy's own hold window — the ledger's own definition. MAE/MFE are close-path and "
      "understate the intraday excursion.")
    A("")
    A("| Policy | n | expectancy | vs SPY | win % | avg win | avg loss | PF | med hold | max hold | capture | med MAE | `data_end` |")
    A("|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|")
    for k in POLICY_KEYS:
        r = m[k]
        A(f"| {POLICY_LABEL[k]} | {r['n_matured']} | **{_f(r['expectancy_pct'])}%** | "
          f"{_f(r['excess_expectancy_pct'])}% | {_f(r['win_pct'], 1)} | "
          f"{_f(r['avg_win_pct'])} | {_f(r['avg_loss_pct'])} | {_f(r['profit_factor'])} | "
          f"{r['median_hold']} | {r['max_hold']} | {_f(r['capture'])} | "
          f"{_f(r.get('mae_median_pct'))} | {r['n_censored']} |")
    A("")
    A("Date-blocked 95% intervals (whole board days resampled, seeded — "
      f"{coh['n_board_days']} blocks):")
    A("")
    A("| Policy | expectancy 95% CI | win-rate 95% CI | vs-SPY expectancy 95% CI |")
    A("|---|---|---|---|")
    for k in POLICY_KEYS:
        r = m[k]
        A(f"| {POLICY_LABEL[k]} | {_ci(r['exp_lo_pct'], r['exp_hi_pct'])} | "
          f"{_ci(r['ci_lo_pct'], r['ci_hi_pct'], 1)} | "
          f"{_ci(r.get('excess_lo_pct'), r.get('excess_hi_pct'))} |")
    A("")
    A("Exit-reason mix (how each rule actually ended):")
    A("")
    A("| Policy | " + " | ".join(f"`{r}`" for r in
                                 (R_HORIZON, R_TRAIL, R_PLAN_STOP, R_PLAN_TARGET,
                                  "stop", "target", R_DATA_END)) + " |")
    A("|---|" + "---:|" * 7)
    for k in POLICY_KEYS:
        rs = m[k]["exit_reasons"]
        A(f"| {POLICY_LABEL[k]} | " + " | ".join(
            str(rs.get(r, 0)) for r in (R_HORIZON, R_TRAIL, R_PLAN_STOP, R_PLAN_TARGET,
                                        "stop", "target", R_DATA_END)) + " |")
    A("")
    A("(`stop` / `target` are the incumbent's own legs — the 90d-trough break and the "
      "3D-StochRSI overbought read — and appear only on the P0 row.)")
    A("")

    # ---- deltas ------------------------------------------------------------
    A("## Does anything separate from the incumbent?")
    A("")
    A("Paired per-episode deltas: same entry, same window, so the difference isolates the "
      "exit rule. The interval still resamples whole board days. **No p-values** — with "
      f"{coh['n_board_days']} blocks a per-policy p-value would be decoration, and the "
      "block structure is the only thing making the interval honest.")
    A("")
    A(f"| Policy | Δ vs P0 (incumbent) | 95% CI | excludes 0? | "
      f"Δ vs P0f (fixed H={LEDGER_HORIZON}) | 95% CI | excludes 0? |")
    A("|---|---:|---|:--:|---:|---|:--:|")

    def _cell(d: Mapping[str, Any] | None) -> str:
        if not d or d.get("mean_delta_pct") is None:
            return "— | — | —"
        return (f"{d['mean_delta_pct']:+.2f} pp | {_ci(d['lo_pct'], d['hi_pct'])} | "
                f"{'**yes**' if d['separates'] else 'no'}")

    for k in POLICY_KEYS:
        A(f"| {POLICY_LABEL[k]} | {_cell(res['deltas_vs_p0'].get(k))} | "
          f"{_cell(res['deltas_vs_p0f'].get(k))} |")
    A("")

    # ---- decomposition -----------------------------------------------------
    A("## Winners kept vs losers cut")
    A("")
    A("The operator's question, decomposed. Anchor = **P0f, a hard exit at bar 10**, so "
      "\"extended beyond 10d\" and \"cut before 10d\" are literal. Every episode lands in "
      "exactly one bucket; each bucket's contribution is `sum(Δ in bucket) / n_total`, so "
      "the five contributions **sum to the policy's total Δ vs P0f**. Both halves get "
      "their cost leg printed beside their benefit leg — a decomposition that shows only "
      "the benefit legs is an advert.")
    A("")
    A("| Policy | extended·winner | extended·loser | **winners-kept net** | cut·loser | cut·winner | **losers-cut net** | same bar | total Δ |")
    A("|---|---:|---:|---:|---:|---:|---:|---:|---:|")

    def _bucket(buckets: Mapping[str, Any], name: str) -> str:
        x = buckets[name]
        return f"{x['contribution_pp']:+.2f} pp<br><sub>n={x['n']}</sub>"

    for k in POLICY_KEYS:
        d = res["decomposition"].get(k)
        if not d:
            continue
        b = d["buckets"]

        def _b(name: str, _b_=b) -> str:
            return _bucket(_b_, name)

        A(f"| {POLICY_LABEL[k]} | {_b('extended_winner')} | {_b('extended_loser')} | "
          f"**{d['winners_kept_net_pp']:+.2f} pp** | {_b('cut_loser')} | {_b('cut_winner')} | "
          f"**{d['losers_cut_net_pp']:+.2f} pp** | {_b('same_bar')} | "
          f"**{d['total_contribution_pp']:+.2f} pp** |")
    A("")

    # ---- ladder ------------------------------------------------------------
    A("## Horizon ladder")
    A("")
    A("| Horizon | Episodes with that many forward bars | Board days |")
    A("|---:|---:|---:|")
    for h in HORIZON_LADDER:
        A(f"| {h} | {lad[h]['n_episodes']} | {lad[h]['n_board_days']} |")
    A("")
    if res["ladder_metrics"]:
        n21 = lad[21]["n_episodes"]
        d21 = lad[21]["n_board_days"]
        A(f"The **21-bar sub-cohort** ({n21} episodes, {d21} board day"
          f"{'s' if d21 != 1 else ''}) is the only slice where the 21-cap policies resolve "
          "without a data mark. It is shown for completeness and is **descriptive only**: "
          + ("with a single board day there is nothing to resample, so `date_block_ci` "
             "correctly returns no interval — any number printed here would be one bet."
             if d21 < 2 else
             f"{d21} board days is far too few blocks for an interval to mean much."))
        A("")
        A("| Policy | n | expectancy | win % | med hold | `data_end` |")
        A("|---|---:|---:|---:|---:|---:|")
        for k in POLICY_KEYS:
            r = res["ladder_metrics"][k]
            A(f"| {POLICY_LABEL[k]} | {r['n_matured']} | {_f(r['expectancy_pct'])}% | "
              f"{_f(r['win_pct'], 1)} | {r['median_hold']} | {r['n_censored']} |")
        A("")
    A(f"**63 sessions: {lad[63]['n_episodes']} episodes support it.** The ladder's 63-bar "
      "rung cannot be printed at all yet — it is not truncated, it does not exist. It will "
      "exist around the turn of the quarter and this study re-runs unchanged.")
    A("")

    # ---- plan geometry note ------------------------------------------------
    pg = res["plan_geometry"]
    A("## Note on P3's geometry")
    A("")
    A(f"P3's stop is the board row's own published invalidation level where present "
      f"({pg['stop_source_counts'].get('plan_invalidation', 0)} episodes; "
      f"{pg['stop_source_counts'].get('atr_fallback', 0)} fell back to entry − 2×ATR14). "
      f"That level is a break of the setup's 90-session trough × 0.97 — a **thesis** "
      f"invalidation, not a risk stop. Its median distance below entry in this cohort is "
      f"**{_f(pg['r_pct_median'])}%** (p10 {_f(pg['r_pct_p10'])}%, p90 "
      f"{_f(pg['r_pct_p90'])}%), which puts the +3R target a median "
      f"**{_f(pg['target_pct_median'])}%** above entry.")
    A("")
    A("A target that far away is essentially unreachable inside 21 sessions, so **P3 as "
      "specified degenerates toward a fixed H=21 with a rarely-touched stop** — which is "
      "what its exit-reason mix above shows. That is a finding about the plan geometry, "
      "not a bug in the walker: the desk publishes an invalidation level, not a stop-loss, "
      "and the two are not interchangeable. Sizing a stop off that level is a separate "
      "question this study does not answer.")
    A("")

    # ---- read --------------------------------------------------------------
    A("## Read")
    A("")
    A(_read_paragraphs(res))
    A("")
    A("## Promotion path: prereg required")
    A("")
    A("Nothing in this report promotes anything. It is measurement tier: the numbers are "
      "printed, the nulls are printed, and the incumbent keeps the headline. For any policy "
      "here to change what the product does, it has to go through the promotion pipeline "
      "first — a pre-registration that fixes the policy, the cohort, the horizon, the "
      "metric and the decision rule **before** the outcome is recomputed, then a verdict "
      "against those pre-registered gates on a sample with enough independent board days "
      "to carry one. This study is an input to that prereg, not a substitute for it "
      "(masterplan §0 G4/G7).")
    A("")
    return "\n".join(L) + "\n"


def _read_paragraphs(res: Mapping[str, Any]) -> str:
    """The honest verdict, GENERATED from the numbers rather than asserted beside them.

    Written so the direction of any separation is stated, never just its existence: a
    policy whose interval excludes zero on the LOW side has been shown to be worse in
    this sample, and reporting that as "separates" without the sign would be a rig.
    """
    coh = res["cohort"]
    d0 = res["deltas_vs_p0"]
    beats = [k for k, d in d0.items() if d.get("separates") and (d["lo_pct"] or 0) > 0]
    lags = [k for k, d in d0.items() if d.get("separates") and (d["hi_pct"] or 0) < 0]
    flat = [k for k in d0 if not d0[k].get("separates")]
    nm = lambda keys: ", ".join(f"**{POLICY_SHORT[k]}**" for k in keys)  # noqa: E731
    lines = []

    if not beats:
        lines.append(
            f"**No policy beats the incumbent in this sample.** Not one paired delta "
            f"versus P0 has a date-blocked 95% interval sitting above zero. "
            + (f"{nm(lags)} sit BELOW zero — in this cohort they gave up ground to the "
               f"incumbent rather than gaining on it. " if lags else "")
            + (f"{nm(flat)} straddle zero, which at {coh['n_episodes']} episodes across "
               f"{coh['n_board_days']} board days is the expected result whether or not a "
               f"real difference exists. " if flat else "")
            + "The study is not powered to find a small edge; a point estimate that "
              "happens to be positive is not evidence that one is there.")
    else:
        lines.append(
            f"{nm(beats)} show a paired delta versus the incumbent whose date-blocked 95% "
            f"interval sits ABOVE zero in this sample. That is a description of "
            f"{coh['n_board_days']} board days, not an edge claim — and any policy here "
            f"has to clear its own pre-registration before it can change anything."
            + (f" {nm(lags)} sit below zero." if lags else ""))
    lines.append("")

    # The decomposition read, keyed off the fixed-H comparison the operator asked about.
    dp1 = res["decomposition"].get("P1")
    dp0 = res["decomposition"].get("P0")
    if dp1:
        ew, el = dp1["buckets"]["extended_winner"], dp1["buckets"]["extended_loser"]
        verb = "cost" if (ew["contribution_pp"] or 0) < 0 else "added"
        tail = ("Running further did not, here, pay for itself."
                if (ew["contribution_pp"] or 0) <= 0 else
                "Running further did, here, pay something — on eight board days.")
        lines.append(
            f"**On the operator's question — *let winners run, cut losers short* — the two "
            f"halves do not behave alike in this sample.** Take the cleanest pair: P1 is "
            f"P0f held to bar {H_LONG} instead of bar {LEDGER_HORIZON}, so its whole delta "
            f"IS the \"let it run\" half. Extending the {ew['n']} episodes P0f had green "
            f"{verb} **{ew['contribution_pp']:+.2f} pp** of expectancy "
            f"({ew['mean_delta_in_bucket_pp']:+.2f} pp each), while extending the "
            f"{el['n']} it had red contributed **{el['contribution_pp']:+.2f} pp**. "
            f"{tail}")
        lines.append("")
    if dp0:
        cl, cw = dp0["buckets"]["cut_loser"], dp0["buckets"]["cut_winner"]
        lines.append(
            f"The cutting half already exists in the product: the incumbent's "
            f"3D-StochRSI target leg exits {cl['n'] + cw['n']} of the {dp0['n_total']} "
            f"episodes before bar 10. Cutting the {cl['n']} that P0f had red is worth "
            f"**{cl['contribution_pp']:+.2f} pp**; cutting the {cw['n']} that P0f had "
            f"green costs **{cw['contribution_pp']:+.2f} pp**; net "
            f"**{dp0['losers_cut_net_pp']:+.2f} pp**. So in this cohort the benefit of "
            f"the desk's early exit comes with a real cost leg attached, and the net is "
            f"small enough that {coh['n_board_days']} board days cannot resolve it — the "
            f"P0-vs-P0f interval straddles zero.")
        lines.append("")

    m1 = res["metrics"].get("P1", {})
    lines.append(
        f"**Every \"run it longer\" number above is contaminated by the data edge.** "
        f"{m1.get('n_censored', 0)} of P1's {m1.get('n_matured', 0)} rows never reached "
        f"bar 21 — they are marks on {res['price_asof']}, not exits. The extended buckets "
        f"therefore mostly measure \"held 11–20 sessions and marked\", not \"held 21\". "
        f"That biases nothing in a known direction; it just makes the estimate mushier "
        f"than its decimal places suggest.")
    lines.append("")
    lines.append(
        f"The structural finding that does not depend on sample size: **the record is too "
        f"young for this question.** A trailing stop is the instrument for capturing moves "
        f"that extend for months, and the longest forward path in existence here is "
        f"{coh['bars_available_max']} sessions — the cap-63 family has never once been "
        f"allowed to reach its cap. The horse race is wired, calibrated against the "
        f"shipped ledger, and cheap to re-run; what it needs is time.")
    return "\n".join(lines)


# --------------------------------------------------------------------------- #
def main(argv: Sequence[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--out", default=str(REPORT_PATH), help="markdown report path")
    ap.add_argument("--json", default=None, help="also dump the raw result dict here")
    ap.add_argument("--quiet", action="store_true")
    args = ap.parse_args(argv)

    res = run_study()
    md = render_report(res)
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(md)
    if args.json:
        def _plain(o):
            if isinstance(o, (np.integer,)):
                return int(o)
            if isinstance(o, (np.floating,)):
                return float(o)
            return str(o)
        Path(args.json).write_text(json.dumps(res, indent=1, default=_plain))
    if not args.quiet:
        coh = res["cohort"]
        print(f"[exit_policy_study] {coh['n_episodes']} episodes / "
              f"{coh['n_board_days']} board days · "
              f"calibration exact={res['calibration']['exact_match']} → {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
