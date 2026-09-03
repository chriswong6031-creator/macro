"""F09-1 — evidence-bound cash-deal economics.

The suite is written as MUTANTS: each test is a way the old ungrounded lane published a
confident wrong number, and it fails if that path ever reopens. The gate that matters most is
`test_precision_corpus_publishes_no_false_price` — zero false precise publications over the
whole reviewed corpus. Recall is allowed to be incomplete and is reported honestly.
"""
from __future__ import annotations

import json
from datetime import date, datetime, timezone
from pathlib import Path

import pytest

from engine import special_arb as arb
from engine import special_situations as sse

CORPUS = json.loads(
    (Path(__file__).parent / "fixtures/special_situations/f09/corpus.json").read_text())["cases"]
ASOF = date(2026, 9, 1)
_CASH_EXACT = ("Each share of common stock will be converted into the right to receive $25.00 "
               "in cash per share. The transaction is expected to close on December 15, 2026.")
NOW = datetime(2026, 6, 18, 22, 0, tzinfo=timezone.utc)   # explicit market clock, never date.today()


def _src(case: dict) -> dict:
    """A COMPLETE retained source object with its acceptance moment — the shape the repaired
    contract requires before any precise term may be called verified."""
    return arb.source_descriptor(
        cik="0000320193", form_type=case["form_type"], accession=case["accession"],
        filing_date=case["filing_date"], source_url=f"https://sec.gov/{case['accession']}.txt",
        body=case["text"], acquired_at="2026-09-02T00:00:00Z",
        raw_sha256="a" * 64, raw_bytes=len(case["text"]) * 3,
        acceptance_datetime=f"{case['filing_date']}T17:31:00-04:00")


def _obs(case: dict) -> list[dict]:
    return arb.extract_term_observations(case["text"], source=_src(case),
                                         listing_currency=case.get("listing_currency"),
                                         recorded_at="2026-09-02T00:00:00Z")


def _case(cid: str) -> dict:
    return next(c for c in CORPUS if c["id"] == cid)


def _price(value=15.19, session="2026-09-01", currency="USD", behind=0, basis="close_raw"):
    """A price carrying an INDEPENDENT calendar receipt and an immutable artifact digest."""
    return arb.price_input(ticker="T", session=session, value=value, currency=currency,
                           basis=basis, source_artifact="breadth/_closes_cache.parquet",
                           artifact_sha256="b" * 64, sessions_behind=behind,
                           expected_session="2026-09-01", calendar_owner="lib/nyse_calendar.py",
                           calendar_revision="nyse_calendar.v1", calendar_id="XNYS")


# ---------------------------------------------------------------- grounding

def test_no_observation_means_no_number():
    """The core rule: without source-bound observations there is nothing to publish."""
    compiled = arb.compile_current_terms([])
    assert compiled["status"] == "unavailable"
    r = arb.reduce_cash_deal(compiled, category="Acquisitions", live_price=_price(), market_session=ASOF, now_utc=NOW)
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
    r = arb.reduce_cash_deal(compiled, category="Acquisitions", live_price=_price(), market_session=ASOF, now_utc=NOW)
    assert r["quality_state"] == arb.QUALITY_NOT_FIXED_CASH
    assert r["live_gross_spread_pct"] is None and r["annualized_pct"] is None


def test_bare_dollar_on_a_foreign_listing_is_not_a_currency():
    compiled = arb.compile_current_terms(_obs(_case("cross_currency_bare_dollar")))
    assert compiled["terms"].get("currency") is None
    r = arb.reduce_cash_deal(compiled, category="Acquisitions",
                             live_price=_price(currency="CAD"), market_session=ASOF, now_utc=NOW)
    assert r["quality_state"] == arb.QUALITY_AMBIGUOUS


def test_explicit_currency_token_is_observed():
    compiled = arb.compile_current_terms(_obs(_case("explicit_foreign_currency")))
    assert compiled["terms"]["currency"] == "CAD"
    assert compiled["evidence"]["price_per_share"]["currency_basis"] == "explicit_token"


def test_price_currency_mismatch_is_refused():
    compiled = arb.compile_current_terms(_obs(_case("cash_acquisition_exact_date")))
    r = arb.reduce_cash_deal(compiled, category="Acquisitions",
                             live_price=_price(currency="CAD"), market_session=ASOF, now_utc=NOW)
    assert r["quality_state"] == arb.QUALITY_AMBIGUOUS
    assert "CURRENCY_MISMATCH" in r["reasons"]


