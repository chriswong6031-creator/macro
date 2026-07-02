"""Provisional-basis tier replay — the W6 #22 measurement the validation never covered.

THE AUDIT'S CORE POINT (research/ENGINE_PROBLEM_AUDIT.md #22): the freshest, most-acted-on
tier the board shows is computed on an INCOMPLETE resample bucket. ``confluence_tiers._tf_bars``
(:78-80) keeps the last 2B/3B bucket even when only 1-2 of its days have printed, and
``FRESH_TICKS=2`` deliberately surfaces names crossing on that provisional tail. Point-in-time
backtests recompute on COMPLETED bars and never see these provisional fires — so the tier a
trader acts on today is precisely the tier the validation did not cover.

This module closes that gap by REPLAYING each historical day D through the SAME live code path
(``engine.signal_gate.gate`` → ``confluence_tiers.cascade`` on the incomplete tail). Truncating a
name's daily close at D reproduces EXACTLY the provisional-bucket state the live board had on D
(verified: the last 3B bucket that spans D-2/D-1/D on a completed day is 1/3 or 2/3 printed on the
two prior days — the same partial tail the live build resampled). We then measure, honestly:

  (a) REPAINT rate  — a fresh T1/T2/T3 shown at D that UN-CROSSES when the bucket completes
      (drops to no-tier / topped by D+lookahead for a reason OTHER than simply aging past the
      freshness window). This is the "appear / vanish / reappear" churn the audit names.
  (b) PROVISIONAL EDGE — the forward next-bar-filled return (engine.grading conventions) of a
      provisional-tail fire vs a completed-bucket fire. If provisional fires have materially worse
      or sign-flipped edge, the freshest lane is misleading and must be split/badged.
  (c) NOT-TOPPED FLICKER — how often the single-bar not-topped veto flips D→D+1 on one noisy
      oscillator reading (the AMAT-guard's precision/recall cost the audit flags).

Determinism: a given (ticker, D, series-truncated-at-D) always yields the SAME tier — the cascade
is a pure function of the close history (tests/test_provisional_replay.py pins this). RESEARCH /
measurement telemetry only — never a trade trigger, never mutates the live board.

Design mirrors engine/china_standout_track + engine/grading: pure pandas/numpy, degrade-safe,
next-bar fills, honest CIs. Callers pass their own {ticker: close Series} panel in.
"""
from __future__ import annotations

import logging
from typing import Any, Callable

import numpy as np
import pandas as pd

from engine import confluence_tiers, signal_gate, grading

log = logging.getLogger(__name__)

# Tiers that constitute a FRESH, ACTIONABLE confluence buy on the board (signal_gate.BUYABLE_TIERS
# = T1/T2/T3). T4 is display-excluded from the board's "what to buy now" strip, but we replay it
# too so the repaint of the earliest anti-falling-knife tier is measured separately.
FRESH_TIERS = ("T1", "T2", "T3")
ALL_TIERS = ("T1", "T2", "T3", "T4")

# Forward horizons for the edge study (next-bar-filled, engine.grading semantics). Short windows —
# a fresh entry is a timing signal, and the repaint churn lives in the first few sessions.
EDGE_HORIZONS = (5, 10, 21)

# How many trading days forward we watch a fresh fire to decide whether it REPAINTED. A cross that
# vanishes within this window WITHOUT simply aging past FRESH_TICKS is a repaint (the bucket
# completed and the cross un-fired). ~2 native 3D ticks.
REPAINT_LOOKAHEAD = 4

# Minimum daily history before a name can be replayed (matches confluence_tiers.MIN_HISTORY plus a
# margin so the 3B/2B resample + 200MA are all defined).
MIN_HISTORY = 260


