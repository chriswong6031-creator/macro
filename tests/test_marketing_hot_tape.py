"""Hot Tape thin lane — detectors, wire copy, refusal, ban list, numeric gate.

Pins the acceptance gates of research/MARKETING_HOT_TAPE_MASTERPLAN.md §0:

  0.2  a post with no §2.D device REFUSES (compose_wire -> None)
  0.3  every number in the copy is a leaf of the FactPacket
  0.4  no call language, ever (cashtags exempted from the scan)
  0.5  the existing outbox guards accept and dedupe our items

Plus the E1 detectors (masterplan §10): the earnings REACTION (BMO gap at the
open / AH reporter's next open, refusing on a stale calendar and refusing
without a device slot) and the two-step context BRIEF, whose mechanism is
computed from the live peer group and whose absence is a refusal.

THIS FILE MUST NOT IMPORT PANDAS — not directly, not through importorskip.
The radar runs on a shallow ubuntu checkout with pyyaml+requests only, and a
suite that silently skips is the unrun-suite rot class. Every fixture date is
derived from today, never written as a literal (the 2026-07-28 date-bomb).

Run: .venv/bin/python -m pytest tests/test_marketing_hot_tape.py -q
"""
from __future__ import annotations

import contextlib
import json
from datetime import date, datetime, timedelta, timezone

import pytest

from engine.marketing import hot_tape as HT
from engine.marketing import hot_tape_wire as W
from engine.marketing.hot_tape import FactPacket


# ─────────────────────────────────────────────────────────────────────────────
# Relative-date fixture helpers (no literal calendar dates anywhere)
# ─────────────────────────────────────────────────────────────────────────────

def _weekday_now(hour: int = 15, minute: int = 10) -> datetime:
    """A deterministic weekday timestamp inside RTH, anchored to today."""
    d = date.today()
    while d.weekday() >= 5:
        d -= timedelta(days=1)
    return datetime(d.year, d.month, d.day, hour, minute, tzinfo=timezone.utc)


def _prev_weekday(d: date) -> date:
    x = d - timedelta(days=1)
    while x.weekday() >= 5:
        x -= timedelta(days=1)
    return x


def _ago(now: datetime, days: int) -> str:
    return (now.date() - timedelta(days=days)).isoformat()


NOW = _weekday_now()
FRESH_TRADE_DATE = _prev_weekday(NOW.date()).isoformat()
STALE_TRADE_DATE = _prev_weekday(NOW.date() - timedelta(days=25)).isoformat()


def _weekday_in(month: int, hour: int, minute: int) -> datetime:
    """A UTC timestamp on a weekday in `month` of the CURRENT year.

    The month is load-bearing and the year is not: these fixtures exist to put
    the clock on either side of a US DST boundary (January = EST, July = EDT),
    so the month is a semantic constant while the year is derived from today —
    a hard-coded year would rot exactly the way a hard-coded date does.
    """
    d = date(date.today().year, month, 10)
    while d.weekday() >= 5:
        d += timedelta(days=1)
    return datetime(d.year, d.month, d.day, hour, minute, tzinfo=timezone.utc)


def _pack(records: dict, trade_date: str) -> dict:
    return {
        "schema": "marketing.hot_tape_pack/v1",
        "built_at": NOW.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "trade_date": trade_date,
        "n_tickers": len(records),
        "sources": {"store_last_date": trade_date, "mcap_asof": None,
                    "earnings_asof": None, "heatmap_asof": None},
        "tickers": records,
    }


def _rec(**over) -> dict:
    """A pack record with every field the detectors read."""
    rec = {
        "last_date": FRESH_TRADE_DATE,
        "last_close": 100.0,
        "prev_close": 101.0,
        "streak": {"dir": "down", "len": 8,
                   "last_run_ge": {"9": _ago(NOW, 1500), "10": None,
                                   "11": None, "12": None}},
        "ath": 140.0,
        "ath_date": _ago(NOW, 50),
        "high_52w": 140.0, "high_52w_date": _ago(NOW, 50),
        "low_52w": 80.0, "low_52w_date": _ago(NOW, 200),
        "pct_from_ath": -28.57,
        "ma20": 105.0, "ma50": 110.0, "ma200": 115.0,
        "rsi14": 34.0, "rsi_avg_gain": 0.5, "rsi_avg_loss": 1.5,
        "rsi_low_1y": 22.0, "rsi_low_1y_date": _ago(NOW, 300),
        "rsi_high_1y": 78.0, "rsi_high_1y_date": _ago(NOW, 320),
        "last_rsi_le_30": _ago(NOW, 500),
        "last_rsi_ge_70": _ago(NOW, 520),
        "max_up_1d": {"pct": 6.5, "date": _ago(NOW, 400)},
        "max_dn_1d": {"pct": -7.4, "date": _ago(NOW, 400)},
        "max_up_5d": {"pct": 12.0, "date": _ago(NOW, 410)},
        "max_dn_5d": {"pct": -14.0, "date": _ago(NOW, 410)},
        "round_above": 110.0, "round_below": 100.0,
        "px_correction": 126.0, "px_bear": 112.0,
        "adv20_dollars": 900_000_000.0, "adv_rank": 12,
        "mcap_usd": 300_000_000_000, "shares_est": 3_000_000_000,
        "sector": "Technology", "sp500": True,
        "earn_next_date": _ago(NOW, -8), "earn_next_time": "time-after-hours",
        "window_start": _ago(NOW, 1800), "suspect": False,
    }
    rec.update(over)
    return rec


def _quote(pct: float, price: float = 100.0, prev: float = 101.0) -> dict:
    return {"price": price, "prev_close": prev, "change_pct": pct,
            "ts_ms": int(NOW.timestamp() * 1000), "source": "quotes"}


def _tile(sym: str, sector: str, pct: float, industry: str = "Widgets",
          name: str | None = None) -> dict:
    return {"t": sym, "name": name or sym, "sector": sector,
            "industry": industry, "size": 0.5, "perf": {"1D": pct}}


def _packet(trigger: str, key: str, direction: str, facts: dict, *,
            session: str = "rth", ticker: str | None = None,
            sector: str | None = None, severity: float = 80.0) -> FactPacket:
    return FactPacket(
        trigger=trigger, key=key, fired_at=NOW.strftime("%Y-%m-%dT%H:%M:%SZ"),
        session=session, ticker=ticker, name=None, sector=sector,
        direction=direction, severity=severity, facts=facts,
        provenance={"pack_asof": None, "store_last_date": FRESH_TRADE_DATE,
                    "quotes_asof": None, "quote_ts_ms": None,
                    "quote_source": "quotes", "bridge_ok": True, "demo": False},
    )


@contextlib.contextmanager
def forced_variant(trigger: str, entry):
    """Pin the bank to exactly one variant so every template gets exercised."""
    original = W.WIRE_BANK[trigger]
    W.WIRE_BANK[trigger] = (entry,)
    try:
        yield
    finally:
        W.WIRE_BANK[trigger] = original


# ─────────────────────────────────────────────────────────────────────────────
# Rich per-family fixtures (every device derivable)
# ─────────────────────────────────────────────────────────────────────────────

def rich_packets() -> dict[str, FactPacket]:
    return {
        "mover_drop": _packet(
            "mover_drop", "mover:AMD:down:x:0", "down", ticker="AMD",
            sector="Technology", facts={
                "ticker": "AMD", "name": "AMD", "pct": -8.13, "price": 84.2,
                "prev_close": 91.65, "dollar_delta_usd": -11_100_000_000,
                "pct_from_ath_live": -28.42, "ath": 117.66, "ath_date": _ago(NOW, 50),
                "streak_extends": {"dir": "down", "len_today": 9,
                                   "since": _ago(NOW, 1500),
                                   "window_start": _ago(NOW, 1800)},
                "rsi_live": 27.4, "rsi_band": 30, "rsi_since": _ago(NOW, 500),
                "biggest_1d": {"window_start": _ago(NOW, 1800), "prior_pct": -7.4,
                               "prior_date": _ago(NOW, 400)},
                "sector": "Technology", "earn_next_date": _ago(NOW, -8),
                "earn_next_time": "time-after-hours"}),
        "mover_pop": _packet(
            "mover_pop", "mover:KO:up:x:0", "up", ticker="KO",
            sector="Consumer Defensive", facts={
                "ticker": "KO", "name": "KO", "pct": 6.02, "price": 74.5,
                "prev_close": 70.27, "dollar_delta_usd": 18_400_000_000,
                "pct_from_ath_live": -2.1, "ath": 76.1, "ath_date": _ago(NOW, 60),
                "streak_extends": {"dir": "up", "len_today": 6,
                                   "since": _ago(NOW, 900),
                                   "window_start": _ago(NOW, 1800)},
                "rsi_live": 72.6, "rsi_band": 70, "rsi_since": _ago(NOW, 520),
                "biggest_1d": {"window_start": _ago(NOW, 1800), "prior_pct": 5.1,
                               "prior_date": _ago(NOW, 380)},
                "sector": "Consumer Defensive", "earn_next_date": None,
                "earn_next_time": None}),
        "sector_rout": _packet(
            "sector_rout", "sector:Semiconductors:down:x", "down",
            sector="Semiconductors", facts={
                "sector": "Semiconductors", "group_kind": "industry",
                "median_pct": -7.85, "breadth_pct": 92.59, "n_members": 27,
                "n_down": 25, "leaders": [["SNDK", -14.32], ["MU", -8.94],
                                          ["STX", -8.51], ["AMD", -8.2], ["ARM", -8.1]],
                "dollar_moved_usd": -284_000_000_000, "index_pct": -1.62,
                "index_ticker": "SPY"}),
        "sector_rip": _packet(
            "sector_rip", "sector:Utilities:up:x", "up", sector="Utilities", facts={
                "sector": "Utilities", "group_kind": "sector", "median_pct": 2.64,
                "breadth_pct": 88.0, "n_members": 25, "n_up": 22,
                "leaders": [["NEE", 4.4], ["DUK", 3.9], ["SO", 3.5], ["AEP", 3.1],
                            ["EXC", 2.9]],
                "dollar_moved_usd": 41_000_000_000, "index_pct": 0.42,
                "index_ticker": "SPY"}),
        "threshold_cross": _packet(
            "threshold_cross", "threshold:QQQ:correction:x", "down", ticker="QQQ",
            facts={"ticker": "QQQ", "kind": "correction", "price": 615.3,
                   "prev_close": 620.1, "pct": -0.77, "direction": "down",
                   "threshold_px": 617.4, "pct_from_ath_live": -10.24,
                   "ath": 686.0, "ath_date": _ago(NOW, 50), "sector": None}),
        "streak_rarity": _packet(
            "streak_rarity", "streak:META:x", "down", ticker="META",
            facts={"ticker": "META", "dir": "down", "len_today": 9,
                   "since": _ago(NOW, 1500), "window_start": _ago(NOW, 1800),
                   "pct_today": -2.14, "price": 548.9}),
        "signal_fired": _packet(
            "signal_fired", "signal:abc123", "up", ticker="MSFT",
            facts={"ticker": "MSFT", "level": 310.5, "price": 311.8,
                   "prev_close": 308.4, "pct": 1.1, "direction": "up",
                   "plan_as_of": _prev_weekday(NOW.date()).isoformat(),
                   "signal_id": "abc123"}),
        "contrarian_breadth": _packet(
            "contrarian_breadth", "contrarian:x", "up", facts={
                "index_pct": -1.82, "index_ticker": "SPY",
                "green": [["COST", 1.24], ["HD", 0.93], ["MMM", 0.71], ["KO", 0.55]],
                "sectors_green": ["Consumer Defensive", "Utilities"], "n_green": 11,
                # The universe the count moves against. Without it the only
                # count-bearing variant refuses (see TestContrarianDetector).
                "n_defensive_members": 18}),
        "earnings_reaction": _packet(
            "earnings_reaction", "earnings:AAPL:up:x:0", "up", ticker="AAPL",
            sector="Technology", severity=95.0, facts={
                "ticker": "AAPL", "name": "Apple", "pct": 6.67, "price": 224.0,
                "prev_close": 210.0, "report_when": "ah",
                "report_date": _prev_weekday(NOW.date()).isoformat(),
                "earn_next_time": "time-after-hours",
                "eps": {"actual": 2.11, "consensus": 1.88, "surprise_pct": 12.23,
                        "reported": _prev_weekday(NOW.date()).isoformat(),
                        "beat": True},
                "dollar_delta_usd": 213_000_000_000,
                "pct_from_ath_live": -13.85, "ath": 260.0, "ath_date": _ago(NOW, 50),
                "biggest_1d": {"window_start": _ago(NOW, 1800), "prior_pct": 5.0,
                               "prior_date": _ago(NOW, 300)},
                "sector": "Technology"}),
        # BOTH a cashtag and a subject_label on purpose: production packets
        # carry one or the other (the label is what selects the group-brief
        # templates), and the rich fixture must render EVERY variant so the ban
        # scan and the numeric gate see all four.
        "context_brief": _packet(
            "context_brief", "brief:mover:MU:down:x:0", "down", ticker="MU",
            sector="Semiconductors", severity=95.0, facts={
                "subject": "MU", "subject_label": "Semiconductors", "ticker": "MU",
                "sector": "Semiconductors", "alert_key": "mover:MU:down:x:0",
                "alert_trigger": "mover_drop", "pct": -8.2, "price": 84.2,
                "mechanism": {"kind": "single_name", "group": "Semiconductors",
                              "group_kind": "industry", "peer_median_pct": -0.31,
                              "n_peers": 26, "n_agree": 14},
                "peers": [["SNDK", -14.32], ["STX", -8.51], ["AMD", -8.2]],
                "watch": {"kind": "level", "price": 84.2}}),
    }


# ─────────────────────────────────────────────────────────────────────────────
# Gate 0.2 — device-slot refusal
# ─────────────────────────────────────────────────────────────────────────────

