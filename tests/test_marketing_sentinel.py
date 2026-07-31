"""tests/test_marketing_sentinel.py — Deterministic Sentinel W1 gate tests.

All file writes go to tmp_path — NEVER to repo data/ (MM_DATA_GUARD tripwire).

Coverage:
  - near-dup across accounts caught; same account NOT sentinel's job
  - shared chart_id across accounts quarantined
  - cadence: 5 items one account cap=4 → 5th quarantined
  - 3 items same cashtag → 3rd quarantined
  - slot collision
  - advice_lexicon phrase hit
  - advice_lexicon pattern hit ("will hit $200")
  - missing_disclosure on signal item
  - cherry-pick: window has loss + plan shows only win receipts → quarantine
  - cherry-pick: loss ticker present in plan receipts → pass
  - cherry-pick: window None → skipped recorded
  - stale receipts: age > max → plan refused, all items quarantined
  - stale receipts: age None → only receipt items quarantined
  - stale receipts: age within → no effect
  - kill-switch: publish_enabled() False by default; True with env "1"
  - account disabled → items quarantined even with exception
  - exception restores lexicon-quarantined item; does NOT restore account_disabled
  - auditor_strict=False → warnings annotated, not quarantined (except always-enforced)
  - de-escalation invariant: gate never changes type/headline/body
  - report counts consistent: passed + quarantined == items
  - reasons_histogram populated
  - self-contained quarantined entries carry account+headline+reasons
  - run_gate: reads plan+cfg from tmp tree, writes both artifacts atomically
  - POST-TIME gates (ported from #3928): per-account template-frame repeats, the
    no-ticker filler cap (plan side AND publish side), and the substance floor —
    each unit-tested and each proven to run through the live publisher
"""
from __future__ import annotations

import json
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import pytest

from engine.marketing.sentinel import gate_plan, run_gate, publish_enabled

#: Repo root — the post-time gate sections read the COMMITTED config/marketing.yml
#: (the plan side and the publisher both read its sentinel keys, so a drifted key
#: silently changes both seams).
ROOT = Path(__file__).resolve().parent.parent


# ---------------------------------------------------------------------------
# Fixture helpers
# ---------------------------------------------------------------------------

def _item(
    id: str,
    account: str,
    headline: str = "Test headline",
    body: str = "Test body. Size appropriately.",
    type: str = "signal",
    cashtag: str = "$AAPL",
    ticker: str = "AAPL",
    slot: str | None = None,
    chart_id: str | None = None,
) -> dict:
    item: dict[str, Any] = {
        "id": id,
        "account": account,
        "type": type,
        "headline": headline,
        "body": body,
        "cashtag": cashtag,
        "ticker": ticker,
        "status": "drafted",
        "provenance": "test",
        "slot": slot or id,
    }
    if chart_id is not None:
        item["chart_id"] = chart_id
    return item


def _plan(accounts_items: dict[str, list[dict]], as_of: str = "2026-07-19") -> dict:
    """Build a minimal plan dict from {account_id: [item, ...]}."""
    accounts = []
    for acc_id, items in accounts_items.items():
        accounts.append({
            "id": acc_id,
            "name": acc_id,
            "kind": "branded",
            "voice": "authoritative desk",
            "tilt": {},
            "mix_observed": {},
            "queue": items,
        })
    return {
        "schema_version": 1,
        "produced_by": "test",
        "produced_at": "2026-07-19T00:00:00Z",
        "tier": "display",
        "schema": "marketing.content/v1",
        "as_of": as_of,
        "source": {},
        "content_types": [],
        "accounts": accounts,
        "featured_charts": [],
        "distinctness": {},
        "summary": {},
    }


def _cfg(
    strict: bool = True,
    near_dup_jaccard: float = 0.60,
    max_posts: int = 4,
    max_cashtag: int = 2,
    max_receipt_age: int = 7,
    disabled_accounts: list[str] | None = None,
    require_signal_disclosure: bool = True,
) -> dict:
    accounts = [
        {"id": "flagship", "kind": "branded", "voice": "authoritative desk"},
        {"id": "receipts", "kind": "branded", "voice": "dry, receipts-forward"},
        {"id": "theme_desk", "kind": "branded", "voice": "specialist"},
    ]
    if disabled_accounts:
        for acc in accounts:
            if acc["id"] in disabled_accounts:
                acc["disabled"] = True
    return {
        "settings": {"auditor_strict": strict},
        "sentinel": {
            "near_dup_jaccard": near_dup_jaccard,
            "max_posts_per_account_per_day": max_posts,
            "max_same_cashtag_per_account_per_day": max_cashtag,
            "max_replies_per_account_per_day": 0,
            "max_receipt_age_days": max_receipt_age,
            "require_signal_disclosure": require_signal_disclosure,
            "lexicon_phrases": [
                "you should buy", "guaranteed", "can't lose", "get in now",
                "to the moon", "all-in", "price target guaranteed",
            ],
            "lexicon_patterns": [
                r"\b(will|going to|gonna)\s+(hit|reach|touch|double|triple|10x)\b",
                r"\bcan'?t\s+(go|drop|fall)\b",
            ],
        },
        "desk_network": {"stage": "A", "accounts": accounts},
    }


# ---------------------------------------------------------------------------
# 1. Near-dup across accounts
# ---------------------------------------------------------------------------

class TestNearDup:

    def test_near_identical_cross_account_quarantined(self):
        """Near-identical pair on DIFFERENT accounts → later one quarantined."""
        shared_text = "AAPL broke out above its 200-day moving average on heavy volume"
        i1 = _item("i1", "flagship", headline=shared_text, body=f"{shared_text}. Size appropriately.", cashtag="$AAPL")
        i2 = _item("i2", "receipts", headline=shared_text, body=f"{shared_text}. Size appropriately.", cashtag="$AAPL")
        plan = _plan({"flagship": [i1], "receipts": [i2]})

        annotated, report = gate_plan(plan, _cfg())

        reasons_flat = [
            r for r in report["quarantined"][0]["reasons"]
            if r.startswith("near_dup:")
        ] if report["quarantined"] else []
        assert len(report["quarantined"]) >= 1
        assert any(q["id"] == "i2" for q in report["quarantined"])
        dup_quarantined = next(q for q in report["quarantined"] if q["id"] == "i2")
        assert any(r.startswith("near_dup:") for r in dup_quarantined["reasons"])

    def test_near_identical_same_account_not_sentinel_job(self):
        """Near-identical pair on SAME account → not sentinel's business (no near-dup quarantine)."""
        shared_text = "AAPL broke out above its 200-day moving average on heavy volume"
        # signal items need disclosure; give them one
        body = f"{shared_text}. Size appropriately."
        i1 = _item("i1", "flagship", headline=shared_text, body=body, slot="s1")
        i2 = _item("i2", "flagship", headline=shared_text + " b", body=body, slot="s2")
        plan = _plan({"flagship": [i1, i2]})

        annotated, report = gate_plan(plan, _cfg())

        dup_quarantines = [
            q for q in report["quarantined"]
            if any(r.startswith("near_dup:") for r in q["reasons"])
        ]
        assert len(dup_quarantines) == 0

    def test_shared_chart_id_cross_account_quarantined(self):
        """Two items on different accounts sharing a non-null chart_id → later quarantined."""
        body = "Chart says buy the dip. Size appropriately."
        i1 = _item("i1", "flagship", type="chart", cashtag="$NVDA", ticker="NVDA",
                   body=body, chart_id="chart_42")
        i2 = _item("i2", "receipts", type="chart", cashtag="$NVDA", ticker="NVDA",
                   body=body, chart_id="chart_42")
        plan = _plan({"flagship": [i1], "receipts": [i2]})

        annotated, report = gate_plan(plan, _cfg())

        shared_q = [q for q in report["quarantined"] if any(r.startswith("shared_media:") for r in q["reasons"])]
        assert len(shared_q) >= 1
        assert shared_q[0]["id"] == "i2"

    def test_shared_chart_id_null_not_flagged(self):
        """chart_id=None on both → no shared_media violation."""
        body = "Size appropriately."
        i1 = _item("i1", "flagship", type="chart", cashtag="$NVDA", ticker="NVDA", body=body)
        i2 = _item("i2", "receipts", type="chart", cashtag="$NVDA", ticker="NVDA", body=body)
        plan = _plan({"flagship": [i1], "receipts": [i2]})

        annotated, report = gate_plan(plan, _cfg())

        shared_q = [q for q in report["quarantined"] if any(r.startswith("shared_media:") for r in q["reasons"])]
        assert len(shared_q) == 0


# ---------------------------------------------------------------------------
# 2. Cadence caps
# ---------------------------------------------------------------------------

class TestCadence:

    def test_fifth_item_quarantined_daily_cap_4(self):
        """5 items on one account with cap=4 → 5th quarantined."""
        body = "Size appropriately."
        items = [
            _item(f"i{n}", "flagship", headline=f"Headline {n}", body=body,
                  cashtag=f"${chr(65+n)}", ticker=chr(65+n), slot=f"s{n}")
            for n in range(5)
        ]
        plan = _plan({"flagship": items})

        annotated, report = gate_plan(plan, _cfg(max_posts=4))

        cadence_q = [q for q in report["quarantined"] if "cadence_cap_daily" in q["reasons"]]
        assert len(cadence_q) == 1
        assert cadence_q[0]["id"] == "i4"

    def test_third_same_cashtag_quarantined(self):
        """3 items with same cashtag on same account, cap=2 → 3rd quarantined."""
        body = "Size appropriately."
        items = [
            _item(f"i{n}", "flagship", headline=f"AAPL note {n}", body=body,
                  cashtag="$AAPL", ticker="AAPL", slot=f"s{n}")
            for n in range(3)
        ]
        plan = _plan({"flagship": items})

        annotated, report = gate_plan(plan, _cfg(max_posts=10, max_cashtag=2))

        cashtag_q = [q for q in report["quarantined"] if any(r.startswith("cashtag_cap:") for r in q["reasons"])]
        assert len(cashtag_q) == 1
        assert cashtag_q[0]["id"] == "i2"

    def test_slot_collision(self):
        """Two items with same slot on same account → second quarantined."""
        body = "Size appropriately."
        i1 = _item("i1", "flagship", headline="First", body=body, cashtag="$A", ticker="A", slot="slot_x")
        i2 = _item("i2", "flagship", headline="Second", body=body, cashtag="$B", ticker="B", slot="slot_x")
        plan = _plan({"flagship": [i1, i2]})

        annotated, report = gate_plan(plan, _cfg(max_posts=10))

        slot_q = [q for q in report["quarantined"] if any(r.startswith("slot_collision:") for r in q["reasons"])]
        assert len(slot_q) == 1
        assert slot_q[0]["id"] == "i2"


# ---------------------------------------------------------------------------
# 3. Financial-advice lexicon
# ---------------------------------------------------------------------------

class TestLexicon:

    def test_phrase_hit_quarantined(self):
        """'guaranteed winner' body → quarantined with advice_lexicon: reason."""
        i1 = _item("i1", "flagship", type="education",
                   headline="Great setup",
                   body="This is a guaranteed winner for the ages.",
                   cashtag="", ticker="")
        plan = _plan({"flagship": [i1]})

        annotated, report = gate_plan(plan, _cfg())

        assert len(report["quarantined"]) >= 1
        q = next(q for q in report["quarantined"] if q["id"] == "i1")
        assert any(r.startswith("advice_lexicon:") for r in q["reasons"])

    def test_pattern_hit_quarantined(self):
        """'will hit $200' → quarantined with advice_lexicon: reason (pattern match)."""
        i1 = _item("i1", "flagship", type="education",
                   headline="NVDA setup",
                   body="NVDA will hit $200 next week without question.",
                   cashtag="", ticker="")
        plan = _plan({"flagship": [i1]})

        annotated, report = gate_plan(plan, _cfg())

        q = next((q for q in report["quarantined"] if q["id"] == "i1"), None)
        assert q is not None
        assert any(r.startswith("advice_lexicon:") for r in q["reasons"])

    def test_clean_item_passes_lexicon(self):
        """Item with no banned phrase → no lexicon quarantine."""
        i1 = _item("i1", "flagship", type="education",
                   headline="Educational post about markets",
                   body="Here is a balanced view of the current market environment.",
                   cashtag="", ticker="")
        plan = _plan({"flagship": [i1]})

        annotated, report = gate_plan(plan, _cfg())

        lexicon_q = [q for q in report["quarantined"] if any(r.startswith("advice_lexicon:") for r in q["reasons"])]
        assert len(lexicon_q) == 0


# ---------------------------------------------------------------------------
# 4. Disclosure law
# ---------------------------------------------------------------------------

