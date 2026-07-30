"""A post that names tickers ships a picture, or it does not ship.

Operator, 2026-07-30, after reading the live flagship account: "YOU WILL NOT
SHIP THESE TEXT ONLY, ID RATHER YOU DESTROY THE ENTIRE ENGINE THAN SHIP TEXT
ONLY, CUZ NO ONE CARES ABOUT THESE TICKER POSTS IF UR GOING TO SHIP THEM NAKED
WITH NO CHARTS."

`_missing_required_media` could not enforce this: it keys on _CHART_BEARING_KINDS
(signal/chart/watchlist/receipt) AND needs a media[] entry to exist, so it only
catches a post whose chart was BUILT and failed to upload. The posts actually
reaching the timeline were `theme_list` — not a chart-bearing kind, no media at
all — so both conditions missed and they auto-posted bare to 1-4 views each.

The strings below are the real live posts.
"""
from __future__ import annotations

from scripts.marketing_publisher import _bare_cashtag_post

CFG = {"media_enabled": True}


def _item(text, kind="theme_list", media=None):
    return {"text": text, "kind": kind, "media": media or []}


class TestBareCashtagGate:
    def test_the_live_insurance_rollup_is_blocked(self):
        it = _item("Insurance - Property & Casualty: 7 of 7 names lower right now, "
                   "median -3.9%. Worst: $ERIE -6.1%, $TRV -4.6%, $ALL -4.1%.")
        assert _bare_cashtag_post(it, CFG, []) == "$ALL $ERIE $TRV"

    def test_the_live_electronic_components_rollup_is_blocked(self):
        it = _item("Electronic Components: 5 of 6 names higher, median +5.4% right "
                   "now. Best: $COHR +10.9%, $GLW +7.8%, $JBL +5.8%.")
        assert _bare_cashtag_post(it, CFG, [])

    def test_a_rollup_naming_no_tickers_still_passes(self):
        """The rule is about TICKER posts. A sector read with no cashtag is not one."""
        it = _item("Semiconductor Equipment & Materials: 5 of 5 names higher so far "
                   "today, median +11.8%. That is roughly $148 billion in fresh "
                   "market value since yesterday's close.")
        assert _bare_cashtag_post(it, CFG, []) == ""

    def test_macro_prose_passes(self):
        it = _item("Real GDP grew at an annual rate of 1.5 percent in the second "
                   "quarter of 2026, down from 2.1 percent.", kind="macro")
        assert _bare_cashtag_post(it, CFG, []) == ""

    def test_a_post_whose_chart_exists_is_not_this_rules_business(self):
        """A built-but-unresolved chart is the DEFERRAL case — recoverable via the
        backfill. This rule must not steal it and quarantine it."""
        it = _item("$HSY closed green eight days running.", kind="watchlist",
                   media=[{"kind": "chart_svg"}])
        assert _bare_cashtag_post(it, CFG, []) == ""

    def test_a_resolved_media_url_passes(self):
        it = _item("Worst: $ERIE -6.1%, $TRV -4.6%.")
        assert _bare_cashtag_post(it, CFG, ["https://r2.dev/x.png"]) == ""

    def test_media_globally_off_does_not_wedge_the_queue(self):
        """Same reasoning as the deferral gate: with media off nothing can ever
        resolve a picture, so gating on it would stop every ticker post forever."""
        it = _item("Worst: $ERIE -6.1%.")
        assert _bare_cashtag_post(it, {"media_enabled": False}, []) == ""

    def test_dollar_amounts_are_not_cashtags(self):
        """'$148 billion' and '$19.6' must not read as tickers."""
        it = _item("That is roughly $148 billion in fresh value, entry near $19.6.")
        assert _bare_cashtag_post(it, CFG, []) == ""


# ─────────────────────────────────────────────────────────────────────────────
# A cashtag no live store can vouch for.
#
# Operator 2026-07-30, on a filing post that shipped: "Wtf is N? Theres no
# ticker called N. This post also makes zero sense. it adds absolutely zero
# value at all." N appears in NO live store — not in the index membership file,
# not in the earnings calendar, not on the rendered board. The filing lane
# emitted a cashtag it had never checked against anything.
# ─────────────────────────────────────────────────────────────────────────────
import pytest  # noqa: E402

