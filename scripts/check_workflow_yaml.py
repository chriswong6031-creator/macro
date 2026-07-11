#!/usr/bin/env python3
"""Guard: every .github/workflows/* file must parse as YAML with on: + jobs:.

Incident (2026-07-10 → 07-11): metabolism-agenda.yml shipped with `python -c`
bodies whose continuation lines sat at column 0 inside a `run: |` block
scalar. A column-0 line terminates the block scalar, so the WHOLE FILE stops
parsing. GitHub cannot read the `on:` block of an unparseable workflow file,
so it stamps a FAILED 0-second run (zero jobs, "workflow file issue") on
every push to every branch carrying the broken file — ~325 failed runs in
~26 hours for a workflow that declares only schedule + workflow_dispatch
triggers. Introduced by #2135; file repaired by #2260 (heredoc rewrite).

Nothing else guards this class: check_dag_conformance.py yaml-loads only the
workflows declared as lanes in config/dag.yml, so a non-lane workflow file
(most of the metabolism-* set, one-shot ops lanes, ...) can merge unparseable
with all checks green. This guard loads EVERY file under .github/workflows/.

Checks per file:
  1. yaml.safe_load succeeds (parse).
  2. Top level is a mapping carrying an `on` trigger block and a non-empty
     `jobs:` mapping. PyYAML (YAML 1.1) reads the bare key `on` as boolean
     True — both spellings are accepted. A parseable file MISSING `on:` hits
     the same GitHub-side validation failure as an unparseable one.

Usage:
    python3 scripts/check_workflow_yaml.py [workflows_dir]
    python3 scripts/check_workflow_yaml.py --selftest

Exit codes: 0 all files pass; 1 any failure (one line per finding).
"""

from __future__ import annotations

import sys
from pathlib import Path

import yaml


def check_file(path: Path) -> list[str]:
    """Return a list of failure messages for one workflow file (empty = pass)."""
    try:
        doc = yaml.safe_load(path.read_text())
    except yaml.YAMLError as exc:
        first = str(exc).replace("\n", " | ")
        return [f"{path}: YAML PARSE ERROR — {first}"]
    if not isinstance(doc, dict):
        return [f"{path}: top level is {type(doc).__name__}, expected a mapping"]
    problems = []
    # PyYAML 1.1 coerces the bare `on` key to boolean True.
    if True not in doc and "on" not in doc:
        problems.append(f"{path}: no `on:` trigger block — GitHub rejects the file")
    jobs = doc.get("jobs")
    if not isinstance(jobs, dict) or not jobs:
        problems.append(f"{path}: no non-empty `jobs:` mapping")
    return problems


def check_dir(workflows_dir: Path) -> int:
    files = sorted(
        p for p in workflows_dir.iterdir() if p.suffix in (".yml", ".yaml")
    )
    if not files:
        print(f"FAIL: no workflow files found under {workflows_dir}")
        return 1
    failures: list[str] = []
    for path in files:
        failures.extend(check_file(path))
    for line in failures:
        print(f"FAIL: {line}")
    if failures:
        print(f"\n{len(failures)} finding(s) across {len(files)} workflow file(s).")
        return 1
    print(f"OK: {len(files)} workflow file(s) parse with on: + jobs: blocks.")
    return 0


def selftest() -> int:
    """Synthetic assertions — no repo files touched."""
    import tempfile

    good = "on:\n  schedule:\n    - cron: '0 0 * * *'\njobs:\n  a:\n    steps: []\n"
    # The incident shape: column-0 line inside a `run: |` block scalar.
    broken = (
        "on: push\njobs:\n  a:\n    steps:\n      - run: |\n"
        "          python -c \"\nimport sys\n\"\n"
    )
    no_on = "name: x\njobs:\n  a:\n    steps: []\n"
    no_jobs = "on: push\nname: x\n"
    cases = [(good, 0), (broken, 1), (no_on, 1), (no_jobs, 1)]
    for i, (text, want_findings) in enumerate(cases):
        with tempfile.NamedTemporaryFile("w", suffix=".yml", delete=False) as f:
            f.write(text)
            tmp = Path(f.name)
        got = len(check_file(tmp))
        tmp.unlink()
        if bool(got) != bool(want_findings):
            print(f"SELFTEST FAIL: case {i} expected findings={want_findings}, got {got}")
            return 1
    print("SELFTEST OK: 4 cases.")
    return 0


def main(argv: list[str]) -> int:
    if "--selftest" in argv:
        return selftest()
    workflows_dir = Path(argv[0]) if argv else Path(".github/workflows")
    if not workflows_dir.is_dir():
        print(f"FAIL: {workflows_dir} is not a directory")
        return 1
    return check_dir(workflows_dir)


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
