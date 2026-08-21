"""tests/test_portfolio_state_js.py — templates/portfolio_state.js, the A1A private
state authority (research/market_os/MASTERMIND_MARKET_OS_ARCHITECTURE_FREEZE_AND_
A1A_COMMISSIONING_2026-08-20.md §9-12).

Pure, DOM-free, node-exported behind a `typeof module` guard (the risk_core.js /
market_books.js idiom) — node-shelled with NO stubs at all beyond `require()` itself.

Covers the weighting law (§12) and the population/authority shape of the private
`portfolio_snapshot.v1` object (§9-10). This is a NEW suite, wired via an explicit
step in the `wri-risk-core` job of `.github/ci/legacy-jobs.yml` (review finding B3) —
`scripts/audit_unrun_tests.py`'s gate only reports/reds an unwired suite, it does not
itself add any `run:` step. Unlike the grandfathered-dark tests/test_market_books_js.py
and tests/test_portfolio.py, this suite actually executes in CI.
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

MODULE = Path(__file__).resolve().parents[1] / "templates" / "portfolio_state.js"


def _run(js_body: str, extra: dict | None = None) -> dict:
    globs = "\n".join("var %s = %s;" % (k, json.dumps(v)) for k, v in (extra or {}).items())
    script = textwrap.dedent(
        """
        var PS = require(%(mod)s);
        %(globs)s
        function OUT(o){ process.stdout.write(JSON.stringify(o)); }
        %(body)s
        """
    ) % {"mod": json.dumps(str(MODULE)), "globs": globs, "body": js_body}
    res = subprocess.run(["node", "-e", script], capture_output=True, text=True, timeout=30)
    assert res.returncode == 0, f"node failed:\nSTDERR:\n{res.stderr}\nSTDOUT:\n{res.stdout}"
    assert res.stdout.strip(), f"no stdout; stderr:\n{res.stderr}"
    return json.loads(res.stdout)


# ---------------------------------------------------------------------------
# weighting law (§12)
# ---------------------------------------------------------------------------
@needs_node
def test_all_unsized_gets_equal_relative_weights_explicitly_labeled():
    out = _run(
        "OUT(PS.computeWeighting(ROWS, function(){ return null; }));",
        {"ROWS": [{"ticker": "AAPL"}, {"ticker": "MSFT"}, {"ticker": "NVDA"}]},
    )
    assert out["state"] == "all_unsized_equal"
    assert out["basis"] == "equal_assumption"
    assert out["complete"] is True
    assert out["weights"]["AAPL"] == pytest.approx(100 / 3)
    assert sum(out["weights"].values()) == pytest.approx(100, abs=1e-6)


@needs_node
def test_all_sized_and_current_priced_gets_current_value_weights():
    out = _run(
        "OUT(PS.computeWeighting(ROWS, function(t){ return t === 'AAPL' ? 100 : 200; }));",
        {"ROWS": [{"ticker": "AAPL", "shares": 10}, {"ticker": "MSFT", "shares": 5}]},
    )
    assert out["state"] == "all_sized_current"
    assert out["basis"] == "current_value"
    assert out["complete"] is True
    # AAPL: 10*100=1000, MSFT: 5*200=1000 -> 50/50
    assert out["weights"]["AAPL"] == pytest.approx(50)
    assert out["weights"]["MSFT"] == pytest.approx(50)


@needs_node
def test_all_sized_but_no_live_price_gets_entry_cost_weights_labeled():
    out = _run(
        "OUT(PS.computeWeighting(ROWS, function(){ return null; }));",
        {"ROWS": [{"ticker": "AAPL", "shares": 10, "entry_price": 50},
                  {"ticker": "MSFT", "shares": 5, "entry_price": 40}]},
    )
    assert out["state"] == "all_sized_cost"
    assert out["basis"] == "entry_cost"
    assert out["complete"] is True
    # AAPL: 500, MSFT: 200 -> 500/700, 200/700
    assert out["weights"]["AAPL"] == pytest.approx(500 / 700 * 100)


@needs_node
def test_some_sized_some_unsized_abstains():
    """A1A defect 'hidden weighting completion': never average-fill the unsized row
    and blend it into the sized rows' distribution."""
    out = _run(
        "OUT(PS.computeWeighting(ROWS, function(){ return 100; }));",
        {"ROWS": [{"ticker": "AAPL", "shares": 10}, {"ticker": "MSFT"}]},
    )
    assert out["state"] == "mixed_unsized_abstain"
    assert out["complete"] is False
    assert out["weights"] == {}
    # the abstention still names both eligible tickers — neither is silently dropped
    assert set(out["eligible"]) == {"AAPL", "MSFT"}


@needs_node
def test_some_current_some_cost_basis_abstains():
    out = _run(
        "OUT(PS.computeWeighting(ROWS, function(t){ return t === 'AAPL' ? 100 : null; }));",
        {"ROWS": [{"ticker": "AAPL", "shares": 10, "entry_price": 50},
                  {"ticker": "MSFT", "shares": 5, "entry_price": 40}]},
    )
    assert out["state"] == "mixed_price_basis_abstain"
    assert out["complete"] is False
    assert out["weights"] == {}


