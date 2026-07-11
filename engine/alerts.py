"""Alert rules — config-driven, evaluated on the engine's daily output.

Every rule compares today against yesterday (or a trailing window) using the
already-stored regime history and raw series, so alerts fire on *changes*,
never on levels alone. Fired alerts are appended to
data/alerts/alerts_log.parquet keyed by (date, rule) — re-running the same
day is idempotent and cannot double-send.

Severity is informational only ("info" | "warn" | "act"): it orders the
message, it does not gate anything.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass

import numpy as np
import pandas as pd

from lib import config, store

log = logging.getLogger(__name__)


@dataclass
class Alert:
    rule: str
    severity: str
    message: str
    message_zh: str = ""


def _regime_history() -> pd.DataFrame | None:
    p = config.data_dir() / "regime" / "regime_history.parquet"
    if not p.exists():
        return None
    df = pd.read_parquet(p)
    df.index = pd.to_datetime(df.index)
    return df.sort_index()


def _last_two(df: pd.DataFrame) -> tuple[pd.Series, pd.Series] | None:
    d = df.dropna(subset=["quad"])
    if len(d) < 2:
        return None
    return d.iloc[-2], d.iloc[-1]


# --- individual rules ----------------------------------------------------------

def transition_state_change(hist: pd.DataFrame, f: pd.DataFrame) -> Alert | None:
    pair = _last_two(hist)
    if pair is None:
        return None
    prev, cur = pair
    if cur["transition_state"] != prev["transition_state"]:
        sev = {"STABLE": "info", "WEAKENING": "warn",
               "TRANSITIONING": "act", "NEW_REGIME": "act"}.get(cur["transition_state"], "info")
        return Alert("transition_state_change", sev,
                     f"Transition state {prev['transition_state']} -> {cur['transition_state']} "
                     f"({int(cur['n_flags'])} flags active)",
                     message_zh=f"转换状态 {prev['transition_state']} -> {cur['transition_state']}"
                                f"（{int(cur['n_flags'])} 个预警激活）")
    return None


def axis_confidence_floor(hist: pd.DataFrame, f: pd.DataFrame) -> list[Alert]:
    floor = config.load()["alerts"]["axis_confidence_floor"]
    pair = _last_two(hist)
    if pair is None:
        return []
    prev, cur = pair
    out = []
    _axis_zh = {"growth": "增长", "inflation": "通胀"}
    for axis in ("growth", "inflation"):
        col = f"{axis}_confidence"
        if prev[col] >= floor > cur[col]:
            out.append(Alert(f"{axis}_confidence_floor", "warn",
                             f"{axis.capitalize()} axis confidence dropped below {floor:.0%}: "
                             f"{prev[col]:.0%} -> {cur[col]:.0%}",
                             message_zh=f"{_axis_zh[axis]} 轴一致度跌破 {floor:.0%}："
                                        f"{prev[col]:.0%} -> {cur[col]:.0%}"))
    return out


def sector_rs_percentile_cross(hist: pd.DataFrame, f: pd.DataFrame) -> list[Alert]:
    acfg = config.load()["alerts"]
    hi, lo = acfg["sector_rs_percentile_hi"], acfg["sector_rs_percentile_lo"]
    from engine.inputs import yahoo_closes
    closes = yahoo_closes()
    bench = config.load()["engine"]["rs_ranking"]["benchmark"]
    sectors = config.load()["yahoo"]["tickers"]["sectors"]
    out = []
    for t in sectors:
        if t not in closes.columns or bench not in closes.columns:
            continue
        rs = (closes[t] / closes[bench]).dropna()
        if len(rs) < 120:
            continue
        pct = rs.rolling(90, min_periods=60).rank(pct=True) * 100
        if len(pct.dropna()) < 2:
            continue
        y, t_ = pct.dropna().iloc[-2], pct.dropna().iloc[-1]
        if y < hi <= t_:
            out.append(Alert("sector_rs_cross_high", "info",
                             f"{t} RS vs {bench} crossed above {hi}th pctile of 90d (now {t_:.0f})",
                             message_zh=f"{t} RS 相对 {bench} 上穿 90 天第 {hi} 百分位（现为 {t_:.0f}）"))
        elif y > lo >= t_:
            out.append(Alert("sector_rs_cross_low", "info",
                             f"{t} RS vs {bench} crossed below {lo}th pctile of 90d (now {t_:.0f})",
                             message_zh=f"{t} RS 相对 {bench} 下穿 90 天第 {lo} 百分位（现为 {t_:.0f}）"))
    return out


def holdings_active_changes(hist: pd.DataFrame, f: pd.DataFrame) -> list[Alert]:
    from collectors.holdings import active_changes
    hcfg = config.load()["holdings"]
    thresh = hcfg["active_change_alert_pct"]
    out = []
    for ticker in hcfg["watchlist"]:
        ch = active_changes(ticker)
        if ch is None or ch.empty:
            continue
        big = ch[ch["active_chg_pct"].abs() >= thresh].dropna(subset=["active_chg_pct"])
        for pos, row in big.iterrows():
            verb = "added" if row["active_chg_pct"] > 0 else "cut"
            out.append(Alert("holdings_active_change", "info",
                             f"{ticker}: manager {verb} {pos} by {row['active_chg_pct']:+.0f}% "
                             f"of position ({row['window_start']}..{row['window_end']}, "
                             f"flow-normalized)",
                             message_zh=f"{ticker}：经理 {verb} {pos} 仓位 {row['active_chg_pct']:+.0f}%"
                                        f"（{row['window_start']}..{row['window_end']}，"
                                        f"已按资金流标准化）"))
    return out


def _fmt_flow_mn(mn: float) -> str:
    """$ millions -> compact string: 1234 -> +$1.2B, -87 -> -$87M."""
    sign = "+" if mn >= 0 else "-"
    a = abs(mn)
    return f"{sign}${a / 1000:.1f}B" if a >= 1000 else f"{sign}${a:.0f}M"


def sector_holdings_accumulation(hist: pd.DataFrame, f: pd.DataFrame) -> list[Alert]:
    """Fires when a sector-ETF holding's PRICE-DECOMPOSED weight change (residual
    beyond what the stock's price move explains) clears the alert threshold. On
    these passive index funds the residual is reconstitution/float flow, not
    discretionary conviction — see engine/holdings_signals.py and D70."""
    if not config.load()["alerts"].get("sector_holdings_accumulation", False):
        return []
    from engine.holdings_signals import all_accumulation_signals
    alert_pp = config.load()["holdings_signals"].get("alert_pp", 0.25)
    out = []
    for s in all_accumulation_signals():
        if abs(s["active_change"]) < alert_pp:
            continue
        verb, verb_zh = ("accumulating", "增持") if s["direction"] == "accumulating" \
            else ("trimming", "减持")
        flow = flow_zh = ""
        if s.get("est_flow_mn") is not None:
            f_str = _fmt_flow_mn(s["est_flow_mn"])
            flow = f" (≈{f_str} est. rebalance flow)"
            flow_zh = f"（≈{f_str} 估算再平衡资金流）"
        cyc = cyc_zh = ""
        if s.get("ladder"):
            cyc = f" — cycle {s['ladder']['label']}·{s['ladder']['action']}"
            cyc_zh = f" — 周期 {s['ladder']['label']}·{s['ladder']['action']}"
        sev = "warn" if s.get("confirmed") else "info"
        out.append(Alert(
            "sector_holdings_accumulation", sev,
            f"{s['fund']}: {s['ticker']} weight {s['active_change']:+.2f}pp beyond price"
            f"{flow} ({verb}), {s['t0']}..{s['t1']}{cyc}",
            message_zh=f"{s['fund']}：{s['ticker']} 权重较价格多变动 {s['active_change']:+.2f}pp"
                       f"{flow_zh}（{verb_zh}），{s['t0']}..{s['t1']}{cyc_zh}"))
    return out


def net_liquidity_roc_flip(hist: pd.DataFrame, f: pd.DataFrame) -> Alert | None:
    acfg = config.load()["alerts"]
    if not acfg["net_liquidity_roc_sign_flip"]:
        return None
    w = config.load()["engine"]["liquidity"]["roc_window_d"]
    # quality gates (config-overridable; defaults mean no config change is needed):
    #   deadband — ignore flips that land within ±N bn of zero (the "+7 -> -0bn"
    #              non-event), and
    #   confirm  — require the new sign to HOLD this many days, so a one-day
    #              whipsaw across zero can't fire.
    deadband = float(acfg.get("net_liquidity_roc_deadband_bn", 25.0))
    confirm = max(1, int(acfg.get("net_liquidity_roc_confirm_days", 2)))
    roc = (f["net_liquidity_bn"] - f["net_liquidity_bn"].shift(w)).dropna()
    if len(roc) < confirm + 1:
        return None
    t = roc.iloc[-1]
    run = roc.iloc[-confirm:]              # the last `confirm` days
    before = roc.iloc[-(confirm + 1)]      # the day just before that run
    held = t != 0 and bool((np.sign(run) == np.sign(t)).all())
    flipped = np.sign(before) != np.sign(t)   # opposite side, or flipping out of an exact 0
    if held and flipped and abs(t) >= deadband:
        direction = "positive (expanding)" if t > 0 else "negative (contracting)"
        direction_zh = "正值（扩张）" if t > 0 else "负值（收缩）"
        return Alert("net_liquidity_roc_flip", "warn",
                     f"Net liquidity 4-week RoC flipped {direction} and held "
                     f"{confirm}d: {before:+.0f}bn -> {t:+.0f}bn",
                     message_zh=f"净流动性 4 周 RoC 转为{direction_zh}并持续 {confirm} 天："
                                f"{before:+.0f}bn -> {t:+.0f}bn")
    return None


def hy_oas_widening(hist: pd.DataFrame, f: pd.DataFrame) -> Alert | None:
    zmax = config.load()["alerts"]["hy_oas_1d_widening_z"]
    oas = f["hy_oas"].dropna()
    if len(oas) < 260:
        return None
    chg = oas.diff()
    z = (chg.iloc[-1] - chg.rolling(252).mean().iloc[-1]) / chg.rolling(252).std().iloc[-1]
    if z > zmax:
        return Alert("hy_oas_widening", "act",
                     f"HY OAS 1-day widening {chg.iloc[-1]:+.2f}pp is {z:.1f} sigma "
                     f"(level {oas.iloc[-1]:.2f}%)",
                     message_zh=f"HY OAS 单日走阔 {chg.iloc[-1]:+.2f}pp，达 {z:.1f} 个标准差"
                                f"（水平 {oas.iloc[-1]:.2f}%）")
    return None


def circuit_breaker_open(hist: pd.DataFrame, f: pd.DataFrame) -> list[Alert]:
    """Fires once, the day a source's breaker opens (count == threshold);
    higher counts mean it already fired, reset-to-zero means recovered."""
    from collectors.base import CIRCUIT_BREAKER_FAILS
    breaker = store.read_status().get("circuit_breaker", {})
    return [Alert("circuit_breaker_open", "warn",
                  f"Source '{src}' marked dead after {n} consecutive failures — "
                  f"collector skipped until it recovers; affected signals degrade",
                  message_zh=f"数据源 '{src}' 连续 {n} 次失败后被标记为中断 —"
                             f"采集器暂停直至恢复；相关信号置信度下降")
            for src, n in breaker.items() if n == CIRCUIT_BREAKER_FAILS]


def gex_flip_cross(hist: pd.DataFrame, f: pd.DataFrame) -> Alert | None:
    if not config.load()["alerts"]["gex_flip_cross"]:
        return None
    g = store.read("cboe", "gex")
    if g is None or len(g) < 2:
        return None
    acfg = config.load()["alerts"]
    g_deadband = float(acfg.get("gex_net_deadband_bn", 1.0))      # ignore sign flips near 0bn
    flip_deadband = float(acfg.get("gex_flip_pct_deadband", 0.25))  # ignore hugging the flip
    y, t = g.iloc[-2], g.iloc[-1]
    crossed_flip = (pd.notna(y.get("spot_vs_flip_pct")) and pd.notna(t.get("spot_vs_flip_pct"))
                    and np.sign(y["spot_vs_flip_pct"]) != np.sign(t["spot_vs_flip_pct"])
                    and abs(t["spot_vs_flip_pct"]) >= flip_deadband)
    sign_change = (pd.notna(y.get("net_gex_bn")) and pd.notna(t.get("net_gex_bn"))
                   and np.sign(y["net_gex_bn"]) != np.sign(t["net_gex_bn"])
                   and abs(t["net_gex_bn"]) >= g_deadband)
    if crossed_flip or sign_change:
        what = "spot crossed the gamma flip" if crossed_flip else "net GEX changed sign"
        ng, sf = t.get("net_gex_bn"), t.get("spot_vs_flip_pct")
        ng_s = f"{ng:+.0f}bn" if pd.notna(ng) else "n/a"
        sf_s = f"{sf:+.1f}%" if pd.notna(sf) else "n/a"
        return Alert("gex_flip_cross", "warn",
                     f"GEX: {what} (net {ng_s}, spot vs flip {sf_s})",
                     message_zh=f"GEX：{what}（净 {ng_s}，现价相对翻转点 {sf_s}）")
    return None


# --- conditions layer (research/QUANT_FACTOR_EXPANSION.md) -----------------------

def _conditions_frame(f: pd.DataFrame):
    from engine.conditions import conditions_frame
    return conditions_frame(f)


def conditions_recession_state_change(hist: pd.DataFrame, f: pd.DataFrame) -> Alert | None:
    """Fire when the recession-risk band (low/elevated/high) changes."""
    if not config.load()["alerts"].get("conditions_recession_state_change", True):
        return None
    rc = config.load()["engine"]["conditions"]["recession"]
    cf = _conditions_frame(f)
    if "recession_risk" not in cf:
        return None
    s = cf["recession_risk"].dropna()
    if len(s) < 2:
        return None

    def band(v: float) -> str:
        return "high" if v >= rc["high_score"] else ("elevated" if v >= rc["elevated_score"] else "low")
    prev, cur = band(s.iloc[-2]), band(s.iloc[-1])
    if prev == cur:
        return None
    rising = s.iloc[-1] > s.iloc[-2]
    sev = "act" if cur == "high" else ("warn" if rising else "info")
    return Alert("conditions_recession_state_change", sev,
                 f"Recession-risk band {prev} -> {cur} (score {s.iloc[-1]:.0f}/100)",
                 message_zh=f"衰退风险等级 {prev} -> {cur}（评分 {s.iloc[-1]:.0f}/100）")


def nfci_tightening(hist: pd.DataFrame, f: pd.DataFrame) -> Alert | None:
    """Financial conditions crossing from loose/neutral into tight."""
    thr = config.load()["alerts"].get("nfci_tightening_z")
    if thr is None or "nfci" not in f.columns:
        return None
    s = f["nfci"].dropna()
    if len(s) < 2:
        return None
    if s.iloc[-2] < thr <= s.iloc[-1]:
        return Alert("nfci_tightening", "warn",
                     f"Financial conditions tightened: NFCI crossed above {thr:+.2f} "
                     f"(now {s.iloc[-1]:+.2f}) — broad risk-off",
                     message_zh=f"金融条件收紧：NFCI 上穿 {thr:+.2f}（现 {s.iloc[-1]:+.2f}）— 广泛避险")
    return None


def sahm_trigger(hist: pd.DataFrame, f: pd.DataFrame) -> Alert | None:
    """The Sahm rule crossing its 0.50 recession threshold (labor-side confirm)."""
    thr = config.load()["alerts"].get("sahm_trigger")
    if thr is None or "sahm" not in f.columns:
        return None
    s = f["sahm"].dropna()
    if len(s) < 2:
        return None
    if s.iloc[-2] < thr <= s.iloc[-1]:
        return Alert("sahm_trigger", "act",
                     f"Sahm rule triggered ({s.iloc[-1]:.2f} >= {thr:.2f}) — labor market "
                     f"signalling a recession is underway",
                     message_zh=f"Sahm 法则触发（{s.iloc[-1]:.2f} >= {thr:.2f}）— 劳动力市场显示衰退已开始")
    return None


def ebp_widening(hist: pd.DataFrame, f: pd.DataFrame) -> Alert | None:
    """Excess Bond Premium spiking — a credit-risk-appetite shock."""
    zmax = config.load()["alerts"].get("ebp_widening_z")
    if zmax is None or "ebp" not in f.columns:
        return None
    ebp = f["ebp"].dropna()
    distinct = ebp[ebp.ne(ebp.shift())]   # monthly prints (de-dupe the ffill)
    if len(distinct) < 24:
        return None
    chg = distinct.diff()
    sd = chg.rolling(36).std().iloc[-1]
    if not sd or pd.isna(sd):
        return None
    z = (chg.iloc[-1] - chg.rolling(36).mean().iloc[-1]) / sd
    if z > zmax:
        return Alert("ebp_widening", "warn",
                     f"Excess Bond Premium jumped {chg.iloc[-1]:+.2f} ({z:.1f} sigma) — "
                     f"credit risk-appetite deteriorating (level {distinct.iloc[-1]:+.2f})",
                     message_zh=f"超额债券溢价跳升 {chg.iloc[-1]:+.2f}（{z:.1f} 个标准差）— "
                                f"信用风险偏好恶化（水平 {distinct.iloc[-1]:+.2f}）")
    return None


def drawdown_risk_high(hist: pd.DataFrame, f: pd.DataFrame) -> Alert | None:
    """Macro-stress (drawdown-risk) gauge crossing into the high band. RE-ISSUED on
    the PIT frame + claims composition (audit #39): P(>=10% drawdown in 63d) ~36% in
    this band vs ~19% base (scripts/validate_drawdown_risk_pit.py)."""
    thr = config.load()["alerts"].get("drawdown_risk_high")
    if thr is None:
        return None
    s = _conditions_frame(f).get("drawdown_risk")
    if s is None:
        return None
    s = s.dropna()
    if len(s) < 2 or not (s.iloc[-2] < thr <= s.iloc[-1]):
        return None
    from engine.conditions import _drawdown_band_table
    bt = _drawdown_band_table()
    hi, base = bt["high"], bt["base"]
    return Alert("drawdown_risk_high", "act",
                 f"Macro-stress gauge crossed into the HIGH band ({s.iloc[-1]:.0f}/100) — "
                 f"P(>=10% drawdown in 3 months) ~{hi}% vs ~{base}% base; size down, widen stops",
                 message_zh=f"宏观压力指标进入高位区（{s.iloc[-1]:.0f}/100）— 未来三个月 >=10% 回撤"
                            f"的概率约 {hi}%（基准约 {base}%）；减小仓位、放宽止损")


def capitulation_signal(hist: pd.DataFrame, f: pd.DataFrame) -> Alert | None:
    """Capitulation gauge going STRONG (>=2 stacked signals). MEASURED contrarian
    bounce: +9.3%/63d, 86% positive vs +2.8% base (research §6)."""
    thr = config.load()["alerts"].get("capitulation_strong")
    if thr is None:
        return None
    s = _conditions_frame(f).get("capitulation_score")
    if s is None:
        return None
    s = s.dropna()
    if len(s) < 2 or not (s.iloc[-2] < thr <= s.iloc[-1]):
        return None
    return Alert("capitulation_signal", "warn",
                 f"Capitulation gauge fired ({int(s.iloc[-1])} of 3 panic signals) — historically a "
                 f"contrarian setup: S&P +9.3%/3mo, 86% positive (vs +2.8% base). Fear, not forecast.",
                 message_zh=f"恐慌触底指标触发（3 个恐慌信号中的 {int(s.iloc[-1])} 个）— 历史上的逆向布局："
                            f"S&P 未来三月 +9.3%，86% 为正（基准 +2.8%）。是恐慌而非预测。")


# --- fused equity-internal risk state (engine/risk_state.py) --------------------

def risk_state_elevated(hist: pd.DataFrame, f: pd.DataFrame) -> Alert | None:
    """The LOUD composite: fire when the fused equity-internal risk-state core
    crosses INTO elevated. Unlike drawdown_risk_high (credit/recession-weighted),
    this leads on positioning/vol/breadth — the exact blind spot on 2026-06-23."""
    if not config.load()["alerts"].get("risk_state_elevated", True):
        return None
    from engine import risk_state as rs
    s = rs.core_series(f)
    if s is None or len(s.dropna()) < 2:
        return None
    s = s.dropna()
    thr = float(rs._cfg()["bands"]["elevated"])
    if not (s.iloc[-2] < thr <= s.iloc[-1]):
        return None
    sev = "act" if s.iloc[-1] >= float(rs._cfg()["bands"]["risk_off"]) else "warn"
    return Alert("risk_state_elevated", sev,
                 f"Equity risk-state crossed into {'RISK-OFF' if sev == 'act' else 'ELEVATED'} "
                 f"({s.iloc[-1]:.0f}/100) — positioning/vol/breadth fragility building; "
                 f"de-gross, favor entries over chasing leaders",
                 message_zh=f"股票风险状态进入{'risk-off' if sev == 'act' else '偏高'}区"
                            f"（{s.iloc[-1]:.0f}/100）— 仓位/波动/宽度脆弱性上升；降低敞口、择优入场而非追高")


def hidden_fragility(hist: pd.DataFrame, f: pd.DataFrame) -> Alert | None:
    """Promote the orphaned complacency / hidden-fragility detector to a real alert:
    a CALM surface (cheap VIX, steep contango) over WEAKENING internals. Fires on the
    cross into watch (calm>=1 & frag>=1); act-tier on hidden-fragility (calm>=1 & frag>=2)."""
    if not config.load()["alerts"].get("hidden_fragility", True):
        return None
    cf = _conditions_frame(f)
    if not {"complacency_calm", "complacency_fragility"} <= set(cf.columns):
        return None
    cc, fr = cf["complacency_calm"], cf["complacency_fragility"]
    warn = ((cc >= 1) & (fr >= 1)).astype(int)
    strong = ((cc >= 1) & (fr >= 2)).astype(int)
    d = pd.concat([warn.rename("w"), strong.rename("s")], axis=1).dropna()
    if len(d) < 2:
        return None
    y, t = d.iloc[-2], d.iloc[-1]
    if t["s"] and not y["s"]:
        return Alert("hidden_fragility", "act",
                     "Hidden fragility: a calm surface (cheap VIX, contango) over weakening "
                     "internals (thinning breadth, HY widening) — the classic complacent pre-drawdown setup",
                     message_zh="隐性脆弱：平静表象（低VIX、contango）下内部走弱（宽度变薄、HY走阔）— 典型的自满型回撤前夜")
    if t["w"] and not y["w"]:
        return Alert("hidden_fragility", "warn",
                     "Complacency watch: calm tape starting to mask weakening internals",
                     message_zh="自满预警：平静走势开始掩盖走弱的内部结构")
    return None


def breadth_divergence(hist: pd.DataFrame, f: pd.DataFrame) -> Alert | None:
    """Promote the orphaned breadth-divergence detector: index near its 1y high while
    %>200dma is weak (a thinning tape). Fires on the cross from confirming -> diverging."""
    if not config.load()["alerts"].get("breadth_divergence", True):
        return None
    cf = _conditions_frame(f)
    if not {"spy_high_prox", "breadth_above200_pctile"} <= set(cf.columns):
        return None
    mcfg = config.load()["engine"]["conditions"].get("complacency", {})
    high_prox = float(mcfg.get("breadth_high_prox", 0.97))
    weak_p = float(mcfg.get("breadth_weak_pctile", 0.35))
    div = ((cf["spy_high_prox"] >= high_prox) &
           (cf["breadth_above200_pctile"] < weak_p)).astype(int)
    d = div.dropna()
    if len(d) < 2 or not (d.iloc[-1] and not d.iloc[-2]):
        return None
    b2p = cf["breadth_above200_pctile"].dropna()
    return Alert("breadth_divergence", "warn",
                 f"Breadth divergence: index near its 1y high while %>200dma is weak "
                 f"({b2p.iloc[-1]:.0%} pctile) — fewer names carrying the tape",
                 message_zh=f"宽度背离：指数接近一年高点但 %>200日均线偏弱"
                            f"（{b2p.iloc[-1]:.0%} 分位）— 抬指数的个股在减少")


# --- runner ---------------------------------------------------------------------

def evaluate(f: pd.DataFrame) -> list[Alert]:
    hist = _regime_history()
    if hist is None:
        log.warning("alerts: no regime history yet")
        return []
    alerts: list[Alert] = []
    rules = [transition_state_change, net_liquidity_roc_flip, hy_oas_widening,
             gex_flip_cross, conditions_recession_state_change, nfci_tightening,
             sahm_trigger, ebp_widening, drawdown_risk_high, capitulation_signal,
             risk_state_elevated, hidden_fragility, breadth_divergence]
    multi = [axis_confidence_floor, sector_rs_percentile_cross,
             holdings_active_changes, sector_holdings_accumulation,
             circuit_breaker_open]
    for rule in rules:
        try:
            a = rule(hist, f)
            if a:
                alerts.append(a)
        except Exception as e:  # noqa: BLE001 — one rule must not kill the rest
            log.error("alert rule %s failed: %s", rule.__name__, e)
    for rule in multi:
        try:
            alerts.extend(rule(hist, f))
        except Exception as e:  # noqa: BLE001
            log.error("alert rule %s failed: %s", rule.__name__, e)
    order = {"act": 0, "warn": 1, "info": 2}
    return sorted(alerts, key=lambda a: order.get(a.severity, 9))


def log_and_dedup(alerts: list[Alert], asof: pd.Timestamp) -> list[Alert]:
    """Append to the alert log; drop alerts already fired for this date."""
    p = config.data_dir() / "alerts" / "alerts_log.parquet"
    p.parent.mkdir(parents=True, exist_ok=True)
    old = pd.read_parquet(p) if p.exists() else pd.DataFrame(
        columns=["date", "rule", "severity", "message", "message_zh"])
    # backfill message_zh column for parquet files written before the zh column existed
    if "message_zh" not in old.columns:
        old["message_zh"] = ""
    seen = set(zip(old["date"].astype(str), old["rule"], old["message"]))
    fresh = [a for a in alerts
             if (str(asof.date()), a.rule, a.message) not in seen]
    if fresh:
        new = pd.DataFrame([{"date": str(asof.date()), "rule": a.rule,
                             "severity": a.severity, "message": a.message,
                             "message_zh": a.message_zh or ""}
                            for a in fresh])
        pd.concat([old, new], ignore_index=True).to_parquet(p)
    return fresh


def recent_alerts(days: int = 7) -> pd.DataFrame:
    p = config.data_dir() / "alerts" / "alerts_log.parquet"
    if not p.exists():
        return pd.DataFrame(columns=["date", "rule", "severity", "message"])
    df = pd.read_parquet(p)
    cutoff = (pd.Timestamp.today() - pd.Timedelta(days=days)).date()
    return df[pd.to_datetime(df["date"]).dt.date >= cutoff]


# --- presentation layer --------------------------------------------------------
# Rule messages are precise but jargon-heavy. ALERT_META adds a plain-English
# headline, an icon, a "what it means / how to use it" explainer, and the macro
# dashboard panel ("scorecard") each alert deep-links to. `anchor` matches an
# id="" on a panel in templates/dashboard.html.j2. This is the single source of
# truth shared by the macro page (scripts/build_site.py) and the landing hub
# (scripts/build_vector.py) — keep anchors in sync with the template.

_DEFAULT_META = {
    "icon": "🔔",
    "plain_en": "Macro signal fired",
    "plain_zh": "宏观信号触发",
    "what_en": "An automated macro signal changed state. Open the dashboard for the "
               "full read.",
    "what_zh": "一个自动宏观信号发生了状态变化。打开仪表盘查看完整解读。",
    "anchor": "",
}

ALERT_META: dict[str, dict] = {
    "risk_state_elevated": {
        "icon": "🚨",
        "plain_en": "Market risk-state went ELEVATED — drawdown risk is building",
        "plain_zh": "市场风险状态转为偏高 — 回撤风险上升",
        "what_en": "The fused equity-internal risk-state (complacency, breadth divergence, "
                   "dealer gamma, vol structure, credit) crossed into elevated. It leads the "
                   "credit-weighted macro gauge on positioning/vol/breadth blow-offs. "
                   "Cue to de-gross and favor good entries over chasing leaders.",
        "what_zh": "融合的股票内部风险状态（自满度、宽度背离、做市商Gamma、波动结构、信用）"
                   "进入偏高区。在仓位/波动/宽度型见顶上领先于信用加权的宏观指标。"
                   "提示降低敞口、择优入场而非追高。",
        "anchor": "risk-state",
    },
    "hidden_fragility": {
        "icon": "🫧",
        "plain_en": "Calm surface, fragile internals — complacency watch",
        "plain_zh": "表象平静、内部脆弱 — 自满预警",
        "what_en": "A cheap-VIX / steep-contango calm sitting over weakening internals "
                   "(thinning breadth, HY credit quietly widening). The classic complacent "
                   "pre-drawdown setup. Context, not a timer — size down, don't chase.",
        "what_zh": "低VIX、陡峭contango的平静，叠加走弱的内部结构（宽度变薄、HY信用悄然走阔）。"
                   "典型的自满型回撤前夜。属背景而非择时 — 缩小仓位，不要追高。",
        "anchor": "risk-state",
    },
    "breadth_divergence": {
        "icon": "📉",
        "plain_en": "Breadth divergence — fewer names carrying the index",
        "plain_zh": "宽度背离 — 抬指数的个股在减少",
        "what_en": "The index is near its 1-year high while the share of stocks above their "
                   "200-day average is weak — a thinning tape. A narrowing-leadership caution.",
        "what_zh": "指数接近一年高点，但站上200日均线的个股占比偏弱 — 走势变薄。"
                   "属领导面收窄的警示。",
        "anchor": "risk-state",
    },
    "transition_state_change": {
        "icon": "🧭",
        "plain_en": "Regime radar moved — the market “weather” may be shifting",
        "plain_zh": "转换雷达变动 — 市场“天气”可能正在转变",
        "what_en": "Tracks whether the current market regime is holding or starting to "
                   "break down, based on how many warning flags are stacking up. A change "
                   "here is a cue to re-check your risk — not a trade on its own.",
        "what_zh": "根据累积的预警旗数量，追踪当前市场周期是稳固还是开始瓦解。"
                   "此处的变化是重新检视风险的提示 — 本身并非交易信号。",
        "anchor": "regime-radar",
    },
    "net_liquidity_roc_flip": {
        "icon": "💧",
        "plain_en": "Fed liquidity tide changed direction",
        "plain_zh": "美联储流动性潮汐转向",
        "what_en": "Net liquidity is the cash the Fed leaves sloshing through markets "
                   "(balance sheet − reverse-repo − the Treasury’s account). Its "
                   "4-week trend just flipped sign. Rising liquidity has historically been "
                   "a tailwind for stocks; falling is a headwind. Use it to lean more or "
                   "less cautious — it’s not a buy/sell button.",
        "what_zh": "净流动性是美联储留在市场中流动的资金（资产负债表 − 逆回购 − 财政部账户）。"
                   "其 4 周趋势刚刚反向。历史上流动性上升对股市是顺风，下降是逆风。"
                   "据此调整谨慎程度 — 它不是买卖按钮。",
        "anchor": "liquidity",
    },
    "hy_oas_widening": {
        "icon": "🚨",
        "plain_en": "Credit stress spiked — the bond market got nervous",
        "plain_zh": "信用压力骤升 — 债市转向紧张",
        "what_en": "“HY OAS” is the extra yield investors demand to hold risky (junk) "
                   "bonds — one of the market’s best early smoke detectors. A sharp "
                   "one-day jump means credit investors are suddenly pricing more risk, "
                   "often before stocks react. Worth taking seriously.",
        "what_zh": "“高收益债利差”是投资者持有高风险（垃圾）债券所要求的额外收益率 —"
                   "市场最灵敏的早期烟雾探测器之一。单日急升意味着信用投资者突然定价更高风险，"
                   "往往早于股市反应。值得认真对待。",
        "anchor": "credit",
    },
    "gex_flip_cross": {
        "icon": "🧲",
        "plain_en": "Options “gravity” flipped — bigger swings more likely",
        "plain_zh": "期权“引力”反转 — 波动可能加大",
        "what_en": "Dealer gamma (GEX) measures how options hedging pushes the market "
                   "around. Positive gamma damps moves (calmer); negative amplifies them "
                   "(sharper swings, both ways). This flag means that backdrop just "
                   "changed — expect the market to move more freely until it flips back.",
        "what_zh": "做市商 gamma（GEX）衡量期权对冲如何推动市场。正 gamma 抑制波动（更平静）；"
                   "负 gamma 放大波动（双向更剧烈）。此信号表示该背景刚刚改变 —"
                   "在它再次反转前，市场可能波动得更自由。",
        "anchor": "positioning",
    },
    "growth_confidence_floor": {
        "icon": "🎚️",
        "plain_en": "Growth read got muddy — trust the regime label less",
        "plain_zh": "增长信号变浑浊 — 降低对周期标签的信任",
        "what_en": "The regime is built from two dials — growth direction and inflation "
                   "direction. “Confidence” is how strongly the underlying indicators "
                   "agree. The growth dial just fell below a usable threshold, so it’s "
                   "now mixed. Lower confidence = size positions down and trust the radar "
                   "more than the label.",
        "what_zh": "周期由两个刻度盘构成 — 增长方向与通胀方向。“一致度”反映底层指标的"
                   "认同程度。增长刻度盘刚跌破可用阈值，目前信号混杂。一致度低 ="
                   "缩小仓位，相信雷达多于标签。",
        "anchor": "dials",
    },
    "inflation_confidence_floor": {
        "icon": "🎚️",
        "plain_en": "Inflation read got muddy — trust the regime label less",
        "plain_zh": "通胀信号变浑浊 — 降低对周期标签的信任",
        "what_en": "The regime is built from two dials — growth direction and inflation "
                   "direction. “Confidence” is how strongly the underlying indicators "
                   "agree. The inflation dial just fell below a usable threshold, so it’s "
                   "now mixed. Lower confidence = size positions down and trust the radar "
                   "more than the label.",
        "what_zh": "周期由两个刻度盘构成 — 增长方向与通胀方向。“一致度”反映底层指标的"
                   "认同程度。通胀刻度盘刚跌破可用阈值，目前信号混杂。一致度低 ="
                   "缩小仓位，相信雷达多于标签。",
        "anchor": "dials",
    },
    "sector_rs_cross_high": {
        "icon": "📈",
        "plain_en": "A sector broke into leadership",
        "plain_zh": "某板块跃升为领先",
        "what_en": "One sector’s strength versus the market just pushed into the top of "
                   "its recent range — it’s starting to lead. This describes where money "
                   "is rotating, not an instant buy. Check the sector’s heat and trigger "
                   "column before acting.",
        "what_zh": "某板块相对市场的强度刚冲入其近期区间的顶部 — 开始领先。这描述的是资金"
                   "轮动的方向，并非立即买入。行动前请查看该板块的热度与触发列。",
        "anchor": "sectors",
    },
    "sector_rs_cross_low": {
        "icon": "📉",
        "plain_en": "A sector fell out of favor",
        "plain_zh": "某板块失宠",
        "what_en": "One sector’s strength versus the market just dropped to the bottom of "
                   "its recent range — money is rotating out. Usually a reason to avoid or "
                   "trim, not to bottom-fish; wait for it to base and trigger again.",
        "what_zh": "某板块相对市场的强度刚跌至其近期区间的底部 — 资金正在流出。通常是回避或"
                   "减仓的理由，而非抄底；等它筑底并再次触发。",
        "anchor": "sectors",
    },
    "holdings_active_change": {
        "icon": "🐳",
        "plain_en": "A star fund manager made a notable move",
        "plain_zh": "明星基金经理出现显著动作",
        "what_en": "One of the tracked funds (ARK, etc.) meaningfully added to or cut a "
                   "position, after stripping out mechanical fund-flow effects — so it "
                   "reflects genuine conviction. It’s information about what active "
                   "managers are doing, not a recommendation to copy it.",
        "what_zh": "在剔除机械性资金流影响后，某只跟踪基金（如 ARK）显著加仓或减仓 —"
                   "因此反映了真实的信念。这是关于主动经理动作的信息，并非照搬的建议。",
        "anchor": "holdings",
    },
    "sector_holdings_accumulation": {
        "icon": "🐳",
        "plain_en": "A sector ETF is over-weighting a stock beyond its price move",
        "plain_zh": "某板块 ETF 对个股的权重提升超过其价格涨幅",
        "what_en": "Each sector SPDR’s top-10 weights are split into the part explained "
                   "by the stock’s own price move and a residual — weight that grew "
                   "MORE than price alone. A big residual means real buying flowed into "
                   "the name beyond market drift. Important honesty note: these SPDRs are "
                   "PASSIVE index funds, so the residual is index reconstitution / "
                   "float-weight flow (forced index-fund buying), not a discretionary "
                   "manager’s conviction. It’s a where-is-flow-being-forced signal, and a "
                   "cue to check the stock’s own technical setup — not an instant buy.",
        "what_zh": "每只板块 SPDR 的前十大权重被拆分为“由个股自身价格变动解释的部分”与“残差”"
                   "——即权重增长超过价格涨幅的部分。残差较大意味着除市场漂移外，确有真实买盘流入"
                   "该股。重要的诚实提示：这些 SPDR 是被动指数基金，故残差代表指数再平衡／流通权重"
                   "调整带来的资金流（指数基金的被动强制买入），而非主动经理的信念。这是“资金被强制"
                   "导向何处”的信号，也提示去核查该股自身的技术形态——并非立即买入。",
        "anchor": "accumulation",
    },
    "circuit_breaker_open": {
        "icon": "🔌",
        "plain_en": "A data source went dark",
        "plain_zh": "某数据源中断",
        "what_en": "A feed this dashboard relies on failed several runs in a row, so it’s "
                   "paused until it recovers. Any signals that depend on it automatically "
                   "lose confidence until it’s back. This is a plumbing notice, not a "
                   "market signal.",
        "what_zh": "本仪表盘依赖的某个数据源连续多次失败，已暂停直至恢复。依赖它的信号会自动"
                   "降低置信度，直到其恢复。这是系统管线提示，并非市场信号。",
        "anchor": "health",
    },
}


# Conviction layer — how much WEIGHT each alert deserves, kept separate from the
# copy blocks above. `tier` drives prioritisation (act > watch > context),
# decoupled from the per-fire `severity`. `edge` is a one-line, grounded "how much
# to trust this" note. The macro engine has no per-rule backtest, so these are
# documented-reasoning calls — and they surface the post-2021 liquidity-edge decay
# the Bitcoin Vector calibration actually measured (net_liq_roc: DIRECTIONAL,
# post-half weak). The vector engine derives its own conviction from
# data/vector/calibration.json (see engine/btc_alerts.py).
_DEFAULT_CONVICTION = {"tier": "watch", "edge_en": "", "edge_zh": ""}

ALERT_CONVICTION: dict[str, dict] = {
    "transition_state_change": {"tier": "act",
        "edge_en": "High — a regime shift re-prices everything downstream.",
        "edge_zh": "高 — 周期转变会重新定价其下游的一切。"},
    "hy_oas_widening": {"tier": "act",
        "edge_en": "High — credit is the market's best early smoke detector.",
        "edge_zh": "高 — 信用市场是最灵敏的早期烟雾探测器。"},
    "net_liquidity_roc_flip": {"tier": "watch",
        "edge_en": "Medium — a documented tail/headwind, but the liquidity edge "
                   "weakened post-2021 (ETF era). Lean on it, don't trade it.",
        "edge_zh": "中 — 有据可查的顺／逆风，但流动性优势在 2021 年后（ETF 时代）减弱。"
                   "据此微调，而非直接交易。"},
    "gex_flip_cross": {"tier": "watch",
        "edge_en": "Medium — changes the volatility backdrop, not the direction.",
        "edge_zh": "中 — 改变的是波动背景，而非方向。"},
    "growth_confidence_floor": {"tier": "context",
        "edge_en": "Context — a confidence drop, not a directional call. Size down.",
        "edge_zh": "背景 — 这是置信度下降，而非方向判断。缩小仓位。"},
    "inflation_confidence_floor": {"tier": "context",
        "edge_en": "Context — a confidence drop, not a directional call. Size down.",
        "edge_zh": "背景 — 这是置信度下降，而非方向判断。缩小仓位。"},
    "sector_rs_cross_high": {"tier": "context",
        "edge_en": "Context — descriptive rotation, not a timing signal.",
        "edge_zh": "背景 — 描述性的轮动，而非择时信号。"},
    "sector_rs_cross_low": {"tier": "context",
        "edge_en": "Context — descriptive rotation, not a timing signal.",
        "edge_zh": "背景 — 描述性的轮动，而非择时信号。"},
    "holdings_active_change": {"tier": "context",
        "edge_en": "Context — what an active manager did, not a recommendation.",
        "edge_zh": "背景 — 主动经理的动作，并非建议。"},
    "sector_holdings_accumulation": {"tier": "context",
        "edge_en": "Context — passive index-flow, not discretionary conviction.",
        "edge_zh": "背景 — 被动指数资金流，而非主动信念。"},
    "circuit_breaker_open": {"tier": "context",
        "edge_en": "Plumbing — data health, not a market signal.",
        "edge_zh": "管线 — 数据健康度，而非市场信号。"},
    "risk_state_elevated": {"tier": "act",
        "edge_en": "High — the equity-internal early-warning the credit gauge misses. "
                   "De-risk response is sizing, not selection.",
        "edge_zh": "高 — 信用指标看不到的股票内部早期预警。应对是调仓位，而非选股。"},
    "hidden_fragility": {"tier": "watch",
        "edge_en": "Medium — a calm-over-weak CONTEXT (the conjunction matters, not low "
                   "VIX alone). Size down, don't chase.",
        "edge_zh": "中 — 平静掩盖走弱的背景（关键是组合而非单看低VIX）。缩小仓位，不要追高。"},
    "breadth_divergence": {"tier": "watch",
        "edge_en": "Medium — fewer names carrying the index; a thinning-tape caution, not a timer.",
        "edge_zh": "中 — 抬指数的个股在减少；属于宽度变薄的警示，而非择时。"},
}


def alert_view(rule: str, severity: str, message: str, message_zh: str = "") -> dict:
    """Enrich a stored alert (rule/severity/message) with plain-English copy, an
    icon, the dashboard panel anchor it deep-links to, and a conviction tier +
    grounded edge note. Unknown rules fall back to generic defaults so a new rule
    still renders sensibly."""
    return {"rule": rule, "severity": severity, "message": message,
            "message_zh": message_zh,
            **ALERT_META.get(rule, _DEFAULT_META),
            **ALERT_CONVICTION.get(rule, _DEFAULT_CONVICTION)}


def alert_views(alerts) -> list[dict]:
    """Map a list of Alert objects or {rule,severity,message} dicts to enriched
    view dicts, preserving order (callers pass them already severity-sorted)."""
    out = []
    for a in alerts:
        if isinstance(a, Alert):
            out.append(alert_view(a.rule, a.severity, a.message, a.message_zh))
        else:
            out.append(alert_view(a.get("rule", ""), a.get("severity", "info"),
                                  a.get("message", ""), a.get("message_zh", "")))
    return out
