"""Rate & inflation TRANSMISSION — the display-only cross-asset pass-through map.

A LEAF module: it imports nothing from the scoring core (regime/axes/conditions'
scored logic) and nothing in the scoring path imports it. It reads the shared causal
feature frame + the MEASURED coefficient matrix (data/transmission/calibration.json,
written by scripts/calibrate_rate_inflation.py) and assembles a structured read of how
the current interest-rate / rate-expectations / inflation (CPI, core PCE) state
propagates — first / second / third order — into per-asset-class headwind / tailwind,
plus honest conditional scenarios and an inflation decomposition.

DISCIPLINE — display / LLM-context ONLY, NEVER scored. The calibrator's scored-leg
gate (the same forward-drawdown bar the bond-health legs pass) found NO rate/inflation
leg robust enough to score (repricing is reactive; rate-of-change beats level; the
strongest leg — real-rate speed — is regime-dependent and fails purged-CV). So this
layer enlarges the facts a read can cite; it does not move any allocation. Every
pass-through coefficient is the split-half forward IC the calibrator measured, carried
with its verdict (CONFIRMED / DIRECTIONAL / CONTEXT / INVERTED) so the reader sees how
much to trust each link. Bilingual throughout. Additive, never fatal.
"""
from __future__ import annotations

import json
import logging

import numpy as np
import pandas as pd

from lib import config

log = logging.getLogger(__name__)

ZWIN = 504  # trailing window for the activation / level z-scores


# --------------------------------------------------------------------------- #
# DRIVERS — the rate/inflation state variables, RAW (interpretable units). Spearman
# IC is rank-invariant so the matrix is identical raw-vs-z; raw keeps the OLS beta in
# "return per unit driver" units for the scenarios. CAUSAL (only data <= t).
# --------------------------------------------------------------------------- #
def build_drivers(f: pd.DataFrame) -> pd.DataFrame:
    d = pd.DataFrame(index=f.index)
    H = 63
    d["real10y"] = f.get("us10y_real")
    d["real10y_chg63"] = f["us10y_real"] - f["us10y_real"].shift(H)
    d["nom10y_chg63"] = f["us10y"] - f["us10y"].shift(H)
    d["be10y"] = f.get("breakeven_10y")
    d["be10y_chg63"] = f["breakeven_10y"] - f["breakeven_10y"].shift(H)
    d["be5y5y"] = f.get("breakeven_5y5y")
    d["curve_tp_adj"] = f.get("curve_tp_adj")
    if "rate_expectations_proxy" in f:
        d["policy_gap"] = f["rate_expectations_proxy"]
    if "core_pce_yoy" in f:
        d["corepce_gap"] = f["core_pce_yoy"] - 2.0
        d["infl_accel"] = f["core_pce_3m_ann"] - f["core_pce_yoy"]
    if "breakeven_5y5y" in f and "infl_exp_5y" in f:
        d["exp_wedge"] = f["breakeven_5y5y"] - f["infl_exp_5y"]
    return d


# key -> (en, zh, kind). kind drives the activation read & UI unit.
DRIVERS_META = {
    "real10y": ("Real 10y yield (level)", "实际10年期收益率（水平）", "level"),
    "real10y_chg63": ("Real 10y — 63d change (speed)", "实际10年期收益率—63日变动（速度）", "change"),
    "nom10y_chg63": ("Nominal 10y — 63d change", "名义10年期收益率—63日变动", "change"),
    "be10y": ("10y breakeven (inflation comp.)", "10年期盈亏平衡通胀", "level"),
    "be10y_chg63": ("10y breakeven — 63d change", "10年期盈亏平衡—63日变动", "change"),
    "be5y5y": ("5y5y forward breakeven (anchor)", "5年5年远期盈亏平衡（锚）", "level"),
    "curve_tp_adj": ("TP-adjusted 2s10s curve", "期限溢价调整后的2-10年曲线", "level"),
    "policy_gap": ("us2y − funds (cut/hike pricing)", "2年期−联邦基金（降/加息定价）", "level"),
    "corepce_gap": ("Core PCE YoY − 2% target", "核心PCE同比−2%目标", "level"),
    "infl_accel": ("Inflation re-acceleration (3m−12m)", "通胀再加速（3月−12月）", "change"),
    "exp_wedge": ("Expectations wedge (mkt − model)", "预期缺口（市场−模型）", "level"),
}

