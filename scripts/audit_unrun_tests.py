#!/usr/bin/env python3
"""Census: which tests/test_*.py suites does NO workflow ever run, and how dark are they?

Two independent holes, deliberately measured separately:

  UNRUN        the suite's filename appears in no `run:` step in any workflow or
               the packed legacy CI manifest. There is no broad `pytest tests/`
               anywhere in the repo — every invocation carries an explicit file
               list — so an unnamed suite is genuinely never executed by CI.

  UNTRIGGERABLE  nothing that would change the suite's verdict is matched by
               ci.yml's `on.pull_request.paths`, so the workflow cannot even START.
               Checked against the test file AND the modules the suite imports,
               with glob semantics (`engine/**` is a broad catch-all; exact-membership
               checks over-report darkness badly).

A suite that is both is STRICTLY DARK: no possible edit produces a signal.  Those are
ranked first, and within them the ones reachable from the nightly/render pipelines
rank highest — a silent break there moves shipped numbers with nothing going red.

Usage:
    python3 scripts/audit_unrun_tests.py                     # summary table
    python3 scripts/audit_unrun_tests.py --tier P0           # list one tier
    python3 scripts/audit_unrun_tests.py --json out.json     # full machine-readable rows

Exit status is always 0: this is a reporting tool, not a gate.  Wiring every unrun
suite would blow the ci-pack budget, so the output is triage input, not a to-do list.
"""
from __future__ import annotations

import argparse
import ast
import fnmatch
import json
import re
import sys
from collections import Counter
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
WORKFLOWS = ROOT / ".github/workflows"
CI_MANIFEST = ROOT / ".github/ci/legacy-jobs.yml"
TESTS = ROOT / "tests"

FIRST_PARTY = ("engine", "scripts", "app", "collectors", "lib", "admin", "site")

# Workflows that BUILD and PUBLISH — a module they invoke feeds shipped numbers.
PIPELINE_WORKFLOWS = (
    "daily.yml", "render.yml", "engine-render.yml", "closing-bell.yml",
    "earlyclose.yml", "intraday.yml", "intraday-fastpath.yml", "asia-close.yml",
    "weekly.yml", "sentinel.yml",
)

# A module that writes under data/ advances a forward ledger; a break there is durable.
_LEDGER_WRITE = re.compile(
    r"to_parquet|to_csv|\.write_text|\.write_bytes|json\.dump|open\([^)]*['\"][wa]", re.S)
_DATA_PATH = re.compile(r"['\"]data/|DATA_DIR|DATA_ROOT|data_dir|/data/")

TIERS = (
    ("P0", "unrun + untriggerable + on a publish pipeline"),
    ("P1", "unrun, on a publish pipeline (triggerable)"),
    ("P2", "unrun + untriggerable + writes a data/ ledger"),
    ("P3", "unrun + untriggerable (other)"),
    ("P4", "unrun, writes a data/ ledger (triggerable)"),
    ("P5", "unrun (remainder)"),
)


def _workflow_blob() -> str:
    """Text of every workflow's `run:` STEPS ONLY — never its comments.

    This used to be the raw file text, so a suite named in a YAML COMMENT counted as
    "run by CI" (OIP E8, 2026-07-29: a `# Anti-rot: tests/test_x.py` line in render.yml
    made the census report a wholly-unwired suite as covered — the census's own vacuous
    green, in the tool whose entire job is finding dark tests).  Parsing the YAML and
    concatenating `run:` scalars keeps prose out of the verdict.

    Fail-open per file: an unparseable workflow falls back to its raw text, because
    over-reporting coverage for one file is better than crashing a reporting tool.
    """
    paths = sorted(WORKFLOWS.glob("*.yml"))
    if CI_MANIFEST.exists():
        paths.append(CI_MANIFEST)
    chunks: list[str] = []
    for p in paths:
        raw = p.read_text(errors="ignore")
        try:
            doc = yaml.safe_load(raw) or {}
            runs: list[str] = []
            for job in (doc.get("jobs") or {}).values():
                if not isinstance(job, dict):
                    continue
                for step in job.get("steps") or []:
                    if isinstance(step, dict) and isinstance(step.get("run"), str):
                        runs.append(step["run"])
                    # reusable-workflow / composite indirection: keep `with:` values too
                    if isinstance(step, dict) and isinstance(step.get("with"), dict):
                        runs += [str(v) for v in step["with"].values()]
            chunks.append("\n".join(runs))
        except Exception:  # noqa: BLE001 — reporting tool: never crash on one bad file
            chunks.append(raw)
    return "\n".join(chunks)


def _ci_paths() -> list[str]:
    doc = yaml.safe_load((WORKFLOWS / "ci.yml").read_text())
    on = doc[True] if True in doc else doc["on"]
    return list((on.get("pull_request") or {}).get("paths") or [])


def _matched(rel: str, patterns: list[str]) -> bool:
    """GitHub Actions paths semantics: exact, fnmatch, or `prefix/**` subtree."""
    for pat in patterns:
        if pat == rel:
            return True
        if "*" in pat:
            if fnmatch.fnmatch(rel, pat):
                return True
            if pat.endswith("**") and rel.startswith(pat[:-2]):
                return True
    return False