def test_per_ads_versus_per_share_is_ambiguous_not_a_guess():
    compiled = arb.compile_current_terms(_obs(_case("per_ads_versus_per_share")))
    r = arb.reduce_cash_deal(compiled, category="Acquisitions", live_price=_price(), market_session=ASOF, now_utc=NOW)
    assert r["quality_state"] == arb.QUALITY_AMBIGUOUS


# ---------------------------------------------------------------- time and price

def test_month_only_close_is_a_window_not_a_month_end():
    """The exact defect behind 42,790.2%: an unobserved day became a precise denominator."""
    compiled = arb.compile_current_terms(_obs(_case("month_only_close")))
    assert compiled["terms"]["expected_close"] == "2026-11"
    assert compiled["terms"]["expected_close_precision"] == arb.PRECISION_MONTH
    r = arb.reduce_cash_deal(compiled, category="Acquisitions", live_price=_price(), market_session=ASOF, now_utc=NOW)
    assert r["days_to_close"] is None and r["annualized_pct"] is None
    assert "DATE_PRECISION_INSUFFICIENT" in r["reasons"]
    assert r["orderable"] is False
    assert arb.days_to_close("2026-11", ASOF) is None      # the substitution is gone entirely


def test_quarter_and_vague_closes_never_annualize():
    for cid in ("going_private_13e3", "vague_close"):
        compiled = arb.compile_current_terms(_obs(_case(cid)))
        r = arb.reduce_cash_deal(compiled, category="Acquisitions", live_price=_price(),
                                 market_session=ASOF, now_utc=NOW)
        assert r["annualized_pct"] is None and r["days_to_close"] is None


def test_exact_date_annualizes_with_its_receipts():
    compiled = arb.compile_current_terms(_obs(_case("cash_acquisition_exact_date")))
    r = arb.reduce_cash_deal(compiled, category="Acquisitions", stage="pending",
                             live_price=_price(), reference_price=_price(session="2026-09-01"), market_session=ASOF, now_utc=NOW)
    assert r["quality_state"] == arb.QUALITY_VERIFIED and r["orderable"] is True
    assert r["days_to_close"] == 105
    assert r["live_session"] == "2026-09-01" and r["price_basis"] == "close_raw"
    assert r["formula_revision"] == arb.FORMULA_REVISION


def test_stale_price_is_visible_context_but_never_ordered():
    compiled = arb.compile_current_terms(_obs(_case("cash_acquisition_exact_date")))
    r = arb.reduce_cash_deal(compiled, category="Acquisitions", live_price=_price(behind=1),
                             market_session=ASOF, now_utc=NOW)
    assert r["quality_state"] == arb.QUALITY_STALE_PRICE
    assert "PRICE_STALE" in r["reasons"]
    assert r["live_gross_spread_pct"] is not None      # still visible …
    assert r["orderable"] is False                     # … but never in the ordered book


def test_missing_and_future_prices_are_typed_not_silent():
    compiled = arb.compile_current_terms(_obs(_case("cash_acquisition_exact_date")))
    missing = arb.reduce_cash_deal(compiled, category="Acquisitions", live_price=None, market_session=ASOF, now_utc=NOW)
    assert missing["quality_state"] == arb.QUALITY_CALCULATION_UNAVAILABLE
    assert "PRICE_MISSING" in missing["reasons"]
    future = arb.reduce_cash_deal(compiled, category="Acquisitions",
                                  live_price=_price(session="2026-09-30"), market_session=ASOF, now_utc=NOW)
    assert future["quality_state"] == arb.QUALITY_CALCULATION_UNAVAILABLE


def test_incompatible_price_bases_are_never_mixed():
    compiled = arb.compile_current_terms(_obs(_case("cash_acquisition_exact_date")))
    r = arb.reduce_cash_deal(compiled, category="Acquisitions", live_price=_price(),
                             reference_price=_price(session="2026-08-29", basis="total_return"), market_session=ASOF, now_utc=NOW)
    assert r["quality_state"] == arb.QUALITY_CALCULATION_UNAVAILABLE
    assert "PRICE_BASIS_UNRESOLVED" in r["reasons"]


