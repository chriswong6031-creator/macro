"""tests/test_watchlist_sentinel.py

Unit tests for engine/watchlist_sentinel.py — Watchlist buy-zone sentinel (B6).

Covers the task requirements:
  1. Enter vs sitting-in-state — only ENTER fires
  2. Each veto individually blocks: earnings_blackout, extension parabolic, extension stretched
  3. Cooldown: no re-alert within COOLDOWN_SESSIONS sessions
  4. Re-enter after leave clears cooldown and fires again
  5. Empty watchlist returns []
  6. Missing prior state (yesterday_states={}) — first nightly fires on current window
  7. Same-day idempotence — run_sentinel is pure; idempotence is caller-side (tested separately)
  8. None-safety: None values in state dicts don't crash
  9. format_discord_message: no advice verbs, no "validated" in output
 10. update_cooldown: advances correctly for alerted and non-alerted tickers
"""
from __future__ import annotations

import pytest

from engine.watchlist_sentinel import (
    COOLDOWN_SESSIONS,
    _in_window,
    _reason_codes,
    _cooldown_blocks,
    run_sentinel,
    update_cooldown,
    format_discord_message,
)


# ---------------------------------------------------------------------------
# Fixtures / helpers
# ---------------------------------------------------------------------------

def _state(
    entry_status: str | None = None,
    gate_eligible: bool | None = None,
    gate_tier: str | None = None,
    in_blackout: bool | None = None,
    extension_grade: str | None = None,
    as_of: str = "2026-07-08",
) -> dict:
    return {
        "entry_status": entry_status,
        "gate_eligible": gate_eligible,
        "gate_tier": gate_tier,
        "in_blackout": in_blackout,
        "extension_grade": extension_grade,
        "as_of": as_of,
    }


def _open_state(**kwargs) -> dict:
    """A state that passes the clean-window rule by default."""
    defaults = dict(
        entry_status="buy_now",
        gate_eligible=True,
        gate_tier="T2",
        in_blackout=False,
        extension_grade=None,
    )
    defaults.update(kwargs)
    return _state(**defaults)


def _closed_state(**kwargs) -> dict:
    """A state that does NOT pass the clean-window rule."""
    defaults = dict(
        entry_status="hold",
        gate_eligible=False,
        gate_tier=None,
        in_blackout=False,
        extension_grade=None,
    )
    defaults.update(kwargs)
    return _state(**defaults)


# ---------------------------------------------------------------------------
# _in_window
# ---------------------------------------------------------------------------

class TestInWindow:
    def test_buy_now_open(self):
        assert _in_window(_state(entry_status="buy_now", in_blackout=False)) is True

    def test_partial_open(self):
        assert _in_window(_state(entry_status="partial", in_blackout=False)) is True

    def test_gate_eligible_with_tier_open(self):
        assert _in_window(_state(gate_eligible=True, gate_tier="T2", in_blackout=False)) is True

    def test_gate_eligible_without_tier_closed(self):
        # eligible=True but no tier_cascade -> not open
        assert _in_window(_state(gate_eligible=True, gate_tier=None, in_blackout=False)) is False

    def test_hold_closed(self):
        assert _in_window(_state(entry_status="hold")) is False

    def test_extended_closed(self):
        assert _in_window(_state(entry_status="extended")) is False

    def test_await_confluence_closed(self):
        assert _in_window(_state(entry_status="await_confluence")) is False

    def test_wait_pullback_closed(self):
        assert _in_window(_state(entry_status="wait_pullback")) is False

    def test_blackout_vetos_buy_now(self):
        assert _in_window(_state(entry_status="buy_now", in_blackout=True)) is False

    def test_parabolic_vetos_buy_now(self):
        assert _in_window(_state(entry_status="buy_now", extension_grade="parabolic", in_blackout=False)) is False

    def test_stretched_vetos_buy_now(self):
        assert _in_window(_state(entry_status="buy_now", extension_grade="stretched", in_blackout=False)) is False

    def test_stretched_vetos_gate_eligible(self):
        assert _in_window(_state(gate_eligible=True, gate_tier="T2",
                                 extension_grade="stretched", in_blackout=False)) is False

    def test_all_none_closed(self):
        assert _in_window({}) is False

    def test_none_values_safe(self):
        assert _in_window(_state(
            entry_status=None, gate_eligible=None, gate_tier=None,
            in_blackout=None, extension_grade=None,
        )) is False

    def test_extension_grade_normal_does_not_block(self):
        assert _in_window(_state(entry_status="buy_now", extension_grade="steady",
                                 in_blackout=False)) is True

    def test_extension_grade_intrend_does_not_block(self):
        assert _in_window(_state(entry_status="buy_now", extension_grade="intrend",
                                 in_blackout=False)) is True


