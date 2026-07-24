"""app/tape.py — the Live Tape relay (Phase 1).

One process-wide background task connects to Yahoo's unofficial streamer
websocket (wss://streamer.finance.yahoo.com), subscribes the six tape symbols,
decodes each frame with the pure vendored decoder (app/tape_decode.py), keeps a
last-quote cache, and fans every update out to all connected browsers over a
same-origin ``GET /ws/tape``. No browser ever talks to the unofficial upstream
directly (China-reachable + no CORS + one shared upstream connection); no API
keys are involved anywhere in this lane.

Fallback ladder (masterplan §0.2 / honesty rails §6):
  1. upstream trade tick  -> basis "quote"  (honest last price from the feed)
  2. upstream silent >~60s during expected trading hours -> REST poll of
     engine.live_quotes every <=15s -> basis "poll" (honestly downgraded)
  3. the socket being down entirely -> the browser's existing live.js polling
     (worker/snapshot) covers the page; and if THAT is down, the baked numbers
     stand. Each tier keeps its own freshness stamping.

Broadcast payload (JSON, one per symbol update, plus a full snapshot on connect):
    {"sym": "ES=F", "price": 5432.25, "chgPct": 0.85,
     "ts": 1753380000000, "basis": "quote"}
  - ts is epoch MILLISECONDS (matches Date.now() on the client so freshness math
    is trivial).
  - basis is one of "quote" (live upstream tick), "poll" (REST fallback), never
    a fabricated "live".

The whole module is import-safe with no network side effects: nothing connects
until start_tape_hub() is called from the app startup hook, and it degrades to a
no-op (the endpoint just serves the empty cache) if the websockets client lib is
absent.
"""
from __future__ import annotations

import asyncio
import contextlib
import json
import logging
import time
from typing import Any

# WebSocket / WebSocketDisconnect are imported at MODULE level (not inside
# register_tape) because `from __future__ import annotations` makes the endpoint's
# `websocket: WebSocket` annotation a STRING that FastAPI resolves against this
# module's globals — a function-local import leaves it unresolvable and FastAPI
# then mistakes the param for a query field.
from fastapi import WebSocket, WebSocketDisconnect

log = logging.getLogger("macro.tape")

# The six tape instruments (masterplan D1 / build spec §1). ORDER here mirrors
# the dashboard strip; it also drives the upstream subscribe list.
TAPE_SYMBOLS: tuple[str, ...] = ("ES=F", "NQ=F", "YM=F", "RTY=F", "^TNX", "DX-Y.NYB")

_UPSTREAM_URL = "wss://streamer.finance.yahoo.com"

# Silence budget: if no upstream frame arrives for this many seconds we assume
# the feed is dead/idle and lean on the REST fallback. 60s per the masterplan.
_UPSTREAM_SILENCE_S = 60.0
# REST fallback cadence (masterplan gate 4: <=15s).
_POLL_INTERVAL_S = 15.0
# Server->client heartbeat so idle proxies don't cull the socket + the client can
# detect a dead relay. 20s per the build spec.
_HEARTBEAT_S = 20.0
# Upstream reconnect backoff (exponential, capped).
_RECONNECT_BASE_S = 1.0
_RECONNECT_MAX_S = 60.0


