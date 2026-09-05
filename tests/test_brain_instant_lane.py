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
from datetime import datetime, timezone
from typing import Any
from unittest.mock import patch

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from engine.intelligence_workspace import context_compiler as cc  # noqa: E402
from engine.neuralweb import brain_gateway as gw  # noqa: E402
from engine.neuralweb import native_facts as nf  # noqa: E402
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
    with patch.object(gw._native_facts, "plan_native_facts", return_value=None):
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
    with patch.object(gw._native_facts, "plan_native_facts", return_value=None):
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

    # W1-C: context_receipt is now a first-class event, always right after meta.
    assert [e["type"] for e in events] == ["meta", "context_receipt", "delta", "done"]
    assert events[0]["lane"] == "fast"
    assert events[1]["schema"] == "ai_context_receipt.v1"
    assert events[2]["text"].startswith("AAPL is at 214.30")
    done = events[3]
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
              effort=None, thinking_mode=None, deepseek_thinking=None, context_receipt=None):
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


def test_w0b_legacy_specs_keep_labels_text_hashes_and_ambient_metadata():
    specs = bench._legacy_prompt_specs(page="terminal", symbol="AAOI")
    assert [s["label"] for s in specs] == ["broad", "native", "simple", "instant"]
    assert [s["prompt_id"] for s in specs] == [
        "legacy.broad.v1", "legacy.native.v1", "legacy.simple.v1", "legacy.instant.v1",
    ]
    assert all(len(s["prompt_text_hash"]) == 64 for s in specs)
    assert all(s["ambient_context"] == {"page": "terminal", "symbol": "AAOI"}
               for s in specs)
    assert specs[1]["prompt_class"] == "native-multi-field"


_W0B_LEGACY_PROMPT_TEXT = {
    "legacy.broad.v1": (
        "Give me situational awareness of the market right now: the regime, which themes "
        "are working, breadth, rates and liquidity, the catalysts ahead and the main "
        "risks. Cite your sources and timestamp every read."
    ),
    "legacy.native.v1": (
        "For AAPL give me relative strength over 1 month, 3 months and 12 months, its "
        "industry rank, its Stage, the next earnings date and the latest reported EPS "
        "growth. Give the as-of for each field and cite the source."
    ),
    "legacy.simple.v1": "What is AAPL's current price? One sentence, with the source and the exact as-of.",
    "legacy.instant.v1": "What's AAPL trading at?",
}

_W0B_PRIVATE_FIXTURE_TEXT = {
    "w0b.context-collision.v1": "What is INOD trading at?",
    "w0b.screener-compilation.v1": "List the current Stage 2 leaders in semiconductors.",
    "w0b.calculation.v1": "Calculate the percentage change from 100 to 125.",
    "w0b.filing-event.v1": "Summarize the latest AAPL earnings filing event.",
    "w0b.deep-synthesis.v1": "Explain the investment implications of the current market regime.",
}


def _complete_w0b_manifest() -> dict:
    """A text-bearing external corpus fixture, in the frozen public ID order."""
    prompts = []
    for prompt_id, prompt_class in bench.W0B_CORPUS_V1:
        prompt_text = (_W0B_LEGACY_PROMPT_TEXT[prompt_id]
                       if prompt_id in _W0B_LEGACY_PROMPT_TEXT
                       else _W0B_PRIVATE_FIXTURE_TEXT[prompt_id])
        collision = prompt_id == "w0b.context-collision.v1"
        prompts.append({
            "prompt_id": prompt_id,
            "prompt_class": prompt_class,
            "prompt_text": prompt_text,
            "prompt_text_hash": bench._sha256_text(prompt_text),
            "explicit_context": {"entity": "INOD"} if collision else {},
            "ambient_context": {"symbol": "AAOI"} if collision else {},
            "expected_effective_entity": "INOD" if collision else None,
            "expected_precedence_reason": "explicit_entity_wins" if collision else None,
        })
    return {
        "schema": bench.W0B_MANIFEST_SCHEMA,
        "version": bench.W0B_CORPUS_VERSION,
        "prompts": prompts,
    }


def _write_w0b_manifest(tmp_path, manifest=None):
    path = tmp_path / "private-w0b-manifest.json"
    path.write_text(json.dumps(manifest or _complete_w0b_manifest()), encoding="utf-8")
    return path


def _strict_w0b_receipt(spec: dict, *, run: int = 1) -> dict:
    """Create a closed, unscored receipt through the production builder."""
    row = {
        "probe": spec["prompt_id"],
        "label": "warm",
        "base_url": "https://benchmark.example.test",
        "ts": "2026-08-24T12:00:00Z",
        "route": "deep",
        "headers_ms": 1,
        "first_status_ms": 2,
        "ttfv_ms": 3,
        "done_ms": 4,
        "n_deltas": 1,
        "n_tool_events": 0,
        "server_latency": {"route": "deep", "ttfv_ms": 3, "total_ms": 4, "rounds": []},
        "answer_chars": 12,
        "output_bytes": 12,
        "degraded": False,
        "error": None,
    }
    return bench.build_receipt_row(
        row, spec, run=run, lane="fast", system="mastermind",
        environment="production", cache_label="warm",
        cache_basis="natural_running_service",
        health={"commit": "a" * 12, "checkout": "b" * 12, "error": None},
        reviewer="fixture-reviewer", rubric_version=bench.W0B_RUBRIC_VERSION,
    )


def _complete_w0b_receipts(tmp_path) -> list[dict]:
    _version, _manifest_digest, specs = bench.load_private_manifest(
        str(_write_w0b_manifest(tmp_path))
    )
    return [_strict_w0b_receipt(spec) for spec in specs]


def _complete_w0b_scorecard(receipts: list[dict]) -> dict:
    return {
        "schema": bench.AI_BENCHMARK_SCORECARD_SCHEMA,
        "rubric_version": bench.W0B_RUBRIC_VERSION,
        "manifest_digest": receipts[0]["manifest_digest"],
        "reviewer": "fixture-reviewer",
        "rubric": bench.W0B_FROZEN_RUBRIC,
        "scores": [{
            "prompt_id": receipt["prompt_id"],
            "run": receipt["run"],
            "field_correctness": 1,
            "numeric_correctness": 1,
            "source_span_correctness": 1,
            "source_as_of_correctness": 1,
            "unsupported_claim_count": 0,
            "missingness_honesty": 1,
        } for receipt in receipts],
    }


def test_w0b_private_manifest_binds_complete_ordered_corpus_and_collision(tmp_path):
    path = _write_w0b_manifest(tmp_path)
    version, manifest_digest, specs = bench.load_private_manifest(str(path))
    assert version == bench.W0B_CORPUS_VERSION
    assert len(manifest_digest) == 64
    assert all(spec["manifest_digest"] == manifest_digest for spec in specs)
    assert [(spec["prompt_id"], spec["prompt_class"]) for spec in specs] == list(bench.W0B_CORPUS_V1)
    assert [spec["message"] for spec in specs[:4]] == list(_W0B_LEGACY_PROMPT_TEXT.values())
    collision = specs[4]
    assert collision["explicit_context"] == {"entity": "INOD"}
    assert collision["ambient_context"] == {"symbol": "AAOI"}
    assert collision["expected_effective_entity"] == "INOD"
    assert collision["expected_precedence_reason"] == "explicit_entity_wins"


@pytest.mark.parametrize("mutation, error", [
    (lambda manifest: manifest["prompts"].pop(), "complete ordered"),
    (lambda manifest: manifest["prompts"][0].update({
        "prompt_text": "Legacy text drift", "prompt_text_hash": bench._sha256_text("Legacy text drift"),
    }), "legacy docket prompt text drift"),
    (lambda manifest: manifest["prompts"][4].update({"prompt_text_hash": "0" * 64}), "hash mismatch"),
    (lambda manifest: manifest["prompts"][4].update({"explicit_context": {}}),
     "context-collision requires"),
    (lambda manifest: manifest["prompts"][4].update({
        "ambient_context": {"symbol": "INOD"},
    }), "context-collision requires"),
    (lambda manifest: manifest["prompts"][4].update({
        "prompt_text": "What is the current price?",
        "prompt_text_hash": bench._sha256_text("What is the current price?"),
    }), "context-collision requires"),
])
def test_w0b_private_manifest_rejects_subset_legacy_drift_and_hash_drift(tmp_path, mutation, error):
    manifest = _complete_w0b_manifest()
    mutation(manifest)
    with pytest.raises(ValueError, match=error):
        bench.load_private_manifest(str(_write_w0b_manifest(tmp_path, manifest)))


def test_w0b_receipt_is_complete_text_free_and_uses_first_delta_for_ttfv():
    times = iter([1.0, 2.0, 3.0])
    lines = [
        'data: {"type":"status"}\n', "\n",
        'data: {"type":"delta","text":"visible"}\n', "\n",
        'data: {"type":"done","route":"deep","usage":{"latency":{"rounds":['
        '{"tools":[{"ms":17}]}]}}}\n', "\n",
    ]
    row = bench.summarize(bench.read_events(lines, clock=lambda: next(times)), 0.0, 9)
    spec = {
        "prompt_id": "w0b.context-collision.v1",
        "prompt_version": "w0b.v1",
        "prompt_class": "context-collision",
        "prompt_text_hash": "a" * 64,
        "manifest_digest": "b" * 64,
        "message": "fixture-only text that must not enter receipt",
        "explicit_context": {"entity": "INOD"},
        "ambient_context": {"symbol": "AAOI"},
        "expected_effective_entity": "INOD",
        "expected_precedence_reason": "explicit_entity_wins",
    }
    receipt = bench.build_receipt_row(
        row, spec, run=1, lane="fast", system="mastermind", environment="production",
        cache_label="cold", cache_basis="verified_restart", health={
            "commit": "a" * 12, "checkout": "b" * 12, "error": None,
        }, reviewer="reviewer-v1", rubric_version=bench.W0B_RUBRIC_VERSION,
    )
    assert bench.RECEIPT_REQUIRED_FIELDS <= set(receipt)
    assert receipt["ttfv_ms"] == 2000, "status is not visible answer content"
    assert receipt["first_status_ms"] == 1000
    assert receipt["output_bytes"] == len("visible".encode("utf-8"))
    assert receipt["server_tool_count"] == 1
    assert receipt["server_tool_durations_ms"] == [17]
    serialized = json.dumps(receipt)
    assert "fixture-only text" not in serialized
    assert "message" not in receipt


def test_w0b_health_capture_and_private_raw_answer_boundary(tmp_path, monkeypatch):
    class _HealthResponse:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def read(self):
            return b'{"commit":"aaaaaaaaaaaa","checkout":"bbbbbbbbbbbb"}'

    monkeypatch.setattr(bench.urllib.request, "urlopen", lambda *args, **kwargs: _HealthResponse())
    assert bench.capture_health("https://example.test/api/health") == {
        "commit": "a" * 12, "checkout": "b" * 12, "error": None,
    }
    with pytest.raises(ValueError, match="outside the repository"):
        bench._assert_private_output_path(
            str(pathlib.Path(bench.__file__).resolve().parent.parent / "site" / "raw.jsonl"))
    assert bench._assert_private_output_path(str(tmp_path / "raw.jsonl")) == (tmp_path / "raw.jsonl")


def test_w0b_context_and_base_url_receipts_strip_private_shapes():
    with pytest.raises(ValueError, match="credentials or account identifiers"):
        bench._safe_context_metadata({"access_token": "fixture-only"})
    with pytest.raises(ValueError, match="public ticker identity"):
        bench._safe_context_metadata({"symbol": "/Users/private/secret"})
    with pytest.raises(ValueError, match="not allowed"):
        bench._safe_context_metadata({"note": "Bearer supersecret"})
    assert bench._safe_context_metadata({
        "entity": "AAPL", "entities": ["AAPL", "MSFT"],
        "page": "terminal", "symbol": "AAOI",
    }) == {
        "entity": "AAPL", "entities": ["AAPL", "MSFT"],
        "page": "terminal", "symbol": "AAOI",
    }
    assert bench._safe_base_url("https://user:pass@example.test/path?token=fixture#frag") == \
        "https://example.test"