class TestDisclosure:

    def test_signal_without_disclosure_quarantined(self):
        """Signal item without a disclosure phrase → missing_disclosure."""
        i1 = _item("i1", "flagship", type="signal",
                   headline="AAPL setup at 180",
                   body="Breakout above resistance. Entry 180, T1 200.",
                   cashtag="$AAPL", ticker="AAPL")
        plan = _plan({"flagship": [i1]})

        annotated, report = gate_plan(plan, _cfg())

        q = next((q for q in report["quarantined"] if q["id"] == "i1"), None)
        assert q is not None
        assert "missing_disclosure" in q["reasons"]

    def test_signal_with_disclosure_passes(self):
        """Signal item WITH a disclosure phrase → no disclosure quarantine."""
        i1 = _item("i1", "flagship", type="signal",
                   headline="AAPL setup at 180",
                   body="Breakout above resistance. Entry 180, T1 200. Size appropriately.",
                   cashtag="$AAPL", ticker="AAPL")
        plan = _plan({"flagship": [i1]})

        annotated, report = gate_plan(plan, _cfg())

        disc_q = [q for q in report["quarantined"] if "missing_disclosure" in (q.get("reasons") or [])]
        assert len(disc_q) == 0

    def test_non_signal_no_disclosure_required(self):
        """Non-signal item without disclosure → no missing_disclosure."""
        i1 = _item("i1", "flagship", type="education",
                   headline="Market education post",
                   body="Here is what a market cycle looks like.",
                   cashtag="", ticker="")
        plan = _plan({"flagship": [i1]})

        annotated, report = gate_plan(plan, _cfg())

        disc_q = [q for q in report["quarantined"] if "missing_disclosure" in (q.get("reasons") or [])]
        assert len(disc_q) == 0

    def test_flag_off_signal_without_disclosure_passes(self):
        """require_signal_disclosure=False → a disclosure-less signal is NOT quarantined.

        Operator ruling 2026-07-26 (config sentinel.require_signal_disclosure: false):
        signal posts no longer need a not-advice / historical caveat to clear the gate.
        """
        i1 = _item("i1", "flagship", type="signal",
                   headline="AAPL setup at 180",
                   body="Breakout above resistance. Entry 180, T1 200.",
                   cashtag="$AAPL", ticker="AAPL")
        plan = _plan({"flagship": [i1]})

        annotated, report = gate_plan(plan, _cfg(require_signal_disclosure=False))

        disc_q = [q for q in report["quarantined"] if "missing_disclosure" in (q.get("reasons") or [])]
        assert len(disc_q) == 0
        assert report["checks"]["disclosure"]["required"] is False
        assert report["checks"]["disclosure"]["hits"] == 0

    def test_flag_off_lexicon_still_enforced(self):
        """Disabling the disclosure law does NOT disable the advice-lexicon guard.

        Surgical-scope guarantee: a signal post with reckless phrasing ("guaranteed")
        is still quarantined even when require_signal_disclosure is False.
        """
        i1 = _item("i1", "flagship", type="signal",
                   headline="AAPL guaranteed to run",
                   body="Entry 180. This is guaranteed.",
                   cashtag="$AAPL", ticker="AAPL")
        plan = _plan({"flagship": [i1]})

        annotated, report = gate_plan(plan, _cfg(require_signal_disclosure=False))

        q = next((q for q in report["quarantined"] if q["id"] == "i1"), None)
        assert q is not None
        assert any(r.startswith("advice_lexicon:") for r in q["reasons"])
        assert "missing_disclosure" not in q["reasons"]

    def test_flag_on_by_default_still_requires_disclosure(self):
        """Default (no config key) keeps the disclosure law ON — safe fallback."""
        i1 = _item("i1", "flagship", type="signal",
                   headline="AAPL setup at 180",
                   body="Breakout above resistance. Entry 180, T1 200.",
                   cashtag="$AAPL", ticker="AAPL")
        plan = _plan({"flagship": [i1]})

        annotated, report = gate_plan(plan, _cfg())  # default require_signal_disclosure=True

        q = next((q for q in report["quarantined"] if q["id"] == "i1"), None)
        assert q is not None
        assert "missing_disclosure" in q["reasons"]
        assert report["checks"]["disclosure"]["required"] is True


# ---------------------------------------------------------------------------
# 5. Cherry-pick detector
# ---------------------------------------------------------------------------

class TestCherryPick:

    def test_cherry_pick_detected(self):
        """Window has a loss + plan shows only win receipts (no loss ticker) → quarantine."""
        graded_window = [
            {"ticker": "AAPL", "outcome": "win"},
            {"ticker": "NVDA", "outcome": "loss"},
        ]
        # Receipt item shows only AAPL (winner), not NVDA (loser).
        # Pass receipts_age_days=3 (fresh) so item is alive for cherry-pick evaluation
        # (receipts_age_days=None would quarantine the item for receipts_age_unknown in
        # step 2 before cherry-pick runs in step 5b, which is the correct M1 behavior).
        i1 = _item("i1", "receipts", type="receipt",
                   headline="AAPL receipt win",
                   body="AAPL T1 hit +8.5%. Track it publicly.",
                   cashtag="$AAPL", ticker="AAPL")
        plan = _plan({"receipts": [i1]})

        annotated, report = gate_plan(plan, _cfg(), graded_window=graded_window,
                                      receipts_age_days=3)

        q = next((q for q in report["quarantined"] if q["id"] == "i1"), None)
        assert q is not None
        assert "cherry_pick_suspected" in q["reasons"]

    def test_cherry_pick_passes_when_loss_ticker_present(self):
        """Window has a loss; plan receipts include the loss ticker → pass."""
        graded_window = [
            {"ticker": "AAPL", "outcome": "win"},
            {"ticker": "NVDA", "outcome": "loss"},
        ]
        # Receipt items include NVDA (loss ticker)
        i1 = _item("i1", "receipts", type="receipt",
                   headline="AAPL receipt",
                   body="AAPL T1 hit. Track it.",
                   cashtag="$AAPL", ticker="AAPL")
        i2 = _item("i2", "receipts", type="receipt",
                   headline="NVDA stopped out",
                   body="NVDA stop hit. Graded.",
                   cashtag="$NVDA", ticker="NVDA",
                   slot="s2")
        plan = _plan({"receipts": [i1, i2]})

        annotated, report = gate_plan(plan, _cfg(max_posts=10), graded_window=graded_window)

        cp_q = [q for q in report["quarantined"] if "cherry_pick_suspected" in (q.get("reasons") or [])]
        assert len(cp_q) == 0

    def test_cherry_pick_window_none_skipped(self):
        """graded_window=None → cherry-pick skipped, status='skipped' in report."""
        i1 = _item("i1", "receipts", type="receipt",
                   headline="AAPL receipt",
                   body="AAPL T1 hit. Track it.",
                   cashtag="$AAPL", ticker="AAPL")
        plan = _plan({"receipts": [i1]})

        annotated, report = gate_plan(plan, _cfg(), graded_window=None)

        assert report["checks"]["cherry_pick"]["status"] == "skipped"
        cp_q = [q for q in report["quarantined"] if "cherry_pick_suspected" in (q.get("reasons") or [])]
        assert len(cp_q) == 0


# ---------------------------------------------------------------------------
# 6. Stale receipts
# ---------------------------------------------------------------------------

class TestStaleReceipts:

    def test_stale_age_refuses_whole_plan(self):
        """receipts_age_days=8 > max=7 → plan refused, all items quarantined stale_receipts_ledger."""
        body = "Size appropriately."
        i1 = _item("i1", "flagship", body=body)
        plan = _plan({"flagship": [i1]})

        annotated, report = gate_plan(plan, _cfg(max_receipt_age=7), receipts_age_days=8)

        assert report["plan_status"] == "refused"
        assert all("stale_receipts_ledger" in q["reasons"] for q in report["quarantined"])
        assert report["counts"]["quarantined"] == 1

    def test_age_none_quarantines_only_receipt_items(self):
        """receipts_age_days=None → only receipt-type items quarantined with receipts_age_unknown."""
        body_sig = "Signal post. Size appropriately."
        body_rec = "Receipt post. Track it."
        i_sig = _item("i_sig", "flagship", type="signal", body=body_sig, slot="s1")
        i_rec = _item("i_rec", "receipts", type="receipt", body=body_rec, slot="s2")
        plan = _plan({"flagship": [i_sig], "receipts": [i_rec]})

        annotated, report = gate_plan(plan, _cfg(), receipts_age_days=None)

        rec_q = [q for q in report["quarantined"] if "receipts_age_unknown" in q["reasons"]]
        assert len(rec_q) == 1
        assert rec_q[0]["id"] == "i_rec"
        sig_q = [q for q in report["quarantined"] if q["id"] == "i_sig" and "receipts_age_unknown" in q["reasons"]]
        assert len(sig_q) == 0

    def test_fresh_age_no_stale_effect(self):
        """receipts_age_days=3 (< max 7) → no stale refusal or receipts_age_unknown quarantine."""
        body = "Track it publicly."
        i1 = _item("i1", "receipts", type="receipt", body=body)
        plan = _plan({"receipts": [i1]})

        annotated, report = gate_plan(plan, _cfg(max_receipt_age=7), receipts_age_days=3)

        stale_q = [q for q in report["quarantined"] if "stale_receipts_ledger" in q["reasons"] or "receipts_age_unknown" in q["reasons"]]
        assert len(stale_q) == 0
        assert report["plan_status"] != "refused"


# ---------------------------------------------------------------------------
# 7. Kill-switch
# ---------------------------------------------------------------------------

class TestKillSwitch:

    def test_publish_enabled_false_by_default(self, monkeypatch):
        """publish_enabled() returns False when env var unset."""
        monkeypatch.delenv("MARKETING_PUBLISH_ENABLED", raising=False)
        assert publish_enabled() is False

    def test_publish_enabled_true_with_env_1(self, monkeypatch):
        """publish_enabled() returns True when env var = '1'."""
        monkeypatch.setenv("MARKETING_PUBLISH_ENABLED", "1")
        assert publish_enabled() is True

    def test_publish_enabled_true_with_env_true(self, monkeypatch):
        """publish_enabled() returns True when env var = 'true'."""
        monkeypatch.setenv("MARKETING_PUBLISH_ENABLED", "true")
        assert publish_enabled() is True

    def test_account_disabled_quarantines_items(self):
        """Account with disabled=True → all its items quarantined (always enforced)."""
        body = "Size appropriately."
        i1 = _item("i1", "flagship", body=body)
        plan = _plan({"flagship": [i1]})
        cfg = _cfg(disabled_accounts=["flagship"])

        annotated, report = gate_plan(plan, cfg)

        q = next((q for q in report["quarantined"] if q["id"] == "i1"), None)
        assert q is not None
        assert "account_disabled" in q["reasons"]

    def test_report_records_publish_enabled(self, monkeypatch):
        """Report always records publish_enabled regardless of items."""
        monkeypatch.delenv("MARKETING_PUBLISH_ENABLED", raising=False)
        plan = _plan({"flagship": []})
        _, report = gate_plan(plan, _cfg())
        assert report["publish_enabled"] is False


# ---------------------------------------------------------------------------
# 8. Exceptions
# ---------------------------------------------------------------------------

class TestExceptions:

    def test_exception_restores_lexicon_quarantined_item(self):
        """allow-exception for lexicon-quarantined item restores it to sentinel_ok=True."""
        i1 = _item("i1", "flagship", type="education",
                   headline="Market note",
                   body="This is a guaranteed winner for the ages.",
                   cashtag="", ticker="")
        plan = _plan({"flagship": [i1]})
        exceptions = {"i1": {"item_id": "i1", "allow": True, "reason": "operator-approved demo"}}

        annotated, report = gate_plan(plan, _cfg(), exceptions=exceptions)

        # i1 should NOT be in quarantined list
        q_ids = [q["id"] for q in report["quarantined"]]
        assert "i1" not in q_ids
        assert report["counts"]["exceptions_applied"] == 1

        # Find annotated item
        acc_items = annotated["accounts"][0]["queue"]
        item = next(x for x in acc_items if x["id"] == "i1")
        assert item.get("sentinel_ok") is True
        assert "exception_applied" in item

    def test_exception_cannot_restore_account_disabled(self):
        """Exception cannot override account_disabled (always-enforced)."""
        body = "Size appropriately."
        i1 = _item("i1", "flagship", body=body)
        plan = _plan({"flagship": [i1]})
        cfg = _cfg(disabled_accounts=["flagship"])
        exceptions = {"i1": {"item_id": "i1", "allow": True, "reason": "human override"}}

        annotated, report = gate_plan(plan, cfg, exceptions=exceptions)

        q = next((q for q in report["quarantined"] if q["id"] == "i1"), None)
        assert q is not None
        assert "account_disabled" in q["reasons"]
        assert report["counts"]["exceptions_applied"] == 0


# ---------------------------------------------------------------------------
# 9. Auditor strict=False
# ---------------------------------------------------------------------------

class TestAuditorStrictFalse:

    def test_strict_false_annotates_warnings_not_quarantine(self):
        """auditor_strict=False → violations become warnings, items not quarantined."""
        i1 = _item("i1", "flagship", type="education",
                   headline="Market note",
                   body="This is a guaranteed winner for the ages.",
                   cashtag="", ticker="")
        plan = _plan({"flagship": [i1]})

        annotated, report = gate_plan(plan, _cfg(strict=False))

        # Nothing quarantined for a soft violation
        lexicon_q = [q for q in report["quarantined"] if any(r.startswith("advice_lexicon:") for r in q["reasons"])]
        assert len(lexicon_q) == 0

        # Item should have sentinel_ok=True and sentinel_warnings set
        acc = annotated["accounts"][0]
        item = next(x for x in acc["queue"] if x["id"] == "i1")
        assert item.get("sentinel_ok") is True
        assert item.get("sentinel_warnings")

    def test_strict_false_always_enforced_still_quarantine(self):
        """auditor_strict=False but account_disabled → still quarantined."""
        body = "Size appropriately."
        i1 = _item("i1", "flagship", body=body)
        plan = _plan({"flagship": [i1]})
        cfg = _cfg(strict=False, disabled_accounts=["flagship"])

        annotated, report = gate_plan(plan, cfg)

        q = next((q for q in report["quarantined"] if q["id"] == "i1"), None)
        assert q is not None
        assert "account_disabled" in q["reasons"]


# ---------------------------------------------------------------------------
# 10. De-escalation invariant
# ---------------------------------------------------------------------------

class TestDeEscalation:

    def test_gate_never_modifies_type_headline_body(self):
        """Gate never changes item type/headline/body — only annotates."""
        orig_headline = "AAPL setup at 180"
        orig_body = "Breakout. Size appropriately."
        orig_type = "signal"
        i1 = _item("i1", "flagship", type=orig_type, headline=orig_headline,
                   body=orig_body, cashtag="$AAPL", ticker="AAPL")
        plan = _plan({"flagship": [i1]})

        annotated, _ = gate_plan(plan, _cfg())

        item = annotated["accounts"][0]["queue"][0]
        assert item["headline"] == orig_headline
        assert item["body"] == orig_body
        assert item["type"] == orig_type

    def test_gate_does_not_elevate_drafted_items(self):
        """Gate never changes 'drafted' status to any elevated state (only quarantine or keep)."""
        body = "Size appropriately."
        i1 = _item("i1", "flagship", body=body)
        plan = _plan({"flagship": [i1]})

        annotated, _ = gate_plan(plan, _cfg())

        item = annotated["accounts"][0]["queue"][0]
        # Status must remain "drafted" or become "quarantined" — never anything else
        assert item.get("status") in {"drafted", "quarantined", None}


# ---------------------------------------------------------------------------
# 11. Report invariants
# ---------------------------------------------------------------------------

