"""Contract S — true token streaming in the Mastermind Phase-2 synthesis.

The buffered single delta (SPEC §D / §0 gate 2) is superseded by the W5 latency wave;
see the 2026-08-01 amendment in research/mastermind_transparency_latency/SPEC.md.  The
guards that made that law safe to lift are what this file pins:

  * the leak screen still sees every character BEFORE it can ship (holdback + a
    chunk-overlapped sentinel sweep), and a hit retracts what already shipped;
  * a `[NEXT]` marker — including one split across two SDK chunks — never puts a
    fragment of itself on the wire;
  * the reassembled multi-delta text is byte-for-byte the answer the buffered path
    used to send in one piece;
  * the final full-answer pipeline stays the authority: when it disagrees with what
    streamed, the text is retracted and replaced.

W5.1 (§F amendment) extends that to EVERY ROUND's model call — the path the live bench
proved was the dominant one — behind a commitment horizon.  The second half of this file
pins the round path: what it may show, when it may show it, and what it takes back when
the round turns out to have been a tool round after all.

All offline (no network, no key) — the stub clients below script the SDK's
`messages.stream()` contract chunk by chunk.
"""
from __future__ import annotations

import json
import pathlib
import sys
import time
from unittest.mock import patch

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from engine.neuralweb import brain_gateway as gw  # noqa: E402
from tests.test_brain_gateway import (  # noqa: E402
    _MockBlock,
    _MockResponse,
    _ScriptedStreamCtx,
    _make_temp_root,
    _sse,
)


@pytest.fixture(autouse=True)
def _ai_costs_ledger_to_tmp(tmp_path, monkeypatch):
    """Same guard as test_brain_gateway: no test may append to the repo's real
    data/ai_costs/usage.jsonl (it would show up as a staged diff in whatever PR ran)."""
    monkeypatch.setattr(
        "lib.ai_costs._write_ledger_path",
        lambda root=None: tmp_path / "ai_costs" / "usage.jsonl",
    )


# ---------------------------------------------------------------------------
# Stub SDK: a stream that yields EXACTLY the chunks it was given
# ---------------------------------------------------------------------------

class _ChunkStreamCtx:
    """Fake anthropic streaming context manager with a scripted chunk list."""

    def __init__(self, chunks: list[str]):
        self._chunks = list(chunks)

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    @property
    def text_stream(self):
        for c in self._chunks:
            yield c

    def get_final_message(self):
        return _MockResponse([_MockBlock("text", "".join(self._chunks))], "end_turn")


class _ChunkClient:
    """One Phase-1 tool round (which is what forces synthesis), then the scripted stream.

    Round 1 calls a tool; round 2 comes back stop_reason=tool_use with NO tool_use block,
    which ends Phase 1 and sends the loop into Phase-2 synthesis — the same shape
    test_brain_gateway's _two_round_client uses.

    W5.1: the ROUNDS stream too, so `stream()` has to answer them from the same script —
    `tools` in the kwargs is what separates a round from synthesis, exactly as it does in
    the gateway (synthesis deliberately ships none). The Phase-2 tests in this file are
    unaffected: the chunk list still serves the synthesis call, alone.
    """

    def __init__(self, chunks: list[str]):
        self._chunks = list(chunks)
        self._n = 0
        self.messages = self
        self.create_kwargs: list[dict] = []
        self.stream_kwargs: list[dict] = []

    def _scripted(self):
        self._n += 1
        if self._n == 1:
            return _MockResponse(
                [_MockBlock("tool_use", name="get_house_view", input_={}, id_="t1")],
                "tool_use")
        return _MockResponse([_MockBlock("text", "Pulling that together.")], "tool_use")

    def create(self, **kwargs):
        self.create_kwargs.append(kwargs)
        return self._scripted()

    def _synthesis_stream(self):
        """Phase-2 only. Subclass THIS (not `stream`) to script a synthesis stream —
        overriding `stream` outright takes the Phase-1 rounds down with it."""
        return _ChunkStreamCtx(self._chunks)

    def stream(self, **kwargs):
        self.stream_kwargs.append(kwargs)
        if "tools" in kwargs:          # a Phase-1 round (W5.1 streams these too)
            return _ScriptedStreamCtx(self._scripted())
        return self._synthesis_stream()


def _drive(chunks: list[str], tmp_path, *, client=None, providers=None,
           lane: str = "fast", question: str = "how does the tape look?",
           user: str = "u-stream", dispatch=None) -> list[dict]:
    """Run a full chat_stream turn against a scripted chunk stream; return SSE events.

    `dispatch` optionally replaces the canned tool handler with a side_effect, so a test
    can see the params the executor actually received.
    """
    root = _make_temp_root()
    if providers is None:
        client = client or _ChunkClient(chunks)
        providers = [{"name": "deepseek", "model": "deepseek-v4-pro", "client": client}]
    tool_patch = (patch.object(gw, "_dispatch_brain_tool", side_effect=dispatch)
                  if dispatch is not None
                  else patch.object(gw, "_dispatch_brain_tool", return_value={"ok": True}))
    with patch.object(gw, "_brain_quota_dir", return_value=tmp_path):
        with patch.object(gw, "_build_lane_providers", return_value=providers):
            with patch.object(gw, "_resolve_tier", return_value={
                    "tier": "pro", "status": "active", "current_period_end": None}):
                with patch.object(gw, "_ensure_thread", return_value=None):
                    with tool_patch:
                        with patch("lib.ai_costs.record_usage", return_value=True):
                            return _sse(list(gw.chat_stream(
                                question, user, lane=lane, root=root)))


def _deltas(parsed: list[dict]) -> list[str]:
    return [e["text"] for e in parsed if e["type"] == "delta"]


def _split(text: str, size: int) -> list[str]:
    return [text[i:i + size] for i in range(0, len(text), size)] or [""]


# A clean answer with no marker and no sentinel. Long enough to clear the holdback.
_LONG = ("The tape is quiet and the leadership is narrow. "
         "Breadth has not confirmed the index, so this is a watch, not a chase. "
         * 20).strip()


# ---------------------------------------------------------------------------
# Flush policy
# ---------------------------------------------------------------------------

def test_flush_fires_on_the_character_threshold(tmp_path):
    """With the time window effectively disabled, every mid-stream delta is at least
    _STREAM_FLUSH_CHARS long — the char threshold is what released it."""
    with patch.object(gw, "_stream_flush_cfg", return_value=(120, 999.0, 256)):
        parsed = _drive(_split(_LONG, 100), tmp_path)
    deltas = _deltas(parsed)
    assert len(deltas) >= 5, deltas                      # it really streamed
    for text in deltas[:-1]:                             # the last one is the tail
        assert len(text) >= 120, (len(text), text[:40])
    assert "".join(deltas) == _LONG


