"""Oracle O2 — Episode layer: hysteresis state machine + rotation episode catalog.

WHAT
----
Detects rotation *episodes* — persistent directional relative-strength moves
by a node — and catalogs them with onset, confirmation, exhaustion dates plus
forward-outcome columns.  Consumes the O0 rotation panel (panel.py) and,
optionally, the P2a rotation-groups file.

WHY
---
group_flow Phase-0 tested daily cross-sectional rank-IC of fingerprint legs and
found noise.  Oracle tests *conditional persistence of detected episodes*
(onset-gated, confirmed states with hysteresis) — a different quantity.
The prior is informative: expect modest, regime-conditional edges; the system
must be valuable as a risk/exposure router even if the persistence null holds.

HONESTY FRAMING
---------------
* accel_z raw run median is 2 days (p90=5 — measured on panel_s 1998–2026).
  Single-day threshold crossings are noise.  ALL onset tests require a 5-day
  smoothed accel_z (accel_z_5d) to suppress this.
* Outcome columns are LOOK-AHEAD free: they use only forward price data that
  post-dates the detection timestamp.  Episodes whose outcome window extends
  past the panel's last date receive outcome=NaN + outcome_mature=False —
  never partially-filled forward windows.
* Two-sided pairing requires overlapping opposite-direction episodes on the
  SAME panel — rotation_groups.json is consumed when present (P2a) but the
  module degrades gracefully to node-level overlap pairing when it is absent.
* Tier-M survivorship watermark (declared-hindsight membership) propagates
  through the episode catalog: episodes on Tier-M nodes carry survivorship_flagged=True.

PUBLIC API
----------
run_state_machine(node_series, cfg=None) → list[EpisodeRow]
    Pure function over one node's panel slice.  Returns raw episode dicts.

build_episodes(panel, rotation_groups=None, cfg=None) → pd.DataFrame
    Run the state machine over every node in `panel` and assemble the catalog.
    Adds outcome columns and two-sided pairing.

EPISODE_CFG (one dict, all thresholds)
---------------------------------------
All defaults are grounded in §4 of ORACLE_MASTERPLAN_BY_FABLE.md + measured
distributions on the real panels (2026-07-04 census).  Provenance comment on
each value.  They will be re-tuned in the Phase-3 calibration; scatter is
impossible — every knob lives here.
"""
from __future__ import annotations

import logging
from typing import Any

import numpy as np
import pandas as pd

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# EPISODE_CFG — single dict, all thresholds.  ONE provenance comment per value.
# ---------------------------------------------------------------------------

