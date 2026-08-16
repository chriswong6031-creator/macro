"""engine.prophet_live.armed_pack — the nightly provisional-close arming pass (P0 D1).

WHAT IT DOES. For every name in the scored universe it re-runs the SAME close-only
admission gate (:func:`engine.signal_gate.gate`) with candidate provisional closes
appended as tonight's new session bar, and records the price interval over which
:func:`engine.signal_gate.is_buyable` is true. The */5 intraday lane then only has
to compare a delayed live price to those two numbers — it never re-derives a signal
(masterplan §4.1/§4.2). The pack is an OPTIMIZATION; the gate is the truth.

THE CANDIDATE IS APPENDED AS THE NEXT SESSION'S BAR — it never overwrites the as-of
close. A probe series is ``close + [candidate]`` indexed at the next NYSE session
after the store's last bar, because the question this pack exists to answer is "will
TONIGHT's admission gate pass at price X", and tonight's nightly APPENDS a new
session bar to the store — it does not restate the last one. The two constructions
are NOT interchangeable, and the difference is not cosmetic: they differ in length,
in the bucket positions ``engine.session_anchor`` assigns every 2D/3D leg, in the
freshness tick counts ``engine.signal_gate`` compares against ``FRESH_TICKS``, and in
whether signal_quality's reclaim-and-hold has a NEXT bar to resolve on at all — a
replace-series never supplies one, so a ``sub:"pending"`` name read buyable at prices
tonight's gate rejects. RE-MEASURED on the 2026-08-08 store, same universe, same probe
set, only the construction changed: 45 of 180 probed names answer differently at their
own close (42 of 72 board names, 3 of 108 cross candidates) and the armed count moved
98 -> 68. Nothing about the tape changed between those two numbers — the pack was
answering the wrong question for 30 of them. (The pre-fix audit measured the same gap
as 8.0% of ±3% grid points disagreeing.)

SO THE ANCHOR IS MEASURED, NOT ASSUMED. Under the old semantics
``candidate == close.iloc[-1]`` returned the input series value-for-value, which made
the pack's centre verdict and its interval anchor the same number by construction. An
appended bar breaks that identity on purpose, so the two readings are now separate,
both published, and neither stands in for the other:

  ``center_buyable``        tonight's board verdict on the store AS IT STANDS. This is
                            what the boards were built from, what the reconciler grades
                            against, and what tells the evaluator whether a row entered
                            from the board or from a cross. UNCHANGED.
  ``probe_center_buyable``  the gate's answer at today's own close WITH the probe's
                            appended bar — one real gate call, not an inherited one. It
                            is the verdict the published interval reproduces at the
                            as-of close, so it is what the membership check compares
                            against (:func:`engine.prophet_live.interval.self_check`).
                            ``meta.probe_center_flips`` counts where the two disagree.

``tier``/``tier_cascade`` ride along as as-of-close context for display and are not
part of any parity assertion.

Parity is proven by :func:`edge_checks` + :func:`verify_edges`, which re-run the REAL
gate at every PUBLISHED price — on the SAME appended construction the edge was
measured on — before anything ships; see the block comment above them for why
:func:`self_check` alone was not evidence. Any mismatch refuses to publish, because a
missing pack makes the evaluator go dark (honest) while a wrong pack lies, and a level
that could not be verified is withheld rather than shipped.

PROBE SCOPE (disclosed in ``meta.probe_scope``, not silently assumed). The band is
swept only where a product state exists:

  * currently buyable  → both edges, over ``[as_of*(1-band), as_of*(1+band)]``:
    ``fade_px`` (drop below it and tonight's verdict flips false) and
    ``fade_hi_px``.
  * not buyable        → up only, over ``[as_of, as_of*(1+band)]``: ``trigger_px``
    is the lowest provisional close that flips the gate true. A cross DOWN into
    buyable is not an intraday state the evaluator can act on, so paying ~1,700
    extra gate calls a night to find one would buy nothing.

WHY A CAP AND A DEADLINE, NOT A CHEAP SCREEN. One gate call costs ~250 ms on this
universe (measured 2026-07-29: 1,742 names, 242 ms mean at 4 workers), so a full
grid over every name is ~15-20 minutes and does not fit the render budget, which is
law. A cheap far-edge screen was measured and REJECTED: a large rally trips the
not-topped veto, so the far edge is systematically the worst place to look — over a
294-name sample the up-band trigger sat at every grid step from +1% to +15% roughly
uniformly, and screening at +15% alone missed 22 of 35 armable names. Instead every
name gets its centre verdict (that census is cheap and honest), candidates are
ordered by :func:`probe_priority`, and the probe phase runs under BOTH ``max_probe``
and a wall-clock ``max_seconds``. Whatever the budget cuts is named in
``meta.skipped`` — never silently dropped, and never presented as "dormant".

CONTIGUITY IS A RESOLUTION BOUND, NOT A PROOF. The same 294-name sweep found the
buyable region to be a single contiguous run in 59 of 59 armable cases — but it
sampled a 1.25% grid, so it can only say there is no island or notch WIDER than one
cell, and the shipped grid is coarser still (1.875%). A narrower notch inside the
range, or an island between two grid points, is invisible to both the sweep and the
probe, and the pack would describe the range as continuous through it. That is the
honest limit of two thresholds, and it is why every state here is display-tier until
the §6 gauntlet.
Where structure IS visible — more than one run of buyable prices on the grid —
nothing is smoothed: the name ships ``state:"irregular"`` with no numbers,
:func:`interval_contains` answers ``None``, and the evaluator darks it.

Outside the probed span the pack knows nothing at all, so it publishes the span
(``band_lo_px``/``band_hi_px``) and the evaluator darks any price beyond it rather
than extrapolating a membership answer.
"""
from __future__ import annotations

import logging
import math
from datetime import date, datetime, timedelta, timezone
from functools import lru_cache
from typing import Any, Callable, Iterable, Sequence

import pandas as pd

from engine import signal_gate
# The interval contract lives in a stdlib-only sibling so the pandas-free */5 lane
# can read it too; re-exported here because this is where callers expect it.
from engine.prophet_live.interval import (  # noqa: F401
    ADJUSTED, DEFAULT_PACK_ADJUSTMENT, STATES, UNADJUSTED, in_probed_band,
    interval_contains, lower_edge, membership_anchor, membership_mismatches,
    self_check,
)

