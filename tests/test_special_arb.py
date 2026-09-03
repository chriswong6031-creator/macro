"""F09-1 — evidence-bound cash-deal economics.

The suite is written as MUTANTS: each test is a way the old ungrounded lane published a
confident wrong number, and it fails if that path ever reopens. The gate that matters most is
`test_precision_corpus_publishes_no_false_price` — zero false precise publications over the
whole reviewed corpus. Recall is allowed to be incomplete and is reported honestly.
"""
from __future__ import annotations

import json
from datetime import date
from pathlib import Path

import pytest

from engine import special_arb as arb

CORPUS = json.loads(
    (Path(__file__).parent / "fixtures/special_situations/f09/corpus.json").read_text())["cases"]
ASOF = date(2026, 9, 1)


def _src(case: dict) -> dict:
    return arb.source_descriptor(
        cik="0000320193", form_type=case["form_type"], accession=case["accession"],
        filing_date=case["filing_date"], source_url=f"https://sec.gov/{case['accession']}.txt",
        body=case["text"], acquired_at="2026-09-02T00:00:00Z")


def _obs(case: dict) -> list[dict]:
    return arb.extract_term_observations(case["text"], source=_src(case),
                                         listing_currency=case.get("listing_currency"),
                                         recorded_at="2026-09-02T00:00:00Z")


def _case(cid: str) -> dict:
    return next(c for c in CORPUS if c["id"] == cid)


def _price(value=15.19, session="2026-09-01", currency="USD", behind=0, basis="close_raw"):
    return arb.price_input(ticker="T", session=session, value=value, currency=currency,
                           basis=basis, source_artifact="breadth/_closes_cache.parquet",
                           sessions_behind=behind, expected_session="2026-09-01")


# ---------------------------------------------------------------- grounding

def test_no_observation_means_no_number():
    """The core rule: without source-bound observations there is nothing to publish."""
    compiled = arb.compile_current_terms([])
    assert compiled["status"] == "unavailable"
    r = arb.reduce_cash_deal(compiled, category="Acquisitions", live_price=_price(), asof=ASOF)
    assert r["quality_state"] == arb.QUALITY_SOURCE_UNAVAILABLE
    assert r["offer_price"] is None and r["annualized_pct"] is None


def test_llm_terms_are_candidate_only_and_never_authority():
    t = arb.parse_terms({"price_per_share": 25.0, "currency": "usd", "consideration": "cash"})
    assert t["_candidate_only"] is True
    # a candidate dict is not an observation, so it cannot compile into current terms
    assert arb.compile_current_terms([t])["status"] == "unavailable"


def test_every_published_number_carries_an_exact_locator():
    for o in _obs(_case("cash_acquisition_exact_date")):
        loc = o["locator"]
        assert loc["end"] > loc["start"] >= 0
        assert loc["excerpt_sha256"] and len(loc["excerpt_sha256"]) == 64
        assert o["source"]["body_sha256"] and o["source"]["accession"]


def test_body_change_under_a_constant_accession_changes_the_observation_id():
    """URL + accession are not identity — the bytes are."""
    c = _case("cash_acquisition_exact_date")
    a = _obs(c)
    tampered = dict(c, text=c["text"].replace("$25.00", "$28.00"))
    b = _obs(tampered)
    assert a[0]["source"]["body_sha256"] != b[0]["source"]["body_sha256"]
    assert a[0]["observation_id"] != b[0]["observation_id"]


@pytest.mark.parametrize("cid", ["dividend_negative", "redemption_negative",
                                 "exercise_price_negative", "aggregate_value_negative"])
def test_negative_lexicon_blocks_lookalike_prices(cid):
    assert [o for o in _obs(_case(cid)) if o["field"] == "price_per_share"] == []


def test_two_disagreeing_spans_refuse_rather_than_pick():
    compiled = arb.compile_current_terms(_obs(_case("conflicting_candidate_prices")))
    assert "TERM_AMBIGUOUS" in compiled["reasons"]
    assert "price_per_share" not in compiled["terms"]


# ---------------------------------------------------------------- consideration / currency

@pytest.mark.parametrize("cid", ["stock_only_merger", "cash_and_stock_merger",
                                 "contingent_value_right"])
def test_non_fixed_cash_never_enters_fixed_price_math(cid):
    compiled = arb.compile_current_terms(_obs(_case(cid)))
    r = arb.reduce_cash_deal(compiled, category="Acquisitions", live_price=_price(), asof=ASOF)
    assert r["quality_state"] == arb.QUALITY_NOT_FIXED_CASH
    assert r["live_gross_spread_pct"] is None and r["annualized_pct"] is None


