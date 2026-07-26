"""Tests for app/tape.py — the Live Tape relay's cache/fallback logic and the
FastAPI /ws/tape websocket contract (Phase 1).

No network: TapeHub's upstream/poll loops are never started here. We drive the
pure fanout/cache methods directly and exercise the route with a pre-seeded
cache + a no-op start() so the TestClient never opens a real socket.
"""
from __future__ import annotations

import asyncio
import base64
import struct

import pytest

from app.tape import TapeHub, TAPE_SYMBOLS, register_tape


# --- reuse the decoder test's tiny encoder for an end-to-end upstream frame ---
def _varint(n: int) -> bytes:
    out = bytearray()
    while True:
        b = n & 0x7F
        n >>= 7
        if n:
            out.append(b | 0x80)
        else:
            out.append(b)
            return bytes(out)


def _tag(field: int, wire: int) -> bytes:
    return _varint((field << 3) | wire)


def _frame(sym: str, price: float, chg: float | None = None,
           prev: float | None = None, time_ms: int | None = None) -> bytes:
    parts = [_tag(1, 2) + _varint(len(sym.encode())) + sym.encode(),
             _tag(2, 5) + struct.pack("<f", price)]
    if time_ms is not None:
        zz = (time_ms << 1) ^ (time_ms >> 63)
        parts.append(_tag(3, 0) + _varint(zz & ((1 << 64) - 1)))
    if chg is not None:
        parts.append(_tag(8, 5) + struct.pack("<f", chg))
    if prev is not None:
        parts.append(_tag(16, 5) + struct.pack("<f", prev))
    return b"".join(parts)


# --------------------------------------------------------------------------- #
# Cache + fanout
# --------------------------------------------------------------------------- #

def test_symbols_are_the_six_tape_instruments():
    assert TAPE_SYMBOLS == ("ES=F", "NQ=F", "YM=F", "RTY=F", "^TNX", "DX-Y.NYB")


def test_publish_caches_and_snapshots():
    hub = TapeHub()
    hub._publish({"sym": "ES=F", "price": 5000.0, "chgPct": 0.5, "ts": 100, "basis": "quote"})
    snap = hub.snapshot()
    assert len(snap) == 1 and snap[0]["sym"] == "ES=F"


def test_publish_same_basis_out_of_order_dropped():
    """A ts older than the cached one of the SAME basis must NOT overwrite
    (protects against out-of-order upstream 'quote' frames)."""
    hub = TapeHub()
    hub._publish({"sym": "ES=F", "price": 5000.0, "chgPct": 0.5, "ts": 200, "basis": "quote"})
    hub._publish({"sym": "ES=F", "price": 4000.0, "chgPct": -9.9, "ts": 100, "basis": "quote"})
    cached = hub.snapshot()[0]
    assert cached["price"] == 5000.0 and cached["ts"] == 200  # older quote ignored


def test_publish_newer_wins():
    hub = TapeHub()
    hub._publish({"sym": "ES=F", "price": 5000.0, "chgPct": 0.5, "ts": 100, "basis": "quote"})
    hub._publish({"sym": "ES=F", "price": 5010.0, "chgPct": 0.7, "ts": 300, "basis": "quote"})
    assert hub.snapshot()[0]["price"] == 5010.0


def test_poll_refreshes_after_fresh_quote_despite_older_ts():
    """CRITICAL fallback-integrity case: after a FRESH ws quote (ts=200), the
    upstream dies and a poll fires whose data ts is OLDER (ts=100, a 15-min-old
    quote_ts). The poll MUST still refresh the cache — otherwise a dead upstream
    freezes the tile on an ever-staler quote and the fallback is silently
    defeated. Cross-basis refresh (quote -> poll) always wins."""
    hub = TapeHub()
    hub._publish({"sym": "ES=F", "price": 5000.0, "chgPct": 0.5, "ts": 200, "basis": "quote"})
    hub._publish({"sym": "ES=F", "price": 4980.0, "chgPct": 0.1, "ts": 100, "basis": "poll"})
    cached = hub.snapshot()[0]
    assert cached["price"] == 4980.0 and cached["basis"] == "poll"  # poll refreshed


