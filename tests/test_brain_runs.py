"""brain_runs: a chat turn must outlive the browser tab that started it.

The failure this module exists to kill: the user asks a question, switches apps or
lets the phone sleep, the SSE socket dies, and the widget shows "The reply didn't
make it through." — even though the model finished thinking seconds later. A run is
now owned by the registry, not by the connection, so:

  * the generator runs to completion (and the gateway still persists both turns to
    the thread store) whether or not anyone is attached;
  * a returning client re-attaches at its cursor and gets the rest, or replays the
    whole answer if it reloaded;
  * a run id is useless to anyone but its owner.
"""
import json
import threading
import time

import pytest

from app import brain_runs


@pytest.fixture(autouse=True)
def _clean_registry():
    brain_runs.reset_for_tests()
    yield
    brain_runs.reset_for_tests()


def _sse(payload: dict) -> str:
    return "data: " + json.dumps(payload) + "\n\n"


def _drain(run, cursor=0, interval=5.0):
    """Collect a follow() to completion, dropping keepalive comments."""
    return [e for e in brain_runs.follow(run, cursor=cursor, interval=interval)
            if e.startswith("data:")]


def _types(events):
    return [json.loads(e[5:].strip())["type"] for e in events]


# ── the core promise: the run finishes without a reader ───────────────────────

def test_run_completes_with_nobody_attached():
    """Nothing ever calls follow() — the generator must still run to its end.

    This is the "user closed the tab" case. The gateway's post-stream thread
    persistence lives at the tail of that generator, so if the pump stopped when the
    reader left, the answer would never be written anywhere.
    """
    finished = threading.Event()

    def source():
        yield _sse({"type": "meta", "thread_id": "t-9"})
        yield _sse({"type": "delta", "text": "hello"})
        yield _sse({"type": "done"})
        finished.set()          # stands in for _append_message + cost accounting

    run = brain_runs.start(source(), user_id="u1")
    assert finished.wait(timeout=5), "pump stopped when no client was attached"
    for _ in range(50):
        if run.done:
            break
        time.sleep(0.02)
    assert run.done and _types(run.events) == ["meta", "delta", "done"]


def test_reader_that_leaves_midstream_does_not_kill_the_run():
    """Closing follow() early (client disconnect) must not disturb the generator."""
    gate = threading.Event()

    def source():
        yield _sse({"type": "meta"})
        gate.wait(timeout=5)         # the client vanishes during this gap
        yield _sse({"type": "delta", "text": "late answer"})
        yield _sse({"type": "done"})

    run = brain_runs.start(source(), user_id="u1")
    stream = brain_runs.follow(run, interval=0.05)
    assert next(stream).startswith("data:")   # meta
    stream.close()                            # ← disconnect
    gate.set()

    for _ in range(200):
        if run.done:
            break
        time.sleep(0.02)
    assert run.done, "run died with its reader"
    assert _types(run.events) == ["meta", "delta", "done"]


# ── resume ───────────────────────────────────────────────────────────────────

def test_resume_from_cursor_returns_only_the_tail():
    def source():
        yield _sse({"type": "meta"})
        yield _sse({"type": "tool", "name": "get_quote"})
        yield _sse({"type": "delta", "text": "answer"})
        yield _sse({"type": "done"})

    run = brain_runs.start(source(), user_id="u1")
    assert _types(_drain(run)) == ["meta", "tool", "delta", "done"]
    # a client that had consumed meta+tool before the drop resumes at 2
    assert _types(_drain(run, cursor=2)) == ["delta", "done"]
    # a client that reloaded and lost its DOM replays the whole turn
    assert _types(_drain(run, cursor=0)) == ["meta", "tool", "delta", "done"]
    # a cursor past the head is not an error — there is simply nothing left
    assert _drain(run, cursor=99) == []


