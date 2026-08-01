"""Regression guards for the signed-in start page publish path.

The 2026-08-01 render race committed an autostash conflict literally into
``site/start.html``. Browsers executed both conflict sides, starting two globe and
sky animation loops on the same canvases. These checks keep the shipped runtime
single-instance and make every lane that writes the page fail closed before push.
"""
from __future__ import annotations

import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
START = ROOT / "site" / "start.html"
WORKFLOWS = ROOT / ".github" / "workflows"


def _script_basenames(html: str) -> list[str]:
    srcs = re.findall(r'<script\b[^>]*\bsrc=["\']([^"\']+)["\']', html)
    return [src.split("?", 1)[0].rsplit("/", 1)[-1] for src in srcs]


def test_committed_start_has_one_copy_of_each_runtime() -> None:
    html = START.read_text(encoding="utf-8")
    assert "<<<<<<< " not in html
    assert ">>>>>>> " not in html

    scripts = _script_basenames(html)
    for asset in (
        "globe-deck.js",
        "sky.js",
        "hub-welcome.js",
        "live_config.js",
        "live.js",
        "wh_banner.js",
    ):
        assert scripts.count(asset) == 1, f"start.html loads {asset} {scripts.count(asset)} times"


def test_animation_runtimes_are_idempotent() -> None:
    guards = {
        "site/globe-deck.js": "window.__gdDeckInit",
        "site/sky.js": "window.__skyDeckInit",
        "site/hub-welcome.js": "window.__hubWelcomeInit",
    }
    for relative, marker in guards.items():
        assert marker in (ROOT / relative).read_text(encoding="utf-8"), relative


def test_start_builder_does_not_reload_nav_live_runtime() -> None:
    source = (ROOT / "scripts" / "build_vector.py").read_text(encoding="utf-8")
    hub = source[source.index("def _hub_html("):source.index("\ndef ", source.index("def _hub_html(") + 1)]
    assert '<script src="live_config.js"></script>' not in hub
    assert '<script src="live.js"></script>' not in hub
    assert hub.count('data-whb data-root="" src="wh_banner.js"') == 1


def test_start_writing_lanes_guard_before_commit_and_after_rebase() -> None:
    guard = "python3 scripts/check_conflict_markers.py --file site/start.html"
    sync = "python -m scripts.check_template_site_sync --fix"
    for lane in ("render.yml", "engine-render.yml", "daily.yml"):
        text = (WORKFLOWS / lane).read_text(encoding="utf-8")
        assert text.count(guard) >= 2, f"{lane} lacks pre-commit and post-rebase marker gates"
        for match in re.finditer(re.escape(sync), text):
            next_guard = text.find(guard, match.end())
            boundaries = [
                pos for token in ("git add site/", "if ! git diff --quiet", "if push_do")
                if (pos := text.find(token, match.end())) >= 0
            ]
            assert boundaries and match.end() < next_guard < min(boundaries), (
                f"{lane} can stage or push after a sync without rerunning the conflict-marker gate"
            )


def test_pr_marker_gate_ratchets_from_the_base_branch() -> None:
    manifest = (ROOT / ".github" / "ci" / "legacy-jobs.yml").read_text(encoding="utf-8")
    assert 'check_conflict_markers.py --changed-from "origin/${CI_BASE_REF:-main}"' in manifest