log = logging.getLogger(__name__)

SCHEMA = "prophet_live.armed/v1"

#: Below this many usable bars a probe cannot say anything the gate does not
#: already say ("insufficient history" for every candidate), so the name ships its
#: centre state and is counted in ``meta.skipped``.
MIN_BARS = 60

#: Emitted prices are rounded to this many decimals. Edges round INTO the measured
#: buyable region (lower up, upper down) so a reported threshold is always a price
#: at which the gate really is buyable.
_PX_DP = 4

_DEFAULTS: dict[str, Any] = {
    # Half-width of the provisional-close band, percent of the as-of close. 15%
    # is far past any plausible intraday move for a liquid name — the band is a
    # bound on the SEARCH, not a claim about the tape.
    "band_pct": 15.0,
    # Structure grid across the probed span, endpoints included. 9 gives 1.875%
    # cells on the up-only span, which 8 halvings refine to ~0.7 bp — inside the
    # ~1 bp the published thresholds claim. Every extra grid point comes straight
    # out of max_probe, so resolution and coverage trade against each other.
    "grid_points": 9,
    "bisect_iters": 8,
    # Ceiling on names given a full grid, ordered by probe_priority. SIZED FROM A
    # MEASURED 4-WORKER PASS, not chosen: 500 produced probed_n=3 / armed_n=0
    # because the probe deadline cut 389 names and verification withheld the rest.
    # Whatever it cuts is counted in meta.skipped.probe_cap and ships probed=False,
    # so the evaluator excludes it from coverage instead of calling it dormant.
    "max_probe": 180,
    # Share of the probe budget — BOTH the wall clock and the name cap — reserved for
    # BOARD names (the two-sided sweep that yields fade_px, the at-risk read). Cross
    # candidates (the up-only sweep that yields trigger_px) get the remainder.
    #
    # Operator ruling: P0's core evidence is the CROSS ledger, so crosses must always
    # be funded — but the at-risk read must not starve either, which a global reorder
    # would simply invert. Ordering alone was not enough: the board class outranks
    # every cross candidate in probe_priority, so on a 4-worker pass it consumed the
    # entire budget and armed 106 fade levels against 4 triggers. The split makes the
    # cross floor an invariant rather than a hope (see class_windows / cross_window).
    "board_probe_share": 0.4,
    # Wall-clock ceiling on the WHOLE pass (census + probe + verification), seconds.
    # The render budget is law and gate cost per name varies ~10x with history depth,
    # so a name count alone cannot bound the step. Whichever binds first is disclosed.
    "max_seconds": 420,
    # A name whose own last bar is this many sessions behind the store tip is
    # probed against a stale close, which is the mixed-asof fabrication trap
    # (masterplan §7). It ships its centre state, unprobed and marked stale.
    "max_lag_sessions": 3,
}


def pack_cfg(cfg: dict | None) -> dict[str, Any]:
    """Resolve the arming config: ``config.yml prophet_live`` over in-code defaults."""
    out = dict(_DEFAULTS)
    try:
        block = (cfg or {}).get("prophet_live") or {}
        for k, dv in _DEFAULTS.items():
            if k in block:
                out[k] = type(dv)(block[k])
    except Exception as exc:  # noqa: BLE001
        log.warning("armed_pack: bad prophet_live config (%s) — using defaults", exc)
    return out


# ─────────────────────────────────────────────────────────────────────────────
# The probe
# ─────────────────────────────────────────────────────────────────────────────

def clean_closes(close: Any) -> pd.Series | None:
    """A float close series with the NaN tail/holes dropped, or None if unusable.

    The breadth caches are wide frames, so a name that stopped trading carries a
    NaN tail; probing that would replace a NaN with a price and invent a bar.
    """
    try:
        s = pd.Series(close).dropna().astype(float)
    except Exception:  # noqa: BLE001
        return None
    if s.empty:
        return None
    return s


# ─────────────────────────────────────────────────────────────────────────────
# CALENDAR THREADING (additive, 2026-08-15, CN-PR-1). Every helper below that has
# to answer "what is the next session" takes an optional ``calendar``. It is a
# MODULE-SHAPED protocol — anything exposing ``is_session(date) -> bool``, which
# both :mod:`lib.nyse_calendar` and :mod:`lib.cn_calendar` do.
#
# ``calendar=None`` IS THE NYSE PATH, BYTE-UNCHANGED. It still goes through
# ``nyse_calendar.sessions_between`` rather than the generic walk, so no US caller
# and no US test changes behaviour or needs an argument. The generic branch exists
# because the two calendars' ``sessions_between`` do not share a return type
# (NYSE returns the list of dates, CN returns a COUNT), so the one primitive they
# genuinely agree on is ``is_session``.
# ─────────────────────────────────────────────────────────────────────────────

#: How far ahead a next-session search may look. The longest mainland closure
#: (Spring Festival / National Day Golden Week) runs ~9-10 calendar days end to end
#: — lib.cn_calendar.MAX_LEGIT_CLOSURE_DAYS is 11 — so 21 clears both markets with
#: room, and a search that exhausts it means the calendar rules are broken, not that
#: the market is shut.
_NEXT_SESSION_HORIZON_DAYS = 21


@lru_cache(maxsize=8192)
def _next_session_after(day: date, calendar: Any = None) -> date:
    """The first session STRICTLY after ``day``, off the repo's own calendar.

    Never weekday arithmetic: a hand-rolled business day puts the appended bar on a
    market holiday, and every 2D/3D bucket the gate reads is a position in the session
    calendar (:mod:`engine.session_anchor`), so one fabricated session re-phases the
    whole cascade. Cached because the probe asks this ~25 times per probed name and
    the answer is a function of one date (and, now, of one calendar).
    """
    if calendar is None:
        from lib.nyse_calendar import sessions_between  # noqa: PLC0415
        ahead = sessions_between(day + timedelta(days=1), day + timedelta(days=14))
        if not ahead:  # pragma: no cover - the longest NYSE closure is a few days
            raise ValueError(f"no NYSE session within 14 days of {day} — calendar rules broken")
        return ahead[0]
    d = day + timedelta(days=1)
    for _ in range(_NEXT_SESSION_HORIZON_DAYS):
        if calendar.is_session(d):
            return d
        d += timedelta(days=1)
    raise ValueError(f"no session within {_NEXT_SESSION_HORIZON_DAYS} days of {day} "
                     f"on {getattr(calendar, '__name__', calendar)} — calendar rules broken")


