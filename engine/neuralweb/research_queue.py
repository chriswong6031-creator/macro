"""engine.neuralweb.research_queue — Read-only EV-ranker for the cortex research queue.

AUTHORITY LAW (FR-7 / FR-4)
-----------------------------
This module is READ-ONLY and advisory. It has zero write or gating authority over
the cortex.  ``metabolism.register_hypothesis()`` remains the sole budget chokepoint.
No LLM calls, no writes to machine_registry.jsonl or any registry.

OUTPUT CATEGORIES
-----------------
  high_ev_build_now    — feasible, novel, data-available; ranked by composite EV score.
  blocked_by_data      — spine query is not resolvable against the known artifact set.
  too_sparse           — expected sample size < MIN_N (server-side min_n clamp floor).
  duplicate_of_existing — mechanism/claim-shape overlaps an existing species or registered
                         cortex hypothesis.
  invalid_shape        — claim_shape or spine_query references cortex_attention (Article-1
                         self-reference guard).

SCORING COMPONENTS (all weights are MODULE CONSTANTS with rationale comments)
------------------------------------------------------------------------------
Each component returns a float in [0, 1] where 1 = best.

  feasibility_score  — n_expected vs MIN_N clamp.  Below MIN_N → too_sparse.
  novelty_score      — string/field overlap against existing species + registered
                       hypotheses.  Exact-field overlap → duplicate_of_existing.
  data_score         — spine_query family/engine/ledger resolvable in the known
                       artifact set → 1.0; not resolvable → blocked_by_data (0.0).
  horizon_score      — mild penalty for long horizons (slower feedback → lower EV).
                       Rationale: shorter horizons give faster evidence accrual,
                       which reduces the opportunity-cost of holding the budget slot.
  composite_ev       — weighted average of the above component scores (for
                       high_ev_build_now candidates only; others are short-circuited).

TRIAL-BUDGET PRESSURE
---------------------
The ranker reports ``trial_budget`` in the payload (informational).  It NEVER
enforces or alters the budget — that is metabolism.py's job.
"""
from __future__ import annotations

import json
import logging
import re
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants (weights with rationale)
# ---------------------------------------------------------------------------

# Server-side min_n floor (mirrors metabolism._HOUSE_MIN_N = 25).
# Candidates whose expected n < MIN_N are categorised as too_sparse before
# any further scoring — the server will reject them anyway.
MIN_N: int = 25

# EV composite weights — these are RESEARCH-PRIORITISER weights, not market
# signal weights.  Fixed + documented values are appropriate here (§B spec).

# novelty: the biggest driver of EV.  An idea we've already studied has near-zero
# marginal value.  Weight 0.35 — the single largest component.
_W_NOVELTY: float = 0.35

# data_score: no data → no experiment is possible at all.  Weight 0.30 — if data
# is unavailable the idea is irrelevant regardless of novelty.
_W_DATA: float = 0.30

# feasibility: n_expected controls statistical power.  Weight 0.20 — important,
# but an idea that is only barely feasible is still worth pursuing.
_W_FEASIBILITY: float = 0.20

# horizon_score: shorter horizons give faster feedback → higher EV.  Mild penalty;
# weight 0.15.  We do NOT want to systematically suppress long-horizon ideas.
_W_HORIZON: float = 0.15

# Horizon penalty parameters:
# Ideas with horizon_d <= HORIZON_FAST_D get score 1.0 (no penalty).
# Ideas with horizon_d >= HORIZON_SLOW_D get score HORIZON_MIN_SCORE (max penalty).
# Linear interpolation in between.
HORIZON_FAST_D: int = 21
HORIZON_SLOW_D: int = 126
HORIZON_MIN_SCORE: float = 0.5  # even a 126d horizon retains 50% of its EV

# Article-1 self-reference guard — spine_query may not reference cortex_attention.
_SELF_REF_FORBIDDEN: frozenset[str] = frozenset({
    "cortex_attention",
    "reflex.cortex_attention",
})

