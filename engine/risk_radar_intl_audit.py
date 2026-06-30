"""International Risk Radar — per-market forward-outcome log + deterministic grading.

The sibling of engine/risk_radar_audit.py (US) for the China / HK / Canada radars
(engine/risk_radar_intl.py). Every daily snapshot is APPENDED to
data/risk_radar_intl/<market>_forward_log.jsonl (idempotent by as-of). Once an entry's
horizon matures it is GRADED against that market's OWN realized index path: did a
>=5% drawdown actually occur within H business days? Each loud call is then a true- or
false-positive. The rolling scorecard (realized precision / per-state hit-rate /
predicted-vs-realized odds) is what the card surfaces, what the bounded tuner
(engine/risk_radar_intl_tune.py) recalibrates from, and what gates whether a market's
radar has earned the right to HARD-FORCE the Market-State verdict (`can_force`).

These radars ship DISPLAY-ONLY (verdict untouched) until each one's own log matures and
clears the bar — accountable by construction, never trusted on faith. Never raises.
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
DD_THRESHOLDS = (0.05, 0.08)
PRIMARY_DD = 0.05
ALERT_STATES = ("elevated", "risk-off")            # the loud tiers, for precision
# --- gate for earning the right to hard-force the verdict ---
MIN_GRADED_FORCE = 30      # need this many matured calls before forcing is even considered
MIN_ALERTS_FORCE = 8       # and this many loud calls among them
MIN_FORCE_LIFT = 1.25      # realized alert-state drawdown rate must beat base by this much


def _path(market: str, root=None) -> Path:
    base = config.data_dir() if root is None else (Path(root) / "data")
    p = base / "risk_radar_intl" / f"{market}_forward_log.jsonl"
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
    if not snap or not snap.get("asof") or snap.get("state") is None:
        return None
    return {
        "asof": str(snap["asof"]),
        "market": snap.get("market"),
        "state": snap.get("state"),
        "alert": snap.get("state") in ALERT_STATES,
        "dominant_scare": snap.get("dominant_scare"),
        "top_score": snap.get("top_score"),
        "conjunction": bool(snap.get("conjunction")),
        "scares": {s["scare"]: {"score": s.get("score"), "band": s.get("band")}
                   for s in (snap.get("scares") or [])},
        "drawdown_prob": snap.get("drawdown_prob"),
        # de-escalation trajectory (engine/risk_radar_intl._trajectory) — for a future recovery audit.
        "traj_phase": (snap.get("trajectory") or {}).get("phase"),
        "traj_intensity": (snap.get("trajectory") or {}).get("intensity"),
        "traj_off_peak": (snap.get("trajectory") or {}).get("off_peak"),
        "traj_odds_now": (snap.get("trajectory") or {}).get("odds_now"),
        "logged_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "graded": None,
    }


def log_snapshot(snap: dict, market: str, root=None) -> bool:
    """Append today's snapshot to the market's forward log (idempotent by as-of)."""
    try:
        entry = _entry_from_snapshot(snap)
        if entry is None:
            return False
        p = _path(market, root)
        rows = _read(p)
        if any(r.get("asof") == entry["asof"] for r in rows):
            return False
        rows.append(entry)
        _write(p, rows)
        return True
    except Exception as e:  # noqa: BLE001
        log.warning("risk_radar_intl_audit log(%s) failed: %s", market, e)
        return False


def _bench(profile) -> pd.Series | None:
    try:
        df = store.read(*profile.bench)
        if df is None or getattr(df, "empty", True):
            return None
        c = "close" if "close" in df.columns else df.columns[0]
        s = df[c].dropna()
        s.index = pd.to_datetime(s.index)
        return s.sort_index()
    except Exception:  # noqa: BLE001
        return None


def _grade_entry(entry: dict, px: pd.Series) -> dict | None:
    """Realized forward max-drawdown per horizon from the as-of date; mark hit + outcome.
    None until the longest horizon has matured."""
    asof = pd.Timestamp(entry["asof"])
    loc = px.index.searchsorted(asof, side="right")
    maxH = max(HORIZONS.values())
    if loc + maxH > len(px):
        return None
    base_px = float(px.iloc[max(0, loc - 1)])
    fwd_dd, hit = {}, {}
    for hk, hd in HORIZONS.items():
        w = px.iloc[loc: loc + hd]
        dd = float(w.min() / base_px - 1.0) if len(w) else None
        fwd_dd[hk] = None if dd is None else round(dd, 4)
        hit[hk] = {f"dd{int(t*100)}": (dd is not None and dd <= -t) for t in DD_THRESHOLDS}
    any_primary = any(fwd_dd[hk] is not None and fwd_dd[hk] <= -PRIMARY_DD for hk in HORIZONS)
    st = entry.get("state")
    if st in ALERT_STATES:
        outcome = "true_positive" if any_primary else "false_positive"
    elif st in ("watch", "caution"):
        outcome = "tp_watch" if any_primary else "tn_watch"
    else:
        outcome = "calm_dd" if any_primary else "calm_quiet"
    return {"base_px": round(base_px, 2), "fwd_dd": fwd_dd, "hit": hit,
            "outcome": outcome, "any_dd5_within_h21": bool(any_primary),
            "graded_at": datetime.now(timezone.utc).isoformat(timespec="seconds")}


def grade_log(profile, root=None) -> int:
    """Grade every matured, ungraded entry against the market's realized index path."""
    try:
        p = _path(profile.key, root)
        rows = _read(p)
        if not rows:
            return 0
        px = _bench(profile)
        if px is None:
            return 0
        n = 0
        for r in rows:
            if r.get("graded"):
                continue
            g = _grade_entry(r, px)
            if g is not None:
                r["graded"] = g
                n += 1
        if n:
            _write(p, rows)
        return n
    except Exception as e:  # noqa: BLE001
        log.warning("risk_radar_intl_audit grade(%s) failed: %s", getattr(profile, "key", "?"), e)
        return 0