def test_flush_fires_on_the_time_threshold(tmp_path):
    """With the char threshold effectively disabled, a zero-length time window releases
    every chunk as it lands — this is what keeps a SLOW token stream feeling continuous
    instead of arriving in 120-char blocks."""
    chunks = ["Rates first. ", "Then breadth. ", "Then the tape. ", "Then rotation."]
    with patch.object(gw, "_stream_flush_cfg", return_value=(10_000, 0.0, 0)):
        parsed = _drive(chunks, tmp_path)
    deltas = _deltas(parsed)
    # No delta here can be char-triggered (the threshold is 10k and the whole answer is
    # 56 chars). The first chunk never flushes — a one-piece provider is not streaming —
    # so the three that follow it each get their own.
    assert len(deltas) == 3, deltas
    assert max(len(d) for d in deltas) < 10_000
    assert "".join(deltas) == "".join(chunks)


def test_a_one_chunk_stream_still_ships_exactly_one_delta(tmp_path):
    """The codex-served pro lane yields its whole answer in ONE text_stream chunk. That
    is not streaming, and it keeps the pre-Contract-S behavior exactly: one delta."""
    parsed = _drive([_LONG], tmp_path)
    deltas = _deltas(parsed)
    assert len(deltas) == 1, deltas
    assert deltas[0] == _LONG


def test_a_short_answer_never_leaves_the_holdback(tmp_path):
    """An answer shorter than the holdback is fully buffered — the leak screen gets the
    whole thing before a byte moves, exactly as it did before Contract S."""
    short = "Quiet tape. Watch, don't chase."
    assert len(short) < gw._LEAK_HOLDBACK_CHARS
    parsed = _drive(_split(short, 5), tmp_path)
    assert _deltas(parsed) == [short]


def test_multi_delta_reassembly_is_byte_identical_to_the_buffered_answer(tmp_path):
    """THE contract: however finely the provider chops the answer, the client ends up
    holding the same bytes the single buffered delta used to carry."""
    buffered = _deltas(_drive([_LONG], tmp_path))
    assert len(buffered) == 1
    for size in (7, 100, 997):
        streamed = _deltas(_drive(_split(_LONG, size), tmp_path))
        assert len(streamed) >= 2, size                   # it really streamed
        assert "".join(streamed) == buffered[0], size


# ---------------------------------------------------------------------------
# Leak holdback — the reason the buffered law could be lifted at all
# ---------------------------------------------------------------------------

def test_a_sentinel_split_across_two_chunks_never_reaches_the_wire(tmp_path):
    """The failure mode the holdback exists for: half a system-prompt sentinel arrives in
    one chunk and the rest in the next. NOTHING of it may have shipped by then, and the
    text that did ship is taken back."""
    sentinel = gw._LEAK_SENTINELS[0]
    head, tail = sentinel[:12], sentinel[12:]
    assert head and tail and head + tail == sentinel
    filler = "Breadth is narrow and the leadership is thin. "
    chunks = [filler] * 12 + [filler + head, tail + " and the rest of the leaked block."]

    parsed = _drive(chunks, tmp_path)
    joined = "".join(_deltas(parsed))
    assert sentinel not in joined
    assert head not in joined, joined[-80:]
    assert "SCOPE" not in joined

    retracts = [e for e in parsed if e["type"] == "retract"]
    assert len(retracts) == 1, [e["type"] for e in parsed]
    assert retracts[0]["text"] == gw._REFUSAL_DISTILL_EN
    assert set(retracts[0]) == {"type", "text"}

    types = [e["type"] for e in parsed]
    assert "delta" not in types[types.index("retract"):], types   # nothing after it
    done = next(e for e in parsed if e["type"] == "done")
    assert done["filtered"] is True, done
    assert types[0] == "meta" and types[-1] == "done"


def test_a_chinese_leak_retracts_in_chinese(tmp_path):
    """The refusal follows the answer's language, same rule as _leak_screen's."""
    sentinel = gw._LEAK_SENTINELS[0]
    filler = "当前市场情绪偏谨慎，领涨范围收窄，观察为主。"
    chunks = [filler] * 30 + [sentinel[:10], sentinel[10:]]
    parsed = _drive(chunks, tmp_path, question="现在大盘怎么样？", user="u-zh-leak")
    retracts = [e for e in parsed if e["type"] == "retract"]
    assert len(retracts) == 1 and retracts[0]["text"] == gw._REFUSAL_DISTILL_ZH


def test_a_sentinel_inside_the_first_chunk_never_streams_at_all(tmp_path):
    """Caught before a single delta: the turn degrades to one buffered refusal, which is
    exactly what the pre-Contract-S path did."""
    chunks = ["Sure — " + gw._LEAK_SENTINELS[1] + " is the rule I follow. " * 30]
    parsed = _drive(chunks, tmp_path, user="u-leak-first")
    assert [e["type"] for e in parsed if e["type"] in ("delta", "retract")] == ["delta"]
    assert _deltas(parsed) == [gw._REFUSAL_DISTILL_EN]


def test_the_final_screen_retracts_what_streaming_missed(tmp_path):
    """Belt and suspenders. The full-answer pass at the end is still the authority: if it
    rejects text the streaming guards let through, that text is taken back and replaced."""
    with patch.object(gw, "_leak_screen", side_effect=lambda t: gw._REFUSAL_DISTILL_EN if t else t):
        parsed = _drive(_split(_LONG, 100), tmp_path, user="u-final-screen")
    types = [e["type"] for e in parsed]
    assert "delta" in types and "retract" in types
    retract = next(e for e in parsed if e["type"] == "retract")
    assert retract["text"] == gw._REFUSAL_DISTILL_EN
    assert "delta" not in types[types.index("retract"):], types
    assert next(e for e in parsed if e["type"] == "done")["filtered"] is True


def test_an_advice_filter_rewrite_also_retracts(tmp_path):
    """_post_filter_advice is a no-op today, but the reconciliation is written against the
    CONTRACT, not against today's implementation: re-arm it and streamed text is withdrawn."""
    rewritten = "I can't put that as a personal order."
    with patch("engine.neuralweb.ask_brain._post_filter_advice",
               return_value=(rewritten, True)):
        parsed = _drive(_split(_LONG, 100), tmp_path, user="u-advice")
    retract = next(e for e in parsed if e["type"] == "retract")
    assert retract["text"] == rewritten
    assert next(e for e in parsed if e["type"] == "done")["filtered"] is True


def test_a_clean_turn_never_retracts_and_is_not_marked_filtered(tmp_path):
    """The flag means the guards rewrote the answer — a healthy streamed turn keeps False."""
    parsed = _drive(_split(_LONG, 100), tmp_path, user="u-clean")
    assert not [e for e in parsed if e["type"] == "retract"]
    assert next(e for e in parsed if e["type"] == "done")["filtered"] is False