class TapeHub:
    """Owns the upstream connection, the last-quote cache, and client fanout.

    A single instance lives on app.state.tape_hub. Thread-affine to the asyncio
    loop it is started on; all mutation happens inside that loop (no locks
    needed — the cache dict and client set are only touched from coroutines on
    the one loop).
    """

    def __init__(self, symbols: tuple[str, ...] = TAPE_SYMBOLS):
        self.symbols = symbols
        # sym -> last broadcast payload dict {"sym","price","chgPct","ts","basis"}
        self._cache: dict[str, dict[str, Any]] = {}
        self._clients: set[asyncio.Queue] = set()
        self._last_upstream_ms: float = 0.0  # wall-clock (ms) of last decoded frame
        self._task: asyncio.Task | None = None
        self._poll_task: asyncio.Task | None = None
        self._stopping = False

    # -- lifecycle ---------------------------------------------------------

    def start(self) -> None:
        if self._task is not None:
            return
        self._stopping = False
        self._task = asyncio.ensure_future(self._run_upstream())
        self._poll_task = asyncio.ensure_future(self._run_poll_fallback())
        log.info("tape hub started (%d symbols)", len(self.symbols))

    async def stop(self) -> None:
        self._stopping = True
        for t in (self._task, self._poll_task):
            if t is not None:
                t.cancel()
                with contextlib.suppress(asyncio.CancelledError, Exception):
                    await t
        self._task = self._poll_task = None

    # -- client registration ----------------------------------------------

    def register(self) -> asyncio.Queue:
        """A new browser connection. Returns a queue seeded with a full snapshot
        of the current cache so the tile shows a number immediately."""
        q: asyncio.Queue = asyncio.Queue(maxsize=256)
        self._clients.add(q)
        # snapshot-on-connect: one message per cached symbol.
        for payload in self._cache.values():
            with contextlib.suppress(asyncio.QueueFull):
                q.put_nowait(payload)
        return q

    def unregister(self, q: asyncio.Queue) -> None:
        self._clients.discard(q)

    def snapshot(self) -> list[dict[str, Any]]:
        return list(self._cache.values())

    # -- fanout ------------------------------------------------------------

    def _publish(self, payload: dict[str, Any]) -> None:
        """Cache the latest per-symbol payload and fan it out. A ws quote wins
        only when its ts is fresher than what we already cached, but ONLY within
        the same basis: an out-of-order upstream ("quote") frame is dropped so a
        late quote can't clobber a fresher one, while a "poll" fallback ALWAYS
        refreshes even though its data ts (engine.live_quotes quote_ts) may be
        older than the last live tick — otherwise a dead upstream would leave the
        cache frozen on an ever-staler quote and the fallback would be defeated.
        A basis change (quote->poll on upstream death, poll->quote on recovery)
        always refreshes for the same reason."""
        sym = payload.get("sym")
        if not sym:
            return
        prev = self._cache.get(sym)
        if (prev is not None
                and payload.get("basis") == prev.get("basis")
                and payload.get("ts", 0) < prev.get("ts", 0)):
            return  # same-basis out-of-order frame — ignore
        self._cache[sym] = payload
        dead: list[asyncio.Queue] = []
        for q in self._clients:
            try:
                q.put_nowait(payload)
            except asyncio.QueueFull:
                # A wedged/slow client: drop it rather than block the hub.
                dead.append(q)
        for q in dead:
            self._clients.discard(q)

    # -- upstream loop -----------------------------------------------------

    async def _run_upstream(self) -> None:
        """Connect + subscribe + decode, with exponential reconnect. Never
        raises out of the loop — any failure just triggers a backoff+retry so
        the endpoint keeps serving the cache (or the poll fallback fills it)."""
        try:
            import websockets  # noqa: PLC0415 — bundled with uvicorn[standard]
        except Exception as e:  # noqa: BLE001
            log.warning("tape: websockets client unavailable (%s); "
                        "relay runs on REST poll fallback only", e)
            return
        from app.tape_decode import decode_pricing  # noqa: PLC0415

        backoff = _RECONNECT_BASE_S
        while not self._stopping:
            try:
                async with websockets.connect(
                    _UPSTREAM_URL, ping_interval=20, ping_timeout=20,
                    close_timeout=5, max_queue=64,
                ) as ws:
                    sub = json.dumps({"subscribe": list(self.symbols)})
                    await ws.send(sub)
                    log.info("tape: upstream connected, subscribed %s", self.symbols)
                    backoff = _RECONNECT_BASE_S  # reset on a clean connect
                    async for raw in ws:
                        self._on_upstream_message(raw, decode_pricing)
            except asyncio.CancelledError:
                raise
            except Exception as e:  # noqa: BLE001 — reconnect on any upstream error
                log.info("tape: upstream disconnected (%s); reconnecting in %.0fs",
                         e, backoff)
            if self._stopping:
                break
            await asyncio.sleep(backoff)
            backoff = min(backoff * 2, _RECONNECT_MAX_S)

    def _on_upstream_message(self, raw, decode_pricing) -> None:
        """Decode one upstream frame and publish it. Yahoo sends base64 TEXT
        frames (delivered as ``str`` by the websockets client); if a binary
        frame ever arrives, ``bytes`` that are ASCII-base64 are normalised to
        text so the same decoder path applies. Frames that don't resolve to an
        actionable id+price are silently dropped by the decoder (returns None)."""
        if isinstance(raw, (bytes, bytearray)):
            # Base64 payload arriving as a binary frame -> decode as text; if it
            # isn't valid ASCII it's passed through as raw protobuf bytes.
            try:
                raw = bytes(raw).decode("ascii")
            except UnicodeDecodeError:
                pass
        q = None
        try:
            q = decode_pricing(raw)
        except Exception:  # noqa: BLE001 — a decode must never kill the loop
            q = None
        if not q:
            return
        sym = q["id"]
        if sym not in self._cache and sym not in self.symbols:
            # ignore any symbol we didn't subscribe (defensive)
            return
        now_ms = time.time() * 1000.0
        self._last_upstream_ms = now_ms
        chg = q.get("chgPct")
        prev = q.get("prevClose")
        if chg is None and prev not in (None, 0):
            chg = (q["price"] / prev - 1.0) * 100.0
        payload = {
            "sym": sym,
            "price": round(float(q["price"]), 6),
            "chgPct": round(float(chg), 4) if chg is not None else None,
            # ts from the frame if present (epoch ms), else our receive time.
            "ts": int(q["ts_ms"]) if q.get("ts_ms") else int(now_ms),
            "basis": "quote",
        }
        self._publish(payload)

    # -- REST poll fallback ------------------------------------------------

    async def _run_poll_fallback(self) -> None:
        """When the upstream has been silent past the budget, poll
        engine.live_quotes and broadcast with basis 'poll' (honestly
        downgraded). Runs on its own cadence; it never fires while fresh quotes
        are flowing, so a healthy feed pays nothing."""
        while not self._stopping:
            try:
                await asyncio.sleep(_POLL_INTERVAL_S)
                now_ms = time.time() * 1000.0
                silent_for = (now_ms - self._last_upstream_ms) / 1000.0
                if self._last_upstream_ms and silent_for < _UPSTREAM_SILENCE_S:
                    continue  # upstream is healthy — no poll needed
                await self._poll_once()
            except asyncio.CancelledError:
                raise
            except Exception as e:  # noqa: BLE001 — a poll failure must never kill the loop
                log.debug("tape: poll fallback tick failed (%s)", e)

    async def _poll_once(self) -> None:
        """One REST snapshot of the tape symbols -> basis 'poll' broadcasts.
        engine.live_quotes is a blocking requests-based call, so it runs in a
        thread to avoid stalling the event loop."""
        quotes = await asyncio.to_thread(self._fetch_rest_quotes)
        if not quotes:
            return
        now_ms = time.time() * 1000.0
        for sym, q in quotes.items():
            price = q.get("price")
            if price is None:
                continue
            prev = q.get("prev_close")
            chg = None
            if prev not in (None, 0):
                chg = (price / prev - 1.0) * 100.0
            ts_ms = _iso_to_ms(q.get("quote_ts")) or int(now_ms)
            payload = {
                "sym": sym,
                "price": round(float(price), 6),
                "chgPct": round(float(chg), 4) if chg is not None else None,
                "ts": int(ts_ms),
                "basis": "poll",
            }
            self._publish(payload)

    def _fetch_rest_quotes(self) -> dict[str, dict]:
        """Blocking REST fetch (runs in a worker thread). Late import so the
        module imports with no engine dependency + startup never blocks on it."""
        try:
            from engine import live_quotes  # noqa: PLC0415
            return live_quotes.fetch_quotes(list(self.symbols)) or {}
        except Exception as e:  # noqa: BLE001
            log.debug("tape: REST fetch_quotes failed (%s)", e)
            return {}


