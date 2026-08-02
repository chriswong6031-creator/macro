"""Tool-loop economics for the Mastermind brain gateway (Analyst OS W5, contract T).

What this suite pins — all offline, no model, no network:

  1. PARALLEL ROUNDS. A round with >1 tool_use block runs its handlers concurrently,
     and the results still land in BLOCK order no matter what order they finish in.
     The order test is mutation-resistant: it asserts the completion order was actually
     REVERSED, so a silently sequential implementation fails it instead of passing by
     accident.
  2. ERROR ISOLATION. A handler that RAISES yields its own error payload; its siblings
     still return. (Before this contract an uncaught handler exception propagated out of
     the round's for-loop and killed the whole turn.)
  3. INLINE-ONLY DENYLIST. The Supabase write and the chart command/state tools never
     run on a worker thread.
  4. SVG FENCE. render_inline_chart's model-visible tool_result is a compact stub with
     NO svg key, while the client-bound `chart` event / chat() `charts` list keep the
     whole picture. Both loops.
  5. MESSAGES CACHE BREAKPOINT. Exactly one ephemeral breakpoint, on the last content
     block of the last message of the initial per-turn array — and the tool_result
     messages appended in later rounds carry none.
  6. LEDGER TTL CACHE. Two earnings-ledger reads inside the TTL parse the file once; a
     changed file invalidates immediately.
  7. ONE-BATCH NUDGE. The seed plan line asks for independent reads in one batch, and
     stays ONE line so the seed-router suite's line parsing still holds.
"""
from __future__ import annotations

import copy
import json
import pathlib
import sys
import tempfile
import threading
import time
from unittest.mock import patch

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from engine.chronicle import earnings_calls as ec  # noqa: E402
from engine.neuralweb import brain_gateway as gw  # noqa: E402
from tests.test_brain_gateway import _ScriptedStreamCtx  # noqa: E402

_ANSWER = ("Steady tape, nothing forcing a move. "
           "is_context_only: true — all signals are display-tier pending FDR.")


# ---------------------------------------------------------------------------
# Stubs
# ---------------------------------------------------------------------------

class _Block:
    def __init__(self, type_: str, text: str = "", name: str = "",
                 input_: dict | None = None, id_: str = "t1"):
        self.type = type_
        self.text = text
        self.name = name
        self.input = input_ or {}
        self.id = id_


class _Usage:
    input_tokens = 11
    output_tokens = 22


class _Resp:
    def __init__(self, content: list, stop_reason: str = "end_turn"):
        self.content = content
        self.stop_reason = stop_reason
        self.usage = _Usage()


class _StreamCtx:
    def __init__(self, text: str):
        self._text = text

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    @property
    def text_stream(self):
        yield self._text

    def get_final_message(self):
        return _Resp([_Block("text", self._text)], "end_turn")


class _CaptureClient:
    """Scripted model responses; every call's kwargs captured as a DEEP COPY.

    The deep copy is load-bearing: the loop keeps appending to the same `messages`
    list, so a stored reference would show every round the FINAL array.

    Both surfaces read the same script. `create()` serves the non-streaming loop;
    `stream()` serves the streaming one, where (W5.1) the Phase-1 ROUNDS stream too —
    `tools` in the kwargs is what separates a round from Phase-2 synthesis, exactly as
    it does in the gateway.
    """

    def __init__(self, responses: list | None = None, answer: str = _ANSWER):
        self._responses = list(responses or [])
        self._i = 0
        self._answer = answer
        self.create_kwargs: list[dict] = []
        self.stream_kwargs: list[dict] = []
        self.messages = self

    def _scripted(self):
        if self._i >= len(self._responses):
            return _Resp([_Block("text", self._answer)], "end_turn")
        resp = self._responses[self._i]
        self._i += 1
        return resp

    def create(self, **kwargs):
        self.create_kwargs.append(copy.deepcopy(kwargs))
        return self._scripted()

    def stream(self, **kwargs):
        self.stream_kwargs.append(copy.deepcopy(kwargs))
        if "tools" in kwargs:          # a Phase-1 round (W5.1 streams these too)
            return _ScriptedStreamCtx(self._scripted())
        return _StreamCtx(self._answer)


def _root() -> pathlib.Path:
    d = pathlib.Path(tempfile.mkdtemp())
    nw = d / "data" / "neuralweb"
    nw.mkdir(parents=True, exist_ok=True)
    (nw / "world_state.json").write_text(json.dumps({"verdict": "RISK_OFF", "score": 34}))
    return d