# The drivers used in the LIVE headwind/tailwind read + chains: the CHANGE/shock and
# gap-vs-anchor drivers, which are the economically clean transmission inputs. The raw
# LEVEL drivers (real10y/be10y/be5y5y) stay in the full calibration matrix for
# transparency but are EXCLUDED here — their forward-return IC partly reflects spurious
# co-trend, and be10y level is mechanically collinear with the already-scored
# tips-nominal leg (the calibrator's VIF flags it). See the report for the full matrix.
READ_DRIVERS = {"real10y_chg63", "nom10y_chg63", "be10y_chg63", "curve_tp_adj",
                "policy_gap", "corepce_gap", "infl_accel", "exp_wedge"}

# ticker -> (en, zh, kind)
ASSETS_META = {
    "SPY": ("S&P 500", "标普500", "equity"),
    "QQQ": ("Nasdaq 100 (long-duration growth)", "纳斯达克100（长久期成长）", "equity"),
    "IWM": ("Russell 2000 (small caps)", "罗素2000（小盘）", "equity"),
    "XLK": ("Technology", "科技", "sector"),
    "XLU": ("Utilities (bond proxy)", "公用事业（类债券）", "sector"),
    "XLRE": ("Real Estate (rate-sensitive)", "房地产（利率敏感）", "sector"),
    "XLF": ("Financials (rate beneficiary)", "金融（利率受益）", "sector"),
    "XLE": ("Energy (inflation beneficiary)", "能源（通胀受益）", "sector"),
    "XLB": ("Materials (inflation beneficiary)", "材料（通胀受益）", "sector"),
    "XLP": ("Staples (defensive)", "必需消费（防御）", "sector"),
    "XLV": ("Health Care (defensive)", "医疗保健（防御）", "sector"),
    "GC=F": ("Gold", "黄金", "commodity"),
    "CL=F": ("Oil (WTI)", "原油(WTI)", "commodity"),
    "HG=F": ("Copper", "铜", "commodity"),
    "DX-Y.NYB": ("US Dollar (DXY)", "美元指数", "fx"),
    "BTC-USD": ("Bitcoin (long-duration)", "比特币（长久期）", "crypto"),
    "TLT": ("Long Treasuries (20y+)", "长期美债(20年+)", "bond"),
    "FXI": ("China large-cap (EM proxy)", "中国大盘（新兴市场代理）", "em"),
}