def next_session_stamp(last: Any, calendar: Any = None) -> pd.Timestamp:
    """The index label the probe's appended bar takes: the next session after ``last``.

    ``last`` need not itself be a session — a store whose tip is a holiday still has a
    well-defined next session, and refusing there would silently unprobe the name.
    """
    ts = pd.Timestamp(last)
    nxt = pd.Timestamp(_next_session_after(ts.date(), calendar))
    return nxt.tz_localize(ts.tz) if ts.tz is not None else nxt


def probe_series(close: pd.Series, candidate: float, calendar: Any = None) -> pd.Series:
    """``close`` with ``candidate`` APPENDED as the NEXT session's bar.

    The provisional close is TOMORROW's bar, not a restatement of today's — see the
    module docstring. Tonight's nightly appends a new session to the store, so a probe
    that replaced the last bar was answering a question no gate is ever asked: it kept
    the series length, the session-anchor bucket positions and the freshness tick
    counts frozen at yesterday's, and it never supplied the NEXT bar that
    signal_quality's reclaim-and-hold resolves a ``pending`` buy on.

    The appended label comes from :func:`next_session_stamp` (the repo NYSE calendar),
    so the new bar lands where tonight's nightly would put it. ``candidate ==
    close.iloc[-1]`` therefore does NOT return the input series — that identity is
    gone by design, and :func:`probe_name` measures the anchor verdict instead of
    inheriting it.
    """
    idx = pd.DatetimeIndex([next_session_stamp(close.index[-1], calendar)])
    tail = pd.Series([float(candidate)], index=idx, dtype="float64", name=close.name)
    return pd.concat([close, tail])


def _buyable_at(ticker: str, close: pd.Series, px: float,
                gate_fn: Callable[[str, Any], dict], calendar: Any = None) -> bool:
    return bool(signal_gate.is_buyable(gate_fn(ticker, probe_series(close, px, calendar))))


def _round_edge(px: float, *, up: bool) -> float:
    """Round INTO the buyable region: lower edges up, upper edges down."""
    scale = 10 ** _PX_DP
    return (math.ceil(px * scale) if up else math.floor(px * scale)) / scale


def _side_safe_round(edge: float | None, as_of_close: float,
                     *, up: bool) -> tuple[float | None, bool]:
    """Round an edge, unless the rounding would move it ACROSS the as-of close.

    Returns ``(price, was_left_unrounded)``. One comparison covers every case: the
    published edge must sit on the same side of today's close as the bisected value
    does. A 1/100-cent rounding step can only cross that line when the boundary
    really is that near today's print — real information, not noise to smooth.

    The earlier version CLAMPED the edge onto the close instead, which made the
    membership self-check pass by construction: a tautology dressed as a parity gate.
    Publishing the full-precision value keeps the number a price the gate genuinely
    accepted, which is what :func:`edge_checks` then re-verifies against the engine.
    """
    if edge is None:
        return None, False
    e = float(edge)
    r = _round_edge(e, up=up)
    if (e <= as_of_close) != (r <= as_of_close):
        return e, True
    return r, False


def _bisect_edge(ticker: str, close: pd.Series, *, false_px: float, true_px: float,
                 iters: int, gate_fn: Callable[[str, Any], dict],
                 calendar: Any = None) -> tuple[float, float, int]:
    """Refine one verdict boundary; returns (known-FALSE bound, known-TRUE bound, calls).

    Invariant on entry and on exit: the gate is false at the first return value and
    true at the second. The published threshold is always the TRUE side, so it never
    names a price the gate would reject — and the FALSE side is kept because the
    independent edge check needs a price the probe genuinely measured as rejected.
    Guessing "one tick below the edge" instead would land INSIDE the final bracket,
    where the verdict is by definition unknown, and the check would be flaky.
    """
    calls = 0
    lo, hi = float(false_px), float(true_px)
    for _ in range(max(0, int(iters))):
        mid = (lo + hi) / 2.0
        calls += 1
        if _buyable_at(ticker, close, mid, gate_fn, calendar):
            hi = mid
        else:
            lo = mid
    return lo, hi, calls


def probe_span(as_of_close: float, center_buyable: bool, band_pct: float) -> tuple[float, float]:
    """The (lo, hi) provisional-close pair swept for a name — see the scope note above."""
    band = float(band_pct) / 100.0
    if center_buyable:
        return (as_of_close * (1.0 - band), as_of_close * (1.0 + band))
    return (as_of_close, as_of_close * (1.0 + band))


def probe_grid(span: tuple[float, float], grid_points: int) -> list[float]:
    """The structure grid across ``span``, endpoints included.

    One definition, used by the probe and by the parity test that re-checks every
    grid point against the real gate — a second copy of this arithmetic would let
    the test verify a grid the pack never evaluated.
    """
    lo, hi = float(span[0]), float(span[1])
    n = max(3, int(grid_points))
    step = (hi - lo) / (n - 1)
    return [lo + step * i for i in range(n)]


def _true_runs(flags: Sequence[bool]) -> list[tuple[int, int]]:
    """Inclusive index ranges of consecutive True values."""
    runs: list[tuple[int, int]] = []
    start: int | None = None
    for i, f in enumerate(flags):
        if f and start is None:
            start = i
        elif not f and start is not None:
            runs.append((start, i - 1))
            start = None
    if start is not None:
        runs.append((start, len(flags) - 1))
    return runs


