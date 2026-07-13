"""Hong Kong alert rules — a clone of engine/china_alerts.py adapted to HK-native
change detectors, evaluated on the HK engine's daily output.

Every rule compares TODAY against YESTERDAY (or a trailing window), so alerts fire
on *changes* — a crossing, a sign flip, a state escalation — never on a level being
high. Fired alerts append to data/hk_alerts/alerts_log.parquet keyed by
(date, rule, message); re-running the same day is idempotent.

DISPLAY-ONLY INVARIANT: nothing here feeds engine/hk_axes.py, engine/hk_regime.py
or engine/hk_playbook.py. Alerts are surfaced notifications, NEVER scored inputs.

Everything degrades gracefully: a missing input skips its rule, one rule raising
can never kill the rest, every public function returns plain-Python data and never
raises into a caller. Bilingual: every alert carries `message` AND `message_zh`.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass

import numpy as np
import pandas as pd

from engine.indicators import pct_rank_window
from lib import config, store

log = logging.getLogger(__name__)


@dataclass
class Alert:
    rule: str
    severity: str          # "info" | "warn" | "high"
    message: str
    message_zh: str = ""


# --- shared helpers -----------------------------------------------------------
def _latest_json() -> dict:
    import json
    p = config.data_dir() / "hk_regime" / "latest.json"
    if not p.exists():
        return {}
    try:
        with open(p) as fh:
            return json.load(fh)
    except Exception as e:  # noqa: BLE001
        log.warning("hk_alerts: latest.json unreadable: %s", e)
        return {}


def _regime_history() -> pd.DataFrame | None:
    df = store.read("hk_regime", "regime_history")
    if df is None or df.empty:
        return None
    df = df.copy()
    df.index = pd.to_datetime(df.index)
    return df.sort_index()


def _col(f: pd.DataFrame | None, name: str) -> pd.Series | None:
    if f is None or name not in f.columns or f[name].isna().all():
        return None
    return f[name].dropna()


def _store_series(group: str, name: str, col: str) -> pd.Series | None:
    df = store.read(group, name)
    if df is None or df.empty or col not in df.columns:
        return None
    s = df[col].dropna()
    return s if len(s) else None


def _z_last(s: pd.Series, window: int = 252) -> float | None:
    s = s.dropna()
    if len(s) < max(20, window // 4):
        return None
    m = float(s.tail(window).mean())
    sd = float(s.tail(window).std())
    if not sd or not np.isfinite(sd):
        return None
    return (float(s.iloc[-1]) - m) / sd


def _crossed_up(s: pd.Series, thr: float) -> bool:
    s = s.dropna()
    return len(s) >= 2 and s.iloc[-2] < thr <= s.iloc[-1]


def _crossed_down(s: pd.Series, thr: float) -> bool:
    s = s.dropna()
    return len(s) >= 2 and s.iloc[-2] >= thr > s.iloc[-1]


# --- individual rules ---------------------------------------------------------
def hk_regime_transition(f, regime, latest) -> Alert | None:
    """Evidence building toward a quad flip (pending_quad held >= 3d, before the
    7-day label flip)."""
    pq = latest.get("pending_quad")
    pd_days = latest.get("pending_days") or 0
    if pq not in ("Q1", "Q2", "Q3", "Q4") or int(pd_days) < 3:
        return None
    names = {"Q1": ("Goldilocks", "理想增长"), "Q2": ("Reflation", "再通胀"),
             "Q3": ("Stagflation", "滞胀"), "Q4": ("Growth scare", "增长恐慌")}
    en, zh = names.get(pq, (pq, pq))
    return Alert("hk_regime_transition", "warn",
                 f"Regime watch: evidence building toward {en} ({pq}) — "
                 f"{int(pd_days)} day(s) so far; the quad label flips after 7",
                 message_zh=f"周期预警：证据正在累积，指向 {zh}（{pq}）— "
                            f"已持续 {int(pd_days)} 天；标签将在第 7 天翻转")


def hk_confidence_floor(f, regime, latest) -> list[Alert]:
    """Regime / axis confidence downcrossing 0.30 vs the prior run."""
    floor = 0.30
    hist = _regime_history()
    if hist is None or len(hist) < 2:
        return []
    out: list[Alert] = []
    pairs = [("regime", "regime_confidence", "Regime", "周期"),
             ("growth", "growth_confidence", "Growth axis", "增长轴"),
             ("inflation", "inflation_confidence", "Inflation axis", "通胀轴")]
    for key, col, en, zh in pairs:
        if col not in hist.columns:
            continue
        s = hist[col].dropna()
        if len(s) < 2:
            continue
        prev, cur = float(s.iloc[-2]), float(s.iloc[-1])
        if prev >= floor > cur:
            out.append(Alert(f"hk_{key}_confidence_floor", "warn",
                             f"{en} confidence dropped below {floor:.0%}: "
                             f"{prev:.0%} -> {cur:.0%} — trust the label less, size down",
                             message_zh=f"{zh}一致度跌破 {floor:.0%}："
                                        f"{prev:.0%} -> {cur:.0%} — 降低对标签的信任，缩小仓位"))
    return out


def hk_risk_state_flip(f, regime, latest) -> Alert | None:
    """The global-risk composite crossing the +/- risk_on_z bands vs the prior day —
    HK's headline driver flipping risk-on / risk-off."""
    hist = _regime_history()
    if hist is None or "global_score" not in hist.columns:
        return None
    s = hist["global_score"].dropna()
    if len(s) < 2:
        return None
    thr = float(config.load().get("hk", {}).get("global_factors", {}).get("risk_on_z", 0.3))
    if _crossed_up(s, thr):
        return Alert("hk_risk_on", "info",
                     f"Global risk overlay flipped RISK-ON (now {s.iloc[-1]:+.2f}, "
                     f"was {s.iloc[-2]:+.2f}) — HK's primary driver turned constructive",
                     message_zh=f"全球风险开关转为「偏好风险」（现 {s.iloc[-1]:+.2f}，"
                                f"前 {s.iloc[-2]:+.2f}）— 香港主驱动转向积极")
    if _crossed_down(s, -thr):
        return Alert("hk_risk_off", "warn",
                     f"Global risk overlay flipped RISK-OFF (now {s.iloc[-1]:+.2f}, "
                     f"was {s.iloc[-2]:+.2f}) — HK's primary driver turned defensive",
                     message_zh=f"全球风险开关转为「避险」（现 {s.iloc[-1]:+.2f}，"
                                f"前 {s.iloc[-2]:+.2f}）— 香港主驱动转向防御")
    return None


