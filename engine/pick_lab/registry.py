"""Pick Lab frozen candidate book registry.

23 frozen book definitions: 20 entry books (plab_*) + 3 long-hold grids
(plab_lh_*) per spec §3.

Each entry:
  engine_id              : canonical identifier, never changes
  name_en / name_zh      : display names (bilingual)
  family                 : family label (A–F or LH)
  ruler                  : primary measurement ruler per PL-R3
  horizon_role           : 'entry' | 'hold_thesis'
  max_picks              : 12 (entry) | 10 (LH)
  refire_lockout_sessions: 21 (entry) | 63 (LH) per PL-R4
  config                 : frozen threshold dict — any parameter change ships
                           as engine_id-v2 with a fresh ledger (PL-R2)
  config_hash            : sha256 of canonical (sorted-keys, compact) JSON of config
  kill_adjacency         : cite standing kill when applicable (PL-R9 / §8)

Expose REGISTRY (ordered list) and BY_ID (dict keyed by engine_id).
"""
from __future__ import annotations

import hashlib
import json


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
        engine_id="plab_1d_pure",
        name_en="1D Pure (velocity gate)",
        name_zh="1日纯速 (动能门)",
        family="A",
        ruler="21d_spy_excess",
        max_picks=12,
        refire_lockout_sessions=21,
        config={
            "macd_xup_bars_max": 2,       # 1D MACD cross-up ≤2 sessions ago
            "kd_xup_bars_max": 8,          # 1D k×d cross-up ≤8 sessions
            "require_from_os": True,        # 1D from_os (d<20 within 8)
            "rsi14_max": 65,               # RSI14 < 65
            "rank_by": "composite_z",
        },
    ),
    _entry(
        engine_id="plab_1d_regime",
        name_en="1D Regime-filtered",
        name_zh="1日制度过滤",
        family="A",
        ruler="21d_spy_excess",
        max_picks=12,
        refire_lockout_sessions=21,
        config={
            "macd_xup_bars_max": 2,        # 1D MACD cross ≤2
            "kd_xup_bars_max": 8,           # 1D k×d cross ≤8
            "calm_min": 0.5,
            "liquidity_not_contracting": True,  # liquidity_overlay != 'contracting'
            "ext_grade_not_parabolic": True,
            "require_from_os": False,       # no RSI cap, no from_os — admits strong names
            "rank_by": "edge_alpha",
        },
    ),
    _entry(
        engine_id="plab_1d_sectorheat",
        name_en="1D Sector-heat",
        name_zh="1日板块热度",
        family="A",
        ruler="21d_spy_excess",
        max_picks=12,
        refire_lockout_sessions=21,
        config={
            # book-2 base conditions
            "macd_xup_bars_max": 2,
            "kd_xup_bars_max": 8,
            "calm_min": 0.5,
            "liquidity_not_contracting": True,
            "ext_grade_not_parabolic": True,
            "require_from_os": False,
            # sector heat overlay
            "sector_heat_improving_stages": ["improving", "leading"],
            "sector_rs_mom20_positive": True,       # sector_rs_mom20 > 0
            "sector_heat_phases": ["Trough", "Recovery"],  # OR condition
            "rank_by": "composite_z",
        },
    ),
    _entry(
        engine_id="plab_1d_blastoff",
        name_en="1D Blastoff (3D gate miss)",
        name_zh="1日起飞 (3日门遗漏)",
        family="A",
        ruler="21d_spy_excess",
        max_picks=12,
        refire_lockout_sessions=21,
        config={
            "macd_xup_bars_max": 3,            # 1D MACD cross ≤3
            "d2_macd_xup_bars_max": None,      # no 2D cross requirement
            "d3_macd_crossed": False,           # 3D MACD NOT yet crossed
            "above_200": True,
            "ext_grade": "none",               # ext_grade = none
            "rank_by": "edge_alpha",
        },
    ),
]