def _tool_block(name: str, idx: int, params: dict | None = None) -> _Block:
    return _Block("tool_use", name=name, input_=params or {}, id_=f"tid{idx}")


@pytest.fixture
def quiet_grounding():
    """Keep the per-turn grounding digests out of the way — these tests are about the
    tool round and the messages array, not about what the packet says."""
    with patch.object(gw, "_grounding_digest", return_value=""):
        with patch.object(gw, "_symbol_grounding_digest", return_value=""):
            with patch.object(gw, "_compact_earnings_call_context", return_value={}):
                yield


def _drive_loop(root: pathlib.Path, client: _CaptureClient, message: str = "what now",
                **kwargs) -> tuple:
    return gw._run_brain_loop(
        message, "fast", [], {}, root, root / "terminal", "http://localhost:3100",
        client, "deepseek-v4-pro", 1000, 5, **kwargs,
    )


def _drive_stream(root: pathlib.Path, client: _CaptureClient,
                  message: str = "what now", **kwargs) -> list[dict]:
    events = list(gw._run_brain_loop_stream(
        message, "fast", [], {}, root, root / "terminal", "http://localhost:3100",
        client, "deepseek-v4-pro", 1000, 5, {"type": "meta"}, **kwargs,
    ))
    return [json.loads(e[6:]) for e in events if e.startswith("data: ")]


# ---------------------------------------------------------------------------
# 1. Parallel execution — order preservation
# ---------------------------------------------------------------------------

def test_round_results_keep_block_order_despite_reversed_completion():
    """Three tools whose sleeps make them finish in REVERSE block order still produce
    results indexed by block position."""
    completed: list[str] = []
    lock = threading.Lock()
    naps = {"slow": 0.18, "medium": 0.09, "fast": 0.0}

    def _dispatch(name: str, _params: dict) -> dict:
        time.sleep(naps[name])
        with lock:
            completed.append(name)
        return {"tool": name}

    blocks = [_tool_block(n, i) for i, n in enumerate(("slow", "medium", "fast"))]
    results = gw._run_tool_blocks(blocks, lambda b: gw._run_tool_block(b, _dispatch))

    assert [r["tool"] for r in results] == ["slow", "medium", "fast"]
    # Mutation guard: if this ran sequentially the completion order would equal the
    # block order and the assertion above would be vacuous.
    assert completed == ["fast", "medium", "slow"], (
        f"tools did not finish out of order — parallelism not exercised: {completed}")


def test_round_results_land_in_block_order_in_the_tool_result_messages(quiet_grounding):
    """End to end through the non-stream loop: the tool_result blocks the model reads
    are in tool_use block order, and each is paired to its own tool_use id."""
    naps = {"a_slow": 0.15, "b_medium": 0.07, "c_fast": 0.0}

    def _dispatch(name, _params, *_a, **_kw):
        time.sleep(naps[name])
        return {"tool": name}

    blocks = [_tool_block(n, i) for i, n in enumerate(("a_slow", "b_medium", "c_fast"))]
    client = _CaptureClient([_Resp(blocks, "tool_use")])

    with patch.object(gw, "_dispatch_brain_tool", side_effect=_dispatch):
        _answer, _cit, _ann, messages, _usage, _cmd, _charts = _drive_loop(_root(), client)

    results = [m for m in messages
               if m.get("role") == "user" and isinstance(m.get("content"), list)
               and m["content"] and m["content"][0].get("type") == "tool_result"][0]["content"]
    assert [r["tool_use_id"] for r in results] == ["tid0", "tid1", "tid2"]
    assert [json.loads(r["content"])["tool"] for r in results] == [
        "a_slow", "b_medium", "c_fast"]


def test_parallel_round_overlaps_in_wall_clock():
    """Three 0.15s tools must finish in well under the 0.45s a sequential round costs."""
    def _dispatch(_name: str, _params: dict) -> dict:
        time.sleep(0.15)
        return {"ok": True}

    blocks = [_tool_block(f"read_{i}", i) for i in range(3)]
    t0 = time.monotonic()
    gw._run_tool_blocks(blocks, lambda b: gw._run_tool_block(b, _dispatch))
    elapsed = time.monotonic() - t0
    assert elapsed < 0.35, f"round took {elapsed:.2f}s — reads did not overlap"