# --------------------------------------------------------------------------- #
# CHAINS — the first/second/third-order causal mechanism (descriptive narrative,
# like playbook.COMPONENT_PLAIN; bilingual). The engine annotates each order with the
# live measured cells for the chain's trigger driver + whether the trigger is active.
# --------------------------------------------------------------------------- #
CHAINS = [
    {"id": "real_rate", "trigger": "real10y_chg63",
     "title_en": "Real-rate / discount-rate channel", "title_zh": "实际利率／贴现率传导",
     "orders": [
        {"order": 1, "assets": ["QQQ", "XLK", "XLRE", "TLT", "BTC-USD"],
         "en": "Rising real 10y yields lift the discount rate → long-duration equities, REITs and other long-duration assets de-rate first.",
         "zh": "实际10年期收益率上行抬高贴现率→长久期股票、REITs等长久期资产首先承压。"},
        {"order": 2, "assets": ["DX-Y.NYB", "GC=F", "HG=F", "CL=F", "FXI"],
         "en": "Higher US real yields pull capital in → the dollar firms → gold, industrial commodities and EM are pressured.",
         "zh": "美国实际收益率走高吸引资本流入→美元走强→黄金、工业商品与新兴市场受压。"},
        {"order": 3, "assets": ["XLE", "XLB", "XLF"],
         "en": "A firm dollar + soft commodities → energy/materials relative headwind and EM-revenue exporters de-rate; financials are the relative beneficiary as curves steepen.",
         "zh": "强美元＋商品走软→能源/材料相对承压、新兴市场营收型出口商估值下修；曲线变陡时金融为相对受益者。"}]},
    {"id": "sticky_inflation", "trigger": "corepce_gap",
     "title_en": "Sticky-inflation / higher-for-longer channel", "title_zh": "通胀粘性／更高更久传导",
     "orders": [
        {"order": 1, "assets": ["SPY", "QQQ"],
         "en": "Core PCE/CPI stuck above the 2% target → the market reprices the terminal rate higher (breakevens, policy path) → broad equities carry a valuation headwind.",
         "zh": "核心PCE/CPI高于2%目标→市场上修终端利率（盈亏平衡、政策路径）→大盘股估值承压。"},
        {"order": 2, "assets": ["IWM", "XLF"],
         "en": "Higher-for-longer keeps real yields elevated → small caps and rate-sensitive borrowers are squeezed by financing cost.",
         "zh": "更高更久使实际收益率维持高位→小盘股与利率敏感借款方被融资成本挤压。"},
        {"order": 3, "assets": ["XLP", "XLV"],
         "en": "PPI / ECI wage pressure compresses margins → defensives (staples, health care) relatively outperform.",
         "zh": "PPI／就业成本（ECI）工资压力压缩利润率→防御板块（必需消费、医疗）相对跑赢。"}]},
    {"id": "policy_easing", "trigger": "curve_tp_adj",
     "title_en": "Policy-easing / curve-steepening channel", "title_zh": "政策宽松／曲线变陡传导",
     "orders": [
        {"order": 1, "assets": ["TLT"],
         "en": "Cuts priced (policy gap negative) → the front end falls and the curve bull-steepens → duration rallies.",
         "zh": "计入降息（政策缺口为负）→短端下行、曲线牛市变陡→久期资产上涨。"},
        {"order": 2, "assets": ["XLF", "XLRE"],
         "en": "A steeper curve → bank net-interest margins and rate-sensitive REITs/housing improve.",
         "zh": "曲线变陡→银行净息差与利率敏感的REITs/地产改善。"},
        {"order": 3, "assets": ["IWM", "XLB"],
         "en": "Easier financial conditions → small caps and cyclicals lead a risk-on rotation.",
         "zh": "金融条件转松→小盘与周期股领涨的风险偏好轮动。"}]},
    {"id": "expectations", "trigger": "exp_wedge",
     "title_en": "Inflation-expectations (anchoring) channel", "title_zh": "通胀预期（锚定）传导",
     "orders": [
        {"order": 1, "assets": ["DX-Y.NYB", "GC=F"],
         "en": "Market inflation expectations drift above the model/survey → unanchoring risk; the dollar firms as the Fed is expected to stay restrictive. Counter-intuitively, gold's MEASURED response to this wedge is a headwind — the higher real yields from a restrictive Fed dominate the inflation-hedge bid.",
         "zh": "市场通胀预期高于模型/调查→脱锚风险；美元因预期美联储维持紧缩而走强。与直觉相反，黄金对此缺口的实测反应为逆风——紧缩带来的更高实际收益率压过了通胀对冲买盘。"},
        {"order": 2, "assets": ["QQQ", "XLV"],
         "en": "Unanchoring → the Fed stays restrictive → real yields rise; long-duration growth de-rates while defensives are relatively favored.",
         "zh": "脱锚→美联储维持紧缩→实际收益率上行；长久期成长下修，防御相对受青睐。"},
        {"order": 3, "assets": ["XLE", "XLB"],
         "en": "The textbook 'real-asset hedge' (energy, materials, gold) is unreliable for this wedge: with the Fed held restrictive, the measured beneficiaries are the dollar and defensives, not the inflation-beneficiary sectors.",
         "zh": "教科书式的“实物资产对冲”（能源、材料、黄金）对此缺口并不可靠：在美联储维持紧缩下，实测受益者是美元与防御板块，而非通胀受益板块。"}]},
]


