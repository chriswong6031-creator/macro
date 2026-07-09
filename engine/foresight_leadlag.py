"""engine.foresight_leadlag — Crowd-arrival lead-lag grader (TIL W6, PR-H).

Judge #3: the front-run receipts.

Reads data/foresight/earliness_log.jsonl (written nightly by foresight_earliness,
previously READ BY NOTHING) and for each logged PRECIPICE/BROADENING flag in
data/foresight/log.jsonl:

  1. Finds the attention legs for the flagged theme in the earliness log at each
     date after the flag.
  2. Detects when each attention leg FIRST crossed a "crowding threshold" (the leg
     value exceeds its own 75th-percentile across all dates in the log for that
     theme) = "attention arrival" for that leg.
  3. Computes signed lead-days: flag_date − attention_arrival_date.
       POSITIVE = we flagged BEFORE the crowd (we led).
       NEGATIVE = crowd arrived before our flag (we were late).
       None = attention never arrived / insufficient data.
  4. Computes basket price excess (equal-weight theme members) in the pre-arrival
     window vs the post-arrival window, using the same PIT-price pattern as
     foresight_grader.py (_closes, survivorship-free approach).

Output: data/foresight/earliness_grades.json — per-flag rows + pooled summary.
  - median_lead_days per leg across all graded flags.
  - share_led: fraction of flags where we led (lead_days > 0).
  - excess split: pre_arrival_excess_pct vs post_arrival_excess_pct (pooled).
  - n_pending: flags that have not yet crossed the attention threshold.
  - If median_lead ~0 the desk is riding attention, not front-running — printed
    prominently in artifact notes (house honesty law).

Authority block: is_context_only=True, all promotion flags False.
No LLM calls. Tolerant reader (missing log -> honest null + n_pending=0).
Append-only tapes are NOT written here (grader reads, does not append).
"""
from __future__ import annotations

import json
import logging
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

ARTIFACT_ID = "foresight-earliness-grades"
OUTPUT_PATH = ("data", "foresight", "earliness_grades.json")

# Attention-leg names (must match foresight_earliness._LEG_NAMES)
_LEG_NAMES = ("coverage_arrival", "news_flow", "ownership_breadth", "tape_extension")

# A leg "arrives" (crowd crosses) when its raw value exceeds this percentile
# of that leg's historical distribution for the same theme.  75th = notably crowded.
_CROWD_THRESHOLD_PCT = 75.0

# Minimum entries in the log for a theme to be gradeable
_MIN_LOG_ENTRIES = 3

# For price windows: look at the 30 calendar days PRE and POST attention arrival
_WINDOW_DAYS = 30

# Direction filter: only grade thesis-direction flags (PRECIPICE/BROADENING).
# RE-RATING/WATCH are control arms — their earliness grades are informational only
# and NEVER reported as skill. We include all logged stages but mark control arms.
_THESIS_STAGES = {"PRECIPICE", "BROADENING",
                  "PRECIPICE (text)", "PRECIPICE (fingerprint)",
                  "BROADENING (text)", "BROADENING (fingerprint)"}

AUTHORITY_BLOCK: dict[str, Any] = {
    "is_context_only": True,
    "may_rank": False,
    "may_gate": False,
    "may_size": False,
    "may_escalate": False,
    "display_only": True,
    "not_a_signal": True,
    "tier": "display",
    "forbidden_uses": [
        "ranking", "sizing", "alert_escalation", "board_ordering",
        "mastermind_arming", "scored_path",
    ],
}


# ---------------------------------------------------------------------------
# Price helpers (mirrors foresight_grader._closes / _ret pattern)
# ---------------------------------------------------------------------------

def _closes(ticker: str, root: Path) -> pd.Series | None:
    """Read close series from data/yahoo/<ticker>.parquet (PIT-safe, survivorship-free)."""
    p = root / "data" / "yahoo" / f"{ticker}.parquet"
    if not p.exists():
        return None
    try:
        df = pd.read_parquet(p)
    except Exception:  # noqa: BLE001
        return None
    if "close" not in df.columns:
        return None
    s = df["close"].dropna()
    if not len(s):
        return None
    s.index = pd.to_datetime(s.index)
    return s.sort_index()


def _window_return(s: pd.Series | None, start: pd.Timestamp,
                   end: pd.Timestamp) -> float | None:
    """Compute total return for a series from start to end (inclusive window).
    No look-ahead past end. Returns None when there are fewer than 2 price points."""
    if s is None or s.empty:
        return None
    within = s[(s.index >= start) & (s.index <= end)]
    if len(within) < 2:
        return None
    p0 = float(within.iloc[0])
    p1 = float(within.iloc[-1])
    if p0 <= 0:
        return None
    return p1 / p0 - 1.0


