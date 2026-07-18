"""Cross-Asset Confirmation — does the fast-family macro complex (BONDS + FX)
CONFIRM or DIVERGE from the equity/macro regime?

Bonds (credit, curve, rates-vol, sovereign) and FX (the dollar, EM carry) sit at
the *fast* end of the macro complex. This leaf reads the two dedicated dashboards'
contracts — ``data/bonds/bond_health.json`` and ``data/forex/latest.json`` — and
compares their INDEPENDENT reads against the equity regime already computed in
``latest`` (engine/run.py), emitting:

  • a CYCLE-agreement leg   — bond credit×curve clock phase vs the equity cycle tag
  • a RISK-appetite leg     — FX risk + bond credit/rates-vol vs the equity RORO/drawdown read
  • a list of CAUTION FLAGS — the bond/FX configurations worth attention, each graded
                              by how *leading* (vs merely coincident) the literature says it is

HONESTY (graded from the literature — see research/CROSS_ASSET_CONFIRMATION.md §2):
only credit/EBP and the near-term-forward curve have a defensible (noisy, ~12mo)
*leading* horizon. MOVE-vs-VIX (VIX actually Granger-leads MOVE ex-acute-stress),
the dollar/EM-FX risk-off read (endogenous co-movement — the dollar move *is* the
tightening), and FX carry are COINCIDENT confirmation / fragility gauges, not
predictors. The stock-bond correlation is a slow regime descriptor. So this is a
cross-asset CONFIRMATION + fragility-watch, NOT a "bonds predict the crash" tool.

DISPLAY-ONLY / LEAF / never scored / never raises. Mirrors engine/signal_stack.py:
a near-pure function of already-computed state, bilingual, graceful, additive. It
invents NO new signal and feeds NOTHING in the scoring path.

CRITICAL: bond_health.json reuses engine.conditions, so its ``recession_risk``,
``drawdown_risk`` and ``stock_bond_corr`` are byte-identical to the equity-side
``conditions`` — comparing those would be a tautology. This module compares ONLY
the genuinely INDEPENDENT bond/FX reads (cycle_phase, credit/curve/rates-vol/
sovereign bands, the dollar-smile regime, EM-FX conviction).
"""
from __future__ import annotations

import json
import logging
from pathlib import Path

from lib import config

log = logging.getLogger(__name__)

BULL, FLAT, BEAR = 1, 0, -1
_TONE = {BULL: "up", FLAT: "flat", BEAR: "down"}

# cycle ADVANCEMENT / adversity ordinal (NOT the cyclical clock): early -> mid ->
# late -> recession. Higher = further into the cycle / more adverse. So a bond phase
# ABOVE the equity phase => bonds reading a later, more-adverse cycle (caution); below
# => bonds reading an earlier, more-benign cycle. recession is the MOST adverse bucket
# (a linear clock that put recession at 0 inverted the "bonds flash recession first"
# divergence — the exact case this leg exists to surface). The equity cycle_tag uses
# early/mid/late; the equity 'recession' state surfaces via the quad recession label.
_CYCLE_ORD = {"early": 0, "mid": 1, "late": 2, "recession": 3}
_PHASE_EN = {"recession": "recession", "early": "early-cycle", "mid": "mid-cycle",
             "late": "late-cycle"}
_PHASE_ZH = {"recession": "衰退", "early": "周期早段", "mid": "周期中段", "late": "周期晚段"}

# dollar-smile regime (forex contract `regime`) -> (zh, is_risk_off flavor)
_SMILE = {
    "Risk-off haven bid": ("避险买盘", True),
    "US-specific stress": ("美国自身风险", True),
    "US growth premium": ("美国增长溢价", False),
    "Global reflation": ("全球再通胀", False),
    "Neutral": ("中性", False),
}


def _read_json(path: Path):
    try:
        return json.loads(Path(path).read_text())
    except Exception:  # noqa: BLE001 — missing/garbled contract degrades to None
        return None


def _g(d, *keys, default=None):
    """Nested dict get: _g(d, 'a', 'b') == d['a']['b'] or default."""
    cur = d
    for k in keys:
        if not isinstance(cur, dict):
            return default
        cur = cur.get(k)
    return default if cur is None else cur


