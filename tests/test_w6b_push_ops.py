"""W6b push spine tests — Neural Web W6b.

Guards the W6b adapter (push_ops_alert) and per-lane ledger design:

1. ADAPTER BEHAVIOR: message preserved verbatim; severity mapped; dedup window
   enforced; disabled-config no-op.
2. PER-LANE SINGLE-WRITER: each lane writes only to its own ledger file.
3. CROSS-LANE DEDUP: a key in one lane's ledger suppresses dispatch to the
   same key from another lane within the window.
4. STATIC GUARD: the 3 migrated senders no longer call send_telegram directly
   (they call push_ops_alert instead).
5. ENABLED STATE: config.yml has alert_push.enabled=true (W6b operator event).
"""
from __future__ import annotations

import json
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from engine import alert_triage as at

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_NOW = datetime(2026, 7, 4, 12, 0, 0, tzinfo=timezone.utc)
_PAST_IN_WINDOW = _NOW - timedelta(hours=3)   # within a 6-hour window
_PAST_OUT_WINDOW = _NOW - timedelta(hours=8)  # outside a 6-hour window


def _write_sent_record(path: Path, source: str, type_: str, sent_at: datetime) -> None:
    rec = {
        "source": source,
        "type": type_,
        "asset": "",
        "headline": "test",
        "priority": -1,
        "sent_at": sent_at.strftime("%Y-%m-%dT%H:%M:%SZ"),
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "a", encoding="utf-8") as fh:
        fh.write(json.dumps(rec) + "\n")


def _enabled_cfg(tmp_root: Path) -> None:
    """Patch config.load() to return alert_push.enabled=true."""
    pass  # We patch per-test via monkeypatch or patch()


# ---------------------------------------------------------------------------
# 1. DISABLED CONFIG — pure no-op
# ---------------------------------------------------------------------------

class TestDisabledConfig:
    def test_no_dispatch_when_disabled(self, tmp_path):
        with patch("engine.alert_triage.config") as mock_cfg:
            mock_cfg.load.return_value = {"alert_push": {"enabled": False, "window_hours": 6}}
            mock_cfg.data_dir.return_value = tmp_path / "data"
            result = at.push_ops_alert(
                source="healthcheck",
                type_="heartbeat_failed",
                message="test",
                severity="critical",
                lane="healthcheck",
                _now=_NOW,
            )
        assert result is False

    def test_no_ledger_written_when_disabled(self, tmp_path):
        with patch("engine.alert_triage.config") as mock_cfg:
            mock_cfg.load.return_value = {"alert_push": {"enabled": False, "window_hours": 6}}
            mock_cfg.data_dir.return_value = tmp_path / "data"
            at.push_ops_alert(
                source="signal_sanity",
                type_="tripwire_failed",
                message="test",
                severity="critical",
                lane="signal_sanity",
                _now=_NOW,
            )
        ledger = tmp_path / "data" / "alert_triage" / "push_sent_signal_sanity.jsonl"
        assert not ledger.exists()


# ---------------------------------------------------------------------------
# 2. ADAPTER BEHAVIOR — message preserved, dedup enforced
# ---------------------------------------------------------------------------

