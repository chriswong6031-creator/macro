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
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pandas as pd
import pytest

from engine import live_overlay
from scripts import build_risk_state as brs

ROOT = Path(__file__).resolve().parents[1]

HAS_NODE = shutil.which("node") is not None
needs_node = pytest.mark.skipif(not HAS_NODE, reason="node not on PATH")

US_JS = [ROOT / "templates" / "risk_state_live.js", ROOT / "site" / "risk_state_live.js"]
CN_JS = [ROOT / "templates" / "china_risk_state_live.js",
         ROOT / "site" / "china_risk_state_live.js"]
US_PAGES = pytest.mark.parametrize("js", US_JS, ids=["template", "site"])
CN_PAGES = pytest.mark.parametrize("js", CN_JS, ids=["template", "site"])

# GD-3 (adjudication #10): the Risk Envelope live overlay is a SECOND US-macro-page
# consumer of the same feed-behind-the-render floor law, but its DOM shape (the
# #risk-envelope-band chip/pending/receipt hooks) is unrelated to the
# ms-word/ms-score headline patcher's, so it gets its own JS list + harness rather
# than being appended into US_JS/US_PAGES (which would silently break every
# existing test there — `entry = "patchMacro"` does not exist in this module).
RE_JS = [ROOT / "templates" / "risk_envelope_live.js", ROOT / "site" / "risk_envelope_live.js"]
RE_PAGES = pytest.mark.parametrize("js", RE_JS, ids=["template", "site"])

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


# ── GD-3: the Risk Envelope overlay's own DOM stub + harness (adjudication #10) ──
# risk_envelope_live.js exposes `applyFeed(d)` (extracted from tick()'s fetch chain
# specifically so it is drivable this way, same idiom as patchMacro/patchChina
# above) — reads the band's data-bundle-id/data-settled-session, and paints/hides
# the #gde-live-chip / #gde-pending-chip / #gde-live-receipt hooks.

RE_BAKED_BUNDLE = "fd9ccdbe47f7f008"
RE_BAKED_SESSION = "2026-08-19"


def _re_harness(js_src: str, feed: dict | None) -> dict:
    """Run risk_envelope_live.js's `applyFeed` against one feed and report what
    the DOM ended up holding. `feed=None` simulates a fetch that resolved falsy
    (network error / non-OK response already reduced to null upstream of
    applyFeed in the real fetch chain)."""
    setup = f"""
    var band = reg("#risk-envelope-band", new El("risk-envelope-band"));
    band.setAttribute("data-bundle-id", {RE_BAKED_BUNDLE!r});
    band.setAttribute("data-settled-session", {RE_BAKED_SESSION!r});

    var chip = reg("#gde-live-chip", new El("gde-live-chip"));
    chip.hidden = true;
    var chipEn = new El("", "l-en", "");
    var chipZh = new El("", "l-zh", "");
    var chipTime = new El("", "gde-live-time", "");
    chip.querySelector = function (sel) {{
      if (sel === ".l-en") return chipEn;
      if (sel === ".l-zh") return chipZh;
      if (sel === ".gde-live-time") return chipTime;
      return null;
    }};

    var pending = reg("#gde-pending-chip", new El("gde-pending-chip"));
    pending.hidden = true;
    var pendingEn = new El("", "l-en", "");
    var pendingZh = new El("", "l-zh", "");
    pending.querySelector = function (sel) {{
      if (sel === ".l-en") return pendingEn;
      if (sel === ".l-zh") return pendingZh;
      return null;
    }};

    var receipt = reg("#gde-live-receipt", new El("gde-live-receipt"));
    receipt.hidden = true;
    """
    readback = """
    out.chip_hidden = !!chip.hidden;
    out.chip_en = chipEn.textContent;
    out.chip_zh = chipZh.textContent;
    out.chip_time = chipTime.textContent;
    out.pending_hidden = !!pending.hidden;
    out.pending_en = pendingEn.textContent;
    out.receipt_hidden = !!receipt.hidden;
    out.receipt_text = receipt.textContent;
    """
    script = "\n".join([
        DOM_STUB,
        setup,
        "var out = {};",
        f"var FEED = {json.dumps(feed)};",
        "(function(){",
        js_src.replace(
            "})();",
            "try { applyFeed(FEED); } catch (e) { out.error = String(e); }\n})();",
        ),
        "})();",
        readback,
        "console.log(JSON.stringify(out));",
    ])
    res = subprocess.run(["node", "-e", script], capture_output=True, text=True, timeout=60)
    assert res.returncode == 0, f"node failed: {res.stderr[-2000:]}"
    return json.loads(res.stdout.strip().splitlines()[-1])


