"""China Mastermind multi-asset GTAA — three active, conviction-weighted, vol-targeted
tactical asset-allocation flagships (Conservative / Moderate / Aggressive), restricted to the
MAINLAND-INVESTIBLE universe (A-share ETFs + onshore gold + China govt bonds; NO crypto,
NO US treasuries, NO US stocks).

The China sibling of engine/masterminds.py. It REUSES the asset-agnostic harness
(engine.active_alloc.backtest_portfolio / split_half_oos) and the price-orthogonal China
edges the validated china_strategies registry already ships — the credit IMPULSE (TSF),
margin-leverage euphoria, and the realized-vol regime — because A-shares mean-revert and
naive price-trend WHIPSAWS here (engine.china_allocation / china_strategies docstrings). So
the conviction DOWN-weights trend (0.30 vs the US 0.45) and leans on the diversification +
credit/vol REGIME layer (0.40).

Universe (asset -> class):
  EQ_BROAD  510300.SS  CSI 300            broad A-share, the benchmark
  EQ_GROWTH 159915.SZ  ChiNext            growth kicker
  INCOME    510880.SS  SSE Dividend       defensive-equity carry (2008->)
  BOND      511010.SS  5y CGB ETF         China govt duration (the only onshore govt-bond ETF)
  GOLD      518880.SS  onshore Gold ETF   SGE-linked RMB gold
  COMMOD    512400.SS  Nonferrous Metals  copper/aluminium producer equity — the China-holdable
                                          commodity proxy (a Mainland investor cannot easily hold
                                          a broad-commodity future; this carries embedded equity beta)

Sizing (shared with US masterminds): per-asset inverse-vol (risk parity) -> conviction tilt ->
per-name cap -> scale the book to the profile target vol -> leverage cap -> weekly rebalance.
Vol targets + leverage are deliberately ONE NOTCH BELOW the US flagships (A-shares are more
volatile + mean-reverting). Cash sleeve = flat ~1.8% (onshore cash earns little — de-risking
here is a drawdown trade, not a carry trade).

DISPLAY-ONLY / experimental: a NEW scored multi-asset book on PRIORS-based knobs (calibration
is a fast-follow, mirroring how Canada/TSX shipped). Net of 3 bps + 1% financing on the levered
part; weekly rebalance. Benchmark = CSI 300 buy-&-hold (and a China 40/60 equity/bond for the
conservative tier). The OOS split-half honesty panel is wired through aa.split_half_oos.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from engine import active_alloc as aa
from engine.china_strategies import (CHINA_CASH_PCT, _cnclose, _credit_derisk,
                                      _margin_derisk, _vol_derisk)
from engine.cross_asset_trend import tsmom_alloc

# universe (asset -> class); income/bond/gold are the carry-bearing defensive sleeves
EQ_BROAD, EQ_GROWTH, INCOME = ["510300.SS"], ["159915.SZ"], ["510880.SS"]
BOND, GOLD, COMMOD = ["511010.SS"], ["518880.SS"], ["512400.SS"]
ASSETS = EQ_BROAD + EQ_GROWTH + INCOME + BOND + GOLD + COMMOD
RISKY = ["510300.SS", "159915.SZ", "512400.SS"]
SAFE = ["511010.SS", "518880.SS", "510880.SS"]
ASSET_LABEL = {
    "510300.SS": ("CSI 300", "沪深300"), "159915.SZ": ("ChiNext (growth)", "创业板（成长）"),
    "510880.SS": ("SSE Dividend", "上证红利"), "511010.SS": ("China 5y Govt Bond", "5年国债"),
    "518880.SS": ("Gold (onshore)", "黄金"), "512400.SS": ("Nonferrous Metals", "有色金属"),
}
# structural carry tilt (constant) for the income/bond/gold sleeves — China lacks a clean
# tradable yield-curve series for a time-varying carry leg, so the carry factor is a small
# steady tilt toward the carry/store-of-value holdings (the diversifying sleeves).
STRUCT_CARRY = {"510880.SS": 0.5, "511010.SS": 0.5, "518880.SS": 0.25}

PROFILES: dict[str, dict] = {
    "conservative": {"target_vol": 0.05, "max_lev": 1.0, "w_cap": 0.35, "icon": "🛟",
                     "label_en": "Conservative", "label_zh": "保守", "bench": "cn6040",
                     "goal_en": "Preserve capital", "goal_zh": "保全资本",
                     "thesis_en": "Capital-preservation GTAA across A-shares, China bonds & gold — no leverage, diversified, leans on the credit-impulse & vol regime, not price trend.",
                     "thesis_zh": "横跨 A 股、国债与黄金的资本保全型全球配置——零杠杆、分散，依靠信用脉冲与波动率体制，而非价格趋势。",
                     "blurb_en": "The risk dials are turned all the way down: a low 5% target volatility, NO leverage (1.0× cap) and a 35% per-name limit force broad diversification across A-shares, China govt bonds and gold. The goal is not to win the next A-share rally — it is to compound through China's violent boom-bust cycles with a fraction of the drawdown, beating a China 40/60 (CSI 300 / govt bond) portfolio on risk-adjusted terms.",
                     "blurb_zh": "风险旋钮全部调到最低：5% 的低目标波动率、零杠杆（1.0× 上限）、35% 单一上限，强制在 A 股、国债与黄金间广泛分散。目标不是赢下下一轮 A 股行情——而是以极小的回撤穿越中国剧烈的繁荣-萧条周期复利增长，在风险调整后跑赢中国 40/60（沪深300 / 国债）组合。"},
    "moderate": {"target_vol": 0.09, "max_lev": 1.3, "w_cap": 0.40, "icon": "⚖️",
                 "label_en": "Moderate", "label_zh": "均衡", "bench": "csi300",
                 "goal_en": "Balanced growth", "goal_zh": "均衡增长",
                 "thesis_en": "Balanced China GTAA — the full A-share + bond + gold + metals book, lightly levered to the highest-conviction sleeves; aims to beat CSI 300 on risk-adjusted return with a far shallower drawdown.",
                 "thesis_zh": "均衡型中国全球配置——A 股＋国债＋黄金＋有色的完整组合，对最高信念的资产轻杠杆；力求在风险调整后收益上跑赢沪深300，回撤浅得多。",
                 "blurb_en": "The balanced setting: a 9% target volatility, up to 1.3× leverage and a 40% per-name cap. It aims to beat CSI 300's long-run return while taking far less risk to get it — leaning on the credit / vol / margin regime rather than chasing price trend, for several times the index's Sharpe at well under half its worst drawdown. The flagship default.",
                 "blurb_zh": "均衡设定：9% 目标波动率、最高 1.3× 杠杆、40% 单一上限。目标是在承担远更低风险的前提下跑赢沪深300 的长期收益——靠信用／波动率／融资体制而非追逐价格趋势，换来数倍于指数的夏普、且最大回撤远不到其一半。旗舰默认档。"},
    "aggressive": {"target_vol": 0.15, "max_lev": 1.8, "w_cap": 0.50, "icon": "🚀",
                   "label_en": "Aggressive", "label_zh": "进取", "bench": "csi300",
                   "goal_en": "Maximum growth", "goal_zh": "增长最大化",
                   "thesis_en": "Maximum-growth China GTAA — levers the strongest A-share / metals trends while the credit & vol regime allows, rotating hard to bonds + gold when it flips to de-risk.",
                   "thesis_zh": "增长最大化中国全球配置——在信用与波动率体制许可时，对最强的 A 股／有色趋势加杠杆；体制转为降险时则大举转向国债与黄金。",
                   "blurb_en": "The dials are opened up: a 15% target volatility, up to 1.8× leverage and a 50% per-name cap let the book lever the strongest A-share and metals trends WHILE the credit & vol regime allows — then rotate hard into China govt bonds and gold the moment it flips to de-risk. Built to out-compound CSI 300 on raw CAGR at a Sharpe still well above the index. The vol target and leverage are deliberately one notch below the US flagship — A-shares are more volatile and mean-reverting.",
                   "blurb_zh": "旋钮全部打开：15% 目标波动率、最高 1.8× 杠杆、50% 单一上限，让组合在信用与波动率体制许可时，对最强的 A 股与有色趋势加杠杆——一旦转为降险便立即大举转向国债与黄金。旨在以原始年化跑赢沪深300，而夏普仍远高于指数。波动率目标与杠杆刻意比美国旗舰低一档——A 股更波动、更易均值回归。"},
}
DEFAULT_PROFILE = "moderate"
_START = pd.Timestamp("2013-08-01")        # CGB(2013-03) + gold(2013-07) spine live
_REBAL = 5                                 # weekly rebalance (trading days)
_LAG = 2
_LAG_CREDIT = 22                           # ~1-month publication lag on the monthly TSF print
W_TREND, W_CARRY, W_REGIME, W_XMOM = 0.30, 0.15, 0.40, 0.15
# within-REGIME leg weights (sum→1 over whichever legs resolve) — single source of truth for
# both _derisk_score() and the live regime_state() transparency panel.
_DERISK_W = {"credit": 0.45, "vol": 0.35, "margin": 0.20}

# ─────────────────────────────────────────────────────────────────────────────
# Strategy-detail metadata — single source of truth for the "how it works" explainer
# on the per-profile flagship pages (strategy_cnmm_*.html). The China sibling of the
# block in engine.masterminds, but tuned to the CHINA model: trend is down-weighted and
# the price-orthogonal credit/vol/margin REGIME carries the largest weight. Kept next to
# the live weights so any change to the math flows straight to the page.
# ─────────────────────────────────────────────────────────────────────────────
# The four conviction factors (ordered by weight — regime first, the China-distinctive one).
FACTORS: list[dict] = [
    {"key": "regime", "weight": W_REGIME, "icon": "🚦",
     "name_en": "Regime", "name_zh": "体制", "tag_en": "the China engine", "tag_zh": "中国引擎",
     "desc_en": "The largest weight and the China-specific heart of the book — a price-orthogonal de-risk signal from three slow, fundamentals-based gauges: the credit impulse (TSF), retail margin-leverage euphoria and CSI 300 realized volatility. When they flash risk-off it fades A-shares & metals into govt bonds, dividend and gold. It carries far more weight here (0.40 vs the US flagship's 0.20) because A-shares are driven by the credit cycle and liquidity, not earnings trends.",
     "desc_zh": "权重最大、也是本组合中国特定的核心——一个与价格正交的降险信号，源自三个慢节奏、基本面驱动的指标：信用脉冲（社融）、散户融资杠杆狂热、以及沪深300已实现波动率。当它们转为风险偏离时，将 A 股与有色减配至国债、红利与黄金。其权重在此远高于美国旗舰（0.40 对 0.20），因为 A 股由信用周期与流动性驱动，而非盈利趋势。",
     "src_en": "TSF impulse · margin/float · 21d realized vol", "src_zh": "社融脉冲 · 融资/流通市值 · 21日已实现波动率"},
    {"key": "trend", "weight": W_TREND, "icon": "📈",
     "name_en": "Trend", "name_zh": "趋势", "tag_en": "down-weighted here", "tag_zh": "此处降权",
     "desc_en": "Multi-horizon time-series momentum on each asset — is it trending up across the 1-to-12-month lookbacks? It is the workhorse of the US flagship but deliberately DOWN-weighted here (0.30 vs 0.45): A-shares mean-revert and whipsaw naive price-trend timers, so trend is a contributor, not the captain.",
     "desc_zh": "对每个资产的多周期时间序列动量——在 1 至 12 个月回看窗口中是否上行？它是美国旗舰的主力，但在此被刻意下调权重（0.30 对 0.45）：A 股均值回归、会让朴素的价格趋势择时频繁打脸，因此趋势是贡献者而非主角。",
     "src_en": "Price · TSMOM (1–12m)", "src_zh": "价格 · TSMOM（1–12月）"},
    {"key": "carry", "weight": W_CARRY, "icon": "💰",
     "name_en": "Carry", "name_zh": "套息", "tag_en": "structural tilt", "tag_zh": "结构性倾斜",
     "desc_en": "A steady structural tilt toward the income-bearing, store-of-value sleeves — SSE Dividend, the 5-year China govt bond and onshore gold. China lacks a clean tradable yield-curve series for a time-varying carry leg, so this is a constant lean toward the diversifiers rather than a live yield signal.",
     "desc_zh": "对生息、价值储藏型资产的稳定结构性倾斜——上证红利、5 年期国债与境内黄金。中国缺乏可交易的干净收益率曲线序列以构建时变套息腿，因此这是对分散资产的恒定倾斜，而非实时收益率信号。",
     "src_en": "Static tilt: dividend · CGB · gold", "src_zh": "静态倾斜：红利 · 国债 · 黄金"},
    {"key": "xmom", "weight": W_XMOM, "icon": "🔀",
     "name_en": "Cross-asset momentum", "name_zh": "跨资产动量", "tag_en": "ride the leaders", "tag_zh": "追随领先者",
     "desc_en": "Relative 6-month momentum ACROSS the six sleeves — overweight whatever has been leading, underweight the laggards. Captures the rotations between A-shares, bonds, gold and metals that single-asset trend alone misses.",
     "desc_zh": "六个资产之间的相对 6 个月动量——超配领先者、低配落后者。捕捉 A 股、国债、黄金与有色之间单资产趋势本身会错过的轮动。",
     "src_en": "126-day relative rank", "src_zh": "126日相对排名"},
]

# The six-asset Mainland-investible universe, grouped by class; row = (ticker, role_en, role_zh).
UNIVERSE: list[dict] = [
    {"cls_en": "A-share equity", "cls_zh": "A股股票", "icon": "📈",
     "rows": [("CSI 300", "Broad A-share beta — the benchmark", "A股大盘贝塔 — 基准"),
              ("ChiNext", "Growth / high-beta kicker", "成长 / 高贝塔加速器")]},
    {"cls_en": "Dividend equity", "cls_zh": "红利股票", "icon": "💴",
     "rows": [("SSE Dividend", "Defensive high-dividend A-shares — equity carry", "防御型高股息 A 股 — 股票套息")]},
    {"cls_en": "Govt bonds", "cls_zh": "国债", "icon": "🏛️",
     "rows": [("5y CGB ETF", "China 5-year govt bond — the duration ballast", "5年期国债 — 久期压舱石")]},
    {"cls_en": "Real assets", "cls_zh": "实物资产", "icon": "🪙",
     "rows": [("Gold (onshore)", "SGE-linked RMB gold — store of value", "上海金 RMB 黄金 — 价值储藏"),
              ("Nonferrous Metals", "Copper/aluminium producers — China-holdable cyclical", "铜/铝生产商 — 境内可投周期品")]},
]

# The weekly sizing pipeline — how a raw conviction score becomes a live position.
PIPELINE: list[dict] = [
    {"icon": "🧮", "en": "Score all six assets 0→1 on the four-factor conviction (regime-led)",
     "zh": "用四因子信念为全部六个资产打分（0→1，体制主导）"},
    {"icon": "⚖️", "en": "Size by inverse volatility (risk parity) — calmer assets get more",
     "zh": "按波动率倒数定仓（风险平价）——更平静的资产权重更大"},
    {"icon": "🎯", "en": "Tilt by conviction — the strongest signals are scaled up",
     "zh": "按信念倾斜——最强信号被加码"},
    {"icon": "🧢", "en": "Cap each name at the profile's per-name limit",
     "zh": "每个标的设单一上限（按风险档）"},
    {"icon": "📐", "en": "Scale the whole book to the profile's target volatility",
     "zh": "将整个组合缩放至风险档的目标波动率"},
    {"icon": "🔧", "en": "Cap total leverage, hold one week, repeat — idle cash earns ~1.8%",
     "zh": "限制总杠杆，持有一周后重复——闲置现金约 1.8%"},
]


def _prices() -> pd.DataFrame:
    px = {}
    for a in ASSETS:
        s = _cnclose(a)
        s = s[s > 0]
        if not s.empty:
            px[a] = s
    if "510300.SS" not in px or "511010.SS" not in px or "518880.SS" not in px:
        return pd.DataFrame()
    core = ("510300.SS", "511010.SS", "518880.SS")
    cal = px[core[0]].index.union(px[core[1]].index).union(px[core[2]].index)
    cal = cal[(cal >= _START) & (cal <= min(px[a].index[-1] for a in core))]
    return pd.DataFrame({a: px[a].reindex(cal).ffill() for a in px}, index=cal)


def _derisk_legs(cal: pd.Index) -> list[tuple[str, pd.Series, float]]:
    """The validated China de-risk legs as (key, series-on-cal, weight) — only those that
    resolve. Lags match what the book actually trades on (credit ~1 month, vol/margin 1 day).
    Shared by _derisk_score() and the live regime_state() panel so they never drift."""
    out: list[tuple[str, pd.Series, float]] = []
    specs = (("credit", _credit_derisk, _LAG_CREDIT),
             ("vol", lambda: _vol_derisk(_cnclose("510300.SS")), 1),
             ("margin", _margin_derisk, 1))
    for key, fn, lag in specs:
        try:
            s = fn()
        except Exception:  # noqa: BLE001
            continue
        if s is not None and not s.empty:
            out.append((key, s.reindex(cal, method="ffill").shift(lag), _DERISK_W[key]))
    return out


def _derisk_score(cal: pd.Index) -> pd.Series | None:
    """Blend the validated China de-risk legs (credit impulse / realized vol / margin
    euphoria) into one [0,1] series on the price calendar (1 = de-risk). Weighted mean of
    whichever legs have data on each date; None if none resolve."""
    legs = _derisk_legs(cal)
    if not legs:
        return None
    num = pd.Series(0.0, index=cal)
    den = pd.Series(0.0, index=cal)
    for _key, s, w in legs:
        present = s.notna()
        num = num.add((s.fillna(0.0) * w).where(present, 0.0), fill_value=0.0)
        den = den.add(pd.Series(np.where(present, w, 0.0), index=cal), fill_value=0.0)
    return (num / den.replace(0, np.nan)).clip(0, 1)


# Per-leg copy for the live regime panel (names + the data source behind each gauge).
_LEG_META = {
    "credit": {"name_en": "Credit impulse", "name_zh": "信用脉冲",
               "src_en": "TSF 12m-sum YoY · 6m change · 36m rank", "src_zh": "社融12月累计同比·6月变化·36月排名",
               "desc_en": "Total Social Financing — China's broadest credit aggregate. The 6-month change of credit growth, ranked over 36 months. High = credit is contracting → de-risk.",
               "desc_zh": "社会融资规模——中国最广义的信用总量。信用增速的6个月变化、按36个月排名。高 = 信用收缩 → 降险。"},
    "vol": {"name_en": "Realized volatility", "name_zh": "已实现波动率",
            "src_en": "CSI 300 21d realized vol · 5y percentile", "src_zh": "沪深300 21日已实现波动率·5年百分位",
            "desc_en": "Moreira-Muir: CSI 300's own 21-day realized volatility, ranked over 5 years. Vol is persistent and precedes drawdowns. High = elevated → de-risk.",
            "desc_zh": "Moreira-Muir：沪深300自身21日已实现波动率、按5年排名。波动率具持续性且先于回撤。高 = 升高 → 降险。"},
    "margin": {"name_en": "Margin euphoria", "name_zh": "融资狂热",
               "src_en": "Margin balance / float mcap · 5y percentile", "src_zh": "融资余额/流通市值·5年百分位",
               "desc_en": "Retail margin financing as a share of float market cap, ranked over 5 years (the 2015 bubble top read an extreme). High = leverage euphoria → de-risk.",
               "desc_zh": "散户融资余额占流通市值比重、按5年排名（2015年泡沫见顶为极值）。高 = 杠杆狂热 → 降险。"},
}


def regime_state(P: pd.DataFrame | None = None) -> dict | None:
    """The LIVE China regime layer — the single largest driver of the book (0.40 weight).
    Returns the latest value of each de-risk leg, the blended de-risk score and a
    risk-on/off state label, so the detail page can show WHY the book is positioned as it is.
    None if no leg resolves (e.g. CI without the akshare-backed collectors)."""
    P = P if P is not None else _prices()
    if P.empty:
        return None
    cal = P.index
    legs_raw = _derisk_legs(cal)
    blended = _derisk_score(cal)
    if not legs_raw or blended is None:
        return None
    b = blended.dropna()
    if b.empty:
        return None
    bl = float(b.iloc[-1])
    legs = []
    for key, s, w in legs_raw:
        sv = s.dropna()
        if sv.empty:
            continue
        m = _LEG_META[key]
        legs.append({"key": key, "weight": w, "value": round(float(sv.iloc[-1]), 2),
                     "name_en": m["name_en"], "name_zh": m["name_zh"],
                     "src_en": m["src_en"], "src_zh": m["src_zh"],
                     "desc_en": m["desc_en"], "desc_zh": m["desc_zh"]})
    if not legs:
        return None
    if bl >= 0.66:
        state_en, state_zh, tone = "Risk-off — de-risking", "风险偏离 — 降险中", "off"
    elif bl >= 0.40:
        state_en, state_zh, tone = "Neutral / mixed", "中性 / 混合", "mixed"
    else:
        state_en, state_zh, tone = "Risk-on — leaning in", "风险偏好 — 加仓", "on"
    return {"blended": round(bl, 2), "tilt": round((bl - 0.5) * 2.0, 2), "pct": round(bl * 100),
            "state_en": state_en, "state_zh": state_zh, "tone": tone,
            "legs": legs, "asof": str(cal[-1].date())}


def _conviction(P: pd.DataFrame) -> pd.DataFrame:
    """The 4-factor signed conviction per asset, floored at 0 (long-only book). China legs:
    TREND (down-weighted), structural CARRY, the credit/vol/margin REGIME, and X-MOM."""
    cal = P.index
    cols = [a for a in ASSETS if a in P.columns]
    # 1) trend (price-based, reused verbatim) — down-weighted for A-share mean-reversion
    trend = pd.DataFrame({a: tsmom_alloc(P[a]) for a in cols}, index=cal)
    # 2) structural carry tilt toward the income/bond/gold sleeves
    carry = pd.DataFrame(0.0, index=cal, columns=cols)
    for a, v in STRUCT_CARRY.items():
        if a in carry:
            carry[a] = v
    # 3) regime tilt — the validated China de-risk legs (credit impulse / vol / margin)
    regime = pd.DataFrame(0.0, index=cal, columns=cols)
    derisk = _derisk_score(cal)
    if derisk is not None:
        tilt = ((derisk - 0.5) * 2.0).clip(-1, 1)        # +1 = de-risk
        for a in cols:
            if a in RISKY:
                regime[a] = (-tilt).clip(-1, 1)
            elif a in SAFE:
                regime[a] = tilt.clip(-1, 1)
    # 4) cross-asset relative momentum (126d)
    xrank = P.pct_change(126).rank(axis=1, pct=True)
    xmom = (2 * xrank - 1).fillna(0.0)
    conv = (W_TREND * trend + W_CARRY * carry.fillna(0) + W_REGIME * regime + W_XMOM * xmom)
    return conv.clip(-1, 1).clip(lower=0.0)              # long-only


def _weights(P: pd.DataFrame, prof: dict) -> pd.DataFrame:
    """Inverse-vol, conviction-tilted weights -> per-name cap -> book vol-target ->
    leverage cap -> weekly rebalance. (Shared with engine.masterminds._weights.)"""
    cal = P.index
    ret = P.pct_change()
    conv = _conviction(P)
    rv = (ret.rolling(21).std() * np.sqrt(aa.TRADING_YEAR)).clip(lower=0.05)
    raw = (conv * (0.10 / rv)).fillna(0.0)
    for a in P.columns:                                 # zero each asset until ~300d history
        fv = P[a].first_valid_index()
        if fv is not None:
            raw.loc[raw.index < fv + pd.Timedelta(days=300), a] = 0.0
    raw = raw.clip(upper=prof["w_cap"])
    port_vol = ((raw.shift(1) * ret).sum(axis=1).rolling(63).std() * np.sqrt(aa.TRADING_YEAR)).clip(lower=0.02)
    W = raw.mul((prof["target_vol"] / port_vol).clip(upper=3.0), axis=0)
    gross = W.abs().sum(axis=1)
    W = W.mul((prof["max_lev"] / gross.replace(0, np.nan)).clip(upper=1.0).fillna(1.0), axis=0).fillna(0.0)
    hold = pd.Series(False, index=cal)
    hold.iloc[::_REBAL] = True
    return W.where(hold).ffill().fillna(0.0)


def _bill(cal: pd.Index) -> pd.Series:
    return pd.Series(float(CHINA_CASH_PCT), index=cal)


def backtest(profile_key: str = DEFAULT_PROFILE, P: pd.DataFrame | None = None) -> dict:
    P = P if P is not None else _prices()
    if P.empty:
        return {"error": "no data"}
    prof = PROFILES[profile_key]
    W = _weights(P, prof)
    bill = _bill(P.index)
    # put CSI 300 first so the portfolio scorecard's hodl_* = CSI 300 buy-&-hold
    cols = ["510300.SS"] + [c for c in P.columns if c != "510300.SS"]
    bt = aa.backtest_portfolio(W[cols], P[cols], bill, cost_bps=3.0)
    # China 40/60 (equity/bond) benchmark for the conservative tier
    b6040 = None
    if "511010.SS" in P.columns:
        w46 = pd.DataFrame({"510300.SS": 0.4, "511010.SS": 0.6}, index=P.index)
        b6040 = aa.backtest_portfolio(w46, P[["510300.SS", "511010.SS"]], bill, cost_bps=1.0)
    if prof["bench"] == "cn6040" and "511010.SS" in P.columns:
        bench_ret = 0.4 * P["510300.SS"].pct_change().fillna(0) + 0.6 * P["511010.SS"].pct_change().fillna(0)
    else:
        bench_ret = P["510300.SS"].pct_change().fillna(0)
    oos = aa.split_half_oos(bt["net"], bench_ret)
    last = W.iloc[-1]
    alloc = [{"asset": a, "label_en": ASSET_LABEL[a][0], "label_zh": ASSET_LABEL[a][1],
              "weight": round(float(last[a]) * 100, 1)} for a in W.columns if abs(last.get(a, 0)) > 1e-4]
    alloc.sort(key=lambda x: -x["weight"])
    return {"profile": profile_key, "scorecard": bt, "bench6040": b6040, "weights": W,
            "oos": oos, "alloc": alloc, "gross_now": round(float(last.abs().sum()), 2),
            "asof": str(P.index[-1].date())}
