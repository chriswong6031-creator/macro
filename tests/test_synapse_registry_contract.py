"""tests/test_synapse_registry_contract.py — Registry structural contract tests.

(a) synapse.yml parses without error via engine.neuralweb.synapse.load_registry.
(b) validate_registry returns [] (zero violations).
(c) admin nw-scope is non-empty: nw_scoped_lobes() returns > 50 entries, guarding
    the silent-empty-masks-drift failure mode.
"""
from __future__ import annotations

from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent


def test_synapse_registry_parses() -> None:
    """load_registry() must succeed without raising."""
    from engine.neuralweb import synapse

    reg = synapse.load_registry(_REPO_ROOT)
    assert isinstance(reg, dict), "load_registry() must return a dict"
    assert "artifacts" in reg, "Registry must have an 'artifacts' key"


def test_synapse_registry_zero_violations() -> None:
    """validate_registry() must return an empty violations list."""
    from engine.neuralweb import synapse

    reg = synapse.load_registry(_REPO_ROOT)
    violations = synapse.validate_registry(reg)
    assert violations == [], (
        f"Registry has {len(violations)} violation(s):\n"
        + "\n".join(violations[:20])
    )


def test_nw_scoped_lobes_non_empty() -> None:
    """nw_scoped_lobes() must return more than 50 entries (guards silent-empty-masks-drift)."""
    from admin.neural_web import nw_scoped_lobes

    lobes = nw_scoped_lobes()
    assert len(lobes) > 50, (
        f"nw_scoped_lobes() returned only {len(lobes)} entries; "
        "expected > 50. The nw-scope filter may be silently empty, "
        "masking a registry or owner_program drift."
    )
