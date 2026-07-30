"""Subsector TURN engine — where in its own cycle is each node, and did it just turn?

The rotation desk (``engine/subsector_rotation.py``) reads Finviz's broad-universe
theme→subsector snapshot: eight *cumulative* horizon returns per node
(1D/1W/1M/MTD/3M/6M/1Y/YTD). Its incumbent metrics treat those eight numbers as eight
independent features. They are not — they are **nested**, and that nesting is the reason
the desk reacts late:

* ``accel = pace(1W) − pace(3M)`` compares the last week against a 13-week window that
  *contains* that same week. The fresh signal is diluted into its own baseline (weight
  5/63) and the difference is dominated by the shared 58-day tail.
* ``rs_mom = mean(z1W, z1M) − mean(z3M, z6M)`` has 1M ⊂ 3M ⊂ 6M, so the
  "momentum of momentum" is mostly one slow, highly autocorrelated component.
* Nothing is scaled by the node's own noise, so a cross-sectional z-score of raw returns
  ranks *volatility* as much as trend: high-beta groups permanently occupy both extremes.
* Nothing knows where a node sits in its own cycle, so "bottom" and "top" cannot be
  expressed at all — only "high/low vs peers right now".

This module fixes the arithmetic. Two ideas do the work.

**1. A term structure is a path.** Cumulative returns at nested horizons algebraically
determine the returns of the *disjoint* segments between them::

    g(h) = 1 + perf[h]/100
    seg(1M ex-1W) = g(1M)/g(1W)      seg(3M ex-1M) = g(3M)/g(1M)      …

Expressed as a geometric weekly pace, those five disjoint segments are a **pace curve**
(oldest → newest), and ``1/g(h)`` for each horizon is a six-knot **level path** normalised
to now = 100. From the pace curve come clean, non-overlapping derivatives — impulse
(newest vs previous segment), acceleration (newest vs the cycle baseline), curvature
(second difference). From the level path come the cycle facts — drawdown from the
reconstructed 1-year peak, run off the reconstructed trough, and position in that range.

*Honest limits of the reconstruction*: six knots cannot see an extreme that happened
inside a segment, so ``pos_in_range`` is a lower bound on the true range and peak/trough
dating is coarse (±the segment span). It is a shape read, not a daily series. Every
field carrying that limitation is named ``*_approx`` or documented as reconstructed.

**2. A move only means something relative to the tape, in units of the node's own noise.**
``data/themes_heatmap/subsector_perf_history.jsonl`` is an append-only point-in-time
archive of the daily snapshot (irreplaceable — Finviz's full-universe aggregates cannot be
rebuilt later). Its ``1D`` column is a genuine daily return series, so every node gets a
realised volatility, and the same archive lets the whole read be **replayed** over the last
N sessions each run — which is what makes the desk reactive without waiting for a state
file to accrue: persistence ("day 3 of this turn"), a real rotation tail, and day-over-day
confirmation are all available on the first run.

Every *turn* derivative is measured on the **excess** pace curve (node pace − the
cross-sectional median pace of that same segment) and scaled by the node's own **tracking
error** (realised vol of its excess daily return). Measured absolutely, a single risk-on
week flags a third of the universe as "turning up" and most of the rest as "topping" — the
detector would be reading the market, not the rotation (verified on the 2026-07-30
cross-section: 92 of 268 nodes in a top state before this correction). Cross-sectional
axes are unaffected by the change — subtracting a cross-sectional constant leaves a z-score
identical — which is exactly why the axes were already market-neutral and the legs were not.
Absolute paces stay in the payload as receipts, alongside the market's own pace, so a
surface can always say "and the whole tape did this".

Cycle position is used ONLY as a precondition — a bottom requires a prior decline, a top
requires a prior advance, and the extreme it turns from must be at least a month old.
It never contributes sign or size to a score. That restriction is deliberate and
load-bearing: ``research/POSTMORTEM_20260714_ROTATION_MISS_BY_FABLE.md`` §4.3 documents how
a ``(50 − pos)/50`` state score structurally fades leaders and buys laggards, and the repo's
own PIT evidence (8,344 stamps) found position predicts nothing at any decile or horizon.
Position tells you *which kind of turn is even possible*, and nothing else. The age gate is
what keeps a node that bottomed five sessions ago out of the "topping" bucket.

Both the price path and the **relative-strength path** (the RS line, reconstructed the same
way from excess returns) supply those preconditions, so a theme whose leadership peaked
three months ago can be read as rolling over even while its price grinds sideways.

Breadth is measured from member horizon returns (``member_perf``, ~1.0 median coverage of
the 941-name universe) and is a *today-only* measurement — member perf is deliberately not
archived, so breadth cannot be replayed. A turn where 8 of 10 members pull away from the
tape is a rotation; one where a single name carries the magnitude is disclosed as
``concentrated`` — shown, not punished.

Doctrine: display/context tier. This module ranks nothing with authority, gates nothing
and sizes nothing. Thresholds below are *interpretable* points on a bounded [0,1] score
(not fitted — there is no forward data yet to fit to); ``engine/subsector_track_record.py``
grades the new rank against the incumbent head-to-head so the ledger, not this docstring,
decides which read is better.

Pure compute. No disk or network I/O — the caller owns loading and persistence.
"""
from __future__ import annotations

import logging
import math
from typing import Iterable, Mapping, Sequence

import numpy as np

log = logging.getLogger(__name__)

SCHEMA = "subsector_rotation.turn.v1"
_EPS = 1e-9      # float-dust guard for "strictly beat" comparisons

# ── segment geometry ─────────────────────────────────────────────────────────────
# (key, cumulative horizon, horizon it is measured against, trading days spanned).
# `None` denominator = the segment starts at "now" (a plain cumulative window).
SEGMENTS: tuple[tuple[str, str, str | None, int], ...] = (
    ("y1x", "1Y", "6M", 126),   # oldest: months 6-12 ago
    ("m6x", "6M", "3M", 63),
    ("m3x", "3M", "1M", 42),
    ("m1x", "1M", "1W", 16),
    ("w1", "1W", None, 5),      # newest weekly segment (contains today)
    ("d1", "1D", None, 1),      # today alone — the fastest sample we have
)
# The pace curve used for derivatives, oldest → newest. `d1` is deliberately excluded:
# a one-day pace is too noisy for curvature and is carried separately as `today_z`.
PACE_CURVE: tuple[str, ...] = ("y1x", "m6x", "m3x", "m1x", "w1")
# Level-path knots, oldest → newest, with their approximate age in trading days.
PATH_KNOTS: tuple[tuple[str, int], ...] = (
    ("1Y", 252), ("6M", 126), ("3M", 63), ("1M", 21), ("1W", 5),
)

