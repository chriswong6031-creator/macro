"""tests/test_company_intelligence_dossier_js.py — E2-D dossier browser cutover.

The dossier JS is a self-contained IIFE that runs on page load. It requests
GET /api/event-workspace/{ticker} as the current-event authority (v2) and only
falls back to GET /api/company-intelligence/{ticker} on a genuine HTTP 404.
Any other non-200 from v2 (503, 429, network reject, invalid payload) renders
the "verified event temporarily unavailable" state without touching v1.

These tests are DISCRIMINATING: the fetch mock is wired so that v1 returns
data that would produce visually wrong output (bullish summary, 14 questions,
score_overlay) if it were ever called on the v2-200 path. A passing test
suite means the module provably applies fallback law, not just that it works
in the happy path.

Same harness as tests/test_watchlist_workspace_js.py: the IIFE is eval-d into
a minimal node shell with stubbed document/window/fetch/AbortController.
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
CI_DOSSIER = ROOT / "site" / "assets" / "js" / "company-intelligence-dossier.js"

# ---------------------------------------------------------------------------
# Frozen payloads (from commission spec)
# ---------------------------------------------------------------------------

V2_PAYLOAD = {
    "schema": "event_workspace_public_glance.v1",
    "available": True,
    "ticker": "AAPL",
    "plane": "event_workspace.v1",
    "event_id": "evt_cik0000320193_2026q3_results",
    "event_alias": "AAPL/2026Q3",
    "generation_id": "f709a0a6ec514282d5769e7d",
    "fiscal_period": {"year": 2026, "quarter": 3},
    "event_date": "2026-07-30",
    "lifecycle_state": "complete",
    "authority": "context_only",
    "reported": [
        {"id": "fact_revenue_gaap", "metric": "revenue", "label": "Revenue",
         "value": "$109.4B \u00b7 +16%", "unit": "usd_millions", "receipt_state": "byte_replayed"},
    ],
    "guidance": [
        {"id": "guidance:revenue_yoy_pct:0", "metric": "revenue_yoy_pct",
         "label": "Q4 revenue growth", "value": "9\u201311%",
         "horizon": "FY2026 Q4", "receipt_state": "byte_replayed"},
    ],
    "watch": [
        {"id": "claim_demand_vs_supply", "label": "Supply constraint",
         "value": "Demand continues to exceed supply", "receipt_state": "byte_replayed"},
        {"id": "claim_memory_flood", "label": "Memory cost/flood",
         "value": "Memory cost and supply remain a constraint", "receipt_state": "byte_replayed"},
        {"id": "claim_fx_headwind", "label": "FX headwind",
         "value": "Foreign exchange was a year-over-year headwind", "receipt_state": "byte_replayed"},
    ],
    "coverage_states": [
        {"id": "consensus", "label": "Consensus", "state": "unlicensed"},
        {"id": "reaction", "label": "Market reaction", "state": "not_joined"},
        {"id": "questions_count", "label": "Analyst questions", "state": "unstructured"},
    ],
    "source_states": [
        {"kind": "issuer_release", "status": "present"},
        {"kind": "transcript", "status": "present"},
        {"kind": "public_wire", "status": "absent"},
    ],
}

# A v1 payload with poisoned content: if v1 is ever called on a v2-200 path,
# these strings would appear in the DOM and fail the assertions below.
V1_POISON_PAYLOAD = {
    "available": True,
    "status": "ready",
    "generation_id": "v1-gen-id",
    "history": [{
        "fiscal_year": 2026,
        "fiscal_quarter": 2,
        "call_date": "2026-04-30",
        "summary": "bullish beat above expectations",
        "positive_highlights": ["Strong beat on every metric"],
        "negative_highlights": [],
        "metrics": {"questions_count": 14, "revenue_growth_pct": 12.5},
        "field_lineage": {"metrics": {"revenue_growth_pct": "earnings_history"}},
        "tags": [],
        "claim_citations_pending": False,
        "sources": [{"kind": "transcript", "status": "present"}],
    }],
}

# ---------------------------------------------------------------------------
# Node test shim — minimal DOM + fetch + window stubs
# ---------------------------------------------------------------------------

SHIM = r"""
global.window = global;
global.window.addEventListener = function () {};
global.window.dispatchEvent = function (e) { __events.push({type: e.type, detail: e.detail}); };
global.window.clearTimeout = clearTimeout;
global.window.setTimeout = setTimeout;

