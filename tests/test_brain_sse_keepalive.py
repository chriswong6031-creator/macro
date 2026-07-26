"""brain_runs.follow: the brain SSE stream must never go silent long enough to be
culled to a blank "reply didn't make it through".

The brain generator has long dead-air gaps — the blocking tool-calling turns and
(the big one) synthesis, which is buffered server-side before the single delta.
`brain_runs` pumps the generator on its own thread and `follow()` streams the
buffer, injecting `: keepalive` comments during any gap and converting a mid-stream
generator failure into a degraded delta+done so the client never sees a bare drop.

(These guarantees used to live in app.main._sse_keepalive; brain_runs took over the
pump when a run stopped being owned by its connection — see test_brain_runs.py for
the durability/resume half.)
"""
import json
import time

from app import brain_runs


def _follow(source, interval, **kw):
    run = brain_runs.start(source, user_id="u1", **kw)
    return list(brain_runs.follow(run, interval=interval)), run


def test_keepalive_injected_during_dead_air_preserving_order():
    def slow_source():
        yield "data: meta\n\n"
        time.sleep(0.75)          # dead air > interval → keepalive(s)
        yield "data: tool\n\n"
        time.sleep(0.75)
        yield "data: delta\n\n"
        yield "data: done\n\n"

    out, _ = _follow(slow_source(), 0.3)
    data = [o for o in out if o.startswith("data:")]
    assert data == ["data: meta\n\n", "data: tool\n\n", "data: delta\n\n", "data: done\n\n"]
    # keepalives are SSE comments (ignored by the client parser), real bytes on the wire
    assert out.count(": keepalive\n\n") >= 2
    assert all(k.startswith(":") for k in out if not k.startswith("data:"))


def test_no_keepalive_when_stream_is_prompt():
    def fast_source():
        yield "data: meta\n\n"
        yield "data: delta\n\n"
        yield "data: done\n\n"

    out, _ = _follow(fast_source(), 5.0)
    assert [o for o in out if o.startswith("data:")] == [
        "data: meta\n\n", "data: delta\n\n", "data: done\n\n"
    ]
    assert ": keepalive\n\n" not in out


def test_generator_exception_becomes_degraded_delta_and_done():
    def boom_source():
        yield "data: meta\n\n"
        raise RuntimeError("kaboom")

    out, run = _follow(boom_source(), 5.0)
    data = [o for o in out if o.startswith("data:")]
    assert data[0] == "data: meta\n\n"
    # a degraded delta then a done — never a bare drop with no delta
    delta = json.loads(data[1][5:].strip())
    done = json.loads(data[2][5:].strip())
    assert delta["type"] == "delta" and delta["text"]
    assert done["type"] == "done" and done["degraded"] is True
    # ...and the degraded turn is BUFFERED, so a client that re-attaches after the
    # failure sees the same terminated turn rather than an empty run.
    assert run.done and len(run.events) == 3
