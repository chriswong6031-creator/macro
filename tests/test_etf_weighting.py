"""W2b — the structural weighting lens on the ETF consensus board (masterplan §4).

The operator asked whether some funds should count more. The answer shipped here
is a SECOND READ, never a re-ranking: `weighted_usd`, `weighted_n` and the
`weight_receipt` that shows their arithmetic sit beside the equal-weight counts,
and the board's default order is the same breadth-then-conviction construction it
has always been. Three sections carry that claim:

  A) the primitives — which component each fund TYPE reports, and how the
     mismatched one is discounted (nothing here is fitted to any outcome);
  B) the lens on synthetic rows — type match, dollar magnitude, freshness
     exclusion, and a receipt whose numbers close by hand;
  C) the DEFAULT ORDER IS UNTOUCHED — replayed against a golden fixture frozen
     from real data/ through the registry-less (default) construction, plus a
     mutation control (flip every fund's type and the board must not move) and a
     non-vacuity control (the two orderings genuinely differ on this fixture, so
     the pin constrains something). The fixture was refrozen 2026-08-12 when
     masterplan §6b R1 landed — the VanEck cash-line fix moved the underlying
     conviction values, which is a DATA correction, not a construction change;
     see the fixture's own _README for the standing regeneration contract;
  D) payload wiring — the lens is premium-payload-only, so the free shell's
     130 KiB budget pays nothing for it;
  E) the SEO fund count, which is now counted rather than typed.

Synthetic everywhere except C, which reads the committed fixture (no parquet, no
network). Save-and-restore config stubbing matches the sibling ETF suites.

Regenerate the golden fixture (real data/, slow) with:
    python3 tests/test_etf_weighting.py --regenerate
"""
from __future__ import annotations

import contextlib
import json
import os
import re
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import engine.etf_consensus as ec  # noqa: E402
from lib import config  # noqa: E402

FIXTURE = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                       "fixtures", "etf_consensus_golden_ordering.json")

#: A registry the lens tests own outright, so no config edit can move their math.
REG = {"URA": {"type": "thematic_passive"}, "XSD": {"type": "sector"},
       "ARKK": {"type": "active"}, "OZEM": {"type": "active"}}


@contextlib.contextmanager
def _weighting(**over):
    """Force `etf_holdings.weighting` so arithmetic never depends on config.yml."""
    orig = config.load
    config.load = lambda: {"etf_holdings": {"weighting": over}}
    try:
        yield
    finally:
        config.load = orig


def _row(fund: str, ticker: str = "NVDA", **over) -> dict:
    """One all_etf_signals()-shaped row, W1 decomposition fields included."""
    base = {"etf": fund, "etf_name": fund, "ticker": ticker, "name": "Nvidia",
            "sector": "Technology", "category": "Semis", "is_active": False,
            "conviction_pp": 1.0, "direction": "accumulating", "weight_pct": 5.0,
            "is_new": False, "is_exit": False, "active_chg_pct": 10.0,
            "flow_usd": 1_000_000.0, "selection_usd": 400_000.0,
            "total_usd": 1_400_000.0, "flow_pp": 0.7, "selection_pp": 0.3,
            "driver": "flow", "streak": 2, "is_stale": False,
            "split_adjusted": False, "exit_confirmed": None,
            "accel_pct_per_day": 0.5}
    return {**base, **over}


def _one(rows: list[dict], **kw) -> dict:
    with _weighting(mismatch_discount=0.35, unattributed_weight=0.35):
        out = ec.consensus_favored(rows, min_funds=1, registry=REG, **kw)
    return out[0]


# =============================================================================
# A) the primitives
# =============================================================================

def test_each_fund_type_reports_exactly_one_component() -> None:
    assert ec.primary_component("active") == "selection"
    assert ec.primary_component("thematic_passive") == "flow"
    assert ec.primary_component("sector") == "flow"


def test_an_unknown_type_degrades_to_the_registrys_own_default() -> None:
    # A metadata gap must not hand the mismatched component a FULL weight.
    for missing in (None, "", "hedge_fund"):
        assert ec.primary_component(missing) == ec.PRIMARY_COMPONENT[ec.DEFAULT_TYPE]
        assert ec.component_weight(missing, "flow") == 1.0
        assert ec.component_weight(missing, "selection") == ec.MISMATCH_DISCOUNT


