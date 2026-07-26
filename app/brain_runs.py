"""Server-side brain runs — a chat turn outlives the browser tab that started it.

WHY THIS EXISTS
---------------
Before this module the brain answer existed only on one SSE socket. If that socket
died — the user switched apps, the phone froze the tab, a laptop slept, a proxy
culled the connection — the widget showed "The reply didn't make it through." and
the answer was gone, even though the model had already finished thinking. Modern
chat apps don't behave that way: you leave, you come back, the reply is waiting.

The fix is to decouple the RUN from the CONNECTION:

    POST /api/brain/stream  →  start(...)   registers a run, pumps the brain
                                            generator on its own daemon thread
                                            into an ordered event buffer, and
                                            streams that buffer to whoever is
                                            currently attached.
    GET  /api/brain/runs/{id}?cursor=N      re-attaches to the same buffer — replays
                                            everything from N, then follows live.

The pump thread never looks at the client. A disconnect closes the `follow()`
generator; the run keeps going, keeps buffering, and (via brain_gateway's
post-stream `_append_message`) still persists both turns to the thread store. So
there are two independent recovery paths, and they cover different failures:

  * run buffer  — exact replay incl. tool/chart/suggest events, works for guests
                  (who own no threads), survives a reconnect within the TTL.
  * thread store — survives an API restart and a different device, but only ever
                  holds the final answer text.

The client tries the buffer first and falls back to re-reading the thread.

SCOPE / LIFETIME
----------------
In-process, single uvicorn worker (`app/deploy/macro-api.service` runs one
`uvicorn app.main:app` with no `--workers`), so an in-memory registry is coherent
for every request that can reach it. A restart drops in-flight runs — the thread
store is the fallback for exactly that case. Finished runs stay resumable for
_RUN_TTL_S so a user who was away for a few minutes still gets the reply painted
in on return; the registry is swept on every start and hard-capped so it can never
grow without bound.
"""

from __future__ import annotations

import json
import logging
import threading
import time
import uuid
from collections.abc import Generator, Iterable

log = logging.getLogger(__name__)

# Dead-air keepalive. Identical intent to app.main._sse_keepalive (which this
# replaces on the brain routes): mastermind-x.com sits behind Tencent EdgeOne,
# which culls an idle SSE connection at ~20s, and the brain buffers synthesis
# server-side for 40-60s. A `:` comment is ignored by the EventSource parser but
# is real bytes on the socket, so it resets the idle timer.
KEEPALIVE_INTERVAL_S = 12.0

# How long a finished run stays re-attachable. Long enough that "I left, made a
# coffee, came back" still repaints the answer; short enough to stay small.
RUN_TTL_S = 30 * 60

# Absolute ceiling on an UNFINISHED run. Far beyond any real turn (the longest Deep
# Research report is minutes), so it only ever catches a generator that will never
# return — which would otherwise hold its registry slot and daemon thread forever.
RUN_LIVE_MAX_S = 60 * 60

# Hard ceiling on retained runs (finished ones are evicted oldest-first once the
# TTL sweep is not enough). ~200 runs x a few KB of events is a few MB.
RUN_CAP = 200

# Per-run event ceiling — a runaway generator can never exhaust memory.
RUN_EVENT_CAP = 4000

_DEGRADED_FALLBACK = (
    "The AI assistant is temporarily unavailable. Please try again in a moment."
)


def _degraded_msg() -> str:
    """The gateway's user-facing degraded copy, with a local fallback."""
    try:
        from engine.neuralweb.brain_gateway import _DEGRADED_USER_MSG  # noqa: PLC0415
        return _DEGRADED_USER_MSG
    except Exception:  # noqa: BLE001 — import trouble must not break the run
        return _DEGRADED_FALLBACK


