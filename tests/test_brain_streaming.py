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

All offline (no network, no key) — the stub clients below script the SDK's
`messages.stream()` contract chunk by chunk.
"""
from __future__ import annotations

import json
import pathlib
import sys
from unittest.mock import patch

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from engine.neuralweb import brain_gateway as gw  # noqa: E402
from tests.test_brain_gateway import (  # noqa: E402
    _MockBlock,
    _MockResponse,
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
    """

    def __init__(self, chunks: list[str]):
        self._chunks = list(chunks)
        self._n = 0
        self.messages = self
        self.stream_kwargs: list[dict] = []

    def create(self, **kwargs):
        self._n += 1
        if self._n == 1:
            return _MockResponse(
                [_MockBlock("tool_use", name="get_house_view", input_={}, id_="t1")],
                "tool_use")
        return _MockResponse([_MockBlock("text", "Pulling that together.")], "tool_use")

    def stream(self, **kwargs):
        self.stream_kwargs.append(kwargs)
        return _ChunkStreamCtx(self._chunks)


def _drive(chunks: list[str], tmp_path, *, client=None, providers=None,
           lane: str = "fast", question: str = "how does the tape look?",
           user: str = "u-stream") -> list[dict]:
    """Run a full chat_stream turn against a scripted chunk stream; return SSE events."""
    root = _make_temp_root()
    if providers is None:
        client = client or _ChunkClient(chunks)
        providers = [{"name": "deepseek", "model": "deepseek-v4-pro", "client": client}]
    with patch.object(gw, "_brain_quota_dir", return_value=tmp_path):
        with patch.object(gw, "_build_lane_providers", return_value=providers):
            with patch.object(gw, "_resolve_tier", return_value={
                    "tier": "pro", "status": "active", "current_period_end": None}):
                with patch.object(gw, "_ensure_thread", return_value=None):
                    with patch.object(gw, "_dispatch_brain_tool", return_value={"ok": True}):
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
        def stream(self, **kwargs):
            self.stream_kwargs.append(kwargs)
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