def test_single_tool_round_never_builds_an_executor():
    """One block = one inline call. An executor for a single sub-100ms read is pure
    overhead, so constructing one is a defect this test fails on."""
    def _boom(*_a, **_kw):
        raise AssertionError("ThreadPoolExecutor built for a single-tool round")

    with patch.object(gw, "ThreadPoolExecutor", _boom):
        results = gw._run_tool_blocks(
            [_tool_block("get_movers", 0)],
            lambda b: gw._run_tool_block(b, lambda n, _p: {"tool": n}),
        )
    assert results == [{"tool": "get_movers"}]


def test_empty_round_returns_empty():
    assert gw._run_tool_blocks([], lambda b: {"never": True}) == []


# ---------------------------------------------------------------------------
# 2. Error isolation
# ---------------------------------------------------------------------------

def test_one_raising_tool_does_not_kill_its_siblings():
    def _dispatch(name: str, _params: dict) -> dict:
        if name == "explodes":
            raise RuntimeError("handler on fire")
        return {"tool": name}

    blocks = [_tool_block(n, i) for i, n in enumerate(("ok_one", "explodes", "ok_two"))]
    results = gw._run_tool_blocks(blocks, lambda b: gw._run_tool_block(b, _dispatch))

    assert results[0] == {"tool": "ok_one"}
    assert results[2] == {"tool": "ok_two"}
    assert "explodes" in results[1]["error"]
    assert "handler on fire" in results[1]["error"]


def test_a_raising_tool_in_a_single_tool_round_also_returns_an_error(quiet_grounding):
    """Batch size must not decide whether a broken tool costs one result or the turn —
    the inline path carries the same catch-all as the threaded one."""
    def _dispatch(*_a, **_kw):
        raise ValueError("nope")

    client = _CaptureClient([_Resp([_tool_block("get_movers", 0)], "tool_use")])
    with patch.object(gw, "_dispatch_brain_tool", side_effect=_dispatch):
        answer, _cit, _ann, messages, _usage, _cmd, _charts = _drive_loop(_root(), client)

    assert answer, "a broken tool must not empty the answer"
    payloads = [json.loads(b["content"])
                for m in messages if isinstance(m.get("content"), list)
                for b in m["content"]
                if isinstance(b, dict) and b.get("type") == "tool_result"]
    assert payloads and "nope" in payloads[0]["error"]


def test_a_deep_handler_exception_is_contained_with_its_type_named():
    """Anything under Exception — including the import/attribute failures a lazy-import
    handler can throw on a worker thread — becomes that tool's result."""
    def _dispatch(name: str, _params: dict) -> dict:
        if name == "explodes":
            raise ImportError("No module named 'pandas'")
        return {"tool": name}

    blocks = [_tool_block(n, i) for i, n in enumerate(("ok_one", "explodes", "ok_two"))]
    results = gw._run_tool_blocks(blocks, lambda b: gw._run_tool_block(b, _dispatch))
    assert results[0] == {"tool": "ok_one"}
    assert "ImportError" in results[1]["error"]
    assert results[2] == {"tool": "ok_two"}


def test_an_interpreter_level_baseexception_still_unwinds():
    """Deliberate boundary: KeyboardInterrupt/SystemExit are not tool failures and must
    NOT be swallowed into a tool result — a Ctrl-C has to keep working."""
    def _dispatch(name: str, _params: dict) -> dict:
        if name == "explodes":
            raise KeyboardInterrupt
        return {"tool": name}

    blocks = [_tool_block(n, i) for i, n in enumerate(("ok_one", "explodes", "ok_two"))]
    with pytest.raises(KeyboardInterrupt):
        gw._run_tool_blocks(blocks, lambda b: gw._run_tool_block(b, _dispatch))


# ---------------------------------------------------------------------------
# 3. Inline-only denylist
# ---------------------------------------------------------------------------

def test_denylist_covers_the_write_and_the_chart_command_bus():
    assert "set_chat_preference" in gw._INLINE_ONLY_TOOLS
    assert "read_chart_state" in gw._INLINE_ONLY_TOOLS
    assert gw._CHART_COMMAND_TOOLS <= gw._INLINE_ONLY_TOOLS


