"""engine/flow_leaders.py — Flow Leaders Desk pure-function engine (FL W1).

Pure-function layer; zero I/O, zero LLM. Callers pass pandas objects.
Display-tier only (CONST-ART2); nothing here feeds authority-path consumers.

Compliance:
  FL-R2  — rank by a single measured statistic; thresholds pre-registered-arbitrary
  FL-R3  — signing_source honesty (~-soft where noted)
  FL-R4  — 0DTE hygiene (ZERODTE_MAX threshold from dossier §6.4)
  FL-R5  — OI-confirmation PIT-pinned on chains store
  FL-R6  — K-of-N booleans; tri-state legs; null ≠ False
  FL-R8  — fire rules; asof-agnostic leg structs; PIT law
  FL-R12 — de-escalation labels, display-only
  FL-R15 — freshness SLA gates; recurrence halts on stale store
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

import numpy as np
import pandas as pd

log = logging.getLogger(__name__)

# ── Thresholds (frozen; pre-registered-arbitrary per FL-R2 unless noted) ─────

# dossier §6.4 / ≥7-DTE principle — empirically argued, not arbitrary
ZERODTE_MAX: float = 0.60

# pre-registered-arbitrary (FL-R2; frozen, not tuned on observed cases)
TOP_N: int = 20               # top-N slots in the normalized net-impact table
RECUR_WINDOW: int = 10        # trailing sessions for recurrence count
RECUR_LEG_WINDOW: int = 5     # trailing sessions for flow_recur_leg (A1 partial)
RECUR_LEG_MIN: int = 3        # ≥3 of trailing 5 → flow_recur (A1)

# dossier §7.5 — z≥2 empirically argued
MIN_Z: float = 2.0

# pre-registered-arbitrary
MIN_Z_HISTORY: int = 20       # build_flow_desk.py precedent
INFLECT_NEG_SESSIONS: int = 3 # B5 soft-path: flip after ≥3 negative sessions

# FL-R5 — OI confirmation (arbitrary but self-consistent)
OI_CONFIRM_VOL_MULT: float = 3.0  # flow-day volume ≥ 3× prior OI

# Board legs
DOMINANT_K: int = 3           # top-k strikes by flow-day volume (FL-R5)

# de-escalation (FL-R12)
EARNINGS_WINDOW_DAYS: int = 14  # Cremers et al. 2023

# Board B recurrence / price confluence
RVOL_CONFIRM: float = 1.30       # A7 vol_confirm threshold (pre-registered-arbitrary)
HIGH52W_PROX_MIN: float = 0.90   # A6 near_high threshold (pre-registered-arbitrary)
UPTURN_WATCH_STATE: str = "UPTURN_WATCH"  # mtf_upturn state for B3

# Cold-start clock: minimum sessions of membership history before recurrence is defined.
# Sourced from masterplan §2 ("5-session cold-start clock").
RECUR_MIN_HISTORY: int = 5


# ── Kleene three-valued logic helpers (FL-R6) ─────────────────────────────────

def _and3(*vals: bool | None) -> bool | None:
    """Kleene AND over pre-evaluated bool-or-None operands.

    Returns:
        False  — any operand is False (short-circuits regardless of None)
        True   — all operands are True (none are None)
        None   — at least one operand is None, none are False
    """
    has_none = False
    for v in vals:
        if v is False:
            return False
        if v is None:
            has_none = True
    return None if has_none else True


def _or3(*vals: bool | None) -> bool | None:
    """Kleene OR over pre-evaluated bool-or-None operands.

    Returns:
        True   — any operand is True (short-circuits regardless of None)
        False  — all operands are False (none are None)
        None   — at least one operand is None, none are True
    """
    has_none = False
    for v in vals:
        if v is True:
            return True
        if v is None:
            has_none = True
    return None if has_none else False


def _is_null(v: object) -> bool:
    """True when v is a null sentinel (None, pd.NA, or float NaN)."""
    if v is None:
        return True
    if v is pd.NA:
        return True
    if isinstance(v, float) and pd.isna(v):
        return True
    return False


# ── Normalized impact table ───────────────────────────────────────────────────

def normalized_impact_table(
    day_rows: pd.DataFrame,
    mktcap_bn: dict[str, float],
    net_premium_ex0dte_mn: dict[str, float] | None = None,
) -> pd.DataFrame:
    """Build the per-session normalized net-impact table (FL-R2/FL-R4).

    Args:
        day_rows: One session's per-name rows.  Required columns:
            ``ticker``, ``net_premium_mn``, ``premium_mn``, ``zerodte_share``,
            ``signing_source``.  Rows where ``zerodte_share`` is null keep all
            flow fields as-is (treated as un-excluded unless tape source gives
            ex-0DTE net premium directly).
        mktcap_bn: Mapping ticker → market-cap in $bn.  Missing tickers get a
            null ``net_prem_norm`` (excluded from ranking, not faked).
        net_premium_ex0dte_mn: Optional mapping ticker → ex-0DTE net premium
            (from tape-source DTE buckets).  When present for a ticker, its
            ``zerodte_excluded`` flag is set to False even if ``zerodte_share``
            exceeds ZERODTE_MAX and the ex-0DTE value is used for ranking.

    Returns:
        DataFrame with all input columns plus:
          ``net_prem_norm``     : net_premium_mn / mktcap_bn (null when missing)
          ``zerodte_excluded``  : bool — name excluded from recurrence count
          ``in_top20``          : bool — in the top-TOP_N by net_prem_norm among
                                  non-excluded, non-null-norm rows

    Null-safety: a row with missing mktcap gets null net_prem_norm and is treated
    as excluded (cannot rank without normalisation).
    """
    df = day_rows.copy()
    ex0dte = net_premium_ex0dte_mn or {}

    # --- 0DTE exclusion / ex-0DTE net premium override ---
    excluded: list[bool] = []
    norm_vals: list[float | None] = []

    for _, row in df.iterrows():
        ticker = str(row.get("ticker", ""))
        z_share = row.get("zerodte_share")

        # tape source with ex-0DTE net premium: use it and mark NOT excluded
        if ticker in ex0dte:
            net_pm = ex0dte[ticker]
            excl = False
        else:
            net_pm = row.get("net_premium_mn")
            excl = bool(z_share is not None and not pd.isna(z_share) and z_share > ZERODTE_MAX)

        excluded.append(excl)

        # mktcap normalisation
        cap = mktcap_bn.get(ticker)
        if cap is not None and not pd.isna(cap) and cap > 0 and net_pm is not None and not pd.isna(net_pm):
            norm_vals.append(float(net_pm) / float(cap))
        else:
            norm_vals.append(None)

    df["zerodte_excluded"] = excluded
    df["net_prem_norm"] = norm_vals

    # --- rank among non-excluded rows with valid norm ---
    eligible_mask = ~df["zerodte_excluded"] & df["net_prem_norm"].notna()
    eligible = df.loc[eligible_mask, "net_prem_norm"]
    ranked = eligible.rank(ascending=False, method="min")
    in_top = ranked <= TOP_N

    df["in_top20"] = False
    df.loc[eligible_mask, "in_top20"] = in_top.reindex(df.loc[eligible_mask].index, fill_value=False)

    return df


# ── Recurrence counter ────────────────────────────────────────────────────────

def recurrence_count(membership: pd.DataFrame) -> pd.Series:
    """Per-ticker count of top-20 sessions within trailing RECUR_WINDOW sessions.

    Args:
        membership: DataFrame with columns ``session`` (date-like) and
            ``ticker`` and ``in_top20`` (bool).  Must cover all sessions
            for all tickers to be ranked (sparse frames allowed — missing
            sessions for a ticker count as absent, not False).

    Returns:
        pd.Series indexed by ticker; value = count of sessions in which the
        ticker appeared in_top20 within the trailing RECUR_WINDOW.
        Value is null (pd.NA) when fewer than 5 sessions of history exist
        for that ticker (cold-start contract).

    Callers wanting ``flow_recur_leg`` (A1) should call ``flow_recur_leg()``
    which applies the RECUR_LEG_MIN/RECUR_LEG_WINDOW rule.
    """
    if membership.empty:
        return pd.Series(dtype="Float64")

    sessions = sorted(membership["session"].unique())
    trailing = sessions[-RECUR_WINDOW:]
    window_data = membership[membership["session"].isin(trailing)]

    # count True in_top20 per ticker within the window
    counts: dict[str, int] = (
        window_data[window_data["in_top20"] == True]  # noqa: E712
        .groupby("ticker")
        .size()
        .to_dict()
    )

    # apply cold-start null: ticker with < RECUR_MIN_HISTORY sessions of ANY history → null
    history_counts = membership.groupby("ticker")["session"].nunique()
    result: dict[str, float | None] = {}
    for ticker in membership["ticker"].unique():
        if history_counts.get(ticker, 0) < RECUR_MIN_HISTORY:
            result[ticker] = None
        else:
            result[ticker] = float(counts.get(ticker, 0))

    return pd.Series(result, dtype="Float64")


def flow_recur_leg(membership: pd.DataFrame) -> pd.Series:
    """A1 leg: ≥RECUR_LEG_MIN of trailing RECUR_LEG_WINDOW sessions in top-20.

    Returns:
        pd.Series[bool | None] — True when condition met; None (pd.NA) when
        fewer than 5 sessions of history exist (same cold-start rule).
    """
    if membership.empty:
        return pd.Series(dtype=object)

    sessions = sorted(membership["session"].unique())
    trailing = sessions[-RECUR_LEG_WINDOW:]
    window_data = membership[membership["session"].isin(trailing)]

    counts: dict[str, int] = (
        window_data[window_data["in_top20"] == True]  # noqa: E712
        .groupby("ticker")
        .size()
        .to_dict()
    )
    history_counts = membership.groupby("ticker")["session"].nunique()
    result: dict[str, Any] = {}
    for ticker in membership["ticker"].unique():
        if history_counts.get(ticker, 0) < RECUR_MIN_HISTORY:
            result[ticker] = pd.NA
        else:
            cnt = counts.get(ticker, 0)
            result[ticker] = bool(cnt >= RECUR_LEG_MIN)

    return pd.Series(result, dtype=object)


# ── Dominant strikes ──────────────────────────────────────────────────────────

def dominant_strikes(chain_day: pd.DataFrame, top_k: int = DOMINANT_K) -> pd.DataFrame:
    """Top-k strikes per underlying by flow-day volume (FL-R5).

    Args:
        chain_day: polygon_gex chains day DataFrame with columns:
            ``underlying``, ``K`` (strike), ``is_call``, ``volume``, ``oi``.
        top_k: Number of dominant strikes per underlying (default 3).

    Returns:
        DataFrame of the top-k rows per underlying by volume descending.
        Empty DataFrame when input is empty.
    """
    if chain_day.empty:
        return pd.DataFrame()

    return (
        chain_day
        .sort_values("volume", ascending=False)
        .groupby("underlying", group_keys=False)
        .head(top_k)
        .reset_index(drop=True)
    )


# ── OI confirmation ───────────────────────────────────────────────────────────

def oi_confirm(chain_flow_day: pd.DataFrame, chain_next_day: pd.DataFrame) -> pd.Series:
    """Per-underlying OI-confirmation flag (FL-R5, tri-state).

    Definition: ΔOI > 0 at the dominant strikes (top-k by flow-day volume)
    AND flow-day volume ≥ OI_CONFIRM_VOL_MULT × prior OI at those strikes.

    Args:
        chain_flow_day: Chains parquet for the flow day.
          Columns: ``underlying``, ``K``, ``is_call``, ``volume``, ``oi``.
        chain_next_day: Chains parquet for the following trading day.
          Same schema.

    Returns:
        pd.Series indexed by underlying.  Values:
          True  — both ΔOI > 0 AND volume ≥ 3× prior OI at dominant strikes
          False — criteria not met
          None  — either chains day absent for that underlying (tri-state)

    Callers must stamp fire_date = next_day's asof when this flag is used.
    """
    result: dict[str, bool | None] = {}

    if chain_flow_day.empty:
        return pd.Series(result, dtype=object)

    underlyings = chain_flow_day["underlying"].unique()

    for u in underlyings:
        fd = chain_flow_day[chain_flow_day["underlying"] == u]
        nd_all = chain_next_day[chain_next_day["underlying"] == u] if not chain_next_day.empty else pd.DataFrame()

        if nd_all.empty:
            # next-day chain absent → tri-state null
            result[u] = None
            continue

        # dominant strikes of the flow day (top-k by volume)
        dom = fd.nlargest(DOMINANT_K, "volume")
        dom_keys = set(zip(dom["K"].tolist(), dom["is_call"].tolist()))

        if not dom_keys:
            result[u] = None
            continue

        # subset next-day chain to dominant strikes
        nd = nd_all[nd_all.apply(lambda r: (r["K"], r["is_call"]) in dom_keys, axis=1)]

        if nd.empty:
            result[u] = None
            continue

        # delta OI at dominant strikes
        fd_at_dom = fd[fd.apply(lambda r: (r["K"], r["is_call"]) in dom_keys, axis=1)]

        # align by (K, is_call)
        prior_oi = fd_at_dom.set_index(["K", "is_call"])["oi"]
        next_oi = nd.set_index(["K", "is_call"])["oi"]
        flow_vol = fd_at_dom.set_index(["K", "is_call"])["volume"]

        shared = prior_oi.index.intersection(next_oi.index)
        if shared.empty:
            result[u] = None
            continue

        delta_oi_ok = bool((next_oi[shared] - prior_oi[shared]).gt(0).all())
        vol_ok = bool(flow_vol[shared].ge(OI_CONFIRM_VOL_MULT * prior_oi[shared]).all())

        result[u] = bool(delta_oi_ok and vol_ok)

    return pd.Series(result, dtype=object)


# ── Term-structure breadth ────────────────────────────────────────────────────

def ts_breadth(tape_row: pd.Series | None) -> int | None:
    """Count of non-0DTE DTE buckets with positive net premium (FL-R6 A4).

    Args:
        tape_row: One row from data/tape_flow/daily; expected columns:
            ``dte_1_7d``, ``dte_8_30d``, ``dte_31_90d``, ``dte_90p``.
            None when the tape source is unavailable (soft path).

    Returns:
        int 0-4 counting DTE buckets with positive net premium, or None when
        tape_row is None (soft path: caller renders chip as dark).
    """
    if tape_row is None:
        return None

    buckets = ["dte_1_7d", "dte_8_30d", "dte_31_90d", "dte_90p"]
    count = 0
    for col in buckets:
        val = tape_row.get(col) if hasattr(tape_row, "get") else getattr(tape_row, col, None)
        if val is not None and not pd.isna(val) and float(val) > 0:
            count += 1
    return count


# ── Flow inflection ───────────────────────────────────────────────────────────

def flow_inflect(net_prem_history: pd.Series) -> dict:
    """B5 soft-path: flow flips positive after ≥INFLECT_NEG_SESSIONS negative sessions.

    Args:
        net_prem_history: Time-ordered Series of net_premium_mn values (most recent last).
            ~-soft signed per FL-R3.

    Returns:
        dict with keys:
          ``inflected``            : bool | None — True when latest bar > 0 and
                                     ≥3 of the preceding bars were negative.
          ``days_since_inflection``: int | None — bars since the FIRST positive
                                     session that ended the most recent ≥3-negative
                                     run (the flip event itself), not since the most
                                     recent positive bar.  For [-1,-1,-1,5,2,3]
                                     the flip event is index 3 (5.0), so
                                     days_since_inflection = 2 (the current bar is
                                     2 steps after the flip).
        Both are None when history < 4 sessions (cold-start).
    """
    null = {"inflected": None, "days_since_inflection": None}
    if net_prem_history is None or len(net_prem_history) < 4:
        return null

    vals = net_prem_history.dropna()
    if len(vals) < 4:
        return null

    latest = float(vals.iloc[-1])
    preceding = vals.iloc[:-1]
    neg_count = int((preceding < 0).sum())

    inflected = bool(latest > 0 and neg_count >= INFLECT_NEG_SESSIONS)

    # days_since_inflection: find the FIRST positive bar that followed the most
    # recent run of ≥INFLECT_NEG_SESSIONS consecutive/cumulative negatives.
    # Search forward from the start to find the earliest qualifying flip event.
    days_since: int | None = None
    n = len(vals)
    for i in range(1, n):
        if float(vals.iloc[i]) > 0:
            neg_before = int((vals.iloc[:i] < 0).sum())
            if neg_before >= INFLECT_NEG_SESSIONS:
                # i is the flip event; days_since = distance from i to end of series
                days_since = n - 1 - i
                break

    return {"inflected": inflected, "days_since_inflection": days_since}


# ── Flow z-score ──────────────────────────────────────────────────────────────

def flow_z(gross_prem_history: pd.Series) -> float | None:
    """Z-score of latest gross premium vs own trailing history (FL-R6 A2).

    Args:
        gross_prem_history: Time-ordered Series of gross_premium_mn values
            (most recent last).  Minimum MIN_Z_HISTORY observations required.

    Returns:
        float z-score, or None when fewer than MIN_Z_HISTORY observations,
        or None when std==0/NaN, or None when the result would be NaN/inf.

    House law (pandas-rolling-inf-nan-prep): pandas rolling maps ±inf→NaN
    pre-window; this function replicates that by replacing ±inf before stats
    so direct-kernel fast-paths produce bit-equivalent results.

    Precedent: build_flow_desk.py MIN_Z_HISTORY = 20.
    """
    if gross_prem_history is None:
        return None
    # Sanitize ±inf before computing stats (house law: inf contaminates mean/std)
    vals = gross_prem_history.replace([np.inf, -np.inf], np.nan).dropna()
    if len(vals) < MIN_Z_HISTORY:
        return None
    mu = float(vals.mean())
    std = float(vals.std(ddof=1))
    if std == 0 or pd.isna(std):
        return None
    latest = float(vals.iloc[-1])
    result = (latest - mu) / std
    if pd.isna(result):
        return None
    return round(result, 3)


# ── De-escalation flags (FL-R12) ─────────────────────────────────────────────

def earnings_window(days_to_earnings: int | None) -> bool | None:
    """True when within EARNINGS_WINDOW_DAYS of next earnings (Cremers 2023).

    Tri-state: None when days_to_earnings is None.
    """
    if days_to_earnings is None:
        return None
    return bool(days_to_earnings <= EARNINGS_WINDOW_DAYS)


def vol_trade_flag(tape_row: pd.Series | None) -> bool | None:
    """Both ask-side call and put premiums z-elevated same session (tape only).

    Tri-state: None when tape_row is None.
    """
    if tape_row is None:
        return None
    ask_call = tape_row.get("ask_side_call_premium") if hasattr(tape_row, "get") else getattr(tape_row, "ask_side_call_premium", None)
    ask_put = tape_row.get("ask_side_put_premium") if hasattr(tape_row, "get") else getattr(tape_row, "ask_side_put_premium", None)
    if ask_call is None or ask_put is None or pd.isna(ask_call) or pd.isna(ask_put):
        return None
    # Both z-elevated = both > 0 (positive = above-average ask-side premium)
    return bool(float(ask_call) > 0 and float(ask_put) > 0)


def protective_put_flag(tape_row: pd.Series | None) -> bool | None:
    """Put flow money far OTM dominant — hedging-likely heuristic (tape only).

    Tri-state: None when tape_row is None.  Column ``money_far_otm`` expected
    as a float in [0, 1] representing put-dominant far-OTM premium fraction.
    """
    if tape_row is None:
        return None
    val = tape_row.get("money_far_otm") if hasattr(tape_row, "get") else getattr(tape_row, "money_far_otm", None)
    if val is None or pd.isna(val):
        return None
    return bool(float(val) > 0)


def gamma_caution(gamma_regime: str | None) -> bool | None:
    """Short-gamma regime → caution flag (sign-free per GEXR law).

    Tri-state: None when gamma_regime is None.
    """
    if gamma_regime is None:
        return None
    return bool(gamma_regime == "short")


# ── Leg dataclasses ───────────────────────────────────────────────────────────

@dataclass
class Legs:
    """Base dataclass for tri-state confluence legs.

    K = count of True legs; n_avail = count of non-None legs.
    Null legs never count as False.
    """
    K: int = field(default=0, init=False)
    n_avail: int = field(default=0, init=False)

    def _bool_fields(self) -> list[bool | None]:
        raise NotImplementedError

    def __post_init__(self) -> None:
        vals = self._bool_fields()
        self.K = sum(1 for v in vals if v is True)
        # n_avail: count non-null legs (None, pd.NA, and float NaN are all null)
        self.n_avail = sum(1 for v in vals if not _is_null(v))


@dataclass
class BoardALegs(Legs):
    """Board A — Flow Leadership legs (A1..A8).

    All fields tri-state (True/False/None); K and n_avail computed post-init.
    """
    A1_flow_recur: bool | None = None        # ≥3 of trailing 5 in top-20 normalized
    A2_flow_z_hot: bool | None = None        # gross-premium z ≥ 2 (min 20 obs)
    A3_oi_confirmed: bool | None = None      # FL-R5 OI-confirmation flag (t+1 asof)
    A4_ts_breadth: bool | None = None        # ≥2 DTE buckets net-positive (tape only)
    A5_price_leader: bool | None = None      # ribbon_up AND rs_1m > 0
    A6_near_high: bool | None = None         # high52w_prox ≥ 0.90
    A7_vol_confirm: bool | None = None       # rel_volume ≥ 1.30 OR obv_slope_up
    A8_not_trap: bool | None = None          # NOT failed_breakout_trap

    def _bool_fields(self) -> list[bool | None]:
        return [self.A1_flow_recur, self.A2_flow_z_hot, self.A3_oi_confirmed,
                self.A4_ts_breadth, self.A5_price_leader, self.A6_near_high,
                self.A7_vol_confirm, self.A8_not_trap]


@dataclass
class BoardBLegs(Legs):
    """Board B — Washout Turn legs (B1..B8).

    All fields tri-state (True/False/None); K and n_avail computed post-init.
    B4 htf_cross_near is display chip only — never fire-qualifying (FL-R7).
    """
    B1_washout_recent: bool | None = None    # IFT washout_context
    B2_oversold_osc: bool | None = None      # weekly StochRSI K<20 OR rsi_stack_oversold
    B3_turn_organ: bool | None = None        # mtf_upturn ≥ UPTURN_WATCH
    B4_htf_cross_near: bool | None = None    # W/2W MACD crossed or ETA ≤2 bars (DISPLAY ONLY)
    B5_flow_inflect: bool | None = None      # flow flips positive after ≥3 negative sessions
    B6_oi_confirmed: bool | None = None      # FL-R5 OI-confirmation
    B7_vol_confirm: bool | None = None       # rel_volume ≥ 1.30 OR obv_slope_up
    B8_not_trap: bool | None = None          # NOT failed_breakout_trap

    def _bool_fields(self) -> list[bool | None]:
        return [self.B1_washout_recent, self.B2_oversold_osc, self.B3_turn_organ,
                self.B4_htf_cross_near, self.B5_flow_inflect, self.B6_oi_confirmed,
                self.B7_vol_confirm, self.B8_not_trap]


# ── Board evaluators ──────────────────────────────────────────────────────────

def board_a_legs(
    *,
    recur_leg: bool | None = None,
    flow_z_val: float | None = None,
    oi_confirmed: bool | None = None,
    ts_breadth_val: int | None = None,
    ribbon_up: bool | None = None,
    rs_1m: float | None = None,
    high52w_prox: float | None = None,
    rel_volume: float | None = None,
    obv_slope_up: bool | None = None,
    failed_breakout_trap: bool | None = None,
) -> BoardALegs:
    """Evaluate Board A legs from precomputed primitives (FL-R6).

    All inputs are precomputed by the caller; no I/O here.

    Args:
        recur_leg: Output of flow_recur_leg() for this ticker.
        flow_z_val: Output of flow_z() for this ticker's gross_premium history.
        oi_confirmed: Output of oi_confirm() for this ticker (t+1 known).
        ts_breadth_val: Output of ts_breadth() for this ticker.
        ribbon_up: Price ribbon above MA stack (from stock context).
        rs_1m: 1-month relative strength (positive = outperforming).
        high52w_prox: Proximity to 52-week high in [0, 1].
        rel_volume: Relative volume ratio.
        obv_slope_up: OBV slope positive.
        failed_breakout_trap: Personality flag from stock_personality.

    Returns:
        BoardALegs dataclass with tri-state fields and K/n_avail counts.
    """
    # A1: flow recurrence (pre-evaluated)
    a1 = recur_leg

    # A2: gross-premium z ≥ 2; None when flow_z_val is None or NaN (M1)
    a2: bool | None = None
    if flow_z_val is not None and not (isinstance(flow_z_val, float) and pd.isna(flow_z_val)):
        a2 = bool(flow_z_val >= MIN_Z)

    # A3: OI-confirmed (t+1 asof — caller stamps fire_date accordingly)
    a3 = oi_confirmed

    # A4: ts_breadth ≥ 2 non-0DTE buckets net-positive (tape source only)
    a4: bool | None = None
    if ts_breadth_val is not None:
        a4 = bool(ts_breadth_val >= 2)

    # A5: price_leader = ribbon_up AND rs_1m > 0
    # Kleene AND (B1): False when ribbon_up is False; False when rs_1m known ≤ 0;
    # True only when both are known True; None when either is None and the other
    # doesn't already settle the result to False.
    _ribbon_false = ribbon_up is False
    _rs_false = rs_1m is not None and rs_1m <= 0
    _ribbon_true = ribbon_up is True
    _rs_true = rs_1m is not None and rs_1m > 0
    if _ribbon_false or _rs_false:
        a5: bool | None = False
    elif _ribbon_true and _rs_true:
        a5 = True
    else:
        a5 = None  # one or both unknown and no False settled the result

    # A6: near_high
    a6: bool | None = None
    if high52w_prox is not None:
        a6 = bool(high52w_prox >= HIGH52W_PROX_MIN)

    # A7: vol_confirm = rel_volume ≥ 1.30 OR obv_slope_up
    # Kleene OR (B1): True when any known operand is True; False only when all
    # known operands are False and none are None; else None.
    _rvol_bool: bool | None = None if rel_volume is None else bool(rel_volume >= RVOL_CONFIRM)
    a7: bool | None = _or3(_rvol_bool, obv_slope_up)

    # A8: not_trap
    a8: bool | None = None
    if failed_breakout_trap is not None:
        a8 = bool(not failed_breakout_trap)

    return BoardALegs(
        A1_flow_recur=a1,
        A2_flow_z_hot=a2,
        A3_oi_confirmed=a3,
        A4_ts_breadth=a4,
        A5_price_leader=a5,
        A6_near_high=a6,
        A7_vol_confirm=a7,
        A8_not_trap=a8,
    )


def board_b_legs(
    *,
    washout_ctx: dict | None = None,
    weekly_stochrsi_k_min3: float | None = None,
    rsi_stack_oversold: bool | None = None,
    mtf_upturn_state: str | None = None,
    htf_cross_near: bool | None = None,
    flow_inflect_val: dict | None = None,
    oi_confirmed: bool | None = None,
    rel_volume: float | None = None,
    obv_slope_up: bool | None = None,
    failed_breakout_trap: bool | None = None,
) -> BoardBLegs:
    """Evaluate Board B legs from precomputed primitives (FL-R6).

    B4 htf_cross_near is a display chip — passed through as-is; never
    contributes to board_b_fire().

    Args:
        washout_ctx: Output dict from engine.intraday_flow.washout_context().
        weekly_stochrsi_k_min3: min(StochRSI K over the last 3 completed weekly
            bars) per masterplan B2 "within 3 weekly bars" (0-100).  Named
            ``weekly_stochrsi_k_min3`` to make the caller's obligation explicit.
        rsi_stack_oversold: True when rsi_stack oversold within 10 sessions.
        mtf_upturn_state: String state from mtf_upturn engine.
        htf_cross_near: W or 2W MACD crossed or ETA ≤ 2 bars (display only).
        flow_inflect_val: Output dict from flow_inflect().
        oi_confirmed: OI-confirmation flag (FL-R5).
        rel_volume: Relative volume ratio.
        obv_slope_up: OBV slope positive.
        failed_breakout_trap: Personality flag.

    Returns:
        BoardBLegs dataclass with tri-state fields and K/n_avail counts.
    """
    # B1: washout_recent — bb_lower_reclaim_days present OR deep drawdown+recovery
    b1: bool | None = None
    if washout_ctx is not None:
        bbd = washout_ctx.get("bb_lower_reclaim_days")
        dd = washout_ctx.get("drawdown_21d_pct")
        rec = washout_ctx.get("recovery_begun")
        if bbd is not None:
            b1 = bool(bbd <= 10)
        elif dd is not None and rec is not None:
            b1 = bool(dd <= -0.12 and rec)

    # B2: oversold_osc — weekly StochRSI K<20 (within 3 bars) OR rsi_stack_oversold
    # Kleene OR (B1): True when any known operand is True; False when all known
    # operands are False; None when at least one is None and none are True.
    _stoch_os: bool | None = (
        None if weekly_stochrsi_k_min3 is None else bool(weekly_stochrsi_k_min3 < 20)
    )
    b2: bool | None = _or3(_stoch_os, rsi_stack_oversold)

    # B3: turn_organ = mtf_upturn ≥ UPTURN_WATCH
    # State strings mirror engine/mtf_upturn.py state machine (raw_state literals).
    b3: bool | None = None
    if mtf_upturn_state is not None:
        b3 = bool(mtf_upturn_state in (UPTURN_WATCH_STATE, "UPTURN_CONFIRMED"))

    # B4: htf_cross_near — display chip, passed through
    b4 = htf_cross_near

    # B5: flow_inflect (soft path result)
    b5: bool | None = None
    if flow_inflect_val is not None:
        inf = flow_inflect_val.get("inflected")
        if inf is not None:
            b5 = bool(inf)

    # B6: oi_confirmed
    b6 = oi_confirmed

    # B7: vol_confirm = rel_volume ≥ 1.30 OR obv_slope_up (Kleene OR, same as A7)
    _b7_rvol: bool | None = None if rel_volume is None else bool(rel_volume >= RVOL_CONFIRM)
    b7: bool | None = _or3(_b7_rvol, obv_slope_up)

    # B8: not_trap
    b8: bool | None = None
    if failed_breakout_trap is not None:
        b8 = bool(not failed_breakout_trap)

    return BoardBLegs(
        B1_washout_recent=b1,
        B2_oversold_osc=b2,
        B3_turn_organ=b3,
        B4_htf_cross_near=b4,
        B5_flow_inflect=b5,
        B6_oi_confirmed=b6,
        B7_vol_confirm=b7,
        B8_not_trap=b8,
    )


# ── Fire rules (FL-R8) ────────────────────────────────────────────────────────

def board_a_fire(legs: BoardALegs) -> bool:
    """Board A fire rule: A1 AND A8 AND (A2 OR A3).

    Null legs NEVER count as False — if a required leg is None, the
    condition for that leg is unmet (False side of the AND).  Fire requires
    all three conditions to be definitively True.

    PIT law: when A3 (oi_confirmed, t+1 asof) is the deciding leg, callers
    must stamp fire_date = the asof on which A3 became known, not the flow date.
    """
    a1 = legs.A1_flow_recur
    a8 = legs.A8_not_trap
    a2 = legs.A2_flow_z_hot
    a3 = legs.A3_oi_confirmed
    if a1 is not True or a8 is not True:
        return False
    return a2 is True or a3 is True


def board_b_fire(legs: BoardBLegs) -> bool:
    """Board B fire rule: B1 AND B5 AND B8.

    B4 (htf_cross_near) is EXCLUDED from fire qualification per FL-R6/FL-R7
    ("display chip only, never fire-qualifying").  Null legs never count as
    False — all three must be definitively True.

    The washout×flow-inflection construction is distinct from the killed
    washout×2W-turn (#1747, ESXA3-FV-C) per masterplan §3 FL-R8.
    """
    b1 = legs.B1_washout_recent
    b5 = legs.B5_flow_inflect
    b8 = legs.B8_not_trap
    return b1 is True and b5 is True and b8 is True
