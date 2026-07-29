"""Fact-locked filing lanes — congress, insider, house picks (XG-E2).

Covers `engine/marketing/congress_feed.py`, `engine/marketing/insider_feed.py`
and `engine/marketing/house_picks.py`, plus their registration into the planned-
kind machinery (`outbox.KINDS`, `content_studio.PLANNED_KINDS`,
`expression_dial.PROFILES`).

WHAT THESE LANES CAN GET WRONG, which is what the file is organised around:

1. **Publishing a stale trade as news.** A congressional disclosure can be six
   weeks behind the trade and the site's own writing says so. §3 proves the lag
   sentence is present AND writer-visible, and that a packet which loses it
   REFUSES rather than shipping quietly.
2. **Ranking on the dollar headline.** The codex measured a $6.92M purchase
   reading as more important than a $299K one that multiplied its holder's stake
   twelve-fold. §2 is the mechanism table, including that exact RBKB case.
3. **Calling compensation a purchase.** §4 pins the open-market-only filter and
   the dividend-reinvestment exclusion.
4. **Printing an internal score as prose.** §6 proves the display-tier phrases
   carry no digit and that the guard raises when one appears.
5. **Re-posting a name a desk covered yesterday.** §5 is the LKFN-class
   interplay through the real outbox ledger.
6. **Laundering a screen into a call.** §7 proves every house pick names its
   desk in plain words and carries that desk's own disclosure.

LANE PURITY. The pure-logic tests import nothing beyond the engine modules and
stdlib, so they run in the thin marketing CI pack (`pytest pyyaml jinja2`). Only
the parquet-fixture tests need pandas, and they gate on it INSIDE the test body
(the sibling pattern in tests/test_marketing_card_parity.py) so the arithmetic,
lag and register guarantees keep their teeth in a pandas-less pack rather than
the whole module skipping.
"""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import pytest

#: A Wednesday, so the trading-day cooldown maths in §5 has ordinary weekdays
#: behind it (the same reason test_marketing_selection.py pins its own dates).
_TODAY = "2026-07-29"
_YESTERDAY = "2026-07-28"
_FIXED_NOW = datetime(2026, 7, 29, 6, 0, 0, tzinfo=timezone.utc)

#: The codex's worked RBKB example, verbatim from
#: research/marketing_dockets/CODEX_CONTENT_CASE_STUDIES_2026_07_28.md.
_RBKB = {"shares": 25_000, "price": 11.94, "shares_following": 27_270}


# ── fixtures ─────────────────────────────────────────────────────────────────

def _congress_row(**over):
    """One congress.parquet row, materially sized and freshly crawled."""
    row = {
        "Representative": "Jane Q. Public",
        "BioGuideID": "P000001",
        "ReportDate": "2026-07-29",
        "TransactionDate": "2026-06-12",
        "Ticker": "NVDA",
        "Transaction": "Purchase",
        "Range": "$50,001 - $100,000",
        "House": "Representatives",
        "Amount": "50001.0",
        "Party": "D",
        "TickerType": "Stock",
        "Description": None,
        "ExcessReturn": 4.2,
        "_first_seen": f"{_TODAY}T00:05:46.698195+00:00",
    }
    row.update(over)
    return row


def _insider_row(**over):
    """One insiders.parquet row: an open-market purchase, freshly crawled."""
    row = {
        "Ticker": "RBKB",
        "Date": "2026-07-27T00:00:00.000",
        "Name": "Nancy Koskey Patzwahl",
        "AcquiredDisposedCode": "A",
        "TransactionCode": "P",
        "Shares": float(_RBKB["shares"]),
        "PricePerShare": _RBKB["price"],
        "SharesOwnedFollowing": float(_RBKB["shares_following"]),
        "fileDate": "2026-07-28T23:29:49.000",
        "officerTitle": "Chief Financial Officer",
        "isDirector": False,
        "isOfficer": True,
        "isTenPercentOwner": False,
        "isOther": False,
        "directOrIndirectOwnership": "D",
        "uploaded": "2026-07-28T00:15:05.197",
        "_first_seen": f"{_TODAY}T00:12:08.631438+00:00",
    }
    row.update(over)
    return row


def _write_parquet(rows, path: Path):
    """Fixture parquet under tmp_path. Gates on pandas INSIDE the test body."""
    pd = pytest.importorskip("pandas")
    pytest.importorskip("pyarrow")
    path.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(rows).to_parquet(path)
    return pd.read_parquet(path)


# ─────────────────────────────────────────────────────────────────────────────
# 1. Derived arithmetic — the codex §Signal-calculation framework
# ─────────────────────────────────────────────────────────────────────────────

def test_rbkb_derivation_matches_the_codex_worked_example():
    """The docket's own numbers, reproduced field by field.

    "the displayed figures imply the insider moved from roughly 2,270 to 27,270
    shares, or about 12 times the prior holding" — if this drifts, the lane has
    stopped implementing the document it cites.
    """
    from engine.marketing.insider_feed import derive_transaction

    d = derive_transaction(**_RBKB)
    assert d["purchase_value"] == pytest.approx(298_500.0)
    assert d["prior_shares"] == pytest.approx(2_270.0)
    assert d["relative_stake_increase_pct"] == pytest.approx(1_101.32, abs=0.01)
    assert d["stake_multiple"] == pytest.approx(12.01, abs=0.01)
    assert d["reconciles"] is True
    assert d["new_position"] is False


def test_zero_prior_shares_is_a_new_position_not_a_percentage():
    """"If prior shares are zero, classify … instead of calculating a percentage."

    A division that would raise is the obvious failure; the quiet one is a lane
    that reports "inf%" or 0.0 and lets the writer treat it as a real figure.
    """
    from engine.marketing.insider_feed import derive_transaction

    d = derive_transaction(shares=100_000, price=4.95, shares_following=100_000)
    assert d["new_position"] is True
    assert d["relative_stake_increase_pct"] is None
    assert d["stake_multiple"] is None


def test_holdings_below_the_purchase_do_not_reconcile():
    """The codex's reconciliation check, as a refusal.

    Post-transaction shares under the quantity purchased is internally
    impossible for a purchase. The lane must say so rather than derive a
    negative prior stake and publish the percentage that falls out of it.
    """
    from engine.marketing.insider_feed import classify_mechanism, derive_transaction

    d = derive_transaction(shares=25_000, price=11.94, shares_following=1_000)
    assert d["reconciles"] is False
    assert d["prior_shares"] is None
    assert classify_mechanism(d)[0] == "NEEDS_REVIEW"


def test_rounded_post_transaction_holdings_are_flagged_approximate():
    """"If post-transaction holdings are rounded, label the derived change
    approximate." A holding of exactly 46,000 is a lot figure; 46,977 is not."""
    from engine.marketing.insider_feed import derive_transaction

    assert derive_transaction(shares=1_000, price=50.0,
                              shares_following=46_000)["approximate"] is True
    assert derive_transaction(shares=1_000, price=50.0,
                              shares_following=46_977)["approximate"] is False


# ─────────────────────────────────────────────────────────────────────────────
# 2. Mechanism classification — the codex's five labels plus the refusal
# ─────────────────────────────────────────────────────────────────────────────

def test_mechanism_classification_table():
    """Table-driven over the codex's five observed cases and its own labels.

    The RBKB row is the load-bearing one: $298.5K is the SMALLEST purchase in
    the docket's table and the largest relative move in it, so a lane that
    classified on dollars would put it last. PBLS ($6.92M, ~0.85%) and ELV
    ($1.002M, ~1.61%) are the mirror image — big cheques, small stake moves —
    and TOI is neither, which is a refusal rather than a weak post.
    """
    from engine.marketing.insider_feed import classify_mechanism, derive_transaction

    cases = (
        # (label, shares, price, following, cluster_n, repeat_n, expected)
        ("RBKB 12x",      25_000,  11.94,  27_270,      0, 1, "MATERIAL_ADDITION"),
        ("FCEL new",     100_000,   4.95, 100_000,      0, 1, "NEW_POSITION"),
        ("PBLS 0.85%",     8_500, 814.00, 1_008_500,    0, 1, "SMALL_ADDITION_TO_LARGE_STAKE"),
        ("ELV 1.61%",      2_000, 501.00, 126_000,      0, 1, "SMALL_ADDITION_TO_LARGE_STAKE"),
        ("TOI 0.17% small", 1_000,  94.90, 589_000,     0, 1, "NEEDS_REVIEW"),
        ("cluster",        1_000,  94.90, 589_000,      3, 1, "CLUSTER_BUY"),
        ("repeat",         1_000,  94.90, 589_000,      0, 2, "REPEAT_BUY"),
    )
    for label, shares, price, following, cluster_n, repeat_n, expected in cases:
        derived = derive_transaction(shares=shares, price=price,
                                     shares_following=following)
        got, why = classify_mechanism(derived, cluster_n=cluster_n,
                                      repeat_n=repeat_n)
        assert got == expected, f"{label}: expected {expected}, got {got}"
        assert why.strip(), f"{label}: mechanism sentence must not be empty"


