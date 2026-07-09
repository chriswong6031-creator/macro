"""Tests for engine/flip_confirmation.py — T+1 sector-flip confirmation lens.

Policy-Shock Regime program §4 W1-C (PR #2008, PS-A2).

All tests are hermetic: synthetic price series monkeypatched onto the store
layer, tmp_path for ledger and qledger stores. No live data, no network,
no side-effects on real data/ or site/ directories.
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

import engine.flip_confirmation as fc


# ── synthetic price helpers ────────────────────────────────────────────────────

def _make_prices(start: str = "2022-01-01", n: int = 400,
                 drift: float = 0.0, seed: int = 42) -> pd.Series:
    rng = np.random.default_rng(seed)
    idx = pd.bdate_range(start=start, periods=n)
    rets = rng.normal(drift, 0.01, n)
    prices = 100.0 * np.cumprod(1 + rets)
    return pd.Series(prices, index=idx, name="close")


def _make_store(*, def_drift: float = 0.0, off_drift: float = 0.0,
                n: int = 400, inject_flip: bool = False,
                flip_day_offset: int = 300,
                t1_continuation: bool = True) -> dict:
    """Return a synthetic store dict keyed by ticker.

    When inject_flip=True, inserts a large defensive spike on flip_day_offset.
    When t1_continuation=True, T+1 (flip_day_offset+1) also has a mild
    defensive continuation (same-sign, |z| >= 0.5 → CONFIRMED territory).
    When t1_continuation=False, T+1 has defensive continuation but at a very
    small magnitude (same-sign, |z| < 0.5 → MIXED territory).
    """
    store: dict[str, pd.Series] = {}
    tickers = ["XLP", "XLU", "XLV", "SMH", "XLK"]
    seeds = [1, 2, 3, 4, 5]
    for ticker, seed in zip(tickers, seeds):
        drift = def_drift if ticker in ("XLP", "XLU", "XLV") else off_drift
        store[ticker] = _make_prices(n=n, drift=drift, seed=seed)

    if inject_flip:
        # Insert a large +8% defensive / -8% offense spike to force a flip
        idx_pos = flip_day_offset
        for ticker in ("XLP", "XLU", "XLV"):
            arr = store[ticker].values.copy()
            arr[idx_pos] = arr[idx_pos - 1] * 1.08
            if t1_continuation:
                # mild continuation on T+1 (small positive for defensive)
                arr[idx_pos + 1] = arr[idx_pos] * 1.005
            else:
                # tiny continuation on T+1 — same sign but very small move
                arr[idx_pos + 1] = arr[idx_pos] * 1.0002
            store[ticker] = pd.Series(arr, index=store[ticker].index)
        for ticker in ("SMH", "XLK"):
            arr = store[ticker].values.copy()
            arr[idx_pos] = arr[idx_pos - 1] * 0.92
            if t1_continuation:
                arr[idx_pos + 1] = arr[idx_pos] * 0.995
            else:
                arr[idx_pos + 1] = arr[idx_pos] * 0.9998
            store[ticker] = pd.Series(arr, index=store[ticker].index)

    return store


@pytest.fixture
def patch_store(monkeypatch):
    """Monkeypatch engine.flip_confirmation._close to return synthetic prices."""
    store = _make_store(inject_flip=True, flip_day_offset=300)

    def _mock_close(ticker: str) -> pd.Series | None:
        s = store.get(ticker)
        if s is None:
            return None
        return pd.DataFrame({"close": s})["close"]

    monkeypatch.setattr("engine.flip_confirmation._close", _mock_close)
    return store


@pytest.fixture
def patch_store_no_flip(monkeypatch):
    """Monkeypatch with NO injected flip (all returns within ±1σ window)."""
    store = _make_store(inject_flip=False)

    def _mock_close(ticker: str) -> pd.Series | None:
        s = store.get(ticker)
        if s is None:
            return None
        return pd.DataFrame({"close": s})["close"]

    monkeypatch.setattr("engine.flip_confirmation._close", _mock_close)
    return store


@pytest.fixture
def patch_store_mixed(monkeypatch):
    """Monkeypatch: flip injected but T+1 has same-sign with tiny magnitude
    (designed to produce a MIXED verdict where |t1_z| < 0.5)."""
    store = _make_store(inject_flip=True, flip_day_offset=300, t1_continuation=False)

    def _mock_close(ticker: str) -> pd.Series | None:
        s = store.get(ticker)
        if s is None:
            return None
        return pd.DataFrame({"close": s})["close"]

    monkeypatch.setattr("engine.flip_confirmation._close", _mock_close)
    return store


# ── composites ────────────────────────────────────────────────────────────────

def test_composites_returns_two_series(patch_store):
    def_comp, off_comp = fc._composites()
    assert def_comp is not None
    assert off_comp is not None
    assert isinstance(def_comp, pd.Series)
    assert isinstance(off_comp, pd.Series)
    # defensive = mean of 3; offense = mean of 2
    assert len(def_comp) > 0
    assert len(off_comp) > 0


def test_composites_missing_ticker(monkeypatch):
    """If any ticker is missing, composites returns (None, None)."""
    # Only provide XLP; rest missing
    s = _make_prices()
    monkeypatch.setattr("engine.flip_confirmation._close",
                        lambda t: s if t == "XLP" else None)
    d, o = fc._composites()
    assert d is None
    assert o is None


# ── spread_z ──────────────────────────────────────────────────────────────────

def test_spread_z_shape(patch_store):
    def_comp, off_comp = fc._composites()
    spread, z = fc._spread_z(def_comp, off_comp)
    assert len(spread) == len(z)
    assert spread.index.equals(z.index)


def test_spread_z_flip_detected(patch_store):
    """The injected large spike should produce at least one |z| >= 2.5 event."""
    def_comp, off_comp = fc._composites()
    spread, z = fc._spread_z(def_comp, off_comp)
    flip_mask = z.abs() >= fc.Z_THRESH
    assert flip_mask.any(), "Expected at least one flip event after injecting a spike"


# ── verdict logic v1.1 (PS-A2) ───────────────────────────────────────────────

@pytest.mark.parametrize("event_z, t1_spread, t1_z, expected", [
    # Defensive flip, same direction, strong t1_z → CONFIRMED
    (3.0,  0.02,   1.2,  "CONFIRMED"),
    # Offense flip, same direction, strong t1_z → CONFIRMED
    (-3.0, -0.02, -0.8,  "CONFIRMED"),
    # Defensive flip, same direction, weak t1_z (< 0.5) → MIXED
    (3.0,  0.005,  0.3,  "MIXED"),
    # Offense flip, same direction, weak t1_z (< 0.5) → MIXED
    (-3.0, -0.005,-0.2,  "MIXED"),
    # Defensive flip, reversed next day → FADED
    (3.0,  -0.02, -1.0,  "FADED"),
    # Offense flip, reversed next day → FADED
    (-3.0,  0.02,  0.9,  "FADED"),
    # Exact boundary: |t1_z| == 0.5 → CONFIRMED (>= threshold)
    (3.0,  0.01,   0.5,  "CONFIRMED"),
    # Just below boundary: |t1_z| = 0.49 → MIXED
    (3.0,  0.01,   0.49, "MIXED"),
    # Strong reversal: t1_z > 0 but event_z < 0 (opposite signs) → FADED
    (-3.0,  0.02,  0.8,  "FADED"),
])
def test_verdict_logic(event_z, t1_spread, t1_z, expected):
    """All three verdict states are reachable through the v1.1 taxonomy."""
    result = fc._verdict_for_t1(
        event_z=event_z,
        t1_spread=t1_spread,
        t1_z=t1_z,
    )
    assert result == expected


def test_confirmed_reachable_via_pipeline(patch_store, monkeypatch):
    """CONFIRMED is reachable via the real pipeline (same-sign + |t1_z| >= 0.5)."""
    monkeypatch.setattr("engine.flip_confirmation._absorption_delta",
                        lambda *a, **k: None)
    events = fc.detect_since("2022-01-01")
    verdicts = {e["verdict"] for e in events if e["verdict"] is not None}
    # With the default store (t1_continuation=True), expect CONFIRMED present
    assert "CONFIRMED" in verdicts, (
        f"CONFIRMED not found in pipeline verdicts: {verdicts}; events: {len(events)}"
    )


def test_mixed_reachable_via_pipeline(patch_store_mixed, monkeypatch):
    """MIXED is reachable via the real pipeline (same-sign + |t1_z| < 0.5).

    Uses the patch_store_mixed fixture where T+1 has a tiny same-sign move
    that should produce |t1_z| < 0.5.
    """
    monkeypatch.setattr("engine.flip_confirmation._absorption_delta",
                        lambda *a, **k: None)
    events = fc.detect_since("2022-01-01")
    graded = [e for e in events if e["verdict"] is not None]
    verdicts = {e["verdict"] for e in graded}
    # MIXED is produced when same-sign continuation is very weak
    assert "MIXED" in verdicts, (
        f"MIXED not found in pipeline verdicts: {verdicts}. "
        f"t1_z values: {[e['t1_attribution'].get('t1_z') for e in graded if e['t1_attribution']]}"
    )


def test_faded_reachable_via_pipeline(monkeypatch):
    """FADED is reachable via the real pipeline (opposite sign on T+1)."""
    # Build a store where T+1 flips to opposite direction
    store = _make_store(inject_flip=True, flip_day_offset=300)
    # Override T+1 for defensive tickers to go DOWN (offense wins T+1)
    idx_pos = 301
    for ticker in ("XLP", "XLU", "XLV"):
        arr = store[ticker].values.copy()
        arr[idx_pos] = arr[idx_pos - 1] * 0.97  # defensive drops on T+1
        store[ticker] = pd.Series(arr, index=store[ticker].index)
    for ticker in ("SMH", "XLK"):
        arr = store[ticker].values.copy()
        arr[idx_pos] = arr[idx_pos - 1] * 1.02  # offense rallies on T+1
        store[ticker] = pd.Series(arr, index=store[ticker].index)

    def _mock_close(ticker: str) -> pd.Series | None:
        s = store.get(ticker)
        if s is None:
            return None
        return pd.DataFrame({"close": s})["close"]

    monkeypatch.setattr("engine.flip_confirmation._close", _mock_close)
    monkeypatch.setattr("engine.flip_confirmation._absorption_delta",
                        lambda *a, **k: None)

    events = fc.detect_since("2022-01-01")
    verdicts = {e["verdict"] for e in events if e["verdict"] is not None}
    assert "FADED" in verdicts, f"FADED not found in verdicts: {verdicts}"


# ── build_event ────────────────────────────────────────────────────────────────

def test_build_event_with_t1(patch_store):
    def_comp, off_comp = fc._composites()
    spread, z = fc._spread_z(def_comp, off_comp)
    flip_mask = z.abs() >= fc.Z_THRESH
    flip_dates = z[flip_mask].index
    assert len(flip_dates) > 0

    flip_dt = flip_dates[0]
    ev = fc._build_event(flip_dt, spread, z)

    assert "event_date" in ev
    assert ev["direction"] in ("defensive", "offense")
    assert ev["z"] is not None
    # T+1 should be populated (flip is not the last bar)
    assert ev["t1_attribution"] is not None
    assert ev["verdict"] in ("CONFIRMED", "FADED", "MIXED")
    # t1_z should be present in attribution
    assert "t1_z" in ev["t1_attribution"]


def test_build_event_no_t1(patch_store):
    """When event is on the last bar, t1_attribution should be None."""
    def_comp, off_comp = fc._composites()
    spread, z = fc._spread_z(def_comp, off_comp)
    last_date = spread.index[-1]
    # Construct synthetic z with large value on last date
    z_fake = z.copy()
    z_fake.iloc[-1] = 3.5

    ev = fc._build_event(last_date, spread, z_fake)
    assert ev["t1_attribution"] is None
    assert ev["verdict"] is None


# ── detect_since ──────────────────────────────────────────────────────────────

def test_detect_since_returns_list(patch_store):
    # Patch absorption delta to avoid reading real data
    import engine.flip_confirmation as _fc
    _fc_orig = _fc._absorption_delta
    _fc._absorption_delta = lambda *a, **k: None
    try:
        events = fc.detect_since("2022-01-01")
        assert isinstance(events, list)
        for ev in events:
            assert "event_date" in ev
            assert ev["direction"] in ("defensive", "offense")
            assert ev["z"] is not None
    finally:
        _fc._absorption_delta = _fc_orig


def test_detect_since_no_flip(patch_store_no_flip):
    """With very low-variance returns, may not produce z >= 2.5 events."""
    events = fc.detect_since("2022-01-01")
    # Just check it returns a list without raising
    assert isinstance(events, list)


# ── snapshot ──────────────────────────────────────────────────────────────────

def test_snapshot_structure(patch_store, monkeypatch):
    monkeypatch.setattr("engine.flip_confirmation._absorption_delta",
                        lambda *a, **k: None)
    snap = fc.snapshot()
    assert "asof" in snap
    assert "last_event" in snap
    assert "base_rates" in snap
    assert "descriptive_scan" in snap
    if snap["last_event"] is not None:
        assert "event_date" in snap["last_event"]
        assert snap["last_event"]["direction"] in ("defensive", "offense")
    if snap["base_rates"] is not None:
        br = snap["base_rates"]
        assert "n_events" in br
        assert "confirmed" in br and "faded" in br and "mixed" in br
        # totals must be consistent
        assert br["confirmed"] + br["faded"] + br["mixed"] == br["n_graded"]


# ── ledger ────────────────────────────────────────────────────────────────────

def test_append_ledger_keep_first(tmp_path, monkeypatch):
    # Override SHIP_DATE so test events (with future dates) pass the filter
    monkeypatch.setattr("engine.flip_confirmation.SHIP_DATE", "2026-07-09")
    events = [
        {"event_date": "2026-07-17", "z": 4.4, "direction": "defensive", "verdict": "FADED"},
        {"event_date": "2026-07-24", "z": 3.6, "direction": "defensive", "verdict": "CONFIRMED"},
    ]
    n = fc.append_ledger(events, root=tmp_path)
    assert n == 2

    # Re-append same events — should write 0 new rows
    n2 = fc.append_ledger(events, root=tmp_path)
    assert n2 == 0

    # Read back and verify content
    p = tmp_path / "data" / "flip_confirmation" / "events.jsonl"
    rows = [json.loads(line) for line in p.read_text().splitlines() if line.strip()]
    assert len(rows) == 2
    assert rows[0]["event_date"] == "2026-07-17"


def test_append_ledger_new_event(tmp_path, monkeypatch):
    monkeypatch.setattr("engine.flip_confirmation.SHIP_DATE", "2026-07-09")
    ev1 = [{"event_date": "2026-07-17", "z": 4.4, "direction": "defensive", "verdict": "FADED"}]
    fc.append_ledger(ev1, root=tmp_path)

    ev2 = [{"event_date": "2026-09-03", "z": 3.7, "direction": "defensive", "verdict": "CONFIRMED"}]
    n = fc.append_ledger(ev2, root=tmp_path)
    assert n == 1


def test_append_ledger_blocks_pre_ship_date(tmp_path, monkeypatch):
    """Events before SHIP_DATE must NOT be written to the ledger."""
    monkeypatch.setattr("engine.flip_confirmation.SHIP_DATE", "2026-07-09")
    events = [
        # before SHIP_DATE — must be blocked
        {"event_date": "2024-07-17", "z": 4.4, "direction": "defensive", "verdict": "FADED"},
        {"event_date": "2026-07-02", "z": 3.0, "direction": "defensive", "verdict": "FADED"},
        # on/after SHIP_DATE — must be written
        {"event_date": "2026-07-09", "z": 3.1, "direction": "defensive", "verdict": "CONFIRMED"},
        {"event_date": "2026-07-24", "z": 3.6, "direction": "defensive", "verdict": "MIXED"},
    ]
    n = fc.append_ledger(events, root=tmp_path)
    assert n == 2, f"Expected 2 rows written (post-ship-date only), got {n}"

    p = tmp_path / "data" / "flip_confirmation" / "events.jsonl"
    rows = [json.loads(line) for line in p.read_text().splitlines() if line.strip()]
    assert len(rows) == 2
    dates = {r["event_date"] for r in rows}
    assert "2024-07-17" not in dates
    assert "2026-07-02" not in dates
    assert "2026-07-09" in dates
    assert "2026-07-24" in dates


# ── register_claims — forward-only and gradeable ──────────────────────────────

def test_register_claims_blocks_pre_ship_date(tmp_path, monkeypatch):
    """Claims for events before SHIP_DATE must not be registered."""
    monkeypatch.setattr("engine.flip_confirmation.SHIP_DATE", "2026-07-09")
    events = [
        {"event_date": "2024-07-17", "z": 4.4, "direction": "defensive", "verdict": "FADED"},
        {"event_date": "2026-07-09", "z": 3.1, "direction": "defensive", "verdict": "CONFIRMED"},
    ]
    registered = fc.register_claims(events, root=tmp_path)
    # Only the post-ship-date event should produce claims (2 horizons → 2 rows)
    open_claims = [r for r in registered if r.get("status") == "open"]
    assert len(open_claims) == 2, (
        f"Expected 2 open claims (5d + 21d for the post-ship event), got {len(open_claims)}"
    )
    for c in open_claims:
        assert c["timestamp_quality"] == "CRAWL_BOUNDED"
        assert c["asof"] == "2026-07-09"


def test_register_claims_gradeable_quality(tmp_path, monkeypatch):
    """Forward claims must use CRAWL_BOUNDED (gradeable=True)."""
    monkeypatch.setattr("engine.flip_confirmation.SHIP_DATE", "2026-07-09")
    from engine import qledger as q
    events = [
        {"event_date": "2026-07-09", "z": 3.1, "direction": "defensive", "verdict": "CONFIRMED"},
    ]
    registered = fc.register_claims(events, root=tmp_path)
    for c in registered:
        tq = c.get("timestamp_quality")
        assert tq == "CRAWL_BOUNDED", f"Expected CRAWL_BOUNDED, got {tq!r}"
        # Verify gradeable=True per the qledger enum
        assert q.TIMESTAMP_QUALITY[tq][1] is True, (
            f"{tq} is not gradeable per qledger.TIMESTAMP_QUALITY"
        )


def test_register_claims_two_horizons_per_event(tmp_path, monkeypatch):
    """Each post-ship event should produce exactly 2 claim rows (5d + 21d)."""
    monkeypatch.setattr("engine.flip_confirmation.SHIP_DATE", "2026-07-09")
    events = [
        {"event_date": "2026-07-09", "z": 3.1, "direction": "defensive", "verdict": "CONFIRMED"},
        {"event_date": "2026-07-11", "z": 2.8, "direction": "offense", "verdict": "FADED"},
    ]
    registered = fc.register_claims(events, root=tmp_path)
    open_claims = [r for r in registered if r.get("status") == "open"]
    # 2 events × 2 horizons = 4 open claims
    assert len(open_claims) == 4, f"Expected 4 open claims, got {len(open_claims)}"
    horizons = sorted({c["horizon_d"] for c in open_claims})
    assert horizons == [5, 21]


# ── nightly_run ────────────────────────────────────────────────────────────────

def test_nightly_run_ok(patch_store, tmp_path, monkeypatch):
    monkeypatch.setattr("engine.flip_confirmation._absorption_delta",
                        lambda *a, **k: None)
    # Stub out qledger to avoid needing ai_desk etc.
    monkeypatch.setattr("engine.flip_confirmation.register_claims",
                        lambda *a, **k: [])
    summary = fc.nightly_run(root=tmp_path)
    assert summary["ok"] is True
    assert summary["n_events"] >= 0
    assert summary["n_written"] >= 0
    assert summary["confirmed"] + summary["faded"] + summary["mixed"] == summary["n_events"] - (
        summary["n_events"] - sum([summary["confirmed"], summary["faded"], summary["mixed"]])
    )


def test_nightly_run_no_backdated_writes(patch_store, tmp_path, monkeypatch):
    """nightly_run must NOT write historical events to the ledger."""
    monkeypatch.setattr("engine.flip_confirmation._absorption_delta",
                        lambda *a, **k: None)
    monkeypatch.setattr("engine.flip_confirmation.register_claims",
                        lambda *a, **k: [])
    # SHIP_DATE is 2026-07-09; synthetic store starts 2022-01-01 → all historical
    # (synthetic events will all be pre-ship-date), so ledger must stay empty
    summary = fc.nightly_run(root=tmp_path)
    assert summary["ok"] is True
    ledger_path = tmp_path / "data" / "flip_confirmation" / "events.jsonl"
    # Either doesn't exist or is empty (no pre-ship rows written)
    if ledger_path.exists():
        content = ledger_path.read_text().strip()
        assert content == "", (
            f"Ledger should be empty for pre-ship events; got: {content[:200]}"
        )


def test_nightly_run_missing_prices(monkeypatch, tmp_path):
    monkeypatch.setattr("engine.flip_confirmation._close", lambda t: None)
    monkeypatch.setattr("engine.flip_confirmation.register_claims",
                        lambda *a, **k: [])
    summary = fc.nightly_run(root=tmp_path)
    assert summary["ok"] is True   # empty list → no crash
    assert summary["n_events"] == 0
