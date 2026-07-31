"""Batch auditor — the operator's stand-in over a whole day of posts.

Operator order 2026-07-30: an LLM auditor approves or disapproves planned posts
for at least a week, and must stop bot-like, nonsensical, erroneous and
repetitive ones.

The property that justifies a SECOND judge beside the cold-read critic: on a
live 16-post batch the per-post critic passed 16/16 and the exact-match closer
ban passed all 16 too (no two used the same sentence) — while the auditor cut 9
for `repetitive`, each a variation on "I respect the move, I'm not chasing".
Only a reader holding the whole day at once sees that.
"""
from __future__ import annotations

import json

from engine.marketing import copy_auditor as ca


def _posts(n=3):
    return [{"account": "flagship", "kind": "watchlist", "text": f"post {i}"}
            for i in range(n)]


class TestNeverRaises:
    def test_empty_batch(self):
        r = ca.audit_batch([], cfg=None)
        assert r["ok"] is True and r["verdicts"] == []

    def test_junk_input_does_not_raise(self):
        r = ca.audit_batch([None, 3, "x"], cfg=None)  # type: ignore[list-item]
        assert isinstance(r, dict) and "verdicts" in r

    def test_disabled_marks_unaudited_not_pass(self, monkeypatch):
        monkeypatch.setenv(ca._ENV_FLAG, "1")
        cfg = {"copywriter": {"llm": {"auditor": {"enabled": False}}}}
        r = ca.audit_batch(_posts(), cfg=cfg)
        assert r["ok"] is False
        assert [v["verdict"] for v in r["verdicts"]] == ["unaudited"] * 3
        assert r["unaudited"] == 3

    def test_unarmed_marks_unaudited(self, monkeypatch):
        monkeypatch.delenv(ca._ENV_FLAG, raising=False)
        r = ca.audit_batch(_posts(), cfg=None)
        assert r["ok"] is False and r["unaudited"] == 3


class TestParsing:
    def test_verdicts_are_index_aligned(self):
        raw = json.dumps({"verdicts": [
            {"n": 1, "verdict": "cut", "codes": ["repetitive"], "note": "dupe"},
            {"n": 3, "verdict": "keep", "codes": []},
        ], "batch_note": "ok"})
        out, err = ca._parse(raw, 3)
        assert err == ""
        assert [v["verdict"] for v in out] == ["cut", "keep", "keep"]
        assert out[1]["note"] == "not judged"   # gap filled, not dropped

    def test_a_cut_with_no_recognised_code_is_downgraded(self):
        """A sloppy reply must not be able to silently delete the day."""
        raw = json.dumps({"verdicts": [
            {"n": 1, "verdict": "cut", "codes": [], "note": "bad"},
            {"n": 2, "verdict": "cut", "codes": ["not_a_real_code"]},
        ]})
        out, _ = ca._parse(raw, 2)
        assert [v["verdict"] for v in out] == ["keep", "keep"]

    def test_out_of_range_indices_are_ignored(self):
        raw = json.dumps({"verdicts": [
            {"n": 99, "verdict": "cut", "codes": ["bot_voice"]},
            {"n": 1, "verdict": "cut", "codes": ["bot_voice"]},
        ]})
        out, _ = ca._parse(raw, 2)
        assert out[0]["verdict"] == "cut" and out[1]["verdict"] == "keep"

    def test_unparseable_reply_reports_why(self):
        for bad in ("", "no json here", "{not json}"):
            out, err = ca._parse(bad, 2)
            assert out is None and err


class TestContract:
    def test_the_operator_criteria_are_all_in_the_prompt(self):
        p = ca._system_prompt()
        for code, _ in ca.AUDIT_CRITERIA:
            assert code in p, f"criterion {code} missing from the prompt"

    def test_the_prompt_forbids_rewriting(self):
        """De-escalation only — the house epistemics law."""
        p = ca._system_prompt().lower()
        assert "only keep or cut" in p
        assert "never rewrite" in p

    def test_the_prompt_tells_it_to_judge_the_batch(self):
        p = ca._system_prompt().lower()
        assert "together" in p and "repetition across" in p

    def test_it_leans_keep_when_unsure(self):
        """A false cut costs a good post; an empty feed costs the day."""
        assert "unsure, keep it" in ca._system_prompt().lower()

    def test_shipped_config_routes_to_terra_not_sol(self):
        import yaml, pathlib
        cfg = yaml.safe_load(pathlib.Path("config/marketing.yml").read_text())
        a = ca._audit_cfg(cfg)
        assert a["codex_source_model"] == "gpt-5.6-terra"
        assert a["provider_order"][0] == "codex"
        assert a["enabled"] is True

    def test_luna_is_never_the_auditor(self):
        import yaml, pathlib
        cfg = yaml.safe_load(pathlib.Path("config/marketing.yml").read_text())
        assert "luna" not in ca._audit_cfg(cfg)["codex_source_model"].lower()



