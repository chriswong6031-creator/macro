"""The theme proxy gate — engine/marketing/theme_proxy.py.

Every leg gets a test that FAILS if the leg is removed, and the refusals get the
same treatment as the passes: this module's whole value is what it says NO to,
because a rule that always prefers the sector ETF is wrong more often than the
member-only status quo it replaces.

The bar fixtures are written as parquet under a tmp ``data/baskets/ohlcv`` so the
cohesion leg is exercised for real (a stubbed cohesion would leave the leg that
kills $XBI-on-biotech untested).
"""
from __future__ import annotations

import json
import math
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from engine.marketing import theme_proxy as tp


# ─────────────────────────────────────────────────────────────────────────────
# Fixtures
# ─────────────────────────────────────────────────────────────────────────────

def _tiers(tmp: Path, advs: dict[str, float]) -> None:
    p = tmp / "data" / "marketing"
    p.mkdir(parents=True, exist_ok=True)
    (p / "cashtag_tiers.json").write_text(json.dumps({
        "tickers": {t: {"tier": "T2", "proxies": {"adv20_musd": v}}
                    for t, v in advs.items()},
    }), encoding="utf-8")


def _map(tmp: Path, themes: dict, gate: dict | None = None) -> None:
    p = tmp / "data" / "marketing"
    p.mkdir(parents=True, exist_ok=True)
    payload: dict = {"schema": "theme_proxy_map/1", "themes": themes}
    if gate is not None:
        payload["gate"] = gate
    (p / "theme_proxy_map.json").write_text(json.dumps(payload), encoding="utf-8")


def _bars(tmp: Path, tickers: list[str], *, rho: float, n: int = 260,
          seed: int = 7) -> None:
    """Write correlated daily bars: one common factor + idiosyncratic noise.

    ``rho`` is the TARGET pairwise correlation; the factor loading is sqrt(rho),
    which makes the realised mean pairwise correlation land near rho for any
    number of names. The test asserts on the SIDE of the threshold, never on the
    exact value, so sampling noise cannot make it flaky.
    """
    rng = np.random.default_rng(seed)
    d = tmp / "data" / "baskets" / "ohlcv"
    d.mkdir(parents=True, exist_ok=True)
    dates = pd.bdate_range("2025-01-01", periods=n)
    factor = rng.normal(0, 0.01, n)
    load = math.sqrt(max(0.0, min(1.0, rho)))
    for t in tickers:
        r = load * factor + math.sqrt(1 - load ** 2) * rng.normal(0, 0.01, n)
        closes = 100.0 * np.cumprod(1.0 + r)
        pd.DataFrame({"date": dates, "close": closes}).to_parquet(d / f"{t}.parquet")


#: One cohesive cohort with a big fund over it — the shape of the case that
#: prompted the feature (gold miners + $GDX), with the real numbers scaled down.
CARD = ["AAA", "BBB", "CCC", "DDD", "EEE", "FFF"]
NAMED = ["AAA", "BBB", "CCC"]
FUND = "ETFX"


def _holdings_cand(tickers=CARD, *, ticker=FUND, weight=5.0):
    return {"ticker": ticker, "basis": "holdings", "adv20_musd": 1300.0,
            "asof": "2026-07-30", "holdings": list(tickers),
            "weights": {t: weight for t in tickers}}


@pytest.fixture
def cohesive(tmp_path):
    """A theme that SHOULD get a proxy: cohesive rows, fund out-trades the names."""
    _bars(tmp_path, CARD, rho=0.85)
    _tiers(tmp_path, {**{t: 200.0 for t in CARD}, FUND: 1300.0})
    _map(tmp_path, {"T": {"candidates": [_holdings_cand()]}})
    return tmp_path


def _resolve(tmp: Path, *, theme="T", card=None, named=None):
    return tp.resolve(theme, card or CARD, named or NAMED,
                      pmap=tp.load_map(tmp), tiers=tp.load_tiers(tmp), root=tmp)


