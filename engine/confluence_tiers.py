"""The owner's WEIGHTED tier cascade for the Standout grids — extends signal_gate.

A single signal is one DOOR in a cascade (the sector-cycle engine + the owner's
leadership/rotation read are the other doors); this grades a name into the owner's
ladder, strongest-confirmed -> earliest, each tier weighted by its held-out balance of
earliness-vs-stop-out (research/signal_engine/TIERED_CASCADE.md, 110 held-out US names):

  TIER  WEIGHT  definition                                              held-out stop-out
  T1    0.90    3D MACD-RSI x 3D StochRSI, buy-filter endorsed (master)   38.3%   (= signal_gate TAKE)
  T2    1.00    2D MACD-RSI cross  & 3D StochRSI crossed (recent)         40.6%   (operator re-ranked above T1 2026-07-06)
  T3    0.60    2D MACD-RSI PROJECTED<=1-2d & 3D StochRSI already crossed 42.3%   (the early prediction)
  T4    0.40    2D MACD-RSI PROJECTED & 2D StochRSI crossed & ABOVE-200MA 43.1%   (earliest; anti-falling-knife)

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
from engine.technicals import rsi   # faithful Wilder RSI (== Pine ta.rsi)

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
MIN_HISTORY = 200

# operator-ratified 2026-07-06 — T2 ranked above T1 for entry quality (fills nearer the
# trough, confirmed-bar low repaint ~9%); T1 remains the highest-precision confirmed state.
WEIGHTS = {"T1": 0.9, "T2": 1.0, "T3": 0.6, "T4": 0.4}
_BLANK = {"tier": None, "weight": 0.0, "sub": None, "eligible": False,
          "bars_to_cross": None, "asof": None, "not_topped": True, "ticks": None,
          "provisional": False}


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


def _tf_bars(daily, n):
    s = daily.resample(f"{n}B").last().dropna()
    known = daily.resample(f"{n}B").apply(lambda x: x.dropna().index.max()).reindex(s.index).dropna()
    return s.reindex(known.index), pd.Series(pd.to_datetime(known.values), index=known.index)


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


def cascade(daily_close: pd.Series, *, take_active: bool = False,
            take_date=None) -> dict:
    """Grade a close series into the weighted tier cascade. The board is ONLY "about to cross"
    (T3/T4, projected) + "JUST crossed" (T1/T2, within FRESH_TICKS on the signal's own TF) —
    never a name that crossed several ticks ago and has been rising. T1 = `take_active` (the
    validated master from signal_quality) but ONLY while its arrow is <= FRESH_TICKS 3D-ticks
    old AND the 3D momentum is still constructive (not-topped). `take_date` = the §7 buy
    marker's date (used to age the take in 3D ticks; falls back to the raw 3D cross). Highest
    active tier wins. Returns {tier, weight, sub, eligible, bars_to_cross, asof, not_topped,
    ticks}. Never raises."""
    try:
        c = daily_close.dropna()
        if not isinstance(c.index, pd.DatetimeIndex):
            c = c.copy(); c.index = pd.to_datetime(c.index)
        if len(c) < MIN_HISTORY:
            v = dict(_BLANK)
            if take_active:               # thin history: trust the §7 marker (can't tick-age it)
                v.update(tier="T1", weight=WEIGHTS["T1"], eligible=True)
            return v
        di = c.index
        last = len(di) - 1

        # 2D RSI-MACD: confirmed cross (T2 leg) + imminent-cross projection (T3/T4 leg)
        sm, smk = _tf_bars(c, 2)
        m2, s2 = _rsi_macd(sm)
        h2 = m2 - s2
        mb2 = _xup(m2, s2)
        slope2 = h2 - h2.shift(1)
        btc = (-h2 / slope2)
        imm2 = ((h2 < 0) & (slope2 > 0) & (btc > 0) & (btc <= EARLY_CROSS_BARS)).fillna(False)

        # 3D StochRSI (T1/T2/T3 stoch leg) + 3D RSI-MACD (master cross + not-rolled-over veto)
        ss3, sk3 = _tf_bars(c, 3)
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
        above200 = (c > ma200).fillna(False)

        confirm3 = (wbull_d | fromos3_d)
        rsi_ok = (r14_d < BUY_RSI_MAX).fillna(False)
        long_bias = bool(m2_d.iloc[last] >= s2_d.iloc[last] and k3_d.iloc[last] >= d3_d.iloc[last])

        # NOT-TOPPED / NOT-ROLLED-OVER veto (the AMAT guard) — a buy is only valid while the
        # higher-TF momentum is still constructive. Reject if the 3D StochRSI is OVERBOUGHT or
        # has bearish-crossed (k<d, made a high and turned down), or the 3D RSI-MACD is below
        # its signal. AMAT (3D stoch k=82/d=86, k<d, overbought) fails on the first two.
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

        # 3D-tick age of the operative buy arrow: the §7 take/pending DATE if supplied, else the
        # raw 3D RSI-MACD cross. Exposed on every return (incl. blank) so the caller can age a
        # pending master too. 0 = arrow on the latest 3D bar; 1 = one tick (3 days) ago.
        idx3 = np.where(mb3_d.fillna(False).to_numpy())[0]
        cross3_date = di[int(idx3[-1])] if len(idx3) else None
        t1_ticks = _ticks_since(sk3, take_date if take_date is not None else cross3_date)
        blank = dict(_BLANK, asof=str(di[last].date()), not_topped=not_topped, ticks=t1_ticks)
        if not not_topped:
            return blank                                # topped/rolled-over: never a fresh buy

        # T1 master = the validated held take, but ONLY while JUST-crossed: its arrow is <=
        # FRESH_TICKS old on the 3D grid (1 tick = 3 days). A take 2+ ticks back has "risen for
        # many days" -> it is a HOLD, not a fresh entry, and drops off the board.
        t1_fresh = bool(take_active and t1_ticks is not None and t1_ticks <= FRESH_TICKS)

        # T2 = a JUST-crossed 2D-MACD x 3D-stoch buy: the 2D arrow is <= FRESH_TICKS 2D-ticks old
        t2_buy = (mb2_d & recent3_d & confirm3 & rsi_ok).fillna(False)
        idx2 = np.where(t2_buy.to_numpy())[0]
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
        }
    except Exception:
        return dict(_BLANK)


def _ticks_since_vec(known: pd.Series, cross_pos_daily: np.ndarray, di: pd.DatetimeIndex,
                     fresh_ticks: int) -> np.ndarray:
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


def tier_stream(daily_close: pd.Series, *, fresh_ticks: int | None = None) -> pd.DataFrame:
    """VECTORIZED per-day tier for EVERY daily bar, on COMPLETED buckets (the validated / point-in-
    time basis). This is the single-pass twin of :func:`cascade` — it shares every constant and
    helper, and on the LAST bar of any truncation it reproduces cascade's tier EXACTLY when T1 is
    taken via the raw-3D-cross fallback (tests/test_confluence_tier_stream pins this).

    The provisional-basis replay compares this stream (completed buckets) against the per-day live
    ``cascade`` (provisional tail) to measure the repaint (#22). T1 here uses the raw 3D RSI-MACD
    cross as ``take`` (cascade's own fallback when no §7 take_date is supplied), so the stream is a
    self-contained close-only signal; the live board's T1 (validated §7 master) is a strict subset.

    Returns a daily-indexed frame: tier (T1..T4|None), weight, ticks, not_topped, eligible, sub.
    ``fresh_ticks`` overrides the module FRESH_TICKS for a knob sweep. Never raises → empty frame."""
    ft = FRESH_TICKS if fresh_ticks is None else int(fresh_ticks)
    try:
        c = daily_close.dropna()
        if not isinstance(c.index, pd.DatetimeIndex):
            c = c.copy(); c.index = pd.to_datetime(c.index)
        if len(c) < MIN_HISTORY:
            return pd.DataFrame()
        di = c.index
        n = len(di)

        sm, smk = _tf_bars(c, 2)
        m2, s2 = _rsi_macd(sm)
        h2 = m2 - s2
        mb2 = _xup(m2, s2)
        slope2 = h2 - h2.shift(1)
        btc = (-h2 / slope2)
        imm2 = ((h2 < 0) & (slope2 > 0) & (btc > 0) & (btc <= EARLY_CROSS_BARS)).fillna(False)

        ss3, sk3 = _tf_bars(c, 3)
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
        return pd.DataFrame({"tier": tier, "weight": weight, "ticks": ticks,
                             "not_topped": not_topped, "eligible": elig, "sub": sub}, index=di)
    except Exception:
        return pd.DataFrame()


def _last_true_pos(mask: np.ndarray) -> np.ndarray:
    """For each position i, the index of the most-recent True at-or-before i (or -1). Vectorized."""
    n = len(mask)
    idx = np.where(mask, np.arange(n), -1)
    return np.maximum.accumulate(idx)
