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
from engine.sector_ignition import compute_basket_ignition

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


def _confirm_rsp_confirm() -> dict:
    """20d log RS slope of RSP vs SPY > 0."""
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
        # 20d log RS slope
        try:
            slope_raw = math.log(float(rs.iloc[-1]) / float(rs.iloc[-21]))
        except (ValueError, ZeroDivisionError):
            return _absent_chip(key, label_en, label_zh, "log RS undefined")
        lit = slope_raw > 0
        since = _iso(rs.index[-21]) if lit else None
        return {
            "key": key, "label_en": label_en, "label_zh": label_zh,
            "lit": lit, "fresh": lit,      # slope is always "recent"
            "since": since,
            "detail_en": f"20d log-RS slope={slope_raw:.4f} ({'positive' if lit else 'negative'})",
            "detail_zh": f"20日对数RS斜率={slope_raw:.4f}（{'正向' if lit else '负向'}）",
            "source": "yahoo/RSP,SPY",
        }
    except Exception as e:  # noqa: BLE001
        return _absent_chip(key, label_en, label_zh, f"error: {e}")


def _confirm_sector_participation() -> dict:
    """>=8 of 11 GICS sector ETFs close > 50dma AND 50dma rising over 10 sessions.

    Denominator = present ETFs; threshold = ceil(8/11 * n_present).
    """
    key, label_en, label_zh = "sector_participation", "Sector breadth (8-of-11)", "板块广度（11中8）"
    try:
        results = {}
        for ticker in _SECTOR_ETFS:
            try:
                df = store.read("yahoo", ticker)
                if df is None or "close" not in df.columns:
                    continue
                s = df["close"].dropna().sort_index().astype(float)
                s.index = pd.to_datetime(s.index)
                if len(s) < 55:
                    continue
                ma50 = s.rolling(50, min_periods=25).mean()
                above = bool(s.iloc[-1] > ma50.iloc[-1])
                rising = bool(ma50.iloc[-1] > ma50.iloc[-11]) if len(ma50) >= 11 else False
                results[ticker] = above and rising
            except Exception:  # noqa: BLE001
                continue
        n_present = len(results)
        if n_present == 0:
            return _absent_chip(key, label_en, label_zh, "no sector ETF data")
        import math as _math
        threshold = _math.ceil(8 / 11 * n_present)
        n_lit = sum(1 for v in results.values() if v)
        lit = n_lit >= threshold
        since = _iso(date.today()) if lit else None
        detail_en = f"{n_lit}/{n_present} ETFs above rising 50dma (need {threshold})"
        detail_zh = f"{n_lit}/{n_present}个ETF高于上升中50日线（需{threshold}个）"
        return {
            "key": key, "label_en": label_en, "label_zh": label_zh,
            "lit": lit, "fresh": lit,
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

def _load_member_closes(basket_id: str, members: list[dict], as_of_date: pd.Timestamp | None = None) -> pd.DataFrame | None:
    """Load current-member closes from data/baskets/ohlcv/<ticker>.parquet.

    Only members with removed=None or removed > as_of_date are included.
    Falls back to data/breadth/_closes_cache.parquet for S&P members if ohlcv absent.
    """
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
        try:
            from lib import config as _cfg
            p = _cfg.data_dir() / "baskets" / "ohlcv" / f"{ticker}.parquet"
            if p.exists():
                df = pd.read_parquet(p)
                if "close" in df.columns:
                    s = df["close"].dropna().sort_index().astype(float)
                    if not s.empty:
                        closes[ticker] = s
        except Exception:  # noqa: BLE001
            continue
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
) -> dict:
    """Compute the narrow channel: per-basket ignition scores + coarse sector ETFs.

    membership: the 'baskets' dict from membership.json (keyed by basket id).
    spy_series: SPY close series.
    Returns {as_of, items:[...sorted by ignition_score desc]}.
    """
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
            member_closes = _load_member_closes(bid, members)
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

    narrow = compute_narrow(membership_data, spy_series)

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