def centre_record(ticker: str, close: pd.Series, *, cfg: dict[str, Any],
                  center_verdict: dict | None = None,
                  gate_fn: Callable[[str, Any], dict] | None = None) -> dict[str, Any]:
    """Tonight's verdict for one name plus the span a probe would sweep (1 gate call).

    Returns ``{ticker, as_of_close, bar_date, center_verdict, center_buyable,
    eligible, tier, tier_cascade, span, wants_probe, gate_calls}``. ``span`` is the
    (lo, hi) provisional-close pair — see the module docstring on scope. Pass
    ``center_verdict`` to reuse a verdict already computed elsewhere.
    """
    g = gate_fn or signal_gate.gate
    rec: dict[str, Any] = {"ticker": ticker, "gate_calls": 0, "wants_probe": False}
    as_of_close = float(close.iloc[-1])
    rec["as_of_close"] = as_of_close
    rec["bar_date"] = str(pd.Timestamp(close.index[-1]).date())

    v = center_verdict if center_verdict is not None else g(ticker, close)
    if center_verdict is None:
        rec["gate_calls"] += 1
    rec["center_verdict"] = v
    rec["center_buyable"] = bool(signal_gate.is_buyable(v))
    rec["eligible"] = bool((v or {}).get("eligible"))
    rec["tier"] = (v or {}).get("tier")
    rec["tier_cascade"] = (v or {}).get("tier_cascade")

    if len(close) < MIN_BARS or not math.isfinite(as_of_close) or as_of_close <= 0:
        rec["skip"] = "insufficient_history"
        return rec

    # NO ``known`` SEED. The census verdict used to be handed to the probe as a free
    # data point at the as-of close, which was sound only while probe_series REPLACED
    # the last bar (the two calls were byte-identical). With the candidate appended the
    # centre census answers a different question from the probe, so seeding it would
    # plant the board verdict inside the interval; probe_name pays one gate call and
    # measures the anchor for real.
    rec["span"] = probe_span(as_of_close, rec["center_buyable"], cfg["band_pct"])
    rec["wants_probe"] = True
    return rec


def probe_name(ticker: str, close: pd.Series, rec: dict[str, Any], *,
               cfg: dict[str, Any],
               gate_fn: Callable[[str, Any], dict] | None = None,
               calendar: Any = None) -> dict[str, Any]:
    """Structure grid + edge bisection over ``rec["span"]``.

    Returns ``{lower_edge, upper_edge, lower_false, upper_false, irregular,
    buyable_in_band, probe_center_buyable, gate_calls}``. ``irregular`` is set when the
    grid shows more than one run of buyable prices — the gate is not single-interval
    over the band and no threshold can honestly stand in for it.

    ``probe_center_buyable`` is the gate's verdict at the name's OWN as-of close under
    the probe's appended bar. It is measured here with a real gate call rather than
    inherited from the centre census: the census asks "is this name on tonight's
    board", the probe asks "does tonight's gate still admit it at this price", and
    under append semantics those are different questions with different answers for a
    large share of the board (module docstring).
    """
    g = gate_fn or signal_gate.gate
    grid = probe_grid(rec["span"], cfg["grid_points"])
    as_of = rec.get("as_of_close")
    as_of = float(as_of) if as_of is not None else float(close.iloc[-1])
    center = _buyable_at(ticker, close, as_of, g, calendar)
    known = {as_of: center}

    # Snap grid points onto the anchor price, whose verdict was just measured. The
    # as-of close is always ON the grid — it is the centre of the two-sided span and
    # the low end of the up-only one — but only to float precision, and paying a
    # second gate call for the same price is waste this pass cannot afford hundreds of
    # times. On an even ``grid_points`` (config-reachable) the centre is not a grid
    # point and the anchor call is simply an extra one; that is the correct trade,
    # because the membership check has nothing to stand on without it.
    calls = 1
    flags: list[bool] = []
    for i, px in enumerate(grid):
        hit = next((k for k in known if abs(k - px) <= abs(px) * 1e-9), None)
        if hit is not None:
            grid[i] = hit
            flags.append(bool(known[hit]))
            continue
        flags.append(_buyable_at(ticker, close, px, g, calendar))
        calls += 1

    out: dict[str, Any] = {"lower_edge": None, "upper_edge": None,
                           "lower_false": None, "upper_false": None,
                           "irregular": False, "buyable_in_band": any(flags),
                           "probe_center_buyable": bool(center),
                           "gate_calls": calls}
    runs = _true_runs(flags)
    if not runs:
        # Nothing in the band is buyable — the ordinary dormant case.
        return out
    if len(runs) > 1:
        out["irregular"] = True
        return out

    start, end = runs[0]
    iters = int(cfg["bisect_iters"])
    if start > 0:
        false_px, edge, c = _bisect_edge(ticker, close, false_px=grid[start - 1],
                                         true_px=grid[start], iters=iters, gate_fn=g,
                                         calendar=calendar)
        out["lower_edge"], out["lower_false"] = edge, false_px
        out["gate_calls"] += c
    if end < len(grid) - 1:
        false_px, edge, c = _bisect_edge(ticker, close, false_px=grid[end + 1],
                                         true_px=grid[end], iters=iters, gate_fn=g,
                                         calendar=calendar)
        out["upper_edge"], out["upper_false"] = edge, false_px
        out["gate_calls"] += c
    return out


