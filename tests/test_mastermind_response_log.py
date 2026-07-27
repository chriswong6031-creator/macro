"""Tests for lib/mastermind_response_log.py — the shared write contract for the
Mastermind AI response log (both Macro brain + Terminal copilot surfaces)."""
from __future__ import annotations

import json

import pytest

from lib import mastermind_response_log as mm


# ---------------------------------------------------------------------------
# Env isolation: default every test to NO sink unless it opts in.
# ---------------------------------------------------------------------------
@pytest.fixture(autouse=True)
def _clean_env(monkeypatch):
    for k in ("R2_ENDPOINT", "R2_ACCESS_KEY_ID", "R2_SECRET_ACCESS_KEY", "R2_BUCKET",
              "MASTERMIND_RESPONSE_LOG_LOCAL_DIR", "MASTERMIND_RESPONSE_LOG_DISABLED"):
        monkeypatch.delenv(k, raising=False)


# ---------------------------------------------------------------------------
# hash_user_ref — privacy
# ---------------------------------------------------------------------------
def test_hash_user_ref_guest_collapses():
    assert mm.hash_user_ref(is_guest=True) == "guest"
    assert mm.hash_user_ref("abc", is_guest=True) == "guest"


def test_hash_user_ref_never_leaks_raw_id_or_email():
    uid = "3f0c-user-uuid"
    email = "someone@example.com"
    ref = mm.hash_user_ref(uid, email)
    assert ref.startswith("u_")
    assert uid not in ref
    assert email not in ref
    # Stable + deterministic.
    assert ref == mm.hash_user_ref(uid, email)


def test_hash_user_ref_anon_when_empty():
    assert mm.hash_user_ref("", "", False) == "anon"


# ---------------------------------------------------------------------------
# build_row — schema shape
# ---------------------------------------------------------------------------
def test_build_row_shape_and_provider_inference():
    row = mm.build_row(
        surface="macro", question="what is spx doing?", answer="It is up 1%.",
        model="claude-opus-4-8", lane="pro", mode="chat", user_id="u1",
        latency_ms=1234, input_tokens=10, output_tokens=20,
        context={"page": "dashboard", "symbol": "SPY", "junk": {"x": 1}},
    )
    assert row["schema"] == "mastermind.response_log.v1"
    assert row["surface"] == "macro"
    assert row["provider"] == "claude_api"          # inferred from claude* model
    assert row["user_ref"].startswith("u_")
    assert row["question"] == "what is spx doing?"
    assert row["answer"] == "It is up 1%."
    assert row["latency_ms"] == 1234
    assert row["input_tokens"] == 10 and row["output_tokens"] == 20
    # context keeps only known scalar keys
    assert row["context"] == {"page": "dashboard", "symbol": "SPY"}
    assert set(row["flags"]) == {"filtered", "degraded", "error", "screened"}
    assert row["id"]


def test_build_row_deepseek_provider_and_terminal_surface():
    row = mm.build_row(surface="terminal", question="q", answer="a", model="deepseek-chat")
    assert row["surface"] == "terminal"
    assert row["provider"] == "deepseek"


def test_build_row_unknown_surface_defaults_macro():
    row = mm.build_row(surface="weird", question="q", answer="a")
    assert row["surface"] == "macro"


def test_build_row_clips_long_answer():
    long = "x" * 40000
    row = mm.build_row(surface="macro", question="q", answer=long)
    assert row["answer"].endswith("…[truncated]")
    assert len(row["answer"]) < len(long)


# ---------------------------------------------------------------------------
# thinking — the reasoning trace (contradiction-assessment corpus)
# ---------------------------------------------------------------------------
def _seg(text="thought", round_=1, phase="tool", model="deepseek-v4-flash", **kw):
    seg = {"round": round_, "phase": phase, "model": model, "text": text}
    seg.update(kw)
    return seg


def test_build_row_thinking_defaults_to_empty_list():
    # Old callers pass nothing; the field must still exist so readers never branch.
    row = mm.build_row(surface="macro", question="q", answer="a")
    assert row["thinking"] == []


def test_build_row_keeps_thinking_segments():
    row = mm.build_row(surface="macro", question="q", answer="a", thinking=[
        _seg("weighing the two reads", round_=1, phase="tool"),
        _seg("they disagree", round_=2, phase="synthesis", model="claude-opus-5"),
    ])
    assert [s["phase"] for s in row["thinking"]] == ["tool", "synthesis"]
    assert row["thinking"][1]["model"] == "claude-opus-5"
    assert row["thinking"][1]["round"] == 2


def test_build_row_clips_each_thinking_segment():
    long = "y" * 40000
    row = mm.build_row(surface="macro", question="q", answer="a",
                       thinking=[_seg(long), _seg(long)])
    for seg in row["thinking"]:
        assert seg["text"].endswith("…[truncated]")
        assert len(seg["text"]) < len(long)
        # Bound is per-segment, not per-trace: a 2-segment trace clips twice.
        assert len(seg["text"]) <= mm._THINKING_TEXT_CAP + 32


def test_build_row_caps_thinking_segment_count_keeping_the_first():
    row = mm.build_row(surface="macro", question="q", answer="a",
                       thinking=[_seg(f"step {i}", round_=i) for i in range(60)])
    assert len(row["thinking"]) == mm._THINKING_MAX_SEGMENTS
    # FIRST N, not last: a chain of thought frames the conflict up front.
    assert row["thinking"][0]["text"] == "step 0"
    assert row["thinking"][-1]["text"] == f"step {mm._THINKING_MAX_SEGMENTS - 1}"


