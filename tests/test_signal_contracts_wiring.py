"""Regression test: export_signal_contracts is wired into daily.yml (neural-web D7).

The contract files (golden_signals.json + artifact_manifest.json) must be
refreshed daily so Terminal consumers don't silently skip their conformance
gate. This test verifies:

  1. The daily.yml engine job contains an "export cross-repo signal contracts"
     step that invokes scripts.export_signal_contracts.
  2. The step is positioned AFTER the "build signal track-record ledger" step
     and BEFORE the "run regime engine" step, so engine.canon is available.
  3. The script's two output paths are under site/ (covered by the existing
     `git add data/ site/ reports/` glob in the commit step).
  4. The script's ARTIFACT_MANIFEST list is non-empty (sanity).
  5. The script's GOLDEN_SYMBOLS list is non-empty (sanity).

Run: python -m pytest tests/test_signal_contracts_wiring.py -v
"""
from __future__ import annotations

from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parent.parent
WORKFLOW = ROOT / ".github" / "workflows" / "daily.yml"


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

def _engine_steps(wf: dict) -> list[dict]:
    """Return the ordered list of steps from the 'engine' job."""
    jobs = wf.get("jobs", {})
    engine_job = jobs.get("engine", {})
    return engine_job.get("steps", [])


def _step_names(steps: list[dict]) -> list[str]:
    return [s.get("name", "") for s in steps]


# ---------------------------------------------------------------------------
# workflow YAML is parseable
# ---------------------------------------------------------------------------

def test_daily_yml_parses():
    assert WORKFLOW.exists(), f"daily.yml not found at {WORKFLOW}"
    with open(WORKFLOW) as fh:
        wf = yaml.safe_load(fh)
    assert isinstance(wf, dict), "daily.yml did not parse to a dict"


# ---------------------------------------------------------------------------
# the contracts step is present and positioned correctly
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def workflow() -> dict:
    with open(WORKFLOW) as fh:
        return yaml.safe_load(fh)


@pytest.fixture(scope="module")
def engine_steps(workflow) -> list[dict]:
    return _engine_steps(workflow)


def test_contracts_step_present(engine_steps):
    names = _step_names(engine_steps)
    matching = [n for n in names if "export cross-repo signal contracts" in n]
    assert matching, (
        "No 'export cross-repo signal contracts' step found in daily.yml engine job. "
        "The step must be added so golden_signals.json + artifact_manifest.json stay fresh."
    )


def test_contracts_step_invokes_script(engine_steps):
    for step in engine_steps:
        if "export cross-repo signal contracts" in step.get("name", ""):
            run_block = step.get("run", "")
            assert "scripts.export_signal_contracts" in run_block, (
                "The contracts step must invoke 'scripts.export_signal_contracts'"
            )
            break


def test_contracts_step_is_resilient(engine_steps):
    """The step must never abort the deploy — it must have a fallback (|| echo)."""
    for step in engine_steps:
        if "export cross-repo signal contracts" in step.get("name", ""):
            run_block = step.get("run", "")
            assert "|| echo" in run_block, (
                "The contracts step must be resilient (include '|| echo ...' fallback) "
                "so a failure never aborts the deploy."
            )
            break


def test_contracts_step_after_track_record(engine_steps):
    names = _step_names(engine_steps)
    # find indices
    tr_idx = next(
        (i for i, n in enumerate(names) if "build signal track-record ledger" in n), None
    )
    contracts_idx = next(
        (i for i, n in enumerate(names) if "export cross-repo signal contracts" in n), None
    )
    assert tr_idx is not None, "build signal track-record ledger step not found"
    assert contracts_idx is not None, "export cross-repo signal contracts step not found"
    assert contracts_idx > tr_idx, (
        f"Contracts step (idx={contracts_idx}) must come AFTER "
        f"build_track_record step (idx={tr_idx})"
    )


def test_contracts_step_before_regime_engine(engine_steps):
    names = _step_names(engine_steps)
    contracts_idx = next(
        (i for i, n in enumerate(names) if "export cross-repo signal contracts" in n), None
    )
    regime_idx = next(
        (i for i, n in enumerate(names) if "run regime engine" in n), None
    )
    assert contracts_idx is not None, "export cross-repo signal contracts step not found"
    assert regime_idx is not None, "run regime engine step not found"
    assert contracts_idx < regime_idx, (
        f"Contracts step (idx={contracts_idx}) must come BEFORE "
        f"regime engine step (idx={regime_idx})"
    )


# ---------------------------------------------------------------------------
# output paths are under site/ (covered by the existing `git add data/ site/` glob)
# ---------------------------------------------------------------------------

def test_output_paths_under_site():
    from scripts.export_signal_contracts import OUT, ROOT as SCRIPT_ROOT  # noqa: PLC0415
    relative = OUT.relative_to(SCRIPT_ROOT)
    assert str(relative).startswith("site"), (
        f"Contract output dir {OUT} must be under site/ to be picked up by "
        f"the 'git add data/ site/ reports/' staging glob in daily.yml"
    )


# ---------------------------------------------------------------------------
# script sanity: non-empty GOLDEN_SYMBOLS + ARTIFACT_MANIFEST
# ---------------------------------------------------------------------------

def test_golden_symbols_non_empty():
    from scripts.export_signal_contracts import GOLDEN_SYMBOLS  # noqa: PLC0415
    assert len(GOLDEN_SYMBOLS) >= 1, "GOLDEN_SYMBOLS must be non-empty"
    for spec in GOLDEN_SYMBOLS:
        assert "symbol" in spec
        assert "path" in spec


def test_artifact_manifest_non_empty():
    from scripts.export_signal_contracts import ARTIFACT_MANIFEST  # noqa: PLC0415
    assert len(ARTIFACT_MANIFEST) >= 1, "ARTIFACT_MANIFEST must be non-empty"
    for entry in ARTIFACT_MANIFEST:
        assert "artifact" in entry
        assert "expected_max_age_td" in entry