def test_denylisted_tools_run_on_the_calling_thread():
    """The Supabase write stays on this thread while the parallel-safe reads move off it."""
    threads: dict[str, str] = {}
    lock = threading.Lock()

    def _dispatch(name: str, _params: dict) -> dict:
        with lock:
            threads[name] = threading.current_thread().name
        return {"tool": name}

    here = threading.current_thread().name
    blocks = [_tool_block(n, i) for i, n in enumerate(
        ("set_chat_preference", "get_movers", "get_house_view"))]
    results = gw._run_tool_blocks(blocks, lambda b: gw._run_tool_block(b, _dispatch))

    assert [r["tool"] for r in results] == [
        "set_chat_preference", "get_movers", "get_house_view"]
    assert threads["set_chat_preference"] == here
    assert threads["get_movers"] != here
    assert threads["get_house_view"] != here


def test_an_all_denylisted_round_never_builds_an_executor():
    def _boom(*_a, **_kw):
        raise AssertionError("ThreadPoolExecutor built for an all-inline round")

    blocks = [_tool_block("set_chart_symbol", 0), _tool_block("emit_chart_command", 1)]
    with patch.object(gw, "ThreadPoolExecutor", _boom):
        results = gw._run_tool_blocks(
            blocks, lambda b: gw._run_tool_block(b, lambda n, _p: {"tool": n}))
    assert [r["tool"] for r in results] == ["set_chart_symbol", "emit_chart_command"]


def test_worker_count_is_capped():
    assert gw._TOOL_PARALLEL_MAX_WORKERS == 6

    seen: list[int] = []
    real = gw.ThreadPoolExecutor

    def _spy(max_workers=None, **kw):
        seen.append(max_workers)
        return real(max_workers=max_workers, **kw)

    blocks = [_tool_block(f"read_{i}", i) for i in range(9)]
    with patch.object(gw, "ThreadPoolExecutor", _spy):
        gw._run_tool_blocks(blocks, lambda b: gw._run_tool_block(b, lambda n, _p: {"t": n}))
    assert seen == [6]


# ---------------------------------------------------------------------------
# 4. SVG fence
# ---------------------------------------------------------------------------

_FAKE_SVG = "<svg>" + ("x" * 4000) + "</svg>"


def test_chart_stub_shape_and_no_svg():
    result = {"client_executed": True, "type": "chart", "ticker": "NVDA",
              "timeframe": "DAILY", "svg": _FAKE_SVG}
    stub = gw._model_visible_tool_result("render_inline_chart", result)
    assert "svg" not in stub
    assert stub["ok"] is True
    assert stub["rendered"] is True
    assert stub["ticker"] == "NVDA"
    assert stub["timeframe"] == "DAILY"
    assert "do not describe" in stub["note"]
    # The original result is untouched — the collectors still read the whole picture.
    assert result["svg"] == _FAKE_SVG


def test_chart_stub_keeps_the_unavailable_signal():
    result = {"client_executed": True, "type": "chart", "ticker": "XYZ",
              "timeframe": "DAILY", "svg": "", "note": "chart unavailable for XYZ"}
    stub = gw._model_visible_tool_result("render_inline_chart", result)
    assert stub["rendered"] is False
    assert "unavailable" in stub["note"]
    assert "svg" not in stub


def test_chart_stub_carries_a_small_numeric_summary_through():
    """A future handler that computes a small summary alongside the picture must not
    lose it behind the fence."""
    result = {"client_executed": True, "type": "chart", "ticker": "NVDA",
              "timeframe": "DAILY", "svg": _FAKE_SVG, "last_close": 123.45, "bars": 90}
    stub = gw._model_visible_tool_result("render_inline_chart", result)
    assert stub["last_close"] == 123.45
    assert stub["bars"] == 90


def test_chart_tool_error_passes_through_unfenced():
    err = {"error": "symbol required"}
    assert gw._model_visible_tool_result("render_inline_chart", err) is err


def test_non_chart_tools_are_never_rewritten():
    payload = {"rows": [1, 2, 3]}
    assert gw._model_visible_tool_result("get_movers", payload) is payload


