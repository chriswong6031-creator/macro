"""Deterioration Cascade — DISPLAY-ONLY organ (RSR-R5).

Watches the international risk-radar forward logs for SPEED of deterioration
across mature markets.  The sibling intl_cascade chip in the template reads the
LEVEL (n_alert); this organ reads the CHANGE RATE so the two chips answer
different questions.

MATURITY GUARD (mandatory — RSR-R5):
  A market participates only once its log holds >=5 prior sessions before
  today's row.  Immature markets are listed separately and NEVER counted.
  Without this guard, 7 of 10 logs (born 2026-07-15/16) would trigger the
  meter on their birth day — making the signal fire purely on log births.

Per session over mature markets:
  n_alert       : # markets with alert==True
  n_escalating  : # markets whose band rank ROSE vs prior session
                   (calm < watch < caution < elevated < risk-off)
  d3_alert      : n_alert(t) - n_alert(t-3 sessions)

STATE:
  STEADY           : n_alert <= 1 AND d3_alert <= 0
  SLIPPING         : d3_alert >= 1 OR n_escalating >= 2
  DETERIORATING_FAST: n_alert >= 3 OR d3_alert >= 2

Thresholds stored in data/deterioration_cascade/calib.json (display copy;
not a scored gate until gauntleted).

DISPLAY-ONLY: writes data/deterioration_cascade/latest.json every run;
appends data/deterioration_cascade/forward_log.jsonl ONLY on the nightly lane.
Never raises into the build (degrade-never-raise).
"""
from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

import pandas as pd

from lib import config

log = logging.getLogger(__name__)

SCHEMA = "deterioration_cascade.v1"

# band ordering for escalation detection (lower = calmer)
_BAND_RANK: dict[str, int] = {
    "calm": 0,
    "watch": 1,
    "caution": 2,
    "elevated": 3,
    "risk-off": 4,
}

# market codes with human-readable names
_MARKET_NAMES: dict[str, tuple[str, str]] = {
    "cn": ("China A", "中国A股"),
    "hk": ("Hong Kong", "港股"),
    "tw": ("Taiwan", "台股"),
    "kr": ("Korea", "韩股"),
    "jp": ("Japan", "日股"),
    "in": ("India", "印度"),
    "au": ("Australia", "澳股"),
    "gb": ("UK", "英股"),
    "ez": ("Eurozone", "欧元区"),
    "ca": ("Canada", "加股"),
}

# Maturity guard: minimum prior sessions before a market counts
_MATURITY_MIN_PRIOR = 5

# State thresholds — frozen in calib.json and here
_DEFAULT_CALIB = {
    "steady_max_alert": 1,
    "steady_max_d3": 0,
    "slipping_min_d3": 1,
    "slipping_min_escalating": 2,
    "fast_min_alert": 3,
    "fast_min_d3": 2,
    "maturity_min_prior": _MATURITY_MIN_PRIOR,
}

# How many sessions back for d3
_D3_LAG = 3


def _data_dir() -> Path:
    return config.data_dir()


def _intl_log_dir() -> Path:
    return _data_dir() / "risk_radar_intl"


def _us_log_path() -> Path:
    return _data_dir() / "risk_radar" / "forward_log.jsonl"


def _out_dir() -> Path:
    d = _data_dir() / "deterioration_cascade"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _calib_path() -> Path:
    return _out_dir() / "calib.json"


def _ensure_calib() -> dict:
    """Write calib.json if absent; always return the canonical thresholds."""
    p = _calib_path()
    if not p.exists():
        try:
            p.write_text(json.dumps(_DEFAULT_CALIB, indent=2), encoding="utf-8")
        except Exception as e:  # noqa: BLE001
            log.debug("deterioration_cascade: calib write failed (%s)", e)
    try:
        c = json.loads(p.read_text())
        # merge with defaults so missing keys don't break
        return {**_DEFAULT_CALIB, **c}
    except Exception:  # noqa: BLE001
        return dict(_DEFAULT_CALIB)