/* URLSearchParams and URL are built-in globals in Node 16+ */

var __events = [];
var __fetchCalls = [];
var __fetchImpl = null;

global.fetch = function (url, opts) {
  /* Never count route-catalog.json; it is optional infrastructure */
  if (String(url).indexOf('route-catalog.json') >= 0) {
    return Promise.resolve({ok: false, status: 404, json: function () { return Promise.reject(new Error('404')); }});
  }
  __fetchCalls.push(String(url));
  return __fetchImpl ? __fetchImpl(url, opts) : Promise.reject(new Error('no fetch impl'));
};

global.AbortController = function () {
  this.signal = null;
  this.abort = function () {};
};

global.CustomEvent = function (t, o) { this.type = t; this.detail = o && o.detail; };

global.Intl = Intl;

/* Minimal element factory */
function mkEl(tag) {
  return {
    id: '',
    tagName: (tag || 'DIV').toUpperCase(),
    textContent: '',
    hidden: false,
    href: '',
    rel: '',
    target: '',
    type: '',
    className: '',
    lang: '',
    style: {},
    children: [],
    _attrs: {},
    _listeners: {},
    getAttribute: function (k) {
      if (k === 'data-company-intelligence') return '';
      if (k === 'data-ticker') return 'AAPL';
      return this._attrs[k] !== undefined ? this._attrs[k] : null;
    },
    setAttribute: function (k, v) { this._attrs[k] = String(v); },
    removeAttribute: function (k) { delete this._attrs[k]; },
    get firstChild() { return this.children.length > 0 ? this.children[0] : null; },
    get parentNode() { return this._parent || null; },
    appendChild: function (c) {
      this.children.push(c);
      if (c && typeof c === 'object') c._parent = this;
      return c;
    },
    removeChild: function (c) {
      var i = this.children.indexOf(c);
      if (i >= 0) this.children.splice(i, 1);
    },
    classList: {
      _list: [],
      add: function (c) { if (this._list.indexOf(c) < 0) this._list.push(c); },
      remove: function (c) { var i = this._list.indexOf(c); if (i >= 0) this._list.splice(i, 1); },
      contains: function (c) { return this._list.indexOf(c) >= 0; }
    },
    addEventListener: function (evt, fn) {
      if (!this._listeners[evt]) this._listeners[evt] = [];
      this._listeners[evt].push(fn);
    },
    focus: function () {},
    click: function () { (__listeners['click'] || []).forEach(function (fn) { fn(); }); }
  };
}

var __elements = {};
var __root = mkEl('SECTION');
/* Root attributes specific to the dossier host element */
__root.getAttribute = function (k) {
  if (k === 'data-company-intelligence') return '';
  if (k === 'data-ticker') return 'AAPL';
  return this._attrs[k] !== undefined ? this._attrs[k] : null;
};

var __ids = [
  'ci-state', 'ci-loading', 'ci-empty', 'ci-empty-title', 'ci-empty-copy',
  'ci-content', 'ci-period', 'ci-v2-host', 'ci-summary', 'ci-strength', 'ci-pressure',
  'ci-tags', 'ci-metrics', 'ci-next-copy', 'ci-transcript', 'ci-earnings-record',
  'ci-history', 'ci-history-tabs', 'ci-receipt', 'ci-foot-note', 'ci-announcer',
  'ci-terminal-upgrade', 'ci-terminal-upgrade-empty'
];
__ids.forEach(function (id) {
  var el = mkEl('DIV');
  el.id = id;
  __elements[id] = el;
});

global.document = {
  readyState: 'complete',
  documentElement: {
    getAttribute: function (a) { return a === 'data-lang' ? 'en' : null; },
    setAttribute: function () {},
    classList: { add: function () {}, remove: function () {} }
  },
  querySelector: function (sel) {
    if (sel === '[data-company-intelligence]') return __root;
    return null;
  },
  getElementById: function (id) {
    if (__elements[id]) return __elements[id];
    for (var k in __elements) {
      var found = findById(__elements[k], id);
      if (found) return found;
    }
    return findById(__root, id) || null;
  },
  createElement: function (tag) {
    return mkEl(tag);
  },
  addEventListener: function () {},
  querySelectorAll: function () { return []; }
};

