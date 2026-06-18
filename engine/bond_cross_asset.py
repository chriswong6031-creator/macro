"""Bonds → Everything — the quantitative cross-asset transmission map.

ADDITIVE / leaf module, DISPLAY-ONLY. Bonds are the discount rate, the growth
signal and the risk gate for every other market; this leaf MEASURES, from the data
already in the frame, how each downstream asset moves with the cleanest bond driver,
and reads the CURRENT headwind / tailwind from the live driver impulse.

It is bond-DRIVER-centric and so complements (does not duplicate) the rate+inflation
STATE-centric transmission page (engine.rate_inflation_transmission / transmission.html):
that page runs split-half forward-IC chains and scenarios across 14 assets; this one
answers "what are bonds doing TO each market right now?" and adds the channels that
page is thin on — credit (HY OAS) as the equity canary, the rate-DIFFERENTIAL → USD,
and MOVE as the cross-asset risk gate.

For each asset it fits a simple contemporaneous OLS of the asset's WEEKLY return on the
WEEKLY change in its primary bond driver, over the full overlapping sample, and reports:
  • the measured beta (per +10bp for a rate driver), with the correlation as a confidence
  • the current driver impulse (recent change / level)
  • the resulting headwind / tailwind = sign(beta) × current impulse

Honest by construction: these betas are CONTEMPORANEOUS (descriptive co-movement, not a
forward forecast) and regime-dependent — the panel is a transmission MAP, never scored,
never an MRS leg. The measured numbers refresh every build so the copy can never drift
from the data.
"""
from __future__ import annotations

import logging

import numpy as np
import pandas as pd

from lib import store

log = logging.getLogger(__name__)

_TY = 252


# --- driver / asset access ----------------------------------------------------
def _f(f: pd.DataFrame, name: str) -> pd.Series | None:
    if name in f.columns and not f[name].isna().all():
        return f[name].dropna()
    return None


def _yahoo(ticker: str) -> pd.Series | None:
    df = store.read("yahoo", ticker)
    if df is None or df.empty or "close" not in df.columns:
        return None
    return df["close"].astype(float).dropna()


def _beta(asset_px: pd.Series | None, driver: pd.Series | None) -> dict | None:
    """Contemporaneous OLS of WEEKLY asset return on WEEKLY driver CHANGE.
    Returns {beta (return per +1.0 unit of driver), corr, n}. Non-overlapping weekly
    sampling avoids the autocorrelation of rolling windows."""
    if asset_px is None or driver is None:
        return None
    a = asset_px.resample("W-FRI").last()
    d = driver.resample("W-FRI").last()
    r = a.pct_change()
    dd = d.diff()
    df = pd.concat([r, dd], axis=1, keys=["r", "d"]).dropna()
    if len(df) < 104:   # need ~2y of weekly obs
        return None
    var = float(df["d"].var())
    if not var or not np.isfinite(var):
        return None
    beta = float(df["r"].cov(df["d"]) / var)
    corr = float(df["r"].corr(df["d"]))
    return {"beta": beta, "corr": corr, "n": int(len(df))}


def _chg(s: pd.Series | None, n: int) -> float | None:
    if s is None:
        return None
    s = s.dropna()
    if len(s) <= n:
        return None
    return float(s.iloc[-1] - s.iloc[-1 - n])


def _r(v, nd=2):
    return None if v is None or not np.isfinite(v) else round(float(v), nd)


# --- the driver registry (bond-side level series, change drives assets) -------
# key -> (frame-col, display unit, "+10bp"-scale for rate drivers else 1.0, label)
def _drivers(f: pd.DataFrame) -> dict:
    real = _f(f, "us10y_real")
    nom = _f(f, "us10y")
    slope = _f(f, "spread_10y3m")
    hy = _f(f, "hy_oas")
    be = _f(f, "breakeven_10y")
    move = _f(f, "move")
    return {
        "real_10y": {"s": real, "rate": True, "en": "real 10y", "zh": "10年实际利率"},
        "nom_10y": {"s": nom, "rate": True, "en": "10y yield", "zh": "10年名义利率"},
        "slope": {"s": slope, "rate": True, "en": "curve slope (10y−3m)", "zh": "曲线斜率"},
        "hy_oas": {"s": hy, "rate": True, "en": "HY credit spread", "zh": "高收益利差"},
        "breakeven": {"s": be, "rate": True, "en": "10y breakeven", "zh": "10年盈亏平衡通胀"},
        "move": {"s": move, "rate": False, "en": "MOVE (rates vol)", "zh": "MOVE利率波动"},
    }