def test_the_matched_component_weighs_one_and_the_mismatch_is_discounted() -> None:
    assert ec.component_weight("active", "selection") == 1.0
    assert ec.component_weight("active", "flow") == ec.MISMATCH_DISCOUNT
    assert ec.component_weight("thematic_passive", "flow") == 1.0
    assert ec.component_weight("thematic_passive", "selection") == ec.MISMATCH_DISCOUNT
    assert ec.component_weight("sector", "flow") == 1.0
    assert ec.component_weight("sector", "selection") == ec.MISMATCH_DISCOUNT


def test_the_discount_is_a_discount_not_a_filter() -> None:
    # 0 would DELETE the mismatched component; a real move does sometimes hide
    # there, so the shipped default has to sit strictly between 0 and 1.
    assert 0.0 < ec.MISMATCH_DISCOUNT < 1.0
    assert 0.0 < ec.UNATTRIBUTED_WEIGHT < 1.0


def test_config_knobs_are_read_and_a_bogus_one_falls_back() -> None:
    assert ec.weighting_cfg({"weighting": {"mismatch_discount": 0.5}})[
        "mismatch_discount"] == 0.5
    for bogus in (35, -1, "0.35pc", None, float("nan")):
        got = ec.weighting_cfg({"weighting": {"mismatch_discount": bogus}})
        assert got["mismatch_discount"] == ec.MISMATCH_DISCOUNT, (
            f"{bogus!r} must fall back, not become the weight")
    # a missing block is not an error
    assert ec.weighting_cfg({})["mismatch_discount"] == ec.MISMATCH_DISCOUNT


def test_config_yml_ships_the_documented_default() -> None:
    block = (config.load().get("etf_holdings") or {}).get("weighting") or {}
    assert block.get("mismatch_discount") == 0.35, "masterplan §4 default drifted"
    assert block.get("unattributed_weight") == 0.35


# =============================================================================
# B) the lens on synthetic rows
# =============================================================================

def test_an_active_funds_selection_outweighs_its_own_flow() -> None:
    """Same dollars in both components; the manager's picks are what an active
    fund actually reports, so they survive at full weight and the creations —
    mostly the sponsor's marketing — are discounted."""
    g = _one([_row("ARKK", flow_usd=1_000_000.0, selection_usd=1_000_000.0,
                   total_usd=2_000_000.0, driver="selection")])
    r = g["weight_receipt"]
    assert r["usd_matched"] == pytest.approx(1_000_000.0)      # the selection half
    assert r["usd_mismatched"] == pytest.approx(1_000_000.0)   # the flow half
    assert g["weighted_usd"] == pytest.approx(1_350_000.0)     # 1.0M + 0.35×1.0M
    assert g["total_usd"] == pytest.approx(2_000_000.0)        # unweighted untouched


def test_a_passive_funds_flow_outweighs_its_own_selection() -> None:
    """The mirror image: for a thematic basket the creations ARE the signal and
    the per-name residual is mostly index reconstitution."""
    g = _one([_row("URA", flow_usd=1_000_000.0, selection_usd=1_000_000.0,
                   total_usd=2_000_000.0, driver="flow")])
    r = g["weight_receipt"]
    assert r["usd_matched"] == pytest.approx(1_000_000.0)      # the FLOW half now
    assert r["usd_mismatched"] == pytest.approx(1_000_000.0)
    assert g["weighted_usd"] == pytest.approx(1_350_000.0)


def test_the_same_event_weighs_differently_by_fund_type() -> None:
    """The whole point of (a): identical dollars, opposite verdicts, because the
    KIND of fund decides which half is evidence. A sector fund reads like a
    thematic one — both are baskets — which is why they share a primary."""
    ev = dict(flow_usd=0.0, selection_usd=1_000_000.0, total_usd=1_000_000.0,
              driver="selection")
    active = _one([_row("ARKK", **ev)])
    passive = _one([_row("URA", **ev)])
    sector = _one([_row("XSD", **ev)])
    assert active["weighted_usd"] == pytest.approx(1_000_000.0)
    assert passive["weighted_usd"] == pytest.approx(350_000.0)
    assert sector["weighted_usd"] == passive["weighted_usd"]
    assert active["weighted_n"] == 1.0 and passive["weighted_n"] == 0.35