EPISODE_CFG: dict[str, Any] = {
    # --- Smoothing ---
    # accel_z raw run median = 2 days (p90 = 5, measured panel_s 1998–2026).
    # Single-day crossings are noise; 5d mean suppresses them while preserving
    # genuine sustained moves.
    "accel_z_smooth_days": 5,

    # --- Onset (rotate-IN) ---
    # accel_z q87 ≈ 1.0 (interpolating between q75=0.60 and q90=1.26).
    # Threshold picks up the top ~13% of acceleration days — uncommon enough
    # to be meaningful, common enough for sufficient episode n.
    "onset_accel_z_threshold": 1.0,

    # Momentum confirmation: 3 of last 5 accel_z > 0 (majority-positive).
    # Guards against a single spike in a range-bound series.
    "onset_positive_days_in_5": 3,

    # RS momentum proxy: vel_1w − vel_3m > 0 means short-term velocity is
    # running faster than long-term velocity (accelerating relative strength).
    # This is a sign-only gate, no magnitude threshold, to avoid double-counting
    # with the accel_z threshold above.
    "onset_rs_mom_positive": True,   # gate on vel_1w − vel_3m > 0

    # --- Confirmation tier ---
    # A: sustained onset held for N consecutive sessions (patience test).
    # 5d mirrors the smoothing window — onset-tier confirmed by survival.
    "confirmed_consecutive_onset_days": 5,

    # B: cohesion_chg spike while onset is already active (group is tightening
    # in the direction of the move).  q75 of panel_m = 0.056 (|cohesion_chg|).
    "confirmed_cohesion_chg_threshold": 0.056,

    # --- Undeniable tier ---
    # RS has flipped sign in the onset direction = sign(rs) == direction AND
    # has crossed from the opposite side.  Lazy check: rs is now positive (IN)
    # or negative (OUT) by this day.
    "undeniable_rs_in_direction": True,

    # Breadth crossed 0.5 in the onset direction (above 0.5 for IN, below for OUT).
    # breadth_50 q50 = 0.53 on panel_m — this checks if majority of members have
    # crossed their 50dma in the rotation direction.  NULL breadth_50 → skip leg
    # (graceful degrade: not all nodes have member data).
    "undeniable_breadth_threshold": 0.5,

    # --- Mature state ---
    # RS extended: |rs_pctile_252d| > mature_rs_pctile_threshold.
    # q80 of rs trailing 252d rank ≈ 0.80 (by definition for a uniform distribution;
    # confirmed on panel_s spot-check).
    "mature_rs_pctile_threshold": 0.80,

    # Fading: accel_z_5d approaching 0 — use a tighter band than onset.
    # Below 0.5 (approximately q75 / 1.2 ≈ 0.50) = noticeably fading.
    "mature_fading_accel_z_threshold": 0.50,

    # --- Exhaustion ---
    # accel_z_5d crosses AGAINST the episode direction by this amount.
    # Symmetric: exhaustion OUT fires when accel_z_5d > +0.5 for an OUT episode.
    # −0.5 = approximately below q75 band, sustained reversal signal.
    "exhausted_accel_z_counter_threshold": -0.50,  # for IN; flipped for OUT

    # Confirmation: ≥3 of last 5 days accel_z crosses against direction.
    "exhausted_days_in_5": 3,

    # --- Hysteresis ---
    # Minimum gap between exhaustion end and any new onset for the SAME node.
    # Prevents re-triggering on the bounce immediately after exhaustion.
    # 5d = one trading week.
    "hysteresis_gap_days": 5,

    # Minimum episode duration before exhaustion can fire.  Prevents same-day
    # onset+exhaustion (a degenerate state that would produce zero-length episodes).
    "min_duration_before_exhaustion": 5,

    # --- Outcomes ---
    # Forward windows for RS-change outcome measurement (sessions, not calendar days).
    "outcome_horizons": [5, 21, 63],

    # --- Two-sided pairing ---
    # Minimum session overlap between an IN and OUT episode to count as a pair.
    "two_sided_min_overlap_sessions": 5,
}

# ---------------------------------------------------------------------------
# State constants (the hysteresis machine states)
# ---------------------------------------------------------------------------

_STATE_FLAT = "flat"
_STATE_ONSET = "onset"
_STATE_ACCELERATING = "accelerating"   # confirmed tier
_STATE_MATURE = "mature"
_STATE_EXHAUSTED = "exhausted"

# Direction constants
_DIR_IN = "in"    # rotate-IN: positive acceleration / gaining RS
_DIR_OUT = "out"  # rotate-OUT: negative acceleration / losing RS


# ---------------------------------------------------------------------------
# Episode record (typed dict for clarity; lives in the return list)
# ---------------------------------------------------------------------------

# Column names emitted by run_state_machine
_EPISODE_COLS = [
    "episode_id",
    "node",
    "direction",
    "onset_date",
    "confirmed_date",      # nullable
    "undeniable_date",     # nullable
    "exhausted_date",      # nullable
    "duration",            # calendar sessions from onset to exhausted/last-date
    "peak_accel_z",        # max |accel_z| during the episode
    "breadth_at_onset",    # nullable
    "cohesion_at_onset",   # nullable
    "regime_vix_pctile",   # nullable
    "regime_tlt_sign",     # sign of tlt_ret_10d at onset; nullable (−1/0/+1)
    "regime_spy_above_200d",  # nullable
    "two_sided",           # bool; filled post-pairing
    "paired_episode_id",   # nullable; filled post-pairing
    "survivorship_flagged",   # bool; Tier-M nodes carry True
]

# Outcome columns — added separately so detection logic can never accidentally
# read them (they are computed on a separate pass in build_episodes).
_OUTCOME_COLS_TEMPLATE = [
    "outcome_rs_{h}d",        # fwd RS-change of the node at +h sessions from onset
    "outcome_rs_{h}d_confirmed",  # same, measured from confirmed_date
    "outcome_rs_{h}d_undeniable",  # same, measured from undeniable_date
    "outcome_mature_{h}d",    # bool: outcome window fully within panel span
]


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _smooth_accel_z(accel_z: np.ndarray, days: int) -> np.ndarray:
    """5d (or cfg-driven) trailing mean of accel_z.

    Uses a simple loop rather than pandas to keep the function dependency on
    numpy only.  Returns NaN for indices where the window cannot be filled.
    """
    n = len(accel_z)
    out = np.full(n, np.nan)
    for i in range(days - 1, n):
        window = accel_z[i - days + 1: i + 1]
        if np.any(np.isnan(window)):
            # If ANY element in the window is NaN, propagate NaN.
            continue
        out[i] = float(np.mean(window))
    return out