def test_non_stream_loop_fences_the_svg_but_keeps_the_charts_payload(quiet_grounding):
    blocks = [_tool_block("render_inline_chart", 0, {"symbol": "TSLA"})]
    client = _CaptureClient([_Resp(blocks, "tool_use")])

    def _dispatch(name, _params, *_a, **_kw):
        return {"client_executed": True, "type": "chart", "ticker": "TSLA",
                "timeframe": "DAILY", "svg": _FAKE_SVG}

    with patch.object(gw, "_dispatch_brain_tool", side_effect=_dispatch):
        _answer, _cit, _ann, messages, _usage, _cmd, charts = _drive_loop(_root(), client)

    # Client-bound payload: the whole picture.
    assert charts and charts[0]["svg"] == _FAKE_SVG
    # Model-visible: a receipt, and the SVG appears NOWHERE in the wire messages.
    payloads = [json.loads(b["content"])
                for m in messages if isinstance(m.get("content"), list)
                for b in m["content"]
                if isinstance(b, dict) and b.get("type") == "tool_result"]
    assert payloads and "svg" not in payloads[0]
    assert payloads[0]["rendered"] is True
    assert _FAKE_SVG not in json.dumps(messages, default=str)
    # And the model call itself never carried it.
    assert _FAKE_SVG not in json.dumps(client.create_kwargs[-1].get("messages"), default=str)


def test_stream_loop_fences_the_svg_but_keeps_the_chart_event(quiet_grounding):
    blocks = [_tool_block("render_inline_chart", 0, {"symbol": "TSLA"})]
    client = _CaptureClient([_Resp(blocks, "tool_use")])

    def _dispatch(name, _params, *_a, **_kw):
        return {"client_executed": True, "type": "chart", "ticker": "TSLA",
                "timeframe": "DAILY", "svg": _FAKE_SVG}

    with patch.object(gw, "_dispatch_brain_tool", side_effect=_dispatch):
        parsed = _drive_stream(_root(), client)

    chart_events = [p for p in parsed if p.get("type") == "chart"]
    assert chart_events and chart_events[0]["svg"] == _FAKE_SVG

    # Round 2's model call carries the tool_result — it must hold the stub, not the SVG.
    # (W5.1: the streaming loop's rounds go out through stream(), not create().)
    assert len(client.stream_kwargs) >= 2
    sent = client.stream_kwargs[1]["messages"]
    results = [b for m in sent if isinstance(m.get("content"), list)
               for b in m["content"]
               if isinstance(b, dict) and b.get("type") == "tool_result"]
    assert results, f"no tool_result reached round 2: {sent}"
    payload = json.loads(results[0]["content"])
    assert "svg" not in payload
    assert payload["ticker"] == "TSLA"
    assert _FAKE_SVG not in json.dumps(sent, default=str)


# ---------------------------------------------------------------------------
# 5. Messages cache breakpoint
# ---------------------------------------------------------------------------

def test_cache_control_last_message_wraps_a_str_content():
    messages = [{"role": "user", "content": "hello"}]
    gw._cache_control_last_message(messages)
    content = messages[0]["content"]
    assert content == [{"type": "text", "text": "hello",
                        "cache_control": {"type": "ephemeral"}}]


def test_cache_control_last_message_stamps_the_last_block_of_a_list():
    image = {"type": "image", "source": {"type": "base64"}}
    messages = [{"role": "user", "content": [{"type": "text", "text": "q"}, image]}]
    gw._cache_control_last_message(messages)
    blocks = messages[0]["content"]
    assert "cache_control" not in blocks[0]
    assert blocks[1]["cache_control"] == {"type": "ephemeral"}
    # Caller-owned block copied, never mutated in place.
    assert "cache_control" not in image


def test_cache_control_last_message_is_a_no_op_on_empties():
    gw._cache_control_last_message([])                                   # no messages
    gw._cache_control_last_message([{"role": "user", "content": ""}])    # empty str
    gw._cache_control_last_message([{"role": "user", "content": []}])    # empty list


def test_initial_messages_carry_one_breakpoint_and_tool_results_carry_none(quiet_grounding):
    blocks = [_tool_block("get_movers", 0), _tool_block("get_house_view", 1)]
    client = _CaptureClient([_Resp(blocks, "tool_use")])

    with patch.object(gw, "_dispatch_brain_tool",
                      side_effect=lambda name, *_a, **_kw: {"tool": name}):
        _drive_loop(_root(), client, message="what moved")

    # Round 1: the question block carries the breakpoint.
    first = client.create_kwargs[0]["messages"]
    assert isinstance(first[-1]["content"], list)
    assert first[-1]["content"][-1]["cache_control"] == {"type": "ephemeral"}

    # Round 2: the appended tool_result message carries NONE, and the array still holds
    # exactly one breakpoint in total (the provider budget is four across the request,
    # and system + tools already spend two).
    second = client.create_kwargs[1]["messages"]
    tail = second[-1]
    assert tail["role"] == "user"
    assert all(b.get("type") == "tool_result" for b in tail["content"])
    assert all("cache_control" not in b for b in tail["content"])
    assert json.dumps(second, default=str).count('"cache_control"') == 1


