"""China-native alert rules — a clone of engine/alerts.py adapted to A-share
change detectors, evaluated on the China engine's daily output.

Every rule compares TODAY against YESTERDAY (or a trailing window / the prior
run), so alerts fire on *changes* — a crossing, a sign flip, a state escalation,
a fresh policy event — never on a level being high (a level-only rule re-fires
every day; the dedup would mask that, but the rule itself should detect change).
Fired alerts are appended to data/china_alerts/alerts_log.parquet keyed by
(date, rule, message) — re-running the same day is idempotent and cannot
double-send.

Severity is informational only ("info" | "warn" | "high"): it orders the
messages, it does not gate anything.

DISPLAY-ONLY INVARIANT: nothing in this module feeds engine/china_axes.py,
engine/china_regime.py or engine/china_playbook.py. Alerts are surfaced
notifications, NEVER scored inputs. (Asserted by a grep test.)

Everything degrades gracefully: a missing input skips its rule cleanly, one
rule raising can never kill the rest, and every public function returns
plain-Python data ([] / None) and never raises into a caller. Bilingual: every
alert carries `message` (EN) AND `message_zh`.
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


# --- shared helpers (mirror engine/china_conditions + china_internals idioms) ---

def _latest_json() -> dict:
    """The China engine's persisted latest.json (regime + conditions + drivers).
    Returns {} if it has not been written yet."""
    import json
    p = config.data_dir() / "china_regime" / "latest.json"
    if not p.exists():
        return {}
    try:
        with open(p) as fh:
            return json.load(fh)
    except Exception as e:  # noqa: BLE001 — bad/partial file must not crash alerts
        log.warning("china_alerts: latest.json unreadable: %s", e)
        return {}


def _regime_history() -> pd.DataFrame | None:
    df = store.read("china_regime", "regime_history")
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
    """Trailing rolling-z of the latest point (causal). None on warm-up."""
    s = s.dropna()
    if len(s) < max(20, window // 4):
        return None
    m = float(s.tail(window).mean())
    sd = float(s.tail(window).std())
    if not sd or not np.isfinite(sd):
        return None
    return (float(s.iloc[-1]) - m) / sd


def _crossed_up(s: pd.Series, thr: float) -> bool:
    """True iff the series UPcrossed `thr` between its last two finite points."""
    s = s.dropna()
    return len(s) >= 2 and s.iloc[-2] < thr <= s.iloc[-1]


def _crossed_down(s: pd.Series, thr: float) -> bool:
    """True iff the series DOWNcrossed `thr` between its last two finite points."""
    s = s.dropna()
    return len(s) >= 2 and s.iloc[-2] >= thr > s.iloc[-1]


# --- individual rules ---------------------------------------------------------
# Each takes (f, regime, latest) and returns Alert | None or list[Alert].

def china_regime_transition(f, regime, latest) -> Alert | None:
    """Evidence building toward a quad flip. Reuses pending_quad/pending_days from
    the regime engine (no separate state machine). Fires once the pending run has
    held >= MIN_DAYS but BEFORE it flips the label (7 days)."""
    min_days = 3
    pq = latest.get("pending_quad")
    pd_days = latest.get("pending_days") or 0
    if pq not in ("Q1", "Q2", "Q3", "Q4") or int(pd_days) < min_days:
        return None
    names = {"Q1": ("Goldilocks", "理想增长"), "Q2": ("Reflation", "再通胀"),
             "Q3": ("Stagflation", "滞胀"), "Q4": ("Growth scare", "增长恐慌")}
    en, zh = names.get(pq, (pq, pq))
    return Alert("china_regime_transition", "warn",
                 f"Regime watch: evidence building toward {en} ({pq}) — "
                 f"{int(pd_days)} day(s) so far; the quad label flips after 7",
                 message_zh=f"周期预警：证据正在累积，指向 {zh}（{pq}）— "
                            f"已持续 {int(pd_days)} 天；标签将在第 7 天翻转")


def china_confidence_floor(f, regime, latest) -> list[Alert]:
    """Regime / axis confidence downcrossing 0.30 vs the PRIOR run (read off the
    recomputed regime_history, so it's a genuine change detector)."""
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
            out.append(Alert(f"china_{key}_confidence_floor", "warn",
                             f"{en} confidence dropped below {floor:.0%}: "
                             f"{prev:.0%} -> {cur:.0%} — trust the label less, size down",
                             message_zh=f"{zh}一致度跌破 {floor:.0%}："
                                        f"{prev:.0%} -> {cur:.0%} — 降低对标签的信任，缩小仓位"))
    return out


def pboc_rrr_event(f, regime, latest) -> Alert | None:
    """A fresh RRR change event in the last ~3 days. Cut = easing (liquidity
    tailwind, info); hike = tightening (warn). Causal: fires on the EVENT date,
    not on the standing level."""
    d = store.read("china_macro", "rrr")
    if d is None or d.empty or "rrr_change" not in d.columns:
        return None
    ev = d[d["rrr_change"].notna() & (d["rrr_change"] != 0)].sort_index()
    if ev.empty:
        return None
    last_idx = ev.index.max()
    age = (pd.Timestamp.today().normalize() - pd.Timestamp(last_idx).normalize()).days
    if age > 3:
        return None
    chg = float(ev.loc[last_idx, "rrr_change"])
    level = ev.loc[last_idx, "rrr_big"]
    lvl_s = f"{float(level):.2f}%" if pd.notna(level) else "n/a"
    if chg < 0:
        return Alert("pboc_rrr_cut", "info",
                     f"PBoC cut the reserve requirement ratio {chg:+.2f}pp to {lvl_s} "
                     f"({last_idx.date()}) — easing, frees bank liquidity (equity tailwind)",
                     message_zh=f"央行下调存款准备金率 {chg:+.2f}pp 至 {lvl_s}"
                                f"（{last_idx.date()}）— 宽松，释放银行流动性（股市顺风）")
    return Alert("pboc_rrr_hike", "warn",
                 f"PBoC raised the reserve requirement ratio {chg:+.2f}pp to {lvl_s} "
                 f"({last_idx.date()}) — tightening, drains bank liquidity",
                 message_zh=f"央行上调存款准备金率 {chg:+.2f}pp 至 {lvl_s}"
                            f"（{last_idx.date()}）— 收紧，回收银行流动性")


def m2_impulse_flip(f, regime, latest) -> Alert | None:
    """The 3-month change of M2 YoY flips sign vs the prior print — a turn in the
    broad-money growth impulse."""
    s = _store_series("china_macro", "money_supply", "m2_yoy")
    if s is None or len(s) < 5:
        return None
    impulse = s.diff(3).dropna()      # 3-month change of M2 YoY
    if len(impulse) < 2:
        return None
    prev, cur = float(impulse.iloc[-2]), float(impulse.iloc[-1])
    if prev == 0 or cur == 0 or np.sign(prev) == np.sign(cur):
        return None
    direction, dir_zh = (("accelerating", "回升") if cur > 0 else ("decelerating", "回落"))
    return Alert("m2_impulse_flip", "info",
                 f"M2 growth impulse flipped {direction}: 3-month change of M2 YoY "
                 f"{prev:+.1f}pp -> {cur:+.1f}pp (now {float(s.iloc[-1]):.1f}% YoY)",
                 message_zh=f"M2 增长脉冲转为{dir_zh}：M2 同比 3 个月变化 "
                            f"{prev:+.1f}pp -> {cur:+.1f}pp（现 {float(s.iloc[-1]):.1f}% 同比）")


def margin_froth(f, regime, latest) -> Alert | None:
    """Margin financing as a % of float crossing its 4y percentile bands. High
    upcross (>=80) = crowded/fragile (high); low downcross (<=20) = washed out
    (info). Percentile crossing, not a standing level."""
    fin = _store_series("china_margin", "balance", "fin_pct_float")
    if fin is None or len(fin) < 252:
        return None
    pct = (pct_rank_window(fin, 252 * 4) * 100).dropna()
    if len(pct) < 2:
        return None
    if _crossed_up(pct, 80.0):
        return Alert("margin_froth_high", "high",
                     f"Margin financing crowding crossed above the 80th percentile "
                     f"(now {pct.iloc[-1]:.0f}th, {fin.iloc[-1]:.2f}% of float) — "
                     f"leverage is stretched, the tape is fragile",
                     message_zh=f"融资拥挤度上穿第 80 百分位"
                                f"（现第 {pct.iloc[-1]:.0f}，占流通市值 {fin.iloc[-1]:.2f}%）— "
                                f"杠杆偏高，盘面脆弱")
    if _crossed_down(pct, 20.0):
        return Alert("margin_capitulation", "info",
                     f"Margin financing crowding crossed below the 20th percentile "
                     f"(now {pct.iloc[-1]:.0f}th, {fin.iloc[-1]:.2f}% of float) — "
                     f"leverage washed out; a contrarian de-fragiling, not a buy",
                     message_zh=f"融资拥挤度下穿第 20 百分位"
                                f"（现第 {pct.iloc[-1]:.0f}，占流通市值 {fin.iloc[-1]:.2f}%）— "
                                f"杠杆出清；逆向的去脆弱，而非买入信号")
    return None


def southbound_extreme(f, regime, latest) -> Alert | None:
    """Southbound (mainland-into-HK smart money) daily net 1y-z reaching +/-2 —
    a surge of conviction buying (info) or an exodus (warn)."""
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
                     f"(net {last:+,.0f}, 1y window) — conviction inflow",
                     message_zh=f"南向资金净买入激增至 {z:+.1f}σ"
                                f"（净额 {last:+,.0f}，1 年窗口）— 信念流入")
    if z <= -2.0:
        return Alert("southbound_exodus", "warn",
                     f"Southbound smart-money net selling spiked to {z:+.1f}σ "
                     f"(net {last:+,.0f}, 1y window) — conviction outflow",
                     message_zh=f"南向资金净卖出骤增至 {z:+.1f}σ"
                                f"（净额 {last:+,.0f}，1 年窗口）— 信念流出")
    return None


