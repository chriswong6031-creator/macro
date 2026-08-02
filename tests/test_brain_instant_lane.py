"""Tests for the W5 instant-fact lane + turn latency instrumentation.

All offline: no provider client is real, no quote leaves the process, and the router
half is pure. Coverage:

  1. Router precision grid — the accept set is small and the reject set is where the
     value is. A FALSE POSITIVE is the failure mode this lane can actually hurt
     someone with (an analytical question answered with a one-line price), so every
     ambiguous case in the grid must come back None.
  2. Fall-through: an unresolvable quote, a dateless quote, a provider exception and a
     leaked sentinel all hand the turn to the normal loop with NOTHING user-visible
     having happened. The tests monkeypatch the loop and assert it ran.
  3. The `done` event's route + usage.latency shape on the instant lane.
  4. The same latency record on the deep lane (rounds populated, total_ms set,
     ttfv_ms stamped at the first delta).
  5. Quota debits on an instant turn exactly as on any other turn.
  6. The bench script's SSE parser, against a canned stream (no network).
"""
from __future__ import annotations

import json
import pathlib
import sys
import tempfile
from typing import Any
from unittest.mock import patch

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from engine.neuralweb import brain_gateway as gw  # noqa: E402
from scripts import brain_latency_bench as bench  # noqa: E402


# ---------------------------------------------------------------------------
# Offline doubles
# ---------------------------------------------------------------------------

class _Blk:
    def __init__(self, type_: str, text: str = "", name: str = "",
                 input_: dict | None = None, id_: str = "t1"):
        self.type = type_
        self.text = text
        self.name = name
        self.input = input_ or {}
        self.id = id_


class _Usage:
    def __init__(self, input_tokens: int = 12, output_tokens: int = 34):
        self.input_tokens = input_tokens
        self.output_tokens = output_tokens


class _Resp:
    def __init__(self, content: list, stop_reason: str = "end_turn", usage: Any = None):
        self.content = content
        self.stop_reason = stop_reason
        self.usage = usage or _Usage()