# Legal claim shapes (from metabolism.CLAIM_SHAPES).
_LEGAL_CLAIM_SHAPES: frozenset[str] = frozenset({
    "lead_lag",
    "conditional_regime",
    "entry_quality",
    "sector_conditional",
})

# Known data artifact families — used for data-availability scoring.
# These are the families/engines that the spine index + known artifact set can
# resolve.  Anything not on this list is flagged blocked_by_data.
# The set is deliberately conservative: we only include families that are
# verifiably present in synapse.yml / git.
_KNOWN_RESOLVABLE_FAMILIES: frozenset[str] = frozenset({
    # Breadth / regime families
    "breadth",
    "regime",
    "regime_vector",
    "risk_radar",
    "macro",
    # Signal families
    "gate_fires",
    "gate_fires_deep",
    "gate_fires_baskets",
    "standouts",
    "signal_gate",
    # NW families
    "kernel",
    "kernel_estimates",
    "cortex",
    "species",
    # Ledger families
    "track_record",
    "trial_ledger",
    "board_ledger",
    "china_standout_track",
    # Factor / analytics
    "factor",
    "ic_scorecard",
    "momentum",
    "reversal",
    # Sector / basket families
    "sector",
    "baskets",
    "rotation",
    # Entry / bottom families
    "entry",
    "bottom_sensors",
    "entry_quality",
    "impulse",
    # Options
    "options",
    "gex",
    "vol_regime",
})


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _load_json_lines(p: Path) -> list[dict]:
    """Load a JSONL file, returning empty list if absent/unreadable."""
    if not p.exists():
        return []
    rows: list[dict] = []
    try:
        for line in p.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                rows.append(json.loads(line))
            except Exception:  # noqa: BLE001
                pass
    except Exception as exc:  # noqa: BLE001
        log.warning("research_queue: could not load %s (%s)", p, exc)
    return rows


def _load_json(p: Path) -> dict | list | None:
    """Load a JSON file, returning None if absent/unreadable."""
    if not p.exists():
        return None
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception as exc:  # noqa: BLE001
        log.warning("research_queue: could not load %s (%s)", p, exc)
        return None


def _repo_root(root: Path | str | None = None) -> Path:
    if root is not None:
        return Path(root)
    try:
        from lib import config as _cfg  # type: ignore[import]
        return Path(_cfg.data_dir()).parent
    except Exception:  # noqa: BLE001
        # Fall back: three levels up from this file (engine/neuralweb/research_queue.py)
        return Path(__file__).resolve().parent.parent.parent


# ---------------------------------------------------------------------------
# Input loaders (all absent-file-safe)
# ---------------------------------------------------------------------------

def _load_machine_registry(root: Path) -> list[dict]:
    """Load machine_registry.jsonl — absent-file-safe."""
    p = root / "data" / "neuralweb" / "machine_registry.jsonl"
    return _load_json_lines(p)


def _load_due_hypotheses(root: Path) -> list[dict]:
    """Load hypotheses past their come_back date via metabolism.load_due()."""
    try:
        from engine.neuralweb import metabolism as _met  # type: ignore[import]
        return _met.load_due(root=root)
    except Exception as exc:  # noqa: BLE001
        log.warning("research_queue: could not load_due from metabolism (%s)", exc)
        return []


def _load_hypothesis_inbox(root: Path) -> list[dict]:
    """Load staged cortex proposals from hypothesis_inbox.jsonl — absent-file-safe."""
    p = root / "data" / "neuralweb" / "cortex" / "hypothesis_inbox.jsonl"
    return _load_json_lines(p)


def _load_species(root: Path) -> list[dict]:
    """Load species registry entries via engine.species_registry.load()."""
    try:
        from engine import species_registry as _sr  # type: ignore[import]
        reg = _sr.load(root / "data" / "species" / "registry.json")
        return reg.get("species", [])
    except Exception as exc:  # noqa: BLE001
        log.warning("research_queue: could not load species registry (%s)", exc)
        return []


