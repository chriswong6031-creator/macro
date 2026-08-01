#!/usr/bin/env python3
"""Static guard: no git conflict markers in templates, shipped site files, or code.

2026-07-03 incident: a merge commit shipped literal conflict markers
(`<<<<<<< ours` / `=======` / `>>>>>>> theirs`) inside templates/dashboard.html.j2
and NOTHING went red. Jinja parses marker lines as plain text (a syntactically
valid template), the pytest suite never rendered that block, and the existing
guards (check_inline_js, check_title_i18n, check_nav_*) don't look for markers —
so the broken merge landed green and the markers rendered on the live page.
This guard turns that whole class of accident into a pre-merge / pre-deploy
failure, in the same ci.yml / pages.yml gates as its siblings.

What it flags (column-0 anchored, like git writes them):
  `<<<<<<< <label>`  — always flagged
  `>>>>>>> <label>`  — always flagged (a lone one = partially cleaned conflict)
  `=======`          — flagged ONLY between a `<<<<<<<` and a `>>>>>>>` line in
                       the same file: a bare 7-equals line is a legitimate
                       setext/RST heading underline in docs, so out-of-block
                       occurrences are ignored. diff3-style `||||||| <base>`
                       lines are flagged under the same in-block rule.

Scope: templates/**, engine/**, scripts/** (every text file), and site/**
restricted to *.html / *.json / *.js / *.css — the bytes that actually ship.
Binary files (NUL in the first 1 KiB) are skipped.

Usage:
    python -m scripts.check_conflict_markers [ROOT]   # default: repo root (.)
    python -m scripts.check_conflict_markers --file PATH
    python -m scripts.check_conflict_markers --changed-from REV [ROOT]
    python -m scripts.check_conflict_markers --self-test
Exit codes: 0 = clean / self-test passed · 1 = marker(s) found / self-test failed.
"""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile

# Assembled by concatenation so no line of THIS file (which sits in the scanned
# scripts/ tree) ever starts with a live marker at column 0.
_OPEN = "<" * 7 + " "   # start of the `ours` side
_MID = "=" * 7          # separator, alone on its line
_BASE = "|" * 7 + " "   # diff3 merged-base separator
_CLOSE = ">" * 7 + " "  # end of the `theirs` side

# (subtree, extensions) scan roots; extensions=None means every text file.
_ROOTS = (
    ("templates", None),
    ("engine", None),
    ("scripts", None),
    ("site", (".html", ".json", ".js", ".css")),
)
_SKIP_DIRS = {".git", "__pycache__", "node_modules", ".venv"}


def _looks_binary(path: str) -> bool:
    try:
        with open(path, "rb") as fh:
            return b"\0" in fh.read(1024)
    except OSError:
        return True


def scan_file(path: str):
    """Return [(lineno, line)] for every conflict-marker line in one file."""
    hits = []
    in_block = False
    with open(path, encoding="utf-8", errors="replace") as fh:
        for lineno, line in enumerate(fh, 1):
            if line.startswith(_OPEN):
                hits.append((lineno, line.rstrip("\r\n")))
                in_block = True
            elif line.startswith(_CLOSE):
                hits.append((lineno, line.rstrip("\r\n")))
                in_block = False
            elif in_block and (line.rstrip("\r\n") == _MID or line.startswith(_BASE)):
                hits.append((lineno, line.rstrip("\r\n")))
    return hits


def scan(root: str = "."):
    """Return sorted [(path, lineno, line)] across all scan roots under `root`."""
    findings = []
    for sub, exts in _ROOTS:
        base = os.path.join(root, sub)
        if not os.path.isdir(base):
            continue
        for dirpath, dirs, names in os.walk(base):
            dirs[:] = sorted(d for d in dirs if d not in _SKIP_DIRS)
            for name in sorted(names):
                if exts is not None and not name.endswith(exts):
                    continue
                path = os.path.join(dirpath, name)
                if _looks_binary(path):
                    continue
                for lineno, line in scan_file(path):
                    findings.append((path, lineno, line))
    findings.sort()
    return findings


def _scannable_relpath(path: str) -> bool:
    """Whether a repo-relative path belongs to the guard's shipping scope."""
    normalized = os.path.normpath(path)
    if normalized == ".." or normalized.startswith(".." + os.sep):
        return False
    top = normalized.split(os.sep, 1)[0]
    for sub, exts in _ROOTS:
        if top != sub:
            continue
        return exts is None or normalized.endswith(exts)
    return False


def scan_changed(root: str, revision: str):
    """Scan only files changed between ``revision`` and HEAD.

    This is the PR ratchet mode: an already-damaged generated baseline cannot
    freeze unrelated shipping, while every in-scope file the PR touches is still
    checked fail-closed. The full-tree default remains the deploy/sweep guard.
    """
    proc = subprocess.run(
        [
            "git", "-C", root, "diff", "--name-only", "-z",
            "--diff-filter=ACMRTUXB", f"{revision}...HEAD", "--",
        ],
        capture_output=True,
    )
    if proc.returncode != 0:
        detail = proc.stderr.decode("utf-8", "replace").strip()
        raise RuntimeError(detail or f"git diff from {revision!r} failed")

    findings = []
    for rel in sorted(proc.stdout.decode("utf-8", "replace").split("\0")):
        if not rel or not _scannable_relpath(rel):
            continue
        path = os.path.join(root, rel)
        if not os.path.isfile(path) or _looks_binary(path):
            continue
        for lineno, line in scan_file(path):
            findings.append((path, lineno, line))
    findings.sort()
    return findings


