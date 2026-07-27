#!/usr/bin/env python3
"""Guard: a test that SKIPS in every job that names it executes nowhere.

The third darkness class.  ``scripts/audit_unrun_tests.py`` measures the two that
bracket it:

    UNRUN          no `run:` step in any workflow names the suite's filename.
    UNTRIGGERABLE  nothing that changes the suite's verdict is matched by
                   ci.yml's `on.pull_request.paths`, so the gate cannot start.

Both ask *"is this suite named by a job"*.  Neither asks *"does the job that names
it install what it needs to run"* — so a suite can be named, triggerable, and green
while every one of its tests is a **skip**.  That is a SKIP-ONLY suite, and it is
what an `importorskip` added to clear a red CI lane creates **by construction**:
main goes green and weaker in the same commit, and nothing notices.

It has happened twice.  #3703 was the first; #3760 found the second — the two
`load_ohlcv` crypto tests from #3722 were `importorskip("pandas")`-gated by #3738 to
clear a red, and `chart-render` (`pip install pytest pyyaml`) was the ONLY job in
any workflow that named `tests/test_chart_render_inline.py`.  Six tests executed in
zero jobs.  Every census in the repo said the file was covered.

WHAT THIS CHECKS (static — no test execution)

  1. For each `tests/test_*.py`, collect its skip gates:
       * `pytest.importorskip("X")`, anywhere in the file;
       * `pytest.mark.skipif(<cond>)` / `pytestmark = ...` whose condition reads a
         module-level flag bound by a `try: import X / except ImportError: flag =
         False` probe or by `importlib.util.find_spec("X")`.
     Gates on things pip cannot install — a data artifact (`_PANEL.exists()`), a
     binary (`shutil.which("node")`) — are deliberately NOT skip gates here.
  2. For each job in `.github/workflows/*.yml` plus `.github/ci/legacy-jobs.yml`,
     collect the test files its `run:` steps name and the modules its single
     `pip install` line provides.  ci.yml's `on.pull_request.paths` list names
     hundreds of test files and is NOT a `run:` step; only `run:` counts.
  3. A gated module `X` is SATISFIED when at least one job that names the suite
     provides `X`.  A first-party gate (`engine.indicators_m2`) is satisfied when
     a job provides that module's own third-party import closure — the file is
     always in the checkout, so what the gate really tests is numpy/pandas/….

  FAIL when a gate is satisfied by NO job that names its suite.

Suites that no job names at all are UNRUN, not skip-only: they are reported under
`--report` and never fail here, because `audit_unrun_tests.py` already owns that
class and wiring them all would blow the ci-pack budget.

Usage:
    python3 scripts/check_skip_only_suites.py            # gate (exit 1 on findings)
    python3 scripts/check_skip_only_suites.py --report   # full census, exit 0
    python3 scripts/check_skip_only_suites.py --selftest # guard's own round-trip
"""
from __future__ import annotations

import argparse
import ast
import json
import re
import sys
from pathlib import Path
from typing import Any, Iterable

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

# Reuse, do not re-implement: the census owns test discovery and the repo layout
# constants; run_ci_pack owns the legacy manifest's fail-closed per-job parse and
# the definition of a job's dependency command (its venv-reuse key).
from scripts.audit_unrun_tests import (  # noqa: E402
    CI_MANIFEST,
    FIRST_PARTY,
    ROOT,
    TESTS,
    WORKFLOWS,
)
from scripts.run_ci_pack import (  # noqa: E402
    ManifestError,
    dependency_command,
    load_legacy_jobs,
)

REQUIREMENTS = ROOT / "requirements.txt"

# Distributions whose import name differs from the name pip is given.
PACKAGE_MODULES: dict[str, tuple[str, ...]] = {
    "pyyaml": ("yaml",),
    "pillow": ("PIL",),
    "beautifulsoup4": ("bs4",),
    "scikit-learn": ("sklearn",),
    "python-dateutil": ("dateutil",),
    "pytest-mock": ("pytest_mock",),
    "google-auth": ("google.auth", "google.oauth2"),
    "attrs": ("attr", "attrs"),
}