def test_stream_loop_also_stamps_exactly_one_messages_breakpoint(quiet_grounding):
    blocks = [_tool_block("get_movers", 0)]
    client = _CaptureClient([_Resp(blocks, "tool_use")])
    with patch.object(gw, "_dispatch_brain_tool",
                      side_effect=lambda name, *_a, **_kw: {"tool": name}):
        _drive_stream(_root(), client)

    # W5.1: the streaming loop's rounds go out through stream(), not create().
    first = client.stream_kwargs[0]["messages"]
    assert first[-1]["content"][-1]["cache_control"] == {"type": "ephemeral"}
    assert json.dumps(client.stream_kwargs[-1]["messages"],
                      default=str).count('"cache_control"') == 1


def test_system_and_tools_keep_their_own_breakpoints(quiet_grounding):
    """The messages breakpoint is ADDITIVE — it must not have displaced either of the
    two that already shipped."""
    client = _CaptureClient()
    with patch.object(gw, "_dispatch_brain_tool",
                      side_effect=lambda name, *_a, **_kw: {"tool": name}):
        _drive_loop(_root(), client)
    kwargs = client.create_kwargs[0]
    assert kwargs["system"][-1]["cache_control"] == {"type": "ephemeral"}
    assert kwargs["tools"][-1]["cache_control"] == {"type": "ephemeral"}


# ---------------------------------------------------------------------------
# 6. Earnings-ledger TTL cache
# ---------------------------------------------------------------------------

def _write_ledger_file(root: pathlib.Path, summary: str) -> pathlib.Path:
    row = ec.project_score_row({
        "ticker": "AAPL",
        "quarter": "Q3",
        "year": 2026,
        "call_date": "2026-07-30",
        "source": "terminal_transcript",
        "source_url": "/data/tx/AAPL/2026Q3.json.gz",
        "source_sha256": "a" * 64,
        "source_revision_sha256": "b" * 64,
        "source_record_id": "defeatbeta:AAPL:2026Q3",
        "source_updated_at": "2026-07-30T21:00:00Z",
        "scored_at": "2026-07-30T21:05:00Z",
        "model": "qwen3-14b",
        "prompt_version": "equal-v2",
        "analysis_schema_version": "earnings-qual/v2",
        "sentiment": 0.72,
        "performance": 8.4,
        "confidence": 0.91,
        "tone_word": "confident",
        "summary": summary,
        "positive_highlights": ["Services demand accelerated."],
        "negative_highlights": ["Component costs remain elevated."],
        "tags": ["services", "cost_pressure"],
        "is_context_only": True,
        "degraded_reason": None,
    })
    path = root / ec.CALL_EVENTS_REL
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(row, sort_keys=True) + "\n", encoding="utf-8")
    return path


@pytest.fixture(autouse=True)
def _clean_ledger_cache():
    ec.clear_ledger_cache()
    yield
    ec.clear_ledger_cache()


class _ReadCounter:
    """Counts real reads of the ledger file, delegating everything else."""

    def __init__(self, monkeypatch):
        self.n = 0
        real = pathlib.Path.read_text

        def _counting(inner_self, *args, **kwargs):
            if inner_self.name == "earnings_call_events.jsonl":
                self.n += 1
            return real(inner_self, *args, **kwargs)

        monkeypatch.setattr(pathlib.Path, "read_text", _counting)


def test_two_reads_inside_the_ttl_parse_the_file_once(tmp_path, monkeypatch):
    _write_ledger_file(tmp_path, "Demand accelerated.")
    counter = _ReadCounter(monkeypatch)

    first, gap1, safe1 = ec._read_ledger(tmp_path)
    second, gap2, safe2 = ec._read_ledger(tmp_path)

    assert counter.n == 1, f"ledger re-parsed inside the TTL ({counter.n} reads)"
    assert first == second
    assert (gap1, safe1) == (gap2, safe2) == (None, True)