def hk_peg_weak_side(f, regime, latest) -> Alert | None:
    """USD/HKD pushing toward the 7.85 weak-side convertibility undertaking — the
    HKMA defends it by draining the Aggregate Balance (HK funding tightens)."""
    u = _col(f, "usdhkd")
    if u is None or len(u) < 2:
        return None
    try:
        from engine import hk_global
        pf = hk_global.peg_frame(u)
    except Exception:  # noqa: BLE001
        return None
    if pf.empty or "peg_distance" not in pf.columns:
        return None
    dist = pf["peg_distance"].dropna()
    if _crossed_up(dist, 0.75):
        return Alert("hk_peg_weak_side", "warn",
                     f"HKD pushed toward the 7.85 weak side (USD/HKD {float(u.iloc[-1]):.4f}, "
                     f"{dist.iloc[-1] * 100:.0f}% across the band) — capital-outflow pressure; "
                     f"HKMA defence drains the Aggregate Balance and tightens HK funding",
                     message_zh=f"港元逼近 7.85 弱方（美元兑港元 {float(u.iloc[-1]):.4f}，"
                                f"区间 {dist.iloc[-1] * 100:.0f}%）— 资本外流压力；金管局护盘"
                                f"将抽走总结余、收紧香港资金面")
    if _crossed_down(dist, 0.25):
        return Alert("hk_peg_strong_side", "info",
                     f"HKD pushed toward the 7.75 strong side (USD/HKD {float(u.iloc[-1]):.4f}, "
                     f"{dist.iloc[-1] * 100:.0f}% across the band) — capital-inflow pressure; "
                     f"HKMA injects liquidity, an HK funding tailwind",
                     message_zh=f"港元逼近 7.75 强方（美元兑港元 {float(u.iloc[-1]):.4f}，"
                                f"区间 {dist.iloc[-1] * 100:.0f}%）— 资本流入压力；金管局注入"
                                f"流动性，香港资金面顺风")
    return None


def hibor_spike(f, regime, latest) -> Alert | None:
    """Overnight HIBOR jumping >= 1y-z of +2 — an HK funding squeeze."""
    s = _col(f, "hibor_on")
    if s is None or len(s) < 60:
        return None
    z = _z_last(s, 252)
    if z is None or z < 2.0:
        return None
    return Alert("hibor_spike", "warn",
                 f"Overnight HIBOR spiked to {z:+.1f}σ (now {float(s.iloc[-1]):.2f}%) — "
                 f"HK funding is tightening; a squeeze pressures rate-sensitive HK names",
                 message_zh=f"隔夜 HIBOR 飙升至 {z:+.1f}σ（现 {float(s.iloc[-1]):.2f}%）— "
                            f"香港资金面收紧；挤压利率敏感的港股")


def southbound_extreme(f, regime, latest) -> Alert | None:
    """Southbound (mainland-into-HK smart money) daily net 1y-z reaching +/-2."""
    s = _store_series("china_connect", "southbound", "net")
    if s is None or len(s) < 60:
        return None
    z = _z_last(s, 252)
    if z is None:
        return None
    last = float(s.iloc[-1])
    if z >= 2.0:
        return Alert("southbound_surge", "info",
                     f"Southbound smart-money net buying surged to {z:+.1f}σ "
                     f"(net {last:+,.0f}, 1y window) — conviction inflow into HK",
                     message_zh=f"南向资金净买入激增至 {z:+.1f}σ"
                                f"（净额 {last:+,.0f}，1 年窗口）— 信念流入港股")
    if z <= -2.0:
        return Alert("southbound_exodus", "warn",
                     f"Southbound smart-money net selling spiked to {z:+.1f}σ "
                     f"(net {last:+,.0f}, 1y window) — conviction outflow from HK",
                     message_zh=f"南向资金净卖出骤增至 {z:+.1f}σ"
                                f"（净额 {last:+,.0f}，1 年窗口）— 信念流出港股")
    return None


