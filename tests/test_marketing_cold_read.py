"""tests/test_marketing_cold_read.py — a VETO, and it must stay one.

Fixture-driven; ZERO live network, ZERO live LLM (every call goes through the
`_call` seam, and the env gate is never set in this suite).

WHAT THIS GATE IS FOR. Every other copy screen in the repo asks a question about
the STRING. The 2026-08-04 flagship post —

    More info on this - South Korea core inflation hits 2-1/2 year high
    despite headline cooling -- wire reports

— was grammatical, sourced, in budget, stance-free and handle-free. It passed all
of them and failed only "a reader who sees nothing but this post cannot resolve
'this'", which is not a rule anyone can write. relay_hygiene enumerates the
defects we already saw; this is for the next one.

WHAT IS PINNED. The happy path is the least of it — most of this file exists to
prove the gate CANNOT become an editor:

  1. It is off by default, and off means ZERO model calls.
  2. It never reaches a lane that writes its own copy.
  3. A block on a category we never authorised is DISCARDED. This is the guard
     that makes "the model decided the copy is boring" a wasted call rather than
     a quarantined post.
  4. Every malformed / absent / refused reply fails OPEN. Post-time quarantine
     is terminal, so a screen that cannot evaluate must never fail dead.
  5. It cannot pass, promote, rank or edit — only stop.
  6. It ships in SHADOW, and the shipped config says so.
  7. One string, one verdict, inside a process.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest


def _worktree_root() -> Path:
    p = Path(__file__).resolve()
    for candidate in [p.parent, p.parent.parent, p.parent.parent.parent]:
        if (candidate / "engine").is_dir():
            return candidate
    raise RuntimeError(f"Could not locate repo root from {p}")


ROOT = _worktree_root()
sys.path.insert(0, str(ROOT))

from engine.marketing import cold_read as cr  # noqa: E402

LIVE_POST = ("More info on this - South Korea core inflation hits 2-1/2 year "
             "high despite headline cooling -- wire reports")
CLEAN_POST = "US ISM Manufacturing PMI for July 55.6 versus 54.0 estimate"
HOUSE_VOICE = ("$AAPL into the week\n\nUp at 52-week highs. Nothing broken here, "
               "and I'd rather wait.")

ARMED = {"enabled": True, "env_gate": ""}   # env_gate="" disables the env check


def _reply(blocked, category="none", reason=""):
    """A model that always answers the same way."""
    import json
    payload = json.dumps({"blocked": blocked, "category": category,
                          "reason": reason})
    return lambda _text, _cfg: payload


@pytest.fixture(autouse=True)
def _clear_memo():
    cr._MEMO.clear()
    yield
    cr._MEMO.clear()


# ── 1. Off by default, and off means no call ─────────────────────────────────

class TestDisarmed:
    def test_absent_config_makes_no_call(self):
        calls = []

        def _spy(text, cfg):
            calls.append(text)
            return _reply(True, "dangling_reference", "no antecedent")(text, cfg)

        v = cr.cold_read_verdict(LIVE_POST, provenance="press_lane", cfg=None,
                                 _call=_spy)
        assert v["blocked"] is False
        assert v["mode"] == "off"
        assert calls == [], "a disarmed gate must not reach the model"

    def test_the_env_gate_is_honoured(self, monkeypatch):
        """Config AND env, like every other LLM gate in this repo."""
        monkeypatch.delenv("MARKETING_LLM_ENABLED", raising=False)
        calls = []
        v = cr.cold_read_verdict(
            LIVE_POST, provenance="press_lane", cfg={"enabled": True},
            _call=lambda t, c: calls.append(t) or _reply(True, "truncated", "x")(t, c),
        )
        assert v["blocked"] is False and calls == []


# ── 2. It never reaches our own voice ────────────────────────────────────────

class TestLaneScope:
    @pytest.mark.parametrize("lane", [
        "content_studio", "weekend_levels", "claude_rewrite",
        "publisher_live_movers", "", "something_new",
    ])
    def test_a_lane_that_writes_its_own_copy_is_never_read(self, lane):
        """Our desks write in the first person on purpose. "Can a stranger
        resolve this" is a question about copy relayed from somebody else's
        page, and a model asked it about our own voice would hold the voice."""
        calls = []
        v = cr.cold_read_verdict(
            HOUSE_VOICE, provenance=lane, cfg=ARMED,
            _call=lambda t, c: calls.append(t) or _reply(
                True, "unnamed_promise", "who is I")(t, c),
        )
        assert v["blocked"] is False
        assert v["mode"] == "skipped"
        assert calls == [], f"{lane} reached the model"

    def test_the_allowlist_is_relay_hygiene_s_and_not_a_second_copy(self):
        src = (ROOT / "engine" / "marketing" / "cold_read.py").read_text(encoding="utf-8")
        assert "lane_is_relayed" in src
        import re
        assert not re.search(r"^\s*_RELAYED_PROVENANCES\s*[:=]", src, re.M)


# ── 3. THE GUARD: an unauthorised block is discarded ─────────────────────────

class TestTheModelCannotBecomeAnEditor:
    @pytest.mark.parametrize("category", [
        "tone", "quality", "too_short", "boring", "inaccurate", "unsourced",
        "formatting", "", "DANGLING_REFERENCE_BUT_WRONG", "opinion",
    ])
    def test_a_block_on_an_unauthorised_category_is_discarded(self, category):
        """THE LOAD-BEARING TEST OF THIS FILE.

        "The model is only allowed to veto" is worth nothing if the veto is
        unbounded. A block counts ONLY when it names one of the five categories
        we authorised — all of which are things the READER cannot resolve. A
        model that decides the copy is boring, badly punctuated or wrong about
        the Fed is discarded, so that failure mode costs a wasted call instead
        of a quarantined post."""
        v = cr.cold_read_verdict(
            CLEAN_POST, provenance="press_lane", cfg=ARMED,
            _call=_reply(True, category, "I did not care for it"),
        )
        assert v["blocked"] is False, category
        assert "discarded" in v["reason"] or v["category"] == ""

    def test_the_enum_is_not_config_widenable(self):
        """A config-widened enum is a config-wide editor. BLOCK_CATEGORIES must
        not be reachable from a config key."""
        src = (ROOT / "engine" / "marketing" / "cold_read.py").read_text(encoding="utf-8")
        body = src.split("BLOCK_CATEGORIES: frozenset[str] = frozenset({", 1)[1]
        body = body.split("})", 1)[0]
        assert "cfg" not in body and "get(" not in body

    def test_a_block_with_no_reason_is_discarded(self):
        v = cr.cold_read_verdict(
            CLEAN_POST, provenance="press_lane", cfg=ARMED,
            _call=_reply(True, "dangling_reference", ""),
        )
        assert v["blocked"] is False
        assert "no reason" in v["reason"]

    def test_an_authorised_block_IS_honoured(self):
        """...and the discards above are not just "nothing ever blocks"."""
        v = cr.cold_read_verdict(
            LIVE_POST, provenance="press_lane", cfg=ARMED,
            _call=_reply(True, "dangling_reference", "no antecedent for 'this'"),
        )
        assert v["blocked"] is True
        assert v["category"] == "dangling_reference"
        assert v["reason"] == "no antecedent for 'this'"


# ── 4. Every failure path fails OPEN ─────────────────────────────────────────

class TestFailOpen:
    @pytest.mark.parametrize("reply", [
        None,                                   # no endpoint / timeout / refusal
        "",                                     # empty
        "I think this post is fine, actually.",  # prose, no JSON
        "{not json at all",                     # broken JSON
        '["blocked"]',                          # JSON, wrong shape
        '{"blocked": true}',                    # no category
        '{"blocked": "yes", "category": "truncated", "reason": "x"}',  # truthy str
    ])
    def test_a_reply_we_cannot_read_never_blocks(self, reply):
        """Post-time quarantine is TERMINAL. A screen that cannot evaluate must
        let the item through — it may never fail dead."""
        v = cr.cold_read_verdict(CLEAN_POST, provenance="press_lane", cfg=ARMED,
                                 _call=lambda t, c: reply)
        assert v["blocked"] is False

    def test_a_raising_model_never_blocks(self):
        def _boom(_t, _c):
            raise RuntimeError("connection refused")

        v = cr.cold_read_verdict(CLEAN_POST, provenance="press_lane", cfg=ARMED,
                                 _call=_boom)
        assert v["blocked"] is False
        assert v["mode"] == "unavailable"

    def test_a_truthy_string_is_not_a_block(self):
        """`"blocked": "yes"` is not a boolean true from a model that ignored
        the schema; a JSON string is truthy in Python and that is how a sloppy
        reply would have quarantined a clean post."""
        v = cr.cold_read_verdict(
            CLEAN_POST, provenance="press_lane", cfg=ARMED,
            _call=lambda t, c: '{"blocked": "yes", "category": "tone", "reason": "meh"}',
        )
        assert v["blocked"] is False


# ── 5. It can only stop ──────────────────────────────────────────────────────

class TestVetoOnly:
    def test_the_verdict_carries_no_score(self):
        """No number means nothing downstream can sort, rank or promote on it —
        which is what keeps this a de-escalation (A7) rather than a signal."""
        v = cr.cold_read_verdict(LIVE_POST, provenance="press_lane", cfg=ARMED,
                                 _call=_reply(True, "dangling_reference", "no 'this'"))
        for value in v.values():
            assert not isinstance(value, (int, float)) or isinstance(value, bool)

    def test_it_never_returns_replacement_text(self):
        """A gate that hands back a rewrite is an editor. Nothing in the verdict
        may be mistakable for copy."""
        v = cr.cold_read_verdict(
            LIVE_POST, provenance="press_lane", cfg=ARMED,
            _call=lambda t, c: ('{"blocked": true, "category": "dangling_reference",'
                                ' "reason": "no antecedent",'
                                ' "rewrite": "South Korea core inflation hits a high"}'),
        )
        assert set(v) == {"blocked", "category", "reason", "mode", "action"}
        assert "rewrite" not in v
        assert len(v["reason"]) <= 120

    def test_a_pass_cannot_promote_anything(self):
        v = cr.cold_read_verdict(CLEAN_POST, provenance="press_lane", cfg=ARMED,
                                 _call=_reply(False))
        assert v["blocked"] is False
        assert set(v) == {"blocked", "category", "reason", "mode", "action"}


# ── 6. It ships dark ─────────────────────────────────────────────────────────

class TestShipsInShadow:
    def test_the_default_action_is_shadow(self):
        assert cr.resolve_action(None) == "shadow"
        assert cr.resolve_action({}) == "shadow"
        assert cr.resolve_action({"action": "nonsense"}) == "shadow"
        assert cr.resolve_action({"action": "quarantine"}) == "quarantine"

    def test_the_shipped_config_is_in_shadow(self):
        import yaml
        cfg = (yaml.safe_load((ROOT / "config" / "marketing.yml")
                              .read_text(encoding="utf-8")) or {}).get("cold_read", {})
        assert cfg.get("action") == "shadow", (
            "arming this gate is an operator decision made after reading a week "
            "of shadow notices — not something a PR does on the way past")
        assert cfg.get("provider_order") == ["ollama"]

    def test_the_publisher_only_quarantines_on_the_terminal_rung(self):
        """"hold" leaves the item queued for another pass; only "quarantine" is
        terminal. A model veto deserves the reversible rung as its first armed
        step, so the two must not share a branch."""
        src = (ROOT / "scripts" / "marketing_publisher.py").read_text(encoding="utf-8")
        block = src.split("-- cold read:", 1)[1].split("-- run dedup", 1)[0]
        assert 'if _cold["action"] == "quarantine":' in block
        assert '_outbox.transition(iid, "quarantined"' in block
        # the transition must sit INSIDE the quarantine branch, not beside it
        after = block.split('if _cold["action"] == "quarantine":', 1)[1]
        assert '_outbox.transition(iid, "quarantined"' in after.split("if ")[0]


# ── 7. One string, one verdict ───────────────────────────────────────────────

class TestDeterminism:
    def test_the_same_text_is_read_once(self):
        calls = []

        def _spy(text, cfg):
            calls.append(text)
            return _reply(True, "dangling_reference", "no antecedent")(text, cfg)

        a = cr.cold_read_verdict(LIVE_POST, provenance="press_lane", cfg=ARMED,
                                 _call=_spy)
        b = cr.cold_read_verdict(LIVE_POST, provenance="press_lane", cfg=ARMED,
                                 _call=_spy)
        assert a["blocked"] == b["blocked"] == True   # noqa: E712
        assert len(calls) == 1, "the publisher sees one item across two passes"


# ── 8. The prompt is the design ──────────────────────────────────────────────

class TestPrompt:
    def test_the_prompt_names_every_authorised_category_and_nothing_else(self):
        system, _user = cr.prompt_for(LIVE_POST)
        for category in cr.BLOCK_CATEGORIES:
            assert category in system, category

    def test_the_prompt_forbids_the_editor_reasons(self):
        """The negative list is what stops a model becoming an editor at the
        prompt level, before the enum has to catch it at the code level."""
        system, _ = cr.prompt_for(LIVE_POST)
        low = system.lower()
        for phrase in ("do not block", "boring", "tone", "not your call",
                       "passing is the normal answer"):
            assert phrase in low, phrase

    def test_the_prompt_states_the_reader_sees_only_the_post(self):
        system, user = cr.prompt_for(LIVE_POST)
        assert "only" in system.lower()
        assert LIVE_POST in user

    def test_prompt_for_is_pure(self):
        assert cr.prompt_for(LIVE_POST) == cr.prompt_for(LIVE_POST)


# ── 9. It cannot stall or leak a long-running publisher ──────────────────────

class TestBudgets:
    def test_the_per_run_read_budget_is_reported_not_silent(self):
        """NO SILENT CAPS. The publisher's loop reaches this gate for every item
        it CONSIDERS, so a wedged local endpoint could stall a sweep one timeout
        at a time. A budget is right — a budget that truncates coverage without
        saying so is the same defect in a different coat, because a screen that
        read nothing and reported nothing looks exactly like a clean run."""
        cr.reset_run_budget()
        cfg = {**ARMED, "max_reads_per_run": 2}
        seen = []
        for i in range(5):
            cr._MEMO.clear()   # force a distinct read each time
            v = cr.cold_read_verdict(f"{CLEAN_POST} #{i}", provenance="press_lane",
                                     cfg=cfg, _call=_reply(False))
            seen.append(v["mode"])
        assert seen[:2] == ["read", "read"]
        assert seen[2:] == ["budget_exhausted"] * 3
        assert all(m != "read" for m in seen[2:])

    def test_reset_run_budget_starts_a_fresh_sweep(self):
        cr.reset_run_budget()
        cfg = {**ARMED, "max_reads_per_run": 1}
        cr._MEMO.clear()
        assert cr.cold_read_verdict("a post about copper 1", provenance="press_lane",
                                    cfg=cfg, _call=_reply(False))["mode"] == "read"
        cr._MEMO.clear()
        assert cr.cold_read_verdict("a post about copper 2", provenance="press_lane",
                                    cfg=cfg, _call=_reply(False))["mode"] == "budget_exhausted"
        cr.reset_run_budget()
        cr._MEMO.clear()
        assert cr.cold_read_verdict("a post about copper 3", provenance="press_lane",
                                    cfg=cfg, _call=_reply(False))["mode"] == "read"

    def test_an_exhausted_budget_never_blocks(self):
        """The fail-open direction holds for the budget too — an unread item is
        an UNSCREENED item, never a held one."""
        cr.reset_run_budget()
        cfg = {**ARMED, "max_reads_per_run": 0 if False else 1}
        cr._MEMO.clear()
        cr.cold_read_verdict("first", provenance="press_lane", cfg=cfg,
                             _call=_reply(True, "dangling_reference", "x"))
        cr._MEMO.clear()
        v = cr.cold_read_verdict(LIVE_POST, provenance="press_lane", cfg=cfg,
                                 _call=_reply(True, "dangling_reference", "no 'this'"))
        assert v["mode"] == "budget_exhausted"
        assert v["blocked"] is False

    def test_the_memo_is_bounded(self):
        """The press fastlane daemon is long-running: a dict keyed on every post
        text a process ever saw is a slow leak in the one service that never
        restarts on its own."""
        cr.reset_run_budget()
        cfg = {**ARMED, "max_reads_per_run": 10_000}
        cr._MEMO.clear()
        for i in range(cr._MEMO_CAP + 50):
            cr.cold_read_verdict(f"post number {i} about copper", provenance="press_lane",
                                 cfg=cfg, _call=_reply(False))
        assert len(cr._MEMO) <= cr._MEMO_CAP

    def test_the_publisher_resets_the_budget_each_sweep(self):
        src = (ROOT / "scripts" / "marketing_publisher.py").read_text(encoding="utf-8")
        assert "_cold_read_reset()" in src, (
            "without a per-sweep reset the budget is a per-PROCESS cap and the "
            "daemon's second sweep reads nothing at all")
