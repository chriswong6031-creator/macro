"""tests/test_risk_state_live_session_floor.py — the live patchers must never drag a
rendered board BACKWARDS onto an older session.

The 2026-08-02 operator report: macro.html showed a 44 / Mixed gauge beside a path
chart whose Jul 31 endpoint sat at 66 in the Risk-on band, and china.html showed a 37
gauge beside a Jul 31 endpoint of 38. Both pages are rendered from the nightly read;
`site/live/risk_state.json` and `site/live/china_risk_state.json` are published by a
SEPARATE intraday VPS lane that does not run on a closed session, so a Friday file is
what a weekend visitor fetches. 44 was Jul 30's graded score; 37 was China's Jul 30
close. `patchPath` already refused to move the chart backwards ("never rewrite
history") — the headline had no such floor, so the feed won the gauge and the render
kept the chart, and the two halves of one card disagreed by a whole band.

A source assertion cannot catch that class: the old code was valid JS reading real
fields, and every value it wrote was a genuine number from a genuine snapshot — just
from the wrong session. So the shipped JS is EXECUTED under node against a minimal DOM
stub, with feeds built to sit behind / level with / ahead of the baked page, and the
resulting DOM is read back. Both the templates/ source and the site/ copy are exercised
(they are a byte-paired plain-copy asset; test_risk_state_live_copy_sync pins the pair,
this pins the behaviour of each).

Node ships on CI + dev Macs; the suite skips loudly when it is absent (mirrors
tests/test_intraday_flow_ncp_js.py).
"""
from __future__ import annotations

import json
import shutil
import subprocess
import textwrap
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]

HAS_NODE = shutil.which("node") is not None
needs_node = pytest.mark.skipif(not HAS_NODE, reason="node not on PATH")

US_JS = [ROOT / "templates" / "risk_state_live.js", ROOT / "site" / "risk_state_live.js"]
CN_JS = [ROOT / "templates" / "china_risk_state_live.js",
         ROOT / "site" / "china_risk_state_live.js"]
US_PAGES = pytest.mark.parametrize("js", US_JS, ids=["template", "site"])
CN_PAGES = pytest.mark.parametrize("js", CN_JS, ids=["template", "site"])

BAKED_SESSION = "2026-07-31"
BAKED_SCORE = 66          # the chart endpoint AND the gauge, post-reconciliation
BAKED_WORD = "Risk-on"

# ── DOM stub ────────────────────────────────────────────────────────────────
# Just enough of the document API for the patchers: getElementById,
# querySelector/querySelectorAll over a flat element registry keyed by the exact
# selector strings the patchers use, classList, style, textContent, and the
# element factory setBL() needs. Elements record every write so the assertions
# can read back what the patcher actually did.
DOM_STUB = r"""
function El(id, cls, text) {
  this.id = id || ""; this.textContent = text === undefined ? "" : text;
  this._cls = {}; (cls || "").split(/\s+/).forEach(function (c) { if (c) this._cls[c] = 1; }, this);
  this.style = {}; this.children = []; this._attrs = {};
  var self = this;
  this.classList = {
    add: function () { [].forEach.call(arguments, function (c) { self._cls[c] = 1; }); },
    remove: function () { [].forEach.call(arguments, function (c) { delete self._cls[c]; }); },
    contains: function (c) { return !!self._cls[c]; },
    toggle: function (c, on) { if (on) self._cls[c] = 1; else delete self._cls[c]; }
  };
}
El.prototype.getAttribute = function (k) { return k in this._attrs ? this._attrs[k] : null; };
El.prototype.setAttribute = function (k, v) { this._attrs[k] = String(v); };
El.prototype.appendChild = function (c) { this.children.push(c); return c; };
El.prototype.querySelector = function () { return null; };
El.prototype.querySelectorAll = function () { return []; };
El.prototype.closest = function () { return null; };
El.prototype.hasClass = function (c) { return !!this._cls[c]; };

var REG = {};      // selector / id -> El
function reg(key, el) { REG[key] = el; return el; }

var document = {
  readyState: "complete",
  documentElement: { getAttribute: function () { return "en"; }, lang: "en" },
  body: { classList: { contains: function () { return false; } } },
  getElementById: function (id) { return REG["#" + id] || null; },
  querySelector: function (s) { return REG[s] || null; },
  querySelectorAll: function (s) { return REG[s] ? [REG[s]] : []; },
  createElement: function () { return new El(); },
  addEventListener: function () {},
  dispatchEvent: function () {}
};
function CustomEvent() {}
var window = {};
var setInterval = function () {};
var fetch = function () { return { then: function () { return this; }, catch: function () {} }; };
"""


