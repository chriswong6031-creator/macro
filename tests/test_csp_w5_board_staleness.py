"""tests/test_csp_w5_board_staleness.py — CSP-W5 board staleness + pending-buy expiry.

Tests the three helpers added by CSP-W5:
  - _compute_board_staleness: fresh/stale/weekend calendar-aware check
  - _expire_pending_buys:     pending fresh vs pending expired vs confirmed (take)
  - check_surface_freshness:  us_standouts.json now in _ARTIFACTS

US-only.  CN/HK/CA parity is explicitly out of scope (noted in PR body).
"""
from __future__ import annotations

import json
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import pandas as pd
import pytest

# ---------------------------------------------------------------------------
# Import the helpers under test
# ---------------------------------------------------------------------------
from scripts.build_stock_library import (
    _compute_board_staleness,
    _count_trading_sessions_between,
    _expire_pending_buys,
    _panel_price_reach,
)
import scripts.check_surface_freshness as freshness_mod
from scripts.check_surface_freshness import _ARTIFACTS


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def _make_ohlcv_store(tmp_path: Path, ticker_dates: dict[str, date]) -> Path:
    """Build a minimal data/baskets/ohlcv structure with one parquet per ticker."""
    ohlcv_dir = tmp_path / "baskets" / "ohlcv"
    ohlcv_dir.mkdir(parents=True)
    for ticker, last_date in ticker_dates.items():
        idx = pd.date_range(end=last_date, periods=5, freq="B")
        df = pd.DataFrame({"close": [100.0] * 5}, index=idx)
        df.to_parquet(str(ohlcv_dir / f"{ticker}.parquet"))
    return ohlcv_dir


def _make_pending_row(ticker: str, fire_date: str, tier_cascade: str = "T1") -> dict:
    """Minimal buy row with a pending anticipation signal."""
    return {
        "ticker": ticker,
        "name": ticker,
        "lane": "trend",
        "signal": {
            "tier": "anticipation",
            "sub": "pending",
            "last": {
                "type": "buy",
                "quality": "pending",
                "date": fire_date,
            },
        },
    }


def _make_take_row(ticker: str, take_date: str) -> dict:
    """Minimal buy row with a confirmed take signal."""
    return {
        "ticker": ticker,
        "name": ticker,
        "lane": "trend",
        "signal": {
            "tier": "take",
            "sub": None,
            "last": {
                "type": "buy",
                "quality": "take",
                "date": take_date,
            },
        },
    }


# ---------------------------------------------------------------------------
# _count_trading_sessions_between
# ---------------------------------------------------------------------------

class TestCountTradingSessions:
    def test_same_day_is_zero(self):
        d = date(2026, 7, 15)  # Wednesday — a session day
        assert _count_trading_sessions_between(d, d) == 0

    def test_one_day_later_session(self):
        # 2026-07-15 (Wed) to 2026-07-16 (Thu): 1 session
        assert _count_trading_sessions_between(date(2026, 7, 15), date(2026, 7, 16)) == 1

    def test_crosses_weekend(self):
        # 2026-07-10 (Fri) to 2026-07-13 (Mon): weekend between → 1 session (Mon)
        assert _count_trading_sessions_between(date(2026, 7, 10), date(2026, 7, 13)) == 1

    def test_crosses_long_weekend(self):
        # 2026-07-03 (Fri) to 2026-07-07 (Tue): July 4th holiday (Sat, observed Fri)
        # 2026-07-04 is a Saturday → observed on 2026-07-03 (Fri) is a holiday
        # Sessions strictly after 07-03 through 07-07:
        #   07-04 Sat: weekend
        #   07-05 Sun: weekend
        #   07-06 Mon: session
        #   07-07 Tue: session
        # = 2 sessions
        assert _count_trading_sessions_between(date(2026, 7, 3), date(2026, 7, 7)) == 2

    def test_week_span(self):
        # 2026-07-07 (Tue) to 2026-07-15 (Wed): 6 sessions
        # 07-08 Wed, 07-09 Thu, 07-10 Fri, 07-13 Mon, 07-14 Tue, 07-15 Wed = 6
        assert _count_trading_sessions_between(date(2026, 7, 7), date(2026, 7, 15)) == 6


# ---------------------------------------------------------------------------
# _compute_board_staleness
# ---------------------------------------------------------------------------