def _conf_word(n_present: int, n_agree: int) -> tuple[str, str, str]:
    """Confidence = BREADTH of agreement across present legs — explicitly NOT a
    forecast probability. Few legs or split -> low."""
    if n_present < 2:
        return "low", "low", "低"
    frac = n_agree / n_present
    if frac >= 0.8 and n_present >= 3:
        return "high", "high", "高"
    if frac >= 0.6:
        return "medium", "medium", "中"
    return "low", "low", "低"


def _cycle_leg(latest: dict, bonds: dict) -> dict | None:
    """Bond credit×curve clock phase vs the equity cycle tag (+ quad recession)."""
    b_phase = _g(bonds, "cycle_phase")
    eq_cycle = latest.get("cycle_tag")
    # the equity 'recession' refinement outranks 'late' — run.py builds label
    # "{quad}/Recession" when the quad recession flag fires (engine/run.py:57-58).
    eq_recession = str(latest.get("label", "")).endswith("Recession")
    eq_key = "recession" if eq_recession else eq_cycle
    if b_phase not in _CYCLE_ORD or eq_key not in _CYCLE_ORD:
        return None
    diff = _CYCLE_ORD[b_phase] - _CYCLE_ORD[eq_key]
    if diff == 0:
        dirn, en, zh = FLAT, (f"bonds & equities agree: {_PHASE_EN[b_phase]}"), \
            (f"债券与股票一致：{_PHASE_ZH[b_phase]}")
    elif diff > 0:
        # bonds further into the cycle / more adverse than equities -> caution lean
        dirn = BEAR
        en = (f"bonds read {_PHASE_EN[b_phase]} while equities read "
              f"{_PHASE_EN.get(eq_key, eq_key)} — the bond clock is further along / more adverse")
        zh = (f"债券读数为{_PHASE_ZH[b_phase]}，股票为{_PHASE_ZH.get(eq_key, eq_key)}"
              f" — 债券时钟更靠后 / 更不利")
    else:
        # bonds earlier / more benign than equities -> mildly constructive
        dirn = BULL
        en = (f"bonds read {_PHASE_EN[b_phase]} while equities read "
              f"{_PHASE_EN.get(eq_key, eq_key)} — the bond clock is earlier / more benign")
        zh = (f"债券读数为{_PHASE_ZH[b_phase]}，股票为{_PHASE_ZH.get(eq_key, eq_key)}"
              f" — 债券时钟更靠前 / 更乐观")
    return {"key": "cycle", "label_en": "Cycle clock", "label_zh": "周期时钟",
            "equity_en": _PHASE_EN.get(eq_key, eq_key) if eq_key else "—",
            "leading_en": _PHASE_EN.get(b_phase, b_phase),
            "agree": diff == 0, "dir": dirn, "tone": _TONE[dirn],
            "detail_en": en, "detail_zh": zh, "tier": "context"}


