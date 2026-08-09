"""The owner's WEIGHTED tier cascade for the Standout grids — extends signal_gate.

A single signal is one DOOR in a cascade (the sector-cycle engine + the owner's
leadership/rotation read are the other doors); this grades a name into the owner's
ladder, strongest-confirmed -> earliest, each tier weighted by its held-out balance of
earliness-vs-stop-out. Every return carries ``anchor_era`` = ANCHOR_ERA: the 2D/3D buckets
are anchored to an ABSOLUTE session calendar (engine/session_anchor), not to the caller's
first timestamp, so a verdict is a function of the price history alone — ruling
research/SESSION_ANCHOR_ABSOLUTE_CALENDAR_ADJUDICATION_BY_FABLE.md.
Tier table (research/signal_engine/TIERED_CASCADE.md, 110 held-out US names):

  TIER  WEIGHT  definition                                              held-out stop-out
  T1    0.90    3D MACD-RSI x 3D StochRSI, buy-filter endorsed (master)   38.3%   (= signal_gate TAKE)
  T2    1.00    2D MACD-RSI cross  & 3D StochRSI crossed (recent)         40.6%   (operator re-ranked above T1 2026-07-06)
  T3    0.60    2D MACD-RSI PROJECTED<=1-2d & 3D StochRSI already crossed 42.3%   (the early prediction)
  T4    0.40    2D MACD-RSI PROJECTED & 2D StochRSI crossed & ABOVE-200MA 43.1%   (earliest; anti-falling-knife)

Temporal provenance is tier-native and never borrowed from the §7 marker by accident:
``tier_event_date`` is the immutable close that fired T1/T2, while projected T3/T4 carry
null there; ``tier_observed_date`` is the daily session whose close produced this verdict.
The two are equal only for a same-session fire.  ``tier_observation_provisional`` names
forming T1 and projected T3/T4 without changing the incumbent calibrated ``provisional``
badge (which remains T3-only and has downstream display behaviour).

The gradient is GENTLE (~5pp master->earliest) so the earlier tiers get REAL weight, not
token. `sub` = the StochRSI cross came from DEEP oversold (<20) vs a SHALLOW cross (>20).
The assessment found shallow crosses are NOT lower quality (lower stop-out, calmer pullback),
so `sub` is a DISPLAY modifier only — it never lowers the tier weight.

T1 is the validated master (passed in as `take_active` from signal_quality.analyze, so the
chart marker and the grid tier never disagree). T2/T3/T4 are computed here from the daily
close — faithful RSI-MACD (NOT price MACD), leak-free 2D/3D->daily known-date mapping,
close-only (works on every market incl. close-only HK/CN). T4's PROJECTION is leak-free: it
extrapolates the 2D MACD histogram forward from PAST bars only; it never reads the future.
"""
from __future__ import annotations

import os

import numpy as np
import pandas as pd

from engine.hysteresis import hysteretic_not_topped   # W6 #22 veto debounce (opt-in)
from engine.session_anchor import session_positions   # absolute session-calendar anchor (R1-R3)
from engine.technicals import rsi   # faithful Wilder RSI (== Pine ta.rsi)

#: The bucketing ERA this module's verdicts belong to (R5, DT-R16 family). Emitted as
#: ``anchor_era`` on every cascade return and as a tier_stream column; signal_gate copies it
#: onto every verdict. Before it existed, 2D/3D buckets were phased to the caller's first
#: timestamp, so the SAME name graded differently from two loaders the same night; graded
#: records separate the cohorts by this field's presence/value. Any future anchor change
#: mints a NEW string — a graded-population change is dated and labelled, never silent.
#: Ruling: research/SESSION_ANCHOR_ABSOLUTE_CALENDAR_ADJUDICATION_BY_FABLE.md
ANCHOR_ERA = "abs-session-2026-08-06"

RSI_LEN, FAST_LEN, BASE_LEN, SIG_LEN = 14, 14, 60, 5
STOCH_LEN, SMOOTH_K, SMOOTH_D = 14, 3, 3
OB, OS = 80, 20
CONF_W, BUY_RSI_MAX = 8, 65
# FRESHNESS — the board is only "about to cross" + "JUST crossed", never "risen for many days".
# A cross is fresh only while it is <= FRESH_TICKS bars old ON THE SIGNAL'S OWN TIMEFRAME (a
# "tick" = one native bar: 3 days on the 3D master, 2 days on the 2D tiers). Owner endorsed
# 2-tick picks (HON/LOW) as still fresh; the topped-veto (not the tick window) is what kills the
# AMAT case (10 ticks late AND overbought/bearish-crossed). A buy 3+ ticks back is a HOLD.
FRESH_TICKS = 2                   # just-crossed window: this bar through 2 ticks ago (~6d on 3D)
EARLY_CROSS_BARS = 1.5            # 2D cross "projected within ~1-2 days" (bars-to-zero on the 2D grid)

# ── HISTORY FLOOR — the MEASURED warmup requirement, not a round number ──────────────────
# Operator order 2026-08-05 ("200 bar indicator floor, lets lift this?"). The incumbent
# MIN_HISTORY = 200 was a round number matching NO leg's actual warmup: it simultaneously
# locked out names on which every T2/T3 leg was ALREADY computable (159 bars) and admitted
# names on which the 3D RSI-MACD leg was STILL NaN (needs 232) — so the not-topped veto's
# macd_bear leg has been silently fail-open on every 200-231 bar name since the floor was set.
#
# Every number below was MEASURED, not derived, and RE-MEASURED under the absolute session
# anchor (R7, era abs-session-2026-08-06). Buckets are now phased to a fixed reference
# calendar, so a trailing N-bar window's bucket count depends on WHERE the window sits: the
# same N yields ceil(N/n) TF bars when the window starts on a bucket boundary and one MORE
# when it straddles. The floor must therefore be the PHASE-WORST case, not one lucky
# alignment. Basis: REAL NYSE sessions (lib.nyse_calendar) ending 2026-08-04 — real phases,
# real holidays — with the window slid across 14 consecutive reference sessions, which
# covers every 2D/3D/weekly/fortnight phase. Method per offset: truncate to N trailing daily
# bars, ask whether the leg is non-NaN at the final bar, take the smallest N that holds for
# all N' >= N; the tabled floor is the MAX over offsets.
#
# OUTCOME: every session-counted leg re-measured to its INCUMBENT value — the phase-worst
# case IS the old phase-0 business-day measurement, because a window that starts exactly on a
# bucket boundary yields ceil(N/n) TF bars either way, and a real session maps to a
# CONSECUTIVE reference position (holidays are absent from both sides). MIN_HISTORY therefore
# stays 159 and no cohort boundary moves under this era.
#
# The two CALENDAR-WEEK legs (`wbull`, `htf_2w`) are the exception, and NOT because of the
# anchor: `wbull` runs on the untouched pandas W-FRI path, and both are dominated by how many
# calendar weeks a window spans, which depends on HOLIDAY DENSITY rather than bucket phase.
# On real sessions they measure lower (14-phase worst case 376 / 759; worst over a decade of
# window ends 379 / 764) than the tabled 391 / 776. The tabled values are kept: they are the
# NO-HOLIDAY worst case, they are the null-SAFE direction (over-disclosing a leg as
# not-yet-knowable costs nothing; under-disclosing asserts a leg is live when it is not —
# the PLTR error class), neither leg gates any tier, and relaxing them is a separate decision
# from this anchor change (R8 keeps warmup-floor SEMANTICS put). Both numbers are pinned in
# tests/test_confluence_warmup_floor.py so the gap is measured, not assumed.
#
#   leg                          daily bars  gates          short of it, TODAY
#   ---------------------------  ----------  -------------  ---------------------------------
#   rsi_ok    (3D RSI-14)                43  T2 T3 T4       NaN -> False -> no tier at all
#   k2_d2     (2D StochRSI)              63  T4             NaN -> recent2 False
#   recent2   (2D stoch cross)           65  T4             cross not computable
#   fromos2   (d2.rolling(8))            77  T4 confirm2    NaN -> False (OR-arm)
#   k3_d3     (3D StochRSI)              94  T2 T3          NaN -> long_bias False
#   recent3   (3D stoch cross)           97  T2 T3          cross not computable
#   fromos3   (d3.rolling(8))           115  T2 T3 confirm3 NaN -> False (OR-arm)
#   m2_s2     (2D RSI-MACD)             155  T2 T3 T4       no cross, no bars-to-cross
#   mb2       (2D MACD cross)           157  T2             cross not computable
#   imm2      (2D MACD projection)      157  T3 T4          projection not computable
#   imm2 x2   (CONFLUENCE_T3_PERSIST)   159  T3             persistence not readable
#   ---------------------------------------------------------------------------------------
#   above200  (200dMA)                  200  T4 ONLY        NULL + disclosed — never False
#   m3_s3     (3D RSI-MACD)             232  nothing        veto macd_bear leg FAILS OPEN
#   mb3       (3D MACD cross)           235  T1 raw only    T1 needs an explicit take_date
#   wbull     (weekly RSI-MACD)         391  nothing        confirm falls back to the fromos arm
#   htf_2w    (S1/S2 badges)            776  nothing        display badges read False
#
# The floor is the MAX over the legs that GATE eligibility for a tier reachable below 200.
# T4 is deliberately NOT in that max — it self-gates at 200 through its own above200 leg,
# which is correct: a name with no 200dMA cannot be graded "anti-falling-knife". T1's
# raw-cross fallback self-gates at 235; T1 via an explicit ``take_date`` is unaffected
# (the §7 marker carries its own date). Pinned by tests/test_confluence_warmup_floor.py —
# a leg whose warmup moves fails loudly rather than drifting the floor in silence.
LEG_WARMUP_BARS = {
    "rsi_ok": 43, "k2_d2": 63, "recent2": 65, "fromos2": 77,
    "k3_d3": 94, "recent3": 97, "fromos3": 115,
    "m2_s2": 155, "mb2": 157, "imm2": 157, "imm2_persist2": 159,
    "above200": 200, "m3_s3": 232, "mb3": 235, "wbull": 391, "htf_2w": 776,
}
#: The legs that GATE eligibility for a tier reachable below the old 200-bar floor (T2/T3).
GATING_LEGS = ("rsi_ok", "k3_d3", "recent3", "fromos3",
               "m2_s2", "mb2", "imm2", "imm2_persist2")