PARAMS: dict = {
    # ── noise floor ──
    "vol_min_obs": 8,        # daily returns needed before realised vol is trusted
    "vol_hist_days": 22,     # daily-return window (the archive's current depth)
    "noise_floor_w": 0.35,   # %/week — keeps a dead-quiet node from printing huge z
    "z_clip": 4.0,           # clip robust z-scores (bounded composites, no outlier rule)
    # ── cycle-position preconditions (context gates, never score terms) ──
    "fell_dd_min": 6.0,      # % below the reconstructed 1y peak to be "coming off a fall"
    "rose_run_min": 8.0,     # % above the reconstructed 1y trough to be "extended"
    "extreme_min_age": 21,   # the peak/trough turned from must be ≥ this many days old,
                             # else last week's low would qualify a node as "topping"
    # ── leg scaling: how many noise units earn full credit for a leg ──
    "leg_noise_full": 3.0,      # tracking-error units in the turn itself (`flip`)
    "leg_regime_full": 1.0,     # adverse-trend units for full `regime` credit
    "leg_breadth_span": 0.30,   # participation above 0.5 that earns full breadth credit
    "leg_rsmom_full": 1.5,      # cross-sectional robust-z units for full `rs` credit
    # ── state machine ──
    "arm": 0.45,             # score ≥ arm  → candidate (bottoming / topping)
    "confirm": 0.62,         # score ≥ confirm on `confirm_days` runs → confirmed turn
    "confirm_days": 2,
    "fast": 0.80,            # a violent single-session read confirms immediately
    "exit_days": 3,          # consecutive sub-arm readings before a confirmed state exits
    "ttl": 20,               # sessions a confirmed turn stays "fresh" (mirrors PARAMS_V2)
    "lockout": 10,           # sessions after a TTL/hysteresis exit during which a STILL-
                             # firing node cannot re-announce itself as a fresh turn.
                             # Released early the moment its score drops below `arm`, so a
                             # genuine new turn after a real lapse is never delayed.
    "trend_flat_z": 0.25,    # |trend_z| below this = range, not a trend
    # ── replay depth ──
    "tail_days": 12,         # sessions of replay kept for the rotation tail
    # ── breadth ──
    "breadth_min_members": 3,
    "narrow_top_share": 0.45,   # one member owning this share of total deviation = narrow
    "narrow_min_members": 4,
}

STATES = ("turn_up", "bottoming", "trending_up", "range",
          "trending_down", "topping", "turn_down")

# Plain-word stance per state (EN, ZH). Glance tier: state + what to do, no jargon,
# no falsifier/refutation language (operator 2026-07-27), no buy/sell instruction.
STATE_COPY: dict[str, dict[str, str]] = {
    "turn_up": {
        "en": "Turned up", "zh": "已转上行",
        "say_en": "Fell, then turned — the change is confirmed across sessions.",
        "say_zh": "先跌后转，且已连续多个交易日确认。"},
    "bottoming": {
        "en": "Bottoming", "zh": "筑底中",
        "say_en": "Early signs of a floor. Watch — one session is not a turn.",
        "say_zh": "初现止跌迹象。观察为主——单日不构成转向。"},
    "trending_up": {
        "en": "Rising", "zh": "上行中",
        "say_en": "Already rising. Not a fresh turn — you are joining a move underway.",
        "say_zh": "已在上行。并非新转向——属中途加入。"},
    "range": {
        "en": "Quiet", "zh": "平静",
        "say_en": "No trend and no turn. Nothing to act on here.",
        "say_zh": "无趋势也无转向。此处无需动作。"},
    "trending_down": {
        "en": "Falling", "zh": "下行中",
        "say_en": "Still falling, no floor yet. Waiting costs less than catching it.",
        "say_zh": "仍在下行，尚未见底。等待的代价小于抢反弹。"},
    "topping": {
        "en": "Topping", "zh": "筑顶中",
        "say_en": "Early signs the run is tiring. Watch the exits, don't add.",
        "say_zh": "涨势初现疲态。留意退出，不宜加码。"},
    "turn_down": {
        "en": "Turned down", "zh": "已转下行",
        "say_en": "Ran, then rolled over — the change is confirmed across sessions.",
        "say_zh": "先涨后转弱，且已连续多个交易日确认。"},
}


# ── small numeric helpers ────────────────────────────────────────────────────────
def _fin(v) -> float | None:
    """Coerce to a finite float, or None. Tolerates strings and absurd magnitudes."""
    if v is None:
        return None
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(f) or abs(f) > 1e5:
        return None
    return f


def _mad(arr: np.ndarray) -> float:
    """Median absolute deviation, scaled to be a std-consistent estimator."""
    if arr.size == 0:
        return 0.0
    return float(np.median(np.abs(arr - np.median(arr))) * 1.4826)


def robust_z(values: Mapping[str, float | None], clip: float | None = None) -> dict[str, float]:
    """Cross-sectional robust z-score (median / scaled-MAD), std fallback, clipped.

    Robust because the subsector cross-section carries genuine 40%-in-a-week outliers:
    a mean/std z would let two names set the scale for all 268 nodes.
    """
    clip = PARAMS["z_clip"] if clip is None else clip
    keys = [k for k, v in values.items() if _fin(v) is not None]
    out = {k: 0.0 for k in values}
    if len(keys) < 3:
        return out
    arr = np.array([float(values[k]) for k in keys], dtype=float)
    med = float(np.median(arr))
    scale = _mad(arr)
    if scale <= 1e-9:
        scale = float(arr.std())
    if scale <= 1e-9:
        return out
    for k in keys:
        out[k] = float(np.clip((float(values[k]) - med) / scale, -clip, clip))
    return out


def _ramp(x: float | None) -> float:
    """Linear ramp into [0, 1] — the only shape used to turn a signal into leg credit."""
    if x is None or not math.isfinite(x):
        return 0.0
    return float(min(1.0, max(0.0, x)))


