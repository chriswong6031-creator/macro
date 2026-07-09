"""Pick Lab market profile — parameterises US vs CN vs HK execution conventions.

A MarketProfile dataclass captures every market-specific constant so that
ledger.py, grade.py, snapshot.py, and book.py can operate identically for
all markets with defaults that preserve the existing US behaviour.

US profile == exact current hard-coded constants (US tests stay green).
CN profile == A-share execution law (CNPL-R3/R4/R8/R9).
HK profile == HK execution law (HKPL-R3/R4/R5/R6/R7).

Public API
----------
US_PROFILE  : MarketProfile  — singleton for the US market (default everywhere)
CN_PROFILE  : MarketProfile  — singleton for the CN A-share market
HK_PROFILE  : MarketProfile  — singleton for the HK market
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Optional

import pandas as pd


# --------------------------------------------------------------------------- #
# Profile dataclass
# --------------------------------------------------------------------------- #

@dataclass(frozen=True)
class MarketProfile:
    """Immutable market profile consumed by the Pick Lab engine modules.

    Fields with defaults match the current US constants exactly — any module
    that passes `profile=US_PROFILE` (or omits the parameter) behaves
    identically to the un-parameterised original.
    """

    # ---- identity --------------------------------------------------------
    market_id: str = "US"
    """Short identifier, e.g. 'US' or 'CN'."""

    # ---- paths -----------------------------------------------------------
    fires_path: Path = Path("data/pick_lab/fires.jsonl")
    grades_path: Path = Path("data/pick_lab/grades.jsonl")
    lh_fires_path: Path = Path("data/pick_lab/lh_fires.jsonl")
    lh_grades_path: Path = Path("data/pick_lab/lh_grades.jsonl")
    snapshot_dir: Path = Path("data/pick_lab/snapshots")

    # ---- benchmark -------------------------------------------------------
    benchmark_ticker: str = "SPY"
    """Ticker used as the benchmark for ret_excess_benchmark in grade.py.

    US: 'SPY' from the main close panel.
    CN: '510300.SS' — loaded from the store in grade via benchmark_loader.
    """

    benchmark_loader: Optional[Callable[[], Optional[pd.Series]]] = None
    """Callable () -> pd.Series[DatetimeIndex -> float] | None.

    When None, grade.py expects the benchmark_ticker column to be present
    in the close_panel argument (US: SPY is already there).
    When provided, grade.py calls this at grade time to fetch benchmark
    closes (CN: reads from the canonical china store).
    """

    # ---- fill convention -------------------------------------------------
    fill_basis: str = "close"
    """'close' (US) | 'hl2_raw' (CN CNPL-R4).

    'close'   — exec price = next-session close (conservative US default).
    'hl2_raw' — exec price = (H+L)/2 from the raw parquet store; fallback
                to close when raw OHLC absent.  Only CN runner uses this;
                grade.py notes the fill_basis in each grade row.
    """

    raw_store_path_template: str = ""
    """Path template for the CN raw-OHLC store (used when fill_basis='hl2_raw').

    Template token: {date} → YYYY-MM-DD trading date string.
    Example: 'data/china_stocks_raw/{date}.parquet'
    Unused (empty string) when fill_basis='close'.
    """

    # ---- executability ---------------------------------------------------
    sealed_up_col: Optional[str] = None
    """Column in the snapshot that indicates a limit-up sealed fire.

    None (US): no sealed-up concept; all fires are fillable.
    'limit_state' (CN): value 'sealed_up' at fire close → excluded from
    grading, counted in skipped_unfillable (CNPL-R4).
    """

    fillable_col: Optional[str] = "fillable"
    """Column that carries a pre-computed fillability flag.

    US: field 'fillable' is absent from US snapshots; the column defaults to
    None (missing column = no fillability screen).
    CN: 'fillable' == False means the name is excluded from universe at fire
    time (executability screen, not a signal — CNPL-R4).

    Set to None to disable the screen entirely.
    """

    # ---- grading horizons -----------------------------------------------
    entry_horizons: tuple[int, ...] = (5, 10, 21, 63)
    """Session horizons graded for entry books."""

    lh_horizons: tuple[int, ...] = (126, 252)
    """Session horizons graded for long-hold books."""

    primary_horizon: int = 21
    """Primary ruler horizon (used for n_open, lift, NAV)."""

    mfe_mae_sessions: int = 25
    """Window for MFE/MAE computation (entry books only)."""

    # ---- scoreboard IDs -------------------------------------------------
    random_ctrl_id: str = "plab_random_ctrl"
    """engine_id of the random control book for this market."""

    avoid_engine_id: str = "plab_topping_avoid"
    """engine_id of the inverse/avoid book (scored as avoid_accuracy)."""

    # ---- refire lockout -------------------------------------------------
    refire_lockout_sessions: int = 21
    """Default refire lockout for entry books (21 for both US and CN)."""

    # ---- liquidity floor ------------------------------------------------
    liq_close_min: float = 5.0
    """Minimum close price for the liquidity floor (USD for US)."""

    liq_turnover_min: float = 10e6
    """Minimum 20d ADV/turnover for the liquidity floor."""

    # ---- max picks default ----------------------------------------------
    max_picks_default: int = 12
    """Default max picks per book."""

    # ---- extra fire stamps (CN-specific) --------------------------------
    extra_fire_stamp_cols: tuple[str, ...] = ()
    """Additional columns copied from the snapshot into the fire row.

    CN adds: board, limit_width, limit_state, t_plus_one_risk,
             cycle_phase, participation_regime, policy_impulse, qvix_z.
    """

    # ---- scoreboard extras (CN honesty columns) -------------------------
    skipped_unfillable_col: bool = False
    """When True, scoreboard carries a 'skipped_unfillable' counter (CNPL-R4)."""

    data_gap_col: bool = False
    """When True, book results may carry a 'data_gap' flag (CNPL-R9)."""

    # ---- ST exclusion ---------------------------------------------------
    st_exclude_col: Optional[str] = None
    """Column name for the ST flag.  When set, is_st==True rows are excluded.

    None (US): no ST concept.
    'is_st' (CN): ST/*ST excluded from all book universes (CNPL-R4).
    """

    # ---- ruler label overrides (CN uses 21-session excess vs CSI 300) ---
    default_ruler: str = "21d_spy_excess"
    """Default ruler label for momentum/quality books when not in ruler_map."""

    excess_label: str = "ret_excess_benchmark"
    """Column name written to grade rows for the excess return.

    US: 'ret_excess_spy' (existing schema, unchanged).
    CN: 'ret_excess_csi300' semantically, but grade.py writes it under the
    profile's excess_label so scoreboard knows which column to aggregate.
    For compatibility we keep 'ret_excess_spy' even for CN until scoreboard
    is updated — the grade row also carries 'benchmark_ticker' for clarity.
    Both US and CN default to 'ret_excess_spy' so the scoreboard reads the
    same column name either way; the benchmark_ticker stamp disambiguates.
    """


# --------------------------------------------------------------------------- #
# US singleton (default — must match every hard-coded constant in the repo)
# --------------------------------------------------------------------------- #

US_PROFILE = MarketProfile(
    market_id="US",
    fires_path=Path("data/pick_lab/fires.jsonl"),
    grades_path=Path("data/pick_lab/grades.jsonl"),
    lh_fires_path=Path("data/pick_lab/lh_fires.jsonl"),
    lh_grades_path=Path("data/pick_lab/lh_grades.jsonl"),
    snapshot_dir=Path("data/pick_lab/snapshots"),
    benchmark_ticker="SPY",
    benchmark_loader=None,
    fill_basis="close",
    raw_store_path_template="",
    sealed_up_col=None,
    fillable_col=None,        # US snapshots don't carry 'fillable'
    entry_horizons=(5, 10, 21, 63),
    lh_horizons=(126, 252),
    primary_horizon=21,
    mfe_mae_sessions=25,
    random_ctrl_id="plab_random_ctrl",
    avoid_engine_id="plab_topping_avoid",
    refire_lockout_sessions=21,
    liq_close_min=5.0,
    liq_turnover_min=10e6,
    max_picks_default=12,
    extra_fire_stamp_cols=(),
    skipped_unfillable_col=False,
    data_gap_col=False,
    st_exclude_col=None,
    default_ruler="21d_spy_excess",
    excess_label="ret_excess_spy",
)


def _hk_benchmark_loader() -> Optional[pd.Series]:
    """Load ^HSI closes from the canonical hk store group.

    Returns a pd.Series indexed by DatetimeIndex, or None on failure.
    Lazy import so the function only runs on the HK runner (not in US/CN tests).
    """
    try:
        from engine.data_store import store  # type: ignore[import]
        df = store.read("hk", "^HSI")
        if df is None or df.empty:
            return None
        close = df["close"] if "close" in df.columns else df.iloc[:, 0]
        close.index = pd.DatetimeIndex(close.index)
        return close.sort_index()
    except Exception:  # noqa: BLE001
        return None


def _cn_benchmark_loader() -> Optional[pd.Series]:
    """Load CSI 300 (510300.SS) closes from the canonical china store.

    Returns a pd.Series indexed by DatetimeIndex, or None on failure.
    Lazy import so the function only runs on the CN runner (not in US tests).
    """
    try:
        from engine.data_store import store  # type: ignore[import]
        df = store.read("china", "510300.SS")
        if df is None or df.empty:
            return None
        close = df["close"] if "close" in df.columns else df.iloc[:, 0]
        close.index = pd.DatetimeIndex(close.index)
        return close.sort_index()
    except Exception:  # noqa: BLE001
        return None


# --------------------------------------------------------------------------- #
# CN singleton
# --------------------------------------------------------------------------- #

CN_PROFILE = MarketProfile(
    market_id="CN",
    fires_path=Path("data/china_pick_lab/fires.jsonl"),
    grades_path=Path("data/china_pick_lab/grades.jsonl"),
    lh_fires_path=Path("data/china_pick_lab/lh_fires.jsonl"),
    lh_grades_path=Path("data/china_pick_lab/lh_grades.jsonl"),
    snapshot_dir=Path("data/china_pick_lab/snapshots"),
    benchmark_ticker="510300.SS",
    benchmark_loader=_cn_benchmark_loader,
    fill_basis="hl2_raw",
    raw_store_path_template="data/china_stocks_raw/{date}.parquet",
    sealed_up_col="limit_state",           # 'sealed_up' value → unfillable
    fillable_col="fillable",               # False → excluded from universe
    entry_horizons=(5, 10, 21, 63),
    lh_horizons=(126, 252),
    primary_horizon=21,
    mfe_mae_sessions=25,
    random_ctrl_id="cnlab_random_ctrl",
    avoid_engine_id="cnlab_chase_avoid",
    refire_lockout_sessions=21,
    liq_close_min=2.0,                     # CN floor: ¥2 (CNPL-R3 defaults)
    liq_turnover_min=30e6,                 # CN floor: 20d turnover ¥30M
    max_picks_default=12,
    extra_fire_stamp_cols=(
        "board",
        "limit_width",
        "limit_state",
        "t_plus_one_risk",
        "cycle_phase",
        "participation_regime",
        "policy_impulse",
        "qvix_z",
    ),
    skipped_unfillable_col=True,           # CNPL-R4 honesty counter
    data_gap_col=True,                     # CNPL-R9 store-honesty flag
    st_exclude_col="is_st",               # ST/*ST excluded (CNPL-R4)
    default_ruler="21d_csi300_excess",
    excess_label="ret_excess_spy",         # grade.py writes under this name;
                                           # benchmark_ticker stamp = 510300.SS
)


# --------------------------------------------------------------------------- #
# HK singleton
# --------------------------------------------------------------------------- #

HK_PROFILE = MarketProfile(
    market_id="HK",
    fires_path=Path("data/hk_pick_lab/fires.jsonl"),
    grades_path=Path("data/hk_pick_lab/grades.jsonl"),
    lh_fires_path=Path("data/hk_pick_lab/lh_fires.jsonl"),   # reserved; HKPL-R9: no LH in v1
    lh_grades_path=Path("data/hk_pick_lab/lh_grades.jsonl"), # reserved
    snapshot_dir=Path("data/hk_pick_lab/snapshots"),
    benchmark_ticker="^HSI",
    benchmark_loader=_hk_benchmark_loader,
    fill_basis="close",                     # HKPL-R4: exec = next HK session close; no price limits
    raw_store_path_template="",             # no raw OHLC store for HK (close fill)
    sealed_up_col=None,                     # no daily price limits in HK (HKPL-R4)
    fillable_col=None,                      # suspension guard handled in hk.py by snapshot filter
    entry_horizons=(5, 10, 21, 63),
    lh_horizons=(126, 252),
    primary_horizon=21,                     # HKPL-R3: 21-session HSI-excess is primary ruler
    mfe_mae_sessions=25,                    # HKPL-R3: MFE/MAE descriptive window
    random_ctrl_id="hklab_random_ctrl",
    avoid_engine_id="hklab_chase_avoid",    # inverse book flagged as avoid (HKPL-R10)
    refire_lockout_sessions=21,             # HKPL-R6: 21-session refire lockout
    liq_close_min=0.0,                      # HK: no close-price floor (HK$ denominated, ADV gates)
    liq_turnover_min=20e6,                  # HKPL-R3 defaults: 63d ADV ≥ HK$20M
    max_picks_default=8,                    # HKPL-R6: max 8 picks/day
    extra_fire_stamp_cols=(
        "risk_state",
        "peg_state",
        "washout_state",
        "adr_gap_pct",
        "beta_role",
        "vhsi_pctile",
        "halted",
        "halt_voided",
    ),
    skipped_unfillable_col=False,           # HK: no sealed-up concept
    data_gap_col=True,                      # organ-dependent books flag disabled_stale
    st_exclude_col=None,                    # no ST concept in HK
    default_ruler="21d_hsi_excess",
    excess_label="ret_excess_spy",          # grade.py column name (benchmark_ticker=^HSI stamps it)
)