def _positive_days_in_last_n(accel_z_raw: np.ndarray, i: int, n: int) -> int:
    """Count of days in the last n where accel_z_raw > 0, ending at i."""
    if i < n - 1:
        return 0
    window = accel_z_raw[i - n + 1: i + 1]
    return int(np.sum(window > 0))


def _against_count_in_last_n(
    accel_z_raw: np.ndarray, i: int, n: int, direction: str, threshold: float
) -> int:
    """Count days in last n where accel_z_raw crosses AGAINST direction by threshold."""
    if i < n - 1:
        return 0
    window = accel_z_raw[i - n + 1: i + 1]
    if direction == _DIR_IN:
        # against IN = accel_z < -|threshold|
        return int(np.sum(window < threshold))  # threshold is negative for IN
    else:
        # against OUT = accel_z > +|threshold|
        return int(np.sum(window > -threshold))  # threshold is positive for OUT


def _rs_pctile_252d(rs_series: np.ndarray, i: int) -> float | None:
    """Causal percentile rank of rs[i] in the trailing 252-day window.

    Returns None if fewer than 126 non-NaN values available.
    """
    start = max(0, i - 252 + 1)
    window = rs_series[start: i + 1]
    valid = window[~np.isnan(window)]
    if len(valid) < 126:
        return None
    current = rs_series[i]
    if np.isnan(current):
        return None
    return float((valid < current).mean())


# ---------------------------------------------------------------------------
# Core state machine (pure function over numpy arrays for one node)
# ---------------------------------------------------------------------------