def _subject_modules(path: Path) -> set[str]:
    """First-party modules a suite imports, plus repo-relative files it names.

    `from pkg import a, b` binds pkg.a / pkg.b when those are submodules; resolving
    only `pkg` collapses hundreds of suites onto pkg/__init__.py and silently
    understates how dark they are.
    """
    src = path.read_text(errors="ignore")
    mods: set[str] = set()
    try:
        tree = ast.parse(src)
    except SyntaxError:
        tree = None
    if tree is not None:
        for node in ast.walk(tree):
            names: list[str] = []
            if isinstance(node, ast.Import):
                names = [a.name for a in node.names]
            elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
                names = [node.module]
                if node.module.split(".")[0] in FIRST_PARTY:
                    for alias in node.names:
                        cand = f"{node.module}.{alias.name}"
                        rel = cand.replace(".", "/")
                        if (ROOT / f"{rel}.py").exists() or (ROOT / rel / "__init__.py").exists():
                            names.append(cand)
            for name in names:
                if name.split(".")[0] in FIRST_PARTY:
                    mods.add(name)
    for m in re.finditer(r'import_module\(\s*["\']([\w.]+)["\']', src):
        if m.group(1).split(".")[0] in FIRST_PARTY:
            mods.add(m.group(1))
    for m in re.finditer(
        r'["\']((?:engine|scripts|app|collectors|lib|admin|site|templates|config)'
        r'/[\w./-]+\.(?:py|js|mjs|ts|yml|yaml|json))["\']', src
    ):
        mods.add("@" + m.group(1))
    return mods


def _to_relpaths(mod: str) -> list[str]:
    if mod.startswith("@"):
        return [mod[1:]]
    base = mod.replace(".", "/")
    found = [c for c in (f"{base}.py", f"{base}/__init__.py") if (ROOT / c).exists()]
    return found or [f"{base}.py"]


def _pipeline_modules() -> set[str]:
    """Modules invoked by the build/publish workflows (module and script forms)."""
    out: set[str] = set()
    for name in PIPELINE_WORKFLOWS:
        p = WORKFLOWS / name
        if not p.exists():
            continue
        src = p.read_text(errors="ignore")
        cands = set(
            m.group(1) for m in
            re.finditer(r'\b(?:python3?\s+-m\s+|run_py\s+"[^"]*"\s+)([\w.]+)', src)
        )
        cands |= set(
            m.group(1).replace("/", ".")[:-3] for m in
            re.finditer(r"\b(?:python3?)\s+(scripts/[\w/]+\.py)", src)
        )
        for c in cands:
            rel = c.replace(".", "/") + ".py"
            if (ROOT / rel).exists():
                out.add(rel)
    return out


def _writes_ledger(relpaths: list[str]) -> bool:
    for rel in relpaths:
        f = ROOT / rel
        if not f.is_file():
            continue
        src = f.read_text(errors="ignore")
        if _LEDGER_WRITE.search(src) and _DATA_PATH.search(src):
            return True
    return False


def census() -> list[dict]:
    blob = _workflow_blob()
    patterns = _ci_paths()
    pipeline = _pipeline_modules()
    rows = []
    for path in sorted(TESTS.glob("test_*.py")):
        name = path.name
        if f"tests/{name}" in blob or name in blob:
            continue                                    # named by some run: step
        subjects = sorted({
            rel for mod in _subject_modules(path) for rel in _to_relpaths(mod)
        })
        real = [s for s in subjects
                if not s.startswith("tests") and not s.endswith("__init__.py")]
        on_pipeline = sorted(s for s in real if s in pipeline)
        triggerable = (_matched(f"tests/{name}", patterns)
                       or any(_matched(s, patterns) for s in subjects))
        ledger = _writes_ledger(real)
        if on_pipeline and not triggerable:
            tier = "P0"
        elif on_pipeline:
            tier = "P1"
        elif not triggerable and ledger:
            tier = "P2"
        elif not triggerable:
            tier = "P3"
        elif ledger:
            tier = "P4"
        else:
            tier = "P5"
        rows.append(dict(test=name, tier=tier, triggerable=triggerable,
                         writes_ledger=ledger, pipeline_subjects=on_pipeline,
                         subjects=real))
    return rows


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--tier", help="list the suites in one tier (P0..P5)")
    ap.add_argument("--json", type=Path, help="write all rows as JSON")
    args = ap.parse_args(argv)

    rows = census()
    total = len(list(TESTS.glob("test_*.py")))
    counts = Counter(r["tier"] for r in rows)
    dark = sum(1 for r in rows if not r["triggerable"])

    print(f"tests/test_*.py suites : {total}")
    print(f"  never run by any workflow : {len(rows)}")
    print(f"  ... of which STRICTLY DARK (also untriggerable) : {dark}")
    print()
    for tier, label in TIERS:
        print(f"  {tier}  {counts.get(tier, 0):5d}  {label}")

    if args.tier:
        want = args.tier.upper()
        print(f"\n=== {want} ===")
        for r in rows:
            if r["tier"] == want:
                subj = ", ".join(r["pipeline_subjects"] or r["subjects"][:3]) or "(none)"
                print(f"  {r['test']:56s} {subj}")

    if args.json:
        args.json.write_text(json.dumps(rows, indent=1))
        print(f"\nwrote {args.json} ({len(rows)} rows)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