def realized_odds(market: str, root=None) -> dict:
    """Per-state realized P(>=5% drawdown within h) from the graded log — the empirical truth
    the tuner recalibrates the prob surface toward. {state: {h5,h10,h21, n}}."""
    rows = [r for r in _read(_path(market, root)) if r.get("graded")]
    out: dict[str, dict] = {}
    for r in rows:
        st = r.get("state")
        d = out.setdefault(st, {"n": 0, "h5": 0, "h10": 0, "h21": 0})
        d["n"] += 1
        g = r["graded"]
        for hk in HORIZONS:
            fdd = (g.get("fwd_dd") or {}).get(hk)
            d[hk] += int(fdd is not None and fdd <= -PRIMARY_DD)
    return {st: {"n": d["n"], **{hk: round(d[hk] / d["n"], 3) for hk in HORIZONS}}
            for st, d in out.items() if d["n"]}


def scorecard(market: str, root=None) -> dict:
    """Rolling realized-accuracy scorecard from the graded log. Carries `can_force`: whether this
    market's radar has earned the right to hard-force the Market-State verdict. Never raises."""
    try:
        rows = [r for r in _read(_path(market, root)) if r.get("graded")]
    except Exception:  # noqa: BLE001
        rows = []
    if not rows:
        return {"market": market, "n_graded": 0, "can_force": False,
                "note": "accruing — grades begin once calls mature (~21 trading days)"}
    n = len(rows)
    base = sum(int(r["graded"].get("any_dd5_within_h21")) for r in rows) / n
    alerts = [r for r in rows if r.get("alert")]
    tp = [r for r in alerts if r["graded"]["outcome"] == "true_positive"]
    alert_hit = (sum(int(r["graded"].get("any_dd5_within_h21")) for r in alerts) / len(alerts)
                 if alerts else None)
    by_state = {}
    for r in rows:
        d = by_state.setdefault(r.get("state"), {"n": 0, "dd": 0})
        d["n"] += 1
        d["dd"] += int(bool(r["graded"].get("any_dd5_within_h21")))
    by_state = {k: {"n": v["n"], "hit_rate": round(v["dd"] / v["n"], 3)} for k, v in by_state.items()}
    force_lift = round(alert_hit / base, 2) if (alert_hit is not None and base) else None
    can_force = bool(n >= MIN_GRADED_FORCE and len(alerts) >= MIN_ALERTS_FORCE
                     and force_lift is not None and force_lift >= MIN_FORCE_LIFT)
    mistakes = [{"asof": r["asof"], "state": r["state"], "dominant_scare": r.get("dominant_scare"),
                 "fwd_dd_h21": r["graded"]["fwd_dd"].get("h21"), "kind": r["graded"]["outcome"]}
                for r in rows if r["graded"]["outcome"] == "false_positive"
                or (not r.get("alert") and r["graded"].get("any_dd5_within_h21"))]
    return {
        "market": market,
        "n_graded": n,
        "base_rate_dd5_h21": round(base, 3),
        "alert_precision": round(len(tp) / len(alerts), 3) if alerts else None,
        "n_alerts": len(alerts),
        "alert_hit_rate": round(alert_hit, 3) if alert_hit is not None else None,
        "force_lift": force_lift,
        "can_force": can_force,
        "by_state": by_state,
        "realized_odds": realized_odds(market, root),
        "recent_mistakes": sorted(mistakes, key=lambda m: m["asof"], reverse=True)[:20],
        "asof_range": [rows[0]["asof"], rows[-1]["asof"]],
    }


def snapshot_and_grade(snap: dict, profile, root=None) -> dict:
    """Log today's snapshot, grade matured entries, return the scorecard (attached to
    latest['risk_radar']['forward_log'] by the build)."""
    log_snapshot(snap, profile.key, root=root)
    grade_log(profile, root=root)
    return scorecard(profile.key, root=root)