class TestReportInvariants:

    def test_counts_consistent(self):
        """passed + quarantined == items."""
        body = "Size appropriately."
        items_flagship = [
            _item(f"i{n}", "flagship", headline=f"H {n}", body=body,
                  cashtag=f"${chr(65+n)}", ticker=chr(65+n), slot=f"s{n}")
            for n in range(5)
        ]
        plan = _plan({"flagship": items_flagship})

        annotated, report = gate_plan(plan, _cfg(max_posts=3))

        c = report["counts"]
        assert c["passed"] + c["quarantined"] == c["items"]

    def test_reasons_histogram_populated(self):
        """reasons_histogram is populated when quarantines exist."""
        i1 = _item("i1", "flagship", type="education",
                   headline="Guaranteed winner",
                   body="This is a guaranteed winner.",
                   cashtag="", ticker="")
        plan = _plan({"flagship": [i1]})

        _, report = gate_plan(plan, _cfg())

        assert len(report["reasons_histogram"]) > 0

    def test_quarantined_entries_self_contained(self):
        """Each quarantined entry carries account, headline, reasons."""
        i1 = _item("i1", "flagship", type="education",
                   headline="Guaranteed winner",
                   body="This is a guaranteed win situation.",
                   cashtag="", ticker="")
        plan = _plan({"flagship": [i1]})

        _, report = gate_plan(plan, _cfg())

        q = next((q for q in report["quarantined"] if q["id"] == "i1"), None)
        assert q is not None
        assert q["account"] == "flagship"
        assert q["headline"]
        assert q["reasons"]

    def test_report_has_required_keys(self):
        """Report has all required top-level keys."""
        plan = _plan({"flagship": []})
        _, report = gate_plan(plan, _cfg())

        required = {
            "schema_version", "produced_by", "produced_at", "as_of",
            "plan_status", "publish_enabled", "auditor_strict",
            "counts", "reasons_histogram", "quarantined", "checks", "notes",
        }
        assert required.issubset(set(report.keys()))

    def test_checks_block_has_required_keys(self):
        """Checks block contains all expected check keys."""
        plan = _plan({"flagship": []})
        _, report = gate_plan(plan, _cfg())

        checks = report["checks"]
        for key in ("near_dup", "cadence", "lexicon", "disclosure", "cherry_pick", "stale_receipts", "kill_switch"):
            assert key in checks, f"missing checks.{key}"


# ---------------------------------------------------------------------------
# 12. run_gate: disk I/O
# ---------------------------------------------------------------------------

class TestRunGate:

    def test_run_gate_reads_and_writes_artifacts(self, tmp_path):
        """run_gate reads plan+cfg from a seeded tmp tree, writes both artifacts atomically."""
        # Seed config
        cfg_dir = tmp_path / "config"
        cfg_dir.mkdir(parents=True)
        cfg_data = {
            "settings": {"auditor_strict": True},
            "sentinel": {
                "near_dup_jaccard": 0.60,
                "max_posts_per_account_per_day": 4,
                "max_same_cashtag_per_account_per_day": 2,
                "max_replies_per_account_per_day": 0,
                "max_receipt_age_days": 7,
                "lexicon_phrases": ["guaranteed"],
                "lexicon_patterns": [],
            },
            "desk_network": {"stage": "A", "accounts": []},
        }
        import yaml
        (cfg_dir / "marketing.yml").write_text(yaml.dump(cfg_data), encoding="utf-8")

        # Seed plan
        plan_dir = tmp_path / "data" / "marketing"
        plan_dir.mkdir(parents=True)
        plan_data = _plan({"flagship": [
            _item("x1", "flagship",
                  headline="Clean post",
                  body="Good post. Size appropriately.",
                  type="signal")
        ]})
        (plan_dir / "content_plan.json").write_text(json.dumps(plan_data), encoding="utf-8")

        report = run_gate(root=tmp_path)

        # Both artifacts should exist
        assert (plan_dir / "content_plan.json").exists()
        assert (plan_dir / "sentinel_report.json").exists()

        # Report parses correctly
        report_from_disk = json.loads((plan_dir / "sentinel_report.json").read_text(encoding="utf-8"))
        assert report_from_disk["schema_version"] == 1
        assert report_from_disk["plan_status"] in {"pass", "pass_with_warnings", "refused", "error"}
        assert report_from_disk["counts"]["items"] == 1

        # Return value matches file
        assert report["counts"]["items"] == 1

    def test_run_gate_fails_closed_on_missing_plan(self, tmp_path):
        """Unreadable plan → error report written, exception raised, and
        content_plan.json is NEVER fabricated/overwritten (fail-closed)."""
        cfg_dir = tmp_path / "config"
        cfg_dir.mkdir(parents=True)
        import yaml
        (cfg_dir / "marketing.yml").write_text(
            yaml.dump({"settings": {}, "sentinel": {}, "desk_network": {"accounts": []}}),
            encoding="utf-8",
        )

        with pytest.raises(Exception):
            run_gate(root=tmp_path)

        report_path = tmp_path / "data" / "marketing" / "sentinel_report.json"
        assert report_path.exists()
        report = json.loads(report_path.read_text(encoding="utf-8"))
        assert report["plan_status"] == "error"
        assert any("unreadable" in n for n in report["notes"])
        # The gate must not conjure a plan out of thin air
        assert not (tmp_path / "data" / "marketing" / "content_plan.json").exists()

    def test_run_gate_fails_closed_on_corrupt_plan(self, tmp_path):
        """Corrupt JSON plan → same fail-closed contract, original bytes preserved."""
        cfg_dir = tmp_path / "config"
        cfg_dir.mkdir(parents=True)
        import yaml
        (cfg_dir / "marketing.yml").write_text(
            yaml.dump({"settings": {}, "sentinel": {}, "desk_network": {"accounts": []}}),
            encoding="utf-8",
        )
        plan_path = tmp_path / "data" / "marketing" / "content_plan.json"
        plan_path.parent.mkdir(parents=True)
        plan_path.write_text("{not valid json", encoding="utf-8")

        with pytest.raises(Exception):
            run_gate(root=tmp_path)

        report = json.loads(
            (tmp_path / "data" / "marketing" / "sentinel_report.json").read_text(encoding="utf-8")
        )
        assert report["plan_status"] == "error"
        # Corrupt file left exactly as it was — never clobbered with a stub
        assert plan_path.read_text(encoding="utf-8") == "{not valid json"


# ---------------------------------------------------------------------------
# 13. Media cap
# ---------------------------------------------------------------------------

class TestMediaCap:

    def test_media_cap_quarantines_excess(self):
        """3 chart items on one account, cap=1 → 2 quarantined with media_cap_daily."""
        body = "Size appropriately."
        items = [
            _item(f"i{n}", "flagship", headline=f"Chart {n}", body=body,
                  type="chart", cashtag="$AAPL", ticker="AAPL",
                  slot=f"s{n}", chart_id=f"chart_{n}")
            for n in range(3)
        ]
        plan = _plan({"flagship": items})
        cfg = _cfg(max_posts=10)
        cfg["sentinel"]["max_media_posts_per_account_per_day"] = 1

        annotated, report = gate_plan(plan, cfg)

        media_q = [q for q in report["quarantined"] if "media_cap_daily" in q["reasons"]]
        assert len(media_q) == 2
        # First chart item passes; i1 and i2 are quarantined
        assert {q["id"] for q in media_q} == {"i1", "i2"}

    def test_media_cap_no_chart_id_not_counted(self):
        """Items without chart_id do not count toward the media cap."""
        body = "Size appropriately."
        items = [
            _item(f"i{n}", "flagship", headline=f"Signal {n}", body=body,
                  type="signal", cashtag=f"${chr(65+n)}", ticker=chr(65+n),
                  slot=f"s{n}")
            for n in range(3)
        ]
        plan = _plan({"flagship": items})
        cfg = _cfg(max_posts=10)
        cfg["sentinel"]["max_media_posts_per_account_per_day"] = 1

        annotated, report = gate_plan(plan, cfg)

        media_q = [q for q in report["quarantined"] if "media_cap_daily" in q["reasons"]]
        assert len(media_q) == 0


# ---------------------------------------------------------------------------
# 14. Cashtag breadth
# ---------------------------------------------------------------------------

class TestCashtagBreadth:

    def test_four_cashtags_in_post_quarantined(self):
        """Post with 4 distinct cashtags, cap=3 → quarantined with cashtag_breadth."""
        body = "Watching $AAPL $MSFT $NVDA $GOOGL for breakouts. Size appropriately."
        i1 = _item("i1", "flagship", headline="Multi-name watch",
                   body=body, type="education", cashtag="$AAPL", ticker="AAPL")
        plan = _plan({"flagship": [i1]})
        cfg = _cfg(max_posts=10)
        cfg["sentinel"]["max_cashtags_per_post"] = 3

        annotated, report = gate_plan(plan, cfg)

        q = next((q for q in report["quarantined"] if q["id"] == "i1"), None)
        assert q is not None
        assert "cashtag_breadth" in q["reasons"]

    def test_three_cashtags_at_cap_passes(self):
        """Post with exactly 3 distinct cashtags, cap=3 → NOT quarantined."""
        body = "Watching $AAPL $MSFT $NVDA for breakouts. Size appropriately."
        i1 = _item("i1", "flagship", headline="Three-name watch",
                   body=body, type="education", cashtag="$AAPL", ticker="AAPL")
        plan = _plan({"flagship": [i1]})
        cfg = _cfg(max_posts=10)
        cfg["sentinel"]["max_cashtags_per_post"] = 3

        annotated, report = gate_plan(plan, cfg)

        q = next((q for q in report["quarantined"] if q["id"] == "i1"), None)
        assert q is None or "cashtag_breadth" not in q.get("reasons", [])

    def test_theme_list_exempt_from_cashtag_breadth(self):
        """theme_list with >3 cashtags is NOT quarantined for cashtag_breadth."""
        body = "$AAPL $MSFT $NVDA $GOOGL $META leading the move. Size appropriately."
        i1 = _item("i1", "flagship", headline="Theme list",
                   body=body, type="theme_list", cashtag="$AAPL", ticker="AAPL")
        plan = _plan({"flagship": [i1]})
        cfg = _cfg(max_posts=10)
        cfg["sentinel"]["max_cashtags_per_post"] = 3

        annotated, report = gate_plan(plan, cfg)

        breadth_q = [q for q in report["quarantined"] if "cashtag_breadth" in q.get("reasons", [])]
        assert len(breadth_q) == 0


# ---------------------------------------------------------------------------
# 15. Link rule
# ---------------------------------------------------------------------------

class TestLinkRule:

    def test_https_url_quarantined_when_links_not_allowed(self):
        """Body with https:// URL + links_allowed=false → quarantined link_not_allowed."""
        body = "Check our research at https://example.com for more. Size appropriately."
        i1 = _item("i1", "flagship", headline="Signal with link",
                   body=body, type="education", cashtag="", ticker="")
        plan = _plan({"flagship": [i1]})
        cfg = _cfg(max_posts=10)
        cfg["sentinel"]["links_allowed"] = False

        annotated, report = gate_plan(plan, cfg)

        q = next((q for q in report["quarantined"] if q["id"] == "i1"), None)
        assert q is not None
        assert "link_not_allowed" in q["reasons"]

    def test_tco_url_quarantined_when_links_not_allowed(self):
        """Body with bare t.co/ short-link + links_allowed=false → quarantined link_not_allowed."""
        body = "See t.co/AbCdEf for the chart. Size appropriately."
        i1 = _item("i1", "flagship", headline="Signal with tco",
                   body=body, type="education", cashtag="", ticker="")
        plan = _plan({"flagship": [i1]})
        cfg = _cfg(max_posts=10)
        cfg["sentinel"]["links_allowed"] = False

        annotated, report = gate_plan(plan, cfg)

        q = next((q for q in report["quarantined"] if q["id"] == "i1"), None)
        assert q is not None
        assert "link_not_allowed" in q["reasons"]

    def test_url_passes_when_links_allowed(self):
        """Body with https:// URL + links_allowed=true → NOT quarantined for link rule."""
        body = "Check our research at https://example.com for more. Size appropriately."
        i1 = _item("i1", "flagship", headline="Signal with link",
                   body=body, type="education", cashtag="", ticker="")
        plan = _plan({"flagship": [i1]})
        cfg = _cfg(max_posts=10)
        cfg["sentinel"]["links_allowed"] = True

        annotated, report = gate_plan(plan, cfg)

        link_q = [q for q in report["quarantined"] if "link_not_allowed" in q.get("reasons", [])]
        assert len(link_q) == 0

    def test_no_url_passes_link_rule(self):
        """Item without any URL → no link_not_allowed violation."""
        body = "Plain text. No links here. Size appropriately."
        i1 = _item("i1", "flagship", headline="Clean post",
                   body=body, type="education", cashtag="", ticker="")
        plan = _plan({"flagship": [i1]})
        cfg = _cfg(max_posts=10)
        cfg["sentinel"]["links_allowed"] = False

        annotated, report = gate_plan(plan, cfg)

        link_q = [q for q in report["quarantined"] if "link_not_allowed" in q.get("reasons", [])]
        assert len(link_q) == 0


# ---------------------------------------------------------------------------
# 16. Near-dup boundary at 0.50 threshold
# ---------------------------------------------------------------------------

class TestNearDupBoundary:

    @staticmethod
    def _build_text_with_jaccard(base_tokens: list[str], target_jaccard: float) -> str:
        """Deterministically build a text string achieving approximately the target Jaccard
        against the base text. Uses disjoint filler tokens to control overlap precisely.
        """
        # Construct a set B of size m so that |A ∩ B|/|A ∪ B| ≈ target_jaccard.
        # With |A|=|B|=m and overlap k: jaccard = k / (2m - k)
        # Solve for k: k = 2mj / (1 + j)
        m = len(base_tokens)
        k = round(2 * m * target_jaccard / (1 + target_jaccard))  # solve: k/(2m-k) = j → k = 2mj/(1+j)
        # Take the first k base tokens as overlap, then pad with unique filler
        overlap = base_tokens[:k]
        n_filler = m - k
        filler = [f"zz_{i}" for i in range(n_filler)]
        return " ".join(overlap + filler)

    def test_jaccard_above_050_quarantined(self):
        """Pair with Jaccard ~0.55 (> 0.50 threshold) across accounts → quarantined."""
        # Construct deterministic token sets: share ~55% Jaccard
        base_tokens = [f"tok{i}" for i in range(20)]
        base_text = " ".join(base_tokens) + " size appropriately"
        similar_text = self._build_text_with_jaccard(base_tokens, 0.55) + " size appropriately"

        i1 = _item("i1", "flagship", headline=base_text, body="Size appropriately.", cashtag="", ticker="")
        i2 = _item("i2", "receipts", headline=similar_text, body="Size appropriately.", cashtag="", ticker="")
        plan = _plan({"flagship": [i1], "receipts": [i2]})
        cfg = _cfg(max_posts=10)
        cfg["sentinel"]["near_dup_jaccard"] = 0.50

        annotated, report = gate_plan(plan, cfg)

        near_dup_q = [q for q in report["quarantined"] if any(r.startswith("near_dup:") for r in q.get("reasons", []))]
        assert len(near_dup_q) >= 1

    def test_jaccard_below_030_not_quarantined(self):
        """Pair with Jaccard ~0.15 (well below 0.50 threshold) → NOT near-dup quarantined."""
        # Mostly disjoint token sets
        tokens_a = [f"alpha_{i}" for i in range(20)]
        tokens_b = [f"beta_{i}" for i in range(20)]
        # 2 shared tokens → jaccard ≈ 2/38 ≈ 0.05
        tokens_b[0] = tokens_a[0]
        tokens_b[1] = tokens_a[1]

        i1 = _item("i1", "flagship", headline=" ".join(tokens_a) + " size appropriately", body="Size appropriately.", cashtag="", ticker="")
        i2 = _item("i2", "receipts", headline=" ".join(tokens_b) + " size appropriately", body="Size appropriately.", cashtag="", ticker="")
        plan = _plan({"flagship": [i1], "receipts": [i2]})
        cfg = _cfg(max_posts=10)
        cfg["sentinel"]["near_dup_jaccard"] = 0.50

        annotated, report = gate_plan(plan, cfg)

        near_dup_q = [q for q in report["quarantined"] if any(r.startswith("near_dup:") for r in q.get("reasons", []))]
        assert len(near_dup_q) == 0


