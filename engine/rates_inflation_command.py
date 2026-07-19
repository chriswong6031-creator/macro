"""Forward Path board — rates & inflation command context layer.

Schema: rates_command.v1
Chartered: research/RATES_INFLATION_COMMAND_MASTERPLAN_BY_FABLE.md §P5, W7.

PUBLIC API
----------
build_board(root)               — full artifact content dict
compact_state(contract)         — small comparable fingerprint for diffing
diff_changes(old_state, new)    — list of change items (max 6)
build_changes(old_contract, new_contract, new_asof) — (changes_block, prev_state_block)
compose_stance(board)           — {en, zh} deterministic stance sentence

HOUSE LAWS (RIC-W7 binding)
---------------------------
* RIC-R1:  display-only end-to-end.  Every emitted dict carries display_only=True,
           authority=False.  No scoring, ranking, gating, sizing, escalation.
* RIC-R9:  deterministic join of existing calibrated artifacts.  "benchmark" NEVER
           "consensus" (MRI-R5 — the word consensus is banned from all strings,
           EN and ZH 共识).  Conditions never intent (PS-R1): no "Fed will …",
           no administration-timing predictions, no policy-intent classification.
* MRI-R4:  never originate a projection/probability.  Read artifact values only.
* MRI-R16: Polymarket values are context-only benchmark.  Display juxtaposition only,
           labeled "market-implied benchmark"; NEVER fused into computed state/score.
* PS-R4:   geopolitical legs are UNSIGNED qualitative display rows (no probability,
           no direction score).  Iran/oil context row = quote policy intel theater
           text + as-of stamp + staleness disclosure.
* Naming:  new field names MUST NOT contain substrings: forecast, predicted,
           expected_return, or "target" in the forward-price/return sense.  Existing
           read keys like fed_path.target_mid are fine to read, and `vs_target_pp`
           is permitted: it measures distance to the Fed's 2% inflation target (a
           policy constant), not a forward price/return target.
* "validated" banned from any user-facing string.
* Fail-open everywhere: absent/corrupt input → leg active=None + null_reason, never raises.
* Ledger law: forward_log.jsonl appends ONLY under nightly lane gate, keep-FIRST per
  asof_night.
* Additive only: never rename/remove keys in existing artifacts.
* Bilingual: every user-facing string has en + zh twins, equally plain.
* No LLM-originated content.
"""
from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Frozen thresholds (module-level constants — unit-tested exhaustively)
# ---------------------------------------------------------------------------
# H1 path_repricing: active when d20 >= +15 bp, easing mirror when d20 <= -15 bp
H1_HAWKISH_THRESHOLD_BP: float = 15.0
H1_DOVISH_THRESHOLD_BP: float = -15.0

# H2 breakeven_momentum: 20d velocity >= +8 bp
H2_BE_THRESHOLD_BP: float = 8.0

# H4 inflation_trajectory: cpi surprise_skew.tag == 'hotter'
# H5 curve_regime: bear_steepener + term_premium_dir == 'rising'
# H6 anchoring_strain: worst anchoring bands
H6_STRAINED_BANDS: frozenset = frozenset({"strained", "de-anchoring", "drifting up"})

# E1 equity_deleveraging: radar.state in caution/elevated/risk-off
E1_TRIGGER_STATES: frozenset = frozenset({"caution", "elevated", "risk-off"})

# E4 credit_stress: hy_oas_z >= 1.0
E4_HY_OAS_Z_THRESHOLD: float = 1.0

# D1 dots_vs_market divergence: |gap_bp| >= 50
D1_GAP_BP_THRESHOLD: float = 50.0

# D3 pressure_vs_market
D3_IMPLIED_BP_LOW: float = 0.0
D3_IMPLIED_BP_HIGH: float = 25.0

# shock_state staleness threshold (days)
SHOCK_STALE_DAYS: int = 7

# Max change items in diff
_MAX_CHANGES: int = 6

# ---------------------------------------------------------------------------
# Plain-word label maps
# ---------------------------------------------------------------------------

_NET_STATE_LABELS: dict[str, dict[str, str]] = {
    "repricing_hawkish": {
        "en": "Hike expectations rising now",
        "zh": "加息预期正在升温",
    },
    "pressure_building": {
        "en": "Hawkish pressure building — market not moved yet",
        "zh": "鹰派压力积聚——市场尚未定价",
    },
    "repricing_dovish": {
        "en": "Cut expectations rising now",
        "zh": "降息预期正在升温",
    },
    "pressure_fading": {
        "en": "Easing pressure building",
        "zh": "宽松压力积聚",
    },
    "two_sided": {
        "en": "Two-sided — watch the tape",
        "zh": "双向——观察市场走势",
    },
}

_ANCHORING_LABEL_ZH: dict[str, str] = {
    "anchored": "锚定",
    "drifting up": "上行脱锚",
    "drifting down": "下行",
    "strained": "承压",
    "de-anchoring": "脱锚",
}

_CURVE_REGIME_ZH: dict[str, str] = {
    "bear_steepener": "熊市变陡",
    "bull_steepener": "牛市变陡",
    "bear_flattener": "熊市变平",
    "bull_flattener": "牛市变平",
    "flat": "曲线平坦",
    "inverted": "曲线倒挂",
}

_INFL_DIR_ZH: dict[str, str] = {
    "re-accelerating": "再加速",
    "steady": "平稳",
    "cooling": "降温",
    "rising": "上行",
    "falling": "下行",
    "flat": "横盘",
}

_DIFF_ORDER: list[str] = [
    "net_state",
    "curve_regime",
    "anchoring",
    "infl_dir",
    "usd_dir",
    "hawk_score",
    "ease_score",
]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _data_root(root=None) -> Path:
    if root is not None:
        return Path(root)
    try:
        from lib import config as _cfg
        return _cfg.data_dir()
    except Exception:
        return Path(__file__).resolve().parent.parent / "data"


def _read_json(path: Path) -> dict | None:
    try:
        return json.loads(path.read_text())
    except Exception:
        return None


def _safe_get(obj: Any, *path) -> Any:
    """Nested dict accessor that fails open to None."""
    for key in path:
        if not isinstance(obj, dict):
            return None
        obj = obj.get(key)
    return obj


def _staleness_days(ts_str: str | None, today: datetime | None = None) -> int | None:
    """Return age in whole days for an ISO timestamp string, or None."""
    if not ts_str:
        return None
    try:
        from datetime import date
        # try ISO datetime first
        try:
            ts = datetime.fromisoformat(ts_str.replace("Z", "+00:00"))
            ref = today or datetime.now(timezone.utc)
            if ts.tzinfo is None:
                ts = ts.replace(tzinfo=timezone.utc)
            if ref.tzinfo is None:
                ref = ref.replace(tzinfo=timezone.utc)
            return (ref - ts).days
        except Exception:
            # date-only string
            ts_d = date.fromisoformat(ts_str[:10])
            ref_d = (today or datetime.now(timezone.utc)).date()
            return (ref_d - ts_d).days
    except Exception:
        return None


def _intel_staleness_days(intel: dict | None) -> int | None:
    as_of = _safe_get(intel, "as_of")
    return _staleness_days(as_of)


# ---------------------------------------------------------------------------
# Leg builders
# ---------------------------------------------------------------------------