# ── 1. term structure → paces + level path ───────────────────────────────────────
def segment_paces(perf: Mapping[str, float | None]) -> dict[str, float | None]:
    """Disjoint-segment **geometric weekly pace** (percent per week) per SEGMENTS entry.

    ``seg_growth = g(h) / g(denominator)``; pace = ``(seg_growth ** (5/days) - 1) * 100``.
    A segment whose growth factor is non-positive (a > -98% cumulative move, i.e. bad
    data) yields None rather than a complex number.
    """
    g: dict[str, float] = {}
    for h in ("1D", "1W", "1M", "3M", "6M", "1Y"):
        v = _fin(perf.get(h))
        if v is not None:
            gv = 1.0 + v / 100.0
            if gv > 0.02:
                g[h] = gv
    out: dict[str, float | None] = {}
    for key, num, den, days in SEGMENTS:
        gn = g.get(num)
        gd = g.get(den) if den else 1.0
        if gn is None or gd is None or gd <= 0.02:
            out[key] = None
            continue
        grow = gn / gd
        if grow <= 0.02:
            out[key] = None
            continue
        out[key] = float((grow ** (5.0 / days) - 1.0) * 100.0)
    return out


def relative_perf(perf: Mapping[str, float | None],
                  market_perf: Mapping[str, float | None] | None) -> dict[str, float | None]:
    """Excess cumulative returns as a ratio of growth factors — the RS line's own returns.

    ``(g_node / g_market - 1) * 100``, not the arithmetic difference: the ratio is what
    compounds, and feeding it back through :func:`level_path` reconstructs the
    relative-strength line's peak, trough and range on the same footing as price.
    """
    out: dict[str, float | None] = {}
    mp = market_perf or {}
    for h, _ in PATH_KNOTS:
        v, m = _fin(perf.get(h)), _fin(mp.get(h))
        if v is None or m is None:
            out[h] = None
            continue
        gn, gm = 1.0 + v / 100.0, 1.0 + m / 100.0
        out[h] = float((gn / gm - 1.0) * 100.0) if (gn > 0.02 and gm > 0.02) else None
    return out


def level_path(perf: Mapping[str, float | None]) -> dict | None:
    """Six-knot level path normalised to now = 100, plus the cycle facts it implies.

    Returns ``{path, ages, pos_in_range, dd_from_peak, up_from_trough,
    days_since_peak_approx, days_since_trough_approx, n_knots}`` or None when fewer than
    three knots are readable. ``dd_from_peak`` ≤ 0, ``up_from_trough`` ≥ 0, and
    ``pos_in_range`` ∈ [0, 100] with 0 = at the reconstructed 1-year low.
    """
    pts: list[tuple[int, float]] = []
    for h, age in PATH_KNOTS:
        v = _fin(perf.get(h))
        if v is None:
            continue
        gv = 1.0 + v / 100.0
        if gv > 0.02:
            pts.append((age, 100.0 / gv))
    pts.append((0, 100.0))
    if len(pts) < 3:
        return None
    pts.sort(key=lambda p: -p[0])                    # oldest → newest
    ages = [p[0] for p in pts]
    path = [p[1] for p in pts]
    hi_i = int(np.argmax(path))
    lo_i = int(np.argmin(path))
    hi, lo = path[hi_i], path[lo_i]
    rng = hi - lo
    return {
        "path": [round(v, 2) for v in path],
        "ages": ages,
        "pos_in_range": round(float((100.0 - lo) / rng * 100.0), 1) if rng > 1e-9 else 50.0,
        "dd_from_peak": round(float((100.0 / hi - 1.0) * 100.0), 2) if hi > 0 else None,
        "up_from_trough": round(float((100.0 / lo - 1.0) * 100.0), 2) if lo > 0 else None,
        "days_since_peak_approx": ages[hi_i],
        "days_since_trough_approx": ages[lo_i],
        "n_knots": len(path),
    }


# ── 2. noise scale ───────────────────────────────────────────────────────────────
def realized_vol_weekly(daily_pct: Sequence[float | None]) -> float | None:
    """Weekly realised volatility (%) from a daily-return series in percent.

    ``std(daily) * sqrt(5)``. None until ``vol_min_obs`` observations exist — an
    under-sampled vol would make every z-score a fiction.
    """
    vals = [f for v in daily_pct if (f := _fin(v)) is not None]
    if len(vals) < PARAMS["vol_min_obs"]:
        return None
    sd = float(np.std(np.array(vals, dtype=float), ddof=1))
    return sd * math.sqrt(5.0) if math.isfinite(sd) and sd > 0 else None


def _noise_w(paces: Mapping[str, float | None], vol_w: float | None) -> tuple[float, str]:
    """Weekly noise scale + which estimator produced it.

    Uses the LARGER of realised vol and the dispersion of the node's own segment paces.
    Deliberately conservative: whipsaw is this detector's dominant failure mode, and the
    incumbent unnormalised read is still on the page for anyone who wants it hotter.
    """
    curve = [f for k in PACE_CURVE if (f := _fin(paces.get(k))) is not None]
    pace_mad = _mad(np.array(curve, dtype=float)) if len(curve) >= 3 else 0.0
    if vol_w is not None and pace_mad > 0:
        return max(float(vol_w), pace_mad, PARAMS["noise_floor_w"]), "vol+pace"
    if vol_w is not None:
        return max(float(vol_w), PARAMS["noise_floor_w"]), "vol"
    if pace_mad > 0:
        return max(pace_mad, PARAMS["noise_floor_w"]), "pace"
    return PARAMS["noise_floor_w"], "floor"


