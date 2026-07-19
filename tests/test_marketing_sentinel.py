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
"""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

import pytest

from engine.marketing.sentinel import gate_plan, run_gate, publish_enabled


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
        assert sc["max_posts_per_account_per_day"] == _DEFAULT_MAX_POSTS_PER_ACCOUNT_PER_DAY
        assert sc["max_same_cashtag_per_account_per_day"] == _DEFAULT_MAX_SAME_CASHTAG_PER_ACCOUNT_PER_DAY
        assert sc["max_replies_per_account_per_day"] == _DEFAULT_MAX_REPLIES_PER_ACCOUNT_PER_DAY
        assert sc["max_receipt_age_days"] == _DEFAULT_MAX_RECEIPT_AGE_DAYS
        assert sc["links_allowed"] == _DEFAULT_LINKS_ALLOWED
        assert sc["max_media_posts_per_account_per_day"] == _DEFAULT_MAX_MEDIA_POSTS_PER_ACCOUNT_PER_DAY
        assert sc["max_cashtags_per_post"] == _DEFAULT_MAX_CASHTAGS_PER_POST

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
        from datetime import date, timedelta
        from engine.marketing.sentinel import receipts_context
        idx_dir = tmp_path / "site" / "prophet"
        idx_dir.mkdir(parents=True)
        newest = (date.today() - timedelta(days=2)).isoformat()
        older = (date.today() - timedelta(days=30)).isoformat()
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
