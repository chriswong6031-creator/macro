"""tests/test_marketing_copy_yield.py — W4e copy-lane yield (masterplan §8).

Program: ``research/X_GROWTH_SUPERINTELLIGENCE_MASTERPLAN_BY_FABLE.md`` §8.2 W4e.

THE NIGHT THIS FILE EXISTS FOR (2026-08-02, in production). The copy lane
attempted 79 posts and shipped 7. The single largest cause was 32 drops reading
``provider returned no text`` — a string that names an outage and sends the
reader to check credentials. It was neither. That exact string is reachable from
ONE branch of ``copywriter._call``: the provider ANSWERED, the reply was not the
contracted ``{"text": ...}`` object, ``_v2_extract_text`` returned "" and the
item was dropped on the spot with ``fault`` never set — no retry, no failover,
no rung named, and an editorial-looking census entry for a post no validator
ever saw. Every other provider-fault path in that function sets a named reason
(``provider_no_text:``, ``provider_error:``, ``provider_refusal``,
``provider_unavailable:``), so the legacy string is a fingerprint, not a
coincidence.

And the second cause, 19 ``number soup`` drops, was the prompt fighting its own
validator: the HARD BANS block ordered "ONE number per post" while
``number_budget_for`` — the single source of truth — has never once returned 1.
On all 154 items of that plan the model was handed a cap no post could satisfy
and that no gate enforced.

TWO LAWS BIND EVERY TEST HERE:

  * A PROVIDER drop (nothing usable came back) may be retried. An EDITORIAL drop
    (a validator refused a draft the model wrote) may not, and the tests below
    pin BOTH directions — a one-directional guard leaves the quiet half open.
  * NO GATE MOVES. ``_NUMBER_BUDGET``, ``_SHAPE_NUMBER_BUDGET`` and
    ``_NUMBER_BUDGET_DEFAULT`` are pinned by value here precisely because the
    fix is next door to them: what changed is what the writer is TOLD, never
    what the validator ALLOWS.

Fixture-driven; ZERO live network, ZERO live LLM. Every provider-path test hands
``engine.llm_auth.build_providers`` a fake provider whose client is a local
object, so the REAL waterfall and the REAL request builder run and only the
transport is fake.
"""
from __future__ import annotations

import json
import re
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

from engine import llm_auth  # noqa: E402
from engine.marketing import copy_critic  # noqa: E402
from engine.marketing import copywriter as cw  # noqa: E402

PLAN_PATH = ROOT / "data" / "marketing" / "content_plan.json"
STUDIO_PATH = ROOT / "engine" / "marketing" / "content_studio.py"


# ─────────────────────────────────────────────────────────────────────────────
# Harness — a scripted provider ladder, no network
# ─────────────────────────────────────────────────────────────────────────────

CRITIC_OFF_CFG = {
    "copy_laws": [],
    "llm": {
        "enabled": True,
        "per_post_max_tokens": 400,
        "max_workers": 2,
        "critic": {"enabled": False},
    },
}


class _Block:
    def __init__(self, text: str) -> None:
        self.type = "text"
        self.text = text


class _Resp:
    """A normal HTTP 200 carrying a text block."""

    def __init__(self, text: str) -> None:
        self.content = [_Block(text)]
        self.stop_reason = "end_turn"
        self.usage = None


class _ThinkBlock:
    def __init__(self, kind: str = "thinking") -> None:
        self.type = kind


class _EmptyResp:
    """The 07-31 outage shape: reasoning only, budget exhausted, HTTP 200."""

    def __init__(self, stop_reason: str = "max_tokens") -> None:
        self.content = [_ThinkBlock()]
        self.stop_reason = stop_reason
        self.usage = None


class _LedgerMessages:
    """Records every request and returns whatever the script says."""

    def __init__(self, name, script, ledger) -> None:
        self._name = name
        self._script = script
        self._ledger = ledger

    def create(self, *, model, max_tokens, system, messages, extra_body=None):
        call = {"provider": self._name, "max_tokens": max_tokens,
                "extra_body": extra_body, "system": system,
                "user": messages[0]["content"]}
        self._ledger.append(call)
        n = sum(1 for c in self._ledger if c["provider"] == self._name)
        return self._script(n=n, call=call)


class _LedgerClient:
    def __init__(self, name, script, ledger) -> None:
        self.messages = _LedgerMessages(name, script, ledger)