# ─────────────────────────────────────────────────────────────────────────────
# The happy path
# ─────────────────────────────────────────────────────────────────────────────

def test_a_cohesive_group_with_a_bigger_fund_gets_the_proxy(cohesive):
    got = _resolve(cohesive)
    assert got is not None
    assert got["cashtag"] == f"${FUND}"
    assert got["basis"] == "holdings"
    r = got["receipts"]
    # The receipts are the audit trail; a tag that ships without them cannot be
    # explained to the operator six weeks later.
    assert r["reach_ratio"] == pytest.approx(1300.0 / 200.0, rel=1e-3)
    assert r["cohesion_rho"] > 0.65
    assert r["rows_held"] == len(CARD)
    assert r["weight_coverage_pct"] == pytest.approx(5.0 * len(CARD))


# ─────────────────────────────────────────────────────────────────────────────
# LEG 1 — reach
# ─────────────────────────────────────────────────────────────────────────────

def test_a_fund_smaller_than_the_names_it_would_replace_is_refused(tmp_path):
    """$SIL on a silver card: cohesive, representative, and a SMALLER ticker than
    the $HL already on the card. Mutation check for leg 1 — drop the reach
    comparison and this ships a smaller cashtag wearing a sector badge.

    These are the operator's own numbers: $SIL trades $71M against $HL's $599M,
    which is why $SIL did not survive the sweep despite being suggested by name.
    """
    _bars(tmp_path, CARD, rho=0.85)
    _tiers(tmp_path, {**{t: 599.0 for t in CARD}, FUND: 71.0})
    _map(tmp_path, {"T": {"candidates": [_holdings_cand()]}})
    assert _resolve(tmp_path) is None


def test_reach_is_measured_against_the_NAMED_members_not_the_whole_card(tmp_path):
    """The bar is the biggest ticker the TEXT would have said out loud.

    A mega-cap sitting on the card but NOT in the named set must not veto a proxy
    that beats everything we were actually going to say — and a mega-cap IN the
    named set must. Both directions in one test, because a leg measured against
    the wrong set fails only one of them.
    """
    _bars(tmp_path, CARD + ["MEGA"], rho=0.85)
    _tiers(tmp_path, {**{t: 200.0 for t in CARD}, "MEGA": 90_000.0, FUND: 1300.0})
    _map(tmp_path, {"T": {"candidates": [_holdings_cand(CARD + ["MEGA"])]}})

    on_card_only = _resolve(tmp_path, card=CARD + ["MEGA"], named=NAMED)
    assert on_card_only is not None, "a name we never say cannot veto the proxy"

    also_named = _resolve(tmp_path, card=CARD + ["MEGA"], named=["MEGA"] + NAMED[:2])
    assert also_named is None, "the biggest name we DO say sets the bar"


def test_an_unpriced_named_set_is_unmeasured_not_a_free_pass(tmp_path, caplog):
    """No ADV on anything we are about to name = no denominator for the ratio.

    A ratio against zero is not infinitely good, it is unknown.

    THE `caplog` ASSERTION IS THE REAL TEST, and this test was vacuous without it.
    `reach_ratio` used to be a bare `padv / named_max`, so deleting the
    `named_max <= 0` guard STILL returned None — via ZeroDivisionError into
    resolve's exception handler. The bare `assert ... is None` therefore passed
    under mutation and pinned nothing. Requiring a SILENT refusal separates the
    guard from the crash: with the guard this returns None and logs nothing; with
    the guard removed and the division unguarded it logs "resolve failed", and
    with both removed it ships an unjustified tag and the first assert fires.
    """
    _bars(tmp_path, CARD, rho=0.85)
    _tiers(tmp_path, {FUND: 1300.0})          # members absent from tiers entirely
    _map(tmp_path, {"T": {"candidates": [_holdings_cand()]}})
    with caplog.at_level("WARNING", logger="engine.marketing.theme_proxy"):
        assert _resolve(tmp_path) is None
    assert not [r for r in caplog.records if "resolve failed" in r.getMessage()], \
        "refused by crash, not by the guard: " + str(
            [r.getMessage() for r in caplog.records])