def test_w0b_native_timing_projection_preserves_route_and_measured_float_stages():
    timing = bench._safe_server_timing({
        "route": "instant/native-fact",
        "ttfv_ms": 411,
        "total_ms": 430,
        "route_decision_ms": 0.125,
        "context_assembly_ms": 188.75,
        "registry_context_assembly_ms": 188.75,
        "render_ms": 0.031,
        "rounds": [],
    })
    assert timing == {
        "route": "instant/native-fact",
        "ttfv_ms": 411,
        "synthesis_ms": None,
        "total_ms": 430,
        "rounds": [],
        "route_decision_ms": 0.125,
        "context_assembly_ms": 188.75,
        "registry_context_assembly_ms": 188.75,
        "resolver_ms": None,
        "render_ms": 0.031,
    }


def test_w0b_context_collision_compares_expected_entity_to_sanitized_actual_receipt():
    fingerprint = "a" * 64
    native_receipt = {
        "schema": "brain.native_fact_receipt.v1",
        "route": "instant/native-fact",
        "planner_version": "w1b.native_fact_planner.v1",
        "registry_digest": "d" * 64,
        "canonical_entity": {"type": "security", "id": "SEC:US-XNAS-AAOI"},
        "identity_admission": {
            "requested_symbol": "AAOI", "alias_interpretation": "current_alias_only",
            "canonical_security_id": "SEC:US-XNAS-AAOI",
        },
        "effective_context": {
            "symbol": "AAOI", "precedence_reason": "ambient_context",
            "ambient_used": True,
        },
        "facts": [{
            "clause_id": "c1", "display_order": 0, "field_id": "stage.current",
            "entity": {"type": "security", "id": "SEC:US-XNAS-AAOI"},
            "fact_fingerprint": fingerprint, "status": "available", "reason_code": None,
            "unit": "stage_code", "source": {"source_id": "stage_analysis.screener"},
            "as_of": "2026-08-23", "freshness": {"state": "fresh"},
        }],
        "clauses": [{
            "clause_id": "c1", "display_order": 0, "field_id": "stage.current",
            "fact_fingerprint": fingerprint, "status": "available",
            "receipt_kind": "typed_fact",
        }],
    }
    done = {
        "type": "done", "route": "instant/native-fact", "degraded": False,
        "usage": {"latency": {
            "route": "instant/native-fact", "ttfv_ms": 1, "total_ms": 2,
        }},
        "native_fact_receipt": native_receipt,
    }
    lines = [
        'data: {"type":"delta","text":"fixture visible"}\n', "\n",
        "data: " + json.dumps(done) + "\n", "\n",
    ]
    row = bench.summarize(bench.read_events(lines, clock=_fake_clock()), 0.0, 1)
    row.update({
        "probe": "w0b.context-collision.v1",
        "run": 1,
        "label": "warm",
        "lane": "fast",
        "base_url": "https://benchmark.example.test",
        "ts": "2026-08-24T12:00:00Z",
    })
    spec = {
        "prompt_id": "w0b.context-collision.v1",
        "prompt_version": "w0b.v1",
        "prompt_class": "context-collision",
        "prompt_text_hash": "a" * 64,
        "manifest_digest": "b" * 64,
        "explicit_context": {"entity": "INOD"},
        "ambient_context": {"symbol": "AAOI"},
        "expected_effective_entity": "INOD",
        "expected_precedence_reason": "explicit_entity_wins",
    }
    receipt = bench.build_receipt_row(
        row, spec, run=1, lane="fast", system="mastermind", environment="production",
        cache_label="warm", cache_basis="natural_running_service",
        health={"commit": "a" * 12, "checkout": "b" * 12, "error": None},
        reviewer="fixture", rubric_version=bench.W0B_RUBRIC_VERSION,
    )
    assert receipt["actual_effective_entity"] == "AAOI"
    assert receipt["actual_precedence_reason"] == "ambient_context"
    assert receipt["precedence_match"] is False
    assert "fixture visible" not in json.dumps(receipt)
    assert bench._is_safe_native_fact_projection(receipt["native_fact_receipt"])
    assert bench._validate_receipt_row(receipt) is receipt
    mutated = json.loads(json.dumps(receipt))
    mutated["ambient_used"] = False
    with pytest.raises(ValueError, match="differs from top-level identity"):
        bench._validate_receipt_row(mutated)


def test_w0b_p95_is_nearest_rank_and_never_printed_for_one_observation(capsys):
    assert bench._nearest_rank_percentile(list(range(1, 21)), 0.95) == 19
    bench.print_p95([{"probe": "single", "ttfv_ms": 1, "done_ms": 2,
                      "headers_ms": 1}])
    assert capsys.readouterr().out == ""


def test_w0b_scorecard_binds_every_strict_private_receipt_exactly_once(tmp_path):
    receipts = _complete_w0b_receipts(tmp_path)
    source = tmp_path / "receipt.jsonl"
    scorecard = tmp_path / "scorecard.json"
    target = tmp_path / "scored.jsonl"
    source.write_text("".join(json.dumps(row) + "\n" for row in receipts), encoding="utf-8")
    scorecard.write_text(json.dumps(_complete_w0b_scorecard(receipts)), encoding="utf-8")
    assert bench.score_receipt_file(str(source), str(scorecard), str(target)) == 0
    scored = [json.loads(line) for line in target.read_text(encoding="utf-8").splitlines()]
    assert [row["prompt_id"] for row in scored] == [row["prompt_id"] for row in receipts]
    assert all(row["reviewer"] == "fixture-reviewer" for row in scored)
    assert all(row["rubric_version"] == bench.W0B_RUBRIC_VERSION for row in scored)
    assert all(row["rubric_digest"] == bench.W0B_RUBRIC_DIGEST for row in scored)
    assert target.stat().st_mode & 0o777 == 0o600
    with pytest.raises(ValueError, match="complete W0-B corpus"):
        bench.apply_scorecard(receipts[:1], bench.load_scorecard(str(scorecard)))


def test_w0b_score_input_rejects_duplicate_receipts_and_raw_or_unknown_fields(tmp_path, capsys):
    receipts = _complete_w0b_receipts(tmp_path)
    scorecard = tmp_path / "scorecard.json"
    scorecard.write_text(json.dumps(_complete_w0b_scorecard(receipts)), encoding="utf-8")

    duplicate_source = tmp_path / "duplicate-receipt.jsonl"
    duplicate_source.write_text(
        "".join(json.dumps(row) + "\n" for row in [*receipts, receipts[0]]), encoding="utf-8"
    )
    assert bench.score_receipt_file(
        str(duplicate_source), str(scorecard), str(tmp_path / "duplicate-scored.jsonl")
    ) == 2
    assert "private benchmark scoring failed: ValueError" in capsys.readouterr().err

    hostile = dict(receipts[0])
    hostile["raw_answer"] = "PRIVATE RAW ANSWER MUST NOT LEAK"
    hostile_source = tmp_path / "hostile-receipt.jsonl"
    hostile_source.write_text(json.dumps(hostile) + "\n", encoding="utf-8")
    assert bench.score_receipt_file(
        str(hostile_source), str(scorecard), str(tmp_path / "hostile-scored.jsonl")
    ) == 2
    stderr = capsys.readouterr().err
    assert "PRIVATE RAW ANSWER MUST NOT LEAK" not in stderr
    assert str(hostile_source) not in stderr


@pytest.mark.parametrize("mutation", [
    lambda row: row.update({"ts": "PRIVATE PROMPT /Users/alice/secret"}),
    lambda row: row.update({"error": "short private answer text", "degraded": True}),
    lambda row: row.update({"health_error": "private account state"}),
    lambda row: row.update({"cache_label": "cold"}),
    lambda row: row.update({"context_bytes": 999999}),
    lambda row: row.update({"actual_effective_entity": "AAPL"}),
    lambda row: row["server_timing"].update({"route": "instant"}),
    lambda row: row.update({"server_tool_count": 99, "server_tool_durations_ms": [999]}),
])
def test_w0b_score_input_rejects_text_or_cross_field_mutations(tmp_path, mutation):
    receipt = _complete_w0b_receipts(tmp_path)[0]
    mutation(receipt)
    with pytest.raises(ValueError):
        bench._validate_receipt_row(receipt)


def test_w0b_score_binding_rejects_noncontiguous_runs_or_manifest_digest_drift(tmp_path):
    receipts = _complete_w0b_receipts(tmp_path)
    run_two = [{**receipt, "run": 2} for receipt in receipts]
    with pytest.raises(ValueError, match="contiguous from 1"):
        bench.apply_scorecard(run_two, {})

    scorecard = _complete_w0b_scorecard(receipts)
    scorecard["manifest_digest"] = "f" * 64
    scorecard_path = tmp_path / "drifted-scorecard.json"
    scorecard_path.write_text(json.dumps(scorecard), encoding="utf-8")
    scores = bench.load_scorecard(str(scorecard_path))
    with pytest.raises(ValueError, match="manifest digest"):
        bench.apply_scorecard(receipts, scores)

    exact_scorecard = _complete_w0b_scorecard(receipts)
    exact_path = tmp_path / "exact-scorecard.json"
    exact_path.write_text(json.dumps(exact_scorecard), encoding="utf-8")
    exact_scores = bench.load_scorecard(str(exact_path))
    stitched = json.loads(json.dumps(receipts))
    stitched[1]["deployed_commit"] = "e" * 12
    with pytest.raises(ValueError, match="invocation identity"):
        bench.apply_scorecard(stitched, exact_scores)

    mismatched_reviewer = _complete_w0b_scorecard(receipts)
    mismatched_reviewer["reviewer"] = "different-reviewer"
    reviewer_path = tmp_path / "reviewer-scorecard.json"
    reviewer_path.write_text(json.dumps(mismatched_reviewer), encoding="utf-8")
    with pytest.raises(ValueError, match="reviewer must match"):
        bench.apply_scorecard(receipts, bench.load_scorecard(str(reviewer_path)))


def test_w0b_native_failure_projection_binds_top_level_degraded_state(tmp_path):
    _version, _digest, specs = bench.load_private_manifest(str(_write_w0b_manifest(tmp_path)))
    failure = bench._safe_native_fact_receipt({
        "schema": "brain.native_fact_receipt.v1",
        "route": "instant/native-fact",
        "planner_version": "w1b.native_fact_planner.v1",
        "registry_digest": None,
        "effective_context": {
            "symbol": "AAPL",
            "precedence_reason": "explicit_entity_wins",
            "ambient_used": False,
        },
        "canonical_entity": None,
        "identity_admission": None,
        "facts": [],
        "clauses": [],
        "relationship_receipt": None,
        "rank_resolution_failure": None,
        "failure": {"status": "unavailable", "reason_code": "identity_unavailable"},
    })
    assert failure is not None
    hostile_failure = {
        "schema": "brain.native_fact_receipt.v1",
        "route": "instant/native-fact",
        "planner_version": "w1b.native_fact_planner.v1",
        "registry_digest": None,
        "effective_context": {
            "symbol": "AAPL", "precedence_reason": "explicit_entity_wins",
            "ambient_used": False,
        },
        "canonical_entity": None,
        "identity_admission": {
            "requested_symbol": "AAPL", "alias_interpretation": "current_alias_only",
            "canonical_security_id": "SEC:US-XNAS-AAPL",
        },
        "facts": [], "clauses": [], "relationship_receipt": None,
        "rank_resolution_failure": None,
        "failure": {"status": "unavailable", "reason_code": "identity_unavailable"},
    }
    assert bench._safe_native_fact_receipt(hostile_failure) is None
    spec = specs[3]
    row = {
        "probe": spec["prompt_id"], "run": 1, "label": "warm", "lane": "fast",
        "base_url": "https://benchmark.example.test", "ts": "2026-08-24T12:00:00Z",
        "route": "instant/native-fact", "headers_ms": 1, "first_status_ms": 2,
        "ttfv_ms": 3, "done_ms": 4, "n_deltas": 1, "n_tool_events": 0,
        "server_latency": {
            "route": "instant/native-fact", "ttfv_ms": 3, "total_ms": 4, "rounds": [],
        },
        "native_fact_receipt": failure, "answer_chars": 12, "output_bytes": 12,
        "degraded": True, "error": None,
    }
    receipt = bench.build_receipt_row(
        row, spec, run=1, lane="fast", system="mastermind", environment="production",
        cache_label="warm", cache_basis="natural_running_service",
        health={"commit": "a" * 12, "checkout": "b" * 12, "error": None},
        reviewer="fixture-reviewer", rubric_version=bench.W0B_RUBRIC_VERSION,
    )
    assert bench._validate_receipt_row(receipt) is receipt
    receipt["degraded"] = False
    with pytest.raises(ValueError, match="differs from top-level identity"):
        bench._validate_receipt_row(receipt)


