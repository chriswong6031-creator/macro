"""scripts/grade_cortex_attention.py — Nightly cortex attention grader + A2 earn-in.

SINGLE-WRITER: this script is the ONLY writer to
  data/reflexes/cortex_attention/grades.jsonl

WHAT IT DOES
------------
1. Reads data/reflexes/cortex_attention/firings.jsonl (attention claims).
2. Finds matured claims (asof + horizon_d elapsed as of today).
3. Grades each matured claim per falsifier class:
   - realized_move   → engine.grading.forward_metrics on the symbol (excess vs SPY)
   - escalation      → check alert artifact for downstream alert within horizon_d
   - verdict_change  → check world_state history for call change in predicted direction
4. Writes graded outcomes to data/reflexes/cortex_attention/grades.jsonl
   (sidecar rows, one per claim_id that matured).
5. Runs A2 earn-in via constitution.grant_authority on the graded record.
6. Writes result to data/neuralweb/cortex/probation.json (single source).
7. Appends governance events ON TRANSITIONS ONLY (granted ↔ refused).

GRADE SCHEMA (reflex.cortex_attention.grade.v1)
-----------------------------------------------
  claim_id          str   — matches the firings.jsonl claim_id
  graded_at         str   — ISO-8601 date (today)
  grader_version    str
  falsifier_class   str   realized_move | escalation | verdict_change | unknown
  outcome_hit       bool  — True if the falsifier criterion fired
  outcome_detail    dict  — evidence detail
  horizon_d         int
  asof              str
  symbol            str
  direction         int
  base_rate         float — estimated base rate for the criterion class

A2 EARN-IN
----------
  After grading, constitution.grant_authority is called with:
    hits  = graded rows where outcome_hit=True
    n     = all graded rows (outcome_graded_at not None)
    base_rate = 0.5 (prior for binary outcomes; updated if enough data)
    min_n = 25, min_events = 8
  Result → data/neuralweb/cortex/probation.json
  Governance event appended ON TRANSITIONS ONLY (refused→granted or granted→refused).

TODAY'S STATUS (2026-07-04):
  Attention record is empty → A2 refused (n=0 < 25).
  The probation.json is written with granted=False and the exact reason.
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any

log = logging.getLogger(__name__)

_GRADER_VERSION = "W7b-PR2"
_GRADE_SCHEMA = "reflex.cortex_attention.grade.v1"
_BASE_RATE_DEFAULT = 0.5   # conservative prior for binary outcome


# ---------------------------------------------------------------------------
# Path helpers
# ---------------------------------------------------------------------------

def _root_path(root: str | Path | None = None) -> Path:
    if root is not None:
        return Path(root)
    return Path(__file__).resolve().parent.parent


def _data(root: Path, *parts: str) -> Path:
    return root / "data" / Path(*parts)


def _firings_path(root: Path) -> Path:
    return _data(root, "reflexes", "cortex_attention", "firings.jsonl")


def _grades_path(root: Path) -> Path:
    return _data(root, "reflexes", "cortex_attention", "grades.jsonl")


def _probation_path(root: Path) -> Path:
    return _data(root, "neuralweb", "cortex", "probation.json")


# ---------------------------------------------------------------------------
# Load helpers
# ---------------------------------------------------------------------------

def _is_synthetic(row: dict) -> bool:
    """Return True if the row is a dry-run synthetic item that must be excluded from grading.

    Synthetic rows must never contribute to the probation counter (n) or hits — they are
    dry-run artefacts seeded at system initialisation, not real cortex attention events.
    Exclusion is at READ/GRADE time only; ledger rows are never deleted (append-only law).
    A row is synthetic if ANY of the following hold:
      - trigger_key == "SYNTHETIC_TICKER"  (legacy dry-run marker)
      - scope_key == "SYNTHETIC_TICKER"
      - "(dry-run synthetic item)" appears in the falsifier field
      - explicit field synthetic: true
    """
    trigger_key = str(row.get("trigger_key") or "")
    scope_key = str(row.get("scope_key") or "")
    falsifier = str(row.get("falsifier") or "")
    synthetic_flag = row.get("synthetic", False)
    return (
        trigger_key == "SYNTHETIC_TICKER"
        or scope_key == "SYNTHETIC_TICKER"
        or "(dry-run synthetic item)" in falsifier
        or synthetic_flag is True
    )


def _load_firings(root: Path) -> list[dict]:
    """Load real (non-synthetic) firing rows from firings.jsonl.

    Synthetic dry-run items (ticker=SYNTHETIC_TICKER or explicit marker) are excluded
    at read time — they must never enter the grading loop or the probation counter.
    The ledger itself is never modified (append-only law).
    """
    p = _firings_path(root)
    if not p.exists():
        return []
    rows = []
    for line in p.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            row = json.loads(line)
            if _is_synthetic(row):
                log.debug("grade_cortex_attention: skipping synthetic row claim_id=%s", row.get("claim_id", "?"))
                continue
            rows.append(row)
        except Exception:  # noqa: BLE001
            pass
    return rows


def _load_grades(root: Path) -> list[dict]:
    """Load real (non-synthetic) grade rows from grades.jsonl.

    Synthetic grades are excluded at read time so they never inflate n or hits.
    A grade row is synthetic if its symbol field is "SYNTHETIC_TICKER" or if the
    original claim_id matches a known synthetic seed (detected via the symbol field).
    Ledger rows are never deleted (append-only law).
    """
    p = _grades_path(root)
    if not p.exists():
        return []
    rows = []
    for line in p.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            row = json.loads(line)
            # Exclude grades whose subject symbol is the synthetic marker
            if str(row.get("symbol") or "") == "SYNTHETIC_TICKER":
                log.debug("grade_cortex_attention: skipping synthetic grade claim_id=%s", row.get("claim_id", "?"))
                continue
            rows.append(row)
        except Exception:  # noqa: BLE001
            pass
    return rows


def _graded_ids(root: Path) -> set[str]:
    return {r.get("claim_id") for r in _load_grades(root) if r.get("claim_id")}


# ---------------------------------------------------------------------------
# Falsifier class detection
# ---------------------------------------------------------------------------

def _detect_falsifier_class(claim: dict) -> str:
    """Detect falsifier class from the claim's falsifier field."""
    falsifier = str(claim.get("falsifier") or "").lower()
    if any(k in falsifier for k in ("move", "return", "price", "excess", "rally", "drop")):
        return "realized_move"
    elif any(k in falsifier for k in ("alert", "escalat", "fire", "trigger")):
        return "escalation"
    elif any(k in falsifier for k in ("verdict", "regime", "call", "change", "flip", "turn")):
        return "verdict_change"
    # Direction-1/+1 suggests realized_move; direction=0 means infrastructure
    direction = claim.get("direction", 0)
    if direction != 0:
        return "realized_move"
    return "unknown"