def test_arithmetic_mechanisms_outrank_pattern_mechanisms():
    """A twelve-fold personal increase is not relabelled "cluster buying".

    Precedence is documented in `classify_mechanism`; this pins it. The pattern
    fact survives in the packet (§3 covers that) — it just does not take the
    headline away from the better fact.
    """
    from engine.marketing.insider_feed import classify_mechanism, derive_transaction

    derived = derive_transaction(**_RBKB)
    assert classify_mechanism(derived, cluster_n=9, repeat_n=5)[0] == "MATERIAL_ADDITION"


def test_mechanism_sentence_never_infers_motive():
    """"Remove unsupported claims about conviction, undervaluation, inside
    knowledge, or future price performance." (codex §Creation workflow step 6)"""
    from engine.marketing.insider_feed import classify_mechanism, derive_transaction

    banned = ("conviction", "undervalued", "never random", "no reason to sell",
              "insider knowledge", "will rise", "bullish signal", "proof")
    for shares, price, following, cluster_n, repeat_n in (
        (25_000, 11.94, 27_270, 0, 1),
        (100_000, 4.95, 100_000, 0, 1),
        (8_500, 814.0, 1_008_500, 0, 1),
        (1_000, 94.9, 589_000, 3, 1),
        (1_000, 94.9, 589_000, 0, 4),
    ):
        derived = derive_transaction(shares=shares, price=price,
                                     shares_following=following)
        _, why = classify_mechanism(derived, cluster_n=cluster_n, repeat_n=repeat_n)
        low = why.lower()
        for word in banned:
            assert word not in low, f"motive language {word!r} in: {why}"


# ─────────────────────────────────────────────────────────────────────────────
# 3. Reporting-lag honesty — present, VISIBLE, and enforced by refusal
# ─────────────────────────────────────────────────────────────────────────────

def test_congress_packet_states_the_reporting_lag():
    """"traded Jun 12, disclosed today" — both dates and the gap, in one fact."""
    from engine.marketing.congress_feed import LAG_FACT_ID, congress_facts

    packet = congress_facts({
        "ticker": "NVDA", "representative": "Jane Q. Public", "title": "Rep.",
        "side": "purchase", "transaction_date": "2026-06-12",
        "report_date": "2026-07-29", "lag_days": 47,
        "amount_low": 50_001, "amount_high": 100_000, "amount_mid": 75_000,
    })
    lag = next(f for f in packet["facts"] if f["id"] == LAG_FACT_ID)
    assert "Jun 12" in lag["text"]
    assert "Jul 29" in lag["text"]
    assert "47 days" in lag["text"]


def test_insider_packet_states_the_filing_lag():
    from engine.marketing.insider_feed import LAG_FACT_ID, insider_facts

    packet = insider_facts({
        "ticker": "RBKB", "insider_name": "Nancy Koskey Patzwahl",
        "role": "Chief Financial Officer", "shares": 25_000, "price": 11.94,
        "shares_following": 27_270, "prior_shares": 2_270,
        "purchase_value": 298_500.0, "trade_date": "2026-07-27",
        "file_date": "2026-07-28", "lag_days": 1, "ownership": "direct",
        "mechanism": "MATERIAL_ADDITION", "why_it_matters": "It got bigger.",
    })
    lag = next(f for f in packet["facts"] if f["id"] == LAG_FACT_ID)
    assert "Jul 27" in lag["text"] and "Jul 28" in lag["text"]
    assert "1 day later" in lag["text"], "singular day must not read '1 days'"


def test_lag_fact_is_inside_the_three_facts_the_writer_actually_sees():
    """PRESENCE IS NOT ENOUGH — this is the whole point of the guard.

    `copywriter.build_context` hands the writer `all_facts[:3]` after sorting by
    (-salience, id). A lag fact ranked fourth is in the packet, absent from the
    prompt, and absent from the post — a disclosure that looks compliant in the
    plan JSON and is not compliant on the timeline.
    """
    from engine.marketing.congress_feed import TOP_FACTS_VISIBLE
    from engine.marketing.congress_feed import LAG_FACT_ID as C_LAG, congress_facts
    from engine.marketing.insider_feed import LAG_FACT_ID as I_LAG, insider_facts

    congress = congress_facts({
        "ticker": "NVDA", "representative": "Jane Q. Public", "title": "Rep.",
        "side": "purchase", "transaction_date": "2026-06-12",
        "report_date": "2026-07-29", "lag_days": 47,
        "amount_low": 50_001, "amount_high": 100_000,
        "member_context": "has one of the chamber's better-documented disclosure records",
    })
    insider = insider_facts({
        "ticker": "RBKB", "insider_name": "Nancy Koskey Patzwahl",
        "role": "Chief Financial Officer", "shares": 25_000, "price": 11.94,
        "shares_following": 27_270, "prior_shares": 2_270,
        "purchase_value": 298_500.0, "trade_date": "2026-07-27",
        "file_date": "2026-07-28", "lag_days": 1, "ownership": "direct",
        "cluster_n": 4, "mechanism": "MATERIAL_ADDITION",
        "why_it_matters": "The relative change is what matters.",
        "power_context": "the wider insider tape at this company has leaned toward buying",
    })
    for packet, lag_id in ((congress, C_LAG), (insider, I_LAG)):
        # `fold_numbers` returns the facts already ordered as build_context sorts.
        visible = [f["id"] for f in packet["facts"][:TOP_FACTS_VISIBLE]]
        assert lag_id in visible, f"{lag_id} ranked outside the visible set: {visible}"


def test_a_packet_without_a_visible_lag_fact_refuses():
    """The guard RAISES; it does not warn and continue.

    Both spellings of the defect are covered: the fact deleted outright, and the
    fact demoted below the cut — the second is the one a future edit produces by
    accident when it adds a higher-salience fact.
    """
    from engine.marketing.congress_feed import (
        LagDisclosureError, assert_lag_disclosed, congress_facts)
    from engine.marketing.insider_feed import (
        assert_lag_disclosed as insider_assert, LAG_FACT_ID as I_LAG)

    packet = congress_facts({
        "ticker": "NVDA", "representative": "Jane Q. Public", "title": "Rep.",
        "side": "purchase", "transaction_date": "2026-06-12",
        "report_date": "2026-07-29", "lag_days": 47,
        "amount_low": 50_001, "amount_high": 100_000,
    })

    stripped = {"facts": [f for f in packet["facts"] if "lag" not in f["id"]],
                "numbers_whitelist": []}
    with pytest.raises(LagDisclosureError):
        assert_lag_disclosed(stripped)

    demoted = {"facts": [
        dict(f, salience=0) if "lag" in f["id"] else dict(f, salience=9)
        for f in packet["facts"]
    ] + [{"id": "filler_a", "text": "a", "salience": 9},
         {"id": "filler_b", "text": "b", "salience": 9}],
        "numbers_whitelist": []}
    with pytest.raises(LagDisclosureError):
        assert_lag_disclosed(demoted)

    with pytest.raises(LagDisclosureError):
        insider_assert({"facts": [{"id": I_LAG, "text": "x", "salience": 0},
                                  {"id": "a", "text": "a", "salience": 5},
                                  {"id": "b", "text": "b", "salience": 5},
                                  {"id": "c", "text": "c", "salience": 5}]})


