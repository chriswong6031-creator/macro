"""HK Pick Lab frozen candidate book registry (hklab_*).

20 books per spec §3 + flagship-2 mirror ledger id (§4, not counted in 20).
Config-hash discipline and frozen-config law identical to registry.py (HKPL-R2).

Kill-adjacency notes per spec §8 for books 7 (hklab_washout_sb), 15
(hklab_beta_amplifier), and 18 (hklab_flagship_nogate) at minimum; also noted
for 10 (hklab_knife_avoid) and 19 (hklab_chase_avoid) as inverse books.

Expose HK_REGISTRY (ordered list of 20 books), HK_BY_ID (dict keyed by engine_id),
and HK_FLAGSHIP2_MIRROR_ID (ledger-only id, not in registry count).

HKPL-R2: any parameter change ships as engine_id-v2 with a fresh ledger.
Standing kills from spec §8:
  - NO residual/selection momentum ranks (HK KILL)
  - NO southbound delta-ranking (NO-GO; SB_ACCUM organ signal consumption is legal)
  - NO COILED books for HK (do-not-port)
  - NO Connect-inclusion event books
"""
from __future__ import annotations

import hashlib
import json


HK_FLAGSHIP2_MIRROR_ID = "hklab_flagship2_mirror"
"""Ledger id for the flagship-2 (1D Velocity Desk) mirror (§4, not counted in 20)."""


def _config_hash(cfg: dict) -> str:
    """sha256 of canonical sorted-key compact JSON of the config dict."""
    canonical = json.dumps(cfg, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode()).hexdigest()


def _entry(
    engine_id: str,
    name_en: str,
    name_zh: str,
    family: str,
    ruler: str,
    max_picks: int,
    refire_lockout_sessions: int,
    config: dict,
    kill_adjacency: str = "",
    horizon_role: str = "entry",
) -> dict:
    return {
        "engine_id": engine_id,
        "name_en": name_en,
        "name_zh": name_zh,
        "family": family,
        "ruler": ruler,
        "horizon_role": horizon_role,
        "max_picks": max_picks,
        "refire_lockout_sessions": refire_lockout_sessions,
        "config": config,
        "config_hash": _config_hash(config),
        "kill_adjacency": kill_adjacency,
    }


# ------------------------------------------------------------------ Family A — 1D velocity ---

_A = [
    _entry(
        engine_id="hklab_1d_pure",
        name_en="HK 1D Velocity Pure",
        name_zh="港股1日速度纯",
        family="A",
        ruler="21d_hsi_excess",
        max_picks=8,
        refire_lockout_sessions=21,
        config={
            # 1D RSI-MACD cross-up ≤2 sessions AND 1D StochRSI k×d cross ≤8 AND 1D from_os
            "d1_macd_xup_bars_max": 2,
            "d1_stoch_xup_bars_max": 8,
            "d1_from_os": True,
            "rsi14_max": 70,
            "rank_by": "edge_z",
        },
    ),
    _entry(
        engine_id="hklab_1d_ignition",
        name_en="HK 1D + Washout Ignition (organ x 1D)",
        name_zh="港股1日+洗盘点火 (器官x1日)",
        family="A",
        ruler="21d_hsi_excess",
        max_picks=8,
        refire_lockout_sessions=21,
        config={
            # 1D MACD cross ≤3 AND washout_state in {ignition_watch, pullback_entry_watch}
            "d1_macd_xup_bars_max": 3,
            "washout_states_allowed": ["ignition_watch", "pullback_entry_watch"],
            "rank_by": "confluence_count",
        },
    ),
    _entry(
        engine_id="hklab_1d_adr",
        name_en="HK 1D + ADR Overnight Confirmation",
        name_zh="港股1日+ADR隔夜确认",
        family="A",
        ruler="21d_hsi_excess",
        max_picks=8,
        refire_lockout_sessions=21,
        config={
            # 1D MACD cross ≤2 AND ADR implied_open_gap_pct ≥ +0.5
            "d1_macd_xup_bars_max": 2,
            "adr_gap_pct_min": 0.5,
            "rank_by": "adr_gap_pct",
        },
    ),
    _entry(
        engine_id="hklab_1d_blastoff",
        name_en="HK 1D Blastoff (fast cohort 3D gate misses)",
        name_zh="港股1日起飞 (3日门遗漏的快速群组)",
        family="A",
        ruler="21d_hsi_excess",
        max_picks=8,
        refire_lockout_sessions=21,
        config={
            # 1D MACD cross ≤3 AND 3D MACD NOT yet crossed AND above 200dma
            "d1_macd_xup_bars_max": 3,
            "d3_macd_not_crossed": True,
            "above_200": True,
            "rank_by": "ret_5d",
        },
    ),
    _entry(
        engine_id="hklab_1d_regime",
        name_en="HK 1D + Risk-On Regime",
        name_zh="港股1日+风险偏好开启",
        family="A",
        ruler="21d_hsi_excess",
        max_picks=8,
        refire_lockout_sessions=21,
        config={
            # 1D MACD cross ≤3 AND risk_state = Risk-on AND peg not weak-side pressure
            "d1_macd_xup_bars_max": 3,
            "risk_state_required": "Risk-on",
            "peg_state_blocked": "weak_side_pressure",
            "rank_by": "edge_z",
        },
    ),
]