def run_state_machine(
    node_series: pd.DataFrame,
    node: str = "",
    cfg: dict[str, Any] | None = None,
) -> list[dict]:
    """Run the hysteresis episode state machine over one node's panel slice.

    Parameters
    ----------
    node_series : pd.DataFrame
        Slice of the Oracle panel for a single node, indexed by date.
        Must contain columns: accel_z, rs, vel_1w, vel_3m.
        Optional: cohesion_chg, breadth_50, vix_pctile, tlt_ret_10d,
        spy_above_200d (graceful degrade when absent or all-NaN).
    node : str
        Node name, embedded in each episode record's 'node' field.
    cfg : dict | None
        Override EPISODE_CFG keys.  Unknown keys are ignored.

    Returns
    -------
    list[dict]
        One dict per detected episode with keys matching _EPISODE_COLS
        (excluding outcome columns and two_sided/paired_episode_id which are
        filled by the caller after cross-node pairing).
        Empty list if the series is too short or has insufficient data.

    Implementation notes
    --------------------
    * Uses numpy arrays throughout (no per-row pandas access) for speed.
    * Hysteresis is enforced by tracking the last exhaustion date and refusing
      a new onset within hysteresis_gap_days of it.
    * The state machine is a simple FSM — no hidden state accumulation.
    * Exits via exhaustion OR series end (open episodes are emitted with
      exhausted_date=None and duration = sessions from onset to last date).
    """
    c = {**EPISODE_CFG, **(cfg or {})}

    smooth_days = c["accel_z_smooth_days"]
    onset_thresh = c["onset_accel_z_threshold"]
    onset_pos_n = c["onset_positive_days_in_5"]
    confirmed_n = c["confirmed_consecutive_onset_days"]
    confirmed_coh_thresh = c["confirmed_cohesion_chg_threshold"]
    undeniable_rs = c["undeniable_rs_in_direction"]
    undeniable_breadth = c["undeniable_breadth_threshold"]
    mature_rs_pctile = c["mature_rs_pctile_threshold"]
    mature_fade_thresh = c["mature_fading_accel_z_threshold"]
    exhaust_counter_thresh = c["exhausted_accel_z_counter_threshold"]
    exhaust_n = c["exhausted_days_in_5"]
    min_dur = c["min_duration_before_exhaustion"]
    hyst_gap = c["hysteresis_gap_days"]

    if node_series.empty or len(node_series) < smooth_days + confirmed_n + 5:
        return []

    dates = node_series.index.values  # numpy datetime64 array
    n = len(dates)

    # Extract required arrays (np.nan where column absent)
    def _col(name: str) -> np.ndarray:
        if name in node_series.columns:
            return node_series[name].to_numpy(dtype=float)
        return np.full(n, np.nan)

    accel_z_raw = _col("accel_z")
    rs_arr = _col("rs")
    vel_1w = _col("vel_1w")
    vel_3m = _col("vel_3m")
    cohesion_chg = _col("cohesion_chg")
    breadth_50 = _col("breadth_50")
    vix_pctile = _col("vix_pctile")
    tlt_ret_10d = _col("tlt_ret_10d")
    spy_above_200d = _col("spy_above_200d")

    # Pre-compute smoothed accel_z
    accel_z_5d = _smooth_accel_z(accel_z_raw, smooth_days)

    # rs_mom proxy: vel_1w - vel_3m
    rs_mom = vel_1w - vel_3m

    episodes: list[dict] = []
    state = _STATE_FLAT
    direction: str | None = None
    onset_idx: int | None = None
    confirmed_idx: int | None = None
    undeniable_idx: int | None = None
    consecutive_onset = 0
    last_exhaustion_idx: int = -hyst_gap - 1  # allows onset from idx=0

    ep_counter = 0  # monotonic counter for episode_id generation

    def _emit(exhausted_idx: int | None) -> dict:
        """Snapshot the current episode into a dict."""
        nonlocal ep_counter
        ep_counter += 1

        oi = onset_idx  # assured non-None when _emit is called
        # duration: from onset to exhausted (or series end)
        end_i = exhausted_idx if exhausted_idx is not None else n - 1
        duration = int(end_i - oi + 1)

        # peak |accel_z| during episode
        ep_accel = accel_z_raw[oi: end_i + 1]
        peak_accel_z = float(np.nanmax(np.abs(ep_accel))) if len(ep_accel) > 0 and not np.all(np.isnan(ep_accel)) else np.nan

        # Regime at onset
        v_vix = vix_pctile[oi] if not np.isnan(vix_pctile[oi]) else None
        v_tlt = tlt_ret_10d[oi]
        tlt_sign = int(np.sign(v_tlt)) if not np.isnan(v_tlt) else None
        v_spy = spy_above_200d[oi] if not np.isnan(spy_above_200d[oi]) else None

        return {
            "episode_id": f"{node}::{direction}::{str(dates[oi])[:10]}::{ep_counter}",
            "node": node,
            "direction": direction,
            "onset_date": pd.Timestamp(dates[oi]),
            "confirmed_date": pd.Timestamp(dates[confirmed_idx]) if confirmed_idx is not None else None,
            "undeniable_date": pd.Timestamp(dates[undeniable_idx]) if undeniable_idx is not None else None,
            "exhausted_date": pd.Timestamp(dates[exhausted_idx]) if exhausted_idx is not None else None,
            "duration": duration,
            "peak_accel_z": peak_accel_z,
            "breadth_at_onset": float(breadth_50[oi]) if not np.isnan(breadth_50[oi]) else None,
            "cohesion_at_onset": float(cohesion_chg[oi]) if not np.isnan(cohesion_chg[oi]) else None,
            "regime_vix_pctile": float(v_vix) if v_vix is not None else None,
            "regime_tlt_sign": tlt_sign,
            "regime_spy_above_200d": float(v_spy) if v_spy is not None else None,
            "two_sided": False,
            "paired_episode_id": None,
            "survivorship_flagged": False,   # set by caller for Tier-M
        }

    def _check_onset(i: int, sign: int) -> bool:
        """Test all onset conditions for direction sign (+1=IN, -1=OUT)."""
        # 1. Smoothed accel_z threshold
        az5 = accel_z_5d[i]
        if np.isnan(az5):
            return False
        threshold = onset_thresh if sign > 0 else -onset_thresh
        if sign > 0 and az5 < threshold:
            return False
        if sign < 0 and az5 > threshold:
            return False

        # 2. Majority of last 5 raw accel_z in the right direction (> 0 for IN, < 0 for OUT)
        pos_count = _positive_days_in_last_n(accel_z_raw, i, 5)
        if sign > 0 and pos_count < onset_pos_n:
            return False
        if sign < 0 and (5 - pos_count) < onset_pos_n:
            return False

        # 3. RS momentum proxy in right direction
        if c["onset_rs_mom_positive"]:
            rsmom = rs_mom[i]
            if np.isnan(rsmom):
                return False
            if sign > 0 and rsmom <= 0:
                return False
            if sign < 0 and rsmom >= 0:
                return False

        return True

    def _check_exhaustion(i: int, onset_i: int, dir_sign: int) -> bool:
        """Test exhaustion conditions."""
        if (i - onset_i) < min_dur:
            return False
        az5 = accel_z_5d[i]
        if np.isnan(az5):
            return False
        # Counter-directional: for IN, exhaustion fires when accel_z_5d < -0.5
        counter_thresh = exhaust_counter_thresh  # negative
        if dir_sign > 0 and az5 > counter_thresh:  # IN: az5 not < counter_thresh (negative)
            return False
        if dir_sign < 0 and az5 < -counter_thresh:  # OUT: az5 not > +|counter_thresh|
            return False

        # Confirm: ≥3 of last 5 raw accel_z days cross against direction
        cnt = _against_count_in_last_n(accel_z_raw, i, 5, direction, counter_thresh)
        return cnt >= exhaust_n

    for i in range(n):
        # ---- FLAT: look for onset ----
        if state == _STATE_FLAT:
            # Hysteresis gap: refuse new onset too soon after last exhaustion
            if (i - last_exhaustion_idx) <= hyst_gap:
                continue

            # Try IN onset first, then OUT
            found = False
            for sign in (+1, -1):
                if _check_onset(i, sign):
                    state = _STATE_ONSET
                    direction = _DIR_IN if sign > 0 else _DIR_OUT
                    onset_idx = i
                    confirmed_idx = None
                    undeniable_idx = None
                    consecutive_onset = 1
                    found = True
                    break
            continue  # move to next day regardless

        dir_sign = +1 if direction == _DIR_IN else -1

        # ---- ONSET: accumulate consecutive sessions; check confirmation/exhaustion ----
        if state == _STATE_ONSET:
            # Check if current day still satisfies onset conditions
            onset_still_holds = _check_onset(i, dir_sign)

            if onset_still_holds:
                consecutive_onset += 1
            else:
                # Onset broken before confirmation → reset to flat
                last_exhaustion_idx = i  # treat as mini-exhaust for hysteresis
                state = _STATE_FLAT
                direction = None
                onset_idx = None
                consecutive_onset = 0
                continue

            # Check confirmation (A: consecutive days)
            if consecutive_onset >= confirmed_n and confirmed_idx is None:
                confirmed_idx = i

            # Check confirmation (B: cohesion_chg spike)
            if confirmed_idx is None:
                cc_val = cohesion_chg[i]
                if not np.isnan(cc_val):
                    cc_signed = cc_val if dir_sign > 0 else -cc_val
                    if cc_signed >= confirmed_coh_thresh:
                        confirmed_idx = i

            if confirmed_idx is not None:
                state = _STATE_ACCELERATING

            # Exhaustion check (even in onset state, though min_dur usually prevents it)
            if _check_exhaustion(i, onset_idx, dir_sign):
                ep = _emit(i)
                episodes.append(ep)
                state = _STATE_FLAT
                last_exhaustion_idx = i
                direction = None
                onset_idx = None
                confirmed_idx = None
                undeniable_idx = None
                consecutive_onset = 0
            continue

        # ---- ACCELERATING (confirmed): check undeniable + mature + exhaustion ----
        if state == _STATE_ACCELERATING:
            # Check undeniable tier
            if undeniable_idx is None:
                rs_flip = False
                if undeniable_rs:
                    rs_val = rs_arr[i]
                    if not np.isnan(rs_val):
                        rs_flip = (rs_val > 0) if dir_sign > 0 else (rs_val < 0)

                breadth_cross = False
                b50 = breadth_50[i]
                if not np.isnan(b50):
                    if dir_sign > 0:
                        breadth_cross = b50 > undeniable_breadth
                    else:
                        breadth_cross = b50 < (1.0 - undeniable_breadth)
                else:
                    breadth_cross = True  # degrade: skip breadth leg when absent

                if rs_flip and breadth_cross:
                    undeniable_idx = i

            # Check mature: rs extended AND accel_z_5d fading toward 0
            az5 = accel_z_5d[i]
            rs_pctile = _rs_pctile_252d(rs_arr, i)
            if (
                rs_pctile is not None
                and rs_pctile >= mature_rs_pctile
                and not np.isnan(az5)
                and abs(az5) <= mature_fade_thresh
            ):
                state = _STATE_MATURE
                continue  # fall through to MATURE on next iteration

            # Exhaustion check
            if _check_exhaustion(i, onset_idx, dir_sign):
                ep = _emit(i)
                episodes.append(ep)
                state = _STATE_FLAT
                last_exhaustion_idx = i
                direction = None
                onset_idx = None
                confirmed_idx = None
                undeniable_idx = None
                consecutive_onset = 0
            continue

        # ---- MATURE: watch for exhaustion ----
        if state == _STATE_MATURE:
            # Undeniable check still runs in mature state if not yet triggered
            if undeniable_idx is None:
                rs_val = rs_arr[i]
                b50 = breadth_50[i]
                rs_flip = (not np.isnan(rs_val)) and ((rs_val > 0 if dir_sign > 0 else rs_val < 0))
                if np.isnan(b50):
                    breadth_cross = True
                else:
                    breadth_cross = (b50 > undeniable_breadth) if dir_sign > 0 else (b50 < 1.0 - undeniable_breadth)
                if rs_flip and breadth_cross:
                    undeniable_idx = i

            if _check_exhaustion(i, onset_idx, dir_sign):
                ep = _emit(i)
                episodes.append(ep)
                state = _STATE_FLAT
                last_exhaustion_idx = i
                direction = None
                onset_idx = None
                confirmed_idx = None
                undeniable_idx = None
                consecutive_onset = 0
            continue

    # --- Emit open (unexhausted) episodes at series end ---
    if state in (_STATE_ONSET, _STATE_ACCELERATING, _STATE_MATURE) and onset_idx is not None:
        ep = _emit(None)   # exhausted_date = None
        episodes.append(ep)

    return episodes