# ---------------------------------------------------------------------------
# 17. M1 regression — quarantine-aware check sequencing
# ---------------------------------------------------------------------------

class TestM1QuarantineAwareSequencing:
    """Repros the a1/a2/a3 cap-slot bug fixed by M1."""

    def test_cap_counts_only_alive_items_a1_a2_a3(self):
        """a1 clean, a2 near-dup-killed, a3 clean, cap=2 → a3 must survive.

        Before M1 fix: a2 consumed a cap slot even though it was quarantined
        for near-dup, causing a3 to be wrongly killed by cadence_cap_daily.
        After fix: cap counts only alive items, so a1+a3 = 2 ≤ cap=2 → a3 lives.

        Plan order matters for near-dup: the FIRST item seen on each cross-account
        pair survives; the later one is quarantined. We put 'cross' (on receipts)
        before the flagship items so that when flagship processes a2, 'cross' is
        already in surviving_cross, making a2 the dup of cross (not the other way).
        """
        shared_text = "AAPL broke out above its 200-day moving average on heavy volume"
        body_disclosure = f"{shared_text}. Size appropriately."

        # cross = near-dup seed on receipts (processed FIRST in plan order)
        cross = _item("cross", "receipts", headline=shared_text, body=body_disclosure,
                      cashtag="$AAPL", ticker="AAPL", slot="sc")
        # a1 = clean on flagship
        a1 = _item("a1", "flagship", headline="A1 unique content about earnings",
                   body="A1 body. Size appropriately.", cashtag="$AAPL", ticker="AAPL", slot="s1")
        # a2 = near-dup of cross → will be killed by near-dup in step 4
        a2 = _item("a2", "flagship", headline=shared_text, body=body_disclosure,
                   cashtag="$AAPL", ticker="AAPL", slot="s2")
        # a3 = clean on flagship — should survive (cap=2, only a1 and a3 are alive)
        a3 = _item("a3", "flagship", headline="A3 different content about semis",
                   body="A3 body. Size appropriately.", cashtag="$MSFT", ticker="MSFT", slot="s3")

        # receipts first in the dict so cross is processed before flagship items
        plan = _plan({"receipts": [cross], "flagship": [a1, a2, a3]})
        cfg = _cfg(max_posts=2, near_dup_jaccard=0.60)

        annotated, report = gate_plan(plan, cfg)

        # a2 must be quarantined for near_dup (it's a dup of 'cross')
        a2_entry = next((q for q in report["quarantined"] if q["id"] == "a2"), None)
        assert a2_entry is not None, "a2 should be quarantined as near-dup"
        assert any(r.startswith("near_dup:") for r in a2_entry["reasons"])

        # a3 must NOT be quarantined — only a1 and a3 are alive, both fit in cap=2
        a3_entry = next((q for q in report["quarantined"] if q["id"] == "a3"), None)
        assert a3_entry is None, f"a3 must survive but was quarantined: {a3_entry}"

        # Verify a3 is sentinel_ok=True in annotated plan
        flagship_queue = next(
            acc["queue"] for acc in annotated["accounts"] if acc["id"] == "flagship"
        )
        a3_item = next(x for x in flagship_queue if x["id"] == "a3")
        assert a3_item.get("sentinel_ok") is True

    def test_near_dup_of_dead_item_survives(self):
        """Near-dup of an already-dead (lexicon-killed) item must survive near-dup check.

        The earlier item is lexicon-killed in step 1. In step 4 it is NOT alive,
        so the later item on a different account must NOT be quarantined as a near-dup.
        """
        shared_text = "AAPL price target guaranteed to go up big time this week"
        body_disclosure = "Size appropriately."

        # i1 on flagship — has lexicon phrase "price target guaranteed" → killed in step 1
        i1 = _item("i1", "flagship",
                   headline=shared_text,
                   body=body_disclosure,
                   cashtag="$AAPL", ticker="AAPL", slot="s1")
        # i2 on receipts — same text (would be a near-dup IF i1 were alive)
        # But i1 is dead, so i2 should survive near-dup.
        i2 = _item("i2", "receipts",
                   headline=shared_text,
                   body=body_disclosure,
                   cashtag="$AAPL", ticker="AAPL", slot="s2")

        plan = _plan({"flagship": [i1], "receipts": [i2]})
        cfg = _cfg(max_posts=10, near_dup_jaccard=0.50)

        annotated, report = gate_plan(plan, cfg)

        # i1 must be quarantined for lexicon (price target guaranteed)
        i1_entry = next((q for q in report["quarantined"] if q["id"] == "i1"), None)
        assert i1_entry is not None, "i1 should be quarantined for advice_lexicon"
        assert any(r.startswith("advice_lexicon:") for r in i1_entry["reasons"])

        # i2 must NOT be quarantined for near_dup (i1 is dead, not a live counterpart)
        i2_entry = next((q for q in report["quarantined"] if q["id"] == "i2"), None)
        if i2_entry is not None:
            near_dup_reasons = [r for r in i2_entry["reasons"] if r.startswith("near_dup:")]
            assert len(near_dup_reasons) == 0, \
                f"i2 should not be near-dup quarantined (counterpart i1 is dead): {i2_entry['reasons']}"

    def test_media_cap_counts_only_alive_items(self):
        """Media cap analog of a1/a2/a3: a2 near-dup-killed, a3 still fits in cap=1.

        Two media items on flagship: m1 (clean) and m3 (clean), plus m2 (near-dup of
        cross-account item, killed in step 4). Cap=1. Only m1 is alive and has
        chart_id, so m3 (no chart_id) must NOT be media-cap quarantined.
        """
        shared_text = "NVDA chart showing the big breakout pattern above 200-day"
        body_disclosure = f"{shared_text}. Size appropriately."

        # m1 = clean media item on flagship
        m1 = _item("m1", "flagship", headline="Clean chart post",
                   body="Chart body. Size appropriately.", cashtag="$NVDA", ticker="NVDA",
                   slot="s1", chart_id="chart_clean")
        # m2 = near-dup of cross → killed in step 4
        m2 = _item("m2", "flagship", headline=shared_text, body=body_disclosure,
                   cashtag="$NVDA", ticker="NVDA", slot="s2", chart_id="chart_dup")
        # m3 = clean non-media item on flagship → should survive (media cap is full on m1 only)
        m3 = _item("m3", "flagship", headline="Signal about macro",
                   body="Macro signal. Size appropriately.", cashtag="$SPY", ticker="SPY", slot="s3")
        # cross = near-dup seed on receipts
        cross = _item("cross", "receipts", headline=shared_text, body=body_disclosure,
                      cashtag="$NVDA", ticker="NVDA", slot="sc")

        plan = _plan({"flagship": [m1, m2, m3], "receipts": [cross]})
        cfg = _cfg(max_posts=10, near_dup_jaccard=0.60)
        cfg["sentinel"]["max_media_posts_per_account_per_day"] = 1

        annotated, report = gate_plan(plan, cfg)

        # m2 must be quarantined for near_dup
        m2_entry = next((q for q in report["quarantined"] if q["id"] == "m2"), None)
        assert m2_entry is not None, "m2 should be near-dup quarantined"

        # m3 must NOT be quarantined for media_cap (m2 was dead, only m1 counts)
        m3_entry = next((q for q in report["quarantined"] if q["id"] == "m3"), None)
        if m3_entry is not None:
            assert "media_cap_daily" not in m3_entry["reasons"], \
                f"m3 must not be media-cap quarantined: {m3_entry['reasons']}"

    def test_exception_restored_item_participates_in_caps(self):
        """Exception restoring a content-killed item makes it participate in caps normally (steps 3→5).

        e1: lexicon violation → exception restores it in step 3 → it now consumes a cap slot.
        e2: clean, same account, cap=1 → e2 should be cadence-capped since e1 now counts.
        """
        body_disclosure = "Size appropriately."

        # e1: "guaranteed" in body → lexicon violation; exception restores it
        e1 = _item("e1", "flagship",
                   headline="Market note",
                   body="This setup looks guaranteed. Size appropriately.",
                   cashtag="$AAPL", ticker="AAPL", slot="s1")
        # e2: clean item — would normally survive cap=1, but e1 is restored and takes the slot
        e2 = _item("e2", "flagship",
                   headline="Different market note",
                   body="Different content. Size appropriately.",
                   cashtag="$MSFT", ticker="MSFT", slot="s2")

        plan = _plan({"flagship": [e1, e2]})
        cfg = _cfg(max_posts=1)
        exceptions = {"e1": {"item_id": "e1", "allow": True, "reason": "operator-approved demo"}}

        annotated, report = gate_plan(plan, cfg, exceptions=exceptions)

        # e1 must be restored (sentinel_ok=True, exception_applied set)
        flagship_queue = next(
            acc["queue"] for acc in annotated["accounts"] if acc["id"] == "flagship"
        )
        e1_item = next(x for x in flagship_queue if x["id"] == "e1")
        assert e1_item.get("sentinel_ok") is True, "e1 should be restored by exception"
        assert e1_item.get("exception_applied"), "e1 should have exception_applied set"
        assert report["counts"]["exceptions_applied"] >= 1

        # e2 must be cadence-capped since e1 consumed the slot
        e2_entry = next((q for q in report["quarantined"] if q["id"] == "e2"), None)
        assert e2_entry is not None, "e2 should be cadence-capped since e1 was restored first"
        assert "cadence_cap_daily" in e2_entry["reasons"]


# ---------------------------------------------------------------------------
# 18. M2 regression — disclosure word-boundary checks
# ---------------------------------------------------------------------------

class TestM2DisclosureWordBoundary:

    def test_upgraded_does_not_trigger_grade_disclosure(self):
        """Signal body containing 'NVDA upgraded, going higher' with no real disclosure
        must FAIL the disclosure check (word 'grade' inside 'upgraded' must NOT match).
        """
        i1 = _item("i1", "flagship", type="signal",
                   headline="NVDA setup",
                   body="NVDA upgraded, going higher. Strong buy.",
                   cashtag="$NVDA", ticker="NVDA")
        plan = _plan({"flagship": [i1]})

        annotated, report = gate_plan(plan, _cfg())

        disc_q = [q for q in report["quarantined"] if "missing_disclosure" in q.get("reasons", [])]
        assert len(disc_q) >= 1, (
            "Signal with 'upgraded' (but no real disclosure) must fail disclosure check; "
            f"got quarantined: {report['quarantined']}"
        )

    def test_historically_does_not_trigger_historical_disclosure(self):
        """Signal body with 'historically speaking' but no real disclosure must FAIL.

        'historical' as a standalone word boundary is required; 'historically' must NOT
        trigger the disclosure anchor.
        """
        i1 = _item("i1", "flagship", type="signal",
                   headline="AAPL setup",
                   body="Historically speaking, AAPL tends to bounce here. Entry 180.",
                   cashtag="$AAPL", ticker="AAPL")
        plan = _plan({"flagship": [i1]})

        annotated, report = gate_plan(plan, _cfg())

        disc_q = [q for q in report["quarantined"] if "missing_disclosure" in q.get("reasons", [])]
        assert len(disc_q) >= 1, (
            "Signal with 'historically' (not 'historical') must fail disclosure check"
        )

    def test_size_appropriately_passes_disclosure(self):
        """'size appropriately' (multi-word anchor) must still pass as disclosure."""
        i1 = _item("i1", "flagship", type="signal",
                   headline="AAPL setup at 180",
                   body="Breakout above resistance. Entry 180, T1 200. Size appropriately.",
                   cashtag="$AAPL", ticker="AAPL")
        plan = _plan({"flagship": [i1]})

        annotated, report = gate_plan(plan, _cfg())

        disc_q = [q for q in report["quarantined"] if "missing_disclosure" in q.get("reasons", [])]
        assert len(disc_q) == 0, "size appropriately should satisfy disclosure"

    def test_historical_standalone_passes_disclosure(self):
        """'historical' as a standalone word must pass as disclosure."""
        i1 = _item("i1", "flagship", type="signal",
                   headline="AAPL setup",
                   body="Historical performance suggests support at 180. Entry here.",
                   cashtag="$AAPL", ticker="AAPL")
        plan = _plan({"flagship": [i1]})

        annotated, report = gate_plan(plan, _cfg())

        disc_q = [q for q in report["quarantined"] if "missing_disclosure" in q.get("reasons", [])]
        assert len(disc_q) == 0, "'historical' standalone should satisfy disclosure"

    def test_not_financial_advice_passes_disclosure(self):
        """'not financial advice' must pass as disclosure."""
        i1 = _item("i1", "flagship", type="signal",
                   headline="MSFT setup",
                   body="MSFT breakout. This is not financial advice. Entry 350.",
                   cashtag="$MSFT", ticker="MSFT")
        plan = _plan({"flagship": [i1]})

        annotated, report = gate_plan(plan, _cfg())

        disc_q = [q for q in report["quarantined"] if "missing_disclosure" in q.get("reasons", [])]
        assert len(disc_q) == 0, "not financial advice should satisfy disclosure"


# ---------------------------------------------------------------------------
# 19. M3 regression — config/code drift guard
# ---------------------------------------------------------------------------