def test_a_symbol_turns_double_read_costs_one_parse(tmp_path, monkeypatch):
    """The shape this cache exists for: latest_for_ticker is called twice per symbol
    turn (ambient context + get_symbol_context)."""
    _write_ledger_file(tmp_path, "Demand accelerated.")
    counter = _ReadCounter(monkeypatch)

    a = ec.latest_for_ticker(tmp_path, "AAPL")
    b = ec.latest_for_ticker(tmp_path, "AAPL")

    assert counter.n == 1
    assert a is not None and a["ticker"] == "AAPL"
    assert a == b


def test_a_changed_file_invalidates_the_cache(tmp_path, monkeypatch):
    _write_ledger_file(tmp_path, "Demand accelerated.")
    counter = _ReadCounter(monkeypatch)

    before, _gap, _safe = ec._read_ledger(tmp_path)
    assert before[0]["summary"] == "Demand accelerated."

    time.sleep(0.01)  # keep the mtime signature distinct on a coarse clock
    _write_ledger_file(tmp_path, "Demand decelerated sharply this quarter.")

    after, _gap, _safe = ec._read_ledger(tmp_path)
    assert counter.n == 2, "a changed ledger must be re-parsed, not served from cache"
    assert after[0]["summary"] == "Demand decelerated sharply this quarter."


def test_ttl_expiry_forces_a_reparse(tmp_path, monkeypatch):
    _write_ledger_file(tmp_path, "Demand accelerated.")
    monkeypatch.setattr(ec, "_LEDGER_CACHE_TTL_S", 0.0)
    counter = _ReadCounter(monkeypatch)

    ec._read_ledger(tmp_path)
    ec._read_ledger(tmp_path)
    assert counter.n == 2


def test_cached_rows_are_clones_so_a_caller_cannot_corrupt_the_next_read(tmp_path):
    _write_ledger_file(tmp_path, "Demand accelerated.")
    first, _gap, _safe = ec._read_ledger(tmp_path)
    first[0]["summary"] = "MUTATED"
    first[0]["tags"].append("injected")
    first.append({"bogus": True})

    second, _gap, _safe = ec._read_ledger(tmp_path)
    assert len(second) == 1
    assert second[0]["summary"] == "Demand accelerated."
    assert "injected" not in second[0]["tags"]


def test_absent_ledger_still_reports_the_gap(tmp_path):
    rows, gap, safe = ec._read_ledger(tmp_path)
    assert rows == []
    assert gap and "absent" in gap
    assert safe is True


def test_an_invalid_row_still_fails_closed_through_the_cache(tmp_path):
    path = tmp_path / ec.CALL_EVENTS_REL
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text('{"schema": "earnings.call_event.v1"}\n', encoding="utf-8")

    for _ in range(2):  # cold then cached — the verdict must not soften
        rows, gap, safe = ec._read_ledger(tmp_path)
        assert rows == []
        assert safe is False
        assert gap and "invalid" in gap


def test_clone_json_is_a_deep_copy():
    src = {"a": [1, {"b": [2]}], "c": "s"}
    out = ec._clone_json(src)
    assert out == src
    out["a"][1]["b"].append(3)
    assert src["a"][1]["b"] == [2]


# ---------------------------------------------------------------------------
# 7. One-batch nudge
# ---------------------------------------------------------------------------

def test_seed_plan_line_asks_for_one_batch():
    line = gw._SEED_PLAN_LINE
    assert "ask for them together" in line
    assert "one first response" in line


def test_seed_plan_line_stays_one_line():
    """The seed-router suite reads the plan by taking the first line after the marker —
    a newline inside the template would silently truncate every assertion there."""
    rendered = gw._SEED_PLAN_LINE.format(tools="get_market_events")
    assert rendered.startswith("\n\n")
    assert "\n" not in rendered[2:]


def test_seed_plan_still_parses_into_its_tool_list():
    line = gw._seed_tool_plan("why is TLT down today")
    assert line
    tools = line.split("start with ")[1].split(";")[0].split(", ")
    assert tools[0] == "get_market_events"
    assert line.count("start with ") == 1


def test_one_batch_nudge_is_advisory_not_enforcement():
    """House doctrine: the seed plan never caps or blocks a tool. The added sentence
    must not introduce imperative gating vocabulary."""
    line = gw._SEED_PLAN_LINE.lower()
    for banned in ("you must", "never call", "only call", "do not call", "required"):
        assert banned not in line