def test_quote_recovery_after_poll_refreshes():
    """And the reverse: upstream recovers, a 'quote' tick refreshes a cache last
    written by a 'poll' even if the fresh tick's ts is (implausibly) not strictly
    greater — a basis change always refreshes."""
    hub = TapeHub()
    hub._publish({"sym": "ES=F", "price": 4980.0, "chgPct": 0.1, "ts": 100, "basis": "poll"})
    hub._publish({"sym": "ES=F", "price": 5001.0, "chgPct": 0.6, "ts": 90, "basis": "quote"})
    assert hub.snapshot()[0]["basis"] == "quote" and hub.snapshot()[0]["price"] == 5001.0


def test_register_seeds_full_snapshot():
    hub = TapeHub()
    hub._publish({"sym": "ES=F", "price": 5000.0, "chgPct": 0.5, "ts": 100, "basis": "quote"})
    hub._publish({"sym": "NQ=F", "price": 19000.0, "chgPct": -0.2, "ts": 100, "basis": "quote"})
    q = hub.register()
    got = []
    while not q.empty():
        got.append(q.get_nowait())
    assert {p["sym"] for p in got} == {"ES=F", "NQ=F"}


def test_unregister_removes_client():
    hub = TapeHub()
    q = hub.register()
    assert q in hub._clients
    hub.unregister(q)
    assert q not in hub._clients


def test_try_admit_caps_connections_per_ip():
    """Per-IP cap: the first _MAX_CONNS_PER_IP admits succeed, the next is refused;
    releasing frees a slot, and a different IP has its own independent budget."""
    from app.tape import _MAX_CONNS_PER_IP

    hub = TapeHub()
    ip = "203.0.113.7"
    assert all(hub.try_admit(ip) for _ in range(_MAX_CONNS_PER_IP))
    assert hub.try_admit(ip) is False              # one past the cap -> refused
    hub.release(ip)                                # free a single slot
    assert hub.try_admit(ip) is True               # now admits again
    assert hub.try_admit("198.51.100.9") is True   # a different IP is independent


def test_release_prunes_bucket_at_zero():
    """release() removes the per-IP bucket when it returns to zero, and
    over-releasing is harmless (never negative, never raises)."""
    hub = TapeHub()
    ip = "203.0.113.8"
    assert hub.try_admit(ip) is True
    hub.release(ip)
    assert ip not in hub._ip_counts
    hub.release(ip)                                # over-release is a no-op
    assert ip not in hub._ip_counts


def test_wedged_client_dropped_on_queue_full():
    """A client whose queue is full (slow/wedged) is dropped rather than blocking
    the hub — one bad browser can't stall the fanout."""
    hub = TapeHub()
    q = hub.register()
    # fill the queue to capacity
    while True:
        try:
            q.put_nowait({"x": 1})
        except asyncio.QueueFull:
            break
    hub._publish({"sym": "ES=F", "price": 5000.0, "chgPct": 0.5, "ts": 100, "basis": "quote"})
    assert q not in hub._clients  # dropped


# --------------------------------------------------------------------------- #
# Upstream message -> payload shaping (uses the real decoder)
# --------------------------------------------------------------------------- #

def test_upstream_message_shapes_quote_payload():
    from app.tape_decode import decode_pricing
    hub = TapeHub()
    hub._on_upstream_message(base64.b64encode(_frame("ES=F", 5432.25, chg=0.85, time_ms=1_753_380_000_000)),
                             decode_pricing)
    p = hub.snapshot()[0]
    assert p["sym"] == "ES=F"
    assert abs(p["price"] - 5432.25) < 1e-2
    assert abs(p["chgPct"] - 0.85) < 1e-3
    assert p["basis"] == "quote"
    assert p["ts"] == 1_753_380_000_000


