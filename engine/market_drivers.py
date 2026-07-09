"""Daily market-driver attribution — "what's in the driver's seat today?"

The dashboard computes every macro/cross-asset leg but never says which one is
actually MOVING the tape on a given day. This leaf closes that gap: it turns the
data wall into a one-line interpretation — the dominant *driver* of the last few
sessions, the direction, the evidence, and what would invalidate the read.

DESIGN — deterministic first, never scored.
  • Each driver is a FINGERPRINT: a signed, weighted set of cross-asset legs that
    co-move when that driver is active (e.g. a real-rate shock lifts the 10y real
    yield while gold and long-duration equity fall together).
  • Each day every leg's short-horizon move is z-scored against its OWN history,
    so a 2σ move in real yields is comparable to a 2σ move in HY spreads.
  • A driver's PROJECTION = the weighted mean of (canonical-sign × leg-z). It is
    large only when the *whole* fingerprint is lit in a coherent direction — one
    big leg with three contradicting legs cancels out. The dominant driver is the
    largest |projection|, gated by magnitude (is anything actually moving?) and
    dominance (does it lead the runner-up?), with the cross-asset ABSORPTION ratio
    as a "is the tape even one-factor today?" confidence input.
  • This is an INTERPRETER, not a signal. Nothing in the scoring path imports it;
    it never gates a leg or a score (the dashboard's narrative-uncertainty Phase-0
    already found text-narrative adds negative incremental info over VIX, so the
    narrative reads here stay display-only). An optional append-only log lets us
    grade the calls later.

ADDITIVE / leaf module: snapshot() reads the store itself and returns a dict for
latest.json["market_drivers"], degrading to verdict="unknown" if the feature
frame is unavailable. An LLM brief may NARRATE this verdict, but the classifier
is fully deterministic.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from lib import config, store


# --- small helpers (kept local; mirror engine/conditions.py) ------------------
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
# driven by that force. `family` groups colinear drivers (the rates complex etc.).
DRIVERS: dict[str, dict] = {
    "fed_repricing": {
        "label": "Fed repricing",
        "family": "rates",
        "pos": "hawkish repricing — cuts priced out, front-end up",
        "neg": "dovish repricing — cuts priced in, front-end down",
        "legs": [
            ("us2y", "d", +1, 1.0, None),                  # front-end leads — the defining leg
            ("rate_expectations_proxy", "d", +1, 0.7, None),  # 2y − fed funds (path repricing)
            ("zq_implied_rate", "d", +1, 0.5, None),       # fed-funds futures imply fewer cuts
            ("us10y", "d", +1, 0.5, None),
            ("dxy", "p", +1, 0.5, None),                   # hawkish Fed firms the dollar
            ("growth_value", "p", -1, 0.4, None),          # higher rates hit long-duration equity
        ],
    },
    "real_rate_shock": {
        "label": "Real-rate shock",
        "family": "rates",
        "pos": "real yields rising — restrictive, gold & duration hit",
        "neg": "real yields falling — easing, gold & duration bid",
        "legs": [
            ("us10y_real", "d", +1, 1.0, None),            # the defining leg (TIPS yield)
            ("gold", "p", -1, 0.7, None),                  # gold ~ inverse real rates
            ("growth_value", "p", -1, 0.5, None),
            ("QQQ", "p", -1, 0.3, None),
            ("term_premium_10y", "d", +1, 0.3, None),
        ],
    },
    "usd_shock": {
        "label": "USD shock",
        "family": "fx",
        "pos": "dollar surging — squeeze, commodities & EM pressured",
        "neg": "dollar falling — risk tailwind, commodities & EM bid",
        "legs": [
            ("dxy", "p", +1, 1.0, None),                   # defining
            ("copper", "p", -1, 0.5, None),
            ("oil", "p", -1, 0.3, None),
            ("china_eq", "p", -1, 0.4, None),              # EM/China pressured by strong USD
            ("gold", "p", -1, 0.3, None),
        ],
    },
    "credit_stress": {
        "label": "Credit stress",
        "family": "credit",
        "pos": "credit spreads widening — stress",
        "neg": "credit spreads compressing — risk-on",
        "legs": [
            ("hy_oas", "d", +1, 1.0, None),                # defining
            ("ebp", "d", +1, 0.6, 20),                     # excess bond premium (slow → 20d)
            ("hyg_lqd", "p", -1, 0.6, None),               # HY underperforms IG
            ("ig_oas", "d", +1, 0.3, None),
            ("vix", "p", +1, 0.3, None),
        ],
    },
    "liquidity_impulse": {
        "label": "Liquidity impulse",
        "family": "liquidity",
        "pos": "net liquidity expanding — broad risk-on tailwind",
        "neg": "net liquidity draining — risk headwind",
        "legs": [
            ("net_liquidity_bn", "d", +1, 1.0, 20),        # weekly series → 20d window
            ("sphb_splv", "p", +1, 0.4, None),             # high-beta over low-vol (junk rally)
            ("iwm_spy", "p", +1, 0.3, None),               # small caps over large (breadth)
            ("hyg_lqd", "p", +1, 0.3, None),
            ("btc", "p", +1, 0.3, None),                   # crypto as a liquidity sponge
        ],
    },
    "china_stimulus": {
        "label": "China stimulus",
        "family": "china",
        "pos": "China risk-on — A-shares/HK & copper lead up",
        "neg": "China risk-off — A-shares/HK & copper lead down",
        "legs": [
            ("china_eq", "p", +1, 1.0, None),              # defining (CSI 300)
            ("hk_eq", "p", +1, 0.7, None),                 # Hang Seng
            ("copper", "p", +1, 0.5, None),                # China demand proxy
            ("copper_gold", "p", +1, 0.3, None),
        ],
    },
    "oil_shock": {
        "label": "Oil shock",
        "family": "inflation",
        "pos": "oil spiking — energy leads, breakevens up",
        "neg": "oil collapsing — energy lags, breakevens down",
        "legs": [
            ("oil", "p", +1, 1.0, None),                   # defining
            ("energy_rs", "p", +1, 0.6, None),             # energy sector relative strength
            ("breakeven_10y", "d", +1, 0.5, None),         # oil pushes inflation expectations
            ("breakeven_5y5y", "d", +1, 0.3, None),
        ],
    },
    "ai_semis": {
        "label": "AI / semis",
        "family": "equity-leadership",
        "pos": "AI/semis leadership — narrow tech-led tape",
        "neg": "AI/semis unwind — tech-led de-rating",
        "legs": [
            ("smh_rs", "p", +1, 1.0, None),                # semis vs market (defining)
            ("growth_value", "p", +1, 0.5, None),
            ("xlk_xlu", "p", +1, 0.5, None),               # tech vs utilities
            ("qqq_rsp", "p", +1, 0.4, None),               # cap-weighted vs equal-weight (concentration)
        ],
    },
    "crypto_liquidity": {
        "label": "Crypto liquidity",
        "family": "crypto",
        "pos": "crypto liquidity surging — BTC/ETH lead up",
        "neg": "crypto liquidity draining — BTC/ETH lead down",
        "legs": [
            ("btc", "p", +1, 1.0, None),                   # defining
            ("eth", "p", +1, 0.5, None),
            ("sphb_splv", "p", +1, 0.2, None),             # risk-appetite spillover (weak)
        ],
    },
}

# Human-readable leg names (English) for the evidence line.
NAMES: dict[str, str] = {
    "us2y": "2y yield", "us10y": "10y yield", "us10y_real": "10y real yield",
    "breakeven_10y": "10y breakeven", "breakeven_5y5y": "5y5y breakeven",
    "rate_expectations_proxy": "rate-path (2y−FF)", "zq_implied_rate": "fed-funds futures",
    "term_premium_10y": "term premium", "dxy": "US dollar", "hy_oas": "HY spread",
    "ig_oas": "IG spread", "ebp": "excess bond premium", "hyg_lqd": "HY vs IG",
    "net_liquidity_bn": "net liquidity", "sphb_splv": "high-beta vs low-vol",
    "iwm_spy": "small vs large caps", "oil": "oil (WTI)", "copper": "copper",
    "gold": "gold", "copper_gold": "copper/gold", "energy_rs": "energy sector RS",
    "growth_value": "growth vs value", "xlk_xlu": "tech vs utilities", "QQQ": "Nasdaq-100",
    "qqq_rsp": "cap-weight vs equal-weight", "vix": "VIX", "btc": "bitcoin", "eth": "ether",
    "china_eq": "China A-shares", "hk_eq": "Hong Kong", "smh_rs": "semis RS",
}

# Chinese mirrors (the dashboard is fully bilingual; dynamic engine strings ship
# both _en and _zh, like the cross-asset confirmation leg).
DRIVERS_ZH: dict[str, tuple[str, str, str]] = {
    "fed_repricing": ("美联储重定价", "鹰派重定价 — 计入更少降息、前端利率上行", "鸽派重定价 — 计入更多降息、前端利率下行"),
    "real_rate_shock": ("实际利率冲击", "实际利率上行 — 紧缩，黄金与长久期承压", "实际利率下行 — 宽松，黄金与长久期受益"),
    "usd_shock": ("美元冲击", "美元飙升 — 挤压，大宗与新兴市场承压", "美元走弱 — 风险顺风，大宗与新兴市场受益"),
    "credit_stress": ("信用压力", "信用利差走阔 — 承压", "信用利差收窄 — 偏好风险"),
    "liquidity_impulse": ("流动性脉冲", "净流动性扩张 — 广泛风险顺风", "净流动性收缩 — 风险逆风"),
    "china_stimulus": ("中国刺激", "中国偏好风险 — A股/港股与铜领涨", "中国避险 — A股/港股与铜领跌"),
    "oil_shock": ("油价冲击", "油价飙升 — 能源领涨、盈亏平衡上行", "油价崩跌 — 能源落后、盈亏平衡下行"),
    "ai_semis": ("AI/半导体", "AI/半导体领涨 — 窄幅科技主导", "AI/半导体回吐 — 科技主导的回调"),
    "crypto_liquidity": ("加密流动性", "加密流动性涌入 — BTC/ETH领涨", "加密流动性流出 — BTC/ETH领跌"),
}
NAMES_ZH: dict[str, str] = {
    "us2y": "2年期收益率", "us10y": "10年期收益率", "us10y_real": "10年期实际收益率",
    "breakeven_10y": "10年盈亏平衡通胀", "breakeven_5y5y": "5年5年远期通胀",
    "rate_expectations_proxy": "利率路径(2年−联邦基金)", "zq_implied_rate": "联邦基金期货",
    "term_premium_10y": "期限溢价", "dxy": "美元", "hy_oas": "高收益利差",
    "ig_oas": "投资级利差", "ebp": "超额债券溢价", "hyg_lqd": "高收益对投资级",
    "net_liquidity_bn": "净流动性", "sphb_splv": "高贝塔对低波动",
    "iwm_spy": "小盘对大盘", "oil": "原油(WTI)", "copper": "铜", "gold": "黄金",
    "copper_gold": "铜/金", "energy_rs": "能源板块相对强度", "growth_value": "成长对价值",
    "xlk_xlu": "科技对公用事业", "QQQ": "纳斯达克100", "qqq_rsp": "市值加权对等权重",
    "vix": "VIX", "btc": "比特币", "eth": "以太坊", "china_eq": "中国A股",
    "hk_eq": "香港", "smh_rs": "半导体相对强度",
}
VERDICT_ZH = {"clear": "明确", "mixed": "混合", "quiet": "平静", "unknown": "未知"}
CONF_ZH = {"low": "低", "medium": "中", "high": "高"}
FAMILY_ZH = {"rates": "利率", "fx": "外汇", "credit": "信用", "liquidity": "流动性",
             "china": "中国", "inflation": "通胀", "equity-leadership": "股票领涨",
             "crypto": "加密"}

# repricing_coherence state thresholds (contract §4 W1-A)
_COH_THRESHOLDS = {"QUIET": (0, 40), "ELEVATED": (40, 70), "SHOCK": (70, 100)}
_COH_STATE_ZH = {"QUIET": "平静", "ELEVATED": "偏高", "SHOCK": "冲击"}


def _cfg() -> dict:
    base = {
        "window_d": 5,            # attribution horizon — "this week's driver"
        "z_window_d": 252,        # history the move is z-scored against
        "min_strength": 0.6,      # below this → "quiet" (moves within normal range)
        "dominance_ratio": 1.3,   # top must lead runner-up by this → else "mixed"
    }
    return {**base, **(config.load().get("engine", {}).get("market_drivers", {}) or {})}


# --- frame assembly -----------------------------------------------------------
def _store_close(grp: str, sid: str, idx: pd.DatetimeIndex) -> pd.Series | None:
    df = store.read(grp, sid)
    if df is None or "close" not in getattr(df, "columns", []):
        return None
    s = df["close"].astype(float)
    s = s[~s.index.duplicated(keep="last")].sort_index()
    return s.reindex(idx.union(s.index)).ffill(limit=5).reindex(idx)


def assemble_frame() -> pd.DataFrame:
    """The macro feature frame plus the extra price legs (crypto/China/HK/semis)
    that build_features() doesn't carry."""
    from engine.inputs import build_features

    f = build_features()
    idx = f.index
    extra = {
        "btc": _store_close("yahoo", "BTC-USD", idx),
        "eth": _store_close("yahoo", "ETH-USD", idx),
        "china_eq": _store_close("china", "510300.SS", idx),
        "hk_eq": _store_close("hk", "_HSI", idx),
    }
    smh = _store_close("yahoo", "SMH", idx)
    if smh is not None and "SPY" in f:
        extra["smh_rs"] = smh / f["SPY"]                   # semis relative to the market
    if "QQQ" in f and "RSP" in f:
        extra["qqq_rsp"] = f["QQQ"] / f["RSP"]             # concentration: cap-weight vs equal-weight
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


