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
