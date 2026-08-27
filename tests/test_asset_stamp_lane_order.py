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

from scripts.workflow_run_source import resolved_workflow_text  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
WORKFLOWS = ROOT / ".github/workflows"

STAMP = "python -m scripts.optimize_assets"
FIX = "python -m scripts.check_template_site_sync --fix"
EXTERNALIZE = "python -m scripts.externalize_css"
SHIM = "python -m scripts.inject_data_base"

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
    # 512KB-cap diet: some daily.yml bodies live in scripts/ci/ — splice them
    # back IN PLACE so index/order assertions keep their pre-extraction meaning.
    return resolved_workflow_text(WORKFLOWS / name, ROOT).splitlines()


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
def test_post_rebase_block_runs_the_full_normalize_chain(lane):
    """P0 2026-08-04 (9a997e9da3f): the nightly hit its 200m cap; the cancel skipped
    the success()-gated normalize step while the always() commit still shipped 5,895
    raw pages. Every later lane REBASED onto that main: its own re-render matched its
    healthy checkout, so the replay merged its small deltas cleanly INTO the fat
    inline pages (no conflict — -X theirs never engaged), and a re-stamp-only heal
    pushed the poison onward re-stamped (f0deeabde39, 0159fe97631) until #4484 healed
    main by hand. A post-rebase heal that re-stamps must therefore also re-shim and
    re-externalize — the full chain makes the next lane push self-heal the tree."""
    lines = _lines(lane)
    stamps = _idx(lines, STAMP)
    post = [i for i in stamps if len(lines[i]) - len(lines[i].lstrip()) >= 14]
    if not post:
        pytest.skip(f"{lane} has no post-rebase heal block (minimal push loop)")
    for s in post:
        window = lines[max(0, s - 12):s]
        for needle, label in ((SHIM, "re-shim"), (EXTERNALIZE, "re-externalize")):
            assert any(needle in ln and not ln.lstrip().startswith("#")
                       for ln in window), (
                f"{lane}:{s + 1} re-stamps post-rebase without a {label} (`{needle}`) "
                "in the same heal block — a raw page inherited from main would be "
                "re-stamped and pushed onward still un-normalized (9a997e9da3f)")


# Lanes whose engine commit runs `if: always()` — it commits even when a
# timeout-cancel skipped every success()-gated step, including the lane's
# normalize pass, so the commit step itself must normalize what it stages.
ALWAYS_COMMIT_LANES = ["daily.yml", "asia-close.yml"]


@pytest.mark.parametrize("lane", ALWAYS_COMMIT_LANES)
def test_always_commit_step_normalizes_inside_the_step(lane):
    """P0 2026-08-04: daily's engine job was cancelled at its 200m cap mid-run; the
    White House step (the job's ONLY shim/externalize/stamp pass) was skipped as
    success()-gated, and the always() `commit engine outputs` step committed the raw
    tree as 9a997e9da3f — 7 shipped-page guards red on every PR head in the repo.
    The normalize chain must live INSIDE the always() step, between its start and
    its authoritative commit boundary, so the staged tree is normalized by
    construction. Daily uses the locked exact-tree helper; asia-close still uses
    porcelain `git commit`."""
    lines = _lines(lane)
    starts = [i for i, ln in enumerate(lines) if "- name: commit engine outputs" in ln]
    assert starts, f"{lane}: 'commit engine outputs' step not found — did the step get renamed?"
    start = starts[0]
    commit_markers = (
        'git commit -m "engine:',
        "options_signal_nightly.sh commit-broad-candidate",
    )
    commits = [
        i
        for i in range(start, len(lines))
        if any(marker in lines[i] for marker in commit_markers)
    ]
    assert commits, f"{lane}: no authoritative engine commit after the commit step start"
    body = lines[start:commits[0]]
    for needle in (SHIM, EXTERNALIZE, STAMP):
        assert any(needle in ln and not ln.lstrip().startswith("#") for ln in body), (
            f"{lane}: the always() commit step no longer runs `{needle}` before its "
            "the authoritative commit — a timeout-cancel that skips the normalize step would ship "
            "a raw tree to main again (9a997e9da3f)")


