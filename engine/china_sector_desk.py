"""China Sector Desk — the live sector board (all 16 dashboard sectors), the free
analogue of the Bloomberg GS China sector basket monitor (GSXAC* family).

For every sector this fuses the three index views from engine.china_sector_index
(authoritative Shenwan L1 deep index · cap-weighted constituent cross-check · live
ETF proxy) with:
  • multi-window performance (1d/5d/20d/YTD) off the Shenwan level
  • relative strength vs CSI 300 (momentum + 200-DMA trend + 252d percentile)
  • a CYCLE-POSITION read on the washout↔euphoria axis the Phase-0 study found stable
    across all four GS sectors (research/CHINA_SECTOR_PATHWAY_PHASE0.md)
  • the last major (≥25% zigzag) turn
  • current Shenwan valuation (PE-TTM / PB / dividend yield)
  • a live ETF data-sym so site/live.js patches the intraday tape.

`snapshot()` is additive/display-only — any failure returns None and the page is
skipped. Heavy per-sector cycle analysis is wrapped so one bad series never sinks the
board.
"""
from __future__ import annotations

import logging

import numpy as np
import pandas as pd

from engine import china_sector_index as csi
from lib import config, store

log = logging.getLogger(__name__)

CSI300 = "510300.SS"


def _pct(a: float, b: float) -> float | None:
    return None if (b is None or b == 0 or pd.isna(b)) else round((a / b - 1.0) * 100.0, 2)


def _win_returns(s: pd.Series) -> dict:
    s = s.dropna()
    if s.empty:
        return {}
    last = float(s.iloc[-1])
    out = {"level": round(last, 2)}
    for k, n in (("chg_1d", 1), ("chg_5d", 5), ("chg_20d", 20), ("chg_60d", 60)):
        out[k] = _pct(last, s.iloc[-1 - n]) if len(s) > n else None
    yr = s.index.max().year
    prev = s[s.index < pd.Timestamp(yr, 1, 1)]
    out["chg_ytd"] = _pct(last, prev.iloc[-1]) if not prev.empty else None
    return out


def _last_pctile(s: pd.Series, lookback: int = 1260) -> float | None:
    """Percentile rank of the last value within its own trailing window (0..1)."""
    s = s.dropna()
    if len(s) < 60:
        return None
    w = s.iloc[-lookback:]
    return round(float((w <= w.iloc[-1]).mean()), 3)


def _rs(sw: pd.Series, bench: pd.Series | None) -> dict | None:
    if bench is None:
        return None
    rs = (sw / bench.reindex(sw.index).ffill()).dropna()
    if len(rs) < 220:
        return None
    ma200 = rs.rolling(200).mean().iloc[-1]
    return {
        "mom_20d": round(float(rs.pct_change(20).iloc[-1] * 100), 2),
        "mom_60d": round(float(rs.pct_change(60).iloc[-1] * 100), 2),
        "above_200d": bool(rs.iloc[-1] > ma200),
        "pctile_252d": round(float(rs.iloc[-252:].rank(pct=True).iloc[-1] * 100), 1),
    }


def _cycle_position(sw: pd.Series) -> dict:
    """Where the sector sits on the washout(0)↔euphoria(100) axis — the Phase-0 stable
    signature: distance-from-trend + drawdown-from-1y-high, each as an own-history
    percentile. Low = capitulation/bottom-like; high = extended/top-like."""
    s = sw.dropna()
    ma200 = s.rolling(200).mean()
    dist = (s / ma200 - 1.0).dropna()
    hi252 = s.rolling(252).max()
    dd = (s / hi252 - 1.0).dropna()
    p_dist = _last_pctile(dist)
    p_dd = _last_pctile(dd)
    legs = [p for p in (p_dist, p_dd) if p is not None]
    score = round(float(np.mean(legs) * 100), 0) if legs else None
    label_en = label_zh = "—"
    if score is not None:
        if score <= 15:
            label_en, label_zh = "Beaten down", "深度超跌"
        elif score <= 35:
            label_en, label_zh = "Recovering", "修复回升"
        elif score <= 65:
            label_en, label_zh = "Mid-cycle", "周期中段"
        elif score <= 85:
            label_en, label_zh = "Stretched", "走高偏贵"
        else:
            label_en, label_zh = "Overheated", "过热"
    return {
        "score": score, "label": label_en, "label_zh": label_zh,
        "dist_200d_pct": round(float(dist.iloc[-1] * 100), 1) if not dist.empty else None,
        "drawdown_pct": round(float(dd.iloc[-1] * 100), 1) if not dd.empty else None,
    }


def _ladder(sw: pd.Series, high: pd.Series | None) -> dict | None:
    """Cycle ladder state via the shared engine.cycles engine (defensive)."""
    try:
        from engine.cycles import analyze
        res = analyze(sw, high=high, kind="equity")
        lad = res.get("ladder") or {}
        if not lad:
            return None
        return {
            "state": lad.get("state"),
            "state_zh": lad.get("state_zh") or lad.get("state"),
            "score": lad.get("score"),
            "bottom_confidence": lad.get("bottom_confidence"),
        }
    except Exception as e:  # noqa: BLE001 — additive
        log.debug("ladder failed: %s", e)
        return None