def test_resume_picks_up_events_produced_while_disconnected():
    """The answer lands while nobody is listening; the returning client still gets it."""
    released = threading.Event()

    def source():
        yield _sse({"type": "meta"})
        released.wait(timeout=5)
        yield _sse({"type": "delta", "text": "produced while away"})
        yield _sse({"type": "done"})

    run = brain_runs.start(source(), user_id="u1")
    first = brain_runs.follow(run, interval=0.05)
    next(first)
    first.close()                 # away
    released.set()
    time.sleep(0.1)               # the model finishes in the meantime

    tail = _drain(run, cursor=1)
    assert _types(tail) == ["delta", "done"]
    assert json.loads(tail[0][5:].strip())["text"] == "produced while away"


def test_follow_waits_for_a_live_run_then_delivers():
    """A client re-attaching to a still-thinking run blocks, then receives the rest."""
    def source():
        yield _sse({"type": "meta"})
        time.sleep(0.25)
        yield _sse({"type": "delta", "text": "slow"})
        yield _sse({"type": "done"})

    run = brain_runs.start(source(), user_id="u1")
    t0 = time.time()
    assert _types(_drain(run, cursor=0, interval=5.0)) == ["meta", "delta", "done"]
    assert time.time() - t0 >= 0.2, "follow returned before the run produced its answer"


# ── ownership + lifecycle ────────────────────────────────────────────────────

def test_run_id_alone_cannot_read_another_users_run():
    def source():
        yield _sse({"type": "done"})

    run = brain_runs.start(source(), user_id="owner")
    assert brain_runs.get(run.run_id, "owner") is run
    assert brain_runs.get(run.run_id, "someone-else") is None
    assert brain_runs.get("no-such-run", "owner") is None


def test_thread_id_is_learned_from_the_meta_event():
    """A first turn carries no thread_id in the request — the thread is created inside
    the gateway. The registry reads it off the wire so a reloaded client knows which
    conversation to reopen."""
    def source():
        yield _sse({"type": "meta", "thread_id": "thr-123"})
        yield _sse({"type": "done"})

    run = brain_runs.start(source(), user_id="u1", thread_id=None)
    _drain(run)
    assert run.thread_id == "thr-123"
    assert run.status()["thread_id"] == "thr-123"


def test_active_for_lists_only_the_callers_runs_newest_first():
    def done_source():
        yield _sse({"type": "done"})

    a = brain_runs.start(done_source(), user_id="u1", lane="fast")
    _drain(a)
    time.sleep(0.01)
    b = brain_runs.start(done_source(), user_id="u1", lane="pro")
    _drain(b)
    other = brain_runs.start(done_source(), user_id="u2")
    _drain(other)

    rows = brain_runs.active_for("u1")
    assert [r["run_id"] for r in rows] == [b.run_id, a.run_id]
    assert rows[0]["lane"] == "pro"
    assert all(r["run_id"] != other.run_id for r in rows)


def test_finished_runs_expire_on_the_ttl():
    def source():
        yield _sse({"type": "done"})

    run = brain_runs.start(source(), user_id="u1")
    _drain(run)
    assert not run.expired()
    run.finished_at = time.time() - brain_runs.RUN_TTL_S - 1
    assert run.expired()
    assert brain_runs.get(run.run_id, "u1") is None      # and is swept on access


def test_a_live_run_outlives_the_ttl_but_not_the_live_ceiling():
    """A Deep Research turn legitimately runs for minutes, so the finished-run TTL must
    not touch it — but a generator wedged on a provider that never returns would
    otherwise pin its slot and its daemon thread for the life of the process."""
    live = brain_runs.BrainRun("live", "u1", None, "pro", "research")
    live.started_at = time.time() - brain_runs.RUN_TTL_S * 1.5
    assert not live.expired(), "a long research turn was evicted mid-flight"
    live.started_at = time.time() - brain_runs.RUN_LIVE_MAX_S - 1
    assert live.expired(), "a wedged run is retained forever"


def test_the_terminal_done_event_survives_the_per_run_event_cap():
    """Truncation must never eat the `done`. A guest has no thread row to fall back on,
    so a capped run with no terminal event is a fully-paid answer reported as lost."""
    run = brain_runs.BrainRun("capped", "u1", None, "fast", "chat")
    for i in range(brain_runs.RUN_EVENT_CAP + 5):
        run.append(_sse({"type": "delta", "text": str(i)}))
    assert len(run.events) == brain_runs.RUN_EVENT_CAP
    run.append(_sse({"type": "tool", "name": "dropped"}))
    assert len(run.events) == brain_runs.RUN_EVENT_CAP     # non-terminal still dropped
    run.append(_sse({"type": "done", "citations": []}))
    assert run.truncated is True
    assert _types(run.events)[-1] == "done"


