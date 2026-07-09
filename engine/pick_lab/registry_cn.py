"""China Pick Lab frozen candidate book registry (cnlab_*).

20 books per spec §3 + flagship-2 mirror ledger id (§4, not counted in 20).
Config-hash discipline and frozen-config law identical to registry.py (CNPL-R2).

Kill-adjacency notes included per spec §8 for books 2,3,4,5,8,9,10,12,13,14,16.

Expose CN_REGISTRY (ordered list of 20 books), CN_BY_ID (dict keyed by engine_id),
and FLAGSHIP2_MIRROR_ID (ledger-only id, not in registry count).

CNPL-R2: any parameter change ships as engine_id-v2 with a fresh ledger.
CNPL-R12: no LLM output, all functions deterministic.
"""
from __future__ import annotations

import hashlib
import json


FLAGSHIP2_MIRROR_ID = "cnlab_flagship2_mirror"
"""Ledger id for the flagship-2 daily top-12 mirror (§4, not counted in the 20)."""


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


# ------------------------------------------------------------------ Family A — validated edge (Reversion) ---

_A = [
    _entry(
        engine_id="cnlab_rev_pure",
        name_en="CN Reversion Pure (flat, no gates)",
        name_zh="A股纯反转 (平坦无门)",
        family="A",
        ruler="21d_csi300_excess",
        max_picks=12,
        refire_lockout_sessions=21,
        config={
            # deepest quintile within-sector 3m return (rev_deepest_quintile bool)
            "rev_deepest_quintile": True,
            # flat, NO confirmation/quality/reclaim gates (FALSIFIED)
            "no_confirmation_gate": True,
            "rank_by": "reversal_depth",  # reversal depth = rev_3m_sector_rank ascending (low = deepest)
        },
    ),
    _entry(
        engine_id="cnlab_rev_washout",
        name_en="CN Reversion + Washout",
        name_zh="A股反转+洗盘",
        family="A",
        ruler="21d_csi300_excess",
        max_picks=12,
        refire_lockout_sessions=21,
        config={
            "rev_deepest_quintile": True,
            "washout_2w": True,            # WASHOUT_BONUS: CN-gate-validated
            "rank_by": "reversal_depth",
        },
        kill_adjacency=(
            "Reversal confirmation/quality/reclaim gates FALSIFIED; "
            "washout_2w is a CN-validated BONUS not a turn-confirmation or quality floor — §8"
        ),
    ),
    _entry(
        engine_id="cnlab_rev_coiled",
        name_en="CN Reversion + Coiled/STAR",
        name_zh="A股反转+盘绕/STAR",
        family="A",
        ruler="21d_csi300_excess",
        max_picks=12,
        refire_lockout_sessions=21,
        config={
            "rev_deepest_quintile": True,
            "coiled_or_star": True,        # CN-validated cohort: clean15 +7.33pp n=10,784
            "rank_by": "coiled_bonus_then_depth",
        },
        kill_adjacency=(
            "Reversal confirmation/quality/reclaim gates FALSIFIED; "
            "COILED/STAR is CN-validated bonus (cohort-washout), not turn-confirmation — §8"
        ),
    ),
    _entry(
        engine_id="cnlab_rev_lowvol",
        name_en="CN Reversion + Low Volatility",
        name_zh="A股反转+低波动",
        family="A",
        ruler="21d_csi300_excess",
        max_picks=12,
        refire_lockout_sessions=21,
        config={
            "rev_deepest_quintile": True,
            "lowvol_tercile": "low",       # lowest-vol tercile (validated as sleeve tilt)
            "rank_by": "reversal_depth",
        },
        kill_adjacency=(
            "Reversal confirmation/quality/reclaim gates FALSIFIED; "
            "low-vol is a validated sleeve tilt, not a quality floor — §8"
        ),
    ),
]

# ------------------------------------------------------------------ Family B — 1D velocity, CN-adapted ---

