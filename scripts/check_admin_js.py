#!/usr/bin/env python3
"""Out-of-scope reference guard for the admin console's JavaScript.

`admin/static/app.js` is a flat top-level browser script — ~390 top-level
declarations, no modules, no bundler. Nothing in CI ran any semantic analysis
over it, so a reference to a name that is not in scope compiled fine, parsed
fine, reviewed fine, and blew up only when the user clicked. That is exactly how
PR #3693 shipped `ReferenceError: rejBox is not defined`: a `let rejBox` local
declared inside `RENDER.marketing_outbox` was read from a *different* top-level
function (`obxRenderLive`). The admin Outbox panel rendered BLANK in production
for ~2 days until #3871 module-scoped the variable (`let OBX_REJ = null;`,
admin/static/app.js:5185 — the same idiom as the `OBX_LAST` above it).

`node --check` (what `check_site_js.py` runs over `site/*.js`) cannot see this:
an undefined identifier is valid syntax. Only a scope analysis catches it, so
this guard shells eslint with a single rule, `no-undef`, over every
`admin/static/*.js` file. No config file, no plugins, no style opinions — one
rule that answers one question: does every bare identifier resolve to something?

admin/static/index.html loads no other script and injects no globals, so the
standard browser environment is the complete global set and no custom globals
list is needed (app.js touches Leaflet only as the member expression `window.L`,
never as a bare `L`).

Usage:
    python3 scripts/check_admin_js.py [FILE ...]   # default: admin/static/*.js
Exit codes: 0 = clean · 1 = finding(s) · 2 = eslint tooling unavailable.
"""
from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_GLOB_DIR = ROOT / "admin" / "static"

# Pinned deliberately at the last 8.x. eslint 8 is the final line whose CLI can
# run fully config-file-free (`--no-eslintrc` + `--env` + `--rule`); eslint 9's
# flat config removed both flags, so moving up means committing an
# eslint.config.js AND depending on the `globals` package just to name the
# browser environment. One pinned version also keeps the check reproducible —
# an unpinned `eslint@latest` would let a rule-behaviour change turn CI red on a
# PR that touched nothing.
ESLINT_PIN = "eslint@8.57.1"

# A cold runner has no npm cache, so the first invocation downloads eslint and
# its dependency tree before it lints anything.
SUBPROCESS_TIMEOUT_S = 180


def _default_files() -> list[Path]:
    """Every JS file in admin/static/ — a glob, so a second file is covered free."""
    return sorted(DEFAULT_GLOB_DIR.glob("*.js"))


def _eslint_argv(files: list[Path]) -> list[str]:
    return [
        "npx",
        "--yes",
        ESLINT_PIN,
        "--no-eslintrc",  # ignore any repo/user config; this guard is self-contained
        "--env",
        "browser,es2022",  # es2022 also sets the parser's ecmaVersion (?? , async, arrows)
        "--rule",
        json.dumps({"no-undef": "error"}),
        "--format",
        "json",  # machine-readable AND the tooling-failure discriminator (see _lint)
        *[str(f) for f in files],
    ]


def _lint(files: list[Path]):
    """Run eslint. Return (findings, None) or (None, tooling-failure reason).

    eslint's exit code alone cannot separate "found lint errors" (1) from "npx
    could not provision the package" (also 1, with an empty stdout). The JSON
    formatter can: a run that actually linted always writes a JSON array to
    stdout, and a run that never got as far as eslint writes nothing parseable.
    """
    try:
        proc = subprocess.run(
            _eslint_argv(files),
            capture_output=True,
            text=True,
            timeout=SUBPROCESS_TIMEOUT_S,
            cwd=str(ROOT),
        )
    except FileNotFoundError:
        return None, "`npx` disappeared between the PATH probe and the call"
    except subprocess.TimeoutExpired:
        return None, (
            f"eslint did not finish within {SUBPROCESS_TIMEOUT_S}s "
            "(cold npx fetch blocked? registry unreachable?)"
        )

    try:
        report = json.loads(proc.stdout)
    except json.JSONDecodeError:
        tail = (proc.stderr or proc.stdout or "").strip().splitlines()[-12:]
        return None, (
            f"eslint could not be provisioned or ran fatally (npx exit {proc.returncode}); "
            "no JSON report on stdout:\n" + "\n".join(f"    {line}" for line in tail)
        )
    if not isinstance(report, list):
        return None, f"unexpected eslint report shape: {type(report).__name__}"

    findings: list[tuple[str, int, int, str, str]] = []
    for entry in report:
        raw_path = str(entry.get("filePath", "?"))
        try:
            rel = str(Path(raw_path).relative_to(ROOT))
        except ValueError:
            rel = raw_path
        for message in entry.get("messages", []):
            # A fatal message is a parse failure: eslint analysed NOTHING in that
            # file, so reporting it clean would be a silent hole in the guard.
            rule = message.get("ruleId") or ("parse-error" if message.get("fatal") else "?")
            findings.append(
                (
                    rel,
                    int(message.get("line") or 0),
                    int(message.get("column") or 0),
                    str(rule),
                    str(message.get("message", "")).strip(),
                )
            )
    findings.sort()
    return findings, None


def main(argv: list[str] | None = None) -> int:
    argv = argv if argv is not None else sys.argv[1:]
    files = [Path(a) for a in argv] if argv else _default_files()

    missing = [f for f in files if not f.is_file()]
    if missing:
        print(
            "check_admin_js: ERROR — file(s) not found: "
            + ", ".join(str(f) for f in missing),
            file=sys.stderr,
        )
        return 2
    if not files:
        print(
            f"check_admin_js: ERROR — no .js files under {DEFAULT_GLOB_DIR}; "
            "the guard would pass vacuously.",
            file=sys.stderr,
        )
        return 2

    for tool in ("node", "npx"):
        if shutil.which(tool) is None:
            print(
                f"check_admin_js: ERROR — `{tool}` not found on PATH; cannot run "
                f"{ESLINT_PIN}. This guard cannot verify anything without it.",
                file=sys.stderr,
            )
            return 2

    findings, failure = _lint(files)
    if failure is not None:
        print(f"check_admin_js: ERROR — {failure}", file=sys.stderr)
        return 2

    if findings:
        print(
            f"check_admin_js: FAIL — {len(findings)} unresolved reference(s) in "
            f"{len(files)} admin JS file(s):\n",
            file=sys.stderr,
        )
        for rel, line, col, rule, message in findings:
            print(f"  {rel}:{line}:{col}  {rule}  {message}", file=sys.stderr)
        print(
            "\nA bare identifier that resolves to nothing throws a ReferenceError at "
            "the moment the code path runs — the admin panel renders BLANK and the "
            "console error is the only trace (PR #3693 → #3871, ~2 days live). "
            "Declare the binding at the scope every reader shares (module scope for "
            "cross-function state, as `OBX_LAST`/`OBX_REJ` do), or pass it as an "
            "argument.",
            file=sys.stderr,
        )
        return 1

    names = ", ".join(f.name for f in files)
    print(f"check_admin_js: OK — every identifier resolves in {names}.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
