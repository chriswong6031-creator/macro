"""Hong Kong daily market-driver attribution — "what's moving the tape?"

A faithful HK-native clone of engine/china_market_drivers.py (itself a clone of
engine/market_drivers.py). The HK dashboard computes every macro / flow / cross-
asset leg but never says which single FORCE is actually moving the Hang Seng tape
on a given week. This leaf closes that gap: the dominant *driver* of the last few
sessions, the direction, the evidence, and what would invalidate it.

HK's reality shapes the fingerprints: HK trades at ~2x the Mainland's global-risk
beta, the HKD peg imports US policy via HIBOR, and HSI earnings are China-driven —
so the drivers are GLOBAL-first (SPY/VIX/DXY/EM), then China-spillover
(H-shares/southbound), then HK-local funding (peg/HIBOR/Aggregate Balance).

DESIGN — deterministic first, never scored (identical to the US/China modules):
  • Each driver is a FINGERPRINT: a signed, weighted set of legs that co-move when
    that driver is active.
  • Each day every leg's short-horizon move is z-scored against its OWN trailing
    252d history, so a 2σ move in HIBOR is comparable to a 2σ move in VHSI.
  • A driver's PROJECTION = weighted mean of (canonical-sign × leg-z). The dominant
    driver is the largest |projection|, gated by magnitude and dominance.

DISPLAY-ONLY INVARIANT: a regime READ, never a scored signal. Never imported by
engine/hk_axes.py / hk_regime.py / hk_playbook.py; never gates the quad or dial.
Degrades to verdict="unknown" if the frame is unavailable.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from lib import config, store


# --- small helpers (mirror engine/china_market_drivers.py) --------------------
def _z(s: pd.Series, window: int) -> pd.Series:
    m = s.rolling(window, min_periods=max(window // 4, 5)).mean()
    sd = s.rolling(window, min_periods=max(window // 4, 5)).std()
    return (s - m) / sd.replace(0, np.nan)


def _move(s: pd.Series, mtype: str, lw: int) -> pd.Series:
    return s.diff(lw) if mtype == "d" else s.pct_change(lw, fill_method=None)


# --- driver fingerprints ------------------------------------------------------
# leg = (column, move-type 'd'|'p', canonical sign, weight, window-override|None).
DRIVERS: dict[str, dict] = {
    "global_risk": {
        "label": "Global risk-on / risk-off",
        "family": "risk",
        "pos": "global risk-ON — S&P up, VIX & dollar down, EM/copper bid (HK's dominant force)",
        "neg": "global risk-OFF — S&P down, VIX & dollar up, EM/copper sold",
        "legs": [
            ("SPY", "p", +1, 1.0, None),                 # S&P 500 — the defining global-risk leg
            ("^VIX", "p", -1, 0.8, None),                # volatility down = risk-on
            ("DX-Y.NYB", "p", -1, 0.6, None),            # weaker dollar = EM/HK liquidity
            ("copper_gold", "p", +1, 0.5, None),         # industrial-vs-haven pulse
            ("EEM", "p", +1, 0.6, None),                 # EM equity beta
        ],
    },
    "china_spillover": {
        "label": "China stimulus spillover",
        "family": "growth",
        "pos": "China bid spilling into HK — H-shares & southbound lead up",
        "neg": "China risk-off spilling into HK — H-shares & southbound lead down",
        "legs": [
            ("hshare_hsi", "p", +1, 1.0, None),          # HSCEI/HSI — H-share leadership (defining)
            ("^HSCE", "p", +1, 0.7, None),               # HSCEI level
            ("southbound_cum", "d", +1, 0.6, None),      # mainland money into HK
            ("copper_gold", "p", +0.5, 0.4, None),       # China-demand proxy
        ],
    },
    "peg_funding_stress": {
        "label": "Peg / HIBOR funding stress",
        "family": "funding",
        "pos": "funding tightening — HKD toward 7.85 weak-side, HIBOR up, Aggregate Balance drained",
        "neg": "funding easing — HKD toward 7.75 strong-side, HIBOR down, Aggregate Balance refilled",
        "legs": [
            ("peg_distance", "d", +1, 1.0, None),        # toward weak-side = outflow (defining)
            ("hibor_on", "d", +1, 0.8, None),            # overnight funding cost
            ("agg_balance", "d", -1, 0.4, None),         # balance shrinks as HKMA defends the peg
        ],
    },
    "us_rate_repricing": {
        "label": "US-rate repricing (via the peg)",
        "family": "rates",
        "pos": "US rates repricing higher — dollar & HIBOR up, the peg imports tightening",
        "neg": "US rates repricing lower — dollar & HIBOR down, the peg imports easing",
        "legs": [
            ("DX-Y.NYB", "p", +1, 1.0, None),            # the dollar leads the rate repricing (defining)
            ("hibor_on", "d", +1, 0.7, None),            # HK rates shadow the Fed via the peg
            ("^VIX", "p", +0.4, 0.3, None),              # rate-shock vol
        ],
    },
    "southbound_appetite": {
        "label": "Southbound / mainland appetite",
        "family": "flows",
        "pos": "mainland risk-on — southbound buying HK, AH premium narrowing",
        "neg": "mainland risk-off — southbound selling HK, AH premium widening",
        "legs": [
            ("southbound_cum", "d", +1, 1.0, None),      # cumulative southbound net (defining)
            ("ah_premium", "d", -1, 0.5, None),          # AH premium narrowing = mainland bid for HK
        ],
    },
    "tech_internet_leadership": {
        "label": "Tech / internet leadership",
        "family": "equity-leadership",
        "pos": "HS-TECH leadership — narrow internet/tech-led tape",
        "neg": "HS-TECH unwind — internet/tech-led de-rating",
        "legs": [
            ("tech_hsi", "p", +1, 1.0, None),            # HS-TECH vs HSI (defining)
            ("3033.HK", "p", +1, 0.6, None),             # HS-TECH ETF
            ("0700.HK", "p", +0.4, 0.3, None),           # Tencent — the bellwether
        ],
    },
    "commodity_energy": {
        "label": "Commodity / energy",
        "family": "inflation",
        "pos": "upstream inflation — energy/materials basket & copper lead up",
        "neg": "upstream disinflation — energy/materials basket & copper lead down",
        "legs": [
            ("infl_basket", "p", +1, 1.0, None),         # HK inflation-beta basket (defining)
            ("copper_gold", "p", +0.6, 0.5, None),
            ("ppi_yoy", "d", +0.6, 0.4, 20),             # China PPI (monthly → 20d)
        ],
    },
    "risk_off_washout": {
        "label": "Risk-off / washout",
        "family": "volatility",
        "pos": "fear spike — VHSI up, breadth collapsing, HSI falling",
        "neg": "fear unwind — VHSI down, breadth recovering, HSI rising",
        "legs": [
            ("vhsi", "p", +1, 1.0, None),                # HK implied vol (defining)
            ("pct_above_50", "d", -1, 0.7, None),        # breadth collapse confirms fear
            ("^HSI", "p", -1, 0.4, None),                # price falls in a washout
        ],
    },
}

NAMES: dict[str, str] = {
    "SPY": "S&P 500", "^VIX": "VIX", "DX-Y.NYB": "US dollar (DXY)", "EEM": "EM equity (EEM)",
    "copper_gold": "copper / gold", "hshare_hsi": "H-shares vs HSI", "^HSCE": "HSCEI",
    "southbound_cum": "southbound flow", "peg_distance": "HKD peg distance",
    "hibor_on": "overnight HIBOR", "agg_balance": "Aggregate Balance", "ah_premium": "AH premium",
    "tech_hsi": "HS-TECH vs HSI", "3033.HK": "HS-TECH ETF", "0700.HK": "Tencent",
    "infl_basket": "inflation basket", "ppi_yoy": "PPI YoY", "vhsi": "VHSI (HK vol)",
    "pct_above_50": "breadth >50d", "^HSI": "Hang Seng",
}

DRIVERS_ZH: dict[str, tuple[str, str, str]] = {
    "global_risk": ("全球风险偏好", "全球偏好风险 — 标普上行、VIX与美元下行、新兴市场/铜受捧（香港主驱动）", "全球避险 — 标普下行、VIX与美元上行、新兴市场/铜遭抛"),
    "china_spillover": ("中国刺激外溢", "中国买盘外溢至香港 — H股与南向领涨", "中国避险外溢至香港 — H股与南向领跌"),
    "peg_funding_stress": ("联汇/HIBOR资金压力", "资金收紧 — 港元趋向7.85弱方、HIBOR上行、总结余被抽走", "资金宽松 — 港元趋向7.75强方、HIBOR下行、总结余回补"),
    "us_rate_repricing": ("美息重定价（经联汇）", "美息走高重定价 — 美元与HIBOR上行、联汇输入收紧", "美息走低重定价 — 美元与HIBOR下行、联汇输入宽松"),
    "southbound_appetite": ("南向/内资偏好", "内资偏好风险 — 南向买入港股、AH溢价收窄", "内资避险 — 南向卖出港股、AH溢价走阔"),
    "tech_internet_leadership": ("科技/互联网领涨", "恒生科技领涨 — 窄幅互联网/科技主导", "恒生科技回吐 — 互联网/科技主导的回调"),
    "commodity_energy": ("大宗/能源", "上游通胀 — 能源/材料篮子与铜领涨", "上游通缩 — 能源/材料篮子与铜领跌"),
    "risk_off_washout": ("避险/恐慌出清", "恐慌飙升 — VHSI上行、市场宽度崩塌、恒指下跌", "恐慌消退 — VHSI下行、宽度修复、恒指上涨"),
}
NAMES_ZH: dict[str, str] = {
    "SPY": "标普500", "^VIX": "VIX", "DX-Y.NYB": "美元指数(DXY)", "EEM": "新兴市场股票",
    "copper_gold": "铜/金", "hshare_hsi": "H股对恒指", "^HSCE": "国企指数",
    "southbound_cum": "南向资金", "peg_distance": "港元联汇距离", "hibor_on": "隔夜HIBOR",
    "agg_balance": "总结余", "ah_premium": "AH溢价", "tech_hsi": "恒生科技对恒指",
    "3033.HK": "恒生科技ETF", "0700.HK": "腾讯", "infl_basket": "通胀篮子",
    "ppi_yoy": "PPI同比", "vhsi": "VHSI(港股波动率)", "pct_above_50": "50日线上占比",
    "^HSI": "恒生指数",
}
VERDICT_ZH = {"clear": "明确", "mixed": "混合", "quiet": "平静", "unknown": "未知"}
CONF_ZH = {"low": "低", "medium": "中", "high": "高"}
FAMILY_ZH = {"risk": "风险", "growth": "增长", "funding": "资金", "rates": "利率",
             "flows": "资金流", "equity-leadership": "股票领涨", "inflation": "通胀",
             "volatility": "波动率"}


def _cfg() -> dict:
    base = {
        "window_d": 5,            # attribution horizon — "this week's driver"
        "z_window_d": 252,        # history the move is z-scored against
        "min_strength": 0.6,      # below this → "quiet"
        "dominance_ratio": 1.3,   # top must lead runner-up by this → else "mixed"
    }
    eng = config.load().get("hk", {}).get("engine", {})
    return {**base, **(eng.get("market_drivers", {}) or {})}


# --- frame assembly -----------------------------------------------------------
def _store_close(grp: str, sid: str, idx: pd.DatetimeIndex) -> pd.Series | None:
    df = store.read(grp, sid)
    if df is None or "close" not in getattr(df, "columns", []):
        return None
    s = df["close"].astype(float)
    s = s[~s.index.duplicated(keep="last")].sort_index()
    return s.reindex(idx.union(s.index)).ffill(limit=5).reindex(idx)


def _constituent_close(ticker: str, idx: pd.DatetimeIndex) -> pd.Series | None:
    """One HK constituent's close from the hk_breadth live cache (0700.HK etc.)."""
    try:
        cc = pd.read_parquet(config.data_dir() / "hk_breadth" / "_closes_cache.parquet")
    except (FileNotFoundError, OSError):
        return None
    if cc is None or cc.empty or ticker not in cc.columns:
        return None
    s = cc[ticker].astype(float).dropna()
    s = s[~s.index.duplicated(keep="last")].sort_index()
    return s.reindex(idx.union(s.index)).ffill(limit=5).reindex(idx)


