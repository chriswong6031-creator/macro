"""China Divergence Radar — management-independent demand/policy signal vs sector price.

LEAF · DISPLAY/CONTEXT-ONLY · KEYLESS · NO VALIDATED EDGE (Phase-0 candidate). The China
build of the narrative-radar idea: for a curated set of (macro/policy/flow signal → the
sector it transmits to) pairs, compare the SIGNAL direction (a free, forward-looking,
management-independent indicator already on disk) against the sector ETF's relative
strength vs CSI 300. A 2×2 kernel flags:

  POSITIVE divergence — support IMPROVING but price LAGGING  (potential catch-up)
  NEGATIVE divergence — support FADING but price LEADING     (potential vulnerability)
  IN LINE (silent)    — signal and price agree               (confirming, no edge)

Winsorised z, a falsifiable per-pair hypothesis seed, and a ledger that accrues on the
fire date (engine/china_radar_ledger.py). Nothing here is scored into an allocation.
See research/CHINA_INTEL_POWERHOUSE.md §4.
"""
from __future__ import annotations

import logging
from datetime import date, datetime, timezone

from lib import store

log = logging.getLogger(__name__)

SCHEMA = "china_radar.v1"
BENCH = "510300.SS"   # CSI 300 ETF
_WINSOR = 3.0


def _winz(x: float) -> float:
    return max(-_WINSOR, min(_WINSOR, x))


# --------------------------------------------------------------------------- #
# price relative strength: sector ETF 63d return minus benchmark, + its z
# --------------------------------------------------------------------------- #
def _price_rs(etf: str, lookback: int = 63):
    try:
        import numpy as np
        import pandas as pd
        a = store.read("china", etf)
        b = store.read("china", BENCH)
        if a is None or b is None or "close" not in a.columns or "close" not in b.columns:
            return None, None
        ca, cb = a["close"].dropna(), b["close"].dropna()
        rel = (ca / cb.reindex(ca.index).ffill()).dropna()
        if len(rel) < lookback + 60:
            return None, None
        roll = rel.pct_change(lookback).dropna()    # rolling 63d relative return
        cur = float(roll.iloc[-1])
        hist = roll.tail(504)
        mu, sd = float(hist.mean()), float(hist.std(ddof=0))
        z = _winz((cur - mu) / sd) if sd > 1e-9 else 0.0
        return round(cur * 100, 2), round(z, 2)
    except Exception as e:  # noqa: BLE001
        log.debug("china_radar price_rs %s failed (%s)", etf, e)
        return None, None


# --------------------------------------------------------------------------- #
# signal-A computations — each returns {value, dir(+1/-1/0), strength(0..1), detail}
# All are free, forward-looking, management-INDEPENDENT macro/policy/flow indicators.
# --------------------------------------------------------------------------- #
def _sig_credit_impulse():
    try:
        import pandas as pd
        df = store.read("china_credit", "tsf")
        if df is None or "tsf_total" not in df.columns:
            return None
        s = pd.to_numeric(df["tsf_total"], errors="coerce").dropna()
        roll = s.rolling(12).sum().dropna()          # 12m TSF sum
        if len(roll) < 18:
            return None
        impulse = roll.pct_change(6).dropna()        # 6m change of the 12m sum (the impulse)
        cur = float(impulse.iloc[-1])
        sd = float(impulse.tail(36).std(ddof=0))
        strength = min(1.0, abs(cur) / (2 * sd)) if sd > 1e-9 else 0.4
        return {"value": round(cur * 100, 1), "dir": 1 if cur > 0 else (-1 if cur < 0 else 0),
                "strength": round(strength, 2),
                "detail_en": f"TSF impulse {cur*100:+.1f}% (6m chg of 12m sum)",
                "detail_zh": f"社融脉冲 {cur*100:+.1f}%（12月滚动和的6月变化）"}
    except Exception:  # noqa: BLE001
        return None