# ---------------------------------------------------------------------------
# [NEXT] holdback
# ---------------------------------------------------------------------------

_NEXT_ANSWER_BODY = ("Financials have the cleanest setup; breadth is the thing to watch. "
                     * 8).rstrip()
_NEXT_TAIL = "\n\n[NEXT]\nWhat's leading?\nShould I hedge?\nWhen does this flip?"


@pytest.mark.parametrize("cut", [0, 1, 3, 6, 8])
def test_the_next_marker_never_appears_in_a_delta_however_it_is_split(tmp_path, cut):
    """The marker is split at every interesting boundary — before '[', mid-'[NEX', right
    after the ']'. No fragment may ship, under the most aggressive flush policy there is
    (every character eligible, zero holdback, zero time window)."""
    answer = _NEXT_ANSWER_BODY + _NEXT_TAIL
    split_at = len(_NEXT_ANSWER_BODY) + 2 + cut          # 2 = the blank line
    chunks = [answer[:split_at], answer[split_at:]]
    with patch.object(gw, "_stream_flush_cfg", return_value=(1, 0.0, 0)):
        parsed = _drive(chunks, tmp_path, user="u-next-%d" % cut)

    joined = "".join(_deltas(parsed))
    assert "[NEXT]" not in joined
    for frag in ("[N", "[NE", "[NEX", "[NEXT"):
        assert frag not in joined, (frag, joined[-60:])
    assert joined == _NEXT_ANSWER_BODY
    suggest = next(e for e in parsed if e["type"] == "suggest")
    assert suggest["items"] == ["What's leading?", "Should I hedge?", "When does this flip?"]
    types = [e["type"] for e in parsed]
    assert types.index("suggest") > max(i for i, t in enumerate(types) if t == "delta")
    assert types[-1] == "done"


def test_text_after_a_marker_line_still_lands_in_the_answer(tmp_path):
    """_split_suggestions honours the LAST '[NEXT]' line, so an earlier one is part of the
    answer. Streaming seals at the FIRST marker and lets the finalize pass emit the rest —
    conservative on the wire, correct in the bubble."""
    answer = ("Early read.\n[NEXT]\nnot the real block\n"
              "Second half of the answer, well past the first marker.\n"
              "[NEXT]\nWhat's next?")
    with patch.object(gw, "_stream_flush_cfg", return_value=(1, 0.0, 0)):
        parsed = _drive(_split(answer, 6), tmp_path, user="u-two-markers")
    joined = "".join(_deltas(parsed))
    assert not [e for e in parsed if e["type"] == "retract"]
    assert joined == gw._split_suggestions(answer)[0]
    assert "Second half of the answer" in joined
    suggest = next(e for e in parsed if e["type"] == "suggest")
    assert suggest["items"] == ["What's next?"]


# ---------------------------------------------------------------------------
# Failover: a dead candidate's draft is taken back, never appended to
# ---------------------------------------------------------------------------

def test_a_candidate_that_dies_mid_body_has_its_draft_wiped_before_the_retry(tmp_path):
    """The buffered law used to make failover free ("no partial text reaches the client").
    Streaming has to pay for that explicitly: an empty retract wipes the dead candidate's
    half-sentence so the next one never writes onto the end of it."""
    class _RateErr(Exception):
        status_code = 429

    class _ExplodingCtx(_ChunkStreamCtx):
        @property
        def text_stream(self):
            for c in self._chunks:
                yield c
            raise _RateErr("429 rate_limit mid-stream")

    class _ExplodingClient(_ChunkClient):
        def _synthesis_stream(self):
            return _ExplodingCtx(self._chunks)

    dead_text = "DEAD CANDIDATE DRAFT. " * 40
    live_text = ("The healthy candidate's answer. " * 30).strip()
    providers = [
        {"name": "deepseek", "model": "deepseek-v4-pro",
         "client": _ExplodingClient(_split(dead_text, 100))},
        {"name": "anthropic", "model": "claude-haiku-4-5",
         "client": _ChunkClient(_split(live_text, 100))},
    ]
    parsed = _drive([], tmp_path, providers=providers, user="u-midbody")

    types = [e["type"] for e in parsed]
    assert "retract" in types, types
    wipe_i = types.index("retract")
    assert parsed[wipe_i]["text"] == "", parsed[wipe_i]
    # everything the client holds at the end comes from AFTER the wipe
    after = "".join(e["text"] for e in parsed[wipe_i:] if e["type"] == "delta")
    assert after == live_text
    assert "DEAD CANDIDATE" not in after
    # a provider hiccup is not a screening event
    assert next(e for e in parsed if e["type"] == "done")["filtered"] is False


# ---------------------------------------------------------------------------
# Run-registry event budget
# ---------------------------------------------------------------------------

def test_a_60k_answer_stays_far_under_the_run_event_cap(tmp_path):
    """app/brain_runs.py buffers RUN_EVENT_CAP events per run and DROPS the overflow
    (only `done` is always admitted). At 120-char flushes even an absurd 60k-char answer
    spends ~500 events, so the cap is left alone — this is the tripwire that says so."""
    from app.brain_runs import RUN_EVENT_CAP

    answer = ("Liquidity, breadth, rates, and the dollar all point the same way today. "
              * 900)[:60_000]
    assert len(answer) == 60_000
    parsed = _drive(_split(answer, 100), tmp_path, user="u-cap")
    assert len(parsed) < RUN_EVENT_CAP, len(parsed)
    assert len(parsed) < RUN_EVENT_CAP // 4, len(parsed)   # ~500, with 8x of headroom
    assert "".join(_deltas(parsed)) == answer


# ---------------------------------------------------------------------------
# Unit level: the cut, the scan, and the config
# ---------------------------------------------------------------------------

def test_stream_display_cut_holds_back_the_tail():
    body = "abcdefghij" * 10                       # 100 chars, no newline
    assert gw._stream_display_cut(body, 0) == (100, False)
    assert gw._stream_display_cut(body, 30) == (70, False)
    assert gw._stream_display_cut(body, 500) == (0, False)
    assert gw._stream_display_cut("", 10) == (0, False)


def test_stream_display_cut_never_ends_on_whitespace():
    """_split_suggestions rstrips its clean text, so a cut that ended on a newline would
    make the streamed prefix stop being a prefix of the final answer — and the finalize
    reconciliation would retract a perfectly good reply."""
    cut, sealed = gw._stream_display_cut("done.\n\n   ", 0)
    assert (cut, sealed) == (5, False)
    assert "done.\n\n   "[:cut] == "done."