global.location = {hash: '', pathname: '/stocks/aapl.html', search: '', origin: 'https://mastermind-x.com'};

/* Recursively find element by id */
function findById(el, id) {
  if (!el || typeof el !== 'object') return null;
  if (el.id === id) return el;
  var ch = el.children || [];
  for (var i = 0; i < ch.length; i++) {
    var found = findById(ch[i], id);
    if (found) return found;
  }
  return null;
}

/* Collect all leaf text content from an element tree */
function leafText(el) {
  if (!el || typeof el !== 'object') return '';
  if ((!el.children || el.children.length === 0) && el.textContent) return el.textContent;
  return (el.children || []).map(leafText).join(' ');
}

function allBodyText() {
  return __ids.map(function (id) { return leafText(__elements[id] || {}); }).join(' ')
    + ' ' + leafText(__root);
}

function OUT(o) { process.stdout.write(JSON.stringify(o) + '\n'); }
"""

# Freeze the IIFE source for repeated injection
_IIFE_SRC = CI_DOSSIER.read_text(encoding="utf-8")


def _run_ci(setup_js: str, wait_ms: int = 80) -> dict:
    """Run the CI dossier IIFE under the shim with a custom fetch impl.

    `setup_js` must assign a function to `__fetchImpl` before the IIFE runs.
    Output is collected after `wait_ms` ms so async chains can resolve.
    """
    script = (
        SHIM + "\n"
        + textwrap.dedent(setup_js) + "\n"
        + _IIFE_SRC + "\n"
        + f"setTimeout(function () {{\n"
        f"  var tu = __elements['ci-terminal-upgrade'] || {{}};\n"
        f"  var tue = __elements['ci-terminal-upgrade-empty'] || {{}};\n"
        f"  var hist = __elements['ci-history'] || {{}};\n"
        f"  var ctn = __elements['ci-content'] || {{}};\n"
        f"  var emp = __elements['ci-empty'] || {{}};\n"
        f"  var retryEl = findById(emp, 'ci-retry');\n"
        f"  OUT({{\n"
        f"    fetchCalls: __fetchCalls,\n"
        f"    mode: __root._attrs['data-ci-mode'] || null,\n"
        f"    eventId: __root._attrs['data-ci-event-id'] || null,\n"
        f"    bodyText: allBodyText(),\n"
        f"    terminalUpgradeHref: tu.href || null,\n"
        f"    terminalUpgradeEmptyHref: tue.href || null,\n"
        f"    historyHidden: hist.hidden,\n"
        f"    contentHidden: ctn.hidden,\n"
        f"    emptyHidden: emp.hidden,\n"
        f"    retryPresent: !!retryEl\n"
        f"  }});\n"
        f"}}, {wait_ms});\n"
    )
    res = subprocess.run(
        ["node", "-e", script],
        capture_output=True, text=True, timeout=30,
    )
    assert res.returncode == 0, (
        f"node exited {res.returncode}:\nSTDERR:\n{res.stderr}\nSTDOUT:\n{res.stdout}"
    )
    assert res.stdout.strip(), f"no stdout; stderr:\n{res.stderr}"
    return json.loads(res.stdout.strip().splitlines()[-1])


# ============================================================================
# 1. v2 200 + malicious v1 overlay waiting
#    v1 returns bullish/beat/14-questions if it were called. Prove it is not.
# ============================================================================
@needs_node
def test_v2_200_never_requests_v1_and_renders_v2_content():
    """THE CORE DISCRIMINATOR.

    The fetch mock has two personalities: a clean v2 200 and a poisoned v1
    payload with summary='bullish beat', questions_count=14, positive_highlights,
    score_overlay. If the module calls v1 for any reason, the forbidden strings
    appear in the DOM and the fetch-order assertion fails.

    Pass means: v2 was fetched, v1 was NEVER requested, and the v2 glance
    content (Revenue $109.4B, 9-11%, Consensus unlicensed, Market reaction
    not joined) appears while the v1 poison strings do not.
    """
    out = _run_ci(
        f"""