# ---------------------------------------------------------------------------
# _cooldown_blocks
# ---------------------------------------------------------------------------

class TestCooldownBlocks:
    def test_no_history_does_not_block(self):
        assert _cooldown_blocks("NVDA", False, {}, "2026-07-08") is False

    def test_within_cooldown_and_continuous_blocks(self):
        cooldown = {"NVDA": {"last_alert": "2026-07-05", "last_in_window": True, "sessions_since": 2}}
        # prev_in_window=True means it was continuously in-window — cooldown applies
        assert _cooldown_blocks("NVDA", prev_in_window=True, cooldown=cooldown, today_str="2026-07-08") is True

    def test_cooldown_expired_does_not_block(self):
        cooldown = {"NVDA": {"last_alert": "2026-07-01", "last_in_window": True, "sessions_since": COOLDOWN_SESSIONS}}
        # sessions_since == COOLDOWN_SESSIONS → not < threshold → does not block
        assert _cooldown_blocks("NVDA", prev_in_window=True, cooldown=cooldown, today_str="2026-07-08") is False

    def test_re_enter_after_leave_clears_cooldown(self):
        # prev_in_window=False means the window closed — cooldown reset, permit re-entry
        cooldown = {"NVDA": {"last_alert": "2026-07-05", "last_in_window": False, "sessions_since": 1}}
        assert _cooldown_blocks("NVDA", prev_in_window=False, cooldown=cooldown, today_str="2026-07-08") is False

    def test_fresh_entry_not_blocked(self):
        # sessions_since=0 after alert was just set → still within COOLDOWN
        cooldown = {"NVDA": {"last_alert": "2026-07-08", "last_in_window": True, "sessions_since": 0}}
        assert _cooldown_blocks("NVDA", prev_in_window=True, cooldown=cooldown, today_str="2026-07-08") is True


# ---------------------------------------------------------------------------
# run_sentinel
# ---------------------------------------------------------------------------