# ------------------------------------------------------------------ Family B — washout/ignition (organ-integrated) ---

_B = [
    _entry(
        engine_id="hklab_washout_ignite",
        name_en="HK Washout Ignition (strongest organ state)",
        name_zh="港股洗盘点火 (最强器官状态)",
        family="B",
        ruler="21d_hsi_excess",
        max_picks=8,
        refire_lockout_sessions=21,
        config={
            # washout_state = ignition_watch
            "washout_states_allowed": ["ignition_watch"],
            "rank_by": "confluence_count",
        },
    ),
    _entry(
        engine_id="hklab_washout_sb",
        name_en="HK Washout + SB Accum Confluence",
        name_zh="港股洗盘+南向积累汇流",
        family="B",
        ruler="21d_hsi_excess",
        max_picks=8,
        refire_lockout_sessions=21,
        config={
            # washout state ∈ {washout_watch, ignition_watch} AND SB_ACCUM in confluence_signals
            # SB level-turn consumed as organ confluence signal — NOT Δ-ranking of the board
            "washout_states_allowed": ["washout_watch", "ignition_watch"],
            "confluence_signal_required": "SB_ACCUM",
            "rank_by": "sb_accum_z",
        },
        kill_adjacency=(
            "Southbound Δ-ranker NO-GO (H1, lag); SB divergence FALSIFIED; "
            "book 7 consumes the organ SB_ACCUM level-turn confluence signal inside a washout "
            "state — not a Δ-ranking of the board — §8"
        ),
    ),
    _entry(
        engine_id="hklab_washout_buyback",
        name_en="HK Washout + Buyback Confluence",
        name_zh="港股洗盘+回购汇流",
        family="B",
        ruler="21d_hsi_excess",
        max_picks=8,
        refire_lockout_sessions=21,
        config={
            # any washout state AND BUYBACK in confluence_signals
            "any_washout_state": True,
            "confluence_signal_required": "BUYBACK",
            "rank_by": "confluence_count",
        },
    ),
    _entry(
        engine_id="hklab_pullback_entry",
        name_en="HK Pullback Entry Watch (second-chance)",
        name_zh="港股回调入场 (第二次机会)",
        family="B",
        ruler="21d_hsi_excess",
        max_picks=8,
        refire_lockout_sessions=21,
        config={
            # state = pullback_entry_watch (ignited, now re-testing)
            "washout_states_allowed": ["pullback_entry_watch"],
            "rank_by": "rsi14_reclaim_depth",
        },
    ),
    _entry(
        engine_id="hklab_knife_avoid",
        name_en="HK Knife Avoid (INVERSE — expected negative)",
        name_zh="港股刀口规避 (反向 — 预期负超额)",
        family="B",
        ruler="21d_hsi_excess_avoid_accuracy",
        max_picks=8,
        refire_lockout_sessions=21,
        config={
            # INVERSE (avoid): knife_risk = True names
            "knife_risk": True,
            "rank_by": "dd_depth",
            "inverse": True,
        },
    ),
]

# ------------------------------------------------------------------ Family C — HK-unique structure ---

_C = [
    _entry(
        engine_id="hklab_cbbc_fuel",
        name_en="HK CBBC Bear Skew Fuel",
        name_zh="港股CBBC空头偏斜燃料",
        family="C",
        ruler="21d_hsi_excess",
        max_picks=8,
        refire_lockout_sessions=21,
        config={
            # CBBC leverage_state ∈ {bear_skew, bear_skew_froth} AND price > 20dma
            # dense bear call-cluster ABOVE spot = forced-buy fuel (leverage-mechanics)
            "cbbc_states_allowed": ["bear_skew", "bear_skew_froth"],
            "above_20dma": True,
            "rank_by": "bear_skew_ratio",
        },
    ),
    _entry(
        engine_id="hklab_ah_value",
        name_en="HK A/H Discount Value (H3 near-GO edge)",
        name_zh="港股A/H折价价值 (H3接近通过)",
        family="C",
        ruler="21d_hsi_excess",
        max_picks=8,
        refire_lockout_sessions=21,
        config={
            # Top A/H-discount own-history percentile names
            "rank_by": "ah_discount_pctile",
        },
    ),
    _entry(
        engine_id="hklab_short_squeeze",
        name_en="HK Short Squeeze Setup (H2a ACCRUE leg)",
        name_zh="港股轧空形态 (H2a积累腿)",
        family="C",
        ruler="21d_hsi_excess",
        max_picks=8,
        refire_lockout_sessions=21,
        config={
            # SFC short-pressure top quartile AND RSI reclaim through 30-50 band
            "sfc_short_pressure_quartile_min": 3,   # top quartile = Q4 (1-4 scale)
            "rsi14_reclaim_band_lo": 30,
            "rsi14_reclaim_band_hi": 50,
            "rank_by": "sfc_short_pressure_q",
        },
    ),
    _entry(
        engine_id="hklab_catalyst_narrative",
        name_en="HK Catalyst + Narrative Attention",
        name_zh="港股催化剂+叙事关注",
        family="C",
        ruler="21d_hsi_excess",
        max_picks=8,
        refire_lockout_sessions=21,
        config={
            # catalyst within 5 sessions AND attention_shock_z ≥ 1.5 AND tone ≥ 55 AND rsi14 < 70
            "catalyst_days_to_max": 5,
            "attention_shock_z_min": 1.5,
            "narrative_tone_min": 55,
            "rsi14_max": 70,
            "rank_by": "attention_shock_z",
        },
    ),
]