# Hard runtime dependencies only — a package listed here is genuinely unusable
# without its entries, so a job installing the key really does provide them.
# Under-declaring costs a false RED, so keep this to certainties; over-declaring
# costs a missed skip-only suite, so never add a soft/extra dependency.
PACKAGE_REQUIRES: dict[str, tuple[str, ...]] = {
    "pandas": ("numpy", "python-dateutil", "pytz", "tzdata"),
    "scipy": ("numpy",),
    "scikit-learn": ("numpy", "scipy", "joblib", "threadpoolctl"),
    "hmmlearn": ("numpy", "scipy", "scikit-learn"),
    "jinja2": ("markupsafe",),
    "requests": ("urllib3", "certifi", "idna", "charset_normalizer"),
    "beautifulsoup4": ("soupsieve",),
    "openpyxl": ("et_xmlfile",),
    "reportlab": ("pillow",),
    "boto3": ("botocore", "jmespath", "s3transfer"),
    "fastapi": ("starlette", "pydantic", "typing_extensions"),
    "httpx": ("httpcore", "certifi", "idna", "anyio", "h11", "sniffio"),
    "anthropic": ("httpx", "pydantic", "anyio", "distro", "jiter", "sniffio"),
    "jsonschema": ("attrs", "referencing", "rpds-py"),
    "pytest": ("pluggy", "iniconfig", "packaging"),
    "pytest-mock": ("pytest",),
    "yfinance": ("pandas", "numpy", "requests", "beautifulsoup4", "pytz",
                 "platformdirs", "multitasking", "frozendict", "peewee"),
    "akshare": ("pandas", "requests", "beautifulsoup4", "lxml", "openpyxl",
                "tqdm", "tabulate", "xlrd"),
    "google-auth": ("cachetools", "pyasn1-modules", "rsa"),
    "plotly": ("packaging",),
}

# Available in every job without an install line.
STDLIB_ALWAYS = frozenset(sys.stdlib_module_names) | {"__future__"}

_PIP_INSTALL = re.compile(r"^\s*(?:(?:python|python3)\s+-m\s+)?pip\s+install\s+(.+)$", re.M)
_TEST_TOKEN = re.compile(r"(?<![\w/.-])(?:tests/)?(test_[\w]+\.py)(?![\w])")
_PIP_FLAG = re.compile(r"^-")
_REQ_NAME = re.compile(r"^([A-Za-z0-9._-]+)")


def _normalize(package: str) -> str:
    return package.strip().strip("\"'").lower().replace("_", "-")


# ─────────────────────────────────────────────────────────────────────────────
# 1. skip gates
# ─────────────────────────────────────────────────────────────────────────────

def _handler_catches_import(handler: ast.ExceptHandler) -> bool:
    """A bare `except:`/`except Exception:`/`except ImportError:` shields imports."""
    node = handler.type
    if node is None:
        return True
    names = node.elts if isinstance(node, ast.Tuple) else [node]
    for name in names:
        label = name.id if isinstance(name, ast.Name) else getattr(name, "attr", "")
        if label in {"ImportError", "ModuleNotFoundError", "Exception", "BaseException"}:
            return True
    return False


def _import_probes(tree: ast.Module) -> dict[str, set[str]]:
    """Module-level names whose value records whether an import succeeded.

    Two shapes, both live in this repo:

        try:                                    _HAS_RSP = (
            import scripts.replay_pipeline          importlib.util.find_spec("x") is not None
            _HAS_RSP = True                     )
        except Exception:
            _HAS_RSP = False
    """
    probes: dict[str, set[str]] = {}
    for node in tree.body:
        if isinstance(node, ast.Try) and any(
            _handler_catches_import(h) for h in node.handlers
        ):
            imported: set[str] = set()
            for inner in ast.walk(node):
                if isinstance(inner, ast.Import):
                    imported |= {a.name for a in inner.names}
                elif isinstance(inner, ast.ImportFrom) and inner.module and not inner.level:
                    imported.add(inner.module)
            if not imported:
                continue
            for inner in ast.walk(node):
                if isinstance(inner, ast.Assign):
                    for target in inner.targets:
                        if isinstance(target, ast.Name):
                            probes.setdefault(target.id, set()).update(imported)
        elif isinstance(node, ast.Assign):
            found = {
                call.args[0].value
                for call in ast.walk(node)
                if isinstance(call, ast.Call)
                and isinstance(call.func, ast.Attribute)
                and call.func.attr == "find_spec"
                and call.args
                and isinstance(call.args[0], ast.Constant)
                and isinstance(call.args[0].value, str)
            }
            if found:
                for target in node.targets:
                    if isinstance(target, ast.Name):
                        probes.setdefault(target.id, set()).update(found)
    return probes