__fetchImpl = function (url) {{
  if (url.indexOf('/api/event-workspace/') >= 0) {{
    return Promise.resolve({{
      ok: true, status: 200,
      json: function () {{ return Promise.resolve({json.dumps(V2_PAYLOAD)}); }}
    }});
  }}
  /* v1 — MUST NEVER BE CALLED on a v2-200 path */
  return Promise.resolve({{
    ok: true, status: 200,
    json: function () {{ return Promise.resolve({json.dumps(V1_POISON_PAYLOAD)}); }}
  }});
}};
"""
    )
    # Fetch order: only v2 URL requested
    assert any("/api/event-workspace/" in u for u in out["fetchCalls"]), (
        "v2 /api/event-workspace/ was never requested", out["fetchCalls"]
    )
    assert not any("/api/company-intelligence/" in u for u in out["fetchCalls"]), (
        "v1 /api/company-intelligence/ was requested on a v2-200 path — fallback law violated",
        out["fetchCalls"],
    )

    # Mode and identity
    assert out["mode"] == "v2", out
    assert out["eventId"] == "evt_cik0000320193_2026q3_results", out

    # v2 glance content is present
    body = out["bodyText"]
    assert "Revenue" in body, body
    assert "$109.4B" in body or "109.4" in body, body
    assert "9" in body and "11" in body, body   # "9–11%"
    assert "Consensus" in body, body
    assert "Unlicensed" in body, body
    assert "Market reaction" in body or "reaction" in body.lower(), body
    assert "Not joined" in body, body
    assert "Supply constraint" in body, body
    assert "Demand continues to exceed supply" in body, body

    # v1 poison strings are absent
    for forbidden in ("14 analyst", "bullish", "beat", "miss",
                      "Wording not yet checked", "Positive context"):
        assert forbidden not in body, (
            f"forbidden v1 string {forbidden!r} appeared in v2 mode body", body[:400]
        )

    # History hidden in v2
    assert out["historyHidden"] is True, (
        "ci-history is not hidden in v2 mode", out
    )

    # Content visible, empty state hidden
    assert out["contentHidden"] is False, out
    assert out["emptyHidden"] is True, out


# ============================================================================
# 2. v2 404 → v1 requested and legacy teaser renders; data-ci-mode=v1
# ============================================================================
@needs_node
def test_v2_404_falls_through_to_v1_and_sets_mode_v1():
    """HTTP 404 from /api/event-workspace/ means no v2 coverage.
    The module MUST then request v1 and render the legacy teaser.
    """
    v1_payload = dict(V1_POISON_PAYLOAD)
    out = _run_ci(
        f"""
__fetchImpl = function (url) {{
  if (url.indexOf('/api/event-workspace/') >= 0) {{
    return Promise.resolve({{ok: false, status: 404, json: function () {{ return Promise.reject(); }}}});
  }}
  return Promise.resolve({{
    ok: true, status: 200,
    json: function () {{ return Promise.resolve({json.dumps(v1_payload)}); }}
  }});
}};
"""
    )
    # v2 fetch happened first
    assert any("/api/event-workspace/" in u for u in out["fetchCalls"]), (
        "v2 /api/event-workspace/ was not requested first", out["fetchCalls"]
    )
    # v1 fetch followed
    assert any("/api/company-intelligence/" in u for u in out["fetchCalls"]), (
        "v1 /api/company-intelligence/ was NOT requested after 404", out["fetchCalls"]
    )
    # v2 before v1 in call order
    v2_idx = next(i for i, u in enumerate(out["fetchCalls"]) if "/api/event-workspace/" in u)
    v1_idx = next(i for i, u in enumerate(out["fetchCalls"]) if "/api/company-intelligence/" in u)
    assert v2_idx < v1_idx, (
        "v1 was requested before v2 — fetch order violated", out["fetchCalls"]
    )
    # Mode is v1
    assert out["mode"] == "v1", out
    # v1 content rendered (content visible)
    assert out["contentHidden"] is False, out


# ============================================================================
# 3. v2 503 → unavailable; v1 NOT requested; Retry present; analysis URL
# ============================================================================
@needs_node
def test_v2_503_renders_unavailable_no_v1_retry_present():
    """HTTP 503 from v2: unavailable state, v1 never touched."""
    out = _run_ci(
        """