class TestComputeBoardStaleness:
    """Calendar-pinned so expected_last_session == 2026-07-16.

    Reference time: 03:00 UTC on 2026-07-17 (Thursday).  At 03:00 UTC the ET
    clock reads 23:00 on 2026-07-16 — after midnight, so 2026-07-17 is the new
    ET calendar day, but the 17:00 ET settle window has NOT been crossed for the
    2026-07-17 session yet, so expected_last_session returns 2026-07-16.

    Verified: lib.nyse_calendar.expected_last_session(datetime(2026,7,17,3,0,utc))
              == date(2026,7,16).
    """

    # 03:00 UTC July 17 → expected session = 2026-07-16 (confirmed above)
    _NOW = datetime(2026, 7, 17, 3, 0, tzinfo=timezone.utc)
    _EXPECTED_SESSION = date(2026, 7, 16)

    @staticmethod
    def _panel(through: str, majority: str | None = None, at_through: int = 1,
               total: int = 1) -> dict:
        maj = majority or through
        return {"through": through, "majority_through": maj,
                "members_at_through": at_through, "members_total": total,
                "mixed_vintage": maj != through}

    def test_fresh_board(self, tmp_path):
        """Cross-section priced through 2026-07-16 (the expected session): not delayed."""
        ohlcv_dir = _make_ohlcv_store(tmp_path, {"AAPL": date(2026, 7, 16)})
        result = _compute_board_staleness(ohlcv_dir=ohlcv_dir, now=self._NOW,
                                          panel_reach=self._panel("2026-07-16"),
                                          board_asof="2026-07-16")
        assert result["price_through"] == "2026-07-16"
        assert result["age_days"] == 0
        assert result["sessions_behind"] == 0
        assert result["delayed"] is False
        assert result["unknown"] is False

    def test_one_session_behind(self, tmp_path):
        """Priced through 2026-07-15 (1 session behind 07-15→07-16):
        NOT delayed (threshold = 2)."""
        ohlcv_dir = _make_ohlcv_store(tmp_path, {"AAPL": date(2026, 7, 15)})
        result = _compute_board_staleness(ohlcv_dir=ohlcv_dir, now=self._NOW,
                                          panel_reach=self._panel("2026-07-15"),
                                          board_asof="2026-07-15")
        assert result["price_through"] == "2026-07-15"
        assert result["sessions_behind"] == 1
        assert result["delayed"] is False

    def test_two_sessions_behind_is_delayed(self, tmp_path):
        """Priced through 2026-07-14 (2 sessions behind: 07-14→07-15, 07-15→07-16):
        delayed = True."""
        ohlcv_dir = _make_ohlcv_store(tmp_path, {"AAPL": date(2026, 7, 14)})
        result = _compute_board_staleness(ohlcv_dir=ohlcv_dir, now=self._NOW,
                                          panel_reach=self._panel("2026-07-14"),
                                          board_asof="2026-07-14")
        assert result["price_through"] == "2026-07-14"
        assert result["sessions_behind"] == 2
        assert result["delayed"] is True

    def test_basis_is_the_older_of_majority_and_board_asof(self, tmp_path):
        """Fail closed on disagreement — in BOTH directions."""
        ohlcv_dir = _make_ohlcv_store(tmp_path, {"AAPL": date(2026, 7, 16)})
        stale_panel = _compute_board_staleness(
            ohlcv_dir=ohlcv_dir, now=self._NOW,
            panel_reach=self._panel("2026-07-14"), board_asof="2026-07-16")
        assert stale_panel["price_through"] == "2026-07-14"
        assert stale_panel["basis"] == "panel_majority"
        assert stale_panel["delayed"] is True

        stale_asof = _compute_board_staleness(
            ohlcv_dir=ohlcv_dir, now=self._NOW,
            panel_reach=self._panel("2026-07-16"), board_asof="2026-07-14")
        assert stale_asof["price_through"] == "2026-07-14"
        assert stale_asof["basis"] == "board_asof"
        assert stale_asof["delayed"] is True

    def test_max_over_members_never_clears_the_badge(self, tmp_path):
        """G0.2 — the 2026-08-06 fail-open, reproduced from the committed artifact.

        us_standouts.json that night: ``as_of 2026-07-31`` beside ``staleness
        {price_through: 2026-08-06, age_days: 0, delayed: false}`` with
        ``panel.majority_through 2026-07-31`` and 423 of 3,028 members reaching 08-06.
        The board self-reported FRESH at maximum staleness because the basis was a
        max() over member reach.  A minority of members advancing is not the board
        advancing, and this shape must be impossible by construction.
        """
        ohlcv_dir = _make_ohlcv_store(tmp_path, {"AAPL": date(2026, 7, 16)})
        result = _compute_board_staleness(
            ohlcv_dir=ohlcv_dir, now=self._NOW,
            panel_reach=self._panel("2026-07-16", majority="2026-07-14",
                                    at_through=423, total=3028),
            board_asof="2026-07-14")
        assert result["delayed"] is True, "a minority reaching the expected session cleared the badge"
        assert result["price_through"] == "2026-07-14"
        # the old (lying) number is kept as disclosure, not as the answer
        assert result["max_through"] == "2026-07-16"
        assert result["inputs"]["panel"]["mixed_vintage"] is True

    def test_no_basis_fails_closed(self, tmp_path):
        """A readable ohlcv store is NOT a basis: it is a side store, and its max is
        the same one-member-clears-it quantity.  With no panel majority and no board
        as_of there is nothing to date the board with — which is a delayed board."""
        ohlcv_dir = _make_ohlcv_store(tmp_path, {"AAPL": date(2026, 7, 16)})
        result = _compute_board_staleness(ohlcv_dir=ohlcv_dir, now=self._NOW)
        assert result["price_through"] is None
        assert result["age_days"] is None
        assert result["delayed"] is True
        assert result["unknown"] is True
        assert result["basis"] == "unknown"

    def test_missing_directory_fails_closed(self, tmp_path):
        """Non-existent directory and no other input: delayed, not silently fresh."""
        result = _compute_board_staleness(ohlcv_dir=tmp_path / "nonexistent", now=self._NOW)
        assert result["price_through"] is None
        assert result["age_days"] is None
        assert result["delayed"] is True
        assert result["unknown"] is True

    def test_empty_directory_fails_closed(self, tmp_path):
        """Empty directory (no parquets) and no other input: delayed."""
        empty = tmp_path / "empty"
        empty.mkdir()
        result = _compute_board_staleness(ohlcv_dir=empty, now=self._NOW)
        assert result["price_through"] is None
        assert result["delayed"] is True

    def test_weekend_reference_uses_prior_session(self, tmp_path):
        """Reference on Saturday 2026-07-18: expected session = 2026-07-17 (Fri).
        Priced through that Friday = not delayed."""
        # 2026-07-18 is Saturday; expected_last_session returns 2026-07-17 (Fri)
        now_sat = datetime(2026, 7, 18, 14, 0, tzinfo=timezone.utc)  # 14:00 UTC Saturday
        ohlcv_dir = _make_ohlcv_store(tmp_path, {"SPY": date(2026, 7, 17)})
        result = _compute_board_staleness(ohlcv_dir=ohlcv_dir, now=now_sat,
                                          panel_reach=self._panel("2026-07-17"),
                                          board_asof="2026-07-17")
        assert result["price_through"] == "2026-07-17"
        assert result["delayed"] is False


