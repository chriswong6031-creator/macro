"""China A-share daily market-driver attribution — "what's moving the tape?"

A faithful China-native clone of engine/market_drivers.py. The China dashboard
computes every macro / flow / cross-asset leg but never says which single FORCE is
actually moving the A-share tape on a given week. This leaf closes that gap: it
turns the data wall into a one-line interpretation — the dominant *driver* of the
last few sessions, the direction, the evidence, and what would invalidate it.

DESIGN — deterministic first, never scored (identical to the US module).
  • Each driver is a FINGERPRINT: a signed, weighted set of legs that co-move when
    that driver is active (e.g. a PBoC tightening surprise lifts SHIBOR 3m/1y and
    the CGB 10y together; a stimulus tape lifts CSI300, brokers, copper and rebar).
  • Each day every leg's short-horizon move is z-scored against its OWN trailing
    252d history, so a 2σ move in SHIBOR is comparable to a 2σ move in QVIX.
  • A driver's PROJECTION = weighted mean of (canonical-sign × leg-z). It is large
    only when the WHOLE fingerprint is lit in a coherent direction — one big leg
    with contradicting legs cancels out. The dominant driver is the largest
    |projection|, gated by magnitude (is anything moving?) and dominance (does it
    lead the runner-up?).
  • This is an INTERPRETER, not a signal. NOTHING in the China scoring path imports
    it: it never feeds engine/china_axes.py, china_regime.py or china_playbook.py,
    never gates a leg or a score. These are descriptive display panels only. An
    optional append-only log lets us grade the calls later.

DISPLAY-ONLY INVARIANT: this module is a regime READ, never a scored signal. It
must never be imported by china_axes.py / china_regime.py / china_playbook.py, and
nothing here may flow into the quad classification or the exposure dial.

ADDITIVE / leaf module: snapshot() reads the store itself and returns a dict for
china latest.json["market_drivers"], degrading to verdict="unknown" if the feature
frame is unavailable. Same None-safe / degrade-don't-crash contract as the US side.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from lib import config, store


# --- small helpers (kept local; mirror engine/market_drivers.py) --------------
def _z(s: pd.Series, window: int) -> pd.Series:
    """Causal rolling z-score."""
    m = s.rolling(window, min_periods=max(window // 4, 5)).mean()
    sd = s.rolling(window, min_periods=max(window // 4, 5)).std()
    return (s - m) / sd.replace(0, np.nan)


def _move(s: pd.Series, mtype: str, lw: int) -> pd.Series:
    """Short-horizon move: 'd' = change in level/rate units, 'p' = % change."""
    return s.diff(lw) if mtype == "d" else s.pct_change(lw, fill_method=None)


# --- driver fingerprints ------------------------------------------------------
# leg = (column, move-type 'd'|'p', canonical sign, weight, window-override|None).
# The canonical "+" direction is documented per driver by pos/neg; the projection
# SIGN selects the label, so the same fingerprint catches a selloff OR a rally
# driven by that force. `family` groups colinear drivers.
DRIVERS: dict[str, dict] = {
    "pboc_repricing": {
        "label": "PBoC / rates repricing",
        "family": "rates",
        "pos": "rates repricing tighter — SHIBOR & CGB yields up, liquidity drained",
        "neg": "rates repricing easier — SHIBOR & CGB yields down, liquidity added",
        "legs": [
            ("rate_1y", "d", +1, 1.0, None),               # 1y SHIBOR — the defining leg
            ("rate_3m", "d", +1, 0.7, None),               # 3m SHIBOR
            ("cgb_10y", "d", +1, 0.6, None),               # 10y China govt bond yield
            ("usdcny", "p", +1, 0.3, None),                # PBoC-pinned fix firms with tightening
        ],
    },
    "cny_shock": {
        "label": "Yuan (CNH) shock",
        "family": "fx",
        "pos": "yuan weakening — CNH up, capital-outflow stress, equities pressured",
        "neg": "yuan firming — CNH down, capital-inflow relief, equities supported",
        "legs": [
            ("usdcnh", "p", +1, 1.0, None),                # offshore yuan — the capital-flow leg (defining)
            ("dxy", "p", +1, 0.6, None),                   # strong USD = yuan pressure
            ("cnh_cny_basis", "d", +1, 0.5, None),         # CNH cheaper than CNY = offshore stress
            ("510300.SS", "p", -1, 0.4, None),             # weaker yuan pressures A-shares
        ],
    },
    "liquidity_impulse": {
        "label": "Liquidity impulse",
        "family": "liquidity",
        "pos": "domestic liquidity easing — M1/M2 up, overnight cheap, small-caps & margin bid",
        "neg": "domestic liquidity draining — M1/M2 down, overnight dear, small-caps & margin sold",
        "legs": [
            ("m1_yoy", "d", +1, 1.0, 20),                  # M1 YoY (monthly → 20d window) — defining
            ("m2_yoy", "d", +0.6, 0.5, 20),                # M2 YoY
            ("rate_3m", "d", -1, 0.5, None),               # falling SHIBOR = easier (inverse)
            ("margin_total", "p", +1, 0.5, 20),            # margin balance momentum (risk appetite)
            ("smallcap_largecap", "p", +1, 0.4, None),     # small-caps lead when liquidity flushes in
        ],
    },
    "china_stimulus": {
        "label": "Stimulus tape",
        "family": "growth",
        "pos": "stimulus-on — CSI300, brokers, property & copper/rebar lead up",
        "neg": "stimulus-off — CSI300, brokers, property & copper/rebar lead down",
        "legs": [
            ("510300.SS", "p", +1, 1.0, None),             # CSI300 ETF — the defining leg
            ("512880.SS", "p", +1, 0.7, None),             # brokers (the classic stimulus front-runner)
            ("512200.SS", "p", +0.6, 0.6, None),           # real-estate ETF
            ("copper", "p", +1, 0.5, None),                # China demand proxy
            ("rebar", "p", +1, 0.4, None),                 # construction demand
            ("iron_ore", "p", +0.6, 0.3, None),
        ],
    },
    "inflation_commodities": {
        "label": "Inflation / commodities",
        "family": "inflation",
        "pos": "upstream inflation — PPI, coal, nonferrous & oil lead up",
        "neg": "upstream disinflation — PPI, coal, nonferrous & oil lead down",
        "legs": [
            ("ppi_yoy", "d", +1, 1.0, 20),                 # PPI YoY (monthly → 20d) — defining
            ("515220.SS", "p", +1, 0.6, None),             # coal ETF
            ("512400.SS", "p", +1, 0.6, None),             # nonferrous ETF
            ("oil", "p", +0.7, 0.4, None),                 # WTI
            ("copper", "p", +0.6, 0.4, None),
        ],
    },
    "ai_semis": {
        "label": "AI / semis leadership",
        "family": "equity-leadership",
        "pos": "AI/semis leadership — narrow tech-led tape",
        "neg": "AI/semis unwind — tech-led de-rating",
        "legs": [
            ("semis_rs", "p", +1, 1.0, None),              # semis vs CSI300 (defining)
            ("tech_rs", "p", +1, 0.6, None),               # tech vs CSI300
            ("smallcap_largecap", "p", +0.4, 0.3, None),   # growth/small-cap spillover (weak)
        ],
    },
    "southbound_appetite": {
        "label": "Southbound / mainland appetite",
        "family": "flows",
        "pos": "mainland risk-on — southbound buying HK, AH premium narrowing",
        "neg": "mainland risk-off — southbound selling HK, AH premium widening",
        "legs": [
            ("southbound_cum", "d", +1, 1.0, None),        # cumulative southbound net (defining)
            ("ah_premium", "d", -1, 0.5, None),            # AH premium narrowing = mainland bid (often missing → drops)
        ],
    },
    "risk_off_washout": {
        "label": "Risk-off / washout",
        "family": "volatility",
        "pos": "fear spike — QVIX up, breadth collapsing, limit-downs surge",
        "neg": "fear unwind — QVIX down, breadth recovering, limit-downs fade",
        "legs": [
            ("qvix300", "p", +1, 1.0, None),               # A-share VIX (defining)
            ("pct_above_50", "d", -1, 0.7, None),          # breadth collapse confirms fear
            ("510300.SS", "p", -1, 0.4, None),             # price falls in a washout
        ],
    },
}

# Human-readable leg names (English) for the evidence line.
NAMES: dict[str, str] = {
    "rate_1y": "1y SHIBOR", "rate_3m": "3m SHIBOR", "cgb_10y": "10y CGB yield",
    "usdcny": "onshore USDCNY", "usdcnh": "offshore CNH", "dxy": "US dollar (DXY)",
    "cnh_cny_basis": "CNH−CNY basis", "510300.SS": "CSI 300", "512880.SS": "brokers",
    "512200.SS": "real estate", "copper": "copper", "rebar": "rebar (螺纹钢)",
    "iron_ore": "iron ore (铁矿石)", "m1_yoy": "M1 YoY", "m2_yoy": "M2 YoY",
    "margin_total": "margin balance", "smallcap_largecap": "small vs large caps",
    "ppi_yoy": "PPI YoY", "515220.SS": "coal", "512400.SS": "nonferrous",
    "oil": "oil (WTI)", "semis_rs": "semis RS", "tech_rs": "tech RS",
    "southbound_cum": "southbound flow", "ah_premium": "AH premium",
    "qvix300": "QVIX (A-share vol)", "pct_above_50": "breadth >50d",
}

# Chinese mirrors (the dashboard is fully bilingual; dynamic engine strings ship
# both en + zh, like the cross-asset / market-drivers leg).
DRIVERS_ZH: dict[str, tuple[str, str, str]] = {
    "pboc_repricing": ("央行/利率重定价", "利率收紧重定价 — SHIBOR与国债收益率上行、流动性回收", "利率宽松重定价 — SHIBOR与国债收益率下行、流动性投放"),
    "cny_shock": ("人民币(CNH)冲击", "人民币走弱 — CNH上行、资本外流压力、股市承压", "人民币走强 — CNH下行、资本流入缓和、股市受支撑"),
    "liquidity_impulse": ("流动性脉冲", "境内流动性宽松 — M1/M2上行、隔夜利率走低、小盘与两融受捧", "境内流动性收缩 — M1/M2下行、隔夜利率走高、小盘与两融遭抛"),
    "china_stimulus": ("刺激行情", "刺激开启 — 沪深300、券商、地产与铜/螺纹领涨", "刺激退潮 — 沪深300、券商、地产与铜/螺纹领跌"),
    "inflation_commodities": ("通胀/大宗", "上游通胀 — PPI、煤炭、有色与油价领涨", "上游通缩 — PPI、煤炭、有色与油价领跌"),
    "ai_semis": ("AI/半导体领涨", "AI/半导体领涨 — 窄幅科技主导", "AI/半导体回吐 — 科技主导的回调"),
    "southbound_appetite": ("南向/内资偏好", "内资偏好风险 — 南向买入港股、AH溢价收窄", "内资避险 — 南向卖出港股、AH溢价走阔"),
    "risk_off_washout": ("避险/恐慌出清", "恐慌飙升 — QVIX上行、市场宽度崩塌、跌停潮", "恐慌消退 — QVIX下行、宽度修复、跌停减少"),
}
NAMES_ZH: dict[str, str] = {
    "rate_1y": "1年期SHIBOR", "rate_3m": "3个月SHIBOR", "cgb_10y": "10年期国债收益率",
    "usdcny": "在岸人民币", "usdcnh": "离岸人民币CNH", "dxy": "美元指数(DXY)",
    "cnh_cny_basis": "CNH−CNY价差", "510300.SS": "沪深300", "512880.SS": "券商",
    "512200.SS": "房地产", "copper": "铜", "rebar": "螺纹钢", "iron_ore": "铁矿石",
    "m1_yoy": "M1同比", "m2_yoy": "M2同比", "margin_total": "两融余额",
    "smallcap_largecap": "小盘对大盘", "ppi_yoy": "PPI同比", "515220.SS": "煤炭",
    "512400.SS": "有色", "oil": "原油(WTI)", "semis_rs": "半导体相对强度",
    "tech_rs": "科技相对强度", "southbound_cum": "南向资金", "ah_premium": "AH溢价",
    "qvix300": "QVIX(A股波动率)", "pct_above_50": "50日线上占比",
}
VERDICT_ZH = {"clear": "明确", "mixed": "混合", "quiet": "平静", "unknown": "未知"}
CONF_ZH = {"low": "低", "medium": "中", "high": "高"}
FAMILY_ZH = {"rates": "利率", "fx": "外汇", "liquidity": "流动性", "growth": "增长",
             "inflation": "通胀", "equity-leadership": "股票领涨", "flows": "资金流",
             "volatility": "波动率"}


def _cfg() -> dict:
    base = {
        "window_d": 5,            # attribution horizon — "this week's driver"
        "z_window_d": 252,        # history the move is z-scored against
        "min_strength": 0.6,      # below this → "quiet" (moves within normal range)
        "dominance_ratio": 1.3,   # top must lead runner-up by this → else "mixed"
    }
    eng = config.load().get("china", {}).get("engine", {})
    return {**base, **(eng.get("market_drivers", {}) or {})}


# --- frame assembly -----------------------------------------------------------
def _store_close(grp: str, sid: str, idx: pd.DatetimeIndex) -> pd.Series | None:
    df = store.read(grp, sid)
    if df is None or "close" not in getattr(df, "columns", []):
        return None
    s = df["close"].astype(float)
    s = s[~s.index.duplicated(keep="last")].sort_index()
    return s.reindex(idx.union(s.index)).ffill(limit=5).reindex(idx)


def assemble_frame() -> pd.DataFrame:
    """The China feature frame plus the extra legs (global commodities/DXY, QVIX,
    margin balance, CGB yield, AH premium, RS ratios, CNH basis) the base
    build_features() doesn't carry. Each extra degrades to absent if its source
    is missing — projections() simply drops the leg and renormalizes."""
    from engine.china_inputs import build_features

    f = build_features()
    idx = f.index
    extra: dict[str, pd.Series] = {
        "copper": _store_close("yahoo", "HG=F", idx),
        "oil": _store_close("yahoo", "CL=F", idx),
        "dxy": _store_close("yahoo", "DX-Y.NYB", idx),
        "qvix300": _store_close("china_qvix", "qvix300", idx),
        "rebar": _store_close("china_property", "rebar", idx),
        "iron_ore": _store_close("china_property", "iron_ore", idx),
    }
    # 10y CGB yield (level, in %) — lives as a column, not "close", in china_property/cgb
    cgb = store.read("china_property", "cgb")
    if cgb is not None and "cgb_10y" in getattr(cgb, "columns", []):
        s = cgb["cgb_10y"].astype(float)
        s = s[~s.index.duplicated(keep="last")].sort_index()
        extra["cgb_10y"] = s.reindex(idx.union(s.index)).ffill(limit=5).reindex(idx)
    # margin balance (亿元) — financing total, the crowding/risk-appetite leg
    mb = store.read("china_margin", "balance")
    if mb is not None and "margin_total" in getattr(mb, "columns", []):
        s = mb["margin_total"].astype(float).dropna()
        s = s[~s.index.duplicated(keep="last")].sort_index()
        extra["margin_total"] = s.reindex(idx.union(s.index)).ffill(limit=5).reindex(idx)
    # AH premium (Hang Seng AH) — usually SHALLOW; drops automatically if too short
    ah = store.read("china_flows", "ah_premium")
    if ah is not None and "hsahp" in getattr(ah, "columns", []):
        s = ah["hsahp"].astype(float).dropna()
        s = s[~s.index.duplicated(keep="last")].sort_index()
        extra["ah_premium"] = s.reindex(idx.union(s.index)).ffill(limit=5).reindex(idx)
    # CNH−CNY basis (offshore stress: CNH cheaper-to-USD than the onshore fix)
    if "usdcnh" in f and "usdcny" in f:
        extra["cnh_cny_basis"] = f["usdcnh"] - f["usdcny"]
    # semis / tech relative strength vs CSI300 (the AI/semis leadership analogue)
    if "512760.SS" in f and "510300.SS" in f:
        extra["semis_rs"] = f["512760.SS"] / f["510300.SS"]
    if "515000.SS" in f and "510300.SS" in f:
        extra["tech_rs"] = f["515000.SS"] / f["510300.SS"]
    extra = {k: v for k, v in extra.items() if v is not None}
    # single concat (not column-by-column inserts) to avoid frame fragmentation
    return pd.concat([f, pd.DataFrame(extra, index=idx)], axis=1)


# --- core attribution ---------------------------------------------------------
def projections(frame: pd.DataFrame, cfg: dict | None = None):
    """Return (proj_df, raw_z) where proj_df[driver] is the daily projection and
    raw_z[driver][col] is each leg's raw (own-direction) move z-score series."""
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
    """Top-k legs by weighted contribution, each with bilingual name + raw z (σ)."""
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
    """Weighted fraction of present legs whose move confirms the projection sign."""
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
    # Confidence rests on the two non-tautological signals: how BIG the move is
    # (strength) and how clearly it leads the runner-up (dominance ratio). Leg
    # agreement is near-tautological for the winner, so it is reported but not
    # scored. (The US module also folds in a cross-asset absorption-ratio cap;
    # the China book has no equivalent absorption series, so it is omitted.)
    if strength >= 1.3 and ratio >= 1.5:
        return "high"
    if strength >= 0.8 and ratio >= 1.2:
        return "medium"
    return "low"


