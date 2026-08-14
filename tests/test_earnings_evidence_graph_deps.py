"""Every earnings lane must install the import closure of the scripts it runs.

THE INCIDENT (2026-08-02 -> 2026-08-14).  `earnings-evidence-graph.yml` installed
`boto3 requests` and nothing else, under a step named "install R2 client only".
That name was the whole mistake: the lane's dependency set is not "what talks to
R2", it is "what the first import statement drags in".
`scripts/refresh_earnings_evidence_graph.py` imports
`engine.earnings_narrative.contracts`, which executes the package
`engine/earnings_narrative/__init__.py`, which re-exports `.promotion`, which does
a module-scope `import yaml`.  So the lane died on
`ModuleNotFoundError: No module named 'yaml'` before fetching one transcript body.

It stayed dead for twelve days and nobody was paged, because this is the ONLY
lane that ingests new calls and every lane DOWNSTREAM of it stayed green:
`earnings-story-packets` kept projecting a frozen evidence root, and
`earnings-public-wire` kept rebuilding and committing the same 436 records every
hour.  Three green lanes plus ~24 commits a day is indistinguishable from a
healthy wire.  Cost: 1,631 transcript bodies dated >= 2026-07-30 unprocessed and
/stocks/earnings frozen at call date 2026-07-29.

WHY THIS TEST IS GENERAL AND NOT A ONE-LINE PIN.  A test asserting "pyyaml is in
earnings-evidence-graph.yml" would have caught this exact regression and nothing
else — the next lane added would repeat it.  So the requirement is DERIVED: we
discover which `scripts/*.py` reach `engine.earnings_narrative`, find every
workflow job that invokes one of them, and require that job to install the
yaml dependency.  `test_the_yaml_premise_still_holds` guards the derivation
itself, so if the import chain is ever refactored this file fails loudly and asks
to be re-derived instead of silently going vacuous.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest
import yaml as _yaml  # noqa: F401  (the dependency under discussion must exist here too)

_ROOT = Path(__file__).resolve().parents[1]
_WORKFLOWS = _ROOT / ".github" / "workflows"

# `python -m scripts.foo` / `python3 -m scripts.foo`
_MODULE_RUN = re.compile(r"python3?\s+-m\s+scripts\.([A-Za-z0-9_]+)")


def _scripts_that_reach_earnings_narrative() -> frozenset[str]:
    """Module names under scripts/ whose import lands in engine.earnings_narrative."""
    found = set()
    for path in sorted((_ROOT / "scripts").glob("*.py")):
        if "engine.earnings_narrative" in path.read_text(encoding="utf-8"):
            found.add(path.stem)
    return frozenset(found)


def _job_runs(workflow: dict) -> dict[str, str]:
    """One concatenated `run:` blob per job id, so a job is checked as a unit."""
    blobs: dict[str, str] = {}
    for job_id, job in (workflow.get("jobs") or {}).items():
        if not isinstance(job, dict):
            continue
        parts = []
        for step in job.get("steps") or []:
            if isinstance(step, dict) and isinstance(step.get("run"), str):
                parts.append(step["run"])
        blobs[job_id] = "\n".join(parts)
    return blobs


def _installs_yaml(run_blob: str) -> bool:
    """True when this job's own steps make `import yaml` succeed.

    A `-r <requirements>` install is accepted only when that file really pins it,
    so a requirements indirection cannot be used to wave the check through.
    """
    for line in run_blob.splitlines():
        if "pip install" not in line:
            continue
        if re.search(r"\bpyyaml\b", line, re.IGNORECASE):
            return True
        for req in re.findall(r"-r\s+(\S+)", line):
            candidate = _ROOT / req.strip("\"'")
            if candidate.is_file() and re.search(
                r"^\s*pyyaml\b", candidate.read_text(encoding="utf-8"), re.IGNORECASE | re.MULTILINE
            ):
                return True
    return False


def _earnings_narrative_jobs() -> list[tuple[str, str, str]]:
    """(workflow filename, job id, run blob) for every job importing the package."""
    reaching = _scripts_that_reach_earnings_narrative()
    hits = []
    for path in sorted(_WORKFLOWS.glob("*.yml")):
        try:
            workflow = _yaml.safe_load(path.read_text(encoding="utf-8"))
        except _yaml.YAMLError:  # a malformed workflow is another test's problem
            continue
        if not isinstance(workflow, dict):
            continue
        for job_id, blob in _job_runs(workflow).items():
            if any(name in reaching for name in _MODULE_RUN.findall(blob)):
                hits.append((path.name, job_id, blob))
    return hits


def test_the_yaml_premise_still_holds() -> None:
    """The derivation below is only valid while this import chain exists.

    If someone drops the `.promotion` re-export or moves `import yaml` off module
    scope, the generalized requirement stops being true and this file must be
    re-derived rather than left asserting a rule nobody needs.
    """
    init = (_ROOT / "engine" / "earnings_narrative" / "__init__.py").read_text(encoding="utf-8")
    promotion = (_ROOT / "engine" / "earnings_narrative" / "promotion.py").read_text(encoding="utf-8")
    assert "from .promotion import" in init, (
        "engine.earnings_narrative no longer re-exports .promotion — re-derive the "
        "yaml requirement in tests/test_earnings_evidence_graph_deps.py"
    )
    assert re.search(r"^import yaml$", promotion, re.MULTILINE), (
        "engine/earnings_narrative/promotion.py no longer imports yaml at module "
        "scope — re-derive tests/test_earnings_evidence_graph_deps.py"
    )


def test_scripts_reaching_earnings_narrative_are_discoverable() -> None:
    """Guards the discovery step: an empty set would make every check below pass."""
    reaching = _scripts_that_reach_earnings_narrative()
    assert "refresh_earnings_evidence_graph" in reaching
    assert "build_earnings_public_wire" in reaching
    assert len(reaching) >= 5


def test_at_least_the_known_earnings_lanes_are_matched() -> None:
    """Guards the matching step: zero matched jobs would also pass vacuously."""
    matched = {name for name, _, _ in _earnings_narrative_jobs()}
    for expected in (
        "earnings-evidence-graph.yml",
        "earnings-public-wire.yml",
        "earnings-story-packets.yml",
    ):
        assert expected in matched, f"{expected} no longer matched by the dependency scan"


@pytest.mark.parametrize("workflow_name,job_id,run_blob", _earnings_narrative_jobs(),
                         ids=lambda v: v if isinstance(v, str) and len(v) < 40 else "")
def test_every_earnings_narrative_job_installs_yaml(workflow_name: str, job_id: str, run_blob: str) -> None:
    assert _installs_yaml(run_blob), (
        f"{workflow_name} job '{job_id}' runs a script that imports "
        f"engine.earnings_narrative but never installs pyyaml. That job will die on "
        f"ModuleNotFoundError: No module named 'yaml' before doing any work — the "
        f"2026-08-02 earnings-evidence-graph outage, repeated."
    )
