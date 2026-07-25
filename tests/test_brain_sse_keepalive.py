"""_sse_keepalive: the brain SSE stream must never go silent long enough to be
culled to a blank "reply didn't make it through".

The brain generator has long dead-air gaps — the blocking tool-calling turns and
(the big one) synthesis, which is buffered server-side before the single delta.
_sse_keepalive wraps the generator, injecting `: keepalive` comments during any
gap and converting a mid-stream generator failure into a degraded delta+done so
the client never sees a bare connection drop.
"""
import json
import time

from app.main import _sse_keepalive


def test_keepalive_injected_during_dead_air_preserving_order():
    def slow_source():
        yield "data: meta\n\n"
        time.sleep(0.75)          # dead air > interval → keepalive(s)
        yield "data: tool\n\n"
        time.sleep(0.75)
        yield "data: delta\n\n"
        yield "data: done\n\n"

    out = list(_sse_keepalive(slow_source(), interval=0.3))
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

    out = list(_sse_keepalive(fast_source(), interval=5.0))
    assert out == ["data: meta\n\n", "data: delta\n\n", "data: done\n\n"]
    assert ": keepalive\n\n" not in out


def test_generator_exception_becomes_degraded_delta_and_done():
    def boom_source():
        yield "data: meta\n\n"
        raise RuntimeError("kaboom")

    out = list(_sse_keepalive(boom_source(), interval=5.0))
    assert out[0] == "data: meta\n\n"
    # a degraded delta then a done — never a bare drop with no delta
    delta = json.loads(out[1][5:].strip())
    done = json.loads(out[2][5:].strip())
    assert delta["type"] == "delta" and delta["text"]
    assert done["type"] == "done" and done["degraded"] is True