def _risk_leg(latest: dict, bonds: dict, fx: dict) -> tuple[dict | None, int]:
    """Fast-family risk read (FX risk + bond credit + bond rates-vol — a MIX of
    partly-leading credit and coincident rates-vol/FX) vs the equity RORO/drawdown
    read. Returns (leg, n_caution_votes)."""
    # --- fast-family caution votes (0..3) ---
    credit_band = _g(bonds, "pillars", "credit", "distress_band")
    credit_dir = _g(bonds, "pillars", "credit", "direction")
    move_band = _g(bonds, "pillars", "stress", "move_band")
    move_leads = bool(_g(bonds, "pillars", "stress", "move_leads_vix"))
    fx_risk = fx.get("risk")
    fx_regime = fx.get("regime")
    smile_risk_off = _SMILE.get(fx_regime, ("", False))[1]

    credit_caution = (credit_band in ("elevated", "distress", "crisis")
                      or credit_dir == "widening")
    vol_caution = (move_band in ("elevated", "crisis") or move_leads)
    fx_caution = (fx_risk == "risk-off") or smile_risk_off
    votes = sum((credit_caution, vol_caution, fx_caution))
    n_present = sum(x is not None for x in (credit_band, move_band, fx_risk))
    if n_present == 0:
        return None, 0

    # --- equity-side risk read ---
    roro_state = _g(latest, "conditions", "risk_appetite", "roro_state")
    dd_band = _g(latest, "conditions", "drawdown_risk", "band")
    # nothing to compare against if the equity risk read is entirely absent — skip the
    # leg rather than silently treating a missing read as "calm" (which would manufacture
    # false equity-blind divergences).
    if roro_state is None and dd_band is None:
        return None, votes
    eq_caution = (roro_state == "risk-off") or (dd_band in ("elevated", "high", "extreme"))

    leading_caution = votes >= 2
    if leading_caution == eq_caution:
        # both sides agree (both cautious, or both calm)
        agree = True
        if eq_caution:
            dirn, en, zh = BEAR, "bonds & FX confirm the cautious equity read", \
                "债券与外汇确认了谨慎的股票读数"
        else:
            dirn, en, zh = BULL, "bonds & FX confirm the risk-on equity read", \
                "债券与外汇确认了偏多的股票读数"
    else:
        agree = False
        if leading_caution and not eq_caution:
            dirn = BEAR
            en = ("fast-family markets cautious (credit/rates-vol/FX) while equities "
                  "still risk-on — a divergence to watch")
            zh = "快端板块（信用/利率波动/外汇）转谨慎，但股票仍偏多 — 值得关注的背离"
        else:  # eq_caution and not leading_caution
            dirn = BULL
            en = ("equities cautious but bonds & FX calm — stress may be equity-specific, "
                  "not a broad risk-off")
            zh = "股票谨慎但债券与外汇平静 — 压力或为股票特有，而非全面避险"
    return ({"key": "risk", "label_en": "Risk appetite", "label_zh": "风险偏好",
             "equity_en": (roro_state or dd_band or "—"),
             "leading_en": ("cautious" if leading_caution else "risk-on"),
             "agree": agree, "dir": dirn, "tone": _TONE[dirn],
             "detail_en": en, "detail_zh": zh, "tier": "context",
             "caution_votes": votes}, votes)


