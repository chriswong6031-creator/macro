"""engine.neuralweb.confluence_discovery — Discovery z-scan over tape (R-V4-8).

PURPOSE
-------
Deterministic robust-stats scan over confluence_tape.jsonl for engine-pair co-occurrence
rates that spike vs a circular-shift null.

Uses median/MAD robust-z (mirroring engine/metabolism/anomaly_monitor.py) and a
circular-shift null distribution (up to 100 distinct non-identity shifts,
matching covariance_spine.py idiom).

HONEST-NULL CONTRACT
--------------------
When the tape is too young (< MIN_SESSIONS_FOR_SCAN sessions), all emitted candidates
carry state="accruing" and z=null.  No z-scores are fabricated on insufficient data.
This is the honest-null required by R-V4-8.

HARD EXCLUSION (DO_NOT_REBUILD)
--------------------------------
rotation-state × cycle-position pairing is DON'T-TEST.  Engine families whose names
match ROTATION_ENGINE_PATTERNS and CYCLE_ENGINE_PATTERNS are counted in co-occurrence
rates normally, but no dedicated rotation_cycle pair candidate is emitted.

NO LLM ANYWHERE.  All computation is deterministic.

SCHEMA
------
data/neuralweb/confluence_candidates.jsonl — one JSON line per candidate.
{
  "pair":       <str>,         # "engine_a+engine_b"
  "z":          <float | null>,
  "n":          <int>,         # observed co-occurrence count
  "first_seen": <str>,         # ISO date of first co-occurrence
  "note":       <str>,         # state or description
  "state":      "accruing" | "candidate" | "below_thresh",
  "rate_obs":   <float | null>,
  "rate_null_median": <float | null>,
  "produced_at": <str>
}

FAIL-OPEN CONTRACT
------------------
Any exception logs a warning and returns gracefully; never raises.
"""
from __future__ import annotations

import json
import logging
import math
import statistics
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

log = logging.getLogger(__name__)


from engine.ledger_lane import nightly_advance_enabled as _ledger_advance_enabled

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_MIN_SESSIONS_FOR_SCAN = 10   # minimum tape sessions before any z-score is emitted
_NULL_DRAWS = 100              # circular-shift null draws (budget-modest)
_Z_CANDIDATE_THRESH = 2.0     # |z| >= 2.0 to be labeled 'candidate'

# DO_NOT_REBUILD: rotation × cycle pairs — match by substring
_ROTATION_ENGINE_PATTERNS = ("rotation", "sector_rotation", "rotation_state")
_CYCLE_ENGINE_PATTERNS = ("cycle", "cycle_position", "cycle_intelligence")

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _repo_root(root: Path | None) -> Path:
    if root is not None:
        return Path(root)
    return Path(__file__).resolve().parent.parent.parent


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


def _is_rotation_engine(name: str) -> bool:
    n = name.lower()
    return any(p in n for p in _ROTATION_ENGINE_PATTERNS)


def _is_cycle_engine(name: str) -> bool:
    n = name.lower()
    return any(p in n for p in _CYCLE_ENGINE_PATTERNS)


def _is_forbidden_rotation_cycle_pair(ea: str, eb: str) -> bool:
    """Return True if this pair is a rotation-state × cycle-position pairing (DON'T-TEST)."""
    a_rot = _is_rotation_engine(ea)
    b_rot = _is_rotation_engine(eb)
    a_cyc = _is_cycle_engine(ea)
    b_cyc = _is_cycle_engine(eb)
    # Forbidden: one is rotation-family AND the other is cycle-family
    return (a_rot and b_cyc) or (b_rot and a_cyc)


# ---------------------------------------------------------------------------
# Robust z
# ---------------------------------------------------------------------------


def _robust_z_latest(values: list[float]) -> tuple[float | None, float | None, float | None]:
    """Compute robust z for the latest value.

    Returns (z, median, mad).  Mirrors anomaly_monitor._robust_z.
    """
    if len(values) < 2:
        return None, None, None
    try:
        med = statistics.median(values)
        deviations = [abs(v - med) for v in values]
        mad = statistics.median(deviations)
        if mad == 0.0:
            return None, med, 0.0
        z = (values[-1] - med) / (1.4826 * mad)
        return z, med, mad
    except Exception as exc:  # noqa: BLE001
        log.warning("confluence_discovery._robust_z_latest: failed — %s", exc)
        return None, None, None


# ---------------------------------------------------------------------------
# Tape reader
# ---------------------------------------------------------------------------


def _read_tape(tape_path: Path, gaps: list[str]) -> list[dict]:
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
        gaps.append(f"confluence_discovery: tape read error — {exc}")
    return rows


# ---------------------------------------------------------------------------
# Co-occurrence matrix builder
# ---------------------------------------------------------------------------


