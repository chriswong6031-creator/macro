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

def route_hypothesis(
    hypothesis: dict,
    *,
    data_dir: Path | None = None,
) -> dict:
    """Route a single cortex hypothesis through the factory adapter.

    Parameters
    ----------
    hypothesis : A single hypothesis row from machine_registry.jsonl.
    data_dir   : Optional root data directory.

    Returns
    -------
    dict with keys:
      hypothesis_id      : str — metabolism-issued id
      spec_ref           : str — same as hypothesis_id (metabolism is authority)
      registered_at      : str | None — metabolism's registered_at
      domain_status      : str — raw metabolism verdict/status
      trial_accounting   : dict — mode='cortex_shared', family=None
      self_ref_excluded  : bool — True if spine_query references cortex_attention
      firings_evidence   : dict | None — stored result fields from registry row;
                           None when self_ref_excluded=True or absent
      note               : str — cross-job lag notice
    """
    hyp_id = hypothesis.get("id", "?")
    registered_at = hypothesis.get("registered_at")
    domain_status = hypothesis.get("status", "unknown")

    # RF-13: re-check self-grading exclusion before attaching firings evidence
    self_ref = _spine_query_references_self(hypothesis)

    firings_evidence: dict | None = None
    if not self_ref:
        # Extract stored evaluation result fields from the registry row
        # These are populated by evaluate_cortex_hypotheses after nightly run
        firings_evidence = {
            "verdict": hypothesis.get("verdict"),
            "n": hypothesis.get("n"),
            "metric_value": hypothesis.get("metric_value"),
            "metric": hypothesis.get("metric"),
            "detail": hypothesis.get("detail"),
            # post-registration evidence fields (may be None if not yet graded)
            "pre_committed_gate": hypothesis.get("pre_committed_gate"),
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
        "registered_at": registered_at,
        "domain_status": domain_status,
        "trial_accounting": {
            "mode": "cortex_shared",
            "family": None,
            "declared_at": None,
        },
        "self_ref_excluded": self_ref,
        "firings_evidence": firings_evidence,
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
            result = route_hypothesis(hyp, data_dir=data_dir)
            results.append(result)
        except Exception as exc:  # noqa: BLE001
            log.error(
                "route_all: route_hypothesis failed for %s: %s",
                hyp.get("id", "?"), exc,
            )
    return results