def _theme_window_excess(members: list[str], start: pd.Timestamp,
                         end: pd.Timestamp, spy: pd.Series | None,
                         root: Path) -> float | None:
    """Equal-weight theme excess vs SPY in the window [start, end]."""
    spy_ret = _window_return(spy, start, end)
    if spy_ret is None:
        return None
    rets = [r for m in (members or [])
            for r in [_window_return(_closes(m, root), start, end)]
            if r is not None]
    if len(rets) < 2:
        return None
    return float(np.mean(rets)) - spy_ret


# ---------------------------------------------------------------------------
# Read helpers
# ---------------------------------------------------------------------------

def _read_jsonl(p: Path) -> list[dict]:
    if not p.exists():
        return []
    out: list[dict] = []
    for line in p.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            out.append(json.loads(line))
        except Exception:  # noqa: BLE001
            continue
    return out


# ---------------------------------------------------------------------------
# Core grading logic
# ---------------------------------------------------------------------------

def _crowd_threshold(theme_log_rows: list[dict], leg: str) -> float | None:
    """75th-percentile of leg values across all log rows for this theme.
    Returns None if insufficient data."""
    vals = [float(r["legs"][leg]) for r in theme_log_rows
            if isinstance(r.get("legs"), dict)
            and r["legs"].get(leg) is not None]
    if len(vals) < _MIN_LOG_ENTRIES:
        return None
    return float(np.percentile(vals, _CROWD_THRESHOLD_PCT))


def _first_crossing(theme_log_rows: list[dict], leg: str,
                    threshold: float, after_date: str) -> str | None:
    """First date (ISO string) where leg value > threshold AND date > after_date.
    Returns None when never crossed."""
    crossed = None
    for row in sorted(theme_log_rows, key=lambda r: r.get("asof", "")):
        asof = row.get("asof", "")
        if asof <= after_date:
            continue
        if not isinstance(row.get("legs"), dict):
            continue
        val = row["legs"].get(leg)
        if val is None:
            continue
        try:
            v = float(val)
        except (TypeError, ValueError):
            continue
        if v > threshold:
            crossed = asof
            break
    return crossed


def grade_flag(flag: dict, theme_log_rows: list[dict], spy: pd.Series | None,
               root: Path) -> dict:
    """Grade one foresight flag against the attention log.

    Returns a grade dict with:
      - flag_date, theme, stage, is_thesis_direction
      - per_leg: {leg: {threshold, arrival_date, lead_days}}
      - n_legs_arrived: int
      - n_legs_pending: int
      - pre_arrival_excess: mean pre-window excess (vs SPY) across arrived legs
      - post_arrival_excess: mean post-window excess (vs SPY) across arrived legs
      - note (any grading caveat)
    """
    flag_date = flag.get("asof", "")
    theme = flag.get("theme", "")
    stage = flag.get("stage", "UNKNOWN")
    members = flag.get("members") or []
    is_thesis = any(stage.upper().startswith(s.upper()) for s in _THESIS_STAGES) or \
                any(stage.upper() in s.upper() for s in ("PRECIPICE", "BROADENING"))

    # simplify: any stage that starts with PRECIPICE or BROADENING (case-insensitive)
    is_thesis = (stage.upper().replace("(TEXT)", "").replace("(FINGERPRINT)", "").strip()
                 in {"PRECIPICE", "BROADENING"})

    per_leg: dict[str, dict] = {}
    pre_excesses: list[float] = []
    post_excesses: list[float] = []
    n_arrived = 0
    n_pending = 0
    caveats: list[str] = []

    if len(theme_log_rows) < _MIN_LOG_ENTRIES:
        caveats.append(f"insufficient log entries ({len(theme_log_rows)}) for threshold")

    for leg in _LEG_NAMES:
        threshold = _crowd_threshold(theme_log_rows, leg)
        if threshold is None:
            per_leg[leg] = {
                "threshold": None,
                "arrival_date": None,
                "lead_days": None,
                "note": "insufficient_data",
            }
            n_pending += 1
            continue

        arrival = _first_crossing(theme_log_rows, leg, threshold, flag_date)
        if arrival is None:
            per_leg[leg] = {
                "threshold": round(threshold, 4),
                "arrival_date": None,
                "lead_days": None,
                "note": "never_crossed",
            }
            n_pending += 1
            continue

        n_arrived += 1
        flag_ts = pd.Timestamp(flag_date)
        arrival_ts = pd.Timestamp(arrival)
        lead_days = int((flag_ts - arrival_ts).days)

        # Price excess in pre-arrival and post-arrival windows (WINDOW_DAYS each)
        pre_start = arrival_ts - pd.Timedelta(days=_WINDOW_DAYS)
        pre_end = arrival_ts
        post_start = arrival_ts
        post_end = arrival_ts + pd.Timedelta(days=_WINDOW_DAYS)

        pre_exc = _theme_window_excess(members, pre_start, pre_end, spy, root)
        post_exc = _theme_window_excess(members, post_start, post_end, spy, root)

        if pre_exc is not None:
            pre_excesses.append(pre_exc)
        if post_exc is not None:
            post_excesses.append(post_exc)

        per_leg[leg] = {
            "threshold": round(threshold, 4),
            "arrival_date": arrival,
            "lead_days": lead_days,
            "pre_arrival_excess_pct": round(100.0 * pre_exc, 2) if pre_exc is not None else None,
            "post_arrival_excess_pct": round(100.0 * post_exc, 2) if post_exc is not None else None,
            "note": "led" if lead_days > 0 else ("concurrent" if lead_days == 0 else "lagged"),
        }

    return {
        "flag_date": flag_date,
        "theme": theme,
        "stage": stage,
        "is_thesis_direction": is_thesis,
        "per_leg": per_leg,
        "n_legs_arrived": n_arrived,
        "n_legs_pending": n_pending,
        "pre_arrival_excess_pct": round(100.0 * float(np.mean(pre_excesses)), 2) if pre_excesses else None,
        "post_arrival_excess_pct": round(100.0 * float(np.mean(post_excesses)), 2) if post_excesses else None,
        "note": "; ".join(caveats) if caveats else None,
    }