def _confidence(strength: float, ratio: float, agree: float, ar_pctile) -> str:
    # Confidence rests on the two non-tautological signals: how BIG the move is
    # (strength) and how clearly it leads the runner-up (dominance ratio). Leg
    # agreement is near-tautological for the winner, so it is reported but not
    # scored. A diversified cross-asset tape (low absorption) caps confidence —
    # if the six markets aren't even one bet, a single "dominant" driver is shaky.
    if strength >= 1.3 and ratio >= 1.5:
        c = "high"
    elif strength >= 0.8 and ratio >= 1.2:
        c = "medium"
    else:
        c = "low"
    if ar_pctile is not None and ar_pctile < 0.35 and c == "high":
        c = "medium"
    return c


def classify_day(proj_df: pd.DataFrame, raw_z: dict, day, cfg: dict | None = None,
                 ar_pctile: float | None = None) -> dict:
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

    conf = _confidence(strength, ratio, agree, ar_pctile)
    same_family = runner_d is not None and DRIVERS[runner_d]["family"] == spec["family"]

    if verdict == "quiet":
        headline = ("No dominant driver — cross-asset moves are within their normal "
                    "weekly range.")
    elif verdict == "mixed":
        join = "the rates complex" if same_family and spec["family"] == "rates" else \
               f"{spec['label']} + {DRIVERS[runner_d]['label']}"
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
        "dir_sign": proj_sign,                    # +1 canonical "pos", -1 "neg" (for UI coloring)
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
        "absorption_pctile": None if ar_pctile is None else round(float(ar_pctile), 2),
        "scores": scores,
        "note": ("Deterministic cross-asset attribution — a regime READ, not a signal; "
                 "never gates a score."),
    }