class TestDeviceRefusal:
    def test_mover_without_any_device_refuses(self):
        """A bare '%-move' post is the corpus's 95-view flop. It must be impossible."""
        bare = _packet("mover_drop", "mover:XYZ:down:x:0", "down", ticker="XYZ",
                       facts={"ticker": "XYZ", "pct": -8.4, "price": 42.0,
                              "prev_close": 45.85, "dollar_delta_usd": None,
                              "pct_from_ath_live": None, "ath": None,
                              "ath_date": None, "streak_extends": None,
                              "rsi_live": None, "rsi_band": None, "rsi_since": None,
                              "biggest_1d": None})
        assert W.compose_wire(bare) is None

    def test_mover_with_one_device_composes(self):
        one = _packet("mover_drop", "mover:XYZ:down:x:0", "down", ticker="XYZ",
                      facts={"ticker": "XYZ", "pct": -8.4, "price": 42.0,
                             "dollar_delta_usd": -3_200_000_000})
        out = W.compose_wire(one)
        assert out is not None
        assert "dollar_clause" in out["devices"]

    def test_sector_without_leaders_or_dollars_refuses(self):
        thin = _packet("sector_rout", "sector:Technology:down:x", "down",
                       sector="Technology",
                       facts={"sector": "Technology", "group_kind": "sector",
                              "median_pct": -3.1, "breadth_pct": 80.0,
                              "n_members": 20, "n_down": 16, "leaders": [],
                              "dollar_moved_usd": None, "index_pct": None})
        assert W.compose_wire(thin) is None

    def test_streak_without_a_day_count_refuses(self):
        thin = _packet("streak_rarity", "streak:X:x", "down", ticker="X",
                       facts={"ticker": "X", "dir": "down", "len_today": None,
                              "since": None, "window_start": None, "pct_today": -2.0})
        assert W.compose_wire(thin) is None

    def test_streak_falls_back_to_the_window_when_since_is_null(self):
        """No prior run in our data is stated honestly, never as a longer memory."""
        p = _packet("streak_rarity", "streak:META:x", "down", ticker="META",
                    facts={"ticker": "META", "dir": "down", "len_today": 9,
                           "since": None, "window_start": _ago(NOW, 1800),
                           "pct_today": -2.1, "price": 548.9})
        out = W.compose_wire(p)
        assert out is not None
        assert "since at least" in out["text"]

    def test_every_earnings_variant_states_the_beat_or_the_miss(self):
        """M3. An earnings reaction post that never prints the EPS line tells
        the reader a report landed and a stock moved, and withholds the one
        number it exists to deliver. Two of the four variants closed on a dollar
        translation or a record rank instead, and `eps_clause` was merely one of
        five acceptable devices, so the shape shipped."""
        mandatory, _any_of = W.DEVICE_LAW["earnings_reaction"]
        assert "eps_clause" in mandatory, mandatory
        for template, required in W.WIRE_BANK["earnings_reaction"]:
            assert "{eps_clause}" in template, template
            assert "eps_clause" in required, template

    def test_an_earnings_packet_with_no_eps_refuses_rather_than_padding(self):
        packet = rich_packets()["earnings_reaction"]
        assert W.compose_wire(packet) is not None, "fixture is degenerate"
        stripped = _packet(
            "earnings_reaction", packet.key, packet.direction,
            ticker=packet.ticker,
            facts={k: v for k, v in packet.facts.items() if k != "eps"})
        assert W.compose_wire(stripped) is None, (
            "an earnings post rendered without the earnings")

    def test_every_composed_post_carries_a_device(self):
        for trigger, packet in rich_packets().items():
            out = W.compose_wire(packet)
            assert out is not None, trigger
            mandatory, any_of = W.DEVICE_LAW[trigger]
            assert set(mandatory) <= set(out["devices"]), trigger
            if any_of:
                assert set(out["devices"]) & any_of, trigger


class TestDeviceClauses:
    """The §2.D slot builders, pinned one claim at a time."""

    def test_the_record_clause_anchors_on_the_window_not_the_prior_extreme(self):
        """M9 — our memory starts at window_start; say so, do not imply more.

        prior_date is the last bigger move INSIDE the dense window, so "biggest
        drop since <prior_date>" quietly claimed a longer memory than the pack
        has. prior_pct / prior_date stay in the facts as provenance.
        """
        packet = rich_packets()["mover_drop"]
        window = W.fmt_since(packet.facts["biggest_1d"]["window_start"],
                             packet.fired_at[:10])
        clause = W._record_rank_clause(packet, packet.facts)
        assert clause == f"That is its biggest one-day drop since at least {window}"
        prior = W.fmt_since(packet.facts["biggest_1d"]["prior_date"],
                            packet.fired_at[:10])
        assert prior not in clause
        assert packet.facts["biggest_1d"]["prior_pct"] == -7.4     # provenance kept

    def test_the_record_clause_says_gain_on_the_way_up(self):
        packet = rich_packets()["mover_pop"]
        clause = W._record_rank_clause(packet, packet.facts)
        assert clause.startswith("That is its biggest one-day gain since at least ")

    def test_a_two_day_run_is_not_a_streak_device(self):
        """m2 — streak_extends carries no rarity floor of its own.

        "Day 2 of the slide, its longest red run since at least March 2021" is a
        two-day sequence dressed as a differentiating stat.
        """
        facts = {"ticker": "X", "dir": "down", "len_today": 2,
                 "since": _ago(NOW, 1500), "window_start": _ago(NOW, 1800)}
        packet = _packet("streak_rarity", "streak:X:x", "down", facts, ticker="X")
        assert W._streak_clause(packet, facts) is None
        assert W.STREAK_CLAUSE_MIN_LEN == 5
        assert HT.DEFAULTS["detectors"]["streak"]["min_len"] == W.STREAK_CLAUSE_MIN_LEN

    def test_a_mover_whose_only_device_is_a_two_day_run_refuses(self):
        thin = _packet("mover_drop", "mover:X:down:x:0", "down", ticker="X",
                       facts={"ticker": "X", "pct": -8.4, "price": 42.0,
                              "dollar_delta_usd": None, "biggest_1d": None,
                              "rsi_band": None, "rsi_since": None,
                              "streak_extends": {"dir": "down", "len_today": 2,
                                                 "since": _ago(NOW, 1500),
                                                 "window_start": _ago(NOW, 1800)}})
        assert W.compose_wire(thin) is None

    def test_a_five_day_run_still_composes(self):
        facts = {"ticker": "X", "dir": "down", "len_today": 5,
                 "since": _ago(NOW, 1500), "window_start": _ago(NOW, 1800)}
        packet = _packet("streak_rarity", "streak:X:x", "down", facts, ticker="X")
        assert W._streak_clause(packet, facts) is not None

    def test_the_rsi_side_comes_from_the_band_never_the_direction(self):
        """C2 (wire half) — the inversion that printed "back under 70" at 75.3."""
        packet = rich_packets()["mover_drop"]
        assert W._since_clause(packet, packet.facts).startswith("RSI is back under 30 ")

        inverted = _packet("mover_drop", "mover:X:down:x:0", "down", ticker="X",
                           facts={"ticker": "X", "pct": -3.1, "price": 42.0,
                                  "rsi_live": 75.3, "rsi_band": 70,
                                  "rsi_since": _ago(NOW, 520)})
        assert W._since_clause(inverted, inverted.facts) is None

    def test_an_up_cross_says_above(self):
        packet = rich_packets()["mover_pop"]
        assert W._since_clause(packet, packet.facts).startswith("RSI is back above 70 ")

    def test_a_nonsense_band_refuses(self):
        packet = _packet("mover_drop", "k", "down", ticker="X",
                         facts={"ticker": "X", "pct": -3.1, "rsi_band": 50,
                                "rsi_since": _ago(NOW, 520), "rsi_live": 49.0})
        assert W._since_clause(packet, packet.facts) is None


# ─────────────────────────────────────────────────────────────────────────────
# Gate 0.4 — call-language ban
# ─────────────────────────────────────────────────────────────────────────────

class TestBanList:
    def test_static_bank_is_clean(self):
        for text in W.static_strings():
            assert W.ban_hits(text) == [], text

    def test_every_variant_of_every_family_is_clean(self):
        for trigger, packet in rich_packets().items():
            for entry in W.WIRE_BANK[trigger]:
                with forced_variant(trigger, entry):
                    out = W.compose_wire(packet)
                assert out is not None, (trigger, entry[0])
                assert W.ban_hits(out["text"]) == [], out["text"]

    @pytest.mark.parametrize("phrase", [
        "we are buying this dip", "great entry here", "adding to my position",
        "take profits", "stop loss at 40", "load up", "I'm in", "sell it",
        "target 500", "watch the calls", "chase it",
    ])
    def test_call_language_is_detected(self, phrase):
        assert W.ban_hits(phrase)

    def test_cashtags_are_exempt_from_the_scan(self):
        """$LONG is a ticker, not the word 'long'."""
        assert W.ban_hits("$LONG is down 4.0% right now") == []
        assert W.ban_hits("$SHORT and $BID and $CALLS held up") == []
        assert "long" in W.ban_hits("long AMD from here")

    def test_a_banned_ticker_still_composes(self):
        p = _packet("mover_drop", "mover:LONG:down:x:0", "down", ticker="LONG",
                    facts={"ticker": "LONG", "pct": -8.4, "price": 42.0,
                           "dollar_delta_usd": -3_200_000_000})
        out = W.compose_wire(p)
        assert out is not None
        assert "$LONG" in out["text"]


# ─────────────────────────────────────────────────────────────────────────────
# Gate 0.3 — numeric consistency
# ─────────────────────────────────────────────────────────────────────────────

class TestNumericConsistency:
    def test_every_rendered_number_comes_from_the_packet(self):
        for trigger, packet in rich_packets().items():
            for entry in W.WIRE_BANK[trigger]:
                with forced_variant(trigger, entry):
                    out = W.compose_wire(packet)
                assert out is not None, (trigger, entry[0])
                assert W.check_text_numbers(out["text"], packet) == [], out["text"]

    def test_a_foreign_number_is_reported(self):
        packet = rich_packets()["mover_drop"]
        text = "$AMD is down 8.1% right now, headed for 42.7% more."
        assert "42.7%" in W.check_text_numbers(text, packet)

    def test_tamper_rendering_against_another_packet_fails(self):
        packets = rich_packets()
        a, b = packets["mover_drop"], packets["mover_pop"]
        text = W.compose_wire(a)["text"]
        assert W.check_text_numbers(text, a) == []
        assert W.check_text_numbers(text, b) != []

    def test_compose_refuses_a_template_that_invents_a_number(self):
        """The runtime gate, not just the test suite, is what holds in production."""
        packet = rich_packets()["mover_drop"]
        bad = ("{cashtag} {dir_verb} {pct_abs} {live_marker}. {dollar_clause}. "
               "That is 99.9% of the float.", ("dollar_clause", "live_marker"))
        with forced_variant("mover_drop", bad):
            assert W.compose_wire(packet) is None

    def test_compose_refuses_a_template_with_banned_language(self):
        packet = rich_packets()["mover_drop"]
        bad = ("{cashtag} {dir_verb} {pct_abs} {live_marker}. {dollar_clause}. "
               "Great entry.", ("dollar_clause", "live_marker"))
        with forced_variant("mover_drop", bad):
            assert W.compose_wire(packet) is None

    def test_dates_do_not_leak_bare_years(self):
        packet = rich_packets()["mover_drop"]
        far = W.fmt_date(_ago(NOW, 500), "month_year")
        assert W.check_text_numbers(f"$AMD is down 8.1% since {far}.", packet) == []

    def test_formatters_are_shared(self):
        assert W.fmt_pct(-8.13) == "-8.1%"
        assert W.fmt_pct(-8.13, signed=False) == "8.1%"
        assert W.fmt_price(84.2) == "$84.20"
        assert W.fmt_big(1e12) == "$1 trillion"
        assert W.fmt_big(-284_000_000_000) == "$284 billion"
        assert W.fmt_big(5_400_000_000) == "$5.4 billion"
        assert W.fmt_big(430_000_000) == "$430 million"
        assert W.fmt_count(27) == "27"

    def test_no_em_dashes_anywhere_in_the_bank(self):
        for text in W.static_strings():
            assert "—" not in text and "–" not in text, text

    def test_posts_fit_the_wire_limit(self):
        for trigger, packet in rich_packets().items():
            for entry in W.WIRE_BANK[trigger]:
                with forced_variant(trigger, entry):
                    out = W.compose_wire(packet)
                assert len(out["text"]) <= W.MAX_CHARS, (trigger, len(out["text"]))

    def test_an_overlong_variant_drops_its_optional_device(self):
        """The drop-longest-optional retry, not a truncated post."""
        label = ("Semiconductor Equipment, Materials and Advanced Packaging "
                 "Names Across The Whole Complex and Related Substrate "
                 "Suppliers Worldwide")
        packet = _packet(
            "sector_rout", "sector:Long:down:x", "down", sector=label,
            facts={"sector": label,
                   "group_kind": "industry", "median_pct": -7.85,
                   "breadth_pct": 92.59, "n_members": 27, "n_down": 25,
                   "leaders": [["SNDK", -14.32], ["MU", -8.94], ["STX", -8.51]],
                   "dollar_moved_usd": -284_000_000_000, "index_pct": -1.62,
                   "index_ticker": "SPY"})
        long_variant = W.WIRE_BANK["sector_rout"][2]
        assert len(long_variant[0]) and "leaders_clause" in long_variant[0]
        with forced_variant("sector_rout", long_variant):
            out = W.compose_wire(packet)
        assert out is not None
        assert len(out["text"]) <= W.MAX_CHARS
        assert "$SNDK" not in out["text"]          # the optional sentence went
        assert "That is roughly $284 billion" in out["text"]
        assert out["text"].endswith(".")
        assert W.check_text_numbers(out["text"], packet) == []

    def test_an_unknown_trigger_refuses(self):
        packet = _packet("earnings_beat", "x", "up", {"pct": 12.0})
        assert W.compose_wire(packet) is None


# ─────────────────────────────────────────────────────────────────────────────
# Session markers (D5)
# ─────────────────────────────────────────────────────────────────────────────

