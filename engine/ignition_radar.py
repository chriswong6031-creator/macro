"""Ignition Radar — risk-ON mirror of the Risk Radar (点火雷达).

DISPLAY-ONLY, FORWARD-GRADED, NOT VALIDATED — nothing here is a buy signal;
states are evidence-taxonomy labels graded by engine.ignition_audit (US arm).

Masterplan §2 IGN-R1..R6, §3 WB, §7.3/7.4. Two channels, NEVER fused into
any cross-channel score:

BROAD channel (K-of-8 confluence count)
  4 thrust/confirmation events reused from engine.risk_radar_market_catalysts.compute()
  — chips c1_thrust_confluence / c2_msi_swing / c3_washout_thrust20 / c4_ftd —
  selected by key prefix (c1/c2/c3/c4).
  4 participation confirms computed here from stores (degrade-don't-crash each):
    pct50_recover    breadth pct_above_50 >= 55 AND +5 pts over 10 sessions
    nh_flip          10d mean of (nh - nl) crossed from <=0 to >0 within 10 sessions
    rsp_confirm      20d log RS slope of RSP vs SPY > 0
    sector_participation >=8 of 11 GICS sector ETFs above 50dma AND 50dma rising

NARROW channel
  compute_basket_ignition from engine.sector_ignition — per US thematic basket +
  the 11 sector ETFs + SMH as coarse items.

Cross-channel LABEL
  regime: broad ignited / narrow / warming / off — bilingual.

Pure compute separated from I/O (compute functions take frames; thin loader
assembles then writes data/ignition_radar/latest.json).
"""
from __future__ import annotations

import json
import logging
import math
import time
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from lib import config, store
from engine.sector_ignition import compute_basket_ignition, STATE_IGNITING

log = logging.getLogger(__name__)

_FRESH_BD = 10          # business days within which a catalyst chip is "fresh"
_K_IGNITED = 3          # broad K threshold for "ignited"
_K_WARMING = 1          # broad K threshold for "warming"
_SECTOR_ETFS = ["XLK", "XLF", "XLV", "XLY", "XLP", "XLE", "XLI", "XLB", "XLU", "XLRE", "XLC"]
_COARSE_ITEMS = _SECTOR_ETFS + ["SMH"]


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

def _iso(ts) -> str | None:
    try:
        if ts is None or (isinstance(ts, float) and np.isnan(ts)):
            return None
        return str(pd.Timestamp(ts).date())
    except Exception:  # noqa: BLE001
        return None


def _bd_since(ts) -> int | None:
    if ts is None:
        return None
    try:
        t = pd.Timestamp(ts)
        today = pd.Timestamp(date.today())
        bdays = len(pd.bdate_range(t, today)) - 1
        return max(0, bdays)
    except Exception:  # noqa: BLE001
        return None


def _is_fresh(ts) -> bool:
    bd = _bd_since(ts)
    return bd is not None and bd <= _FRESH_BD


def _absent_chip(key: str, label_en: str, label_zh: str, note: str) -> dict:
    return {
        "key": key,
        "label_en": label_en,
        "label_zh": label_zh,
        "lit": False,
        "fresh": False,
        "since": None,
        "detail_en": note,
        "detail_zh": note,
        "source": "risk_radar_market_catalysts",
    }


# ---------------------------------------------------------------------------
# BROAD CHANNEL — pull C1–C4 from risk_radar_market_catalysts
# ---------------------------------------------------------------------------

def _broad_thrust_chips(catalysts_payload: dict | None) -> list[dict]:
    """Extract the 4 thrust chips (c1..c4) from the catalysts payload.

    Spec: select by key prefix c1/c2/c3/c4 (NOT by any 'channel' field —
    a sibling PR adds that field and we must not depend on it).
    """
    prefixes = ("thrust_confluence", "msi_swing", "washout_thrust20", "ftd")
    label_map = {
        "thrust_confluence": ("Breadth thrust confluence", "广度推进共振"),
        "msi_swing":         ("Summation low→high swing", "麦克伦求和指数低位跃升"),
        "washout_thrust20":  ("%>20dma washout→thrust",  "20日线上比例洗出→推进"),
        "ftd":               ("Follow-through day",       "放量确认日"),
    }

    chips_raw = (catalysts_payload or {}).get("chips", [])
    out = []
    matched_keys: set[str] = set()

    for pfx in prefixes:
        matched = [c for c in chips_raw if c.get("key", "").startswith(pfx) or c.get("key") == pfx]
        if matched:
            c = matched[0]
            key = c.get("key", pfx)
            matched_keys.add(key)
            labels = label_map.get(pfx, (key, key))
            out.append({
                "key": key,
                "label_en": c.get("label_en", labels[0]),
                "label_zh": c.get("label_zh", labels[1]),
                "lit": bool(c.get("fired") and c.get("fresh")),
                "fresh": bool(c.get("fresh")),
                "since": c.get("since"),
                "detail_en": str((c.get("detail") or {}).get("note", "")),
                "detail_zh": str((c.get("detail") or {}).get("note", "")),
                "source": "risk_radar_market_catalysts",
            })
        else:
            labels = label_map.get(pfx, (pfx, pfx))
            out.append(_absent_chip(pfx, labels[0], labels[1],
                                    "catalysts payload absent or chip not found"))

    return out