def _skipif_conditions(tree: ast.Module) -> list[tuple[str, ast.expr]]:
    """Every condition that can turn a test in this file into a skip.

    Two spellings, both used here: the decorator/`pytestmark` form, and the
    in-body `if not _HAS_RSP: pytest.skip(...)` form (tests/test_staleness_replay.py
    uses the latter eight times).  Skipping in the body is the same darkness as
    skipping at collection, so it is the same gate.
    """
    out: list[tuple[str, ast.expr]] = []
    for node in ast.walk(tree):
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr == "skipif"
            and node.args
        ):
            out.append(("skipif", node.args[0]))
        elif isinstance(node, ast.If) and any(
            isinstance(inner, ast.Call)
            and isinstance(inner.func, ast.Attribute)
            and inner.func.attr == "skip"
            for stmt in node.body
            for inner in ast.walk(stmt)
        ):
            out.append(("skip", node.test))
    return out


def skip_gates(path: Path) -> dict[str, list[str]]:
    """Modules whose absence makes tests in ``path`` skip → why, for the report."""
    try:
        tree = ast.parse(path.read_text(errors="ignore"))
    except SyntaxError:
        return {}
    gates: dict[str, list[str]] = {}

    for node in ast.walk(tree):
        if not isinstance(node, ast.Call) or not node.args:
            continue
        func = node.func
        label = func.attr if isinstance(func, ast.Attribute) else getattr(func, "id", "")
        # `pytest_importorskip_soft` (tests/test_chart_render_m2.py) wraps the real
        # call; matching on the substring keeps such helpers in scope.
        if "importorskip" not in label:
            continue
        arg = node.args[0]
        if isinstance(arg, ast.Constant) and isinstance(arg.value, str):
            gates.setdefault(arg.value, []).append(f"importorskip line {node.lineno}")

    probes = _import_probes(tree)
    if probes:
        for kind, cond in _skipif_conditions(tree):
            names = {n.id for n in ast.walk(cond) if isinstance(n, ast.Name)}
            for name in sorted(names & probes.keys()):
                for module in sorted(probes[name]):
                    gates.setdefault(module, []).append(
                        f"{kind} on {name} line {cond.lineno}"
                    )
    return gates


# ─────────────────────────────────────────────────────────────────────────────
# 2. what a first-party gate really needs
# ─────────────────────────────────────────────────────────────────────────────

def _module_level_imports(tree: ast.Module) -> set[str]:
    """Imports that run at import time and are not shielded by a try/except.

    Function bodies are excluded: a lazy import inside a function cannot make the
    module fail to import, which is the whole point of the thin-lane contract.
    """
    found: set[str] = set()

    def walk(nodes: Iterable[ast.stmt], guarded: bool) -> None:
        for node in nodes:
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            if isinstance(node, ast.Try):
                shielded = guarded or any(
                    _handler_catches_import(h) for h in node.handlers
                )
                walk(node.body, shielded)
                for handler in node.handlers:
                    walk(handler.body, shielded)
                walk(node.orelse, shielded)
                walk(node.finalbody, guarded)
                continue
            if isinstance(node, ast.Import):
                if not guarded:
                    found.update(a.name for a in node.names)
                continue
            if isinstance(node, ast.ImportFrom):
                if not guarded and node.module and not node.level:
                    found.add(node.module)
                continue
            for field in ("body", "orelse", "finalbody"):
                walk(getattr(node, field, []) or [], guarded)

    walk(tree.body, False)
    return found