class TestM3ConfigDriftGuard:
    """Loads the REAL config/marketing.yml and asserts it matches in-code defaults."""

    @staticmethod
    def _load_real_cfg() -> dict:
        import yaml
        from pathlib import Path
        # Walk up from tests/ to find config/marketing.yml
        here = Path(__file__).resolve().parent
        repo_root = here.parent
        cfg_path = repo_root / "config" / "marketing.yml"
        with open(cfg_path, encoding="utf-8") as f:
            return yaml.safe_load(f) or {}

    def test_scalar_knobs_match_in_code_defaults(self):
        """Every sentinel scalar knob in marketing.yml equals the in-code default."""
        from engine.marketing.sentinel import (
            _DEFAULT_NEAR_DUP_JACCARD,
            _DEFAULT_MAX_POSTS_PER_ACCOUNT_PER_DAY,
            _DEFAULT_MAX_SAME_CASHTAG_PER_ACCOUNT_PER_DAY,
            _DEFAULT_MAX_REPLIES_PER_ACCOUNT_PER_DAY,
            _DEFAULT_MAX_RECEIPT_AGE_DAYS,
            _DEFAULT_LINKS_ALLOWED,
            _DEFAULT_MAX_MEDIA_POSTS_PER_ACCOUNT_PER_DAY,
            _DEFAULT_MAX_CASHTAGS_PER_POST,
        )
        cfg = self._load_real_cfg()
        sc = cfg.get("sentinel", {})

        assert sc["near_dup_jaccard"] == _DEFAULT_NEAR_DUP_JACCARD, \
            f"near_dup_jaccard drift: yaml={sc['near_dup_jaccard']} code={_DEFAULT_NEAR_DUP_JACCARD}"
        # Daily post + media caps INTENTIONALLY diverge from the safe code
        # defaults: the operator lifted them to unlimited (autonomous cadence,
        # 2026-07-24). -1 is the sentinel _cap_unlimited decodes to "no limit";
        # the code defaults stay bounded (2 / 1) as the missing-key fallback.
        assert sc["max_posts_per_account_per_day"] == -1
        assert sc["max_media_posts_per_account_per_day"] == -1
        # Same intentional-divergence pattern: raised 1 -> 3 (operator 2026-07-28)
        # alongside the 10/20-per-day volume. At 1/day the cashtag cap became the
        # binding limit the moment volume rose — and because the base block is the
        # STRICTER half of the ramp merge, leaving it at 1 would have silently
        # pinned every tier row back to 1 no matter what the tier said. The code
        # default stays 1 as the missing-key fallback (a lost key must fail toward
        # the quieter account, never toward a louder one).
        assert _DEFAULT_MAX_SAME_CASHTAG_PER_ACCOUNT_PER_DAY == 1
        assert sc["max_same_cashtag_per_account_per_day"] == 3
        assert sc["max_replies_per_account_per_day"] == _DEFAULT_MAX_REPLIES_PER_ACCOUNT_PER_DAY
        assert sc["max_receipt_age_days"] == _DEFAULT_MAX_RECEIPT_AGE_DAYS
        assert sc["links_allowed"] == _DEFAULT_LINKS_ALLOWED
        assert sc["max_cashtags_per_post"] == _DEFAULT_MAX_CASHTAGS_PER_POST
        # Signal-disclosure law INTENTIONALLY diverges from the safe code default
        # (True), same pattern as the unlimited caps above: the operator disabled it
        # (ruling 2026-07-26 — signal posts are no longer quarantined for a missing
        # not-advice caveat). The code default stays True as the missing-key fallback;
        # config carries the live policy. Flip config back to true to re-enable.
        from engine.marketing.sentinel import _DEFAULT_REQUIRE_SIGNAL_DISCLOSURE
        assert _DEFAULT_REQUIRE_SIGNAL_DISCLOSURE is True
        assert sc["require_signal_disclosure"] is False

    def test_lexicon_lists_match_in_code_defaults(self):
        """lexicon_phrases and lexicon_patterns lists equal in-code defaults exactly."""
        from engine.marketing.sentinel import (
            _DEFAULT_LEXICON_PHRASES,
            _DEFAULT_LEXICON_PATTERNS,
        )
        cfg = self._load_real_cfg()
        sc = cfg.get("sentinel", {})

        assert sc["lexicon_phrases"] == _DEFAULT_LEXICON_PHRASES, \
            f"lexicon_phrases drift:\nyaml={sc['lexicon_phrases']}\ncode={_DEFAULT_LEXICON_PHRASES}"
        assert sc["lexicon_patterns"] == _DEFAULT_LEXICON_PATTERNS, \
            f"lexicon_patterns drift:\nyaml={sc['lexicon_patterns']}\ncode={_DEFAULT_LEXICON_PATTERNS}"

    def test_each_config_pattern_compiles(self):
        """Each config lexicon_pattern compiles as a regex."""
        import re
        cfg = self._load_real_cfg()
        sc = cfg.get("sentinel", {})
        for pat in sc.get("lexicon_patterns", []):
            try:
                re.compile(pat, re.IGNORECASE)
            except re.error as e:
                raise AssertionError(f"Pattern {pat!r} failed to compile: {e}") from e

    def test_cant_pattern_matches_both_forms(self):
        """The can't pattern from config must match both 'can\\'t go' and 'cant go'."""
        import re
        cfg = self._load_real_cfg()
        sc = cfg.get("sentinel", {})
        patterns = sc.get("lexicon_patterns", [])
        cant_patterns = [p for p in patterns if "can" in p and "go" in p]
        assert cant_patterns, "No can't pattern found in config lexicon_patterns"
        for pat in cant_patterns:
            cp = re.compile(pat, re.IGNORECASE)
            assert cp.search("can't go"), f"Pattern {pat!r} must match \"can't go\""
            assert cp.search("cant go"), f"Pattern {pat!r} must match \"cant go\""


# ---------------------------------------------------------------------------
# 20. M4 regression — mark_all_unverified helper
# ---------------------------------------------------------------------------

class TestM4MarkAllUnverified:

    def test_marks_all_items_sentinel_ok_false(self):
        """mark_all_unverified stamps every queue item sentinel_ok=False across all accounts."""
        from engine.marketing.sentinel import mark_all_unverified

        body = "Size appropriately."
        plan = _plan({
            "flagship": [
                _item("i1", "flagship", body=body, slot="s1"),
                _item("i2", "flagship", body=body, slot="s2"),
            ],
            "receipts": [
                _item("i3", "receipts", body=body, slot="s3"),
            ],
        })

        mark_all_unverified(plan)

        for acc in plan["accounts"]:
            for item in acc["queue"]:
                assert item.get("sentinel_ok") is False, \
                    f"Item {item.get('id')} should have sentinel_ok=False"

    def test_does_not_touch_other_fields(self):
        """mark_all_unverified only sets sentinel_ok; does not modify type/headline/body."""
        from engine.marketing.sentinel import mark_all_unverified

        i1 = _item("i1", "flagship", type="signal",
                   headline="Original headline",
                   body="Original body. Size appropriately.")
        plan = _plan({"flagship": [i1]})

        mark_all_unverified(plan)

        item = plan["accounts"][0]["queue"][0]
        assert item["headline"] == "Original headline"
        assert item["body"] == "Original body. Size appropriately."
        assert item["type"] == "signal"
        assert item["sentinel_ok"] is False


# ---------------------------------------------------------------------------
# 18. Quality pass (W1b): full reason lists, slot economics, reason classes,
#     exception override of caps, receipts_context, error_report
# ---------------------------------------------------------------------------

class TestFullReasonLists:

    def test_lexicon_collects_every_hit(self):
        """An item with three lexicon phrases lists ALL of them, not just the first."""
        plan = _plan({"flagship": [_item(
            "bad1", "flagship",
            headline="A guaranteed winner",
            body="Sure thing, get in now. Size appropriately.",
        )]})
        cfg = _cfg()
        cfg["sentinel"]["lexicon_phrases"] = ["guaranteed", "sure thing", "get in now"]
        _, report = gate_plan(plan, cfg, receipts_age_days=3)
        (entry,) = report["quarantined"]
        matched = {r for r in entry["reasons"] if r.startswith("advice_lexicon:")}
        assert matched == {
            "advice_lexicon:guaranteed",
            "advice_lexicon:sure thing",
            "advice_lexicon:get in now",
        }, f"expected all three hits, got {matched}"

    def test_lexicon_phrase_and_pattern_both_recorded(self):
        """A phrase hit does not shadow a pattern hit on the same item."""
        plan = _plan({"flagship": [_item(
            "bad2", "flagship",
            headline="Guaranteed — this will hit 10x",
            body="Size appropriately.",
        )]})
        _, report = gate_plan(plan, _cfg(), receipts_age_days=3)
        (entry,) = report["quarantined"]
        assert "advice_lexicon:guaranteed" in entry["reasons"]
        assert any(r.startswith("advice_lexicon:will hit") for r in entry["reasons"])


class TestCapSlotEconomics:

    def test_media_killed_item_consumes_no_media_slot(self):
        """Check-then-commit: a cadence-killed media item must not burn the media
        slot a later clean media item needed."""
        cfg = _cfg(max_posts=2)
        cfg["sentinel"]["max_media_posts_per_account_per_day"] = 1
        body = "Size appropriately."
        plan = _plan({"flagship": [
            _item("a1", "flagship", headline="Post one plain", body=body, cashtag="$A", ticker="A", slot="s1"),
            _item("a2", "flagship", headline="Post two plain", body=body, cashtag="$B", ticker="B", slot="s2"),
            # a3 is over the daily cap (2) — killed by cadence, has media
            _item("a3", "flagship", headline="Post three chart", body=body, cashtag="$C", ticker="C",
                  slot="s3", chart_id="c3"),
        ]})
        _, report = gate_plan(plan, cfg, receipts_age_days=3)
        q = {e["id"]: e["reasons"] for e in report["quarantined"]}
        assert q == {"a3": ["cadence_cap_daily"]}
        # Media counter untouched by the dead a3: hits recorded = 0
        assert report["checks"]["media_cap"]["hits"] == 0

    def test_empty_string_chart_id_is_not_media(self):
        """chart_id '' is no media (matches outbox truthiness), never counts."""
        cfg = _cfg(max_posts=4)
        cfg["sentinel"]["max_media_posts_per_account_per_day"] = 0
        plan = _plan({"flagship": [
            _item("a1", "flagship", body="Size appropriately.", chart_id=""),
        ]})
        _, report = gate_plan(plan, cfg, receipts_age_days=3)
        assert report["counts"]["quarantined"] == 0

    def test_reply_cap_uses_distinct_reason(self):
        """Reply overflow reports reply_cap_daily, not the generic cadence reason."""
        plan = _plan({"flagship": [
            _item("r1", "flagship", type="reply", body="Size appropriately."),
        ]})
        _, report = gate_plan(plan, _cfg(), receipts_age_days=3)
        (entry,) = report["quarantined"]
        assert entry["reasons"] == ["reply_cap_daily"]
        assert report["checks"]["cadence"]["reply_cap_hits"] == 1


class TestReasonClasses:

    def test_counts_split_policy_vs_overflow(self):
        """Capacity trims and policy flags are counted separately."""
        cfg = _cfg(max_posts=1)
        body = "Size appropriately."
        plan = _plan({"flagship": [
            _item("ok1", "flagship", headline="Fine post", body=body, slot="s1"),
            _item("over1", "flagship", headline="Over the cap", body=body, slot="s2"),
            _item("bad1", "flagship", headline="A guaranteed winner", body=body, slot="s3"),
        ]})
        _, report = gate_plan(plan, cfg, receipts_age_days=3)
        counts = report["counts"]
        assert counts["quarantined"] == 2
        assert counts["quarantined_policy"] == 1
        assert counts["quarantined_overflow"] == 1
        by_id = {e["id"]: e["class"] for e in report["quarantined"]}
        assert by_id == {"over1": "overflow", "bad1": "policy"}

    def test_mixed_reasons_classify_as_policy(self):
        """Any policy reason on an item outranks its overflow reasons."""
        from engine.marketing.sentinel import reason_class
        assert reason_class("cadence_cap_daily") == "overflow"
        assert reason_class("cashtag_cap:$AAPL") == "overflow"
        assert reason_class("slot_collision:D1-AM") == "overflow"
        assert reason_class("media_cap_daily") == "overflow"
        assert reason_class("reply_cap_daily") == "overflow"
        assert reason_class("advice_lexicon:guaranteed") == "policy"
        assert reason_class("near_dup:x") == "policy"
        assert reason_class("shared_media:c1") == "policy"
        assert reason_class("missing_disclosure") == "policy"
        assert reason_class("account_disabled") == "policy"
        assert reason_class("stale_receipts_ledger") == "policy"


class TestExceptionOverridesCaps:

    def test_exception_restores_cap_killed_item(self):
        """An operator allow-exception clears a step-5 cap violation (human
        override by design)."""
        cfg = _cfg(max_posts=1)
        body = "Size appropriately."
        plan = _plan({"flagship": [
            _item("k1", "flagship", headline="First post fine", body=body, slot="s1"),
            _item("k2", "flagship", headline="Second post over cap", body=body, slot="s2"),
        ]})
        exceptions = {"k2": {"item_id": "k2", "allow": True, "reason": "operator ok"}}
        annotated, report = gate_plan(plan, cfg, receipts_age_days=3, exceptions=exceptions)
        assert report["counts"]["quarantined"] == 0
        assert report["counts"]["exceptions_applied"] == 1
        item = annotated["accounts"][0]["queue"][1]
        assert item["sentinel_ok"] is True
        assert item["exception_applied"] == "operator ok"

    def test_exception_restored_item_recounted_once(self):
        """An item restored from a content violation, then cap-killed, then
        restored again counts as ONE exception application."""
        cfg = _cfg(max_posts=1)
        body = "Size appropriately."
        plan = _plan({"flagship": [
            _item("k1", "flagship", headline="First post fine", body=body, slot="s1"),
            # lexicon-killed in step 1, restored in step 3, over cap in step 5,
            # restored again in step 6
            _item("k2", "flagship", headline="A guaranteed winner", body=body, slot="s2"),
        ]})
        exceptions = {"k2": {"item_id": "k2", "allow": True, "reason": "operator ok"}}
        annotated, report = gate_plan(plan, cfg, receipts_age_days=3, exceptions=exceptions)
        assert report["counts"]["quarantined"] == 0
        assert report["counts"]["exceptions_applied"] == 1


class TestReceiptsContext:

    def test_receipts_context_missing_index(self, tmp_path):
        from engine.marketing.sentinel import receipts_context
        age, window = receipts_context(tmp_path)
        assert age is None and window is None

    def test_receipts_context_age_from_newest_signal(self, tmp_path):
        """Age = days since the NEWEST _signal_date across plans."""
        from datetime import datetime, timedelta, timezone
        from engine.marketing.sentinel import receipts_context
        idx_dir = tmp_path / "site" / "prophet"
        idx_dir.mkdir(parents=True)
        # Same clock as receipts_context (UTC). Local date.today() goes red every
        # evening 5pm–midnight PDT when local/UTC dates differ (and in local-ahead
        # zones the newest row would land future-dated and be skipped as corrupt).
        today = datetime.now(timezone.utc).date()
        newest = (today - timedelta(days=2)).isoformat()
        older = (today - timedelta(days=30)).isoformat()
        idx_dir.joinpath("index.json").write_text(json.dumps({"plans": [
            {"_signal_date": older}, {"_signal_date": newest}, {"_signal_date": ""},
        ]}), encoding="utf-8")
        age, _window = receipts_context(tmp_path)
        assert age == 2