def _sig_pboc_easing():
    try:
        import pandas as pd
        lpr = store.read("china_macro", "lpr_rate")
        rrr = store.read("china_macro", "rrr")
        lpr_chg = 0.0
        if lpr is not None and "lpr_1y" in lpr.columns:
            s = lpr["lpr_1y"].dropna()
            cutoff = s.index.max() - pd.Timedelta(days=365)
            past = s[s.index <= cutoff]
            if not past.empty:
                lpr_chg = float(s.iloc[-1] - past.iloc[-1])
        rrr_chg = 0.0
        if rrr is not None and "rrr_change" in rrr.columns:
            r = rrr["rrr_change"].dropna()
            cutoff = r.index.max() - pd.Timedelta(days=365)
            rrr_chg = float(r[r.index >= cutoff].sum())
        easing = -(lpr_chg * 100) - (rrr_chg * 20)   # bp + RRR-pp scaled; >0 = easing
        strength = min(1.0, abs(easing) / 40.0)
        return {"value": round(easing, 1), "dir": 1 if easing > 1 else (-1 if easing < -1 else 0),
                "strength": round(strength, 2),
                "detail_en": f"12m easing score {easing:+.0f} (LPR {lpr_chg*100:+.0f}bp, RRR {rrr_chg:+.2f}pp)",
                "detail_zh": f"12月宽松分 {easing:+.0f}（LPR {lpr_chg*100:+.0f}基点，准备金 {rrr_chg:+.2f}pp）"}
    except Exception:  # noqa: BLE001
        return None


def _sig_pmi():
    try:
        import pandas as pd
        df = store.read("china_macro", "pmi")
        if df is None or "pmi_mfg" not in df.columns:
            return None
        s = pd.to_numeric(df["pmi_mfg"], errors="coerce").dropna()
        if len(s) < 6:
            return None
        cur = float(s.iloc[-1])
        chg3 = float(s.iloc[-1] - s.iloc[-4]) if len(s) > 4 else 0.0
        above = cur - 50.0
        strength = min(1.0, (abs(above) + abs(chg3)) / 2.0)
        d = 1 if (above > 0 and chg3 >= 0) else (-1 if (above < 0 and chg3 <= 0) else (1 if chg3 > 0 else -1))
        return {"value": round(cur, 1), "dir": d, "strength": round(strength, 2),
                "detail_en": f"Mfg PMI {cur:.1f} ({chg3:+.1f} 3m)",
                "detail_zh": f"制造业PMI {cur:.1f}（3月{chg3:+.1f}）"}
    except Exception:  # noqa: BLE001
        return None


def _sig_ppi():
    try:
        import pandas as pd
        df = store.read("china_macro", "ppi")
        if df is None or "ppi_yoy" not in df.columns:
            return None
        s = pd.to_numeric(df["ppi_yoy"], errors="coerce").dropna()
        if len(s) < 6:
            return None
        # data-quality guard: China PPI YoY is slow-moving. A >2.5pp single-month jump (parse
        # explosion) OR a >5pp swing over the trailing 6 months (vintage/base-effect artifact —
        # the implausible -1.9→+3.9 reflation the audit flagged) is data-suspect → skip, don't fire.
        if abs(float(s.iloc[-1]) - float(s.iloc[-2])) > 2.5:
            return None
        win6 = s.tail(6)
        if float(win6.max() - win6.min()) > 5.0:
            return None
        cur = float(s.iloc[-1])
        chg3 = float(s.iloc[-1] - s.iloc[-4])
        strength = min(1.0, abs(chg3) / 2.0)
        return {"value": round(cur, 1), "dir": 1 if chg3 > 0 else (-1 if chg3 < 0 else 0),
                "strength": round(strength, 2),
                "detail_en": f"PPI YoY {cur:+.1f}% ({chg3:+.1f} 3m, reflation tilt)",
                "detail_zh": f"PPI同比 {cur:+.1f}%（3月{chg3:+.1f}，再通胀倾向）"}
    except Exception:  # noqa: BLE001
        return None


def _sig_southbound():
    try:
        import pandas as pd
        df = store.read("china_connect", "southbound")
        if df is None or "net" not in df.columns:
            return None
        s = pd.to_numeric(df["net"], errors="coerce").dropna()
        if len(s) < 80:
            return None
        flow20 = s.rolling(20).sum().dropna()
        cur = float(flow20.iloc[-1])
        mu, sd = float(flow20.tail(252).mean()), float(flow20.tail(252).std(ddof=0))
        z = _winz((cur - mu) / sd) if sd > 1e-9 else 0.0
        return {"value": round(cur / 1e8, 1) if abs(cur) > 1e6 else round(cur, 1),
                "dir": 1 if z > 0.3 else (-1 if z < -0.3 else 0),
                "strength": round(min(1.0, abs(z) / 2.0), 2),
                "detail_en": f"Southbound 20d flow z {z:+.2f}",
                "detail_zh": f"南向20日净流入 z {z:+.2f}"}
    except Exception:  # noqa: BLE001
        return None