# --------------------------------------------------------------------------- #
# helpers
# --------------------------------------------------------------------------- #
def _z(s: pd.Series, win: int = ZWIN) -> pd.Series:
    return (s - s.rolling(win, min_periods=126).mean()) / s.rolling(win, min_periods=126).std()


def _last(s: pd.Series):
    s = s.dropna()
    return float(s.iloc[-1]) if len(s) else None


def _pctile(s: pd.Series, lookback: int = 1260) -> float | None:
    s = s.dropna()
    if len(s) < 60:
        return None
    win = s.iloc[-lookback:]
    return round(float((win <= win.iloc[-1]).mean()), 2)


def load_calibration() -> dict | None:
    p = config.data_dir() / "transmission" / "calibration.json"
    try:
        return json.loads(p.read_text()) if p.exists() else None
    except Exception as e:  # noqa: BLE001
        log.warning("transmission calibration unreadable: %s", e)
        return None


def _bil(en: str, zh: str) -> dict:
    return {"en": en, "zh": zh}


# --------------------------------------------------------------------------- #
# current STATE
# --------------------------------------------------------------------------- #
def current_state(f: pd.DataFrame) -> dict:
    real = _last(f.get("us10y_real", pd.Series(dtype=float)))
    real_pct = _pctile(f["us10y_real"]) if "us10y_real" in f else None
    real_chg = (_last(f["us10y_real"]) - _last(f["us10y_real"].shift(63))
                if "us10y_real" in f and len(f["us10y_real"].dropna()) > 63 else None)
    rate_regime = ("restrictive" if (real_pct or 0) >= 0.70 else
                   "accommodative" if (real_pct is not None and real_pct <= 0.30) else "neutral")
    rate_dir = ("rising" if (real_chg or 0) > 0.1 else "falling" if (real_chg or 0) < -0.1 else "stable")

    core_pce = _last(f.get("core_pce_yoy", pd.Series(dtype=float)))
    core_pce_3m = _last(f.get("core_pce_3m_ann", pd.Series(dtype=float)))
    accel = (core_pce_3m - core_pce) if (core_pce is not None and core_pce_3m is not None) else None
    infl_regime = ("above target" if (core_pce or 0) > 2.3 else
                   "at target" if (core_pce is not None and core_pce <= 2.3 and core_pce >= 1.7) else "below target")
    infl_dir = ("re-accelerating" if (accel or 0) > 0.2 else "cooling" if (accel or 0) < -0.2 else "steady")

    be10 = _last(f.get("breakeven_10y", pd.Series(dtype=float)))
    be55 = _last(f.get("breakeven_5y5y", pd.Series(dtype=float)))
    model5 = _last(f.get("infl_exp_5y", pd.Series(dtype=float)))
    survey1 = _last(f.get("umich_infl_exp", pd.Series(dtype=float)))
    wedge = (be55 - model5) if (be55 is not None and model5 is not None) else None
    anchoring = ("drifting up" if (wedge or 0) > 0.3 else "drifting down" if (wedge or 0) < -0.3 else "anchored")

    return {
        "rates": {
            "real_10y": round(real, 2) if real is not None else None,
            "real_10y_pctile": real_pct,
            "real_10y_chg_63d_bp": round(real_chg * 100, 0) if real_chg is not None else None,
            "nominal_10y": round(_last(f.get("us10y", pd.Series(dtype=float))) or 0, 2) if "us10y" in f else None,
            "curve_2s10s": round(_last(f.get("spread_2s10s", pd.Series(dtype=float))) or 0, 2) if "spread_2s10s" in f else None,
            "curve_tp_adj": round(_last(f.get("curve_tp_adj", pd.Series(dtype=float))) or 0, 2) if "curve_tp_adj" in f else None,
            "policy_gap": round(_last(f.get("rate_expectations_proxy", pd.Series(dtype=float))) or 0, 2) if "rate_expectations_proxy" in f else None,
            "regime": rate_regime, "direction": rate_dir,
            "label": _bil(f"Real 10y {real:.2f}% ({rate_regime}, {rate_dir})" if real is not None else "—",
                          f"实际10年期 {real:.2f}%（{ {'restrictive':'偏紧','accommodative':'宽松','neutral':'中性'}.get(rate_regime, rate_regime) }）" if real is not None else "—"),
        },
        "inflation": {
            "core_pce_yoy": round(core_pce, 2) if core_pce is not None else None,
            "core_cpi_yoy": round(_last(f.get("core_cpi_yoy", pd.Series(dtype=float))) or 0, 2) if "core_cpi_yoy" in f else None,
            "headline_cpi_yoy": round(_last(f.get("headline_cpi_yoy", pd.Series(dtype=float))) or 0, 2) if "headline_cpi_yoy" in f else None,
            "core_pce_3m_ann": round(core_pce_3m, 2) if core_pce_3m is not None else None,
            "ppi_core_yoy": round(_last(f.get("ppi_core_yoy", pd.Series(dtype=float))) or 0, 2) if "ppi_core_yoy" in f else None,
            "eci_comp_yoy": round(_last(f.get("eci_comp_yoy", pd.Series(dtype=float))) or 0, 2) if "eci_comp_yoy" in f else None,
            "vs_target_pp": round(core_pce - 2.0, 2) if core_pce is not None else None,
            "regime": infl_regime, "direction": infl_dir,
            "label": _bil(f"Core PCE {core_pce:.1f}% ({infl_regime}, {infl_dir})" if core_pce is not None else "—",
                          f"核心PCE {core_pce:.1f}%（{ {'above target':'高于目标','at target':'达标','below target':'低于目标'}.get(infl_regime, infl_regime) }）" if core_pce is not None else "—"),
        },
        "expectations": {
            "breakeven_10y": round(be10, 2) if be10 is not None else None,
            "breakeven_5y5y": round(be55, 2) if be55 is not None else None,
            "model_5y": round(model5, 2) if model5 is not None else None,
            "survey_1y": round(survey1, 2) if survey1 is not None else None,
            "market_minus_model_bp": round(wedge * 100, 0) if wedge is not None else None,
            "anchoring": anchoring,
            "label": _bil(f"5y5y breakeven {be55:.2f}% vs model {model5:.2f}% ({anchoring})" if (be55 is not None and model5 is not None) else "—",
                          f"5年5年盈亏平衡 {be55:.2f}% vs 模型 {model5:.2f}%（{ {'drifting up':'上行脱锚','drifting down':'下行','anchored':'锚定'}.get(anchoring, anchoring) }）" if (be55 is not None and model5 is not None) else "—"),
        },
    }