def _re_feed(*, source_session="2026-08-20", bundle_id=RE_BAKED_BUNDLE, precedence="live",
             live_active=True, built=None, stale_after_min=5,
             stage="FRAGILE", stable_stage="FRAGILE", pending=None, data_state="FRESH") -> dict:
    # `active()`'s freshness gate compares against REAL wall-clock Date.now() (it
    # must, in production), so a fixture built from a fixed historical string would
    # go stale the moment real time moves past it. Default to "90s ago" computed at
    # call time instead, well inside the 5min horizon regardless of when the suite
    # actually runs.
    if built is None:
        built = (datetime.now(timezone.utc) - timedelta(seconds=90)).strftime("%Y-%m-%d %H:%M:%S UTC")
    return {
        "schema": "mastermind.risk_envelope/v1",
        "revision": "live_provisional",
        "precedence": precedence,
        "source_session": source_session,
        "bundle_id": "9c4a7e21ab30f581",
        "built": built,
        "live_active": live_active,
        "stale_after_min": stale_after_min,
        "data_state": data_state,
        "hazard_summary": {"stage": stage},
        "overlays": {"settled_bundle_id": bundle_id, "settled_source_session": RE_BAKED_SESSION},
        "live_transition": {"candidate_stage": stage, "stable_stage": stable_stage, "pending": pending},
    }


@needs_node
@RE_PAGES
def test_re_feed_a_session_behind_the_render_never_paints(js):
    """The SAME feed-behind-the-render floor law as risk_state_live.js, applied to
    the Risk Envelope overlay: a live read whose own source_session is OLDER than
    the page's baked settled session (data-settled-session) must never paint."""
    feed = _re_feed(source_session="2026-08-18")   # older than RE_BAKED_SESSION
    out = _re_harness(js.read_text(encoding="utf-8"), feed)
    assert not out.get("error"), out.get("error")
    assert out["chip_hidden"] is True
    assert out["pending_hidden"] is True
    assert out["receipt_hidden"] is True


@needs_node
@RE_PAGES
def test_re_feed_on_or_ahead_of_the_render_still_paints(js):
    """Sanity control for the floor test above: a live session AHEAD of the baked
    settled session (the normal case) must still paint."""
    feed = _re_feed(source_session="2026-08-20")   # ahead of RE_BAKED_SESSION
    out = _re_harness(js.read_text(encoding="utf-8"), feed)
    assert not out.get("error"), out.get("error")
    assert out["chip_hidden"] is False
    assert out["chip_en"] == "Live · provisional"


@needs_node
@RE_PAGES
def test_re_unpaint_hides_all_three_hooks_completely(js):
    """A feed that fails `active()` (mismatched settled_bundle_id here) must hide
    ALL three hooks — chip, pending, and receipt — never leave one painted while
    the others clear."""
    feed = _re_feed()
    feed["overlays"]["settled_bundle_id"] = "SOME-OTHER-BUNDLE"
    out = _re_harness(js.read_text(encoding="utf-8"), feed)
    assert not out.get("error"), out.get("error")
    assert out["chip_hidden"] is True
    assert out["pending_hidden"] is True
    assert out["receipt_hidden"] is True
    assert out["receipt_text"] == ""