def test_dollar_magnitude_is_the_aggregation_basis_not_fund_count() -> None:
    """§4(b): a $4B fund's 0.5pp is not a $30M fund's 0.5pp. Equal conviction_pp,
    100× the dollars — the COUNTS stay equal and only the lens separates them."""
    big = _row("URA", ticker="AAA", conviction_pp=0.5, flow_usd=400_000_000.0,
               selection_usd=0.0, total_usd=400_000_000.0)
    small = _row("XSD", ticker="AAA", conviction_pp=0.5, flow_usd=4_000_000.0,
                 selection_usd=0.0, total_usd=4_000_000.0)
    g = _one([big, small])
    assert g["n_accum"] == 2                      # equal-weight read: two funds
    assert g["weighted_n"] == 2.0                 # …and both are type-matched
    assert g["weighted_usd"] == pytest.approx(404_000_000.0)
    assert g["weight_receipt"]["n_passive_flow"] == 2


def test_a_stale_fund_is_excluded_from_this_cycle_and_says_so() -> None:
    """§4(c). The primary read still counts the stale fund — it is a real past
    decision — but it is not part of "this cycle", so the lens drops it and the
    receipt prints why rather than letting it age quietly into the number."""
    fresh = _row("URA", flow_usd=1_000_000.0, selection_usd=0.0, total_usd=1_000_000.0)
    stale = _row("XSD", flow_usd=9_000_000.0, selection_usd=0.0,
                 total_usd=9_000_000.0, is_stale=True)
    g = _one([fresh, stale])
    assert g["n_accum"] == 2 and g["n_stale"] == 1          # equal-weight untouched
    assert g["total_usd"] == pytest.approx(10_000_000.0)    # W1 total untouched
    assert g["weighted_usd"] == pytest.approx(1_000_000.0)  # the stale $9M is gone
    assert g["weighted_n"] == 1.0
    r = g["weight_receipt"]
    assert r["n_stale_excluded"] == 1 and r["n_funds_weighted"] == 1
    assert [f["weight"] for f in g["funds"] if f["fund"] == "XSD"] == [None]


def test_an_unattributed_event_is_discounted_not_dropped() -> None:
    """A fund whose decomposition failed (one snapshot, quarantined pair, no share
    column) carries no evidence about WHICH component moved. Unattributed evidence
    is not disproved evidence: it counts, at the discount, and is disclosed."""
    g = _one([_row("URA"), _row("XSD", driver=None, flow_usd=None,
                                selection_usd=None, total_usd=None)])
    r = g["weight_receipt"]
    assert r["n_unattributed"] == 1 and r["n_funds_weighted"] == 2
    assert g["weighted_n"] == pytest.approx(1.35)     # 1.0 matched + 0.35 unknown
    assert r["n_funds_usd"] == 1 and r["weighted_usd_complete"] is False


def test_the_receipt_arithmetic_closes_by_hand() -> None:
    """The receipt exists so a reader can re-derive the number. If this identity
    ever stops holding, the printed arithmetic is decoration."""
    rows = [_row("URA"), _row("ARKK", driver="selection", flow_usd=250_000.0,
                              selection_usd=-600_000.0, total_usd=-350_000.0),
            _row("XSD", flow_usd=-100_000.0, selection_usd=50_000.0,
                 total_usd=-50_000.0)]
    g = _one(rows)
    r = g["weight_receipt"]
    assert r["usd_mismatched_weighted"] == pytest.approx(
        r["mismatch_discount"] * r["usd_mismatched"])
    assert g["weighted_usd"] == pytest.approx(
        r["usd_matched"] + r["usd_mismatched_weighted"])
    # and the unweighted total is still the plain sum of every component
    assert g["total_usd"] == pytest.approx(r["usd_matched"] + r["usd_mismatched"])


def test_the_receipt_carries_every_input_it_claims_to() -> None:
    g = _one([_row("URA"), _row("ARKK", driver="selection")])
    assert set(g["weight_receipt"]) == {
        "mismatch_discount", "unattributed_weight", "n_funds_weighted",
        "n_active_selection", "n_passive_flow", "n_mismatched", "n_unattributed",
        "n_stale_excluded", "n_funds_usd", "weighted_usd_complete",
        "usd_matched", "usd_mismatched", "usd_mismatched_weighted"}
    r = g["weight_receipt"]
    assert r["n_active_selection"] == 1 and r["n_passive_flow"] == 1
    assert r["n_mismatched"] == 0 and r["n_funds_weighted"] == 2
    # every fund on the row carries its own type + weight, so the aggregate is
    # auditable per fund and not only in total
    assert {f["fund"]: (f["fund_type"], f["weight"]) for f in g["funds"]} == {
        "URA": ("thematic_passive", 1.0), "ARKK": ("active", 1.0)}