def classify_day(proj_df: pd.DataFrame, raw_z: dict, day, cfg: dict | None = None) -> dict:
    """Turn one day's projections into a driver verdict dict."""
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
        headline = ("No dominant driver — China cross-asset moves are within their "
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
        "verdict": verdict,                       # clear | mixed | quiet | unknown
        "verdict_zh": VERDICT_ZH.get(verdict, verdict),
        "primary": top_d,
        "primary_label": spec["label"],
        "primary_label_zh": zh[0],
        "direction": direction,
        "direction_zh": direction_zh,
        "dir_sign": proj_sign,                    # +1 canonical "pos", -1 "neg" (UI coloring)
        "confidence": conf,
        "confidence_zh": CONF_ZH.get(conf, conf),
        "strength": round(strength, 2),
        "dominance_ratio": round(ratio, 2),
        "agreement": round(agree, 2),
        "runner_up": runner_d,
        "runner_up_label": DRIVERS[runner_d]["label"] if runner_d else None,
        "runner_up_label_zh": DRIVERS_ZH[runner_d][0] if runner_d else None,
        "headline": headline,
        "evidence": evidence,                     # flat strings (harness / log / LLM)
        "evidence_legs": ev_legs,                 # structured + bilingual (the card)
        "invalidation": invalidation,
        "invalidation_zh": invalidation_zh,
        "scores": scores,
        "note": ("Deterministic China cross-asset attribution — a regime READ, not "
                 "a signal; never gates a score or the quad."),
    }