# ---------------------------------------------------------------------------
# NARROW publishing lanes (the #4492 follow-up).
#
# #4492 fixed the seven render lanes above — every one of them stages `site/`
# broadly and now normalizes what it commits. The audit that followed found six
# MORE workflows that stage site/ HTML and ran no externalize_css anywhere in the
# file. They are a different shape: each stages a FEW explicit paths, not the
# tree, so the render lanes' contracts (broad `site/` add, templates/ add,
# post-rebase heal block) do not apply and they get their own gates here.
#
# site/stocks/earnings is the one that could not self-heal: it is in NO render
# lane's rebuild scope, so unlike the nightly's 5,895 pages nothing ever re-baked
# it. Its 444 pages carried ~25KB of inline <style> each with no
# assets/css/<hash>.css ref from the launch (#4298) until this fix — 527 commits.
# The other five publish to pages a later full-tree render DOES re-bake, so their
# exposure is one render window rather than forever.
#
# Value maps the lane to the HTML pathspec whose staging the chain must precede.
NARROW_HTML_LANES = {
    "earnings-public-wire.yml": "site/stocks/earnings",
    "commodity-sentinel.yml": "site/commodities.html",
    "press-publish.yml": "site/blog",
    "sentinel.yml": "site/vector.html",
    "special-sits-backfill.yml": "site/special_situations.html",
    "whitehouse-sentinel.yml": "site/whitehouse.html",
}

# `git add …` up to the first comment/pipe/&& — the same slicing the staging
# tests above use, so a trailing `2>/dev/null || true` never becomes a pathspec.
_GIT_ADD_RE = re.compile(r"^\s*git add\b(?P<args>[^#|&]*)")
_STEP_START_RE = re.compile(r"^\s*-\s+(name|run|uses):")


def _staged_paths(lines: list[str], prefix: str = "site/") -> dict[str, int]:
    """{pathspec: first line index that stages it} for every `git add` in the file."""
    out: dict[str, int] = {}
    for i, ln in enumerate(lines):
        if ln.lstrip().startswith("#"):
            continue
        m = _GIT_ADD_RE.match(ln)
        if not m:
            continue
        for tok in m.group("args").split():
            if tok.startswith("-") or not tok.startswith(prefix):
                continue  # flags, redirections, non-site pathspecs
            out.setdefault(tok.rstrip("/"), i)
    return out


def _step_start(lines: list[str], i: int) -> int:
    """Index of the step header enclosing line i (-1 when none precedes it)."""
    for j in range(i, -1, -1):
        if _STEP_START_RE.match(lines[j]):
            return j
    return -1


@pytest.mark.parametrize("lane", sorted(NARROW_HTML_LANES))
def test_narrow_lane_normalizes_inside_the_step_that_stages_html(lane):
    """A lane that commits site/ HTML without shim → externalize → stamp publishes a
    RAW page: inline <style>, no assets/css/<hash>.css ref, stale `?v=`. The chain
    must run INSIDE the committing step and BEFORE the `git add`, in that order —
    externalize rewrites the page the stamp then has to see, and both have to have
    happened before the tree is staged (the #4492 contract, applied to the lanes
    that fix missed)."""
    lines = _lines(lane)
    html_path = NARROW_HTML_LANES[lane]
    staged = _staged_paths(lines)
    assert html_path in staged, (
        f"{lane} no longer stages {html_path} — did the commit step change? Re-point "
        "NARROW_HTML_LANES at the path it stages now, or drop the lane if it stopped "
        "publishing HTML.")
    add = staged[html_path]
    step = _step_start(lines, add)
    prev = -1
    for needle, label in ((SHIM, "shim"), (EXTERNALIZE, "externalize"), (STAMP, "stamp")):
        runs = [i for i in _idx(lines, needle) if step < i < add]
        assert runs, (
            f"{lane}:{add + 1} stages {html_path} with no `{needle}` between the step "
            f"header ({step + 1}) and the add — the page ships un-normalized "
            "(9a997e9da3f). Run the chain inside the committing step, before staging.")
        assert runs[-1] > prev, (
            f"{lane}: the normalize chain is out of order — `{needle}` must run after "
            f"the {label}'s predecessor (shim → externalize → stamp)")
        prev = runs[-1]


@pytest.mark.parametrize("lane", sorted(NARROW_HTML_LANES))
def test_narrow_lane_stages_the_hash_assets_its_pages_link(lane):
    """externalize_css lifts each page's inline CSS into a content-hashed
    site/assets/css/<hash>.css and rewrites the page to <link> it. These lanes stage
    explicit paths, not the tree — so staging the page WITHOUT the asset commits a
    link to a file that was never committed: a 404 stylesheet, strictly worse than
    the inline block it replaced. Whoever adds the chain has to widen the staging
    with it."""
    lines = _lines(lane)
    staged = _staged_paths(lines)
    for asset in ("site/assets/css", "site/assets/js"):
        assert asset in staged, (
            f"{lane} runs externalize_css but never stages `{asset}` — a page whose CSS "
            "changed would ship a <link> to a hash file that is not in the commit")