# ---------------------------------------------------------------------------
# BROAD CHANNEL — 4 participation confirms computed from stores
# ---------------------------------------------------------------------------

def _confirm_pct50_recover(breadth: pd.DataFrame | None) -> dict:
    """pct_above_50 >= 55 AND gained +5 pts over 10 sessions."""
    key, label_en, label_zh = "pct50_recover", "Breadth >50dma recovery", "50日线广度回升"
    try:
        if breadth is None or breadth.empty or "pct_above_50" not in breadth.columns:
            return _absent_chip(key, label_en, label_zh, "breadth/pct_above_50 unavailable")
        b = breadth["pct_above_50"].dropna().sort_index()
        if len(b) < 12:
            return _absent_chip(key, label_en, label_zh, "insufficient breadth history")
        now_val = float(b.iloc[-1])
        prev_val = float(b.iloc[-11])   # 10 sessions ago
        lit = (now_val >= 55.0) and ((now_val - prev_val) >= 5.0)
        # find the date it first crossed 55 in the last 10bd (for "since")
        since = None
        if lit:
            w10 = b.iloc[-11:]
            above55 = w10[w10 >= 55.0]
            since = _iso(above55.index[0]) if not above55.empty else None
        return {
            "key": key, "label_en": label_en, "label_zh": label_zh,
            "lit": lit, "fresh": lit and _is_fresh(since),
            "since": since,
            "detail_en": f"pct_above_50={now_val:.1f}% (was {prev_val:.1f}% 10d ago)",
            "detail_zh": f"50日线上比例={now_val:.1f}%（10日前{prev_val:.1f}%）",
            "source": "breadth",
        }
    except Exception as e:  # noqa: BLE001
        return _absent_chip(key, label_en, label_zh, f"error: {e}")


def _confirm_nh_flip(breadth: pd.DataFrame | None) -> dict:
    """10d mean of (nh - nl) crossed from <=0 to >0 within last 10 sessions."""
    key, label_en, label_zh = "nh_flip", "New highs flipping positive", "新高翻正"
    try:
        if breadth is None or breadth.empty:
            return _absent_chip(key, label_en, label_zh, "breadth unavailable")
        req = {"nh", "nl"}
        if not req.issubset(breadth.columns):
            return _absent_chip(key, label_en, label_zh, "nh/nl columns missing")
        b = breadth[["nh", "nl"]].dropna().sort_index()
        if len(b) < 22:
            return _absent_chip(key, label_en, label_zh, "insufficient breadth history")
        spread = (b["nh"] - b["nl"]).astype(float)
        mean10 = spread.rolling(10, min_periods=5).mean()
        if len(mean10) < 11:
            return _absent_chip(key, label_en, label_zh, "rolling window insufficient")
        # did it cross from <=0 to >0 in the last 10 sessions?
        now_mean = float(mean10.iloc[-1])
        prev_mean = float(mean10.iloc[-11])
        lit = (prev_mean <= 0) and (now_mean > 0)
        since = None
        if lit:
            # find first date in last 10 where mean10 > 0
            w10 = mean10.iloc[-10:]
            positive = w10[w10 > 0]
            since = _iso(positive.index[0]) if not positive.empty else None
        return {
            "key": key, "label_en": label_en, "label_zh": label_zh,
            "lit": lit, "fresh": lit and _is_fresh(since),
            "since": since,
            "detail_en": f"10d mean(nh-nl)={now_mean:.1f} (was {prev_mean:.1f} 10d ago)",
            "detail_zh": f"10日均(新高-新低)={now_mean:.1f}（10日前{prev_mean:.1f}）",
            "source": "breadth",
        }
    except Exception as e:  # noqa: BLE001
        return _absent_chip(key, label_en, label_zh, f"error: {e}")


def _find_last_crossing(bool_series: pd.Series) -> pd.Timestamp | None:
    """Find the most recent False→True crossing in bool_series.

    Returns the index timestamp of the first True in the most recent True-run
    that was preceded by a False, or None if no such crossing exists.
    """
    if len(bool_series) < 2:
        return None
    # Walk backwards to find the start of the current True-run
    vals = bool_series.values
    idx = bool_series.index
    n = len(vals)
    if not vals[-1]:
        return None  # currently False — no active crossing
    # Find where the current True-run begins
    i = n - 1
    while i > 0 and vals[i - 1]:
        i -= 1
    # i is now the start of the current True-run; it must have been preceded by a False
    if i == 0:
        return None  # True the whole time — no crossing detected
    return idx[i]