def _build_hawkish_legs(
    fed_path: dict,
    tx: dict,
    zq_d20_bp: float | None,
    release_items: list[dict],
    shock_state_oil: dict | None,
    shock_stale: bool,
) -> list[dict]:
    """Build H1-H6 hawkish pressure legs.

    Each leg: {key, active: true|false|null, weight, value, detail_en, detail_zh, null_reason}
    """
    legs: list[dict] = []

    # H1 — path_repricing (weight 2)
    if zq_d20_bp is None:
        legs.append({
            "key": "H1_path_repricing",
            "active": None,
            "weight": 2,
            "value": None,
            "detail_en": "Rate futures 12m path change unavailable (zq_path.parquet missing).",
            "detail_zh": "利率期货12个月路径变化不可用（zq_path.parquet缺失）。",
            "null_reason": "zq_path.parquet absent or unreadable",
        })
    else:
        active = zq_d20_bp >= H1_HAWKISH_THRESHOLD_BP
        legs.append({
            "key": "H1_path_repricing",
            "active": active,
            "weight": 2,
            "value": round(zq_d20_bp, 1),
            "detail_en": (
                f"Futures added {zq_d20_bp:+.1f}bp of 12-month rate over the last month."
                if active
                else f"12-month rate futures moved {zq_d20_bp:+.1f}bp over 20 trading days (threshold: +{H1_HAWKISH_THRESHOLD_BP:.0f}bp)."
            ),
            "detail_zh": (
                f"期货在过去一个月内将12个月利率上调了{zq_d20_bp:+.1f}个基点。"
                if active
                else f"20个交易日内12个月利率期货变动{zq_d20_bp:+.1f}个基点（阈值：+{H1_HAWKISH_THRESHOLD_BP:.0f}bp）。"
            ),
            "null_reason": None,
        })

    # H2 — breakeven_momentum (weight 1)
    be_v = _safe_get(tx, "breakeven_decomp", "velocity_bp", "chg_20d_bp")
    if be_v is None:
        legs.append({
            "key": "H2_breakeven_momentum",
            "active": None,
            "weight": 1,
            "value": None,
            "detail_en": "Breakeven velocity unavailable.",
            "detail_zh": "盈亏平衡点速度不可用。",
            "null_reason": "breakeven_decomp.velocity_bp.chg_20d_bp absent",
        })
    else:
        active = float(be_v) >= H2_BE_THRESHOLD_BP
        legs.append({
            "key": "H2_breakeven_momentum",
            "active": active,
            "weight": 1,
            "value": round(float(be_v), 1),
            "detail_en": f"10y breakeven moved {be_v:+.1f}bp over 20 days (threshold: +{H2_BE_THRESHOLD_BP:.0f}bp).",
            "detail_zh": f"10年期盈亏平衡点20天变动{be_v:+.1f}个基点（阈值：+{H2_BE_THRESHOLD_BP:.0f}bp）。",
            "null_reason": None,
        })

    # H3 — oil_impulse (weight 1)
    oil_trend = _safe_get(tx, "state", "rates")  # We'll read from commodity artifact separately
    # The commodity data is passed via tx dict indirectly — caller injects oil_trend/shock
    # We'll use the values already extracted from the commodity artifact (passed as shock_state_oil)
    # and read from fed_path (cause_badge from breakeven_decomp)
    cause_badge_cause = _safe_get(tx, "breakeven_decomp", "cause_badge", "cause")

    # oil data is NOT in tx; it is passed as parameters
    # Caller must inject oil_trend from commodity/latest.json
    # We use the _oil_trend parameter (see build_board)
    # For this function, oil_trend is passed via shock_state_oil dict with extra keys
    _oil_trend = _safe_get(shock_state_oil, "_oil_trend") if shock_state_oil else None
    _oil_chg = _safe_get(shock_state_oil, "_oil_chg") if shock_state_oil else None

    if _oil_trend is None:
        legs.append({
            "key": "H3_oil_impulse",
            "active": None,
            "weight": 1,
            "value": None,
            "detail_en": "Oil trend data unavailable.",
            "detail_zh": "原油趋势数据不可用。",
            "null_reason": "commodity/latest.json absent or oil.trend missing",
        })
    else:
        oil_up = _oil_trend == "up"
        if shock_stale:
            # Judge on trend + cause_badge alone
            shock_qualifier = oil_up and cause_badge_cause == "oil"
            detail_note_en = " (shock_state stale >7d — judged on trend+cause_badge only)"
            detail_note_zh = "（shock_state超过7天未更新——仅依据趋势和原因标识判断）"
        else:
            shock_oil_state = _safe_get(shock_state_oil, "state") if shock_state_oil else None
            shock_qualifier = shock_oil_state in {"stabilizing", "shock"}
            detail_note_en = ""
            detail_note_zh = ""
        active = oil_up and (shock_qualifier or cause_badge_cause == "oil")
        legs.append({
            "key": "H3_oil_impulse",
            "active": active,
            "weight": 1,
            "value": _oil_trend,
            "detail_en": (
                f"Oil trending {_oil_trend} ({_oil_chg:+.1f}% 20d) with shock/oil-driven breakeven pressure.{detail_note_en}"
                if active
                else f"Oil trend: {_oil_trend}; shock or oil-driver condition not met.{detail_note_en}"
            ),
            "detail_zh": (
                f"原油趋势{_oil_trend}（20天涨跌{_oil_chg:+.1f}%），叠加冲击/油价驱动的盈亏平衡压力。{detail_note_zh}"
                if active
                else f"原油趋势：{_oil_trend}；冲击或油价驱动条件未满足。{detail_note_zh}"
            ),
            "null_reason": None,
        })

    # H4 — inflation_trajectory (weight 1)
    # Nearest cpi_headline OR cpi_core tag == 'hotter', OR infl direction indicates re-acceleration
    cpi_hotter = False
    cpi_detail_en = "No upcoming CPI data with hotter skew."
    cpi_detail_zh = "无近期CPI数据显示偏热倾斜。"
    for item in release_items:
        rtype = item.get("release_type", "")
        if rtype in {"cpi_headline", "cpi_core"}:
            tag = _safe_get(item, "surprise_skew", "tag")
            if tag == "hotter":
                cpi_hotter = True
                cpi_detail_en = (
                    f"Nearest {rtype.replace('_', ' ')} (due {item.get('release_date', '?')}) "
                    f"skewed hotter (sigma={_safe_get(item, 'surprise_skew', 'sigma'):.2f})."
                )
                cpi_detail_zh = (
                    f"近期{rtype.replace('_', ' ')}（预定{item.get('release_date', '?')}）"
                    f"偏热（sigma={_safe_get(item, 'surprise_skew', 'sigma'):.2f}）。"
                )
                break

    infl_dir = _safe_get(tx, "state", "inflation", "direction")
    reaccel = infl_dir in {"re-accelerating", "rising"}
    active_h4 = cpi_hotter or reaccel

    if not cpi_hotter and reaccel:
        cpi_detail_en = f"Inflation direction: {infl_dir} (re-acceleration flag active)."
        cpi_detail_zh = f"通胀方向：{infl_dir}（再加速信号有效）。"

    legs.append({
        "key": "H4_inflation_trajectory",
        "active": active_h4,
        "weight": 1,
        "value": infl_dir,
        "detail_en": cpi_detail_en,
        "detail_zh": cpi_detail_zh,
        "null_reason": None,
    })

    # H5 — curve_regime (weight 1)
    yc_regime_key = _safe_get(tx, "yield_curve", "regime", "key")
    term_premium_dir = _safe_get(tx, "yield_curve", "regime", "term_premium_dir")

    if yc_regime_key is None:
        legs.append({
            "key": "H5_curve_regime",
            "active": None,
            "weight": 1,
            "value": None,
            "detail_en": "Yield curve regime unavailable.",
            "detail_zh": "收益率曲线形态不可用。",
            "null_reason": "yield_curve.regime.key absent",
        })
    else:
        active_h5 = yc_regime_key == "bear_steepener" and term_premium_dir == "rising"
        legs.append({
            "key": "H5_curve_regime",
            "active": active_h5,
            "weight": 1,
            "value": yc_regime_key,
            "detail_en": (
                f"Bear steepener with rising term premium — "
                "fiscal/risk-premium driven steepening, not growth-led."
                if active_h5
                else f"Curve regime: {yc_regime_key}; term premium direction: {term_premium_dir}."
                " Bear steepener + rising term premium condition not met."
            ),
            "detail_zh": (
                "熊市变陡叠加期限溢价上升——财政/风险溢价驱动，并非增长主导。"
                if active_h5
                else f"曲线形态：{_CURVE_REGIME_ZH.get(yc_regime_key, yc_regime_key)}；期限溢价方向：{term_premium_dir}。"
                "熊市变陡+期限溢价上升条件未满足。"
            ),
            "null_reason": None,
        })

    # H6 — anchoring_strain (weight 1)
    anchoring = _safe_get(tx, "state", "expectations", "anchoring")
    if anchoring is None:
        legs.append({
            "key": "H6_anchoring_strain",
            "active": None,
            "weight": 1,
            "value": None,
            "detail_en": "Anchoring state unavailable.",
            "detail_zh": "锚定状态不可用。",
            "null_reason": "state.expectations.anchoring absent",
        })
    else:
        active_h6 = str(anchoring).lower() in H6_STRAINED_BANDS
        legs.append({
            "key": "H6_anchoring_strain",
            "active": active_h6,
            "weight": 1,
            "value": anchoring,
            "detail_en": (
                f"Inflation expectations strained: anchoring = '{anchoring}'."
                if active_h6
                else f"Inflation expectations anchored: '{anchoring}'."
            ),
            "detail_zh": (
                f"通胀预期承压：锚定状态为'{_ANCHORING_LABEL_ZH.get(anchoring, anchoring)}'。"
                if active_h6
                else f"通胀预期稳定：'{_ANCHORING_LABEL_ZH.get(anchoring, anchoring)}'。"
            ),
            "null_reason": None,
        })

    return legs


