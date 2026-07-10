"""china_basket_turn — washout-lifecycle state machine for CN basket EW level series (W8-R5).

Classifies each basket (22 curated + 237 THS) into one of five states based on its
equal-weight level series: FALLING / WASHED_OUT / BASING / TURNING / CONFIRMED / NONE.

DOCTRINE
--------
- DISPLAY-ONLY / CONTEXT.  Authority block: tier=display, horizon_role=context,
  may_rank/gate/size/escalate = false.
- DISCLOSURE (FT-R9 / W8-R5, VERBATIM):
  "Sector-level standalone washout-to-turn triggers printed NULL
  (Oracle P8 P-W1/S-W3; DO_NOT_REBUILD §2 'Washout × turn') — this is a
  *different construction* (washout lifecycle at basket granularity, no K-of-N legs)
  shipped display-tier as an expected-NULL forward meter (FT-R9). Not a revival claim.
  Backscan = site-artifact descriptive; forward ledger starts at ship date."
- NOT a revival of the killed sector-level washout→turn trigger. Different
  construction and granularity; registered expected-NULL per FT-R9.
- Thresholds module-level constants, v1 FROZEN descriptively — amendment-logged;
  expected-NULL forward meter (FT-R9). Recalibration clock per W8-R5.
- Nightly writer gate: ledger appended ONLY when CN_LANE == 'asia' (house law:
  nightly is the sole advancer of data/ ledgers).
- Idempotent re-runs: keep-first per (date, basket_id) in the ledger.
- DO NOT copy basket_turn_watch.py's K-of-N leg design — this is a simpler
  washout-lifecycle machine.

STATE MACHINE (HARD PRECEDENCE cascade — mirrors W8-R1 zone cascade at basket level)
---------------------------------------------------------------------------------------
States are evaluated in STRICT precedence order — first match wins:

1. FALLING (evaluated FIRST, vetoes all others):
   5d return <= FALLING_RET_THRESH  OR
   (MACD hist negative AND hist is falling — i.e. hist_d < 0)
   Rationale: a basket still in active price collapse cannot be at a bottom.

2. WASHED_OUT (requires: NOT FALLING):
   drawdown_vs_252d_high <= WASHOUT_DD_THRESH  AND  below 200d MA  AND
   decline arrested (hist_d >= WASHOUT_HIST_ARREST — hist stabilizing, not falling hard)

3. TURNING (requires: WASHED_OUT context — dd_252 qualifies regardless of current
   hist to catch lagged recoveries):
   (dd_252 <= WASHOUT_DD_THRESH) AND below_200d historically (above_200d_soft check)
   AND (stoch_reclaim >= STOCH_RECLAIM_THRESH  OR  hist_d >= TURNING_HIST_CROSS)

4. CONFIRMED (requires: TURNING held N=3+ sessions AND 20d slope positive):
   days_in_turning >= CONFIRMED_MIN_DAYS  AND  slope_20d >= CONFIRMED_SLOPE_MIN

5. BASING (requires: washout depth qualifies, not TURNING or CONFIRMED, no FALLING):
   dd_252 <= WASHOUT_DD_THRESH  AND  not falling hard

6. NONE — none of the above patterns match

Evidence tags are descriptive only (no forward verbs per house law).
"""
from __future__ import annotations

import json
import logging
import os
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Authority block (invariant — matches synapse registration)
# ---------------------------------------------------------------------------

AUTHORITY: dict[str, Any] = {
    "tier": "display",
    "horizon_role": "context",
    "may_rank": False,
    "may_gate": False,
    "may_size": False,
    "may_escalate": False,
}

# FT-R9 expected-NULL disclosure (verbatim — do not paraphrase).
DISCLOSURE = (
    "Sector-level standalone washout-to-turn triggers printed NULL "
    "(Oracle P8 P-W1/S-W3; DO_NOT_REBUILD §2 'Washout × turn') — this is a "
    "*different construction* (washout lifecycle at basket granularity, no K-of-N legs) "
    "shipped display-tier as an expected-NULL forward meter (FT-R9). Not a revival claim. "
    "Backscan = site-artifact descriptive; forward ledger starts at ship date."
)

# ---------------------------------------------------------------------------
# Thresholds — v1 FROZEN descriptively (FT-R9 / PS-R9)
# Amendment log: (date, field, old, new, reason) appended below per amendment.
# ---------------------------------------------------------------------------

# FALLING leg
FALLING_RET_THRESH: float = -0.06          # 5d return <= -6% => FALLING
# (Note: W8-R1 uses -8% for individual stocks; basket-level EW is smoother, use -6%)