class TestStalenessDisclosureBlock:
    """The block still carries every input's reach — as DISCLOSURE, never as the basis.

    2026-08-03→05 regression this disclosure was built for: the ohlcv scan sat at 07-31
    while --heal lanes ranked yahoo closes through 08-03/04, and 22 consecutive builds
    claimed identical reach while the buy lane swung 55↔76 names.  Publishing every
    input's reach is right; ANSWERING "how fresh is this board" with the max over them
    is what 2026-08-06 disproved.
    """

    _NOW = TestComputeBoardStaleness._NOW  # expected session = 2026-07-16
    _panel = staticmethod(TestComputeBoardStaleness._panel)

    def test_ohlcv_scan_is_disclosure_only(self, tmp_path):
        """A fresh side store cannot clear a badge the cross-section has not earned."""
        ohlcv_dir = _make_ohlcv_store(tmp_path, {"AAPL": date(2026, 7, 16)})
        result = _compute_board_staleness(ohlcv_dir=ohlcv_dir, now=self._NOW,
                                          panel_reach=self._panel("2026-07-14"),
                                          board_asof="2026-07-14")
        assert result["price_through"] == "2026-07-14"
        assert result["delayed"] is True
        assert result["inputs"]["baskets_ohlcv_through"] == "2026-07-16"
        assert result["max_through"] == "2026-07-16"

    def test_missing_store_with_panel_still_dates_the_board(self, tmp_path):
        """Absent ohlcv store never suppresses the badge when the panel reach is
        known — the board WAS priced from something."""
        result = _compute_board_staleness(
            ohlcv_dir=tmp_path / "nonexistent", now=self._NOW,
            panel_reach=self._panel("2026-07-15"), board_asof="2026-07-15")
        assert result["price_through"] == "2026-07-15"
        assert result["delayed"] is False
        assert result["inputs"]["baskets_ohlcv_through"] is None

    def test_malformed_panel_date_falls_back_to_board_asof(self, tmp_path):
        """A garbage panel date never breaks the badge — and never invents freshness."""
        ohlcv_dir = _make_ohlcv_store(tmp_path, {"AAPL": date(2026, 7, 16)})
        result = _compute_board_staleness(
            ohlcv_dir=ohlcv_dir, now=self._NOW,
            panel_reach={"through": "not-a-date", "majority_through": "not-a-date"},
            board_asof="2026-07-16")
        assert result["price_through"] == "2026-07-16"
        assert result["basis"] == "board_asof"

    def test_malformed_panel_and_no_asof_fails_closed(self, tmp_path):
        result = _compute_board_staleness(ohlcv_dir=tmp_path / "nonexistent",
                                          now=self._NOW,
                                          panel_reach={"through": "not-a-date"})
        assert result["price_through"] is None
        assert result["delayed"] is True
        assert result["unknown"] is True

    def test_no_panel_keeps_inputs_block(self, tmp_path):
        """Without panel_reach the result still carries the disclosure block
        (panel None) so consumers get a stable shape."""
        ohlcv_dir = _make_ohlcv_store(tmp_path, {"AAPL": date(2026, 7, 16)})
        result = _compute_board_staleness(ohlcv_dir=ohlcv_dir, now=self._NOW,
                                          board_asof="2026-07-16")
        assert result["inputs"]["panel"] is None
        assert result["inputs"]["baskets_ohlcv_through"] == "2026-07-16"
        assert result["inputs"]["board_asof"] == "2026-07-16"

    def test_unknown_block_keeps_the_shape(self, tmp_path):
        """The fail-closed sentinel is a full block, not a stub: a consumer reading
        `inputs` must not have to special-case the one path where it matters most."""
        result = _compute_board_staleness(ohlcv_dir=tmp_path / "nonexistent",
                                          now=self._NOW)
        assert set(result["inputs"]) == {"baskets_ohlcv_through", "panel", "board_asof"}
        assert result["max_through"] is None
        assert result["unknown_reason"]