class TestSessionMarkers:
    @pytest.mark.parametrize("phase", ["pre_open", "rth", "after_hours"])
    def test_every_phase_has_its_own_wording(self, phase):
        packet = rich_packets()["mover_drop"]
        packet.session = phase
        text = W.compose_wire(packet)["text"]
        assert any(m in text for m in W._LIVE_MARKERS[phase]), (phase, text)

    def test_the_close_marker_is_after_hours_only(self):
        """The window opens BEFORE the bell — "at the close" at 09:27 is a lie."""
        assert "at the close" in W._LIVE_MARKERS["after_hours"]
        for phase in ("pre_open", "rth"):
            assert "at the close" not in W._LIVE_MARKERS[phase]
        packet = rich_packets()["mover_drop"]
        packet.session = "pre_open"
        text = W.compose_wire(packet)["text"]
        assert not any(m in text for m in ("at the close", "so far today", "right now"))


class TestEasternWindow:
    """M6 — the window and the session phase live on the ET clock, not UTC.

    A UTC pair is right for one half of the year: 13:25-20:05Z is 09:25-16:05 ET
    under EDT but 08:25-15:05 ET under EST, which would wake the radar an hour
    early every winter and go dark for the last hour of every session.
    """

    def test_january_afternoon_is_inside_the_window(self):
        """20:30Z in EST is 15:30 ET — the hour a UTC window used to lose."""
        t = _weekday_in(1, 20, 30)
        assert HT.in_window(t, HT.DEFAULTS)
        assert HT.session_phase(t) == "rth"

    def test_january_morning_is_outside_the_window(self):
        """13:30Z in EST is 08:30 ET — an hour before the radar should wake."""
        assert not HT.in_window(_weekday_in(1, 13, 30), HT.DEFAULTS)

    def test_july_grace_admits_a_late_cron_tick(self):
        """20:10Z in EDT is 16:10 ET: five past the end, inside the 10m grace."""
        assert HT.in_window(_weekday_in(7, 20, 10), HT.DEFAULTS)
        assert not HT.in_window(_weekday_in(7, 20, 20), HT.DEFAULTS)

    def test_july_open_edge_is_pre_open(self):
        """13:25Z in EDT is 09:25 ET — in the window, before the bell."""
        t = _weekday_in(7, 13, 25)
        assert HT.in_window(t, HT.DEFAULTS)
        assert HT.session_phase(t) == "pre_open"

    def test_the_close_is_after_hours_in_both_regimes(self):
        assert HT.session_phase(_weekday_in(7, 20, 5)) == "after_hours"   # 16:05 EDT
        assert HT.session_phase(_weekday_in(1, 21, 5)) == "after_hours"   # 16:05 EST

    def test_the_weekend_is_never_in_the_window(self):
        day = NOW.date()
        sat = day + timedelta(days=(5 - day.weekday()) % 7 or 7)
        t = datetime(sat.year, sat.month, sat.day, 15, 0, tzinfo=timezone.utc)
        assert not HT.in_window(t, HT.DEFAULTS)
        assert HT.session_phase(t) == "after_hours"

    def test_the_grace_is_configurable_and_end_only(self):
        cfg = HT.load_config(None)
        cfg["window_grace_min"] = 0
        assert not HT.in_window(_weekday_in(7, 20, 10), cfg)
        # Grace never widens the OPEN side.
        cfg["window_grace_min"] = 60
        assert not HT.in_window(_weekday_in(7, 13, 20), cfg)


# ─────────────────────────────────────────────────────────────────────────────
# Config, freshness, bridge
# ─────────────────────────────────────────────────────────────────────────────

class TestConfigAndFreshness:
    def test_defaults_work_without_a_config_file(self, tmp_path):
        cfg = HT.load_config(tmp_path)
        assert cfg["detectors"]["mover"]["min_abs_pct"] == 4.0
        assert cfg["detectors"]["sector"]["industry_min_members"] == 5
        assert cfg["emit"]["account"] == "mastermind_news"

    def test_config_file_overrides_defaults(self, tmp_path):
        (tmp_path / "config").mkdir()
        (tmp_path / "config" / "hot_tape.yml").write_text(
            "detectors:\n  mover:\n    min_abs_pct: 6.5\n", encoding="utf-8")
        cfg = HT.load_config(tmp_path)
        assert cfg["detectors"]["mover"]["min_abs_pct"] == 6.5
        assert cfg["detectors"]["mover"]["cooldown_min"] == 120

    def test_quotes_fresh(self):
        live = {"quotes": {"AMD": _quote(-5.0)}, "asof": None}
        ok, age = HT.quotes_fresh(live, NOW, HT.DEFAULTS)
        assert ok and age is not None and age < 1
        stale = {"quotes": {"AMD": {"ts_ms": int((NOW - timedelta(minutes=60))
                                                 .timestamp() * 1000)}}, "asof": None}
        ok, age = HT.quotes_fresh(stale, NOW, HT.DEFAULTS)
        assert not ok and age > 12

    def test_quotes_fresh_accepts_a_bare_map(self):
        ok, _ = HT.quotes_fresh({"AMD": _quote(-5.0)}, NOW, HT.DEFAULTS)
        assert ok

    # ── the delay-aware ceiling (2026-07-29 zero-events diagnosis) ───────────
    #
    # A quote's ts is Yahoo's regularMarketTime, which is behind wall clock by
    # (how long since we looked) PLUS (the feed's contractual delay). Measured
    # 2026-07-30T03:46Z on symbols trading at that moment: 0700.HK 15.0m,
    # 0005.HK 15.1m, 9988.HK 15.1m, futures ~10m, BTC-USD/EURUSD=X 0.6-0.9m.
    # A 12-minute budget compared straight against that is unsatisfiable for
    # every equity on the only feed we have, however healthy the writer lane is.

    def test_effective_ceiling_is_the_bare_budget_when_no_delay_is_declared(self):
        assert HT.effective_max_quote_age_min(
            {"quotes": {}}, HT.DEFAULTS) == HT.DEFAULTS["max_quote_age_min"]
        assert HT.effective_max_quote_age_min(None, HT.DEFAULTS) == 12

    def test_effective_ceiling_allows_for_a_declared_feed_delay(self):
        view = {"quotes": {}, "feed_delay_min": 15.0}
        assert HT.effective_max_quote_age_min(view, HT.DEFAULTS) == 27.0

    def test_a_fresh_equity_on_a_delayed_feed_is_admitted(self):
        """The bug: a snapshot pushed one second ago still reads 15m old.

        Every US equity quote in a just-written snapshot carries ts = now - 15m.
        Against a bare 12m ceiling that is "stale", so the radar could never act
        on an equity — and the failure was invisible because the gate's min()
        passed on a real-time crypto tick while the per-quote drop silently binned
        every equity behind it.
        """
        equity_age_min = 15.05        # measured, not assumed
        view = {
            "quotes": {"MU": {"ts_ms": int(
                (NOW - timedelta(minutes=equity_age_min)).timestamp() * 1000)}},
            "asof": None,
            "feed_delay_min": 15.0,
        }
        ok, age = HT.quotes_fresh(view, NOW, HT.DEFAULTS)
        assert ok, f"a just-fetched equity at {age}m must clear a 12+15 ceiling"
        # …and the same quote is correctly REFUSED when the feed admits no delay.
        assert not HT.quotes_fresh(dict(view, feed_delay_min=0.0), NOW,
                                   HT.DEFAULTS)[0]

    def test_the_worst_observed_stale_merge_still_fails_the_ceiling(self):
        """Allowing for the declared delay must not forgive a stale WRITER lane.

        49.72m — run 30467377599 at 15:48Z, against a last successful live-quotes
        push of 14:58:23Z — was a genuinely stale feed and must still stand the
        pass down. If a widened ceiling ever admits it, the gate has stopped doing
        its job.

        The dark day's OTHER sampled age, 21.92m (run 30478516423 at 18:08Z, last
        push 17:46:53Z), is deliberately NOT asserted here: 21.92 is inside a
        12+15 ceiling and this layer is right to admit it. What made that pass
        undetectable was the equity book behind that freshest print — FX at 21.92m
        over equities stamped ~17:31, i.e. ~37m — and catching that is the radar's
        book-collapse gate, pinned in test_marketing_hot_tape_radar.py. One layer,
        one job.
        """
        view = {
            "quotes": {"MU": {"ts_ms": int(
                (NOW - timedelta(minutes=49.72)).timestamp() * 1000)}},
            "asof": None,
            "feed_delay_min": 15.0,
        }
        ok, age = HT.quotes_fresh(view, NOW, HT.DEFAULTS)
        assert not ok, (
            f"49.72m was a stale feed on 2026-07-29 and must stay refused "
            f"(reported {age}m)")

    def test_bridge_ok_is_true_for_the_previous_session(self):
        assert HT.bridge_ok(_pack({}, FRESH_TRADE_DATE), NOW)

    def test_bridge_ok_is_false_for_a_stale_store(self):
        """The live state on 2026-07-28: the store was 18 sessions behind."""
        assert not HT.bridge_ok(_pack({}, STALE_TRADE_DATE), NOW)
        assert not HT.bridge_ok(_pack({}, None), NOW)
        assert not HT.bridge_ok(None, NOW)


# ─────────────────────────────────────────────────────────────────────────────
# Detectors
# ─────────────────────────────────────────────────────────────────────────────