def test_bare_dollar_on_a_foreign_listing_is_not_a_currency():
    compiled = arb.compile_current_terms(_obs(_case("cross_currency_bare_dollar")))
    assert compiled["terms"].get("currency") is None
    r = arb.reduce_cash_deal(compiled, category="Acquisitions",
                             live_price=_price(currency="CAD"), asof=ASOF)
    assert r["quality_state"] == arb.QUALITY_AMBIGUOUS


def test_explicit_currency_token_is_observed():
    compiled = arb.compile_current_terms(_obs(_case("explicit_foreign_currency")))
    assert compiled["terms"]["currency"] == "CAD"
    assert compiled["evidence"]["price_per_share"]["currency_basis"] == "explicit_token"


def test_price_currency_mismatch_is_refused():
    compiled = arb.compile_current_terms(_obs(_case("cash_acquisition_exact_date")))
    r = arb.reduce_cash_deal(compiled, category="Acquisitions",
                             live_price=_price(currency="CAD"), asof=ASOF)
    assert r["quality_state"] == arb.QUALITY_AMBIGUOUS
    assert "CURRENCY_MISMATCH" in r["reasons"]


def test_per_ads_versus_per_share_is_ambiguous_not_a_guess():
    compiled = arb.compile_current_terms(_obs(_case("per_ads_versus_per_share")))
    r = arb.reduce_cash_deal(compiled, category="Acquisitions", live_price=_price(), asof=ASOF)
    assert r["quality_state"] == arb.QUALITY_AMBIGUOUS


# ---------------------------------------------------------------- time and price

def test_month_only_close_is_a_window_not_a_month_end():
    """The exact defect behind 42,790.2%: an unobserved day became a precise denominator."""
    compiled = arb.compile_current_terms(_obs(_case("month_only_close")))
    assert compiled["terms"]["expected_close"] == "2026-11"
    assert compiled["terms"]["expected_close_precision"] == arb.PRECISION_MONTH
    r = arb.reduce_cash_deal(compiled, category="Acquisitions", live_price=_price(), asof=ASOF)
    assert r["days_to_close"] is None and r["annualized_pct"] is None
    assert "DATE_PRECISION_INSUFFICIENT" in r["reasons"]
    assert r["orderable"] is False
    assert arb.days_to_close("2026-11", ASOF) is None      # the substitution is gone entirely


def test_quarter_and_vague_closes_never_annualize():
    for cid in ("going_private_13e3", "vague_close"):
        compiled = arb.compile_current_terms(_obs(_case(cid)))
        r = arb.reduce_cash_deal(compiled, category="Acquisitions", live_price=_price(),
                                 asof=ASOF)
        assert r["annualized_pct"] is None and r["days_to_close"] is None


def test_exact_date_annualizes_with_its_receipts():
    compiled = arb.compile_current_terms(_obs(_case("cash_acquisition_exact_date")))
    r = arb.reduce_cash_deal(compiled, category="Acquisitions", stage="pending",
                             live_price=_price(), reference_price=_price(session="2026-09-01"),
                             availability_session="2026-09-02", asof=ASOF)
    assert r["quality_state"] == arb.QUALITY_VERIFIED and r["orderable"] is True
    assert r["days_to_close"] == 105
    assert r["live_session"] == "2026-09-01" and r["price_basis"] == "close_raw"
    assert r["formula_revision"] == arb.FORMULA_REVISION


def test_stale_price_is_visible_context_but_never_ordered():
    compiled = arb.compile_current_terms(_obs(_case("cash_acquisition_exact_date")))
    r = arb.reduce_cash_deal(compiled, category="Acquisitions", live_price=_price(behind=1),
                             asof=ASOF)
    assert r["quality_state"] == arb.QUALITY_STALE_PRICE
    assert "PRICE_STALE" in r["reasons"]
    assert r["live_gross_spread_pct"] is not None      # still visible …
    assert r["orderable"] is False                     # … but never in the ordered book


def test_missing_and_future_prices_are_typed_not_silent():
    compiled = arb.compile_current_terms(_obs(_case("cash_acquisition_exact_date")))
    missing = arb.reduce_cash_deal(compiled, category="Acquisitions", live_price=None, asof=ASOF)
    assert missing["quality_state"] == arb.QUALITY_CALCULATION_UNAVAILABLE
    assert "PRICE_MISSING" in missing["reasons"]
    future = arb.reduce_cash_deal(compiled, category="Acquisitions",
                                  live_price=_price(session="2026-09-30"), asof=ASOF)
    assert future["quality_state"] == arb.QUALITY_CALCULATION_UNAVAILABLE