class TestPanelPriceReach:
    """_panel_price_reach: last-close distribution of the ranked panel."""

    @staticmethod
    def _member(ticker: str, last: date, periods: int = 10,
                nan_tail: int = 0, freq: str = "B") -> tuple:
        # freq="D" for 24/7- and 6-day-calendar members, whose bars land on
        # weekends. freq="B" would silently roll `last` back to the preceding
        # Friday, which is the very thing under test.
        idx = pd.date_range(end=last, periods=periods, freq=freq)
        vals = [100.0] * periods
        for i in range(nan_tail):
            vals[-(i + 1)] = float("nan")
        # (ticker, close, high, name, sector) — the universe() tuple shape
        return (ticker, pd.Series(vals, index=idx), None, ticker, "Materials")

    def test_mixed_vintage_panel(self):
        """1 fresh member vs 3 stale: through=max, majority=modal, mixed=True —
        the 2026-08-04 shape (yahoo extras at 08-03, everything else 07-31)."""
        uni = [self._member("FRESH", date(2026, 7, 16))] + [
            self._member(t, date(2026, 7, 14)) for t in ("A", "B", "C")]
        reach = _panel_price_reach(uni)
        assert reach["through"] == "2026-07-16"
        assert reach["majority_through"] == "2026-07-14"
        assert reach["members_at_through"] == 1
        assert reach["members_total"] == 4
        assert reach["mixed_vintage"] is True

    def test_uniform_panel_is_not_mixed(self):
        uni = [self._member(t, date(2026, 7, 16)) for t in ("A", "B", "C")]
        reach = _panel_price_reach(uni)
        assert reach["through"] == "2026-07-16"
        assert reach["majority_through"] == "2026-07-16"
        assert reach["mixed_vintage"] is False

    def test_delisted_straggler_does_not_flag_mixed(self):
        """A dead name whose series stops months earlier loses the mode —
        majority == through, mixed stays False."""
        uni = [self._member(t, date(2026, 7, 16)) for t in ("A", "B", "C")] + [
            self._member("DEAD", date(2026, 4, 1))]
        reach = _panel_price_reach(uni)
        assert reach["through"] == "2026-07-16"
        assert reach["majority_through"] == "2026-07-16"
        assert reach["mixed_vintage"] is False

    def test_even_split_ties_toward_fresher(self):
        """A 50/50 split reports majority == through (not flagged by a coin flip)."""
        uni = [self._member(t, date(2026, 7, 16)) for t in ("A", "B")] + [
            self._member(t, date(2026, 7, 14)) for t in ("C", "D")]
        reach = _panel_price_reach(uni)
        assert reach["majority_through"] == "2026-07-16"
        assert reach["mixed_vintage"] is False

    def test_nan_tail_uses_last_valid_close(self):
        """A breadth-panel column with a NaN tail (name stopped trading) reports
        its last VALID close, not the panel's index end."""
        uni = [self._member("NANTAIL", date(2026, 7, 16), periods=10, nan_tail=2),
               self._member("A", date(2026, 7, 16))]
        reach = _panel_price_reach(uni)
        # NANTAIL's last valid bar is 2 business days before 07-16 → 07-14
        assert reach["through"] == "2026-07-16"
        assert reach["members_total"] == 2
        assert reach["members_at_through"] == 1

    def test_empty_and_unreadable_members(self):
        assert _panel_price_reach([]) is None
        assert _panel_price_reach(None) is None
        all_bad = [("X", None, None, "X", ""),
                   ("Y", pd.Series(dtype=float), None, "Y", "")]
        assert _panel_price_reach(all_bad) is None
        # unreadable members are skipped, not fatal
        uni = all_bad + [self._member("A", date(2026, 7, 16))]
        reach = _panel_price_reach(uni)
        assert reach["members_total"] == 1
        assert reach["through"] == "2026-07-16"

    def test_crypto_member_never_moves_through(self):
        """A 24/7 member with a weekend-fresh bar must not claim session reach
        for the equity board (it would clear the DELAYED badge while every
        equity is stale — the exact masking this disclosure exists to stop)."""
        uni = [self._member(t, date(2026, 7, 14)) for t in ("A", "B", "C")] + [
            self._member("FAKE-USD", date(2026, 7, 16))]
        reach = _panel_price_reach(uni, exclude={"FAKE-USD"})
        assert reach["through"] == "2026-07-14"
        assert reach["members_total"] == 3
        assert reach["mixed_vintage"] is False

    def test_weekend_riders_do_not_tear_the_panel(self, tmp_path):
        """R6 REGRESSION PIN — the 2026-08-09 (Sunday) nightly, exactly.

        1,758 members: the equity majority last-valid Friday 2026-08-07, six
        weekend-calendar members carrying Sunday 08-09 bars past the three-coin
        crypto exclusion. Before the session clamp this read through=08-09 vs
        majority=08-07 → mixed_vintage TRUE, and prophet_bridge refused ALL 30
        eligible candidates at clock_provenance ("mixed-vintage boards cannot
        originate plans"): zero plans originated, deterministically, on every
        Sunday and holiday-Monday bake.

        A Sunday bar is not a session, so it counts as the session it followed.
        The board is NOT torn: mixed_vintage False, nobody off-majority — and
        the raw Sunday reach stays disclosed, in `through_raw` here and in
        `max_through` on the staleness block.
        """
        uni = [self._member(t, date(2026, 8, 7)) for t in ("A", "B", "C", "D")] + [
            self._member(t, date(2026, 8, 9), freq="D")
            for t in ("RIDE1-USD", "RIDE2")]
        reach = _panel_price_reach(uni, exclude=frozenset())

        assert reach["mixed_vintage"] is False
        assert reach["majority_through"] == "2026-08-07"
        assert reach["through"] == "2026-08-07"
        assert reach["off_majority_tickers"] == []
        # Clamped judgment, undeleted facts.
        assert reach["through_raw"] == "2026-08-09"
        assert reach["members_total"] == 6
        assert reach["members_at_through"] == 6

        # The staleness block keeps publishing the RAW freshest reach.
        result = _compute_board_staleness(
            ohlcv_dir=tmp_path / "absent", panel_reach=reach,
            now=datetime(2026, 8, 9, 23, 58, tzinfo=timezone.utc))
        assert result["price_through"] == "2026-08-07"
        assert result["max_through"] == "2026-08-09"
        assert result["basis"] == "panel_majority"
        assert result["delayed"] is False and result["unknown"] is False

    def test_same_calendar_tear_still_flags_and_names_the_minority(self):
        """A GENUINE tear — two SESSION dates in one panel — still flags, and
        the receipt now names the off-majority members instead of leaving the
        diagnosis to artifact archaeology."""
        uni = [self._member(t, date(2026, 8, 5)) for t in ("A", "B", "C", "D")] + [
            self._member(t, date(2026, 8, 7)) for t in ("FRESH2", "FRESH1")]
        reach = _panel_price_reach(uni, exclude=frozenset())

        assert reach["mixed_vintage"] is True
        assert reach["majority_through"] == "2026-08-05"
        assert reach["through"] == "2026-08-07"
        assert reach["through_raw"] == "2026-08-07"
        assert reach["off_majority_tickers"] == ["FRESH1", "FRESH2"]

    def test_off_majority_list_is_capped(self):
        """Diagnosability, not a dump: the name list stays bounded at 10."""
        uni = [self._member(f"OLD{i}", date(2026, 8, 5)) for i in range(20)] + [
            self._member(f"NEW{i:02d}", date(2026, 8, 7)) for i in range(15)]
        reach = _panel_price_reach(uni, exclude=frozenset())
        assert reach["mixed_vintage"] is True
        assert len(reach["off_majority_tickers"]) == 10
        assert reach["off_majority_tickers"] == sorted(reach["off_majority_tickers"])

    def test_default_exclusion_is_config_crypto_set(self, monkeypatch):
        """exclude=None wires to _crypto_tickers() — the same config block
        universe() sources crypto from (never a hardcoded coin list)."""
        import scripts.build_stock_library as bsl
        monkeypatch.setattr(bsl, "_crypto_tickers",
                            lambda: frozenset({"FAKE-USD"}))
        uni = [self._member("A", date(2026, 7, 14)),
               self._member("FAKE-USD", date(2026, 7, 16))]
        reach = _panel_price_reach(uni)
        assert reach["through"] == "2026-07-14"
        assert reach["members_total"] == 1
        # an explicit empty exclusion set overrides the default (nothing skipped)
        reach_all = _panel_price_reach(uni, exclude=frozenset())
        assert reach_all["through"] == "2026-07-16"
        assert reach_all["members_total"] == 2