def _self_test() -> int:
    """Fixture check: known-bad files must be flagged, known-good must not."""
    tmp = tempfile.mkdtemp(prefix="check_conflict_markers_selftest_")
    try:
        os.makedirs(os.path.join(tmp, "templates"))
        os.makedirs(os.path.join(tmp, "site"))

        def write(rel: str, text: str) -> None:
            with open(os.path.join(tmp, rel), "w", encoding="utf-8") as fh:
                fh.write(text)

        # FAIL: a full conflict block — all three marker lines must be flagged.
        write(
            "templates/bad_block.html.j2",
            "<div>\n"
            + _OPEN + "ours\n"
            + "  <b>kept</b>\n"
            + _MID + "\n"
            + "  <b>dropped</b>\n"
            + _CLOSE + "theirs\n"
            + "</div>\n",
        )
        # FAIL: a lone close marker left behind by a partial hand-cleanup.
        write("site/lone_close.json", '{"k": 1}\n' + _CLOSE + "theirs\n")
        # PASS: setext/RST-style 7-equals underline with no conflict block around it.
        write("templates/underline.md", "Heading\n" + _MID + "\nBody text.\n")
        # PASS: plain clean file.
        write("site/clean.html", "<html><body>fine\n== not a marker ==\n</body></html>\n")

        expected = {
            os.path.join(tmp, "templates", "bad_block.html.j2"): [2, 4, 6],
            os.path.join(tmp, "site", "lone_close.json"): [2],
        }
        got: dict[str, list[int]] = {}
        for path, lineno, _line in scan(tmp):
            got.setdefault(path, []).append(lineno)

        ratchet_ok = True
        if shutil.which("git"):
            try:
                def git(*args: str) -> None:
                    subprocess.run(
                        ["git", *args], cwd=tmp, check=True,
                        stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                    )

                git("init", "-q")
                git("config", "user.email", "guard-selftest@example.invalid")
                git("config", "user.name", "guard-selftest")
                git("add", ".")
                git("commit", "-qm", "baseline with known legacy damage")

                # A clean changed file must pass even though unchanged legacy
                # fixtures still contain markers.
                write("site/clean.html", "<html><body>fresh and clean</body></html>\n")
                git("add", "site/clean.html")
                git("commit", "-qm", "clean change")
                clean_findings = scan_changed(tmp, "HEAD~1")

                # The same ratchet must fail as soon as the changed file itself
                # introduces a conflict block.
                write(
                    "site/clean.html",
                    _OPEN + "ours\n" + "good\n" + _MID + "\n" + "bad\n" + _CLOSE + "theirs\n",
                )
                git("add", "site/clean.html")
                git("commit", "-qm", "bad change")
                bad_findings = scan_changed(tmp, "HEAD~1")
                ratchet_ok = not clean_findings and [line for _p, line, _m in bad_findings] == [1, 3, 5]
            except (OSError, subprocess.SubprocessError, RuntimeError):
                ratchet_ok = False

        if got == expected and ratchet_ok:
            print(
                "check_conflict_markers: self-test OK — bad fixtures flagged, "
                "good fixtures clean, changed-file ratchet proven."
            )
            return 0
        print(
            "check_conflict_markers: SELF-TEST FAIL —\n"
            f"  expected: {expected}\n"
            f"  got:      {got}\n"
            f"  changed-file ratchet: {'OK' if ratchet_ok else 'FAIL'}",
            file=sys.stderr,
        )
        return 1
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def main(argv: list[str] | None = None) -> int:
    argv = argv if argv is not None else sys.argv[1:]
    if argv and argv[0] == "--self-test":
        return _self_test()
    if argv and argv[0] == "--file":
        if len(argv) != 2:
            print(
                "usage: check_conflict_markers.py --file PATH",
                file=sys.stderr,
            )
            return 2
        target = argv[1]
        findings = [
            (target, lineno, line) for lineno, line in scan_file(target)
        ]
        scope = os.path.abspath(target)
    elif argv and argv[0] == "--changed-from":
        if len(argv) not in (2, 3):
            print(
                "usage: check_conflict_markers.py --changed-from REV [ROOT]",
                file=sys.stderr,
            )
            return 2
        revision = argv[1]
        root = argv[2] if len(argv) == 3 else "."
        try:
            findings = scan_changed(root, revision)
        except RuntimeError as exc:
            print(
                f"check_conflict_markers: ERROR — cannot classify files changed "
                f"from {revision}: {exc}",
                file=sys.stderr,
            )
            return 2
        scope = f"files changed from {revision} under {os.path.abspath(root)}"
    else:
        root = argv[0] if argv else "."
        findings = scan(root)
        scope = os.path.abspath(root)
    if findings:
        print(
            f"check_conflict_markers: FAIL — {len(findings)} git conflict-marker "
            f"line(s) in committed content:\n",
            file=sys.stderr,
        )
        for path, lineno, line in findings:
            print(f"  {path}:{lineno}: {line}", file=sys.stderr)
        print(
            "\nA merge or rebase left literal conflict markers behind. Re-open each file,"
            "\nresolve the conflict properly (keep exactly one side or a real merge of the"
            "\ntwo), delete the marker lines, and re-run this check.",
            file=sys.stderr,
        )
        return 1
    print(f"check_conflict_markers: OK — no git conflict markers under {scope}.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