def china_roro_flip(f, regime, latest) -> Alert | None:
    """The display-only RORO composite crossing the +/-0.35 risk-on / risk-off
    bands vs prior. Reads the conditions snapshot already on `latest` (rebuilds it
    from f if absent). Causal: a band CROSS, not a standing state."""
    cur = None
    cond = (latest or {}).get("conditions") or {}
    roro = cond.get("roro") or {}
    cur = roro.get("roro")
    # rebuild a tiny 2-point history off f to detect the cross (the snapshot only
    # carries the latest value). china_conditions is display-only -> safe to read.
    try:
        from engine import china_conditions
        rf = china_conditions.roro_frame(f) if f is not None else None
        if rf is not None and "roro" in rf.columns:
            s = rf["roro"].dropna()
            if len(s) >= 2:
                if _crossed_up(s, 0.35):
                    return Alert("china_roro_flip_on", "info",
                                 f"Cross-asset RORO crossed into RISK-ON "
                                 f"(now {s.iloc[-1]:+.2f}, was {s.iloc[-2]:+.2f}) — "
                                 f"A-share risk appetite turned up",
                                 message_zh=f"跨资产 RORO 上穿进入「偏好风险」"
                                            f"（现 {s.iloc[-1]:+.2f}，前 {s.iloc[-2]:+.2f}）— "
                                            f"A 股风险偏好转暖")
                if _crossed_down(s, -0.35):
                    return Alert("china_roro_flip_off", "warn",
                                 f"Cross-asset RORO crossed into RISK-OFF "
                                 f"(now {s.iloc[-1]:+.2f}, was {s.iloc[-2]:+.2f}) — "
                                 f"A-share risk appetite turned down",
                                 message_zh=f"跨资产 RORO 下穿进入「避险」"
                                            f"（现 {s.iloc[-1]:+.2f}，前 {s.iloc[-2]:+.2f}）— "
                                            f"A 股风险偏好转弱")
    except Exception as e:  # noqa: BLE001 — additive, never fatal
        log.warning("china_roro_flip rebuild failed: %s", e)
    return None