def hk_roro_flip(f, regime, latest) -> Alert | None:
    """The display-only RORO composite crossing the +/-0.35 bands vs prior."""
    try:
        from engine import hk_conditions
        rf = hk_conditions.roro_frame(f) if f is not None else None
        if rf is None or "roro" not in rf.columns:
            return None
        s = rf["roro"].dropna()
        if len(s) < 2:
            return None
        if _crossed_up(s, 0.35):
            return Alert("hk_roro_flip_on", "info",
                         f"Cross-asset RORO crossed into RISK-ON "
                         f"(now {s.iloc[-1]:+.2f}, was {s.iloc[-2]:+.2f}) — "
                         f"HK risk appetite turned up",
                         message_zh=f"跨资产 RORO 上穿进入「偏好风险」"
                                    f"（现 {s.iloc[-1]:+.2f}，前 {s.iloc[-2]:+.2f}）— "
                                    f"香港风险偏好转暖")
        if _crossed_down(s, -0.35):
            return Alert("hk_roro_flip_off", "warn",
                         f"Cross-asset RORO crossed into RISK-OFF "
                         f"(now {s.iloc[-1]:+.2f}, was {s.iloc[-2]:+.2f}) — "
                         f"HK risk appetite turned down",
                         message_zh=f"跨资产 RORO 下穿进入「避险」"
                                    f"（现 {s.iloc[-1]:+.2f}，前 {s.iloc[-2]:+.2f}）— "
                                    f"香港风险偏好转弱")
    except Exception as e:  # noqa: BLE001
        log.warning("hk_roro_flip rebuild failed: %s", e)
    return None


def vhsi_spike(f, regime, latest) -> Alert | None:
    """VHSI (HK implied vol) jumping >= 15% day-over-day OR upcrossing its 90th
    percentile — a fear spike."""
    s = _store_series("hk", "^HSIL", "close")
    if s is None or len(s) < 60:
        return None
    dod = s.pct_change().iloc[-1]
    pct = (pct_rank_window(s, 252) * 100).dropna()
    jumped = pd.notna(dod) and float(dod) >= 0.15
    crossed_90 = len(pct) >= 2 and _crossed_up(pct, 90.0)
    if not (jumped or crossed_90):
        return None
    what = (f"jumped {float(dod) * 100:+.0f}% day-over-day" if jumped
            else f"crossed its 90th percentile ({pct.iloc[-1]:.0f}th)")
    what_zh = (f"单日跳升 {float(dod) * 100:+.0f}%" if jumped
               else f"上穿第 90 百分位（现第 {pct.iloc[-1]:.0f}）")
    return Alert("vhsi_spike", "warn",
                 f"HK implied vol (VHSI) {what} to {float(s.iloc[-1]):.1f} — "
                 f"fear is repricing",
                 message_zh=f"港股隐含波动率（VHSI）{what_zh}至 {float(s.iloc[-1]):.1f} — "
                            f"恐慌正在重新定价")


def fear_euphoria_extreme(f, regime, latest) -> Alert | None:
    """Fear<->Euphoria reaching euphoria (>=88) or panic (<=12). Reads latest."""
    fe = (latest or {}).get("fear_euphoria") or {}
    score = fe.get("fe_score")
    if score is None:
        return None
    score = float(score)
    band = fe.get("band", "")
    band_zh = fe.get("band_zh", band)
    if score >= 88:
        return Alert("fear_euphoria_extreme", "warn",
                     f"Sentiment reached the euphoria-caution band ({score:.0f}/100, {band}) — "
                     f"historically a caution zone; crowding is one-sided, not a forecast",
                     message_zh=f"情绪进入欣喜警惕区（{score:.0f}/100，{band_zh}）— 历史上的"
                                f"警惕区；拥挤一边倒，并非预测")
    if score <= 12:
        return Alert("fear_euphoria_capitulation", "info",
                     f"Sentiment is at PANIC ({score:.0f}/100, {band}) — a contrarian "
                     f"capitulation band; fear, not a forecast",
                     message_zh=f"情绪处于「恐慌」（{score:.0f}/100，{band_zh}）— 逆向的"
                                f"投降区；是恐慌而非预测")
    return None


def ah_premium_extreme(f, regime, latest) -> Alert | None:
    """The A/H premium reaching its own-history extreme: a wide premium (>=85th pct)
    means HK-listed H is the cheaper way to own the same company (rotation context)."""
    try:
        from engine.hk_ah import ah_basket_series
        s = ah_basket_series()
    except Exception:  # noqa: BLE001
        s = None
    if s is None or len(s) < 252:
        return None
    pct = (pct_rank_window(s, 252 * 3) * 100).dropna()
    if len(pct) < 2:
        return None
    if _crossed_up(pct, 85.0):
        return Alert("ah_premium_wide", "info",
                     f"A/H premium widened to its {pct.iloc[-1]:.0f}th percentile "
                     f"(now {float(s.iloc[-1]):.0f}%) — mainland A-shares dear vs the HK-listed "
                     f"H twin; HK is the cheaper way to own the same names",
                     message_zh=f"AH 溢价走阔至第 {pct.iloc[-1]:.0f} 百分位"
                                f"（现 {float(s.iloc[-1]):.0f}%）— A 股相对 H 股偏贵；"
                                f"港股是更便宜的同股敞口")
    if _crossed_down(pct, 15.0):
        return Alert("ah_premium_narrow", "info",
                     f"A/H premium narrowed to its {pct.iloc[-1]:.0f}th percentile "
                     f"(now {float(s.iloc[-1]):.0f}%) — the H/HK discount has compressed",
                     message_zh=f"AH 溢价收窄至第 {pct.iloc[-1]:.0f} 百分位"
                                f"（现 {float(s.iloc[-1]):.0f}%）— H/港股折让已压缩")
    return None


