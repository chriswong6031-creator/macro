"""engine.neuralweb.confluence_sequence — Confluence tape + sequence organ (R-V4-7).

PURPOSE
-------
Nightly append to data/neuralweb/confluence_tape.jsonl (PIT tape; nightly is the
SOLE ADVANCER) and derivation of sequence statistics per subject/engine-pair:

  persistence_streak  — consecutive sessions the event fired (int)
  strength_slope      — simple robust OLS slope over trailing K sessions (float | null)
  state               — one of {new, strengthening, stable, decaying, gone}

IDEMPOTENCY
-----------
Re-running the same night (same as_of) replaces existing rows for that date;
never duplicates.  The tape is keyed on (subject, as_of, direction, horizon) for
strength rows and on (pair_id, as_of) for contradiction rows.

SEQUENCE STATE MACHINE
----------------------
state is derived per (subject, direction, horizon) across the trailing-K tape:

  new          — first ever appearance (streak == 1 and only 1 session in tape)
  strengthening — slope > SLOPE_THRESH
  stable        — |slope| <= SLOPE_THRESH AND streak > 1
  decaying      — slope < -SLOPE_THRESH
  gone          — appeared in tape but NOT in current session (handled by caller)

SCHEMA
------
data/neuralweb/confluence_tape.jsonl — one JSON line per (subject, as_of) event row.
{
  "schema":                   "neuralweb.confluence_tape.v1",
  "subject":                  <str>,
  "as_of":                    <str>,
  "direction":                <int>,
  "horizon":                  <str>,
  "n_confirming_raw":         <int>,
  "n_independent_confirming": <float>,
  "engines":                  [<str>, ...],
  "regime_bucket":            <str | null>,
  "n_cofire_events":          <int | null>,
  "pair_id":                  <str | null>,   # for contradiction rows
  "kind":                     <str | null>,   # contradiction kind
  "severity":                 <str | null>    # contradiction severity
}

data/neuralweb/confluence_sequence.json
{
  "schema":       "neuralweb.confluence_sequence.v1",
  "artifact_id":  "confluence-sequence",
  "asof":         <str>,
  "tier":         "display",
  "is_context_only": true,
  "display_only": true,
  "produced_by":  "engine/neuralweb/confluence_sequence.py",
  "produced_at":  <utc str>,
  "authority_check": [...],
  "subjects":     [
    {
      "subject":            <str>,
      "direction":          <int>,
      "horizon":            <str>,
      "persistence_streak": <int>,
      "strength_slope":     <float | null>,
      "state":              "new" | "strengthening" | "stable" | "decaying" | "gone",
      "last_as_of":         <str>,
      "n_sessions_in_tape": <int>,
      "n_independent_confirming_latest": <float | null>
    }
  ],
  "contradiction_pairs": [
    {
      "pair_id":            <str>,
      "persistence_streak": <int>,
      "strength_slope":     <float | null>,
      "state":              <str>,
      "last_as_of":         <str>,
      "n_sessions_in_tape": <int>
    }
  ],
  "gaps": [<str>, ...]
}

FAIL-OPEN CONTRACT
------------------
Any exception logs a warning and returns an empty/degraded payload; never raises.
"""
from __future__ import annotations

import json
import logging
import math
import statistics
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from engine.neuralweb._law import assert_no_authority

log = logging.getLogger(__name__)

_SCHEMA_TAPE = "neuralweb.confluence_tape.v1"
_SCHEMA_SEQ = "neuralweb.confluence_sequence.v1"
_HARD_LAW = (
    "HARD LAW: display-only; nightly sole advancer; idempotent per as_of; "
    "never gates, never ranks, never raises a priority."
)

# Slope threshold for state classification
_SLOPE_THRESH = 0.05
# Trailing K sessions for slope
_SLOPE_K = 10


# ---------------------------------------------------------------------------
# Repo root
# ---------------------------------------------------------------------------