def _confirm_rsp_confirm() -> dict:
    """20d log RS slope of RSP vs SPY > 0.

    lit   = slope > 0 now (STATE).
    fresh = a <=0 → >0 crossing occurred within the last 15 sessions AND <=10bd ago.
    since = the crossing date (not today).
    """
    key, label_en, label_zh = "rsp_confirm", "Equal-weight RS (RSP/SPY)", "等权RS（RSP/SPY）"
    try:
        rsp_df = store.read("yahoo", "RSP")
        spy_df = store.read("yahoo", "SPY")
        if rsp_df is None or spy_df is None:
            return _absent_chip(key, label_en, label_zh, "RSP or SPY unavailable")
        rsp = rsp_df["close"].dropna().sort_index().astype(float)
        spy = spy_df["close"].dropna().sort_index().astype(float)
        rsp.index = pd.to_datetime(rsp.index)
        spy.index = pd.to_datetime(spy.index)
        common = rsp.index.intersection(spy.index)
        if len(common) < 30:
            return _absent_chip(key, label_en, label_zh, "insufficient RSP/SPY history")
        rsp = rsp.loc[common]
        spy = spy.loc[common]
        rs = rsp / spy
        rs = rs.replace([np.inf, -np.inf], np.nan).dropna()
        if len(rs) < 22:
            return _absent_chip(key, label_en, label_zh, "RS series too short")

        # Compute rolling 20d log-RS slope over the trailing 15+21 sessions
        # so we can detect the last ≤0→>0 crossing within 15 sessions.
        n_lookback = 15 + 21  # need 21-bar window for each slope point
        window = rs.iloc[-(n_lookback + 21):] if len(rs) > n_lookback + 21 else rs
        slopes = pd.Series(
            [
                (
                    math.log(float(window.iloc[j]) / float(window.iloc[j - 20]))
                    if window.iloc[j - 20] > 0 and window.iloc[j] > 0
                    else float("nan")
                )
                for j in range(20, len(window))
            ],
            index=window.index[20:],
        )
        if slopes.empty or slopes.isna().all():
            return _absent_chip(key, label_en, label_zh, "log RS slope undefined")

        slope_raw = float(slopes.iloc[-1]) if not np.isnan(slopes.iloc[-1]) else None
        if slope_raw is None:
            return _absent_chip(key, label_en, label_zh, "log RS slope undefined")

        lit = slope_raw > 0

        # Detect the most recent ≤0→>0 crossing within the last 15 slope sessions
        recent_slopes = slopes.iloc[-15:] if len(slopes) >= 15 else slopes
        positive_now = recent_slopes > 0
        crossing_ts = _find_last_crossing(positive_now)
        fresh = crossing_ts is not None and _is_fresh(crossing_ts)
        since = _iso(crossing_ts) if crossing_ts is not None else None

        return {
            "key": key, "label_en": label_en, "label_zh": label_zh,
            "lit": lit, "fresh": fresh,
            "since": since,
            "detail_en": (
                f"20d log-RS slope={slope_raw:.4f} ({'positive' if lit else 'negative'})"
                + (f"; turned positive {_bd_since(since)}bd ago" if fresh else
                   ("; state positive but no recent turn (~>2–3 wks)" if lit else ""))
            ),
            "detail_zh": (
                f"20日对数RS斜率={slope_raw:.4f}（{'正向' if lit else '负向'}）"
                + (f"；{_bd_since(since)}日前转正" if fresh else
                   ("；状态正向但近期无转折（约>2–3周）" if lit else ""))
            ),
            "source": "yahoo/RSP,SPY",
        }
    except Exception as e:  # noqa: BLE001
        return _absent_chip(key, label_en, label_zh, f"error: {e}")