@needs_node
@RE_PAGES
def test_re_stage_null_routes_to_degraded_even_when_data_state_is_fresh(js):
    """Adjudication #8 regression: route on hazard_summary.stage alone. A feed
    with a null stage but data_state FRESH (the exact shape a laundered empty
    live block used to produce) must still paint the DEGRADED copy, never the
    healthy "Live · provisional" chip."""
    feed = _re_feed(stage=None, stable_stage="FRAGILE", data_state="FRESH")
    out = _re_harness(js.read_text(encoding="utf-8"), feed)
    assert not out.get("error"), out.get("error")
    assert out["chip_hidden"] is False
    assert out["chip_en"] == "Live · not enough to say"
    assert out["chip_zh"] == "实时 · 暂无法判断"
    assert out["pending_hidden"] is True


@needs_node
@RE_PAGES
def test_re_paint_degraded_paint_restores_chip_copy_and_receipt(js):
    """Adjudication #4 regression: paint() must NOT assume the DOM still holds its
    baked "Live · provisional" copy — a prior paintDegraded() call must not leave
    the chip stuck on degraded text, or the receipt stuck on a stale HEALTHY line,
    once a subsequent feed is healthy again. Runs three feeds through the SAME
    long-lived DOM stub in one node process, exactly like a real poll sequence."""
    healthy = _re_feed(stage="TRANSMITTING",
                       pending={"stage": "TRANSMITTING", "ticks": 2, "needs": 3})
    degraded = _re_feed(stage=None, data_state="DEGRADED")
    healthy_again = _re_feed(stage="FRAGILE", pending=None)

    setup = f"""
    var band = reg("#risk-envelope-band", new El("risk-envelope-band"));
    band.setAttribute("data-bundle-id", {RE_BAKED_BUNDLE!r});
    band.setAttribute("data-settled-session", {RE_BAKED_SESSION!r});

    var chip = reg("#gde-live-chip", new El("gde-live-chip"));
    chip.hidden = true;
    var chipEn = new El("", "l-en", "");
    var chipZh = new El("", "l-zh", "");
    var chipTime = new El("", "gde-live-time", "");
    chip.querySelector = function (sel) {{
      if (sel === ".l-en") return chipEn;
      if (sel === ".l-zh") return chipZh;
      if (sel === ".gde-live-time") return chipTime;
      return null;
    }};

    var pending = reg("#gde-pending-chip", new El("gde-pending-chip"));
    pending.hidden = true;
    var pendingEn = new El("", "l-en", "");
    var pendingZh = new El("", "l-zh", "");
    pending.querySelector = function (sel) {{
      if (sel === ".l-en") return pendingEn;
      if (sel === ".l-zh") return pendingZh;
      return null;
    }};

    var receipt = reg("#gde-live-receipt", new El("gde-live-receipt"));
    receipt.hidden = true;
    """
    readback = """
    out.chip_en = chipEn.textContent;
    out.receipt_text = receipt.textContent;
    """
    script = "\n".join([
        DOM_STUB,
        setup,
        "var out1 = {}, out2 = {}, out3 = {};",
        f"var FEED1 = {json.dumps(healthy)};",
        f"var FEED2 = {json.dumps(degraded)};",
        f"var FEED3 = {json.dumps(healthy_again)};",
        "(function(){",
        js.read_text(encoding="utf-8").replace(
            "})();",
            "try {\n"
            "  applyFeed(FEED1);\n"
            "  out1.chip_en = chipEn.textContent; out1.receipt_text = receipt.textContent;\n"
            "  applyFeed(FEED2);\n"
            "  out2.chip_en = chipEn.textContent; out2.receipt_text = receipt.textContent;\n"
            "  applyFeed(FEED3);\n"
            "  out3.chip_en = chipEn.textContent; out3.receipt_text = receipt.textContent;\n"
            "} catch (e) { out1.error = String(e); }\n"
            "})();",
        ),
        "})();",
        "console.log(JSON.stringify({one: out1, two: out2, three: out3}));",
    ])
    res = subprocess.run(["node", "-e", script], capture_output=True, text=True, timeout=60)
    assert res.returncode == 0, f"node failed: {res.stderr[-2000:]}"
    out = json.loads(res.stdout.strip().splitlines()[-1])
    assert not out["one"].get("error"), out["one"].get("error")

    assert out["one"]["chip_en"] == "Live · provisional"
    assert "TRANSMITTING" in out["one"]["receipt_text"]

    assert out["two"]["chip_en"] == "Live · not enough to say", (
        "paintDegraded must overwrite the chip copy"
    )
    assert "TRANSMITTING" not in out["two"]["receipt_text"], (
        "the degraded receipt must not keep showing the last HEALTHY pending line"
    )

    assert out["three"]["chip_en"] == "Live · provisional", (
        "a healthy feed after a degraded one must restore the chip's normal copy, "
        "not leave it stuck on 'not enough to say'"
    )
    assert "TRANSMITTING" not in out["three"]["receipt_text"]


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
@US_PAGES
def test_us_null_measured_and_display_scores_preserve_the_baked_path(js):
    """JS must not coerce an explicit null score to zero and invent a Risk-off point."""
    feed = _us_feed(BAKED_SESSION, 44, "MIXED", live=True,
                    built=f"{BAKED_SESSION} 14:05:00 UTC")
    feed["display"]["score"] = None
    feed["display"]["raw_score"] = None
    out = _harness(js.read_text(encoding="utf-8"), feed, "us")
    assert not out.get("error"), out["error"]
    assert out["score"] == str(BAKED_SCORE)
    assert out["chart_last"]["s"] == BAKED_SCORE
    assert out["chart_last"]["v"] == BAKED_WORD


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