@pytest.mark.parametrize("lane", sorted(NARROW_HTML_LANES))
def test_narrow_lane_never_commits_an_asset_deletion(lane):
    """`--ignore-removal` is load-bearing, not stylistic. _prune_orphans decides
    orphanhood from the pages the sweep can SEE, and a narrow lane's push races the
    render lanes: an asset minted for a page that landed on main mid-run reads as
    unreferenced here and would be staged as a DELETION, 404-ing a page this lane
    never rendered. The render lanes can absorb that because #4492 gave them a
    post-rebase re-externalize that re-mints; these six have no heal block at all.
    So they add and update assets, and never prune — pruning stays with the
    full-tree lanes."""
    for i, ln in enumerate(_lines(lane)):
        if ln.lstrip().startswith("#"):
            continue
        m = _GIT_ADD_RE.match(ln)
        if not m or "site/assets/" not in m.group("args"):
            continue
        assert "--ignore-removal" in m.group("args"), (
            f"{lane}:{i + 1} stages site/assets/ without `--ignore-removal`: "
            f"{ln.strip()!r} — an orphan prune racing a sibling lane's push would "
            "commit the deletion of a stylesheet a live page still links (#3988/#4042)")


def test_earnings_containment_admits_every_path_the_lane_stages():
    """earnings-public-wire refuses to commit outside its redacted estate — a real
    `exit 1`, not a warning. That guard is a hand-written regex sitting next to a
    hand-written staging list, and widening one without the other breaks the lane in
    whichever direction you get wrong: too narrow and every publication dies on the
    containment check (the chain now stages the CSS assets its pages link); too wide
    and the guard stops containing anything. Pin them to each other."""
    lane = "earnings-public-wire.yml"
    lines = _lines(lane)
    pattern = None
    for ln in lines:
        if "diff --cached --name-only" not in ln:
            continue
        m = re.search(r"grep -Ev '([^']+)'", ln)
        if m:
            pattern = m.group(1)
    assert pattern, (
        f"{lane}: the containment check (`git diff --cached --name-only | grep -Ev …`) "
        "is gone — the lane can now commit anywhere in the tree")
    admits = re.compile(pattern)
    for path in sorted(_staged_paths(lines)):
        # what the commit actually carries: a file for a file pathspec, a member for
        # a directory one. grep sees committed FILE paths, never the pathspec.
        sample = path if path.endswith(".html") else f"{path}/sample-file"
        assert admits.search(sample), (
            f"{lane} stages `{path}` but the containment regex /{pattern}/ rejects "
            f"{sample!r} — every run would die on 'refusing to commit outside the "
            "redacted earnings public estate'")
    # …and it must still contain: the paths the guard exists to keep out stay out.
    for forbidden in ("site/index.html", "data/regime/x.json", "templates/index.html",
                      "site/assets/img/logo.png"):
        assert not admits.search(forbidden), (
            f"{lane}: containment regex /{pattern}/ now admits {forbidden!r} — it has "
            "been widened past the earnings estate plus its own hashed CSS/JS")


def _bears_html(pathspec: str) -> bool | None:
    """True/False if the checkout can classify the pathspec; None if it cannot."""
    p = ROOT / pathspec
    if p.is_file():
        return p.suffix == ".html"
    if p.is_dir():
        return any(p.rglob("*.html"))
    return None


def test_every_workflow_that_stages_html_runs_externalize():
    """The standing audit, executable. This is the guard that catches the NEXT lane:
    #4492 fixed six workflows, and six more were still shipping raw pages because
    nothing enforced the rule file-wide. Any workflow that stages a site/ path
    carrying HTML must run externalize_css somewhere in the file.

    Lanes that stage only JSON/config under site/ (btc-live, cortex-retry,
    intraday-fastpath → site/live/*.json, site/live_config.js) have nothing to
    normalize and are excluded by the on-disk classification, not by a hand-kept
    allowlist that would rot."""
    offenders, covered = [], set()
    for wf in sorted(WORKFLOWS.glob("*.yml")):
        lines = _lines(wf.name)
        html = sorted(p for p in _staged_paths(lines) if _bears_html(p))
        if not html:
            continue
        covered.add(wf.name)
        if not _idx(lines, EXTERNALIZE):
            offenders.append(f"{wf.name} stages {html} but never runs `{EXTERNALIZE}`")
    # The classification reads the real tree, so a checkout without site/ would
    # classify nothing and green this gate forever. Pin the lanes it must have seen.
    expected = set(NARROW_HTML_LANES) | {"render.yml", "daily.yml"}
    assert expected <= covered, (
        "this guard went dark — it classified no HTML staging in "
        f"{sorted(expected - covered)}. It reads site/ from the checkout; a partial "
        "tree makes it vacuous rather than red.")
    assert not offenders, (
        "these workflows commit site/ HTML with no CSS externalization, so every page "
        "they publish ships its inline <style> raw and un-stamped (9a997e9da3f):\n  "
        + "\n  ".join(offenders))


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
