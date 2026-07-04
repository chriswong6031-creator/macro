"""engine/explanation_memory.py — W2 Explanation-Memory v0 (§5.3 of
research/SETUP_SPECIES_MASTERPLAN_BY_FABLE.md).

Post-outcome attribution grader: "was the stated mechanism the realised one?"
Produces a DISPLAY/META artifact (site/qledger/explanation_memory.json) that
accumulates attribution verdicts and Brier calibration across all 8 desk
theses ledgers.  Never writes to any names/scores/rank surface.

v0 is DETERMINISTIC — verdicts derive from machine-readable fields already on
the thesis row.  The LLM-assisted refinement (mechanism narrative matching) is
the v1 follow-on; a placeholder docstring is kept here so v1 can anchor on it.
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Sequence

import pandas as pd

from lib import config
from engine.validation import brier_reliability

log = logging.getLogger("explanation_memory")

# --------------------------------------------------------------------------- #
# frozen verdict enum (pre-registered v0 logic — do not alter without a new
# species-card revision; v1 adds LLM-assisted paths on top of this set)
# --------------------------------------------------------------------------- #
ATTRIBUTION_VERDICTS: tuple[str, ...] = (
    "right-for-right-reason",
    "right-wrong-reason",
    "wrong-regime-changed",
    "wrong-missing-data",
    "wrong-overfit",
    "wrong-undetermined",
)

# desks with a theses.jsonl
_DESKS: tuple[str, ...] = (
    "ai_desk",
    "altdata",
    "demand_chain",
    "master_brain",
    "policy_intent",
    "radar",
    "stock_desk",
    "thematic_desk",
)

# statuses that mean a thesis has been closed / graded
_CLOSED_STATUSES: frozenset[str] = frozenset(
    {"closed", "graded", "resolved", "scored", "hit", "miss"}
)

# markers in outcome/realized that mean the data was missing at grade time
_DEGRADED_MARKERS: frozenset[str] = frozenset(
    {"degraded", "no_data", "missing", "data_missing", "insufficient"}
)

# regime fields checked for material change (§5.3 spec)
_REGIME_FIELDS: tuple[str, ...] = ("rate_pressure", "quad_hard_label", "risk_radar_state")

# Brier minimum: validation.brier_reliability already requires ≥30 for its
# internal path; we keep our own <10 short-circuit to emit the honest note
# before even trying.
_BRIER_MIN_PAIRS = 10


# --------------------------------------------------------------------------- #
# helpers
# --------------------------------------------------------------------------- #
def _root(root: Path | str | None) -> Path:
    return Path(root) if root else config.ROOT


def _read_jsonl(p: Path) -> list[dict]:
    """Tolerant JSONL reader — mirrors qledger._read_jsonl exactly."""
    if not p.exists():
        return []
    out: list[dict] = []
    for line in p.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            out.append(json.loads(line))
        except Exception:  # noqa: BLE001
            continue
    return out


def _is_matured(t: dict) -> bool:
    """True iff the thesis has been closed/graded/resolved."""
    status = (t.get("status") or "").lower()
    if status in _CLOSED_STATUSES:
        return True
    # Also consider a thesis matured if outcome or realized is a non-None,
    # non-empty value (a scorer has filled it in).
    outcome = t.get("outcome")
    realized = t.get("realized")
    if outcome is not None and outcome != "" and str(outcome).lower() not in {"none", "null"}:
        return True
    if realized is not None and realized != "" and str(realized).lower() not in {"none", "null"}:
        return True
    return False


def _is_degraded(val: object) -> bool:
    """Return True if the value carries a missing/degraded marker."""
    if val is None:
        return False
    return any(m in str(val).lower() for m in _DEGRADED_MARKERS)


def _direction_hit(thesis: dict) -> bool | None:
    """
    Derive whether the subject moved in the leaned direction once matured.

    Reads from (in order):
      1. ``realized`` field — expected to carry a dict or a scalar once scored.
         Dict: look for keys ``hit``, ``direction_hit``, ``correct``.
         Scalar: "hit"/"miss"/"true"/"false" strings, or a numeric rel-return.
      2. ``outcome`` field — same conventions.
      3. ``status`` exact "hit" / "miss" as last resort.

    Returns True/False, or None if indeterminate.
    """
    for key in ("realized", "outcome"):
        val = thesis.get(key)
        if val is None or val == "" or str(val).lower() in {"none", "null"}:
            continue
        if _is_degraded(val):
            continue  # degraded → handled by caller

        # dict form: scanner fields
        if isinstance(val, dict):
            for sub in ("hit", "direction_hit", "correct"):
                sv = val.get(sub)
                if sv is not None:
                    if isinstance(sv, bool):
                        return sv
                    s = str(sv).lower()
                    if s in {"true", "1", "yes", "hit"}:
                        return True
                    if s in {"false", "0", "no", "miss"}:
                        return False
            # numeric rel-return in dict
            lean = (thesis.get("lean") or "").lower()
            for sub in ("rel_return", "excess_return", "return"):
                rv = val.get(sub)
                if rv is not None:
                    try:
                        r = float(rv)
                        if lean in ("overweight", "long", "bullish", "buy"):
                            return r > 0
                        if lean in ("underweight", "short", "bearish", "sell"):
                            return r < 0
                        # neutral — any non-zero move is not a clear direction hit
                    except (TypeError, ValueError):
                        pass

        # scalar string form
        if isinstance(val, str):
            s = val.lower()
            if s in {"hit", "true", "correct", "win"}:
                return True
            if s in {"miss", "false", "wrong", "loss", "incorrect"}:
                return False
            # numeric string
            lean = (thesis.get("lean") or "").lower()
            try:
                r = float(val)
                if lean in ("overweight", "long", "bullish", "buy"):
                    return r > 0
                if lean in ("underweight", "short", "bearish", "sell"):
                    return r < 0
            except (TypeError, ValueError):
                pass

        # numeric scalar
        if isinstance(val, (int, float)):
            lean = (thesis.get("lean") or "").lower()
            r = float(val)
            if lean in ("overweight", "long", "bullish", "buy"):
                return r > 0
            if lean in ("underweight", "short", "bearish", "sell"):
                return r < 0

    # Last resort: status == "hit" / "miss"
    status = (thesis.get("status") or "").lower()
    if status == "hit":
        return True
    if status == "miss":
        return False

    return None


def _falsifier_fired(thesis: dict) -> bool | None:
    """
    Return True if the thesis's machine falsifier predicate was triggered.

    The falsifier dict on a matured thesis may carry an ``outcome`` sub-key
    (scorer fill), a ``fired`` bool, or a ``triggered`` bool.  Returns None
    if unknown.
    """
    f = thesis.get("falsifier")
    if not isinstance(f, dict):
        return None
    for sub in ("fired", "triggered", "outcome"):
        sv = f.get(sub)
        if sv is None:
            continue
        if isinstance(sv, bool):
            return sv
        s = str(sv).lower()
        if s in {"true", "1", "yes", "fired", "triggered"}:
            return True
        if s in {"false", "0", "no"}:
            return False
    return None


def _has_degraded_inputs(thesis: dict) -> bool:
    """Return True if any outcome/realized field carries a degraded/missing marker."""
    for key in ("outcome", "realized"):
        if _is_degraded(thesis.get(key)):
            return True
    return False


def _regime_changed_materially(
    thesis: dict, regime_history: pd.DataFrame
) -> bool:
    """
    Return True if the regime changed materially between logged_at and check_by.

    Material change: any of rate_pressure | quad_hard_label | risk_radar_state
    differs between the logged_at row and the check_by row.

    Gracefully returns False on any lookup failure.
    """
    try:
        logged_at_raw = thesis.get("logged_at") or thesis.get("state_asof")
        check_by_raw = thesis.get("check_by")
        if not logged_at_raw or not check_by_raw:
            return False

        t_logged = pd.Timestamp(logged_at_raw).normalize()
        t_check = pd.Timestamp(check_by_raw).normalize()

        if not isinstance(regime_history.index, pd.DatetimeIndex):
            return False

        def _row_at(ts: pd.Timestamp) -> pd.Series | None:
            before = regime_history[regime_history.index <= ts]
            if before.empty:
                return None
            return before.iloc[-1]

        row_logged = _row_at(t_logged)
        row_check = _row_at(t_check)
        if row_logged is None or row_check is None:
            return False

        for field in _REGIME_FIELDS:
            if field not in regime_history.columns:
                continue
            v_logged = row_logged.get(field)
            v_check = row_check.get(field)
            if v_logged is None or v_check is None:
                continue
            if str(v_logged) != str(v_check):
                return True

        return False

    except Exception:  # noqa: BLE001
        return False


# --------------------------------------------------------------------------- #
# grade_thesis
# --------------------------------------------------------------------------- #

def grade_thesis(
    thesis: dict,
    *,
    regime_history: pd.DataFrame | None = None,
) -> dict | None:
    """Grade a single thesis row and return an attribution verdict dict.

    Returns None for unmatured theses.

    v0 rule table (pre-registered, deterministic — no LLM):
      direction_hit True  + falsifier_fired False  → right-for-right-reason
      direction_hit True  + falsifier_fired True   → right-wrong-reason
      direction_hit False + degraded inputs        → wrong-missing-data
      direction_hit False + regime changed         → wrong-regime-changed
      direction_hit False + regime stable + inputs present → wrong-overfit
      direction_hit False + no regime_history      → wrong-undetermined
      direction_hit None                           → wrong-undetermined

    v1 note (future): an LLM pass will match the ``why`` field of the species card
    or the committee memo against the realised causal narrative.  v0 deliberately
    omits this so the first artifact is fully reproducible without any external call.
    """
    if not _is_matured(thesis):
        return None

    desk = thesis.get("desk", "unknown")
    t_id = thesis.get("id", "")
    subject = thesis.get("subject") or thesis.get("ticker") or ""
    ticker = thesis.get("ticker") or ""
    conviction_raw = thesis.get("conviction")

    try:
        conviction = float(conviction_raw) if conviction_raw is not None else None
    except (TypeError, ValueError):
        conviction = None

    d_hit = _direction_hit(thesis)
    f_fired = _falsifier_fired(thesis)
    has_degraded = _has_degraded_inputs(thesis)

    # Brier outcome: 1.0 if direction hit, 0.0 if miss, None if unknown
    realized_hit: float | None
    if d_hit is True:
        realized_hit = 1.0
    elif d_hit is False:
        realized_hit = 0.0
    else:
        realized_hit = None

    # --- RULE TABLE (v0, exactly as spec'd) ---
    if d_hit is True and f_fired is False:
        verdict = "right-for-right-reason"
        reason_note = "direction hit; falsifier predicate did not fire"
    elif d_hit is True and f_fired is True:
        verdict = "right-wrong-reason"
        reason_note = "direction hit but stated mechanism's predicate also fired — other driver"
    elif d_hit is True and f_fired is None:
        # direction hit, falsifier unknown → generous classification but note
        verdict = "right-for-right-reason"
        reason_note = "direction hit; falsifier state unknown (treated as not-fired)"
    elif d_hit is False or (d_hit is None and has_degraded):
        # Covers: direction explicitly miss, OR direction indeterminate because
        # the inputs themselves carry a degraded/missing marker (the degraded
        # marker prevented direction derivation — still counts as missing-data).
        if has_degraded:
            verdict = "wrong-missing-data"
            reason_note = "direction miss; degraded or missing input data at grade time"
        elif regime_history is not None and _regime_changed_materially(thesis, regime_history):
            verdict = "wrong-regime-changed"
            reason_note = "direction miss; regime changed materially between entry and check_by"
        elif regime_history is None:
            verdict = "wrong-undetermined"
            reason_note = "direction miss; no regime_history supplied — cannot attribute"
        else:
            verdict = "wrong-overfit"
            reason_note = "direction miss; regime stable, inputs present — likely overfit"
    else:
        # d_hit is None (and no degraded inputs — direction truly indeterminate)
        verdict = "wrong-undetermined"
        reason_note = "direction indeterminate from available fields"

    return {
        "id": t_id,
        "subject": subject,
        "ticker": ticker,
        "desk": desk,
        "verdict": verdict,
        "direction_hit": d_hit,
        "falsifier_fired": f_fired,
        "conviction": conviction,
        "realized_hit": realized_hit,
        "reason_note": reason_note,
        "graded_at": datetime.now(timezone.utc).isoformat(),
    }


# --------------------------------------------------------------------------- #
# grade_ledger
# --------------------------------------------------------------------------- #

def grade_ledger(
    desk: str,
    root: Path | str | None = None,
    regime_history: pd.DataFrame | None = None,
) -> dict:
    """Load data/<desk>/theses.jsonl, grade every thesis, return a summary dict.

    Always returns a valid dict even if the file is absent or empty.
    Skips (returns None for) unmatured theses — those are NOT counted in n_graded.
    """
    p = _root(root) / "data" / desk / "theses.jsonl"
    rows = _read_jsonl(p)

    n_theses = len(rows)
    n_matured = 0
    graded_rows: list[dict] = []
    verdict_counts: dict[str, int] = {v: 0 for v in ATTRIBUTION_VERDICTS}

    for thesis in rows:
        # Inject the desk name so grade_thesis can attach it
        thesis_with_desk = {"desk": desk, **thesis}
        result = grade_thesis(thesis_with_desk, regime_history=regime_history)
        if result is None:
            continue
        n_matured += 1
        graded_rows.append(result)
        v = result.get("verdict", "wrong-undetermined")
        if v in verdict_counts:
            verdict_counts[v] += 1
        else:
            verdict_counts["wrong-undetermined"] = verdict_counts.get("wrong-undetermined", 0) + 1

    return {
        "desk": desk,
        "n_theses": n_theses,
        "n_matured": n_matured,
        "n_graded": len(graded_rows),
        "verdicts": verdict_counts,
        "rows": graded_rows,
    }


# --------------------------------------------------------------------------- #
# build_explanation_memory
# --------------------------------------------------------------------------- #

def _load_regime_history(root: Path) -> pd.DataFrame | None:
    """Load data/regime/regime_vector.parquet if present; else return None.

    Falls back to None (not a crash) when the file is absent — the heavy store
    is not guaranteed in all environments (e.g. CI).
    """
    p = root / "data" / "regime" / "regime_vector.parquet"
    if not p.exists():
        log.debug("regime_vector.parquet absent — regime-change detection disabled")
        return None
    try:
        df = pd.read_parquet(p)
        if not isinstance(df.index, pd.DatetimeIndex):
            df.index = pd.to_datetime(df.index)
        return df
    except Exception as e:  # noqa: BLE001
        log.warning("explanation_memory: could not read regime_vector.parquet (%s)", e)
        return None


def _compute_brier(all_rows: list[dict]) -> dict:
    """Run brier_reliability over graded rows with non-null (conviction, realized_hit).

    Returns {"brier": float, ...} on success; {"brier": None, "note": ...} when
    there are fewer than _BRIER_MIN_PAIRS valid pairs.
    """
    pairs = [
        (r["conviction"], r["realized_hit"])
        for r in all_rows
        if r.get("conviction") is not None and r.get("realized_hit") is not None
    ]
    if len(pairs) < _BRIER_MIN_PAIRS:
        return {
            "brier": None,
            "note": f"insufficient matured pairs (<{_BRIER_MIN_PAIRS}); "
                    f"currently {len(pairs)}",
        }
    ps = [p[0] for p in pairs]
    ys = [p[1] for p in pairs]
    result = brier_reliability(ps, ys)
    if not result:
        # brier_reliability returns {} when len < 30 (its own internal floor)
        return {
            "brier": None,
            "note": f"brier_reliability returned empty ({len(pairs)} pairs < 30 internal floor)",
        }
    return result


def build_explanation_memory(root: Path | str | None = None) -> dict:
    """Grade all 8 desk ledgers, aggregate verdict tallies, emit the display artifact.

    DISPLAY / META ONLY — never writes to names/scores/rank surfaces.

    With 0 matured theses (the expected state as of 2026-07-04), the artifact
    emits clean zeros and a status message; it never crashes or fabricates.

    Output: site/qledger/explanation_memory.json
    """
    r = _root(root)
    regime_history = _load_regime_history(r)

    desk_results: list[dict] = []
    all_graded_rows: list[dict] = []
    overall_verdicts: dict[str, int] = {v: 0 for v in ATTRIBUTION_VERDICTS}
    total_theses = 0
    total_matured = 0

    for desk in _DESKS:
        result = grade_ledger(desk, root=r, regime_history=regime_history)
        desk_results.append({
            "desk": result["desk"],
            "n_theses": result["n_theses"],
            "n_matured": result["n_matured"],
            "n_graded": result["n_graded"],
            "verdicts": result["verdicts"],
        })
        all_graded_rows.extend(result["rows"])
        total_theses += result["n_theses"]
        total_matured += result["n_matured"]
        for v, cnt in result["verdicts"].items():
            if v in overall_verdicts:
                overall_verdicts[v] += cnt

    brier_block = _compute_brier(all_graded_rows)

    if total_matured == 0:
        status_msg = (
            "accruing — activates as theses mature (check_by ~2026-10)"
        )
    else:
        status_msg = f"{total_matured} theses graded"

    payload: dict = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "version": "v0",
        "status": status_msg,
        "total_theses": total_theses,
        "total_matured": total_matured,
        "overall_verdicts": overall_verdicts,
        "brier": brier_block,
        "desks": desk_results,
    }

    # Write display artifact to site/qledger/explanation_memory.json
    out_dir = r / "site" / "qledger"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / "explanation_memory.json"
    try:
        out_path.write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")
        log.info("explanation_memory: wrote %s", out_path)
    except Exception as e:  # noqa: BLE001
        log.warning("explanation_memory: could not write artifact (%s)", e)

    return payload