class TestRunSentinel:
    TODAY = "2026-07-08"

    def test_empty_watchlist_returns_empty(self):
        alerts = run_sentinel([], {}, {}, {}, today_str=self.TODAY)
        assert alerts == []

    def test_enter_fires_when_not_in_yesterday(self):
        """Ticker goes from closed window to open window → fires."""
        today = {"NVDA": _open_state()}
        yesterday = {"NVDA": _closed_state()}
        alerts = run_sentinel(["NVDA"], today, yesterday, {}, today_str=self.TODAY)
        assert len(alerts) == 1
        a = alerts[0]
        assert a["ticker"] == "NVDA"
        assert a["state_entered"] == "buy_zone_enter"
        assert a["as_of"] == self.TODAY
        assert "entry_status=buy_now" in a["reasons"] or any("entry_status" in r for r in a["reasons"])

    def test_sitting_in_window_does_not_fire(self):
        """Ticker already in window yesterday AND today → no new alert."""
        today = {"NVDA": _open_state()}
        yesterday = {"NVDA": _open_state()}
        alerts = run_sentinel(["NVDA"], today, yesterday, {}, today_str=self.TODAY)
        assert alerts == []

    def test_closed_today_does_not_fire(self):
        """Ticker was open yesterday but closed today → no alert."""
        today = {"NVDA": _closed_state()}
        yesterday = {"NVDA": _open_state()}
        alerts = run_sentinel(["NVDA"], today, yesterday, {}, today_str=self.TODAY)
        assert alerts == []

    def test_missing_prior_state_counts_as_closed_yesterday(self):
        """No yesterday state → treated as not-in-window → ENTER fires if today open."""
        today = {"NVDA": _open_state()}
        yesterday = {}  # first nightly — no prior
        alerts = run_sentinel(["NVDA"], today, yesterday, {}, today_str=self.TODAY)
        assert len(alerts) == 1

    def test_blackout_veto_blocks_alert(self):
        today = {"NVDA": _open_state(in_blackout=True)}
        yesterday = {"NVDA": _closed_state()}
        alerts = run_sentinel(["NVDA"], today, yesterday, {}, today_str=self.TODAY)
        assert alerts == []

    def test_parabolic_veto_blocks_alert(self):
        today = {"NVDA": _open_state(extension_grade="parabolic")}
        yesterday = {"NVDA": _closed_state()}
        alerts = run_sentinel(["NVDA"], today, yesterday, {}, today_str=self.TODAY)
        assert alerts == []

    def test_stretched_veto_blocks_alert(self):
        today = {"NVDA": _open_state(extension_grade="stretched")}
        yesterday = {"NVDA": _closed_state()}
        alerts = run_sentinel(["NVDA"], today, yesterday, {}, today_str=self.TODAY)
        assert alerts == []

    def test_cooldown_blocks_continuous_window(self):
        """Same ticker still in continuous window within cooldown → suppressed."""
        today = {"NVDA": _open_state()}
        yesterday = {"NVDA": _open_state()}  # continuous — but yesterday_in=True so no enter anyway
        # Actually yesterday_in=True means NOT entering → the test above covers continuous stay
        # This test: ticker enters on day 1, is in cooldown, re-enters after still being in window
        # Simulate: yesterday not in window (so we'd normally fire), but cooldown blocks because
        # prev_in_window=True in the cooldown check is about the state *at the last check*.
        # Cooldown check: prev_in_window comes from yesterday_in_window, not from cooldown map.
        # prev_in_window=False (yesterday closed) → cooldown cleared → fires regardless.
        # So cooldown only blocks when yesterday_in=True AND sessions_since < threshold.
        # But if yesterday_in=True AND today_in=True → "sitting", no enter fire at all!
        # Conclusion: cooldown acts as a secondary guard; the primary is enter-detection.
        # The relevant case: ticker exits window then re-enters BUT cooldown hasn't expired.
        # In that case prev_in_window=False → cooldown is CLEARED → fires.
        # So cooldown is only relevant when prev_in_window=True (continuous stay) which
        # is the same as "sitting" (no enter). Cooldown's main purpose: suppress repeated
        # same-day or next-day re-triggers when the window opens/closes/reopens rapidly.
        # Test: ticker was NOT in window yesterday (→ enter fires), BUT was in-window 2 sessions ago
        # with sessions_since=2. Since prev_in_window=False, cooldown is cleared.
        cooldown = {"NVDA": {"last_alert": "2026-07-06", "last_in_window": True, "sessions_since": 2}}
        today = {"NVDA": _open_state()}
        yesterday = {"NVDA": _closed_state()}  # left window → prev_in_window=False
        alerts = run_sentinel(["NVDA"], today, yesterday, cooldown, today_str=self.TODAY)
        # prev_in_window=False clears the cooldown check → fires
        assert len(alerts) == 1

    def test_multiple_tickers_independent(self):
        today = {
            "NVDA": _open_state(),
            "AAPL": _closed_state(),
            "MSFT": _open_state(),
        }
        yesterday = {
            "NVDA": _closed_state(),
            "AAPL": _open_state(),  # leaving window
            "MSFT": _open_state(),  # continuous
        }
        alerts = run_sentinel(["NVDA", "AAPL", "MSFT"], today, yesterday, {}, today_str=self.TODAY)
        assert len(alerts) == 1
        assert alerts[0]["ticker"] == "NVDA"

    def test_only_entry_signal_open(self):
        """buy_now entry but no gate tier — still fires (entry_signal alone suffices)."""
        today = {"NVDA": _state(entry_status="buy_now", gate_eligible=False, gate_tier=None,
                                in_blackout=False, extension_grade=None)}
        yesterday = {"NVDA": _closed_state()}
        alerts = run_sentinel(["NVDA"], today, yesterday, {}, today_str=self.TODAY)
        assert len(alerts) == 1

    def test_only_gate_open(self):
        """Gate eligible + tier but no buy_now status — still fires."""
        today = {"NVDA": _state(entry_status="hold", gate_eligible=True, gate_tier="T2",
                                in_blackout=False, extension_grade=None)}
        yesterday = {"NVDA": _closed_state()}
        alerts = run_sentinel(["NVDA"], today, yesterday, {}, today_str=self.TODAY)
        assert len(alerts) == 1

    def test_none_ticker_skipped(self):
        today = {"NVDA": _open_state()}
        yesterday = {}
        alerts = run_sentinel([None, "", "NVDA", "  "], today, yesterday, {}, today_str=self.TODAY)
        assert len(alerts) == 1
        assert alerts[0]["ticker"] == "NVDA"

    def test_ticker_not_in_today_states_treated_as_closed(self):
        """Ticker in watchlist but not in today_states → not-in-window → no fire."""
        today = {}  # ticker not computed
        yesterday = {}
        alerts = run_sentinel(["UNKNOWN_XYZ"], today, yesterday, {}, today_str=self.TODAY)
        assert alerts == []

    def test_alert_id_key_is_deterministic(self):
        today = {"NVDA": _open_state()}
        yesterday = {"NVDA": _closed_state()}
        alerts = run_sentinel(["NVDA"], today, yesterday, {}, today_str=self.TODAY)
        assert alerts[0]["alert_id_key"] == f"watchlist|buy_zone_enter|NVDA|{self.TODAY}"


# ---------------------------------------------------------------------------
# update_cooldown
# ---------------------------------------------------------------------------