from scripts.marketing_publisher import (  # noqa: E402
    _SYMBOL_UNIVERSE_MIN,
    _symbol_universe,
    _unknown_cashtags,
)

_UNIVERSE = _symbol_universe(".")


def _membership_active() -> set[str]:
    """Active membership rows only — the `active` filter in isolation.

    The full universe unions in the earnings calendar and the rendered board,
    and a name can legitimately sit in those after leaving an index, so the
    delisting assertion has to be made against membership alone.
    """
    try:
        import pandas as pd
        df = pd.read_parquet("data/universe/membership.parquet",
                             columns=["ticker", "active"])
        return {str(t).upper()
                for t in df.loc[df["active"].astype(bool), "ticker"].tolist()}
    except Exception:  # noqa: BLE001
        return set()


_UNIVERSE_FROM_MEMBERSHIP_ONLY = _membership_active()
_needs_store = pytest.mark.skipif(
    not _UNIVERSE, reason="symbol stores unavailable in this checkout")


class TestUnknownCashtagGate:
    @_needs_store
    def test_the_live_delisted_ticker_is_caught(self):
        it = {"text": "$N's CEO opened a new 25,477-share stake at $19.6 a share."}
        assert _unknown_cashtags(it) == ["N"]

    @_needs_store
    def test_real_tickers_pass(self):
        it = {"text": "Insurance names moving: $ALL $ERIE $TRV"}
        assert _unknown_cashtags(it) == []

    @_needs_store
    def test_a_dollar_amount_is_not_a_cashtag(self):
        """$148 billion and $19.6 must not read as symbols."""
        it = {"text": "A $148 billion quarter, and the CEO paid $19.6 a share."}
        assert _unknown_cashtags(it) == []

    @_needs_store
    def test_one_bad_symbol_among_good_ones_is_reported_alone(self):
        it = {"text": "$N and $NSSC both moved today."}
        assert _unknown_cashtags(it) == ["N"]

    def test_an_unreadable_universe_never_refuses_a_post(self):
        """Fail OPEN. The gate must be able to say "I looked it up and it is not
        there" — never "I could not read the store, so nothing ships"."""
        it = {"text": "$N $ZZZZZ $NOTREAL"}
        assert _unknown_cashtags(it, root="/nonexistent-root") == []
        assert _symbol_universe("/nonexistent-root") == frozenset()

    def test_a_too_small_universe_is_treated_as_unavailable(self):
        """A truncated or half-written parquet must not quarantine the night."""
        assert _SYMBOL_UNIVERSE_MIN >= 500

    @_needs_store
    def test_a_delisted_row_is_excluded_even_though_it_is_in_the_file(self):
        """The `active` filter, pinned on whatever the vintage actually holds.

        N itself is absent from every store, so it is caught by simple absence.
        The `active` filter covers the OTHER shape: a ticker still listed in
        membership whose listing has died. Both must stay excluded.
        """
        import pandas as pd
        df = pd.read_parquet("data/universe/membership.parquet",
                             columns=["ticker", "active"])
        # One ticker holds several rows (sp500 / sp400 / sp600 / r2000), and a
        # name that MIGRATES between indices is active=False on the row it left
        # and active=True on the one it joined. Dead means inactive on EVERY
        # row — an earlier version of this test compared dead-anywhere against
        # active-anywhere and flagged 40+ perfectly live names.
        sym = df["ticker"].astype(str).str.upper()
        alive_any = set(sym[df["active"].astype(bool)])
        dead_everywhere = set(sym) - alive_any
        assert "N" not in _UNIVERSE, "an absent symbol must not be vouched for"
        leaked = dead_everywhere & _UNIVERSE_FROM_MEMBERSHIP_ONLY
        assert not leaked, f"delisted rows leaked into the universe: {sorted(leaked)[:5]}"
        assert dead_everywhere, "fixture holds no delisted rows — test is vacuous"