def test_a_mismatched_driver_is_counted_as_mismatched() -> None:
    """An active fund whose move was driven by creations, and a basket whose move
    was driven by the residual — both are the noisier half, both discounted."""
    g = _one([_row("ARKK", driver="flow"), _row("URA", driver="selection")])
    r = g["weight_receipt"]
    assert r["n_mismatched"] == 2
    assert r["n_active_selection"] == 0 and r["n_passive_flow"] == 0
    assert g["weighted_n"] == pytest.approx(0.70)      # 0.35 + 0.35


def test_weighted_dollars_are_absent_not_zero_when_nobody_published_values() -> None:
    """Plain-word null disclosure: a confident $0 would read as "no money moved"
    when the truth is "no sponsor published market values"."""
    g = _one([_row("URA", flow_usd=None, selection_usd=None, total_usd=None,
                   driver=None),
              _row("XSD", flow_usd=None, selection_usd=None, total_usd=None,
                   driver=None)])
    assert g["weighted_usd"] is None
    assert g["weighted_n"] == pytest.approx(0.70)   # the funds still count
    assert g["weight_receipt"]["n_funds_usd"] == 0


def test_an_all_stale_row_weighs_nothing_and_is_not_a_null() -> None:
    """Zero here is a real answer — "nothing fresh on this row" — unlike the
    missing-dollars case above, so it must not masquerade as absent."""
    g = _one([_row("URA", is_stale=True), _row("XSD", is_stale=True)])
    assert g["weighted_n"] == 0.0
    assert g["weight_receipt"]["n_stale_excluded"] == 2
    assert g["weight_receipt"]["n_funds_weighted"] == 0


def test_a_fund_absent_from_the_registry_still_lands_on_the_row() -> None:
    g = _one([_row("NEWFUND")])
    assert g["n_accum"] == 1
    assert g["funds"][0]["fund_type"] == ec.DEFAULT_TYPE
    assert g["weight_receipt"]["n_passive_flow"] == 1


def test_the_discount_is_the_configured_one() -> None:
    with _weighting(mismatch_discount=0.10):
        g = ec.consensus_favored([_row("ARKK", driver="selection")],
                                 min_funds=1, registry=REG)[0]
    assert g["weight_receipt"]["mismatch_discount"] == 0.10
    # 400k selection matched + 0.10 × 1.0M flow
    assert g["weighted_usd"] == pytest.approx(500_000.0)


# =============================================================================
# C) the default board is UNTOUCHED (the epistemics gate, masterplan §0.6)
# =============================================================================

def _golden() -> dict:
    with open(FIXTURE, encoding="utf-8") as fh:
        return json.load(fh)


def _replay(fx: dict, registry: dict | None) -> list[dict]:
    return ec.consensus_favored(fx["rows"], limit=10_000,
                                min_funds=fx["min_funds"], registry=registry)


def test_the_golden_fixture_is_a_real_board() -> None:
    fx = _golden()
    assert len(fx["ordering"]) >= 100, "a tiny fixture cannot pin an ordering"
    assert fx["rows"] and fx["n_rows"] == len(fx["rows"])
    readme = " ".join(fx["_README"])
    assert "python3 tests/test_etf_weighting.py --regenerate" in readme, (
        "the fixture must carry its own regeneration contract")
    assert "R1 LANDED" in readme, (
        "…and say which engine state these rows were frozen from")


def test_default_ordering_is_byte_identical_to_the_pre_w2b_golden() -> None:
    """THE gate. These rows and this ordering were frozen from real data/ before
    the lens existed; the lens may add fields and must not move one row."""
    fx = _golden()
    from engine.etf_registry import fund_registry
    assert [g["ticker"] for g in _replay(fx, fund_registry())] == fx["ordering"]


def test_the_lens_cannot_move_the_board_even_when_every_type_flips() -> None:
    """Mutation control. If the ordering ever DID read a weighted field, flipping
    every fund's type would show up here — the weights all change and the board
    must not."""
    fx = _golden()
    funds = {r["etf"] for r in fx["rows"] if r.get("etf")}
    flipped = {f: {"type": "active"} for f in funds}
    all_passive = {f: {"type": "thematic_passive"} for f in funds}
    base = [g["ticker"] for g in _replay(fx, all_passive)]
    assert base == fx["ordering"]
    assert [g["ticker"] for g in _replay(fx, flipped)] == fx["ordering"]
    # …and the flip really did change the lens, or the control proves nothing
    weighted_flipped = [g["weighted_usd"] for g in _replay(fx, flipped)]
    weighted_passive = [g["weighted_usd"] for g in _replay(fx, all_passive)]
    assert weighted_flipped != weighted_passive