def name_entry(rec: dict[str, Any], probe: dict[str, Any] | None) -> dict[str, Any]:
    """Assemble the published per-name entry from a centre record (+ optional probe).

    Field contract (schema ``prophet_live.armed/v1``):
      ``state``          one of :data:`STATES`.
      ``center_buyable`` the gate verdict at the as-of close on the store AS IT
                         STANDS — tonight's board membership. NOT the interval's
                         anchor; see the next field and the module docstring.
      ``probe_center_buyable``
                         the gate verdict at that same close with the probe's
                         APPENDED next-session bar — the reading every published edge
                         was measured on, and therefore the one the interval
                         reproduces at the as-of close. Probed names only.
      ``trigger_px``     lowest provisional close that is buyable, for a name that
                         is NOT buyable now. Null when none was found in band.
      ``fade_px``        the same lower edge for a name that IS buyable now: below
                         it tonight's verdict flips false. Under append semantics this
                         edge can sit ABOVE the as-of close — that is not a
                         representation bug, it is the honest reading that tonight's
                         gate no longer admits the name at today's price
                         (``probe_center_buyable`` False on a ``center_buyable`` name).
      ``fade_hi_px``     upper edge of the buyable interval; null = unbounded in band.
      ``buyable_in_band`` False = no probed price in the band is buyable.
      ``band_lo_px`` /   the price range actually SWEPT. Outside it the pack knows
      ``band_hi_px``     nothing and the evaluator darks the name — publishing these
                         means the evaluator needs no band arithmetic of its own.
                         Rounded OUTWARD so the evaluable region is never smaller
                         than what was probed. ``band_lo_px`` is 0 for a name that
                         was not buyable at the close (see interval.in_probed_band).
      ``probed``         True when the band was actually swept. False means the
                         budget or the data stopped us: the entry still carries
                         tonight's honest state but NO threshold, and the evaluator
                         leaves it out of coverage rather than calling it dormant.
    """
    as_of_close = round(float(rec["as_of_close"]), _PX_DP)
    entry: dict[str, Any] = {
        "state": "dormant",
        "center_buyable": bool(rec.get("center_buyable")),
        "as_of_close": as_of_close,
        "bar_date": rec.get("bar_date"),
        "tier": rec.get("tier"),
        "tier_cascade": rec.get("tier_cascade"),
        "probed": probe is not None,
    }
    if rec.get("skip"):
        entry["skip"] = rec["skip"]
    if rec.get("stale_sessions"):
        entry["stale_sessions"] = int(rec["stale_sessions"])

    if rec.get("skip") in ("stale_series", "census_deadline"):
        # No gate ran for this name at all, so it has no verdict to report. Saying
        # "dormant" here would count a never-evaluated name as an affirmative
        # "nothing forming", which is the honesty bug m1 names.
        entry["state"] = "stale"
    elif entry["center_buyable"]:
        entry["state"] = "buyable"
    elif rec.get("eligible"):
        entry["state"] = "eligible_t4"

    if probe is None:
        return entry

    # The interval's anchor verdict, published beside the board one because they are
    # different readings and a consumer must not have to guess which it is holding.
    # Set BEFORE the irregular returns: it is a measurement the probe really made, and
    # a name whose structure could not be resolved still learned it.
    entry["probe_center_buyable"] = bool(probe.get("probe_center_buyable"))

    lo_span, hi_span = float(rec["span"][0]), float(rec["span"][1])
    # Outward, and outward of BOTH readings of the span. The probe swept the band
    # around the raw close; a consumer recomputing it from the published (4-dp)
    # close lands up to ~1e-4 away, and either one falling outside the published band
    # would dark a price that was genuinely evaluated. So the band covers the union.
    raw = float(rec["as_of_close"])
    band = (hi_span / raw - 1.0) if raw else 0.0
    entry["band_hi_px"] = _round_edge(max(hi_span, as_of_close * (1.0 + band)), up=True)
    # Non-buyable names get a floor of 0 — their span starts at the as-of close and
    # runs up, and below that close the centre verdict already answers the question
    # for a cross-up gate (see interval.in_probed_band).
    #
    # ...UNLESS THE ANCHOR ITSELF CAME BACK BUYABLE. That floor rests on "the gate says
    # no at the bottom of this span", which the REPLACE probe guaranteed for the whole
    # cross class (its centre call WAS the census call). With the bar appended it is
    # measurable and sometimes false — 3 of 108 cross-class names on the 2026-08-08
    # store are admitted at their own close once tonight's bar exists — and such a name
    # has no lower edge inside its span, so a 0 floor made ``interval_contains`` answer
    # True at every price down to zero, none of which was ever probed. Fail closed: the
    # floor becomes the span low and the evaluator darks below it, exactly as it does
    # for a board name that gapped out of its band.
    if entry["center_buyable"]:
        entry["band_lo_px"] = _round_edge(min(lo_span, as_of_close * (1.0 - band)),
                                          up=False)
    elif probe.get("probe_center_buyable"):
        entry["band_lo_px"] = _round_edge(min(lo_span, as_of_close), up=False)
    else:
        entry["band_lo_px"] = 0.0

    if probe.get("irregular"):
        entry["state"] = "irregular"
        entry["buyable_in_band"] = None
        return entry

    entry["buyable_in_band"] = bool(probe.get("buyable_in_band"))
    # ROUND, BUT NEVER ACROSS THE AS-OF CLOSE. The earlier version clamped the edge
    # ONTO the close in that case, which silently guaranteed the membership check
    # passed — a tautology dressed as a parity gate. Now a rounding step that would
    # cross the close is simply not taken: the full-precision bisected value is
    # published (it is a price the gate really accepted) and the event is counted in
    # meta.unrounded_edges, where a reviewer can see it.
    # The as-of close is STILL the right pivot under append semantics: it is the price
    # the membership check asks about, so a 1/100-cent step across it is exactly the
    # step that would make the published interval contradict the measured anchor.
    lower, unrounded_lo = _side_safe_round(probe.get("lower_edge"), as_of_close, up=True)
    upper, unrounded_hi = _side_safe_round(probe.get("upper_edge"), as_of_close, up=False)
    if unrounded_lo or unrounded_hi:
        entry["unrounded_edge"] = True
    if lower is not None and upper is not None and upper < lower:
        # A degenerate interval cannot be described by two thresholds. Report it as
        # structure we could not resolve rather than publishing an empty range.
        entry["state"] = "irregular"
        entry["buyable_in_band"] = None
        return entry

    # WHICH KEY the lower edge ships under still follows tonight's BOARD membership,
    # not the probe anchor. The two keys are a story about the row — "you hold this and
    # it could fade" vs "you don't and it could cross" — and that story is decided by
    # whether the name is on tonight's published board, which is what ``center_buyable``
    # says and what the evaluator reads for its own ``entered`` label
    # (engine.prophet_live.live_states). Re-keying it off the append anchor would relabel
    # 42 of 72 board rows as crosses on a night when nothing about the board changed.
    if entry["center_buyable"]:
        entry["fade_px"] = lower
        entry["fade_hi_px"] = upper
    else:
        entry["trigger_px"] = lower
        entry["fade_hi_px"] = upper
        if entry["buyable_in_band"] and entry["state"] == "dormant":
            entry["state"] = "near"
    return entry


# ─────────────────────────────────────────────────────────────────────────────
# The INDEPENDENT parity gate (G0.1). This is the one that can actually fail.
#
# :func:`self_check` asks whether the published interval contains the as-of close.
# That is worth asserting — it catches a representation bug — but it is NOT
# independent evidence: it reads the same numbers the assembly just wrote, and
# fuzzing 400 synthetic gates produced zero failures because nothing in the
# assembly path can violate it. The step, the docstrings and the PR body all
# advertised "fail-closed parity" on the back of a check that could not fire.
#
# So the real gate re-runs the REAL gate at the PUBLISHED prices: at each edge
# (must be buyable) and at the false-side bound the bisection actually measured
# (must not be). Rounding, side-safety and derivation are all downstream of the
# probe, so a bug in any of them shows up here as a live engine disagreement.
#
# WHAT THE APPEND CHANGE DID TO THIS GATE. It did not weaken it — the check was
# never "feed the close back and get the same series", it is "feed the PUBLISHED
# PRICE back through the SAME construction the edge was measured on and get the
# same verdict", and probe_series is that construction on both sides. What DID
# change is that the gate is no longer tautological on the semantics axis: under
# replace, feeding the as-of close back reproduced the input series by definition,
# so every check at the anchor passed no matter which question the pack meant to
# answer. It now measures the anchor (probe_name's ``probe_center_buyable``), so a
# semantics regression here shows up as a live disagreement like any other.
# ─────────────────────────────────────────────────────────────────────────────