def _build_easing_legs(
    tx: dict,
    release_items: list[dict],
    complex_growth_dir: str | None,
    chains: list[dict],
) -> list[dict]:
    """Build E1-E5 easing/offset legs."""
    legs: list[dict] = []

    # E1 — equity_deleveraging (weight 2)
    radar_state = _safe_get(tx, "_radar_state")  # injected by build_board
    if radar_state is None:
        legs.append({
            "key": "E1_equity_deleveraging",
            "active": None,
            "weight": 2,
            "value": None,
            "detail_en": "Equity radar state unavailable.",
            "detail_zh": "股票雷达状态不可用。",
            "null_reason": "market_state/latest.json absent",
        })
    else:
        active_e1 = str(radar_state).lower() in E1_TRIGGER_STATES
        legs.append({
            "key": "E1_equity_deleveraging",
            "active": active_e1,
            "weight": 2,
            "value": radar_state,
            "detail_en": (
                f"Equity radar in '{radar_state}' — risk-off pressure historically cools "
                "inflation and rate expectations."
                if active_e1
                else f"Equity radar in '{radar_state}' — not triggering offset."
            ),
            "detail_zh": (
                f"股票雷达处于'{radar_state}'状态——历史上风险规避会压制通胀和加息预期。"
                if active_e1
                else f"股票雷达处于'{radar_state}'状态——未触发对冲条件。"
            ),
            "null_reason": None,
        })

    # E2 — growth_cooling (weight 1)
    nfp_cooler = False
    e2_detail_en = "No NFP cooler skew; complex growth direction not falling."
    e2_detail_zh = "无NFP偏冷倾斜；商品综合增长方向未下行。"

    for item in release_items:
        if item.get("release_type") == "nfp":
            tag = _safe_get(item, "surprise_skew", "tag")
            if tag == "cooler":
                nfp_cooler = True
                e2_detail_en = f"NFP (due {item.get('release_date','?')}) skewed cooler."
                e2_detail_zh = f"NFP（预定{item.get('release_date','?')}）偏冷。"
            break

    growth_falling = complex_growth_dir == "falling"
    active_e2 = nfp_cooler or growth_falling

    if not nfp_cooler and growth_falling:
        e2_detail_en = "Commodity complex growth direction: falling."
        e2_detail_zh = "商品综合增长方向：下行。"
    elif nfp_cooler and growth_falling:
        e2_detail_en += " Commodity complex growth also falling."
        e2_detail_zh += " 商品综合增长方向也在下行。"

    legs.append({
        "key": "E2_growth_cooling",
        "active": active_e2,
        "weight": 1,
        "value": complex_growth_dir,
        "detail_en": e2_detail_en,
        "detail_zh": e2_detail_zh,
        "null_reason": None,
    })

    # E3 — dollar_tightening (weight 1)
    usd_dir = _safe_get(tx, "dollar_channel", "usd_dir")
    if usd_dir is None:
        # Try state.rates indirectly — dollar_channel may not always be present
        legs.append({
            "key": "E3_dollar_tightening",
            "active": None,
            "weight": 1,
            "value": None,
            "detail_en": "Dollar direction unavailable.",
            "detail_zh": "美元方向不可用。",
            "null_reason": "dollar_channel.usd_dir absent",
        })
    else:
        active_e3 = usd_dir == "strengthening"
        legs.append({
            "key": "E3_dollar_tightening",
            "active": active_e3,
            "weight": 1,
            "value": usd_dir,
            "detail_en": (
                "Dollar strengthening — acts as an external tightening offset to domestic inflation pressure."
                if active_e3
                else f"Dollar direction: {usd_dir} — no tightening offset active."
            ),
            "detail_zh": (
                "美元走强——作为对国内通胀压力的外部紧缩对冲。"
                if active_e3
                else f"美元方向：{usd_dir}——无紧缩对冲效果。"
            ),
            "null_reason": None,
        })

    # E4 — credit_stress (weight 1)
    hy_oas_z = _safe_get(tx, "breakeven_decomp", "costate", "hy_oas_z")
    if hy_oas_z is None:
        legs.append({
            "key": "E4_credit_stress",
            "active": None,
            "weight": 1,
            "value": None,
            "detail_en": "HY OAS z-score unavailable.",
            "detail_zh": "高收益利差z分数不可用。",
            "null_reason": "breakeven_decomp.costate.hy_oas_z absent",
        })
    else:
        active_e4 = float(hy_oas_z) >= E4_HY_OAS_Z_THRESHOLD
        legs.append({
            "key": "E4_credit_stress",
            "active": active_e4,
            "weight": 1,
            "value": round(float(hy_oas_z), 2),
            "detail_en": (
                f"HY OAS z-score elevated at {hy_oas_z:.2f} — credit stress may cool inflation pressure."
                if active_e4
                else f"HY OAS z-score: {hy_oas_z:.2f} (threshold: +{E4_HY_OAS_Z_THRESHOLD:.1f})."
            ),
            "detail_zh": (
                f"高收益利差z分数偏高{hy_oas_z:.2f}——信用压力可能抑制通胀。"
                if active_e4
                else f"高收益利差z分数：{hy_oas_z:.2f}（阈值：+{E4_HY_OAS_Z_THRESHOLD:.1f}）。"
            ),
            "null_reason": None,
        })

    # E5 — policy_easing_chain (weight 1)
    policy_easing_active = None
    for c in chains:
        if c.get("id") == "policy_easing":
            policy_easing_active = bool(c.get("active"))
            break

    if policy_easing_active is None:
        legs.append({
            "key": "E5_policy_easing_chain",
            "active": None,
            "weight": 1,
            "value": None,
            "detail_en": "Policy easing chain state unavailable.",
            "detail_zh": "政策宽松链状态不可用。",
            "null_reason": "chains[policy_easing] not found in transmission",
        })
    else:
        legs.append({
            "key": "E5_policy_easing_chain",
            "active": policy_easing_active,
            "weight": 1,
            "value": policy_easing_active,
            "detail_en": (
                "Policy easing transmission chain active — supports lower rate expectations."
                if policy_easing_active
                else "Policy easing transmission chain inactive."
            ),
            "detail_zh": (
                "政策宽松传导链活跃——支持降低加息预期。"
                if policy_easing_active
                else "政策宽松传导链未激活。"
            ),
            "null_reason": None,
        })

    return legs