# ---------------------------------------------------------------------------
# Producer → consumer seam: the panel receipt that gates plan origination
# ---------------------------------------------------------------------------

class TestPanelReachReachesTheOriginationGate:
    """R6: the clamp is producer-side ONLY — the #5071 gate is byte-identical.

    engine.prophet_bridge._resolve_origination_clocks refuses EVERY candidate
    when staleness.inputs.panel.mixed_vintage is true. That refusal is correct
    and stays: what changed is that a weekend bar no longer counts as a torn
    panel. Both halves are pinned here, on the real 2026-08-09 shapes.
    """

    _RECORDED_ASOF = "2026-08-09"   # the nightly's own run date (Sunday)
    _NOW = datetime(2026, 8, 9, 23, 58, tzinfo=timezone.utc)

    def _tonight(self, tmp_path) -> dict:
        """The 2026-08-09 panel, end to end through the real producer."""
        uni = [TestPanelPriceReach._member(t, date(2026, 8, 7))
               for t in ("A", "B", "C", "D")] + [
            TestPanelPriceReach._member(t, date(2026, 8, 9), freq="D")
            for t in ("RIDE1-USD", "RIDE2")]
        return _compute_board_staleness(
            ohlcv_dir=tmp_path / "absent",
            panel_reach=_panel_price_reach(uni, exclude=frozenset()),
            now=self._NOW)

    @staticmethod
    def _clocks(staleness: dict):
        """Read the staleness block exactly as prophet_bridge does."""
        from engine.prophet_bridge import _resolve_origination_clocks
        panel = (staleness.get("inputs") or {}).get("panel") or {}
        return _resolve_origination_clocks(
            price_through=staleness.get("price_through"),
            recorded_asof=TestPanelReachReachesTheOriginationGate._RECORDED_ASOF,
            panel_mixed_vintage=bool(panel.get("mixed_vintage")),
            source_delayed=staleness.get("delayed"),
            source_unknown=staleness.get("unknown"),
            source_basis=staleness.get("basis"),
        )

    def test_healed_sunday_board_originates(self, tmp_path):
        """AFTER the fix: tonight's board clears the gate with zero errors."""
        staleness = self._tonight(tmp_path)
        recorded_at, price_basis_date, errors = self._clocks(staleness)
        assert errors == []
        assert recorded_at == "2026-08-09"
        assert price_basis_date == "2026-08-07"

    def test_gate_still_refuses_a_genuinely_mixed_board(self, tmp_path):
        """The RAW 2026-08-09 shape (mixed_vintage true, as the artifact
        actually published it) is STILL refused — the gate is untouched."""
        staleness = self._tonight(tmp_path)
        staleness["inputs"]["panel"]["mixed_vintage"] = True
        _, _, errors = self._clocks(staleness)
        assert any("mixed-vintage boards cannot originate plans" in e
                   for e in errors)