def qvix_spike(f, regime, latest) -> Alert | None:
    """A-share implied vol (QVIX 300) jumping >= 15% day-over-day OR upcrossing its
    90th percentile — a fear spike."""
    s = _store_series("china_qvix", "qvix300", "close")
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
    return Alert("qvix_spike", "warn",
                 f"A-share implied vol (QVIX 300) {what} to {float(s.iloc[-1]):.1f} — "
                 f"fear is repricing",
                 message_zh=f"A 股隐含波动率（QVIX 300）{what_zh}至 {float(s.iloc[-1]):.1f} — "
                            f"恐慌正在重新定价")


def fear_euphoria_extreme(f, regime, latest) -> Alert | None:
    """Fear<->Euphoria 0-100 reaching euphoria (>=88, caution) or panic (<=12,
    capitulation). Reads the synthesis already on `latest`."""
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


def ppi_deflation_deepen(f, regime, latest) -> Alert | None:
    """PPI YoY downcrossing -2.0% — deepening industrial deflation, the
    China-specific recession tell (factory-gate prices falling fast)."""
    s = _col(f, "ppi_yoy")
    if s is None or len(s) < 2:
        return None
    if _crossed_down(s, -2.0):
        return Alert("ppi_deflation_deepen", "warn",
                     f"Producer-price deflation deepened: PPI YoY crossed below -2.0% "
                     f"(now {float(s.iloc[-1]):+.1f}%) — factory-gate prices falling, "
                     f"a China-specific recession tell",
                     message_zh=f"工业通缩加深：PPI 同比下穿 -2.0%"
                                f"（现 {float(s.iloc[-1]):+.1f}%）— 工业品出厂价下跌，"
                                f"中国特有的衰退信号")
    return None


def china_drawdown_elevated(f, regime, latest) -> Alert | None:
    """The display-only drawdown-risk gauge crossing UP into elevated/high (score
    upcrossing ~60). Rebuilds the 0..100 series off f to detect the cross. The
    gauge is UNCALIBRATED — surface it as attention, not a forecast."""
    thr = 60.0
    try:
        from engine import china_conditions
        rec_series, _ = china_conditions._recession_score_series(f)
        dd = china_conditions._drawdown_score_series(f, rec_series).dropna()
        if len(dd) < 2 or not _crossed_up(dd, thr):
            return None
        band = ((latest or {}).get("conditions") or {}).get("drawdown_risk", {}).get("band")
        band_s = f", band {band}" if band else ""
        return Alert("china_drawdown_elevated", "warn",
                     f"A-share drawdown-risk gauge crossed up through {thr:.0f}/100 "
                     f"(now {dd.iloc[-1]:.0f}{band_s}) — stress legs stacking; "
                     f"UNCALIBRATED, read as attention not a P(drawdown) forecast",
                     message_zh=f"A 股回撤风险指标上穿 {thr:.0f}/100"
                                f"（现 {dd.iloc[-1]:.0f}{band_s}）— 压力因子累积；"
                                f"未校准，作为关注信号而非回撤概率预测")
    except Exception as e:  # noqa: BLE001 — additive, never fatal
        log.warning("china_drawdown_elevated rebuild failed: %s", e)
    return None


def market_driver_clear(f, regime, latest) -> Alert | None:
    """A single macro driver dominating the tape today — market_drivers verdict
    'clear' with 'high' confidence. Reads the snapshot already on `latest`."""
    md = (latest or {}).get("market_drivers") or {}
    if md.get("verdict") != "clear" or md.get("confidence") != "high":
        return None
    pl = md.get("primary_label") or md.get("primary") or "a single driver"
    pl_zh = md.get("primary_label_zh") or pl
    return Alert("market_driver_clear", "info",
                 f"One macro driver is clearly dominating the tape today: {pl} "
                 f"(high confidence) — moves are being driven by this, not breadth",
                 message_zh=f"今日单一宏观驱动明显主导盘面：{pl_zh}"
                            f"（高置信）— 行情由此驱动，而非全面宽度")