class TestSectorDetector:
    @staticmethod
    def _heatmap(tiles):
        return {"asof": FRESH_TRADE_DATE, "tiles": tiles}

    def test_sector_rout_fires_once(self):
        tiles = [_tile(f"S{i}", "Technology", -3.0, industry="Sub") for i in range(10)]
        events = HT.detect_events({}, pack=_pack({}, FRESH_TRADE_DATE),
                                  heatmap=self._heatmap(tiles), now=NOW,
                                  cfg=HT.DEFAULTS)
        routs = [e for e in events if e.trigger == "sector_rout"]
        assert len(routs) == 1
        packet = routs[0]
        assert packet.facts["n_members"] == 10
        assert packet.facts["breadth_pct"] == 100.0
        assert packet.severity == 86.0
        assert packet.key.endswith(NOW.date().isoformat())

    def test_below_threshold_does_not_fire(self):
        tiles = [_tile(f"S{i}", "Technology", -1.0) for i in range(10)]
        assert HT.detect_events({}, heatmap=self._heatmap(tiles), now=NOW,
                                cfg=HT.DEFAULTS) == []

    def test_breadth_gate_blocks_a_lopsided_group(self):
        tiles = ([_tile(f"D{i}", "Technology", -6.0) for i in range(5)]
                 + [_tile(f"U{i}", "Technology", 0.5) for i in range(5)])
        events = HT.detect_events({}, heatmap=self._heatmap(tiles), now=NOW,
                                  cfg=HT.DEFAULTS)
        assert [e for e in events if e.trigger.startswith("sector_")] == []

    def test_min_members_gate(self):
        tiles = [_tile(f"S{i}", "Technology", -4.0, industry="Tiny") for i in range(4)]
        events = HT.detect_events({}, heatmap=self._heatmap(tiles), now=NOW,
                                  cfg=HT.DEFAULTS)
        assert [e for e in events if e.trigger.startswith("sector_")] == []

    def test_industry_fires_when_the_parent_sector_is_masked(self):
        """2026-07-28's real tape: Semiconductors -8% inside a green Technology."""
        tiles = ([_tile(f"SEMI{i}", "Technology", -8.0, industry="Semiconductors")
                  for i in range(6)]
                 + [_tile(f"SW{i}", "Technology", 0.5,
                          industry="Software - Infrastructure") for i in range(8)])
        events = HT.detect_events({}, heatmap=self._heatmap(tiles), now=NOW,
                                  cfg=HT.DEFAULTS)
        groups = [e for e in events if e.trigger.startswith("sector_")]
        assert len(groups) == 1
        assert groups[0].facts["group_kind"] == "industry"
        assert groups[0].sector == "Semiconductors"
        assert groups[0].facts["n_members"] == 6

    def test_the_more_extreme_of_an_overlapping_pair_wins(self):
        tiles = ([_tile(f"SEMI{i}", "Technology", -9.0, industry="Semiconductors")
                  for i in range(6)]
                 + [_tile(f"SW{i}", "Technology", -2.2,
                          industry="Software - Infrastructure") for i in range(9)])
        events = HT.detect_events({}, heatmap=self._heatmap(tiles), now=NOW,
                                  cfg=HT.DEFAULTS)
        groups = [e for e in events if e.trigger.startswith("sector_")]
        # Semiconductors (-9.0) beats its parent Technology (-2.2); the software
        # industry ties its parent and yields to it, and the parent is gone.
        assert [g.sector for g in groups] == ["Semiconductors"]

    def test_live_quotes_win_over_stale_tile_percentages(self):
        tiles = [_tile(f"S{i}", "Technology", 0.1) for i in range(10)]
        quotes = {f"S{i}": _quote(-3.0) for i in range(10)}
        events = HT.detect_events(quotes, heatmap=self._heatmap(tiles), now=NOW,
                                  cfg=HT.DEFAULTS)
        assert [e for e in events if e.trigger == "sector_rout"]

    def test_once_per_sector_per_direction_per_day(self):
        tiles = [_tile(f"S{i}", "Technology", -3.0, industry="Sub") for i in range(10)]
        day = NOW.date().isoformat()
        fired = [{"key": f"sector:Technology:down:{day}"},
                 {"key": f"sector:Sub:down:{day}"}]
        events = HT.detect_events({}, heatmap=self._heatmap(tiles),
                                  fired_today=fired, now=NOW, cfg=HT.DEFAULTS)
        assert [e for e in events if e.trigger.startswith("sector_")] == []

    def test_dollar_translation_needs_EVERY_members_cap(self, capsys):
        """2026-07-31: the coverage floor was 70%, so the sum lost members.

        Eight of ten caps cleared the old gate and the group shipped a total
        computed over eight names as if it were the group's. The claim the copy
        makes ("roughly $X billion in fresh market value") is about the GROUP,
        so anything less than every member is a different number wearing the
        same sentence.
        """
        tiles = [_tile(f"S{i}", "Technology", -3.0, industry="Sub") for i in range(10)]
        recs = {f"S{i}": _rec(mcap_usd=100_000_000_000) for i in range(8)}
        events = HT.detect_events({}, pack=_pack(recs, FRESH_TRADE_DATE),
                                  heatmap=self._heatmap(tiles), now=NOW,
                                  cfg=HT.DEFAULTS)
        rout = [e for e in events if e.trigger == "sector_rout"][0]
        # PRE-FIX this was round(8 * 100e9 * -0.03) = -$24B, a group total with
        # two members quietly missing from it.
        assert rout.facts["dollar_moved_usd"] is None
        assert rout.facts["dollar_missing_caps"] == 2
        # ... and the loss is on the console, line-start so GitHub keeps it.
        line = [ln for ln in capsys.readouterr().out.splitlines()
                if "hot-tape-group-dollars-dropped" in ln]
        assert line and line[0].startswith("::warning title=")
        assert "2 of 10 members have no mcap_usd" in line[0]

        thin = {f"S{i}": _rec(mcap_usd=100_000_000_000) for i in range(5)}
        events = HT.detect_events({}, pack=_pack(thin, FRESH_TRADE_DATE),
                                  heatmap=self._heatmap(tiles), now=NOW,
                                  cfg=HT.DEFAULTS)
        rout = [e for e in events if e.trigger == "sector_rout"][0]
        assert rout.facts["dollar_moved_usd"] is None
        assert rout.facts["dollar_missing_caps"] == 5

    def test_two_passes_over_one_group_cannot_grow_the_median_and_shrink_the_dollars(self):
        """The shipped contradiction, reproduced: same group, same names, same
        session — 15:27 "median +11.8% ... roughly $148 billion in fresh market
        value", 19:03 "median +13.4% ... roughly $135 billion". With a pinned
        cap base a bigger move CANNOT be a smaller dollar figure; the only way
        to print that pair is to sum over a silently smaller membership.
        """
        tiles_a = [_tile(f"S{i}", "Technology", 3.0, industry="Sub") for i in range(10)]
        tiles_b = [_tile(f"S{i}", "Technology", 4.0, industry="Sub") for i in range(10)]
        full = {f"S{i}": _rec(mcap_usd=100_000_000_000) for i in range(10)}
        # The second pass loses three caps — 70% coverage, which is exactly what
        # the old gate admitted.
        thinned = {f"S{i}": _rec(mcap_usd=100_000_000_000) for i in range(7)}

        def _rip(tiles, recs):
            events = HT.detect_events({}, pack=_pack(recs, FRESH_TRADE_DATE),
                                      heatmap=self._heatmap(tiles), now=NOW,
                                      cfg=HT.DEFAULTS)
            return [e for e in events if e.trigger == "sector_rip"][0]

        first, second = _rip(tiles_a, full), _rip(tiles_b, thinned)
        assert second.facts["median_pct"] > first.facts["median_pct"]
        # PRE-FIX: 7 * 100e9 * 0.04 = $280B against the first pass's $300B — a
        # bigger median with a smaller total, on the same ten names.
        assert first.facts["dollar_moved_usd"] == round(10 * 100_000_000_000 * 0.03)
        assert second.facts["dollar_moved_usd"] is None
        # The invariant itself, stated: two comparable claims can never invert.
        if second.facts["dollar_moved_usd"] is not None:
            assert (second.facts["dollar_moved_usd"]
                    >= first.facts["dollar_moved_usd"])

    def test_a_dollar_total_whose_sign_fights_the_direction_is_withheld(self):
        """M8 — the trigger is a MEDIAN, the total is CAP-WEIGHTED.

        One green mega-cap flips the aggregate positive inside a group the
        median calls a rout, and "$130 billion gone" rendered off a +$130B
        number is a lie with a minus sign glued on.
        """
        # Letters-only tickers: the wire's cashtag regex stops at the first
        # digit, so a `$S0` would leave a bare "0" for the numeric gate.
        syms = [f"SM{c}" for c in "ABCDEFGHI"]
        tiles = ([_tile(s, "Technology", -3.0, industry="Sub") for s in syms]
                 + [_tile("MEGA", "Technology", 2.0, industry="Sub")])
        recs = {s: _rec(mcap_usd=100_000_000_000) for s in syms}
        recs["MEGA"] = _rec(mcap_usd=20_000_000_000_000)
        events = HT.detect_events({}, pack=_pack(recs, FRESH_TRADE_DATE),
                                  heatmap=self._heatmap(tiles), now=NOW,
                                  cfg=HT.DEFAULTS)
        rout = [e for e in events if e.trigger == "sector_rout"][0]
        assert rout.facts["median_pct"] == -3.0
        assert rout.facts["dollar_moved_usd"] is None
        # The post still ships: the copy falls back to the leaders device.
        out = W.compose_wire(rout)
        assert out is not None
        assert "dollar_clause" not in out["devices"]
        assert "leaders_clause" in out["devices"]

    def test_a_dollar_total_that_agrees_with_the_direction_survives(self):
        tiles = [_tile(f"S{i}", "Technology", -3.0, industry="Sub") for i in range(10)]
        recs = {f"S{i}": _rec(mcap_usd=100_000_000_000) for i in range(10)}
        events = HT.detect_events({}, pack=_pack(recs, FRESH_TRADE_DATE),
                                  heatmap=self._heatmap(tiles), now=NOW,
                                  cfg=HT.DEFAULTS)
        rout = [e for e in events if e.trigger == "sector_rout"][0]
        assert rout.facts["dollar_moved_usd"] < 0

    def test_demo_mode_lowers_the_bar_and_is_stamped(self):
        tiles = [_tile(f"S{i}", "Technology", -0.8, industry="Sub") for i in range(10)]
        events = HT.detect_events({}, heatmap=self._heatmap(tiles), now=NOW,
                                  cfg=HT.DEFAULTS, demo=True)
        routs = [e for e in events if e.trigger == "sector_rout"]
        assert routs and routs[0].provenance["demo"] is True


class TestMoverDetector:
    @staticmethod
    def _inputs(pct, rec_over=None, trade_date=FRESH_TRADE_DATE):
        recs = {"AMD": _rec(**(rec_over or {}))}
        quotes = {"AMD": _quote(pct, price=84.2, prev=91.65)}
        return quotes, _pack(recs, trade_date)

    @classmethod
    def _movers(cls, pct, rec_over=None, trade_date=FRESH_TRADE_DATE, **kw):
        """Mover packets only — the same fixture legitimately fires streak_rarity."""
        quotes, pack = cls._inputs(pct, rec_over, trade_date)
        events = HT.detect_events(quotes, pack=pack, now=NOW, cfg=HT.DEFAULTS, **kw)
        return [e for e in events if e.trigger.startswith("mover_")]

    def test_fires_above_the_threshold(self):
        quotes, pack = self._inputs(-8.13)
        events = HT.detect_events(quotes, pack=pack, now=NOW, cfg=HT.DEFAULTS)
        movers = [e for e in events if e.trigger == "mover_drop"]
        assert len(movers) == 1
        packet = movers[0]
        assert packet.facts["pct"] == -8.13
        assert packet.facts["dollar_delta_usd"] == round(300_000_000_000 * -0.0813)
        assert packet.key.endswith(":0")

    def test_does_not_fire_below_the_threshold(self):
        assert self._movers(-3.5) == []

    def test_severity_boosts(self):
        packet = self._movers(-8.0)[0]
        assert packet.severity == 100.0        # 50 + 20 base, +10 sp500/rank/mcap
        packet = self._movers(
            -8.0, {"sp500": False, "adv_rank": 250, "mcap_usd": 2_000_000_000})[0]
        assert packet.severity == 70.0

    def test_two_hour_cooldown_suppresses_a_repeat(self):
        fired = [{"key": "mover:AMD:down:x:0", "trigger": "mover_drop",
                  "ticker": "AMD", "direction": "down", "magnitude": -8.0,
                  "fired_at": (NOW - timedelta(minutes=30))
                  .strftime("%Y-%m-%dT%H:%M:%SZ")}]
        assert self._movers(-8.5, fired_today=fired) == []

    def test_a_doubled_move_re_fires_inside_the_cooldown(self):
        fired = [{"key": "mover:AMD:down:x:0", "trigger": "mover_drop",
                  "ticker": "AMD", "direction": "down", "magnitude": -8.0,
                  "fired_at": (NOW - timedelta(minutes=30))
                  .strftime("%Y-%m-%dT%H:%M:%SZ")}]
        events = self._movers(-16.5, fired_today=fired)
        assert len(events) == 1
        assert events[0].key.endswith(":1")

    def test_the_cooldown_expires(self):
        fired = [{"key": "mover:AMD:down:x:0", "trigger": "mover_drop",
                  "ticker": "AMD", "direction": "down", "magnitude": -8.0,
                  "fired_at": (NOW - timedelta(minutes=121))
                  .strftime("%Y-%m-%dT%H:%M:%SZ")}]
        assert len(self._movers(-8.5, fired_today=fired)) == 1

    def test_the_opposite_direction_is_not_cooled_down(self):
        quotes, pack = self._inputs(8.5)
        fired = [{"key": "mover:AMD:down:x:0", "trigger": "mover_drop",
                  "ticker": "AMD", "direction": "down", "magnitude": -8.0,
                  "fired_at": NOW.strftime("%Y-%m-%dT%H:%M:%SZ")}]
        events = HT.detect_events(quotes, pack=pack, fired_today=fired, now=NOW,
                                  cfg=HT.DEFAULTS)
        assert [e.trigger for e in events if e.trigger.startswith("mover")] \
            == ["mover_pop"]

    def test_history_facts_are_suppressed_when_the_bridge_is_down(self):
        """Live behaviour, not theory: the store really is sessions behind."""
        quotes, pack = self._inputs(-8.13, trade_date=STALE_TRADE_DATE)
        packet = [e for e in HT.detect_events(quotes, pack=pack, now=NOW,
                                              cfg=HT.DEFAULTS)
                  if e.trigger == "mover_drop"][0]
        for field in ("streak_extends", "biggest_1d", "ath", "ath_date",
                      "pct_from_ath_live", "rsi_live", "rsi_since"):
            assert packet.facts[field] is None, field
        assert packet.provenance["bridge_ok"] is False
        # The dollar translation survives: mcap needs no price history.
        assert packet.facts["dollar_delta_usd"] is not None
        out = W.compose_wire(packet)
        assert out is not None and out["devices"] == ["dollar_clause", "live_marker"]

    def test_history_facts_are_suppressed_for_a_split_suspect(self):
        quotes, pack = self._inputs(-8.13, {"suspect": True})
        packet = [e for e in HT.detect_events(quotes, pack=pack, now=NOW,
                                              cfg=HT.DEFAULTS)
                  if e.trigger == "mover_drop"][0]
        assert packet.facts["streak_extends"] is None
        assert packet.facts["biggest_1d"] is None
        assert packet.facts["ath"] is None

    def test_history_facts_are_present_when_bridged(self):
        quotes, pack = self._inputs(-8.13)
        packet = [e for e in HT.detect_events(quotes, pack=pack, now=NOW,
                                              cfg=HT.DEFAULTS)
                  if e.trigger == "mover_drop"][0]
        assert packet.facts["streak_extends"]["len_today"] == 9
        assert packet.facts["streak_extends"]["since"] == _ago(NOW, 1500)
        assert packet.facts["biggest_1d"]["prior_pct"] == -7.4
        assert packet.facts["ath"] == 140.0
        assert packet.facts["ath_date"] == _ago(NOW, 50)
        assert packet.facts["pct_from_ath_live"] == round((84.2 - 140.0) / 140.0 * 100, 2)
        assert packet.facts["rsi_live"] is not None

    def test_rsi_band_facts_appear_only_when_the_band_is_crossed(self):
        quotes, pack = self._inputs(-8.13, {"rsi_avg_gain": 0.2, "rsi_avg_loss": 3.0})
        packet = [e for e in HT.detect_events(quotes, pack=pack, now=NOW,
                                              cfg=HT.DEFAULTS)
                  if e.trigger == "mover_drop"][0]
        assert packet.facts["rsi_live"] < 30
        assert packet.facts["rsi_band"] == 30
        assert packet.facts["rsi_since"] == _ago(NOW, 500)

    def test_a_down_mover_still_above_70_gets_no_rsi_band(self):
        """C2, reproduced on the real tape: RSI 78 -> 75.3 on a red day.

        The old test was "rsi_live is past the band", which is a STATE. A name
        selling off from 78 to 75.3 never left the band, so there is nothing to
        be "back" on either side of — and the clause took its side from the
        DIRECTION, so it rendered "RSI is back under 70" at an RSI of 75.3.
        """
        packet = self._movers(-8.13, {"rsi14": 78.0, "rsi_avg_gain": 3.705,
                                      "rsi_avg_loss": 0.0})[0]
        assert packet.facts["rsi_live"] == 75.3      # the honest live number stays
        assert packet.facts["rsi_band"] is None
        assert packet.facts["rsi_since"] is None
        assert W._since_clause(packet, packet.facts) is None

    def test_an_up_mover_below_70_gets_no_rsi_band(self):
        """The mirror: rising into 68 has not crossed 70 either."""
        packet = self._movers(8.13, {"rsi14": 55.0, "rsi_avg_gain": 3.0,
                                     "rsi_avg_loss": 1.0})[0]
        assert packet.facts["rsi_live"] is not None
        if packet.facts["rsi_live"] < 70:
            assert packet.facts["rsi_band"] is None

    def test_a_band_fact_needs_yesterday_on_the_other_side(self):
        """Crossing is a two-day claim: today under 30, yesterday above it."""
        already = self._movers(-8.13, {"rsi14": 22.0, "rsi_avg_gain": 0.2,
                                       "rsi_avg_loss": 3.0})[0]
        assert already.facts["rsi_live"] < 30      # today is oversold …
        assert already.facts["rsi_band"] is None   # … and so was yesterday

    def test_demo_threshold(self):
        assert self._movers(-2.0) == []
        assert self._movers(-2.0, demo=True)

    def test_a_record_lagging_the_pack_tip_gets_no_history(self):
        """M1 — the bridge is GLOBAL; a stale RECORD needs its own gate.

        The shipped pack carried 26 live-quoted records behind its own tip, one
        of them a "5-day streak" that had ended six sessions earlier. bridge_ok
        was perfectly True for all of them.
        """
        lagging = _prev_weekday(_prev_weekday(_prev_weekday(
            date.fromisoformat(FRESH_TRADE_DATE)))).isoformat()
        recs = {"AMD": _rec(), "OLD": _rec(last_date=lagging)}
        quotes = {"AMD": _quote(-8.13, price=84.2, prev=91.65),
                  "OLD": _quote(-8.13, price=84.2, prev=91.65)}
        packets = {e.ticker: e for e in
                   HT.detect_events(quotes, pack=_pack(recs, FRESH_TRADE_DATE),
                                    now=NOW, cfg=HT.DEFAULTS)
                   if e.trigger == "mover_drop"}
        assert set(packets) == {"AMD", "OLD"}
        assert packets["AMD"].facts["streak_extends"]["len_today"] == 9
        assert packets["AMD"].facts["ath"] == 140.0
        for field in ("streak_extends", "biggest_1d", "ath", "ath_date",
                      "pct_from_ath_live", "rsi_live", "rsi_band", "rsi_since"):
            assert packets["OLD"].facts[field] is None, field
        # The dollar translation survives: mcap needs no price history.
        assert packets["OLD"].facts["dollar_delta_usd"] is not None

    def test_severity_ties_break_on_magnitude_not_the_alphabet(self):
        """M2 — the mover formula saturates at 100 well before the tape does.

        SNDK -14.25, GLW -12.10 and AMD -8.15 all scored exactly 100 on the
        2026-07-28 tape; an alphabetical tie-break then handed the three-item
        run cap to AMD and dropped the biggest move of the day.
        """
        pcts = {"AMD": -8.15, "GLW": -12.10, "SNDK": -14.25}
        recs = {sym: _rec() for sym in pcts}
        quotes = {sym: _quote(pct, price=84.2, prev=91.65) for sym, pct in pcts.items()}
        movers = [e for e in HT.detect_events(quotes, pack=_pack(recs, FRESH_TRADE_DATE),
                                              now=NOW, cfg=HT.DEFAULTS)
                  if e.trigger == "mover_drop"]
        assert {e.severity for e in movers} == {100.0}
        assert [e.ticker for e in movers] == ["SNDK", "GLW", "AMD"]

    def test_illiquid_names_are_outside_the_universe(self):
        recs = {"TINY": _rec(adv_rank=4000, sp500=False, sector=None)}
        quotes = {"TINY": _quote(-9.0)}
        events = HT.detect_events(quotes, pack=_pack(recs, FRESH_TRADE_DATE),
                                  now=NOW, cfg=HT.DEFAULTS)
        assert [e for e in events if e.trigger.startswith("mover")] == []


