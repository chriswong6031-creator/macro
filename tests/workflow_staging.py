"""One parser for "which pathspecs does this workflow's `git add` stage?".

Why this module exists
----------------------
Three test files each carried their own inline regex for this question, and
every one of them was wrong in the same family of ways.  They were then fixed
*separately*, which is the actual defect this module closes:

    #4549  fixed one copy and left another broken
    #4707  ...which surfaced as the press-properties guard going blind
    #4714  ...and again as the hot-tape radar guards going blind

The three shapes on the eve of this sweep, and what each did with a real line::

    test_press_workflow.py    r"^\\s*git add\\s+(?:--\\S+\\s+)*([^\\s]+)"
    test_press_properties.py  r"^\\s*git add ([^\\s]+)"
    test_marketing_hot_tape_radar.py  r"^\\s*git add (\\S+)"

    'git add --ignore-removal data/x'  -> 'data/x' / '--ignore-removal' / '--ignore-removal'
    'git add -f data/x'                -> '-f'     / '-f'               / '-f'
    'git add data/a data/b'            -> 'data/a' (all three: the 2nd path is unseen)

Only the first form skipped a flag at all, and `--\\S+` skips LONG flags only —
so `git add -f data/somewhere` parsed as the pathspec ``-f`` and the real path
was never seen.  A guard that asserts an exact staged set still goes red on
such a line, but it reds naming ``-f``, not the path, so the failure reads as
"the flag is not in my allow-set" rather than "this lane stages a path it does
not own".  `git add -f` is a live idiom in this repo's workflows
(live-quotes.yml, earlyclose.yml, render.yml, closing-bell.yml); it is absent
from press-publish.yml and marketing-hot-tape.yml today, and that absence is
the *only* reason those three guards were green.

What this parser handles that the inline regexes did not
--------------------------------------------------------
* **short flags** (``-f``, ``-A``, ``-u``) as well as long ones — the residual
  defect that motivated the sweep;
* **every pathspec on the line**, not just the first, so ``git add -f a b``
  cannot hide ``b`` from an exact-set assertion;
* the ``--`` end-of-options separator;
* shell redirections (``2>/dev/null``), which are not pathspecs;
* trailing-backslash line continuations, joined before parsing;
* the ``[^#|&]`` slice, so ``|| true`` and ``&& git commit`` never become
  pathspecs, and a commented-out ``# git add ...`` is not a staging claim.

Deliberately NOT converged here: ``tests/test_asset_stamp_lane_order.py`` keeps
its own variant.  It returns ``{pathspec: line index}`` because it asserts on
the *order* of the shim/externalize/stamp chain relative to the add, and it
filters to a ``site/`` prefix.  That is a different question than "what does
this step stage", and folding it in would have meant contorting this signature
to serve one caller.
"""

from __future__ import annotations

import re

__all__ = ["staged_paths"]

# `git add …` up to the first comment / pipe / `&&`.  Mirrors the slicing in
# tests/test_asset_stamp_lane_order.py so a trailing `2>/dev/null || true`
# never becomes a pathspec.
_GIT_ADD_RE = re.compile(r"^\s*git add\b(?P<args>[^#|&]*)")


def _logical_lines(text: str):
    """Yield lines with trailing-backslash continuations joined into one.

    A `git add -f a \\` / `   b` pair stages both paths; parsed per physical
    line, `b` is invisible to every caller here.
    """
    buf = ""
    for raw in text.splitlines():
        buf = raw if not buf else f"{buf} {raw.strip()}"
        stripped = buf.rstrip()
        if stripped.endswith("\\"):
            buf = stripped[:-1]
            continue
        yield buf
        buf = ""
    if buf:
        yield buf


def _is_pathspec(token: str) -> bool:
    """A `git add` argument that names a path, rather than a flag or a redirect."""
    if token == "--":
        return False           # end-of-options separator
    if token.startswith("-"):
        return False           # flags: BOTH `-f` and `--ignore-removal`
    if ">" in token or "<" in token:
        return False           # shell redirection, e.g. `2>/dev/null`
    return bool(token)


def staged_paths(text: str) -> set[str]:
    """Every pathspec staged by a `git add` line in ``text``.

    ``text`` may be a single step's ``run:`` body or a whole workflow file —
    callers here pass both.
    """
    out: set[str] = set()
    for line in _logical_lines(text):
        if line.lstrip().startswith("#"):
            continue
        m = _GIT_ADD_RE.match(line)
        if not m:
            continue
        out.update(tok for tok in m.group("args").split() if _is_pathspec(tok))
    return out
