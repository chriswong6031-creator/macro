"""tests/test_live_breadth_js_contract.py — executes `applyBreadth`
(templates/live.js) under node against a DOM stub, proving the fail-CLOSED
eligibility gate (FROZEN CONTRACT §3/§9) by EXECUTION rather than by reading
the source.

WHY EXECUTION, NOT A SOURCE GREP. The whole point of this wave is that a
degraded/stale/holiday/failed live snapshot must never be able to overwrite
the valid baked nightly breadth board (848 adv / 651 dec class of numbers) —
that is a CLIENT decision made in the browser, and a source grep proves only
that the right-looking code exists, never that it actually behaves. The idiom
here is copied from tests/test_wl1_board_state_surface.py's `_qualify`/`_pvc`:
lift the pure contract verbatim out of the template between marker comments,
run it under node (installed in CI via actions/setup-node@v4, node 20), and
assert on its actual output. A missing `node` in CI must be a RED pack, never
a silent skip that reports green having executed nothing.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

LIVE_JS = (ROOT / "templates" / "live.js").read_text()

_BEGIN = "/* SBX-BREADTH-CONTRACT-BEGIN"
_END = "/* SBX-BREADTH-CONTRACT-END */"


def _contract() -> str:
    a = LIVE_JS.index(_BEGIN)
    b = LIVE_JS.index(_END)
    assert a < b, f"{_BEGIN} must precede {_END}"
    return LIVE_JS[a:b]


# The harness supplies a minimal DOM stub (no jsdom dependency — the CI packs
# install a minimal set, not requirements.txt, so the safe assumption is
# "node only"). `document` is a plain `var` so the contract's function bodies
# (which reference the free variable `document` at CALL time, not definition
# time) resolve it via the enclosing scope once the per-case value is assigned.
_HARNESS = r"""
function makeDom(values) {
  var store = {};
  Object.keys(values).forEach(function (id) {
    var v = values[id];
    var node = {
      id: id,
      _text: v.text || "",
      _html: v.html || "",
      style: {},
      className: v.className || "",
      firstElementChild: v.firstElementChild ? { style: {} } : null
    };
    var classSet = {};
    (v.classes || []).forEach(function (c) { classSet[c] = true; });
    node.classList = {
      add: function (c) { classSet[c] = true; },
      remove: function (c) { delete classSet[c]; },
      toggle: function (c, on) { if (on) { classSet[c] = true; } else { delete classSet[c]; } },
      contains: function (c) { return !!classSet[c]; },
      _set: classSet
    };
    Object.defineProperty(node, "textContent", {
      get: function () { return node._text; },
      set: function (val) { node._text = val; }
    });
    Object.defineProperty(node, "innerHTML", {
      get: function () { return node._html; },
      set: function (val) { node._html = val; }
    });
    store[id] = node;
  });
  return {
    getElementById: function (id) { return Object.prototype.hasOwnProperty.call(store, id) ? store[id] : null; },
    __store: store
  };
}

var document;

%(contract)s

