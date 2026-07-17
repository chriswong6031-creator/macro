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

CAN_FORCE — ARTICLE-3 GATE (W7a)
---------------------------------
`can_force` is now gated by a Wilson-CI lower-bound lift (Article 3) rather than a
point-estimate threshold.  The Wilson lower bound at the 90%-confidence level (z=1.645)
must exceed 1.25× the base drawdown rate — matching the retired point-estimate floor of
1.25 but measured on the CI lower bound instead of the point estimate.  Because
wilson_lb <= point_estimate always, the CI gate is strictly tighter everywhere: zero
grant-more cases across the full (k, n, base) space.  At minimum sample sizes (n_alerts=8)
the old point-estimate gate false-granted ~44% of the time under the null; the Wilson
gate reduces this to ~5.8%.  This is the conservative / authority-revoking direction:
markets that previously cleared the point-estimate gate may lose can_force; no market
can gain force authority it did not have under the old gate.

When the grant state changes vs the previous scorecard call, authority_grant or
authority_lapse events are appended to data/neuralweb/governance.jsonl via
engine.neuralweb.governance (fail-open — a governance-write failure never aborts the
audit).
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
# --- gate for earning the right to hard-force the verdict (Article 3) ---
MIN_GRADED_FORCE = 30      # need this many matured calls before forcing is even considered
MIN_ALERTS_FORCE = 8       # and this many loud calls among them
# NOTE: MIN_FORCE_LIFT (point-estimate 1.25) REMOVED — replaced by Wilson CI lift > 1.25
# The Wilson lower-bound gate (z=1.645, 90% one-sided) is evaluated inside scorecard().
# Threshold 1.25 matches the retired point-estimate floor; because wilson_lb <= point_estimate
# always, the CI gate is strictly tighter everywhere (zero grant-more cases, verified in tests).
# At n_alerts=8 the old gate false-granted ~44% under the null; Wilson reduces this to ~5.8%.


def ledger_lane_armed() -> bool:
    """True only on the nightly collect lane (COLLECT_LANE=nightly, legacy alias
    US_LANE). House law: nightly is the SOLE advancer of data/ forward ledgers —
    the engine-render/render re-render lanes and closing-bell run the CN/HK/CA/intl
    builds too; on those lanes the radar snapshot still renders but snapshot_and_grade
    and the tuner must not advance (a mid-session append is PIT-inconsistent and,
    being idempotent-by-asof, would permanently displace the nightly row). Canonical
    home for the gate; engine/intl_run._ledger_lane_armed delegates here."""
    import os
    lane = os.environ.get("COLLECT_LANE", "") or os.environ.get("US_LANE", "")
    return lane.lower() == "nightly"


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


def _load_previous_can_force(market: str, root=None) -> bool | None:
    """Read the last can_force value written for this market (for change detection).

    Returns None when no previous scorecard exists.  Never raises.
    """
    try:
        if root is None:
            base = config.data_dir()
        else:
            base = Path(root) / "data"
        # Previous can_force lives in the risk_radar payload inside latest.json
        for region_dir in ("", "china_regime/", "hk_regime/", "canada_regime/"):
            p = Path(base) / f"{region_dir}latest.json"
            if p.exists():
                try:
                    obj = json.loads(p.read_text())
                    fwd = (obj.get("risk_radar") or {}).get("forward_log") or {}
                    if fwd.get("market") == market and "can_force" in fwd:
                        return bool(fwd["can_force"])
                except Exception:  # noqa: BLE001
                    pass
        # 7-market intl payload: data/intl/latest.json records[*].risk_radar.forward_log
        p = Path(base) / "intl" / "latest.json"
        if p.exists():
            try:
                obj = json.loads(p.read_text())
                for rec in (obj.get("records") or []):
                    fwd = ((rec.get("risk_radar") or {}).get("forward_log") or {})
                    if fwd.get("market") == market and "can_force" in fwd:
                        return bool(fwd["can_force"])
            except Exception:  # noqa: BLE001
                pass
    except Exception:  # noqa: BLE001
        pass
    return None


def _log_can_force_governance(
    market: str,
    can_force: bool,
    prev_can_force: bool | None,
    hits: int,
    n_alerts: int,
    base: float,
    wilson_lb: float | None,
    lift_lb: float | None,
    grant_reason: str,
    evidence_asof: str | None,
    root=None,
) -> None:
    """Append authority_grant or authority_lapse to the governance ledger when can_force changes.

    Fail-open: exceptions are logged but never propagated.
    """
    try:
        if prev_can_force is None or can_force == prev_can_force:
            return  # no state change — nothing to log
        from engine.neuralweb.governance import append_event  # type: ignore[import]
        event_type = "authority_grant" if can_force else "authority_lapse"
        target = f"engine/risk_radar_intl_audit.can_force:{market}"
        append_event(
            event_type,
            target,
            article=3,
            authored_by="risk_radar_intl_audit",
            evidence={
                "hits": hits,
                "n_alerts": n_alerts,
                "base_rate": round(base, 4),
                "wilson_lb": wilson_lb,
                "lift_lb": lift_lb,
                "evidence_asof": evidence_asof,
            },
            before={"can_force": prev_can_force},
            after={"can_force": can_force},
            note=grant_reason,
            root=root,
        )
    except Exception as exc:  # noqa: BLE001
        log.warning("risk_radar_intl_audit: governance log failed for %s: %s", market, exc)