def test_the_disclosure_note_is_writer_visible_on_both_lanes():
    """M4. "This is a filing, not a call" was ranked ninth of nine on the
    insider lane and below the member record on the congress lane, so on a
    typical packet the one sentence that stops a filing post from reading as a
    recommendation was in the packet and absent from the prompt. Presence was
    never the property that mattered — the lag guard learned that first."""
    from engine.marketing.congress_feed import (
        DISCLOSURE_FACT_ID as C_NOTE, TOP_FACTS_VISIBLE, congress_facts)
    from engine.marketing.insider_feed import (
        DISCLOSURE_FACT_ID as I_NOTE, insider_facts)

    congress = congress_facts({
        "ticker": "NVDA", "representative": "Jane Q. Public", "title": "Rep.",
        "side": "purchase", "transaction_date": "2026-06-12",
        "report_date": "2026-07-29", "lag_days": 47,
        "amount_low": 50_001, "amount_high": 100_000,
        "member_context": "has a long list of disclosed trades on file",
    })
    insider = insider_facts({
        "ticker": "RBKB", "insider_name": "Nancy Koskey Patzwahl",
        "role": "Chief Financial Officer", "shares": 25_000, "price": 11.94,
        "shares_following": 27_270, "prior_shares": 2_270,
        "purchase_value": 298_500.0, "trade_date": "2026-07-27",
        "file_date": "2026-07-28", "lag_days": 1, "ownership": "direct",
        "cluster_n": 4, "mechanism": "MATERIAL_ADDITION",
        "why_it_matters": "The relative change is what matters.",
        "power_context": "the wider insider tape at this company has leaned toward buying",
    })
    for packet, note_id in ((congress, C_NOTE), (insider, I_NOTE)):
        visible = [f["id"] for f in packet["facts"][:TOP_FACTS_VISIBLE]]
        assert note_id in visible, f"{note_id} ranked outside {visible}"
        blob = " ".join(f["text"] for f in packet["facts"][:TOP_FACTS_VISIBLE])
        assert "not a call" in blob


def test_promoting_the_disclosure_did_not_cost_the_mechanism_its_slot():
    """The insider lane's thesis is the MECHANISM (the codex's RBKB case: a
    $299K buy that multiplied a stake outranks a $6.92M one). Three slots, four
    things to say, so the mechanism rides on the transaction fact rather than
    being dropped for the disclosure."""
    from engine.marketing.congress_feed import TOP_FACTS_VISIBLE
    from engine.marketing.insider_feed import insider_facts

    packet = insider_facts({
        "ticker": "RBKB", "insider_name": "Nancy Koskey Patzwahl",
        "role": "Chief Financial Officer", "shares": 25_000, "price": 11.94,
        "shares_following": 27_270, "prior_shares": 2_270,
        "purchase_value": 298_500.0, "trade_date": "2026-07-27",
        "file_date": "2026-07-28", "lag_days": 1, "ownership": "direct",
        "mechanism": "MATERIAL_ADDITION",
        "why_it_matters": "The relative change is what matters.",
    })
    blob = " ".join(f["text"] for f in packet["facts"][:TOP_FACTS_VISIBLE])
    assert "The relative change is what matters." in blob
    assert "bought 25,000 shares" in blob
    assert "day later" in blob            # the lag
    assert "not a call" in blob           # the disclosure


def test_a_packet_whose_disclosure_is_outranked_refuses():
    """The guard raises rather than shipping quietly, exactly as the lag guard
    does. This is the failure a future fact addition produces by accident."""
    from engine.marketing.congress_feed import (
        DISCLOSURE_FACT_ID, LagDisclosureError, assert_disclosure_visible)
    from engine.marketing.insider_feed import (
        assert_disclosure_visible as insider_assert)

    demoted = {"facts": [
        {"id": DISCLOSURE_FACT_ID, "text": "note", "salience": 1},
        {"id": "a", "text": "a", "salience": 9},
        {"id": "b", "text": "b", "salience": 9},
        {"id": "c", "text": "c", "salience": 9},
    ]}
    with pytest.raises(LagDisclosureError):
        assert_disclosure_visible(demoted)
    with pytest.raises(LagDisclosureError):
        insider_assert({"facts": [{"id": "x", "text": "x", "salience": 9},
                                  {"id": "y", "text": "y", "salience": 9},
                                  {"id": "z", "text": "z", "salience": 9}]})


class _Frame:
    """A minimal records-yielding stand-in for a DataFrame.

    Lets the date and eligibility gates be proven WITHOUT pandas, so they keep
    their teeth in the thin marketing CI pack. `__getitem__` raises so
    `narrow_by_day`'s fast path falls back exactly as it does on a frame whose
    column cannot be masked.
    """

    def __init__(self, rows):
        self._rows = rows

    def to_dict(self, _orient):
        return list(self._rows)

    def __getitem__(self, _key):
        raise TypeError("not maskable")


def test_an_undatable_row_is_dropped_rather_than_posted_without_its_lag():
    """Fail CLOSED. A row we cannot date is a row whose honesty we cannot write.

    This is the reason the date parse is a filter and not a formatting concern:
    a missing TransactionDate would otherwise render as "The trade happened ;
    it only became public Jul 29, 0 days later" — a sentence that is both broken
    and false.
    """
    from engine.marketing.congress_feed import new_disclosures
    from engine.marketing.insider_feed import open_market_purchases

    assert new_disclosures(_Frame([_congress_row(TransactionDate=None)]),
                           today=_TODAY) == []
    assert new_disclosures(_Frame([_congress_row(ReportDate="")]),
                           today=_TODAY) == []
    assert open_market_purchases(_Frame([_insider_row(fileDate=None)]),
                                 today=_TODAY) == []
    # A trade disclosed a year late is a compliance story, not a market one.
    assert new_disclosures(_Frame([_congress_row(TransactionDate="2025-06-12")]),
                           today=_TODAY) == []
    # …and the sane row still comes through, so the gate is not vacuously green.
    assert len(new_disclosures(_Frame([_congress_row()]), today=_TODAY)) == 1


# ─────────────────────────────────────────────────────────────────────────────
# 4. Eligibility — open-market only, materiality floors, purchases first
# ─────────────────────────────────────────────────────────────────────────────

def test_only_transaction_code_p_acquisitions_are_called_purchases(tmp_path):
    """Grants, option exercises, tax withholding and gifts are NOT purchases.

    This is the codex's transaction-integrity dimension, and it is the single
    highest-consequence filter in the lane: an award published as "the CFO
    bought" is a false statement about a named person.
    """
    from engine.marketing.insider_feed import open_market_purchases

    rows = [_insider_row(TransactionCode=code, AcquiredDisposedCode=ad,
                         Ticker=f"T{i}")
            for i, (code, ad) in enumerate(
                (("A", "A"), ("M", "A"), ("F", "D"), ("C", "A"),
                 ("G", "A"), ("J", "A"), ("S", "D"), ("P", "D")))]
    df = _write_parquet(rows, tmp_path / "data" / "quiver" / "insiders.parquet")
    assert open_market_purchases(df, today=_TODAY) == []

    df_ok = _write_parquet([_insider_row()],
                           tmp_path / "data" / "quiver" / "ok.parquet")
    assert [c["ticker"] for c in open_market_purchases(df_ok, today=_TODAY)] == ["RBKB"]


def test_congress_materiality_floor_drops_the_noise_bucket(tmp_path):
    """73,206 of 99,585 real rows sit in $1,001–$15,000. That bucket IS the floor."""
    from engine.marketing.congress_feed import new_disclosures

    small = _congress_row(Ticker="AMAT", Range="$1,001 - $15,000", Amount="1001.0")
    big = _congress_row(Ticker="NVDA", Range="$100,001 - $250,000", Amount="100001.0")
    df = _write_parquet([small, big],
                        tmp_path / "data" / "quiver" / "congress.parquet")
    assert [c["ticker"] for c in new_disclosures(df, today=_TODAY)] == ["NVDA"]
    # …and the floor is a config lever, not a constant.
    got = new_disclosures(df, today=_TODAY, cfg={"congress_lane": {"min_amount_usd": 100}})
    assert sorted(c["ticker"] for c in got) == ["AMAT", "NVDA"]


def test_insider_value_floor_drops_token_purchases(tmp_path):
    from engine.marketing.insider_feed import open_market_purchases

    tiny = _insider_row(Ticker="TINY", Shares=10.0, PricePerShare=2.0,
                        SharesOwnedFollowing=1_000.0)
    df = _write_parquet([tiny, _insider_row()],
                        tmp_path / "data" / "quiver" / "insiders.parquet")
    assert [c["ticker"] for c in open_market_purchases(df, today=_TODAY)] == ["RBKB"]


