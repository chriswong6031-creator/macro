"""Oracle tape-onset tier — TAPE-ONSET (unconfirmed) display flag.

REGISTRATION
------------
research/ORACLE_TAPE_ONSET_TIER_REGISTRATION.md — MERGED before any result is
computed (Constitution §I.3).  This module implements exactly the construction
frozen in §2 of that registration.  Truth-in-labeling law: this docstring
describes what the code executes, not a mechanism the author wishes it executed.

WHAT
----
Per Oracle panel node, on the latest panel row (rotate-IN direction only, v1):

    tape_onset(t) := raw accel_z(t) >= 1.0            # same threshold, UNSMOOTHED
                     AND vel_1w(t) > vel_3m(t)         # same direction check episodes use
                     AND no active same-direction episode at any tier for this node

The flag is NOT part of the episode state machine — episodes.py is untouched.
The flag lives BESIDE the episode column, never inside it.

PAYLOAD FIELDS (additive, tolerant-reader, banned-substring-checked)
--------------------------------------------------------------------
tape_onset_unconfirmed : bool
    True when all three conditions above are met on the latest panel date.

tape_onset_stats : dict
    n_flags          — count of historical tape_onset days
    p_onset_5d       — fraction followed by accel_z_5d >= 1.0 within 5 sessions
    p_confirmed_10d  — fraction followed by a CONFIRMED episode within 10 sessions
    false_positive_5d — fraction with NO smoothed onset within 5 sessions (= 1 - p_onset_5d)
    window_start     — ISO date of earliest panel row in the count
    window_end       — ISO date of latest panel row in the count

PRINTED RATES
-------------
Computed nightly from panel history (never hardcoded, R4 binding).
accel_z is price-derived and reaches the full Tier-S panel span (1998→).

DISPLAY TIER / AUTHORITY BLOCK
-------------------------------
This artifact is DISPLAY/CONTEXT tier.  No consumer may rank, gate, size, or
escalate on it (Constitution §II, §III; FT-R2).  Every render must carry the
"TAPE-ONSET (unconfirmed)" label in both EN and ZH.

FORWARD LEDGER
--------------
Every tape_onset flag appends to data/oracle/tape_onset_ledger.jsonl
(trial-ledger convention, Constitution §I.2 — mining is legal because it is
counted; accrual from ship date only; no backfilled gradeable claims).
The ledger append helper follows the same keep-first pattern as the turn-desk
ledger and forward_ledger in oracle_nightly.py.

EVALUATION CLOCK: 2026-10-09 (joint with FTR grading window; §4 of registration).
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

import numpy as np
import pandas as pd

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants (frozen v1 per registration §2)
# ---------------------------------------------------------------------------

# Raw accel_z threshold — same scalar as onset_accel_z_threshold in EPISODE_CFG,
# deliberately UNSMOOTHED (the distinguishing feature of this tier vs the episode onset tier).
TAPE_ONSET_RAW_ACCEL_Z_THRESHOLD: float = 1.0

# vel_1w > vel_3m: direction check matching episodes.py onset_rs_mom_positive gate.
# (vel_1w - vel_3m) > 0 ≡ the weekly velocity exceeds the quarterly velocity in magnitude.

# Smoothing days for p_onset_5d historical rate computation (MUST match episodes.py accel_z_smooth_days).
_ACCEL_Z_SMOOTH_DAYS: int = 5

# Forward-look windows for printed rate computation (registration §3).
_P_ONSET_WINDOW_SESSIONS: int = 5    # "reach smoothed onset in 5 sessions"
_P_CONFIRMED_WINDOW_SESSIONS: int = 10  # "reach a CONFIRMED episode in 10 sessions"

# Banned implication key substrings (Constitution §III / contract.py).
_BANNED_KEY_SUBS = frozenset({"forecast", "predicted", "target", "expected_return"})


# ---------------------------------------------------------------------------
# Construction predicate (pure function — testable in isolation)
# ---------------------------------------------------------------------------

def is_tape_onset(
    accel_z_raw: float,
    vel_1w: float,
    vel_3m: float,
    has_active_same_direction_episode: bool,
) -> bool:
    """Return True when all tape_onset conditions are met (rotate-IN direction).

    Parameters
    ----------
    accel_z_raw               : raw (unsmoothed) accel_z value for the node today
    vel_1w                    : 1-week velocity for the node today
    vel_3m                    : 3-month velocity for the node today
    has_active_same_direction_episode : True if the node already has an active
                                       rotate-IN episode at any tier today

    Returns
    -------
    bool : True iff all three registration §2 conditions are satisfied.

    Registration §2 conditions (verbatim):
        1. raw accel_z(t) >= 1.0             (unsmoothed, threshold = EPISODE_CFG onset threshold)
        2. vel_1w(t) > vel_3m(t)             (same direction check episodes use)
        3. no active same-direction episode at any tier for this node
    """
    if np.isnan(accel_z_raw) or np.isnan(vel_1w) or np.isnan(vel_3m):
        return False
    if accel_z_raw < TAPE_ONSET_RAW_ACCEL_Z_THRESHOLD:
        return False
    if vel_1w <= vel_3m:
        return False
    if has_active_same_direction_episode:
        return False
    return True


# ---------------------------------------------------------------------------
# Historical rate computation (registration §3, printed from data)
# ---------------------------------------------------------------------------

def _smooth_accel_z_series(accel_z: pd.Series, days: int = _ACCEL_Z_SMOOTH_DAYS) -> pd.Series:
    """Trailing mean of accel_z (same smoothing as episodes.py _smooth_accel_z).

    Uses pandas rolling with min_periods=days to match the numpy implementation
    in episodes.py: returns NaN until the window is fully filled.
    """
    return accel_z.rolling(days, min_periods=days).mean()


def compute_tape_onset_stats(
    node_panel: pd.DataFrame,
    episodes_df: pd.DataFrame | None,
    node: str,
) -> dict[str, Any]:
    """Compute historical printed rates for tape_onset flags on a single node.

    Parameters
    ----------
    node_panel   : panel rows for this node, indexed by date, columns include
                   accel_z, vel_1w, vel_3m.
    episodes_df  : full episodes DataFrame with columns node, direction,
                   onset_date, confirmed_date, exhausted_date.  May be None
                   (degrades to episode-suppression-unknown → rates based on
                   accel_z_5d only).
    node         : node identifier (for episode lookup).

    Returns
    -------
    dict with keys: n_flags, p_onset_5d, p_confirmed_10d, false_positive_5d,
                    window_start, window_end.
    All numeric values are float or None (never hardcoded; None when insufficient data).

    CAUSAL invariant: outcomes are evaluated on forward data only.
    """
    _empty: dict[str, Any] = {
        "n_flags": 0,
        "p_onset_5d": None,
        "p_confirmed_10d": None,
        "false_positive_5d": None,
        "window_start": None,
        "window_end": None,
    }

    if node_panel.empty:
        return _empty

    required_cols = {"accel_z", "vel_1w", "vel_3m"}
    if not required_cols.issubset(set(node_panel.columns)):
        log.warning("tape_onset_stats: node %s missing columns %s", node,
                    required_cols - set(node_panel.columns))
        return _empty

    df = node_panel.sort_index().copy()
    dates = df.index

    # Smoothed accel_z for outcome measurement (Constitution §IV, registration §3)
    accel_z_5d = _smooth_accel_z_series(df["accel_z"])

    # Build per-day active-IN episode mask from episodes_df
    # (suppression: tape_onset cannot fire when a same-direction episode is already active)
    active_in_mask = pd.Series(False, index=dates, dtype=bool)
    if episodes_df is not None and not episodes_df.empty:
        node_eps = episodes_df[
            (episodes_df["node"] == node) & (episodes_df["direction"] == "in")
        ]
        for _, ep in node_eps.iterrows():
            onset_dt = ep.get("onset_date")
            exhaust_dt = ep.get("exhausted_date")
            if onset_dt is None or pd.isnull(onset_dt):
                continue
            # Episode is active from onset_date to exhausted_date (inclusive), or open
            start = pd.Timestamp(onset_dt)
            end = pd.Timestamp(exhaust_dt) if (exhaust_dt is not None and not pd.isnull(exhaust_dt)) else dates[-1]
            mask_range = (dates >= start) & (dates <= end)
            active_in_mask = active_in_mask | mask_range

    # Identify historical tape_onset days
    az_raw = df["accel_z"].to_numpy(dtype=float)
    vel_1w = df["vel_1w"].to_numpy(dtype=float)
    vel_3m = df["vel_3m"].to_numpy(dtype=float)
    active_in_arr = active_in_mask.to_numpy(dtype=bool)

    flag_indices: list[int] = []
    for i in range(len(dates)):
        if is_tape_onset(
            accel_z_raw=az_raw[i],
            vel_1w=vel_1w[i],
            vel_3m=vel_3m[i],
            has_active_same_direction_episode=active_in_arr[i],
        ):
            flag_indices.append(i)

    n_flags = len(flag_indices)
    if n_flags == 0:
        return {
            **_empty,
            "n_flags": 0,
            "window_start": dates[0].strftime("%Y-%m-%d") if len(dates) else None,
            "window_end": dates[-1].strftime("%Y-%m-%d") if len(dates) else None,
        }

    # Compute printed rates (forward-looking, CAUSAL — never uses future data at flag time)
    az5_arr = accel_z_5d.to_numpy(dtype=float)

    # p_onset_5d: fraction of flag days where accel_z_5d >= 1.0 within the next 5 sessions
    onset_5d_hits = 0
    for i in flag_indices:
        # Look at the NEXT 5 sessions after the flag (exclusive of the flag day itself)
        future_slice = az5_arr[i + 1: i + 1 + _P_ONSET_WINDOW_SESSIONS]
        if len(future_slice) == 0:
            continue  # Skip flags at the very end of the panel (no forward data)
        if np.any(~np.isnan(future_slice) & (future_slice >= TAPE_ONSET_RAW_ACCEL_Z_THRESHOLD)):
            onset_5d_hits += 1

    # Denominator: flags with at least 1 forward session of data (exclude tail flags)
    flags_with_fwd = sum(
        1 for i in flag_indices if (i + 1 + _P_ONSET_WINDOW_SESSIONS) <= len(dates)
    )

    p_onset_5d: float | None = None
    if flags_with_fwd > 0:
        p_onset_5d = round(onset_5d_hits / flags_with_fwd, 4)
    false_positive_5d: float | None = None
    if p_onset_5d is not None:
        false_positive_5d = round(1.0 - p_onset_5d, 4)

    # p_confirmed_10d: fraction followed by a CONFIRMED episode within 10 sessions
    # A CONFIRMED episode is identified by: node has an episode with confirmed_date
    # in [flag_date+1, flag_date+10].
    confirmed_10d_hits = 0
    flags_with_fwd10 = 0
    if episodes_df is not None and not episodes_df.empty:
        node_confirmed_eps = episodes_df[
            (episodes_df["node"] == node)
            & (episodes_df["direction"] == "in")
            & episodes_df["confirmed_date"].notna()
        ]
        confirmed_dates = set()
        for _, ep in node_confirmed_eps.iterrows():
            cd = ep.get("confirmed_date")
            if cd is not None and not pd.isnull(cd):
                confirmed_dates.add(pd.Timestamp(cd))

        for i in flag_indices:
            # Need at least 10 forward sessions of panel data
            if (i + 1 + _P_CONFIRMED_WINDOW_SESSIONS) > len(dates):
                continue
            flags_with_fwd10 += 1
            flag_date = dates[i]
            window_end_date = dates[min(i + _P_CONFIRMED_WINDOW_SESSIONS, len(dates) - 1)]
            for cd in confirmed_dates:
                if flag_date < cd <= window_end_date:
                    confirmed_10d_hits += 1
                    break

    p_confirmed_10d: float | None = None
    if flags_with_fwd10 > 0:
        p_confirmed_10d = round(confirmed_10d_hits / flags_with_fwd10, 4)

    return {
        "n_flags": n_flags,
        "p_onset_5d": p_onset_5d,
        "p_confirmed_10d": p_confirmed_10d,
        "false_positive_5d": false_positive_5d,
        "window_start": dates[0].strftime("%Y-%m-%d") if len(dates) else None,
        "window_end": dates[-1].strftime("%Y-%m-%d") if len(dates) else None,
    }


# ---------------------------------------------------------------------------
# Per-node tape-onset payload (additive, tolerant-reader)
# ---------------------------------------------------------------------------

def compute_tape_onset_payload(
    panel: pd.DataFrame,
    episodes_df: pd.DataFrame | None,
) -> dict[str, dict]:
    """Compute tape_onset_unconfirmed and tape_onset_stats for every node in panel.

    Parameters
    ----------
    panel       : MultiIndex (node, date) Oracle panel (Tier S or M).
    episodes_df : episode catalog from build_oracle_episodes (may be None).

    Returns
    -------
    dict node_id → {"tape_onset_unconfirmed": bool, "tape_onset_stats": {...}}

    Only rotate-IN direction evaluated in v1 (per registration §2).
    """
    if panel.empty:
        return {}

    result: dict[str, dict] = {}
    nodes = panel.index.get_level_values("node").unique()

    for node in nodes:
        try:
            node_panel = panel.xs(node, level="node").sort_index()
        except KeyError:
            continue

        if node_panel.empty:
            continue

        # Latest row
        latest_date = node_panel.index[-1]
        latest = node_panel.iloc[-1]

        # --- Active-IN episode check for latest date ---
        has_active_in = False
        if episodes_df is not None and not episodes_df.empty:
            node_in_eps = episodes_df[
                (episodes_df["node"] == node) & (episodes_df["direction"] == "in")
            ]
            for _, ep in node_in_eps.iterrows():
                onset_dt = ep.get("onset_date")
                exhaust_dt = ep.get("exhausted_date")
                if onset_dt is None or pd.isnull(onset_dt):
                    continue
                start = pd.Timestamp(onset_dt)
                # Open episode (exhausted_date is None/NaT) is still active
                end = (
                    pd.Timestamp(exhaust_dt)
                    if (exhaust_dt is not None and not pd.isnull(exhaust_dt))
                    else latest_date + pd.Timedelta(days=1)  # treat as still-open
                )
                if start <= latest_date <= end:
                    has_active_in = True
                    break

        # --- tape_onset predicate ---
        flag = is_tape_onset(
            accel_z_raw=float(latest.get("accel_z", np.nan)),
            vel_1w=float(latest.get("vel_1w", np.nan)),
            vel_3m=float(latest.get("vel_3m", np.nan)),
            has_active_same_direction_episode=has_active_in,
        )

        # --- Historical stats ---
        stats = compute_tape_onset_stats(node_panel, episodes_df, str(node))

        result[str(node)] = {
            "tape_onset_unconfirmed": flag,
            "tape_onset_stats": stats,
        }

    return result


# ---------------------------------------------------------------------------
# Banned-key check (Constitution §III / contract.py mirrored)
# ---------------------------------------------------------------------------

def check_banned_keys(obj: Any, path: str = "") -> list[str]:
    """Recursively check for banned-implication key substrings.

    Returns a list of error strings (empty = clean).
    Mirrors the logic in engine/oracle/contract.py::_check_banned_keys.
    """
    errors: list[str] = []
    if isinstance(obj, dict):
        for k, v in obj.items():
            k_lower = k.lower()
            for banned in _BANNED_KEY_SUBS:
                if banned in k_lower:
                    full_path = f"{path}.{k}" if path else k
                    errors.append(
                        f"BANNED key '{full_path}' contains '{banned}' — "
                        "remove or rename (Constitution §III)"
                    )
            child_path = f"{path}.{k}" if path else k
            errors.extend(check_banned_keys(v, child_path))
    elif isinstance(obj, list):
        for i, item in enumerate(obj):
            errors.extend(check_banned_keys(item, f"{path}[{i}]"))
    return errors


# ---------------------------------------------------------------------------
# Trial-ledger append (registration §4, forward accrual from ship date)
# ---------------------------------------------------------------------------

def append_tape_onset_ledger(
    tape_onset_payload: dict[str, dict],
    asof: str,
    ledger_path: "Path",
    *,
    dry_run: bool = False,
) -> int:
    """Append new tape_onset flags to data/oracle/tape_onset_ledger.jsonl.

    Keep-FIRST convention (same as forward_ledger in oracle_nightly.py):
    once a node::date key is written, subsequent nightly runs with the same key
    are silently ignored — PIT-stamped at first observation.

    Parameters
    ----------
    tape_onset_payload : output of compute_tape_onset_payload
    asof               : ISO date string of the panel's latest date
    ledger_path        : Path to data/oracle/tape_onset_ledger.jsonl
    dry_run            : if True, compute but do not write

    Returns
    -------
    int : number of new rows appended
    """
    import json as _json
    from pathlib import Path as _Path

    if not isinstance(ledger_path, _Path):
        ledger_path = _Path(ledger_path)

    # Load existing keys (node::asof)
    existing_keys: set[str] = set()
    if ledger_path.exists():
        for line in ledger_path.read_text().splitlines():
            line_s = line.strip()
            if not line_s:
                continue
            try:
                r = _json.loads(line_s)
                k = f"{r.get('node', '')}::{r.get('asof', '')}"
                existing_keys.add(k)
            except Exception:  # noqa: BLE001
                pass

    now_utc = datetime.now(timezone.utc).isoformat()
    new_rows: list[dict] = []

    for node, payload in tape_onset_payload.items():
        if not payload.get("tape_onset_unconfirmed", False):
            continue  # Only log when flag fires (Constitution §I.2 — "every flag appends a row")

        key = f"{node}::{asof}"
        if key in existing_keys:
            continue

        row: dict = {
            "key": key,
            "node": node,
            "asof": asof,
            "tape_onset_unconfirmed": True,
            "registered_at": now_utc,
            # Forward grading fields (None until matured at 2026-10-09 clock)
            "fwd_smoothed_onset_5d": None,   # did accel_z_5d >= 1.0 fire within 5 sessions?
            "fwd_confirmed_10d": None,        # did a CONFIRMED episode fire within 10 sessions?
            "outcome_mature": False,
        }

        # Banned-key check on the row itself before writing
        banned_errs = check_banned_keys(row)
        if banned_errs:
            log.error("tape_onset_ledger: banned key in row for %s: %s", node, banned_errs)
            continue

        new_rows.append(row)
        existing_keys.add(key)

    if new_rows and not dry_run:
        import json as _json
        ledger_path.parent.mkdir(parents=True, exist_ok=True)
        with open(ledger_path, "a") as fh:
            for r in new_rows:
                fh.write(_json.dumps(r, separators=(",", ":"), default=str) + "\n")

    return len(new_rows)
