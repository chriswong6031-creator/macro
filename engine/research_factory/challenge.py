"""engine.research_factory.challenge — packet builder + reviewer-response validator (W4).

Implements RF-7 challenger law:
  - build_challenge_input(candidate): outcome-blind packet for the Opus reviewer.
  - validate_reviewer_response(json_obj): strict §5.3 validation; rejects confidence
    numbers; does NOT transition.
  - write_challenge(candidate_id, packet): assemble mechanical_probes + reviewer block
    → data/research_factory/challenges/<candidate_id>.json, then transition
    screened→challenged→human_review (both mechanical, actor='script').

Confidence-number smuggling is rejected per RF-7/RF-16.  Categorical output
contract per §5.3.  The transition wiring is mechanical (RF-5).

Pure stdlib — no pandas, no yaml, no third-party imports.
"""
from __future__ import annotations

import json
import logging
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

DEFAULT_RF_DIR = Path("data") / "research_factory"
CHALLENGES_DIR = DEFAULT_RF_DIR / "challenges"

# ---------------------------------------------------------------------------
# Outcome-blind field exclusion (RF-7b)
# The challenge input NEVER carries per-fire outcome series, realized PnL
# narratives, or post-window interpretations.
# ---------------------------------------------------------------------------

_EXCLUDED_KEYS = frozenset({
    # Per-fire series
    "outcomes", "ret_exit_series", "outcome_array",
    # Narrative fields that could carry realized outcomes
    "post_window_narrative", "realized_outcome", "live_pnl",
    # Full artifacts dict (we send only aggregate summaries)
    "artifacts",
    # Transition log (reviewer doesn't need provenance history)
    "transition_log",
})

# Which aggregate metrics to include (outcome-blind summary).
# Used as a WHITELIST for the reversion_screen artifact path (RF-7b):
# only these keys are emitted; any outcome-revealing scalar not listed here
# is silently dropped even if it appears in the reversion_screen dict.
_AGGREGATE_METRIC_KEYS = frozenset({
    "n", "WR", "wr", "asym", "ret_exit", "mean_ret_exit",
    "mean_MFE", "mean_MAE",
    # Gauntlet / risk-regime summary keys (safe — no per-fire outcome signal)
    "gauntlet", "search_width_at_scan", "risk_on", "risk_off", "asof",
})

# ---------------------------------------------------------------------------
# Forbidden reviewer response fields (RF-7/RF-16)
# ---------------------------------------------------------------------------

_FORBIDDEN_NUMERIC_FIELDS = frozenset({
    "confidence_score", "confidence", "score", "prob", "probability",
    "posterior", "prior", "belief", "credibility",
})

# §5.3 valid recommendation enum
_VALID_RECOMMENDATIONS = frozenset({
    "ADVISORY_REJECT",
    "ADVISORY_REVIEW",
    "ADVISORY_PASS",
})

# §5.3 blocker severity enum
_VALID_SEVERITIES = frozenset({"blocker", "major", "minor"})

# §5.3 blocker category enum (11 categories, incl. parametric_lookahead)
_VALID_CATEGORIES = frozenset({
    "lookahead",
    "parametric_lookahead",
    "survivorship",
    "overfit",
    "cost",
    "regime",
    "mechanism",
    "implementation",
    "data",
    "authority",
    "duplicate",
})


# ---------------------------------------------------------------------------
# Dedup context helpers (RF-14)
# ---------------------------------------------------------------------------