__fetchImpl = function (url) {
  if (url.indexOf('/api/event-workspace/') >= 0) {
    return Promise.resolve({ok: false, status: 503, json: function () { return Promise.reject(); }});
  }
  /* v1 must not be reached */
  return Promise.resolve({ok: true, status: 200, json: function () { return Promise.resolve({available: true}); }});
};
"""
    )
    assert any("/api/event-workspace/" in u for u in out["fetchCalls"]), out
    assert not any("/api/company-intelligence/" in u for u in out["fetchCalls"]), (
        "v1 was requested after v2 503 — fallback law violated", out["fetchCalls"]
    )
    assert out["mode"] == "unavailable", out
    assert out["retryPresent"] is True, (
        "Retry button (#ci-retry) is missing after v2 503", out
    )
    # Open Terminal href must be analysis URL, not v1 upgrade URL
    tue_href = out["terminalUpgradeEmptyHref"] or ""
    assert "/analysis?symbol=AAPL&page=intelligence" in tue_href, (
        "Open Terminal href does not point to analysis intelligence URL", tue_href
    )
    # Unavailable copy present
    body = out["bodyText"]
    assert "temporarily unavailable" in body.lower() or "暂时不可用" in body, body[:300]


# ============================================================================
# 4. v2 network reject → same as 503; v1 NOT requested
# ============================================================================
@needs_node
def test_v2_network_reject_renders_unavailable_no_v1():
    """A rejected Promise (network failure) is treated identically to 503."""
    out = _run_ci(
        """
__fetchImpl = function (url) {
  if (url.indexOf('/api/event-workspace/') >= 0) {
    return Promise.reject(new Error('network failure'));
  }
  return Promise.resolve({ok: true, status: 200, json: function () { return Promise.resolve({available: true}); }});
};
"""
    )
    assert any("/api/event-workspace/" in u for u in out["fetchCalls"]), out
    assert not any("/api/company-intelligence/" in u for u in out["fetchCalls"]), (
        "v1 was requested after network rejection — fallback law violated",
        out["fetchCalls"],
    )
    assert out["mode"] == "unavailable", out
    assert out["retryPresent"] is True, out


# ============================================================================
# 5. v2 200 invalid schema → unavailable; v1 NOT requested
# ============================================================================
@needs_node
def test_v2_200_invalid_schema_renders_unavailable_no_v1():
    """A 200 with a wrong schema string must not fall through to v1."""
    bad_payload = dict(V2_PAYLOAD, schema="something_else.v99")
    out = _run_ci(
        f"""
__fetchImpl = function (url) {{
  if (url.indexOf('/api/event-workspace/') >= 0) {{
    return Promise.resolve({{
      ok: true, status: 200,
      json: function () {{ return Promise.resolve({json.dumps(bad_payload)}); }}
    }});
  }}
  return Promise.resolve({{ok: true, status: 200, json: function () {{ return Promise.resolve({json.dumps(V1_POISON_PAYLOAD)}); }}}});
}};
"""
    )
    assert not any("/api/company-intelligence/" in u for u in out["fetchCalls"]), (
        "v1 was requested after invalid v2 schema — fallback law violated",
        out["fetchCalls"],
    )
    assert out["mode"] == "unavailable", out


# ============================================================================
# 6. v2 429 → unavailable; v1 NOT requested
# ============================================================================
@needs_node
def test_v2_429_renders_unavailable_no_v1():
    """HTTP 429 (rate-limited) is not a 404; v1 must not be requested."""
    out = _run_ci(
        """
__fetchImpl = function (url) {
  if (url.indexOf('/api/event-workspace/') >= 0) {
    return Promise.resolve({ok: false, status: 429, json: function () { return Promise.reject(); }});
  }
  return Promise.resolve({ok: true, status: 200, json: function () { return Promise.resolve({available: true}); }});
};
"""
    )
    assert not any("/api/company-intelligence/" in u for u in out["fetchCalls"]), (
        "v1 was requested after 429 — fallback law violated", out["fetchCalls"]
    )
    assert out["mode"] == "unavailable", out
    assert out["retryPresent"] is True, out


# ============================================================================
# 7. Primary CTA in v2 is the analysis intelligence URL, not pane=transcripts
# ============================================================================
@needs_node
def test_v2_primary_cta_is_analysis_intelligence_url():
    """ci-terminal-upgrade href must point to /analysis?symbol=...&page=intelligence,
    not to the v1 transcript pane URL.
    """
    out = _run_ci(
        f"""
