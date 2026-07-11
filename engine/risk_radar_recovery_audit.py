"""Risk Radar — recovery-channel forward-outcome log + deterministic grading.

Mirrors engine/risk_radar_audit.py patterns exactly (read that module first).

File: data/risk_radar/recovery_log.jsonl
  One idempotent-by-asof line per daily snapshot. Graded when SPY path matures.

Ruler: REBOUND CAPTURE (RRX-R2 — the only valid ruler for recovery confirmers):
  Conditioned on radar phase in {peaking, receding}, grade h21 (primary) and h63 (secondary)
  SPY forward returns + max-adverse-excursion vs the peaking/receding base rate.
  Significance by within-episode time-preserving permutation — NOT here, at read time (2027-01).

STANDING NOTE: No significance claim is made below n>=30 per arm. First read clock 2027-01-15
  per §8 of the masterplan. Scorecard is purely descriptive until that date.

Pure-ish + never raises into the build.
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

from lib import config, store

log = logging.getLogger(__name__)

HORIZONS = {"h21": 21, "h63": 63}          # business-day forward windows (rebound ruler, RRX-R2)
RECOVERY_PHASES = ("peaking", "receding")   # which phases count as "something to recover FROM"

_N_MIN_SIGNIFICANCE = 30   # minimum per arm before any significance claim (printed, not hidden)


def _path(root=None) -> Path:
    base = config.data_dir() if root is None else (Path(root) / "data")
    p = base / "risk_radar" / "recovery_log.jsonl"
    p.parent.mkdir(parents=True, exist_ok=True)
    return p


def _read(p: Path) -> list[dict]:
    if not p.exists():
        return []
    rows = []
    for line in p.read_text().splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            rows.append(json.loads(line))
        except Exception:  # noqa: BLE001
            continue
    return rows


def _write(p: Path, rows: list[dict]) -> None:
    p.write_text("\n".join(json.dumps(r, separators=(",", ":"), default=str) for r in rows) + "\n")


def log_snapshot(recovery: dict, radar_snap: dict, root=None) -> bool:
    """Append today's recovery snapshot to the forward log (idempotent by asof).
    Returns True if a new row was written.

    Args:
        recovery: output of engine.risk_radar_recovery.assess()
        radar_snap: the risk_radar snapshot (latest['risk_radar'])
    """
    try:
        if not recovery or not isinstance(recovery, dict):
            return False

        asof = str((recovery.get("asof") or radar_snap.get("asof") or ""))
        if not asof:
            return False

        traj = radar_snap.get("trajectory") or {}
        phase = traj.get("phase")

        mkt = recovery.get("market") or {}
        chips_snap: dict = {}
        for chip in (mkt.get("chips") or []):
            k = chip.get("key")
            if k:
                chips_snap[k] = {
                    "fired": bool(chip.get("fired")),
                    "fresh": bool(chip.get("fresh")),
                    # RRX2 WA-6: record channel alongside fired/fresh for the audit log
                    "channel": chip.get("channel", "internals"),
                }
        veto = mkt.get("veto") or {}
        # RRX2 WA-6: record morphology.shape in the audit row
        morphology_shape = (mkt.get("morphology") or {}).get("shape", "grinding")

        entry = {
            "asof": asof,
            "phase": phase,
            "intensity": traj.get("intensity"),
            "chips": chips_snap,
            "veto": {
                "active": bool(veto.get("active")),
                "p_now": veto.get("p_now"),
            },
            "liquidity_n": int(recovery.get("n_fresh") or 0),
            "market_confirmed": bool(mkt.get("market_confirmed")),
            "turn_confirmed_full": bool(recovery.get("turn_confirmed_full")),
            # RRX2 WA-6: morphology shape alongside chip states (same rebound-ruler grading path)
            "morphology_shape": morphology_shape,
            "logged_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "graded": None,
        }

        p = _path(root)
        rows = _read(p)
        if any(r.get("asof") == entry["asof"] for r in rows):
            return False
        rows.append(entry)
        _write(p, rows)
        return True
    except Exception as e:  # noqa: BLE001
        log.warning("risk_radar_recovery_audit log_snapshot failed: %s", e)
        return False


def _spy() -> pd.Series | None:
    df = store.read("yahoo", "SPY")
    if df is None or "close" not in df:
        return None
    s = df["close"].dropna().astype(float)
    s.index = pd.to_datetime(s.index)
    return s.sort_index()


def _grade_entry(entry: dict, spy: pd.Series) -> dict | None:
    """Realized forward return + MAE per horizon from the as-of date.
    Returns the 'graded' dict when BOTH horizons have matured, else None.

    fwd_ret = SPY close t+h / t - 1  (rebound capture, not drawdown)
    mae = min cumulative return over the window (max adverse excursion from base)
    """
    asof = pd.Timestamp(entry["asof"])
    loc = spy.index.searchsorted(asof, side="right")    # first bar strictly after as-of
    max_h = max(HORIZONS.values())
    if loc + max_h > len(spy):
        return None                                      # not matured yet

    base_loc = max(0, loc - 1)
    base_px = float(spy.iloc[base_loc])
    result: dict = {"base_px": round(base_px, 2)}

    for hk, hd in HORIZONS.items():
        w = spy.iloc[loc: loc + hd]
        if len(w) == 0:
            result[hk] = {"fwd_ret": None, "mae": None}
            continue
        fwd_ret = float(w.iloc[-1] / base_px - 1.0)
        # MAE: min cumulative return over the window (largest adverse move)
        mae = float((w / base_px - 1.0).min())
        result[hk] = {
            "fwd_ret": round(fwd_ret, 4),
            "mae": round(mae, 4),
        }

    result["graded_at"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
    return result


def grade_log(root=None) -> int:
    """Grade every matured, ungraded recovery entry. Returns # newly graded."""
    try:
        p = _path(root)
        rows = _read(p)
        if not rows:
            return 0
        spy = _spy()
        if spy is None:
            return 0
        n = 0
        for r in rows:
            if r.get("graded"):
                continue
            g = _grade_entry(r, spy)
            if g is not None:
                r["graded"] = g
                n += 1
        if n:
            _write(p, rows)
        return n
    except Exception as e:  # noqa: BLE001
        log.warning("risk_radar_recovery_audit grade_log failed: %s", e)
        return 0