def _load_dedup_context(root: Path | None = None) -> dict[str, Any]:
    """Load the four dedup-context blocks absent-safely.

    Returns a dict with:
      - species_names: list[str]
      - machine_registry_hypotheses: list[str]
      - trial_ledger_families: list[str]
      - nw_quant_synthesis_s3_text: str (embedded verbatim prose)

    All sources are absent-safe.
    """
    _root = root or Path(".")

    # 1. Species names
    species_names: list[str] = []
    try:
        import engine.species_registry as sr
        reg = sr.load(_root / "data" / "species" / "registry.json")
        for s in reg.get("species", []):
            sid = s.get("species_id", "")
            name = s.get("name", "")
            if sid:
                species_names.append(sid)
            if name and name != sid:
                species_names.append(name)
    except Exception as exc:  # noqa: BLE001
        log.debug("dedup_context: species_registry unavailable: %s", exc)

    # 2. Machine-registry hypotheses (absent-safe)
    machine_hyps: list[str] = []
    mr_path = _root / "data" / "neuralweb" / "machine_registry.jsonl"
    if mr_path.exists():
        try:
            with mr_path.open(encoding="utf-8") as fh:
                for line in fh:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        row = json.loads(line)
                    except Exception:
                        continue
                    hyp = row.get("hypothesis") or row.get("name") or ""
                    if hyp:
                        machine_hyps.append(hyp[:200])
        except OSError as exc:
            log.debug("dedup_context: machine_registry.jsonl read error: %s", exc)

    # 3. Trial-ledger family strings
    families: list[str] = []
    tl_path = _root / "data" / "trial_ledger.jsonl"
    if tl_path.exists():
        seen: set[str] = set()
        try:
            with tl_path.open(encoding="utf-8") as fh:
                for line in fh:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        row = json.loads(line)
                    except Exception:
                        continue
                    fam = row.get("family")
                    if fam and fam not in seen:
                        seen.add(fam)
                        families.append(fam)
        except OSError as exc:
            log.debug("dedup_context: trial_ledger.jsonl read error: %s", exc)

    # 4. NW_QUANT_SYNTHESIS §3 duplicate table (embedded as text per RF-14)
    nw_s3_text = _NW_QUANT_S3_TEXT

    return {
        "species_names": sorted(set(species_names)),
        "machine_registry_hypotheses": machine_hyps,
        "trial_ledger_families": sorted(families),
        "nw_quant_synthesis_s3_text": nw_s3_text,
    }


# §3 table from research/NW_QUANT_SYNTHESIS_MASTERPLAN_BY_FABLE.md — embedded
# verbatim per RF-14 (prose table, never machine-parsed).
_NW_QUANT_S3_TEXT = """\
=== NW_QUANT_SYNTHESIS §3 — DUPLICATE-OF-EXISTING REGISTRY (do not re-propose) ===

| External proposal | Existing home | Status |
|---|---|---|
| Ownership-pressure map / 13F breadth | engine/beneficial_ownership.py, collectors/edgar_13f.py | built, display-only |
| ETF/fund-flow pressure | engine/etf_flows.py, engine/group_flow.py, exit-crowding phase0 | built / phase0 |
| Short-interest split | engine/short_volume.py; crowding phase0 null; no PIT SI history | built; split not backtestable |
| Options panic / dealer positioning | gex_engine.py, gex_model.py, options_skew.py, options_ivspread.py, market_gamma.py | built; RO-2 bars composites |
| Event calendar (macro) | engine/event_calendar.py, engine/event_risk.py | built |
| Crowding / effective bets | crowding.py, theme_crowding.py, froth_fragility.py, factor_exposure.py, fund_crowding.py; N_eff in reflexivity.py, foresight_enb.py | built; split-half FAIL |
| Post-event absorption | SETUP_SPECIES S9 (bad-news immunity), queued W3 | registered |
| Confidence surface (Brier/Wilson/ECE) | validation.py brier_reliability/ECE/platt; qledger Wilson; NW kernel | built; kernel arms 2026-10 |
| Hazard/survival desk | hazard_score.py, fit_cycle_hazard.py (macro-level) | built (macro); per-stock n-starved |
| Analogue retrieval | engine/oracle/memory.py::find_analogues | built |
| Falsifier generation | engine/falsifier_tripwires.py (+ per-ticker scope in item C) | built |
| Retirement state machine | engine/species_registry.py, experiments_registry.py | built |
| Disagreement mining | contradictions.py, factor_contradictions.py; W5A dissent study | built; study under-powered |
| Regime specialists (MoE) | regime gates exist; MoE is n-starved pre-kernel-arming | do not build now |
| Analyst dispersion / borrow / true fund flows | paid-data candidates | Phase-4 watchlist only |

=== END NW_QUANT_SYNTHESIS §3 TABLE ===
"""


# ---------------------------------------------------------------------------
# build_challenge_input(candidate)
# ---------------------------------------------------------------------------

