"""engine/basket_index.py — the consolidated ETF-like CANDLE for a thematic basket.

The baskets page already builds an equal-weight close LEVEL per basket (engine.baskets
._ew_level). That is the consolidated index's close, but it carries no intraday range and
no volume, so it can't feed the technical/flow engines that need a real candle (ATR /
Bollinger vol-hole, whale accumulation, Chaikin money-flow). This module builds the full
basket CANDLE — open/high/low/close + traded dollar-volume — from the deep per-member
OHLCV store (data/baskets/ohlcv, fetched by scripts/fetch_basket_ohlcv), with point-in-time
dated membership and a choice of weighting.

CONSTRUCTION (return-space, so it reduces EXACTLY to _ew_level when mode="equal"):
  • per member, daily close-to-close return r_i(t), and intraday range returns measured off
    the PRIOR close: open/high/low_ret_i(t) = open/high/low_i(t)/close_i(t-1) − 1;
  • a member is live only within [added, removed); weights are renormalised over the live set
    each day (so an entry/exit rebalances exactly like the EW level);
  • basket close return R(t) = Σ w_i(t)·r_i(t) → close level = cumprod(1+R) from 1.0;
    the basket high/low/open levels = prior close level × (1 + weighted range return), which
    keeps high ≥ close ≥ low bar-by-bar (the weighting preserves the per-member ordering);
  • dollar-volume(t) = Σ_live close_i(t)·volume_i(t) — the basket's true traded dollars (raw
    share volume is meaningless across different-priced names; dollars are the right unit and
    the right weight for the money-flow math downstream).

WEIGHTING modes (the user's "equal weighted, or weighted as you think"):
  • "equal"     — 1/n_live(t); the honest default and the SCORED baseline.
  • "relevance" — by an explicit member `weight` (membership.json) else the per-stock
    Conviction score (passed in as conv_map); a higher-conviction / more on-thesis name
    carries more of the index. Static weights, renormalised over the live set.
  • "alpha"     — tilt by each member's trailing risk-adjusted relative strength (60d return
    over realised vol vs the basket); capped. DISPLAY/EXPLORATORY — a directional bet on
    close-only momentum with ~0 validated cross-sectional edge (house finding), so never the
    scored baseline.

HONEST BY CONSTRUCTION: like the baskets themselves the membership is ~hindsight-curated, so
this is a descriptive consolidated tape, not an out-of-sample backtest. Coverage is reported
(n_live / n_with_ohlcv) so a thin pull degrades visibly rather than silently.
"""
from __future__ import annotations

import logging

import numpy as np
import pandas as pd

from lib import config

log = logging.getLogger(__name__)

OHLCV_COLS = ["open", "high", "low", "close", "volume"]
ALPHA_CAP = 2.0            # alpha-tilt weight is capped at this × the equal weight
_CACHE: dict[str, pd.DataFrame | None] = {}


def _load_member_ohlcv(ticker: str) -> pd.DataFrame | None:
    """Per-member OHLCV, preferring the deep baskets store, then data/stocks (already OHLCV),
    then the China A-share store (data/china_stocks, .SS/.SZ tickers — close/high/low/volume, no
    open), then the yahoo store (close+volume → high/low/open synthesised as the close). Cached.
    The china_stocks fallback never collides with the US stores (A-share tickers carry a .SS/.SZ
    suffix), so it makes the basket machinery China-capable without touching the US path."""
    if ticker in _CACHE:
        return _CACHE[ticker]
    out: pd.DataFrame | None = None
    bp = config.data_dir() / "baskets" / "ohlcv" / f"{ticker}.parquet"
    sp = config.data_dir() / "stocks" / f"{ticker}.parquet"
    cp = config.data_dir() / "china_stocks" / f"{ticker}.parquet"
    yp = config.data_dir() / "yahoo" / f"{ticker}.parquet"
    try:
        if bp.exists():
            df = pd.read_parquet(bp)
            out = df
        elif sp.exists():
            df = pd.read_parquet(sp)            # close/high/low/volume (no open)
            df = df.copy()
            if "open" not in df.columns:
                df["open"] = df["close"]
            out = df
        elif cp.exists():
            df = pd.read_parquet(cp)            # A-share close/high/low/volume (no open)
            df = df.copy()
            if "open" not in df.columns:
                df["open"] = df["close"]
            out = df
        elif yp.exists():
            df = pd.read_parquet(yp)            # close[,volume]
            df = df.copy()
            for c in ("open", "high", "low"):
                if c not in df.columns:
                    df[c] = df["close"]
            if "volume" not in df.columns:
                df["volume"] = np.nan
            out = df
        if out is not None:
            out = out[[c for c in OHLCV_COLS if c in out.columns]].copy()
            out.index = pd.DatetimeIndex(out.index)
            out = out[~out.index.duplicated(keep="last")].sort_index()
    except Exception as e:  # noqa: BLE001
        log.warning("basket member OHLCV unreadable %s: %s", ticker, e)
        out = None
    _CACHE[ticker] = out
    return out


