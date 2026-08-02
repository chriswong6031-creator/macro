"""tests/test_regime_sizing_disclosure_parity.py — the sizing pill's null disclosure must be
identical on all five basket pages.

`renderRegimeSizing()` exists TWICE and cannot be collapsed into one function: the US flagship
(`templates/baskets.html.j2`) is hand-authored and loads no `baskets_desk.js`, while the four
regional pages (china / hk / canada / intl) load the shared `templates/baskets_desk.js` and carry
no inline copy. That is a real structural fork, so it needs a guard instead of a refactor — the
fork previously drifted, shipping the regime-caution null disclosure on the US page only.

What is pinned:

  - the two implementations emit BYTE-IDENTICAL HTML for the same payload, across a matrix
    covering calm / vol-target-only / warning / backwardation-stress / gate-open;
  - the null disclosure actually fires when the caution gate is closed and the shadow bites
    (the state the live gate is in), in BOTH languages;
  - it does NOT fire when the gate is open (the caution is then applied to gross, so there is
    nothing being withheld to disclose);
  - the copy names WHOSE volatility is being read. `regime_sizing` is a single global snapshot
    (CBOE VIX complex) stamped onto every market page — `engine/theme_scoring.py` calls
    `vol_regime.published_snapshot()` with no region argument — so an unattributed "volatility
    target 75%" on an A-share page asserts a reading of A-share volatility that was never taken.

Both functions are extracted from source and executed under `node`, so the test sees what the
browser sees; a mis-extraction fails loudly on a syntax error rather than passing vacuously.
Node is available on the CI runners and dev Macs; the suite skips loudly when it is not
(mirrors tests/test_risk_core_js.py).
"""
from __future__ import annotations

import json
import shutil
import subprocess
import textwrap
from pathlib import Path

import pytest

HAS_NODE = shutil.which("node") is not None
needs_node = pytest.mark.skipif(not HAS_NODE, reason="node not on PATH")

ROOT = Path(__file__).resolve().parents[1]
US_SRC = ROOT / "templates" / "baskets.html.j2"
DESK_SRC = ROOT / "templates" / "baskets_desk.js"

FN = "function renderRegimeSizing(){"


def _extract(path: Path) -> str:
    """Pull the whole `function renderRegimeSizing(){...}` text out of a source file by brace
    matching. Raises (never returns a partial) so a failed extraction cannot pass silently."""
    src = path.read_text(encoding="utf-8")
    i = src.find(FN)
    assert i != -1, f"{path.name}: renderRegimeSizing() not found"
    assert src.find(FN, i + 1) == -1, f"{path.name}: more than one renderRegimeSizing()"
    depth, j = 0, src.index("{", i)
    for k in range(j, len(src)):
        if src[k] == "{":
            depth += 1
        elif src[k] == "}":
            depth -= 1
            if depth == 0:
                return src[i:k + 1]
    raise AssertionError(f"{path.name}: unbalanced braces in renderRegimeSizing()")


# The shared harness: the real `esc` (both files escape & < > "), an `L` that keeps BOTH
# languages so a divergence in either is visible, and the payload injected as THEME.
HARNESS = """
var esc = function(s){ return (s==null?'':String(s)).replace(/[&<>"]/g, function(c){
  return {'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]; }); };
var L = function(en, zh){ return '<EN>' + en + '</EN><ZH>' + zh + '</ZH>'; };
var THEME = %(theme)s;
%(fn)s
process.stdout.write(JSON.stringify({html: renderRegimeSizing()}));
"""


def _render(fn_src: str, theme: dict) -> str:
    script = HARNESS % {"theme": json.dumps(theme), "fn": fn_src}
    p = subprocess.run(["node", "-e", script], capture_output=True, text=True, timeout=60)
    assert p.returncode == 0, f"node failed: {p.stderr.strip()}"
    return json.loads(p.stdout)["html"]


def _theme(**rs) -> dict:
    """A regime_sizing payload shaped like engine/vol_regime.sizing_overlay's v2 output."""
    base = {
        "schema": "vol_regime.sizing.v2",
        "gross_scalar": 1.0, "mech_scalar": 1.0, "regime_caution": 1.0,
        "regime_caution_shadow": 1.0, "caution_scored": False, "scored_cut": 1.0,
        "regime": None, "scored_active": False, "active": False,
        "caution_passport": {
            "basis": "measured", "verdict": "display-only",
            "validation": {"regime_marginal_over_voltarget": False,
                           "live_overlay_helps": False, "asof": "2026-06-21"},
        },
    }
    base.update(rs)
    return {"regime_sizing": base, "themes": []}