def _compute_net_state(
    hawk_score: float,
    ease_score: float,
    zq_d20_bp: float | None,
    h1_active: bool | None,
) -> str:
    """Frozen net-state mapping (unit-tested exhaustively).

    Inputs:
        hawk_score: weighted sum of active hawkish legs (H1-H6)
        ease_score: weighted sum of active easing legs (E1-E5)
        zq_d20_bp:  20-day change in ZQ m12 (None if unavailable)
        h1_active:  whether H1 path_repricing is active
    """
    net = hawk_score - ease_score
    net_ease = ease_score - hawk_score

    # Hawkish path
    if h1_active and net >= 2:
        return "repricing_hawkish"
    if net >= 2:
        return "pressure_building"

    # Easing/dovish path (mirror of H1: d20 <= -15)
    h1_dovish_mirror = zq_d20_bp is not None and zq_d20_bp <= H1_DOVISH_THRESHOLD_BP
    if h1_dovish_mirror and net_ease >= 2:
        return "repricing_dovish"
    if net_ease >= 2:
        return "pressure_fading"

    return "two_sided"


def _compute_divergence(
    fed_path: dict,
    release_items: list[dict],
    tx: dict,
    net_state: str,
) -> list[dict]:
    """Compute D1-D3 divergence flags.

    Each: {key, active: bool|null, detail_en, detail_zh}
    """
    flags: list[dict] = []

    # D1 — dots_vs_market: |gap_bp| >= 50
    gap_bp = _safe_get(fed_path, "gap", "gap_bp")
    if gap_bp is None:
        flags.append({
            "key": "D1_dots_vs_market",
            "active": None,
            "detail_en": "Dot-vs-market gap unavailable.",
            "detail_zh": "点阵图与市场利差不可用。",
        })
    else:
        active_d1 = abs(float(gap_bp)) >= D1_GAP_BP_THRESHOLD
        lean_en = _safe_get(fed_path, "gap", "lean_en") or ""
        flags.append({
            "key": "D1_dots_vs_market",
            "active": active_d1,
            "value_bp": round(float(gap_bp), 1),
            "detail_en": (
                f"Significant divergence: market vs dot gap = {gap_bp:+.0f}bp ({lean_en})."
                if active_d1
                else f"Market vs dot gap: {gap_bp:+.0f}bp — within normal range (threshold: ±{D1_GAP_BP_THRESHOLD:.0f}bp)."
            ),
            "detail_zh": (
                f"显著背离：市场与点阵图利差{gap_bp:+.0f}个基点（{_safe_get(fed_path, 'gap', 'lean_zh') or ''}）。"
                if active_d1
                else f"市场与点阵图利差：{gap_bp:+.0f}个基点——在正常范围内。"
            ),
        })

    # D2 — projection_vs_breakeven wedge
    # hotter CPI while breakevens down, or cooler CPI while breakevens up
    cpi_tag = None
    for item in release_items:
        if item.get("release_type") in {"cpi_headline", "cpi_core"}:
            cpi_tag = _safe_get(item, "surprise_skew", "tag")
            break

    be_chg_20d = _safe_get(tx, "breakeven_decomp", "velocity_bp", "chg_20d_bp")
    if cpi_tag is None or be_chg_20d is None:
        flags.append({
            "key": "D2_projection_vs_breakeven",
            "active": None,
            "detail_en": "Insufficient data for CPI-breakeven wedge check.",
            "detail_zh": "CPI与盈亏平衡点楔形检查数据不足。",
        })
    else:
        be_chg = float(be_chg_20d)
        # wedge: hot print + falling breakevens; or cool print + rising breakevens
        d2_active = (cpi_tag == "hotter" and be_chg <= -5.0) or \
                    (cpi_tag == "cooler" and be_chg >= 5.0)
        if d2_active:
            if cpi_tag == "hotter" and be_chg <= -5.0:
                detail_en = f"Wedge: near-term CPI skewed hotter but 20d breakeven down {be_chg:.0f}bp — market not believing the print."
                detail_zh = f"楔形：近期CPI偏热但20天盈亏平衡点下降{be_chg:.0f}bp——市场不相信数据。"
            else:
                detail_en = f"Wedge: near-term CPI skewed cooler but 20d breakeven up {be_chg:.0f}bp — market pricing persistent inflation anyway."
                detail_zh = f"楔形：近期CPI偏冷但20天盈亏平衡点上升{be_chg:.0f}bp——市场仍定价持续通胀。"
        else:
            detail_en = f"No projection-breakeven wedge: CPI tag={cpi_tag}, 20d breakeven={be_chg:+.0f}bp."
            detail_zh = f"无预测-盈亏平衡楔形：CPI标签={cpi_tag}，20天盈亏平衡点={be_chg:+.0f}bp。"

        flags.append({
            "key": "D2_projection_vs_breakeven",
            "active": d2_active,
            "detail_en": detail_en,
            "detail_zh": detail_zh,
        })

    # D3 — pressure_vs_market
    implied_bp_12m = _safe_get(fed_path, "implied_bp_12m")
    if implied_bp_12m is None:
        flags.append({
            "key": "D3_pressure_vs_market",
            "active": None,
            "detail_en": "implied_bp_12m unavailable for pressure-vs-market check.",
            "detail_zh": "implied_bp_12m不可用，无法进行压力与市场比较。",
        })
    else:
        ibp = float(implied_bp_12m)
        d3_active = (
            (net_state == "pressure_building" and ibp <= D3_IMPLIED_BP_LOW) or
            (net_state == "pressure_fading" and ibp >= D3_IMPLIED_BP_HIGH)
        )
        flags.append({
            "key": "D3_pressure_vs_market",
            "active": d3_active,
            "detail_en": (
                f"Hawkish pressure building but futures imply {ibp:+.0f}bp over 12m — "
                "market has not priced the pressure yet."
                if net_state == "pressure_building" and ibp <= D3_IMPLIED_BP_LOW else
                f"Easing pressure building but futures imply {ibp:+.0f}bp over 12m — "
                "market still priced for tightening."
                if net_state == "pressure_fading" and ibp >= D3_IMPLIED_BP_HIGH else
                f"Pressure-vs-market gap not active (net_state={net_state}, implied={ibp:+.0f}bp)."
            ),
            "detail_zh": (
                f"鹰派压力积聚但期货12个月隐含{ibp:+.0f}个基点——市场尚未定价该压力。"
                if net_state == "pressure_building" and ibp <= D3_IMPLIED_BP_LOW else
                f"宽松压力积聚但期货12个月隐含{ibp:+.0f}个基点——市场仍定价紧缩。"
                if net_state == "pressure_fading" and ibp >= D3_IMPLIED_BP_HIGH else
                f"压力与市场背离未激活（net_state={net_state}，隐含={ibp:+.0f}bp）。"
            ),
        })

    return flags


def _render_cuts(implied_cuts_12m: int | float | None) -> dict[str, str]:
    """Render implied cuts/hikes as plain words.

    -2 -> 'about two hikes'
    +2 -> 'about two cuts'
     0 -> 'roughly on hold'
    """
    if implied_cuts_12m is None:
        return {"en": "path unclear", "zh": "路径不明"}
    n = float(implied_cuts_12m)
    abs_n = abs(n)
    # Build magnitude word
    if abs_n < 0.5:
        return {"en": "roughly on hold", "zh": "基本按兵不动"}
    count = int(round(abs_n))
    if count == 1:
        count_word_en = "one"
        count_word_zh = "一次"
    elif count == 2:
        count_word_en = "two"
        count_word_zh = "两次"
    elif count == 3:
        count_word_en = "three"
        count_word_zh = "三次"
    else:
        count_word_en = str(count)
        count_word_zh = f"{count}次"

    if n < 0:
        # Negative cuts = hikes
        return {"en": f"about {count_word_en} hike{'s' if count != 1 else ''}", "zh": f"约{count_word_zh}加息"}
    else:
        return {"en": f"about {count_word_en} cut{'s' if count != 1 else ''}", "zh": f"约{count_word_zh}降息"}