def china_circuit_breaker(f, regime, latest) -> list[Alert]:
    """Fires the day a china_* data source's breaker opens (count == threshold);
    mirrors the US circuit_breaker_open rule. Plumbing, not a market signal."""
    from collectors.base import CIRCUIT_BREAKER_FAILS
    breaker = store.read_status().get("circuit_breaker", {})
    out = []
    for src, n in breaker.items():
        if not str(src).startswith("china"):
            continue
        if n == CIRCUIT_BREAKER_FAILS:
            out.append(Alert("china_circuit_breaker", "high",
                             f"China source '{src}' marked dead after {n} consecutive "
                             f"failures — collector skipped until it recovers; affected "
                             f"signals degrade",
                             message_zh=f"中国数据源 '{src}' 连续 {n} 次失败后被标记为中断 — "
                                        f"采集器暂停直至恢复；相关信号置信度下降"))
    return out


# --- runner -------------------------------------------------------------------

_SINGLE_RULES = [
    china_regime_transition, pboc_rrr_event, m2_impulse_flip, margin_froth,
    southbound_extreme, china_roro_flip, qvix_spike, fear_euphoria_extreme,
    ppi_deflation_deepen, china_drawdown_elevated, market_driver_clear,
]
_MULTI_RULES = [china_confidence_floor, china_circuit_breaker]

_SEV_ORDER = {"high": 0, "warn": 1, "info": 2}


def evaluate(f: pd.DataFrame | None = None, regime: pd.DataFrame | None = None,
             latest: dict | None = None) -> list[Alert]:
    """Run every China alert rule against today's engine output and return the
    fired Alert objects, severity-sorted (high -> warn -> info). Builds f /
    regime / latest internally if not supplied, so it's testable standalone.
    One rule raising can never kill the rest."""
    if latest is None:
        latest = _latest_json()
    if f is None:
        try:
            from engine.china_inputs import build_features
            f = build_features()
        except Exception as e:  # noqa: BLE001 — degrade, never raise into a caller
            log.warning("china_alerts: build_features failed: %s", e)
            f = None
    if regime is None:
        regime = _regime_history()

    alerts: list[Alert] = []
    for rule in _SINGLE_RULES:
        try:
            a = rule(f, regime, latest)
            if a:
                alerts.append(a)
        except Exception as e:  # noqa: BLE001 — isolate each rule
            log.error("china alert rule %s failed: %s", rule.__name__, e)
    for rule in _MULTI_RULES:
        try:
            alerts.extend(rule(f, regime, latest) or [])
        except Exception as e:  # noqa: BLE001
            log.error("china alert rule %s failed: %s", rule.__name__, e)
    return sorted(alerts, key=lambda a: _SEV_ORDER.get(a.severity, 9))


def _log_path():
    return config.data_dir() / "china_alerts" / "alerts_log.parquet"


def log_and_dedup(alerts: list[Alert], asof) -> list[dict]:
    """Append fired alerts to data/china_alerts/alerts_log.parquet, dropping any
    already logged for `asof` (keyed by (date, rule, message)). Returns TODAY's
    fired alerts as enriched view dicts (alert_views shape) — ready for the
    template. Idempotent: running twice the same day adds nothing and returns the
    same views."""
    asof = pd.Timestamp(asof)
    p = _log_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    cols = ["date", "rule", "severity", "message", "message_zh"]
    old = pd.read_parquet(p) if p.exists() else pd.DataFrame(columns=cols)
    for c in cols:                                  # tolerate an older/narrower schema
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
    # return ALL of today's fired alerts (incl. ones logged on an earlier run
    # today), so the page is stable across same-day rebuilds.
    return today_views(asof)


def today_views(asof=None) -> list[dict]:
    """Enriched view dicts for every alert logged for `asof` (default: today),
    severity-sorted. Reads the append-only log so the page is identical no matter
    which same-day run rendered it."""
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
    # one alert per rule per day — collapse same-day re-runs whose message wording
    # drifted (the (date, rule, message) log key would otherwise double-show a rule;
    # keep the most-recently-logged wording). EXCEPT the circuit-breaker rule: there
    # each same-rule row is a DIFFERENT dark source, not wording drift — those keep
    # one row per message and alert_views collapses them into one count-aware view
    # ("N China data sources went dark").
    is_breaker = rows["rule"] == "china_circuit_breaker"
    rows = pd.concat([
        rows[~is_breaker].drop_duplicates(subset=["rule"], keep="last"),
        rows[is_breaker].drop_duplicates(subset=["rule", "message"], keep="last"),
    ]).sort_index()
    rows = rows.sort_values("severity", key=lambda s: s.map(lambda x: _SEV_ORDER.get(x, 9)))
    return alert_views(rows.to_dict(orient="records"))