def _caution_flags(bonds: dict, fx: dict, eq_calm: bool) -> list[dict]:
    """The bond/FX configurations worth attention. Each carries an honest `lead`
    grade (leading | coincident) from the literature, a severity, and whether it is
    firing while the equity gauges are still benign (`equity_blind`)."""
    flags: list[dict] = []

    def add(key, en, zh, severity, owner, lead):
        flags.append({"key": key, "en": en, "zh": zh, "severity": severity,
                      "owner": owner, "lead": lead, "equity_blind": eq_calm})

    # --- bonds ---
    credit_band = _g(bonds, "pillars", "credit", "distress_band")
    credit_dir = _g(bonds, "pillars", "credit", "direction")
    # NB: the ~12mo recession lead is an EBP (excess-bond-premium) property; the raw HY
    # distress band / direction is more coincident, so the framing is hedged accordingly.
    if credit_band in ("distress", "crisis"):
        add("credit", f"High-yield credit at {credit_band} levels — credit risk-appetite (the "
            "EBP family has a noisy ~12mo lead; the raw HY level is more coincident).",
            f"高收益信用处于{'危机' if credit_band == 'crisis' else '困境'}水平 — 信用风险偏好"
            "（EBP具嘈杂的约12个月领先；HY利差本身更偏同步）。", "high", "bonds", "leading")
    elif credit_dir == "widening" or credit_band == "elevated":
        add("credit", "High-yield credit widening from tight — credit risk-appetite turning "
            "(partly-leading via the EBP family, but often coincident with equity stress).",
            "高收益信用从偏紧走阔 — 信用风险偏好转向（经EBP具部分领先性，但常与股票压力同步）。",
            "medium", "bonds", "leading")

    uninv = bool(_g(bonds, "pillars", "curve", "uninversion_alarm"))
    bull_uninv = bool(_g(bonds, "pillars", "curve", "bull_steepener_uninversion"))
    if bull_uninv:
        add("uninversion", "Bull-steepener un-inversion — short rates collapsing as the curve "
            "dis-inverts; often the truer real-time recession alarm than the inversion itself.",
            "牛市陡峭式去倒挂 — 曲线去倒挂时短端利率快速下行；常比倒挂本身更真实的实时衰退警报。",
            "high", "bonds", "leading")
    elif uninv:
        add("uninversion", "Yield curve un-inverting — historically a late-cycle recession "
            "warning (lead time highly variable).",
            "收益率曲线去倒挂 — 历史上的晚周期衰退警告（领先时间高度可变）。",
            "medium", "bonds", "leading")

    move_band = _g(bonds, "pillars", "stress", "move_band")
    move_leads = bool(_g(bonds, "pillars", "stress", "move_leads_vix"))
    if move_band == "crisis":
        add("rates_vol", "Rates volatility (MOVE) at crisis levels — systemic rates stress.",
            "利率波动率（MOVE）处于危机水平 — 系统性利率压力。", "high", "bonds", "coincident")
    elif move_leads or move_band == "elevated":
        add("rates_vol", "Rates volatility (MOVE) rising relative to equity vol (VIX) — a "
            "coincident stress configuration (predictive only when both are already elevated).",
            "利率波动率（MOVE）相对股票波动率（VIX）上升 — 同步的压力配置（仅当两者均已偏高时具预测性）。",
            "low", "bonds", "coincident")

    if bool(_g(bonds, "pillars", "stress", "repo_stress")):
        add("plumbing", "Repo / funding plumbing stress — reserve scarcity or a repo spike.",
            "回购/资金管道压力 — 准备金稀缺或回购飙升。", "medium", "bonds", "coincident")

    frag_state = _g(bonds, "pillars", "sovereign", "frag_state")
    if frag_state in ("elevated", "stress"):
        add("sovereign", f"Euro-periphery fragmentation {frag_state} (BTP-Bund) — sovereign "
            "stress at the European core.",
            f"欧元区外围分化{('压力' if frag_state == 'stress' else '偏高')}（BTP-Bund）— 欧洲核心主权压力。",
            "high" if frag_state == "stress" else "medium", "bonds", "coincident")

    # --- FX ---
    fx_regime = fx.get("regime")
    if fx_regime == "Risk-off haven bid":
        add("fx_risk_off", "Dollar-smile in risk-off (haven bid for USD/JPY/CHF) — FX positioning "
            "defensive (a coincident global-risk-off read, not a forecaster).",
            "美元微笑处于避险侧（美元/日元/瑞郎避险买盘）— 外汇仓位防御（同步的全球避险读数，非预测）。",
            "medium", "fx", "coincident")
    elif fx_regime == "US-specific stress":
        add("fx_us_stress", "Dollar-smile broken (US-specific stress) — the dollar is weak into "
            "risk-off, a US-idiosyncratic configuration.",
            "美元微笑破裂（美国自身风险）— 美元在避险中走弱，美国特有配置。",
            "medium", "fx", "coincident")

    # EM-FX bid: USD strong vs the high-carry EM pairs (USD/MXN, USD/BRL LONG-base) —
    # EM cracking is a classic coincident global-risk-off amplifier.
    pairs = fx.get("pairs") or {}
    em = [pairs.get(p, {}) for p in ("USDMXN", "USDBRL")]
    # match BOTH long bands — the forex contract emits "LONG" and "STRONG LONG"
    # (engine/forex_conviction._FX_ACTION); an exact "LONG" match would silently drop
    # the strongest USD-bid-vs-EM config. The score>20 floor still enforces magnitude.
    em_long = [p for p in em if str(p.get("action") or "").endswith("LONG")
               and (p.get("score") or 0) > 20]
    if len(em_long) >= 2:
        add("em_fx_stress", "EM FX under pressure (USD bid vs MXN & BRL) — carry unwinds are a "
            "coincident risk-off amplifier (fat-tailed, not a clean lead).",
            "新兴市场货币承压（美元相对墨西哥比索与巴西雷亚尔走强）— 套息平仓是同步的避险放大器"
            "（肥尾，非干净领先）。", "medium", "fx", "coincident")

    # --- Dollar Desk (the deepened dollar read; all display-only / coincident-context) ---
    desk = fx.get("dollar_desk") or {}
    if desk.get("triple_red"):
        add("usd_triple_red", "Triple-red — USD, equities & Treasuries falling together: the dollar "
            "is NOT acting as a safe haven (a US-idiosyncratic 'sell-America' configuration).",
            "三红 — 美元、股票与国债同步下跌：美元未发挥避险作用（美国特有的‘抛售美国’配置）。",
            "high", "fx", "coincident")
    if desk.get("usd_pos_state") in ("crowded_long", "crowded_short"):
        _side = "long" if desk["usd_pos_state"] == "crowded_long" else "short"
        _side_zh = "做多" if _side == "long" else "做空"
        add("usd_positioning", f"USD spec positioning crowded {_side} ({desk.get('usd_pos_pctile')}th "
            "pctile) — a contrarian fragility/crowding gauge, not a timing signal (lagged, unmeasured).",
            f"美元投机持仓拥挤{_side_zh}（第{desk.get('usd_pos_pctile')}百分位）— 逆向脆弱性/拥挤度计量，"
            "非择时信号（滞后、未测）。", "info", "fx", "context")
    unstable = (fx.get("transmission") or {}).get("unstable") or []
    if unstable:
        add("usd_transmission_unstable", "Dollar↔asset betas are sign-unstable right now ("
            + ", ".join(unstable[:3]) + ") — cross-asset transmission reads should be taken with caution.",
            "美元与资产的贝塔当前符号不稳定（" + "、".join(unstable[:3]) + "）— 跨资产传导解读需谨慎。",
            "info", "fx", "context")

    return flags