# ---------------------------------------------------------------------------
# Falsifier class graders
# ---------------------------------------------------------------------------

def _grade_realized_move(
    claim: dict,
    root: Path,
    today: date,
) -> tuple[bool, dict]:
    """Grade realized-move claims via forward_metrics vs SPY."""
    symbol = claim.get("scope_key") or claim.get("symbol") or ""
    horizon_d = int(claim.get("horizon_d") or 5)
    direction = int(claim.get("direction") or 1)
    asof_str = str(claim.get("asof") or "")

    detail: dict[str, Any] = {
        "symbol": symbol,
        "horizon_d": horizon_d,
        "direction": direction,
    }

    if not symbol or not asof_str:
        detail["note"] = "missing symbol or asof"
        return False, detail

    try:
        from engine.grading import forward_metrics  # type: ignore[import]
        import pandas as pd  # noqa: PLC0415

        # Load symbol close
        close = _load_close(root, symbol)
        spy_close = _load_close(root, "SPY")

        if close is None or len(close) < 5:
            detail["note"] = f"no price data for {symbol}"
            return False, detail

        # Compute forward metrics
        fm = forward_metrics(close, asof_str, horizons=(horizon_d,))
        fwd_ret = fm.get(f"fwd_ret_{horizon_d}")

        if fwd_ret is None:
            detail["note"] = f"horizon {horizon_d}d not yet elapsed"
            return False, detail

        # Compute SPY forward return for excess
        spy_ret = None
        if spy_close is not None:
            spy_fm = forward_metrics(spy_close, asof_str, horizons=(horizon_d,))
            spy_ret = spy_fm.get(f"fwd_ret_{horizon_d}")

        excess = fwd_ret - (spy_ret or 0.0) if spy_ret is not None else fwd_ret

        detail.update({
            "fwd_ret": round(float(fwd_ret), 4),
            "spy_ret": round(float(spy_ret), 4) if spy_ret is not None else None,
            "excess": round(float(excess), 4),
        })

        # Hit if excess directional
        hit = (excess > 0) if direction > 0 else (excess < 0)
        return bool(hit), detail

    except Exception as exc:  # noqa: BLE001
        log.debug("grade_realized_move: %s (%s)", symbol, exc)
        detail["error"] = str(exc)
        return False, detail