def _confirm_sector_participation() -> dict:
    """>=8 of 11 GICS sector ETFs close > 50dma AND 50dma rising over 10 sessions.

    Denominator = present ETFs; threshold = ceil(8/11 * n_present).

    lit   = count >= threshold now (STATE).
    fresh = count crossed from < threshold to >= threshold within the last 15 sessions AND <=10bd ago.
    since = the crossing date (not today).
    """
    key, label_en, label_zh = "sector_participation", "Sector breadth (8-of-11)", "板块广度（11中8）"
    try:
        # Load each sector ETF and build a time-series of per-day "above_and_rising" flags.
        # We need at least 15 trailing sessions to detect a crossing.
        n_lookback = 15 + 1  # 15 crossing-detection sessions + 1 guard
        etf_series: dict[str, pd.Series] = {}
        for ticker in _SECTOR_ETFS:
            try:
                df = store.read("yahoo", ticker)
                if df is None or "close" not in df.columns:
                    continue
                s = df["close"].dropna().sort_index().astype(float)
                s.index = pd.to_datetime(s.index)
                if len(s) < 55:
                    continue
                etf_series[ticker] = s
            except Exception:  # noqa: BLE001
                continue

        n_present = len(etf_series)
        if n_present == 0:
            return _absent_chip(key, label_en, label_zh, "no sector ETF data")

        import math as _math
        threshold = _math.ceil(8 / 11 * n_present)

        # Build a common date index spanning the last n_lookback+ sessions
        all_idx = sorted(set().union(*[set(s.index) for s in etf_series.values()]))
        if not all_idx:
            return _absent_chip(key, label_en, label_zh, "no common dates")
        window_dates = all_idx[-(n_lookback + 60):]  # extra buffer for rolling MA

        # For each date in window, count ETFs satisfying above + rising.
        # "rising" = MA50 at loc > MA50 at loc-10 (same pure-backward calculation).
        count_series_data = []
        for d in window_dates:
            n_lit = 0
            for s in etf_series.values():
                if d not in s.index:
                    continue
                loc = s.index.get_loc(d)
                if loc < 59:  # need at least 60 bars for ma50_prev at loc-10
                    continue
                seg_now = s.iloc[loc - 49: loc + 1]   # 50 bars ending at loc
                ma50_now = seg_now.mean()
                seg_prev = s.iloc[loc - 59: loc - 9]   # 50 bars ending at loc-10
                ma50_prev = seg_prev.mean()
                above = bool(float(s.iloc[loc]) > ma50_now)
                rising = bool(ma50_now > ma50_prev)
                if above and rising:
                    n_lit += 1
            count_series_data.append((d, n_lit))

        if not count_series_data:
            return _absent_chip(key, label_en, label_zh, "no count series built")

        count_idx = pd.DatetimeIndex([r[0] for r in count_series_data])
        count_vals = [r[1] for r in count_series_data]
        count_s = pd.Series(count_vals, index=count_idx)

        n_lit_now = int(count_s.iloc[-1])
        lit = n_lit_now >= threshold

        # Detect crossing: count < threshold → >= threshold in the last 15 sessions
        recent_count = count_s.iloc[-15:] if len(count_s) >= 15 else count_s
        above_threshold = recent_count >= threshold
        crossing_ts = _find_last_crossing(above_threshold)
        fresh = crossing_ts is not None and _is_fresh(crossing_ts)
        since = _iso(crossing_ts) if crossing_ts is not None else None

        detail_en = (
            f"{n_lit_now}/{n_present} ETFs above rising 50dma (need {threshold})"
            + (f"; turned on {_bd_since(since)}bd ago" if fresh else
               ("; state met but no recent turn (~>2–3 wks)" if lit else ""))
        )
        detail_zh = (
            f"{n_lit_now}/{n_present}个ETF高于上升中50日线（需{threshold}个）"
            + (f"；{_bd_since(since)}日前达标" if fresh else
               ("；状态达标但近期无转折（约>2–3周）" if lit else ""))
        )
        return {
            "key": key, "label_en": label_en, "label_zh": label_zh,
            "lit": lit, "fresh": fresh,
            "since": since,
            "detail_en": detail_en,
            "detail_zh": detail_zh,
            "source": "yahoo/sector_etfs",
        }
    except Exception as e:  # noqa: BLE001
        return _absent_chip(key, label_en, label_zh, f"error: {e}")


# ---------------------------------------------------------------------------
# BROAD CHANNEL — state from K count
# ---------------------------------------------------------------------------

def _broad_state(k: int, chips: list[dict]) -> str:
    """ignited = K>=3 AND >=1 thrust chip lit fresh; warming = K>=1 fresh; off."""
    thrust_keys = {"thrust_confluence", "msi_swing", "washout_thrust20", "ftd"}
    has_thrust = any(c["lit"] and c.get("fresh") and c["key"] in thrust_keys for c in chips)
    n_fresh = sum(1 for c in chips if c.get("fresh"))
    if k >= _K_IGNITED and has_thrust and n_fresh >= _K_IGNITED:
        return "ignited"
    if n_fresh >= _K_WARMING:
        return "warming"
    return "off"


# ---------------------------------------------------------------------------
# BROAD CHANNEL — compute
# ---------------------------------------------------------------------------

def compute_broad(
    catalysts_payload: dict | None,
    breadth: pd.DataFrame | None,
) -> dict:
    """Pure: compute the 8-chip broad confluence count.

    Returns {k_count, state, chips[8], as_of}.
    """
    # 4 thrust chips from catalysts
    thrust_chips = _broad_thrust_chips(catalysts_payload)

    # 4 participation confirms
    confirm_chips = [
        _confirm_pct50_recover(breadth),
        _confirm_nh_flip(breadth),
        _confirm_rsp_confirm(),
        _confirm_sector_participation(),
    ]

    chips = thrust_chips + confirm_chips
    k_count = sum(1 for c in chips if c.get("lit"))
    state = _broad_state(k_count, chips)

    return {
        "as_of": str(date.today()),
        "k_count": k_count,
        "state": state,
        "chips": chips,
    }


# ---------------------------------------------------------------------------
# NARROW CHANNEL — US thematic baskets + coarse sector ETFs
# ---------------------------------------------------------------------------

def _load_ticker_series(ticker: str, ticker_cache: dict[str, pd.Series | None]) -> pd.Series | None:
    """Load a single ticker's close Series, using ticker_cache to avoid redundant reads.

    ticker_cache is a dict[ticker -> Series|None] that is created once per snapshot() call
    and threaded through _load_member_closes so that tickers shared across baskets are only
    read from disk once.
    """
    if ticker in ticker_cache:
        return ticker_cache[ticker]
    result: pd.Series | None = None
    try:
        from lib import config as _cfg
        p = _cfg.data_dir() / "baskets" / "ohlcv" / f"{ticker}.parquet"
        if p.exists():
            df = pd.read_parquet(p)
            if "close" in df.columns:
                s = df["close"].dropna().sort_index().astype(float)
                if not s.empty:
                    result = s
    except Exception:  # noqa: BLE001
        pass
    ticker_cache[ticker] = result
    return result