def _load_family_trial_counts(root: Path) -> dict[str, int]:
    """Load family-level trial counts from the trial ledger.

    Returns {family: effective_n}.  The 'cortex' FDR family is hard-wired
    and must not be conflated with human program families.
    """
    try:
        from engine.trial_ledger import TrialLedger, DEFAULT_PATH  # type: ignore[import]
        p = root / "data" / "trial_ledger.jsonl"
        if not p.exists():
            p = DEFAULT_PATH
        led = TrialLedger(path=p)
        # Gather all families seen in the ledger
        families: dict[str, int] = {}
        for fam in led._seen:  # noqa: SLF001 — accessing internals for read-only census
            families[fam] = led.effective_n(fam)
        for fam in led._declared:  # noqa: SLF001
            if fam not in families:
                families[fam] = led.effective_n(fam)
        return families
    except Exception as exc:  # noqa: BLE001
        log.warning("research_queue: could not load trial ledger (%s)", exc)
        return {}


# ---------------------------------------------------------------------------
# Article-1 guard
# ---------------------------------------------------------------------------

def _has_self_ref(candidate: dict) -> bool:
    """Return True if spine_query references cortex_attention (Article 1 violation)."""
    sq = candidate.get("spine_query") or {}
    if not isinstance(sq, dict):
        return False
    values = {
        str(sq.get("family", "")),
        str(sq.get("engine", "")),
        str(sq.get("ledger", "")),
    }
    return bool(values & _SELF_REF_FORBIDDEN) or str(sq.get("family", "")).startswith(
        "reflex.cortex_attention"
    )


def _has_invalid_claim_shape(candidate: dict) -> bool:
    """Return True if the candidate has an illegal claim_shape."""
    return candidate.get("claim_shape") not in _LEGAL_CLAIM_SHAPES


# ---------------------------------------------------------------------------
# Overlap / novelty helpers
# ---------------------------------------------------------------------------

def _mechanism_tokens(text: str) -> frozenset[str]:
    """Tokenise a mechanism/hypothesis string for overlap detection."""
    # lower-case, split on whitespace + punctuation, drop stopwords
    _STOP = frozenset({
        "the", "a", "an", "and", "or", "in", "on", "of", "to", "is", "are",
        "that", "this", "with", "as", "by", "for", "from", "at", "not", "no",
        "it", "its", "be", "been", "have", "has", "had", "do", "does", "did",
        "will", "would", "could", "should", "may", "might", "can",
    })
    words = re.split(r"[\s,.:;()\[\]{}'\"!?/\\—–\-]+", text.lower())
    return frozenset(w for w in words if len(w) > 2 and w not in _STOP)


def _overlap_ratio(tokens_a: frozenset[str], tokens_b: frozenset[str]) -> float:
    """Jaccard overlap between two token sets."""
    if not tokens_a or not tokens_b:
        return 0.0
    intersection = tokens_a & tokens_b
    union = tokens_a | tokens_b
    return len(intersection) / len(union)

# Threshold above which two candidates are considered "same mechanism" duplicates.
_DUPLICATE_OVERLAP_THRESHOLD: float = 0.55


def _is_duplicate_of(
    candidate_tokens: frozenset[str],
    candidate_shape: str,
    existing_tokens: frozenset[str],
    existing_shape: str,
) -> bool:
    """True if the candidate is a probable duplicate of an existing entry.

    Shape matching applies only when both entries have a concrete claim shape
    (neither is 'species').  A candidate that overlaps a species entry is always
    flagged as a duplicate regardless of claim_shape — the mechanism description
    is the primary duplicate signal for species, which don't have claim_shapes.
    """
    # When either side is the 'species' pseudo-shape, skip shape requirement
    # and rely purely on mechanism-token overlap.
    if existing_shape != "species" and candidate_shape != existing_shape:
        return False
    return _overlap_ratio(candidate_tokens, existing_tokens) >= _DUPLICATE_OVERLAP_THRESHOLD


# ---------------------------------------------------------------------------
# Data-availability scoring
# ---------------------------------------------------------------------------