# WASHED_OUT legs
WASHOUT_DD_THRESH: float = -0.25           # drawdown vs 252d high <= -25%
WASHOUT_HIST_ARREST: float = -0.005        # hist_d (day-over-day MACD hist change) >= this
                                            # (stabilizing = not aggressively falling)

# TURNING legs
STOCH_RECLAIM_THRESH: float = 0.25         # stochastic (0-1 scale) >= 0.25 = "reclaim"
TURNING_HIST_CROSS: float = 0.0            # MACD hist_d crossed to positive (>= 0)

# CONFIRMED
CONFIRMED_MIN_DAYS: int = 3                # sessions basket must hold TURNING state
CONFIRMED_SLOPE_MIN: float = 0.0           # 20d slope must be non-negative (trending up)

# MACD parameters (applied to the level series)
MACD_FAST: int = 12
MACD_SLOW: int = 26
MACD_SIGNAL: int = 9

# Stochastic window (periods, applied to the level series)
STOCH_WINDOW: int = 14


# ---------------------------------------------------------------------------
# Core series math
# ---------------------------------------------------------------------------

def _ema(series: pd.Series, span: int) -> pd.Series:
    return series.ewm(span=span, adjust=False).mean()


def _macd(levels: pd.Series) -> tuple[pd.Series, pd.Series, pd.Series]:
    """Return (macd_line, signal_line, histogram) on the level series."""
    fast = _ema(levels, MACD_FAST)
    slow = _ema(levels, MACD_SLOW)
    macd_line = fast - slow
    signal = _ema(macd_line, MACD_SIGNAL)
    hist = macd_line - signal
    return macd_line, signal, hist


def _stoch(levels: pd.Series, window: int = STOCH_WINDOW) -> pd.Series:
    """Stochastic %K on the level series (0..1 scale, NaN when window < min)."""
    roll_min = levels.rolling(window, min_periods=window).min()
    roll_max = levels.rolling(window, min_periods=window).max()
    rng = roll_max - roll_min
    stoch = (levels - roll_min) / rng.where(rng != 0)
    return stoch


def _ret_nd(levels: pd.Series, n: int) -> float | None:
    """n-session return from the last available value. None if insufficient data."""
    vals = levels.dropna()
    if len(vals) < n + 1:
        return None
    prev = float(vals.iloc[-(n + 1)])
    if prev == 0:
        return None
    return float(vals.iloc[-1]) / prev - 1.0


def _drawdown_vs_252d_high(levels: pd.Series) -> float | None:
    """Current EW level relative to the rolling 252-session high. Returns a negative fraction."""
    vals = levels.dropna()
    if len(vals) < 10:
        return None
    high_252 = float(vals[-252:].max() if len(vals) >= 252 else vals.max())
    current = float(vals.iloc[-1])
    if high_252 <= 0:
        return None
    return current / high_252 - 1.0  # e.g. -0.43 for -43% drawdown


def _above_200d(levels: pd.Series) -> bool | None:
    """Is the current level above its 200-session simple moving average?"""
    vals = levels.dropna()
    if len(vals) < 200:
        return None
    ma200 = float(vals.iloc[-200:].mean())
    return float(vals.iloc[-1]) > ma200


def _slope_20d(levels: pd.Series) -> float | None:
    """Linear regression slope over the last 20 sessions (normalised by mean level)."""
    vals = levels.dropna()
    if len(vals) < 20:
        return None
    seg = vals.iloc[-20:].values.astype(float)
    x = np.arange(len(seg), dtype=float)
    mu = np.mean(seg)
    if mu == 0:
        return None
    # OLS slope
    slope = float(np.polyfit(x, seg, 1)[0]) / mu
    return slope


# ---------------------------------------------------------------------------
# Single-basket classification
# ---------------------------------------------------------------------------