def inflation_decomposition(f: pd.DataFrame) -> dict:
    def g(c):
        return _last(f.get(c, pd.Series(dtype=float)))
    headline, core = g("headline_cpi_yoy"), g("core_cpi_yoy")
    coreserv, shelter = g("cpi_core_services_yoy"), g("cpi_shelter_yoy")
    core_pce, core_cpi = g("core_pce_yoy"), g("core_cpi_yoy")
    be10 = g("breakeven_10y")
    return {
        "headline_minus_core": round(headline - core, 2) if (headline is not None and core is not None) else None,
        "food_energy_note": _bil("headline above core = food/energy adding; below = subtracting",
                                  "整体高于核心＝食品/能源在推升；低于＝在拖累"),
        "core_services_yoy": round(coreserv, 2) if coreserv is not None else None,
        "shelter_yoy": round(shelter, 2) if shelter is not None else None,
        "services_minus_shelter": round(coreserv - shelter, 2) if (coreserv is not None and shelter is not None) else None,
        "pce_minus_cpi": round(core_pce - core_cpi, 2) if (core_pce is not None and core_cpi is not None) else None,
        "actual_vs_market_bp": round((core_cpi - be10) * 100, 0) if (core_cpi is not None and be10 is not None) else None,
        "actual_vs_market_note": _bil("realized core CPI vs the 10y breakeven the market prices",
                                      "已实现核心CPI vs 市场定价的10年期盈亏平衡"),
    }


