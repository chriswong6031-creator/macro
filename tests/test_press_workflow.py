"""tests/test_press_workflow.py — .github/workflows/press-publish.yml shape.

A publishing workflow is the one file in this lane nobody can test by running
it: it fires at 13:20 UTC on a runner, and its failure mode is publishing
something, which is not reversible by re-running.  So its safety properties are
asserted statically, here.

What is pinned:
  * DARK BY DEFAULT — every job gated on PRESS_PUBLISH_ENABLED == 'true', and
    the variable is created nowhere in the repo.
  * OFF the render path (never the macstudio pool).
  * EXPLICIT git-add scoping, and site/sitemap.xml never staged.
  * GitHub annotations start their line (house law).
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

import pytest

_REPO = Path(__file__).resolve().parent.parent
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

_WF = _REPO / ".github" / "workflows" / "press-publish.yml"
_CI = _REPO / ".github" / "workflows" / "ci.yml"
_LEGACY = _REPO / ".github" / "ci" / "legacy-jobs.yml"


def _load(path: Path) -> dict:
    yaml = pytest.importorskip("yaml")
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def _text() -> str:
    return _WF.read_text(encoding="utf-8")


def _code_lines(path: Path = _WF) -> list[str]:
    """Non-comment lines — so documentation about a hazard is not read as one."""
    return [l for l in path.read_text(encoding="utf-8").splitlines()
            if not l.lstrip().startswith("#")]


def _triggers(wf: dict) -> dict:
    """The `on:` block.

    PyYAML follows YAML 1.1 and coerces a bare `on` key to the boolean True, so
    `wf["on"]` is a KeyError on every workflow in this repo.  scripts/
    check_workflow_yaml.py accepts both spellings for the same reason.
    """
    return wf.get("on") if "on" in wf else wf[True]


def _jobs() -> dict:
    return _load(_WF)["jobs"]


# ─────────────────────────────────────────────────────────────────────────────
# dark by default
# ─────────────────────────────────────────────────────────────────────────────


def test_workflow_exists_and_parses():
    assert _WF.exists()
    wf = _load(_WF)
    assert wf["name"] == "press-publish"
    assert wf["jobs"]


def test_every_job_is_gated_on_the_kill_switch():
    for name, job in _jobs().items():
        cond = str(job.get("if") or "")
        assert "vars.PRESS_PUBLISH_ENABLED == 'true'" in cond, \
            f"job {name} is not gated on the kill switch"


def test_the_kill_switch_has_no_secrets_fallback():
    """A lingering secret of the same name must not keep the lane live after the
    toggle goes off (the marketing lane's documented failure mode)."""
    assert "secrets.PRESS_PUBLISH_ENABLED" not in _text()


def test_the_kill_switch_variable_is_created_nowhere_in_the_repo():
    """W1 ships dark: this change must not arm anything."""
    hits = []
    for path in _REPO.rglob("*.yml"):
        if ".claude" in path.parts or "worktrees" in path.parts:
            continue
        try:
            body = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        for line in body.splitlines():
            if "PRESS_PUBLISH_ENABLED" in line and re.search(
                    r"PRESS_PUBLISH_ENABLED\s*[:=]\s*['\"]?(true|1|yes)", line):
                hits.append(f"{path.relative_to(_REPO)}: {line.strip()}")
    assert not hits, f"the kill switch is armed somewhere: {hits}"


def test_emit_needs_an_explicit_human_dispatch():
    """A scheduled run stages and stops. The first weeks of this lane are meant
    to be READ before they are shipped."""
    cond = str(_jobs()["emit"]["if"])
    assert "github.event_name == 'workflow_dispatch'" in cond
    assert "inputs.emit" in cond
    assert "needs.stage.outputs.passed != '0'" in cond


def test_dispatch_emit_input_defaults_to_false():
    inputs = _triggers(_load(_WF))["workflow_dispatch"]["inputs"]
    assert inputs["emit"]["default"] is False
    assert inputs["emit"]["type"] == "boolean"


# ─────────────────────────────────────────────────────────────────────────────
# off the render path
# ─────────────────────────────────────────────────────────────────────────────


def test_no_job_runs_on_the_render_pool():
    """The nightly render budget (~67 min, 4-core-bound) is law; a publishing
    lane must never contend for it."""
    for name, job in _jobs().items():
        assert job["runs-on"] == "ubuntu-latest", name
    # Belt and braces: no `runs-on:` line anywhere in the file names the pool,
    # so a job added later cannot slip onto it. Scanning the whole file would
    # trip on the header comment that explains WHY the pool is off-limits.
    runs_on_lines = [l.split("#", 1)[0] for l in _code_lines()
                     if l.strip().startswith("runs-on:")]
    assert runs_on_lines
    for line in runs_on_lines:
        assert "macstudio" not in line and "self-hosted" not in line, line


def test_every_job_carries_a_timeout():
    for name, job in _jobs().items():
        assert isinstance(job.get("timeout-minutes"), int), name


def test_runs_are_serialised():
    wf = _load(_WF)
    assert wf["concurrency"]["group"] == "press-publish"
    assert wf["concurrency"]["cancel-in-progress"] is False


def test_the_schedule_avoids_the_nightly_window():
    crons = [s["cron"] for s in _triggers(_load(_WF))["schedule"]]
    assert crons
    for cron in crons:
        hour = int(cron.split()[1])
        assert not (21 <= hour <= 23), f"{cron} lands in the ~22:30 UTC nightly window"


# ─────────────────────────────────────────────────────────────────────────────
# commit scoping
# ─────────────────────────────────────────────────────────────────────────────


def _commit_step() -> str:
    for step in _jobs()["emit"]["steps"]:
        if "git add" in str(step.get("run") or ""):
            return str(step["run"])
    pytest.fail("no commit step found")
    return ""


def test_git_add_names_exactly_the_three_owned_paths():
    added = set(re.findall(r"^\s*git add ([^\s]+)", _commit_step(), re.MULTILINE))
    assert added == {"content/seo/blog", "site/blog", "data/press/published.jsonl"}


def test_the_commit_step_refuses_to_stage_the_sitemap():
    """The nightly owns site/sitemap.xml. Belt (never `git add` it) and braces
    (fail the step if it somehow got staged)."""
    step = _commit_step()
    assert "git add site/sitemap.xml" not in step
    assert "grep -q '^site/sitemap.xml$'" in step
    assert "press_sitemap_guard" in step


def test_no_step_writes_the_regwall_or_the_caddyfile():
    body = _text()
    for forbidden in ("regwall", "Caddyfile", "sitemap.xml\"", "git add site "):
        assert forbidden not in body or forbidden == "sitemap.xml\""


def test_the_commit_step_does_not_run_on_a_failed_emit():
    """THE DEFECT THIS CLOSES: the commit step carried `if: always()`, so a
    failed emit or a red drift check still committed whatever had landed on
    disk — a half-published estate on main for the next PR to inherit."""
    step = next(s for s in _jobs()["emit"]["steps"]
                if "git add" in str(s.get("run") or ""))
    assert "if" not in step, "commit must run only when every prior step passed"
    assert "always()" not in str(step)


def test_the_staging_step_fails_loudly_instead_of_reading_green():
    """`set -uo pipefail` without -e let a Python traceback sail past and the
    PASSED fallback reported a CRASHED run as a thin day."""
    step = next(s for s in _jobs()["stage"]["steps"]
                if "run_press" in str(s.get("run") or ""))
    run = str(step["run"])
    assert "set -euo pipefail" in run
    assert "press_staging_crashed" in run
    assert "if [ ! -f data/press/staging/_run_summary.json ]" in run


def test_the_evidence_gate_protocol_forbids_as_of_back_walking():
    """A back-dated run can only see today's snapshots, so its fact pool is one
    that will never exist again — evidence about nothing."""
    body = _text()
    assert "DO NOT collect the gate by back-walking" in body
    assert "REAL CONSECUTIVE STAGED RUNS AT CURRENT DATES" in body
    inputs = _triggers(_load(_WF))["workflow_dispatch"]["inputs"]
    assert "DEV ONLY" in inputs["as_of"]["description"]


def test_the_emit_job_reruns_the_estate_drift_check():
    """If the sweep replay ever stops matching, it goes red HERE, in the lane
    that caused it, not on somebody else's PR."""
    runs = " ".join(str(s.get("run") or "") for s in _jobs()["emit"]["steps"])
    assert "scripts.build_free_content --check" in runs


# ─────────────────────────────────────────────────────────────────────────────
# annotations (house law) + spend guards
# ─────────────────────────────────────────────────────────────────────────────


def test_every_annotation_starts_its_line():
    """`echo "x ::warning::y"` is not an annotation — GitHub only parses a line
    that STARTS with the marker."""
    offenders = []
    for line in _text().splitlines():
        stripped = line.strip()
        if "::warning" in stripped or "::error" in stripped or "::notice" in stripped:
            if stripped.startswith("#"):
                continue                       # documentation, not emission
            m = re.search(r'echo\s+"([^"]*)"', stripped)
            if m and not m.group(1).startswith("::"):
                offenders.append(stripped)
    assert not offenders, offenders


def test_the_spend_guards_are_reachable_from_the_workflow():
    env = _jobs()["stage"]["env"]
    assert "PRESS_RUN_TOKEN_BUDGET" in env
    assert "PRESS_CIRCUIT_BREAKER_FAILURES" in env


def test_the_credential_waterfall_is_wired():
    env = _jobs()["stage"]["env"]
    for key in ("CLAUDE_CODE_OAUTH_TOKEN", "ANTHROPIC_API_KEY", "DEEPSEEK_API_KEY"):
        assert key in env, key


def test_staging_evidence_is_uploaded_even_on_a_thin_run():
    step = next(s for s in _jobs()["stage"]["steps"]
                if "upload-artifact" in str(s.get("uses") or ""))
    assert step["if"] == "always()"
    assert step["with"]["path"].startswith("data/press/staging")


# ─────────────────────────────────────────────────────────────────────────────
# CI wiring — a guard the guarded change cannot trigger is not a guard
# ─────────────────────────────────────────────────────────────────────────────


def test_press_paths_reach_ci():
    paths = _triggers(_load(_CI))["pull_request"]["paths"]
    for needed in ("engine/press/**", "scripts/run_press.py", "config/press.yml",
                   "admin/press.py", "tests/test_press_*.py",
                   ".github/workflows/press-publish.yml"):
        assert needed in paths, f"{needed} cannot trigger ci.yml"


def test_the_estate_check_still_triggers_on_content_changes():
    """--emit writes content/seo/blog and site/blog; the estate drift law has to
    see that."""
    paths = _triggers(_load(_CI))["pull_request"]["paths"]
    assert "content/seo/**" in paths
    assert "scripts/build_free_content.py" in paths


def test_press_lane_job_exists_and_obeys_the_pack_manifest_rules():
    job = _load(_LEGACY)["jobs"]["press-lane"]
    assert job["if"] == "${{ false }}"
    assert job["runs-on"] == "ubuntu-latest"
    assert set(job) <= {"if", "runs-on", "steps", "timeout-minutes"}
    for step in job["steps"]:
        assert set(step) <= {"name", "run", "uses", "with"}
    installs = [s for s in job["steps"] if "pip install" in str(s.get("run") or "")]
    assert len(installs) == 1, "run_ci_pack.py allows at most one pip-install step"


def test_press_lane_follows_the_estate_jobs_minimal_deps_convention():
    """Same three packages, spelled the same way.

    NOT a venv-sharing claim: run_ci_pack.py shares an environment only between
    ADJACENT jobs in the same pack, and these two currently land in different
    packs. The convention is worth holding anyway — one spelling for one
    closure keeps the manifest readable and keeps the door open to sharing."""
    jobs = _load(_LEGACY)["jobs"]

    def _install(name):
        return next(str(s["run"]).strip() for s in jobs[name]["steps"]
                    if "pip install" in str(s.get("run") or ""))

    assert _install("press-lane") == _install("free-content-estate")


def test_every_press_suite_is_named_by_the_ci_job():
    job = _load(_LEGACY)["jobs"]["press-lane"]
    named = set(re.findall(r"tests/test_press_\w+\.py",
                           " ".join(str(s.get("run") or "") for s in job["steps"])))
    on_disk = {f"tests/{p.name}" for p in (_REPO / "tests").glob("test_press_*.py")}
    assert named == on_disk, f"unrun press suites: {sorted(on_disk - named)}"
