"""Unit tests for app/tape_decode.decode_pricing — the vendored, pure Yahoo
streamer PricingData decoder (Live Tape Phase 1).

The decoder is the ONLY place a fabricated number could enter the live tape, so
it is covered against synthetic frames whose bytes we build here from the
canonical proto3 wire format, plus junk / partial / heartbeat frames.

The tiny protobuf ENCODER below is a TEST FIXTURE, not shipped code: it lets us
assert "these exact field values → this exact decode" without a protobuf
runtime. It mirrors the wire rules the decoder must invert:
  wire 0 varint, wire 2 length-delimited (string), wire 5 fixed32 (float LE),
  and sint64 zigzag for field 3 (time).
"""
from __future__ import annotations

import base64
import struct

from app.tape_decode import decode_pricing


# --------------------------------------------------------------------------- #
# Minimal proto3 encoder (test fixture)
# --------------------------------------------------------------------------- #

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


def _zigzag(n: int) -> int:
    return (n << 1) ^ (n >> 63)


def _tag(field: int, wire: int) -> bytes:
    return _varint((field << 3) | wire)


def _string_field(field: int, s: str) -> bytes:
    data = s.encode("utf-8")
    return _tag(field, 2) + _varint(len(data)) + data


def _float_field(field: int, v: float) -> bytes:
    return _tag(field, 5) + struct.pack("<f", v)


def _sint64_field(field: int, v: int) -> bytes:
    return _tag(field, 0) + _varint(_zigzag(v) & ((1 << 64) - 1))


def _enum_field(field: int, v: int) -> bytes:
    return _tag(field, 0) + _varint(v)


def _double_field(field: int, v: float) -> bytes:
    return _tag(field, 1) + struct.pack("<d", v)


def _pricing_frame(**kw) -> bytes:
    """Build a PricingData protobuf blob from keyword field values.

    Supported: id, price, time_ms, change_pct, prev_close, market_hours,
    day_volume (varint noise), currency (string noise), marketcap (double noise).
    Fields are emitted in ascending field-number order to look like a real frame.
    """
    parts: list[bytes] = []
    if "id" in kw:
        parts.append(_string_field(1, kw["id"]))
    if "price" in kw:
        parts.append(_float_field(2, kw["price"]))
    if "time_ms" in kw:
        parts.append(_sint64_field(3, kw["time_ms"]))
    if "currency" in kw:  # noise: a string field the decoder must skip
        parts.append(_string_field(4, kw["currency"]))
    if "market_hours" in kw:
        parts.append(_enum_field(7, kw["market_hours"]))
    if "change_pct" in kw:
        parts.append(_float_field(8, kw["change_pct"]))
    if "day_volume" in kw:  # noise: a sint64 field the decoder must skip
        parts.append(_sint64_field(9, kw["day_volume"]))
    if "prev_close" in kw:
        parts.append(_float_field(16, kw["prev_close"]))
    if "marketcap" in kw:  # noise: a double (fixed64) field the decoder must skip
        parts.append(_double_field(33, kw["marketcap"]))
    return b"".join(parts)


def _b64(blob: bytes) -> str:
    return base64.b64encode(blob).decode("ascii")


# --------------------------------------------------------------------------- #
# Happy-path decodes
# --------------------------------------------------------------------------- #

def test_full_futures_frame_bytes():
    blob = _pricing_frame(id="ES=F", price=5432.25, time_ms=1_753_380_000_000,
                          change_pct=0.85, prev_close=5386.5, market_hours=1)
    q = decode_pricing(blob)
    assert q is not None
    assert q["id"] == "ES=F"
    assert abs(q["price"] - 5432.25) < 1e-2
    assert q["ts_ms"] == 1_753_380_000_000
    assert abs(q["chgPct"] - 0.85) < 1e-4
    assert abs(q["prevClose"] - 5386.5) < 1e-2
    assert q["marketHours"] == "regular"


def test_full_frame_from_base64_string():
    """The socket delivers base64 TEXT — decode_pricing must accept it directly."""
    blob = _pricing_frame(id="NQ=F", price=19875.5, time_ms=1_753_380_123_456,
                          change_pct=-0.42, prev_close=19959.0, market_hours=2)
    q = decode_pricing(_b64(blob))
    assert q is not None
    assert q["id"] == "NQ=F"
    assert abs(q["price"] - 19875.5) < 1e-1
    assert q["marketHours"] == "post"
    assert q["chgPct"] < 0