# --------------------------------------------------------------------------- #
# current per-asset transmission (measured cells x current driver activation)
# --------------------------------------------------------------------------- #
def transmission_read(f: pd.DataFrame, cal: dict, cfg: dict) -> dict:
    if not cal or "transmission_matrix" not in cal:
        return {}
    drivers = build_drivers(f)
    act = {k: _last(_z(drivers[k])) for k in drivers.columns if drivers[k].notna().any()}
    z_cap = cfg.get("z_cap", 2.5)
    min_ic = cfg.get("min_ic", 0.04)
    cut = cfg.get("effect_cut", 0.06)
    mat = cal["transmission_matrix"]
    out = {}
    for tkr, (en, zh, kind) in ASSETS_META.items():
        net = 0.0
        parts = []
        for drv, dd in mat.items():
            if drv not in READ_DRIVERS:               # levels excluded from the live read (co-trend)
                continue
            cell = dd.get("assets", {}).get(tkr)
            if not cell:
                continue
            ic = cell.get("ic")
            verdict = cell.get("verdict")
            az = act.get(drv)
            if ic is None or az is None or abs(ic) < min_ic or verdict in ("CONTEXT", "UNMEASURED"):
                continue
            azc = max(-z_cap, min(z_cap, az))
            c = ic * (azc / z_cap)                      # contribution in [-|ic|, |ic|]
            net += c
            parts.append({"driver": drv, "label": DRIVERS_META.get(drv, (drv, drv, ""))[0],
                          "ic": ic, "activation_z": round(az, 2),
                          "contribution": round(c, 3), "verdict": verdict})
        parts.sort(key=lambda p: -abs(p["contribution"]))
        verdict = "headwind" if net < -cut else "tailwind" if net > cut else "neutral"
        out[tkr] = {"label": _bil(en, zh), "kind": kind, "net": round(net, 3),
                    "verdict": verdict, "top_drivers": parts[:3]}
    return out


def _annotate_chains(cal: dict, f: pd.DataFrame) -> list:
    drivers = build_drivers(f)
    act = {k: _last(_z(drivers[k])) for k in drivers.columns if drivers[k].notna().any()}
    mat = (cal or {}).get("transmission_matrix", {})
    out = []
    for ch in CHAINS:
        trig = ch["trigger"]
        az = act.get(trig)
        active = az is not None and abs(az) >= 0.7
        sign = "up" if (az or 0) > 0 else "down"
        orders = []
        for o in ch["orders"]:
            cells = []
            for a in o["assets"]:
                cell = mat.get(trig, {}).get("assets", {}).get(a, {})
                cells.append({"asset": a, "label": ASSETS_META.get(a, (a, a, ""))[0],
                              "ic": cell.get("ic"), "effect": cell.get("effect", "—"),
                              "verdict": cell.get("verdict", "UNMEASURED")})
            orders.append({"order": o["order"], "text": _bil(o["en"], o["zh"]), "assets": cells})
        out.append({"id": ch["id"], "title": _bil(ch["title_en"], ch["title_zh"]),
                    "trigger": trig, "trigger_label": DRIVERS_META.get(trig, (trig, trig, ""))[0],
                    "active": bool(active), "trigger_z": round(az, 2) if az is not None else None,
                    "trigger_dir": sign, "orders": orders})
    return out