def _arm_ladder(monkeypatch, rungs):
    """Arm a MULTI-rung waterfall. Returns the shared call ledger."""
    monkeypatch.setenv("MARKETING_LLM_ENABLED", "1")
    ledger: list[dict] = []
    providers = [{
        "name": name,
        "env_var": f"ENV_{name.upper()}",
        "cred": "not-a-real-token",
        "client": _LedgerClient(name, script, ledger),
        "model": f"model-{name}",
    } for name, script in rungs]
    monkeypatch.setattr(llm_auth, "build_providers", lambda *a, **k: providers)
    llm_auth.clear_dead()
    cw.reset_writer_stats()
    copy_critic.reset_critic_stats()
    return ledger


GOOD_POST = "$ARES dipped back to 122 and held. Not chasing it here."
#: A reply that ARRIVED and is not the contracted object. Verbatim-shaped after
#: the wrappers models actually add: a sentence of preamble and no JSON at all.
UNREADABLE = "Sure thing! Here is a post for you: $ARES dipped back to 122."


def _good(text: str = GOOD_POST):
    return lambda **_kw: _Resp(json.dumps({"text": text}))


def _unreadable(**_kw):
    return _Resp(UNREADABLE)


def _always_empty(**_kw):
    return _EmptyResp()


def _chart_ctx(ticker: str = "ARES", price: str = "121.66", **over) -> dict:
    """A real build_context for a chart item, so rounding is exercised too."""
    facts = {
        "facts": [{
            "id": "poc_retest_hold",
            "text": f"{ticker} dipped back to {price} and held.",
            "salience": 7,
            "numbers": [price],
        }],
        "numbers_whitelist": [price],
    }
    ctx = cw.build_context(
        {"ticker": ticker, "type": "chart", "account": "testdesk"},
        persona={"name": "Test", "voice_notes": "Emoji budget: 0",
                 "example_lines": []},
        facts=facts,
    )
    ctx["type"] = "chart"
    ctx["voice"] = "authoritative desk"
    ctx["shape"] = "one_liner"
    ctx["angle"] = "level_watch"
    ctx.update(over)
    return ctx


# ─────────────────────────────────────────────────────────────────────────────
# 1. THE 32 DROPS. A reply that arrived and could not be read.
# ─────────────────────────────────────────────────────────────────────────────

