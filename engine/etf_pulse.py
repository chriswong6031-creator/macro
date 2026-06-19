"""ETF Pulse — style / risk / sector rotation context strip (DISPLAY-ONLY).

A compact cross-asset "what is the tape rotating toward" read to sit beside the Theme
Rotation Desk on the thematic page. It is the rotation context a theme allocator wants
at a glance — is the market paying for growth or value, small or large, risk-on or
risk-off, and which sectors lead — so a per-theme lean can be read against the prevailing
regime.

Three legs, all trailing ratio returns off the FREE caches (zero new data):

  STYLE   pairwise ratio returns over 1/5/20/60d:
            IWM/SPY  small vs large        RSP/SPY  equal- vs cap-weight (breadth)
            QQQ/SPY  growth-tilt vs broad  IWF/IWD  growth vs value
            EEM/SPY  EM vs US
  RISK    HYG/TLT credit vs duration · GC=F/SPY gold vs equities · DX-Y.NYB dollar ·
          _VIX vol — folded into a single coarse RORO tilt.
  SECTOR  the 11 GICS sector ETFs, RANKED — reuses the regime engine's already-computed
          relative strength (data/regime/latest.json["sector_rs"]; engine.sectors.rs_table),
          so the methodology matches the rest of the site exactly.

HONEST BY CONSTRUCTION: descriptive ratio momentum, never scored, no forward claim — a
context strip, like the Flow Lens. Additive: any shortfall returns None and the caller
skips the panel.
"""
from __future__ import annotations

import json
import logging

import numpy as np
import pandas as pd

from lib import config, store

log = logging.getLogger(__name__)

# ratio-return horizons (trading days)
_HORIZONS = (1, 5, 20, 60)

# style rotation pairs: (numerator, denominator, en, zh, up_label_en, up_label_zh)
_STYLE_PAIRS = [
    ("IWM", "SPY", "Small vs Large", "小盘 vs 大盘", "small-cap leading", "小盘领先"),
    ("RSP", "SPY", "Equal vs Cap-weight", "等权 vs 市值加权", "breadth broadening", "广度扩散"),
    ("QQQ", "SPY", "Growth-tilt vs Broad", "成长 vs 大盘", "growth leading", "成长领先"),
    ("IWF", "IWD", "Growth vs Value", "成长 vs 价值", "growth leading", "成长领先"),
    ("EEM", "SPY", "EM vs US", "新兴 vs 美国", "EM leading", "新兴领先"),
]

# risk pulse legs: (numerator, denominator|None, en, zh, "risk_on_when" direction)
#   direction = +1: numerator OUTPERFORMING / RISING is RISK-ON
#   direction = -1: numerator OUTPERFORMING / RISING is RISK-OFF
_RISK_LEGS = [
    ("HYG", "TLT", "Credit vs Duration", "信用 vs 久期", +1),
    ("GC=F", "SPY", "Gold vs Equities", "黄金 vs 股票", -1),
    ("DX-Y.NYB", None, "US Dollar", "美元", -1),
    ("_VIX", None, "Volatility", "波动率", -1),
]

# GICS sector ETFs (the rotation board) + bilingual labels.
_SECTOR_ETFS = {
    "XLK": ("Technology", "科技"), "XLF": ("Financials", "金融"),
    "XLE": ("Energy", "能源"), "XLV": ("Health Care", "医疗"),
    "XLY": ("Cons. Discretionary", "非必需消费"), "XLP": ("Cons. Staples", "必需消费"),
    "XLI": ("Industrials", "工业"), "XLU": ("Utilities", "公用事业"),
    "XLB": ("Materials", "原材料"), "XLC": ("Comm. Services", "通信服务"),
    "XLRE": ("Real Estate", "房地产"),
}


def _r(x, n: int = 2):
    if x is None or (isinstance(x, float) and not np.isfinite(x)):
        return None
    return round(float(x), n)


def _close(sym: str) -> pd.Series | None:
    """Daily close for a symbol, trying the yahoo cache then the hk cache (EEM lives there)."""
    for grp in ("yahoo", "hk"):
        df = store.read(grp, sym)
        if df is not None and "close" in df.columns and not df["close"].dropna().empty:
            return df["close"].dropna()
    return None


def _ratio_perf(num: pd.Series, den: pd.Series | None) -> dict | None:
    """level + 1/5/20/60d % change of num (or num/den ratio). None if too little history."""
    if num is None:
        return None
    if den is not None:
        a, b = num.align(den, join="inner")
        s = (a / b).replace([np.inf, -np.inf], np.nan).dropna()
    else:
        s = num.dropna()
    if len(s) < 25:
        return None
    out = {"level": _r(s.iloc[-1], 4)}
    for h in _HORIZONS:
        out[f"chg_{h}d"] = (_r((s.iloc[-1] / s.iloc[-1 - h] - 1.0) * 100) if len(s) > h else None)
    return out