__fetchImpl = function (url) {{
  return Promise.resolve({{
    ok: url.indexOf('/api/event-workspace/') >= 0,
    status: url.indexOf('/api/event-workspace/') >= 0 ? 200 : 404,
    json: function () {{ return Promise.resolve({json.dumps(V2_PAYLOAD)}); }}
  }});
}};
"""
    )
    assert out["mode"] == "v2", out
    href = out["terminalUpgradeHref"] or ""
    assert "/analysis?symbol=AAPL&page=intelligence" in href, (
        "primary CTA does not point to the analysis intelligence URL", href
    )
    assert "pane=transcripts" not in href, (
        "primary CTA still points to the v1 transcripts pane instead of analysis", href
    )


# ============================================================================
# 8. v1 history (#ci-history) is hidden in v2 mode
# ============================================================================
@needs_node
def test_v2_hides_history_section():
    """#ci-history must be hidden=true after a successful v2 render."""
    out = _run_ci(
        f"""
__fetchImpl = function (url) {{
  return Promise.resolve({{
    ok: url.indexOf('/api/event-workspace/') >= 0,
    status: url.indexOf('/api/event-workspace/') >= 0 ? 200 : 404,
    json: function () {{ return Promise.resolve({json.dumps(V2_PAYLOAD)}); }}
  }});
}};
"""
    )
    assert out["mode"] == "v2", out
    assert out["historyHidden"] is True, (
        "#ci-history is not hidden after v2 render — spec requires it hidden in v2 mode",
        out,
    )


# ============================================================================
# Source-level checks (no node required)
# ============================================================================

def test_js_syntax_check():
    """node --check must pass on the dossier source."""
    result = subprocess.run(
        ["node", "--check", str(CI_DOSSIER)],
        capture_output=True, text=True,
    )
    assert result.returncode == 0, f"node --check failed:\n{result.stderr}"


def test_v2_fetch_is_primary_and_v1_is_fallback_in_source():
    """Static source check: v2 fetch appears before v1 in the module.

    The commission requires /api/event-workspace/ as the primary authority
    and /api/company-intelligence/ retained only as the genuine 404 fallback.
    Ordering in source mirrors the execution order.
    """
    src = CI_DOSSIER.read_text(encoding="utf-8")
    assert "fetch('/api/event-workspace/' + encodeURIComponent(ticker)," in src, (
        "/api/event-workspace/ fetch is not present in the module source"
    )
    assert "fetch('/api/company-intelligence/' + encodeURIComponent(ticker)," in src, (
        "/api/company-intelligence/ fetch is not present (needed as 404 fallback)"
    )
    v2_pos = src.index("fetch('/api/event-workspace/'")
    v1_pos = src.index("fetch('/api/company-intelligence/'")
    assert v2_pos < v1_pos, (
        "v1 fetch appears before v2 in the source — fetch order is inverted"
    )


def test_no_llm_or_qwen_in_source():
    """The module must not reference any LLM or Qwen callable."""
    src = CI_DOSSIER.read_text(encoding="utf-8")
    for banned in ("Qwen", "qwen", "llm", "openai", "anthropic",
                   "model.invoke", "model.call"):
        assert banned not in src, (
            f"Banned term {banned!r} found in dossier source"
        )


def test_v2_zh_map_is_closed_no_dynamic_lookup():
    """The ZH map for v2 content must be a static literal (frozen spec),
    not resolved via a function call to an LLM or dynamic translation layer.
    """
    import re
    src = CI_DOSSIER.read_text(encoding="utf-8")
    # V2_ZH must be a literal object assignment
    m = re.search(r"var V2_ZH\s*=\s*\{", src)
    assert m, "V2_ZH closed map is not defined as a literal in the source"
    # Spot-check closed-map entries
    for entry in ("'Verified event'", "'已核实事件'", "'unlicensed'", "'未授权'",
                  "'Market reaction'", "'市场反应'", "'not_joined'", "'未接入'"):
        assert entry in src, (
            f"Expected closed-map entry {entry!r} not found in V2_ZH"
        )