def replay_series(
    ticker: str,
    daily_close: pd.Series,
    *,
    start: pd.Timestamp | None = None,
    end: pd.Timestamp | None = None,
    max_days: int | None = None,
    gate_fn: Callable[[str, pd.Series], dict] | None = None,
) -> pd.DataFrame:
    """Replay one name day-by-day through the LIVE gate on the truncated-at-D series.

    For each trading day D in [start, end] (last ``max_days`` if given), compute the tier EXACTLY
    as the live build would have at D — the incomplete resample tail included — by calling
    ``signal_gate.gate(ticker, close[:D])``. Returns a per-day frame:

        date, tier, ticks, not_topped, eligible, bars_to_cross, close

    ``not_topped`` reads the cascade's veto directly (topped days return a blank tier but the veto
    state is still exposed). Never raises; a bad day yields a blank row rather than aborting the
    replay. ``gate_fn`` is injectable so a KNOB SWEEP can replay under a patched FRESH_TICKS/veto
    without editing the module under test."""
    gate = gate_fn if gate_fn is not None else signal_gate.gate
    c = pd.to_numeric(daily_close, errors="coerce").dropna()
    if not isinstance(c.index, pd.DatetimeIndex):
        c = c.copy()
        c.index = pd.to_datetime(c.index)
    c = c.sort_index()
    if len(c) < MIN_HISTORY:
        return pd.DataFrame()
    di = c.index
    # the window of days we actually replay (each needs enough history behind it)
    days = di[di.searchsorted(pd.Timestamp(start)) if start is not None else MIN_HISTORY:]
    if end is not None:
        days = days[days <= pd.Timestamp(end)]
    if max_days is not None and len(days) > max_days:
        days = days[-max_days:]

    # COMPLETED-bucket (validated) tier for every day — ONE fast vectorized pass. This is the basis
    # the point-in-time validation covered; the provisional per-day view is compared against it.
    completed = confluence_tiers.tier_stream(c)

    rows: list[dict] = []
    for D in days:
        trunc = c[c.index <= D]
        try:
            v = gate(ticker, trunc)                    # PROVISIONAL view: the live board at D
        except Exception:  # noqa: BLE001 — a single bad day never aborts the replay
            v = {}
        # The live gate clears tier_cascade to None on topped/stale; the raw cascade carries the
        # not_topped veto. Re-derive the veto from the cascade directly so flicker is measurable
        # even on days the gate blanked the tier.
        nt = _not_topped_at(trunc)
        crow = completed.loc[D] if (not completed.empty and D in completed.index) else None
        comp_tier = _clean_tier(crow["tier"]) if crow is not None else None
        rows.append({
            "date": D,
            "tier": v.get("tier_cascade"),             # provisional (live board) tier
            "ticks": v.get("ticks"),
            "not_topped": nt,
            "eligible": bool(v.get("eligible")),
            "bars_to_cross": v.get("bars_to_cross"),
            "completed_tier": comp_tier,               # completed-bucket (validated) tier at D
            "completed_not_topped": (bool(crow["not_topped"]) if crow is not None else None),
            "close": float(trunc.iloc[-1]),
        })
    out = pd.DataFrame(rows)
    if not out.empty:
        out["ticker"] = ticker
    return out


def _clean_tier(t) -> str | None:
    """Normalise a tier_stream cell (may be a numpy object/nan) to a str tier or None."""
    if t is None:
        return None
    if isinstance(t, float) and np.isnan(t):
        return None
    return str(t)


def _not_topped_at(trunc_close: pd.Series) -> bool | None:
    """The not-topped veto state on the truncated series (the raw cascade veto, before the gate
    blanks a stale tier). None if undeterminable."""
    try:
        casc = confluence_tiers.cascade(trunc_close, take_active=False)
        return bool(casc.get("not_topped", True))
    except Exception:  # noqa: BLE001
        return None


# --------------------------------------------------------------------------- #
# (a) REPAINT — a fresh tier that un-crosses when the bucket completes
# --------------------------------------------------------------------------- #
def _tier_rank(t: str | None) -> int:
    """Cascade strength rank (higher = stronger confirmed). None/blank = 0."""
    return {"T4": 1, "T3": 2, "T2": 3, "T1": 4}.get(t or "", 0)