def _build_rate_path_row(fed_path: dict) -> dict:
    """Build the rate_path display row."""
    implied = fed_path.get("implied") or {}
    dots = fed_path.get("dots") or []
    gap = fed_path.get("gap") or {}
    implied_cuts_12m = fed_path.get("implied_cuts_12m")
    implied_bp_12m = fed_path.get("implied_bp_12m")
    path_read = _render_cuts(implied_cuts_12m)

    return {
        "asof": fed_path.get("asof"),
        "policy_rate": fed_path.get("policy_rate"),
        "implied_path": {
            "m1": implied.get("m1"),
            "m3": implied.get("m3"),
            "m6": implied.get("m6"),
            "m12": implied.get("m12"),
        },
        "implied_bp_12m": implied_bp_12m,
        "implied_cuts_12m": implied_cuts_12m,
        "path_plain": path_read,
        "dots": dots,
        "gap": gap,
        "headline_en": fed_path.get("headline_en"),
        "headline_zh": fed_path.get("headline_zh"),
        "read_en": fed_path.get("read_en"),
        "read_zh": fed_path.get("read_zh"),
        "source_en": fed_path.get("implied_source_en", "ZQ fed-funds futures"),
        "source_zh": fed_path.get("implied_source_zh", "ZQ联邦基金期货"),
    }


def _build_inflation_row(tx: dict, release_items: list[dict]) -> dict:
    """Build the inflation display row."""
    infl = (_safe_get(tx, "state", "inflation") or {})
    exp = (_safe_get(tx, "state", "expectations") or {})

    # Nearest CPI projection data
    cpi_proj = None
    for item in release_items:
        if item.get("release_type") in {"cpi_headline", "cpi_core"}:
            cpi_proj = {
                "release_type": item.get("release_type"),
                "period": item.get("period"),
                "release_date": item.get("release_date"),
                "days_to": item.get("days_to"),
                "point": _safe_get(item, "projection", "point"),
                "surprise_skew_tag": _safe_get(item, "surprise_skew", "tag"),
                "surprise_skew_sigma": _safe_get(item, "surprise_skew", "sigma"),
            }
            break

    return {
        "core_pce_yoy": infl.get("core_pce_yoy"),
        "core_cpi_yoy": infl.get("core_cpi_yoy"),
        "core_pce_3m_ann": infl.get("core_pce_3m_ann"),
        "vs_target_pp": infl.get("vs_target_pp"),
        "regime": infl.get("regime"),
        "direction": infl.get("direction"),
        "breakeven_10y": exp.get("breakeven_10y"),
        "breakeven_5y5y": exp.get("breakeven_5y5y"),
        "anchoring": exp.get("anchoring"),
        "nearest_cpi": cpi_proj,
    }


def _build_risk_row(tx: dict) -> dict:
    """Build the risk display row.

    Honest label: real_speed_pctile MUST print 'flags risk, not return'.
    Term premium: Kim-Wright model (FRED THREEFYTP10); ACM pending.
    """
    yc = tx.get("yield_curve") or {}
    regime = (yc.get("regime") or {}) if isinstance(yc, dict) else {}
    momentum = (yc.get("momentum") or {}) if isinstance(yc, dict) else {}
    recession = (yc.get("recession") or {}) if isinstance(yc, dict) else {}

    real_speed_pctile = momentum.get("real_speed_pctile")
    curve_key = regime.get("key")
    term_premium_dir = regime.get("term_premium_dir")
    term_premium_chg_bp = regime.get("term_premium_chg_bp")

    # Look for Kim-Wright term premium from transmission state
    # THREEFYTP10 is stored as term_premium_10y in the parquet store;
    # yield_curve.regime.term_premium_dir reflects the direction
    term_premium_note_en = "Kim-Wright model (FRED THREEFYTP10); ACM pending"
    term_premium_note_zh = "Kim-Wright模型（FRED THREEFYTP10）；ACM待接入"

    return {
        "real_speed_pctile": real_speed_pctile,
        "real_speed_note_en": "Flags risk, not return — high percentile = fast real-rate moves, not directional signal.",
        "real_speed_note_zh": "标记风险而非收益——高百分位表示实际利率快速波动，并非方向性信号。",
        "curve_regime_key": curve_key,
        "curve_regime_label_en": regime.get("label", {}).get("en") if isinstance(regime.get("label"), dict) else curve_key,
        "curve_regime_label_zh": _CURVE_REGIME_ZH.get(curve_key or "", curve_key or ""),
        "term_premium_dir": term_premium_dir,
        "term_premium_chg_bp": term_premium_chg_bp,
        "term_premium_note_en": term_premium_note_en,
        "term_premium_note_zh": term_premium_note_zh,
        "front2y_speed_bp": momentum.get("front2y_speed_bp"),
        "real10y_speed_bp": momentum.get("real10y_speed_bp"),
        "recession_ntfs": recession.get("ntfs"),
        "nyfed_prob": recession.get("nyfed_prob"),
    }


def _build_policy_row(
    policy_lever: dict | None,
    intel: dict | None,
    intel_staleness_days: int | None,
) -> dict:
    """Build the policy conditions row."""
    fed_intel = (intel.get("fed") or {}) if intel else {}
    chair = fed_intel.get("chair", "")
    profile_en = (fed_intel.get("profile") or {}).get("en", "") if isinstance(fed_intel.get("profile"), dict) else str(fed_intel.get("profile") or "")
    optionality_en = (fed_intel.get("optionality_read") or {}).get("en", "") if isinstance(fed_intel.get("optionality_read"), dict) else ""

    # th_iran theater
    iran_row = None
    if intel:
        theaters = (intel.get("administration") or {}).get("theaters") or []
        for t in theaters:
            if t.get("id") == "th_iran":
                iran_row = {
                    "title_en": t.get("title_en"),
                    "title_zh": t.get("title_zh"),
                    "facts_en": t.get("facts_en"),
                    "facts_zh": t.get("facts_zh"),
                    "as_of_note_en": (
                        f"Intel as of {intel.get('as_of', '?')} "
                        f"({intel_staleness_days}d old)" if intel_staleness_days is not None
                        else f"Intel as of {intel.get('as_of', '?')}"
                    ),
                    "as_of_note_zh": (
                        f"情报截至{intel.get('as_of', '?')}"
                        f"（{intel_staleness_days}天前）" if intel_staleness_days is not None
                        else f"情报截至{intel.get('as_of', '?')}"
                    ),
                    "unsigned_display": True,
                }
                break

    return {
        "state": (policy_lever.get("state") if policy_lever else None),
        "jawboning": (policy_lever.get("jawboning") if policy_lever else None),
        "lever_asof": (policy_lever.get("as_of") if policy_lever else None),
        "chair": chair,
        "chair_profile_en": profile_en[:400] + "…" if len(profile_en) > 400 else profile_en,
        "chair_profile_zh": "",  # profile is EN-only in the intel artifact
        "optionality_read_en": optionality_en,
        "intel_as_of": (intel.get("as_of") if intel else None),
        "intel_staleness_days": intel_staleness_days,
        "iran_context": iran_row,
    }