@pytest.mark.parametrize("tail", ["", " ", "[", "[N", "[NE", "[NEX", "[NEXT", "[NEXT]",
                                  "  [NEXT] "])
def test_a_trailing_line_that_could_become_the_marker_is_held_whole(tail):
    body = "The answer.\n" + tail
    cut, sealed = gw._stream_display_cut(body, 0)
    assert sealed is False
    assert cut == len("The answer."), (tail, cut)


@pytest.mark.parametrize("tail", ["[NEXT]x", "[NEXTs", "x[NEXT]", "Next up"])
def test_a_trailing_line_that_cannot_become_the_marker_is_emitted(tail):
    body = "The answer.\n" + tail
    cut, sealed = gw._stream_display_cut(body, 0)
    assert sealed is False and cut == len(body), (tail, cut)


def test_a_complete_marker_line_seals_the_stream():
    body = "The answer.\n[NEXT]\nWhat now?"
    cut, sealed = gw._stream_display_cut(body, 0)
    assert sealed is True
    assert body[:cut] == "The answer."
    # the seal survives more text arriving after it
    cut2, sealed2 = gw._stream_display_cut(body + "\nAnd more?", 0)
    assert sealed2 is True and cut2 == cut


def test_the_cut_never_runs_backwards_as_the_answer_grows():
    """The emission cursor only ever moves forward; a cut that shrank would mean text was
    emitted that the guards later wanted back."""
    body = ("Rates are the story.\n\nBreadth is not confirming. \n[NE"
            "XT]\nWhat's leading?\n")
    last = 0
    for i in range(1, len(body) + 1):
        cut, _sealed = gw._stream_display_cut(body[:i], 24)
        assert cut >= last, (i, cut, last)
        last = cut


def test_leak_hit_sees_a_sentinel_split_across_the_scan_window():
    """The windowed scan is only equivalent to re-scanning the whole answer if callers
    back the start up by _MAX_SENTINEL_LEN - 1. Pin that."""
    sentinel = gw._LEAK_SENTINELS[0]
    text = "x" * 500 + sentinel + "y" * 10
    already = 500 + len(sentinel) - 3          # scanned to 3 chars short of the end
    assert gw._leak_hit(text, already) is False            # naive resume misses it
    assert gw._leak_hit(text, already - (gw._MAX_SENTINEL_LEN - 1)) is True
    assert gw._leak_hit(text, 0) is True
    assert gw._leak_hit("nothing to see here", 0) is False
    assert gw._leak_hit("", 0) is False


def test_max_sentinel_len_tracks_the_assembled_sentinel_tuple():
    assert gw._MAX_SENTINEL_LEN == max(len(s) for s in gw._LEAK_SENTINELS)
    assert gw._LEAK_HOLDBACK_CHARS > gw._MAX_SENTINEL_LEN


def test_stream_flush_cfg_reads_the_config_block(tmp_path):
    root = tmp_path / "repo"
    (root / "config").mkdir(parents=True)
    (root / "config" / "brain.yml").write_text(
        "schema: brain_config.v1\n"
        "streaming:\n  flush_chars: 40\n  flush_seconds: 0.1\n"
        "  leak_holdback_chars: 900\n", encoding="utf-8")
    gw._BRAIN_CONFIG_CACHE = None
    try:
        assert gw._stream_flush_cfg(root) == (40, 0.1, 900)
    finally:
        gw._BRAIN_CONFIG_CACHE = None


def _cfg_for(tmp_path, name: str, body: str):
    root = tmp_path / name
    (root / "config").mkdir(parents=True)
    (root / "config" / "brain.yml").write_text(body, encoding="utf-8")
    gw._BRAIN_CONFIG_CACHE = None
    try:
        return gw._stream_flush_cfg(root)
    finally:
        gw._BRAIN_CONFIG_CACHE = None


_DEFAULTS = (gw._STREAM_FLUSH_CHARS, gw._STREAM_FLUSH_S, gw._LEAK_HOLDBACK_CHARS)


def test_stream_flush_cfg_falls_back_when_the_block_is_absent(tmp_path):
    assert _cfg_for(tmp_path, "a", "schema: brain_config.v1\n") == _DEFAULTS
    assert _cfg_for(tmp_path, "b", "streaming:\n") == _DEFAULTS
    assert _cfg_for(tmp_path, "c", "streaming: not-a-mapping\n") == _DEFAULTS


def test_stream_flush_cfg_floors_a_too_short_holdback(tmp_path):
    """Floored, not honoured: below the longest sentinel a split echo could ship ahead of
    the scan that catches it."""
    chars, secs, hold = _cfg_for(tmp_path, "d", "streaming:\n  leak_holdback_chars: 4\n")
    assert (chars, secs) == (gw._STREAM_FLUSH_CHARS, gw._STREAM_FLUSH_S)
    assert hold == gw._MAX_SENTINEL_LEN


def test_stream_flush_cfg_never_raises_on_a_garbage_value(tmp_path):
    """A malformed knob loses the override, never the turn."""
    assert _cfg_for(tmp_path, "e", "streaming:\n  flush_chars: nonsense\n") == _DEFAULTS
    assert _cfg_for(tmp_path, "f", "streaming:\n  flush_seconds: [1,2]\n") == _DEFAULTS


def test_the_shipped_config_matches_the_module_defaults():
    """config/brain.yml is the operator's knob and the module constants are the
    last-resort fallback — they must not drift apart (MNZ-R12)."""
    import yaml
    repo = pathlib.Path(__file__).resolve().parent.parent
    raw = yaml.safe_load((repo / "config" / "brain.yml").read_text(encoding="utf-8"))
    blk = raw["streaming"]
    assert blk["flush_chars"] == gw._STREAM_FLUSH_CHARS
    assert blk["flush_seconds"] == gw._STREAM_FLUSH_S
    assert blk["leak_holdback_chars"] == gw._LEAK_HOLDBACK_CHARS
    assert set(blk) == {"flush_chars", "flush_seconds", "leak_holdback_chars"}


# ---------------------------------------------------------------------------
# Widget: the client half of the contract
# ---------------------------------------------------------------------------

def test_the_widget_handles_retract_and_the_pair_is_byte_identical():
    repo = pathlib.Path(__file__).resolve().parent.parent
    tpl = (repo / "templates" / "mm_brain.js").read_text(encoding="utf-8")
    site = (repo / "site" / "mm_brain.js").read_text(encoding="utf-8")
    assert tpl == site, "templates/mm_brain.js and site/mm_brain.js have drifted"
    assert "j.type === 'retract'" in tpl, "no retract branch in handleEvent"
    assert "reset: function (text)" in tpl, "MdStream has no reset()"
    # Cursor law (SPEC §B7): every parsed data event bumps the cursor — only the `run`
    # envelope returns false, so a retract branch must NOT add an early return.
    branch = tpl.split("j.type === 'retract'", 1)[1].split("else if", 1)[0]
    assert "return false" not in branch, branch


