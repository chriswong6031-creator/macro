"""Deterministic tool-plan seeding for the gateway's fast lane (Analyst OS W1-A).

What this suite pins:
  1. The plan line reaches the system prompt on a fast/chat/off-terminal turn, and names
     the events wire for a "today" question — the shape the fast lane most often misplays.
  2. The three gates: pro lane, research mode and the Terminal page each drop the line
     (autonomy by design, own report shape, technician read order respectively).
  3. Street/research shape seeds search_research.
  4. Never enforcement, never fatal: a classifier that raises yields "" and the turn still
     produces an answer.
  5. Word-boundary discipline: 'Newsroom' must not fire the news nudge; 'news' as a word must.
  6. Dedupe: a tool named by both a nudge and the classifier appears exactly once.
"""
from __future__ import annotations

import json
import pathlib

from engine.neuralweb import ask_brain as ab
from engine.neuralweb import brain_gateway as gw

_PLAN_MARK = "TOOL PLAN for this question shape"
_TLT_Q = "why is TLT down today"
_ANSWER = ("Steady tape, nothing forcing a move. "
           "is_context_only: true — all signals are display-tier pending FDR.")


# ── stubs (mirror tests/test_brain_gateway.py's capture idiom) ───────────────

class _MockBlock:
    def __init__(self, type_: str, text: str = ""):
        self.type = type_
        self.text = text
        self.name = ""
        self.input = {}
        self.id = "tid1"


class _MockResponse:
    def __init__(self, content: list, stop_reason: str = "end_turn"):
        self.content = content
        self.stop_reason = stop_reason


class _CaptureClient:
    """Answers every create() with a plain end_turn text, keeping each call's kwargs."""

    def __init__(self) -> None:
        self.create_kwargs: list[dict] = []
        self.messages = self

    def create(self, **kwargs):
        self.create_kwargs.append(kwargs)
        return _MockResponse([_MockBlock("text", _ANSWER)], "end_turn")


def _make_root(tmp_path: pathlib.Path) -> pathlib.Path:
    nw = tmp_path / "data" / "neuralweb"
    nw.mkdir(parents=True, exist_ok=True)
    (nw / "world_state.json").write_text(json.dumps(
        {"verdict": "RISK_OFF", "regime": "Q1", "score": 34}))
    return tmp_path


def _system_text(client: _CaptureClient) -> str:
    """The system prompt as the model saw it (a one-element cache_control block list)."""
    assert client.create_kwargs, "the loop never called the model"
    system = client.create_kwargs[0]["system"]
    if isinstance(system, list):
        return "".join(str(b.get("text", "")) for b in system)
    return str(system)


def _run(tmp_path, message: str = _TLT_Q, lane: str = "fast",
         mode: str = "chat", page: str = "dashboard") -> str:
    root = _make_root(tmp_path)
    client = _CaptureClient()
    answer, *_ = gw._run_brain_loop(
        message, lane, [], {"page": page}, root, tmp_path, "http://127.0.0.1:3100",
        client, "deepseek-v4-flash", 500, 2, mode=mode)
    assert answer, "the turn must still produce an answer"
    return _system_text(client)


# ── 1. Present on the lane that needs it, and names the events wire ──────────

def test_plan_line_rides_fast_chat_dashboard(tmp_path):
    system = _run(tmp_path)
    assert _PLAN_MARK in system
    assert "get_market_events" in system.split(_PLAN_MARK)[1].split("\n")[0]


def test_plan_line_is_guidance_not_a_cap(tmp_path):
    # GUIDANCE, never enforcement: the plan only tells the model where to START, and the
    # sentence that follows must hand the remaining budget back to it.
    system = _run(tmp_path)
    line = _PLAN_MARK + system.split(_PLAN_MARK)[1].split("\n")[0]
    assert "start with" in line
    assert "spend any remaining calls only on what discriminates" in line


# ── 2. The three gates ───────────────────────────────────────────────────────

def test_pro_lane_gets_no_plan_line(tmp_path):
    assert _PLAN_MARK not in _run(tmp_path, lane="pro")


def test_research_mode_gets_no_plan_line(tmp_path):
    assert _PLAN_MARK not in _run(tmp_path, mode="research")


def test_terminal_page_gets_no_plan_line(tmp_path):
    assert _PLAN_MARK not in _run(tmp_path, page="terminal")


# ── 3. Street / research shape ───────────────────────────────────────────────

def test_street_question_seeds_search_research():
    line = gw._seed_tool_plan("what does the street think of NVDA")
    assert "search_research" in line
    assert "get_market_events" not in line


def test_zh_research_shape_seeds_search_research():
    assert "search_research" in gw._seed_tool_plan("机构怎么看 NVDA")


# ── 4. Never enforcement, never fatal ────────────────────────────────────────

def test_classifier_exception_degrades_to_empty(monkeypatch):
    def _boom(_q, _t):
        raise RuntimeError("classifier on fire")

    monkeypatch.setattr(ab, "_classify_question", _boom)
    assert gw._seed_tool_plan(_TLT_Q) == ""


def test_turn_survives_a_broken_classifier(tmp_path, monkeypatch):
    def _boom(_q, _t):
        raise RuntimeError("classifier on fire")

    monkeypatch.setattr(ab, "_classify_question", _boom)
    system = _run(tmp_path)
    assert _PLAN_MARK not in system
    assert "LANGUAGE FOR THIS TURN" in system  # the rest of the prompt is intact


# ── 5. Word-boundary discipline on the short ASCII nudges ────────────────────

def test_newsroom_does_not_fire_the_news_nudge():
    assert "get_market_events" not in gw._seed_tool_plan("Newsroom coverage of duration")


def test_news_as_a_word_does_fire():
    assert "get_market_events" in gw._seed_tool_plan("any news on the dollar")


def test_adjusted_does_not_fire_the_just_nudge():
    assert "get_market_events" not in gw._seed_tool_plan("explain adjusted close")


# ── 6. Dedupe, and the 3-tool display cap ────────────────────────────────────

def test_both_nudges_and_classifier_seeds_dedupe():
    line = gw._seed_tool_plan(
        "what does the street think about today's breaking news for TLT")
    tools = line.split("start with ")[1].split(";")[0].split(", ")
    assert tools == ["get_market_events", "search_research", "read_world_state"]
    assert len(tools) == len(set(tools))


def test_nudge_overlapping_a_classifier_seed_shows_once(monkeypatch):
    # A future classifier that seeds the same tool must not double it in the line.
    monkeypatch.setattr(ab, "_classify_question",
                        lambda _q, _t: (5, ["get_market_events", "read_world_state"]))
    line = gw._seed_tool_plan("what did the street say about today's news")
    tools = line.split("start with ")[1].split(";")[0].split(", ")
    assert tools.count("get_market_events") == 1
    assert tools == ["get_market_events", "search_research", "read_world_state"]


def test_plan_shows_at_most_three_tools(monkeypatch):
    monkeypatch.setattr(ab, "_classify_question",
                        lambda _q, _t: (5, ["a", "b", "c", "d", "e"]))
    tools = gw._seed_tool_plan("today").split("start with ")[1].split(";")[0].split(", ")
    assert tools == ["get_market_events", "a", "b"]


def test_empty_message_never_raises():
    assert isinstance(gw._seed_tool_plan(""), str)
    assert isinstance(gw._seed_tool_plan(None), str)  # type: ignore[arg-type]