def _style_leg() -> list[dict]:
    rows = []
    for num, den, en, zh, up_en, up_zh in _STYLE_PAIRS:
        perf = _ratio_perf(_close(num), _close(den) if den else None)
        if perf is None:
            continue
        c20 = perf.get("chg_20d")
        tilt = (up_en if (c20 or 0) > 0 else "—")
        rows.append({
            "pair": f"{num}/{den}", "label_en": en, "label_zh": zh,
            "lead_en": (up_en if (c20 or 0) > 0 else _flip_en(en)),
            "lead_zh": (up_zh if (c20 or 0) > 0 else _flip_zh(zh)),
            "tilt": (1 if (c20 or 0) > 0 else -1 if (c20 or 0) < 0 else 0),
            **perf,
        })
    return rows


def _flip_en(label: str) -> str:
    # "Small vs Large" -> "large-cap leading"; generic fallback to the 2nd term
    parts = label.split(" vs ")
    return f"{parts[-1].lower()} leading" if len(parts) == 2 else "—"


def _flip_zh(label: str) -> str:
    parts = label.split(" vs ")
    return f"{parts[-1]}领先" if len(parts) == 2 else "—"


def _risk_leg() -> dict | None:
    legs, score, n = [], 0.0, 0
    for num, den, en, zh, direction in _RISK_LEGS:
        perf = _ratio_perf(_close(num), _close(den) if den else None)
        if perf is None:
            continue
        c20 = perf.get("chg_20d")
        # contribution to the RORO tilt: sign of 20d move × the leg's risk-on direction
        contrib = None
        if c20 is not None:
            contrib = float(np.tanh(c20 / 5.0)) * direction
            score += contrib
            n += 1
        legs.append({
            "pair": (f"{num}/{den}" if den else num), "label_en": en, "label_zh": zh,
            "direction": direction, "contrib": _r(contrib), **perf,
        })
    if not legs:
        return None
    tilt = (score / n) if n else 0.0
    label_en, label_zh = ("RISK-ON", "风险偏好") if tilt > 0.15 else \
        ("RISK-OFF", "风险规避") if tilt < -0.15 else ("NEUTRAL", "中性")
    return {"legs": legs, "tilt": _r(tilt, 3), "label_en": label_en, "label_zh": label_zh}


def _sector_leg() -> dict | None:
    """Reuse the regime engine's sector RS (already computed, same as the rest of the site)."""
    p = config.data_dir() / "regime" / "latest.json"
    if not p.exists():
        return None
    try:
        reg = json.loads(p.read_text())
    except Exception:  # noqa: BLE001
        return None
    rows = []
    for r in (reg.get("sector_rs") or []):
        t = r.get("ticker")
        if t not in _SECTOR_ETFS:
            continue
        en, zh = _SECTOR_ETFS[t]
        rows.append({
            "ticker": t, "label_en": en, "label_zh": zh,
            "mom_20d": _r(r.get("mom_20d_pct")), "mom_60d": _r(r.get("mom_60d_pct")),
            "pctile_252d": _r(r.get("pctile_252d"), 1),
            "above_200d": bool(r.get("above_200d_trend")),
        })
    if not rows:
        return None
    rows.sort(key=lambda x: (x["mom_60d"] is None, -(x["mom_60d"] or -1e9)))
    for k, x in enumerate(rows, 1):
        x["rank"] = k
    return {"as_of": reg.get("date"), "rows": rows,
            "leaders": [x["ticker"] for x in rows[:3]],
            "laggards": [x["ticker"] for x in rows[-3:]]}


def compute_etf_pulse() -> dict | None:
    """Style + risk + sector rotation context. None if nothing computed."""
    style = _style_leg()
    risk = _risk_leg()
    sector = _sector_leg()
    if not style and not risk and not sector:
        return None
    spy = _close("SPY")
    as_of = (spy.index.max().strftime("%Y-%m-%d") if spy is not None else
             (sector or {}).get("as_of"))
    return {
        "as_of": as_of,
        "disclaimer_en": ("Display-only rotation context — trailing ratio momentum across "
                          "style, risk and sector ETFs. Descriptive, never a buy list."),
        "disclaimer_zh": ("仅供展示的轮动背景 — 风格/风险/行业 ETF 的滞后比值动量。"
                          "描述性，非买入清单。"),
        "horizons": list(_HORIZONS),
        "style": style, "risk": risk, "sector": sector,
    }