@pytest.mark.parametrize("field, value", [
    ("field_correctness", float("nan")),
    ("numeric_correctness", 2),
    ("unsupported_claim_count", -1),
])
def test_w0b_scorecard_rejects_nonfinite_or_out_of_range_scores(tmp_path, field, value):
    receipts = _complete_w0b_receipts(tmp_path)
    scorecard = _complete_w0b_scorecard(receipts)
    scorecard["scores"][0][field] = value
    path = tmp_path / "invalid-scorecard.json"
    path.write_text(json.dumps(scorecard), encoding="utf-8")
    with pytest.raises(ValueError):
        bench.load_scorecard(str(path))


def test_w0b_cli_manifest_errors_redact_private_path_and_text(tmp_path, capsys):
    manifest = _complete_w0b_manifest()
    manifest["prompts"][4]["prompt_text"] = "PRIVATE PROMPT THAT MUST NOT LEAK"
    manifest["prompts"][4]["prompt_text_hash"] = "0" * 64
    path = _write_w0b_manifest(tmp_path, manifest)
    assert bench.main([
        "--manifest", str(path), "--out", str(tmp_path / "receipt.jsonl"),
        "--reviewer", "fixture-reviewer", "--rubric-version", bench.W0B_RUBRIC_VERSION,
        "--expected-manifest-digest", "a" * 64,
    ]) == 2
    stderr = capsys.readouterr().err
    assert "PRIVATE PROMPT THAT MUST NOT LEAK" not in stderr
    assert str(path) not in stderr
    assert "manifest prompt hash mismatch" in stderr


def test_w0b_cli_rejects_private_prompt_mutation_against_pinned_manifest_digest(
        tmp_path, monkeypatch):
    original = _complete_w0b_manifest()
    original_path = _write_w0b_manifest(tmp_path, original)
    _version, original_digest, _specs = bench.load_private_manifest(str(original_path))
    mutated = _complete_w0b_manifest()
    replacement = "Use a different but internally self-hashed screener prompt."
    mutated["prompts"][5].update({
        "prompt_text": replacement,
        "prompt_text_hash": bench._sha256_text(replacement),
    })
    mutated_path = tmp_path / "mutated-private-w0b-manifest.json"
    mutated_path.write_text(json.dumps(mutated), encoding="utf-8")
    monkeypatch.setattr(
        bench, "probe", lambda *args, **kwargs: pytest.fail("digest mismatch sent a probe")
    )
    assert bench.main([
        "--manifest", str(mutated_path),
        "--expected-manifest-digest", original_digest,
        "--out", str(tmp_path / "receipt.jsonl"),
        "--reviewer", "fixture-reviewer",
        "--rubric-version", bench.W0B_RUBRIC_VERSION,
    ]) == 2
    assert not (tmp_path / "receipt.jsonl").exists()


@pytest.mark.parametrize("health, expected_checkout, error", [
    (
        {"commit": "b" * 12, "checkout": "c" * 12, "error": None},
        "",
        "process commit does not match",
    ),
    (
        {"commit": "a" * 12, "checkout": "c" * 12, "error": None},
        "d" * 40,
        "checkout does not match",
    ),
    (
        {"commit": None, "checkout": None, "error": "fixture unavailable"},
        "",
        "health identity is unavailable",
    ),
])
def test_w0b_production_identity_fails_before_any_probe(
        tmp_path, monkeypatch, capsys, health, expected_checkout, error):
    manifest_path = _write_w0b_manifest(tmp_path)
    _version, manifest_digest, _specs = bench.load_private_manifest(str(manifest_path))
    monkeypatch.setattr(bench, "capture_health", lambda *args, **kwargs: health)
    monkeypatch.setattr(
        bench, "probe",
        lambda *args, **kwargs: pytest.fail("production identity failure sent a probe"),
    )
    argv = [
        "--base-url", "https://benchmark.example.test",
        "--cookie", "ephemeral-guest-fixture",
        "--environment", "production",
        "--cache-basis", "natural_running_service",
        "--manifest", str(manifest_path),
        "--out", str(tmp_path / "after-receipt.jsonl"),
        "--health-url", "https://benchmark.example.test/api/health",
        "--expected-deployed-commit", "a" * 40,
        "--reviewer", "fixture-reviewer",
        "--rubric-version", bench.W0B_RUBRIC_VERSION,
        "--expected-manifest-digest", manifest_digest,
    ]
    if expected_checkout:
        argv.extend(["--expected-deployed-checkout", expected_checkout])
    assert bench.main(argv) == 2
    assert error in capsys.readouterr().err
    assert not (tmp_path / "after-receipt.jsonl").exists()


def test_w0b_manifest_run_rejects_partial_or_nonpositive_execution_before_probe(
        tmp_path, monkeypatch):
    manifest_path = _write_w0b_manifest(tmp_path)
    _version, manifest_digest, _specs = bench.load_private_manifest(str(manifest_path))
    monkeypatch.setattr(
        bench, "probe",
        lambda *args, **kwargs: pytest.fail("invalid corpus arguments sent a probe"),
    )
    common = [
        "--manifest", str(manifest_path),
        "--out", str(tmp_path / "receipt.jsonl"),
        "--reviewer", "fixture-reviewer",
        "--rubric-version", bench.W0B_RUBRIC_VERSION,
        "--expected-manifest-digest", manifest_digest,
    ]
    assert bench.main([*common, "--only", "legacy.instant.v1"]) == 2
    assert bench.main([*common, "--runs", "0"]) == 2


def test_w0b_deployment_identity_accepts_safe_short_or_full_sha_prefixes():
    full = "abcdef0123456789" * 2 + "abcdef01"
    assert bench._sha_prefix_matches(full[:12], full)
    assert bench._sha_prefix_matches(full, full[:12])
    assert not bench._sha_prefix_matches("abcdef0", "bbcdef0")
    assert not bench._sha_prefix_matches("unknown", full)


def test_w0b_production_identity_is_rechecked_after_complete_corpus(
        tmp_path, monkeypatch, capsys):
    manifest_path = _write_w0b_manifest(tmp_path)
    _version, manifest_digest, _specs = bench.load_private_manifest(str(manifest_path))
    health_reads = iter([
        {"commit": "a" * 12, "checkout": "c" * 12, "error": None},
        {"commit": "b" * 12, "checkout": "d" * 12, "error": None},
    ])
    monkeypatch.setattr(bench, "capture_health", lambda *args, **kwargs: next(health_reads))
    probes = []

    def _probe(*args, **kwargs):
        probes.append(args[1])
        return {
            "headers_ms": 1, "first_status_ms": 2, "ttfv_ms": 3, "done_ms": 4,
            "n_deltas": 1, "n_tool_events": 0, "route": "deep",
            "server_latency": {"route": "deep", "ttfv_ms": 3, "total_ms": 4,
                               "rounds": []},
            "answer_chars": 7, "output_bytes": 7, "degraded": False, "error": None,
        }

    monkeypatch.setattr(bench, "probe", _probe)
    out = tmp_path / "after-receipt.jsonl"
    assert bench.main([
        "--base-url", "https://benchmark.example.test",
        "--cookie", "ephemeral-guest-fixture",
        "--environment", "production",
        "--cache-basis", "natural_running_service",
        "--manifest", str(manifest_path),
        "--expected-manifest-digest", manifest_digest,
        "--out", str(out),
        "--health-url", "https://benchmark.example.test/api/health",
        "--expected-deployed-commit", "a" * 40,
        "--reviewer", "fixture-reviewer",
        "--rubric-version", bench.W0B_RUBRIC_VERSION,
    ]) == 2
    assert len(probes) == len(bench.W0B_CORPUS_V1)
    assert "identity changed during the corpus" in capsys.readouterr().err
    assert not out.exists()


def test_w0b_production_checkout_change_without_optional_pin_writes_no_proof(
        tmp_path, monkeypatch, capsys):
    manifest_path = _write_w0b_manifest(tmp_path)
    _version, manifest_digest, _specs = bench.load_private_manifest(str(manifest_path))
    health_reads = iter([
        {"commit": "a" * 12, "checkout": "b" * 12, "error": None},
        {"commit": "a" * 12, "checkout": "c" * 12, "error": None},
    ])
    monkeypatch.setattr(bench, "capture_health", lambda *args, **kwargs: next(health_reads))
    probes = []

    def _probe(*args, **kwargs):
        probes.append(args[1])
        return {
            "headers_ms": 1, "first_status_ms": 2, "ttfv_ms": 3, "done_ms": 4,
            "n_deltas": 1, "n_tool_events": 0, "route": "deep",
            "server_latency": {
                "route": "deep", "ttfv_ms": 3, "total_ms": 4, "rounds": [],
            },
            "answer_chars": 7, "output_bytes": 7, "degraded": False, "error": None,
            "_raw_answer": "private fixture",
        }

    monkeypatch.setattr(bench, "probe", _probe)
    out = tmp_path / "after-receipt.jsonl"
    raw_out = tmp_path / "after-answers.jsonl"
    assert bench.main([
        "--base-url", "https://benchmark.example.test",
        "--cookie", "ephemeral-guest-fixture",
        "--environment", "production",
        "--cache-basis", "natural_running_service",
        "--manifest", str(manifest_path),
        "--expected-manifest-digest", manifest_digest,
        "--out", str(out),
        "--raw-answer-out", str(raw_out),
        "--health-url", "https://benchmark.example.test/api/health",
        "--expected-deployed-commit", "a" * 40,
        "--reviewer", "fixture-reviewer",
        "--rubric-version", bench.W0B_RUBRIC_VERSION,
    ]) == 2
    assert len(probes) == len(bench.W0B_CORPUS_V1)
    assert "deployment checkout changed during the corpus" in capsys.readouterr().err
    assert not out.exists()
    assert not raw_out.exists()


def test_w0b_private_output_is_owner_only_and_refuses_symlink(tmp_path):
    target = tmp_path / "private.jsonl"
    bench.append_jsonl(target, [{"safe": True}])
    assert target.stat().st_mode & 0o777 == 0o600
    link = tmp_path / "link.jsonl"
    link.symlink_to(target)
    with pytest.raises(OSError):
        bench.append_jsonl(link, [{"must_not_land": True}])
    assert "must_not_land" not in target.read_text(encoding="utf-8")