class TestErrorReport:

    def test_error_report_shape(self):
        from engine.marketing.sentinel import error_report
        rpt = error_report(as_of="2026-07-19", exc="boom")
        assert rpt["plan_status"] == "error"
        assert rpt["as_of"] == "2026-07-19"
        assert rpt["counts"]["quarantined_policy"] == 0
        assert any("boom" in n for n in rpt["notes"])

    def test_error_report_reads_live_kill_switch(self, monkeypatch):
        from engine.marketing.sentinel import error_report
        monkeypatch.delenv("MARKETING_PUBLISH_ENABLED", raising=False)
        assert error_report()["publish_enabled"] is False
        monkeypatch.setenv("MARKETING_PUBLISH_ENABLED", "1")
        assert error_report()["publish_enabled"] is True


# ─────────────────────────────────────────────────────────────────────────────
# F1: per-day cap keyed on (account, day), not plan-wide
# ─────────────────────────────────────────────────────────────────────────────

class TestPerDayCap:
    """The daily cap must apply PER DAY, not once across the whole 7-day plan.

    The bug: max_posts_per_account_per_day=2 was keyed on account alone, so a
    21-item 7-day plan (3/day) passed only 2 total and quarantined 19 as
    cadence_cap_daily. Correct: 2/day × 7 days = 14 pass, 7 quarantined.
    """

    def test_two_per_day_across_seven_days(self):
        # 21 items: 3 per day (AM/PM/EOD) across D1..D7, each a distinct cashtag
        # so the same-cashtag cap can't interfere with the cadence cap under test.
        items = []
        n = 0
        for d in range(1, 8):
            for suffix in ("AM", "PM", "EOD"):
                items.append(_item(
                    f"i{n}", "flagship",
                    headline=f"Headline {n}", body="Size appropriately.",
                    cashtag=f"${chr(65 + n)}{n}", ticker=f"T{n}",
                    slot=f"D{d}-{suffix}",
                ))
                n += 1
        plan = _plan({"flagship": items})

        annotated, report = gate_plan(plan, _cfg(max_posts=2, max_cashtag=99))

        assert report["counts"]["passed"] == 14
        cadence_q = [q for q in report["quarantined"]
                     if "cadence_cap_daily" in q["reasons"]]
        assert len(cadence_q) == 7
        # The two that survive each day are that day's first two (queue order).
        passed_ids = {e["id"] for e in report["passed"]}
        assert "i0" in passed_ids and "i1" in passed_ids  # D1-AM, D1-PM
        assert "i2" not in passed_ids                      # D1-EOD → over cap

    def test_publish_time_families_bucket_separately(self):
        # MOVER / THEME / CONF are their own per-day buckets — a full D1 does not
        # eat into the mover budget.
        items = [
            _item("d1a", "flagship", slot="D1-AM", cashtag="$A", ticker="A"),
            _item("d1p", "flagship", slot="D1-PM", cashtag="$B", ticker="B"),
            _item("mv1", "flagship", slot="MOVER-01", cashtag="$C", ticker="C"),
            _item("mv2", "flagship", slot="MOVER-02", cashtag="$D", ticker="D"),
        ]
        plan = _plan({"flagship": items})
        annotated, report = gate_plan(plan, _cfg(max_posts=2, max_cashtag=99))
        # D1 full (2) + MOVER full (2) = all 4 pass; no cadence cap.
        assert report["counts"]["passed"] == 4
        assert not [q for q in report["quarantined"]
                    if "cadence_cap_daily" in q["reasons"]]

    def test_unlimited_cap_never_quarantines_for_cadence(self):
        """max_posts_per_account_per_day = -1 (unlimited) → NO cadence_cap_daily,
        no matter how many post to one account/day. The autonomous-cadence policy
        (operator 2026-07-24): volume is paced by the post-time 10-minute floor,
        not a daily ceiling. Mirrors test_two_per_day_across_seven_days, which
        under a cap of 2 quarantines 7 of the 21 — here all 21 clear."""
        items = []
        n = 0
        for d in range(1, 8):
            for suffix in ("AM", "PM", "EOD"):
                items.append(_item(
                    f"i{n}", "flagship",
                    headline=f"Headline {n}", body="Size appropriately.",
                    cashtag=f"${chr(65 + n)}{n}", ticker=f"T{n}",
                    slot=f"D{d}-{suffix}",
                ))
                n += 1
        plan = _plan({"flagship": items})

        annotated, report = gate_plan(plan, _cfg(max_posts=-1, max_cashtag=99))

        assert report["counts"]["passed"] == 21
        assert not [q for q in report["quarantined"]
                    if "cadence_cap_daily" in q["reasons"]]


def test_cap_unlimited_decodes_no_limit_sentinels():
    """_cap_unlimited: -1 / "unlimited" → None (no bound); everything else is a
    normal bounded cap. The null gotcha is pinned deliberately: a present-null
    collapses to the (bounded) default via _get, so null is NOT how you express
    unlimited — the -1 sentinel is."""
    from engine.marketing.sentinel import _cap_unlimited
    assert _cap_unlimited({"k": -1}, "k", 2) is None            # -1 → unlimited
    assert _cap_unlimited({"k": "unlimited"}, "k", 2) is None   # string sentinel
    assert _cap_unlimited({"k": 5}, "k", 2) == 5                # explicit bound honoured
    assert _cap_unlimited({"k": 0}, "k", 2) == 0               # 0 = block all (≠ unlimited)
    assert _cap_unlimited({}, "k", 2) == 2                      # missing key → default
    assert _cap_unlimited({"k": None}, "k", 2) == 2            # null collapses to default (NOT unlimited)
    assert _cap_unlimited({"k": "junk"}, "k", 2) == 2         # unparseable → default


# ─────────────────────────────────────────────────────────────────────────────
# F2: report carries a `passed` list (operator can see what cleared)
# ─────────────────────────────────────────────────────────────────────────────

class TestPassedList:
    def test_report_has_passed_entries_with_fields(self):
        items = [
            _item("p1", "flagship", slot="D1-AM", cashtag="$A", ticker="A",
                  headline="Clean one"),
            _item("p2", "flagship", slot="D1-PM", cashtag="$B", ticker="B",
                  headline="Clean two"),
        ]
        plan = _plan({"flagship": items})
        annotated, report = gate_plan(plan, _cfg(max_posts=99, max_cashtag=99))

        assert "passed" in report
        assert isinstance(report["passed"], list)
        assert len(report["passed"]) == report["counts"]["passed"] == 2
        entry = next(e for e in report["passed"] if e["id"] == "p1")
        # Same field set the operator sees on quarantined rows.
        assert set(entry) >= {"id", "account", "slot", "type", "cashtag", "headline"}
        assert entry["account"] == "flagship"
        assert entry["slot"] == "D1-AM"
        assert entry["headline"] == "Clean one"

    def test_passed_list_matches_count_with_some_quarantined(self):
        # cap=1/day → of two D1 items, one passes, one is quarantined.
        items = [
            _item("a", "flagship", slot="D1-AM", cashtag="$A", ticker="A"),
            _item("b", "flagship", slot="D1-PM", cashtag="$B", ticker="B"),
        ]
        plan = _plan({"flagship": items})
        annotated, report = gate_plan(plan, _cfg(max_posts=1, max_cashtag=99))
        assert len(report["passed"]) == report["counts"]["passed"] == 1
        assert report["passed"][0]["id"] == "a"


# ─────────────────────────────────────────────────────────────────────────────
# F1 unit: the day-bucket derivation itself
# ─────────────────────────────────────────────────────────────────────────────

class TestSlotDayBucket:
    def test_day_slots_bucket_by_day_number(self):
        from engine.marketing.sentinel import _slot_day_bucket
        assert _slot_day_bucket("D1-AM") == "D1"
        assert _slot_day_bucket("D7-EOD") == "D7"

    def test_publish_time_families(self):
        from engine.marketing.sentinel import _slot_day_bucket
        assert _slot_day_bucket("MOVER-01") == "MOVER"
        assert _slot_day_bucket("THEME-02") == "THEME"
        assert _slot_day_bucket("CONF-01") == "CONF"

    def test_unrecognized_and_empty_share_one_bucket(self):
        from engine.marketing.sentinel import _slot_day_bucket
        assert _slot_day_bucket("s1") == ""
        assert _slot_day_bucket("") == ""
        assert _slot_day_bucket("random") == ""


# ─────────────────────────────────────────────────────────────────────────────
# F3e: accounts disabled via the effective model show as OFF in the report
# ─────────────────────────────────────────────────────────────────────────────

class TestEffectiveDisabledAccounts:
    def test_enabled_false_account_is_reported_disabled(self):
        cfg = _cfg()
        # theme_desk not enabled via the new model (no literal `disabled: true`).
        for acc in cfg["desk_network"]["accounts"]:
            if acc["id"] == "theme_desk":
                acc["enabled"] = False
        plan = _plan({"flagship": [_item("i0", "flagship", slot="D1-AM")]})
        annotated, report = gate_plan(plan, cfg)
        off = report["checks"]["kill_switch"]["accounts_disabled"]
        assert "theme_desk" in off
        assert "flagship" not in off


# ═════════════════════════════════════════════════════════════════════════════
# POST-TIME GATES (ported from PR #3928, adapted to the W1 pipeline 2026-07-29)
#
# Three gates that run at PUBLISH time, not plan time, over ONE account's
# same-day posted history. #3928's other halves (consequence.py, the template
# bank rewrites) are obsolete under the W1 no-fallback law — the bank no longer
# ships planned copy anywhere — but these three are lane-independent post-time
# checks that gate_plan structurally cannot perform, because an account's day is
# assembled from lanes that never share a plan.
#
# EVERY GATE HERE IS PROVEN TO RUN. The unit sections pin the arithmetic; the
# publisher section drives the real scripts/marketing_publisher.main() over a
# fixture clock and asserts the ledger, so reverting a call site turns these red
# rather than leaving a tested function nothing calls.
# ═════════════════════════════════════════════════════════════════════════════

# ── The real corpus these gates were measured on ─────────────────────────────
# Two posts flagship ACTUALLY SHIPPED on 2026-07-25 (outbox ids
# ob-2026-07-25-8431ea805e / ob-2026-07-25-b87e9ce3f7, both `watchlist`, both
# status `posted`). One template, two tickers, two prices. Verbatim from
# data/marketing/outbox/items.jsonl so the threshold is pinned against live copy
# and not against a paraphrase of it.
_REAL_FRAME_A = (
    "$PLTR into the week\n\nClosed 123, down 7% on the week, under both the "
    "20- (128) and 50-day (132). About 41% off the highs, in the lower third of "
    "its range. Into next week, the 20-day at 128 is the first hurdle back. On "
    "the watch list, not a call."
)
_REAL_FRAME_B = (
    "$MSFT into the week\n\nClosed 382, down 3% on the week, under both the "
    "20- (387) and 50-day (399). About 29% off the highs, in the lower third of "
    "its range. Into next week, the 20-day at 387 is the first hurdle back. "
    "Watching, no position."
)
# The HIGHEST-scoring pair that must NOT trip: also flagship, also one day
# (2026-07-28), also both posted, and genuinely two different reads — one is a
# bare stance, the other carries a level and a dated volume spike.
_REAL_DIFFERENT_A = (
    "Watching $TEL, not buying yet\n\nPrice is the most honest thing on the "
    "screen. Interesting name, unfinished setup. The list stays honest that way."
)
_REAL_DIFFERENT_B = (
    "Watching $CUBI, not buying yet\n\nCUBI closed back above 77.99, the "
    "average price paid since the Jun 26 volume spike. Interesting name, "
    "unfinished setup. The list stays honest that way."
)


class TestSkeletonFrame:
    """The template-frame primitive: blank the tickers and numbers, compare."""

    def test_skeleton_blanks_tickers_and_numbers(self):
        from engine.marketing.sentinel import skeleton

        out = skeleton("$TEL close to going. Almost there at 41.20.")
        assert "TEL" not in out and "41" not in out
        assert "close to going" in out

    def test_the_founder_desk_trio_collapses_to_one_frame(self):
        """"$TEL close to going" / "$CBOE close to going" / "$FDS close to going"
        — the three posts the founder desk shipped in one day on 2026-07-28."""
        from engine.marketing.sentinel import skeleton

        frames = {
            skeleton(f"{tag} close to going\n\nAlmost there at {px}. "
                     f"Haven't touched it. Watching live.")
            for tag, px in (("$TEL", "41.20"), ("$CBOE", "219.80"), ("$FDS", "486.10"))
        }
        assert len(frames) == 1, f"three renders of one template gave {len(frames)} frames"

    def test_token_jaccard_structurally_cannot_see_it(self):
        """WHY THIS GATE EXISTS, pinned as an assertion.

        The publisher's per-account near-dup gate compares RAW tokens, and the
        tickers and prices differ, so the real 2026-07-25 pair scores UNDER its
        bar and both posts went out. Blank the tickers and numbers and the same
        pair is over the frame bar. If a future refactor ever makes raw Jaccard
        catch this on its own, this assertion is the thing that says so.
        """
        from engine.marketing.outbox import _NEAR_DUP_JACCARD, token_jaccard
        from engine.marketing.sentinel import (
            _DEFAULT_FRAME_SIMILARITY, skeleton_similarity)

        raw = token_jaccard(_REAL_FRAME_A, _REAL_FRAME_B)
        frame = skeleton_similarity(_REAL_FRAME_A, _REAL_FRAME_B)
        assert raw < _NEAR_DUP_JACCARD, (
            f"raw jaccard {raw:.3f} already clears the near-dup bar "
            f"{_NEAR_DUP_JACCARD} — this fixture no longer pins the blind spot")
        assert frame >= _DEFAULT_FRAME_SIMILARITY, (
            f"the real shipped pair scored {frame:.3f} on skeletons")

    def test_two_genuinely_different_reads_do_not_collide(self):
        """The false-positive guard, on the closest real pair in the corpus.

        Measured over the whole live outbox on 2026-07-29: 124 same-(account,
        day) pairs among approved/posted items, exactly ONE at or over 0.60 (the
        pair above, at 0.778). This is the runner-up, at 0.500 — so the shipped
        threshold sits in a real gap rather than on a slope.
        """
        from engine.marketing.sentinel import (
            _DEFAULT_FRAME_SIMILARITY, skeleton_similarity)

        score = skeleton_similarity(_REAL_DIFFERENT_A, _REAL_DIFFERENT_B)
        assert score < _DEFAULT_FRAME_SIMILARITY, (
            f"two real, genuinely different posts scored {score:.3f}")

    def test_frame_repeat_of_names_the_prior_post(self):
        from engine.marketing.sentinel import frame_repeat_of, skeleton_tokens

        prior = [("ob-earlier", skeleton_tokens(_REAL_FRAME_A))]
        hit = frame_repeat_of(skeleton_tokens(_REAL_FRAME_B), prior, threshold=0.60)
        assert hit is not None
        prior_id, score = hit
        assert prior_id == "ob-earlier"
        assert score >= 0.60

    def test_a_different_frame_passes(self):
        from engine.marketing.sentinel import frame_repeat_of, skeleton_tokens

        prior = [("ob-earlier", skeleton_tokens(_REAL_FRAME_A))]
        assert frame_repeat_of(skeleton_tokens(_REAL_DIFFERENT_B), prior,
                              threshold=0.60) is None

    def test_empty_prior_history_passes(self):
        """The first post of the day has nothing to repeat."""
        from engine.marketing.sentinel import frame_repeat_of, skeleton_tokens

        assert frame_repeat_of(skeleton_tokens(_REAL_FRAME_A), [], threshold=0.60) is None
        assert frame_repeat_of(skeleton_tokens(_REAL_FRAME_A), None, threshold=0.60) is None

    def test_threshold_comes_from_config(self):
        """A config key nothing reads is a lie in a config file."""
        from engine.marketing.sentinel import (
            _DEFAULT_FRAME_SIMILARITY, frame_similarity_threshold)

        assert frame_similarity_threshold({"sentinel": {"frame_similarity": 0.9}}) == 0.9
        assert frame_similarity_threshold({}) == _DEFAULT_FRAME_SIMILARITY
        # A garbage value must fall back, never crash the publisher.
        assert frame_similarity_threshold(
            {"sentinel": {"frame_similarity": "wat"}}) == _DEFAULT_FRAME_SIMILARITY