def scorecard(root=None) -> dict:
    """Per-chip mean forward returns (with/without chip) among graded peaking/receding rows.
    Counts printed; no significance claim below n>=30 per arm (RRX-R2; first read 2027-01-15).
    Never raises.
    """
    try:
        rows = [r for r in _read(_path(root)) if r.get("graded")]
    except Exception:  # noqa: BLE001
        rows = []

    if not rows:
        return {"n_graded": 0, "note": "no matured entries yet"}

    # Restrict to recovery-relevant phases
    eligible = [r for r in rows if r.get("phase") in RECOVERY_PHASES]
    n_eligible = len(eligible)

    if n_eligible == 0:
        return {
            "n_graded": len(rows),
            "n_eligible_phase": 0,
            "note": f"no graded rows in phases {RECOVERY_PHASES} yet",
        }

    # Collect all chip keys seen
    all_keys: set = set()
    for r in eligible:
        all_keys.update((r.get("chips") or {}).keys())

    per_chip: dict = {}
    for key in sorted(all_keys):
        with_chip: list[dict] = []
        without_chip: list[dict] = []
        for r in eligible:
            chip_fired = (r.get("chips") or {}).get(key, {}).get("fired", False)
            g = r["graded"]
            if chip_fired:
                with_chip.append(g)
            else:
                without_chip.append(g)

        def _mean_ret(entries, hk):
            vals = [e[hk]["fwd_ret"] for e in entries
                    if hk in e and e[hk]["fwd_ret"] is not None]
            return round(float(np.mean(vals)), 4) if vals else None

        chip_stat: dict = {"n_with": len(with_chip), "n_without": len(without_chip)}
        for hk in HORIZONS:
            chip_stat[f"mean_fwd_ret_{hk}_with"] = _mean_ret(with_chip, hk)
            chip_stat[f"mean_fwd_ret_{hk}_without"] = _mean_ret(without_chip, hk)

        min_n = min(len(with_chip), len(without_chip))
        chip_stat["significance_note"] = (
            f"n_with={len(with_chip)}, n_without={len(without_chip)}. "
            f"{'INSUFFICIENT (<30 per arm): descriptive only.' if min_n < _N_MIN_SIGNIFICANCE else 'n sufficient — run within-episode permutation at read time.'}"
        )
        per_chip[key] = chip_stat

    # Overall base rates for peaking/receding
    base_stats: dict = {}
    for hk in HORIZONS:
        vals = [r["graded"][hk]["fwd_ret"] for r in eligible
                if hk in r["graded"] and r["graded"][hk]["fwd_ret"] is not None]
        base_stats[f"base_mean_fwd_ret_{hk}"] = round(float(np.mean(vals)), 4) if vals else None
        base_stats[f"base_n_{hk}"] = len(vals)

    return {
        "n_graded": len(rows),
        "n_eligible_phase": n_eligible,
        "per_chip": per_chip,
        "base_rates": base_stats,
        "asof_range": [rows[0]["asof"], rows[-1]["asof"]],
        "note": (
            f"Rebound ruler (RRX-R2): h21 primary, h63 secondary vs peaking/receding base rate. "
            f"No significance claim below n>={_N_MIN_SIGNIFICANCE} per arm. "
            f"First permutation read: 2027-01-15."
        ),
    }


def snapshot_and_grade(recovery: dict, radar_snap: dict, root=None) -> dict:
    """Convenience for run.py: log today's snapshot, grade matured entries, return the scorecard.
    Never raises."""
    try:
        log_snapshot(recovery, radar_snap, root=root)
        grade_log(root=root)
        return scorecard(root=root)
    except Exception as e:  # noqa: BLE001
        log.warning("risk_radar_recovery_audit snapshot_and_grade failed: %s", e)
        return {"n_graded": 0, "note": f"error: {e}"}
