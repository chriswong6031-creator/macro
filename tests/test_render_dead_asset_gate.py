"""Render publication must fail closed on dangling content-addressed assets.

Run 30705845154 proved two separate gaps: engine-render published after its
dead-reference guard failed, and its post-rebase tree was never checked.  Keep
the generated crypto repair and both render-lane publication fences pinned.
"""

from __future__ import annotations

import hashlib
from pathlib import Path
import re


ROOT = Path(__file__).resolve().parents[1]
LANES = (
    ROOT / ".github" / "workflows" / "render.yml",
    ROOT / ".github" / "workflows" / "engine-render.yml",
)


def _text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _porcelain_rebase_at(lane: Path, text: str) -> int:
    """Return the publication rebase after asserting its lane-specific contract."""
    if lane.name == "render.yml":
        rebase = text.index("git rebase --autostash -X theirs origin/main")
        assert text.index("push_fetch_main_for_rebase") < rebase
        return rebase
    return text.index("git pull --rebase --autostash -X theirs origin main")


#: The dangling reference the incident actually published: site/crypto.html
#: pointed at assets/css/94a4f2e3.css, which no longer existed, so the page
#: shipped unstyled.  Human-reviewed and incident-specific — no lane can move it,
#: and it is what keeps the derived clauses below from being satisfied by just any
#: resolving reference.
_INCIDENT_DEAD_CSS = "94a4f2e3.css"

_CONTENT_ADDRESSED_CSS = re.compile(r'href="assets/css/([0-9a-f]{8})\.css\?v=\1"')


def test_crypto_page_restores_current_house_style_asset_contract() -> None:
    """The page's content-addressed stylesheet must RESOLVE.  The hash is weather.

    Pinning the hash re-armed the very bomb this fence exists to catch, one axis
    over.  A content-addressed name changes by construction whenever the bundle
    body does, so ``ab184288`` was only ever the name of one night's build: the
    2026-08-13 ``scope=all`` re-render (eb90d4ff945 — the backlog flush after a
    stale ``index.lock`` had frozen every render for seven hours) deleted
    ``ab184288.css`` and published ``54cf9bc6.css`` in the same commit.  This case
    then went red against a site with NO dead reference at all:
    ``scripts/check_site_asset_refs.py site`` — the guard the other cases in this
    file require the render lanes to run BEFORE they commit — reports every
    template-decided href under ``site/`` resolving, 0 gaps.

    So assert what the incident was about and let the hash move: the page carries a
    content-addressed stylesheet, its file EXISTS, its name is its own content
    digest (a stale body served under a fresh name is the same defect wearing a
    different hash), the ``?v=`` stamp matches the name it busts, and the dangling
    reference from the incident never comes back.
    """

    page = _text(ROOT / "site" / "crypto.html")

    assert _INCIDENT_DEAD_CSS not in page
    digests = _CONTENT_ADDRESSED_CSS.findall(page)
    # Anti-vacuity: a page that lost its stylesheet altogether would satisfy every
    # clause below by having nothing left to check.
    assert digests, (
        "site/crypto.html carries no content-addressed stylesheet at all — the "
        "house-style asset contract this fence guards is gone, not merely re-hashed"
    )
    for digest in digests:
        css = ROOT / "site" / "assets" / "css" / f"{digest}.css"
        assert css.is_file(), (
            f"crypto.html references a dangling stylesheet: {css.name} is not on "
            "disk — this is the incident, not a re-hash"
        )
        assert hashlib.sha256(css.read_bytes()).hexdigest().startswith(digest), (
            f"{css.name} is not its own content digest — a content-addressed URL "
            "that does not address its content cannot be cache-busted"
        )


def test_render_lanes_guard_the_finalized_tree_before_commit() -> None:
    for lane in LANES:
        text = _text(lane)
        normalize = text.index("- name: inject data-base shim")
        final_guard = text.index("- name: guard — finalized site has no dead references")
        commit = text.index("- name: commit rendered site")

        assert normalize < final_guard < commit, lane
        guard_block = text[final_guard:commit]
        assert "python3 scripts/check_site_asset_refs.py site" in guard_block, lane


def test_engine_render_never_commits_after_a_failed_guard() -> None:
    text = _text(ROOT / ".github" / "workflows" / "engine-render.yml")
    commit = text.index("- name: commit rendered site")
    commit_header = text[commit : commit + 260]

    assert re.search(r"\n\s+if: \$\{\{ success\(\) \}\}", commit_header)
    assert "if: always()" not in commit_header


def test_render_lanes_guard_both_possible_porcelain_push_heads() -> None:
    for lane in LANES:
        text = _text(lane)
        rebase = _porcelain_rebase_at(lane, text)
        post_rebase = text[rebase:]
        guards = [
            match.start()
            for match in re.finditer(
                "python3 scripts/check_site_asset_refs.py site", post_rebase
            )
        ]
        first_mutator = post_rebase.index("python -m scripts.optimize_assets")
        push = post_rebase.index("if push_do")

        assert len(guards) >= 2, lane
        assert guards[0] < first_mutator < guards[1] < push, lane


def test_render_lanes_recheck_the_healed_tree_immediately_before_commit() -> None:
    commit_commands = {
        "render.yml": 'commit_index "$RENDER_MESSAGE"',
        "engine-render.yml": 'git commit -m "engine-render:',
    }
    for lane in LANES:
        text = _text(lane)
        step = text.index("- name: commit rendered site")
        block = text[step:]
        healed = block.index("push_staged_heal site/ templates/ || exit 1")
        final_guard = block.index("python3 scripts/check_site_asset_refs.py site", healed)
        commit = block.index(commit_commands[lane.name], final_guard)

        assert healed < final_guard < commit, lane


def test_render_metadata_replay_is_code_data_only() -> None:
    text = _text(ROOT / ".github" / "workflows" / "render.yml")
    replay = text.index("PUBLISH_COMMIT=$(push_metadata_replay_commit")
    gate = text.rfind(
        'git diff --quiet "$RENDER_PARENT" origin/main -- site/ templates/',
        0,
        replay,
    )

    assert gate != -1
    assert replay - gate < 240


def test_engine_render_owns_the_crypto_emitter_in_every_hub_scope() -> None:
    workflow = _text(ROOT / ".github" / "workflows" / "engine-render.yml")
    assert "crypto() {" in workflow
    assert "scripts.build_crypto" in workflow

    case_body = workflow.split('case "$SCOPE" in', 1)[1].split("esac", 1)[0]
    assert len(re.findall(r"\bhub\s*;\s*crypto\b", case_body)) == 8
    assert not re.search(r"\bhub\s*;(?!\s*crypto\b)", case_body)

    dag = _text(ROOT / "config" / "dag.yml")
    engine_lane = dag.split(
        "- workflow: .github/workflows/engine-render.yml", 1
    )[1].split("- workflow:", 1)[0]
    assert "module: scripts.build_crypto" in engine_lane