def _sector_flow_boards():
    """{board_name: net_amount_rate} for 东财 INDUSTRY boards (GATED Tushare moneyflow_ind_dc snapshot).
    {} when the token / cache is absent. Sector net-flow rate (% of turnover) for the latest day."""
    out: dict = {}
    try:
        import pandas as pd
        from lib import config
        p = config.data_dir() / "tushare" / "moneyflow_sector.parquet"
        if not p.exists():
            return out
        df = pd.read_parquet(p)
        ind = df[df.get("content_type") == "行业"] if "content_type" in df.columns else df
        for _, r in ind.iterrows():
            nm = str(r.get("name") or "")
            v = r.get("net_amount_rate")
            if nm and v is not None and v == v:
                out[nm] = float(v)
    except Exception as e:  # noqa: BLE001
        log.debug("china_radar sector-flow boards failed (%s)", e)
    return out


def _sector_flow_signal(board: str, boards: dict):
    """signal-A from a sector's own 东财 net-flow rate (daily). Deadbanded so a small move stays
    silent. None when the board is absent."""
    rate = boards.get(board)
    if rate is None:
        return None
    d = 1 if rate > 1.0 else (-1 if rate < -1.0 else 0)
    return {"value": round(rate, 2), "dir": d, "strength": round(min(1.0, abs(rate) / 3.0), 2),
            "detail_en": f"Sector net-flow {rate:+.1f}% (东财 board, daily)",
            "detail_zh": f"板块净流入 {rate:+.1f}%（东财行业板块，当日）"}


# Sector ETF → 东财 industry board (exact name) for the sector-flow radar pairs. Reuses the radar's
# existing sector ETFs so the price-RS leg is identical.
_SECTOR_FLOW_MAP = [
    ("512800.SS", "Banks", "银行", "银行"),
    ("512200.SS", "Real estate", "房地产", "房地产"),
    ("512880.SS", "Brokers", "券商", "证券Ⅱ"),
    ("512400.SS", "Nonferrous metals", "有色金属", "有色金属"),
    ("515030.SS", "New-energy vehicle", "新能源车", "锂电池"),
    ("512760.SS", "Semiconductors", "半导体", "半导体"),
    ("512660.SS", "Defense", "国防军工", "国防军工"),
    ("515220.SS", "Coal", "煤炭", "煤炭"),
]
_SECTOR_FLOW_THESIS = ("Sector smart-money net-flow tends to lead the sector's price when it "
                       "diverges from current relative strength.")


# (signal_key, signal_fn, signal_en, signal_zh, [(etf, sector_en, sector_zh)...], thesis)
_PAIRS = [
    ("credit_impulse", _sig_credit_impulse, "Credit impulse (TSF)", "信用脉冲(社融)",
     [("512800.SS", "Banks", "银行"), ("512200.SS", "Real estate", "房地产")],
     "Credit impulse leads cyclicals/financials by 2-4 quarters."),
    ("pboc_easing", _sig_pboc_easing, "PBoC easing", "央行宽松",
     [("512880.SS", "Brokers", "券商"), ("512200.SS", "Real estate", "房地产")],
     "Easing (RRR/LPR cuts) lifts rate-sensitive brokers + property."),
    ("pmi", _sig_pmi, "Mfg PMI", "制造业PMI",
     [("512400.SS", "Nonferrous metals", "有色金属"), ("515030.SS", "New-energy vehicle", "新能源车")],
     "Manufacturing expansion supports industrial cyclicals."),
    ("ppi", _sig_ppi, "PPI reflation", "PPI再通胀",
     [("512400.SS", "Nonferrous metals", "有色金属"), ("515220.SS", "Coal", "煤炭")],
     "PPI inflecting up reflates upstream-resource margins."),
    ("southbound", _sig_southbound, "Southbound flow", "南向资金",
     [("512760.SS", "Semiconductors", "半导体"), ("512660.SS", "Defense", "国防军工")],
     "Sustained southbound inflow tends to lead the names it chases."),
]