# ------------------------------------------------------------------ Family B — momentum ---
_B = [
    _entry(
        engine_id="plab_breakout_vol",
        name_en="Breakout + Volume",
        name_zh="突破+量能",
        family="B",
        ruler="21d_spy_excess",
        max_picks=12,
        refire_lockout_sessions=21,
        config={
            "is_20d_high": True,           # close = 20d high
            "vol_ratio_20d_min": 1.5,
            "ext_grade_not_parabolic": True,
            "calm_min": 0.5,
            "rank_by": "vol_ratio_20d",
        },
    ),
    _entry(
        engine_id="plab_resid_mom",
        name_en="Residual Momentum (no gate)",
        name_zh="残差动能 (无门控)",
        family="B",
        ruler="21d_spy_excess",
        max_picks=12,
        refire_lockout_sessions=21,
        config={
            "calm_min": 0.5,
            "ext_grade_not_parabolic": True,
            "no_oscillator_condition": True,  # prices the gate's cost on momentum leaders
            "rank_by": "edge_alpha",
        },
    ),
    _entry(
        engine_id="plab_otr_pullback",
        name_en="On-the-Run Pullback",
        name_zh="热门板块回调",
        family="B",
        ruler="21d_spy_excess",
        max_picks=12,
        refire_lockout_sessions=21,
        config={
            "sector_bucket": "on_the_run",
            "above_200": True,
            "pct_vs_20dma_min": -0.08,     # pullback band [-8%, -2%]
            "pct_vs_20dma_max": -0.02,
            "d1_k_above_d": True,           # 1D k > d (stoch not crossed down)
            "d1_d_max": 50,                 # 1D d < 50
            "rank_by": "composite_z",
        },
    ),
    _entry(
        engine_id="plab_hi_base",
        name_en="High Base / Squeeze",
        name_zh="高位基建/盘整",
        family="B",
        ruler="21d_spy_excess",
        max_picks=12,
        refire_lockout_sessions=21,
        config={
            "off_52w_high_pct_max": 0.10,  # off_52w_high_pct ≤ 10%
            "vol_squeeze_on": True,          # vol_squeeze_state is active
            "rank_by": "composite_z",
        },
        kill_adjacency=(
            "near_52w_high alone anti-predictive (MEASUREMENT_FLOOR); "
            "this tests CONDITIONED construction (squeeze/basing) — PL-R9/§8"
        ),
    ),
]

# ------------------------------------------------------------------ Family C — washout ---
_C = [
    _entry(
        engine_id="plab_washout_deep",
        name_en="Deep Washout + Structure",
        name_zh="深度洗盘+结构",
        family="C",
        ruler="21d_abs_reversion_capture_mfe_mae",
        max_picks=12,
        refire_lockout_sessions=21,
        config={
            "washout_active": True,
            "dd_pct_min": 25.0,             # dd_pct > 25
            "coiled_or_star": True,          # coiled OR star
            "d3_from_os": True,              # 3D from_os (uses d3 grid)
            "rank_by": "dd_pct",
        },
    ),
    _entry(
        engine_id="plab_sector_trough",
        name_en="Sector Trough / Recovery",
        name_zh="板块底部/复苏",
        family="C",
        ruler="21d_abs_reversion_capture_mfe_mae",
        max_picks=12,
        refire_lockout_sessions=21,
        config={
            "sector_phases": ["Trough", "Recovery"],
            "tier_whitelist": ["T1", "T2"],
            "t_ticks_max": 2,               # fresh: t_ticks ≤ 2
            "rank_by": "composite_z",
        },
        kill_adjacency=(
            "rotation×cycle-position DON'T-TEST kill; "
            "this is sector-PHASE screen (sector_central), no oracle rotation input — PL-R9/§8"
        ),
    ),
    _entry(
        engine_id="plab_washout_clean",
        name_en="Clean Washout (quality screen)",
        name_zh="优质洗盘",
        family="C",
        ruler="21d_abs_reversion_capture_mfe_mae",
        max_picks=12,
        refire_lockout_sessions=21,
        config={
            "washout_active": True,
            "dd_pct_min": 20.0,
            "dilution_events_365d_max": 0,
            "days_since_shelf_min_or_null": 90,   # > 90 or null passes
            "interest_coverage_min_or_null": 2.0,  # > 2 or null passes
            "rank_by": "axis_quality",
        },
    ),
]