def hk_drawdown_elevated(f, regime, latest) -> Alert | None:
    """The display-only drawdown-risk gauge crossing UP through ~60 (UNCALIBRATED)."""
    thr = 60.0
    try:
        from engine import hk_conditions
        rec_series, _ = hk_conditions._recession_score_series(f)
        dd = hk_conditions._drawdown_score_series(f, rec_series).dropna()
        if len(dd) < 2 or not _crossed_up(dd, thr):
            return None
        band = ((latest or {}).get("conditions") or {}).get("drawdown_risk", {}).get("band")
        band_s = f", band {band}" if band else ""
        return Alert("hk_drawdown_elevated", "warn",
                     f"HK drawdown-risk gauge crossed up through {thr:.0f}/100 "
                     f"(now {dd.iloc[-1]:.0f}{band_s}) — stress legs stacking; "
                     f"UNCALIBRATED, read as attention not a P(drawdown) forecast",
                     message_zh=f"香港回撤风险指标上穿 {thr:.0f}/100"
                                f"（现 {dd.iloc[-1]:.0f}{band_s}）— 压力因子累积；"
                                f"未校准，作为关注信号而非回撤概率预测")
    except Exception as e:  # noqa: BLE001
        log.warning("hk_drawdown_elevated rebuild failed: %s", e)
    return None


def market_driver_clear(f, regime, latest) -> Alert | None:
    """A single macro driver dominating the tape (verdict 'clear' + 'high' conf)."""
    md = (latest or {}).get("market_drivers") or {}
    if md.get("verdict") != "clear" or md.get("confidence") != "high":
        return None
    pl = md.get("primary_label") or md.get("primary") or "a single driver"
    pl_zh = md.get("primary_label_zh") or pl
    return Alert("market_driver_clear", "info",
                 f"One macro driver is clearly dominating the HK tape today: {pl} "
                 f"(high confidence) — moves are being driven by this, not breadth",
                 message_zh=f"今日单一宏观驱动明显主导港股盘面：{pl_zh}"
                            f"（高置信）— 行情由此驱动，而非全面宽度")


def hk_circuit_breaker(f, regime, latest) -> list[Alert]:
    """Fires the day an hk_* / hkma data source's breaker opens."""
    from collectors.base import CIRCUIT_BREAKER_FAILS
    breaker = store.read_status().get("circuit_breaker", {})
    out = []
    for src, n in breaker.items():
        s = str(src)
        if not (s.startswith("hk") or s == "hkma"):
            continue
        if n == CIRCUIT_BREAKER_FAILS:
            out.append(Alert("hk_circuit_breaker", "high",
                             f"HK source '{src}' marked dead after {n} consecutive "
                             f"failures — collector skipped until it recovers; affected "
                             f"signals degrade",
                             message_zh=f"香港数据源 '{src}' 连续 {n} 次失败后被标记为中断 — "
                                        f"采集器暂停直至恢复；相关信号置信度下降"))
    return out


# --- runner -------------------------------------------------------------------
_SINGLE_RULES = [
    hk_regime_transition, hk_risk_state_flip, hk_peg_weak_side, hibor_spike,
    southbound_extreme, hk_roro_flip, vhsi_spike, fear_euphoria_extreme,
    ah_premium_extreme, hk_drawdown_elevated, market_driver_clear,
]
_MULTI_RULES = [hk_confidence_floor, hk_circuit_breaker]

_SEV_ORDER = {"high": 0, "warn": 1, "info": 2}


def evaluate(f: pd.DataFrame | None = None, regime: pd.DataFrame | None = None,
             latest: dict | None = None) -> list[Alert]:
    """Run every HK alert rule against today's engine output, severity-sorted."""
    if latest is None:
        latest = _latest_json()
    if f is None:
        try:
            from engine.hk_inputs import build_features
            f = build_features()
        except Exception as e:  # noqa: BLE001
            log.warning("hk_alerts: build_features failed: %s", e)
            f = None
    if regime is None:
        regime = _regime_history()

    alerts: list[Alert] = []
    for rule in _SINGLE_RULES:
        try:
            a = rule(f, regime, latest)
            if a:
                alerts.append(a)
        except Exception as e:  # noqa: BLE001
            log.error("hk alert rule %s failed: %s", rule.__name__, e)
    for rule in _MULTI_RULES:
        try:
            alerts.extend(rule(f, regime, latest) or [])
        except Exception as e:  # noqa: BLE001
            log.error("hk alert rule %s failed: %s", rule.__name__, e)
    return sorted(alerts, key=lambda a: _SEV_ORDER.get(a.severity, 9))


def _log_path():
    return config.data_dir() / "hk_alerts" / "alerts_log.parquet"