class TestAdapterBehavior:
    def _patch_enabled(self):
        """Context manager: patch config to enabled=true."""
        return patch("engine.alert_triage.config", **{
            "load.return_value": {"alert_push": {"enabled": True, "window_hours": 6}},
            "data_dir.return_value": None,  # overridden per-call via root=
        })

    def test_message_preserved_verbatim(self, tmp_path):
        """The message sent to send_telegram must match the caller's message exactly."""
        sent_messages = []

        def fake_send_telegram(msg):
            sent_messages.append(msg)
            return True

        with patch("engine.alert_triage.config") as mock_cfg:
            mock_cfg.load.return_value = {"alert_push": {"enabled": True, "window_hours": 6}}
            with patch("scripts.notify.send_telegram", fake_send_telegram), \
                 patch("scripts.notify.send_discord", return_value=False):
                at.push_ops_alert(
                    source="basket_freeze",
                    type_="churn_guard",
                    message="EXACT MESSAGE CONTENT",
                    severity="critical",
                    lane="basket_freeze",
                    root=tmp_path,
                    _now=_NOW,
                )

        assert len(sent_messages) == 1
        assert sent_messages[0] == "EXACT MESSAGE CONTENT"

    def test_severity_recorded_in_ledger(self, tmp_path):
        """The severity parameter must be stored in the per-lane ledger."""
        with patch("engine.alert_triage.config") as mock_cfg:
            mock_cfg.load.return_value = {"alert_push": {"enabled": True, "window_hours": 6}}
            with patch("scripts.notify.send_telegram", return_value=True), \
                 patch("scripts.notify.send_discord", return_value=False):
                at.push_ops_alert(
                    source="signal_sanity",
                    type_="tripwire_failed",
                    message="sanity failed",
                    severity="major",
                    lane="signal_sanity",
                    root=tmp_path,
                    _now=_NOW,
                )

        ledger = tmp_path / "data" / "alert_triage" / "push_sent_signal_sanity.jsonl"
        assert ledger.exists()
        rec = json.loads(ledger.read_text().strip())
        assert rec["severity"] == "major"
        assert rec["source"] == "signal_sanity"
        assert rec["type"] == "tripwire_failed"

    def test_dedup_window_suppresses_repeat(self, tmp_path):
        """A key sent within the dedup window must not be dispatched again."""
        # Pre-populate the ledger with a recent send
        ledger = tmp_path / "data" / "alert_triage" / "push_sent_signal_sanity.jsonl"
        _write_sent_record(ledger, "signal_sanity", "tripwire_failed", _PAST_IN_WINDOW)

        dispatched = []

        with patch("engine.alert_triage.config") as mock_cfg:
            mock_cfg.load.return_value = {"alert_push": {"enabled": True, "window_hours": 6}}
            mock_cfg.data_dir.return_value = tmp_path / "data"
            with patch("scripts.notify.send_telegram") as mock_tg:
                result = at.push_ops_alert(
                    source="signal_sanity",
                    type_="tripwire_failed",
                    message="repeat fire",
                    severity="critical",
                    lane="signal_sanity",
                    root=tmp_path,
                    _now=_NOW,
                )

        assert result is False
        # send_telegram must not have been called
        mock_tg.assert_not_called() if hasattr(mock_tg, "assert_not_called") else None

    def test_outside_dedup_window_dispatches(self, tmp_path):
        """A key sent outside the dedup window must be dispatched again."""
        ledger = tmp_path / "data" / "alert_triage" / "push_sent_healthcheck.jsonl"
        _write_sent_record(ledger, "healthcheck", "heartbeat_failed", _PAST_OUT_WINDOW)

        with patch("engine.alert_triage.config") as mock_cfg:
            mock_cfg.load.return_value = {"alert_push": {"enabled": True, "window_hours": 6}}
            mock_cfg.data_dir.return_value = tmp_path / "data"
            with patch("scripts.notify.send_telegram", return_value=True), \
                 patch("scripts.notify.send_discord", return_value=False):
                result = at.push_ops_alert(
                    source="healthcheck",
                    type_="heartbeat_failed",
                    message="heartbeat failed",
                    severity="critical",
                    lane="healthcheck",
                    root=tmp_path,
                    _now=_NOW,
                )

        assert result is True


# ---------------------------------------------------------------------------
# 3. PER-LANE SINGLE-WRITER
# ---------------------------------------------------------------------------

