"""Tests for CSP-W6 forward-ledger heartbeat — scripts/check_ledger_advance.py.

Guards:
1. Advance is silent: when a ledger's asof advances and render happened, no
   stall is returned and no alert fires.
2. Stall + render = one ledger_stall alert: stalled list is non-empty and
   _dispatch_stall_alert fires push_ops_alert with type_=ledger_stall.
3. Stall without render = no stall row (no escalation without republish).
4. Weekend = skip: a non-trading day returns empty, no state mutation.
5. Double-run = no dup: same-calendar-day re-run does NOT produce a stall
   (idempotent per last_check_date guard).
6. Missing ledger file is silently skipped (no stall for absent files).
7. State is persisted and the next-run prev_asof reflects current-run curr_asof.
8. Multiple stalls in one run: all stalled ledgers returned; one combined alert.
9. Corrupt state file → fail-open, treated as empty.
10. push_ops_alert failure → fail-open, no crash.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

import pytest

from scripts import check_ledger_advance as M

# ── shared datetimes ────────────────────────────────────────────────────────
# Use Thursdays/Fridays (guaranteed trading days; not near US holidays).
_D1 = datetime(2026, 7, 16, 22, 0, 0, tzinfo=timezone.utc)  # Thu, first run
_D2 = datetime(2026, 7, 17, 22, 0, 0, tzinfo=timezone.utc)  # Fri, second run

# Saturday (non-trading day)
_SAT = datetime(2026, 7, 19, 22, 0, 0, tzinfo=timezone.utc)


# ── helpers ────────────────────────────────────────────────────────────────

def _write_jsonl(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(json.dumps(r) for r in rows) + "\n", encoding="utf-8")


def _write_state(state_path: Path, ledgers: dict) -> None:
    state_path.parent.mkdir(parents=True, exist_ok=True)
    state_path.write_text(
        json.dumps({
            "schema": "ledger_heartbeat_state.v1",
            "updated_utc": None,
            "last_check_date": None,
            "ledgers": ledgers,
        }),
        encoding="utf-8",
    )


def _load_state(state_path: Path) -> dict:
    return json.loads(state_path.read_text(encoding="utf-8"))


class _Dispatch:
    """Records push_ops_alert calls."""
    def __init__(self):
        self.calls: list[dict] = []

    def __call__(self, *, source, type_, message, severity, lane, root):
        self.calls.append(dict(source=source, type_=type_, message=message,
                               severity=severity, lane=lane))


# ── Test 1: advance is silent ──────────────────────────────────────────────

def test_advance_silent(tmp_path):
    """When ledger advances and render happened, no stall and no alert."""
    ledger = tmp_path / "data" / "risk_radar" / "forward_log.jsonl"
    _write_jsonl(ledger, [
        {"asof": "2026-07-15", "state": "caution"},
        {"asof": "2026-07-16", "state": "caution"},
    ])
    state_path = tmp_path / "data" / "ci" / "ledger_heartbeat_state.json"
    _write_state(state_path, {
        "data/risk_radar/forward_log.jsonl": {
            "asof": "2026-07-15",
            "last_check_date": "2026-07-16",
            "stalled_since": None,
        },
    })

    manifest = [{"path": "data/risk_radar/forward_log.jsonl", "label": "risk_radar"}]
    dispatch = _Dispatch()
    with (
        patch.object(M, "_LEDGER_MANIFEST", manifest),
        patch("engine.alert_triage.push_ops_alert", dispatch),
    ):
        stalled = M.run_check(
            root=tmp_path,
            state_path=state_path,
            render_happened=True,
            _now=_D2,
        )
        # Also verify the dispatch function doesn't fire
        M._dispatch_stall_alert(stalled, tmp_path)

    assert stalled == []
    assert dispatch.calls == []
    # State updated to new asof
    saved = _load_state(state_path)
    assert saved["ledgers"]["data/risk_radar/forward_log.jsonl"]["asof"] == "2026-07-16"


# ── Test 2: stall + render = alert fires ─────────────────────────────────

def test_stall_with_render(tmp_path):
    """Stall + render_happened=True → stall dict returned, push_ops_alert fires."""
    ledger = tmp_path / "data" / "risk_radar" / "forward_log.jsonl"
    _write_jsonl(ledger, [{"asof": "2026-07-15", "state": "caution"}])
    state_path = tmp_path / "data" / "ci" / "ledger_heartbeat_state.json"
    _write_state(state_path, {
        "data/risk_radar/forward_log.jsonl": {
            "asof": "2026-07-15",
            "last_check_date": "2026-07-16",  # yesterday
            "stalled_since": None,
        },
    })

    manifest = [{"path": "data/risk_radar/forward_log.jsonl", "label": "risk_radar"}]
    dispatch = _Dispatch()
    with (
        patch.object(M, "_LEDGER_MANIFEST", manifest),
        patch("engine.alert_triage.push_ops_alert", dispatch),
    ):
        stalled = M.run_check(
            root=tmp_path,
            state_path=state_path,
            render_happened=True,
            _now=_D2,
        )
        M._dispatch_stall_alert(stalled, tmp_path)

    assert len(stalled) == 1
    s = stalled[0]
    assert s["label"] == "risk_radar"
    assert s["prev_asof"] == "2026-07-15"
    assert s["curr_asof"] == "2026-07-15"
    assert len(dispatch.calls) == 1
    assert dispatch.calls[0]["type_"] == "ledger_stall"
    assert dispatch.calls[0]["source"] == "ledger_heartbeat"


# ── Test 3: stall without render = no stall row ──────────────────────────

def test_stall_without_render(tmp_path):
    """Stall + render_happened=False → empty (no escalation without republish)."""
    ledger = tmp_path / "data" / "risk_radar" / "forward_log.jsonl"
    _write_jsonl(ledger, [{"asof": "2026-07-15", "state": "caution"}])
    state_path = tmp_path / "data" / "ci" / "ledger_heartbeat_state.json"
    _write_state(state_path, {
        "data/risk_radar/forward_log.jsonl": {
            "asof": "2026-07-15",
            "last_check_date": "2026-07-16",
            "stalled_since": None,
        },
    })

    manifest = [{"path": "data/risk_radar/forward_log.jsonl", "label": "risk_radar"}]
    dispatch = _Dispatch()
    with (
        patch.object(M, "_LEDGER_MANIFEST", manifest),
        patch("engine.alert_triage.push_ops_alert", dispatch),
    ):
        stalled = M.run_check(
            root=tmp_path,
            state_path=state_path,
            render_happened=False,   # <-- no render
            _now=_D2,
        )
        M._dispatch_stall_alert(stalled, tmp_path)

    assert stalled == []
    assert dispatch.calls == []


# ── Test 4: weekend = skip ────────────────────────────────────────────────

def test_weekend_skip(tmp_path):
    """Non-trading day (Saturday) → empty, no state mutation."""
    ledger = tmp_path / "data" / "risk_radar" / "forward_log.jsonl"
    _write_jsonl(ledger, [{"asof": "2026-07-15", "state": "caution"}])
    state_path = tmp_path / "data" / "ci" / "ledger_heartbeat_state.json"
    initial_ledgers = {
        "data/risk_radar/forward_log.jsonl": {
            "asof": "2026-07-15",
            "last_check_date": "2026-07-17",
            "stalled_since": None,
        },
    }
    _write_state(state_path, initial_ledgers)

    manifest = [{"path": "data/risk_radar/forward_log.jsonl", "label": "risk_radar"}]
    dispatch = _Dispatch()
    with (
        patch.object(M, "_LEDGER_MANIFEST", manifest),
        patch("engine.alert_triage.push_ops_alert", dispatch),
    ):
        stalled = M.run_check(
            root=tmp_path,
            state_path=state_path,
            render_happened=True,
            _now=_SAT,  # Saturday
        )

    assert stalled == []
    assert dispatch.calls == []
    # State file not mutated on non-trading day
    saved = _load_state(state_path)
    assert saved["ledgers"]["data/risk_radar/forward_log.jsonl"]["last_check_date"] == "2026-07-17"


# ── Test 5: double-run = no dup ──────────────────────────────────────────

def test_double_run_idempotent(tmp_path):
    """Same-day re-run does not produce a second stall (idempotent)."""
    ledger = tmp_path / "data" / "risk_radar" / "forward_log.jsonl"
    _write_jsonl(ledger, [{"asof": "2026-07-16", "state": "caution"}])
    state_path = tmp_path / "data" / "ci" / "ledger_heartbeat_state.json"
    # Simulate state AFTER a first run today already recorded last_check_date=today
    _write_state(state_path, {
        "data/risk_radar/forward_log.jsonl": {
            "asof": "2026-07-16",
            "last_check_date": "2026-07-17",  # already ran today (_D2)
            "stalled_since": None,
        },
    })

    manifest = [{"path": "data/risk_radar/forward_log.jsonl", "label": "risk_radar"}]
    dispatch = _Dispatch()
    with (
        patch.object(M, "_LEDGER_MANIFEST", manifest),
        patch("engine.alert_triage.push_ops_alert", dispatch),
    ):
        stalled = M.run_check(
            root=tmp_path,
            state_path=state_path,
            render_happened=True,
            _now=_D2,  # 2026-07-17 — same day as last_check_date
        )
        M._dispatch_stall_alert(stalled, tmp_path)

    assert stalled == []
    assert dispatch.calls == []


# ── Test 6: missing ledger file is silently skipped ──────────────────────

def test_missing_ledger_skipped(tmp_path):
    """A ledger file that doesn't exist yet is silently skipped."""
    state_path = tmp_path / "data" / "ci" / "ledger_heartbeat_state.json"
    _write_state(state_path, {})

    manifest = [{"path": "data/leadership_crack/forward_log.jsonl", "label": "leadership_crack"}]
    dispatch = _Dispatch()
    with (
        patch.object(M, "_LEDGER_MANIFEST", manifest),
        patch("engine.alert_triage.push_ops_alert", dispatch),
    ):
        stalled = M.run_check(
            root=tmp_path,
            state_path=state_path,
            render_happened=True,
            _now=_D2,
        )
        M._dispatch_stall_alert(stalled, tmp_path)

    assert stalled == []
    assert dispatch.calls == []
    # State updated but curr_asof is None (file absent)
    saved = _load_state(state_path)
    entry = saved["ledgers"].get("data/leadership_crack/forward_log.jsonl", {})
    assert entry.get("asof") is None