# ---------------------------------------------------------------------------
# _expire_pending_buys
# ---------------------------------------------------------------------------

class TestExpirePendingBuys:
    """Board as_of = 2026-07-17 (Thursday).

    Session counts from fire_date to 2026-07-17:
      fire_date=2026-07-09 (Thu) → 07-10 Fri, 07-13 Mon, 07-14 Tue, 07-15 Wed, 07-16 Thu, 07-17 Thu
                                 = 6 sessions → expired (> 3)
      fire_date=2026-07-14 (Tue) → 07-15 Wed, 07-16 Thu, 07-17 Thu = 3 sessions → NOT expired (= 3)
      fire_date=2026-07-15 (Wed) → 07-16 Thu, 07-17 Thu = 2 sessions → NOT expired
      fire_date=2026-07-16 (Thu) → 07-17 Thu = 1 session → NOT expired
    """
    _ASOF = "2026-07-17"

    def test_fresh_pending_stays_on_buy(self):
        """A pending buy fired today (0 sessions old) stays on buy."""
        row = _make_pending_row("FRESH", "2026-07-17")
        buy_in = [row]
        watch_in = []
        buy_out, watch_out, n = _expire_pending_buys(buy_in, watch_in, self._ASOF)
        assert n == 0
        assert len(buy_out) == 1
        assert buy_out[0]["ticker"] == "FRESH"
        assert len(watch_out) == 0

    def test_exactly_3_sessions_stays_on_buy(self):
        """A pending buy exactly 3 sessions old (= threshold) stays on buy (rule is > 3)."""
        row = _make_pending_row("EXACT3", "2026-07-14")
        buy_in = [row]
        watch_in = []
        buy_out, watch_out, n = _expire_pending_buys(buy_in, watch_in, self._ASOF)
        assert n == 0
        assert len(buy_out) == 1

    def test_expired_pending_demoted_to_watch_lane_in_buy(self):
        """A pending buy > 3 sessions old is demoted to lane='watch' but stays in buy_out.

        The standout board template only renders rows from wide["buy"] / _su.buy.
        Moving expired rows to the separate wide["watch"] data-plane would silently
        drop them from the board.  Instead they stay in buy with lane='watch' so the
        template's _lane_order partition renders them under the Watch sub-heading and
        the pending_expired note fires.
        """
        row = _make_pending_row("OLD", "2026-07-09")  # 6 sessions ago
        buy_in = [row]
        watch_in = []
        buy_out, watch_out, n = _expire_pending_buys(buy_in, watch_in, self._ASOF)
        assert n == 1
        # Demoted row stays in buy_out with lane='watch'
        assert len(buy_out) == 1
        expired_row = buy_out[0]
        assert expired_row["ticker"] == "OLD"
        assert expired_row["pending_expired"] is True
        assert "2026-07-09" in expired_row["pending_expiry_reason"]
        assert "2026-07-09" in expired_row["pending_expiry_reason_zh"]
        assert expired_row["lane"] == "watch"
        # watch_out is the unchanged watch_rows passthrough (empty in this case)
        assert len(watch_out) == 0

    def test_confirmed_take_never_expires(self):
        """A confirmed take signal (quality='take') is never expired, regardless of age."""
        row = _make_take_row("TAKE", "2026-07-01")  # very old, but confirmed
        buy_in = [row]
        watch_in = []
        buy_out, watch_out, n = _expire_pending_buys(buy_in, watch_in, self._ASOF)
        assert n == 0
        assert len(buy_out) == 1
        assert buy_out[0]["ticker"] == "TAKE"

    def test_expired_row_in_buy_watch_rows_passed_through(self):
        """Expired pending rows stay in buy_out (lane='watch'); watch_rows pass through unchanged.

        The wide["watch"] data-plane is a separate list the board template never iterates,
        so expired rows must NOT be moved there.  watch_rows are passed through unchanged.
        """
        expired_row = _make_pending_row("OLD", "2026-07-09")
        existing_watch = [{"ticker": "WATCH1", "lane": "watch", "signal": {}}]
        buy_in = [expired_row]
        buy_out, watch_out, n = _expire_pending_buys(buy_in, existing_watch, self._ASOF)
        assert n == 1
        # Expired row is in buy_out with lane='watch'
        assert buy_out[0]["ticker"] == "OLD"
        assert buy_out[0]["lane"] == "watch"
        assert buy_out[0]["pending_expired"] is True
        # watch_rows are passed through unchanged (not prepended to)
        assert len(watch_out) == 1
        assert watch_out[0]["ticker"] == "WATCH1"

    def test_mixed_buy_rows(self):
        """Fresh + old pending + confirmed: only old pending is demoted to lane='watch'.

        All three rows stay in buy_out; the demoted row has lane='watch' and
        pending_expired=True so the template renders it under the Watch sub-heading.
        """
        rows = [
            _make_pending_row("FRESH", "2026-07-17"),   # 0 sessions — stays as-is
            _make_pending_row("OLD", "2026-07-09"),      # 6 sessions — demoted to watch lane
            _make_take_row("TAKE", "2026-07-01"),        # confirmed — never expires
        ]
        buy_out, watch_out, n = _expire_pending_buys(rows, [], self._ASOF)
        assert n == 1
        buy_tickers = [r["ticker"] for r in buy_out]
        # All three rows remain in buy_out
        assert "FRESH" in buy_tickers
        assert "TAKE" in buy_tickers
        assert "OLD" in buy_tickers
        # The demoted row is tagged correctly
        old_row = next(r for r in buy_out if r["ticker"] == "OLD")
        assert old_row["lane"] == "watch"
        assert old_row["pending_expired"] is True
        # watch_out is the unchanged passthrough (empty in this case)
        assert len(watch_out) == 0

    def test_none_asof_does_nothing(self):
        """None board_asof: no rows are expired (fail-soft)."""
        row = _make_pending_row("OLD", "2026-07-01")
        buy_out, watch_out, n = _expire_pending_buys([row], [], None)
        assert n == 0
        assert len(buy_out) == 1

    def test_missing_fire_date_stays_on_buy(self):
        """A pending row with no fire date (last.date absent) stays on buy."""
        row = {
            "ticker": "NODATE",
            "lane": "trend",
            "signal": {
                "tier": "anticipation",
                "sub": "pending",
                "last": {"type": "buy", "quality": "pending"},
            },
        }
        buy_out, watch_out, n = _expire_pending_buys([row], [], self._ASOF)
        assert n == 0
        assert len(buy_out) == 1

    def test_does_not_mutate_original_buy_list(self):
        """The original buy list items are not mutated (shallow copy is made)."""
        row = _make_pending_row("OLD", "2026-07-09")
        original_lane = row["lane"]
        buy_out, watch_out, n = _expire_pending_buys([row], [], self._ASOF)
        assert n == 1
        # Original row's lane should not have been changed
        assert row["lane"] == original_lane, "original row must not be mutated"

    def test_watch_row_not_expired(self):
        """Rows already on watch (not in buy_rows) are never double-processed."""
        # _expire_pending_buys only processes buy_rows; watch_rows are passed through
        watch_row = _make_pending_row("WATCH_PEND", "2026-07-01")
        buy_out, watch_out, n = _expire_pending_buys([], [watch_row], self._ASOF)
        assert n == 0
        assert len(watch_out) == 1  # watch row passed through unchanged