def _load_member_closes(
    basket_id: str,
    members: list[dict],
    as_of_date: pd.Timestamp | None = None,
    ticker_cache: dict[str, pd.Series | None] | None = None,
) -> pd.DataFrame | None:
    """Load current-member closes from data/baskets/ohlcv/<ticker>.parquet.

    Only members with removed=None or removed > as_of_date are included.
    ticker_cache (dict[ticker->Series|None]) is created once in snapshot() and passed through
    to avoid redundant parquet reads when the same ticker appears in multiple baskets.
    Falls back to data/breadth/_closes_cache.parquet for S&P members if ohlcv absent.
    """
    if ticker_cache is None:
        ticker_cache = {}
    ref_date = as_of_date or pd.Timestamp(date.today())
    closes: dict[str, pd.Series] = {}
    for m in members:
        ticker = m.get("ticker")
        removed = m.get("removed")
        if not ticker:
            continue
        # respect removal date
        if removed is not None:
            try:
                if pd.Timestamp(removed) <= ref_date:
                    continue
            except Exception:  # noqa: BLE001
                pass
        s = _load_ticker_series(ticker, ticker_cache)
        if s is not None:
            closes[ticker] = s
    if not closes:
        return None
    result = pd.DataFrame(closes)
    result.index = pd.to_datetime(result.index)
    return result.sort_index()


def _load_etf_series(ticker: str) -> pd.Series | None:
    """Load close series for a sector ETF."""
    try:
        df = store.read("yahoo", ticker)
        if df is None or "close" not in df.columns:
            return None
        s = df["close"].dropna().sort_index().astype(float)
        s.index = pd.to_datetime(s.index)
        return s if len(s) > 60 else None
    except Exception:  # noqa: BLE001
        return None


def _quality_flags(level: pd.Series | None, spy: pd.Series | None) -> dict:
    """rs_new_high: 20d RS ratio vs SPY at a 126d high.
       above_200d_rising: level > 200dma AND 200dma rising.
    """
    flags = {"rs_new_high": False, "above_200d_rising": False}
    if level is None or len(level) < 30:
        return flags
    try:
        s = level.sort_index().astype(float)
        # above_200d_rising
        if len(s) >= 210:
            ma200 = s.rolling(200, min_periods=100).mean()
            flags["above_200d_rising"] = bool(s.iloc[-1] > ma200.iloc[-1] and ma200.iloc[-1] > ma200.iloc[-11])
        # rs_new_high
        if spy is not None and len(spy) > 60:
            spy_s = spy.sort_index().astype(float)
            common = s.index.intersection(spy_s.index)
            if len(common) >= 130:
                rs = (s.loc[common] / spy_s.loc[common]).replace([np.inf, -np.inf], np.nan).dropna()
                if len(rs) >= 130:
                    now_rs = float(rs.iloc[-1])
                    hi126 = float(rs.iloc[-126:].max())
                    flags["rs_new_high"] = bool(now_rs >= hi126 * 0.999)  # at or near a 126d high
    except Exception:  # noqa: BLE001
        pass
    return flags


def compute_narrow(
    membership: dict,
    spy_series: pd.Series | None,
    ticker_cache: dict[str, pd.Series | None] | None = None,
) -> dict:
    """Compute the narrow channel: per-basket ignition scores + coarse sector ETFs.

    membership: the 'baskets' dict from membership.json (keyed by basket id).
    spy_series: SPY close series.
    ticker_cache: optional dict[ticker->Series|None] shared across all baskets to avoid
        redundant parquet reads when the same ticker appears in multiple baskets.
        Created per snapshot() call and passed through.
    Returns {as_of, items:[...sorted by ignition_score desc]}.
    """
    if ticker_cache is None:
        ticker_cache = {}
    as_of = str(date.today())
    items = []
    spy_bench = spy_series  # SPY as benchmark for all US baskets

    # --- thematic baskets ---
    for bid, b in (membership or {}).items():
        name = b.get("name", bid)
        name_zh = b.get("name_zh", name)
        category = b.get("category", "")
        members = b.get("members", [])
        try:
            member_closes = _load_member_closes(bid, members, ticker_cache=ticker_cache)
            # build EW level from member closes (rebase 100)
            if member_closes is not None and not member_closes.empty:
                normed = member_closes / member_closes.iloc[0] * 100
                level = normed.mean(axis=1)
            else:
                level = None
            ig = compute_basket_ignition(bid, member_closes, level, spy_bench)
            qf = _quality_flags(level, spy_bench)
            ig["name"] = name
            ig["name_zh"] = name_zh
            ig["category"] = category
            ig["type"] = "basket"
            ig["rs_new_high"] = qf["rs_new_high"]
            ig["above_200d_rising"] = qf["above_200d_rising"]
            items.append(ig)
        except Exception as e:  # noqa: BLE001
            log.warning("ignition_radar narrow basket %s failed: %s", bid, e)
            continue

    # --- coarse items: sector ETFs + SMH ---
    for ticker in _COARSE_ITEMS:
        try:
            level = _load_etf_series(ticker)
            if level is None:
                continue
            ig = compute_basket_ignition(ticker, member_closes=None, level=level, bench=spy_bench)
            qf = _quality_flags(level, spy_bench)
            ig["name"] = ticker
            ig["name_zh"] = ticker
            ig["category"] = "Sector ETF"
            ig["type"] = "etf"
            ig["rs_new_high"] = qf["rs_new_high"]
            ig["above_200d_rising"] = qf["above_200d_rising"]
            items.append(ig)
        except Exception as e:  # noqa: BLE001
            log.warning("ignition_radar narrow etf %s failed: %s", ticker, e)
            continue

    items.sort(key=lambda x: (x["ignition_score"] is None, -(x["ignition_score"] or 0.0)))
    return {"as_of": as_of, "items": items}


