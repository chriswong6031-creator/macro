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

THE SECOND INCIDENT (2026-08-14), and why this file grew a second half.  The
pyyaml heal merged and the lane STILL died, on `No module named 'engine.press'`.
Installing wheels is only half of "can this job import what it runs": under a
SPARSE checkout a LOCAL module is on disk only if it is coned in.  The second
half of this file therefore asks Python rather than parsing YAML — it blocks
every local module the cone would not check out and imports the entry the lane
actually runs, which reproduces the production failure instead of modelling it.
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


# --------------------------------------------------------------------------- #
# The SECOND failure, standing directly behind the first (2026-08-14)
# --------------------------------------------------------------------------- #
# The pyyaml heal landed and the lane STILL died, on
# `ModuleNotFoundError: No module named 'engine.press'`. The audit that shipped
# with that heal had enumerated third-party WHEELS and treated every `engine.*`
# import as local-and-therefore-present. Under a SPARSE checkout that is false: a
# local module is on disk only if it is coned in.
#
# And nothing in the three scripts this lane runs names the missing module.
# `engine/earnings_narrative/{story_packets,admission}.py` import
# `engine.press.earnings_adapter`, and the package `__init__` re-exports
# story_packets — so importing `engine.earnings_narrative.contracts` executes the
# package `__init__` and pulls `engine.press`.
#
# WHY THIS IS EXECUTED, NOT PARSED. The first version of this guard walked the
# import graph with `ast` and flagged four healthy lanes: it counted
# `engine/__init__.py` as missing (cone mode materializes files sitting directly
# in ANY ancestor directory, so it is present) and decided
# earnings-story-press-stage needed `collectors` (it does not — verified by
# import). A guard that cries wolf on healthy lanes gets deleted, and an
# approximation of the import system is not the import system. So this asks
# Python: block every local module whose file the cone would NOT check out, then
# import the entry the lane actually runs. That reproduces the production failure
# exactly instead of modelling it.
_LOCAL_ROOTS = ("engine", "scripts", "lib", "collectors", "app", "tools")


def _covered(rel: str, cone: list[str]) -> bool:
    """Model git CONE mode, which materializes more than the literal patterns.

    `git sparse-checkout set engine/earnings_narrative` writes
    `/*`, `!/*/`, `/engine/`, `!/engine/*/`, `/engine/earnings_narrative/` — i.e.
    every file at the repo root, every file DIRECTLY inside each ancestor
    directory of a coned pattern, and everything under the pattern itself.

    So `engine/__init__.py` is present (direct child of the ancestor `engine/`),
    and a coned FILE like `scripts/refresh_earnings_evidence_graph.py` works for
    the same reason — cone mode has no file patterns, it adds `/scripts/` and the
    script rides in. `engine/press/earnings_adapter.py` is neither: `press` is a
    SIBLING subdirectory, never an ancestor. That asymmetry is the whole bug.
    """
    for pat in cone:
        clean = pat.rstrip("/")
        if rel == clean or rel.startswith(clean + "/"):
            return True
    parent = str(Path(rel).parent)
    if parent == ".":
        return True
    for pat in cone:
        node = Path(pat.rstrip("/"))
        ancestors = {str(a) for a in node.parents if str(a) != "."}
        ancestors.add(str(node))
        if parent in ancestors:
            return True
    return False


_CHILD = '''
import sys, json
from pathlib import Path
from importlib.abc import MetaPathFinder

ROOT = Path.cwd()
CONE = json.loads({cone!r})
LOCAL_ROOTS = {roots!r}

def covered(rel):
    for pat in CONE:
        clean = pat.rstrip("/")
        if rel == clean or rel.startswith(clean + "/"):
            return True
    parent = str(Path(rel).parent)
    if parent == ".":
        return True
    for pat in CONE:
        node = Path(pat.rstrip("/"))
        anc = {{str(a) for a in node.parents if str(a) != "."}}
        anc.add(str(node))
        if parent in anc:
            return True
    return False

def files_for(name):
    parts = name.split(".")
    out = []
    leaf = ROOT.joinpath(*parts[:-1], parts[-1] + ".py")
    pkg = ROOT.joinpath(*parts, "__init__.py")
    for c in (leaf, pkg):
        if c.is_file():
            out.append(str(c.relative_to(ROOT)))
    return out

class ConeBlocker(MetaPathFinder):
    def find_spec(self, name, path=None, target=None):
        if name.split(".")[0] not in LOCAL_ROOTS:
            return None
        files = files_for(name)
        if files and not any(covered(f) for f in files):
            raise ImportError(
                "SPARSE CONE would not check out %s (%s)" % (name, ", ".join(files))
            )
        return None

sys.meta_path.insert(0, ConeBlocker())
import importlib
importlib.import_module({entry!r})
print("CONE_IMPORT_OK")
'''