class _StreamCtx:
    def __init__(self, text: str, chunks: int = 2):
        self._text = text
        self._chunks = chunks

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    @property
    def text_stream(self):
        size = max(1, len(self._text) // self._chunks + 1)
        for i in range(0, len(self._text), size):
            yield self._text[i:i + size]

    def get_final_message(self):
        return _Resp([_Blk("text", self._text)], "end_turn")


class _Client:
    """Scripted create() + a canned stream(), capturing every call's kwargs."""

    def __init__(self, answer: str = "AAPL is at 214.30 as of 2026-08-01T19:55:00Z.",
                 responses: list | None = None,
                 create_exc: Exception | None = None,
                 stream_exc: Exception | None = None):
        self._answer = answer
        self._responses = list(responses or [])
        self._i = 0
        self._create_exc = create_exc
        self._stream_exc = stream_exc
        self.create_kwargs: list[dict] = []
        self.stream_kwargs: list[dict] = []
        self.messages = self

    def create(self, **kwargs):
        self.create_kwargs.append(kwargs)
        if self._create_exc is not None:
            raise self._create_exc
        if self._i < len(self._responses):
            resp = self._responses[self._i]
            self._i += 1
            return resp
        return _Resp([_Blk("text", self._answer)], "end_turn")

    def stream(self, **kwargs):
        self.stream_kwargs.append(kwargs)
        if self._stream_exc is not None:
            raise self._stream_exc
        return _StreamCtx(self._answer)


_GOOD_QUOTE = {"symbol": "AAPL", "price": 214.30, "as_of": "2026-08-01T19:55:00Z",
               "source": "terminal_hub"}


def _root() -> pathlib.Path:
    d = pathlib.Path(tempfile.mkdtemp())
    (d / "data" / "neuralweb").mkdir(parents=True, exist_ok=True)
    return d


def _sse(events: list[str]) -> list[dict]:
    return [json.loads(e[6:]) for e in events if e.startswith("data: ")]


@pytest.fixture(autouse=True)
def _no_real_ledger(tmp_path, monkeypatch):
    """Never let a probe row reach the repo's append-only ai_costs ledger."""
    monkeypatch.setattr("lib.ai_costs._write_ledger_path",
                        lambda root=None: tmp_path / "ai_costs" / "usage.jsonl")


@pytest.fixture(autouse=True)
def _no_tape_read(monkeypatch):
    """The tape line is a market-packet read; pin it so tests touch no artifacts."""
    monkeypatch.setattr(gw, "_instant_tape_line", lambda root: "")


# ---------------------------------------------------------------------------
# 1. Router precision grid
# ---------------------------------------------------------------------------

_ROUTER_ACCEPT: list[tuple[str, dict | None, str]] = [
    ("what's AAPL trading at?",              None,               "AAPL"),
    ("whats AAPL trading at",                None,               "AAPL"),
    ("What is AAPL trading at now",          None,               "AAPL"),
    ("AAPL price",                           None,               "AAPL"),
    ("aapl price",                           None,               "AAPL"),
    ("what is the price of aapl",            None,               "AAPL"),
    ("what's the current price of TSLA",     None,               "TSLA"),
    ("quote MSFT",                           None,               "MSFT"),
    ("price of 0700.HK",                     None,               "0700.HK"),
    ("SSE:600036 price",                     None,               "600036.SS"),
    ("how much is NVDA",                     None,               "NVDA"),
    ("where is TSLA trading right now",      None,               "TSLA"),
    ("AAPL quote today",                     None,               "AAPL"),
    # symbol from the page/chart context chip
    ("what's the price",                     {"symbol": "NVDA"}, "NVDA"),
    ("price",                                {"symbol": "SPY"},  "SPY"),
    ("how much is it",                       {"symbol": "TSLA"}, "TSLA"),
    ("where is it trading",                  {"symbol": "QQQ"},  "QQQ"),
    # zh
    ("AAPL 现价多少",                          None,               "AAPL"),
    ("AAPL现价",                              None,               "AAPL"),
    ("AAPL 价格是多少？",                       None,               "AAPL"),
    ("AAPL 现在多少钱",                         None,               "AAPL"),
    ("600036 报价",                           None,               "600036.SS"),
    ("现价",                                  {"symbol": "AAPL"}, "AAPL"),
    ("股价多少",                               {"symbol": "NVDA"}, "NVDA"),
]

_ROUTER_REJECT: list[tuple[str, dict | None]] = [
    # analytical qualifiers — the whole reason this router is allowed to exist
    ("why is AAPL down",                        None),
    ("should I buy AAPL",                       None),
    ("what do you think of AAPL price",         None),
    ("AAPL price target",                       None),
    ("is AAPL a buy at this price",             None),
    ("what's the outlook for AAPL",             None),
    ("AAPL price vs MSFT price",                None),
    ("compare AAPL and MSFT price",             None),
    ("AAPL price last week",                    None),
    ("what will AAPL be trading at next week",  None),
    ("AAPL 现价怎么看",                          None),
    ("AAPL 报价和走势",                          None),
    ("AAPL 目标价格",                            None),
    # a qualifier sitting INSIDE an otherwise-matching pattern: only the reject screen
    # stands between these and a "quote for the ticker TARGET / BUY / EXIT".
    ("target price",                            None),
    ("buy price",                               None),
    ("entry price",                             None),
    ("exit price",                              None),
    ("what's the sell price",                   None),
    ("risk price",                              {"symbol": "AAPL"}),
    # more than one symbol named. The zh pair is the one that ONLY the multi-symbol
    # veto catches: the zh path matches on residue, not on an anchored slot, so
    # without the veto it would silently answer about the FIRST ticker.
    ("AAPL MSFT price",                         None),
    ("what is AAPL and MSFT trading at",        None),
    ("price of 0700.HK and 9988.HK",            None),
    ("AAPL MSFT 现价",                           None),
    ("600036 000001 报价",                       None),
    # the symbol slot is not a ticker
    ("gold price",                              None),
    ("oil price",                               None),
    ("what is the market price",                None),
    ("how much is bitcoin",                     None),
    ("what is 500 trading at",                  None),
    ("what is 0700 trading at",                 None),
    # nothing resolves: no ticker in the turn and no context chip
    ("what's the price",                        None),
    ("how much is it",                          None),
    ("price",                                   {}),
    ("现价",                                     None),
    ("现价",                                     {"symbol": ""}),
    # not a price ask at all
    ("hello",                                   None),
    ("",                                        None),
    ("   ",                                     None),
    ("what is the yield on the 10y",            None),
    ("AAPL price in 2024",                      None),
    ("give me the AAPL price and volume",       None),
    ("what is aapl trading at compared to msft", None),
    ("read me the AAPL chart",                  None),
]


@pytest.mark.parametrize("message,context,symbol", _ROUTER_ACCEPT)
def test_router_accepts_pure_quote_asks(message, context, symbol):
    route = gw._instant_route(message, context)
    assert route is not None, f"router should have matched {message!r}"
    assert route == {"kind": "quote", "symbol": symbol}


@pytest.mark.parametrize("message,context", _ROUTER_REJECT)
def test_router_rejects_everything_ambiguous(message, context):
    """Every ambiguous case returns None — a false negative is slow, a false positive
    answers an analytical question with a price."""
    assert gw._instant_route(message, context) is None, \
        f"router must NOT have matched {message!r}"


def test_router_prefers_the_symbol_the_user_typed_over_the_context_chip():
    """Context precedence: the entity named in the request beats the pinned chip
    (teardown docket §6.4). A stale chart chip must never rename the answer."""
    assert gw._instant_route("AAPL price", {"symbol": "MSFT"}) == {
        "kind": "quote", "symbol": "AAPL"}


@pytest.mark.parametrize("text", [
    "why", "should", "vs", "versus", "compare", "outlook", "forecast", "target",
    "buy", "sell", "next", "earnings", "last week", "and",
    "怎么看", "为什么", "该不该", "对比", "预测", "目标",
])
def test_reject_screen_catches_every_qualifier_family(text):
    """The screen is a second, independent layer under the anchored patterns — pinned
    directly so it cannot rot into a no-op behind them."""
    assert gw._instant_reject(f"AAPL {text} price") is True


@pytest.mark.parametrize("text", [
    "AAPL price", "what's AAPL trading at", "quote MSFT", "how much is NVDA",
    "AAPL 现价多少", "600036 报价", "where is TSLA trading now",
])
def test_reject_screen_passes_a_clean_lookup(text):
    """The inverse half: the screen must not swallow the shapes the lane exists for."""
    assert gw._instant_reject(text) is False


def test_router_is_pure_and_never_raises_on_junk():
    for junk in (None, "", "?" * 300, "\x00\x01", "价" * 40, "AAPL " * 40):
        assert gw._instant_route(junk, {"symbol": None}) is None, junk
    # A malformed context is data, not a crash site.
    for ctx in (None, {}, {"symbol": None}, {"symbol": 12345}, {"symbol": "../../etc"}):
        gw._instant_route("hello there", ctx)


# ---------------------------------------------------------------------------
# 2. Instant serve — happy path
# ---------------------------------------------------------------------------

def _chat(root, tmp_path, client, message="AAPL price", **kw):
    providers = [{"client": client, "model": "deepseek-v4-flash"}]
    with patch.object(gw, "_brain_quota_dir", return_value=tmp_path):
        with patch.object(gw, "_build_lane_providers", return_value=providers):
            with patch.object(gw, "_resolve_tier", return_value={
                    "tier": "pro", "status": "active", "current_period_end": None}):
                with patch.object(gw, "_ensure_thread", return_value=None):
                    with patch("lib.ai_costs.record_usage", return_value=True):
                        return gw.chat(message, kw.pop("user_id", "u_instant"),
                                       lane="fast", root=root, **kw)


def _stream(root, tmp_path, client, message="AAPL price", **kw):
    providers = [{"client": client, "model": "deepseek-v4-flash"}]
    with patch.object(gw, "_brain_quota_dir", return_value=tmp_path):
        with patch.object(gw, "_build_lane_providers", return_value=providers):
            with patch.object(gw, "_resolve_tier", return_value={
                    "tier": "pro", "status": "active", "current_period_end": None}):
                with patch.object(gw, "_ensure_thread", return_value=None):
                    with patch("lib.ai_costs.record_usage", return_value=True):
                        return list(gw.chat_stream(
                            message, kw.pop("user_id", "u_instant_s"),
                            lane="fast", root=root, **kw))


def test_instant_chat_returns_route_instant_and_a_latency_record(tmp_path):
    client = _Client()
    with patch.object(gw, "_tool_get_quote", return_value=dict(_GOOD_QUOTE)):
        result = _chat(_root(), tmp_path, client)

    assert result["route"] == "instant"
    assert result["reply"].startswith("AAPL is at 214.30")
    assert result["citations"] == []
    assert result["symbol"] == "AAPL"
    latency = result["latency"]
    assert latency["route"] == "instant"
    assert latency["ttfv_ms"] is None          # non-streaming: no wire to be first on
    assert isinstance(latency["total_ms"], int)
    assert [t["name"] for t in latency["rounds"][0]["tools"]] == ["get_quote"]
    # ONE model call, and it carried NO tool schemas and no doctrine stack.
    assert len(client.create_kwargs) == 1
    call = client.create_kwargs[0]
    assert "tools" not in call
    system = call["system"]
    assert isinstance(system, str)             # not the cached block list of the deep loop
    assert "single factual price lookup" in system
    for sentinel in gw._LEAK_SENTINELS:
        assert sentinel not in system
    # The quote rides as DATA, and the model is told not to invent numbers.
    user_text = call["messages"][0]["content"]
    assert "214.3" in user_text and "2026-08-01T19:55:00Z" in user_text
    assert "never invent" in system.lower()


def test_instant_stream_emits_meta_delta_done_with_route_and_latency(tmp_path):
    client = _Client()
    with patch.object(gw, "_tool_get_quote", return_value=dict(_GOOD_QUOTE)):
        events = _sse(_stream(_root(), tmp_path, client))

    assert [e["type"] for e in events] == ["meta", "delta", "done"]
    assert events[0]["lane"] == "fast"
    assert events[1]["text"].startswith("AAPL is at 214.30")
    done = events[2]
    assert done["route"] == "instant"
    assert done["citations"] == []
    assert done["degraded"] is False
    latency = done["usage"]["latency"]
    assert set(latency) == {"route", "ttfv_ms", "rounds", "synthesis_ms", "total_ms"}
    assert latency["route"] == "instant"
    assert isinstance(latency["ttfv_ms"], int)
    assert isinstance(latency["total_ms"], int)
    assert latency["synthesis_ms"] is None
    assert latency["rounds"] and isinstance(latency["rounds"][0]["model_ms"], int)
    assert latency["rounds"][0]["tools"][0]["name"] == "get_quote"
    # The lane's STREAMING client served it, and with no tool schemas attached.
    assert len(client.stream_kwargs) == 1
    assert "tools" not in client.stream_kwargs[0]


def test_instant_turn_debits_quota_exactly_like_any_other_turn(tmp_path):
    """The router sits AFTER the quota increment, so two instant turns burn two
    messages. A fast lane that did not meter would be a free tier by accident."""
    client = _Client()
    root = _root()
    with patch.object(gw, "_tool_get_quote", return_value=dict(_GOOD_QUOTE)):
        first = _chat(root, tmp_path, client, user_id="u_quota")
        second = _chat(root, tmp_path, client, user_id="u_quota")
    assert first["route"] == second["route"] == "instant"
    assert second["quota"]["remaining"] == first["quota"]["remaining"] - 1


# ---------------------------------------------------------------------------
# 3. Fall-through — instant is an optimization, never a new failure mode
# ---------------------------------------------------------------------------

_DEEP_REPLY = "Deep loop answer."


def _deep_loop_spy(calls: list):
    def _loop(message, lane, history, context, root_, tdd, thu, client, model, max_t, tb,
              mode="chat", image_blocks=None, providers=None, user_id="", user_email="",
              effort=None, thinking_mode=None, deepseek_thinking=None):
        calls.append(message)
        return _DEEP_REPLY, [], [], [], {}, [], []
    return _loop


def _deep_stream_spy(calls: list):
    def _loop(message, lane, history, context, root_, tdd, thu, client, model, max_t, tb,
              meta_event, usage_out=None, answer_out=None, thinking_out=None,
              mode="chat", image_blocks=None, providers=None, user_id="", user_email="",
              effort=None, thinking_mode=None, deepseek_thinking=None):
        calls.append(message)
        yield f"data: {json.dumps(meta_event)}\n\n"
        yield f"data: {json.dumps({'type': 'delta', 'text': _DEEP_REPLY})}\n\n"
        yield f"data: {json.dumps({'type': 'done', 'citations': [], 'usage': {}})}\n\n"
        if usage_out is not None:
            usage_out.append({})
        if answer_out is not None:
            answer_out.append(_DEEP_REPLY)
    return _loop


@pytest.mark.parametrize("quote", [
    {"symbol": "AAPL", "available": False, "note": "quote not available from any source"},
    {"error": "symbol required"},
    {"symbol": "AAPL", "price": None, "as_of": "2026-08-01T19:55:00Z"},
    # a price with NO as-of: house law is that every displayed number carries its
    # as-of, and this lane's whole contract is stating the timestamp.
    {"symbol": "AAPL", "price": 214.30},
])
def test_instant_falls_through_when_the_quote_is_unusable(tmp_path, quote):
    calls: list = []
    client = _Client()
    with patch.object(gw, "_tool_get_quote", return_value=quote):
        with patch.object(gw, "_run_brain_loop", side_effect=_deep_loop_spy(calls)):
            result = _chat(_root(), tmp_path, client)
    assert calls == ["AAPL price"], "the normal loop must own the turn"
    assert result["reply"] == _DEEP_REPLY
    assert result["route"] == "deep"
    assert client.create_kwargs == [], "no instant model call may have been made"


def test_instant_falls_through_when_the_quote_lookup_raises(tmp_path):
    calls: list = []
    with patch.object(gw, "_tool_get_quote", side_effect=RuntimeError("hub down")):
        with patch.object(gw, "_run_brain_loop", side_effect=_deep_loop_spy(calls)):
            result = _chat(_root(), tmp_path, _Client())
    assert calls and result["reply"] == _DEEP_REPLY


def test_instant_falls_through_on_a_model_exception(tmp_path):
    """A provider error on the instant call is invisible: the deep loop answers."""
    calls: list = []
    client = _Client(create_exc=RuntimeError("provider exploded"))
    with patch.object(gw, "_tool_get_quote", return_value=dict(_GOOD_QUOTE)):
        with patch.object(gw, "_run_brain_loop", side_effect=_deep_loop_spy(calls)):
            result = _chat(_root(), tmp_path, client)
    assert calls == ["AAPL price"]
    assert result["reply"] == _DEEP_REPLY
    assert result["route"] == "deep"
    assert result["degraded"] is False


def test_instant_falls_through_on_an_empty_model_answer(tmp_path):
    calls: list = []
    with patch.object(gw, "_tool_get_quote", return_value=dict(_GOOD_QUOTE)):
        with patch.object(gw, "_run_brain_loop", side_effect=_deep_loop_spy(calls)):
            result = _chat(_root(), tmp_path, _Client(answer="   "))
    assert calls and result["reply"] == _DEEP_REPLY


def test_instant_stream_falls_through_on_a_stream_error_with_no_bytes_sent(tmp_path):
    """The instant answer is resolved BEFORE the first byte goes out, so a failure
    leaves the wire untouched — the client sees an ordinary deep-lane turn."""
    calls: list = []
    client = _Client(stream_exc=RuntimeError("stream open failed"))
    with patch.object(gw, "_tool_get_quote", return_value=dict(_GOOD_QUOTE)):
        with patch.object(gw, "_run_brain_loop_stream", side_effect=_deep_stream_spy(calls)):
            events = _sse(_stream(_root(), tmp_path, client))
    assert calls == ["AAPL price"]
    assert [e["type"] for e in events] == ["meta", "delta", "done"]
    assert events[1]["text"] == _DEEP_REPLY
    assert "route" not in events[2] or events[2].get("route") != "instant"


def test_instant_never_fires_for_an_image_turn(tmp_path):
    """An attachment is never a price lookup — the deep loop owns vision turns."""
    calls: list = []
    with patch.object(gw, "_tool_get_quote", return_value=dict(_GOOD_QUOTE)):
        with patch.object(gw, "_run_brain_loop", side_effect=_deep_loop_spy(calls)):
            result = _chat(_root(), tmp_path, _Client(),
                           images=["data:image/png;base64,aGk="])
    assert calls == ["AAPL price"]
    assert result["route"] == "deep"


# ---------------------------------------------------------------------------
# 4. Leak screen on instant answers
# ---------------------------------------------------------------------------

def test_instant_answer_is_leak_screened(tmp_path):
    """The instant prompt carries no doctrine, so a sentinel cannot come from an echo —
    but the screen runs anyway, and a tripped screen is not an instant answer: the
    turn falls through instead of shipping a refusal from the fast lane."""
    leaky = "SCOPE — THIS PRODUCT ONLY. AAPL is at 214.30."
    calls: list = []
    with patch.object(gw, "_tool_get_quote", return_value=dict(_GOOD_QUOTE)):
        with patch.object(gw, "_run_brain_loop", side_effect=_deep_loop_spy(calls)):
            result = _chat(_root(), tmp_path, _Client(answer=leaky))
    assert calls, "a leaked answer must hand the turn to the normal loop"
    assert "SCOPE — THIS PRODUCT ONLY" not in result["reply"]
    assert result["reply"] == _DEEP_REPLY


def test_instant_answer_drops_a_stray_next_block(tmp_path):
    answer = "AAPL is at 214.30 as of 2026-08-01T19:55:00Z.\n\n[NEXT]\n1. What now?"
    with patch.object(gw, "_tool_get_quote", return_value=dict(_GOOD_QUOTE)):
        result = _chat(_root(), tmp_path, _Client(answer=answer))
    assert result["route"] == "instant"
    assert "[NEXT]" not in result["reply"]
    assert "suggestions" not in result


# ---------------------------------------------------------------------------
# 5. Deep-lane latency record
# ---------------------------------------------------------------------------

def test_deep_loop_timing_records_every_round_and_the_total(tmp_path):
    """Two Phase-1 rounds (one tool call, then an answer) → two round records with the
    tool named and timed, and a total_ms for the turn."""
    client = _Client(responses=[
        _Resp([_Blk("tool_use", name="get_quote", input_={"symbol": "AAPL"}, id_="t1")],
              "tool_use"),
        _Resp([_Blk("text", "Answer.")], "end_turn"),
    ])
    providers = [{"client": client, "model": "deepseek-v4-flash"}]
    root = _root()
    with patch.object(gw, "_brain_quota_dir", return_value=tmp_path):
        with patch.object(gw, "_build_lane_providers", return_value=providers):
            with patch.object(gw, "_resolve_tier", return_value={
                    "tier": "pro", "status": "active", "current_period_end": None}):
                with patch.object(gw, "_ensure_thread", return_value=None):
                    with patch.object(gw, "_dispatch_brain_tool",
                                      return_value={"symbol": "AAPL", "price": 1.0}):
                        with patch("lib.ai_costs.record_usage", return_value=True):
                            result = gw.chat("what is going on with breadth today",
                                             "u_deep", lane="fast", root=root)

    assert result["route"] == "deep"
    latency = result["latency"]
    assert latency["route"] == "deep"
    assert isinstance(latency["total_ms"], int)
    assert len(latency["rounds"]) == 2, latency["rounds"]
    assert [t["name"] for t in latency["rounds"][0]["tools"]] == ["get_quote"]
    assert all(isinstance(r["model_ms"], int) for r in latency["rounds"])
    assert latency["rounds"][1]["tools"] == []


def test_deep_stream_done_carries_route_deep_and_a_stamped_ttfv(tmp_path):
    client = _Client(responses=[_Resp([_Blk("text", "Answer.")], "end_turn")])
    providers = [{"client": client, "model": "deepseek-v4-flash"}]
    root = _root()
    with patch.object(gw, "_brain_quota_dir", return_value=tmp_path):
        with patch.object(gw, "_build_lane_providers", return_value=providers):
            with patch.object(gw, "_resolve_tier", return_value={
                    "tier": "pro", "status": "active", "current_period_end": None}):
                with patch.object(gw, "_ensure_thread", return_value=None):
                    with patch("lib.ai_costs.record_usage", return_value=True):
                        events = _sse(list(gw.chat_stream(
                            "what is going on with breadth today", "u_deep_s",
                            lane="fast", root=root)))

    done = [e for e in events if e["type"] == "done"][0]
    assert done["route"] == "deep"
    latency = done["usage"]["latency"]
    assert latency["route"] == "deep"
    assert isinstance(latency["ttfv_ms"], int), "ttfv must be stamped at the first delta"
    assert isinstance(latency["total_ms"], int)
    assert latency["ttfv_ms"] <= latency["total_ms"]
    assert len(latency["rounds"]) == 1


def test_ttfv_stamp_lands_on_the_first_delta_only():
    """The stamp is a once-only guard, so splitting the answer into many deltas keeps
    a correct time-to-first-byte. This pins the guard itself, not today's emit count."""
    timing = gw._new_turn_timing("deep")
    t0 = 0.0
    with patch.object(gw, "_ms_since", side_effect=[11, 22, 33]):
        gw._timing_stamp_once(timing, "ttfv_ms", t0)
        gw._timing_stamp_once(timing, "ttfv_ms", t0)
        gw._timing_stamp_once(timing, "ttfv_ms", t0)
    assert timing["ttfv_ms"] == 11


def test_new_turn_timing_shape():
    timing = gw._new_turn_timing("instant")
    assert timing == {"route": "instant", "ttfv_ms": None, "rounds": [],
                      "synthesis_ms": None, "total_ms": None}


# ---------------------------------------------------------------------------
# 6. Bench script — SSE parser (no network)
# ---------------------------------------------------------------------------

_CANNED_STREAM = [
    'data: {"type": "run", "run_id": "r1", "cursor": 0}\n',
    "\n",
    ': keepalive\n',
    'data: {"type": "meta", "lane": "fast", "model": "deepseek-v4-flash"}\n',
    "\n",
    'data: {"type": "status", "phase": "start"}\n',
    "\n",
    'data: {"type": "tool", "name": "get_quote"}\n',
    "\n",
    ': keepalive\n',
    'data: {"type": "delta", "text": "Hello "}\n',
    "\n",
    'data: {"type": "delta",\n',
    'data:  "text": "world."}\n',
    "\n",
    'data: {"type": "done", "route": "deep", "usage": {"input_tokens": 5, '
    '"latency": {"route": "deep", "ttfv_ms": 900, "total_ms": 1200}}}\n',
    "\n",
]


def _fake_clock():
    ticks = iter([0.1 * i for i in range(1, 200)])
    return lambda: next(ticks)


def test_bench_parser_reads_events_and_ignores_keepalive_comments():
    events = bench.read_events(_CANNED_STREAM, clock=_fake_clock())
    assert [e["type"] for e, _ in events] == [
        "run", "meta", "status", "tool", "delta", "delta", "done"]
    # the multi-line data event reassembled correctly
    assert events[5][0]["text"] == "world."


def test_bench_parser_survives_junk_and_an_unterminated_tail():
    lines = ["data: not json\n", "\n", "event: ping\n", "\n",
             'data: {"type": "done"}\n']          # no trailing blank line
    events = bench.read_events(lines, clock=_fake_clock())
    assert [e["type"] for e, _ in events] == ["done"]


def test_bench_summarize_reports_the_row_the_table_prints():
    events = bench.read_events(_CANNED_STREAM, clock=_fake_clock())
    row = bench.summarize(events, t0=0.0, headers_ms=42)
    assert row["headers_ms"] == 42
    assert row["n_deltas"] == 2
    assert row["n_tool_events"] == 1
    assert row["answer_chars"] == len("Hello world.")
    assert row["route"] == "deep"
    assert row["server_latency"]["ttfv_ms"] == 900
    assert row["first_status_ms"] is not None
    assert row["ttfv_ms"] is not None
    assert row["done_ms"] is not None
    assert row["first_status_ms"] <= row["ttfv_ms"] <= row["done_ms"]


def test_bench_summarize_degrades_on_a_pre_w5_server():
    """No route, no usage.latency — every timing still lands, the new columns print '-'."""
    lines = ['data: {"type": "meta"}\n', "\n",
             'data: {"type": "delta", "text": "hi"}\n', "\n",
             'data: {"type": "done", "citations": [], "usage": {}}\n', "\n"]
    row = bench.summarize(bench.read_events(lines, clock=_fake_clock()),
                          t0=0.0, headers_ms=10)
    assert row["route"] is None and row["server_latency"] is None
    assert bench._cell(row["route"]) == "-"
    assert row["n_deltas"] == 1 and row["done_ms"] is not None


def test_bench_probe_reports_a_clean_connection_error_without_a_server():
    row = bench.probe("http://127.0.0.1:1", "hi", cookie="x", timeout=2.0)
    assert "cannot reach" in row["error"]
    assert row.get("done_ms") is None


def test_bench_docket_prompts_are_the_three_classes_plus_the_instant_probe():
    labels = [n for n, _ in bench.DOCKET_PROMPTS]
    assert labels == ["broad", "native", "simple", "instant"]
    # The docket's own "simple current fact" ask carries extra instructions, so it is
    # NOT an instant-lane shape — the fourth probe is. Pin both facts.
    prompts = dict(bench.DOCKET_PROMPTS)
    assert gw._instant_route(prompts["simple"], None) is None
    assert gw._instant_route(prompts["instant"], None) == {"kind": "quote", "symbol": "AAPL"}
    assert gw._instant_route(prompts["broad"], None) is None
    assert gw._instant_route(prompts["native"], None) is None


# ---------------------------------------------------------------------------
# W5.1 — the site_quotes reader carries the plane's timestamp through
# ---------------------------------------------------------------------------
# Live finding (2026-08-02, W5 verification): quotes.json writes per-row `ts`
# (epoch ms) and file-level `asof`, but the reader asked for `as_of` — a key the
# file never carries — so EVERY quote from this source shipped dateless and the
# instant lane's dateless-refuse gate correctly rejected all of them.

def _quotes_root(tmp_path, rows, top=None):
    live = tmp_path / "site" / "live"
    live.mkdir(parents=True)
    payload = {"quotes": rows}
    payload.update(top or {})
    (live / "quotes.json").write_text(json.dumps(payload), encoding="utf-8")
    return tmp_path


def test_site_quotes_reader_converts_row_ts_to_an_iso_as_of(tmp_path):
    root = _quotes_root(tmp_path, {"SPY": {
        "price": 739.09, "ts": 1785182400000, "prevClose": 738.93, "changePct": 0.02}})
    q = gw._tool_get_quote({"symbol": "SPY"}, tmp_path / "absent", "", root)
    assert q["source"] == "site_quotes" and q["price"] == 739.09
    # 1785182400000 ms = 2026-07-27T20:00:00Z — the 16:00 ET close, as the plane wrote it.
    assert q["as_of"] == "2026-07-27T20:00:00+00:00"
    assert q["change_pct"] == 0.02 and q["prev_close"] == 738.93
    # ...and the instant gate now accepts what the plane always knew the date of.
    with patch.object(gw, "_tool_get_quote", return_value=q):
        assert gw._instant_quote("SPY", tmp_path / "absent", "", root) is not None


def test_site_quotes_reader_falls_back_to_file_level_asof(tmp_path):
    root = _quotes_root(tmp_path, {"SPY": {"price": 739.09}},
                        top={"asof": "2026-07-28T04:00:05Z"})
    q = gw._tool_get_quote({"symbol": "SPY"}, tmp_path / "absent", "", root)
    assert q["as_of"] == "2026-07-28T04:00:05Z"


def test_site_quotes_reader_still_returns_dateless_when_no_timestamp_exists(tmp_path):
    root = _quotes_root(tmp_path, {"SPY": {"price": 739.09}})
    q = gw._tool_get_quote({"symbol": "SPY"}, tmp_path / "absent", "", root)
    assert q.get("as_of") is None, "no timestamp may be invented"
