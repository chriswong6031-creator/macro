"""The US macro reaction basket — engine/marketing/tape_stamp.reaction_basket.

WHAT THIS PINS. Measured on `data/marketing/outbox/items.jsonl`, all 83
`kind=breaking` rows since 2026-08-03T14:39Z shipped `source.tape_stamp == ""`;
replaying the module over them returned `no_mapping` 79 times, because the entity
map needs a headline to NAME an instrument and a macro print names a statistic.
`config/marketing.yml wire_routing.classes` keeps macro_print on the brand
account on the grounds that "the half our readers come for is what it does to
the path" — so the empty stamp was the missing half of every one of those posts.

Every test below pins a way this could ship WRONG rather than merely absent:
yield units (the one that would print a false number), the honesty gate on
economy, fail-closed on an unscored item, and additivity for every other class.

Import closure matters here: tape_stamp is stdlib-only on purpose so the thin
marketing CI pack stays green. This module imports nothing heavier.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from engine.marketing.tape_stamp import (
    compute_stamp,
    reaction_basket,
    shorten_stamp,
    stamp_clause,
)

NOW = datetime(2026, 8, 5, 14, 45, tzinfo=timezone.utc)


def _ts(now: datetime = NOW, *, age_s: int = 60) -> int:
    return int((now - timedelta(seconds=age_s)).timestamp() * 1000)


def _store(now: datetime = NOW, **overrides) -> dict:
    """A live-plane-shaped store with all three basket legs clearly moving."""
    quotes = {
        # +0.9 % clears the 0.5 % floor.
        "ES=F": {"ts": _ts(now), "changePct": 0.9, "price": 7800.0,
                 "prevClose": 7730.4},
        # 4.686 -> 4.746 is +6.0 bp, clearing the 4 bp floor.
        "^TNX": {"ts": _ts(now), "price": 4.746, "prevClose": 4.686,
                 "changePct": 1.28},
        # -0.30 % clears the 0.17 % floor.
        "DX-Y.NYB": {"ts": _ts(now), "changePct": -0.30, "price": 99.5,
                     "prevClose": 99.8},
    }
    quotes.update(overrides)
    return {"ts": _ts(now), "quotes": quotes}


def _print_item(**over) -> dict:
    item = {"headline": "US ISM Manufacturing PMI for July 55.6 versus 54.0 estimate",
            "body_snippet": "", "event_class": "macro_print",
            "macro_economy": "us", "matched": {}}
    item.update(over)
    return item


# ─────────────────────────────────────────────────────────────────────────────
# The defect itself: a macro print now earns a read
# ─────────────────────────────────────────────────────────────────────────────

def test_a_us_macro_print_that_names_no_instrument_now_earns_a_stamp():
    """The exact live headline that returned no_mapping for every one of 83 posts."""
    res = compute_stamp(_print_item(), _store(), now=NOW)
    assert res["stamp"] == (
        "S&P futures +0.9% · the 10-year +6bp · the dollar index -0.3%"
    )
    assert res["reason"] == "basket"


@pytest.mark.parametrize("headline", [
    "JOLTs job openings 7.359M vs 7.400M estimate. Lower than last month.",
    "US June factory orders -0.3% vs +0.2% expected",
    "US International Trade balance for June -$73.3B vs -$73.0B estimate",
    "Redbook Retail Sales Index Up 8.7% YoY For Week Ended 8/1/26",
])
def test_the_real_headlines_that_measured_no_mapping_all_earn_one(headline):
    """Verbatim from the outbox — the population this exists for."""
    assert stamp_clause(_print_item(headline=headline), _store(), now=NOW)


# ─────────────────────────────────────────────────────────────────────────────
# YIELD UNITS — the leg that could ship a FALSE number rather than none
# ─────────────────────────────────────────────────────────────────────────────

def test_the_ten_year_is_quoted_in_bp_never_as_percent_of_a_percent():
    """^TNX carries changePct = a percent OF a percent. Printing it is wrong.

    Live store 2026-08-05: price 4.627, prevClose 4.686, changePct -1.26. The
    yield moved -5.9 bp. A leg rendered off changePct would read "the 10-year
    -1.3%", which a reader parses as a 1.3 % yield or a bond-price move --
    neither happened. This is the one failure mode where the basket would ship a
    number that is not true, so it gets its own pin.
    """
    store = _store(**{"^TNX": {"ts": _ts(), "price": 4.627, "prevClose": 4.686,
                               "changePct": -1.26}})
    res = reaction_basket(_print_item(), store, now=NOW)

    assert "the 10-year -6bp" in res["stamp"]
    assert "-1.3%" not in res["stamp"]
    assert "-1.26" not in res["stamp"]
    leg = next(x for x in res["legs"] if x["symbol"] == "^TNX")
    assert leg["units"] == "bp"
    assert leg["move"] == pytest.approx(-5.9, abs=0.05)


@pytest.mark.parametrize("quote", [
    pytest.param({"ts": _ts(), "price": 4.627, "changePct": -1.26}, id="absent"),
    pytest.param({"ts": _ts(), "price": 4.627, "prevClose": 0.0}, id="zero"),
    pytest.param({"ts": _ts(), "price": 4.627, "prevClose": None}, id="null"),
])
def test_a_yield_leg_with_no_usable_prevclose_is_dropped_not_zeroed(quote):
    """An unknown base is not a zero move -- fail closed rather than mint 0bp.

    A zero prevClose is the one that would not raise: (4.627 - 0) * 100 is a
    tidy "+463bp", a number that is arithmetic on a placeholder rather than a
    reading of the tape.
    """
    store = _store(**{"^TNX": quote})
    res = reaction_basket(_print_item(), store, now=NOW)
    assert "10-year" not in res["stamp"]
    assert "S&P futures" in res["stamp"]  # the other legs still ship


# ─────────────────────────────────────────────────────────────────────────────
# THE HONESTY GATE — real numbers with a fabricated link is the failure mode
# ─────────────────────────────────────────────────────────────────────────────

def test_a_foreign_print_gets_no_us_tape_basket():
    """Every leg is a US instrument.

    Hanging "S&P futures +0.9%" off "Canada June trade balance +3.86B" would
    present an unrelated US session move as that print's reading -- real numbers,
    fabricated link, which is precisely what the module's "we never fabricate a
    reaction" law exists to stop.
    """
    item = _print_item(
        headline="Canada June trade balance +3.86B vs +3.0B expected",
        macro_economy="foreign")
    res = reaction_basket(item, _store(), now=NOW)
    assert res["stamp"] == ""
    assert res["reason"] == "no_basket"


def test_an_item_scored_before_macro_economy_existed_gets_no_basket():
    """FAIL-CLOSED on an absent field.

    The field is stamped by breaking_relevance.score_item. An item that predates
    it carries no key at all, and an absent economy must read as "not proven US",
    never as the default -- otherwise every foreign print inherits the US tape
    the moment one upstream field goes missing.
    """
    item = _print_item()
    del item["macro_economy"]
    assert reaction_basket(item, _store(), now=NOW)["reason"] == "no_basket"


@pytest.mark.parametrize("event_class",
                         ["company_news", "geopolitical", "policy", "earnings", "none"])
def test_no_other_class_inherits_the_basket(event_class):
    """Scoped to one class on purpose; `policy` is a follow-up, not an oversight."""
    item = _print_item(event_class=event_class)
    assert reaction_basket(item, _store(), now=NOW)["reason"] == "no_basket"


# ─────────────────────────────────────────────────────────────────────────────
# PER-LEG GATING — a quiet or stale leg drops out, the rest still ship
# ─────────────────────────────────────────────────────────────────────────────

def test_a_leg_below_its_own_floor_drops_out_and_the_others_ship():
    store = _store(**{"ES=F": {"ts": _ts(), "changePct": 0.05}})
    stamp = reaction_basket(_print_item(), store, now=NOW)["stamp"]
    assert "S&P futures" not in stamp
    assert "the 10-year +6bp" in stamp and "the dollar index" in stamp


def test_an_overnight_stale_yield_drops_out_rather_than_claiming_a_rates_move():
    """The yield indexes only tick in the US session.

    ^TNX carried delayMin 826 at 04:46 ET on 2026-08-05, so a pre-open print
    must read on futures and the dollar and simply not claim a rates move it
    cannot see.
    """
    store = _store(**{"^TNX": {"ts": _ts(age_s=826 * 60), "price": 4.746,
                               "prevClose": 4.686}})
    stamp = reaction_basket(_print_item(), store, now=NOW)["stamp"]
    assert "10-year" not in stamp
    assert "S&P futures +0.9%" in stamp


def test_a_wholly_quiet_tape_is_honestly_silent():
    """No placeholder, no "flat" -- the same silence a quiet tape always gave."""
    store = _store(
        **{"ES=F": {"ts": _ts(), "changePct": 0.05},
           "^TNX": {"ts": _ts(), "price": 4.687, "prevClose": 4.686},
           "DX-Y.NYB": {"ts": _ts(), "changePct": 0.01}})
    res = reaction_basket(_print_item(), store, now=NOW)
    assert res["stamp"] == ""
    assert res["reason"] == "basket_quiet_or_stale"


def test_a_future_dated_quote_is_rejected_by_the_basket_too():
    """The m3 clock-skew clamp is per-leg, not only on the entity path."""
    store = _store(**{"ES=F": {"ts": _ts(age_s=-3600), "changePct": 0.9}})
    stamp = reaction_basket(_print_item(), store, now=NOW)["stamp"]
    assert "S&P futures" not in stamp


# ─────────────────────────────────────────────────────────────────────────────
# ADDITIVITY — the basket may only ADD a stamp, never change or remove one
# ─────────────────────────────────────────────────────────────────────────────

def test_a_company_item_keeps_the_entity_map_stamp_unchanged():
    store = _store(**{"CL=F": {"ts": _ts(), "changePct": -2.3}})
    item = {"headline": "Chevron CEO on the crude oil outlook", "body_snippet": "",
            "event_class": "company_news", "matched": {}}
    res = compute_stamp(item, store, now=NOW)
    assert res["stamp"] == "WTI -2.3%"
    assert res["reason"] == "moved"


def test_a_us_print_falls_back_to_the_entity_map_when_the_basket_is_silent():
    """Basket first, entity map second -- so nothing that stamps today stops."""
    store = _store(
        **{"ES=F": {"ts": _ts(), "changePct": 0.05},
           "^TNX": {"ts": _ts(), "price": 4.687, "prevClose": 4.686},
           "DX-Y.NYB": {"ts": _ts(), "changePct": 0.01},
           "GC=F": {"ts": _ts(), "changePct": 1.9}})
    item = _print_item(headline="Gold jumped above 4,000 after the payrolls print")
    res = compute_stamp(item, store, now=NOW)
    assert res["stamp"] == "Gold +1.9%"
    assert res["reason"] == "moved"


def test_the_basket_wins_over_an_incidental_entity_match_on_a_us_print():
    """ORDER, pinned where it is actually decidable.

    "Gold jumped above 4,000..." is a US macro print that also happens to say
    "gold". With both paths live the BASKET is the read -- the whole point is
    that a macro print's reaction is the path, not whichever noun the wire
    editor happened to put in the headline. With the two calls in the other
    order this returns "Gold +1.9%" and the test goes red.
    """
    store = _store(**{"GC=F": {"ts": _ts(), "changePct": 1.9}})
    item = _print_item(headline="Gold jumped above 4,000 after the payrolls print")
    res = compute_stamp(item, store, now=NOW)
    assert res["reason"] == "basket"
    assert res["stamp"].startswith("S&P futures +0.9%")
    assert "Gold" not in res["stamp"]


def test_the_basket_can_be_switched_off_and_the_module_reverts_exactly():
    cfg = {"reaction": {"enabled": False}}
    assert compute_stamp(_print_item(), _store(), now=NOW, cfg=cfg)["reason"] == "no_mapping"


# ─────────────────────────────────────────────────────────────────────────────
# The length-budget ladder
# ─────────────────────────────────────────────────────────────────────────────

def test_shorten_stamp_sheds_legs_from_the_tail():
    full = "S&P futures +0.9% · the 10-year +6bp · the dollar index -0.3%"
    assert shorten_stamp(full, 3) == full
    assert shorten_stamp(full, 2) == "S&P futures +0.9% · the 10-year +6bp"
    assert shorten_stamp(full, 1) == "S&P futures +0.9%"
    assert shorten_stamp(full, 0) == ""
    assert shorten_stamp("", 2) == ""


def test_the_stamp_stays_well_inside_the_flash_budget():
    """Backtested max over 742 sessions was 62 chars against a 280-char budget."""
    stamp = reaction_basket(_print_item(), _store(), now=NOW)["stamp"]
    assert len(stamp) <= 80


def test_an_over_budget_post_sheds_a_leg_instead_of_the_whole_read():
    """press_lane's ladder used to go opener -> DECLINE, and decline returns tape="".

    So the one post whose value IS the tape read was also the post that shipped
    without it the moment the summary ran long. The new rung sheds legs from the
    tail first: a two-leg read is still a read.

    Driven through the real `_apply_wire_voice` rather than a re-implementation,
    with a summary sized so the three-leg stamp overflows the flash budget and a
    shorter one does not.
    """
    from engine.marketing.press_lane import _apply_wire_voice

    full = "S&P futures +0.9% · the 10-year +6bp · the dollar index -0.3%"
    summary = "US ISM manufacturing came in at 55.6 against a 54.0 estimate. " + (
        "The survey covers new orders, production and employment across the sector. "
        "Respondents flagged input costs and delivery times in the month. ")
    fmt_cfg = {"flash_max_chars": 280, "flash_max_sentences": 4}

    body, _register, opener, _fmt, tape, applied = _apply_wire_voice(
        _print_item(), summary, "wire reports",
        account="flagship", recent_openers={},
        quotes_store=_store(), fmt="flash",
        voice_cfg={}, format_cfg=fmt_cfg,
        tape_cfg={"quote_store_paths": []}, now=NOW,
    )

    assert applied, "the voice pass declined instead of shedding a leg"
    assert tape, "the tape read was thrown away to save characters"
    assert tape != full, "this case is only meaningful when the full stamp overflows"
    assert tape == "S&P futures +0.9%" or tape.startswith("S&P futures +0.9% · ")
    assert body.endswith(f" · {tape}")
    assert len(body) <= fmt_cfg["flash_max_chars"]
    assert opener == ""


# ─────────────────────────────────────────────────────────────────────────────
# Copy law: the clause states what the tape DID, never a stance or a cause
# ─────────────────────────────────────────────────────────────────────────────

def test_the_clause_carries_no_stance_or_causal_vocabulary():
    """breaking_summary._STANCE_BANNED plus the causal words a relay may not use.

    The wire is a RELAY (charter §4). A measured co-timed reading is legal; "on
    the print", "after the data", "because" would all assert a link we did not
    measure.
    """
    from engine.marketing.breaking_summary import _STANCE_BANNED

    stamp = reaction_basket(_print_item(), _store(), now=NOW)["stamp"].lower()
    for word in _STANCE_BANNED:
        assert word not in stamp, f"stance word {word!r} reached the tape clause"
    for causal in ("on the print", "after the", "because", "on the headline",
                   "in response", "driven by", "sparked", "triggered"):
        assert causal not in stamp