def test_a_reference_session_must_have_closed_before_sec_availability():
    """Only the exact acceptance MOMENT can decide this. The corpus filings accept at 17:31 ET,
    after the close, so that day's close precedes availability and IS a valid reference. A
    date-only value decides nothing and is refused outright (see the repair mutants below)."""
    compiled = arb.compile_current_terms(_obs(_case("cash_acquisition_exact_date")))
    after_close = arb.reduce_cash_deal(compiled, category="Acquisitions", live_price=_price(),
                                       reference_price=_price(session="2026-09-02"),
                                       market_session=ASOF, now_utc=NOW)
    assert after_close["filing_reference_premium_pct"] is not None
    assert after_close["acceptance_datetime"].endswith("17:31:00-04:00")
    # a session AFTER availability already contains the announcement, so it is never a reference
    later = arb.reduce_cash_deal(compiled, category="Acquisitions", live_price=_price(),
                                 reference_price=_price(session="2026-09-03"),
                                 market_session=ASOF, now_utc=NOW)
    assert later["filing_reference_premium_pct"] is None
    assert "REFERENCE_SESSION_UNRESOLVED" in later["reasons"]


def test_stated_premium_is_never_the_computed_premium():
    compiled = arb.compile_current_terms(_obs(_case("cash_acquisition_exact_date")))
    r = arb.reduce_cash_deal(compiled, category="Acquisitions", live_price=_price(),
                             reference_price=_price(session="2026-08-29"), market_session=ASOF, now_utc=NOW)
    assert r["stated_premium_pct"] == 45.0                       # what the filing claims
    assert r["filing_reference_premium_pct"] != r["stated_premium_pct"]
    assert r["live_gross_spread_pct"] != r["stated_premium_pct"]


# ---------------------------------------------------------------- correction and lineage

def test_amendment_supersedes_without_editing_history():
    """Lineage is opt-in and evidenced. Two accessions only merge through an explicit
    source-linked supersession — a shared issuer or an `/A` form is not a relation."""
    first = _obs(_case("cash_acquisition_exact_date"))
    amended = arb.link_supersession(_obs(_case("amendment_price_increase")), first)
    compiled = arb.compile_current_terms(first + amended)
    assert compiled["terms"]["price_per_share"] == 27.5          # linked amendment wins
    assert len(compiled["amendment_chain"]) == 2
    assert all(o["observation_id"] for o in first)               # history intact, not rewritten


def test_retraction_removes_the_current_term_but_keeps_the_receipt():
    base = _obs(_case("cash_acquisition_exact_date"))
    price = next(o for o in base if o["field"] == "price_per_share")
    src = dict(price["source"], accession="0000000001-26-000099", filing_date="2026-09-25")
    retraction = dict(price, status="retracted", source=src,
                      supersedes_observation_id=price["observation_id"],
                      prior_observation_id=price["observation_id"],
                      correction_reason="offer withdrawn")
    retraction["observation_id"] = arb.observation_id(
        source=src, field=retraction["field"], locator=retraction["locator"],
        normalized=retraction["normalized"])
    assert arb.validate_observation(retraction)      # a correction is evidenced, not asserted
    compiled = arb.compile_current_terms(base + [retraction])
    assert "RETRACTED" in compiled["reasons"]
    assert "price_per_share" not in compiled["terms"]


def test_terminal_deal_leaves_current_context():
    compiled = arb.compile_current_terms(_obs(_case("terminated_offer")))
    r = arb.reduce_cash_deal(compiled, category="Acquisitions", stage="terminated",
                             live_price=_price(), market_session=ASOF, now_utc=NOW)
    assert r["quality_state"] == arb.QUALITY_TERMINAL and r["orderable"] is False


def test_identical_rebuild_is_byte_stable_and_appends_no_duplicate():
    c = _case("cash_acquisition_exact_date")
    a = {o["observation_id"] for o in _obs(c)}
    b = {o["observation_id"] for o in _obs(c)}
    assert a == b and len(a) == len(_obs(c))


def test_ineligible_category_is_typed():
    compiled = arb.compile_current_terms(_obs(_case("cash_acquisition_exact_date")))
    r = arb.reduce_cash_deal(compiled, category="Capital Returns", live_price=_price(), market_session=ASOF, now_utc=NOW)
    assert r["quality_state"] == arb.QUALITY_INELIGIBLE


# ---------------------------------------------------------------- one ordered projection

def _row(ticker, econ):
    return {"ticker": ticker, "company": ticker, "category": "Acquisitions", "arb": econ}