def assemble_frame() -> pd.DataFrame:
    """The HK feature frame plus the extra legs (global SPY/VIX/DXY/EEM, the HKD
    peg distance, the AH premium, Tencent) the base build_features() doesn't carry.
    Each extra degrades to absent if its source is missing."""
    from engine.hk_inputs import build_features

    f = build_features()
    idx = f.index
    extra: dict[str, pd.Series] = {
        "SPY": _store_close("yahoo", "SPY", idx),
        "^VIX": _store_close("yahoo", "^VIX", idx),
        "DX-Y.NYB": _store_close("yahoo", "DX-Y.NYB", idx),
        "EEM": _store_close("hk", "EEM", idx),
        "0700.HK": _constituent_close("0700.HK", idx),
    }
    # HKD peg distance (0 = 7.75 strong-side, 1 = 7.85 weak-side)
    if "usdhkd" in f and not f["usdhkd"].dropna().empty:
        try:
            from engine import hk_global
            pf = hk_global.peg_frame(f["usdhkd"].dropna())
            if not pf.empty and "peg_distance" in pf.columns:
                s = pf["peg_distance"]
                extra["peg_distance"] = s.reindex(idx.union(s.index)).ffill(limit=5).reindex(idx)
        except Exception:  # noqa: BLE001 — additive leg
            pass
    # AH premium — official ~190-pair index if collected, else the computed basket
    ah = None
    off = store.read("hk_ah_official", "ah_premium")
    if off is not None and "hsahp" in getattr(off, "columns", []):
        s = off["hsahp"].astype(float).dropna()
        if not s.empty:
            ah = s.reindex(idx.union(s.index)).ffill(limit=5).reindex(idx)
    if ah is None:
        try:
            from engine.hk_ah import ah_basket_series
            b = ah_basket_series()
            if b is not None and not b.empty:
                ah = b.reindex(idx.union(b.index)).ffill(limit=5).reindex(idx)
        except Exception:  # noqa: BLE001
            ah = None
    if ah is not None:
        extra["ah_premium"] = ah
    extra = {k: v for k, v in extra.items() if v is not None}
    return pd.concat([f, pd.DataFrame(extra, index=idx)], axis=1)