def _absorption_pctile_series(window: int = 63) -> pd.Series:
    """Expanding percentile of the cross-asset absorption ratio (one-factor-ness)."""
    try:
        from engine import cross_asset
        rets = cross_asset.returns_frame()
        ar = cross_asset.absorption_series(rets, window)
        if ar.empty:
            return pd.Series(dtype=float)
        return ar.expanding(min_periods=252).apply(lambda x: (x <= x[-1]).mean(), raw=True)
    except Exception:
        return pd.Series(dtype=float)


def _load_log_df() -> pd.DataFrame:
    """Load the market_drivers_log.parquet for coherence computation. Returns empty
    DataFrame on any failure (coherence degrades gracefully without it)."""
    try:
        p = config.data_dir() / "regime" / "market_drivers_log.parquet"
        return pd.read_parquet(p) if p.exists() else pd.DataFrame()
    except Exception:
        return pd.DataFrame()


def repricing_coherence(snap: dict, log_df: pd.DataFrame | None = None) -> dict:
    """Compute the repricing_coherence block from today's classify_day output.

    Inputs
    ------
    snap      : dict returned by classify_day() for today
    log_df    : (optional) existing market_drivers_log.parquet loaded by the caller
                so this function never reads from disk itself (pure function).
                Pass None to have it loaded automatically; on failure → quiet with note.

    Returns a dict with keys: score, state, components, state_zh, note, note_zh.
    Never raises — degrades to state=QUIET with a reason note on any error.

    Component scoring (contract §4 W1-A):
      driver_flip         30 pts — primary changed vs previous log row AND
                                   min(strength_today, strength_prev) >= 1.0
      strength_extreme    25 pts — strength >= p95 of trailing 252 log rows
                                   (fallback: strength >= 2.0 when < 40 rows)
      absorption_spike    20 pts — absorption_pctile >= 0.90 (0 if None)
      repricing_breadth   25 pts — >= 3 distinct driver families with |proj| >= 1.5
    """
    _quiet = lambda note, note_zh="": {   # noqa: E731
        "score": 0, "state": "QUIET", "state_zh": _COH_STATE_ZH["QUIET"],
        "components": {
            "driver_flip": 0, "strength_extreme": 0,
            "absorption_spike": 0, "repricing_breadth": 0,
        },
        "note": note,
        "note_zh": note_zh or "数据不足，降级为平静状态。",
    }

    try:
        if not snap or snap.get("verdict") in (None, "unknown"):
            return _quiet("no valid snap — degraded to QUIET",
                          "无有效快照，降级为平静状态。")

        # ---------- load log if not supplied ----------
        _log: pd.DataFrame | None = log_df
        if _log is None:
            try:
                p = config.data_dir() / "regime" / "market_drivers_log.parquet"
                _log = pd.read_parquet(p) if p.exists() else pd.DataFrame()
            except Exception:
                _log = pd.DataFrame()

        # ---------- component 1: driver_flip ----------
        c_flip = 0
        today_primary = snap.get("primary")
        today_strength = float(snap.get("strength") or 0.0)
        if _log is not None and not _log.empty and "primary" in _log.columns and "asof" in _log.columns:
            prev_rows = _log.sort_values("asof")
            today_asof = str(snap.get("asof", ""))
            prev_rows = prev_rows[prev_rows["asof"].astype(str) < today_asof]
            if not prev_rows.empty:
                prev_primary = prev_rows.iloc[-1].get("primary")
                prev_strength_raw = prev_rows.iloc[-1].get("strength")
                prev_strength = float(prev_strength_raw) if pd.notna(prev_strength_raw) else 0.0
                if (today_primary and prev_primary and today_primary != prev_primary and
                        min(today_strength, prev_strength) >= 1.0):
                    c_flip = 30

        # ---------- component 2: strength_extreme ----------
        c_strength = 0
        if _log is not None and not _log.empty and "strength" in _log.columns:
            today_asof = str(snap.get("asof", ""))
            hist_str = _log[_log["asof"].astype(str) < today_asof]["strength"].dropna()
            tail_252 = hist_str.iloc[-252:] if len(hist_str) >= 252 else hist_str
            if len(tail_252) >= 40:
                p95 = float(np.percentile(tail_252, 95))
                if today_strength >= p95:
                    c_strength = 25
            else:
                # fallback: fewer than 40 rows available
                if today_strength >= 2.0:
                    c_strength = 25

        # ---------- component 3: absorption_spike ----------
        c_absorb = 0
        ar = snap.get("absorption_pctile")
        if ar is not None and not np.isnan(float(ar)) and float(ar) >= 0.90:
            c_absorb = 20

        # ---------- component 4: repricing_breadth ----------
        # Count distinct driver families with |driver projection| >= 1.5.
        # The projections are already available in snap["scores"] as floats.
        c_breadth = 0
        scores_list = snap.get("scores") or []
        # Deduplicate by family — take the max |projection| per family.
        family_max: dict[str, float] = {}
        for s in scores_list:
            fam = DRIVERS.get(s.get("driver", ""), {}).get("family", "")
            proj_abs = abs(float(s.get("projection") or 0.0))
            if fam:
                family_max[fam] = max(family_max.get(fam, 0.0), proj_abs)
        n_families_hot = sum(1 for v in family_max.values() if v >= 1.5)
        if n_families_hot >= 3:
            c_breadth = 25

        # ---------- aggregate ----------
        score = c_flip + c_strength + c_absorb + c_breadth
        score = max(0, min(100, score))
        if score >= 70:
            state = "SHOCK"
        elif score >= 40:
            state = "ELEVATED"
        else:
            state = "QUIET"

        return {
            "score": score,
            "state": state,
            "state_zh": _COH_STATE_ZH[state],
            "components": {
                "driver_flip": c_flip,
                "strength_extreme": c_strength,
                "absorption_spike": c_absorb,
                "repricing_breadth": c_breadth,
            },
            "note": ("derived reading of market_drivers — de-escalation/display consumer only"),
            "note_zh": "基于市场驱动因子的衍生读数，仅供展示参考，不作为评分依据。",
        }

    except Exception as e:
        return _quiet(f"repricing_coherence computation error: {e}",
                      "计算异常，降级为平静状态。")