class TestFillerKinds:
    """The no-ticker, no-chart kinds and their daily budget."""

    def test_the_three_no_ticker_kinds_are_filler(self):
        from engine.marketing.sentinel import FILLER_KINDS, is_filler_kind

        assert FILLER_KINDS == frozenset({"macro", "event", "education"})
        for kind in ("macro", "event", "education", "MACRO"):
            assert is_filler_kind(kind), kind

    def test_every_ticker_bearing_kind_is_not_filler(self):
        from engine.marketing.sentinel import is_filler_kind

        for kind in ("signal", "chart", "watchlist", "receipt", "mover",
                     "theme_list", "breaking", "", None):
            assert not is_filler_kind(kind), kind

    def test_cap_comes_from_config_and_minus_one_is_unlimited(self):
        from engine.marketing.sentinel import (
            _DEFAULT_MAX_FILLER_PER_ACCOUNT_PER_DAY,
            max_filler_per_account_per_day)

        assert max_filler_per_account_per_day(
            {"sentinel": {"max_filler_per_account_per_day": 3}}) == 3
        assert max_filler_per_account_per_day(
            {"sentinel": {"max_filler_per_account_per_day": -1}}) is None
        assert max_filler_per_account_per_day({}) == \
            _DEFAULT_MAX_FILLER_PER_ACCOUNT_PER_DAY

    def test_shipped_config_carries_the_key(self):
        """The committed marketing.yml must actually set it — the plan side and
        the publisher both read it, so a missing key silently changes both."""
        import yaml

        cfg = yaml.safe_load((ROOT / "config" / "marketing.yml").read_text())
        sc = cfg["sentinel"]
        assert sc["max_filler_per_account_per_day"] == 1
        assert sc["frame_similarity"] == 0.60
        assert sc["require_ticker_and_number"] is False


class TestSubstanceFloor:
    """Name a cashtag, state a quantity. Armed by config, dark by default."""

    def test_a_no_ticker_post_states_no_ticker(self):
        from engine.marketing.sentinel import substance_gap

        assert substance_gap("Rates drifted again today. Liquidity is thinner.") \
            == "ticker"

    def test_a_cashtag_with_no_quantity_states_no_number(self):
        from engine.marketing.sentinel import substance_gap

        assert substance_gap("$AAPL is interesting here. Watching it.") == "number"

    def test_a_post_naming_both_passes(self):
        from engine.marketing.sentinel import substance_gap

        assert substance_gap("$AAPL closed 214, back over its 20-day.") is None

    def test_the_ticker_may_come_from_the_item_not_the_copy(self):
        """Outbox items keep the name on source.ticker; the copy is the fallback."""
        from engine.marketing.sentinel import substance_gap

        assert substance_gap("Closed 214, back over the 20-day.", ticker="AAPL") is None
        assert substance_gap("Closed 214, back over the 20-day.") == "ticker"

    def test_looser_than_the_copywriter_number_rule_on_purpose(self):
        """copywriter._NUMBER_RE skips bare 1-2 digit integers so "T1" and
        "3 weeks" do not read as invented prices. THIS regex takes any digit: the
        question here is "does the post state a quantity at all", not "is every
        quantity whitelisted". The divergence is pinned so a future unification
        has to be deliberate."""
        from engine.marketing.copywriter import _NUMBER_RE
        from engine.marketing.sentinel import substance_gap

        text = "$AAPL has held this base for 3 weeks."
        assert not _NUMBER_RE.search(text), \
            "fixture no longer exercises the divergence — pick another number"
        assert substance_gap(text) is None

    def test_the_floor_is_dark_by_default_and_arms_by_config(self):
        from engine.marketing.sentinel import require_ticker_and_number

        assert require_ticker_and_number({}) is False
        assert require_ticker_and_number(
            {"sentinel": {"require_ticker_and_number": True}}) is True
        # A quoted "false" must never arm a gate (the _flag contract).
        assert require_ticker_and_number(
            {"sentinel": {"require_ticker_and_number": "false"}}) is False


# ─────────────────────────────────────────────────────────────────────────────
# The PLAN side of the filler cap (content_studio.apply_reuse_budget)
#
# THE RECONCILIATION. Measured on the committed tilts, the W1 allocator gives
# ONE desk 3-10 filler slots on the emitted day (sophia 10, kelly 9, meagan 7,
# flagship 6, cici 6, founder 3), and the live 2026-07-28/29 queues carried 6
# for flagship. A publish-time cap of 1 with no plan-side trim would therefore
# have quarantined 5 of 6 planned-and-written posts every night. The plan side
# reads the SAME sentinel key and trims first, which is what makes the
# publisher's copy a backstop instead of a scythe.
# ─────────────────────────────────────────────────────────────────────────────

def _filler_row(account: str, n: int, *, kind: str = "macro", day: str = "D1") -> dict:
    return {"id": account, "queue": [
        {"id": f"{account}-{i}", "account": account, "type": kind, "ticker": "",
         "slot": f"{day}-S{i + 1}"}
        for i in range(n)
    ]}


class TestPlanSideFillerBudget:
    def test_four_filler_posts_trim_to_one(self):
        """Kelly's 2026-07-28 day, at the seam where it should have been stopped."""
        from engine.marketing.content_studio import apply_reuse_budget

        rows = [_filler_row("kelly", 4)]
        counts = apply_reuse_budget(rows, cfg=None, day_prefix="D1")
        assert len(rows[0]["queue"]) == 1
        assert counts["dropped_filler_budget"] == 3

    def test_the_budget_is_per_account(self):
        from engine.marketing.content_studio import apply_reuse_budget

        rows = [_filler_row("kelly", 3), _filler_row("sophia", 3)]
        apply_reuse_budget(rows, cfg=None, day_prefix="D1")
        assert [len(r["queue"]) for r in rows] == [1, 1]

    def test_mixed_filler_kinds_share_one_budget(self):
        """macro + event + education are one class, not three budgets — Kelly's
        day was four posts across two of them."""
        from engine.marketing.content_studio import apply_reuse_budget

        rows = [{"id": "kelly", "queue": [
            {"id": f"k{i}", "account": "kelly", "type": k, "ticker": "",
             "slot": f"D1-S{i + 1}"}
            for i, k in enumerate(("macro", "education", "event"))]}]
        counts = apply_reuse_budget(rows, cfg=None, day_prefix="D1")
        assert len(rows[0]["queue"]) == 1
        assert counts["dropped_filler_budget"] == 2

    def test_ticker_bearing_posts_are_untouched(self):
        """The budget is about the NO-ticker kinds; a watchlist post is not filler."""
        from engine.marketing.content_studio import apply_reuse_budget

        rows = [{"id": "flagship", "queue": [
            {"id": f"w{i}", "account": "flagship", "type": "watchlist",
             "ticker": f"T{i}", "slot": f"D1-S{i + 1}"} for i in range(4)]}]
        counts = apply_reuse_budget(rows, cfg=None, day_prefix="D1")
        assert len(rows[0]["queue"]) == 4
        assert counts["dropped_filler_budget"] == 0

    def test_only_the_emitted_day_is_trimmed(self):
        """D2-D7 never reach the outbox, so trimming them would delete posts
        nothing was going to send — the same scoping the ticker budget uses."""
        from engine.marketing.content_studio import apply_reuse_budget

        rows = [_filler_row("kelly", 4, day="D3")]
        apply_reuse_budget(rows, cfg=None, day_prefix="D1")
        assert len(rows[0]["queue"]) == 4

    def test_unlimited_keeps_everything(self):
        from engine.marketing.content_studio import apply_reuse_budget

        rows = [_filler_row("kelly", 4)]
        counts = apply_reuse_budget(
            rows, cfg={"sentinel": {"max_filler_per_account_per_day": -1}},
            day_prefix="D1")
        assert len(rows[0]["queue"]) == 4
        assert counts["dropped_filler_budget"] == 0

    def test_the_number_comes_from_the_sentinel_key(self):
        """ONE reader for the key: the plan side must move when it moves, or the
        two seams disagree about how many filler posts a day holds."""
        from engine.marketing.content_studio import apply_reuse_budget

        rows = [_filler_row("kelly", 4)]
        apply_reuse_budget(
            rows, cfg={"sentinel": {"max_filler_per_account_per_day": 2}},
            day_prefix="D1")
        assert len(rows[0]["queue"]) == 2

    def test_survivors_still_get_their_angle(self):
        """The trim must not cost the surviving filler post its angle stamp —
        the writer, the emit provenance and the learning lane all read it."""
        from engine.marketing.content_studio import apply_reuse_budget

        rows = [_filler_row("kelly", 3)]
        apply_reuse_budget(rows, cfg=None, day_prefix="D1")
        assert rows[0]["queue"][0].get("angle")

    def test_the_shipped_config_trims_the_real_allocator(self):
        """END-TO-END on the committed tilts: every enabled desk lands at 1."""
        import yaml

        from engine.marketing import content_studio as cs

        cfg = yaml.safe_load((ROOT / "config" / "marketing.yml").read_text())
        accounts = [a for a in ((cfg.get("desk_network") or {}).get("accounts") or [])
                    if a.get("enabled")]
        assert accounts, "fixture needs at least one enabled desk"
        rows = []
        for acct in accounts:
            tilt = acct.get("tilt") or {}
            items = cs.plan_account(account=acct, plans=[], n_days=7,
                                    per_day=len(cs._LADDER_SLOTS), seed=0,
                                    tilt=tilt or None)
            rows.append({"id": acct["id"], "queue": [i.as_dict() for i in items]})

        def _d1_filler(row):
            return sum(1 for i in row["queue"]
                       if str(i.get("slot", "")).startswith("D1-")
                       and i.get("type") in {"macro", "event", "education"})

        before = {r["id"]: _d1_filler(r) for r in rows}
        assert max(before.values()) >= 2, (
            "THE RECONCILIATION IS VACUOUS: the allocator no longer plans 2+ "
            f"filler posts for any desk ({before}), so the publish-time cap "
            "could not have killed planned work and this trim is unneeded")
        cs.apply_reuse_budget(rows, cfg=cfg, day_prefix="D1")
        after = {r["id"]: _d1_filler(r) for r in rows}
        assert set(after.values()) <= {0, 1}, after


# ─────────────────────────────────────────────────────────────────────────────
# The PUBLISH side: the gates run inside scripts/marketing_publisher.main()
#
# A gate with no production caller is not a gate. These drive the real publisher
# over a fixture clock with a fake backend and assert the outbox ledger, so
# deleting a call site turns them red.
# ─────────────────────────────────────────────────────────────────────────────

_PG_NOW = datetime(2026, 7, 22, 12, 0, 0, tzinfo=timezone.utc)
_PG_AS_OF = "2026-07-22"
_PG_UNLIMITED = {"sentinel": {"max_posts_per_account_per_day": -1}}


class _PGFakePublisher:
    backend = "buffer"

    def __init__(self) -> None:
        self.calls: list[dict] = []

    def publish(self, **kwargs):
        from engine.marketing.social_publisher import Receipt

        self.calls.append(kwargs)
        at_iso = (kwargs.get("now") or _PG_NOW).strftime("%Y-%m-%dT%H:%M:%SZ")
        return Receipt(True, f"buf-{len(self.calls)}", None, None, self.backend, at_iso)

    def list_channels(self):
        return []


def _pg_write_cfg(root: Path, *, extra: str = "") -> None:
    (root / "config").mkdir(parents=True, exist_ok=True)
    (root / "config" / "marketing.yml").write_text(
        "sentinel:\n"
        "  max_posts_per_account_per_day: -1\n"   # isolate the ported gates
        "  max_filler_per_account_per_day: 1\n"
        "  frame_similarity: 0.60\n" + extra
        + "publish:\n"
          "  backend: buffer\n"
          "  require_approval: true\n"
          "  auto_approve: true\n"
          "  min_minutes_between_any_posts: 0\n"
          "  post_jitter_max_min: 0\n"
          "  channels:\n"
          '    desk: "buf-chan-0"\n',
        encoding="utf-8",
    )
    p = root / "data" / "marketing"
    p.mkdir(parents=True, exist_ok=True)
    (p / "live_quotes_snapshot.json").write_text(json.dumps({
        "asof": _PG_NOW.strftime("%Y-%m-%dT%H:%M:%SZ"), "quotes": {},
    }), encoding="utf-8")


def _pg_seed(root: Path, *, text: str, kind: str = "watchlist",
             immediate: bool = False, posted: bool = False) -> str:
    """Queue + approve (and optionally POST) one item on the `desk` account.

    A ladder item gets an explicit past slot time so it does not take the
    immediate/breaking path, which the volume caps exempt.
    """
    from engine.marketing.outbox import enqueue, make_item, transition

    when = _PG_NOW - timedelta(hours=3)
    item = make_item(
        account="desk", kind=kind, text=text, as_of=_PG_AS_OF,
        scheduled_at=("immediate" if immediate
                      else (_PG_NOW - timedelta(hours=1)).strftime("%Y-%m-%dT%H:%M:%SZ")),
        provenance="content_studio", now=when)
    assert enqueue(item, root=root, cfg=_PG_UNLIMITED) == "queued"
    assert transition(item["id"], "approved", actor="test", root=root, now=when)
    if posted:
        assert transition(item["id"], "posted", actor="test", root=root, now=when)
    return item["id"]