def _harness(js_src: str, feed: dict, page: str) -> dict:
    """Run one patcher against one feed and report what the DOM ended up holding."""
    if page == "us":
        setup = f"""
        var wordEl  = reg("#ms-word", new El("ms-word", "", {BAKED_WORD!r}));
        var scoreEl = reg("#ms-score", new El("ms-score", "", "{BAKED_SCORE}"));
        var bigEl   = reg(".mx5-big-score", new El("", "mx5-big-score", "{BAKED_SCORE}"));
        var vwEl    = reg(".mx5-verdict-word", new El("", "mx5-verdict-word", {BAKED_WORD!r}));
        var thesis  = reg(".mx5-thesis", new El("", "mx5-thesis", "Risk-on — the tape"));
        var pill    = reg("#ms-live-pill", new El("ms-live-pill", "on"));
        reg("#ms-date", new El("ms-date", "", "{BAKED_SESSION}"));
        reg("#regime-asof", new El("regime-asof", "", "{BAKED_SESSION}"));
        reg("#ms-tick", new El("ms-tick"));
        var gauge = reg(".mx5-gauge-svg", new El("", "mx5-gauge-svg"));
        gauge.setAttribute("data-gauge-arc-len", "175.93");
        """
        readback = """
        out.word  = (wordEl.children[0] || {}).textContent || wordEl.textContent;
        out.score = String(scoreEl.textContent);
        out.big   = String(bigEl.textContent);
        out.thesis = (thesis.children[0] || {}).textContent || thesis.textContent;
        out.pill_on = pill.hasClass("on");
        """
    else:
        setup = f"""
        var wordEl  = reg("#ms-word", new El("ms-word", "", {BAKED_WORD!r}));
        var scoreEl = reg("#ms-score", new El("ms-score", "", "{BAKED_SCORE}"));
        var numEl   = reg("#mx5-score-numeral", new El("mx5-score-numeral", "", "{BAKED_SCORE}"));
        var dateEl  = reg("#ms-date", new El("ms-date", "", "{BAKED_SESSION}"));
        var pill    = reg("#ms-live-pill", new El("ms-live-pill", "on"));
        reg("#ms-tick", new El("ms-tick"));
        reg(".v-thesis", new El("", "v-thesis", "Risk-on — the tape"));
        """
        readback = """
        out.word  = (wordEl.children[0] || {}).textContent || wordEl.textContent;
        out.score = String(scoreEl.textContent);
        out.numeral = String(numEl.textContent);
        out.date  = (dateEl.children[0] || {}).textContent || dateEl.textContent;
        out.pill_on = pill.hasClass("on");
        """

    pts = [{"d": "2026-07-30", "md": "Jul 30", "mz": "7月30", "s": 44,
            "v": "Mixed", "vz": "中性", "x": 945.09, "y": 113.04},
           {"d": BAKED_SESSION, "md": "Jul 31", "mz": "7月31", "s": BAKED_SCORE,
            "v": BAKED_WORD, "vz": "偏多", "x": 988.0, "y": 72.56}]
    chart = f"""
        var svg = reg(".mx5-sc-right .mx5-path-svg[data-points]", new El("", "mx5-path-svg"));
        svg.setAttribute("data-points", {json.dumps(json.dumps(pts))});
        svg.setAttribute("data-px0", "44"); svg.setAttribute("data-pxw", "944");
        svg.setAttribute("data-py0", "10"); svg.setAttribute("data-pyb", "194");
        svg.setAttribute("data-vbw", "1000"); svg.setAttribute("data-vbh", "224");
    """

    # the patchers are IIFEs that self-invoke on DOMContentLoaded/readyState and
    # keep their internals private; re-expose the one entry point we drive by
    # replacing the fetch-driven tick with a direct call.
    entry = "patchMacro" if page == "us" else "patchChina"
    script = "\n".join([
        DOM_STUB,
        setup,
        chart,
        "var out = {};",
        f"var FEED = {json.dumps(feed)};",
        # strip the module's own auto-run tail, then invoke the patcher directly
        "(function(){",
        js_src.replace("})();", f"try {{ {entry}(FEED); }} catch (e) {{ out.error = String(e); }}\n}})();"),
        "})();",
        readback,
        "out.chart_last = JSON.parse(svg.getAttribute('data-points')).slice(-1)[0];",
        "console.log(JSON.stringify(out));",
    ])
    res = subprocess.run(["node", "-e", script], capture_output=True, text=True, timeout=60)
    assert res.returncode == 0, f"node failed: {res.stderr[-2000:]}"
    return json.loads(res.stdout.strip().splitlines()[-1])


# display labels exactly as engine/market_state.py _LABEL emits them
LABEL = {"RISK_ON": ("Risk-on", "风险偏好"), "MIXED": ("Mixed", "混合"),
         "RISK_OFF": ("Risk-off", "避险")}
COLOR = {"RISK_ON": "green", "MIXED": "yellow", "RISK_OFF": "red"}