class TestThresholdDetector:
    @staticmethod
    def _run(price, prev, rec_over=None, trade_date=FRESH_TRADE_DATE):
        recs = {"AMD": _rec(**(rec_over or {}))}
        quotes = {"AMD": {"price": price, "prev_close": prev,
                          "change_pct": round((price - prev) / prev * 100, 2),
                          "ts_ms": int(NOW.timestamp() * 1000), "source": "quotes"}}
        return [e for e in HT.detect_events(quotes, pack=_pack(recs, trade_date),
                                            now=NOW, cfg=HT.DEFAULTS)
                if e.trigger == "threshold_cross"]

    def test_correction_cross_fires(self):
        events = self._run(125.0, 127.0)
        kinds = {e.facts["kind"] for e in events}
        assert "correction" in kinds
        packet = [e for e in events if e.facts["kind"] == "correction"][0]
        assert packet.facts["threshold_px"] == 126.0
        assert packet.facts["ath"] == 140.0
        assert packet.direction == "down"

    def test_correction_requires_the_bridge(self):
        events = self._run(125.0, 127.0, trade_date=STALE_TRADE_DATE)
        assert "correction" not in {e.facts["kind"] for e in events}

    def test_bear_cross_fires(self):
        events = self._run(111.0, 113.0)
        assert "bear" in {e.facts["kind"] for e in events}

    def test_new_ath_fires_and_needs_the_bridge(self):
        events = self._run(141.0, 139.0)
        assert "ath" in {e.facts["kind"] for e in events}
        stale = self._run(141.0, 139.0, trade_date=STALE_TRADE_DATE)
        assert "ath" not in {e.facts["kind"] for e in stale}

    def test_round_number_cross_both_ways_without_the_bridge(self):
        up = self._run(111.0, 109.0, trade_date=STALE_TRADE_DATE)
        rounds = [e for e in up if e.facts["kind"] == "round"]
        assert rounds and rounds[0].facts["level"] == 110.0
        assert rounds[0].direction == "up"
        down = self._run(99.0, 101.0, trade_date=STALE_TRADE_DATE)
        rounds = [e for e in down if e.facts["kind"] == "round"]
        assert rounds and rounds[0].facts["level"] == 100.0
        assert rounds[0].direction == "down"

    def test_a_round_cross_stays_under_the_flagship_floor(self):
        """M2 — a round number is arithmetic, not tape.

        At base 70 a mega-cap round cross scored 90 and OUTRANKED a real rout
        for the single flagship mirror ("$LLY cleared $1,200"). Base 60 caps the
        same event at 80, below the 85 floor, while it still ships on the wire.
        """
        events = self._run(111.0, 109.0, {"sp500": True, "mcap_usd": 800_000_000_000})
        rounds = [e for e in events if e.facts["kind"] == "round"]
        assert len(rounds) == 1
        assert rounds[0].severity == 80.0
        assert rounds[0].severity < HT.DEFAULTS["emit"]["flagship_severity_floor"]
        assert HT.severity_account(rounds[0], HT.DEFAULTS) == "mastermind_news"

    def test_a_real_threshold_keeps_its_weight(self):
        """Only `round` was demoted: correction/bear/ath/mcap stay at base 70."""
        events = self._run(125.0, 127.0, {"sp500": True,
                                          "mcap_usd": 800_000_000_000})
        correction = [e for e in events if e.facts["kind"] == "correction"][0]
        assert correction.severity == 90.0

    def test_mcap_milestones_die_without_shares_est(self):
        """C1 — the pack withholds shares_est unless mcap and close agree on a date."""
        events = self._run(170.0, 160.0, {"shares_est": None, "ath": 500.0,
                                          "px_correction": 450.0, "px_bear": 400.0,
                                          "round_above": 200.0, "round_below": 150.0})
        assert [e for e in events if e.facts["kind"] == "mcap"] == []

    def test_a_lagging_record_gets_no_history_threshold(self):
        """M1 again, on the threshold lane: correction needs a CURRENT record."""
        lagging = _prev_weekday(_prev_weekday(_prev_weekday(
            date.fromisoformat(FRESH_TRADE_DATE)))).isoformat()
        events = self._run(125.0, 127.0, {"last_date": lagging})
        assert "correction" not in {e.facts["kind"] for e in events}

    def test_round_number_respects_the_price_floor(self):
        events = self._run(11.0, 9.0, {"round_above": 10.0, "round_below": 5.0,
                                       "ath": 140.0})
        assert [e for e in events if e.facts["kind"] == "round"] == []

    def test_mcap_milestone_crosses(self):
        events = self._run(170.0, 160.0, {"shares_est": 3_000_000_000,
                                          "ath": 500.0, "px_correction": 450.0,
                                          "px_bear": 400.0, "round_above": 200.0,
                                          "round_below": 150.0})
        mcaps = [e for e in events if e.facts["kind"] == "mcap"]
        assert mcaps and mcaps[0].facts["milestone_usd"] == int(5e11)
        assert mcaps[0].direction == "up"

    def test_once_per_day_per_kind(self):
        day = NOW.date().isoformat()
        recs = {"AMD": _rec()}
        quotes = {"AMD": {"price": 125.0, "prev_close": 127.0, "change_pct": -1.57,
                          "ts_ms": int(NOW.timestamp() * 1000), "source": "quotes"}}
        fired = [{"key": f"threshold:AMD:correction:126.0:{day}"}]
        events = [e for e in HT.detect_events(quotes, pack=_pack(recs, FRESH_TRADE_DATE),
                                              fired_today=fired, now=NOW,
                                              cfg=HT.DEFAULTS)
                  if e.trigger == "threshold_cross"]
        assert "correction" not in {e.facts["kind"] for e in events}


class TestThresholdFreshness:
    """2026-07-29, the gap day: '$AAPL right now: just broke below $325.00'
    booked at 16:00:27Z on a level the tape crossed at the opening gap, in the
    same sweep that had the name 11% below its all-time high (~$302 against a
    $325 'break'). The crossing test is prev_close vs the live price, so it is
    true all session; 'just' is a claim about TIME and needs the prior tick.
    """

    # AAPL's real shape that day: gapped ~9% down through the $325 round level
    # at the open and sat well below it for the rest of the session.
    PREV, PRICE, LEVEL = 350.0, 302.0, 325.0

    @classmethod
    def _run(cls, *, ring, now=None, price=None, cfg=None):
        recs = {"AAPL": _rec(round_above=cls.LEVEL, round_below=250.0,
                             ath=340.0, px_correction=None, px_bear=None,
                             mcap_usd=3_000_000_000_000, sp500=True,
                             shares_est=None)}
        px = cls.PRICE if price is None else price
        quotes = {"AAPL": {"price": px, "prev_close": cls.PREV,
                           "change_pct": round((px - cls.PREV) / cls.PREV * 100, 2),
                           "ts_ms": int(NOW.timestamp() * 1000), "source": "quotes"}}
        events = HT.detect_events(quotes, pack=_pack(recs, FRESH_TRADE_DATE),
                                  ring=ring, now=now or NOW,
                                  cfg=cfg or HT.DEFAULTS)
        rounds = [e for e in events
                  if e.trigger == "threshold_cross" and e.facts["kind"] == "round"]
        assert len(rounds) == 1, [e.facts["kind"] for e in events]
        return rounds[0]

    @classmethod
    def _ring_row(cls, *, minutes_ago: float, ids, complete=True, min_sev=80.0,
                  day=None):
        at = NOW - timedelta(minutes=minutes_ago)
        return {"at": at.strftime("%Y-%m-%dT%H:%M:%SZ"),
                "day": day or NOW.date().isoformat(),
                HT.RING_CROSS_IDS: list(ids),
                HT.RING_CROSS_COMPLETE: complete,
                HT.RING_CROSS_MIN_SEV: min_sev}

    def test_a_level_crossed_at_the_open_cannot_say_just_broke_hours_later(self):
        """THE SHIPPED DEFECT. The prior tick already had the crossing."""
        cross_id = f"AAPL:round:{self.LEVEL}"
        packet = self._run(ring=[self._ring_row(minutes_ago=305, ids=[cross_id]),
                                 self._ring_row(minutes_ago=5, ids=[cross_id])])
        assert packet.facts["cross_basis"] == HT.CROSS_EARLIER
        assert packet.facts["crossed_in_window"] is False
        out = W.compose_wire(packet)
        assert out is not None
        assert "just broke" not in out["text"], out["text"]
        assert "trades below $325.00" in out["text"], out["text"]

    def test_a_crossing_absent_from_the_prior_tick_is_fresh(self):
        packet = self._run(ring=[self._ring_row(minutes_ago=5, ids=[])])
        assert packet.facts["cross_basis"] == HT.CROSS_FIRST_SEEN
        assert packet.facts["crossed_in_window"] is True
        out = W.compose_wire(packet)
        assert out is not None and "just broke below $325.00" in out["text"]

    def test_no_ring_means_unknown_means_the_standing_phrasing(self):
        packet = self._run(ring=[])
        assert packet.facts["cross_basis"] == HT.CROSS_UNKNOWN
        assert "just broke" not in (W.compose_wire(packet) or {"text": ""})["text"]

    def test_a_gap_in_the_ring_is_not_evidence_of_a_fresh_break(self):
        """A missed cron would otherwise turn every hours-old level into news:
        the crossing is absent from a row that is 40 minutes stale, which says
        nothing about the last five minutes."""
        packet = self._run(ring=[self._ring_row(minutes_ago=40, ids=[])])
        assert packet.facts["cross_basis"] == HT.CROSS_UNKNOWN
        assert packet.facts["crossed_in_window"] is False

    def test_an_incomplete_memory_is_not_evidence_either(self):
        """xk is capped; a truncated list is missing crossings it DID see."""
        packet = self._run(ring=[self._ring_row(minutes_ago=5, ids=[],
                                                complete=False)])
        assert packet.facts["cross_basis"] == HT.CROSS_UNKNOWN

    def test_yesterdays_ring_is_not_this_sessions_prior_tick(self):
        stale_day = (NOW.date() - timedelta(days=1)).isoformat()
        packet = self._run(ring=[self._ring_row(minutes_ago=5, ids=[],
                                                day=stale_day)])
        assert packet.facts["cross_basis"] == HT.CROSS_UNKNOWN

    def test_a_crossing_under_the_rows_severity_floor_is_unknown(self):
        """The memory is complete AT OR ABOVE its own floor and says nothing
        below it, so a cheap crossing cannot read its own absence as news."""
        recs = {"MID": _rec(round_above=110.0, round_below=100.0, ath=140.0,
                            px_correction=None, px_bear=None, sp500=False,
                            mcap_usd=20_000_000_000, shares_est=None)}
        quotes = {"MID": {"price": 111.0, "prev_close": 109.0, "change_pct": 1.83,
                          "ts_ms": int(NOW.timestamp() * 1000), "source": "quotes"}}
        ring = [self._ring_row(minutes_ago=5, ids=[], min_sev=80.0)]
        events = [e for e in HT.detect_events(quotes, pack=_pack(recs, FRESH_TRADE_DATE),
                                              ring=ring, now=NOW, cfg=HT.DEFAULTS)
                  if e.trigger == "threshold_cross"]
        assert events and events[0].severity == 60.0
        assert events[0].facts["cross_basis"] == HT.CROSS_UNKNOWN

    def test_the_ring_row_this_pass_writes_is_what_the_next_pass_reads(self):
        """The two halves of the contract, wired together."""
        fresh = self._run(ring=[self._ring_row(minutes_ago=5, ids=[])])
        row = HT.cross_memory_row([fresh], HT.DEFAULTS)
        assert row[HT.RING_CROSS_IDS] == [f"AAPL:round:{self.LEVEL}"]
        assert row[HT.RING_CROSS_COMPLETE] is True
        assert row[HT.RING_CROSS_MIN_SEV] == 80.0
        row["at"] = (NOW - timedelta(minutes=5)).strftime("%Y-%m-%dT%H:%M:%SZ")
        row["day"] = NOW.date().isoformat()
        again = self._run(ring=[row])
        assert again.facts["cross_basis"] == HT.CROSS_EARLIER

    def test_the_memory_drops_crossings_under_the_floor_and_is_still_complete(self):
        cheap = _packet("threshold_cross", "threshold:MID:round:110.0:x", "up",
                        {"cross_id": "MID:round:110.0"}, severity=60.0)
        rich = _packet("threshold_cross", "threshold:AAPL:round:325.0:x", "down",
                       {"cross_id": "AAPL:round:325.0"}, severity=80.0)
        row = HT.cross_memory_row([cheap, rich], HT.DEFAULTS)
        assert row[HT.RING_CROSS_IDS] == ["AAPL:round:325.0"]
        assert row[HT.RING_CROSS_COMPLETE] is True

    def test_a_truncated_memory_marks_itself_incomplete(self):
        cfg = HT._deep_merge(HT.DEFAULTS, {
            "detectors": {"threshold": {"cross_memory_max_ids": 2}}})
        packets = [_packet("threshold_cross", f"threshold:S{i}:round:1.0:x", "up",
                           {"cross_id": f"S{i}:round:1.0"}, severity=90.0)
                   for i in range(4)]
        row = HT.cross_memory_row(packets, cfg)
        assert len(row[HT.RING_CROSS_IDS]) == 2
        assert row[HT.RING_CROSS_COMPLETE] is False

    def test_the_standing_form_covers_every_kind_that_can_claim_freshness(self):
        """One gate, all five milestone shapes — a kind that kept its event
        verb would ship the same lie in a different sentence."""
        base = {"ticker": "X", "price": 100.0, "prev_close": 110.0,
                "pct_from_ath_live": -12.0, "ath": 140.0,
                "ath_date": _ago(NOW, 50), "crossed_in_window": False}
        for kind, extra in (("round", {"level": 100.0}),
                            ("correction", {}),
                            ("ath", {}),
                            ("mcap", {"milestone_usd": int(1e12)})):
            packet = _packet("threshold_cross", f"threshold:X:{kind}:1:x", "down",
                             {**base, "kind": kind, **extra}, ticker="X")
            clause = W._milestone_clause(packet, packet.facts)
            assert clause and not clause.startswith("just"), (kind, clause)
            assert "enters correction" not in clause, (kind, clause)


