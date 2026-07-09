"""Tests for scripts/refresh_regime_if_stale.py — the regime freshness self-heal.

Pins the DECISION logic (the novel part): re-stamp only when the price store's last
close is NEWER than data/regime/latest.json's as-of; no-op when already fresh or equal;
degrade to a no-op when the store has no SPY close. The expensive engine.run() branch is
monkeypatched so the test stays fast and IO-free — we assert it is called exactly when the
regime is behind the store, and never otherwise.
"""
from __future__ import annotations

import scripts.refresh_regime_if_stale as rr


def _patch_dates(monkeypatch, store_date, regime_date, market_date=None):
    monkeypatch.setattr(rr, "_store_close_date", lambda: store_date)
    monkeypatch.setattr(rr, "_regime_asof", lambda: regime_date)
    # HERMETICITY: the real market reference reads the massive manifest from the REAL
    # data dir AND (since the 2026-07-07 incident fix) the NYSE calendar — with a stale
    # patched store_date that arms the mode-3 self-heal, and a REAL keyless yahoo
    # re-pull then mutates data/yahoo/*.parquet mid-test. Pin it (None = mode 3 off,
    # what these decision tests want) so no test touches the network or the real store.
    monkeypatch.setattr(rr, "_market_reference_date", lambda: market_date)
    monkeypatch.setattr(rr, "_repull_yahoo",
                        lambda: (_ for _ in ()).throw(AssertionError("unexpected re-pull")))
    # refresh() appends to the real reflex firings ledger on every "refreshed" status —
    # no-op it so tests don't pollute data/reflexes/ (single-writer: intraday fast-path).
    import engine.neuralweb.reflexes as _rf
    monkeypatch.setattr(_rf, "record_firing", lambda *a, **k: None)


def test_stale_triggers_refresh(monkeypatch):
    """store ahead of regime -> engine re-runs and the persist path fires."""
    calls = {"run": 0, "persist": 0}

    def _fake_run():
        calls["run"] += 1
        return {"date": "2026-07-01", "quad_name": "Goldilocks", "alerts": []}

    # engine.run is imported lazily inside refresh(); patch at its source module.
    import engine.run as _er
    monkeypatch.setattr(_er, "run", _fake_run)
    import engine.market_state as _ms
    monkeypatch.setattr(_ms, "market_state_snapshot", lambda *a, **k: {"verdict": "MIXED"})
    monkeypatch.setattr(_ms, "persist", lambda *a, **k: calls.__setitem__("persist", calls["persist"] + 1))
    import engine.inputs as _inp
    monkeypatch.setattr(_inp, "build_features", lambda *a, **k: object())

    # after the refresh the module re-reads latest.json; return the new date
    _patch_dates(monkeypatch, store_date="2026-07-01", regime_date="2026-06-30")
    # first _regime_asof() call (pre-check) sees the stale date; the post-refresh read sees fresh
    seq = iter(["2026-06-30", "2026-07-01"])
    monkeypatch.setattr(rr, "_regime_asof", lambda: next(seq))

    out = rr.refresh()
    assert out["status"] == "refreshed"
    assert out["prev"] == "2026-06-30" and out["asof"] == "2026-07-01"
    assert calls["run"] == 1 and calls["persist"] == 1


def test_fresh_is_noop(monkeypatch):
    """regime as-of == store -> no engine run."""
    import engine.run as _er
    monkeypatch.setattr(_er, "run", lambda: (_ for _ in ()).throw(AssertionError("must not run")))
    _patch_dates(monkeypatch, store_date="2026-07-01", regime_date="2026-07-01")
    out = rr.refresh()
    assert out["status"] == "fresh"


def test_regime_ahead_is_noop(monkeypatch):
    """regime as-of NEWER than store (e.g. futures-stamped) -> no engine run."""
    import engine.run as _er
    monkeypatch.setattr(_er, "run", lambda: (_ for _ in ()).throw(AssertionError("must not run")))
    _patch_dates(monkeypatch, store_date="2026-06-30", regime_date="2026-07-01")
    assert rr.refresh()["status"] == "fresh"


def test_force_runs_even_when_fresh(monkeypatch):
    """--force re-runs the engine regardless of the freshness comparison."""
    ran = {"n": 0}

    def _fake_run():
        ran["n"] += 1
        return {"date": "2026-07-01", "quad_name": "Goldilocks"}

    import engine.run as _er
    monkeypatch.setattr(_er, "run", _fake_run)
    import engine.market_state as _ms
    monkeypatch.setattr(_ms, "market_state_snapshot", lambda *a, **k: None)
    monkeypatch.setattr(_ms, "persist", lambda *a, **k: None)
    import engine.inputs as _inp
    monkeypatch.setattr(_inp, "build_features", lambda *a, **k: object())
    _patch_dates(monkeypatch, store_date="2026-07-01", regime_date="2026-07-01")
    out = rr.refresh(force=True)
    assert out["status"] == "refreshed" and ran["n"] == 1


def test_no_store_is_noop(monkeypatch):
    """empty store -> graceful no-op, never raises."""
    import engine.run as _er
    monkeypatch.setattr(_er, "run", lambda: (_ for _ in ()).throw(AssertionError("must not run")))
    _patch_dates(monkeypatch, store_date=None, regime_date="2026-06-30")
    assert rr.refresh()["status"] == "no_store"