# ── Test 7: state persists for next run ──────────────────────────────────

def test_state_persists(tmp_path):
    """After a run, the saved state carries the current asof as the new prev_asof."""
    ledger = tmp_path / "data" / "market_state" / "forward_log.jsonl"
    _write_jsonl(ledger, [
        {"asof": "2026-07-14"},
        {"asof": "2026-07-15"},
        {"asof": "2026-07-16"},
    ])
    state_path = tmp_path / "data" / "ci" / "ledger_heartbeat_state.json"
    _write_state(state_path, {})  # no prior state

    manifest = [{"path": "data/market_state/forward_log.jsonl", "label": "market_state"}]
    with patch.object(M, "_LEDGER_MANIFEST", manifest):
        M.run_check(
            root=tmp_path,
            state_path=state_path,
            render_happened=True,
            _now=_D1,
        )

    saved = _load_state(state_path)
    assert saved["ledgers"]["data/market_state/forward_log.jsonl"]["asof"] == "2026-07-16"
    assert saved["ledgers"]["data/market_state/forward_log.jsonl"]["last_check_date"] == "2026-07-16"


# ── Test 8: multiple stalls in one run ───────────────────────────────────

def test_multiple_stalls(tmp_path):
    """All stalled ledgers in one run are reported; dispatch_stall_alert fires once."""
    l1 = tmp_path / "data" / "risk_radar" / "forward_log.jsonl"
    l2 = tmp_path / "data" / "market_state" / "forward_log.jsonl"
    _write_jsonl(l1, [{"asof": "2026-07-15"}])
    _write_jsonl(l2, [{"asof": "2026-07-14"}])

    state_path = tmp_path / "data" / "ci" / "ledger_heartbeat_state.json"
    _write_state(state_path, {
        "data/risk_radar/forward_log.jsonl": {
            "asof": "2026-07-15",
            "last_check_date": "2026-07-16",
            "stalled_since": None,
        },
        "data/market_state/forward_log.jsonl": {
            "asof": "2026-07-14",
            "last_check_date": "2026-07-16",
            "stalled_since": None,
        },
    })

    manifest = [
        {"path": "data/risk_radar/forward_log.jsonl", "label": "risk_radar"},
        {"path": "data/market_state/forward_log.jsonl", "label": "market_state"},
    ]
    dispatch = _Dispatch()
    with (
        patch.object(M, "_LEDGER_MANIFEST", manifest),
        patch("engine.alert_triage.push_ops_alert", dispatch),
    ):
        stalled = M.run_check(
            root=tmp_path,
            state_path=state_path,
            render_happened=True,
            _now=_D2,
        )
        # Dispatch is called once with the combined stall list (mimics main())
        M._dispatch_stall_alert(stalled, tmp_path)

    assert len(stalled) == 2
    labels = {s["label"] for s in stalled}
    assert labels == {"risk_radar", "market_state"}
    # One combined alert dispatched
    assert len(dispatch.calls) == 1
    assert dispatch.calls[0]["type_"] == "ledger_stall"


