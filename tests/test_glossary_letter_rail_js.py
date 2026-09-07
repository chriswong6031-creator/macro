"""Behavioral contract for the glossary A-Z rail's click handling.

The rail emits exactly one build-time `id="gl-letter-X"` anchor per occupied
letter (pinned by tests/test_glossary_contract.py::
test_rendered_letter_rail_anchors_are_unique_ids). That single anchor can
live inside a row that the current domain/search filter has hidden
(`display:none`) — a `display:none` fragment target has no layout box, so a
plain `href="#gl-letter-X"` native jump is a silent no-op even though the
rail still presents the letter as enabled (findings review, round 2,
MAJOR 1). This module runs the actual inline glossary IIFE (extracted from
a real render) in a node-shelled DOM shim and asserts that clicking a live
letter scrolls to the first currently-VISIBLE row carrying that letter,
never to a hidden one — regardless of which row happens to hold the
build-time anchor.
"""
from __future__ import annotations

import json
import re
import shutil
import subprocess
import textwrap

import pytest
from jinja2 import Environment, FileSystemLoader

from lib import config
from lib.glossary import glossary_view_model

ROOT = config.ROOT
HAS_NODE = shutil.which("node") is not None
needs_node = pytest.mark.skipif(not HAS_NODE, reason="node not on PATH")


def _extract_iife() -> str:
    env = Environment(loader=FileSystemLoader(ROOT / "templates"), autoescape=True)
    vm = glossary_view_model(ROOT)
    html = env.get_template("glossary.html.j2").render(generated_utc="2026-01-01 00:00", **vm)
    scripts = re.findall(r"<script>(.*?)</script>", html, re.S)
    assert scripts, "no inline <script> blocks rendered"
    iife = scripts[-1]
    assert "gl-search" in iife, "expected the glossary filter IIFE as the last inline script"
    return iife


SHIM = r"""
global.__scrollLog = [];
global.__replaceStateLog = [];

function makeEl(id, attrs) {
  attrs = attrs || {};
  var listeners = {};
  var el = {
    id: id,
    tagName: attrs.tagName || 'DIV',
    hidden: !!attrs.hidden,
    dataset: {},
    _attrs: {},
  };
  Object.keys(attrs).forEach(function (k) {
    if (k === 'tagName' || k === 'hidden') return;
    el._attrs[k] = attrs[k];
  });
  el.getAttribute = function (name) {
    return Object.prototype.hasOwnProperty.call(el._attrs, name) ? el._attrs[name] : null;
  };
  el.setAttribute = function (name, val) { el._attrs[name] = String(val); };
  el.removeAttribute = function (name) { delete el._attrs[name]; };
  el.hasAttribute = function (name) { return Object.prototype.hasOwnProperty.call(el._attrs, name); };
  el.classList = { toggle: function () {}, add: function () {}, remove: function () {} };
  el.addEventListener = function (type, fn) { (listeners[type] = listeners[type] || []).push(fn); };
  el.dispatchEvent = function (ev) {
    (listeners[ev.type] || []).forEach(function (fn) { fn(ev); });
    return true;
  };
  el.scrollIntoView = function (opts) { global.__scrollLog.push({ id: el.id, opts: opts }); };
  el.querySelector = function () { return null; };
  el.querySelectorAll = function () { return []; };
  return el;
}

var ROOT_EL = makeEl('glossary', { 'data-glossary-state': 'complete' });
var QUERY_EL = makeEl('gl-search', { tagName: 'INPUT' });
QUERY_EL.value = '';
var COUNT_EL = makeEl('gl-result-count');
var PANEL_EL = makeEl('panel');

// Two rows sharing letter E: the FIRST (build-time anchor holder, per the
// unique-id fix) sits in a domain the current filter has hidden; the
// SECOND is visible. This mirrors the review's measured us-stocks/
// china-stocks E-letter stranding.
var ROW_HIDDEN_ANCHOR = makeEl('gl-entry-timing-dot-us', {
  'data-glossary-row': '', 'data-domain': 'us-stocks', 'data-letter': 'E',
  'data-search': 'entry timing dot', hidden: true,
});
var ROW_VISIBLE = makeEl('gl-entry-timing-chips-cn', {
  'data-glossary-row': '', 'data-domain': 'china-stocks', 'data-letter': 'E',
  'data-search': 'entry timing chip', hidden: false,
});
var ROWS = [ROW_HIDDEN_ANCHOR, ROW_VISIBLE];

var LETTER_E = makeEl('letter-E', { tagName: 'A', 'data-letter': 'E', href: '#gl-letter-E' });
var LETTERS = [LETTER_E];

ROOT_EL.querySelectorAll = function (sel) {
  if (sel === '[data-glossary-row]') return ROWS;
  if (sel === '.gl-letter') return LETTERS;
  if (sel === '[data-domain-section]') return [];
  if (sel === '[data-domain]') return [];
  return [];
};
ROOT_EL.querySelector = function (sel) {
  if (sel === '[data-empty-state]') return PANEL_EL;
  return null;
};

var __byId = { glossary: ROOT_EL, 'gl-search': QUERY_EL, 'gl-result-count': COUNT_EL };
global.document = {
  readyState: 'complete',
  documentElement: {
    getAttribute: function () { return null; },
    setAttribute: function () {},
  },
  getElementById: function (id) { return __byId[id] || null; },
  addEventListener: function () {},
  removeEventListener: function () {},
};
global.window = global;
global.history = { replaceState: function (a, b, url) { global.__replaceStateLog.push(url); } };
function OUT(o) { process.stdout.write(JSON.stringify(o)); }
"""


@needs_node
def test_clicking_a_live_letter_scrolls_to_a_visible_row_not_a_hidden_anchor():
    iife = _extract_iife()
    script = SHIM + "\n" + textwrap.dedent(iife) + """
    var ev = { type: 'click', defaultPrevented: false, preventDefault: function () { this.defaultPrevented = true; } };
    LETTER_E.dispatchEvent(ev);
    OUT({
      scrollLog: global.__scrollLog,
      defaultPrevented: ev.defaultPrevented,
    });
    """
    res = subprocess.run(["node", "-e", script], capture_output=True, text=True, timeout=30)
    assert res.returncode == 0, f"node failed:\nSTDERR:\n{res.stderr}\nSTDOUT:\n{res.stdout}"
    assert res.stdout.strip(), f"no stdout; stderr:\n{res.stderr}"
    out = json.loads(res.stdout)
    assert out["scrollLog"], (
        "clicking a live letter must scroll to a row — the letter link needs a "
        "click handler that re-targets to the currently-visible row, not just a "
        "static href to the build-time anchor"
    )
    scrolled_ids = [entry["id"] for entry in out["scrollLog"]]
    assert "gl-entry-timing-dot-us" not in scrolled_ids, (
        "must never scroll to a row the current filter has hidden — "
        f"scrolled to {scrolled_ids!r}"
    )
    assert "gl-entry-timing-chips-cn" in scrolled_ids, (
        "must scroll to the first currently-visible row carrying the clicked letter — "
        f"scrolled to {scrolled_ids!r}"
    )
    assert out["defaultPrevented"], (
        "native fragment navigation to the (possibly hidden) static anchor must be "
        "suppressed once JS has taken over the jump"
    )