def snapshot() -> dict:
    """Latest China market-driver attribution for china latest.json["market_drivers"]."""
    try:
        frame = assemble_frame()
    except Exception as e:  # pragma: no cover - defensive, mirrors other leaves
        return {"verdict": "unknown", "headline": f"feature frame unavailable: {e}"}
    cfg = _cfg()
    proj_df, raw_z = projections(frame, cfg)
    if proj_df.empty:
        return {"verdict": "unknown", "headline": "no driver projections available"}
    day = proj_df.dropna(how="all").index[-1]
    return classify_day(proj_df, raw_z, day, cfg)


def history(n: int = 20) -> list[dict]:
    """Last `n` days of attribution — for the preview harness / append-only log."""
    frame = assemble_frame()
    cfg = _cfg()
    proj_df, raw_z = projections(frame, cfg)
    proj_df = proj_df.dropna(how="all")
    return [classify_day(proj_df, raw_z, day, cfg) for day in proj_df.index[-n:]]


def append_log(snap: dict) -> None:
    """Append today's verdict to an append-only log (keep-first per date) so the
    attribution can be GRADED later. Best-effort — never read back into a score,
    never breaks the build. Mirrors engine/market_drivers.append_log()."""
    try:
        if not snap or snap.get("verdict") in (None, "unknown") or not snap.get("asof"):
            return
        p = config.data_dir() / "china_regime" / "china_market_drivers_log.parquet"
        p.parent.mkdir(parents=True, exist_ok=True)
        asof = str(snap["asof"])
        old = pd.read_parquet(p) if p.exists() else None
        if old is not None and "asof" in old.columns and asof in set(old["asof"].astype(str)):
            return  # keep-first: already logged today
        row = {k: snap.get(k) for k in
               ("asof", "verdict", "primary", "direction", "dir_sign", "confidence",
                "strength", "dominance_ratio")}
        row["evidence"] = "; ".join(snap.get("evidence") or [])
        new = pd.DataFrame([row])
        out = pd.concat([old, new], ignore_index=True) if old is not None else new
        out.to_parquet(p, index=False)
    except Exception:
        pass