def repaint_events(frame: pd.DataFrame, *, lookahead: int = REPAINT_LOOKAHEAD) -> pd.DataFrame:
    """From one name's replay frame, flag every FRESH PROVISIONAL fire and whether it REPAINTED.

    A fresh fire = the PROVISIONAL (live-board) view shows a tier in FRESH_TIERS that is genuinely
    fresh (ticks None — projected T3 — or ticks <= FRESH_TICKS). Each fire at D is classified by
    comparing the live view against the COMPLETED-bucket (validated) view, both AT D and over the
    next ``lookahead`` days as the bucket settles:

      * ``confirmed``  — the completed-bucket view AT D already agrees the fire is a fresh tier at
                         least as strong (the provisional tail didn't invent it) → NOT a repaint.
      * ``held``       — the completed view at D disagrees but a same-or-stronger fresh tier appears
                         in the completed view within the window (the cross was real, just settling)
                         → NOT a repaint.
      * ``repaint``    — the completed-bucket view never shows this fresh tier through the window:
                         the fire existed ONLY because of the incomplete tail and un-crosses when the
                         bucket completes. This is the audit's exact repaint (#22). Sub-typed by
                         whether the veto flickered (``repaint_veto_flicker``) or the cross simply
                         un-fired (``repaint_uncross``).

    Returns rows: date, tier, ticks, provisional(bool), repaint(bool), outcome, close. A fire in the
    last ``lookahead`` days is dropped (the bucket can't settle yet)."""
    if frame.empty or "completed_tier" not in frame.columns:
        return pd.DataFrame()
    f = frame.reset_index(drop=True)
    n = len(f)
    ft = confluence_tiers.FRESH_TICKS
    out = []
    for i in range(n):
        tier = f.at[i, "tier"]                                    # provisional (live) tier at D
        if tier not in FRESH_TIERS:
            continue
        ticks = f.at[i, "ticks"]
        is_fresh = (ticks is None) or (pd.notna(ticks) and float(ticks) <= ft)
        if not is_fresh:
            continue
        if i + lookahead >= n:
            continue  # bucket cannot settle yet
        cur_rank = _tier_rank(tier)
        # completed-bucket view AT D and across the settling window
        comp_here = _tier_rank(f.at[i, "completed_tier"])
        comp_window = [_tier_rank(t) for t in
                       f.iloc[i: i + 1 + lookahead]["completed_tier"].tolist()]
        comp_nt = f.iloc[i: i + 1 + lookahead]["completed_not_topped"].tolist()
        outcome, repaint = _classify_vs_completed(cur_rank, comp_here, comp_window, comp_nt)
        out.append({
            "date": f.at[i, "date"], "tier": tier, "ticks": ticks,
            "repaint": repaint, "outcome": outcome, "close": f.at[i, "close"],
        })
    return pd.DataFrame(out)


def _classify_vs_completed(cur_rank: int, comp_here: int, comp_window: list[int],
                           comp_nt: list) -> tuple[str, bool]:
    """Classify a provisional fresh fire against the completed-bucket view. See repaint_events."""
    # the completed view already carries a fresh tier >= this one AT D → the tail didn't invent it
    if comp_here >= cur_rank and comp_here > 0:
        return "confirmed", False
    # a same-or-stronger fresh tier shows up in the completed view as the bucket settles → real cross
    if any(r >= cur_rank for r in comp_window):
        return "held_into_completed", False
    # the completed view carries a WEAKER-but-present fresh tier through the window → a downgrade,
    # the name is still on the board (softening, not a full un-cross)
    if any(0 < r < cur_rank for r in comp_window):
        return "downgraded", False
    # the completed view NEVER shows a fresh tier → the fire existed only on the provisional tail.
    veto_tripped = any(nt is False for nt in comp_nt if nt is not None)
    return (("repaint_veto_flicker", True) if veto_tripped else ("repaint_uncross", True))