def test_the_two_orderings_genuinely_disagree_on_this_fixture() -> None:
    """Non-vacuity. If weighted order happened to equal default order here, the
    gate above would be satisfied by a lens that does nothing at all."""
    fx = _golden()
    from engine.etf_registry import fund_registry
    board = _replay(fx, fund_registry())
    default_top = [g["ticker"] for g in board[:10]]
    weighted_top = [g["ticker"] for g in
                    sorted((g for g in board if g["weighted_usd"] is not None),
                           key=lambda g: -g["weighted_usd"])[:10]]
    assert default_top != weighted_top
    assert set(default_top) - set(weighted_top), (
        "the fixture must contain at least one name the lens demotes")


def test_the_lens_reaches_every_row_of_a_real_board() -> None:
    """A field that is silently None on real data would make the gate above pass
    for the wrong reason."""
    fx = _golden()
    from engine.etf_registry import fund_registry
    board = _replay(fx, fund_registry())
    assert all(isinstance(g["weighted_n"], float) for g in board)
    assert all(set(g["weight_receipt"]) for g in board)
    priced = [g for g in board if g["weighted_usd"] is not None]
    assert len(priced) > 0.5 * len(board), (
        f"only {len(priced)}/{len(board)} rows priced — the $ lens is mostly dark")


# =============================================================================
# D) payload wiring — premium side only
# =============================================================================

def test_payload_block_carries_the_lens_and_stays_json_safe() -> None:
    from scripts.build_site import _etf_flow_block
    with _weighting(mismatch_discount=0.35):
        favored = ec.consensus_favored([_row("URA"), _row("ARKK", driver="selection")],
                                       min_funds=1, registry=REG)
    block = _etf_flow_block(favored)
    assert set(block) == {"NVDA"}
    entry = block["NVDA"]
    for key in ("weighted_usd", "weighted_n", "weight_receipt"):
        assert key in entry, f"payload lost {key}"
    assert entry["weight_receipt"]["n_funds_weighted"] == 2
    dumped = json.dumps(block)
    assert "NaN" not in dumped and "Infinity" not in dumped
    assert json.loads(dumped)["NVDA"]["weighted_n"] == 2.0


def test_the_free_shell_template_never_renders_a_weighted_field() -> None:
    """The lens is paid-side data. If a template starts printing it, the 130 KiB
    shell budget and the tier split both need re-deciding — not a silent add."""
    here = os.path.dirname(os.path.abspath(__file__))
    tdir = os.path.join(os.path.dirname(here), "templates")
    for name in os.listdir(tdir):
        if not name.startswith(("etfs", "_etf")):
            continue
        with open(os.path.join(tdir, name), encoding="utf-8") as fh:
            body = fh.read()
        for field in ("weighted_usd", "weighted_n", "weight_receipt"):
            assert field not in body, f"{name} renders {field} (W2b is payload-only)"


# =============================================================================
# E) the SEO fund count is counted, not typed
# =============================================================================

def _render_shell(coverage: list[dict]) -> str:
    from jinja2 import Environment, FileSystemLoader
    here = os.path.dirname(os.path.abspath(__file__))
    env = Environment(loader=FileSystemLoader(os.path.join(os.path.dirname(here),
                                                           "templates")),
                      autoescape=True)
    env.globals.update(td=lambda en: en, tr=lambda en: en,
                       clean_name=lambda n: n or "")
    return env.get_template("etfs.html.j2").render(
        favored=[], accumulation=[], trims=[], coverage=coverage, pulse={},
        board=None, gate=None, generated_utc="2026-08-12 00:00")


def _cov(n_with_data: int, n_empty: int = 0) -> list[dict]:
    return ([{"fund": f"F{i}", "fund_name": f"F{i}", "sponsor": "ssga",
              "category": "X", "is_active": False, "unofficial": False,
              "n_snapshots": 3, "latest_asof": "2026-08-11", "stale_days": 0}
             for i in range(n_with_data)]
            + [{"fund": f"E{i}", "fund_name": f"E{i}", "sponsor": "ssga",
                "category": "X", "is_active": False, "unofficial": False,
                "n_snapshots": 0, "latest_asof": None, "stale_days": None}
               for i in range(n_empty)])