def classify_basket(levels: pd.Series, prev_state: str | None = None,
                    days_in_state: int = 0) -> dict[str, Any]:
    """Classify one basket's EW level series into a washout-lifecycle state.

    Parameters
    ----------
    levels        : pd.Series — EW index level series (may contain NaNs at start)
    prev_state    : str | None — previous session's state (for CONFIRMED hysteresis)
    days_in_state : int — sessions this basket has been in `prev_state`

    Returns
    -------
    dict with keys:
        state        : str — one of FALLING / WASHED_OUT / BASING / TURNING / CONFIRMED / NONE
        evidence     : list[str] — descriptive evidence tags (no forward verbs)
        dd_252       : float | None — drawdown vs 252d high (negative fraction)
        hist_d       : float | None — day-over-day change in MACD histogram
        slope_20d    : float | None — normalised 20d linear regression slope
        stoch_last   : float | None — last stochastic value (0..1)
        ret_5d       : float | None — 5-session return
        above_200d   : bool | None — EW level above 200-session SMA
        days_in_state: int — sessions in current returned state
    """
    vals = levels.dropna()

    # Default payload
    out: dict[str, Any] = {
        "state": "NONE",
        "evidence": [],
        "dd_252": None,
        "hist_d": None,
        "slope_20d": None,
        "stoch_last": None,
        "ret_5d": None,
        "above_200d": None,
        "days_in_state": 0,
    }

    if len(vals) < 30:
        out["evidence"].append("insufficient_history")
        return out

    # -- Compute series metrics --
    ret_5d = _ret_nd(vals, 5)
    dd_252 = _drawdown_vs_252d_high(vals)
    ab200 = _above_200d(vals)
    slp20 = _slope_20d(vals)
    out["ret_5d"] = round(ret_5d, 4) if ret_5d is not None else None
    out["dd_252"] = round(dd_252, 4) if dd_252 is not None else None
    out["slope_20d"] = round(slp20, 5) if slp20 is not None else None
    out["above_200d"] = ab200

    # MACD on levels
    _, _, hist_series = _macd(vals)
    hist_last = float(hist_series.iloc[-1]) if not hist_series.empty else None
    hist_prev = float(hist_series.iloc[-2]) if len(hist_series) >= 2 else None
    hist_d: float | None = None
    if hist_last is not None and hist_prev is not None:
        hist_d = hist_last - hist_prev
    out["hist_d"] = round(hist_d, 6) if hist_d is not None else None

    # Stochastic on levels
    stoch_series = _stoch(vals)
    stoch_last: float | None = None
    if not stoch_series.empty and not pd.isna(stoch_series.iloc[-1]):
        stoch_last = float(stoch_series.iloc[-1])
    out["stoch_last"] = round(stoch_last, 4) if stoch_last is not None else None

    evidence: list[str] = []

    # ── HARD PRECEDENCE CASCADE ──────────────────────────────────────────────

    # 1. FALLING — evaluated FIRST, vetoes all others
    falling_ret = ret_5d is not None and ret_5d <= FALLING_RET_THRESH
    falling_macd = (hist_last is not None and hist_last < 0
                    and hist_d is not None and hist_d < 0)
    if falling_ret or falling_macd:
        if falling_ret:
            evidence.append(f"5d_ret={round(ret_5d, 4)}_<=_{FALLING_RET_THRESH}")
        if falling_macd:
            evidence.append(f"macd_hist_neg_and_falling:hist={round(hist_last or 0, 4)},d={round(hist_d or 0, 6)}")
        out["state"] = "FALLING"
        out["evidence"] = evidence
        days_new = (days_in_state + 1) if prev_state == "FALLING" else 1
        out["days_in_state"] = days_new
        return out

    # 2. Check washout depth (used by WASHED_OUT, TURNING, BASING, CONFIRMED)
    washout_depth_qualifies = (
        dd_252 is not None and dd_252 <= WASHOUT_DD_THRESH
        and (ab200 is False or ab200 is None)  # below or unknown 200d
    )

    # Decline arrested: hist_d is not aggressively falling
    hist_arrested = hist_d is not None and hist_d >= WASHOUT_HIST_ARREST

    # 3. TURNING — checked BEFORE WASHED_OUT since it extends into partial recovery
    # (basket may be slightly above 200d already as it turns)
    stoch_reclaim = stoch_last is not None and stoch_last >= STOCH_RECLAIM_THRESH
    hist_crossed_positive = hist_d is not None and hist_d >= TURNING_HIST_CROSS
    turning_context = dd_252 is not None and dd_252 <= WASHOUT_DD_THRESH  # still deep
    turning_signals = stoch_reclaim or hist_crossed_positive

    if turning_context and turning_signals:
        if stoch_reclaim:
            evidence.append(f"stoch_reclaim={round(stoch_last or 0, 3)}_>=_{STOCH_RECLAIM_THRESH}")
        if hist_crossed_positive:
            evidence.append(f"macd_hist_d_positive={round(hist_d or 0, 6)}")
        evidence.append(f"dd_252={round(dd_252 or 0, 4)}")

        # 4. CONFIRMED — TURNING held long enough AND slope positive
        in_turning = prev_state in ("TURNING", "CONFIRMED")
        days_turning = (days_in_state + 1) if in_turning else 1
        if (days_turning >= CONFIRMED_MIN_DAYS
                and slp20 is not None and slp20 >= CONFIRMED_SLOPE_MIN):
            evidence.append(f"days_turning={days_turning},slope_20d={round(slp20 or 0, 5)}")
            out["state"] = "CONFIRMED"
            out["evidence"] = evidence
            out["days_in_state"] = days_turning
            return out

        out["state"] = "TURNING"
        out["evidence"] = evidence
        days_new = (days_in_state + 1) if prev_state in ("TURNING", "CONFIRMED") else 1
        out["days_in_state"] = days_new
        return out

    # 5. WASHED_OUT — deep drawdown, below 200d, decline arrested
    if washout_depth_qualifies and hist_arrested:
        evidence.append(f"dd_252={round(dd_252 or 0, 4)}_<=_{WASHOUT_DD_THRESH}")
        evidence.append(f"below_200d=True,hist_arrested=True(d={round(hist_d or 0, 6)})")
        out["state"] = "WASHED_OUT"
        out["evidence"] = evidence
        days_new = (days_in_state + 1) if prev_state == "WASHED_OUT" else 1
        out["days_in_state"] = days_new
        return out

    # 6. BASING — washout depth qualifies but no turning evidence yet
    if dd_252 is not None and dd_252 <= WASHOUT_DD_THRESH:
        evidence.append(f"dd_252={round(dd_252 or 0, 4)}_basing_no_turn_yet")
        out["state"] = "BASING"
        out["evidence"] = evidence
        days_new = (days_in_state + 1) if prev_state == "BASING" else 1
        out["days_in_state"] = days_new
        return out

    # 7. NONE
    out["state"] = "NONE"
    out["evidence"] = evidence
    out["days_in_state"] = 0
    return out