def build_challenge_input(
    candidate: dict,
    root: Path | None = None,
) -> dict[str, Any]:
    """Build the outcome-blind challenge input packet for the Opus reviewer.

    RF-7b: no per-fire outcome series, no post-window narrative.
    The packet contains:
      - hypothesis, mechanism, candidate_type, domain, track
      - AGGREGATE metrics only (n, WR/effect, gauntlet leg verdicts)
      - mechanical_probes block (flags + permutation probe result)
      - dedup_context (species names, machine-registry hypotheses, trial families,
        NW_QUANT_SYNTHESIS §3 table text)

    Returns a JSON-serialisable dict.  Does NOT write to disk (caller's job).
    """
    from engine.research_factory.probes import (
        collect_flags,
        gauntlet_legs,
        permutation_probe,
    )

    candidate_id = candidate.get("candidate_id", "?")

    # Mechanical probes
    flags_block = collect_flags(candidate)
    legs = gauntlet_legs(candidate)
    perm = permutation_probe(candidate)

    mechanical_probes: dict[str, Any] = {
        "input_insensitive": perm.get("input_insensitive"),
        "permutation_probe": perm,
        "near_dup": flags_block.get("near_dup"),
        "mechanism_spec_mismatch": flags_block.get("mechanism_spec_mismatch"),
        "recent_only_columns": flags_block.get("recent_only_columns"),
        "scale_flagged": flags_block.get("scale_flagged"),
        "raw_flags": flags_block.get("raw_flags"),
        "gauntlet_legs": legs,
    }

    # Aggregate metrics from artifacts — OUTCOME-BLIND
    aggregate_metrics = _extract_aggregate_metrics(candidate)

    # Dedup context (RF-14)
    dedup_context = _load_dedup_context(root)

    # Core candidate metadata (outcome-blind subset)
    packet: dict[str, Any] = {
        "schema": "research_factory.challenge_input.v1",
        "candidate_id": candidate_id,
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        # Identity fields
        "hypothesis": candidate.get("hypothesis"),
        "mechanism": candidate.get("mechanism"),
        "candidate_type": candidate.get("candidate_type"),
        "domain": candidate.get("domain"),
        "track": _infer_track(candidate),
        "spec_ref": candidate.get("spec_ref"),
        "evaluation_plan": candidate.get("evaluation_plan"),
        "decay_conditions": candidate.get("decay_conditions") or [],
        "expected_failure_modes": candidate.get("expected_failure_modes") or [],
        "falsifiers": candidate.get("falsifiers") or [],
        "trial_accounting": candidate.get("trial_accounting"),
        # Aggregate-only metrics (never per-fire series)
        "aggregate_metrics": aggregate_metrics,
        # Mechanical probes
        "mechanical_probes": mechanical_probes,
        # Dedup context refs (RF-14)
        "dedup_context": dedup_context,
        # Source tracking
        "source": candidate.get("source"),
        "authority": "display_only",
    }

    return packet


def _infer_track(candidate: dict) -> str:
    """Infer the evaluation track from candidate metadata."""
    domain = candidate.get("domain", "")
    artifacts = candidate.get("artifacts") or {}
    rev_screen = artifacts.get("reversion_screen") or {}
    if isinstance(rev_screen, dict) and rev_screen.get("gauntlet") == "PASS":
        return "reversion"
    reversion = candidate.get("reversion") or {}
    if isinstance(reversion, dict) and reversion.get("gauntlet") == "PASS":
        return "reversion"
    if domain == "oracle":
        return "oracle_63d"
    return domain or "unknown"