MIN_HISTORY = max(LEG_WARMUP_BARS[k] for k in GATING_LEGS)   # == 159 (measured, not chosen)
#: T4's own leg. NOT the cascade floor — T4 simply cannot fire below it.
MA200_WARMUP_BARS = LEG_WARMUP_BARS["above200"]
#: The PRE-CHANGE floor. A name tiering on fewer than this many daily bars belongs to the
#: post-2026-08-05 cohort and is stamped ``young_history=True`` all the way to the board row
#: and the candidates store, so the graded record can forever separate the two populations
#: (era law: a graded-population change is dated and labelled, never silent).
YOUNG_HISTORY_BARS = 200

# operator-ratified 2026-07-06 — T2 ranked above T1 for entry quality (fills nearer the
# trough, confirmed-bar low repaint ~9%); T1 remains the highest-precision confirmed state.
WEIGHTS = {"T1": 0.9, "T2": 1.0, "T3": 0.6, "T4": 0.4}
_BLANK = {"tier": None, "weight": 0.0, "sub": None, "eligible": False,
          "bars_to_cross": None, "asof": None, "not_topped": True, "ticks": None,
          "provisional": False, "htf": {"s1": False, "s2": False},
          # Native temporal contract. A blank has no tier, therefore no tier dates.
          "tier_event_date": None, "tier_observed_date": None,
          "tier_observation_provisional": False,
          "hist_d2": None, "hist_d3": None,
          # ── warmup disclosure (2026-08-05) ────────────────────────────────────────────
          # `bars`         daily bars the cascade actually read (None = never got that far)
          # `young_history` True = fewer than YOUNG_HISTORY_BARS; the graded-cohort label
          # `above200`     True/False/None — None means the 200dMA is NOT YET KNOWABLE.
          #                NEVER False on an unknowable value (the PLTR precedent).
          # `null_legs`    {leg: plain-word reason} for every leg short of its warmup
          # `veto_legs_null` the SAME disclosure for the not-topped veto's own legs (F6/R4)
          # `anchor_era`   the bucketing era this verdict belongs to (R5)
          "bars": None, "young_history": None, "above200": None, "null_legs": None,
          "veto_legs_null": None, "anchor_era": ANCHOR_ERA,
          # `evaluated` False = the cascade CRASHED or never ran — every other field in
          # this blank is "not knowable", NOT a verdict. A consumer that treats a blank
          # as a clean pass converts a data failure into a buyable T1 (audit F2
          # 2026-08-06: the exception return asserted not_topped=True + ticks=None,
          # which signal_gate read as fresh-and-clean and admitted at weight 0.9).
          "evaluated": True}

# HTF super-tier constants (S1/S2 display-only, rank-neutral, 2026-07-06)
# Frozen per research/signal_engine/HTF_SUPER_TIERS_ADJUDICATION_AND_PREREG.md Part 2.
HTF_FW = 2           # freshness window: MACD cross within this many native TF bars (FW=2 ratified)
HTF_CONF_W = 8       # StochRSI cross window (same as CONF_W — use the module constant)
HTF_BTC = 1.0        # bars-to-cross threshold for S2 2W MACD pending leg
_HTF_BLANK = {"s1": False, "s2": False}


def _veto_confirm() -> int:
    """Confirm length for the not-topped veto (env ``VETO_HYSTERESIS_CONFIRM``). Unset/1 = the
    incumbent single-bar veto, unchanged. >=2 = the N-bar Schmitt debounce (engine/hysteresis):
    the veto only trips/clears after N consecutive daily bars agree, killing the one-bar
    appear/vanish/reappear flicker. Measured at confirm=2 on the W6 #22 replay (219 US names):
    flicker 1.6% -> 0.0%, flip rate 7.2% -> 4.4%, recall 97.7%, precision 95.6%
    (calibration/provisional_replay.json veto_hysteresis). OPT-IN per the masterplan flip
    criterion — the single-bar flicker measured small, so this is offered, not forced."""
    try:
        return max(1, int(os.environ.get("VETO_HYSTERESIS_CONFIRM", "1")))
    except (TypeError, ValueError):
        return 1


def _t3_persist() -> int:
    """Persistence window for T3 firing (env ``CONFLUENCE_T3_PERSIST``). Unset/2 = the T3 raw
    condition must hold on N=2 consecutive evaluable sessions before T3 fires (the repaint-
    hardening default). N=1 restores the legacy single-session behaviour. Measured at N=2 on a
    2026-07-06 backtest (110 held-out US + CN names): repaint US 15.5%->9.4% / CN 16%->0%,
    mean 21d excess +0.16%->+0.41%, median lead 11.0->10.5 sessions, event count -35%.
    This is a DE-ESCALATION (strictly fewer fires). Calibration/provisional_replay repaint
    figures (23.8% US / 15.1% CN) and the T3 tooltip copy predate this change."""
    try:
        return max(1, int(os.environ.get("CONFLUENCE_T3_PERSIST", "2")))
    except (TypeError, ValueError):
        return 2