def _us_feed(nightly_asof: str, score: int, verdict: str, *, live=False, built=None) -> dict:
    en, zh = LABEL[verdict]
    return {
        "schema": "risk_state.v1",
        "built": built or f"{nightly_asof} 22:31:49 UTC",
        "live_active": live, "realtime": False, "stale": not live,
        "nightly_asof": nightly_asof,
        "display": {"verdict": verdict, "label_en": en, "label_zh": zh,
                    "color": COLOR[verdict], "score": score},
        "nightly": {"verdict": verdict, "score": score, "label_en": en, "label_zh": zh},
    }


def _cn_feed(nightly_asof: str, score: int, verdict: str, *, live=False, built=None) -> dict:
    f = _us_feed(nightly_asof, score, verdict, live=live, built=built)
    f["schema"] = "china_risk_state.v1"
    f["live"] = {"verdict": verdict, "headline_en": "Risk-off — stress is elevated",
                 "headline_zh": "避险"}
    f["nightly"]["headline_en"] = "Risk-off — stress is elevated"
    f["nightly"]["headline_zh"] = "避险"
    return f


# ── the regression itself ───────────────────────────────────────────────────

@needs_node
@US_PAGES
def test_us_feed_a_session_behind_leaves_the_board_alone(js):
    """The reported bug: a Jul 30 feed must not repaint a Jul 31 board."""
    out = _harness(js.read_text(encoding="utf-8"),
                   _us_feed("2026-07-30", 44, "MIXED"), "us")
    assert not out.get("error"), out["error"]
    assert out["score"] == str(BAKED_SCORE), (
        f"gauge regressed to the older session: {out['score']} (chart still "
        f"{out['chart_last']['s']}) — the split the floor exists to prevent")
    assert out["big"] == str(BAKED_SCORE)
    assert out["word"] == BAKED_WORD
    assert out["thesis"].startswith("Risk-on")
    assert out["pill_on"] is False, "a behind-the-render feed must not claim live"
    assert out["chart_last"]["s"] == BAKED_SCORE


@needs_node
@CN_PAGES
def test_cn_feed_a_session_behind_leaves_the_board_alone(js):
    out = _harness(js.read_text(encoding="utf-8"),
                   _cn_feed("2026-07-30", 37, "RISK_OFF", live=True,
                            built="2026-07-30 08:22:23 UTC"), "cn")
    assert not out.get("error"), out["error"]
    assert out["score"] == str(BAKED_SCORE), (
        f"gauge regressed to the older session: {out['score']} (chart still "
        f"{out['chart_last']['s']})")
    assert out["numeral"] == str(BAKED_SCORE)
    assert out["word"] == BAKED_WORD
    assert out["date"] == BAKED_SESSION, (
        f"freshness chip claims {out['date']!r} for a feed a session behind the render")
    assert out["pill_on"] is False


# ── and the floor must not break the thing it guards ────────────────────────

@needs_node
@US_PAGES
def test_us_feed_on_the_rendered_session_still_patches(js):
    """Same-session feed is the normal intraday case — it must still win."""
    out = _harness(js.read_text(encoding="utf-8"),
                   _us_feed(BAKED_SESSION, 44, "MIXED"), "us")
    assert not out.get("error"), out["error"]
    assert out["score"] == "44"
    assert out["word"] == "Mixed"
    assert out["chart_last"]["s"] == 44, "same-session patch must carry the chart with it"
    assert out["chart_last"]["v"] == "Mixed"


@needs_node
@US_PAGES
def test_us_feed_ahead_of_the_render_appends_a_provisional_point(js):
    """A genuinely newer session still appends, and the chart follows the gauge."""
    out = _harness(js.read_text(encoding="utf-8"),
                   _us_feed("2026-08-03", 52, "MIXED", live=True,
                            built="2026-08-03 14:05:00 UTC"), "us")
    assert not out.get("error"), out["error"]
    assert out["score"] == "52"
    assert out["chart_last"]["d"] == "2026-08-03"
    assert out["chart_last"]["s"] == 52


@needs_node
@CN_PAGES
def test_cn_feed_on_the_rendered_session_still_patches(js):
    out = _harness(js.read_text(encoding="utf-8"),
                   _cn_feed(BAKED_SESSION, 37, "RISK_OFF", live=True,
                            built=f"{BAKED_SESSION} 08:22:23 UTC"), "cn")
    assert not out.get("error"), out["error"]
    assert out["score"] == "37"
    assert out["word"] == "Risk-off"


@needs_node
@US_PAGES
def test_us_unreadable_feed_session_fails_closed(js):
    """No parseable session on the feed → keep the served render, not a guess."""
    feed = _us_feed("2026-07-30", 44, "MIXED")
    feed["nightly_asof"] = None
    feed["built"] = ""
    out = _harness(js.read_text(encoding="utf-8"), feed, "us")
    assert not out.get("error"), out["error"]
    assert out["score"] == str(BAKED_SCORE)
    assert out["word"] == BAKED_WORD