# ─────────────────────────────────────────────────────────────────────────────
# LEG 2 — cohesion
# ─────────────────────────────────────────────────────────────────────────────

def test_a_group_whose_names_do_not_move_together_is_refused(tmp_path):
    """THE $XBI CASE, which is the reason reach alone is not the rule.

    $XBI out-trades every one of its own holdings by 2.5x, so a reach-only gate
    tags it eagerly — but biotech's measured rho_bar is 0.21, the lowest in the
    inventory, because trial and approval risk is idiosyncratic by construction.
    "Biotech is +3% on average, $XBI" would assert a coherence the tape denies.

    Mutation check for leg 2: delete the cohesion comparison and this ships.
    """
    _bars(tmp_path, CARD, rho=0.05)
    _tiers(tmp_path, {**{t: 200.0 for t in CARD}, FUND: 1300.0})
    _map(tmp_path, {"T": {"candidates": [_holdings_cand()]}})
    assert _resolve(tmp_path) is None


def test_cohesion_is_measured_on_the_cards_rows_not_the_whole_theme(tmp_path):
    """The defect an earlier draft of the builder shipped, pinned.

    Cohesion computed over a theme's FULL membership refused every theme in the
    inventory: "Commodities Metals" spans gold, silver, copper, steel, aluminium
    and lithium and scores 0.39 across 51 names, while the eight precious-metals
    rows that actually shipped score 0.81.

    Here the theme has a cohesive core (the card) inside an incoherent sprawl. A
    resolver reading the sprawl refuses; one reading the rows ships.
    """
    sprawl = [f"S{i}" for i in range(10)]
    _bars(tmp_path, CARD, rho=0.85, seed=3)
    _bars(tmp_path, sprawl, rho=0.02, seed=99)
    _tiers(tmp_path, {**{t: 200.0 for t in CARD + sprawl}, FUND: 1300.0})
    _map(tmp_path, {"T": {"candidates": [_holdings_cand(CARD + sprawl)]}})

    assert _resolve(tmp_path, card=CARD) is not None
    # ...and the same theme, asked about the sprawl, is refused. Same map, same
    # fund, same tiers — only the rows differ, which is the whole point.
    assert _resolve(tmp_path, card=sprawl, named=sprawl[:3]) is None


def test_absent_bars_are_unmeasured_and_refuse(tmp_path):
    """A panel too thin to correlate is neither cohesion 0 nor cohesion 1.

    This is a real production path, not a hypothetical: the 2026-08-02 metals card
    was silver-heavy ($CTGO $BVN $SVM $AG) and only 3 of its 8 rows have bars in
    any curated tree, so it resolves to no proxy rather than to a guess.
    """
    _bars(tmp_path, CARD[:2], rho=0.85)      # 2 names < MIN_CORR_NAMES
    _tiers(tmp_path, {**{t: 200.0 for t in CARD}, FUND: 1300.0})
    _map(tmp_path, {"T": {"candidates": [_holdings_cand()]}})
    assert _resolve(tmp_path) is None
    rho, n = tp.cohesion(CARD, tmp_path)
    assert rho is None and n < tp.MIN_CORR_NAMES


# ─────────────────────────────────────────────────────────────────────────────
# LEG 3 — representativeness
# ─────────────────────────────────────────────────────────────────────────────

def test_a_fund_holding_one_row_is_piggybacking_and_is_refused(tmp_path):
    """$SMH on Industrial Automation: holds 1 of 8 rows, 1.8% of the fund.

    The sweep surfaced this as a live "PROXY WINS" hit on reach alone — a single
    coincidental overlap ($SNPS) on an $ETN/$FTNT post. Tagging it is cashtag
    piggybacking, the exact fingerprint max_theme_cashtags_in_text exists to keep
    off the account. Mutation check for the row-coverage half of leg 3.
    """
    _bars(tmp_path, CARD, rho=0.85)
    _tiers(tmp_path, {**{t: 200.0 for t in CARD}, FUND: 1300.0})
    _map(tmp_path, {"T": {"candidates": [_holdings_cand(CARD[:1], weight=40.0)]}})
    assert _resolve(tmp_path) is None


