"""HK Command Panel — synthesis organ (display-tier).

Fuses the seven HK Neural Web organs into one "is this HK tape becoming
combustible?" view. The **combustibility verdict** is a DETERMINISTIC
DESCRIPTIVE SUMMARY of how many forces confirm — it is NOT an LLM/originated
score or a buy/sell signal.

DOCTRINE
--------
- DISPLAY-ONLY. Context, not a signal / 参考，非买卖信号.
- FAIL-OPEN: a missing organ → that force = neutral/absent. Never raises.
- Accrues nothing new (reads existing organ outputs only).
- Verdict counts are DETERMINISTIC TALLIES — no model, no score origination.
- "No HK selection alpha" verdict stands. This panel is CONTEXT.

FORCE STACK (8 forces, all always shown)
-----------------------------------------
1. ADR offshore bridge      — adr_bridge composite implied gap
2. Tech bellwether impulse  — hk_market_drivers tech_internet_leadership
3. Narrative attention      — hk_narrative attention_shock / tone
4. Southbound flow          — internals.southbound accel / appetite
5. Breadth thrust           — breadth (hk_conditions / scoreboard breadth)
6. CBBC leverage            — hk_cbbc bull/bear skew
7. Funding / peg            — hk_liquidity_regime + peg_state
8. Global risk              — latest.risk_state / gv.state

Force state vocabulary: confirm | watch | neutral | stress
  confirm   — green: force actively arming / supporting
  watch     — amber: mixed / partially confirming
  neutral   — gray:  no clear directional read
  stress    — red:   force actively pressing against bottom-arming

Bottom-arming count  = number of confirm states across all 8 forces
Chase-risk count     = number of stress states (tape extended / chasing)
Verdict label        = deterministic from (bottom_arming_n, chase_risk_n, total=8)
"""
from __future__ import annotations

import logging
from typing import Any

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_TOTAL_FORCES = 8

# ADR gap thresholds
_ADR_GAP_CONFIRM   =  1.0   # implied_open_gap_pct > +1% = confirm (bottom arming)
_ADR_GAP_WATCH     =  0.25  # > +0.25% = watch
_ADR_GAP_STRESS    = -1.0   # < -1% = stress (extended selloff risk)

# Market-drivers tech projection thresholds
_TECH_CONFIRM  =  0.4
_TECH_WATCH    =  0.15
_TECH_STRESS   = -0.4

# Narrative thresholds
_NARR_Z_SPIKE  = 2.0   # attention_shock_z >= this = notable
_NARR_TONE_HIGH = 65.0
_NARR_TONE_LOW  = 35.0

# Southbound flow thresholds (accel_z / net_flow proxies)
_SB_CONFIRM  =  0.5   # net or accel reading ≥ this = confirm
_SB_STRESS   = -0.5

# Breadth thresholds (pct_above_200 or advance-decline readings)
_BREADTH_CONFIRM = 0.55   # above200 fraction >= 55%
_BREADTH_WATCH   = 0.45
_BREADTH_STRESS  = 0.30

# CBBC state mapping
_CBBC_CONFIRM_STATES  = {"bear_skew_froth", "bear_skew"}   # bears exhausted → potential squeeze
_CBBC_WATCH_STATES    = {"balanced"}
_CBBC_STRESS_STATES   = {"bull_skew_froth", "bull_skew"}   # bulls overcrowded → chase risk

# Peg / liquidity regime
_EASY_CONFIRM   = "EASY"
_TIGHT_STRESS   = "TIGHT"

# Global risk states
_RISK_ON_CONFIRM = {"Risk-on", "risk_on"}
_RISK_OFF_STRESS = {"Risk-off", "risk_off"}


# ---------------------------------------------------------------------------
# Per-force state derivation
# ---------------------------------------------------------------------------