def fired_today(latest: dict | None = None) -> list[dict]:
    """Convenience: evaluate + log + return today's fired alert views in one call.
    `asof` is taken from latest['date'] when available, else today."""
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
# Rule messages are precise but jargon-heavy. ALERT_META adds a plain-English
# headline, an icon, a "what it means / how to use it" explainer, and the China
# macro-dashboard panel ("scorecard") each alert deep-links to. `anchor` matches
# an id="" on a panel in templates/china.html.j2.

_DEFAULT_META = {
    "icon": "🔔",
    "plain_en": "A China macro signal changed — check the dashboard read",
    "plain_zh": "一个中国宏观信号变化 — 查看仪表盘解读",
    "what_en": "An automated A-share macro signal changed state. Open the China "
               "dashboard for the full read.",
    "what_zh": "一个自动 A 股宏观信号发生了状态变化。打开中国仪表盘查看完整解读。",
    "anchor": "",
}

ALERT_META: dict[str, dict] = {
    "china_regime_transition": {
        "icon": "🧭",
        "plain_en": "Regime radar moved — the A-share quad may be flipping",
        "plain_zh": "周期雷达变动 — A 股象限可能正在翻转",
        "what_en": "The growth/inflation quad is built from a stable label plus a "
                   "\"pending\" reading that has to hold a week before the label flips. "
                   "Evidence is now stacking toward a new quad. A cue to re-check your "
                   "tilt before it confirms — not a trade on its own.",
        "what_zh": "增长／通胀象限由稳定标签加上一个需持续一周才翻转的「待定」读数构成。"
                   "证据正在累积指向新的象限。这是在确认前重新检视配置的提示 — 本身并非交易信号。",
        "anchor": "regime-radar",
    },
    "china_regime_confidence_floor": {
        "icon": "🎚️",
        "plain_en": "Regime read got muddy — trust the quad label less",
        "plain_zh": "周期信号变浑浊 — 降低对象限标签的信任",
        "what_en": "Confidence is how strongly the underlying indicators agree on the "
                   "quad. It just fell below a usable threshold, so the label is now "
                   "mixed. Lower confidence = size positions down and lean on the "
                   "conditions lens more than the label.",
        "what_zh": "置信度反映底层指标对象限的认同程度。它刚跌破可用阈值，目前标签混杂。"
                   "置信度低 = 缩小仓位，更依赖条件透镜而非标签。",
        "anchor": "regime-radar",
    },
    "china_growth_confidence_floor": {
        "icon": "🎚️",
        "plain_en": "Growth read got muddy — trust the quad label less",
        "plain_zh": "增长信号变浑浊 — 降低对象限标签的信任",
        "what_en": "The growth dial's indicators just stopped agreeing (confidence fell "
                   "below a usable threshold). The growth half of the quad is now mixed — "
                   "size down and trust the conditions lens more than the label.",
        "what_zh": "增长刻度盘的指标刚停止一致（置信度跌破可用阈值）。象限的增长一侧现已混杂 —"
                   "缩小仓位，相信条件透镜多于标签。",
        "anchor": "regime-radar",
    },
    "china_inflation_confidence_floor": {
        "icon": "🎚️",
        "plain_en": "Inflation read got muddy — trust the quad label less",
        "plain_zh": "通胀信号变浑浊 — 降低对象限标签的信任",
        "what_en": "The inflation dial's indicators just stopped agreeing (confidence "
                   "fell below a usable threshold). The inflation half of the quad is now "
                   "mixed — size down and trust the conditions lens more than the label.",
        "what_zh": "通胀刻度盘的指标刚停止一致（置信度跌破可用阈值）。象限的通胀一侧现已混杂 —"
                   "缩小仓位，相信条件透镜多于标签。",
        "anchor": "regime-radar",
    },
    "pboc_rrr_cut": {
        "icon": "💧",
        "plain_en": "PBoC cut reserve requirements — easing",
        "plain_zh": "央行降准 — 宽松",
        "what_en": "The reserve requirement ratio (RRR) is how much banks must park at "
                   "the PBoC. A cut releases bank liquidity into the economy — China's "
                   "most-watched easing lever and historically an equity tailwind. Lean "
                   "more constructive; it's not a buy button.",
        "what_zh": "存款准备金率（RRR）是银行必须存放在央行的比例。降准把银行流动性释放入"
                   "经济 — 中国最受关注的宽松工具，历史上对股市是顺风。可偏积极；这不是买入按钮。",
        "anchor": "internals",
    },
    "pboc_rrr_hike": {
        "icon": "🧊",
        "plain_en": "PBoC raised reserve requirements — tightening",
        "plain_zh": "央行升准 — 收紧",
        "what_en": "A hike to the reserve requirement ratio drains bank liquidity — the "
                   "opposite of easing, and historically an equity headwind. Lean more "
                   "cautious until the policy stance turns.",
        "what_zh": "上调存款准备金率会回收银行流动性 — 与宽松相反，历史上对股市是逆风。"
                   "在政策立场转向前可偏谨慎。",
        "anchor": "internals",
    },
    "m2_impulse_flip": {
        "icon": "🌀",
        "plain_en": "Broad-money growth impulse turned",
        "plain_zh": "广义货币增长脉冲转向",
        "what_en": "M2 is the broad money supply. Its 3-month growth impulse just flipped "
                   "direction — the rate at which liquidity is building or fading changed "
                   "sign. A slow-moving liquidity backdrop cue, not a timing signal.",
        "what_zh": "M2 是广义货币供应。其 3 个月增长脉冲刚刚反向 — 流动性积累或消退的速度"
                   "改变了符号。这是缓慢变化的流动性背景提示，并非择时信号。",
        "anchor": "internals",
    },
    "margin_froth_high": {
        "icon": "🎈",
        "plain_en": "Margin leverage is crowded — the tape is fragile",
        "plain_zh": "融资杠杆拥挤 — 盘面脆弱",
        "what_en": "Margin financing as a share of free float is the A-share crowding "
                   "gauge (the retail-leverage analog of COT). It just pushed into the "
                   "top of its multi-year range — crowded books unwind violently. A "
                   "fragility flag, not a short signal.",
        "what_zh": "融资余额占流通市值的比例是 A 股拥挤度计（散户杠杆版的 COT）。它刚冲入"
                   "多年区间的顶部 — 拥挤的头寸会剧烈平仓。这是脆弱性提示，并非做空信号。",
        "anchor": "internals",
    },
    "margin_capitulation": {
        "icon": "🧹",
        "plain_en": "Margin leverage washed out",
        "plain_zh": "融资杠杆出清",
        "what_en": "Margin financing as a share of free float just fell to the bottom of "
                   "its multi-year range — leverage has been flushed out, which lowers "
                   "downside fragility. A contrarian de-risking of the tape, not an "
                   "instant buy.",
        "what_zh": "融资余额占流通市值的比例刚跌至多年区间的底部 — 杠杆已被冲洗，下行脆弱性"
                   "下降。这是盘面的逆向去风险，而非立即买入。",
        "anchor": "internals",
    },
    "southbound_surge": {
        "icon": "🐉",
        "plain_en": "Southbound smart money surged in",
        "plain_zh": "南向资金大举流入",
        "what_en": "Southbound flow is mainland money buying Hong Kong via Stock Connect "
                   "— a closely-watched \"smart money\" gauge. Net buying just spiked to "
                   "an extreme. Conviction inflow worth noting; confirm against price.",
        "what_zh": "南向资金是内地资金通过港股通买入香港 — 受关注的「聪明钱」指标。净买入刚"
                   "飙升至极值。值得留意的信念流入；请与价格相互印证。",
        "anchor": "internals",
    },
    "southbound_exodus": {
        "icon": "🐉",
        "plain_en": "Southbound smart money rushed out",
        "plain_zh": "南向资金大举流出",
        "what_en": "Mainland \"smart money\" buying of Hong Kong via Stock Connect just "
                   "swung to an extreme net OUTFLOW. A conviction-selling cue — risk "
                   "appetite is fading; confirm against price.",
        "what_zh": "内地通过港股通买入香港的「聪明钱」刚摆向极端净流出。这是信念卖出提示 —"
                   "风险偏好正在消退；请与价格相互印证。",
        "anchor": "internals",
    },
    "china_roro_flip_on": {
        "icon": "🟢",
        "plain_en": "Cross-asset risk appetite turned ON",
        "plain_zh": "跨资产风险偏好转「开」",
        "what_en": "The RORO composite blends copper/gold, breadth, southbound flow, the "
                   "M1-M2 scissors, turnover, QVIX, the yuan and margin froth into one "
                   "risk-on/off read. It just crossed into risk-ON. A regime read of the "
                   "tape's mood, not a scored signal.",
        "what_zh": "RORO 综合指标把铜／金、宽度、南向资金、M1−M2 剪刀差、成交、QVIX、人民币"
                   "和融资拥挤度融合为一个风险开关读数。它刚上穿进入「偏好风险」。这是盘面情绪"
                   "的区制解读，并非评分信号。",
        "anchor": "fear-euphoria",
    },
    "china_roro_flip_off": {
        "icon": "🔴",
        "plain_en": "Cross-asset risk appetite turned OFF",
        "plain_zh": "跨资产风险偏好转「关」",
        "what_en": "The RORO composite (copper/gold, breadth, southbound, M1-M2, "
                   "turnover, QVIX, yuan, margin froth) just crossed into risk-OFF — the "
                   "tape's cross-asset mood turned defensive. A regime read, not a scored "
                   "signal.",
        "what_zh": "RORO 综合指标（铜／金、宽度、南向、M1−M2、成交、QVIX、人民币、融资拥挤度）"
                   "刚下穿进入「避险」— 盘面的跨资产情绪转向防御。这是区制解读，并非评分信号。",
        "anchor": "fear-euphoria",
    },
    "qvix_spike": {
        "icon": "⚡",
        "plain_en": "A-share fear gauge spiked",
        "plain_zh": "A 股恐慌指标骤升",
        "what_en": "QVIX(300) is the A-share implied-volatility / fear gauge (the local "
                   "VIX analog). A sharp jump or a push into its top decile means traders "
                   "are paying up for protection — expect bigger swings.",
        "what_zh": "QVIX(300) 是 A 股隐含波动率／恐慌指标（本地版 VIX）。急升或冲入前十分位"
                   "意味着交易者在为保护付高价 — 预期波动加大。",
        "anchor": "fear-euphoria",
    },
    "fear_euphoria_extreme": {
        "icon": "🥵",
        "plain_en": "Sentiment hit EUPHORIA — caution",
        "plain_zh": "情绪触及「欣喜」— 警惕",
        "what_en": "The Fear<->Euphoria gauge maps cross-asset sentiment onto a 0-100 "
                   "scale. It's now in the euphoria band — historically a caution zone "
                   "where positioning is one-sided. It describes crowding, it does not "
                   "forecast a top.",
        "what_zh": "恐惧↔欣喜指标把跨资产情绪映射到 0-100 区间。现处于欣喜区 — 历史上的"
                   "警惕地带，持仓一边倒。它描述拥挤，并不预测顶部。",
        "anchor": "fear-euphoria",
    },
    "fear_euphoria_capitulation": {
        "icon": "🥶",
        "plain_en": "Sentiment hit PANIC — contrarian zone",
        "plain_zh": "情绪触及「恐慌」— 逆向区",
        "what_en": "The Fear<->Euphoria gauge is now in the panic band — historically a "
                   "contrarian capitulation zone. It describes fear, it does not forecast "
                   "a bottom; size into weakness carefully if at all.",
        "what_zh": "恐惧↔欣喜指标现处于恐慌区 — 历史上的逆向投降地带。它描述恐慌，并不预测"
                   "底部；若要逢弱布局也需谨慎。",
        "anchor": "fear-euphoria",
    },
    "ppi_deflation_deepen": {
        "icon": "📉",
        "plain_en": "Industrial deflation deepened",
        "plain_zh": "工业通缩加深",
        "what_en": "PPI is factory-gate (producer) price inflation. It just fell deeper "
                   "into deflation — falling industrial prices squeeze corporate margins "
                   "and signal weak demand, a China-specific recession tell. A macro "
                   "context cue, not a trade.",
        "what_zh": "PPI 是工业品出厂（生产者）价格通胀。它刚跌入更深的通缩 — 工业品价格下跌"
                   "挤压企业利润、显示需求疲弱，是中国特有的衰退信号。这是宏观背景提示，并非交易。",
        "anchor": "china-risk",
    },
    "china_drawdown_elevated": {
        "icon": "⚠️",
        "plain_en": "Drawdown-risk gauge rose into elevated",
        "plain_zh": "回撤风险指标升入偏高区",
        "what_en": "The drawdown-risk gauge stacks A-share stress legs (slowdown, margin "
                   "froth, flat CGB curve, QVIX, turnover mania) into a 0-100 read. It "
                   "just crossed up into the elevated zone. IMPORTANT: it is UNCALIBRATED "
                   "(China history is too short for a measured P(drawdown)) — read it as "
                   "attention, never a forecast.",
        "what_zh": "回撤风险指标把 A 股压力因子（放缓、融资拥挤、国债曲线走平、QVIX、成交"
                   "狂热）叠加为 0-100 读数。它刚上穿进入偏高区。重要：它未校准（中国历史"
                   "过短，无法给出可测的回撤概率）— 作为关注信号，绝非预测。",
        "anchor": "china-risk",
    },
    "market_driver_clear": {
        "icon": "🎯",
        "plain_en": "One macro driver is dominating the tape",
        "plain_zh": "单一宏观驱动主导盘面",
        "what_en": "The market-drivers leaf decomposes today's cross-asset move into "
                   "competing macro fingerprints. Today one driver clearly dominates "
                   "(high confidence) — moves are being driven by this one factor, not "
                   "broad breadth. Deterministic attribution, never a scored signal.",
        "what_zh": "市场驱动叶子把今日的跨资产波动分解为相互竞争的宏观指纹。今日单一驱动"
                   "明显主导（高置信）— 行情由这一个因素驱动，而非全面宽度。确定性归因，"
                   "绝非评分信号。",
        "anchor": "market-drivers",
    },
    "china_circuit_breaker": {
        "icon": "🔌",
        "plain_en": "A China data source went dark",
        "plain_zh": "某中国数据源中断",
        "what_en": "A China feed this dashboard relies on failed several runs in a row, "
                   "so it's paused until it recovers. Any signals that depend on it lose "
                   "confidence until it's back. This is a plumbing notice, not a market "
                   "signal.",
        "what_zh": "本仪表盘依赖的某个中国数据源连续多次失败，已暂停直至恢复。依赖它的信号"
                   "会自动降低置信度，直到其恢复。这是系统管线提示，并非市场信号。",
        "anchor": "data-health",
    },
}