def _pg_run(monkeypatch, root: Path, fake, *, voice_gate: bool = False) -> int:
    import scripts.marketing_publisher as pub

    monkeypatch.setenv("MARKETING_PUBLISH_ENABLED", "1")
    monkeypatch.setenv("BUFFER_TOKEN", "test-token")
    monkeypatch.setattr(pub, "_make_publisher", lambda backend, *, token, cfg: fake)
    if not voice_gate:
        # The fixtures above are VERBATIM live posts, kept verbatim on purpose so
        # the frame threshold is pinned against real copy rather than a
        # paraphrase. They predate the 2026-07-30 voice laws and carry five
        # prices each, so the voice gate quarantines them before the FRAME gate
        # — the gate under test here — ever sees them. Neutralising it keeps
        # each test measuring its own seam; the voice gate has its own suite in
        # tests/test_marketing_voice_laws.py, and one test below deliberately
        # leaves it armed to prove it still fires on this same corpus.
        monkeypatch.setattr(pub, "_queued_voice_violations", lambda text, kind="": [])
    return pub.main(["--live", "--root", str(root),
                     "--now", _PG_NOW.strftime("%Y-%m-%dT%H:%M:%SZ")])


class TestPublisherFrameGate:
    def test_a_frame_repeat_of_todays_post_is_quarantined(self, monkeypatch, tmp_path):
        """THE NAMED DEFECT, at the seam that should have stopped it: one post of
        the frame already went out today, the second is the same template with a
        different ticker, and it must not reach the network."""
        from engine.marketing.outbox import current_statuses

        _pg_write_cfg(tmp_path)
        _pg_seed(tmp_path, text=_REAL_FRAME_A, posted=True)
        pending = _pg_seed(tmp_path, text=_REAL_FRAME_B)

        fake = _PGFakePublisher()
        assert _pg_run(monkeypatch, tmp_path, fake) == 0
        assert fake.calls == [], "a template-frame repeat reached the network"
        assert current_statuses(tmp_path)[pending] == "quarantined"

    def test_the_voice_gate_fires_on_this_same_live_corpus(self, monkeypatch, tmp_path):
        """The gate the other tests here neutralise, left armed on purpose.

        _REAL_FRAME_B is a post flagship ACTUALLY SHIPPED on 2026-07-25. It
        carries five prices, which is the "number soup" the operator named
        ("shut up with all of these numbers, its literally so AI like"). With
        no sibling to trip the frame gate it would post today; the voice gate
        is what stops it. If this test ever goes green-by-passing, the
        neutralisation in _pg_run has quietly become a hole rather than a
        scope decision.
        """
        from engine.marketing.outbox import current_statuses

        _pg_write_cfg(tmp_path)
        pending = _pg_seed(tmp_path, text=_REAL_FRAME_B)

        fake = _PGFakePublisher()
        assert _pg_run(monkeypatch, tmp_path, fake, voice_gate=True) == 0
        assert fake.calls == [], "pre-law live copy reached the network"
        assert current_statuses(tmp_path)[pending] == "quarantined"

    def test_a_genuinely_different_read_still_posts(self, monkeypatch, tmp_path):
        """The same fixture shape, flipped by COPY alone — which is what makes
        the test above a test of the frame and not of "something refused"."""
        from engine.marketing.outbox import current_statuses

        _pg_write_cfg(tmp_path)
        _pg_seed(tmp_path, text=_REAL_DIFFERENT_A, posted=True)
        pending = _pg_seed(tmp_path, text=_REAL_DIFFERENT_B)

        fake = _PGFakePublisher()
        assert _pg_run(monkeypatch, tmp_path, fake) == 0
        assert len(fake.calls) == 1
        assert current_statuses(tmp_path)[pending] == "posted"

    def test_two_frame_siblings_in_ONE_run_cannot_both_go_out(
            self, monkeypatch, tmp_path):
        """The folded state is read before the loop, so without in-loop
        bookkeeping a single sweep sends both — which is exactly how the three
        "$X close to going" renders shipped on one day."""
        from engine.marketing.outbox import current_statuses

        _pg_write_cfg(tmp_path)
        a = _pg_seed(tmp_path, text=_REAL_FRAME_A)
        b = _pg_seed(tmp_path, text=_REAL_FRAME_B)

        fake = _PGFakePublisher()
        assert _pg_run(monkeypatch, tmp_path, fake) == 0
        assert len(fake.calls) == 1
        statuses = current_statuses(tmp_path)
        assert sorted((statuses[a], statuses[b])) == ["posted", "quarantined"]

    def test_the_frame_gate_binds_breaking_items(self, monkeypatch, tmp_path):
        """Every SIMILARITY gate above it binds immediates on purpose (a
        coordinated-looking set of renders is worse when it is fast). Only the
        VOLUME caps exempt breaking. This pins which family the gate is in."""
        from engine.marketing.outbox import current_statuses

        _pg_write_cfg(tmp_path)
        _pg_seed(tmp_path, text=_REAL_FRAME_A, posted=True)
        pending = _pg_seed(tmp_path, text=_REAL_FRAME_B, immediate=True)

        fake = _PGFakePublisher()
        assert _pg_run(monkeypatch, tmp_path, fake) == 0
        assert fake.calls == []
        assert current_statuses(tmp_path)[pending] == "quarantined"

    def test_a_loose_threshold_lets_the_pair_through(self, monkeypatch, tmp_path):
        """The publisher reads the CONFIG number, not a buried constant."""
        from engine.marketing.outbox import current_statuses

        _pg_write_cfg(tmp_path)
        (tmp_path / "config" / "marketing.yml").write_text(
            (tmp_path / "config" / "marketing.yml").read_text().replace(
                "frame_similarity: 0.60", "frame_similarity: 0.99"),
            encoding="utf-8")
        _pg_seed(tmp_path, text=_REAL_FRAME_A, posted=True)
        pending = _pg_seed(tmp_path, text=_REAL_FRAME_B)

        fake = _PGFakePublisher()
        assert _pg_run(monkeypatch, tmp_path, fake) == 0
        assert current_statuses(tmp_path)[pending] == "posted"


class TestPublisherFillerCap:
    def test_a_second_filler_post_is_held_not_quarantined(self, monkeypatch, tmp_path):
        """Kelly's day, at the last gate. HELD (still approved): the item is
        fine, the day is full, and it can post tomorrow — the same treatment the
        daily cap and the cadence resolver give."""
        from engine.marketing.outbox import current_statuses

        _pg_write_cfg(tmp_path)
        _pg_seed(tmp_path, kind="macro", posted=True,
                 text="Rates drifted lower again, the third session in a row.")
        pending = _pg_seed(
            tmp_path, kind="education",
            text="What a moving average actually tells you, in plain words.")

        fake = _PGFakePublisher()
        assert _pg_run(monkeypatch, tmp_path, fake) == 0
        assert fake.calls == [], "a second filler post cleared the daily cap"
        assert current_statuses(tmp_path)[pending] == "approved"

    def test_a_ticker_post_is_not_filler(self, monkeypatch, tmp_path):
        """Same fixture, one field changed: the cap covers macro/event/education
        only, so a watchlist post after a macro post still goes out."""
        from engine.marketing.outbox import current_statuses

        _pg_write_cfg(tmp_path)
        _pg_seed(tmp_path, kind="macro", posted=True,
                 text="Rates drifted lower again, the third session in a row.")
        pending = _pg_seed(tmp_path, kind="watchlist", text=_REAL_DIFFERENT_B)

        fake = _PGFakePublisher()
        assert _pg_run(monkeypatch, tmp_path, fake) == 0
        assert len(fake.calls) == 1
        assert current_statuses(tmp_path)[pending] == "posted"

    def test_breaking_is_exempt_from_the_filler_cap(self, monkeypatch, tmp_path):
        """"Breaking has no limits" (operator 2026-07-27) — the standing ruling
        that already exempts immediates from the daily cap and the resolver. A
        breaking `event` post is exactly what it protects."""
        from engine.marketing.outbox import current_statuses

        _pg_write_cfg(tmp_path)
        _pg_seed(tmp_path, kind="macro", posted=True,
                 text="Rates drifted lower again, the third session in a row.")
        pending = _pg_seed(
            tmp_path, kind="event", immediate=True,
            text="The jobs print landed hot and the whole curve repriced at once.")

        fake = _PGFakePublisher()
        assert _pg_run(monkeypatch, tmp_path, fake) == 0
        assert len(fake.calls) == 1, "the filler cap killed a breaking post"
        assert current_statuses(tmp_path)[pending] == "posted"

    def test_unlimited_disarms_the_cap(self, monkeypatch, tmp_path):
        from engine.marketing.outbox import current_statuses

        _pg_write_cfg(tmp_path)
        (tmp_path / "config" / "marketing.yml").write_text(
            (tmp_path / "config" / "marketing.yml").read_text().replace(
                "max_filler_per_account_per_day: 1",
                "max_filler_per_account_per_day: -1"),
            encoding="utf-8")
        _pg_seed(tmp_path, kind="macro", posted=True,
                 text="Rates drifted lower again, the third session in a row.")
        pending = _pg_seed(
            tmp_path, kind="education",
            text="What a moving average actually tells you, in plain words.")

        fake = _PGFakePublisher()
        assert _pg_run(monkeypatch, tmp_path, fake) == 0
        assert current_statuses(tmp_path)[pending] == "posted"


class TestPublisherSubstanceFloor:
    def test_dark_by_default_the_post_goes_out(self, monkeypatch, tmp_path):
        """The shipped posture: the verdict is computed and counted, nothing is
        enforced. Arming it is a product ruling about the no-ticker lanes."""
        from engine.marketing.outbox import current_statuses

        _pg_write_cfg(tmp_path)
        pending = _pg_seed(tmp_path, kind="macro",
                           text="Rates drifted lower, and positioning has not caught up.")

        fake = _PGFakePublisher()
        assert _pg_run(monkeypatch, tmp_path, fake) == 0
        assert len(fake.calls) == 1
        assert current_statuses(tmp_path)[pending] == "posted"

    def test_armed_by_config_the_same_post_is_quarantined(self, monkeypatch, tmp_path):
        """ONE key flips it, and the fixture is otherwise identical — which is
        what makes this a test of the floor rather than of "something refused"."""
        from engine.marketing.outbox import current_statuses

        _pg_write_cfg(tmp_path, extra="  require_ticker_and_number: true\n")
        pending = _pg_seed(tmp_path, kind="macro",
                           text="Rates drifted lower, and positioning has not caught up.")

        fake = _PGFakePublisher()
        assert _pg_run(monkeypatch, tmp_path, fake) == 0
        assert fake.calls == []
        assert current_statuses(tmp_path)[pending] == "quarantined"

    def test_armed_a_post_naming_a_ticker_and_a_number_still_ships(
            self, monkeypatch, tmp_path):
        from engine.marketing.outbox import current_statuses

        _pg_write_cfg(tmp_path, extra="  require_ticker_and_number: true\n")
        pending = _pg_seed(tmp_path, kind="watchlist", text=_REAL_DIFFERENT_B)

        fake = _PGFakePublisher()
        assert _pg_run(monkeypatch, tmp_path, fake) == 0
        assert len(fake.calls) == 1
        assert current_statuses(tmp_path)[pending] == "posted"


class TestPublisherGatesFailSoft:
    def test_a_broken_sentinel_never_wedges_the_queue(self, monkeypatch, tmp_path):
        """A guard that can stop the whole desk is worse than the defect it
        guards. If the gate module cannot be read, the post still goes out and
        every pre-existing gate still runs."""
        from engine.marketing import sentinel as sen
        from engine.marketing.outbox import current_statuses

        _pg_write_cfg(tmp_path)
        _pg_seed(tmp_path, text=_REAL_FRAME_A, posted=True)
        pending = _pg_seed(tmp_path, text=_REAL_FRAME_B)

        def _boom(*a, **k):
            raise RuntimeError("sentinel gates unavailable")

        # The publisher imports sentinel lazily inside main(), so the module
        # attribute is the patch point (monkeypatch restores it either way).
        # Fault-injecting the CONFIG READ is the realistic shape: everything the
        # gates do in the loop afterwards is pure string work on a str and cannot
        # raise, so the import and the setup read are the whole risk surface.
        monkeypatch.setattr(sen, "frame_similarity_threshold", _boom)
        fake = _PGFakePublisher()
        assert _pg_run(monkeypatch, tmp_path, fake) == 0
        assert len(fake.calls) == 1, "a broken gate must not hold the queue"
        assert current_statuses(tmp_path)[pending] == "posted"


class TestPostedTodayRowsSurface:
    """The same-day surface both gates read, and its agreement with the cap."""

    def test_rows_carry_id_text_and_kind(self):
        from engine.marketing.outbox import posted_today_rows_by_account

        state = {
            "items": {"i1": {"account": "desk", "text": "one", "kind": "macro"}},
            "status": {"i1": "posted"},
            "last": {"i1": {"at": "2026-07-22T10:00:00Z"}},
        }
        rows = posted_today_rows_by_account(state, "2026-07-22")
        assert rows == {"desk": [("i1", "one", "macro")]}

    def test_the_cap_counter_is_a_count_over_the_same_rows(self):
        """ONE predicate for "did this consume a posting slot today" — if the two
        ever diverge, the cap and the gates disagree about the account's day."""
        from engine.marketing.outbox import (
            posted_today_by_account, posted_today_rows_by_account)

        state = {
            "items": {
                "i1": {"account": "desk", "text": "a", "kind": "macro"},
                "i2": {"account": "desk", "text": "b", "kind": "signal"},
                "i3": {"account": "desk", "text": "c", "kind": "macro"},
                "i4": {"account": "other", "text": "d", "kind": "macro"},
            },
            "status": {"i1": "posted", "i2": "posting", "i3": "quarantined",
                       "i4": "posted"},
            "last": {"i1": {"at": "2026-07-22T10:00:00Z"},
                     "i2": {"at": "2026-07-22T11:00:00Z"},
                     "i3": {"at": "2026-07-22T09:00:00Z"},
                     "i4": {"at": "2026-07-21T10:00:00Z"}},
        }
        rows = posted_today_rows_by_account(state, "2026-07-22")
        counts = posted_today_by_account(state, "2026-07-22")
        assert counts == {a: len(r) for a, r in rows.items()}
        assert counts == {"desk": 2}, "quarantined and yesterday must not count"