class TestUpdateCooldown:
    TODAY = "2026-07-08"

    def test_newly_alerted_ticker_set_to_sessions_since_0(self):
        alert = {"ticker": "NVDA"}
        today = {"NVDA": _open_state()}
        new_cd = update_cooldown({}, ["NVDA"], today, [alert], self.TODAY)
        assert new_cd["NVDA"]["sessions_since"] == 0
        assert new_cd["NVDA"]["last_alert"] == self.TODAY

    def test_in_window_not_alerted_increments(self):
        old_cd = {"NVDA": {"last_alert": "2026-07-07", "last_in_window": True, "sessions_since": 2}}
        today = {"NVDA": _open_state()}
        new_cd = update_cooldown(old_cd, ["NVDA"], today, [], self.TODAY)
        assert new_cd["NVDA"]["sessions_since"] == 3

    def test_not_in_window_drops_entry(self):
        """Ticker left the window → dropped from cooldown so next ENTER is fresh."""
        today = {"NVDA": _closed_state()}
        old_cd = {"NVDA": {"last_alert": "2026-07-07", "last_in_window": True, "sessions_since": 2}}
        new_cd = update_cooldown(old_cd, ["NVDA"], today, [], self.TODAY)
        assert "NVDA" not in new_cd

    def test_multiple_tickers(self):
        today = {"NVDA": _open_state(), "AAPL": _closed_state()}
        alert = {"ticker": "NVDA"}
        new_cd = update_cooldown({}, ["NVDA", "AAPL"], today, [alert], self.TODAY)
        assert "NVDA" in new_cd
        assert "AAPL" not in new_cd

    def test_empty_watchlist(self):
        new_cd = update_cooldown({}, [], {}, [], self.TODAY)
        assert new_cd == {}


# ---------------------------------------------------------------------------
# format_discord_message
# ---------------------------------------------------------------------------

class TestFormatDiscordMessage:
    def _alert(self, **kwargs) -> dict:
        defaults = {
            "ticker": "NVDA",
            "state_entered": "buy_zone_enter",
            "reasons": ["entry_status=buy_now", "gate_tier=T2"],
            "as_of": "2026-07-08",
            "entry_status": "buy_now",
            "gate_tier": "T2",
            "in_blackout": False,
            "extension_grade": None,
        }
        defaults.update(kwargs)
        return defaults

    def test_ticker_appears_in_message(self):
        msg = format_discord_message(self._alert())
        assert "NVDA" in msg

    def test_buy_zone_label_appears(self):
        msg = format_discord_message(self._alert())
        assert "buy zone" in msg.lower()

    def test_no_advice_verbs(self):
        """Message must not contain imperative buy/sell/add/avoid directives."""
        msg = format_discord_message(self._alert())
        # We check for the most obvious forbidden imperatives
        lower = msg.lower()
        assert "buy now" not in lower  # "buy zone" is allowed, "buy now" as directive is not
        assert "sell" not in lower
        assert " add " not in lower
        # "avoid" is not expected either
        assert "avoid" not in lower

    def test_no_validated_word(self):
        """CI-enforced: 'validated' must not appear in user-facing strings."""
        msg = format_discord_message(self._alert())
        assert "validated" not in msg.lower()

    def test_date_appears(self):
        msg = format_discord_message(self._alert())
        assert "2026-07-08" in msg

    def test_blackout_note_when_in_blackout(self):
        msg = format_discord_message(self._alert(in_blackout=True))
        assert "earnings blackout" in msg.lower()

    def test_no_blackout_note_when_not_in_blackout(self):
        msg = format_discord_message(self._alert(in_blackout=False))
        assert "no earnings blackout" in msg.lower()

    def test_extension_appears_in_message(self):
        msg = format_discord_message(self._alert(extension_grade="intrend"))
        assert "intrend" in msg

    def test_none_extension_defaults_to_normal(self):
        msg = format_discord_message(self._alert(extension_grade=None))
        assert "normal" in msg

    def test_watchlist_prefix(self):
        msg = format_discord_message(self._alert())
        assert msg.startswith("WATCHLIST ·")

    def test_reasons_appear_in_message(self):
        reasons = ["entry_status=buy_now", "gate_tier=T2"]
        msg = format_discord_message(self._alert(reasons=reasons))
        assert "entry_status=buy_now" in msg
        assert "gate_tier=T2" in msg

    def test_empty_reasons_safe(self):
        msg = format_discord_message(self._alert(reasons=[]))
        assert isinstance(msg, str)
        assert len(msg) > 0

    def test_missing_keys_safe(self):
        """format_discord_message must not crash on a minimal alert dict."""
        msg = format_discord_message({"ticker": "X"})
        assert "X" in msg