def _pick_conditions(
    hawkish_legs: list[dict],
    easing_legs: list[dict],
    iran_row: dict | None,
) -> list[dict]:
    """Pick 2-3 conditions rows deterministically.

    Rule: top active hawkish leg by weight, then top active easing leg, then
    geopolitical row if th_iran present.
    """
    conditions: list[dict] = []

    # Top active hawkish leg by weight desc
    active_h = [l for l in hawkish_legs if l.get("active") is True]
    if active_h:
        top_h = max(active_h, key=lambda l: l.get("weight", 0))
        conditions.append({
            "key": top_h["key"],
            "direction": "hawkish",
            "en": top_h.get("detail_en", ""),
            "zh": top_h.get("detail_zh", ""),
            "watch_en": (
                "If this pressure persists, upward rate repricing stays at risk; "
                "a deepening equity correction historically pulls the other way."
            ),
            "watch_zh": (
                "若该压力持续，利率上调风险上升；"
                "股市进一步下跌历史上会起到反向对冲作用。"
            ),
        })

    # Top active easing leg by weight desc
    active_e = [l for l in easing_legs if l.get("active") is True]
    if active_e:
        top_e = max(active_e, key=lambda l: l.get("weight", 0))
        conditions.append({
            "key": top_e["key"],
            "direction": "easing",
            "en": top_e.get("detail_en", ""),
            "zh": top_e.get("detail_zh", ""),
            "watch_en": (
                "If this offset fades, the hawkish legs would have less counterweight — "
                "watch the tape for repricing."
            ),
            "watch_zh": (
                "若该对冲因素消退，鹰派腿将减少制衡——"
                "关注市场定价变化。"
            ),
        })

    # Geopolitical row if iran present
    if iran_row:
        conditions.append({
            "key": "geo_iran",
            "direction": "geopolitical",
            "en": iran_row.get("title_en", ""),
            "zh": iran_row.get("title_zh", ""),
            "watch_en": (
                "Conditions-only: oil market conditions may shift if the theater escalates "
                "or de-escalates — unsigned, no probability assigned."
            ),
            "watch_zh": (
                "条件性观察：若局势升级或缓和，油市条件可能变化——"
                "无定向，不赋予概率。"
            ),
        })

    return conditions


def _build_market_check(
    fed_path: dict,
    pm_snapshot: dict | None,
) -> dict:
    """Build the market_check display block (juxtaposition only, never fused)."""
    implied = fed_path.get("implied") or {}
    implied_bp_12m = fed_path.get("implied_bp_12m")
    headline_en = fed_path.get("headline_en", "")
    headline_zh = fed_path.get("headline_zh", "")

    futures_block = {
        "m1": implied.get("m1"),
        "m3": implied.get("m3"),
        "m6": implied.get("m6"),
        "m12": implied.get("m12"),
        "implied_bp_12m": implied_bp_12m,
        "plain_read_en": headline_en,
        "plain_read_zh": headline_zh,
    }

    pm_block = None
    if pm_snapshot and pm_snapshot.get("events"):
        events_out = []
        for ev in pm_snapshot["events"][:3]:
            top = ev.get("top") or {}
            events_out.append({
                "key": ev.get("key"),
                "label_en": ev.get("label_en"),
                "label_zh": ev.get("label_zh"),
                "top_outcome": top.get("outcome"),
                "top_prob": top.get("prob"),
                "chg_pp": top.get("chg_pp"),
                "source": "Polymarket",
                "type": "market_implied_benchmark",
            })
        pm_block = {
            "as_of": pm_snapshot.get("asof"),
            "source": "Polymarket",
            "events": events_out,
        }

    return {
        "futures": futures_block,
        "prediction_markets": pm_block,
        "benchmark_note_en": "What markets price — a benchmark, not our read.",
        "benchmark_note_zh": "市场定价内容——作为参考基准，不代表本系统观点。",
    }


def compose_stance(board: dict) -> dict[str, str]:
    """Deterministic template stance sentence from board contents.

    <= 2 sentences, plain words, numbers with interpretation.
    Never intent, never probability.
    """
    try:
        ep = board.get("expectations_pressure") or {}
        net_state = ep.get("net_state", "two_sided")
        hawk_score = ep.get("hawk_score", 0)
        ease_score = ep.get("ease_score", 0)
        legs = ep.get("legs") or []

        # Build context phrases from active legs
        rate_path_row = board.get("board", {}).get("rate_path_row") or {}
        implied_bp_12m = rate_path_row.get("implied_bp_12m") or 0
        path_plain_en = (rate_path_row.get("path_plain") or {}).get("en", "roughly on hold")
        path_plain_zh = (rate_path_row.get("path_plain") or {}).get("zh", "基本按兵不动")
        net = hawk_score - ease_score

        # Build top active leg descriptions
        active_h_legs = [l for l in legs if l.get("active") is True and l.get("key", "").startswith("H")]
        active_e_legs = [l for l in legs if l.get("active") is True and l.get("key", "").startswith("E")]

        top_h_key = active_h_legs[0]["key"] if active_h_legs else None
        top_e_key = active_e_legs[0]["key"] if active_e_legs else None

        # Hawkish driver phrase
        h_phrase_en = ""
        h_phrase_zh = ""
        # Noun phrases only — branch templates below supply the predicates.
        if top_h_key == "H1_path_repricing":
            h_phrase_en = "front-end futures repricing"
            h_phrase_zh = "期货利率重新定价"
        elif top_h_key == "H3_oil_impulse":
            h_phrase_en = "hot oil"
            h_phrase_zh = "原油走高"
        elif top_h_key == "H4_inflation_trajectory":
            h_phrase_en = "a hotter-than-expected inflation print"
            h_phrase_zh = "高于预期的通胀数据"
        elif top_h_key == "H5_curve_regime":
            h_phrase_en = "long rates rising on term premium"
            h_phrase_zh = "期限溢价推动长端利率上行"
        elif top_h_key:
            h_phrase_en = "hawkish inputs"
            h_phrase_zh = "鹰派因素"

        # Easing offset noun phrase
        e_phrase_en = ""
        e_phrase_zh = ""
        if top_e_key == "E1_equity_deleveraging":
            e_phrase_en = "a deeper equity pullback"
            e_phrase_zh = "股市进一步回调"
        elif top_e_key == "E3_dollar_tightening":
            e_phrase_en = "dollar strength"
            e_phrase_zh = "美元走强"
        elif top_e_key:
            e_phrase_en = "easing inputs"
            e_phrase_zh = "宽松因素"

        # Build sentence based on net_state (phrases above are noun phrases)
        if net_state == "repricing_hawkish":
            s1_en = f"Futures now price {path_plain_en} over the next year — hawkish repricing is underway."
            s1_zh = f"期货目前为未来一年定价{path_plain_zh}——加息定价正在进行。"
            if h_phrase_en and e_phrase_en:
                s2_en = f"{h_phrase_en.capitalize()} is the main pressure; {e_phrase_en} is the offset to watch."
                s2_zh = f"{h_phrase_zh}是主要压力；{e_phrase_zh}是需要关注的对冲。"
            elif h_phrase_en:
                s2_en = f"{h_phrase_en.capitalize()} is the main pressure."
                s2_zh = f"{h_phrase_zh}是主要压力。"
            else:
                s2_en = s2_zh = ""
        elif net_state == "pressure_building":
            s1_en = f"Hawkish pressure is building ({hawk_score:.0f} hawkish vs {ease_score:.0f} easing inputs) — the market has not moved yet ({path_plain_en} priced)."
            s1_zh = f"鹰派压力正在积聚（{hawk_score:.0f}项鹰派对{ease_score:.0f}项宽松）——市场尚未行动（当前定价{path_plain_zh}）。"
            s2_en = f"{h_phrase_en.capitalize()} is the pressure; {e_phrase_en} is the offset to watch." if h_phrase_en and e_phrase_en else (f"{h_phrase_en.capitalize()} is the pressure." if h_phrase_en else "")
            s2_zh = f"{h_phrase_zh}构成压力；{e_phrase_zh}是需要关注的对冲。" if h_phrase_zh and e_phrase_zh else (f"{h_phrase_zh}构成压力。" if h_phrase_zh else "")
        elif net_state == "repricing_dovish":
            s1_en = f"Futures now price {path_plain_en} over the next year — dovish repricing is underway."
            s1_zh = f"期货目前为未来一年定价{path_plain_zh}——降息定价正在进行。"
            s2_en = f"{e_phrase_en.capitalize()} is driving the move." if e_phrase_en else ""
            s2_zh = f"{e_phrase_zh}是主要驱动。" if e_phrase_zh else ""
        elif net_state == "pressure_fading":
            s1_en = f"Easing pressure is building — futures still price {path_plain_en}."
            s1_zh = f"宽松压力积聚——期货仍定价{path_plain_zh}。"
            s2_en = f"{e_phrase_en.capitalize()} is the main offset." if e_phrase_en else ""
            s2_zh = f"{e_phrase_zh}是主要对冲。" if e_phrase_zh else ""
        else:  # two_sided
            s1_en = f"Outlook is two-sided: futures price {path_plain_en}; hawkish and easing inputs are roughly balanced ({hawk_score:.0f} vs {ease_score:.0f})."
            s1_zh = f"前景双向：期货定价{path_plain_zh}；鹰派与宽松因素大体制衡（{hawk_score:.0f}对{ease_score:.0f}）。"
            if h_phrase_en and e_phrase_en:
                s2_en = f"{h_phrase_en.capitalize()} and {e_phrase_en} are pulling against each other."
                s2_zh = f"{h_phrase_zh}与{e_phrase_zh}相互制衡。"
            elif h_phrase_en:
                s2_en = f"{h_phrase_en.capitalize()} is the pressure; no clear offset yet."
                s2_zh = f"{h_phrase_zh}构成压力；暂无明确对冲。"
            else:
                s2_en = "Watch the tape — no dominant pressure yet."
                s2_zh = "观察市场走势——暂无主导压力。"

        en = (s1_en + " " + s2_en).strip()
        zh = (s1_zh + " " + s2_zh).strip()
        return {"en": en, "zh": zh}
    except Exception as exc:
        log.warning("compose_stance failed: %s", exc)
        return {
            "en": "Rate-path and inflation pressure summary unavailable.",
            "zh": "利率路径与通胀压力摘要不可用。",
        }


