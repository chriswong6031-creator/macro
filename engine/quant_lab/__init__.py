"""Quant Lab — where EXTERNAL quant models are specified, recreated on our panel, and studied.

The lab exists because "recreate Fintel's QVM" is three separable questions that get
conflated into one:

  1. WHAT does the vendor actually disclose?   -> specs.py  (a provenance-carrying registry)
  2. CAN our substrate compute that leg?        -> legs.py   (+ a per-leg fidelity grade)
  3. DOES the recreation rank anything here?    -> study.py  (the house IC gauntlet)

Keeping them separate is the whole point. A vendor's marketing CAGR is not evidence about
our universe; a leg we compute from a different input is not the vendor's leg; and a
recreation that ranks nothing is a null we print rather than hide.

EPISTEMIC TIER (CLAUDE.md §Epistemics): everything here is DISPLAY-TIER research. The lab
may not promote a recreated score to rank/size/gate authority. Promotion needs a
pre-registered gauntlet run of its own — `study.py` produces the evidence, it does not
confer the authority. Vendor performance claims are reproduced as CLAIMS, attributed and
dated, never as findings of ours.

Entry points:
    specs.MODELS                    the registry (vendor spec + our recreation plan)
    legs.compute_legs(asof=...)     point-in-time leg cross-section
    score.model_scores(...)         vendor-shaped 0-100 percentile scores
    study.study_model(...)          IC / decile evidence for a recreation
"""
from __future__ import annotations

from engine.quant_lab import legs, score, specs, study  # noqa: F401

__all__ = ["specs", "legs", "score", "study"]