def test_dividend_reinvestment_is_not_a_decision(tmp_path):
    """A standing instruction published as "bought" is the congress-lane spelling
    of the grant-counted-as-a-purchase error."""
    from engine.marketing.congress_feed import new_disclosures

    df = _write_parquet(
        [_congress_row(Ticker="FMAO", Description="DIVIDEND REINVESTMENT",
                       Range="$100,001 - $250,000", Amount="100001.0")],
        tmp_path / "data" / "quiver" / "congress.parquet")
    assert new_disclosures(df, today=_TODAY) == []


def test_option_and_other_security_types_are_excluded(tmp_path):
    from engine.marketing.congress_feed import new_disclosures

    df = _write_parquet(
        [_congress_row(Ticker="NVDA", TickerType="Stock Option",
                       Range="$100,001 - $250,000", Amount="100001.0"),
         _congress_row(Ticker="MSFT", TickerType="Other Securities",
                       Range="$100,001 - $250,000", Amount="100001.0")],
        tmp_path / "data" / "quiver" / "congress.parquet")
    assert new_disclosures(df, today=_TODAY) == []


def test_purchases_outrank_sales_regardless_of_size(tmp_path):
    """A sale has a dozen innocent explanations; a purchase spends money."""
    from engine.marketing.congress_feed import new_disclosures

    df = _write_parquet(
        [_congress_row(Ticker="SOLD", Transaction="Sale",
                       Range="$1,000,001 - $5,000,000", Amount="1000001.0"),
         _congress_row(Ticker="BUY", Transaction="Purchase",
                       Range="$50,001 - $100,000", Amount="50001.0")],
        tmp_path / "data" / "quiver" / "congress.parquet")
    assert [c["ticker"] for c in new_disclosures(df, today=_TODAY)] == ["BUY", "SOLD"]


def test_stale_crawl_rows_are_not_tonights_news(tmp_path):
    """`_first_seen` is the only column that can answer "new tonight"."""
    from engine.marketing.congress_feed import new_disclosures

    df = _write_parquet(
        [_congress_row(Ticker="OLD", _first_seen="2026-07-01T00:05:00+00:00")],
        tmp_path / "data" / "quiver" / "congress.parquet")
    assert new_disclosures(df, today=_TODAY) == []


def test_daily_caps_hold_and_selection_is_deterministic(tmp_path):
    """Two of each per day, fleet-wide, and the same night twice agrees.

    Determinism is not a nicety here: the governor can re-run a date, and a lane
    that reshuffled would plan a different post for the same disclosure.
    """
    from engine.marketing.congress_feed import new_disclosures

    rows = [_congress_row(Ticker=f"T{i}", Range="$100,001 - $250,000",
                          Amount=f"{100_001 + i}.0")
            for i in range(9)]
    df = _write_parquet(rows, tmp_path / "data" / "quiver" / "congress.parquet")
    first = new_disclosures(df, today=_TODAY)
    assert len(first) == 2
    assert [c["ticker"] for c in first] == [c["ticker"] for c in new_disclosures(df, today=_TODAY)]
    assert len(new_disclosures(df, today=_TODAY,
                               cfg={"congress_lane": {"max_per_day": 5}})) == 5


def test_a_disabled_lane_produces_nothing(tmp_path):
    from engine.marketing.congress_feed import new_disclosures
    from engine.marketing.insider_feed import open_market_purchases

    congress = _write_parquet([_congress_row()],
                              tmp_path / "data" / "quiver" / "congress.parquet")
    insider = _write_parquet([_insider_row()],
                             tmp_path / "data" / "quiver" / "insiders.parquet")
    assert new_disclosures(congress, today=_TODAY,
                           cfg={"congress_lane": {"enabled": False}}) == []
    assert open_market_purchases(insider, today=_TODAY,
                                 cfg={"insider_lane": {"enabled": False}}) == []


# ─────────────────────────────────────────────────────────────────────────────
# 5. The LKFN-class cooldown interplay (masterplan §5.1)
# ─────────────────────────────────────────────────────────────────────────────

def _seed_posted(tmp_path, ticker, *, as_of):
    """Put a real posted item on the outbox ledger — the canonical path.

    Hand-rolled JSONL would bypass make_item/validate_item and prove nothing
    about what `ticker_exposure` actually reads.
    """
    from engine.marketing.outbox import enqueue, make_item, transition

    item = make_item(
        account="flagship", kind="watchlist",
        text=f"${ticker} back on the board after the flush.",
        as_of=as_of, scheduled_at=None, slot="D1-S1",
        provenance="content_studio", source={"ticker": ticker}, now=_FIXED_NOW,
    )
    assert enqueue(item, root=tmp_path, max_per_account_day=99) == "queued"
    for step in ("approved", "posted"):
        assert transition(item["id"], step, actor="test", root=tmp_path, now=_FIXED_NOW)
    return item


def test_a_congress_pick_on_a_ticker_posted_yesterday_defers(tmp_path):
    """THE NAMED LKFN CASE, in the filing lane.

    On 2026-07-29 LKFN, GPI and CBOE were all planned the day after they posted,
    because nothing asked the ledger "did we already show this name?". A filing
    lane holding two slots a day is the easiest place for that to happen again —
    the disclosure is genuinely new even when the ticker is not. So the cooldown
    is applied AT SOURCE and the lane spends the slot on its next-best candidate
    rather than on a name a desk covered yesterday.
    """
    from engine.marketing.congress_feed import new_disclosures
    from engine.marketing.content_studio import cooled_tickers, ticker_exposure

    _seed_posted(tmp_path, "LKFN", as_of=_YESTERDAY)
    exposure = ticker_exposure(tmp_path, as_of=_TODAY)
    assert exposure.get("LKFN") == _YESTERDAY
    cooled = cooled_tickers(exposure, as_of=_TODAY, kind="watchlist")
    assert "LKFN" in cooled

    df = _write_parquet(
        [_congress_row(Ticker="LKFN", Range="$1,000,001 - $5,000,000",
                       Amount="1000001.0"),
         _congress_row(Ticker="CBOE", Range="$50,001 - $100,000",
                       Amount="50001.0")],
        tmp_path / "data" / "quiver" / "congress.parquet")

    # Uncooled, the far larger LKFN disclosure wins on materiality …
    assert new_disclosures(df, today=_TODAY)[0]["ticker"] == "LKFN"
    # … cooled, it defers and the slot goes to the next-best name, not to nothing.
    got = [c["ticker"] for c in new_disclosures(df, today=_TODAY, cooled=cooled)]
    assert "LKFN" not in got
    assert got == ["CBOE"]


def test_the_insider_lane_honours_the_same_cooldown(tmp_path):
    from engine.marketing.insider_feed import open_market_purchases

    df = _write_parquet(
        [_insider_row(Ticker="RBKB"), _insider_row(Ticker="FCEL")],
        tmp_path / "data" / "quiver" / "insiders.parquet")
    got = [c["ticker"] for c in open_market_purchases(
        df, today=_TODAY, cooled=frozenset({"RBKB"}))]
    assert got == ["FCEL"]


# ─────────────────────────────────────────────────────────────────────────────
# 6. Display-tier only — a score never leaves the engine
# ─────────────────────────────────────────────────────────────────────────────

def test_member_context_is_plain_words_and_never_a_score():
    """ExcessReturn is horizon-inconsistent by construction (see
    engine/congress_members.py). Its derived rate is an internal ranking input,
    not a sentence we may print beside a politician's name. The guard is a digit
    check because every spelling of the defect — "39.3%", "tier 2", "0.71" —
    contains one."""
    from engine.marketing.congress_feed import member_context

    for n_eff in (0, 1, 5, 12, 40):
        phrase = member_context({"n_eff_valid": n_eff, "chamber": "House"})
        if n_eff == 0:
            assert phrase == "", "no disclosures is no sentence, not a verdict"
            continue
        assert phrase and not any(ch.isdigit() for ch in phrase)
        # Internal slugs are banned vocabulary on user-facing surfaces.
        for slug in ("proven", "watch", "limited", "tier", "shrunk", "hit rate"):
            assert slug not in phrase.lower(), f"{slug!r} leaked into {phrase!r}"
    assert member_context(None) == ""
    assert member_context({}) == ""