def test_the_delta_and_retract_events_are_json_clean():
    """Both events are emitted through json.dumps in the gateway; the client parses them
    with JSON.parse. Round-trip the exact shapes the reconciliation can produce."""
    for payload in ({"type": "delta", "text": "partial "},
                    {"type": "retract", "text": ""},
                    {"type": "retract", "text": gw._REFUSAL_DISTILL_ZH}):
        assert json.loads(json.dumps(payload)) == payload


# ===========================================================================
# W5.1 — every ROUND streams, behind a commitment horizon
# ===========================================================================
# W5 (above) streams Phase-2 synthesis, which only runs when the tool budget is
# exhausted. The dominant real turn writes its answer INSIDE a tool round, and that call
# was blocking — the live post-merge bench measured ttfv == done with one delta. These
# pin the round path: what it shows, when it is allowed to show it, and what it takes
# back when the round turns out to have been a tool round after all.


class _RateErr(Exception):
    status_code = 429


class _RoundCtx:
    """One Phase-1 ROUND served as a real token stream.

    `tools` are the tool_use blocks the round ends up calling: they ride
    `get_final_message()` — which is exactly where the Anthropic SDK puts them, and where
    the gateway's parallel executor reads them from — never the text stream.
    `snapshot_tool_after` makes `current_message_snapshot` (the SDK's in-flight view)
    reveal them after N chunks, which is the early signal the gateway freezes display on.
    """

    def __init__(self, chunks, *, tools=(), stop_reason=None, raise_after=None,
                 snapshot_tool_after=None, pause_before_last=0.0):
        self._chunks = list(chunks)
        self._tools = list(tools)
        self._stop = stop_reason or ("tool_use" if tools else "end_turn")
        self._raise_after = raise_after
        self._snap_after = snapshot_tool_after
        self._pause = pause_before_last
        self._seen = 0

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def _tool_blocks(self):
        return [_MockBlock("tool_use", name=name, input_=params, id_=f"rt{i}")
                for i, (name, params) in enumerate(self._tools)]

    @property
    def text_stream(self):
        for i, chunk in enumerate(self._chunks):
            if self._pause and i == len(self._chunks) - 1:
                time.sleep(self._pause)
            self._seen = i + 1
            yield chunk
            if self._raise_after is not None and self._seen >= self._raise_after:
                raise _RateErr("429 rate_limit mid-round")

    @property
    def current_message_snapshot(self):
        content = [_MockBlock("text", "".join(self._chunks[:self._seen]))]
        if self._snap_after is not None and self._seen >= self._snap_after:
            content.extend(self._tool_blocks())
        return _MockResponse(content, "end_turn")

    def get_final_message(self):
        text = "".join(self._chunks)
        content = ([_MockBlock("text", text)] if text else []) + self._tool_blocks()
        return _MockResponse(content, self._stop)


def _round(chunks, **kw):
    """A FACTORY, so every candidate and every round gets a fresh context object."""
    return lambda: _RoundCtx(chunks, **kw)


class _RoundClient:
    """Serves scripted ROUNDS as streams; a turn that still reaches Phase 2 gets a
    one-chunk synthesis of `answer`. create() is a tripwire: on this path the gateway
    must never fall back to the blocking call."""

    def __init__(self, rounds, answer: str = "Synthesis fallback answer."):
        self._rounds = list(rounds)
        self._i = 0
        self._answer = answer
        self.messages = self
        self.stream_kwargs: list[dict] = []

    def create(self, **kwargs):
        raise AssertionError("W5.1: a client with .stream must never be create()d here")

    def stream(self, **kwargs):
        self.stream_kwargs.append(kwargs)
        if "tools" not in kwargs:                     # Phase-2 synthesis
            return _ChunkStreamCtx([self._answer])
        if self._i < len(self._rounds):
            ctx = self._rounds[self._i]()
            self._i += 1
            return ctx
        return _RoundCtx(["Out of script — plain end_turn answer."])


def _drive_rounds(tmp_path, rounds=None, *, providers=None, client=None,
                  user: str = "u-round", **kw) -> list[dict]:
    if providers is None:
        client = client or _RoundClient(rounds or [])
        providers = [{"name": "deepseek", "model": "deepseek-v4-pro", "client": client}]
    return _drive([], tmp_path, providers=providers, user=user, **kw)


def _types(parsed: list[dict]) -> list[str]:
    return [e["type"] for e in parsed]


# 9 sentences ≈ 584 chars: past the 256-char holdback AND the 200-char horizon.
_ROUND_ANSWER = ("Breadth is narrow and the leadership is thin, so this is a watch. "
                 * 9).strip()
# Just past the horizon, nowhere near the default holdback — for horizon-only tests.
_NARRATION = ("Before I answer that I want to look at the tape properly. " * 6).strip()


# ── the answer a round writes now streams ────────────────────────────────────

def test_a_final_round_answer_streams_instead_of_arriving_whole(tmp_path):
    """THE W5.1 heal. A round that ends `end_turn` is the answer, and it now reaches the
    user as it is written — not as one delta at `done`."""
    parsed = _drive_rounds(tmp_path, [_round(_split(_ROUND_ANSWER, 60),
                                             pause_before_last=0.05)])
    deltas = _deltas(parsed)
    assert len(deltas) > 1, deltas
    assert "".join(deltas) == _ROUND_ANSWER
    assert not [e for e in parsed if e["type"] == "retract"]
    done = next(e for e in parsed if e["type"] == "done")
    assert done["filtered"] is False
    latency = done["usage"]["latency"]
    assert latency["ttfv_ms"] < latency["total_ms"], latency
    # …and the turn never touched Phase 2: one round, no synthesis.
    assert latency["synthesis_ms"] is None, latency
    assert "synthesis" not in [e.get("phase") for e in parsed]


def test_round_streaming_reassembles_byte_for_byte_into_the_buffered_answer(tmp_path):
    """However finely the provider chops the round, the client ends up holding exactly
    what the one-piece (pre-W5.1) round used to deliver in a single delta."""
    buffered = _deltas(_drive_rounds(tmp_path, [_round([_ROUND_ANSWER])], user="u-r-one"))
    assert buffered == [_ROUND_ANSWER]
    for size in (7, 60, 997):
        streamed = _deltas(_drive_rounds(tmp_path, [_round(_split(_ROUND_ANSWER, size))],
                                         user="u-r-%d" % size))
        assert "".join(streamed) == _ROUND_ANSWER, size


# ── the horizon: nothing is shown until the round has committed ──────────────