class TestAnUnreadableReplyIsAProviderFaultAndIsRetried:

    def test_the_legacy_string_is_reachable_from_exactly_one_branch(self):
        """WHY THIS FILE BLAMES THE PARSE AND NOT THE CREDENTIALS.

        The whole diagnosis rests on one claim: every OTHER way `_call` can
        return "" writes a named reason into `fault`, so a drop carrying the
        bare legacy string can only have come from a reply that arrived and did
        not parse. Pinned at source level because it is an argument about
        control flow, not about any one run — if a future edit adds a second
        silent path, the 08-02 census becomes ambiguous again and this goes red.
        """
        import inspect

        src = inspect.getsource(cw._v2_write_one)
        # The fallback exists for artifacts written by older builds; it must
        # stay UNREACHABLE from live code.
        assert 'or "provider returned no text"' in src
        returns_empty = [ln.strip() for ln in src.splitlines()
                         if ln.strip() == 'return ""']
        # Each of those sites is guarded by a fault["reason"] assignment or by
        # the shared _one_more_rung tail, which always names a family.
        assert src.count('fault["reason"]') >= 4, src.count('fault["reason"]')
        assert len(returns_empty) >= 3, returns_empty
        assert 'family="unreadable_reply"' in src

    def test_an_unreadable_reply_fails_over_and_the_post_ships(self, monkeypatch):
        """THE LOAD-BEARING FIX. Pre-fix this item was dropped after ONE call.

        The rung answered, so `make_call` stopped walking and the healthy rungs
        below it were never asked — the same gap the textless class already had
        closed, on a branch that returned before reaching it.
        """
        ledger = _arm_ladder(monkeypatch, [
            ("codex", _unreadable), ("oauth", _good()),
            ("anthropic", _good("never reached")),
        ])
        posts = cw.write_posts_llm_v2([_chart_ctx()], CRITIC_OFF_CFG)

        assert posts[0]["mode"] == "llm", posts[0]
        assert posts[0]["text"] == GOOD_POST
        assert [c["provider"] for c in ledger] == ["codex", "oauth"], ledger
        stats = cw.writer_stats()
        assert stats["unreadable_replies"] == 1
        assert stats["unreadable_reasks"] == 1
        assert stats["provider_recovered"] == 1
        assert stats["dropped_provider"] == 0

    def test_the_reask_restates_the_output_shape_and_changes_nothing_else(
            self, monkeypatch):
        """The re-ask is a REPAIR of the envelope, not of the post.

        A retry that quietly asked for something easier would be a gate
        relaxation wearing a retry's clothes. Pinned: the item payload is
        byte-identical, the appended text names only the output object, and it
        carries no instruction that touches the copy laws.
        """
        ledger = _arm_ladder(monkeypatch, [
            ("codex", _unreadable), ("oauth", _good())])
        cw.write_posts_llm_v2([_chart_ctx()], CRITIC_OFF_CFG)

        first, second = ledger[0]["user"], ledger[1]["user"]
        assert second.startswith(first), "the item itself must be unchanged"
        added = second[len(first):]
        assert added == cw._OUTPUT_SHAPE_REMINDER
        assert "COULD NOT BE READ" in added
        assert "same laws, same shape, same numbers" in added
        for softener in ("simpler", "shorter", "ignore", "skip", "you may"):
            assert softener not in added.lower(), added

    def test_the_last_rung_gets_one_reask_on_itself_rather_than_a_silent_drop(
            self, monkeypatch):
        """An unreadable reply is a model output-shape fault, not a dead rung.

        The textless class must NEVER re-ask the rung that served nothing (a
        silent rung is the suspect). This class must, when there is nothing
        below it: the credential is demonstrably alive, and the thing that
        failed is something the model can be told about.
        """
        def script(*, n, call):
            return _Resp(UNREADABLE) if n == 1 else _Resp(
                json.dumps({"text": GOOD_POST}))

        ledger = _arm_ladder(monkeypatch, [("codex", script)])
        posts = cw.write_posts_llm_v2([_chart_ctx()], CRITIC_OFF_CFG)

        assert posts[0]["mode"] == "llm", posts[0]
        assert [c["provider"] for c in ledger] == ["codex", "codex"], ledger
        assert cw._OUTPUT_SHAPE_REMINDER in ledger[1]["user"]
        assert cw.writer_stats()["provider_recovered"] == 1

    def test_a_textless_last_rung_still_never_gets_the_extra_reask(
            self, monkeypatch):
        """THE INVERSE. The two families must not collapse into each other.

        `_always_empty` buys the ONE same-provider retry that already existed
        (thinking off) and then stops. If the unreadable branch's same-rung
        re-ask leaked into this family, a dead rung would be asked three times
        per item across a whole night.
        """
        ledger = _arm_ladder(monkeypatch, [("codex", _always_empty)])
        posts = cw.write_posts_llm_v2([_chart_ctx()], CRITIC_OFF_CFG)

        assert posts[0]["reasons"] == ["provider_no_text:codex"], posts[0]
        assert len(ledger) == 2, ledger
        assert cw.writer_stats()["unreadable_reasks"] == 0

    def test_two_unreadable_rungs_drop_with_a_reason_that_names_the_class(
            self, monkeypatch):
        """The census entry an operator can act on.

        "provider returned no text" pointed at credentials; four were checked on
        07-31 and all four were fine. `unreadable_reply:codex+oauth` says the
        rungs answered, names them, and by naming the CLASS says the fix is the
        prompt/parse, not the key.
        """
        ledger = _arm_ladder(monkeypatch, [
            ("codex", _unreadable), ("oauth", _unreadable)])
        posts = cw.write_posts_llm_v2([_chart_ctx()], CRITIC_OFF_CFG)

        assert posts[0]["mode"] == "dropped"
        assert posts[0]["stage"] == "provider"
        assert posts[0]["reasons"] == ["unreadable_reply:codex+oauth"], posts[0]
        assert "text" not in posts[0], "a dropped item must carry no post text"
        assert [c["provider"] for c in ledger] == ["codex", "oauth"], ledger
        assert cw.writer_stats()["dropped_provider"] == 1

    def test_an_unreadable_SECOND_reply_does_not_escape_under_the_legacy_string(
            self, monkeypatch):
        """MUTATION-SHAPED: the pre-fix laundering, one line deeper.

        The old failover tail was `if raw2: return _v2_extract_text(raw2)`, so a
        failover rung that ALSO answered unreadably produced "" with `fault`
        still empty and the item died under the legacy string again. This is the
        same defect the whole fix is about, and it lived inside the fix.
        """
        ledger = _arm_ladder(monkeypatch, [
            ("codex", _unreadable), ("oauth", _unreadable)])
        posts = cw.write_posts_llm_v2([_chart_ctx()], CRITIC_OFF_CFG)

        assert "provider returned no text" not in posts[0]["reasons"], posts[0]
        assert len(ledger) == 2, ledger