_B = [
    _entry(
        engine_id="cnlab_1d_pure",
        name_en="CN 1D Velocity Pure",
        name_zh="A股1日速度纯",
        family="B",
        ruler="21d_csi300_excess",
        max_picks=12,
        refire_lockout_sessions=21,
        config={
            # 1D RSI-MACD cross-up ≤2 sessions AND 1D StochRSI k×d cross-up ≤8 AND 1D from_os
            "d1_macd_xup_bars_max": 2,
            "d1_kd_xup_bars_max": 8,
            "d1_from_os": True,            # StochRSI d<20 within 8 sessions
            "rsi_10_max": 70,              # rsi_10 < 70 (CN uses rsi_10 not rsi_14)
            "rank_by": "freshness_depth_composite",
        },
        kill_adjacency=(
            "FALS-OSC oscillator covariate family NULL (cycle program); "
            "CN momentum FALSIFIED — these are per-name entry-TIMING constructions, new — §8"
        ),
    ),
    _entry(
        engine_id="cnlab_1d_phase",
        name_en="CN 1D + Cycle Phase",
        name_zh="A股1日+周期阶段",
        family="B",
        ruler="21d_csi300_excess",
        max_picks=12,
        refire_lockout_sessions=21,
        config={
            # book-5 base
            "d1_macd_xup_bars_max": 2,
            "d1_kd_xup_bars_max": 8,
            "d1_from_os": True,
            "rsi_10_max": 70,
            # CNPL-R6: shadow conditioning on constructive cycle phases
            "cycle_phases_allowed": [
                "ACCUMULATION",
                "POLICY_PUT",
                "LIQUIDITY_IGNITION",
                "RECOVERY",
                "REPAIR",
            ],
            "rank_by": "freshness_depth_composite",
        },
    ),
    _entry(
        engine_id="cnlab_1d_participation",
        name_en="CN 1D + Participation Regime",
        name_zh="A股1日+参与制度",
        family="B",
        ruler="21d_csi300_excess",
        max_picks=12,
        refire_lockout_sessions=21,
        config={
            # book-5 base
            "d1_macd_xup_bars_max": 2,
            "d1_kd_xup_bars_max": 8,
            "d1_from_os": True,
            "rsi_10_max": 70,
            # participation regime filter (CNPL-R6 shadow)
            "participation_regimes_allowed": [
                "institutional_accumulation",
                "retail_ignition",
            ],
            "participation_risks_blocked": ["frothy", "fire_sale"],
            "rank_by": "freshness_depth_composite",
        },
    ),
    _entry(
        engine_id="cnlab_1d_blastoff",
        name_en="CN 1D Blastoff (2D/3D gate miss)",
        name_zh="A股1日起飞 (2D/3D门遗漏)",
        family="B",
        ruler="21d_csi300_excess",
        max_picks=12,
        refire_lockout_sessions=21,
        config={
            # 1D MACD cross ≤3 AND 3D MACD not yet crossed AND above_ma120 AND NOT chase_veto
            "d1_macd_xup_bars_max": 3,
            "d3_macd_not_crossed": True,   # 3D MACD has not yet crossed (null = not crossed)
            "above_ma120": True,
            "chase_veto_exclude": True,    # NOT chase_veto
            "rank_by": "d1_relative_strength_5d",
        },
        kill_adjacency=(
            "Limit-up/lianban continuation FALSIFIED as buy; CN-SYS-R3; "
            "chase_veto used as EXCLUSION not signal — §8"
        ),
    ),
]

# ------------------------------------------------------------------ Family C — structure/flow ---