def log_and_dedup(alerts: list[Alert], asof) -> list[dict]:
    """Append fired alerts to the log (drop those already logged for `asof`) and
    return TODAY's fired alerts as enriched view dicts. Idempotent."""
    asof = pd.Timestamp(asof)
    p = _log_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    cols = ["date", "rule", "severity", "message", "message_zh"]
    old = pd.read_parquet(p) if p.exists() else pd.DataFrame(columns=cols)
    for c in cols:
        if c not in old.columns:
            old[c] = "" if c in ("message_zh",) else old.get(c, "")
    today = str(asof.date())
    seen = set(zip(old["date"].astype(str), old["rule"].astype(str),
                   old["message"].astype(str)))
    fresh = [a for a in alerts if (today, a.rule, a.message) not in seen]
    if fresh:
        new = pd.DataFrame([{"date": today, "rule": a.rule, "severity": a.severity,
                             "message": a.message, "message_zh": a.message_zh}
                            for a in fresh])
        pd.concat([old[cols], new], ignore_index=True).to_parquet(p)
    return today_views(asof)


def today_views(asof=None) -> list[dict]:
    p = _log_path()
    if not p.exists():
        return []
    df = pd.read_parquet(p)
    if df.empty:
        return []
    day = str((pd.Timestamp(asof) if asof is not None else pd.Timestamp.today()).date())
    rows = df[df["date"].astype(str) == day]
    if rows.empty:
        return []
    # per-rule dedup collapses same-day wording drift — EXCEPT the circuit-breaker
    # rule, where each same-rule row is a DIFFERENT dark source: keep one row per
    # message and let alert_views collapse them count-aware ("N HK data sources
    # went dark").
    is_breaker = rows["rule"] == "hk_circuit_breaker"
    rows = pd.concat([
        rows[~is_breaker].drop_duplicates(subset=["rule"], keep="last"),
        rows[is_breaker].drop_duplicates(subset=["rule", "message"], keep="last"),
    ]).sort_index()
    rows = rows.sort_values("severity", key=lambda s: s.map(lambda x: _SEV_ORDER.get(x, 9)))
    return alert_views(rows.to_dict(orient="records"))


def fired_today(latest: dict | None = None) -> list[dict]:
    if latest is None:
        latest = _latest_json()
    asof = pd.Timestamp(latest.get("date")) if latest.get("date") else pd.Timestamp.today()
    return log_and_dedup(evaluate(latest=latest), asof)


def recent_alerts(days: int = 7) -> pd.DataFrame:
    p = _log_path()
    if not p.exists():
        return pd.DataFrame(columns=["date", "rule", "severity", "message", "message_zh"])
    df = pd.read_parquet(p)
    cutoff = (pd.Timestamp.today() - pd.Timedelta(days=days)).date()
    return df[pd.to_datetime(df["date"]).dt.date >= cutoff]


# --- presentation layer -------------------------------------------------------
_DEFAULT_META = {
    "icon": "🔔",
    "plain_en": "An HK macro signal changed — check the dashboard read",
    "plain_zh": "一个香港宏观信号变化 — 查看仪表盘解读",
    "what_en": "An automated HK macro signal changed state. Open the HK dashboard for "
               "the full read.",
    "what_zh": "一个自动香港宏观信号发生了状态变化。打开香港仪表盘查看完整解读。",
    "anchor": "",
}