# ─────────────────────────────────────────────────────────────────────────────
# 2. RETRYING A PROVIDER FAULT IS NOT WEAKENING A GATE
# ─────────────────────────────────────────────────────────────────────────────

class TestTheGatesStillFireOnWhateverComesBack:

    def test_a_recovered_reply_that_breaks_a_copy_law_is_still_dropped(
            self, monkeypatch):
        """The recovery buys an ANSWER, never a pass.

        The failover rung answers in the contracted shape with a fabricated
        price. The item is recovered from the provider stage and then dies at
        the validate stage, which is the whole distinction this wave draws.
        """
        ledger = _arm_ladder(monkeypatch, [
            ("codex", _unreadable),
            ("oauth", _good("$ARES ripped to 999.99 and never looked back.")),
        ])
        posts = cw.write_posts_llm_v2([_chart_ctx()], CRITIC_OFF_CFG)

        assert posts[0]["mode"] == "dropped"
        assert posts[0]["stage"] == "validate", posts[0]
        assert any("999.99" in r for r in posts[0]["reasons"]), posts[0]
        # Twice: the draft turn AND the editorial repair turn each start at the
        # top of the waterfall, so each one pays the unreadable rung and then
        # recovers. That is the honest cost of a bad rung sitting at the head of
        # `provider_order`, and it is bounded at one extra call per turn.
        assert cw.writer_stats()["provider_recovered"] == 2
        assert [c["provider"] for c in ledger] == [
            "codex", "oauth", "codex", "oauth"], ledger

    def test_an_editorial_rejection_never_reaches_the_provider_recovery(
            self, monkeypatch):
        """THE INVERSE GUARD. A post the copy laws refuse is a content outcome.

        If a validate-stage failure could enter the provider ladder, every picky
        night would multiply model spend by the depth of the waterfall and a
        voice problem would read as an outage.
        """
        bad = _good("$ARES ripped to 999.99 and never looked back.")
        ledger = _arm_ladder(monkeypatch, [("codex", bad), ("oauth", _good())])
        posts = cw.write_posts_llm_v2([_chart_ctx()], CRITIC_OFF_CFG)

        assert posts[0]["stage"] == "validate", posts[0]
        assert {c["provider"] for c in ledger} == {"codex"}, ledger
        stats = cw.writer_stats()
        assert stats["unreadable_replies"] == 0
        assert stats["unreadable_reasks"] == 0
        assert stats["provider_failovers"] == 0

    def test_a_repair_turn_that_never_answered_is_not_an_editorial_drop(
            self, monkeypatch):
        """THE LAUNDERING THIS FIXES, on the largest stage in the census.

        Pre-fix: the first draft violates, the repair turn faults, `retry` is
        "" so `violations` still holds the FIRST round's list, and the item is
        reported at stage=validate — a provider fault counted as "the copy laws
        refused it", on the one split the outage breaker reads.
        """
        def script(*, n, call):
            if n == 1:
                return _Resp(json.dumps(
                    {"text": "$ARES ripped to 999.99 and never looked back."}))
            return _EmptyResp()

        _arm_ladder(monkeypatch, [("codex", script)])
        posts = cw.write_posts_llm_v2([_chart_ctx()], CRITIC_OFF_CFG)

        assert posts[0]["mode"] == "dropped"
        assert posts[0]["stage"] == "provider", posts[0]
        assert posts[0]["reasons"][0].startswith("repair_unanswered:"), posts[0]
        # The editorial evidence is KEPT, not thrown away: the census still says
        # what the first draft was being repaired for.
        assert any("999.99" in r for r in posts[0]["reasons"][1:]), posts[0]
        stats = cw.writer_stats()
        assert stats["dropped_provider"] == 1
        assert stats["dropped_validate"] == 0