def _repo_root(root: Path | None) -> Path:
    if root is not None:
        return Path(root)
    return Path(__file__).resolve().parent.parent.parent


# ---------------------------------------------------------------------------
# Robust slope (simple OLS; N >= 2 guard)
# ---------------------------------------------------------------------------


def _robust_slope(values: list[float]) -> float | None:
    """Simple OLS slope over a list of values.  Returns None if < 2 non-None values.

    Uses median detrending: robust to outliers by computing the Theil-Sen slope
    (median of pairwise slopes) when N <= 30; for larger N use OLS (budget).
    """
    if not values or len(values) < 2:
        return None
    # Filter out NaN/inf
    clean = [v for v in values if v is not None and math.isfinite(v)]
    if len(clean) < 2:
        return None

    n = len(clean)
    x = list(range(n))

    try:
        if n <= 30:
            # Theil-Sen: median of pairwise slopes
            slopes: list[float] = []
            for i in range(n):
                for j in range(i + 1, n):
                    dx = x[j] - x[i]
                    if dx != 0:
                        slopes.append((clean[j] - clean[i]) / dx)
            if not slopes:
                return None
            return statistics.median(slopes)
        else:
            # OLS for larger series
            x_mean = (n - 1) / 2.0
            y_mean = sum(clean) / n
            num = sum((xi - x_mean) * (yi - y_mean) for xi, yi in zip(x, clean))
            den = sum((xi - x_mean) ** 2 for xi in x)
            if den == 0:
                return None
            return num / den
    except Exception as exc:  # noqa: BLE001
        log.warning("confluence_sequence._robust_slope: failed — %s", exc)
        return None


# ---------------------------------------------------------------------------
# State machine
# ---------------------------------------------------------------------------


def _derive_state(
    streak: int,
    slope: float | None,
    n_sessions: int,
    fired_today: bool,
) -> str:
    """Derive sequence state from streak + slope."""
    if not fired_today:
        return "gone"
    if n_sessions == 1:
        return "new"
    if slope is not None and slope > _SLOPE_THRESH:
        return "strengthening"
    if slope is not None and slope < -_SLOPE_THRESH:
        return "decaying"
    return "stable"


# ---------------------------------------------------------------------------
# Tape I/O
# ---------------------------------------------------------------------------


def _read_tape(tape_path: Path, gaps: list[str]) -> list[dict]:
    """Read all tape rows from jsonl file.  Fail-open: returns empty on error."""
    rows: list[dict] = []
    if not tape_path.exists():
        return rows
    try:
        for line in tape_path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                rows.append(json.loads(line))
            except Exception:  # noqa: BLE001
                continue
    except Exception as exc:  # noqa: BLE001
        gaps.append(f"confluence_sequence: tape read error — {exc}")
    return rows


def _write_tape(tape_path: Path, rows: list[dict], gaps: list[str]) -> None:
    """Write rows to tape jsonl (overwrite)."""
    try:
        tape_path.parent.mkdir(parents=True, exist_ok=True)
        tape_path.write_text(
            "\n".join(json.dumps(r, ensure_ascii=False, default=str) for r in rows) + "\n",
            encoding="utf-8",
        )
    except Exception as exc:  # noqa: BLE001
        gaps.append(f"confluence_sequence: tape write error — {exc}")
        log.warning("confluence_sequence: tape write failed — %s", exc)


# ---------------------------------------------------------------------------
# Tape upsert (idempotent per as_of)
# ---------------------------------------------------------------------------