def _grade_escalation(
    claim: dict,
    root: Path,
    today: date,
) -> tuple[bool, dict]:
    """Grade escalation claims: did an alert fire within horizon_d?"""
    symbol = claim.get("scope_key") or ""
    horizon_d = int(claim.get("horizon_d") or 5)
    asof_str = str(claim.get("asof") or "")
    detail: dict[str, Any] = {"symbol": symbol, "horizon_d": horizon_d}

    try:
        asof_date = date.fromisoformat(asof_str[:10])
        deadline = asof_date + timedelta(days=horizon_d)

        # Check data/alerts/ for any alert matching the symbol in the window
        alerts_dir = _data(root, "alerts")
        if not alerts_dir.exists():
            detail["note"] = "no alerts directory"
            return False, detail

        found_alert = False
        for alert_file in alerts_dir.glob("*.json"):
            try:
                content = json.loads(alert_file.read_text(encoding="utf-8"))
                alert_date_str = str(content.get("date") or alert_file.stem[:10])
                alert_date = date.fromisoformat(alert_date_str[:10])
                if asof_date < alert_date <= deadline:
                    # Check if symbol appears
                    content_str = json.dumps(content)
                    if symbol and symbol.lower() in content_str.lower():
                        found_alert = True
                        detail["alert_file"] = alert_file.name
                        break
            except Exception:  # noqa: BLE001
                continue

        detail["horizon_window"] = f"{asof_date} to {deadline}"
        return found_alert, detail

    except Exception as exc:  # noqa: BLE001
        detail["error"] = str(exc)
        return False, detail


def _grade_verdict_change(
    claim: dict,
    root: Path,
    today: date,
) -> tuple[bool, dict]:
    """Grade verdict-change claims via world_state history."""
    symbol = claim.get("scope_key") or ""
    horizon_d = int(claim.get("horizon_d") or 5)
    direction = int(claim.get("direction") or 0)
    asof_str = str(claim.get("asof") or "")
    detail: dict[str, Any] = {"symbol": symbol, "direction": direction}

    try:
        # Check world_state for regime change
        ws_path = _data(root, "neuralweb", "world_state.json")
        if not ws_path.exists():
            detail["note"] = "world_state not available"
            return False, detail

        ws = json.loads(ws_path.read_text(encoding="utf-8"))
        asof_date = date.fromisoformat(asof_str[:10])
        ws_date_str = str(ws.get("as_of") or "")[:10]

        if not ws_date_str:
            detail["note"] = "world_state has no as_of"
            return False, detail

        ws_date = date.fromisoformat(ws_date_str)
        deadline = asof_date + timedelta(days=horizon_d)

        if ws_date < asof_date or ws_date > deadline:
            detail["note"] = f"world_state date {ws_date} outside window {asof_date}..{deadline}"
            return False, detail

        # Look for any regime/verdict change in the world state
        verdict = ws.get("verdict") or ""
        risk_state = ws.get("risk_radar_state") or ""

        # Simple heuristic: if direction=-1 and verdict/risk_state contains
        # escalatory keywords, that's a verdict change
        if direction < 0:
            hit = any(kw in (verdict + " " + risk_state).lower()
                      for kw in ("risk-off", "risk_off", "elevated", "critical"))
        elif direction > 0:
            hit = any(kw in (verdict + " " + risk_state).lower()
                      for kw in ("risk-on", "risk_on", "positive", "recovery"))
        else:
            hit = False

        detail.update({
            "verdict": verdict,
            "risk_state": risk_state,
            "window": f"{asof_date} to {deadline}",
        })
        return hit, detail

    except Exception as exc:  # noqa: BLE001
        detail["error"] = str(exc)
        return False, detail


def _load_close(root: Path, symbol: str):
    """Load close series for a symbol from yahoo parquet."""
    try:
        import pandas as pd  # noqa: PLC0415
        p = root / "data" / "yahoo" / f"{symbol}.parquet"
        if not p.exists():
            return None
        df = pd.read_parquet(p)
        if "close" not in df.columns:
            return None
        s = df["close"].dropna()
        s.name = symbol
        return s
    except Exception:  # noqa: BLE001
        return None