# ── 3. breadth from member horizon returns (today only — never replayed) ─────────
def member_breadth(members: Iterable[str],
                   member_perf: Mapping[str, Mapping[str, float | None]],
                   market_pace: Mapping[str, float | None] | None = None) -> dict | None:
    """Member participation in the node's newest weekly segment, measured vs the market.

    ``turn_up`` / ``turn_dn`` are the fraction of members whose own EXCESS newest-segment
    pace beats (resp. trails) their own excess previous-segment pace — participation in the
    *change*, relative to the tape. Absolute participation would read ~1.0 for every node
    in a risk-on week and tell you nothing about rotation; ``up_1w`` keeps the absolute
    count as a receipt.

    ``concentrated`` marks a move where one member owns most of the magnitude: disclosed,
    never used to zero a score (a narrow megacap-led bid is a real rotation signature, per
    ROTATION_COMMAND §RC-4 — the failure mode to avoid is punishing it, not showing it).
    """
    mkt = market_pace or {}
    m_w1, m_m1x = _fin(mkt.get("w1")) or 0.0, _fin(mkt.get("m1x")) or 0.0
    abs_w1: list[float] = []
    rel_w1: list[float] = []
    turned_up = turned_dn = 0
    for t in members or ():
        mp = member_perf.get(str(t).strip().upper())
        if not mp:
            continue
        p = segment_paces(mp)
        a, b = _fin(p.get("w1")), _fin(p.get("m1x"))
        if a is None:
            continue
        abs_w1.append(a)
        rel_w1.append(a - m_w1)
        if b is not None:
            # _EPS, not 0: a member exactly at the market pace is not "beating" it, and
            # the geometric pace of a round 10% week lands at 10.000000000000009.
            d = (a - m_w1) - (b - m_m1x)
            if d > _EPS:
                turned_up += 1
            elif d < -_EPS:
                turned_dn += 1
    n = len(abs_w1)
    if n < PARAMS["breadth_min_members"]:
        return None
    arr = np.array(abs_w1, dtype=float)
    rel = np.array(rel_w1, dtype=float)
    mag = np.abs(rel)
    tot = float(mag.sum())
    top_share = float(mag.max() / tot) if tot > 1e-9 else 0.0
    n_dir = turned_up + turned_dn
    return {
        "n": n,
        "up_1w": round(float((arr > _EPS).sum() / n), 3),
        "beat_mkt_1w": round(float((rel > _EPS).sum() / n), 3),
        "turn_up": round(turned_up / n_dir, 3) if n_dir else None,
        "turn_dn": round(turned_dn / n_dir, 3) if n_dir else None,
        "disp_w": round(_mad(arr), 2),
        "med_minus_mean": round(float(np.median(arr) - arr.mean()), 2),
        "top_share": round(top_share, 3),
        "concentrated": bool(top_share >= PARAMS["narrow_top_share"]
                            and n >= PARAMS["narrow_min_members"]),
    }


# ── 4. per-node turn read ────────────────────────────────────────────────────────
def _legs(paces: Mapping[str, float | None], noise: float, *, up: bool,
          breadth_frac: float | None, rs_mom: float | None) -> dict:
    """The four turn legs, each in [0, 1], with the raw z-values kept as receipts.

    The legs are chosen to carry **independent** information. An earlier version scored
    ``flip`` + ``accel`` + ``curve`` + breadth + rs, but on this data the newest excess
    pace dwarfs every older segment (±15%/wk against ±1%/wk), so all three of the first
    legs were monotone in the same difference and maxed out together: a five-leg score
    that was really one dimension in a costume, saturating at 1.000 for dozens of nodes and
    destroying rank information. The four kept legs answer four different questions:

      flip    *How big* is the change, in this node's own tracking error? And did the
              previous segment run the other way — a node already rising and rising faster
              is a continuation, not a bottom.
      regime  *What is it turning from?* Graded on how adverse the node's excess trend was
              (3-6 month segments). A turn out of a beaten-down trend is a turn; a wobble
              in a flat one is noise. Looks only at the past, so it is orthogonal to `flip`.
      rs      *How rare* is the change across the cross-section (robust z of the disjoint
              jerk). A big move on a day when everything moves big is not rotation.
      part    *Who is doing it* — member participation vs the tape. Cross-member, so
              independent of every aggregate term above.

    ``accel`` and ``curve`` remain in the receipts (they are the honest way to say "vs its
    3-6 month baseline" on a surface) but are deliberately not scored.
    """
    s = 1.0 if up else -1.0
    w1, m1x, m3x, m6x = (_fin(paces.get(k)) for k in ("w1", "m1x", "m3x", "m6x"))
    full = PARAMS["leg_noise_full"]
    base_parts = [v for v in (m3x, m6x) if v is not None]
    base = float(np.mean(base_parts)) if base_parts else None

    impulse_z = ((w1 - m1x) / noise) if (w1 is not None and m1x is not None) else None
    accel_z = ((w1 - base) / noise) if (w1 is not None and base is not None) else None
    curve_z = (((w1 - m1x) - (m1x - m3x)) / noise
               if None not in (w1, m1x, m3x) else None)

    prior_opposed = (m1x is not None and s * m1x < 0)
    flip = _ramp(s * impulse_z / full) if (impulse_z is not None and prior_opposed) else 0.0
    regime = (_ramp(-s * base / (noise * PARAMS["leg_regime_full"]))
              if base is not None else 0.0)
    return {
        "flip": round(flip, 3),
        "regime": round(regime, 3),
        "rs": round(_ramp(s * rs_mom / PARAMS["leg_rsmom_full"])
                    if rs_mom is not None else 0.0, 3),
        "part": round(_ramp((breadth_frac - 0.5) / PARAMS["leg_breadth_span"])
                      if breadth_frac is not None else 0.0, 3),
        "_impulse_z": impulse_z,
        "_accel_z": accel_z,
        "_curve_z": curve_z,
        "_base_pace": base,
        "_has_part": breadth_frac is not None,
    }


LEG_WEIGHTS = {"flip": 0.30, "regime": 0.20, "rs": 0.25, "part": 0.25}


def _score(legs: Mapping[str, float]) -> float:
    """Weighted mean of the legs, renormalised over the legs that are actually measurable.

    Renormalisation matters: a node with no priceable members must not be capped at 0.75
    for a missing breadth leg. A missing leg abstains; it does not vote zero.
    """
    tot = 0.0
    wsum = 0.0
    for k, w in LEG_WEIGHTS.items():
        if k == "part" and not legs.get("_has_part"):
            continue
        tot += w * float(legs.get(k) or 0.0)
        wsum += w
    return round(tot / wsum, 3) if wsum > 0 else 0.0


def _precondition(path: Mapping, *, want_fall: bool) -> bool:
    """Was there a real prior move to turn out of, and is the extreme old enough?

    A pure context gate — see the module docstring on why position may never carry sign or
    size. The age term is what stops a five-session-old low from qualifying a node to be
    called "topping".
    """
    if not path:
        return False
    if want_fall:
        v, age = _fin(path.get("dd_from_peak")), path.get("days_since_peak_approx")
        return bool(v is not None and v <= -PARAMS["fell_dd_min"]
                    and (age or 0) >= PARAMS["extreme_min_age"])
    v, age = _fin(path.get("up_from_trough")), path.get("days_since_trough_approx")
    return bool(v is not None and v >= PARAMS["rose_run_min"]
                and (age or 0) >= PARAMS["extreme_min_age"])