def test_null_annualized_never_sorts_as_zero_into_the_verified_set():
    compiled = arb.compile_current_terms(_obs(_case("cash_acquisition_exact_date")))
    verified = arb.reduce_cash_deal(compiled, category="Acquisitions", live_price=_price(),
                                    market_session=ASOF, now_utc=NOW)
    windowed = arb.reduce_cash_deal(
        arb.compile_current_terms(_obs(_case("month_only_close"))), category="Acquisitions",
        live_price=_price(), market_session=ASOF, now_utc=NOW)
    ordered, counts = arb.select_ordered_context([_row("WIN", windowed), _row("OK", verified)])
    assert [r["ticker"] for r in ordered] == ["OK"]
    assert counts["excluded"] == 1 and counts["considered"] == 2


def test_ordered_rows_carry_quality_provenance_and_freshness():
    compiled = arb.compile_current_terms(_obs(_case("cash_acquisition_exact_date")))
    econ = arb.reduce_cash_deal(compiled, category="Acquisitions", live_price=_price(),
                                reference_price=_price(session="2026-08-29"), market_session=ASOF, now_utc=NOW)
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
    assert {"SOURCE_BYTES_UNAVAILABLE", "INTEGRITY_FAILED"} & set(compiled["reasons"])
    econ = arb.reduce_cash_deal(compiled, category="Acquisitions", live_price=_price(),
                                market_session=ASOF, now_utc=NOW)
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
                                live_price=_price(value=15.19), market_session=ASOF, now_utc=NOW)
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
                                live_price=_price(value=15.19), market_session=ASOF, now_utc=NOW)
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


# ---------------------------------------------------------------- the published contract

def test_every_observation_validates_against_the_committed_contract():
    from jsonschema import Draft202012Validator
    schema = json.loads(
        (Path(__file__).parents[1] /
         "contracts/special_situations_deal_term_observation.schema.json").read_text())
    v = Draft202012Validator(schema)
    n = 0
    for case in CORPUS:
        for o in _obs(case):
            errors = sorted(v.iter_errors(o), key=str)
            assert not errors, f"{case['id']}/{o['field']}: {[e.message for e in errors]}"
            n += 1
    assert n > 20, "corpus produced too few observations to be a real contract check"


def test_a_model_authored_term_cannot_satisfy_the_contract():
    """`llm_terms` have no bytes, no span and no digest — they cannot be minted as observations."""
    from jsonschema import Draft202012Validator
    schema = json.loads(
        (Path(__file__).parents[1] /
         "contracts/special_situations_deal_term_observation.schema.json").read_text())
    candidate = arb.parse_terms({"price_per_share": 25.0, "consideration": "cash"})
    assert list(Draft202012Validator(schema).iter_errors(candidate))


# ===========================================================================
# F09-1 REPAIR — Sol REQUEST_REPAIR (review 5099936758) + source-owner ruling
# + semantic-evidence addendum. Each test below is a required RED mutant.
# ===========================================================================

def _price_now(**kw):
    """A price on a session consistent with NOW, for the repair-era mutants."""
    kw.setdefault("session", "2026-06-18")
    return _price(**kw)


def _src_full(text, *, accession="0000000001-26-000001", cik="1", filing_date="2026-06-17",
              truncated=False, acceptance=None):
    return arb.source_descriptor(
        cik=cik, form_type="8-K", accession=accession, filing_date=filing_date,
        source_url="https://sec.gov/x", body=text, acquired_at="2026-06-17T12:00:00Z",
        body_truncated=truncated, acceptance_datetime=acceptance)


# --- 2. deal identity fails closed -----------------------------------------

def test_two_unrelated_deals_under_one_cik_cannot_share_terms():
    """CIK is an ISSUER, not a transaction. Grouping by it let one deal's price
    compile into another deal's economics."""
    a = arb.extract_term_observations(_CASH_EXACT, source=_src_full(
        _CASH_EXACT, accession="0000000001-26-000001", filing_date="2026-06-17"),
        listing_currency="USD")
    other = ("Each share will be converted into the right to receive $99.00 in cash per share. "
             "The transaction is expected to close on December 20, 2026.")
    b = arb.extract_term_observations(other, source=_src_full(
        other, accession="0000000001-26-000777", filing_date="2026-06-18"),
        listing_currency="USD")
    # same CIK, two unrelated accessions, no source-linked supersession
    compiled = arb.compile_current_terms(a + b)
    assert compiled["status"] != "observed", "two unrelated accessions silently merged"
    assert "CONFLICTING_AMENDMENT" in compiled["reasons"] or \