# asset roster -> primary bond driver + the economic story. icon for the UI.
_ASSETS = [
    {"key": "spx", "src": ("f", "SPY"), "icon": "📈", "en": "S&P 500", "zh": "标普500",
     "driver": "hy_oas", "story_en": "Credit (HY OAS) is the canary that leads equity drawdowns; widening = headwind.",
     "story_zh": "信用利差是领先股票回撤的预警；走阔=逆风。"},
    {"key": "ndx", "src": ("f", "QQQ"), "icon": "💻", "en": "Nasdaq 100", "zh": "纳斯达克100",
     "driver": "real_10y", "story_en": "Long-duration growth de-rates as the real discount rate rises.",
     "story_zh": "实际贴现率上升时，长久期成长股估值下移。"},
    {"key": "fins", "src": ("y", "XLF"), "icon": "🏦", "en": "Financials (XLF)", "zh": "金融（XLF）",
     "driver": "slope", "story_en": "Banks earn the curve — a steeper slope lifts net interest margins.",
     "story_zh": "银行赚取曲线利差——曲线越陡，净息差越高。"},
    {"key": "reit", "src": ("y", "XLRE"), "icon": "🏢", "en": "REITs (XLRE)", "zh": "房地产（XLRE）",
     "driver": "real_10y", "story_en": "Rate-sensitive long-duration cash flows; rising real yields are a headwind.",
     "story_zh": "对利率敏感的长久期现金流；实际利率上行为逆风。"},
    {"key": "utes", "src": ("f", "XLU"), "icon": "💡", "en": "Utilities (XLU)", "zh": "公用事业（XLU）",
     "driver": "nom_10y", "story_en": "A bond proxy — high yield, rate-sensitive; rising yields compete it down.",
     "story_zh": "类债券——高股息、对利率敏感；利率上行形成竞争压力。"},
    {"key": "iwm", "src": ("f", "IWM"), "icon": "🔹", "en": "Small caps (IWM)", "zh": "小盘股（IWM）",
     "driver": "hy_oas", "story_en": "Floating-rate, credit-dependent balance sheets — credit stress hits hardest.",
     "story_zh": "浮动利率、依赖信用的资产负债表——信用压力冲击最大。"},
    {"key": "usd", "src": ("f", "dxy"), "icon": "💵", "en": "US Dollar (DXY)", "zh": "美元（DXY）",
     "driver": "real_10y", "story_en": "Rate-differential / real-carry channel — a higher US real yield pulls the dollar up.",
     "story_zh": "利差/实际套息通道——美国实际利率走高拉升美元。"},
    {"key": "gold", "src": ("f", "gold"), "icon": "🥇", "en": "Gold", "zh": "黄金",
     "driver": "real_10y", "story_en": "The real 10y is gold's opportunity cost — the cleanest inverse in macro.",
     "story_zh": "10年实际利率是黄金的机会成本——宏观中最干净的反向关系。"},
    {"key": "copper", "src": ("f", "copper"), "icon": "🔩", "en": "Copper", "zh": "铜",
     "driver": "slope", "story_en": "Dr. Copper tracks the growth impulse the curve slope proxies.",
     "story_zh": "“铜博士”跟随曲线斜率所代表的增长动能。"},
    {"key": "oil", "src": ("f", "oil"), "icon": "🛢", "en": "Crude oil", "zh": "原油",
     "driver": "breakeven", "story_en": "Breakevens and energy feed each other; growth + inflation impulse.",
     "story_zh": "盈亏平衡通胀与能源相互驱动；增长+通胀动能。"},
    {"key": "btc", "src": ("y", "BTC-USD"), "icon": "₿", "en": "Bitcoin", "zh": "比特币",
     "driver": "real_10y", "story_en": "A long-duration liquidity asset — falling real yields + calm rates-vol are a tailwind.",
     "story_zh": "长久期流动性资产——实际利率下行+利率波动平静为顺风。"},
]


def _impulse(drv: dict, f: pd.DataFrame) -> dict:
    """Current driver impulse: rate drivers use the 63-bday change (bp); MOVE its level z."""
    s = drv["s"]
    if s is None:
        return {"val": None, "disp_en": "—", "disp_zh": "—"}
    if drv["rate"]:
        ch = _chg(s, 63)
        bp = None if ch is None else ch * 100.0
        word = ("rising" if (bp or 0) > 5 else "falling" if (bp or 0) < -5 else "flat")
        word_zh = {"rising": "上行", "falling": "下行", "flat": "走平"}[word]
        return {"val": bp, "word": word,
                "disp_en": f"{bp:+.0f}bp/3m" if bp is not None else "—",
                "disp_zh": f"{bp:+.0f}基点/3月" if bp is not None else "—"}
    # MOVE: level z over 1y
    w = s.iloc[-_TY:]
    z = float((s.iloc[-1] - w.mean()) / w.std()) if w.std() else None
    return {"val": z, "disp_en": f"z {z:+.1f}" if z is not None else "—",
            "disp_zh": f"z {z:+.1f}" if z is not None else "—"}