# Conviction layer — how much WEIGHT each alert deserves, kept separate from the
# copy blocks above. `tier` drives prioritisation (act > watch > context). The
# China conditions / regime lenses are explicitly UNCALIBRATED (short, regime-
# unstable history), so every edge note is a documented-reasoning call, NOT a
# measured forward-return claim — and several leaves are flagged context-only.
_DEFAULT_CONVICTION = {"tier": "watch", "edge_en": "", "edge_zh": ""}

ALERT_CONVICTION: dict[str, dict] = {
    "china_regime_transition": {"tier": "act",
        "edge_en": "High — a quad shift re-prices the sector tilt downstream.",
        "edge_zh": "高 — 象限转变会重新定价其下游的板块配置。"},
    "pboc_rrr_cut": {"tier": "watch",
        "edge_en": "Medium — China's headline easing lever; a documented equity "
                   "tailwind, but the transmission lag is long. Lean on it, don't trade it.",
        "edge_zh": "中 — 中国旗舰宽松工具；有据可查的股市顺风，但传导滞后较长。据此微调，"
                   "而非直接交易。"},
    "pboc_rrr_hike": {"tier": "watch",
        "edge_en": "Medium — a tightening headwind; rare, so worth noting.",
        "edge_zh": "中 — 收紧逆风；少见，值得留意。"},
    "m2_impulse_flip": {"tier": "context",
        "edge_en": "Context — a slow liquidity-backdrop turn, not a timing signal.",
        "edge_zh": "背景 — 缓慢的流动性背景转向，而非择时信号。"},
    "margin_froth_high": {"tier": "watch",
        "edge_en": "Medium — crowding precedes fragility; a risk flag, not a short.",
        "edge_zh": "中 — 拥挤先于脆弱；风险提示，而非做空。"},
    "margin_capitulation": {"tier": "context",
        "edge_en": "Context — leverage washout lowers fragility; not a buy.",
        "edge_zh": "背景 — 杠杆出清降低脆弱性；并非买入。"},
    "southbound_surge": {"tier": "context",
        "edge_en": "Context — a smart-money inflow read; confirm against price.",
        "edge_zh": "背景 — 聪明钱流入读数；请与价格印证。"},
    "southbound_exodus": {"tier": "watch",
        "edge_en": "Medium — a smart-money outflow; risk appetite fading.",
        "edge_zh": "中 — 聪明钱流出；风险偏好消退。"},
    "china_roro_flip_on": {"tier": "context",
        "edge_en": "Context — a cross-asset regime read; the composite is never scored.",
        "edge_zh": "背景 — 跨资产区制解读；综合指标从不计入评分。"},
    "china_roro_flip_off": {"tier": "watch",
        "edge_en": "Medium — cross-asset mood turned defensive; a regime read.",
        "edge_zh": "中 — 跨资产情绪转向防御；区制解读。"},
    "qvix_spike": {"tier": "watch",
        "edge_en": "Medium — fear repricing; expect bigger swings, not a direction.",
        "edge_zh": "中 — 恐慌重新定价；预期波动加大，而非方向。"},
    "fear_euphoria_extreme": {"tier": "context",
        "edge_en": "Context — euphoria describes crowding, it does not time a top.",
        "edge_zh": "背景 — 欣喜描述拥挤，并不预测顶部。"},
    "fear_euphoria_capitulation": {"tier": "context",
        "edge_en": "Context — panic describes fear, it does not time a bottom.",
        "edge_zh": "背景 — 恐慌描述恐惧，并不预测底部。"},
    "ppi_deflation_deepen": {"tier": "watch",
        "edge_en": "Medium — deepening industrial deflation is a real China growth tell.",
        "edge_zh": "中 — 加深的工业通缩是真实的中国增长信号。"},
    "china_drawdown_elevated": {"tier": "context",
        "edge_en": "Context — UNCALIBRATED stress gauge; attention, not a P(drawdown).",
        "edge_zh": "背景 — 未校准的压力指标；关注信号，而非回撤概率。"},
    "market_driver_clear": {"tier": "context",
        "edge_en": "Context — deterministic attribution of today's move; never scored.",
        "edge_zh": "背景 — 今日波动的确定性归因；从不评分。"},
    "china_circuit_breaker": {"tier": "context",
        "edge_en": "Plumbing — data health, not a market signal.",
        "edge_zh": "管线 — 数据健康度，而非市场信号。"},
}