# ---------------------------------------------------------------------------
# A2 earn-in evaluation
# ---------------------------------------------------------------------------

def _load_previous_probation(root: Path) -> dict:
    p = _probation_path(root)
    try:
        if p.exists():
            return json.loads(p.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        pass
    return {}


def _write_probation(
    root: Path,
    probation: dict,
    dry_run: bool,
) -> None:
    if dry_run:
        return
    p = _probation_path(root)
    try:
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(probation, indent=2, default=str), encoding="utf-8")
    except Exception as exc:  # noqa: BLE001
        log.warning("grade_cortex_attention: could not write probation.json (%s)", exc)


def _emit_governance_transition(
    event_type: str,
    result,
    root: Path,
    dry_run: bool,
) -> None:
    if dry_run:
        return
    try:
        from engine.neuralweb.governance import append_event  # type: ignore[import]
        append_event(
            event_type,
            target="cortex_attention_queue",
            article=2,
            authored_by="grade_cortex_attention",
            evidence={
                "granted": result.granted,
                "reason": result.reason,
                "lift_lb": result.lift_lb,
                "wilson_lb": result.wilson_lb,
                "lapses_at": result.lapses_at,
                "evidence_asof": result.evidence_asof,
            },
            note=(
                f"A2 earn-in: {event_type} — {result.reason}. "
                f"Probation status updated in data/neuralweb/cortex/probation.json."
            ),
            root=str(root),
        )
    except Exception as exc:  # noqa: BLE001
        log.warning("grade_cortex_attention: governance event failed (%s)", exc)


def evaluate_a2_earn_in(
    grades: list[dict],
    root: Path,
    dry_run: bool,
    now: datetime,
) -> dict[str, Any]:
    """Evaluate A2 earn-in from graded attention record.  Returns probation dict."""
    from engine.neuralweb.constitution import (  # type: ignore[import]
        AuthorityLevel, grant_authority,
    )

    n = len(grades)
    hits = sum(1 for g in grades if g.get("outcome_hit"))
    evidence_asof = None
    if grades:
        dates = [g.get("graded_at") for g in grades if g.get("graded_at")]
        if dates:
            evidence_asof = max(str(d)[:10] for d in dates)

    evidence = {
        "hits": hits,
        "n": n,
        "base_rate": _BASE_RATE_DEFAULT,
        "evidence_asof": evidence_asof,
    }

    result = grant_authority(
        evidence,
        floors={"min_n": 25, "min_events": 8},
        target_level=AuthorityLevel.A2_ATTEND,
        now=now,
    )

    prev = _load_previous_probation(root)
    prev_granted = prev.get("granted", False)

    probation: dict[str, Any] = {
        "schema": "neuralweb.cortex_probation.v1",
        "as_of": now.date().isoformat(),
        "granted": result.granted,
        "tier": "A2 granted" if result.granted else "A0/A1 shadow",
        "reason": result.reason,
        "lift_lb": result.lift_lb,
        "wilson_lb": result.wilson_lb,
        "lapses_at": result.lapses_at,
        "evidence_asof": result.evidence_asof,
        "attention_track_record": {
            "n": n,
            "hits": hits,
            "base_rate": _BASE_RATE_DEFAULT,
        },
        "is_context_only": True,
    }

    # Governance events ON TRANSITIONS ONLY
    transition = prev_granted != result.granted
    if transition:
        event_type = "authority_grant" if result.granted else "authority_lapse"
        _emit_governance_transition(event_type, result, root, dry_run)
        log.info(
            "grade_cortex_attention: A2 transition %s→%s — %s",
            prev_granted, result.granted, result.reason,
        )
    else:
        log.info(
            "grade_cortex_attention: A2 unchanged (granted=%s) — %s. "
            "n=%d, hits=%d. Running at %s.",
            result.granted, result.reason, n, hits,
            "A2/ATTEND" if result.granted else "A0/A1 (observe+explain)",
        )

    _write_probation(root, probation, dry_run)
    return probation


# ---------------------------------------------------------------------------
# Main grading loop
# ---------------------------------------------------------------------------