# ------------------------------------------------------------------ Family D — EDGE/quality ---
_D = [
    _entry(
        engine_id="plab_edge_pure",
        name_en="EDGE Pure (no gate)",
        name_zh="纯EDGE (无门控)",
        family="D",
        ruler="21d_spy_excess",
        max_picks=12,
        refire_lockout_sessions=21,
        config={
            "exclude_blackout": True,       # only exclusion: earnings blackout
            "no_entry_gate": True,          # no entry oscillator gate
            "rank_by": "axis_selection",
        },
    ),
    _entry(
        engine_id="plab_edge_1d",
        name_en="EDGE × 1D Grid",
        name_zh="EDGE×1日网格",
        family="D",
        ruler="21d_spy_excess",
        max_picks=12,
        refire_lockout_sessions=21,
        config={
            "axis_selection_top_quartile": True,
            "d1_macd_xup_bars_max": 3,     # 1D MACD cross ≤3
            "d1_kd_xup_bars_max": 8,        # 1D k×d cross ≤8
            "rank_by": "axis_selection",
        },
        kill_adjacency=(
            "insider×T2 KILLED (#1781); "
            "this is composite EDGE axis × 1D grid ≠ insider × T2-tier interaction — PL-R9/§8"
        ),
    ),
    _entry(
        engine_id="plab_quality_pullback",
        name_en="Quality Pullback",
        name_zh="优质回调",
        family="D",
        ruler="21d_spy_excess",
        max_picks=12,
        refire_lockout_sessions=21,
        config={
            "axis_quality_top_quartile": True,
            "archetypes": ["quality_compounder", "secular_growth"],
            "pct_vs_20dma_max": 0.0,        # pct_vs_20dma < 0 (any pullback)
            "rsi14_max": 55,
            "above_200": True,
            "rank_by": "axis_quality",
        },
    ),
]

# ------------------------------------------------------------------ Family E — context ---
_E = [
    _entry(
        engine_id="plab_beta_squeeze",
        name_en="Beta Squeeze",
        name_zh="Beta压缩",
        family="E",
        ruler="21d_spy_excess",
        max_picks=12,
        refire_lockout_sessions=21,
        config={
            "archetype": "high_beta_momentum",
            "current_mode": "squeeze",
            "calm_min": 0.5,
            "rank_by": "edge_alpha",
        },
    ),
    _entry(
        engine_id="plab_revision_accel",
        name_en="Revision Acceleration",
        name_zh="预测加速上修",
        family="E",
        ruler="21d_spy_excess",
        max_picks=12,
        refire_lockout_sessions=21,
        config={
            "edge_revision_min": 1.0,
            "implied_upside_pct_min": 15.0,
            "not_blackout": True,
            "above_200": True,
            "rank_by": "edge_revision",
        },
    ),
]

