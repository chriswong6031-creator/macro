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


def test_render_lanes_recheck_assets_after_porcelain_rebase_before_push() -> None:
    for lane in LANES:
        text = _text(lane)
        rebase = text.index("git pull --rebase --autostash -X theirs origin main")
        post_rebase = text[rebase:]
        guard = post_rebase.index("python3 scripts/check_site_asset_refs.py site")
        push = post_rebase.index("if push_do")

        assert guard < push, lane