ALERT_META: dict[str, dict] = {
    "hk_regime_transition": {
        "icon": "🧭",
        "plain_en": "Regime radar moved — the HK quad may be flipping",
        "plain_zh": "周期雷达变动 — 香港象限可能正在翻转",
        "what_en": "The growth/inflation quad needs a pending reading to hold a week "
                   "before the label flips. Evidence is now stacking toward a new quad — "
                   "re-check your tilt before it confirms.",
        "what_zh": "增长／通胀象限需「待定」读数持续一周才翻转标签。证据正在累积指向新的象限 —"
                   "在确认前重新检视配置。",
        "anchor": "regime-radar"},
    "hk_regime_confidence_floor": {
        "icon": "🎚️", "plain_en": "Regime read got muddy — trust the quad less",
        "plain_zh": "周期信号变浑浊 — 降低对象限的信任",
        "what_en": "Confidence (how strongly the indicators agree on the quad) fell below "
                   "a usable threshold. Size down and lean on the conditions lens.",
        "what_zh": "置信度（指标对象限的认同程度）跌破可用阈值。缩小仓位，更依赖条件透镜。",
        "anchor": "regime-radar"},
    "hk_growth_confidence_floor": {
        "icon": "🎚️", "plain_en": "Growth read got muddy — trust the quad less",
        "plain_zh": "增长信号变浑浊 — 降低对象限的信任",
        "what_en": "The growth dial's indicators stopped agreeing. The growth half of the "
                   "quad is now mixed — size down.",
        "what_zh": "增长刻度盘的指标停止一致。象限的增长一侧现已混杂 — 缩小仓位。",
        "anchor": "regime-radar"},
    "hk_inflation_confidence_floor": {
        "icon": "🎚️", "plain_en": "Inflation read got muddy — trust the quad less",
        "plain_zh": "通胀信号变浑浊 — 降低对象限的信任",
        "what_en": "The inflation dial's indicators stopped agreeing. The inflation half "
                   "of the quad is now mixed — size down.",
        "what_zh": "通胀刻度盘的指标停止一致。象限的通胀一侧现已混杂 — 缩小仓位。",
        "anchor": "regime-radar"},
    "hk_risk_on": {
        "icon": "🟢", "plain_en": "Global risk overlay flipped RISK-ON",
        "plain_zh": "全球风险开关转「开」",
        "what_en": "HK's primary high-frequency driver is the global risk-on/off composite "
                   "(dollar, VIX, S&P, copper/gold, EM). It just crossed into risk-ON — a "
                   "constructive backdrop for HK. A concurrent state, not a forecast.",
        "what_zh": "香港最主要的高频驱动是全球风险开关（美元、VIX、标普、铜金比、新兴市场）。"
                   "它刚上穿进入「偏好风险」— 对香港是积极背景。这是同步状态，并非预测。",
        "anchor": "global-risk"},
    "hk_risk_off": {
        "icon": "🔴", "plain_en": "Global risk overlay flipped RISK-OFF",
        "plain_zh": "全球风险开关转「关」",
        "what_en": "HK's primary driver (the global risk composite) just crossed into "
                   "risk-OFF — a defensive backdrop for HK. A concurrent state, not a "
                   "forecast.",
        "what_zh": "香港主驱动（全球风险综合指标）刚下穿进入「避险」— 对香港是防御背景。"
                   "同步状态，并非预测。",
        "anchor": "global-risk"},
    "hk_peg_weak_side": {
        "icon": "🪝", "plain_en": "HKD pushed toward the 7.85 weak side",
        "plain_zh": "港元逼近 7.85 弱方",
        "what_en": "The HKD trades in a 7.75–7.85 convertibility band. Toward 7.85 = "
                   "capital outflow; the HKMA defends it by buying HKD, which drains the "
                   "Aggregate Balance and tightens HK funding — a real HSI headwind.",
        "what_zh": "港元在 7.75–7.85 兑换区间交易。趋向 7.85 = 资本外流；金管局买入港元护盘，"
                   "抽走总结余、收紧香港资金面 — 是恒指的实质逆风。",
        "anchor": "peg-funding"},
    "hk_peg_strong_side": {
        "icon": "🪝", "plain_en": "HKD pushed toward the 7.75 strong side",
        "plain_zh": "港元逼近 7.75 强方",
        "what_en": "Toward the 7.75 strong side = capital inflow; the HKMA injects HKD "
                   "liquidity, an HK funding tailwind. A concurrent flow state.",
        "what_zh": "趋向 7.75 强方 = 资本流入；金管局注入港元流动性，是香港资金面顺风。"
                   "同步的资金状态。",
        "anchor": "peg-funding"},
    "hibor_spike": {
        "icon": "⚡", "plain_en": "Overnight HIBOR spiked — funding squeeze",
        "plain_zh": "隔夜 HIBOR 飙升 — 资金挤压",
        "what_en": "HIBOR is HK's interbank rate (it shadows the Fed via the peg). A sharp "
                   "overnight spike signals a funding squeeze that pressures leveraged and "
                   "rate-sensitive HK names.",
        "what_zh": "HIBOR 是香港银行同业拆息（经联汇跟随美联储）。隔夜急升预示资金挤压，"
                   "挤压杠杆与利率敏感的港股。",
        "anchor": "peg-funding"},
    "southbound_surge": {
        "icon": "🐉", "plain_en": "Southbound smart money surged in",
        "plain_zh": "南向资金大举流入",
        "what_en": "Southbound flow is mainland money buying HK via Stock Connect — a "
                   "watched smart-money gauge. Net buying just spiked to an extreme; "
                   "confirm against price.",
        "what_zh": "南向资金是内地资金通过港股通买入香港 — 受关注的聪明钱指标。净买入刚飙升"
                   "至极值；请与价格印证。",
        "anchor": "southbound"},
    "southbound_exodus": {
        "icon": "🐉", "plain_en": "Southbound smart money rushed out",
        "plain_zh": "南向资金大举流出",
        "what_en": "Mainland smart-money buying of HK just swung to an extreme net OUTFLOW "
                   "— risk appetite fading; confirm against price.",
        "what_zh": "内地聪明钱买入香港刚摆向极端净流出 — 风险偏好消退；请与价格印证。",
        "anchor": "southbound"},
    "hk_roro_flip_on": {
        "icon": "🟢", "plain_en": "Cross-asset risk appetite turned ON",
        "plain_zh": "跨资产风险偏好转「开」",
        "what_en": "The RORO composite blends global risk, China spillover and HK-local "
                   "legs into one risk-on/off read. It just crossed into risk-ON. A regime "
                   "read of the tape's mood, never scored.",
        "what_zh": "RORO 综合指标把全球风险、中国外溢与香港本地分腿融合为一个风险开关读数。"
                   "它刚上穿进入「偏好风险」。盘面情绪的区制解读，从不评分。",
        "anchor": "fear-euphoria"},
    "hk_roro_flip_off": {
        "icon": "🔴", "plain_en": "Cross-asset risk appetite turned OFF",
        "plain_zh": "跨资产风险偏好转「关」",
        "what_en": "The RORO composite just crossed into risk-OFF — HK's cross-asset mood "
                   "turned defensive. A regime read, never scored.",
        "what_zh": "RORO 综合指标刚下穿进入「避险」— 香港跨资产情绪转向防御。区制解读，从不评分。",
        "anchor": "fear-euphoria"},
    "vhsi_spike": {
        "icon": "⚡", "plain_en": "HK fear gauge (VHSI) spiked",
        "plain_zh": "港股恐慌指标（VHSI）骤升",
        "what_en": "VHSI is the HSI implied-volatility / fear gauge (HK's VIX). A sharp "
                   "jump or a push into its top decile means traders are paying up for "
                   "protection — expect bigger swings.",
        "what_zh": "VHSI 是恒指隐含波动率／恐慌指标（港版 VIX）。急升或冲入前十分位意味着"
                   "交易者在为保护付高价 — 预期波动加大。",
        "anchor": "fear-euphoria"},
    "fear_euphoria_extreme": {
        "icon": "🥵", "plain_en": "Sentiment hit EUPHORIA — caution",
        "plain_zh": "情绪触及「欣喜」— 警惕",
        "what_en": "The Fear<->Euphoria gauge maps cross-asset sentiment onto 0-100. It's "
                   "now in the euphoria band — historically a caution zone where "
                   "positioning is one-sided. Describes crowding, doesn't forecast a top.",
        "what_zh": "恐惧↔欣喜指标把跨资产情绪映射到 0-100。现处于欣喜区 — 历史上的警惕地带，"
                   "持仓一边倒。描述拥挤，并不预测顶部。",
        "anchor": "fear-euphoria"},
    "fear_euphoria_capitulation": {
        "icon": "🥶", "plain_en": "Sentiment hit PANIC — contrarian zone",
        "plain_zh": "情绪触及「恐慌」— 逆向区",
        "what_en": "The Fear<->Euphoria gauge is now in the panic band — historically a "
                   "contrarian capitulation zone. Describes fear, doesn't forecast a bottom.",
        "what_zh": "恐惧↔欣喜指标现处于恐慌区 — 历史上的逆向投降地带。描述恐慌，并不预测底部。",
        "anchor": "fear-euphoria"},
    "ah_premium_wide": {
        "icon": "⚖️", "plain_en": "A/H premium widened — HK is the cheaper twin",
        "plain_zh": "AH 溢价走阔 — 港股是更便宜的同股",
        "what_en": "Many mainland firms list both an A-share (CNY) and an H-share (HK). A "
                   "wide A/H premium means the HK-listed H line is the cheaper way to own "
                   "the same company — a rotation context, not a timing signal.",
        "what_zh": "许多内地公司同时上市 A 股（人民币）与 H 股（香港）。AH 溢价走阔意味着"
                   "港股 H 是更便宜的同股敞口 — 轮动背景，而非择时信号。",
        "anchor": "ah-premium"},
    "ah_premium_narrow": {
        "icon": "⚖️", "plain_en": "A/H premium narrowed",
        "plain_zh": "AH 溢价收窄",
        "what_en": "The A/H premium compressed — the H/HK discount to the mainland A-share "
                   "has shrunk. A rotation context, not a timing signal.",
        "what_zh": "AH 溢价压缩 — 港股 H 相对 A 股的折让收窄。轮动背景，而非择时信号。",
        "anchor": "ah-premium"},
    "hk_drawdown_elevated": {
        "icon": "⚠️", "plain_en": "Drawdown-risk gauge rose into elevated",
        "plain_zh": "回撤风险指标升入偏高区",
        "what_en": "The drawdown-risk gauge stacks HK stress legs (slowdown, VHSI, peg "
                   "stress, HIBOR, breadth) into a 0-100 read. It crossed up into elevated. "
                   "IMPORTANT: UNCALIBRATED (HK history is short/global) — read as "
                   "attention, never a forecast.",
        "what_zh": "回撤风险指标把香港压力因子（放缓、VHSI、联汇压力、HIBOR、宽度）叠加为 "
                   "0-100 读数。它刚上穿进入偏高区。重要：未校准（香港历史短且全球化）— "
                   "作为关注信号，绝非预测。",
        "anchor": "hk-risk"},
    "market_driver_clear": {
        "icon": "🎯", "plain_en": "One macro driver is dominating the tape",
        "plain_zh": "单一宏观驱动主导盘面",
        "what_en": "The market-drivers leaf decomposes today's cross-asset move into "
                   "competing macro fingerprints. Today one driver clearly dominates (high "
                   "confidence). Deterministic attribution, never a scored signal.",
        "what_zh": "市场驱动叶子把今日的跨资产波动分解为相互竞争的宏观指纹。今日单一驱动"
                   "明显主导（高置信）。确定性归因，绝非评分信号。",
        "anchor": "market-drivers"},
    "hk_circuit_breaker": {
        "icon": "🔌", "plain_en": "An HK data source went dark",
        "plain_zh": "某香港数据源中断",
        "what_en": "An HK feed this dashboard relies on failed several runs in a row, so "
                   "it's paused until it recovers. Signals that depend on it lose "
                   "confidence. A plumbing notice, not a market signal.",
        "what_zh": "本仪表盘依赖的某个香港数据源连续多次失败，已暂停直至恢复。依赖它的信号"
                   "会降低置信度。系统管线提示，并非市场信号。",
        "anchor": ""},   # HK macro page has no data-health panel — render as plain text, no dead jump
}

