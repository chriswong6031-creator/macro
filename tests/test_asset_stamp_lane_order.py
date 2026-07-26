"""Lane ordering for `?v=` stamps (ui.asset_stamp).

`app/deploy/Caddyfile` serves versioned asset requests `immutable, max-age=1y`, so
a stamp that does not move pins every returning browser to the bytes the asset had
when the page was last stamped. Two lane-shaped defects kept that happening long
after #3573 fixed the rewrite itself (`lib.pages.optimize_assets_text`):

  1. `check_template_site_sync --fix` rewrites the site copy of every plain-copy
     pair FROM `templates/`. It runs after the stamping sweep in every lane, so a
     stamp written only site-side was reverted before it could reach main —
     structurally unreachable, not merely stale. `scripts.optimize_assets` now
     stamps the `templates/` side too, which only helps if the lane also STAGES
     `templates/`; staging `site/` alone lands the pair diverged and reds the
     publish gate (pages.yml). Live cost: #3617's onboard.css fix was at the origin
     while browsers kept the old sheet (site/index.html linked
     onboard.css?v=cfdca9e2); #3624 hand-bumped that one page.

  2. The tree a lane PUSHES is its post-rebase tree, not the one it stamped. Pages
     a sibling lane lands mid-run arrive at `git pull --rebase`, long after the
     normalizer step — so a green scope=all render can still ship them un-stamped.
     2026-07-26: render 6260e5ac8c0 shipped site/us_track_record.html with a bare
     `theme.css` because standout-audit-us committed it 14 minutes AFTER that
     run's checkout (from=83004e1e9b0). Every lane with a post-rebase heal block
     must therefore re-stamp inside the push loop, before the `--fix`.

These pin the ordering so neither can regress silently in a workflow edit.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

ROOT = Path(__file__).resolve().parents[1]
WORKFLOWS = ROOT / ".github/workflows"

STAMP = "python -m scripts.optimize_assets"
FIX = "python -m scripts.check_template_site_sync --fix"

# Lanes that both stamp assets and commit site/ — every one of them must satisfy
# the ordering + staging contract below.
LANES = [
    "render.yml",
    "engine-render.yml",
    "daily.yml",
    "weekly.yml",
    "asia-close.yml",
    "closing-bell.yml",
    "earlyclose.yml",
]


def _lines(name: str) -> list[str]:
    return (WORKFLOWS / name).read_text().splitlines()


def _idx(lines: list[str], needle: str) -> list[int]:
    """Line numbers of every RUN of `needle` (comments mentioning it don't count)."""
    return [i for i, ln in enumerate(lines)
            if needle in ln and not ln.lstrip().startswith("#")]


@pytest.mark.parametrize("lane", LANES)
def test_lane_still_stamps_assets(lane):
    assert _idx(_lines(lane), STAMP), f"{lane} no longer runs the stamping sweep"


@pytest.mark.parametrize("lane", LANES)
def test_every_sync_fix_is_preceded_by_a_stamp(lane):
    """`--fix` copies templates/ over site/, so the template must already be
    re-stamped when it runs — otherwise the fix reverts the stamp (defect 1)."""
    lines = _lines(lane)
    stamps, fixes = _idx(lines, STAMP), _idx(lines, FIX)
    assert fixes, f"{lane} no longer runs the template↔site sync fix"
    for f in fixes:
        assert any(s < f for s in stamps), (
            f"{lane}:{f + 1} runs `{FIX}` with no `{STAMP}` before it — the pair would be "
            "healed from a STALE templates/ stamp, reverting the fresh one")


@pytest.mark.parametrize("lane", LANES)
def test_stamped_lanes_stage_templates(lane):
    """Staging site/ without templates/ leaves the re-stamped template uncommitted, so
    the committed pair diverges and the pages.yml publish gate reds — every broad
    `git add … site/` must be accompanied by a `git add templates/`.

    Accepted as a SEPARATE line on purpose: `git add site/ templates/` exits 128 when a
    pathspec matches nothing and the pre-commit staging runs under `-eo pipefail`, which
    would abort the commit and lose a whole render instead of just the stamp.
    """
    lines = _lines(lane)
    broad = [i for i, ln in enumerate(lines)
             if re.search(r"^\s*git add (?!-f\b)[^#|&]*\bsite/(\s|$)", ln)]
    assert broad, f"{lane} no longer stages site/ broadly — did the commit step move?"
    offenders = []
    for i in broad:
        window = lines[i:i + 8]  # same staging run, before the diff/commit
        if not any(re.search(r"^\s*git add [^#|&]*\btemplates/", ln) for ln in window):
            offenders.append(f"{lane}:{i + 1}: {lines[i].strip()}")
    assert not offenders, (
        "these stage site/ with no `git add templates/` alongside, so a re-stamped "
        "templates/ side is left uncommitted and the pair lands diverged:\n  "
        + "\n  ".join(offenders))


@pytest.mark.parametrize("lane", LANES)
def test_templates_staging_cannot_abort_the_commit(lane):
    """The templates/ add must never be able to kill the commit that ships the render.
    A bare `git add … templates/` under `-eo pipefail` exits 128 on a missing pathspec —
    2026-07-26 this reddened three render-lane push-block tests before it could ship."""
    for i, ln in enumerate(_lines(lane)):
        if not re.search(r"^\s*git add [^#|&]*\btemplates/", ln):
            continue
        tolerated = "|| true" in ln or "2>/dev/null" in ln or "&&" in ln
        assert tolerated, (
            f"{lane}:{i + 1} stages templates/ fatally: {ln.strip()!r} — exits 128 when the "
            "pathspec matches nothing and aborts the whole commit step")


@pytest.mark.parametrize("lane", LANES)
def test_post_rebase_block_re_stamps_before_committing(lane):
    """Defect 2: the pushed tree is the POST-rebase tree. A lane that heals after
    `git pull --rebase` must re-stamp there, or pages a sibling lane landed
    mid-run ship un-stamped through a fully green run."""
    lines = _lines(lane)
    # the post-rebase heal block is the `--fix` that sits inside the push loop,
    # i.e. indented deeper than the pre-commit one
    fixes = _idx(lines, FIX)
    post = [i for i in fixes if len(lines[i]) - len(lines[i].lstrip()) >= 14]
    if not post:
        pytest.skip(f"{lane} has no post-rebase heal block (minimal push loop)")
    for f in post:
        window = lines[max(0, f - 12):f]
        assert any(STAMP in ln and not ln.lstrip().startswith("#") for ln in window), (
            f"{lane}:{f + 1} heals post-rebase without re-stamping first — a page a sibling "
            "lane landed mid-run would be pushed un-stamped (render 6260e5ac8c0)")


@pytest.mark.parametrize("lane", LANES)
def test_stamp_failure_is_annotated_not_silently_swallowed(lane):
    """The sweep is deliberately non-blocking (`|| …`) so a failure cannot block the
    commit that ships the render — but a bare `echo` made stamp staleness invisible
    in a green run. Keep it non-blocking AND visible."""
    for i in _idx(_lines(lane), STAMP):
        ln = _lines(lane)[i]
        if "||" not in ln:
            continue
        assert "::warning::" in ln, (
            f"{lane}:{i + 1} swallows a stamping failure into a green run without a "
            "::warning:: annotation")