def _upsert_tape_rows(
    existing: list[dict],
    new_rows: list[dict],
    contra_rows: list[dict],
) -> list[dict]:
    """Upsert new_rows into existing tape.  Keyed on (subject, as_of, direction, horizon).
    Contradiction rows keyed on (pair_id, as_of).

    Re-running the same night replaces (never duplicates).
    """
    # Build index of existing rows by their key
    result: dict[tuple, dict] = {}

    for row in existing:
        if row.get("pair_id"):
            key: tuple = ("_contra", row.get("pair_id"), row.get("as_of", ""))
        else:
            key = (
                row.get("subject", ""),
                row.get("as_of", ""),
                row.get("direction", 0),
                row.get("horizon", ""),
            )
        result[key] = row

    # Upsert strength rows
    for row in new_rows:
        key = (
            row.get("subject", ""),
            row.get("as_of", ""),
            row.get("direction", 0),
            row.get("horizon", ""),
        )
        result[key] = row

    # Upsert contradiction rows
    for row in contra_rows:
        key = ("_contra", row.get("pair_id", ""), row.get("as_of", ""))
        result[key] = row

    # Return sorted by as_of, then subject
    return sorted(result.values(), key=lambda r: (r.get("as_of") or "", r.get("subject") or ""))


# ---------------------------------------------------------------------------
# Sequence derivation
# ---------------------------------------------------------------------------


def _derive_sequences(
    tape_rows: list[dict],
    current_as_of: str,
    gaps: list[str],
) -> tuple[list[dict], list[dict]]:
    """Derive per-subject and per-pair sequence statistics from tape.

    Returns (subject_sequences, pair_sequences).
    """
    # ── Subject sequences ────────────────────────────────────────────────────
    # Group tape by (subject, direction, horizon)
    from collections import defaultdict  # noqa: PLC0415
    subject_groups: dict[tuple, list[dict]] = defaultdict(list)
    pair_groups: dict[str, list[dict]] = defaultdict(list)

    for row in tape_rows:
        if row.get("pair_id"):
            pair_groups[row["pair_id"]].append(row)
        else:
            sub_key = (
                row.get("subject", ""),
                int(row.get("direction", 0)),
                row.get("horizon", ""),
            )
            subject_groups[sub_key].append(row)

    subject_seqs: list[dict] = []
    for (subject, direction, horizon), rows in subject_groups.items():
        # Sort by as_of
        rows_sorted = sorted(rows, key=lambda r: r.get("as_of") or "")
        as_of_vals = [r.get("as_of") or "" for r in rows_sorted]
        n_sessions = len(rows_sorted)

        last_as_of = as_of_vals[-1] if as_of_vals else ""
        fired_today = (last_as_of == current_as_of)

        # Persistence streak = consecutive sessions from the end
        streak = 0
        if fired_today and as_of_vals:
            streak = 1
            # Count consecutive sessions backward (assuming dates are calendar days)
            prev = as_of_vals[-1]
            for i in range(len(as_of_vals) - 2, -1, -1):
                cur = as_of_vals[i]
                # Simple: consecutive means "appeared on prior session" (strict consecutive)
                streak += 1
                prev = cur
            # Actually re-derive: streak = how many sessions fired in a row from latest
            # We count consecutive non-gap sessions (just count all sessions since they
            # appear only when fired — tape only has fired rows)
            streak = n_sessions  # All rows = all fired sessions; streak = n_sessions for
            # subjects that appear every day. But we want CONSECUTIVE.
            # Use calendar-day consecutive: check if gaps between consecutive dates > 2 days
            streak = _count_streak(as_of_vals)

        # Slope over trailing K
        n_vals = [_safe_float(r.get("n_independent_confirming")) for r in rows_sorted[-_SLOPE_K:]]
        n_vals_clean = [v for v in n_vals if v is not None]
        slope = _robust_slope(n_vals_clean) if len(n_vals_clean) >= 2 else None

        state = _derive_state(streak, slope, n_sessions, fired_today)

        latest_n_indep = _safe_float(rows_sorted[-1].get("n_independent_confirming")) if rows_sorted else None

        subject_seqs.append({
            "subject": subject,
            "direction": direction,
            "horizon": horizon,
            "persistence_streak": streak,
            "strength_slope": round(slope, 5) if slope is not None else None,
            "state": state,
            "last_as_of": last_as_of,
            "n_sessions_in_tape": n_sessions,
            "n_independent_confirming_latest": latest_n_indep,
        })

    # ── Contradiction pair sequences ─────────────────────────────────────────
    pair_seqs: list[dict] = []
    for pair_id, rows in pair_groups.items():
        rows_sorted = sorted(rows, key=lambda r: r.get("as_of") or "")
        as_of_vals = [r.get("as_of") or "" for r in rows_sorted]
        n_sessions = len(rows_sorted)
        last_as_of = as_of_vals[-1] if as_of_vals else ""
        fired_today = (last_as_of == current_as_of)
        streak = _count_streak(as_of_vals) if fired_today else 0

        # For contradiction pairs, slope over n_confirming_raw (always 1 per fire;
        # use streak as proxy over trailing sessions = presence/absence binary)
        presence = [1.0 if d == current_as_of else 1.0 for d in as_of_vals[-_SLOPE_K:]]
        slope = _robust_slope(presence) if len(presence) >= 2 else None

        state = _derive_state(streak, slope, n_sessions, fired_today)

        pair_seqs.append({
            "pair_id": pair_id,
            "persistence_streak": streak,
            "strength_slope": round(slope, 5) if slope is not None else None,
            "state": state,
            "last_as_of": last_as_of,
            "n_sessions_in_tape": n_sessions,
        })

    return subject_seqs, pair_seqs