def _adr_force(adr_bridge: dict | None) -> dict:
    """Force 1: ADR offshore bridge."""
    key = "adr_bridge"
    name_en = "ADR Offshore Bridge"
    name_zh = "离岸 / ADR 桥"

    try:
        if not adr_bridge:
            return _neutral(key, name_en, name_zh, "no data", "无数据")
        comp = adr_bridge.get("composite") or {}
        gap = comp.get("bellwether_implied_open_pct")
        ctx = comp.get("gap_context", "")
        fresh = adr_bridge.get("freshness_verdict", "")
        if fresh in ("stale", "dead"):
            return _neutral(key, name_en, name_zh,
                            f"data {fresh}", f"数据{fresh}")
        if gap is None:
            return _neutral(key, name_en, name_zh, "no gap data", "无隐含跳空数据")
        gap = float(gap)
        if gap >= _ADR_GAP_CONFIRM:
            return _state(key, name_en, name_zh, "confirm",
                          f"implied open {gap:+.1f}% — offshore bid",
                          f"隐含跳空 {gap:+.1f}% — 离岸做多")
        if gap >= _ADR_GAP_WATCH:
            return _state(key, name_en, name_zh, "watch",
                          f"implied open {gap:+.1f}% — mild positive",
                          f"隐含跳空 {gap:+.1f}% — 温和偏多")
        if gap <= _ADR_GAP_STRESS:
            return _state(key, name_en, name_zh, "stress",
                          f"implied open {gap:+.1f}% — offshore pressure",
                          f"隐含跳空 {gap:+.1f}% — 离岸承压")
        return _state(key, name_en, name_zh, "neutral",
                      f"implied open {gap:+.1f}% — flat",
                      f"隐含跳空 {gap:+.1f}% — 平盘")
    except Exception as e:  # noqa: BLE001
        log.debug("hk_command_panel: adr force failed (%s)", e)
        return _neutral(key, name_en, name_zh, "compute error", "计算错误")


def _tech_force(market_drivers: dict | None) -> dict:
    """Force 2: Tech / internet bellwether impulse."""
    key = "tech_impulse"
    name_en = "Tech Bellwether Impulse"
    name_zh = "科技龙头动量"

    try:
        if not market_drivers:
            return _neutral(key, name_en, name_zh, "no data", "无数据")
        # Look for tech_internet_leadership in the drivers dict
        drivers = market_drivers.get("drivers") or {}
        tech = drivers.get("tech_internet_leadership") or {}
        proj = tech.get("projection")
        sign = tech.get("sign")
        if proj is None:
            return _neutral(key, name_en, name_zh, "no tech read", "无科技读数")
        proj = float(proj)
        if proj >= _TECH_CONFIRM:
            return _state(key, name_en, name_zh, "confirm",
                          f"HSTECH leading up (proj {proj:+.2f})",
                          f"恒生科技领涨（投影 {proj:+.2f}）")
        if proj >= _TECH_WATCH:
            return _state(key, name_en, name_zh, "watch",
                          f"HSTECH mild positive (proj {proj:+.2f})",
                          f"恒生科技温和偏多（投影 {proj:+.2f}）")
        if proj <= _TECH_STRESS:
            return _state(key, name_en, name_zh, "stress",
                          f"HSTECH de-rating (proj {proj:+.2f})",
                          f"恒生科技承压（投影 {proj:+.2f}）")
        return _state(key, name_en, name_zh, "neutral",
                      f"tech neutral (proj {proj:+.2f})",
                      f"科技中性（投影 {proj:+.2f}）")
    except Exception as e:  # noqa: BLE001
        log.debug("hk_command_panel: tech force failed (%s)", e)
        return _neutral(key, name_en, name_zh, "compute error", "计算错误")


