"""Tests for engine.run's regime no-regress guard (2026-07-13 earlyclose↔render flip-flop).

In the post-close window the committed data/regime/latest.json can be AHEAD of the
committed price store: the earlyclose lane and the intraday fast-path self-heal both
recompute from an ephemeral keyless store heal and commit only the snapshot pointers,
while the store itself advances at the nightly collect. A render lane recomputing there
(engine-render fires on every engine/** push) would re-stamp the PRIOR session over the
fresh one — run() must return the committed snapshot untouched instead. The expensive
build_features() branch is monkeypatched so the tests stay fast and IO-free — we assert
the recompute is entered exactly when it cannot regress, and never otherwise.
"""
from __future__ import annotations

import pytest

import engine.run as er

_SENTINEL = RuntimeError("recompute-entered")


def _patch(monkeypatch, persisted, store_date):
    monkeypatch.setattr(er, "_persisted_latest", lambda: persisted)
    monkeypatch.setattr(er, "_store_spy_date", lambda: store_date)
    # Prove the early exit: entering the recompute at all raises the sentinel.
    monkeypatch.setattr(er, "build_features",
                        lambda *a, **k: (_ for _ in ()).throw(_SENTINEL))
    monkeypatch.delenv("REGIME_FORCE_RECOMPUTE", raising=False)


def test_guard_blocks_regressing_recompute(monkeypatch):
    """latest.json ahead of the store -> committed snapshot returned, NO recompute."""
    latest = {"date": "2026-07-13", "quad_name": "Goldilocks", "alerts": []}
    _patch(monkeypatch, latest, "2026-07-10")
    assert er.run() is latest


def test_equal_session_recomputes(monkeypatch):
    """Same session on both sides -> routine same-day recompute proceeds (idempotent)."""
    _patch(monkeypatch, {"date": "2026-07-10"}, "2026-07-10")
    with pytest.raises(RuntimeError, match="recompute-entered"):
        er.run()


def test_store_ahead_recomputes(monkeypatch):
    """Store past the snapshot (the normal nightly advance) -> recompute proceeds."""
    _patch(monkeypatch, {"date": "2026-07-10"}, "2026-07-13")
    with pytest.raises(RuntimeError, match="recompute-entered"):
        er.run()


def test_force_kwarg_bypasses_guard(monkeypatch):
    _patch(monkeypatch, {"date": "2026-07-13"}, "2026-07-10")
    with pytest.raises(RuntimeError, match="recompute-entered"):
        er.run(force=True)


def test_force_env_bypasses_guard(monkeypatch):
    _patch(monkeypatch, {"date": "2026-07-13"}, "2026-07-10")
    monkeypatch.setenv("REGIME_FORCE_RECOMPUTE", "1")
    with pytest.raises(RuntimeError, match="recompute-entered"):
        er.run()


def test_missing_latest_recomputes(monkeypatch):
    """Degrade-never-block: no persisted snapshot -> guard off, recompute proceeds."""
    _patch(monkeypatch, None, "2026-07-10")
    with pytest.raises(RuntimeError, match="recompute-entered"):
        er.run()


def test_missing_store_recomputes(monkeypatch):
    """Degrade-never-block: unreadable/absent store -> guard off, recompute proceeds."""
    _patch(monkeypatch, {"date": "2026-07-13"}, None)
    with pytest.raises(RuntimeError, match="recompute-entered"):
        er.run()


def test_dateless_snapshot_recomputes(monkeypatch):
    """A snapshot with no usable date can't prove a regression -> recompute proceeds."""
    _patch(monkeypatch, {"quad_name": "Goldilocks"}, "2026-07-10")
    with pytest.raises(RuntimeError, match="recompute-entered"):
        er.run()