# --------------------------------------------------------------------------- #
# (b) PROVISIONAL EDGE — forward return of a provisional-tail fire vs a completed-bucket fire
# --------------------------------------------------------------------------- #
def bucket_completeness(daily_close: pd.Series, D: pd.Timestamp, n_tf: int = 3) -> dict:
    """Is day D's newest n_tf-bar bucket COMPLETE or PROVISIONAL, and how many days have printed?

    The board's freshest tier reads the last n_tf-business-day bucket. On the day that bucket's
    final constituent prints, it is COMPLETE; on the 1-2 days before, it is PROVISIONAL (the tail
    the validation never saw). Returns {complete, printed, expected, bucket_label}."""
    c = pd.to_numeric(daily_close, errors="coerce").dropna()
    c = c[c.index <= pd.Timestamp(D)]
    if len(c) < n_tf:
        return {"complete": None, "printed": None, "expected": n_tf, "bucket_label": None}
    s = c.resample(f"{n_tf}B").last().dropna()
    label = s.index[-1]
    in_bucket = c[c.index >= label]
    printed = int(len(in_bucket))
    return {
        "complete": bool(printed >= n_tf),
        "printed": printed, "expected": n_tf,
        "bucket_label": str(label.date()),
    }


def edge_of_fires(
    ticker: str,
    daily_close: pd.Series,
    fires: pd.DataFrame,
    *,
    horizons=EDGE_HORIZONS,
    n_tf: int = 3,
) -> pd.DataFrame:
    """Attach next-bar-filled forward returns + provisional/completed classification to each fresh
    fire. Uses engine.grading.forward_metrics (NEXT-BAR fill, strictly-forward window — the honest
    convention) on the FULL series (the forward return is measured on realised bars after D, which
    is legitimate: we are grading the fire's outcome, not recomputing the tier).

    Adds per row: provisional(bool), printed, plus fwd_ret_{H} for each horizon. A fire on a
    provisional bucket day is the exact fire the point-in-time backtest never saw."""
    if fires.empty:
        return fires
    c = pd.to_numeric(daily_close, errors="coerce").dropna().sort_index()
    recs = []
    for _i, row in fires.iterrows():
        D = pd.Timestamp(row["date"])
        bc = bucket_completeness(c, D, n_tf=n_tf)
        fm = grading.forward_metrics(c, D, horizons=horizons)
        rec = dict(row)
        rec["provisional"] = (bc["complete"] is False)
        rec["printed"] = bc["printed"]
        for h in horizons:
            rec[f"fwd_ret_{h}"] = fm.get(f"fwd_ret_{h}")
        recs.append(rec)
    return pd.DataFrame(recs)


# --------------------------------------------------------------------------- #
# (c) NOT-TOPPED single-bar flicker
# --------------------------------------------------------------------------- #
def veto_flicker(frame: pd.DataFrame) -> dict:
    """Single-bar flicker rate of the not-topped veto over one name's replay frame.

    A flicker is a day where not_topped differs from BOTH its neighbours (True→False→True or the
    inverse) — a one-bar oscillator wiggle that silently drops (or re-admits) a name. Returns
    {n_days, n_flips, flip_rate, n_flickers, flicker_rate}."""
    if frame.empty or "not_topped" not in frame:
        return {"n_days": 0, "n_flips": 0, "flip_rate": None,
                "n_flickers": 0, "flicker_rate": None}
    nt = frame["not_topped"].tolist()
    vals = [x for x in nt if x is not None]
    n = len(vals)
    if n < 3:
        return {"n_days": n, "n_flips": 0, "flip_rate": None,
                "n_flickers": 0, "flicker_rate": None}
    flips = sum(1 for a, b in zip(vals[:-1], vals[1:]) if a != b)
    flickers = sum(1 for a, b, cc in zip(vals[:-2], vals[1:-1], vals[2:])
                   if (a == cc) and (a != b))
    return {
        "n_days": n, "n_flips": flips,
        "flip_rate": round(flips / (n - 1), 4),
        "n_flickers": flickers,
        "flicker_rate": round(flickers / (n - 2), 4),
    }