def test_member_context_describes_ACTIVITY_never_performance():
    """M5. The phrase used to be derived from the member TIER, and the tier is
    not an activity fact: "proven" means n_eff_valid >= 8 AND a shrunk hit rate
    above the pooled prior. So the copy beside a politician's name carried an
    internal, horizon-inconsistent performance claim in plain words — and it was
    wrong on its own terms, because a member with a long history and a
    below-pooled rate is "watch" and was described as having a SHORT one."""
    from engine.marketing.congress_feed import member_context

    long_history_poor_rate = {"n_eff_valid": 25, "tier": "watch",
                              "shrunk_hit_rate": 0.21}
    short_history_good_rate = {"n_eff_valid": 3, "tier": "proven",
                               "shrunk_hit_rate": 0.88}
    long_phrase = member_context(long_history_poor_rate)
    short_phrase = member_context(short_history_good_rate)

    assert "long" in long_phrase, long_phrase
    assert "short" in short_phrase, short_phrase
    # The judgment vocabulary is gone in both directions: no praise, no verdict.
    for phrase in (long_phrase, short_phrase):
        for word in ("better", "best", "well", "poor", "reliable", "accurate",
                     "judge", "record of", "track record", "successful"):
            assert word not in phrase.lower(), f"{word!r} in {phrase!r}"

    # A tier with no count says nothing at all rather than guessing.
    assert member_context({"tier": "proven"}) == ""


def test_insider_power_contributes_words_not_its_score():
    from engine.marketing.insider_feed import power_context

    phrase = power_context({"signal": "insider_buy", "score": 87.4})
    assert phrase and not any(ch.isdigit() for ch in phrase)
    assert "87" not in phrase
    assert power_context({"score": 87.4}) == ""
    assert power_context(None) == ""


def test_assert_no_score_raises_on_a_digit():
    from engine.marketing.congress_feed import ScoreLeakError, assert_no_score

    assert_no_score("has one of the chamber's better-documented records")
    with pytest.raises(ScoreLeakError):
        assert_no_score("hits on 39.3% of disclosed trades")


def test_congress_copy_never_prints_the_excess_return(tmp_path):
    """The column is in the source frame; it must not be in the packet."""
    from engine.marketing.congress_feed import candidates, load_congress

    _write_parquet([_congress_row(ExcessReturn=87.65)],
                   tmp_path / "data" / "quiver" / "congress.parquet")
    assert load_congress(tmp_path) is not None
    for cand in candidates(tmp_path, today=_TODAY):
        blob = " ".join(f["text"] for f in cand["facts"]["facts"])
        assert "87.6" not in blob and "87.65" not in blob


# ─────────────────────────────────────────────────────────────────────────────
# 7. House picks — every pick names the desk that produced it
# ─────────────────────────────────────────────────────────────────────────────

def _write_house_artifacts(tmp_path):
    import json

    fd = tmp_path / "site" / "factordata"
    fd.mkdir(parents=True, exist_ok=True)
    (fd / "impulse.json").write_text(json.dumps({
        "as_of": _TODAY, "status": "ok",
        "buy": [{"ticker": "AWI", "name": "Armstrong", "sector": "Industrials",
                 "price": 179.4, "impulse_score": 100, "state": "EARLY_IGNITION",
                 "just_starting": True, "days_igniting": 1}],
        "igniting": [], "coiling": [],
    }), encoding="utf-8")
    (fd / "tech_screener.json").write_text(json.dumps({
        "universe_n": 231,
        "stocks": {"DG": {"name": "Dollar General", "price": 126.2, "score": 0.81,
                          "band": "Hold", "active_buy": 20, "active_total": 28}},
    }), encoding="utf-8")
    ad = tmp_path / "site" / "allocationdata"
    ad.mkdir(parents=True, exist_ok=True)
    (ad / "special_situations.json").write_text(json.dumps({
        "schema": "special_situations.v1", "is_context_only": True,
        "by_ticker": {"ASH": {"ticker": "ASH", "company": "ASHLAND INC.",
                              "category": "Capital Returns", "stage": "announced",
                              "date": _TODAY, "country": "US",
                              "confidence": "low"}},
    }), encoding="utf-8")


def test_every_house_pick_names_its_desk_in_plain_words(tmp_path):
    """A reader who cannot tell where a name came from cannot weigh it — and an
    unattributed screen output is indistinguishable from a call."""
    from engine.marketing.house_picks import DESK_WORDS, house_picks

    _write_house_artifacts(tmp_path)
    picks = house_picks(tmp_path, today=_TODAY)
    assert {p["ticker"] for p in picks} == {"AWI", "DG", "ASH"}
    for pick in picks:
        lead = pick["facts"]["facts"][0]["text"]
        assert DESK_WORDS[pick["engine"]].lower() in lead.lower(), lead
        assert lead[:1].isupper(), f"sentence case: {lead!r}"


def test_house_pick_copy_carries_no_internal_slug(tmp_path):
    """"EARLY_IGNITION", "impulse_score", "tier_a" are internal state names, and
    the design doctrine bans every one of them from a user-facing surface."""
    from engine.marketing.house_picks import house_picks

    _write_house_artifacts(tmp_path)
    banned = ("EARLY_IGNITION", "IGNITING", "COILING", "impulse_score",
              "active_buy", "setup_grade", "vote-scheduled", "_", "v1")
    for pick in house_picks(tmp_path, today=_TODAY):
        blob = " ".join(f["text"] for f in pick["facts"]["facts"])
        for slug in banned:
            assert slug not in blob, f"{slug!r} leaked into: {blob}"


def test_each_desk_ships_its_own_disclosure(tmp_path):
    """The special-situations artifact declares itself context-only; a pick that
    dropped that on the way to a timeline would launder an event tracker into a
    recommendation. Same for the tech lab's survivor-universe caveat."""
    from engine.marketing.house_picks import house_picks

    _write_house_artifacts(tmp_path)
    by_engine = {p["engine"]: p for p in house_picks(tmp_path, today=_TODAY)}
    special = " ".join(f["text"] for f in by_engine["special_situations"]["facts"]["facts"])
    assert "context" in special.lower() and "recommendation" in special.lower()
    lab = " ".join(f["text"] for f in by_engine["tech_lab"]["facts"]["facts"])
    assert "long-surviving" in lab or "large caps" in lab


def test_house_picks_never_displace_a_name_the_plan_already_claimed(tmp_path):
    """Supply, not competition: the picks are EXTRA fact supply for existing
    kinds and must not push out a Prophet or mover item."""
    from engine.marketing.house_picks import house_picks

    _write_house_artifacts(tmp_path)
    got = {p["ticker"] for p in house_picks(tmp_path, today=_TODAY,
                                            exclude=frozenset({"AWI"}))}
    assert "AWI" not in got and got == {"DG", "ASH"}
    cooled = {p["ticker"] for p in house_picks(tmp_path, today=_TODAY,
                                               cooled=frozenset({"DG"}))}
    assert "DG" not in cooled


def test_stale_special_situations_are_not_news(tmp_path):
    from engine.marketing.house_picks import (
        load_special_situations, special_situation_picks)

    _write_house_artifacts(tmp_path)
    data = load_special_situations(tmp_path)
    assert special_situation_picks(data, today=_TODAY) != []
    assert special_situation_picks(data, today="2026-08-15") == []


def test_absent_artifacts_cost_only_this_lane(tmp_path):
    """Fail-soft: an empty repo yields no picks and raises nothing."""
    from engine.marketing.house_picks import house_picks, load_impulse

    assert load_impulse(tmp_path) is None
    assert house_picks(tmp_path, today=_TODAY) == []


# ─────────────────────────────────────────────────────────────────────────────
# 8. Packet ↔ writer contract (whitelist, rounding, no invented numbers)
# ─────────────────────────────────────────────────────────────────────────────

def test_packets_pass_the_copy_validator_with_their_own_facts():
    """THE SELF-CONSISTENCY GUARANTEE.

    `validate_copy` rejects any number not in `numbers_whitelist`, and the
    whitelist is built from the packet's own rendered text — so quoting a fact
    verbatim must always be legal. It is not obvious that it is: the validator's
    extractor reads "27,270" as the fragment "270" because the comma is a word
    boundary, and a hand-written whitelist would have missed it. This test is
    what pins the two extractors together.
    """
    from engine.marketing.copywriter import build_context, validate_copy
    from engine.marketing.congress_feed import congress_facts
    from engine.marketing.insider_feed import insider_facts

    packets = [
        ("congress", congress_facts({
            "ticker": "NVDA", "representative": "Jane Q. Public", "title": "Rep.",
            "side": "purchase", "transaction_date": "2026-06-12",
            "report_date": "2026-07-29", "lag_days": 47,
            "amount_low": 50_001, "amount_high": 100_000})),
        ("insider", insider_facts({
            "ticker": "RBKB", "insider_name": "Nancy Koskey Patzwahl",
            "role": "Chief Financial Officer", "shares": 25_000, "price": 11.94,
            "shares_following": 27_270, "prior_shares": 2_270,
            "purchase_value": 298_500.0, "trade_date": "2026-07-27",
            "file_date": "2026-07-28", "lag_days": 1, "ownership": "direct",
            "mechanism": "MATERIAL_ADDITION",
            "why_it_matters": "The purchase took the disclosed holding to 12x "
                              "its previous size."})),
    ]
    for kind, packet in packets:
        item = {"ticker": packet["facts"][0]["text"].split()[-1].strip("."),
                "type": kind, "account": "flagship"}
        ctx = build_context(item, persona=None, facts=packet, extra=None)
        body = " ".join(f["text"] for f in packet["facts"])
        violations = [v for v in validate_copy("", body, ctx)
                      if "whitelist" in v or "invented" in v]
        assert violations == [], f"{kind}: {violations}"