def _extract_aggregate_metrics(candidate: dict) -> dict[str, Any]:
    """Extract aggregate metrics from candidate artifacts (no per-fire series).

    Reads from:
      - candidate['artifacts']['reversion_screen'] top-level aggregates
      - candidate['reversion'] block (oracle domain)
      - candidate['artifacts']['screen_result']
    Never includes outcome arrays, ret_exit_series, or narrative fields.
    """
    out: dict[str, Any] = {}
    artifacts = candidate.get("artifacts") or {}

    # Oracle reversion block
    rev_block = candidate.get("reversion") or {}
    if isinstance(rev_block, dict):
        for k in ("n", "wr", "asym", "ret_exit", "gauntlet", "asof",
                  "risk_on", "risk_off"):
            if k in rev_block:
                out[k] = rev_block[k]

    # Screen artifact (reversion_screen) — WHITELIST ONLY (RF-7b).
    # We must not pass outcome-revealing scalars such as best_fire_return,
    # per_fire_max_gain, or max_drawdown_realized even if they are not lists.
    # Only the keys in _AGGREGATE_METRIC_KEYS are emitted; everything else is
    # dropped.  This mirrors the reversion-block path (lines above) which also
    # uses a fixed key set.
    rev_screen = artifacts.get("reversion_screen") or {}
    if isinstance(rev_screen, dict):
        for k in _AGGREGATE_METRIC_KEYS:
            if k in rev_screen:
                out[k] = rev_screen[k]

    # screen_result artifact (oracle 63d screen per-section dicts) — WHITELIST ONLY (RF-7b).
    # Per-section dicts from adapter_oracle.py contain outcome-revealing scalars such as
    # best_fire_return, max_drawdown_realized, per_fire_max_gain, post_fire_alpha.
    # The blocklist + isinstance(v,list) filter used before was insufficient: it passed
    # all scalars not named in _EXCLUDED_KEYS, leaking realized outcomes to the reviewer.
    # Only keys in _AGGREGATE_METRIC_KEYS are emitted; everything else is silently dropped.
    screen_result = artifacts.get("screen_result") or {}
    if isinstance(screen_result, dict):
        for section in ("all", "risk_on", "risk_off"):
            section_data = screen_result.get(section) or {}
            if isinstance(section_data, dict):
                agg: dict[str, Any] = {
                    k: section_data[k]
                    for k in _AGGREGATE_METRIC_KEYS
                    if k in section_data
                }
                if agg:
                    out[f"screen_{section}"] = agg

    # search_width_at_scan (required for oracle review per charter §6 W3)
    swas = artifacts.get("search_width_at_scan")
    if swas is not None:
        out["search_width_at_scan"] = swas

    return out


# ---------------------------------------------------------------------------
# validate_reviewer_response(json_obj)
# ---------------------------------------------------------------------------

def validate_reviewer_response(json_obj: Any) -> list[str]:
    """Validate a reviewer-response dict against §5.3 schema.

    Returns a list of human-readable violation strings (empty = valid).
    Does NOT raise; the caller decides how to handle violations.

    Checks:
      - Must be a dict
      - recommendation: required, ADVISORY_* enum
      - blockers: list of {severity, category, finding}
      - NO numeric confidence fields (RF-7/RF-16) — confidence-number smuggling
      - candidate_id: required
    """
    if not isinstance(json_obj, dict):
        return ["reviewer response must be a JSON object (dict); got " + type(json_obj).__name__]

    errs: list[str] = []

    # --- Required: candidate_id ---
    if not json_obj.get("candidate_id"):
        errs.append("reviewer response missing required field 'candidate_id'")

    # --- Required: recommendation (ADVISORY_* enum) ---
    rec = json_obj.get("recommendation")
    if rec is None:
        errs.append("reviewer response missing required field 'recommendation'")
    elif rec not in _VALID_RECOMMENDATIONS:
        errs.append(
            f"reviewer recommendation {rec!r} is not in the ADVISORY_* enum "
            f"({sorted(_VALID_RECOMMENDATIONS)}) — only ADVISORY_* values are allowed "
            f"(RF-7: the reviewer is advisory-only, never a gate)"
        )

    # --- Confidence-number smuggling (RF-7/RF-16) ---
    for fn in _FORBIDDEN_NUMERIC_FIELDS:
        if fn in json_obj:
            val = json_obj[fn]
            errs.append(
                f"reviewer response contains forbidden numeric field {fn!r}={val!r} — "
                f"LLM confidence scores are prohibited (RF-7/RF-16)"
            )

    # --- blockers (optional list, but each must conform) ---
    blockers = json_obj.get("blockers")
    if blockers is not None:
        if not isinstance(blockers, list):
            errs.append("reviewer response 'blockers' must be a list")
        else:
            for i, b in enumerate(blockers):
                if not isinstance(b, dict):
                    errs.append(f"reviewer blockers[{i}] must be a dict")
                    continue
                sev = b.get("severity")
                if sev is not None and sev not in _VALID_SEVERITIES:
                    errs.append(
                        f"reviewer blockers[{i}].severity {sev!r} not in "
                        f"{sorted(_VALID_SEVERITIES)}"
                    )
                cat = b.get("category")
                if cat is not None and cat not in _VALID_CATEGORIES:
                    errs.append(
                        f"reviewer blockers[{i}].category {cat!r} not in the "
                        f"11-category enum {sorted(_VALID_CATEGORIES)}"
                    )
                # Confidence-number smuggling inside blockers
                for fn in _FORBIDDEN_NUMERIC_FIELDS:
                    if fn in b:
                        errs.append(
                            f"reviewer blockers[{i}] contains forbidden numeric "
                            f"field {fn!r} — confidence scores prohibited in blockers too"
                        )

    # --- agent_type must be 'reviewer' (RF-7) ---
    agent_type = json_obj.get("agent_type")
    if agent_type is not None and agent_type != "reviewer":
        errs.append(
            f"reviewer response agent_type={agent_type!r}; expected 'reviewer' "
            f"(RF-7 — challenger must be spawned as agentType='reviewer')"
        )

    return errs