# ---------------------------------------------------------------------------
# Two-sided pairing
# ---------------------------------------------------------------------------

def _pair_episodes(
    episodes_df: pd.DataFrame,
    rotation_groups: dict | None,
    cfg: dict[str, Any],
    panel_last_date: pd.Timestamp | None = None,
) -> pd.DataFrame:
    """Mark opposite-direction episode overlaps as two-sided pairs.

    Strategy when rotation_groups is present (P2a):
      For each IN episode, find OUT episodes in any *other* node belonging to
      the same rotation group, overlapping ≥ two_sided_min_overlap_sessions.
      Prefer the OUT episode with the highest |combined peak_accel_z|.

    Strategy when rotation_groups is absent (graceful degrade):
      For each IN episode, search all OUT episodes in the SAME panel
      (any node), overlapping ≥ threshold.  Rank by |combined peak_accel_z|.

    Pairing is symmetric: each episode is paired at most once.

    Parameters
    ----------
    panel_last_date : pd.Timestamp | None
        The last date in the source panel.  Used as the end-date for open
        (unexhausted) episodes when computing overlap.  When None, falls back
        to the latest exhausted_date in the episode set (less accurate for
        panels where most episodes are open).
    """
    min_overlap = cfg["two_sided_min_overlap_sessions"]

    if episodes_df.empty:
        episodes_df["two_sided"] = False
        episodes_df["paired_episode_id"] = None
        return episodes_df

    df = episodes_df.copy()
    df["two_sided"] = df["two_sided"].astype(bool)

    # Determine the sentinel end-date for open episodes:
    # prefer panel_last_date; fall back to the latest exhausted_date; then
    # use the latest onset_date + 90 days as a broad upper bound.
    if panel_last_date is not None:
        _open_end = panel_last_date
    else:
        exhausted_dates = df["exhausted_date"].dropna()
        if not exhausted_dates.empty:
            _open_end = exhausted_dates.max()
        else:
            _open_end = df["onset_date"].max() + pd.Timedelta(days=90)

    # Determine group mapping for each node
    node_to_group: dict[str, str] = {}
    if rotation_groups and isinstance(rotation_groups, dict):
        for group_id, members in rotation_groups.items():
            if isinstance(members, list):
                for m in members:
                    node_name = m if isinstance(m, str) else m.get("node", "")
                    if node_name:
                        node_to_group[node_name] = group_id

    in_eps = df[df["direction"] == _DIR_IN].copy()
    out_eps = df[df["direction"] == _DIR_OUT].copy()

    paired_ids: set[str] = set()

    for in_row in in_eps.itertuples():
        if in_row.episode_id in paired_ids:
            continue

        # Date range of this IN episode; open episodes end at _open_end
        in_start = in_row.onset_date
        _exhausted = in_row.exhausted_date
        in_end = _exhausted if (_exhausted is not None and not pd.isnull(_exhausted)) else _open_end

        # Candidate OUT episodes: different node, not yet paired
        candidates = out_eps[
            (out_eps["node"] != in_row.node)
            & (~out_eps["episode_id"].isin(paired_ids))
        ]

        # Filter by group membership if groups available
        if node_to_group:
            in_group = node_to_group.get(in_row.node)
            if in_group:
                same_group_nodes = {n for n, g in node_to_group.items() if g == in_group}
                candidates = candidates[candidates["node"].isin(same_group_nodes)]

        if candidates.empty:
            continue

        # Compute overlap (calendar days as a proxy for trading sessions;
        # accurate enough for the ≥5 session threshold when episodes are days wide)
        def _overlap(out_row, _in_start=in_start, _in_end=in_end, _oe=_open_end) -> int:
            out_start = out_row["onset_date"]
            out_exhausted = out_row["exhausted_date"]
            out_end = out_exhausted if (out_exhausted is not None and not pd.isnull(out_exhausted)) else _oe
            overlap_start = max(_in_start, out_start)
            overlap_end = min(_in_end, out_end)
            if overlap_end >= overlap_start:
                # Approximate as calendar days + 1 (conservative: trading days ~5/7)
                delta = (overlap_end - overlap_start).days + 1
                return delta
            return 0

        candidates = candidates.copy()
        candidates["_overlap"] = candidates.apply(_overlap, axis=1)
        valid = candidates[candidates["_overlap"] >= min_overlap]
        if valid.empty:
            continue

        # Pick best partner: highest |combined peak_accel_z|
        combined = valid["peak_accel_z"].fillna(0) + in_row.peak_accel_z
        best_idx = combined.abs().idxmax()
        best_out = valid.loc[best_idx]

        # Mark both as paired
        df.loc[df["episode_id"] == in_row.episode_id, "two_sided"] = True
        df.loc[df["episode_id"] == in_row.episode_id, "paired_episode_id"] = best_out["episode_id"]
        df.loc[df["episode_id"] == best_out["episode_id"], "two_sided"] = True
        df.loc[df["episode_id"] == best_out["episode_id"], "paired_episode_id"] = in_row.episode_id

        paired_ids.add(in_row.episode_id)
        paired_ids.add(best_out["episode_id"])

    return df