# ---------------------------------------------------------------------------
# Main build_board function
# ---------------------------------------------------------------------------

def build_board(root=None) -> dict:
    """Build the full rates_command.v1 artifact.

    Fails open everywhere: absent/corrupt input -> leg active=None, never raises.
    Returns a complete dict with display_only=True, authority=False.
    """
    data_dir = _data_root(root)
    caveats: list[str] = [
        "futures-implied path reflects risk premium not stripped — not a forecast",
        "All legs are display-tier context only; no scoring or authority.",
    ]

    # ------------------------------------------------------------------ #
    # 1. Load all input artifacts (fail-open)
    # ------------------------------------------------------------------ #

    # bond_health.json -> fed_path
    bond_health = _read_json(data_dir / "bonds" / "bond_health.json") or {}
    fed_path = bond_health.get("fed_path") or {}
    main_asof = fed_path.get("asof") or bond_health.get("as_of") or ""

    if not fed_path:
        caveats.append("bond_health.json / fed_path absent — rate path row will be empty")
        log.warning("build_board: bond_health.json fed_path absent")

    # transmission/latest.json
    tx = _read_json(data_dir / "transmission" / "latest.json") or {}
    tx_asof = tx.get("asof") or ""
    if not tx:
        caveats.append("transmission/latest.json absent — many legs will be null")

    # zq_path.parquet -> H1 d20
    zq_d20_bp: float | None = None
    try:
        import pandas as pd
        zq_path = data_dir / "rate_futures" / "zq_path.parquet"
        if zq_path.exists():
            zq_df = pd.read_parquet(str(zq_path))
            if "m12" in zq_df.columns:
                m12 = zq_df["m12"].dropna()
                if len(m12) >= 20:
                    delta = m12.iloc[-1] - m12.iloc[-20]
                    zq_d20_bp = round(float(delta) * 100, 2)
    except Exception as exc:
        caveats.append(f"zq_path.parquet unavailable: {exc}")
        log.warning("build_board: zq_path.parquet error: %s", exc)

    # release_forecast/latest.json
    release_latest = _read_json(data_dir / "release_forecast" / "latest.json") or {}
    release_items = release_latest.get("upcoming") or []

    # market_state/latest.json
    market_state = _read_json(data_dir / "market_state" / "latest.json") or {}
    radar_state = _safe_get(market_state, "radar", "state")

    # commodity/latest.json, shock_state.json, complex_latest.json
    commodity = _read_json(data_dir / "commodity" / "latest.json") or {}
    oil_asset = (commodity.get("assets") or {}).get("oil") or {}
    oil_trend = oil_asset.get("trend")
    oil_chg = oil_asset.get("chg")

    shock_state_raw = _read_json(data_dir / "commodity" / "shock_state.json") or {}
    shock_oil_raw = shock_state_raw.get("oil") or {}
    shock_oil_ts = shock_oil_raw.get("ts") or shock_oil_raw.get("last_eval")
    shock_stale_days = _staleness_days(shock_oil_ts)
    shock_stale = shock_stale_days is not None and shock_stale_days > SHOCK_STALE_DAYS

    if shock_stale:
        caveats.append(f"commodity/shock_state.json oil entry is {shock_stale_days}d old (>{SHOCK_STALE_DAYS}d threshold) — H3 leg judged on trend+cause_badge only")
    if shock_stale_days is not None:
        shock_oil_raw["_stale_days"] = shock_stale_days

    # Inject oil data into shock_oil_raw for H3 leg builder
    shock_oil_aug = dict(shock_oil_raw)
    shock_oil_aug["_oil_trend"] = oil_trend
    shock_oil_aug["_oil_chg"] = oil_chg

    complex_d = _read_json(data_dir / "commodity" / "complex_latest.json") or {}
    complex_growth_dir = complex_d.get("growth_dir")

    # policy/intel.json
    intel = _read_json(data_dir / "policy" / "intel.json") or {}
    intel_stale_days = _intel_staleness_days(intel) if intel else None
    if intel_stale_days is not None:
        caveats.append(f"policy/intel.json is {intel_stale_days}d old — policy row quotes as-of {intel.get('as_of','?')}")

    # site/policy_lever.json
    policy_lever = _read_json(data_dir.parent / "site" / "policy_lever.json") or \
                   _read_json(data_dir / "policy_lever.json")

    # prediction_markets
    pm_snapshot: dict | None = None
    try:
        import sys
        repo_root = str(Path(__file__).resolve().parent.parent)
        if repo_root not in sys.path:
            sys.path.insert(0, repo_root)
        from engine.prediction_markets import snapshot as pm_snapshot_fn
        pm_snapshot = pm_snapshot_fn()
    except Exception as exc:
        log.warning("prediction_markets.snapshot() failed: %s", exc)
        caveats.append(f"prediction_markets unavailable: {exc}")

    # Inject radar_state into tx so leg builders can access it
    tx["_radar_state"] = radar_state

    # ------------------------------------------------------------------ #
    # 2. Build expectation pressure gauge legs
    # ------------------------------------------------------------------ #
    chains = tx.get("chains") or []
    hawkish_legs = _build_hawkish_legs(
        fed_path=fed_path,
        tx=tx,
        zq_d20_bp=zq_d20_bp,
        release_items=release_items,
        shock_state_oil=shock_oil_aug,
        shock_stale=shock_stale,
    )
    easing_legs = _build_easing_legs(
        tx=tx,
        release_items=release_items,
        complex_growth_dir=complex_growth_dir,
        chains=chains,
    )

    all_legs = hawkish_legs + easing_legs

    # Compute scores (null legs contribute 0)
    hawk_score = sum(
        l["weight"] for l in hawkish_legs
        if l.get("active") is True
    )
    ease_score = sum(
        l["weight"] for l in easing_legs
        if l.get("active") is True
    )

    # Net state
    h1_leg = next((l for l in hawkish_legs if l["key"] == "H1_path_repricing"), None)
    h1_active = h1_leg["active"] if h1_leg else None
    net_state = _compute_net_state(
        hawk_score=hawk_score,
        ease_score=ease_score,
        zq_d20_bp=zq_d20_bp,
        h1_active=h1_active,
    )
    state_label = _NET_STATE_LABELS.get(net_state, {"en": net_state, "zh": net_state})

    # ------------------------------------------------------------------ #
    # 3. Divergence flags
    # ------------------------------------------------------------------ #
    divergence = _compute_divergence(
        fed_path=fed_path,
        release_items=release_items,
        tx=tx,
        net_state=net_state,
    )

    # ------------------------------------------------------------------ #
    # 4. Board rows
    # ------------------------------------------------------------------ #
    iran_row = None
    for t in (intel.get("administration") or {}).get("theaters") or []:
        if t.get("id") == "th_iran":
            iran_row = {"title_en": t.get("title_en"), "title_zh": t.get("title_zh"),
                        "facts_en": t.get("facts_en")}
            break

    board = {
        "rate_path_row": _build_rate_path_row(fed_path),
        "inflation_row": _build_inflation_row(tx, release_items),
        "risk_row": _build_risk_row(tx),
        "policy_row": _build_policy_row(policy_lever, intel, intel_stale_days),
    }

    # ------------------------------------------------------------------ #
    # 5. Conditions block
    # ------------------------------------------------------------------ #
    conditions = _pick_conditions(hawkish_legs, easing_legs, iran_row)

    # ------------------------------------------------------------------ #
    # 6. Market check block
    # ------------------------------------------------------------------ #
    market_check = _build_market_check(fed_path, pm_snapshot)

    # ------------------------------------------------------------------ #
    # 7. Determine asof (newest input)
    # ------------------------------------------------------------------ #
    candidate_dates = [d for d in [main_asof, tx_asof] if d]
    asof = max(candidate_dates) if candidate_dates else str(datetime.now(timezone.utc).date())

    # Build the pre-stance artifact (needed by compose_stance)
    pre_artifact = {
        "schema": "rates_command.v1",
        "asof": asof,
        "built": datetime.now(timezone.utc).isoformat(),
        "display_only": True,
        "authority": False,
        "board": board,
        "expectations_pressure": {
            "legs": all_legs,
            "hawk_score": hawk_score,
            "ease_score": ease_score,
            "net_state": net_state,
            "state_label": state_label,
        },
        "divergence": divergence,
        "conditions": conditions,
        "market_check": market_check,
        "caveats": caveats,
    }

    # Stance sentence
    stance = compose_stance(pre_artifact)

    # Final artifact
    artifact = dict(pre_artifact)
    artifact["stance"] = stance
    # changes + prev_state are added by the builder (build_changes call)
    artifact["changes"] = {"vs_asof": None, "items": []}
    artifact["prev_state"] = {"as_of": None, "state": {}}

    return artifact