# ── Test 9: corrupt state file → fail-open ──────────────────────────────

def test_corrupt_state_fail_open(tmp_path):
    """Corrupt state JSON → fail-open, treated as empty state."""
    ledger = tmp_path / "data" / "risk_radar" / "forward_log.jsonl"
    _write_jsonl(ledger, [{"asof": "2026-07-16"}])
    state_path = tmp_path / "data" / "ci" / "ledger_heartbeat_state.json"
    state_path.parent.mkdir(parents=True, exist_ok=True)
    state_path.write_text("{INVALID JSON{{")

    manifest = [{"path": "data/risk_radar/forward_log.jsonl", "label": "risk_radar"}]
    with patch.object(M, "_LEDGER_MANIFEST", manifest):
        stalled = M.run_check(
            root=tmp_path,
            state_path=state_path,
            render_happened=True,
            _now=_D2,
        )
    # No previous state → no stall (prev_asof is None → no comparison possible)
    assert stalled == []


# ── Test 10: push_ops_alert failure → fail-open ──────────────────────────

def test_push_ops_alert_failure_fail_open(tmp_path):
    """push_ops_alert raising an exception → script still exits 0 (fail-open)."""
    ledger = tmp_path / "data" / "risk_radar" / "forward_log.jsonl"
    _write_jsonl(ledger, [{"asof": "2026-07-15"}])
    state_path = tmp_path / "data" / "ci" / "ledger_heartbeat_state.json"
    _write_state(state_path, {
        "data/risk_radar/forward_log.jsonl": {
            "asof": "2026-07-15",
            "last_check_date": "2026-07-16",
            "stalled_since": None,
        },
    })

    manifest = [{"path": "data/risk_radar/forward_log.jsonl", "label": "risk_radar"}]
    with (
        patch.object(M, "_LEDGER_MANIFEST", manifest),
        patch("engine.alert_triage.push_ops_alert", side_effect=RuntimeError("boom")),
    ):
        stalled = M.run_check(
            root=tmp_path,
            state_path=state_path,
            render_happened=True,
            _now=_D2,
        )
        # Should not raise
        M._dispatch_stall_alert(stalled, tmp_path)

    # Stall was detected even though alert dispatch failed
    assert len(stalled) == 1