def _narrative_force(hk_narrative: dict | None) -> dict:
    """Force 3: Narrative / attention shock."""
    key = "narrative"
    name_en = "Narrative Attention"
    name_zh = "舆情关注度"

    try:
        if not hk_narrative:
            return _neutral(key, name_en, name_zh, "no data", "无数据")
        fresh = hk_narrative.get("freshness", "")
        if fresh in ("stale", "missing"):
            return _neutral(key, name_en, name_zh, f"data {fresh}", f"数据{fresh}")
        entities = hk_narrative.get("entities") or []
        if not entities:
            return _neutral(key, name_en, name_zh, "no entities", "无实体数据")

        # Aggregate across entities: count spikes and tone shifts
        spike_count = 0
        tone_pos = 0
        tone_neg = 0
        valid = 0
        for ent in entities:
            state = ent.get("narrative_state")
            if state is None:
                continue
            valid += 1
            if state == "attention_spike":
                spike_count += 1
            elif state == "tone_positive_shift":
                tone_pos += 1
            elif state == "tone_negative_shift":
                tone_neg += 1

        if valid == 0:
            return _neutral(key, name_en, name_zh, "all young series", "序列尚不成熟")

        if spike_count >= 2 and tone_pos >= 1:
            return _state(key, name_en, name_zh, "confirm",
                          f"{spike_count} attention spikes + tone positive",
                          f"{spike_count} 个关注度峰值 + 情绪偏正")
        if spike_count >= 1 or tone_pos >= 2:
            return _state(key, name_en, name_zh, "watch",
                          f"attention elevated ({spike_count} spikes, +tone {tone_pos})",
                          f"关注度升温（{spike_count} 峰值，正面 {tone_pos}）")
        if tone_neg >= 2:
            return _state(key, name_en, name_zh, "stress",
                          f"{tone_neg} entities tone-negative",
                          f"{tone_neg} 个实体情绪偏负")
        return _state(key, name_en, name_zh, "neutral",
                      "narrative quiet", "舆情平静")
    except Exception as e:  # noqa: BLE001
        log.debug("hk_command_panel: narrative force failed (%s)", e)
        return _neutral(key, name_en, name_zh, "compute error", "计算错误")


def _southbound_force(internals: dict | None) -> dict:
    """Force 4: Southbound flow — mainland buy appetite."""
    key = "southbound"
    name_en = "Southbound Flow"
    name_zh = "南向资金"

    try:
        if not internals:
            return _neutral(key, name_en, name_zh, "no internals data", "无内部数据")
        sb = internals.get("southbound") or {}
        if not sb:
            return _neutral(key, name_en, name_zh, "no southbound data", "无南向数据")

        # Read the available southbound fields
        net = sb.get("net_hkd")   # latest net HKD flow
        accel = sb.get("accel_z") if sb.get("accel_z") is not None else None
        # Also check trend description if present
        trend = sb.get("trend", "")
        appetite = sb.get("appetite", "")

        # Derive state from what we have
        if accel is not None:
            accel = float(accel)
            if accel >= _SB_CONFIRM:
                return _state(key, name_en, name_zh, "confirm",
                              f"SB accelerating (z={accel:+.1f})",
                              f"南向加速流入（z={accel:+.1f}）")
            if accel <= _SB_STRESS:
                return _state(key, name_en, name_zh, "stress",
                              f"SB decelerating (z={accel:+.1f})",
                              f"南向减速（z={accel:+.1f}）")
            return _state(key, name_en, name_zh, "watch",
                          f"SB flow mixed (z={accel:+.1f})",
                          f"南向流向中性（z={accel:+.1f}）")

        # Fallback on net flow direction / appetite string
        if appetite in ("strong_buy", "buying"):
            return _state(key, name_en, name_zh, "confirm",
                          "southbound buying", "南向积极买入")
        if appetite in ("selling", "strong_sell"):
            return _state(key, name_en, name_zh, "stress",
                          "southbound selling", "南向净卖出")
        if net is not None:
            net = float(net)
            if net > 0:
                return _state(key, name_en, name_zh, "watch",
                              f"net positive HKD {net/1e8:.1f}亿",
                              f"净流入港元 {net/1e8:.1f}亿")
            return _state(key, name_en, name_zh, "neutral",
                          f"net flow {net/1e8:.1f}亿", f"净流量 {net/1e8:.1f}亿")
        return _neutral(key, name_en, name_zh, "no flow metrics", "无流量指标")
    except Exception as e:  # noqa: BLE001
        log.debug("hk_command_panel: southbound force failed (%s)", e)
        return _neutral(key, name_en, name_zh, "compute error", "计算错误")