class BrainRun:
    """One brain turn: an append-only SSE event buffer plus its completion state.

    `events` holds the RAW brain events only (no keepalives, no envelope), so an
    index into it is a stable cursor a client can resume from. Readers wait on
    `_cv`; the pump appends under it and broadcasts.
    """

    __slots__ = ("run_id", "user_id", "thread_id", "lane", "mode", "started_at",
                 "finished_at", "events", "done", "cancelled", "truncated", "_cv")

    def __init__(self, run_id: str, user_id: str, thread_id: str | None,
                 lane: str, mode: str) -> None:
        self.run_id = run_id
        self.user_id = user_id
        self.thread_id = thread_id
        self.lane = lane
        self.mode = mode
        self.started_at = time.time()
        self.finished_at: float | None = None
        self.events: list[str] = []
        self.done = False
        self.cancelled = False
        self.truncated = False
        self._cv = threading.Condition()

    # ── pump side ────────────────────────────────────────────────────────────
    def append(self, chunk: str) -> None:
        """Buffer one SSE chunk and wake every attached reader.

        A TERMINAL event is always admitted, even at the cap. Dropping the `done` is
        the one truncation a client cannot recover from: the stream would end with no
        terminal event, and a guest (who has no thread row to fall back on) would be
        told the reply didn't make it through on a turn that fully succeeded and was
        already paid for.
        """
        with self._cv:
            if len(self.events) >= RUN_EVENT_CAP:
                self.truncated = True
                if '"type": "done"' not in chunk:
                    return
            self.events.append(chunk)
            self._cv.notify_all()

    def finish(self) -> None:
        with self._cv:
            self.done = True
            self.finished_at = time.time()
            self._cv.notify_all()

    def note_thread(self, chunk: str) -> None:
        """Learn this run's thread_id from the brain's `meta` event.

        The thread is created inside the gateway (a first turn has no thread_id in
        the request body), so the registry can only know it by reading it off the
        wire. A client that reloaded needs it to know which thread to reopen.
        """
        if self.thread_id or not chunk.startswith("data:"):
            return
        try:
            payload = json.loads(chunk[5:].strip())
        except Exception:  # noqa: BLE001 — not JSON / partial: nothing to learn
            return
        if isinstance(payload, dict) and payload.get("type") == "meta":
            tid = payload.get("thread_id")
            if isinstance(tid, str) and tid:
                self.thread_id = tid

    # ── reader side ──────────────────────────────────────────────────────────
    def status(self) -> dict:
        with self._cv:
            return {
                "run_id": self.run_id,
                "thread_id": self.thread_id,
                "lane": self.lane,
                "mode": self.mode,
                "done": self.done,
                "cancelled": self.cancelled,
                "truncated": self.truncated,
                "events": len(self.events),
                "started_at": self.started_at,
                "finished_at": self.finished_at,
                "age_s": round(time.time() - self.started_at, 1),
            }

    def expired(self, now: float | None = None) -> bool:
        """True once a FINISHED run has aged past the TTL.

        A live run is given a much longer rope — a Deep Research turn legitimately
        runs for minutes and must never be evicted mid-flight — but not an infinite
        one: a generator wedged on a provider that never returns would otherwise pin
        its registry slot and its daemon thread for the life of the process, and count
        against RUN_CAP forever.
        """
        now = time.time() if now is None else now
        if not self.done:
            return (now - self.started_at) > RUN_LIVE_MAX_S
        return (now - (self.finished_at or self.started_at)) > RUN_TTL_S


# ── registry ─────────────────────────────────────────────────────────────────
_runs: dict[str, BrainRun] = {}
_runs_lock = threading.Lock()


def _sweep_locked(now: float) -> None:
    """Drop expired runs, then evict oldest FINISHED runs until under the cap.
    Caller holds _runs_lock. A live run is never evicted — it is still generating."""
    for rid in [rid for rid, r in _runs.items() if r.expired(now)]:
        _runs.pop(rid, None)
    if len(_runs) <= RUN_CAP:
        return
    finished = sorted(
        (r for r in _runs.values() if r.done),
        key=lambda r: r.finished_at or r.started_at,
    )
    for run in finished:
        if len(_runs) <= RUN_CAP:
            break
        _runs.pop(run.run_id, None)


def start(source: Iterable[str], *, user_id: str, thread_id: str | None = None,
          lane: str = "fast", mode: str = "chat") -> BrainRun:
    """Register a run and pump `source` into it on a detached daemon thread.

    Returns immediately — the caller streams with `follow(run)`. The pump owns the
    generator from here: it runs to completion (including the gateway's post-stream
    thread persistence and cost accounting) whether or not anyone is listening.
    """
    run = BrainRun(uuid.uuid4().hex, user_id, thread_id, lane, mode)
    with _runs_lock:
        # Insert THEN sweep, so the cap holds inclusive of the new run. The sweep can
        # never evict it: it is neither expired nor finished.
        _runs[run.run_id] = run
        _sweep_locked(time.time())

    def _pump() -> None:
        try:
            for chunk in source:
                run.note_thread(chunk)
                run.append(chunk)
        except Exception as exc:  # noqa: BLE001 — surfaced as a degraded turn
            log.warning("brain_runs: run %s failed (%s)", run.run_id, exc)
            # Never leave a reader with tool events and no answer: buffer a visible
            # degraded delta + done so both the live client and any later resume see
            # a terminated turn instead of a bare drop.
            run.append(f"data: {json.dumps({'type': 'delta', 'text': _degraded_msg()})}\n\n")
            run.append("data: " + json.dumps({
                "type": "done", "citations": [], "quota": {}, "usage": {},
                "filtered": False, "degraded": True, "is_context_only": True,
            }) + "\n\n")
        finally:
            run.finish()

    threading.Thread(target=_pump, name=f"brain-run-{run.run_id[:8]}", daemon=True).start()
    return run