var cases = JSON.parse(process.argv[2]);
var out = cases.map(function (c) {
  document = makeDom(c.dom);
  applyBreadth(c.payload);
  var snap = {};
  Object.keys(c.dom).forEach(function (id) {
    var el = document.__store[id];
    snap[id] = {
      text: el._text,
      html: el._html,
      classes: Object.keys(el.classList._set)
    };
  });
  return snap;
});
console.log(JSON.stringify(out));
"""


def _run(cases: list) -> list:
    node = shutil.which("node")
    if node is None:
        # A skip here is only ever a local-dev convenience. In CI it would take
        # THE gate that stops a degraded/stale/holiday/failed live snapshot from
        # silently overwriting the baked nightly board and make it silently dark
        # — the pack would go green having executed nothing. ci.yml installs
        # node 20 (actions/setup-node@v4), so its absence under CI means the
        # setup step moved or was removed, which is a red pack, not a quiet pass.
        if os.environ.get("CI"):
            raise AssertionError(
                "node is required to execute the applyBreadth client contract, and "
                "CI installs it via actions/setup-node@v4 — its absence means the "
                "setup step moved or was removed, which would leave the fail-closed "
                "truth-boundary gate (FROZEN CONTRACT §3) unproven."
            )
        pytest.skip("node not available to execute the client contract (local only)")
    src = _HARNESS % {"contract": _contract()}
    with tempfile.TemporaryDirectory() as td:
        path = Path(td) / "sbx_breadth_contract.js"
        path.write_text(src)
        run = subprocess.run([node, str(path), json.dumps(cases)],
                             capture_output=True, text=True, check=False)
    assert run.returncode == 0, run.stdout + run.stderr
    return json.loads(run.stdout)


# ── fixtures ─────────────────────────────────────────────────────────────────

BAKED_ADV = "848"
BAKED_DEC = "651"

# sbxSet() (the shared setter applyBreadth uses for sbx-adv/sbx-dec) writes via
# .innerHTML, not .textContent — the baked fixture and every assertion below
# read the SAME property the real code path writes.
_DOM = {
    "sbx-adv": {"html": BAKED_ADV},
    "sbx-dec": {"html": BAKED_DEC},
    "sbx-stamp": {"html": "", "classes": []},
}


def _now_iso(offset_min: float = 0.0) -> str:
    from datetime import datetime, timedelta, timezone
    dt = datetime.now(timezone.utc) - timedelta(minutes=offset_min)
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")


def _usable_comp(**over):
    c = {"n": 1503, "adv": 900, "dec": 580, "unch": 23, "adv_pct": 60.8,
         "pa50": 61.2, "pa200": 58.4, "net_nh": 12}
    c.update(over)
    return c


def _payload(**over):
    p = {
        "schema": "live.breadth.v1",
        "asof": _now_iso(),
        "built_at": _now_iso(),
        "source_asof": _now_iso(16),
        "source_age_min": 16,
        "delay_min": 17,
        "session": "rth",
        "basis": "poll",
        "feed_status": "ok",
        "usable": True,
        "unusable_reason": None,
        "coverage": {"n": 1503, "expected": 1500, "pct": 100.2},
        "producer": "host:test",
        "tiers": [],
        "comp": _usable_comp(),
        "meta": {"missing": {}},
    }
    p.update(over)
    return p


def _empty_payload(feed_status: str) -> dict:
    return {
        "schema": "live.breadth.v1",
        "asof": _now_iso(),
        "built_at": _now_iso(),
        "source_asof": None,
        "source_age_min": None,
        "delay_min": 15,
        "session": "rth",
        "basis": "poll",
        "feed_status": feed_status,
        "usable": False,
        "unusable_reason": "feed_" + feed_status,
        "coverage": {"n": 0, "expected": 1500, "pct": 0.0},
        "producer": "host:test",
        "tiers": [],
        "comp": {"n": 0, "adv": 0, "dec": 0, "unch": 0, "adv_pct": None,
                 "pa50": None, "pa200": None, "net_nh": 0},
        "meta": {"missing": {}, "note": feed_status},
    }


def _assert_no_mutation(snap: dict) -> None:
    assert snap["sbx-adv"]["html"] == BAKED_ADV
    assert snap["sbx-dec"]["html"] == BAKED_DEC
    assert "live" not in snap["sbx-stamp"]["classes"]


def test_truth_boundary_contract():
    cases = [
        # A. fail-soft no_key empty payload -> baked numbers untouched, no live stamp.
        {"dom": _DOM, "payload": _empty_payload("no_key")},
        # B. offline empty payload -> identical: no mutation, no delayed stamp.
        {"dom": _DOM, "payload": _empty_payload("offline")},
        # C. usable payload, source_age_min 16 -> counts PATCH, stamp shows SOURCE delay.
        {"dom": _DOM, "payload": _payload()},
        # D. usable-shaped payload but source_age_min 120, built_at = now -> NO mutation.
        {"dom": _DOM, "payload": _payload(source_age_min=120, source_asof=_now_iso(120))},
        # E. built_at 3h old, source_age_min 5 -> NO mutation (stale ARTIFACT, fresh source).
        {"dom": _DOM, "payload": _payload(built_at=_now_iso(180), asof=_now_iso(180),
                                          source_age_min=5, source_asof=_now_iso(5))},
        # F. source_asof/source_age_min absent -> NO mutation.
        {"dom": _DOM, "payload": {k: v for k, v in _payload().items()
                                  if k not in ("source_asof", "source_age_min")}},
        # G. legacy v1 payload (no usable key) with real counts -> NO mutation.
        {"dom": _DOM, "payload": {k: v for k, v in _payload().items() if k != "usable"}},
        # H. session: "closed" -> NO mutation.
        {"dom": _DOM, "payload": _payload(session="closed")},
        # I. UNPARSEABLE built_at with an otherwise-perfect payload -> NO mutation.
        #    new Date("not-a-date") is NaN, and every NaN comparison is false, so a
        #    bare `buildAge > SLA` would FAIL OPEN here and hand a malformed payload
        #    live authority over the baked board. This case pins the isFinite guard.
        {"dom": _DOM, "payload": _payload(built_at="not-a-date", asof="not-a-date")},
        # J. built_at absent and asof unparseable -> NO mutation (same NaN class).
        {"dom": _DOM, "payload": {k: v for k, v in _payload(asof="").items()
                                  if k != "built_at"}},
    ]
    got = _run(cases)
    assert len(got) == len(cases)

    # A, B — fail-soft payloads never mutate, regardless of comp shape.
    _assert_no_mutation(got[0])
    _assert_no_mutation(got[1])

    # C — the ONLY accepted case: counts patch to the live payload's values, and
    # the stamp shows the source-derived (not build-derived) delay.
    accepted = got[2]
    assert accepted["sbx-adv"]["html"] == "900"
    assert accepted["sbx-dec"]["html"] == "580"
    assert "live" in accepted["sbx-stamp"]["classes"]
    assert "16-min delayed" in accepted["sbx-stamp"]["html"]

    # D — stale SOURCE clock (120 > 25) rejects even a fresh build.
    _assert_no_mutation(got[3])
    # E — stale ARTIFACT (built_at 3h old) rejects even a fresh source clock.
    _assert_no_mutation(got[4])
    # F — missing source clock fields fail closed.
    _assert_no_mutation(got[5])
    # G — no `usable` key at all (legacy v1) is rejected outright.
    _assert_no_mutation(got[6])
    # H — closed session never patches, even if otherwise usable-shaped.
    _assert_no_mutation(got[7])
    # I, J — an unparseable build clock is NaN, not "fresh": the gate must fail
    # CLOSED on it rather than sail through the false NaN comparison.
    _assert_no_mutation(got[8])
    _assert_no_mutation(got[9])