def _spark(s: pd.Series, points: int = 80, years: float = 3.0) -> list[float] | None:
    """Downsampled, first=100 normalized close for an inline SVG sparkline."""
    s = s.dropna()
    if len(s) < 30:
        return None
    s = s[s.index >= s.index.max() - pd.Timedelta(days=int(365 * years))]
    if len(s) > points:
        step = len(s) // points
        s = s.iloc[::step]
    base = float(s.iloc[0])
    if base == 0:
        return None
    return [round(float(v) / base * 100.0, 2) for v in s.values]


def _valuation_snapshot() -> pd.Series | None:
    df = store.read("china_sectors", "valuation")
    if df is None or df.empty:
        return None
    return df.iloc[-1]


def _desk_sectors() -> list[tuple[str, str, str]]:
    """(etf_ticker, sector_name, shenwan_code) for the 16 dashboard sectors."""
    etfs = config.load()["china"]["yahoo"]["sector_etfs"]
    out = []
    for tk, meta in etfs.items():
        name = meta[0] if isinstance(meta, list) else str(meta)
        sw = csi.SECTOR_SW.get(name)
        if sw:
            out.append((tk, name, sw))
    return out


# zh display names for the dashboard sectors (matches the rest of the China site)
_ZH = {
    "Banks": "银行", "Securities & Brokers": "券商", "Baijiu & Liquor": "白酒",
    "Consumer Staples": "消费", "Healthcare": "医药", "Innovative Drugs": "创新药",
    "Semiconductors": "半导体", "Technology": "科技", "New-Energy Vehicle": "新能源车",
    "Solar & Photovoltaic": "光伏", "Defense & Military": "军工", "Nonferrous Metals": "有色",
    "Coal": "煤炭", "Real Estate": "地产", "Automobiles": "汽车", "Media": "传媒",
}


def snapshot() -> dict | None:
    bench = store.read("china", CSI300)
    bench_close = bench["close"].dropna() if (bench is not None and "close" in bench.columns) else None
    val = _valuation_snapshot()

    sectors = []
    last_dates = []
    for etf, name, swcode in _desk_sectors():
        df = store.read("china_sectors", swcode)
        if df is None or "close" not in df.columns:
            continue
        sw = df["close"].dropna().sort_index()
        if sw.empty:
            continue
        high = df["high"].reindex(sw.index) if "high" in df.columns else None
        last_dates.append(sw.index.max())
        perf = _win_returns(sw)
        rs = _rs(sw, bench_close)
        pos = _cycle_position(sw)
        lad = _ladder(sw, high)
        turns = csi.zigzag_turns(sw, 0.25)
        last_turn = turns[-1] if turns else None
        cap = csi.cap_weighted_basket([name])
        etf_px = store.read("china", etf)
        etf_last = round(float(etf_px["close"].dropna().iloc[-1]), 3) if (
            etf_px is not None and "close" in etf_px.columns and not etf_px["close"].dropna().empty) else None
        valrow = {}
        if val is not None:
            for fld, key in (("pe_ttm", "pe"), ("pb", "pb"), ("div", "div")):
                v = val.get(f"{swcode}_{fld}")
                valrow[key] = round(float(v), 2) if v is not None and pd.notna(v) else None

        sectors.append({
            "key": swcode, "etf": etf, "live_sym": etf, "etf_last": etf_last,
            "name": name, "name_zh": _ZH.get(name, name),
            "sw_code": swcode,
            **perf,
            "rs": rs, "position": pos, "cycle": lad,
            "valuation": valrow or None,
            "last_turn": ({"kind": last_turn["kind"], "date": last_turn["date"].strftime("%Y-%m-%d"),
                           "price": round(last_turn["price"], 1)} if last_turn else None),
            "cap_basket_chg_20d": (_win_returns(cap).get("chg_20d") if cap is not None else None),
            "history_from": sw.index.min().strftime("%Y-%m"),
            "spark": _spark(sw),
        })

    if not sectors:
        return None

    # board summary: leaders/laggards (60d RS), washed-out vs euphoric (position)
    ranked = [s for s in sectors if s.get("rs")]
    ranked.sort(key=lambda s: s["rs"]["mom_60d"], reverse=True)
    by_pos = [s for s in sectors if s["position"]["score"] is not None]
    washed = sorted(by_pos, key=lambda s: s["position"]["score"])[:4]
    eup = sorted(by_pos, key=lambda s: s["position"]["score"], reverse=True)[:4]

    bench_perf = _win_returns(bench_close) if bench_close is not None else {}
    return {
        "as_of": max(last_dates).strftime("%Y-%m-%d") if last_dates else None,
        "benchmark": {"ticker": CSI300, "name": "CSI 300", "name_zh": "沪深300", **bench_perf},
        "sectors": sectors,
        "summary": {
            "leaders": [{"name": s["name"], "name_zh": s["name_zh"], "rs_60d": s["rs"]["mom_60d"]}
                        for s in ranked[:4]],
            "laggards": [{"name": s["name"], "name_zh": s["name_zh"], "rs_60d": s["rs"]["mom_60d"]}
                         for s in ranked[-4:]][::-1],
            "washed_out": [{"name": s["name"], "name_zh": s["name_zh"], "score": s["position"]["score"]}
                           for s in washed],
            "euphoric": [{"name": s["name"], "name_zh": s["name_zh"], "score": s["position"]["score"]}
                         for s in eup],
        },
    }