def edge_checks(entry: dict[str, Any], probe: dict[str, Any] | None) -> list[tuple[float, bool]]:
    """``[(price, expected_buyable), ...]`` re-verifying one name's published edges.

    The false-side prices come from the bisection's own measured bound, never from
    "one tick below the edge": a tick lands inside the final bracket, where the
    verdict is unknown by construction, and the check would be flaky rather than
    strict.
    """
    if not probe or probe.get("irregular") or entry.get("state") == "irregular":
        return []
    out: list[tuple[float, bool]] = []
    lo = lower_edge(entry)
    if lo is not None:
        out.append((lo, True))
        if probe.get("lower_false") is not None:
            out.append((float(probe["lower_false"]), False))
    hi = entry.get("fade_hi_px")
    if hi is not None:
        out.append((float(hi), True))
        if probe.get("upper_false") is not None:
            out.append((float(probe["upper_false"]), False))
    return out


def verify_edges(ticker: str, close: pd.Series, checks: list[tuple[float, bool]],
                 gate_fn: Callable[[str, Any], dict] | None = None,
                 calendar: Any = None) -> tuple[list[str], int]:
    """Re-run the real gate at each checked price; returns (mismatch lines, gate calls).

    ``calendar`` MUST be the same one the probe measured the edge on: the check's whole
    value is that it re-runs the gate through the SAME construction, and an appended bar
    landing on a different session date is a different construction.
    """
    g = gate_fn or signal_gate.gate
    bad: list[str] = []
    for px, expected in checks:
        got = _buyable_at(ticker, close, float(px), g, calendar)
        if got != expected:
            bad.append(f"{ticker}: gate says buyable={got} at published price {px!r} "
                       f"but the pack's interval requires {expected}")
    return bad, len(checks)


# ─────────────────────────────────────────────────────────────────────────────
# Assembly
# ─────────────────────────────────────────────────────────────────────────────

def probe_priority(rec: dict[str, Any]) -> tuple[int, int, float, str]:
    """Sort key deciding who survives ``max_probe`` (lower = probed first).

    Buyable names first (they are on tonight's board and their fade level is the
    at-risk read), then eligible ones, then the rest ordered by the gate's OWN
    projection fields — ``bars_to_cross`` when the cascade produced one, else the
    2D RSI-MACD histogram distance from zero, which is comparable across names
    because it lives in RSI space. Both are already on the verdict: nothing is
    re-derived and no verdict is changed, this only decides who gets budget.
    Ticker breaks ties so the cut is deterministic across rebakes.
    """
    if rec.get("center_buyable"):
        tier = 0
    elif rec.get("eligible"):
        tier = 1
    else:
        tier = 2
    v = rec.get("center_verdict") or {}
    btc, h2 = v.get("bars_to_cross"), v.get("hist_d2")
    try:
        return (tier, 0, float(btc), str(rec.get("ticker") or ""))
    except (TypeError, ValueError):
        pass
    try:
        return (tier, 1, abs(float(h2)), str(rec.get("ticker") or ""))
    except (TypeError, ValueError):
        return (tier, 2, float("inf"), str(rec.get("ticker") or ""))


def _is_armed(entry: dict[str, Any]) -> bool:
    return entry.get("trigger_px") is not None or entry.get("fade_px") is not None


def class_counts(names: dict[str, dict[str, Any]],
                 probe_seconds: dict[str, float] | None = None) -> dict[str, dict[str, Any]]:
    """Per-class probed/armed/eligible counts (+ measured probe seconds).

    The nightly log needs to SHOW the split working. A single armed_n cannot: the run
    that armed 106 fade levels and 4 triggers reported ``armed_n: 110`` and looked fine.
    """
    out: dict[str, dict[str, Any]] = {}
    for cls in CLASSES:
        rows = [e for e in names.values()
                if ("board" if e.get("center_buyable") else "cross") == cls]
        out[cls] = {
            "candidates_n": len(rows),
            "probed_n": sum(1 for e in rows if e.get("probed")),
            "armed_n": sum(1 for e in rows if _is_armed(e)),
            "probe_seconds": round(float((probe_seconds or {}).get(cls, 0.0)), 1),
        }
    return out