def _pooled_summary(flag_grades: list[dict]) -> dict:
    """Compute pooled lead-lag summary across all graded flags (thesis only)."""
    thesis_grades = [g for g in flag_grades if g.get("is_thesis_direction")]

    summary_by_leg: dict[str, dict] = {}
    for leg in _LEG_NAMES:
        lead_vals = [
            g["per_leg"][leg]["lead_days"]
            for g in thesis_grades
            if leg in g.get("per_leg", {})
            and g["per_leg"][leg].get("lead_days") is not None
        ]
        if not lead_vals:
            summary_by_leg[leg] = {
                "n_graded": 0,
                "median_lead_days": None,
                "share_led": None,
                "note": "no_arrivals_yet",
            }
            continue

        median_lead = float(np.median(lead_vals))
        share_led = float(sum(1 for v in lead_vals if v > 0) / len(lead_vals))
        note = (
            "desk_leads_attention" if median_lead > 2
            else ("desk_concurrent_with_attention" if abs(median_lead) <= 2
                  else "desk_rides_attention_not_front_running")
        )
        summary_by_leg[leg] = {
            "n_graded": len(lead_vals),
            "median_lead_days": round(median_lead, 1),
            "share_led": round(share_led, 3),
            "note": note,
        }

    # pooled excess split
    pre_vals = [g["pre_arrival_excess_pct"] for g in thesis_grades
                if g.get("pre_arrival_excess_pct") is not None]
    post_vals = [g["post_arrival_excess_pct"] for g in thesis_grades
                 if g.get("post_arrival_excess_pct") is not None]

    # Overall lead assessment (across legs)
    all_leads = [
        g["per_leg"][leg]["lead_days"]
        for g in thesis_grades
        for leg in _LEG_NAMES
        if leg in g.get("per_leg", {})
        and g["per_leg"][leg].get("lead_days") is not None
    ]
    overall_median = float(np.median(all_leads)) if all_leads else None

    if overall_median is None:
        front_run_assessment = "INSUFFICIENT_DATA"
    elif abs(overall_median) <= 2:
        front_run_assessment = "CONCURRENT_WITH_CROWD — desk does not demonstrably front-run"
    elif overall_median > 2:
        front_run_assessment = f"DESK_LEADS_CROWD (median {overall_median:.1f}d)"
    else:
        front_run_assessment = f"DESK_LAGS_CROWD (median {overall_median:.1f}d)"

    return {
        "n_thesis_flags": len(thesis_grades),
        "n_control_flags": len(flag_grades) - len(thesis_grades),
        "by_leg": summary_by_leg,
        "pooled_pre_arrival_excess_pct": round(float(np.mean(pre_vals)), 2) if pre_vals else None,
        "pooled_post_arrival_excess_pct": round(float(np.mean(post_vals)), 2) if post_vals else None,
        "overall_median_lead_days": overall_median,
        "front_run_assessment": front_run_assessment,
        "note": (
            "HONEST NULL — front_run_assessment is printed regardless of direction. "
            "A near-zero or negative median lead means the desk is riding attention, "
            "not front-running it. THIS IS THE PROGRAM'S CORE HONESTY CHECK. "
            "n_pending flags have not yet produced an attention crossing — they will "
            "accrue as the tape grows. First promotion-eligible read: 2026-10-15."
        ),
    }