def test_upstream_message_derives_chg_from_prevclose():
    """When the frame omits changePercent but carries previousClose, the relay
    derives the % move — the tile still shows a delta."""
    from app.tape_decode import decode_pricing
    hub = TapeHub()
    hub._on_upstream_message(_frame("YM=F", 40400.0, prev=40000.0), decode_pricing)
    p = hub.snapshot()[0]
    assert abs(p["chgPct"] - 1.0) < 1e-3  # +400 / 40000 = +1.0%


def test_upstream_junk_frame_ignored():
    from app.tape_decode import decode_pricing
    hub = TapeHub()
    hub._on_upstream_message(b"\xff\xff\xff", decode_pricing)
    assert hub.snapshot() == []


def test_unsubscribed_symbol_ignored():
    from app.tape_decode import decode_pricing
    hub = TapeHub()
    hub._on_upstream_message(_frame("AAPL", 200.0), decode_pricing)  # not a tape sym
    assert hub.snapshot() == []


# --------------------------------------------------------------------------- #
# REST poll fallback
# --------------------------------------------------------------------------- #

def test_poll_once_broadcasts_poll_basis(monkeypatch):
    hub = TapeHub()

    def fake_fetch():
        return {
            "ES=F": {"price": 5100.0, "prev_close": 5049.5, "quote_ts": "2026-07-24T18:00:00+00:00"},
            "^TNX": {"price": 42.5, "prev_close": 42.25, "quote_ts": None},
        }
    monkeypatch.setattr(hub, "_fetch_rest_quotes", fake_fetch)
    asyncio.run(hub._poll_once())
    by_sym = {p["sym"]: p for p in hub.snapshot()}
    assert by_sym["ES=F"]["basis"] == "poll"
    assert abs(by_sym["ES=F"]["chgPct"] - 1.0) < 1e-2  # +50.5/5049.5 ≈ +1.0%
    assert by_sym["^TNX"]["price"] == 42.5  # raw, no tnx transform server-side
    assert by_sym["^TNX"]["ts"] > 0         # None quote_ts -> receive time


def test_poll_empty_is_noop(monkeypatch):
    hub = TapeHub()
    monkeypatch.setattr(hub, "_fetch_rest_quotes", lambda: {})
    asyncio.run(hub._poll_once())
    assert hub.snapshot() == []


# --------------------------------------------------------------------------- #
# FastAPI /ws/tape route contract (TestClient, no real upstream)
# --------------------------------------------------------------------------- #

def test_ws_route_sends_snapshot_on_connect(monkeypatch):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    app = FastAPI()
    register_tape(app)
    # Pre-seed the hub cache; neutralise start() so no real socket opens.
    hub = TapeHub()
    hub._publish({"sym": "ES=F", "price": 5000.0, "chgPct": 0.5, "ts": 100, "basis": "quote"})
    hub._publish({"sym": "NQ=F", "price": 19000.0, "chgPct": -0.2, "ts": 100, "basis": "quote"})
    monkeypatch.setattr(hub, "start", lambda: None)
    app.state.tape_hub = hub

    with TestClient(app) as client:
        with client.websocket_connect("/ws/tape") as ws:
            got = {}
            for _ in range(2):
                msg = ws.receive_json()
                got[msg["sym"]] = msg
            assert set(got) == {"ES=F", "NQ=F"}
            assert got["ES=F"]["basis"] == "quote"


def test_ws_route_pushes_live_update(monkeypatch):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    app = FastAPI()
    register_tape(app)
    hub = TapeHub()
    monkeypatch.setattr(hub, "start", lambda: None)
    app.state.tape_hub = hub

    with TestClient(app) as client:
        with client.websocket_connect("/ws/tape") as ws:
            # publish AFTER connect -> the client should receive the update
            hub._publish({"sym": "ES=F", "price": 5432.0, "chgPct": 0.9, "ts": 500, "basis": "quote"})
            msg = ws.receive_json()
            assert msg["sym"] == "ES=F" and msg["price"] == 5432.0