def deep_calendar(members: list[dict], min_start: str | None = None) -> pd.DatetimeIndex:
    """Union trading calendar across the members' deep OHLCV (back to ~2014), so the MONTHLY /
    weekly MTF timeframes resolve — the shallow ~3y baskets close-cache index is too short for
    month-end MACD (engine.cycles needs ~900 trading days). Empty index if nothing loads."""
    cals = []
    for m in members:
        df = _load_member_ohlcv(m.get("ticker"))
        if df is not None and not df.empty:
            cals.append(df.index)
    if not cals:
        return pd.DatetimeIndex([])
    idx = cals[0]
    for c in cals[1:]:
        idx = idx.union(c)
    idx = pd.DatetimeIndex(idx).sort_values()
    if min_start:
        idx = idx[idx >= pd.Timestamp(min_start)]
    return idx


def _live_mask(members: list[dict], idx: pd.DatetimeIndex, present: list[str],
               pit: bool = True, close: pd.DataFrame | None = None) -> pd.DataFrame:
    """Boolean [date × ticker] membership mask.

    pit=True  → strict point-in-time: a member is live only in [added, removed). This is the
                perf-faithful index that matches engine.baskets._ew_level.
    pit=False → CURRENT membership over its FULL available history: live wherever the member has
                traded (and not after `removed`), ignoring `added`. This is the read the MTF /
                vol-hole engines want — the technical picture of the basket AS CONSTITUTED TODAY,
                deep enough for the monthly timeframe — not gated to when the curator added a name.
    """
    mask = pd.DataFrame(False, index=idx, columns=present)
    for m in members:
        t = m.get("ticker")
        if t not in present:
            continue
        if pit:
            a = np.asarray(idx >= pd.Timestamp(m["added"]))
        elif close is not None and t in close:
            fv = close[t].first_valid_index()
            a = np.asarray(idx >= fv) if fv is not None else np.zeros(len(idx), dtype=bool)
        else:
            a = np.ones(len(idx), dtype=bool)
        if m.get("removed"):
            a = a & np.asarray(idx < pd.Timestamp(m["removed"]))
        mask[t] = a
    return mask


def _base_weights(members: list[dict], present: list[str], mode: str,
                  conv_map: dict | None, ret: pd.DataFrame, mask: pd.DataFrame) -> pd.Series:
    """Per-member STATIC base weight (renormalised over the live set each day downstream)."""
    if mode == "relevance":
        wm = {}
        cm = conv_map or {}
        for m in members:
            t = m.get("ticker")
            if t not in present:
                continue
            w = m.get("weight")
            if w is None:
                sc = cm.get(t)
                w = (float(sc) / 50.0) if sc is not None else 1.0   # conviction 50 ⇒ equal
            wm[t] = max(float(w), 0.05)
        return pd.Series(wm).reindex(present).fillna(1.0)
    if mode == "alpha":
        # trailing 120d risk-adjusted strength of each member (only over its live days), z-scored
        rr = ret[present].where(mask)
        win = min(120, len(rr))
        seg = rr.iloc[-win:]
        mu = seg.mean()
        sd = seg.std().replace(0, np.nan)
        strength = (mu / sd).replace([np.inf, -np.inf], np.nan)
        sstd = strength.std()
        denom = sstd if (sstd and np.isfinite(sstd)) else 1.0       # NaN/0 std → no spread → equal
        z = (strength - strength.mean()) / denom
        w = np.exp(np.clip(z.fillna(0.0), -1.5, 1.5))               # softmax-ish tilt
        w = (w / w.mean()).clip(1.0 / ALPHA_CAP, ALPHA_CAP)         # capped vs equal
        return w.reindex(present).fillna(1.0)
    return pd.Series(1.0, index=present)                            # equal


