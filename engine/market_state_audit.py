"""Market State — forward-outcome log + deterministic grading + corroborator attribution.

The sibling of engine/risk_radar_audit.py, for the Market State verdict
(engine/market_state.py). Every daily Market State snapshot is APPENDED to
data/market_state/forward_log.jsonl (idempotent by as-of date; every writer self-gates
on ledger_lane_armed(), so off-lane renders are read-only). Once an entry's horizon
matures, it is GRADED deterministically against the realized SPY path: did a >= threshold
drawdown actually occur within H business days? A RISK_OFF verdict is then a true- or
false-positive; a quiet verdict that preceded a drawdown is a miss.

What makes this the EVERGREEN piece: the scorecard adds PER-CORROBORATOR attribution. For
each amplification flag the Risk-Radar override fired (conjunction, complacency, breadth_div,
drawdown_band, systemic_stress, turning_point, two_plus_scares) it measures how often a
drawdown actually followed when that corroborator was present in a risk-off call — i.e.
which corroborators genuinely LEAD drawdowns (keep / up-weight) and which are noise or lag
(prune / down-weight). That is the evidence the confluence multiplier should be tuned by
over time, instead of a human re-picking the weights. It accrues forward from first run,
exactly like the radar's loop; until entries mature the scorecard simply reports that.

Pure-ish + never raises into the build. No new data is fetched beyond the SPY close series
already in the price store.
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

from lib import config, store

log = logging.getLogger(__name__)

HORIZONS = {"h5": 5, "h10": 10, "h21": 21}        # business-day forward windows
PRIMARY_DD = 0.05                                  # a >=5% pullback = a "drawdown"
RISK_VERDICTS = ("RISK_OFF",)                      # the loud risk call graded for precision
# the full, stable corroborator vocabulary (must match engine.market_state._radar_override)
CORROBORATORS = ("conjunction", "two_plus_scares", "complacency", "breadth_div",
                 "drawdown_band", "systemic_stress", "turning_point")


def ledger_lane_armed() -> bool:
    """True only on a ledger-advancing collect lane (COLLECT_LANE=nightly, legacy
    alias US_LANE). House law: nightly is the SOLE advancer of data/ forward
    ledgers — this log's only advancing lane is daily.yml's engine job (job-level
    COLLECT_LANE=nightly; verified via git log on data/market_state/forward_log.jsonl:
    every advancing commit is that job's "engine: regime update"). The call site
    (scripts/build_site.py market_state_view) also runs on closing-bell (whose
    contract, closing-bell.yml, is that every ledger writer self-gates on
    COLLECT_LANE) and the engine-render/render re-render lanes; there the Market
    State card still renders and snapshot_and_grade degrades to a pure scorecard
    read, but log/grade must not advance — appends are idempotent-by-asof with
    FIRST-WRITER-WINS, so a mid-session off-lane append would permanently displace
    the nightly row. Canonical gate:
    engine/risk_radar_intl_audit.ledger_lane_armed (#2684); ignition sibling
    engine/ignition_audit.ledger_lane_armed (#2693)."""
    import os
    lane = os.environ.get("COLLECT_LANE", "") or os.environ.get("US_LANE", "")
    return lane.lower() == "nightly"


def _path(root=None) -> Path:
    base = config.data_dir() if root is None else (Path(root) / "data")
    p = base / "market_state" / "forward_log.jsonl"
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


def _extract_components(ms: dict) -> dict | None:
    """Extract per-component scores from a market_state_snapshot() result.

    The 'components' key in the snapshot is a list of dicts, each with
    {key, score, weight, ...}. We store a compact dict {key: {score, weight}}
    so the weights-vs-equal-weight measurement harness can reconstruct the
    hand-weighted raw_score and the equal-weight counterfactual from the same
    logged data (PIT-honest: whatever resolved that day).

    Returns None if the components field is absent or malformed — the caller
    omits the 'components' key from the log entry in that case, which is safe:
    the log is forward-append-only and older entries without 'components' are
    parsed by readers that treat the key as optional (additive-safe).
    """
    raw = ms.get("components")
    if not raw or not isinstance(raw, list):
        return None
    out: dict = {}
    for c in raw:
        if not isinstance(c, dict):
            continue
        key = c.get("key")
        score = c.get("score")
        weight = c.get("weight")
        if key is None:
            continue
        # score and weight may be None if a component failed to resolve;
        # store what is available so the harness can detect partial resolves.
        out[str(key)] = {
            "score": score,
            "weight": weight,
        }
    return out if out else None


def _entry_from_snapshot(ms: dict) -> dict | None:
    """Slim a market_state_snapshot() result to the loggable fields (no recompute).

    Existing fields (additive-safe — readers must not require 'components'):
      asof, verdict, score, raw_score, radar_state, radar_top, amp, amp_keys,
      severe_gated, logged_at, graded

    Added in W3 PR2 (additive key — old entries without it parse safely):
      components: {key: {score, weight}} for each resolved component.
        Enables the pre-registered market-state-weights-vs-equal measurement
        (h21 drawdown-concordance Brier, hand vs equal-weight counterfactual).
        Absent when the snapshot carries no 'components' list.
    """
    if not ms or not ms.get("asof") or not ms.get("verdict"):
        return None
    rd = ms.get("radar") or {}
    entry: dict = {
        "asof": str(ms["asof"]),
        "verdict": ms.get("verdict"),
        "score": ms.get("score"),
        "raw_score": ms.get("raw_score"),
        "radar_state": rd.get("state"),
        "radar_top": rd.get("top_score"),
        "amp": rd.get("amp"),
        "amp_keys": list(rd.get("amp_keys") or []),
        "severe_gated": bool(rd.get("severe_gated")),
        "logged_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "graded": None,
    }
    # W3 PR2 addition: per-component scores (additive — old entries lack this key)
    components = _extract_components(ms)
    if components is not None:
        entry["components"] = components
    return entry


def log_snapshot(ms: dict, root=None) -> bool:
    """Append today's Market State snapshot to the forward log (idempotent by as-of).
    Ledger-advancing lanes only (ledger_lane_armed): off-lane calls no-op, returning False."""
    try:
        if not ledger_lane_armed():
            log.debug("market_state_audit log skipped: lane not armed")
            return False
        entry = _entry_from_snapshot(ms)
        if entry is None:
            return False
        p = _path(root)
        rows = _read(p)
        # premise_repair rows share an as-of date with the real snapshot on the switch
        # date — skip them in the idempotency guard so the snapshot still lands.
        snapshot_rows = [r for r in rows if r.get("type") != "premise_repair"]
        if any(r.get("asof") == entry["asof"] for r in snapshot_rows):
            return False
        rows.append(entry)
        _write(p, rows)
        return True
    except Exception as e:  # noqa: BLE001 — never fatal
        log.warning("market_state_audit log failed: %s", e)
        return False


def _spy() -> pd.Series | None:
    try:
        df = store.read("yahoo", "SPY")
    except Exception:  # noqa: BLE001
        return None
    if df is None or "close" not in df:
        return None
    s = df["close"].dropna()
    s.index = pd.to_datetime(s.index)
    return s.sort_index()


def _grade_entry(entry: dict, spy: pd.Series) -> dict | None:
    """Realized forward max-drawdown per horizon from the as-of date; classify the verdict.
    Returns the 'graded' dict, or None if the longest horizon hasn't matured yet."""
    asof = pd.Timestamp(entry["asof"])
    loc = spy.index.searchsorted(asof, side="right")     # first bar strictly after as-of
    maxH = max(HORIZONS.values())
    if loc + maxH > len(spy):
        return None                                       # not matured
    base_px = float(spy.iloc[max(0, loc - 1)])
    fwd_dd = {}
    for hk, hd in HORIZONS.items():
        w = spy.iloc[loc: loc + hd]
        fwd_dd[hk] = round(float(w.min() / base_px - 1.0), 4) if len(w) else None
    any_dd5 = any(fwd_dd[hk] is not None and fwd_dd[hk] <= -PRIMARY_DD for hk in HORIZONS)
    is_risk = entry.get("verdict") in RISK_VERDICTS
    if is_risk:
        outcome = "true_positive" if any_dd5 else "false_positive"
    else:
        outcome = "miss" if any_dd5 else "quiet"          # quiet verdict that did / didn't precede a dd
    return {"base_px": round(base_px, 2), "fwd_dd": fwd_dd,
            "any_dd5_within_h21": bool(any_dd5), "outcome": outcome,
            "graded_at": datetime.now(timezone.utc).isoformat(timespec="seconds")}


def grade_log(root=None) -> int:
    """Grade every matured, ungraded entry against the realized SPY path. Returns # newly graded.

    Ledger-advancing lanes only (ledger_lane_armed): grades are keep-first-permanent,
    so an off-lane grade computed from a mid-session store would stick — no-op, 0.
    """
    try:
        if not ledger_lane_armed():
            log.debug("market_state_audit grade skipped: lane not armed")
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
            if r.get("type") == "premise_repair":   # disclosure row — not a scored snapshot
                continue
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
        log.warning("market_state_audit grade failed: %s", e)
        return 0


def scorecard(root=None) -> dict:
    """Rolling realized-accuracy scorecard from the graded log: risk-call precision, drawdown
    recall, per-verdict hit-rate, and PER-CORROBORATOR precision + lift (which amplification
    flags actually precede drawdowns). What the dashboard surfaces and a future bounded
    auto-tuner would read to re-weight / prune corroborators. Never raises."""
    try:
        rows = [r for r in _read(_path(root)) if r.get("graded")]
    except Exception:  # noqa: BLE001
        rows = []
    if not rows:
        return {"n_graded": 0, "note": "accruing — no matured entries yet"}
    base_rate = round(sum(int(r["graded"]["any_dd5_within_h21"]) for r in rows) / len(rows), 3)
    risk = [r for r in rows if r.get("verdict") in RISK_VERDICTS]
    tp = [r for r in risk if r["graded"]["outcome"] == "true_positive"]
    fp = [r for r in risk if r["graded"]["outcome"] == "false_positive"]
    pre = [r for r in rows if r["graded"].get("any_dd5_within_h21")]      # days that preceded a dd
    pre_called = [r for r in pre if r.get("verdict") in RISK_VERDICTS]
    by_verdict = {}
    for r in rows:
        d = by_verdict.setdefault(r.get("verdict"), {"n": 0, "dd": 0})
        d["n"] += 1
        d["dd"] += int(bool(r["graded"].get("any_dd5_within_h21")))
    by_verdict = {k: {"n": v["n"], "hit_rate": round(v["dd"] / v["n"], 3) if v["n"] else None}
                  for k, v in by_verdict.items()}
    # per-corroborator: precision of risk calls in which that flag was present, + lift vs base
    per_corr = {}
    for k in CORROBORATORS:
        with_k = [r for r in risk if k in (r.get("amp_keys") or [])]
        if not with_k:
            continue
        tp_k = sum(1 for r in with_k if r["graded"]["outcome"] == "true_positive")
        prec = round(tp_k / len(with_k), 3)
        per_corr[k] = {"n": len(with_k), "precision": prec,
                       "lift": round(prec / base_rate, 2) if base_rate else None}
    mistakes = [{"asof": r["asof"], "verdict": r["verdict"], "amp_keys": r.get("amp_keys"),
                 "kind": r["graded"]["outcome"], "fwd_dd_h21": r["graded"]["fwd_dd"].get("h21")}
                for r in rows
                if r["graded"]["outcome"] in ("false_positive", "miss")]
    return {
        "n_graded": len(rows),
        "base_rate_dd5": base_rate,
        "risk_precision": round(len(tp) / len(risk), 3) if risk else None,
        "risk_lift": round((len(tp) / len(risk)) / base_rate, 2) if risk and base_rate else None,
        "n_risk": len(risk), "n_true_pos": len(tp), "n_false_pos": len(fp),
        "recall_dd5": round(len(pre_called) / len(pre), 3) if pre else None,
        "by_verdict": by_verdict,
        "per_corroborator": per_corr,
        "recent_mistakes": sorted(mistakes, key=lambda m: m["asof"], reverse=True)[:25],
        "asof_range": [rows[0]["asof"], rows[-1]["asof"]],
    }


def snapshot_and_grade(ms: dict, root=None) -> dict:
    """Convenience for the build: log today's Market State snapshot, grade matured entries,
    and return the scorecard (attached to the snapshot as ms['audit'] for the dashboard).

    Off-lane (ledger_lane_armed() False) the log/grade legs no-op and this is a
    pure scorecard read — the display payload stays populated on the
    closing-bell / engine-render / render lanes without advancing the ledger."""
    log_snapshot(ms, root=root)
    grade_log(root=root)
    return scorecard(root=root)