def test_cancel_ends_follow_and_blocks_reattachment():
    """Stop must not leave a widget re-attaching to a turn the user abandoned."""
    def source():
        yield _sse({"type": "meta"})
        time.sleep(3)                      # still "thinking" when Stop is pressed
        yield _sse({"type": "done"})

    run = brain_runs.start(source(), user_id="u1")
    stream = brain_runs.follow(run, interval=0.05)
    next(stream)                            # meta
    assert brain_runs.cancel(run.run_id, "u1") is True
    assert list(stream) == []               # follow returns instead of hanging
    assert run.cancelled is True
    assert brain_runs.cancel(run.run_id, "someone-else") is False


def test_registry_is_capped():
    """A busy day can never grow the registry without bound."""
    def source():
        yield _sse({"type": "done"})

    for _ in range(brain_runs.RUN_CAP + 25):
        _drain(brain_runs.start(source(), user_id="u1"))
    assert brain_runs._iter_len() <= brain_runs.RUN_CAP


def test_run_event_carries_what_a_client_needs_to_resume():
    def source():
        yield _sse({"type": "done"})

    run = brain_runs.start(source(), user_id="u1", thread_id="t1", lane="pro", mode="research")
    evt = json.loads(brain_runs.run_event(run)[5:].strip())
    assert evt == {"type": "run", "run_id": run.run_id, "cursor": 0,
                   "thread_id": "t1", "lane": "pro", "mode": "research"}
    # the envelope is NEVER buffered — buffer indices must stay equal to the client's
    # count of received brain events, or every resume cursor would be off by one.
    _drain(run)
    assert all('"type": "run"' not in e for e in run.events)


# ── routes ───────────────────────────────────────────────────────────────────
# NOTE (repo memory fastapi-includedrouter-route-verify): this fastapi wraps routes in
# _IncludedRouter, so verify endpoints via TestClient RESPONSES, never by scanning
# app.routes for .path.

def _client():
    from fastapi.testclient import TestClient
    from app.main import app
    return TestClient(app), app


def _as_user(app, uid="run-user"):
    from app.main import _brain_user_or_guest
    app.dependency_overrides[_brain_user_or_guest] = lambda: {
        "id": uid, "email": f"{uid}@x.com", "_is_guest": False,
        "_guest_aid": "", "_guest_ip": "",
    }


def test_resume_route_replays_from_cursor():
    def source():
        yield _sse({"type": "meta", "thread_id": "t7"})
        yield _sse({"type": "delta", "text": "the answer"})
        yield _sse({"type": "done"})

    client, app = _client()
    _as_user(app)
    try:
        run = brain_runs.start(source(), user_id="run-user")
        _drain(run)
        resp = client.get(f"/api/brain/runs/{run.run_id}/stream?cursor=1")
        assert resp.status_code == 200
        assert "the answer" in resp.text
        assert '"type": "meta"' not in resp.text     # already consumed → not replayed
        assert '"type": "done"' in resp.text
    finally:
        app.dependency_overrides.clear()


def test_status_and_active_routes():
    def source():
        yield _sse({"type": "meta", "thread_id": "t8"})
        yield _sse({"type": "done"})

    client, app = _client()
    _as_user(app)
    try:
        run = brain_runs.start(source(), user_id="run-user", lane="pro", mode="research")
        _drain(run)
        status = client.get(f"/api/brain/runs/{run.run_id}").json()
        assert status["done"] is True
        assert status["thread_id"] == "t8"
        assert status["lane"] == "pro" and status["mode"] == "research"

        rows = client.get("/api/brain/runs/active").json()["runs"]
        assert [r["run_id"] for r in rows] == [run.run_id]

        assert client.post(f"/api/brain/runs/{run.run_id}/cancel").json() == {"ok": True}
    finally:
        app.dependency_overrides.clear()


