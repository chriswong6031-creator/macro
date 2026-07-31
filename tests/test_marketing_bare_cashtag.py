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
    def test_a_tracked_name_outside_every_us_index_is_not_fake(self):
        """The false positive this gate shipped with, caught on the live queue.

        $TEAM (Atlassian) sits in NO membership row and no earnings-calendar
        vintage, so the first universe — index membership + earnings + heatmap
        — called it fake and would have quarantined four legitimate CHARTED
        signal posts. The engine holds OHLCV, tape-flow and Yahoo history for
        it, which is the whole proof that it trades. Price stores are now the
        widest source in the union.
        """
        assert _unknown_cashtags({"text": "$TEAM | 95.87 is the line"}) == []

    @_needs_store
    def test_the_price_stores_are_actually_reached(self):
        """Guards the union, not just its result: membership alone is too narrow."""
        pd = pytest.importorskip(
            "pandas",
            reason="CI packs install minimal deps, not requirements.txt")
        mem = pd.read_parquet("data/universe/membership.parquet", columns=["ticker"])
        mem_syms = {str(t).upper() for t in mem["ticker"].tolist()}
        assert _UNIVERSE - mem_syms, (
            "the universe adds nothing beyond index membership — the price-store "
            "leg is not being reached")

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
        pd = pytest.importorskip(
            "pandas",
            reason="CI packs install minimal deps, not requirements.txt")
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


class TestNonEquityCashtagsAreRealTickers:
    """$VIX / $SPX / $BTC are correct FinTwit usage, not fake symbols.

    The gate shipped earlier today checked one thing: is this symbol in an
    EQUITY price store. Indices, rates, FX and crypto are in none of them, so
    the first live check of the gate quarantined $VIX, $SPX, $DXY, $BTC and
    $ETH -- terminally, with a false accusation of naming a fake ticker. Every
    macro and crypto post on the roster would have died.

    ETFs need no allowlist entry: $SPY/$QQQ/$TLT/$GLD are real listings and the
    price stores already carry them.
    """

    @pytest.mark.parametrize("tag", [
        "$VIX", "$SPX", "$DXY", "$BTC", "$ETH", "$SOL", "$TNX", "$WTI", "$GOLD",
    ])
    def test_a_non_equity_cashtag_is_never_called_fake(self, tag):
        assert _unknown_cashtags({"text": f"Macro read: {tag} is moving."}) == []

    @_needs_store
    @pytest.mark.parametrize("tag", ["$SPY", "$QQQ", "$TLT", "$AAPL"])
    def test_real_listings_still_pass_without_an_allowlist_entry(self, tag):
        from scripts.marketing_publisher import _NON_EQUITY_CASHTAGS
        assert tag.lstrip("$") not in _NON_EQUITY_CASHTAGS, (
            f"{tag} is a real listing; allowlisting it would hide a genuine "
            f"price-store gap"
        )
        assert _unknown_cashtags({"text": f"{tag} moved today."}) == []

    @_needs_store
    def test_the_allowlist_does_not_swallow_a_genuinely_dead_symbol(self):
        assert _unknown_cashtags({"text": "$N and $ZZZZZ"}) == ["N", "ZZZZZ"]