def _auditor_block(src: str) -> str:
    """The auditor wiring, start marker to end marker.

    NOT a fixed-length slice. Adding the cost-monoculture trim above the auditor
    pushed its internals past a [:3000] cut and failed two unrelated tests; a
    literal length is a time bomb that fires on the next insertion.
    """
    start = src.index("copy_auditor as _auditor")
    return src[start:src.index("_surviving_ids = {", start)]


class TestPlanWiring:
    """The auditor is the last gate in content_plan. These pin the properties
    that keep a judge safe inside a publishing path."""

    def test_it_runs_after_copy_and_before_reconciliation(self):
        import inspect
        from engine.marketing import content_studio
        src = inspect.getsource(content_studio)
        audit_at = src.index("from engine.marketing import copy_auditor as _auditor")
        # There are TWO reconciliation blocks; the one that matters is the first
        # one AFTER the auditor, which is what folds its cuts into all_items.
        recon_at = src.index("_surviving_ids = {", audit_at)
        assert audit_at < recon_at, (
            "a cut must leave the plan through the same reconciliation as every "
            "other drop, or all_items and the queues diverge")

    def test_it_audits_the_forward_tail_too(self):
        """WAS: "D1 is the only day that has ever enqueued; auditing the forward
        tail spends model calls judging posts that cannot post."

        That premise was false for the EVERGREEN kinds. Watchlist and receipt
        copy is forward-booked to the full seven-day horizon deliberately, and a
        forward-booked post reaches its slot and ships. The D1 pin left 73
        watchlist posts unjudged on the 2026-07-30 plan.

        The scope now comes from config (auditor.max_day, 0 = whole horizon),
        so the cost lever stays available without a code change.
        """
        import inspect
        from engine.marketing import content_studio
        src = inspect.getsource(content_studio)
        seg = _auditor_block(src)
        assert 'startswith("D1-")' not in seg, (
            "the auditor is hard-pinned to D1 again -- the evergreen forward "
            "tail ships unjudged when it is")
        assert "max_audit_day" in seg, "scope must be resolved from config"

    def test_it_audits_per_account(self):
        """'Does this feed read like a bot' is a question about ONE timeline.
        A repeat across two desks is invisible to any reader."""
        import inspect
        from engine.marketing import content_studio
        src = inspect.getsource(content_studio)
        seg = _auditor_block(src)
        assert "for _row in account_rows:" in seg

    def test_an_auditor_failure_cannot_break_the_night(self):
        import inspect
        from engine.marketing import content_studio
        src = inspect.getsource(content_studio)
        seg = _auditor_block(src)
        assert "except Exception" in seg
        assert "marketing-auditor-failed" in seg

    def test_cuts_carry_the_text_and_the_reason(self):
        """A gate that prints only a count is the tinted window again."""
        import inspect
        from engine.marketing import content_studio
        src = inspect.getsource(content_studio)
        seg = _auditor_block(src)
        for field in ('"codes"', '"note"', '"text"'):
            assert field in seg, f"cut record missing {field}"


class TestAuditScopeIsTheShippingDay:
    """D1 only -- and the reasoning that briefly widened it was WRONG.

    On 2026-07-30 I set max_day to 0 (whole horizon) believing evergreen
    watchlist/receipt copy forward-books and ships on its own day, leaving 73
    D2-D7 posts unjudged. The code contradicts that: `emit_from_content_plan`
    takes `day_prefix="D1"` (outbox.py:1630) and the governor takes the default,
    so ONLY D1 slots are ever emitted. The outbox proves it -- across its entire
    history: 185 D1 items, 4 LIVE, 19 HOT, ZERO D2+.

    D2-D7 is a PROJECTION the next nightly regenerates from fresh facts.
    Auditing it spends model calls on posts that can never post.
    """

    def test_the_shipped_default_is_the_shipping_day(self):
        import yaml
        from engine.marketing.copy_auditor import max_audit_day
        cfg = yaml.safe_load(open("config/marketing.yml", encoding="utf-8"))
        assert max_audit_day(cfg) == 1, (
            "the auditor is reading past D1 again -- those slots never emit"
        )

    def test_only_d1_is_ever_emitted(self):
        """The premise itself, pinned. If this changes, revisit the scope."""
        import inspect
        from engine.marketing import outbox
        sig = inspect.signature(outbox.emit_from_content_plan)
        assert sig.parameters["day_prefix"].default == "D1"

    def test_zero_and_junk_mean_no_limit_but_a_positive_n_still_caps(self):
        from engine.marketing.copy_auditor import max_audit_day
        for value in (0, -3, "nonsense", None):
            assert max_audit_day(
                {"copywriter": {"llm": {"auditor": {"max_day": value}}}}) is None, value
        for value in (1, 7):
            assert max_audit_day(
                {"copywriter": {"llm": {"auditor": {"max_day": value}}}}) == value

    def test_the_scope_is_still_config_driven(self):
        """Widening must stay a config change, not a code change."""
        import inspect
        from engine.marketing import content_studio
        seg = _auditor_block(inspect.getsource(content_studio))
        assert "max_audit_day" in seg
