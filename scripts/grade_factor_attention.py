"""scripts/grade_factor_attention.py — Factor attention grader (Lane 1, P1-D).

SINGLE-WRITER: this script is the ONLY writer to
  data/reflexes/factor_attention/grades.jsonl

It is a minimal parallel grader that reuses the same _grade_realized_move machinery
from scripts/grade_cortex_attention.py.  This is NOT a fork of the grading logic —
the _grade_realized_move function is imported from a shared location, or re-used via
the same engine.grading.forward_metrics call pattern.

WHY A SEPARATE GRADER (not parameterized wiring)
-------------------------------------------------
grade_cortex_attention.py is hardcoded to the cortex reflex paths and the cortex
A2 authority level.  It is not parameterizable (all paths + authority level are
hardcoded constants, not arguments).

The factor_attention reflex lives in its OWN probation record:
  data/reflexes/factor_attention/grades.jsonl
  data/reflexes/factor_attention/probation.json

Since grade_cortex_attention.py is not parameterizable (all paths + authority level
are hardcoded constants, not arguments), this script provides the minimal parallel
grader as specified in RULING-G, reusing the engine.grading.forward_metrics call
pattern and the SAME falsifier class detection and hit logic.

FALSIFIER CLASS
---------------
All factor_attention firings carry:
  direction=-1, falsifier text starts with "direction=-1; hit = name underperforms SPY"
  → falsifier_class='realized_move'
  → graded by _grade_realized_move machinery (excess < 0 = hit when direction=-1)

GRADE SCHEMA (reflex.factor_attention.grade.v1)
-----------------------------------------------
  claim_id          str   — matches the firings.jsonl claim_id
  graded_at         str   — ISO date (today)
  grader_version    str
  falsifier_class   str   — 'realized_move' (all factor_attention claims)
  outcome_hit       bool  — True if name underperformed SPY at horizon_d=21
  outcome_detail    dict  — evidence detail
  horizon_d         int
  asof              str
  symbol            str
  direction         int   — always -1
  base_rate         float — 0.5 (prior)

A2 EARN-IN (DISPLAY-ONLY PROBATION)
------------------------------------
After grading, constitution.grant_authority is called with the graded factor_attention
record.  Result is written to data/reflexes/factor_attention/probation.json.
Governance event appended ON TRANSITIONS ONLY (refused→granted or granted→refused).
The factor_attention reflex is display-only; earn-in here is for observational tracking.

CADENCE
-------
This script runs in the SAME cortex job as grade_cortex_attention.py in daily.yml —
added as a step immediately after grade_cortex_attention (see daily.yml cortex job).
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

_GRADER_VERSION = "P1D-v1"
_GRADE_SCHEMA = "reflex.factor_attention.grade.v1"
_BASE_RATE_DEFAULT = 0.5
_REFLEX_NAME = "factor_attention"


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
    return _data(root, "reflexes", _REFLEX_NAME, "firings.jsonl")


def _grades_path(root: Path) -> Path:
    return _data(root, "reflexes", _REFLEX_NAME, "grades.jsonl")


def _probation_path(root: Path) -> Path:
    return _data(root, "reflexes", _REFLEX_NAME, "probation.json")


# ---------------------------------------------------------------------------
# Load helpers (same pattern as grade_cortex_attention.py)
# ---------------------------------------------------------------------------

def _load_jsonl(p: Path) -> list[dict]:
    if not p.exists():
        return []
    rows = []
    for line in p.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            rows.append(json.loads(line))
        except Exception:  # noqa: BLE001
            pass
    return rows


def _graded_ids(root: Path) -> set[str]:
    return {r.get("claim_id") for r in _load_jsonl(_grades_path(root)) if r.get("claim_id")}


# ---------------------------------------------------------------------------
# Close loader (same as grade_cortex_attention.py)
# ---------------------------------------------------------------------------

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
# _grade_realized_move — reuses engine.grading.forward_metrics
# (same call pattern as grade_cortex_attention._grade_realized_move)
# ---------------------------------------------------------------------------

def _grade_realized_move(
    claim: dict,
    root: Path,
    today: date,
) -> tuple[bool, dict]:
    """Grade realized-move claims via forward_metrics vs SPY.

    Hit criterion: excess vs SPY < 0 when direction=-1 (name underperforms SPY).
    This is the falsifier for factor_attention per RULING-G.
    """
    symbol = claim.get("scope_key") or claim.get("symbol") or ""
    horizon_d = int(claim.get("horizon_d") or 21)
    direction = int(claim.get("direction") or -1)
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

        close = _load_close(root, symbol)
        spy_close = _load_close(root, "SPY")

        if close is None or len(close) < 5:
            detail["note"] = f"no price data for {symbol}"
            return False, detail

        fm = forward_metrics(close, asof_str, horizons=(horizon_d,))
        fwd_ret = fm.get(f"fwd_ret_{horizon_d}")

        if fwd_ret is None:
            detail["note"] = f"horizon {horizon_d}d not yet elapsed"
            return False, detail

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

        # Hit: direction=-1 means we expect the name to underperform SPY (excess < 0)
        hit = (excess > 0) if direction > 0 else (excess < 0)
        return bool(hit), detail

    except Exception as exc:  # noqa: BLE001
        log.debug("grade_factor_attention: _grade_realized_move %s (%s)", symbol, exc)
        detail["error"] = str(exc)
        return False, detail


# ---------------------------------------------------------------------------
# Probation helpers
# ---------------------------------------------------------------------------

def _load_previous_probation(root: Path) -> dict:
    p = _probation_path(root)
    try:
        if p.exists():
            return json.loads(p.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        pass
    return {}


def _write_probation(root: Path, probation: dict, dry_run: bool) -> None:
    if dry_run:
        return
    p = _probation_path(root)
    try:
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(probation, indent=2, default=str), encoding="utf-8")
    except Exception as exc:  # noqa: BLE001
        log.warning("grade_factor_attention: could not write probation.json (%s)", exc)


def _emit_governance_transition(
    event_type: str,
    result: Any,
    root: Path,
    dry_run: bool,
) -> None:
    if dry_run:
        return
    try:
        from engine.neuralweb.governance import append_event  # type: ignore[import]
        append_event(
            event_type,
            target="factor_attention_reflex",
            article=2,
            authored_by="grade_factor_attention",
            evidence={
                "granted": result.granted,
                "reason": result.reason,
                "lift_lb": result.lift_lb,
                "wilson_lb": result.wilson_lb,
                "lapses_at": result.lapses_at,
                "evidence_asof": result.evidence_asof,
            },
            note=(
                f"factor_attention A2 earn-in: {event_type} — {result.reason}. "
                f"Probation at data/reflexes/factor_attention/probation.json."
            ),
            root=str(root),
        )
    except Exception as exc:  # noqa: BLE001
        log.warning("grade_factor_attention: governance event failed (%s)", exc)


def _evaluate_a2_earn_in(
    grades: list[dict],
    root: Path,
    dry_run: bool,
    now: datetime,
) -> dict[str, Any]:
    """Evaluate A2 earn-in for factor_attention.  Returns probation dict."""
    try:
        from engine.neuralweb.constitution import (  # type: ignore[import]
            AuthorityLevel, grant_authority,
        )
    except Exception as exc:
        log.warning("grade_factor_attention: constitution import failed (%s)", exc)
        return {"granted": False, "reason": f"constitution import failed: {exc}"}

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
        "schema": "reflex.factor_attention_probation.v1",
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

    transition = prev_granted != result.granted
    if transition:
        event_type = "authority_grant" if result.granted else "authority_lapse"
        _emit_governance_transition(event_type, result, root, dry_run)
        log.info(
            "grade_factor_attention: A2 transition %s→%s — %s",
            prev_granted, result.granted, result.reason,
        )
    else:
        log.info(
            "grade_factor_attention: A2 unchanged (granted=%s) — %s. n=%d, hits=%d.",
            result.granted, result.reason, n, hits,
        )

    _write_probation(root, probation, dry_run)
    return probation


# ---------------------------------------------------------------------------
# Main grading loop
# ---------------------------------------------------------------------------

def grade_factor_attention(
    root: Path | str | None = None,
    dry_run: bool = False,
    today: date | None = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Grade matured factor_attention claims and update A2 earn-in.

    Never raises.  Returns summary dict.
    """
    root_p = _root_path(root) if not isinstance(root, Path) else root
    if today is None:
        today = datetime.now(timezone.utc).date()
    if now is None:
        now = datetime.now(timezone.utc)

    firings = _load_jsonl(_firings_path(root_p))
    already_graded = _graded_ids(root_p)

    matured = []
    for claim in firings:
        cid = claim.get("claim_id")
        if not cid or cid in already_graded:
            continue
        asof_str = str(claim.get("asof") or "")[:10]
        horizon_d = claim.get("horizon_d") or 21
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
        "grade_factor_attention: %d total firings, %d already graded, %d matured today",
        len(firings), len(already_graded), len(matured),
    )

    new_grades = []
    for claim in matured:
        cid = claim.get("claim_id", "unknown")
        symbol = claim.get("scope_key") or claim.get("symbol") or "macro"
        horizon_d = int(claim.get("horizon_d") or 21)
        direction = int(claim.get("direction") or -1)
        asof_str = str(claim.get("asof") or "")[:10]

        # All factor_attention claims use realized_move falsifier class
        hit, detail = _grade_realized_move(claim, root_p, today)

        grade_row: dict[str, Any] = {
            "schema": _GRADE_SCHEMA,
            "claim_id": cid,
            "graded_at": today.isoformat(),
            "grader_version": _GRADER_VERSION,
            "falsifier_class": "realized_move",
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
            "grade_factor_attention: graded %s (hit=%s, horizon=%dd)",
            cid[:12], hit, horizon_d,
        )

    if new_grades and not dry_run:
        grades_p = _grades_path(root_p)
        try:
            grades_p.parent.mkdir(parents=True, exist_ok=True)
            with grades_p.open("a", encoding="utf-8") as fh:
                for g in new_grades:
                    fh.write(json.dumps(g, default=str) + "\n")
        except Exception as exc:  # noqa: BLE001
            log.warning("grade_factor_attention: grades write failed (%s)", exc)

    all_grades = _load_jsonl(_grades_path(root_p)) if not dry_run else (
        _load_jsonl(_grades_path(root_p)) + new_grades
    )

    probation: dict[str, Any] = {}
    try:
        probation = _evaluate_a2_earn_in(all_grades, root_p, dry_run, now)
    except Exception as exc:  # noqa: BLE001
        log.warning("grade_factor_attention: A2 earn-in failed (%s)", exc)
        probation = {"granted": False, "reason": f"earn-in error: {exc}"}

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
        format="%(asctime)s %(levelname)s [grade_factor_attention] %(message)s",
    )
    parser = argparse.ArgumentParser(
        description="Factor attention grader + A2 earn-in (P1-D)"
    )
    parser.add_argument("--root", default=None)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)

    try:
        summary = grade_factor_attention(root=args.root, dry_run=args.dry_run)
        print(json.dumps(summary, indent=2, default=str))
        return 0
    except Exception as exc:  # noqa: BLE001
        log.error("grade_factor_attention: fatal (%s)", exc, exc_info=True)
        return 0


if __name__ == "__main__":
    sys.exit(main())