def _null_legs(n_bars: int) -> dict:
    """Plain-word disclosure for every leg whose warmup ``n_bars`` has not reached.

    A leg short of its warmup is NULL — "not knowable yet" — never False. The PLTR
    narration-gap postmortem is the binding precedent: an ``above200: False`` stamped on an
    unknowable value read as "below its 200-day average" and excluded a live winner from
    every lane that tests that field. Absence of evidence is disclosed here, not asserted
    as evidence of absence. Returns a FRESH dict each call (``_BLANK`` is shallow-copied,
    so a shared mutable would alias across every blank return)."""
    return {leg: f"needs {need} daily bars, has {n_bars}"
            for leg, need in LEG_WARMUP_BARS.items() if n_bars < need}


#: The not-topped veto's three legs -> the LEG_WARMUP_BARS entry each one reads. The stoch
#: pair warms at k3_d3 (94 bars); macd_bear reads the 3D RSI-MACD, which warms at m3_s3 (232).
_VETO_LEGS = {"stoch_ob": "k3_d3", "stoch_bear": "k3_d3", "macd_bear": "m3_s3"}


def _veto_legs_null(n_bars: int) -> dict:
    """Plain-word disclosure for every NOT-TOPPED VETO leg that ``n_bars`` cannot yet compute.

    F6 (adjudication R4). ``macd_bear`` compares ``float(m3_d[-1]) < float(s3_d[-1])``, and
    ``float(nan) < float(nan)`` is False — so on every 159-231 bar name the leg has been
    silently FAIL-OPEN while ``not_topped=True`` shipped as if all three legs had been checked.

    The boolean's decision arithmetic is deliberately UNCHANGED (see the veto block in
    :func:`cascade`): tri-stating it would flow through every ``if not not_topped`` consumer as
    falsy and blank the whole 159-231 bar cohort, silently reversing the operator's 2026-08-05
    floor-lift. What changes is that the gap is now DISCLOSED rather than implied — the same
    shape as ``null_legs`` and the same binding precedent (the PLTR ``above200`` narration gap):
    never assert the unknowable, name it. Returns a FRESH dict each call.
    """
    return {leg: f"needs {LEG_WARMUP_BARS[src]} daily bars, has {n_bars}"
            for leg, src in _VETO_LEGS.items() if n_bars < LEG_WARMUP_BARS[src]}


def _ema(s, span):
    return s.ewm(span=span, min_periods=span).mean()


def _rsi_macd(c):
    r = rsi(c, RSI_LEN)
    m = _ema(r, FAST_LEN) - _ema(r, BASE_LEN)
    return m, _ema(m, SIG_LEN)


def _stoch_rsi_kd(c):
    r = rsi(c, RSI_LEN)
    lo, hi = r.rolling(STOCH_LEN).min(), r.rolling(STOCH_LEN).max()
    rawk = (r - lo) / (hi - lo).replace(0, np.nan) * 100
    k = rawk.rolling(SMOOTH_K).mean()
    return k, k.rolling(SMOOTH_D).mean()


def _xup(a, b):
    return (a > b) & (a.shift(1) <= b.shift(1))


def _since(cond):
    pos = np.arange(len(cond))
    last = pd.Series(np.where(cond.to_numpy(), pos, np.nan), index=cond.index).ffill()
    return pd.Series(pos, index=cond.index) - last


def _tf_bars(daily, n, market: str = "US"):
    """The n-session timeframe grid, bucketed on the ABSOLUTE session calendar.

    ``bucket(d) = session_anchor.session_positions(d, market) // n`` — a function of
    ``(reference calendar, date)`` alone, so the grid is IDENTICAL no matter how much leading
    history the caller passed. That is the whole repair: the previous ``resample("2B"/"3B")``
    anchored its bin edges to the SERIES' FIRST timestamp, so one dropped leading bar flipped
    the tier on 13/232 data/stocks names and the not-topped veto on 27/232, and the deep
    data/stocks loader disagreed with the 2014-start baskets/ohlcv loader about live
    buyability the same night. Ruling + measured blast radius:
    research/SESSION_ANCHOR_ABSOLUTE_CALENDAR_ADJUDICATION_BY_FABLE.md (R1-R3).

    Returns ``(tf_close, known)``: the per-bucket LAST close and its known-date, both indexed
    by that bucket's last SESSION date (the old bin LABELS were pandas' synthetic bin edges
    and nothing downstream read them semantically — every consumer reads ``known``'s VALUES
    and does positional TF math). The return SHAPE is unchanged: a value Series plus a
    Timestamp Series of the same length.
    """
    s = daily.dropna()
    if not s.index.is_monotonic_increasing:
        s = s.sort_index()                       # resample used to sort; keep that contract
    s = s[~s.index.duplicated(keep="last")]
    if s.empty:
        return pd.Series(dtype="float64"), pd.Series(dtype="datetime64[ns]")
    # One vectorized groupby over absolute bucket ids. `s` is sorted, so `.last()` per bucket
    # IS the last close and the max date — no Python-level apply on the hot path.
    b = session_positions(s.index, market) // n
    g = pd.DataFrame({"v": s.to_numpy(), "d": s.index.to_numpy()}).groupby(b, sort=True).last()
    known_dates = pd.DatetimeIndex(g["d"])
    return (pd.Series(g["v"].to_numpy(), index=known_dates),
            pd.Series(known_dates, index=known_dates))


def _to_daily(tf_series, known, di, how="ffill"):
    kd = pd.Series(tf_series.to_numpy(), index=pd.to_datetime(known.to_numpy()))
    kd = kd[~kd.index.duplicated(keep="last")].sort_index()
    if how == "ffill":
        return kd.reindex(di, method="ffill")
    out = pd.Series(False, index=di)
    pos = di.searchsorted(kd.index, side="left")
    for p, v in zip(pos, kd.to_numpy()):
        if v and p < len(di):
            out.iloc[p] = True
    return out


def _ticks_since(known, when) -> int | None:
    """How many native-TF bars (ticks) have CLOSED since `when` (a date), measured on a TF grid
    whose per-bar known-dates are `known`. 0 = `when` is in the latest bar (just printed); 1 =
    one tick ago. None if undatable. This is the "1 tick = 3 days on the 3D" yardstick."""
    if when is None:
        return None
    try:
        kv = pd.to_datetime(pd.Series(known).to_numpy())
        return int((kv > pd.Timestamp(when)).sum())
    except Exception:
        return None


def _session_iso(value, sessions: pd.Index) -> str | None:
    """Return ``value`` as an ISO date only when it is an observed input session.

    This is deliberately stricter than date parsing.  A malformed value, weekend,
    future date, or marker date from a different tape/era returns null rather than
    creating apparently precise tier provenance.
    """
    if value is None or sessions is None or len(sessions) == 0:
        return None
    try:
        stamp = pd.Timestamp(value)
    except (TypeError, ValueError):
        return None
    if pd.isna(stamp):
        return None
    if stamp.tzinfo is not None:
        stamp = stamp.tz_localize(None)
    stamp = stamp.normalize()
    try:
        idx = pd.DatetimeIndex(sessions)
        if idx.tz is not None:
            idx = idx.tz_localize(None)
        idx = idx.normalize()
        if int(idx.get_indexer([stamp])[0]) < 0:
            return None
    except (TypeError, ValueError):
        return None
    return str(stamp.date())


def _tier_dates(
    tier: str | None,
    observed_date: str | None,
    *,
    t1_event_date: str | None = None,
    t2_event_date: str | None = None,
) -> dict:
    """Return the additive tier-native temporal contract.

    T1 is the §7 master and may use its explicitly supplied knowability close. T2 is
    the cascade's own confirmed 2D-cross close. T3/T4 are projections: the observation
    is real, but no event has fired, so their event date is null by construction.
    """
    event_date = (t1_event_date if tier == "T1"
                  else t2_event_date if tier == "T2" else None)
    return {
        "tier_event_date": event_date,
        "tier_observed_date": observed_date if tier else None,
        "tier_observation_provisional": tier in ("T3", "T4"),
    }


