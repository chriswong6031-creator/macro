"""International Risk Radar — bounded, do-no-harm auto-calibration of the prob surface.

Closes the evergreen loop the audit (engine/risk_radar_intl_audit.py) opens. It reads the
GRADED forward-outcome log and nudges each market's displayed pullback-odds toward the odds
the radar ACTUALLY realized in that state — so the number on the card becomes measured from
the radar's own track record, not a hand-set prior. Deterministic, no LLM, fully auditable.

THREE GUARDS so a self-tuning gauge can't tune itself off a cliff:
  1. GATED — nothing until >= MIN_GRADED matured calls; a state's odds move only once it has
     fired on >= MIN_STATE_SAMPLES of them.
  2. CLAMPED + MONOTONE — every odds value stays in [0, .95], moves <= MAX_STEP per run, and
     the surface is forced non-decreasing calm→risk-off (a louder state can't imply calmer odds).
  3. DO-NO-HARM — the candidate surface must not WORSEN the Brier score on the graded log.

Accepted surfaces are written to data/risk_radar_intl/<key>_calibration.json (the overlay
engine/risk_radar_intl.compute reads); every proposal is appended to <key>_tune_log.jsonl.
Bands are left structural (only the displayed odds are tuned). Never raises.
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path

from engine import risk_radar_intl as R
from engine import risk_radar_intl_audit as A
from lib import config

log = logging.getLogger(__name__)

MIN_GRADED = 25
MIN_STATE_SAMPLES = 6
MAX_STEP = 0.05            # max odds move per (state, horizon) per run
BLEND = 0.5               # target = halfway between current odds and realized odds
STATES = ["calm", "watch", "caution", "elevated", "risk-off"]
HK = ("h5", "h10", "h21")


def _clamp(x, lo=0.0, hi=0.95):
    return max(lo, min(hi, x))


def _monotone(pc: dict) -> dict:
    """Force odds non-decreasing along calm→risk-off within each horizon."""
    for h in HK:
        run = 0.0
        for s in STATES:
            if s in pc[h]:
                run = max(run, pc[h][s])
                pc[h][s] = round(run, 3)
    return pc


def _brier(rows: list[dict], pc: dict) -> float:
    """Mean squared error of the h21 odds vs the realized 0/1 outcome over the graded log."""
    se = n = 0.0
    for r in rows:
        st = r.get("state")
        g = r.get("graded") or {}
        fdd = (g.get("fwd_dd") or {}).get("h21")
        if fdd is None:
            continue
        actual = 1.0 if fdd <= -A.PRIMARY_DD else 0.0
        p = pc.get("h21", {}).get(st)
        if p is None:
            continue
        se += (p - actual) ** 2
        n += 1
    return se / n if n else 1.0


def _calib_path(key: str, root=None) -> Path:
    base = config.data_dir() if root is None else (Path(root) / "data")
    p = base / "risk_radar_intl" / f"{key}_calibration.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    return p


def _log_review(key: str, root, record: dict) -> None:
    try:
        p = _calib_path(key, root).parent / f"{key}_tune_log.jsonl"
        with p.open("a") as fh:
            fh.write(json.dumps(record, separators=(",", ":"), default=str) + "\n")
    except Exception:  # noqa: BLE001
        pass


def tune(profile, root=None) -> dict:
    """One bounded calibration step for `profile`. Returns a status dict; never raises."""
    key = profile.key
    try:
        rows = [r for r in A._read(A._path(key, root)) if r.get("graded")]
        if len(rows) < MIN_GRADED:
            return {"status": "accruing", "n_graded": len(rows), "need": MIN_GRADED}
        cal = R._calib(profile, root)
        cur_pc, base = cal["prob_cal"], cal["prob_base"]
        realized = A.realized_odds(key, root)
        cand = {h: dict(cur_pc[h]) for h in HK}
        for h in HK:
            for s in STATES:
                cur = cur_pc[h].get(s, base[h])
                r = realized.get(s)
                if not r or r["n"] < MIN_STATE_SAMPLES:
                    cand[h][s] = round(cur, 3)
                    continue
                target = (1 - BLEND) * cur + BLEND * r[h]
                step = max(-MAX_STEP, min(MAX_STEP, target - cur))
                cand[h][s] = round(_clamp(cur + step), 3)
        cand = _monotone(cand)
        changed = any(abs(cand[h].get(s, 0) - cur_pc[h].get(s, base[h])) >= 0.005
                      for h in HK for s in STATES)
        brier_cur, brier_cand = _brier(rows, cur_pc), _brier(rows, cand)
        improves = brier_cand <= brier_cur + 1e-9
        decision = "apply" if (changed and improves) else "hold"
        if decision == "apply":
            payload = {"prob_cal": cand, "n_graded": len(rows),
                       "brier_before": round(brier_cur, 4), "brier_after": round(brier_cand, 4),
                       "updated": datetime.now(timezone.utc).isoformat(timespec="seconds")}
            _calib_path(key, root).write_text(json.dumps(payload, indent=2))
        rec = {"asof": rows[-1]["asof"], "ts": datetime.now(timezone.utc).isoformat(timespec="seconds"),
               "n_graded": len(rows), "decision": decision,
               "brier": {"current": round(brier_cur, 4), "candidate": round(brier_cand, 4)},
               "realized": realized}
        _log_review(key, root, rec)
        return {"status": decision, "n_graded": len(rows),
                "brier": rec["brier"], "realized": realized}
    except Exception as e:  # noqa: BLE001
        log.warning("risk_radar_intl_tune(%s) failed: %s", key, e)
        return {"status": "error", "reason": str(e)}