# ---------------------------------------------------------------------------
# CROSS-CHANNEL REGIME LABEL
# ---------------------------------------------------------------------------

def _top_igniting_name(narrow_items: list[dict]) -> str:
    """Name of top igniting basket/etf or '' if none."""
    for it in narrow_items:
        if it.get("state") in ("igniting", "running"):
            return it.get("name", "")
    return ""


def compute_regime(
    broad_state: str,
    narrow_items: list[dict],
    rsp_confirm_lit: bool,
    sector_participation_lit: bool,
) -> dict:
    """Derive the cross-channel regime label. Never a score."""
    top_name = _top_igniting_name(narrow_items)
    narrow_igniting = bool(top_name)
    participation_ok = rsp_confirm_lit or sector_participation_lit

    if broad_state == "ignited" and narrow_igniting:
        label_en = f"Broad ignition + {top_name} leading"
        label_zh = f"全面点火 + {top_name}领涨"
        fragile = False
        do_en = "Broad thrust + theme leadership. Evidence read, not a buy call — confluence with your own entry process."
        do_zh = "全面推进且主题领涨。证据读取，非买入信号 — 请结合您的入场流程综合判断。"
    elif broad_state == "ignited":
        label_en = "Broad ignition — participation surging"
        label_zh = "全面点火 — 参与度激增"
        fragile = False
        do_en = "Broad thrust evident. Evidence read, not a buy call — confluence with your own entry process."
        do_zh = "全面推进明显。证据读取，非买入信号 — 请结合您的入场流程综合判断。"
    elif narrow_igniting and not participation_ok:
        label_en = f"Narrow ignition — {top_name}; fragile until participation broadens"
        label_zh = f"局部点火 — {top_name}；需参与度扩散方可确认"
        fragile = True
        do_en = "Theme-level evidence only. Fragile until RSP or sector breadth confirms. Evidence read, not a buy call."
        do_zh = "仅主题级证据，RSP或板块广度未确认前存在脆弱性。证据读取，非买入信号。"
    elif narrow_igniting and participation_ok:
        label_en = f"Theme ignition — {top_name}, participation OK"
        label_zh = f"主题点火 — {top_name}，参与度尚可"
        fragile = False
        do_en = "Theme ignition with adequate participation. Evidence read, not a buy call — confluence with your own entry process."
        do_zh = "主题点火且参与度尚可。证据读取，非买入信号 — 请结合您的入场流程综合判断。"
    elif broad_state == "warming":
        label_en = "Warming — early risk-on evidence"
        label_zh = "升温 — 初步偏多信号"
        fragile = False
        do_en = "Early-stage evidence only. Evidence read, not a buy call."
        do_zh = "仅初步阶段证据。证据读取，非买入信号。"
    else:
        label_en = "No ignition"
        label_zh = "未点火"
        fragile = False
        do_en = "No confirming evidence. Evidence read, not a buy call."
        do_zh = "无确认证据。证据读取，非买入信号。"

    return {
        "label_en": label_en,
        "label_zh": label_zh,
        "fragile": fragile,
        "do_en": do_en,
        "do_zh": do_zh,
    }


# ---------------------------------------------------------------------------
# RADAR CROSS-REFERENCE
# ---------------------------------------------------------------------------

def _load_radar_xref() -> dict:
    """Read risk radar state + trajectory from data/market_state/latest.json.
    Degrade gracefully if absent.
    """
    try:
        from lib import config as _cfg
        p = _cfg.data_dir() / "market_state" / "latest.json"
        if not p.exists():
            return {"state": None, "phase": None}
        payload = json.loads(p.read_text())
        radar = payload.get("radar") or {}
        return {
            "state": radar.get("state"),
            "phase": payload.get("phase") or payload.get("trajectory"),
        }
    except Exception:  # noqa: BLE001
        return {"state": None, "phase": None}