def cascade(daily_close: pd.Series, *, take_active: bool = False,
            take_date=None, take_event_date=None, market: str = "US",
            event_latch=None, latch_key: str | None = None) -> dict:
    """Grade a close series into the weighted tier cascade. The board is ONLY "about to cross"
    (T3/T4, projected) + "JUST crossed" (T1/T2, within FRESH_TICKS on the signal's own TF) —
    never a name that crossed several ticks ago and has been rising. T1 = `take_active` (the
    validated master from signal_quality) but ONLY while its arrow is <= FRESH_TICKS 3D-ticks
    old AND the 3D momentum is still constructive (not-topped). `take_date` = the §7 buy
    marker's legacy bucket-open date (used only to age the take in 3D ticks; falls back
    to the raw 3D cross). ``take_event_date`` is that marker's separately emitted
    knowability close and is provenance only — it never changes tiering or freshness.
    ``market`` picks the reference session calendar the 2D/3D buckets are anchored to (US
    default; signal_gate infers it from the ticker suffix — session_anchor R3). Highest
    active tier wins. Returns {tier, weight, sub, eligible, bars_to_cross, asof, not_topped,
    ticks, ..., veto_legs_null, anchor_era}. Never raises.

    ``event_latch`` (engine.confluence_latch.EventLatch) + ``latch_key`` (the ticker) make the
    T2 event history IMMUTABLE: a bar's verdict is written once, when that bar was the as-of
    bar, and restored from the store thereafter. Without it the incomplete trailing bucket's
    known-date advances nightly and un-fires events on bars that already printed — see that
    module's docstring for the measured case. DEFAULT None = byte-identical to before, so only
    the caller that opts in (the CN board) changes behaviour."""
    try:
        c = daily_close.dropna()
        if not isinstance(c.index, pd.DatetimeIndex):
            c = c.copy(); c.index = pd.to_datetime(c.index)
        n_bars = len(c)
        di = c.index
        observed_date = _session_iso(di[-1], di) if n_bars else None
        t1_event_date = _session_iso(take_event_date, di)
        if n_bars < MIN_HISTORY:
            v = dict(_BLANK, bars=n_bars, young_history=True, above200=None,
                     null_legs=_null_legs(n_bars),
                     veto_legs_null=_veto_legs_null(n_bars))
            if take_active:               # thin history: trust the §7 marker (can't tick-age it)
                v.update(tier="T1", weight=WEIGHTS["T1"], eligible=True,
                         **_tier_dates("T1", observed_date,
                                       t1_event_date=t1_event_date))
            return v
        last = len(di) - 1
        young = n_bars < YOUNG_HISTORY_BARS
        nulls = _null_legs(n_bars)
        veto_nulls = _veto_legs_null(n_bars)
        # HTF super-tier (S1/S2): display-only, rank-neutral, computed once per call.
        # Kept inside the try so any HTF failure degrades to {"s1":False,"s2":False} via _BLANK.
        htf = _compute_htf(daily_close, market)

        # 2D RSI-MACD: confirmed cross (T2 leg) + imminent-cross projection (T3/T4 leg)
        sm, smk = _tf_bars(c, 2, market)
        m2, s2 = _rsi_macd(sm)
        h2 = m2 - s2
        mb2 = _xup(m2, s2)
        slope2 = h2 - h2.shift(1)
        btc = (-h2 / slope2)
        imm2 = ((h2 < 0) & (slope2 > 0) & (btc > 0) & (btc <= EARLY_CROSS_BARS)).fillna(False)

        # 3D StochRSI (T1/T2/T3 stoch leg) + 3D RSI-MACD (master cross + not-rolled-over veto)
        ss3, sk3 = _tf_bars(c, 3, market)
        k3, d3 = _stoch_rsi_kd(ss3)
        sb3 = _xup(k3, d3)
        recent3 = _since(sb3) <= CONF_W
        fromos3 = d3.rolling(CONF_W).min() < OS
        r14_3 = rsi(ss3, RSI_LEN)
        m3, s3 = _rsi_macd(ss3)            # 3D RSI-MACD: the master cross + rollover guard
        mb3 = _xup(m3, s3)
        # 2D StochRSI (T4 leg)
        k2, d2 = _stoch_rsi_kd(sm)
        sb2 = _xup(k2, d2)
        recent2 = _since(sb2) <= CONF_W
        fromos2 = d2.rolling(CONF_W).min() < OS

        wk = c.resample("W-FRI").last().dropna()
        wm, ws = _rsi_macd(wk)
        wbull = (wm >= ws).shift(1)
        ma200 = c.rolling(200).mean()

        td = lambda s, kn, how="ffill": _to_daily(s, kn, di, how)
        mb2_d = td(mb2.fillna(False), smk, "event")
        imm2_d = td(imm2.fillna(False), smk).fillna(False)
        btc_d = td(btc, smk)
        m2_d, s2_d = td(m2, smk), td(s2, smk)
        mb3_d = td(mb3.fillna(False), sk3, "event")
        m3_d, s3_d = td(m3, sk3), td(s3, sk3)
        recent3_d = td(recent3.fillna(False), sk3).fillna(False)
        fromos3_d = td(fromos3.fillna(False), sk3).fillna(False)
        k3_d, d3_d = td(k3, sk3), td(d3, sk3)
        r14_d = td(r14_3, sk3)
        recent2_d = td(recent2.fillna(False), smk).fillna(False)
        fromos2_d = td(fromos2.fillna(False), smk).fillna(False)
        wbull_d = wbull.reindex(di, method="ffill").fillna(False).astype(bool)
        # NOTE the two faces of above200. The SERIES keeps `.fillna(False)` because that is
        # what T4's conjunction needs — a name whose 200dMA is unknown must NOT collect the
        # anti-falling-knife tier, so T4 self-gates at MA200_WARMUP_BARS. The PUBLISHED
        # scalar below is the opposite: NULL when the average is not computable, because a
        # downstream lane reading `above200: False` would take it as "trading below its
        # 200-day average" — a claim the data cannot support (the PLTR precedent).
        above200 = (c > ma200).fillna(False)
        above200_pub = (bool(above200.iloc[last])
                        if bool(pd.notna(ma200.iloc[last])) else None)

        confirm3 = (wbull_d | fromos3_d)
        rsi_ok = (r14_d < BUY_RSI_MAX).fillna(False)
        long_bias = bool(m2_d.iloc[last] >= s2_d.iloc[last] and k3_d.iloc[last] >= d3_d.iloc[last])

        # NOT-TOPPED / NOT-ROLLED-OVER veto (the AMAT guard) — a buy is only valid while the
        # higher-TF momentum is still constructive. Reject if the 3D StochRSI is OVERBOUGHT or
        # has bearish-crossed (k<d, made a high and turned down), or the 3D RSI-MACD is below
        # its signal. AMAT (3D stoch k=82/d=86, k<d, overbought) fails on the first two.
        #
        # FAIL-OPEN ON AN UNKNOWABLE LEG IS AN EXPLICIT DECISION (F6 / adjudication R4), not an
        # oversight: `float(nan) < float(nan)` is False, so below a leg's warmup that leg cannot
        # veto. Between MIN_HISTORY and m3_s3's warmup the macd_bear leg is structurally
        # unknowable and the veto rests on the two stoch legs alone. Tri-stating not_topped
        # would read falsy in every `if not not_topped` consumer and blank the whole young
        # cohort — silently reversing the operator's 2026-08-05 floor lift, which is not this
        # change's call. So the arithmetic stands and `veto_legs_null` (published on every
        # return) NAMES each leg that could not be checked. Do not "fix" this to block.
        k3n, d3n = float(k3_d.iloc[last]), float(d3_d.iloc[last])
        m3n, s3n = float(m3_d.iloc[last]), float(s3_d.iloc[last])
        stoch_ob   = (k3n >= OB) or (d3n >= OB)        # in the overbought zone -> extended entry
        stoch_bear = k3n < d3n                          # k below d -> rolled over / not crossed up
        macd_bear  = m3n < s3n                          # 3D RSI-MACD outright below signal
        not_topped = not (stoch_ob or stoch_bear or macd_bear)
        confirm = _veto_confirm()
        if confirm > 1:
            # Hysteretic veto (opt-in, see _veto_confirm): debounce the PER-DAY veto stream —
            # the same daily basis the W6 #22 replay measured flicker on — so one noisy bar on
            # the provisional resample tail can no longer blank/re-admit a name. NaN warmup days
            # compare False on every leg -> constructive, matching the scalar's float-NaN path.
            nt_raw = ~((k3_d >= OB) | (d3_d >= OB) | (k3_d < d3_d) | (m3_d < s3_d))
            not_topped = bool(hysteretic_not_topped(nt_raw, confirm=confirm).iloc[-1])

        # Display-tier 2D/3D RSI-MACD histogram as of the latest daily bar — the same m−s
        # spreads the tier legs read, exposed (incl. on blank returns) so boards can render
        # D/2D/3D direction glyphs. Sign is the contract; NaN warmup → None. Never a gate,
        # rank or stage input here.
        def _hist_last(m_s, s_s):
            try:
                h = float(m_s.iloc[last]) - float(s_s.iloc[last])
                return round(h, 4) if np.isfinite(h) else None
            except Exception:
                return None
        hist_d2 = _hist_last(m2_d, s2_d)
        hist_d3 = _hist_last(m3_d, s3_d)

        # 3D-tick age of the operative buy arrow: the §7 take/pending DATE if supplied, else the
        # raw 3D RSI-MACD cross. Exposed on every return (incl. blank) so the caller can age a
        # pending master too. 0 = arrow on the latest 3D bar; 1 = one tick (3 days) ago.
        idx3 = np.where(mb3_d.fillna(False).to_numpy())[0]
        cross3_date = di[int(idx3[-1])] if len(idx3) else None
        t1_ticks = _ticks_since(sk3, take_date if take_date is not None else cross3_date)
        blank = dict(_BLANK, asof=str(di[last].date()), not_topped=not_topped, ticks=t1_ticks,
                     htf=htf, hist_d2=hist_d2, hist_d3=hist_d3,
                     bars=n_bars, young_history=young, above200=above200_pub,
                     null_legs=nulls, veto_legs_null=veto_nulls)
        # T2 = a JUST-crossed 2D-MACD x 3D-stoch buy: the 2D arrow is <= FRESH_TICKS 2D-ticks old
        #
        # PIT LATCH (engine/confluence_latch): a fired event may never be un-fired.  The 2D cross
        # is stamped at its own CLOSED bucket's known-date, but recent3_d is ffilled from the 3D
        # known-date — and the trailing 3D bucket is INCOMPLETE, so its known-date advances every
        # session and de-annotates the bar the 2D event sits on.  The conjunction then un-fires
        # on a bar that ALREADY PRINTED, the last event falls back many ticks past FRESH_TICKS,
        # and the name leaves every lane at once (300363.SZ: 2026-08-05 rank 1 -> 08-06 absent
        # -> +20.02% on 08-07).  The latch restores each already-observed bar to the verdict
        # written when it WAS the as-of bar.  None (every caller but the CN board) = unchanged.
        #
        # COMPUTED AND LATCHED BEFORE THE not_topped RETURN, deliberately: whether the
        # conjunction FIRED on a bar is a property of that bar's own legs, independent of
        # today's not-topped veto.  Latching after the early return would leave every
        # vetoed-day bar unrecorded — exactly the bars most likely to be erased tomorrow —
        # and the latch would silently do nothing on the names that need it.
        t2_buy = (mb2_d & recent3_d & confirm3 & rsi_ok).fillna(False)
        if event_latch is not None:
            t2_buy = event_latch.stabilize(latch_key or "", t2_buy)

        if not not_topped:
            return blank                                # topped/rolled-over: never a fresh buy

        # T1 master = the validated held take, but ONLY while JUST-crossed: its arrow is <=
        # FRESH_TICKS old on the 3D grid (1 tick = 3 days). A take 2+ ticks back has "risen for
        # many days" -> it is a HOLD, not a fresh entry, and drops off the board.
        t1_fresh = bool(take_active and t1_ticks is not None and t1_ticks <= FRESH_TICKS)

        idx2 = np.where(t2_buy.to_numpy())[0]
        t2_event_date = _session_iso(di[int(idx2[-1])], di) if len(idx2) else None
        t2_ticks = _ticks_since(smk, di[int(idx2[-1])]) if len(idx2) else None
        t2_active = bool(t2_ticks is not None and t2_ticks <= FRESH_TICKS and long_bias)
        # T3 = 2D MACD projected <=1-2d AND 3D stoch already crossed (ABOUT TO cross — anticipation)
        # Persistence hardening (CONFLUENCE_T3_PERSIST, default 2): T3 only fires when the 2D
        # imminence condition (imm2) holds for at least N consecutive 2D-bucket evaluations (the
        # repainting component). The stable legs (recent3/confirm3/rsi_ok) are checked on the
        # current daily bar only. N=1 restores legacy single-bucket firing. Cuts repaint
        # US 15.5%->9.4% / CN 16%->0% at the cost of ~0.5 sessions median lead (DE-ESCALATION).
        _t3_n = _t3_persist()
        if _t3_n <= 1:
            t3_active = bool((imm2_d & recent3_d & confirm3 & rsi_ok).iloc[last])
        else:
            # imm2 is a 2D-frequency series; check the last N buckets are ALL True, then verify
            # the stable daily-level legs hold on today's bar. Rolling min over the 2D-TF imm2
            # and map to the last daily bar via imm2_d (ffill from 2D known-dates).
            imm2_persist = imm2.rolling(_t3_n, min_periods=_t3_n).min().fillna(False)
            imm2_persist_d = td(imm2_persist.astype(float), smk).fillna(0).astype(bool)
            t3_active = bool((imm2_persist_d & recent3_d & confirm3 & rsi_ok).iloc[last])
        # T4 = 2D MACD projected AND 2D stoch crossed AND above the 200MA (earliest about-to-cross)
        confirm2 = (wbull_d | fromos2_d)
        t4_active = bool((imm2_d & recent2_d & above200 & confirm2 & rsi_ok).iloc[last])

        # highest active tier wins (all already gated on not_topped above)
        if t1_fresh:
            tier, deep, ticks = "T1", bool(fromos3_d.iloc[last]), t1_ticks
        elif t2_active:
            tier, deep, ticks = "T2", bool(fromos3_d.iloc[last]), t2_ticks
        elif t3_active:
            tier, deep, ticks = "T3", bool(fromos3_d.iloc[last]), 0   # not crossed yet
        elif t4_active:
            tier, deep, ticks = "T4", bool(fromos2_d.iloc[last]), 0
        else:
            return blank
        btc_last = btc_d.iloc[last]
        return {
            "tier": tier, "weight": WEIGHTS[tier], "eligible": True,
            "sub": ("deep" if deep else "shallow"),
            "bars_to_cross": (round(float(btc_last), 2)
                              if (tier in ("T3", "T4") and pd.notna(btc_last)) else None),
            "asof": str(di[last].date()), "not_topped": True, "ticks": ticks,
            # PROVISIONAL basis (W6 #22): T3 is a projection off the INCOMPLETE 2D resample tail
            # and repaints at a measured 23.8% US / 15.1% CN of fresh fires when the bucket
            # completes — above the ~15% flip criterion. T1/T2 measured fine (5.3%/8.8%), so
            # only T3 carries the flag (calibration/provisional_replay.json repaint.by_tier).
            "provisional": tier == "T3",
            "htf": htf,   # S1/S2 display-only badges (rank-neutral)
            "hist_d2": hist_d2, "hist_d3": hist_d3,   # display-only glyph feed
            # warmup disclosure — see _BLANK. `young_history` is the graded-cohort label
            # (era law); `above200` is None, never False, when the 200dMA is unknowable;
            # `veto_legs_null` names each not-topped leg the history could not check (F6).
            "bars": n_bars, "young_history": young,
            "above200": above200_pub, "null_legs": nulls,
            "veto_legs_null": veto_nulls, "anchor_era": ANCHOR_ERA,
            **_tier_dates(tier, observed_date, t1_event_date=t1_event_date,
                          t2_event_date=t2_event_date),
        }
    except Exception:
        # Crash path: "not evaluated" must be distinguishable from "passed" — the blank's
        # not_topped=True/ticks=None otherwise reads as fresh-and-clean downstream (F2).
        return dict(_BLANK, null_legs={}, evaluated=False)