def test_a_short_narration_before_a_tool_call_never_reaches_the_screen(tmp_path):
    """The common shape: one sentence of "let me look" and then a tool call. It is under
    the horizon, so nothing ships, nothing is retracted, and the wire is byte-identical
    to the pre-W5.1 tool round."""
    with patch.object(gw, "_stream_flush_cfg", return_value=(1, 0.0, 0)):
        parsed = _drive_rounds(tmp_path, [
            _round(_split("Let me check the tape.", 6),
                   tools=[("get_house_view", {})]),
            _round(_split(_ROUND_ANSWER, 60)),
        ])
    assert not [e for e in parsed if e["type"] == "retract"], parsed
    assert "".join(_deltas(parsed)) == _ROUND_ANSWER
    assert _types(parsed).count("tool") == 1          # the tool round really ran
    assert next(e for e in parsed if e["type"] == "done")["filtered"] is False


def test_disabling_the_horizon_puts_wipe_noise_on_the_wire(tmp_path):
    """MUTATION CHECK for the test above: with the horizon at 0 the same turn shows the
    narration and then yanks it back. That flicker is exactly what the horizon buys, and
    this is the guard that fails if someone quietly zeroes it."""
    with patch.object(gw, "_stream_flush_cfg", return_value=(1, 0.0, 0)):
        with patch.object(gw, "_stream_commit_chars", return_value=0):
            parsed = _drive_rounds(tmp_path, [
                _round(_split("Let me check the tape.", 6),
                       tools=[("get_house_view", {})]),
                _round(_split(_ROUND_ANSWER, 60)),
            ], user="u-nohorizon")
    types = _types(parsed)
    assert "retract" in types, types
    wipe = types.index("retract")
    shown_before_the_wipe = "".join(e["text"] for e in parsed[:wipe] if e["type"] == "delta")
    assert "Let me check the tape." in shown_before_the_wipe
    assert parsed[wipe]["text"] == ""


def test_narration_past_the_horizon_streams_and_is_then_wiped(tmp_path):
    """The horizon is a bet, not a proof. When the model narrates past it and calls tools
    anyway, the narration is taken back with ONE empty retract, the tool round proceeds
    normally, and the final answer is clean, complete, and NOT marked filtered (a wipe is
    not a screening event)."""
    with patch.object(gw, "_stream_flush_cfg", return_value=(1, 0.0, 0)):
        parsed = _drive_rounds(tmp_path, [
            _round(_split(_NARRATION, 50), tools=[("get_house_view", {})]),
            _round(_split(_ROUND_ANSWER, 60)),
        ], user="u-narrate")

    types = _types(parsed)
    retracts = [e for e in parsed if e["type"] == "retract"]
    assert len(retracts) == 1 and retracts[0]["text"] == "", retracts
    wipe = types.index("retract")
    before = "".join(e["text"] for e in parsed[:wipe] if e["type"] == "delta")
    assert before and _NARRATION.startswith(before), before
    after = "".join(e["text"] for e in parsed[wipe:] if e["type"] == "delta")
    assert after == _ROUND_ANSWER                      # clean, complete, un-concatenated
    assert "Before I answer" not in after
    assert types.count("tool") == 1
    assert next(e for e in parsed if e["type"] == "done")["filtered"] is False


def test_narration_on_the_last_round_is_wiped_before_synthesis_writes(tmp_path):
    """The shape that has no next round to clean up after it: the model comes back
    `tool_use` with NO tool block, which ends Phase 1 and sends the turn to synthesis.
    The narration must be wiped THERE — if it is left standing, the finalize pass has to
    replace it wholesale, which lands as a screening retract and marks a healthy turn
    `filtered`. (Mutation guard for the round-path wipe: the next round's own defensive
    wipe cannot cover this case, because there is no next round.)"""
    with patch.object(gw, "_stream_flush_cfg", return_value=(1, 0.0, 0)):
        parsed = _drive_rounds(tmp_path, [
            _round(_split(_NARRATION, 50), stop_reason="tool_use"),
        ], client=_RoundClient([_round(_split(_NARRATION, 50), stop_reason="tool_use")],
                               answer=_ROUND_ANSWER), user="u-narrate-last")

    retracts = [e for e in parsed if e["type"] == "retract"]
    assert len(retracts) == 1, _types(parsed)
    assert retracts[0]["text"] == "", retracts[0]        # a wipe, not a replacement
    types = _types(parsed)
    after = "".join(e["text"] for e in parsed[types.index("retract"):]
                    if e["type"] == "delta")
    assert after == _ROUND_ANSWER
    assert "synthesis" in [e.get("phase") for e in parsed]
    assert next(e for e in parsed if e["type"] == "done")["filtered"] is False


def test_a_tool_block_in_the_live_snapshot_freezes_display_early(tmp_path):
    """The SDK exposes the assembling message while it streams. Once a tool_use block is
    open in it, the text already written is narration by definition — display freezes
    there, so the horizon can never release it."""
    with patch.object(gw, "_stream_flush_cfg", return_value=(1, 0.0, 0)):
        parsed = _drive_rounds(tmp_path, [
            _round(_split(_NARRATION, 50), tools=[("get_house_view", {})],
                   snapshot_tool_after=2),            # open at 100 chars, under the horizon
            _round(_split(_ROUND_ANSWER, 60)),
        ], user="u-snapshot")
    assert not [e for e in parsed if e["type"] == "retract"], parsed
    assert "".join(_deltas(parsed)) == _ROUND_ANSWER


def test_the_gate_holds_every_character_until_the_horizon_exactly(tmp_path):
    """Unit level, at the boundary: 199 characters show nothing; the 200th releases the
    whole eligible prefix at once."""
    gate = gw._StreamGate(1, 0.0, 0, commit_chars=200)
    assert "".join(gate.feed(c) for c in _split("x" * 199, 40)) == ""
    assert gate.shown == 0
    assert gate.feed("y") == "x" * 199 + "y"
    assert gate.shown == 200
    # committed: from here on the ordinary flush policy runs, horizon or not
    assert gate.feed("z") == "z"


def test_the_gate_default_horizon_is_the_module_constant():
    assert gw._STREAM_COMMIT_CHARS == 200
    assert gw._stream_commit_chars(pathlib.Path("/nonexistent")) == 200
    # Phase-2 passes no horizon at all: synthesis text IS the answer, so the second chunk
    # already carries the first one out (chunk 1 alone never flushes — a provider that
    # hands the whole answer over in one piece is not streaming).
    gate = gw._StreamGate(1, 0.0, 0)
    assert gate.feed("a") == ""
    assert gate.feed("b") == "ab"
    assert gate.feed("c") == "c"


# ── failover after the round has already shown text ──────────────────────────