def test_build_row_redacted_thinking_survives_with_empty_text():
    row = mm.build_row(surface="macro", question="q", answer="a",
                       thinking=[_seg("", redacted=True), _seg("")])
    # The redacted one is kept (evidence the model reasoned); the plain empty is dropped.
    assert len(row["thinking"]) == 1
    assert row["thinking"][0]["text"] == ""
    assert row["thinking"][0]["redacted"] is True


def test_build_row_drops_non_dict_thinking_segments():
    row = mm.build_row(surface="macro", question="q", answer="a",
                       thinking=["a bare string", None, 7, _seg("real")])
    assert [s["text"] for s in row["thinking"]] == ["real"]


def test_build_row_thinking_coerces_types():
    row = mm.build_row(surface="macro", question="q", answer="a",
                       thinking=[{"round": "3", "phase": 9, "model": None, "text": "t"}])
    seg = row["thinking"][0]
    assert seg["round"] == 3 and isinstance(seg["round"], int)
    assert seg["phase"] == "9" and seg["model"] == ""


def test_build_row_thinking_non_list_is_empty():
    assert mm.build_row(surface="macro", question="q", answer="a",
                        thinking="not a list")["thinking"] == []


def test_thinking_round_trips_through_the_local_sink(tmp_path, monkeypatch):
    monkeypatch.setenv("MASTERMIND_RESPONSE_LOG_LOCAL_DIR", str(tmp_path))
    assert mm.log_response(surface="macro", question="q", answer="a",
                           thinking=[_seg("the two reads disagree")]) is True
    written = json.loads(list(tmp_path.rglob("*.json"))[0].read_text())
    assert written["thinking"][0]["text"] == "the two reads disagree"


# ---------------------------------------------------------------------------
# object_key — R2 layout
# ---------------------------------------------------------------------------
def test_object_key_layout():
    row = mm.build_row(surface="terminal", question="q", answer="a", row_id="abc123")
    key = mm.object_key(row)
    assert key.startswith("mastermind_response_logs/terminal/")
    assert key.endswith("/abc123.json")
    # date segment between surface and id
    parts = key.split("/")
    assert len(parts) == 4 and parts[2][:4].isdigit()


# ---------------------------------------------------------------------------
# enabled() gating
# ---------------------------------------------------------------------------
def test_enabled_false_without_any_sink():
    assert mm.enabled() is False


def test_enabled_true_with_local_dir(tmp_path, monkeypatch):
    monkeypatch.setenv("MASTERMIND_RESPONSE_LOG_LOCAL_DIR", str(tmp_path))
    assert mm.enabled() is True


def test_disabled_flag_overrides_sink(tmp_path, monkeypatch):
    monkeypatch.setenv("MASTERMIND_RESPONSE_LOG_LOCAL_DIR", str(tmp_path))
    monkeypatch.setenv("MASTERMIND_RESPONSE_LOG_DISABLED", "1")
    assert mm.enabled() is False


# ---------------------------------------------------------------------------
# write_row / log_response — local mirror sink
# ---------------------------------------------------------------------------
def test_write_row_local_mirror(tmp_path, monkeypatch):
    monkeypatch.setenv("MASTERMIND_RESPONSE_LOG_LOCAL_DIR", str(tmp_path))
    row = mm.build_row(surface="macro", question="hi", answer="hello", row_id="rid1")
    assert mm.write_row(row) is True
    files = list(tmp_path.rglob("*.json"))
    assert len(files) == 1
    written = json.loads(files[0].read_text())
    assert written["id"] == "rid1"
    assert written["answer"] == "hello"
    # path mirrors the R2 key layout (minus the prefix)
    assert files[0].parent.parent.name == "macro"


def test_log_response_noop_when_disabled():
    # No sink configured → best-effort no-op, returns False, never raises.
    assert mm.log_response(surface="macro", question="q", answer="a") is False


# ---------------------------------------------------------------------------
# brain_gateway integration — surface is derived from context.page so ONE
# instrumentation point covers BOTH surfaces (Macro widget + Terminal widget,
# both run mm_brain.js against /api/brain/stream; page='terminal' on the Terminal).
# ---------------------------------------------------------------------------
def test_surface_derived_from_context_page(monkeypatch, tmp_path):
    monkeypatch.setenv("MASTERMIND_RESPONSE_LOG_LOCAL_DIR", str(tmp_path))
    from engine.neuralweb import brain_gateway as bg

    captured: dict = {}
    monkeypatch.setattr(mm, "log_response_async", lambda **kw: captured.update(kw))

    bg._log_brain_response(question="q", answer="a", context={"page": "terminal", "symbol": "AAPL"})
    assert captured.get("surface") == "terminal"

    captured.clear()
    bg._log_brain_response(question="q", answer="a", context={"page": "dashboard"})
    assert captured.get("surface") == "macro"

    captured.clear()
    bg._log_brain_response(question="q", answer="a", context={})
    assert captured.get("surface") == "macro"  # missing page → macro

    captured.clear()
    bg._log_brain_response(question="q", answer="   ", context={"page": "terminal"})
    assert captured == {}  # empty answer → not a response, no write