_DEFAULT_CONVICTION = {"tier": "watch", "edge_en": "", "edge_zh": ""}

ALERT_CONVICTION: dict[str, dict] = {
    "hk_regime_transition": {"tier": "act",
        "edge_en": "High — a quad shift re-prices the sector tilt downstream.",
        "edge_zh": "高 — 象限转变会重新定价其下游的板块配置。"},
    "hk_risk_on": {"tier": "watch",
        "edge_en": "Medium — HK's headline driver; concurrent risk state, confirm with price.",
        "edge_zh": "中 — 香港头号驱动；同步风险状态，请与价格印证。"},
    "hk_risk_off": {"tier": "watch",
        "edge_en": "Medium — HK's headline driver turned defensive; concurrent, not a forecast.",
        "edge_zh": "中 — 香港头号驱动转向防御；同步而非预测。"},
    "hk_peg_weak_side": {"tier": "act",
        "edge_en": "High — weak-side defence drains liquidity; a real HK funding headwind.",
        "edge_zh": "高 — 弱方护盘抽走流动性；是真实的香港资金面逆风。"},
    "hk_peg_strong_side": {"tier": "context",
        "edge_en": "Context — strong-side inflow adds liquidity; a funding tailwind.",
        "edge_zh": "背景 — 强方流入增加流动性；资金面顺风。"},
    "hibor_spike": {"tier": "watch",
        "edge_en": "Medium — a funding squeeze pressures leveraged/rate-sensitive names.",
        "edge_zh": "中 — 资金挤压压制杠杆与利率敏感标的。"},
    "southbound_surge": {"tier": "context",
        "edge_en": "Context — a smart-money inflow read; confirm against price.",
        "edge_zh": "背景 — 聪明钱流入读数；请与价格印证。"},
    "southbound_exodus": {"tier": "watch",
        "edge_en": "Medium — a smart-money outflow; risk appetite fading.",
        "edge_zh": "中 — 聪明钱流出；风险偏好消退。"},
    "hk_roro_flip_on": {"tier": "context",
        "edge_en": "Context — a cross-asset regime read; the composite is never scored.",
        "edge_zh": "背景 — 跨资产区制解读；综合指标从不计入评分。"},
    "hk_roro_flip_off": {"tier": "watch",
        "edge_en": "Medium — cross-asset mood turned defensive; a regime read.",
        "edge_zh": "中 — 跨资产情绪转向防御；区制解读。"},
    "vhsi_spike": {"tier": "watch",
        "edge_en": "Medium — fear repricing; expect bigger swings, not a direction.",
        "edge_zh": "中 — 恐慌重新定价；预期波动加大，而非方向。"},
    "fear_euphoria_extreme": {"tier": "context",
        "edge_en": "Context — euphoria describes crowding, it does not time a top.",
        "edge_zh": "背景 — 欣喜描述拥挤，并不预测顶部。"},
    "fear_euphoria_capitulation": {"tier": "context",
        "edge_en": "Context — panic describes fear, it does not time a bottom.",
        "edge_zh": "背景 — 恐慌描述恐惧，并不预测底部。"},
    "ah_premium_wide": {"tier": "context",
        "edge_en": "Context — a valuation/rotation read; HK is the cheaper twin.",
        "edge_zh": "背景 — 估值／轮动读数；港股是更便宜的同股。"},
    "ah_premium_narrow": {"tier": "context",
        "edge_en": "Context — the H/HK discount compressed; rotation context.",
        "edge_zh": "背景 — H/港股折让压缩；轮动背景。"},
    "hk_drawdown_elevated": {"tier": "context",
        "edge_en": "Context — UNCALIBRATED stress gauge; attention, not a P(drawdown).",
        "edge_zh": "背景 — 未校准的压力指标；关注信号，而非回撤概率。"},
    "market_driver_clear": {"tier": "context",
        "edge_en": "Context — deterministic attribution of today's move; never scored.",
        "edge_zh": "背景 — 今日波动的确定性归因；从不评分。"},
    "hk_circuit_breaker": {"tier": "context",
        "edge_en": "Plumbing — data health, not a market signal.",
        "edge_zh": "管线 — 数据健康度，而非市场信号。"},
}