def _load_log(code: str) -> list[dict]:
    """Load all rows from a market's forward_log.jsonl.  Returns [] on error."""
    p = _intl_log_dir() / f"{code}_forward_log.jsonl"
    if not p.exists():
        return []
    try:
        rows = []
        for line in p.read_text(encoding="utf-8").strip().split("\n"):
            line = line.strip()
            if line:
                rows.append(json.loads(line))
        return rows
    except Exception as e:  # noqa: BLE001
        log.debug("deterioration_cascade: log load failed %s (%s)", code, e)
        return []


def _rows_by_date(rows: list[dict]) -> dict[str, dict]:
    """Index rows by asof date string, keeping last if dup."""
    out: dict[str, dict] = {}
    for r in rows:
        d = r.get("asof")
        if d:
            out[str(d)] = r
    return out


def _band_rank(state: str | None) -> int:
    """Map state string to band rank (0=calm, 4=risk-off).  Unknown maps to 0."""
    if state is None:
        return 0
    return _BAND_RANK.get(str(state).lower(), 0)


def _is_mature(rows: list[dict], today_str: str, min_prior: int) -> bool:
    """True if the log has >=min_prior rows with asof < today_str."""
    prior = [r for r in rows if str(r.get("asof", "")) < today_str]
    return len(prior) >= min_prior


def build() -> dict | None:
    """Compute deterioration_cascade snapshot, write latest.json, conditionally
    append forward_log.jsonl.  Returns the snapshot dict or None on failure."""
    try:
        return _build()
    except Exception as e:  # noqa: BLE001
        log.warning("deterioration_cascade: build failed (%s)", e, exc_info=True)
        return None


def _build() -> dict | None:
    calib = _ensure_calib()
    min_prior: int = int(calib.get("maturity_min_prior", _MATURITY_MIN_PRIOR))

    # Determine today = max asof across all logs
    all_rows: dict[str, list[dict]] = {}
    for code in _MARKET_NAMES:
        all_rows[code] = _load_log(code)

    all_asofs = [r.get("asof") for rows in all_rows.values() for r in rows if r.get("asof")]
    if not all_asofs:
        log.warning("deterioration_cascade: no intl logs found")
        return None

    today_str = max(all_asofs)

    # Classify each market as mature or immature
    mature_codes: list[str] = []
    immature_codes: list[str] = []
    for code, rows in all_rows.items():
        if _is_mature(rows, today_str, min_prior):
            mature_codes.append(code)
        else:
            if rows:  # log exists but not mature
                immature_codes.append(code)

    if not mature_codes:
        # All markets immature — still write a snapshot but state is STEADY by definition
        snap = _make_snap(today_str, "STEADY", 0, 0, 0,
                          len(mature_codes), [], immature_codes)
        _persist(snap)
        return snap

    # Build cross-market panel of alert and state, indexed by asof date
    # for the mature markets only
    panel_alert: dict[str, dict[str, bool]] = {}    # date -> {code: alert}
    panel_state: dict[str, dict[str, str]] = {}     # date -> {code: state}
    for code in mature_codes:
        by_date = _rows_by_date(all_rows[code])
        for d, row in by_date.items():
            panel_alert.setdefault(d, {})[code] = bool(row.get("alert", False))
            panel_state.setdefault(d, {})[code] = str(row.get("state") or "calm")

    # Sort dates
    sorted_dates = sorted(panel_alert.keys())
    if not sorted_dates:
        log.warning("deterioration_cascade: no dates in mature market panel")
        return None

    # B2 fix: derive today_str from the MATURE panel's latest date.
    # The global today_str may be dominated by an immature market's birth-day log
    # (e.g. tw born 2026-07-16 carries that asof, but no mature market has a row
    # for that date yet).  Using the mature panel's max date prevents the organ
    # from returning None on the exact day a new market is first recorded.
    if today_str not in sorted_dates:
        today_str = sorted_dates[-1]
        log.debug("deterioration_cascade: today_str not in mature panel; using %s", today_str)

    today_idx = sorted_dates.index(today_str)

    # Count alerts and escalations at today
    alert_today = panel_alert.get(today_str, {})
    state_today = panel_state.get(today_str, {})

    n_alert = sum(1 for code in mature_codes if alert_today.get(code, False))
    alerts = [code for code in mature_codes if alert_today.get(code, False)]

    # n_escalating: band rank rose vs prior session (for EACH mature market)
    n_escalating = 0
    if today_idx > 0:
        prev_date = sorted_dates[today_idx - 1]
        state_prev = panel_state.get(prev_date, {})
        for code in mature_codes:
            rank_now = _band_rank(state_today.get(code))
            rank_prev = _band_rank(state_prev.get(code))
            if rank_now > rank_prev:
                n_escalating += 1

    # d3_alert: n_alert(t) - n_alert(t-3 sessions).
    # M2 fix: only count markets present on BOTH today and the baseline date.
    # A market that is "mature" today but had no row 3 sessions ago would
    # otherwise default-to-False at baseline, making its alert today count as
    # a spurious +1 rise that never actually happened.
    d3_alert = 0
    if today_idx >= _D3_LAG:
        past_date = sorted_dates[today_idx - _D3_LAG]
        alert_past = panel_alert.get(past_date, {})
        # Restrict to markets present on both dates
        both_dates_codes = [c for c in mature_codes
                            if c in alert_today and c in alert_past]
        n_alert_today_d3 = sum(1 for c in both_dates_codes if alert_today.get(c, False))
        n_alert_past = sum(1 for c in both_dates_codes if alert_past.get(c, False))
        d3_alert = n_alert_today_d3 - n_alert_past

    # State machine (flat thresholds, no hysteresis)
    state = _classify(n_alert, n_escalating, d3_alert, calib)

    snap = _make_snap(today_str, state, n_alert, n_escalating, d3_alert,
                      len(mature_codes), alerts, immature_codes)
    _persist(snap)
    return snap