def test_w0b_cli_raw_and_scored_outputs_refuse_dangling_symlinks(tmp_path, monkeypatch):
    raw_target = tmp_path / "raw-target.jsonl"
    raw_link = tmp_path / "raw-link.jsonl"
    raw_link.symlink_to(raw_target)
    monkeypatch.setattr(bench, "probe", lambda *args, **kwargs: {
        "headers_ms": 1, "first_status_ms": 2, "ttfv_ms": 3, "done_ms": 4,
        "n_deltas": 1, "n_tool_events": 0, "route": "instant",
        "server_latency": None, "answer_chars": 7, "output_bytes": 7,
        "degraded": False, "error": None, "_raw_answer": "private fixture",
    })
    monkeypatch.setattr(bench, "print_table", lambda rows: None)
    monkeypatch.setattr(bench, "print_medians", lambda rows: None)
    monkeypatch.setattr(bench, "print_p95", lambda rows: None)
    assert bench.main([
        "--only", "instant", "--raw-answer-out", str(raw_link),
    ]) == 2
    assert raw_link.is_symlink()
    assert not raw_target.exists()

    receipt = {
        "schema": bench.AI_BENCHMARK_RECEIPT_SCHEMA,
        "prompt_id": "p1",
        "run": 1,
    }
    source = tmp_path / "receipt.jsonl"
    source.write_text(json.dumps(receipt) + "\n", encoding="utf-8")
    scorecard = tmp_path / "scorecard.json"
    scorecard.write_text(json.dumps({
        "schema": bench.AI_BENCHMARK_SCORECARD_SCHEMA,
        "rubric_version": bench.W0B_RUBRIC_VERSION,
        "reviewer": "fixture-reviewer",
        "rubric": bench.W0B_FROZEN_RUBRIC,
        "manifest_digest": "a" * 64,
        "scores": [],
    }), encoding="utf-8")
    scored_target = tmp_path / "scored-target.jsonl"
    scored_link = tmp_path / "scored-link.jsonl"
    scored_link.symlink_to(scored_target)
    assert bench.score_receipt_file(str(source), str(scorecard), str(scored_link)) == 2
    assert scored_link.is_symlink()
    assert not scored_target.exists()


def test_w0b_native_receipt_projection_rejects_path_like_or_extra_proof_metadata():
    hostile = {
        "schema": "brain.native_fact_receipt.v1",
        "route": "instant/native-fact",
        "planner_version": "w1b.native_fact_planner.v1",
        "registry_digest": "/Users/private/secret",
        "canonical_entity": {
            "type": "security", "id": "SEC:US-XNAS-AAPL",
            "owner_artifact": "/Users/private/path",
        },
        "identity_admission": {
            "requested_symbol": "AAPL", "alias_interpretation": "current_alias_only",
            "canonical_security_id": "SEC:US-XNAS-AAPL",
        },
        "effective_context": {
            "symbol": "AAPL", "precedence_reason": "explicit_request",
            "ambient_used": False,
        },
        "facts": [{
            "clause_id": "c1", "display_order": 0,
            "field_id": "stage.current",
            "entity": {"type": "security", "id": "SEC:US-XNAS-AAPL"},
            "fact_fingerprint": "a" * 64,
            "status": "available", "reason_code": None, "unit": "stage_code",
            "source": {"source_id": "/Users/private/source"},
            "as_of": "2026-08-23", "freshness": {"state": "fresh"},
        }],
        "clauses": [],
    }
    assert bench._safe_native_fact_receipt(hostile) is None

    safe = dict(hostile)
    safe["registry_digest"] = "b" * 64
    safe["facts"] = [{
        "clause_id": "c1", "display_order": 0,
        "field_id": "stage.current",
        "entity": {"type": "security", "id": "SEC:US-XNAS-AAPL"},
        "fact_fingerprint": "a" * 64,
        "status": "available", "reason_code": None, "unit": "stage_code",
        "source": {"source_id": "stage_analysis.screener"},
        "as_of": "2026-08-23", "freshness": {"state": "fresh"},
    }]
    safe["clauses"] = [{
        "clause_id": "c1", "display_order": 0,
        "field_id": "stage.current", "fact_fingerprint": "a" * 64,
        "status": "available", "receipt_kind": "typed_fact",
    }]
    projected = bench._safe_native_fact_receipt(safe)
    assert projected is not None
    assert projected["canonical_entity"] == {
        "type": "security", "id": "SEC:US-XNAS-AAPL",
    }
    assert projected["facts"][0]["entity"] == projected["canonical_entity"]
    assert "/Users" not in json.dumps(projected)

    price = json.loads(json.dumps(safe))
    price["facts"][0]["field_id"] = "market.price.last"
    price["facts"][0]["unit"] = "USD"
    price["clauses"][0]["field_id"] = "market.price.last"
    projected_price = bench._safe_native_fact_receipt(price)
    assert projected_price is not None
    assert projected_price["facts"][0]["unit"] == "USD"

    invalid_currency = json.loads(json.dumps(price))
    invalid_currency["facts"][0]["unit"] = "USDT"
    assert bench._safe_native_fact_receipt(invalid_currency) is None

    missing_price_unit = json.loads(json.dumps(price))
    missing_price_unit["facts"][0]["unit"] = None
    assert bench._safe_native_fact_receipt(missing_price_unit) is None

    missing_fixed_unit = json.loads(json.dumps(safe))
    missing_fixed_unit["facts"][0]["unit"] = None
    assert bench._safe_native_fact_receipt(missing_fixed_unit) is None

    for field_id, currency_shaped_unit in (
        ("stage.current", "USD"),
        ("market.return.1m", "JPY"),
        ("earnings.next_date", "ABC"),
        ("security.industry_member.rs_percentile", "USD"),
    ):
        wrong_dynamic_field = json.loads(json.dumps(safe))
        wrong_dynamic_field["facts"][0]["field_id"] = field_id
        wrong_dynamic_field["facts"][0]["unit"] = currency_shaped_unit
        wrong_dynamic_field["clauses"][0]["field_id"] = field_id
        assert bench._safe_native_fact_receipt(wrong_dynamic_field) is None

    wrong_fixed_unit = json.loads(json.dumps(safe))
    wrong_fixed_unit["facts"][0]["unit"] = "percent"
    assert bench._safe_native_fact_receipt(wrong_fixed_unit) is None

    wrong_symbol = json.loads(json.dumps(safe))
    wrong_symbol["effective_context"]["symbol"] = "INOD"
    assert bench._safe_native_fact_receipt(wrong_symbol) is None

    missing_admission = json.loads(json.dumps(safe))
    missing_admission.pop("identity_admission")
    assert bench._safe_native_fact_receipt(missing_admission) is None

    wrong_admission_symbol = json.loads(json.dumps(safe))
    wrong_admission_symbol["identity_admission"]["requested_symbol"] = "INOD"
    assert bench._safe_native_fact_receipt(wrong_admission_symbol) is None

    wrong_alias_kind = json.loads(json.dumps(safe))
    wrong_alias_kind["identity_admission"]["alias_interpretation"] = "id_suffix_guess"
    assert bench._safe_native_fact_receipt(wrong_alias_kind) is None

    wrong_fact_entity = json.loads(json.dumps(safe))
    wrong_fact_entity["facts"][0]["entity"]["id"] = "SEC:US-XNAS-AAOI"
    assert bench._safe_native_fact_receipt(wrong_fact_entity) is None


def test_w0b_native_rank_proof_binds_relationship_origin_and_industry_target():
    raw = {
        "schema": "brain.native_fact_receipt.v1",
        "route": "instant/native-fact",
        "planner_version": "w1b.native_fact_planner.v1",
        "registry_digest": "d" * 64,
        "canonical_entity": {"type": "security", "id": "SEC:US-XNAS-AAPL"},
        "identity_admission": {
            "requested_symbol": "AAPL", "alias_interpretation": "current_alias_only",
            "canonical_security_id": "SEC:US-XNAS-AAPL",
        },
        "effective_context": {
            "symbol": "AAPL", "precedence_reason": "explicit_request",
            "ambient_used": False,
        },
        "facts": [{
            "clause_id": "c1", "display_order": 0,
            "field_id": "industry.rank.percentile",
            "entity": {"type": "industry", "id": "software"},
            "fact_fingerprint": "a" * 64, "status": "available", "reason_code": None,
            "unit": "percentile", "source": {"source_id": "stage_analysis.screener"},
            "as_of": "2026-08-23", "freshness": {"state": "fresh"},
        }],
        "clauses": [{
            "clause_id": "c1", "display_order": 0,
            "field_id": "industry.rank.percentile", "fact_fingerprint": "a" * 64,
            "status": "available", "receipt_kind": "typed_fact",
        }],
        "relationship_receipt": {
            "from": {"type": "security", "id": "SEC:US-XNAS-AAPL"},
            "to": {"type": "industry", "id": "software"},
            "status": "available", "reason_code": None,
            "relationship_fingerprint": "b" * 64,
            "source": {"source_id": "stage_analysis.screener"},
            "as_of": "2026-08-23",
        },
    }
    projected = bench._safe_native_fact_receipt(raw)
    assert projected is not None
    assert projected["relationship"]["from_security_id"] == "SEC:US-XNAS-AAPL"
    assert projected["facts"][0]["entity"] == {"type": "industry", "id": "software"}

    wrong_origin = json.loads(json.dumps(raw))
    wrong_origin["relationship_receipt"]["from"]["id"] = "SEC:US-XNAS-AAOI"
    assert bench._safe_native_fact_receipt(wrong_origin) is None

    wrong_target = json.loads(json.dumps(raw))
    wrong_target["facts"][0]["entity"]["id"] = "hardware"
    assert bench._safe_native_fact_receipt(wrong_target) is None


@pytest.mark.parametrize(("symbol", "canonical_id"), [
    ("FI", "SEC:US-XNAS-FISV"),
    ("MRSH", "SEC:US-XNYS-MMC"),
])
def test_w0b_native_proof_uses_rename_safe_w1a_identity_admission(symbol, canonical_id):
    raw = {
        "schema": "brain.native_fact_receipt.v1",
        "route": "instant/native-fact",
        "planner_version": "w1b.native_fact_planner.v1",
        "registry_digest": "d" * 64,
        "canonical_entity": {"type": "security", "id": canonical_id},
        "identity_admission": {
            "requested_symbol": symbol, "alias_interpretation": "current_alias_only",
            "canonical_security_id": canonical_id,
        },
        "effective_context": {
            "symbol": symbol, "precedence_reason": "explicit_request",
            "ambient_used": False,
        },
        "facts": [{
            "clause_id": "c1", "display_order": 0,
            "field_id": "market.price.last",
            "entity": {"type": "security", "id": canonical_id},
            "fact_fingerprint": "a" * 64, "status": "unavailable",
            "reason_code": "owner_unavailable", "unit": "currency",
            "source": {"source_id": "quote_resolution"},
            "as_of": None, "freshness": {"state": "unknown"},
        }],
        "clauses": [{
            "clause_id": "c1", "display_order": 0,
            "field_id": "market.price.last", "fact_fingerprint": "a" * 64,
            "status": "unavailable", "receipt_kind": "typed_fact",
        }],
    }
    projected = bench._safe_native_fact_receipt(raw)
    assert projected is not None
    assert projected["actual_effective_entity"] == symbol
    assert projected["canonical_entity"]["id"] == canonical_id

    wrong_canonical = json.loads(json.dumps(raw))
    wrong_canonical["canonical_entity"]["id"] = "SEC:US-XNAS-AAOI"
    wrong_canonical["facts"][0]["entity"]["id"] = "SEC:US-XNAS-AAOI"
    assert bench._safe_native_fact_receipt(wrong_canonical) is None