# ---------------------------------------------------------------------------
# write_challenge(candidate_id, packet)
# ---------------------------------------------------------------------------

def write_challenge(
    candidate_id: str,
    packet: dict[str, Any],
    *,
    reviewer_response: dict | None = None,
    root: Path | None = None,
) -> Path:
    """Assemble mechanical_probes + reviewer block → challenges/<candidate_id>.json.

    Uses the challenge.v1 schema.  Validates the reviewer_response if provided.
    Caller must have already validated reviewer_response (use validate_reviewer_response).

    Parameters
    ----------
    candidate_id        : The candidate's ID (used for the filename).
    packet              : The build_challenge_input() result.
    reviewer_response   : Optional reviewer dict (already validated by caller).
    root                : Optional project root override.

    Returns
    -------
    Path to the written challenge JSON file.

    Raises
    ------
    ValueError  : If reviewer_response fails validation.
    """
    from engine.research_factory.ledger import DEFAULT_RF_DIR

    _root = root or Path(".")
    challenges_dir = _root / DEFAULT_RF_DIR / "challenges"
    challenges_dir.mkdir(parents=True, exist_ok=True)

    # Build the §5.3 challenge row
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    row: dict[str, Any] = {
        "schema": "research_factory.challenge.v1",
        "authority": "display_only",
        "candidate_id": candidate_id,
        "challenged_at": now,
        "mechanical_probes": packet.get("mechanical_probes") or {},
    }

    # Merge reviewer block if provided
    if reviewer_response is not None:
        # Final validation guard
        errs = validate_reviewer_response(reviewer_response)
        if errs:
            raise ValueError(
                f"write_challenge: reviewer_response failed validation for "
                f"{candidate_id!r}:\n  " + "\n  ".join(errs)
            )
        row["reviewer"] = {
            "agent_type": reviewer_response.get("agent_type", "reviewer"),
            "recommendation": reviewer_response.get("recommendation"),
            "blockers": reviewer_response.get("blockers") or [],
            "non_blocking_concerns": reviewer_response.get("non_blocking_concerns") or [],
            "best_counterargument": reviewer_response.get("best_counterargument"),
            "minimum_fix_to_reconsider": reviewer_response.get("minimum_fix_to_reconsider"),
            "falsifier_spec": reviewer_response.get("falsifier_spec"),
            "human_review_question": reviewer_response.get("human_review_question"),
        }

    # Atomic write via tempfile + replace
    out_path = challenges_dir / f"{candidate_id}.json"
    fd, tmp = tempfile.mkstemp(dir=str(challenges_dir), prefix=".tmp_", suffix=".json")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump(row, fh, indent=2, default=str)
        os.replace(tmp, str(out_path))
    except Exception:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise

    log.info("write_challenge: wrote %s", out_path)
    return out_path


# ---------------------------------------------------------------------------
# State transitions after a valid challenge write (RF-5, RF-7)
# ---------------------------------------------------------------------------

def _load_candidate(candidate_id: str, root: Path) -> dict | None:
    """Load the candidate dict from candidates.jsonl (absent-safe).

    Returns the most-recent row for ``candidate_id``, or None if not found.
    Used by _transition to give state.transition a candidate context for the
    screened-gate, as_of-monotonic, and respin checks (RF-5/RF-6).
    """
    from engine.research_factory.ledger import load_jsonl, DEFAULT_RF_DIR

    cands_path = root / DEFAULT_RF_DIR / "candidates.jsonl"
    rows = load_jsonl(cands_path)
    # Most-recent row wins (last occurrence per candidate_id)
    candidate = None
    for row in rows:
        if row.get("candidate_id") == candidate_id:
            candidate = row
    return candidate


