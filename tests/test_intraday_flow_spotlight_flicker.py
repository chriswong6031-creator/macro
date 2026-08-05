"""tests/test_intraday_flow_spotlight_flicker.py — the "Look here first" cards must not strobe.

`render()` is called from every fetch completion on the page: quotes (60s), flow pulse
(5min), the options-flow tide, AND once per per-root flow payload — up to 20 of those, each
its own network callback. The `_rendering` flag guards SYNCHRONOUS reentrancy only, so none
of those coalesced: instrumenting the shipped page with a MutationObserver on `#spot-grid`
measured **19 childList writes inside 2.8s of page load, 15 of them byte-identical**.

Each write is `grid.innerHTML = ...`, which destroys and recreates every card node. The CSS
gave `.spot-card` an unconditional `animation:iftRise ... both` — a fade from `opacity:0` —
so every rebuild restarted the entrance. At 30-120ms apart the cards never finished rising
before snapping back to transparent: the operator saw them "flicker 5-6 times really really
fast, then stop", on every refresh.

The fix has two halves and this suite pins both, by EXECUTION rather than by text — the old
code was valid JS producing correct markup, so a string assertion cannot see the defect:

  1. `buildSpotlight` keeps the last markup in `_spotHtml` and skips the DOM write entirely
     when nothing changed. An identical re-render must not touch the grid at all.
  2. The entrance is keyed to card IDENTITY via `.spot-in`, added only to a ticker that was
     not already on screen. A card that is merely UPDATED (same ticker, new price) is an
     update, not an arrival, and must not fade in from zero.

Both pages are checked: `site/intraday_flow.html` is what the VPS serves, and it is rendered
from the template only on the nightly closing-bell lane, so the two can drift for a day.
"""
from __future__ import annotations

import json
import re
import shutil
import subprocess
import sys
import textwrap
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

HAS_NODE = shutil.which("node") is not None
needs_node = pytest.mark.skipif(not HAS_NODE, reason="node not on PATH")

TEMPLATE = ROOT / "templates" / "intraday_flow.html.j2"
SITE = ROOT / "site" / "intraday_flow.html"
CSS_SOURCES = pytest.mark.parametrize(
    "css_path",
    # The template carries its CSS inline; the shipped page has it externalized into a
    # content-hashed bundle by scripts/externalize_css.py. Both must carry the fix.
    [TEMPLATE, None],
    ids=["template-inline", "site-bundle"],
)
PAGES = pytest.mark.parametrize("path", [TEMPLATE, SITE], ids=["template", "site"])


# ═══════════════════════════════════════════════════════════════════════════════
# Extract the spotlight JS and run it against a fake grid
# ═══════════════════════════════════════════════════════════════════════════════

def _region(src: str, start: str, end: str) -> str:
    i = src.index(start)
    return src[i:src.index(end, i)]


# Jinja-free regions. The formatters/helpers spotCard leans on, then the spotlight itself.
# The spotlight region is anchored on the SECTION BANNER, not on the fix's own variables:
# an anchor that only exists after the fix would turn a revert into an extraction crash
# instead of the assertion failure that names the defect.
REGIONS = (
    ("function fmtNum", "function fetchQuotes"),   # fmt*, esc, lz, volumeWords, rangeWords
    ("// ══ SPOTLIGHT", "function buildRow"),      # state + buildSpotlight + spotCard
    ("function prettyBasket", "function dealerCompact"),
)


def _spotlight_js(path: Path) -> str:
    src = path.read_text(encoding="utf-8")
    return "\n".join(_region(src, a, b) for a, b in REGIONS)


def _row(ticker: str, *, stance: str = "get_ready", price: float = 100.0) -> dict:
    """One entry of computeAll()'s output — only the fields spotCard actually reads."""
    return {
        "l": {"ticker": ticker, "baskets": ["mag7"], "entry_signal": {"stop": price * 0.95}},
        "meta": {"lane": "lane-ready" if stance == "get_ready" else "lane-act",
                 "en": "Almost ready", "zh": "即将就绪", "order": 1},
        "st": {"key": stance, "reason_en": "Base in place — waiting for the open.",
               "reason_zh": "底部已成——静候开盘。"},
        "d": None,
        "q": {"price": price, "changePct": 0.5, "lo": price * 0.98},
        "p": {"vol_durability": 0.7},
        "f": {"ncp": -1000.0},
        "conf": {"K": 4},
        "rvol": 1.4,
        "vwapDelta": 0.8,
    }