def snapshot() -> dict:
    """Latest market-driver attribution for latest.json["market_drivers"]."""
    try:
        frame = assemble_frame()
    except Exception as e:  # pragma: no cover - defensive, mirrors other leaves
        return {"verdict": "unknown", "headline": f"feature frame unavailable: {e}"}
    cfg = _cfg()
    proj_df, raw_z = projections(frame, cfg)
    if proj_df.empty:
        return {"verdict": "unknown", "headline": "no driver projections available"}
    day = proj_df.dropna(how="all").index[-1]
    ar = _absorption_pctile_series()
    ar_pctile = float(ar.get(day)) if day in ar.index and pd.notna(ar.get(day)) else None
    snap = classify_day(proj_df, raw_z, day, cfg, ar_pctile)
    # attach repricing_coherence block — load the log once, pass it in (pure)
    log_df = _load_log_df()
    snap["repricing_coherence"] = repricing_coherence(snap, log_df=log_df)
    return snap


def history(n: int = 20) -> list[dict]:
    """Last `n` days of attribution — for the preview harness / append-only log."""
    frame = assemble_frame()
    cfg = _cfg()
    proj_df, raw_z = projections(frame, cfg)
    proj_df = proj_df.dropna(how="all")
    ar = _absorption_pctile_series()
    # load the log once for all history rows (coherence uses it for driver_flip + p95)
    log_df = _load_log_df()
    out = []
    for day in proj_df.index[-n:]:
        arp = float(ar.get(day)) if day in ar.index and pd.notna(ar.get(day)) else None
        snap = classify_day(proj_df, raw_z, day, cfg, arp)
        snap["repricing_coherence"] = repricing_coherence(snap, log_df=log_df)
        out.append(snap)
    return out