# ─────────────────────────────────────────────────────────────────────────────
# 3. THE ALARM FLOOR — a quarter of the day may not vanish quietly
# ─────────────────────────────────────────────────────────────────────────────

class TestTheProviderFaultAlarmFiresWellBelowFiftyPercent:

    @staticmethod
    def _ctxs(n: int) -> list[dict]:
        return [_chart_ctx(ticker=f"AA{i:02d}") for i in range(n)]

    @staticmethod
    def _mixed(n_bad: int):
        """Unreadable for the first `n_bad` tickers, contracted for the rest."""
        bad = {f"$AA{i:02d}" for i in range(n_bad)}

        def script(*, n, call):
            user = call["user"]
            if any(t in user for t in bad):
                return _Resp(UNREADABLE)
            return _Resp(json.dumps({"text": GOOD_POST}))

        return script

    def test_four_in_ten_lost_at_the_provider_stage_fires_an_error(
            self, monkeypatch, capsys):
        """40% is a green run today: content_studio's breaker trips above 50%."""
        _arm_ladder(monkeypatch, [("codex", self._mixed(4))])
        posts = cw.write_posts_llm_v2(self._ctxs(10), CRITIC_OFF_CFG)

        n_prov = sum(1 for p in posts if p.get("stage") == "provider")
        assert n_prov == 4, [p.get("stage") for p in posts]
        out = capsys.readouterr().out
        line = next((ln for ln in out.splitlines()
                     if "marketing_copy_provider_faults" in ln), "")
        assert line, out
        assert line.startswith("::error title=marketing_copy_provider_faults::"), line
        assert "4 of 10 attempted posts (40%" in line, line
        assert "LOST SUPPLY" in line, line

    def test_it_fires_at_twenty_percent_which_the_breaker_ignores(
            self, monkeypatch, capsys):
        """The 08-02 shape at its census reading: 28% of the drop reasons, a
        quarter of the day, and completely silent before this."""
        _arm_ladder(monkeypatch, [("codex", self._mixed(3))])
        cw.write_posts_llm_v2(self._ctxs(15), CRITIC_OFF_CFG)

        out = capsys.readouterr().out
        assert "::error title=marketing_copy_provider_faults::" in out, out
        assert "3 of 15 attempted posts (20%" in out, out

    def test_one_unlucky_item_on_a_small_desk_stays_quiet(
            self, monkeypatch, capsys):
        """An alarm that fires on every four-item desk is an alarm nobody reads.
        The floor is a COUNT as well as a share, and this pins the count half."""
        _arm_ladder(monkeypatch, [("codex", self._mixed(1))])
        cw.write_posts_llm_v2(self._ctxs(4), CRITIC_OFF_CFG)

        assert "marketing_copy_provider_faults" not in capsys.readouterr().out

    def test_a_clean_desk_says_nothing(self, monkeypatch, capsys):
        _arm_ladder(monkeypatch, [("codex", _good())])
        cw.write_posts_llm_v2([_chart_ctx()], CRITIC_OFF_CFG)

        assert "marketing_copy_provider_faults" not in capsys.readouterr().out

    def test_the_alarm_steers_to_the_output_shape_when_that_is_the_fault(
            self, monkeypatch, capsys):
        """The 07-31 remedy sent an operator to check four credentials that were
        all fine. When the replies ARRIVED, the alarm must say so in words."""
        _arm_ladder(monkeypatch, [("codex", self._mixed(4))])
        cw.write_posts_llm_v2(self._ctxs(10), CRITIC_OFF_CFG)

        out = capsys.readouterr().out
        assert "UNREADABLE REPLIES" in out, out
        assert "will not touch it" in out, out
        assert "unreadable_reply=4" in out, out

    def test_the_alarm_steers_to_the_rungs_when_they_really_are_silent(
            self, monkeypatch, capsys):
        """...and the other way, because a one-directional steer is half a
        diagnosis: four textless rungs IS the credential/rung question."""
        _arm_ladder(monkeypatch, [("codex", _always_empty)])
        cw.write_posts_llm_v2(self._ctxs(4), CRITIC_OFF_CFG)

        out = capsys.readouterr().out
        assert "provider_order" in out, out
        assert "UNREADABLE REPLIES" not in out, out
        assert "provider_no_text=4" in out, out

    def test_the_floor_really_is_below_the_studio_breaker(self):
        """The point of the whole alarm: it must live UNDER the 50% breaker.

        Read from content_studio's source rather than imported — that module is
        another lane's territory and an import couples this file to whatever it
        is mid-edit. The claim under test is a number, and the number is there.
        """
        src = STUDIO_PATH.read_text(encoding="utf-8")
        m = re.search(r"^_PROVIDER_OUTAGE_SHARE\s*=\s*([0-9.]+)", src, re.M)
        assert m, "content_studio no longer declares _PROVIDER_OUTAGE_SHARE"
        assert cw._PROVIDER_FAULT_ALARM_SHARE < float(m.group(1))
        assert cw._PROVIDER_FAULT_ALARM_SHARE <= 0.15, "materially degrading != half"

    def test_the_annotation_starts_the_line_and_is_never_logged(self):
        """A `::error` behind this module's prefixing formatter is not a line
        start and GitHub drops it silently — it shipped dead five times."""
        import inspect

        src = inspect.getsource(cw._provider_fault_alarm)
        assert 'print(f"::error title=marketing_copy_provider_faults::' in src
        assert "flush=True" in src
        assert not re.search(r"log\.\w+\(\s*f?[\"']::", src), src

    def test_the_alarm_never_breaks_the_writer(self, monkeypatch):
        """It is a report on a night that already went wrong. A report that can
        raise turns a bad night into a lost one."""
        cw.reset_writer_stats()
        cw._provider_fault_alarm(None, None)  # type: ignore[arg-type]
        cw._provider_fault_alarm([{}] * 10, [{"stage": "provider"}] * 4)
        cw._provider_fault_alarm([1, 2, 3], [{"stage": "provider", "reasons": None}] * 3)