def test_w0b_native_route_with_malformed_proof_fails_the_run(tmp_path, monkeypatch):
    lines = [
        'data: {"type":"delta","text":"fixture visible"}\n', "\n",
        'data: {"type":"done","route":"instant/native-fact","degraded":false,'
        '"usage":{"latency":{"route":"instant/native-fact","ttfv_ms":1,"total_ms":2}},'
        '"native_fact_receipt":{"schema":"brain.native_fact_receipt.v1",'
        '"route":"instant/native-fact","planner_version":"w1b.native_fact_planner.v1",'
        '"registry_digest":"/Users/private/secret","effective_context":'
        '{"symbol":"AAPL","precedence_reason":"explicit_request",'
        '"ambient_used":false},"facts":[],"clauses":[]}}\n',
        "\n",
    ]
    row = bench.summarize(bench.read_events(lines, clock=_fake_clock()), 0.0, 1)
    assert row["route"] == "instant/native-fact"
    assert row["native_fact_receipt"] is None
    assert row["degraded"] is True
    assert row["error"] == "native route omitted or malformed proof receipt"

    monkeypatch.setattr(bench, "probe", lambda *args, **kwargs: dict(row))
    monkeypatch.setattr(bench, "print_table", lambda rows: None)
    monkeypatch.setattr(bench, "print_medians", lambda rows: None)
    monkeypatch.setattr(bench, "print_p95", lambda rows: None)
    assert bench.main(["--only", "instant", "--out", str(tmp_path / "receipt.jsonl")]) == 1

    proofless = {
        "schema": "brain.native_fact_receipt.v1",
        "route": "instant/native-fact",
        "planner_version": "w1b.native_fact_planner.v1",
        "effective_context": {
            "symbol": "AAPL", "precedence_reason": "explicit_request",
            "ambient_used": False,
        },
        "facts": [], "clauses": [],
    }
    proofless_done = {
        "type": "done", "route": "instant/native-fact", "degraded": False,
        "usage": {"latency": {"route": "instant/native-fact"}},
        "native_fact_receipt": proofless,
    }
    proofless_row = bench.summarize(bench.read_events([
        'data: {"type":"delta","text":"fabricated native prose"}\n', "\n",
        "data: " + json.dumps(proofless_done) + "\n", "\n",
    ], clock=_fake_clock()), 0.0, 1)
    assert proofless_row["native_fact_receipt"] is None
    assert proofless_row["error"] == "native route omitted or malformed proof receipt"


def test_w0b_legacy_main_stays_selectable_and_writes_a_text_free_receipt(tmp_path, monkeypatch):
    captured: list[dict] = []

    def _probe(*args, **kwargs):
        return {
            "headers_ms": 1, "first_status_ms": 2, "ttfv_ms": 3, "done_ms": 4,
            "n_deltas": 1, "n_tool_events": 0, "route": "instant",
            "server_latency": None, "answer_chars": 7, "output_bytes": 7,
            "degraded": False, "error": None,
        }

    monkeypatch.setattr(bench, "probe", _probe)
    monkeypatch.setattr(bench, "print_table", lambda rows: None)
    monkeypatch.setattr(bench, "print_medians", lambda rows: None)
    monkeypatch.setattr(bench, "append_jsonl", lambda path, rows, **kwargs: captured.extend(rows))
    assert bench.main(["--only", "instant", "--cookie", "fixture", "--out",
                       str(tmp_path / "receipt.jsonl")]) == 0
    assert len(captured) == 1
    receipt = captured[0]
    assert receipt["probe"] == "instant"
    assert receipt["prompt_id"] == "legacy.instant.v1"
    assert receipt["schema"] == "ai_benchmark_receipt.v1"
    assert "message" not in receipt


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


# ---------------------------------------------------------------------------
# W1-B — deterministic W1-A native fact planner/executor
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(("message", "expected"), [
    ("AAPL price", ("market.price.last",)),
    ("What's AAPL trading at?", ("market.price.last",)),
    ("How much is AAPL?", ("market.price.last",)),
    ("AAPL Stage", ("stage.current",)),
    ("AAPL weeks in Stage", ("stage.weeks_in_stage",)),
    ("AAPL 1m, 3m and 12m return", (
        "market.return.1m", "market.return.3m", "market.return.12m")),
    ("AAPL industry rank", ("industry.rank.percentile",)),
    ("AAPL within-industry member RS percentile", (
        "security.industry_member.rs_percentile",)),
    ("AAPL next earnings date", ("earnings.next_date",)),
    ("AAPL latest EPS growth", ("earnings.latest.eps_growth_pct",)),
    ("AAPL latest revenue growth", ("earnings.latest.revenue_growth_pct",)),
    ("AAPL direct local theme memberships", ("theme.local.memberships",)),
])
def test_w1b_native_planner_maps_only_exact_frozen_fields(message, expected):
    plan = nf.plan_native_facts(message)
    assert plan is not None
    assert plan.field_ids == expected
    assert set(plan.field_ids) <= nf.ALLOWED_FIELD_IDS


def test_w1b_native_planner_preserves_multi_field_order_and_explicit_precedence():
    plan = nf.plan_native_facts(
        "Give me INOD's 1m, 3m and 12m return, Stage, industry rank and latest EPS growth.",
        {"symbol": "AAOI"},
    )
    assert plan is not None
    assert plan.symbol == "INOD"
    assert plan.explicit_entity is True
    assert plan.effective_context_reason == "explicit_entity_wins"
    assert plan.field_ids == (
        "market.return.1m", "market.return.3m", "market.return.12m", "stage.current",
        "industry.rank.percentile", "earnings.latest.eps_growth_pct",
    )


@pytest.mark.parametrize("symbol", [
    "IT", "ARE", "AS", "AT", "BE", "AN", "ME", "A", "FOR", "NOW", "NEXT", "YOU",
    "ONE", "IS",
])
def test_w1b_native_planner_grammar_collision_symbol_never_yields_to_ambient(symbol):
    plan = nf.plan_native_facts(f"{symbol} price", {"symbol": "AAPL"})
    assert plan is not None
    assert plan.symbol == symbol
    assert plan.explicit_entity is True
    assert plan.effective_context_reason == "explicit_entity_wins"


def test_w1b_native_planner_accepts_grammar_collision_in_structured_ambient_context():
    plan = nf.plan_native_facts("price", {"symbol": "IT"})
    assert plan is not None
    assert plan.symbol == "IT"
    assert plan.explicit_entity is False
    assert plan.effective_context_reason == "ambient_context"


@pytest.mark.parametrize("message", [
    "IT and price",
    "Give me IT and price",
    "IT and Stage",
    "Give me ARE and price",
    "A and price",
    "What Stage is IT",
    "What Stage is IT in",
])
def test_w1b_native_planner_ambiguous_uppercase_collision_vetoes_ambient(message):
    assert nf.plan_native_facts(message, {"symbol": "AAPL"}) is None


@pytest.mark.parametrize("message", [
    "How much is IT",
    "How much is A",
    "How much is ARE",
    "What is IT trading at",
])
def test_w1b_native_planner_natural_price_slot_beats_ambient(message):
    plan = nf.plan_native_facts(message, {"symbol": "AAPL"})
    assert plan is not None
    assert plan.symbol in {"IT", "A", "ARE"}
    assert plan.explicit_entity is True
    assert plan.effective_context_reason == "explicit_entity_wins"


@pytest.mark.parametrize(("message", "symbol", "fields"), [
    ("What's PRICE trading at?", "PRICE", ("market.price.last",)),
    ("What's QUOTE trading at?", "QUOTE", ("market.price.last",)),
    ("What's STAGE trading at?", "STAGE", ("market.price.last",)),
    ("What's STAGE price?", "STAGE", ("market.price.last",)),
    ("What's PRICE Stage?", "PRICE", ("stage.current",)),
    ("What's QUOTE Stage?", "QUOTE", ("stage.current",)),
])
def test_w1b_native_planner_explicit_suffix_slot_field_word_never_yields_to_ambient(
        message, symbol, fields):
    plan = nf.plan_native_facts(message, {"symbol": "MSFT"})
    assert plan is not None
    assert plan.symbol == symbol
    assert plan.explicit_entity is True
    assert plan.effective_context_reason == "explicit_entity_wins"
    assert plan.field_ids == fields


@pytest.mark.parametrize(("message", "field_id"), [
    ("What's PRICE?", "market.price.last"),
    ("How much is PRICE?", "market.price.last"),
    ("What's QUOTE?", "market.price.last"),
    ("What's STAGE?", "stage.current"),
])
def test_w1b_native_planner_natural_prefix_field_grammar_uses_ambient(message, field_id):
    plan = nf.plan_native_facts(message, {"symbol": "MSFT"})
    assert plan is not None
    assert plan.symbol == "MSFT"
    assert plan.explicit_entity is False
    assert plan.field_ids == (field_id,)


@pytest.mark.parametrize("message", [
    "What's THE price?",
    "What is THE price?",
    "How much is THE price?",
])
def test_w1b_native_planner_natural_prefix_determiner_cannot_defeat_ambient(message):
    assert nf.plan_native_facts(message, {"symbol": "MSFT"}) is None


def test_w1b_native_planner_dollar_collision_symbol_is_unambiguously_explicit():
    plan = nf.plan_native_facts("$IT and price", {"symbol": "AAPL"})
    assert plan is not None
    assert plan.symbol == "IT"
    assert plan.effective_context_reason == "explicit_entity_wins"


def test_w1b_native_planner_dollar_symbol_overrides_request_grammar_collision():
    plan = nf.plan_native_facts("$WHAT price", {"symbol": "AAPL"})
    assert plan is not None
    assert plan.symbol == "WHAT"
    assert plan.effective_context_reason == "explicit_entity_wins"


@pytest.mark.parametrize(("message", "fields"), [
    ("PRICE AND STAGE", ("market.price.last", "stage.current")),
    ("PRICE WITH STAGE", ("market.price.last", "stage.current")),
    ("PRICE AND INDUSTRY RANK", ("market.price.last", "industry.rank.percentile")),
])
def test_w1b_native_planner_all_caps_grammar_cannot_hijack_ambient(message, fields):
    plan = nf.plan_native_facts(message, {"symbol": "AAPL"})
    assert plan is not None
    assert plan.symbol == "AAPL"
    assert plan.explicit_entity is False
    assert plan.field_ids == fields


@pytest.mark.parametrize("message", ["THE STAGE", "WHAT STAGE", "SHOW STAGE", "GIVE ME PRICE"])
def test_w1b_native_planner_all_caps_ambiguous_request_prose_goes_deep(message):
    assert nf.plan_native_facts(message, {"symbol": "AAPL"}) is None


@pytest.mark.parametrize("message", [
    "why is AAPL down", "AAPL price target", "should I buy AAPL", "forecast AAPL Stage",
    "compare AAPL and MSFT price", "AAPL vs MSFT", "AAPL price last month", "AAPL RS",
    "0700.HK price", "SSE:600036 price",
])
def test_w1b_native_planner_falls_through_for_ambiguous_analytical_history_or_non_us(message):
    assert nf.plan_native_facts(message, {"symbol": "AAOI"}) is None


@pytest.mark.parametrize("message", [
    "AAPL price yesterday",
    "AAPL Stage in 2024",
    "Give AAPL price and volume",
    "AAPL price and market capitalization",
    "AAPL price and EPS",
    "AAPL returns and Stage",
    "AAPL one month return and Stage",
    "AAPL Stage and weeks",
    "AAPL price and theme",
    "AAPL price and growth",
    "AAPL price and memberships",
    "AAPL price and strength",
    "AAPL price and member",
    "AAPL price over one year",
    "AAPL Stage over one year",
    "AAPL price for the month",
    "AAPL price one month",
    "AAPL price over one month",
    "AAPL price over the year",
    "AAPL price for one year",
])
def test_w1b_native_planner_rejects_historical_or_unsupported_composite_residue(message):
    assert nf.plan_native_facts(message) is None