def test_tnx_yield_frame_raw_value_preserved():
    """^TNX streams yield×10 (42.5 => 4.25%). The decoder must NOT transform —
    that is the client's job (data-fmt=tnx). It reports the raw 42.5."""
    blob = _pricing_frame(id="^TNX", price=42.5, time_ms=1_753_380_000_000,
                          change_pct=0.6, prev_close=42.25, market_hours=1)
    q = decode_pricing(blob)
    assert q is not None
    assert abs(q["price"] - 42.5) < 1e-3  # raw, NOT 4.25
    assert abs(q["prevClose"] - 42.25) < 1e-3


def test_negative_and_zero_change_pct():
    for cp in (-3.14, 0.0, 12.5):
        blob = _pricing_frame(id="YM=F", price=40000.0, change_pct=cp)
        q = decode_pricing(blob)
        assert q is not None and abs(q["chgPct"] - cp) < 1e-3


def test_noise_fields_skipped_cleanly():
    """day_volume (varint), currency (string), marketcap (double) must be
    skipped by wire type without corrupting the fields we read."""
    blob = _pricing_frame(id="DX-Y.NYB", price=104.32, currency="USD",
                          day_volume=123456789, marketcap=1.2e13,
                          change_pct=0.11, market_hours=1)
    q = decode_pricing(blob)
    assert q is not None
    assert q["id"] == "DX-Y.NYB"
    assert abs(q["price"] - 104.32) < 1e-2
    assert abs(q["chgPct"] - 0.11) < 1e-3


def test_market_hours_enum_all_values():
    labels = {0: "pre", 1: "regular", 2: "post", 3: "extended"}
    for code, label in labels.items():
        blob = _pricing_frame(id="ES=F", price=5000.0, market_hours=code)
        q = decode_pricing(blob)
        assert q is not None and q["marketHours"] == label


def test_negative_time_zigzag_roundtrip():
    """A negative sint64 must survive zigzag decode (guards a plain-varint bug)."""
    blob = _pricing_frame(id="ES=F", price=5000.0, time_ms=-1000)
    q = decode_pricing(blob)
    assert q is not None and q["ts_ms"] == -1000


# --------------------------------------------------------------------------- #
# Junk / partial / non-actionable frames -> None
# --------------------------------------------------------------------------- #

def test_empty_bytes_returns_none():
    assert decode_pricing(b"") is None


def test_empty_string_returns_none():
    assert decode_pricing("") is None


def test_invalid_base64_returns_none():
    assert decode_pricing("!!!not base64@@@") is None


def test_random_junk_bytes_returns_none_not_raise():
    # Must never raise, whatever the bytes.
    for junk in (b"\xff\xff\xff\xff", b"\x08", b"\x12\x7f", bytes(range(30))):
        # Any dict returned must at least be self-consistent; else None.
        out = decode_pricing(junk)
        assert out is None or (out["id"] and out["price"] is not None)


def test_heartbeat_no_id_returns_none():
    """A frame with no symbol id (id-less / heartbeat-shaped) is dropped."""
    blob = _pricing_frame(price=1.0, market_hours=1)  # no id
    assert decode_pricing(blob) is None


def test_id_without_price_returns_none():
    """A symbol with no price is not actionable -> dropped."""
    blob = _pricing_frame(id="ES=F", market_hours=1)  # no price
    assert decode_pricing(blob) is None


def test_truncated_float_field_drops_frame():
    """A frame cut off mid-fixed32 after a valid id+price: the good prefix is
    kept if it already resolved id+price, else dropped. Here we truncate BEFORE
    price resolves -> None."""
    good = _pricing_frame(id="ES=F")           # id only, no price
    truncated = good + _tag(2, 5) + b"\x00\x01"  # price tag + only 2 of 4 bytes
    assert decode_pricing(truncated) is None


def test_partial_frame_after_valid_price_keeps_prefix():
    """id + price resolved, THEN a truncated trailing field: we keep the usable
    id+price rather than throwing the good data away."""
    blob = _pricing_frame(id="ES=F", price=5100.0)
    truncated = blob + _tag(8, 5) + b"\x00"     # change_pct tag + 1 of 4 bytes
    q = decode_pricing(truncated)
    assert q is not None
    assert q["id"] == "ES=F" and abs(q["price"] - 5100.0) < 1e-2
    assert q["chgPct"] is None  # the truncated field never landed