def scenarios(f: pd.DataFrame, cal: dict, cfg: dict) -> list:
    """Display-only conditional projections: per-asset implied 63d move under a shock,
    using the MEASURED CONTEMPORANEOUS beta (asset 63d return vs same-window driver
    change). Caveated as illustrative & regime-dependent — never a forecast, never
    scored."""
    sb = (cal or {}).get("scenario_betas", {})
    out = []
    for sc in cfg.get("scenarios", []):
        drv = sc["driver"]
        shock = sc["shock_bp"] / 100.0                  # bp -> driver units (pp)
        betas = sb.get(drv, {})
        moves = []
        for tkr, beta in betas.items():
            if beta is None:
                continue
            mv = beta * shock
            if abs(mv) < 0.005:                          # ignore <0.5% implied moves
                continue
            moves.append({"asset": tkr, "label": ASSETS_META.get(tkr, (tkr, tkr, ""))[0],
                          "implied_move_pct": round(mv * 100, 1)})
        moves.sort(key=lambda m: m["implied_move_pct"])
        out.append({"key": sc["key"], "label": _bil(sc["label_en"], sc["label_zh"]),
                    "shock_bp": sc["shock_bp"], "driver": drv,
                    "driver_label": DRIVERS_META.get(drv, (drv, drv, ""))[0],
                    "headwinds": [m for m in moves if m["implied_move_pct"] < 0][:5],
                    "tailwinds": [m for m in moves if m["implied_move_pct"] > 0][-5:][::-1]})
    return out


CAVEATS = [
    _bil("Display-only — never scored. The repricing of rates/inflation is REACTIVE; the curve moves after the data and the Fed, it does not lead them.",
         "仅供展示，从不计入评分。利率/通胀的重新定价是被动的；曲线在数据与美联储之后变动，而非领先。"),
    _bil("Rate-of-change beats level: the SPEED of a real-yield move breaks equities more than its level. Coefficients are the measured forward IC, not a promise.",
         "变动速度比水平更重要：实际收益率移动的速度比其水平更能冲击股票。系数为已测得的前瞻IC，并非承诺。"),
    _bil("Scenario moves apply a historical beta to a hypothetical shock — they are regime-dependent illustrations, not predictions, and assume the shock persists one quarter.",
         "情景中的涨跌幅是将历史beta应用于假设冲击——属于依赖状态的示意而非预测，且假设冲击持续一个季度。"),
    _bil("The real / nominal / breakeven 63d-change drivers are mechanically collinear (real = nominal − breakeven); do not treat them as independent confirmations.",
         "实际／名义／盈亏平衡的63日变动驱动在机制上共线（实际＝名义−盈亏平衡）；不应视为相互独立的印证。"),
]


def snapshot(f: pd.DataFrame) -> dict | None:
    cfg = config.load().get("transmission") or {}
    if not cfg.get("enabled", True):
        return None
    cal = load_calibration()
    state = current_state(f)
    read = transmission_read(f, cal, cfg)
    headwinds = sorted([{"asset": k, **v} for k, v in read.items() if v["verdict"] == "headwind"],
                       key=lambda x: x["net"])[:6]
    tailwinds = sorted([{"asset": k, **v} for k, v in read.items() if v["verdict"] == "tailwind"],
                       key=lambda x: -x["net"])[:6]
    sg = (cal or {}).get("scored_gate", {})
    elig = [k for k, s in sg.items() if s.get("scored_eligible")]
    return {
        "asof": str(f.index[-1].date()),
        "state": state,
        "inflation_decomposition": inflation_decomposition(f),
        "transmission": read,
        "headwinds": headwinds,
        "tailwinds": tailwinds,
        "chains": _annotate_chains(cal, f),
        "scenarios": scenarios(f, cal, cfg),
        "scored_status": _bil(
            f"Display-only. Scored-leg gate: {', '.join(elig) if elig else 'NO rate/inflation leg passed the forward-drawdown bar with purged-CV robustness'} "
            "(see reports/rate-inflation-transmission-calibration.md).",
            f"仅供展示。可计分腿检验：{'，'.join(elig) if elig else '没有任何利率/通胀腿通过前瞻回撤门槛并满足清洗交叉验证稳健性'}（详见校准报告）。"),
        "caveats": CAVEATS,
        "calibrated": cal is not None,
    }