def test_w1b_native_planner_supports_complete_hyphenated_return_clause():
    plan = nf.plan_native_facts("AAPL 3-month return and Stage")
    assert plan is not None
    assert plan.field_ids == ("market.return.3m", "stage.current")


@pytest.mark.parametrize(
    "message",
    [
        "1m return and one year return",
        "1m return for one year",
        "1m and 3m return over one year",
        "3-month return over the year",
        "AAPL 1m return and one year return",
        "AAPL 1m return for one year",
        "AAPL 1m and 3m return over one year",
        "AAPL 3-month return over the year",
    ],
)
def test_w1b_native_planner_rejects_mixed_registered_and_unbounded_return_horizons(message):
    assert nf.plan_native_facts(message, context={"symbol": "AAPL"}) is None


@pytest.mark.parametrize("unsupported", ["beta", "high", "open", "PE", "yield", "float"])
def test_w1b_native_planner_does_not_let_unsupported_field_hijack_ambient_entity(unsupported):
    assert nf.plan_native_facts(
        f"price and {unsupported}", {"symbol": "AAPL"}
    ) is None


@pytest.mark.parametrize(
    "unsupported", ["RSI", "MACD", "VWAP", "ATR", "LOW", "CLOSE", "DEBT", "CASH", "FCF", "ROE"],
)
def test_w1b_native_planner_request_prefix_does_not_turn_unknown_metric_into_ticker(unsupported):
    assert nf.plan_native_facts(
        f"Give me {unsupported} and price", {"symbol": "AAPL"}
    ) is None


class _NativeIdentity:
    def normalize_many(self, entities):
        entity = entities[0]
        if entity.symbol == "ZZZZZ":
            raise ValueError("unknown identity")
        if entity.type == "security":
            from engine.intelligence_workspace.contracts import CanonicalEntity
            return (CanonicalEntity(
                "security", "SEC:US-XNAS-" + (entity.symbol or "AAPL"), "us_equity",
                alias_interpretation="current_alias_only",
            ),)
        from engine.intelligence_workspace.contracts import CanonicalEntity
        return (CanonicalEntity("industry", entity.id, "us_industry"),)


def _native_envelope(field_id, entity, *, value=2, status="available", reason=None, unit="percent"):
    if status != "available":
        value = None
        reason = reason or ("rights_blocked" if status == "rights_blocked" else "owner_missing")
    return {
        "schema": "datapoint_value.v1", "registry_digest": "registry-digest", "field_id": field_id,
        "entity": entity, "value": value, "status": status, "reason_code": reason, "unit": unit,
        "observed_at": "2026-08-23", "effective_at": "2026-08-23", "as_of": "2026-08-23",
        "freshness": {"state": "stale" if status == "stale" else "fresh", "policy": "owner_native"},
        "quality": {"state": "ok", "issues": []},
        "source": {"source_id": "owner." + field_id, "owner": "owner", "license_class": "internal"},
        "provenance": {"kind": "owner_derived", "owner_field_key": field_id, "basis": "owner"},
        "audience": "subscriber", "consumer_uses": ["ai_fact"],
        "fact_fingerprint": "fp-" + field_id,
    }


class _NativeRuntime:
    class _Registry:
        digest = "registry-digest"

    registry = _Registry()

    def __init__(self, statuses=None, *, relationship=None, rank_raises=False):
        self.identity_normalizer = _NativeIdentity()
        self.calls = []
        self.statuses = statuses or {}
        self.relationship = relationship or _native_relationship()
        self.rank_raises = rank_raises

    def resolve_current_industry_relationship(self, entity):
        return self.relationship

    def resolve(self, request):
        self.calls.append(request)
        entity = request.entities[0]
        if entity.type == "industry" and self.rank_raises:
            raise RuntimeError("fixture industry resolver unavailable")
        canonical = {"type": entity.type, "id": entity.id or "SEC:US-XNAS-AAPL"}
        return tuple(
            _native_envelope(
                field_id, canonical, value=87.7 if field_id == "industry.rank.percentile" else 2,
                status=self.statuses.get(field_id, "available"),
                unit="stage_code" if field_id == "stage.current" else "percent",
            )
            for field_id in request.field_ids
        )


def _native_relationship(*, status="available", reason=None):
    available = status == "available"
    return {
        "schema": "intelligence_workspace.current_industry_relationship.v1",
        "registry_digest": "registry-digest",
        "relationship": "security.current_industry",
        "from": {"type": "security", "id": "SEC:US-XNAS-AAPL"},
        "to": (
            {"type": "industry", "id": "Technology Hardware", "universe": "us_industry"}
            if available else None
        ),
        "status": status,
        "reason_code": reason,
        "observed_at": "2026-08-23",
        "effective_at": "2026-08-23",
        "as_of": "2026-08-23",
        "freshness": {
            "state": "fresh" if available else ("stale" if status == "stale" else "unknown"),
            "policy": "owner_native",
        },
        "quality": {"state": "ok" if available else "degraded", "issues": []},
        "source": {
            "source_id": "stage_analysis.screener", "owner": "stage_analysis",
            "license_class": "internal_derived", "dataset_id": None,
        },
        "provenance": {
            "kind": "owner_relationship", "owner_field_key": "current_industry",
            "relationship": "security.current_industry",
            "basis": "owner_published_current_relationship",
        },
        "audience": "subscriber",
        "consumer_use": "ai_fact",
        "relationship_fingerprint": "relationship-fingerprint",
    }


def test_w1b_executor_partitions_industry_rank_and_preserves_direct_fingerprints(tmp_path):
    runtime = _NativeRuntime()
    plan = nf.plan_native_facts("AAPL Stage, industry rank and within-industry member RS percentile")
    result = nf.execute_native_fact_plan(plan, runtime=runtime, repo_root=tmp_path)
    assert [call.entities[0].type for call in runtime.calls] == ["security", "industry"]
    assert runtime.calls[0].field_ids == ("stage.current", "security.industry_member.rs_percentile")
    assert runtime.calls[1].field_ids == ("industry.rank.percentile",)
    receipt = result.receipt
    assert receipt["route"] == "instant/native-fact"
    assert receipt["relationship_receipt"]["to"]["id"] == "Technology Hardware"
    assert receipt["relationship_receipt"]["from"] == {
        "type": "security", "id": "SEC:US-XNAS-AAPL",
    }
    assert [fact["fact_fingerprint"] for fact in receipt["facts"]] == [
        "fp-stage.current", "fp-industry.rank.percentile", "fp-security.industry_member.rs_percentile",
    ]
    # A hostile rank/member swap changes both field and entity request and cannot pass.
    assert "industry rank percentile: 87.7%" in result.answer
    assert "within-industry member RS percentile: 2%" in result.answer
    assert [clause["fact_fingerprint"] for clause in result.clauses] == [
        "fp-stage.current", "fp-industry.rank.percentile", "fp-security.industry_member.rs_percentile",
    ]
    assert [fact["clause_id"] for fact in receipt["facts"]] == ["c1", "c2", "c3"]
    assert [fact["display_order"] for fact in receipt["facts"]] == [0, 1, 2]


def test_w1b_real_w1a_runtime_preserves_direct_parity_and_dynamic_theme_denial():
    from engine.intelligence_workspace.consumers import PARITY_KEYS
    from engine.intelligence_workspace.contracts import (
        EntityRequest,
        ResolutionRequest,
        RightsDecision,
    )
    from engine.intelligence_workspace.runtime import build_runtime

    repo_root = pathlib.Path(__file__).resolve().parents[1]
    runtime = build_runtime(repo_root=repo_root)
    direct_stage = runtime.resolve(ResolutionRequest(
        entities=(EntityRequest(type="security", symbol="AAPL", universe="us_equity"),),
        field_ids=("stage.current",),
        audience="subscriber",
        consumer_use="ai_fact",
    ))[0]
    stage_plan = nf.plan_native_facts("AAPL Stage")
    brain_stage = nf.execute_native_fact_plan(stage_plan, runtime=runtime, repo_root=repo_root)
    projected_stage = brain_stage.receipt["facts"][0]
    assert {key: projected_stage[key] for key in PARITY_KEYS} == {
        key: direct_stage[key] for key in PARITY_KEYS
    }

    runtime.rights_projector = lambda *_: RightsDecision(False)
    direct_theme = runtime.resolve(ResolutionRequest(
        entities=(EntityRequest(type="security", symbol="AAPL", universe="us_equity"),),
        field_ids=("theme.local.memberships",),
        audience="subscriber",
        consumer_use="ai_fact",
    ))[0]
    theme_plan = nf.plan_native_facts("AAPL direct local theme memberships")
    brain_theme = nf.execute_native_fact_plan(theme_plan, runtime=runtime, repo_root=repo_root)
    projected_theme = brain_theme.receipt["facts"][0]
    assert (direct_theme["status"], direct_theme["reason_code"], direct_theme["value"]) == (
        "rights_blocked", "rights_blocked", None,
    )
    assert {key: projected_theme[key] for key in PARITY_KEYS} == {
        key: direct_theme[key] for key in PARITY_KEYS
    }
    assert "rights_blocked" in brain_theme.answer
    assert all("owner_artifact" not in json.dumps(fact)
               for fact in brain_theme.receipt["facts"])


def test_w1b_executor_keeps_stale_missing_and_rights_blocked_honest(tmp_path):
    runtime = _NativeRuntime({
        "stage.current": "stale", "earnings.next_date": "unavailable", "theme.local.memberships": "rights_blocked",
    })
    plan = nf.plan_native_facts("AAPL Stage, next earnings date and direct local theme memberships")
    result = nf.execute_native_fact_plan(plan, runtime=runtime, repo_root=tmp_path)
    assert "Stage: stale (owner_missing)" in result.answer
    assert "next earnings date: unavailable (owner_missing)" in result.answer
    assert "direct local theme memberships: rights_blocked (rights_blocked)" in result.answer
    assert all(" 2" not in clause["text"] for clause in result.clauses)


def test_w1b_missing_industry_relationship_is_a_receipted_visible_stream_clause(tmp_path):
    runtime = _NativeRuntime(relationship=_native_relationship(
        status="unavailable", reason="owner_missing"))
    plan = nf.plan_native_facts("AAPL Stage and industry rank")
    result = nf.execute_native_fact_plan(plan, runtime=runtime, repo_root=tmp_path)
    assert len(result.clauses) == 2
    missing = result.clauses[1]
    assert missing == {
        "clause_id": "c2",
        "display_order": 1,
        "field_id": None,
        "requested_field_id": "industry.rank.percentile",
        "fact_fingerprint": None,
        "status": "unavailable",
        "receipt_kind": "owner_relationship",
        "receipt_reference": "relationship_receipt",
        "text": missing["text"],
    }
    assert missing["text"] in result.answer
    assert result.receipt["clauses"][1] == missing
    chunks = gw._native_fact_stream_chunks(result)
    assert "".join(chunks) == result.answer


@pytest.mark.parametrize(("schema", "current", "reason"), [
    ("hostile.lookalike.v1", True, "owner_degraded"),
    ("stage_screener.v1", False, "owner_stale"),
])
def test_w1b_industry_rank_fails_closed_on_invalid_or_stale_relationship(
        tmp_path, schema, current, reason):
    status = "stale" if not current else "unavailable"
    runtime = _NativeRuntime(relationship=_native_relationship(status=status, reason=reason))
    plan = nf.plan_native_facts("AAPL Stage and industry rank")
    result = nf.execute_native_fact_plan(plan, runtime=runtime, repo_root=tmp_path)
    assert [call.entities[0].type for call in runtime.calls] == ["security"]
    assert result.receipt["relationship_receipt"]["reason_code"] == reason
    assert "industry rank was not resolved" in result.answer
    assert all(fact["field_id"] != "industry.rank.percentile"
               for fact in result.receipt["facts"])