def test_display_rounding_is_the_house_law_not_a_second_table():
    """Prices at the W1 magnitude law; money abbreviated only above 10K."""
    from engine.marketing.congress_feed import display_price, display_usd

    assert display_price(11.94) == "11.9"      # 10-100 → one decimal
    assert display_price(285.10) == "285"      # >=100 → integer
    assert display_price(4.87) == "4.87"       # <10 → two decimals
    for value, want in ((1_001, "$1,001"), (15_000, "$15K"), (298_500, "$298K"),
                        (6_920_000, "$6.92M"), (1_200_000_000, "$1.20B")):
        assert display_usd(value) == want, f"{value} -> {display_usd(value)}"


def test_the_whitelist_is_never_empty_when_the_packet_states_a_figure():
    """An empty whitelist reads to the writer as "use no numbers".

    The validator skips one- and two-digit bare integers, so a packet whose only
    figures were "38 days" and "$15K" licensed literally nothing while the
    prompt still said "use ONLY these numbers" — which strips the post of the
    facts it exists to carry.
    """
    from engine.marketing.congress_feed import congress_facts

    packet = congress_facts({
        "ticker": "NVDA", "representative": "Jane Q. Public", "title": "Rep.",
        "side": "purchase", "transaction_date": "2026-06-12",
        "report_date": "2026-07-20", "lag_days": 38,
        "amount_low": 15_000, "amount_high": 50_000})
    whitelist = packet["numbers_whitelist"]
    assert "$15K" in whitelist and "$50K" in whitelist and "38" in whitelist
    # …and no token may carry a sentence comma ("26," is not a number).
    assert not [t for t in whitelist if t.endswith(",")], whitelist


def test_a_shouted_filed_name_is_de_shouted_but_never_reordered():
    """The codex requires the exact filed name; ALL CAPS is shouting, not
    accuracy. "Moriarty Thomas M" keeps its filed order."""
    from engine.marketing.congress_feed import display_entity_name

    assert display_entity_name("RA CAPITAL MANAGEMENT, L.P.") == "Ra Capital Management, L.P."
    assert display_entity_name("ASHLAND INC.") == "Ashland Inc."
    assert display_entity_name("Moriarty Thomas M") == "Moriarty Thomas M"
    assert display_entity_name("Alon Haggai") == "Alon Haggai"


# ─────────────────────────────────────────────────────────────────────────────
# 9. The splice: real D1 slots, tape cards, no fabricated BUY label
# ─────────────────────────────────────────────────────────────────────────────

def _spliced_plan():
    """A real `content_plan` over the repo root, so the splice actually fires.

    DATA-DEPENDENT, like tests/test_marketing_chart_coverage.py's own fixtures:
    the tape variant has no v1 fallback by design, so a card only exists when
    `render_chart_v2` succeeds off real bars. Skipped on the thin lane, executed
    on the fat one.
    """
    pytest.importorskip("pandas")
    pytest.importorskip("pyarrow")
    from engine.marketing.chart_render import load_closes
    from engine.marketing.content_studio import content_plan

    root = Path(__file__).resolve().parents[1]
    cfg = {"desk_network": {"stage": "A", "accounts": [
        {"id": "flagship", "kind": "branded", "beat": "b",
         "voice": "authoritative desk"},
    ]}}
    # A REAL closes_loader, or `_filing_chart` returns None for every ticker,
    # no house pick is ever created, and the two card guards below skip
    # themselves into a vacuous pass. `plans=[]` keeps the Prophet chart loop
    # empty so the only cards rendered are this lane's.
    return content_plan(cfg, [], closes_loader=lambda t: load_closes(t, root, n=90),
                        root=root)


def test_filing_items_take_a_real_d1_ladder_slot():
    """`emit_from_content_plan` only processes `D1-`-prefixed slots.

    The confluence/mover lanes label their items "CONF-01"/"MOVER-01", which is
    correct for a publish-time lane and fatal for a planned one: the item would
    be built, budgeted, shaped, charged a model call, and then silently never
    reach the outbox. Nothing downstream reports that — the post simply never
    exists.
    """
    plan = _spliced_plan()
    spliced = [q for a in plan["accounts"] for q in a["queue"]
               if q.get("provenance") in ("congress_desk", "insider_desk", "house_picks")]
    if not spliced:
        pytest.skip("no filing/house-pick supply in the repo today")
    for item in spliced:
        slot = str(item.get("slot") or "")
        assert slot.startswith("D1-"), f"{item['id']} took a non-emitting slot {slot!r}"
    # No two items on one desk may hold the same rung.
    for acct in plan["accounts"]:
        slots = [q.get("slot") for q in acct["queue"] if str(q.get("slot") or "").startswith("D1-")]
        assert len(slots) == len(set(slots)), f"{acct['id']} double-booked: {slots}"


def test_a_filing_card_is_a_tape_card_and_never_a_buy_label():
    """THE FABRICATED-RECOMMENDATION GUARD.

    The v1 `render_signal_chart` fallback hard-draws a green BUY label at its
    marker. Reached from this lane it would put that label on "Rep. Public
    bought NVDA six weeks ago" — a recommendation we never made, attached to a
    named politician's trade. So the lane renders v2 or nothing, and the card it
    does produce declares itself `tape` with no marker and no anchor.
    """
    plan = _spliced_plan()
    spliced = {q["chart_id"] for a in plan["accounts"] for q in a["queue"]
               if q.get("provenance") in ("congress_desk", "insider_desk", "house_picks")
               and q.get("chart_id")}
    if not spliced:
        pytest.skip("no charted filing/house-pick supply in the repo today")
    charts = {c["id"]: c for c in plan["featured_charts"]}
    for chart_id in spliced:
        card = charts[chart_id]
        assert card.get("variant") == "tape", f"{chart_id}: {card.get('variant')!r}"
        assert card.get("marker_source") == "none", card.get("marker_source")
        assert "BUY" not in str(card.get("svg") or ""), (
            f"{chart_id} carries a BUY label on a no-claim post")


def test_a_house_pick_that_cannot_be_charted_is_never_created():
    """A house pick rides `watchlist`, which IS chart-required at publish time.

    A chartless one does not ship — it defers three days and then quarantines as
    `expired_no_media`, every night. So the pick is not created at all: an empty
    rung stays empty rather than filling with a post that cannot publish.
    """
    plan = _spliced_plan()
    picks = [q for a in plan["accounts"] for q in a["queue"]
             if q.get("provenance") == "house_picks"]
    if not picks:
        pytest.skip("no house-pick supply in the repo today")
    for pick in picks:
        assert pick.get("chart_id"), f"{pick['id']} ({pick['ticker']}) has no card"


# ─────────────────────────────────────────────────────────────────────────────
# 10. Registration into the planned-kind machinery
# ─────────────────────────────────────────────────────────────────────────────

def test_the_new_kinds_are_planned_kinds_everywhere_that_matters():
    """A kind in `outbox.KINDS` but not in `PLANNED_KINDS` would be exempt from
    the no-fallback law — template prose under a named politician."""
    from engine.marketing.content_studio import PLANNED_KINDS
    from engine.marketing.outbox import KINDS, planned_kinds

    for kind in ("congress", "insider"):
        assert kind in KINDS
        assert kind in PLANNED_KINDS
        assert kind in planned_kinds()