def grade_attention(
    root: Path | str | None = None,
    dry_run: bool = False,
    today: date | None = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Grade matured attention claims and update A2 earn-in.  Returns summary."""
    root_p = _root_path(root) if not isinstance(root, Path) else root
    if today is None:
        today = datetime.now(timezone.utc).date()
    if now is None:
        now = datetime.now(timezone.utc)

    firings = _load_firings(root_p)
    already_graded = _graded_ids(root_p)

    matured = []
    for claim in firings:
        cid = claim.get("claim_id")
        if not cid or cid in already_graded:
            continue
        asof_str = str(claim.get("asof") or "")[:10]
        horizon_d = claim.get("horizon_d") or 5
        if not asof_str:
            continue
        try:
            asof_date = date.fromisoformat(asof_str)
            deadline = asof_date + timedelta(days=int(horizon_d))
            if today >= deadline:
                matured.append(claim)
        except Exception:  # noqa: BLE001
            pass

    log.info(
        "grade_cortex_attention: %d total firings, %d already graded, %d matured today",
        len(firings), len(already_graded), len(matured),
    )

    new_grades = []
    for claim in matured:
        cid = claim.get("claim_id", "unknown")
        symbol = claim.get("scope_key") or claim.get("symbol") or "macro"
        horizon_d = int(claim.get("horizon_d") or 5)
        direction = int(claim.get("direction") or 0)
        asof_str = str(claim.get("asof") or "")[:10]

        fc = _detect_falsifier_class(claim)

        if fc == "realized_move":
            hit, detail = _grade_realized_move(claim, root_p, today)
        elif fc == "escalation":
            hit, detail = _grade_escalation(claim, root_p, today)
        elif fc == "verdict_change":
            hit, detail = _grade_verdict_change(claim, root_p, today)
        else:
            hit = False
            detail = {"note": "ungradeable (direction=0 or unknown falsifier class)"}

        grade_row: dict[str, Any] = {
            "schema": _GRADE_SCHEMA,
            "claim_id": cid,
            "graded_at": today.isoformat(),
            "grader_version": _GRADER_VERSION,
            "falsifier_class": fc,
            "outcome_hit": hit,
            "outcome_detail": detail,
            "horizon_d": horizon_d,
            "asof": asof_str,
            "symbol": symbol,
            "direction": direction,
            "base_rate": _BASE_RATE_DEFAULT,
        }
        new_grades.append(grade_row)
        log.info(
            "grade_cortex_attention: graded %s (class=%s, hit=%s)",
            cid[:12], fc, hit,
        )

    # Write new grades (single-writer; append to sidecar)
    if new_grades and not dry_run:
        grades_p = _grades_path(root_p)
        try:
            grades_p.parent.mkdir(parents=True, exist_ok=True)
            with grades_p.open("a", encoding="utf-8") as fh:
                for g in new_grades:
                    fh.write(json.dumps(g, default=str) + "\n")
        except Exception as exc:  # noqa: BLE001
            log.warning("grade_cortex_attention: grades write failed (%s)", exc)

    # Reload all grades (including newly written ones if not dry_run)
    all_grades = _load_grades(root_p) if not dry_run else (
        _load_grades(root_p) + new_grades
    )

    # A2 earn-in
    probation = evaluate_a2_earn_in(all_grades, root_p, dry_run, now)

    # adapt_reflexes join: mark graded firings in spine by updating query layer
    # (query.adapt_reflexes will pick up grades.jsonl via the join documented in
    # the scout — the grader writes grades.jsonl; adapt_reflexes is updated to
    # read and join it onto firings rows by claim_id)

    summary = {
        "as_of": today.isoformat(),
        "grader_version": _GRADER_VERSION,
        "dry_run": dry_run,
        "total_firings": len(firings),
        "already_graded": len(already_graded),
        "matured_today": len(matured),
        "new_grades": len(new_grades),
        "all_grades_n": len(all_grades),
        "a2_earn_in": {
            "granted": probation.get("granted"),
            "reason": probation.get("reason"),
            "n": probation.get("attention_track_record", {}).get("n", 0),
            "hits": probation.get("attention_track_record", {}).get("hits", 0),
        },
    }

    return summary


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s [grade_cortex_attention] %(message)s",
    )
    parser = argparse.ArgumentParser(
        description="Cortex attention grader + A2 earn-in (W7b PR2)"
    )
    parser.add_argument("--root", default=None)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)

    try:
        summary = grade_attention(root=args.root, dry_run=args.dry_run)
        print(json.dumps(summary, indent=2, default=str))
        return 0
    except Exception as exc:  # noqa: BLE001
        log.error("grade_cortex_attention: fatal (%s)", exc, exc_info=True)
        return 0


if __name__ == "__main__":
    sys.exit(main())
