"""Tests for scripts/notify_turn_events.py — FTR W10.

Covers:
  (1) IGNITION transition detection — fires on NEW IGNITION, not on persistence
  (2) Per-day dedup — does not re-fire on same basket-day
  (3) Shock activation detection — fires on activation, not on persistence
  (4) Tape disagreement detection — IGNITION basket with positive live tape
  (5) Absent webhook — dark mode, exit 0, no crash
  (6) Copy contract — no forbidden words in any emitted message
  (7) Dedup state loading — tolerant of missing file
  (8) run() never raises (exit-0 contract)
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import scripts.notify_turn_events as NTE


# ---------------------------------------------------------------------------
# Fixtures and helpers
# ---------------------------------------------------------------------------

_TODAY = "2026-07-09"

_TURN_WATCH_IGNITION = {
    "schema": "basket_turn_watch.v1",
    "as_of": _TODAY,
    "baskets": [
        {
            "basket_id": "semicap_equipment",
            "state": "IGNITION",
            "k": 4,
            "legs": {
                "impulse_day": True,
                "rs_z": True,
                "volume_confirm": True,
                "complex_confirm": True,
                "breadth_surge": False,
                "shock_relative_bid": False,
            },
            "rs_z_value": 2.5,
            "ew_1d_ret": 0.031,
            "as_of": _TODAY,
        },
        {
            "basket_id": "memory_storage",
            "state": "WATCH",
            "k": 2,
            "legs": {
                "impulse_day": True,
                "rs_z": False,
                "volume_confirm": True,
                "complex_confirm": False,
                "breadth_surge": False,
                "shock_relative_bid": False,
            },
            "rs_z_value": 1.1,
            "ew_1d_ret": 0.012,
            "as_of": _TODAY,
        },
    ],
}

_TURN_WATCH_EMPTY = {
    "schema": "basket_turn_watch.v1",
    "as_of": _TODAY,
    "baskets": [],
}

_SHOCK_ACTIVE = {
    "active": True,
    "score": 75,
    "since": _TODAY,
    "reason": "driver_flip + breadth",
    "expires": "2026-07-16",
    "schema": "shock_deescalation.v1",
}

_SHOCK_INACTIVE = {
    "active": False,
    "score": None,
    "since": None,
    "schema": "shock_deescalation.v1",
}

_BASKET_PULSE_WITH_IGNITION = {
    "schema": "basket_pulse.v1",
    "as_of_utc": _TODAY + "T15:00:00Z",
    "session": "rth",
    "baskets": [
        {
            "id": "semicap_equipment",
            # live_ew_chg_pct is ALREADY in percent units: 0.40 = +0.40%
            # (scripts/build_basket_pulse.py averages changePct from live_quotes,
            #  which emits (price/prev - 1) * 100). Use a realistic percent value.
            "live_ew_chg_pct": 0.40,
            "stale": False,
            "n_members": 16,
            "n_quoted": 14,
            "tape_rank": 3,
            "cum_2d_pct": 0.80,
        },
    ],
}

_BASKET_PULSE_STALE = {
    "schema": "basket_pulse.v1",
    "as_of_utc": _TODAY + "T15:00:00Z",
    "session": "rth",
    "baskets": [
        {
            "id": "semicap_equipment",
            "live_ew_chg_pct": 0.40,  # percent units; stale=True → should NOT fire
            "stale": True,  # stale — should NOT fire
            "n_members": 16,
            "n_quoted": 0,
            "tape_rank": None,
        },
    ],
}

_BASKET_PULSE_NEGATIVE = {
    "schema": "basket_pulse.v1",
    "as_of_utc": _TODAY + "T15:00:00Z",
    "session": "rth",
    "baskets": [
        {
            "id": "semicap_equipment",
            "live_ew_chg_pct": -0.75,  # percent units: -0.75% — not a disagreement
            "stale": False,
            "n_members": 16,
            "n_quoted": 14,
        },
    ],
}


# ---------------------------------------------------------------------------
# (1) IGNITION transition detection
# ---------------------------------------------------------------------------

class TestIgnitionTransitionDetection:
    def test_fires_on_ignition_state(self):
        state = {}
        results = NTE._detect_ignition_transitions(_TURN_WATCH_IGNITION, state, _TODAY)
        basket_ids = [r[0] for r in results]
        assert "semicap_equipment" in basket_ids

    def test_does_not_fire_on_watch_state(self):
        state = {}
        results = NTE._detect_ignition_transitions(_TURN_WATCH_IGNITION, state, _TODAY)
        basket_ids = [r[0] for r in results]
        assert "memory_storage" not in basket_ids

    def test_does_not_fire_on_empty_baskets(self):
        state = {}
        results = NTE._detect_ignition_transitions(_TURN_WATCH_EMPTY, state, _TODAY)
        assert results == []

    def test_fires_exactly_once_per_basket_day(self):
        """First call fires; second call (same basket, same day) does NOT fire."""
        state = {}
        results1 = NTE._detect_ignition_transitions(_TURN_WATCH_IGNITION, state, _TODAY)
        # Mark as fired (simulates what run() does)
        for basket_id, _ in results1:
            NTE._mark_fired(state, "ignition", basket_id, _TODAY)

        results2 = NTE._detect_ignition_transitions(_TURN_WATCH_IGNITION, state, _TODAY)
        assert results2 == []


# ---------------------------------------------------------------------------
# (2) Per-day dedup
# ---------------------------------------------------------------------------

class TestPerDayDedup:
    def test_same_basket_same_day_no_refire(self):
        state = {}
        NTE._mark_fired(state, "ignition", "semicap_equipment", _TODAY)
        results = NTE._detect_ignition_transitions(_TURN_WATCH_IGNITION, state, _TODAY)
        assert all(r[0] != "semicap_equipment" for r in results)

    def test_different_day_refires(self):
        """A different date should allow re-firing."""
        state = {}
        NTE._mark_fired(state, "ignition", "semicap_equipment", "2026-07-08")
        results = NTE._detect_ignition_transitions(_TURN_WATCH_IGNITION, state, _TODAY)
        basket_ids = [r[0] for r in results]
        assert "semicap_equipment" in basket_ids

    def test_dedup_key_format(self):
        key = NTE._dedup_key("ignition", "semicap_equipment", _TODAY)
        assert key == f"ignition|semicap_equipment|{_TODAY}"

    def test_already_fired_true(self):
        state = {}
        NTE._mark_fired(state, "ignition", "foo", _TODAY)
        assert NTE._already_fired(state, "ignition", "foo", _TODAY) is True

    def test_already_fired_false(self):
        assert NTE._already_fired({}, "ignition", "foo", _TODAY) is False


# ---------------------------------------------------------------------------
# (3) Shock activation detection
# ---------------------------------------------------------------------------

class TestShockActivationDetection:
    def test_fires_when_active(self):
        state = {}
        results = NTE._detect_shock_activation(_SHOCK_ACTIVE, state, _TODAY)
        assert len(results) == 1
        assert results[0][0] == "shock_state"

    def test_no_fire_when_inactive(self):
        state = {}
        results = NTE._detect_shock_activation(_SHOCK_INACTIVE, state, _TODAY)
        assert results == []

    def test_no_refire_on_persistence(self):
        """Active shock that has already fired today should not re-fire."""
        state = {}
        NTE._mark_fired(state, "shock_activation", "shock_state", _TODAY)
        results = NTE._detect_shock_activation(_SHOCK_ACTIVE, state, _TODAY)
        assert results == []

    def test_message_contains_score(self):
        state = {}
        results = NTE._detect_shock_activation(_SHOCK_ACTIVE, state, _TODAY)
        assert len(results) == 1
        assert "75" in results[0][1]


# ---------------------------------------------------------------------------
# (4) Tape disagreement detection
# ---------------------------------------------------------------------------

class TestTapeDisagreementDetection:
    def test_fires_for_ignition_basket_with_positive_live_tape(self):
        state = {}
        with patch.object(NTE, "_lookup_slow_reco", return_value="hold"):
            results = NTE._detect_tape_disagreement(
                _BASKET_PULSE_WITH_IGNITION, _TURN_WATCH_IGNITION, state, _TODAY
            )
        basket_ids = [r[0] for r in results]
        assert "semicap_equipment" in basket_ids

    def test_no_fire_for_stale_quotes(self):
        state = {}
        with patch.object(NTE, "_lookup_slow_reco", return_value="hold"):
            results = NTE._detect_tape_disagreement(
                _BASKET_PULSE_STALE, _TURN_WATCH_IGNITION, state, _TODAY
            )
        assert results == []

    def test_no_fire_for_negative_live_tape(self):
        state = {}
        with patch.object(NTE, "_lookup_slow_reco", return_value="hold"):
            results = NTE._detect_tape_disagreement(
                _BASKET_PULSE_NEGATIVE, _TURN_WATCH_IGNITION, state, _TODAY
            )
        assert results == []

    def test_no_fire_when_slow_reco_enter(self):
        """If slow reco is 'enter', tape and slow agree — not a disagreement."""
        state = {}
        with patch.object(NTE, "_lookup_slow_reco", return_value="enter"):
            results = NTE._detect_tape_disagreement(
                _BASKET_PULSE_WITH_IGNITION, _TURN_WATCH_IGNITION, state, _TODAY
            )
        assert results == []

    def test_no_fire_when_slow_reco_accumulate(self):
        state = {}
        with patch.object(NTE, "_lookup_slow_reco", return_value="accumulate"):
            results = NTE._detect_tape_disagreement(
                _BASKET_PULSE_WITH_IGNITION, _TURN_WATCH_IGNITION, state, _TODAY
            )
        assert results == []

    def test_no_refire_same_day(self):
        state = {}
        NTE._mark_fired(state, "tape_disagreement", "semicap_equipment", _TODAY)
        with patch.object(NTE, "_lookup_slow_reco", return_value="hold"):
            results = NTE._detect_tape_disagreement(
                _BASKET_PULSE_WITH_IGNITION, _TURN_WATCH_IGNITION, state, _TODAY
            )
        assert all(r[0] != "semicap_equipment" for r in results)

    def test_no_fire_when_not_ignition(self):
        """WATCH basket should not produce a disagreement alert."""
        state = {}
        turn_watch_watch_only = {
            "schema": "basket_turn_watch.v1",
            "as_of": _TODAY,
            "baskets": [
                {
                    "basket_id": "semicap_equipment",
                    "state": "WATCH",  # not IGNITION
                    "k": 2,
                    "legs": {"impulse_day": True, "rs_z": False},
                    "as_of": _TODAY,
                }
            ],
        }
        with patch.object(NTE, "_lookup_slow_reco", return_value="hold"):
            results = NTE._detect_tape_disagreement(
                _BASKET_PULSE_WITH_IGNITION, turn_watch_watch_only, state, _TODAY
            )
        assert results == []


# ---------------------------------------------------------------------------
# (5) Absent webhook — dark mode
# ---------------------------------------------------------------------------

class TestAbsentWebhookDarkMode:
    def test_run_exits_zero_when_no_webhook(self, tmp_path):
        """run() returns 0 and never raises when webhook is absent."""
        with (
            patch.object(NTE, "_TURN_WATCH_PATH", tmp_path / "turn_watch.json"),
            patch.object(NTE, "_SHOCK_STATE_PATH", tmp_path / "shock_state.json"),
            patch.object(NTE, "_BASKET_PULSE_PATH", tmp_path / "basket_pulse.json"),
            patch.object(NTE, "_NOTIFY_STATE_PATH", tmp_path / "notify_state.json"),
            patch("scripts.notify_turn_events.config") as mock_cfg,
        ):
            mock_cfg.secret.return_value = None  # no webhook
            # Write fixture data
            (tmp_path / "turn_watch.json").write_text(
                json.dumps(_TURN_WATCH_IGNITION)
            )
            (tmp_path / "shock_state.json").write_text(json.dumps(_SHOCK_ACTIVE))
            (tmp_path / "basket_pulse.json").write_text(
                json.dumps(_BASKET_PULSE_WITH_IGNITION)
            )
            result = NTE.run(today_str=_TODAY)
        assert result == 0

    def test_send_discord_returns_false_when_no_url(self):
        with patch("scripts.notify_turn_events.config") as mock_cfg:
            mock_cfg.secret.return_value = None
            result = NTE._send_discord("test message")
        assert result is False


# ---------------------------------------------------------------------------
# (6) Copy contract — no forbidden words
# ---------------------------------------------------------------------------

class TestCopyContract:
    def test_ignition_message_no_forbidden_words(self):
        legs = {
            "impulse_day": True,
            "rs_z": True,
            "volume_confirm": True,
            "complex_confirm": True,
            "breadth_surge": False,
            "shock_relative_bid": False,
        }
        msg = NTE._ignition_message("semicap_equipment", legs, _TODAY)
        lower = msg.lower().split()
        for word in NTE.FORBIDDEN_WORDS:
            assert word not in lower, f"Forbidden word '{word}' found in: {msg}"

    def test_shock_activation_message_no_forbidden_words(self):
        msg = NTE._shock_activation_message(75, _TODAY, "driver_flip")
        lower = msg.lower().split()
        for word in NTE.FORBIDDEN_WORDS:
            assert word not in lower, f"Forbidden word '{word}' found in: {msg}"

    def test_tape_disagreement_message_no_forbidden_words(self):
        # live_ew_chg_pct is in percent units (e.g. 0.40 = +0.40%)
        msg = NTE._tape_disagreement_message("semicap_equipment", 0.40, _TODAY)
        lower = msg.lower().split()
        for word in NTE.FORBIDDEN_WORDS:
            assert word not in lower, f"Forbidden word '{word}' found in: {msg}"

    def test_tape_disagreement_message_percent_scale(self):
        """live_ew_chg_pct is already a percent: 0.40 must render as +0.40%, NOT +40.00%."""
        msg = NTE._tape_disagreement_message("semicap_equipment", 0.40, _TODAY)
        assert "+0.40%" in msg, f"Expected '+0.40%' in message, got: {msg}"
        assert "40.00%" not in msg, f"Expected NOT to find '40.00%' (scale bug) in: {msg}"

    def test_tape_disagreement_message_sub_one_percent_scale(self):
        """Values < 1 (e.g. 0.75%) must NOT be multiplied by 100."""
        msg = NTE._tape_disagreement_message("test_basket", 0.75, _TODAY)
        assert "+0.75%" in msg, f"Expected '+0.75%' in message, got: {msg}"
        assert "75.00%" not in msg

    def test_ignition_message_contains_fade_copy(self):
        legs = {"impulse_day": True, "rs_z": True}
        msg = NTE._ignition_message("test_basket", legs, _TODAY)
        assert "58%" in msg
        assert "T+1" in msg

    def test_ignition_message_contains_as_of(self):
        legs = {"impulse_day": True, "rs_z": True}
        msg = NTE._ignition_message("test_basket", legs, _TODAY)
        assert _TODAY in msg

    def test_shock_message_contains_display_tier(self):
        msg = NTE._shock_activation_message(75, _TODAY, None)
        assert "display-tier" in msg.lower()

    def test_disagreement_message_contains_expected_null(self):
        msg = NTE._tape_disagreement_message("test_basket", 0.20, _TODAY)
        assert "expected-null" in msg.lower()

    def test_ignition_message_contains_k_count(self):
        legs = {
            "impulse_day": True,
            "rs_z": True,
            "volume_confirm": True,
            "complex_confirm": True,
        }
        msg = NTE._ignition_message("test_basket", legs, _TODAY)
        assert "K=4" in msg

    def test_ignition_message_lists_active_legs(self):
        legs = {
            "impulse_day": True,
            "rs_z": True,
            "volume_confirm": False,
        }
        msg = NTE._ignition_message("test_basket", legs, _TODAY)
        assert "impulse_day" in msg
        assert "rs_z" in msg

    def test_forbidden_word_guard_catches_exact_word(self):
        """_assert_no_forbidden_words raises on an exact forbidden word."""
        import pytest as _pytest
        with _pytest.raises(ValueError, match="buy"):
            NTE._assert_no_forbidden_words("IGNITION — buy this basket")

    def test_forbidden_word_guard_catches_word_boundary_compound(self):
        """Hyphenated forms like 'buy-side' contain the boundary word 'buy'."""
        import pytest as _pytest
        with _pytest.raises(ValueError, match="buy"):
            NTE._assert_no_forbidden_words("IGNITION — buy-side flow detected")

    def test_tape_disagreement_message_uses_pulse_as_of(self):
        """tape_as_of is the pulse as_of_utc, not the nightly turn_watch date."""
        pulse_as_of = _TODAY + "T14:30:00Z"
        msg = NTE._tape_disagreement_message("test_basket", 0.50, pulse_as_of)
        assert pulse_as_of in msg


# ---------------------------------------------------------------------------
# (7) Dedup state loading — tolerant of missing file
# ---------------------------------------------------------------------------

class TestDedupStateTolerance:
    def test_load_notify_state_returns_empty_dict_when_missing(self, tmp_path):
        with patch.object(NTE, "_NOTIFY_STATE_PATH", tmp_path / "nonexistent.json"):
            state = NTE._load_notify_state()
        assert state == {}

    def test_load_notify_state_returns_empty_on_corrupt_json(self, tmp_path):
        corrupt = tmp_path / "notify_state.json"
        corrupt.write_text("{ this is not valid json }")
        with patch.object(NTE, "_NOTIFY_STATE_PATH", corrupt):
            state = NTE._load_notify_state()
        assert state == {}

    def test_save_notify_state_is_noop_in_dry_run(self, tmp_path):
        path = tmp_path / "notify_state.json"
        with patch.object(NTE, "_NOTIFY_STATE_PATH", path):
            NTE._save_notify_state({"key": True}, dry_run=True)
        assert not path.exists()

    def test_save_and_load_roundtrip(self, tmp_path):
        path = tmp_path / "notify_state.json"
        state = {"ignition|semicap_equipment|2026-07-09": True}
        with patch.object(NTE, "_NOTIFY_STATE_PATH", path):
            NTE._save_notify_state(state, dry_run=False)
            loaded = NTE._load_notify_state()
        assert loaded == state


# ---------------------------------------------------------------------------
# (8) run() never raises — exit-0 contract
# ---------------------------------------------------------------------------

class TestRunExitZeroContract:
    def test_run_does_not_raise_with_missing_files(self, tmp_path):
        """run() must not raise even when all source files are absent."""
        with (
            patch.object(NTE, "_TURN_WATCH_PATH", tmp_path / "missing.json"),
            patch.object(NTE, "_SHOCK_STATE_PATH", tmp_path / "missing2.json"),
            patch.object(NTE, "_BASKET_PULSE_PATH", tmp_path / "missing3.json"),
            patch.object(NTE, "_NOTIFY_STATE_PATH", tmp_path / "notify_state.json"),
            patch("scripts.notify_turn_events.config") as mock_cfg,
        ):
            mock_cfg.secret.return_value = None
            result = NTE.run(today_str=_TODAY)
        assert result == 0

    def test_run_dispatches_when_webhook_present(self, tmp_path):
        """With a webhook configured and IGNITION data, run() dispatches and returns > 0."""
        (tmp_path / "turn_watch.json").write_text(json.dumps(_TURN_WATCH_IGNITION))
        (tmp_path / "shock_state.json").write_text(json.dumps(_SHOCK_INACTIVE))
        (tmp_path / "basket_pulse.json").write_text(json.dumps({}))
        notify_state_path = tmp_path / "notify_state.json"

        with (
            patch.object(NTE, "_TURN_WATCH_PATH", tmp_path / "turn_watch.json"),
            patch.object(NTE, "_SHOCK_STATE_PATH", tmp_path / "shock_state.json"),
            patch.object(NTE, "_BASKET_PULSE_PATH", tmp_path / "basket_pulse.json"),
            patch.object(NTE, "_NOTIFY_STATE_PATH", notify_state_path),
            patch("scripts.notify_turn_events.config") as mock_cfg,
            patch("scripts.notify_turn_events.requests.post") as mock_post,
        ):
            mock_cfg.secret.return_value = "https://discord.example.com/webhook"
            mock_response = MagicMock()
            mock_response.status_code = 204
            mock_post.return_value = mock_response

            result = NTE.run(today_str=_TODAY)

        # semicap_equipment is in IGNITION → should dispatch
        assert result >= 1

    def test_run_does_not_refire_on_second_call(self, tmp_path):
        """Second run() call in the same day should send 0 new messages."""
        (tmp_path / "turn_watch.json").write_text(json.dumps(_TURN_WATCH_IGNITION))
        (tmp_path / "shock_state.json").write_text(json.dumps(_SHOCK_INACTIVE))
        (tmp_path / "basket_pulse.json").write_text(json.dumps({}))
        notify_state_path = tmp_path / "notify_state.json"

        with (
            patch.object(NTE, "_TURN_WATCH_PATH", tmp_path / "turn_watch.json"),
            patch.object(NTE, "_SHOCK_STATE_PATH", tmp_path / "shock_state.json"),
            patch.object(NTE, "_BASKET_PULSE_PATH", tmp_path / "basket_pulse.json"),
            patch.object(NTE, "_NOTIFY_STATE_PATH", notify_state_path),
            patch("scripts.notify_turn_events.config") as mock_cfg,
            patch("scripts.notify_turn_events.requests.post") as mock_post,
        ):
            mock_cfg.secret.return_value = "https://discord.example.com/webhook"
            mock_response = MagicMock()
            mock_response.status_code = 204
            mock_post.return_value = mock_response

            # First run
            r1 = NTE.run(today_str=_TODAY)
            # Second run — same day, same data
            r2 = NTE.run(today_str=_TODAY)

        assert r1 >= 1
        assert r2 == 0  # no re-fire