def test_incompatible_price_bases_are_never_mixed():
    compiled = arb.compile_current_terms(_obs(_case("cash_acquisition_exact_date")))
    r = arb.reduce_cash_deal(compiled, category="Acquisitions", live_price=_price(),
                             reference_price=_price(session="2026-08-29", basis="total_return"),
                             availability_session="2026-09-02", asof=ASOF)
    assert r["quality_state"] == arb.QUALITY_CALCULATION_UNAVAILABLE
    assert "PRICE_BASIS_UNRESOLVED" in r["reasons"]


def test_filing_day_close_is_not_a_reference_price():
    """A close on or after SEC availability already contains the announcement."""
    compiled = arb.compile_current_terms(_obs(_case("cash_acquisition_exact_date")))
    r = arb.reduce_cash_deal(compiled, category="Acquisitions", live_price=_price(),
                             reference_price=_price(session="2026-09-02"),
                             availability_session="2026-09-02", asof=ASOF)
    assert r["filing_reference_premium_pct"] is None
    assert "REFERENCE_SESSION_UNRESOLVED" in r["reasons"]


def test_stated_premium_is_never_the_computed_premium():
    compiled = arb.compile_current_terms(_obs(_case("cash_acquisition_exact_date")))
    r = arb.reduce_cash_deal(compiled, category="Acquisitions", live_price=_price(),
                             reference_price=_price(session="2026-08-29"),
                             availability_session="2026-09-02", asof=ASOF)
    assert r["stated_premium_pct"] == 45.0                       # what the filing claims
    assert r["filing_reference_premium_pct"] != r["stated_premium_pct"]
    assert r["live_gross_spread_pct"] != r["stated_premium_pct"]


# ---------------------------------------------------------------- correction and lineage

def test_amendment_supersedes_without_editing_history():
    first = _obs(_case("cash_acquisition_exact_date"))
    amended = _obs(_case("amendment_price_increase"))
    compiled = arb.compile_current_terms(first + amended)
    assert compiled["terms"]["price_per_share"] == 27.5          # newest accession wins
    assert len(compiled["amendment_chain"]) == 2
    assert all(o["observation_id"] for o in first)               # history intact, not rewritten


def test_retraction_removes_the_current_term_but_keeps_the_receipt():
    base = _obs(_case("cash_acquisition_exact_date"))
    price = next(o for o in base if o["field"] == "price_per_share")
    retraction = dict(price, status="retracted", observation_id=price["observation_id"] + "r",
                      source=dict(price["source"], accession="0000000001-26-000099",
                                  filing_date="2026-09-25"),
                      correction_reason="offer withdrawn")
    compiled = arb.compile_current_terms(base + [retraction])
    assert "RETRACTED" in compiled["reasons"]
    assert "price_per_share" not in compiled["terms"]


def test_terminal_deal_leaves_current_context():
    compiled = arb.compile_current_terms(_obs(_case("terminated_offer")))
    r = arb.reduce_cash_deal(compiled, category="Acquisitions", stage="terminated",
                             live_price=_price(), asof=ASOF)
    assert r["quality_state"] == arb.QUALITY_TERMINAL and r["orderable"] is False


def test_identical_rebuild_is_byte_stable_and_appends_no_duplicate():
    c = _case("cash_acquisition_exact_date")
    a = {o["observation_id"] for o in _obs(c)}
    b = {o["observation_id"] for o in _obs(c)}
    assert a == b and len(a) == len(_obs(c))


def test_ineligible_category_is_typed():
    compiled = arb.compile_current_terms(_obs(_case("cash_acquisition_exact_date")))
    r = arb.reduce_cash_deal(compiled, category="Capital Returns", live_price=_price(), asof=ASOF)
    assert r["quality_state"] == arb.QUALITY_INELIGIBLE


# ---------------------------------------------------------------- one ordered projection

def _row(ticker, econ):
    return {"ticker": ticker, "company": ticker, "category": "Acquisitions", "arb": econ}


def test_null_annualized_never_sorts_as_zero_into_the_verified_set():
    compiled = arb.compile_current_terms(_obs(_case("cash_acquisition_exact_date")))
    verified = arb.reduce_cash_deal(compiled, category="Acquisitions", live_price=_price(),
                                    asof=ASOF)
    windowed = arb.reduce_cash_deal(
        arb.compile_current_terms(_obs(_case("month_only_close"))), category="Acquisitions",
        live_price=_price(), asof=ASOF)
    ordered, counts = arb.select_ordered_context([_row("WIN", windowed), _row("OK", verified)])
    assert [r["ticker"] for r in ordered] == ["OK"]
    assert counts["excluded"] == 1 and counts["considered"] == 2