# ------------------------------------------------------------------ Family D — beta/regime ---

_D = [
    _entry(
        engine_id="hklab_beta_amplifier",
        name_en="HK Beta Amplifier (Risk-On)",
        name_zh="港股Beta放大器 (风险偏好开启)",
        family="D",
        ruler="21d_hsi_excess",
        max_picks=8,
        refire_lockout_sessions=21,
        config={
            # risk_state = Risk-on AND beta role = amplifier AND above 200dma
            "risk_state_required": "Risk-on",
            "beta_role_required": "amplifier",
            "above_200": True,
            "rank_by": "beta",
        },
        kill_adjacency=(
            "HK residual/selection momentum KILL (DSR/IC); "
            "rank key is beta-role (amplifier) — per-name measured beta relationship — "
            "not a momentum factor; gate requires role=amplifier AND risk_state=Risk-on — §8"
        ),
    ),
    _entry(
        engine_id="hklab_beta_cushion",
        name_en="HK Beta Cushion (Risk-Off Defensive)",
        name_zh="港股Beta缓冲 (防御型)",
        family="D",
        ruler="21d_hsi_excess",
        max_picks=8,
        refire_lockout_sessions=21,
        config={
            # risk_state = Risk-off AND beta role = cushion
            "risk_state_required": "Risk-off",
            "beta_role_required": "cushion",
            "rank_by": "inverse_beta",
        },
    ),
    _entry(
        engine_id="hklab_hibor_easy",
        name_en="HK HIBOR/Peg Easy Liquidity Rebound",
        name_zh="港股HIBOR/联系汇率宽松流动性反弹",
        family="D",
        ruler="21d_hsi_excess",
        max_picks=8,
        refire_lockout_sessions=21,
        config={
            # liquidity_regime = EASY AND washout_2w (liquidity-cushioned rebound thesis)
            "liquidity_regime_required": "EASY",
            "washout_2w": True,
            "rank_by": "washout_depth",
        },
    ),
]

# ------------------------------------------------------------------ Family E — ablations + controls ---

_E = [
    _entry(
        engine_id="hklab_flagship_nogate",
        name_en="HK Flagship (no signal-gate ablation)",
        name_zh="港股旗舰 (无信号门消融)",
        family="E",
        ruler="21d_hsi_excess",
        max_picks=8,
        refire_lockout_sessions=21,
        config={
            # Top-8 by edge_z IGNORING the signal_gate entry-open/setting-up grouping
            "ignore_signal_gate": True,
            "rank_by": "edge_z",
        },
        kill_adjacency=(
            "HK residual/selection momentum KILL (DSR/IC); "
            "rank key is edge_z — the board's own fused edge blend (A/H + context legs) — "
            "not a momentum factor; gate-ablation construction tests the gating effect — §8"
        ),
    ),
    _entry(
        engine_id="hklab_chase_avoid",
        name_en="HK Chase Avoid (INVERSE — chase_risk state)",
        name_zh="港股追涨规避 (反向 — 追涨风险状态)",
        family="E",
        ruler="21d_hsi_excess_avoid_accuracy",
        max_picks=8,
        refire_lockout_sessions=21,
        config={
            # INVERSE (avoid): washout_state = chase_risk (RSI ≥ 70 gapped names)
            "washout_states_required": ["chase_risk"],
            "rank_by": "rsi14_desc",
            "inverse": True,
        },
    ),
    _entry(
        engine_id="hklab_random_ctrl",
        name_en="HK Random Control",
        name_zh="港股随机基准",
        family="E",
        ruler="21d_hsi_excess",
        max_picks=8,
        refire_lockout_sessions=21,
        config={
            "sample_n": 8,
            "seed_method": "sha256(engine_id+asof)",  # deterministic (HKPL-R2 reproducibility)
            "rank_by": "random",
        },
    ),
]

# ------------------------------------------------------------------ Exports ---

HK_REGISTRY: list[dict] = _A + _B + _C + _D + _E
HK_BY_ID: dict[str, dict] = {b["engine_id"]: b for b in HK_REGISTRY}

# Sanity checks at module load
assert len(HK_REGISTRY) == 20, f"Expected 20 HK books, got {len(HK_REGISTRY)}"
assert len({b["config_hash"] for b in HK_REGISTRY}) == 20, "Duplicate config_hash in HK_REGISTRY"
assert HK_FLAGSHIP2_MIRROR_ID not in HK_BY_ID, "flagship2_mirror must not be in the registry count"
