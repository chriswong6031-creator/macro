"""Market State amplification — bounded, do-no-harm auto-calibration of the corroborator weights.

This closes the evergreen loop the self-audit opened (engine/market_state_audit.py). It reads
the GRADED forward-outcome log, measures each corroborator's realized forward-drawdown lift,
and nudges the per-corroborator amplification weight toward that lift — so a signal that
reliably precedes drawdowns pulls the Market-State verdict harder and one that does not gets
pruned toward zero. No human re-picks the weights and (unlike the radar's loop) no LLM is in
the path — the mapping is deterministic and fully auditable.

THREE GUARDS so a self-tuning risk gauge can't tune itself off a cliff:
  1. GATED — does nothing until >= MIN_GRADED matured calls exist, and only adjusts a
     corroborator that has fired on >= MIN_SAMPLES of them.
  2. CLAMPED — every weight stays in [0, 12] and moves at most MAX_STEP per run.
  3. DO-NO-HARM BACKTEST — the candidate weights are RE-RUN over the whole graded log via the
     SAME engine.market_state._ceiling_for the live override uses (so production and the
     backtest can never diverge); applied only if risk-call F1 does not drop AND false
     positives do not rise. Otherwise it holds.

Accepted weights are written to data/market_state/calibration.json (the overlay the engine
reads); every proposal + verdict is appended to data/market_state/tune_log.jsonl. Never raises.
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path

from engine import market_state as M
from engine.market_state_audit import _path as _log_path
from engine.market_state_audit import _read as _read_log

log = logging.getLogger(__name__)

MIN_GRADED = 20        # don't tune until this many matured calls accrue
MIN_SAMPLES = 8        # per-corroborator min firings before its weight is adjusted
MAX_STEP = 3.0         # max weight change per run (points)
NEUTRAL_W = 6.0        # lift == 1.0 maps back to the default pull


def _calib_path(root=None) -> Path:
    base = M_config_data_dir(root)
    p = base / "market_state" / "calibration.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    return p


def M_config_data_dir(root=None) -> Path:
    from lib import config
    return config.data_dir() if root is None else (Path(root) / "data")


def _graded(root=None) -> list[dict]:
    return [r for r in _read_log(_log_path(root)) if r.get("graded")]


def _corr_lift(rows: list[dict]) -> tuple[dict, float]:
    """Weight-INDEPENDENT realized lift per corroborator: among graded calls where the flag
    fired, the rate a >=5% drawdown followed, vs the base rate over all graded calls."""
    n = len(rows)
    base = sum(int(r["graded"].get("any_dd5_within_h21")) for r in rows) / n if n else 0.0
    out = {}
    for k in M.CORROBORATORS:
        with_k = [r for r in rows if k in (r.get("amp_keys") or [])]
        if len(with_k) < MIN_SAMPLES:
            continue
        hit = sum(int(r["graded"].get("any_dd5_within_h21")) for r in with_k) / len(with_k)
        out[k] = {"n": len(with_k), "hit": round(hit, 3),
                  "lift": round(hit / base, 2) if base else None}
    return out, round(base, 3)


def _propose(current_w: dict, corr_lift: dict) -> dict:
    """Target weight = NEUTRAL_W * realized lift (clamped); move there by <= MAX_STEP/run.
    Corroborators without enough samples (or no measurable base) are left untouched."""
    lo, hi = M._WEIGHT_BOUNDS
    new = {}
    for k in M.CORROBORATORS:
        cur = float(current_w.get(k, NEUTRAL_W))
        info = corr_lift.get(k)
        if not info or info.get("lift") is None:
            new[k] = cur
            continue
        target = min(hi, max(lo, NEUTRAL_W * info["lift"]))
        step = max(-MAX_STEP, min(MAX_STEP, target - cur))
        new[k] = round(cur + step, 1)
    return new


def _backtest(rows: list[dict], calib: dict) -> dict:
    """Re-derive each graded call's verdict under `calib` (shared _ceiling_for) and score the
    risk call vs the realized path: precision / recall / F1 / false-positives."""
    tp = fp = n_risk = dd_days = dd_called = 0
    for r in rows:
        dd = bool(r["graded"].get("any_dd5_within_h21"))
        dd_days += int(dd)
        ceil = M._ceiling_for(r.get("radar_state"), bool(r.get("severe_gated")),
                              r.get("amp_keys") or [], calib)
        if ceil is None:                       # calm state: weight-independent, keep logged verdict
            verdict = r.get("verdict")
        else:
            raw = r.get("raw_score")
            raw = 50 if raw is None else raw
            verdict = M._verdict_from_score(min(raw, ceil))
        if verdict == "RISK_OFF":
            n_risk += 1
            if dd:
                tp += 1
                dd_called += 1
            else:
                fp += 1
        elif dd:
            pass  # a missed drawdown (quiet call); counted in recall denominator below
    precision = tp / n_risk if n_risk else 0.0
    recall = dd_called / dd_days if dd_days else 0.0
    f1 = (2 * precision * recall / (precision + recall)) if (precision + recall) else 0.0
    return {"precision": round(precision, 3), "recall": round(recall, 3),
            "f1": round(f1, 3), "n_risk": n_risk, "tp": tp, "fp": fp}


def _write_calib(root, calib: dict, base_rate: float, n_graded: int) -> None:
    payload = {"weights": {k: calib["weights"][k] for k in M.CORROBORATORS},
               "base": calib["base"], "severe_bump": calib.get("severe_bump", 10),
               "floor": calib.get("floor", 12), "base_rate_dd5": base_rate,
               "n_graded": n_graded,
               "updated": datetime.now(timezone.utc).isoformat(timespec="seconds")}
    _calib_path(root).write_text(json.dumps(payload, indent=2))


def _log_review(root, record: dict) -> None:
    try:
        p = M_config_data_dir(root) / "market_state" / "tune_log.jsonl"
        p.parent.mkdir(parents=True, exist_ok=True)
        with p.open("a") as fh:
            fh.write(json.dumps(record, separators=(",", ":"), default=str) + "\n")
    except Exception:  # noqa: BLE001
        pass


def tune(root=None) -> dict:
    """Run one bounded calibration step. Returns a status dict; never raises into the build."""
    try:
        rows = _graded(root)
        if len(rows) < MIN_GRADED:
            return {"status": "accruing", "n_graded": len(rows), "need": MIN_GRADED}
        current = M._ms_calib(root=root)
        corr_lift, base_rate = _corr_lift(rows)
        cand_w = _propose(current["weights"], corr_lift)
        candidate = {**current, "weights": cand_w}
        bt_cur = _backtest(rows, current)
        bt_cand = _backtest(rows, candidate)
        changed = any(abs(cand_w[k] - current["weights"].get(k, NEUTRAL_W)) >= 0.1
                      for k in M.CORROBORATORS)
        # do-no-harm: no F1 regression AND no extra false positives
        improves = bt_cand["f1"] >= bt_cur["f1"] and bt_cand["fp"] <= bt_cur["fp"]
        decision = "apply" if (changed and improves) else "hold"
        if decision == "apply":
            _write_calib(root, candidate, base_rate, len(rows))
        rec = {"asof": rows[-1]["asof"], "ts": datetime.now(timezone.utc).isoformat(timespec="seconds"),
               "n_graded": len(rows), "base_rate_dd5": base_rate, "decision": decision,
               "corr_lift": corr_lift, "from": current["weights"], "to": cand_w,
               "backtest": {"current": bt_cur, "candidate": bt_cand}}
        _log_review(root, rec)
        return {"status": decision, "n_graded": len(rows), "weights": cand_w,
                "backtest": rec["backtest"], "corr_lift": corr_lift}
    except Exception as e:  # noqa: BLE001 — never fatal
        log.warning("market_state_tune failed: %s", e)
        return {"status": "error", "reason": str(e)}