def alert_view(rule: str, severity: str, message: str, message_zh: str = "") -> dict:
    return {"rule": rule, "severity": severity, "message": message,
            "message_zh": message_zh,
            **ALERT_META.get(rule, _DEFAULT_META),
            **ALERT_CONVICTION.get(rule, _DEFAULT_CONVICTION)}


def alert_views(alerts) -> list[dict]:
    out = []
    for a in alerts:
        if isinstance(a, Alert):
            out.append(alert_view(a.rule, a.severity, a.message, a.message_zh))
        else:
            out.append(alert_view(a.get("rule", ""), a.get("severity", "info"),
                                  a.get("message", ""), a.get("message_zh", "")))
    from engine.alerts import collapse_breaker_views
    return collapse_breaker_views(
        out, rule="hk_circuit_breaker",
        plural_en="{n} HK data sources went dark", plural_zh="{n} 个香港数据源中断",
        what_en="Multiple HK feeds this dashboard relies on failed several runs in "
                "a row, so they're paused until they recover. Signals that depend "
                "on them lose confidence. A plumbing notice, not a market signal.",
        what_zh="本仪表盘依赖的多个香港数据源连续多次失败，已暂停直至恢复。依赖它们的"
                "信号会降低置信度。系统管线提示，并非市场信号。")