def _classify(n_alert: int, n_escalating: int, d3_alert: int, calib: dict) -> str:
    """Map (n_alert, n_escalating, d3_alert) to a state string."""
    # DETERIORATING_FAST takes priority
    if (n_alert >= calib["fast_min_alert"] or d3_alert >= calib["fast_min_d3"]):
        return "DETERIORATING_FAST"
    # SLIPPING
    if (d3_alert >= calib["slipping_min_d3"] or n_escalating >= calib["slipping_min_escalating"]):
        return "SLIPPING"
    # STEADY
    return "STEADY"


def _make_snap(today_str: str, state: str, n_alert: int,
               n_escalating: int, d3_alert: int,
               n_mature: int, alerts: list[str],
               immature: list[str]) -> dict[str, Any]:
    return {
        "schema": SCHEMA,
        "asof": today_str,
        "state": state,
        "n_alert": n_alert,
        "n_escalating": n_escalating,
        "d3_alert": d3_alert,
        "n_mature": n_mature,
        "alerts": alerts,
        "immature": immature,
    }


def _persist(snap: dict) -> None:
    out_dir = _out_dir()
    latest_path = out_dir / "latest.json"
    try:
        latest_path.write_text(json.dumps(snap, default=str), encoding="utf-8")
        log.info("deterioration_cascade: wrote %s", latest_path)
    except Exception as e:  # noqa: BLE001
        log.warning("deterioration_cascade: latest.json write failed (%s)", e)

    try:
        from engine.risk_radar_intl_audit import ledger_lane_armed
        if ledger_lane_armed():
            import datetime as _dt
            fwd_path = out_dir / "forward_log.jsonl"
            # Read existing rows; skip append if this asof already recorded
            existing: list[dict] = []
            if fwd_path.exists():
                for line in fwd_path.read_text(encoding="utf-8").splitlines():
                    line = line.strip()
                    if line:
                        try:
                            existing.append(json.loads(line))
                        except Exception:  # noqa: BLE001
                            pass
            asof_str = str(snap.get("asof", ""))
            if any(r.get("asof") == asof_str for r in existing):
                log.debug("deterioration_cascade: asof %s already in forward_log, skipping", asof_str)
            else:
                row = dict(snap)
                row["logged_at"] = _dt.datetime.now(_dt.timezone.utc).isoformat(timespec="seconds")
                with open(fwd_path, "a", encoding="utf-8") as fh:
                    fh.write(json.dumps(row, default=str) + "\n")
                log.info("deterioration_cascade: appended to %s", fwd_path)
    except Exception as e:  # noqa: BLE001
        log.warning("deterioration_cascade: forward_log append failed (%s)", e)