def _breadth_force(breadth: dict | None) -> dict:
    """Force 5: Breadth thrust."""
    key = "breadth"
    name_en = "Breadth Thrust"
    name_zh = "市场广度"

    try:
        if not breadth:
            return _neutral(key, name_en, name_zh, "no data", "无数据")

        # breadth dict from _breadth() or conditions
        pct200 = breadth.get("pct_above_200d") or breadth.get("above_200d")
        adv_dec = breadth.get("adv_dec_ratio")
        pctile = breadth.get("above200_pctile")   # from conditions

        if pct200 is not None:
            pct200 = float(pct200)
            if pct200 >= _BREADTH_CONFIRM:
                return _state(key, name_en, name_zh, "confirm",
                              f"{pct200:.0%} above 200dma — broad participation",
                              f"{pct200:.0%} 站上 200 日均线 — 广度充分")
            if pct200 >= _BREADTH_WATCH:
                return _state(key, name_en, name_zh, "watch",
                              f"{pct200:.0%} above 200dma — mixed",
                              f"{pct200:.0%} 站上 200 日均线 — 分化")
            if pct200 <= _BREADTH_STRESS:
                return _state(key, name_en, name_zh, "stress",
                              f"{pct200:.0%} above 200dma — thin tape",
                              f"{pct200:.0%} 站上 200 日均线 — 窄幅下跌")
            return _state(key, name_en, name_zh, "neutral",
                          f"{pct200:.0%} above 200dma",
                          f"{pct200:.0%} 站上 200 日均线")

        if adv_dec is not None:
            adv_dec = float(adv_dec)
            if adv_dec > 1.5:
                return _state(key, name_en, name_zh, "confirm",
                              f"A/D {adv_dec:.1f} — advancing", f"涨跌比 {adv_dec:.1f} — 上涨为主")
            if adv_dec < 0.7:
                return _state(key, name_en, name_zh, "stress",
                              f"A/D {adv_dec:.1f} — declining", f"涨跌比 {adv_dec:.1f} — 下跌为主")
            return _state(key, name_en, name_zh, "neutral",
                          f"A/D {adv_dec:.1f} — balanced", f"涨跌比 {adv_dec:.1f} — 平衡")

        return _neutral(key, name_en, name_zh, "no breadth metrics", "无广度指标")
    except Exception as e:  # noqa: BLE001
        log.debug("hk_command_panel: breadth force failed (%s)", e)
        return _neutral(key, name_en, name_zh, "compute error", "计算错误")


def _cbbc_force(cbbc_map: dict | None) -> dict:
    """Force 6: CBBC leverage — bull/bear skew."""
    key = "cbbc"
    name_en = "CBBC Leverage"
    name_zh = "CBBC 杠杆"

    try:
        if not cbbc_map:
            return _neutral(key, name_en, name_zh, "no data", "无数据")
        fresh = cbbc_map.get("freshness", "")
        if fresh in ("stale", "dead", "missing"):
            return _neutral(key, name_en, name_zh, f"data {fresh}", f"数据{fresh}")

        bellwethers = cbbc_map.get("bellwethers") or []
        if not bellwethers:
            return _neutral(key, name_en, name_zh, "no bellwethers", "无龙头数据")

        # Count leverage states across bellwethers (index-weighted = ^HSI, ^HSTECH first)
        state_counts: dict[str, int] = {}
        for bw in bellwethers:
            ls = bw.get("leverage_state", "no_data")
            state_counts[ls] = state_counts.get(ls, 0) + 1

        bear_crowd = (state_counts.get("bear_skew_froth", 0) +
                      state_counts.get("bear_skew", 0))
        bull_crowd = (state_counts.get("bull_skew_froth", 0) +
                      state_counts.get("bull_skew", 0))
        total = len(bellwethers)

        if bear_crowd > total / 2:
            return _state(key, name_en, name_zh, "confirm",
                          f"bear skew in {bear_crowd}/{total} — potential squeeze",
                          f"{bear_crowd}/{total} 龙头空方拥挤 — 潜在轧空")
        if bull_crowd > total / 2:
            return _state(key, name_en, name_zh, "stress",
                          f"bull skew in {bull_crowd}/{total} — retail froth",
                          f"{bull_crowd}/{total} 龙头多方拥挤 — 散户追高")
        # Mixed
        dominant_state = max(state_counts, key=lambda k: state_counts[k])
        return _state(key, name_en, name_zh, "watch",
                      f"CBBC balanced ({dominant_state})",
                      f"CBBC 平衡（{dominant_state}）")
    except Exception as e:  # noqa: BLE001
        log.debug("hk_command_panel: cbbc force failed (%s)", e)
        return _neutral(key, name_en, name_zh, "compute error", "计算错误")