def snapshot(latest: dict | None = None, root: Path | str | None = None,
             bonds: dict | None = None, fx: dict | None = None) -> dict:
    """Build the cross-asset confirmation read. Pure-ish: reads the bond + forex
    contracts from disk (or accepts them directly, for tests) and the already-built
    equity ``latest`` dict. Never raises; returns verdict='unknown' when too little
    is present. DISPLAY-ONLY — nothing in the scoring path consumes this.
    """
    try:
        root = Path(root) if root else config.ROOT
        if bonds is None:
            bonds = _read_json(root / "data" / "bonds" / "bond_health.json")
        if fx is None:
            fx = _read_json(root / "data" / "forex" / "latest.json")
        latest = latest or {}
        bonds = bonds or {}
        fx = fx or {}

        note_en = ("Bonds & FX cross-check: does the fast-family complex (bonds + FX) agree "
                   "with the equity/macro regime? DISPLAY-ONLY — never scored. Most legs are "
                   "coincident confirmation / fragility gauges; only credit/EBP and the curve have "
                   "a (noisy) leading horizon. Divergences are attention flags, not forecasts.")
        note_zh = ("债券与外汇交叉验证：快端板块（债券+外汇）是否与股票/宏观周期一致？仅供展示 — 从不评分。"
                   "多数为同步确认/脆弱性计量；仅信用/EBP与曲线具（嘈杂的）领先性。背离为关注信号，非预测。")
        unknown = {"verdict": "unknown", "headline_en": "Cross-asset confirmation unavailable "
                   "(bond / forex contracts not found).", "headline_zh": "跨资产确认不可用（未找到债券/外汇数据）。",
                   "confidence": "low", "note_en": note_en, "note_zh": note_zh,
                   "asof": bonds.get("as_of") or fx.get("date")}
        if not bonds and not fx:
            return unknown

        legs: list[dict] = []
        cyc = _cycle_leg(latest, bonds)
        if cyc:
            legs.append(cyc)
        risk_leg, votes = _risk_leg(latest, bonds, fx)
        if risk_leg:
            legs.append(risk_leg)
        if not legs:
            return unknown

        # equity gauges benign? (so a firing bond/FX flag is something equities don't yet show).
        # Require at least one equity gauge to be PRESENT — a missing equity read must not be
        # treated as "calm" (that would manufacture false equity-blind divergences).
        roro_state = _g(latest, "conditions", "risk_appetite", "roro_state")
        dd_band = _g(latest, "conditions", "drawdown_risk", "band")
        eq_present = (roro_state is not None) or (dd_band is not None)
        eq_calm = (eq_present and dd_band in (None, "low")
                   and roro_state in (None, "risk-on", "neutral"))

        flags = _caution_flags(bonds, fx, eq_calm)

        n_present = len(legs)
        n_agree = sum(1 for x in legs if x.get("agree"))
        n_diverge = n_present - n_agree
        # equity-blind flags = fast-family caution the equity gauges don't yet show
        blind_flags = [f for f in flags if f.get("equity_blind")]
        blind_sev = [f for f in blind_flags if f.get("severity") in ("medium", "high")]

        # --- verdict ---
        # confirm  : every leg agrees AND no fast-family caution the equities miss
        # diverge  : a medium/high caution flag equities don't yet show, OR ≥1 leg diverges
        #            alongside such a flag, OR a majority of legs diverge
        # mixed    : some cross-currents but not enough to call either way (the common case)
        if n_agree == n_present and not blind_flags:
            verdict = "confirm"
        elif blind_sev or (n_diverge >= 1 and blind_flags) or n_diverge > n_agree:
            verdict = "diverge"
        else:
            verdict = "mixed"

        conf_en, conf_key, conf_zh = _conf_word(n_present, n_agree)
        agree_pct = round(100 * n_agree / n_present) if n_present else None

        # --- headline ---
        b_phase = _g(bonds, "cycle_phase")
        eq_cycle = latest.get("cycle_tag")
        fx_regime = fx.get("regime")
        if verdict == "confirm":
            he = "Bonds & FX confirm the equity/macro regime."
            hz = "债券与外汇确认了股票/宏观周期。"
        elif verdict == "diverge":
            lead_bits = ", ".join(f["key"] for f in (blind_flags or flags)[:3])
            he = ("Bonds/FX diverge from the equity read"
                  + (f" — fast-family caution the equity gauges don't yet show ({lead_bits})"
                     if blind_flags else "") + ".")
            hz = ("债券/外汇与股票读数背离"
                  + ("（领先板块出现股票计量尚未显示的谨慎信号）" if blind_flags else "") + "。")
        else:
            he = "Bonds & FX broadly track the equity regime, with some cross-currents."
            hz = "债券与外汇大体跟随股票周期，但存在一些交叉信号。"

        # --- compact summary the master brain ingests ---
        to_brain = {
            "verdict": verdict,
            "cycle": {"equity": eq_cycle, "bonds": b_phase, "fx_regime": fx_regime},
            "leading_caution_votes": votes,
            "fx_risk": fx.get("risk"),
            "bond_health": bonds.get("health_score"),
            "bond_health_label": bonds.get("health_label"),
            "stock_bond_hedge": _g(bonds, "pillars", "cross_asset", "regime"),
            "caution_flags": [{"key": f["key"], "lead": f["lead"], "severity": f["severity"],
                               "equity_blind": f["equity_blind"]} for f in flags],
        }

        # B3: named display reasons (additive payload fields — never affects vote math).
        # These are named handles the template can render as plain-word context chips.
        # Fail-open: any read error yields an empty list.
        _display_reasons: list[str] = []
        try:
            _desk = fx.get("dollar_desk") or {}
            if _desk.get("triple_red"):
                _display_reasons.append("usd_triple_red")
            _lq_dir = _desk.get("liquidity_dir")
            # "supportive" = liquidity draining from risk assets (= USD absorbing flow).
            # Match both the canonical enum ("supportive") and the prose form ("draining")
            # that future builds may emit, per B3 spec.
            if _lq_dir in ("supportive", "draining"):
                _display_reasons.append("usd_liquidity_draining")
        except Exception:  # noqa: BLE001
            pass

        return {
            "verdict": verdict,
            "verdict_zh": {"confirm": "一致", "diverge": "背离", "mixed": "分歧"}.get(verdict, verdict),
            "headline_en": he, "headline_zh": hz,
            "confidence": conf_key, "confidence_en": conf_en, "confidence_zh": conf_zh,
            "agree_pct": agree_pct,
            "legs": legs,
            "caution_flags": flags,
            "display_reasons": _display_reasons,  # B3: named display reasons (additive)
            "cycle": {"equity": eq_cycle, "bonds": b_phase,
                      "bonds_en": _PHASE_EN.get(b_phase, b_phase) if b_phase else None,
                      "bonds_zh": _PHASE_ZH.get(b_phase, b_phase) if b_phase else None,
                      "fx_regime": fx_regime,
                      "fx_regime_zh": _SMILE.get(fx_regime, (fx_regime, False))[0] if fx_regime else None},
            "n_legs": n_present, "n_agree": n_agree, "n_diverge": n_diverge,
            "n_blind_flags": len(blind_flags),
            "to_brain": to_brain,
            "note_en": note_en, "note_zh": note_zh,
            "asof": bonds.get("as_of") or fx.get("date"),
        }
    except Exception as e:  # noqa: BLE001 — additive leaf, never fatal
        log.error("cross_asset_confirm.snapshot failed: %s", e)
        return {"verdict": "unknown", "headline_en": "Cross-asset confirmation error.",
                "headline_zh": "跨资产确认错误。", "confidence": "low"}
