"""Regression checks for the start-page intelligence surface and its voice."""
from __future__ import annotations

import re
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent


def test_builder_renders_the_floating_intelligence_surface():
    builder = (ROOT / "scripts" / "build_vector.py").read_text(encoding="utf-8")
    assert '<div class="hub-intel-message"><span class="greet-tx"></span>' in builder
    assert "hub-intel-meta" not in builder
    assert "hub-intel-foot" not in builder

    match = re.search(r'_GLOBE_HUB_CSS = r?"""<style>(.*?)</style>"""', builder, re.DOTALL)
    assert match, "build_vector must carry the hub page CSS"
    css = match.group(1)
    assert ".hub-intel-shell" in css
    assert ".hub-greet.is-speaking" in css
    assert "-webkit-backdrop-filter:blur(18px)" in css
    assert "-webkit-mask-image:radial-gradient" in css
    assert ".hub-intel-meta" not in css
    assert ".hub-intel-foot" not in css
    shell_rule = re.search(r"\.hub-intel-shell\{([^}]+)\}", css)
    assert shell_rule
    assert "display:flex" in shell_rule.group(1)
    assert "border:" not in shell_rule.group(1)
    assert "background:" not in shell_rule.group(1)
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


def test_welcome_cannot_be_interrupted_and_holds_the_last_thought():
    js = (ROOT / "site" / "hub-welcome.js").read_text(encoding="utf-8")
    assert "var LINE_HOLD_MIN_MS = 3000;" in js
    assert "var FINAL_HOLD_MS = 6500;" in js
    assert "var BRAND_HANDOFF_MS = 900;" in js
    assert "li === lines.length - 1" in js
    assert "wait(BRAND_HANDOFF_MS, finish)" in js
    assert "function onSkip" not in js
    assert "var skip =" not in js
    assert "document.addEventListener('click', onSkip" not in js