# ── Test: stalled_since is preserved across consecutive stall days ────────

def test_stalled_since_preserved(tmp_path):
    """stalled_since is set on first stall and preserved on subsequent stall days."""
    ledger = tmp_path / "data" / "risk_radar" / "forward_log.jsonl"
    _write_jsonl(ledger, [{"asof": "2026-07-15"}])
    state_path = tmp_path / "data" / "ci" / "ledger_heartbeat_state.json"
    _write_state(state_path, {
        "data/risk_radar/forward_log.jsonl": {
            "asof": "2026-07-15",
            "last_check_date": "2026-07-16",
            "stalled_since": "2026-07-16",  # was already stalled yesterday
        },
    })

    manifest = [{"path": "data/risk_radar/forward_log.jsonl", "label": "risk_radar"}]
    dispatch = _Dispatch()
    with (
        patch.object(M, "_LEDGER_MANIFEST", manifest),
        patch("engine.alert_triage.push_ops_alert", dispatch),
    ):
        stalled = M.run_check(
            root=tmp_path,
            state_path=state_path,
            render_happened=True,
            _now=_D2,
        )

    assert len(stalled) == 1
    assert stalled[0]["stalled_since"] == "2026-07-16"  # preserved, not overwritten

    saved = _load_state(state_path)
    assert saved["ledgers"]["data/risk_radar/forward_log.jsonl"]["stalled_since"] == "2026-07-16"