# --- core attribution (identical machinery to china_market_drivers) -----------
def projections(frame: pd.DataFrame, cfg: dict | None = None):
    cfg = cfg or _cfg()
    window, zwin = int(cfg["window_d"]), int(cfg["z_window_d"])
    proj: dict[str, pd.Series] = {}
    raw_z: dict[str, dict[str, pd.Series]] = {}
    for dname, spec in DRIVERS.items():
        contribs, weights, legs = [], [], {}
        for col, mtype, sign, w, lw in spec["legs"]:
            if col not in frame.columns or frame[col].isna().all():
                continue
            z = _z(_move(frame[col], mtype, lw or window), zwin)
            legs[col] = z
            contribs.append(sign * z * w)
            weights.append(w)
        raw_z[dname] = legs
        if contribs:
            num = pd.concat(contribs, axis=1).sum(axis=1, min_count=1)
            proj[dname] = num / sum(weights)
    return pd.DataFrame(proj), raw_z


def _evidence_legs(spec: dict, legs_z: dict, day, k: int = 3) -> list[dict]:
    items = []
    weight = {c: w for c, _, _, w, _ in spec["legs"]}
    for col, z in legs_z.items():
        v = z.get(day)
        if v is None or pd.isna(v):
            continue
        items.append((col, float(v), weight.get(col, 1.0)))
    items.sort(key=lambda x: -abs(x[1] * x[2]))
    return [{"en": NAMES.get(c, c), "zh": NAMES_ZH.get(c, c), "z": round(v, 1)}
            for c, v, _ in items[:k]]


