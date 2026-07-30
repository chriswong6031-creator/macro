"""Regression checks for the start-page intelligence surface and its voice."""
from __future__ import annotations

import re
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent


def test_start_page_ships_the_intelligence_surface():
    html = (ROOT / "site" / "start.html").read_text(encoding="utf-8")
    assert 'class="hub-intel-shell"' in html
    assert "Market read" in html
    assert "市场解读" in html

    match = re.search(r'href="(assets/css/[a-f0-9]+\.css)\?v=', html)
    assert match, "start.html must reference its externalized page CSS"
    css = (ROOT / "site" / match.group(1)).read_text(encoding="utf-8")
    assert ".hub-intel-shell" in css
    assert ".hub-greet.is-speaking" in css
    assert "@media(prefers-reduced-motion:reduce)" in css


def test_welcome_voice_retired_the_awkward_lines():
    js = (ROOT / "site" / "hub-welcome.js").read_text(encoding="utf-8")
    for retired in (
        "When you watch this closely, so do I",
        "{V}th",
        "Give the decision-making part of your brain the day off",
        "只说准话",
        "负责做决定的那部分脑子",
    ):
        assert retired not in js

    assert "I've done the first pass. Here's what matters." in js
    assert "盘面我先过了一遍。先看最重要的。" in js
    assert "document.addEventListener('langchange'" in js