def _funding_peg_force(funding: dict | None, latest: dict | None) -> dict:
    """Force 7: Funding / peg — HKMA aggregate balance + peg stress."""
    key = "funding_peg"
    name_en = "Funding / Peg"
    name_zh = "资金 / 联汇"

    try:
        peg_state = None
        liq_regime = None
        peg_level = None
        agg_pctile = None

        if latest:
            peg_state = latest.get("peg_state")
            gv = latest.get("global_snapshot") or {}
            peg_info = gv.get("peg") or {}
            peg_level = peg_info.get("level")
            if not peg_state:
                peg_state = peg_info.get("state")

        if funding:
            agg_pctile = funding.get("agg_pctile")
            peg_from_funding = (funding.get("peg") or {}).get("state")
            if not peg_state:
                peg_state = peg_from_funding

        # Derive state
        # EASY liquidity (high aggregate balance) + stable/strong peg = confirm
        # TIGHT liquidity (low aggregate balance) + weak peg side = stress
        if agg_pctile is not None:
            pctile = int(agg_pctile)
            if pctile >= 60:
                liq_label = "ample"
                base_state = "confirm"
            elif pctile >= 35:
                liq_label = "neutral"
                base_state = "neutral"
            else:
                liq_label = "tight"
                base_state = "stress"

            peg_note = f" peg {peg_state}" if peg_state else ""
            if base_state == "confirm":
                return _state(key, name_en, name_zh, "confirm",
                              f"HK liquidity {liq_label} (AB pctile {pctile}%){peg_note}",
                              f"港元流动性充裕（AB分位 {pctile}%）{peg_note}")
            if base_state == "stress":
                return _state(key, name_en, name_zh, "stress",
                              f"HK liquidity {liq_label} (AB pctile {pctile}%){peg_note}",
                              f"港元流动性偏紧（AB分位 {pctile}%）{peg_note}")
            return _state(key, name_en, name_zh, "neutral",
                          f"HK liquidity {liq_label} (AB pctile {pctile}%){peg_note}",
                          f"港元流动性中性（AB分位 {pctile}%）{peg_note}")

        # Fallback: peg_state only
        if peg_state:
            ps = str(peg_state).lower()
            if "strong" in ps or "easy" in ps:
                return _state(key, name_en, name_zh, "confirm",
                              f"peg {peg_state}", f"联汇 {peg_state}")
            if "weak" in ps or "stress" in ps or "tight" in ps:
                return _state(key, name_en, name_zh, "stress",
                              f"peg {peg_state}", f"联汇 {peg_state}")
            return _state(key, name_en, name_zh, "watch",
                          f"peg {peg_state}", f"联汇 {peg_state}")

        return _neutral(key, name_en, name_zh, "no funding data", "无资金数据")
    except Exception as e:  # noqa: BLE001
        log.debug("hk_command_panel: funding/peg force failed (%s)", e)
        return _neutral(key, name_en, name_zh, "compute error", "计算错误")