# ------------------------------------------------------------------ Family F — ablations + control ---
_F = [
    _entry(
        engine_id="plab_flagship_nogate",
        name_en="Flagship (no oscillator gate)",
        name_zh="旗舰 (无振荡器门控)",
        family="F",
        ruler="21d_spy_excess",
        max_picks=12,
        refire_lockout_sessions=21,
        config={
            "exclude_cycle_hard_block": True,  # cycle hard-block states still excluded
            "no_oscillator_gate": True,         # ignores confluence gate
            "rank_by": "composite_z",
        },
    ),
    _entry(
        engine_id="plab_flagship_t3t4",
        name_en="Flagship T3/T4 (early tiers)",
        name_zh="旗舰T3/T4 (早期档位)",
        family="F",
        ruler="21d_spy_excess",
        max_picks=12,
        refire_lockout_sessions=21,
        config={
            "tier_whitelist": ["T1", "T2", "T3", "T4"],  # early/projected tiers admitted
            "rank_by": "composite_z",
        },
    ),
    _entry(
        engine_id="plab_topping_avoid",
        name_en="Topping Avoid (INVERSE)",
        name_zh="顶部规避 (反向)",
        family="F",
        ruler="21d_spy_excess_avoid_accuracy",
        max_picks=12,
        refire_lockout_sessions=21,
        config={
            "cycle_states_avoid": ["TOP WATCH", "ROLLING OVER"],
            "sector_bucket_avoid": "take_profits",  # OR condition
            "sector_rsi14_min": 70,                  # AND rsi14 > 70
            "rank_by": "rsi14_desc",                 # rank highest RSI first (highest risk)
            "inverse": True,                         # scored as avoid-accuracy (expected negative)
        },
        kill_adjacency=(
            "FRESH-BUY-as-edge REFUTED (#1513); "
            "this measures the veto/EXIT side (avoid-accuracy), proposes no buy edge — PL-R9/§8"
        ),
    ),
    _entry(
        engine_id="plab_random_ctrl",
        name_en="Random Control",
        name_zh="随机基准",
        family="F",
        ruler="21d_spy_excess",
        max_picks=12,
        refire_lockout_sessions=21,
        config={
            "sample_n": 12,
            "seed_method": "sha256(engine_id+asof)",  # deterministic per PL-R12
            "rank_by": "random",
        },
    ),
]

# ------------------------------------------------------------------ Long-Hold grids ---
_LH = [
    _entry(
        engine_id="plab_lh_compounder",
        name_en="LH Compounder Grid",
        name_zh="长持复利网格",
        family="LH",
        ruler="126d_252d_sector_relative_spy_excess_descriptive",
        horizon_role="hold_thesis",
        max_picks=10,
        refire_lockout_sessions=63,
        config={
            "axis_quality_top_decile": True,
            "archetypes": ["quality_compounder", "secular_growth"],
            "dilution_events_365d_max": 0,
            "rank_by": "axis_quality",
        },
    ),
    _entry(
        engine_id="plab_lh_edge_durability",
        name_en="LH EDGE Durability Grid",
        name_zh="长持EDGE耐久网格",
        family="LH",
        ruler="126d_252d_sector_relative_spy_excess_descriptive",
        horizon_role="hold_thesis",
        max_picks=10,
        refire_lockout_sessions=63,
        config={
            "axis_selection_top_decile": True,
            "axis_quality_above_median": True,
            "rank_by": "axis_selection",
        },
    ),
    _entry(
        engine_id="plab_lh_washout_survivor",
        name_en="LH Washout Survivor Grid",
        name_zh="长持洗盘幸存网格",
        family="LH",
        ruler="126d_252d_sector_relative_spy_excess_descriptive",
        horizon_role="hold_thesis",
        max_picks=10,
        refire_lockout_sessions=63,
        config={
            "dd_pct_min": 40.0,
            "axis_quality_above_median": True,
            "interest_coverage_min": 3.0,
            "dilution_events_365d_max": 0,
            "rank_by": "axis_quality",
        },
    ),
]

# ------------------------------------------------------------------ Exports ---
REGISTRY: list[dict] = _A + _B + _C + _D + _E + _F + _LH
BY_ID: dict[str, dict] = {b["engine_id"]: b for b in REGISTRY}

# Sanity check at module load: 23 books, all config_hashes unique
assert len(REGISTRY) == 23, f"Expected 23 books, got {len(REGISTRY)}"
assert len({b["config_hash"] for b in REGISTRY}) == 23, "Duplicate config_hash detected"
