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


def test_crypto_page_restores_current_house_style_asset_contract() -> None:
    page = _text(ROOT / "site" / "crypto.html")
    css = ROOT / "site" / "assets" / "css" / "ab184288.css"

    assert 'href="assets/css/ab184288.css?v=ab184288"' in page
    assert "94a4f2e3.css" not in page
    assert css.is_file()
    assert hashlib.sha256(css.read_bytes()).hexdigest() == (
        "ab1842887865b3dba40cc9c760f0816f92de604effe39da72f9289a042e00e8c"
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
        rebase = text.index("git pull --rebase --autostash -X theirs origin main")
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