def assemble(names: dict[str, dict[str, Any]], *, as_of: str, cfg: dict[str, Any],
             universe_n: int, wanted_n: int, gate_calls: int,
             build_seconds: float, skipped: dict[str, int],
             edges_checked: int = 0, probe_seconds: dict[str, float] | None = None,
             price_adjustment: dict[str, str] | None = None,
             now: datetime | None = None) -> dict[str, Any]:
    """The published ``prophet_live.armed/v1`` payload.

    ``price_adjustment`` is ``{ticker: basis}`` from
    :func:`scripts.build_stock_library.universe_price_adjustment` — the adjustment
    family of the close series each name's edges were probed on (W-L0 gate 3). Every
    edge in this pack is a price ON that series, and the */5 evaluator compares it to a
    RAW vendor print, so the pack has to say which one it is rather than leave the
    consumer to infer it. The payload states the DOMINANT family once and marks only
    the names that differ, because the exceptions — the breadth-cache names, which
    accrue raw closes between rebuilds — are the minority and a per-name string on
    every one of ~2,900 entries would say the same thing 2,700 times.
    """
    ts = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
    states: dict[str, int] = {}
    for e in names.values():
        states[e.get("state", "dormant")] = states.get(e.get("state", "dormant"), 0) + 1
    probed_n = sum(1 for e in names.values() if e.get("probed"))
    armed_n = sum(1 for e in names.values() if _is_armed(e))
    adj_counts = _stamp_price_adjustment(names, price_adjustment)
    return {
        "schema": SCHEMA,
        "as_of": as_of,
        # The basis the edges below are prices on. A name whose series is on a
        # DIFFERENT basis carries its own `price_adjustment`; absent means this one.
        "price_adjustment": DEFAULT_PACK_ADJUSTMENT,
        "built_at": ts.isoformat(timespec="seconds").replace("+00:00", "Z"),
        "band_pct": float(cfg["band_pct"]),
        "grid_points": int(cfg["grid_points"]),
        "bisect_iters": int(cfg["bisect_iters"]),
        "names": names,
        "meta": {
            "universe_n": int(universe_n),
            # Names whose band was actually swept, and of those the ones that came
            # back with a usable threshold. COVERAGE, stated per pack: a consumer
            # that reads probed_n as universe_n is claiming arming it does not have.
            "probed_n": int(probed_n),
            "armed_n": int(armed_n),
            # PER CLASS, because the aggregate hides the thing that matters: a pack that
            # armed only fade levels and a pack that armed a healthy mix report the same
            # armed_n. board = two-sided fade sweeps, cross = up-only trigger sweeps.
            "by_class": class_counts(names, probe_seconds),
            "board_probe_share": float(cfg.get("board_probe_share", 0.4)),
            "wanted_probe_n": int(wanted_n),
            "gate_calls": int(gate_calls),
            # Published prices re-verified against the real gate before publishing
            # (G0.1's fail-closed gate). 0 here on a pack with armed names means the
            # check did not run — treat that as unproven, not as clean.
            "edges_checked": int(edges_checked),
            "build_seconds": round(float(build_seconds), 1),
            "states": states,
            "unrounded_edges": sum(1 for e in names.values() if e.get("unrounded_edge")),
            # Probed names whose APPEND anchor disagrees with tonight's board verdict:
            # the gate admits the name at last night's close but not with tonight's bar
            # appended at that same price, or the reverse. Stated per pack because it is
            # the size of the gap the replace-probe used to hide — a run reporting 0 of
            # a large probed_n is the tell that the probe went back to restating the
            # last bar rather than adding one.
            "probe_center_flips": sum(
                1 for e in names.values()
                if e.get("probe_center_buyable") is not None
                and bool(e["probe_center_buyable"]) != bool(e.get("center_buyable"))),
            # The band is swept UP ONLY for names that are not buyable tonight; a
            # cross down into buyable is not an intraday state, so it is not paid
            # for. Said out loud because a consumer must not read the interval as
            # a two-sided claim for those names.
            "probe_scope": "two_sided_for_buyable__up_only_for_rest",
            "probe_order": "buyable__eligible__bars_to_cross__hist_d2__ticker",
            "skipped": {k: int(v) for k, v in sorted(skipped.items()) if v},
            # Population per price basis, so a consumer can size the exception rather
            # than discover it name by name. `unknown` counts names the universe map
            # did not carry — the honest answer when a group failed to load, and NOT
            # folded into the adjusted count.
            "price_adjustment_counts": adj_counts,
        },
    }


def _stamp_price_adjustment(names: dict[str, dict[str, Any]],
                            by_ticker: dict[str, str] | None) -> dict[str, int]:
    """Mark the off-default names in place; return the per-basis population.

    Called by :func:`assemble` only. With no map (an ad-hoc build, a test) every name
    is counted ``unknown`` and NOTHING is stamped: a pack that cannot see its own
    provenance must not claim the default basis per name — the top-level field already
    states the store's dominant family, and inventing per-name agreement with it would
    turn a missing map into a positive assertion.
    """
    counts: dict[str, int] = {}
    for tkr, entry in names.items():
        basis = (by_ticker or {}).get(tkr)
        if not basis:
            counts["unknown"] = counts.get("unknown", 0) + 1
            continue
        counts[basis] = counts.get(basis, 0) + 1
        if basis != DEFAULT_PACK_ADJUSTMENT:
            entry["price_adjustment"] = basis
    return dict(sorted(counts.items()))


def as_of_date(closes: Iterable[pd.Series]) -> str | None:
    """Store tip = the MAX last-bar date across the universe (the data-through date).

    Not today's wall date: on a stale-store night the pack must say what it is
    actually armed on, and the evaluator's hard staleness gate compares this to
    the last completed session.
    """
    best: pd.Timestamp | None = None
    for s in closes:
        try:
            t = pd.Timestamp(s.index[-1])
        except Exception:  # noqa: BLE001
            continue
        if best is None or t > best:
            best = t
    return str(best.date()) if best is not None else None


def session_lag(bar_date: str, tip: str | None, calendar: Any = None) -> int:
    """Exchange sessions between a name's last bar and the store tip (0 = current).

    Exchange sessions, not weekdays: a holiday week would otherwise read as a
    two-session lag and strip healthy names out of the probe set. ``calendar=None``
    is the NYSE path, unchanged; a module exposing ``is_session`` counts on that
    market's calendar instead.
    """
    if not (bar_date and tip):
        return 0
    try:
        from datetime import date as _date, timedelta as _td  # noqa: PLC0415
        b = _date.fromisoformat(str(bar_date)[:10])
        t = _date.fromisoformat(str(tip)[:10])
        if b >= t:
            return 0
        if calendar is None:
            from lib.nyse_calendar import sessions_between  # noqa: PLC0415
            return len(sessions_between(b + _td(days=1), t))
        n, d = 0, b
        while d < t:
            d += _td(days=1)
            if calendar.is_session(d):
                n += 1
        return n
    except Exception:  # noqa: BLE001
        return 0


def stale_record(ticker: str, close: pd.Series, lag: int) -> dict[str, Any]:
    """The unprobed record for a name whose last bar trails the store tip."""
    return {"ticker": ticker, "gate_calls": 0, "wants_probe": False,
            "as_of_close": float(close.iloc[-1]),
            "bar_date": str(pd.Timestamp(close.index[-1]).date()),
            "center_buyable": False, "eligible": False,
            "tier": None, "tier_cascade": None,
            "skip": "stale_series", "stale_sessions": int(lag)}


#: The two probe classes. A BOARD name is buyable at the as-of close and gets the
#: two-sided sweep that yields ``fade_px`` (the at-risk read); a CROSS candidate is not,
#: and gets the up-only sweep that yields ``trigger_px`` (the intraday cross).
CLASSES: tuple[str, str] = ("board", "cross")