def _build_cooccurrence_by_session(
    tape_rows: list[dict],
) -> tuple[dict[str, dict[str, int]], list[str], dict[tuple, str]]:
    """Build per-session co-occurrence counts.

    Returns:
      cooccur: dict[engine_a][engine_b] -> total co-occurrence count
      sessions: sorted list of unique as_of dates
      first_seen: dict[(engine_a, engine_b)] -> first as_of date seen
    """
    from collections import defaultdict  # noqa: PLC0415

    # Filter to strength rows (have engines list)
    strength_rows = [r for r in tape_rows if r.get("engines") and r.get("as_of")]

    # Group by as_of
    by_session: dict[str, list[list[str]]] = defaultdict(list)
    for row in strength_rows:
        engines = row.get("engines") or []
        if len(engines) >= 2:
            by_session[row["as_of"]].append(engines)

    sessions = sorted(by_session.keys())

    cooccur: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    first_seen: dict[tuple, str] = {}

    for session_date in sessions:
        for eng_list in by_session[session_date]:
            # All unique pairs in this engine list
            uniq = sorted(set(eng_list))
            for i, ea in enumerate(uniq):
                for j in range(i + 1, len(uniq)):
                    eb = uniq[j]
                    cooccur[ea][eb] += 1
                    pair_key = (ea, eb)
                    if pair_key not in first_seen:
                        first_seen[pair_key] = session_date

    return dict({k: dict(v) for k, v in cooccur.items()}), sessions, first_seen


# ---------------------------------------------------------------------------
# Circular-shift null
# ---------------------------------------------------------------------------


def _build_engine_session_presence(
    tape_rows: list[dict],
    engine: str,
    sessions: list[str],
) -> list[bool]:
    """Binary presence vector: True if ``engine`` fired in a session, False otherwise.

    This is an INDIVIDUAL engine presence (not pair co-fire), used to build the
    circular-shift null by shifting one engine's series relative to the other.
    Shifting destroys the pairing while preserving each engine's marginal firing rate.
    """
    fired_sessions: set[str] = set()
    for row in tape_rows:
        engines = row.get("engines") or []
        if engine in engines and row.get("as_of"):
            fired_sessions.add(row["as_of"])
    return [s in fired_sessions for s in sessions]


# ---------------------------------------------------------------------------
# Main scan
# ---------------------------------------------------------------------------