# --- the payload matrix -------------------------------------------------------------------
# `calm` is the inert case; `live` mirrors the state actually shipping today (regime
# "normalizing", vol-target biting, shadow 1.0 -> no note); `warning` / `stress` are the two
# states that open the shadow; `gate_open` is the counterfactual where the caution binds gross.
CASES = {
    "calm": _theme(active=False, gross_scalar=1.0),
    "live": _theme(active=True, gross_scalar=0.75, mech_scalar=0.75, regime="normalizing"),
    "warning": _theme(active=True, gross_scalar=0.75, mech_scalar=0.75,
                      regime="warning", regime_caution_shadow=0.85),
    "stress": _theme(active=True, gross_scalar=0.70, mech_scalar=0.70,
                     regime="backwardation-stress", regime_caution_shadow=0.70),
    "gate_open": _theme(
        active=True, gross_scalar=0.49, mech_scalar=0.70, regime_caution=0.70,
        regime="backwardation-stress", regime_caution_shadow=0.70, caution_scored=True,
        caution_passport={"basis": "measured", "verdict": "scored",
                          "validation": {"regime_marginal_over_voltarget": True,
                                         "live_overlay_helps": True, "asof": "2026-06-21"}}),
}


@pytest.fixture(scope="module")
def fns() -> tuple[str, str]:
    us, desk = _extract(US_SRC), _extract(DESK_SRC)
    # non-vacuity: a truncated or empty extraction must not be able to pass the parity check
    assert len(us) > 800 and len(desk) > 800, "extraction looks truncated"
    return us, desk


@needs_node
@pytest.mark.parametrize("case", sorted(CASES))
def test_us_and_shared_renderers_emit_identical_html(fns, case):
    """The US inline copy and the shared desk renderer are byte-identical per payload."""
    us_fn, desk_fn = fns
    us = _render(us_fn, CASES[case])
    desk = _render(desk_fn, CASES[case])
    assert us == desk, f"[{case}] US page and shared desk renderer diverged:\n{us}\n!=\n{desk}"


@needs_node
def test_calm_renders_nothing(fns):
    """Subtract-only: no pill at all when the overlay is inert (no '100% — calm' noise)."""
    for fn in fns:
        assert _render(fn, CASES["calm"]) == ""


@needs_node
@pytest.mark.parametrize("case", ["warning", "stress"])
def test_withheld_caution_is_disclosed_in_both_languages(fns, case):
    """House epistemics: a layer computed but NOT applied is printed, not hidden.

    The disclosure must say it is not acting (the null), and must not overclaim the evidence —
    the gate behind it was measured on US books only, so the scope lives in the Tier-2 receipt.
    """
    shadow = int(round(CASES[case]["regime_sizing"]["regime_caution_shadow"] * 100))
    for fn in fns:
        html = _render(fn, CASES[case])
        assert f"×{shadow}% caution" in html, "the withheld amount must be stated"
        assert "does NOT reduce your positions" in html, "EN null disclosure missing"
        assert "不会减少您的仓位" in html, "ZH null disclosure missing"
        assert "no measured edge" in html, "EN must not imply the layer earned its place"
        assert "没有可测的优势" in html, "ZH must not imply the layer earned its place"
        # scope of the evidence belongs on the Tier-2 receipt, not the tip body
        assert "data-tip-rc-en=" in html and "data-tip-rc-zh=" in html, "receipt missing"
        assert "US books only" in html and "仅基于美国标的" in html, "gate scope unstated"
        assert "asof 2026-06-21" in html, "receipt must carry the gate's asof from the payload"


@needs_node
def test_no_disclosure_when_the_caution_actually_binds(fns):
    """When the gate is OPEN the caution IS applied to gross — there is no withheld layer, so
    the 'shown for awareness only' note would be a false statement."""
    for fn in fns:
        html = _render(fn, CASES["gate_open"])
        assert "does NOT reduce your positions" not in html
        assert "不会减少您的仓位" not in html
        assert "data-tip-rc-en=" not in html


@needs_node
@pytest.mark.parametrize("case", ["live", "warning", "stress"])
def test_sizing_read_is_attributed_to_its_source_market(fns, case):
    """`regime_sizing` is ONE global US-derived snapshot stamped onto all five market pages
    (engine/theme_scoring.py -> vol_regime.published_snapshot(), no region argument). Whenever
    the pill renders it must say whose volatility it is reading, or a reader on the china / hk /
    canada / intl page takes 'volatility target 75%' as a reading of their own market."""
    for fn in fns:
        html = _render(fn, CASES[case])
        assert "Read from US volatility" in html, "EN source attribution missing"
        assert "依据美国波动率读数" in html, "ZH source attribution missing"


@needs_node
def test_parity_check_can_see_a_divergence(fns):
    """Mutation control: the comparison above must actually fail when the two copies differ.

    Without this, an extraction bug that returned the same text twice would make every parity
    assertion vacuously true."""
    us_fn, _ = fns
    mutated = us_fn.replace("does NOT reduce your positions", "does not reduce your positions")
    assert mutated != us_fn, "mutation control did not apply — the sentinel copy moved"
    assert _render(us_fn, CASES["stress"]) != _render(mutated, CASES["stress"])