class TestStreakDetector:
    @staticmethod
    def _run(pct, rec_over=None, trade_date=FRESH_TRADE_DATE):
        recs = {"META": _rec(**(rec_over or {}))}
        quotes = {"META": _quote(pct)}
        return [e for e in HT.detect_events(quotes, pack=_pack(recs, trade_date),
                                            now=NOW, cfg=HT.DEFAULTS)
                if e.trigger == "streak_rarity"]

    def test_fires_when_today_extends_a_rare_run(self):
        events = self._run(-2.1)
        assert len(events) == 1
        assert events[0].facts["len_today"] == 9
        assert events[0].facts["since"] == _ago(NOW, 1500)
        assert events[0].severity == 95.0

    def test_requires_the_bridge(self):
        assert self._run(-2.1, trade_date=STALE_TRADE_DATE) == []

    def test_requires_rarity(self):
        recent = {"streak": {"dir": "down", "len": 8,
                             "last_run_ge": {"9": _ago(NOW, 100)}}}
        assert self._run(-2.1, recent) == []

    def test_a_null_prior_run_is_rare_enough(self):
        never = {"streak": {"dir": "down", "len": 8, "last_run_ge": {"9": None}}}
        assert len(self._run(-2.1, never)) == 1

    def test_requires_the_live_sign_to_match(self):
        assert self._run(2.1) == []

    def test_requires_the_minimum_length(self):
        short_run = {"streak": {"dir": "down", "len": 2,
                                "last_run_ge": {"3": None}}}
        assert self._run(-2.1, short_run) == []

    def test_a_split_suspect_is_skipped(self):
        assert self._run(-2.1, {"suspect": True}) == []


class TestSignalDetector:
    @staticmethod
    def _run(price, prev, entry=310.5, direction="BULL", as_of_days=1, fired=None):
        quotes = {"MSFT": {"price": price, "prev_close": prev,
                           "change_pct": round((price - prev) / prev * 100, 2),
                           "ts_ms": int(NOW.timestamp() * 1000), "source": "quotes"}}
        signals = [{"ticker": "MSFT", "entry": entry, "direction": direction,
                    "signal_id": "sig-1", "as_of": _ago(NOW, as_of_days)}]
        return [e for e in HT.detect_events(quotes, pack=_pack({"MSFT": _rec()},
                                                              FRESH_TRADE_DATE),
                                            plan_signals=signals,
                                            fired_today=fired or [], now=NOW,
                                            cfg=HT.DEFAULTS)
                if e.trigger == "signal_fired"]

    def test_bull_gap_over_fires(self):
        events = self._run(315.0, 308.0)
        assert len(events) == 1
        assert events[0].facts["level"] == 310.5
        assert events[0].direction == "up"

    def test_bull_touch_fires(self):
        assert len(self._run(310.5, 308.0)) == 1

    def test_bull_below_does_not_fire(self):
        assert self._run(309.0, 308.0) == []

    def test_bear_cross_fires(self):
        assert len(self._run(305.0, 312.0, direction="BEAR")) == 1
        assert self._run(311.0, 312.0, direction="BEAR") == []

    def test_stale_plan_signals_are_ignored(self):
        assert self._run(315.0, 308.0, as_of_days=3) == []

    def test_a_signal_fires_only_once(self):
        assert self._run(315.0, 308.0, fired=[{"key": "signal:sig-1"}]) == []


class TestContrarianDetector:
    @staticmethod
    def _tiles(defensive_pct=1.0, n=3):
        tiles = [_tile(f"T{i}", "Technology", -3.0) for i in range(10)]
        for sector in ("Consumer Defensive", "Utilities"):
            tiles += [_tile(f"{sector[:2]}{i}", sector, defensive_pct)
                      for i in range(n)]
        return {"asof": FRESH_TRADE_DATE, "tiles": tiles}

    def test_fires_when_the_index_is_red_and_defensives_are_green(self):
        quotes = {"SPY": _quote(-1.82)}
        events = [e for e in HT.detect_events(quotes, heatmap=self._tiles(),
                                              now=NOW, cfg=HT.DEFAULTS)
                  if e.trigger == "contrarian_breadth"]
        assert len(events) == 1
        assert events[0].facts["n_green"] == 6
        assert set(events[0].facts["sectors_green"]) == {"Consumer Defensive",
                                                        "Utilities"}
        assert events[0].severity == 75.0

    def test_does_not_fire_on_a_shallow_index_move(self):
        quotes = {"SPY": _quote(-0.5)}
        assert [e for e in HT.detect_events(quotes, heatmap=self._tiles(), now=NOW,
                                            cfg=HT.DEFAULTS)
                if e.trigger == "contrarian_breadth"] == []

    def test_does_not_fire_when_defensives_are_red(self):
        quotes = {"SPY": _quote(-1.82)}
        assert [e for e in HT.detect_events(quotes,
                                            heatmap=self._tiles(defensive_pct=-1.0),
                                            now=NOW, cfg=HT.DEFAULTS)
                if e.trigger == "contrarian_breadth"] == []

    def test_needs_enough_green_members(self):
        quotes = {"SPY": _quote(-1.82)}
        assert [e for e in HT.detect_events(quotes, heatmap=self._tiles(n=2),
                                            now=NOW, cfg=HT.DEFAULTS)
                if e.trigger == "contrarian_breadth"] == []

    def test_the_green_count_carries_its_universe(self):
        """A COUNT WITH NO DENOMINATOR IS NOT A FACT (2026-07-31).

        "31 names across Utilities and Consumer Defensive are green" — 31 of
        how many? The same numerator-with-no-universe the desk feeds shipped as
        "18 groups on the move today" eleven times. The detector now counts the
        universe the numerator moves against: every live-quoted member of the
        sectors that qualified, green AND red.
        """
        # LETTERS ONLY: the wire's cashtag regex stops at the first digit, so a
        # generated `$CO0` would leave a bare "0" for the numeric gate.
        tiles = [_tile(f"T{c}", "Technology", -3.0) for c in "ABCDEFGHIJ"]
        for sector, prefix in (("Consumer Defensive", "CD"), ("Utilities", "UT")):
            tiles += [_tile(f"{prefix}{c}", sector, 1.0) for c in "XYZ"]
        # One red name inside a still-green defensive sector, so the count and
        # its universe cannot be the same number by construction.
        tiles.append(_tile("UTQ", "Utilities", -0.4))
        quotes = {"SPY": _quote(-1.82)}
        events = [e for e in HT.detect_events(
            quotes, heatmap={"asof": FRESH_TRADE_DATE, "tiles": tiles},
            now=NOW, cfg=HT.DEFAULTS) if e.trigger == "contrarian_breadth"]
        assert len(events) == 1
        packet = events[0]
        assert packet.facts["n_green"] == 6
        assert packet.facts["n_defensive_members"] == 7

        with forced_variant("contrarian_breadth", W.WIRE_BANK["contrarian_breadth"][1]):
            out = W.compose_wire(packet)
        assert out is not None
        assert "6 of 7 names across" in out["text"], out["text"]

    def test_a_packet_with_no_universe_refuses_the_count_variant(self):
        """The other two variants make no count claim, so the family still
        ships — it just never ships a bare numerator."""
        packet = _packet("contrarian_breadth", "contrarian:x", "up", {
            "index_pct": -1.82, "index_ticker": "SPY",
            "green": [["COST", 1.24], ["HD", 0.93], ["MMM", 0.71], ["KO", 0.55]],
            "sectors_green": ["Consumer Defensive", "Utilities"], "n_green": 11})
        with forced_variant("contrarian_breadth", W.WIRE_BANK["contrarian_breadth"][1]):
            assert W.compose_wire(packet) is None
        out = W.compose_wire(packet)
        assert out is not None and "11 names" not in out["text"]


# ─────────────────────────────────────────────────────────────────────────────
# T4 — the earnings-reaction detector (masterplan §10 E1)
# ─────────────────────────────────────────────────────────────────────────────

TODAY_ET = HT._et_date(NOW)
YESTERDAY_ET = HT._prev_session(TODAY_ET)


def _earn_row(*, next_date, next_time, surprises=None, as_of=None,
              eps_forecast=1.88) -> dict:
    return {"next_date": next_date, "next_time": next_time,
            "eps_forecast": eps_forecast, "surprises": surprises or [],
            "as_of": as_of or TODAY_ET.isoformat()}


def _surprise(reported, *, eps=2.11, consensus=1.88, pct=12.23) -> dict:
    return {"qtr": "Jun", "reported": reported, "eps": eps,
            "consensus": consensus, "surprise_pct": pct}


def _earn_events(rows: dict, quotes: dict, *, recs: dict | None = None,
                 tiles: list | None = None, fired: list | None = None,
                 cfg: dict | None = None, demo: bool = False) -> list:
    return HT.detect_events(
        quotes,
        pack=_pack(recs if recs is not None else {"AAPL": _rec(mcap_usd=3_200_000_000_000)},
                   FRESH_TRADE_DATE),
        heatmap={"asof": None, "tiles": tiles if tiles is not None
                 else [_tile("AAPL", "Technology", 6.67, industry="Consumer Electronics")]},
        earnings={"asof": TODAY_ET.isoformat(), "tickers": rows},
        fired_today=fired or [], now=NOW, cfg=cfg or HT.DEFAULTS, demo=demo)