def test_a_round_candidate_that_dies_after_committing_has_its_draft_wiped(tmp_path):
    """Same law as the Phase-2 mid-body failover, on the round path: the dead candidate's
    half-sentence is wiped before the healthy one writes a character."""
    dead = ("DEAD ROUND DRAFT. " * 30).strip()
    live = ("The healthy candidate's round answer. " * 12).strip()
    providers = [
        {"name": "deepseek", "model": "deepseek-v4-pro",
         "client": _RoundClient([_round(_split(dead, 50), raise_after=6)])},
        {"name": "anthropic", "model": "claude-haiku-4-5",
         "client": _RoundClient([_round(_split(live, 50))])},
    ]
    with patch.object(gw, "_stream_flush_cfg", return_value=(1, 0.0, 0)):
        parsed = _drive_rounds(tmp_path, providers=providers, user="u-round-failover")

    types = _types(parsed)
    assert "retract" in types, types
    wipe = types.index("retract")
    assert parsed[wipe]["text"] == ""
    assert "DEAD ROUND" in "".join(e["text"] for e in parsed[:wipe] if e["type"] == "delta")
    after = "".join(e["text"] for e in parsed[wipe:] if e["type"] == "delta")
    assert after == live                                # no concatenation
    assert "DEAD ROUND" not in after
    assert next(e for e in parsed if e["type"] == "done")["filtered"] is False


def test_every_round_candidate_failing_still_ships_the_degraded_notice(tmp_path):
    """A round with no surviving provider degrades exactly as the blocking call did —
    and anything it had already shown is wiped first, so the notice stands alone."""
    dead = ("DEAD ROUND DRAFT. " * 30).strip()
    providers = [
        {"name": "deepseek", "model": "deepseek-v4-pro",
         "client": _RoundClient([_round(_split(dead, 50), raise_after=6)])},
    ]
    with patch.object(gw, "_stream_flush_cfg", return_value=(1, 0.0, 0)):
        parsed = _drive_rounds(tmp_path, providers=providers, user="u-round-dead")
    types = _types(parsed)
    assert types[-1] == "done"
    wipe = types.index("retract")
    assert parsed[wipe]["text"] == ""
    assert _deltas(parsed)[-1] == gw._DEGRADED_USER_MSG
    done = next(e for e in parsed if e["type"] == "done")
    assert done["degraded"] is True and done["filtered"] is False


def test_a_provider_that_cannot_stream_a_tool_round_still_answers(tmp_path):
    """W5.1 safety net. `stream` + `tools` is a request shape this loop never sent before
    a provider whose compat endpoint rejects it must NOT black out the lane: with nothing
    on screen, the round retries once through the pre-W5.1 blocking call and the turn
    answers normally (one buffered delta, no retract, not degraded)."""
    class _NoStreamStream(Exception):
        status_code = 400          # a plain bad-request: NOT failover-worthy

    class _CannotStreamClient(_RoundClient):
        def __init__(self):
            super().__init__([])
            self.create_kwargs: list[dict] = []

        def create(self, **kwargs):
            self.create_kwargs.append(kwargs)
            return _MockResponse([_MockBlock("text", _ROUND_ANSWER)], "end_turn")

        def stream(self, **kwargs):
            self.stream_kwargs.append(kwargs)
            raise _NoStreamStream("messages: streaming with tools is not supported")

    client = _CannotStreamClient()
    parsed = _drive_rounds(tmp_path, client=client, user="u-nostream")
    assert client.stream_kwargs and client.create_kwargs, "both surfaces were tried"
    assert _deltas(parsed) == [_ROUND_ANSWER]
    assert not [e for e in parsed if e["type"] == "retract"]
    done = next(e for e in parsed if e["type"] == "done")
    assert done["degraded"] is False and done["filtered"] is False


def test_a_client_with_no_stream_surface_keeps_the_blocking_round(tmp_path):
    """Not every provider object has `.messages.stream`. One with only `create()` takes
    the pre-W5.1 path directly — no streaming attempt, no deltas mid-round."""
    class _CreateOnly:
        def __init__(self):
            self.messages = self
            self.create_kwargs: list[dict] = []

        def create(self, **kwargs):
            self.create_kwargs.append(kwargs)
            return _MockResponse([_MockBlock("text", _ROUND_ANSWER)], "end_turn")

    client = _CreateOnly()
    providers = [{"name": "anthropic", "model": "claude-haiku-4-5", "client": client}]
    parsed = _drive_rounds(tmp_path, providers=providers, user="u-createonly")
    assert len(client.create_kwargs) == 1
    assert _deltas(parsed) == [_ROUND_ANSWER]
    assert not [e for e in parsed if e["type"] == "retract"]


# ── the leak screen and the [NEXT] seal hold on the round path too ───────────

def test_a_sentinel_split_across_two_round_chunks_never_reaches_the_wire(tmp_path):
    """The holdback guards the round path with the same runway it gives synthesis: half a
    system-prompt sentinel in one chunk and the rest in the next, with text already on
    screen. Nothing of it ships, and what did ship is replaced by the refusal."""
    sentinel = gw._LEAK_SENTINELS[0]
    head, tail = sentinel[:12], sentinel[12:]
    filler = "Breadth is narrow and the leadership is thin. "
    chunks = [filler] * 12 + [filler + head, tail + " and the rest of the leaked block."]

    parsed = _drive_rounds(tmp_path, [_round(chunks)], user="u-round-leak")
    joined = "".join(_deltas(parsed))
    assert sentinel not in joined and head not in joined, joined[-80:]
    retracts = [e for e in parsed if e["type"] == "retract"]
    assert len(retracts) == 1 and retracts[0]["text"] == gw._REFUSAL_DISTILL_EN
    types = _types(parsed)
    assert "delta" not in types[types.index("retract"):], types
    assert next(e for e in parsed if e["type"] == "done")["filtered"] is True


def test_a_sentinel_inside_the_first_round_chunk_never_streams_at_all(tmp_path):
    """Caught before anything shipped: one buffered refusal delta, no retract — the
    pre-W5.1 wire, exactly."""
    chunks = ["Sure — " + gw._LEAK_SENTINELS[1] + " is the rule I follow. " * 30]
    parsed = _drive_rounds(tmp_path, [_round(chunks)], user="u-round-leak-first")
    assert [t for t in _types(parsed) if t in ("delta", "retract")] == ["delta"]
    assert _deltas(parsed) == [gw._REFUSAL_DISTILL_EN]