# ---------------------------------------------------------------------------
# Outcome columns (LOOK-AHEAD DISCIPLINE enforced here)
# ---------------------------------------------------------------------------

def _add_outcome_columns(
    episodes_df: pd.DataFrame,
    panel: pd.DataFrame,
    cfg: dict[str, Any],
) -> pd.DataFrame:
    """Compute forward RS-change outcomes anchored at each detection tier date.

    LOOK-AHEAD DISCIPLINE:
    * Outcomes are computed from forward panel data ONLY.
    * The detection dates (onset, confirmed, undeniable) are determined SOLELY
      from data ≤ that date — this is enforced by the state machine.
    * An episode whose +h horizon window extends past the panel's last available
      date receives outcome=NaN + outcome_mature=False.  NO partial windows.
    * This function ONLY reads panel[date > detection_date] — it does not read
      any feature that drove detection.

    The outcome column set is clearly named 'outcome_*' so that no detection
    logic can accidentally import them.
    """
    horizons = cfg["outcome_horizons"]
    df = episodes_df.copy()

    # Panel last date per node (for maturity check)
    if panel.empty:
        for h in horizons:
            df[f"outcome_rs_{h}d"] = np.nan
            df[f"outcome_rs_{h}d_confirmed"] = np.nan
            df[f"outcome_rs_{h}d_undeniable"] = np.nan
            df[f"outcome_mature_{h}d"] = False
        return df

    # Build a lookup: node → sorted rs Series indexed by date
    node_rs: dict[str, pd.Series] = {}
    if isinstance(panel.index, pd.MultiIndex):
        for node in panel.index.get_level_values("node").unique():
            node_rs[node] = panel.xs(node, level="node")["rs"].sort_index()
    else:
        # Flat index — single-node panel
        node_rs[""] = panel["rs"].sort_index() if "rs" in panel.columns else pd.Series(dtype=float)

    def _fwd_rs(node: str, anchor_date, h: int) -> tuple[float, bool]:
        """Return (rs_change, outcome_mature).

        rs_change = cumulative RS over the next h sessions from anchor_date.
        outcome_mature = True iff the full window is within the panel span.
        """
        if anchor_date is None or pd.isnull(anchor_date):
            return np.nan, False
        rs_node = node_rs.get(node)
        if rs_node is None or rs_node.empty:
            return np.nan, False

        # Locate anchor position in the sorted series
        future = rs_node[rs_node.index > anchor_date]
        if len(future) < h:
            return np.nan, False  # window extends past last date

        # Forward cumulative RS over h sessions
        window = future.iloc[:h]
        cum_rs = (1 + window).prod() - 1
        return float(cum_rs), True

    for h in horizons:
        onset_vals: list[float] = []
        onset_mature: list[bool] = []
        confirmed_vals: list[float] = []
        confirmed_mature: list[bool] = []
        undeniable_vals: list[float] = []
        undeniable_mature: list[bool] = []

        for _, row in df.iterrows():
            node = row["node"]

            v, m = _fwd_rs(node, row["onset_date"], h)
            onset_vals.append(v)
            onset_mature.append(m)

            v, m = _fwd_rs(node, row.get("confirmed_date"), h)
            confirmed_vals.append(v)
            confirmed_mature.append(m)

            v, m = _fwd_rs(node, row.get("undeniable_date"), h)
            undeniable_vals.append(v)
            undeniable_mature.append(m)

        df[f"outcome_rs_{h}d"] = onset_vals
        df[f"outcome_rs_{h}d_confirmed"] = confirmed_vals
        df[f"outcome_rs_{h}d_undeniable"] = undeniable_vals
        # outcome_mature is True iff onset-anchored window fits: use onset window
        df[f"outcome_mature_{h}d"] = onset_mature

    return df


