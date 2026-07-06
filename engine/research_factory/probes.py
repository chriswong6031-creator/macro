"""engine.research_factory.probes — mechanical adversarial layer (RF-7a, W4).

Deterministic, zero LLM.  All three probes are FLAG-ONLY — they never
transition or kill a candidate; they populate the ``mechanical_probes``
block of the challenge packet, which the Opus reviewer sees as evidence.

Public API:
    collect_flags(candidate)       → dict  (ingest-time flags, not-applicable sentinels)
    gauntlet_legs(candidate)       → list[dict]  (leg verdicts from oracle screen artifact)
    permutation_probe(candidate)   → dict  (label-permutation robustness result)

All heavy imports (pandas, numpy) are forbidden here — pure stdlib only.
The permutation probe is stdlib-only by spec: random.seed / statistics path.
"""
from __future__ import annotations

import hashlib
import logging
import math
import random
import statistics
from typing import Any

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Sentinels (RF-7 — "not_applicable" sentinel, never null-as-zero)
# ---------------------------------------------------------------------------

_NOT_APPLICABLE = "not_applicable"


# ---------------------------------------------------------------------------
# 1. collect_flags(candidate)
# ---------------------------------------------------------------------------

# Flag names that probes can surface (superset; ingest may add others)
_INGEST_FLAGS = frozenset({
    "near_dup_review",
    "mechanism_spec_mismatch",
    "recent_only_columns",
    "scale_flagged",
})


def collect_flags(candidate: dict) -> dict[str, Any]:
    """Gather ingest-time probe flags from the candidate packet.

    Reads the ``flags`` list already set by the ingest script and
    materialises each recognised flag into the mechanical_probes dict.
    Flags not yet set are reported as False (not triggered).

    Returns a dict suitable for ``mechanical_probes`` — the caller merges
    it with the output of ``gauntlet_legs`` and ``permutation_probe`` to
    build the full block.

    Never modifies the candidate in-place.  No I/O.
    """
    flags: list[str] = list(candidate.get("flags") or [])
    flags_set = set(flags)

    # Near-dup: score surfaced from ingest; re-surface from flags list here.
    # The full score+nearest pair is in the near_dup sub-dict when available.
    near_dup_meta = candidate.get("near_dup") or {}
    near_dup_score = near_dup_meta.get("score")
    near_dup_nearest = near_dup_meta.get("nearest")
    near_dup_review = "near_dup_review" in flags_set

    # If there's no stored score but the flag is set, default to 1.0 (unknown but flagged)
    if near_dup_review and near_dup_score is None:
        near_dup_score = 1.0

    return {
        "near_dup": {
            "score": float(near_dup_score) if near_dup_score is not None else None,
            "nearest": near_dup_nearest,
            "flagged": near_dup_review,
        },
        "mechanism_spec_mismatch": "mechanism_spec_mismatch" in flags_set,
        "recent_only_columns": "recent_only_columns" in flags_set,
        "scale_flagged": "scale_flagged" in flags_set,
        # Passthrough: all flag strings, for human review context
        "raw_flags": sorted(flags),
    }


# ---------------------------------------------------------------------------
# 2. gauntlet_legs(candidate)
# ---------------------------------------------------------------------------

# The oracle reversion screen stores its result in the reversion block or
# in the artifacts dict.  We read both and normalise.
_LEG_KEYS = ("leg1", "leg2", "leg3", "leg4", "leg5", "leg6")


def _parse_leg_verdict(val: Any) -> str | None:
    """Coerce various stored shapes to 'PASS' / 'FAIL' / None."""
    if val is None:
        return None
    if isinstance(val, bool):
        return "PASS" if val else "FAIL"
    if isinstance(val, str):
        v = val.upper()
        if v in ("PASS", "P", "TRUE"):
            return "PASS"
        if v in ("FAIL", "F", "FALSE"):
            return "FAIL"
    return None