# ══ GD-3R1 — scripts/build_risk_state.py's own quote-clock plumbing ══════════════
#
# No suite unit-tests scripts/build_risk_state.py's pure Python helpers directly
# (tests/test_risk_state.py covers the unrelated engine/risk_state.py; this file
# is the sibling JS-behavior suite for the SAME risk_state.json artifact that
# module's `build()` publishes — its `_us_feed`/`_cn_feed` fixtures already mirror
# that artifact's shape). GD-3R1 adds the real source-market quote clock to that
# artifact's `live` block (`live.source_event_time` / `live.source_quote_clocks`,
# scripts/build_risk_state.py's `_spliced_frames` / `_source_event_time`); these
# classes are the discriminating regression FROZEN SPEC item 5 requires: a
# spliced quote's own `quote_ts` lands in `live.source_quote_clocks` and the max
# of those lands in `live.source_event_time`; an unclocked quote is excluded from
# the max; all-None -> None.

def _nightly_close(price: float, n: int = 3) -> pd.Series:
    idx = pd.date_range("2026-08-18", periods=n, freq="D")
    return pd.Series([price] * n, index=idx)


def _live_quote(price: float, quote_ts: str | None, prev_close: float = 100.0,
                delay_min: float = 0.0) -> dict:
    # Real engine.live_quotes.fetch_quotes() quotes always carry both `quote_ts`
    # AND a precomputed `delay_min` (engine/live_quotes.py's `_delay_min`).
    # `delay_min` is supplied explicitly so `live_overlay.staleness()` can judge
    # freshness even in the (synthetic, defensive) case a test wants a spliceable
    # quote whose `quote_ts` is itself None.
    return {"price": price, "prev_close": prev_close, "quote_ts": quote_ts,
            "delay_min": delay_min}


class TestSourceEventTime:

    def test_max_of_parseable_clocks_wins(self):
        clocks = {
            "SPY": "2026-08-21T09:00:00+00:00",
            "QQQ": "2026-08-21T09:05:00+00:00",   # newest -> must win
            "IWM": "2026-08-21T08:50:00+00:00",
        }
        assert brs._source_event_time(clocks) == "2026-08-21T09:05:00+00:00"

    def test_unclocked_quote_is_excluded_from_the_max(self):
        clocks = {
            "SPY": "2026-08-21T09:00:00+00:00",
            "QQQ": None,   # spliced but carried no quote_ts — must not participate
        }
        assert brs._source_event_time(clocks) == "2026-08-21T09:00:00+00:00"

    def test_all_none_or_empty_is_none(self):
        assert brs._source_event_time({"SPY": None, "QQQ": None}) is None
        assert brs._source_event_time({}) is None

    def test_unparseable_clock_is_excluded_not_fatal(self):
        clocks = {"SPY": "not-a-timestamp", "QQQ": "2026-08-21T09:00:00+00:00"}
        assert brs._source_event_time(clocks) == "2026-08-21T09:00:00+00:00"


