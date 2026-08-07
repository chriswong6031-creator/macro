"""Unit tests for the single shared `git add` pathspec parser.

Three staging guards now share one parser, so this file is the only place the
parsing contract is pinned.  Each case below is a shape that broke, or would
have broken, one of the three inline regexes it replaced — see the module
docstring of tests/workflow_staging.py for the history.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from tests.workflow_staging import staged_paths

_REPO = Path(__file__).resolve().parent.parent


# ─────────────────────────────────────────────────────────────────────────────
# The residual defect the #4707 / #4714 sweep closed: SHORT flags
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("line", [
    "git add -f data/x",
    "git add -A data/x",
    "git add -u data/x",
    "git add --ignore-removal data/x",
    "git add -f --ignore-removal data/x",
    "git add --ignore-removal -f data/x",
    "git add -- data/x",
    "git add -f -- data/x",
])
def test_a_flag_is_never_read_as_the_pathspec(line):
    """`--\\S+` skipped LONG flags only, so `git add -f data/x` parsed as `-f`.

    The guard still went red on such a line, but it named the FLAG, not the
    path — so the failure read as "unexpected token in my allow-set" instead of
    "this lane stages a path it does not own".  Which token the failure names
    is the whole discriminator.
    """
    assert staged_paths(line) == {"data/x"}


def test_the_bare_flag_forms_are_actually_distinguishable():
    """Guard against a parser that just drops every token containing a dash."""
    assert staged_paths("git add data/some-dashed-dir") == {"data/some-dashed-dir"}
    assert staged_paths("git add -f data/some-dashed-dir") == {"data/some-dashed-dir"}


# ─────────────────────────────────────────────────────────────────────────────
# The second blindness: only the FIRST pathspec on a line was ever seen
# ─────────────────────────────────────────────────────────────────────────────

def test_every_pathspec_on_the_line_is_seen():
    """All three inline forms captured one token and stopped.

    `git add -f a b` is a live idiom in this repo (render.yml, closing-bell.yml),
    so an exact-set guard could be handed a second staged path it never saw.
    """
    assert staged_paths("git add data/a data/b") == {"data/a", "data/b"}
    assert staged_paths(
        "git add -f data/regime/latest.json data/market_state/latest.json"
    ) == {"data/regime/latest.json", "data/market_state/latest.json"}


def test_a_trailing_backslash_continuation_is_joined():
    assert staged_paths("git add -f data/a \\\n    data/b") == {"data/a", "data/b"}


# ─────────────────────────────────────────────────────────────────────────────
# Things that are not pathspecs
# ─────────────────────────────────────────────────────────────────────────────

def test_a_redirection_is_not_a_pathspec():
    """Every real staging line in these workflows ends `2>/dev/null || true`."""
    assert staged_paths("git add data/x 2>/dev/null || true") == {"data/x"}
    assert staged_paths("git add -f data/x >/dev/null 2>&1") == {"data/x"}


def test_the_line_is_sliced_at_a_pipe_or_and():
    assert staged_paths("git add data/x && git commit -m nope") == {"data/x"}
    assert staged_paths("git add data/x | tee log") == {"data/x"}


def test_a_commented_out_add_is_not_a_staging_claim():
    assert staged_paths("# git add data/x") == set()
    assert staged_paths("   # git add data/x") == set()
    assert staged_paths("git add data/x  # git add data/y") == {"data/x"}


def test_a_line_that_merely_mentions_git_add_is_not_a_staging_line():
    assert staged_paths("echo 'run git add data/x'") == set()
    assert staged_paths("# the commit step's git add names them") == set()


def test_multiline_text_and_indentation():
    body = """
          git add content/seo/blog 2>/dev/null || true
          git add --ignore-removal site/assets/css 2>/dev/null || true
          git add -f data/press/published.jsonl 2>/dev/null || true
    """
    assert staged_paths(body) == {
        "content/seo/blog", "site/assets/css", "data/press/published.jsonl"}


def test_empty_and_addless_text():
    assert staged_paths("") == set()
    assert staged_paths("git commit -m x\ngit push") == set()


# ─────────────────────────────────────────────────────────────────────────────
# The parser must agree with the old house form wherever the old form was right
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("wf", ["press-publish.yml", "marketing-hot-tape.yml"])
def test_parser_matches_the_old_house_form_on_todays_workflows(wf):
    """A regression fence for the sweep itself.

    On the lines these two workflows carry TODAY (single pathspec, long flags
    only) the new parser must return exactly what the old `(?:--\\S+\\s+)*`
    house form returned — otherwise the sweep silently moved a guard's goalposts
    rather than only widening what it can see.
    """
    text = (_REPO / ".github/workflows" / wf).read_text(encoding="utf-8")
    old = set(re.findall(r"^\s*git add\s+(?:--\S+\s+)*([^\s]+)", text, re.M))
    assert staged_paths(text) == old, (
        f"{wf}: new parser disagrees with the old house form on the CURRENT "
        "file — investigate before assuming the sweep is behaviour-preserving")


def test_the_two_swept_workflows_carry_no_short_flag_add_today():
    """Pins the stated premise of the sweep.

    `git add -f` is absent from these two files, and that absence is the ONLY
    reason the three guards were green before the sweep.  If this test starts
    failing, the guards are now load-bearing for real — which is the point.
    """
    for wf in ("press-publish.yml", "marketing-hot-tape.yml"):
        text = (_REPO / ".github/workflows" / wf).read_text(encoding="utf-8")
        assert not re.search(r"^\s*git add\s+-[^-]", text, re.M), (
            f"{wf} now uses a short-flag `git add`; that is fine and the parser "
            "handles it — this test just records that the premise changed")