def _module_file(module: str) -> Path | None:
    base = module.replace(".", "/")
    for candidate in (f"{base}.py", f"{base}/__init__.py"):
        path = ROOT / candidate
        if path.is_file():
            return path
    return None


def required_modules(module: str, _seen: set[str] | None = None) -> set[str]:
    """Third-party top-level modules ``module`` needs before it will import.

    A third-party gate resolves to itself.  A first-party gate resolves to the
    third-party closure of its own module-level imports — `engine.indicators_m2`
    is always in the checkout, so what `importorskip` is really testing there is
    numpy, exactly as PR #3760 worked out by hand.
    """
    root = module.split(".")[0]
    if root in STDLIB_ALWAYS:
        return set()          # `try: import jinja2, os` attributes `os` too; ignore it
    if root not in FIRST_PARTY:
        return {root}
    seen = _seen if _seen is not None else set()
    if module in seen:
        return set()
    seen.add(module)
    path = _module_file(module)
    if path is None:
        return set()
    try:
        tree = ast.parse(path.read_text(errors="ignore"))
    except SyntaxError:
        return set()
    needed: set[str] = set()
    for imported in _module_level_imports(tree):
        if imported.split(".")[0] in FIRST_PARTY:
            needed |= required_modules(imported, seen)
        else:
            needed.add(imported.split(".")[0])
    return {m for m in needed if m not in STDLIB_ALWAYS}


# ─────────────────────────────────────────────────────────────────────────────
# 3. jobs
# ─────────────────────────────────────────────────────────────────────────────

def _requirements_packages() -> set[str]:
    if not REQUIREMENTS.is_file():
        return set()
    out = set()
    for raw in REQUIREMENTS.read_text().splitlines():
        line = raw.split("#", 1)[0].strip()
        match = _REQ_NAME.match(line)
        if match:
            out.add(_normalize(match.group(1)))
    return out


def install_packages(command: str | None) -> set[str] | None:
    """Distributions a job's pip line installs, closed over hard dependencies.

    ``None`` means the job installs nothing, so only the standard library is
    available.  ``-r requirements.txt`` expands to the pinned dependency set.
    """
    if not command:
        return None
    direct: set[str] = set()
    for match in _PIP_INSTALL.finditer(command):
        tokens = match.group(1).replace("\\\n", " ").split()
        skip_next = False
        for token in tokens:
            if skip_next:
                skip_next = False
                if token.endswith("requirements.txt"):
                    direct |= _requirements_packages()
                continue
            if token in {"-r", "--requirement", "-c", "--constraint"}:
                skip_next = True
                continue
            if _PIP_FLAG.match(token):
                continue
            name = _REQ_NAME.match(_normalize(token))
            if name:
                direct.add(name.group(1))
    if not direct:
        return None
    closure = set(direct)
    frontier = list(direct)
    while frontier:
        package = frontier.pop()
        for dependency in PACKAGE_REQUIRES.get(package, ()):
            normalized = _normalize(dependency)
            if normalized not in closure:
                closure.add(normalized)
                frontier.append(normalized)
    return closure


def provided_modules(packages: set[str] | None) -> set[str]:
    modules = set(STDLIB_ALWAYS)
    for package in packages or ():
        modules.update(PACKAGE_MODULES.get(package, (package.replace("-", "_"),)))
    return modules


def _steps_of(definition: Any) -> list[dict]:
    steps = definition.get("steps") if isinstance(definition, dict) else None
    return [s for s in steps or [] if isinstance(s, dict)]


def _job_view(job_id: str, source: str, run_text: str, install: str | None) -> dict:
    packages = install_packages(install)
    return {
        # Job ids repeat across files on purpose — ci-main-heartbeat.yml mirrors a
        # curated subset of the legacy jobs — so the label carries the file too.
        "job": f"{source}::{job_id}",
        "source": source,
        "tests": {m.group(1) for m in _TEST_TOKEN.finditer(run_text)},
        "install": install,
        "packages": packages,
        "modules": provided_modules(packages),
    }