def _agreement(spec: dict, legs_z: dict, day, proj_sign: int) -> float:
    num = den = 0.0
    for col, mtype, sign, w, lw in spec["legs"]:
        z = legs_z.get(col)
        if z is None:
            continue
        v = z.get(day)
        if v is None or pd.isna(v):
            continue
        den += w
        if np.sign(sign * v) == proj_sign:
            num += w
    return num / den if den else 0.0


def _confidence(strength: float, ratio: float, agree: float) -> str:
    if strength >= 1.3 and ratio >= 1.5:
        return "high"
    if strength >= 0.8 and ratio >= 1.2:
        return "medium"
    return "low"


def classify_day(proj_df: pd.DataFrame, raw_z: dict, day, cfg: dict | None = None) -> dict:
    cfg = cfg or _cfg()
    row = proj_df.loc[day].dropna()
    if row.empty:
        return {"asof": str(pd.Timestamp(day).date()), "verdict": "unknown",
                "headline": "no driver projections available"}

    ranked = row.reindex(row.abs().sort_values(ascending=False).index)
    top_d, top_v = ranked.index[0], float(ranked.iloc[0])
    strength = abs(top_v)
    runner_d = ranked.index[1] if len(ranked) > 1 else None
    runner_v = float(ranked.iloc[1]) if len(ranked) > 1 else 0.0
    ratio = strength / max(abs(runner_v), 1e-9)

    spec = DRIVERS[top_d]
    zh = DRIVERS_ZH[top_d]
    proj_sign = 1 if top_v >= 0 else -1
    direction = spec["pos"] if proj_sign > 0 else spec["neg"]
    direction_zh = zh[1] if proj_sign > 0 else zh[2]
    agree = _agreement(spec, raw_z[top_d], day, proj_sign)
    ev_legs = _evidence_legs(spec, raw_z[top_d], day)
    evidence = [f"{e['en']} {e['z']:+.1f}σ" for e in ev_legs]

    if strength < cfg["min_strength"]:
        verdict = "quiet"
    elif ratio < cfg["dominance_ratio"]:
        verdict = "mixed"
    else:
        verdict = "clear"

    conf = _confidence(strength, ratio, agree)

    if verdict == "quiet":
        headline = ("No dominant driver — HK cross-asset moves are within their "
                    "normal weekly range.")
    elif verdict == "mixed":
        join = f"{spec['label']} + {DRIVERS[runner_d]['label']}"
        headline = (f"Mixed — {join} jointly leading "
                    f"({', '.join(evidence)}); no single dominant driver.")
    else:
        headline = f"{spec['label']} — {direction}. {', '.join(evidence)}."

    defining_en = NAMES.get(spec["legs"][0][0], spec["legs"][0][0])
    defining_zh = NAMES_ZH.get(spec["legs"][0][0], spec["legs"][0][0])
    fam_zh = FAMILY_ZH.get(spec["family"], spec["family"])
    invalidation = (f"Fades if {defining_en} reverses and the rest of the "
                    f"{spec['family']} fingerprint stops confirming.")
    invalidation_zh = f"若{defining_zh}反转、且{fam_zh}指纹其余腿停止确认，此判读将消退。"

    scores = [{
        "driver": d, "label": DRIVERS[d]["label"], "label_zh": DRIVERS_ZH[d][0],
        "family": DRIVERS[d]["family"], "projection": round(float(v), 2),
        "strength": round(abs(float(v)), 2),
        "direction": DRIVERS[d]["pos"] if v >= 0 else DRIVERS[d]["neg"],
    } for d, v in ranked.items()]

    return {
        "asof": str(pd.Timestamp(day).date()),
        "window_d": int(cfg["window_d"]),
        "verdict": verdict,
        "verdict_zh": VERDICT_ZH.get(verdict, verdict),
        "primary": top_d,
        "primary_label": spec["label"],
        "primary_label_zh": zh[0],
        "direction": direction,
        "direction_zh": direction_zh,
        "dir_sign": proj_sign,
        "confidence": conf,
        "confidence_zh": CONF_ZH.get(conf, conf),
        "strength": round(strength, 2),
        "dominance_ratio": round(ratio, 2),
        "agreement": round(agree, 2),
        "runner_up": runner_d,
        "runner_up_label": DRIVERS[runner_d]["label"] if runner_d else None,
        "runner_up_label_zh": DRIVERS_ZH[runner_d][0] if runner_d else None,
        "headline": headline,
        "evidence": evidence,
        "evidence_legs": ev_legs,
        "invalidation": invalidation,
        "invalidation_zh": invalidation_zh,
        "scores": scores,
        "note": ("Deterministic HK cross-asset attribution — a regime READ, not a "
                 "signal; never gates a score or the quad."),
    }