def get(run_id: str, user_id: str) -> BrainRun | None:
    """Return the run iff it exists, has not expired, and belongs to user_id.

    Ownership is checked here rather than at the route so a run id — which the
    owner's browser stores in localStorage — is never enough on its own to read
    somebody else's conversation.
    """
    with _runs_lock:
        run = _runs.get(run_id)
        if run is None:
            return None
        if run.expired():
            _runs.pop(run_id, None)
            return None
    return run if run.user_id == user_id else None


def active_for(user_id: str, limit: int = 5) -> list[dict]:
    """Recent runs for user_id, newest first — the recovery path for a client that
    lost its localStorage (cleared storage, a different tab, a fresh device)."""
    now = time.time()
    with _runs_lock:
        rows = [r for r in _runs.values() if r.user_id == user_id and not r.expired(now)]
    rows.sort(key=lambda r: r.started_at, reverse=True)
    return [r.status() for r in rows[:limit]]


def cancel(run_id: str, user_id: str) -> bool:
    """Mark a run cancelled (the user pressed Stop).

    The provider call already in flight cannot be interrupted, so this does not stop
    the pump — it stops the run being re-attached to, and lets `follow` end promptly
    for anyone still listening. The gateway still persists whatever it produced, which
    matches today's Stop behaviour (the partial stays in the thread).
    """
    run = get(run_id, user_id)
    if run is None:
        return False
    with run._cv:  # noqa: SLF001 — same module, the condition IS the run's lock
        run.cancelled = True
        run._cv.notify_all()  # noqa: SLF001
    return True


def follow(run: BrainRun, cursor: int = 0,
           interval: float = KEEPALIVE_INTERVAL_S) -> Generator[str, None, None]:
    """Yield the run's buffered events from `cursor`, then follow it live.

    Replays instantly up to the head, then blocks for new events, emitting a
    `: keepalive` comment during any gap longer than `interval` so an idle-culling
    proxy (EdgeOne at ~20s) never sees a silent socket. Returns when the run is done
    and the cursor has drained — or as soon as it is cancelled.

    Closing this generator (client disconnect) has NO effect on the run.
    """
    cursor = max(0, int(cursor or 0))
    while True:
        batch: list[str] = []
        with run._cv:  # noqa: SLF001 — reader side of the run's own condition
            if cursor >= len(run.events) and not run.done and not run.cancelled:
                run._cv.wait(timeout=interval)  # noqa: SLF001
            if cursor < len(run.events):
                batch = run.events[cursor:]
                cursor = len(run.events)
            elif run.done or run.cancelled:
                return
        if batch:
            yield from batch
        else:
            yield ": keepalive\n\n"


def run_event(run: BrainRun, cursor: int = 0) -> str:
    """The envelope event a client needs to be able to resume this run.

    Sent ONCE per attachment and never buffered, so buffer indices stay equal to the
    client's count of received brain events. The client stores run_id, counts every
    later event, and resumes at that count.
    """
    return "data: " + json.dumps({
        "type": "run",
        "run_id": run.run_id,
        "cursor": cursor,
        "thread_id": run.thread_id,
        "lane": run.lane,
        "mode": run.mode,
    }) + "\n\n"


def reset_for_tests() -> None:
    """Drop every registered run (unit tests only)."""
    with _runs_lock:
        _runs.clear()


def _iter_len() -> int:
    """Registered run count (unit tests / diagnostics)."""
    with _runs_lock:
        return len(_runs)


__all__ = [
    "KEEPALIVE_INTERVAL_S", "RUN_CAP", "RUN_EVENT_CAP", "RUN_LIVE_MAX_S", "RUN_TTL_S",
    "BrainRun", "active_for", "cancel", "follow", "get", "reset_for_tests", "run_event",
    "start",
]
