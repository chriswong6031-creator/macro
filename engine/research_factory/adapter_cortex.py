"""engine.research_factory.adapter_cortex — Cortex domain adapter (W3, RF-13).

POINTER / PROJECTION ONLY — this adapter NEVER:
  - writes machine_registry.jsonl
  - calls metabolism.register_hypothesis
  - creates a trial family
  - advances any domain lifecycle

Domain seam (RF-13 — Cortex):
  The factory reads data/neuralweb/machine_registry.jsonl ABSENT-SAFELY
  (the file does not exist today on main; adapter returns [] gracefully).
  source='cortex' candidates carry the metabolism-issued id as spec_ref with
  registration timestamp >= metabolism's registered_at.

Trial accounting (RF-6):
  mode = 'cortex_shared' — cortex candidates share the existing 'cortex'
  family and create NO new trial family.

Self-grading exclusion (RF-13 / evaluate_cortex_hypotheses._SELF_LEDGER_EXCLUSIONS):
  Before attaching any firings evidence, the adapter re-checks whether the
  hypothesis spine_query references cortex_attention (the closed self-grading
  loop forbidden by Article 1).  Any hypothesis that passes this check is
  flagged and returns with firings_evidence=None.

One-night cross-job lag (documented here per RF-13):
  The engine job reads the PRIOR NIGHT's cortex commit.  A hypothesis
  registered today will not have graded firings evidence until the following
  nightly run.  The adapter reflects this reality: firings evidence is read
  from the machine_registry row's stored result fields, not re-evaluated live.

Pure stdlib: no pandas, no yaml, no heavy imports at module level.
"""
from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# RF-2: Domain-status projection map (metabolism vocabulary → factory states)
# ---------------------------------------------------------------------------

#: Fixed projection mapping.  Applied at READ TIME — never persisted.
#: Rules:
#:   registered      → screened     (accepted by metabolism; challenge-eligible)
#:   insufficient-n  → awaiting_data (also handles underscore variant)
#:   insufficient_n  → awaiting_data
#:   failed          → numeric_rejected
#:   passed          → screened     (passed gate; factory's own transitions handle
#:                                   screened→challenged→human_review; projection
#:                                   must NOT promote beyond screened)
#:   budget-rejected → numeric_rejected  (rejected before entry; treat as terminal)
#:   invalid         → numeric_rejected  (invalid schema; terminal)
#:   retired         → numeric_rejected  (retired by operator; terminal)
#:   invalid-self-reference → numeric_rejected
#: Any other status is passed through with a warning.
METABOLISM_STATUS_PROJECTION: dict[str, str] = {
    "registered": "screened",
    "insufficient-n": "awaiting_data",
    "insufficient_n": "awaiting_data",   # underscore spelling guard
    "failed": "numeric_rejected",
    "passed": "screened",
    "budget-rejected": "numeric_rejected",
    "invalid": "numeric_rejected",
    "retired": "numeric_rejected",
    "invalid-self-reference": "numeric_rejected",
}


def project_metabolism_status(raw_status: str) -> str:
    """Project a raw metabolism status string to a factory display state (RF-2).

    Unknown statuses are passed through verbatim with a warning logged.
    Returns the projected state string.
    """
    projected = METABOLISM_STATUS_PROJECTION.get(raw_status)
    if projected is None:
        log.warning(
            "project_metabolism_status: unknown metabolism status %r — "
            "passing through verbatim (RF-2 projection map incomplete?)",
            raw_status,
        )
        return raw_status
    return projected


# ---------------------------------------------------------------------------
# Self-grading exclusion constants (mirrors evaluate_cortex_hypotheses)
# ---------------------------------------------------------------------------

#: Ledger / engine / family values that indicate a self-grading reference.
#: Mirrors _SELF_LEDGER_EXCLUSIONS in scripts/evaluate_cortex_hypotheses.py.
_SELF_LEDGER_EXCLUSIONS: frozenset[str] = frozenset({
    "cortex_attention",
    "reflex.cortex_attention",
})
_SELF_FAMILY_PREFIX: str = "reflex.cortex_attention"