def _ticks_since_vec(known: pd.Series, cross_pos_daily: np.ndarray, di: pd.DatetimeIndex,
                     fresh_ticks: int | None = None) -> np.ndarray:
    # `fresh_ticks` is ACCEPTED AND IGNORED (audit F8 2026-08-06): freshness is applied by
    # the caller (tier_stream's override at its own call sites), never inside this counter.
    # The parameter stays for call-site stability; do not "fix" a sweep by threading it here.
    """Vectorized per-day tick-age of the most-recent cross, on the TF grid whose per-bar
    known-dates are ``known``. ``cross_pos_daily`` is a daily-length int array giving, for each
    daily bar, the daily index of the last cross at-or-before it (or -1 if none). Returns the
    per-day tick age (native-TF bars closed since that cross AND on-or-before the current day —
    the point-in-time count, NOT the full-series count), matching the scalar _ticks_since run on
    the series truncated at each day. The ≤-current-day bound is essential: without it the stream
    would count every FUTURE TF bar and never look fresh (the interior-day leak that a naive
    full-series pass introduces)."""
    kv = pd.to_datetime(pd.Series(known).to_numpy()).values      # TF known-dates (sorted asc)
    di_vals = di.values
    out = np.full(len(di), np.iinfo(np.int32).max, dtype=np.int64)
    for i in range(len(di)):
        cp = cross_pos_daily[i]
        if cp < 0:
            continue
        when = di_vals[cp]
        today = di_vals[i]
        # ticks whose known-date is strictly AFTER the cross and AT-OR-BEFORE the current day —
        # exactly what _ticks_since(known_truncated_at_i, cross) counts point-in-time.
        out[i] = int(((kv > when) & (kv <= today)).sum())
    return out