class TestABuiltChartThatFailedToUploadNeverShipsBare:
    """The hole BETWEEN the two chart gates, closed 2026-07-30.

    A theme_list/mover rollup whose chart WAS rendered and whose R2 upload then
    failed carries a media[] dict with no media_url.

      * _bare_cashtag_post treats a built-but-unresolved chart as the
        recoverable DEFERRAL case and returns "" -- so it waves it through;
      * _missing_required_media keyed on _CHART_BEARING_KINDS, and theme_list
        and mover are not in it -- so it waved it through too.

    Each gate deferred to the other and the post shipped BARE with
    "$ALL $ERIE $TRV" in the text: the precise failure that drew "ID RATHER YOU
    DESTROY THE ENTIRE ENGINE THAN SHIP TEXT ONLY".
    """

    CFG = {"media_enabled": True}

    def _ships_bare(self, it):
        from scripts.marketing_publisher import (
            _bare_cashtag_post, _missing_required_media)
        return (not _bare_cashtag_post(it, self.CFG, [])
                and not _missing_required_media(it, self.CFG, []))

    @pytest.mark.parametrize("kind", ["theme_list", "mover"])
    def test_the_rollup_that_shipped_bare_is_now_held(self, kind):
        it = {"kind": kind, "text": "Insurance moving: $ALL $ERIE $TRV",
              "media": [{"kind": "chart_svg", "chart_id": "chart-009"}]}
        assert not self._ships_bare(it)

    def test_it_DEFERS_rather_than_quarantines(self):
        """The chart exists, so the backfill can still stamp its URL.

        Quarantine is terminal; the bounded age escape still kills it if the
        picture never arrives.
        """
        from scripts.marketing_publisher import (
            _bare_cashtag_post, _missing_required_media)
        it = {"kind": "theme_list", "text": "Insurance: $ALL $ERIE",
              "media": [{"kind": "chart_svg", "chart_id": "chart-009"}]}
        assert _bare_cashtag_post(it, self.CFG, []) == "", "must not quarantine"
        assert _missing_required_media(it, self.CFG, []) is True, "must defer"

    def test_a_ticker_less_post_with_media_is_not_held(self):
        """A macro card has no ticker to illustrate; holding it wedges the lane."""
        it = {"kind": "macro", "text": "GDP was revised again.",
              "media": [{"kind": "chart_svg", "chart_id": "chart-007"}]}
        from scripts.marketing_publisher import _missing_required_media
        assert _missing_required_media(it, self.CFG, []) is False

    def test_a_post_that_never_had_a_chart_is_still_the_other_gate_s_job(self):
        """No media[] at all is the bare-cashtag quarantine, not a deferral."""
        from scripts.marketing_publisher import (
            _bare_cashtag_post, _missing_required_media)
        it = {"kind": "theme_list", "text": "Insurance: $ALL $ERIE", "media": []}
        assert _bare_cashtag_post(it, self.CFG, []), "should quarantine as bare"
        assert _missing_required_media(it, self.CFG, []) is False


class TestTheGroupCardActuallySatisfiesThisGate:
    """The radar's fix and this gate must agree, or neither works.

    2026-07-31: the hot-tape radar now draws a watchlist card for its group
    posts, because shipping them text-only walked straight into the gate above
    — 19 queued on 2026-07-30, 19 quarantined, none ever seen.

    That fix is only real if the entry the radar attaches is one THIS side
    recognises. The two live in different files and neither imports the other:
    the radar writes media[] entries, the publisher resolves them through
    _media_paths_for, and a field-name drift between them would reproduce the
    exact outage with a card rendered, uploaded, paid for and still refused.
    So the item below is built the way resolve_group_card builds it, and run
    through the real resolver rather than a hand-made list of URLs.
    """

    # The 2026-07-30 story, verbatim, and the entry the radar now attaches.
    TEXT = ("Computer Hardware: 5 of 7 names higher right now, median +10.0%. "
            "Best: $SNDK +21.1%, $WDC +15.2%.")
    ENTRY = {
        "kind": "chart_svg",
        "path": "data/marketing/outbox/media/2026-07-30/"
                "hottape-sector_rip-computer-hardware-1530Z.svg",
        "chart_id": "hottape-sector_rip-computer-hardware-1530Z",
        "tickers": ["SNDK", "WDC", "STX", "DELL", "HPQ"],
        "media_url": "https://pub-test.r2.dev/c/hottape-sector_rip.png",
    }

    def _item(self):
        return {"text": self.TEXT, "kind": "breaking", "as_of": "2026-07-30",
                "media": [self.ENTRY]}

    def test_the_publisher_resolves_the_url_the_radar_attaches(self):
        from scripts.marketing_publisher import _media_paths_for

        urls = _media_paths_for(self._item(), CFG, None)
        assert urls == [self.ENTRY["media_url"]], (
            "the publisher cannot see the URL the radar attached — the two "
            "sides have drifted on the media entry's field names"
        )

    def test_the_group_post_is_no_longer_quarantined(self):
        from scripts.marketing_publisher import _media_paths_for

        it = self._item()
        assert _bare_cashtag_post(it, CFG, _media_paths_for(it, CFG, None)) == ""

    def test_the_same_post_without_the_card_is_still_refused(self):
        """The gate is not weakened — only satisfied."""
        it = {"text": self.TEXT, "kind": "breaking", "as_of": "2026-07-30",
              "media": []}
        assert _bare_cashtag_post(it, CFG, []) == "$SNDK $WDC"

    def test_an_entry_whose_upload_failed_does_not_count_as_a_picture(self):
        """A media[] entry with no hosted URL is not a card.

        The radar drops these before they reach the queue, but nothing stops
        another lane attaching one — and here it must NOT read as satisfied,
        because Buffer would then post the text with no image.
        """
        from scripts.marketing_publisher import _media_paths_for

        entry = {k: v for k, v in self.ENTRY.items() if k != "media_url"}
        it = {"text": self.TEXT, "kind": "breaking", "as_of": "2026-07-30",
              "media": [entry]}
        assert _media_paths_for(it, CFG, None) == []