def test_filing_kinds_sit_at_dial_zero_in_every_profile():
    """A filing post's whole value is that the reader trusts the record. The
    `UNLISTED_KIND_DIAL` fallback of 1 would have granted a personality budget
    to a sentence whose job is to carry a reporting lag intact — which is the
    codex's measured failure of this exact format."""
    from engine.marketing.expression_dial import PROFILES, dial_for

    for profile in PROFILES:
        for kind in ("congress", "insider"):
            assert PROFILES[profile].get(kind) == 0, (profile, kind)
            assert dial_for(kind, profile=profile) == 0


def test_filing_kinds_do_not_default_to_a_level_angle():
    """A disclosure names no level. `angle_for`'s default is level_watch, so an
    unregistered kind would open every filing post on a price the filing never
    mentioned."""
    from engine.marketing.content_studio import angle_for

    for kind in ("congress", "insider"):
        assert angle_for(kind, 0) == "process"
        assert angle_for(kind, 1) != "level_watch"


def test_config_defaults_ship_the_lanes_enabled():
    """Operator 2026-07-29: the lanes go live. Enabling a SUPPLY lane is not
    enabling a publisher — the outbox approval gate is the arm that matters."""
    import engine.marketing.congress_feed as cf
    import engine.marketing.house_picks as hp
    import engine.marketing.insider_feed as inf

    assert cf.DEFAULTS["enabled"] is True
    assert inf.DEFAULTS["enabled"] is True
    assert hp.DEFAULTS["enabled"] is True
    # …and the shipped config agrees with the in-code floor.
    import yaml
    root = Path(__file__).resolve().parents[1]
    cfg = yaml.safe_load((root / "config" / "marketing.yml").read_text(encoding="utf-8"))
    assert cfg["congress_lane"]["enabled"] is True
    assert cfg["insider_lane"]["enabled"] is True
    assert cfg["house_picks"]["enabled"] is True
    assert cf.lane_cfg(cfg)["max_per_day"] == cfg["congress_lane"]["max_per_day"]
    assert inf.lane_cfg(cfg)["max_per_day"] == cfg["insider_lane"]["max_per_day"]


# ─────────────────────────────────────────────────────────────────────────────
# 11. The lane may fail soft, but never SILENTLY (E-wave review, MAJOR 5)
# ─────────────────────────────────────────────────────────────────────────────

def _lane_cfg() -> dict:
    return {"desk_network": {"stage": "A", "accounts": [
        {"id": "flagship", "kind": "branded", "beat": "US equities",
         "voice": "authoritative desk"},
    ]}}


def test_a_crashed_filing_lane_annotates_and_names_itself_in_the_census(
        monkeypatch, tmp_path, capsys):
    """`except Exception: pass` made two live lanes indistinguishable from empty.

    The census wrote `{"congress": 0, "insider": 0, "house_picks": 0}` from
    INSIDE the try, so a block that died on its first line produced the same row
    as a quiet night — and the lanes could stay dark for weeks behind a green
    nightly. Fail-soft stays (the rest of the plan must still build); silence
    does not.
    """
    from engine.marketing import congress_feed
    from engine.marketing.content_studio import content_plan

    def _boom(*a, **k):
        raise RuntimeError("parquet is unreadable")

    monkeypatch.setattr(congress_feed, "candidates", _boom, raising=False)
    plan = content_plan(_lane_cfg(), [], closes_loader=None, root=tmp_path)

    lanes = plan["content"]["selection"]["filing_lanes"]
    assert lanes.get("error") == "RuntimeError", (
        f"the census cannot tell a crash from an empty night: {lanes}")

    lines = capsys.readouterr().out.splitlines()
    hits = [ln for ln in lines
            if ln.startswith("::warning") and "marketing-filing-lanes" in ln]
    assert hits, (
        "no start-of-line ::warning for the crashed lane — a logger prefixes the "
        "line and GitHub drops the annotation silently "
        "(tests/test_gh_annotation_line_start.py)")
    assert "RuntimeError" in hits[0]

    # FAIL-SOFT IS STILL THE CONTRACT: the rest of the plan is unaffected.
    assert plan["accounts"], "a crashed filing lane took the whole plan down"


def test_a_healthy_filing_lane_carries_no_error_key(monkeypatch, tmp_path):
    """The mirror: a quiet night must not look like a crash either."""
    from engine.marketing import congress_feed, house_picks, insider_feed
    from engine.marketing.content_studio import content_plan

    for mod, name in ((congress_feed, "candidates"), (insider_feed, "candidates"),
                      (house_picks, "house_picks")):
        monkeypatch.setattr(mod, name, lambda *a, **k: [], raising=False)
    plan = content_plan(_lane_cfg(), [], closes_loader=None, root=tmp_path)

    lanes = plan["content"]["selection"]["filing_lanes"]
    assert "error" not in lanes, lanes
    assert lanes == {"congress": 0, "insider": 0, "house_picks": 0}


# ─────────────────────────────────────────────────────────────────────────────
# 12. One name, one post a night (E-wave review, m5)
# ─────────────────────────────────────────────────────────────────────────────

def test_the_filing_lanes_receive_the_tickers_the_plan_already_claimed(
        monkeypatch, tmp_path):
    """House picks got `exclude=` from day one; congress and insider did not.

    Without it a desk could carry a Prophet signal on NVDA, a congressional
    disclosure on NVDA and a Form 4 on NVDA in one evening — one name, three
    posts, from one account, which reads as a campaign rather than as three
    independent facts. The insider lane must also see what congress just took,
    since the two run back to back off one `_claimed` set.
    """
    from engine.marketing import congress_feed, house_picks, insider_feed
    from engine.marketing.content_studio import content_plan

    seen: dict[str, frozenset] = {}

    def _spy(kind, out):
        def _fn(*a, exclude=None, **k):
            seen[kind] = frozenset(exclude or ())
            return list(out)
        return _fn

    cand = {"ticker": "PLTR",
            "facts": {"facts": [{"text": "A member disclosed a PLTR purchase."}]}}
    monkeypatch.setattr(congress_feed, "candidates", _spy("congress", [dict(cand)]),
                        raising=False)
    monkeypatch.setattr(insider_feed, "candidates", _spy("insider", []), raising=False)
    monkeypatch.setattr(house_picks, "house_picks", lambda *a, **k: [], raising=False)

    plans = [{"id": "PLTR-BULL", "asset": "PLTR", "direction": "BULL",
              "entry": 120.0, "invalidation": 100.0, "targets": [150.0],
              "trigger": 125.0, "phase": "triggered_pre_t1",
              "recommended_action": "hold", "management_confidence": 66.0,
              "_signal_date": "2026-07-28"}]
    plan = content_plan(_lane_cfg(), plans, closes_loader=None, root=tmp_path)

    assert "congress" in seen and "insider" in seen, (
        "a filing feed was never called — the guard would be vacuous")
    assert "PLTR" in seen["congress"], (
        "the congress lane was not told which tickers the plan already claimed")
    assert "PLTR" in seen["insider"], (
        "the insider lane did not inherit the congress lane's claim")

    # And the belt: a claimed ticker never reaches a queue twice from this lane.
    filing = [q for a in plan["accounts"] for q in a["queue"]
              if q.get("provenance") in ("congress_desk", "insider_desk")]
    assert not [q for q in filing if q.get("ticker") == "PLTR"], (
        "a claimed ticker was posted a second time by a filing lane")


@pytest.mark.parametrize("module_name, loader, inner", [
    ("congress_feed", "load_congress", "new_disclosures"),
    ("insider_feed", "load_insiders", "open_market_purchases"),
])
def test_the_feeds_merge_exclude_into_their_blocklist(monkeypatch, module_name,
                                                      loader, inner):
    """Unit-level: `exclude` must actually FILTER, not merely be accepted.

    No pandas here on purpose — the inner selector is stubbed, so the loader may
    hand back any non-None sentinel and this runs on the thin CI lane.
    """
    import importlib

    mod = importlib.import_module(f"engine.marketing.{module_name}")
    calls: dict = {}

    def _spy(df, *, today, cfg, cooled):
        calls["cooled"] = frozenset(cooled or ())
        return []

    monkeypatch.setattr(mod, loader, lambda root: object(), raising=True)
    monkeypatch.setattr(mod, inner, _spy, raising=True)
    mod.candidates(None, today="2026-07-29", cfg={},
                   cooled={"AAA"}, exclude={"BBB"})

    assert calls["cooled"] == frozenset({"AAA", "BBB"}), calls