def test_w1b_industry_resolver_failure_preserves_resolved_security_fact(tmp_path):
    runtime = _NativeRuntime(rank_raises=True)
    plan = nf.plan_native_facts("AAPL Stage and industry rank")
    result = nf.execute_native_fact_plan(plan, runtime=runtime, repo_root=tmp_path)
    assert "Stage: 2" in result.answer
    assert "industry rank was not resolved" in result.answer
    assert [fact["field_id"] for fact in result.receipt["facts"]] == ["stage.current"]
    assert result.receipt["rank_resolution_failure"] == \
        "industry_rank_resolver_unavailable"


def test_w1b_executor_unknown_identity_fails_closed_without_fabricated_fact(tmp_path):
    plan = nf.plan_native_facts("ZZZZZ price")
    result = nf.execute_native_fact_plan(plan, runtime=_NativeRuntime(), repo_root=tmp_path)
    assert result.receipt["facts"] == []
    assert result.receipt["failure"]["reason_code"] == "identity_unavailable"
    assert "no fact was asserted" in result.answer


def _gateway_native_execution():
    fact = _native_envelope(
        "stage.current", {"type": "security", "id": "SEC:US-XNAS-INOD"},
        value=2, unit="stage_code",
    )
    fact.update({"clause_id": "c1", "display_order": 0})
    clause_text = (
        "Stage: 2 [stage.current; source=owner.stage.current; "
        "as_of=2026-08-23; freshness=fresh]"
    )
    receipt = {
        "schema": "brain.native_fact_receipt.v1",
        "route": "instant/native-fact",
        "planner_version": "w1b.native_fact_planner.v1",
        "registry_digest": "registry-digest",
        "canonical_entity": {"type": "security", "id": "SEC:US-XNAS-INOD"},
        "identity_admission": {
            "requested_symbol": "INOD", "alias_interpretation": "current_alias_only",
            "canonical_security_id": "SEC:US-XNAS-INOD",
        },
        "effective_context": {
            "symbol": "INOD", "explicit_entity": True,
            "reason": "explicit_entity_wins", "precedence_reason": "explicit_entity_wins",
            "ambient_symbol": "AAOI", "ambient_used": False,
        },
        "relationship_receipt": None,
        "facts": [fact],
        "cache": {"label": "request_scoped_no_value_cache", "hit": False},
        "timing": {
            "route_decision_ms": 1, "context_assembly_ms": 4,
            "registry_context_assembly_ms": 4, "render_ms": 1, "total_ms": 6,
        },
    }
    return nf.NativeFactExecution(
        answer=f"INOD — {clause_text}", receipt=receipt,
        clauses=({"clause_id": "c1", "field_id": "stage.current",
                  "fact_fingerprint": "fp-stage.current", "status": "available",
                  "text": clause_text},),
    )


def test_w1b_gateway_native_nonstream_needs_no_provider_and_persists_one_turn(tmp_path):
    plan = nf.plan_native_facts("INOD Stage", {"symbol": "AAOI"})
    appended: list[tuple[str, str, str]] = []
    with patch.object(gw, "_brain_quota_dir", return_value=tmp_path):
        with patch.object(gw, "_resolve_tier", return_value={
                "tier": "pro", "status": "active", "current_period_end": None}):
            with patch.object(gw._native_facts, "plan_native_facts", return_value=plan):
                with patch.object(gw._native_facts, "execute_native_fact_plan",
                                  return_value=_gateway_native_execution()):
                    with patch.object(gw, "_build_lane_providers",
                                      side_effect=AssertionError("provider must not be built")):
                        with patch.object(gw, "_ensure_thread", return_value="thread-native"):
                            with patch.object(
                                gw, "_append_message",
                                side_effect=lambda thread, role, text, **kw:
                                    appended.append((thread, role, text)),
                            ):
                                with patch("lib.ai_costs.record_usage",
                                           side_effect=AssertionError("no provider cost row")):
                                    result = gw.chat(
                                        "INOD Stage", "u_native", lane="fast", root=_root(),
                                        context={"symbol": "AAOI"},
                                    )
    assert result["route"] == "instant/native-fact"
    assert result["model"] == "native-fact.v1"
    assert result["reply"].startswith("INOD — Stage: 2")
    assert result["citations"] == ["owner.stage.current"]
    assert result["native_fact_receipt"]["facts"][0]["field_id"] == "stage.current"
    assert result["native_fact_receipt"]["effective_context"]["precedence_reason"] == \
        "explicit_entity_wins"
    assert result["usage"]["input_tokens"] == result["usage"]["output_tokens"] == 0
    assert result["latency"] == result["usage"]["latency"]
    assert [row[1] for row in appended] == ["user", "assistant"]


def test_w1b_gateway_native_stream_is_resumable_shape_and_first_delta_is_a_fact(tmp_path):
    plan = nf.plan_native_facts("INOD Stage", {"symbol": "AAOI"})
    with patch.object(gw, "_brain_quota_dir", return_value=tmp_path):
        with patch.object(gw, "_resolve_tier", return_value={
                "tier": "pro", "status": "active", "current_period_end": None}):
            with patch.object(gw._native_facts, "plan_native_facts", return_value=plan):
                with patch.object(gw._native_facts, "execute_native_fact_plan",
                                  return_value=_gateway_native_execution()):
                    with patch.object(gw, "_build_lane_providers",
                                      side_effect=AssertionError("provider must not be built")):
                        with patch.object(gw, "_ensure_thread", return_value=None):
                            events = _sse(list(gw.chat_stream(
                                "INOD Stage", "u_native_stream", lane="fast", root=_root(),
                                context={"symbol": "AAOI"},
                            )))
    # W1-C: context_receipt is now a first-class event, always right after meta.
    assert [event["type"] for event in events] == \
        ["meta", "context_receipt", "status", "delta", "done"]
    assert events[0]["model"] == "native-fact.v1"
    assert events[1]["schema"] == "ai_context_receipt.v1"
    assert "stage.current" in events[3]["text"]
    done = events[-1]
    assert done["route"] == "instant/native-fact"
    assert done["native_fact_receipt"]["facts"][0]["fact_fingerprint"] == \
        "fp-stage.current"
    assert done["context_receipt"]["schema"] == "ai_context_receipt.v1"
    latency = done["usage"]["latency"]
    assert latency["route"] == "instant/native-fact"
    assert isinstance(latency["ttfv_ms"], int)
    assert latency["context_assembly_ms"] == 4
    assert done["usage"]["input_tokens"] == done["usage"]["output_tokens"] == 0


def test_w1b_gateway_native_turns_each_consume_exactly_one_message_quota(tmp_path):
    plan = nf.plan_native_facts("INOD Stage")
    results = []
    with patch.object(gw, "_brain_quota_dir", return_value=tmp_path):
        with patch.object(gw, "_resolve_tier", return_value={
                "tier": "pro", "status": "active", "current_period_end": None}):
            with patch.object(gw._native_facts, "plan_native_facts", return_value=plan):
                with patch.object(gw._native_facts, "execute_native_fact_plan",
                                  return_value=_gateway_native_execution()):
                    with patch.object(gw, "_build_lane_providers",
                                      side_effect=AssertionError("provider must not be built")):
                        with patch.object(gw, "_ensure_thread", return_value=None):
                            for _ in range(2):
                                results.append(gw.chat(
                                    "INOD Stage", "u_native_quota", lane="fast", root=_root(),
                                ))
    assert results[1]["quota"]["remaining"] == results[0]["quota"]["remaining"] - 1


def test_w1b_native_stream_disconnect_resume_replays_tail_without_second_quota(tmp_path):
    from app import brain_runs

    brain_runs.reset_for_tests()
    plan = nf.plan_native_facts("INOD Stage")
    quota_calls = 0

    def _quota(*args, **kwargs):
        nonlocal quota_calls
        quota_calls += 1
        return True, {"lane": "fast", "remaining": 9, "limit": 10, "period": "fixture"}

    try:
        with patch.object(gw, "_resolve_tier", return_value={
                "tier": "pro", "status": "active", "current_period_end": None}):
            with patch.object(gw, "_check_and_increment_quota", side_effect=_quota):
                with patch.object(gw._native_facts, "plan_native_facts", return_value=plan):
                    with patch.object(gw._native_facts, "execute_native_fact_plan",
                                      return_value=_gateway_native_execution()):
                        with patch.object(gw, "_build_lane_providers",
                                          side_effect=AssertionError("provider must not be built")):
                            with patch.object(gw, "_ensure_thread", return_value=None):
                                with patch.object(gw, "_log_brain_response"):
                                    run = brain_runs.start(
                                        gw.chat_stream(
                                            "INOD Stage", "u_native_resume", lane="fast",
                                            root=_root(),
                                        ),
                                        user_id="u_native_resume",
                                    )
                                    first = brain_runs.follow(run, interval=0.05)
                                    # W1-C: context_receipt is now a first-class event,
                                    # always right after meta — one more event to drain
                                    # before the disconnect.
                                    received = [next(first), next(first), next(first), next(first)]
                                    first.close()
                                    tail = list(brain_runs.follow(
                                        run, cursor=4, interval=0.05,
                                    ))
        first_events = [json.loads(chunk[5:].strip()) for chunk in received]
        tail_events = [json.loads(chunk[5:].strip()) for chunk in tail
                       if chunk.startswith("data:")]
        assert [event["type"] for event in first_events] == \
            ["meta", "context_receipt", "status", "delta"]
        assert [event["type"] for event in tail_events] == ["done"]
        assert first_events[3]["text"].startswith("INOD — Stage: 2")
        assert tail_events[0]["native_fact_receipt"]["facts"][0]["field_id"] == \
            "stage.current"
        assert quota_calls == 1
    finally:
        brain_runs.reset_for_tests()


def test_w1b_simple_price_with_receipt_instructions_still_plans_native():
    plan = nf.plan_native_facts(
        "What is AAPL's current price? One sentence, with the source and the exact as-of."
    )
    assert plan is not None
    assert plan.symbol == "AAPL"
    assert plan.field_ids == ("market.price.last",)


# ---------------------------------------------------------------------------
# W1-C: context_receipt — guest/authenticated stream+chat parity (12, 13),
# resume replay with the original revision (14), five-fact parity through an
# explicit ai_context envelope (16), and deep-route receipt carriage (17).
# See research/DEEPVUE_W1C_CONTEXT_ENVELOPE_CONTRACT_2026-08-25.md.
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("is_guest", [False, True])
def test_w1c_native_stream_emits_context_receipt_for_guest_and_authenticated(tmp_path, is_guest):
    """12+13: both guest and authenticated stream turns carry a context_receipt
    right after meta, and quota/thread behavior is exactly what it always was —
    guest is stateless, authenticated persists one user+assistant turn."""
    plan = nf.plan_native_facts("INOD Stage", {"symbol": "AAOI"})
    appended: list[tuple[str, str]] = []
    quota_calls = 0

    def _quota(*args, **kwargs):
        nonlocal quota_calls
        quota_calls += 1
        return True, {"lane": "fast", "remaining": 9, "limit": 10, "period": "fixture"}

    with patch.object(gw, "_resolve_tier", return_value={
            "tier": "pro", "status": "active", "current_period_end": None}):
        with patch.object(gw, "_check_and_increment_quota", side_effect=_quota):
            with patch.object(gw, "_check_and_increment_guest_quota", side_effect=_quota):
                with patch.object(gw._native_facts, "plan_native_facts", return_value=plan):
                    with patch.object(gw._native_facts, "execute_native_fact_plan",
                                      return_value=_gateway_native_execution()):
                        with patch.object(gw, "_build_lane_providers",
                                          side_effect=AssertionError("provider must not be built")):
                            with patch.object(gw, "_ensure_thread", return_value="thread-1"):
                                with patch.object(
                                    gw, "_append_message",
                                    side_effect=lambda thread, role, text, **kw:
                                        appended.append((thread, role)),
                                ):
                                    events = _sse(list(gw.chat_stream(
                                        "INOD Stage", "u_ctx_guest_vs_auth", lane="fast",
                                        root=_root(), context={"symbol": "AAOI"},
                                        is_guest=is_guest, guest_aid="gaid", guest_ip="gip",
                                    )))
    assert [e["type"] for e in events] == ["meta", "context_receipt", "status", "delta", "done"]
    receipt_event = events[1]
    assert receipt_event["schema"] == "ai_context_receipt.v1"
    assert receipt_event["effective_context"]["source"] == "explicit"
    done = events[-1]
    assert done["context_receipt"]["schema"] == "ai_context_receipt.v1"
    assert quota_calls == 1
    if is_guest:
        # Guests are stateless: no thread row, nothing appended.
        assert appended == []
        assert events[0]["thread_id"] is None
    else:
        assert [row[1] for row in appended] == ["user", "assistant"]
        assert events[0]["thread_id"] == "thread-1"


