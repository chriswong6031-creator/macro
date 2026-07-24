"""app/tape_decode.py — vendored, dependency-free decoder for Yahoo's streamer
websocket frames (Live Tape Phase 1, research/LIVE_TAPE_SCOREBOARD_MASTERPLAN.md).

The unofficial Yahoo streamer (wss://streamer.finance.yahoo.com) pushes one
base64-encoded protobuf ``PricingData`` message per frame. Rather than pull a
protobuf runtime + a generated stub into the lean serving-tier requirements
(app/requirements.txt), we hand-roll a MINIMAL wire parser for exactly the six
fields the tape needs. This is a PURE function — no I/O, no sockets, no clock —
so it is fully covered by unit tests against recorded / synthetic frames
(tests/test_tape_decode.py). If Yahoo ever ships an incompatible schema the
tests fail here first, before the relay ships a bad number.

Canonical ``PricingData`` field map (proto3; only the fields we read):

    field 1  id            string   — the symbol (e.g. "ES=F", "^TNX")
    field 2  price         float    — last price (fixed32, IEEE-754 LE)
    field 3  time          sint64   — epoch **milliseconds**, ZIGZAG varint
    field 7  marketHours   enum     — 0 PRE / 1 REGULAR / 2 POST / 3 EXTENDED
    field 8  changePercent float    — % change vs prev close (fixed32)
    field 16 previousClose float    — prior settle (fixed32)

Wire types we handle: 0 (varint), 5 (fixed32). Length-delimited (2) is read for
the ``id`` string and skipped for anything else; fixed64 (1) is skipped. Unknown
fields are skipped by wire type so a schema addition never breaks the parse.

HONESTY: this decoder reports only what the frame carried. It never fabricates a
price, a timestamp, or a "live" basis — those judgments live in app/tape.py.
"""
from __future__ import annotations

import base64
import struct
from typing import Any

# Yahoo streams time as epoch milliseconds; the relay works in ms internally and
# lets the client convert. marketHours enum → a short honest label.
_MARKET_HOURS = {0: "pre", 1: "regular", 2: "post", 3: "extended"}


def _read_varint(buf: bytes, pos: int) -> tuple[int, int]:
    """Decode a base-128 varint at ``pos``. Returns (value, new_pos).

    Raises ValueError on a truncated varint (continuation bit set at EOF) so a
    partial frame is rejected cleanly rather than silently returning garbage.
    """
    result = 0
    shift = 0
    n = len(buf)
    while pos < n:
        b = buf[pos]
        result |= (b & 0x7F) << shift
        pos += 1
        if not (b & 0x80):
            return result, pos
        shift += 7
        if shift > 63:  # a well-formed 64-bit varint never exceeds 10 bytes
            raise ValueError("varint too long")
    raise ValueError("truncated varint")


def _zigzag_decode(n: int) -> int:
    """sint64 zigzag → signed int. Yahoo encodes ``time`` (and other sint64s)
    this way; a plain-varint read would yield a huge positive garbage value."""
    return (n >> 1) ^ -(n & 1)


def decode_pricing(raw: bytes | str) -> dict[str, Any] | None:
    """Decode ONE Yahoo ``PricingData`` frame.

    ``raw`` is either the base64 text as received on the socket, or the already
    base64-decoded protobuf bytes. Returns a normalised dict::

        {"id": str, "price": float|None, "ts_ms": int|None,
         "chgPct": float|None, "prevClose": float|None, "marketHours": str|None}

    Returns ``None`` for a frame that carries no symbol id (e.g. a heartbeat or
    an undecodable / empty payload) — the caller drops those. Never raises on a
    malformed frame: a decode error yields ``None`` so one bad frame can never
    take down the relay loop.
    """
    if isinstance(raw, str):
        try:
            # Yahoo may or may not pad; validate=False tolerates whitespace.
            buf = base64.b64decode(raw)
        except Exception:
            return None
    else:
        buf = raw
    if not buf:
        return None

    out: dict[str, Any] = {
        "id": None, "price": None, "ts_ms": None,
        "chgPct": None, "prevClose": None, "marketHours": None,
    }
    pos = 0
    n = len(buf)
    try:
        while pos < n:
            key, pos = _read_varint(buf, pos)
            field = key >> 3
            wire = key & 0x07

            if wire == 0:  # varint
                val, pos = _read_varint(buf, pos)
                if field == 3:      # time — sint64 zigzag, epoch ms
                    out["ts_ms"] = _zigzag_decode(val)
                elif field == 7:    # marketHours enum
                    out["marketHours"] = _MARKET_HOURS.get(val, str(val))
                # other varint fields (dayVolume, etc.) ignored
            elif wire == 5:  # fixed32 — float32 LE
                if pos + 4 > n:
                    raise ValueError("truncated fixed32")
                fval = struct.unpack_from("<f", buf, pos)[0]
                pos += 4
                if field == 2:
                    out["price"] = fval
                elif field == 8:
                    out["chgPct"] = fval
                elif field == 16:
                    out["prevClose"] = fval
                # other float fields (dayHigh/Low/change/…) ignored
            elif wire == 1:  # fixed64 (double) — skip (marketcap etc.)
                if pos + 8 > n:
                    raise ValueError("truncated fixed64")
                pos += 8
            elif wire == 2:  # length-delimited (string/bytes)
                ln, pos = _read_varint(buf, pos)
                if pos + ln > n:
                    raise ValueError("truncated length-delimited")
                chunk = buf[pos:pos + ln]
                pos += ln
                if field == 1:  # id (symbol)
                    try:
                        out["id"] = chunk.decode("utf-8")
                    except UnicodeDecodeError:
                        return None
                # other string fields (currency/exchange/shortName/…) ignored
            else:
                # wire types 3/4 (groups, deprecated) — unparseable stream; bail.
                raise ValueError(f"unsupported wire type {wire}")
    except (ValueError, struct.error, IndexError):
        # A partial or corrupt frame: return whatever we resolved IF it at least
        # named a symbol AND a price; otherwise drop it. A frame with only an id
        # and no price is not actionable, so it is dropped too.
        pass

    if not out["id"] or out["price"] is None:
        return None
    return out