# ─────────────────────────────────────────────────────────────────────────────
# 4. THE PROMPT AND THE VALIDATOR AGREE ON THE NUMBER COUNT
# ─────────────────────────────────────────────────────────────────────────────

class TestTheWriterIsToldTheBudgetTheValidatorEnforces:

    def test_the_blanket_one_number_rule_is_gone_from_the_live_prompt(self):
        """It contradicted the per-shape contract in the SAME request and named
        a cap `number_budget_for` cannot return. An instruction whose compliance
        is a rejection teaches the model that the instructions are noise."""
        prompt = cw._v2_system_prompt({})
        assert "ONE number per post" not in prompt
        assert "number_budget" in prompt

    def test_the_budget_the_model_reads_is_the_object_the_gate_reads(self):
        """Not a copy of the number: the same call, so a one-sided edit is
        impossible. Every kind x shape pair, including the ones where the KIND
        widens past what shape_contract quotes."""
        for kind in ("chart", "signal", "receipt", "earnings", "macro", ""):
            for shape in (*cw.SHAPES, "not_a_shape"):
                ctx = _chart_ctx(type=kind, shape=shape)
                payload = cw._v2_item_payload(
                    ctx, persona_card=None, codex_by_account={},
                    memory_by_account={})
                assert payload["number_budget"] == cw.number_budget_for(
                    kind=kind, shape=shape), (kind, shape)

    def test_a_receipt_is_told_four_where_its_shape_contract_says_two(self):
        """The half the shape prose structurally cannot carry. A receipt's
        numbers ARE the fact; written as a two_part its contract still quotes
        the shape budget of 2, and the validator allows 4."""
        ctx = _chart_ctx(type="receipt", shape="two_part")
        payload = cw._v2_item_payload(ctx, persona_card=None,
                                      codex_by_account={}, memory_by_account={})
        assert payload["number_budget"] == 4
        assert "at most 2 numbers" in payload["shape_contract"].lower()

    def test_the_contract_line_tells_the_model_which_one_wins(self):
        """Shipping the field without saying what it BINDS is the autopsy-3
        defect: an unexplained JSON key reads as decoration."""
        block = cw._V2_PAYLOAD_CONTRACT_BLOCK
        assert re.search(r"(?m)^- [^\n:]*\bnumber_budget\b[^\n]*:", block)
        assert "number_budget" in cw.V2_PAYLOAD_CONTRACT_KEYS
        low = block.lower()
        assert "ceiling, never a target" in low
        assert "this is the one that counts" in low

    def test_the_writer_actually_ships_the_field(self, monkeypatch):
        """End to end through the real request builder: the number reaches the
        model's user turn, not just the payload dict."""
        ledger = _arm_ladder(monkeypatch, [("codex", _good())])
        cw.write_posts_llm_v2([_chart_ctx(type="receipt", shape="list")],
                              CRITIC_OFF_CFG)
        item = json.loads(ledger[0]["user"].split("ITEM:\n", 1)[1])
        assert item["number_budget"] == 6

    # ── THE GATE DID NOT MOVE. This is the §8.0 gate-2 proof. ────────────────

    def test_the_budget_table_is_byte_for_byte_what_it_was(self):
        """W4e is allowed to change what the writer is TOLD and nothing else.
        Pinned by value next to the fix, because that is where a 'while I'm
        here' edit would land."""
        assert cw._NUMBER_BUDGET == {"receipt": 4, "earnings": 4}
        assert cw._NUMBER_BUDGET_DEFAULT == 2
        assert cw._SHAPE_NUMBER_BUDGET == {
            "one_liner": 2, "two_part": 2, "caption": 2, "stack": 3, "list": 6}

    def test_the_validator_still_rejects_one_number_over_budget(self):
        """A told budget is not a raised budget: budget+1 still dies, on every
        shape, and the message still names the count."""
        for shape, limit in cw._SHAPE_NUMBER_BUDGET.items():
            nums = [f"{10 + i}.{i}" for i in range(limit + 1)]
            text = " then ".join(nums) + "."
            assert cw.number_soup_violations(text, shape=shape) != [], shape
            assert cw.number_soup_violations(
                " then ".join(nums[:limit]) + ".", shape=shape) == [], shape