def _iso_to_ms(iso: str | None) -> int | None:
    """ISO-8601 (engine.live_quotes quote_ts) -> epoch ms. None on any failure."""
    if not iso:
        return None
    try:
        from datetime import datetime  # noqa: PLC0415
        return int(datetime.fromisoformat(iso).timestamp() * 1000)
    except Exception:  # noqa: BLE001
        return None


# --------------------------------------------------------------------------- #
# App wiring — router + startup helpers (imported by app/main.py)
# --------------------------------------------------------------------------- #

def _get_hub(app) -> TapeHub:
    hub = getattr(app.state, "tape_hub", None)
    if hub is None:
        hub = TapeHub()
        app.state.tape_hub = hub
    return hub


def start_tape_hub(app) -> None:
    """Called from the app startup hook. Idempotent + never raises."""
    try:
        hub = _get_hub(app)
        hub.start()
    except Exception as e:  # noqa: BLE001 — a relay wiring error must not crash the API
        log.warning("tape: hub failed to start (%s); page degrades to polling", e)


async def stop_tape_hub(app) -> None:
    hub = getattr(app.state, "tape_hub", None)
    if hub is not None:
        with contextlib.suppress(Exception):
            await hub.stop()


def register_tape(app) -> None:
    """Wire the /ws/tape websocket route onto the FastAPI app. Kept as a
    function (not a module-level router include) because a WebSocket route needs
    the live ``app`` to reach app.state.tape_hub, and startup/shutdown hooks are
    registered here in one place."""

    @app.websocket("/ws/tape")
    async def ws_tape(websocket: WebSocket) -> None:  # noqa: ANN001
        await websocket.accept()
        hub = _get_hub(websocket.app)
        # A lazily-started hub: if the startup hook didn't fire (e.g. a test
        # client that only exercises the route), start it on first connect.
        hub.start()
        q = hub.register()
        try:
            while True:
                try:
                    payload = await asyncio.wait_for(q.get(), timeout=_HEARTBEAT_S)
                    await websocket.send_json(payload)
                except asyncio.TimeoutError:
                    # 20s server heartbeat — keeps proxies from culling an idle
                    # socket and lets the client detect a dead relay.
                    await websocket.send_json({"type": "heartbeat",
                                               "ts": int(time.time() * 1000)})
        except WebSocketDisconnect:
            pass
        except Exception as e:  # noqa: BLE001
            log.debug("tape: ws client dropped (%s)", e)
        finally:
            hub.unregister(q)

    @app.on_event("startup")
    async def _tape_startup() -> None:
        start_tape_hub(app)

    @app.on_event("shutdown")
    async def _tape_shutdown() -> None:
        await stop_tape_hub(app)
