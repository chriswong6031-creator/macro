"""Guard: the verdict-keyed Tier-1 copy mirrored into site/risk_state_live.js must
stay in lockstep with its sources of truth — engine/market_state.py _HEADLINES and
the dashboard.html.j2 sub-line / What-To-Do vocab. The live patcher rewrites those
nodes on every intraday tick; silent drift here would put wrong stance words on the
glance tier (the exact bug class this file exists to prevent, 2026-07-13).

Stdlib-only on purpose: the engine dict is read via ast (no engine import, no pandas).
"""
from __future__ import annotations

import ast
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ENGINE = ROOT / "engine" / "market_state.py"
LIVE_JS = ROOT / "site" / "risk_state_live.js"
LIVE_JS_TPL = ROOT / "templates" / "risk_state_live.js"
DASH = ROOT / "templates" / "dashboard.html.j2"

VERDICTS = ("RISK_ON", "MIXED", "RISK_OFF")


def _engine_headlines() -> dict[str, tuple[str, str]]:
    tree = ast.parse(ENGINE.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign):
            for tgt in node.targets:
                if isinstance(tgt, ast.Name) and tgt.id == "_HEADLINES":
                    return ast.literal_eval(node.value)
    raise AssertionError("_HEADLINES dict not found in engine/market_state.py")


def _js_map(js: str, name: str) -> dict[str, tuple[str, str]]:
    block = re.search(rf"var {name} = \{{(.*?)\n  \}};", js, re.S)
    assert block, f"var {name} block not found in risk_state_live.js"
    out: dict[str, tuple[str, str]] = {}
    for verdict, en, zh in re.findall(
        r'(RISK_ON|MIXED|RISK_OFF): \["(.*?)",\s*"(.*?)"\]', block.group(1), re.S
    ):
        out[verdict] = (en, zh)
    assert set(out) == set(VERDICTS), f"{name} must carry exactly {VERDICTS}"
    return out


def test_js_headlines_mirror_engine():
    js = LIVE_JS.read_text(encoding="utf-8")
    engine = _engine_headlines()
    mirrored = _js_map(js, "HEADLINE")
    for v in VERDICTS:
        assert mirrored[v] == tuple(engine[v]), (
            f"HEADLINE[{v}] in risk_state_live.js drifted from engine _HEADLINES"
        )


def test_js_vocab_present_in_dashboard_template():
    """SUBLINE / ACTION strings are baked inline in dashboard.html.j2 — every JS
    mirror string must literally appear there (presence check; the template is
    Jinja so a structural parse would be brittle)."""
    js = LIVE_JS.read_text(encoding="utf-8")
    dash = DASH.read_text(encoding="utf-8")
    for name in ("SUBLINE", "ACTION"):
        for v, (en, zh) in _js_map(js, name).items():
            for s in (en, zh):
                # accept the literal, the &mdash;-entity form, or (the template builds
                # the EN sub-line from two Jinja maps joined by &mdash;) every dash-
                # separated part appearing on its own
                ok = (
                    s in dash
                    or s.replace(" — ", " &mdash; ") in dash
                    or all(part in dash for part in s.split(" — "))
                )
                assert ok, f"{name}[{v}] string not found in dashboard.html.j2: {s!r}"


def test_paired_template_copy_identical():
    assert LIVE_JS.read_bytes() == LIVE_JS_TPL.read_bytes(), (
        "templates/risk_state_live.js and site/risk_state_live.js must be byte-identical "
        "(run: python -m scripts.check_template_site_sync --fix)"
    )