def node_read(perf: Mapping[str, float | None], *,
              market_perf: Mapping[str, float | None] | None = None,
              market_pace: Mapping[str, float | None] | None = None,
              rel_vol_w: float | None = None,
              abs_vol_w: float | None = None,
              breadth: Mapping | None = None,
              rs_mom: float | None = None) -> dict:
    """Everything derivable for ONE node from its term structure (+ cross-sectional context).

    ``market_perf`` / ``market_pace`` are the cross-sectional medians; ``rs_mom`` is the
    cross-sectional momentum axis. All three are passed in because they can only be known
    once the whole cross-section is (see :func:`cross_section`). With no market context the
    read degrades to absolute — usable, but it will read the tape instead of the rotation.
    """
    paces = segment_paces(perf)
    mkt = market_pace or {}
    rel_paces = {k: (v - m) if ((v := _fin(paces.get(k))) is not None
                                and (m := _fin(mkt.get(k))) is not None) else _fin(paces.get(k))
                 for k, *_ in SEGMENTS}
    path = level_path(perf) or {}
    rs_path = level_path(relative_perf(perf, market_perf)) or {} if market_perf else {}

    # Turn derivatives live on the EXCESS curve, scaled by tracking error.
    noise, noise_src = _noise_w(rel_paces, rel_vol_w)
    base = [v for k in ("m3x", "m6x") if (v := _fin(rel_paces.get(k))) is not None]
    base_pace = float(np.mean(base)) if base else None

    # Which path qualified is published, not re-derived downstream: a node at its price
    # high whose LEADERSHIP fell and is turning back up is a real read, but a surface that
    # assumes the price path would print "fell 0%" and contradict itself.
    fell_price = _precondition(path, want_fall=True)
    fell_rs = _precondition(rs_path, want_fall=True)
    rose_price = _precondition(path, want_fall=False)
    rose_rs = _precondition(rs_path, want_fall=False)
    fell, rose = (fell_price or fell_rs), (rose_price or rose_rs)

    up_legs = _legs(rel_paces, noise, up=True,
                    breadth_frac=(breadth or {}).get("turn_up"), rs_mom=rs_mom)
    dn_legs = _legs(rel_paces, noise, up=False,
                    breadth_frac=(breadth or {}).get("turn_dn"), rs_mom=rs_mom)
    bottom = _score(up_legs) if fell else 0.0
    top = _score(dn_legs) if rose else 0.0

    d1 = _fin(rel_paces.get("d1"))
    today_z = (d1 / (noise / math.sqrt(5.0))) if d1 is not None else None
    return {
        "pace": {k: (round(v, 2) if (v := _fin(paces.get(k))) is not None else None)
                 for k, *_ in SEGMENTS},
        "pace_rel": {k: (round(v, 2) if (v := _fin(rel_paces.get(k))) is not None else None)
                     for k, *_ in SEGMENTS},
        "pace_mkt": {k: (round(v, 2) if (v := _fin(mkt.get(k))) is not None else None)
                     for k, *_ in SEGMENTS},
        "path": path.get("path"),
        "path_ages": path.get("ages"),
        "pos_in_range": path.get("pos_in_range"),
        "dd_from_peak": path.get("dd_from_peak"),
        "up_from_trough": path.get("up_from_trough"),
        "days_since_peak_approx": path.get("days_since_peak_approx"),
        "days_since_trough_approx": path.get("days_since_trough_approx"),
        "rs_path": rs_path.get("path"),
        "rs_pos_in_range": rs_path.get("pos_in_range"),
        "rs_dd_from_peak": rs_path.get("dd_from_peak"),
        "rs_up_from_trough": rs_path.get("up_from_trough"),
        "rs_days_since_peak_approx": rs_path.get("days_since_peak_approx"),
        "rs_days_since_trough_approx": rs_path.get("days_since_trough_approx"),
        "noise_w": round(noise, 3),
        "noise_src": noise_src,
        "vol_cold": rel_vol_w is None,
        "vol_abs_w": round(abs_vol_w, 3) if abs_vol_w else None,
        "impulse_z": _r3(up_legs["_impulse_z"]),
        "accel_z": _r3(up_legs["_accel_z"]),
        "curve_z": _r3(up_legs["_curve_z"]),
        "trend_z": _r3(base_pace / noise if base_pace is not None else None),
        "today_z": _r3(today_z),
        "base_pace": _r3(base_pace),
        "fell": fell,
        "rose": rose,
        "basis_up": ("price" if fell_price else ("leadership" if fell_rs else None)),
        "basis_dn": ("price" if rose_price else ("leadership" if rose_rs else None)),
        "bottom_score": bottom,
        "top_score": top,
        "legs_up": {k: v for k, v in up_legs.items() if not k.startswith("_")},
        "legs_dn": {k: v for k, v in dn_legs.items() if not k.startswith("_")},
        "breadth": dict(breadth) if breadth else None,
    }


def _r3(v) -> float | None:
    f = _fin(v)
    return round(f, 3) if f is not None else None