def snapshot() -> dict:
    """Latest HK market-driver attribution for hk latest.json["market_drivers"]."""
    try:
        frame = assemble_frame()
    except Exception as e:  # pragma: no cover - defensive
        return {"verdict": "unknown", "headline": f"feature frame unavailable: {e}"}
    cfg = _cfg()
    proj_df, raw_z = projections(frame, cfg)
    if proj_df.empty:
        return {"verdict": "unknown", "headline": "no driver projections available"}
    day = proj_df.dropna(how="all").index[-1]
    return classify_day(proj_df, raw_z, day, cfg)


def history(n: int = 20) -> list[dict]:
    frame = assemble_frame()
    cfg = _cfg()
    proj_df, raw_z = projections(frame, cfg)
    proj_df = proj_df.dropna(how="all")
    return [classify_day(proj_df, raw_z, day, cfg) for day in proj_df.index[-n:]]


def append_log(snap: dict) -> None:
    """Append today's verdict to an append-only log (keep-first per date) so the
    attribution can be GRADED later. Best-effort; never read back into a score."""
    try:
        if not snap or snap.get("verdict") in (None, "unknown") or not snap.get("asof"):
            return
        p = config.data_dir() / "hk_regime" / "hk_market_drivers_log.parquet"
        p.parent.mkdir(parents=True, exist_ok=True)
        asof = str(snap["asof"])
        old = pd.read_parquet(p) if p.exists() else None
        if old is not None and "asof" in old.columns and asof in set(old["asof"].astype(str)):
            return
        row = {k: snap.get(k) for k in
               ("asof", "verdict", "primary", "direction", "dir_sign", "confidence",
                "strength", "dominance_ratio")}
        row["evidence"] = "; ".join(snap.get("evidence") or [])
        new = pd.DataFrame([row])
        out = pd.concat([old, new], ignore_index=True) if old is not None else new
        out.to_parquet(p, index=False)
    except Exception:
        pass
