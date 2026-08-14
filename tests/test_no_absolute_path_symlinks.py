"""tests/test_no_absolute_path_symlinks.py — no machine-local paths in the tree.

A tracked symlink whose target is an ABSOLUTE path is a machine-local pointer committed
into a repo that gets checked out on other machines. It resolves on exactly one laptop
and is a dangling link everywhere else — including CI and the VPS.

THE INCIDENT THIS CLOSES. A crop harness links `site/stockdata/` in from the main
checkout for the duration of a shoot (the nightly per-ticker artifacts are untracked, so
an agent worktree has none of them) and removes it afterwards. Two mechanisms let one
escape: the link was created OUTSIDE the harness's `try`, so an exception skipped the
cleanup; and a later run's "already exists, skip" branch returned before recording it,
so no subsequent run would ever remove it either. `.gitignore` carried
`site/stockdata/` — and a TRAILING-SLASH PATTERN MATCHES DIRECTORIES ONLY, so the
symlink was never ignored. A broad `git add -A` then committed
`site/stockdata -> /Users/<someone>/…` into the shipping tree, at the exact path four
builders write into and `scripts/audit_r2.py` reads as its freshness beacon.

All four holes are fixed at their own layer. This test closes the CLASS, so the next
harness that borrows a directory cannot re-introduce it silently.

RELATIVE-target symlinks stay legal: they are portable by construction and the repo uses
them deliberately.
"""
from __future__ import annotations

import os
import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _tracked_symlinks() -> list[tuple[str, str]]:
    """Every tracked mode-120000 entry, with the target read from the OBJECT.

    Read out of git rather than off disk on purpose: a sparse or partial checkout may
    not have the entry materialised, and this must fail on the committed content."""
    out = subprocess.run(
        ["git", "-C", str(ROOT), "ls-files", "-s"],
        capture_output=True, text=True, check=True).stdout
    links = []
    for line in out.splitlines():
        meta, _, path = line.partition("\t")
        parts = meta.split()
        if len(parts) < 3 or parts[0] != "120000":
            continue
        target = subprocess.run(
            ["git", "-C", str(ROOT), "cat-file", "-p", parts[1]],
            capture_output=True, text=True, check=True).stdout.strip()
        links.append((path, target))
    return links


def test_no_tracked_symlink_points_at_an_absolute_path():
    """MUTATION CHECK: `ln -s /tmp/x site/x && git add -f site/x` and this reds."""
    offenders = [(p, t) for p, t in _tracked_symlinks()
                 if os.path.isabs(t) or t.startswith("~")]
    assert not offenders, (
        "these tracked symlinks carry ABSOLUTE targets — they resolve on one machine and "
        "dangle on every other checkout (CI, the VPS, any other agent worktree): %s"
        % offenders)


def test_the_nightly_artifact_paths_are_ignored_as_paths_not_as_directories():
    """The specific hole, pinned at the pattern.

    A trailing slash restricts a `.gitignore` entry to directories, so it stops ignoring
    the path the moment something puts a SYMLINK there — which is exactly what a
    borrow-the-artifacts harness does. These paths are borrowed by harnesses in this
    repo, so their patterns must match both forms."""
    lines = [ln.strip() for ln in (ROOT / ".gitignore").read_text().splitlines()]
    for path in ("site/stockdata",):
        assert path in lines, (
            "%r must be ignored WITHOUT a trailing slash so the pattern covers a symlink "
            "at that path, not only a real directory. Present entries: %s"
            % (path, [ln for ln in lines if ln.startswith(path)]))


def test_the_crop_harness_cleans_up_a_symlink_it_did_not_create():
    """The second mechanism, pinned in the harness that caused it.

    `link_nightly_artifacts()` skips a path that already exists. If it skips WITHOUT
    recording it, a leftover from an aborted run is invisible to every later run's
    cleanup and can only accumulate."""
    src = (ROOT / "mockups" / "refs" / "psi" / "workspace" / "crops" / "impl" / "w4"
           / "shoot_w4_crops.py").read_text()
    block = src[src.index("def link_nightly_artifacts"):src.index("def assert_not_stub_grade")]
    skip = block.index("if dst.exists() or dst.is_symlink():")
    # to the `continue` STATEMENT, not to the first occurrence of the word — the comment
    # explaining this very fix contains it, and a guard that cannot tell a rule from its
    # explanation is the trap this wave has now hit four separate times.
    m = re.search(r"^\s*continue\s*$", block[skip:], re.M)
    assert m, "the skip branch no longer ends in a `continue`; re-derive this test"
    tail = block[skip:skip + m.start()]
    assert "made.append(dst)" in tail, (
        "the skip branch must ADOPT a pre-existing symlink for cleanup; without it an "
        "aborted run's leftover is never removed by any later run")
    # and the link call must sit inside the try that owns the cleanup
    main = src[src.index("def main("):]
    assert main.index("try:") < main.index("linked = link_nightly_artifacts()"), (
        "link_nightly_artifacts() must be called INSIDE the try whose finally removes "
        "the symlink, or an exception before the try leaves it in the tree")