def _global_risk_force(latest: dict | None) -> dict:
    """Force 8: Global risk overlay."""
    key = "global_risk"
    name_en = "Global Risk"
    name_zh = "全球风险"

    try:
        if not latest:
            return _neutral(key, name_en, name_zh, "no data", "无数据")

        risk_state = latest.get("risk_state")
        gv = latest.get("global_snapshot") or {}
        gv_state = gv.get("state")
        state_str = str(risk_state or gv_state or "").lower()

        if not state_str:
            return _neutral(key, name_en, name_zh, "unknown", "未知")

        if "risk-on" in state_str or "risk_on" in state_str:
            return _state(key, name_en, name_zh, "confirm",
                          f"global Risk-on ({risk_state or gv_state})",
                          f"全球风险偏好（{risk_state or gv_state}）")
        if "risk-off" in state_str or "risk_off" in state_str:
            return _state(key, name_en, name_zh, "stress",
                          f"global Risk-off ({risk_state or gv_state})",
                          f"全球避险（{risk_state or gv_state}）")
        return _state(key, name_en, name_zh, "watch",
                      f"global mixed ({risk_state or gv_state})",
                      f"全球混合（{risk_state or gv_state}）")
    except Exception as e:  # noqa: BLE001
        log.debug("hk_command_panel: global_risk force failed (%s)", e)
        return _neutral(key, name_en, name_zh, "compute error", "计算错误")


# ---------------------------------------------------------------------------
# Verdict label derivation (deterministic)
# ---------------------------------------------------------------------------

def _verdict_label(bottom_n: int, chase_n: int, total: int) -> tuple[str, str]:
    """Return (label_en, label_zh) from the tally. Deterministic, no LLM."""
    if bottom_n >= 6:
        return "Bottom Ignition", "多因素点火"
    if bottom_n >= 4:
        return "Bottom Arming", "底部酝酿"
    if chase_n >= 5:
        return "Chase Risk", "追涨风险"
    if chase_n >= 3:
        return "Extended — Caution", "过热 — 警惕"
    if bottom_n >= 2:
        return "Mixed — Watch", "混合 — 观察"
    return "Quiet / No Setup", "平静 / 无明显机会"


# ---------------------------------------------------------------------------
# Catalyst tape helper
# ---------------------------------------------------------------------------

def _build_catalyst_tape(
    filing_bus: dict | None,
    catalyst_strip: list | None,
    hk_narrative: dict | None,
    max_items: int = 6,
) -> list[dict]:
    """Merge filing-bus events + scheduled catalysts + narrative spikes.
    Newest first, source-tagged. Returns up to max_items rows."""
    rows: list[dict] = []

    # Filing bus tape
    try:
        if filing_bus:
            tape = filing_bus.get("tape") or []
            for ev in tape[:3]:
                rows.append({
                    "date": ev.get("date") or ev.get("filing_date") or "—",
                    "source": "filing",
                    "source_zh": "公告",
                    "text_en": (
                        f"{ev.get('ticker','?')} · {ev.get('type_label','filing')} "
                        f"{ev.get('description','') or ''}"
                    ).strip(),
                    "text_zh": (
                        f"{ev.get('ticker','?')} · {ev.get('type_label_zh','公告')} "
                        f"{ev.get('description_zh','') or ev.get('description','') or ''}"
                    ).strip(),
                })
    except Exception as e:  # noqa: BLE001
        log.debug("hk_command_panel: filing tape failed (%s)", e)

    # Scheduled catalyst strip
    try:
        if catalyst_strip:
            for cat in catalyst_strip[:3]:
                rows.append({
                    "date": cat.get("date") or "—",
                    "source": "catalyst",
                    "source_zh": "催化剂",
                    "text_en": (
                        f"{cat.get('ticker','?')} · {cat.get('event','catalyst')}"
                    ),
                    "text_zh": (
                        f"{cat.get('ticker','?')} · {cat.get('event_zh','') or cat.get('event','催化剂')}"
                    ),
                })
    except Exception as e:  # noqa: BLE001
        log.debug("hk_command_panel: catalyst strip failed (%s)", e)

    # Narrative spikes (entities with attention_spike)
    try:
        if hk_narrative:
            for ent in (hk_narrative.get("entities") or []):
                if ent.get("narrative_state") == "attention_spike":
                    rows.append({
                        "date": ent.get("as_of_date") or "—",
                        "source": "narrative",
                        "source_zh": "舆情",
                        "text_en": (
                            f"{ent.get('name_en','?')} attention spike "
                            f"z={ent.get('attention_shock_z','?'):.1f}"
                            if isinstance(ent.get("attention_shock_z"), (int, float))
                            else f"{ent.get('name_en','?')} attention spike"
                        ),
                        "text_zh": (
                            f"{ent.get('name_zh','?')} 关注度峰值 "
                            f"z={ent.get('attention_shock_z','?'):.1f}"
                            if isinstance(ent.get("attention_shock_z"), (int, float))
                            else f"{ent.get('name_zh','?')} 关注度峰值"
                        ),
                    })
    except Exception as e:  # noqa: BLE001
        log.debug("hk_command_panel: narrative tape failed (%s)", e)

    # Sort by date descending (simple lexicographic — ISO dates sort correctly)
    rows.sort(key=lambda r: r.get("date") or "", reverse=True)
    return rows[:max_items]