def tier_stream(daily_close: pd.Series, *, fresh_ticks: int | None = None,
                market: str = "US") -> pd.DataFrame:
    """VECTORIZED per-day tier for EVERY daily bar. BASIS CAVEAT (audit F3 2026-08-06):
    interior rows read the last COMPLETED bucket, but the FINAL row sits on the in-progress
    partial bucket `_tf_bars` still emits — the live board's provisional basis. The last row
    and the interior rows are therefore NOT one basis; a consumer reading a historical day D
    must truncate the series at D BEFORE calling (the prophet_stage_shadow pattern), or its
    day-D read can differ from what the gate saw on ~8% of days. Settled-day parity with
    :func:`cascade` is pinned by tests/test_provisional_replay.py::
    test_tier_stream_matches_cascade_on_settled_days (reproduction requires take_active=True;
    cascade awards no T1 from the raw cross alone, and the live board's §7-validated T1 set
    is NOT a subset of this stream's — 5/18 sampled live T1 days were absent here).

    The provisional-basis replay compares this stream (completed buckets) against the per-day live
    ``cascade`` (provisional tail) to measure the repaint (#22). T1 here uses the raw 3D RSI-MACD
    cross as ``take`` (cascade's own fallback when no §7 take_date is supplied), so the stream is a
    self-contained close-only signal; the live board's T1 (validated §7 master) is a strict subset.

    Returns a daily-indexed frame: tier (T1..T4|None), weight, ticks, not_topped, eligible, sub,
    s1/s2 and a constant ``anchor_era`` column (R5 — the bucketing era every row belongs to).
    ``fresh_ticks`` overrides the module FRESH_TICKS for a knob sweep; ``market`` picks the
    reference session calendar (session_anchor R3). Never raises → empty frame."""
    ft = FRESH_TICKS if fresh_ticks is None else int(fresh_ticks)
    try:
        c = daily_close.dropna()
        if not isinstance(c.index, pd.DatetimeIndex):
            c = c.copy(); c.index = pd.to_datetime(c.index)
        if len(c) < MIN_HISTORY:
            return pd.DataFrame()
        di = c.index
        n = len(di)

        sm, smk = _tf_bars(c, 2, market)
        m2, s2 = _rsi_macd(sm)
        h2 = m2 - s2
        mb2 = _xup(m2, s2)
        slope2 = h2 - h2.shift(1)
        btc = (-h2 / slope2)
        imm2 = ((h2 < 0) & (slope2 > 0) & (btc > 0) & (btc <= EARLY_CROSS_BARS)).fillna(False)

        ss3, sk3 = _tf_bars(c, 3, market)
        k3, d3 = _stoch_rsi_kd(ss3)
        sb3 = _xup(k3, d3)
        recent3 = _since(sb3) <= CONF_W
        fromos3 = d3.rolling(CONF_W).min() < OS
        r14_3 = rsi(ss3, RSI_LEN)
        m3, s3 = _rsi_macd(ss3)
        mb3 = _xup(m3, s3)
        k2, d2 = _stoch_rsi_kd(sm)
        sb2 = _xup(k2, d2)
        recent2 = _since(sb2) <= CONF_W
        fromos2 = d2.rolling(CONF_W).min() < OS

        wk = c.resample("W-FRI").last().dropna()
        wm, ws = _rsi_macd(wk)
        wbull = (wm >= ws).shift(1)
        ma200 = c.rolling(200).mean()

        td = lambda s, kn, how="ffill": _to_daily(s, kn, di, how)
        mb2_d = td(mb2.fillna(False), smk, "event")
        imm2_d = td(imm2.fillna(False), smk).fillna(False)
        m2_d, s2_d = td(m2, smk), td(s2, smk)
        mb3_d = td(mb3.fillna(False), sk3, "event")
        m3_d, s3_d = td(m3, sk3), td(s3, sk3)
        recent3_d = td(recent3.fillna(False), sk3).fillna(False)
        fromos3_d = td(fromos3.fillna(False), sk3).fillna(False)
        k3_d, d3_d = td(k3, sk3), td(d3, sk3)
        r14_d = td(r14_3, sk3)
        recent2_d = td(recent2.fillna(False), smk).fillna(False)
        fromos2_d = td(fromos2.fillna(False), smk).fillna(False)
        wbull_d = wbull.reindex(di, method="ffill").fillna(False).astype(bool)
        above200 = (c > ma200).fillna(False)

        confirm3 = (wbull_d | fromos3_d)
        confirm2 = (wbull_d | fromos2_d)
        rsi_ok = (r14_d < BUY_RSI_MAX).fillna(False)
        long_bias = ((m2_d >= s2_d) & (k3_d >= d3_d)).fillna(False)

        # veto (per-day, vectorized) — matches the scalar not_topped
        k3n, d3n = k3_d.to_numpy(), d3_d.to_numpy()
        m3n, s3n = m3_d.to_numpy(), s3_d.to_numpy()
        stoch_ob = (k3n >= OB) | (d3n >= OB)
        stoch_bear = k3n < d3n
        macd_bear = m3n < s3n
        not_topped = ~(stoch_ob | stoch_bear | macd_bear)

        # per-day daily index of the last 3D cross (T1 raw fallback) and last T2 buy
        mb3_np = mb3_d.fillna(False).to_numpy().astype(bool)
        last_cross3 = _last_true_pos(mb3_np)
        t1_ticks = _ticks_since_vec(sk3, last_cross3, di, ft)

        t2_buy = (mb2_d & recent3_d & confirm3 & rsi_ok).fillna(False).to_numpy().astype(bool)
        last_t2 = _last_true_pos(t2_buy)
        t2_ticks = _ticks_since_vec(smk, last_t2, di, ft)

        imm2_np = imm2_d.to_numpy().astype(bool)
        recent3_np = recent3_d.to_numpy().astype(bool)
        confirm3_np = confirm3.fillna(False).to_numpy().astype(bool)
        confirm2_np = confirm2.fillna(False).to_numpy().astype(bool)
        rsi_ok_np = rsi_ok.to_numpy().astype(bool)
        recent2_np = recent2_d.to_numpy().astype(bool)
        above200_np = above200.to_numpy().astype(bool)
        long_bias_np = long_bias.to_numpy().astype(bool)
        fromos3_np = fromos3_d.to_numpy().astype(bool)
        fromos2_np = fromos2_d.to_numpy().astype(bool)

        t1_fresh = (last_cross3 >= 0) & (t1_ticks <= ft)                    # raw-cross T1 fallback
        t2_active = (last_t2 >= 0) & (t2_ticks <= ft) & long_bias_np
        # T3 persistence hardening (CONFLUENCE_T3_PERSIST, default 2): apply rolling all-True
        # over N consecutive 2D-bucket evaluations of imm2 (the repainting component) before
        # mapping to daily — matching cascade()'s 2D-TF rolling-min approach. N=1 = legacy.
        _t3_n = _t3_persist()
        if _t3_n <= 1:
            imm2_persist_d = imm2_d.fillna(False)
        else:
            imm2_persist_tf = imm2.rolling(_t3_n, min_periods=_t3_n).min().fillna(False)
            imm2_persist_d = td(imm2_persist_tf.astype(float), smk).fillna(0).astype(bool)
        imm2_persist_np = imm2_persist_d.to_numpy().astype(bool)
        t3_active = imm2_persist_np & recent3_np & confirm3_np & rsi_ok_np
        t4_active = imm2_np & recent2_np & above200_np & confirm2_np & rsi_ok_np

        tier = np.array([None] * n, dtype=object)
        weight = np.zeros(n)
        ticks = np.full(n, np.nan)
        sub = np.array([None] * n, dtype=object)
        elig = np.zeros(n, dtype=bool)
        for i in range(n):
            if not not_topped[i]:
                continue
            if t1_fresh[i]:
                tier[i], weight[i], ticks[i] = "T1", WEIGHTS["T1"], t1_ticks[i]
                sub[i] = "deep" if fromos3_np[i] else "shallow"
            elif t2_active[i]:
                tier[i], weight[i], ticks[i] = "T2", WEIGHTS["T2"], t2_ticks[i]
                sub[i] = "deep" if fromos3_np[i] else "shallow"
            elif t3_active[i]:
                tier[i], weight[i], ticks[i] = "T3", WEIGHTS["T3"], 0
                sub[i] = "deep" if fromos3_np[i] else "shallow"
            elif t4_active[i]:
                tier[i], weight[i], ticks[i] = "T4", WEIGHTS["T4"], 0
                sub[i] = "deep" if fromos2_np[i] else "shallow"
            else:
                continue
            elig[i] = True
        # HTF super-tier streams (S1/S2): display-only, rank-neutral boolean columns.
        # Computed on the completed-bucket basis (same convention as the T1-T4 stream).
        htf_s1, htf_s2 = _compute_htf_stream(daily_close, market)
        # Align to di (the dropna'd close index) — reindex fills missing dates with False.
        htf_s1 = htf_s1.reindex(di, fill_value=False).fillna(False).astype(bool)
        htf_s2 = htf_s2.reindex(di, fill_value=False).fillna(False).astype(bool)
        return pd.DataFrame({"tier": tier, "weight": weight, "ticks": ticks,
                             "not_topped": not_topped, "eligible": elig, "sub": sub,
                             "s1": htf_s1.to_numpy(), "s2": htf_s2.to_numpy(),
                             # constant column, not a per-row measurement: every row in this
                             # frame was bucketed under ANCHOR_ERA (R5).
                             "anchor_era": ANCHOR_ERA}, index=di)
    except Exception:
        return pd.DataFrame()