def workflow_jobs() -> list[dict]:
    """Every CI job, with the test files its `run:` steps name and its install line.

    The legacy manifest goes through ``run_ci_pack.load_legacy_jobs`` so this guard
    reads jobs through the same fail-closed validator that executes them, and takes
    the install line from ``dependency_command`` — the exact string whose byte
    identity decides venv reuse.
    """
    jobs: list[dict] = []
    for path in sorted(WORKFLOWS.glob("*.yml")):
        try:
            payload = yaml.safe_load(path.read_text(errors="ignore"))
        except yaml.YAMLError:
            continue
        if not isinstance(payload, dict) or not isinstance(payload.get("jobs"), dict):
            continue
        for job_id, definition in payload["jobs"].items():
            runs = [str(s["run"]) for s in _steps_of(definition) if "run" in s]
            installs = [r for r in runs if _PIP_INSTALL.search(r)]
            jobs.append(
                _job_view(
                    str(job_id),
                    path.name,
                    "\n".join(runs),
                    "\n".join(installs) or None,
                )
            )
    if CI_MANIFEST.exists():
        for legacy in load_legacy_jobs(CI_MANIFEST):
            runs = [
                str(step["run"])
                for step in legacy.definition["steps"]
                if "run" in step
            ]
            jobs.append(
                _job_view(
                    legacy.job_id,
                    CI_MANIFEST.name,
                    "\n".join(runs),
                    dependency_command(legacy),
                )
            )
    return jobs


# ─────────────────────────────────────────────────────────────────────────────
# 4. verdict
# ─────────────────────────────────────────────────────────────────────────────

def census(jobs: list[dict] | None = None) -> list[dict]:
    jobs = workflow_jobs() if jobs is None else jobs
    rows: list[dict] = []
    for path in sorted(TESTS.glob("test_*.py")):
        gates = skip_gates(path)
        if not gates:
            continue
        naming = [j for j in jobs if path.name in j["tests"]]
        for gate, why in sorted(gates.items()):
            needs = sorted(required_modules(gate))
            if not needs:
                continue  # first-party and pure-stdlib: nothing to install
            satisfied = sorted(
                j["job"] for j in naming if all(n in j["modules"] for n in needs)
            )
            rows.append(
                dict(
                    test=path.name,
                    gate=gate,
                    needs=needs,
                    why=why,
                    naming_jobs=[j["job"] for j in naming],
                    satisfying_jobs=satisfied,
                    status=(
                        "UNRUN" if not naming
                        else "OK" if satisfied
                        else "SKIP-ONLY"
                    ),
                )
            )
    return rows