# ---------------------------------------------------------------------------
# Main builder
# ---------------------------------------------------------------------------

def build_episodes(
    panel: pd.DataFrame,
    rotation_groups: dict | None = None,
    tier: str = "s",
    cfg: dict[str, Any] | None = None,
) -> pd.DataFrame:
    """Run the episode state machine over every node in panel.

    Parameters
    ----------
    panel : pd.DataFrame
        MultiIndex (node, date) Oracle rotation panel from panel.py.
        Tier S or Tier M — caller passes which.
    rotation_groups : dict | None
        Parsed data/oracle/rotation_groups.json from P2a (optional).
        When None, two-sided pairing falls back to same-panel overlap.
    tier : str
        "s" = survivorship-clean (Tier S), "m" = survivorship-flagged (Tier M).
        Controls the survivorship_flagged field on each episode.
    cfg : dict | None
        Override EPISODE_CFG keys.

    Returns
    -------
    pd.DataFrame
        One row per episode with columns from _EPISODE_COLS + outcome columns.
        Sorted by onset_date.  Empty DataFrame if no episodes detected.

    Notes
    -----
    * The state machine is run per-node over the node's full history.
    * Outcome columns are added in a SEPARATE pass after all episodes are
      detected to enforce the no-lookahead invariant: detection code can never
      accidentally branch on outcome data.
    * Two-sided pairing is also a post-detection pass.
    """
    c = {**EPISODE_CFG, **(cfg or {})}
    survivorship_flagged = tier == "m"

    if panel.empty:
        return pd.DataFrame(columns=_EPISODE_COLS)

    all_episodes: list[dict] = []

    nodes = panel.index.get_level_values("node").unique()
    for node in nodes:
        try:
            node_series = panel.xs(node, level="node").sort_index()
        except KeyError:
            continue

        eps = run_state_machine(node_series, node=str(node), cfg=c)

        # Tag survivorship on Tier-M nodes
        for ep in eps:
            ep["survivorship_flagged"] = survivorship_flagged

        all_episodes.extend(eps)

    if not all_episodes:
        return pd.DataFrame(columns=_EPISODE_COLS)

    df = pd.DataFrame(all_episodes)

    # Ensure all expected columns are present (degrade-never-raise)
    for col in _EPISODE_COLS:
        if col not in df.columns:
            df[col] = None

    df = df.sort_values("onset_date").reset_index(drop=True)

    # Compute the panel's last date for open-episode pairing
    panel_last_date: pd.Timestamp | None = None
    if isinstance(panel.index, pd.MultiIndex):
        dates = panel.index.get_level_values("date")
        if len(dates) > 0:
            panel_last_date = dates.max()
    elif hasattr(panel.index, "max"):
        panel_last_date = panel.index.max()

    # ---- Pass 1: Two-sided pairing (no panel data needed) ----
    df = _pair_episodes(df, rotation_groups, c, panel_last_date=panel_last_date)

    # ---- Pass 2: Outcome columns (forward-only, clearly separated) ----
    df = _add_outcome_columns(df, panel, c)

    return df