# ─────────────────────────────────────────────────────────────────────────────
# 8. B4 — the reporting lag is not model-writable
#
# `validate_copy` licenses bare one- and two-digit integers by design (ordinary
# copy counts things and the whitelist cannot carry every small integer the
# language needs). Every reporting lag is a bare one- or two-digit integer. So
# on the two lanes whose whole disclosure law is "state the gap honestly", the
# gap was the one number the model could write freely: "disclosed 6 days later"
# on a 47-day lag cleared every gate. `filing_fact_lock_violations` closes it by
# running the wire desk's gate 0.3 (`hot_tape_llm.numeric_violations`, imported,
# never forked) over the fact-bearing half of the writer payload.
# ─────────────────────────────────────────────────────────────────────────────

_CONGRESS_CAND = {
    "ticker": "NVDA", "representative": "Jane Q. Public", "title": "Rep.",
    "side": "purchase", "transaction_date": "2026-06-12",
    "report_date": "2026-07-29", "lag_days": 47,
    "amount_low": 50_001, "amount_high": 100_000, "amount_mid": 75_000,
}
_INSIDER_CAND = {
    "ticker": "RBKB", "insider_name": "Nancy Koskey Patzwahl",
    "role": "Chief Financial Officer", "shares": 25_000, "price": 11.94,
    "shares_following": 27_270, "prior_shares": 2_270,
    "purchase_value": 298_500.0, "trade_date": "2026-07-27",
    "file_date": "2026-07-28", "lag_days": 1, "ownership": "direct",
    "mechanism": "MATERIAL_ADDITION", "why_it_matters": "The stake multiplied.",
}


def _filing_payload(kind: str):
    """(payload, packet) for one filing item, built the production way.

    congress_facts -> build_context -> _v2_item_payload is exactly the chain
    content_studio runs before it calls the writer, so the packet this gate
    judges is the packet the model was shown.
    """
    from engine.marketing import copywriter as cw
    if kind == "congress":
        from engine.marketing.congress_feed import congress_facts
        packet = congress_facts(dict(_CONGRESS_CAND))
        item = {"type": "congress", "ticker": "NVDA", "account": "flagship"}
    else:
        from engine.marketing.insider_feed import insider_facts
        packet = insider_facts(dict(_INSIDER_CAND))
        item = {"type": "insider", "ticker": "RBKB", "account": "flagship"}
    ctx = cw.build_context(item, persona=None, facts=packet, extra=None)
    ctx["type"] = kind
    payload = cw._v2_item_payload(ctx, persona_card=None, codex_by_account={},
                                  memory_by_account={})
    return payload, packet


@pytest.mark.parametrize("kind, true_lag, fake_lag", [
    ("congress", "47", "6"),
    ("insider", "1", "9"),
])
def test_a_fabricated_reporting_lag_is_rejected(kind, true_lag, fake_lag):
    """The defect, stated as the test: swap the lag, keep everything else."""
    from engine.marketing import copywriter as cw

    payload, _packet = _filing_payload(kind)
    honest = (f"A filing, not a call.\n\nThe trade was disclosed {true_lag} "
              f"days after it happened.")
    faked = (f"A filing, not a call.\n\nThe trade was disclosed {fake_lag} "
             f"days after it happened.")

    assert cw.filing_fact_lock_violations(honest, payload, kind) == [], (
        "the TRUE lag must pass: a gate that rejects the packet's own number "
        "would drop every filing post and teach the next reader to widen it")
    hits = cw.filing_fact_lock_violations(faked, payload, kind)
    assert hits, f"a fabricated {kind} lag cleared the fact lock"
    assert any(fake_lag in h for h in hits), hits


@pytest.mark.parametrize("kind", ["congress", "insider"])
def test_validate_copy_v2_alone_does_not_catch_it(kind):
    """PINS THE REASON THIS GATE EXISTS. If a future edit makes the general
    numeric gate demand a licence for small bare integers, this test fails and
    the fact lock can be reconsidered. Until then it is load-bearing."""
    from engine.marketing import copywriter as cw

    payload, packet = _filing_payload(kind)
    ctx = {"type": kind, "account": "flagship", "shape": "two_part",
           "ticker": payload.get("cashtag", "").lstrip("$"),
           "numbers_whitelist": list(packet["numbers_whitelist"]),
           "top_facts": list(packet["facts"])[:3]}
    faked = "A filing, not a call.\n\nDisclosed 6 days after the trade."
    assert not [v for v in cw.validate_copy_v2(faked, ctx, headline="A filing, not a call.")
                if "6" in v], (
        "validate_copy_v2 now catches the bare lag integer on its own")


def test_the_fact_lock_is_scoped_to_the_filing_lanes():
    """Every OTHER kind keeps the bare-integer exemption. Applying gate 0.3 to
    the whole estate would reject ordinary counting language ("3 names", "2
    weeks") that no whitelist carries."""
    from engine.marketing import copywriter as cw

    payload, _ = _filing_payload("congress")
    text = "Watching 3 names into the close.\n\nTwo weeks of this pattern now."
    assert cw.filing_fact_lock_violations(text, payload, "signal") == []
    assert cw.filing_fact_lock_violations(text, payload, "chart") == []
    assert cw.FACT_LOCKED_KINDS == frozenset({"congress", "insider"})


def test_style_prose_never_licenses_a_filing_number():
    """The packet is the FACT half of the payload. A persona card that happens
    to say "1 in 4 posts" must not license a 4-day lag."""
    from engine.marketing import copywriter as cw

    payload, _ = _filing_payload("congress")
    payload["persona"] = {"voice": "at most 1 promise in 4 posts, 88 chars max"}
    payload["shape_contract"] = "headline 90 chars, body 275 chars"
    hits = cw.filing_fact_lock_violations(
        "A filing, not a call.\n\nDisclosed 88 days after the trade.",
        payload, "congress")
    assert hits, "a number from the STYLE block licensed a filing claim"


def test_the_fact_lock_fails_closed_when_it_cannot_run(monkeypatch):
    """A gate that cannot run must refuse the post, not pass it. Dropping a
    disclosure post costs one post; shipping an unchecked one costs a claim
    about a document somebody signed."""
    import builtins

    from engine.marketing import copywriter as cw

    payload, _ = _filing_payload("congress")
    real_import = builtins.__import__

    def _boom(name, *a, **k):
        if name == "engine.marketing.hot_tape_llm":
            raise ImportError("simulated thin-lane failure")
        return real_import(name, *a, **k)

    monkeypatch.setattr(builtins, "__import__", _boom)
    hits = cw.filing_fact_lock_violations(
        "A filing, not a call.\n\nDisclosed 47 days after the trade.",
        payload, "congress")
    assert hits and "unavailable" in hits[0], hits


def test_the_writer_drops_a_post_whose_lag_it_invented(monkeypatch):
    """END TO END through `write_posts_llm_v2`, the real production writer: a
    model that returns a fabricated lag twice (draft + repair) yields a DROP at
    the validate stage, not a post."""
    from engine import llm_auth
    from engine.marketing import copywriter as cw

    payload, packet = _filing_payload("congress")
    calls = {"n": 0}

    class _Client:
        class messages:
            @staticmethod
            def create(**kw):
                calls["n"] += 1
                raise AssertionError("unreachable: make_call is stubbed")

    monkeypatch.setenv("MARKETING_LLM_ENABLED", "1")
    monkeypatch.setattr(llm_auth, "build_providers",
                        lambda *a, **k: [{"name": "oauth", "client": _Client(),
                                          "model": "m", "env_var": "X", "cred": "x"}])

    def _make_call(providers, fn, context=""):
        calls["n"] += 1
        return ('{"text": "A filing, not a call.\\n\\nRep. Jane Q. Public bought '
                'NVDA. Disclosed 6 days after the trade."}'), None, "oauth"

    monkeypatch.setattr(llm_auth, "make_call", _make_call)

    from engine.marketing.congress_feed import congress_facts
    ctx = cw.build_context({"type": "congress", "ticker": "NVDA",
                            "account": "flagship"},
                           persona=None, facts=congress_facts(dict(_CONGRESS_CAND)),
                           extra=None)
    ctx["type"] = "congress"
    ctx["shape"] = "two_part"
    out = cw.write_posts_llm_v2([ctx], {"llm": {"enabled": True}})

    assert out and out[0].get("mode") == "dropped", out
    assert out[0].get("stage") == "validate", out[0]
    assert any("fact lock" in r for r in out[0].get("reasons") or []), out[0]
    assert calls["n"] >= 2, "the writer must have spent its one repair round first"
