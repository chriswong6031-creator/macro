"""Strategy Lab — a registry of causal, cross-sectional strategy legs and the
honest forward-IC machinery to measure them, so a backtest can decide which legs
earn weight in the scoring / selection engines.

Every leg is a pure function ``leg(closes, asof[, market]) -> Series(ticker->value)``
computed from ``closes.loc[:asof]`` ONLY (point-in-time / causal, the same contract
as ``engine.predictive_signals``).  The SIGN of each leg is aligned so that a
POSITIVE forward rank-IC means the leg is constructive — i.e. higher value should
precede higher forward return.  That convention is what lets a downstream weighter
treat ``ic_ir`` as a signed evidence weight without per-leg bookkeeping.

Families
--------
momentum     trend-continuation (Jegadeesh-Titman, 52w-high anchoring, FIP)
reversal     mean-reversion / wash-out (1m reversal, below-200dma, drawdown, RSI)
trend        trend-quality / persistence (200dma slope, above-200 persistence, ER)
lowvol       low-volatility / lottery anomalies (inverse vol, MAX-caution)

This module computes NOTHING on import and feeds NOTHING scored on its own — it is
the measurement substrate.  Wiring a winning leg into a live score is a separate,
deliberate, config-gated step (see scripts/backtest_strategies.py for the verdict
and research notes for the integration design).
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from engine import predictive_signals as ps

_FORM, _SKIP, _WIN = 252, 21, 252


# ----------------------------------------------------------- leg helpers -----

def _sub(closes: pd.DataFrame, asof, n: int) -> pd.DataFrame:
    sub = closes.loc[:asof]
    return sub.iloc[-n:] if len(sub) >= 2 else sub


def _sma(sub: pd.DataFrame, n: int) -> pd.Series:
    return sub.iloc[-n:].mean() if len(sub) >= n else pd.Series(dtype=float)


# ----- reversal / mean-reversion family (higher = more washed-out) -----------

def rev_1m(closes: pd.DataFrame, asof, win: int = 21) -> pd.Series:
    """Short-term reversal: NEGATIVE of the last-month return (Jegadeesh 1990 1m
    reversal). Higher = fell more recently = constructive (mean-reversion)."""
    sub = _sub(closes, asof, win + 1)
    if len(sub) < win:
        return pd.Series(dtype=float)
    r = sub.iloc[-1] / sub.iloc[0] - 1.0
    return (-r)[sub.iloc[-1].notna() & sub.iloc[0].notna()]


def below_200dma(closes: pd.DataFrame, asof, win: int = 200) -> pd.Series:
    """NEGATIVE distance to the 200d average: higher = further BELOW the 200dma."""
    sub = _sub(closes, asof, win + 1)
    if len(sub) < win:
        return pd.Series(dtype=float)
    ma = sub.iloc[-win:].mean()
    last = sub.iloc[-1]
    out = -(last / ma - 1.0)
    return out[(ma > 0) & last.notna()]


def drawdown_252(closes: pd.DataFrame, asof, win: int = 252) -> pd.Series:
    """Depth below the trailing 252d high (>=0). Higher = deeper drawdown."""
    sub = _sub(closes, asof, win)
    if len(sub) < 60:
        return pd.Series(dtype=float)
    hi = sub.max()
    last = sub.iloc[-1]
    out = -(last / hi - 1.0)
    return out[(hi > 0) & last.notna()]


def rsi_oversold(closes: pd.DataFrame, asof, n: int = 14) -> pd.Series:
    """50 - RSI(14): higher = more oversold (constructive mean-reversion)."""
    sub = _sub(closes, asof, n * 6 + 1)
    if len(sub) < n + 2:
        return pd.Series(dtype=float)
    delta = sub.diff()
    up = delta.clip(lower=0).ewm(alpha=1 / n, min_periods=n).mean().iloc[-1]
    dn = (-delta.clip(upper=0)).ewm(alpha=1 / n, min_periods=n).mean().iloc[-1]
    rs = up / dn.replace(0, np.nan)
    rsi = 100 - 100 / (1 + rs)
    return (50.0 - rsi).dropna()


# ----- momentum family (higher = stronger up-trend) --------------------------

def mom_12_1(closes: pd.DataFrame, asof, **k) -> pd.Series:
    return ps.mom_12_1(closes, asof)


def fip_continuity(closes: pd.DataFrame, asof, **k) -> pd.Series:
    return ps.fip_continuity(closes, asof)


def near_52w_high(closes: pd.DataFrame, asof, **k) -> pd.Series:
    return ps.near_52w_high(closes, asof)


def _ret(closes: pd.DataFrame, asof, form: int, skip: int) -> pd.Series:
    """Total return over [t-form-skip, t-skip] (skip the last `skip` days)."""
    sub = closes.loc[:asof]
    if len(sub) < form + skip + 1:
        return pd.Series(dtype=float)
    need = sub.iloc[-(form + skip):]
    end = need.iloc[-(skip + 1)]
    start = need.iloc[0]
    out = end / start - 1.0
    return out[end.notna() & start.notna()]


def mom_6_1(closes: pd.DataFrame, asof) -> pd.Series:
    """6-1 momentum (126d formation, skip last 21d)."""
    return _ret(closes, asof, 126, 21)


def mom_3_1(closes: pd.DataFrame, asof) -> pd.Series:
    """3-1 momentum (63d formation, skip last 5d) — faster trend."""
    return _ret(closes, asof, 63, 5)


def mom_accel(closes: pd.DataFrame, asof) -> pd.Series:
    """Momentum ACCELERATION: recent 63d return minus the prior 63d return. Higher =
    the trend is speeding up (Novy-Marx 'momentum of momentum')."""
    sub = closes.loc[:asof]
    if len(sub) < 130:
        return pd.Series(dtype=float)
    recent = sub.iloc[-1] / sub.iloc[-64] - 1.0
    prior = sub.iloc[-64] / sub.iloc[-127] - 1.0
    out = recent - prior
    return out[recent.notna() & prior.notna()]


def volscaled_mom(closes: pd.DataFrame, asof, form: int = 252, skip: int = 21,
                  vwin: int = 126) -> pd.Series:
    """12-1 momentum divided by trailing realized vol (risk-adjusted / 'sharpe'
    momentum) — the construct that travels best across regimes."""
    m = ps.mom_12_1(closes, asof, form=form, skip=skip)
    sub = closes.loc[:asof]
    if len(sub) < vwin + 1 or m.empty:
        return pd.Series(dtype=float)
    vol = sub.pct_change().iloc[-vwin:].std()
    out = m / vol.replace(0, np.nan)
    return out.dropna()


# ----- trend / quality family (higher = cleaner, more persistent up-trend) ---

def ma200_slope(closes: pd.DataFrame, asof, win: int = 200, look: int = 21) -> pd.Series:
    """21d change in the 200dma (trend persistence). Higher = the long trend is
    turning/accelerating up."""
    sub = _sub(closes, asof, win + look + 1)
    if len(sub) < win + look:
        return pd.Series(dtype=float)
    ma_now = sub.iloc[-win:].mean()
    ma_prev = sub.iloc[-(win + look):-look].mean()
    out = ma_now / ma_prev - 1.0
    return out[(ma_prev > 0)].dropna()


def above200_persist(closes: pd.DataFrame, asof, win: int = 200, look: int = 63) -> pd.Series:
    """Fraction of the last `look` days the close held above its 200dma. Higher =
    durable up-trend."""
    sub = _sub(closes, asof, win + look + 1)
    if len(sub) < win + look:
        return pd.Series(dtype=float)
    ma = sub.rolling(win).mean()
    above = (sub > ma).iloc[-look:]
    return above.mean().dropna()


def kaufman_er(closes: pd.DataFrame, asof, win: int = 21) -> pd.Series:
    """Kaufman efficiency ratio over `win` days: |net move| / sum|daily moves| ∈
    [0,1]. Higher = a clean directional trend (low chop)."""
    sub = _sub(closes, asof, win + 1)
    if len(sub) < win:
        return pd.Series(dtype=float)
    net = (sub.iloc[-1] - sub.iloc[-win - 1]).abs()
    path = sub.diff().abs().iloc[-win:].sum()
    out = net / path.replace(0, np.nan)
    return out.dropna()


# ----- low-vol / lottery family (higher = calmer = constructive) -------------

def lowvol_63(closes: pd.DataFrame, asof, win: int = 63) -> pd.Series:
    """NEGATIVE of trailing 63d daily-return vol (low-vol anomaly). Higher = calmer."""
    sub = _sub(closes, asof, win + 1)
    if len(sub) < win:
        return pd.Series(dtype=float)
    vol = sub.pct_change().iloc[-win:].std()
    return (-vol).dropna()


def max_caution(closes: pd.DataFrame, asof, **k) -> pd.Series:
    return ps.max_caution(closes, asof)


# ----- novel / academic factors (causal; sign aligned + => constructive) -----

def _panel_returns(closes: pd.DataFrame, asof, win: int):
    """Trailing `win` daily returns + the EW cross-sectional market proxy, causal."""
    sub = closes.loc[:asof]
    if len(sub) < win + 2:
        return None, None
    r = sub.iloc[-(win + 1):].pct_change().iloc[1:]
    return r, r.mean(axis=1)


def _betas(r: pd.DataFrame, m: pd.Series) -> pd.Series:
    mv = float(m.var())
    if not mv:
        return pd.Series(dtype=float)
    return r.apply(lambda c: c.cov(m)) / mv


def low_beta(closes: pd.DataFrame, asof, win: int = 252) -> pd.Series:
    """NEGATIVE trailing market beta (Frazzini-Pedersen betting-against-beta): low-beta
    names earn higher risk-adjusted returns, so higher (= lower beta) is constructive."""
    r, m = _panel_returns(closes, asof, win)
    if r is None:
        return pd.Series(dtype=float)
    b = _betas(r, m)
    return (-b).dropna()


def idio_vol(closes: pd.DataFrame, asof, win: int = 126) -> pd.Series:
    """NEGATIVE idiosyncratic volatility (Ang-Hodrick-Xing-Zhang): residual std vs the
    market. The IVOL anomaly is negatively priced, so higher (= calmer idio) = better."""
    r, m = _panel_returns(closes, asof, win)
    if r is None:
        return pd.Series(dtype=float)
    b = _betas(r, m)
    if b.empty:
        return pd.Series(dtype=float)
    pred = pd.DataFrame(np.outer(m.to_numpy(), b.to_numpy()), index=r.index, columns=b.index)
    return (-(r[b.index] - pred).std()).dropna()


def resid_mom(closes: pd.DataFrame, asof, win: int = 252, skip: int = 21) -> pd.Series:
    """Idiosyncratic / residual momentum (Blitz-Huij-Martens): 12-1 cumulative return of
    the market-residual series. More robust and less reversal-prone than raw momentum."""
    sub = closes.loc[:asof]
    need = win + skip
    if len(sub) < need + 2:
        return pd.Series(dtype=float)
    r = sub.iloc[-(need + 1):].pct_change().iloc[1:]
    m = r.mean(axis=1)
    b = _betas(r, m)
    if b.empty:
        return pd.Series(dtype=float)
    pred = pd.DataFrame(np.outer(m.to_numpy(), b.to_numpy()), index=r.index, columns=b.index)
    resid = r[b.index] - pred
    form = resid.iloc[:-skip] if skip > 0 else resid
    return ((1.0 + form).prod() - 1.0).dropna()


def seasonality(closes: pd.DataFrame, asof, years: int = 5) -> pd.Series:
    """Same-calendar-month historical return (Heston-Sadka): the average of this name's
    returns in the SAME month over the prior `years`. Higher = a positive seasonal."""
    sub = closes.loc[:asof]
    if len(sub) < 252 * 2:
        return pd.Series(dtype=float)
    monthly = sub.resample("ME").last().pct_change()
    mth = pd.Timestamp(asof).month
    same = monthly[(monthly.index.month == mth) &
                   (monthly.index < pd.Timestamp(asof).replace(month=1, day=1))]
    if len(same) < 2:
        return pd.Series(dtype=float)
    return same.tail(years).mean().dropna()


def vol_of_vol(closes: pd.DataFrame, asof, win: int = 126, sub_win: int = 21) -> pd.Series:
    """NEGATIVE vol-of-vol: std of the trailing rolling realized-vol series. Higher
    (= more stable volatility) is the constructive read (test the sign empirically)."""
    sub = closes.loc[:asof]
    if len(sub) < win + sub_win + 2:
        return pd.Series(dtype=float)
    rv = sub.pct_change().rolling(sub_win).std()
    return (-rv.iloc[-win:].std()).dropna()


# ----- live-model components (what the SHIPPED confluence score keys on) ------
# Measuring these as standalone legs tells us which pieces of the current model
# actually carry forward edge — the basis for re-weighting config.engine.confluence.

def live_above200(closes: pd.DataFrame, asof, win: int = 200) -> pd.Series:
    """close/200dma - 1 (the confluence `tech_above200` leg, as a continuous tilt)."""
    sub = _sub(closes, asof, win + 1)
    if len(sub) < win:
        return pd.Series(dtype=float)
    ma = sub.iloc[-win:].mean()
    out = sub.iloc[-1] / ma - 1.0
    return out[(ma > 0)].dropna()


def live_dist_50dma(closes: pd.DataFrame, asof, win: int = 50) -> pd.Series:
    """close/50dma - 1 (the confluence `tech_above50` leg, continuous)."""
    sub = _sub(closes, asof, win + 1)
    if len(sub) < win:
        return pd.Series(dtype=float)
    ma = sub.iloc[-win:].mean()
    out = sub.iloc[-1] / ma - 1.0
    return out[(ma > 0)].dropna()


def live_macd_pos(closes: pd.DataFrame, asof) -> pd.Series:
    """MACD histogram sign (the confluence `tech_macd` leg)."""
    sub = _sub(closes, asof, 60)
    if len(sub) < 35:
        return pd.Series(dtype=float)
    ema12 = sub.ewm(span=12, min_periods=12).mean()
    ema26 = sub.ewm(span=26, min_periods=26).mean()
    macd = ema12 - ema26
    hist = (macd - macd.ewm(span=9, min_periods=9).mean()).iloc[-1]
    return np.sign(hist).dropna()


def live_rs_crowded(closes: pd.DataFrame, asof, win: int = 252) -> pd.Series:
    """Trailing-`win` return percentile within the panel (the `crowding`/rs_pctile
    the confluence score PENALIZES at the top). If this has POSITIVE forward IC, the
    crowding penalty is fighting the momentum edge — a key re-weighting question."""
    sub = _sub(closes, asof, win + 1)
    if len(sub) < 60:
        return pd.Series(dtype=float)
    ret = sub.iloc[-1] / sub.iloc[0] - 1.0
    ret = ret.dropna()
    if len(ret) < 10:
        return pd.Series(dtype=float)
    return ret.rank(pct=True)


# --------------------------------------------------------- the registry ------

STRATEGIES: dict[str, dict] = {
    # name:           {family, fn, note(sign already aligned: + => constructive)}
    "mom_12_1":        {"family": "momentum", "fn": mom_12_1,
                        "note": "12-1 total-return momentum"},
    "fip_continuity":  {"family": "momentum", "fn": fip_continuity,
                        "note": "frog-in-the-pan continuous-info momentum"},
    "near_52w_high":   {"family": "momentum", "fn": near_52w_high,
                        "note": "proximity to the 52w high (anchoring)"},
    "mom_6_1":         {"family": "momentum", "fn": mom_6_1,
                        "note": "6-1 momentum (126d, skip 21d)"},
    "mom_3_1":         {"family": "momentum", "fn": mom_3_1,
                        "note": "3-1 momentum (63d, skip 5d)"},
    "mom_accel":       {"family": "momentum", "fn": mom_accel,
                        "note": "momentum acceleration (recent 63d - prior 63d)"},
    "volscaled_mom":   {"family": "momentum", "fn": volscaled_mom,
                        "note": "risk-adjusted 12-1 momentum (per unit vol)"},
    "rev_1m":          {"family": "reversal", "fn": rev_1m,
                        "note": "1-month short-term reversal"},
    "below_200dma":    {"family": "reversal", "fn": below_200dma,
                        "note": "distance below the 200dma"},
    "drawdown_252":    {"family": "reversal", "fn": drawdown_252,
                        "note": "depth below the 252d high"},
    "rsi_oversold":    {"family": "reversal", "fn": rsi_oversold,
                        "note": "50 - RSI(14)"},
    "ma200_slope":     {"family": "trend", "fn": ma200_slope,
                        "note": "21d slope of the 200dma"},
    "above200_persist": {"family": "trend", "fn": above200_persist,
                         "note": "share of last 63d above the 200dma"},
    "kaufman_er":      {"family": "trend", "fn": kaufman_er,
                        "note": "Kaufman efficiency ratio (21d)"},
    "lowvol_63":       {"family": "lowvol", "fn": lowvol_63,
                        "note": "inverse 63d realized vol"},
    "max_caution":     {"family": "lowvol", "fn": max_caution,
                        "note": "inverse 1m MAX (lottery) return"},
    "low_beta":        {"family": "lowvol", "fn": low_beta,
                        "note": "betting-against-beta (inverse market beta)"},
    "idio_vol":        {"family": "lowvol", "fn": idio_vol,
                        "note": "inverse idiosyncratic vol (Ang IVOL anomaly)"},
    "vol_of_vol":      {"family": "lowvol", "fn": vol_of_vol,
                        "note": "inverse vol-of-vol (volatility stability)"},
    "resid_mom":       {"family": "momentum", "fn": resid_mom,
                        "note": "residual/idiosyncratic 12-1 momentum (Blitz)"},
    "seasonality":     {"family": "seasonal", "fn": seasonality,
                        "note": "same-month historical return (Heston-Sadka)"},
    "live_above200":   {"family": "model", "fn": live_above200,
                        "note": "confluence tech_above200 leg (close/200dma)"},
    "live_dist_50dma": {"family": "model", "fn": live_dist_50dma,
                        "note": "confluence tech_above50 leg (close/50dma)"},
    "live_macd_pos":   {"family": "model", "fn": live_macd_pos,
                        "note": "confluence tech_macd leg (MACD sign)"},
    "live_rs_crowded": {"family": "model", "fn": live_rs_crowded,
                        "note": "rs percentile the score PENALIZES (crowding)"},
}


# ----- fundamental family (PIT earnings surprise) ----------------------------

def build_sue_panel(eps: pd.DataFrame) -> pd.DataFrame:
    """Standardized earnings surprise (SUE) as a date×ticker panel, keyed by the
    REPORTING date (asof_date) so it is point-in-time: the value is only known once
    the quarter is reported. SUE = (eps_q - eps_q[YoY]) / rolling-std(that YoY diff).

    `eps` columns: ticker, period_end, eps_q, asof_date (engine reads
    data/edgar/eps_quarterly.parquet). Returns a frame indexed by asof_date; a
    backtest reads the latest row at-or-before its rebalance date."""
    frames = []
    for tk, g in eps.dropna(subset=["eps_q", "asof_date"]).groupby("ticker"):
        g = g.sort_values("period_end").drop_duplicates("period_end")
        if len(g) < 6:
            continue
        surprise = g["eps_q"] - g["eps_q"].shift(4)            # YoY change
        std = surprise.rolling(8, min_periods=4).std()
        sue = (surprise / std).replace([np.inf, -np.inf], np.nan)
        frames.append(pd.DataFrame({"asof": pd.to_datetime(g["asof_date"].values),
                                    "ticker": tk, "sue": sue.values}).dropna(subset=["sue"]))
    if not frames:
        return pd.DataFrame()
    allr = pd.concat(frames).sort_values("asof")
    return allr.pivot_table(index="asof", columns="ticker", values="sue",
                            aggfunc="last").sort_index()


def sue_asof(panel: pd.DataFrame, d, max_stale_days: int = 130) -> pd.Series:
    """Latest known SUE at-or-before `d`, dropping reports older than
    `max_stale_days` (so a name's signal goes stale a quarter after it last reported
    rather than persisting forever)."""
    if panel.empty:
        return pd.Series(dtype=float)
    lo = pd.Timestamp(d) - pd.Timedelta(days=max_stale_days)
    window = panel.loc[lo:pd.Timestamp(d)]
    if window.empty:
        return pd.Series(dtype=float)
    return window.ffill().iloc[-1].dropna()


# ----------------------------------------------------- measurement core ------

def sector_demean(s: pd.Series, sec: pd.Series | None) -> pd.Series:
    """Within-sector demean (sector-neutral). No-op if no sector map.

    NOTE: `sec` is the CURRENT/static classification (no as-of dimension), applied
    to every historical date — a small known approximation on the neutralization
    step (not a price/outcome leak). Sectors are slow-moving, so the IC impact is
    minor; the raw-IC column is sector-blind and unaffected. Disclosed in the
    harness caveats; cure = a point-in-time sector history."""
    if sec is None:
        return s - s.mean()
    g = sec.reindex(s.index)
    return s - s.groupby(g).transform("mean")


def forward_excess(closes: pd.DataFrame, pos: int, horizon: int,
                   eligible: set | None = None) -> pd.Series:
    """Cross-sectionally DEMEANED forward `horizon`-day return as of index[pos]
    (market-neutral outcome). `eligible` restricts to PIT members on that date."""
    cur = closes.iloc[pos]
    fwd = closes.iloc[pos + horizon] / cur - 1.0
    fwd = fwd.dropna()
    if eligible is not None:
        fwd = fwd[[t for t in fwd.index if t in eligible]]
    return fwd - fwd.mean() if len(fwd) else fwd