_C = [
    _entry(
        engine_id="cnlab_block_discount",
        name_en="CN Block Discount ≤−15%",
        name_zh="A股大宗折价≤−15%",
        family="C",
        ruler="21d_csi300_excess",
        max_picks=12,
        refire_lockout_sessions=21,
        config={
            # block trade at ≤−15% discount within last 10 sessions (CNPL-R9: store-honest)
            "block_discount_recent": True,
            "block_discount_pct_max": -0.15,  # ≤ −15%
            "block_lookback_sessions": 10,
            "rank_by": "discount_depth",
        },
        kill_adjacency=(
            "Block-trade PREMIUM as accumulation FALSIFIED (wrong sign); "
            "book 9 is the inverted leg (≤−15% DISCOUNT), probationary +3.45%/21d — §8"
        ),
    ),
    _entry(
        engine_id="cnlab_lhb_inst",
        name_en="CN LHB Institutional Seats ≥2",
        name_zh="A股龙虎榜机构席位≥2",
        family="C",
        ruler="21d_csi300_excess",
        max_picks=12,
        refire_lockout_sessions=21,
        config={
            # LHB institutional net-buy ≥2 seats within 5 sessions (CNPL-R9: store-honest)
            "lhb_inst_seats_5d_min": 2,
            "rank_by": "seat_count",
        },
        kill_adjacency=(
            "LHB raw hot-money flag FALSIFIED (wrong sign); "
            "inst-seat ≥2 leg only (the ACCRUING construction) — §8"
        ),
    ),
    _entry(
        engine_id="cnlab_policy_put",
        name_en="CN Policy Put Bottom Fisher",
        name_zh="A股政策托底抄底",
        family="C",
        ruler="21d_csi300_excess",
        max_picks=12,
        refire_lockout_sessions=21,
        config={
            # policy_impulse ∈ {market_rescue, easing} AND dd > 30% from 2y high AND above 20d low
            "policy_impulse_allowed": ["market_rescue", "easing"],
            "dd_pct_2y_min": 30.0,         # drawdown > 30% from 2y high
            "above_20d_low": True,         # price above its own 20d low
            "rank_by": "drawdown_depth",
        },
    ),
    _entry(
        engine_id="cnlab_theme_laggard",
        name_en="CN Theme Laggard Catch-up",
        name_zh="A股主题落后者补涨",
        family="C",
        ruler="21d_csi300_excess",
        max_picks=12,
        refire_lockout_sessions=21,
        config={
            # member of theme basket with breadth ≥80% AND own 21d return bottom half AND NOT chase_veto
            "theme_breadth_pct_min": 80.0,     # basket breadth ≥ 80%
            "theme_member_ret21_rank_max": 50,  # own 21d rank ≤ 50th pct = bottom half of basket
            "chase_veto_exclude": True,
            "rank_by": "breadth_times_laggardness",
        },
        kill_adjacency=(
            "Basket TS-momentum + rank-IC rotation FALSIFIED; low-breadth conditioning FALSIFIED; "
            "book 12 buys the LAGGARD inside a HIGH-BREADTH theme (catch-up, not continuation) — §8"
        ),
    ),
]

# ------------------------------------------------------------------ Family D — washout/panic regimes ---

_D = [
    _entry(
        engine_id="cnlab_capitulation_beta",
        name_en="CN Capitulation Beta (dormant unless market caps)",
        name_zh="A股资本出逃Beta (非市场投降期休眠)",
        family="D",
        ruler="21d_csi300_excess",
        max_picks=12,
        refire_lockout_sessions=21,
        config={
            # book dormant unless cycle_phase ∈ {CAPITULATION, DELEVERAGING}
            "cycle_phases_required": ["CAPITULATION", "DELEVERAGING"],
            # name drawdown > 40% (junk-beats-quality regime)
            "dd_pct_2y_min": 40.0,
            "rank_by": "drawdown_depth",
        },
        kill_adjacency=(
            "SLF-051 margin impulse FAIL/NULL; "
            "phase/QVIX conditioning not margin ROC; direction is reversion into panic — §8"
        ),
    ),
    _entry(
        engine_id="cnlab_qvix_panic",
        name_en="CN QVIX Panic Entry",
        name_zh="A股波动率恐慌入场",
        family="D",
        ruler="21d_csi300_excess",
        max_picks=12,
        refire_lockout_sessions=21,
        config={
            # qvix_z > 2.0 AND name in deepest-dd quintile AND NOT sealed_down at fire
            "qvix_z_min": 2.0,
            "rev_deepest_quintile": True,
            "exclude_sealed_down": True,   # NOT sealed_down at fire time
            "rank_by": "drawdown_depth",
        },
        kill_adjacency=(
            "SLF-051 margin impulse FAIL/NULL; distinct from killed margin direction; "
            "QVIX vol-panic extreme entry, direction is REVERSION into panic — §8"
        ),
    ),
    _entry(
        engine_id="cnlab_star_20cm",
        name_en="CN STAR/ChiNext 20cm 1D Timing",
        name_zh="A股科创/创业20cm 1日择时",
        family="D",
        ruler="21d_csi300_excess",
        max_picks=12,
        refire_lockout_sessions=21,
        config={
            # 688xxx/300xxx boards (±20% limit) only
            "boards_allowed": ["star", "chinext"],
            # book-5 1D confluence
            "d1_macd_xup_bars_max": 2,
            "d1_kd_xup_bars_max": 8,
            "d1_from_os": True,
            "rsi_10_max": 70,
            "above_ma120": True,
            "chase_veto_exclude": True,
            "rank_by": "freshness_depth_composite",
        },
    ),
    _entry(
        engine_id="cnlab_chase_avoid",
        name_en="CN Chase Avoid (INVERSE)",
        name_zh="A股追涨规避 (反向)",
        family="D",
        ruler="21d_csi300_excess_avoid_accuracy",
        max_picks=12,
        refire_lockout_sessions=21,
        config={
            # INVERSE (avoid): chase_veto flagged (sealed_up or 5d run ≥15%)
            # legal AVOID-direction use of limit data (CNPL-R7)
            "chase_veto": True,            # only names with chase_veto == True
            "rank_by": "five_day_run_desc",  # highest 5d run first (highest risk)
            "inverse": True,               # scored as avoid-accuracy (expected NEGATIVE)
        },
        kill_adjacency=(
            "Limit-up/lianban continuation FALSIFIED as BUY; CN-SYS-R3; "
            "book 16 is the INVERSE (avoid) direction — legal per CNPL-R7 — §8"
        ),
    ),
]