def _run(path: Path, calls: list[list[dict]]) -> dict:
    """Call buildSpotlight() once per entry in `calls`; report what hit the DOM.

    The fake grid records every innerHTML assignment and the classes added to each card
    afterwards, which is exactly what the browser MutationObserver measured on the real page.
    """
    script = textwrap.dedent(
        """
        var CALLS = %(calls)s;
        var REDUCED_MOTION = false, RVOL_CONFIRM = 1.30, DUR_MIN = 0.60;
        function sessionPhase() { return 'pre'; }   // off-hours: the "bases ready" branch

        var WRITES = [], CLASSES = [];
        function FakeCard(html) {
          this._html = html;
          this.classList = { _l: [], add: function (c) { this._l.push(c); } };
        }
        var grid = {
          _html: '', _cards: [],
          get innerHTML() { return this._html; },
          set innerHTML(v) {
            this._html = v;
            WRITES.push(v);
            // Order matters: buildSpotlight indexes these against its ticker list.
            this._cards = v.split('<article class="spot-card')
                           .slice(1).map(function (h) { return new FakeCard(h); });
          },
          querySelectorAll: function (sel) { return sel === '.spot-card' ? this._cards : []; }
        };
        var note = { innerHTML: '' };
        var document = { getElementById: function (id) {
          return id === 'spot-grid' ? grid : (id === 'spot-note' ? note : null);
        } };

        %(js)s

        CALLS.forEach(function (rows) {
          buildSpotlight(rows, {act: 0, get_ready: rows.length, take_profits: 0});
          CLASSES.push(grid._cards.map(function (c) { return c.classList._l.join(' '); }));
        });
        process.stdout.write(JSON.stringify({
          writes: WRITES.length,
          identical: WRITES.filter(function (w, i) { return i > 0 && WRITES.indexOf(w) < i; }).length,
          classesPerCall: CLASSES,
          finalCards: grid._cards.length
        }));
        """
    ) % {"calls": json.dumps(calls), "js": _spotlight_js(path)}
    res = subprocess.run(["node", "-e", script], capture_output=True, text=True, timeout=30)
    assert res.returncode == 0, f"node failed:\nSTDERR:\n{res.stderr}\nSTDOUT:\n{res.stdout}"
    assert res.stdout.strip(), f"no stdout; stderr:\n{res.stderr}"
    return json.loads(res.stdout)


# ═══════════════════════════════════════════════════════════════════════════════
# 1. An unchanged re-render must not touch the DOM
# ═══════════════════════════════════════════════════════════════════════════════

@needs_node
@PAGES
def test_repeated_identical_renders_write_the_grid_once(path):
    """The measured storm was 19 writes / 15 identical. Only the FIRST may reach the DOM.

    This is the load-bearing half: a write that never happens cannot restart an animation,
    whatever the CSS says.
    """
    rows = [_row("AMZN"), _row("NEE"), _row("SNOW")]
    out = _run(path, [rows, rows, rows, rows, rows, rows])
    assert out["writes"] == 1, (
        f"6 identical renders produced {out['writes']} grid writes — each one recreates "
        "every card node and restarts the entrance animation (the reported flicker)"
    )
    assert out["finalCards"] == 3


@needs_node
@PAGES
def test_an_empty_spotlight_also_settles(path):
    """The no-setups branch writes its own markup and must be guarded the same way —
    off-hours with nothing set up is the state the page sits in for most of the day."""
    out = _run(path, [[], [], []])
    assert out["writes"] == 1, f"empty state rewritten {out['writes']}× — same strobe"


# ═══════════════════════════════════════════════════════════════════════════════
# 2. The entrance belongs to an ARRIVAL, never to an update
# ═══════════════════════════════════════════════════════════════════════════════

@needs_node
@PAGES
def test_a_new_card_gets_the_entrance(path):
    """A ticker that was not on screen is genuinely arriving — it may rise in."""
    out = _run(path, [[_row("AMZN"), _row("NEE")]])
    assert out["classesPerCall"][0] == ["spot-in", "spot-in"], (
        "first paint must animate — a spotlight that never animates is a different defect"
    )


@needs_node
@PAGES
def test_an_updated_card_does_not_re_enter(path):
    """Same ticker, new price: the node is recreated, but this is an update, not an arrival.

    This is the case the 60s quote poll hits all day. Before the fix it replayed the fade.

    Both halves are asserted in ONE run on purpose. `classesPerCall[1] == ["", ""]` alone is
    vacuous — code that never animates anything satisfies it, which is exactly what the
    pre-fix page did (it called classList.add zero times and leaned on the CSS instead). The
    arrival assertion first is what forces this test to distinguish the two.
    """
    out = _run(path, [
        [_row("AMZN", price=100.0), _row("NEE", price=50.0)],
        [_row("AMZN", price=101.2), _row("NEE", price=50.0)],   # AMZN ticked — content differs
    ])
    assert out["writes"] == 2, "the content really did change, so the DOM must be updated"
    assert out["classesPerCall"][0] == ["spot-in", "spot-in"], (
        "arrival must animate — without this the update assertion below is vacuous"
    )
    assert out["classesPerCall"][1] == ["", ""], (
        f"a price tick re-triggered the entrance ({out['classesPerCall'][1]}) — "
        "cards already on screen must swap content without fading from zero"
    )