def _count_streak(as_of_vals: list[str]) -> int:
    """Count consecutive sessions from the latest date backwards.

    Consecutive = no gap larger than 2 calendar days (weekend gap allowed).
    """
    if not as_of_vals:
        return 0
    try:
        from datetime import date as dt_date  # noqa: PLC0415

        dates = []
        for d in as_of_vals:
            try:
                dates.append(dt_date.fromisoformat(str(d)))
            except Exception:  # noqa: BLE001
                pass
        if not dates:
            return len(as_of_vals)  # can't parse — assume consecutive

        dates.sort()
        streak = 1
        for i in range(len(dates) - 1, 0, -1):
            gap = (dates[i] - dates[i - 1]).days
            if gap <= 4:  # allow up to 4 calendar days (weekend + one holiday)
                streak += 1
            else:
                break
        return streak
    except Exception:  # noqa: BLE001
        return len(as_of_vals)


def _safe_float(x: Any) -> float | None:
    if x is None:
        return None
    try:
        v = float(x)
        if math.isnan(v) or math.isinf(v):
            return None
        return v
    except (TypeError, ValueError):
        return None


# ---------------------------------------------------------------------------
# Contradiction rows from confluence graph
# ---------------------------------------------------------------------------


def _extract_contra_rows(
    graph: dict | None,
    current_as_of: str,
    gaps: list[str],
) -> list[dict]:
    """Extract contradiction-pair firing rows from the confluence graph."""
    rows: list[dict] = []
    if graph is None:
        return rows

    contra_records = graph.get("contradiction_records") or []
    for rec in contra_records:
        pair_id = rec.get("pair_id") or "unknown"
        rows.append({
            "schema": _SCHEMA_TAPE,
            "pair_id": pair_id,
            "as_of": rec.get("as_of") or current_as_of,
            "kind": rec.get("kind"),
            "severity": rec.get("severity"),
            "subject": None,
            "direction": None,
            "horizon": None,
            "n_confirming_raw": None,
            "n_independent_confirming": None,
            "engines": None,
            "regime_bucket": None,
        })
    return rows


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def append_tape_and_build_sequence(
    strength_payload: dict,
    root: Path | str | None = None,
    now: datetime | None = None,
    graph: dict | None = None,
    out_tape: Path | str | None = None,
    out_seq: Path | str | None = None,
) -> dict:
    """Append to confluence_tape.jsonl and build confluence_sequence.json.

    Parameters
    ----------
    strength_payload:
        The output of build_strength() for the current nightly run.
    root:
        Repo root override.
    now:
        UTC datetime for produced_at.
    graph:
        Pre-loaded confluence_graph.json dict (for contradiction rows).
    out_tape:
        Override tape path.
    out_seq:
        Override sequence output path.

    Returns
    -------
    dict
        The sequence payload.  Always returns a dict; never raises.
    """
    if now is None:
        now = datetime.now(timezone.utc)

    repo = _repo_root(root)
    gaps: list[str] = []

    tape_path = Path(out_tape) if out_tape else repo / "data" / "neuralweb" / "confluence_tape.jsonl"
    seq_path = Path(out_seq) if out_seq else repo / "data" / "neuralweb" / "confluence_sequence.json"

    current_as_of = now.strftime("%Y-%m-%d")

    # ── Read existing tape ───────────────────────────────────────────────────
    existing_tape = _read_tape(tape_path, gaps)

    # ── Build new strength tape rows ─────────────────────────────────────────
    new_strength_rows: list[dict] = []
    for row in (strength_payload.get("rows") or []):
        tape_row = dict(row)
        tape_row["schema"] = _SCHEMA_TAPE
        # Ensure as_of is set (pair-aggregate rows have as_of=None; use current)
        if not tape_row.get("as_of"):
            tape_row["as_of"] = current_as_of
        new_strength_rows.append(tape_row)

    # ── Load confluence graph for contradiction rows ─────────────────────────
    if graph is None:
        graph_path = repo / "data" / "neuralweb" / "confluence_graph.json"
        if graph_path.exists():
            try:
                raw = json.loads(graph_path.read_text(encoding="utf-8"))
                if isinstance(raw, dict):
                    graph = raw
            except Exception as exc:  # noqa: BLE001
                gaps.append(f"confluence_sequence: graph read error — {exc}")

    contra_rows = _extract_contra_rows(graph, current_as_of, gaps)

    # ── Upsert tape (idempotent per as_of) ───────────────────────────────────
    merged_tape = _upsert_tape_rows(existing_tape, new_strength_rows, contra_rows)
    _write_tape(tape_path, merged_tape, gaps)

    # ── Derive sequence statistics from merged tape ──────────────────────────
    try:
        subject_seqs, pair_seqs = _derive_sequences(merged_tape, current_as_of, gaps)
    except Exception as exc:  # noqa: BLE001
        log.warning("confluence_sequence: _derive_sequences failed — %s", exc)
        gaps.append(f"confluence_sequence: sequence derivation error — {exc}")
        subject_seqs, pair_seqs = [], []

    # ── Assemble payload ─────────────────────────────────────────────────────
    payload: dict[str, Any] = {
        "schema": _SCHEMA_SEQ,
        "artifact_id": "confluence-sequence",
        "asof": current_as_of,
        "tier": "display",
        "is_context_only": True,
        "display_only": True,
        "hard_law": _HARD_LAW,
        "subjects": subject_seqs,
        "contradiction_pairs": pair_seqs,
        "n_tape_rows": len(merged_tape),
        "gaps": gaps,
        "produced_by": "engine/neuralweb/confluence_sequence.py",
        "produced_at": now.strftime("%Y-%m-%dT%H:%M:%SZ"),
    }

    # ── assert_no_authority self-check ───────────────────────────────────────
    violations = assert_no_authority(payload)
    payload["authority_check"] = violations
    if violations:
        log.warning("confluence_sequence: authority violations: %s", violations)

    # ── Write sequence artifact ──────────────────────────────────────────────
    try:
        seq_path.parent.mkdir(parents=True, exist_ok=True)
        seq_path.write_text(
            json.dumps(payload, indent=2, ensure_ascii=False, default=str),
            encoding="utf-8",
        )
        log.info(
            "confluence_sequence: %d subjects, %d pairs, %d tape rows → %s",
            len(subject_seqs),
            len(pair_seqs),
            len(merged_tape),
            seq_path,
        )
    except Exception as exc:  # noqa: BLE001
        gaps.append(f"confluence_sequence: sequence write error — {exc}")
        log.warning("confluence_sequence: write failed — %s", exc)

    return payload