class TestPerLaneLedger:
    def test_basket_freeze_writes_to_own_lane(self, tmp_path):
        """basket_freeze must write to push_sent_basket_freeze.jsonl only."""
        with patch("engine.alert_triage.config") as mock_cfg:
            mock_cfg.load.return_value = {"alert_push": {"enabled": True, "window_hours": 6}}
            with patch("scripts.notify.send_telegram", return_value=True), \
                 patch("scripts.notify.send_discord", return_value=False):
                at.push_ops_alert(
                    source="basket_freeze",
                    type_="churn_guard",
                    message="freeze skipped",
                    severity="critical",
                    lane="basket_freeze",
                    root=tmp_path,
                    _now=_NOW,
                )

        triage_dir = tmp_path / "data" / "alert_triage"
        written = sorted(p.name for p in triage_dir.iterdir())
        # Only the basket_freeze lane file should exist
        assert "push_sent_basket_freeze.jsonl" in written
        assert "push_sent_signal_sanity.jsonl" not in written
        assert "push_sent_healthcheck.jsonl" not in written
        assert "push_sent.jsonl" not in written  # original lane not written by ops adapter

    def test_signal_sanity_writes_to_own_lane(self, tmp_path):
        with patch("engine.alert_triage.config") as mock_cfg:
            mock_cfg.load.return_value = {"alert_push": {"enabled": True, "window_hours": 6}}
            with patch("scripts.notify.send_telegram", return_value=True), \
                 patch("scripts.notify.send_discord", return_value=False):
                at.push_ops_alert(
                    source="signal_sanity",
                    type_="tripwire_failed",
                    message="sanity tripped",
                    severity="critical",
                    lane="signal_sanity",
                    root=tmp_path,
                    _now=_NOW,
                )

        triage_dir = tmp_path / "data" / "alert_triage"
        written = sorted(p.name for p in triage_dir.iterdir())
        assert "push_sent_signal_sanity.jsonl" in written
        assert "push_sent_basket_freeze.jsonl" not in written
        assert "push_sent_healthcheck.jsonl" not in written

    def test_healthcheck_writes_to_own_lane(self, tmp_path):
        with patch("engine.alert_triage.config") as mock_cfg:
            mock_cfg.load.return_value = {"alert_push": {"enabled": True, "window_hours": 6}}
            with patch("scripts.notify.send_telegram", return_value=True), \
                 patch("scripts.notify.send_discord", return_value=False):
                at.push_ops_alert(
                    source="healthcheck",
                    type_="heartbeat_failed",
                    message="pipeline dead",
                    severity="critical",
                    lane="healthcheck",
                    root=tmp_path,
                    _now=_NOW,
                )

        triage_dir = tmp_path / "data" / "alert_triage"
        written = sorted(p.name for p in triage_dir.iterdir())
        assert "push_sent_healthcheck.jsonl" in written
        assert "push_sent_basket_freeze.jsonl" not in written
        assert "push_sent_signal_sanity.jsonl" not in written

    def test_explicit_dedup_store_path_used_when_provided(self, tmp_path):
        """_dedup_store override routes the write to the specified path."""
        override = tmp_path / "custom_dedup.jsonl"
        with patch("engine.alert_triage.config") as mock_cfg:
            mock_cfg.load.return_value = {"alert_push": {"enabled": True, "window_hours": 6}}
            with patch("scripts.notify.send_telegram", return_value=True), \
                 patch("scripts.notify.send_discord", return_value=False):
                at.push_ops_alert(
                    source="basket_freeze",
                    type_="churn_guard",
                    message="msg",
                    severity="critical",
                    lane="basket_freeze",
                    root=tmp_path,
                    _now=_NOW,
                    _dedup_store=override,
                )
        assert override.exists()
        rec = json.loads(override.read_text().strip())
        assert rec["source"] == "basket_freeze"


# ---------------------------------------------------------------------------
# 4. CROSS-LANE DEDUP (read-many)
# ---------------------------------------------------------------------------

class TestCrossLaneDedup:
    def test_prior_send_in_different_lane_suppresses(self, tmp_path):
        """A key already sent by basket_freeze must suppress re-send from signal_sanity."""
        # Write a record to the basket_freeze lane (same source+type key)
        bf_ledger = tmp_path / "data" / "alert_triage" / "push_sent_basket_freeze.jsonl"
        _write_sent_record(bf_ledger, "basket_freeze", "churn_guard", _PAST_IN_WINDOW)

        with patch("engine.alert_triage.config") as mock_cfg:
            mock_cfg.load.return_value = {"alert_push": {"enabled": True, "window_hours": 6}}
            mock_cfg.data_dir.return_value = tmp_path / "data"
            with patch("scripts.notify.send_telegram") as mock_tg:
                # Now signal_sanity fires with the same source+type combination
                result = at.push_ops_alert(
                    source="basket_freeze",
                    type_="churn_guard",
                    message="duplicate attempt from signal_sanity lane",
                    severity="major",
                    lane="signal_sanity",  # different lane, but same dedup key
                    root=tmp_path,
                    _now=_NOW,
                )

        assert result is False

    def test_different_type_same_source_not_suppressed(self, tmp_path):
        """Different type from same source must NOT be suppressed."""
        bf_ledger = tmp_path / "data" / "alert_triage" / "push_sent_basket_freeze.jsonl"
        _write_sent_record(bf_ledger, "basket_freeze", "churn_guard", _PAST_IN_WINDOW)

        with patch("engine.alert_triage.config") as mock_cfg:
            mock_cfg.load.return_value = {"alert_push": {"enabled": True, "window_hours": 6}}
            mock_cfg.data_dir.return_value = tmp_path / "data"
            with patch("scripts.notify.send_telegram", return_value=True), \
                 patch("scripts.notify.send_discord", return_value=False):
                result = at.push_ops_alert(
                    source="basket_freeze",
                    type_="OTHER_TYPE",   # different type
                    message="different type should dispatch",
                    severity="major",
                    lane="basket_freeze",
                    root=tmp_path,
                    _now=_NOW,
                )

        assert result is True