def alert_view(rule: str, severity: str, message: str, message_zh: str = "") -> dict:
    """Enrich a stored alert (rule/severity/message) with plain-English copy, an
    icon, the China dashboard panel anchor it deep-links to, and a conviction tier
    + grounded edge note. Unknown rules fall back to generic defaults so a new
    rule still renders sensibly. SAME output shape as engine/alerts.alert_view."""
    return {"rule": rule, "severity": severity, "message": message,
            "message_zh": message_zh,
            **ALERT_META.get(rule, _DEFAULT_META),
            **ALERT_CONVICTION.get(rule, _DEFAULT_CONVICTION)}


def alert_views(alerts) -> list[dict]:
    """Map a list of Alert objects or {rule,severity,message[,message_zh]} dicts to
    enriched view dicts, preserving order (callers pass them already severity-
    sorted). SAME output shape as engine/alerts.alert_views."""
    out = []
    for a in alerts:
        if isinstance(a, Alert):
            out.append(alert_view(a.rule, a.severity, a.message, a.message_zh))
        else:
            out.append(alert_view(a.get("rule", ""), a.get("severity", "info"),
                                  a.get("message", ""), a.get("message_zh", "")))
    from engine.alerts import collapse_breaker_views
    return collapse_breaker_views(
        out, rule="china_circuit_breaker",
        plural_en="{n} China data sources went dark", plural_zh="{n} 个中国数据源中断",
        what_en="Multiple China feeds this dashboard relies on failed several runs "
                "in a row, so they're paused until they recover. Any signals that "
                "depend on them lose confidence until they're back. This is a "
                "plumbing notice, not a market signal.",
        what_zh="本仪表盘依赖的多个中国数据源连续多次失败，已暂停直至恢复。依赖它们的"
                "信号会自动降低置信度，直到其恢复。这是系统管线提示，并非市场信号。")