# ─────────────────────────────────────────────────────────────────────────────
# 5. THE REAL ARTIFACT — tonight's plan, not a fixture
# ─────────────────────────────────────────────────────────────────────────────

class TestAgainstTheShippedPlan:
    """Reads `data/marketing/content_plan.json` when it is present.

    The plan is regenerated nightly, so nothing here pins its CONTENTS. What is
    pinned is the invariant that produced the 19 rejections: for every (kind,
    shape) pair the plan actually carries, the number the writer is handed is
    the number the validator will count.
    """

    @staticmethod
    def _pairs() -> list[tuple[str, str]]:
        if not PLAN_PATH.exists():
            pytest.skip("no content_plan.json in this checkout")
        try:
            plan = json.loads(PLAN_PATH.read_text(encoding="utf-8"))
        except ValueError:
            pytest.skip("content_plan.json is not readable JSON")
        out = []
        for acct in plan.get("accounts") or []:
            for item in acct.get("queue") or []:
                out.append((str(item.get("type") or ""),
                            str(item.get("shape") or cw.DEFAULT_SHAPE)))
        if not out:
            pytest.skip("the shipped plan carries no queue items")
        return out

    def test_the_shipped_plan_has_items_to_scan(self):
        """A scan over an empty iterable is a green light. Pin the supply."""
        assert len(self._pairs()) >= 1

    def test_no_planned_item_is_told_a_cap_its_validator_would_refuse(self):
        """On the 08-02 plan this was 154 of 154 items: every one was told ONE
        while the gate counted 2, 3 or 6."""
        bad = []
        for kind, shape in self._pairs():
            ctx = _chart_ctx(type=kind, shape=shape)
            payload = cw._v2_item_payload(ctx, persona_card=None,
                                          codex_by_account={},
                                          memory_by_account={})
            enforced = cw.number_budget_for(kind=kind, shape=shape)
            if payload["number_budget"] != enforced or enforced < 1:
                bad.append((kind, shape, payload["number_budget"], enforced))
        assert bad == [], bad

    def test_the_prompt_states_no_flat_cap_any_planned_item_would_break(self):
        """The other half: the per-item field is only worth shipping if the
        account-invariant prose above it has stopped contradicting it."""
        prompt = cw._v2_system_prompt({})
        assert not re.search(r"\bONE number per post\b", prompt)
        enforced = {cw.number_budget_for(kind=k, shape=s)
                    for k, s in self._pairs()}
        assert enforced and min(enforced) >= 2, enforced