def _divergence(sig: dict, rs_pct, rs_z):
    """2×2 verdict from signal direction vs price relative strength. PURE.

    price direction is taken from rs_z (the sector's OWN-history-normalized relative return)
    with a deadband, NOT the raw 63d rel return — otherwise in a broad-underperformance regime
    every sector reads pdir=-1 and the radar is structurally one-sided (the 6/6-positive bug)."""
    if sig is None or sig.get("dir", 0) == 0 or rs_z is None:
        return "in_line", 0.0
    sdir = sig["dir"]
    z = rs_z or 0.0
    pdir = 1 if z > 0.3 else (-1 if z < -0.3 else 0)   # deadband → mild moves stay silent
    if pdir == 0:
        return "in_line", 0.0
    strength = round(sig.get("strength", 0.0) * min(1.0, abs(z) / 2.0), 3)
    if sdir > 0 and pdir < 0:
        return "positive", strength      # support improving, price lagging
    if sdir < 0 and pdir > 0:
        return "negative", strength      # support fading, price extended
    return "in_line", strength


def _ledger_reliability():
    """(by_pair, by_signal) → {key: {n_resolved, hits, hit_rate}} from the falsification
    ledger. Both {} when nothing has matured (n_resolved 0). Lazy + degrade-to-empty."""
    by_pair, by_signal = {}, {}
    try:
        from engine import china_radar_ledger as rl
        tr = rl.track_record()
        for r in (tr or {}).get("rows", []):
            if r.get("status") not in ("hit", "miss"):
                continue
            hit = 1 if r["status"] == "hit" else 0
            for d, k in ((by_pair, r.get("pair")), (by_signal, r.get("signal_key"))):
                if not k:
                    continue
                cur = d.setdefault(k, {"n_resolved": 0, "hits": 0})
                cur["n_resolved"] += 1
                cur["hits"] += hit
        for d in (by_pair, by_signal):
            for v in d.values():
                v["hit_rate"] = round(v["hits"] / v["n_resolved"], 2) if v["n_resolved"] else None
    except Exception as e:  # noqa: BLE001
        log.debug("china_radar reliability unavailable (%s)", e)
    return by_pair, by_signal


def _candidates(etf, sign, conv_map, n=3):
    """Per-divergence candidate names — the basket members the divergence implicates, joined to
    alt-data convergence (top by accumulation for positive, bottom for negative). Bilingual why."""
    try:
        from engine import china_basket_spine as sp
        bids = sp.etf_to_basket().get(etf, [])
        members = []
        for b in bids:
            members += sp.basket_members(b)
        members = list(dict.fromkeys(members))
        cand = [(t, conv_map[t]) for t in members if t in conv_map]
        if not cand:
            return []
        cand.sort(key=lambda x: x[1]["convergence"], reverse=(sign == "positive"))
        out = []
        for t, info in cand[:n]:
            acc = info.get("side") == "accumulate"
            out.append({
                "ticker": t, "name": info.get("name", t),
                "convergence": info.get("convergence"),
                "why_en": f"{'leads' if sign == 'positive' else 'lags'} cohort · alt-data {info.get('side','')}",
                "why_zh": f"{'领先' if sign == 'positive' else '落后'}同业 · 另类数据{'吸筹' if acc else '派发'}",
            })
        return out
    except Exception:  # noqa: BLE001
        return []