def test_ordered_rows_carry_quality_provenance_and_freshness():
    compiled = arb.compile_current_terms(_obs(_case("cash_acquisition_exact_date")))
    econ = arb.reduce_cash_deal(compiled, category="Acquisitions", live_price=_price(),
                                reference_price=_price(session="2026-08-29"),
                                availability_session="2026-09-02", asof=ASOF)
    row = arb.context_row(_row("OK", econ))
    for k in ("quality_state", "accession", "live_session", "price_basis", "sessions_behind",
              "formula_revision", "calc_asof", "expected_close_precision", "source_url"):
        assert k in row
    assert row["is_signal"] is False and row["is_context_only"] is True
    assert row["display_order_basis"] == "annualized_pct"


def test_removing_source_identity_does_not_leave_machine_context_green():
    c = dict(_case("cash_acquisition_exact_date"))
    obs = _obs(c)
    for o in obs:                       # strip the byte binding, keep everything else
        o["source"] = dict(o["source"], body_sha256=None, accession=None)
    compiled = arb.compile_current_terms(obs)
    assert "SOURCE_BYTES_UNAVAILABLE" in compiled["reasons"]
    econ = arb.reduce_cash_deal(compiled, category="Acquisitions", live_price=_price(), asof=ASOF)
    assert econ["quality_state"] == arb.QUALITY_SOURCE_UNAVAILABLE
    assert econ["orderable"] is False and econ["annualized_pct"] is None
    assert arb.select_ordered_context([_row("X", econ)])[0] == []


# ---------------------------------------------------------------- the current regression

def test_lgmk_shape_cannot_reproduce_without_an_observed_exact_date():
    """The live artifact published 64.57% gross / 42,790.2% annualized on a 30-day close that
    no filing ever stated. With the same offer and price but no observed exact date, the row
    is not orderable and no annualized number exists at all."""
    c = dict(_case("month_only_close"), text=_case("month_only_close")["text"]
             .replace("$40.00", "$25.00"))
    econ = arb.reduce_cash_deal(arb.compile_current_terms(_obs(c)), category="Acquisitions",
                                live_price=_price(value=15.19), asof=ASOF)
    assert econ["live_gross_spread_pct"] == pytest.approx(64.58, abs=0.02)
    assert econ["annualized_pct"] is None and econ["orderable"] is False
    ordered, counts = arb.select_ordered_context([_row("LGMK", econ)])
    assert ordered == [] and counts["excluded"] == 1


def test_no_clamp_no_band_no_ticker_exception_in_the_owner():
    src = Path(arb.__file__).read_text()
    assert "LGMK" not in src, "a hard-coded ticker exception is not a fix"
    for banned in ("_PLAUS_LO", "_PLAUS_HI", "_DAYS_CAP"):
        assert banned not in src, f"{banned} is a clamp; the receipt is the fix"


def test_an_extreme_but_fully_grounded_value_is_disclosed_not_hidden():
    """A real, receipted extreme value must still publish — flagged, never banded away."""
    c = dict(_case("cash_acquisition_exact_date"),
             text=_case("cash_acquisition_exact_date")["text"]
             .replace("December 15, 2026", "September 15, 2026"))
    econ = arb.reduce_cash_deal(arb.compile_current_terms(_obs(c)), category="Acquisitions",
                                live_price=_price(value=15.19), asof=ASOF)
    assert econ["annualized_pct"] > 1000 and econ["extreme_value"] is True
    assert econ["quality_state"] == arb.QUALITY_VERIFIED     # grounded, so it is published


# ---------------------------------------------------------------- the precision gate

def test_precision_corpus_publishes_no_false_price():
    """Zero false precise numeric publications over the whole reviewed corpus."""
    wrong = []
    for case in CORPUS:
        compiled = arb.compile_current_terms(_obs(case))
        got = compiled["terms"].get("price_per_share")
        want = case["expect"].get("price_per_share", "unspecified")
        if want == "unspecified":
            continue
        if got != want:
            wrong.append((case["id"], want, got))
    assert not wrong, f"false or missed precise publications: {wrong}"


def test_precision_corpus_close_precision_is_never_overstated():
    for case in CORPUS:
        want = case["expect"].get("close_precision")
        if not want:
            continue
        compiled = arb.compile_current_terms(_obs(case))
        assert compiled["terms"].get("expected_close_precision") == want, case["id"]