def _print_row(row: dict) -> None:
    needs = ", ".join(row["needs"])
    detail = f" (needs {needs})" if needs != row["gate"] else ""
    print(f"  {row['test']}  gate={row['gate']}{detail}")
    print(f"      {row['why'][0]}" + (f"  (+{len(row['why']) - 1} more)"
                                      if len(row["why"]) > 1 else ""))
    if row["naming_jobs"]:
        print(f"      named by: {', '.join(sorted(row['naming_jobs']))}")
        print("      installed by: (no job)")
    else:
        print("      named by: (no job — UNRUN, see audit_unrun_tests.py)")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--report", action="store_true",
                        help="print the full census and exit 0")
    parser.add_argument("--json", type=Path, help="write all rows as JSON")
    parser.add_argument("--selftest", action="store_true",
                        help="round-trip the detector against seeded fixtures")
    args = parser.parse_args(argv)

    if args.selftest:
        return _selftest()

    try:
        rows = census()
    except ManifestError as exc:
        print(f"::error title=skip-only-suites::cannot read the CI manifest: {exc}",
              flush=True)
        return 2

    if args.json:
        args.json.write_text(json.dumps(rows, indent=1))

    bad = [r for r in rows if r["status"] == "SKIP-ONLY"]
    unrun = [r for r in rows if r["status"] == "UNRUN"]
    ok = [r for r in rows if r["status"] == "OK"]

    print(f"skip gates examined       : {len(rows)}")
    print(f"  satisfied by some job   : {len(ok)}")
    print(f"  suite named by no job   : {len(unrun)}  (UNRUN — not this gate's class)")
    print(f"  SKIP-ONLY               : {len(bad)}")

    if args.report:
        for label, group in (("SKIP-ONLY", bad), ("UNRUN", unrun), ("OK", ok)):
            print(f"\n=== {label} ({len(group)}) ===")
            for row in group:
                if label == "OK":
                    print(f"  {row['test']}  gate={row['gate']}  "
                          f"→ {', '.join(row['satisfying_jobs'][:3])}")
                else:
                    _print_row(row)
        return 0

    if not bad:
        print("\nOK — every skip gate is satisfied by a job that names its suite.")
        return 0

    print()
    for row in bad:
        print(
            f"::error title=skip-only-suite::{row['test']} skips its "
            f"{row['gate']} tests in every job that names it "
            f"({', '.join(sorted(row['naming_jobs']))}) — none installs "
            f"{', '.join(row['needs'])}",
            flush=True,
        )
    print(f"\n{len(bad)} skip-only gate(s). Each one is a test that executes in NO job.")
    print("Fix by adding the suite to a job whose pip line already provides the")
    print("module (byte-identical install lines share one venv, so that is free),")
    print("or by pairing the thin lane with a fat one — see PR #3760.")
    return 1


# ─────────────────────────────────────────────────────────────────────────────
# selftest — a guard that stops detecting is worse than no guard
# ─────────────────────────────────────────────────────────────────────────────

_FIXTURE_SUITE = '''
import pytest

try:
    import demo_probe
    _HAVE = True
except ImportError:
    _HAVE = False


def test_direct():
    pytest.importorskip("demo_direct")


@pytest.mark.skipif(not _HAVE, reason="demo_probe absent")
def test_flagged():
    pass
'''


def _selftest() -> int:
    import tempfile

    failures: list[str] = []
    with tempfile.TemporaryDirectory() as tmp:
        suite = Path(tmp) / "test_demo_fixture.py"
        suite.write_text(_FIXTURE_SUITE)
        gates = skip_gates(suite)
        if set(gates) != {"demo_direct", "demo_probe"}:
            failures.append(f"skip_gates found {sorted(gates)}, want both forms")

    thin = _job_view("thin", "fixture", "pytest tests/test_demo.py",
                     "pip install pytest pyyaml")
    fat = _job_view("fat", "fixture", "pytest tests/test_demo.py",
                    "pip install pytest pandas pyyaml")
    if "yaml" not in thin["modules"]:
        failures.append("pyyaml must provide the `yaml` module")
    if "numpy" not in fat["modules"]:
        failures.append("pandas must close over numpy")
    if "numpy" in thin["modules"]:
        failures.append("thin lane must NOT provide numpy")
    if thin["tests"] != {"test_demo.py"}:
        failures.append(f"run-step test parse got {thin['tests']}")

    paths_only = _job_view("paths", "fixture", "echo nothing", None)
    if paths_only["tests"]:
        failures.append("a job with no test in its run steps must name none")

    # Seeded defect: the thin lane alone must read as SKIP-ONLY, the pair as OK.
    with tempfile.TemporaryDirectory() as tmp:
        suite = Path(tmp) / "test_seeded.py"
        suite.write_text('import pytest\n\n\ndef t():\n    pytest.importorskip("pandas")\n')
        gate_rows = skip_gates(suite)
        if "pandas" not in gate_rows:
            failures.append("seeded importorskip('pandas') not detected")
    if "pandas" in thin["modules"]:
        failures.append("thin lane must not satisfy a pandas gate")
    if "pandas" not in fat["modules"]:
        failures.append("fat lane must satisfy a pandas gate")

    if failures:
        for failure in failures:
            print(f"::error title=skip-only-selftest::{failure}", flush=True)
        return 1
    print("SELFTEST OK — both gate forms detected, install closure behaves.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
