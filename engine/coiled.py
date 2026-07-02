"""COILED composite — wave-2-validated cohort-washout ranking bonus for the US standout board.

Framework doc: research/signal_engine/DURABLE_BOTTOM_FRAMEWORK.md §6 + §8 ledger (2026-07-01)
Wave-2 report:  research/entry_timing/WAVE2_REPORT.md
Wave-4 report:  research/entry_timing/WAVE4_REPORT.md

Validated numbers (basket OOS, G2 — the decisive gate):
  COILED vs noncoiled_washout: clean15 +7.54pp, stop5 −5.64pp (better), n=6,842
  STAR (COILED ∩ bull_div): stop5 −2.4pp further vs COILED (baskets)

Wave-4 COILED-FIRE marker (C2 = union m1d_s3d ∪ m2d_s3d inside COILED):
  stop5 non-inferior to R on all panels; premium 7.02 vs 8.08; lead 3d vs 6d;
  recall +1.83pp US stocks / +10.10pp CN. DISPLAY chip + forward-ledger only.

WHAT THIS MODULE IS:
  display/ranking bonus + forward-ledger fields, NOT a standalone alpha signal,
  NOT a hard gate, NOT an auto-trade trigger.

  A hard gate would gut recall by ~88% (COILED recalls only 7.35% of B15 durable bottoms
  vs 59.71% for all m2d_s3d fires — T8 of the wave-2 report). Shipped as a graded ranking
  bonus that lifts a COILED name ~half a cascade tier, STAR ~0.8 tier, mirroring the CN
  WASHOUT_BONUS precedent. Graded refinement (quartile scoring) is a W6-US Buy Board 2.0
  decision per the ship record.

Public API (all functions never raise):
  weekly_d_last(daily_close)          -> float | None
  washout_ctx(daily_close)            -> bool | None
  bull_div(daily_close)               -> bool
  cohort_fractions(latest_d, sector_of, d_thresh, min_peers) -> dict[str, float | None]
  assess(washout, cohort_frac, div)   -> dict  (JSON-safe, no NaN)
  fire_recent(daily_close, within=3)  -> dict  (JSON-safe; fire/ticks/src; never raises)
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from engine.technicals import rsi  # faithful Wilder RSI (== Pine ta.rsi)

# ── bonus constants (on the _combine_key pct + 0.5·w scale) ─────────────────
# +0.40 max sits just under one full cascade tier, mirroring the CN WASHOUT_BONUS
# precedent; graded refinement is a W6-US Buy Board 2.0 decision.
COILED_BONUS = 0.25   # cohort-washout confirmed
STAR_EXTRA   = 0.15   # additional bonus for STAR (COILED ∩ bull_div)

# ── indicator constants (match confluence_tiers.py exactly) ─────────────────
_RSI_LEN   = 14
_FAST_LEN  = 14
_BASE_LEN  = 60
_SIG_LEN   = 5
_STOCH_LEN = 14
_SMOOTH_K  = 3
_SMOOTH_D  = 3

# ── minimum-bar thresholds ────────────────────────────────────────────────────
_MIN_WEEKLY = 60      # weekly_d_last: need >=60 weekly bars
_WASH_CTX_A = 217     # washout_ctx: capit window (daily)
_WASH_CTX_B = 91      # washout_ctx: look-back window for argmin

# ── fire_recent constants ─────────────────────────────────────────────────────
FIRE_WITHIN = 3       # default look-back for fire_recent (trading bars)
_FIRE_MIN_BARS = 300  # minimum daily bars for fire_recent to attempt computation
# CONF_W for the 3D stoch-cross recency window (must match tuning_harness.CONF_W = 8)
_CONF_W = 8           # 3D bars within which the 3D stoch cross is considered "recent"


def _ema(s: pd.Series, span: int) -> pd.Series:
    return s.ewm(span=span, min_periods=span).mean()


def _rsi_macd(c: pd.Series) -> tuple[pd.Series, pd.Series]:
    """RSI-MACD: fast EMA − slow EMA of RSI(14), then signal."""
    r = rsi(c, _RSI_LEN)
    macd = _ema(r, _FAST_LEN) - _ema(r, _BASE_LEN)
    sig  = _ema(macd, _SIG_LEN)
    return macd, sig


def _stoch_rsi_kd(c: pd.Series) -> tuple[pd.Series, pd.Series]:
    """14/3/3 StochRSI KD — exact copy of confluence_tiers._stoch_rsi_kd."""
    r   = rsi(c, _RSI_LEN)
    lo  = r.rolling(_STOCH_LEN).min()
    hi  = r.rolling(_STOCH_LEN).max()
    rawk = (r - lo) / (hi - lo).replace(0, np.nan) * 100
    k   = rawk.rolling(_SMOOTH_K).mean()
    d   = k.rolling(_SMOOTH_D).mean()
    return k, d


# ── Public functions ──────────────────────────────────────────────────────────

def weekly_d_last(daily_close: pd.Series) -> float | None:
    """Return the most-recent weekly (W-FRI) StochRSI D value as a float in [0,100].

    Resamples to W-FRI .last().dropna(), computes 14/3/3 StochRSI on the weekly
    series, returns float(D.iloc[-1]).  Returns None if fewer than _MIN_WEEKLY (60)
    weekly bars, or if the last value is NaN, or on any error.
    """
    try:
        c = daily_close.dropna()
        if not isinstance(c.index, pd.DatetimeIndex):
            c = c.copy()
            c.index = pd.to_datetime(c.index)
        wk = c.resample("W-FRI").last().dropna()
        if len(wk) < _MIN_WEEKLY:
            return None
        _, d = _stoch_rsi_kd(wk)
        val = d.iloc[-1]
        if pd.isna(val):
            return None
        return float(val)
    except Exception:
        return None


def washout_ctx(daily_close: pd.Series) -> bool | None:
    """H2/H1 washout context — True iff the series just capitulated >=15% from
    its 126-day pre-capitulation high within the last 91 bars.

    Algorithm (wave-1 in_washout_ctx definition, causal):
      c         = daily_close.dropna()
      need >= _WASH_CTX_A + _WASH_CTX_B = 217 + 91 = 308 bars; else return None
      capit_pos = argmin of c[-91:]   (absolute position in c)
      prior_126 = c[capit_pos - 126 : capit_pos]  (strictly before the trough)
      if fewer than 126 bars exist before capit_pos: return None
      dd_at_capit = c[capit_pos] / max(prior_126) - 1
      return dd_at_capit <= -0.15

    Returns None when insufficient history, True/False otherwise.  Never raises.
    """
    try:
        c = daily_close.dropna()
        if not isinstance(c.index, pd.DatetimeIndex):
            c = c.copy()
            c.index = pd.to_datetime(c.index)
        arr = c.to_numpy()
        n   = len(arr)
        if n < _WASH_CTX_A + _WASH_CTX_B:
            return None
        # argmin over the trailing 91 bars (absolute index in arr)
        window = arr[n - _WASH_CTX_B:]
        local_min = int(np.argmin(window))
        capit_pos = (n - _WASH_CTX_B) + local_min
        # need 126 bars strictly before capit_pos
        if capit_pos < 126:
            return None
        prior_max = float(np.nanmax(arr[capit_pos - 126: capit_pos]))
        if prior_max <= 0:
            return None
        dd = arr[capit_pos] / prior_max - 1.0
        return bool(dd <= -0.15)
    except Exception:
        return None


def bull_div(daily_close: pd.Series) -> bool:
    """H3 bullish momentum divergence — price lower-low + 3D RSI-MACD/D higher-low.

    Procedure (wave-1 spec, causal, leak-free known-date mapping):
    1. Resample to 3B .last().dropna() (the "3D grid").
    2. Map 3D bars back to daily index: each 3D bar's "known date" = the maximum
       daily date whose close fell into that bucket (same protocol as
       research/signal_engine/tuning_harness.py to_daily / known-date ffill).
       Reindex to the full daily index with method="ffill".
    3. Find confirmed daily-close swing lows with w=5: position j is a confirmed
       low when c[j] == min(c[j-5 : j+6]) AND there are >=5 bars after j
       (i.e. j <= len(c) - 6).  The last 5 bars can never be pivots.
    4. Take the last two confirmed lows within the final 120 bars: L1 (earlier),
       L2 (later).
    5. True iff close[L2] < close[L1]  (price LL)
              AND (macd3[L2] > macd3[L1]  OR  d3[L2] > d3[L1])  (oscillator HL).

    Returns False if fewer than two qualifying lows.  Never raises.
    """
    try:
        c = daily_close.dropna()
        if not isinstance(c.index, pd.DatetimeIndex):
            c = c.copy()
            c.index = pd.to_datetime(c.index)
        if len(c) < 60:
            return False

        # ── 3D grid (resample("3B").last().dropna()) ────────────────────────
        s3 = c.resample("3B").last().dropna()
        if len(s3) < 20:
            return False

        macd3, _ = _rsi_macd(s3)
        _, d3     = _stoch_rsi_kd(s3)

        # known-date mapping: each 3B bar → max daily date in its bucket
        # (same as tuning_harness.to_daily / confluence_tiers._tf_bars)
        known_raw = c.resample("3B").apply(
            lambda x: x.dropna().index.max() if len(x.dropna()) > 0 else pd.NaT
        ).reindex(s3.index)
        known = pd.Series(
            pd.to_datetime(known_raw.values), index=s3.index
        ).dropna()
        # align macd3/d3 to the same valid-known index
        macd3 = macd3.reindex(known.index)
        d3    = d3.reindex(known.index)

        di = c.index

        def _to_daily_ffill(tf_vals: pd.Series, kn: pd.Series) -> pd.Series:
            kd = pd.Series(tf_vals.to_numpy(), index=pd.to_datetime(kn.to_numpy()))
            kd = kd[~kd.index.duplicated(keep="last")].sort_index()
            return kd.reindex(di, method="ffill")

        macd3_d = _to_daily_ffill(macd3, known)
        d3_d    = _to_daily_ffill(d3, known)

        arr  = c.to_numpy()
        m3_a = macd3_d.to_numpy()
        d3_a = d3_d.to_numpy()
        n    = len(arr)

        # confirmed swing lows: w=5; j confirmed only when j+5 < n
        w = 5
        sw_lo = []
        start = max(w, n - 120 - w)   # search within last 120 bars + w buffer
        for j in range(start, n - w):
            lo_window = arr[j - w: j + w + 1]
            if len(lo_window) < 2 * w + 1:
                continue
            if arr[j] == lo_window.min():
                sw_lo.append(j)

        if len(sw_lo) < 2:
            return False

        L1, L2 = sw_lo[-2], sw_lo[-1]
        # both must be within the last 120 bars
        if L1 < n - 120:
            return False
        if arr[L2] >= arr[L1]:
            return False  # need price LL
        m3_L1, m3_L2 = m3_a[L1], m3_a[L2]
        d3_L1, d3_L2 = d3_a[L1], d3_a[L2]
        macd_div = (not np.isnan(m3_L1)) and (not np.isnan(m3_L2)) and (m3_L2 > m3_L1)
        stch_div = (not np.isnan(d3_L1)) and (not np.isnan(d3_L2)) and (d3_L2 > d3_L1)
        return bool(macd_div or stch_div)

    except Exception:
        return False


def cohort_fractions(
    latest_d: dict[str, float | None],
    sector_of: dict[str, str | None],
    d_thresh: float = 30.0,
    min_peers: int = 5,
) -> dict[str, float | None]:
    """Compute per-ticker cohort washout fractions (H6).

    For each ticker that has a sector, peers = other tickers in the same sector
    that have a non-None latest_d.  frac = mean(peer_d < d_thresh).
    Returns None for the ticker if len(peers) < min_peers.

    The ticker itself is excluded from its own peer set (self-exclusion).
    Returns a dict keyed by every ticker that appears in sector_of.
    Never raises.
    """
    try:
        # pre-group: sector -> list of (ticker, d) with non-None d
        by_sector: dict[str, list[tuple[str, float]]] = {}
        for t, sec in sector_of.items():
            if sec is None:
                continue
            d = latest_d.get(t)
            if d is None:
                continue
            by_sector.setdefault(sec, []).append((t, d))

        result: dict[str, float | None] = {}
        for t, sec in sector_of.items():
            if sec is None:
                result[t] = None
                continue
            peers = [(pt, pd_) for pt, pd_ in by_sector.get(sec, []) if pt != t]
            if len(peers) < min_peers:
                result[t] = None
                continue
            frac = float(np.mean([pd_ < d_thresh for _, pd_ in peers]))
            result[t] = frac
        return result
    except Exception:
        return {}


def assess(
    washout: bool | None,
    cohort_frac: float | None,
    div: bool,
) -> dict:
    """Compute the COILED/STAR verdict and ranking bonus.

    coiled = bool(washout) AND cohort_frac is not None AND cohort_frac >= 0.40
    star   = coiled AND div
    bonus  = COILED_BONUS if coiled else 0.0
           + STAR_EXTRA   if star   else 0.0

    Returns a JSON-safe dict with no NaN values:
      {coiled, star, washout_ctx, cohort, div, bonus}

    Never raises.
    """
    try:
        coiled = bool(washout) and cohort_frac is not None and cohort_frac >= 0.40
        star   = coiled and bool(div)
        bonus  = (COILED_BONUS if coiled else 0.0) + (STAR_EXTRA if star else 0.0)
        return {
            "coiled":      bool(coiled),
            "star":        bool(star),
            "washout_ctx": bool(washout) if washout is not None else None,
            "cohort":      round(float(cohort_frac), 3) if cohort_frac is not None else None,
            "div":         bool(div),
            "bonus":       round(bonus, 3),
        }
    except Exception:
        return {
            "coiled": False, "star": False, "washout_ctx": None,
            "cohort": None, "div": False, "bonus": 0.0,
        }


def fire_recent(daily_close: pd.Series, within: int = FIRE_WITHIN) -> dict:
    """COILED-FIRE marker — did a fresh C2 (union m1d_s3d ∪ m2d_s3d) fire in the
    last `within` trading bars?

    Wave-4 ship record (2026-07-02):
      C2 = union(m1d_s3d, m2d_s3d) inside COILED. Ships as **display chip +
      forward-ledger fields ONLY — no rank/bonus change** (ledger grades it live
      before it earns weight). Validated numbers:
        stop5 non-inferior to R (38.41 vs 39.12 stocks); clean15 37.92 (within bar);
        premium 7.02 vs 8.08; lead 3d vs 6d; recall +1.83pp US / +10.10pp CN.
      HK: NOT shipped (wave-3 gate failed).

    IMPORTANT SEMANTICS:
      This function answers ONLY: "did a fresh union fire print in the last `within`
      trading bars on the DAILY close series?" It does NOT:
        - change any rank or bonus (NO rank/bonus change — display chip only)
        - enforce COILED state (the caller checks coiled_by[t]['coiled'])
        - dedupe or burst-suppress (dedupe / 8-bar burst semantics live in the
          research harness; production boards typically call with within=3 daily bars)
        - auto-trade or generate orders

    Fire definition (C2):
      m1d fire: RSI-MACD (14/60/5) bull cross on the 1D daily grid (xup of macd over
        sig on the raw daily series), WHILE the 3D stoch (14/3/3, resample("3B").last())
        has crossed up from oversold recently (within _CONF_W 2D bars) AND confirm
        (prior-closed-week weekly RSI-MACD bull OR 3D stoch was oversold within window)
        AND rsi_ok (3D RSI14 < 65).
      m2d fire: same but the MACD cross is on the 2B grid (resample("2B").last()),
        mapped to the daily index by known-date (same protocol as tuning_harness.to_daily).
      union fire (any calendar day): m1d OR m2d (same-day counts once).
      Returns {"fire": bool, "ticks": int|None, "src": "m1d"|"m2d"|"both"|None}.

    Implementation replicates tuning_harness.build_signals (macd_cross trigger) conditions
    faithfully (same math as the validated harness):
      MACD-TF bull cross (xup of rsi_macd on that grid, mapped to daily by known-date)
      AND recent 3D stoch cross (within CONF_W=8 3D bars, from-oversold flag feeding confirm)
      AND confirm (prior-closed-week weekly rsi_macd bull OR 3D stoch was oversold within window)
      AND rsi_ok (3D RSI14 < 65)
    For the union, the 3D-stoch leg is shared between both TFs (same 3D grid, same known-date
    mapping — C2 in the harness shares the stoch TF between m1d and m2d in the union).

    Args:
      daily_close: daily close price series with DatetimeIndex (or parseable index).
      within: number of trading bars to look back for a union fire (default FIRE_WITHIN=3).

    Returns dict (always, never raises):
      {
        "fire":  bool    — True iff any union (m1d OR m2d) fire landed in the last `within` bars,
        "ticks": int|None — bars since the most recent union fire; None if no fire ever occurred,
        "src":   "m1d"|"m2d"|"both"|None — source(s) of the most recent fire; None if never.
      }
    All values JSON-safe (no NaN, no numpy scalars).
    """
    _null = {"fire": False, "ticks": None, "src": None}
    try:
        c = daily_close.dropna()
        if not isinstance(c.index, pd.DatetimeIndex):
            c = c.copy()
            c.index = pd.to_datetime(c.index)
        n = len(c)
        if n < _FIRE_MIN_BARS:
            return _null
        if within < 0:
            within = 0

        di = c.index

        # ── helpers (inline, mirrors tuning_harness exactly) ──────────────────

        def _xup(a: pd.Series, b: pd.Series) -> pd.Series:
            return (a > b) & (a.shift(1) <= b.shift(1))

        def _since_cross(cond: pd.Series) -> pd.Series:
            """bars since last True (NaN where never fired yet)."""
            pos = np.arange(len(cond))
            last = pd.Series(np.where(cond.to_numpy(), pos, np.nan),
                             index=cond.index).ffill()
            return pd.Series(pos, index=cond.index) - last

        def _to_daily_ffill(tf_vals: pd.Series, kn: pd.Series) -> pd.Series:
            kd = pd.Series(tf_vals.to_numpy(), index=pd.to_datetime(kn.to_numpy()))
            kd = kd[~kd.index.duplicated(keep="last")].sort_index()
            return kd.reindex(di, method="ffill")

        def _to_daily_event(tf_bool: pd.Series, kn: pd.Series) -> pd.Series:
            """Place True on the daily bar at/after the known date of each True TF bar."""
            out = pd.Series(False, index=di)
            kd = pd.Series(tf_bool.to_numpy(), index=pd.to_datetime(kn.to_numpy()))
            kd = kd[~kd.index.duplicated(keep="last")].sort_index()
            for dt, v in kd.items():
                if v:
                    p = int(di.searchsorted(dt, side="left"))
                    if p < len(di):
                        out.iloc[p] = True
            return out

        def _known(tf_grid: pd.Series) -> pd.Series:
            """known-date series: max daily date in each resample bucket."""
            raw = c.resample(tf_grid.index.freqstr if hasattr(tf_grid.index, "freqstr")
                             else "1B").apply(lambda x: x.dropna().index.max()
                                              if len(x.dropna()) > 0 else pd.NaT)
            return raw  # placeholder; see per-TF below

        # ── 3D stoch grid (shared by both fire legs; tf=2B used as "2D" proxy for the
        #    3D stoch, matching tuning_harness m2d_s3d / m1d_s3d where stoch_tf=3) ────
        # NOTE: the harness uses stoch_tf=3 ("3B") for both m1d_s3d and m2d_s3d.
        # We use "3B" here to match exactly.
        s3 = c.resample("3B").last().dropna()
        s3_known_raw = c.resample("3B").apply(
            lambda x: x.dropna().index.max() if len(x.dropna()) > 0 else pd.NaT
        ).reindex(s3.index)
        s3_known = pd.Series(pd.to_datetime(s3_known_raw.values), index=s3.index).dropna()
        s3 = s3.reindex(s3_known.index)

        k3, d3 = _stoch_rsi_kd(s3)
        sb_cross3 = _xup(k3, d3)
        b1_from_os3 = d3.rolling(_CONF_W).min() < 20.0   # tuning_harness OS=20
        recent_sb3  = _since_cross(sb_cross3) <= _CONF_W
        sb_from_os3 = sb_cross3 & b1_from_os3
        r14_3 = rsi(s3, _RSI_LEN)

        # Map 3D indicators to daily
        recent_sb_d  = _to_daily_ffill(recent_sb3.fillna(False), s3_known)
        b1os_d       = _to_daily_ffill(b1_from_os3.fillna(False), s3_known)
        r14_3_d      = _to_daily_ffill(r14_3, s3_known)

        # ── weekly confirm (prior closed week; matches tuning_harness exactly) ─
        wk = c.resample("W-FRI").last().dropna()
        wmacd, wsig = _rsi_macd(wk)
        w_bull_tf = (wmacd >= wsig).shift(1)   # prior closed week (no repaint)
        w_bull_d  = w_bull_tf.reindex(di, method="ffill").fillna(False).astype(bool)

        confirm_bull = (w_bull_d | b1os_d.reindex(di).fillna(False).astype(bool))
        rsi_ok = (r14_3_d < 65.0).fillna(False)   # BUY_RSI_MAX=65

        # ── m1d leg: MACD cross on the 1D (raw daily) grid ────────────────────
        macd1, sig1 = _rsi_macd(c)
        mb1_cross   = _xup(macd1, sig1)
        # event mapping: True only on the day the cross happened (same logic as "event" in harness)
        mb1_d       = mb1_cross.fillna(False)    # already on the daily grid

        m1d_fire = (mb1_d & recent_sb_d.reindex(di).fillna(False).astype(bool)
                    & confirm_bull & rsi_ok).fillna(False).astype(bool)

        # ── m2d leg: MACD cross on the 2B grid, mapped by known-date ──────────
        s2 = c.resample("2B").last().dropna()
        s2_known_raw = c.resample("2B").apply(
            lambda x: x.dropna().index.max() if len(x.dropna()) > 0 else pd.NaT
        ).reindex(s2.index)
        s2_known = pd.Series(pd.to_datetime(s2_known_raw.values), index=s2.index).dropna()
        s2 = s2.reindex(s2_known.index)

        macd2, sig2 = _rsi_macd(s2)
        mb2_cross   = _xup(macd2, sig2)
        mb2_d       = _to_daily_event(mb2_cross.fillna(False), s2_known)

        m2d_fire = (mb2_d & recent_sb_d.reindex(di).fillna(False).astype(bool)
                    & confirm_bull & rsi_ok).fillna(False).astype(bool)

        # ── union and look-back ────────────────────────────────────────────────
        union_fire = m1d_fire | m2d_fire   # same-day counts once

        # find the most recent union fire
        fire_positions = np.where(union_fire.to_numpy())[0]
        if len(fire_positions) == 0:
            return _null

        last_pos = int(fire_positions[-1])
        ticks    = int((n - 1) - last_pos)   # bars since most recent fire (0 = today)

        # source of the most recent fire
        at_m1d = bool(m1d_fire.iloc[last_pos]) if last_pos < n else False
        at_m2d = bool(m2d_fire.iloc[last_pos]) if last_pos < n else False
        if at_m1d and at_m2d:
            src: str | None = "both"
        elif at_m1d:
            src = "m1d"
        elif at_m2d:
            src = "m2d"
        else:
            src = None

        fired = ticks <= within if within >= 0 else False

        return {
            "fire":  bool(fired),
            "ticks": ticks,
            "src":   src,
        }

    except Exception:
        return _null