class TestEarningsDetector:
    def test_an_after_hours_reporter_fires_on_the_next_open(self):
        rows = {"AAPL": _earn_row(next_date=YESTERDAY_ET.isoformat(),
                                  next_time="time-after-hours",
                                  surprises=[_surprise(YESTERDAY_ET.isoformat())])}
        events = [e for e in _earn_events(rows, {"AAPL": _quote(6.67, 224.0, 210.0)})
                  if e.trigger == "earnings_reaction"]
        assert len(events) == 1
        packet = events[0]
        assert packet.ticker == "AAPL" and packet.direction == "up"
        assert packet.facts["report_when"] == "ah"
        assert packet.facts["report_date"] == YESTERDAY_ET.isoformat()
        assert packet.facts["eps"]["actual"] == 2.11
        assert packet.facts["eps"]["beat"] is True
        assert packet.facts["dollar_delta_usd"] is not None

    def test_a_pre_market_reporter_fires_on_todays_gap(self):
        rows = {"AAPL": _earn_row(next_date=TODAY_ET.isoformat(),
                                  next_time="time-pre-market")}
        events = [e for e in _earn_events(rows, {"AAPL": _quote(-6.1, 197.0, 210.0)})
                  if e.trigger == "earnings_reaction"]
        assert len(events) == 1
        assert events[0].facts["report_when"] == "bmo"
        assert events[0].direction == "down"
        # No filing yet at the open — the post still ships on its other devices.
        assert events[0].facts["eps"] is None

    def test_the_us_date_form_in_surprises_json_is_read(self):
        """The vendor writes 4/30/2026; the rest of the estate writes ISO."""
        us = f"{YESTERDAY_ET.month}/{YESTERDAY_ET.day}/{YESTERDAY_ET.year}"
        rows = {"AAPL": _earn_row(next_date=YESTERDAY_ET.isoformat(),
                                  next_time="time-after-hours",
                                  surprises=[_surprise(us)])}
        events = [e for e in _earn_events(rows, {"AAPL": _quote(6.67, 224.0, 210.0)})
                  if e.trigger == "earnings_reaction"]
        assert events and events[0].facts["eps"]["consensus"] == 1.88

    def test_a_stale_surprise_row_is_not_todays_beat(self):
        """Last quarter's beat presented as today's is the one lie here."""
        rows = {"AAPL": _earn_row(next_date=YESTERDAY_ET.isoformat(),
                                  next_time="time-after-hours",
                                  surprises=[_surprise(_ago(NOW, 90))])}
        events = [e for e in _earn_events(rows, {"AAPL": _quote(6.67, 224.0, 210.0)})
                  if e.trigger == "earnings_reaction"]
        assert events and events[0].facts["eps"] is None

    def test_a_stale_calendar_never_fires(self):
        """A months-old row still reading 'reports today' is not evidence."""
        rows = {"AAPL": _earn_row(next_date=TODAY_ET.isoformat(),
                                  next_time="time-pre-market",
                                  as_of=_ago(NOW, 90))}
        events = [e for e in _earn_events(rows, {"AAPL": _quote(-6.1, 197.0, 210.0)})
                  if e.trigger == "earnings_reaction"]
        assert events == []

    def test_a_reporter_on_another_day_is_not_a_reaction(self):
        rows = {"AAPL": _earn_row(next_date=_ago(NOW, -6),
                                  next_time="time-after-hours")}
        assert [e for e in _earn_events(rows, {"AAPL": _quote(6.67, 224.0, 210.0)})
                if e.trigger == "earnings_reaction"] == []

    def test_time_not_supplied_is_not_a_reaction(self):
        """1,249 of the 1,364 shipped rows say time-not-supplied."""
        rows = {"AAPL": _earn_row(next_date=TODAY_ET.isoformat(),
                                  next_time="time-not-supplied")}
        assert [e for e in _earn_events(rows, {"AAPL": _quote(6.67, 224.0, 210.0)})
                if e.trigger == "earnings_reaction"] == []

    def test_a_small_move_on_a_report_day_is_not_the_story(self):
        rows = {"AAPL": _earn_row(next_date=TODAY_ET.isoformat(),
                                  next_time="time-pre-market")}
        assert [e for e in _earn_events(rows, {"AAPL": _quote(1.2, 212.5, 210.0)})
                if e.trigger == "earnings_reaction"] == []

    def test_an_after_hours_reporter_before_a_holiday_still_fires(self):
        """END TO END across Labor Day (reviewer minor, #3960).

        AAPL reports after the close on FRIDAY 2026-09-04. Monday is Labor Day,
        so the reaction is read at TUESDAY 2026-09-08's open. The old
        weekday-only walk named Monday as "yesterday's session", ``next_date ==
        yesterday`` never matched, and the biggest gap of the week produced no
        post at all -- silently, with no refusal line to notice.
        """
        friday, tuesday = date(2026, 9, 4), date(2026, 9, 8)
        now = datetime(tuesday.year, tuesday.month, tuesday.day, 15, 10,
                       tzinfo=timezone.utc)                     # 11:10 ET
        rows = {"AAPL": {"next_date": friday.isoformat(),
                         "next_time": "time-after-hours",
                         "eps_forecast": 1.88,
                         "surprises": [_surprise(friday.isoformat())],
                         "as_of": tuesday.isoformat()}}
        events = [e for e in HT.detect_events(
            {"AAPL": {"price": 224.0, "prev_close": 210.0, "change_pct": 6.67,
                      "ts_ms": int(now.timestamp() * 1000), "source": "quotes"}},
            pack=_pack({"AAPL": _rec(mcap_usd=3_200_000_000_000)},
                       friday.isoformat()),
            heatmap={"asof": None,
                     "tiles": [_tile("AAPL", "Technology", 6.67,
                                     industry="Consumer Electronics")]},
            earnings={"asof": tuesday.isoformat(), "tickers": rows},
            fired_today=[], now=now, cfg=HT.DEFAULTS,
        ) if e.trigger == "earnings_reaction"]
        assert len(events) == 1
        assert events[0].facts["report_when"] == "ah"
        assert events[0].facts["report_date"] == friday.isoformat()


class TestSessionWalkCrossesMarketHolidays:
    """"Yesterday's session" is a SESSION, not the previous weekday (#3960).

    ``_prev_weekday`` skipped weekends and nothing else, so every day that
    follows a scheduled closure named a CLOSED day as yesterday's session. Two
    consequences, both silent: the earnings detector matches ``next_date ==
    yesterday`` EXACTLY, so an after-hours reporter read on the session after a
    holiday was never detected; and ``bridge_ok`` counted the closure as a
    session, so the pack looked one session staler than it was and every history
    fact was suppressed for that whole day.

    The dates below are LITERALS on purpose and are not the fixture-date-bomb
    class: they name specific scheduled NYSE closures, which are fixed calendar
    facts, and no assertion here reads the current clock. The first test pins
    that premise so none of the others can pass on a wrong one.
    """

    LABOR_DAY = date(2026, 9, 7)              # 1st Monday of September 2026
    THANKSGIVING = date(2026, 11, 26)         # 4th Thursday of November 2026

    def test_the_exchange_calendar_agrees_on_the_premise(self):
        assert HT._is_session(self.LABOR_DAY) is False
        assert HT._is_session(self.THANKSGIVING) is False
        for open_day in (date(2026, 9, 4), date(2026, 9, 8),
                         date(2026, 11, 25), date(2026, 11, 27)):
            assert HT._is_session(open_day) is True, open_day

    def test_prev_session_walks_across_labor_day(self):
        # Tuesday's previous session is FRIDAY, not the Monday holiday.
        assert HT._prev_session(date(2026, 9, 8)) == date(2026, 9, 4)

    def test_prev_session_walks_across_thanksgiving(self):
        # Friday's previous session is WEDNESDAY, not Thanksgiving Thursday.
        assert HT._prev_session(date(2026, 11, 27)) == date(2026, 11, 25)

    def test_prev_session_still_walks_the_weekend(self):
        # The behaviour the old helper got right is not regressed: Monday
        # 2026-09-14's previous session is Friday 2026-09-11.
        assert HT._prev_session(date(2026, 9, 14)) == date(2026, 9, 11)

    def test_a_closure_is_not_counted_as_a_session(self):
        # Friday's pack read on the Tuesday after Labor Day is ONE session old,
        # which is inside the default bridge_max_gap_days=1.
        assert HT._sessions_between(date(2026, 9, 4), date(2026, 9, 8)) == 1
        assert HT._sessions_between(date(2026, 11, 25), date(2026, 11, 27)) == 1

    def test_bridge_ok_accepts_fridays_pack_on_the_tuesday_after_labor_day(self):
        now = datetime(2026, 9, 8, 15, 10, tzinfo=timezone.utc)      # 11:10 ET
        assert HT.bridge_ok(_pack({}, "2026-09-04"), now) is True
        # Still a real staleness gate: Thursday's pack is two sessions behind.
        assert HT.bridge_ok(_pack({}, "2026-09-03"), now) is False

    def test_a_packet_with_no_device_slot_is_refused(self):
        """Gate 0.2 in the DETECTOR: no stat, no packet, no chart raster."""
        rows = {"ZZZ": _earn_row(next_date=TODAY_ET.isoformat(),
                                 next_time="time-pre-market")}
        bare = _rec(mcap_usd=None, ath=None, max_up_1d=None, max_dn_1d=None,
                    last_date=_ago(NOW, 30))       # no mcap, no history
        events = _earn_events(rows, {"ZZZ": _quote(-6.1, 40.0, 42.6)},
                              recs={"ZZZ": bare},
                              tiles=[_tile("ZZZ", "Technology", -6.1)])
        assert [e for e in events if e.trigger == "earnings_reaction"] == []

    def test_severity_scales_with_the_move_and_the_size(self):
        rows = {"AAPL": _earn_row(next_date=TODAY_ET.isoformat(),
                                  next_time="time-pre-market")}

        def _sev(quote, **kw) -> float:
            # By TRIGGER, never by rank: the same fixture also trips the streak
            # detector, and indexing [0] would silently compare the wrong packet.
            events = [e for e in _earn_events(rows, {"AAPL": quote}, **kw)
                      if e.trigger == "earnings_reaction"]
            assert events, "no earnings packet in this fixture"
            return events[0].severity

        small = _sev(_quote(-4.1, 201.0, 210.0))
        big = _sev(_quote(-11.0, 187.0, 210.0))
        assert big > small
        # A mega-cap gap clears the flagship floor AND the two-step floor.
        assert big >= HT.DEFAULTS["two_step"]["min_severity"]

        tiny = _sev(_quote(-4.1, 201.0, 210.0),
                    recs={"AAPL": _rec(mcap_usd=2_000_000_000, sp500=False,
                                       adv_rank=900)})
        assert tiny < small                        # size is half the ranking

    def test_the_earnings_packet_suppresses_its_own_mover_twin(self):
        """One story, one post: the same |>=4%| trips both detectors."""
        rows = {"AAPL": _earn_row(next_date=TODAY_ET.isoformat(),
                                  next_time="time-pre-market",
                                  surprises=[_surprise(TODAY_ET.isoformat())])}
        events = _earn_events(rows, {"AAPL": _quote(-6.1, 197.0, 210.0)})
        triggers = {e.trigger for e in events if e.ticker == "AAPL"}
        assert "earnings_reaction" in triggers
        assert not any(t.startswith("mover_") for t in triggers), triggers

    def test_an_earnings_packet_with_NO_fresh_eps_leaves_the_mover_alive(self):
        """M3. The suppression's own justification is that the earnings packet
        "names the cause AND carries the EPS device". A BMO reporter is
        routinely unfiled at 09:30, so that second half is false, and the wire
        now REFUSES an earnings post with no beat/miss to state. Suppressing the
        mover twin as well would delete the name from the tape on the one
        morning it is most worth reading."""
        rows = {"AAPL": _earn_row(next_date=TODAY_ET.isoformat(),
                                  next_time="time-pre-market")}   # no surprises
        events = _earn_events(rows, {"AAPL": _quote(-6.1, 197.0, 210.0)})
        earnings = [e for e in events
                    if e.trigger == "earnings_reaction" and e.ticker == "AAPL"]
        assert earnings and earnings[0].facts.get("eps") is None
        assert any(e.trigger.startswith("mover_") for e in events
                   if e.ticker == "AAPL"), [e.trigger for e in events]

        # ...and the earnings packet itself renders NOTHING, which is what makes
        # the surviving mover the post rather than a second post.
        from engine.marketing.hot_tape_wire import compose_wire
        assert compose_wire(earnings[0]) is None

    def test_a_fired_mover_holds_the_earnings_cooldown(self):
        """The two detectors share ONE cooldown memory per name+direction."""
        rows = {"AAPL": _earn_row(next_date=TODAY_ET.isoformat(),
                                  next_time="time-pre-market")}
        prior = {"key": "mover:AAPL:down:x:0", "trigger": "mover_drop",
                 "ticker": "AAPL", "direction": "down", "magnitude": -6.1,
                 "fired_at": NOW.strftime("%Y-%m-%dT%H:%M:%SZ")}
        events = _earn_events(rows, {"AAPL": _quote(-6.2, 197.0, 210.0)},
                              fired=[prior])
        assert [e for e in events if e.trigger == "earnings_reaction"] == []

    def test_demo_relaxes_only_the_threshold(self):
        rows = {"AAPL": _earn_row(next_date=TODAY_ET.isoformat(),
                                  next_time="time-pre-market")}
        quotes = {"AAPL": _quote(-2.0, 205.8, 210.0)}
        assert [e for e in _earn_events(rows, quotes)
                if e.trigger == "earnings_reaction"] == []
        assert [e for e in _earn_events(rows, quotes, demo=True)
                if e.trigger == "earnings_reaction"]

    def test_the_calendar_view_accepts_a_bare_map(self):
        rows = {"AAPL": _earn_row(next_date=TODAY_ET.isoformat(),
                                  next_time="time-pre-market")}
        events = HT.detect_events(
            {"AAPL": _quote(-6.1, 197.0, 210.0)},
            pack=_pack({"AAPL": _rec(mcap_usd=3_200_000_000_000)}, FRESH_TRADE_DATE),
            earnings=rows, now=NOW, cfg=HT.DEFAULTS)
        assert [e for e in events if e.trigger == "earnings_reaction"]

    def test_a_broken_calendar_never_raises(self):
        assert HT.detect_events({"AAPL": _quote(-6.1)}, earnings="nonsense",
                                now=NOW, cfg=HT.DEFAULTS) is not None
        assert HT.detect_events({"AAPL": _quote(-6.1)},
                                earnings={"tickers": {"AAPL": "not-a-dict"}},
                                now=NOW, cfg=HT.DEFAULTS) is not None

    def test_the_composed_post_names_the_report_and_a_stat(self):
        rows = {"AAPL": _earn_row(next_date=YESTERDAY_ET.isoformat(),
                                  next_time="time-after-hours",
                                  surprises=[_surprise(YESTERDAY_ET.isoformat())])}
        packet = [e for e in _earn_events(rows, {"AAPL": _quote(6.67, 224.0, 210.0)})
                  if e.trigger == "earnings_reaction"][0]
        out = W.compose_wire(packet)
        assert out is not None
        assert "reported after yesterday's close" in out["text"]
        assert "earnings_clause" in out["devices"]
        assert W.ban_hits(out["text"]) == []
        assert W.check_text_numbers(out["text"], packet) == []


class TestEarningsClauses:
    def test_the_eps_clause_needs_both_numbers(self):
        packet = rich_packets()["earnings_reaction"]
        clause = W._eps_clause(packet, packet.facts)
        assert clause.startswith("EPS came in at $2.11, ahead of the $1.88 consensus")
        assert "12.2% surprise" in clause
        assert W._eps_clause(packet, {"eps": {"actual": 2.11}}) is None
        assert W._eps_clause(packet, {}) is None

    def test_a_miss_reads_as_a_miss(self):
        facts = {"eps": {"actual": 1.10, "consensus": 1.40, "surprise_pct": -21.4,
                         "beat": False}}
        packet = _packet("earnings_reaction", "k", "down", facts, ticker="X")
        assert W._eps_clause(packet, facts).startswith(
            "EPS came in at $1.10, under the $1.40 consensus")

    def test_the_report_clause_refuses_an_unknown_window(self):
        packet = rich_packets()["earnings_reaction"]
        assert W._earnings_clause(packet, {"report_when": "sometime"}) is None
        assert W._earnings_clause(packet, {}) is None

    def test_the_family_needs_a_real_device_on_top_of_the_report(self):
        """"Reported and moved 6%" is the flop shape with a calendar on it."""
        bare = _packet("earnings_reaction", "earnings:X:up:x:0", "up", ticker="X",
                       facts={"ticker": "X", "pct": 6.1, "price": 40.0,
                              "report_when": "bmo", "eps": None,
                              "dollar_delta_usd": None, "biggest_1d": None,
                              "pct_from_ath_live": None})
        assert W.compose_wire(bare) is None