class TestSplicedFramesQuoteClocks:

    def test_spliced_quotes_own_clock_is_captured_per_store(self, monkeypatch):
        closes = {"SPY": _nightly_close(500.0), "QQQ": _nightly_close(400.0)}
        monkeypatch.setattr(live_overlay, "read_close", lambda name: closes.get(name))
        now = datetime(2026, 8, 21, 9, 6, tzinfo=timezone.utc)
        quotes = {
            "SPY": _live_quote(505.0, "2026-08-21T09:05:30+00:00", prev_close=500.0),
            "QQQ": _live_quote(404.0, "2026-08-21T09:04:10+00:00", prev_close=400.0),
        }
        spliced, live_close, nightly_close, quote_clocks = brs._spliced_frames(
            quotes, max_chg=10.0, stale_after=20.0, now=now, session_open=True)
        assert set(spliced) == {"SPY", "QQQ"}
        # each store's OWN quote_ts lands in quote_clocks — never a builder wall clock
        assert quote_clocks["SPY"] == "2026-08-21T09:05:30+00:00"
        assert quote_clocks["QQQ"] == "2026-08-21T09:04:10+00:00"
        assert quote_clocks["SPY"] != now.isoformat()
        # and the max of those lands in source_event_time
        assert brs._source_event_time(quote_clocks) == "2026-08-21T09:05:30+00:00"

    def test_a_quote_that_fails_usable_is_never_spliced_and_never_clocked(self, monkeypatch):
        """A rejected (limit-move-guard) quote must not appear in quote_clocks at
        all — bounded to exactly the members actually spliced."""
        closes = {"SPY": _nightly_close(500.0)}
        monkeypatch.setattr(live_overlay, "read_close", lambda name: closes.get(name))
        now = datetime(2026, 8, 21, 9, 6, tzinfo=timezone.utc)
        quotes = {"SPY": _live_quote(5000.0, "2026-08-21T09:05:30+00:00", prev_close=500.0)}
        spliced, live_close, nightly_close, quote_clocks = brs._spliced_frames(
            quotes, max_chg=10.0, stale_after=20.0, now=now, session_open=True)
        assert "SPY" not in spliced
        assert "SPY" not in quote_clocks

    def test_a_quote_with_no_quote_ts_still_splices_but_carries_a_none_clock(self, monkeypatch):
        closes = {"SPY": _nightly_close(500.0)}
        monkeypatch.setattr(live_overlay, "read_close", lambda name: closes.get(name))
        now = datetime(2026, 8, 21, 9, 6, tzinfo=timezone.utc)
        quotes = {"SPY": _live_quote(505.0, None, prev_close=500.0)}
        spliced, live_close, nightly_close, quote_clocks = brs._spliced_frames(
            quotes, max_chg=10.0, stale_after=20.0, now=now, session_open=True)
        assert "SPY" in spliced
        assert quote_clocks["SPY"] is None
        assert brs._source_event_time(quote_clocks) is None

    def test_nothing_spliced_yields_empty_quote_clocks(self, monkeypatch):
        monkeypatch.setattr(live_overlay, "read_close", lambda name: None)
        now = datetime(2026, 8, 21, 9, 6, tzinfo=timezone.utc)
        spliced, live_close, nightly_close, quote_clocks = brs._spliced_frames(
            {}, max_chg=10.0, stale_after=20.0, now=now, session_open=True)
        assert spliced == {}
        assert quote_clocks == {}
        assert brs._source_event_time(quote_clocks) is None