def test_a_fund_with_a_trivial_weight_in_the_rows_is_refused(tmp_path):
    """The OTHER direction of leg 3, and it needs its own test.

    A fund can hold every row and still not be ABOUT them — 8 names at 0.2% each
    is 1.6% of the fund, which is $XOP-on-Commodities-Agriculture (2 of 8 rows,
    1.5% of the fund). Row coverage alone passes this; weight coverage is what
    refuses it. Mutation check: delete the weight comparison and this ships.
    """
    _bars(tmp_path, CARD, rho=0.85)
    _tiers(tmp_path, {**{t: 200.0 for t in CARD}, FUND: 1300.0})
    _map(tmp_path, {"T": {"candidates": [_holdings_cand(weight=0.2)]}})
    assert _resolve(tmp_path) is None


def test_a_declared_commodity_proxy_skips_holdings_but_not_reach_or_cohesion(tmp_path):
    """$GLD on gold miners: bullion holds metal, so no holdings test can select it.

    The declared class is exempt from leg 3 BY DESIGN — and from nothing else. The
    second half of this test is the part that matters: an incohesive group gets no
    declared proxy either, so "declared" is not a bypass around the whole gate.
    """
    _bars(tmp_path, CARD, rho=0.85, seed=11)
    _tiers(tmp_path, {**{t: 200.0 for t in CARD}, "BULL": 2300.0})
    declared = {"ticker": "BULL", "basis": "declared", "adv20_musd": 2300.0}
    _map(tmp_path, {"T": {"candidates": [declared]}})
    got = _resolve(tmp_path)
    assert got is not None and got["cashtag"] == "$BULL"
    assert got["basis"] == "declared"
    assert "rows_held" not in got["receipts"], "no holdings receipt to claim"

    _bars(tmp_path, CARD, rho=0.03, seed=12)  # same map, incohesive rows
    assert _resolve(tmp_path) is None


def test_an_unknown_basis_fails_closed(tmp_path):
    """A basis this module does not implement must not inherit the declared
    class's holdings exemption. Mutation check: change the final `continue` to a
    return and a map typo becomes an unverified tag."""
    _bars(tmp_path, CARD, rho=0.85)
    _tiers(tmp_path, {**{t: 200.0 for t in CARD}, FUND: 1300.0})
    _map(tmp_path, {"T": {"candidates": [
        {"ticker": FUND, "basis": "vibes", "adv20_musd": 1300.0}]}})
    assert _resolve(tmp_path) is None


# ─────────────────────────────────────────────────────────────────────────────
# Selection among candidates
# ─────────────────────────────────────────────────────────────────────────────

def test_the_most_traded_qualifying_candidate_wins(tmp_path):
    """Reach is the objective, so among candidates that all clear the gate the
    biggest ticker is the answer — and map ORDER must not decide it. The map here
    lists the small fund first, which is what a stale builder run looks like."""
    _bars(tmp_path, CARD, rho=0.85)
    _tiers(tmp_path, {**{t: 200.0 for t in CARD}, "SMALL": 300.0, "BIG": 1300.0})
    _map(tmp_path, {"T": {"candidates": [
        _holdings_cand(ticker="SMALL"), _holdings_cand(ticker="BIG")]}})
    got = _resolve(tmp_path)
    assert got is not None and got["ticker"] == "BIG"


def test_a_failing_big_candidate_falls_through_to_a_passing_smaller_one(tmp_path):
    """One bad candidate must not veto the theme. The biggest fund here holds a
    single row (piggyback); the next one holds them all and should ship."""
    _bars(tmp_path, CARD, rho=0.85)
    _tiers(tmp_path, {**{t: 200.0 for t in CARD}, "HUGE": 9000.0, "FITS": 1300.0})
    _map(tmp_path, {"T": {"candidates": [
        _holdings_cand(CARD[:1], ticker="HUGE", weight=40.0),
        _holdings_cand(ticker="FITS")]}})
    got = _resolve(tmp_path)
    assert got is not None and got["ticker"] == "FITS"