# ---------------------------------------------------------------------------
# compact_state, diff_changes, build_changes
# ---------------------------------------------------------------------------

def compact_state(contract: dict) -> dict:
    """Extract a comparable fingerprint from a rates_command artifact."""
    ep = contract.get("expectations_pressure") or {}
    return {
        "net_state": ep.get("net_state"),
        "hawk_score": ep.get("hawk_score"),
        "ease_score": ep.get("ease_score"),
        "curve_regime": _safe_get(contract, "board", "risk_row", "curve_regime_key"),
        "anchoring": _safe_get(contract, "board", "inflation_row", "anchoring"),
        "infl_dir": _safe_get(contract, "board", "inflation_row", "direction"),
        "usd_dir": _safe_get(contract, "board", "policy_row"),  # not in policy_row; get from tx channel
        "implied_bp_12m": _safe_get(contract, "board", "rate_path_row", "implied_bp_12m"),
    }


def _compact_sentence(key: str, old_val, new_val) -> tuple[str, str]:
    if key == "net_state":
        old_lbl = _NET_STATE_LABELS.get(old_val or "", {}).get("en", old_val or "—")
        new_lbl = _NET_STATE_LABELS.get(new_val or "", {}).get("en", new_val or "—")
        return (f"Pressure state changed: {old_lbl} → {new_lbl}",
                f"压力状态变化：{_NET_STATE_LABELS.get(old_val or '', {}).get('zh', old_val or '—')} → "
                f"{_NET_STATE_LABELS.get(new_val or '', {}).get('zh', new_val or '—')}")
    if key == "curve_regime":
        oe = old_val or "—"; ne = new_val or "—"
        oz = _CURVE_REGIME_ZH.get(old_val or "", old_val or "—")
        nz = _CURVE_REGIME_ZH.get(new_val or "", new_val or "—")
        return (f"Curve regime: {oe} → {ne}", f"曲线形态：{oz} → {nz}")
    if key == "anchoring":
        oz = _ANCHORING_LABEL_ZH.get(old_val or "", old_val or "—")
        nz = _ANCHORING_LABEL_ZH.get(new_val or "", new_val or "—")
        return (f"Anchoring: {old_val or '—'} → {new_val or '—'}",
                f"锚定状态：{oz} → {nz}")
    if key == "infl_dir":
        oz = _INFL_DIR_ZH.get(old_val or "", old_val or "—")
        nz = _INFL_DIR_ZH.get(new_val or "", new_val or "—")
        return (f"Inflation direction: {old_val or '—'} → {new_val or '—'}",
                f"通胀方向：{oz} → {nz}")
    if key == "implied_bp_12m":
        return (f"12m implied change shifted: {old_val:+.0f}bp → {new_val:+.0f}bp",
                f"12个月隐含变化：{old_val:+.0f}bp → {new_val:+.0f}bp")
    return (f"{key} changed: {old_val} → {new_val}", f"{key}变化：{old_val} → {new_val}")


def diff_changes(prev: dict, curr: dict) -> list[dict]:
    """Compare two compact_state dicts; emit at most 6 change items."""
    candidates: list[tuple[int, dict]] = []

    for key in _DIFF_ORDER:
        old_val = prev.get(key)
        new_val = curr.get(key)
        if old_val is None or new_val is None:
            continue
        if old_val == new_val:
            continue
        try:
            en, zh = _compact_sentence(key, old_val, new_val)
        except Exception:
            en = f"{key}: {old_val} → {new_val}"
            zh = en
        idx = _DIFF_ORDER.index(key)
        candidates.append((idx, {"key": key, "from": old_val, "to": new_val, "en": en, "zh": zh}))

    candidates.sort(key=lambda x: x[0])
    return [item for _, item in candidates[:_MAX_CHANGES]]


def build_changes(
    old_contract: dict | None,
    new_contract: dict,
    new_asof: str,
) -> tuple[dict, dict]:
    """Same-day-idempotent changes block builder.

    Mirror of transmission_context.build_changes semantics (lines 507-554).
    """
    if old_contract is None:
        return (
            {"vs_asof": None, "items": []},
            {"as_of": None, "state": {}},
        )

    new_cs = compact_state(new_contract)
    old_asof = old_contract.get("asof")

    if old_asof != new_asof:
        # New day — diff against yesterday
        base = compact_state(old_contract)
        base_asof = old_asof
    else:
        # Same-day rebuild — reuse stored prev_state
        prev_state_stored = old_contract.get("prev_state") or {}
        base = prev_state_stored.get("state") or {}
        base_asof = prev_state_stored.get("as_of")

    if base_asof is None or not base:
        items: list[dict] = []
    else:
        items = diff_changes(base, new_cs)

    changes = {"vs_asof": base_asof, "items": items}
    prev_state = {"as_of": base_asof, "state": base}
    return changes, prev_state