def _desc(html: str) -> str:
    m = re.search(r'<meta name="description" content="([^"]+)"', html)
    assert m, "no meta description rendered"
    return m.group(1)


def test_seo_description_counts_the_universe_instead_of_hardcoding_77() -> None:
    """It said 77 while the universe was 103 — a number typed once goes stale on
    the quiet side: nothing renders wrong, the description just starts lying."""
    src = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                       "templates", "etfs.html.j2")
    with open(src, encoding="utf-8") as fh:
        assert "77 thematic and active ETFs" not in fh.read()
    assert "103 thematic and active ETFs" in _desc(_render_shell(_cov(103)))
    assert "41 thematic and active ETFs" in _desc(_render_shell(_cov(41)))


def test_seo_count_ignores_funds_that_have_collected_nothing() -> None:
    """A configured fund with zero snapshots is not a tracked fund — the same
    rule the page's own "Tracking N" line uses, so the two cannot disagree."""
    assert "60 thematic and active ETFs" in _desc(_render_shell(_cov(60, n_empty=45)))


def test_seo_description_stays_inside_the_search_snippet_budget() -> None:
    """CI's literal-string length gate (50-170) skips a computed description, so
    the bound is pinned here instead — at the widest count the page can reach."""
    for n in (2, 41, 103, 999):
        assert 50 <= len(_desc(_render_shell(_cov(n)))) <= 170


def test_an_empty_coverage_directory_drops_the_number_not_the_sentence() -> None:
    desc = _desc(_render_shell([]))
    assert "Track which stocks thematic and active ETFs are accumulating" in desc
    assert " 0 " not in desc and " 1 " not in desc


# =============================================================================
# fixture regeneration (real data/, slow — never runs under pytest)
# =============================================================================

def _regenerate() -> None:
    """Rebuild the golden fixture from the worktree's data/. See the file header
    of the fixture for WHEN this is the right thing to do (masterplan §6b R1)."""
    import subprocess
    from engine.etf_board import drop_cash
    from engine.holdings_signals import all_etf_signals

    keep = ("etf", "etf_name", "category", "is_active", "ticker", "name", "sector",
            "weight_pct", "active_chg_pct", "conviction_pp", "is_new", "is_exit",
            "direction", "confirmed", "flow_usd", "selection_usd", "total_usd",
            "flow_pp", "selection_pp", "driver", "streak", "is_stale",
            "split_adjusted", "exit_confirmed", "accel_pct_per_day")
    rows = drop_cash(all_etf_signals())
    min_funds = config.load()["etf_holdings"].get("consensus_min_funds", 2)
    board = ec.consensus_favored(rows, limit=10_000, min_funds=min_funds)
    on_board = {g["ticker"] for g in board}
    lean = [{k: round(v, 6) if isinstance(v, float) else v
             for k, v in r.items() if k in keep and v is not None}
            for r in rows if r.get("ticker") in on_board]
    old = _golden()
    fx = {"_README": old["_README"],
          "engine_head": subprocess.run(["git", "rev-parse", "--short", "HEAD"],
                                        capture_output=True, text=True).stdout.strip(),
          "min_funds": min_funds, "n_rows": len(lean),
          "ordering": [g["ticker"] for g in board], "rows": lean}
    assert [g["ticker"] for g in ec.consensus_favored(
        lean, limit=10_000, min_funds=min_funds)] == fx["ordering"], \
        "the ticker-sliced replay does not reproduce the full-input ordering"
    head = json.dumps({k: v for k, v in fx.items() if k != "rows"}, indent=1)
    body = ",\n".join("  " + json.dumps(r, separators=(",", ":")) for r in fx["rows"])
    with open(FIXTURE, "w", encoding="utf-8") as fh:
        fh.write(head[:-2] + ',\n "rows": [\n' + body + "\n ]\n}\n")
    print(f"regenerated {FIXTURE}: {len(fx['ordering'])} tickers, {len(lean)} rows")


if __name__ == "__main__":
    if "--regenerate" in sys.argv:
        _regenerate()
        raise SystemExit(0)
    raise SystemExit(pytest.main([os.path.abspath(__file__), "-q"]))