def _spine_query_references_self(hypothesis: dict) -> bool:
    """Return True if the hypothesis spine_query references cortex_attention.

    Replicates the defense-in-depth check from evaluate_cortex_hypotheses.py
    and metabolism._validate_hypothesis.  Article 1 — the cortex may never be
    its own evidence.

    Checks:
      - spine_query.ledger in _SELF_LEDGER_EXCLUSIONS
      - spine_query.engine in _SELF_LEDGER_EXCLUSIONS
      - spine_query.family starts with _SELF_FAMILY_PREFIX
    """
    sq = hypothesis.get("spine_query") or {}
    if not sq:
        return False

    ledger_val = str(sq.get("ledger", ""))
    engine_val = str(sq.get("engine", ""))
    family_val = str(sq.get("family", ""))

    if ledger_val in _SELF_LEDGER_EXCLUSIONS:
        return True
    if engine_val in _SELF_LEDGER_EXCLUSIONS:
        return True
    if family_val.startswith(_SELF_FAMILY_PREFIX):
        return True

    return False


# ---------------------------------------------------------------------------
# Registry loader (absent-file-safe)
# ---------------------------------------------------------------------------

def load_machine_registry(data_dir: Path | None = None) -> list[dict]:
    """Load data/neuralweb/machine_registry.jsonl absent-safely.

    Returns [] when the file does not exist or cannot be parsed.
    Pure stdlib — no pandas.
    """
    _dir = Path(data_dir) if data_dir else Path("data")
    path = _dir / "neuralweb" / "machine_registry.jsonl"
    if not path.exists():
        log.debug(
            "machine_registry.jsonl not found at %s — cortex adapter returning []", path
        )
        return []
    rows: list[dict] = []
    try:
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                rows.append(json.loads(line))
            except Exception:  # noqa: BLE001
                continue
    except OSError as exc:
        log.warning("load_machine_registry: read failed: %s", exc)
    return rows


# ---------------------------------------------------------------------------
# Single-hypothesis adapter
# ---------------------------------------------------------------------------

def _parse_iso(ts: str | None) -> float | None:
    """Parse an ISO-8601 timestamp to a Unix float.  Returns None on failure."""
    if not ts:
        return None
    try:
        # Python 3.7+ fromisoformat handles most ISO-8601 variants; Z suffix
        # is handled by replacing 'Z' with '+00:00'.
        from datetime import datetime  # noqa: PLC0415
        cleaned = ts.replace("Z", "+00:00")
        return datetime.fromisoformat(cleaned).timestamp()
    except Exception:  # noqa: BLE001
        return None


