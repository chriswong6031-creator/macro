#!/usr/bin/env python3
"""GitHub Actions `paths` filter semantics — ONE matcher, shared by every consumer.

`fnmatch` is the wrong tool and the wrong-ness is directional. In `fnmatch` a
single `*` crosses `/`, so `scripts/*.py` reports `scripts/ci/deep.py` as covered —
which GitHub does NOT. A guard built on `fnmatch` therefore under-reports exactly
the nested modules most likely to be missing a path entry (the live bug in
`scripts/audit_unrun_tests.py:_matched`). So the pattern is translated instead:

    `*`   any run of characters EXCEPT `/`
    `**`  crosses directories
    `?`   exactly one non-`/` character

PROVENANCE. This is `_glob_regex`/`matched` from `scripts/check_ci_trigger_closure.py`
(PR #4649, `claude/ci-trigger-closure-guard`), lifted into a module of its own so the
merge-on-green sweeper can reuse it without importing that guard's dependency chain
(`yaml`, `scripts.audit_unrun_tests`, `scripts.run_ci_pack`) into a lane whose whole
point is to be a handful of API calls on a sparse checkout. Nothing here imports
anything outside the standard library, on purpose. When #4649 lands it should drop
its private copy and import this instead — see that PR's sequencing note.

NEGATION IS NOT MODELLED. GitHub's filter syntax allows `!`-prefixed exclusion
entries evaluated in order. `.github/workflows/ci.yml` uses none (verified
2026-08-06: zero `!` entries across 1,713 paths). Callers that gate a decision on
this matcher must REFUSE a pattern list containing one rather than mis-evaluate it —
`merge_on_green.load_pr_gates` raises, which stops the sweep loudly instead of
quietly widening or narrowing a surface nobody re-derived.
"""

from __future__ import annotations

import re

__all__ = ["NEGATION_PREFIX", "glob_to_regex", "matches", "matched", "matching_patterns"]

NEGATION_PREFIX = "!"

_CACHE: dict[str, re.Pattern[str]] = {}


def glob_to_regex(pattern: str) -> re.Pattern[str]:
    """Translate one GitHub filter pattern into an anchored regex."""
    out: list[str] = []
    index = 0
    while index < len(pattern):
        char = pattern[index]
        if char == "*":
            if pattern[index : index + 2] == "**":
                out.append(".*")
                index += 2
                continue
            out.append("[^/]*")
        elif char == "?":
            out.append("[^/]")
        else:
            out.append(re.escape(char))
        index += 1
    return re.compile("^" + "".join(out) + "$")


def matches(rel: str, pattern: str) -> bool:
    """Would an edit to ``rel`` alone satisfy this single pattern?"""
    if "*" not in pattern and "?" not in pattern:
        return pattern == rel
    compiled = _CACHE.get(pattern)
    if compiled is None:
        compiled = _CACHE[pattern] = glob_to_regex(pattern)
    return bool(compiled.match(rel))


def matched(rel: str, patterns: list[str] | None) -> bool:
    """``patterns is None`` means the workflow declares no filter — it always runs."""
    if patterns is None:
        return True
    return any(matches(rel, pattern) for pattern in patterns)


def matching_patterns(rel: str, patterns: list[str] | None) -> list[str]:
    """EVERY entry ``rel`` satisfies, not just the first.

    The merge-on-green surface check intersects two files' matched-entry sets, so a
    file that is covered twice (`engine/signal_quality.py` is listed explicitly AND
    swept by `engine/**`) must report both: stopping at the first match would make
    the intersection depend on list order.
    """
    if patterns is None:
        return []
    return [pattern for pattern in patterns if matches(rel, pattern)]