# ── 5. cross-section: clean RRG axes + the fast rank ─────────────────────────────
def cross_section(perf_by_key: Mapping[str, Mapping[str, float | None]]) -> dict:
    """Cross-sectional axes computed from DISJOINT segments (the overlap fix).

    * ``rs_ratio_v2`` — leadership *level*: robust z of excess cumulative return over the
      cross-sectional median, averaged over 1M and 3M (same axis meaning as the incumbent,
      robust scale).
    * ``rs_mom_v2`` — leadership *change*: robust z of the newest disjoint segment's pace
      minus the previous one (weight 0.7), blended with the same one step back (0.3). No
      window shares a day with its own baseline, which is what makes this axis fast.

    Also returns the cross-sectional medians the per-node read needs: ``median_perf`` (per
    horizon) and ``median_pace`` (per segment) — "the market" for this universe, which the
    desk defines as the median node, not an index it may not hold prices for.
    """
    keys = list(perf_by_key)
    paces = {k: segment_paces(perf_by_key[k]) for k in keys}

    med: dict[str, float | None] = {}
    for h, _ in PATH_KNOTS:
        col = [f for k in keys if (f := _fin(perf_by_key[k].get(h))) is not None]
        med[h] = float(np.median(col)) if col else None
    med_1d = [f for k in keys if (f := _fin(perf_by_key[k].get("1D"))) is not None]
    med["1D"] = float(np.median(med_1d)) if med_1d else None
    med_pace: dict[str, float | None] = {}
    for seg, *_ in SEGMENTS:
        col = [f for k in keys if (f := _fin(paces[k].get(seg))) is not None]
        med_pace[seg] = float(np.median(col)) if col else None

    z_ex = {}
    for h in ("1M", "3M"):
        z_ex[h] = robust_z({k: (v - med[h]) if (med[h] is not None and (v := _fin(perf_by_key[k].get(h))) is not None) else None
                            for k in keys})

    jerk_now = {k: (a - b) if ((a := _fin(paces[k].get("w1"))) is not None
                               and (b := _fin(paces[k].get("m1x"))) is not None) else None
                for k in keys}
    jerk_prev = {k: (a - b) if ((a := _fin(paces[k].get("m1x"))) is not None
                                and (b := _fin(paces[k].get("m3x"))) is not None) else None
                 for k in keys}
    z_now, z_prev = robust_z(jerk_now), robust_z(jerk_prev)

    nodes: dict[str, dict] = {}
    for k in keys:
        ratio = float(np.mean([z_ex["1M"].get(k, 0.0), z_ex["3M"].get(k, 0.0)]))
        mom = 0.7 * z_now.get(k, 0.0) + 0.3 * z_prev.get(k, 0.0)
        nodes[k] = {"rs_ratio_v2": round(ratio, 3), "rs_mom_v2": round(mom, 3),
                    "paces": paces[k]}
    return {"nodes": nodes, "median_perf": med, "median_pace": med_pace}


def fast_rank(reads: Mapping[str, Mapping]) -> dict[str, float]:
    """The v2 rotation rank — a fast, vol-normalised, breadth-aware composite.

    Parallel to the incumbent ``emerging_score`` (which is untouched). Both are logged and
    graded head-to-head by ``engine/subsector_track_record.py``; the ledger decides.
    """
    keys = list(reads)
    z_acc = robust_z({k: reads[k].get("accel_z") for k in keys})
    z_tod = robust_z({k: reads[k].get("today_z") for k in keys})
    z_brd = robust_z({k: ((reads[k].get("breadth") or {}).get("turn_up")) for k in keys})
    out = {}
    for k in keys:
        out[k] = round(0.40 * float(reads[k].get("rs_mom_v2") or 0.0)
                       + 0.25 * z_acc.get(k, 0.0)
                       + 0.20 * z_brd.get(k, 0.0)
                       + 0.15 * z_tod.get(k, 0.0), 3)
    return out


# ── 6. state machine (replayed over the PIT archive each run) ────────────────────
def _blank_state() -> dict:
    return {"state": "range", "since": None, "age": 0, "arm_up": 0, "arm_dn": 0,
            "contra": 0, "peak_score": 0.0, "persist_up": 0, "persist_dn": 0,
            "lockout": 0}


def _trend_state(trend_z: float | None) -> str:
    t = _fin(trend_z)
    if t is None or abs(t) < PARAMS["trend_flat_z"]:
        return "range"
    return "trending_up" if t > 0 else "trending_down"


def advance_state(prior: Mapping | None, read: Mapping, day: str) -> dict:
    """One deterministic step of the per-node turn state machine.

    Hysteresis in both directions: a candidate needs ``confirm_days`` consecutive
    confirming readings (or one ``fast`` reading — V-recoveries confirm in ~3 sessions per
    the Rotation Command field guide, and a 2-session wait spends most of that), and a
    confirmed state needs ``exit_days`` consecutive sub-arm readings (or ``ttl``) to
    leave. Without this the quadrant read flips daily on noise.
    """
    st = dict(_blank_state())
    st.update({k: v for k, v in (prior or {}).items() if k in st})
    b = float(read.get("bottom_score") or 0.0)
    t = float(read.get("top_score") or 0.0)
    arm, conf, fast = PARAMS["arm"], PARAMS["confirm"], PARAMS["fast"]

    st["persist_up"] = st["persist_up"] + 1 if b >= arm else 0
    st["persist_dn"] = st["persist_dn"] + 1 if t >= arm else 0
    st["arm_up"] = st["arm_up"] + 1 if b >= conf else 0
    st["arm_dn"] = st["arm_dn"] + 1 if t >= conf else 0
    # Re-fire lockout: count down while the node keeps firing, release the moment the
    # condition actually lapses. Without it, a node that stays above `confirm` re-enters a
    # confirmed turn on the session after TTL expiry — resetting `since` and `age`, so a
    # 40-session trend would advertise itself as "day 1 of a fresh turn" forever.
    if max(b, t) < arm:
        st["lockout"] = 0
    elif st["lockout"] > 0:
        st["lockout"] -= 1

    # A read with no realised volatility yet cannot CONFIRM — only arm. Early in a replay
    # (or for a newly listed node) the noise scale falls back to pace dispersion, which is
    # small, so every z is inflated: the first sessions of the 2026-07-30 archive replay
    # printed 29 confirmed upturns that decayed to 3 once vol samples existed. Arming on a
    # cold read is fine; promoting one to a confirmed turn is not.
    cold = bool(read.get("vol_cold"))
    cur = st["state"]
    confirmed = cur in ("turn_up", "turn_down")
    if confirmed:
        live = b if cur == "turn_up" else t
        st["age"] += 1
        st["peak_score"] = max(float(st["peak_score"] or 0.0), live)
        st["contra"] = st["contra"] + 1 if live < arm else 0
        if st["contra"] >= PARAMS["exit_days"] or st["age"] >= PARAMS["ttl"]:
            st.update({"state": _trend_state(read.get("trend_z")), "since": day,
                       "age": 0, "contra": 0, "peak_score": 0.0,
                       "lockout": PARAMS["lockout"]})
        return st

    # not currently confirmed → can arm or confirm. Opposite-signed candidates are
    # mutually exclusive by construction; if both arm, the stronger one owns the node.
    up_first = b >= t
    for want_up in (up_first, not up_first):
        score = b if want_up else t
        armed = st["arm_up"] if want_up else st["arm_dn"]
        if (not cold and not st["lockout"] and score >= conf
                and (armed >= PARAMS["confirm_days"] or score >= fast)):
            new = "turn_up" if want_up else "turn_down"
            if cur != new:
                st.update({"state": new, "since": day, "age": 0, "contra": 0,
                           "peak_score": score})
            return st
        if score >= arm:
            new = "bottoming" if want_up else "topping"
            if cur != new:
                st.update({"state": new, "since": day, "age": 0})
            else:
                st["age"] += 1
            st["peak_score"] = max(float(st["peak_score"] or 0.0), score)
            return st
    new = _trend_state(read.get("trend_z"))
    if cur != new:
        st.update({"state": new, "since": day, "age": 0, "peak_score": 0.0})
    else:
        st["age"] += 1
    return st


