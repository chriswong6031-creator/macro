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
# ONE explicit market clock for the whole suite, consistent with ASOF and every session below.
# It was 2026-06-18 while ASOF and the price sessions were 2026-09-01 — an incoherence the old
# reducer could not see because it TRUSTED the caller's `sessions_behind` instead of recomputing
# it from the calendar. Now that freshness is re-derived from `now_utc`, the clock has to be real.
NOW = datetime(2026, 9, 1, 22, 0, tzinfo=timezone.utc)   # 18:00 ET, after the 2026-09-01 close


def _src(case: dict) -> dict:
    """A COMPLETE retained source object with its acceptance moment — the shape the repaired
    contract requires before any precise term may be called verified."""
    return arb.source_descriptor(
        cik="0000320193", form_type=case["form_type"], accession=case["accession"],
        filing_date=case["filing_date"], source_url=f"https://sec.gov/{case['accession']}.txt",
        body=case["text"], acquired_at="2026-09-02T00:00:00Z",
        raw_sha256="a" * 64, raw_bytes=len(case["text"]) * 3,
        # the resolved listing travels WITH the observation: an observed bare-dollar USD price
        # may not exist without it, which is what the hardened contract now refuses
        resolved_listing="ABC" if case.get("listing_currency") == "USD" else None,
        acceptance_datetime=f"{case['filing_date']}T17:31:00-04:00")


def _obs(case: dict) -> list[dict]:
    return arb.extract_term_observations(case["text"], source=_src(case),
                                         listing_currency=case.get("listing_currency"),
                                         recorded_at="2026-09-02T00:00:00Z")


def _case(cid: str) -> dict:
    return next(c for c in CORPUS if c["id"] == cid)


def _price(value=15.19, session="2026-09-01", currency="USD", basis=None, ticker="T",
           now=None, **override):
    """A TRUTHFUL narrow-V1 price receipt — what an honest producer would write.

    It used to name `breadth/_closes_cache.parquet` with `basis="close_raw"`, which is a FALSE
    receipt: breadth is written `auto_adjust=True`. CI therefore blessed the exact fiction the
    owner ruling prohibits. V1 reads only the per-ticker U.S. Yahoo store's `close_price`
    (`auto_adjust=False`, split-adjusted / dividend-unadjusted), on XNYS.

    `expected_session` and `sessions_behind` are DERIVED here from the approved calendar owner,
    exactly as the producer must derive them — so a test that wants a stale price moves the
    SESSION, and a test that wants to lie passes the lie explicitly through `override`.
    """
    from lib import nyse_calendar
    now = now or NOW
    listing = arb.resolve_us_listing(ticker)
    day = date.fromisoformat(session)
    kw = dict(ticker=listing or ticker, listing="XNYS", session=session, value=value,
              currency=currency, basis=basis or arb.PRICE_BASIS_SPLIT_ADJ,
              column=arb.PRICE_COLUMN, source_artifact=f"yahoo/{listing or ticker}.parquet",
              artifact_sha256="b" * 64, artifact_bytes=4096,
              writer_owner=arb.PRICE_WRITER_OWNER, writer_blob=arb.PRICE_WRITER_BLOB,
              calendar_owner=arb.CALENDAR_OWNER, calendar_blob=arb.CALENDAR_BLOB,
              calendar_revision=arb.CALENDAR_REVISION, calendar_id=arb.US_CALENDAR_ID,
              expected_session=nyse_calendar.expected_last_session(now).isoformat(),
              sessions_behind=int(nyse_calendar.sessions_behind(day, now)),
              sessions_unique_monotonic=True, values_finite_positive=True,
              read_validated=True)
    kw.update(override)
    return arb.price_input(**kw)


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
    # informational, not a failure: a VERIFIED row must never carry a failure reason
    assert "DATE_PRECISION_INSUFFICIENT" in r["warnings"] and r["reasons"] == []
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
    assert r["live_session"] == "2026-09-01"
    assert r["price_basis"] == arb.PRICE_BASIS_SPLIT_ADJ
    assert r["live_source"] == "yahoo/T.parquet"
    assert r["formula_revision"] == arb.FORMULA_REVISION