@pytest.mark.parametrize("is_guest", [False, True])
def test_w1c_native_chat_response_carries_context_receipt_for_guest_and_authenticated(
        tmp_path, is_guest):
    """Same as above for the non-streaming chat() response shape."""
    plan = nf.plan_native_facts("INOD Stage", {"symbol": "AAOI"})

    def _quota(*args, **kwargs):
        return True, {"lane": "fast", "remaining": 9, "limit": 10, "period": "fixture"}

    with patch.object(gw, "_resolve_tier", return_value={
            "tier": "pro", "status": "active", "current_period_end": None}):
        with patch.object(gw, "_check_and_increment_quota", side_effect=_quota):
            with patch.object(gw, "_check_and_increment_guest_quota", side_effect=_quota):
                with patch.object(gw._native_facts, "plan_native_facts", return_value=plan):
                    with patch.object(gw._native_facts, "execute_native_fact_plan",
                                      return_value=_gateway_native_execution()):
                        with patch.object(gw, "_build_lane_providers",
                                          side_effect=AssertionError("provider must not be built")):
                            with patch.object(gw, "_ensure_thread", return_value="thread-1"):
                                with patch.object(gw, "_append_message"):
                                    result = gw.chat(
                                        "INOD Stage", "u_ctx_chat", lane="fast", root=_root(),
                                        context={"symbol": "AAOI"},
                                        is_guest=is_guest, guest_aid="gaid", guest_ip="gip",
                                    )
    assert result["context_receipt"]["schema"] == "ai_context_receipt.v1"
    assert result["context_receipt"]["effective_context"]["source"] == "explicit"
    assert result["thread_id"] == (None if is_guest else "thread-1")


def test_w1c_resumed_run_replays_context_receipt_with_its_original_revision(tmp_path):
    """14: the run buffer persists whatever chat_stream() yielded, so a resumed
    reader sees the SAME context_receipt (same revision) the live client saw —
    never a recompiled one against moved UI state."""
    from app import brain_runs

    brain_runs.reset_for_tests()
    ai_context = {
        "schema": "ai_context_client.v1", "origin_id": "mount-resume", "context_revision": 7,
        "captured_at": "2026-08-25T19:59:00Z", "pinned": [], "active": None,
        "ambient": {"symbol": None, "timeframe": "1D", "page": "terminal", "panel": None},
    }
    plan = nf.plan_native_facts("INOD Stage", {"ai_context": ai_context})

    def _quota(*args, **kwargs):
        return True, {"lane": "fast", "remaining": 9, "limit": 10, "period": "fixture"}

    try:
        with patch.object(gw, "_resolve_tier", return_value={
                "tier": "pro", "status": "active", "current_period_end": None}):
            with patch.object(gw, "_check_and_increment_quota", side_effect=_quota):
                with patch.object(gw._native_facts, "plan_native_facts", return_value=plan):
                    with patch.object(gw._native_facts, "execute_native_fact_plan",
                                      return_value=_gateway_native_execution()):
                        with patch.object(gw, "_build_lane_providers",
                                          side_effect=AssertionError("provider must not be built")):
                            with patch.object(gw, "_ensure_thread", return_value=None):
                                with patch.object(gw, "_log_brain_response"):
                                    run = brain_runs.start(
                                        gw.chat_stream(
                                            "INOD Stage", "u_ctx_resume", lane="fast",
                                            root=_root(), context={"ai_context": ai_context},
                                        ),
                                        user_id="u_ctx_resume",
                                    )
                                    # Let the run finish, then resume from a cold cursor —
                                    # the exact "I left and came back" path.
                                    all_events = list(brain_runs.follow(run, interval=0.05))
        resumed = list(brain_runs.follow(run, cursor=0, interval=0.05))
        parsed_live = [json.loads(c[5:].strip()) for c in all_events if c.startswith("data:")]
        parsed_resumed = [json.loads(c[5:].strip()) for c in resumed if c.startswith("data:")]
        assert parsed_live == parsed_resumed
        receipt = next(e for e in parsed_resumed if e["type"] == "context_receipt")
        assert receipt["origin"]["origin_id"] == "mount-resume"
        assert receipt["origin"]["context_revision"] == 7
    finally:
        brain_runs.reset_for_tests()


def test_w1c_five_fact_parity_through_explicit_context_envelope():
    """16: for the five frozen parity fields, identity/value/status/as_of/
    fingerprint are identical between (a) a direct resolver.resolve() call and
    (b) the brain packet facts produced under an EXPLICIT-context request whose
    single entity was resolved through a compiled W1-C envelope — extends the
    existing W1-B direct-parity idiom (test_w1b_real_w1a_runtime_preserves_
    direct_parity_and_dynamic_theme_denial) across the full frozen set."""
    from engine.intelligence_workspace.consumers import PARITY_KEYS
    from engine.intelligence_workspace.contracts import EntityRequest, ResolutionRequest
    from engine.intelligence_workspace.runtime import build_runtime

    repo_root = pathlib.Path(__file__).resolve().parents[1]
    runtime = build_runtime(repo_root=repo_root)

    message = ("AAPL price, Stage, industry rank, within-industry member RS percentile "
               "and next earnings date")
    now = datetime(2026, 8, 25, 20, 0, 0, tzinfo=timezone.utc)
    envelope = cc.compile_envelope(message, {}, now=now, request_id="parity-r1")
    assert envelope["effective_context"]["source"] == "explicit"
    assert envelope["effective_context"]["entities"] == [{"type": "security", "id": "AAPL"}]

    plan = nf.plan_native_facts(message, envelope=envelope)
    assert plan is not None
    brain = nf.execute_native_fact_plan(plan, runtime=runtime, repo_root=repo_root)
    brain_facts = {fact["field_id"]: fact for fact in brain.receipt["facts"]}

    canonical = runtime.identity_normalizer.normalize_many(
        (EntityRequest(type="security", symbol="AAPL", universe="us_equity"),)
    )[0]

    direct_by_field: dict[str, dict] = {}
    security_fields = [
        "market.price.last", "stage.current", "security.industry_member.rs_percentile",
        "earnings.next_date",
    ]
    for envelope_fact in runtime.resolve(ResolutionRequest(
        entities=(EntityRequest(type="security", id=canonical.id, universe="us_equity"),),
        field_ids=tuple(security_fields), audience="subscriber", consumer_use="ai_fact",
    )):
        direct_by_field[envelope_fact["field_id"]] = envelope_fact

    relationship = runtime.resolve_current_industry_relationship(canonical)
    industry_target = relationship.get("to") if isinstance(relationship, dict) else None
    if industry_target and industry_target.get("id"):
        for envelope_fact in runtime.resolve(ResolutionRequest(
            entities=(EntityRequest(type="industry", id=industry_target["id"],
                                     universe="us_industry"),),
            field_ids=("industry.rank.percentile",), audience="subscriber",
            consumer_use="ai_fact",
        )):
            direct_by_field[envelope_fact["field_id"]] = envelope_fact

    checked = 0
    for field_id, direct_fact in direct_by_field.items():
        brain_fact = brain_facts.get(field_id)
        if brain_fact is None:
            continue  # an honestly-unavailable field carries no typed envelope either side
        assert {key: brain_fact[key] for key in PARITY_KEYS} == \
            {key: direct_fact[key] for key in PARITY_KEYS}
        checked += 1
    assert checked >= 1, "at least one frozen field must be directly comparable"


def test_w1c_deep_route_request_keeps_legacy_context_byte_identical_and_carries_receipt():
    """17: an unsupported-wording (analytical) request still deep-routes, and the
    deep loop receives the EXACT legacy `context` dict it has always seen —
    same keys/values, nothing added, nothing rewritten.

    NB-6 docstring correction (review repair): `_run_brain_loop_stream` is
    replaced here by `_spy_loop`, which re-implements the SSE yields itself —
    so this test does NOT prove the real internal event ordering inside that
    generator (meta -> context_receipt -> status/tool -> delta -> done); that
    ordering is proven against the REAL function by
    test_brain_gateway.py::test_status_event_sequence_two_round_tool_turn
    (lines ~4814-4820 there, driven through the real `chat_stream()` ->
    `_run_brain_loop_stream` path via `_stream_events()`). What THIS test
    proves is narrower and still real: `chat_stream()` computes the envelope/
    receipt and threads `context_receipt=` into the loop call, and the deep
    lane's legacy `context` dict argument is byte-identical to what a caller
    passed in — the receipt is additive, never a prompt-construction change."""
    seen_contexts: list[dict] = []

    def _spy_loop(message, lane, history, context, root_, tdd, thu, client, model, max_t, tb,
                  meta_event, usage_out=None, answer_out=None, thinking_out=None,
                  mode="chat", image_blocks=None, providers=None, user_id="", user_email="",
                  effort=None, thinking_mode=None, deepseek_thinking=None, context_receipt=None):
        seen_contexts.append(dict(context))
        yield f"data: {json.dumps(meta_event)}\n\n"
        if context_receipt is not None:
            yield "data: " + json.dumps({"type": "context_receipt", **context_receipt}) + "\n\n"
        yield f"data: {json.dumps({'type': 'delta', 'text': 'Deep loop answer.'})}\n\n"
        yield "data: " + json.dumps({"type": "done", "citations": [], "usage": {}}) + "\n\n"
        if answer_out is not None:
            answer_out.append("Deep loop answer.")

    message = "Should I buy AAPL? What's your outlook and price target?"
    raw_context = {"symbol": "AAOI", "page": "terminal"}
    with patch.object(gw, "_brain_quota_dir", return_value=pathlib.Path(tempfile.mkdtemp())):
        with patch.object(gw, "_resolve_tier", return_value={
                "tier": "pro", "status": "active", "current_period_end": None}):
            with patch.object(gw, "_build_lane_providers",
                              return_value=[{"client": _Client(), "model": "deepseek-v4-flash"}]):
                with patch.object(gw, "_ensure_thread", return_value=None):
                    with patch.object(gw, "_run_brain_loop_stream", side_effect=_spy_loop):
                        events = _sse(list(gw.chat_stream(
                            message, "u_ctx_deep", lane="fast", root=_root(),
                            context=dict(raw_context),
                        )))
    assert [e["type"] for e in events] == ["meta", "context_receipt", "delta", "done"]
    assert seen_contexts, "the deep loop must have been invoked"
    # The legacy context dict the deep prompt path sees is untouched by W1-C —
    # same keys/values it always carried (plus nothing new).
    assert seen_contexts[0] == raw_context
    assert events[1]["schema"] == "ai_context_receipt.v1"
    assert events[1]["effective_context"]["source"] == "active"
    assert events[1]["effective_context"]["entities"] == [{"type": "security", "id": "AAOI"}]