# ─────────────────────────────────────────────────────────────────────────────
# Two-step publish — the context brief (codex law, masterplan §10 E1)
# ─────────────────────────────────────────────────────────────────────────────

def _peer_tiles(pcts: dict, *, industry: str = "Semiconductors") -> list[dict]:
    return [_tile(sym, "Technology", pct, industry=industry)
            for sym, pct in pcts.items()]


def _alert_row(**over) -> dict:
    row = {"key": "mover:MU:down:x:0", "trigger": "mover_drop", "ticker": "MU",
           "sector": "Technology", "direction": "down", "severity": 95.0,
           "magnitude": -8.2, "account": "flagship",
           "fired_at": NOW.strftime("%Y-%m-%dT%H:%M:%SZ"), "item_id": "abc123"}
    row.update(over)
    return row


class TestBriefPacket:
    def test_a_group_wide_move_is_named_as_one(self):
        pcts = {"MU": -8.2, "SNDK": -9.1, "STX": -8.4, "NVDA": -7.9, "AMD": -8.8}
        quotes = {s: _quote(p, 50.0, 55.0) for s, p in pcts.items()}
        packet = HT.build_brief_packet(_alert_row(), quotes=quotes,
                                       heatmap={"tiles": _peer_tiles(pcts)},
                                       now=NOW, cfg=HT.DEFAULTS)
        assert packet is not None
        assert packet.trigger == HT.BRIEF_TRIGGER == "context_brief"
        assert packet.key == HT.brief_key("mover:MU:down:x:0")
        mech = packet.facts["mechanism"]
        assert mech["kind"] == "group"
        assert mech["group"] == "Semiconductors" and mech["group_kind"] == "industry"
        assert mech["n_peers"] == 4          # the subject is not its own peer
        out = W.compose_wire(packet)
        assert out is not None and "mechanism_clause" in out["devices"]
        assert "This is a group move" in out["text"]
        assert W.check_text_numbers(out["text"], packet) == []

    def test_a_lone_mover_is_named_as_one_name(self):
        pcts = {"MU": -8.2, "SNDK": -0.2, "STX": 0.1, "NVDA": -0.4, "AMD": 0.3}
        quotes = {s: _quote(p, 50.0, 55.0) for s, p in pcts.items()}
        packet = HT.build_brief_packet(_alert_row(), quotes=quotes,
                                       heatmap={"tiles": _peer_tiles(pcts)},
                                       now=NOW, cfg=HT.DEFAULTS)
        assert packet.facts["mechanism"]["kind"] == "single_name"
        text = W.compose_wire(packet)["text"]
        assert "so this is one name and not the group" in text

    def test_too_few_peers_refuses(self):
        """No group, no mechanism, no brief — gate 0.2 applies to the brief too."""
        pcts = {"MU": -8.2, "SNDK": -9.1}
        quotes = {s: _quote(p, 50.0, 55.0) for s, p in pcts.items()}
        assert HT.build_brief_packet(_alert_row(), quotes=quotes,
                                     heatmap={"tiles": _peer_tiles(pcts)},
                                     now=NOW, cfg=HT.DEFAULTS) is None

    def test_no_live_quote_for_the_subject_refuses(self):
        pcts = {"MU": -8.2, "SNDK": -9.1, "STX": -8.4, "NVDA": -7.9, "AMD": -8.8}
        quotes = {s: _quote(p, 50.0, 55.0) for s, p in pcts.items() if s != "MU"}
        assert HT.build_brief_packet(_alert_row(), quotes=quotes,
                                     heatmap={"tiles": _peer_tiles(pcts)},
                                     now=NOW, cfg=HT.DEFAULTS) is None

    def test_a_group_alert_briefs_without_a_cashtag(self):
        pcts = {"MU": -8.2, "SNDK": -9.1, "STX": -8.4, "NVDA": -7.9, "AMD": -8.8}
        quotes = {s: _quote(p, 50.0, 55.0) for s, p in pcts.items()}
        row = _alert_row(key="sector:Semiconductors:down:x", trigger="sector_rout",
                         ticker=None, sector="Semiconductors",
                         account="mastermind_news")
        packet = HT.build_brief_packet(row, quotes=quotes,
                                       heatmap={"tiles": _peer_tiles(pcts)},
                                       now=NOW, cfg=HT.DEFAULTS)
        assert packet is not None and packet.ticker is None
        assert packet.facts["subject_label"] == "Semiconductors"
        assert packet.facts["watch"]["kind"] == "breadth"
        text = W.compose_wire(packet)["text"]
        assert text.startswith("Semiconductors:")

    def test_the_quotes_wrapper_is_accepted(self):
        pcts = {"MU": -8.2, "SNDK": -9.1, "STX": -8.4, "NVDA": -7.9, "AMD": -8.8}
        live = {"asof": "2020-01-01",
                "quotes": {s: _quote(p, 50.0, 55.0) for s, p in pcts.items()}}
        packet = HT.build_brief_packet(_alert_row(), quotes=live,
                                       heatmap={"tiles": _peer_tiles(pcts)},
                                       now=NOW, cfg=HT.DEFAULTS)
        assert packet is not None
        assert packet.provenance["quotes_asof"] == "2020-01-01"

    def test_bad_input_never_raises(self):
        assert HT.build_brief_packet({}, now=NOW) is None
        assert HT.build_brief_packet({"key": "k", "direction": "sideways"},
                                     now=NOW) is None
        assert HT.build_brief_packet(_alert_row(), quotes="broken", now=NOW) is None

    def test_the_watch_clause_is_a_window_never_a_call(self):
        """Operator 2026-07-27: projection windows, never verdicts or calls."""
        packet = rich_packets()["context_brief"]
        clause = W._watch_clause(packet, packet.facts)
        assert clause.startswith("What we are watching:")
        assert W.ban_hits(clause) == []
        for banned in ("falsif", "refuted", "证伪", "thesis"):
            assert banned not in clause.lower()

    def test_the_mechanism_clause_is_mandatory(self):
        no_mech = _packet("context_brief", "brief:x", "down", ticker="MU",
                          facts={"ticker": "MU", "pct": -8.2, "price": 84.2,
                                 "peers": [["SNDK", -14.3], ["STX", -8.5]],
                                 "watch": {"kind": "level", "price": 84.2}})
        assert W._mechanism_clause(no_mech, no_mech.facts) is None
        assert W.compose_wire(no_mech) is None

    def test_the_mechanism_count_is_agreeing_names_over_group_size(self):
        """2026-07-31, the same defect class as "18 groups on the move today":
        the clause read "{n_peers} names are trading together", and n_peers is
        the SIZE of the peer group, not a count of names that moved. A group
        where 3 of 9 names agreed was described as nine names trading together
        — a bare numerator that was also the wrong number.
        """
        mech = {"kind": "group", "group": "Semiconductors",
                "group_kind": "industry", "peer_median_pct": -6.4,
                "n_peers": 9, "n_agree": 7}
        packet = _packet("context_brief", "brief:x", "down", ticker="MU",
                         facts={"ticker": "MU", "pct": -8.2, "price": 84.2,
                                "mechanism": mech,
                                "peers": [["SNDK", -14.3], ["STX", -8.5]],
                                "watch": {"kind": "level", "price": 84.2}})
        clause = W._mechanism_clause(packet, packet.facts)
        assert clause == ("This is a group move: 7 of 9 names are trading "
                          "together, median -6.4%")

        lone = dict(mech, kind="single_name", n_agree=3, peer_median_pct=-0.3)
        packet.facts["mechanism"] = lone
        assert W._mechanism_clause(packet, packet.facts) == (
            "The rest of Semiconductors is not following: 3 of 9 names moved "
            "with it, median -0.3%, so this is one name and not the group")

    def test_a_mechanism_with_no_agreement_count_refuses(self):
        """Denominator law both ways: no numerator, no count claim, no brief."""
        packet = _packet("context_brief", "brief:x", "down", ticker="MU",
                         facts={"ticker": "MU", "pct": -8.2, "price": 84.2,
                                "mechanism": {"kind": "group",
                                              "group": "Semiconductors",
                                              "peer_median_pct": -6.4,
                                              "n_peers": 9},
                                "peers": [["SNDK", -14.3], ["STX", -8.5]],
                                "watch": {"kind": "level", "price": 84.2}})
        assert W._mechanism_clause(packet, packet.facts) is None
        assert W.compose_wire(packet) is None


class TestDetectEventsContract:
    def test_output_is_sorted_by_severity(self):
        tiles = [_tile(f"S{i}", "Technology", -3.0, industry="Sub") for i in range(10)]
        tiles.append(_tile("AMD", "Technology", -8.0, industry="Semiconductors"))
        quotes = {"AMD": _quote(-8.0, price=84.2, prev=91.65)}
        events = HT.detect_events(quotes, pack=_pack({"AMD": _rec()},
                                                     FRESH_TRADE_DATE),
                                  heatmap={"asof": None, "tiles": tiles}, now=NOW,
                                  cfg=HT.DEFAULTS)
        assert len(events) >= 2
        assert [e.severity for e in events] == sorted(
            [e.severity for e in events], reverse=True)

    def test_bad_input_never_raises(self):
        assert HT.detect_events(None) == []
        assert HT.detect_events({"AMD": "not-a-dict"}, now=NOW) == []
        assert HT.detect_events({}, pack={"tickers": "broken"}, now=NOW) == []

    def test_quotes_wrapper_is_accepted(self):
        recs = {"AMD": _rec()}
        live = {"quotes": {"AMD": _quote(-8.13, 84.2, 91.65)}, "asof": "2020-01-01"}
        events = HT.detect_events(live, pack=_pack(recs, FRESH_TRADE_DATE), now=NOW,
                                  cfg=HT.DEFAULTS)
        assert events and events[0].provenance["quotes_asof"] == "2020-01-01"


# ─────────────────────────────────────────────────────────────────────────────
# Routing, state, outbox handoff
# ─────────────────────────────────────────────────────────────────────────────

class TestRouting:
    def test_flagship_floor(self):
        # Floor is 85 (routing amendment 2026-07-28): ordinary sector routs
        # (base 80) home to the wire desk; only a 2.5%+ median rout or a
        # boosted mega-cap event mirrors to flagship.
        packet = _packet("mover_drop", "k", "down", {"pct": -9.0}, severity=85.0)
        assert HT.severity_account(packet, HT.DEFAULTS) == "flagship"
        packet.severity = 84.9
        assert HT.severity_account(packet, HT.DEFAULTS) == "mastermind_news"
        packet.severity = 80.0
        assert HT.severity_account(packet, HT.DEFAULTS) == "mastermind_news"

    def test_routing_reads_the_config(self):
        cfg = HT.load_config(None)
        cfg["emit"]["flagship_severity_floor"] = 95
        packet = _packet("mover_drop", "k", "down", {"pct": -9.0}, severity=90.0)
        assert HT.severity_account(packet, cfg) == "mastermind_news"


class TestRingAndFired:
    def test_ring_round_trip_and_compaction(self, tmp_path):
        for i in range(40):
            HT.append_ring(tmp_path, {"i": i, "asof": NOW.isoformat()})
        assert len(HT.load_ring(tmp_path, n=36)) == 36
        HT.compact_ring(tmp_path, keep=36)
        rows = HT.load_ring(tmp_path, n=100)
        assert len(rows) == 36
        assert rows[0]["i"] == 4 and rows[-1]["i"] == 39

    def test_ring_is_empty_when_absent(self, tmp_path):
        assert HT.load_ring(tmp_path) == []

    def test_fired_is_filtered_to_the_day(self, tmp_path):
        today = NOW.date().isoformat()
        HT.append_fired(tmp_path, {"key": "a", "fired_at":
                                   NOW.strftime("%Y-%m-%dT%H:%M:%SZ")})
        HT.append_fired(tmp_path, {"key": "b", "fired_at":
                                   (NOW - timedelta(days=3))
                                   .strftime("%Y-%m-%dT%H:%M:%SZ")})
        rows = HT.load_fired(tmp_path, today)
        assert [r["key"] for r in rows] == ["a"]

    def test_fired_entry_shape(self):
        packet = rich_packets()["mover_drop"]
        row = HT.fired_entry(packet, item_id="itm-1", account="mastermind_news")
        assert row["key"] == packet.key
        assert row["magnitude"] == -8.13
        assert row["ticker"] == "AMD"
        assert row["day"] == packet.fired_at[:10]
        json.dumps(row)


class TestPacketToSource:
    def test_source_carries_the_full_packet(self):
        packet = rich_packets()["mover_drop"]
        source = HT.packet_to_source(packet, {"media_url": "https://r2/x.png",
                                              "chart_id": "c1"})
        assert source["lane"] == "hot_tape"
        assert source["trigger"] == "mover_drop"
        assert source["baseline_pct"] == -8.13
        assert source["bridge_ok"] is True
        assert source["demo"] is False
        assert source["media_url"].endswith("x.png")
        assert source["fact_packet"]["facts"]["ath"] == 117.66
        assert json.loads(json.dumps(source))["fact_packet"]["trigger"] == "mover_drop"

    def test_sector_baseline_is_the_median(self):
        source = HT.packet_to_source(rich_packets()["sector_rout"])
        assert source["baseline_pct"] == -7.85
        assert source["ticker"] is None


class TestOutboxHandoff:
    """Gate 0.5 — our items pass the untouched sentinel/near-dup guards."""

    def test_item_validates_enqueues_and_dedupes(self, tmp_path):
        from engine.marketing import outbox

        packet = rich_packets()["mover_drop"]
        composed = W.compose_wire(packet)
        assert composed is not None
        item = outbox.make_item(
            account="mastermind_news", kind="breaking", text=composed["text"],
            as_of=NOW.date().isoformat(), scheduled_at="immediate", priority=1,
            provenance="hot_tape", source=HT.packet_to_source(packet), now=NOW,
        )
        assert outbox.validate_item(item) == []
        assert outbox.enqueue(item, root=tmp_path) == "queued"
        assert outbox.enqueue(item, root=tmp_path) == "duplicate"

    def test_the_kind_is_admitted(self):
        from engine.marketing import outbox

        assert "breaking" in outbox.KINDS