def route_hypothesis(
    hypothesis: dict,
    *,
    data_dir: Path | None = None,
    registry_rows: list[dict] | None = None,
) -> dict:
    """Route a single cortex hypothesis through the factory adapter.

    Parameters
    ----------
    hypothesis : A single hypothesis row from machine_registry.jsonl, or a
                 synthetic dict built from a factory candidate (research_factory_run.py).
    data_dir   : Optional root data directory.
    registry_rows : Already-loaded machine_registry rows; pass from batch
                 callers (route_all) to avoid re-reading the file per row.

    Returns
    -------
    dict with keys:
      hypothesis_id         : str — metabolism-issued id
      spec_ref              : str — same as hypothesis_id (metabolism is authority)
      registered_at         : str | None — metabolism's registered_at
      domain_status         : str — PROJECTED factory display state (RF-2)
      domain_status_raw     : str — verbatim metabolism status (for audit)
      trial_accounting      : dict — mode='cortex_shared', family=None
      self_ref_excluded     : bool — True if spine_query references cortex_attention
      firings_evidence      : dict | None — stored result fields from registry row;
                              None when self_ref_excluded=True or absent
      rf13_timestamp_violation : bool — True when candidate timestamp precedes
                              the matched registry row's registered_at (RF-13)
      note                  : str — cross-job lag notice
    """
    hyp_id = hypothesis.get("id", "?")
    candidate_ts = hypothesis.get("registered_at")   # from candidate's perspective
    domain_status_raw = str(hypothesis.get("status") or "unknown")

    # RF-2: project domain status at read time — never persist the raw value.
    domain_status_projected = project_metabolism_status(domain_status_raw)

    # RF-13: check registration timestamp against the machine_registry row.
    # Load the registry to find the authoritative registered_at for this id.
    rf13_violation = False
    registry_registered_at: str | None = None
    if registry_rows is None:
        registry_rows = load_machine_registry(data_dir)
    matched_row = next(
        (r for r in registry_rows if r.get("id") == hyp_id), None
    )
    if matched_row is not None:
        registry_registered_at = matched_row.get("registered_at")
        cand_epoch = _parse_iso(candidate_ts)
        reg_epoch = _parse_iso(registry_registered_at)
        if cand_epoch is not None and reg_epoch is not None:
            if cand_epoch < reg_epoch:
                log.warning(
                    "route_hypothesis RF-13 timestamp violation: hypothesis %r "
                    "candidate timestamp %r precedes registry registered_at %r",
                    hyp_id,
                    candidate_ts,
                    registry_registered_at,
                )
                rf13_violation = True

    # RF-13: re-check self-grading exclusion before attaching firings evidence.
    self_ref = _spine_query_references_self(hypothesis)

    firings_evidence: dict | None = None
    if not self_ref:
        # Extract stored evaluation result fields from the registry row.
        # These are populated by evaluate_cortex_hypotheses after nightly run.
        # Prefer values from the matched registry row (authoritative) when available.
        src = matched_row if matched_row is not None else hypothesis
        firings_evidence = {
            "verdict": src.get("verdict"),
            "n": src.get("n"),
            "metric_value": src.get("metric_value"),
            "metric": src.get("metric"),
            "detail": src.get("detail"),
            # post-registration evidence fields (may be None if not yet graded)
            "pre_committed_gate": src.get("pre_committed_gate"),
        }
    else:
        log.info(
            "route_hypothesis: %s — self-grading exclusion triggered "
            "(spine_query references cortex_attention); firings_evidence=None",
            hyp_id,
        )

    return {
        "hypothesis_id": hyp_id,
        "spec_ref": hyp_id,   # metabolism-issued id is the authority ref
        "registered_at": registry_registered_at or candidate_ts,
        "domain_status": domain_status_projected,    # RF-2: projected state
        "domain_status_raw": domain_status_raw,       # verbatim for audit
        "trial_accounting": {
            "mode": "cortex_shared",
            "family": None,
            "declared_at": None,
        },
        "self_ref_excluded": self_ref,
        "firings_evidence": firings_evidence,
        "rf13_timestamp_violation": rf13_violation,
        "note": (
            "One-night cross-job lag: the engine job reads the prior night's "
            "cortex commit.  Firings evidence is read from the stored registry "
            "row — a hypothesis registered today will not have graded evidence "
            "until the following nightly run (RF-13)."
        ),
    }


# ---------------------------------------------------------------------------
# Batch adapter
# ---------------------------------------------------------------------------

def route_all(
    data_dir: Path | None = None,
) -> list[dict]:
    """Load all cortex hypotheses from machine_registry.jsonl and route them.

    Returns [] when the registry file is absent (absent-file-safe).
    """
    rows = load_machine_registry(data_dir)
    if not rows:
        log.debug("route_all: machine_registry empty or absent — returning []")
        return []

    results: list[dict] = []
    for hyp in rows:
        try:
            result = route_hypothesis(hyp, data_dir=data_dir, registry_rows=rows)
            results.append(result)
        except Exception as exc:  # noqa: BLE001
            log.error(
                "route_all: route_hypothesis failed for %s: %s",
                hyp.get("id", "?"), exc,
            )
    return results