# ---------------------------------------------------------------------------
# Batch compute over the committed chinabasketdata payloads
# ---------------------------------------------------------------------------

def compute_all(data_root: Path | None = None) -> dict[str, Any]:
    """Classify all CN baskets (curated 22 + THS 237) from committed site payloads.

    Reads chinabasketdata/baskets.json (curated) and chinabasketdata/baskets_ths.json
    (THS) — both committed nightly, no price re-fetch required. Returns the full
    artifact dict including schema, as_of, disclosure, and per-basket states.

    Performance target: seconds (series math on ~260 short series).
    """
    from lib import config as _cfg
    root = data_root or _cfg.ROOT
    site = root / "site" / "chinabasketdata"

    curated_path = site / "baskets.json"
    ths_path = site / "baskets_ths.json"

    # Load committed payloads
    curated_chart: dict[str, list] = {}
    ths_chart: dict[str, list] = {}
    curated_dates: list[str] = []
    ths_dates: list[str] = []

    if curated_path.exists():
        try:
            raw = json.loads(curated_path.read_text())
            ch = raw.get("chart", {})
            curated_dates = ch.get("dates", [])
            curated_chart = ch.get("baskets", {})
        except Exception as e:
            log.warning("china_basket_turn: failed to load curated baskets.json: %s", e)

    if ths_path.exists():
        try:
            raw = json.loads(ths_path.read_text())
            ch = raw.get("chart", {})
            ths_dates = ch.get("dates", [])
            ths_chart = ch.get("baskets", {})
        except Exception as e:
            log.warning("china_basket_turn: failed to load baskets_ths.json: %s", e)

    as_of_date = (curated_dates[-1] if curated_dates
                  else ths_dates[-1] if ths_dates
                  else datetime.now(timezone.utc).strftime("%Y-%m-%d"))

    results: dict[str, dict] = {}

    def _levels_to_series(dates: list[str], levels: list) -> pd.Series:
        idx = pd.DatetimeIndex([pd.Timestamp(d) for d in dates])
        vals = [None if v is None else float(v) for v in levels]
        s = pd.Series(vals, index=idx, dtype=float)
        return s

    # Curated baskets
    for bid, lvls in curated_chart.items():
        if not lvls or not curated_dates:
            continue
        try:
            s = _levels_to_series(curated_dates, lvls)
            cls_out = classify_basket(s)
            results[bid] = cls_out
        except Exception as e:
            log.warning("china_basket_turn: curated %s failed: %s", bid, e)
            results[bid] = {"state": "NONE", "evidence": [f"error:{e}"],
                            "dd_252": None, "hist_d": None, "slope_20d": None,
                            "stoch_last": None, "ret_5d": None, "above_200d": None,
                            "days_in_state": 0}

    # THS baskets
    for bid, lvls in ths_chart.items():
        if not lvls or not ths_dates:
            continue
        if bid in results:
            continue  # curated id collision (shouldn't happen, but guard)
        try:
            s = _levels_to_series(ths_dates, lvls)
            cls_out = classify_basket(s)
            results[bid] = cls_out
        except Exception as e:
            log.warning("china_basket_turn: ths %s failed: %s", bid, e)
            results[bid] = {"state": "NONE", "evidence": [f"error:{e}"],
                            "dd_252": None, "hist_d": None, "slope_20d": None,
                            "stoch_last": None, "ret_5d": None, "above_200d": None,
                            "days_in_state": 0}

    return {
        "schema": "basket_turn_cn.v1",
        "as_of": as_of_date,
        "disclosure": DISCLOSURE,
        "authority": AUTHORITY,
        "baskets": results,
    }