def run_discovery_scan(
    tape_rows: list[dict],
    now: datetime,
    gaps: list[str],
) -> list[dict]:
    """Run the engine-pair co-occurrence z-scan.

    Returns a list of candidate dicts (one per engine pair that has any
    co-occurrence or is above threshold).
    """
    produced_at = now.strftime("%Y-%m-%dT%H:%M:%SZ")

    # ── Extract sessions ─────────────────────────────────────────────────────
    strength_rows = [r for r in tape_rows if r.get("engines") and r.get("as_of")]
    sessions = sorted({r["as_of"] for r in strength_rows})
    n_sessions = len(sessions)

    if n_sessions == 0:
        return []

    # ── Honest-null: too-young tape ──────────────────────────────────────────
    young_tape = n_sessions < _MIN_SESSIONS_FOR_SCAN

    # ── Build co-occurrence counts ───────────────────────────────────────────
    cooccur, _, first_seen = _build_cooccurrence_by_session(tape_rows)

    # ── Collect all pairs ────────────────────────────────────────────────────
    all_pairs: set[tuple[str, str]] = set()
    for ea, inner in cooccur.items():
        for eb in inner:
            if ea < eb:
                all_pairs.add((ea, eb))

    if not all_pairs:
        gaps.append("confluence_discovery: no co-occurring engine pairs in tape")
        return []

    # ── Per-session presence vectors for null draws ──────────────────────────
    candidates: list[dict] = []

    for ea, eb in sorted(all_pairs):
        # HARD EXCLUSION: skip rotation × cycle pair (DON'T-TEST)
        if _is_forbidden_rotation_cycle_pair(ea, eb):
            continue  # counted in cooccur but no candidate emitted

        n_cooccur = cooccur.get(ea, {}).get(eb, cooccur.get(eb, {}).get(ea, 0))
        obs_rate = n_cooccur / n_sessions if n_sessions > 0 else 0.0
        pair_key = (ea, eb) if (ea, eb) in first_seen else (eb, ea)
        first_date = first_seen.get(pair_key, sessions[0] if sessions else "")

        if young_tape:
            # Honest-null: print accruing rows, no z fabricated
            candidates.append({
                "pair": f"{ea}+{eb}",
                "z": None,
                "n": n_cooccur,
                "first_seen": first_date,
                "note": f"accruing ({n_sessions}/{_MIN_SESSIONS_FOR_SCAN} sessions)",
                "state": "accruing",
                "rate_obs": round(obs_rate, 4),
                "rate_null_median": None,
                "produced_at": produced_at,
            })
            continue

        # ── Circular-shift null ──────────────────────────────────────────────
        # Build per-engine individual presence vectors (fired at all in a session,
        # regardless of co-fire partner).  Shift ea's vector relative to eb's to
        # destroy pairing while preserving each engine's marginal firing rate.
        ea_presence = _build_engine_session_presence(tape_rows, ea, sessions)
        eb_presence = _build_engine_session_presence(tape_rows, eb, sessions)

        null_rates: list[float] = []
        n_sessions_v = len(sessions)
        # Distinct NON-IDENTITY shifts only: shift=0 reproduces the observed pairing
        # and must never be a null draw, and repeated shifts add no information.
        # Deterministic stride subsample when there are more shifts than the budget.
        stride = max(1, (n_sessions_v - 1) // _NULL_DRAWS)
        shifts = list(range(1, n_sessions_v, stride))[:_NULL_DRAWS]
        for shift in shifts:
            # Shift eb's presence relative to ea (destroys pairing, preserves marginals)
            eb_shifted = eb_presence[shift:] + eb_presence[:shift]
            count = sum(
                1 for a_val, b_val in zip(ea_presence, eb_shifted)
                if a_val and b_val
            )
            null_rates.append(count / n_sessions_v if n_sessions_v > 0 else 0.0)

        # Compute z using robust_z over [null_rates + [obs_rate]] (obs is latest)
        all_rates = null_rates + [obs_rate]
        z, med, mad = _robust_z_latest(all_rates)

        null_median = statistics.median(null_rates) if null_rates else None

        if z is not None and abs(z) >= _Z_CANDIDATE_THRESH:
            state = "candidate"
            note = f"z={z:.2f} vs {len(null_rates)}-draw circular-shift null"
        elif z is not None:
            state = "below_thresh"
            note = f"z={z:.2f} (|z|<{_Z_CANDIDATE_THRESH})"
        else:
            state = "below_thresh"
            note = "z=null (degenerate null distribution)"

        candidates.append({
            "pair": f"{ea}+{eb}",
            "z": round(z, 4) if z is not None else None,
            "n": n_cooccur,
            "first_seen": first_date,
            "note": note,
            "state": state,
            "rate_obs": round(obs_rate, 4),
            "rate_null_median": round(null_median, 4) if null_median is not None else None,
            "produced_at": produced_at,
        })

    # Sort by |z| descending (accruing last)
    def _sort_key(c: dict) -> tuple:
        z = c.get("z")
        if z is None:
            return (0, 0.0)
        return (1, -abs(z))

    candidates.sort(key=_sort_key)
    return candidates


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def build_and_write(
    root: Path | str | None = None,
    now: datetime | None = None,
    out_path: Path | str | None = None,
    tape_path: Path | str | None = None,
) -> list[dict]:
    """Run discovery scan and write data/neuralweb/confluence_candidates.jsonl.

    Returns the list of candidate dicts.  Never raises.
    """
    if now is None:
        now = datetime.now(timezone.utc)

    repo = _repo_root(root)
    gaps: list[str] = []

    tape_file = (
        Path(tape_path)
        if tape_path
        else repo / "data" / "neuralweb" / "confluence_tape.jsonl"
    )
    dest = (
        Path(out_path)
        if out_path
        else repo / "data" / "neuralweb" / "confluence_candidates.jsonl"
    )

    tape_rows = _read_tape(tape_file, gaps)

    if not tape_rows:
        gaps.append(
            "confluence_discovery: tape empty or absent — no candidates emitted"
        )
        candidates: list[dict] = []
    else:
        try:
            candidates = run_discovery_scan(tape_rows, now, gaps)
        except Exception as exc:  # noqa: BLE001
            log.warning("confluence_discovery: scan failed — %s", exc)
            gaps.append(f"confluence_discovery: scan error — {exc}")
            candidates = []

    if gaps:
        log.warning("confluence_discovery: %d gap(s)", len(gaps))
        for g in gaps:
            log.warning("  - %s", g)

    # Write candidates (gated: nightly lane only)
    if not _ledger_advance_enabled():
        log.debug(
            "confluence_discovery.build_and_write: candidates write skipped "
            "(COLLECT_LANE != nightly)"
        )
        return candidates
    try:
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(
            "\n".join(
                json.dumps(c, ensure_ascii=False, default=str) for c in candidates
            ) + ("\n" if candidates else ""),
            encoding="utf-8",
        )
        log.info(
            "confluence_discovery: %d candidates written → %s",
            len(candidates),
            dest,
        )
    except Exception as exc:  # noqa: BLE001
        log.warning("confluence_discovery: write failed — %s", exc)

    return candidates