def probe_class(rec: dict[str, Any]) -> str:
    return "board" if rec.get("center_buyable") else "cross"


def class_windows(probe_budget: float, board_share: float) -> tuple[float, float]:
    """``(board wall-clock window, GUARANTEED cross floor)`` for the probe phase.

    Splitting the budget by class is what makes the cross floor an invariant instead of
    a hope. Ordering alone could not do it: every board name outranks every cross
    candidate in :func:`probe_priority`, so a 4-worker pass spent the entire budget on
    the board and armed 106 fade levels against 4 triggers. P0's core evidence is the
    cross ledger, so crosses must always be funded — and a global reorder would just
    invert the starvation onto the at-risk read.
    """
    s = min(max(float(board_share), 0.0), 1.0)
    board = float(probe_budget) * s
    return board, float(probe_budget) - board


def cross_window(probe_budget: float, board_share: float, board_elapsed: float) -> float:
    """The cross class's wall clock, never less than its floor.

    A running gate call cannot be interrupted, so the board phase can overshoot its
    window by up to one call. The ``max`` is the invariant: however long the board class
    actually took, the cross class still gets ``(1 - board_share) * probe_budget``.
    """
    _, floor = class_windows(probe_budget, board_share)
    return max(floor, float(probe_budget) - float(board_elapsed))


def split_probes(recs: dict[str, dict[str, Any]], cfg: dict[str, Any],
                 skipped: dict[str, int]) -> dict[str, list[str]]:
    """Per-class probe orders, best first, with each class's cut recorded in ``skipped``.

    The name cap is split on the SAME share as the wall clock. Capping globally would
    leave the hole the split exists to close: the board class would take all 180 slots
    and the cross class would have wall clock but no names to spend it on.
    """
    share = min(max(float(cfg.get("board_probe_share", 0.4)), 0.0), 1.0)
    cap = int(cfg["max_probe"])
    caps = {"board": int(round(cap * share))}
    caps["cross"] = max(0, cap - caps["board"])

    out: dict[str, list[str]] = {}
    for cls in CLASSES:
        wants = sorted((t for t, r in recs.items()
                        if r.get("wants_probe") and probe_class(r) == cls),
                       key=lambda t: probe_priority(recs[t]))
        limit = caps[cls]
        if len(wants) > limit:
            key = f"probe_cap_{cls}"
            skipped[key] = skipped.get(key, 0) + (len(wants) - limit)
            wants = wants[:limit]
        out[cls] = wants
    return out


def order_probes(recs: dict[str, dict[str, Any]], cfg: dict[str, Any],
                 skipped: dict[str, int]) -> list[str]:
    """Flattened :func:`split_probes` — board slice then cross slice, in spend order."""
    split = split_probes(recs, cfg, skipped)
    return [t for cls in CLASSES for t in split[cls]]


def build_pack(entries: Sequence[tuple[str, Any]], *, cfg: dict[str, Any] | None = None,
               now: datetime | None = None,
               gate_fn: Callable[[str, Any], dict] | None = None,
               calendar: Any = None) -> dict[str, Any]:
    """Serial reference build over ``[(ticker, close_series), ...]``.

    The nightly script fans :func:`centre_record`/:func:`probe_name` across a
    process pool for the ~1,700-name universe; this is the same computation in one
    process, which is what the tests drive. ``max_seconds`` is NOT enforced here —
    the deadline belongs to the pool driver that can cancel outstanding work.
    """
    import time as _time
    c = pack_cfg({"prophet_live": cfg} if cfg is not None else None)
    t0 = _time.time()
    cleaned: list[tuple[str, pd.Series]] = []
    skipped: dict[str, int] = {}
    for tkr, close in entries:
        s = clean_closes(close)
        if s is None or len(s) < 2:
            skipped["no_series"] = skipped.get("no_series", 0) + 1
            continue
        cleaned.append((tkr, s))

    tip = as_of_date(s for _, s in cleaned)
    max_lag = int(c["max_lag_sessions"])

    recs: dict[str, dict[str, Any]] = {}
    series: dict[str, pd.Series] = {}
    gate_calls = 0
    for tkr, s in cleaned:
        lag = session_lag(str(pd.Timestamp(s.index[-1]).date()), tip, calendar)
        if lag > max_lag:
            recs[tkr] = stale_record(tkr, s, lag)
            skipped["stale_series"] = skipped.get("stale_series", 0) + 1
            continue
        r = centre_record(tkr, s, cfg=c, gate_fn=gate_fn)
        gate_calls += r["gate_calls"]
        if r.get("skip"):
            skipped[r["skip"]] = skipped.get(r["skip"], 0) + 1
        recs[tkr] = r
        series[tkr] = s

    wanted = sum(1 for r in recs.values() if r.get("wants_probe"))
    probes: dict[str, dict[str, Any]] = {}
    probe_seconds: dict[str, float] = {}
    split = split_probes(recs, c, skipped)
    for cls in CLASSES:
        t_cls = _time.time()
        for tkr in split[cls]:
            p = probe_name(tkr, series[tkr], recs[tkr], cfg=c, gate_fn=gate_fn,
                           calendar=calendar)
            gate_calls += p["gate_calls"]
            probes[tkr] = p
            if p.get("irregular"):
                skipped["irregular"] = skipped.get("irregular", 0) + 1
        probe_seconds[cls] = _time.time() - t_cls

    names = {t: name_entry(r, probes.get(t)) for t, r in recs.items()}

    # The independent gate, inline in the serial path.
    edges = 0
    bad: list[str] = []
    for tkr, entry in names.items():
        checks = edge_checks(entry, probes.get(tkr))
        if not checks:
            continue
        lines, n = verify_edges(tkr, series[tkr], checks, gate_fn=gate_fn,
                                calendar=calendar)
        bad.extend(lines)
        edges += n
        gate_calls += n
    if bad:
        # build_pack is the reference/serial path used by tests; the CLI owns the
        # refuse-to-publish decision, so surface the finding rather than raising.
        skipped["edge_mismatch"] = len(bad)

    pack = assemble(names, as_of=tip or "", cfg=c, universe_n=len(entries),
                    wanted_n=wanted, gate_calls=gate_calls, edges_checked=edges,
                    probe_seconds=probe_seconds,
                    build_seconds=_time.time() - t0, skipped=skipped, now=now)
    pack["meta"]["edge_mismatches"] = bad
    return pack