def consolidated_candle(members: list[dict], idx: pd.DatetimeIndex, mode: str = "equal",
                        conv_map: dict | None = None, pit: bool = True
                        ) -> tuple[pd.DataFrame | None, dict]:
    """The basket CANDLE on calendar `idx`: columns [open, high, low, close, dollar_vol, n_live],
    + a coverage/meta dict. None if fewer than 3 members resolve OHLCV. close is a LEVEL from 1.0.

    `members` are membership entries ({ticker, added, removed, weight?}); `idx` the basket
    calendar; `conv_map` ticker→conviction score for relevance weighting; `pit` selects strict
    point-in-time membership (True, perf-faithful) vs current-membership-over-full-history
    (False, for the deep MTF/vol-hole technical read). See _live_mask."""
    tickers = [m.get("ticker") for m in members if m.get("ticker")]
    loaded = {t: _load_member_ohlcv(t) for t in tickers}
    present = [t for t in tickers if loaded.get(t) is not None and not loaded[t].empty]
    n_total = len(set(tickers))
    if len(present) < 3:
        return None, {"n_total": n_total, "n_with_ohlcv": len(present), "coverage_pct": None,
                      "mode": mode}

    # align each field to the basket calendar
    def _field(col: str) -> pd.DataFrame:
        cols = {t: loaded[t][col].reindex(idx) for t in present if col in loaded[t].columns}
        return pd.DataFrame(cols, index=idx)

    close = _field("close").ffill()
    high = _field("high").ffill()
    low = _field("low").ffill()
    open_ = _field("open").ffill()
    vol = _field("volume")

    prev_close = close.shift(1)
    r_close = close / prev_close - 1.0
    r_high = high / prev_close - 1.0
    r_low = low / prev_close - 1.0
    r_open = open_ / prev_close - 1.0

    mask = _live_mask(members, idx, present, pit=pit, close=close)
    base_w = _base_weights(members, present, mode, conv_map, r_close, mask)

    # daily renormalised weights over the live set
    w = mask.astype(float) * base_w.reindex(present).to_numpy()
    wsum = w.sum(axis=1).replace(0, np.nan)
    w = w.div(wsum, axis=0)

    def _wret(rf: pd.DataFrame) -> pd.Series:
        return (rf[present] * w).sum(axis=1, min_count=1)

    Rc, Rh, Rl, Ro = _wret(r_close), _wret(r_high), _wret(r_low), _wret(r_open)
    first = Rc.first_valid_index()
    if first is None:
        return None, {"n_total": n_total, "n_with_ohlcv": len(present), "coverage_pct": None,
                      "mode": mode}
    lvl_close = pd.Series(np.nan, index=idx)
    lvl_close.loc[first:] = (1.0 + Rc.loc[first:].fillna(0.0)).cumprod()
    prev_lvl = lvl_close.shift(1)
    prev_lvl.loc[first] = 1.0    # the implicit cumprod base — the level the day before `first`

    cand = pd.DataFrame(index=idx)
    cand["close"] = lvl_close
    cand["high"] = prev_lvl * (1.0 + Rh)
    cand["low"] = prev_lvl * (1.0 + Rl)
    cand["open"] = prev_lvl * (1.0 + Ro)
    # guard the candle ordering (numerical safety): high ≥ {open,close} ≥ low
    cand["high"] = cand[["high", "open", "close"]].max(axis=1)
    cand["low"] = cand[["low", "open", "close"]].min(axis=1)

    # traded dollar-volume over the live set = Σ price·volume
    dvol = (close[present] * vol[present]).where(mask)
    cand["dollar_vol"] = dvol.sum(axis=1, min_count=1)
    cand["n_live"] = mask.sum(axis=1)
    cand = cand.loc[first:]

    n_live_now = int(mask.iloc[-1].sum())
    with_vol_now = int((vol[present].iloc[-1].notna() & (vol[present].iloc[-1] > 0) & mask.iloc[-1]).sum())
    meta = {
        "mode": mode, "n_total": n_total, "n_with_ohlcv": len(present),
        "n_live": n_live_now, "n_live_with_volume": with_vol_now,
        "coverage_pct": round(with_vol_now / n_live_now, 3) if n_live_now else None,
        "as_of": str(cand.index.max().date()) if not cand.empty else None,
        "start": str(cand.index.min().date()) if not cand.empty else None,
    }
    return cand, meta


def weight_variants(members: list[dict], idx: pd.DatetimeIndex,
                    conv_map: dict | None = None) -> dict:
    """The three weighting schemes' CLOSE levels (rebased to 1.0), for the comparison overlay.
    Display-only — lets the user see how a conviction- or alpha-tilt reshapes the same basket."""
    out = {}
    for mode in ("equal", "relevance", "alpha"):
        cand, _ = consolidated_candle(members, idx, mode, conv_map)
        if cand is not None and not cand["close"].dropna().empty:
            out[mode] = [None if pd.isna(v) else round(float(v), 5) for v in cand["close"].reindex(idx)]
    return out