def _transition(
    candidate_id: str,
    from_state: str,
    to_state: str,
    reason_code: str,
    reason_text: str,
    challenge_ref: str | None = None,
    root: Path | None = None,
) -> None:
    """Append one transition row to transitions.jsonl.

    Routes through engine.research_factory.state.transition to enforce the
    RF-5 allowed-pair matrix, actor-class gate (script actors barred from
    human-gate targets), mandatory-field-per-destination gate, and monotonic
    as_of — raising IllegalTransition on any violation.

    Mechanical actor ('script').
    """
    from engine.research_factory.ledger import append_row, DEFAULT_RF_DIR
    from engine.research_factory.schema import validate_transition
    from engine.research_factory.state import transition as state_transition

    _root = root or Path(".")
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")

    row: dict[str, Any] = {
        "schema": "research_factory.transition.v1",
        "authority": "display_only",
        "candidate_id": candidate_id,
        "from": from_state,
        "to": to_state,
        "reason_code": reason_code,
        "reason_text": reason_text,
        "actor": "script",
        "actor_ref": None,
        "as_of": now,
    }
    if challenge_ref:
        row["challenge_packet_ref"] = challenge_ref
    if to_state == "human_review":
        row["review_packet_ref"] = challenge_ref or f"challenges/{candidate_id}.json"

    # Load candidate for screened-gate + monotonic as_of checks (absent-safe).
    candidate = _load_candidate(candidate_id, _root)

    # Enforce the state machine BEFORE writing.  Raises IllegalTransition on any violation.
    state_transition(
        from_state=from_state,
        to_state=to_state,
        actor="script",
        transition_row=row,
        candidate=candidate,
    )

    transitions_path = _root / DEFAULT_RF_DIR / "transitions.jsonl"
    append_row(transitions_path, row, validate_fn=validate_transition)
    log.info(
        "transition: %s %s→%s (reason=%s)", candidate_id, from_state, to_state, reason_code
    )


def _get_candidate_current_status(candidate_id: str, root: Path) -> str | None:
    """Read the candidate's current status from the transitions log.

    Scans transitions.jsonl for the last transition row for this candidate_id
    and returns the ``to`` state.  Falls back to reading the candidate row's
    ``status`` field if no transition rows exist.  Returns None when the
    candidate cannot be found at all.
    """
    from engine.research_factory.ledger import load_jsonl, DEFAULT_RF_DIR

    # Prefer the last transition row (transitions.jsonl is authoritative)
    transitions_path = root / DEFAULT_RF_DIR / "transitions.jsonl"
    rows = load_jsonl(transitions_path)
    last_to: str | None = None
    for row in rows:
        if row.get("candidate_id") == candidate_id:
            last_to = row.get("to")
    if last_to is not None:
        return last_to

    # Fall back to the candidate row's status field
    candidate = _load_candidate(candidate_id, root)
    if candidate is not None:
        return candidate.get("status")

    return None


def apply_challenge_transitions(
    candidate_id: str,
    challenge_path: Path,
    *,
    root: Path | None = None,
) -> None:
    """Perform the two mechanical transitions after a valid challenge write.

    Per RF-5 / §4:
      screened → challenged  (challenge_packet_ref = path to .json)
      challenged → human_review  (unconditional — every challenged candidate enters the queue)

    Both are mechanical (actor='script').

    Idempotency guard (RF-5 audit-log integrity): if the candidate is already
    past ``screened`` (i.e. a prior run already applied the transitions), this
    call raises ValueError rather than appending spurious out-of-order rows to
    the append-only audit log.  Re-running --ingest-response on a candidate
    that is already in ``challenged`` or ``human_review`` is a caller error.
    """
    _root = root or Path(".")
    current_status = _get_candidate_current_status(candidate_id, _root)

    if current_status not in (None, "screened"):
        raise ValueError(
            f"apply_challenge_transitions: candidate {candidate_id!r} is already in "
            f"state {current_status!r} — cannot re-apply screened→challenged→human_review. "
            f"Re-running --ingest-response on a candidate that is already past 'screened' "
            f"would corrupt the append-only audit log."
        )

    challenge_ref = str(challenge_path)

    _transition(
        candidate_id,
        from_state="screened",
        to_state="challenged",
        reason_code="challenge_packet_complete",
        reason_text="Mechanical probes completed; challenge packet written.",
        challenge_ref=challenge_ref,
        root=root,
    )
    _transition(
        candidate_id,
        from_state="challenged",
        to_state="human_review",
        reason_code="challenger_advisory_complete",
        reason_text=(
            "Reviewer advisory received and schema-checked; unconditionally "
            "entering human_review queue (RF-7: every challenged candidate enters the queue)."
        ),
        challenge_ref=challenge_ref,
        root=root,
    )