def append_log(snap: dict, allow_write: bool = True) -> None:
    """Append today's verdict to an append-only log (keep-first per date) so the
    attribution can be GRADED later. Best-effort — never read back into a score,
    never breaks the build. See engine/alerts.py log_and_dedup for the pattern.

    PS-R7 guard: intraday callers MUST pass allow_write=False (the nightly path is
    the sole advancer of data/ ledgers). The default allow_write=True preserves the
    existing nightly call-sites unchanged.
    """
    if not allow_write:
        return  # PS-R7: intraday path must not write the parquet ledger
    try:
        if not snap or snap.get("verdict") in (None, "unknown") or not snap.get("asof"):
            return
        p = config.data_dir() / "regime" / "market_drivers_log.parquet"
        p.parent.mkdir(parents=True, exist_ok=True)
        asof = str(snap["asof"])
        old = pd.read_parquet(p) if p.exists() else None
        if old is not None and "asof" in old.columns and asof in set(old["asof"].astype(str)):
            return  # keep-first: already logged today
        row = {k: snap.get(k) for k in
               ("asof", "verdict", "primary", "direction", "dir_sign", "confidence",
                "strength", "dominance_ratio", "absorption_pctile")}
        row["evidence"] = "; ".join(snap.get("evidence") or [])
        # include coherence columns (None-safe; old rows without them are fine on read)
        coh = snap.get("repricing_coherence") or {}
        row["coherence_score"] = coh.get("score")
        row["coherence_state"] = coh.get("state")
        new = pd.DataFrame([row])
        out = pd.concat([old, new], ignore_index=True) if old is not None else new
        out.to_parquet(p, index=False)
    except Exception:
        pass