@needs_node
def test_sized_but_no_basis_anywhere_abstains_rather_than_dropping_the_row():
    """A sized row with neither a live price nor an entry price cannot be honestly
    weighted; it must not be silently excluded from `eligible` either."""
    out = _run(
        "OUT(PS.computeWeighting(ROWS, function(){ return null; }));",
        {"ROWS": [{"ticker": "AAPL", "shares": 10}, {"ticker": "MSFT", "shares": 5}]},
    )
    assert out["state"] == "mixed_unsized_abstain"
    assert out["reason"] == "unresolved_basis"
    assert set(out["eligible"]) == {"AAPL", "MSFT"}


@needs_node
@pytest.mark.parametrize("rows", [[], [{"ticker": "AAPL", "shares": 10}]])
def test_zero_or_one_position_is_insufficient_no_relationship_read(rows):
    out = _run("OUT(PS.computeWeighting(ROWS, function(){ return 100; }));", {"ROWS": rows})
    assert out["state"] == "insufficient"
    assert out["complete"] is False
    assert out["weights"] == {}


# ---------------------------------------------------------------------------
# the snapshot — population, authority, and the "never assert zero" law (§9-10)
# ---------------------------------------------------------------------------
@needs_node
def test_population_empty_one_many():
    for rows, want in (
        ([], "empty"),
        ([{"ticker": "AAPL", "status": "open"}], "one"),
        ([{"ticker": "AAPL", "status": "open"}, {"ticker": "MSFT", "status": "open"}], "many"),
    ):
        out = _run("OUT(PS.computeSnapshot({rows: ROWS, authority: 'local'}));", {"ROWS": rows})
        assert out["population"] == want, (rows, out)


@needs_node
def test_closed_rows_never_enter_population_or_open_rows():
    out = _run(
        "OUT(PS.computeSnapshot({rows: ROWS, authority: 'cloud'}));",
        {"ROWS": [{"ticker": "AAPL", "status": "open"}, {"ticker": "MSFT", "status": "closed"}]},
    )
    assert out["population"] == "one"
    assert [r["ticker"] for r in out["open_rows"]] == ["AAPL"]
    assert [r["ticker"] for r in out["closed_rows"]] == ["MSFT"]


@needs_node
def test_rows_null_is_never_coerced_to_a_false_zero():
    """A1A authority law (§10): `rows: null` — a genuinely unknown cloud read — must
    stay honestly unknown. `read_state` carries that, never a fabricated empty
    population standing in for it. This is the mutation-red pin for 'restore
    cloud-to-local fallback' at the snapshot layer: a caller that coerces null to []
    before calling computeSnapshot loses the distinction this test is pinning."""
    out = _run(
        "OUT(PS.computeSnapshot({rows: null, authority: 'cloud', readState: 'error'}));"
    )
    assert out["read_state"] == "error"
    assert out["rows"] == []
    assert out["open_rows"] == []
    # population sits inside its frozen 3-value enum — read_state is what a caller
    # MUST gate on before trusting it as a real zero
    assert out["population"] == "empty"
    assert out["weighting"]["state"] == "insufficient"


@needs_node
def test_authority_is_never_fabricated_from_rows_shape():
    """computeSnapshot describes exactly the authority it is TOLD, never infers one
    from the rows it is handed — the caller (watchstore.js) is the sole authority
    source. This is what keeps a local batch of rows from ever being described as
    'cloud' by accident."""
    out_local = _run("OUT(PS.computeSnapshot({rows: [], authority: 'local'}));")
    out_cloud = _run("OUT(PS.computeSnapshot({rows: [], authority: 'cloud'}));")
    assert out_local["authority"] == "local"
    assert out_cloud["authority"] == "cloud"


@needs_node
def test_cross_currency_partitions_before_weighting_never_a_blended_map():
    """A1A weighting law (§12): different currencies -> partition before weighting.
    A caller that passes `bookOf` gets `cross_currency_partitioned` with an EMPTY
    weights map — never a flat map that silently summed HK$ and US$ together."""
    out = _run(
        "OUT(PS.computeSnapshot({rows: ROWS, authority: 'cloud', "
        "bookOf: function (t) { return t === 'AAPL' ? 'us' : 'hk'; }}).weighting);",
        {"ROWS": [{"ticker": "AAPL", "shares": 10, "status": "open"},
                  {"ticker": "0700.HK", "shares": 100, "status": "open"}]},
    )
    assert out["state"] == "cross_currency_partitioned"
    assert out["weights"] == {}
    assert out["complete"] is False


@needs_node
def test_single_currency_with_bookOf_still_computes_real_weights():
    out = _run(
        "OUT(PS.computeSnapshot({rows: ROWS, authority: 'cloud', priceOf: function(){return 100;}, "
        "bookOf: function () { return 'us'; }}).weighting);",
        {"ROWS": [{"ticker": "AAPL", "shares": 10, "status": "open"},
                  {"ticker": "MSFT", "shares": 10, "status": "open"}]},
    )
    assert out["state"] == "all_sized_current"
    assert out["complete"] is True


@needs_node
def test_snapshot_never_mutates_between_calls():
    """Each call returns a FRESH object — a caller holding a reference across a render
    must never see it change underneath it."""
    out = _run(
        """
        var a = PS.computeSnapshot({rows: ROWS, authority: 'local'});
        a.population = 'MUTATED';
        var b = PS.computeSnapshot({rows: ROWS, authority: 'local'});
        OUT({b: b.population});
        """,
        {"ROWS": [{"ticker": "AAPL", "status": "open"}]},
    )
    assert out["b"] == "one"
