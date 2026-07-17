"""Risk Radar — forward-outcome log + deterministic grading (Phase B).

Every daily risk_radar snapshot is APPENDED to data/risk_radar/forward_log.jsonl (idempotent
by as-of date; every writer self-gates on ledger_lane_armed(), so off-lane renders are
read-only). Once an entry's horizon matures, it is GRADED deterministically against the
realized SPY path: did a >= threshold drawdown actually occur within H business days? Each
alert is then a true-positive or a false-positive. The rolling scorecard (realized precision /
recall / false-positive rate per state-band and per scare-type and per horizon) is what the
dashboard surfaces and what the Opus self-correction loop (engine/risk_radar_review.py) reads
to rethink wrong calls and retune the calibration. Self-auditing by construction.

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

HORIZONS = {"h5": 5, "h10": 10, "h21": 21}        # business-day forward windows
DD_THRESHOLDS = (0.05, 0.08)                       # a >=5% pullback = a "drawdown"; 8% = a bigger one
PRIMARY_DD = 0.05
ALERT_STATES = ("elevated", "risk-off")            # which states count as a loud alert for precision


def ledger_lane_armed() -> bool:
    """True only on a ledger-advancing collect lane (COLLECT_LANE=nightly, legacy
    alias US_LANE). House law: nightly is the SOLE advancer of data/ forward
    ledgers — this log's only advancing lane is daily.yml's engine job (job-level
    COLLECT_LANE=nightly; verified via git log on data/risk_radar/forward_log.jsonl:
    every advancing commit is that job's "engine: regime update"). engine/run.py
    also runs on closing-bell (whose contract, closing-bell.yml, is that every
    ledger writer self-gates on COLLECT_LANE) and the engine-render/render
    re-render lanes; there the radar still renders and snapshot_and_grade degrades
    to a pure scorecard read, but log/grade must not advance — appends are
    idempotent-by-asof with FIRST-WRITER-WINS, so a mid-session off-lane append
    would permanently displace the nightly row. Canonical gate:
    engine/risk_radar_intl_audit.ledger_lane_armed (#2684); ignition sibling
    engine/ignition_audit.ledger_lane_armed (#2693)."""
    import os
    lane = os.environ.get("COLLECT_LANE", "") or os.environ.get("US_LANE", "")
    return lane.lower() == "nightly"


def _path(root=None) -> Path:
    base = config.data_dir() if root is None else (Path(root) / "data")
    p = base / "risk_radar" / "forward_log.jsonl"
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


def _entry_from_snapshot(snap: dict) -> dict | None:
    """Slim a risk_radar.compute() snapshot to the loggable fields (no recompute)."""
    if not snap or not snap.get("asof") or snap.get("state") is None:
        return None
    return {
        "asof": str(snap["asof"]),
        "state": snap.get("state"),
        "alert": bool(snap.get("alert")),
        "dominant_scare": snap.get("dominant_scare"),
        "top_score": snap.get("top_score"),
        "conjunction_n": (snap.get("drawdown_prob") or {}).get("conjunction_n"),
        "scares": {s["scare"]: {"score": s.get("score"), "band": s.get("band")}
                   for s in (snap.get("scares") or [])},
        "drawdown_prob": snap.get("drawdown_prob"),
        # de-escalation trajectory (engine/risk_radar.trajectory) — slim record so a future
        # recovery audit can grade whether "peaking/receding" actually preceded a rebound.
        "traj_phase": (snap.get("trajectory") or {}).get("phase"),
        "traj_intensity": (snap.get("trajectory") or {}).get("intensity"),
        "traj_off_peak": (snap.get("trajectory") or {}).get("off_peak"),
        "traj_odds_now": (snap.get("trajectory") or {}).get("odds_now"),
        # W1-S3 enabling fields (§8 ruling 2026-07-04): the DE-ESCALATION verdict and
        # dislocation switch were never logged, so S3's retro-derivation had a ZERO-day
        # overlap window for its pre-registered reconstruction check (→ moved to W3+).
        # Logging them from today makes the check possible when the window matures.
        "deescalation_eligible": (snap.get("deescalation") or {}).get("eligible"),
        "deescalation_reason": (snap.get("deescalation") or {}).get("reason"),
        "dislocation_active": snap.get("dislocation_active"),
        "logged_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "graded": None,
    }


def log_snapshot(snap: dict, root=None) -> bool:
    """Append today's snapshot to the forward log (idempotent by as-of). Returns True if added.
    Ledger-advancing lanes only (ledger_lane_armed): off-lane calls no-op, returning False."""
    try:
        if not ledger_lane_armed():
            log.debug("risk_radar_audit log skipped: lane not armed")
            return False
        entry = _entry_from_snapshot(snap)
        if entry is None:
            return False
        p = _path(root)
        rows = _read(p)
        if any(r.get("asof") == entry["asof"] for r in rows):
            return False
        rows.append(entry)
        _write(p, rows)
        return True
    except Exception as e:  # noqa: BLE001 — never fatal
        log.warning("risk_radar_audit log failed: %s", e)
        return False


def _spy():
    df = store.read("yahoo", "SPY")
    if df is None or "close" not in df:
        return None
    s = df["close"].dropna()
    s.index = pd.to_datetime(s.index)
    return s.sort_index()


def _grade_entry(entry: dict, spy: pd.Series) -> dict | None:
    """Realized forward max-drawdown per horizon from the as-of date; mark hit + outcome.
    Returns the 'graded' dict, or None if the longest horizon hasn't matured yet."""
    asof = pd.Timestamp(entry["asof"])
    loc = spy.index.searchsorted(asof, side="right")     # first bar strictly after as-of
    maxH = max(HORIZONS.values())
    if loc + maxH > len(spy):
        return None                                       # not matured
    base_loc = max(0, loc - 1)
    base_px = float(spy.iloc[base_loc])
    fwd_dd, hit = {}, {}
    for hk, hd in HORIZONS.items():
        w = spy.iloc[loc: loc + hd]
        dd = float(w.min() / base_px - 1.0) if len(w) else None
        fwd_dd[hk] = None if dd is None else round(dd, 4)
        hit[hk] = {f"dd{int(t*100)}": (dd is not None and dd <= -t) for t in DD_THRESHOLDS}
    any_primary = any(fwd_dd[hk] is not None and fwd_dd[hk] <= -PRIMARY_DD for hk in HORIZONS)
    is_alert = entry.get("state") in ALERT_STATES
    outcome = None
    if is_alert:
        outcome = "true_positive" if any_primary else "false_positive"
    elif entry.get("state") in ("watch", "caution"):
        outcome = "tp_watch" if any_primary else "tn_watch"
    else:
        outcome = "calm_dd" if any_primary else "calm_quiet"
    return {"base_px": round(base_px, 2), "fwd_dd": fwd_dd, "hit": hit,
            "outcome": outcome, "any_dd5_within_h21": bool(any_primary),
            "graded_at": datetime.now(timezone.utc).isoformat(timespec="seconds")}


def grade_log(root=None) -> int:
    """Grade every matured, ungraded entry against the realized SPY path. Returns # newly graded.

    Ledger-advancing lanes only (ledger_lane_armed): grades are keep-first-permanent,
    so an off-lane grade computed from a mid-session store would stick — no-op, 0.
    """
    try:
        if not ledger_lane_armed():
            log.debug("risk_radar_audit grade skipped: lane not armed")
            return 0
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
        log.warning("risk_radar_audit grade failed: %s", e)
        return 0


def scorecard(root=None) -> dict:
    """Rolling realized-accuracy scorecard from the graded log: overall alert precision, per-state
    hit-rate, per-dominant-scare precision, and recent mistakes (FPs + missed drawdowns). What the
    dashboard shows + the Opus review reads. Never raises."""
    try:
        rows = [r for r in _read(_path(root)) if r.get("graded")]
    except Exception:  # noqa: BLE001
        rows = []
    if not rows:
        return {"n_graded": 0, "note": "no matured entries yet"}
    alerts = [r for r in rows if r.get("alert")]
    tp = [r for r in alerts if r["graded"]["outcome"] == "true_positive"]
    fp = [r for r in alerts if r["graded"]["outcome"] == "false_positive"]
    # recall: of all matured days that PRECEDED a >=5%/h21 drawdown, how many were alerted?
    pre = [r for r in rows if r["graded"].get("any_dd5_within_h21")]
    pre_alerted = [r for r in pre if r.get("alert")]
    by_state = {}
    for r in rows:
        st = r.get("state")
        d = by_state.setdefault(st, {"n": 0, "dd": 0})
        d["n"] += 1
        d["dd"] += int(bool(r["graded"].get("any_dd5_within_h21")))
    by_state = {k: {"n": v["n"], "hit_rate": round(v["dd"] / v["n"], 3) if v["n"] else None}
                for k, v in by_state.items()}
    mistakes = [{"asof": r["asof"], "state": r["state"], "dominant_scare": r.get("dominant_scare"),
                 "scares": r.get("scares"), "kind": r["graded"]["outcome"],
                 "fwd_dd_h21": r["graded"]["fwd_dd"].get("h21")}
                for r in rows
                if r["graded"]["outcome"] in ("false_positive",)
                or (not r.get("alert") and r["graded"].get("any_dd5_within_h21"))]  # FPs + misses
    return {
        "n_graded": len(rows),
        "alert_precision": round(len(tp) / len(alerts), 3) if alerts else None,
        "n_alerts": len(alerts), "n_true_pos": len(tp), "n_false_pos": len(fp),
        "recall_dd5_h21": round(len(pre_alerted) / len(pre), 3) if pre else None,
        "by_state": by_state,
        "recent_mistakes": sorted(mistakes, key=lambda m: m["asof"], reverse=True)[:25],
        "asof_range": [rows[0]["asof"], rows[-1]["asof"]],
    }


def snapshot_and_grade(snap: dict, root=None) -> dict:
    """Convenience for run.py: log today's snapshot, grade matured entries, return the scorecard
    (which the engine attaches to latest['risk_radar']['forward_log']).

    Off-lane (ledger_lane_armed() False) the log/grade legs no-op and this is a
    pure scorecard read — the display payload stays populated on the
    closing-bell / engine-render / render lanes without advancing the ledger."""
    log_snapshot(snap, root=root)
    grade_log(root=root)
    return scorecard(root=root)