def _build_row(cv, key, sen, szh, etf, sec_en, sec_zh, sig, thesis,
               by_pair, by_signal, conv_map) -> dict:
    """One radar row: signal-A direction vs the sector ETF's price RS → divergence verdict,
    conviction-scored (strength × ledger reliability) with falsifiable hypothesis + candidates.
    Shared by the macro/policy/flow pairs AND the per-sector sector-flow pairs. PURE-ish (reads
    price + ledger + convergence)."""
    rs_pct, rs_z = _price_rs(etf)
    sign, strength = _divergence(sig, rs_pct, rs_z)
    pair = f"{key}->{etf}"
    if sign == "positive":
        hyp_en = f"If {sen} is leading, {sec_en} should outperform CSI 300 over ~3 months."
        hyp_zh = f"若{szh}领先，{sec_zh}未来约3个月应跑赢沪深300。"
    elif sign == "negative":
        hyp_en = f"If {sen} is fading, {sec_en}'s lead over CSI 300 should fade over ~3 months."
        hyp_zh = f"若{szh}转弱，{sec_zh}相对沪深300的领先应在约3个月内消退。"
    else:
        hyp_en = hyp_zh = ""
    # reliability: per-pair, fall back to per-signal, else unproven
    rel = by_pair.get(pair) or by_signal.get(key) or {}
    n_res = rel.get("n_resolved", 0)
    hr = rel.get("hit_rate")
    basis = ("pair" if pair in by_pair else ("signal_key" if key in by_signal else "unproven"))
    if n_res >= 3 and hr is not None:
        # proven-good rewarded up to 1.5×; proven-BAD (hr→0) collapses toward 0,
        # so a demonstrably-falsified signal drops out of Moderate+ (not floored at 0.5×)
        rel_factor = max(0.15, min(1.5, 1.5 * hr))
    else:
        rel_factor = 1.0
        basis = "unproven"
    conviction100 = cv.to_100(strength * rel_factor) if sign != "in_line" else 0
    return {
        "pair": pair, "signal_key": key,
        "signal_en": sen, "signal_zh": szh,
        "sector": sec_en, "sector_etf": etf, "sector_en": sec_en, "sector_zh": sec_zh,
        "sign": sign, "strength": strength, "conviction100": conviction100,
        "signal_value": sig.get("value"), "signal_dir": sig.get("dir"),
        "signal_detail_en": sig.get("detail_en"), "signal_detail_zh": sig.get("detail_zh"),
        "price_rs": rs_pct, "price_rs_z": rs_z,
        "reliability": {"hit_rate": hr, "n_resolved": int(n_res), "basis": basis},
        "candidates": _candidates(etf, sign, conv_map) if sign != "in_line" else [],
        "thesis": thesis, "hypothesis_en": hyp_en, "hypothesis_zh": hyp_zh,
    }


def scan(asof: date | str | None = None) -> dict | None:
    """Run all radar pairs → divergence verdicts + falsifiable hypotheses, conviction-scored
    (strength × ledger reliability) with per-name candidates. Never raises."""
    try:
        from engine import china_conviction as cv
        by_pair, by_signal = _ledger_reliability()
        try:
            from engine import china_altdata
            conv_map = china_altdata.convergence_map()
        except Exception:  # noqa: BLE001
            conv_map = {}
        rows: list[dict] = []
        for key, fn, sen, szh, targets, thesis in _PAIRS:
            sig = fn()
            if sig is None:
                continue
            for etf, sec_en, sec_zh in targets:
                rows.append(_build_row(cv, key, sen, szh, etf, sec_en, sec_zh, sig, thesis,
                                       by_pair, by_signal, conv_map))
        # sector-flow pairs (GATED Tushare): each sector's OWN 东财 net-flow vs its price RS.
        # Absent without a token / cache → simply no sector-flow rows.
        boards = _sector_flow_boards()
        for etf, sec_en, sec_zh, board in _SECTOR_FLOW_MAP:
            sig = _sector_flow_signal(board, boards)
            if sig is None:
                continue
            rows.append(_build_row(cv, "sector_flow", "Sector net-flow", "板块净流入",
                                   etf, sec_en, sec_zh, sig, _SECTOR_FLOW_THESIS,
                                   by_pair, by_signal, conv_map))
        if not rows:
            return None
        active = [r for r in rows if r["sign"] != "in_line"]
        active.sort(key=lambda r: (r["conviction100"], r["strength"]), reverse=True)
        return {
            "schema": SCHEMA, "is_context_only": True,
            "asof": str(asof) if asof else str(date.today()),
            "built": datetime.now(timezone.utc).isoformat(),
            "divergences": active,
            "in_line": [r for r in rows if r["sign"] == "in_line"],
            "n_active": len(active), "n_pairs": len(rows),
            "disclaimer_en": "Context only — a divergence is a falsifiable hypothesis, not a trade. "
                             "No validated edge; the ledger tracks whether these calls hold.",
            "disclaimer_zh": "仅作背景——背离是可证伪的假设，而非交易。无已验证优势；台账追踪这些判断是否成立。",
        }
    except Exception as e:  # noqa: BLE001 — additive, never fatal
        log.error("china_radar.scan failed (%s)", e)
        return None