# ---------------------------------------------------------------------------
# Bottom-watch / Chase-watch scorecards
# ---------------------------------------------------------------------------

def _build_scorecards(setups: dict | None) -> tuple[list[dict], list[dict]]:
    """Extract bottom_watch and chase_watch from setups.washout_watch."""
    bottom_watch: list[dict] = []
    chase_watch: list[dict] = []
    try:
        if not setups:
            return bottom_watch, chase_watch
        ww = setups.get("washout_watch") or []
        for row in ww:
            state = row.get("state", "")
            entry = {
                "ticker": row.get("ticker", "?"),
                "name": row.get("name") or "",
                "state": state,
                "confluence_n": len(row.get("confluence_signals") or []),
                "signals": row.get("confluence_signals") or [],
                "knife_risk": bool(row.get("knife_risk")),
                "rsi": row.get("rsi"),
                "dist_200dma": row.get("dist_200dma"),
            }
            if state in ("washout_watch", "ignition_watch", "pullback_entry_watch"):
                bottom_watch.append(entry)
            elif state == "chase_risk":
                chase_watch.append(entry)
    except Exception as e:  # noqa: BLE001
        log.debug("hk_command_panel: scorecards failed (%s)", e)
    return bottom_watch, chase_watch


# ---------------------------------------------------------------------------
# Freshness strip
# ---------------------------------------------------------------------------

def _build_freshness_strip(freshness: dict | None) -> dict:
    """Build the freshness strip dict from the sentinel result."""
    try:
        if not freshness:
            return {"verdict": "unknown", "label_en": "Freshness unknown",
                    "label_zh": "新鲜度未知", "expected_session": None,
                    "n_fresh": 0, "n_total": 0}
        verdict = freshness.get("verdict", "unknown")
        expected = freshness.get("expected_session") or "—"
        stores = freshness.get("stores") or {}
        n_fresh = sum(1 for v in stores.values()
                      if v.get("state") in ("fresh", "slow"))
        n_total = len(stores)

        if verdict == "ok":
            label_en = f"Data fresh · HK {expected} close · {n_fresh}/{n_total} stores current"
            label_zh = f"数据新鲜 · 港股 {expected} 收盘 · {n_fresh}/{n_total} 数据源同步"
        elif verdict == "degraded":
            label_en = f"Data degraded · HK {expected} · {n_fresh}/{n_total} stores fresh"
            label_zh = f"数据降级 · 港股 {expected} · {n_fresh}/{n_total} 数据源新鲜"
        else:
            label_en = f"Data STALE — do not rely on displayed values (expected {expected})"
            label_zh = f"数据已过期 — 请勿依赖当前值（预期交易日 {expected}）"

        return {
            "verdict": verdict,
            "label_en": label_en,
            "label_zh": label_zh,
            "expected_session": expected,
            "n_fresh": n_fresh,
            "n_total": n_total,
        }
    except Exception as e:  # noqa: BLE001
        log.debug("hk_command_panel: freshness strip failed (%s)", e)
        return {"verdict": "unknown", "label_en": "Freshness check error",
                "label_zh": "新鲜度检查错误", "expected_session": None,
                "n_fresh": 0, "n_total": 0}