# ------------------------------------------------------------------ Family E — defensive + ablations + control ---

_E = [
    _entry(
        engine_id="cnlab_lowvol_defensive",
        name_en="CN Low-Vol Defensive",
        name_zh="A股低波动防御",
        family="E",
        ruler="21d_csi300_excess",
        max_picks=12,
        refire_lockout_sessions=21,
        config={
            # lowest-vol tercile top-12 (validated tilt as standing defensive book)
            "lowvol_tercile": "low",
            "rank_by": "inverse_vol",      # lowest vol first
        },
    ),
    _entry(
        engine_id="cnlab_dividend_ma120",
        name_en="CN Dividend / 中特估 Defensive",
        name_zh="A股分红/中特估防御",
        family="E",
        ruler="21d_csi300_excess",
        max_picks=12,
        refire_lockout_sessions=21,
        config={
            # dividend_defensive archetype AND above_ma120 AND dd < 15%
            "archetype": "dividend_defensive",
            "above_ma120": True,
            "dd_pct_2y_max": 15.0,         # dd < 15%
            "rank_by": "dividend_context",
        },
    ),
    _entry(
        engine_id="cnlab_flagship_nogate",
        name_en="CN Flagship (no US confluence-cascade gate)",
        name_zh="A股旗舰 (无美式汇流门)",
        family="E",
        ruler="21d_csi300_excess",
        max_picks=12,
        refire_lockout_sessions=21,
        config={
            # current CN board composite rank WITHOUT the US confluence-cascade gate
            # (gate-vs-edge divorce ablation)
            "no_confluence_cascade": True,
            "rank_by": "composite",        # CN board composite rank
        },
    ),
    _entry(
        engine_id="cnlab_random_ctrl",
        name_en="CN Random Control",
        name_zh="A股随机基准",
        family="E",
        ruler="21d_csi300_excess",
        max_picks=12,
        refire_lockout_sessions=21,
        config={
            "sample_n": 12,
            "seed_method": "sha256(engine_id+asof)",  # deterministic per CNPL-R12
            "rank_by": "random",
        },
    ),
]

# ------------------------------------------------------------------ Exports ---

CN_REGISTRY: list[dict] = _A + _B + _C + _D + _E
CN_BY_ID: dict[str, dict] = {b["engine_id"]: b for b in CN_REGISTRY}

# Sanity checks at module load
assert len(CN_REGISTRY) == 20, f"Expected 20 CN books, got {len(CN_REGISTRY)}"
assert len({b["config_hash"] for b in CN_REGISTRY}) == 20, "Duplicate config_hash in CN_REGISTRY"
assert FLAGSHIP2_MIRROR_ID not in CN_BY_ID, "flagship2_mirror must not be in the registry count"