def gauntlet_legs(candidate: dict) -> list[dict]:
    """Extract existing numeric-gauntlet leg verdicts from screen artifacts.

    Reads from:
      1. candidate['artifacts']['reversion_screen']['gauntlet_legs'] (preferred)
      2. candidate['artifacts']['reversion_screen'] top-level leg keys
      3. candidate's reversion block (when stored in the oracle-domain style)

    Returns a list of dicts:
        [{"leg": "leg1", "verdict": "PASS"|"FAIL", "source": "..."},
         ...]

    If no gauntlet data is found, returns [].  NEVER fakes verdicts.
    """
    artifacts = candidate.get("artifacts") or {}

    # Path 1: explicit gauntlet_legs list in the screen artifact
    rev_screen = artifacts.get("reversion_screen") or {}
    if isinstance(rev_screen, dict):
        stored_legs = rev_screen.get("gauntlet_legs")
        if isinstance(stored_legs, list) and stored_legs:
            result = []
            for item in stored_legs:
                if not isinstance(item, dict):
                    continue
                leg = item.get("leg")
                verdict = _parse_leg_verdict(item.get("verdict") or item.get("result"))
                if leg and verdict:
                    result.append({"leg": leg, "verdict": verdict, "source": "artifact_gauntlet_legs"})
            if result:
                return result

        # Path 2: top-level leg keys in the screen artifact dict
        result = []
        for lk in _LEG_KEYS:
            if lk in rev_screen:
                verdict = _parse_leg_verdict(rev_screen[lk])
                if verdict is not None:
                    result.append({"leg": lk, "verdict": verdict, "source": "artifact_top_level"})
        if result:
            return result

    # Path 3: reversion block in oracle-domain style (stored directly on candidate)
    rev_block = candidate.get("reversion") or {}
    if isinstance(rev_block, dict):
        # The reversion block stores aggregate metrics; construct legs from frozen gates
        n = rev_block.get("n")
        wr = rev_block.get("wr")
        asym = rev_block.get("asym")
        ret_exit = rev_block.get("ret_exit")
        gauntlet = rev_block.get("gauntlet")

        result = []
        if n is not None:
            result.append({"leg": "leg1", "verdict": "PASS" if n >= 100 else "FAIL",
                           "source": "reversion_block_n"})
        if wr is not None:
            result.append({"leg": "leg2", "verdict": "PASS" if wr >= 0.62 else "FAIL",
                           "source": "reversion_block_wr"})
        if asym is not None:
            result.append({"leg": "leg3", "verdict": "PASS" if asym >= 1.5 else "FAIL",
                           "source": "reversion_block_asym"})
        if ret_exit is not None:
            result.append({"leg": "leg4", "verdict": "PASS" if ret_exit >= 0.01 else "FAIL",
                           "source": "reversion_block_ret_exit"})
        if gauntlet is not None:
            # If the overall gauntlet verdict is stored and we have leg 1-4,
            # the residual (leg5+leg6 = OOS holdout + timing placebo) is reflected in the overall.
            result.append({"leg": "gauntlet_overall",
                           "verdict": "PASS" if str(gauntlet).upper() == "PASS" else "FAIL",
                           "source": "reversion_block_gauntlet"})
        if result:
            return result

    return []


# ---------------------------------------------------------------------------
# 3. permutation_probe(candidate)
# ---------------------------------------------------------------------------

_NOT_APPLICABLE_SENTINEL = {
    "input_insensitive": _NOT_APPLICABLE,
    "note": "no per-fire outcome arrays present in artifacts",
}

# Threshold: if the permuted headline reaches within this fraction of the real,
# the probe flags input_insensitive=True.
_INSENSITIVE_MARGIN = 0.95   # permuted p95 >= 0.95 * real_metric => input insensitive

# Permutation count and seed derivation
_N_PERMUTATIONS = 200


def _seed_from_candidate_id(candidate_id: str) -> int:
    """Deterministic seed: SHA-256 of candidate_id → first 8 bytes → int."""
    h = hashlib.sha256(candidate_id.encode("utf-8")).digest()
    return int.from_bytes(h[:8], "big")


def _headline_metric(outcomes: list[float]) -> float | None:
    """Compute the headline metric: win-rate (fraction > 0).

    Returns None if outcomes is empty.
    """
    if not outcomes:
        return None
    return sum(1 for v in outcomes if v > 0) / len(outcomes)