def _last_true_pos(mask: np.ndarray) -> np.ndarray:
    """For each position i, the index of the most-recent True at-or-before i (or -1). Vectorized."""
    n = len(mask)
    idx = np.where(mask, np.arange(n), -1)
    return np.maximum.accumulate(idx)


# ---------------------------------------------------------------------------
# HTF super-tier helpers (S1/S2 — display-only, rank-neutral, 2026-07-06)
# Pre-registration: research/signal_engine/HTF_SUPER_TIERS_ADJUDICATION_AND_PREREG.md Part 2.
# Reference implementation: scripts/_bt_htf_super_tiers.py (validated; logic must match exactly).
# ---------------------------------------------------------------------------

#: A Friday, and the phase origin of the absolute fortnight grid (R6).
_EPOCH_FRIDAY = pd.Timestamp("1970-01-02")


def _completed_resample(daily: pd.Series, rule: str):
    """Return completed bars only — the in-progress tail bucket is dropped.
    Pattern: entry_primitives._completed_resample (RUL-31 PIT gate).
    Returns (tf_close, known_dt) where known_dt is a pd.Series of Timestamps
    indexed by the TF bar labels (same index as tf_close).

    ``"W-FRI"`` keeps the pandas path: a weekly W-FRI bin is CALENDAR-absolute already (its
    edges are Fridays, not the series start), so it never carried the F1 defect. ``"2W-FRI"``
    did: pandas phases the FORTNIGHT to the series' first timestamp, so the S1/S2 badges
    flipped with the caller's slice. It is replaced here by the absolute fortnight (R6):

        week_friday(d) = d + (4 - d.weekday()) % 7           # the Friday closing d's week
        fortnight_id   = (week_friday - 1970-01-02).days // 14
        label          = 1970-01-02 + (2*fortnight_id + 1) * 7 days     # the pair-END Friday

    Same right-closed/right-labelled semantics pandas gives ``2W-FRI`` — only the PHASE moves,
    from "wherever this series happens to start" to a fixed epoch. The completed-only tail rule
    is applied exactly as before, on the label.
    """
    last_obs = daily.index.max()
    if rule != "2W-FRI":
        raw = daily.resample(rule).last().dropna()
        raw = raw[raw.index <= last_obs]
        known = (
            daily.resample(rule)
            .apply(lambda x: x.dropna().index.max())
            .reindex(raw.index)
            .dropna()
        )
        raw = raw.reindex(known.index)
        known_dt = pd.Series(pd.to_datetime(known.values), index=known.index)
        return raw, known_dt

    s = daily.dropna()
    if not s.index.is_monotonic_increasing:
        s = s.sort_index()
    if s.empty:
        return pd.Series(dtype="float64"), pd.Series(dtype="datetime64[ns]")
    d = pd.DatetimeIndex(s.index)
    week_friday = d + pd.to_timedelta((4 - d.dayofweek.to_numpy()) % 7, unit="D")
    fid = ((week_friday - _EPOCH_FRIDAY).days.to_numpy() // 14)
    label = _EPOCH_FRIDAY + pd.to_timedelta((2 * fid + 1) * 7, unit="D")
    g = pd.DataFrame({"v": s.to_numpy(), "d": d.to_numpy(), "lab": label.to_numpy()}
                     ).groupby(fid, sort=True).last()
    raw = pd.Series(g["v"].to_numpy(), index=pd.DatetimeIndex(g["lab"]))
    known_dt = pd.Series(pd.DatetimeIndex(g["d"]), index=raw.index)
    keep = raw.index <= last_obs            # completed-only: drop the in-progress tail bucket
    return raw[keep], known_dt[keep]


def _htf_confluence_active(c: pd.Series, di: pd.DatetimeIndex, rule: str,
                           market: str = "US") -> pd.Series:
    """Per-TF confluence-active state (daily boolean) for W-FRI or 2W-FRI resamples.

    confluence-active on TF = MACD-RSI crossed up within HTF_FW native bars
                               AND StochRSI K >= D (crossed up within HTF_CONF_W native bars).
    Not-topped veto is applied for the 3D leg via _htf_confluence_active_3d; here it is
    NOT applied so callers can compose the veto themselves (S1 uses 3D veto only).

    Returns a daily boolean Series (ffill from completed known-dates).
    """
    td = lambda s, kn, how="ffill": _to_daily(s, kn, di, how)  # noqa: E731
    if rule == "3D":
        # 3D uses _tf_bars (session buckets, known-date mapped) — same as production tier_stream
        ss, sk = _tf_bars(c, 3, market)
    else:
        ss, sk = _completed_resample(c, rule)

    k, d = _stoch_rsi_kd(ss)
    sb = _xup(k, d)
    recent = _since(sb) <= HTF_CONF_W
    m, s = _rsi_macd(ss)
    mb = _xup(m, s)
    mb_since = _since(mb)

    # not-topped on this TF (stoch ob/bear + macd bear) — used for compositing
    stoch_ob = (k >= OB) | (d >= OB)
    stoch_bear = k < d
    macd_bear = m < s
    not_topped_tf = ~(stoch_ob | stoch_bear | macd_bear)

    mb_since_d = td(mb_since.fillna(999), sk).fillna(999)
    k_d, d_d = td(k, sk), td(d, sk)
    nt_d = td(not_topped_tf.fillna(False), sk).fillna(False)

    stoch_ok_d = (k_d >= d_d).fillna(False)
    macd_fresh_d = mb_since_d <= HTF_FW

    active_d = (macd_fresh_d & stoch_ok_d & nt_d).fillna(False)
    return active_d


def _htf_2w_pending(c: pd.Series, di: pd.DatetimeIndex) -> pd.Series:
    """2W MACD pending leg for S2: hist < 0, slope > 0, 0 < btc <= HTF_BTC.
    Uses 2W-FRI completed resample; returns daily boolean Series.
    """
    td = lambda s, kn, how="ffill": _to_daily(s, kn, di, how)  # noqa: E731
    s2w, kn2w = _completed_resample(c, "2W-FRI")
    m2w, s2w_s = _rsi_macd(s2w)
    h2w = m2w - s2w_s
    slope2w = h2w - h2w.shift(1)
    btc2w = (-h2w / slope2w).where((slope2w > 0) & (h2w < 0), other=np.nan)

    h2w_d = td(h2w, kn2w)
    slope2w_d = td(slope2w, kn2w)
    btc2w_d = td(btc2w, kn2w)

    pending_d = (
        (h2w_d < 0) & (slope2w_d > 0) & (btc2w_d > 0) & (btc2w_d <= HTF_BTC)
    ).fillna(False)
    return pending_d


def _htf_not_topped_3d(c: pd.Series, di: pd.DatetimeIndex, market: str = "US") -> pd.Series:
    """Production 3D not-topped veto (daily boolean) — same as cascade()."""
    ss3, sk3 = _tf_bars(c, 3, market)
    k3, d3 = _stoch_rsi_kd(ss3)
    m3, s3 = _rsi_macd(ss3)
    td = lambda s, kn: _to_daily(s, kn, di)  # noqa: E731
    k3_d, d3_d = td(k3, sk3), td(d3, sk3)
    m3_d, s3_d = td(m3, sk3), td(s3, sk3)
    stoch_ob = (k3_d >= OB) | (d3_d >= OB)
    stoch_bear = k3_d < d3_d
    macd_bear = m3_d < s3_d
    return ~(stoch_ob | stoch_bear | macd_bear).fillna(True)


def _compute_htf(c: pd.Series, market: str = "US") -> dict:
    """Compute S1 and S2 HTF super-tier booleans for the LAST bar.

    S1 = 2W confluence-active AND 3D confluence-active AND not_topped (3D).
    S2 = 3D confluence-active AND 1W confluence-active AND 2W MACD pending AND not_topped (3D).

    Both booleans are for the most-recent daily bar (today's state).
    Returns {"s1": bool, "s2": bool}. Never raises.
    """
    try:
        c = c.dropna()
        if not isinstance(c.index, pd.DatetimeIndex):
            c = c.copy()
            c.index = pd.to_datetime(c.index)
        if len(c) < MIN_HISTORY:
            return dict(_HTF_BLANK)
        di = c.index

        act_3d = _htf_confluence_active(c, di, "3D", market)
        act_1w = _htf_confluence_active(c, di, "W-FRI", market)
        act_2w = _htf_confluence_active(c, di, "2W-FRI", market)
        pend_2w = _htf_2w_pending(c, di)
        not_topped = _htf_not_topped_3d(c, di, market)

        last = len(di) - 1
        s1 = bool(act_2w.iloc[last] and act_3d.iloc[last] and not_topped.iloc[last])
        s2 = bool(act_3d.iloc[last] and act_1w.iloc[last] and pend_2w.iloc[last] and not_topped.iloc[last])
        return {"s1": s1, "s2": s2}
    except Exception:
        return dict(_HTF_BLANK)


def _compute_htf_stream(c: pd.Series, market: str = "US") -> tuple[pd.Series, pd.Series]:
    """Vectorized per-day S1/S2 boolean streams (completed-bucket basis).

    Returns (s1_series, s2_series) as daily boolean pd.Series aligned to c.index.
    Uses the same completed-resample convention as the rest of tier_stream().
    Never raises — returns two all-False series on error.
    """
    try:
        c = c.dropna()
        if not isinstance(c.index, pd.DatetimeIndex):
            c = c.copy()
            c.index = pd.to_datetime(c.index)
        if len(c) < MIN_HISTORY:
            false_s = pd.Series(False, index=c.index)
            return false_s, false_s
        di = c.index

        act_3d = _htf_confluence_active(c, di, "3D", market)
        act_1w = _htf_confluence_active(c, di, "W-FRI", market)
        act_2w = _htf_confluence_active(c, di, "2W-FRI", market)
        pend_2w = _htf_2w_pending(c, di)
        not_topped = _htf_not_topped_3d(c, di, market)

        s1 = (act_2w & act_3d & not_topped).fillna(False).reindex(di, fill_value=False)
        s2 = (act_3d & act_1w & pend_2w & not_topped).fillna(False).reindex(di, fill_value=False)
        return s1, s2
    except Exception:
        false_s = pd.Series(False, index=c.index if hasattr(c, "index") else pd.DatetimeIndex([]))
        return false_s, false_s