def scorecard(market: str, root=None, log_governance: bool = True) -> dict:
    """Rolling realized-accuracy scorecard from the graded log. Carries `can_force`: whether this
    market's radar has earned the right to hard-force the Market-State verdict. Never raises.

    ARTICLE-3 GATE (W7a): can_force is now granted via Wilson CI lower-bound lift > 1.25
    at z=1.645 (90% one-sided).  Threshold 1.25 matches the retired point-estimate floor;
    because wilson_lb <= point_estimate always, the CI gate is strictly tighter everywhere
    (zero grant-more cases across all k/n/base — verified in tests).  Additive scorecard
    fields: wilson_lift_lb, grant_reason, evidence_asof.  Existing consumers read only
    the can_force bool — these additions are backward-compatible.

    ``log_governance=False`` makes the call fully READ-ONLY: the authority_grant/lapse
    append to the governance ledger is skipped. The intraday live fast-path
    (scripts/build_china_risk_state.py) uses this to reproduce the board's can_force
    without writing — the nightly snapshot_and_grade remains the sole governance writer.
    """
    try:
        rows = [r for r in _read(_path(market, root)) if r.get("graded")]
    except Exception:  # noqa: BLE001
        rows = []
    if not rows:
        return {"market": market, "n_graded": 0, "can_force": False,
                "wilson_lift_lb": None, "grant_reason": "accruing",
                "evidence_asof": None,
                "note": "accruing — grades begin once calls mature (~21 trading days)"}
    n = len(rows)
    base = sum(int(r["graded"].get("any_dd5_within_h21")) for r in rows) / n
    alerts = [r for r in rows if r.get("alert")]
    tp = [r for r in alerts if r["graded"]["outcome"] == "true_positive"]
    alert_hit_count = sum(int(r["graded"].get("any_dd5_within_h21")) for r in alerts)
    alert_hit = alert_hit_count / len(alerts) if alerts else None
    by_state = {}
    for r in rows:
        d = by_state.setdefault(r.get("state"), {"n": 0, "dd": 0})
        d["n"] += 1
        d["dd"] += int(bool(r["graded"].get("any_dd5_within_h21")))
    by_state = {k: {"n": v["n"], "hit_rate": round(v["dd"] / v["n"], 3)} for k, v in by_state.items()}
    # point-estimate lift kept for display only (not the gate)
    force_lift = round(alert_hit / base, 2) if (alert_hit is not None and base) else None

    # Article-3 Wilson CI gate (replaces point-estimate >= 1.25)
    evidence_asof = rows[-1]["asof"] if rows else None
    wilson_lb: float | None = None
    lift_lb: float | None = None
    grant_reason: str = "accruing"
    can_force: bool = False

    n_alerts = len(alerts)
    if n >= MIN_GRADED_FORCE and n_alerts >= MIN_ALERTS_FORCE:
        try:
            from engine.neuralweb.constitution import grant_authority  # type: ignore[import]
            result = grant_authority(
                evidence={
                    "hits": alert_hit_count,
                    "n": n_alerts,
                    "base_rate": base,
                    "evidence_asof": evidence_asof,
                },
                floors={"min_n": MIN_GRADED_FORCE, "min_events": MIN_ALERTS_FORCE},
            )
            can_force = result.granted
            wilson_lb = result.wilson_lb
            lift_lb = result.lift_lb
            grant_reason = result.reason
        except Exception as exc:  # noqa: BLE001
            log.warning("risk_radar_intl_audit: constitution gate failed for %s: %s", market, exc)
            grant_reason = f"gate-error: {exc}"
    else:
        grant_reason = (f"n-floors-not-met: n_graded={n} (need {MIN_GRADED_FORCE}), "
                        f"n_alerts={n_alerts} (need {MIN_ALERTS_FORCE})")

    # Governance ledger: log when grant state changes (skipped on read-only calls)
    if log_governance:
        try:
            prev_cf = _load_previous_can_force(market, root)
            _log_can_force_governance(
                market=market,
                can_force=can_force,
                prev_can_force=prev_cf,
                hits=alert_hit_count,
                n_alerts=n_alerts,
                base=base,
                wilson_lb=wilson_lb,
                lift_lb=lift_lb,
                grant_reason=grant_reason,
                evidence_asof=evidence_asof,
                root=root,
            )
        except Exception as exc:  # noqa: BLE001
            log.warning("risk_radar_intl_audit: governance logging failed for %s: %s", market, exc)

    mistakes = [{"asof": r["asof"], "state": r["state"], "dominant_scare": r.get("dominant_scare"),
                 "fwd_dd_h21": r["graded"]["fwd_dd"].get("h21"), "kind": r["graded"]["outcome"]}
                for r in rows if r["graded"]["outcome"] == "false_positive"
                or (not r.get("alert") and r["graded"].get("any_dd5_within_h21"))]
    return {
        "market": market,
        "n_graded": n,
        "base_rate_dd5_h21": round(base, 3),
        "alert_precision": round(len(tp) / len(alerts), 3) if alerts else None,
        "n_alerts": n_alerts,
        "alert_hit_rate": round(alert_hit, 3) if alert_hit is not None else None,
        "force_lift": force_lift,
        "can_force": can_force,
        # Additive Article-3 fields (existing consumers read only the bool above)
        "wilson_lift_lb": lift_lb,
        "grant_reason": grant_reason,
        "evidence_asof": evidence_asof,
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