# ---------------------------------------------------------------------------
# Artifact writer (site/chinabasketdata/basket_turn_cn.json)
# ---------------------------------------------------------------------------

def write_artifact(artifact: dict[str, Any], site_dir: Path) -> Path:
    """Write the basket_turn_cn.json artifact to site/chinabasketdata/."""
    out_dir = site_dir / "chinabasketdata"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / "basket_turn_cn.json"
    out_path.write_text(json.dumps(artifact, separators=(",", ":"), default=str))
    return out_path


# ---------------------------------------------------------------------------
# Ledger writer (data/china_basket_turn/ledger.jsonl)
# ---------------------------------------------------------------------------

def _cn_lane_active() -> bool:
    """Return True if the current job is the CN_LANE asia runner (house law gate)."""
    lane = os.environ.get("CN_LANE", "").strip().lower()
    return lane == "asia"


def append_ledger(artifact: dict[str, Any], data_root: Path) -> int:
    """Append one row per basket state to the PIT forward ledger (CN_LANE=asia gate).

    Append-only, keep-first per (date, basket_id). Returns number of rows appended.
    """
    if not _cn_lane_active():
        log.info("china_basket_turn: ledger append skipped (CN_LANE != asia)")
        return 0

    ledger_dir = data_root / "china_basket_turn"
    ledger_dir.mkdir(parents=True, exist_ok=True)
    ledger_path = ledger_dir / "ledger.jsonl"

    as_of = artifact.get("as_of", "")
    baskets = artifact.get("baskets", {})

    # Build existing-key set for idempotency (keep-first)
    seen: set[tuple[str, str]] = set()
    if ledger_path.exists():
        try:
            for line in ledger_path.read_text().splitlines():
                if not line.strip():
                    continue
                row = json.loads(line)
                seen.add((row.get("date", ""), row.get("basket_id", "")))
        except Exception as e:
            log.warning("china_basket_turn: ledger read failed (will append anyway): %s", e)

    rows_written = 0
    with ledger_path.open("a") as fh:
        for bid, st in baskets.items():
            key = (as_of, bid)
            if key in seen:
                continue
            row = {
                "date": as_of,
                "basket_id": bid,
                "state": st.get("state", "NONE"),
                "dd_252": st.get("dd_252"),
                "hist_d": st.get("hist_d"),
                "slope_20d": st.get("slope_20d"),
                "ret_5d": st.get("ret_5d"),
                "evidence": st.get("evidence", []),
                "days_in_state": st.get("days_in_state", 0),
            }
            fh.write(json.dumps(row, separators=(",", ":"), default=str) + "\n")
            rows_written += 1
            seen.add(key)

    log.info("china_basket_turn: ledger appended %d rows for %s", rows_written, as_of)
    return rows_written


# ---------------------------------------------------------------------------
# Entry point (called from build scripts)
# ---------------------------------------------------------------------------

def run(data_root: Path | None = None, site_root: Path | None = None) -> dict[str, Any]:
    """Compute + write artifact + conditionally append ledger. Returns artifact."""
    from lib import config as _cfg
    root = data_root or _cfg.ROOT
    site = site_root or (root / "site")

    t0 = time.time()
    artifact = compute_all(data_root=root)
    elapsed = time.time() - t0

    n_baskets = len(artifact.get("baskets", {}))
    state_counts: dict[str, int] = {}
    for st in artifact.get("baskets", {}).values():
        s = st.get("state", "NONE")
        state_counts[s] = state_counts.get(s, 0) + 1

    log.info("china_basket_turn: classified %d baskets in %.2fs — state dist: %s",
             n_baskets, elapsed, state_counts)

    out_path = write_artifact(artifact, site)
    log.info("china_basket_turn: wrote artifact %s", out_path)

    append_ledger(artifact, root / "data")

    return artifact