def _sign_permuted_outcomes(outcomes: list[float], rng: random.Random) -> list[float]:
    """Return a sign-permuted copy: each value's sign is independently flipped with p=0.5.

    This is the standard label-permutation for binary outcomes: it tests whether
    the wins/losses are distinguishable from random sign assignment.
    """
    return [abs(v) * (1 if rng.random() < 0.5 else -1) for v in outcomes]


def permutation_probe(candidate: dict) -> dict[str, Any]:
    """Run a label-permutation robustness check.

    When per-fire outcome arrays are present in the candidate's artifacts
    (under any of the recognised paths below), runs N=200 label permutations
    seeded from the candidate_id hash and checks whether the permuted headline
    metric (win-rate) reaches within _INSENSITIVE_MARGIN of the real metric.

    Returns
    -------
    dict with keys:
        "input_insensitive"  : bool | "not_applicable"
        "real_metric"        : float | None
        "permuted_p95"       : float | None
        "n_permutations"     : int
        "note"               : str (diagnostic)

    The "not_applicable" sentinel is returned (never null) when no per-fire
    data is present.  Probes NEVER transition or kill.
    """
    candidate_id = candidate.get("candidate_id", "?")
    outcomes = _extract_outcome_array(candidate)

    if outcomes is None:
        return dict(_NOT_APPLICABLE_SENTINEL)

    if len(outcomes) == 0:
        return {
            "input_insensitive": _NOT_APPLICABLE,
            "note": "per-fire array present but empty",
        }

    real_metric = _headline_metric(outcomes)
    if real_metric is None:
        return {
            "input_insensitive": _NOT_APPLICABLE,
            "note": "could not compute headline metric from outcomes",
        }

    seed = _seed_from_candidate_id(candidate_id)
    rng = random.Random(seed)

    permuted_metrics: list[float] = []
    for _ in range(_N_PERMUTATIONS):
        perm = _sign_permuted_outcomes(outcomes, rng)
        m = _headline_metric(perm)
        if m is not None:
            permuted_metrics.append(m)

    if not permuted_metrics:
        return {
            "input_insensitive": _NOT_APPLICABLE,
            "note": "permutation loop produced no valid metrics",
        }

    permuted_metrics.sort()
    # p95 of permuted distribution
    idx = max(0, int(0.95 * len(permuted_metrics)) - 1)
    p95 = permuted_metrics[idx]

    # Flag: insensitive when permuted p95 reaches within margin of real
    if real_metric <= 0:
        input_insensitive = True
    else:
        input_insensitive = p95 >= _INSENSITIVE_MARGIN * real_metric

    return {
        "input_insensitive": input_insensitive,
        "real_metric": real_metric,
        "permuted_p95": p95,
        "n_permutations": len(permuted_metrics),
        "note": (
            f"seed={seed}; real_wr={real_metric:.4f}; "
            f"permuted_p95={p95:.4f}; "
            f"threshold={_INSENSITIVE_MARGIN * real_metric:.4f}; "
            f"insensitive={input_insensitive}"
        ),
    }


def _extract_outcome_array(candidate: dict) -> list[float] | None:
    """Extract per-fire outcome array from candidate artifacts.

    Returns None if no array is found (probe should return not_applicable).
    Returns a list[float] (possibly empty) when an array is found.

    Recognised paths (priority order):
      1. artifacts['reversion_screen']['outcomes']  (list of floats)
      2. artifacts['reversion_screen']['ret_exit_series']
      3. artifacts['outcomes']
      4. artifacts['ret_exit_series']
    """
    artifacts = candidate.get("artifacts") or {}
    rev_screen = artifacts.get("reversion_screen") or {}

    for path_obj, keys in [
        (rev_screen, ["outcomes", "ret_exit_series", "outcome_array"]),
        (artifacts, ["outcomes", "ret_exit_series", "outcome_array"]),
    ]:
        if not isinstance(path_obj, dict):
            continue
        for k in keys:
            val = path_obj.get(k)
            if isinstance(val, list):
                # Coerce to floats, dropping non-numeric items
                result = []
                for v in val:
                    try:
                        result.append(float(v))
                    except (TypeError, ValueError):
                        pass
                return result  # found a list (may be empty)

    return None  # no per-fire data found