# ---------------------------------------------------------------------------
# 5. STATIC GUARD — migrated senders no longer call send_telegram directly
# ---------------------------------------------------------------------------

class TestStaticGuard:
    """Verify that the three migrated call sites no longer contain direct
    send_telegram calls in their _notify / alert paths.
    """

    def test_basket_freeze_no_direct_send_telegram(self):
        """engine/basket_freeze.py churn_guard block must not call send_telegram directly."""
        import inspect
        from engine import basket_freeze
        src = inspect.getsource(basket_freeze)
        # The churn_guard block no longer imports send_telegram from scripts.notify
        # Look for the specific pattern that was replaced
        # The old pattern was: from scripts.notify import send_telegram, send_discord
        # followed by direct send_telegram(alert_msg) in the churn_guard block.
        # We verify the replacement: push_ops_alert is now imported instead.
        assert "push_ops_alert" in src, "basket_freeze must import push_ops_alert"
        # The specific direct-send pattern should no longer appear in the churn_guard block
        # (it may still appear in other non-migrated parts of the file — we check the block)
        lines = src.split("\n")
        in_churn_guard = False
        for line in lines:
            if "churn_guard" in line and "push_ops_alert" in line:
                break
            if "TRUNCATION GUARD TRIGGERED" in line:
                in_churn_guard = True
            if in_churn_guard and "send_telegram(alert_msg)" in line:
                pytest.fail("basket_freeze churn_guard block still calls send_telegram directly")

    def test_signal_sanity_no_direct_send_telegram_in_notify(self):
        """scripts/signal_sanity.py _notify() must not call send_telegram directly.

        We check for the actual call pattern (send_telegram() or send_telegram(msg))
        rather than the bare string, because docstrings may reference the old name.
        """
        import inspect
        from scripts import signal_sanity
        src = inspect.getsource(signal_sanity._notify)
        # The direct-call pattern: send_telegram( followed by arguments
        # Docstring mentions are allowed; what is forbidden is an actual call site
        import re
        direct_calls = re.findall(r'\bsend_telegram\s*\(', src)
        assert len(direct_calls) == 0, (
            f"signal_sanity._notify still has {len(direct_calls)} direct send_telegram() call(s) "
            "— W6b migration failed"
        )
        assert "push_ops_alert" in src, "signal_sanity._notify must use push_ops_alert"

    def test_healthcheck_no_direct_send_telegram_in_notify(self):
        """scripts/healthcheck.py _notify() must not call send_telegram directly.

        Same rationale: check for call pattern, not bare string mention.
        """
        import inspect
        import re
        from scripts import healthcheck
        src = inspect.getsource(healthcheck._notify)
        direct_calls = re.findall(r'\bsend_telegram\s*\(', src)
        assert len(direct_calls) == 0, (
            f"healthcheck._notify still has {len(direct_calls)} direct send_telegram() call(s) "
            "— W6b migration failed"
        )
        assert "push_ops_alert" in src, "healthcheck._notify must use push_ops_alert"


# ---------------------------------------------------------------------------
# 6. ENABLED STATE in config.yml
# ---------------------------------------------------------------------------

class TestConfigEnabledState:
    def test_config_yml_alert_push_enabled(self):
        """config.yml must have alert_push.enabled=true after W6b."""
        from lib import config
        cfg = config.load()
        push_cfg = cfg.get("alert_push") or {}
        assert push_cfg.get("enabled") is True, (
            "config.yml alert_push.enabled must be true (W6b operator Article-2 event). "
            "If this test fails, the operator gate was not enabled in this PR."
        )
        assert push_cfg.get("threshold", 0) >= 60, "threshold must be >= 60"
        assert push_cfg.get("window_hours", 0) >= 1, "window_hours must be >= 1"

    def test_ops_lane_constants_match_synapse_registered_lanes(self):
        """_OPS_LANES in alert_triage must include the 3 migrated senders."""
        lanes = at._OPS_LANES
        for expected in ("basket_freeze", "signal_sanity", "healthcheck"):
            assert expected in lanes, f"_OPS_LANES missing lane '{expected}'"
        # Each value must be a distinct file name
        file_names = list(lanes.values())
        assert len(file_names) == len(set(file_names)), "Lane file names must be unique (single-writer law)"