def test_run_routes_404_for_a_run_the_caller_does_not_own():
    """`active` must not leak it either — a stored run id is not a capability."""
    def source():
        yield _sse({"type": "done"})

    client, app = _client()
    try:
        run = brain_runs.start(source(), user_id="someone-else")
        _drain(run)
        _as_user(app, "run-user")
        assert client.get(f"/api/brain/runs/{run.run_id}").status_code == 404
        assert client.get(f"/api/brain/runs/{run.run_id}/stream").status_code == 404
        assert client.post(f"/api/brain/runs/{run.run_id}/cancel").status_code == 404
        assert client.get("/api/brain/runs/active").json()["runs"] == []
    finally:
        app.dependency_overrides.clear()


def test_active_route_is_not_shadowed_by_the_run_id_route():
    """/api/brain/runs/active must resolve to the listing, not be parsed as a run id."""
    client, app = _client()
    _as_user(app)
    try:
        resp = client.get("/api/brain/runs/active")
        assert resp.status_code == 200 and "runs" in resp.json()
    finally:
        app.dependency_overrides.clear()


def test_active_route_never_enumerates_runs_for_a_guest():
    """THE guest-privacy invariant. A guest principal is `guest:<mm_aid cookie>`, or
    `guest:ip:<hash>`/`guest:anon` with no cookie — shared by every anonymous visitor
    behind one office/CGNAT egress IP, and the cookie half is client-settable. Listing
    run ids to it would hand one visitor another's question and answer verbatim.

    A guest's capability is its 128-bit run id, which is only ever sent to the client
    that started the run; enumeration is what would turn a shared quota bucket into a
    read capability over other people's conversations.
    """
    from app.main import _brain_user_or_guest
    client, app = _client()

    def source():
        yield _sse({"type": "meta", "thread_id": None})
        yield _sse({"type": "delta", "text": "the other visitor's private answer"})
        yield _sse({"type": "done"})

    # visitor A, sharing one office IP → the same guest principal as visitor B
    shared = "guest:ip:deadbeefdeadbeef"
    run = brain_runs.start(source(), user_id=shared)
    _drain(run)

    app.dependency_overrides[_brain_user_or_guest] = lambda: {
        "id": shared, "email": "", "_is_guest": True, "_guest_aid": "", "_guest_ip": "x",
    }
    try:
        assert client.get("/api/brain/runs/active").json() == {"runs": []}, \
            "a guest was handed another guest's run ids"
        # holding the id still works — it is the guest's own resume path
        assert client.get(f"/api/brain/runs/{run.run_id}").status_code == 200
    finally:
        app.dependency_overrides.clear()


def test_active_route_still_lists_for_a_verified_user():
    """The counterpart: a signed-in caller is a verified Supabase id, not a shared
    bucket, so enumeration stays available as their lost-storage recovery path."""
    def source():
        yield _sse({"type": "done"})

    client, app = _client()
    _as_user(app, "real-user")
    try:
        run = brain_runs.start(source(), user_id="real-user")
        _drain(run)
        assert [r["run_id"] for r in client.get("/api/brain/runs/active").json()["runs"]] == [run.run_id]
    finally:
        app.dependency_overrides.clear()


def test_resume_route_404s_a_cancelled_run():
    """A cancelled run would `follow` to an instant empty body; the client would spend
    its whole backoff budget re-attaching to nothing with the composer disabled."""
    def source():
        yield _sse({"type": "meta"})
        time.sleep(2)
        yield _sse({"type": "done"})

    client, app = _client()
    _as_user(app)
    try:
        run = brain_runs.start(source(), user_id="run-user")
        assert client.get(f"/api/brain/runs/{run.run_id}/stream?cursor=0") is not None
        brain_runs.cancel(run.run_id, "run-user")
        assert client.get(f"/api/brain/runs/{run.run_id}/stream").status_code == 404
        assert client.get(f"/api/brain/runs/{run.run_id}").json()["cancelled"] is True
    finally:
        app.dependency_overrides.clear()