# ---------------------------------------------------------------------------
# check_surface_freshness: us_standouts.json in _ARTIFACTS
# ---------------------------------------------------------------------------

class TestStandoutsSentinelRegistration:
    def test_us_standouts_in_artifacts(self):
        """us_standouts.json must be registered in _ARTIFACTS (FT-R8 CSP-W5)."""
        paths = [spec.path for spec in _ARTIFACTS]
        assert "site/factordata/us_standouts.json" in paths

    def test_sentinel_checks_us_standouts(self, tmp_path, capsys):
        """A stale us_standouts.json emits a ::warning:: annotation."""
        ref_now = datetime(2026, 7, 9, 3, 0, tzinfo=timezone.utc)
        expected_session = "2026-07-08"
        # Write all artifacts fresh
        for spec in _ARTIFACTS:
            p = tmp_path / spec.path
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(json.dumps({"as_of": expected_session}))
        # Poison us_standouts.json specifically
        standouts_path = tmp_path / "site" / "factordata" / "us_standouts.json"
        standouts_path.write_text(json.dumps({"as_of": "2020-01-01"}))
        rc = freshness_mod.run(now=ref_now, root=tmp_path)
        assert rc == 0  # always warn-only
        out = capsys.readouterr().out
        assert "::warning::SURFACE STALE:" in out
        assert "site/factordata/us_standouts.json" in out

    def test_fresh_us_standouts_no_warning(self, tmp_path, capsys):
        """A fresh us_standouts.json generates no warning."""
        ref_now = datetime(2026, 7, 9, 3, 0, tzinfo=timezone.utc)
        expected_session = "2026-07-08"
        for spec in _ARTIFACTS:
            p = tmp_path / spec.path
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(json.dumps({"as_of": expected_session}))
        rc = freshness_mod.run(now=ref_now, root=tmp_path)
        assert rc == 0
        out = capsys.readouterr().out
        assert "::warning::" not in out