@pytest.mark.parametrize("cut", [0, 1, 3, 6, 8])
def test_the_next_marker_never_fragments_on_the_round_path(tmp_path, cut):
    """The suggestions marker is split at every interesting boundary inside a ROUND's
    stream, under the most aggressive flush policy there is."""
    body = ("Financials have the cleanest setup; breadth is the thing to watch. " * 8).rstrip()
    answer = body + "\n\n[NEXT]\nWhat's leading?\nShould I hedge?"
    split_at = len(body) + 2 + cut
    with patch.object(gw, "_stream_flush_cfg", return_value=(1, 0.0, 0)):
        parsed = _drive_rounds(tmp_path, [_round([answer[:split_at], answer[split_at:]])],
                               user="u-round-next-%d" % cut)
    joined = "".join(_deltas(parsed))
    for frag in ("[N", "[NE", "[NEX", "[NEXT", "[NEXT]"):
        assert frag not in joined, (frag, joined[-60:])
    assert joined == body
    suggest = next(e for e in parsed if e["type"] == "suggest")
    assert suggest["items"] == ["What's leading?", "Should I hedge?"]


# ── the tool executor still receives the SDK's own blocks ────────────────────

def test_the_round_stream_hands_the_executor_the_same_tool_blocks(tmp_path):
    """Requirement of the conversion: streaming the round must not degrade the tool_use
    blocks. Names, ids and INPUTS arrive whole, in block order, from the stream's final
    message — which is where the SDK assembles them."""
    seen: list[tuple] = []

    def _dispatch(name, params, *_a, **_kw):
        seen.append((name, dict(params)))
        return {"ok": True, "tool": name}

    with patch.object(gw, "_stream_flush_cfg", return_value=(1, 0.0, 0)):
        parsed = _drive_rounds(tmp_path, [
            _round(["Checking."], tools=[("get_quote", {"symbol": "AAPL"}),
                                         ("get_movers", {"limit": 5})]),
            _round(_split(_ROUND_ANSWER, 60)),
        ], user="u-round-tools", dispatch=_dispatch)

    assert seen == [("get_quote", {"symbol": "AAPL"}), ("get_movers", {"limit": 5})]
    tools = [e for e in parsed if e["type"] == "tool"]
    assert [t["name"] for t in tools] == ["get_quote", "get_movers"]
    assert tools[0]["detail"] == "AAPL"
    assert "".join(_deltas(parsed)) == _ROUND_ANSWER


# ── the codex shim: one chunk is not streaming, and it must stay that way ────

def test_a_one_chunk_round_keeps_its_single_buffered_delta(tmp_path):
    """engine.codex_provider._Stream yields one chunk per text block after the blocking
    call has already returned — that is not streaming, and splitting it would be churn.
    A codex-served round keeps the pre-W5.1 wire: exactly one delta, at the end."""
    parsed = _drive_rounds(tmp_path, [_round([_ROUND_ANSWER])], user="u-round-codex")
    assert _deltas(parsed) == [_ROUND_ANSWER]
    assert not [e for e in parsed if e["type"] == "retract"]


def test_a_one_chunk_round_that_calls_tools_shows_nothing_and_wipes_nothing(tmp_path):
    """The codex shape with tool_calls in the same envelope: the text arrives whole,
    together with the tool blocks. Nothing flushed, so there is nothing to take back."""
    with patch.object(gw, "_stream_flush_cfg", return_value=(1, 0.0, 0)):
        parsed = _drive_rounds(tmp_path, [
            _round([_NARRATION], tools=[("get_house_view", {})]),
            _round([_ROUND_ANSWER]),
        ], user="u-round-codex-tools")
    assert not [e for e in parsed if e["type"] == "retract"], parsed
    assert _deltas(parsed) == [_ROUND_ANSWER]
    assert _types(parsed).count("tool") == 1


def test_the_codex_stream_shape_is_what_the_round_path_assumes():
    """Pinned against the real class, not a mock of it: text_stream yields the text
    blocks (one chunk each), get_final_message carries the tool_use blocks AND the
    stop_reason, and there is no in-flight snapshot to read — so a codex round can only
    learn it was a tool round at the end, which is why one chunk must never flush."""
    from engine import codex_provider as cp

    msg = cp._Message(
        content=[cp._TextBlock("The whole answer, in one piece."),
                 cp._ToolUseBlock(name="get_quote", input={"symbol": "AAPL"})],
        usage=cp._Usage(), stop_reason="tool_use")

    class _FakeMessages:
        def create(self, **kwargs):
            return msg

    with cp._Stream(_FakeMessages(), {}) as stream:
        assert list(stream.text_stream) == ["The whole answer, in one piece."]
        final = stream.get_final_message()
    assert final.stop_reason == "tool_use"
    assert [b.type for b in final.content] == ["text", "tool_use"]
    assert final.content[1].input == {"symbol": "AAPL"}
    assert getattr(cp._Stream, "current_message_snapshot", None) is None
    assert gw._stream_tool_use_started(cp._Stream(_FakeMessages(), {})) is False


# ── the horizon knob ─────────────────────────────────────────────────────────

def test_stream_commit_chars_reads_the_config_block(tmp_path):
    root = tmp_path / "commit"
    (root / "config").mkdir(parents=True)
    (root / "config" / "brain.yml").write_text(
        "schema: brain_config.v1\nstreaming:\n  commit_chars: 40\n", encoding="utf-8")
    gw._BRAIN_CONFIG_CACHE = None
    try:
        assert gw._stream_commit_chars(root) == 40
    finally:
        gw._BRAIN_CONFIG_CACHE = None


@pytest.mark.parametrize("body", [
    "schema: brain_config.v1\n",                       # no streaming block
    "streaming:\n",                                    # empty block
    "streaming: not-a-mapping\n",                      # wrong type
    "streaming:\n  commit_chars: nonsense\n",          # garbage value
    "streaming:\n  flush_chars: 40\n",                 # block present, key absent
])
def test_stream_commit_chars_falls_back_to_the_module_default(tmp_path, body):
    root = tmp_path / ("cc%d" % abs(hash(body)))
    (root / "config").mkdir(parents=True)
    (root / "config" / "brain.yml").write_text(body, encoding="utf-8")
    gw._BRAIN_CONFIG_CACHE = None
    try:
        assert gw._stream_commit_chars(root) == gw._STREAM_COMMIT_CHARS
    finally:
        gw._BRAIN_CONFIG_CACHE = None


def test_a_negative_commit_chars_disarms_rather_than_inverts(tmp_path):
    """max(0, …): a nonsense negative horizon must mean "no horizon", never a cursor
    running backwards inside the gate."""
    root = tmp_path / "neg"
    (root / "config").mkdir(parents=True)
    (root / "config" / "brain.yml").write_text(
        "streaming:\n  commit_chars: -5\n", encoding="utf-8")
    gw._BRAIN_CONFIG_CACHE = None
    try:
        assert gw._stream_commit_chars(root) == 0
    finally:
        gw._BRAIN_CONFIG_CACHE = None