def _data_score(candidate: dict) -> float:
    """Score 1.0 if spine_query is resolvable; 0.0 if not."""
    sq = candidate.get("spine_query") or {}
    if not isinstance(sq, dict):
        return 0.0
    family = str(sq.get("family", "")).strip()
    engine = str(sq.get("engine", "")).strip()
    # Either family or engine must be resolvable
    resolvable = (
        family in _KNOWN_RESOLVABLE_FAMILIES
        or engine in _KNOWN_RESOLVABLE_FAMILIES
        or any(family.startswith(f) for f in _KNOWN_RESOLVABLE_FAMILIES)
    )
    return 1.0 if resolvable else 0.0


# ---------------------------------------------------------------------------
# Component scorers
# ---------------------------------------------------------------------------

def _feasibility_score(candidate: dict) -> float:
    """0.0 → 1.0.  Based on n_expected vs MIN_N clamp.

    Below MIN_N → 0.0 (caller should categorise as too_sparse).
    At MIN_N → 0.5; 3×MIN_N or above → 1.0.
    """
    n = candidate.get("n_expected") or candidate.get("pre_committed_gate", {}).get("min_n", 0)
    try:
        n = int(n)
    except (TypeError, ValueError):
        return 0.0
    if n < MIN_N:
        return 0.0
    # Logarithmic scaling: MIN_N → 0.5, 3*MIN_N → 1.0
    import math  # noqa: PLC0415
    ratio = n / MIN_N
    return min(1.0, 0.5 + 0.5 * math.log(ratio, 3))


def _novelty_score(
    candidate_tokens: frozenset[str],
    candidate_shape: str,
    existing_token_sets: list[tuple[frozenset[str], str]],
) -> float:
    """0.0 → 1.0.  Lower overlap with existing ideas → higher novelty.

    If maximum overlap exceeds _DUPLICATE_OVERLAP_THRESHOLD → 0.0 (caller
    should mark as duplicate_of_existing).

    Shape matching is relaxed when the existing entry is a species (shape='species'):
    species don't have claim_shapes, so any high-overlap mechanism is treated as
    a duplicate regardless of the candidate's claim_shape.
    """
    if not existing_token_sets:
        return 1.0

    def _effective_overlap(et: frozenset[str], cs: str) -> float:
        # Species bucket: no shape requirement — mechanism overlap is sufficient
        if cs == "species" or cs == candidate_shape:
            return _overlap_ratio(candidate_tokens, et)
        return 0.0

    max_overlap = max(_effective_overlap(et, cs) for et, cs in existing_token_sets)
    if max_overlap >= _DUPLICATE_OVERLAP_THRESHOLD:
        return 0.0
    # Map 0 → 1.0, approaching threshold → 0.0 linearly
    return 1.0 - (max_overlap / _DUPLICATE_OVERLAP_THRESHOLD)


def _horizon_score(candidate: dict) -> float:
    """0.5 → 1.0.  Shorter horizons score higher (faster feedback).

    horizon_d <= HORIZON_FAST_D → 1.0.
    horizon_d >= HORIZON_SLOW_D → HORIZON_MIN_SCORE (0.5).
    Linear interpolation between.
    """
    hd = candidate.get("horizon_d") or candidate.get("pre_committed_gate", {}).get("horizon_d", 63)
    try:
        hd = int(hd)
    except (TypeError, ValueError):
        hd = 63
    if hd <= HORIZON_FAST_D:
        return 1.0
    if hd >= HORIZON_SLOW_D:
        return HORIZON_MIN_SCORE
    span = HORIZON_SLOW_D - HORIZON_FAST_D
    return 1.0 - (1.0 - HORIZON_MIN_SCORE) * (hd - HORIZON_FAST_D) / span


def _composite_ev(f: float, n: float, d: float, h: float) -> float:
    """Weighted EV composite for high_ev_build_now candidates."""
    return _W_FEASIBILITY * f + _W_NOVELTY * n + _W_DATA * d + _W_HORIZON * h


# ---------------------------------------------------------------------------
# Main ranking function
# ---------------------------------------------------------------------------

def _candidate_id(candidate: dict, idx: int) -> str:
    """Return a stable identifier for a candidate."""
    # Prefer explicit ids; fall back to index.
    return (
        candidate.get("id")
        or candidate.get("species_id")
        or f"candidate_{idx}"
    )