challenge_reason(compiled) , compiled["reasons"]


def challenge_reason(compiled):
    return "TERM_AMBIGUOUS" in compiled["reasons"] or "IDENTITY_UNRESOLVED" in compiled["reasons"]


def test_an_amendment_form_alone_does_not_merge_deal_lineage():
    """`/A` or same issuer is not sufficient — only an explicit source-linked
    supersession may form one lineage."""
    base = arb.extract_term_observations(_CASH_EXACT, source=_src_full(
        _CASH_EXACT, accession="0000000001-26-000001"), listing_currency="USD")
    amend_text = ("Amendment No. 1. The consideration is increased to $27.50 in cash per share. "
                  "The transaction is expected to close on December 15, 2026.")
    amend = arb.extract_term_observations(amend_text, source=_src_full(
        amend_text, accession="0000000001-26-000002", filing_date="2026-06-20"),
        listing_currency="USD")
    merged = arb.compile_current_terms(base + amend)
    assert merged["status"] != "observed", "an /A alone merged two accessions"
    linked = arb.compile_current_terms(base + arb.link_supersession(amend, base))
    assert linked["status"] == "observed"
    assert linked["terms"]["price_per_share"] == 27.5


# --- 3. byte binding must be true ------------------------------------------

def test_a_truncated_body_cannot_produce_a_verified_term():
    """doc_cache is _strip_markup(raw)[:40000]. A truncated projection cannot be
    declared conflict-free — a later contradicting price may sit past the cut."""
    obs = arb.extract_term_observations(_CASH_EXACT, source=_src_full(
        _CASH_EXACT, truncated=True), listing_currency="USD")
    compiled = arb.compile_current_terms(obs)
    econ = arb.reduce_cash_deal(compiled, category="Acquisitions", stage="pending",
                                live_price=_price_now(), now_utc=NOW)
    assert econ["quality_state"] != arb.QUALITY_VERIFIED
    assert "SOURCE_TRUNCATED" in econ["reasons"] or "SOURCE_BYTES_UNAVAILABLE" in econ["reasons"]


def test_observation_declares_the_projection_it_was_read_from():
    """An observation read from a stripped projection must not claim full submission text."""
    obs = arb.extract_term_observations(_CASH_EXACT, source=_src_full(_CASH_EXACT),
                                        listing_currency="USD")
    src = obs[0]["source"]
    assert src.get("raw_sha256") or src.get("projection_revision"), \
        "no raw-object receipt or projection revision on the observation"


# --- 4. ledger integrity fails closed --------------------------------------

def test_a_forged_observation_is_rejected_not_trusted():
    obs = arb.extract_term_observations(_CASH_EXACT, source=_src_full(_CASH_EXACT),
                                        listing_currency="USD")
    price = next(o for o in obs if o["field"] == "price_per_share")
    forged = dict(price, normalized=999.0)          # value swapped, id left alone
    assert not arb.validate_observation(forged), "a forged value kept its observation_id"
    compiled = arb.compile_current_terms([forged])
    assert compiled["status"] != "observed"
    assert "INTEGRITY_FAILED" in compiled["reasons"]


def test_a_tampered_offset_is_rejected():
    obs = arb.extract_term_observations(_CASH_EXACT, source=_src_full(_CASH_EXACT),
                                        listing_currency="USD")
    price = next(o for o in obs if o["field"] == "price_per_share")
    moved = dict(price, locator=dict(price["locator"], start=price["locator"]["start"] + 3))
    assert not arb.validate_observation(moved)


def test_a_valid_observation_validates():
    for o in arb.extract_term_observations(_CASH_EXACT, source=_src_full(_CASH_EXACT),
                                           listing_currency="USD"):
        assert arb.validate_observation(o), o["field"]


# --- 5. independent calendar ------------------------------------------------

def test_expected_session_comes_from_the_calendar_owner_not_the_price_panel():
    """A globally stale panel must not self-certify sessions_behind=0."""
    import inspect
    src = inspect.getsource(sse)
    assert "_calendar_index" not in src, "panel-derived calendar still present"
    assert "nyse_calendar" in src, "the canonical calendar owner is not used"