def veto_hysteresis_compare(frame: pd.DataFrame, *, confirm: int = 2, sustained: int = 3) -> dict:
    """Single-bar vs hysteretic not-topped veto precision/recall over one name's veto stream.

    Delegates to engine.hysteresis.veto_precision_recall on the frame's ``not_topped`` series — the
    measured basis on which ``confirm`` is chosen (mission part 2). Returns the per-arm precision /
    recall / flip / flicker, or None when the stream is too short."""
    from engine.hysteresis import veto_precision_recall
    if frame.empty or "not_topped" not in frame:
        return {}
    raw = pd.Series([x for x in frame["not_topped"].tolist() if x is not None])
    if len(raw) < 5:
        return {}
    return veto_precision_recall(raw, confirm=confirm, sustained=sustained)


# --------------------------------------------------------------------------- #
# Panel-level aggregation → the honest numbers
# --------------------------------------------------------------------------- #
def _wilson_ci(k: int, n: int, z: float = 1.96) -> tuple[float, float]:
    """Wilson score interval for k/n (n>0). Honest small-sample bounds."""
    if n <= 0:
        return 0.0, 0.0
    phat = k / n
    denom = 1 + z * z / n
    centre = (phat + z * z / (2 * n)) / denom
    half = z * ((phat * (1 - phat) / n + z * z / (4 * n * n)) ** 0.5) / denom
    return max(0.0, centre - half), min(1.0, centre + half)


def _median_or_none(a) -> float | None:
    a = [x for x in a if x is not None and np.isfinite(x)]
    return round(float(np.median(a)), 5) if a else None


def replay_panel(
    panel: dict[str, pd.Series],
    *,
    max_days: int | None = 250,
    horizons=EDGE_HORIZONS,
    lookahead: int = REPAINT_LOOKAHEAD,
    gate_fn: Callable[[str, pd.Series], dict] | None = None,
    n_tf: int = 3,
) -> dict[str, Any]:
    """Replay a whole {ticker: close Series} panel and return the honest measurement bundle:

        {n_names, n_days_total, n_fresh_fires, repaint, edge, veto_flicker}

    ``repaint`` carries the overall repaint rate (Wilson-CI'd) + the outcome histogram.
    ``edge`` carries provisional-vs-completed median forward returns per horizon (the sign-flip
    check that decides whether the provisional lane must split).
    ``veto_flicker`` carries the panel-median single-bar flip/flicker rate.
    Deterministic and degrade-safe. ``gate_fn`` injectable for the knob sweep."""
    all_fires = []
    flick = []
    hyst = []
    n_days_total = 0
    n_names = 0
    for t, close in panel.items():
        frame = replay_series(t, close, max_days=max_days, gate_fn=gate_fn)
        if frame.empty:
            continue
        n_names += 1
        n_days_total += len(frame)
        flick.append(veto_flicker(frame))
        hc = veto_hysteresis_compare(frame)
        if hc:
            hyst.append(hc)
        fires = repaint_events(frame, lookahead=lookahead)
        if not fires.empty:
            fires = edge_of_fires(t, close, fires, horizons=horizons, n_tf=n_tf)
            fires["ticker"] = t
            all_fires.append(fires)

    fires_df = pd.concat(all_fires, ignore_index=True) if all_fires else pd.DataFrame()
    return {
        "n_names": n_names,
        "n_days_total": int(n_days_total),
        "n_fresh_fires": int(len(fires_df)),
        "repaint": _summarize_repaint(fires_df),
        "edge": _summarize_edge(fires_df, horizons),
        "veto_flicker": _summarize_flicker(flick),
        "veto_hysteresis": _summarize_hysteresis(hyst),
        "config": {
            "max_days": max_days, "horizons": list(horizons), "lookahead": lookahead,
            "FRESH_TICKS": confluence_tiers.FRESH_TICKS, "n_tf": n_tf,
            "fresh_tiers": list(FRESH_TIERS),
        },
    }