# ---------------------------------------------------------------------------
# NARROW STREAK — consecutive daily sessions at or above the igniting threshold
# ---------------------------------------------------------------------------

_STREAK_FILE = "narrow_streak.json"  # inside data/ignition_radar/


def _streak_from_us_log(basket_id: str, log_path: Path) -> tuple[int, str | None]:
    """Count consecutive trailing days in us_ignition.jsonl where basket_id's
    ignition_score >= STATE_IGNITING.

    Reads the us_ignition.jsonl (sorted ascending by asof), walks backward from
    the most-recent entry counting consecutive sessions where the basket meets the
    threshold.

    Returns (streak_count, most_recent_asof) where most_recent_asof is the
    asof string of the log's newest row (or None when the log is empty/missing).
    The caller uses most_recent_asof to detect whether today's snapshot has
    already been committed to the log (same-day re-render idempotency).
    """
    if not log_path.exists():
        return 0, None
    rows: list[dict] = []
    try:
        for line in log_path.read_text().splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                rows.append(json.loads(line))
            except Exception:  # noqa: BLE001
                continue
    except Exception:  # noqa: BLE001
        return 0, None

    if not rows:
        return 0, None

    # sort by asof ascending
    rows.sort(key=lambda r: r.get("asof", ""))

    most_recent_asof: str | None = rows[-1].get("asof") or None

    streak = 0
    for row in reversed(rows):
        top_narrow = row.get("top_narrow") or []
        found = False
        for it in top_narrow:
            if it.get("id") == basket_id:
                score = it.get("ignition_score") or 0.0
                if float(score) >= STATE_IGNITING:
                    streak += 1
                    found = True
                break
        if not found:
            # basket absent or below threshold — streak broken
            break

    return streak, most_recent_asof


def _update_streak_cache(
    basket_id: str,
    score: float | None,
    today_str: str,
    streak_path: Path,
) -> int:
    """Advance the narrow_streak.json cache (idempotent for same-date reruns).

    If us_ignition.jsonl history has >= 1 entry with this basket, the log-based
    count (from _streak_from_us_log) is authoritative and this file is only a
    warm-start seed.  When the log is empty the file IS the sole persistence.

    Returns the current streak count for basket_id.
    """
    data: dict = {}
    try:
        if streak_path.exists():
            data = json.loads(streak_path.read_text())
    except Exception:  # noqa: BLE001
        data = {}

    entry = data.get(basket_id, {})
    last_date = entry.get("last_date")
    current_streak = int(entry.get("streak", 0))

    above = (score is not None) and (float(score) >= STATE_IGNITING)

    if last_date == today_str:
        # idempotent: same-date rerun — return stored value without modifying
        return current_streak

    if above:
        current_streak += 1
    else:
        current_streak = 0

    data[basket_id] = {
        "streak": current_streak,
        "last_date": today_str,
        "score": score,
    }
    try:
        streak_path.parent.mkdir(parents=True, exist_ok=True)
        streak_path.write_text(json.dumps(data, indent=2))
    except Exception:  # noqa: BLE001
        pass

    return current_streak


def _compute_narrow_top(
    narrow_items: list[dict],
    base_path: Path,
) -> dict | None:
    """Build the narrow_top display payload for the top-ranked narrow basket/ETF.

    Returns None if no item is at or above the igniting threshold.

    Streak calculation — same-date idempotency:

    The us_ignition.jsonl log is the authoritative streak source.  The log may or may
    not contain a row for today depending on when in the pipeline we are called:

      * Nightly first-run: snapshot() runs BEFORE log_us_snapshot() (run.py order),
        so the log does NOT yet contain today.  We count history from the log and add
        +1 via the cache file for the current day.

      * Same-day re-render (engine-render.yml, cortex-retry): log_us_snapshot() has
        ALREADY been called earlier in the day and today's row IS in the log.
        historical_streak already includes today — adding +1 would double-count.

    Fix: compare the log's most-recent asof against today.  If they match, the log
    already includes today so use historical_streak directly.  If the log predates
    today (or is empty), use cache_streak which bridges the current day.
    """
    if not narrow_items:
        return None

    top = narrow_items[0]  # already sorted desc by ignition_score
    score = top.get("ignition_score")
    if score is None or float(score) < STATE_IGNITING:
        return None

    basket_id = top.get("id", "")
    today_str = str(date.today())

    log_path = base_path / "ignition_log" / "us_ignition.jsonl"
    streak_path = base_path / "ignition_radar" / _STREAK_FILE

    # Streak from log + the date of the most-recent log row (for same-day detection)
    historical_streak, log_latest_date = _streak_from_us_log(basket_id, log_path)

    # Advance the cache file (+1 for today, idempotent for same-date reruns)
    cache_streak = _update_streak_cache(basket_id, score, today_str, streak_path)

    # Determine the authoritative streak — idempotent across same-day re-renders:
    #   * log already contains today (same-day re-render) -> log is complete, use as-is.
    #   * log predates today or is empty -> log covers prior days only; bridge +today via cache.
    if log_latest_date == today_str:
        # Today's snapshot is already committed to the log — historical_streak includes today.
        streak = historical_streak
    elif historical_streak > 0:
        # Log has prior-day history; cache adds the current day's +1.
        streak = historical_streak + 1
    else:
        # Log empty or basket never appeared — cache is the sole source.
        streak = cache_streak

    return {
        "basket_id": basket_id,
        "name": top.get("name", basket_id),
        "name_zh": top.get("name_zh", top.get("name", basket_id)),
        "score": score,
        "streak_sessions": streak,
    }