@needs_node
@PAGES
def test_only_the_newcomer_animates_when_the_pick_changes(path):
    """A card rotating into the spotlight animates; the ones that were already there do not."""
    out = _run(path, [
        [_row("AMZN"), _row("NEE")],
        [_row("AMZN"), _row("SNOW")],   # NEE drops out, SNOW arrives
    ])
    assert out["classesPerCall"][1] == ["", "spot-in"], (
        f"expected only SNOW to enter, got {out['classesPerCall'][1]}"
    )


# ═══════════════════════════════════════════════════════════════════════════════
# 3. The CSS half — a bare .spot-card must carry no entrance
# ═══════════════════════════════════════════════════════════════════════════════

def _page_css(path: Path | None) -> str:
    """The template's inline CSS, or the shipped page's externalized bundle."""
    if path is not None:
        return path.read_text(encoding="utf-8")
    site = SITE.read_text(encoding="utf-8")
    hits = re.findall(r'href="(assets/css/[^"?]+\.css)', site)
    assert hits, "site/intraday_flow.html no longer links an externalized CSS bundle"
    bundle = ROOT / "site" / hits[0]
    assert bundle.is_file(), f"linked bundle missing: {bundle}"
    return bundle.read_text(encoding="utf-8")


@CSS_SOURCES
def test_the_entrance_rule_is_gated_on_spot_in(css_path):
    """`.spot-card { animation:iftRise }` is the rule that made every rebuild a fade.

    Guarding it in JS alone is not enough: the JS still rewrites the grid whenever the data
    genuinely changes, and an ungated rule would fade every card on each of those.
    """
    css = _page_css(css_path)
    assert "iftRise" in css, "entrance keyframes gone — wrong anchor, this test is blind"
    entrance = [
        ln.strip() for ln in css.splitlines()
        if "iftRise" in ln and "animation:" in ln and "@keyframes" not in ln
    ]
    assert entrance, "no rule applies iftRise — the spotlight would never animate at all"
    for rule in entrance:
        selectors = rule.split("{")[0]
        assert "spot-card" not in selectors or "spot-in" in selectors, (
            f"unconditional entrance on a rebuilt node: {rule!r} — every innerHTML "
            "rewrite of #spot-grid will replay the fade-from-zero"
        )


@CSS_SOURCES
def test_the_breathing_act_card_still_breathes(css_path):
    """Splitting the entrance out must not cost the top `act` card its idle motion."""
    css = _page_css(css_path)
    assert ".spot-card.breathe" in css and "iftBreathe" in css
    breathe = [ln for ln in css.splitlines() if ".spot-card.breathe" in ln]
    assert breathe and "iftBreathe" in breathe[0], (
        "the .breathe rule no longer applies iftBreathe"
    )


# ═══════════════════════════════════════════════════════════════════════════════
# 4. The render storm itself — async callers must coalesce
# ═══════════════════════════════════════════════════════════════════════════════

@PAGES
def test_fetch_handlers_go_through_the_coalescer(path):
    """Each fetch completion asked for a FULL render — the whole leaders table too, not
    just the spotlight. They must queue through scheduleRender() instead.

    requestAnimationFrame is deliberately NOT the timer: rAF is suspended in a hidden tab,
    so an rAF-coalesced render would freeze a backgrounded tab at its last paint.
    """
    src = path.read_text(encoding="utf-8")
    body = src[src.index("function fetchQuotes"):src.index("function updateFlowStamp")]
    assert "\n    render();" not in body, (
        "a fetch handler still calls render() directly — that is the uncoalesced storm"
    )
    assert body.count("scheduleRender();") == 4, (
        f"expected 4 coalesced call sites (quotes, pulse, flow, per-root), "
        f"found {body.count('scheduleRender();')}"
    )
    sched = src[src.index("function scheduleRender"):src.index("function render()")]
    assert "setTimeout" in sched and "requestAnimationFrame" not in sched, (
        "scheduleRender must use a timer — rAF does not fire while the tab is hidden"
    )
