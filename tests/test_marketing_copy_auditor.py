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

    def test_it_only_audits_the_shipping_day(self):
        """D1 is the only day that has ever enqueued; auditing the forward tail
        spends model calls judging posts that cannot post."""
        import inspect
        from engine.marketing import content_studio
        src = inspect.getsource(content_studio)
        seg = src[src.index("copy_auditor as _auditor"):][:2000]
        assert 'startswith("D1-")' in seg

    def test_it_audits_per_account(self):
        """'Does this feed read like a bot' is a question about ONE timeline.
        A repeat across two desks is invisible to any reader."""
        import inspect
        from engine.marketing import content_studio
        src = inspect.getsource(content_studio)
        seg = src[src.index("copy_auditor as _auditor"):][:2000]
        assert "for _row in account_rows:" in seg

    def test_an_auditor_failure_cannot_break_the_night(self):
        import inspect
        from engine.marketing import content_studio
        src = inspect.getsource(content_studio)
        seg = src[src.index("copy_auditor as _auditor"):][:3000]
        assert "except Exception" in seg
        assert "marketing-auditor-failed" in seg

    def test_cuts_carry_the_text_and_the_reason(self):
        """A gate that prints only a count is the tinted window again."""
        import inspect
        from engine.marketing import content_studio
        src = inspect.getsource(content_studio)
        seg = src[src.index("copy_auditor as _auditor"):][:3000]
        for field in ('"codes"', '"note"', '"text"'):
            assert field in seg, f"cut record missing {field}"