# ---------------------------------------------------------------------------
# Small helpers
# ---------------------------------------------------------------------------

def _state(key: str, name_en: str, name_zh: str, state: str,
           detail_en: str, detail_zh: str) -> dict:
    return {
        "key": key, "name_en": name_en, "name_zh": name_zh,
        "state": state, "detail_en": detail_en, "detail_zh": detail_zh,
    }


def _neutral(key: str, name_en: str, name_zh: str,
             detail_en: str = "—", detail_zh: str = "—") -> dict:
    return _state(key, name_en, name_zh, "neutral", detail_en, detail_zh)


# ---------------------------------------------------------------------------
# Public API: compute
# ---------------------------------------------------------------------------

def compute(
    *,
    freshness: dict | None = None,
    adr_bridge: dict | None = None,
    market_drivers: dict | None = None,
    hk_narrative: dict | None = None,
    internals: dict | None = None,
    breadth: dict | None = None,
    cbbc_map: dict | None = None,
    funding: dict | None = None,
    latest: dict | None = None,
    filing_bus: dict | None = None,
    catalyst_strip: list | None = None,
    setups: dict | None = None,
) -> dict:
    """Compute the HK Command Panel.

    All arguments are optional keyword-only; any missing organ yields neutral
    for that force. Never raises.

    Returns::

        {
            "display_only": True,
            "freshness_strip": {...},
            "verdict": {
                "label_en": str, "label_zh": str,
                "bottom_arming_n": int,
                "chase_risk_n": int,
                "of": 8,
            },
            "force_stack": [
                {"key", "name_en", "name_zh", "state", "detail_en", "detail_zh"},
                ...  # 8 rows always
            ],
            "bottom_watch": [...],
            "chase_watch": [...],
            "catalyst_tape": [...],
        }
    """
    try:
        # Force stack (order matches the 8-force spec)
        forces = [
            _adr_force(adr_bridge),
            _tech_force(market_drivers),
            _narrative_force(hk_narrative),
            _southbound_force(internals),
            _breadth_force(breadth),
            _cbbc_force(cbbc_map),
            _funding_peg_force(funding, latest),
            _global_risk_force(latest),
        ]

        # Count confirms (bottom-arming) and stress (chase-risk)
        bottom_n = sum(1 for f in forces if f["state"] == "confirm")
        chase_n = sum(1 for f in forces if f["state"] == "stress")

        label_en, label_zh = _verdict_label(bottom_n, chase_n, _TOTAL_FORCES)

        freshness_strip = _build_freshness_strip(freshness)
        bottom_watch, chase_watch = _build_scorecards(setups)
        catalyst_tape = _build_catalyst_tape(filing_bus, catalyst_strip, hk_narrative)

        return {
            "display_only": True,
            "freshness_strip": freshness_strip,
            "verdict": {
                "label_en": label_en,
                "label_zh": label_zh,
                "bottom_arming_n": bottom_n,
                "chase_risk_n": chase_n,
                "of": _TOTAL_FORCES,
            },
            "force_stack": forces,
            "bottom_watch": bottom_watch,
            "chase_watch": chase_watch,
            "catalyst_tape": catalyst_tape,
            "note": "context, not a signal / 参考，非买卖信号",
        }
    except Exception as e:  # noqa: BLE001 — total safety net
        log.error("hk_command_panel.compute crashed (%s) — returning empty panel", e)
        return {
            "display_only": True,
            "freshness_strip": {"verdict": "unknown", "label_en": "—", "label_zh": "—",
                                 "expected_session": None, "n_fresh": 0, "n_total": 0},
            "verdict": {
                "label_en": "—", "label_zh": "—",
                "bottom_arming_n": 0, "chase_risk_n": 0, "of": _TOTAL_FORCES,
            },
            "force_stack": [],
            "bottom_watch": [],
            "chase_watch": [],
            "catalyst_tape": [],
            "error": str(e),
            "note": "context, not a signal / 参考，非买卖信号",
        }