def test_price_without_calendar_receipt_is_not_verified():
    obs = arb.extract_term_observations(_CASH_EXACT, source=_src_full(_CASH_EXACT),
                                        listing_currency="USD")
    bare = arb.price_input(ticker="ABC", session="2026-06-18", value=20.0, currency="USD",
                           basis="close_raw", source_artifact="p.parquet")  # no calendar/digest
    econ = arb.reduce_cash_deal(arb.compile_current_terms(obs), category="Acquisitions",
                                stage="pending", live_price=bare, now_utc=NOW)
    assert econ["quality_state"] != arb.QUALITY_VERIFIED


# --- 6. invented clocks and listings ----------------------------------------

def test_unresolved_listing_never_defaults_to_usd():
    assert arb.market_currency("") is None
    assert arb.market_currency(None) is None
    assert arb.market_currency("AAPL") == "USD"


def test_date_only_filing_date_cannot_resolve_the_reference_session():
    """Premarket vs after-close acceptance changes the valid reference session."""
    obs = arb.extract_term_observations(_CASH_EXACT, source=_src_full(
        _CASH_EXACT, acceptance=None), listing_currency="USD")
    econ = arb.reduce_cash_deal(arb.compile_current_terms(obs), category="Acquisitions",
                                stage="pending", live_price=_price_now(),
                                reference_price=_price_now(session="2026-06-16"), now_utc=NOW)
    assert econ["filing_reference_premium_pct"] is None
    assert "REFERENCE_SESSION_UNRESOLVED" in econ["reasons"]


def test_the_reducer_requires_an_explicit_market_clock():
    obs = arb.extract_term_observations(_CASH_EXACT, source=_src_full(_CASH_EXACT),
                                        listing_currency="USD")
    with pytest.raises(TypeError):
        arb.reduce_cash_deal(arb.compile_current_terms(obs), category="Acquisitions")


# --- addendum 1: transaction-scoped consideration ---------------------------

_BACKGROUND_CVR = (
    "Each share of common stock will be converted into the right to receive $25.00 in cash per "
    "share. The transaction is expected to close on December 15, 2026. Background of the Merger: "
    "in 2024 the board reviewed an unrelated proposal that would have included one contingent "
    "value right per share.")

_STOCK_DEAL_CASH_FINANCING = (
    "The parties entered into a stock-for-stock merger at a fixed exchange ratio of 0.750 shares. "
    "Parent has obtained committed cash financing of $400 million in cash to refinance existing "
    "indebtedness. The transaction is expected to close on November 30, 2026.")


def test_a_background_only_cvr_does_not_classify_the_live_deal():
    compiled = arb.compile_current_terms(arb.extract_term_observations(
        _BACKGROUND_CVR, source=_src_full(_BACKGROUND_CVR), listing_currency="USD"))
    assert compiled["terms"].get("consideration") != "contingent"


def test_cash_financing_beside_a_stock_deal_is_not_a_cash_deal():
    compiled = arb.compile_current_terms(arb.extract_term_observations(
        _STOCK_DEAL_CASH_FINANCING, source=_src_full(_STOCK_DEAL_CASH_FINANCING),
        listing_currency="USD"))
    econ = arb.reduce_cash_deal(compiled, category="Acquisitions", stage="pending",
                                live_price=_price_now(), now_utc=NOW)
    assert econ["quality_state"] != arb.QUALITY_VERIFIED
    assert econ["live_gross_spread_pct"] is None


# --- addendum 2: stated premium needs its comparator ------------------------

def test_a_bare_premium_percentage_has_no_publishable_basis():
    text = ("Each share will be converted into the right to receive $25.00 in cash per share. "
            "The offer represents a 35% premium. The transaction is expected to close on "
            "December 15, 2026.")
    compiled = arb.compile_current_terms(arb.extract_term_observations(
        text, source=_src_full(text), listing_currency="USD"))
    assert compiled["terms"].get("stated_premium_pct") is None or \
        compiled["terms"].get("stated_premium_basis_state") == "STATED_PREMIUM_BASIS_UNRESOLVED"


def test_two_premium_statements_with_different_comparators_do_not_collapse():
    text = ("Each share will be converted into the right to receive $25.00 in cash per share. "
            "The consideration represents a premium of approximately 45% to the closing price on "
            "September 1, 2026, and a premium of approximately 60% to the closing price on "
            "June 1, 2026. The transaction is expected to close on December 15, 2026.")
    compiled = arb.compile_current_terms(arb.extract_term_observations(
        text, source=_src_full(text), listing_currency="USD"))
    assert compiled["terms"].get("stated_premium_pct") is None, \
        "two different stated comparators collapsed into one number"