# ── Test: main() CLI always returns 0 ────────────────────────────────────

def test_main_always_exits_zero(tmp_path):
    """main() always returns 0 regardless of outcome (fail-open, CSP-R1)."""
    rc = M.main(["--root", str(tmp_path)])
    assert rc == 0


def test_main_with_render_happened(tmp_path):
    """--render-happened flag + stall condition triggers alert via main()."""
    ledger = tmp_path / "data" / "risk_radar" / "forward_log.jsonl"
    _write_jsonl(ledger, [{"asof": "2026-07-15"}])
    state_path = tmp_path / "data" / "ci" / "ledger_heartbeat_state.json"
    _write_state(state_path, {
        "data/risk_radar/forward_log.jsonl": {
            "asof": "2026-07-15",
            "last_check_date": "2026-07-16",
            "stalled_since": None,
        },
    })

    manifest = [{"path": "data/risk_radar/forward_log.jsonl", "label": "risk_radar"}]
    dispatch = _Dispatch()
    with (
        patch.object(M, "_LEDGER_MANIFEST", manifest),
        patch("engine.alert_triage.push_ops_alert", dispatch),
        # Ensure the test date is treated as a trading day
        patch.object(M, "_is_trading_day", return_value=True),
    ):
        rc = M.main([
            "--root", str(tmp_path),
            "--state-file", str(state_path),
            "--render-happened",
        ])
    assert rc == 0
    # Alert should have fired for the stall
    assert len(dispatch.calls) == 1
    assert dispatch.calls[0]["type_"] == "ledger_stall"


# ── Test: _latest_asof supports 'date' field fallback ────────────────────

def test_latest_asof_date_field(tmp_path):
    """_latest_asof reads 'date' field when 'asof' is absent (mag7_regime schema)."""
    ledger = tmp_path / "ledger.jsonl"
    _write_jsonl(ledger, [
        {"date": "2026-07-15", "trend_state": "turning_up"},
        {"date": "2026-07-16", "trend_state": "running_narrow"},
    ])
    result = M._latest_asof(ledger)
    assert result == "2026-07-16"


def test_latest_asof_asof_field(tmp_path):
    """_latest_asof reads 'asof' field for risk_radar/market_state schema."""
    ledger = tmp_path / "forward_log.jsonl"
    _write_jsonl(ledger, [
        {"asof": "2026-07-14", "state": "caution"},
        {"asof": "2026-07-16", "state": "caution"},
        {"asof": "2026-07-15", "state": "caution"},  # out-of-order, but tail-scan handles it
    ])
    result = M._latest_asof(ledger)
    # Tail scan of last 20 rows; picks max within that window
    # All 3 rows are in the window; max is "2026-07-16"
    assert result == "2026-07-16"


def test_latest_asof_missing_file(tmp_path):
    """_latest_asof returns None when file does not exist."""
    result = M._latest_asof(tmp_path / "nonexistent.jsonl")
    assert result is None