def replay(history: Sequence[Mapping], *,
           member_map: Mapping[str, Sequence[str]] | None = None,
           member_perf: Mapping[str, Mapping] | None = None,
           keys: Iterable[str] | None = None) -> dict:
    """Replay the whole read over the append-only PIT archive, oldest → newest.

    ``history`` is ``[{asof, subsectors: {key: {horizon: pct}}}, ...]`` — the archive
    rows, which include today's. Deterministic: same rows in, same states out, so nothing
    depends on a mutable state file that could drift (RC-R2's append-only spirit).

    Breadth is attached on the FINAL day only — member perf is not archived, so replaying
    it would be back-filling today's members onto old dates. The historical legs simply
    abstain on participation (see :func:`_score`).

    Returns ``{asof, reads, states, tails, n_days, warm}``.
    """
    rows = _clean_history(history)
    if not rows:
        return {"asof": None, "reads": {}, "states": {}, "tails": {}, "n_days": 0,
                "warm": False}
    last_i = len(rows) - 1
    want = set(keys) if keys is not None else None

    # Daily-return series per key, in archive order — absolute and EXCESS (vs the
    # cross-sectional median that day). Excess drives the tracking-error denominator.
    daily: dict[str, list[float | None]] = {}
    rel_daily: dict[str, list[float | None]] = {}
    for r in rows:
        subs = r.get("subsectors") or {}
        col = [f for p in subs.values() if (f := _fin((p or {}).get("1D"))) is not None]
        mkt_1d = float(np.median(col)) if col else None
        for k, p in subs.items():
            if want is not None and k not in want:
                continue
            v = _fin((p or {}).get("1D"))
            daily.setdefault(k, []).append(v)
            rel_daily.setdefault(k, []).append(
                (v - mkt_1d) if (v is not None and mkt_1d is not None) else None)

    states: dict[str, dict] = {}
    tails: dict[str, list] = {}
    reads_final: dict[str, dict] = {}
    market_final: dict = {}
    for i, row in enumerate(rows):
        day = str(row.get("asof") or "")
        perf_by_key = {k: v for k, v in (row.get("subsectors") or {}).items()
                       if v and (want is None or k in want)}
        if not perf_by_key:
            continue
        xs = cross_section(perf_by_key)
        nodes, mkt_perf, mkt_pace = xs["nodes"], xs["median_perf"], xs["median_pace"]
        is_last = (i == last_i)
        if is_last:
            market_final = {"perf": mkt_perf, "pace": mkt_pace}
        for k, perf in perf_by_key.items():
            # vol from the returns known ON that day only (no look-ahead).
            win = PARAMS["vol_hist_days"]
            rel_vol = realized_vol_weekly((rel_daily.get(k) or [])[:i + 1][-win:])
            abs_vol = realized_vol_weekly((daily.get(k) or [])[:i + 1][-win:])
            brd = None
            if is_last and member_perf:
                brd = member_breadth((member_map or {}).get(k) or [], member_perf, mkt_pace)
            rd = node_read(perf, market_perf=mkt_perf, market_pace=mkt_pace,
                           rel_vol_w=rel_vol, abs_vol_w=abs_vol, breadth=brd,
                           rs_mom=nodes[k]["rs_mom_v2"])
            rd["rs_ratio_v2"] = nodes[k]["rs_ratio_v2"]
            rd["rs_mom_v2"] = nodes[k]["rs_mom_v2"]
            states[k] = advance_state(states.get(k), rd, day)
            tails.setdefault(k, []).append([rd["rs_ratio_v2"], rd["rs_mom_v2"]])
            if is_last:
                reads_final[k] = rd
    tail_n = PARAMS["tail_days"]
    tails = {k: v[-tail_n:] for k, v in tails.items()}
    for k, st in states.items():
        rd = reads_final.get(k)
        if rd is not None:
            rd["turn_state"] = st["state"]
            rd["turn_since"] = st["since"]
            rd["turn_age"] = st["age"]
            rd["persist_up"] = st["persist_up"]
            rd["persist_dn"] = st["persist_dn"]
            rd["peak_score"] = round(float(st["peak_score"] or 0.0), 3)
            rd["turn_score"] = max(rd.get("bottom_score") or 0.0, rd.get("top_score") or 0.0)
            rd["tail"] = tails.get(k)
    ranks = fast_rank(reads_final)
    for k, rd in reads_final.items():
        rd["rank_score_v2"] = ranks.get(k, 0.0)
    return {"asof": str(rows[-1].get("asof") or ""), "reads": reads_final,
            "states": states, "tails": tails, "n_days": len(rows),
            "market": market_final,
            "warm": len(rows) >= PARAMS["confirm_days"] + PARAMS["exit_days"]}


def _clean_history(history: Sequence[Mapping]) -> list[dict]:
    """Sort oldest → newest, de-duplicate by asof, then **drop non-sessions**.

    A non-session is a row whose payload is identical to the previous kept row. The
    archive is written whenever the nightly runs, and on a weekend or holiday Finviz still
    serves Friday's numbers — 6 of the 22 rows on 2026-07-30 were byte-identical repeats
    (Sat+Sun+Mon of 07-18..07-20 all carried Friday's snapshot). Counting those as
    sessions hands the state machine free confirmations: a candidate armed on Friday would
    "confirm across three sessions" without one new observation, and the repeated ``1D``
    value would pad the volatility sample with a copy of itself.

    The FIRST occurrence is kept, so ``since`` dates land on the session that actually
    produced the numbers.
    """
    by_day: dict[str, dict] = {}
    for r in history or ():
        day = str((r or {}).get("asof") or "").strip()
        if day and (r.get("subsectors") or {}):
            by_day[day] = dict(r)
    out: list[dict] = []
    prev_sig: tuple | None = None
    for day in sorted(by_day):
        row = by_day[day]
        subs = row.get("subsectors") or {}
        sig = tuple(sorted((k, v.get("1D"), v.get("1W"), v.get("1M"), v.get("3M"))
                           for k, v in subs.items() if v))
        if prev_sig is not None and sig == prev_sig:
            continue
        out.append(row)
        prev_sig = sig
    return out