def test_stale_price_is_visible_context_but_never_ordered():
    compiled = arb.compile_current_terms(_obs(_case("cash_acquisition_exact_date")))
    # a GENUINELY stale session — staleness is recomputed from the calendar, so it can no
    # longer be asserted by a caller who simply says `sessions_behind=1`
    r = arb.reduce_cash_deal(compiled, category="Acquisitions",
                             live_price=_price(session="2026-08-31"),
                             market_session=ASOF, now_utc=NOW)
    assert r["quality_state"] == arb.QUALITY_STALE_PRICE
    assert "PRICE_STALE" in r["reasons"] and r["sessions_behind"] == 1
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
    assert "REFERENCE_SESSION_UNRESOLVED" in later["warnings"]


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
    # `reseal()` is now the ONLY lawful way to mint a row carrying a correction relation:
    # the relation is inside the closed digest, so an id minted without it is not this row's id
    retraction = arb.reseal(retraction)
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
    kw.setdefault("session", "2026-09-01")
    return _price(**kw)


def _src_full(text, *, accession="0000000001-26-000001", cik="1", filing_date="2026-09-01",
              truncated=False, acceptance=None):
    return arb.source_descriptor(
        cik=cik, form_type="8-K", accession=accession, filing_date=filing_date,
        source_url="https://sec.gov/x", body=text, acquired_at="2026-06-17T12:00:00Z",
        body_truncated=truncated, resolved_listing="ABC", acceptance_datetime=acceptance)


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
    # A real amendment names the agreement it amends; without that the body carries no
    # current-transaction anchor at all and now yields no observations, which would make this
    # test pass for the wrong reason (nothing to merge) instead of proving lineage is refused.
    amend_text = ("Amendment No. 1 to the Agreement and Plan of Merger. The consideration is "
                  "increased to $27.50 in cash per share. The transaction is expected to close "
                  "on December 15, 2026.")
    amend = arb.extract_term_observations(amend_text, source=_src_full(
        amend_text, accession="0000000001-26-000002", filing_date="2026-09-20"),
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
    assert "REFERENCE_SESSION_UNRESOLVED" in econ["warnings"]


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


# ===========================================================================
# F09-1 CRITICAL REPAIR — Sol reviews 5102199556 / 5102373399 and the reviewer
# STOP addendum (carrier 1788441394.459699). Every test below is a reproduced
# EXPLOIT: it published a wrong or unproven number at head a88c12f2.
# ===========================================================================

_YAHOO_ARTIFACT = "yahoo/ABC.parquet"


def _us_price(**kw):
    """A COMPLETE narrow-V1 price receipt: exact resolved US listing, per-ticker Yahoo
    `close_price`, XNYS, and every receipt field the reducer independently re-checks."""
    kw.setdefault("session", "2026-09-01")
    kw.setdefault("expected_session", "2026-09-01")
    kw.setdefault("value", 20.0)
    kw.setdefault("currency", "USD")
    kw.setdefault("sessions_behind", 0)
    kw.setdefault("basis", arb.PRICE_BASIS_SPLIT_ADJ)
    kw.setdefault("column", "close_price")
    kw.setdefault("listing", "XNYS")
    kw.setdefault("ticker", "ABC")
    kw.setdefault("source_artifact", _YAHOO_ARTIFACT)
    kw.setdefault("artifact_sha256", "b" * 64)
    kw.setdefault("artifact_bytes", 4096)
    kw.setdefault("writer_owner", arb.PRICE_WRITER_OWNER)
    kw.setdefault("writer_blob", arb.PRICE_WRITER_BLOB)
    kw.setdefault("calendar_owner", arb.CALENDAR_OWNER)
    kw.setdefault("calendar_blob", arb.CALENDAR_BLOB)
    kw.setdefault("calendar_revision", arb.CALENDAR_REVISION)
    kw.setdefault("calendar_id", "XNYS")
    kw.setdefault("sessions_unique_monotonic", True)
    kw.setdefault("values_finite_positive", True)
    kw.setdefault("read_validated", True)
    return arb.price_input(**kw)


def _complete_src(text, *, accession="0000000001-26-000001", cik="1",
                  filing_date="2026-09-01", acceptance="2026-09-01T21:31:00+00:00"):
    """A complete retained source object — the only shape a VERIFIED row may cite."""
    return arb.source_descriptor(
        cik=cik, form_type="8-K", accession=accession, filing_date=filing_date,
        source_url="https://sec.gov/x", body=text, acquired_at="2026-06-17T12:00:00Z",
        raw_sha256="a" * 64, raw_bytes=len(text) * 3, resolved_listing="ABC",
        acceptance_datetime=acceptance)


def _verified(text=_CASH_EXACT, **kw):
    obs = arb.extract_term_observations(text, source=_complete_src(text),
                                        listing_currency="USD")
    return arb.reduce_cash_deal(arb.compile_current_terms(obs, accession="0000000001-26-000001"),
                                category="Acquisitions", stage="pending",
                                live_price=_us_price(), now_utc=NOW, **kw)


# --- CRITICAL A: correction relation identity is an authorization boundary ---

_OTHER_DEAL = ("Each share will be converted into the right to receive $250.00 in cash per "
               "share. The transaction is expected to close on December 20, 2026.")
_ACC_A = "0000000001-26-000001"
_ACC_B = "0000000001-26-000777"
_ACC_C = "0000000001-26-000999"


def _obs_for(text, accession, filed):
    return arb.extract_term_observations(
        text, source=_complete_src(text, accession=accession, filing_date=filed),
        listing_currency="USD")


def test_a_forged_supersession_field_cannot_pull_an_unrelated_price_into_a_deal():
    """ONE unauthenticated field merged two unrelated transactions.

    `prior/supersedes_observation_id` and `correction_reason` sat OUTSIDE the observation
    digest, so a hand-forged link kept the row's id and passed validation, and the compiler
    admitted the whole multi-accession bucket when ANY supersession matched ANY bucket id.
    """
    a = _obs_for(_CASH_EXACT, _ACC_A, "2026-09-01")
    b = _obs_for(_OTHER_DEAL, _ACC_B, "2026-09-02")
    target = next(o for o in a if o["field"] == "price_per_share")
    forged = [dict(o, supersedes_observation_id=target["observation_id"],
                   prior_observation_id=target["observation_id"],
                   correction_reason="forged") if o["field"] == "price_per_share" else o
              for o in b]
    # the forged row must not even validate: its id no longer covers its own relation fields
    assert not arb.validate_observation(
        next(o for o in forged if o["field"] == "price_per_share")), \
        "a forged correction link kept the observation id"
    compiled = arb.compile_current_terms(a + forged, accession=_ACC_A)
    econ = arb.reduce_cash_deal(compiled, category="Acquisitions", stage="pending",
                                live_price=_us_price(), now_utc=NOW)
    assert econ["quality_state"] != arb.QUALITY_VERIFIED
    assert econ["offer_price"] != 250.0, "an unrelated accession's price reached this deal"


def test_link_supersession_changes_the_observation_identity():
    """`link_supersession()` recomputed the id and got the SAME string back — a no-op.

    A relation that can change without changing the identity is not immutable, which is what
    made the forged-field exploit above possible.
    """
    older = _obs_for(_CASH_EXACT, _ACC_A, "2026-09-01")
    amend = _OTHER_DEAL.replace("$250.00", "$260.00")
    newer = _obs_for(amend, _ACC_B, "2026-09-02")
    linked = arb.link_supersession(newer, older)
    before = {o["field"]: o["observation_id"] for o in newer}
    after = {o["field"]: o["observation_id"] for o in linked}
    changed = [f for f in after if after[f] != before.get(f)]
    assert changed, "stamping a supersession did not change any observation id"
    for o in linked:
        assert arb.validate_observation(o), "a lawfully linked row failed its own digest"


def test_one_valid_link_cannot_legalize_an_unrelated_third_accession():
    """A linked pair admitted an entire bucket, including an accession with no relation."""
    older = _obs_for(_CASH_EXACT, _ACC_A, "2026-09-01")
    amend_text = _CASH_EXACT.replace("$25.00", "$27.00")
    newer = arb.link_supersession(_obs_for(amend_text, _ACC_B, "2026-09-02"), older)
    stranger = _obs_for(_OTHER_DEAL, _ACC_C, "2026-09-02")
    compiled = arb.compile_current_terms(older + newer + stranger, accession=_ACC_A)
    cited = {(compiled.get("evidence") or {}).get(f, {}).get("accession")
             for f in ("price_per_share", "consideration", "expected_close")}
    assert _ACC_C not in cited, "an unrelated accession was compiled into the lineage"
    assert compiled["terms"].get("price_per_share") != 250.0


def test_a_dangling_correction_link_is_an_integrity_failure():
    rows = _obs_for(_CASH_EXACT, _ACC_A, "2026-09-01")
    broken = [dict(o, prior_observation_id="f" * 32, supersedes_observation_id="f" * 32,
                   correction_reason="amended") if o["field"] == "price_per_share" else o
              for o in rows]
    broken = [arb.reseal(o) if o["field"] == "price_per_share" else o for o in broken]
    compiled = arb.compile_current_terms(broken, accession=_ACC_A)
    assert "INTEGRITY_FAILED" in compiled["reasons"]
    assert compiled["terms"].get("price_per_share") is None


def test_a_supersession_cycle_is_an_integrity_failure():
    rows = [o for o in _obs_for(_CASH_EXACT, _ACC_A, "2026-09-01")
            if o["field"] == "price_per_share"]
    a = rows[0]
    b = arb.reseal(dict(a, prior_observation_id=a["observation_id"],
                        supersedes_observation_id=a["observation_id"],
                        correction_reason="amended"))
    a2 = arb.reseal(dict(a, prior_observation_id=b["observation_id"],
                         supersedes_observation_id=b["observation_id"],
                         correction_reason="amended"))
    compiled = arb.compile_current_terms([a2, b], accession=_ACC_A)
    assert "INTEGRITY_FAILED" in compiled["reasons"]


# --- CRITICAL C: the reducer must recompute receipt truth -------------------

def test_a_stale_session_with_a_caller_authored_zero_behind_is_not_verified():
    """`sessions_behind=0` was TRUSTED and `session` was never compared to `expected_session`.

    A 2020 session beside a 2026 expected session therefore reached VERIFIED.
    """
    econ = _verified()
    assert econ["quality_state"] == arb.QUALITY_VERIFIED, "control case must be verified"
    bad = arb.reduce_cash_deal(
        arb.compile_current_terms(
            arb.extract_term_observations(_CASH_EXACT, source=_complete_src(_CASH_EXACT),
                                          listing_currency="USD"), accession=_ACC_A),
        category="Acquisitions", stage="pending", now_utc=NOW,
        live_price=_us_price(session="2020-01-02", expected_session="2026-06-01",
                             sessions_behind=0))
    assert bad["quality_state"] != arb.QUALITY_VERIFIED
    assert "PRICE_STALE" in bad["reasons"] or "PRICE_RECEIPT_INVALID" in bad["reasons"]


def test_a_made_up_price_basis_is_not_verified():
    bad = arb.reduce_cash_deal(
        arb.compile_current_terms(
            arb.extract_term_observations(_CASH_EXACT, source=_complete_src(_CASH_EXACT),
                                          listing_currency="USD"), accession=_ACC_A),
        category="Acquisitions", stage="pending", now_utc=NOW,
        live_price=_us_price(basis="totally_made_up_basis"))
    assert bad["quality_state"] != arb.QUALITY_VERIFIED
    assert "PRICE_BASIS_UNRESOLVED" in bad["reasons"]


def test_price_input_has_no_raw_close_default():
    """The `close_raw` fiction lived in the PURE owner's own default, not only the producer."""
    p = arb.price_input(ticker="ABC", session="2026-06-18", value=1.0, currency="USD")
    assert p["basis"] is None, "price_input still defaults to a basis it cannot prove"


def test_sessions_behind_is_recomputed_not_accepted():
    """The receipt's own arithmetic is re-derived from the approved calendar owner."""
    bad = arb.reduce_cash_deal(
        arb.compile_current_terms(
            arb.extract_term_observations(_CASH_EXACT, source=_complete_src(_CASH_EXACT),
                                          listing_currency="USD"), accession=_ACC_A),
        category="Acquisitions", stage="pending", now_utc=NOW,
        live_price=_us_price(session="2026-08-25", sessions_behind=0))
    # the receipt's own conclusion was a lie, so the receipt itself is invalid and NOTHING
    # numeric is published — and the recomputed count contradicts the claimed zero
    assert bad["quality_state"] != arb.QUALITY_VERIFIED
    assert "PRICE_RECEIPT_INVALID" in bad["reasons"] and "PRICE_STALE" in bad["reasons"]
    assert bad["sessions_behind"] and bad["sessions_behind"] > 0
    assert bad["live_gross_spread_pct"] is None

    # an HONEST stale receipt is different: still visible, never ordered
    honest = arb.reduce_cash_deal(
        arb.compile_current_terms(
            arb.extract_term_observations(_CASH_EXACT, source=_complete_src(_CASH_EXACT),
                                          listing_currency="USD"), accession=_ACC_A),
        category="Acquisitions", stage="pending", now_utc=NOW,
        live_price=_price(session="2026-08-25", value=20.0, ticker="ABC"))
    assert honest["quality_state"] == arb.QUALITY_STALE_PRICE
    assert honest["live_gross_spread_pct"] is not None and honest["orderable"] is False


def test_a_false_expected_session_field_is_invalid_even_when_the_price_is_current():
    """The receipt's DECLARED `expected_session` is re-derived, not just used for arithmetic.

    Found by mutation, not by reading: deleting the `expected_session` comparison from
    `validate_price_receipt` left all 197 tests passing. Every other freshness test here moves
    `session` or `sessions_behind` too, so the recomputed-staleness arithmetic caught those
    mutants and this check was never the thing under test.

    It is a real gate, because the receipt is PUBLISHED. Here `session` and `sessions_behind`
    are both honest for `NOW` — the price genuinely is current — and only the receipt's own
    claim about which session the market last completed is wrong. Nothing downstream would
    contradict it, so a VERIFIED row would ship a calendar fact no owner ever produced. That is
    the false-precision shape this wave exists to remove, one field further in.
    """
    control = arb.reduce_cash_deal(
        arb.compile_current_terms(
            arb.extract_term_observations(_CASH_EXACT, source=_complete_src(_CASH_EXACT),
                                          listing_currency="USD"), accession=_ACC_A),
        category="Acquisitions", stage="pending", now_utc=NOW, live_price=_us_price())
    assert control["quality_state"] == arb.QUALITY_VERIFIED, "control must isolate one field"

    bad = arb.reduce_cash_deal(
        arb.compile_current_terms(
            arb.extract_term_observations(_CASH_EXACT, source=_complete_src(_CASH_EXACT),
                                          listing_currency="USD"), accession=_ACC_A),
        category="Acquisitions", stage="pending", now_utc=NOW,
        live_price=_us_price(expected_session="2026-08-31"))
    assert bad["quality_state"] != arb.QUALITY_VERIFIED
    assert "PRICE_RECEIPT_INVALID" in bad["reasons"]
    assert bad["orderable"] is False
    # the honest arithmetic is untouched, which is exactly why nothing else could catch this
    assert bad["sessions_behind"] == 0


def test_an_adjusted_breadth_artifact_can_never_be_verified():
    """breadth/`_closes_cache.parquet` is written `auto_adjust=True`; the branch labelled it raw."""
    for kw in ({"source_artifact": "breadth/_closes_cache.parquet"},
               {"column": "close"},
               {"writer_owner": "collectors/breadth.py"},
               {"artifact_sha256": None},
               {"artifact_bytes": None},
               {"calendar_blob": None},
               {"calendar_id": "XHKG"},
               {"listing": "XHKG"}):
        bad = arb.reduce_cash_deal(
            arb.compile_current_terms(
                arb.extract_term_observations(_CASH_EXACT, source=_complete_src(_CASH_EXACT),
                                              listing_currency="USD"), accession=_ACC_A),
            category="Acquisitions", stage="pending", now_utc=NOW, live_price=_us_price(**kw))
        assert bad["quality_state"] != arb.QUALITY_VERIFIED, f"{kw} reached VERIFIED"


def test_a_tampered_artifact_digest_shape_is_not_verified():
    for digest in ("", "not-a-digest", "b" * 63, "z" * 64):
        bad = arb.reduce_cash_deal(
            arb.compile_current_terms(
                arb.extract_term_observations(_CASH_EXACT, source=_complete_src(_CASH_EXACT),
                                              listing_currency="USD"), accession=_ACC_A),
            category="Acquisitions", stage="pending", now_utc=NOW,
            live_price=_us_price(artifact_sha256=digest))
        assert bad["quality_state"] != arb.QUALITY_VERIFIED, f"digest {digest!r} reached VERIFIED"


def test_the_reviewed_owner_blobs_are_pinned_to_the_real_repository_blobs():
    """The receipt names a REVIEWED writer/calendar blob. If either owner legitimately moves,
    this test — not a silent coverage collapse — is what tells a session to re-review it."""
    import subprocess
    for path, pinned in ((arb.PRICE_WRITER_OWNER, arb.PRICE_WRITER_BLOB),
                         (arb.CALENDAR_OWNER, arb.CALENDAR_BLOB)):
        actual = subprocess.run(["git", "rev-parse", f"HEAD:{path}"], capture_output=True,
                                text=True, cwd=Path(__file__).resolve().parents[1]).stdout.strip()
        assert actual == pinned, (
            f"{path} moved: reviewed blob {pinned} != current {actual}. Re-review the owner's "
            f"basis/calendar semantics, then re-pin — do not widen the vocabulary.")


# --- CRITICAL B: the narrow U.S.-listing boundary ---------------------------

def test_a_foreign_listing_is_declined_not_graded_on_xnys():
    """On 2026-07-03 NYSE was closed while HKEX traded: an HK row one local session stale
    reported `sessions_behind=0` against the US calendar and reached VERIFIED."""
    for tk, art in (("ARX.TO", "yahoo/ARX.TO.parquet"), ("0700.HK", "yahoo/0700.HK.parquet"),
                    ("BRK.B", "yahoo/BRK.B.parquet")):
        assert arb.resolve_us_listing(tk) is None, f"{tk} resolved as a US cash-equity listing"
    assert arb.resolve_us_listing("ABC") == "ABC"
    assert arb.resolve_us_listing("") is None and arb.resolve_us_listing(None) is None


def test_no_syntax_derived_usd_reaches_the_verified_path():
    """`market_currency()` returned USD for ANY dotless ticker (BABA, ADS1)."""
    import inspect
    for fn in (arb.reduce_cash_deal, arb.validate_price_receipt):
        assert "market_currency" not in inspect.getsource(fn), \
            f"{fn.__name__} still derives a currency from ticker syntax"
    # the syntax helper itself survives for the display/candidate lanes, and still says USD —
    # which is exactly why the verified path may not call it
    assert arb.market_currency("BABA") == "USD" and arb.resolve_us_listing("BABA") == "BABA"
    assert arb.market_currency("ARX.TO") == "CAD" and arb.resolve_us_listing("ARX.TO") is None


# --- HIGH E: historical proposal vs the current transaction -----------------

_HISTORICAL_CASH_CURRENT_STOCK = (
    "The Company entered into an Agreement and Plan of Merger under which each share of common "
    "stock will be converted into the right to receive 0.850 shares of Parent common stock in a "
    "stock-for-stock merger. The transaction is expected to close on December 15, 2026. "
    "Background of the Merger: in March 2025 the board received and rejected an unsolicited "
    "proposal to acquire the Company for $48.00 in cash per share.")


def test_a_historical_cash_proposal_cannot_price_a_current_stock_deal():
    """Reproduced by the independent reviewer: VERIFIED, offer 48.00, spread +20%, cash.

    The extractor anchored the transaction scope on the FIRST price candidate, which scoped
    into `Background of the Merger` and made a rejected 2025 proposal the live consideration.
    """
    compiled = arb.compile_current_terms(arb.extract_term_observations(
        _HISTORICAL_CASH_CURRENT_STOCK, source=_complete_src(_HISTORICAL_CASH_CURRENT_STOCK),
        listing_currency="USD"), accession=_ACC_A)
    econ = arb.reduce_cash_deal(compiled, category="Acquisitions", stage="pending",
                                live_price=_us_price(value=40.0), now_utc=NOW)
    assert econ["offer_price"] != 48.0, "a rejected historical proposal priced the live deal"
    assert econ["quality_state"] != arb.QUALITY_VERIFIED
    assert econ["live_gross_spread_pct"] is None


def test_a_background_price_is_never_the_only_admissible_candidate():
    """Even with no current price at all, a background price cannot become the offer."""
    text = ("The parties agreed to an all-stock combination. The transaction is expected to "
            "close on December 15, 2026. Prior Proposals: the Company previously rejected "
            "$61.00 in cash per share.")
    compiled = arb.compile_current_terms(
        arb.extract_term_observations(text, source=_complete_src(text),
                                      listing_currency="USD"), accession=_ACC_A)
    assert compiled["terms"].get("price_per_share") is None


# --- an UNANCHORED admissible section is not a current transaction ----------
# Sol semantic addendum (carrier 1788494850.137529): `(anchored or admissible)[0]` selected the
# first admissible section when nothing carried a current-transaction anchor. That reads as
# conservative and is not — it makes DOCUMENT ORDER the authority for which deal a published
# price belongs to. None of these sections is `excluded`; the point is that admissible is not
# the same as proven.

_TWO_UNANCHORED_ITEMS = (
    "Item 8.01 Other Events. In March 2025 the board reviewed and declined an unsolicited "
    "indication of interest valuing the Company at $48.00 in cash per share. "
    "Item 7.01 Regulation FD Disclosure. The Company continues to evaluate strategic "
    "alternatives with a third party and has retained a financial adviser.")

_ONE_UNANCHORED_ITEM = (
    "Item 8.01 Other Events. The Company confirmed that the per share cash amount under "
    "discussion with the counterparty is $52.00 per share in cash.")

_ANCHORED_SECOND_ITEM = (
    "Item 8.01 Other Events. In March 2025 the board reviewed and declined an unsolicited "
    "indication of interest valuing the Company at $48.00 in cash per share. "
    "Item 1.01 Entry into a Material Definitive Agreement. The Company entered into an "
    "Agreement and Plan of Merger under which each share will be converted into the right to "
    "receive $75.00 in cash per share. The transaction is expected to close on "
    "December 15, 2026.")


def test_two_unanchored_admissible_sections_emit_no_current_terms():
    """Neither section carries an anchor, so the first one is not the current transaction."""
    secs = arb.document_sections(_TWO_UNANCHORED_ITEMS)
    assert len([s for s in secs if not s["excluded"]]) >= 2, "fixture must be admissible, not excluded"
    assert arb.current_transaction_scope(_TWO_UNANCHORED_ITEMS) is None

    compiled = arb.compile_current_terms(
        arb.extract_term_observations(_TWO_UNANCHORED_ITEMS,
                                      source=_complete_src(_TWO_UNANCHORED_ITEMS),
                                      listing_currency="USD"), accession=_ACC_A)
    assert compiled["terms"].get("price_per_share") is None
    assert compiled["terms"].get("consideration") is None
    econ = arb.reduce_cash_deal(compiled, category="Acquisitions", stage="pending",
                                live_price=_us_price(value=40.0), now_utc=NOW)
    assert econ["offer_price"] != 48.0, "document order selected a declined 2025 indication"
    assert econ["quality_state"] != arb.QUALITY_VERIFIED
    assert econ["live_gross_spread_pct"] is None


def test_a_lone_unanchored_section_declines_rather_than_publishing_its_price():
    """The document's only per-share number, in its only admissible section — still declined."""
    assert arb.current_transaction_scope(_ONE_UNANCHORED_ITEM) is None
    compiled = arb.compile_current_terms(
        arb.extract_term_observations(_ONE_UNANCHORED_ITEM,
                                      source=_complete_src(_ONE_UNANCHORED_ITEM),
                                      listing_currency="USD"), accession=_ACC_A)
    assert compiled["terms"].get("price_per_share") is None
    econ = arb.reduce_cash_deal(compiled, category="Acquisitions", stage="pending",
                                live_price=_us_price(value=40.0), now_utc=NOW)
    assert econ["quality_state"] != arb.QUALITY_VERIFIED
    assert econ["offer_price"] != 52.0


def test_an_anchor_in_the_later_section_scopes_to_that_section_only():
    """The repair must not degrade into blanket refusal — an anchored section still publishes.

    Same two-section shape as above with a real anchor added to the SECOND section. The scope
    must be that section, the $75.00 current offer must be the published price, and the $48.00
    declined indication in the earlier unanchored section must not win on document order.
    """
    scope = arb.current_transaction_scope(_ANCHORED_SECOND_ITEM)
    assert scope is not None, "an anchored section must still resolve"
    start, end = scope
    assert _ANCHORED_SECOND_ITEM.index("$75.00") >= start
    assert _ANCHORED_SECOND_ITEM.index("$48.00") < start, "scope must exclude the earlier section"

    compiled = arb.compile_current_terms(
        arb.extract_term_observations(_ANCHORED_SECOND_ITEM,
                                      source=_complete_src(_ANCHORED_SECOND_ITEM),
                                      listing_currency="USD"), accession=_ACC_A)
    assert compiled["terms"]["price_per_share"] == 75.0
    assert compiled["terms"]["price_per_share"] != 48.0


# --- quality semantics ------------------------------------------------------

def test_a_verified_row_carries_no_failure_reasons():
    """A VERIFIED row shipped `REFERENCE_SESSION_UNRESOLVED` in its own failure list."""
    econ = _verified()
    assert econ["quality_state"] == arb.QUALITY_VERIFIED
    assert econ["reasons"] == [], f"VERIFIED row carries failure reasons {econ['reasons']}"
    assert isinstance(econ.get("warnings"), list)


def test_informational_gaps_are_warnings_not_failures():
    econ = _verified()
    assert "REFERENCE_SESSION_UNRESOLVED" in econ["warnings"]


# --- the hardened contract refuses what the runtime refuses -----------------

def _validator():
    from jsonschema import Draft202012Validator
    return Draft202012Validator(json.loads(
        (Path(__file__).parents[1] /
         "contracts/special_situations_deal_term_observation.schema.json").read_text()))


def _one_observed_price() -> dict:
    obs = arb.extract_term_observations(_CASH_EXACT, source=_complete_src(_CASH_EXACT),
                                        listing_currency="USD")
    return next(o for o in obs if o["field"] == "price_per_share" and o["status"] == "observed")


def test_the_committed_contract_matches_the_runtime_law():
    """Every mutant the runtime refuses, the published contract must refuse too.

    The schema previously required an 8-character `observation_id`, omitted `raw_sha256`,
    `raw_bytes`, acceptance and event identity from `source.required`, and did not require the
    locator excerpt — so a row the runtime would reject still satisfied the contract a consumer
    reads. A contract weaker than its runtime is a licence, not a contract.
    """
    v = _validator()
    good = _one_observed_price()
    assert not list(v.iter_errors(good)), "the control row must validate"

    def refuses(mutant, why):
        assert list(v.iter_errors(mutant)), f"the contract accepted {why}"

    refuses(dict(good, observation_id="abcdef12"), "an 8-character observation id")
    refuses(dict(good, observation_id="A" * 32), "an upper-case observation id")
    refuses(dict(good, locator={k: x for k, x in good["locator"].items() if k != "excerpt"}),
            "a locator with no excerpt")
    refuses(dict(good, source={k: x for k, x in good["source"].items() if k != "raw_sha256"}),
            "an observed precise term with no retained-object digest")
    refuses(dict(good, source=dict(good["source"], raw_bytes=None)),
            "an observed precise term with no retained-object length")
    refuses(dict(good, source=dict(good["source"], completeness="truncated")),
            "an observed precise term read from a truncated body")
    refuses(dict(good, source=dict(good["source"], acquired_at=None)),
            "an observed precise term with no acquisition time")
    refuses(dict(good, supersedes_observation_id="f" * 32),
            "a supersession with no predecessor and no reason")
    refuses(dict(good, supersedes_observation_id="f" * 32, prior_observation_id="f" * 32),
            "a supersession with no stated reason")
    refuses(dict(good, correction_reason="amended"),
            "a correction reason with no relation")
    refuses(dict(good, supersedes_observation_id="not-a-digest",
                 prior_observation_id="not-a-digest", correction_reason="amended"),
            "a correction link that is not a closed digest")
    refuses(dict(good, source=dict(good["source"], resolved_listing=None)),
            "an observed bare-dollar USD price with no resolved listing receipt")
    refuses(dict(good, source=dict(good["source"], resolved_listing="ARX.TO")),
            "a foreign listing standing in as the resolved U.S. listing")
    refuses(dict(good, locator=dict(good["locator"], start=-1)),
            "a negative locator offset")


def test_a_lawfully_corrected_row_still_satisfies_the_contract():
    """The hardening must refuse forgeries without refusing real corrections."""
    v = _validator()
    older = _obs_for(_CASH_EXACT, _ACC_A, "2026-09-01")
    amend = _CASH_EXACT.replace("$25.00", "$27.00")
    linked = arb.link_supersession(_obs_for(amend, _ACC_B, "2026-09-02"), older)
    for o in linked:
        assert not list(v.iter_errors(o)), \
            f"the contract refused a lawful correction: {[e.message for e in v.iter_errors(o)]}"
        assert arb.validate_observation(o)