def _summarize_hysteresis(hyst: list[dict]) -> dict:
    """Aggregate the single-bar vs hysteretic veto precision/recall across names (median)."""
    if not hyst:
        return {"n_names": 0, "note": "no veto streams"}

    def _med(arm, key):
        vals = [h[arm].get(key) for h in hyst if h.get(arm) and h[arm].get(key) is not None]
        return round(float(np.median(vals)), 4) if vals else None

    return {
        "n_names": len(hyst),
        "confirm": hyst[0].get("confirm"),
        "single_bar": {"precision": _med("single_bar", "precision"),
                       "recall": _med("single_bar", "recall"),
                       "flip_rate": _med("single_bar", "flip_rate"),
                       "flicker_rate": _med("single_bar", "flicker_rate")},
        "hysteretic": {"precision": _med("hysteretic", "precision"),
                       "recall": _med("hysteretic", "recall"),
                       "flip_rate": _med("hysteretic", "flip_rate"),
                       "flicker_rate": _med("hysteretic", "flicker_rate")},
    }


def _summarize_repaint(fires: pd.DataFrame) -> dict:
    if fires.empty:
        return {"n": 0, "repaint_rate": None, "note": "no fresh fires"}
    n = int(len(fires))
    k = int(fires["repaint"].sum())
    lo, hi = _wilson_ci(k, n)
    hist = fires["outcome"].value_counts().to_dict()
    by_tier = {}
    for tier, sub in fires.groupby("tier"):
        kk, nn = int(sub["repaint"].sum()), int(len(sub))
        by_tier[tier] = {"n": nn, "repaint": kk, "rate": round(kk / nn, 4) if nn else None}
    return {
        "n": n, "n_repaint": k,
        "repaint_rate": round(k / n, 4),
        "repaint_ci": [round(lo, 4), round(hi, 4)],
        "outcome_hist": {str(kk): int(vv) for kk, vv in hist.items()},
        "by_tier": by_tier,
    }


def _summarize_edge(fires: pd.DataFrame, horizons) -> dict:
    if fires.empty:
        return {"n": 0, "note": "no fresh fires"}
    prov = fires[fires["provisional"] == True]  # noqa: E712 — explicit bool compare on object col
    comp = fires[fires["provisional"] == False]  # noqa: E712
    out = {"n_provisional": int(len(prov)), "n_completed": int(len(comp)), "by_horizon": {}}
    for h in horizons:
        col = f"fwd_ret_{h}"
        pv = _median_or_none(prov[col].tolist()) if col in prov else None
        cv = _median_or_none(comp[col].tolist()) if col in comp else None
        sign_flip = (pv is not None and cv is not None and (pv < 0 <= cv))
        out["by_horizon"][f"{h}d"] = {
            "provisional_median_fwd": pv,
            "completed_median_fwd": cv,
            "delta": (round(pv - cv, 5) if (pv is not None and cv is not None) else None),
            "provisional_sign_flip_vs_completed": bool(sign_flip),
        }
    return out


def _summarize_flicker(flick: list[dict]) -> dict:
    if not flick:
        return {"n_names": 0, "median_flip_rate": None, "median_flicker_rate": None}
    fr = [d["flip_rate"] for d in flick if d.get("flip_rate") is not None]
    fk = [d["flicker_rate"] for d in flick if d.get("flicker_rate") is not None]
    return {
        "n_names": len(flick),
        "median_flip_rate": _median_or_none(fr),
        "median_flicker_rate": _median_or_none(fk),
        "total_days": int(sum(d.get("n_days", 0) for d in flick)),
        "total_flickers": int(sum(d.get("n_flickers", 0) for d in flick)),
    }