# ---------------------------------------------------------------------------
# Main compute function
# ---------------------------------------------------------------------------

def compute_earliness_grades(root: Path, today: str | None = None) -> dict:
    """Read earliness_log.jsonl + foresight/log.jsonl, grade all flags,
    return the artifact dict (not written here — caller writes atomically).

    Returns a displayable dict. Missing input -> honest null, never crashes.
    """
    if today is None:
        today = date.today().isoformat()

    foresight_log_path = root / "data" / "foresight" / "log.jsonl"
    earliness_log_path = root / "data" / "foresight" / "earliness_log.jsonl"

    foresight_flags = _read_jsonl(foresight_log_path)
    earliness_log = _read_jsonl(earliness_log_path)

    # Index earliness log by theme
    by_theme: dict[str, list[dict]] = {}
    for row in earliness_log:
        theme = row.get("theme", "")
        if not theme:
            continue
        by_theme.setdefault(theme, []).append(row)

    if not foresight_flags:
        return _null_artifact(today, "foresight/log.jsonl absent or empty")

    # Load SPY for excess calculations
    try:
        spy = _closes("SPY", root)
    except Exception as e:  # noqa: BLE001
        log.warning("earliness grader: SPY load failed: %s", e)
        spy = None

    flag_grades: list[dict] = []
    n_no_log = 0
    for flag in foresight_flags:
        theme = flag.get("theme", "")
        theme_rows = by_theme.get(theme, [])
        if not theme_rows:
            n_no_log += 1
        grade = grade_flag(flag, theme_rows, spy, root)
        flag_grades.append(grade)

    pooled = _pooled_summary(flag_grades)

    # Count pending (flags where all legs are pending)
    n_pending = sum(
        1 for g in flag_grades
        if g["n_legs_arrived"] == 0
    )

    stale_legs: list[str] = []
    if not earliness_log:
        stale_legs.append("earliness_log.jsonl — absent (no attention data yet)")
    if spy is None:
        stale_legs.append("SPY closes — absent (price excess calculations null)")
    if n_no_log > 0:
        stale_legs.append(f"{n_no_log} themes in foresight/log.jsonl have no earliness_log rows yet")

    return {
        "as_of": today,
        "produced_at": datetime.now(timezone.utc).isoformat(),
        "n_flags": len(flag_grades),
        "n_pending": n_pending,
        "n_legs_arrived_total": sum(g["n_legs_arrived"] for g in flag_grades),
        "authority": AUTHORITY_BLOCK,
        "stale_legs": stale_legs,
        "pooled_summary": pooled,
        "flag_grades": flag_grades,
        "schema": "foresight.earliness_grades.v1",
        "note": (
            f"Crowd-arrival lead-lag grader (TIL W6 PR-H, judge #3). "
            f"Signed lead-days = flag_date - attention_arrival_date; "
            f"POSITIVE = desk flagged before crowd. "
            f"n_pending={n_pending}: flags with no attention crossing yet. "
            f"FRONT_RUN_ASSESSMENT: {pooled['front_run_assessment']}. "
            "Display-only; never a scored path. "
            "First promotion-eligible read: 2026-10-15."
        ),
    }


def _null_artifact(today: str, reason: str) -> dict:
    return {
        "as_of": today,
        "produced_at": datetime.now(timezone.utc).isoformat(),
        "n_flags": 0,
        "n_pending": 0,
        "n_legs_arrived_total": 0,
        "authority": AUTHORITY_BLOCK,
        "stale_legs": [reason],
        "pooled_summary": None,
        "flag_grades": [],
        "schema": "foresight.earliness_grades.v1",
        "note": f"Honest null — {reason}. Will accrue as log is written nightly.",
    }