# ─────────────────────────────────────────────────────────────────────────────
# Config + fail-soft
# ─────────────────────────────────────────────────────────────────────────────

def test_the_gate_is_data_driven(cohesive):
    """An operator retune of the map's own gate block changes the answer with no
    deploy. Pinned by raising the cohesion floor above the fixture's rho."""
    _map(cohesive, {"T": {"candidates": [_holdings_cand()]}},
         gate={"min_cohesion": 0.99})
    assert _resolve(cohesive) is None


def test_one_bad_gate_value_does_not_ungate_the_other_legs(cohesive):
    """Per-key degradation. A junk `min_row_coverage` must not take the cohesion
    floor down with it — a wholesale fallback-to-defaults would be fine here, but
    a wholesale fallback to `{}` would open all four legs at once."""
    _map(cohesive, {"T": {"candidates": [_holdings_cand()]}},
         gate={"min_row_coverage": "not-a-number", "min_cohesion": 0.99})
    assert tp.gate_of(tp.load_map(cohesive))["min_row_coverage"] == \
        tp.DEFAULT_GATE["min_row_coverage"]
    assert _resolve(cohesive) is None, "the good key still gates"


@pytest.mark.parametrize("mutate", [
    pytest.param(lambda p: (p / "data/marketing/theme_proxy_map.json").unlink(),
                 id="map-absent"),
    pytest.param(lambda p: (p / "data/marketing/theme_proxy_map.json").write_text(
        "{not json", encoding="utf-8"), id="map-corrupt"),
    pytest.param(lambda p: (p / "data/marketing/theme_proxy_map.json").write_text(
        json.dumps({"themes": {"T": {"candidates": "nope"}}}), encoding="utf-8"),
        id="candidates-wrong-type"),
    pytest.param(lambda p: (p / "data/marketing/cashtag_tiers.json").unlink(),
                 id="tiers-absent"),
])
def test_every_broken_input_degrades_to_no_proxy(cohesive, mutate):
    """A tag is never worth a dropped post. Each of these returns None and the
    caller posts exactly what it posted before the feature existed."""
    mutate(cohesive)
    assert _resolve(cohesive) is None


def test_an_unknown_theme_is_not_an_error(cohesive):
    assert _resolve(cohesive, theme="Theme That Does Not Exist") is None


def test_resolve_never_raises_on_a_malformed_candidate(cohesive):
    _map(cohesive, {"T": {"candidates": [
        {"ticker": FUND, "basis": "holdings", "holdings": None, "weights": 17}]}})
    assert _resolve(cohesive) is None


def test_broad_index_funds_are_not_theme_proxies():
    """$SPY on 'Artificial Intelligence' would pass a naive weight test through
    mega-cap overlap alone. The builder's exclusion list is the guard; this pins
    the membership so a future edit cannot quietly drop one."""
    from scripts import build_theme_proxy_map as b
    for t in ("SPY", "QQQ", "DIA", "RSP", "IWM", "VTI"):
        assert t in b.BROAD


def test_the_non_instrument_cashtags_stay_out_of_the_declared_map():
    """$GOLD and $SILVER are NOT instruments. `GOLD` is absent from the cashtag
    universe because Barrick renamed to `$B`, so the cashtag is a stale-ticker
    collision carrying another company's history; `SILVER` was never a US ticker.
    Both resolve to X search surfaces, which makes them a real reach question —
    and they still have no price, no card row and nothing the engine can verify,
    so they stay out until an operator asks for a non-instrument class by name."""
    from scripts import build_theme_proxy_map as b
    declared = {t for v in b.DECLARED.values() for t in v}
    assert not declared & {"GOLD", "SILVER", "OIL", "COPPER"}