# ── 7. handoff nominations (the rotation-universe candidate lane) ────────────────
def handoff_nominations(reads: Mapping[str, Mapping], meta: Mapping[str, Mapping],
                        *, max_out: int = 8) -> list[dict]:
    """Pair a confirmed roll-over (donor) with a confirmed upturn (receiver) in the same
    parent theme — the "this is a handoff, not two unrelated moves" object.

    These are NOMINATIONS. ``config/rotation_universe.json`` is frozen under
    ``research/ROTATION_UNIVERSE_EXTENSION_PREREG.md`` (registered 2026-07-18) and is not
    touched here: adding series to a pre-registered detector universe would void its
    accrual clock. The nomination lane accrues its own census so a future extension can
    adopt candidates with history already on the board.
    """
    donors: dict[str, list] = {}
    receivers: dict[str, list] = {}
    for k, rd in reads.items():
        m = meta.get(k) or {}
        theme = str(m.get("theme") or "")
        st = rd.get("turn_state")
        if st in ("turn_down", "topping"):
            donors.setdefault(theme, []).append((k, rd))
        elif st in ("turn_up", "bottoming"):
            receivers.setdefault(theme, []).append((k, rd))

    def _strength(rd: Mapping, up: bool) -> float:
        base = float((rd.get("bottom_score") if up else rd.get("top_score")) or 0.0)
        confirmed = 1.0 if rd.get("turn_state") in ("turn_up", "turn_down") else 0.6
        return base * confirmed

    out = []
    for theme, ds in donors.items():
        rs = receivers.get(theme) or []
        if not rs:
            continue
        d_key, d_rd = max(ds, key=lambda p: _strength(p[1], up=False))
        r_key, r_rd = max(rs, key=lambda p: _strength(p[1], up=True))
        conf = round((_strength(d_rd, up=False) + _strength(r_rd, up=True)) / 2.0, 3)
        dm, rm = meta.get(d_key) or {}, meta.get(r_key) or {}
        out.append({
            "theme": theme,
            "theme_zh": dm.get("theme_zh") or theme,
            "donor": {"key": d_key, "name": dm.get("name") or d_key,
                      "name_zh": dm.get("name_zh") or dm.get("name") or d_key,
                      "state": d_rd.get("turn_state"), "since": d_rd.get("turn_since"),
                      "score": d_rd.get("top_score"), "n_members": dm.get("n_members"),
                      "pace_w1": (d_rd.get("pace") or {}).get("w1"),
                      "up_from_trough": d_rd.get("up_from_trough")},
            "receiver": {"key": r_key, "name": rm.get("name") or r_key,
                         "name_zh": rm.get("name_zh") or rm.get("name") or r_key,
                         "state": r_rd.get("turn_state"), "since": r_rd.get("turn_since"),
                         "score": r_rd.get("bottom_score"), "n_members": rm.get("n_members"),
                         "pace_w1": (r_rd.get("pace") or {}).get("w1"),
                         "dd_from_peak": r_rd.get("dd_from_peak")},
            "confidence": conf,
            "both_confirmed": bool(d_rd.get("turn_state") == "turn_down"
                                   and r_rd.get("turn_state") == "turn_up"),
        })
    out.sort(key=lambda e: (e["both_confirmed"], e["confidence"]), reverse=True)
    return out[:max_out]


# ── 8. payload helpers ───────────────────────────────────────────────────────────
# Fields copied onto each rotation-payload row. Additive: every incumbent field
# (rs_ratio, rs_mom, accel, emerging_score, quadrant) is left exactly as it was.
ROW_FIELDS = (
    "pace", "pace_rel", "pace_mkt", "path", "path_ages", "pos_in_range", "dd_from_peak",
    "up_from_trough", "days_since_peak_approx", "days_since_trough_approx",
    "rs_path", "rs_pos_in_range", "rs_dd_from_peak", "rs_up_from_trough",
    "rs_days_since_peak_approx", "rs_days_since_trough_approx",
    "noise_w", "noise_src", "vol_cold", "vol_abs_w", "impulse_z", "accel_z", "curve_z", "trend_z",
    "today_z", "base_pace", "fell", "rose", "basis_up", "basis_dn",
    "bottom_score", "top_score",
    "legs_up", "legs_dn", "breadth", "rs_ratio_v2", "rs_mom_v2", "rank_score_v2",
    "turn_state", "turn_since", "turn_age", "persist_up", "persist_dn", "turn_score",
    "tail",
)


def summarize(reads: Mapping[str, Mapping], meta: Mapping[str, Mapping],
              *, min_members: int = 3, per_bucket: int = 12) -> dict:
    """Highlight buckets keyed on the turn read, with the same breadth floor the
    incumbent highlights use (1-2 member "subsectors" are a stock, not a rotation)."""
    def _ok(k: str) -> bool:
        # UNKNOWN breadth (None) passes: a sector ETF is a broad basket with no member
        # count of its own, and treating unknown as zero would silently empty its buckets.
        n = (meta.get(k) or {}).get("n_members")
        return n is None or int(n) >= min_members

    def _bucket(states: tuple[str, ...], score: str) -> list[str]:
        rows = [(k, rd) for k, rd in reads.items()
                if _ok(k) and rd.get("turn_state") in states]
        rows.sort(key=lambda p: (float(p[1].get(score) or 0.0),
                                 float(p[1].get("persist_up" if score == "bottom_score"
                                                else "persist_dn") or 0)), reverse=True)
        return [k for k, _ in rows[:per_bucket]]

    counts: dict[str, int] = {s: 0 for s in STATES}
    for rd in reads.values():
        st = rd.get("turn_state")
        if st in counts:
            counts[st] += 1
    return {
        "turned_up": _bucket(("turn_up",), "bottom_score"),
        "bottoming": _bucket(("bottoming",), "bottom_score"),
        "turned_down": _bucket(("turn_down",), "top_score"),
        "topping": _bucket(("topping",), "top_score"),
        "counts": counts,
        "params": {k: PARAMS[k] for k in ("arm", "confirm", "confirm_days", "fast",
                                          "exit_days", "ttl", "fell_dd_min",
                                          "rose_run_min")},
        "leg_weights": dict(LEG_WEIGHTS),
    }