def build_queue(root: Path | str | None = None) -> dict:
    """Rank research candidates and return the output payload.

    This function is READ-ONLY — it writes nothing.
    The returned dict is ready to be envelope-stamped and written to disk by
    the caller (scripts/build_research_queue.py).

    Returns
    -------
    dict with keys:
        candidates       — full ranked list with per-candidate metadata
        high_ev_build_now — list of candidate ids in priority order
        blocked_by_data  — list of candidate ids
        too_sparse       — list of candidate ids
        duplicate_of_existing — list of candidate ids
        invalid_shape    — list of candidate ids
        next_best_experiment — id of the single top-ranked high_ev candidate,
                               or None if the list is empty
        trial_budget     — informational budget status dict
        as_of            — ISO-8601 UTC timestamp of this ranking run
    """
    r = _repo_root(root)

    # ------------------------------------------------------------------
    # 1. Load all inputs (absent-file-safe)
    # ------------------------------------------------------------------
    machine_rows = _load_machine_registry(r)
    due_rows = _load_due_hypotheses(r)
    inbox_rows = _load_hypothesis_inbox(r)
    species_list = _load_species(r)
    family_trial_counts = _load_family_trial_counts(r)

    # ------------------------------------------------------------------
    # 2. Build existing knowledge base for overlap detection
    # ------------------------------------------------------------------
    # Collect (tokens, claim_shape, id) for all existing species + registered hypotheses
    existing_knowledge: list[tuple[frozenset[str], str, str]] = []

    for sp in species_list:
        mech = str(sp.get("mechanism", ""))
        name = str(sp.get("name", ""))
        tokens = _mechanism_tokens(mech + " " + name)
        # Species don't have a claim_shape per se; use a synthetic one
        existing_knowledge.append((tokens, "species", sp.get("species_id", "?")))

    for row in machine_rows:
        if row.get("status") in ("budget-rejected", "invalid"):
            continue
        hyp = str(row.get("hypothesis", ""))
        tokens = _mechanism_tokens(hyp)
        shape = row.get("claim_shape", "unknown")
        existing_knowledge.append((tokens, shape, row.get("id", "?")))

    existing_token_sets: list[tuple[frozenset[str], str]] = [
        (t, s) for t, s, _ in existing_knowledge
    ]

    # ------------------------------------------------------------------
    # 3. Assemble candidate list
    # ------------------------------------------------------------------
    # Candidates come from:
    #   a) hypothesis_inbox.jsonl (staged cortex proposals — primary source)
    #   b) due hypotheses from machine_registry (for re-ranking)
    #   c) phase0 species (rankable research candidates)

    raw_candidates: list[tuple[str, dict]] = []  # (source, candidate_dict)

    for row in inbox_rows:
        raw_candidates.append(("inbox", row))

    # Due hypotheses that need re-evaluation
    for row in due_rows:
        raw_candidates.append(("due", row))

    # Phase0 species (not yet accruing — rankable candidates)
    for sp in species_list:
        if sp.get("validation_status") in ("phase0",):
            raw_candidates.append(("species", sp))

    # Deduplicate by id
    seen_ids: set[str] = set()
    candidates: list[dict] = []
    for src, raw in raw_candidates:
        cid = _candidate_id(raw, len(candidates))
        if cid in seen_ids:
            continue
        seen_ids.add(cid)
        # Normalise to a common shape
        c: dict[str, Any] = dict(raw)
        c.setdefault("_source", src)
        c.setdefault("_candidate_id", cid)
        candidates.append(c)

    # ------------------------------------------------------------------
    # 4. Trial-budget pressure (informational)
    # ------------------------------------------------------------------
    cortex_trials = family_trial_counts.get("cortex", 0)
    # Budget from metabolism: 3 per week; remaining is informational
    from engine.neuralweb import metabolism as _met  # noqa: PLC0415
    try:
        now = datetime.now(timezone.utc)
        week_used = _met._count_week_registrations(r, now)  # noqa: SLF001
        week_budget = _met._BUDGET_PER_WEEK  # noqa: SLF001
        week_remaining = max(0, week_budget - week_used)
    except Exception as exc:  # noqa: BLE001
        log.warning("research_queue: budget check failed (%s)", exc)
        week_used = 0
        week_budget = 3
        week_remaining = 3

    trial_budget = {
        "week_used": week_used,
        "week_limit": week_budget,
        "week_remaining": week_remaining,
        "cortex_total_trials": cortex_trials,
        "note": "informational only — the ranker never enforces this budget",
    }

    # ------------------------------------------------------------------
    # 5. Score and categorise each candidate
    # ------------------------------------------------------------------
    ranked_high_ev: list[dict] = []
    blocked_by_data: list[str] = []
    too_sparse: list[str] = []
    duplicate_of_existing: list[str] = []
    invalid_shape_ids: list[str] = []

    scored_candidates: list[dict] = []

    for c in candidates:
        cid = c["_candidate_id"]
        c_shape = c.get("claim_shape", "")
        c_source = c.get("_source", "")

        # 5a. Article-1 guard — spine_query must not self-reference
        if _has_self_ref(c):
            invalid_shape_ids.append(cid)
            scored_candidates.append({
                "id": cid,
                "source": c_source,
                "category": "invalid_shape",
                "reason": "spine_query references cortex_attention (Article-1 self-reference guard)",
                "component_scores": {},
            })
            continue

        # 5b. Invalid claim_shape (for inbox / due rows; species have no claim_shape)
        if c_source in ("inbox", "due") and _has_invalid_claim_shape(c):
            invalid_shape_ids.append(cid)
            scored_candidates.append({
                "id": cid,
                "source": c_source,
                "category": "invalid_shape",
                "reason": f"claim_shape {c_shape!r} is not a legal shape",
                "component_scores": {},
            })
            continue

        # 5c. Feasibility check (too_sparse gate)
        fs = _feasibility_score(c)
        if fs == 0.0:
            # Check if n_expected is explicitly set; species without n_expected
            # are not gated by this (their sample size depends on the study design).
            n_exp = c.get("n_expected") or (c.get("pre_committed_gate") or {}).get("min_n")
            if n_exp is not None:
                too_sparse.append(cid)
                scored_candidates.append({
                    "id": cid,
                    "source": c_source,
                    "category": "too_sparse",
                    "reason": f"n_expected={n_exp} < MIN_N={MIN_N}",
                    "component_scores": {"feasibility": 0.0},
                })
                continue
            # If no n_expected is specified, treat as MIN_N (feasible) for species
            fs = 0.5

        # 5d. Tokenise mechanism for novelty + duplicate detection
        mech_text = (
            str(c.get("mechanism", ""))
            + " "
            + str(c.get("hypothesis", ""))
            + " "
            + str(c.get("name", ""))
        )
        c_tokens = _mechanism_tokens(mech_text)

        # Effective shape for novelty (species → use "species" bucket)
        eff_shape = c_shape if c_source in ("inbox", "due") else "species"

        # Check for duplicate
        dup_id: str | None = None
        for ex_tokens, ex_shape, ex_id in existing_knowledge:
            if _is_duplicate_of(c_tokens, eff_shape, ex_tokens, ex_shape):
                # Skip duplicating against itself (species registered and ranked)
                if ex_id != cid:
                    dup_id = ex_id
                    break

        if dup_id is not None:
            duplicate_of_existing.append(cid)
            scored_candidates.append({
                "id": cid,
                "source": c_source,
                "category": "duplicate_of_existing",
                "reason": f"mechanism overlaps existing entry: {dup_id}",
                "duplicate_of": dup_id,
                "component_scores": {"novelty": 0.0},
            })
            continue

        # 5e. Data-availability score
        ds = _data_score(c)
        if ds == 0.0:
            sq = c.get("spine_query") or {}
            blocked_by_data.append(cid)
            scored_candidates.append({
                "id": cid,
                "source": c_source,
                "category": "blocked_by_data",
                "reason": (
                    f"spine_query family={sq.get('family')!r} engine={sq.get('engine')!r} "
                    f"not resolvable in known artifact set"
                ),
                "component_scores": {"data": 0.0},
            })
            continue

        # 5f. Full scoring for high_ev_build_now candidates
        ns = _novelty_score(c_tokens, eff_shape, existing_token_sets)
        hs = _horizon_score(c)

        # DSR haircut proxy: families with huge trial counts get a mild EV haircut.
        # The cortex FDR family is hard-wired; do not conflate.
        fam = (c.get("spine_query") or {}).get("family", "")
        family_n = family_trial_counts.get(fam, 0)
        # Mild penalty: each doubling of trials beyond 10 reduces EV by 2%
        import math  # noqa: PLC0415
        trial_penalty = max(0.0, 0.02 * math.log2(max(1, family_n / 10))) if family_n > 10 else 0.0
        trial_penalty = min(0.15, trial_penalty)  # cap at 15% haircut

        ev = _composite_ev(fs, ns, ds, hs) * (1.0 - trial_penalty)

        entry = {
            "id": cid,
            "source": c_source,
            "category": "high_ev_build_now",
            "composite_ev": round(ev, 4),
            "component_scores": {
                "feasibility": round(fs, 4),
                "novelty": round(ns, 4),
                "data": round(ds, 4),
                "horizon": round(hs, 4),
                "trial_penalty": round(trial_penalty, 4),
            },
            "name": c.get("name", c.get("hypothesis", "")[:80]),
            "mechanism_excerpt": mech_text[:200].strip(),
        }
        # Attach original claim_shape / horizon_d for traceability
        if c_shape:
            entry["claim_shape"] = c_shape
        hd = c.get("horizon_d") or (c.get("pre_committed_gate") or {}).get("horizon_d")
        if hd:
            entry["horizon_d"] = hd
        ranked_high_ev.append(entry)
        scored_candidates.append(entry)

    # Sort high_ev by composite_ev descending
    ranked_high_ev.sort(key=lambda e: e["composite_ev"], reverse=True)

    high_ev_ids = [e["id"] for e in ranked_high_ev]
    next_best = high_ev_ids[0] if high_ev_ids else None

    # ------------------------------------------------------------------
    # 6. Assemble output payload (ready for envelope.stamp)
    # ------------------------------------------------------------------
    payload: dict[str, Any] = {
        "as_of": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "candidates": scored_candidates,
        "high_ev_build_now": high_ev_ids,
        "blocked_by_data": blocked_by_data,
        "too_sparse": too_sparse,
        "duplicate_of_existing": duplicate_of_existing,
        "invalid_shape": invalid_shape_ids,
        "next_best_experiment": next_best,
        "trial_budget": trial_budget,
        "summary": {
            "total_candidates": len(candidates),
            "high_ev": len(high_ev_ids),
            "blocked": len(blocked_by_data),
            "sparse": len(too_sparse),
            "duplicate": len(duplicate_of_existing),
            "invalid": len(invalid_shape_ids),
        },
    }

    return payload


# ---------------------------------------------------------------------------
# Output writer (called from the CLI runner — not from build_queue itself)
# ---------------------------------------------------------------------------

def write_queue(root: Path | str | None = None) -> dict:
    """Build and write the research queue artifact.

    Calls build_queue(), envelope-stamps the result, and writes it to
    ``data/neuralweb/research_queue.json``.  Returns the payload dict.
    """
    r = _repo_root(root)
    payload = build_queue(root=r)

    try:
        from engine.neuralweb.envelope import stamp  # type: ignore[import]
        from engine.neuralweb.synapse import load_registry  # type: ignore[import]
        reg = load_registry(r)
        payload = stamp(payload, artifact_id="research-queue", registry=reg)
    except Exception as exc:  # noqa: BLE001
        log.warning("research_queue: envelope stamp failed (%s); writing without stamp", exc)

    out = r / "data" / "neuralweb" / "research_queue.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    log.info("research_queue: wrote %s (%d candidates)", out, payload["summary"]["total_candidates"])
    return payload