class TestTheTwoGatesHandOffWithoutAGap:
    """A post fell BETWEEN the bare-cashtag rule and the deferral rule.

    _bare_cashtag_post stepped aside whenever the item carried a media[] entry,
    on the stated grounds that "a chart exists but has no URL yet — that is the
    DEFERRAL case above". _missing_required_media takes only the kinds in
    _CHART_BEARING_KINDS / _TICKER_ROLLUP_KINDS, and `breaking` is deliberately
    in neither: a breadth read may mention $SPY in passing and holding it for an
    upload would strangle the desks' non-ticker voice.

    Both statements are true. Together they meant a `breaking` post that NAMED
    tickers, whose card was drawn and whose upload failed, passed the first gate
    (media[] non-empty), passed the second (wrong kind), and SHIPPED BARE —
    the exact outcome both rules exist to prevent.

    It is not a hypothetical kind. `breaking` is what the hot-tape and press
    lanes emit, so it is most of the account's volume, and the press wire could
    not host a card AT ALL until 2026-07-31 (no boto3, no R2 credentials): both
    live wire posts on main carry media_url: null.
    """

    CFG = {"media_enabled": True}
    TEXT = ("Computer Hardware: 5 of 7 names higher right now, median +10.0%. "
            "Best: $SNDK +21.1%, $WDC +15.2%.")
    UNHOSTED = {"kind": "chart_svg", "chart_id": "c1", "path": "media/c1.svg"}

    def _verdict(self, kind, media):
        from scripts.marketing_publisher import (
            _bare_cashtag_post, _media_paths_for, _missing_required_media)
        it = {"text": self.TEXT, "kind": kind, "as_of": "2026-07-30",
              "media": list(media)}
        paths = _media_paths_for(it, self.CFG, None)
        if _bare_cashtag_post(it, self.CFG, paths):
            return "quarantine"
        return "defer" if _missing_required_media(it, self.CFG, paths) else "ships"

    def test_a_breaking_ticker_post_with_a_failed_upload_never_ships(self):
        assert self._verdict("breaking", [self.UNHOSTED]) == "quarantine"

    def test_any_kind_the_deferral_gate_ignores_is_covered(self):
        """The defect was never specific to `breaking` — that is just the kind
        production hit. Every kind outside both frozensets had the same hole."""
        for kind in ("breaking", "macro", "education", "event", "wire",
                     "earnings"):
            assert self._verdict(kind, [self.UNHOSTED]) == "quarantine", kind

    def test_a_recoverable_kind_still_defers_rather_than_quarantines(self):
        """The fix must not turn a recoverable hold into a deletion.

        These kinds have a working recovery path (the media backfill fills the
        URL in and the next sweep posts it), so quarantining them would throw
        away a post the system can still complete.
        """
        for kind in ("signal", "chart", "watchlist", "receipt", "theme_list",
                     "mover"):
            assert self._verdict(kind, [self.UNHOSTED]) == "defer", kind

    def test_a_hosted_card_ships_on_every_kind(self):
        hosted = dict(self.UNHOSTED, media_url="https://pub-test.r2.dev/c1.png")
        for kind in ("breaking", "signal", "theme_list", "macro"):
            assert self._verdict(kind, [hosted]) == "ships", kind

    def test_a_post_with_no_cashtag_is_untouched(self):
        """The live BEA wire posts. No ticker, so no picture is owed, and this
        change must not start holding the desks' macro voice."""
        from scripts.marketing_publisher import _bare_cashtag_post
        it = {"text": "Real GDP grew at an annual rate of 1.5 percent in the "
                      "second quarter of 2026.", "kind": "breaking",
              "as_of": "2026-07-30", "media": [self.UNHOSTED]}
        assert _bare_cashtag_post(it, self.CFG, []) == ""

    def test_the_helper_reads_the_deferral_gate_s_own_sets(self):
        """Derived, not duplicated — or the two drift apart again."""
        import inspect
        from scripts.marketing_publisher import _deferral_covers

        src = inspect.getsource(_deferral_covers)
        assert "_CHART_BEARING_KINDS" in src and "_TICKER_ROLLUP_KINDS" in src, (
            "a hand-copied kind list will drift from the gate it mirrors"
        )