# ---------------------------------------------------------------------------
# SNAPSHOT — main entry point
# ---------------------------------------------------------------------------

def snapshot(root: str | Path | None = None) -> dict:
    """Compute the full Ignition Radar snapshot.

    Returns the payload dict AND writes data/ignition_radar/latest.json.
    Never raises — degrades gracefully on every store failure.
    """
    t0 = time.monotonic()

    # --- load breadth once ---
    breadth: pd.DataFrame | None
    try:
        breadth = store.read("breadth", "breadth")
        if breadth is not None:
            breadth.index = pd.to_datetime(breadth.index)
    except Exception as e:  # noqa: BLE001
        log.warning("ignition_radar: breadth load failed: %s", e)
        breadth = None

    # --- load SPY once ---
    spy_series: pd.Series | None
    try:
        spy_df = store.read("yahoo", "SPY")
        if spy_df is not None and "close" in spy_df.columns:
            spy_series = spy_df["close"].dropna().sort_index().astype(float)
            spy_series.index = pd.to_datetime(spy_series.index)
        else:
            spy_series = None
    except Exception as e:  # noqa: BLE001
        log.warning("ignition_radar: SPY load failed: %s", e)
        spy_series = None

    # --- broad channel: pull catalysts ---
    catalysts_payload: dict | None
    try:
        from engine.risk_radar_market_catalysts import compute as _cats_compute
        catalysts_payload = _cats_compute(root=root)
    except Exception as e:  # noqa: BLE001
        log.warning("ignition_radar: catalysts compute failed: %s", e)
        catalysts_payload = None

    broad = compute_broad(catalysts_payload, breadth)

    # --- narrow channel ---
    membership_data: dict
    try:
        from lib import config as _cfg
        mem_path = _cfg.data_dir() / "baskets" / "membership.json"
        with open(mem_path) as fh:
            raw = json.load(fh)
        membership_data = raw.get("baskets", {})
    except Exception as e:  # noqa: BLE001
        log.warning("ignition_radar: membership.json load failed: %s", e)
        membership_data = {}

    # ticker_cache is created once per snapshot and threaded through compute_narrow /
    # _load_member_closes so that tickers shared across multiple baskets are only read
    # from disk once (eliminates ~329 redundant parquet reads on the 683-ticker universe).
    _ticker_cache: dict[str, "pd.Series | None"] = {}
    narrow = compute_narrow(membership_data, spy_series, ticker_cache=_ticker_cache)
    log.info("[timing] ignition_radar: ticker_cache populated %d unique tickers", len(_ticker_cache))

    # --- regime label ---
    rsp_chip = next((c for c in broad["chips"] if c["key"] == "rsp_confirm"), None)
    sec_chip = next((c for c in broad["chips"] if c["key"] == "sector_participation"), None)
    rsp_lit = bool(rsp_chip and rsp_chip.get("lit"))
    sec_lit = bool(sec_chip and sec_chip.get("lit"))

    regime = compute_regime(
        broad["state"],
        narrow["items"],
        rsp_lit,
        sec_lit,
    )

    # --- radar cross-reference ---
    radar_xref = _load_radar_xref()

    # --- narrow_top streak payload ---
    _base_path = (Path(root) / "data") if root else config.data_dir()
    narrow_top: dict | None = None
    try:
        narrow_top = _compute_narrow_top(narrow["items"], _base_path)
    except Exception as e:  # noqa: BLE001
        log.warning("ignition_radar: narrow_top computation failed: %s", e)

    t1 = time.monotonic()
    elapsed = round(t1 - t0, 2)
    log.info("[timing] ignition_radar.snapshot: %.2fs", elapsed)

    payload = {
        "as_of": str(date.today()),
        "state": broad["state"],
        "k_count": broad["k_count"],
        "chips": broad["chips"],
        "regime": regime,
        "narrow": {
            "items": narrow["items"][:8],
            "as_of": narrow["as_of"],
        },
        "narrow_top": narrow_top,
        "radar_xref": radar_xref,
        "accruing": (
            "accruing — display-only until >=30 broad-state grades + operator ruling. "
            "Forward-graded by engine/ignition_audit.py (US arm)."
        ),
        "_timing_s": elapsed,
    }

    # --- write latest.json ---
    try:
        _base = (Path(root) / "data") if root else config.data_dir()
        out_path = _base / "ignition_radar" / "latest.json"
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(json.dumps(payload, indent=2, default=str))
        log.info("ignition_radar: wrote %s", out_path)
    except Exception as e:  # noqa: BLE001
        log.warning("ignition_radar: write latest.json failed: %s", e)

    return payload
