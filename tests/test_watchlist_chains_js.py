"""tests/test_watchlist_chains_js.py — the WRI transmission chain lane (templates/watchlist_risk.js).

The chain-lane helpers are pure + DOM-free (exported under node behind a
`typeof module` guard, exactly like risk_core.js). We node-shell them with the published
transmission_chains.json subset fixture and assert:
  - chainIndex inverts ARMED chains only (dormant excluded), deduped per chain×channel
  - furthestChain picks expressed > propagating > arming (ties by links confirmed)
  - railChainSentence fires ONLY when a chain is propagating|expressed AND ≥1 book name is
    downstream; it returns null for an arming-only book and an empty book
  - a 404 / empty subset yields an empty index (the whole lane stays silently absent)
  - chainDrawerRows emits data-tip-* (never title=), carries the "not a signal" review copy,
    and never says "validated"

Node is available on CI + dev Macs; the suite skips loudly when it is not (mirrors
tests/test_risk_core_js.py).
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

MODULE = Path(__file__).resolve().parents[1] / "templates" / "watchlist_risk.js"
SUBSET = Path(__file__).resolve().parents[1] / "tests" / "fixtures" / "transmission" / "transmission_chains.json"


def _run(js_body: str, extra: dict | None = None) -> dict:
    """Load watchlist_risk.js under node, inject globals, run js_body, parse its JSON stdout."""
    globs = "\n".join("var %s = %s;" % (k, json.dumps(v)) for k, v in (extra or {}).items())
    script = textwrap.dedent(
        """
        var WRI = require(%(mod)s);
        %(globs)s
        function OUT(o){ process.stdout.write(JSON.stringify(o)); }
        %(body)s
        """
    ) % {"mod": json.dumps(str(MODULE)), "globs": globs, "body": js_body}
    res = subprocess.run(["node", "-e", script], capture_output=True, text=True, timeout=30)
    assert res.returncode == 0, f"node failed:\nSTDERR:\n{res.stderr}\nSTDOUT:\n{res.stdout}"
    assert res.stdout.strip(), f"no stdout; stderr:\n{res.stderr}"
    return json.loads(res.stdout)


@pytest.fixture(scope="module")
def subset() -> dict:
    return json.loads(SUBSET.read_text(encoding="utf-8"))


# ---------------------------------------------------------------------------
# chainIndex — armed-only, deduped
# ---------------------------------------------------------------------------
@needs_node
def test_index_armed_only_and_dedup(subset):
    out = _run(
        "var idx = WRI.chainIndex(SUB); "
        "var nvda = (idx.NVDA||[]).map(function(m){return m.id+'|'+m.state+'|'+m.channel;}); "
        "var anyVol = Object.keys(idx).some(function(t){return idx[t].some(function(m){return /vol/.test(m.id);});}); "
        "var pairs = (idx.NVDA||[]).map(function(m){return m.id+'|'+m.channel;}); "
        "OUT({n:Object.keys(idx).length, nvda:nvda, anyVol:anyVol, dedup:(pairs.length===new Set(pairs).size)});",
        {"SUB": subset},
    )
    assert out["n"] == 23
    assert out["anyVol"] is False                        # dormant vol_regime excluded
    assert out["dedup"] is True
    # NVDA is in the propagating dollar chain (2 channels) + arming oil chain (1)
    assert any("dollar_spike" in m and "propagating" in m for m in out["nvda"])
    assert any("oil_inflation" in m and "arming" in m for m in out["nvda"])


# ---------------------------------------------------------------------------
# furthestChain — progress ranking
# ---------------------------------------------------------------------------
@needs_node
def test_furthest_prefers_more_progressed(subset):
    out = _run(
        "var idx = WRI.chainIndex(SUB); "
        "OUT({nvda:WRI.furthestChain(idx.NVDA).state, "        # propagating (dollar) > arming (oil)
        "ccl:WRI.furthestChain(idx.CCL).state, "               # expressed (credit) > arming (oil)
        "empty:WRI.furthestChain([]), null_:WRI.furthestChain(null)});",
        {"SUB": subset},
    )
    assert out["nvda"] == "propagating"
    assert out["ccl"] == "expressed"
    assert out["empty"] is None and out["null_"] is None


# ---------------------------------------------------------------------------
# railChainSentence — condition
# ---------------------------------------------------------------------------
@needs_node
def test_rail_fires_on_propagating_or_expressed_with_book_name(subset):
    out = _run(
        "var idx = WRI.chainIndex(SUB); "
        "var hit = WRI.railChainSentence(idx, ['NVDA','AAPL']); "     # NVDA downstream of propagating dollar
        "var armOnly = WRI.railChainSentence(idx, ['PLTR']); "        # PLTR only in ARMING oil -> no fire
        "var noBook = WRI.railChainSentence(idx, []); "
        "OUT({hitEn:hit&&hit.en, hitM: hit&&/\\b2 of your names\\b/.test(hit.en), armOnly:armOnly, noBook:noBook});",
        {"SUB": subset},
    )
    assert out["hitEn"] and "cascade is propagating" in out["hitEn"]
    assert out["hitM"] is True                     # counts the 2 downstream book names (NVDA+AAPL)
    assert out["armOnly"] is None                  # arming-only never triggers the rail
    assert out["noBook"] is None


# ---------------------------------------------------------------------------
# 404 / empty subset -> whole lane silently absent
# ---------------------------------------------------------------------------
@needs_node
def test_empty_subset_yields_empty_index():
    out = _run(
        "OUT({none:Object.keys(WRI.chainIndex(null)).length, "
        "empty:Object.keys(WRI.chainIndex({})).length, "
        "noChains:Object.keys(WRI.chainIndex({chains:[]})).length});"
    )
    assert out == {"none": 0, "empty": 0, "noChains": 0}


# ---------------------------------------------------------------------------
# chainDrawerRows — copy discipline
# ---------------------------------------------------------------------------
@needs_node
def test_drawer_rows_copy_and_tips(subset):
    out = _run(
        "var idx = WRI.chainIndex(SUB); var html = WRI.chainDrawerRows(idx.NVDA); "
        "OUT({html:html, hasTip:/data-tip-en=/.test(html)&&/data-tip-zh=/.test(html), "
        "hasTitle:/ title=/.test(html), notSignal:/not a signal/.test(html), "
        "validated:/validated/i.test(html), empty:WRI.chainDrawerRows([])});",
        {"SUB": subset},
    )
    assert out["hasTip"] is True
    assert out["hasTitle"] is False               # receipts ride data-tip-*, never title=
    assert out["notSignal"] is True               # "Early monitor — not a signal."
    assert out["validated"] is False
    assert "Sits downstream of the" in out["html"]
    assert out["empty"] == ""                      # no armed chain -> no rows


# ---------------------------------------------------------------------------
# ENB display clamp — tier 1 never prints more bets than names
# ---------------------------------------------------------------------------
@needs_node
def test_enb_clamps_to_the_name_count_and_discloses_the_raw_value():
    """The estimator is a factor + per-name bucket composition and can land ABOVE the
    number of names held (measured live: 3 names, raw 4.06). "Your 3 names move as about
    4 bets" is not actionable, so tier 1 caps at the count — and the raw reading is
    DISCLOSED in the Tier-2 method tip rather than quietly dropped."""
    out = _run(
        "var i = WRI.enbClamp(4.1, 3); var tip = WRI.enbTipSuffix(i); "
        "OUT({bets:i.bets, shown:i.shown.toFixed(1), raw:i.raw, clamped:i.clamped, "
        "verdict:WRI.betCount({enb:4.1, held:['A','B','C']}), "
        "tipEn:tip&&tip.en, tipZh:tip&&tip.zh});"
    )
    assert out["bets"] == 3                    # verdict h2 prints 3, not 4
    assert out["shown"] == "3.0"               # footer reads "≈ 3.0 of 3 names"
    assert out["verdict"] == 3
    assert out["clamped"] is True
    # the raw value survives into the Tier-2 receipt, in both languages
    assert "4.1" in out["tipEn"] and "4.1" in out["tipZh"]
    assert "caps at the count" in out["tipEn"]
    assert "上限" in out["tipZh"]


@needs_node
def test_enb_below_the_name_count_is_untouched_and_adds_no_tip():
    """The clamp must be invisible in the ordinary case — otherwise every book grows a
    disclosure sentence it does not need."""
    out = _run(
        "var i = WRI.enbClamp(2.4, 5); "
        "OUT({bets:i.bets, shown:i.shown.toFixed(1), clamped:i.clamped, "
        "tip:WRI.enbTipSuffix(i), "
        "verdict:WRI.betCount({enb:2.4, held:['A','B','C','D','E']})});"
    )
    assert out["bets"] == 2 and out["shown"] == "2.4"
    assert out["clamped"] is False
    assert out["tip"] is None                  # no dynamic sentence appended
    assert out["verdict"] == 2


@needs_node
def test_enb_clamp_never_returns_zero_bets():
    """A one-name book still holds one bet; rounding 0.4 down to 0 would print
    "moves as about 0 bets"."""
    out = _run(
        "OUT({tiny:WRI.enbClamp(0.4, 1).bets, one:WRI.enbClamp(1.0, 1).bets, "
        "emptyN:WRI.enbClamp(2.0, 0).bets});"
    )
    assert out["tiny"] == 1 and out["one"] == 1
    assert out["emptyN"] == 1


@needs_node
def test_chain_driver_plain_words(subset):
    out = _run(
        "OUT({dollar:WRI.chainDriver({id:'dollar_spike_em_multinational'}), "
        "oil:WRI.chainDriver({id:'oil_inflation_duration_derate'}), "
        "credit:WRI.chainDriver({id:'credit_spreads_refinancing'})});"
    )
    assert out["dollar"]["en"] == "Dollar" and out["dollar"]["zh"] == "美元"
    assert out["oil"]["en"] == "Oil→rates"
    assert out["credit"]["en"] == "Credit-spread"