def snapshot(f: pd.DataFrame) -> dict | None:
    if f is None or f.empty:
        return None
    drivers = _drivers(f)
    impulses = {k: _impulse(v, f) for k, v in drivers.items()}

    assets = []
    for spec in _ASSETS:
        kind, tk = spec["src"]
        px = _f(f, tk) if kind == "f" else _yahoo(tk)
        drv = drivers.get(spec["driver"])
        b = _beta(px, drv["s"] if drv else None)
        if b is None:
            continue
        beta = b["beta"]
        imp = impulses.get(spec["driver"], {})
        # display beta: per +10bp for a rate driver, raw weekly-return-per-unit otherwise
        if drv["rate"]:
            beta_10bp_pct = beta * 0.10 * 100.0   # weekly % move per +10bp
            beta_disp = f"{beta_10bp_pct:+.2f}%/+10bp"
        else:
            beta_disp = f"{beta*100:+.2f}%/unit"
        # headwind/tailwind = sign(beta) × current impulse direction
        contrib = None
        if imp.get("val") is not None:
            contrib = beta * imp["val"]
        verdict = ("tailwind" if (contrib or 0) > 0 else "headwind" if (contrib or 0) < 0 else "neutral")
        assets.append({
            "key": spec["key"], "icon": spec["icon"], "en": spec["en"], "zh": spec["zh"],
            "driver_key": spec["driver"], "driver_en": drv["en"], "driver_zh": drv["zh"],
            "beta": _r(beta, 3), "beta_disp": beta_disp, "corr": _r(b["corr"], 2), "n": b["n"],
            "sign": "neg" if beta < 0 else "pos",
            "impulse_en": imp.get("disp_en"), "impulse_zh": imp.get("disp_zh"),
            "verdict": verdict,
            "story_en": spec["story_en"], "story_zh": spec["story_zh"],
        })

    # driver snapshot for the header strip
    drv_now = {
        "real_10y": _r(_f(f, "us10y_real").iloc[-1] if _f(f, "us10y_real") is not None else None, 2),
        "real_chg_bp": _r(impulses["real_10y"].get("val"), 0),
        "slope": _r(_f(f, "spread_10y3m").iloc[-1] if _f(f, "spread_10y3m") is not None else None, 2),
        "slope_chg_bp": _r(impulses["slope"].get("val"), 0),
        "hy_oas": _r(_f(f, "hy_oas").iloc[-1] if _f(f, "hy_oas") is not None else None, 2),
        "hy_chg_bp": _r(impulses["hy_oas"].get("val"), 0),
        "breakeven": _r(_f(f, "breakeven_10y").iloc[-1] if _f(f, "breakeven_10y") is not None else None, 2),
        "move": _r(_f(f, "move").iloc[-1] if _f(f, "move") is not None else None, 0),
    }

    snap = {"as_of": str(f.index[-1].date()), "drivers_now": drv_now, "assets": assets}
    snap["verdict_en"], snap["verdict_zh"] = _verdict(snap)
    return snap


def _verdict(s: dict) -> tuple[str, str]:
    tail = [a for a in s["assets"] if a["verdict"] == "tailwind"]
    head = [a for a in s["assets"] if a["verdict"] == "headwind"]
    dn = s["drivers_now"]
    en = (f"Real-10y {dn.get('real_10y')}% ({dn.get('real_chg_bp'):+.0f}bp/3m), curve {dn.get('slope')}pp, "
          f"HY OAS {dn.get('hy_oas')}%. ") if dn.get('real_10y') is not None else ""
    en += f"{len(tail)} markets with a bond tailwind, {len(head)} with a headwind right now."
    zh = (f"10年实际利率 {dn.get('real_10y')}%（{dn.get('real_chg_bp'):+.0f}基点/3月），曲线 {dn.get('slope')}pp，"
          f"高收益利差 {dn.get('hy_oas')}%。") if dn.get('real_10y') is not None else ""
    zh += f"当前 {len(tail)} 个市场受债券顺风，{len(head)} 个受逆风。"
    return en, zh