def _import_under_cone(entry_module: str, cone: list[str]) -> str:
    """Import `entry_module` with every non-coned local module blocked.

    Runs in a subprocess so one lane's imports cannot leak into the next via
    sys.modules and quietly satisfy a cone that would really have failed.
    """
    import json
    import subprocess
    import sys as _sys

    code = _CHILD.format(cone=json.dumps(cone), roots=_LOCAL_ROOTS, entry=entry_module)
    proc = subprocess.run(
        [_sys.executable, "-c", code], cwd=str(_ROOT), capture_output=True, text=True, timeout=180
    )
    return proc.stdout + proc.stderr


def _cone_of(job: dict) -> list[str] | None:
    for step in job.get("steps") or []:
        if not isinstance(step, dict):
            continue
        if str(step.get("uses", "")).startswith("actions/checkout"):
            raw = (step.get("with") or {}).get("sparse-checkout")
            if not isinstance(raw, str):
                return None  # full checkout — everything is present
            return [ln.strip() for ln in raw.splitlines() if ln.strip()]
    return None


def _coned_earnings_jobs() -> list[tuple[str, str, list[str], str]]:
    """(workflow, job id, cone, entry module) for coned jobs running our scripts."""
    reaching = _scripts_that_reach_earnings_narrative()
    out = []
    for path in sorted(_WORKFLOWS.glob("*.yml")):
        try:
            workflow = _yaml.safe_load(path.read_text(encoding="utf-8"))
        except _yaml.YAMLError:
            continue
        if not isinstance(workflow, dict):
            continue
        for job_id, job in (workflow.get("jobs") or {}).items():
            if not isinstance(job, dict):
                continue
            cone = _cone_of(job)
            if cone is None:
                continue
            blob = "\n".join(
                s["run"] for s in job.get("steps") or []
                if isinstance(s, dict) and isinstance(s.get("run"), str)
            )
            for name in dict.fromkeys(_MODULE_RUN.findall(blob)):
                if name in reaching and (_ROOT / f"scripts/{name}.py").is_file():
                    out.append((path.name, job_id, cone, f"scripts.{name}"))
    return out


def test_a_sparse_cone_never_contains_comment_lines() -> None:
    """`sparse-checkout` is a literal pattern list, not a commented scalar.

    A `#` line does not document the cone — it becomes a pattern matching
    nothing, so the reader sees an explanation and git sees junk.
    """
    for name, job_id, cone, _ in _coned_earnings_jobs():
        for pattern in cone:
            assert not pattern.startswith("#"), (
                f"{name} job '{job_id}' has a comment line inside sparse-checkout: "
                f"{pattern!r}. Put the explanation above the step instead."
            )


def test_the_cone_blocker_can_actually_see_the_failure() -> None:
    """Non-vacuity, as a MUTATION of the real bug.

    Drop `engine/press` from the evidence-graph cone and the entry module must
    fail exactly the way production did. Without this, a blocker that silently
    stopped intercepting (the `find_module` -> `find_spec` removal in 3.12 does
    exactly that) would report every cone healthy forever.
    """
    healthy = [
        "engine/earnings_narrative", "engine/earnings_transcript_intake.py", "engine/press",
        "scripts/refresh_earnings_evidence_graph.py",
    ]
    assert "CONE_IMPORT_OK" in _import_under_cone(
        "scripts.refresh_earnings_evidence_graph", healthy
    ), "the real evidence-graph cone should import cleanly"

    mutated = [c for c in healthy if c != "engine/press"]
    out = _import_under_cone("scripts.refresh_earnings_evidence_graph", mutated)
    assert "CONE_IMPORT_OK" not in out, (
        "removing engine/press from the cone no longer breaks the import — the "
        "blocker has gone inert and every cone assertion below is vacuous"
    )
    assert "engine.press" in out, f"expected engine.press to be named; got:\n{out[-800:]}"


@pytest.mark.parametrize("workflow_name,job_id,cone,entry", _coned_earnings_jobs(),
                         ids=lambda v: v if isinstance(v, str) and len(v) < 44 else "")
def test_a_coned_job_can_import_what_it_runs(
    workflow_name: str, job_id: str, cone: list[str], entry: str
) -> None:
    out = _import_under_cone(entry, cone)
    assert "CONE_IMPORT_OK" in out, (
        f"{workflow_name} job '{job_id}' runs `python -m {entry}` but its "
        f"sparse-checkout cone does not check out everything that importing it "
        f"touches, so the job dies before doing any work:\n{out[-900:]}"
    )
